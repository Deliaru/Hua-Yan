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
        selected = next(c for c in candidates if c.product_id == decision.choice)
        deps.events.append("recommend", _acting(session), {"product_id": decision.choice, "version": disclosure.choice,
            "p_choice": decision.probabilities[decision.choice], "candidate_ids": [c.product_id for c in candidates],
            "phenomenon": session.need.phenomenon, "known": session.need.known(),
            "customer_id": session.customer_id, "status": selected.status,
            "capability_id": selected.capability_id}, session_id=session.id)
        record_disclosure(card, deps)
        deps._use_capability(selected.capability_id, session.id, _acting(session))
    return session


def recommendation_note(session, deps):
    rec = session.recommendation
    candidate = next((c for c in rec.candidates if c.product_id == rec.product_id), None)
    if candidate is None or candidate.status == "confirmed":
        return ""
    product = next(p for p in deps.kb.view(deps.actors[_acting(session)]).products if p.id == rec.product_id)
    known, unknown = session.need.known(), {}
    for situation in product.situations:
        if situation.phenomenon != session.need.phenomenon or any(
                value not in situation.conditions[slot] for slot, value in known.items() if slot in situation.conditions):
            continue
        for slot, values in situation.conditions.items():
            if slot not in known:
                unknown.setdefault(slot, []).extend(v for v in values if v not in unknown.get(slot, []))
    labels = {s.id: s.label for s in deps.seeds.slots}
    return "可能适用：" + "；".join(f"{labels[slot]}为{'、'.join(values)}，请确认" for slot, values in unknown.items())


def ask_customer(session, hint, deps):
    """客户自助时没有业务员替觉问：化言把第一条提示的问法说给客户，写进对话，一次只问一个。"""
    n = len(session.turns) + 1
    session.turns.append(Turn(id=f"turn:{session.id}:{n}", session_id=session.id, n=n, speaker="assistant",
                              text=hint.ask_text, ts=get_clock().now()))
    session.need.asked[hint.slot] = session.need.asked.get(hint.slot, 0) + 1
    deps.events.append("turn", "system", {"turn_id": session.turns[-1].id, "speaker": "assistant",
                                          "text": hint.ask_text}, session_id=session.id)


def handle_turn(session, speaker, text, deps, answering=False, asking=()):
    """回问及已签字升级的会话只抽取和回答；需求单生命周期由门面处理。asking：客户页上正显示、对话里没有的回问槽位。"""
    n = len(session.turns) + 1
    turn = Turn(id=f"turn:{session.id}:{n}", session_id=session.id, n=n, speaker=speaker,
                text=text, ts=get_clock().now())
    session.turns.append(turn)
    deps.events.append("turn", session.customer_id if speaker == "customer" else session.sales_id,
                       {"turn_id": turn.id, "speaker": speaker, "text": text}, session_id=session.id)
    rec_id = session.recommendation.product_id if session.recommendation else None
    view = [{"id": p.id, "name": p.name, "recommended": p.id == rec_id}
            for p in deps.kb.view(deps.actors[_acting(session)]).products]
    # ⑰′：这句话在问什么、指到哪些产品，只由抽取理解一次；下游只读这两个字段
    result = validate_extraction(deps.extractor.extract(session.turns, session.need, view, asking=asking if speaker == "customer" else ()), deps.seeds, session.turns,
                                 {p["id"] for p in view})
    previous_conditions = session.need.phenomenon, session.need.known()
    after_rec = bool(rec_id)
    session.need = apply_extraction(session.need, result, session.turns)
    conditions_changed = previous_conditions != (session.need.phenomenon, session.need.known())
    session.need.extracted_by = deps.extractor.name
    deps.events.append("extraction", _acting(session), {"intent": result.intent, "phenomenon": result.phenomenon,
        "filled": session.need.known(), "extracted_by": deps.extractor.name,
        "conditions_changed": conditions_changed, "turn_id": turn.id, "speaker": speaker,
        "customer_id": session.customer_id, "after_rec": after_rec, "products": result.product_refs}, session_id=session.id)
    matching = not answering and session.status not in ("escalated", "closed")
    if conditions_changed and matching:
        session.recommendation, session.status = None, "open"
    # 已有推荐在需求条件未变时继续有效，普通发言不能用 L1 匹配覆盖研发审定的复用结果。
    if (conditions_changed or (result.intent == "need" and session.status != "recommended")) and matching:
        session.hints = deps.ask_hints(session.need)
        for capability in deps.kb.ask_capabilities(deps.actors[_acting(session)], session.need.phenomenon,
                                                   {h.slot for h in session.hints}):
            deps._use_capability(capability.id, session.id, _acting(session))
        deps.events.append("ask_hint", _acting(session), {"slots": [h.slot for h in session.hints],
            "p": {h.slot: h.p_need for h in session.hints}, "model": deps.jue_realtime.name}, session_id=session.id)
        if not session.hints:
            recommend(session, deps)
        elif session.status == "recommended":
            session.recommendation, session.status = None, "open"
        if session.hints and session.sales_id is None:
            ask_customer(session, session.hints[0], deps)
    if result.intent in ("product_question", "cause_question", "mechanism_request"):
        session.replies.append(answer(session, deps, result.product_refs))
    return session
