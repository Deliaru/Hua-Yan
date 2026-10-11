"""契约 5.1 / 5.2：把会话、需求单与事件日志变成「对象 × 属性」。只读 NeedState、需求单、事件日志、种子与知识库。"""
from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from huayan.contracts import (Actor, JueObject, JueState, NeedState, Phenomenon, Product, Requirement,
                              Seeds, Session, SlotDef, Trial)
from huayan.domain import correct_product, match_candidates
from huayan.escalation.translate import leak_hits, match_translations
from huayan.events import EventLog

if TYPE_CHECKING:
    from huayan.knowledge import KnowledgeBase

WINDOWS = {"theme_days": 7, "knowledge_days": 7, "actor_hours": 48}   # 与 config/app.yaml 的 windows 一致
_PRODUCT_KU = {"sheet", "usage", "mechanism", "formula"}
_INTERNAL = Actor(id="system:jue", role="rd", name="觉（内部身份，只用于属性计数）")


def realtime_state(need: NeedState, seeds: Seeds, products: list[Product], at: datetime) -> JueState:
    return JueState(at=at, mode="realtime", objects=_slot_objects(need.session_id, need.known(), need, seeds, products, 1))


def session_state(sess: Session, events: EventLog, at: datetime) -> JueState:
    """p_none、p_top、n_candidates 取本会话最近一次 match 事件。
    escalated 取 escalate 事件（业务员签字升级是历史事实）：现成产品被采用后会话变为 recommended，不能因此再次到点升级。"""
    relevant = [e for e in events.query(["match", "decrypt_request", "escalate"]) if e.session_id == sess.id]
    match = next((e.payload for e in reversed(relevant) if e.kind == "match"), None)
    p_none = match["p_none"] if match is not None else 0.0
    p_top = max(match["p_choice"].values(), default=0.0) if match is not None else 0.0
    need = sess.need
    oid = f"session:{sess.id}"
    obj = JueObject(object_id=oid, object_type="session", attrs={
        "phenomenon": need.phenomenon or "unknown", "phenomenon_known": need.phenomenon is not None,
        "turn": need.turn_count, "n_filled": len(need.known()),
        "n_open_asks": len(sess.hints),  # hints 已由 select_asks 按阈值筛选
        "matched": match is not None, "p_none": p_none, "p_top": p_top,
        "n_candidates": len(match["candidate_ids"]) if match is not None else 0,
        "top_is_none": match is not None and p_none >= p_top,
        "recommended": sess.status == "recommended", "escalated": any(e.kind == "escalate" for e in relevant),
        "chem_savvy": need.profile.chem_savvy, "asked_mechanism": need.profile.asked_mechanism,
        "decrypt_requested": any(e.kind == "decrypt_request" for e in relevant),
    })
    return JueState(at=at, mode="realtime", objects={oid: obj})


def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime,
                      events: EventLog) -> JueState:
    """活动单总是产出需求单对象，起草中（L2 / L3）另产出槽位对象。"""
    if req.status in {"released", "rejected", "reused", "merged"}:
        return JueState(at=at, mode="realtime", objects={})
    layer = {"draft": 2, "rd_accepted": 3}.get(req.status, 0)
    need = need.model_copy(update={"phenomenon": req.phenomenon})
    objects = _slot_objects(req.id, req.known_slots, need, seeds, kb.products(), layer, kb) if layer else {}
    history = events.query()
    own = [e for e in history if e.payload.get("requirement_id") == req.id]
    items = {2: req.product_lang, 3: req.chem_lang}.get(layer, [])
    upstream = set(req.known_slots) if layer == 2 else {i.slot for i in req.product_lang if i.slot} if layer == 3 else set()
    open_backs = set()
    for e in history:
        p = e.payload
        if e.kind in {"question_published", "question_resolved"} and p["family"] == "ask_back" \
                and p["object_id"].startswith(f"slot:{req.id}/"):
            (open_backs.add if e.kind == "question_published" else open_backs.discard)(p["question_id"])
    # draft 内的退回只是重写草稿，不重置「停留在 draft」的时间。
    entered_kind = {"draft": "requirement_created", "rd_accepted": "requirement_accepted",
                    "rd_confirmed": "requirement_translated"}[req.status]
    entered_at = next((e.ts for e in reversed(own) if e.kind == entered_kind), req.created_at)
    declined = req.reuse is not None and bool(req.reuse.declined_reason)
    oid = f"requirement:{req.id}"
    objects[oid] = JueObject(object_id=oid, object_type="requirement", attrs={
        "status": req.status, "layer": layer,
        "n_product_items": len(req.product_lang), "n_chem_items": len(req.chem_lang),
        "n_returns": len(req.return_notes), "n_open_ask_back": len(open_backs),
        "n_unmapped_constraints": len(upstream - {i.slot for i in items if i.slot}),
        "n_unquoted_items": sum(not i.quote_refs for i in items),
        "n_edited_uncovered": _edited_uncovered(req, seeds, kb),
        "n_contributed": len({e.payload["ku_id"] for e in own if e.kind == "knowledge_contributed"}),
        **_trial_attrs(req, kb, own),
        "points_set": any(e.kind == "points_set" for e in own),
        "n_sealed": len(req.sealed), "sheet_ready": req.sheet is not None,
        "n_leak_hits": len({h.index for h in leak_hits(req.sheet.sheet + "\n" + req.sheet.usage,
                                                     req.sealed, req.hypotheses, kb)}) if req.sheet else 0,
        "released": False, "hours_in_status": (at - entered_at).total_seconds() / 3600,
        "reuse_checked": req.reuse is not None,
        "reuse_pending": req.reuse is not None and req.reuse.product_id is not None and not declined,
        "reuse_declined": declined,
    })
    return JueState(at=at, mode="realtime", objects=objects)


