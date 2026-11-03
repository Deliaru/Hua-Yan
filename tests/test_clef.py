"""V9.0：Jev 经 Cloudflare clef 打分。离线用 MockTransport 核对请求形状与响应外层。"""

import json

import httpx
import pytest

from huayan.contracts import S1Choice, S1Noul, S1Score
from huayan.jev.system1 import ClefClient


class _Meter:
    def record(self, **kw):
        self.last = kw


def _client(handler, model="clef"):
    client = ClefClient("acc", "tok", model, _Meter())
    client.http.close()
    client.http = httpx.Client(base_url=client.http.base_url, headers=client.http.headers, transport=httpx.MockTransport(handler))
    return client


@pytest.mark.parametrize("model", ["clef", "clef-flash"])
def test_clef_request_and_envelope(model):
    seen = {}

    def handler(request):
        seen["url"], seen["auth"], seen["body"] = str(request.url), request.headers["authorization"], json.loads(request.content)
        assert seen["body"]["model"] == model
        return httpx.Response(200, json={"success": True, "errors": [], "result": {"model": model, "usage": {"input_tokens": 9}, "answers": {
            "a": {"type": "noul", "noul": 0.8},
            "b": {"type": "choice", "choice": "x", "probabilities": {"x": 0.9, "y": 0.1}, "confidence": 0.8},
            "c": {"type": "score", "score": 1.0, "legend": {"0": "低", "1": "高"}, "probabilities": {"0": 0.25, "1": 0.75}}}}})

    result = _client(handler, model).ask({"t": "s"}, [], {"a": S1Noul(text="?"), "b": S1Choice(text="?", options={"x": "X", "y": "Y"}),
                                                   "c": S1Score(text="?", levels=["低", "高"])}, "test:clef")
    assert seen["url"] == f"https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/cloudflare/{model}"
    assert seen["auth"] == "Bearer tok" and "media" not in seen["body"] and "images" not in seen["body"]
    assert result.answers["a"].probabilities["yes"] == pytest.approx(0.8)
    assert result.answers["b"].probabilities == pytest.approx({"x": 0.9, "y": 0.1})
    assert result.answers["c"].probabilities == pytest.approx({"低": 0.25, "高": 0.75}) and result.answers["c"].expected == pytest.approx(0.75)


def test_clef_error_raises():
    client = _client(lambda request: httpx.Response(200, json={"success": False, "errors": [{"message": "Unsupported model"}], "result": {}}))
    with pytest.raises(ValueError, match="Unsupported model"):
        client.ask({}, [], {"a": S1Noul(text="?")}, "test:clef")
