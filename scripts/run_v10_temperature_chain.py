"""V10 升级需求回流与温度走链：独立实例、合成资料与模拟签字，无模型实调。"""
import json
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.ingest.compile import EvidenceRef, Proposal


def main():
    output = Path("data/knowledge_v10/validation") / f"temperature-chain-{uuid4().hex[:8]}"
    output.mkdir(parents=True)
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(output / "runs"), qi_state=None,
                  sources=[{"name": "合成温度资料（非企业报告）", "kind": "internal", "root": "tests/fixtures/reader"}],
                  gateway_mock=True, system1_impl="mock", extractor="rule", replay=False,
                  realtime_model="jue_proto", scheduled_model="jue_proto", agent_threads="object", agent_memory=False)
    config_path = output / "app.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(config_path), run_id="developer-simulation")
    # 仅撤销本次合成实例的旧无温度限制种子，避免它掩盖新范围；不读取真实实例。
    app.revoke_capability("cap:applicable:T-205:color_unlevel", "rd:R01")
    prefix = "（合成需求）深一块浅一块，锦纶氨纶的，溢流缸，"
    original = app.start_session("customer:C01", "sales:S01")
    original = app.add_turn(original.id, "customer", prefix + "75℃")
    assert original.recommendation is None
    # 仅为本次合成走链限定接单参与人，保持既有温度/复核演示的研发标识。
    actors = app.actors
    app.actors = {key: actor for key, actor in actors.items() if actor.role != "rd" or key == "rd:R01"}
    app.save_escalate_note(original.id, "开发者合成需求：请对照合成温度资料，准备后交研发判断。", "sales:S01")
    escalation = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{original.id}")
    app.mark_prepared(escalation.id, escalation.owner_id)
    req = app.escalate(original.id, "sales:S01")
    app.actors = actors
    assert req.assigned_rd == "rd:R01" and req.status == "draft"
    app.source_owners = {"synthetic-temperature": req.assigned_rd}
    tool_trace = []

    def call(ctx, name, args):
        result = app.agents.call_tool(ctx, name, args)
        if not result.ok:
            raise ValueError(result.error)
        tool_trace.append({"principal": ctx.principal.id, "tool": name, "arguments": args, "ok": result.ok})
        return result.data

    rd_context = app.agents.context(req.assigned_rd, thread=req.id)
    call(rd_context, "get_requirement", {"req_id": req.id})
    call(rd_context, "get_session", {"session_id": original.id})
    fragments = call(rd_context, "read_source", {"doc_id": "synthetic-temperature"})
    proposal = Proposal(title="合成温度适用判断", text="合成温度适用判断，待确认", product="T-205",
        phenomenon="color_unlevel", form="applicable", author="rd:R01", conditions=["锦纶氨纶", "溢流染色机"],
        temperature_c=(70, 80), evidence=[EvidenceRef(doc_id="synthetic-temperature", span="p1", quote="适用温度70—80℃")])
    row, = app.import_proposals([proposal], "rd:R01")["admitted"]
    unit, source = app.kb._units[row["ku_id"]], app.kb._caps[row["capability_id"]]
    stages = [{"step": "import", "claim_status": unit.status, "capability": source.model_dump(mode="json")}]
    assert unit.status == "candidate" and source.status == "proposed"
    call(rd_context, "save_source_preparation", {"req_id": req.id,
        "evidence": [f"{f['doc_id']}#{f['span']}@{f['fingerprint']}" for f in fragments],
        "claim_ids": [unit.id], "pending": "开发者合成范围，专业签字与用途批准仍未发生。"})
    review = app.review_claims([unit.id], "rd:R01")
    app.confirm_claims(req.id, [unit.id], "rd:R01", reviewed_evidence=review["reviewed_evidence"])
    assert unit.status == "active" and unit.confirmed_by == "rd:R01"
    assert source.status == "proposed"
    scope_questions = []

    def approve(cap_id):
        question = next(q for q in app.questions("pm:P01")
                        if q.family == "scope_update" and q.refs["capability_id"] == cap_id)
        assert json.loads(question.refs["temperature_c"]) == [70, 80]
        app.mark_prepared(question.id, "pm:agent")
        approved = app.extend_scope(question.id, "开发者模拟批准：仅限合成资料70—80℃及所列枚举条件。", "pm:P01")
        scope_questions.append(question.id)
        stages.append({"step": "scope_approved", "question_id": question.id, "capability": approved.model_dump(mode="json")})
        return approved

    approve(source.id)
    app.kb.explore("合成温度适用判断", app.actors["customer:C01"], session_id=original.id)
    app.scan()
    question = next(q for q in app.questions("rd:R01")
                    if q.family == "qi_grant" and q.refs.get("capability_id") == source.id and q.refs["audience"] == "0")
    assert any("70—80℃" in evidence.summary for evidence in question.evidence)
    app.mark_prepared(question.id, "rd:R01")
    granted = app.sign_qi_grant(question.id, "rd:R01", note="开发者模拟授予，非企业专业结论。")
    stages.append({"step": "granted_before_scope_approval", "capability": granted.model_dump(mode="json")})
    assert granted.status == "proposed" and granted.payload["temperature_c"] == [70, 80]
    assert not any(s.capability_id == granted.id for p in app.kb.view(app.actors["customer:C01"]).products for s in p.situations)
    assert app._sessions[original.id].recommendation is None
    approved = approve(granted.id)
    # 批准组织适用范围与审定本单复用是两件事；沿原入口准备并模拟研发签字回原单。
    assert app._requirements[req.id].status == "draft" and app._sessions[original.id].recommendation is None
    pm_context = app.agents.context("pm:agent", thread=req.id)
    note = "开发者合成演练：本单条件已核对，请联系业务员安排后续试样。"
    call(pm_context, "propose_reuse", {"req_id": req.id, "product_id": "T-205", "ku_refs": [],
        "customer_note": note, "note": f"仅依据已批准合成范围{approved.id}，本单75℃在70—80℃内。"})
    reuse_question = next(q for q in app.questions("rd:R01")
                          if q.family == "reuse_product" and q.refs["requirement_id"] == req.id)
    assert app.preparation_gap(reuse_question.id) == ""
    app.mark_prepared(reuse_question.id, "pm:agent")
    original = app.adopt_reuse(req.id, "rd:R01")
    assert original.recommendation.product_id == "T-205"
    assert app._requirements[req.id].status == "reused" and app.bus.get(reuse_question.id).status == "resolved"
    reuse_view = app.view_session(original.id, "sales:S01").reuse
    assert reuse_view.status == "adopted" and reuse_view.customer_note == note
    assert note in app.view_session(original.id, "customer:C01").card.note
    returned_basis = app.kb._caps[original.recommendation.candidates[0].capability_id]
    assert returned_basis.form == "statement" and returned_basis.payload["text"] == note
    assert any(s.capability_id == approved.id for p in app.kb.view(app.actors["customer:C01"]).products for s in p.situations)
    branches = []
    for label, text, expected in (("满足", "75℃", "confirmed"), ("待补", "温度不知道", "possible"), ("超范围", "85℃", None)):
        session = app.start_session("customer:C02")
        session = app.add_turn(session.id, "customer", prefix + text)
        candidates = session.recommendation.candidates if session.recommendation else []
        if expected is None:
            assert session.recommendation is None
            session = app.add_turn(session.id, "customer", "T-205怎么用")
            assert "不适用" in session.replies[-1].text
        else:
            candidate, = candidates
            assert candidate.status == expected and candidate.capability_id == approved.id
            assert candidate.unknown_slots == (["temperature_c"] if expected == "possible" else [])
        branches.append({"branch": label, "input": prefix + text, "session_id": session.id,
                         "temperature": session.need.temperature.model_dump(mode="json"),
                         "candidates": [c.model_dump(mode="json") for c in candidates], "replies": [r.text for r in session.replies]})
    uses = [e.model_dump(mode="json") for e in app.events.query(["capability_used"])
            if e.payload["capability_id"] == approved.id]
    assert any(e["session_id"] == branches[0]["session_id"] for e in uses)
    assert not any(e.payload.get("requirement_id") != req.id for e in app.events.query(["requirement_created"]))
    metering = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()
                if line] if app.meter.path.exists() else []
    summary = {
        "at": get_clock().now().isoformat(), "result": "passed", "chain": "applicable_temperature",
        "data_kind": "synthetic_fixture_requests_and_signatures_in_fresh_instance",
        "source": "tests/fixtures/reader/synthetic-temperature.txt", "product": "T-205", "temperature_c": approved.payload["temperature_c"],
        "claim_id": unit.id, "reviewed_evidence": review["reviewed_evidence"], "stages": stages,
        "original_session": original.id, "original_recommendation": original.recommendation.model_dump(mode="json"),
        "requirement_id": req.id, "requirement_status": app._requirements[req.id].status,
        "preparation": app.source_preparation(req.id, "rd:R01"), "tool_trace": tool_trace,
        "reuse_question": app.bus.get(reuse_question.id).model_dump(mode="json"),
        "original_return_basis": returned_basis.model_dump(mode="json"), "original_reuse": reuse_view.model_dump(mode="json"),
        "branches": branches, "use_events": uses,
        "simulated_confirmation_count": len(app.events.query(["claim_confirmed"])),
        "simulated_scope_approval_count": len(app.events.query(["scope_extended"])),
        "grant_question": question.model_dump(mode="json"), "scope_questions": scope_questions,
        "runtime": app.status().model_dump(mode="json") | {"model_calls": sum(r["kind"] == "llm" for r in metering)},
        "real_signatures": 0, "real_participants": [],
        "manual_help": ["开发者选用既有合成范围与资料并限定隔离分单参与人", "脚本驱动已注册准备工具和门面，未测Agent自主准备", "确认、授予、批准及本单复用审定均为模拟签字"],
        "remaining": ["真实报告的专业确认与适用范围", "真实需求单业务回流验收", "真实业务来源变化复核", "四岗位真人试用"],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "\n".join(f"| {b['branch']} | {b['input']} | {b['candidates'][0]['status'] if b['candidates'] else '无推荐；回答不适用'} | {b['session_id']} |" for b in branches)
    report = ("# V10 产品适用与温度开发者走链\n\n全部资料、范围、需求及签字均为合成演练；无真人参与，无模型实调。\n\n"
              f"- 合成产品T-205，70—80℃；依据：synthetic-temperature#p1；候选：{unit.id}。\n"
              f"- 固定指纹审阅确认 → 内部范围批准 → {question.id} 授予 → 客户层范围批准；客户能力：{approved.id}。\n"
              f"- 原单{req.id}经Agent工具保存依据和候选；客户层批准前无推荐，批准后仍待本单复用审定。\n"
              f"- 产品经理Agent工具准备复用建议，模拟研发审定后原单变为reused，原会话{original.id}收到T-205及审定说明；复用事项{reuse_question.id}结案。\n"
              f"- 原单推荐依据为本单审定的statement {returned_basis.id}；下一单按applicable {approved.id}匹配，两者分别记录。\n\n"
              "| 分支 | 合成原话 | 实际结果 | 会话 |\n|---|---|---|---|\n" + rows + "\n\n"
              f"模拟专业确认{summary['simulated_confirmation_count']}次，模拟范围批准{summary['simulated_scope_approval_count']}次；真实签字0。\n\n"
              "本次原单回流调用既有adopt_reuse，不调用recommend_now或增加自动回流机制。仅验证合成范围、准备工具、模拟签字与需求单回流；真实报告132℃试验点未被转成适用范围，真人业务及自主Agent准备仍待验证。\n")
    (output / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"result": "passed", "data_kind": "developer_simulation", "report": str(output / "report.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
