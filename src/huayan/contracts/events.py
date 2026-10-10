"""契约 ⑧：事件（EventLog 在 huayan.events）。"""
from __future__ import annotations

from typing import Any, Literal

from ._base import BaseModel, datetime

EventKind = Literal["turn", "extraction", "ask_hint", "recommend", "escalate", "retrieve", "access_denied",
                    "decrypt_request", "decrypt_approve", "question_published", "question_resolved",
                    "requirement_confirmed", "requirement_translated", "knowledge_contributed", "trial",
                    "product_released", "sheet_updated", "access_frozen", "agent_action_proposed",
                    "agent_action_decided"]


class Event(BaseModel):
    id: str                                   # 日志分配
    ts: datetime
    kind: EventKind
    actor: str
    session_id: str | None = None
    payload: dict[str, Any] = {}
