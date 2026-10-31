import base64
import hashlib
import json
from pathlib import Path

import httpx
import openai

from huayan.gateway.client import OpenAICompatGateway
from huayan.ingest.reader.image import read_image
from huayan.ingest.reader.evidence import EvidenceBlock
from huayan.ingest.reader.trials import build_trial_record
from huayan.ingest.reader.summary import summarize_trials
from huayan.ingest.reader.word import read_docx, read_native_labels
from huayan.meter import FileMeter

FIXTURE = Path(__file__).parent / "fixtures/reader"


def test_native_report_groups_units_and_merged_curve():
    source = {"source_id": "SYNTH-REPORT", "sha256": hashlib.sha256((FIXTURE / "synthetic.docx").read_bytes()).hexdigest(),
              "source": "internal", "level": 3}
    pages = json.loads((FIXTURE / "pages.json").read_text(encoding="utf-8"))
    blocks = read_docx(FIXTURE / "synthetic.docx", source, pages, ["synthetic-page-1.png"])
    readings, pending = read_native_labels(blocks)
    holds = [(r.group, r.value, r.conditions) for r in readings if r.stage == "保温"]
    assert holds == [("A", "12", ["85℃"]), ("B", "6", ["95℃"])]
    for group, quote in [("A", "85℃*12min"), ("B", "95℃*6min")]:
        table = next(block for block in blocks if block.kind == "table" and block.group == group)
        assert table.text.count(quote) == 1
        assert table.fragment().text.count(quote) == 1
    assert [(r.value, r.status) for r in readings if r.unit == "℃/min"] == [("0..7", "needs_reading"), ("1.2", "native")]
    assert any("table-1 r2c2" in note and "未写单位" in note for note in pending)
    assert not any("table-2" in note and "未写单位" in note for note in pending)
    assert next(r for r in readings if r.value == "90").group is None
    textbox = next(b for b in blocks if b.kind == "textbox")
    assert textbox.text == "合成文本框 30℃" and textbox.locations[0].page == 1
    record = build_trial_record(blocks, readings, pending)
    a, b = record.groups
    assert [(x.name, x.value, x.unit) for x in a.formula] == [("SYNTH-A", "7", None)]
    assert [(x.name, x.value, x.unit) for x in b.formula] == [("SYNTH-B", "2", "kg")]
    assert [r.conditions for r in a.curve_labels if r.stage == "保温"] == [["85℃"]]
    assert [r.conditions for r in b.curve_labels if r.stage == "保温"] == [["95℃"]]
    assert a.formula[0].evidence[1].cell == (2, 2)
    assert record.time.a is None and record.time.b is None  # 未标组别的总时间90min不回填A/B。
    # 配方和曲线只存在于表格引用中，也必须可筛选并进入导出文本。
    entries = [(Path("synthetic/trial-record.json"), record)]
    sources = {record.source_id: source | {"title": "合成原生报告", "products": ["SYNTH-PRODUCT"]}}
    for condition in ("SYNTH-A", "85℃*12min"):
        row, = summarize_trials(entries, sources, condition=condition)["rows"]
        assert condition in row["condition_text"]
        assert "A组配方/曲线依据" in row["condition_text"]
        assert "SYNTH-REPORT#table-1@" in row["condition_text"]
        assert "单元格(2, 2)" in row["condition_text"]


