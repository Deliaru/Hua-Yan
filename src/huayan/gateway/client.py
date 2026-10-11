# 复用自 JUE 赛前代码 src/jue/gateway/client.py
"""OpenAI-compatible synchronous gateway with bounded retries and replay."""

import hashlib
import json
import os
import time
from pathlib import Path

import openai
from pydantic import ValidationError

from huayan.contracts import LLMResponse, LLMToolCall, Message, Tier, Usage


class StructuredOutputError(ValueError):
    pass


class ReplayMiss(RuntimeError):
    """严格回放缺少录制结果，禁止转为真实请求。"""


class OpenAICompatGateway:
    def __init__(self, config, meter=None, *, clients=None, cache_dir=None, trace=None, sleep=time.sleep):
        self.tiers = config["tiers"]
        self.meter, self.trace = meter, trace
        self.clients = {} if clients is None else dict(clients)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.replay = False
        self.sleep = sleep

    def _client(self, tier):
        if tier not in self.clients:
            cfg = self.tiers[tier]
            self.clients[tier] = openai.OpenAI(base_url=cfg["base_url"], api_key=os.environ[cfg["api_key_env"]], max_retries=0)
        return self.clients[tier]

    def _order(self, tier):
        pending, seen = [tier], set()
        while pending:
            current = pending.pop(0)
            if current not in seen:
                seen.add(current)
                yield current
                pending.extend(self.tiers[current].get("fallbacks", []))

    def _record(self, req, response, *, cached=False):
        if self.meter is not None:
            self.meter.record(caller=req.caller, kind="llm", model=response.model,
                              input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                              latency_ms=response.latency_ms, cost=response.cost,
                              fallback_used=response.fallback_used, degraded=response.fallback_used)
        if self.trace is not None:
            self.trace("llm", caller=req.caller, tier=response.tier.value, model=response.model,
                       cached=cached, fallback_used=response.fallback_used)

    def _complete(self, req, schema=None):
        if not req.caller:
            raise ValueError("Every model call needs caller")
        cache_key = hashlib.sha256(json.dumps({"request": req.model_dump(mode="json"),
            "schema": schema.model_json_schema() if schema else None, "tiers": self.tiers},
            sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        path = Path(self.cache_dir) / f"{cache_key}.json" if self.cache_dir else None
        if path and path.exists():
            response = LLMResponse.model_validate_json(path.read_text(encoding="utf-8"))
            print(f"[cache:gateway] caller={req.caller}")
            self._record(req, response, cached=True)
            return response
        if self.replay:
            raise ReplayMiss(f"gateway 回放缓存未命中：caller={req.caller} key={cache_key}")
        messages = []
        for message in req.messages:
            item = {"role": message.role, "content": message.content}
            if message.tool_call_id:
                item["tool_call_id"] = message.tool_call_id
            if message.tool_calls:
                item["tool_calls"] = [{"id": call.call_id, "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
                    for call in message.tool_calls]
            messages.append(item)
        if schema is not None:
            messages.insert(0, {"role": "system", "content": "Return a JSON object matching this schema: " + json.dumps(schema.model_json_schema(), ensure_ascii=False)})
        last_error = None
        for tier in self._order(req.tier.value):
            cfg = self.tiers[tier]
            for attempt in range(4):
                started = time.perf_counter()
                try:
                    kwargs = dict(model=cfg["model"], messages=messages, temperature=req.temperature,
                                  max_tokens=req.max_tokens, timeout=req.timeout_s)
                    if req.tools:
                        kwargs["tools"] = req.tools
                    if schema is not None:
                        kwargs["response_format"] = {"type": "json_object"}
                    raw = self._client(tier).chat.completions.create(**kwargs)
                    latency = (time.perf_counter() - started) * 1000
                    usage = Usage(input_tokens=raw.usage.prompt_tokens if raw.usage else 0,
                                  output_tokens=raw.usage.completion_tokens if raw.usage else 0)
                    prices = cfg["price_per_1k"]
                    cost = None if raw.usage is None or None in (prices["input"], prices["output"]) else (
                        usage.input_tokens * prices["input"] + usage.output_tokens * prices["output"]) / 1000
                    message = raw.choices[0].message
                    response = LLMResponse(content=message.content,
                        tool_calls=[LLMToolCall(call_id=call.id, name=call.function.name,
                                               arguments=json.loads(call.function.arguments)) for call in (message.tool_calls or [])],
                        usage=usage, latency_ms=latency, model=raw.model, tier=Tier(tier), cost=cost,
                        fallback_used=tier != req.tier.value)
                    self._record(req, response)
                    if path:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(response.model_dump_json(), encoding="utf-8")
                    return response
                except (openai.APIConnectionError, openai.APIStatusError) as exc:
                    last_error = exc
                    if self.meter is not None:
                        self.meter.record(caller=req.caller, kind="llm", model=cfg["model"], ok=False,
                                          latency_ms=(time.perf_counter() - started) * 1000,
                                          fallback_used=tier != req.tier.value, degraded=tier != req.tier.value)
                    retryable = isinstance(exc, openai.APIConnectionError) or exc.status_code == 429 or exc.status_code >= 500
                    if not retryable:
                        raise
                    if attempt < 3:
                        self.sleep(2 ** attempt)
        raise last_error

    def complete(self, req):
        return self._complete(req)

    def structured(self, req, schema):
        request = req.model_copy(deep=True)
        for attempt in range(3):
            response = self._complete(request, schema)
            content = (response.content or "").strip()
            if content.startswith("```"):  # Some OpenAI-compatible relays fence json_object replies in Markdown.
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
            try:
                return schema.model_validate_json(content), response
            except ValidationError as exc:
                if attempt == 2:
                    raise StructuredOutputError(f"{schema.__name__} failed validation after 3 attempts: {exc}") from exc
                request.messages.extend([Message(role="assistant", content=response.content or ""),
                    Message(role="user", content=f"Invalid JSON/schema: {exc}. Return a corrected JSON object.")])
