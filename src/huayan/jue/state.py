"""契约 5.1 / 5.2：把会话、需求单与事件日志变成「对象 × 属性」。只读 NeedState、需求单、事件日志、种子与知识库。"""
from __future__ import annotations

import itertools
import json
import math
import re
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
_PURCHASE = re.compile("报价|价格|采购|下单|送样")   # v6：商务诉求，纯规则


def realtime_state(need: NeedState, seeds: Seeds, products: list[Product], at: datetime) -> JueState:
    # 判断层：客户自助会话里代客户判断（L0），陪同会话里代业务员判断（L1）
    return JueState(at=at, mode="realtime", objects=_slot_objects(need.session_id, need.known(), need, seeds, products, 1,
                                                                  judge=0 if need.sales_id is None else 1))


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
        "self_serve": sess.origin == "customer", "sales_assigned": sess.sales_id is not None,
        "purchase_intent": any(t.speaker == "customer" and _PURCHASE.search(t.text) for t in sess.turns),
    })
    return JueState(at=at, mode="realtime", objects={oid: obj})


def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime,
                      events: EventLog) -> JueState:
    """活动单总是产出需求单对象，起草中（L2 / L3）另产出槽位对象。"""
    if req.status in {"released", "rejected", "reused", "merged"}:
        return JueState(at=at, mode="realtime", objects={})
    layer = {"draft": 2, "rd_accepted": 3}.get(req.status, 0)
    need = need.model_copy(update={"phenomenon": req.phenomenon})
    history = events.query()
    own = [e for e in history if e.payload.get("requirement_id") == req.id]
    missing, last_result = _missing(req, kb, own, history)
    objects = _slot_objects(req.id, req.known_slots, need, seeds, kb.products(), layer, kb, missing) if layer else {}
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
        "n_pm_edited_uncovered": _pm_edited_uncovered(req, seeds, kb),
        "n_contributed": len({e.payload["ku_id"] for e in own if e.kind == "knowledge_contributed"}),
        **_trial_attrs(req, kb, own), **_risk_attrs(req, need, seeds, kb),
        "n_missing": len(missing), "last_result": last_result,
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


def _pm_edited_uncovered(req: Requirement, seeds: Seeds, kb: KnowledgeBase) -> int:
    """v6：真人产品经理改过的 L2 条目，尚未从该条目沉淀过 L2 知识（ku:translation:<req>:l2:<i>）。"""
    pm_ids = {a.id for a in seeds.actors if a.role == "pm" and a.id != "pm:agent"}
    return sum(item.edited_by in pm_ids and f"ku:translation:{req.id}:l2:{i}" not in kb._units
               for i, item in enumerate(req.product_lang))


def _trial_attrs(req: Requirement, kb: KnowledgeBase, own: list) -> dict:
    """market_eval 取最近一次通过的试样上的客户评价（契约 5.2）。"""
    trials = [t for t in (Trial.model_validate_json(u.text) for u in kb.list(_INTERNAL, kinds=["trial"]))
              if t.requirement_id == req.id]
    passed = next((t for t in reversed(trials) if t.result == "pass"), None)
    evaluation = next((e.payload["result"] for e in reversed(own)
                       if e.kind == "market_eval" and passed and e.payload["trial_id"] == passed.id), "none")
    return {"n_trials": len(trials), "trial_passed": bool(trials) and trials[-1].result == "pass",
            "market_eval": evaluation}


