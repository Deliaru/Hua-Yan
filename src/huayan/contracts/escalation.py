"""契约 ⑦：升级、分层转译与回流。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime
from .seeds import Level


class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []                # turn id，可回查客户原话
    ku_refs: list[str] = []                   # 依据的知识单元（转化对照、案例、机理）；其归属人记 cited


class PMDraft(BaseModel):                     # L2 转译（caller "agent:pm_draft"）：场景语言 → 产品需求语言
    direction: str
    product_lang: list[ReqItem]


class RDDraft(BaseModel):                     # L3 转译（caller "agent:rd_translate"）：产品需求 → 化学语言
    chem_lang: list[ReqItem]
    hypotheses: list[str] = []                # 研发方向假设


class SheetDraft(BaseModel):                  # 反向包装（caller "agent:package"）：研发结果 → L1 说明书
    sheet: str
    usage: str


class Requirement(BaseModel):
    id: str                                   # "req:<n>"
    question_id: str
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    direction: str
    product_lang: list[ReqItem]               # L2/L3 可见
    chem_lang: list[ReqItem] = []             # L2/L3 可见；所引 L3 知识的原文只有 L3 可见
    hypotheses: list[str] = []
    status: Literal["draft", "pm_confirmed", "rd_confirmed", "released", "rejected"]
    drafted_by: str
    pm_confirmed_by: str | None = None
    rd_confirmed_by: str | None = None
    product_id: str | None = None
    created_at: datetime


class Trial(BaseModel):
    id: str
    product_id: str
    requirement_id: str | None = None
    rd: str
    conditions: dict[str, str]
    result: Literal["pass", "fail"]
    cause: Literal["none", "product", "equipment", "operation"]
    note: str = ""
    at: datetime


class CitedKnowledge(BaseModel):              # 需求单中被引用的知识，按查看者裁剪
    ku_id: str
    owner: str
    level: Level
    title: str
    text: str | None                          # 查看者无权阅读时为 None，只显示归属与层级
    n_cited: int                              # 全系统累计被引用次数


class RequirementView(BaseModel):
    viewer: str
    viewer_level: Level
    requirement: Requirement
    quotes: dict[str, str]                    # turn id → 客户原话
    cited: list[CitedKnowledge]


class ContributionStat(BaseModel):            # 贡献看板的一行
    owner: str
    ku_id: str
    level: Level
    title: str
    n_cited: int
    points: int
    used_by: list[str]                        # 需求单 / 会话 id
