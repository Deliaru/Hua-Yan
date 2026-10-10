"""契约 ②：知识单元、披露、审计与积分（具体类 KnowledgeBase / AuditLog / Ledger 在 huayan.knowledge）。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime
from .seeds import Level

KUKind = Literal["sheet", "usage", "case", "translation", "requirement", "mechanism", "formula", "trial"]
KIND_LEVEL: dict[KUKind, Level] = {"sheet": 1, "usage": 1, "case": 2, "requirement": 2,
                                    "mechanism": 3, "formula": 3, "trial": 3}   # translation 取种子中的 level


class KnowledgeUnit(BaseModel):
    id: str                                   # "ku:<kind>:<ref>"
    level: Level
    kind: KUKind
    title: str
    text: str
    product_id: str | None = None
    phenomenon_ids: list[str] = []
    owner: str
    decryptable: bool = False                 # 只有 mechanism 为 True
    source: Literal["seed", "released", "trial", "contributed"] = "seed"
    created_at: datetime


class KnowledgeHit(BaseModel):
    ku: KnowledgeUnit
    score: float


Version = Literal["product", "product_usage", "full_mechanism", "internal"]
CUSTOMER_VERSIONS: list[Version] = ["product", "product_usage", "full_mechanism"]   # Jev 只在这三者中选


class DecryptGrant(BaseModel):
    id: str
    customer_id: str
    product_id: str
    session_id: str
    approved_by: str
    at: datetime


class CardSection(BaseModel):
    title: str
    text: str
    ku_id: str
    level: Level


class RecommendationCard(BaseModel):          # 按「查看者」渲染的结果，不落盘
    session_id: str
    viewer: str
    product_id: str | None                    # None = 已升级，无推荐
    version: Version
    sections: list[CardSection]
    note: str = ""


class AuditRecord(BaseModel):
    ts: datetime
    actor: str
    action: Literal["disclose", "deny", "decrypt_request", "decrypt_approve", "decrypt_reject", "freeze"]
    object_ids: list[str]
    version: Version | None = None
    session_id: str | None = None
    reason: str = ""


class LedgerEntry(BaseModel):
    ts: datetime
    owner: str
    points: int
    reason: Literal["cited", "contributed", "trial_pass", "product_released", "bounty"]
    ku_id: str | None = None
    ref: str
