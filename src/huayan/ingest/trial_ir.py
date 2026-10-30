"""首条操作经验的读取侧 IR 与审阅材料；不写正式知识状态。"""
import html
import json
import os
from pathlib import Path
from typing import Literal

from huayan.contracts._base import BaseModel
from huayan.contracts import Fragment
from huayan.domain import find_phenomenon, find_slot_values
from huayan.ingest.compile import EvidenceRef, Proposal
from huayan.ingest.reader.trials import Citation, TrialRecord, TrialText


class EvidenceReportSource:
    """让现有 admit/recheck 按原块位置取回读取记录，不改写段号或指纹。"""
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.name, self.file_sha256 = data["source_id"], data["file_sha256"]
        self.fragments = {f.span: f for f in [Fragment.model_validate(x) for x in data["fragments"]]}
        self.kind = next(iter(self.fragments.values())).source

    def list_docs(self):
        return [self.name]

    def fetch(self, doc_id, span=None):
        if doc_id != self.name:
            raise KeyError(doc_id)
        return list(self.fragments.values()) if span is None else self.fragments[span]


class IRCondition(BaseModel):
    text: str
    group: Literal["A", "B"] | None
    stage: str | None = None
    structured: dict[str, list[str]] = {}
    evidence: list[Citation]


class ProductAlignment(BaseModel):
    """资料侧的产品身份与使用原文，尚非正式 Product 或适用能力。"""
    product_id: str
    name: str
    facts: list[TrialText]
    source_records: list[str]
    pending: list[str]


def read_product_alignment(path, product):
    path = Path(path)
    alignment = ProductAlignment.model_validate_json(path.read_text(encoding="utf-8"))
    if alignment.product_id != product:
        raise ValueError("产品对齐材料与所选产品不一致")
    sources = [EvidenceReportSource(path.parent / record) for record in alignment.source_records]
    fragments = {f"{f.doc_id}#{f.span}@{f.fingerprint}": f for s in sources for f in s.fetch(s.name)}
    for fact in alignment.facts:
        if not fact.evidence or not any(product in fragments[c.fragment].text for c in fact.evidence):
            raise ValueError("产品事实缺少对应型号的依据")
        for citation in fact.evidence:
            if citation.quote not in fragments[citation.fragment].text:
                raise ValueError(f"产品对齐引文不符：{citation.span}")
    return alignment


class OperationIR(BaseModel):
    id: str
    source_id: str
    file_sha256: str
    level: int
    nature: Literal["observation"] = "observation"
    prepared_by: Literal["rule"] = "rule"
    product_raw: str
    group: Literal["A", "B"]
    observation: str
    conditions: list[IRCondition]
    evidence: list[Citation]
    pending: list[str]
    proposal: Proposal
    product_alignment: ProductAlignment | None = None


def prepare_operation(record: TrialRecord, seeds, group, product, index=0):
    own = next(g for g in record.groups if g.group == group)
    operation = own.operations[index]
    conditions = [IRCondition(text=t.text, group=None, evidence=t.evidence) for t in record.common_conditions]
    conditions += [IRCondition(text=f'{x.name} {x.value}{x.unit or "（单位未记载）"}', group=group,
                               stage="配方", evidence=x.evidence) for x in own.formula]
    conditions += [IRCondition(text=x.text, group=group, stage="配方说明", evidence=x.evidence)
                   for x in own.formula_notes]
    conditions += [IRCondition(text=c.quote, group=group, stage="工艺曲线", evidence=[c])
                   for c in own.curve_evidence]
    # 操作原句内含加料顺序、泵速和时间，整体保留，不推断复用范围。
    conditions.append(IRCondition(text=operation.text, group=group, stage="现场操作", evidence=operation.evidence))
    for condition in conditions:
        text = condition.text.strip().strip("，。；")
        matches = find_slot_values(text, seeds.slots)
        # 只有整项文字就是已知取值/说法才算完整结构化，含其他限制的原句整体留待判断。
        condition.structured = {slot: [value] for slot, (value, phrase) in matches.items() if text == phrase}
    limits = "\n".join(dict.fromkeys(e.quote for c in conditions if not c.structured for e in c.evidence))
    pending = list(record.pending) + [note.text for note in record.review_notes]
    pending.append("专业确认人与用途授予待安排；单次观察的复用范围待研发判断。")
    if product not in {p.id for p in seeds.products}:
        pending.append(f"产品原词 {product} 尚未对齐现有产品词表。")
    phenomenon = find_phenomenon(operation.text, seeds.phenomena)
    if phenomenon is None:
        pending.append("观察涉及的现象尚未对齐词表。")
    evidence = list({c.fragment + "\n" + c.quote: c for c in
                     [*operation.evidence, *(e for condition in conditions for e in condition.evidence)]}.values())
    proposal = Proposal(title=f"{product} {group}组现场操作观察", text=operation.text,
        product=product, phenomenon=phenomenon[0] if phenomenon else "", form=None,
        conditions=[c.text for c in conditions], limits=limits,
        evidence=[EvidenceRef(doc_id=record.source_id, span=c.span, quote=c.quote) for c in evidence])
    return OperationIR(id=f"{record.source_id}:{group}:operation-{index + 1}", source_id=record.source_id,
        file_sha256=record.file_sha256, level=record.level, product_raw=product, group=group,
        observation=operation.text, conditions=conditions, evidence=evidence, pending=pending, proposal=proposal)


