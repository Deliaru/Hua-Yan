"""研发知识沉淀与新品发布。调用者门面负责角色、状态与引用校验。"""
from huayan.contracts import Capability, KnowledgeUnit, LedgerEntry


def contribute_translation(req, item_index, scene_phrase, chem_term, by, kb, ledger, events, at):
    unit = KnowledgeUnit(id=f"ku:translation:{req.id}:{item_index}:{len(ledger.list()) + 1}",
        kind="translation", level=3, title=scene_phrase, text=f"{scene_phrase} → {chem_term}",
        phenomenon_ids=[req.phenomenon], owner=by.id, source="contributed", created_at=at)
    kb.add(unit)
    req.chem_lang[item_index].ku_refs.append(unit.id)
    ledger.add(LedgerEntry(ts=at, owner=by.id, points=ledger.points["contributed"],
                          reason="contributed", ku_id=unit.id, ref=req.id))
    events.append("knowledge_contributed", by.id,
                  {"ku_id": unit.id, "owner": by.id, "requirement_id": req.id}, ts=at)
    return unit


def release_product(req, product, kb, ledger, events, by, at):
    released = product.model_copy(update={"status": "released"}, deep=True)
    kb.add_product(released, at)
    for situation in released.situations:
        kb.grant(Capability(id=situation.capability_id, form="applicable", audience=0,
            payload={"product_id": released.id, "phenomenon": situation.phenomenon,
                     "conditions": situation.conditions}, based_on=[f"ku:sheet:{released.id}"],
            granted_by=released.owner, approved_by=by, status="active", at=at))
    ledger.add(LedgerEntry(ts=at, owner=product.owner, points=ledger.points["product_released"],
                          reason="product_released", ku_id=f"ku:sheet:{product.id}", ref=product.id))
    events.append("product_released", by, {"product_id": product.id, "requirement_id": req.id,
        "phenomenon": req.phenomenon, "situations": [s.model_dump() for s in product.situations]}, ts=at)
    req.status = "released"
    return released
