"""来源副本复核演示：复用合成温度走链状态，模拟恢复或重建判断，无模型实调。"""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.ingest.compile import EvidenceRef, Proposal


def run_case(root, name, config, state_path, previous, replacement, new_range):
    output = root / name
    sources = output / "sources"
    sources.mkdir(parents=True)
    source_path = sources / "synthetic-temperature.txt"
    before = Path(previous["source"]).read_text(encoding="utf-8")
    source_path.write_text(before, encoding="utf-8")
    shutil.copyfile(state_path, output / "qi_state.json")
    config = config | {"qi_state": str(output / "qi_state.json"), "run_root": str(output / "runs"),
        "sources": [{"name": "合成温度演示副本", "kind": "internal", "root": str(sources)}],
        "gateway_mock": True, "system1_impl": "mock", "extractor": "rule", "replay": False,
        "realtime_model": "jue_proto", "scheduled_model": "jue_proto", "agent_memory": False}
    path = output / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(path), run_id="developer-simulation")
    unit = app.kb._units[previous["claim_id"]]
    old = app.kb._caps[previous["branches"][0]["candidates"][0]["capability_id"]]
    prefix = "（合成需求）深一块浅一块，锦纶氨纶的，溢流缸，"
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", prefix + "75℃")
    assert session.recommendation.candidates[0].capability_id == old.id
    original_evidence = list(unit.evidence)
    after = before.replace("70—80℃", replacement)
    assert after != before
    source_path.write_text(after, encoding="utf-8")
    (output / "source-change.json").write_text(json.dumps({"before": before, "after": after}, ensure_ascii=False, indent=2), encoding="utf-8")
    changed = app.recheck_evidence()
    assert unit.id in changed and unit.status == "candidate" and old.status == "suspended"
    assert app._sessions[session.id].recommendation is None
    question = next(q for q in app.questions("rd:R01") if q.family == "qi_review" and q.refs["ku_id"] == unit.id)
    suspended = {"claim": unit.model_dump(mode="json"), "capability": old.model_dump(mode="json"),
                 "question": question.model_dump(mode="json")}
    review = app.review_claims([unit.id], "rd:R01")
    assert review["reviewed_evidence"][unit.id] != original_evidence
    scope_ids = []

    def approve(cap_id):
        q = next(q for q in app.questions("pm:P01") if q.family == "scope_update" and q.refs["capability_id"] == cap_id)
        app.mark_prepared(q.id, "pm:agent")
        scope_ids.append(q.id)
        return app.extend_scope(q.id, "开发者模拟：按修改后的合成范围重新批准。", "pm:P01")

    if new_range is None:
        app.mark_prepared(question.id, "rd:R01")
        app.resolve(question.id, "sign", "rd:R01", note="开发者模拟：仅区间连接符更正，原判断和范围仍成立。",
                    reviewed_evidence=review["reviewed_evidence"])
        assert unit.evidence == review["reviewed_evidence"][unit.id] and old.status == "active"
        current = app.recommend_now(session.id)
        assert current.recommendation.candidates[0].capability_id == old.id
        active = old
        new_claim_id = None
    else:
        app.withdraw_claim(unit.id, "rd:R01")
        proposal = Proposal(title="合成修订温度判断", text="合成修订：范围收窄，原判断不再使用。", product="T-205",
            phenomenon="color_unlevel", form="applicable", author="rd:R01", conditions=["锦纶氨纶", "溢流染色机"],
            temperature_c=new_range, evidence=[EvidenceRef(doc_id="synthetic-temperature", span="p1", quote=replacement)])
        row, = app.import_proposals([proposal], "rd:R01")["admitted"]
        new_claim_id = row["ku_id"]
        assert new_claim_id != unit.id and app.kb._units[new_claim_id].status == "candidate"
        assert app.kb._caps[row["capability_id"]].status == "proposed"
        reviewed = app.review_claims([new_claim_id], "rd:R01")
        app.confirm_claims(None, [new_claim_id], "rd:R01", reviewed_evidence=reviewed["reviewed_evidence"])
        internal = approve(row["capability_id"])
        app.kb.explore("合成修订温度判断", app.actors["customer:C01"], session_id=session.id)
        app.scan()
        grant = next(q for q in app.questions("rd:R01") if q.family == "qi_grant"
                     and q.refs.get("capability_id") == internal.id and q.refs["audience"] == "0")
        app.mark_prepared(grant.id, "rd:R01")
        pending = app.sign_qi_grant(grant.id, "rd:R01", note="开发者模拟：仅授予修改后的合成范围。")
        assert pending.id != old.id and pending.status == "proposed" and pending.approved_by is None
        assert app.recommend_now(session.id).recommendation is None
        active = approve(pending.id)
        assert old.status == "suspended" and unit.status == "withdrawn"
        assert app.recommend_now(session.id).recommendation is None
    next_session = app.start_session("customer:C02")
    next_session = app.add_turn(next_session.id, "customer", prefix + "72℃")
    candidate, = next_session.recommendation.candidates
    assert candidate.status == "confirmed" and candidate.capability_id == active.id
    uses = [e.model_dump(mode="json") for e in app.events.query(["capability_used"])
            if e.session_id == next_session.id and e.payload["capability_id"] == active.id]
    assert uses
    metering = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()
                if line] if app.meter.path.exists() else []
    final_review = app.bus.get(question.id)
    assert final_review.status == "resolved"
    return {"case": name, "before": before, "after": after, "changed": changed,
            "old_evidence": original_evidence, "reviewed_evidence": review["reviewed_evidence"], "suspended": suspended,
            "review_question": final_review.model_dump(mode="json"), "old_claim_status": unit.status,
            "old_capability_status": old.status, "new_claim_id": new_claim_id,
            "active_capability": active.model_dump(mode="json"), "scope_questions": scope_ids,
            "original_session": app.view_session(session.id, "sales:S01").model_dump(mode="json"),
            "next_session": next_session.id, "use_events": uses,
            "recommendation_withdrawals": [e.model_dump(mode="json") for e in app.events.query(["recommendation_withdrawn"])],
            "runtime": app.status().model_dump(mode="json") | {"model_calls": sum(r["kind"] == "llm" for r in metering)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-run", required=True, help="已通过的合成 temperature-chain 运行目录")
    args = parser.parse_args()
    source_run = Path(args.from_run)
    previous = json.loads((source_run / "summary.json").read_text(encoding="utf-8"))
    if previous["chain"] != "applicable_temperature" or previous["data_kind"] != "synthetic_fixture_requests_and_signatures_in_fresh_instance":
        parser.error("仅接受合成温度走链产物，不接受真实专业状态")
    config = yaml.safe_load((source_run / "app.yaml").read_text(encoding="utf-8"))
    state_path = Path(config["run_root"]) / "developer-simulation" / "qi_state.json"
    original_state = state_path.read_bytes()
    original_source = Path(previous["source"]).read_bytes()
    output = Path("data/knowledge_v10/validation") / f"revision-chain-{uuid4().hex[:8]}"
    cases = [run_case(output, "restore", config, state_path, previous, "70～80℃", None),
             run_case(output, "replace", config, state_path, previous, "70—74℃", (70, 74))]
    assert state_path.read_bytes() == original_state and Path(previous["source"]).read_bytes() == original_source
    summary = {"at": get_clock().now().isoformat(), "result": "passed", "data_kind": "synthetic_revision_simulation",
               "from_run": str(source_run), "cases": cases, "input_files_unchanged": True,
               "real_signatures": 0, "real_participants": [],
               "manual_help": ["脚本修改演示副本并显式执行recheck和重匹配", "模拟研发复核、重建判断和授予，模拟产品经理批准；未测Agent自主准备"],
               "remaining": ["真实报告专业签字和范围", "真实业务来源复核", "四岗位真人试用"]}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"| {c['case']} | {c['after'].strip()} | {c['old_capability_status']} | {c['active_capability']['id']} | {c['next_session']} |" for c in cases]
    report = ("# V10 来源副本复核演示\n\n全部资料、需求、范围与签字为合成演练；无真人参与，无模型实调。\n\n"
              "共同起点为已通过的70—80℃能力，75℃会话有推荐。修改后手工recheck：结论candidate、能力suspended，原推荐撤回，出现qi_review。\n\n"
              "| 处置 | 修改后片段 | 旧能力最终状态 | 后续使用能力 | 72℃下一会话 |\n|---|---|---|---|---|\n" + "\n".join(lines) + "\n\n"
              "- restore：仅连接符更正，显式审阅新指纹，沿qi_review签字恢复原判断及原范围；75℃原会话显式重匹配后恢复推荐。\n"
              "- replace：范围改成70—74℃，撤回旧判断并新建候选，重新确认、授予与产品经理批准；75℃原会话仍无推荐，72℃下一单使用新能力。\n\n"
              "两分支使用独立副本。原合成状态与夹具字节未变；真实报告及其状态未读取或修改。此结果仅为软件演示，不代表真人业务来源复核通过。\n")
    (output / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"result": "passed", "data_kind": "developer_simulation", "report": str(output / "report.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
