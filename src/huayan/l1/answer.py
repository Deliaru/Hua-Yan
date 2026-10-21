import json
import re
from pathlib import Path

from huayan.clock import get_clock
from huayan.contracts import AssistantReply, AuditRecord, KnowledgeHit, LLMRequest, Message, Tier
from huayan.domain import consistent
from huayan.escalation.translate import leak_hits
from huayan.knowledge import PermissionDenied, level_of
from huayan.knowledge.disclosure import render_refs


def target_products(session, deps, products):
    """解析明确型号和最近的唯一话题；不确定时请客户澄清。"""
    boundary = next((e.payload["turn_id"] for e in reversed(deps.events.query(kinds=["extraction"]))
                     if e.session_id == session.id and e.payload.get("conditions_changed")), None)
    rec = session.recommendation
    recommended = [rec.product_id] if rec and rec.product_id else []
    for turn in reversed(session.turns):
        # 已知型号以知识库为准，不假设连字符、字母或数字的排列方式。
        ids = [pid for pid in products if re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(pid)}(?![A-Za-z0-9_-])", turn.text, re.IGNORECASE)]
        remainder = turn.text
        for pid in ids:
            remainder = re.sub(rf"(?<![A-Za-z0-9_-]){re.escape(pid)}(?![A-Za-z0-9_-])",
                               "", remainder, flags=re.IGNORECASE)
        # 未知的型号形态仅用于阻止回退，不能拿它推断已知产品。
        unknown = re.search(r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+", remainder)
        if ids or unknown:
            return ids if not unknown and (turn.id == session.turns[-1].id or len(ids) == 1) else []
        if any(word in turn.text for word in ("前者", "后者", "前一个", "后一个", "另一个")):
            return []
        if re.search(r"推荐(?:的)?(?:产品|型号|那个|这个)", turn.text):
            return recommended
        # 条件变更意味着新一轮匹配，不沿用更早的产品话题。
        if turn.id == boundary:
            break
    return recommended


def answer(session, deps, *, check_grounding=False):
    turn = session.turns[-1]
    actor = deps.actors[session.sales_id or session.customer_id]   # v6：自助会话按客户身份检索
    products = {p.id: p for p in deps.kb.view(deps.actors[session.sales_id or session.customer_id]).products}
    rec = session.recommendation
    targets = target_products(session, deps, products)
    query = turn.text + " " + " ".join(targets)
    # 先记完整检索事件；明确型号不受当前会话现象筛选，以免查别的产品时答错。
    # v8：检索用的是这句话，记在说这句话的人名下（客户问的不算业务员的）；权限仍按会话身份
    asker = session.customer_id if turn.speaker == "customer" else actor.id
    found = deps.kb.explore(query, actor, session_id=session.id, asked_by=asker,
                            phenomenon=None if targets else session.need.phenomenon)
    # 研发授予这一层的话（statement）：前台可以说这句话，看不到它依据的结论
    statements = [c for c in found.capabilities if c.form == "statement"]
    # 是否问机理只看抽取给出的意图；能看到什么由知识库按层级裁剪。有授予的话就用它回答。
    mechanism = session.need.last_intent == "mechanism_request"
    blocked = mechanism and not statements
    public_request = not mechanism or any(word in turn.text for word in ("怎么用", "用法", "用量", "说明书", "产品说明"))
    if targets and public_request:
        hits = [KnowledgeHit(ku=deps.kb.get(f"ku:{kind}:{pid}", actor), score=1.0)
                for pid in targets for kind in ("sheet", "usage")]
    else:
        # 没有明确指代或有效推荐时，不把其他型号的剂量当成当前建议。
        hits = []
    denial = ("这部分属于研发保密内容；你的高层级访问已被冻结，暂不能申请解密。" if deps.kb.is_frozen(actor.id)
              else "这部分属于研发保密内容，可以为客户申请解密。") + "配方不对外开放。" if targets \
        else "这部分需要专业人员解答。"
    if blocked:
        deps.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="deny",
            object_ids=[turn.id], session_id=session.id, reason="提问涉及高层级知识"))
    used = statements
    if not hits and not statements:
        text = denial if blocked else "请明确要查询的产品型号；目前没有足够依据提供用法。"
        if not blocked and session.status == "escalated":
            status = "已转产品经理处理。" if rec and rec.escalated_question_id else "请联系产品经理。"
            text = "当前条件没有适用的推荐产品，" + status + text
    elif deps.config["gateway_mock"]:
        text = render_refs("\n".join([h.ku.text for h in hits] + [f"[[{c.id}]]" for c in statements]),
                           level_of(actor), deps.kb)
    else:
        prompt = (Path(__file__).resolve().parents[3] / "prompts/l1_answer.md").read_text(encoding="utf-8")
        response = deps.gateway.complete(LLMRequest(tier=Tier.FAST, caller="agent:l1_answer", temperature=0,
            messages=[Message(role="system", content=prompt), Message(role="user", content=json.dumps(
                {"question": turn.text, "target_product_ids": targets,
                 "recommended_product_id": rec.product_id if rec else None,
                 "need": {"phenomenon": session.need.phenomenon, "known": session.need.known()},
                 "turns": [{"speaker": t.speaker, "text": t.text} for t in session.turns[-6:]],
                 "hits": [{"ku_id": h.ku.id, "title": h.ku.title, "text": h.ku.text} for h in hits],
                 "statements": [{"ref": c.id, "text": c.payload["text"]} for c in statements]},
                ensure_ascii=False))]))
        used = [c for c in statements if f"[[{c.id}]]" in (response.content or "")]
        # 专业内容只以 [[编号]] 写出，按收件层渲染并查泄密；任一不过就不发出
        try:
            text = render_refs(response.content or "没有生成可用回答。", level_of(actor), deps.kb)
            leaked = bool(leak_hits(text, [], [], deps.kb, audience=level_of(actor)))
        except PermissionDenied:
            leaked = True
        if leaked:
            deps.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="deny",
                object_ids=[turn.id], session_id=session.id, reason="回答含收件层不可见的内容"))
            text, used = "这部分需要专业人员解答。", []
    for c in used:      # 说出了授予的话 = 能力被使用，给确认人记分
        deps._use_capability(c.id, session.id, actor.id)
    if hits and blocked:
        text += "\n" + denial
    if any(not consistent(products[pid], session.need.known()) or
           (session.need.phenomenon and session.need.phenomenon not in products[pid].solves) for pid in targets):
        text += "\n以上仅为所问型号的公开资料，该产品不适用于当前已知条件，不作为本会话推荐。"
    grounding = deps.jev.grounding(text, hits) if check_grounding and hits and not blocked else None
    if grounding and grounding.choice != "grounded":
        text = "回答依据不足，请联系产品经理。"
    return AssistantReply(turn_id=turn.id, text=text, ku_ids=[h.ku.id for h in hits],
                          blocked=blocked, grounding=grounding)
