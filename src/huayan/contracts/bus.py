"""契约 ⑥：问题（QuestionBus 在 huayan.bus）。"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

from ._base import BaseModel, datetime
from .seeds import Role

QFamily = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]   # 同契约 ⑤ Family：由模板目录校验


class Evidence(BaseModel):
    summary: str
    event_ids: list[str] = []
    quote: str = ""


class Resolution(BaseModel):
    action: Literal["sign", "accept", "return", "answered", "update_sheet", "freeze_access",
                    "approve_decrypt", "reject_decrypt", "dismiss"]
    # sign：签字人在工作面签字（v5.2：机会汇聚的 sign = 研发签字合并）；accept / return：研发接单 / 退回（accept 同时关闭关联的 opportunity）；
    # answered：回问已答，或异常类问题的前置条件不再成立
    by: str
    note: str = ""


class Question(BaseModel):
    id: str
    family: QFamily
    title: str
    object_id: str                            # sess:3 / theme:... / knowledge:... / actor:...
    owner_role: Role                          # 主人（谁准备）
    owner_id: str | None = None
    signer_role: Role | None = None           # None = 提示类
    signer_id: str | None = None
    prepared_at: datetime | None = None       # None = 准备中；有值 = 待签
    template_id: str | None = None
    status: Literal["open", "resolved", "dismissed"] = "open"
    p_need: float | None = None
    urgency: float | None = None
    scored_by: str                            # onejev / llm_fallback / mock / rule / jue_k / human
    discoverer: Literal["jue_proto", "jue_k", "rule_alert", "llm_poll", "human"]
    evidence: list[Evidence] = []
    refs: dict[str, str] = {}
    bounty_points: int = 0
    dedup_key: str                            # f"{family}:{object_id}"
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: Resolution | None = None
