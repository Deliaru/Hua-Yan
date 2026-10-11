"""单卡对照（WP-E2）：跑一次失真对照（同 run_distortion.py，带逐轮轨迹），按固定规则选卡，写出
docs/reports/distortion/（失真报告）、docs/reports/single_card/（metrics.json、README.md）与开发用 web/src/fixtures/single_card.json。
零成本：抽取、转译为规则，觉按 config/eval/distortion.yaml 用规则原型或本地 Jue-K，大模型调用为 0；同一种子重跑结果一致。

uv run python scripts/make_single_card.py
"""
import json
from pathlib import Path

from huayan.eval.single_card import STATS_GROUPS, pick, single_card
from run_distortion import parser, run

LABELS = {"completeness": "关键信息完整率", "returned": "研发需退回比例", "asks": "平均追问次数", "backs": "平均回问次数"}


def main():
    ap = parser()
    ap.add_argument("--single-out", default="docs/reports/single_card")
    ap.add_argument("--fixture", default="web/src/fixtures/single_card.json")
    args = ap.parse_args()

    cards, df, metrics, traces = run(args, trace=True)
    card, selection = pick(cards, df)
    stats = {g: metrics["metrics"][g] for g in STATS_GROUPS} | {"n_cards": metrics["n_cards"], "selection": selection}
    data = single_card(card, traces[card.id], stats)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    out = Path(args.single_out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(text, encoding="utf-8")
    Path(args.fixture).write_text(text, encoding="utf-8")
    (out / "README.md").write_text(_readme(data, metrics), encoding="utf-8")
    print(f"选中 {card.id}（{selection['n_eligible']} / {selection['n_same_phenomenon']} 张同现象卡满足条件）；"
          f"写出 {out}、{args.fixture}")


def _readme(d: dict, metrics: dict) -> str:
    sel, h, g2 = d["stats"]["selection"], d["huayan"], d["one_shot"]
    asked = [r["asked"] for r in h["rounds"] if r["asked"]]
    rows = "\n".join(f"| {label} | " + " | ".join(_fmt(k, d["stats"][g][k]) for g in STATS_GROUPS) + " |"
                     for k, label in LABELS.items())
    jue = metrics["jue"]
    return f"""# 单卡对照

> 全部为模拟数据。由 `scripts/make_single_card.py` 生成，与 `docs/reports/distortion/` 是**同一次运行**（{d['stats']['n_cards']} 张卡）；
> 觉：`{jue['model']}`，追问阈值 {jue['ask_threshold']}、回问阈值 {jue['back_threshold']}；大模型调用 {metrics['calls']['llm']} 次。展示数据见 `metrics.json`。

## 选卡（规则写死，不挑）

{sel['rule']}。{sel['n_cards']} 张卡中同现象 {sel['n_same_phenomenon']} 张，**满足条件 {sel['n_eligible']} 张**，选中 `{d['card_id']}`。

## 这张卡

- 客户知道的必问信息：{'、'.join(f'{k}={v}' for k, v in d['truth'].items())}
- **一次性翻译**：只听开场白「{g2['turns'][0]['text']}」，{'研发退回（' + g2['return_reason'] + '）' if g2['returned'] else '研发不退回'}。
- **化言**：觉提示追问 {'、'.join(asked) or '无'}，回问 {'、'.join(b['slot'] for b in h['back_asks']) or '无'}，{'研发退回（' + h['return_reason'] + '）' if h['returned'] else '研发不退回'}。

## 底部统计（{d['stats']['n_cards']} 张卡，取自同一次失真对照）

| 指标 | {' | '.join(STATS_GROUPS)} |
|---|---|---|---|
{rows}

## 必须说明

1. **单卡是按固定规则选出的例子**，不代表每张卡都这样；证据是上面的统计。
2. G1 的转述噪声是假设参数（`config/eval/distortion.yaml`），见 `docs/reports/distortion/README.md`。
3. 模板客户与规则抽取共用种子里的口语说法表，G3 的槽位错误率偏乐观。
4. 规则打分的追问、回问在界面上标「规则」，不显示为概率。
"""


def _fmt(key: str, v) -> str:
    return "—" if v is None else f"{v:.2f}" if key in ("asks", "backs") else f"{v:.1%}"


if __name__ == "__main__":
    main()
