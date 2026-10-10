"""生成需求卡 data/sim/cards.jsonl 与模拟业务周 data/week/w1/，并打印统计。"""
import argparse
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

from huayan.contracts import SHANGHAI
from huayan.domain import load_seeds
from huayan.sim import make_cards, make_week, to_jsonl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n-cards", type=int, default=1500)
    ap.add_argument("--week-days", type=int, default=5)
    ap.add_argument("--seeds-dir", default="seeds")
    ap.add_argument("--start", default="2026-10-12", help="业务周第一天（周一）")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds_dir)
    cards = make_cards(seeds, args.n_cards, random.Random(args.seed))
    start = datetime.fromisoformat(args.start).replace(tzinfo=SHANGHAI)
    items, week_cards, injections = make_week(seeds, start, args.week_days, random.Random(args.seed))

    out = Path(args.out)
    (out / "sim").mkdir(parents=True, exist_ok=True)
    (out / "sim" / "cards.jsonl").write_text(to_jsonl(cards), encoding="utf-8", newline="\n")
    week = out / "week" / "w1"
    week.mkdir(parents=True, exist_ok=True)
    for name, rows in [("script", items), ("cards", week_cards), ("injections", injections)]:
        (week / f"{name}.jsonl").write_text(to_jsonl(rows), encoding="utf-8", newline="\n")

    phen = Counter(c.phenomenon for c in cards)
    print(f"需求卡 {len(cards)} 张（种子{'占位' if seeds.placeholder else '真实'}），现象分布：{dict(sorted(phen.items()))}")
    print(f"  应升级比例 {sum(c.truth_product is None for c in cards) / len(cards):.1%}；"
          f"含说不清槽位 {sum(bool(c.unknown_slots) for c in cards) / len(cards):.1%}；"
          f"懂化学 {sum(c.chem_savvy for c in cards) / len(cards):.1%}，其中要原理 {sum(c.wants_mechanism for c in cards)}")
    kinds = Counter(i.kind for i in items)
    print(f"业务周 {args.week_days} 天：剧本 {len(items)} 条 {dict(kinds)}；会话应升级 "
          f"{sum(c.truth_product is None for c in week_cards)}/{len(week_cards)}")
    for inj in injections:
        tag = "困难负样本" if inj.hard_negative else "注入"
        print(f"  [{tag}] {inj.family:18s} {inj.object_id}  onset {inj.onset:%m-%d %H:%M}  "
              f"窗口 {inj.earliest:%m-%d %H:%M} ~ {inj.latest:%m-%d %H:%M}")


if __name__ == "__main__":
    main()
