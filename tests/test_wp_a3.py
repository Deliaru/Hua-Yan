import json
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ReqItem, SheetDraft, SlotFill, Trial
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
    # v8：退回后由产品经理 Agent 按理由重写（真人产品经理退出逐单转述）；没改之前不算准备好
    accept = next(q for q in app.bus.list(family="accept_requirement") if q.object_id == f"requirement:{req.id}")
    assert accept.owner_id == "pm:agent" and "还没按理由修改" in app.preparation_gap(accept.id)
    app.edit_req_item(req.id, 0, returned.product_lang[0].model_copy(
        update={"text": returned.product_lang[0].text + "；突出无APEO"}), "pm:agent")
    prepare("accept_requirement", f"requirement:{req.id}")
    # v8 接单前先回问客户：研发勾选设备 → 仍待接单、觉对设备提出回问、答完之前不再提接单 → 客户答后再提接单
    assert app.ask_before_accept(req.id, ["equipment"], rd).status == "draft"
    assert any(q.object_id == f"slot:{req.id}/equipment" for q in app.bus.list(family="ask_back"))
    assert not any(q.object_id == f"requirement:{req.id}" for q in app.bus.list(family="accept_requirement"))
    app.add_turn(session.id, "customer", "设备是气流缸")
    assert any(q.object_id == f"requirement:{req.id}" for q in app.bus.list(family="accept_requirement"))
    # v8 收口：回问答复与会话补条件同一条路——未经人改的产品需求条目清掉，由产品经理 Agent 按新条件重写
    assert app.requirement_view(req.id, rd).requirement.product_lang == []
    get_clock().advance_to(get_clock().now() + timedelta(hours=1))   # 之后的退回晚于这次回答
    app.draft_requirement(req.id, "pm:agent")
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
    # v8 试样风险：客户对必问的设备答过「不清楚」（模拟）→ 觉在试样前提出 trial_risk → 研发先回问 →
    # 回到待重新转译、觉对设备提出回问 → 回答后重新确认，不再提出
    app._requirements[req.id].known_slots.pop("equipment")
    app._sessions[session.id].need.slots["equipment"] = SlotFill(slot="equipment", value=None, status="unknown",
                                                                 confidence=0.7, quote="不清楚", turn_id="turn:x")
    app._after(req_ids=[req.id])
    prepare("trial_risk", f"requirement:{req.id}")
    assert app.return_for_conditions(req.id, ["equipment"], rd).status == "rd_accepted"
    assert any(q.object_id == f"slot:{req.id}/equipment" for q in app.bus.list(family="ask_back"))
    app.add_turn(session.id, "customer", "设备是气流缸")
    # V9.6a：条件变了，化学稿里 Agent 起草的条目清掉、研发改过的保留并请研发重新确认；没按新条件重新起草前不算准备好
    returned = app.requirement_view(req.id, rd).requirement
    assert returned.known_slots["equipment"] == "气流染色机"
    assert [i.edited_by for i in returned.chem_lang] == [rd] and "重新确认" in returned.return_notes[-1]
    assert any(i.slot == "equipment" and "气流" in i.text for i in returned.product_lang)
    confirm = next(q for q in app.bus.list(family="confirm_translation") if q.object_id == f"requirement:{req.id}")
    assert "重新起草" in app.preparation_gap(confirm.id)
    app.translate_requirement(req.id, rd)
    prepare("confirm_translation", f"requirement:{req.id}")
    req = app.confirm_translation(req.id, rd)
    assert not app.bus.list(family="trial_risk")
    get_clock().advance_to(get_clock().now() + timedelta(hours=1))   # 之后的试样失败晚于这次回答
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
    # Q5.5 试样失败回路：单上设备填错了（模拟），研发录入「需求条件缺失：设备」→ 觉提出 trial_rework →
    # 签字后回到待重新转译、觉对设备提出回问 → 回答的新值覆盖原值、不再提出
    app._requirements[req.id].known_slots["equipment"] = "溢流染色机"
    with pytest.raises(ValueError):
        app.record_requirement_trial(req.id, "fail", rd)
    app.record_requirement_trial(req.id, "fail", rd, cause="requirement", missing_slots=["equipment"])
    prepare("trial_rework", f"requirement:{req.id}")
    assert app.rework_requirement(req.id, rd).status == "rd_accepted"
    assert not app.bus.list(family="trial_rework")
    back = next(q for q in app.bus.list(family="ask_back") if q.object_id == f"slot:{req.id}/equipment")
    app.add_turn(session.id, "customer", "设备是气流缸")
    assert back.id not in {q.id for q in app.bus.list(family="ask_back")}
    assert app.requirement_view(req.id, rd).requirement.known_slots["equipment"] == "气流染色机"
    assert not any(q.object_id == f"slot:{req.id}/equipment" for q in app.bus.list(family="ask_back"))
    app.translate_requirement(req.id, rd)
    prepare("confirm_translation", f"requirement:{req.id}")
    req = app.confirm_translation(req.id, rd)
    assert not app.bus.list(family="trial_rework")
    app.record_trial(Trial(id="trial:2", product_id=req.product_id, requirement_id=req.id, rd=rd,
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
    # V9.6a：发布后原会话收到新产品推荐，依据是本单发布的适用情境；这次推荐给说明书记一次引用
    origin = app._sessions[session.id]
    released = next(p for p in app.kb.products() if p.id == "T-206")
    assert origin.status == "recommended" and origin.recommendation.product_id == "T-206"
    assert origin.recommendation.candidates[0].capability_id in {x.capability_id for x in released.situations}
    assert row.points == app.config["points"]["product_released"] + app.config["points"]["cited"]
    assert row.n_cited == 1 and row.used_by == ["T-206", session.id]
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

    # v8 Q9.5：主管看一天的时间线，研发写的话与上层结论只给存根，不含任何研发级原文；别人看不了
    day = next(e.ts.date() for e in app.events.query(["requirement_translated"]))
    with pytest.raises(PermissionDenied):
        app.timeline(day, rd)
    dump = json.dumps(app.timeline(day, "supervisor:M01"), ensure_ascii=False)
    l3 = [u.text for u in app.kb._units.values() if u.level == 3 and u.kind != "trial"]
    l3 += [it.text for r in app._requirements.values() for it in r.chem_lang]
    assert "研发知识 · 归属" in dump and not any(t in dump for t in l3 if len(t) >= 8)

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
    # 撤回后重新匹配留下 match 事件：自助会话没有别的产品时由觉直达研发，不停在没有下文的会话里
    assert app.events.query(["match"])[-1].session_id == reuse.id
    app.tick()
    assert app._sessions[reuse.id].status == "escalated"

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

    # Q2.5：同层研发用到才看、看了记分、想看先申请。换一份夹具副本，让 R02 接这类单（转化对照归属对调）。
    import shutil
    seeds_dir = tmp_path / "seeds_r02"
    shutil.copytree("tests/fixtures/mini_seeds", seeds_dir)
    swap = {"rd:R01": "rd:R02", "rd:R02": "rd:R01"}
    translations = yaml.safe_load((seeds_dir / "translations.yaml").read_text(encoding="utf-8"))
    for item in translations["items"]:
        item["owner"] = swap.get(item["owner"], item["owner"])
    (seeds_dir / "translations.yaml").write_text(yaml.safe_dump(translations, allow_unicode=True), encoding="utf-8")
    path_r02 = tmp_path / "app_r02.yaml"
    rag = seeds_dir / "rag"                            # Q4 用夹具 rag/ 的临时副本
    sources = [{"name": kind, "kind": kind, "root": str(rag / kind)} for kind in ("public", "internal", "external")]
    path_r02.write_text(yaml.safe_dump({**config, "seeds_dir": str(seeds_dir), "sources": sources}), encoding="utf-8")
    app = HuayanApp.build(str(path_r02))
    r01, r02 = app.actors["rd:R01"], app.actors["rd:R02"]
    tr5 = "ku:translation:tr:5"                       # 现归 R01：「锦纶氨纶」的转化知识
    assert any(s.ku_id == tr5 and s.owner == "rd:R01" for s in app.kb.search_blocked("锦纶氨纶", r02))
    with pytest.raises(PermissionDenied):
        app.kb.get(tr5, r02)
    for other in ("sales:S01", "pm:P01"):
        assert all(s.ku_id is None for s in app.kb.search_blocked("锦纶氨纶 匀染", app.actors[other]))
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    app.save_escalate_note(session.id, "（模拟）锦纶氨纶、气流缸色花", "sales:S01")
    prepare("escalate_need", f"session:{session.id}")
    req = app.escalate(session.id, "sales:S01")
    assert req.assigned_rd == "rd:R02"
    app.save_reuse_proposal(req.id, None, [], "", "离线：未检索现成产品", "pm:agent")
    app.draft_requirement(req.id, "pm:agent")
    prepare("accept_requirement", f"requirement:{req.id}")
    app.accept_requirement(req.id, "rd:R02")
    req = app.translate_requirement(req.id, "rd:R02")
    assert tr5 in req.engine_refs
    assert next(c for c in app.requirement_view(req.id, "rd:R02").cited if c.ku_id == tr5).text is not None
    peek = app.requirement_view(req.id, "rd:R01").requirement      # 同事打开 R02 的单子：只见 L2 与归属
    assert not peek.chem_lang and not peek.hypotheses and not peek.sealed and peek.product_lang
    assert any("有相关机理（归属" in h for h in req.hypotheses)    # R01 的机理对 R02 只写归属
    with pytest.raises(ValueError, match="无权读取"):
        app.edit_req_item(req.id, -1, ReqItem(text="手加同事的机理", ku_refs=["ku:mechanism:T-205"]), "rd:R02")
    prepare("confirm_translation", f"requirement:{req.id}")
    app.confirm_translation(req.id, "rd:R02")
    assert any(e.reason == "cited" and e.owner == "rd:R01" and e.ku_id == tr5 for e in app.ledger.list())
    for ku_id in (tr5, "ku:formula:T-205"):         # 配方同样走申请与授予
        app.request_share(ku_id, "rd:R02")
        q = next(q for q in app.bus.list(family="qi_grant") if q.refs.get("ku_id") == ku_id)
        assert q.owner_id == q.signer_id == "rd:R01"
        app.agents.dispatch()
        assert app.bus.get(q.id).prepared_at is not None
        share = app.sign_qi_grant(q.id, "rd:R01")
        assert app.kb.get(ku_id, r02).id == ku_id
        assert any(e.reason == "shared" and e.ku_id == ku_id for e in app.ledger.list("rd:R01"))
    app.revoke_capability(share.id, "rd:R01")
    with pytest.raises(PermissionDenied):
        app.kb.get("ku:formula:T-205", r02)
    assert app.kb.get(tr5, r02) and app.kb.get("ku:formula:T-205", r01)

    # Q4：编译。候选不进任何更低层的视图、不经 search 读出；只有外部依据的不能确认；改原文 → 挂起与复核。
    from huayan.ingest.compile import Proposals, admit
    recorded = yaml.safe_load((rag / "proposals.yaml").read_text(encoding="utf-8"))["items"]
    views = {a: app.kb.view(app.actors[a]).model_dump() for a in ("customer:C01", "sales:S01", "pm:P01", "rd:R01")}
    report = admit(Proposals(items=recorded).items, app.kb.sources, app.kb)
    assert report["dropped"] == ["引文不符（模拟）"] and len(report["admitted"]) == 3
    ask, situation, external = report["admitted"]
    assert ask["level"] == situation["level"] == 3 and external["level"] == 0
    assert all(app.kb.view(app.actors[a]).model_dump() == v for a, v in views.items())
    for viewer in ("customer:C01", "rd:R01"):
        assert not any(h.ku.kind == "claim" and h.ku.status == "candidate"
                       for h in app.kb.search("无APEO 涤纶 气流 升温", app.actors[viewer]))
    with pytest.raises(ValueError, match="外部"):
        app.kb.confirm([external["ku_id"]], "rd:R01")
    app.kb.confirm([ask["ku_id"]], "rd:R01")
    assert app.kb._caps[ask["capability_id"]].status == "active"
    assert "constraint" in next(p for p in app.kb.view(r01).phenomena if p.id == "color_unlevel").required_slots
    report_path = rag / "internal" / "RPT-T1.md"
    report_path.write_text(report_path.read_text(encoding="utf-8").replace("无APEO", "低泡"), encoding="utf-8")
    assert app.recheck_evidence() == [ask["ku_id"]]
    assert app.kb._caps[ask["capability_id"]].status == "suspended"
    review = next(q for q in app.bus.list(family="qi_review") if q.refs["ku_id"] == ask["ku_id"])
    assert review.signer_id == "rd:R01"


def test_corrected_condition_reaches_release(tmp_path):
    """V9.6a：立项后客户更正条件——发布的适用情境与说明书用最后一次通过试样、本单当前条件；原会话收到推荐，
    按旧条件来的下一位客户不会被推荐。"""
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    clock = get_clock()

    def prepare(family, object_id):
        question = next(q for q in app.bus.list(family=family) if q.object_id == object_id)
        app.mark_prepared(question.id, question.owner_id)

    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "洗了掉色厉害，涤纶的")
    app.save_escalate_note(session.id, "（模拟）涤纶掉色，现有产品无法匹配", "sales:S01")
    prepare("escalate_need", f"session:{session.id}")
    req = app.escalate(session.id, "sales:S01")
    app.save_reuse_proposal(req.id, None, [], "", "离线：未检索现成产品", "pm:agent")
    app.draft_requirement(req.id, "pm:agent")
    prepare("accept_requirement", f"requirement:{req.id}")
    rd = req.assigned_rd
    app.accept_requirement(req.id, rd)
    app.translate_requirement(req.id, rd)
    prepare("confirm_translation", f"requirement:{req.id}")
    req = app.confirm_translation(req.id, rd)
    assert req.product_id == f"proj:{req.id}"
    app.record_requirement_trial(req.id, "pass", rd)                       # 按旧条件（涤纶）通过
    prepare("market_eval", f"requirement:{req.id}")
    app.record_market_eval(req.id, "fail", "（模拟）客户说布其实是锦纶氨纶", "sales:S01", missing_slots=["fiber"])
    prepare("trial_rework", f"requirement:{req.id}")
    app.rework_requirement(req.id, rd)
    clock.advance_to(clock.now() + timedelta(hours=1))
    app.add_turn(session.id, "customer", "其实是锦纶氨纶的")
    returned = app.requirement_view(req.id, rd).requirement
    assert returned.known_slots["fiber"] == "锦纶氨纶"
    assert [i for i in returned.product_lang if i.slot == "fiber"][0].text == "条件：锦纶氨纶"
    app.translate_requirement(req.id, rd)
    prepare("confirm_translation", f"requirement:{req.id}")
    app.confirm_translation(req.id, rd)
    app.record_requirement_trial(req.id, "pass", rd)                       # 按更正后的条件通过
    prepare("market_eval", f"requirement:{req.id}")
    app.record_market_eval(req.id, "pass", "（模拟）客户试用通过", "sales:S01")
    app.save_points_draft(req.id, "（模拟）改善锦纶氨纶色牢度。", [], rd)
    prepare("seal_points", f"requirement:{req.id}")
    app.set_public_points(req.id, "（模拟）改善锦纶氨纶色牢度。", [], rd)
    sheet = app.package_sheet(req.id, "pm:agent")
    assert "锦纶氨纶" in sheet.usage and "涤纶" not in sheet.usage
    prepare("release", f"requirement:{req.id}")
    released = app.release_product(req.id, rd, name="（模拟）锦氨固色剂 T-901", category="固色剂")
    assert (released.name, released.category) == ("（模拟）锦氨固色剂 T-901", "固色剂")
    assert released.situations[0].conditions["fiber"] == ["锦纶氨纶"]
    assert "未转译" not in released.mechanism
    origin = app._sessions[session.id]
    assert origin.status == "recommended" and origin.recommendation.product_id == released.id
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "洗了掉色厉害，涤纶的")
    assert other.recommendation is None or other.recommendation.product_id != released.id


