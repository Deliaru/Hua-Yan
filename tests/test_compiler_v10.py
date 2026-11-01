import hashlib
import json
import pytest
from pathlib import Path

from huayan.domain import load_seeds
from huayan.events import EventLog
from huayan.ingest.compile import EvidenceRef, Proposal, admit
from huayan.ingest.folder import FolderSource
from huayan.ingest.trial_ir import EvidenceReportSource, prepare_negative
from huayan.ingest.reader.trials import Citation, build_trial_record
from huayan.ingest.reader.word import read_docx, read_native_labels
from huayan.knowledge import AuditLog, KnowledgeBase, PermissionDenied


def test_negative_ir_keeps_both_specimens_both_curves_and_original_limits():
    path = Path("tests/fixtures/reader/synthetic-negative.docx")
    source = {"source_id": "SYNTH-NEGATIVE", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "source": "internal", "level": 3}
    blocks = read_docx(path, source, {f"paragraph-{n}": [1] for n in range(1, 9)} | {"table-1": [1]}, ["synthetic.png"])
    readings, pending = read_native_labels(blocks)
    record = build_trial_record(blocks, readings, pending)
    expert = Citation(fragment="SYNTH-EXPERT#q8@synthetic-review", span="q8", pages=[],
                      quote="合成专家补充：该观察保留原对象和限制。")
    record.quality[0].evidence.append(expert)
    ir = prepare_negative(record, load_seeds("tests/fixtures/mini_seeds"), "SYNTH-PRODUCT（试样版）")
    assert ir.group is None and ir.nature == "observation"
    assert "合成甲布面合格" in ir.observation and "合成乙布面出现色花，不合格" in ir.observation
    assert "合成甲染色配方" in ir.proposal.limits and "合成乙染色配方" in ir.proposal.limits
    curves = [c for c in ir.conditions if c.stage == "工艺曲线"]
    assert {c.group for c in curves} == {"A", "B"}
    assert "0.5℃/min" in ir.proposal.limits and "0.8℃/min" in ir.proposal.limits
    assert "操作警告" in ir.proposal.limits and "已取合成乙" in ir.proposal.limits
    assert record.quality[0].evidence[0] in ir.evidence
    assert expert in ir.evidence
    assert EvidenceRef(doc_id="SYNTH-EXPERT", span="q8", quote=expert.quote) in ir.proposal.evidence
    assert not any(e.doc_id == source["source_id"] and e.span == "q8" for e in ir.proposal.evidence)
    assert ir.proposal.form is None and ir.proposal.temperature_c is None and ir.proposal.author is None
    assert ir.product_raw == ir.proposal.product == "SYNTH-PRODUCT（试样版）"
    assert any("总时长" in note for note in ir.pending) and any("成本变化" in note for note in ir.pending)


def test_unpublished_catalog_product_can_have_candidate_without_being_recommended():
    seeds = load_seeds("tests/fixtures/mini_seeds")
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog())
    source = FolderSource("synthetic", "internal", "tests/fixtures/reader")
    p = Proposal(title="合成未发布目录观察", text="单次观察，待审", product="T-206", author="rd:R01",
        phenomenon="color_unlevel", evidence=[EvidenceRef(doc_id="synthetic-conditions", span="p1", quote="涤纶")])
    report = admit([p], [source], kb)
    unit = kb._units[report["admitted"][0]["ku_id"]]
    assert unit.product_id == "T-206" and unit.status == "candidate"
    assert report["admitted"][0]["capability_id"] is None
    assert "T-206" not in {p.id for p in kb.products()}


def test_pending_scope_follows_explicit_product_line_pm(tmp_path):
    import yaml
    from huayan.app import HuayanApp
    from huayan.contracts import Actor

    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path), run_id="pm-line")
    app.kb.sources = [FolderSource("合成报告", "internal", "tests/fixtures/reader")]
    proposal = Proposal(title="合成待批准范围", text="仅合成范围，待确认", product="T-205", author="rd:R01",
        phenomenon="color_unlevel", form="applicable", conditions=["涤纶"],
        evidence=[EvidenceRef(doc_id="synthetic-conditions", span="p1", quote="涤纶")])
    admitted = app.import_proposals([proposal], "rd:R01")["admitted"][0]
    q = next(q for q in app.bus.list(family="scope_update") if q.refs["capability_id"] == admitted["capability_id"])
    assert q.signer_id == "pm:P01"
    # 产品线编制改动随重启/续跑生效：待批准范围交现任产品经理
    config["pm_lines"] = {"color_unlevel": "pm:P02"}
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path), run_id="pm-line", resume=True)
    new_pm = Actor(id="pm:P02", role="pm", name="合成新产品经理")
    app.seeds.actors.append(new_pm)
    app.actors[new_pm.id] = new_pm
    q = app.bus.get(q.id)
    assert q.signer_id == new_pm.id and q.status == "open"
    assert q.id in {item.id for item in app.questions(new_pm.id)}
    assert HuayanApp.build(str(path), run_id="pm-line", resume=True).bus.get(q.id).signer_id == new_pm.id
    assert app.kb._units[admitted["ku_id"]].status == "candidate"
    assert app.kb._caps[admitted["capability_id"]].status == "proposed"
    assert not app.events.query(["claim_confirmed", "scope_extended"])


