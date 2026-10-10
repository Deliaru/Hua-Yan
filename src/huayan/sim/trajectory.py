"""契约 ⑨ / JUE_K_TRAINING 第 3、11 节：Jue-K 的追问与回问样本。
程序模拟对话的槽位状态序列（不生成文本），用需求卡真值回头算事后有用性标签；只收前置条件通过的组合，与推理一致。"""
import random
from datetime import datetime, timedelta

from huayan.contracts import (CustomerProfile, JueObject, JueState, NeedCard, NeedState, Phenomenon, Product,
                              QuestionModel, Requirement, Seeds, SlotFill)
from huayan.domain import match_candidates
from huayan.jue.state import realtime_state, requirement_state, trans_hits

TURNS = 6
WRONG, MISS = 0.10, 0.05      # 抽取噪声：填错（同槽位另一个取值，低置信度）、漏填


def ask_label(need: NeedState, card: NeedCard, slot: str, products: list[Product]) -> int:
    """追问：补上真实值（或把填错的改成真实值）后，候选产品集合是否变化。客户说不清的槽位为 0。"""
    if _no_gain(need, card, slot):
        return 0
    known = need.known()
    ids = lambda k: {c.product_id for c in match_candidates(card.phenomenon, k, products)}
    return int(ids(known) != ids({**known, slot: card.slots[slot]}))


def back_label(req: Requirement, need: NeedState, card: NeedCard, slot: str, phen: Phenomenon, kb, layer: int) -> int:
    """回问：补上真实值（或改正）后，本层转化对照的命中集合是否变化。"""
    if _no_gain(need, card, slot):
        return 0
    known = req.known_slots
    return int(trans_hits(phen, known, kb, layer) != trans_hits(phen, {**known, slot: card.slots[slot]}, kb, layer))


def _no_gain(need: NeedState, card: NeedCard, slot: str) -> bool:
    """客户答过「不清楚」、自己也说不清，或已经填对：再问都不会带来新信息。"""
    fill = need.slots.get(slot)
    return (fill is not None and fill.status == "unknown") or slot in card.unknown_slots \
        or need.known().get(slot) == card.slots[slot]


def _answer(need: NeedState, card: NeedCard, slot: str, seeds: Seeds, rng: random.Random, turn: int) -> None:
    tid = f"turn:{need.session_id}:{turn}"
    if slot in card.unknown_slots:
        need.slots[slot] = SlotFill(slot=slot, value=None, status="unknown", confidence=0.7, quote="不太清楚", turn_id=tid)
        return
    r, truth = rng.random(), card.slots[slot]
    if r < MISS:
        return
    if r < MISS + WRONG:
        value = rng.choice([v for v in next(s for s in seeds.slots if s.id == slot).values if v != truth])
        confidence = rng.uniform(0.4, 0.6)
    else:
        value, confidence = truth, rng.uniform(0.7, 0.95)
    need.slots[slot] = SlotFill(slot=slot, value=value, status="filled", confidence=confidence, quote=value, turn_id=tid)


def _sales_asks(need: NeedState, phen: Phenomenon, seeds: Seeds, rng: random.Random) -> list[str]:
    """随机业务员：40% 问还没问清的必问槽位，30% 随机问，30% 不问；每次 1～2 个。"""
    r = rng.random()
    if r < 0.3:
        return []
    known = need.known()
    pool = [s for s in phen.required_slots if s not in known] if r < 0.7 else [s.id for s in seeds.slots]
    return rng.sample(pool, min(len(pool), rng.randint(1, 2)))


def _rows(model: QuestionModel, state: JueState, label, source_id: str) -> list[dict]:
    rows = []
    for d in model.propose(state).decisions:
        if d.precondition_passed:
            obj: JueObject = state.objects[d.object_id]
            rows.append({"family": d.family, "object_type": obj.object_type, "object_id": d.object_id,
                         "at": state.at.isoformat(), "source_id": source_id, "label": label(obj), **obj.attrs})
    return rows


def trajectory(card: NeedCard, seeds: Seeds, kb, model: QuestionModel, rng: random.Random, start: datetime) -> list[dict]:
    """一张卡一段轨迹：每轮对全部槽位出追问样本；应升级的卡在结束时构造需求单，出 layer 2、3 的回问样本。"""
    products = kb.products()
    phen = next(p for p in seeds.phenomena if p.id == card.phenomenon)
    need = NeedState(session_id=card.id, customer_id=card.customer_id, sales_id="sales:S01", phenomenon=card.phenomenon,
                     turn_count=1, profile=CustomerProfile(chem_savvy=card.chem_savvy), extracted_by="rule")
    for slot in card.opening_slots:
        _answer(need, card, slot, seeds, rng, 1)
    rows = []
    for turn in range(1, TURNS + 1):
        state = realtime_state(need, seeds, products, start + timedelta(minutes=turn))
        rows += _rows(model, state, lambda o: ask_label(need, card, o.attrs["slot"], products), card.id)
        for slot in _sales_asks(need, phen, seeds, rng):
            need.asked[slot] = need.asked.get(slot, 0) + 1
            _answer(need, card, slot, seeds, rng, turn + 1)
        need.turn_count += 1
    if card.truth_product is None:
        for status, layer in (("draft", 2), ("pm_confirmed", 3)):
            req = Requirement(id=f"req:{card.id}", question_id=f"q:{card.id}", session_ids=[card.id],
                              phenomenon=card.phenomenon, known_slots=need.known(), direction="", product_lang=[],
                              status=status, drafted_by="pm:P01", created_at=start)
            state = requirement_state(req, need, seeds, kb, start + timedelta(minutes=TURNS + layer))
            rows += _rows(model, state,
                          lambda o: back_label(req, need, card, o.attrs["slot"], phen, kb, layer), card.id)
    return rows
