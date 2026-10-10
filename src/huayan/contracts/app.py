"""契约 ⑫：门面返回给界面的视图（HuayanApp 在 huayan.app）。"""
from __future__ import annotations

from ._base import BaseModel, datetime
from .escalation import Requirement
from .jue import Family
from .knowledge import RecommendationCard
from .seeds import Level
from .session import AskHint, AssistantReply, SlotFill, Turn


class SessionView(BaseModel):
    session_id: str
    viewer: str
    viewer_level: Level
    turns: list[Turn]
    slots: list[SlotFill]
    hints: list[AskHint]
    replies: list[AssistantReply]             # 已按查看者层级过滤
    card: RecommendationCard | None
    status: str
    escalation_question_id: str | None = None
    requirement: Requirement | None = None    # 只对 L2/L3 返回
    reply_draft: str = ""
    escalate_note: str = ""


class RunStatus(BaseModel):
    run_id: str
    replay: bool
    system1_impl: str
    realtime_model: str
    extractor: str
    gateway_mock: bool
    simulated_data: bool = True
    seeds_placeholder: bool
    scheduled_model: str = "jue_proto"


class TimelinePoint(BaseModel):               # 觉的一次判断中的一个「决策 × 对象」
    at: datetime
    family: Family
    object_id: str
    p_need: float | None
    threshold: float
    scored_by: str
    raised: bool                              # 这一次是否提出了问题


class TimelineNode(BaseModel):                # 一个被提出的问题的全过程
    question_id: str
    family: Family
    owner_id: str | None
    signer_id: str | None
    created_at: datetime
    prepared_at: datetime | None
    resolved_at: datetime | None
    action: str | None
    by: str | None


class JueTimeline(BaseModel):
    target_id: str                            # sess:<n> 或 req:<n>；需求单线程含其全部会话
    viewer: str
    points: list[TimelinePoint]               # 按查看者裁剪
    nodes: list[TimelineNode]
    n_judgments: int                          # 觉的判断次数（JueRecord 条数）
    n_llm_calls: int                          # 计量中 caller 以 "jue" 开头的大模型调用数（应为 0，取自计量）
    n_questions: int
    n_signatures: int
