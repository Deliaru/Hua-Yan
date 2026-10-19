"""Jue-K 训练（从 scripts/train_jue_k.py 移出）：按「家族 × 判断层」每格一个 HistGradientBoostingClassifier，
在验证集上拟合 isotonic 校准，在测试集上与模板规则分配对比较，赢了才保存（D20），没保存的格由规则打分。
每格只用同家族、同判断层、且结果层级不高于该层的行（rows_for），更高层的判断不会经共用分类器影响下层的分数。
做法参照 JUE-r2 qmodel/v0/train.py（梯度提升 + 验证集 isotonic）。只在本地 CPU 上运行，不调用任何模型服务。

一行（dict）：family、object_type、object_id、attrs、label（0/1）、judge_level、level，可带 split（train / val / test / heldout）；
没有 split 的行按 object_id 稳定划分 70 / 15 / 15。"""
import json
import pickle
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from huayan.contracts import JueObject
from huayan.jue.features import build, vectorize
from huayan.jue.proto import load_templates, rule_score
from huayan.jue.records import rows_for

MIN_TRAIN = 100      # 一格训练行少于这个数就不训练，照旧规则打分
SPLITS = ["train"] * 14 + ["val"] * 3 + ["test"] * 3


def make_classifier() -> HistGradientBoostingClassifier:
    """浅树 + 叶子最少样本 + L2：样本少（回问约千条）且有现象 × 槽位独热，默认深树会记住训练卡。学习曲线也用它。"""
    return HistGradientBoostingClassifier(max_iter=150, max_depth=3, min_samples_leaf=30, l2_regularization=1.0,
                                          random_state=0)


def beats_rule(y: np.ndarray, model: np.ndarray, rule: np.ndarray, n: int = 500) -> tuple[bool, list[float]]:
    """配对 bootstrap：返回是否显著胜出（AUC 差 95% 区间下界 > 0 且 Brier 差上界 < 0），以及 AUC 差的 95% 区间。"""
    rng = np.random.default_rng(0)
    d_auc, d_brier = [], []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if len(set(y[i])) < 2:
            continue
        d_auc.append(roc_auc_score(y[i], model[i]) - roc_auc_score(y[i], rule[i]))
        d_brier.append(np.mean((model[i] - y[i]) ** 2) - np.mean((rule[i] - y[i]) ** 2))
    ci = [round(float(np.percentile(d_auc, 2.5)), 3), round(float(np.percentile(d_auc, 97.5)), 3)]
    return ci[0] > 0 and float(np.percentile(d_brier, 97.5)) < 0, ci


def _auc(y: np.ndarray, p: np.ndarray) -> float | None:
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else None


def _split(row) -> str:
    return row.get("split") or SPLITS[zlib.crc32(row["object_id"].encode("utf-8")) % len(SPLITS)]


def cells(rows: list[dict]) -> dict[str, list[dict]]:
    """「家族 × 判断层」→ 该格的训练行：同家族、同判断层，且 level ≤ 判断层。没有标签的行不进。"""
    out = defaultdict(list)
    for row in rows:
        if row["label"] is not None:
            out[f"{row['family']}|L{row['judge_level']}"].append(row)
    return {cell: rows_for(group, group[0]["judge_level"]) for cell, group in sorted(out.items())}


def fit(rows: list[dict], templates_dir, out_dir) -> dict[str, dict]:
    """训练、校准、与规则比较；写 model.pkl（models: {"<family>|L<k>": (classifier, calibrator)}）、
    features.json（每格的特征列）、metrics.json。返回每格的指标。"""
    templates = {t.family: t for t in load_templates(templates_dir).values()}
    models, columns, summary = {}, {}, {}
    for cell, group in cells(rows).items():
        family = group[0]["family"]
        objects = [JueObject(object_id=r["object_id"], object_type=r["object_type"], attrs=r["attrs"]) for r in group]
        feats = [build(o, family) for o in objects]
        split, y = np.array([_split(r) for r in group]), np.array([int(r["label"]) for r in group])
        train, val, test, held = (split == s for s in ("train", "val", "test", "heldout"))
        n = {s: int((split == s).sum()) for s in ("train", "val", "test", "heldout")}
        positives = {s: int(y[split == s].sum()) for s in ("train", "val", "test", "heldout")}
        if n["train"] < MIN_TRAIN or len(set(y[train])) < 2 or len(set(y[val])) < 2 or len(set(y[test])) < 2:
            summary[cell] = {"n": n, "positives": positives, "scored_by": "rule", "reason": "样本不够"}
            continue
        cols = sorted({k for f, s in zip(feats, split) if s == "train" for k in f})
        x = np.asarray(vectorize(feats, cols))
        classifier = make_classifier().fit(x[train], y[train])
        raw = classifier.predict_proba(x)[:, 1]
        calibrator = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(raw[val], y[val])
        rule = np.array([rule_score(templates[family], o) for o in objects])
        cal_t = calibrator.predict(raw[test])
        auc = _auc(y[test], raw[test])
        wins, ci = beats_rule(y[test], cal_t, rule[test]) if auc is not None else (False, None)
        if wins:
            models[cell], columns[cell] = (classifier, calibrator), cols
        summary[cell] = {
            "n": n, "positives": positives,
            "val_auc": _auc(y[val], raw[val]), "val_brier_raw": float(brier_score_loss(y[val], raw[val])),
            "val_brier_calibrated": float(brier_score_loss(y[val], calibrator.predict(raw[val]))),
            "test_auc": auc, "test_rule_auc": _auc(y[test], rule[test]), "test_auc_diff_ci95": ci,
            "test_brier": float(brier_score_loss(y[test], cal_t)), "test_rule_brier": float(brier_score_loss(y[test], rule[test])),
            "heldout_auc": _auc(y[held], raw[held]) if held.any() else None,
            "heldout_rule_auc": _auc(y[held], rule[held]) if held.any() else None,
            "scored_by": "jue_k" if wins else "rule"}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "model.pkl").open("wb") as stream:
        pickle.dump({"models": models}, stream)
    (out / "features.json").write_text(json.dumps({
        "columns": columns, "encoding": "数值属性原值；布尔 0/1；slot / role / family / object_type 独热（phenomenon 不进特征）；缺失与未见取值记 0",
        "sklearn": sklearn.__version__}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps({"rows": len(rows), "by_cell": summary}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    return summary
