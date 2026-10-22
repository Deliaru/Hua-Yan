"""V9.6：合成试用实际加载的 Jue-K。入库的 models/jue_k 与 data/models_v8（新训的判断过时、试样风险）
按格取用；两类格不加载，这些家族由规则打分、标 scored_by: rule：
特征里带占位种子槽位 id 的（试用种子的槽位 id 不同，这些列在试用里全是 0）；
数值特征在现行觉状态里已不再产生的（训练后特征改过名，这些列恒为 0，模型等于没看到输入）。

    uv run python scripts/merge_jue_k_trial.py
"""
import json
import pickle
from pathlib import Path

import yaml

SOURCES = {"leak_risk|L2": "models/jue_k", "opportunity|L2": "models/jue_k",
           "stale_capability|L3": "data/models_v8", "trial_risk|L3": "data/models_v8",
           "ask_slot|L1": "models/jue_k", "ask_back|L3": "models/jue_k"}
OUT = Path("models/jue_k_trial")


def seed_bound(columns, slots):
    """列名里出现占位种子的槽位 id（slot=、missing:、unknown:、value:、现象/槽位）即依赖种子。"""
    return sorted(c for c in columns if any(f"={s}" in c or f":{s}" in c or c.endswith(f"/{s}") for s in slots))


def renamed(columns, state_source):
    """数值列（不带 =、:、/ 的）须仍是现行觉状态产生的属性名。"""
    return sorted(c for c in columns if not any(t in c for t in "=:/") and f'"{c}"' not in state_source)


def main():
    placeholder = {s["id"] for s in yaml.safe_load(Path("seeds/slots.yaml").read_text(encoding="utf-8"))["items"]}
    trial = {s["id"] for s in yaml.safe_load(Path("data/pilot/seeds/slots.yaml").read_text(encoding="utf-8"))["items"]}
    state_source = Path("src/huayan/jue/state.py").read_text(encoding="utf-8")
    models, columns, rows, sklearn = {}, {}, [], None
    for cell, src in SOURCES.items():
        features = json.loads(Path(src, "features.json").read_text(encoding="utf-8"))
        bound = seed_bound(features["columns"][cell], placeholder - trial)
        sklearn = features["sklearn"]
        if bound:
            rows.append(f"| `{cell}` | `{src}` | 规则（不加载：{len(bound)} 列依赖占位种子槽位，如 `{bound[0]}`） |")
            continue
        stale = renamed(features["columns"][cell], state_source)
        if stale:
            rows.append(f"| `{cell}` | `{src}` | 规则（不加载：{len(stale)} 列现行状态已不产生，如 `{stale[0]}`） |")
            continue
        with Path(src, "model.pkl").open("rb") as stream:
            models[cell] = pickle.load(stream)["models"][cell]
        columns[cell] = features["columns"][cell]
        rows.append(f"| `{cell}` | `{src}` | Jue-K |")
    OUT.mkdir(exist_ok=True)
    with (OUT / "model.pkl").open("wb") as stream:
        pickle.dump({"models": models}, stream)
    (OUT / "features.json").write_text(json.dumps({"columns": columns, "encoding": "utf-8", "sklearn": sklearn},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "model_card.md").write_text("\n".join([
        "# Jue-K 试用版模型卡（V9.6）", "",
        "由 `scripts/merge_jue_k_trial.py` 从入库的 `models/jue_k` 与 `data/models_v8` 按格合成，试用配置 `scheduled_model: jue_k` 加载。",
        "各格的训练数据、评估与已知局限见两份来源的模型卡；训练数据全部是占位种子上的模拟数据。", "",
        "| 家族 × 判断层 | 来源 | 试用中 |", "|---|---|---|", *rows, "",
        "不加载的格有两类。一是特征里带占位种子的槽位 id（`fiber`、`dye_class` 等），试用种子的槽位是 `fiber_type`、`dye_category` 等，",
        "这些列在试用里恒为 0。二是训练后觉状态的特征改过名（如泄露风险 v8 改为按同一产品的存根、授予结论计数），",
        "旧列恒为 0，模型对任何业务员都给 0。两类都要用现行特征、试用种子重训；在那之前这些家族用模板规则打分，逐条标 `scored_by: rule`。",
        "实时觉（追问、回问）因此没有可用的学习格，试用里 `realtime_model` 仍为原型。决策目录里其余家族本来就没有学习模型，同样是规则。", ""]),
        encoding="utf-8")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
