# 复用自 JUE 赛前代码 src/jue/system1/onejev.py（build_system1 增加 impl="mock"）
"""OneJev HTTP client and the explicit LLM fallback (WP-P stage 1). Unreachable OneJev raises; it never degrades silently."""

import base64
import hashlib
import json
import math
import mimetypes
import os
import time
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict

from huayan.contracts import LLMRequest, Message, S1Answer, S1Choice, S1Noul, S1Result, Tier
from huayan.gateway.client import ReplayMiss


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

    path = "/v1/systemone"

    def __init__(self, base_url, model, meter, timeout_s=120, gpu_price_per_hour=None, evidence_dir=None, media_root=None, deadline=None):
        self.http = httpx.Client(base_url=base_url, timeout=timeout_s, trust_env=False)
        self.model, self.meter, self.price = model, meter, gpu_price_per_hour
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self.media_root = Path(media_root).resolve() if media_root else None
        self.deadline = deadline
        self.last_request = self.last_response = None
        self.cache_dir, self.replay = None, False
        self.trace = None   # 界面过程面板的进度回调（可选）

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
        cache_key = hashlib.sha256(json.dumps({"caller": caller, "request": body},
            sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        path = Path(self.cache_dir) / f"{cache_key}.json" if self.cache_dir else None
        if self.trace:
            self.trace("s1_start", caller=caller, model=self.model)
        if path and path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            self.last_response = cached["response"]
            result = S1Result.model_validate(cached["result"])
            print(f"[cache:onejev] caller={caller}")
            if self.trace:
                self.trace("s1", caller=caller, model=self.model, cached=True, ok=True, latency_ms=result.latency_ms)
            self.meter.record(caller=caller, kind="s1", model=self.model, impl="onejev", degraded=False,
                              n_questions=len(questions), latency_ms=0, cost=0)
            return result
        if self.replay:
            raise ReplayMiss(f"onejev 回放缓存未命中：caller={caller} key={cache_key}")
        started, ok, raw_text, error = time.monotonic(), False, None, None
        try:
            timeout = self.http.timeout.read
            if self.deadline is not None:
                timeout = min(timeout, self.deadline - time.time())
                if timeout <= 0:
                    raise TimeoutError("Request deadline exhausted")
            response = self.http.post(self.path, json=self._wire(body), timeout=timeout)
            raw_text = response.text
            response.raise_for_status()
            raw = self.last_response = self._unwrap(response.json())
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
            result = S1Result(answers=answers, latency_ms=(time.monotonic() - started) * 1000, impl="onejev", degraded=False)
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"request": body, "response": raw,
                    "result": result.model_dump(mode="json")}, ensure_ascii=False), encoding="utf-8")
            ok = True
            return result
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = (time.monotonic() - started) * 1000
            if self.trace:
                self.trace("s1", caller=caller, model=self.model, cached=False, ok=ok, latency_ms=elapsed)
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


    def _wire(self, body):
        return body

    def _unwrap(self, raw):
        return raw

    def health(self):
        self.http.get("/health").raise_for_status()


class ClefClient(OneJevClient):
    """Cloudflare Workers AI `@cf/cloudflare/clef`: the same state-and-questions protocol behind the account REST API."""

    path = "/ai/run/@cf/cloudflare/clef"

    def __init__(self, account_id, token, model, meter, timeout_s=120, media_root=None):
        super().__init__(f"https://api.cloudflare.com/client/v4/accounts/{account_id}", model, meter, timeout_s, media_root=media_root)
        self.http.headers["Authorization"] = f"Bearer {token}"

    def _wire(self, body):
        # Cloudflare 收 images（内嵌 data URL），不收 media
        wire = {k: v for k, v in body.items() if k != "media"}
        if body["media"]:
            wire["images"] = [item["data"] for item in body["media"]]
        return wire

    def _unwrap(self, raw):
        if not raw.get("success"):
            raise ValueError(f"Cloudflare error: {raw.get('errors')}")
        return raw["result"]

    def health(self):
        pass   # 没有健康检查端点，首个请求即探测


class ClefWorkerClient(ClefClient):
    """用户 Worker 转发 Clef 原始 model/answers/usage，复用既有概率与计量协议。"""
    path = "/"

    def __init__(self, worker_url, meter, timeout_s=120):
        OneJevClient.__init__(self, worker_url, "clef", meter, timeout_s)

    def _unwrap(self, raw):
        if "model" not in raw or "answers" not in raw:
            raise ValueError("Worker 尚未返回 Clef 的 model/answers，请检查服务端是否使用 Clef 正式协议")
        return raw


class _FallbackProbabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers: dict[str, dict[str, float]]


class LLMSystem1Fallback:
    """Explicitly selected degraded System 1: the FAST-tier LLM returns probabilities via the gateway."""

    def __init__(self, gateway, meter):
        self.gateway, self.meter = gateway, meter

    def close(self):
        pass

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
    if cfg.get("kind") == "cloudflare_worker":
        base_url = os.environ[cfg["base_url_env"]] if "base_url_env" in cfg else cfg["base_url"]
        client = ClefWorkerClient(base_url, meter, cfg["timeout_s"])
    elif cfg.get("kind") == "cloudflare":
        client = ClefClient(os.environ[cfg["account_id_env"]], os.environ[cfg["api_key_env"]], cfg["model"], meter,
                            cfg["timeout_s"], media_root=cfg.get("media_root"))
    else:
        client = OneJevClient(cfg["base_url"], cfg["model"], meter, cfg["timeout_s"], cfg.get("gpu_price_per_hour"), media_root=cfg.get("media_root"))
    # 独立探测脚本传 gateway=None；离线网关也没有录制缓存。
    client.replay = getattr(gateway, "replay", False)
    cache = getattr(gateway, "cache_dir", None)
    client.cache_dir = Path(cache) / "s1" if cache else None
    if client.replay:
        return client
    try:
        client.health()
    except Exception:
        client.close()
        raise
    return client
