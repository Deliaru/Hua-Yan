"""追问操作点：在测试卡上做交互回放，比较 Jue-K、B1 必问清单、B2 信息价值规则、觉原型规则模式。
策略每轮选 p ≥ τ 的槽位（最多 2 个）追问，模拟客户按真值回答（与训练相同的抽取噪声），直到没有要问的（最多 8 轮）；
最终按 correct_product 的同一规则用已知槽位选产品，与需求卡的 truth_product 一致（含正确判为应升级）算正确。

uv run python scripts/eval_ask_policies.py [--n 300] → docs/reports/jue_k/ask_policies.json、ask_curve.png
"""
import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from huayan.contracts import SHANGHAI, CustomerProfile, NeedState
from huayan.domain import correct_product, load_seeds
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto
from huayan.jue.publish import select_asks
from huayan.jue.state import realtime_state
from huayan.sim import make_cards
from huayan.sim.trajectory import answer, ask_label

TAUS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
MAX_TURNS = 8
EN = {"Jue-K": "Jue-K", "觉原型（规则分）": "jue_proto (rule score)", "B1 必问清单": "B1 required list",
      "B2 信息价值规则": "B2 info value", "不追问": "no asking"}     # 图中用英文，避免依赖中文字体


def replay(card, model, tau, seeds, products, rng, at):
    need = NeedState(session_id=card.id, customer_id=card.customer_id, sales_id="sales:S01", phenomenon=card.phenomenon,
                     turn_count=1, profile=CustomerProfile(chem_savvy=card.chem_savvy), extracted_by="rule")
    for slot in card.opening_slots:
        answer(need, card, slot, seeds, rng, 1)
    asks = useless = 0
    for turn in range(1, MAX_TURNS + 1):
        state = realtime_state(need, seeds, products, at)
        hints = select_asks(model.propose(state), state, seeds, tau, 2)
        if not hints:
            break
        for h in hints:
            useless += 1 - ask_label(need, card, h.slot, products)
            need.asked[h.slot] = need.asked.get(h.slot, 0) + 1
            answer(need, card, h.slot, seeds, rng, turn + 1)
            asks += 1
        need.turn_count += 1
    return asks, useless, correct_product(card.phenomenon, need.known(), products) == card.truth_product


def evaluate(cards, model, tau, seeds, products, at):
    results = [replay(c, model, tau, seeds, products, random.Random(k), at) for k, c in enumerate(cards)]
    asks = sum(r[0] for r in results)
    return {"tau": tau, "mean_asks": asks / len(cards), "useless_rate": sum(r[1] for r in results) / asks if asks else 0.0,
            "accuracy": sum(r[2] for r in results) / len(cards)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--heldout", default="crease_marks,low_whiteness")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--model-dir", default="models/jue_k")
    ap.add_argument("--out", default="docs/reports/jue_k")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds_dir)
    products = [p for p in seeds.products if p.status == "released"]
    at = datetime(2026, 10, 12, 9, tzinfo=SHANGHAI)
    heldout = set(args.heldout.split(","))
    pool = make_cards(seeds, args.n * 20, random.Random(args.seed))     # 新种子抽卡：训练与校准都没见过
    sets = {"test": [c for c in pool if c.phenomenon not in heldout][:args.n],
            "heldout": [c for c in pool if c.phenomenon in heldout][:args.n]}
    sweep = {"Jue-K": JueK(args.model_dir, "config/templates", "realtime"),
             "觉原型（规则分）": JueProto("config/templates", None, "realtime")}
    fixed = {"B1 必问清单": JueProto("config/baselines/b1_required", None, "realtime"),
             "B2 信息价值规则": JueProto("config/baselines/b2_info_value", None, "realtime")}

    result = {}
    for name, cards in sets.items():
        result[name] = {"n_cards": len(cards), "不追问": evaluate(cards, fixed["B1 必问清单"], 2.0, seeds, products, at)}
        for policy, model in sweep.items():
            result[name][policy] = [evaluate(cards, model, t, seeds, products, at) for t in TAUS]
        for policy, model in fixed.items():
            result[name][policy] = evaluate(cards, model, 0.5, seeds, products, at)
        print(f"== {name}（{len(cards)} 张卡）")
        for policy, r in result[name].items():
            for point in (r if isinstance(r, list) else [r] if isinstance(r, dict) else []):
                print(f"  {policy:14s} τ={point['tau']:<4} 平均追问 {point['mean_asks']:.2f}  无效追问率 {point['useless_rate']:.0%}"
                      f"  最终正确率 {point['accuracy']:.1%}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ask_policies.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for axis, (name, r) in zip(axes, result.items()):
        for policy, style in zip(sweep, ("o-", "s--")):
            axis.plot([p["mean_asks"] for p in r[policy]], [p["accuracy"] for p in r[policy]], style, label=f"{EN[policy]} (sweep tau)")
        for policy, marker in zip(["不追问", *fixed], ("x", "^", "D")):
            axis.plot(r[policy]["mean_asks"], r[policy]["accuracy"], marker, markersize=9, label=EN[policy])
        axis.set(title=f"{name}: asks per session vs final accuracy ({r['n_cards']} cards)", xlabel="mean asks per session",
                 ylabel="final accuracy")
        axis.grid(alpha=0.3)
        axis.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "ask_curve.png", dpi=140)
    print(f"写出 {out / 'ask_policies.json'}、{out / 'ask_curve.png'}")


if __name__ == "__main__":
    main()
