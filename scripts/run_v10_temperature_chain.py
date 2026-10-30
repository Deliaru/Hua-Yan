"""V10 产品适用与温度走链：独立实例、合成资料与模拟签字，无模型实调。"""
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
    proposal = Proposal(title="合成温度适用判断", text="合成温度适用判断，待确认", product="T-205",
        phenomenon="color_unlevel", form="applicable", author="rd:R01", conditions=["锦纶氨纶", "溢流染色机"],
        temperature_c=(70, 80), evidence=[EvidenceRef(doc_id="synthetic-temperature", span="p1", quote="适用温度70—80℃")])
    row, = app.import_proposals([proposal], "rd:R01")["admitted"]
    unit, source = app.kb._units[row["ku_id"]], app.kb._caps[row["capability_id"]]
    stages = [{"step": "import", "claim_status": unit.status, "capability": source.model_dump(mode="json")}]
    assert unit.status == "candidate" and source.status == "proposed"
    review = app.review_claims([unit.id], "rd:R01")
    app.confirm_claims(None, [unit.id], "rd:R01", reviewed_evidence=review["reviewed_evidence"])
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
    assert app.recommend_now(original.id).recommendation is None
    approved = approve(granted.id)
    original = app.recommend_now(original.id)
    assert original.recommendation.product_id == "T-205"
    assert original.recommendation.candidates[0].capability_id == approved.id
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
    assert any(e["session_id"] == original.id for e in uses)
    assert any(e["session_id"] == branches[0]["session_id"] for e in uses)
    metering = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()
                if line] if app.meter.path.exists() else []
    summary = {
        "at": get_clock().now().isoformat(), "result": "passed", "chain": "applicable_temperature",
        "data_kind": "synthetic_fixture_requests_and_signatures_in_fresh_instance",
        "source": "tests/fixtures/reader/synthetic-temperature.txt", "product": "T-205", "temperature_c": approved.payload["temperature_c"],
        "claim_id": unit.id, "reviewed_evidence": review["reviewed_evidence"], "stages": stages,
        "original_session": original.id, "original_recommendation": original.recommendation.model_dump(mode="json"),
        "branches": branches, "use_events": uses,
        "simulated_confirmation_count": len(app.events.query(["claim_confirmed"])),
        "simulated_scope_approval_count": len(app.events.query(["scope_extended"])),
        "grant_question": question.model_dump(mode="json"), "scope_questions": scope_questions,
        "runtime": app.status().model_dump(mode="json") | {"model_calls": sum(r["kind"] == "llm" for r in metering)},
        "real_signatures": 0, "real_participants": [],
        "manual_help": ["开发者选用既有合成范围与资料", "脚本驱动门面并模拟研发和产品经理签字，未测Agent自主准备", "原会话由脚本显式请求重新匹配"],
        "remaining": ["真实报告的专业确认与适用范围", "真实需求单业务回流验收", "来源变化复核", "四岗位真人试用"],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "\n".join(f"| {b['branch']} | {b['input']} | {b['candidates'][0]['status'] if b['candidates'] else '无推荐；回答不适用'} | {b['session_id']} |" for b in branches)
    report = ("# V10 产品适用与温度开发者走链\n\n全部资料、范围、需求及签字均为合成演练；无真人参与，无模型实调。\n\n"
              f"- 合成产品T-205，70—80℃；依据：synthetic-temperature#p1；候选：{unit.id}。\n"
              f"- 固定指纹审阅确认 → 内部范围批准 → {question.id} 授予 → 客户层范围批准；客户能力：{approved.id}。\n"
              f"- 客户层批准前原会话无推荐，批准后显式重匹配，原会话 {original.id} 得到T-205；下一会话实际使用同一能力。\n\n"
              "| 分支 | 合成原话 | 实际结果 | 会话 |\n|---|---|---|---|\n" + rows + "\n\n"
              f"模拟专业确认{summary['simulated_confirmation_count']}次，模拟范围批准{summary['simulated_scope_approval_count']}次；真实签字0。\n\n"
              "仅验证产品范围与温度软件链。脚本显式重匹配不代表已升级需求单自动回流；真实报告132℃试验点未被转成适用范围。来源复核与四岗位真人试用仍待完成。\n")
    (output / "report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"result": "passed", "data_kind": "developer_simulation", "report": str(output / "report.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
