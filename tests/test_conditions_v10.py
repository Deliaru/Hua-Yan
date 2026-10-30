"""V10.6：合成授权 70—80℃，不代表真实产品的专业确认范围。"""
from huayan.contracts import Situation
from huayan.domain import match_candidates
from huayan.events import EventLog
from huayan.knowledge import AuditLog, KnowledgeBase


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
    product.situations.append(Situation(phenomenon="color_unlevel", conditions={"fiber": ["锦纶氨纶"]},
                                       capability_id="cap:synthetic:unrestricted"))
    [candidate] = match_candidates("color_unlevel", {"fiber": "锦纶氨纶"}, [product])
    assert candidate.status == "confirmed" and candidate.capability_id == "cap:synthetic:unrestricted"
