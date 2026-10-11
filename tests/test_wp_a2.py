from pathlib import Path
import json

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied
from huayan.contracts import (CustomerProfile, ExtractedSlot, ExtractionResult, Resolution,
                              Requirement, ReqItem, SheetDraft, Trial)
from huayan.clock import get_clock
from huayan.l1.extract import validate_extraction


def test_l1_recommend_and_escalate(tmp_path, monkeypatch):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    assert {h.slot for h in session.hints} == {"fiber", "equipment"}
    assert not app.events.query(kinds=["match"])
    session = app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    assert session.recommendation.product_id == "T-205"
    match = app.events.query(kinds=["match"])[-1]
    assert match.session_id == session.id and match.actor == session.sales_id
    assert match.payload == {"phenomenon": "color_unlevel",
        "known": {"fiber": "锦纶氨纶", "equipment": "溢流染色机"}, "customer_id": "customer:C01",
        "candidate_ids": ["T-205"], "p_choice": {"T-205": session.recommendation.match.probabilities["T-205"]},
        "p_none": session.recommendation.match.probabilities["none"], "scored_by": "mock"}
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
    # 型号同样命中机理标题，不应妨碍公开用法；省略型号时使用当前推荐。
    for question in ("T-205 怎么用？", "用法用量是什么，怎么用？"):
        reply = app.add_turn(session.id, "customer", question).replies[-1]
        assert not reply.blocked
        assert set(reply.ku_ids) == {"ku:sheet:T-205", "ku:usage:T-205"}
        assert "0.5–1.5" in reply.text and "T-101" not in reply.text
    reply = app.add_turn(session.id, "customer", "T-205 怎么用，配方是什么？").replies[-1]
    assert reply.blocked and "0.5–1.5" in reply.text and "保密" in reply.text
    assert all(app.kb.get(ref, app.actors["sales:S01"]).level == 1 for ref in reply.ku_ids)
    reply = app.add_turn(session.id, "customer", "T-101 怎么用？").replies[-1]
    assert not reply.blocked and set(reply.ku_ids) == {"ku:sheet:T-101", "ku:usage:T-101"}
    assert "不适用" in reply.text
    for question in ("那它的用量呢，怎么用？", "具体怎么用？"):
        reply = app.add_turn(session.id, "customer", question).replies[-1]
        assert set(reply.ku_ids) == {"ku:sheet:T-101", "ku:usage:T-101"}
        assert "0.5–1.5" not in reply.text
    app.add_turn(session.id, "customer", "T-101 和 T-205 怎么用？")
    reply = app.add_turn(session.id, "customer", "那它怎么用？").replies[-1]
    assert not reply.ku_ids and "请明确" in reply.text
    reply = app.add_turn(session.id, "customer", "T-999 怎么用？").replies[-1]
    assert not reply.ku_ids and "0.5–1.5" not in reply.text
    reply = app.add_turn(session.id, "customer", "那它怎么用？").replies[-1]
    assert not reply.ku_ids and "请明确" in reply.text
    reply = app.add_turn(session.id, "customer", "推荐的产品怎么用？").replies[-1]
    assert set(reply.ku_ids) == {"ku:sheet:T-205", "ku:usage:T-205"}

    # 使用已有 MockGateway 检查真实回答分支的上下文，不构造新的网关桩。
    requests = []
    original_complete = app.gateway.complete
    def capture(req):
        requests.append(req)
        return original_complete(req)
    monkeypatch.setattr(app.gateway, "complete", capture)
    app.config["gateway_mock"] = False
    app.add_turn(session.id, "customer", "用法用量是什么，怎么用？")
    app.config["gateway_mock"] = True
    payload = json.loads(requests[-1].messages[-1].content)
    assert payload["target_product_ids"] == ["T-205"]
    assert payload["recommended_product_id"] == "T-205"
    assert payload["need"]["known"]["equipment"] == "溢流染色机"
    assert payload["turns"][-1]["text"] == "用法用量是什么，怎么用？"
    assert {h["ku_id"] for h in payload["hits"]} == {"ku:sheet:T-205", "ku:usage:T-205"}
    app.add_turn(session.id, "customer", "T-101 怎么用？")
    app.config["gateway_mock"] = False
    app.add_turn(session.id, "customer", "那它的用量呢，怎么用？")
    app.config["gateway_mock"] = True
    payload = json.loads(requests[-1].messages[-1].content)
    assert payload["target_product_ids"] == ["T-101"]
    assert payload["recommended_product_id"] == "T-205"
    assert {h["ku_id"] for h in payload["hits"]} == {"ku:sheet:T-101", "ku:usage:T-101"}

    app.add_turn(session.id, "customer", "我们懂一点，你们这个匀染剂的原理直接讲明白就行")
    q = app.request_decrypt(session.id, "sales:S01")
    app.decide_decrypt(q.id, "rd:R01", True)
    assert not any(e.ku_id == "ku:mechanism:T-205" for e in app.ledger.list())
    card = app.view_session(session.id, "sales:S01").card
    assert card.version == "full_mechanism"
    counts = len(app.audit.list()), len(app.ledger.list())
    for _ in range(3):
        app.view_session(session.id, "sales:S01")
    assert counts == (len(app.audit.list()), len(app.ledger.list()))
    assert any(r.version == "full_mechanism" and r.action == "disclose" for r in app.audit.list())
    assert sum(e.ku_id == "ku:mechanism:T-205" and e.reason == "cited" for e in app.ledger.list()) == 1
    app.view_session(session.id, "customer:C01")
    assert len(app.ledger.list()) == counts[1]

    _check_l1_match_without_automatic_escalation(app)

    # 以下旧升级/草稿生命周期断言待 WP-C 门面签字模块按 v5 迁移，保留以暴露集成缺口。
    # 条件修改与问答同时出现时，先清除失效推荐，再回答。
    changed = app.add_turn(session.id, "customer", "设备是气流缸，怎么用？")
    assert changed.status == "escalated" and changed.recommendation.product_id is None
    assert app.view_session(session.id, "sales:S01").card is None
    assert not changed.replies[-1].ku_ids and "T-205" not in changed.replies[-1].text
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.status == "escalated"
    assert any(q.refs["session_id"] == other.id for q in app.bus.list(family="escalate_need"))
    old_qid = other.recommendation.escalated_question_id
    other = app.add_turn(other.id, "customer", "刚才说错了，是溢流缸，怎么用？")
    assert other.status == "recommended" and other.recommendation.product_id == "T-205"
    assert set(other.replies[-1].ku_ids) == {"ku:sheet:T-205", "ku:usage:T-205"}
    assert app.view_session(other.id, "sales:S01").card.product_id == "T-205"
    old = app.bus.get(old_qid)
    assert old.status == "dismissed" and old.resolution.by == "system:l1"
    assert "失效" in old.resolution.note
    assert any("溢流染色机" in e.summary for e in old.evidence)
    assert not any("气流染色机" in e.summary for e in old.evidence)
    assert not any(q.refs.get("session_id") == other.id for q in app.bus.list())
    # 更正后再变回无解条件，不受系统撤销产生的 24 小时忽略窗口阻断。
    other = app.add_turn(other.id, "customer", "设备改成气流缸，怎么用？")
    second_qid = other.recommendation.escalated_question_id
    assert other.status == "escalated" and second_qid != old_qid
    assert app.bus.get(old_qid).status == "dismissed"
    assert app.bus.get(second_qid).refs["previous_question_id"] == old_qid
    other = app.add_turn(other.id, "customer", "还要求不要APEO，怎么用？")
    latest_qid = other.recommendation.escalated_question_id
    assert latest_qid not in {old_qid, second_qid}
    assert any("无APEO" in e.summary for e in app.bus.get(latest_qid).evidence)
    assert any("气流染色机" in e.summary for e in app.bus.get(latest_qid).evidence)
    assert app.bus.get(second_qid).status == "dismissed"
    # WP-L 按已派过的 ID 排除；新一轮仍在可派集合中，无需重置历史。
    dispatched_ids = {old_qid, second_qid}
    assert latest_qid in {q.id for q in app.bus.list() if q.id not in dispatched_ids}
    assert any(e.payload["question_id"] == latest_qid for e in app.events.query(kinds=["question_published"]))
    count = len(app.events.query(kinds=["escalate"]))
    app.recommend_now(other.id)
    assert len(app.events.query(kinds=["escalate"])) == count
    assert len([q for q in app.bus.list() if q.refs.get("session_id") == other.id]) == 1
    assert app.recommend_now(other.id).recommendation.escalated_question_id == latest_qid
    snapshots = [json.loads(line) for line in (app.run_dir / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(q["id"] == old_qid and q["status"] == "dismissed" for q in snapshots)
    assert [q for q in snapshots if q["id"] == old_qid][-1]["status"] == "dismissed"
    assert [q for q in snapshots if q["id"] == latest_qid][-1]["status"] == "open"
    # 人工已处置的记录不能被纠正流程覆盖或自动重新打开。
    app.bus.resolve(latest_qid, Resolution(action="dismiss", by="pm:P01", note="人工忽略"), get_clock().now())
    app.add_turn(other.id, "customer", "改成溢流缸，怎么用？")
    suppressed = app.add_turn(other.id, "customer", "改回气流缸，怎么用？")
    assert suppressed.recommendation.escalated_question_id is None
    assert "已转" not in suppressed.replies[-1].text
    assert app.bus.get(latest_qid).resolution.by == "pm:P01"
    assert not any(q.refs.get("session_id") == other.id for q in app.bus.list())
    unknown = app.start_session("customer:C03", "sales:S01")
    app.add_turn(unknown.id, "customer", "深一块浅一块，锦纶氨纶的")
    app.add_turn(unknown.id, "sales", "请问用的是什么染色设备？")
    unknown = app.add_turn(unknown.id, "customer", "这个不清楚")
    assert unknown.need.slots["equipment"].status == "unknown"
    assert unknown.need.asked["equipment"] == 1
    assert not unknown.hints
    assert (app.run_dir / "sessions/sess_1.json").exists()
    assert app.status().realtime_model == "jue_proto"
    bad = ExtractionResult(intent="need", phenomenon="color_unlevel", profile=CustomerProfile(), slots=[
        ExtractedSlot(slot="fiber", value="虚构面料", status="filled", confidence=0.9,
                      quote="锦纶氨纶", turn_n=2)])
    assert not validate_extraction(bad, app.seeds, session.turns).slots
    bad.slots[0].value, bad.slots[0].quote = "棉", "客户并未说过的原话"
    with pytest.raises(ValueError):
        validate_extraction(bad, app.seeds, session.turns)

    # 正式型号同样从实际知识库解析，不依赖 mini_seeds 的型号形态。
    product = app.kb.product("T-205").model_copy(update={"id": "HY-LV205"})
    app.kb.add_product(product, get_clock().now())
    formal = app.start_session("customer:C01", "sales:S01")
    for question in ("HY-LV205 怎么用？", "那它的用量呢，怎么用？", "hy-lv205 怎么用？"):
        reply = app.add_turn(formal.id, "customer", question).replies[-1]
        assert set(reply.ku_ids) == {"ku:sheet:HY-LV205", "ku:usage:HY-LV205"}
    for question in ("HY-LV2050 怎么用？", "HY-LV999 怎么用？", "HY-LV205 和 HY-LV999 怎么用？"):
        reply = app.add_turn(formal.id, "customer", question).replies[-1]
        assert not reply.ku_ids and "请明确" in reply.text

    # 手工既有草稿只验证门面生命周期，不替代 WP-T 的转译验收。
    pending = app.start_session("customer:C02", "sales:S01")
    pending = app.add_turn(pending.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    qid = pending.recommendation.escalated_question_id
    draft = Requirement(id="req:1", question_id=qid, session_ids=[pending.id],
        phenomenon=pending.need.phenomenon, known_slots=pending.need.known(), direction="模拟匀染需求",
        product_lang=[ReqItem(text="模拟气流缸需求", quote_refs=[pending.turns[0].id])],
        status="draft", drafted_by="pm:P01", created_at=get_clock().now())
    app._requirements[draft.id] = draft
    assert app.draft_requirement(qid, "pm:P01").id == draft.id
    app.add_turn(pending.id, "customer", "怎么用？")
    assert draft.status == "draft"
    pending = app.add_turn(pending.id, "customer", "还要求不要APEO，怎么用？")
    original_qid, qid = qid, pending.recommendation.escalated_question_id
    assert original_qid != qid and app.bus.get(original_qid).status == "dismissed"
    assert draft.status == "rejected" and "constraint" not in draft.known_slots
    with pytest.raises(ValueError, match="重新核对"):
        app.confirm_requirement(draft.id, "pm:P01")
    assert app.bus.get(qid).status == "open"
    assert any("重新核对并起草" in e.summary for e in app.bus.get(qid).evidence)
    assert not app.events.query(kinds=["requirement_confirmed"])
    assert json.loads((app.run_dir / "requirements/req_1.json").read_text(encoding="utf-8"))["status"] == "rejected"
    assert app.view_session(pending.id, "pm:P01").requirement is None
    # 旧版落盘草稿未带失效状态时，确认入口仍按当前需求拦截。
    draft.status = "draft"
    with pytest.raises(ValueError, match="重新核对"):
        app.confirm_requirement(draft.id, "pm:P01")
    assert draft.status == "rejected"
    updated = draft.model_copy(deep=True, update={"id": "req:2", "status": "draft",
        "question_id": qid,
        "created_at": get_clock().now(), "known_slots": pending.need.known(),
        "product_lang": [ReqItem(text="模拟气流缸匀染，要求无 APEO", quote_refs=[pending.turns[-1].id])]})
    app._requirements[updated.id] = updated
    assert app.draft_requirement(qid, "pm:P01").id == updated.id
    app.bus.resolve(qid, Resolution(action="dismiss", by="pm:P01"), get_clock().now())
    with pytest.raises(ValueError, match="非待处理"):
        app.confirm_requirement(updated.id, "pm:P01")
    assert updated.status == "draft"
    app.bus.get(qid).status = "open"  # 恢复手工夹具，验证有效草稿的正常确认。
    assert app.confirm_requirement(updated.id, "pm:P01").status == "pm_confirmed"
    assert app.bus.get(qid).status == "resolved"
    app.add_turn(pending.id, "customer", "设备改成溢流缸，怎么用？")
    assert updated.status == "pm_confirmed"  # 已确认需求不自动重写。

    # 手工研发阶段记录：保存说明书的返回值与只读门面执行相同裁剪。
    secret = "（模拟）仅研发可读的内部假设"
    updated.status, updated.product_id = "rd_confirmed", "T-206"
    updated.hypotheses = [secret]
    assert secret in app.set_public_points(updated.id, "（模拟）改善匀染，先试样", "rd:R02").hypotheses
    sheet = SheetDraft(sheet="（模拟）气流缸用匀染产品", usage="（模拟）按试样用量使用")
    returned = app.save_sheet(updated.id, sheet, "pm:P01")
    assert returned.hypotheses == [] and secret not in returned.model_dump_json()
    assert returned == app.requirement_view(updated.id, "pm:P01").requirement
    assert app.requirement_view(updated.id, "rd:R02").requirement.hypotheses == [secret]
    saved = json.loads((app.run_dir / "requirements/req_2.json").read_text(encoding="utf-8"))
    assert saved["hypotheses"] == [secret]
    returned.sheet.sheet = "外部修改"
    assert updated.sheet.sheet == sheet.sheet
    app.record_trial(Trial(id="trial:return-boundary", product_id="T-206", requirement_id=updated.id,
        rd="rd:R02", conditions=updated.known_slots, result="pass", cause="none", at=get_clock().now()))
    released = app.release_product(updated.id, "pm:P01")
    assert not released.mechanism and not released.formula
    assert app.kb.get("ku:formula:T-206", app.actors["rd:R02"]).text


def _check_l1_match_without_automatic_escalation(app):
    """WP-C 第 2 步第 1 项；使用现有离线门面与 MockSystem1，不替代觉或签字流程。"""
    assert "routing" not in app.config
    questions_before = [q.model_dump() for q in app.bus.list(status=None)]
    resolutions_before = len(app.events.query(kinds=["question_resolved"]))
    session = app.start_session("customer:C02", "sales:S01")
    session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert session.status == "open" and session.recommendation is None
    assert app.view_session(session.id, "sales:S01").card is None
    event = app.events.query(kinds=["match"])[-1]
    assert event.session_id == session.id
    assert event.payload == {"phenomenon": "color_unlevel",
        "known": {"fiber": "锦纶氨纶", "equipment": "气流染色机"}, "customer_id": "customer:C02",
        "candidate_ids": [], "p_choice": {}, "p_none": 1.0, "scored_by": "rule"}
    assert not app.events.query(kinds=["escalate"])
    assert not app.requirements("rd:R01")
    # 没有自动升级；更正条件后仍可在 L1 重新匹配，后续变更也不能保留旧卡。
    session = app.add_turn(session.id, "customer", "刚才说错了，是溢流缸，怎么用？")
    assert session.status == "recommended" and session.recommendation.product_id == "T-205"
    assert set(session.replies[-1].ku_ids) == {"ku:sheet:T-205", "ku:usage:T-205"}
    assert app.events.query(kinds=["match"])[-1].payload["known"]["equipment"] == "溢流染色机"
    session = app.add_turn(session.id, "customer", "改回气流缸，怎么用？")
    assert session.status == "open" and session.recommendation is None
    assert not session.replies[-1].ku_ids and "已转" not in session.replies[-1].text
    assert app.view_session(session.id, "sales:S01").card is None
    # 有追问提示时点“直接推荐”也写 match；低置信度不推荐、不升级、不记披露积分。
    undecided = app.start_session("customer:C03", "sales:S01")
    undecided = app.add_turn(undecided.id, "customer", "深一块浅一块")
    assert undecided.hints
    records_before = len(app.audit.list()), len(app.ledger.list()), len(app.events.query(kinds=["recommend"]))
    undecided = app.recommend_now(undecided.id)
    assert undecided.status == "open" and undecided.recommendation is None
    event = app.events.query(kinds=["match"])[-1]
    assert event.session_id == undecided.id and event.payload["candidate_ids"]
    assert max(event.payload["p_choice"].values()) < app.jev.match_threshold
    assert records_before == (len(app.audit.list()), len(app.ledger.list()), len(app.events.query(kinds=["recommend"])))
    # 相同条件下重新匹配变得不确定时，同样清除原推荐。
    session = app.add_turn(session.id, "customer", "改成溢流缸")
    assert session.status == "recommended"
    threshold = app.jev.match_threshold
    app.jev.match_threshold = 0.99
    try:
        session = app.recommend_now(session.id)
    finally:
        app.jev.match_threshold = threshold
    assert session.status == "open" and session.recommendation is None
    assert app.view_session(session.id, "sales:S01").card is None
    assert [q.model_dump() for q in app.bus.list(status=None)] == questions_before
    assert not app.events.query(kinds=["escalate"])
    assert len(app.events.query(kinds=["question_resolved"])) == resolutions_before
