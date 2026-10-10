"""契约 ⑦：升级与回流。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime


class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []                # turn id


class PMDraft(BaseModel):                     # caller "agent:pm_draft"
    direction: str
    product_lang: list[ReqItem]               # L2
    chem_lang: list[ReqItem]                  # L2/L3 可见


class Requirement(BaseModel):
    id: str                                   # "req:<n>"
    question_id: str
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    direction: str
    product_lang: list[ReqItem]
    chem_lang: list[ReqItem]
    status: Literal["draft", "confirmed", "released", "rejected"]
    drafted_by: str
    confirmed_by: str | None = None
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
