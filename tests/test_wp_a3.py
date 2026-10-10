from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ReqItem, Trial
from huayan.knowledge import PermissionDenied


def test_translation_release_and_ownership(tmp_path):
    pytest.importorskip("huayan.escalation.translate", reason="等待 B 线 WP-T 转译引擎集成")
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    req = app.draft_requirement(session.recommendation.escalated_question_id, "pm:P01")
    with pytest.raises(ValueError):
        app.edit_req_item(req.id, -1, ReqItem(text="伪造引用", quote_refs=["turn:missing"]), "pm:P01")
    with pytest.raises(ValueError):
        app.edit_req_item(req.id, -1, ReqItem(text="越权引用", ku_refs=["ku:translation:tr:4"]), "pm:P01")
    app.confirm_requirement(req.id, "pm:P01")
    req = app.translate_requirement(req.id, "rd:R02")
    first = req.chem_lang[0]
    app.edit_req_item(req.id, 0, first.model_copy(update={"text": first.text + "；验证低浴比稳定性"}), "rd:R02")
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）低浴比缓染稳定性", "rd:R02")
    req = app.confirm_translation(req.id, "rd:R02")
    assert req.product_id == "T-206"
    cited_owners = {e.owner for e in app.ledger.list() if e.reason == "cited"}
    assert {"rd:R01", "rd:R02"} <= cited_owners
    assert any(e.reason == "contributed" for e in app.ledger.list("rd:R02"))
    pm_view = app.requirement_view(req.id, "pm:P01")
    assert all(c.text is None for c in pm_view.cited if c.level == 3)
    assert not pm_view.requirement.hypotheses
    assert all(c.text is not None for c in app.requirement_view(req.id, "rd:R01").cited)
    with pytest.raises(PermissionDenied):
        app.requirement_view(req.id, "sales:S01")
    app.set_public_points(req.id, "（模拟）改善低浴比匀染；按工艺试样确认。", "rd:R02")
    app.package_sheet(req.id, "pm:P01")
    with pytest.raises(ValueError):
        app.release_product(req.id, "pm:P01")
    app.record_trial(Trial(id="trial:1", product_id=req.product_id, requirement_id=req.id, rd="rd:R02",
        conditions=req.known_slots, result="pass", cause="none", at=get_clock().now()))
    app.release_product(req.id, "pm:P01")
    with pytest.raises(ValueError):
        app.release_product(req.id, "pm:P01")
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.recommendation.product_id == "T-206"
