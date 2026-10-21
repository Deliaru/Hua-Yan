import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest

from huayan.bus import QuestionBus
from huayan.contracts import (Capability, JueObject, JueOutput, JueRecord, JueState, NeedState, Requirement, ReuseProposal,
                              ScoredDecision, Session)
from huayan.events import EventLog
from huayan.jev.system1 import MockSystem1Client
from huayan.jue.expr import evaluate
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import ask_hints, publish
from huayan.jue.records import decision_rows, rows_for
from huayan.jue.scan import scan
from huayan.jue.state import collect_scheduled, requirement_state, session_state
from huayan.jue.train import fit
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

    # 模板目录：Q2 新增 qi_grant、qi_review，Q5.5 新增 trial_rework，v8 新增 trial_risk、stale_capability，共 24 个；自动动作仍只有两种。
    templates = load_templates(TEMPLATES)
    assert len({t.family for t in templates.values()}) == 24
    assert {t.auto_action for t in templates.values() if t.auto_action} == {"escalate", "assign_sales"}
    for name in ("b1_required", "b2_info_value", "rule_alert"):
        load_templates(ROOT / "config" / "baselines" / name)

    # v8 判断过时：研发签出两条说明书没有声称的适用判断（锦纶氨纶），knowledge_conflict 不管；一条之后 3 次在气流染色机上因产品本身失败，另一条只有 1 次设备原因失败
    stale_events, caps = EventLog(), [Capability(id=f"cap:{i}", form="applicable", audience=0, payload={
        "product_id": pid, "phenomenon": "color_unlevel", "conditions": {"fiber": ["锦纶氨纶"]}},
        based_on=["ku:claim:1"], granted_by="rd:R01", approved_by="pm:P01", status="active", at=t0)
        for i, pid in ((1, "T-101"), (2, "T-301"))]
    for i, (cap, equipment, result, cause) in enumerate([*[(caps[0], "气流染色机", "fail", "product")] * 3,
            (caps[0], "溢流染色机", "pass", "none"), (caps[1], "气流染色机", "fail", "equipment"),
            (caps[1], "溢流染色机", "pass", "none")]):
        ts = t0 + timedelta(days=1 + i)
        stale_events.append("capability_used", "sales:S01", {"capability_id": cap.id}, session_id=f"sess:s{i}", ts=ts)
        stale_events.append("trial", "rd:R01", {"trial_id": f"t{i}", "product_id": cap.payload["product_id"],
            "conditions": {"fiber": "锦纶氨纶", "equipment": equipment}, "result": result, "cause": cause}, ts=ts)
    state, refs = collect_scheduled(stale_events, t0 + timedelta(days=8), mini_seeds, mini_seeds.products, caps=caps)
    found = publish(model.propose(state), state, templates, QuestionBus(stale_events), 0.5, seeds=mini_seeds, refs=refs)
    assert [(q.family, q.object_id, q.signer_id) for q in found] == [
        ("stale_capability", "knowledge:stale:cap:1", "rd:R01")]
    assert found[0].refs["fail_values"] == "equipment=气流染色机"     # 范围里只有一个取值的纤维不算

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


    # Q6 决策投影：一行 = 觉提出的一个决策点；标签只来自人的处置与试样 / 评价结果，层级不低于判断层
    def slot(oid, judge, **attrs):
        return JueObject(object_id=oid, object_type="slot", attrs={"layer": 1, "slot": "fiber", "phenomenon": "color_unlevel",
                                                                   "judge_level": judge} | attrs)
    objects = {o.object_id: o for o in (slot("slot:sess:a/fiber", 0), slot("slot:sess:b/fiber", 1),
                                        *(slot(f"slot:req:{i}/equipment", 3, layer=3, slot="equipment") for i in (7, 8, 9)))}
    record = JueRecord(state=JueState(at=t0, mode="realtime", objects=objects), output=JueOutput(
        at=t0, mode="realtime", model="jue_proto", scored_by="rule",
        decisions=[ScoredDecision(family="ask_slot" if "sess" in oid else "ask_back", object_id=oid, p_need=0.7)
                   for oid in objects]))
    log = EventLog()
    for qid, oid, by, action in (("q:7", "slot:req:7/equipment", "rd:R01", "dismiss"),
                                 ("q:8", "slot:req:8/equipment", "pm:agent", "answered"),
                                 ("q:9", "slot:req:9/equipment", "customer:C01", "answered")):
        log.append("question_published", "jue", {"question_id": qid, "family": "ask_back", "object_id": oid,
                                                 "template_id": "ask_back"}, ts=t0)
        log.append("question_resolved", by, {"question_id": qid, "family": "ask_back", "object_id": oid,
                                             "template_id": "ask_back", "action": action, "by": by}, ts=t0 + timedelta(hours=1))
    log.append("trial", "rd:R01", {"requirement_id": "req:9", "result": "fail", "cause": "requirement",
                                   "missing_slots": ["equipment"]}, ts=t0 + timedelta(hours=2))
    rows = decision_rows([record], log)
    # 追问是提示、没有人的处置，标签留空；Agent 的处置不当标签；客户回答研发的回问，结果仍属 L3
    assert [(r["family"], r["label"], r["judge_level"], r["level"]) for r in rows] == [
        ("ask_slot", None, 0, 0), ("ask_slot", None, 1, 1), ("ask_back", 0, 3, 3), ("ask_back", None, 3, None),
        ("ask_back", 1, 3, 3), ("ask_back", 1, 3, 3)]
    assert [r["object_id"] for r in rows_for(rows, 0)] == ["slot:sess:a/fiber"]     # 研发回问的结果行不进客户层

    # Q6 隔离：ask_slot|L0 训练一次；再加入 L1、L2 的行与「判断层 0、结果来自 L3」的行重训，L0 的分数逐条不变
    rng = np.random.default_rng(0)
    def synth(n, judge, level, flip, tag):
        out = []
        for i in range(n):
            p = float(rng.random())         # 规则看不到的信号：模型赢了规则才会保存这一格
            attrs = {"layer": 1, "filled": False, "unknown": False, "asked": 0, "phenomenon": "color_unlevel", "slot": "fiber",
                     "splits": 2, "required": False, "prior_top": float(rng.random()), "p_fix": p, "judge_level": judge}
            out.append({"family": "ask_slot", "object_type": "slot", "object_id": f"slot:{tag}{i}/fiber", "attrs": attrs,
                        "label": int((p > 0.5) != flip), "judge_level": judge, "level": level})
        return out
    base = synth(600, 0, 0, False, "a")
    fixed = {f"slot:f{i}/fiber": JueObject(object_id=f"slot:f{i}/fiber", object_type="slot",
                                           attrs=base[0]["attrs"] | {"p_fix": i / 10}) for i in range(11)}

    def ask_scores(rows, out):
        summary = fit(rows, TEMPLATES, out)
        decided = JueK(out, TEMPLATES).propose(JueState(at=t0, mode="realtime", objects=fixed)).decisions
        return summary, [(d.p_need, d.scored_by) for d in decided if d.family == "ask_slot"]
    first, before = ask_scores(base, tmp_path / "k1")
    second, after = ask_scores(base + synth(300, 1, 1, True, "b") + synth(300, 2, 2, True, "c") + synth(300, 0, 3, True, "d"),
                              tmp_path / "k2")
    assert first["ask_slot|L0"]["scored_by"] == second["ask_slot|L0"]["scored_by"] == "jue_k"
    assert {"ask_slot|L1", "ask_slot|L2"} <= set(second) and len(before) == 11 and before == after
    # L1 同理：判断层 1、结果来自 L2 / L3 的行不改变 ask_slot|L1 的分数
    fixed = {k: o.model_copy(update={"attrs": o.attrs | {"judge_level": 1}}) for k, o in fixed.items()}
    rows = base + synth(300, 1, 1, True, "b") + synth(300, 2, 2, True, "c")
    _, before = ask_scores(rows, tmp_path / "k3")
    third, after = ask_scores(rows + synth(300, 1, 2, False, "e") + synth(300, 1, 3, False, "f"), tmp_path / "k4")
    assert third["ask_slot|L1"]["scored_by"] == "jue_k" and before == after and {s for _, s in after} == {"jue_k"}
