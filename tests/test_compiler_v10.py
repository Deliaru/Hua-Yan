import hashlib
import json
import pytest
from pathlib import Path

from huayan.domain import load_seeds
from huayan.events import EventLog
from huayan.ingest.compile import EvidenceRef, Proposal, admit
from huayan.ingest.folder import FolderSource
from huayan.ingest.trial_ir import EvidenceReportSource
from huayan.knowledge import AuditLog, KnowledgeBase


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
