from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import PointsDraft, ReqItem, Requirement, SheetDraft
from huayan.knowledge import PermissionDenied


def test_pm_assistant_tools_respect_layers_and_confirmation(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), gateway_mock=True)
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    hub = app.agents
    pm = hub.context("pm:agent")
    l3_texts = [u.text for u in app.kb._units.values() if u.level == 3]

    # 越权检索只给归属人，读 L3 原文被拒；结果里没有任何 L3 原文
    found = hub.call_tool(pm, "search_knowledge", {"query": "匀染 缓染 染座"})
    denied = hub.call_tool(pm, "get_knowledge", {"ku_id": "ku:translation:tr:4"})
    assert any("rd:R01" in b for b in found.data["blocked"])
    assert not denied.ok
    assert not any(t in (found.model_dump_json() + denied.model_dump_json()) for t in l3_texts)

    # 需求单：pm:agent 看不到假设、封存项、两栏草稿；研发看得到
    session = app.start_session("customer:C01", "sales:S01")
    req = Requirement(id="req:1", question_id="q:1", session_ids=[session.id], phenomenon="color_unlevel",
        known_slots={}, assigned_rd="rd:R01", status="rd_confirmed", created_at=get_clock().now(),
        hypotheses=["（模拟）内部假设甲"], sealed=["（模拟）封存诀窍乙"],
        points_draft=PointsDraft(public="（模拟）待签要点丙", sealed=["（模拟）待签诀窍丁"]),
        chem_lang=[ReqItem(text="（模拟）化学条目", ku_refs=["ku:translation:tr:4"])])
    app._requirements[req.id] = req
    private = ["内部假设甲", "封存诀窍乙", "待签要点丙", "待签诀窍丁"]
    tool_view = hub.call_tool(pm, "get_requirement", {"req_id": req.id})
    assert not any(s in app.requirement_view(req.id, "pm:agent").model_dump_json() + tool_view.model_dump_json()
                   for s in private)
    assert app.requirement_view(req.id, "rd:R01").requirement.sealed == req.sealed

    # 说明书自查：三类来源各命中一次，只给句序号与类别
    l3_term = next(t.chem_term for t in app.seeds.translations if t.level == 3)
    req.sheet = SheetDraft(sheet=f"请先试样。{req.sealed[0]}", usage=f"{l3_term}；{req.hypotheses[0]}")
    assert [(h.index, h.source) for h in app.leak_check(req.id, "pm:agent")] == [
        (1, "sealed"), (2, "l3_term"), (3, "hypothesis")]

    # 生效类工具只挂起确认卡，确认前不改状态；非委托人不能确认（委托人确认后生效由 WP-C 删除 _hand_over 后补回）
    rd = hub.context("rd:R01")
    proposed = hub.call_tool(rd, "set_public_points", {"req_id": req.id, "text": "（模拟）低浴比下匀染好"})
    assert proposed.pending_action_id and not req.public_points
    with pytest.raises(PermissionDenied):
        hub.approve(proposed.pending_action_id, "rd:R02")
