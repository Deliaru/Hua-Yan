# Jue-K 试用版模型卡（V9.6）

由 `scripts/merge_jue_k_trial.py` 从入库的 `models/jue_k` 与 `data/models_v8` 按格合成，试用配置 `scheduled_model: jue_k` 加载。
各格的训练数据、评估与已知局限见两份来源的模型卡；训练数据全部是占位种子上的模拟数据。

| 家族 × 判断层 | 来源 | 试用中 |
|---|---|---|
| `leak_risk|L2` | `models/jue_k` | 规则（不加载：4 列现行状态已不产生，如 `blocked_top_share`） |
| `opportunity|L2` | `models/jue_k` | Jue-K |
| `stale_capability|L3` | `data/models_v8` | Jue-K |
| `trial_risk|L3` | `data/models_v8` | 规则（不加载：44 列依赖占位种子槽位，如 `missing:bath_ph`） |
| `ask_slot|L1` | `models/jue_k` | 规则（不加载：24 列依赖占位种子槽位，如 `bleeding_staining/dye_class`） |
| `ask_back|L3` | `models/jue_k` | 规则（不加载：18 列依赖占位种子槽位，如 `bleeding_staining/equipment`） |

不加载的格有两类。一是特征里带占位种子的槽位 id（`fiber`、`dye_class` 等），试用种子的槽位是 `fiber_type`、`dye_category` 等，
这些列在试用里恒为 0。二是训练后觉状态的特征改过名（如泄露风险 v8 改为按同一产品的存根、授予结论计数），
旧列恒为 0，模型对任何业务员都给 0。两类都要用现行特征、试用种子重训；在那之前这些家族用模板规则打分，逐条标 `scored_by: rule`。
实时觉（追问、回问）因此没有可用的学习格，试用里 `realtime_model` 仍为原型。决策目录里其余家族本来就没有学习模型，同样是规则。
