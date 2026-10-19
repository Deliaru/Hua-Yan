import pytest

from huayan.contracts import Capability, DecryptGrant
from huayan.domain import match_candidates
from huayan.events import EventLog
from huayan.knowledge import AuditLog, KnowledgeBase, PermissionDenied
from huayan.knowledge.disclosure import cap, render


def test_l1_knowledge_boundary(mini_seeds, sim_clock, tmp_path):
    actors = {a.id: a for a in mini_seeds.actors}
    sales, pm = actors["sales:S01"], actors["pm:P01"]
    events, audit = EventLog(), AuditLog(tmp_path / "audit.jsonl")
    kb = KnowledgeBase.from_seeds(mini_seeds, events, audit)
    context = dict(session_id="sess:1", customer_id="customer:C01", grants=[])
    for query in ("配方", "机理", "色花", "匀染 缓染 染座", "锦纶氨纶 色花"):
        assert all(h.ku.level <= 1 for h in kb.search(query, sales))
    assert any(e.payload["n_blocked"] > 0 for e in events.query(kinds=["retrieve"]))
    for product in kb.products():
        card = render(product.id, cap(sales, "customer:C01", product.id, []), sales, kb, **context)
        assert card.session_id == "sess:1"
        assert all(s.level <= 1 for s in card.sections)
    with pytest.raises(PermissionDenied):
        kb.get("ku:formula:T-205", sales)
    with pytest.raises(PermissionDenied):
        render("T-205", "full_mechanism", sales, kb, **context)
    grant = DecryptGrant(id="grant:1", customer_id="customer:C01", product_id="T-205",
        session_id="sess:1", approved_by="rd:R01", at=sim_clock.now())
    context["grants"] = [grant]
    card = render("T-205", "full_mechanism", sales, kb, **context)
    assert [s.ku_id for s in card.sections] == ["ku:sheet:T-205", "ku:usage:T-205", "ku:mechanism:T-205"]
    for viewer, version in ((sales, "internal"), (pm, "full_mechanism")):
        with pytest.raises(PermissionDenied):
            render("T-205", version, viewer, kb, **context)
    for changes in ({"customer_id": "customer:C02"}, {"approved_by": "rd:R02"}, {"product_id": "T-101"}):
        with pytest.raises(PermissionDenied):
            render("T-205", "full_mechanism", sales, kb,
                   **{**context, "grants": [grant.model_copy(update=changes)]})
    before = len(events.events), len(audit.list())
    hints = kb.search_blocked("匀染 缓染 染座", pm)
    assert any(h.owner == "rd:R01" for h in hints)
    assert all(set(h.model_dump()) == {"owner", "level", "kind", "ku_id"} and h.ku_id is None for h in hints)
    assert before == (len(events.events), len(audit.list()))
    kb.freeze(sales.id, "supervisor:M01", sim_clock.now())
    assert kb.search("T-205 配方", sales) == []
    assert kb.search("用法", sales)
    assert not KnowledgeBase.from_seeds(mini_seeds, EventLog(), AuditLog()).is_frozen(sales.id)
    assert events.query(kinds=["access_denied"]) and audit.list(sales.id)

    # 情境取并集，不能把两条情境里的面料和设备交叉拼接。
    kb.grant(Capability(id=kb.next_cap_id(), form="applicable", audience=0,
        payload={"product_id": "T-205", "phenomenon": "color_unlevel",
                 "conditions": {"fiber": ["涤纶"], "equipment": ["气流染色机"]}},
        based_on=["ku:sheet:T-205"], granted_by="rd:R01", approved_by="pm:P01",
        status="active", at=sim_clock.now()))
    products = kb.view(actors["customer:C01"]).products
    assert "T-205" not in {c.product_id for c in match_candidates("color_unlevel",
        {"fiber": "锦纶氨纶", "equipment": "气流染色机"}, products)}
    partial = next(c for c in match_candidates("color_unlevel", {"fiber": "涤纶"}, products) if c.product_id == "T-205")
    assert partial.status == "possible" and partial.unknown_slots == ["equipment"]
    complete = next(c for c in match_candidates("color_unlevel",
        {"fiber": "涤纶", "equipment": "气流染色机"}, products) if c.product_id == "T-205")
    assert complete.status == "confirmed" and not complete.unknown_slots

    with pytest.raises(PermissionDenied, match="配方"):
        kb.grant(Capability(id=kb.next_cap_id(), form="statement", audience=0,
            payload={"text": "不应放出"}, based_on=["ku:formula:T-205"], granted_by="rd:R01",
            status="active", at=sim_clock.now()))
