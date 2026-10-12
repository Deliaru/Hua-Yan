import json
from datetime import timedelta
from pathlib import Path

import pytest

from huayan.bus import QuestionBus
from huayan.contracts import NeedState, Requirement, ReuseProposal, ScoredDecision, Session
from huayan.events import EventLog
from huayan.jev.system1 import MockSystem1Client
from huayan.jue.expr import evaluate
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import ask_hints, publish
from huayan.jue.scan import scan
from huayan.jue.state import requirement_state, session_state
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.meter import FileMeter

ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / "config" / "templates"
TARGET = "theme:color_unlevel|equipment=气流染色机,fiber=锦纶氨纶"


def test_scan_finds_injection_and_asks_without_llm(mini_seeds, sim_clock, tmp_path):
    meter = FileMeter(tmp_path, "t")
    system1 = MockSystem1Client(meter)        # 不是 OneJev：觉必须走规则分，不调用任何模型
    events, t0 = EventLog(), sim_clock.now()
    def escalate(i, cust, ph, known):
        ts = t0 + timedelta(hours=5 * i)
        events.append("requirement_created", "sales:S01", {"requirement_id": f"req:{i}", "question_id": f"q:x{i}",
            "phenomenon": ph, "session_ids": [f"sess:{i}"], "assigned_rd": "rd:R01"}, ts=ts)
        events.append("escalate", "sales:S01", {"question_id": f"q:x{i}", "requirement_id": f"req:{i}",
            "phenomenon": ph, "known": known, "customer_id": cust, "p_none": 0.8},
            session_id=f"sess:{i}", ts=ts)
        events.append("reuse_proposed", "pm:agent", {"requirement_id": f"req:{i}", "product_id": None,
                                                     "ku_refs": []}, ts=ts)
    # 注入：3 个客户 4 次「锦纶氨纶 + 气流染色机」色花升级
    for i, cust in enumerate(["customer:C01", "customer:C02", "customer:C03", "customer:C02"]):
        escalate(i, cust, "color_unlevel", {"fiber": "锦纶氨纶", "equipment": "气流染色机"})
    # 困难负样本：同一个客户就另一个无解需求反复升级 3 次；同现象 3 次成功推荐 T-205
    for i in range(4, 7):
        escalate(i, "customer:C01", "poor_fastness", {"fiber": "涤纶"})
    for i in range(7, 10):
        events.append("recommend", "sales:S02",
                      {"product_id": "T-205", "version": "product_usage", "p_choice": 0.8, "candidate_ids": ["T-205"],
                       "phenomenon": "color_unlevel", "known": {"fiber": "锦纶氨纶", "equipment": "溢流染色机"},
                       "customer_id": f"customer:C0{i - 6}"}, session_id=f"sess:{i}", ts=t0 + timedelta(hours=5 * i))

    bus = QuestionBus(events)
    templates_all = {t.family: t for t in load_templates(TEMPLATES).values()}
    model = JueProto(TEMPLATES, system1, "scheduled", meter)
    at = t0 + timedelta(days=2)
    published = scan(events, at, model, mini_seeds, mini_seeds.products, load_templates(TEMPLATES), bus, 0.5)
    assert [(q.family, q.object_id, q.owner_id, q.signer_id, q.scored_by) for q in published] == [
        ("opportunity", TARGET, "pm:agent", "pm:P01", "rule")]
    assert published[0].refs["session_ids"] == "sess:0,sess:1,sess:2,sess:3"
    assert published[0].refs["requirement_ids"] == "req:0,req:1,req:2,req:3"
    assert scan(events, at, model, mini_seeds, mini_seeds.products, load_templates(TEMPLATES), bus, 0.5) == []

    need = NeedState(session_id="sess:20", customer_id="customer:C01", sales_id="sales:S01", phenomenon="color_unlevel")
    hints, out = ask_hints(need, mini_seeds, mini_seeds.products, JueProto(TEMPLATES, system1, "realtime", meter), 0.5)
    assert {h.slot for h in hints} == {"fiber", "equipment"} and out.scored_by == "rule"

    # 会话：最近一次 match 中「都不合适」最高 → top_is_none（escalate_need 的信号）
    session = Session(id=need.session_id, customer_id=need.customer_id, sales_id=need.sales_id,
                      started_at=t0, need=need, hints=hints)
    session_events = EventLog()
    session_events.append("match", "sales:S01", {"phenomenon": "color_unlevel", "known": {},
        "customer_id": need.customer_id, "candidate_ids": ["T-205"], "p_choice": {"T-205": 0.2},
        "p_none": 0.8, "scored_by": "mock"}, session_id=session.id, ts=t0)
    attrs = session_state(session, session_events, t0).objects["session:sess:20"].attrs
    assert attrs["top_is_none"] and not attrs["escalated"]
    # 升级后现成产品被采用、会话变为 recommended：仍算已升级，escalate_need 不再到点
    session_events.append("escalate", "sales:S01", {"requirement_id": "req:20"}, session_id=session.id, ts=t0)
    session.status = "recommended"
    attrs = session_state(session, session_events, t0).objects["session:sess:20"].attrs
    assert attrs["escalated"] and not evaluate(templates_all["escalate_need"].precondition, attrs, boolean=True)

    # 模板目录：19 个 family（v6 新增 route_rd、handoff_sales、scope_update、contribution_pm）；基线三个目录也能加载
    templates = load_templates(TEMPLATES)
    assert len({t.family for t in templates.values()}) == 19
    for name in ("b1_required", "b2_info_value", "rule_alert"):
        load_templates(ROOT / "config" / "baselines" / name)

    # 需求单 4 个状态只到点对应的推进决策
    kb = KnowledgeBase.from_seeds(mini_seeds, EventLog(), AuditLog())
    req = Requirement(id="req:1", question_id="q:1", session_ids=[need.session_id], phenomenon="color_unlevel",
                      known_slots={}, assigned_rd="rd:R01", status="draft", created_at=t0)
    req_templates = [t for t in templates.values() if t.object_type == "requirement"]

    def due():
        attrs = requirement_state(req, need, mini_seeds, kb, t0, EventLog()).objects["requirement:req:1"].attrs
        return [t.family for t in req_templates if evaluate(t.precondition, attrs, boolean=True)]
    assert due() == ["reuse_product"]
    req.reuse = ReuseProposal(product_id=None)
    assert due() == ["accept_requirement"]
    req.reuse = ReuseProposal(product_id="T-205", customer_note="（模拟）待研发审定")
    assert due() == []
    req.status = "rd_accepted"
    assert due() == ["confirm_translation"]

    # 发布：需求单问题按解析表填主人与签字人；引用未加载 family 的决策被拒
    state = requirement_state(req, need, mini_seeds, kb, t0, EventLog())
    out = JueProto(TEMPLATES, system1, "realtime", meter).propose(state)
    refs = {oid: {"session_id": need.session_id, "sales_id": need.sales_id, "assigned_rd": req.assigned_rd}
            for oid in state.objects}
    [q] = [q for q in publish(out, state, templates, bus, 0.5, seeds=mini_seeds, refs=refs)
           if q.object_id == "requirement:req:1"]
    assert (q.family, q.owner_id, q.signer_id, q.refs["requirement_id"]) == (
        "confirm_translation", "rd:R01", "rd:R01", "req:1")
    rogue = out.model_copy(update={"decisions": [ScoredDecision(family="approve_project", object_id="requirement:req:1",
                                                                p_need=1.0)]})
    with pytest.raises(ValueError):
        publish(rogue, state, templates, bus, 0.5, seeds=mini_seeds, refs=refs)

    # 觉零大模型调用：计量里只有 jue 记录，且觉的源码不引用网关
    assert {json.loads(line)["kind"] for line in meter.path.read_text(encoding="utf-8").splitlines()} == {"jue"}
    assert not any("huayan.gateway" in p.read_text(encoding="utf-8") for p in (ROOT / "src/huayan/jue").glob("*.py"))