def test_report_source_explore_exposes_candidate_only_to_owning_rd(tmp_path):
    seeds = load_seeds("tests/fixtures/mini_seeds")
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog())
    folder = FolderSource("synthetic", "internal", "tests/fixtures/reader")
    doc = "synthetic-conditions"
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"source_id": doc,
        "file_sha256": hashlib.sha256(Path(f"tests/fixtures/reader/{doc}.txt").read_bytes()).hexdigest(),
        "fragments": [f.model_dump(mode="json") for f in folder.fetch(doc)]}, ensure_ascii=False), encoding="utf-8")
    source = EvidenceReportSource(path)
    kb.sources = [source]
    proposal = Proposal(title="合成升温限制", text="涤纶升温观察，待审", product="T-205", author="rd:R01",
        phenomenon="color_unlevel", evidence=[EvidenceRef(doc_id=doc, span="p1", quote="涤纶")])
    report = admit([proposal], [source], kb)
    ku_id = report["admitted"][0]["ku_id"]
    actors = {a.id: a for a in seeds.actors}
    assert ku_id in {u.id for u in kb.explore("涤纶升温", actors["rd:R01"]).candidates}
    customer = kb.explore("涤纶升温", actors["customer:C01"])
    assert customer.candidates == []
    assert ku_id not in {u.id for u in customer.units}


