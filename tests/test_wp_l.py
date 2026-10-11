from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.agent.tools import TOOLS
from huayan.clock import get_clock
from huayan.contracts import PointsDraft, Question, ReqItem, Requirement, SheetDraft
from huayan.knowledge import PermissionDenied


def test_pm_assistant_tools_respect_layers_and_confirmation(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), gateway_mock=True)
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    hub = app.agents
    pm = hub.context("pm:agent")
    assert all(spec.kind != "effect" for spec, _ in TOOLS.values() if "pm" in spec.roles)
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

    # 两栏草稿自查不生效；签字提议确认前不改状态，非委托人不能确认。
    rd = hub.context("rd:R01")
    points_before = app.ledger.list()
    contribution = hub.call_tool(rd, "save_contribution_draft", {"req_id": req.id, "index": 0,
        "scene_phrase": "（模拟）低浴比下色差", "chem_term": "（模拟）分阶段调节吸附速率", "note": "已去掉客户特定信息"})
    assert contribution.ok and contribution.data["contribution_drafts"][0]["item_index"] == 0
    assert app.ledger.list() == points_before and not app.events.query(["knowledge_contributed"])
    assert hub.call_tool(pm, "get_requirement", {"req_id": req.id}).data["contribution_drafts"] == []
    pending = hub.call_tool(rd, "contribute_translation", {"req_id": req.id, "index": 0,
        "scene_phrase": "（模拟）低浴比下色差", "chem_term": "（模拟）分阶段调节吸附速率"})
    assert pending.pending_action_id and not app.events.query(["knowledge_contributed"])
    draft = hub.call_tool(rd, "save_points_draft", {"req_id": req.id, "public": req.sealed[0], "sealed": req.sealed})
    assert draft.ok and draft.data["points_draft"]["self_check"] == [{"index": 0, "source": "sealed"}]
    assert not req.public_points and not app.events.query(["points_set"])
    proposed = hub.call_tool(rd, "set_public_points", {
        "req_id": req.id, "text": "（模拟）低浴比下匀染好", "sealed": req.sealed})
    assert proposed.pending_action_id and not req.public_points
    with pytest.raises(PermissionDenied):
        hub.approve(proposed.pending_action_id, "rd:R02")

    # 手工待处理问题只验准备权限：主人准备，签字人查看；准备不等于签字。
    q = app.bus.publish(Question(id="", family="release", template_id="release", title="审定发布",
        object_id=f"requirement:{req.id}", owner_role="pm", owner_id="pm:agent",
        signer_role="rd", signer_id="rd:R01", scored_by="rule", discoverer="jue_proto",
        dedup_key=f"release:{req.id}", created_at=get_clock().now()))
    assert [x.id for x in app.questions("pm:agent")] == [q.id]
    assert [x.id for x in app.questions("rd:R01")] == [q.id]
    assert not app.questions("rd:R02")
    with pytest.raises(PermissionDenied):
        app.mark_prepared(q.id, "rd:R01")
    prepared = app.mark_prepared(q.id, "pm:agent")
    assert prepared.prepared_at == get_clock().now() and prepared.status == "open"
    assert req.status == "rd_confirmed" and prepared.resolution is None
    assert app.events.query(["question_prepared"])[-1].actor == "pm:agent"
