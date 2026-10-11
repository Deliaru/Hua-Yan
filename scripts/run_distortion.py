"""失真对照（WP-E）：业务员转述 / 一次性翻译 / 化言三组 → docs/reports/distortion/（metrics.json、table.csv、distortion.png）。
零成本：抽取、觉、转译全是规则实现；觉的调用记在 runs/distortion/metering.jsonl，大模型调用应为 0。

uv run python scripts/run_distortion.py --cards data/sim/cards.jsonl --n 60
"""
import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from huayan.clock import SimClock, set_clock
from huayan.contracts import SHANGHAI, NeedCard
from huayan.domain import load_seeds
from huayan.eval.distortion import GROUPS, METRICS, run_distortion, summarize
from huayan.meter import FileMeter

PLOTTED = ["completeness", "slot_error", "mistranslation", "traceable", "returned"]
EN = {"completeness": "key info complete", "slot_error": "slot error", "mistranslation": "mistranslation",
      "traceable": "traceable to quote", "returned": "returned by R&D",
      GROUPS[0]: "G1 sales relay", GROUPS[1]: "G2 one-shot translation", GROUPS[2]: "G3 HuaYan (no ask-back)",
      GROUPS[3]: "G3 HuaYan"}                                           # 图中用英文，避免依赖中文字体


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cards", default="data/sim/cards.jsonl")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--config", default="config/eval/distortion.yaml")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--out", default="docs/reports/distortion")
    return ap


def run(args, trace: bool = False):
    """跑一次失真对照并写出报告；返回 (cards, 逐卡逐组 DataFrame, metrics, 轨迹或 None)。make_single_card.py 复用。"""
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    seeds = load_seeds(args.seeds_dir)
    lines = Path(args.cards).read_text(encoding="utf-8").splitlines()[:args.n]
    cards = [NeedCard.model_validate_json(line) for line in lines]
    set_clock(SimClock(datetime(2026, 10, 12, 9, tzinfo=SHANGHAI)))
    meter_path = Path("runs/distortion/metering.jsonl")
    meter_path.unlink(missing_ok=True)
    result = run_distortion(cards, seeds, cfg, random.Random(cfg["seed"]), FileMeter("runs/distortion", "distortion"),
                            trace=trace)
    df, traces = result if trace else (result, None)
    table = summarize(df)
    calls = [json.loads(line)["kind"] for line in meter_path.read_text(encoding="utf-8").splitlines()]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table.rename(columns=METRICS).to_csv(out / "table.csv", encoding="utf-8", float_format="%.3f")
    metrics = {
        "n_cards": len(cards), "cards": args.cards, "seed": cfg["seed"], "placeholder_seeds": seeds.placeholder,
        "relay_assumption": cfg["relay"], "jue": cfg["jue"],
        "calls": {"jue": calls.count("jue"), "llm": calls.count("llm"), "s1": calls.count("s1")},
        "metrics": {g: {k: (None if v is None or v != v else float(v)) for k, v in row.items()}
                    for g, row in table.to_dict("index").items()},
        "labels": METRICS}
    (out / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    fig, axis = plt.subplots(figsize=(11, 4.5))
    width = 0.8 / len(table)
    for k, (group, row) in enumerate(table.iterrows()):
        values = [np.nan if row[m] is None else row[m] for m in PLOTTED]
        bars = axis.bar(np.arange(len(PLOTTED)) + (k - (len(table) - 1) / 2) * width, values, width,
                        label=f"{EN[group]} (asks {row.asks:.2f})")
        axis.bar_label(bars, fmt="%.2f", fontsize=7)
    axis.set_xticks(np.arange(len(PLOTTED)), [EN[m] for m in PLOTTED])
    axis.set(ylim=(0, 1.3), ylabel="rate", title=f"Requirement distortion at R&D ({len(cards)} simulated cards, "
                                                 "G1 noise is assumed)")
    axis.legend(fontsize=8, loc="upper center", ncol=2)
    axis.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "distortion.png", dpi=140)

    print(table.rename(columns=METRICS).to_string(float_format=lambda v: f"{v:.3f}"))
    print(f"觉调用 {calls.count('jue')} 次，大模型调用 {calls.count('llm')} 次；写出 {out}")
    return cards, df, metrics, traces


def main():
    run(parser().parse_args())


if __name__ == "__main__":
    main()
