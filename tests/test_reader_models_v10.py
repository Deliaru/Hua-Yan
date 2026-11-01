"""合成资料；守住旧 Worker 把调用失败当成证据否定的实际问题。"""
import json

import httpx
import pytest

from huayan.ingest.reader.verify import ClefWorkerClient, JevVerifier
from huayan.meter import FileMeter
from huayan.gateway.mock import MockGateway
from huayan.ingest.reader.chart_qa import answer_chart, table_context


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


def test_chart_answer_uses_native_cells_and_marks_unlocatable_model_values():
    page = {"source_id": "SYNTH-CHART", "page": 2, "table_layout": {},
        "blocks": [{"span": "synthetic-title", "text": "合成标题不是表格定位", "cells": []},
            {"span": "table-1", "text": "合成表：润湿\t4.2\tS", "cells": [
            {"row": 1, "column": 1, "text": "润湿（S）"}, {"row": 1, "column": 2, "text": "SYNTH-X"},
            {"row": 2, "column": 1, "text": "0.3%"}, {"row": 2, "column": 2, "text": "NaOH20g/L"},
            {"row": 3, "column": 1, "text": "润湿"}, {"row": 3, "column": 2, "text": "4.2"}]}],
        "fragments": [{"span": "table-1", "text": "合成表：润湿\t4.2\tS"}]}
    raw = {"values": [{"span": "table-1", "object": "SYNTH-X", "metric": "润湿时间", "value": "4.2",
        "conditions": ["0.3%", "NaOH20g/L"]}], "pending": []}
    requests = []

    def respond(schema, request):
        requests.append(request)
        return raw

    gateway = MockGateway(canned={"ingest:extract": respond})
    answer, _ = answer_chart("合成图表问题", page, "data:image/png;base64,synthetic", gateway)
    assert answer.values[0].value == "4.2" and answer.values[0].unit == "S"
    assert answer.values[0].conditions == ["0.3%", "NaOH20g/L"] and not answer.pending
    assert answer.values[0].metric == "润湿" and answer.values[0].cell == (3, 2)
    assert answer.values[0].quote == "4.2"
    assert requests[0].messages[-1].content[-1].text == "合成图表问题"
    context = json.loads(requests[0].messages[-1].content[0].text)
    assert [b["span"] for b in context["blocks"]] == ["table-1"]
    assert context["page_context"] == ["合成标题不是表格定位"]
    raw["values"][0]["value"] = "9.99"
    changed, _ = answer_chart("合成图表问题", page, "data:image/png;base64,synthetic", gateway)
    assert not changed.values and any("没有唯一" in note for note in changed.pending)


def test_chart_context_keeps_merged_product_dosage_and_row_headers():
    cells = [(1, 1, "指标（S）", 2, 2), (1, 3, "SYNTH-X", 1, 2),
             (2, 3, "0.2%", 1, 1), (2, 4, "0.4%", 1, 1),
             (3, 1, "合成条件A", 2, 1), (3, 2, "润湿", 1, 1),
             (3, 3, "3.1", 1, 1), (3, 4, "4.2", 1, 1),
             (4, 2, "沉降", 1, 1), (4, 3, "5.3", 1, 1), (4, 4, "6.4", 1, 1)]
    block = {"span": "synthetic-table", "text": "合成表格", "cells": [
        {"row": r, "column": c, "text": t} for r, c, t, _, _ in cells]}
    layout = [{"row": r, "column": c, "row_span": rs, "column_span": cs} for r, c, _, rs, cs in cells]
    result = table_context(block, layout)
    selected = next(row for row in result["native_records"] if row["cell"] == [4, 4])
    assert selected == {"cell": [4, 4], "value": "6.4", "column_headers": ["SYNTH-X", "0.4%"],
                        "row_headers": ["合成条件A", "沉降"]}
    assert result["unit_header_raw"] == "指标（S）"
    raw = {"values": [{"span": block["span"], "object": "模型把标题当作对象", "metric": "沉降时间",
                       "value": "6.4", "conditions": []}], "pending": []}
    requests = []

    def respond(schema, request):
        requests.append(request)
        return raw

    page = {"source_id": "SYNTH-MERGED", "page": 1, "blocks": [block], "table_layout": {block["span"]: layout}}
    answer, _ = answer_chart("合成查证", page, "unused-image", MockGateway(canned={"ingest:extract": respond}))
    assert answer.method == "native_table_selection" and answer.values[0].object == "SYNTH-X"
    assert answer.values[0].conditions == ["SYNTH-X", "0.4%", "合成条件A", "沉降"]
    assert all(part.type == "text" for part in requests[0].messages[-1].content)
