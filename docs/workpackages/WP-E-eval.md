# WP-E 失真对照、业务周对照、三层对照页与评测页

> 负责：B｜时段：**前半 3:30–5:00**（与 WP-B3 同时开第二个 Agent）＋**后半 5:45–7:00**｜分支：`dev/b`

## 目标
1. **失真对照（必做）**：用数字回答「化言的转译比现在的做法少走样多少」——同一批需求卡上，业务员转述 / 一次性翻译 / 化言三组，比较到达研发时的需求信息。
2. **业务周对照**：在模拟业务周上用真实链路验证觉的定时发现，只做机会汇聚的「处置 / 不处置」两个分支。
3. 两个界面：**三层对照页**（必做，演示主线的收尾画面）与评测页；觉视图可选。

## 依赖
WP-I（门面完整）、WP-T（规则模式）、WP-B2（需求卡、模拟客户、业务周）、WP-B3（Jue-K 报告）。

| 段 | 内容 | 依赖 |
|---|---|---|
| 前半 | 失真对照全部代码（G1、G2、G3、指标、`config/eval/distortion.yaml`）并先跑出不含回问的结果；评测页框架 | WP-B2、WP-T、WP-B1（G3 的回问在 B3 第 ① 段合并后接上） |
| 后半 | G3 加回问重跑与出图；业务周（真实链路，三种发现器）；三层对照页；评测页填数 | WP-I、WP-B3 第 ③ 段 |

## 必读
`CONTRACTS.md` 第 ③、⑤ 5.5、⑦、⑨、⑫ 节；`ARCHITECTURE.md` 第 8、9 节（失真来源的定性描述）。

## 允许修改的范围
`src/huayan/eval/`、`config/eval/`、`scripts/run_distortion.py`、`scripts/run_week.py`、`docs/reports/distortion/`、`docs/reports/week/`、`src/huayan/ui/pages/4_三层对照.py`、`src/huayan/ui/pages/5_评测.py`、`src/huayan/ui/pages/6_觉视图.py`

## 交付物与已定设计

### 1. 失真对照 `eval/distortion.py`（必做，零成本）
`run_distortion(cards, seeds, cfg, rng) -> pandas.DataFrame`，每张卡 × 每组一行。

- **卡**：`data/sim/cards.jsonl` 前 60 张，全部参与（问题是「需求信息到研发手里时还剩多少、对不对」，与 L1 能否直接推荐无关）。
- **真值（关键信息）**：现象 + 该现象全部必问槽位的取值；`unknown_slots` 不计入分母（客户自己也说不清）。
- **三组**，都用 `SimCustomer` 模板模式、同一个随机种子：
  - **G1 业务员转述**：不用觉的提示；业务员只按习惯问 `relay.habit_slots` 中的槽位（默认只问面料）；然后按**转述噪声模型**写给研发：现象以 `relay.vague_prob` 的概率被说成笼统的「染色有问题」，每个已知槽位以 `relay.drop_prob` 的概率漏掉、以 `relay.swap_prob` 的概率被记成同槽位的另一个取值；没有原话、没有依据。参数放 `config/eval/distortion.yaml`，**在报告中标明是假设**，写出依据；企业数据到位后用真实转述样本替换。
  - **G2 一次性翻译**：不追问，只有客户开场白；规则抽取得到槽位，再用**全部**转化对照（L2、L3 混在一起、不按现象过滤）对开场白做一次匹配，直接产出化学语言条目。只有开场白一轮可回查，引用不记归属。
  - **G3 化言**：按觉的提示追问（取第一条提示的话术，最多 8 轮）→ `NeedState` → `translate.draft_product_need` → `draft_chem_need`（规则模式）→ **回问**（契约 v4）：对 L3 草稿调用一次 `requirement_state` + 觉（规则原型），`ask_back` 中 p ≥ 阈值的槽位（最多 2 个）让模拟客户各回答一次，回填后重新起草 L3。`Question` 由评测代码直接构造一个 `escalate_need`（不经过总线）。
- **指标**（每组一行，写 `metrics.json` 与 `table.csv`）：
  - 关键信息完整率：研发拿到的、值正确的必问槽位 / 必问槽位；
  - 槽位错误率：值错误的槽位 / 研发拿到的槽位；
  - 错译率：引用的转化知识不属于该卡现象的条目 / 全部条目；
  - 平均追问次数；
  - 回问次数（仅 G3）：觉在转译时发起的回问，以及其中事后有用（补上后 L3 命中改变）的比例；
  - 可回查率：带客户原话（`quote_refs`）的条目 / 全部条目；
  - 研发需退回比例：现象不明、或任一必问槽位缺失 / 错误的卡的比例。
