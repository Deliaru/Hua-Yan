"""契约 7.1：转译引擎的规则骨架。每层只用 kb.list 给该身份的知识；每条都带原话（quote_refs）与依据（ku_refs）；不调用大模型。"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from huayan.contracts import (Actor, KnowledgeHit, KnowledgeUnit, LeakHit, PMDraft, RDDraft, ReqItem, Requirement,
                              Session, SheetDraft)

if TYPE_CHECKING:
    from huayan.knowledge import KnowledgeBase

MIN_OVERLAP = 0.5      # 原文的字符二元组有一半出现在文本中即算命中（写死）


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _score(phrase: str, text: str) -> float:
    if phrase in text:
        return 1.0
    grams = _bigrams(phrase)
    return len(grams & _bigrams(text)) / len(grams) if grams else 0.0


def _term(ku: KnowledgeUnit) -> str:
    return ku.text.split(" → ", 1)[1]           # 转化对照知识的 text 为「原文 → 译文」


def _hypothesis_body(value: str) -> str:
    """去掉规则骨架写入的「参考 X 的机理：（模拟机理）」前缀，免得前缀拉低重合度。"""
    return re.sub(r"^参考 \S+ 的机理：(（模拟机理）)?", "", value)


def leak_hits(text: str, sealed: list[str], hypotheses: list[str], kb: KnowledgeBase) -> list[LeakHit]:
    """按非空句编号，只返回句序号与来源类别；同句同类去重，不返回保密原文。"""
    sources = (("sealed", sealed), ("l3_term", kb._l3_translation_terms()),
               ("hypothesis", [_hypothesis_body(value) for value in hypotheses]))
    phrases = [(source, [p.strip() for value in values for p in re.split(r"[。；！？\n]+", value) if p.strip()])
               for source, values in sources]
    sentences = [s.strip() for s in re.split(r"[。；！？\n]+", text) if s.strip()]
    return [LeakHit(index=index, source=source) for index, sentence in enumerate(sentences)
            for source, terms in phrases if any(_score(term, sentence) >= MIN_OVERLAP for term in terms)]


def match_translations(text: str, kb: KnowledgeBase, actor: Actor,
                       phenomenon: str | None = None) -> list[KnowledgeHit]:
    hits = [KnowledgeHit(ku=ku, score=s) for ku in kb.list(actor, kinds=["translation"], phenomenon=phenomenon)
            if (s := _score(ku.title, text)) >= MIN_OVERLAP]
    return sorted(hits, key=lambda h: (-h.score, h.ku.id))


def _translate(sources: list[ReqItem], kb: KnowledgeBase, actor: Actor, phenomenon: str, level: int) -> list[ReqItem]:
    """逐条来源匹配本层转化对照：同一条知识合并为一个条目，继承来源的原话；一条都没命中的来源，
    槽位条件原样保留，其余记为「未转译」（不编造）。"""
    items: dict[str, ReqItem] = {}
    rest = []
    for src in sources:
        hits = [h for h in match_translations(src.text, kb, actor, phenomenon) if h.ku.level == level]
        for h in hits:
            item = items.setdefault(h.ku.id, ReqItem(text=f"『{h.ku.title}』→ {_term(h.ku)}", ku_refs=[h.ku.id]))
            item.quote_refs += [q for q in src.quote_refs if q not in item.quote_refs]
        if not hits:
            rest.append(src if src.slot else ReqItem(text="未转译：" + src.text.removeprefix("未转译："), quote_refs=src.quote_refs))
    return list(items.values()) + rest


def _slot_items(known: dict[str, str], sessions: list[Session]) -> list[ReqItem]:
    """每个已知槽位一条条件条目；槽位中文名由界面按 slot 字段从种子渲染。"""
    return [ReqItem(text=f"条件：{value}", slot=slot,
                    quote_refs=[s.need.slots[slot].turn_id for s in sessions
                                if slot in s.need.slots and s.need.slots[slot].value == value])
            for slot, value in known.items()]


def _residual(item: ReqItem, sessions: list[Session]) -> bool:
    """未命中的发言去掉槽位原话片段后还剩内容（如「交期必须三天内」），就作为未转译条目保留；只回答了槽位的由条件条目承载。"""
    turn = next(t for s in sessions for t in s.turns if t.id == item.quote_refs[0])
    text = turn.text
    for fill in (f for s in sessions for f in s.need.slots.values() if f.turn_id == turn.id):
        text = text.replace(fill.quote, "")
    return len(re.sub(r"[\W_]", "", text)) >= 2


def draft_product_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, pm: Actor, at: datetime) -> PMDraft:
    phenomenon = req.phenomenon
    sources = [ReqItem(text=t.text, quote_refs=[t.id]) for s in sessions for t in s.turns if t.speaker == "customer"]
    items = [i for i in _translate(sources, kb, pm, phenomenon, level=2) if i.ku_refs or _residual(i, sessions)]
    for i in items:
        if i.ku_refs:
            i.text = "客户反映" + i.text
    first = next((i for i in items if i.ku_refs), None)
    if first:                                                         # 同现象的案例作为参考，挂在第一条命中条目上
        first.ku_refs += [ku.id for ku in kb.list(pm, kinds=["case"], phenomenon=phenomenon)]
    known = req.known_slots
    top = max((i for i in items if i.ku_refs), key=lambda i: len(i.quote_refs), default=None)
    head = top.text.split("→ ", 1)[1] if top else "待产品经理确定方向"
    direction = head + ("（" + "、".join(known.values()) + "）" if known else "")
    return PMDraft(direction=direction, product_lang=items + _slot_items(known, sessions))


def draft_chem_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, rd: Actor, at: datetime) -> RDDraft:
    # 条件以 req.known_slots 为准（回问回填后会多出槽位），其余来源是产品需求条目
    sources = [i for i in req.product_lang if i.slot is None] + _slot_items(req.known_slots, sessions)
    items = _translate(sources, kb, rd, req.phenomenon, level=3)
    # 研发方向假设：已知槽位至少有一个落在其适用限定内的同现象已发布产品，取其机理首句
    related = {p.id for p in kb.products()
               if any(req.known_slots.get(slot) in values for slot, values in p.applicable.items())}
    hypotheses = [f"参考 {ku.product_id} 的机理：{ku.text.split('。')[0]}"
                  for ku in kb.list(rd, kinds=["mechanism"], phenomenon=req.phenomenon) if ku.product_id in related]
    return RDDraft(chem_lang=items, hypotheses=hypotheses)


def package_sheet(req: Requirement) -> SheetDraft:
    """只读产品需求条目与对外要点，不接触机理、配方与 L3 转化对照。"""
    needs = [i.text.split("→ ", 1)[-1] for i in req.product_lang if i.slot is None and i.ku_refs]
    conditions = "、".join(i.text.removeprefix("条件：") for i in req.product_lang if i.slot is not None)
    sheet = "（模拟）" + "；".join(dict.fromkeys(needs)) + "。"
    if conditions:
        sheet += f"适用于{conditions}。"
    if req.public_points:
        sheet += req.public_points
    usage = f"（模拟）适用条件：{conditions or '见说明书'}；用量与工艺以试样结果为准，请联系业务员确认。"
    return SheetDraft(sheet=sheet, usage=usage)