def _edited_uncovered(req: Requirement, seeds: Seeds, kb: KnowledgeBase) -> int:
    """研发改过的 L3 条目去掉已有 L3 骨架与译文后还剩内容，即未被覆盖；已从该条目沉淀过的算覆盖
    （研发 Agent 提炼的译文不必与修改逐字一致）。"""
    terms = sorted(((u.text.split(" → ", 1)[1], u.title) for u in kb.list(_INTERNAL, kinds=["translation"])
                    if u.level == 3), key=lambda t: len(t[0]), reverse=True)
    rd_ids = {a.id for a in seeds.actors if a.role == "rd"}
    uncovered = 0
    for item in req.chem_lang:
        if item.edited_by not in rd_ids or any(r.startswith(f"ku:translation:{req.id}:") for r in item.ku_refs):
            continue
        text = item.text
        for term, title in terms:
            text = text.replace(f"『{title}』→ {term}", "")
        for term, _ in terms:
            text = text.replace(term, "")
        uncovered += bool(text.strip(" \t\r\n，。；、：:！？!?/"))
    return uncovered


def _trial_attrs(req: Requirement, kb: KnowledgeBase, own: list) -> dict:
    """market_eval 取最近一次通过的试样上的客户评价（契约 5.2）。"""
    trials = [t for t in (Trial.model_validate_json(u.text) for u in kb.list(_INTERNAL, kinds=["trial"]))
              if t.requirement_id == req.id]
    passed = next((t for t in reversed(trials) if t.result == "pass"), None)
    evaluation = next((e.payload["result"] for e in reversed(own)
                       if e.kind == "market_eval" and passed and e.payload["trial_id"] == passed.id), "none")
    return {"n_trials": len(trials), "trial_passed": bool(trials) and trials[-1].result == "pass",
            "market_eval": evaluation}


def _slot_objects(owner: str, known: dict[str, str], need: NeedState, seeds: Seeds, products: list[Product],
                  layer: int, kb: KnowledgeBase | None = None) -> dict[str, JueObject]:
    ph = need.phenomenon
    phen = next((p for p in seeds.phenomena if p.id == ph), None)
    ids = lambda k: tuple(c.product_id for c in match_candidates(ph, k, products))
    objects = {}
    for slot in seeds.slots:
        fill = need.slots.get(slot.id)
        filled = slot.id in known
        splits = 0 if filled or ph is None else len({ids({**known, slot.id: v}) for v in slot.values})
        trans = 0 if filled or kb is None else _trans_splits(phen, known, slot, kb, layer)
        prior = phen.slot_priors.get(slot.id, {}) if phen else {}
        p_fix = 0.0 if filled or phen is None or layer != 1 else _p_fix(phen, known, slot.id, seeds, products)
        oid = f"slot:{owner}/{slot.id}"
        objects[oid] = JueObject(object_id=oid, object_type="slot", attrs={
            "slot": slot.id, "phenomenon": ph or "unknown", "filled": filled,
            "unknown": not filled and fill is not None and fill.status == "unknown",
            "confidence": (fill.confidence if fill is not None and fill.value == known[slot.id] else 1.0) if filled else 0.0,
            "asked": need.asked.get(slot.id, 0), "required": phen is not None and slot.id in phen.required_slots,
            "turn": need.turn_count, "n_filled": len(known), "n_candidates": len(ids(known)) if ph else 0,
            "splits": splits, "prior_top": max(prior.values(), default=0.0), "chem_savvy": need.profile.chem_savvy,
            "layer": layer, "trans_splits": trans, "p_fix": p_fix})
    return objects


