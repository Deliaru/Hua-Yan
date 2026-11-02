"""WP-E 失真对照：同一批需求卡、同一个模拟客户随机种子，比较三种做法到达研发时的需求信息。
G1 业务员转述（假设的转述噪声）/ G2 一次性翻译（只有开场白，全部转化对照）/ G3 化言（觉追问 → L2 → L3 → 回问）。
抽取与转译是规则实现，觉按配置用规则原型或本地 Jue-K，不调用大模型。只有 sim 与 eval 可以读需求卡。
trace=True 时另返回每张卡 G2、G3 的逐轮轨迹（WP-E2 单卡对照），统计口径不变。"""
from __future__ import annotations

import random

import pandas as pd

from huayan.clock import get_clock
from huayan.contracts import NeedCard, NeedState, ReqItem, Requirement, ReuseProposal, Seeds, Session, Turn
from huayan.escalation.translate import draft_chem_need, draft_product_need, match_translations
from huayan.events import EventLog
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto
from huayan.jue.publish import ask_hints
from huayan.jue.state import requirement_state, trans_hits
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.l1.extract import RuleExtractor, apply_extraction
from huayan.sim import SimCustomer

GROUPS = ["G1 业务员转述", "G2 一次性翻译", "G3 化言（不含回问）", "G3 化言"]
METRICS = {"completeness": "关键信息完整率", "slot_error": "槽位错误率", "mistranslation": "错译率",
           "asks": "平均追问次数", "backs": "平均回问次数", "backs_useful": "回问事后有用比例",
           "traceable": "可回查率", "returned": "研发需退回比例"}


class _Dialog:
    """一段模板模式的对话：模拟客户按卡回答，规则抽取逐轮更新 NeedState。"""

    def __init__(self, card: NeedCard, seeds: Seeds, rng: random.Random, extractor: RuleExtractor):
        self.customer, self.extractor = SimCustomer(card, seeds, rng), extractor
        self.id, self.turns = f"sess:{card.id}", []
        self.need = NeedState(session_id=self.id, customer_id=card.customer_id, sales_id="sales:S01", extracted_by="rule")
        self.say("customer", self.customer.opening())

    def say(self, speaker: str, text: str) -> None:
        n = len(self.turns) + 1
        self.turns.append(Turn(id=f"turn:{self.id}:{n}", session_id=self.id, n=n, speaker=speaker, text=text,
                               ts=get_clock().now()))
        self.need = apply_extraction(self.need, self.extractor.extract(self.turns, self.need), self.turns)

    def ask(self, slot) -> None:
        self.say("sales", slot.ask_text)
        self.say("customer", self.customer.reply(slot.ask_text))

    def session(self) -> Session:
        return Session(id=self.id, customer_id=self.need.customer_id, sales_id=self.need.sales_id,
                       started_at=self.turns[0].ts, turns=list(self.turns), need=self.need, status="escalated")


def _score(card: NeedCard, seeds: Seeds, trans: dict[str, list[str]], group: str, phenomenon: str | None,
           slots: dict[str, str], items: list[ReqItem], asks: int, backs: int = 0, useful: int = 0) -> dict:
    """真值 = 现象 + 该现象全部必问槽位（客户自己也说不清的不计）。"""
    required = [s for s in next(p for p in seeds.phenomena if p.id == card.phenomenon).required_slots
                if s not in card.unknown_slots]
    phen_ok = phenomenon == card.phenomenon
    req_ok = sum(slots.get(s) == card.slots[s] for s in required)
    cites = [[r for r in i.ku_refs if r in trans] for i in items]
    return {"group": group, "card_id": card.id, "key_ok": phen_ok + req_ok, "key_total": 1 + len(required),
            "received": len(slots), "wrong": sum(v != card.slots[s] for s, v in slots.items()),
            "items": len(items), "translated": sum(bool(c) for c in cites),
            "mistranslated": sum(any(card.phenomenon not in trans[r] for r in c) for c in cites),
            "quoted": sum(bool(i.quote_refs) for i in items), "asks": asks, "backs": backs, "backs_useful": useful,
            "returned": not phen_ok or req_ok < len(required)}


