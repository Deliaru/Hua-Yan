"""契约 0（角色与层级）与 ①（种子数据、Seeds、Candidate）。"""
from __future__ import annotations

from typing import Literal

from ._base import BaseModel

Role = Literal["customer", "sales", "pm", "rd", "supervisor"]
Level = Literal[1, 2, 3]
ROLE_LEVEL: dict[Role, Level] = {"customer": 1, "sales": 1, "pm": 2, "rd": 3, "supervisor": 2}


class Actor(BaseModel):
    id: str                  # "sales:S01"
    role: Role
    name: str


class SlotDef(BaseModel):
    id: str
    label: str
    values: list[str]
    ask_text: str
    ask_keywords: list[str]
    customer_phrases: dict[str, list[str]]    # 取值 → 客户口语说法；不同取值之间的说法不得重复


class Phenomenon(BaseModel):
    id: str
    label: str
    customer_phrases: list[str]
    required_slots: list[str]
    causes: str                               # L3 知识
    slot_priors: dict[str, dict[str, float]] = {}


class Product(BaseModel):
    id: str
    name: str
    category: str
    solves: list[str]
    applicable: dict[str, list[str]] = {}     # 槽位 → 适用取值；未列出的槽位不限
    sheet: str                                # L1
    usage: str                                # L1
    mechanism: str                            # L3，可经审批解密
    formula: str                              # L3，永不对外
    owner: str
    status: Literal["released", "project"] = "released"


class Case(BaseModel):
    id: str
    phenomenon: str
    slots: dict[str, str]
    product_id: str | None
    scene_text: str
    pm_translation: str
    owner: str


class Translation(BaseModel):
    id: str
    scene_phrase: str                         # 原文：客户的场景说法（L2 条目）或产品需求说法（L3 条目）
    chem_term: str                            # 译文：L2 条目为产品需求语言，L3 条目为化学语言
    level: Literal[2, 3]                      # 2 = 产品经理的「场景 → 产品需求」；3 = 研发的「→ 化学语言」
    owner: str
    phenomenon_ids: list[str] = []


class Seeds(BaseModel):
    slots: list[SlotDef]
    phenomena: list[Phenomenon]
    products: list[Product]
    cases: list[Case]
    translations: list[Translation]
    actors: list[Actor]
    placeholder: bool                         # 任一文件为占位即为 True


class Candidate(BaseModel):
    product_id: str
    unknown_slots: list[str]                  # applicable 中有限定、但当前未知的槽位
