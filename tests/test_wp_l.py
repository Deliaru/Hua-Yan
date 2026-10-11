from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ContributionDraft, PointsDraft, ReqItem, Requirement, SheetDraft
from huayan.knowledge import PermissionDenied


def test_pm_assistant_tools_respect_layers_and_confirmation(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), gateway_mock=True)
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    _check_requirement_privacy_and_leak_check(HuayanApp.build(str(path)))
    app = HuayanApp.build(str(path))
    hub = app.agents
    pm = hub.context("pm:P01")
    l3_texts = [u.text for u in app.kb._units.values() if u.level == 3]

    # 越权检索只给归属人，读 L3 原文被拒；结果里没有任何 L3 原文
    found = hub.call_tool(pm, "search_knowledge", {"query": "匀染 缓染 染座"})
    denied = hub.call_tool(pm, "get_knowledge", {"ku_id": "ku:translation:tr:4"})
    assert any("rd:R01" in b for b in found.data["blocked"])
    assert not denied.ok
    assert not any(t in (found.model_dump_json() + denied.model_dump_json()) for t in l3_texts)

    # 生效类工具只挂起确认卡；非委托人不能确认；委托人确认后才生效并派给研发
    session = app.add_turn(app.start_session("customer:C01", "sales:S01").id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    req = hub.call_tool(pm, "draft_product_need", {"question_id": session.recommendation.escalated_question_id}).data
    proposed = hub.call_tool(pm, "confirm_requirement", {"req_id": req["req_id"]})
    assert proposed.pending_action_id and app.requirement_view(req["req_id"], "pm:P01").requirement.status == "draft"
    with pytest.raises(PermissionDenied):
        hub.approve(proposed.pending_action_id, "rd:R01")
    assert hub.approve(proposed.pending_action_id, "pm:P01").result.ok
    assert app.requirement_view(req["req_id"], "pm:P01").requirement.status == "pm_confirmed"
    assert any(c.role == "rd" and "已确认需求单" in c.messages[0].text
               for actor in ("rd:R01", "rd:R02") for c in hub.conversations(actor))


def _check_requirement_privacy_and_leak_check(app):
    """手工研发阶段记录只验权限与自查，不替代签字、回流的端到端验收。"""
    session = app.start_session("customer:C01", "sales:S01")
    req = Requirement(id="req:privacy", question_id="q:privacy", session_ids=[session.id],
        phenomenon="color_unlevel", known_slots={}, assigned_rd="rd:R01", status="rd_confirmed",
        public_points="（模拟）请先做小样确认", created_at=get_clock().now(),
        hypotheses=["（模拟）内部假设甲"], sealed=["（模拟）封存诀窍乙"],
        points_draft=PointsDraft(public="（模拟）待签要点丙", sealed=["（模拟）待签诀窍丁"]),
        contribution_drafts=[ContributionDraft(item_index=0, scene_phrase="（模拟）待沉淀现象戊",
                                               chem_term="（模拟）待沉淀机理己")],
        chem_lang=[ReqItem(text="需研发确认的化学条目", ku_refs=["ku:translation:tr:4"])])
    app._requirements[req.id] = req
    app._save_requirement(req)
    safe_sheet = SheetDraft(sheet="（模拟）改善布面均匀性", usage="（模拟）先做小样")
    private = [*req.hypotheses, *req.sealed, req.points_draft.public, *req.points_draft.sealed,
               req.contribution_drafts[0].scene_phrase, req.contribution_drafts[0].chem_term]
    for viewer in ("pm:agent", "pm:P01"):
        view = app.requirement_view(req.id, viewer)
        saved = app.save_sheet(req.id, safe_sheet, viewer)
        copies = [view.requirement, saved, app.requirements(viewer)[0],
                  app.view_session(session.id, viewer).requirement]
        for copy in copies:
            assert not copy.hypotheses and not copy.sealed and copy.points_draft is None
            assert not copy.contribution_drafts
            assert not any(secret in copy.model_dump_json() for secret in private)
        assert view.cited[0].owner == "rd:R01" and view.cited[0].text is None
        result = app.agents.call_tool(app.agents.context(viewer), "get_requirement", {"req_id": req.id})
        assert result.ok and not any(secret in result.model_dump_json() for secret in private)
        assert result.data["cited"][0]["text"] is None
        saved.sealed.append("外部修改")
        saved.chem_lang[0].text = "外部修改"
        assert "外部修改" not in req.model_dump_json()
    supervisor = app.requirement_view(req.id, "supervisor:M01")
    assert supervisor.viewer_level == 2 and supervisor.cited[0].text is None
    assert not any(secret in supervisor.model_dump_json() for secret in private)
    for viewer in ("rd:R01", "rd:R02"):
        view = app.requirement_view(req.id, viewer)
        assert view.requirement == req and view.cited[0].text
    persisted = app.run_dir / "requirements/req_privacy.json"
    assert Requirement.model_validate_json(persisted.read_text(encoding="utf-8")) == req

    # 检查的是 sheet + usage，不是对 L2 裁剪后的来源，也不是 public_points 或草稿。
    assert app.leak_check(req.id, "pm:agent") == []
    l3_term = next(t.chem_term for t in app.seeds.translations if t.level == 3)
    req.sheet = SheetDraft(sheet=f"请先试样。{req.sealed[0]}",
                           usage=f"{l3_term}；{req.hypotheses[0]}")
    app._save_requirement(req)
    before = req.model_dump_json()
    files = {p: p.read_bytes() for p in app.run_dir.rglob("*") if p.is_file()}
    expected = [{"index": 1, "source": "sealed"}, {"index": 2, "source": "l3_term"},
                {"index": 3, "source": "hypothesis"}]
    for viewer in ("pm:agent", "pm:P01", "rd:R01", "supervisor:M01"):
        assert [h.model_dump() for h in app.leak_check(req.id, viewer)] == expected
    assert req.model_dump_json() == before
    assert {p: p.read_bytes() for p in app.run_dir.rglob("*") if p.is_file()} == files
    assert not app.events.query() and not app.bus.list(status=None) and not app.ledger.list()

    for viewer in ("sales:S01", "customer:C01", "unknown"):
        for read in (app.requirement_view, app.leak_check):
            with pytest.raises(PermissionDenied):
                read(req.id, viewer)
        with pytest.raises(PermissionDenied):
            app.requirements(viewer)
    req.sheet = None
    assert app.leak_check(req.id, "pm:agent") == []
    # 空说明书也不能绕过权限；不存在的需求单明确报错。
    with pytest.raises(PermissionDenied):
        app.leak_check(req.id, "sales:S01")
    with pytest.raises(ValueError):
        app.leak_check("req:missing", "pm:agent")
    for viewer in ("pm:agent", "rd:R01"):
        app.kb.freeze(viewer, "supervisor:M01", get_clock().now())
        for read in (app.requirement_view, app.leak_check):
            with pytest.raises(PermissionDenied):
                read(req.id, viewer)
        with pytest.raises(PermissionDenied):
            app.requirements(viewer)
