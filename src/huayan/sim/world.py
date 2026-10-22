"""REPLAN-v8 Q9.1：模拟世界的试样规律（只供 sim/ 与 eval/；觉、门面、Agent 不读）。
需求单上缺了或填错的条件（与需求卡真值不一致）叫「缺口」；缺口只在特定的交叉条件下才会让试样失败，
这是染整常识的简化（模拟假设，写进报告口径）。每个缺口的抽签按「卡 × 槽位」固定种子，
所以同一张卡补上某个条件后，其余缺口的结果不变，可以回答「原条件本会不会失败」。"""
import random
from datetime import datetime, timedelta

from huayan.contracts import NeedCard, Seeds, Trial

BASE_FAIL = 0.06        # 设备、操作原因的失败，与需求无关

# 缺口槽位 → [(真值条件, 失败概率)]：缺口在满足真值条件时按该概率导致失败，取第一条命中的；都不命中按 OTHER
GAPS = {
    "equipment": [({"fiber": {"锦纶氨纶", "锦纶"}}, 0.85)],                # 弹力、细旦面料对张力与流速敏感
    "bath_ph": [({"dye_class": {"酸性染料"}}, 0.85), ({"fiber": {"锦纶", "锦纶氨纶"}}, 0.6),   # 锦纶的上染对 pH 敏感
                ({"dye_class": {"活性染料"}}, 0.45)],
    "water": [({"dye_class": {"活性染料"}, "process": {"浸染"}}, 0.7), ({"fiber": {"粘胶"}}, 0.5)],   # 硬水、回用水下易色点
    "process": [({"process": {"冷轧堆"}}, 0.75)],
    "constraint": [({"constraint": {"低温节能"}, "fiber": {"涤纶", "涤棉"}}, 0.7)],   # 分散染料要高温，低温节能的要求没写上就不行
    "dye_class": [({"fiber": {"涤棉"}}, 0.6)],                               # 涤棉要两类染料，只写一类就不行
}
# 第 3 周起的世界漂移：新客户群大量使用气流染色机做涤纶 / 涤棉，涤纶上的设备缺口也开始要命
DRIFT = {"equipment": [({"fiber": {"涤纶", "涤棉"}, "equipment": {"气流染色机"}}, 0.85)]}
OTHER = 0.01            # v8 Q9.4 调世界：不在交叉条件里的缺口几乎不要命（离线比较见 docs/reports/month/）

# v8 Q9.4：产品本身合不合用（cause = product）。用在适用表以外的取值上（研发签出去的判断把范围放宽了），
# 一半取值其实不行（按「产品 × 槽位 = 取值」固定抽签）；说明书有一处写错；第 3 周起没限定设备的产品在
# 涤纶 / 涤棉 × 气流染色机上开始不行（低浴比、高张力）。在研发中新立的产品只有偶发失败与漂移。
PRODUCT_NOISE, PRODUCT_BAD, OUT_OF_RANGE_BAD = 0.04, 0.65, 0.5
WRONG_CLAIMS = {("HY-RP330", "water", "自来水"): 0.65}       # 说明书写了适用自来水，自来水硬度一波动就色差
DRIFT_PRODUCT = ({"fiber": {"涤纶", "涤棉"}, "equipment": {"气流染色机"}}, 0.5)


def product_risk(product_id: str, applicable: dict[str, list[str]], truth: dict[str, str], drift: bool = False) -> float:
    """applicable：种子里产品的适用表（新立的产品为空）。"""
    for slot, values in applicable.items():
        if (product_id, slot, truth[slot]) in WRONG_CLAIMS:
            return WRONG_CLAIMS[(product_id, slot, truth[slot])]
        if truth[slot] not in values and random.Random(f"{product_id}:{slot}={truth[slot]}").random() < OUT_OF_RANGE_BAD:
            return PRODUCT_BAD
    cond, p = DRIFT_PRODUCT
    if drift and "equipment" not in applicable and all(truth[s] in vs for s, vs in cond.items()):
        return p
    return PRODUCT_NOISE


def gaps(card: NeedCard, known: dict[str, str]) -> list[str]:
    return [s for s, v in card.slots.items() if known.get(s) != v]


def gap_risk(card: NeedCard, slot: str, drift: bool = False) -> float:
    rules = (DRIFT.get(slot, []) if drift else []) + GAPS.get(slot, [])
    return next((p for cond, p in rules if all(card.slots[s] in vs for s, vs in cond.items())), OTHER)


def trial_outcome(card: NeedCard, known: dict[str, str], drift: bool = False,
                  product: tuple[str, dict] | None = None) -> tuple[str, str, list[str]]:
    """返回 (result, cause, missing_slots)：先看缺口（cause = requirement），再看产品本身（给了 product =
    (产品编号, 种子适用表) 时），最后看设备与操作。"""
    fired = [s for s in gaps(card, known) if random.Random(f"{card.id}:{s}").random() < gap_risk(card, s, drift)]
    if fired:
        return "fail", "requirement", fired
    if product and random.Random(f"{card.id}:{product[0]}:product").random() < product_risk(*product, card.slots, drift):
        return "fail", "product", []
    if random.Random(f"{card.id}:base").random() < BASE_FAIL:
        return "fail", "equipment", []
    return "pass", "none", []


def market_outcome(card: NeedCard, known: dict[str, str], drift: bool = False) -> tuple[str, list[str]]:
    """v8 收口：试样过了，客户按真实条件上大货；试样单上的缺口另抽一次签（种子与试样不同），中了即客户评价不通过。"""
    fired = [s for s in gaps(card, known) if random.Random(f"{card.id}:{s}:market").random() < gap_risk(card, s, drift)]
    return ("fail" if fired else "pass"), fired


def recorded(card: NeedCard, seeds: Seeds, rng: random.Random) -> dict[str, str]:
    """历史试样单上记下的条件：必问条件都问了（一成记错），其余条件四成问到；客户说不清的不记。"""
    phen = next(p for p in seeds.phenomena if p.id == card.phenomenon)
    values = {s.id: s.values for s in seeds.slots}
    out = {}
    for slot, truth in card.slots.items():
        if slot in card.unknown_slots or (slot not in phen.required_slots and rng.random() > 0.4):
            continue
        out[slot] = rng.choice([v for v in values[slot] if v != truth]) if rng.random() < 0.1 else truth
    return out


def history_trials(seeds: Seeds, cards: list[NeedCard], end: datetime, rng: random.Random) -> list[Trial]:
    """第 0 周导入的历史试样（模拟 ELN 记录）：每张卡用解决该现象的产品按记下的条件试样一次，分布在 end 之前的半年里。"""
    out = []
    for i, card in enumerate(cards):
        products = sorted((p for p in seeds.products if card.phenomenon in p.solves), key=lambda p: p.id)
        if not products:
            continue
        product, known = rng.choice(products), recorded(card, seeds, rng)
        result, cause, missing = trial_outcome(card, known)
        out.append(Trial(id=f"hist:{i + 1}", product_id=product.id, rd=product.owner, conditions=known, result=result,
                         cause=cause, missing_slots=missing, note="（模拟）历史试样记录",
                         at=end - timedelta(days=rng.uniform(1, 180))))
    return out
