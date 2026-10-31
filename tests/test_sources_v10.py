"""合成资料：统一入口读取原文，内部查证不等于对外能力。"""
from base64 import b64decode
import hashlib
from io import BytesIO
import json
from pathlib import Path

from PIL import Image
import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import Capability, KnowledgeUnit, LLMResponse, LLMToolCall, Tier, Usage
from huayan.ingest.folder import FolderSource
from huayan.ingest.reader.trials import build_trial_record
from huayan.ingest.reader.word import read_docx, read_native_labels
from huayan.knowledge import PermissionDenied
from huayan.ui import server


class _ImageTurn:
    """离线脚本只核对真实工具及多模态消息传递，不判断模型读图质量。"""
    def __init__(self, doc_id):
        self.doc_id, self.requests = doc_id, []

    def complete(self, req):
        self.requests.append(req.model_copy(deep=True))
        calls = [LLMToolCall(call_id="image", name="read_source_image", arguments={
            "doc_id": self.doc_id, "page": 1, "span": "table-2"}),
            LLMToolCall(call_id="text", name="read_source", arguments={"doc_id": self.doc_id, "span": "table-2"})]
        return LLMResponse(content="（脚本化）本轮图像传递核对，非专业结论。",
            tool_calls=calls if len(self.requests) == 1 else [], usage=Usage(input_tokens=0, output_tokens=0),
            latency_ms=0, model="scripted-image-transport", tier=Tier.FAST, cost=None)


