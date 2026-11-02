"""真实CLI生成/回读E2静态标注文件，不调用或模拟模型。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.eval.routing import PATHS, prepare


def test_e2_form_roundtrip_preserves_e1_and_unselected_answers(tmp_path):
    cases = Path("tests/fixtures/e1/synthetic-cases.yaml")
    before = cases.read_bytes()
    raw = yaml.safe_load(Path("tests/fixtures/e2/synthetic-labels.yaml").read_text(encoding="utf-8"))
    raw["labels"][-1]["expected_path"] = "heldout-path-not-for-development"
    labels = tmp_path / "labels.yaml"
    labels.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "prepared"
    subprocess.run([sys.executable, "scripts/prepare_routing.py", "--cases", str(cases), "--labels", str(labels),
                    "--seeds", "tests/fixtures/mini_seeds", "--out", str(output)], check=True, capture_output=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    rows = json.loads((output / "details.json").read_text(encoding="utf-8"))
    assert summary["selected_cases"] == 4 and summary["not_selected_cases"] == 2
    assert summary["label_rows"] == 5 and summary["draft_labels"] == 5 and summary["filled_labels"] == 0
    assert summary["business_metrics"] is None and summary["model_calls"] == 0
    assert summary["paths"] == PATHS
    assert len([row for row in rows if row["case"]["id"] == "SYN-E1-001"]) == 2
    form = (output / "annotation-form.html").read_text(encoding="utf-8")
    assert "collectLabels" in form and "未标注（不要猜）" in form
    assert "heldout-path-not-for-development" not in form
    imported = prepare(cases, "tests/fixtures/mini_seeds", tmp_path / "roundtrip", output / "annotations.json")
    assert imported["label_rows"] == 5 and imported["filled_labels"] == 0
    assert cases.read_bytes() == before
    raw["labels"][0]["case_id"] = "nonexistent-case"
    labels.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="E1样本不存在"):
        prepare(cases, "tests/fixtures/mini_seeds", tmp_path / "rejected", labels)


@pytest.mark.parametrize("occupied_ids", [
    ["E2-SYN-E1-002"],
    ["E2-SYN-E1-002", "E2-SYN-E1-002-2"],
])
def test_e2_generated_ids_avoid_imported_ids_and_roundtrip(tmp_path, occupied_ids):
    cases = Path("tests/fixtures/e1/synthetic-cases.yaml")
    raw = yaml.safe_load(Path("tests/fixtures/e2/synthetic-labels.yaml").read_text(encoding="utf-8"))
    raw["labels"] = [{"id": label_id, "case_id": "SYN-E1-001"} for label_id in occupied_ids]
    labels = tmp_path / "colliding-labels.yaml"
    labels.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    output = tmp_path / "prepared"
    prepare(cases, "tests/fixtures/mini_seeds", output, labels)
    exported = json.loads((output / "annotations.json").read_text(encoding="utf-8"))
    ids = [label["id"] for label in exported["labels"]]
    assert len(ids) == len(set(ids))
    assert [label["id"] for label in exported["labels"] if label["case_id"] == "SYN-E1-001"] == occupied_ids
    imported = prepare(cases, "tests/fixtures/mini_seeds", tmp_path / "roundtrip", output / "annotations.json")
    assert imported["label_rows"] == len(occupied_ids) + 3
    assert json.loads((tmp_path / "roundtrip/annotations.json").read_text(encoding="utf-8")) == exported
