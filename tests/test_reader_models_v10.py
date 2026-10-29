"""合成资料；守住旧 Worker 把调用失败当成证据否定的实际问题。"""
import json

import httpx
import pytest

from huayan.ingest.reader.verify import ClefWorkerClient, JevVerifier
from huayan.meter import FileMeter


def test_worker_uses_clef_probabilities_and_meter(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "clef" and "question" not in body
        assert body["questions"]["evidence_gate"]["type"] == "noul"
        return httpx.Response(200, json={"model": "clef", "usage": {"input_tokens": 18},
                                       "answers": {"evidence_gate": {"type": "noul", "noul": 0.82}}})

    client = ClefWorkerClient("https://example.invalid", FileMeter(tmp_path, "synthetic"))
    client.http.close()
    client.http = httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler))
    try:
        result = JevVerifier(client).verify_evidence_gate("合成资料：A组80℃保温10min。", "A组保温温度？")
        assert result["probabilities"] == pytest.approx({"yes": 0.82, "no": 0.18})
        assert result["passed"] and result["impl"] == "onejev" and not result["degraded"]
        meter = json.loads((tmp_path / "metering.jsonl").read_text(encoding="utf-8"))
        assert meter["model"] == "clef" and meter["caller"] == "jev:grounding" and meter["ok"]
    finally:
        client.close()


@pytest.mark.parametrize("status,body,error", [(200, {"result": False}, ValueError),
                                               (502, {"error": "upstream failed"}, httpx.HTTPStatusError)])
def test_worker_failure_is_not_negative_evidence(tmp_path, status, body, error):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body)

    client = ClefWorkerClient("https://example.invalid", FileMeter(tmp_path, "synthetic"))
    client.http.close()
    client.http = httpx.Client(base_url="https://example.invalid", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(error):
            JevVerifier(client).verify_evidence_gate("合成资料", "合成问题")
        assert len(calls) == 1
        meter = json.loads((tmp_path / "metering.jsonl").read_text(encoding="utf-8"))
        assert not meter["ok"]
    finally:
        client.close()
