"""E7合成输入准备回归，不调用或模拟模型响应。"""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from huayan.contracts import Injection, NeedCard, WeekItem
from huayan.eval.discovery_week import prepare
from huayan.eval.week import _build


def test_e7_existing_generator_preserves_spine_gold_and_end_boundary(tmp_path):
    dataset, output = tmp_path / "dataset", tmp_path / "out"
    subprocess.run([sys.executable, "scripts/prepare_discovery_week.py", "--seeds", "tests/fixtures/mini_seeds",
                    "--dataset", str(dataset), "--out", str(output)], check=True, capture_output=True)
    def load(part, filename, model):
        return [model.model_validate_json(line) for line in (dataset / part / filename).read_text(encoding="utf-8").splitlines()]
    full = load("full-week", "script.jsonl", WeekItem)
    selected = load("spine-week", "script.jsonl", WeekItem)
    cards = load("spine-week", "cards.jsonl", NeedCard)
    gold = load("spine-week", "injections.jsonl", Injection)
    assert len(selected) < len(full) and selected[-1] == full[-1]
    assert all(item in full for item in selected)
    assert {item.card_id for item in selected if item.kind == "session"} == {card.id for card in cards}
    assert (dataset / "full-week/injections.jsonl").read_bytes() == (dataset / "spine-week/injections.jsonl").read_bytes()
    assert len(gold) == 7 and sum(not inj.hard_negative for inj in gold) == 3
    annotations = json.loads((dataset / "annotations.json").read_text(encoding="utf-8"))
    assert {row["id"] for row in annotations} == {inj.id for inj in gold}
    assert all(row["kind"] == "合成" and row["split"] == "dev" for row in annotations)
    result = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert result["online_status"] == "not_run" and result["model_calls"] == 0 and result["detection"] is None
    before = (dataset / "annotations.json").read_bytes()
    with pytest.raises(ValueError, match="数据集或报告已存在"):
        prepare("tests/fixtures/mini_seeds", dataset, output)
    assert (dataset / "annotations.json").read_bytes() == before
    with pytest.raises(ValueError, match="不接受mock"):
        _build(str(tmp_path / "runs"), "bad-mock", "jue_proto", "config/app.yaml")
    protected = tmp_path / "existing-state.json"
    protected.write_text("不得覆盖", encoding="utf-8")
    config = tmp_path / "app.yaml"
    config.write_text(yaml.safe_dump({"gateway_mock": False, "system1_impl": "onejev", "extractor": "llm",
                                    "replay": False, "qi_state": str(protected)}), encoding="utf-8")
    with pytest.raises(ValueError, match="不能写入既有知识状态"):
        _build(str(tmp_path / "runs"), "bad-state", "jue_proto", config)
    assert protected.read_text(encoding="utf-8") == "不得覆盖"
