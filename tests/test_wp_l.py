from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied


def test_pm_assistant_tools_respect_layers_and_confirmation(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), gateway_mock=True)
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
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
