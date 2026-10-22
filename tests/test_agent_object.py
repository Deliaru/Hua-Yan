"""V9.4：助手按当前对象装配上下文——派来的问题以它的对象为当前工作面，只看本段对话的确认卡；
签字前要有的草稿派单时写明；引用不了的原话说清是哪条、能引哪些。"""

from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import LLMResponse, PendingAction, ReqItem, Tier, Usage


def _app(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), agent_threads="object")
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return HuayanApp.build(str(path), run_id="v94")


class _Recorder:
    """记下每次请求，回一句不调工具的话。"""
    cache_dir = replay = trace = None

    def __init__(self):
        self.requests = []

    def complete(self, req):
        self.requests.append(req)
        return LLMResponse(content="好的", usage=Usage(input_tokens=0, output_tokens=0), latency_ms=0,
                           model="fake", tier=Tier.FAST, cost=None)


def test_dispatch_assembles_context_for_its_object(tmp_path):
    app = _app(tmp_path)
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    app.escalate(session.id, "sales:S01")
    req = next(r for r in app._requirements.values() if session.id in r.session_ids)
    app.agents._pending["act:other"] = PendingAction(
        id="act:other", conversation_id="conv:pm:agent:req:999", principal="pm:agent", tool="edit_item",
        args={}, summary="别的单的确认卡", created_at=get_clock().now())
    app.config["gateway_mock"], app.gateway = False, (rec := _Recorder())

    app.agents.dispatch()
    first = [r for r in rec.requests if r.caller == "agent:pm"][0]
    system, notice = first.messages[0].content, first.messages[-1].content
    assert f"当前工作面对象（focus）：{req.id}" in system
    assert "别的单的确认卡" not in system
    assert "签字前对象上要有" in notice and req.id in notice
    conv = app.agents.conversation("pm:agent", thread=req.id)
    assert conv.id == f"conv:pm:agent:{req.id}" and all(m.target in (None, req.id) for m in conv.messages)


def test_quote_rejection_names_the_bad_ref(tmp_path):
    app = _app(tmp_path)
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    app.add_turn(session.id, "sales", "什么面料？")
    app.escalate(session.id, "sales:S01")
    req = next(r for r in app._requirements.values() if session.id in r.session_ids)
    item = ReqItem(text="x", quote_refs=[f"turn:{session.id}:2"])
    with pytest.raises(ValueError, match=rf"turn:{session.id}:2 不是；可引用 turn:{session.id}:1"):
        app._validate_item(req, item, app.actors["pm:agent"])