def _risk_attrs(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase) -> dict:
    """v8 试样风险（契约 ⑯）：客户答不清楚、没问到的条件，已知条件取值，以及同产品、同现象的历史试样。"""
    phen = next(p for p in seeds.phenomena if p.id == req.phenomenon)
    unknown = {s for s, f in need.slots.items() if f.status == "unknown" and s not in req.known_slots}
    product = next((p for p in seeds.products if p.id == req.product_id), None)
    matched = match_candidates(req.phenomenon, req.known_slots, [product.model_copy(update={"status": "released"})]) if product else []
    solvers = {p.id for p in seeds.products if req.phenomenon in p.solves}
    trials = [t for t in (Trial.model_validate_json(u.text) for u in kb.list(_INTERNAL, kinds=["trial"]))
              if t.requirement_id != req.id]
    same = [t for t in trials if t.product_id == req.product_id
            and all(t.conditions.get(s) == v for s, v in req.known_slots.items() if s in t.conditions)]
    phen_trials = [t for t in trials if t.product_id in solvers]
    return {"n_unknown_required": len(unknown & set(phen.required_slots)),
            "n_unquoted_slots": sum(not (need.slots.get(s) and need.slots[s].quote) for s in req.known_slots),
            "match_possible": bool(matched) and matched[0].status == "possible",
            "hist_n_trials": len(same), "hist_fail_rate": sum(t.result == "fail" for t in same) / len(same) if same else 0.0,
            "hist_req_fail_rate": sum(t.cause == "requirement" for t in phen_trials) / len(phen_trials) if phen_trials else 0.0,
            **{f"unknown:{s.id}": int(s.id in unknown) for s in seeds.slots},
            **{f"missing:{s.id}": int(s.id not in req.known_slots and s.id not in unknown) for s in seeds.slots},
            **{f"value:{s}={v}": 1 for s, v in req.known_slots.items()}}


def _missing(req: Requirement, kb: KnowledgeBase, own: list, history: list) -> tuple[frozenset[str], str]:
    """最近一次试样失败（原因为需求条件缺失）、客户评价不通过或试样前回问（v8）所指向、此后还没回问答过的槽位。"""
    trials = {t.id: t for t in (Trial.model_validate_json(u.text) for u in kb.list(_INTERNAL, kinds=["trial"]))
              if t.requirement_id == req.id}
    failures = [(t.at, t.missing_slots, "试样失败") for t in trials.values() if t.result == "fail" and t.cause == "requirement"]
    failures += [(e.ts, trials[e.payload["trial_id"]].market_eval_missing, "客户评价不通过") for e in own
                 if e.kind == "market_eval" and e.payload["result"] == "fail"]
    failures += [(e.ts, e.payload["slots"], "试样前回问") for e in own if e.kind == "requirement_returned" and e.payload.get("slots")]
    if not failures:
        return frozenset(), "none"
    at, slots, label = max(failures, key=lambda f: f[0])
    answered = {e.payload["object_id"].rsplit("/", 1)[1] for e in history if e.kind == "question_resolved"
                and e.payload["family"] == "ask_back" and e.payload["action"] == "answered"
                and e.payload["object_id"].startswith(f"slot:{req.id}/") and e.ts >= at}
    return frozenset(slots) - answered, label


def _slot_objects(owner: str, known: dict[str, str], need: NeedState, seeds: Seeds, products: list[Product],
                  layer: int, kb: KnowledgeBase | None = None, failed=frozenset(), judge=None) -> dict[str, JueObject]:
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
            "layer": layer, "trans_splits": trans, "p_fix": p_fix, "failed_on": slot.id in failed,
            "judge_level": layer if judge is None else judge})
    return objects


def _p_fix(phen: Phenomenon, known: dict[str, str], slot_id: str, seeds: Seeds, products: list[Product]) -> float:
    """信息价值：按种子中该现象的槽位先验（没有则均匀），问到该槽位真值后推荐由错变对的概率。
    推荐只取决于解决该现象的产品在适用范围上限定过的槽位，只枚举其中未知的那些。"""
    relevant = {s for p in products if p.status == "released" and phen.id in p.solves for situation in p.situations if situation.phenomenon == phen.id for s in situation.conditions}
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
                      windows: dict | None = None, caps=(), units=None) -> tuple[JueState, dict[str, dict]]:
    """返回状态，以及每个对象的引用（event_ids、session_ids；主题另有 requirement_ids、assigned_rd），供发布层写证据与解析签字人。"""
    w = {**WINDOWS, **(windows or {})}
    objects, refs = {}, {}
    for obj, ref in [*_themes(events, at, seeds, at - timedelta(days=w["theme_days"])),
                     *_knowledge(events, at, products, caps, at - timedelta(days=w["knowledge_days"])),
                     *_stale(events, at, caps, seeds),
                     *_scope(events, at, caps),
                     *_qi(events, at, caps, units or {}),
                     *_actors(events, at, at - timedelta(hours=w["actor_hours"]))]:
        objects[obj.object_id], refs[obj.object_id] = obj, ref
    return JueState(at=at, mode="scheduled", objects=objects), refs


