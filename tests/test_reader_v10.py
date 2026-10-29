import base64
import hashlib
import json
from pathlib import Path

import httpx
import openai

from huayan.gateway.client import OpenAICompatGateway
from huayan.ingest.reader.image import read_image
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


def test_image_gateway_serializes_bytes_and_reuses_only_same_image(tmp_path):
    sent = []

    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "synthetic-response", "object": "chat.completion", "created": 0,
            "model": "synthetic-vision", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": '{"text":"合成图片读稿","pending":[]}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}})

    client = openai.OpenAI(api_key="synthetic-key", base_url="https://gateway.invalid/v1",
                          http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    gateway = OpenAICompatGateway({"tiers": {"strong": {"model": "synthetic-vision", "fallbacks": [],
        "price_per_1k": {"input": None, "output": None}}}}, clients={"strong": client},
        cache_dir=tmp_path / "cache", meter=FileMeter(tmp_path, "synthetic-reader"))
    image = tmp_path / "input.png"
    # 合成传输字节：HTTP 替身不做图片解码，此测试只检验请求序列化与缓存隔离。
    image.write_bytes(b"synthetic-image-A")
    first, response = read_image(image, "合成上下文", gateway)
    repeated, _ = read_image(image, "合成上下文", gateway)
    image.write_bytes(b"synthetic-image-B")
    read_image(image, "合成上下文", gateway)
    assert first.text == repeated.text == "合成图片读稿" and response.model == "synthetic-vision"
    assert len(sent) == 2
    content = sent[0]["messages"][-1]["content"]
    assert content[0] == {"type": "text", "text": "合成上下文"}
    assert base64.b64decode(content[1]["image_url"]["url"].split(",", 1)[1]) == b"synthetic-image-A"
    assert sent[0]["response_format"] == {"type": "json_object"}
    records = [json.loads(line) for line in (tmp_path / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(row["caller"] == "ingest:extract" and row["input_tokens"] == 12 for row in records)
