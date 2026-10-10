"""L1 链路；required_hints 是 WP-I 将替换的明确标注的追问替身。"""
from huayan.clock import get_clock
from huayan.contracts import (AskHint, AuditRecord, Evidence, LedgerEntry, Question,
                              Recommendation, Turn)
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


def recommend(session, deps):
    if session.status == "escalated" or not session.need.phenomenon:
        return session
    products = {p.id: p for p in deps.kb.products()}
    candidates = match_candidates(session.need.phenomenon, session.need.known(), list(products.values()))
    decision = deps.jev.match(session.need, candidates, products)
    at = get_clock().now()
    if decision.choice == "none" or (not decision.confident and not session.hints):
        q = deps.bus.publish(Question(id="", family="escalate_need", title="没有合适产品，需产品经理处理",
            object_id=session.id, owner_role=deps.config["routing"]["escalate_need"],
            scored_by=decision.scored_by, discoverer="jev", created_at=at,
            dedup_key=f"escalate_need:{session.id}", refs={"session_id": session.id, "customer_id": session.customer_id},
            evidence=[Evidence(summary=f"{s.slot}: {s.value}", quote=s.quote) for s in session.need.slots.values()]))
        session.status = "escalated"
        session.recommendation = Recommendation(product_id=None, candidates=candidates, match=decision,
            disclose=None, version=None, escalated_question_id=q.id, at=at)
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
        deps.audit.append(AuditRecord(ts=at, actor=viewer.id, action="disclose", session_id=session.id,
            object_ids=[s.ku_id for s in card.sections], version=card.version))
        for section in card.sections:
            owner = products[decision.choice].owner
            if not deps.ledger.has(owner, section.ku_id, session.id):
                deps.ledger.add(LedgerEntry(ts=at, owner=owner, ku_id=section.ku_id, ref=session.id,
                    points=deps.config["points"]["cited"], reason="cited"))
    return session


def handle_turn(session, speaker, text, deps):
    n = len(session.turns) + 1
    turn = Turn(id=f"turn:{session.id}:{n}", session_id=session.id, n=n, speaker=speaker,
                text=text, ts=get_clock().now())
    session.turns.append(turn)
    deps.events.append("turn", session.customer_id if speaker == "customer" else session.sales_id,
                       {"turn_id": turn.id, "speaker": speaker, "text": text}, session_id=session.id)
    result = validate_extraction(deps.extractor.extract(session.turns, session.need), deps.seeds, session.turns)
    session.need = apply_extraction(session.need, result, session.turns)
    session.need.extracted_by = deps.extractor.name
    deps.events.append("extraction", session.sales_id, {"intent": result.intent, "phenomenon": result.phenomenon,
        "filled": session.need.known(), "extracted_by": deps.extractor.name}, session_id=session.id)
    if result.intent in ("product_question", "mechanism_request"):
        session.replies.append(answer(session, deps))
    elif result.intent == "need":
        session.hints = deps.ask_hints(session.need)
        deps.events.append("ask_hint", session.sales_id, {"slots": [h.slot for h in session.hints],
            "p": {h.slot: h.p_need for h in session.hints}, "model": "required_stub"}, session_id=session.id)
        if not session.hints:
            recommend(session, deps)
        elif session.status == "recommended":
            session.recommendation, session.status = None, "open"
    return session
