"""契约 ⑧：事件（EventLog 在 huayan.events）。"""
from __future__ import annotations

from typing import Any, Literal

from ._base import BaseModel, datetime

EventKind = Literal["turn", "extraction", "ask_hint", "match", "recommend", "escalate", "retrieve", "access_denied",
                    "decrypt_request", "decrypt_approve", "question_published", "question_prepared",
                    "question_resolved", "requirement_created", "requirement_accepted", "requirement_returned",
                    "requirement_edited", "requirement_translated", "knowledge_contributed", "trial", "market_eval",
                    "points_set", "reuse_proposed", "reuse_adopted", "reuse_declined", "merge_proposed", "requirements_merged", "product_released", "sheet_updated", "access_frozen", "human_decision",
                    "agent_action_proposed", "agent_action_decided"]


class Event(BaseModel):
    id: str                                   # 日志分配
    ts: datetime
    kind: EventKind
    actor: str
    session_id: str | None = None
    payload: dict[str, Any] = {}
