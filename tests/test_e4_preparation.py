"""E4合成准备回归；真实文件/CLI检查，不调用或模拟模型。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.eval.reuse import prepare


def test_e4_snapshot_links_roundtrip_and_unselected_labels(tmp_path):
    raw = yaml.safe_load(Path("tests/fixtures/e4/synthetic-pairs.yaml").read_text(encoding="utf-8"))
    state_path = Path(raw["knowledge_state"])
    before = state_path.read_bytes()
    raw["pairs"][-1]["expected"] = "heldout-label-not-for-development"
    pairs = tmp_path / "pairs.yaml"
    pairs.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_reuse_pairs.py", "--pairs", str(pairs),
                    "--seeds", "tests/fixtures/mini_seeds", "--out", str(output)], check=True, capture_output=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["selected"] == 2 and summary["not_selected"] == 1
    assert summary["draft_labels"] == 2 and summary["filled_labels"] == 0
    assert summary["model_calls"] == 0 and summary["business_metrics"] is None
    rows = json.loads((output / "details.json").read_text(encoding="utf-8"))
    assert all(row["limits"] == "合成限制：指定流程须人工核对" for row in rows)
    assert all(row["capability"]["status"] == "proposed" for row in rows)
    assert "heldout-label-not-for-development" not in (output / "report.md").read_text(encoding="utf-8")
    prepare(output / "pairs.json", tmp_path / "roundtrip", seeds_dir="tests/fixtures/mini_seeds")
    assert json.loads((tmp_path / "roundtrip/pairs.json").read_text(encoding="utf-8")) == json.loads(
        (output / "pairs.json").read_text(encoding="utf-8"))
    assert state_path.read_bytes() == before
    raw["pairs"][0]["capability_id"] = "cap:SYN-B"
    pairs.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="关联该判断的applicable能力"):
        prepare(pairs, tmp_path / "wrong-link")
    raw["pairs"][0]["capability_id"] = "cap:SYN-A"
    raw["knowledge_state_sha256"] = "0" * 64
    pairs.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="知识状态快照指纹不符"):
        prepare(pairs, tmp_path / "wrong-state")
