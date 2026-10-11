"""契约 ⑨：模拟业务周。常规会话 + 三类注入 + 困难负样本；注入清单只供事后评估。
注入对象按固定规则从种子推出（不写死型号与槽位）：机会汇聚取第一个「必问槽位全被限定」的研发中产品所覆盖的主题；
知识冲突取同现象下第一个有适用限定的已发布产品，在其第一个限定槽位的最后一个取值上连续失败。"""
import random
from datetime import datetime, time, timedelta

from huayan.contracts import Injection, NeedCard, Phenomenon, Seeds, Trial, WeekItem
from huayan.domain import correct_product
from huayan.jue.state import theme_id
from huayan.sim.cards import make_card, sample_slots

SESSIONS_PER_DAY = 20
_LEAK = ["{p} 的配方里加了什么？", "{p} 为什么能起作用，原理是什么？", "{p} 主要用的是哪类表面活性剂？",
         "{p} 和同类产品成分上有什么区别？", "{p} 里面的有效成分大概是什么结构？", "我们想自己配 {p}，需要哪些原料？"]


def make_week(seeds: Seeds, start: datetime, days: int,
              rng: random.Random) -> tuple[list[WeekItem], list[NeedCard], list[Injection]]:
    customers = [a.id for a in seeds.actors if a.role == "customer"]
    sales = [a.id for a in seeds.actors if a.role == "sales"]
    released = sorted((p for p in seeds.products if p.status == "released"), key=lambda p: p.id)
    phens = {p.id: p for p in seeds.phenomena}
    day0 = datetime.combine(start.date(), time(9), tzinfo=start.tzinfo)
    at = lambda d, span=9 * 60: day0 + timedelta(days=d, minutes=rng.randrange(span))
    close = lambda d: day0 + timedelta(days=d, hours=9)          # 当天 18:00
    items, cards, injections = [], [], []

    def session(phen: Phenomenon, slots: dict, customer: str, d: int, sales_id: str | None = None,
                allow_unknown: bool = False) -> datetime:
        card = make_card(f"wk:card:{len(cards) + 1}", phen, slots, customer, seeds, rng, allow_unknown)
        cards.append(card)
        items.append(WeekItem(at=(t := at(d)), kind="session", actor=sales_id or rng.choice(sales), card_id=card.id))
        return t

    def trial(product, conditions: dict, result: str, cause: str, t: datetime) -> None:
        tr = Trial(id=f"wk:trial:{sum(i.kind == 'trial' for i in items) + 1}", product_id=product.id, rd=product.owner,
                   conditions=conditions, result=result, cause=cause, at=t)
        items.append(WeekItem(at=t, kind="trial", actor=product.owner, trial=tr))

    def query(actor: str, text: str, t: datetime) -> None:
        items.append(WeekItem(at=t, kind="query", actor=actor, text=text))

    def inject(family: str, object_id: str, times: list[datetime], earliest: datetime, latest: datetime,
               hard: bool = False) -> None:
        injections.append(Injection(id=f"inj:{len(injections) + 1}", family=family, object_id=object_id,
                                    hard_negative=hard, onset=min(times), earliest=earliest, latest=latest))

    def unsolved(exclude: set[str]) -> tuple[Phenomenon, dict]:
        """现象与槽位一起抽：相容约束下有的现象总有现成产品可解（如色牢度差），只固定现象会死循环。"""
        while True:
            phen = rng.choice(seeds.phenomena)
            slots = sample_slots(phen, seeds, rng)
            if correct_product(phen.id, slots, seeds.products) is None and theme_id(phen.id, slots, seeds) not in exclude:
                return phen, slots

    # 机会汇聚：第 1～4 天，3～4 个不同客户共 5 次同主题、无已发布产品适用
    project = next(p for p in sorted(seeds.products, key=lambda p: p.id)
                   if p.status == "project" and all(s in p.applicable for s in phens[p.solves[0]].required_slots))
    phen = phens[project.solves[0]]
    fixed = {s: project.applicable[s][0] for s in phen.required_slots}
    opp_theme = theme_id(phen.id, fixed, seeds)
    group = rng.sample(customers, min(4, len(customers)))
    visits = sorted((session(phen, sample_slots(phen, seeds, rng, fixed), c, rng.randrange(4)), c)
                    for c in group + [rng.choice(group)])
    earliest = next(t for k, (t, _) in enumerate(visits) if len({c for _, c in visits[:k + 1]}) >= 2)
    inject("opportunity", opp_theme, [t for t, _ in visits], earliest, close(3))

    # 困难负样本：同一个客户就同一个无解需求反复咨询 3 次（第 2～4 天）
    other, slots = unsolved({opp_theme})
    cust = rng.choice(customers)
    times = [session(other, slots, cust, d) for d in (1, 2, 3)]
    inject("opportunity", theme_id(other.id, slots, seeds), times, times[0], close(days - 1), hard=True)
    used = {opp_theme, theme_id(other.id, slots, seeds)}

    # 困难负样本：同一现象 3 次，都有产品解决
    while correct_product(phen.id, slots := sample_slots(phen, seeds, rng), seeds.products) is None:
        pass
    times = [session(phen, slots, c, d) for c, d in zip(rng.sample(customers, 3), sorted(rng.sample(range(days), 3)))]
    inject("opportunity", theme_id(phen.id, slots, seeds), times, times[0], close(days - 1), hard=True)

    # 知识冲突：第 2～4 天，某产品在其声称适用的取值上 3 次试样失败、原因为产品本身
    target = next(p for p in released if phen.id in p.solves and p.applicable)
    slot, values = next(iter(target.applicable.items()))
    times = [at(d) for d in (1, 2, 3)]
    for t in times:
        trial(target, {**{s: v[0] for s, v in target.applicable.items()}, slot: values[-1]}, "fail", "product", t)
    inject("knowledge_conflict", f"knowledge:{target.id}|{slot}={values[-1]}", times, times[1], close(days - 1))

    # 困难负样本：1 次试样失败、原因 equipment；另有 3 次正常通过的试样
    restricted = [p for p in released if p.applicable and p.id != target.id]
    for k, p in enumerate(rng.sample(restricted, min(4, len(restricted)))):
        cond = {s: v[0] for s, v in p.applicable.items()}
        trial(p, cond, "fail" if k == 0 else "pass", "equipment" if k == 0 else "none", t := at(rng.randrange(days)))
        if k == 0:
            s0 = next(iter(cond))
            inject("knowledge_conflict", f"knowledge:{p.id}|{s0}={cond[s0]}", [t], t, close(days - 1), hard=True)

    # 泄露风险：第 3 天，某业务员 2 小时内 6 次换角度问同一产品的原理和配方
    leaker, normal = rng.sample(sales, 2)
    product = rng.choice(released)
    base = at(2, 7 * 60)
    times = [base + timedelta(minutes=18 * k + rng.randrange(10)) for k in range(6)]
    for t, text in zip(times, rng.sample(_LEAK, 6)):
        query(leaker, text.format(p=product.id), t)
    inject("leak_risk", f"actor:{leaker}", times, times[2], close(3))

    # 困难负样本：另一个业务员正常地连续问 6 个不同产品的用法
    base = at(rng.randrange(days), 7 * 60)
    times = [base + timedelta(minutes=15 * k) for k in range(6)]
    for t, p in zip(times, rng.sample(released, min(6, len(released)))):
        query(normal, f"{p.id} 怎么用？用量多少？", t)
    inject("leak_risk", f"actor:{normal}", times, times[0], close(days - 1), hard=True)

    # 常规会话：每天约 20 次，业务员轮流；会升级的主题各只出现一次，且避开注入主题（避免意外形成机会汇聚）
    for d in range(days):
        for k in range(SESSIONS_PER_DAY):
            while True:
                ph = rng.choice(seeds.phenomena)
                slots = sample_slots(ph, seeds, rng)
                key = theme_id(ph.id, slots, seeds)
                if correct_product(ph.id, slots, seeds.products) is not None or key not in used:
                    break
            if correct_product(ph.id, slots, seeds.products) is None:
                used.add(key)
            session(ph, slots, rng.choice(customers), d, sales[k % len(sales)], allow_unknown=True)

    return sorted(items, key=lambda i: i.at), cards, injections


def to_jsonl(rows) -> str:
    return "".join(r.model_dump_json() + "\n" for r in rows)