def test_trial_record_readback_preserves_groups_and_rejects_changed_evidence(tmp_path, monkeypatch):
    path = Path("tests/fixtures/reader/synthetic.docx")
    doc_id = "synthetic-conditions"
    source = {"source_id": doc_id, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "source": "internal", "level": 3}
    pages = json.loads(Path("tests/fixtures/reader/pages.json").read_text(encoding="utf-8"))
    blocks = read_docx(path, source, pages, ["synthetic-page-1.png"])
    image_path = tmp_path / "synthetic-page.png"
    image = Image.new("RGB", (20, 20), "red")
    image.paste("green", (10, 0, 20, 20))
    image.save(image_path)
    next(b for b in blocks if b.span == "table-2").locations[0].bbox = (10, 0, 20, 20)
    readings, pending = read_native_labels(blocks)
    record = build_trial_record(blocks, readings, pending)
    trial_path = tmp_path / "trial-record.json"
    trial_path.write_text(record.model_dump_json(), encoding="utf-8")
    evidence = {"source_id": doc_id, "file_sha256": source["sha256"], "images": [str(image_path)],
                "blocks": [b.model_dump() for b in blocks], "fragments": [b.fragment().model_dump() for b in blocks]}
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"),
        source_manifest="tests/fixtures/reader/source-manifest.json", source_trials={doc_id: str(trial_path)},
        sources=[{"name": "合成报告", "kind": "internal", "root": str(evidence_path)}])
    config_path = tmp_path / "app.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(config_path))
    params = {"doc_id": doc_id, "viewer": "rd:R01"}
    before = app.kb.state_path.read_bytes()
    page = server.GET["/api/sources/image"](app, params | {"page": "1"})
    assert page["kind"] == "page" and page["bbox"] is None and page["level"] == 3
    assert b64decode(page["image_url"].split(",", 1)[1]) == image_path.read_bytes()
    region = server.GET["/api/sources/image"](app, params | {"page": "1", "span": "table-2"})
    assert region["kind"] == "region" and region["bbox"] == (10, 0, 20, 20)
    assert (region["width"], region["height"]) == (10, 20) and region["fingerprint"] != page["fingerprint"]
    with Image.open(BytesIO(b64decode(region["image_url"].split(",", 1)[1]))) as cropped:
        assert cropped.getpixel((0, 0)) == (0, 128, 0)
    assert all("path" not in key for key in region)
    whole = app.read_source_image(doc_id, 1, "rd:R01", "table-1")
    assert whole["kind"] == "page" and whole["bbox"] is None
    fetched = server.GET["/api/sources/trial"](app, params)
    assert fetched == record and fetched.status == "draft" and fetched.professional_confirmation is None
    a, b = fetched.groups
    assert a.formula[0].name == "SYNTH-A" and b.formula[0].name == "SYNTH-B"
    assert a.formula[0].unit is None and b.formula[0].unit == "kg"
    assert [r.conditions for r in a.curve_labels if r.stage == "保温"] == [["85℃"]]
    assert [r.conditions for r in b.curve_labels if r.stage == "保温"] == [["95℃"]]
    assert fetched.pending == pending and fetched.time.a is None and fetched.time.b is None
    assert "path" not in json.dumps(fetched.model_dump(mode="json"))
    tool = app.agents.call_tool(app.agents.context("rd:R01"), "read_trial_record", {"doc_id": doc_id})
    assert tool.ok and tool.data["groups"][0]["formula"][0]["name"] == "SYNTH-A"
    assert tool.data["groups"][1]["formula"][0]["unit"] == "kg" and tool.data["pending"] == pending
    assert "file_sha256" not in tool.data and "professional_confirmation" not in tool.data
    denied = app.agents.call_tool(app.agents.context("pm:agent"), "read_trial_record", {"doc_id": doc_id})
    assert not denied.ok and "无权读取" in denied.error and not app.agents.pending("rd:R01")
    # 一次响应含多个工具时，所有tool回复先齐备，再将真正图片送给下一轮网关。
    gateway = _ImageTurn(doc_id)
    app.gateway, app.config["gateway_mock"] = gateway, False
    conv = app.agents.chat("rd:R01", "（合成）请回看table-2第1页的已登记区域。")
    request = gateway.requests[1]
    assert request.caller == "agent:rd"
    assert [m.role for m in request.messages[-3:]] == ["tool", "tool", "user"]
    metadata = json.loads(request.messages[-3].content)["data"]
    assert metadata["kind"] == "region" and metadata["span"] == "table-2" and "image_url" not in metadata
    text, picture = request.messages[-1].content
    assert text.type == "text" and doc_id in text.text
    assert picture.type == "image_url" and picture.image_url.url == region["image_url"]
    assert all("data:image" not in row.result_summary for row in app.agents.trace(conv.id))
    app.agents.chat("rd:R01", "（合成）结束本次查看。")
    assert all(isinstance(m.content, str) for m in gateway.requests[-1].messages)
    assert "data:image" not in conv.model_dump_json() and not app.agents.pending("rd:R01")
    denied_gateway = _ImageTurn(doc_id)
    app.gateway = denied_gateway
    app.agents.chat("pm:agent", "（合成）请求内部图像，应由原入口拒绝。")
    rejected = denied_gateway.requests[1]
    assert all(isinstance(m.content, str) for m in rejected.messages)
    assert all(not json.loads(m.content)["ok"] for m in rejected.messages if m.role == "tool")
    monkeypatch.setattr(server, "trial_roles", {"sales-session": "sales:S01"})
    bound = server.trial_params("sales-session", "GET", "/api/sources/trial", params)
    with pytest.raises(PermissionDenied):
        server.GET["/api/sources/trial"](app, bound)
    image_bound = server.trial_params("sales-session", "GET", "/api/sources/image", params | {"page": "1"})
    with pytest.raises(PermissionDenied):
        server.GET["/api/sources/image"](app, image_bound)
    # 外部记录的错误来源标注不改变统一入口确定的密级。
    trial_path.write_text(record.model_copy(update={"level": 0, "source": "public"}).model_dump_json(), encoding="utf-8")
    fetched = app.read_trial_record(doc_id, "rd:R01")
    assert fetched.level == 3 and fetched.source == "internal"
    trial_path.write_text(record.model_copy(update={"file_sha256": "old"}).model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="来源不一致"):
        app.read_trial_record(doc_id, "rd:R01")
    trial_path.write_text(record.model_dump_json(), encoding="utf-8")
    fragment = app.kb.sources[0].fragments["table-2"]
    app.kb.sources[0].fragments["table-2"] = fragment.model_copy(update={"fingerprint": "changed"})
    with pytest.raises(ValueError, match="依据已变化"):
        app.read_trial_record(doc_id, "rd:R01")
    assert app.kb.state_path.read_bytes() == before and not app.events.query(["claim_confirmed"])


