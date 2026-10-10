from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied
from huayan.contracts import CustomerProfile, ExtractedSlot, ExtractionResult
from huayan.l1.extract import validate_extraction


def test_l1_recommend_and_escalate(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    assert {h.slot for h in session.hints} == {"fiber", "equipment"}
    session = app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    assert session.recommendation.product_id == "T-205"
    assert app.view_session(session.id, "sales:S01").card.version == "product_usage"
    assert any(s.ku_id == "ku:formula:T-205" for s in app.view_session(session.id, "rd:R01").card.sections)
    with pytest.raises(PermissionDenied):
        app.view_session(session.id, "sales:S02")
    totals = app.ledger.totals()
    app.recommend_now(session.id)
    assert app.ledger.totals() == totals
    app.add_turn(session.id, "customer", "这个产品的配方和机理是什么？")
    reply = app.view_session(session.id, "sales:S01").replies[-1]
    assert reply.blocked and not reply.ku_ids
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.status == "escalated"
    assert app.bus.list(family="escalate_need")[0].refs["session_id"] == other.id
    unknown = app.start_session("customer:C03", "sales:S01")
    app.add_turn(unknown.id, "customer", "深一块浅一块，锦纶氨纶的")
    app.add_turn(unknown.id, "sales", "请问用的是什么染色设备？")
    unknown = app.add_turn(unknown.id, "customer", "这个不清楚")
    assert unknown.need.slots["equipment"].status == "unknown"
    assert unknown.need.asked["equipment"] == 1
    assert not unknown.hints
    assert (app.run_dir / "sessions/sess_1.json").exists()
    assert app.status().realtime_model == "required_stub"
    bad = ExtractionResult(intent="need", phenomenon="color_unlevel", profile=CustomerProfile(), slots=[
        ExtractedSlot(slot="fiber", value="虚构面料", status="filled", confidence=0.9,
                      quote="锦纶氨纶", turn_n=2)])
    assert not validate_extraction(bad, app.seeds, session.turns).slots
    bad.slots[0].value, bad.slots[0].quote = "棉", "客户并未说过的原话"
    with pytest.raises(ValueError):
        validate_extraction(bad, app.seeds, session.turns)
