"""E5合成提问准备检查；不运行助手、泄露检测或模型。"""
from collections import Counter
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field, model_validator
import yaml

from huayan.clock import get_clock
from huayan.contracts import ROLE_LEVEL
from huayan.contracts._base import BaseModel, datetime
from huayan.eval.backtest import fingerprint


class LeakPrompt(BaseModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_group: str = Field(min_length=1)
    kind: Literal["真实", "还原", "合成"]
    split: Literal["dev", "heldout"]
    prepared_by: str = Field(min_length=1)
    prepared_at: datetime
    category: Literal["对抗", "正常"]
    role: Literal["customer", "sales"]
    surface: Literal["customer_answer", "sales_workbench", "sales_history", "sales_agent", "recommendation_evidence"]
    scenario: str = Field(min_length=1)
    turns: list[str] = Field(min_length=1)
    review_focus: str = Field(min_length=1)
    forbidden: list[str] | None = None
    public_points: list[str] | None = None
    gold_source: str = ""
    basis: str = ""
    labeled_by: str = ""
    labeled_at: datetime | None = None

    @model_validator(mode="after")
    def valid_draft(self):
        if any(not turn.strip() for turn in self.turns):
            raise ValueError("提问轮次不能是空白")
        if (self.surface == "customer_answer" and self.role != "customer"
                or self.surface.startswith("sales_") and self.role != "sales"):
            raise ValueError("拟观察出口与绑定角色不一致")
        points = self.forbidden if self.category == "对抗" else self.public_points
        if points is not None:
            if not points or any(not point.strip() for point in points):
                raise ValueError("未标注须用null，已填金标内容不得为空")
            if not all(value.strip() for value in (self.gold_source, self.basis, self.labeled_by)) or self.labeled_at is None:
                raise ValueError("填写金标后须提供来源、理由、实际标注人和带时区时间")
        return self


def prepare(prompts_path, output_dir, split="dev", seeds_dir="seeds"):
    raw = yaml.safe_load(Path(prompts_path).read_text(encoding="utf-8"))["prompts"]
    ids, groups, counts = set(), {}, Counter()
    for item in raw:
        if item["id"] in ids:
            raise ValueError(f"重复提问编号：{item['id']}")
        ids.add(item["id"])
        if item["kind"] not in ("真实", "还原", "合成") or item["split"] not in ("dev", "heldout"):
            raise ValueError("kind或split不在提问格式取值中")
        group, part = item["source_group"], item["split"]
        if group in groups and groups[group] != part:
            raise ValueError(f"同一来源组跨dev/heldout：{group}")
        groups[group] = part
        counts[item["kind"], part] += 1
    selected = [LeakPrompt.model_validate(item) for item in raw if item["split"] == split]
    rows = []
    for sample in selected:
        points = sample.forbidden if sample.category == "对抗" else sample.public_points
        rows.append({"sample": sample.model_dump(mode="json"), "planned_level": ROLE_LEVEL[sample.role],
                     "label_fields_filled": points is not None, "professional_review": "pending"})
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "prompts.json").write_text(json.dumps({"prompts": [row["sample"] for row in rows]},
                                                   ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"task": "E5", "scope": "prompt_preparation_only", "at": get_clock().now().isoformat(),
               "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
               "input": fingerprint(prompts_path), "split": split, "selected": len(rows),
               "not_selected": len(raw) - len(rows),
               "counts": {kind: {part: counts[kind, part] for part in ("dev", "heldout")}
                          for kind in ("真实", "还原", "合成")},
               "categories": dict(Counter(sample.category for sample in selected)),
               "planned_roles": dict(Counter(sample.role for sample in selected)),
               "planned_surfaces": dict(Counter(sample.surface for sample in selected)),
               "multi_turn_cases": sum(len(sample.turns) > 1 for sample in selected),
               "filled_labels": sum(row["label_fields_filled"] for row in rows),
               "draft_labels": sum(not row["label_fields_filled"] for row in rows),
               "vocabulary": [fingerprint(Path(seeds_dir) / name) for name in ("slots.yaml", "phenomena.yaml")],
               "model_calls": 0, "models": {name: "未运行" for name in ("extractor", "jue", "jev", "assistant")},
               "knowledge_state_loaded": False, "business_metrics": None, "zero_tolerance_findings": None}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E5提问准备检查", "", f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取/觉/Jev/助手均未运行，实际模型名未产生，请求0；未装载知识状态或执行leak_hits。",
             "词表指纹（仅记录快照，未参与回答）：" + "；".join(f"{v['path']} {v['sha256']}" for v in summary["vocabulary"]),
             "", "| 提问来源类别 | dev | heldout |", "|---|---:|---:|"]
    lines += [f"| {kind} | {parts['dev']} | {parts['heldout']} |" for kind, parts in summary["counts"].items()]
    lines += ["", f"所选{split} {len(rows)}条，其他分区{summary['not_selected']}条答案未解析或导出。",
              "题型：" + json.dumps(summary["categories"], ensure_ascii=False),
              "拟观察出口（只是设计，未运行）：" + json.dumps(summary["planned_surfaces"], ensure_ascii=False),
              f"多轮题{summary['multi_turn_cases']}条；标签字段已填{summary['filled_labels']}条，草稿{summary['draft_labels']}条。",
              "研发复核pending；正常提问的公开可答要点尚须逐条核定，题型不代表已证明应答/拒答。",
              "泄露数、过度拒答率和零容忍发现均未评估，不填写0次泄露或成功率。",
              "role只是拟绑定身份，实际执行须由服务端认定；提问中的自称身份不能改变权限。", ""]
    for row in rows:
        sample = row["sample"]
        lines += [f"## {sample['id']}｜{sample['category']}｜{sample['scenario']}", "",
                  f"拟绑定：{sample['role']}（L{row['planned_level']}）；拟观察出口：{sample['surface']}。", ""]
        lines += [f"{n}. {turn}" for n, turn in enumerate(sample["turns"], 1)]
        lines += ["", "审阅关注（不是金标）：" + sample["review_focus"],
                  "待核禁出内容：" + json.dumps(sample["forbidden"], ensure_ascii=False),
                  "待核公开应答要点：" + json.dumps(sample["public_points"], ensure_ascii=False), ""]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary
