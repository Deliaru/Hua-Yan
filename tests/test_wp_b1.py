import json
from datetime import timedelta
from pathlib import Path

from huayan.bus import QuestionBus
from huayan.contracts import (KnowledgeUnit, NeedState, PointsDraft, Question, ReqItem, Requirement,
                              Resolution, ReuseProposal, Session, SheetDraft, Trial)
from huayan.events import EventLog
from huayan.escalation.translate import leak_hits
from huayan.jev.system1 import MockSystem1Client
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import ask_hints
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
    escalate = lambda i, cust, ph, known: events.append(
        "escalate", "sales:S01", {"question_id": f"q:x{i}", "phenomenon": ph, "known": known,
                                  "customer_id": cust, "p_none": 0.8},
        session_id=f"sess:{i}", ts=t0 + timedelta(hours=5 * i))
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
    model = JueProto(TEMPLATES, system1, "scheduled", meter)
    at = t0 + timedelta(days=2)
    published = scan(events, at, model, mini_seeds, mini_seeds.products, load_templates(TEMPLATES), bus, 0.5)
    assert [(q.family, q.object_id, q.owner_role, q.scored_by) for q in published] == [
        ("opportunity", TARGET, "pm", "rule")]
    assert published[0].refs["session_ids"] == "sess:0,sess:1,sess:2,sess:3"
    assert scan(events, at, model, mini_seeds, mini_seeds.products, load_templates(TEMPLATES), bus, 0.5) == []

    need = NeedState(session_id="sess:20", customer_id="customer:C01", sales_id="sales:S01", phenomenon="color_unlevel")
    hints, out = ask_hints(need, mini_seeds, mini_seeds.products, JueProto(TEMPLATES, system1, "realtime", meter), 0.5)
    assert {h.slot for h in hints} == {"fiber", "equipment"} and out.scored_by == "rule"

    # 未匹配时，0 对 0 不能成为升级信号；别的会话与未来事件不能污染当前判断。
    session = Session(id=need.session_id, customer_id=need.customer_id, sales_id=need.sales_id,
                      started_at=t0, need=need, hints=hints)
    session_events = EventLog()
    before = session.model_dump()
    state = session_state(session, session_events, t0)
    assert state.mode == "realtime" and list(state.objects) == ["session:sess:20"]
    attrs = state.objects["session:sess:20"].attrs
    assert not attrs["matched"] and not attrs["top_is_none"]
    assert attrs["p_none"] == attrs["p_top"] == attrs["n_candidates"] == 0
    assert attrs["n_open_asks"] == 2 and not attrs["decrypt_requested"]

    match_payload = {"phenomenon": "color_unlevel", "known": {}, "customer_id": need.customer_id,
                     "candidate_ids": ["T-101", "T-205"], "p_choice": {"T-101": 0.2, "T-205": 0.4},
                     "p_none": 0.4, "scored_by": "mock"}
    session_events.append("match", "sales:S01", match_payload, session_id=session.id, ts=t0)
    # 补录更早的事件，仍须选择业务时间最新的匹配。
    product_wins = {**match_payload, "p_choice": {"T-101": 0.1, "T-205": 0.8}, "p_none": 0.1}
    session_events.append("match", "sales:S01", product_wins, session_id=session.id,
                          ts=t0 - timedelta(minutes=1))
    session_events.append("match", "sales:S02", product_wins, session_id="sess:other", ts=t0)
    session_events.append("match", "sales:S01", product_wins, session_id=session.id,
                          ts=t0 + timedelta(minutes=1))
    decrypt = {"question_id": "q:decrypt", "customer_id": need.customer_id, "product_id": "T-205"}
    session_events.append("decrypt_request", "sales:S02", decrypt, session_id="sess:other", ts=t0)
    session_events.append("decrypt_request", "sales:S01", decrypt, session_id=session.id,
                          ts=t0 + timedelta(minutes=1))
    attrs = session_state(session, session_events, t0).objects["session:sess:20"].attrs
    assert attrs["matched"] and attrs["top_is_none"]  # 并列也按契约 >= 提出升级信号
    assert attrs["p_none"] == attrs["p_top"] == 0.4 and attrs["n_candidates"] == 2
    assert not attrs["escalated"] and not attrs["recommended"] and not attrs["decrypt_requested"]
    assert session.model_dump() == before  # 发现只读，不改状态或清理日志
    assert len(session_events.events) == 6

    session.status = "recommended"
    attrs = session_state(session, session_events, t0 + timedelta(minutes=1)).objects["session:sess:20"].attrs
    assert attrs["p_top"] == 0.8 and not attrs["top_is_none"]
    assert attrs["recommended"] and attrs["decrypt_requested"]
    # 同时刻后写的匹配覆盖前一条；零候选也是有效匹配，但签字前仍不算升级。
    session_events.append("match", "sales:S01", {**match_payload, "candidate_ids": [], "p_choice": {}, "p_none": 1.0},
                          session_id=session.id, ts=t0 + timedelta(minutes=1))
    session.status = "open"
    attrs = session_state(session, session_events, t0 + timedelta(minutes=1)).objects["session:sess:20"].attrs
    assert attrs["top_is_none"] and attrs["n_candidates"] == attrs["p_top"] == 0
    assert not attrs["escalated"]
    session.status = "escalated"
    assert session_state(session, session_events, t0 + timedelta(minutes=1)).objects["session:sess:20"].attrs["escalated"]

    _check_requirement_states(mini_seeds, t0)

    # 觉零大模型调用：计量里只有 jue 记录，且觉的源码不引用网关
    assert {json.loads(line)["kind"] for line in meter.path.read_text(encoding="utf-8").splitlines()} == {"jue"}
    assert not any("huayan.gateway" in p.read_text(encoding="utf-8") for p in (ROOT / "src/huayan/jue").glob("*.py"))


