"""契约 ⑨：需求卡。按种子抽样真值并算出正确产品，不调用大模型。"""
import random

from huayan.contracts import NeedCard, Phenomenon, Seeds
from huayan.domain import correct_product


# 槽位取值的化学相容性（印染常识，模拟假设）：(槽位甲, 槽位乙) → 甲的取值 → 乙可取的值
COMPATIBLE = {
    ("fiber", "dye_class"): {"棉": ["活性染料", "还原染料"], "粘胶": ["活性染料", "还原染料"], "涤纶": ["分散染料"],
                             "涤棉": ["分散染料", "活性染料", "还原染料"], "锦纶": ["酸性染料"],
                             "锦纶氨纶": ["酸性染料", "分散染料"]},
    ("dye_class", "bath_ph"): {"活性染料": ["碱性", "中性"], "还原染料": ["碱性"], "分散染料": ["弱酸性"],
                               "酸性染料": ["强酸性", "弱酸性"]},
    ("dye_class", "process"): {"活性染料": ["浸染", "连续轧染", "冷轧堆", "印花"], "还原染料": ["浸染", "连续轧染", "印花"],
                               "分散染料": ["浸染", "连续轧染", "印花"], "酸性染料": ["浸染", "印花"]},
}


def compatible(slots: dict[str, str]) -> bool:
    return all(slots[b] in table[slots[a]] for (a, b), table in COMPATIBLE.items() if a in slots and b in slots)


def sample_slots(phen: Phenomenon, seeds: Seeds, rng: random.Random, fixed: dict[str, str] | None = None) -> dict[str, str]:
    """按现象先验逐槽抽样，只在与已定取值（含 fixed）相容的值里抽。"""
    slots = dict(fixed or {})
    for slot in seeds.slots:
        if slot.id in slots:
            continue
        prior = phen.slot_priors.get(slot.id) or {v: 1.0 for v in slot.values}
        ok = {v: w for v, w in prior.items() if w > 0 and compatible({**slots, slot.id: v})}
        slots[slot.id] = rng.choices(list(ok), weights=list(ok.values()))[0]
    return {s.id: slots[s.id] for s in seeds.slots}


def make_card(card_id: str, phen: Phenomenon, slots: dict[str, str], customer_id: str, seeds: Seeds,
              rng: random.Random, allow_unknown: bool = True) -> NeedCard:
    others = [s.id for s in seeds.slots if s.id != phen.required_slots[0]]
    unknown = [rng.choice(others)] if allow_unknown and rng.random() < 0.1 else []
    told = [s.id for s in seeds.slots if s.id not in unknown]
    savvy = rng.random() < 0.15
    return NeedCard(id=card_id, phenomenon=phen.id, slots=slots, unknown_slots=unknown,
                    opening_slots=rng.sample(told, rng.randint(0, 2)), customer_id=customer_id,
                    chem_savvy=savvy, wants_mechanism=savvy and rng.random() < 0.5,
                    truth_product=correct_product(phen.id, slots, seeds.products))


def make_cards(seeds: Seeds, n: int, rng: random.Random) -> list[NeedCard]:
    customers = [a.id for a in seeds.actors if a.role == "customer"]
    cards = []
    for i in range(1, n + 1):
        phen = rng.choice(seeds.phenomena)
        cards.append(make_card(f"card:{i}", phen, sample_slots(phen, seeds, rng), rng.choice(customers), seeds, rng))
    return cards


def shifted_world(seeds: Seeds, lam: float, rng: random.Random) -> Seeds:
    """Jue-K 学习曲线用：真实世界的槽位先验 = (1-λ)·种子先验（专家估计）+ λ·随机先验（Dirichlet(0.5)）。
    返回的种子只用于抽需求卡真值；觉的状态仍用原种子，即觉只知道专家估计。λ=0 时与原种子相同。"""
    phenomena = []
    for phen in seeds.phenomena:
        priors = {}
        for slot, prior in phen.slot_priors.items():
            noise = [rng.gammavariate(0.5, 1.0) for _ in prior]
            total, z = sum(prior.values()), sum(noise)
            priors[slot] = {v: (1 - lam) * w / total + lam * n / z for (v, w), n in zip(prior.items(), noise)}
        phenomena.append(phen.model_copy(update={"slot_priors": priors}))
    return seeds.model_copy(update={"phenomena": phenomena})
