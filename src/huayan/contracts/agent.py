"""契约 ⑭：角色助手（huayan.agent，WP-L）。工具注册表与 Agent Loop 在 huayan.agent。"""
from __future__ import annotations

from typing import Any, Literal

from ._base import BaseModel, datetime
from .seeds import Role

ToolKind = Literal["read", "draft", "effect"]
# read：只读，按委托人权限过滤，自动执行
# draft：写草稿（未生效），自动执行
# effect：让结果生效；只用于对话里 Agent 的提议，挂起为 PendingAction，委托人确认后才执行。
#         工作面上的签字按钮直接调门面，不经过 PendingAction；没有委托人的 Agent（pm:agent）没有 effect 工具


class ToolSpec(BaseModel):
    name: str                                 # 动词_名词，如 search_knowledge
    kind: ToolKind
    roles: list[Role]                         # 哪些角色的助手拥有它
    description: str                          # 给模型看的一句话
    params: type[BaseModel]                   # 参数模型：扁平、字段少；不得含委托人 / 身份字段（运行时绑定）
    confirm_text: str = ""                    # effect 工具确认卡模板，用 args 格式化，如「确认需求单 {req_id} 并交研发」


class ToolResult(BaseModel):
    ok: bool = True
    data: Any = None                          # 精简 JSON：只含委托人权限内的内容，不含当前时间
    error: str | None = None                  # 参数错误 / 权限拒绝 / 校验失败；原样回给模型
    pending_action_id: str | None = None      # effect 工具：已挂起，等待委托人确认


class PendingAction(BaseModel):
    id: str                                   # "act:<n>"
    conversation_id: str
    principal: str                            # 委托人 actor id；只有他能确认
    tool: str
    args: dict[str, Any]
    summary: str                              # 确认卡上的人话：要做什么、影响谁
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime
    decided_at: datetime | None = None
    result: ToolResult | None = None          # 确认后执行的结果


class AgentStep(BaseModel):                   # 执行轨迹的一步，写 runs/<run_id>/agent_trace.jsonl
    conversation_id: str
    step: int
    principal: str
    tool: str | None                          # None = 本轮最终的文字回复
    args: dict[str, Any] = {}
    result_summary: str = ""
    blocked: list[str] = []                   # 越权命中，只有「归属人 · L3」这样的提示
    pending_action_id: str | None = None
    at: datetime


class AgentMessage(BaseModel):
    role: Literal["principal", "assistant", "system"]   # system = 派单通知、确认结果
    text: str
    at: datetime
    pending_action_ids: list[str] = []
    target: str | None = None                 # 批注挂的位置，如 "req:3/chem/2"、"sess:5/reply"；None = 普通消息


class Conversation(BaseModel):
    id: str                                   # "conv:<actor_id>:<session_id 或 inbox>"
    principal: str
    role: Role                                # sales / pm / rd；产品经理 Agent 的 principal 为 pm:agent
    session_id: str | None = None             # 业务员助手绑定的客户会话
    messages: list[AgentMessage] = []


class MemoryEntry(BaseModel):                 # v8（人批准 2026-10-21）：助手记忆，按委托人存，写 runs/<run_id>/memory.json
    id: str                                   # "mem:<n>"
    principal: str                            # 委托人；产品经理 Agent 为 pm:agent
    kind: Literal["habit", "fact", "lesson"]  # 委托人的习惯 / 业务事实 / 教训
    text: str                                 # 一句话，进每段对话开头的索引
    why: str = ""                             # 来由与怎么用
    refs: list[str] = []                      # 依据：需求单、会话、问题编号
    at: datetime
    status: Literal["active", "deleted"] = "active"
