"""契约 ⑭：角色助手的 Agent Loop。改写自 JUE 赛前代码 src/jue/agent/__init__.py 的 Agent.handle：
去掉派生子问题、钩子注册表和最终结构化决策；effect 工具由 AgentHub 挂起为确认卡。"""
from pathlib import Path

from huayan.clock import get_clock
from huayan.contracts import AgentMessage, AgentStep, Conversation, LLMRequest, Message, Tier
from huayan.knowledge import level_of

from .tools import ToolContext, openai_schemas

MAX_STEPS = 8
PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
OUT_OF_STEPS = "步数用完，已完成的部分见上。"


def system_prompt(ctx: ToolContext, pending: list) -> str:
    me = ctx.principal
    lines = [(PROMPTS / f"assistant_{me.role}.md").read_text(encoding="utf-8"),
             f"\n委托人：{me.name}（{me.id}，角色 {me.role}，可读知识层级 L1–L{level_of(me)}）。"]
    if ctx.session_id:
        lines.append(f"当前绑定的客户会话：{ctx.session_id}。")
    if pending:
        lines.append("委托人尚未确认的动作：" + "；".join(f"{a.id} {a.summary}" for a in pending))
    return "\n".join(lines)


def history(conv: Conversation) -> list[Message]:
    """跨轮只保留文字消息；system 消息（派单、确认结果）作为带标记的用户消息传给模型。"""
    role = {"principal": "user", "assistant": "assistant", "system": "user"}
    return [Message(role=role[m.role], content=m.text if m.role != "system" else f"【系统通知】{m.text}")
            for m in conv.messages]


def run_turn(conv: Conversation, ctx: ToolContext, hub, gateway) -> list[AgentMessage]:
    """跑一轮：模型 → 工具 → 模型 … 直到没有工具调用或满 8 步；返回本轮的助手消息。"""
    role = ctx.principal.role
    messages = [Message(role="system", content=system_prompt(ctx, hub.pending(ctx.principal.id))), *history(conv)]
    created, reply = [], OUT_OF_STEPS
    for step in range(1, MAX_STEPS + 1):
        response = gateway.complete(LLMRequest(tier=Tier.FAST, caller=f"agent:{role}", messages=messages,
                                               tools=openai_schemas(role), temperature=0))
        messages.append(Message(role="assistant", content=response.content or "", tool_calls=response.tool_calls))
        if not response.tool_calls:
            reply = response.content or ""
            hub.record_step(AgentStep(conversation_id=conv.id, step=step, principal=ctx.principal.id, tool=None,
                                      result_summary=reply[:200], at=get_clock().now()))
            break
        for call in response.tool_calls:
            result = hub.call_tool(ctx, call.name, call.arguments)
            data = result.data if isinstance(result.data, dict) else {}
            encoded = result.model_dump_json(exclude_none=True)
            hub.record_step(AgentStep(conversation_id=conv.id, step=step, principal=ctx.principal.id, tool=call.name,
                                      args=call.arguments, result_summary=encoded[:200], blocked=data.get("blocked", []),
                                      pending_action_id=result.pending_action_id, at=get_clock().now()))
            created += [result.pending_action_id] if result.pending_action_id else []
            messages.append(Message(role="tool", content=encoded, tool_call_id=call.call_id))
    return [AgentMessage(role="assistant", text=reply, at=get_clock().now(), pending_action_ids=created)]
