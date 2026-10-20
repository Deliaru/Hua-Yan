"""Q7.5 真实案例回测：案例的客户第一句话进入真实链路，模拟客户按案例的最终条件如实回答，觉照常追问，
统计第一轮是否就问到后来导致补样或返工的条件（late_conditions），以及需求进研发时的必问信息完整率。
对照组：业务员原样转述（失真对照的转述假设）与强模型一次性翻译（经网关，caller eval:one_shot）；
觉分冻结与进化后两份模型各跑一次。只有 eval/ 读案例的答案（铁律 5）。"""
import hashlib
import random
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from huayan.contracts import LLMRequest, Message, NeedCard, Tier
from huayan.gateway.mock import MockGateway
from huayan.jue.jue_k import JueK
from huayan.sim import SimCustomer

SOURCES = ("oral", "raw", "restored", "summary")
VIEWERS = {"L0": "customer:C01", "L1": "sales:S01", "L3": "rd:R02"}


class Case(BaseModel):
    id: str
    source: Literal["oral", "raw", "restored", "summary"]
    first_words: str
    final_conditions: dict[str, str]
    late_conditions: list[str]
    phenomenon: str


class OneShot(BaseModel):
    """一次性翻译给研发的需求：客户话里能确定的条件，与认为研发还要确认的条件。"""
    conditions: dict[str, str]
    to_confirm: list[str]