def test_trial_risk_counts_required_conditions_never_obtained(tmp_path):
    """V9.6a：试样前风险既数客户答过「不清楚」的必问条件，也数一直没取得的；配置可以停用某个觉家族。"""
    from huayan.jue.state import requirement_state
    from huayan.contracts import Actor
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), jue_off=["leak_risk"])
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    assert all(t.family != "leak_risk" for m in (app.jue_realtime, app.jue_scheduled) for t in m.templates.values())

    def prepare(family, object_id):
        question = next(q for q in app.bus.list(family=family) if q.object_id == object_id)
        app.mark_prepared(question.id, question.owner_id)

    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "洗了掉色厉害，涤纶的")
    app.save_escalate_note(session.id, "（模拟）涤纶掉色，现有产品无法匹配", "sales:S01")
    prepare("escalate_need", f"session:{session.id}")
    req = app.escalate(session.id, "sales:S01")
    app.save_reuse_proposal(req.id, None, [], "", "离线：未检索现成产品", "pm:agent")
    app.draft_requirement(req.id, "pm:agent")
    prepare("accept_requirement", f"requirement:{req.id}")
    app.accept_requirement(req.id, req.assigned_rd)
    app.translate_requirement(req.id, req.assigned_rd)
    prepare("confirm_translation", f"requirement:{req.id}")
    app.confirm_translation(req.id, req.assigned_rd)
    assert not app.bus.list(family="trial_risk")
    # 纤维（掉色的必问条件）从没取得过：单上没有、客户也没答过「不清楚」
    app._requirements[req.id].known_slots.pop("fiber")
    app._sessions[session.id].need.slots.pop("fiber")
    state = requirement_state(app._requirements[req.id], app._sessions[session.id].need,
                              app.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")),
                              app.kb, get_clock().now(), app.events)
    attrs = state.objects[f"requirement:{req.id}"].attrs
    assert (attrs["n_unknown_required"], attrs["n_missing_required"]) == (0, 1)
    app._after(req_ids=[req.id])
    risk = next(q for q in app.bus.list(family="trial_risk") if q.object_id == f"requirement:{req.id}")
    assert any("还没取得 1 个" in e.summary for e in risk.evidence)
