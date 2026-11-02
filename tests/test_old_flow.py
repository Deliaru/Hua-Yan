"""V11.2：旧流程推算——按实际路径推算旧流程；转述不丢条件时不再出现补问和返工（CEO-VIEW C2 完成标准）。"""
import random
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.domain import load_seeds
from huayan.eval.old_flow import card_loss, estimate, load_params
from huayan.sim.cards import make_cards


def _app(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return HuayanApp.build(str(path))


def test_paths(tmp_path):
    app, params = _app(tmp_path), load_params(override=tmp_path / "none.yaml")
    sid = app.start_session("customer:C01", "sales:S01").id
    app.add_turn(sid, "customer", "深一块浅一块，锦氨的，溢流缸")
    own = estimate(app.route_of(sid, "sales:S01"), params)
    assert own["path"] == "自助解决" and "研发" not in own["old"]["roles"] and own["now"]["roles"] == []

    sid = app.start_session("customer:C02", "sales:S01").id
    app.add_turn(sid, "customer", "深一块浅一块，锦氨的，气流缸")
    app.tick()
    req = app.escalate(sid, "sales:S01")
    rd = estimate(app.route_of(req.id, req.assigned_rd), params)
    assert rd["old"]["roles"] == ["业务员", "产品经理", "研发"] and rd["old"]["backs"] > 0 and rd["old"]["reworks"] > 0
    assert rd["old"]["work_hours"] > own["old"]["work_hours"] and rd["source"] == "推算"
    assert estimate(app.route_of(req.id, req.assigned_rd), params, cases=2)["old"]["work_hours"] == pytest.approx(2 * rd["old"]["work_hours"], abs=0.01)


def test_lossless_relay_has_no_rework(tmp_path):
    seeds = load_seeds("tests/fixtures/mini_seeds")
    cards = make_cards(seeds, 20, random.Random(7))
    route = {"path": "入研", "roles": {}, "n_human_steps": 0}
    params = load_params(override=tmp_path / "none.yaml")
    lossless = {"habit_slots": [s.id for s in seeds.slots], "vague_prob": 0, "drop_prob": 0, "swap_prob": 0}
    for card in cards:
        old = estimate(route, params, loss=card_loss(card, seeds, lossless, 1))["old"]
        assert old["backs"] == old["reworks"] == 0 and old["lost"] == []
    noisy = yaml.safe_load(Path("config/eval/distortion.yaml").read_text(encoding="utf-8"))["relay"]
    assert any(estimate(route, params, loss=card_loss(c, seeds, noisy, 1))["old"]["lost"] for c in cards)


def test_given_params_override_assumptions(tmp_path):
    given = tmp_path / "old_flow.yaml"
    given.write_text("source: 传化研发估计\nminutes: {pm_relay: 90}\nwait_hours: 8\n", encoding="utf-8")
    params = load_params(override=given)
    assert params["minutes"]["pm_relay"] == 90 and params["source"] == "传化研发估计"
    assert "minutes.pm_relay" not in params["assumed"] and "wait_hours" not in params["assumed"]
    assert "minutes.rd_review" in params["assumed"]
