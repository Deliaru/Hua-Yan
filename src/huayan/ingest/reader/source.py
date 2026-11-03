"""按来源编号读取原文；权限集中在此入口，底层适配器仍只负责取回。"""
from base64 import b64encode
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit
from huayan.ingest.trial_ir import EvidenceReportSource
from huayan.knowledge.permission import PermissionDenied, can_read

from .library import LibrarySource
from .trials import TrialRecord
from .evidence import EvidenceBlock


def read_source(kb, doc_id, actor, owners, span=None):
    source = next((s for s in kb.sources if doc_id in s.list_docs()), None)
    if source is None:
        raise ValueError(f"来源不存在：{doc_id}")
    owner = owners.get(doc_id)
    if source.kind == "internal" and owner is None:
        raise ValueError(f"内部来源尚未指定归属人：{doc_id}")
    fragments = source.fetch(doc_id)
    level = max([3 if source.kind == "internal" else 0, *(f.level for f in fragments)])
    if not _may_read(kb, doc_id, actor, owner, level):
        raise PermissionDenied("无权读取该来源")
    selected = fragments if span is None else [f for f in fragments if f.span == span]
    if not selected:
        raise ValueError(f"来源片段不存在：{doc_id}#{span}")
    return [f.model_copy(update={"level": level}, deep=True) for f in selected]


def _may_read(kb, doc_id, actor, owner, level):
    # 只作读取权限描述，不加入正式知识状态；share 仅认整份来源对应的 report 编号。
    unit = KnowledgeUnit(id=f"ku:report:{doc_id}", kind="report", level=level, title=doc_id,
                         text="", owner=owner or "public", created_at=get_clock().now())
    return can_read(actor, unit, kb._shared(actor)) and not (level > 1 and kb.is_frozen(actor.id))


def readable_sources(kb, actor, owners):
    """V11.13 检索前先划范围：委托人按统一入口能读的整份来源（内部来源没指定归属人的不算）。"""
    return {d for s in kb.sources for d in s.list_docs()
            if s.kind != "internal" or owners.get(d) is not None
            if _may_read(kb, d, actor, owners.get(d), max([3 if s.kind == "internal" else 0, *(f.level for f in s.fetch(d))]))}


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
    for cited_doc in sorted({c.fragment.split("#", 1)[0] for c in citations} - {doc_id}):
        fragments += read_source(kb, cited_doc, actor, owners)
    current = {f"{f.doc_id}#{f.span}@{f.fingerprint}": f.text for f in fragments}
    if any(c.fragment not in current or c.quote not in current[c.fragment] for c in citations):
        raise ValueError("试样记录依据已变化或无法取回，请重新整理")
    return record.model_copy(update={"level": max(f.level for f in fragments),
        "source": "internal" if any(f.source == "internal" for f in fragments) else fragments[0].source})


def read_source_image(kb, doc_id, actor, owners, page, span=None):
    """回取原页或块的已登记区域；没有坐标时如实返回整页。"""
    fragments = read_source(kb, doc_id, actor, owners, span)
    source = next(s for s in kb.sources if doc_id in s.list_docs())
    if isinstance(source, LibrarySource):            # V11.13 资料库：登记时渲染的整页图，没有区域坐标
        images = source.images(doc_id)
        if not 1 <= page <= len(images) or span not in (None, f"p{page}"):
            raise ValueError("该来源没有指定原页")
        return _image(doc_id, span, page, None, Path(images[page - 1]).read_bytes(), fragments[0])
    if not isinstance(source, EvidenceReportSource):
        raise ValueError("该来源尚未登记原页图像")
    report = json.loads(source.path.read_text(encoding="utf-8"))
    if report["source_id"] != doc_id or report["file_sha256"] != source.file_sha256:
        raise ValueError("图像读取记录与当前来源不一致，请重新读取")
    images = report.get("images", [])
    if not 1 <= page <= len(images):
        raise ValueError("该来源没有指定原页")
    bbox = None
    if span is not None:
        data = next((b for b in report.get("blocks", []) if b["span"] == span), None)
        if data is None:
            raise ValueError("该块尚无图像定位")
        block = EvidenceBlock.model_validate(data)
        if (block.source_id != doc_id or block.file_sha256 != source.file_sha256
                or block.fragment().fingerprint != fragments[0].fingerprint):
            raise ValueError("块依据已变化，请重新读取")
        location = next((loc for loc in block.locations if loc.page == page), None)
        if location is None:
            raise ValueError("该块不在指定页面")
        bbox = location.bbox
    path = Path(images[page - 1])
    raw = (path if path.is_absolute() else source.path.parent / path).read_bytes()
    return _image(doc_id, span, page, bbox, raw, fragments[0])


def _image(doc_id, span, page, bbox, raw, fragment):
    with Image.open(BytesIO(raw)) as image:
        mime = Image.MIME[image.format]
        width, height = image.size
        if bbox is not None:
            left, top, right, bottom = bbox
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError("登记区域超出原页或为空，请重新定位")
            with BytesIO() as stream:
                image.crop(bbox).save(stream, format="PNG")
                raw = stream.getvalue()
            width, height, mime = right - left, bottom - top, "image/png"
    return {"doc_id": doc_id, "span": span, "page": page, "bbox": bbox,
            "kind": "region" if bbox is not None else "page", "level": fragment.level,
            "source": fragment.source, "width": width, "height": height,
            "fingerprint": sha256(raw).hexdigest()[:12], "image_url": f"data:{mime};base64,{b64encode(raw).decode('ascii')}"}
