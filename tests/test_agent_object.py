"""V9.4：助手按当前对象装配上下文——派来的问题以它的对象为当前工作面，只看本段对话的确认卡；
签字前要有的草稿派单时写明；引用不了的原话说清是哪条、能引哪些。"""

import json
from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import LLMResponse, LLMToolCall, PendingAction, ReqItem, Tier, Usage
from huayan.ingest.folder import FolderSource


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


class _SourcePreparation:
    """脚本化网关只驱动真实工具链；输出是合成准备摘要，不是模型能力测评。"""
    def __init__(self, req_id, session_id):
        self.calls = [("get_requirement", {"req_id": req_id}), ("get_session", {"session_id": session_id}),
                      ("read_source", {"doc_id": "synthetic-conditions", "span": "p1"})]
        self.requests = []

    def complete(self, req):
        self.requests.append(req)
        results = [json.loads(m.content)["data"] for m in req.messages if m.role == "tool"]
        calls, content = [], ""
        if len(results) < len(self.calls):
            name, arguments = self.calls[len(results)]
            calls = [LLMToolCall(call_id=str(len(results)), name=name, arguments=arguments)]
        else:
            unit = results[-1][0]
            content = (f"（脚本化合成摘要）{results[0]['req_id']}：已知条件 {results[0]['known_slots']}；"
                       f"依据 {unit['doc_id']}#{unit['span']}@{unit['fingerprint']}：{unit['text']}；"
                       "报告条件与本单是否一致待研发核对，未导入候选、未确认或授予。")
        return LLMResponse(content=content, tool_calls=calls, usage=Usage(input_tokens=0, output_tokens=0),
                           latency_ms=0, model="scripted-source-preparation", tier=Tier.FAST, cost=None)


def test_agent_reads_report_for_current_requirement_without_signing(tmp_path):
    app = _app(tmp_path)
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块，锦纶氨纶的，气流缸，75℃")
    app.save_escalate_note(session.id, "（合成）气流缸条件需研发判断", "sales:S01")
    question = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
    app.mark_prepared(question.id, question.owner_id)
    req = app.escalate(session.id, "sales:S01")
    source = FolderSource("合成内部资料", "internal", "tests/fixtures/reader")
    app.kb.sources = [source]
    app.source_owners = {"synthetic-conditions": req.assigned_rd}
    gateway = _SourcePreparation(req.id, session.id)
    app.gateway, app.config["gateway_mock"] = gateway, False
    before = app.kb.state_path.read_bytes()
    conv = app.agents.chat(req.assigned_rd, "请读取 synthetic-conditions 的 p1，为本单准备查证摘要。", focus=req.id)
    fragment = source.fetch("synthetic-conditions", "p1")
    assert conv.id == f"conv:{req.assigned_rd}:{req.id}"
    assert conv.messages[-1].target == req.id and req.id in conv.messages[-1].text
    assert f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}" in conv.messages[-1].text
    assert [s.tool for s in app.agents.trace(conv.id) if s.tool] == ["get_requirement", "get_session", "read_source"]
    assert all(r.caller == "agent:rd" for r in gateway.requests)
    session_read = json.loads(next(m.content for m in gateway.requests[-1].messages
                                  if m.role == "tool" and m.tool_call_id == "1"))
    assert session_read["data"]["temperature"]["celsius"] == [75.0, 75.0]
    read = json.loads(next(m.content for m in gateway.requests[-1].messages if m.role == "tool" and m.tool_call_id == "2"))
    assert read["data"] == [fragment.model_dump()]
    assert not app.agents.pending(req.assigned_rd) and not app.events.query(["claim_confirmed"])
    assert app.kb.state_path.read_bytes() == before
