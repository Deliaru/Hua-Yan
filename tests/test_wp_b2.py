import random
from pathlib import Path

from huayan.sim import make_cards, make_week, to_jsonl

SRC = Path(__file__).parents[1] / "src" / "huayan"
FORBIDDEN = ["injections", "NeedCard", "cards.jsonl", "truth_product"]


def test_reproducible_and_isolated(mini_seeds, sim_clock):
    def generate(seed):
        cards = make_cards(mini_seeds, 50, random.Random(seed))
        items, week_cards, injections = make_week(mini_seeds, sim_clock.now(), 5, random.Random(seed))
        return [to_jsonl(rows) for rows in (cards, items, week_cards, injections)]

    first, second = generate(11), generate(11)
    assert first == second and first != generate(12)

    # 业务代码不得引用需求卡与注入清单（契约目录只放定义，不算引用）
    offenders = [str(p.relative_to(SRC)) for p in SRC.rglob("*.py")
                 if p.parent.name not in ("sim", "eval", "contracts")
                 and any(word in p.read_text(encoding="utf-8") for word in FORBIDDEN)]
    assert offenders == []
