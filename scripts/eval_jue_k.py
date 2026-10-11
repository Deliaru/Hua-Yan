"""评估 Jue-K → docs/reports/jue_k/：
1. 校准（主结果）：每类在 test（追问 / 回问另加 heldout）上的 AUC、Brier、ECE，校准前后与原型规则分数对照；五类可靠性图；
2. 定时发现：6 个测试周（与训练同一生成方式、在真实链路上跑出事件、未参与训练）上，Jue-K 与原型规则模式按 WP-E 口径比较窗口内发现、提前量、困难负样本误报。
3. 学习曲线（--parts learning_curve，不依赖 1、2 的样本与模型）：真实世界的槽位先验偏离专家估计 λ 时，
   追问上 Jue-K 随训练会话数的 AUC / Brier，对照只用专家先验的信息价值规则（p_fix）。λ 是假设，所以整条扫描都列出。
ECE 用 10 个等频分箱、可靠性图用 10 个等宽分箱，做法参照 JUE-r2 eval/calibration.py。

uv run python scripts/eval_jue_k.py [--parts main,learning_curve]（main 先跑 make_jue_k_data.py、train_jue_k.py；追问操作点见 eval_ask_policies.py）
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
from huayan.jue.features import vectorize
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto
from huayan.jue.state import collect_scheduled
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.sim import make_cards, make_week, shifted_world
from huayan.sim.trajectory import trajectory
from huayan.sim.week_events import TICK_HOURS
from train_jue_k import features, make_classifier, rule_scores

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


def learning_curve(seeds, kb, templates: str, start: datetime, lams=(0.0, 0.25, 0.5, 1.0),
                   sizes=(100, 300, 1000, 3000), n_test=1500, repeats=3) -> dict:
    """每个 λ、每次重复：一个偏离世界（种子 42 + r），训练池按卡的顺序取前 N 张，测试另抽 n_test 张；只看追问。
    Jue-K 与线上同一套特征与分类器（未另做 isotonic 校准）；规则 = p_fix（专家先验下的信息价值）与现模板规则分。"""
    model = JueProto(templates, None, "realtime")

    def rows(world, n, seed):
        rng, out = random.Random(seed), []
        for k, card in enumerate(make_cards(world, n, rng)):
            out += [{**row, "card": k} for row in trajectory(card, seeds, kb, model, rng, start) if row["family"] == "ask_slot"]
        return pd.DataFrame(out)

    result = {}
    for lam in lams:
        runs = []
        for r in range(repeats):
            world = shifted_world(seeds, lam, random.Random(42 + r))
            pool, test = rows(world, max(sizes), 1000 * r + 1), rows(world, n_test, 1000 * r + 2).drop(columns="card")
            y = test.label.to_numpy()
            run = {"p_fix": stats(test.p_fix.to_numpy(), y), "template_rule": stats(rule_scores(test, templates), y), "jue_k": {}}
            for n in sizes:
                train = pool[pool.card < n].drop(columns="card")
                feats = features(train)
                columns = sorted({k for f in feats for k in f})
                clf = make_classifier().fit(np.asarray(vectorize(feats, columns)), train.label)
                run["jue_k"][n] = stats(clf.predict_proba(np.asarray(vectorize(features(test), columns)))[:, 1], y)
            runs.append(run)
        mean = lambda get: float(np.mean([get(run) for run in runs]))
        result[str(lam)] = {
            "p_fix": {k: mean(lambda run: run["p_fix"][k]) for k in ("auc", "brier")},
            "template_rule": {"auc": mean(lambda run: run["template_rule"]["auc"])},
            "jue_k": {str(n): {k: mean(lambda run: run["jue_k"][n][k]) for k in ("auc", "brier")} for n in sizes},
            "jue_k_range": {str(n): [min(run["jue_k"][n]["auc"] for run in runs), max(run["jue_k"][n]["auc"] for run in runs)]
                            for n in sizes}}
        print(f"λ={lam}: p_fix 规则 AUC {result[str(lam)]['p_fix']['auc']:.3f} / Brier {result[str(lam)]['p_fix']['brier']:.3f}  "
              + "  ".join(f"N={n} {v['auc']:.3f}/{v['brier']:.3f}" for n, v in result[str(lam)]["jue_k"].items()), flush=True)
    return {"lams": list(lams), "sizes": list(sizes), "n_test_cards": n_test, "repeats": repeats, "by_lam": result}


def _plot_learning_curve(lc: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for j, lam in enumerate(lc["lams"]):
        r = lc["by_lam"][str(lam)]
        for axis, key in zip(axes, ("auc", "brier")):
            axis.plot(lc["sizes"], [r["jue_k"][str(n)][key] for n in lc["sizes"]], "o-", color=f"C{j}", label=f"Jue-K, λ={lam}")
            axis.axhline(r["p_fix"][key], color=f"C{j}", ls="--", lw=1, label=f"VOI rule (expert prior), λ={lam}")
    for axis, key in zip(axes, ("AUC (higher is better)", "Brier (lower is better)")):
        axis.set(xscale="log", xlabel="training sessions (dispositions collected)", ylabel=key)
        axis.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    fig.suptitle("ask_slot: Jue-K learns from outcomes vs. value-of-information rule on expert priors; "
                 "λ = how far the world deviates from expert priors", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", default="main,learning_curve", help="main = 校准与定时发现；learning_curve = 学习曲线")
    ap.add_argument("--samples", default="data/jue_k/samples.csv")
    ap.add_argument("--model-dir", default="models/jue_k")
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--weeks", type=int, default=40)
    ap.add_argument("--start", default="2026-10-12")
    ap.add_argument("--out", default="docs/reports/jue_k")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if "learning_curve" in args.parts:
        seeds = load_seeds(args.seeds_dir)
        lc = learning_curve(seeds, KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog()), args.templates,
                            datetime.fromisoformat(args.start).replace(tzinfo=SHANGHAI))
        (out / "learning_curve.json").write_text(json.dumps(lc, ensure_ascii=False, indent=2), encoding="utf-8")
        _plot_learning_curve(lc, out / "learning_curve.png")
        print(f"写出 {out / 'learning_curve.json'}、{out / 'learning_curve.png'}")
    if "main" in args.parts:
        evaluate(args, out)


def evaluate(args, out: Path) -> None:
    df = pd.read_csv(args.samples)
    with (Path(args.model_dir) / "model.pkl").open("rb") as stream:
        artifact = pickle.load(stream)
    columns = json.loads((Path(args.model_dir) / "features.json").read_text(encoding="utf-8"))["columns"]
    raw = artifact["classifier"].predict_proba(np.asarray(vectorize(features(df), columns)))[:, 1]
    rule = rule_scores(df, args.templates)
    # 回落规则的类没有校准器：「jue_k」一栏即最终使用的分数（规则），与 JueK 推理一致
    cal = np.array([artifact["calibrators"][f].predict([r])[0] if f in artifact["calibrators"] else q
                    for f, r, q in zip(df.family, raw, rule)])
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
