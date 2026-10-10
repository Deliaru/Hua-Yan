# WP-B3 Jue-K：轨迹、标签、训练、评估

> 负责：B｜时段：3:30–5:00｜分支：`dev/b`

## 目标
训练觉在追问补全上的版本 Jue-K v0：对「会话此刻 × 某槽位」输出「现在需要追问」的校准概率。替换原型后，链路和界面不改。完整方案见 `docs/JUE_K_TRAINING.md`，本包是它的 8 小时执行版。

## 依赖
WP-B1（`realtime_state`）、WP-B2（`make_cards`）。

## 必读
`JUE_K_TRAINING.md` 全文；`CONTRACTS.md` 第 5.2（slot 属性）、5.4、⑨ 节。

## 允许修改的范围
`src/huayan/jue/jue_k.py`、`src/huayan/jue/features.py`、`src/huayan/sim/trajectory.py`、`scripts/train_jue_k.py`、`scripts/eval_ask_policies.py`、`models/jue_k/`、`docs/reports/jue_k/`、`tests/test_wp_b3.py`

## 交付物与已定设计

### 1. 轨迹与标签 `sim/trajectory.py`
- 每张需求卡模拟一段对话的**槽位状态序列**（不生成文本）：首轮只知道现象和 `opening_slots`；之后每轮业务员按随机策略追问 0～2 个槽位（40% 问必问槽位、30% 问随机槽位、30% 不问）；客户按真值回答，`unknown_slots` 答不清楚。
- **抽取噪声**：每次填入时 10% 概率填错（同槽位的另一个取值，置信度 0.4～0.6），5% 漏填；正确填入置信度 0.7～0.95。
- 每轮对每个槽位：用 `realtime_state` 得到属性；**标签（事后有用性）**：
  - 未填：`unknown` 为 0；否则「补上真实值后，候选集合发生变化」为 1；
  - 已填：「填的值 ≠ 真实值，且改成真实值后候选集合发生变化」为 1（这是重新确认的价值，让模型学会对低置信度的值复问）；
  - 现象未知的轮次不出样本。
- 输出 `data/jue_k/steps.csv`（列按契约 ⑨）。约 2,000 张卡 × 6 轮 × 7 槽位。
- 划分：按卡随机 70/15/15；另留 2 个现象作为 `heldout`（不进训练和验证）。

### 2. 特征与模型
- `jue/features.py`：`build(obj)`：数值属性直接用，布尔转 0/1，`slot` 与 `phenomenon` 独热（未见取值全 0）。训练和推理共用。
- `scripts/train_jue_k.py`：`HistGradientBoostingClassifier` + 验证集上拟合 isotonic 校准；产物写 `models/jue_k/`（契约 ⑨）。`model_card.md` 写清数据来源（占位种子 + 程序生成）、标签含义、适用范围、已知局限。
- `jue/jue_k.py`：`JueK(model_dir)` 实现 `QuestionModel`，只处理 `slot` 对象，输出 `family="ask_slot"`、`scored_by="jue_k"`；每次 `propose` 写 `kind="jue"` 计量。

### 3. 评估 `scripts/eval_ask_policies.py` → `docs/reports/jue_k/`
- **分类**：测试集与 heldout 上的 AUC、Brier、ECE，校准前后的可靠性图。
- **操作点（主结果）**：在 300 张测试卡上做交互回放——策略每轮选 p ≥ τ 的槽位（最多 2 个）追问，模拟客户按真值回答（带同样的抽取噪声），直到没有要问的；最终用 `match_candidates` 是否唯一命中 `truth_product`（或正确判为应升级）算正确。扫描 τ，画「平均追问次数 – 最终正确率」曲线，比较 **Jue-K、B1 必问清单、B2 信息价值规则、觉原型规则模式**。
- `README.md` 一页说明：如实写结论；如果 B2 一样好，就写「信息价值规则已经足够，Jue-K 的增量在于校准概率和对抽取噪声的复问」。

## 验收
1. `tests/test_wp_b3.py` 只有 1 个测试：在小种子上手算 3 个样例的标签（未填且会改变候选 → 1；已答不清楚 → 0；填错且改正会改变候选 → 1），与 `trajectory.py` 的结果一致。
2. `models/jue_k/` 产物齐全；`docs/reports/jue_k/` 有曲线、可靠性图和说明。
3. 在 `seeds/` 上把 `config/app.yaml` 的 `realtime_model` 改为 `jue_k`，演示主线照样跑通，链路代码不改（WP-I 时验证）。小种子上的测试不用 Jue-K（槽位和现象不同）。

## 不做
泄露风险的训练版（v0.5）；大模型追问基线 B3（需要文本对话和费用，放到 WP-E 可选）；超参数搜索。
