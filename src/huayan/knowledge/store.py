"""分级知识库。结构化产品只供业务内部使用，助手通过知识接口访问。"""
from __future__ import annotations

import re
from datetime import datetime

from huayan.clock import get_clock
from huayan.contracts import (KIND_LEVEL, Actor, AuditRecord, BlockedHint, KnowledgeHit,
                              KnowledgeUnit, KUKind, Product, Seeds)
from huayan.events import EventLog
from .permission import PermissionDenied, can_read, level_of
from .records import AuditLog

_TITLES = {"sheet": "产品说明", "usage": "用法用量", "mechanism": "机理", "formula": "配方"}


def _grams(text: str) -> set[str]:
    parts = re.findall(r"[\w]+", text.casefold())
    return {p[i:i + 2] for p in parts for i in range(max(1, len(p) - 1))}


def _intent(query: str) -> str:
    return "mechanism_request" if any(w in query.casefold() for w in
        ("配方", "机理", "原理", "为什么", "成分", "染座", "ph")) else "product_question"


class KnowledgeBase:
    def __init__(self, events: EventLog, audit: AuditLog):
        self.events, self.audit = events, audit
        self._units: dict[str, KnowledgeUnit] = {}
        self._products: dict[str, Product] = {}
        self._frozen: set[str] = set()

    @classmethod
    def from_seeds(cls, seeds: Seeds, events: EventLog, audit: AuditLog) -> KnowledgeBase:
        kb = cls(events, audit)
        at = get_clock().now()
        for product in seeds.products:
            if product.status == "released":
                kb._put_product(product, at, "seed")
        for case in seeds.cases:
            kb.add(KnowledgeUnit(id=f"ku:case:{case.id}", level=2, kind="case",
                title=f"历史案例 {case.id} · {next(p.label for p in seeds.phenomena if p.id == case.phenomenon)}",
                text=f"{case.scene_text}\n{case.pm_translation}",
                product_id=case.product_id, phenomenon_ids=[case.phenomenon], owner=case.owner,
                created_at=at))
        for tr in seeds.translations:
            kb.add(KnowledgeUnit(id=f"ku:translation:{tr.id}", level=tr.level, kind="translation",
                title=tr.scene_phrase, text=f"{tr.scene_phrase} → {tr.chem_term}",
                phenomenon_ids=tr.phenomenon_ids, owner=tr.owner, created_at=at))
        return kb

    def _put_product(self, product, at, source):
        self._products[product.id] = product.model_copy(deep=True)
        units = [KnowledgeUnit(id=f"ku:{kind}:{product.id}", level=KIND_LEVEL[kind], kind=kind,
            title=f"{product.name} · {label}", text=getattr(product, kind), product_id=product.id,
            phenomenon_ids=product.solves, owner=product.owner, decryptable=kind == "mechanism",
            source=source, created_at=at) for kind, label in _TITLES.items()]
        for unit in units:
            self.add(unit)
        return units

    def products(self) -> list[Product]:
        return [p.model_copy(deep=True) for p in self._products.values()]

    def product(self, product_id: str) -> Product:
        if product_id not in self._products:
            raise ValueError(f"产品 {product_id} 不存在")
        return self._products[product_id].model_copy(deep=True)

    def add_product(self, product: Product, at: datetime) -> list[KnowledgeUnit]:
        return self._put_product(product.model_copy(update={"status": "released"}), at, "released")

    def update_applicable(self, product_id: str, slot: str, values: list[str], by: str) -> None:
        self._products[product_id].applicable[slot] = list(values)
        self.events.append("sheet_updated", by, {"product_id": product_id, "slot": slot, "values": values})

    def add(self, ku: KnowledgeUnit) -> None:
        self._units[ku.id] = ku.model_copy(deep=True)

    def _readable(self, actor, ku):
        return can_read(actor, ku) and (not self.is_frozen(actor.id) or ku.level == 1)

    def list(self, actor: Actor, *, kinds: list[KUKind] | None = None,
             phenomenon: str | None = None) -> list[KnowledgeUnit]:
        return [ku.model_copy(deep=True) for ku in self._units.values()
                if self._readable(actor, ku) and (kinds is None or ku.kind in kinds)
                and (phenomenon is None or not ku.phenomenon_ids or phenomenon in ku.phenomenon_ids)]

    def _deny(self, actor, object_ids, reason, session_id=None):
        self.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="deny",
            object_ids=object_ids, session_id=session_id, reason=reason))
        for object_id in object_ids:
            self.events.append("access_denied", actor.id, {"object_id": object_id, "reason": reason},
                               session_id=session_id)

    def get(self, ku_id: str, actor: Actor) -> KnowledgeUnit:
        if ku_id not in self._units:
            raise ValueError(f"知识 {ku_id} 不存在")
        ku = self._units[ku_id]
        if not self._readable(actor, ku):
            self._deny(actor, [ku_id], "无权读取该层级知识")
            raise PermissionDenied("无权读取该层级知识")
        return ku.model_copy(deep=True)

    def _rank(self, query, phenomenon):
        grams = _grams(query)
        if not grams:
            return []
        hits = []
        for ku in self._units.values():
            if phenomenon and ku.phenomenon_ids and phenomenon not in ku.phenomenon_ids:
                continue
            score = len(grams & _grams(ku.title + " " + ku.text)) / len(grams)
            if score > 0:
                score += 0.25 if phenomenon and phenomenon in ku.phenomenon_ids else 0
                hits.append(KnowledgeHit(ku=ku.model_copy(deep=True), score=score))
        return sorted(hits, key=lambda hit: (-hit.score, hit.ku.id))

    def search(self, query: str, actor: Actor, *, phenomenon: str | None = None, k: int = 5,
               session_id: str | None = None) -> list[KnowledgeHit]:
        ranked = self._rank(query, phenomenon)
        visible = [h for h in ranked if self._readable(actor, h.ku)]
        blocked = [h for h in ranked if not self._readable(actor, h.ku)]
        intent = _intent(query)
        if self.is_frozen(actor.id) and (intent == "mechanism_request" or (blocked and not visible)):
            self._deny(actor, [h.ku.id for h in blocked] or [actor.id], "高层级访问已冻结", session_id)
            visible = []
        result = visible[:max(0, k)]
        self.events.append("retrieve", actor.id, {"query": query, "intent": intent,
            "actor_level": level_of(actor), "hit_ku_ids": [h.ku.id for h in result],
            "n_blocked": len(blocked),
            "blocked_product_ids": [h.ku.product_id for h in blocked if h.ku.product_id]},
            session_id=session_id)
        return result

    def search_blocked(self, query: str, actor: Actor, *, phenomenon: str | None = None,
                       k: int = 3) -> list[BlockedHint]:
        return [BlockedHint(owner=h.ku.owner, level=h.ku.level, kind=h.ku.kind)
                for h in self._rank(query, phenomenon) if not self._readable(actor, h.ku)][:max(0, k)]

    def is_frozen(self, actor_id: str) -> bool:
        return actor_id in self._frozen

    def freeze(self, actor_id: str, by: str, at: datetime) -> None:
        self._frozen.add(actor_id)
        self.events.append("access_frozen", by, {"actor_id": actor_id}, ts=at)
        self.audit.append(AuditRecord(ts=at, actor=by, action="freeze", object_ids=[actor_id]))