def test_text_recipe_keeps_unknown_amount_subprocesses_and_result_basis():
    rows = json.loads((FIXTURE / "synthetic-text-recipe.json").read_text(encoding="utf-8"))
    blocks = [EvidenceBlock(source_id="SYNTH-TEXT", file_sha256="synthetic", level=3, source="internal",
                            kind="paragraph", **row) for row in rows]
    record = build_trial_record(blocks, [], [])
    a, b = record.groups
    assert [(x.name, x.value, x.unit) for x in a.formula] == [
        ("SYNTH-DYE", "X", None), ("SYNTH-ACID", "0.4", "g/L"), ("SYNTH-OLD", "0.3", "%")]
    assert [(x.name, x.value, x.unit) for x in b.formula] == [
        ("SYNTH-DYE", "X", None), ("SYNTH-ACID", "0.4", "g/L"), ("SYNTH-NEW", "0.8", "g/L")]
    assert a.formula[0].evidence[0].quote == rows[1]["text"]
    assert a.formula[0].evidence[0].fragment.startswith("SYNTH-TEXT#p2@")
    assert a.formula[-1].basis is None and any("百分比基准" in note for note in record.pending)
    assert sum("具体数值及单位待补" in note for note in record.pending) == 2
    assert rows[4]["text"] in [x.text for x in a.operations]
    assert rows[8]["text"] not in [x.text for x in a.operations]
    assert [x.text for x in record.quality] == [rows[10]["text"]]
    assert record.reported_results[-1].text == rows[-1]["text"]
    assert record.time.calculated_saving is None and record.time.reported_saving is None
    assert record.professional_confirmation is None


def test_negative_report_keeps_fabric_columns_curve_groups_and_missing_outcomes():
    path = FIXTURE / "synthetic-negative.docx"
    source = {"source_id": "SYNTH-NEGATIVE", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "source": "internal", "level": 3}
    pages = {f"paragraph-{n}": [1] for n in range(1, 9)} | {"table-1": [1]}
    blocks = read_docx(path, source, pages, ["synthetic-page.png"])
    readings, pending = read_native_labels(blocks)
    assert [(r.group, r.value) for r in readings if r.stage == "保温"] == [("A", "7"), ("B", "7")]
    assert [(r.group, r.value) for r in readings if r.unit == "℃/min"] == [("A", "0.5"), ("B", "0.8")]
    assert [(r.group, r.value) for r in readings if r.unit == "℃"] == [("A", "40-50"), ("B", "40-50")]
    record = build_trial_record(blocks, readings, pending)
    assert [g.formula for g in record.groups] == [[], []]  # 两种织物列不是原/试样两套配方。
    assert "合成甲染色配方" in record.groups[0].formula_notes[0].text
    assert "合成乙染色配方" in record.groups[0].formula_notes[0].text
    assert record.groups[1].formula_notes == []
    assert record.quality[0].text == "1、合成甲布面合格，合成乙布面出现色花，不合格。"
    assert record.quality[0].evidence[0].span == "paragraph-6"
    assert "操作警告" in record.reported_results[1].text
    assert "已取合成乙" in record.follow_up[0].text
    assert record.cost == [] and record.time.calculated_saving is None
    assert record.time.a is None and record.time.b is None
    assert any("多织物配方表" in note for note in record.pending)


