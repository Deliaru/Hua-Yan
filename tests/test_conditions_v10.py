"""V10.6：合成授权 70—80℃，不代表真实产品的专业确认范围。"""
import json
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import CustomerProfile, ExtractedTemperature, ExtractionResult, NeedState, Turn
from huayan.contracts import Situation
from huayan.domain import consistent, match_candidates
from huayan.events import EventLog
from huayan.ingest.compile import EvidenceRef, Proposal, _key
from huayan.ingest.folder import FolderSource
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.l1.extract import RuleExtractor, apply_extraction, validate_extraction


def test_temperature_range_survives_capability_view_and_matches(mini_seeds):
    product = next(p for p in mini_seeds.products if p.id == "T-205")
    product.situations[0].temperature_c = (70, 80)
    kb = KnowledgeBase.from_seeds(mini_seeds, EventLog(), AuditLog())
    customer = next(a for a in mini_seeds.actors if a.id == "customer:C01")
    products = kb.view(customer).products
    known = {"fiber": "锦纶氨纶", "equipment": "溢流染色机"}
    for actual in ((75, 75), (72, 78), (70, 80)):
        [candidate] = match_candidates("color_unlevel", known, products, temperature_c=actual)
        assert candidate.status == "confirmed" and candidate.unknown_slots == []
        assert candidate.capability_id == product.situations[0].capability_id
    [unknown] = match_candidates("color_unlevel", known, products)
    assert unknown.status == "possible" and unknown.unknown_slots == ["temperature_c"]
    for actual in ((85, 85), (75, 85)):
        assert match_candidates("color_unlevel", known, products, temperature_c=actual) == []
    viewed = next(p for p in products if p.id == "T-205")
    assert consistent(viewed, known, temperature_c=(75, 75))
    assert consistent(viewed, known)
    assert not consistent(viewed, known, temperature_c=(85, 85))
    [limited] = match_candidates("color_unlevel", known, products, [unknown.capability_id], temperature_c=(75, 75))
    assert limited.status == "possible"


def test_temperature_stays_with_its_own_situation(mini_seeds):
    product = next(p for p in mini_seeds.products if p.id == "T-205")
    product.situations = [
        Situation(phenomenon="color_unlevel", conditions={"fiber": ["锦纶氨纶"]},
                  capability_id="cap:synthetic:cool", temperature_c=(70, 80)),
        Situation(phenomenon="color_unlevel", conditions={"fiber": ["涤纶"]},
                  capability_id="cap:synthetic:hot", temperature_c=(90, 100))]
    assert match_candidates("color_unlevel", {"fiber": "锦纶氨纶"}, [product], temperature_c=(95, 95)) == []
    assert not consistent(product, {"fiber": "锦纶氨纶"}, temperature_c=(95, 95))
    product.situations.append(Situation(phenomenon="color_unlevel", conditions={"fiber": ["锦纶氨纶"]},
                                       capability_id="cap:synthetic:unrestricted"))
    [candidate] = match_candidates("color_unlevel", {"fiber": "锦纶氨纶"}, [product])
    assert candidate.status == "confirmed" and candidate.capability_id == "cap:synthetic:unrestricted"


