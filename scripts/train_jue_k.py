"""训练 Jue-K：一个 HistGradientBoostingClassifier（五类样本混在一起）+ 按 family 在验证集上拟合 isotonic 校准。
做法参照 JUE-r2 qmodel/v0/train.py（梯度提升 + 验证集 isotonic），数据与特征为本项目重写。
D20：每类在测试集（不参与训练与校准）的同一组合上与模板规则分比较，AUC 更高且 Brier 更低才算赢；
验证集同时用于拟合校准层，样本又少，不用来判胜负（回问在验证集上 0.60、测试集上 0.50）。只保存赢了的类的校准器，
JueK 对没有校准器的类回落规则打分（huayan.jue.jue_k）。比较结果写进 metrics.json 与模型卡。

uv run python scripts/train_jue_k.py [--samples data/jue_k/samples.csv --out models/jue_k]
"""
import argparse
import json
import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from huayan.contracts import JueObject
from huayan.jue.expr import evaluate
from huayan.jue.features import build, vectorize
from huayan.jue.proto import load_templates

META = ["family", "object_type", "object_id", "at", "source_id", "label", "split"]
SOURCES = {"ask_slot": "程序轨迹（需求卡 + 随机追问策略 + 抽取噪声）", "ask_back": "程序轨迹结束时构造的需求单（应升级的卡）",
           "opportunity": "多周模拟业务周在真实链路上跑出的事件", "knowledge_conflict": "多周模拟业务周在真实链路上跑出的事件",
           "leak_risk": "多周模拟业务周在真实链路上跑出的事件"}
LABELS = {"ask_slot": "补上 / 改正真实值后，最终推荐是否由错变对", "ask_back": "补上 / 改正真实值后，本层转化对照命中集合是否变化",
          "opportunity": "落在非困难负样本注入的 [earliest, latest] 内、object_id 一致（注入外、≥ 2 位客户升级的主题不进样本）",
          "knowledge_conflict": "同 opportunity", "leak_risk": "同 opportunity"}


def features(df: pd.DataFrame) -> list[dict[str, float]]:
    attrs = [c for c in df.columns if c not in META]
    out = []
    for row in df.to_dict("records"):
        values = {k: row[k] for k in attrs if not (isinstance(row[k], float) and math.isnan(row[k]))}
        out.append(build(JueObject(object_id=row["object_id"], object_type=row["object_type"], attrs=values), row["family"]))
    return out


def rule_scores(df: pd.DataFrame, templates_dir: str) -> np.ndarray:
    """每行用同 family 模板的 rule_score 打分（截断到 [0,1]），即 jue_proto 规则模式在同一组合上的分数。"""
    templates = {t.family: t for t in load_templates(templates_dir).values()}
    attrs = [c for c in df.columns if c not in META]
    return np.array([min(1.0, max(0.0, float(evaluate(templates[row["family"]].rule_score,
                                                         {k: v for k, v in row.items() if k in attrs and pd.notna(v)}))))
                     for row in df.to_dict("records")])


