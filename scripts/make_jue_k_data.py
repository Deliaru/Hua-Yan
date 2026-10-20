"""生成 Jue-K 训练数据 data/jue_k/samples.csv（契约 ⑨），并打印每类样本数与正例数。

uv run python scripts/make_jue_k_data.py [--n-cards 2000 --weeks 40 --heldout crease_marks,low_whiteness]
追问 / 回问：程序轨迹，按卡 70/15/15 划分，另留 2 个现象为 heldout；定时三类：多周业务周在真实链路上跑出的事件，按周 28/6/6 划分
（data/week/w1 由 make_sim.py 用另一个种子生成，不参与训练，留给 run_week.py 评估）。
"""
import argparse
import random
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from huayan.contracts import SHANGHAI, KnowledgeUnit
from huayan.domain import load_seeds
from huayan.eval.week import chain_events
from huayan.events import EventLog
from huayan.jue.proto import JueProto
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.sim import make_cards, make_week
from huayan.sim.trajectory import trajectory
from huayan.sim.world import history_trials
from huayan.sim.week_events import week_rows

META = ["family", "object_type", "object_id", "at", "source_id", "label", "split"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n-cards", type=int, default=2000)
    ap.add_argument("--n-back-cards", type=int, default=3000, help="额外的应升级卡，只取回问样本")
    ap.add_argument("--n-history", type=int, default=300, help="v8：第 0 周导入的历史试样数")
    ap.add_argument("--weeks", type=int, default=40)
    ap.add_argument("--week-days", type=int, default=5)
    ap.add_argument("--heldout", default="crease_marks,low_whiteness")
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--start", default="2026-10-12")
    ap.add_argument("--out", default="data/jue_k")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds_dir)
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog())
    start = datetime.fromisoformat(args.start).replace(tzinfo=SHANGHAI)
    heldout = set(args.heldout.split(","))
    rng = random.Random(args.seed)

    # v8：第 0 周导入的历史试样（模拟 ELN 记录），试样风险的历史属性从这里来
    for trial in history_trials(seeds, make_cards(seeds, args.n_history, random.Random(args.seed + 1)), start,
                                random.Random(args.seed + 2)):
        kb.add(KnowledgeUnit(id=f"ku:trial:{trial.id}", level=3, kind="trial", title=f"试样 {trial.id}",
                             text=trial.model_dump_json(), product_id=trial.product_id, owner=trial.rd,
                             source="trial", created_at=trial.at))
    realtime = JueProto(args.templates, None, "realtime")

    def split_of(card):
        r = rng.random()
        return "heldout" if card.phenomenon in heldout else "train" if r < 0.7 else "val" if r < 0.85 else "test"

    rows = []
    for card in make_cards(seeds, args.n_cards, rng):
        split = split_of(card)
        rows += [{**row, "split": split} for row in trajectory(card, seeds, kb, realtime, rng, start)]
    # 应升级的卡只占约两成，回问样本另补：继续抽卡，只保留应升级的、只取回问样本
    extra = []
    while len(extra) < args.n_back_cards:
        extra += [c for c in make_cards(seeds, 500, rng) if c.truth_product is None]
    for k, card in enumerate(extra[:args.n_back_cards]):
        card = card.model_copy(update={"id": f"back:{k + 1}"})
        split = split_of(card)
        rows += [{**row, "split": split} for row in trajectory(card, seeds, kb, realtime, rng, start)
                 if row["family"] in ("ask_back", "trial_risk")]

    scheduled = JueProto(args.templates, None, "scheduled")
    with tempfile.TemporaryDirectory() as work:
        for w in range(args.weeks):
            items, cards, injections = make_week(seeds, start, args.week_days, random.Random(1000 + w))
            events = chain_events(items, cards, Path(work), f"w{w}")
            split = "train" if w < args.weeks * 0.7 else "val" if w < args.weeks * 0.85 else "test"
            rows += [{**row, "split": split} for row in week_rows(events, injections, seeds, kb.products(), scheduled,
                                                                    start, args.week_days, f"week:{w}")]

    df = pd.DataFrame(rows)
    df = df[META + sorted(c for c in df.columns if c not in META)]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "samples.csv", index=False, encoding="utf-8")
    table = df.groupby(["family", "split"])["label"].agg(n="size", positives="sum").unstack("split", fill_value=0)
    print(f"写出 {out / 'samples.csv'}：{len(df)} 行（种子{'占位' if seeds.placeholder else '真实'}）")
    print(table.to_string())
    for family, n in df[df.label == 1].groupby("family").size().items():
        if n < 100:
            print(f"  注意：{family} 正例 {n} < 100")


if __name__ == "__main__":
    main()