- 图：三组 × 指标的分组柱状图；`README.md` 一页说明，必须如实写两点：G1 的噪声来自假设参数；模板客户与规则抽取共用种子中的口语说法表，G3 的槽位错误率偏乐观。
- 发现与转译环节大模型调用为 0（计量为空）；同一种子重跑结果一致。
- **可选**（大模型费用已授权，时间够再做）：G2 换成真大模型一次性翻译（caller `baseline:one_shot`），G3 改由产品经理 / 研发助手在规则骨架上修改（`agents.notify` 派单，确认由评测代码代替并标注），各 20 张卡，作为附加列，不替换规则版结果。

### 2. 业务周运行器 `eval/week.py`：`run_week(week_dir, policy, discoverer) -> run_dir`
- `HuayanApp.build` 使用 `SimClock`，并覆盖配置：`extractor: rule`、`system1_impl: mock`、`gateway_mock: true`（零成本；如实标注「业务周中抽取为规则、Jev 为桩、转译为规则模式」）。
- 按 `script.jsonl` 推进时钟：`session`（模拟客户开场 → 按觉的提示追问 → 直到推荐或升级，最多 8 轮；没有提示仍未推荐时 `recommend_now`）、`trial`（`record_trial`）、`query`（以该业务员身份发起一句提问）。
- 每 2 个业务小时 `scan` 一次。`discoverer="jue_proto"` 用 `config/templates/`；`"rule_alert"` 用 `config/baselines/rule_alert/`；`"jue_k"`（契约 v4）用 `models/jue_k/`。Jue-K 训练用的是合成事件，这里是它在真实链路事件上的评估。
- **只做机会汇聚的处置分支**：`policy="handle"` 时，新出现的机会汇聚问题在 2 业务小时后走 `approve_project` → L2 确认 → L3 确认 → 1 个业务日后发布种子中覆盖该主题的研发中产品（包装用规则模式）；`policy="ignore"` 时不处置。其他 family 两个分支都只记录发现。
- 运行器可以读需求卡（它在扮演客户）；**注入清单只在算指标时读取**。

### 3. 业务周指标 `eval/metrics.py` → `docs/reports/week/`
- 发现：每类注入是否在 `[earliest, latest]` 内被发现（问题 `object_id` 与注入一致）、提前量；困难负样本误报数；发现环节大模型调用次数（应为 0）。觉原型、Jue-K 与规则告警各一行。
- 后果（机会汇聚，处置 vs 不处置）：发现后同主题的升级次数（产品经理被打扰次数）与 L1 直接命中次数。
- 图：按天的升级次数（两个分支对比）；发现时间线。`README.md` 如实写；规则告警在某类上更好就照写。

### 4. 三层对照页 `ui/pages/4_三层对照.py`（必做）
- 选一个已到 `rd_confirmed` 或之后状态的需求单，三列并排：
  - **L1**：`view_session(..., "sales:S01")` 的场景需求卡（槽位 + 原话）；发布后显示包装后的产品卡；
  - **L2**：`requirement_view(..., "pm:P01")`——产品需求条目 + 所引知识（L3 知识只显示「研发 R01 的转化知识（L3）」）；
  - **L3**：`requirement_view(..., 产品归属研发)`——化学语言条目、所引知识原文、假设；产品卡 `internal` 版本。
- 条目用 WP-U 的需求条目组件；同一 `quote_refs` 在三列中高亮同一句原话，看得出「一句客户原话如何逐层变成化学语言」。
- 下方**贡献看板**：`contributions(viewer)`——每位研发 / 产品经理的知识被引用次数、积分、被哪些需求单使用。
- 下方一行失真对照的关键数字（取 `docs/reports/distortion/metrics.json`），链接到评测页。

### 5. 评测页 `ui/pages/5_评测.py`
展示 `docs/reports/distortion/`、`docs/reports/jue_k/`、`docs/reports/week/` 的图和关键数字，每块写明数据来源（模拟数据、种子是否占位、哪些参数是假设）。

### 6. 觉视图 `ui/pages/6_觉视图.py`（可选，时间不够先砍）
- 实时：选一个会话，按轮显示每个槽位的 `p_need`（热力表）、当轮提示、`scored_by`、大模型调用数（应为 0）；
- 定时：「执行一次扫描」按钮与发现的问题列表（概率、紧急度、证据、负责人）；
- 数据引擎：`jue_samples.jsonl` 的记录条数与按类型的概率分布。

## 验收
1. `uv run python scripts/run_distortion.py --cards data/sim/cards.jsonl --n 60` 生成 `docs/reports/distortion/`；同一种子重跑一致；首版 Demo 验收第 5 条的三组对照有图有表。
2. `uv run python scripts/run_week.py --week data/week/w1` 生成两个分支、三种发现器的运行目录与 `docs/reports/week/`；机会汇聚的处置与不处置差异在图上可见。
3. 三层对照页在演示主线跑完后能打开，三列内容与首版 Demo 验收第 2 条一致；评测页数字与报告一致。

## 不做
知识冲突与泄露风险的处置分支（只记录发现）；新的发现类型；调参追求好看的结果；在测试种子上改阈值；为评测再写测试。
