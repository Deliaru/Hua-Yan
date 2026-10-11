"""业务周对照（WP-E）：处置 / 不处置两个分支 × 觉原型、Jue-K、规则告警三种发现器 → runs/week-<周>-<发现器>-<分支>/
与 docs/reports/week/（metrics.json、week_detection.png、week_escalations.png）。零成本：抽取规则、Jev 桩、起草走 hub 离线骨架。
流程只由觉的问题与模拟人的签字推进（eval/week.py）；handling 为处置分支里除升级、回问以外的签字记录。

uv run python scripts/run_week.py --week data/week/w1
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from huayan.contracts import Injection
from huayan.domain import load_seeds
from huayan.eval.metrics import consequences, summary
from huayan.eval.week import run_week

DISCOVERERS = ["jue_proto", "jue_k", "rule_alert"]
POLICIES = ["ignore", "handle"]
EN = {"jue_proto": "Jue prototype", "jue_k": "Jue-K", "rule_alert": "rule alert (>=3 escalations)"}   # 图中用英文


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="data/week/w1")
    ap.add_argument("--run-root", default="runs")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--out", default="docs/reports/week")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds_dir)
    injections = [Injection.model_validate_json(l)
                  for l in (Path(args.week) / "injections.jsonl").read_text(encoding="utf-8").splitlines()]
    theme = next(i.object_id for i in injections if i.family == "opportunity" and not i.hard_negative)
    runs = {(d, p): run_week(args.week, p, d, args.run_root) for d in DISCOVERERS for p in POLICIES}
    result = {"week": args.week, "placeholder_seeds": seeds.placeholder, "opportunity_theme": theme,
              "runs": {f"{d}/{p}": str(run) for (d, p), run in runs.items()},
              "detection": {d: summary(runs[(d, "ignore")], injections) for d in DISCOVERERS},
              "consequences": {f"{d}/{p}": consequences(runs[(d, p)], theme, seeds) for d in DISCOVERERS for p in POLICIES},
              "handling": {d: [r for r in map(json.loads, (runs[(d, "handle")] / "week_log.jsonl")
                                              .read_text(encoding="utf-8").splitlines())
                               if r["family"] not in ("escalate_need", "ask_back")]
                           for d in DISCOVERERS}}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _plot_detection(result, injections, out / "week_detection.png")
    _plot_escalations(result, out / "week_escalations.png")

    for d in DISCOVERERS:
        s = result["detection"][d]
        print(f"{d}: 命中 {s['hits']}/{s['positives']}，困难负样本误报 {s['false_alarms']}/{s['hard_negatives']}，"
              f"平均提前 {s['mean_lead_hours']} 小时，注入外发现 {s['n_found_outside_injections']}，觉大模型调用 {s['jue_llm_calls']}")
        for p in POLICIES:
            c = result["consequences"][f"{d}/{p}"]
            print(f"  {p}: 发现后同主题升级 {c['escalations_after']}，L1 直接命中 {c['l1_hits_after']}；全周升级 {c['all_escalations']}")
    print(f"写出 {out}")


def _plot_detection(result: dict, injections: list[Injection], path: Path) -> None:
    fig, axis = plt.subplots(figsize=(11, 4.2))
    markers = {"jue_proto": "o", "jue_k": "s", "rule_alert": "^"}
    for k, inj in enumerate(injections):
        color = "#bbbbbb" if inj.hard_negative else "#9ecae1"
        axis.barh(k, mdates.date2num(inj.latest) - mdates.date2num(inj.earliest), left=mdates.date2num(inj.earliest),
                  height=0.5, color=color)
        axis.plot(mdates.date2num(inj.onset), k, "|", color="black", markersize=14)
        for j, d in enumerate(DISCOVERERS):
            row = result["detection"][d]["detection"][k]
            if row["found_at"]:
                axis.plot(mdates.date2num(datetime.fromisoformat(row["found_at"])), k + (j - 1) * 0.18,
                          markers[d], color=f"C{j}", label=EN[d] if k == 0 or not axis.get_legend_handles_labels()[1].count(EN[d]) else None)
    labels = [f"{i.id} {i.family}{' (hard neg.)' if i.hard_negative else ''}" for i in injections]
    axis.set_yticks(range(len(injections)), labels, fontsize=8)
    axis.invert_yaxis()
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    axis.set(title="Scheduled discovery on a simulated week: blue = valid window, grey = hard negative, | = onset")
    axis.legend(fontsize=8, loc="lower left")
    axis.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)


def _plot_escalations(result: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, len(DISCOVERERS), figsize=(12, 3.6), sharey=True)
    days = sorted({day for c in result["consequences"].values() for day in c["escalations_by_day"]})
    for axis, d in zip(axes, DISCOVERERS):
        for j, p in enumerate(POLICIES):
            counts = [result["consequences"][f"{d}/{p}"]["escalations_by_day"].get(day, 0) for day in days]
            axis.bar([k + (j - 0.5) * 0.4 for k in range(len(days))], counts, 0.4, label=p)
        axis.set_xticks(range(len(days)), [day[5:] for day in days], fontsize=8)
        axis.set_title(EN[d], fontsize=9)
        axis.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("escalations / day")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Opportunity theme {result['opportunity_theme'].split('|')[0]}: escalations per day, handle vs ignore",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=140)


if __name__ == "__main__":
    main()
