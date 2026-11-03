"""E2队友准备：从E1样本生成离线分流标注表，不运行业务或模型。"""
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
import yaml

from huayan.contracts._base import BaseModel, datetime
from huayan.eval.backtest import fingerprint
from huayan.eval.e1 import prepare as prepare_e1

Route = Literal["自助解决", "交业务员", "复用", "研发不立项", "入研", "产品机会"]
PATHS = ["自助解决", "交业务员", "复用", "研发不立项", "入研", "产品机会"]


class RoutingLabel(BaseModel):
    id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    expected_path: Route | None = None
    knowledge_state: str = ""
    knowledge_state_sha256: str = ""
    viewer: str = ""
    basis: str = ""
    labeled_by: str = ""
    labeled_at: datetime | None = None

    @model_validator(mode="after")
    def filled_annotation(self):
        if self.expected_path is not None:
            if not all(s.strip() for s in (self.knowledge_state, self.viewer, self.basis, self.labeled_by)) or self.labeled_at is None:
                raise ValueError("选择路径后须填知识状态、判断主体、依据、实际标注人和带时区时间")
            if len(self.knowledge_state_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.knowledge_state_sha256):
                raise ValueError("选择路径后须填写所依据qi_state副本的完整SHA-256（小写）")
        return self


def prepare(cases_path, seeds_dir, output_dir, labels_path=None, split="dev"):
    output = Path(output_dir)
    check = prepare_e1(cases_path, seeds_dir, output / "e1-check", split)
    cases = {r["id"]: r for r in json.loads((output / "e1-check/details.json").read_text(encoding="utf-8"))}
    labels = []
    ids = set()
    if labels_path:
        data = yaml.safe_load(Path(labels_path).read_text(encoding="utf-8"))
        if data["cases_fingerprint"] != check["input"]["sha256"] or data["split"] != split:
            raise ValueError("E1输入指纹或分区已变化，请重新导出标注表")
        all_case_ids = {item["id"] for item in yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))["cases"]}
        for item in data["labels"]:
            if item["id"] in ids:
                raise ValueError(f"重复标注编号：{item['id']}")
            ids.add(item["id"])
            if item["case_id"] not in all_case_ids:
                raise ValueError(f"标注所关联E1样本不存在：{item['case_id']}")
            # 未选分区的标签只识别case_id，不解析、导出其路径答案。
            if item["case_id"] in cases:
                labels.append(RoutingLabel.model_validate(item))
    for case_id in sorted(cases.keys() - {label.case_id for label in labels}):
        base_id = label_id = f"E2-{case_id}"
        suffix = 2
        while label_id in ids:
            label_id = f"{base_id}-{suffix}"
            suffix += 1
        ids.add(label_id)
        labels.append(RoutingLabel(id=label_id, case_id=case_id))
    labels.sort(key=lambda label: (label.case_id, label.id))
    rows = [{"case": cases[label.case_id]["annotation"], "label": label.model_dump(mode="json"),
             "vocabulary_gaps": cases[label.case_id]["vocabulary_gaps"],
             "status": "字段已填，未核专业判断" if label.expected_path else "未标注草稿"} for label in labels]
    payload = {"cases_fingerprint": check["input"]["sha256"], "split": split,
               "labels": [row["label"] for row in rows]}
    (output / "annotations.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    form = {"paths": PATHS, "cases_fingerprint": payload["cases_fingerprint"], "split": split, "rows": rows}
    template = Path(__file__).with_name("routing_form.html").read_text(encoding="utf-8")
    (output / "annotation-form.html").write_text(template.replace("__E2_DATA__", json.dumps(form, ensure_ascii=False)
                                                              .replace("<", "\\u003c")), encoding="utf-8")
    summary = {"task": "E2", "kind": "preparation_only", "at": check["at"],
        "code_commit": check["code_commit"], "working_tree_dirty": check["working_tree_dirty"],
        "input": check["input"], "labels_input": fingerprint(labels_path) if labels_path else None,
        "vocabulary": check["vocabulary"], "counts": check["counts"], "split": split,
        "selected_cases": len(cases), "not_selected_cases": check["not_selected"],
        "label_rows": len(rows), "filled_labels": sum(label.expected_path is not None for label in labels),
        "draft_labels": sum(label.expected_path is None for label in labels), "paths": PATHS,
        "vocabulary_gap_count": check["vocabulary_gap_count"], "model_calls": 0,
        "models": check["models"], "business_metrics": None, "zero_tolerance_findings": None}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E2队友准备检查", "", "本报告只验证标注文件和静态表，不是分流能力成绩。",
             f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取/觉/Jev未运行，模型请求0；未加载、验证或修改标注所指qi_state。",
             f"所选{split}样本{len(cases)}条；其他分区{check['not_selected']}条答案未检查或导出。",
             f"标注行{len(rows)}条：路径及必要字段已填{summary['filled_labels']}条，草稿{summary['draft_labels']}条。",
             "字段齐全不表示已经专业核验；未标注不会自动变成金标。", "",
             "| 来源类别 | dev | heldout |", "|---|---:|---:|"]
    lines += [f"| {kind} | {parts['dev']} | {parts['heldout']} |" for kind, parts in check["counts"].items()]
    lines += ["", "标注表：annotation-form.html；可导出JSON后通过--labels再次检查。",
              "原始E1检查及词表缺口见e1-check/，逐条关联见details.json。",
              "输入指纹：" + check["input"]["sha256"],
              "词表指纹：" + "；".join(f"{v['path']} {v['sha256']}" for v in check["vocabulary"]), "",
              "混淆矩阵、误转/漏转与零容忍结果未评估，不填写0次通过或成功率。",
              "研发不立项/入研等需要专业判断的终局不能用待处理状态或脚本代签补齐。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
