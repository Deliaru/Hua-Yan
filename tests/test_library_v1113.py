"""V11.13 合成资料库：检索只在委托人能读的来源里做，读不到的连编号都不出现；命中指针可回取原文。"""
import json
from pathlib import Path

from PIL import Image
import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied


def test_search_sources_only_in_readable_and_pointer_reads_back(tmp_path):
    root = tmp_path / "library"
    (root / "docs").mkdir(parents=True)
    docs = {"trial-1": ("internal", "rd:R02", ["试样目的：涤纶汽流染色色花", "133℃保温30min，匀染剂 TF-213HE 用量 1g/L，色花改善"]),
            "sheet-1": ("public", None, ["TF-213HE 分散匀染剂 说明书：适用于涤纶高温染色"])}
    for doc_id, (_, _, pages) in docs.items():
        images = [str(root / f"{doc_id}-{n}.jpg") for n in range(1, len(pages) + 1)]
        for path in images:
            Image.new("RGB", (8, 8), "white").save(path)
        (root / "docs" / f"{doc_id}.json").write_text(json.dumps({"doc_id": doc_id, "pages": pages, "images": images}), encoding="utf-8")
    (root / "sources.json").write_text(json.dumps({"sources": [
        {"source_id": d, "kind": k, "owner_actor_id": o, "title": f"{d}.doc"} for d, (k, o, _) in docs.items()]}), encoding="utf-8")
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), sources=[
        {"name": "资料库（内部）", "kind": "internal", "root": str(root), "library": True},
        {"name": "资料库（公开）", "kind": "public", "root": str(root), "library": True}])
    (tmp_path / "app.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(tmp_path / "app.yaml"))

    query = "涤纶汽流染色机上用 TF-213HE，133℃ 出现色花"
    owner = app.search_sources(query, "rd:R02")
    assert {h["doc_id"] for h in owner["hits"]} == {"trial-1", "sheet-1"}
    assert all(h["method"] == "keyword" for h in owner["hits"]) and "只用了关键词" in owner["note"]
    hit = next(h for h in owner["hits"] if h["doc_id"] == "trial-1" and h["page"] == 2)
    doc_id, rest = hit["pointer"].split("#", 1)
    span, fingerprint = rest.split("@")
    assert app.read_source(doc_id, "rd:R02", span)[0].fingerprint == fingerprint
    page = app.read_source_image(doc_id, 2, "rd:R02", span)       # 整页图，同一统一入口
    assert page["kind"] == "page" and page["level"] == 3 and page["image_url"].startswith("data:image/jpeg")
    with pytest.raises(PermissionDenied):
        app.read_source_image(doc_id, 2, "rd:R01")

    for other in ("rd:R01", "sales:S01"):          # 同事未分享、业务员 L1：内部报告连编号都不出现
        assert {h["doc_id"] for h in app.search_sources(query, other)["hits"]} == {"sheet-1"}
