import json
from datetime import timedelta
from pathlib import Path

from huayan.bus import QuestionBus
from huayan.contracts import NeedState, Session
from huayan.events import EventLog
from huayan.jev.system1 import MockSystem1Client
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import ask_hints
from huayan.jue.scan import scan
from huayan.jue.state import session_state
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

    # 觉零大模型调用：计量里只有 jue 记录，且觉的源码不引用网关
    assert {json.loads(line)["kind"] for line in meter.path.read_text(encoding="utf-8").splitlines()} == {"jue"}
    assert not any("huayan.gateway" in p.read_text(encoding="utf-8") for p in (ROOT / "src/huayan/jue").glob("*.py"))
