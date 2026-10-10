"""契约 ⑩：计量记录（FileMeter 在 huayan.meter）。"""
from __future__ import annotations

from typing import Literal, Protocol

from ._base import BaseModel, datetime


class MeterRecord(BaseModel):
    ts: datetime                              # 墙钟
    run_id: str
    caller: str
    kind: Literal["llm", "s1", "jue"]
    model: str | None = None
    impl: str | None = None
    degraded: bool = False
    n_questions: int | None = None
    n_objects: int | None = None              # jue：本次评估的对象数
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    cost: float | None = None
    ok: bool = True
    fallback_used: bool = False


class Meter(Protocol):
    def record(self, *, caller: str, kind: str, **fields) -> None: ...
