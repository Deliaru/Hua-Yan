"""E6问题覆盖及假设来源回归，不模拟访谈、模型或效率成绩。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.eval.old_flow_preparation import prepare


def test_e6_questions_cover_defaults_without_turning_assumptions_into_overrides(tmp_path):
    defaults_path = Path("tests/fixtures/e6/synthetic-old-flow.yaml")
    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_old_flow_interview.py", "--defaults", str(defaults_path),
                    "--seeds", "tests/fixtures/mini_seeds", "--out", str(output)], check=True, capture_output=True)
    sheet = yaml.safe_load((output / "interview-template.yaml").read_text(encoding="utf-8"))
    rows = {row["field"]: row for row in sheet["questions"]}
    assert len(rows) == 16 and rows["minutes.back_round"]["default_value"] == defaults["minutes"]["back_round"]
    assert all(row["answer"] is None and row["respondent"] == "" for row in rows.values())
    assert sum(row["default_status"] == "假设" for row in rows.values()) == 15
    override = yaml.safe_load((output / "old-flow.override-template.yaml").read_text(encoding="utf-8"))
    # 对齐已读取消费方的扁平字段口径：没有数值覆盖，15个默认值继续保留假设身份。
    flat = lambda value: {f"minutes.{key}" for key in value["minutes"]} | (set(value) - {"source", "minutes"})
    assert override["source"] == "假设" and flat(override) == set()
    assert len(flat(defaults) - flat(override)) == 15
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["answered"] == summary["measured_parameters"] == 0
    assert summary["model_calls"] == 0 and summary["business_metrics"] is None
    questions = yaml.safe_load(Path("config/eval/e6-questions.yaml").read_text(encoding="utf-8"))
    questions["questions"].pop()
    incomplete = tmp_path / "questions.yaml"
    incomplete.write_text(yaml.safe_dump(questions, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="问题与默认字段不一致"):
        prepare(defaults_path, incomplete, tmp_path / "missing-question")
