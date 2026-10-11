"""契约 ③：会话与需求（Extractor 协议与 apply_extraction 在 huayan.l1.extract）。"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import BaseModel, datetime
from .jev import JevDecision
from .knowledge import Version
from .seeds import Candidate

Intent = Literal["need", "product_question", "mechanism_request", "smalltalk"]


class Turn(BaseModel):
    id: str                                   # "turn:sess:3:2"
    session_id: str
    n: int                                    # 从 1 开始
    speaker: Literal["customer", "sales"]
    text: str
    ts: datetime


class SlotFill(BaseModel):
    slot: str
    value: str | None                         # status=unknown 时为 None
    status: Literal["filled", "unknown"]
    confidence: float = Field(ge=0, le=1)
    quote: str                                # 客户原话片段（溯源）
    turn_id: str


class CustomerProfile(BaseModel):
    chem_savvy: bool = False
    asked_mechanism: bool = False
    evidence_quote: str = ""


class NeedState(BaseModel):
    session_id: str
    customer_id: str
    sales_id: str
    phenomenon: str | None = None
    phenomenon_quote: str = ""
    slots: dict[str, SlotFill] = {}
    asked: dict[str, int] = {}                # 槽位 → 业务员已追问次数
    turn_count: int = 0
    profile: CustomerProfile = Field(default_factory=CustomerProfile)
    last_intent: Intent = "need"
    extracted_by: Literal["llm", "rule"] = "llm"

    def known(self) -> dict[str, str]:
        return {slot: fill.value for slot, fill in self.slots.items() if fill.status == "filled"}


class ExtractedSlot(BaseModel):
    slot: str
    value: str | None
    status: Literal["filled", "unknown"]
    confidence: float = Field(ge=0, le=1)
    quote: str
    turn_n: int


class ExtractionResult(BaseModel):            # caller "agent:extract"
    intent: Intent
    phenomenon: str | None
    phenomenon_quote: str = ""
    slots: list[ExtractedSlot] = []           # 只含本次新增或改变的槽位
    asked_slots: list[str] = []
    profile: CustomerProfile


class AskHint(BaseModel):
    session_id: str
    slot: str
    label: str
    ask_text: str
    p_need: float
    scored_by: str                            # 同 JueOutput.scored_by


class Recommendation(BaseModel):              # 会话里存的「决定」，渲染另做
    product_id: str | None
    candidates: list[Candidate]
    match: JevDecision | None                 # 无候选时为 None
    disclose: JevDecision | None
    version: Version | None                   # 对 L1 披露的版本
    escalated_question_id: str | None = None  # 业务员签字升级时关闭的 escalate_need 问题
    at: datetime


class AssistantReply(BaseModel):
    turn_id: str
    text: str
    ku_ids: list[str]
    blocked: bool                             # 命中了高层级内容但被拦截
    grounding: JevDecision | None = None


class Session(BaseModel):
    id: str
    customer_id: str
    sales_id: str
    started_at: datetime
    turns: list[Turn] = []
    need: NeedState
    hints: list[AskHint] = []
    replies: list[AssistantReply] = []
    recommendation: Recommendation | None = None
    status: Literal["open", "recommended", "escalated", "closed"] = "open"
    reply_draft: str = ""                     # Agent 起草的回复，预填进「发给客户」输入框；发出后清空
    escalate_note: str = ""                   # Agent 起草的升级说明；业务员签字时写入需求单
