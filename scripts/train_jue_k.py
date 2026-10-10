"""训练 Jue-K：一个 HistGradientBoostingClassifier（五类样本混在一起）+ 按 family 在验证集上拟合 isotonic 校准。
做法参照 JUE-r2 qmodel/v0/train.py（梯度提升 + 验证集 isotonic），数据与特征为本项目重写。

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
from huayan.jue.features import build, vectorize

META = ["family", "object_type", "object_id", "at", "source_id", "label", "split"]
SOURCES = {"ask_slot": "程序轨迹（需求卡 + 随机追问策略 + 抽取噪声）", "ask_back": "程序轨迹结束时构造的需求单（应升级的卡）",
           "opportunity": "多周模拟业务周的合成事件", "knowledge_conflict": "多周模拟业务周的合成事件",
           "leak_risk": "多周模拟业务周的合成事件"}
LABELS = {"ask_slot": "补上 / 改正真实值后，最终推荐是否由错变对", "ask_back": "补上 / 改正真实值后，本层转化对照命中集合是否变化",
          "opportunity": "落在非困难负样本注入的 [earliest, latest] 内、object_id 一致",
          "knowledge_conflict": "同 opportunity", "leak_risk": "同 opportunity"}


def features(df: pd.DataFrame) -> list[dict[str, float]]:
    attrs = [c for c in df.columns if c not in META]
    out = []
    for row in df.to_dict("records"):
        values = {k: row[k] for k in attrs if not (isinstance(row[k], float) and math.isnan(row[k]))}
        out.append(build(JueObject(object_id=row["object_id"], object_type=row["object_type"], attrs=values), row["family"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="data/jue_k/samples.csv")
    ap.add_argument("--out", default="models/jue_k")
    args = ap.parse_args()

    df = pd.read_csv(args.samples)
    feats = features(df)
    columns = sorted({k for f, s in zip(feats, df.split) if s == "train" for k in f})
    x, y = np.asarray(vectorize(feats, columns)), df.label.to_numpy()
    train, val = (df.split == "train").to_numpy(), (df.split == "val").to_numpy()

    classifier = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.1, random_state=0).fit(x[train], y[train])
    raw = classifier.predict_proba(x)[:, 1]
    calibrators, summary = {}, {}
    for family in sorted(df.family.unique()):
        fam = (df.family == family).to_numpy()
        v = fam & val
        calibrators[family] = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw[v], y[v])
        cal = calibrators[family].predict(raw[v])
        summary[family] = {
            "n": {s: int((fam & (df.split == s).to_numpy()).sum()) for s in ("train", "val", "test", "heldout")},
            "positives": {s: int(y[fam & (df.split == s).to_numpy()].sum()) for s in ("train", "val", "test", "heldout")},
            "val_auc": float(roc_auc_score(y[v], raw[v])) if len(set(y[v])) == 2 else None,
            "val_brier_raw": float(brier_score_loss(y[v], raw[v])), "val_brier_calibrated": float(brier_score_loss(y[v], cal))}

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
        print(f"{family:20s} train {s['n']['train']:5d}（正例 {s['positives']['train']:4d}）  val AUC {s['val_auc'] or float('nan'):.3f}"
              f"  Brier 原始 {s['val_brier_raw']:.3f} → 校准 {s['val_brier_calibrated']:.3f}")
    print(f"产物写入 {out}（特征 {len(columns)} 个）")


def model_card(summary: dict, n_features: int) -> str:
    rows = "\n".join(f"| `{f}` | {SOURCES[f]} | {LABELS[f]} | {s['n']['train']} / {s['n']['val']} / {s['n']['test']} / {s['n']['heldout']} "
                     f"| {s['positives']['train']} / {s['positives']['val']} / {s['positives']['test']} / {s['positives']['heldout']} |"
                     for f, s in summary.items())
    return f"""# Jue-K v0 模型卡

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

- 追问、回问按需求卡划分 70 / 15 / 15，另留 2 个现象（`crease_marks`、`low_whiteness`）为 heldout，不参与训练与校准；定时三类按业务周划分 28 / 6 / 6。
- 回问样本另补了 3,000 张应升级的卡（只取回问样本）；种子 `tr:50`～`tr:57` 是为回问补的挂在槽位取值上的 L3 转化对照。

## 适用范围
占位种子下的追问、回问与三类定时发现的打分；链路沿用 `config/app.yaml`。换真实种子后用 `scripts/make_jue_k_data.py` 与本脚本重训。
输出是校准概率，阈值按代价取 1 / (1 + 漏问代价 / 多问代价)：实时追问建议 0.15 左右（原型的 0.5 会几乎不问），定时三类 0.5。

## 已知局限
- 标签由需求卡真值或注入清单算出，是受控的模拟数据，不代表真实业务分布；接入真实对话后需用真实处置结果（`jue_samples.jsonl`）重新校准。
- 现象不进特征（独热会让模型记住现象），未见现象上的追问不优于规则；换种子必须覆盖全部现象。
- 追问只在前置条件通过的组合上打分：已填的槽位不进追问，模型不负责「对低置信度的值复问」。
- 抽取噪声中填错的置信度（0.4～0.6）与填对的（0.7～0.95）不重叠，比真实抽取更容易分辨。
- 回问的正例主要取决于该现象下槽位取值的先验（模型看不到真实值），且只来自挂在槽位取值上的少数几条转化对照。
- 定时三类来自合成事件，比真实链路干净；注入与困难负样本的模式固定，正例少，模型容易学到模式本身。
- 转化对照匹配的字符二元组规则会让相近取值误命中（如「溢流染色机」命中「气流染色机」），影响回问的取值区分度。
"""


if __name__ == "__main__":
    main()
