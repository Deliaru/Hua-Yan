"""契约 ⑨：需求卡。按种子抽样真值并算出正确产品，不调用大模型。"""
import random

from huayan.contracts import NeedCard, Phenomenon, Seeds
from huayan.domain import correct_product


def sample_slots(phen: Phenomenon, seeds: Seeds, rng: random.Random) -> dict[str, str]:
    slots = {}
    for slot in seeds.slots:
        prior = phen.slot_priors.get(slot.id)
        slots[slot.id] = rng.choices(list(prior), weights=list(prior.values()))[0] if prior else rng.choice(slot.values)
    return slots


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
