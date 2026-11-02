"""合成标注文件走真实CLI；不调用或模拟任何模型。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.eval.e1 import prepare


def test_e1_preparation_cli_keeps_sources_and_heldout_separate(tmp_path):
    fixture = Path("tests/fixtures/e1/synthetic-cases.yaml")
    payload = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    # 默认dev检查不应验证或导出heldout答案。
    payload["cases"][-1]["final_conditions"] = "heldout-answer-not-for-development"
    cases = tmp_path / "cases.yaml"
    cases.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "report"
    subprocess.run([sys.executable, "scripts/backtest_cases.py", "--prepare", "--cases", str(cases),
                    "--seeds", "tests/fixtures/mini_seeds", "--out", str(output)], check=True, capture_output=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    rows = json.loads((output / "details.json").read_text(encoding="utf-8"))
    assert summary["selected"] == 4 and summary["not_selected"] == 2
    assert summary["counts"]["合成"] == {"dev": 4, "heldout": 2}
    assert summary["vocabulary_gap_count"] == 1
    assert rows[0]["annotation"]["unknown"] == ["temperature_c"]
    assert rows[1]["annotation"]["temperature_c"] == [72, 78]
    assert rows[1]["annotation"]["late_conditions"] == ["equipment"]
    assert "溢流缸" not in rows[1]["annotation"]["first_words"]
    assert rows[1]["annotation"]["turns"] == ["设备是溢流缸。"]
    assert rows[2]["annotation"]["tags"] == ["否定", "纠正"]
    assert rows[2]["annotation"]["late_conditions"] == []
    assert rows[3]["annotation"]["final_conditions"]["equipment"] == "合成专用设备X"
    assert "heldout-answer-not-for-development" not in (output / "details.json").read_text(encoding="utf-8")
    assert summary["model_calls"] == 0 and summary["business_metrics"] is None
    assert summary["zero_tolerance_findings"] is None
    assert "合成专用设备X" in (output / "vocab_gaps.md").read_text(encoding="utf-8")
    # 同一原始来源的两条样本不能分到不同分区。
    payload["cases"][-1]["source_group"] = "synthetic-basic"
    cases.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="同一来源跨dev/heldout"):
        prepare(cases, "tests/fixtures/mini_seeds", tmp_path / "rejected")