def test_report_candidate_can_be_reviewed_and_confirmed_without_requirement(tmp_path):
    import yaml
    from huayan.app import HuayanApp
    from huayan.ui.server import GET, POST

    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    config_path = tmp_path / "app.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(config_path))
    app.kb.sources = [FolderSource("合成报告", "internal", "tests/fixtures/reader")]
    proposal = Proposal(title="合成资料观察", text="仅为合成观察，待审", product="T-206", author="rd:R01",
        phenomenon="color_unlevel", evidence=[EvidenceRef(doc_id="synthetic-conditions", span="p1", quote="涤纶")])
    report = app.import_proposals([proposal], "rd:R01")
    ku_id = report["admitted"][0]["ku_id"]
    # 合成复现：本人归属的待审候选尚未指定确认人。
    app.kb.add(app.kb._units[ku_id].model_copy(update={"confirmed_by": None}))
    assert not app._requirements
    assert [u.id for u in GET["/api/claims"](app, {"viewer": "rd:R01"})] == [ku_id]
    assert GET["/api/claims"](app, {"viewer": "rd:R02"}) == []
    params = {"ku_ids": [ku_id], "by": "rd:R01"}
    review = POST["/api/qi/review"](app, params)
    assert review["fragments"][ku_id][0].text.startswith("合成测试资料")
    with pytest.raises(PermissionDenied):
        POST["/api/qi/withdraw"](app, {"ku_id": ku_id, "by": "rd:R02"})
    with pytest.raises(ValueError, match="本人负责"):
        POST["/api/qi/revise"](app, {"ku_id": ku_id, "text": "同事不能改写", "by": "rd:R02"})
    revised = POST["/api/qi/revise"](app, {"ku_id": ku_id, "text": "合成修订：保留原条件，仍待专业确认", "by": "rd:R01"})
    assert revised.id != ku_id and revised.status == "candidate" and revised.evidence == review["claims"][0].evidence
    assert app.kb._units[ku_id].status == "withdrawn" and app.kb._units[ku_id].text == proposal.text
    assert app.kb._units[ku_id].confirmed_by is None and revised.confirmed_by is None
    assert not app.events.query(["claim_confirmed"])
    with pytest.raises(ValueError, match="待审列表"):
        POST["/api/qi/confirm"](app, params | {"reviewed_evidence": review["reviewed_evidence"]})
    assert [u.id for u in GET["/api/claims"](app, {"viewer": "rd:R01"})] == [revised.id]
    ku_id = revised.id
    params = {"ku_ids": [ku_id], "by": "rd:R01"}
    review = POST["/api/qi/review"](app, params)
    assert review["claims"][0].text == revised.text
    with pytest.raises(ValueError, match="实际审阅"):
        POST["/api/qi/confirm"](app, params)
    assert app.kb._units[ku_id].status == "candidate"
    assert POST["/api/qi/confirm"](app, params | {"reviewed_evidence": review["reviewed_evidence"]}) is None
    assert app.kb._units[ku_id].status == "active"
    assert GET["/api/claims"](app, {"viewer": "rd:R01"}) == []
    with pytest.raises(ValueError, match="待审候选"):
        POST["/api/qi/revise"](app, {"ku_id": ku_id, "text": "已确认后不能原地改写", "by": "rd:R01"})
    # 已确认结论仍只认确认人，不能因归属不同而放宽撤回权限。
    app.kb.add(app.kb._units[ku_id].model_copy(update={"owner": "rd:R02"}))
    with pytest.raises(PermissionDenied):
        POST["/api/qi/withdraw"](app, {"ku_id": ku_id, "by": "rd:R02"})
    POST["/api/qi/withdraw"](app, {"ku_id": ku_id, "by": "rd:R01"})
    assert app.kb._units[ku_id].status == "withdrawn"
    assert not app._requirements
    assert not any(c.payload.get("product_id") == "T-206" for c in app.kb.capabilities())

    # 同一现象的需求单也不能把未授权的同事候选全文交给接单研发。
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    app.save_escalate_note(session.id, "（合成）现有产品不匹配，交研发", "sales:S01")
    question = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
    app.mark_prepared(question.id, question.owner_id)
    req = app.escalate(session.id, "sales:S01")
    rd = req.assigned_rd
    colleague = "rd:R02" if rd == "rd:R01" else "rd:R01"
    own = app.import_proposals([proposal.model_copy(update={"author": rd, "title": "本人的合成待审判断"})], rd)
    other = app.import_proposals([proposal.model_copy(update={"author": colleague, "text": "合成同事未授权正文"})], colleague)
    own_id, other_id = own["admitted"][0]["ku_id"], other["admitted"][0]["ku_id"]
    listed = GET["/api/claims"](app, {"req_id": req.id, "viewer": rd})
    assert [u.id for u in listed] == [own_id]
    assert "合成同事未授权正文" not in json.dumps([u.model_dump(mode="json") for u in listed], ensure_ascii=False)
    assert POST["/api/qi/review"](app, {"ku_ids": [own_id], "by": rd})["claims"][0].id == own_id
    with pytest.raises(ValueError, match="待审列表"):
        POST["/api/qi/confirm"](app, {"req_id": req.id, "ku_ids": [other_id], "by": rd})

    # 修订判断不自动承接原用途；原依据撤回后仍沿已有挂起语义处理。
    applicable = proposal.model_copy(update={"form": "applicable", "conditions": ["涤纶"], "author": "rd:R01"})
    row = app.import_proposals([applicable], "rd:R01")["admitted"][0]
    revised = app.revise_claim(row["ku_id"], "合成修订判断，拟用范围须重新准备", "rd:R01")
    cap = app.kb._caps[row["capability_id"]]
    assert cap.status == "suspended" and cap.based_on == [row["ku_id"]]
    assert revised.id not in cap.based_on and revised.status == "candidate"


