"""契约 1.5：所有包共用的领域函数。"""
from pathlib import Path

import yaml

from huayan.contracts import Actor, Candidate, Case, Phenomenon, Product, Seeds, SlotDef, Translation

_FILES = {"slots": SlotDef, "phenomena": Phenomenon, "products": Product, "cases": Case,
          "translations": Translation, "actors": Actor}


def load_seeds(seeds_dir: str | Path) -> Seeds:
    data, placeholder = {}, False
    for name, model in _FILES.items():
        doc = yaml.safe_load((Path(seeds_dir) / f"{name}.yaml").read_text(encoding="utf-8"))
        placeholder = placeholder or bool(doc["placeholder"])
        data[name] = [model.model_validate(item) for item in doc["items"]]
    return Seeds(**data, placeholder=placeholder)


def consistent(product: Product, known: dict[str, str]) -> bool:
    return all(value in product.applicable[slot] for slot, value in known.items() if slot in product.applicable)


def match_candidates(phenomenon: str, known: dict[str, str], products: list[Product]) -> list[Candidate]:
    return [Candidate(product_id=p.id, unknown_slots=[s for s in p.applicable if s not in known])
            for p in sorted(products, key=lambda p: p.id)
            if p.status == "released" and phenomenon in p.solves and consistent(p, known)]


def correct_product(phenomenon: str, slots: dict[str, str], products: list[Product]) -> str | None:
    by_id = {p.id: p for p in products}
    candidates = match_candidates(phenomenon, slots, products)
    if not candidates:
        return None
    return min(candidates, key=lambda c: (-len(by_id[c.product_id].applicable), c.product_id)).product_id


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
