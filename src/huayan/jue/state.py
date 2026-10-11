"""契约 5.1 / 5.2：把会话、需求单与事件日志变成「对象 × 属性」。只读 NeedState、需求单、事件日志、种子与知识库。"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from huayan.contracts import (Actor, JueObject, JueState, NeedState, Phenomenon, Product, Requirement,
                              Seeds, Session, SlotDef, Trial)
from huayan.domain import match_candidates
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
    """会话快照应对应 at；事件只取该时刻之前的本会话记录，不由匹配结果推断已升级。"""
    relevant = [e for e in events.query(["match", "decrypt_request"], until=at) if e.session_id == sess.id]
    matches = sorted((e for e in relevant if e.kind == "match"), key=lambda e: e.ts)
    match = matches[-1].payload if matches else None
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
        "recommended": sess.status == "recommended", "escalated": sess.status == "escalated",
        "chem_savvy": need.profile.chem_savvy, "asked_mechanism": need.profile.asked_mechanism,
        "decrypt_requested": any(e.kind == "decrypt_request" for e in relevant),
    })
    return JueState(at=at, mode="realtime", objects={oid: obj})


def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime,
                      events: EventLog) -> JueState:
    """需求单与知识库快照应对应 at；活动单始终产出需求单对象，起草中另产出槽位对象。"""
    if req.status in {"released", "rejected", "reused", "merged"}:
        return JueState(at=at, mode="realtime", objects={})
    layer = {"draft": 2, "rd_accepted": 3}.get(req.status, 0)
    need = need.model_copy(update={"phenomenon": req.phenomenon})
    objects = _slot_objects(req.id, req.known_slots, need, seeds, kb.products(), layer, kb) if layer else {}
    history = sorted(events.query(until=at), key=lambda e: e.ts)
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
        "n_edited_uncovered": _edited_uncovered(req, seeds, kb, at),
        "n_contributed": len({e.payload["ku_id"] for e in own if e.kind == "knowledge_contributed"}),
        **_trial_attrs(req, kb, own, at),
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


def _edited_uncovered(req: Requirement, seeds: Seeds, kb: KnowledgeBase, at: datetime) -> int:
    """只用 L3 译文覆盖研发修改；旧译文前后新增的约束仍需沉淀。"""
    terms = sorted(((u.text.split(" → ", 1)[1], u.title) for u in kb.list(_INTERNAL, kinds=["translation"])
                    if u.level == 3 and u.created_at <= at), key=lambda t: len(t[0]), reverse=True)
    rd_ids = {a.id for a in seeds.actors if a.role == "rd"}
    uncovered = 0
    for item in req.chem_lang:
        if item.edited_by not in rd_ids:
            continue
        text = item.text
        # 只移除与已知 L3 知识完全一致的骨架片段，保留片段前后及引号内的人为修改。
        for term, title in terms:
            text = text.replace(f"『{title}』→ {term}", "")
        for term, _ in terms:
            text = text.replace(term, "")
        uncovered += bool(text.strip(" \t\r\n，。；、：:！？!?/"))
    return uncovered


def _trial_attrs(req: Requirement, kb: KnowledgeBase, own: list, at: datetime) -> dict:
    """试样知识保留 Trial.requirement_id；同产品的其他需求单不混入本单。"""
    trials = [Trial.model_validate_json(u.text) for u in kb.list(_INTERNAL, kinds=["trial"]) if u.created_at <= at]
    trials = sorted((t for t in trials if t.requirement_id == req.id and t.at <= at), key=lambda t: t.at)
    passed = next((t for t in reversed(trials) if t.result == "pass"), None)
    evaluation = next((e.payload["result"] for e in reversed(own)
                       if e.kind == "market_eval" and passed is not None and e.payload["trial_id"] == passed.id), "none")
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
        oid = f"slot:{owner}/{slot.id}"
        objects[oid] = JueObject(object_id=oid, object_type="slot", attrs={
            "slot": slot.id, "phenomenon": ph or "unknown", "filled": filled,
            "unknown": not filled and fill is not None and fill.status == "unknown",
            "confidence": (fill.confidence if fill is not None and fill.value == known[slot.id] else 1.0) if filled else 0.0,
            "asked": need.asked.get(slot.id, 0), "required": phen is not None and slot.id in phen.required_slots,
            "turn": need.turn_count, "n_filled": len(known), "n_candidates": len(ids(known)) if ph else 0,
            "splits": splits, "prior_top": max(prior.values(), default=0.0), "chem_savvy": need.profile.chem_savvy,
            "layer": layer, "trans_splits": trans})
    return objects


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
                      windows: dict | None = None) -> tuple[JueState, dict[str, dict[str, list[str]]]]:
    """返回状态，以及每个对象的引用（event_ids、session_ids），供发布层写证据。"""
    w = {**WINDOWS, **(windows or {})}
    objects, refs = {}, {}
    for obj, ref in [*_themes(events, at, seeds, at - timedelta(days=w["theme_days"])),
                     *_knowledge(events, at, products, at - timedelta(days=w["knowledge_days"])),
                     *_actors(events, at, at - timedelta(hours=w["actor_hours"]))]:
        objects[obj.object_id], refs[obj.object_id] = obj, ref
    return JueState(at=at, mode="scheduled", objects=objects), refs


def _themes(events, at, seeds, since):
    # 立项（处置或确认需求单）与发布之前的升级视为已处理；立项后未发布即 open_project
    req_theme, handled, released = {}, {}, set()
    for e in events.query(["question_resolved", "requirement_confirmed", "product_released"], until=at):
        p = e.payload
        if e.kind == "requirement_confirmed":
            req_theme[p["requirement_id"]] = key = theme_id(p["phenomenon"], p["known"], seeds)
        elif e.kind == "product_released":
            key = req_theme.get(p["requirement_id"])
        elif p["family"] == "opportunity" and p["action"] in ("approve_project", "draft_requirement"):
            key = p["object_id"]
        else:
            continue
        handled[key] = e.ts
        (released.add if e.kind == "product_released" else released.discard)(key)
    groups = defaultdict(list)
    for e in events.query(["escalate", "recommend"], since=since, until=at):
        key = theme_id(e.payload["phenomenon"], e.payload["known"], seeds)
        if e.kind == "recommend" or e.ts > handled.get(key, since):
            groups[key].append(e)
    for key, evs in groups.items():
        esc = [e for e in evs if e.kind == "escalate"]
        yield JueObject(object_id=key, object_type="theme", attrs={
            "phenomenon": evs[0].payload["phenomenon"], "n_escalations": len(esc),
            "n_customers": len({e.payload["customer_id"] for e in esc}),
            "n_matched": len(evs) - len(esc), "days_active": len({e.ts.date() for e in evs}),
            "open_project": key in handled and key not in released,
            "mean_p_none": sum(e.payload["p_none"] for e in esc) / len(esc) if esc else 0.0,
        }), {"event_ids": [e.id for e in esc], "session_ids": sorted({e.session_id for e in esc if e.session_id})}


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
