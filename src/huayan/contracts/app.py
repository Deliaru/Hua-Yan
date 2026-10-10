"""契约 ⑫：门面返回给界面的视图（HuayanApp 在 huayan.app）。"""
from __future__ import annotations

from ._base import BaseModel
from .escalation import Requirement
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
