"""V11.1：一件事的前情——按时间排列、标明主体，按查看者层级裁剪。"""
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied


@pytest.fixture
def app(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return HuayanApp.build(str(path))


def test_self_service_story(app):
    sid = app.start_session("customer:C01", "sales:S01").id
    app.add_turn(sid, "customer", "深一块浅一块")
    app.add_turn(sid, "customer", "锦氨的，溢流缸")
    story = app.case_story(sid, "customer:C01")["story"]
    assert story[0] == {**story[0], "subject": "human", "role": "customer", "who": "customer:C01"}
    assert "深一块浅一块" in story[0]["text"]
    assert any(x["subject"] == "jue" and "需要向客户问清" in x["text"] for x in story)
    assert any(x["subject"] == "jev" and x["text"].startswith("推荐") for x in story)
    assert any(x["subject"] == "qi" for x in story)
    assert [x["ts"] for x in story] == sorted(x["ts"] for x in story)


def test_escalated_story_is_trimmed_by_level(app):
    sid = app.start_session("customer:C02", "sales:S01").id
    app.add_turn(sid, "customer", "深一块浅一块，锦氨的，气流缸")
    app.tick()
    req = app.escalate(sid, "sales:S01")
    app.tick()
    rd = req.assigned_rd

    inner = app.case_story(req.id, rd)
    assert inner["session_id"] == sid and inner["requirement_id"] == req.id
    kinds = [x["kind"] for x in inner["story"]]
    assert {"escalate", "requirement_created", "reuse_proposed", "question_prepared"} <= set(kinds)
    assert next(x for x in inner["story"] if x["kind"] == "escalate")["who"] == "sales:S01"
    assert any(x["subject"] == "agent" and x["who"] == "pm:agent" for x in inner["story"])
    assert any(w["family"] == "accept_requirement" and w["signer_id"] == rd for w in inner["waiting"])

    outer = app.case_story(sid, "sales:S01")     # L1：只看会话上的经过和自己经手的决策
    assert not {"reuse_proposed", "requirement_edited"} & {x["kind"] for x in outer["story"]}
    assert all(x["who"] != "pm:agent" for x in outer["story"])
    assert not outer["waiting"]
    with pytest.raises(PermissionDenied):
        app.case_story(sid, "customer:C03")
