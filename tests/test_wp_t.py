from datetime import timedelta

from huayan.contracts import (ROLE_LEVEL, CustomerProfile, KnowledgeUnit, NeedState, Question, Requirement, Session,
                              SlotFill, Turn)
from huayan.escalation.translate import draft_chem_need, draft_product_need, package_sheet


class ListOnlyKB:
    """WP-A1 合并前的最简替身：只实现 list 与 products（按 WP-A1 的知识单元格式从小种子构造）。A1 合并后换成 KnowledgeBase.from_seeds。"""

    def __init__(self, seeds, at):
        self._products = [p for p in seeds.products if p.status == "released"]
        self.units = [KnowledgeUnit(id=f"ku:translation:{t.id}", level=t.level, kind="translation", title=t.scene_phrase,
                                    text=f"{t.scene_phrase} → {t.chem_term}", phenomenon_ids=t.phenomenon_ids,
                                    owner=t.owner, created_at=at) for t in seeds.translations]
        self.units += [KnowledgeUnit(id=f"ku:case:{c.id}", level=2, kind="case", title=c.scene_text, text=c.pm_translation,
                                     phenomenon_ids=[c.phenomenon], owner=c.owner, created_at=at) for c in seeds.cases]
        self.units += [KnowledgeUnit(id=f"ku:mechanism:{p.id}", level=3, kind="mechanism", title=p.name, text=p.mechanism,
                                     product_id=p.id, phenomenon_ids=p.solves, owner=p.owner, decryptable=True,
                                     created_at=at) for p in seeds.products if p.status == "released"]

    def products(self):
        return self._products

    def list(self, actor, *, kinds=None, phenomenon=None):
        return [u for u in self.units if u.level <= ROLE_LEVEL[actor.role] and (kinds is None or u.kind in kinds)
                and (phenomenon is None or not u.phenomenon_ids or phenomenon in u.phenomenon_ids)]


def test_layers_cite_own_knowledge_and_keep_quotes(mini_seeds, sim_clock):
    at = sim_clock.now()
    actors = {a.id: a for a in mini_seeds.actors}
    kb = ListOnlyKB(mini_seeds, at)
    lines = [("customer", "染完以后布面深一块浅一块"), ("sales", "请问是什么面料？"), ("customer", "锦氨的"),
             ("sales", "用的什么染色机？"), ("customer", "气流缸")]
    turns = [Turn(id=f"turn:sess:1:{n}", session_id="sess:1", n=n, speaker=sp, text=tx, ts=at + timedelta(minutes=n))
             for n, (sp, tx) in enumerate(lines, 1)]
    fill = lambda slot, value, quote, n: SlotFill(slot=slot, value=value, status="filled", confidence=0.7, quote=quote,
                                                 turn_id=f"turn:sess:1:{n}")
    need = NeedState(session_id="sess:1", customer_id="customer:C02", sales_id="sales:S01", phenomenon="color_unlevel",
                     slots={"fiber": fill("fiber", "锦纶氨纶", "锦氨", 3),
                            "equipment": fill("equipment", "气流染色机", "气流缸", 5)},
                     turn_count=5, profile=CustomerProfile())
    session = Session(id="sess:1", customer_id="customer:C02", sales_id="sales:S01", started_at=at, turns=turns,
                      need=need, status="escalated")
    q = Question(id="q:1", family="escalate_need", title="升级", object_id="sess:1", owner_role="pm", scored_by="mock",
                 discoverer="jev", dedup_key="escalate_need:sess:1", created_at=at)
    l3_terms = [t.chem_term for t in mini_seeds.translations if t.level == 3]
    units = {u.id: u for u in kb.units}

    # L2：引用 tr:1、tr:3，不含任何 L3 知识（引用与文字都不含）
    pm = draft_product_need(q, [session], kb, actors["pm:P01"], at)
    l2_refs = {r for i in pm.product_lang for r in i.ku_refs}
    assert {"ku:translation:tr:1", "ku:translation:tr:3"} <= l2_refs
    assert all(units[r].level <= 2 for r in l2_refs)
    assert not any(term in text for text in [pm.direction] + [i.text for i in pm.product_lang] for term in l3_terms)

    # L3：引用两位研发各自的转化对照，每条都能回查原话
    req = Requirement(id="req:1", question_id="q:1", session_ids=["sess:1"], phenomenon="color_unlevel",
                      known_slots=need.known(), direction=pm.direction, product_lang=pm.product_lang, status="pm_confirmed",
                      drafted_by="pm:P01", public_points="低浴比下匀染好、氨纶沾色低", created_at=at)
    rd = draft_chem_need(req, [session], kb, actors["rd:R02"], at)
    l3_owners = {units[r].owner for i in rd.chem_lang for r in i.ku_refs if units[r].level == 3}
    assert {"rd:R01", "rd:R02"} <= l3_owners
    assert all(i.quote_refs for i in rd.chem_lang)

    # 反向包装：不含 L3 转化对照译文与任何机理文字
    sheet = package_sheet(req)
    secret = l3_terms + [p.mechanism for p in mini_seeds.products]
    assert not any(s in sheet.sheet or s in sheet.usage for s in secret)