def write_operation_review(ir, output, evidence_review):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "operation-ir.json").write_text(ir.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (output / "proposals.json").write_text(json.dumps({"items": [ir.proposal.model_dump(mode="json")]},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    esc = html.escape
    def citations(items):
        return "<br>".join(f'<a href="{esc(evidence_review)}#{esc(c.span)}">'
            f'{esc(c.span)} · 第{esc(str(c.pages))}页</a><pre>{esc(c.quote)}</pre>' for c in items)
    rows = "".join(f'<tr><td>{c.group or "共同"} · {esc(c.stage or "共同条件")}</td>'
        f'<td><pre>{esc(c.text)}</pre></td><td>{esc(str(c.structured)) if c.structured else "保留原文待判断"}</td>'
        f'<td>{citations(c.evidence)}</td></tr>' for c in ir.conditions)
    pending = "".join(f"<li>{esc(note)}</li>" for note in ir.pending)
    product = "<p>产品身份依据待补。</p>"
    if ir.product_alignment is not None:
        alignment = ir.product_alignment
        product = f"<h3>{esc(alignment.name)} · {esc(alignment.product_id)}</h3>"
        for fact in alignment.facts:
            refs = "；".join(f'{esc(c.fragment)} · 第{esc(str(c.pages))}页' for c in fact.evidence)
            quotes = "\n".join(c.quote for c in fact.evidence)
            product += f"<p>{esc(fact.text)}</p><pre>{esc(quotes)}</pre><small>{refs}</small>"
        for index, record in enumerate(alignment.source_records, 1):
            link = Path(os.path.relpath(Path(record).parent / "review.html", output)).as_posix()
            product += f'<p><a href="{esc(link)}">产品来源{index}：原文、原生首页与 PDF</a></p>'
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>操作经验 IR 审阅</title>
<style>body{{font:16px/1.6 'Microsoft YaHei',sans-serif;margin:32px;color:#183044}}
table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ccd6df;padding:10px;text-align:left}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.notice{{background:#fff3d4;padding:16px}}</style>
<h1>操作经验 IR · {esc(ir.id)}</h1><p class="notice">L{ir.level} 内部资料；规则整理的单次观察草稿，
未专业确认，未导入契，未授予能力。产品原词与未结构化限制交人判断；配方保持原密级。</p>
<h2>观察及拟用方式</h2><pre>{esc(ir.observation)}</pre><p>拟作为同类现场操作的审阅材料；
复用范围待研发确定，当前不提议 applicable 或 ask。</p>{citations(ir.evidence[:1])}
<h2>产品身份与说明书原文（目录登记待归属）</h2>{product}
<h2>完整条件与原文</h2><table><tr><th>组别／阶段</th><th>条件</th><th>对齐状态</th><th>出处</th></tr>{rows}</table>
<h2>保留到 limits 的原文</h2><pre>{esc(ir.proposal.limits)}</pre><h2>待处理</h2><ul>{pending}</ul>
<p><a href="operation-ir.json">IR</a> · <a href="proposals.json">现有 Proposal 格式</a> ·
<a href="{esc(evidence_review)}">原页对照</a></p></html>'''
    (output / "review.html").write_text(page, encoding="utf-8")