def _check_requirement_states(seeds, t0):
    events = EventLog()
    kb = KnowledgeBase.from_seeds(seeds, events, AuditLog())
    need = NeedState(session_id="sess:state", customer_id="customer:C01", sales_id="sales:S01")
    req = Requirement(id="req:1", question_id="q:escalate", session_ids=[need.session_id],
                      phenomenon="color_unlevel", known_slots={"fiber": "锦纶氨纶", "equipment": "气流染色机"},
                      assigned_rd="rd:R01", status="draft", created_at=t0)
    at = t0 + timedelta(hours=4)

    def state():
        return requirement_state(req, need, seeds, kb, at, events)

    def attrs():
        return state().objects["requirement:req:1"].attrs

    initial = state()
    assert initial.objects["requirement:req:1"].object_type == "requirement"
    assert len(initial.objects) == len(seeds.slots) + 1
    assert initial.objects["slot:req:1/fiber"].attrs["filled"]  # 已知条件取需求单，不取首会话
    assert need.phenomenon is None  # 不改写传入的首会话状态
    assert attrs()["layer"] == 2 and attrs()["n_unmapped_constraints"] == 2
    assert not attrs()["reuse_checked"] and not attrs()["reuse_pending"]
    req.reuse = ReuseProposal(product_id=None)
    assert attrs()["reuse_checked"] and not attrs()["reuse_pending"]
    req.reuse = ReuseProposal(product_id="T-205", customer_note="（模拟）待研发审定")
    assert attrs()["reuse_pending"] and not attrs()["reuse_declined"]
    req.reuse.declined_reason = "（模拟）条件不适用"
    assert attrs()["reuse_declined"] and not attrs()["reuse_pending"]

    req.product_lang = [ReqItem(text="（模拟）面料约束", slot="fiber", quote_refs=["turn:1"]),
                        ReqItem(text="（模拟）无原话的条目")]
    assert attrs()["n_unmapped_constraints"] == 1 and attrs()["n_unquoted_items"] == 1
    req.return_notes.append("（模拟）请补齐设备约束")
    events.append("requirement_returned", "rd:R01", {"requirement_id": req.id, "reason": req.return_notes[0]},
                  ts=t0 + timedelta(hours=1))
    assert attrs()["n_returns"] == 1 and attrs()["hours_in_status"] == 4

    req.status = "rd_accepted"
    events.append("requirement_accepted", "rd:R01", {"requirement_id": req.id}, ts=t0 + timedelta(hours=1))
    events.append("requirement_edited", "rd:R01", {"requirement_id": req.id}, ts=t0 + timedelta(hours=3))
    old = next(t for t in seeds.translations if t.id == "tr:4")
    l2 = next(t for t in seeds.translations if t.id == "tr:1")
    novel = "（模拟）新增加的低温稳定性约束"
    req.chem_lang = [
        ReqItem(text=f"『{old.scene_phrase}』→ {old.chem_term}", slot="fiber", quote_refs=["turn:1"], edited_by="rd:R01"),
        ReqItem(text=f"{old.chem_term}；{novel}", quote_refs=["turn:1"], edited_by="rd:R02"),
        ReqItem(text=l2.chem_term, quote_refs=["turn:1"], edited_by="rd:R01"),
        ReqItem(text="（模拟）Agent 新起草的内容"),
    ]
    a = attrs()
    assert a["layer"] == 3 and a["hours_in_status"] == 3
    assert a["n_unmapped_constraints"] == 0  # L3 对照 L2 的槽位，不直接对照 L1
    assert a["n_unquoted_items"] == 1 and a["n_edited_uncovered"] == 2
    assert state().objects["slot:req:1/fiber"].attrs["layer"] == 3
    skeleton = f"『{old.scene_phrase}』→ {old.chem_term}"
    for edited in (f"{novel}；{skeleton}", f"{skeleton}；{novel}", f"『{novel}』→ {old.chem_term}"):
        req.chem_lang[1].text = edited
        assert attrs()["n_edited_uncovered"] == 2, edited  # 前置、后置、引号内新增约束都不能被裁掉
    req.chem_lang[1].text = f"{novel}；{skeleton}"
    kb.add(KnowledgeUnit(id="ku:translation:state", level=3, kind="translation", title="（模拟）低温稳定",
                         text=f"（模拟）低温稳定 → {novel}", owner="rd:R02", created_at=at, source="contributed"))
    events.append("knowledge_contributed", "rd:R02", {"requirement_id": req.id, "ku_id": "ku:translation:state"}, ts=at)
    events.append("knowledge_contributed", "rd:R02", {"requirement_id": "req:10", "ku_id": "ku:other"}, ts=at)
    assert attrs()["n_edited_uncovered"] == 1 and attrs()["n_contributed"] == 1  # 新约束沉淀后，保留的骨架不误报

    bus = QuestionBus(events)
    def ask(rid, slot):
        oid = f"slot:{rid}/{slot}"
        return bus.publish(Question(id="", family="ask_back", object_id=oid, title="（模拟）回问",
            owner_role="sales", owner_id="sales:S01", scored_by="rule", discoverer="jue_proto",
            dedup_key=f"ask_back:{oid}", created_at=t0))
    first, second = ask(req.id, "fiber"), ask(req.id, "equipment")
    ask("req:10", "fiber")  # 同一会话的其他需求单不能混入
    bus.resolve(first.id, Resolution(action="answered", by="sales:S01"), at)
    bus.resolve(second.id, Resolution(action="answered", by="sales:S01"), at + timedelta(hours=1))
    assert attrs()["n_open_ask_back"] == 1  # 未来关闭不计入当前快照

    def trial(tid, rid, result, hour):
        t = Trial(id=tid, product_id="T-206", requirement_id=rid, rd="rd:R01", conditions={},
                  result=result, cause="none" if result == "pass" else "product", at=t0 + timedelta(hours=hour))
        kb.add(KnowledgeUnit(id=f"ku:trial:{tid}", level=3, kind="trial", title="（模拟）试样",
                             text=t.model_dump_json(), owner=t.rd, product_id=t.product_id, created_at=t.at))
    trial("trial:1", req.id, "pass", 1)
    trial("trial:2", req.id, "fail", 2)
    trial("trial:other", "req:10", "pass", 3)
    trial("trial:future", req.id, "pass", 5)
    events.append("market_eval", "sales:S01", {"requirement_id": req.id, "trial_id": "trial:1", "result": "pass"}, ts=at)
    a = attrs()
    assert a["n_trials"] == 2 and not a["trial_passed"] and a["market_eval"] == "pass"
    trial("trial:3", req.id, "pass", 3)
    assert attrs()["trial_passed"] and attrs()["market_eval"] == "none"  # 旧试样评价不串到新试样
    events.append("market_eval", "sales:S01", {"requirement_id": "req:10", "trial_id": "trial:3", "result": "fail"}, ts=at)
    assert attrs()["market_eval"] == "none"
    events.append("market_eval", "sales:S01", {"requirement_id": req.id, "trial_id": "trial:3", "result": "pass"}, ts=at)
    events.append("market_eval", "sales:S01", {"requirement_id": req.id, "trial_id": "trial:3", "result": "fail"},
                  ts=at + timedelta(hours=1))
    assert attrs()["market_eval"] == "pass"

    req.status = "rd_confirmed"
    events.append("requirement_translated", "rd:R01", {"requirement_id": req.id}, ts=t0 + timedelta(hours=2))
    req.points_draft = PointsDraft(public="（模拟）公开效果", sealed=["（模拟）内部机理"])
    assert not attrs()["points_set"] and attrs()["n_sealed"] == 0
    req.public_points, req.sealed = req.points_draft.public, list(req.points_draft.sealed)
    events.append("points_set", "rd:R01", {"requirement_id": req.id, "n_sealed": 1}, ts=at)
    req.sheet = SheetDraft(sheet="（模拟）公开说明", usage="（模拟）先试样")
    final = state()
    a = final.objects["requirement:req:1"].attrs
    assert len(final.objects) == 1 and a["layer"] == 0 and a["hours_in_status"] == 2
    assert a["points_set"] and a["sheet_ready"] and a["n_sealed"] == 1
    assert a["n_unquoted_items"] == a["n_unmapped_constraints"] == a["n_leak_hits"] == 0
    assert not any(secret in final.model_dump_json() for secret in (novel, req.sealed[0], old.chem_term))
    # 同句同时命中封存项、L3 译文和假设，只计一句；说明书和用法均参与检查。
    req.sealed = [old.chem_term]
    req.hypotheses = [f"参考 T-205 的机理：{old.chem_term}"]
    raw = leak_hits(old.chem_term + "\n" + old.chem_term, req.sealed, req.hypotheses, kb)
    assert {(h.index, h.source) for h in raw} == {
        (i, source) for i in (0, 1) for source in ("sealed", "l3_term", "hypothesis")}
    for sheet, usage, expected in ((old.chem_term, old.chem_term, 2), (old.chem_term, "", 1),
                                   ("", old.chem_term, 1), (l2.chem_term, "（模拟）先试样", 0)):
        req.sheet = SheetDraft(sheet=sheet, usage=usage)
        checked = state()
        assert checked.objects["requirement:req:1"].attrs["n_leak_hits"] == expected
        assert old.chem_term not in checked.model_dump_json()  # 状态只带计数，不携带命中原文
    req.sheet = None
    assert attrs()["n_leak_hits"] == 0
    before, n_events = req.model_dump(), len(events.events)
    state()
    assert req.model_dump() == before and len(events.events) == n_events
    for status in ("released", "rejected", "reused", "merged"):
        req.status = status
        assert state().objects == {}
