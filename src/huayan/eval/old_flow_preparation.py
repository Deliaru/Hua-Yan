"""E6把默认参数逐项转为访谈问题；不运行旧流程推算或填实测值。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field
import yaml

from huayan.clock import get_clock
from huayan.contracts._base import BaseModel
from huayan.eval.backtest import fingerprint


class InterviewQuestion(BaseModel):
    field: str = Field(min_length=1)
    question: str = Field(min_length=1)
    unit: Literal["分钟", "小时", "比例(0–1)", "来源说明"]
    respondents: list[str] = Field(min_length=1)
    scope: str = Field(min_length=1)


def prepare(defaults_path, questions_path, output_dir, origin_path=None, seeds_dir="seeds"):
    defaults_path = Path(defaults_path)
    defaults = yaml.safe_load(defaults_path.read_text(encoding="utf-8"))
    params = {"source": defaults["source"], **{f"minutes.{key}": value for key, value in defaults["minutes"].items()},
              **{key: value for key, value in defaults.items() if key not in ("minutes", "source")}}
    questions = [InterviewQuestion.model_validate(item) for item in yaml.safe_load(
        Path(questions_path).read_text(encoding="utf-8"))["questions"]]
    fields = [q.field for q in questions]
    if len(fields) != len(set(fields)):
        raise ValueError("访谈问题字段重复")
    if set(fields) != set(params):
        raise ValueError(f"问题与默认字段不一致；缺少{sorted(set(params)-set(fields))}；多出{sorted(set(fields)-set(params))}")
    origin = json.loads(Path(origin_path).read_text(encoding="utf-8")) if origin_path else None
    if origin is not None and origin["sha256"] != sha256(defaults_path.read_bytes()).hexdigest():
        raise ValueError("默认参数快照与来源指纹不一致")
    at = get_clock().now().isoformat()
    rows = [{**q.model_dump(), "default_value": params[q.field],
             "default_status": "来源元字段" if q.field == "source" else "假设",
             "answer": None, "answer_kind": None, "respondent": "", "answered_at": None,
             "period": "", "sample_count": None, "numerator": None, "denominator": None,
             "evidence_source": "", "evidence_quote": ""} for q in questions]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    sheet = {"scope": "interview_preparation_only", "prepared_by": "Codex（问题整理，尚未访谈）",
             "prepared_at": at, "questions": rows}
    (output / "interview-template.yaml").write_text(yaml.safe_dump(sheet, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 无实际数据时只给来源占位，不把假设数值放进override，让消费方继续使用默认值并标假设。
    (output / "old-flow.override-template.yaml").write_text("source: 假设\nminutes: {}\n", encoding="utf-8")
    (output / "details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"task": "E6", "scope": "interview_preparation_only", "at": at,
               "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
               "inputs": [fingerprint(defaults_path), fingerprint(questions_path)], "definition_origin": origin,
               "questions": len(rows), "numeric_parameters": len(params) - 1, "source_fields": 1,
               "assumed_parameters": len(params) - 1, "answered": 0, "measured_parameters": 0,
               "case_counts": {kind: {part: 0 for part in ("dev", "heldout")} for kind in ("真实", "还原", "合成")},
               "vocabulary": [fingerprint(Path(seeds_dir) / name) for name in ("slots.yaml", "phenomena.yaml")],
               "model_calls": 0, "models": {name: "未运行" for name in ("extractor", "jue", "jev")},
               "business_metrics": None, "zero_tolerance_findings": None}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E6旧流程访谈准备", "", f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取/觉/Jev均未运行，实际模型名未产生，请求0；未运行旧流程或化言效率推算。",
             "词表指纹（仅记录快照）：" + "；".join(f"{v['path']} {v['sha256']}" for v in summary["vocabulary"]),
             "参数定义来源：" + json.dumps(origin, ensure_ascii=False),
             f"{len(rows)}个问题：{len(params)-1}个数值参数全部是假设，1个来源元字段；回答0、实测0。",
             "业务案例分母：真实/还原/合成的dev和heldout均为0；问题数不作业务样本数。",
             "效率、耗时差异和零容忍发现均未评估，不填写提效比例或零错误。", "",
             "覆盖模板只含source和空minutes，不含任何数值覆盖。逐参数来源留在访谈表，不塞入旧参数文件。", ""]
    for row in rows:
        lines += [f"## {row['field']}", "", row["question"], "",
                  f"单位：{row['unit']}；建议问：{'、'.join(row['respondents'])}。",
                  f"默认参考：{row['default_value']}（{row['default_status']}）；实际回答：未提供。",
                  "口径：" + row["scope"], ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
