"""觉的自进化·真实数据版本（REPLAN-v7 Q7「真实数据版本」）：世界换成 Q4.5 从真实产品目录起草、经人审定的种子
（真实的产品与适用结构），客户仍是模拟的。复用 demo_evolution 的流程，只换三处：
- 种子没有专家先验：模拟一侧把「专家先验」当作均匀分布，W2 起按同一个 λ 偏离；觉的状态仍用原种子；
- 真实词表没有预训练的觉：frozen 组全程用规则觉，evolving、unfiltered 从规则起步、每窗口后重训；
- 真实资料没有内部依据：不做授予 K3 的结构层对照。
报告写在 data/ 下，不入库（铁律 7）。

  uv run python scripts/demo_evolution_real.py --seeds-dir data/pilot/seeds --catalog data/finals/public [--focus uneven_dyeing]
"""
import argparse
import json
import random
import shutil
from pathlib import Path

import numpy as np
import yaml

import demo_evolution as evo
from huayan.domain import load_seeds
from huayan.jue.jue_k import JueK
from huayan.sim.cards import make_card, sample_slots, shifted_world
from huayan.ui.server import Api, T0
from huayan.clock import SimClock

WORK = Path("data/jue_evolution_real")


def config_file(work, seeds_dir, catalog):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir=seeds_dir, realtime_model="jue_proto", run_root=str(work / "runs"),
                  sources=[{"name": "公开资料", "kind": "public", "root": catalog}])
    path = work / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def uniform(seeds):
    """模拟一侧的「专家先验」：种子没有先验时按均匀分布。"""
    values = {s.id: s.values for s in seeds.slots}
    return seeds.model_copy(update={"phenomena": [p.model_copy(update={"slot_priors": p.slot_priors or {
        s: {v: 1.0 for v in values[s]} for s in values}}) for p in seeds.phenomena]})


def make_batch(seeds, n, lam, seed, focus):
    world = shifted_world(seeds, lam, random.Random(seed))
    customers = [a.id for a in seeds.actors if a.role == "customer"]
    batch = {}
    for w in evo.WINDOWS:
        src, rng = (seeds if w == "W1" else world), random.Random(f"{seed}:{w}")
        phen = {p.id: p for p in src.phenomena}
        batch[w] = [make_card(f"card:{w}:{i}", p, sample_slots(p, src, rng), rng.choice(customers), src, rng)
                    for i in range(n) for p in [phen[focus] if i % 2 == 0 else rng.choice(src.phenomena)]]
    return batch


class Arm(evo.Arm):
    def __init__(self, name, config, seed, work):        # 不编译模拟资料、不确认 C4
        self.name, self.seed, self.work = name, seed, work
        self.api = Api(None, str(config), SimClock(T0))
        self.api.build()
        self.app = self.api.app
        self.snaps = evo.defaultdict(list)
        self.cards, self.windows, self.rows, self.cells = {}, {}, [], {}


def merged(previous, out, templates, meter, pooled):
    """上一个是规则觉时没有可沿用的格，直接用新模型（没胜过规则的格 JueK 自己退回规则）。"""
    if isinstance(previous, JueK):
        return original_merged(previous, out, templates, meter, pooled)
    new = JueK(out, templates, "realtime", meter)
    if pooled and "ask_slot|L0" in new.models:
        new.models["ask_slot|L1"], new.columns["ask_slot|L1"] = new.models["ask_slot|L0"], new.columns["ask_slot|L0"]
    return new


original_merged, evo.merged = evo.merged, merged


