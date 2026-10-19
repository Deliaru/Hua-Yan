from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.agent.tools import TOOLS
from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit, PointsDraft, Question, ReqItem, Requirement, SheetDraft
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
    assert [x.id for x in app.questions("rd:R01") if x.family == "release"] == [q.id]
    assert any(x.family == "seal_leak" for x in app.questions("rd:R01"))
    assert not app.questions("rd:R02")
    with pytest.raises(PermissionDenied):
        app.mark_prepared(q.id, "rd:R01")
    prepared = app.mark_prepared(q.id, "pm:agent")
    assert prepared.prepared_at == get_clock().now() and prepared.status == "open"
    assert req.status == "rd_confirmed" and prepared.resolution is None
    assert app.events.query(["question_prepared"])[-1].actor == "pm:agent"

    # Q5 分层召回：客户层命中上层与「没找到」完全相同；L1、L2 只得本层，存根不带原文
    customer, sales = app.actors["customer:C01"], app.actors["sales:S01"]
    assert app.kb.explore("缓染 染座", customer) == app.kb.explore("无关查询", customer)
    for who in (sales, app.actors["pm:agent"]):
        found = app.kb.explore("缓染 染座", who)
        assert all(u.level <= (1 if who is sales else 2) for u in found.units) and found.stubs
        assert not any(t in found.model_dump_json() for t in l3_texts)
    # L1 两次问到一条 L3 结论却答不了 → 觉提出授予一句话 → 研发签字 → 回答说出这句话、不出现结论原文 → 撤销后回到「需要专业人员解答」
    claim = KnowledgeUnit(id=app.kb.next_claim_id(), kind="claim", level=3, title="（模拟）升温过快致色花",
        text="（模拟）锦纶氨纶升温过快会使匀染剂来不及缓染而色花", phenomenon_ids=["color_unlevel"],
        owner="rd:R01", confirmed_by="rd:R01", source="contributed", created_at=get_clock().now())
    app.kb.add(claim)
    ask = app.start_session("customer:C02", "sales:S01")
    for _ in range(2):
        app.add_turn(ask.id, "customer", "为什么升温快了就会色花？")
    assert app.view_session(ask.id, "sales:S01").replies[-1].text == "这部分需要专业人员解答。"
    app.scan()
    grant = next(q for q in app.questions("rd:R01") if q.object_id == f"knowledge:grant:{claim.id}|L1")
    assert any(e.quote == claim.text for e in grant.evidence)
    app.mark_prepared(grant.id, "rd:R01")
    with pytest.raises(ValueError):
        app.sign_qi_grant(grant.id, "rd:R01", note=claim.text)
    said = "（模拟）这和染色工艺的控制有关，可以安排技术人员上门看工艺。"
    statement = app.sign_qi_grant(grant.id, "rd:R01", note=said)
    reply = app.view_session(app.add_turn(ask.id, "customer", "为什么升温快了就会色花？").id, "sales:S01").replies[-1].text
    assert said in reply and claim.text not in reply
    assert app.events.query(["capability_used"])[-1].payload["capability_id"] == statement.id
    app.revoke_capability(statement.id, "rd:R01")
    app.add_turn(ask.id, "customer", "为什么升温快了就会色花？")
    assert app.view_session(ask.id, "sales:S01").replies[-1].text == "这部分需要专业人员解答。"
