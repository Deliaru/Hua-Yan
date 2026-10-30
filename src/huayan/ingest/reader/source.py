"""按来源编号读取原文；权限集中在此入口，底层适配器仍只负责取回。"""
from pathlib import Path

from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit
from huayan.ingest.trial_ir import EvidenceReportSource
from huayan.knowledge.permission import PermissionDenied, can_read

from .trials import TrialRecord


def read_source(kb, doc_id, actor, owners, span=None):
    source = next((s for s in kb.sources if doc_id in s.list_docs()), None)
    if source is None:
        raise ValueError(f"来源不存在：{doc_id}")
    owner = owners.get(doc_id)
    if source.kind == "internal" and owner is None:
        raise ValueError(f"内部来源尚未指定归属人：{doc_id}")
    fragments = source.fetch(doc_id)
    level = max([3 if source.kind == "internal" else 0, *(f.level for f in fragments)])
    # 只作读取权限描述，不加入正式知识状态；share 仅认整份来源对应的 report 编号。
    unit = KnowledgeUnit(id=f"ku:report:{doc_id}", kind="report", level=level, title=doc_id,
                         text="", owner=owner or "public", created_at=get_clock().now())
    if not can_read(actor, unit, kb._shared(actor)) or (level > 1 and kb.is_frozen(actor.id)):
        raise PermissionDenied("无权读取该来源")
    selected = fragments if span is None else [f for f in fragments if f.span == span]
    if not selected:
        raise ValueError(f"来源片段不存在：{doc_id}#{span}")
    return [f.model_copy(update={"level": level}, deep=True) for f in selected]


def read_trial_record(kb, doc_id, actor, owners, path):
    """按同一来源边界回取已整理记录；文件和引用须仍对应当前依据。"""
    fragments = read_source(kb, doc_id, actor, owners)
    if path is None:
        raise ValueError(f"该来源尚未登记试样记录：{doc_id}")
    source = next(s for s in kb.sources if doc_id in s.list_docs())
    if not isinstance(source, EvidenceReportSource):
        raise ValueError("试样记录须关联已登记的报告读取来源")
    record = TrialRecord.model_validate_json(Path(path).read_text(encoding="utf-8"))
    if record.source_id != doc_id or record.file_sha256 != source.file_sha256:
        raise ValueError("试样记录与报告读取来源不一致，请重新整理")
    texts = (record.metadata + record.purpose + record.common_conditions + record.quality + record.cost
             + record.follow_up + record.reported_results + record.review_notes)
    citations = [c for text in texts for c in text.evidence] + record.time.evidence
    citations += [c for change in record.changes for c in change.evidence]
    for group in record.groups:
        citations += [c for item in group.formula + group.formula_notes + group.operations for c in item.evidence]
        citations += group.curve_evidence
    current = {f"{f.doc_id}#{f.span}@{f.fingerprint}": f.text for f in fragments}
    if any(c.fragment not in current or c.quote not in current[c.fragment] for c in citations):
        raise ValueError("试样记录依据已变化或无法取回，请重新整理")
    return record.model_copy(update={"level": max(f.level for f in fragments), "source": fragments[0].source})
