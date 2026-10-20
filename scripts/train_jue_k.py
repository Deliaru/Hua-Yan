"""训练 Jue-K：按「家族 × 判断层」每格一个 HistGradientBoostingClassifier + 验证集 isotonic 校准（huayan.jue.train.fit）。
D20：每格在测试集（不参与训练与校准）的同一组合上与模板规则分比较，配对 bootstrap（500 次）下
AUC 差的 95% 区间下界 > 0 且 Brier 差的上界 < 0 才算赢；只保存赢了的格，JueK 对没有模型的格回落规则打分。
比较结果写进 metrics.json 与模型卡。

样本里没有 judge_level 的行（v7 之前生成）：追问来自业务员陪同的程序轨迹（trajectory.py 的 sales_id），取 L1；
回问取对象的 layer；其余取模板签字人所在层。模拟样本的标签来自需求卡真值，结果层级取判断层。

uv run python scripts/train_jue_k.py [--samples data/jue_k/samples.csv --out models/jue_k]
"""
import argparse
import math
from pathlib import Path

import pandas as pd

from huayan.contracts import JueObject
from huayan.jue.proto import judge_level, load_templates
from huayan.jue.train import fit

META = ["family", "object_type", "object_id", "at", "source_id", "label", "split"]
SOURCES = {"ask_slot": "程序轨迹（需求卡 + 随机追问策略 + 抽取噪声）", "ask_back": "程序轨迹结束时构造的需求单（应升级的卡）",
           "opportunity": "多周模拟业务周在真实链路上跑出的事件", "knowledge_conflict": "多周模拟业务周在真实链路上跑出的事件",
           "leak_risk": "多周模拟业务周在真实链路上跑出的事件",
           "trial_risk": "程序轨迹结束时构造的待试样需求单（应升级的卡），历史属性来自第 0 周导入的模拟历史试样"}
LABELS = {"ask_slot": "补上 / 改正真实值后，最终推荐是否由错变对；或需求应升级而该槽位是研发必问信息", "ask_back": "补上 / 改正真实值后，本层转化对照命中集合是否变化",
          "opportunity": "落在非困难负样本注入的 [earliest, latest] 内、object_id 一致（注入外、≥ 2 位客户升级的主题不进样本）",
          "knowledge_conflict": "同 opportunity", "leak_risk": "同 opportunity",
          "trial_risk": "按模拟世界的试样规律（sim/world.py），这张单试样会因需求条件缺失而失败"}


def sample_rows(df: pd.DataFrame, templates_dir: str) -> list[dict]:
    templates = {t.family: t for t in load_templates(templates_dir).values()}
    attrs = [c for c in df.columns if c not in META]
    rows = []
    for r in df.to_dict("records"):
        values = {k: r[k] for k in attrs if not (isinstance(r[k], float) and math.isnan(r[k]))}
        if r["object_type"] == "slot" and "judge_level" not in values:     # v7 之前生成的样本
            values["judge_level"] = 1 if values["layer"] == 1 else int(values["layer"])
            values["failed_on"] = False
        obj = JueObject(object_id=r["object_id"], object_type=r["object_type"], attrs=values)
        level = judge_level(templates[r["family"]], obj)
        rows.append({"family": r["family"], "object_type": r["object_type"], "object_id": r["object_id"],
                     "attrs": values, "label": int(r["label"]), "judge_level": level, "level": level, "split": r.get("split")})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="data/jue_k/samples.csv")
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--out", default="models/jue_k")
    args = ap.parse_args()

    rows = sample_rows(pd.read_csv(args.samples), args.templates)
    summary = fit(rows, args.templates, args.out)
    (Path(args.out) / "model_card.md").write_text(model_card(summary), encoding="utf-8")
    nan = float("nan")
    for cell, s in summary.items():
        if "test_auc" not in s:
            print(f"{cell:22s} train {s['n']['train']:5d}  样本不够 → rule")
            continue
        print(f"{cell:22s} train {s['n']['train']:5d}（正例 {s['positives']['train']:4d}）  test AUC {s['test_auc'] or nan:.3f}"
              f" / 规则 {s['test_rule_auc'] or nan:.3f}  Brier {s['test_brier']:.3f} / 规则 {s['test_rule_brier']:.3f}"
              f"  AUC 差 95% 区间 {s['test_auc_diff_ci95']}  heldout AUC {s['heldout_auc'] or nan:.3f} / 规则 {s['heldout_rule_auc'] or nan:.3f}"
              f"  → {s['scored_by']}")
    print(f"产物写入 {args.out}")