def test_compiled_temperature_survives_confirmation_grant_and_scope_approval(tmp_path):
    """合成专业签字，仅在临时实例走原有门面，不代表真实研发结论。"""
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))
    app.kb.sources = [FolderSource("合成温度资料", "internal", "tests/fixtures/reader")]
    app.revoke_capability("cap:applicable:T-205:color_unlevel", "rd:R01")
    proposal = Proposal(title="合成温度适用判断", text="合成温度适用判断，待确认", product="T-205",
        phenomenon="color_unlevel", form="applicable", author="rd:R01", conditions=["锦纶氨纶", "溢流染色机"],
        temperature_c=(70, 80), evidence=[EvidenceRef(doc_id="synthetic-temperature", span="p1", quote="适用温度70—80℃")])
    row = app.import_proposals([proposal], "rd:R01")["admitted"][0]
    source = app.kb._caps[row["capability_id"]]
    assert source.status == "proposed" and source.payload["temperature_c"] == [70, 80]
    assert app.kb._units[row["ku_id"]].status == "candidate"
    review = app.review_claims([row["ku_id"]], "rd:R01")
    app.confirm_claims(None, [row["ku_id"]], "rd:R01", review["reviewed_evidence"])

    def approve(cap_id):
        question = next(q for q in app.questions("pm:P01") if q.family == "scope_update" and q.refs["capability_id"] == cap_id)
        assert json.loads(question.refs["temperature_c"]) == [70, 80]
        app.mark_prepared(question.id, "pm:agent")
        return app.extend_scope(question.id, "合成温度范围核对", "pm:P01")

    approve(source.id)
    app.kb.explore("合成温度适用判断", app.actors["customer:C01"])
    app.scan()
    question = next(q for q in app.questions("rd:R01") if q.family == "qi_grant" and q.refs.get("capability_id") == source.id)
    assert any("70—80℃" in e.summary for e in question.evidence)
    app.mark_prepared(question.id, "rd:R01")
    granted = app.sign_qi_grant(question.id, "rd:R01")
    assert granted.audience == 0 and granted.status == "proposed" and granted.payload["temperature_c"] == [70, 80]
    assert not any(s.capability_id == granted.id for p in app.kb.view(app.actors["customer:C01"]).products for s in p.situations)
    # 真实回归：已授予、待PM批准时反复扫描不能再次催签或新增能力。
    count = len(app.kb.capabilities())
    for _ in range(2):
        app.scan()
        assert not any(q.object_id == question.object_id for q in app.bus.list(family="qi_grant"))
        assert len(app.kb.capabilities()) == count
    with pytest.raises(ValueError, match="已准备的授予问题"):
        app.sign_qi_grant(question.id, "rd:R01")
    # 修复前已经留下的旧待签卡，同样复用当前待批准项，不再次写授予事件。
    legacy = app.bus.publish(question.model_copy(update={"id": "", "status": "open", "resolution": None,
                                                        "resolved_at": None, "prepared_at": None}))
    app.mark_prepared(legacy.id, "rd:R01")
    event_count = len(app.events.query(["capability_granted"]))
    assert app.sign_qi_grant(legacy.id, "rd:R01").id == granted.id
    assert len(app.kb.capabilities()) == count
    assert len(app.events.query(["capability_granted"])) == event_count
    approved = approve(granted.id)
    assert approved.status == "active"
    for text, expected in (("75℃", "confirmed"), ("温度不知道", "possible"), ("85℃", None)):
        session = app.start_session("customer:C01", "sales:S01")
        session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，溢流缸，" + text)
        if expected is None:
            assert session.recommendation is None
        else:
            [candidate] = session.recommendation.candidates
            assert candidate.status == expected and candidate.capability_id == approved.id


def test_temperature_customer_turns_match_and_correct_current_recommendation(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path), run_id="temperature")
    # 只在合成测试实例设置授权范围，不代表真人签字。
    cap_id = "cap:applicable:T-205:color_unlevel"
    app.kb._caps[cap_id].payload["temperature_c"] = [70, 80]
    prefix = "染完布面深一块浅一块，锦纶氨纶的，溢流缸，"
    for text, expected, value in (("温度75℃", "confirmed", (75, 75)),
        ("温度72—78℃", "confirmed", (72, 78)), ("温度不清楚", "possible", None),
        ("温度85℃", None, (85, 85)), ("温度75—85℃", None, (75, 85))):
        session = app.start_session("customer:C01", "sales:S01")
        session = app.add_turn(session.id, "customer", prefix + text)
        assert session.need.known_temperature() == value
        view = app.view_session(session.id, "customer:C01")
        assert view.temperature.quote in session.turns[0].text
        assert view.temperature.turn_id == session.turns[0].id
        if expected is None:
            assert session.recommendation is None and view.card is None
            if value == (85, 85):
                session = app.add_turn(session.id, "customer", "T-205怎么用")
                assert "不适用于当前已知条件" in session.replies[-1].text
                app.save_escalate_note(session.id, "（合成）温度超出授权范围，交研发判断", "sales:S01")
                question = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
                app.mark_prepared(question.id, question.owner_id)
                app.escalate(session.id, "sales:S01")
                why = app.route_of(session.id, "customer:C01")["why"]
                excluded = next(p for p in why["excluded"] if p["product_id"] == "T-205")
                assert {"slot": "温度", "value": "85℃", "allowed": ["70—80℃"]} in excluded["mismatch"]
        else:
            [candidate] = session.recommendation.candidates
            assert candidate.status == expected and candidate.capability_id == cap_id
            assert candidate.unknown_slots == (["temperature_c"] if expected == "possible" else [])
            assert "70—80℃" in view.card.note and cap_id in view.card.note
            if expected == "possible":
                assert "请补充确认" in view.card.note and view.temperature.status == "unknown"
    session = app.start_session("customer:C02", "sales:S01")
    session = app.add_turn(session.id, "customer", prefix + "先问一下")
    assert session.need.temperature is None
    session = app.add_turn(session.id, "customer", "温度75℃")
    known = session.need.known()
    session = app.add_turn(session.id, "customer", "谢谢")
    assert session.need.known_temperature() == (75, 75)
    session = app.add_turn(session.id, "customer", "不是75℃，是85℃")
    assert session.need.known_temperature() == (85, 85) and session.recommendation is None
    session = app.add_turn(session.id, "customer", "温度其实不确定")
    assert session.need.temperature.status == "unknown" and session.need.known() == known
    assert session.recommendation.candidates[0].status == "possible"
    session = app.add_turn(session.id, "customer", "75℃")
    assert session.need.known_temperature() == (75, 75)
    for text in ("先60℃再75℃", "先60℃保温再升到75℃"):
        session = app.add_turn(session.id, "customer", text)
        assert session.need.temperature.status == "unknown"
        assert session.need.known_temperature() is None
        assert session.need.temperature.quote == text
        assert session.recommendation.candidates[0].status == "possible"
    session = app.add_turn(session.id, "customer", "不是75℃")
    assert session.need.known_temperature() is None and session.recommendation.candidates[0].status == "possible"
    for text in ("75℃不对，实际温度不清楚", "说明书写75℃，实际温度不知道",
                 "实际温度不知道，说明书写75℃", "温度75℃，不确定",
                 "实际温度不清楚，75℃", "温度不清楚，说明书确认75℃"):
        session = app.add_turn(session.id, "customer", "75℃")
        assert session.recommendation.candidates[0].status == "confirmed"
        session = app.add_turn(session.id, "customer", text)
        assert session.need.temperature.status == "unknown"
        assert session.need.known_temperature() is None and session.need.temperature.quote == text
        assert session.recommendation.candidates[0].status == "possible"
        assert session.recommendation.candidates[0].unknown_slots == ["temperature_c"]
    resumed = HuayanApp.build(str(path), run_id="temperature", resume=True)
    assert resumed._sessions[session.id].need.temperature == session.need.temperature


