from huayan.domain import load_seeds
from huayan.events import EventLog
from huayan.ingest.compile import EvidenceRef, Proposal, admit
from huayan.ingest.folder import FolderSource
from huayan.knowledge import AuditLog, KnowledgeBase


def test_partial_conditions_and_new_evidence_stay_pending(tmp_path):
    seeds = load_seeds("tests/fixtures/mini_seeds")
    state = tmp_path / "qi_state.json"
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog(), state_path=state)
    source = FolderSource("synthetic", "internal", "tests/fixtures/reader")
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
