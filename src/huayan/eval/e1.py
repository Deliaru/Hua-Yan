"""E1队友准备：检查标注文件与词表缺口，不运行抽取、觉、Jev或模型。"""
from collections import Counter
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field, model_validator
import yaml

from huayan.clock import get_clock
from huayan.contracts._base import BaseModel, datetime
from huayan.eval.backtest import fingerprint


class E1Case(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_group: str = Field(min_length=1)
    kind: Literal["真实", "还原", "合成"]
    labeled_by: str = Field(min_length=1)
    labeled_at: datetime
    basis: str = Field(min_length=1)
    split: Literal["dev", "heldout"]
    phenomenon: str = Field(min_length=1)
    first_words: str = Field(min_length=1)
    turns: list[str] = []
    final_conditions: dict[str, str]
    unknown: list[str] = []
    late_conditions: list[str] = []
    temperature_c: tuple[float, float] | None = None
    temperature_quote: str = ""
    tags: list[Literal["否定", "纠正"]] = []

    @model_validator(mode="after")
    def annotation_consistency(self):
        known = set(self.final_conditions)
        if self.temperature_c is not None:
            lower, upper = self.temperature_c
            if not lower <= upper or not self.temperature_quote.strip():
                raise ValueError("温度须为升序摄氏闭区间，并保留原话")
            if not any(self.temperature_quote in text for text in [self.first_words, *self.turns]):
                raise ValueError("temperature_quote必须逐字来自客户原话")
            known.add("temperature_c")
        if known.intersection(self.unknown):
            raise ValueError("最终已知与明确未知不能同时标在同一条件上")
        if not set(self.late_conditions) <= known | set(self.unknown):
            raise ValueError("晚到条件须同时标出最终值或明确未知")
        return self


def prepare(cases_path, seeds_dir, output_dir, split="dev"):
    """仅评测侧读取标注。未选择的split只计元数据，不解析或导出其答案。"""
    cases_path, seeds_dir, output = Path(cases_path), Path(seeds_dir), Path(output_dir)
    raw = yaml.safe_load(cases_path.read_text(encoding="utf-8"))["cases"]
    ids, sources, counts = set(), {}, Counter()
    for item in raw:
        if item["id"] in ids:
            raise ValueError(f"重复样本编号：{item['id']}")
        ids.add(item["id"])
        if item["kind"] not in ("真实", "还原", "合成") or item["split"] not in ("dev", "heldout"):
            raise ValueError("kind或split不在标注格式的取值中")
        source, part = item["source_group"], item["split"]
        if source in sources and sources[source] != part:
            raise ValueError(f"同一来源跨dev/heldout：{source}")
        sources[source] = part
        counts[(item["kind"], part)] += 1
    selected = [E1Case.model_validate(item) for item in raw if item["split"] == split]
    slots_doc = yaml.safe_load((seeds_dir / "slots.yaml").read_text(encoding="utf-8"))
    phen_doc = yaml.safe_load((seeds_dir / "phenomena.yaml").read_text(encoding="utf-8"))
    slots = {s["id"]: s["values"] for s in slots_doc["items"]}
    phenomena = {p["id"] for p in phen_doc["items"]} | {p["label"] for p in phen_doc["items"]}
    rows, gaps = [], []
    for case in selected:
        missing = []
        if case.phenomenon not in phenomena:
            missing.append(f"现象未覆盖：{case.phenomenon}")
        for slot, value in case.final_conditions.items():
            if slot not in slots or value not in slots[slot]:
                missing.append(f"条件或取值未覆盖：{slot}={value}")
        for slot in set(case.unknown + case.late_conditions) - set(slots) - {"temperature_c"}:
            missing.append(f"条件名未覆盖：{slot}")
        gaps += [{"id": case.id, "source": case.source, "original": m} for m in missing]
        rows.append({"id": case.id, "source": case.source, "kind": case.kind,
                     "annotation": case.model_dump(mode="json"), "vocabulary_gaps": missing,
                     "status": "词表待核对" if missing else "格式已检查，未核专业金标"})
    output.mkdir(parents=True, exist_ok=True)
    summary = {"at": get_clock().now().isoformat(), "task": "E1", "kind": "preparation_only",
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
        "input": fingerprint(cases_path), "vocabulary": [fingerprint(seeds_dir / name)
            for name in ("slots.yaml", "phenomena.yaml")],
        "placeholder_vocabulary": slots_doc["placeholder"] or phen_doc["placeholder"],
        "split": split, "selected": len(rows), "not_selected": len(raw) - len(rows),
        "counts": {kind: {part: counts[kind, part] for part in ("dev", "heldout")}
                   for kind in ("真实", "还原", "合成")},
        "source_groups": sources, "vocabulary_gap_count": len(gaps),
        "model_calls": 0, "models": {"extractor": "未运行", "jue": "未运行", "jev": "未运行"},
        "business_metrics": None, "zero_tolerance_findings": None,
        "evidence_status": "无可检查样本" if not selected else "仅合成回归准备"
                           if all(c.kind == "合成" for c in selected) else "仅准备检查，不代表专业标注已核验"}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    gap_text = "# E1词表缺口\n\n仅列本次所选split，不改词表，不强制映射原词。\n\n"
    gap_text += "\n".join(f"- {g['id']}（{g['source']}）：{g['original']}" for g in gaps) or "本次所选样本未发现词表缺口。"
    (output / "vocab_gaps.md").write_text(gap_text + "\n", encoding="utf-8")
    lines = ["# E1队友准备检查", "", "本报告只检查标注文件与词表，不是需求理解能力成绩。",
             f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取、觉、Jev均未运行，模型请求0；没有mock模型成绩。",
             f"本次选择{split} {len(rows)}条，其他split {summary['not_selected']}条未检查答案。",
             "", "| 来源类别 | dev | heldout |", "|---|---:|---:|"]
    lines += [f"| {kind} | {parts['dev']} | {parts['heldout']} |" for kind, parts in summary["counts"].items()]
    lines += ["", f"词表缺口{len(gaps)}项，详见vocab_gaps.md；逐条检查见details.json。",
              "词表指纹：" + "；".join(f"{v['path']} {v['sha256']}" for v in summary["vocabulary"]),
              "", "零容忍项：未执行业务评测，不填写0次通过。",
              "真实金标、抽取准确率、追问率与进研发完整率未评估；材料获取和专业标注不属本项队友准备交付。"]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
