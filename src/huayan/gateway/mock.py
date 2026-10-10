# 复用自 JUE 赛前代码 src/jue/gateway/mock.py（零值 datetime 取 get_clock().now()，默认墙钟）
"""Deterministic gateway for offline development; canned handles business outputs."""

import re
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import AwareDatetime, BaseModel

from huayan.clock import get_clock
from huayan.contracts import LLMRequest, LLMResponse, LLMToolCall, Tier, Usage


def _zero(annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is Annotated:
        return _zero(args[0])
    if origin in (Union, UnionType):
        return None if type(None) in args else _zero(args[0])
    if origin is Literal:
        return args[0]
    if origin in (list, dict, set):
        return origin()
    if origin is tuple:
        return () if Ellipsis in args else tuple(_zero(arg) for arg in args)
    if annotation is Any or annotation is type(None):
        return None
    if annotation in (str, int, float, bool):
        return annotation()
    if annotation in (datetime, AwareDatetime):
        return get_clock().now()
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _instance(annotation)
    if origin is type and issubclass(args[0], BaseModel):
        return args[0]
    raise TypeError(f"Provide a canned response for {annotation!r}")


def _instance(schema):
    return schema.model_validate({
        name: _zero(field.annotation)
        for name, field in schema.model_fields.items() if field.is_required()
    })


class MockGateway:
    def __init__(self, meter=None, canned=None):
        self.meter = meter
        self.canned = {} if canned is None else canned

    def _response(self, req, content, tool_calls=()):
        response = LLMResponse(
            content=content, tool_calls=list(tool_calls),
            usage=Usage(input_tokens=0, output_tokens=0),
            latency_ms=0, model="mock", tier=Tier.MOCK, cost=None,
        )
        if self.meter is not None:
            self.meter.record(caller=req.caller, kind="llm", model="mock",
                              input_tokens=0, output_tokens=0, latency_ms=0,
                              cost=None, degraded=True, fallback_used=False, ok=True)
        return response

    def complete(self, req: LLMRequest) -> LLMResponse:
        if req.tools and req.messages and req.messages[-1].role == "user":
            match = re.search(r"\[\[call:([^\]]+)\]\]", req.messages[-1].content)
            if match:
                call = LLMToolCall(call_id="mock-call-1", name=match[1], arguments={})
                return self._response(req, None, [call])
        return self._response(req, "mock")

    def structured(self, req: LLMRequest, schema: type[BaseModel]) -> tuple[BaseModel, LLMResponse]:
        value = self.canned[req.caller](schema, req) if req.caller in self.canned else _instance(schema)
        value = schema.model_validate(value)
        return value, self._response(req, value.model_dump_json())