def model_card(summary: dict) -> str:
    fam = lambda cell: cell.split("|")[0]
    rows = "\n".join(f"| `{c}` | {SOURCES[fam(c)]} | {LABELS[fam(c)]} | {s['n']['train']} / {s['n']['val']} / {s['n']['test']} / {s['n']['heldout']} "
                     f"| {s['positives']['train']} / {s['positives']['val']} / {s['positives']['test']} / {s['positives']['heldout']} |"
                     for c, s in summary.items())
    num = lambda x: "—" if x is None else f"{x:.3f}"
    ci = lambda c: "—" if c is None else f"[{c[0]:+.3f}, {c[1]:+.3f}]"
    choice = "\n".join(f"| `{c}` | {num(s.get('test_auc'))} | {num(s.get('test_rule_auc'))} | {ci(s.get('test_auc_diff_ci95'))} "
                       f"| {num(s.get('test_brier'))} | {num(s.get('test_rule_brier'))} | {num(s.get('heldout_auc'))} / {num(s.get('heldout_rule_auc'))} "
                       f"| {'Jue-K' if s['scored_by'] == 'jue_k' else '规则（' + s.get('reason', '回落') + '）'} |"
                       for c, s in summary.items())
    return f"""# Jue-K v7 模型卡

> 由 `scripts/train_jue_k.py`（训练函数在 `huayan.jue.train`）生成。评估结果见 `docs/reports/jue_k/`。

## 是什么
觉的训练版：按「家族 × 判断层」**每格一个** `HistGradientBoostingClassifier`（150 轮、深度 3、叶子至少 30 条、L2 1.0，无超参数搜索），
对「此刻 × 模板 × 对象」中前置条件通过的组合输出「需要决策」的概率，再在验证集上拟合 isotonic 校准层。
判断层 = 这个决策代谁判断：追问在客户自助会话里是 L0、陪同会话里是 L1；回问是需求单所在层（产品经理 L2、研发 L3）；其余取签字人所在层。
每格只用同家族、同判断层、且结果层级不高于该层的行训练（`rows_for`），更高层的判断不会经共用分类器影响下层的分数。
特征见 `features.json`（每格一组列；`huayan.jue.features.build`，训练与推理共用）。
前置条件与紧急度沿用原型模板（紧急度是规则，不学习）。只做本地推理，不调用任何大模型。
`model.pkl` 随仓库提交，克隆后无需重训即可运行（scikit-learn 版本以 `uv.lock` 为准）。

## 数据（全部为模拟数据）
种子为占位数据（大模型按印染行业常识编写，非任何企业资料）；需求卡、对话轨迹、业务周事件全部由程序生成，不调用大模型。

| 类型 | 数据来源 | 标签（事后有用性 / 注入窗口） | 样本数 train / val / test / heldout | 正例数 |
|---|---|---|---|---|
{rows}

- 追问、回问按需求卡划分 70 / 15 / 15，另留 2 个现象（`crease_marks`、`low_whiteness`）为 heldout，不参与训练与校准；定时三类按业务周划分 28 / 6 / 6；`data/week/w1`（另一个种子）不参与训练，由 `scripts/run_week.py` 评估。
- 回问样本另补了 3,000 张应升级的卡（只取回问样本）；种子 `tr:50`～`tr:57` 是为回问补的挂在槽位取值上的 L3 转化对照。

## 打分来源（D20：新模型赢的用模型，输的回落规则）
测试集上同一组合、配对 bootstrap 500 次：校准后 AUC 差的 95% 区间下界 > 0、且 Brier 差的上界 < 0 才算赢（heldout 为未见现象，只列出不判胜负）。只保存赢了的格；
`JueK` 对没有模型的格用模板 `rule_score` 打分，逐条标 `scored_by: rule`。训练行少于 100 的格不训练。规则分不是校准概率，Brier 对它偏严，如实列出。

| 家族 × 判断层 | Jue-K AUC | 规则 AUC | AUC 差 95% 区间 | Jue-K Brier | 规则 Brier | 未见现象 AUC（Jue-K / 规则） | 最终 |
|---|---|---|---|---|---|---|---|
{choice}

## 适用范围
占位种子下的追问、回问与三类定时发现的打分；链路沿用 `config/app.yaml`。换真实种子后用 `scripts/make_jue_k_data.py` 与本脚本重训。
输出是校准概率，阈值按代价取 1 / (1 + 漏问代价 / 多问代价)：实时追问建议 0.15 左右（原型的 0.5 会几乎不问），定时三类 0.5。

## 已知局限
- 标签由需求卡真值或注入清单算出，是受控的模拟数据，不代表真实业务分布；接入真实对话后需用真实处置结果（`jue_samples.jsonl`）重新校准。
- 现象不进特征（独热会让模型记住现象），未见现象上的追问不优于规则；换种子必须覆盖全部现象。
- 追问只在前置条件通过的组合上打分：已填的槽位不进追问，模型不负责「对低置信度的值复问」。
- 抽取噪声中填错的置信度（0.4～0.6）与填对的（0.7～0.95）不重叠，比真实抽取更容易分辨。
- 回问的正例主要取决于该现象下槽位取值的先验（模型看不到真实值），且只来自挂在槽位取值上的少数几条转化对照。
- 定时三类的事件来自真实链路（`eval.week.chain_events`：抽取规则、Jev 桩、转译规则模式），与线上定时发现共用状态构建；但注入与困难负样本的模式固定，正例少，模型容易学到模式本身。
- 升级事件里的 `p_none` 来自 Jev 桩；换成 OneJev 或大模型降级后，机会汇聚的 `mean_p_none` 分布会变，需要用对应配置重跑样本。
- 知识库检索目前把全部排名里被拦截的知识都计入 `n_blocked`（每次检索几十条），泄露风险主要靠「要求讲原理的次数」区分；检索口径改了之后要重新生成样本并重训。
- 转化对照匹配的字符二元组规则会让相近取值误命中（如「溢流染色机」命中「气流染色机」），影响回问的取值区分度。
"""


if __name__ == "__main__":
    main()
