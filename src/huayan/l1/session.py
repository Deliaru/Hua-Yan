"""L1 链路：抽取 → 觉的追问提示 → Jev 匹配与推荐 → L1 回答；升级由门面签字执行。"""
from huayan.clock import get_clock
from huayan.contracts import AuditRecord, LedgerEntry, Recommendation, Turn
from huayan.domain import match_candidates
from huayan.knowledge.disclosure import cap, render
from .answer import answer
from .extract import apply_extraction, validate_extraction


def _acting(session):
    """v6：客户自助会话没有业务员时，事件记录与披露上限用客户身份。"""
    return session.sales_id or session.customer_id


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
    if not session.need.phenomenon or session.status in ("escalated", "closed"):
        return session
    products = {p.id: p for p in deps.kb.view(deps.actors[session.sales_id or session.customer_id]).products}
    candidates = match_candidates(session.need.phenomenon, session.need.known(), list(products.values()))
    decision = deps.jev.match(session.need, candidates, products)
    at = get_clock().now()
    deps.events.append("match", _acting(session), {
        "phenomenon": session.need.phenomenon, "known": session.need.known(),
        "customer_id": session.customer_id, "candidate_ids": [c.product_id for c in candidates],
        "p_choice": {c.product_id: decision.probabilities[c.product_id] for c in candidates},
        "p_none": decision.probabilities["none"], "scored_by": decision.scored_by,
    }, session_id=session.id, ts=at)
    # 匹配失败也须清除先前推荐；结果由 match 事件交给觉，不在此发布升级问题。
    session.recommendation, session.status = None, "open"
    if decision.confident and decision.choice != "none":
        viewer = deps.actors[_acting(session)]
        maximum = "product_usage" if deps.kb.is_frozen(viewer.id) else cap(
            viewer, session.customer_id, decision.choice, deps.grants)
        disclosure = deps.jev.disclose(session.need, decision.choice, maximum)
        card = render(decision.choice, disclosure.choice, viewer, deps.kb, session_id=session.id,
                      customer_id=session.customer_id, grants=deps.grants)
        session.recommendation = Recommendation(product_id=decision.choice, candidates=candidates, match=decision,
            disclose=disclosure, version=disclosure.choice, at=at)
        session.status = "recommended"
        deps.events.append("recommend", _acting(session), {"product_id": decision.choice, "version": disclosure.choice,
            "p_choice": decision.probabilities[decision.choice], "candidate_ids": [c.product_id for c in candidates],
            "phenomenon": session.need.phenomenon, "known": session.need.known(),
            "customer_id": session.customer_id}, session_id=session.id)
        record_disclosure(card, deps)
        cite_scope(session, decision.choice, deps)
    return session


def cite_scope(session, product_id, deps):
    """v6：产品因产品经理扩展的适用范围才命中时，按 cited 给扩展知识的归属人记分。"""
    unit = deps.kb._units.get(f"ku:translation:scope:{product_id}:{session.need.phenomenon}")
    if unit and not deps.ledger.has(unit.owner, unit.id, session.id):
        deps.ledger.add(LedgerEntry(ts=get_clock().now(), owner=unit.owner, ku_id=unit.id, ref=session.id,
            points=deps.config["points"]["cited"], reason="cited"))


def handle_turn(session, speaker, text, deps, answering=False):
    """回问及已签字升级的会话只抽取和回答；需求单生命周期由门面处理。"""
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
    deps.events.append("extraction", _acting(session), {"intent": result.intent, "phenomenon": result.phenomenon,
        "filled": session.need.known(), "extracted_by": deps.extractor.name,
        "conditions_changed": conditions_changed, "turn_id": turn.id}, session_id=session.id)
    matching = not answering and session.status not in ("escalated", "closed")
    if conditions_changed and matching:
        session.recommendation, session.status = None, "open"
    # 已有推荐在需求条件未变时继续有效，普通发言不能用 L1 匹配覆盖研发审定的复用结果。
    if (conditions_changed or (result.intent == "need" and session.status != "recommended")) and matching:
        session.hints = deps.ask_hints(session.need)
        deps.events.append("ask_hint", _acting(session), {"slots": [h.slot for h in session.hints],
            "p": {h.slot: h.p_need for h in session.hints}, "model": deps.jue_realtime.name}, session_id=session.id)
        if not session.hints:
            recommend(session, deps)
        elif session.status == "recommended":
            session.recommendation, session.status = None, "open"
    if result.intent in ("product_question", "mechanism_request"):
        session.replies.append(answer(session, deps))
    return session