def test_source_entry_uses_manifest_owner_and_existing_permissions(tmp_path, monkeypatch):
    doc_id = "synthetic-conditions"
    source = FolderSource("合成内部资料", "internal", "tests/fixtures/reader")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"source_id": doc_id, "file_sha256": "synthetic",
        "fragments": [f.model_dump() for f in source.fetch(doc_id)]}), encoding="utf-8")
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"),
        source_manifest="tests/fixtures/reader/source-manifest.json",
        sources=[{"name": "合成内部资料", "kind": "internal", "root": str(evidence)},
                 {"name": "公开资料", "kind": "public", "root": "seeds/rag/public"}])
    config_path = tmp_path / "app.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(config_path))
    params = {"doc_id": doc_id, "viewer": "rd:R01", "span": "p1"}
    read = server.GET["/api/sources/read"](app, params)
    assert read == source.fetch(doc_id)[:1]
    assert set(read[0].model_dump()) == {"doc_id", "span", "text", "level", "source", "fingerprint"}
    for viewer in ["rd:R02", "pm:agent", "sales:S01", "customer:C01"]:
        with pytest.raises(PermissionDenied):
            server.GET["/api/sources/read"](app, params | {"viewer": viewer})
    # HTTP 仍使用服务器会话认定主体，请求中的 viewer 不能借用研发身份。
    monkeypatch.setattr(server, "trial_roles", {"sales-session": "sales:S01"})
    bound = server.trial_params("sales-session", "GET", "/api/sources/read", params)
    with pytest.raises(PermissionDenied):
        server.GET["/api/sources/read"](app, bound)
    public_id = app.kb.sources[1].list_docs()[0]
    assert all(f.level == 0 and f.source == "public" for f in app.read_source(public_id, "pm:agent"))
    assert app.read_source(public_id, "customer:C01")
    app.source_owners[doc_id] = None
    with pytest.raises(ValueError, match="尚未指定归属人"):
        app.read_source(doc_id, "rd:R01")
    app.source_owners[doc_id] = "rd:R01"

    # 只承认整份来源的 report 授权；结论分享不隐含整份原始报告的分享。
    unit = KnowledgeUnit(id=f"ku:report:{doc_id}", kind="report", level=3, title="合成来源",
        text="合成来源归属记录", owner="rd:R01", confirmed_by="rd:R01", created_at=get_clock().now())
    app.kb.add(unit)
    claim = unit.model_copy(update={"id": "ku:claim:1", "kind": "claim", "evidence": [
        f"{doc_id}#p1@{read[0].fingerprint}"]})
    app.kb.add(claim)
    app.kb.grant(Capability(id=app.kb.next_cap_id(), form="share", audience="rd:R02",
        payload={"ku_id": claim.id}, based_on=[claim.id], granted_by="rd:R01", status="active", at=get_clock().now()))
    with pytest.raises(PermissionDenied):
        app.read_source(doc_id, "rd:R02", "p1")
    app.kb.grant(Capability(id=app.kb.next_cap_id(), form="share", audience="rd:R02",
        payload={"ku_id": unit.id}, based_on=[unit.id], granted_by="rd:R01", status="active", at=get_clock().now()))
    assert app.read_source(doc_id, "rd:R02", "p1") == read
    app.kb.sources[0] = source
    assert app.read_source(doc_id, "rd:R01", "p1") == read
    assert not app.events.query(["claim_confirmed"])
