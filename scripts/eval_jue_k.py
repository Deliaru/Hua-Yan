"""评估 Jue-K → docs/reports/jue_k/：
1. 校准（主结果）：每类在 test（追问 / 回问另加 heldout）上的 AUC、Brier、ECE，校准前后与原型规则分数对照；五类可靠性图；
2. 定时发现：6 个测试周（与训练同一生成方式、在真实链路上跑出事件、未参与训练）上，Jue-K 与原型规则模式按 WP-E 口径比较窗口内发现、提前量、困难负样本误报。
ECE 用 10 个等频分箱、可靠性图用 10 个等宽分箱，做法参照 JUE-r2 eval/calibration.py。

uv run python scripts/eval_jue_k.py（先跑 make_jue_k_data.py、train_jue_k.py；追问操作点见 eval_ask_policies.py）
"""
import argparse
import json
import pickle
import random
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from huayan.contracts import SHANGHAI
from huayan.domain import load_seeds
from huayan.eval.week import chain_events
from huayan.events import EventLog
from huayan.jue.expr import evaluate
from huayan.jue.features import vectorize
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.state import collect_scheduled
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.sim import make_week
from huayan.sim.week_events import TICK_HOURS
from train_jue_k import META, features

FAMILIES = ["ask_slot", "ask_back", "opportunity", "knowledge_conflict", "leak_risk"]


