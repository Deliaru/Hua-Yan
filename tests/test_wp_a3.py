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

    def prepare(family, object_id):
        # 离线直接起草后，由问题主人标记准备；问题必须由觉真实提出。
        question = next(q for q in app.bus.list(family=family) if q.object_id == object_id)
        app.mark_prepared(question.id, question.owner_id)

    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    with pytest.raises(ValueError, match="准备中"):
        app.escalate(session.id, "sales:S01")
    app.save_escalate_note(session.id, "（模拟）锦纶氨纶、气流缸色花，现有产品无法匹配", "sales:S01")
    prepare("escalate_need", f"session:{session.id}")
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
    item = req.product_lang[0].model_copy(update={"edited_by": rd})
    saved = app.edit_req_item(req.id, 0, item, "pm:agent")
    assert saved.product_lang[0].edited_by is None
    l3_term = next(t.chem_term for t in app.seeds.translations if t.level == 3)
    with pytest.raises(ValueError, match="研发术语"):
        app.return_requirement(req.id, l3_term, rd)
    prepare("accept_requirement", f"requirement:{req.id}")
    returned = app.return_requirement(req.id, "请突出客户的无APEO要求", rd)
    assert returned.status == "draft" and returned.return_notes == ["请突出客户的无APEO要求"]
    # v6：退回后的纠偏派给真人产品经理（不走 Agent 起草），改完标记准备、回到研发接单
    accept = next(q for q in app.bus.list(family="accept_requirement") if q.object_id == f"requirement:{req.id}")
    assert accept.owner_id == "pm:P01"
    fixed = app.edit_req_item(req.id, 0, returned.product_lang[0].model_copy(
        update={"text": returned.product_lang[0].text + "；突出无APEO"}), "pm:P01")
    assert fixed.product_lang[0].edited_by == "pm:P01"
    prepare("accept_requirement", f"requirement:{req.id}")
    app.accept_requirement(req.id, rd)
    req = app.translate_requirement(req.id, rd)
    first = req.chem_lang[0]
    agent_edit = app.agents.call_tool(app.agents.context(rd), "edit_item", {"req_id": req.id, "index": 0,
        "text": first.text + "；待核对低浴比条件", "quote_refs": first.quote_refs, "ku_refs": first.ku_refs})
    assert agent_edit.ok
    assert app.requirement_view(req.id, rd).requirement.chem_lang[0].edited_by is None
    assert app.events.query(["requirement_edited"])[-1].payload["after"]["edited_by"] is None
    assert not any(q.refs.get("requirement_id") == req.id for q in app.bus.list(family="contribution"))
    app.edit_req_item(req.id, 0, first.model_copy(update={"text": first.text + "；验证低浴比稳定性"}), rd)
    assert app.requirement_view(req.id, rd).requirement.chem_lang[0].edited_by == rd
    prepare("contribution", f"requirement:{req.id}")
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）低浴比缓染稳定性", rd)
    prepare("confirm_translation", f"requirement:{req.id}")
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
    prepare("market_eval", f"requirement:{req.id}")
    app.record_market_eval(req.id, "pass", "（模拟）客户试用通过", "sales:S01")
    app.save_points_draft(req.id, "（模拟）改善低浴比匀染；按工艺试样确认。", ["（模拟）分段吸附诀窍"], rd)
    prepare("seal_points", f"requirement:{req.id}")
    app.set_public_points(req.id, "（模拟）改善低浴比匀染；按工艺试样确认。", ["（模拟）分段吸附诀窍"], rd)
    sheet = app.package_sheet(req.id, "pm:agent")
    prepare("release", f"requirement:{req.id}")
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
    app.save_escalate_note(reuse_session.id, "（模拟）涤纶手感发硬，无说明书匹配产品", "sales:S01")
    prepare("escalate_need", f"session:{reuse_session.id}")
    reuse_req = app.escalate(reuse_session.id, "sales:S01")
    note = "（模拟）可用 HY-SF520 改善手感，按用法先做小样。"
    app.save_reuse_proposal(reuse_req.id, "HY-SF520", ["ku:case:case:reuse_softness"], note,
                            "参考 P01 的历史案例，待研发审定", "pm:agent")
    pending = app.view_session(reuse_session.id, "sales:S01")
    assert pending.reuse.status == "pending" and not pending.reuse.customer_note and not pending.reuse.basis
    assert pending.card is None and not pending.reuse.usage
    with pytest.raises(PermissionDenied):
        app.adopt_reuse(reuse_req.id, "sales:S01")
    prepare("reuse_product", f"requirement:{reuse_req.id}")
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
    sent = app.add_turn(reuse_session.id, "sales", note)
    assert sent.status == "recommended" and sent.recommendation == adopted.recommendation
    assert not any(q.object_id == f"session:{reuse_session.id}" for q in app.bus.list(family="escalate_need"))
    assert app.view_session(reuse_session.id, "sales:S01").card.note == sales_view.card.note
    repeated = app.add_turn(reuse_session.id, "customer", "对，涤纶布手感发硬")
    assert repeated.recommendation == adopted.recommendation
    changed = app.add_turn(reuse_session.id, "customer", "说错了，是锦纶氨纶，手感发硬")
    assert changed.recommendation is None and changed.status == "open"

    # Q2：未授予的研发追问不影响客户；授予、撤销与持久化共用能力表。
    from huayan.contracts import Capability, KnowledgeUnit
    from huayan.domain import match_candidates
    from huayan.events import EventLog
    from huayan.knowledge import AuditLog, KnowledgeBase

    app = HuayanApp.build(str(path))
    unit = KnowledgeUnit(id=app.kb.next_claim_id(), kind="claim", level=3, title="环保条件判断（模拟）",
        text="（模拟）此类需求要确认环保要求", owner="rd:R01", status="candidate",
        phenomenon_ids=["color_unlevel"], source="contributed", created_at=get_clock().now())
    app.kb.add(unit)
    assert not any(h.ku.id == unit.id for h in app.kb.search("环保", app.actors["rd:R01"]))
    app.kb.confirm([unit.id], "rd:R01")
    local = app.kb.grant(Capability(id=app.kb.next_cap_id(), form="ask", audience=3,
        payload={"phenomenon": "color_unlevel", "slot": "constraint", "required": True},
        based_on=[unit.id], granted_by="rd:R01", status="active", at=get_clock().now()))
    opening = "深一块浅一块，锦氨的，溢流缸"
    first = app.start_session("customer:C01")
    assert not app.add_turn(first.id, "customer", opening).hints
    granted = app.kb.grant(local.model_copy(update={"id": app.kb.next_cap_id(), "audience": 0}))
    second = app.start_session("customer:C02")
    assert {h.slot for h in app.add_turn(second.id, "customer", opening).hints} == {"constraint"}
    used = [e for e in app.events.query(["capability_used"]) if e.payload["capability_id"] == granted.id]
    assert len(used) == 1 and used[0].session_id == second.id
    app._use_capability(granted.id, second.id, second.customer_id)
    assert len([e for e in app.ledger.list("rd:R01") if e.reason == "used" and e.ref == second.id]) == 1
    with pytest.raises(PermissionDenied):
        app.kb.grant(local.model_copy(update={"id": app.kb.next_cap_id(), "granted_by": "rd:R02"}))
    with pytest.raises(PermissionDenied):
        app.revoke_capability(granted.id, "rd:R02")
    app.revoke_capability(granted.id, "rd:R01")
    assert not app.view_session(second.id, second.customer_id).hints
    third = app.start_session("customer:C03")
    assert not app.add_turn(third.id, "customer", opening).hints

    # 适用情境待产品经理批准；撤销后客户、业务员和 Agent 的匹配一起停止。
    situation = app.kb.grant(Capability(id=app.kb.next_cap_id(), form="applicable", audience=0,
        payload={"product_id": "T-205", "phenomenon": "color_unlevel",
                 "conditions": {"fiber": ["锦纶氨纶"], "equipment": ["气流染色机"]}},
        based_on=[unit.id], granted_by="rd:R01", status="active", at=get_clock().now()))
    known = {"fiber": "锦纶氨纶", "equipment": "气流染色机"}
    assert situation.status == "proposed"
    assert not match_candidates("color_unlevel", known, app.kb.view(app.actors["customer:C01"]).products)
    app.scan()
    app.tick()
    q = next(q for q in app.bus.list(family="scope_update") if q.refs["capability_id"] == situation.id)
    app.extend_scope(q.id, "（模拟）批准这一完整情境", "pm:P01")
    reuse = app.start_session("customer:C01")
    assert app.add_turn(reuse.id, "customer", "深一块浅一块，锦氨的，气流缸").recommendation.product_id == "T-205"
    assert {"rd:R01", "pm:P01"} <= {e.owner for e in app.ledger.list() if e.reason == "used" and e.ref == reuse.id}
    app.revoke_capability(situation.id, "rd:R01")
    for viewer in ("customer:C01", "sales:S01", "pm:agent"):
        assert not match_candidates("color_unlevel", known, app.kb.view(app.actors[viewer]).products)
    result = app.agents.call_tool(app.agents.context("pm:agent"), "find_products",
                                 {"phenomenon": "color_unlevel", "slots": known})
    assert result.ok and not result.data
    assert app.view_session(reuse.id, "customer:C01").card is None

    # 解密撤销沿用披露上限，原推荐卡立即不再包含机理。
    decrypted = app.start_session("customer:C02", "sales:S01")
    app.add_turn(decrypted.id, "customer", "深一块浅一块，锦氨的，溢流缸，要匀染剂")
    request = app.request_decrypt(decrypted.id, "sales:S01")
    app.decide_decrypt(request.id, "rd:R01", True, "（模拟）审定的机理说明")
    assert app.view_session(decrypted.id, "sales:S01").card.version == "full_mechanism"
    decrypt = next(c for c in app.capabilities("rd:R01") if c.form == "decrypt")
    app.revoke_capability(decrypt.id, "rd:R01")
    assert app.view_session(decrypted.id, "sales:S01").card.version == "product_usage"
    restored = KnowledgeBase.from_seeds(app.seeds, EventLog(), AuditLog(), state_path=app.kb.state_path)
    statuses = {c.id: c.status for c in restored.capabilities()}
    assert statuses[local.id] == "active"
    assert all(statuses[c.id] == "revoked" for c in (granted, situation, decrypt))
    assert not restored.decrypt_grants()
