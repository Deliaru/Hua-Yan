# WP-B3 Jue-K：一个模型覆盖全部决策类型

> 负责：B｜时段：3:30–6:45（分三段，见下）｜分支：`dev/b`
>
> **v4 重写**：原版只训练追问，不符合觉的定义（发现需要决策的情况并给出校准概率）。现改为一个模型覆盖五类决策，并新增「回问」让觉出现在转译主线上。原版已写的追问轨迹、标签、特征代码保留，在此基础上扩展。

## 目标
训练觉在化言中的版本 Jue-K v0：**一个模型**，对「此刻 × 模板 × 对象」的全部组合输出「需要决策」的校准概率，覆盖五类：

| 类型 | 模式 | 对象 | 交给谁 |
|---|---|---|---|
| 追问 `ask_slot` | 实时 | 会话 × 槽位（layer 1） | 业务员（提示，不进总线） |
| **回问 `ask_back`**（新增） | 实时 | 需求单 × 槽位（layer 2/3） | 原业务员（进总线，派给业务员助手） |
| 机会汇聚、知识冲突、泄露风险 | 定时 | 主题、知识、提问者 | 产品经理、研发、主管 |

实时与定时都能把原型换成 Jue-K，链路和界面不改。完整方案见 `docs/JUE_K_TRAINING.md` v3。

## 分段

| 段 | 时段 | 内容 | 谁在等 |
|---|---|---|---|
| ① 回问与紧急度 | 3:30–4:00 | `layer` / `trans_splits`、`requirement_state`、`ask_back` 模板、5 个模板的 `urgency`、`publish` 处理回问；**完成后先合并** | WP-I（5:00） |
| ② 样本 | 4:00–5:00 | 轨迹（追问 + 回问）、多周业务周合成事件 → `samples.csv` | — |
| ③ 训练与评估 | 5:00–6:45 | 训练在后台跑，期间参加 WP-I；之后评估、报告、双路热替换 | WP-I 验收 2、WP-E 评测页 |

## 依赖
WP-B1、WP-B2、WP-T（`match_translations`）。

## 必读
`JUE_K_TRAINING.md` v3 全文（第 1、3、11 节重点）；`CONTRACTS.md` v4 第 5.1–5.4、⑥、⑨ 节。

## 允许修改的范围
`src/huayan/jue/`（含 WP-B1 已写的 `state.py`、`publish.py`、`proto.py`；不含 `expr.py`）、`config/templates/`、`src/huayan/sim/trajectory.py`、`src/huayan/sim/week_events.py`、`scripts/make_jue_k_data.py`、`scripts/train_jue_k.py`、`scripts/eval_ask_policies.py`、`scripts/eval_jue_k.py`、`models/jue_k/`、`docs/reports/jue_k/`、`tests/test_wp_b3.py`、`tests/test_wp_b1.py`（只在模板加 `layer` 条件后需要时改）

## 交付物与已定设计

### ① 回问与紧急度（`jue/state.py`、`config/templates/`、`jue/proto.py`、`jue/publish.py`）
- `realtime_state` 的 slot 对象增加 `layer=1`、`trans_splits=0`；新增 `requirement_state(req, need, seeds, kb, at)`，按契约 5.1 / 5.2（draft → layer 2，pm_confirmed → layer 3）。
- 模板：
  - `ask_slot` 前置条件加 `attrs.layer == 1`；
  - 新增 `ask_back.yaml`：前置条件 `attrs.layer >= 2 and not attrs.filled and not attrs.unknown and attrs.trans_splits >= 2`；规则打分随 `trans_splits` 增大；`title` 如「转译需要确认客户的 {attrs.slot}」；`owner_role: sales`；
  - 五个模板都写 `urgency`：`ask_slot` 为 `1.0`（客户在线）；`ask_back` 为 `0.8`；`opportunity` 为 `min(1, attrs.n_customers / 4)`；`knowledge_conflict` 为 `min(1, attrs.n_recommended / 5)`（还在被推荐，损害在扩大）；`leak_risk` 为 `1.0`。
- `JueProto` 填 `ScoredDecision.urgency`；`publish` 把回问发成问题（owner_id = 会话的业务员，refs 见契约 5.4），所有问题照填 `Question.urgency`。

