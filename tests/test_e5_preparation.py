"""E5草稿CLI流转检查，不调用或模拟模型。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.eval.leak import prepare


def test_e5_prompt_roundtrip_preserves_roles_turns_and_unselected_labels(tmp_path):
    raw = yaml.safe_load(Path("tests/fixtures/e5/synthetic-prompts.yaml").read_text(encoding="utf-8"))
    raw["prompts"][-1]["forbidden"] = "heldout-label-not-for-development"
    prompts = tmp_path / "prompts.yaml"
    prompts.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_leak_prompts.py", "--prompts", str(prompts),
                    "--seeds", "tests/fixtures/mini_seeds", "--out", str(output)], check=True, capture_output=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["selected"] == 2 and summary["not_selected"] == 1
    assert summary["filled_labels"] == 0 and summary["draft_labels"] == 2
    assert summary["multi_turn_cases"] == 1 and summary["model_calls"] == 0
    assert summary["business_metrics"] is None and summary["zero_tolerance_findings"] is None
    rows = json.loads((output / "details.json").read_text(encoding="utf-8"))
    assert rows[0]["sample"]["role"] == "customer" and rows[0]["planned_level"] == 0
    assert rows[0]["sample"]["turns"] == raw["prompts"][0]["turns"]
    assert rows[1]["sample"]["role"] == "sales" and rows[1]["planned_level"] == 1
    assert "heldout-label-not-for-development" not in (output / "report.md").read_text(encoding="utf-8")
    prepare(output / "prompts.json", tmp_path / "roundtrip", seeds_dir="tests/fixtures/mini_seeds")
    assert (output / "prompts.json").read_bytes() == (tmp_path / "roundtrip/prompts.json").read_bytes()
    raw["prompts"][0]["surface"] = "sales_agent"
    prompts.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="拟观察出口与绑定角色不一致"):
        prepare(prompts, tmp_path / "wrong-surface")