def stats(p: np.ndarray, y: np.ndarray) -> dict:
    bins = np.array_split(np.argsort(p, kind="stable"), min(10, len(p)))
    ece = sum(len(b) * abs(p[b].mean() - y[b].mean()) for b in bins) / len(p)
    return {"n": int(len(p)), "base_rate": float(y.mean()), "brier": float(np.mean((p - y) ** 2)), "ece": float(ece),
            "auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None}


def reliability(p: np.ndarray, y: np.ndarray) -> list[tuple[float, float, int]]:
    index = np.minimum((p * 10).astype(int), 9)
    return [(float(p[index == i].mean()), float(y[index == i].mean()), int((index == i).sum()))
            for i in range(10) if (index == i).any()]


def detection(seeds, products, models: dict, weeks: range, start: datetime, days: int, threshold: float) -> dict:
    result = {name: {"hits": 0, "positives": 0, "lead_hours": [], "hard_false_alarms": 0, "hard_negatives": 0,
                     "other_alarms": 0} for name in models}
    by_family = {name: {} for name in models}
    work = tempfile.TemporaryDirectory()
    for w in weeks:
        items, cards, injections = make_week(seeds, start, days, random.Random(1000 + w))
        events = chain_events(items, cards, Path(work.name), f"w{w}")
        ticks = [datetime.combine(start.date() + timedelta(days=d), time(h), tzinfo=start.tzinfo)
                 for d in range(days) for h in TICK_HOURS]
        for name, model in models.items():
            first = {}                       # (family, object_id) → 首次 p ≥ 阈值的时刻
            for at in ticks:
                state, _ = collect_scheduled(events, at, seeds, products)
                for d in model.propose(state).decisions:
                    if d.p_need is not None and d.p_need >= threshold:
                        first.setdefault((d.family, d.object_id), at)
            known = {(i.family, i.object_id) for i in injections}
            r = result[name]
            for i in injections:
                at = first.get((i.family, i.object_id))
                fam = by_family[name].setdefault(i.family, {"hits": 0, "positives": 0, "hard_false_alarms": 0})
                if i.hard_negative:
                    r["hard_negatives"] += 1
                    r["hard_false_alarms"] += at is not None
                    fam["hard_false_alarms"] += at is not None
                else:
                    r["positives"] += 1
                    fam["positives"] += 1
                    if at is not None and i.earliest <= at <= i.latest:
                        r["hits"] += 1
                        fam["hits"] += 1
                        r["lead_hours"].append((i.latest - at).total_seconds() / 3600)
            r["other_alarms"] += sum(k not in known for k in first)
    for name, r in result.items():
        r["recall"] = r["hits"] / r["positives"]
        r["lead_hours_median"] = float(np.median(r.pop("lead_hours"))) if r["hits"] else None
        r["by_family"] = by_family[name]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="data/jue_k/samples.csv")
    ap.add_argument("--model-dir", default="models/jue_k")
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--weeks", type=int, default=40)
    ap.add_argument("--start", default="2026-10-12")
    ap.add_argument("--out", default="docs/reports/jue_k")
    args = ap.parse_args()

    df = pd.read_csv(args.samples)
    with (Path(args.model_dir) / "model.pkl").open("rb") as stream:
        artifact = pickle.load(stream)
    columns = json.loads((Path(args.model_dir) / "features.json").read_text(encoding="utf-8"))["columns"]
    raw = artifact["classifier"].predict_proba(np.asarray(vectorize(features(df), columns)))[:, 1]
    cal = np.array([artifact["calibrators"][f].predict([r])[0] for f, r in zip(df.family, raw)])
    templates = {t.family: t for t in load_templates(args.templates).values()}
    attrs = [c for c in df.columns if c not in META]
    rule = np.array([min(1.0, max(0.0, float(evaluate(templates[row["family"]].rule_score,
                                                         {k: v for k, v in row.items() if k in attrs and pd.notna(v)}))))
                     for row in df.to_dict("records")])
    y = df.label.to_numpy()

    calibration, curves = {}, {}
    for family in FAMILIES:
        for split in ("test", "heldout") if family.startswith("ask") else ("test",):
            m = ((df.family == family) & (df.split == split)).to_numpy()
            calibration[f"{family}/{split}"] = {"jue_k_raw": stats(raw[m], y[m]), "jue_k": stats(cal[m], y[m]),
                                                "jue_proto_rule": stats(rule[m], y[m]), "positives": int(y[m].sum())}
            if split == "test":
                curves[family] = {"raw": reliability(raw[m], y[m]), "calibrated": reliability(cal[m], y[m]),
                                  "rule": reliability(rule[m], y[m])}

    seeds = load_seeds(args.seeds_dir)
    products = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog()).products()
    start = datetime.fromisoformat(args.start).replace(tzinfo=SHANGHAI)
    test_weeks = range(int(np.ceil(args.weeks * 0.85)), args.weeks)
    scheduled = detection(seeds, products, {"jue_k": JueK(args.model_dir, args.templates, "scheduled"),
                                            "jue_proto_rule": JueProto(args.templates, None, "scheduled")},
                          test_weeks, start, 5, 0.5)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps({"calibration": calibration, "scheduled_detection": {
        "weeks": list(test_weeks), "threshold": 0.5, **scheduled}, "ask_policies": "见 ask_policies.json"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 5, figsize=(22, 4.5))
    for axis, family in zip(axes, FAMILIES):
        for key, style, label in (("raw", "o--", "Jue-K raw"), ("calibrated", "s-", "Jue-K calibrated"),
                                  ("rule", "^:", "jue_proto rule score")):
            pts = curves[family][key]
            axis.plot([p for p, _, _ in pts], [o for _, o, _ in pts], style, label=label)
        axis.plot([0, 1], [0, 1], color="gray", lw=0.8)
        axis.set(title=f"{family} (test, n={calibration[f'{family}/test']['jue_k']['n']})", xlabel="predicted p_need",
                 ylabel="observed rate", xlim=(0, 1), ylim=(0, 1))
        axis.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(out / "reliability.png", dpi=130)

    print("== 校准（AUC / Brier / ECE）")
    for key, c in calibration.items():
        cells = "  ".join(f"{name} {c[name]['auc'] or float('nan'):.3f}/{c[name]['brier']:.3f}/{c[name]['ece']:.3f}"
                          for name in ("jue_k_raw", "jue_k", "jue_proto_rule"))
        print(f"  {key:26s} n={c['jue_k']['n']:4d} 正例 {c['positives']:4d}  {cells}")
    print("== 定时发现（6 个测试周，阈值 0.5）")
    for name, r in scheduled.items():
        print(f"  {name:15s} 召回 {r['hits']}/{r['positives']}  提前量中位数 {r['lead_hours_median']} h  "
              f"困难负样本误报 {r['hard_false_alarms']}/{r['hard_negatives']}  其他报警 {r['other_alarms']}  {r['by_family']}")
    print(f"写出 {out / 'metrics.json'}、{out / 'reliability.png'}")


if __name__ == "__main__":
    main()