### ② 样本 `sim/trajectory.py`、`sim/week_events.py`、`scripts/make_jue_k_data.py` → `data/jue_k/samples.csv`
- **追问**：沿用原设计（随机追问策略、抽取噪声、事后有用性标签），layer 1。约 2,000 张卡 × 6 轮 × 7 槽位。
- **回问**：每段轨迹结束时，若该卡应升级（`truth_product is None`），用结束时（带噪声）的槽位状态构造需求单（`known_slots` = 已填槽位），对 layer 2、3 各出一组槽位样本。标签：未填、未答不清楚，且补上真实值后本层转化对照命中集合改变 → 1；填错且改正后改变 → 1；其余 0。`trans_splits` 与标签用同一个 `match_translations`。
- **定时三类**：
  - `make_week` 用 40 个随机种子生成 40 周（每周 5 个业务日，注入与困难负样本照 WP-B2）；
  - `week_events.synth_events(items, cards, seeds, products, rng) -> EventLog`：**不跑链路**，直接按剧本和需求卡真值合成觉定时状态依赖的事件：`session` 用需求卡全部真值调用 `match_candidates`，唯一命中写 `recommend`，否则写 `escalate`（`p_none` 在 0.6～0.9 随机）；`trial` 写 `trial`；`query` 写 `retrieve`（问机理或配方的记为被拦截，`blocked_product_ids` 取文本中的型号）。payload 字段按契约 ⑧；
  - 每 2 个业务小时 `scheduled_state` 一次，标签按契约 ⑨；
  - 打印每类样本数与正例数；某类正例 < 100 时加周数，不改标签。
- 只收前置条件通过的组合，与推理时一致。

### ③ 训练、推理、评估
- `jue/features.py`：`build(obj, family)`：数值属性直接用，布尔转 0/1，`slot`、`phenomenon`、`role`、`family`、`object_type` 独热（未见取值全 0），缺失属性记 0。训练和推理共用。
- `scripts/train_jue_k.py`：**一个** `HistGradientBoostingClassifier`（五类样本混在一起），再按 family 在验证集上各拟合一个 isotonic 校准；产物按契约 ⑨。`model_card.md` 写清每类的数据来源、标签含义、正例数、适用范围和已知局限（定时三类是合成事件、正例少）。
- `jue/jue_k.py`：`JueK(model_dir, templates_dir, mode)` 按契约 5.4：与原型共用模板枚举、前置条件和紧急度；一次批量 `predict_proba`；`scored_by="jue_k"`；每次 `propose` 写 `kind="jue"` 计量。
- `scripts/eval_jue_k.py` → `docs/reports/jue_k/`：
  - **校准（主结果）**：每类在 test（追问 / 回问另加 heldout）上的 AUC、Brier、ECE，以及校准前后的可靠性图；同一批组合上原型规则分数的 Brier / ECE 作对照，说明规则分数不是概率；
  - **追问操作点**：保留 `eval_ask_policies.py` 的「平均追问次数 – 最终正确率」曲线（Jue-K、B1 必问清单、B2 信息价值规则、原型规则模式）；
  - **定时发现**：在 6 个测试周上，按 WP-E 的口径（窗口内发现、提前量、困难负样本误报）比较 Jue-K 与原型规则模式；
  - `README.md` 一页说明，如实写哪一类 Jue-K 更好、哪一类规则已经够用。

## 验收
1. `tests/test_wp_b3.py` 只有 1 个测试：在小种子上手算 6 个样例，与样本生成代码的结果一致：
   - 追问 3 例：未填且会改变候选 → 1；答过「不清楚」→ 0；填错且改正会改变候选 → 1；
   - 回问 1 例：layer 3 未填且补上会改变 L3 命中 → 1；
   - 定时 2 例：注入窗口内的机会汇聚主题 → 1；同一客户反复升级的困难负样本 → 0。
2. 第 ① 段合并后，WP-I 的离线主线第 3 步出现一次回问。
3. `models/jue_k/` 产物齐全；`docs/reports/jue_k/` 有五类可靠性图、校准表、追问曲线、定时对比和说明。
4. `realtime_model: jue_k`、`scheduled_model: jue_k` 时演示主线照样跑通，链路代码不改。小种子上的测试不用 Jue-K。

## 不做
超参数搜索；每类单独训练一个模型；学习紧急度；大模型追问基线（WP-E 可选）；用真实链路生成训练数据。