def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="data/jue_k/samples.csv")
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--out", default="models/jue_k")
    args = ap.parse_args()

    df = pd.read_csv(args.samples)
    rule = rule_scores(df, args.templates)
    feats = features(df)
    columns = sorted({k for f, s in zip(feats, df.split) if s == "train" for k in f})
    x, y = np.asarray(vectorize(feats, columns)), df.label.to_numpy()
    train, val, test = (df.split == "train").to_numpy(), (df.split == "val").to_numpy(), (df.split == "test").to_numpy()

    classifier = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=0).fit(x[train], y[train])
    raw = classifier.predict_proba(x)[:, 1]
    calibrators, summary = {}, {}
    for family in sorted(df.family.unique()):
        fam = (df.family == family).to_numpy()
        v, t, h = fam & val, fam & test, fam & (df.split == "heldout").to_numpy()
        calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw[v], y[v])
        cal = calibrator.predict(raw[v])
        auc, rule_auc = _auc(y[t], raw[t]), _auc(y[t], rule[t])
        brier, rule_brier = (float(brier_score_loss(y[t], calibrator.predict(raw[t]))),
                             float(brier_score_loss(y[t], rule[t])))
        wins = auc is not None and rule_auc is not None and auc > rule_auc and brier < rule_brier
        if wins:
            calibrators[family] = calibrator
        summary[family] = {
            "n": {s: int((fam & (df.split == s).to_numpy()).sum()) for s in ("train", "val", "test", "heldout")},
            "positives": {s: int(y[fam & (df.split == s).to_numpy()].sum()) for s in ("train", "val", "test", "heldout")},
            "val_auc": _auc(y[v], raw[v]), "val_brier_raw": float(brier_score_loss(y[v], raw[v])),
            "val_brier_calibrated": float(brier_score_loss(y[v], cal)),
            "test_auc": auc, "test_rule_auc": rule_auc, "test_brier": brier, "test_rule_brier": rule_brier,
            "heldout_auc": _auc(y[h], raw[h]) if h.any() else None, "heldout_rule_auc": _auc(y[h], rule[h]) if h.any() else None,
            "scored_by": "jue_k" if wins else "rule"}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "model.pkl").open("wb") as stream:
        pickle.dump({"classifier": classifier, "calibrators": calibrators}, stream)
    (out / "features.json").write_text(json.dumps({
        "columns": columns, "encoding": "数值属性原值；布尔 0/1；slot / role / family / object_type 独热（phenomenon 不进特征）；缺失与未见取值记 0",
        "sklearn": sklearn.__version__}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps({"samples": args.samples, "rows": len(df), "by_family": summary},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "model_card.md").write_text(model_card(summary, len(columns)), encoding="utf-8")
    for family, s in summary.items():
        nan = float("nan")
        print(f"{family:20s} train {s['n']['train']:5d}（正例 {s['positives']['train']:4d}）  test AUC {s['test_auc'] or nan:.3f}"
              f" / 规则 {s['test_rule_auc'] or nan:.3f}  Brier {s['test_brier']:.3f} / 规则 {s['test_rule_brier']:.3f}"
              f"  heldout AUC {s['heldout_auc'] or nan:.3f} / 规则 {s['heldout_rule_auc'] or nan:.3f}  → {s['scored_by']}")
    print(f"产物写入 {out}（特征 {len(columns)} 个）")


def model_card(summary: dict, n_features: int) -> str:
    rows = "\n".join(f"| `{f}` | {SOURCES[f]} | {LABELS[f]} | {s['n']['train']} / {s['n']['val']} / {s['n']['test']} / {s['n']['heldout']} "
                     f"| {s['positives']['train']} / {s['positives']['val']} / {s['positives']['test']} / {s['positives']['heldout']} |"
                     for f, s in summary.items())
    num = lambda x: "—" if x is None else f"{x:.3f}"
    choice = "\n".join(f"| `{f}` | {num(s['test_auc'])} | {num(s['test_rule_auc'])} | {num(s['test_brier'])} "
                       f"| {num(s['test_rule_brier'])} | {num(s['heldout_auc'])} / {num(s['heldout_rule_auc'])} "
                       f"| {'Jue-K' if s['scored_by'] == 'jue_k' else '规则（回落）'} |"
                       for f, s in summary.items())
    return f"""# Jue-K v5 模型卡

> 由 `scripts/train_jue_k.py` 生成。评估结果见 `docs/reports/jue_k/`。

## 是什么
觉的训练版：**一个** `HistGradientBoostingClassifier`（300 轮、学习率 0.1、无超参数搜索），对「此刻 × 模板 × 对象」中前置条件通过的组合输出「需要决策」的概率；
再按决策类型在验证集上各拟合一个 isotonic 校准层。特征 {n_features} 个，见 `features.json`（`huayan.jue.features.build`，训练与推理共用）。
前置条件与紧急度沿用原型模板（紧急度是规则，不学习）。只做本地推理，不调用任何大模型。

## 数据（全部为模拟数据）
种子为占位数据（大模型按印染行业常识编写，非任何企业资料）；需求卡、对话轨迹、业务周事件全部由程序生成，不调用大模型。

| 类型 | 数据来源 | 标签（事后有用性 / 注入窗口） | 样本数 train / val / test / heldout | 正例数 |
|---|---|---|---|---|
{rows}

- 追问、回问按需求卡划分 70 / 15 / 15，另留 2 个现象（`crease_marks`、`low_whiteness`）为 heldout，不参与训练与校准；定时三类按业务周划分 28 / 6 / 6；`data/week/w1`（另一个种子）不参与训练，由 `scripts/run_week.py` 评估。
- 回问样本另补了 3,000 张应升级的卡（只取回问样本）；种子 `tr:50`～`tr:57` 是为回问补的挂在槽位取值上的 L3 转化对照。

## 打分来源（D20：新模型赢的用模型，输的回落规则）
测试集上同一组合比较：Jue-K 的 AUC（校准前）高于规则分、且校准后 Brier 低于规则分才算赢（heldout 为未见现象，只列出不判胜负）。只保存赢了的类的校准器；
`JueK` 对没有校准器的类用模板 `rule_score` 打分，逐条标 `scored_by: rule`。规则分不是校准概率，Brier 对它偏严，如实列出。

| 决策 | Jue-K AUC | 规则 AUC | Jue-K Brier | 规则 Brier | 未见现象 AUC（Jue-K / 规则） | 最终 |
|---|---|---|---|---|---|---|
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