def _gaps(card: NeedCard, seeds: Seeds, phenomenon: str | None, slots: dict[str, str]) -> dict:
    """研发视角：缺了哪些、错了哪些（与 _score 的退回口径一致），以及给人看的退回理由。"""
    required = [s for s in next(p for p in seeds.phenomena if p.id == card.phenomenon).required_slots
                if s not in card.unknown_slots]
    labels = {s.id: s.label for s in seeds.slots} | {"phenomenon": "现象"}
    missing = ([] if phenomenon == card.phenomenon else ["phenomenon"]) + [s for s in required if s not in slots]
    wrong = [s for s in required if s in slots and slots[s] != card.slots[s]]
    reason = "；".join(f"{k}：{'、'.join(labels[s] for s in v)}" for k, v in (("缺", missing), ("错", wrong)) if v)
    return {"missing": missing, "wrong": wrong, "returned": bool(missing or wrong), "return_reason": reason}


def relay_g1(card: NeedCard, seeds: Seeds, relay: dict, seed: int, extractor: RuleExtractor):
    """G1 业务员转述：按习惯问，再按假设的噪声模型写给研发。返回 (研发收到的现象, 研发收到的条件)。
    V11.2 旧流程推算在同一张卡上复用。"""
    slot_defs = {s.id: s for s in seeds.slots}
    d = _Dialog(card, seeds, random.Random(seed), extractor)
    for slot in relay["habit_slots"]:
        d.ask(slot_defs[slot])
    noise = random.Random(seed + 1)
    phenomenon = None if noise.random() < relay["vague_prob"] else d.need.phenomenon
    told = {}
    for slot, value in d.need.known().items():
        r = noise.random()
        if r >= relay["drop_prob"]:
            told[slot] = (noise.choice([v for v in slot_defs[slot].values if v != value])
                          if r < relay["drop_prob"] + relay["swap_prob"] else value)
    return phenomenon, told


def _items(items: list[ReqItem], turns: list[Turn], owners: dict[str, str] | None = None) -> list[dict]:
    """需求单条目 → 展示：原话取第一条 quote_ref 的发言；owners 给出所引转化知识的归属人。"""
    text = {t.id: t.text for t in turns}
    out = []
    for i in items:
        row = {"text": i.text, "quote": text[i.quote_refs[0]] if i.quote_refs else None}
        if owners is not None:
            row["owner"] = next((owners[r] for r in i.ku_refs if r in owners), None)
        out.append(row)
    return out


def _model(cfg: dict, meter):
    if cfg["model"] == "jue_k":
        return JueK(cfg["jue_k_dir"], "config/templates", "realtime", meter)
    return JueProto("config/templates", None, "realtime", meter)