def run(n, lam, seed, config, focus):
    work = WORK / f"seed{seed}"
    work.mkdir(parents=True)
    arms = {name: Arm(name, config, seed, work) for name in evo.ARMS}
    seeds = arms["frozen"].app.seeds
    templates = arms["frozen"].app.config["templates_dir"]
    batch = make_batch(uniform(seeds), n, lam, seed, focus)
    rd_required = {p.id: p.required_slots for p in arms["frozen"].app.kb.view(evo.RD).phenomena}
    l0_required = {p.id: p.required_slots for p in arms["frozen"].app.kb.view(evo.CUSTOMER).phenomena}
    report = {"seed": seed, "windows": {}, "cells": {}}
    for w in evo.WINDOWS:
        for arm in arms.values():
            for i, card in enumerate(batch[w]):
                arm.visit(card, w, accompanied=i % 2 == 1)
        report["windows"][w] = {name: evo.window_metrics(arm, w, rd_required, l0_required) for name, arm in arms.items()}
        for name in ("evolving", "unfiltered"):
            arms[name].retrain(w, templates)
            report["cells"].setdefault(name, {})[w] = {c: s["scored_by"] for c, s in arms[name].cells[w].items()}
        print(f"seed {seed} {w}", {a: report["windows"][w][a]["handled_rate"] for a in evo.ARMS}, flush=True)
    return report


def page(r, seeds):
    runs = r["runs"]
    metrics = [m for m in evo.METRICS if m[0] != "complete_l0_rate"]
    mean = lambda w, arm, key: (lambda v: "—" if not v else f"{np.mean(v):.3f}")(
        [x["windows"][w][arm][key] for x in runs if x["windows"][w][arm][key] is not None])
    lines = ["# 觉的自进化·真实产品结构（本地，不入库）", "",
             f"> 世界：从真实产品目录起草、模拟认领的种子（产品 {len(seeds.products)}、现象 {len(seeds.phenomena)}、槽位 {len(seeds.slots)}）；"
             f"客户是模拟的，种子没有专家先验，模拟一侧按均匀分布当先验，W2 起偏离 λ = {r['lambda']}。"
             f"每窗口 {r['n_per_window']} 位客户（一半是 {r['focus']}），种子 {', '.join(map(str, r['seeds']))}。",
             "> frozen：规则觉（真实词表没有预训练的觉）；evolving：从规则起步，每窗口后按「家族 × 判断层」过滤重训；"
             "unfiltered：不按层过滤。没有内部资料，不做授予 K3 的结构层对照。", "",
             "## 各组均值（按种子平均）", "",
             "| 窗口 | 组 | " + " | ".join(name for _, name, _ in metrics) + " |", "|---|---|" + "---|" * len(metrics)]
    for w in evo.WINDOWS:
        for arm in evo.ARMS:
            lines.append(f"| {w} | {arm} | " + " | ".join(mean(w, arm, k) for k, _, _ in metrics) + " |")
    for a, b, title in (("evolving", "frozen", "进化有没有用：evolving − frozen"),
                        ("unfiltered", "evolving", "不按层过滤会怎样：unfiltered − evolving")):
        lines += ["", f"## {title}（各种子平均［最小，最大］）", "",
                  "| 窗口 | " + " | ".join(name for _, name, _ in metrics) + " |", "|---|" + "---|" * len(metrics)]
        lines += [f"| {w} | " + " | ".join(evo._diff(runs, w, a, b, k) for k, _, _ in metrics) + " |" for w in evo.WINDOWS]
    cells = {w: {arm: sum(x["cells"][arm][w].get(c) == "jue_k" for x in runs for c in ("ask_slot|L0", "ask_slot|L1"))
                 for arm in ("evolving", "unfiltered")} for w in evo.WINDOWS}
    lines += ["", f"每窗口重训后换上 Jue-K 的追问格数（L0、L1 两格 × 种子数 {len(runs) * 2}）：" +
              "；".join(f"{w} evolving {c['evolving']}、unfiltered {c['unfiltered']}" for w, c in cells.items()) + "。", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds-dir", required=True)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--focus", default="uneven_dyeing")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--lam", type=float, default=0.6)
    ap.add_argument("--seeds", default="0,1,2,3,4")
    args = ap.parse_args()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    config = config_file(WORK, args.seeds_dir, args.catalog)
    runs = [run(args.n, args.lam, int(seed), config, args.focus) for seed in args.seeds.split(",")]
    report = {"lambda": args.lam, "n_per_window": args.n, "focus": args.focus,
              "seeds": [r["seed"] for r in runs], "runs": runs}
    (WORK / "evolution.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "README.md").write_text(page(report, load_seeds(args.seeds_dir)), encoding="utf-8")
    print(page(report, load_seeds(args.seeds_dir)))


if __name__ == "__main__":
    main()
