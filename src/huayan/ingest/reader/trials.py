"""首份报告的原生 A/B 记录；保存资料观察，不创建业务 Trial 或契的结论。"""
from decimal import Decimal
import re
from typing import Literal

from huayan.contracts._base import BaseModel
from huayan.contracts.seeds import Level

from .evidence import EvidenceBlock, Reading


class Citation(BaseModel):
    fragment: str
    span: str
    pages: list[int]
    quote: str
    cell: tuple[int, int] | None = None


class TrialText(BaseModel):
    text: str
    evidence: list[Citation]


class Ingredient(BaseModel):
    name: str
    value: str
    unit: str | None
    basis: str | None = None
    evidence: list[Citation]


class TrialGroup(BaseModel):
    group: Literal["A", "B"]
    formula: list[Ingredient]
    formula_notes: list[TrialText]
    curve_labels: list[Reading]
    curve_evidence: list[Citation]
    reported_time: Reading | None
    operations: list[TrialText]


class TrialChange(BaseModel):
    item: str
    before: str | None
    after: str | None
    evidence: list[Citation]


class TimeComparison(BaseModel):
    a: Reading | None
    b: Reading | None
    reported_saving: Reading | None
    calculated_saving: str | None = None
    formula: str | None = None
    unit: str = "min"
    matches_report: bool | None = None
    basis: str = "报告标注的升温总时长；未从曲线重算，是否包含保温等阶段待确认。"
    evidence: list[Citation]


class TrialRecord(BaseModel):
    source_id: str
    file_sha256: str
    source: Literal["public", "internal", "external"]
    level: Level
    extracted_by: Literal["rule"] = "rule"
    status: Literal["draft"] = "draft"
    metadata: list[TrialText]
    purpose: list[TrialText]
    common_conditions: list[TrialText]
    groups: list[TrialGroup]
    changes: list[TrialChange]
    time: TimeComparison
    quality: list[TrialText]
    cost: list[TrialText]
    follow_up: list[TrialText]
    pending: list[str]
    reported_results: list[TrialText] = []
    review_notes: list[TrialText] = []
    professional_confirmation: str | None = None


def cite(block, quote=None, cell=None):
    fragment = block.fragment()
    return Citation(fragment=f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}", span=block.span,
                    pages=[loc.page for loc in block.locations], quote=block.text if quote is None else quote, cell=cell)


def as_text(block):
    return TrialText(text=block.text.strip(), evidence=[cite(block)])


def read_formula(blocks):
    ingredients, notes = [], []
    for block in blocks:
        if block.kind == "paragraph":
            match = re.fullmatch(r"\s*(.+?)\s{2,}(\d+(?:\.\d+)?|[Xx])\s*(g/L|%)?\s*", block.text)
            if match:
                ingredients.append(Ingredient(name=match[1], value=match[2], unit=match[3], evidence=[cite(block)]))
            continue
        cells = {(c.row, c.column): c for c in block.cells}
        if "染色配方" in block.text and not any(c.text.strip() == "用量" for c in block.cells):
            notes.append(as_text(block))  # 多织物并列表保留整表列关系，不冒认成 A/B 配方。
        for header in [c for c in block.cells if c.text.strip() == "用量"]:
            for amount in [c for c in block.cells if c.column == header.column and c.row > header.row and c.text.strip()]:
                name = cells[(amount.row, amount.column - 1)]
                match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(.*?)\s*", amount.text)
                value, unit = (match[1], match[2] or None) if match else (amount.text.strip(), None)
                basis = unit[1:].strip() or None if unit and unit.startswith("%") else None
                ingredients.append(Ingredient(name=name.text.strip(), value=value, unit=unit, basis=basis,
                    evidence=[cite(block, name.text, (name.row, name.column)),
                              cite(block, amount.text, (amount.row, amount.column))]))
        notes.extend(TrialText(text=c.text, evidence=[cite(block, c.text, (c.row, c.column))])
                     for c in block.cells if c.text.strip().startswith("染料配方"))
    return ingredients, notes


def find_minutes(blocks, pattern, group):
    for block in blocks:
        texts = [(c.text, (c.row, c.column)) for c in block.cells] if block.kind == "table" else [(block.text, None)]
        for text, cell in texts:
            match = re.search(pattern, text)
            if match:
                return Reading(span=block.span, cell=cell, object=block.section, group=group,
                               stage="报告标注时间", value=match[1], unit="min", quote=match[0])
    return None


def formula_amount(item):
    return item.value + (item.unit or "（单位未记载）") if item is not None else None


