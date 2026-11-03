"""E4队友准备：核对边界配对与知识快照，专业标签不自动填写。"""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field, model_validator
import yaml

from huayan.clock import get_clock
from huayan.contracts import Capability, KnowledgeUnit, Situation
from huayan.contracts._base import BaseModel, datetime
from huayan.eval.backtest import fingerprint


class ReusePair(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_group: str = Field(min_length=1)
    kind: Literal["真实", "还原", "合成"]
    split: Literal["dev", "heldout"]
    prepared_by: str = Field(min_length=1)
    prepared_at: datetime
    judgment_kind: Literal["真实", "合成"]
    judgment_id: str
    capability_id: str
    viewer_id: str = Field(min_length=1)
    design: str = Field(min_length=1)
    first_words: str = Field(min_length=1)
    expected: Literal["同范围", "条件未知", "超范围"] | None = None
    basis: str = ""
    labeled_by: str = ""
    labeled_at: datetime | None = None

    @model_validator(mode="after")
    def completed_label(self):
        if self.expected is not None and (not self.basis.strip() or not self.labeled_by.strip() or self.labeled_at is None):
            raise ValueError("选择专业标签后须填写理由、实际标注人和带时区时间")
        return self


def prepare(pairs_path, output_dir, split="dev", seeds_dir="seeds"):
    raw = yaml.safe_load(Path(pairs_path).read_text(encoding="utf-8"))
    state_path = Path(raw["knowledge_state"])
    state_bytes = state_path.read_bytes()
    if sha256(state_bytes).hexdigest() != raw["knowledge_state_sha256"]:
        raise ValueError("知识状态快照指纹不符，请重新核对配对依据")
    state = json.loads(state_bytes)
    ids, groups, counts = set(), {}, Counter()
    for item in raw["pairs"]:
        if item["id"] in ids:
            raise ValueError(f"重复配对编号：{item['id']}")
        ids.add(item["id"])
        if item["kind"] not in ("真实", "还原", "合成") or item["split"] not in ("dev", "heldout"):
            raise ValueError("kind或split不在配对格式取值中")
        group, part = item["source_group"], item["split"]
        if group in groups and groups[group] != part:
            raise ValueError(f"同一来源组跨dev/heldout：{group}")
        groups[group] = part
        counts[item["kind"], part] += 1
    selected = [ReusePair.model_validate(item) for item in raw["pairs"] if item["split"] == split]
    units = {unit["id"]: unit for unit in state["units"]}
    caps = {cap["id"]: cap for cap in state["capabilities"]}
    rows = []
    for pair in selected:
        if pair.judgment_id not in units or pair.capability_id not in caps:
            raise ValueError(f"配对所关联判断或能力不存在：{pair.id}")
        unit = KnowledgeUnit.model_validate(units[pair.judgment_id])
        cap = Capability.model_validate(caps[pair.capability_id])
        if cap.form != "applicable" or unit.id not in cap.based_on:
            raise ValueError(f"配对须关联该判断的applicable能力：{pair.id}")
        situation = Situation(phenomenon=cap.payload["phenomenon"], conditions=cap.payload["conditions"],
                              temperature_c=cap.payload.get("temperature_c"), capability_id=cap.id)
        rows.append({"pair": pair.model_dump(mode="json"), "judgment": unit.model_dump(mode="json"),
                     "capability": cap.model_dump(mode="json"), "situation": situation.model_dump(mode="json"),
                     "limits": cap.payload.get("limits", ""), "professional_review": "pending"})
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {"knowledge_state": str(state_path), "knowledge_state_sha256": raw["knowledge_state_sha256"],
               "signature_nature": raw["signature_nature"], "pairs": [row["pair"] for row in rows]}
    (output / "pairs.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"task": "E4", "scope": "pair_preparation_only", "at": get_clock().now().isoformat(),
               "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
               "input": fingerprint(pairs_path), "knowledge_state_sha256": raw["knowledge_state_sha256"],
               "signature_nature": raw["signature_nature"], "split": split, "selected": len(rows),
               "not_selected": len(raw["pairs"]) - len(rows),
               "counts": {kind: {part: counts[kind, part] for part in ("dev", "heldout")}
                          for kind in ("真实", "还原", "合成")},
               "judgments": len({pair.judgment_id for pair in selected}),
               "judgment_counts": {kind: len({pair.judgment_id for pair in selected if pair.judgment_kind == kind})
                                   for kind in ("真实", "合成")},
               "filled_labels": sum(pair.expected is not None for pair in selected),
               "draft_labels": sum(pair.expected is None for pair in selected),
               "vocabulary": [fingerprint(Path(seeds_dir) / name) for name in ("slots.yaml", "phenomena.yaml")],
               "model_calls": 0, "models": {name: "未运行" for name in ("extractor", "jue", "jev")},
               "business_metrics": None, "zero_tolerance_findings": None}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E4边界配对准备", "", f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取/觉/Jev均未运行，实际模型名未产生，请求0；不是判断复用能力成绩。",
             "词表指纹（仅记录快照，未参与抽取）：" + "；".join(f"{v['path']} {v['sha256']}" for v in summary["vocabulary"]),
             f"知识状态SHA-256：{raw['knowledge_state_sha256']}；签字性质：{raw['signature_nature']}。",
             "", "| 配对来源类别 | dev | heldout |", "|---|---:|---:|"]
    lines += [f"| {kind} | {parts['dev']} | {parts['heldout']} |" for kind, parts in summary["counts"].items()]
    lines += ["", f"所选{split}配对{len(rows)}条、判断{summary['judgments']}条，其他分区{summary['not_selected']}条答案未解析或导出。",
              "判断来源类别单独计数（不等于专业确认）：" + json.dumps(summary["judgment_counts"], ensure_ascii=False),
              f"标签字段已填{summary['filled_labels']}条，草稿{summary['draft_labels']}条；字段齐全不表示专业核验通过。",
              "研发复核pending；零容忍、过度保守与命中率未评估，不填写0次错误。",
              "保留limits和能力层级；完整枚举与温度在范围内不等于可直接推荐，也未检查当前主体权限。", ""]
    shown = set()
    for row in rows:
        pair, unit, cap = row["pair"], row["judgment"], row["capability"]
        if (unit["id"], cap["id"]) not in shown:
            shown.add((unit["id"], cap["id"]))
            lines += [f"## 判断依据：{unit['id']}／{cap['id']}", "", unit["title"], "", unit["text"],
                      "", "原始证据指针：" + "；".join(unit["evidence"]), ""]
        lines += [f"## {pair['id']}｜{pair['design']}", "", pair["first_words"], "",
                  f"判断{unit['id']}（{unit['status']}）／能力{cap['id']}（{cap['status']}，受众{cap['audience']}），主体{pair['viewer_id']}。",
                  f"专业标签：{pair['expected'] or '未标注'}；理由：{pair['basis'] or '待实际标注'}。",
                  "情境：" + json.dumps(row["situation"], ensure_ascii=False), "原文limits：" + (row["limits"] or "未附限制原文"), ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
