"""L1 链路；required_hints 是 WP-I 将替换的明确标注的追问替身。"""
from huayan.clock import get_clock
from huayan.contracts import (AskHint, AuditRecord, Evidence, LedgerEntry, Question,
                              Recommendation, Resolution, Turn)
from huayan.domain import match_candidates
from huayan.knowledge.disclosure import cap, render
from .answer import answer
from .extract import apply_extraction, validate_extraction


def required_hints(need, seeds, max_asks=2):
    phenomenon = next((p for p in seeds.phenomena if p.id == need.phenomenon), None)
    if not phenomenon:
        return []
    return [AskHint(session_id=need.session_id, slot=s.id, label=s.label, ask_text=s.ask_text,
                    p_need=0.8, scored_by="rule") for s in seeds.slots
            if s.id in phenomenon.required_slots and s.id not in need.slots and need.asked.get(s.id, 0) < 2][:max_asks]


def record_disclosure(card, deps):
    """同一查看者的同一版本审计去重；知识引用按会话去重。"""
    ids = [s.ku_id for s in card.sections]
    if not any(r.action == "disclose" and r.session_id == card.session_id
               and r.version == card.version and r.object_ids == ids for r in deps.audit.list(card.viewer)):
        deps.audit.append(AuditRecord(ts=get_clock().now(), actor=card.viewer, action="disclose",
            session_id=card.session_id, object_ids=ids, version=card.version))
    for section in card.sections:
        owner = deps.kb._units[section.ku_id].owner
        if not deps.ledger.has(owner, section.ku_id, card.session_id):
            deps.ledger.add(LedgerEntry(ts=get_clock().now(), owner=owner, ku_id=section.ku_id,
                ref=card.session_id, points=deps.config["points"]["cited"], reason="cited"))


def recommend(session, deps):
    if not session.need.phenomenon:
        return session
    products = {p.id: p for p in deps.kb.products()}
    candidates = match_candidates(session.need.phenomenon, session.need.known(), list(products.values()))
    decision = deps.jev.match(session.need, candidates, products)
    at = get_clock().now()
    if decision.choice == "none" or (not decision.confident and not session.hints):
        evidence = [Evidence(summary=f"{s.slot}: {s.value}", quote=s.quote)
                    for s in session.need.slots.values()]
        history = [q for q in deps.bus.list(status=None, family="escalate_need")
                   if q.refs.get("session_id") == session.id]
        previous = history[-1] if history else None
        # 同一轮升级仍合并；系统撤销后使用新对象、新问题 ID，兼容助手按 ID 派单。
        object_id = session.id if not history else f"{session.id}/need:{len(history) + 1}"
        if previous and (previous.status == "open" or
                         (previous.status == "dismissed" and previous.resolution.by != "system:l1")):
            object_id = previous.object_id  # 人工忽略继续由总线执行原抑制窗口。
        refs = {"session_id": session.id, "customer_id": session.customer_id}
        if previous and object_id != previous.object_id:
            refs["previous_question_id"] = previous.id
            evidence.append(Evidence(summary=f"最新需求替代旧升级 {previous.id}，请按当前条件重新核对并起草"))
        q = deps.bus.publish(Question(id="", family="escalate_need", title="没有合适产品，需产品经理处理",
            object_id=object_id, owner_role=deps.config["routing"]["escalate_need"],
            scored_by=decision.scored_by, discoverer="jev", created_at=at,
            dedup_key=f"escalate_need:{object_id}", refs=refs,
            evidence=evidence))
        same_escalation = (session.recommendation is not None and
                           session.recommendation.escalated_question_id == q.id)
        session.status = "escalated"
        session.recommendation = Recommendation(product_id=None, candidates=candidates, match=decision,
            disclose=None, version=None, escalated_question_id=q.id or None, at=at)
        if q.id and not same_escalation:
            deps.events.append("escalate", session.sales_id, {"question_id": q.id,
                "phenomenon": session.need.phenomenon, "known": session.need.known(),
                "customer_id": session.customer_id, "p_none": decision.probabilities["none"]}, session_id=session.id)
    elif decision.confident:
        viewer = deps.actors[session.sales_id]
        maximum = cap(viewer, session.customer_id, decision.choice, deps.grants)
        disclosure = deps.jev.disclose(session.need, decision.choice, maximum)
        card = render(decision.choice, disclosure.choice, viewer, deps.kb, session_id=session.id,
                      customer_id=session.customer_id, grants=deps.grants)
        session.recommendation = Recommendation(product_id=decision.choice, candidates=candidates, match=decision,
            disclose=disclosure, version=disclosure.choice, at=at)
        session.status = "recommended"
        deps.events.append("recommend", session.sales_id, {"product_id": decision.choice, "version": disclosure.choice,
            "p_choice": decision.probabilities[decision.choice], "candidate_ids": [c.product_id for c in candidates],
            "phenomenon": session.need.phenomenon, "known": session.need.known(),
            "customer_id": session.customer_id}, session_id=session.id)
        record_disclosure(card, deps)
        retire_escalation(session, deps, f"最新需求已匹配 {decision.choice}，撤销旧升级")
    return session


def retire_escalation(session, deps, note):
    """保留撤销快照；已由人处理的问题和需求单保持原有记录。"""
    for q in deps.bus.list(family="escalate_need"):
        if q.refs.get("session_id") != session.id:
            continue
        q.evidence = [Evidence(summary=f"最新 {s.slot}: {s.value}", quote=s.quote)
                      for s in session.need.slots.values()]
        q.evidence.append(Evidence(summary=note, quote=session.turns[-1].text))
        deps.bus.resolve(q.id, Resolution(action="dismiss", by="system:l1", note=note), get_clock().now())


def handle_turn(session, speaker, text, deps):
    n = len(session.turns) + 1
    turn = Turn(id=f"turn:{session.id}:{n}", session_id=session.id, n=n, speaker=speaker,
                text=text, ts=get_clock().now())
    session.turns.append(turn)
    deps.events.append("turn", session.customer_id if speaker == "customer" else session.sales_id,
                       {"turn_id": turn.id, "speaker": speaker, "text": text}, session_id=session.id)
    result = validate_extraction(deps.extractor.extract(session.turns, session.need), deps.seeds, session.turns)
    previous_conditions = session.need.phenomenon, session.need.known()
    session.need = apply_extraction(session.need, result, session.turns)
    conditions_changed = previous_conditions != (session.need.phenomenon, session.need.known())
    session.need.extracted_by = deps.extractor.name
    deps.events.append("extraction", session.sales_id, {"intent": result.intent, "phenomenon": result.phenomenon,
        "filled": session.need.known(), "extracted_by": deps.extractor.name,
        "conditions_changed": conditions_changed, "turn_id": turn.id}, session_id=session.id)
    if conditions_changed:
        retire_escalation(session, deps, "客户需求条件已变化，旧升级依据失效，重新评估")
        session.recommendation, session.status = None, "open"
    if result.intent == "need" or conditions_changed:
        session.hints = deps.ask_hints(session.need)
        deps.events.append("ask_hint", session.sales_id, {"slots": [h.slot for h in session.hints],
            "p": {h.slot: h.p_need for h in session.hints}, "model": "required_stub"}, session_id=session.id)
        if not session.hints:
            recommend(session, deps)
        elif session.status == "recommended":
            session.recommendation, session.status = None, "open"
    if result.intent in ("product_question", "mechanism_request"):
        session.replies.append(answer(session, deps))
    return session