def load_cases(path, seeds) -> tuple[bool, list[Case]]:
    """读案例文件并按冻结的词表校验（真实输入边界）。返回 (是否模拟样本, 案例)。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    slots = {s.id: s.values for s in seeds.slots}
    phens = {p.label: p.id for p in seeds.phenomena} | {p.id: p.id for p in seeds.phenomena}
    cases = []
    for item in data["cases"]:
        case = Case.model_validate(item)
        if case.phenomenon not in phens:
            raise ValueError(f"{case.id}：现象不在词表里：{case.phenomenon}")
        bad = [f"{k}={v}" for k, v in case.final_conditions.items() if v not in slots.get(k, [])] + \
              [k for k in case.late_conditions if k not in case.final_conditions]
        if bad:
            raise ValueError(f"{case.id}：条件不在词表里或晚到条件没有最终取值：{bad}")
        cases.append(case.model_copy(update={"phenomenon": phens[case.phenomenon]}))
    return bool(data.get("simulated")), cases


def fingerprint(path="seeds/slots.yaml") -> dict:
    """冻结词表的指纹与修改时间，写进报告。"""
    p = Path(path)
    return {"path": p.as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()[:16],
            "modified": datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds")}


def card_of(case: Case, seeds) -> NeedCard:
    """模拟客户只知道案例的最终条件；其余槽位答「不清楚」。"""
    unknown = [s.id for s in seeds.slots if s.id not in case.final_conditions]
    return NeedCard(id=case.id, phenomenon=case.phenomenon,
                    slots=case.final_conditions | {s: next(x.values[0] for x in seeds.slots if x.id == s) for s in unknown},
                    unknown_slots=unknown, customer_id=VIEWERS["L0"], chem_savvy=False, wants_mechanism=False,
                    truth_product=None)


def _required(app, case):
    """研发视图里该现象的必问条件，只算客户知道的（案例里有最终取值的）。"""
    rd = app.actors[VIEWERS["L3"]]
    return [s for s in next(p.required_slots for p in app.kb.view(rd).phenomena if p.id == case.phenomenon)
            if s in case.final_conditions]


def _complete(known, case, required) -> bool:
    return all(known.get(s) == case.final_conditions[s] for s in required)


def run_jue(app, case: Case, seed: int) -> dict:
    """觉组：业务员陪同，按觉的第一条提示追问（最多 8 轮）；觉提出升级时业务员签字。"""
    sales = VIEWERS["L1"]
    customer = SimCustomer(card_of(case, app.seeds), app.seeds, random.Random(f"{seed}:{case.id}"))
    sid = app.start_session(VIEWERS["L0"], sales).id
    s = app.add_turn(sid, "customer", case.first_words)
    first = [h.slot for h in s.hints]
    asked = []
    for _ in range(8):
        if s.status != "open" or not s.hints:
            break
        asked.append(s.hints[0].slot)
        app.add_turn(sid, "sales", s.hints[0].ask_text)
        s = app.add_turn(sid, "customer", customer.reply(s.hints[0].ask_text))
    if s.status == "open":
        app.recommend_now(sid)
    app.tick()
    if any(q.object_id == f"session:{sid}" for q in app.bus.list(family="escalate")):
        app.escalate(sid, sales)
    known = app._sessions[sid].need.known()
    escalated = any(sid in r.session_ids for r in app._requirements.values())
    required = _required(app, case)
    return {"phenomenon_ok": app._sessions[sid].need.phenomenon == case.phenomenon, "first_round": first,
            "asked": asked, "late_first": [c for c in case.late_conditions if c in first],
            "escalated": escalated, "complete": _complete(known, case, required), "known": known}


def run_relay(app, case: Case, seed: int, relay: dict) -> dict:
    """转述组：业务员按习惯问，再按失真对照的转述假设（漏记、记错、现象说笼统）写给研发。"""
    customer = SimCustomer(card_of(case, app.seeds), app.seeds, random.Random(f"{seed}:{case.id}"))
    sid = app.start_session(VIEWERS["L0"], VIEWERS["L1"]).id
    app.add_turn(sid, "customer", case.first_words)
    asks = {s.id: s.ask_text for s in app.seeds.slots}
    for slot in relay["habit_slots"]:
        app.add_turn(sid, "sales", asks[slot])
        app.add_turn(sid, "customer", customer.reply(asks[slot]))
    noise, values = random.Random(f"{seed}:{case.id}:relay"), {s.id: s.values for s in app.seeds.slots}
    told = {}
    for slot, value in app._sessions[sid].need.known().items():
        r = noise.random()
        if r >= relay["drop_prob"]:
            told[slot] = noise.choice([v for v in values[slot] if v != value]) if r < relay["drop_prob"] + relay["swap_prob"] else value
    return {"late_first": [c for c in case.late_conditions if c in relay["habit_slots"]],
            "complete": _complete(told, case, _required(app, case)), "known": told}


def run_one_shot(app, case: Case) -> dict:
    """一次性翻译组：只有客户第一句话，强模型直接写成给研发的需求（经网关，caller eval:one_shot）。"""
    vocab = "\n".join(f"- {s.id}（{s.label}）：{'、'.join(s.values)}" for s in app.seeds.slots)
    out, _ = app.gateway.structured(LLMRequest(tier=Tier.STRONG, caller="eval:one_shot", messages=[
        Message(role="system", content="你是染整助剂企业的技术翻译。把客户的第一句话一次性写成给研发的需求："
                "conditions 只写客户话里能确定的工艺条件（槽位 → 取值，只用下列词表）；to_confirm 列出研发开工前还要向客户确认的槽位。\n"
                + vocab),
        Message(role="user", content=case.first_words)]), OneShot)
    return {"late_first": [c for c in case.late_conditions if c in out.to_confirm],
            "complete": _complete(out.conditions, case, _required(app, case)), "known": out.conditions,
            "to_confirm": out.to_confirm}


def use_model(app, model_dir) -> None:
    app.jue_realtime = JueK(model_dir, app.config["templates_dir"], "realtime", app.meter)


def one_shot_impl(app) -> str:
    return "mock（离线桩，不代表强模型）" if isinstance(app.gateway, MockGateway) else "live"


def qa_table(app, questions: list[str]) -> list[dict]:
    """同一问题三个身份看到什么、依据谁的知识（只读分层召回）。"""
    rows = []
    for q in questions:
        for level, actor_id in VIEWERS.items():
            r = app.kb.explore(q, app.actors[actor_id])
            rows.append({"question": q, "level": level, "actor": actor_id,
                         "readable": [f"{u.title}（{u.owner}）" for u in r.units],
                         "capabilities": [f"{c.form}（{c.granted_by}）" for c in r.capabilities],
                         "stubs": [f"L{b.level} {b.kind}（{b.owner}）" for b in r.stubs], "hints": r.hints})
    return rows
