"""契约 ④：System 1 题型（与 JUE 一致）与 Jev 决策。"""
from __future__ import annotations

from typing import Any, Literal, Protocol

from ._base import BaseModel


class S1Noul(BaseModel):
    kind: Literal["noul"] = "noul"; text: str


class S1Choice(BaseModel):
    kind: Literal["choice"] = "choice"; text: str; options: dict[str, str]


class S1Score(BaseModel):
    kind: Literal["score"] = "score"; text: str; levels: list[str]


S1Question = S1Noul | S1Choice | S1Score


class S1Answer(BaseModel):
    probabilities: dict[str, float]           # noul: {"yes", "no"}
    expected: float | None = None


class S1Result(BaseModel):
    answers: dict[str, S1Answer]
    latency_ms: float
    impl: Literal["onejev", "llm_fallback", "mock"]
    degraded: bool                            # impl != "onejev"


class System1Client(Protocol):
    def ask(self, state: dict[str, Any], media: list, questions: dict[str, S1Question], caller: str) -> S1Result: ...


class JevDecision(BaseModel):
    question: Literal["match", "disclose", "grounding"]
    probabilities: dict[str, float]           # 选项 id → 概率
    choice: str                               # 概率最大的选项
    confident: bool
    scored_by: Literal["onejev", "llm_fallback", "mock", "rule"]