def test_trial_summary_deduplicates_preserves_mixed_results_and_time_denominator():
    records = []
    for name in ("synthetic-summary-time.json", "synthetic-text-recipe.json"):
        path = FIXTURE / name
        source = {"source_id": name, "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "level": 3, "source": "internal", "kind": "paragraph"}
        blocks = [EvidenceBlock(**source, **row) for row in json.loads(path.read_text(encoding="utf-8"))]
        records.append(build_trial_record(blocks, [], []))
    path = FIXTURE / "synthetic-negative.docx"
    source = {"source_id": "SYNTH-NEGATIVE", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "level": 3, "source": "internal"}
    blocks = read_docx(path, source, {f"paragraph-{n}": [1] for n in range(1, 9)} | {"table-1": [1]}, ["synthetic.png"])
    readings, pending = read_native_labels(blocks)
    records.append(build_trial_record(blocks, readings, pending))
    sources = {r.source_id: {"sha256": r.file_sha256, "title": "合成测试报告", "products": ["SYNTH-PRODUCT"]} for r in records}
    entries = [(Path(f"synthetic/{r.source_id}/trial-record.json"), r) for r in records]
    entries.append((Path("synthetic/duplicate/trial-record.json"), records[-1]))
    summary = summarize_trials(entries, sources, product="SYNTH-PRODUCT")
    assert summary["input_count"] == 4 and summary["unique_input_reports"] == summary["matched_reports"] == 3
    assert len(summary["duplicate_inputs"]) == 1
    assert summary["paired_time_reports"] == 1 and summary["paired_time_source_ids"] == [records[0].source_id]
    assert summary["rows"][0]["record"]["time"]["calculated_saving"] == "20"
    assert summary["rows"][1]["record"]["time"]["calculated_saving"] is None
    negative = summarize_trials(entries, sources, product="SYNTH-PRODUCT", condition="合成乙", result="不合格")
    row, = negative["rows"]
    assert "合成甲布面合格" in row["result_text"] and "合成乙布面出现色花，不合格" in row["result_text"]
    assert row["record"]["quality"][0]["evidence"][0]["fragment"].startswith("SYNTH-NEGATIVE#")
    assert row["record"]["cost"] == [] and negative["paired_time_reports"] == 0
    assert summarize_trials(entries, sources, product="UNKNOWN")["matched_reports"] == 0


def test_image_gateway_keeps_readings_and_caches_by_image_and_model(tmp_path):
    sent, waits, traces = [], [], []
    readout = {"text": "合成图片读稿", "readings": [
        {"object": "合成布样", "group": "A", "stage": "保温", "value": "12", "unit": "min",
         "conditions": ["85℃"], "position": "上部原工艺横线", "quote": "85℃*12min"},
        {"object": "合成布样", "group": "B", "stage": "保温", "value": "6", "unit": "min",
         "conditions": ["95℃"], "position": "下部试样工艺横线", "quote": "95℃*6min"},
        {"object": "未标注阶段", "group": "A", "stage": None, "value": None, "unit": None,
         "conditions": [], "position": "未读清的曲线起点", "quote": None}], "pending": []}

    def handle(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {"message": "synthetic rate limit"}})
        return httpx.Response(200, json={"id": "synthetic-response", "object": "chat.completion", "created": 0,
            "model": sent[-1]["model"], "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "synthetic reasoning</think>" + json.dumps(readout, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

    client = openai.OpenAI(api_key="synthetic-key", base_url="https://gateway.invalid/v1", max_retries=0,
                          http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    gateway = OpenAICompatGateway({"concurrency": 1, "retry_waits": [7], "tiers": {"strong": {"model": "synthetic-vision", "fallbacks": [],
        "price_per_1k": {"input": None, "output": None}}}}, clients={"strong": client},
        cache_dir=tmp_path / "cache", meter=FileMeter(tmp_path, "synthetic-reader"), sleep=waits.append,
        trace=lambda event, **fields: traces.append({"event": event, **fields}))
    image = tmp_path / "input.png"
    # 合成传输字节：HTTP 替身不做图片解码，此测试只检验请求序列化与缓存隔离。
    image.write_bytes(b"synthetic-image-A")
    first, response = read_image(image, "合成上下文", gateway)
    repeated, _ = read_image(image, "合成上下文", gateway)
    image.write_bytes(b"synthetic-image-B")
    read_image(image, "合成上下文", gateway)
    assert first.text == repeated.text == "合成图片读稿" and response.model == "synthetic-vision"
    assert len(sent) == 3 and waits == [2]
    assert any(t["event"] == "llm" and t["cached"] for t in traces)
    assert [(r.group, r.value, r.unit, r.conditions) for r in repeated.readings[:2]] == [
        ("A", "12", "min", ["85℃"]), ("B", "6", "min", ["95℃"])]
    assert repeated.readings[-1].quote is None and any("未读清" in note for note in repeated.pending)
    gateway.tiers["strong"]["model"] = "synthetic-vision-v2"
    _, updated_response = read_image(image, "合成上下文", gateway)
    assert len(sent) == 4 and updated_response.model == "synthetic-vision-v2"
    content = sent[0]["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "合成上下文"}
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == b"synthetic-image-A"
    assert sent[0]["response_format"] == {"type": "json_object"}
    records = [json.loads(line) for line in (tmp_path / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(row["caller"] == "ingest:extract" for row in records)
    assert sum(not row["ok"] for row in records) == 1
    assert all(row["input_tokens"] == 12 for row in records if row["ok"])