def _themes(events, at, seeds, since):
    # 立项、合并、发布不限窗口；复用状态取最后一次决定。
    history = events.query(["requirement_created", "escalate", "recommend", "reuse_proposed", "reuse_declined",
                            "reuse_adopted", "requirement_accepted", "requirements_merged", "product_released",
                            "project_declined"], until=at)
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
        elif e.kind in ("reuse_adopted", "project_declined"):     # v6：研发不立项的单不再是合并候选
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


def _knowledge(events, at, products, caps, since):
    # v8：说明书声称的只算第 0 天迁移进来的情境；运行中人签出的判断归 stale_capability
    signed = {c.id for c in caps if c.form == "applicable" and c.approved_by not in (None, "seed")}
    claimed = {p.id: [s.conditions for s in p.situations if s.capability_id not in signed] for p in products}
    trials, recs = defaultdict(list), Counter()
    for e in events.query(["trial"], since=since, until=at):
        for slot, value in e.payload["conditions"].items():
            trials[(e.payload["product_id"], slot, value)].append(e)
    for e in events.query(["recommend"], since=since, until=at):
        for slot, value in e.payload["known"].items():
            recs[(e.payload["product_id"], slot, value)] += 1
    for (pid, slot, value), evs in trials.items():
        fails = [e for e in evs if e.payload["result"] == "fail"]
        yield JueObject(object_id=f"knowledge:{pid}|{slot}={value}", object_type="knowledge", attrs={
            "product_id": pid, "slot": slot, "value": value,
            "claimed": any(value in c.get(slot, []) for c in claimed.get(pid, [])),
            "n_trials": len(evs), "n_fail": len(fails),
            "n_fail_product": sum(e.payload["cause"] == "product" for e in fails),
            "fail_ratio": len(fails) / len(evs), "n_recommended": recs[(pid, slot, value)],
        }), {"event_ids": [e.id for e in fails], "session_ids": []}


def _stale(events, at, caps, seeds):
    """v8 判断过时：运行中由人签出的生效适用能力，看授予之后的使用与结果。失败只计产品原因
    （判断本身错了），设备、操作、需求条件缺失的失败不计；客户评价不通过另计。"""
    history = events.query(["capability_used", "trial", "market_eval"], until=at)
    values = {s.id: s.values for s in seeds.slots}
    for cap in caps:
        if cap.form != "applicable" or cap.status != "active" or cap.approved_by in (None, "seed"):
            continue
        pid, scope = cap.payload["product_id"], cap.payload["conditions"]
        after = [e for e in history if e.ts >= cap.at]
        used = [e for e in after if e.kind == "capability_used" and e.payload["capability_id"] == cap.id]
        trials = [e for e in after if e.kind == "trial" and e.payload["product_id"] == pid
                  and all(v in scope[s] for s, v in e.payload["conditions"].items() if s in scope)]
        failed = {e.id for e in trials if e.payload["result"] == "fail" and e.payload["cause"] == "product"}
        ids = {e.payload["trial_id"] for e in trials}
        recent = [e for e in trials if e.ts >= at - timedelta(days=7)]
        early = [e for e in trials if e.ts < at - timedelta(days=7)]
        rate = lambda evs: sum(e.id in failed for e in evs) / len(evs) if evs else 0.0
        # 只看还能收窄的取值：范围里只剩一个取值的槽位，所有失败都落在它上面，不说明问题
        spots = Counter(f"{s}={v}" for e in trials if e.id in failed for s, v in e.payload["conditions"].items()
                        if len(scope.get(s, values[s])) > 1)
        yield JueObject(object_id=f"knowledge:stale:{cap.id}", object_type="knowledge", attrs={
            "product_id": pid, "slot": "phenomenon", "value": cap.payload["phenomenon"],
            "n_used": len(used), "n_outcomes": len(trials), "n_fail": len(failed), "fail_rate": rate(trials),
            "recent_fail_rate": rate(recent), "early_fail_rate": rate(early),
            "fail_concentration": max(spots.values()) / len(failed) if spots else 0.0,
            "days_since_grant": (at - cap.at).total_seconds() / 86400,
            "n_market_fail": sum(e.kind == "market_eval" and e.payload["result"] == "fail"
                                 and e.payload["trial_id"] in ids for e in after),
        }), {"signer": cap.granted_by, "capability_id": cap.id,
             "event_ids": [e.id for e in trials if e.id in failed],
             "session_ids": sorted({e.session_id for e in used if e.session_id}),
             # 界面收窄用：原条件、失败集中的取值（多到少）与这些槽位可选的取值
             "conditions": json.dumps(scope, ensure_ascii=False),
             "fail_values": [k for k, _ in spots.most_common()],
             "scope": json.dumps({s: scope.get(s, values[s]) for s in dict.fromkeys(
                 [*scope, *(k.split("=")[0] for k in spots)])}, ensure_ascii=False)}


