"""契约 ⑤：觉的对象、状态、模板与输出。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import Field

from ._base import BaseModel, datetime
from .bus import Question
from .seeds import Role

if TYPE_CHECKING:
    from huayan.events import EventLog

ObjectType = Literal["slot", "theme", "knowledge", "actor"]
Family = Literal["ask_slot", "opportunity", "knowledge_conflict", "leak_risk"]


class JueObject(BaseModel):
    object_id: str
    object_type: ObjectType
    attrs: dict[str, float | int | str | bool]    # 命名见契约 5.2


class JueState(BaseModel):
    at: datetime
    mode: Literal["realtime", "scheduled"]
    objects: dict[str, JueObject]

    def to_s1_state(self, object_ids: list[str] | None = None) -> dict:
        ids = list(self.objects) if object_ids is None else object_ids
        return {"at": self.at.isoformat(),
                "objects": {i: {"type": self.objects[i].object_type, "attrs": dict(self.objects[i].attrs)}
                            for i in ids}}


class JueTemplate(BaseModel):
    id: str
    family: Family
    object_type: ObjectType
    decision_label: str
    precondition: str | None = None           # 布尔表达式，只能引用 attrs.x
    rule_score: str | None = None             # 数值表达式；为空时 1.0
    worth_prompt: str                         # 含 {object}
    title: str                                # 可含 {object} 与 {attrs.x}
    owner_role: Role
    bounty_points: int = 0


class ScoredDecision(BaseModel):
    family: Family
    object_id: str
    p_need: float | None = Field(default=None, ge=0, le=1)   # None = 前置条件未通过
    urgency: float | None = None
    precondition_passed: bool = True
    template_id: str | None = None


class JueOutput(BaseModel):
    at: datetime
    mode: Literal["realtime", "scheduled"]
    model: Literal["jue_proto", "jue_k"]
    scored_by: Literal["onejev", "rule", "jue_k"]
    decisions: list[ScoredDecision]


class QuestionModel(Protocol):
    name: Literal["jue_proto", "jue_k"]
    def propose(self, state: JueState) -> JueOutput: ...


class Discoverer(Protocol):
    name: Literal["jue_proto", "rule_alert", "llm_poll"]
    def discover(self, events: EventLog, at: datetime) -> list[Question]: ...
