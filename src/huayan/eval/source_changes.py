"""E8合成副本变更：门面重查/复核及原匹配器核对，不调用模型裁决。"""
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from typing import Literal

from pydantic import Field, model_validator
import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts._base import BaseModel, datetime
from huayan.domain import match_candidates
from huayan.eval.backtest import fingerprint
from huayan.ingest.compile import EvidenceRef, Proposal


class SourceChange(BaseModel):
    id: str = Field(min_length=1)
    source: str
    source_group: str
    kind: Literal["合成"]
    split: Literal["dev", "heldout"]
    type: Literal["referenced_condition", "unrelated_paragraph", "whitespace_format", "equivalent_typography"]
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    review_action: Literal["none", "restore", "replace"]
    new_temperature_c: tuple[float, float] | None = None
    expected_affected: list[Literal["temperature_claim", "control_claim"]]
    expected_review: Literal["不受影响", "仍然成立", "要改或撤销"]
    basis: str = Field(min_length=1)
    labeled_by: str = Field(min_length=1)
    labeled_at: datetime

    @model_validator(mode="after")
    def revision_range(self):
        if self.review_action == "replace" and (self.new_temperature_c is None or self.new_temperature_c[0] > self.new_temperature_c[1]):
            raise ValueError("重建分支须填写升序摄氏闭区间")
        return self


def run_change(case, config_path, output):
    output.mkdir(parents=True)
    sources = output / "sources"
    sources.mkdir()
    source = sources / "synthetic-source.txt"
    original = Path(case.source).read_text(encoding="utf-8")
    source.write_text(original, encoding="utf-8")
    shutil.copyfile("tests/fixtures/e8/synthetic-control.txt", sources / "synthetic-control.txt")
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if config["gateway_mock"] or config["system1_impl"] != "onejev" or config["replay"]:
        raise ValueError("E8实际运行只接受当前真实模型配置，不使用mock/fallback或回放")
    config.update(seeds_dir="tests/fixtures/mini_seeds", sources=[{"name": "E8合成副本", "kind": "internal", "root": str(sources)}],
                  qi_state=None, run_root=str(output / "runs"), source_trials={}, source_irs={}, source_manifest=None,
                  llm_cache_dir=None, agent_threads="object", agent_memory=False, pm_lines={},
                  realtime_model="jue_proto", scheduled_model="jue_proto")
    local_config = output / "app.yaml"
    local_config.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(local_config), run_id="synthetic-change")
    # 种子旧范围仅在新建演示实例内撤销，避免掩盖本条有来源的范围。
    app.revoke_capability("cap:applicable:T-205:color_unlevel", "rd:R01")

    def import_range(temperature, quote):
        proposal = Proposal(title="E8合成温度判断", text="合成范围判断，非企业专业结论", product="T-205",
            phenomenon="color_unlevel", form="applicable", author="rd:R01", conditions=["锦纶氨纶", "溢流染色机"],
            temperature_c=temperature, evidence=[EvidenceRef(doc_id="synthetic-source", span="p1", quote=quote)])
        row, = app.import_proposals([proposal], "rd:R01")["admitted"]
        return row

    def confirm_and_approve(row):
        review = app.review_claims([row["ku_id"]], "rd:R01")
        app.confirm_claims(None, [row["ku_id"]], "rd:R01", reviewed_evidence=review["reviewed_evidence"])
        q = next(q for q in app.questions("pm:P01") if q.family == "scope_update" and q.refs["capability_id"] == row["capability_id"])
        app.mark_prepared(q.id, "pm:agent")
        app.extend_scope(q.id, "开发者模拟：仅批准合成资料所列温度范围。", "pm:P01")

    row = import_range((70, 80), "70—80℃")
    confirm_and_approve(row)
    control = Proposal(title="E8合成独立观察", text="不受其他来源改写影响的合成观察", author="rd:R01",
                       phenomenon="color_unlevel", evidence=[EvidenceRef(doc_id="synthetic-control", span="p1", quote="合成独立对照")])
    control_row, = app.import_proposals([control], "rd:R01")["admitted"]
    review = app.review_claims([control_row["ku_id"]], "rd:R01")
    app.confirm_claims(None, [control_row["ku_id"]], "rd:R01", reviewed_evidence=review["reviewed_evidence"])
    unit, capability = app.kb._units[row["ku_id"]], app.kb._caps[row["capability_id"]]

    def matches(temperature):
        candidates = match_candidates("color_unlevel", {"fiber": "锦纶氨纶", "equipment": "溢流染色机"},
            app.kb.view(app.actors["rd:R01"]).products, temperature_c=(temperature, temperature))
        return [candidate.model_dump(mode="json") for candidate in candidates if candidate.product_id == "T-205"]

    initial = {"claim_id": unit.id, "capability_id": capability.id, "evidence": list(unit.evidence), "matches75": matches(75)}
    if not initial["matches75"]:
        raise ValueError("合成初始75℃范围未建立，不能验证变更")
    if original.count(case.before) != 1:
        raise ValueError("变更目标须在原副本恰好出现一次")
    after = original.replace(case.before, case.after, 1)
    source.write_text(after, encoding="utf-8")
    changed = app.recheck_evidence()
    questions = [q for q in app.questions("rd:R01") if q.family == "qi_review" and q.refs["ku_id"] == unit.id]
    after_recheck = {"changed": changed, "claim_status": unit.status, "capability_status": capability.status,
                     "control_status": app.kb._units[control_row["ku_id"]].status,
                     "matches75": matches(75), "review_questions": [q.model_dump(mode="json") for q in questions]}
    (output / "after-recheck.json").write_text(json.dumps(after_recheck, ensure_ascii=False, indent=2), encoding="utf-8")
    new_id = None
    if case.review_action == "restore":
        q, = questions
        reviewed = app.review_claims([unit.id], "rd:R01")
        app.mark_prepared(q.id, "rd:R01")
        app.resolve(q.id, "sign", "rd:R01", note="开发者合成复核：只更正连接符，原范围仍成立。",
                    reviewed_evidence=reviewed["reviewed_evidence"])
    elif case.review_action == "replace":
        app.withdraw_claim(unit.id, "rd:R01")
        revised = import_range(case.new_temperature_c, case.after)
        new_id = revised["ku_id"]
        confirm_and_approve(revised)
    final = {"old_claim_status": unit.status, "old_capability_status": capability.status,
             "new_claim_id": new_id, "matches75": matches(75), "matches72": matches(72),
             "old_evidence": initial["evidence"], "final_old_evidence": list(unit.evidence),
             "review_status": [app.bus.get(q.id).status for q in questions]}
    actual_affected = [alias for alias, uid in (("temperature_claim", unit.id), ("control_claim", control_row["ku_id"])) if uid in changed]
    meter = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()] if app.meter.path.exists() else []
    return {"id": case.id, "initial": initial, "source_before": original, "source_after": after,
            "actual_affected": actual_affected, "after_recheck": after_recheck, "final": final,
            "model_call_records": sum(r["kind"] in ("llm", "s1") for r in meter),
            "run_dir": str(app.run_dir), "professional_review": "pending", "signature_nature": "developer_simulation"}