def _p_fix(phen: Phenomenon, known: dict[str, str], slot_id: str, seeds: Seeds, products: list[Product]) -> float:
    """信息价值：按种子中该现象的槽位先验（没有则均匀），问到该槽位真值后推荐由错变对的概率。
    推荐只取决于解决该现象的产品在适用范围上限定过的槽位，只枚举其中未知的那些。"""
    relevant = {s for p in products if p.status == "released" and phen.id in p.solves for s in p.applicable}
    if slot_id not in relevant:
        return 0.0
    dists = []
    for sd in seeds.slots:
        if sd.id in relevant and sd.id not in known:
            prior = phen.slot_priors.get(sd.id) or {v: 1.0 for v in sd.values}
            total = sum(prior.values())
            dists.append([(sd.id, v, w / total) for v, w in prior.items()])
    now = correct_product(phen.id, known, products)
    p = 0.0
    for combo in itertools.product(*dists):
        truth = {**known, **{sid: v for sid, v, _ in combo}}
        target = correct_product(phen.id, truth, products)
        if now != target and correct_product(phen.id, {**known, slot_id: truth[slot_id]}, products) == target:
            p += math.prod(w for _, _, w in combo)
    return p


def _trans_splits(phen: Phenomenon, known: dict[str, str], slot: SlotDef, kb: KnowledgeBase, layer: int) -> int:
    """该槽位取各个值时，本层转化对照的命中集合有几种。"""
    return len({trans_hits(phen, {**known, slot.id: v}, kb, layer) for v in slot.values})


def trans_hits(phen: Phenomenon, known: dict[str, str], kb: KnowledgeBase, layer: int) -> frozenset[str]:
    """text = 现象名 + 已知槽位取值，以内部 L3 身份匹配后只留本层；只在觉内部计数，不外泄内容。回问标签也用它。"""
    text = " ".join([phen.label, *known.values()])
    return frozenset(h.ku.id for h in match_translations(text, kb, _INTERNAL, phen.id) if h.ku.level == layer)


def theme_id(phenomenon: str, known: dict[str, str], seeds: Seeds) -> str:
    required = next(p.required_slots for p in seeds.phenomena if p.id == phenomenon)
    return f"theme:{phenomenon}|" + ",".join(f"{s}={known[s]}" for s in sorted(required) if s in known)


def scheduled_state(events: EventLog, at: datetime, seeds: Seeds, products: list[Product],
                    windows: dict | None = None) -> JueState:
    return collect_scheduled(events, at, seeds, products, windows)[0]


def collect_scheduled(events: EventLog, at: datetime, seeds: Seeds, products: list[Product],
                      windows: dict | None = None) -> tuple[JueState, dict[str, dict]]:
    """返回状态，以及每个对象的引用（event_ids、session_ids；主题另有 requirement_ids、assigned_rd），供发布层写证据与解析签字人。"""
    w = {**WINDOWS, **(windows or {})}
    objects, refs = {}, {}
    for obj, ref in [*_themes(events, at, seeds, at - timedelta(days=w["theme_days"])),
                     *_knowledge(events, at, products, at - timedelta(days=w["knowledge_days"])),
                     *_actors(events, at, at - timedelta(hours=w["actor_hours"]))]:
        objects[obj.object_id], refs[obj.object_id] = obj, ref
    return JueState(at=at, mode="scheduled", objects=objects), refs


