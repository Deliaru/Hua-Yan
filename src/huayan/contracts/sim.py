"""契约 ⑨：模拟与评测数据。只有 huayan.sim 与 huayan.eval 可以读这些文件。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel, datetime
from .escalation import Trial


class NeedCard(BaseModel):                    # data/sim/cards.jsonl
    id: str
    phenomenon: str
    slots: dict[str, str]
    unknown_slots: list[str] = []
    opening_slots: list[str] = []
    customer_id: str
    chem_savvy: bool
    wants_mechanism: bool
    truth_product: str | None                 # None = 应升级


class Injection(BaseModel):                   # data/week/<week_id>/injections.jsonl
    id: str
    family: Literal["opportunity", "knowledge_conflict", "leak_risk"]
    object_id: str
    hard_negative: bool
    onset: datetime
    earliest: datetime
    latest: datetime


class WeekItem(BaseModel):                    # data/week/<week_id>/script.jsonl
    at: datetime
    kind: Literal["session", "trial", "query"]
    actor: str
    card_id: str | None = None
    text: str = ""
    trial: Trial | None = None
