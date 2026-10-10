# 复用自 JUE 赛前代码 src/jue/system1/onejev.py（build_system1 增加 impl="mock"）
"""OneJev HTTP client and the explicit LLM fallback (WP-P stage 1). Unreachable OneJev raises; it never degrades silently."""

import base64
import hashlib
import json
import math
import mimetypes
import time
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from huayan.contracts import LLMRequest, Message, S1Answer, S1Choice, S1Noul, S1Result, Tier


def _distribution(raw, keys):
    if set(raw) != set(keys):
        raise ValueError("Probability keys do not match the question")
    values = {key: float(raw[key]) for key in keys}
    if any(not math.isfinite(p) or p < 0 or p > 1 for p in values.values()):
        raise ValueError("Probabilities must be finite and within [0,1]")
    total = sum(values.values())
    if abs(total - 1) > 1e-3:
        raise ValueError(f"Invalid probability sum: {total}")
    return {key: value / total for key, value in values.items()}


def _expected(probabilities, levels):
    return sum(probabilities[label] * i / (len(levels) - 1) for i, label in enumerate(levels))


class OneJevClient:
    """`POST /v1/systemone`: one request answers every question about one state."""

    def __init__(self, base_url, model, meter, timeout_s=120, gpu_price_per_hour=None, evidence_dir=None, media_root=None, deadline=None):
        self.http = httpx.Client(base_url=base_url, timeout=timeout_s, trust_env=False)
        self.model, self.meter, self.price = model, meter, gpu_price_per_hour
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self.media_root = Path(media_root).resolve() if media_root else None
        self.deadline = deadline
        self.last_request = self.last_response = None

    def close(self):
        self.http.close()

    def _media(self, item):
        if item.type != "image":
            raise ValueError("OneJev client only sends images")
        if item.path:
            path = Path(item.path).resolve()
            if self.media_root is None or not path.is_relative_to(self.media_root):
                raise ValueError("Image is outside the configured media root")
            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            return {"type": "image", "data": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")}
        if not item.url or not item.url.startswith("data:image/"):
            raise ValueError("Only local files or inline image data are sent, never external URLs")
        return {"type": "image", "data": item.url}

    def ask(self, state, media, questions, caller):
        body = {"model": self.model, "state": state, "media": [self._media(item) for item in media], "questions": {}}
        for key, question in questions.items():
            body["questions"][key] = {"type": question.kind, "instructions": question.text}
            if isinstance(question, S1Choice):
                body["questions"][key]["criteria"] = question.options
            elif not isinstance(question, S1Noul):
                if len(question.levels) < 2:
                    raise ValueError("A score question needs at least two levels")
                body["questions"][key]["criteria"] = question.levels
        self.last_request = body
        started, ok, raw_text, error = time.monotonic(), False, None, None
        try:
            timeout = self.http.timeout.read
            if self.deadline is not None:
                timeout = min(timeout, self.deadline - time.time())
                if timeout <= 0:
                    raise TimeoutError("Request deadline exhausted")
            response = self.http.post("/v1/systemone", json=body, timeout=timeout)
            raw_text = response.text
            response.raise_for_status()
            raw = self.last_response = response.json()
            if raw["model"] != self.model or set(raw["answers"]) != set(questions):
                raise ValueError("Served model or question IDs do not match the request")
            answers = {}
            for key, question in questions.items():
                answer = raw["answers"][key]
                if answer["type"] != question.kind:
                    raise ValueError("Answer type mismatch")
                if isinstance(question, S1Noul):
                    p = float(answer["noul"])
                    answers[key] = S1Answer(probabilities=_distribution({"yes": p, "no": 1 - p}, ["yes", "no"]))
                elif isinstance(question, S1Choice):
                    answers[key] = S1Answer(probabilities=_distribution(answer["probabilities"], list(question.options)))
                else:
                    # OneJev keys score levels by index; map them back to the question's labels.
                    by_index = _distribution(answer["probabilities"], [str(i) for i in range(len(question.levels))])
                    probabilities = {label: by_index[str(i)] for i, label in enumerate(question.levels)}
                    answers[key] = S1Answer(probabilities=probabilities, expected=_expected(probabilities, question.levels))
            ok = True
            return S1Result(answers=answers, latency_ms=(time.monotonic() - started) * 1000, impl="onejev", degraded=False)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = (time.monotonic() - started) * 1000
            usage = (self.last_response or {}).get("usage", {}) if ok else {}
            self.meter.record(caller=caller, kind="s1", model=self.model, impl="onejev", degraded=False, n_questions=len(questions),
                              input_tokens=usage.get("input_tokens", 0), latency_ms=elapsed, ok=ok,
                              cost=None if self.price is None else self.price * elapsed / 3_600_000)
            if self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                with (self.evidence_dir / "requests.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"request": body, "response_text": raw_text, "latency_ms": elapsed, "ok": ok, "error": error,
                                             "response_sha256": hashlib.sha256((raw_text or "").encode("utf-8")).hexdigest()},
                                            ensure_ascii=False) + "\n")


class _FallbackProbabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, dict[str, float]]


class LLMSystem1Fallback:
    """Explicitly selected degraded System 1: the FAST-tier LLM returns probabilities via the gateway."""

    def __init__(self, gateway, meter):
        self.gateway, self.meter = gateway, meter

    def ask(self, state, media, questions, caller):
        started, ok = time.monotonic(), False
        try:
            content = json.dumps({"state": state, "media": [m.model_dump(mode="json") for m in media],
                                  "questions": {k: v.model_dump() for k, v in questions.items()}}, ensure_ascii=False, sort_keys=True)
            output, _ = self.gateway.structured(LLMRequest(tier=Tier.FAST, caller=caller, messages=[Message(role="user", content=content)]),
                                                _FallbackProbabilities)
            if set(output.answers) != set(questions):
                raise ValueError("Fallback question IDs mismatch")
            answers = {}
            for key, question in questions.items():
                keys = ["yes", "no"] if isinstance(question, S1Noul) else list(question.options) if isinstance(question, S1Choice) else question.levels
                probabilities = _distribution(output.answers[key], keys)
                expected = None if isinstance(question, (S1Noul, S1Choice)) else _expected(probabilities, keys)
                answers[key] = S1Answer(probabilities=probabilities, expected=expected)
            ok = True
            return S1Result(answers=answers, latency_ms=(time.monotonic() - started) * 1000, impl="llm_fallback", degraded=True)
        finally:
            self.meter.record(caller=caller, kind="s1", impl="llm_fallback", degraded=True, n_questions=len(questions),
                              latency_ms=(time.monotonic() - started) * 1000, cost=None, ok=ok)


def build_system1(impl, config_path, gateway, meter):
    if impl == "mock":
        from .mock import MockSystem1Client
        return MockSystem1Client(meter)
    if impl == "llm_fallback":
        return LLMSystem1Fallback(gateway, meter)
    if impl != "onejev":
        raise ValueError(f"Unknown System 1 implementation: {impl}")
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    client = OneJevClient(cfg["base_url"], cfg["model"], meter, cfg["timeout_s"], cfg.get("gpu_price_per_hour"), media_root=cfg.get("media_root"))
    try:
        client.http.get("/health").raise_for_status()
    except Exception:
        client.close()
        raise
    return client