def build_trial_record(blocks: list[EvidenceBlock], readings: list[Reading], pending: list[str]):
    by_span = {b.span: b for b in blocks}
    body = [b for b in blocks if b.kind == "paragraph" and b.text.strip() != b.section.strip()]
    groups = []
    for group in ("A", "B"):
        own = [b for b in blocks if b.group == group]
        formula, notes = read_formula([b for b in own if b.kind == "table" or "配方" in b.section])
        curves = [b for b in own if "工艺曲线" in b.text or b.kind == "textbox"]
        groups.append(TrialGroup(group=group, formula=formula, formula_notes=notes,
            curve_labels=[r for r in readings if r.group == group and r.span in {b.span for b in curves}],
            curve_evidence=[cite(b) for b in curves],
            reported_time=find_minutes(curves, r"升温总时长\s*(\d+(?:\.\d+)?)\s*min", group),
            operations=[as_text(b) for b in body if b.group == group]))
    a, b = groups
    changes = []
    left, right = {x.name: x for x in a.formula}, {x.name: x for x in b.formula}
    for name in dict.fromkeys([*left, *right]):
        old, new = left.get(name), right.get(name)  # 配方表允许某一组未列出此物料。
        if formula_amount(old) != formula_amount(new):
            changes.append(TrialChange(item=f"配方：{name}", before=formula_amount(old), after=formula_amount(new),
                evidence=(old.evidence if old is not None else []) + (new.evidence if new is not None else [])))
    left_holds = {tuple(r.conditions): r for r in a.curve_labels if r.stage == "保温"}
    right_holds = {tuple(r.conditions): r for r in b.curve_labels if r.stage == "保温"}
    for conditions in dict.fromkeys([*left_holds, *right_holds]):
        old, new = left_holds.get(conditions), right_holds.get(conditions)
        before, after = old.value + old.unit if old is not None else None, new.value + new.unit if new is not None else None
        if before != after:
            changes.append(TrialChange(item="保温点：" + "、".join(conditions), before=before, after=after,
                evidence=[cite(by_span[r.span], r.quote, r.cell) for r in (old, new) if r is not None]))
    results = [x for x in body if "结果" in x.section and "分析" in x.section]
    saving = find_minutes(results, r"(?:共)?节省\s*(\d+(?:\.\d+)?)\s*min", None)
    comparison = TimeComparison(a=a.reported_time, b=b.reported_time, reported_saving=saving,
        evidence=[cite(by_span[r.span], r.quote, r.cell) for r in (a.reported_time, b.reported_time, saving) if r is not None])
    if comparison.a is not None and comparison.b is not None:
        difference = Decimal(comparison.a.value) - Decimal(comparison.b.value)
        comparison.calculated_saving = str(difference)
        comparison.formula = f"{comparison.a.value} - {comparison.b.value}"
        comparison.matches_report = difference == Decimal(saving.value) if saving is not None else None
    quality, cost = [], []
    target = None
    for block in results:
        if re.match(r"\d+[.、]\s*.*(?:品质|质量|成本)", block.text.strip()) or re.fullmatch(
            r"试样(?:品质|质量|成本)方面[：:]", block.text.strip()):
            target = cost if "成本" in block.text else quality
        elif re.match(r"\d+[.、]\s*试样结论", block.text.strip()):
            target = None
        elif target is None and re.search(r"布面.*(?:合格|色花|色点)", block.text):
            quality.append(as_text(block))
        elif not re.match(r"\s*试样人[：:]", block.text) and target is not None:
            target.append(as_text(block))
    missing = list(pending)
    missing.extend(f"{group.group}组 {item.name}：百分比基准未记载，不默认解释为 %owf。"
                   for group in groups for item in group.formula if item.unit == "%")
    missing.extend(f"{group.group}组 {item.name}：原文用量为 {item.value}，具体数值及单位待补，不按零处理。"
                   for group in groups for item in group.formula if item.value.upper() == "X")
    missing.extend(f"{block.span}：多阶段文字工艺保留原句，未结构化速率/阶段或从中重算总时长。"
                   for block in body if "升温速率及保温时间" in block.text)
    missing.extend(f"{block.span}：多织物配方表按原列保留，未拆成原/试样配方；百分比基准未确认，不换算用量。"
                   for block in blocks if block.kind == "table" and "染色配方" in block.text
                   and not any(c.text.strip() == "用量" for c in block.cells))
    if comparison.matches_report is False:
        missing.append("报告 A/B 总时长差值与所写节省时间不一致，保留两者待核对。")
    return TrialRecord(source_id=blocks[0].source_id, file_sha256=blocks[0].file_sha256,
        source=blocks[0].source, level=max(x.level for x in blocks),
        metadata=[as_text(x) for x in body if not x.section],
        purpose=[as_text(x) for x in body if "目的" in x.section],
        common_conditions=[as_text(x) for x in body if "基本信息" in x.section
                           and not re.fullmatch(r"\s*\d+[.、]\s*[^：:]+[：:]\s*", x.text)],
        groups=groups, changes=changes, time=comparison, quality=quality, cost=cost,
        reported_results=[as_text(x) for x in results if not re.match(r"\s*试样人[：:]", x.text)],
        follow_up=[as_text(x) for x in body if "后续" in x.section or "计划" in x.section
                   or re.search(r"已取.*(?:研究|改善)", x.text)], pending=missing)
