"""E3记录级金标准备检查；不运行读取器、模型或业务评测。"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Literal

from pydantic import Field

from huayan.clock import get_clock
from huayan.contracts._base import BaseModel, datetime
from huayan.eval.backtest import fingerprint
from huayan.ingest.reader.evidence import EvidenceBlock
from huayan.ingest.reader.trials import TrialRecord, TrialText


class InputFile(BaseModel):
    path: str
    sha256: str


class GoldAnnotation(BaseModel):
    kind: Literal["真实", "合成"]
    split: Literal["dev", "heldout"]
    labeled_by: str = Field(min_length=1)
    labeled_at: datetime
    method: Literal["native_office_visual_and_xml"]
    professional_review: Literal["pending"] = "pending"
    original: InputFile
    native_docx: InputFile
    native_pages: list[InputFile] = Field(min_length=1)
    limits: list[TrialText]
    notes: list[str]


def prepare(record_path, annotation_path, evidence_path, output_dir):
    record = TrialRecord.model_validate_json(Path(record_path).read_text(encoding="utf-8"))
    annotation = GoldAnnotation.model_validate_json(Path(annotation_path).read_text(encoding="utf-8"))
    evidence = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    if (record.source_id, record.file_sha256) != (evidence["source_id"], evidence["file_sha256"]):
        raise ValueError("金标与证据的来源编号或原件指纹不一致")
    if record.file_sha256 != annotation.original.sha256:
        raise ValueError("标注原件指纹与金标不一致")
    for item in [annotation.original, annotation.native_docx, *annotation.native_pages]:
        if sha256(Path(item.path).read_bytes()).hexdigest() != item.sha256:
            raise ValueError(f"标注输入内容已变化：{item.path}")
    if [group.group for group in record.groups] != ["A", "B"]:
        raise ValueError("本准备包须按原工艺A、试样工艺B分别记录")
    if record.professional_confirmation is not None:
        raise ValueError("本准备入口不接收或代填专业确认")
    blocks = {b["span"]: EvidenceBlock.model_validate(b) for b in evidence["blocks"]}
    checked = 0

    def check_quote(span, quote, group=None, cell=None):
        if span not in blocks:
            raise ValueError(f"引用块不存在：{span}")
        block = blocks[span]
        if not quote.strip() or quote not in block.text:
            raise ValueError(f"引用原文不符：{span}")
        if group is not None and block.group not in (None, group):
            raise ValueError(f"{group}组引用了{block.group}组依据：{span}")
        if cell is not None:
            cells = {(item.row, item.column): item.text for item in block.cells}
            if cell not in cells or quote not in cells[cell]:
                raise ValueError(f"引用单元格不符：{span}")
        return block

    def check_citations(citations, group=None):
        nonlocal checked
        if not citations:
            raise ValueError("金标字段缺少原文引用")
        for citation in citations:
            block = check_quote(citation.span, citation.quote, group, citation.cell)
            fragment = block.fragment()
            if citation.fragment != f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}":
                raise ValueError(f"引用片段指纹不符：{citation.span}")
            if not citation.pages or not set(citation.pages) <= {loc.page for loc in block.locations}:
                raise ValueError(f"引用页码不符：{citation.span}")
            checked += 1

    def check_texts(items, group=None):
        for item in items:
            check_citations(item.evidence, group)

    def check_reading(reading, group=None):
        check_quote(reading.span, reading.quote, group, reading.cell)
        if group is not None and reading.group != group:
            raise ValueError("读数组别与所属工艺不一致")

    for items in (record.metadata, record.purpose, record.common_conditions, record.quality, record.cost,
                  record.follow_up, record.reported_results, record.review_notes, annotation.limits):
        check_texts(items)
    for group in record.groups:
        for item in group.formula:
            check_citations(item.evidence, group.group)
        for items in (group.formula_notes, group.operations):
            check_texts(items, group.group)
        if group.curve_evidence:
            check_citations(group.curve_evidence, group.group)
        for reading in group.curve_labels:
            check_reading(reading, group.group)
        if group.reported_time is not None:
            check_reading(group.reported_time, group.group)
    for change in record.changes:
        check_citations(change.evidence)
    if record.time.evidence:
        check_citations(record.time.evidence)
    for reading, group in ((record.time.a, "A"), (record.time.b, "B"), (record.time.reported_saving, None)):
        if reading is not None:
            check_reading(reading, group)
    summary = {"task": "E3", "scope": "gold_preparation_only", "at": get_clock().now().isoformat(),
               "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
               "working_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True)),
               "vocabulary": [fingerprint(Path("seeds") / name) for name in ("slots.yaml", "phenomena.yaml")],
               "models": {name: "未运行" for name in ("extractor", "jue", "jev", "vision")},
               "source_id": record.source_id, "kind": annotation.kind, "split": annotation.split,
               "counts": {kind: {part: int((kind, part) == (annotation.kind, annotation.split))
                                 for part in ("dev", "heldout")} for kind in ("真实", "还原", "合成")},
               "professional_review": annotation.professional_review, "records_checked": 1,
               "citation_occurrences_checked": checked, "limits": len(annotation.limits),
               "pending": len(record.pending), "model_calls": 0, "business_metrics": None,
               "zero_tolerance_findings": None,
               "input_sha256": {str(path): sha256(Path(path).read_bytes()).hexdigest()
                                for path in (record_path, annotation_path, evidence_path)}}
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    details = {"source_id": record.source_id, "status": "开发者草稿，研发未复核",
               "record": record.model_dump(mode="json"), "annotation": annotation.model_dump(mode="json")}
    (output / "details.json").write_text(json.dumps([details], ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E3金标准备检查", "", f"代码：{summary['code_commit']}；工作区有改动：{summary['working_tree_dirty']}。",
             "抽取、觉、Jev和视觉模型均未运行，实际模型名未产生，请求0；不是模型成绩。",
             "词表指纹（只记录快照，未参与转录）：" + "；".join(f"{v['path']} {v['sha256']}" for v in summary["vocabulary"]),
             "", "| 来源类别 | dev | heldout |", "|---|---:|---:|"]
    lines += [f"| {kind} | {parts['dev']} | {parts['heldout']} |" for kind, parts in summary["counts"].items()]
    lines += ["", "只检查显式传入的1份记录；其他资料未纳入本项，不计作跳过或已核验分母。",
             "零容忍项未评估，绝对数和逐条发现留空，不写0次通过。",
             f"来源：{record.source_id}；{annotation.kind} / {annotation.split}。",
             f"实际标注：{annotation.labeled_by}；{annotation.labeled_at.isoformat()}。",
             f"检查1份记录、{checked}处引用出现位置、{len(annotation.limits)}条原文限制。",
             "通过仅表示结构、输入指纹和引用核对；不证明字段语义正确或专业核验通过。",
             "研发复核pending；未运行读取器、模型、字段准确率或零容忍评测。逐条明细见details.json。", "",
             f"[金标草稿]({Path(record_path).resolve().as_posix()})",
             f"[标注说明及limits]({Path(annotation_path).resolve().as_posix()})", "", "## 原生页图", ""]
    lines += [f"- [第{n}页]({Path(item.path).resolve().as_posix()})" for n, item in enumerate(annotation.native_pages, 1)]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary
