"""契约 ⑨ / JUE_K_TRAINING 第 11 节：Jue-K 定时三类的样本。不跑链路，按业务周剧本与需求卡真值直接合成
觉定时状态依赖的事件（payload 按契约 ⑧），每 2 个业务小时构建一次定时状态，按注入窗口打标签。"""
import random
from datetime import datetime, time, timedelta

from huayan.contracts import Injection, NeedCard, Product, QuestionModel, Seeds, WeekItem
from huayan.domain import match_candidates
from huayan.events import EventLog
from huayan.jue.state import collect_scheduled

TICK_HOURS = (11, 13, 15, 17)          # 每个业务日 9:00 开工后每 2 小时扫描一次
_MECH_WORDS = ("配方", "原理", "成分", "原料", "结构", "表面活性剂")


def synth_events(items: list[WeekItem], cards: list[NeedCard], seeds: Seeds, products: list[Product],
                 rng: random.Random) -> EventLog:
    by_card = {c.id: c for c in cards}
    events = EventLog()
    for it in items:
        if it.kind == "session":
            c = by_card[it.card_id]
            known = {s: v for s, v in c.slots.items() if s not in c.unknown_slots}
            sid = f"sess:{c.id}"
            if c.truth_product is not None:      # 全部真值下按 correct_product 的同一规则推荐
                ids = [x.product_id for x in match_candidates(c.phenomenon, known, products)]
                events.append("recommend", it.actor, {
                    "product_id": c.truth_product, "version": "product_usage", "p_choice": rng.uniform(0.6, 0.95),
                    "candidate_ids": ids, "phenomenon": c.phenomenon, "known": known, "customer_id": c.customer_id},
                    session_id=sid, ts=it.at)
            else:
                events.append("escalate", it.actor, {
                    "question_id": f"q:{sid}", "phenomenon": c.phenomenon, "known": known,
                    "customer_id": c.customer_id, "p_none": rng.uniform(0.6, 0.9)}, session_id=sid, ts=it.at)
        elif it.kind == "trial":
            t = it.trial
            events.append("trial", it.actor, {"trial_id": t.id, "product_id": t.product_id, "conditions": t.conditions,
                                              "result": t.result, "cause": t.cause}, ts=it.at)
        else:   # 问机理 / 配方的被拦截：该产品的机理与配方两条 L3 知识
            pids = [p.id for p in products if p.id in it.text]
            blocked = any(w in it.text for w in _MECH_WORDS)
            events.append("retrieve", it.actor, {
                "query": it.text, "intent": "mechanism_request" if blocked else "product_question", "actor_level": 1,
                "hit_ku_ids": [f"ku:sheet:{p}" for p in pids] + ([] if blocked else [f"ku:usage:{p}" for p in pids]),
                "n_blocked": 2 * len(pids) if blocked else 0,
                "blocked_product_ids": [p for p in pids for _ in range(2)] if blocked else []}, ts=it.at)
    return events


def window_label(family: str, object_id: str, at: datetime, injections: list[Injection]) -> int:
    """落在某条非困难负样本注入的 [earliest, latest] 内、family 与 object_id 一致为 1。"""
    return int(any(not i.hard_negative and i.family == family and i.object_id == object_id
                   and i.earliest <= at <= i.latest for i in injections))


def week_rows(items: list[WeekItem], cards: list[NeedCard], injections: list[Injection], seeds: Seeds,
              products: list[Product], model: QuestionModel, start: datetime, days: int, source_id: str,
              rng: random.Random) -> list[dict]:
    events = synth_events(items, cards, seeds, products, rng)
    rows = []
    for d in range(days):
        for hour in TICK_HOURS:
            at = datetime.combine(start.date() + timedelta(days=d), time(hour), tzinfo=start.tzinfo)
            state, _ = collect_scheduled(events, at, seeds, products)
            for dec in model.propose(state).decisions:
                if dec.precondition_passed:
                    obj = state.objects[dec.object_id]
                    rows.append({"family": dec.family, "object_type": obj.object_type, "object_id": dec.object_id,
                                 "at": at.isoformat(), "source_id": source_id,
                                 "label": window_label(dec.family, dec.object_id, at, injections), **obj.attrs})
    return rows