def test_rule_temperature_units_and_local_negation(mini_seeds):
    extractor = RuleExtractor(mini_seeds)
    prev = NeedState(session_id="sess:1", customer_id="customer:C01", sales_id=None)
    for text, expected in (("75℃", (75, 75)), ("75°C", (75, 75)), ("75摄氏度", (75, 75)),
        ("75度", None), ("水硬度10度", None), ("色牢度4度", None), ("温度75度", (75, 75)),
        ("我们温度是75℃，不是85℃", (75, 75)), ("不是75℃而是85℃", (85, 85)),
        ("75℃，不对，改成85℃", (85, 85)), ("温度不清楚，问过了是75℃", (75, 75)),
        ("温度不清楚，刚实测确认75℃", (75, 75)),
        ("说明书写85℃，我们实际75℃", (75, 75)), ("温度75℃，水硬度不清楚", (75, 75))):
        turn = Turn(id="turn:sess:1:1", session_id="sess:1", n=1, speaker="customer", text=text, ts=get_clock().now())
        output = extractor.extract([turn], prev)
        if expected is None:
            assert output.temperature is None
        else:
            assert output.temperature.status == "filled" and output.temperature.celsius == expected
    question = turn.model_copy(update={"speaker": "sales", "text": "工艺温度是多少？"})
    reply = turn.model_copy(update={"id": "turn:sess:1:2", "n": 2, "text": "75度"})
    assert extractor.extract([question, reply], prev).temperature.celsius == (75, 75)
    for word in ("硬度", "牢度", "白度", "浓度", "粘度", "酸度", "碱度"):
        reply = reply.model_copy(update={"text": f"{word}10度"})
        assert extractor.extract([question, reply], prev).temperature is None
    for text in ("不是75℃", "75℃以上", "85—75℃", "先60℃再75℃", "先75℃再85℃"):
        reply = reply.model_copy(update={"text": text})
        assert extractor.extract([question, reply], prev).temperature.status == "unknown"


def test_temperature_payload_comparison_normalizes_json_range():
    payload = {"product_id": "T-205", "phenomenon": "color_unlevel", "conditions": {"fiber": ["锦纶氨纶"]},
               "temperature_c": [70, 80]}
    assert _key(payload) == _key({**payload, "temperature_c": (70, 80)})
    assert _key(payload) != _key({**payload, "temperature_c": [70, 85]})


def test_structured_temperature_uses_customer_quote_and_missing_keeps_previous(mini_seeds):
    turn = Turn(id="turn:sess:1:1", session_id="sess:1", n=1, speaker="customer",
                text="温度72—78℃", ts=get_clock().now())
    result = ExtractionResult(intent="need", phenomenon=None, profile=CustomerProfile(),
        temperature=ExtractedTemperature(celsius=(72, 78), status="filled", quote="72—78℃", turn_n=1))
    prev = NeedState(session_id="sess:1", customer_id="customer:C01", sales_id=None)
    valid = validate_extraction(result, mini_seeds, [turn], set())
    known = apply_extraction(prev, valid, [turn])
    assert known.known_temperature() == (72, 78) and known.temperature.turn_id == turn.id
    for temperature in (None, result.temperature.model_copy(update={"quote": "75℃"}),
                        result.temperature.model_copy(update={"celsius": (78, 72)})):
        output = result.model_copy(update={"temperature": temperature})
        validated = validate_extraction(output, mini_seeds, [turn], set())
        assert apply_extraction(known, validated, [turn]).temperature == known.temperature
