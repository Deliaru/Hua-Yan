"""按来源编号读取原文；权限集中在此入口，底层适配器仍只负责取回。"""
from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit
from huayan.knowledge.permission import PermissionDenied, can_read


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
