"""契约 ⑥：问题（QuestionBus 在 huayan.bus）。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime
from .seeds import Role

QFamily = Literal["escalate_need", "opportunity", "knowledge_conflict", "leak_risk", "decrypt_request"]


class Evidence(BaseModel):
    summary: str
    event_ids: list[str] = []
    quote: str = ""


class Resolution(BaseModel):
    action: Literal["draft_requirement", "approve_project", "update_sheet", "freeze_access",
                    "approve_decrypt", "reject_decrypt", "dismiss"]
    by: str
    note: str = ""


class Question(BaseModel):
    id: str
    family: QFamily
    title: str
    object_id: str                            # sess:3 / theme:... / knowledge:... / actor:...
    owner_role: Role
    owner_id: str | None = None
    status: Literal["open", "resolved", "dismissed"] = "open"
    p_need: float | None = None
    scored_by: str                            # onejev / llm_fallback / mock / rule / jue_k / human
    discoverer: Literal["jev", "jue_proto", "jue_k", "rule_alert", "llm_poll", "human"]
    evidence: list[Evidence] = []
    refs: dict[str, str] = {}
    bounty_points: int = 0
    dedup_key: str                            # f"{family}:{object_id}"
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: Resolution | None = None
