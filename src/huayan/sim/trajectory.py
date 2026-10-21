"""契约 ⑨ / JUE_K_TRAINING 第 3、11 节：Jue-K 的追问与回问样本。
程序模拟对话的槽位状态序列（不生成文本），用需求卡真值回头算事后有用性标签；只收前置条件通过的组合，与推理一致。"""
import random
from datetime import datetime, timedelta

from huayan.contracts import (Capability, CustomerProfile, JueObject, JueState, NeedCard, NeedState, Phenomenon, Product,
                              QuestionModel, Requirement, ReuseProposal, Seeds, SlotFill)
from huayan.domain import correct_product
from huayan.events import EventLog
from huayan.jue.state import collect_scheduled, realtime_state, requirement_state, trans_hits
from huayan.sim.world import trial_outcome

TURNS = 6
WRONG, MISS = 0.10, 0.05      # 抽取噪声：填错（同槽位另一个取值，低置信度）、漏填


def ask_label(need: NeedState, card: NeedCard, slot: str, products: list[Product], required: list[str]) -> int:
    """追问：补上真实值（或把填错的改成真实值）后，最终推荐是否由错变对（含正确判为应升级）；
    或该需求应升级、而这是研发的必问信息（不问研发会退回）。客户说不清的槽位为 0。"""
    if _no_gain(need, card, slot):
        return 0
    if card.truth_product is None and slot in required:
        return 1
    known = need.known()
    right = lambda k: correct_product(card.phenomenon, k, products) == card.truth_product
    return int(not right(known) and right({**known, slot: card.slots[slot]}))


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


def answer(need: NeedState, card: NeedCard, slot: str, seeds: Seeds, rng: random.Random, turn: int) -> None:
    """客户按真值回答该槽位，经过抽取噪声写入 NeedState（追问策略评估的回放也用它）。"""
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


def _rows(model: QuestionModel, state: JueState, label, source_id: str,
          families=("ask_slot", "ask_back")) -> list[dict]:
    """只收追问、回问（槽位对象）与 v8 试样风险；需求单对象上的其余推进决策由规则到点，不训练。"""
    rows = []
    for d in model.propose(state).decisions:
        if d.precondition_passed and d.family in families:
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
        answer(need, card, slot, seeds, rng, 1)
    rows = []
    for turn in range(1, TURNS + 1):
        state = realtime_state(need, seeds, products, start + timedelta(minutes=turn))
        rows += _rows(model, state, lambda o: ask_label(need, card, o.attrs["slot"], products, phen.required_slots),
                      card.id)
        for slot in _sales_asks(need, phen, seeds, rng):
            need.asked[slot] = need.asked.get(slot, 0) + 1
            answer(need, card, slot, seeds, rng, turn + 1)
        need.turn_count += 1
    if card.truth_product is None:
        # v5 链路：业务员签字升级 → 空单 → 产品经理 Agent 查无现成产品后起草 L2（layer 2）→ 研发接单后起草 L3（layer 3）。
        # 槽位对象只取决于已知槽位与层，与草稿内容无关，所以不生成条目。
        req = Requirement(id=f"req:{card.id}", question_id=f"q:{card.id}", session_ids=[card.id],
                          phenomenon=card.phenomenon, known_slots=need.known(), assigned_rd="rd:R01",
                          reuse=ReuseProposal(product_id=None), status="draft", created_at=start)
        for status, layer in (("draft", 2), ("rd_accepted", 3)):
            req.status = status
            state = requirement_state(req, need, seeds, kb, start + timedelta(minutes=TURNS + layer), EventLog())
            rows += _rows(model, state,
                          lambda o: back_label(req, need, card, o.attrs["slot"], phen, kb, layer), card.id)
        # v8 试样风险：转译确认、即将试样；标签 = 按世界规律试样会因需求条件缺失而失败
        solvers = sorted((p for p in seeds.products if card.phenomenon in p.solves), key=lambda p: (p.status != "project", p.id))
        req.status, req.product_id = "rd_confirmed", solvers[0].id if solvers else None
        state = requirement_state(req, need, seeds, kb, start + timedelta(minutes=TURNS + 4), EventLog())
        rows += _rows(model, state, lambda o: int(trial_outcome(card, req.known_slots)[1] == "requirement"),
                      card.id, ("trial_risk",))
    return rows


DAYS, BAD_FAIL, NOISE_PRODUCT, NOISE_EQUIPMENT, BAD_SHARE = 28, 0.65, 0.04, 0.06, 0.4


def capability_rows(cap_id: str, seeds: Seeds, model: QuestionModel, rng: random.Random, start: datetime) -> list[dict]:
    """v8 判断过时：造一条运行中人签出的适用判断的四周生命周期。四成本来就对；三成在某个「槽位 = 取值」上
    本来就错；三成在第 7～21 天的世界漂移之后才在那个取值上变错。每次使用后试样一次，结果按这条规律抽签；
    每次试样后看一眼，标签 = 接下来 5 次试样的产品原因失败率 ≥ 0.4（不足 5 次的不出样本）。"""
    product = rng.choice([p for p in seeds.products if p.status == "released"])
    phenomenon = rng.choice(product.solves)
    values = {s.id: s.values for s in seeds.slots}
    scope = {"fiber": rng.sample(values["fiber"], rng.randint(1, 2))}
    cap = Capability(id=cap_id, form="applicable", audience=0, payload={"product_id": product.id,
        "phenomenon": phenomenon, "conditions": scope}, based_on=[f"ku:claim:{cap_id}"], granted_by=product.owner,
        approved_by="pm:P01", status="active", at=start)
    kind, slot = rng.random(), rng.choice([s for s in values if s != "fiber"])
    bad, wrong_from = rng.choice(values[slot]), (start if kind < 0.7 else start + timedelta(days=rng.uniform(7, 21)))
    events, outcomes = EventLog(), []
    for i, day in enumerate(sorted(rng.uniform(0.2, DAYS) for _ in range(rng.randint(8, 30)))):
        at = start + timedelta(days=day)
        conditions = {s: rng.choice(scope.get(s, vs)) for s, vs in values.items()}
        if rng.random() < BAD_SHARE:
            conditions[slot] = bad
        hit = kind >= 0.4 and at >= wrong_from and conditions[slot] == bad
        r = rng.random()
        result, cause = (("fail", "product") if r < (BAD_FAIL if hit else NOISE_PRODUCT) else
                         ("fail", "equipment") if r < (BAD_FAIL if hit else NOISE_PRODUCT) + NOISE_EQUIPMENT else ("pass", "none"))
        events.append("capability_used", "sales:S01", {"capability_id": cap_id}, session_id=f"{cap_id}/s{i}", ts=at)
        events.append("trial", product.owner, {"trial_id": f"{cap_id}/t{i}", "product_id": product.id,
            "conditions": conditions, "result": result, "cause": cause}, ts=at + timedelta(hours=2))
        if result == "pass" and hit and rng.random() < 0.5:        # 试样过了，客户大货上仍不满意
            events.append("market_eval", "sales:S01", {"trial_id": f"{cap_id}/t{i}", "result": "fail"},
                          ts=at + timedelta(days=2))
        outcomes.append((at + timedelta(hours=3), cause == "product"))
    rows = []
    for k, (at, _) in enumerate(outcomes[:-5]):
        state = collect_scheduled(events, at, seeds, [], caps=[cap])[0]
        label = int(sum(f for _, f in outcomes[k + 1:k + 6]) / 5 >= 0.4)
        rows += _rows(model, state, lambda o, y=label: y, cap_id, ("stale_capability",))
    return rows
