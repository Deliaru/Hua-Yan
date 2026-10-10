from datetime import timedelta

from huayan.bus import QuestionBus
from huayan.contracts import Evidence, Question, Resolution
from huayan.domain import correct_product, match_candidates
from huayan.events import EventLog


def test_candidate_relations(mini_seeds):
    products = mini_seeds.products
    ids = lambda known: [c.product_id for c in match_candidates("color_unlevel", known, products)]

    assert ids({}) == ["T-101", "T-205"]
    assert ids({"fiber": "锦纶氨纶"}) == ["T-205"]
    assert ids({"fiber": "锦纶氨纶", "equipment": "气流染色机"}) == []
    assert correct_product("color_unlevel", {"fiber": "锦纶氨纶", "equipment": "气流染色机"}, products) is None

    released = [p.model_copy(update={"status": "released"}) if p.id == "T-206" else p for p in products]
    assert [c.product_id for c in match_candidates(
        "color_unlevel", {"fiber": "锦纶氨纶", "equipment": "气流染色机"}, released)] == ["T-206"]
    assert correct_product("color_unlevel", {"fiber": "锦纶氨纶", "equipment": "气流染色机"}, released) == "T-206"


def test_bus_merge_and_suppress(sim_clock):
    events = EventLog()
    bus = QuestionBus(events, suppress_hours=24)
    now = sim_clock.now()
    make = lambda summary, at: Question(
        id="", family="opportunity", title="锦氨气流缸色花", object_id="theme:color_unlevel|equipment=气流染色机",
        owner_role="pm", scored_by="rule", discoverer="jue_proto", evidence=[Evidence(summary=summary)],
        dedup_key="opportunity:theme:color_unlevel|equipment=气流染色机", created_at=at)

    first = bus.publish(make("3 次升级", now))
    merged = bus.publish(make("4 次升级", now + timedelta(hours=1)))
    assert merged.id == first.id and len(bus.list()) == 1
    assert [e.summary for e in merged.evidence] == ["3 次升级", "4 次升级"]

    bus.resolve(first.id, Resolution(action="dismiss", by="pm:P01"), now + timedelta(hours=2))
    dropped = bus.publish(make("5 次升级", now + timedelta(hours=10)))
    assert dropped.id == "" and bus.list(status=None) == [first]

    again = bus.publish(make("6 次升级", now + timedelta(hours=30)))
    assert again.id == "q:2" and again.status == "open"
    assert [e.kind for e in events.query()] == ["question_published", "question_resolved", "question_published"]
