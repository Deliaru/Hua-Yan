"""分级知识库。结构化产品只供业务内部使用，助手通过知识接口访问。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime

from huayan.clock import get_clock
from huayan.contracts import (KIND_LEVEL, Actor, AuditRecord, BlockedHint, KnowledgeHit,
                              KnowledgeUnit, KUKind, Product, Seeds, Capability, Situation, DecryptGrant, ExploreResult)
from huayan.events import EventLog
from .permission import PermissionDenied, can_read, colleague_l3, holder, level_of
from .records import AuditLog

_TITLES = {"sheet": "产品说明", "usage": "用法用量", "mechanism": "机理", "formula": "配方"}


def _grams(text: str) -> set[str]:
    parts = re.findall(r"[\w]+", text.casefold())
    return {p[i:i + 2] for p in parts for i in range(max(1, len(p) - 1))}


def migrate_seeds(seeds, at):
    units, caps = [], []
    for product in seeds.products:
        if product.status != "released":
            continue
        for situation in product.situations:
            caps.append(Capability(id=situation.capability_id, form="applicable", audience=0,
                payload={"product_id": product.id, "phenomenon": situation.phenomenon,
                         "conditions": situation.conditions}, based_on=[f"ku:sheet:{product.id}"],
                granted_by=product.owner, approved_by="seed", status="active", at=at))
    for phen in seeds.phenomena:
        unit = KnowledgeUnit(id=f"ku:claim:phen:{phen.id}", kind="claim", level=3,
            title=phen.label, text=phen.causes, phenomenon_ids=[phen.id], owner="seed",
            confirmed_by="seed", created_at=at)
        units.append(unit)
        for slot in phen.required_slots:
            caps.append(Capability(id=f"cap:ask:{phen.id}:{slot}", form="ask", audience=0,
                payload={"phenomenon": phen.id, "slot": slot, "required": True},
                based_on=[unit.id], granted_by="seed", status="active", at=at))
        for slot, prior in phen.slot_priors.items():
            caps.append(Capability(id=f"cap:prior:{phen.id}:{slot}", form="ask", audience=0,
                payload={"phenomenon": phen.id, "slot": slot, "prior": prior},
                based_on=[unit.id], granted_by="seed", status="active", at=at))
    return units, caps


class KnowledgeBase:
    def __init__(self, events: EventLog, audit: AuditLog):
        self.events, self.audit = events, audit
        self._units: dict[str, KnowledgeUnit] = {}
        self._products: dict[str, Product] = {}
        self._frozen: set[str] = set()
        self._caps: dict[str, Capability] = {}
        self.state_path = None
        self._version = 0
        self._claim_seq = self._cap_seq = 0
        self._doc_levels = {}
        self._pending_evidence = {}
        self.sources = []
        self._seed_units = {}

    @classmethod
    def from_seeds(cls, seeds: Seeds, events: EventLog, audit: AuditLog, *, state_path=None) -> KnowledgeBase:
        kb = cls(events, audit)
        kb.seeds = seeds
        at = get_clock().now()
        for product in seeds.products:
            if product.status == "released":
                kb._put_product(product, at, "seed")
        for case in seeds.cases:
            kb.add(KnowledgeUnit(id=f"ku:case:{case.id}", level=2, kind="case",
                title=f"历史案例 {case.id} · {next(p.label for p in seeds.phenomena if p.id == case.phenomenon)}",
                text=f"{case.scene_text}\n{case.pm_translation}",
                product_id=case.product_id, phenomenon_ids=[case.phenomenon], owner=case.owner, confirmed_by=case.owner,
                created_at=at))
        for tr in seeds.translations:
            kb.add(KnowledgeUnit(id=f"ku:translation:{tr.id}", level=tr.level, kind="translation",
                title=tr.scene_phrase, text=f"{tr.scene_phrase} → {tr.chem_term}",
                phenomenon_ids=tr.phenomenon_ids, owner=tr.owner, confirmed_by=tr.owner, created_at=at))
        units, caps = migrate_seeds(seeds, at)
        for unit in units:
            kb.add(unit)
        kb._caps = {cap.id: cap for cap in caps}
        kb._seed_units = {key: unit.model_copy(deep=True) for key, unit in kb._units.items()}
        for e in events.query(["access_frozen", "access_unfrozen"]):     # 续跑时事件已读回，按先后恢复
            (kb._frozen.add if e.kind == "access_frozen" else kb._frozen.discard)(e.payload["actor_id"])
        kb.state_path = Path(state_path) if state_path else None
        if kb.state_path and kb.state_path.exists():
            data = json.loads(kb.state_path.read_text(encoding="utf-8"))
            kb._units.update({u["id"]: KnowledgeUnit.model_validate(u) for u in data["units"]})
            kb._products.update({p["id"]: Product.model_validate(p) for p in data["products"]})
            kb._caps.update({c["id"]: Capability.model_validate(c) for c in data["capabilities"]})
            kb._version, kb._doc_levels = data["version"], data["doc_levels"]
            kb._claim_seq, kb._cap_seq = data["claim_seq"], data["cap_seq"]
            kb._pending_evidence = data.get("pending_evidence", {})  # 兼容此前保存的状态文件。
        kb._save()
        return kb

    def _put_product(self, product, at, source):
        self._products[product.id] = product.model_copy(deep=True)
        units = [KnowledgeUnit(id=f"ku:{kind}:{product.id}", level=KIND_LEVEL[kind], kind=kind,
            title=f"{product.name} · {label}", text=getattr(product, kind), product_id=product.id,
            phenomenon_ids=product.solves, owner=product.owner, decryptable=kind == "mechanism",
            source=source, confirmed_by=product.owner, created_at=at) for kind, label in _TITLES.items()]
        for unit in units:
            self.add(unit)
        return units

    def _visible_caps(self, actor):
        level = level_of(actor)
        return [c for c in self._caps.values() if c.status == "active" and c.audience in range(level + 1)]

    def ask_capabilities(self, actor, phenomenon, slots):
        """本层生效、属于该现象且槽位在 slots 中的追问能力（供记「被使用」）。"""
        return [c.model_copy(deep=True) for c in self._visible_caps(actor) if c.form == "ask"
                and c.payload["phenomenon"] == phenomenon and c.payload["slot"] in slots]

    def view(self, actor) -> Seeds:
        level = level_of(actor)
        caps = self._visible_caps(actor)
        phenomena = []
        for phen in self.seeds.phenomena:
            asks = [c.payload for c in caps if c.form == "ask" and c.payload["phenomenon"] == phen.id]
            required = list(dict.fromkeys(a["slot"] for a in asks if a.get("required")))
            priors = {a["slot"]: a["prior"] for a in asks if "prior" in a}
            phenomena.append(phen.model_copy(update={"required_slots": required, "slot_priors": priors,
                                                     "causes": phen.causes if level == 3 else ""}))
        products = []
        for product in self._products.values():
            situations = [Situation(phenomenon=c.payload["phenomenon"], conditions=c.payload["conditions"],
                capability_id=c.id) for c in caps if c.form == "applicable" and c.payload["product_id"] == product.id]
            products.append(product.model_copy(update={"situations": situations, "applicable": {},
                "solves": list(dict.fromkeys(s.phenomenon for s in situations))}, deep=True))
        return self.seeds.model_copy(update={"phenomena": phenomena, "products": products}, deep=True)

    def products(self) -> list[Product]:
        return self.view(Actor(id="system:knowledge", role="rd", name="知识库")).products

    def product(self, product_id: str) -> Product:
        if product_id not in self._products:
            raise ValueError(f"产品 {product_id} 不存在")
        return next(p for p in self.products() if p.id == product_id)

    def add_product(self, product: Product, at: datetime) -> list[KnowledgeUnit]:
        return self._put_product(product.model_copy(update={"status": "released"}), at, "released")

    def grant(self, cap: Capability) -> Capability:
        units = [self._units[ku_id] for ku_id in cap.based_on]
        if not units or any(u.confirmed_by != cap.granted_by for u in units):
            raise PermissionDenied("授予人必须是全部依据结论的确认人")
        if cap.audience in (0, 1, 2) and any(u.kind == "formula" for u in units):
            raise PermissionDenied("配方不能作为下层能力的依据")
        cap = cap.model_copy(deep=True)
        if any(u.status != "active" for u in units):
            cap.status = "proposed"
        if cap.form == "applicable" and cap.approved_by is None:
            cap.status = "proposed"
        self._caps[cap.id] = cap
        if cap.id.removeprefix("cap:").isdigit():
            self._cap_seq = max(self._cap_seq, int(cap.id.removeprefix("cap:")))
        self.events.append("capability_granted", cap.granted_by, cap.model_dump(mode="json"))
        self._save()
        return cap.model_copy(deep=True)

    def approve(self, cap_id, by):
        actor = next(a for a in self.seeds.actors if a.id == by)
        if actor.role != "pm" or by == "pm:agent":
            raise PermissionDenied("适用能力必须由真人产品经理批准")
        cap = self._caps[cap_id]
        if cap.form != "applicable" or cap.status != "proposed":
            raise ValueError("只能批准待批准的适用能力")
        pending = [u for u in cap.based_on if self._units[u].status != "active"]
        if any(self._units[u].confirmed_by != by for u in pending):
            raise ValueError("依据结论尚未确认")
        if pending:                      # 公开产品页的结论由批准它的产品经理核对，批准即确认
            self.confirm(pending, by)
        cap.approved_by, cap.status = by, "active"
        self._save()
        return cap.model_copy(deep=True)

    def revoke(self, cap_id, by):
        cap = self._caps[cap_id]
        owner = self._products[cap.payload["product_id"]].owner if cap.form == "applicable" else None
        if by not in (cap.granted_by, owner):
            raise PermissionDenied("只有授予人或产品归属研发可以撤销能力")
        cap.status = "revoked"
        self.events.append("capability_revoked", by, {"capability_id": cap_id})
        self._save()

    def capabilities(self):
        return [c.model_copy(deep=True) for c in self._caps.values()]

    def limits(self):
        """V9.5：生效的、带限制原文的适用能力 {能力 id: 限制原文}。"""
        return {c.id: c.payload["limits"] for c in self._caps.values()
                if c.form == "applicable" and c.status == "active" and c.payload.get("limits")}

    def decrypt_grants(self):
        return [DecryptGrant(id=c.id, customer_id=c.audience, product_id=c.payload["product_id"],
            session_id=c.payload["session_id"], text=c.payload["text"], approved_by=c.granted_by, at=c.at)
            for c in self._caps.values() if c.form == "decrypt" and c.status == "active"]

    def next_claim_id(self):
        self._claim_seq += 1
        return f"ku:claim:{self._claim_seq}"

    def _fragments(self, unit):
        fragments = []
        for evidence in unit.evidence:
            location = evidence.rsplit("@", 1)[0]
            doc_id, span = location.rsplit("#", 1)
            source = next(s for s in self.sources if doc_id in s.list_docs())
            fragments.append(source.fetch(doc_id, span))
        return fragments

    def confirm(self, ku_ids, by):
        units = [self._units[ku_id] for ku_id in ku_ids]
        for unit in units:
            if unit.confirmed_by not in (None, by):
                raise PermissionDenied("只能确认本人负责的结论")
            fragments = self._fragments(unit)
            if fragments and all(f.source == "external" for f in fragments):
                raise ValueError("只依据外部片段的结论不能确认")
        for unit in units:
            if unit.evidence:
                unit.evidence = [f"{f.doc_id}#{f.span}@{f.fingerprint}" for f in self._fragments(unit)]
            unit.status, unit.confirmed_by, unit.owner = "active", by, by
            self.events.append("claim_confirmed", by, {"ku_id": unit.id})
        for cap in self._caps.values():
            if cap.status not in {"proposed", "suspended"} or not set(cap.based_on) & set(ku_ids):
                continue
            if all(self._units[u].status == "active" for u in cap.based_on):
                cap.status = "proposed" if cap.form == "applicable" and cap.approved_by is None else "active"
        self._save()

    def _suspend(self, ku_id):
        for cap in self._caps.values():
            if ku_id in cap.based_on and cap.status in {"active", "proposed"}:
                cap.status = "suspended"
                self.events.append("capability_suspended", cap.granted_by,
                                   {"capability_id": cap.id, "ku_id": ku_id})
        self._save()

    def withdraw(self, ku_id, by):
        unit = self._units[ku_id]
        if unit.confirmed_by != by:
            raise PermissionDenied("只有确认人可以撤回结论")
        unit.status = "withdrawn"
        self.events.append("claim_withdrawn", by, {"ku_id": ku_id})
        self._suspend(ku_id)

    def evidence_changed(self, ku_id):
        unit = self._units[ku_id]
        unit.status = "candidate"
        self.events.append("evidence_changed", "system:knowledge", {"ku_id": ku_id,
            "signer": unit.confirmed_by, "product_id": unit.product_id, "evidence": unit.evidence})
        self._suspend(ku_id)

    def attach_evidence(self, cap_id, ku: KnowledgeUnit):
        """补充依据先候选化；保留贡献人与待挂接目标，由 V10.7 审阅后挂接。"""
        cap = self._caps[cap_id]
        self._pending_evidence[ku.id] = {"capability_id": cap_id, "contributor": ku.owner}
        self.add(ku.model_copy(update={"owner": cap.granted_by, "confirmed_by": cap.granted_by, "status": "candidate"}))

    def next_cap_id(self):
        self._cap_seq += 1
        return f"cap:{self._cap_seq}"

    def add(self, ku: KnowledgeUnit) -> None:
        unit = ku.model_copy(deep=True)
        if unit.status == "active" and unit.confirmed_by is None:
            unit.confirmed_by = unit.owner
        self._units[ku.id] = unit
        if ku.id.removeprefix("ku:claim:").isdigit():
            self._claim_seq = max(self._claim_seq, int(ku.id.removeprefix("ku:claim:")))
        self._save()

    def _save(self):
        if self.state_path is None:
            return
        self._version += 1
        data = {"version": self._version, "units": [u.model_dump(mode="json") for u in self._units.values()
                    if u.kind == "claim" or u != self._seed_units.get(u.id)],
                "products": [p.model_dump(mode="json") for p in self._products.values()
                    if self._units[f"ku:sheet:{p.id}"].source != "seed"],
                "capabilities": [c.model_dump(mode="json") for c in self._caps.values()],
                "doc_levels": self._doc_levels, "claim_seq": self._claim_seq, "cap_seq": self._cap_seq,
                "pending_evidence": self._pending_evidence}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.state_path)

    def _shared(self, actor):
        return frozenset(c.payload["ku_id"] for c in self._caps.values()
                         if c.form == "share" and c.status == "active" and c.audience == actor.id)

    def _readable(self, actor, ku):
        return ku.status == "active" and can_read(actor, ku, self._shared(actor)) and (not self.is_frozen(actor.id) or ku.level <= 1)

    def list(self, actor: Actor, *, kinds: list[KUKind] | None = None,
             phenomenon: str | None = None) -> list[KnowledgeUnit]:
        return [ku.model_copy(deep=True) for ku in self._units.values()
                if self._readable(actor, ku) and (kinds is None or ku.kind in kinds)
                and (phenomenon is None or not ku.phenomenon_ids or phenomenon in ku.phenomenon_ids)]

    def _l3_translation_terms(self) -> list[str]:
        """内部泄密检查的词表；不作为用户检索接口，不受发送者阅读权限或冻结状态影响。"""
        return [ku.text.split(" → ", 1)[1] for ku in self._units.values()
                if ku.kind == "translation" and ku.level == 3]

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
            if ku.status != "active":
                continue
            if phenomenon and ku.phenomenon_ids and phenomenon not in ku.phenomenon_ids:
                continue
            # 产品编号也入索引：按编号问（「TF-217A 用量」）要命中这支产品，而不是名字相近的别的产品
            score = len(grams & _grams(f"{ku.product_id or ''} {ku.title} {ku.text}")) / len(grams)
            if score > 0:
                score += 0.25 if phenomenon and phenomenon in ku.phenomenon_ids else 0
                hits.append(KnowledgeHit(ku=ku.model_copy(deep=True), score=score))
        return sorted(hits, key=lambda hit: (-hit.score, hit.ku.id))

    def search(self, query: str, actor: Actor, *, phenomenon: str | None = None, k: int = 5,
               session_id: str | None = None, asked_by: str | None = None, intent: str = "",
               products: list[str] = ()) -> list[KnowledgeHit]:
        ranked = self._rank(query, phenomenon)
        visible = [h for h in ranked if self._readable(actor, h.ku)]
        blocked = [h for h in ranked if self._stub(actor, h.ku)]
        # 拼凑机密只看越层命中；同层研发的存根可以申请查看，不算拼凑信号
        above = [h for h in blocked if h.ku.level > level_of(actor)]
        result = visible[:max(0, k)]
        # v8：事件记在真正提问的人或助手名下（asked_by），委托人记在 principal；权限仍按委托人
        self.events.append("retrieve", asked_by or actor.id, {"query": query, "intent": intent, "principal": actor.id,
            "actor_level": level_of(actor), "hit_ku_ids": [h.ku.id for h in result],
            "n_blocked": len(above), "blocked_product_ids": [h.ku.product_id for h in above if h.ku.product_id],
            "target_products": list(products), "capability_ids": [], "denied": False},
            session_id=session_id)
        return result

    def search_blocked(self, query: str, actor: Actor, *, phenomenon: str | None = None,
                       k: int = 3) -> list[BlockedHint]:
        # 只有同层研发的存根带 ku_id（可申请查看）；跨层存根不带；冻结后不给上层存根（⑰′）
        if self.is_frozen(actor.id):
            return []
        return [BlockedHint(owner=holder(h.ku), level=h.ku.level, kind=h.ku.kind,
                            ku_id=h.ku.id if colleague_l3(actor, h.ku) else None)
                for h in self._rank(query, phenomenon) if self._stub(actor, h.ku)][:max(0, k)]

    def _stub(self, actor: Actor, ku: KnowledgeUnit) -> bool:
        """v8：读不到的才出存根；试样记录是原始数据、不是能向下讲的结论，不算被拦命中、也不出存根。"""
        return ku.kind != "trial" and not self._readable(actor, ku)

    def _hits(self, text, phenomenon, k):
        hits = [h.ku for h in self._rank(text, phenomenon)][:k]
        docs = {f.doc_id for s in self.sources for f in s.search(text, k)}
        return hits + [u for u in self._units.values() if u.status == "active" and u.id not in {h.id for h in hits}
                       and any(e.rsplit("@", 1)[0].rsplit("#", 1)[0] in docs for e in u.evidence)]

    def explore(self, query: str, actor: Actor, *, phenomenon: str | None = None, k: int = 5,
                session_id: str | None = None, asked_by: str | None = None, intent: str = "",
                products: list[str] = ()) -> ExploreResult:
        """分层召回（只读）：本层可读的结论给原文，授予本层的能力给能力，命中却没有能力的只记「不可答」；
        内部各层给存根，客户层什么都不给，与没找到相同。"""
        level = level_of(actor)
        # 1. 转化对照把查询往上扩展；扩展词只在内部用
        terms = [h.ku.text for h in self._rank(query, phenomenon) if h.ku.kind == "translation"][:k]
        expanded = " ".join([query, *terms])
        # 2. 结论直接命中，加上片段命中后按依据的文档接回结论。本层可读的只用原查询找：
        #    经上层转化对照才连上的内容不给下层，客户层命中上层时与没找到相同
        direct, reached = self._hits(query, phenomenon, k), self._hits(expanded, phenomenon, k)
        # 3. 本层可读 → 原文；授予本层且依据命中的能力 → 能力；越层命中且没有能力 → 不可答
        units = [u.model_copy(deep=True) for u in direct if self._readable(actor, u)]
        blocked = [u for u in reached if self._stub(actor, u)]
        above = [u for u in blocked if u.level > level]
        hit_ids = {u.id for u in direct} | {u.id for u in above}
        caps = [c for c in self._visible_caps(actor) if hit_ids & set(c.based_on)]
        # ⑰′ 冻结：不给授予本层的上层结论（statement），也不给上层存根（谁知道）；挡下了什么就记拒绝
        frozen = self.is_frozen(actor.id)
        held = [c.id for c in caps if c.form == "statement"] + [u.id for u in above] if frozen else []
        if frozen:
            caps = [c for c in caps if c.form != "statement"]
            blocked = [u for u in blocked if u.level <= level]
        if held:
            self._deny(actor, held, "访问已冻结", session_id)
        covered = {ku_id for c in caps for ku_id in c.based_on}
        # 转化对照走升级转译，配方永不对下；其余越层命中没有能力的才算「不可答」
        unanswerable = [u.id for u in above if u.id not in covered and u.kind not in ("formula", "translation")]
        self.events.append("retrieve", asked_by or actor.id, {"query": query, "intent": intent,
            "principal": actor.id, "actor_level": level, "hit_ku_ids": [u.id for u in units], "n_blocked": len(above),
            "blocked_product_ids": [u.product_id for u in above if u.product_id],
            "unanswerable_ku_ids": unanswerable, "n_unanswerable": len(unanswerable), "target_products": list(products),
            "capability_ids": [c.id for c in caps if c.form == "statement"], "denied": bool(held)}, session_id=session_id)
        if level == 0:
            return ExploreResult(units=units, capabilities=[c.model_copy(deep=True) for c in caps], hints=[])
        # 4. 提示只从本层视图算
        view = self.view(actor)
        hints = [f"相关条件：{s.label}" for s in view.slots if any(v in query for v in s.values)]
        hints += [f"相关现象：{p.label}" for p in view.phenomena if p.label in query]
        hints += [f"相关产品：{p.id}" for p in view.products if p.id in query or p.name in query]
        stubs = [BlockedHint(owner=holder(u), level=u.level, kind=u.kind, ku_id=u.id if colleague_l3(actor, u) else None)
                 for u in blocked]
        grams = _grams(expanded)
        candidates = [u.model_copy(deep=True) for u in self._units.values() if actor.role == "rd"
                      and u.status == "candidate" and u.confirmed_by == actor.id and grams & _grams(u.title + u.text)]
        return ExploreResult(units=units, capabilities=[c.model_copy(deep=True) for c in caps], hints=hints,
                             stubs=stubs, candidates=candidates)

    def is_frozen(self, actor_id: str) -> bool:
        return actor_id in self._frozen

    def freeze(self, actor_id: str, by: str, at: datetime) -> None:
        self._frozen.add(actor_id)
        self.events.append("access_frozen", by, {"actor_id": actor_id}, ts=at)
        self.audit.append(AuditRecord(ts=at, actor=by, action="freeze", object_ids=[actor_id]))

    def unfreeze(self, actor_id: str, by: str, at: datetime) -> None:
        self._frozen.discard(actor_id)
        self.events.append("access_unfrozen", by, {"actor_id": actor_id}, ts=at)
        self.audit.append(AuditRecord(ts=at, actor=by, action="unfreeze", object_ids=[actor_id]))
