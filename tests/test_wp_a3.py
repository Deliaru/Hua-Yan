from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ReqItem, SheetDraft, Trial
from huayan.knowledge import PermissionDenied


def test_translation_release_and_ownership(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    req = app.escalate(session.id, "sales:S01")
    session = app.add_turn(session.id, "customer", "还要求不要APEO")
    app.save_reuse_proposal(req.id, None, [], "", "离线：未检索现成产品", "pm:agent")
    req = app.draft_requirement(req.id, "pm:agent")
    assert req.known_slots["constraint"] == "无APEO"
    rd = req.assigned_rd
    with pytest.raises(ValueError):
        app.edit_req_item(req.id, -1, ReqItem(text="伪造引用", quote_refs=["turn:missing"]), "pm:agent")
    with pytest.raises(ValueError):
        app.edit_req_item(req.id, -1, ReqItem(text="越权引用", ku_refs=["ku:translation:tr:4"]), "pm:agent")
    l3_term = next(t.chem_term for t in app.seeds.translations if t.level == 3)
    with pytest.raises(ValueError, match="研发术语"):
        app.return_requirement(req.id, l3_term, rd)
    returned = app.return_requirement(req.id, "请突出客户的无APEO要求", rd)
    assert returned.status == "draft" and returned.return_notes == ["请突出客户的无APEO要求"]
    app.draft_requirement(req.id, "pm:agent")
    app.accept_requirement(req.id, rd)
    req = app.translate_requirement(req.id, rd)
    first = req.chem_lang[0]
    app.edit_req_item(req.id, 0, first.model_copy(update={"text": first.text + "；验证低浴比稳定性"}), rd)
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）低浴比缓染稳定性", rd)
    req = app.confirm_translation(req.id, rd)
    assert req.product_id == "T-206"
    cited_owners = {e.owner for e in app.ledger.list() if e.reason == "cited"}
    assert {"rd:R01", "rd:R02"} <= cited_owners
    assert any(e.reason == "contributed" for e in app.ledger.list(rd))
    assert not any(e.owner in {"pm:agent", "jue"} for e in app.ledger.list())
    pm_view = app.requirement_view(req.id, "pm:agent")
    assert all(c.text is None for c in pm_view.cited if c.level == 3)
    assert not pm_view.requirement.hypotheses
    assert all(c.text is not None for c in app.requirement_view(req.id, "rd:R01").cited)
    with pytest.raises(PermissionDenied):
        app.requirement_view(req.id, "sales:S01")
    app.record_trial(Trial(id="trial:1", product_id=req.product_id, requirement_id=req.id, rd=rd,
        conditions=req.known_slots, result="pass", cause="none", at=get_clock().now()))
    app.record_market_eval(req.id, "pass", "（模拟）客户试用通过", "sales:S01")
    app.set_public_points(req.id, "（模拟）改善低浴比匀染；按工艺试样确认。", ["（模拟）分段吸附诀窍"], rd)
    sheet = app.package_sheet(req.id, "pm:agent")
    with pytest.raises(PermissionDenied):
        app.release_product(req.id, "pm:agent")
    with pytest.raises(PermissionDenied):
        app.release_product(req.id, "rd:R02")
    saved = app.save_sheet(req.id, SheetDraft(sheet=sheet.sheet, usage="（模拟）分段吸附诀窍"), "pm:agent")
    assert not saved.hypotheses and not saved.sealed and saved.points_draft is None
    with pytest.raises(ValueError, match="泄密"):
        app.release_product(req.id, rd)
    app.save_sheet(req.id, sheet, rd)
    app.release_product(req.id, rd)
    rewards = [e for e in app.ledger.list() if e.reason == "product_released"]
    assert len(rewards) == 1 and rewards[0].ku_id == "ku:sheet:T-206"
    row = next(r for r in app.contributions("pm:agent") if r.ku_id == "ku:sheet:T-206")
    assert row.points == app.config["points"]["product_released"]
    assert row.n_cited == 0 and row.used_by == ["T-206"]
    with pytest.raises(ValueError):
        app.release_product(req.id, rd)
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.recommendation.product_id == "T-206"

    # 复用支线：L1 适用表不匹配，研发审定历史案例建议后才给业务员说明与归属。
    reuse_session = app.start_session("customer:C03", "sales:S01")
    reuse_session = app.add_turn(reuse_session.id, "customer", "涤纶布手感发硬")
    assert reuse_session.recommendation is None
    reuse_req = app.escalate(reuse_session.id, "sales:S01")
    note = "（模拟）可用 HY-SF520 改善手感，按用法先做小样。"
    app.save_reuse_proposal(reuse_req.id, "HY-SF520", ["ku:case:case:reuse_softness"], note,
                            "参考 P01 的历史案例，待研发审定", "pm:agent")
    pending = app.view_session(reuse_session.id, "sales:S01")
    assert pending.reuse.status == "pending" and not pending.reuse.customer_note and not pending.reuse.basis
    assert pending.card is None and not pending.reuse.usage
    with pytest.raises(PermissionDenied):
        app.adopt_reuse(reuse_req.id, "sales:S01")
    adopted = app.adopt_reuse(reuse_req.id, reuse_req.assigned_rd)
    assert adopted.status == "recommended" and adopted.recommendation.product_id == "HY-SF520"
    assert app.requirement_view(reuse_req.id, reuse_req.assigned_rd).requirement.status == "reused"
    sales_view = app.view_session(reuse_session.id, "sales:S01")
    assert sales_view.reuse.customer_note == note and sales_view.reuse.usage
    assert "审定" in sales_view.card.note and "pm:P01" in sales_view.reuse.basis[0]
    case_text = app.kb.get("ku:case:case:reuse_softness", app.actors["pm:agent"]).text
    assert case_text not in sales_view.model_dump_json()
    assert len([e for e in app.ledger.list("pm:P01") if e.ref == reuse_req.id and e.reason == "cited"]) == 1
    assert not any(e.payload["requirement_id"] == reuse_req.id for e in app.events.query(["requirement_accepted"]))
