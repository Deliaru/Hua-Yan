"""合成资料：统一入口读取原文，内部查证不等于对外能力。"""
import json
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import Capability, KnowledgeUnit
from huayan.ingest.folder import FolderSource
from huayan.knowledge import PermissionDenied
from huayan.ui import server


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