def test_partial_conditions_and_new_evidence_stay_pending(tmp_path):
    seeds = load_seeds("tests/fixtures/mini_seeds")
    state = tmp_path / "qi_state.json"
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog(), state_path=state)
    source_path = tmp_path / "synthetic-conditions.txt"
    original = Path("tests/fixtures/reader/synthetic-conditions.txt").read_text(encoding="utf-8")
    source_path.write_text(original, encoding="utf-8")
    source = FolderSource("synthetic", "internal", tmp_path)
    kb.sources = [source]
    doc = "synthetic-conditions"
    proposal = Proposal(title="合成升温限制", text="合成判断，待确认", product="T-205",
        phenomenon="color_unlevel", form="applicable", author="rd:R01",
        conditions=["涤纶", "气流染色机，升温速率不超过1℃/min"],
        evidence=[EvidenceRef(doc_id=doc, span="p1", quote="升温速率不超过1℃/min")])
    result = admit([proposal], [source], kb)
    cap = kb._caps[result["admitted"][0]["capability_id"]]
    assert cap.status == "proposed"
    assert cap.payload["conditions"] == {"fiber": ["涤纶"], "equipment": ["气流染色机"]}
    assert cap.payload["limits"] == "气流染色机，升温速率不超过1℃/min"
    based_on = list(cap.based_on)
    extra = proposal.model_copy(update={"title": "合成补充依据", "author": "rd:R02",
        "evidence": [EvidenceRef(doc_id=doc, span="p2", quote="升温速率不超过1℃/min")]})
    repeated = admit([extra], [source], kb)
    pending = repeated["pending_evidence"][0]
    assert kb._units[pending["ku_id"]].status == "candidate"
    assert cap.based_on == based_on and cap.status == "proposed"
    reloaded = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog(), state_path=state)
    assert reloaded._pending_evidence[pending["ku_id"]] == {"capability_id": cap.id, "contributor": "rd:R02"}
    assert reloaded._caps[cap.id].based_on == based_on
    # C7：审阅后来源变化，旧指纹不得签成新依据；失败不改变状态或挂接。
    ku_id = pending["ku_id"]
    viewed = {ku_id: list(kb._units[ku_id].evidence)}
    kb.sources = []
    with pytest.raises(ValueError, match="依据无法取回"):
        kb.confirm([ku_id], "rd:R01", reviewed_evidence=viewed)
    kb.sources = [source]
    missing = kb._units[ku_id].model_copy(update={"evidence": [f"{doc}#missing@old"]})
    with pytest.raises(ValueError, match="依据无法取回"):
        kb._fragments(missing)
    source_path.write_text(original.replace("相同材料", "已修订的相同材料"), encoding="utf-8")
    with pytest.raises(ValueError, match="依据已变化"):
        kb.confirm([ku_id], "rd:R01", reviewed_evidence=viewed)
    assert kb._units[ku_id].status == "candidate" and cap.based_on == based_on
    with pytest.raises(ValueError, match="实际审阅"):
        kb.confirm([ku_id], "rd:R01")
    current = source.fetch(doc, "p2")
    reviewed = {ku_id: [f"{current.doc_id}#{current.span}@{current.fingerprint}"]}
    kb.confirm([ku_id], "rd:R01", reviewed_evidence=reviewed)
    assert kb._units[ku_id].status == "active" and cap.based_on == [*based_on, ku_id]
    assert ku_id not in kb._pending_evidence
    event = kb.events.query(["claim_confirmed"])[-1]
    assert event.payload["contributor"] == "rd:R02" and event.payload["reviewed_evidence"] == reviewed[ku_id]
    kb.confirm([ku_id], "rd:R01", reviewed_evidence=reviewed)
    assert cap.based_on.count(ku_id) == 1 and len(kb.events.query(["claim_confirmed"])) == 1


@pytest.mark.parametrize("explicit", [False, True])
def test_public_scope_approval_checks_evidence(tmp_path, explicit):
    import yaml
    from huayan.app import HuayanApp
    from huayan.knowledge import PermissionDenied
    from huayan.ui.server import POST

    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    config_path = tmp_path / "app.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(config_path))
    root = tmp_path / "public"
    root.mkdir()
    page = root / "synthetic-public.txt"
    original = Path("tests/fixtures/reader/synthetic-conditions.txt").read_text(encoding="utf-8")
    page.write_text(original, encoding="utf-8")
    source = FolderSource("公开合成资料", "public", root)
    app.kb.sources = [source]
    proposal = Proposal(title="合成公开适用", text="合成判断，待产品经理核对", product="T-205",
        phenomenon="color_unlevel", form="applicable", conditions=["涤纶", "气流染色机"],
        evidence=[EvidenceRef(doc_id="synthetic-public", span="p1", quote="升温速率不超过1℃/min")],
        limits="升温速率不超过1℃/min")
    result = admit([proposal], [source], app.kb)["admitted"][0]
    ids = [result["ku_id"]]
    with pytest.raises(PermissionDenied):
        app.review_claims(ids, "pm:agent")
    viewed = POST["/api/qi/review"](app, {"ku_ids": ids, "by": "pm:P01"})["reviewed_evidence"]
    app.scan()
    app.tick()
    q = next(q for q in app.bus.list(family="scope_update") if q.refs["capability_id"] == result["capability_id"])
    params = {"question_id": q.id, "note": "合成产品页核对", "by": "pm:P01"}
    if explicit:
        params["reviewed_evidence"] = viewed
    page.write_text(original.replace("合成测试资料", "修订的合成测试资料"), encoding="utf-8")
    with pytest.raises(ValueError, match="依据已变化"):
        POST["/api/scope/extend"](app, params)
    assert app.kb._units[ids[0]].status == "candidate"
    assert app.kb._caps[result["capability_id"]].approved_by is None
    if explicit:
        params["reviewed_evidence"] = app.review_claims(ids, "pm:P01")["reviewed_evidence"]
    else:
        page.write_text(original, encoding="utf-8")
    approved = POST["/api/scope/extend"](app, params)
    assert approved.status == "active" and approved.approved_by == "pm:P01"
    assert app.kb._units[ids[0]].status == "active"
