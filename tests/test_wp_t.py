from datetime import timedelta

from huayan.contracts import CustomerProfile, NeedState, Requirement, Session, SlotFill, Turn
from huayan.escalation.translate import draft_chem_need, draft_product_need, leak_hits, package_sheet
from huayan.events import EventLog
from huayan.knowledge import AuditLog, KnowledgeBase


def test_layers_cite_own_knowledge_and_keep_quotes(mini_seeds, sim_clock):
    at = sim_clock.now()
    actors = {a.id: a for a in mini_seeds.actors}
    kb = KnowledgeBase.from_seeds(mini_seeds, EventLog(), AuditLog())
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
    req = Requirement(id="req:1", question_id="q:1", session_ids=[session.id], phenomenon="color_unlevel",
                      known_slots=need.known(), assigned_rd="rd:R02", status="draft", created_at=at)
    l3_terms = [t.chem_term for t in mini_seeds.translations if t.level == 3]
    units = {u.id: u for u in kb.list(actors["rd:R01"])}

    # L2：引用 tr:1、tr:3，不含任何 L3 知识（引用与文字都不含）
    before = req.model_dump()
    pm = draft_product_need(req, [session], kb, actors["pm:agent"], at)
    assert req.model_dump() == before  # 转译只返回草稿，不自行推进需求单。
    l2_refs = {r for i in pm.product_lang for r in i.ku_refs}
    assert {"ku:translation:tr:1", "ku:translation:tr:3"} <= l2_refs
    assert all(units[r].level <= 2 for r in l2_refs)
    assert not any(term in text for text in [pm.direction] + [i.text for i in pm.product_lang] for term in l3_terms)

    # 需求单是现象与已确认条件的来源，不再从第一个会话重建或补入被排除的槽位。
    scoped = req.model_copy(update={"phenomenon": "poor_fastness", "known_slots": {"fiber": "锦纶氨纶"}})
    other = draft_product_need(scoped, [session], kb, actors["pm:agent"], at)
    assert not any(i.ku_refs for i in other.product_lang)
    assert {i.slot for i in other.product_lang if i.slot} == {"fiber"}

    # 回问补充的约束由需求单承接，并保留新增客户原话。
    answer = Turn(id="turn:sess:1:6", session_id=session.id, n=6, speaker="customer", text="不能含APEO",
                  ts=at + timedelta(minutes=6))
    session.turns.append(answer)
    session.need.slots["constraint"] = fill("constraint", "无APEO", "不能含APEO", 6)
    req.known_slots["constraint"] = "无APEO"
    pm = draft_product_need(req, [session], kb, actors["pm:agent"], at)
    constraint = next(i for i in pm.product_lang if i.slot == "constraint")
    assert constraint.text == "条件：无APEO" and constraint.quote_refs == [answer.id]

    # L3：引用两位研发各自的转化对照，每条都能回查原话
    req.direction, req.product_lang = pm.direction, pm.product_lang
    req.status, req.rd_accepted_by = "rd_accepted", req.assigned_rd
    req.public_points = "低浴比下匀染好、氨纶沾色低"
    rd = draft_chem_need(req, [session], kb, actors["rd:R02"], at)
    l3_owners = {units[r].owner for i in rd.chem_lang for r in i.ku_refs if units[r].level == 3}
    assert {"rd:R01", "rd:R02"} <= l3_owners
    assert all(i.quote_refs for i in rd.chem_lang)

    # 反向包装：不含 L3 转化对照译文与任何机理文字
    sheet = package_sheet(req)
    secret = l3_terms + [p.mechanism for p in mini_seeds.products]
    assert not any(s in sheet.sheet or s in sheet.usage for s in secret)

    # 三类来源逐句定位；同句同类去重，输出不含保密正文，L2 不进入词表。
    sealed = "升温到九十度后分两次加入保护液"
    hypothesis = "预润湿可能减少织物表面的机械摩擦"
    text = f"请先做小样。{sealed}；{l3_terms[0]}！{hypothesis}？\n谢谢。"
    hits = leak_hits(text, [sealed, sealed, ""], [hypothesis], kb)
    assert [h.model_dump() for h in hits] == [
        {"index": 1, "source": "sealed"}, {"index": 2, "source": "l3_term"},
        {"index": 3, "source": "hypothesis"}]
    assert [(h.index, h.source) for h in leak_hits(sealed, [sealed], [sealed], kb)] == [
        (0, "sealed"), (0, "hypothesis")]
    assert leak_hits("。；！？\n", [sealed], [hypothesis], kb) == []
    l2_text = "。".join(t.chem_term for t in mini_seeds.translations if t.level == 2)
    assert leak_hits(l2_text, [], [], kb) == []
    # 措辞略改仍由二元组重合识别；不能只实现完整子串匹配。
    assert any(h.source == "sealed" for h in leak_hits("升温至九十度以后分两次加入保护液", [sealed], [], kb))
