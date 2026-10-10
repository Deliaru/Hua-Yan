# 复用自 JUE 赛前代码 src/jue/contracts/gateway.py
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Protocol

from ._base import BaseModel


class Tier(str, Enum):
    FAST = "fast"; STRONG = "strong"; BACKUP = "backup"; MOCK = "mock"


class LLMToolCall(BaseModel):
    call_id: str; name: str; arguments: dict[str, Any]


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[LLMToolCall] = []


class LLMRequest(BaseModel):
    tier: Tier
    caller: str                               # "<模块>:<用途>"，见契约 ⑩
    messages: list[Message]
    tools: list[dict] | None = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout_s: float = 60


class Usage(BaseModel):
    input_tokens: int; output_tokens: int


class LLMResponse(BaseModel):
    content: str | None
    tool_calls: list[LLMToolCall] = []
    usage: Usage
    latency_ms: float
    model: str
    tier: Tier
    cost: float | None
    fallback_used: bool = False


class ModelGateway(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
    def structured(self, req: LLMRequest, schema: type[BaseModel]) -> tuple[BaseModel, LLMResponse]: ...
