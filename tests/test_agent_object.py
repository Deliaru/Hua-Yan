"""V9.4：助手按当前对象装配上下文——派来的问题以它的对象为当前工作面，只看本段对话的确认卡；
签字前要有的草稿派单时写明；引用不了的原话说清是哪条、能引哪些。"""

import hashlib
import json
from pathlib import Path

import pytest
import yaml
import httpx
import openai

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import LLMRequest, LLMResponse, LLMToolCall, Message, PendingAction, ReqItem, Tier, Usage
from huayan.gateway.client import OpenAICompatGateway
from huayan.ingest.folder import FolderSource
from huayan.ingest.compile import EvidenceRef, Proposal
from huayan.ingest.trial_ir import EvidenceReportSource, prepare_negative
from huayan.ingest.reader.trials import build_trial_record
from huayan.ingest.reader.word import read_docx, read_native_labels
from huayan.knowledge import PermissionDenied
from huayan.ui.server import GET, POST


def _app(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"), agent_threads="object")
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return HuayanApp.build(str(path), run_id="v94")


def test_standard_tool_calls_do_not_execute_text_protocol():
    # 当前网关只认标准tool_calls；文字中的旧工具协议不再转成执行。
    protocol = '<tool_call>\n{"name":"get_requirement","arguments":{"req_id":"req:1"}}\n</tool_call>'
    responses = iter([{"role":"assistant","content":"", "tool_calls":[{"id":"call:1","type":"function",
        "function":{"name":"get_requirement","arguments":"{\"req_id\":\"req:1\"}"}}]},
        {"role":"assistant","content":protocol,"reasoning_content":protocol}])
    def handle(request):
        return httpx.Response(200, json={"id":"synthetic-qwen", "object":"chat.completion", "created":0,
            "model":"synthetic-tool-model", "choices":[{"index":0,"finish_reason":"stop",
                "message":next(responses)}],
            "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}})
    client = openai.OpenAI(api_key="synthetic", base_url="https://synthetic.invalid/v1", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    gateway = OpenAICompatGateway({"tiers":{"fast":{"model":"synthetic-tool-model",
        "fallbacks":[],"price_per_1k":{"input":None,"output":None}}}}, clients={"fast":client})
    request = LLMRequest(tier=Tier.FAST, caller="agent:pm", messages=[Message(role="user",content="合成协议检查")],
        tools=[{"type":"function","function":{"name":"get_requirement","parameters":{"type":"object"}}}])
    actual = gateway.complete(request)
    assert [(c.name,c.arguments) for c in actual.tool_calls] == [("get_requirement",{"req_id":"req:1"})]
    assert actual.content == ""
    explanation = gateway.complete(request)
    assert explanation.tool_calls == [] and explanation.content == protocol
    client.close()


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
    def __init__(self, req_id, session_id, claim_ids=()):
        self.calls = [("get_requirement", {"req_id": req_id}), ("get_session", {"session_id": session_id}),
                      ("read_source", {"doc_id": "synthetic-conditions", "span": "p1"})]
        self.requests = []
        self.claim_ids = list(claim_ids)

    def complete(self, req):
        self.requests.append(req)
        results = [json.loads(m.content)["data"] for m in req.messages if m.role == "tool"]
        calls, content = [], ""
        if len(results) < len(self.calls):
            name, arguments = self.calls[len(results)]
            calls = [LLMToolCall(call_id=str(len(results)), name=name, arguments=arguments)]
        elif len(results) == len(self.calls):
            unit = results[2][0]
            calls = [LLMToolCall(call_id="3", name="save_source_preparation", arguments={
                "req_id": results[0]["req_id"], "evidence": [f"{unit['doc_id']}#{unit['span']}@{unit['fingerprint']}"],
                "claim_ids": self.claim_ids, "pending": "（合成）涤纶报告与本单锦纶氨纶条件不同，待研发核对。"})]
        else:
            unit = results[2][0]
            content = (f"（脚本化合成摘要）{results[0]['req_id']}：已知条件 {results[0]['known_slots']}；"
                       f"依据 {unit['doc_id']}#{unit['span']}@{unit['fingerprint']}：{unit['text']}；"
                       "已保存本单资料准备草稿，条件差异待研发核对，未确认或授予。")
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
    proposal = Proposal(title="合成报告观察", text="涤纶操作观察，未判断本单适用", product="T-206",
        author=req.assigned_rd, phenomenon=req.phenomenon,
        evidence=[EvidenceRef(doc_id="synthetic-conditions", span="p1", quote="涤纶")])
    claim_id = app.import_proposals([proposal], req.assigned_rd)["admitted"][0]["ku_id"]
    gateway = _SourcePreparation(req.id, session.id, [claim_id])
    app.gateway, app.config["gateway_mock"] = gateway, False
    before = app.kb.state_path.read_bytes()
    conv = app.agents.chat(req.assigned_rd, "请读取 synthetic-conditions 的 p1，为本单准备查证摘要。", focus=req.id)
    fragment = source.fetch("synthetic-conditions", "p1")
    assert conv.id == f"conv:{req.assigned_rd}:{req.id}"
    assert conv.messages[-1].target == req.id and req.id in conv.messages[-1].text
    assert f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}" in conv.messages[-1].text
    assert [s.tool for s in app.agents.trace(conv.id) if s.tool] == [
        "get_requirement", "get_session", "read_source", "save_source_preparation"]
    assert all(r.caller == "agent:rd" for r in gateway.requests)
    session_read = json.loads(next(m.content for m in gateway.requests[-1].messages
                                  if m.role == "tool" and m.tool_call_id == "1"))
    assert session_read["data"]["temperature"]["celsius"] == [75.0, 75.0]
    read = json.loads(next(m.content for m in gateway.requests[-1].messages if m.role == "tool" and m.tool_call_id == "2"))
    assert read["data"] == [fragment.model_dump()]
    assert not app.agents.pending(req.assigned_rd) and not app.events.query(["claim_confirmed"])
    assert app.kb.state_path.read_bytes() == before
    saved = GET["/api/source-preparation"](app, {"req_id": req.id, "viewer": req.assigned_rd})
    assert saved["claim_ids"] == [claim_id] and saved["req_id"] == req.id
    assert saved["evidence"] == [f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}"]
    assert saved["temperatures"][session.id]["celsius"] == [75.0, 75.0]
    assert "条件不同" in saved["pending"] and app.kb._units[claim_id].status == "candidate"
    assert GET["/api/source-preparation"](app, {"req_id": req.id, "viewer": "pm:agent"}) is None
    colleague = "rd:R02" if req.assigned_rd == "rd:R01" else "rd:R01"
    assert GET["/api/source-preparation"](app, {"req_id": req.id, "viewer": colleague}) is None
    with pytest.raises(PermissionDenied):
        POST["/api/source-preparation"](app, saved | {"by": colleague})
    with pytest.raises(ValueError, match="依据已变化"):
        POST["/api/source-preparation"](app, saved | {"by": req.assigned_rd, "evidence": [f"{fragment.doc_id}#{fragment.span}@old"]})
    with pytest.raises(ValueError, match="待审列表"):
        POST["/api/source-preparation"](app, saved | {"by": req.assigned_rd, "claim_ids": ["ku:claim:999"]})
    assert app.source_preparation(req.id, req.assigned_rd) == saved
    # 条件变化不把保存时的条件冒充当前事实；再次准备时保存明确未知。
    app.add_turn(session.id, "customer", "实际温度不清楚")
    updated = POST["/api/source-preparation"](app, saved | {"by": req.assigned_rd})
    assert updated["temperatures"][session.id]["status"] == "unknown"
    assert updated["temperatures"][session.id]["celsius"] is None


def test_report_level_negative_preparation_preserves_scope_and_alignment_gap(tmp_path):
    app = _app(tmp_path)
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸，75℃")
    app.save_escalate_note(session.id, "（合成）对照历史负例，不能直接归因", "sales:S01")
    q = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
    app.mark_prepared(q.id, q.owner_id)
    req = app.escalate(session.id, "sales:S01")
    path = Path("tests/fixtures/reader/synthetic-negative.docx")
    doc = "SYNTH-NEGATIVE"
    source = {"source_id": doc, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "source": "internal", "level": 3}
    blocks = read_docx(path, source, {f"paragraph-{n}": [1] for n in range(1, 9)} | {"table-1": [1]}, ["synthetic.png"])
    readings, pending = read_native_labels(blocks)
    ir = prepare_negative(build_trial_record(blocks, readings, pending), app.seeds, "SYNTH-PRODUCT（试样版）")
    evidence = tmp_path / "negative-evidence.json"
    evidence.write_text(json.dumps({"source_id": doc, "file_sha256": source["sha256"],
        "fragments": [b.fragment().model_dump() for b in blocks]}), encoding="utf-8")
    app.kb.sources = [EvidenceReportSource(evidence)]
    app.source_owners = {doc: req.assigned_rd}
    ir_path = tmp_path / "negative-ir.json"
    ir_path.write_text(ir.model_dump_json(), encoding="utf-8")
    app.config["source_irs"] = {doc: str(ir_path)}
    pointers = list(dict.fromkeys(c.fragment for c in ir.evidence))
    app.save_source_preparation(req.id, pointers, [], "（合成）混合品质结果，仅作比较材料", req.assigned_rd)
    before = app.kb.state_path.read_bytes()
    with pytest.raises(ValueError, match="已指定本人负责"):
        app.compile_source_preparation(req.id, doc, req.assigned_rd)
    # 仅在合成临时实例指定本条归属；型号未对齐仍保留在原单编译报告中。
    ir.proposal.author = req.assigned_rd
    ir_path.write_text(ir.model_dump_json(), encoding="utf-8")
    ctx = app.agents.context(req.assigned_rd, thread=req.id)
    result = app.agents.call_tool(ctx, "compile_source_preparation", {"req_id": req.id, "doc_id": doc})
    assert result.ok and result.data["claim_ids"] == []
    report = result.data["compilation"]["report"]
    assert report["admitted"] == [] and report["dropped"] == []
    assert report["unaligned_details"][0]["reasons"] == ["产品未对齐：SYNTH-PRODUCT（试样版）"]
    assert app.kb.state_path.read_bytes() == before
    # 明确登记独立的合成试样型号，不把后缀隐式折叠到基础产品。
    product = next(p for p in app.seeds.products if p.id == "T-206")
    app.kb.seeds.products.append(product.model_copy(update={"id": ir.product_raw, "owner": req.assigned_rd}))
    result = app.agents.call_tool(ctx, "compile_source_preparation", {"req_id": req.id, "doc_id": doc})
    assert result.ok
    saved = app.source_preparation(req.id, req.assigned_rd)
    row = saved["compilation"]["report"]["admitted"][0]
    unit = app.kb._units[row["ku_id"]]
    assert saved["claim_ids"] == [unit.id] and unit.product_id == ir.product_raw
    assert unit.text.startswith("报告层单次观察：") and "None组" not in unit.text
    assert "合成甲布面合格" in unit.text and "合成乙布面出现色花，不合格" in unit.text
    assert "[A组 / 工艺曲线]" in unit.text and "[B组 / 工艺曲线]" in unit.text
    assert "[原文范围 / 配方原文（按原对象及列）]" in unit.text
    assert all(c.text in unit.text for c in ir.conditions) and ir.proposal.limits in unit.text
    assert set(unit.evidence) == set(pointers) and all(note in saved["pending"] for note in ir.pending)
    assert unit.status == "candidate" and unit.level == 3 and row["capability_id"] is None
    assert not app.events.query(["claim_confirmed", "capability_granted"])
    assert app.authorized_source_replies(session.id, "customer:C01") == []
    assert saved["temperatures"][session.id]["celsius"] == [75.0, 75.0]


def test_prepared_ir_imports_candidate_with_full_conditions_on_original_requirement(tmp_path):
    app = _app(tmp_path)
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块，锦纶氨纶的，气流缸，75℃")
    app.save_escalate_note(session.id, "（合成）交研发对照操作报告", "sales:S01")
    q = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
    app.mark_prepared(q.id, q.owner_id)
    req = app.escalate(session.id, "sales:S01")
    doc = "synthetic-conditions"
    fragments = FolderSource("合成资料", "internal", "tests/fixtures/reader").fetch(doc)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps({"source_id": doc, "file_sha256": "synthetic",
        "fragments": [f.model_dump() for f in fragments]}), encoding="utf-8")
    app.kb.sources = [EvidenceReportSource(evidence_path)]
    app.source_owners = {doc: req.assigned_rd}
    ir = json.loads(Path("tests/fixtures/reader/synthetic-operation-ir.json").read_text(encoding="utf-8"))
    ir["proposal"]["author"] = req.assigned_rd
    ir_path = tmp_path / "operation-ir.json"
    ir_path.write_text(json.dumps(ir), encoding="utf-8")
    app.config["source_irs"] = {doc: str(ir_path)}
    pointers = [f"{f.doc_id}#{f.span}@{f.fingerprint}" for f in fragments]
    app.save_source_preparation(req.id, pointers[:1], [], "本单与报告纤维不同，待核对", req.assigned_rd)
    params = {"req_id": req.id, "doc_id": doc, "by": req.assigned_rd}
    before = app.kb.state_path.read_bytes()
    with pytest.raises(ValueError, match="完整依据"):
        POST["/api/source-preparation/compile"](app, params)
    assert app.kb.state_path.read_bytes() == before
    app.save_source_preparation(req.id, pointers, [], "本单与报告纤维不同，待核对", req.assigned_rd)
    ctx = app.agents.context(req.assigned_rd, thread=req.id)
    result = app.agents.call_tool(ctx, "compile_source_preparation", {"req_id": req.id, "doc_id": doc})
    assert result.ok
    saved = app.source_preparation(req.id, req.assigned_rd)
    row = saved["compilation"]["report"]["admitted"][0]
    unit = app.kb._units[row["ku_id"]]
    assert saved == result.data and saved["claim_ids"] == [unit.id]
    assert "纤维不同" in saved["pending"] and ir["pending"][0] in saved["pending"]
    assert unit.status == "candidate" and unit.level == 3 and row["capability_id"] is None
    assert unit.evidence == pointers and unit.id in {u.id for u in app.candidate_claims(req.id, req.assigned_rd)}
    assert "B组单次观察" in unit.text and all(c["text"] in unit.text for c in ir["conditions"])
    assert ir["proposal"]["limits"] in unit.text and "锦纶氨纶" in unit.text
    assert not app.events.query(["claim_confirmed"]) and not app.agents.pending(req.assigned_rd)
    material_path = app.run_dir / "source_preparations" / f"{req.id.replace(':', '_')}.json"
    material = material_path.read_bytes()
    status_params = {"req_id": req.id, "viewer": req.assigned_rd}
    pending = GET["/api/source-preparation/status"](app, status_params)
    assert pending == {"claims": [{"id": unit.id, "status": "candidate", "confirmed_by": None}], "capabilities": []}
    reply_params = {"session_id": session.id, "viewer": "sales:S01"}
    assert GET["/api/source-preparation/replies"](app, reply_params) == []
    assert GET["/api/source-preparation/status"](app, status_params | {"viewer": "pm:agent"}) is None
    # 以下签字仅在合成临时实例中模拟；复用已有 C7 读取与真人确认入口。
    review = POST["/api/qi/review"](app, {"ku_ids": [unit.id], "by": req.assigned_rd})
    POST["/api/qi/confirm"](app, {"req_id": req.id, "ku_ids": [unit.id], "by": req.assigned_rd,
                               "reviewed_evidence": review["reviewed_evidence"]})
    confirmed = GET["/api/source-preparation/status"](app, status_params)
    assert confirmed["claims"] == [{"id": unit.id, "status": "active", "confirmed_by": req.assigned_rd}]
    assert confirmed["capabilities"] == []
    assert GET["/api/source-preparation/replies"](app, reply_params) == []
    # 现有“本层答不了”信号提出授予事项，模拟研发签字后状态回到原单。
    app.kb.explore(unit.title, app.actors["sales:S01"], session_id=session.id)
    app.scan()
    grant = next(q for q in app.bus.list(family="qi_grant")
                 if q.refs.get("ku_id") == unit.id and q.refs.get("form") == "statement")
    app.mark_prepared(grant.id, grant.owner_id)
    cap = app.sign_qi_grant(grant.id, req.assigned_rd, note="（合成）请联系专员安排沟通。")
    granted = GET["/api/source-preparation/status"](app, status_params)
    assert granted["capabilities"] == [{"id": cap.id, "form": "statement", "audience": cap.audience,
        "status": "active", "granted_by": req.assigned_rd, "approved_by": None}]
    assert GET["/api/source-preparation/replies"](app, reply_params) == [
        {"ref": cap.id, "text": cap.payload["text"], "audience": 1}]
    assert GET["/api/source-preparation/replies"](app, reply_params | {"viewer": "customer:C01"}) == []
    sales_ctx = app.agents.context("sales:S01", session_id=session.id)
    assert app.agents.call_tool(sales_ctx, "get_authorized_replies", {}).data == app.authorized_source_replies(session.id, "sales:S01")
    with pytest.raises(PermissionDenied):
        app.save_reply_draft(session.id, f"[[{cap.id}]]", "sales:S01")
    # 客户层另外授权后，客户只看到这一句；研发原文和本单待补说明不随之返回。
    app.kb.explore(unit.title, app.actors["customer:C01"], session_id=session.id)
    app.scan()
    customer_grant = next(q for q in app.bus.list(family="qi_grant")
                          if q.refs.get("ku_id") == unit.id and q.refs.get("audience") == "0")
    app.mark_prepared(customer_grant.id, customer_grant.owner_id)
    public = app.sign_qi_grant(customer_grant.id, req.assigned_rd, note="（合成）客户可查看的流程说明。")
    shown = GET["/api/source-preparation/replies"](app, reply_params | {"viewer": "customer:C01"})
    assert shown == [{"ref": public.id, "text": public.payload["text"], "audience": 0}]
    assert unit.text not in json.dumps(shown, ensure_ascii=False)
    another = app.start_session("customer:C01", "sales:S01")
    assert app.authorized_source_replies(another.id, "customer:C01") == []
    next_customer = app.start_session("customer:C02")
    reused = app.add_turn(next_customer.id, "customer", f"{unit.title}，为什么会这样？")
    assert public.payload["text"] in reused.replies[-1].text and unit.text not in reused.replies[-1].text
    assert any(e.session_id == reused.id and e.payload["capability_id"] == public.id
               for e in app.events.query(["capability_used"]))
    with pytest.raises(PermissionDenied):
        GET["/api/source-preparation/replies"](app, reply_params | {"viewer": "customer:C02"})
    app.withdraw_claim(unit.id, req.assigned_rd)
    withdrawn = GET["/api/source-preparation/status"](app, status_params)
    assert withdrawn["claims"][0]["status"] == "withdrawn"
    assert withdrawn["capabilities"][0]["status"] == "suspended"
    assert GET["/api/source-preparation/replies"](app, reply_params) == []
    assert app.authorized_source_replies(session.id, "customer:C01") == []
    assert material_path.read_bytes() == material
