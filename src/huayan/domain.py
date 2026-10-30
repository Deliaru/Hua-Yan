"""契约 1.5：所有包共用的领域函数。"""
from pathlib import Path
from typing import Literal

import yaml

from huayan.contracts import Actor, Candidate, Case, Phenomenon, Product, Seeds, Situation, SlotDef, Translation

_FILES = {"slots": SlotDef, "phenomena": Phenomenon, "products": Product, "cases": Case,
          "translations": Translation, "actors": Actor}


def load_seeds(seeds_dir: str | Path) -> Seeds:
    data, placeholder = {}, False
    for name, model in _FILES.items():
        doc = yaml.safe_load((Path(seeds_dir) / f"{name}.yaml").read_text(encoding="utf-8"))
        placeholder = placeholder or bool(doc["placeholder"])
        data[name] = [model.model_validate(item) for item in doc["items"]]
    for product in data["products"]:
        product.situations = [Situation(phenomenon=ph, conditions=product.applicable,
            capability_id=f"cap:applicable:{product.id}:{ph}") for ph in product.solves]
    return Seeds(**data, placeholder=placeholder)


def consistent(product: Product, known: dict[str, str]) -> bool:
    return any(all(value in situation.conditions[slot] for slot, value in known.items()
                   if slot in situation.conditions) for situation in product.situations)


def temperature_match(actual: tuple[float, float] | None, allowed: tuple[float, float] | None
                      ) -> Literal["satisfied", "unknown", "outside"]:
    if allowed is None:
        return "satisfied"
    if actual is None:
        return "unknown"
    return "satisfied" if allowed[0] <= actual[0] <= actual[1] <= allowed[1] else "outside"


def match_candidates(phenomenon: str, known: dict[str, str], products: list[Product], limited=(), *,
                     temperature_c: tuple[float, float] | None = None) -> list[Candidate]:
    """limited：带研发限制原文的适用能力 id；同一产品优先取不带限制的情境，带限制的只算「可能」。"""
    candidates = []
    for product in sorted(products, key=lambda p: p.id):
        matches = [s for s in product.situations if s.phenomenon == phenomenon
                   and all(value in s.conditions[slot] for slot, value in known.items() if slot in s.conditions)
                   and temperature_match(temperature_c, s.temperature_c) != "outside"]
        if product.status != "released" or not matches:
            continue
        situation = min(matches, key=lambda s: (s.capability_id in limited, sum(slot not in known for slot in s.conditions)
                        + (temperature_match(temperature_c, s.temperature_c) == "unknown")))
        unknown = [slot for slot in situation.conditions if slot not in known]
        if temperature_match(temperature_c, situation.temperature_c) == "unknown":
            unknown.append("temperature_c")
        candidates.append(Candidate(product_id=product.id, unknown_slots=unknown,
            status="possible" if unknown or situation.capability_id in limited else "confirmed",
            capability_id=situation.capability_id))
    return candidates


def correct_product(phenomenon: str, slots: dict[str, str], products: list[Product]) -> str | None:
    by_id = {p.id: p for p in products}
    candidates = match_candidates(phenomenon, slots, products)
    if not candidates:
        return None
    def specificity(candidate):
        situation = next(s for s in by_id[candidate.product_id].situations
                         if s.capability_id == candidate.capability_id)
        return -len(situation.conditions), candidate.product_id
    return min(candidates, key=specificity).product_id


def detect_asked_slots(text: str, slots: list[SlotDef]) -> list[str]:
    return [s.id for s in slots if any(k in text for k in s.ask_keywords)]


def find_slot_values(text: str, slots: list[SlotDef]) -> dict[str, tuple[str, str]]:
    found = {}
    for slot in slots:
        # 先口语说法、再取值本身；同长度时先出现的优先，整体取最长匹配
        pairs = [(phrase, value) for value, phrases in slot.customer_phrases.items() for phrase in phrases]
        pairs += [(value, value) for value in slot.values]
        best = None
        for phrase, value in pairs:
            if phrase in text and (best is None or len(phrase) > len(best[1])):
                best = (value, phrase)
        if best:
            found[slot.id] = best
    return found


def find_phenomenon(text: str, phenomena: list[Phenomenon]) -> tuple[str, str] | None:
    best = None
    for ph in phenomena:
        for phrase in ph.customer_phrases:
            if phrase in text and (best is None or len(phrase) > len(best[1])):
                best = (ph.id, phrase)
    return best
