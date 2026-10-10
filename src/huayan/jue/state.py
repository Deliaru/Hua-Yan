"""契约 5.1 / 5.2：把会话与事件日志变成「对象 × 属性」。只读 NeedState、事件日志、种子与已发布产品。"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from huayan.contracts import JueObject, JueState, NeedState, Product, Seeds
from huayan.domain import match_candidates
from huayan.events import EventLog

WINDOWS = {"theme_days": 7, "knowledge_days": 7, "actor_hours": 48}   # 与 config/app.yaml 的 windows 一致
_PRODUCT_KU = {"sheet", "usage", "mechanism", "formula"}


def realtime_state(need: NeedState, seeds: Seeds, products: list[Product], at: datetime) -> JueState:
    ph = need.phenomenon
    phen = next((p for p in seeds.phenomena if p.id == ph), None)
    known = need.known()
    ids = lambda k: tuple(c.product_id for c in match_candidates(ph, k, products))
    objects = {}
    for slot in seeds.slots:
        fill = need.slots.get(slot.id)
        filled = fill is not None and fill.status == "filled"
        splits = 0 if filled or ph is None else len({ids({**known, slot.id: v}) for v in slot.values})
        prior = phen.slot_priors.get(slot.id, {}) if phen else {}
        oid = f"slot:{need.session_id}/{slot.id}"
        objects[oid] = JueObject(object_id=oid, object_type="slot", attrs={
            "slot": slot.id, "phenomenon": ph or "unknown", "filled": filled,
            "unknown": fill is not None and fill.status == "unknown",
            "confidence": fill.confidence if filled else 0.0, "asked": need.asked.get(slot.id, 0),
            "required": phen is not None and slot.id in phen.required_slots, "turn": need.turn_count,
            "n_filled": len(known), "n_candidates": len(ids(known)) if ph else 0, "splits": splits,
            "prior_top": max(prior.values(), default=0.0), "chem_savvy": need.profile.chem_savvy})
    return JueState(at=at, mode="realtime", objects=objects)


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
