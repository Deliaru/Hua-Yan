"""BYOK（评委自带密钥）：用试用者在界面上填的大模型与 OneJev 接口组装网关和 Jev 的 System 1。
密钥只存在本会话的内存里：不写配置、不写运行目录、不回显到界面；会话淘汰或服务重启即丢弃。
接口地址由服务器代为请求，只允许公网地址（防止借演示服务器访问本机与内网）。"""
import ipaddress
import json
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
import openai

from huayan.gateway.client import OpenAICompatGateway
from huayan.jev.system1 import LLMSystem1Fallback, OneJevClient


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"接口地址要以 http:// 或 https:// 开头：{url}")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"解析不到域名：{parsed.hostname}") from None
    if not all(ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise ValueError("接口地址不能指向本机或内网（演示服务器只代为访问公网地址）")
    return url.rstrip("/")


@dataclass
class Byok:
    llm_base_url: str
    llm_model: str
    llm_key: str = field(repr=False)
    jev_base_url: str | None = None            # 不填 = 不接 Jev，Jev 走大模型降级
    jev_model: str = "OneJev-9B"
    jev_key: str | None = field(default=None, repr=False)
    jev_fallback: bool = True                  # OneJev 调用失败时降级到大模型（结果标 llm_fallback）

    @property
    def system1_impl(self):
        return "onejev" if self.jev_base_url else "llm_fallback"

    def gateway(self, meter):
        tier = {"base_url": self.llm_base_url, "model": self.llm_model, "api_key_env": None,
                "fallbacks": []}
        client = openai.OpenAI(base_url=self.llm_base_url, api_key=self.llm_key, max_retries=0)
        names = ("fast", "strong", "backup")
        return OpenAICompatGateway({"tiers": {n: tier for n in names}}, meter=meter, clients={n: client for n in names})

    def system1(self, gateway, meter):
        fallback = LLMSystem1Fallback(gateway, meter)
        if not self.jev_base_url:
            return fallback
        client = self.onejev(meter)
        return OneJevOrLLM(client, fallback) if self.jev_fallback else client

    def onejev(self, meter):
        client = OneJevClient(self.jev_base_url, self.jev_model, meter, timeout_s=120)
        if self.jev_key:
            client.http.headers["Authorization"] = f"Bearer {self.jev_key}"
        return client

    def check(self):
        """填完先体检：对话不通当场报错；JSON 输出、工具调用不支持时照常接入，但逐项告诉试用者会影响哪一环。"""
        client = openai.OpenAI(base_url=self.llm_base_url, api_key=self.llm_key, max_retries=0)

        def ask(text, **kw):
            return client.chat.completions.create(model=self.llm_model, messages=[{"role": "user", "content": text}],
                                                  max_tokens=1024, timeout=60, **kw).choices[0].message

        try:
            ask("ping")
        except openai.APIError as e:
            raise ValueError(f"大模型连接失败：{type(e).__name__}: {e}") from None
        probes = [{"item": "对话", "ok": True, "affects": "L1 回答客户、Agent 起草的正文", "detail": ""}]
        try:
            text = ask('只输出 JSON：{"ok": true}', response_format={"type": "json_object"}).content or ""
            json.loads(text.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
            probes.append({"item": "JSON 输出", "ok": True, "affects": "听懂客户原话（抽取）、Jev 推荐", "detail": ""})
        except (openai.APIError, ValueError) as e:
            probes.append({"item": "JSON 输出", "ok": False, "affects": "听懂客户原话（抽取）、Jev 推荐", "detail": f"{type(e).__name__}: {e}"[:200]})
        tool = {"type": "function", "function": {"name": "ping", "description": "连通测试",
                "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}}}
        try:
            calls = ask("调用 ping 工具，参数 x 填 1。", tools=[tool]).tool_calls
            probes.append({"item": "工具调用", "ok": bool(calls), "affects": "产品经理 / 研发 Agent 起草需求单、准备待签事项",
                           "detail": "" if calls else "模型没有调用工具"})
        except openai.APIError as e:
            probes.append({"item": "工具调用", "ok": False, "affects": "产品经理 / 研发 Agent 起草需求单、准备待签事项",
                           "detail": f"{type(e).__name__}: {e}"[:200]})
        if self.jev_base_url:
            client = self.onejev(None)
            try:
                client.http.get("/health", timeout=15).raise_for_status()
            except httpx.HTTPError as e:
                raise ValueError(f"OneJev 连接失败：{type(e).__name__}: {e}") from None
            finally:
                client.close()
        return probes


class OneJevOrLLM:
    """OneJev 优先；调用失败时降级到大模型，结果的 impl 为 llm_fallback、degraded 为真（铁律 6）。"""

    def __init__(self, onejev, fallback):
        self.onejev, self.fallback = onejev, fallback

    def ask(self, state, media, questions, caller):
        try:
            return self.onejev.ask(state, media, questions, caller)
        except (httpx.HTTPError, ValueError, TimeoutError) as e:
            print(f"[byok] OneJev 失败，降级到大模型：{type(e).__name__}")
            return self.fallback.ask(state, media, questions, caller)

    def close(self):
        self.onejev.close()