def _themes(events, at, seeds, since):
    # 立项、合并、发布不限窗口；复用状态取最后一次决定。
    history = events.query(["requirement_created", "escalate", "recommend", "reuse_proposed", "reuse_declined",
                            "reuse_adopted", "requirement_accepted", "requirements_merged", "product_released"], until=at)
    req_theme, req_rd, handled, reuse_closed, projects = {}, {}, {}, set(), set()
    for e in history:
        p = e.payload
        if e.kind == "requirement_created":
            req_rd[p["requirement_id"]] = p["assigned_rd"]
        elif e.kind == "escalate":
            req_theme[p["requirement_id"]] = theme_id(p["phenomenon"], p["known"], seeds)
        elif e.kind == "reuse_proposed":
            (reuse_closed.add if p["product_id"] is None else reuse_closed.discard)(p["requirement_id"])
        elif e.kind == "reuse_declined":
            reuse_closed.add(p["requirement_id"])
        elif e.kind == "reuse_adopted":
            reuse_closed.discard(p["requirement_id"])
        elif e.kind == "requirement_accepted":
            handled[req_theme[p["requirement_id"]]] = e.ts
            projects.add(p["requirement_id"])
        elif e.kind == "requirements_merged":
            handled[req_theme[p["target"]]] = e.ts
        elif e.kind == "product_released":
            projects.discard(p["requirement_id"])
            handled[req_theme[p["requirement_id"]]] = e.ts
    open_themes = {req_theme[rid] for rid in projects}
    groups, phenomena = defaultdict(list), {}
    for e in history:
        if e.kind not in {"escalate", "recommend"} or e.ts < since:
            continue
        key = theme_id(e.payload["phenomenon"], e.payload["known"], seeds)
        phenomena[key] = e.payload["phenomenon"]
        evs = groups[key]
        if e.kind == "recommend" or (e.payload["requirement_id"] in reuse_closed
                                      and (key not in handled or e.ts > handled[key])):
            evs.append(e)
    for key, evs in groups.items():
        esc = [e for e in evs if e.kind == "escalate"]
        yield JueObject(object_id=key, object_type="theme", attrs={
            "phenomenon": phenomena[key], "n_escalations": len(esc),
            "n_customers": len({e.payload["customer_id"] for e in esc}),
            "n_matched": len(evs) - len(esc), "days_active": len({e.ts.date() for e in evs}),
            "open_project": key in open_themes,
            "mean_p_none": sum(e.payload["p_none"] for e in esc) / len(esc) if esc else 0.0,
        }), {"event_ids": [e.id for e in esc], "session_ids": sorted({e.session_id for e in esc if e.session_id}),
             # 机会汇聚的候选单 = 计入 n_escalations 的单（C14）；签字研发取最早一张的研发
             "requirement_ids": [e.payload["requirement_id"] for e in esc],
             "assigned_rd": req_rd[esc[0].payload["requirement_id"]] if esc else None}


def _knowledge(events, at, products, since):
    by_id = {p.id: p for p in products}
    trials, recs = defaultdict(list), Counter()
    for e in events.query(["trial"], since=since, until=at):
        for slot, value in e.payload["conditions"].items():
            trials[(e.payload["product_id"], slot, value)].append(e)
    for e in events.query(["recommend"], since=since, until=at):
        for slot, value in e.payload["known"].items():
            recs[(e.payload["product_id"], slot, value)] += 1
    for (pid, slot, value), evs in trials.items():
        fails = [e for e in evs if e.payload["result"] == "fail"]
        product = by_id.get(pid)
        yield JueObject(object_id=f"knowledge:{pid}|{slot}={value}", object_type="knowledge", attrs={
            "product_id": pid, "slot": slot, "value": value,
            "claimed": product is not None and value in product.applicable.get(slot, []),
            "n_trials": len(evs), "n_fail": len(fails),
            "n_fail_product": sum(e.payload["cause"] == "product" for e in fails),
            "fail_ratio": len(fails) / len(evs), "n_recommended": recs[(pid, slot, value)],
        }), {"event_ids": [e.id for e in fails], "session_ids": []}


def _actors(events, at, since):
    frozen = {e.payload["actor_id"] for e in events.query(["access_frozen"], until=at)}
    groups = defaultdict(list)
    for e in events.query(["retrieve"], since=since, until=at):
        groups[e.actor].append(e)
    for actor, evs in groups.items():
        blocked = Counter(pid for e in evs for pid in e.payload["blocked_product_ids"])
        hit = {ku.split(":", 2)[2] for e in evs for ku in e.payload["hit_ku_ids"] if ku.split(":")[1] in _PRODUCT_KU}
        yield JueObject(object_id=f"actor:{actor}", object_type="actor", attrs={
            "role": actor.split(":")[0], "n_queries": len(evs),
            "n_mech_requests": sum(e.payload["intent"] == "mechanism_request" for e in evs),
            "n_blocked": sum(e.payload["n_blocked"] for e in evs),
            "blocked_top_share": max(blocked.values()) / sum(blocked.values()) if blocked else 0.0,
            "n_distinct_products": len(hit | set(blocked)), "frozen": actor in frozen,
        }), {"event_ids": [e.id for e in evs if e.payload["n_blocked"]], "session_ids": []}
