import json
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit, Trial


def test_mainline_offline(tmp_path):
    """真实觉提出 → Hub 离线准备 → 人签字；含合并后重派、回问与发布回流。"""
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))

    # 1 短路径：觉提示追问 → 推荐
    s1 = app.start_session("customer:C01", "sales:S01").id
    assert {h.slot for h in app.add_turn(s1, "customer", "深一块浅一块").hints} == {"fiber", "equipment"}
    assert app.add_turn(s1, "customer", "锦氨的，溢流缸").recommendation.product_id == "T-205"
    assert all(s.level == 1 for s in app.view_session(s1, "sales:S01").card.sections)
    assert any(s.level == 3 for s in app.view_session(s1, "rd:R01").card.sections)

    def prepared(family, object_id):
        app.tick()
        question = next(q for q in app.bus.list(family=family) if q.object_id == object_id)
        assert question.prepared_at is not None
        return question

    # 两位客户各自升级，Hub 查无复用并起草；人尚未接单。
    sessions, reqs = [], []
    for customer in ["customer:C02", "customer:C03"]:
        sid = app.start_session(customer, "sales:S01").id
        assert app.add_turn(sid, "customer", "深一块浅一块，锦氨的，气流缸").status == "open"
        prepared("escalate_need", f"session:{sid}")
        req = app.escalate(sid, "sales:S01")
        prepared("accept_requirement", f"requirement:{req.id}")
        sessions.append(sid)
        reqs.append(req)
    opportunity = app.bus.list(family="opportunity")[0]
    assert opportunity.prepared_at is not None
    main, member = reqs
    draft = app.requirement_view(main.id, "pm:agent").requirement
    assert draft.merge_from == [member.id] and "离线模式" in draft.merge_note
    rd = main.assigned_rd
    main = app.merge_requirements(opportunity.id, rd)
    assert main.status == "draft" and not main.product_lang
    assert set(main.session_ids) == set(sessions)
    assert app.requirement_view(member.id, rd).requirement.status == "merged"
    assert not any(q.refs.get("requirement_id") == member.id for q in app.bus.list())
    accept = next(q for q in app.bus.list(family="accept_requirement") if q.refs["requirement_id"] == main.id)
    assert accept.prepared_at is None
    prepared("accept_requirement", f"requirement:{main.id}")
    main = app.requirement_view(main.id, rd).requirement
    refs = {ref for item in main.product_lang for ref in item.quote_refs}
    assert all(any(t.id in refs for t in app.view_session(sid, rd).turns) for sid in sessions)
    assert len([e for e in app.events.query(["question_prepared"]) if e.payload["question_id"] == accept.id]) == 2
    app.accept_requirement(main.id, rd)

    # L3 骨架引出回问；回答后重派同一个确认问题，保留研发改过的条目。
    app.kb.add(KnowledgeUnit(id="ku:translation:tr:e2e", level=3, kind="translation", title="无APEO",
        text="无APEO → （模拟）不得使用烷基酚聚氧乙烯醚类乳化组分", phenomenon_ids=["color_unlevel"],
        owner="rd:R02", created_at=get_clock().now()))
    confirm = prepared("confirm_translation", f"requirement:{main.id}")
    req = app.requirement_view(main.id, rd).requirement
    edited = req.chem_lang[0].model_copy(update={"text": req.chem_lang[0].text + "；验证低浴比稳定性", "edited_by": rd})
    app.edit_req_item(req.id, 0, edited, rd)
    ask = next(q for q in app.bus.list(family="ask_back") if q.refs["requirement_id"] == req.id)
    assert ask.refs["slot"] == "constraint" and ask.refs["session_id"] == sessions[0]
    assert ask.prepared_at is None
    conv = app.agents.conversations("sales:S01")
    assert any(c.session_id == sessions[0] and any(ask.id in m.text for m in c.messages) for c in conv)
    app.add_turn(sessions[0], "sales", "有没有环保方面的要求？")
    app.add_turn(sessions[0], "customer", "不要APEO")
    assert app.bus.get(ask.id).resolution.action == "answered" and confirm.prepared_at is None
    prepared("confirm_translation", f"requirement:{req.id}")
    req = app.requirement_view(req.id, rd).requirement
    assert req.known_slots["constraint"] == "无APEO"
    assert any(i.text == edited.text and i.edited_by == rd for i in req.chem_lang)
    assert any("ku:translation:tr:e2e" in i.ku_refs for i in req.chem_lang)
    app.confirm_translation(req.id, rd)

    # 试样、客户评价、两栏签字、包装发布；每次签字都有真实待签问题。
    req = app.requirement_view(req.id, rd).requirement
    app.record_trial(Trial(id="trial:e2e", product_id=req.product_id, requirement_id=req.id, rd=rd,
        conditions=req.known_slots, result="pass", cause="none", at=get_clock().now()))
    prepared("market_eval", f"requirement:{req.id}")
    app.record_market_eval(req.id, "pass", "（模拟）客户试用通过", "sales:S01")
    prepared("seal_points", f"requirement:{req.id}")
    app.set_public_points(req.id, "（模拟）改善低浴比匀染；按工艺试样确认。", [], rd)
    prepared("release", f"requirement:{req.id}")
    app.release_product(req.id, rd)
    s4 = app.start_session("customer:C01", "sales:S01").id
    assert app.add_turn(s4, "customer", "锦氨布气流缸里染，深一块浅一块，不要APEO").recommendation.product_id == "T-206"
    assert not app.events.query(["human_decision"])
    before = len(app.events.query(["question_prepared"]))
    app.tick()
    assert len(app.events.query(["question_prepared"])) == before

    meter = [json.loads(line) for line in (app.run_dir / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["caller"].startswith("jue:") for r in meter)
    assert not any(r["kind"] == "llm" and r["caller"].startswith("jue:") for r in meter)
