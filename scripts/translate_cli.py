"""一段对话的 L1 → L2 → L3 转译（规则骨架，零成本）。M1 演示用。

uv run python scripts/translate_cli.py [--dialogue 对话.yaml] [--seeds-dir seeds]
对话 yaml：sessions: [{customer_id, sales_id, turns: [[customer|sales, 文字], ...]}]；不给则用内置的「锦纶氨纶 + 气流缸」两段升级对话。
"""
import argparse
from datetime import timedelta
from pathlib import Path

import yaml

from huayan.clock import get_clock
from huayan.contracts import NeedState, Question, Requirement, Session, SlotFill, Turn
from huayan.domain import find_phenomenon, find_slot_values, load_seeds
from huayan.escalation.translate import draft_chem_need, draft_product_need
from huayan.events import EventLog
from huayan.knowledge import AuditLog, KnowledgeBase

DEFAULT = {"sessions": [
    {"customer_id": "customer:C02", "sales_id": "sales:S01", "turns": [
        ["customer", "我们染完以后布面深一块浅一块，客户老投诉"], ["sales", "请问是什么面料？"],
        ["customer", "锦氨弹力布"], ["sales", "请问用的是什么染色设备？"], ["customer", "气流缸，浴比很低"]]},
    {"customer_id": "customer:C03", "sales_id": "sales:S02", "turns": [
        ["customer", "锦氨布在气流机里染，颜色不匀，回修了好几次"], ["sales", "有没有环保方面的要求？"],
        ["customer", "没什么要求"]]}]}


def build_session(k: int, spec: dict, seeds, at) -> Session:
    sid = f"sess:{k}"
    turns = [Turn(id=f"turn:{sid}:{n}", session_id=sid, n=n, speaker=sp, text=tx, ts=at + timedelta(minutes=n))
             for n, (sp, tx) in enumerate(spec["turns"], 1)]
    need = NeedState(session_id=sid, customer_id=spec["customer_id"], sales_id=spec["sales_id"],
                     turn_count=len(turns), extracted_by="rule")
    for t in (t for t in turns if t.speaker == "customer"):       # 与规则抽取器同口径：先到先得，置信度 0.7
        if need.phenomenon is None and (ph := find_phenomenon(t.text, seeds.phenomena)):
            need.phenomenon, need.phenomenon_quote = ph
        for slot, (value, quote) in find_slot_values(t.text, seeds.slots).items():
            need.slots.setdefault(slot, SlotFill(slot=slot, value=value, status="filled", confidence=0.7,
                                                 quote=quote, turn_id=t.id))
    return Session(id=sid, customer_id=spec["customer_id"], sales_id=spec["sales_id"], started_at=at, turns=turns,
                   need=need, status="escalated")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dialogue")
    ap.add_argument("--seeds-dir", default="seeds")
    args = ap.parse_args()
    seeds = load_seeds(args.seeds_dir)
    spec = yaml.safe_load(Path(args.dialogue).read_text(encoding="utf-8")) if args.dialogue else DEFAULT
    at = get_clock().now()
    sessions = [build_session(k, s, seeds, at) for k, s in enumerate(spec["sessions"], 1)]
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog())
    actors = {a.id: a for a in seeds.actors}
    pm = next(a for a in seeds.actors if a.role == "pm")
    rd = min((a for a in seeds.actors if a.role == "rd"), key=lambda a: a.id)
    labels = {s.id: s.label for s in seeds.slots}
    quotes = {t.id: t.text for s in sessions for t in s.turns}
    owners = {u.id: u.owner for u in kb.list(rd)}

    def show(items):
        for k, i in enumerate(items, 1):
            text = f"{labels[i.slot]}：{i.text.removeprefix('条件：')}" if i.slot else i.text
            print(f"  {k}. {text}")
            for q in i.quote_refs:
                print(f"       原话 {q}：{quotes[q]}")
            for r in i.ku_refs:
                print(f"       依据：{actors[owners[r]].name} 的 {r}")

    print("== L1 场景需求卡")
    for s in sessions:
        print(f"  {s.id}（{s.customer_id}）现象：{s.need.phenomenon}（原话「{s.need.phenomenon_quote}」）")
        for f in s.need.slots.values():
            print(f"    {labels[f.slot]}：{f.value}（原话「{f.quote}」，{f.turn_id}）")
    q = Question(id="q:cli", family="escalate_need", title="升级", object_id=sessions[0].id, owner_role="pm",
                 scored_by="human", discoverer="human", dedup_key=f"escalate_need:{sessions[0].id}", created_at=at)
    draft = draft_product_need(q, sessions, kb, pm, at)
    print(f"== L2 产品需求（{pm.name}）  方向：{draft.direction}")
    show(draft.product_lang)
    known = {}
    for s in sessions:
        for slot, value in s.need.known().items():
            known.setdefault(slot, value)
    req = Requirement(id="req:cli", question_id=q.id, session_ids=[s.id for s in sessions],
                      phenomenon=sessions[0].need.phenomenon, known_slots=known, direction=draft.direction,
                      product_lang=draft.product_lang, status="pm_confirmed", drafted_by=pm.id, created_at=at)
    chem = draft_chem_need(req, sessions, kb, rd, at)
    print(f"== L3 化学语言需求单（{rd.name}）")
    show(chem.chem_lang)
    print("  研发方向假设：")
    for h in chem.hypotheses:
        print(f"    - {h}")


if __name__ == "__main__":
    main()