def run_distortion(cards: list[NeedCard], seeds: Seeds, cfg: dict, rng: random.Random, meter=None,
                   trace: bool = False):
    """每张卡 × 每组一行；meter 记录觉的调用（用来证明发现环节没有大模型调用）。
    trace=True 时返回 (DataFrame, {card_id: 轨迹})。"""
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog())
    extractor, model = RuleExtractor(seeds), _model(cfg["jue"], meter)
    slot_defs, phens = {s.id: s for s in seeds.slots}, {p.id: p for p in seeds.phenomena}
    pm = next(a for a in seeds.actors if a.id == "pm:agent")
    rd = min((a for a in seeds.actors if a.role == "rd"), key=lambda a: a.id)
    translations = kb.list(rd, kinds=["translation"])
    trans = {ku.id: ku.phenomenon_ids for ku in translations}
    owners = {ku.id: ku.owner for ku in translations}
    products, relay, jue = kb.products(), cfg["relay"], cfg["jue"]
    rows, traces = [], {}
    for card in cards:
        seed, now = rng.randrange(2 ** 31), get_clock().now()
        score = lambda *a, **k: rows.append(_score(card, seeds, trans, *a, **k))

        # G1 业务员转述：按习惯问，再按假设的噪声模型写给研发；没有原话、没有依据
        phenomenon, told = relay_g1(card, seeds, relay, seed, extractor)
        items = [ReqItem(text=f"现象：{phenomenon or '染色有问题'}")] + [ReqItem(text=f"条件：{v}", slot=s)
                                                                       for s, v in told.items()]
        score(GROUPS[0], phenomenon, told, items, len(relay["habit_slots"]))

        # G2 一次性翻译：只有开场白；全部转化对照（L2、L3 混用、不按现象过滤）匹配一次
        d = _Dialog(card, seeds, random.Random(seed), extractor)
        opening = d.turns[0]
        items = [ReqItem(text=f"『{h.ku.title}』→ {h.ku.text.split(' → ', 1)[1]}", quote_refs=[opening.id],
                         ku_refs=[h.ku.id]) for h in match_translations(opening.text, kb, rd)]
        items += [ReqItem(text=f"条件：{v}", slot=s, quote_refs=[opening.id]) for s, v in d.need.known().items()]
        score(GROUPS[1], d.need.phenomenon, d.need.known(), items, 0)
        one_shot = {"turns": [{"speaker": opening.speaker, "text": opening.text}], "chem_lang": _items(items, d.turns),
                    **_gaps(card, seeds, d.need.phenomenon, d.need.known())}

        # G3 化言：按觉的第一条提示追问 → L2 → L3；再对 L3 草稿回问，回填后重新起草 L3
        d = _Dialog(card, seeds, random.Random(seed), extractor)
        asks, rounds = 0, []
        required = next(p for p in seeds.phenomena if p.id == card.phenomenon).required_slots
        for _ in range(jue["max_rounds"]):
            hints, out = ask_hints(d.need, seeds, products, model, jue["ask_threshold"])
            scored = {x.object_id: x for x in out.decisions if x.family == "ask_slot"}
            said = d.turns[-1]
            rounds.append({"turn": {"speaker": said.speaker, "text": said.text},
                           "p_need": {s: scored[f"slot:{d.id}/{s}"].p_need for s in required},
                           "scored_by": {s: scored[f"slot:{d.id}/{s}"].scored_by or out.scored_by for s in required},
                           "threshold": jue["ask_threshold"], "asked": hints[0].slot if hints else None,
                           "ask_text": slot_defs[hints[0].slot].ask_text if hints else None})
            if not hints:
                break
            d.ask(slot_defs[hints[0].slot])
            asks += 1
        session = d.session()
        # v5：业务员签字升级 → 空单 → 产品经理 Agent 查无现成产品后起草 L2 → 研发接单 → 起草 L3
        req = Requirement(id=f"req:{card.id}", question_id=f"q:{card.id}", session_ids=[session.id],
                          phenomenon=d.need.phenomenon, known_slots=d.need.known(), assigned_rd=rd.id,
                          reuse=ReuseProposal(product_id=None), status="draft", drafted_by=pm.id, created_at=now)
        pm_draft = draft_product_need(req, [session], kb, pm, now)
        req.direction, req.product_lang = pm_draft.direction, pm_draft.product_lang
        req.status, req.rd_accepted_by = "rd_accepted", rd.id
        chem = draft_chem_need(req, [session], kb, rd, now).chem_lang
        score(GROUPS[2], req.phenomenon, req.known_slots, chem, asks)
        state = requirement_state(req, d.need, seeds, kb, now, EventLog())
        out = model.propose(state)
        backs = sorted(((x.p_need, state.objects[x.object_id].attrs["slot"], x.scored_by or out.scored_by)
                        for x in out.decisions
                        if x.family == "ask_back" and x.p_need is not None and x.p_need >= jue["back_threshold"]),
                       reverse=True)[:jue["max_backs"]]
        useful, back_asks = 0, []
        for p_need, slot, scored_by in backs:
            before = d.need.known()
            d.ask(slot_defs[slot])
            changed = trans_hits(phens[req.phenomenon], before, kb, 3) != trans_hits(phens[req.phenomenon],
                                                                                    d.need.known(), kb, 3)
            useful += changed
            back_asks.append({"slot": slot, "p_need": p_need, "scored_by": scored_by,
                              "threshold": jue["back_threshold"], "ask_text": slot_defs[slot].ask_text,
                              "answer": d.turns[-1].text, "changed": changed})
        if backs:
            req = req.model_copy(update={"known_slots": d.need.known()})
            chem = draft_chem_need(req, [d.session()], kb, rd, now).chem_lang
        score(GROUPS[3], req.phenomenon, req.known_slots, chem, asks, len(backs), useful)
        traces[card.id] = {"one_shot": one_shot, "huayan": {
            "rounds": rounds, "back_asks": back_asks, "chem_lang": _items(chem, d.turns, owners),
            **_gaps(card, seeds, req.phenomenon, req.known_slots)}}
    return (pd.DataFrame(rows), traces) if trace else pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """每组一行；比率按全部卡合计后相除。G1 不引用转化知识，错译率记为空。"""
    out = {}
    for group, g in df.groupby("group", sort=False):
        s = g.sum(numeric_only=True)
        out[group] = {"completeness": s.key_ok / s.key_total, "slot_error": s.wrong / s.received,
                      "mistranslation": s.mistranslated / s["items"] if s.translated else None,
                      "asks": g.asks.mean(), "backs": g.backs.mean(),
                      "backs_useful": s.backs_useful / s.backs if s.backs else None,
                      "traceable": s.quoted / s["items"], "returned": g.returned.mean()}
    return pd.DataFrame(out).T