def prepare(changes_path, output_dir, config_path=None):
    output = Path(output_dir)
    if output.exists():
        raise ValueError("输出目录已存在，请保留原运行并另选--out")
    raw = yaml.safe_load(Path(changes_path).read_text(encoding="utf-8"))["changes"]
    cases = [SourceChange.model_validate(item) for item in raw]
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("变更编号重复")
    if any(case.split != "dev" for case in cases):
        raise ValueError("本合成开发演示只接收dev，不读取heldout答案")
    output.mkdir(parents=True)
    originals = {path: Path(path).read_bytes() for path in {case.source for case in cases} | {"tests/fixtures/e8/synthetic-control.txt"}}
    (output / "changes.json").write_text(json.dumps({"changes": [case.model_dump(mode="json") for case in cases]},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"task": "E8", "scope": "synthetic_source_revision", "at": get_clock().now().isoformat(),
              "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
              "input": fingerprint(changes_path), "sources": [fingerprint(path) for path in sorted(originals)],
              "vocabulary": [fingerprint(Path("tests/fixtures/mini_seeds") / name) for name in ("slots.yaml", "phenomena.yaml")],
              "counts": {"真实": {"dev": 0, "heldout": 0}, "还原": {"dev": 0, "heldout": 0},
                         "合成": {"dev": len(cases), "heldout": 0}},
              "status": "not_run", "model_calls": 0, "models": "抽取/Jev/助手未运行；显式运行时qi_review由规则觉提出", "professional_review": "pending",
              "real_signatures": 0, "details": [], "zero_tolerance_findings": None}
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if config_path is not None:
        for case in cases:
            prediction = run_change(case, config_path, output / case.id)
            (output / case.id / "prediction.json").write_text(json.dumps(prediction, ensure_ascii=False, indent=2), encoding="utf-8")
            affected_ok = sorted(prediction["actual_affected"]) == sorted(case.expected_affected)
            final = prediction["final"]
            old_cap = prediction["initial"]["capability_id"]
            review_ok = (bool(final["matches75"]) and final["matches75"][0]["capability_id"] == old_cap
                         and final["old_claim_status"] == "active" and final["old_capability_status"] == "active"
                         if case.expected_review in ("不受影响", "仍然成立") else
                         not final["matches75"] and bool(final["matches72"])
                         and final["matches72"][0]["capability_id"] != old_cap
                         and final["old_claim_status"] == "withdrawn" and final["old_capability_status"] == "suspended")
            if case.review_action == "restore":
                review_ok = review_ok and final["review_status"] == ["resolved"] and final["old_evidence"] != final["final_old_evidence"]
            elif case.review_action == "replace":
                review_ok = review_ok and final["review_status"] == ["resolved"] and final["new_claim_id"] is not None
            else:
                review_ok = review_ok and not prediction["after_recheck"]["review_questions"]
            inactive = (not prediction["after_recheck"]["matches75"] and prediction["after_recheck"]["capability_status"] == "suspended"
                        and prediction["after_recheck"]["claim_status"] == "candidate"
                        and len(prediction["after_recheck"]["review_questions"]) == 1
                        if case.expected_affected else True)
            result["details"].append({"id": case.id, "type": case.type, "expected_affected": case.expected_affected,
                "actual_affected": prediction["actual_affected"], "affected_matches": affected_ok,
                "review_matches": review_ok, "changed_basis_unavailable": inactive,
                "control_unchanged": prediction["after_recheck"]["control_status"] == "active",
                "model_calls": prediction["model_call_records"]})
        result.update(status="completed", model_calls=sum(row["model_calls"] for row in result["details"]),
                      scoped_stale_match_count=sum(not row["changed_basis_unavailable"] for row in result["details"]),
                      all_checks_passed=all(row["affected_matches"] and row["review_matches"] and row["changed_basis_unavailable"]
                                           and row["control_unchanged"] for row in result["details"]),
                      config=fingerprint(config_path))
    result["input_files_unchanged"] = all(Path(path).read_bytes() == data for path, data in originals.items())
    (output / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "details.json").write_text(json.dumps(result["details"], ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E8合成资料变更", "", f"代码：{result['code_commit']}；工作区改动：{result['working_tree_dirty']}。",
             "抽取/Jev/助手均未运行，qi_review由规则觉提出（scored_by=rule）；当前真实配置只构建组件，无mock模型验证。",
             "词表指纹：" + "；".join(f"{v['path']} {v['sha256']}" for v in result["vocabulary"]),
             f"合成dev变更{len(cases)}条；真实/还原/heldout均0；状态{result['status']}；实际模型调用{result['model_calls']}。",
             "变更金标为开发者按合成语义编写，研发未核；确认、批准、复核均是独立实例的模拟签字。",
             "只验证当前研发知识视图+原匹配器的固定结构条件，不是原话抽取或客户推荐模型成绩。", "",
             "| 变更 | 受影响名单一致 | 复核后匹配一致 | 受影响时挂起检查 | 独立对照未改 |", "|---|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['affected_matches']} | {r['review_matches']} | {r['changed_basis_unavailable']} | {r['control_unchanged']} |"
              for r in result["details"]]
    lines += ["", f"本次挂起阶段结构匹配不符次数：{result.get('scoped_stale_match_count', '未运行')}；逐条布尔结果见表。",
              "未受影响分支的挂起检查按不适用通过，不表示原能力不可用。此局部核验只检查本次受影响能力在结构匹配入口不命中；不是所有业务出口/真实新需求的零错误结论。",
              "每例prediction.json、after-recheck.json及运行目录保存状态/事件；原始夹具不修改。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
