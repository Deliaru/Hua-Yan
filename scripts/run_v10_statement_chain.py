"""首份真实报告的授权说明链：独立副本、脚本化工具准备和模拟签字，无模型实调。"""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.ingest.trial_ir import OperationIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="data/knowledge_v10/instance-first-report/app.yaml")
    parser.add_argument("--doc-id", default="SRC-3a2130604c")
    parser.add_argument("--source-run", default="first-report")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.doc_id not in config.get("source_irs", {}):
        parser.error("需提供已登记 source_irs 的首份实例配置")
    ir = OperationIR.model_validate_json(Path(config["source_irs"][args.doc_id]).read_text(encoding="utf-8"))
    rd = ir.proposal.author
    if rd is None:
        parser.error("操作观察 IR 尚未指定研发归属")
    original_path = Path(config["qi_state"]) if config.get("qi_state") else Path(config["run_root"]) / args.source_run / "qi_state.json"
    original = original_path.read_bytes()
    output = Path("data/knowledge_v10/validation") / f"statement-chain-{uuid4().hex[:8]}"
    output.mkdir(parents=True)
    shutil.copyfile(original_path, output / "qi_state.json")
    config.update(qi_state=str(output / "qi_state.json"), run_root=str(output / "runs"),
                  gateway_mock=True, system1_impl="mock", extractor="rule", replay=False,
                  realtime_model="jue_proto", scheduled_model="jue_proto", agent_threads="object", agent_memory=False)
    config_path = output / "app.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(config_path), run_id="developer-simulation")
    # 仅为隔离演练限定接单参与人，创建需求后恢复；不修改原实例编制或归属。
    actors = app.actors
    app.actors = {key: actor for key, actor in actors.items() if actor.role != "rd" or key == rd}
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "（合成需求）深一块浅一块，锦纶氨纶的，气流缸，75℃")
    app.save_escalate_note(session.id, "（开发者模拟）先准备报告对照，条件差异交研发核对。", "sales:S01")
    escalation = next(q for q in app.bus.list(family="escalate_need") if q.object_id == f"session:{session.id}")
    app.mark_prepared(escalation.id, escalation.owner_id)
    req = app.escalate(session.id, "sales:S01")
    app.actors = actors
    assert req.assigned_rd == rd
    ctx = app.agents.context(rd, thread=req.id)
    tool_trace = []

    def call(name, arguments):
        result = app.agents.call_tool(ctx, name, arguments)
        if not result.ok:
            raise ValueError(result.error)
        tool_trace.append({"tool": name, "arguments": arguments, "ok": result.ok})
        return result.data

    call("get_requirement", {"req_id": req.id})
    call("get_session", {"session_id": session.id})
    call("read_source", {"doc_id": args.doc_id})
    pointers = list(dict.fromkeys(c.fragment for c in ir.evidence))
    call("save_source_preparation", {"req_id": req.id, "evidence": pointers, "claim_ids": [],
        "pending": "开发者合成需求与报告条件有差异，待真人核对；不得据此推断产品适用。"})
    prepared = call("compile_source_preparation", {"req_id": req.id, "doc_id": args.doc_id})
    row, = prepared["compilation"]["report"]["admitted"]
    unit = app.kb._units[row["ku_id"]]
    assert unit.status == "candidate" and row["capability_id"] is None
    assert all(c.text in unit.text for c in ir.conditions)
    assert app.authorized_source_replies(session.id, "customer:C01") == []
    review = app.review_claims([unit.id], rd)
    app.confirm_claims(req.id, [unit.id], rd, reviewed_evidence=review["reviewed_evidence"])
    question = f"{ir.proposal.product or ''} 染色不匀，为什么会这样？"
    app.kb.explore(question, app.actors["customer:C01"], session_id=session.id)
    app.scan()
    grant = next(q for q in app.bus.list(family="qi_grant")
                 if q.refs.get("ku_id") == unit.id and q.refs.get("audience") == "0")
    app.mark_prepared(grant.id, grant.owner_id)
    note = "开发者演练：本单需由技术人员核对工艺条件；本说明不构成产品适用结论。"
    capability = app.sign_qi_grant(grant.id, rd, note=note)
    original_reply = app.authorized_source_replies(session.id, "customer:C01")
    assert original_reply == [{"ref": capability.id, "text": note, "audience": 0}]
    next_session = app.start_session("customer:C02")
    reused = app.add_turn(next_session.id, "customer", question)
    assert note in reused.replies[-1].text and unit.text not in reused.replies[-1].text
    uses = [e.id for e in app.events.query(["capability_used"])
            if e.session_id == reused.id and e.payload["capability_id"] == capability.id]
    assert uses
    app.withdraw_claim(unit.id, rd)
    assert app.authorized_source_replies(session.id, "customer:C01") == []
    after = app.start_session("customer:C03")
    stopped = app.add_turn(after.id, "customer", question)
    assert note not in stopped.replies[-1].text
    assert original_path.read_bytes() == original
    metering = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()
                if line] if app.meter.path.exists() else []
    runtime = app.status().model_dump(mode="json") | {"model_calls": sum(r["kind"] == "llm" for r in metering)}
    summary = {
        "at": get_clock().now().isoformat(), "result": "passed", "chain": "statement_only",
        "data_kind": "real_report_with_synthetic_requests_and_signatures_in_isolated_instance",
        "source_id": args.doc_id, "ir_id": ir.id, "group": ir.group,
        "condition_count": len(ir.conditions), "evidence_count": len(unit.evidence),
        "requirement_id": req.id, "claim_id": unit.id, "capability_id": capability.id,
        "original_session": session.id, "next_session": reused.id, "after_withdraw_session": stopped.id,
        "original_reply": original_reply, "next_reply": reused.replies[-1].text, "use_events": uses,
        "withdrawn_claim_status": unit.status, "withdrawn_capability_status": app.kb._caps[capability.id].status,
        "tool_trace": tool_trace, "simulated_confirmation_count": len(app.events.query(["claim_confirmed"])),
        "simulated_grant_question": grant.id, "grant_question_status": grant.status,
        "original_qi_state_unchanged": True, "real_signatures": 0, "real_participants": [],
        "runtime": runtime,
        "manual_help": ["开发者限定隔离分单参与人", "脚本驱动已注册 Agent 工具，未测自主规划", "确认与授予措辞由开发者模拟"],
        "remaining": ["真实专业判断与用途范围", "产品适用及温度三分支走链", "来源变化复核", "四岗位真人试用"],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = (f"# V10 开发者授权说明链\n\n真实资料，合成需求、措辞及签字；无真人参与，无模型实调。\n\n"
              f"- 来源：{ir.source_id}；{ir.group}组，{len(ir.conditions)}项条件，{len(unit.evidence)}条依据。\n"
              f"- 原单：{req.id}；候选：{unit.id}；说明能力：{capability.id}。\n"
              f"- 原会话收到授权说明，下一会话 {reused.id} 实际引用，使用事件：{', '.join(uses)}。\n"
              f"- 结论撤回后能力 {app.kb._caps[capability.id].status}，原单及新会话停止返回说明。\n"
              f"- 模拟确认 {summary['simulated_confirmation_count']} 次；真实签字0；原实例知识状态未变。\n\n"
              "| 事项 | 软件走链观察 | 人工帮助 |\n|---|---|---|\n"
              f"| {escalation.id} 升级 | 已转入原需求 | 合成需求及升级说明 |\n"
              f"| {grant.id} 授予 | 低层答不了后提出，签字后 {grant.status} | 开发者模拟确认和授予 |\n\n"
              "本轮只验证授权说明链，不能据此宣称产品适用、温度范围、四岗位试用或真实研发判断通过。\n")
    (output / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"result": "passed", "data_kind": "developer_simulation", "report": str(output / "report.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
