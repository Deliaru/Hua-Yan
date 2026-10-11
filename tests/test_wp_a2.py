from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import Requirement
from huayan.knowledge import PermissionDenied


def test_l1_recommend_and_escalate(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))

    # 追问 → 推荐，写 match 事件；L1 与 L3 视图不同
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    assert {h.slot for h in session.hints} == {"fiber", "equipment"}
    session = app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    assert session.recommendation.product_id == "T-205"
    assert app.events.query(kinds=["match"])[-1].payload["candidate_ids"] == ["T-205"]
    assert app.view_session(session.id, "sales:S01").card.version == "product_usage"
    assert any(s.ku_id == "ku:formula:T-205" for s in app.view_session(session.id, "rd:R01").card.sections)
    with pytest.raises(PermissionDenied):
        app.view_session(session.id, "sales:S02")

    # 套问配方被拒；解密须产品归属研发审批，通过后看到机理
    app.add_turn(session.id, "customer", "这个产品的配方和机理是什么？")
    assert app.view_session(session.id, "sales:S01").replies[-1].blocked
    app.add_turn(session.id, "customer", "我们懂一点，你们这个匀染剂的原理直接讲明白就行")
    q = app.request_decrypt(session.id, "sales:S01")
    app.decide_decrypt(q.id, "rd:R01", True)
    assert app.view_session(session.id, "sales:S01").card.version == "full_mechanism"
    # 冻结只收回高层访问；已有解密授权的会话仍能查看和重新推荐 L1 卡片。
    app.kb.freeze("sales:S01", "supervisor:M01", get_clock().now())
    frozen_card = app.view_session(session.id, "sales:S01").card
    assert frozen_card.version == "product_usage" and all(s.level == 1 for s in frozen_card.sections)
    assert app.recommend_now(session.id).recommendation.version in {"product", "product_usage"}

    # 无解：只写 match，不自动升级、不建需求单
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.status == "open" and other.recommendation is None
    assert app.events.query(kinds=["match"])[-1].payload["p_none"] == 1.0
    assert not app.events.query(kinds=["escalate"]) and not app.requirements("rd:R01")

    # 助手只写草稿；本人发送才产生发言并清空回复草稿。
    ctx = app.agents.context("sales:S01", other.id)
    reply = app.agents.call_tool(ctx, "save_reply_draft", {"text": "请再确认设备条件。"})
    note = app.agents.call_tool(ctx, "save_escalate_note", {"text": "（模拟）气流缸匀染需求，待补充用量。"})
    assert reply.ok and note.ok
    assert len(app.view_session(other.id, "sales:S01").turns) == len(other.turns)
    assert app.view_session(other.id, "sales:S01").reply_draft == "请再确认设备条件。"
    assert not app.view_session(other.id, "customer:C02").reply_draft
    with pytest.raises(PermissionDenied):
        app.save_escalate_note(other.id, "越权修改", "sales:S02")
    assert not app.add_turn(other.id, "sales", "请再确认设备条件。").reply_draft

    # 业务员发出含封存项的话被拦截，不写入；客户原话照常记录
    secret = "（模拟）先投甲料再降温静置十分钟"
    app._requirements["req:send"] = Requirement(id="req:send", question_id="q:send", session_ids=[other.id],
        phenomenon="color_unlevel", known_slots={}, assigned_rd="rd:R01", status="rd_confirmed",
        sealed=[secret], created_at=get_clock().now())
    other = app.save_reply_draft(other.id, secret, "sales:S01")
    n = len(other.turns)
    with pytest.raises(ValueError):
        app.add_turn(other.id, "sales", f"请先试样。{secret}")
    other = app.add_turn(other.id, "customer", secret)
    assert len(other.turns) == n + 1 and other.reply_draft == secret
