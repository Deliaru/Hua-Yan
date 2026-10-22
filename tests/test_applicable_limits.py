"""V9.5：研发判「已有产品适用」时写下的限制原文随适用能力保存；带限制的适用不在客户自助阶段自动推荐，
同类需求照常转研发，研发和产品经理看得到限制原文，其他人只知道要研发处理；不带限制的照旧确认适用。"""

from pathlib import Path

import pytest
import yaml

from huayan.agent.tools import ProductArgs, ToolContext, find_products
from huayan.app import HuayanApp

LIMIT = "（模拟）只在升温段控制在每分钟 1 度以内时适用"


def _app(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return HuayanApp.build(str(path), run_id="v95")


def _escalate(app, session_id):
    # 离线：业务员写好升级说明，问题主人标记准备后签字
    app.save_escalate_note(session_id, "（模拟）涤纶掉色，说明书没有匹配的产品", "sales:S01")
    question = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session_id}")
    app.mark_prepared(question.id, question.owner_id)
    app.escalate(session_id, "sales:S01")
    return next(r for r in app._requirements.values() if session_id in r.session_ids)


def _escalated(app, customer):
    session = app.start_session(customer, "sales:S01")
    app.add_turn(session.id, "customer", "涤纶的布洗了褪色")
    return session, _escalate(app, session.id)


def _declined(app, limits):
    """研发判 T-301 也适用涤纶掉色，产品经理批准适用范围。"""
    _, req = _escalated(app, "customer:C01")
    app.decline_project(req.id, "现有固色剂对这类情况同样有效", req.assigned_rd, "T-301", limits=limits)
    cap = next(c for c in app.kb.capabilities() if c.form == "applicable" and c.payload["product_id"] == "T-301"
               and c.status == "proposed")
    app.kb.approve(cap.id, "pm:P01")
    return cap


def _matched(app, session_id):
    return [e.payload for e in app.events.query(["match"]) if e.session_id == session_id][-1]


def test_limited_applicable_goes_to_rd_with_its_text(tmp_path):
    app = _app(tmp_path)
    cap = _declined(app, LIMIT)
    assert next(c for c in app.kb.capabilities() if c.id == cap.id).payload["limits"] == LIMIT

    session = app.start_session("customer:C02", "sales:S01")
    app.add_turn(session.id, "customer", "涤纶的布洗了褪色")
    assert app._sessions[session.id].recommendation is None
    match = _matched(app, session.id)
    assert match["limited_ids"] == ["T-301"] and "T-301" not in match["candidate_ids"]

    req = _escalate(app, session.id)
    assert [m["limits"] for m in app.matched_limits(req.id, req.assigned_rd)] == [LIMIT]
    with pytest.raises(Exception):
        app.matched_limits(req.id, "sales:S01")

    args = ProductArgs(phenomenon="poor_fastness", slots={"fiber": "涤纶"})
    for who, shown in (("rd:R01", LIMIT), ("pm:agent", LIMIT), ("sales:S01", "带研发限制，需研发处理")):
        [row] = find_products(ToolContext(app=app, principal=app.actors[who], conversation_id="conv:test"), args).data
        assert row["status"] == "possible" and row["limits"] == shown
    with pytest.raises(ValueError, match="poor_fastness="):       # 填了说法不是 id：报错，不当作没有候选
        find_products(ToolContext(app=app, principal=app.actors["pm:agent"], conversation_id="conv:test"),
                      ProductArgs(phenomenon="掉色", slots={"fiber": "涤纶"}))


def test_unlimited_applicable_still_confirmed(tmp_path):
    app = _app(tmp_path)
    _declined(app, "")
    session = app.start_session("customer:C02", "sales:S01")
    app.add_turn(session.id, "customer", "涤纶的布洗了褪色")
    assert app._sessions[session.id].recommendation.product_id == "T-301"
    assert _matched(app, session.id)["limited_ids"] == []


def test_limits_pass_the_leak_check(tmp_path):
    app = _app(tmp_path)
    _, req = _escalated(app, "customer:C01")
    with pytest.raises(ValueError, match="限制条件含研发术语"):
        app.decline_project(req.id, "现有固色剂同样有效", req.assigned_rd, "T-301",
                            limits="染浴 pH 漂移导致上染速率波动时不适用")


def _recommended(app, customer):
    session = app.start_session(customer, "sales:S01")
    app.add_turn(session.id, "customer", "涤纶的布洗了褪色")
    return app._sessions[session.id]


def test_revoke_leaves_no_recommendation_on_a_limited_basis(tmp_path):
    """V9.6a：同一产品还有一条带限制的情境时，撤销不带限制的那条，推荐也要撤回，不能挂在已撤销的能力上。"""
    app = _app(tmp_path)
    plain = _declined(app, "")
    limited = app.kb.grant(plain.model_copy(update={"id": app.kb.next_cap_id(), "status": "active",
                                                   "payload": {**plain.payload, "limits": LIMIT}}))
    app.kb.approve(limited.id, "pm:P01")
    session = _recommended(app, "customer:C02")
    assert session.recommendation.product_id == "T-301"
    app.revoke_capability(plain.id, plain.granted_by)
    assert app._sessions[session.id].recommendation is None
    assert any(e.session_id == session.id and e.payload["capability_id"] == plain.id
               for e in app.events.query(["recommendation_withdrawn"]))
    assert _matched(app, session.id)["limited_ids"] == ["T-301"]


def test_withdrawn_claim_takes_back_the_rd_recommendation(tmp_path):
    """V9.6a：研发判「已有产品适用」直接推给原客户的推荐记着依据；研发撤回这条结论，推荐随之撤回并重新匹配。"""
    app = _app(tmp_path)
    session, req = _escalated(app, "customer:C01")
    app.decline_project(req.id, "现有固色剂对这类情况同样有效", req.assigned_rd, "T-301")
    assert app._sessions[session.id].recommendation.product_id == "T-301"
    cap = next(c for c in app.kb.capabilities() if c.payload.get("product_id") == "T-301" and c.status == "proposed")
    app.withdraw_claim(cap.based_on[0], req.assigned_rd)
    assert app._sessions[session.id].recommendation is None
    assert _matched(app, session.id)["candidate_ids"] == []
    # 这位客户之前升级过；推荐撤回后觉照常跟进，再次提出升级
    assert any(q.object_id == f"session:{session.id}" for q in app.bus.list()
               if q.family in {"escalate_need", "route_rd"})
