"""E8合成变更输入准备，不模拟模型响应。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest

from huayan.eval.source_changes import prepare


def test_e8_changes_prepare_roundtrip_without_touching_sources(tmp_path):
    source = Path("tests/fixtures/e8/synthetic-source.txt")
    before = source.read_bytes()
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_source_changes.py", "--out", str(output)], check=True, capture_output=True)
    changes = json.loads((output / "changes.json").read_text(encoding="utf-8"))["changes"]
    assert len(changes) == 4 and sum(bool(c["expected_affected"]) for c in changes) == 2
    assert {c["review_action"] for c in changes} == {"none", "restore", "replace"}
    assert next(c for c in changes if c["type"] == "whitespace_format")["after"].startswith("  ")
    summary = prepare(output / "changes.json", tmp_path / "roundtrip")
    assert summary["status"] == "not_run" and summary["model_calls"] == 0
    assert json.loads((tmp_path / "roundtrip/changes.json").read_text(encoding="utf-8"))["changes"] == changes
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match="输出目录已存在"):
        prepare(output / "changes.json", output)
