"""V9.3：研发的回问显示在客户自助页上、不在对话里。抽取拿到页面正显示的那一条，客户答「不清楚」时记在该槽位，回问结案、已知条件不丢。
语义由大模型抽取判断（真实模型另行核对）；这里用结构化输出夹具只验下游。"""

from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ExtractedSlot, ExtractionResult, Question


def _config(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


class _Fixture:
    """结构化输出夹具：客户这句答的就是 asking 里的那一项，记不清楚。"""
    name = "llm"

    def __init__(self):
        self.calls = []

    def extract(self, turns, prev, products=(), asking=()):
        self.calls.append((turns[-1].speaker, list(asking)))
        slots = [ExtractedSlot(slot=s, value=None, status="unknown", confidence=0.9,
                               quote=turns[-1].text, turn_n=turns[-1].n) for s in asking[:1]]
        return ExtractionResult(intent="need", phenomenon=prev.phenomenon, phenomenon_quote=prev.phenomenon_quote,
                                slots=slots, profile=prev.profile)


def _ask(app, session_id, req_id, slot):
    return app.bus.publish(Question(
        id="new", family="ask_back", title="回问", object_id=f"slot:{req_id}/{slot}", owner_role="customer",
        scored_by="rule", discoverer="jue_proto", refs={"session_id": session_id, "requirement_id": req_id, "slot": slot},
        dedup_key=f"ask_back:slot:{req_id}/{slot}", created_at=get_clock().now()))


def test_unknown_answer_to_page_ask_closes_it(tmp_path):
    app = HuayanApp.build(_config(tmp_path), run_id="v93")
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    app.escalate(session.id, "sales:S01")
    req = next(r for r in app._requirements.values() if session.id in r.session_ids)
    known = app._sessions[session.id].need.known()
    first, second = _ask(app, session.id, req.id, "constraint"), _ask(app, session.id, req.id, "equipment")
    assert [a.slot for a in app.view_session(session.id, "customer:C01").asks] == ["constraint", "equipment"]

    app.extractor = fixture = _Fixture()
    app.add_turn(session.id, "customer", "这个我不太清楚，都是车间那边在弄。")
    assert fixture.calls[-1] == ("customer", ["constraint"])       # 只给页面上正显示的第一条
    need = app._sessions[session.id].need
    assert need.slots["constraint"].status == "unknown"
    assert app.bus.get(first.id).resolution.note == "客户不清楚"
    assert (app.bus.get(second.id).resolution.note if app.bus.get(second.id).resolution else "") != "客户不清楚"
    assert {k: v for k, v in need.known().items() if k in known} == known     # 已知条件原样保留

    app.add_turn(session.id, "sales", "设备是哪种？")
    assert fixture.calls[-1] == ("sales", [])                        # 业务员的话不是在答回问