def _scope(events, at, caps):
    for cap in caps:
        if cap.form != "applicable" or cap.status != "proposed":
            continue
        pid, ph = cap.payload["product_id"], cap.payload["phenomenon"]
        evs = [e for e in events.query(["project_declined", "reuse_adopted"], until=at)
               if e.payload.get("product_id") == pid and e.payload.get("phenomenon") == ph]
        yield JueObject(object_id=f"knowledge:cap:{cap.id}", object_type="knowledge", attrs={
            "product_id": pid, "slot": "phenomenon", "value": ph, "conditions": json.dumps(cap.payload["conditions"], ensure_ascii=False),
            "n_applicable": len(evs), "pending": True,
        }), {"capability_id": cap.id, "product_id": pid, "event_ids": [e.id for e in evs],
             "session_ids": sorted({sid for e in evs for sid in e.payload.get("session_ids", [])}),
             "requirement_ids": [e.payload["requirement_id"] for e in evs]}


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


def _qi(events, at, caps, units):
    """能力授予与依据复核：只读能力、结论的归属和业务事件，不读取资料、不调用工具。"""
    history = events.query(until=at)
    requirements = {e.payload["requirement_id"]: e.payload["phenomenon"] for e in history
                    if e.kind == "requirement_created"}
    accompanied = {e.session_id for e in history if e.session_id and e.actor.startswith("sales:")}
    req_level = {e.payload["requirement_id"]: min(1 if s in accompanied else 0 for s in e.payload["session_ids"])
                 for e in history if e.kind == "requirement_created"}
    # 试样失败（需求条件缺失）与客户评价不通过指向的条件：研发的判断，只作为授予追问的理由
    trial_misses = defaultdict(list)
    for unit in units.values():
        if unit.kind != "trial" or unit.status != "active":
            continue
        t = Trial.model_validate_json(unit.text)
        slots = (t.missing_slots if t.result == "fail" and t.cause == "requirement" else []) +             (t.market_eval_missing if t.market_eval == "fail" else [])
        for slot in slots if t.requirement_id in requirements else []:
            trial_misses[(requirements[t.requirement_id], slot)].append(req_level[t.requirement_id])
    backs, unanswerable = defaultdict(list), defaultdict(list)
    changed, requests = {}, {}
    for event in history:
        if event.kind == "retrieve":       # 命中却没有能力：按「结论 × 提问者层级」计数
            for ku_id in event.payload.get("unanswerable_ku_ids", []):
                unanswerable[(ku_id, event.payload["actor_level"])].append(event)
        if event.kind == "share_requested":
            requests[f"knowledge:share:{event.payload['ku_id']}|{event.actor}"] = event
        elif event.kind == "question_resolved" and event.payload["object_id"] in requests:
            requests.pop(event.payload["object_id"])      # 归属人已授予或拒绝，申请结束
        if event.kind == "question_published" and event.payload["family"] == "ask_back":
            rid, slot = event.payload["object_id"].removeprefix("slot:").rsplit("/", 1)
            backs[(requirements[rid], slot)].append(event)
        if event.kind == "evidence_changed":
            changed[event.payload["ku_id"]] = event
        elif event.kind in {"claim_confirmed", "claim_withdrawn"}:
            changed.pop(event.payload["ku_id"], None)
    for cap in caps:
        if cap.form not in {"ask", "applicable"} or cap.status != "active" or cap.audience == 0:
            continue
        ph = cap.payload["phenomenon"]
        evs = backs[(ph, cap.payload["slot"])] if cap.form == "ask" else [
            event for (phen, _), rows in backs.items() if phen == ph for event in rows]
        # 只授予真正缺这个条件的那一层：回问出自业务员陪同的会话为 L1，出自客户自助的会话为 L0，取最低的一层。
        missed = trial_misses[(ph, cap.payload["slot"])] if cap.form == "ask" else []
        back_level = min([1 if e.session_id in accompanied else 0 for e in evs] + missed, default=0)
        misses = {level: [e for ku_id in cap.based_on for e in unanswerable[(ku_id, level)]] for level in range(3)}
        for level in sorted({back_level} | {k for k, v in misses.items() if v}):
            granted = any(c.form == cap.form and c.payload == cap.payload and c.status == "active"
                          and c.audience in range(level + 1) for c in caps)
            asked = evs if level == back_level else []
            yield JueObject(object_id=f"knowledge:grant:{cap.id}|L{level}", object_type="knowledge", attrs={
                "product_id": cap.payload.get("product_id", ""), "slot": cap.payload.get("slot", "phenomenon"),
                "value": ph, "n_ask_back": len(asked), "n_unanswerable": len(misses[level]), "requested": False,
                "n_trial_missing": len(missed) if level == back_level else 0, "granted": granted,
            }), {"capability_id": cap.id, "product_id": cap.payload.get("product_id", ""),
                 "audience": str(level), "signer": cap.granted_by, "form": cap.form,
                 "based_on": cap.based_on, "event_ids": [e.id for e in asked + misses[level]]}
    # 命中却没有任何能力的结论：要授予的是一句可说的话（statement），由结论确认人起草措辞并签字
    with_caps = {ku_id for c in caps if c.status == "active" and c.form != "statement" for ku_id in c.based_on}
    for (ku_id, level), evs in unanswerable.items():
        if ku_id in with_caps or not (units[ku_id].confirmed_by or "").startswith("rd:"):
            continue       # 有能力的走上面的授予；只有研发确认的结论由研发授予一句话
        unit = units[ku_id]
        granted = any(c.form == "statement" and c.status == "active" and ku_id in c.based_on
                      and c.audience in range(level + 1) for c in caps)
        yield JueObject(object_id=f"knowledge:grant:{ku_id}|L{level}", object_type="knowledge", attrs={
            "product_id": unit.product_id or "", "slot": "statement", "value": ku_id,
            "n_ask_back": 0, "n_unanswerable": len(evs), "n_trial_missing": 0, "requested": False, "granted": granted,
        }), {"ku_id": ku_id, "product_id": unit.product_id or "", "audience": str(level),
             "signer": unit.confirmed_by, "form": "statement", "based_on": [ku_id],
             "session_ids": sorted({e.session_id for e in evs if e.session_id}),
             "retrieve_ids": [e.id for e in evs], "event_ids": [e.id for e in evs]}
    for object_id, event in requests.items():
        ku_id, requester = event.payload["ku_id"], event.actor
        granted = any(c.form == "share" and c.status == "active" and c.audience == requester
                      and c.payload["ku_id"] == ku_id for c in caps)
        touched = [e for e in history if e.kind == "requirement_translated" and e.actor == requester
                   and ku_id in e.payload["ku_refs"]]
        yield JueObject(object_id=object_id, object_type="knowledge", attrs={
            "product_id": event.payload["product_id"] or "", "slot": "share", "value": requester,
            "n_ask_back": 0, "n_unanswerable": 0, "n_trial_missing": 0, "requested": True, "granted": granted,
        }), {"ku_id": ku_id, "requester": requester, "product_id": event.payload["product_id"] or "",
             "signer": event.payload["owner"], "requirement_ids": [e.payload["requirement_id"] for e in touched],
             "event_ids": [event.id]}
    for ku_id, event in changed.items():
        if event.payload["signer"] is None:
            continue
        yield JueObject(object_id=f"knowledge:claim:{ku_id}", object_type="knowledge", attrs={
            "product_id": event.payload["product_id"] or "", "slot": "evidence", "value": ku_id,
            "evidence_changed": True,
        }), {"ku_id": ku_id, "product_id": event.payload["product_id"] or "",
             "signer": event.payload["signer"], "event_ids": [event.id]}
