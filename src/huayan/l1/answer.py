import json
from pathlib import Path

from huayan.clock import get_clock
from huayan.contracts import AssistantReply, AuditRecord, LLMRequest, Message, Tier


def answer(session, deps, *, check_grounding=False):
    turn = session.turns[-1]
    actor = deps.actors[session.sales_id]
    hits = deps.kb.search(turn.text, actor, phenomenon=session.need.phenomenon, session_id=session.id)
    blocked = bool(deps.kb.search_blocked(turn.text, actor, phenomenon=session.need.phenomenon))
    if blocked:
        text = "这部分属于研发保密内容，可以为客户申请解密。配方不对外开放。"
        deps.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="deny",
            object_ids=[turn.id], session_id=session.id, reason="提问涉及高层级知识"))
    elif not hits:
        text = "现有可读知识没有足够依据，请联系产品经理。"
    elif deps.config["gateway_mock"]:
        text = "\n".join(h.ku.text for h in hits)
    else:
        prompt = (Path(__file__).resolve().parents[3] / "prompts/l1_answer.md").read_text(encoding="utf-8")
        response = deps.gateway.complete(LLMRequest(tier=Tier.FAST, caller="agent:l1_answer", temperature=0,
            messages=[Message(role="system", content=prompt), Message(role="user", content=json.dumps(
                {"question": turn.text, "hits": [{"title": h.ku.title, "text": h.ku.text} for h in hits]},
                ensure_ascii=False))]))
        text = response.content or "没有生成可用回答。"
    grounding = deps.jev.grounding(text, hits) if check_grounding and hits and not blocked else None
    if grounding and grounding.choice != "grounded":
        text = "回答依据不足，请联系产品经理。"
    return AssistantReply(turn_id=turn.id, text=text, ku_ids=[] if blocked else [h.ku.id for h in hits],
                          blocked=blocked, grounding=grounding)
