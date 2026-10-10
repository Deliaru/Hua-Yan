# WP-E 模拟业务周对照与评测、觉视图与评测页

> 负责：B｜时段：5:45–7:15｜分支：`dev/b`

## 目标
在模拟业务周上用真实链路验证觉的定时发现：同一段事件流跑「处置」与「不处置」两个分支，比较后果；与规则告警对照。做觉视图和评测页两个界面。

## 依赖
WP-I（门面的 `scan` / `resolve`）、WP-B2（业务周数据）、WP-B3（Jue-K 报告）。

## 必读
`ARCHITECTURE.md` 第 8、9 节；`CONTRACTS.md` 第 ⑤ 5.5、⑨、⑫ 节。

## 允许修改的范围
`src/huayan/eval/`、`scripts/run_week.py`、`docs/reports/week/`、`src/huayan/ui/pages/4_觉视图.py`、`src/huayan/ui/pages/5_评测.py`

## 交付物与已定设计

### 1. 业务周运行器 `eval/week.py`：`run_week(week_dir, policy, discoverer) -> run_dir`
- `HuayanApp.build` 使用 `SimClock`，并覆盖配置：`extractor: rule`、`system1_impl: mock`、`gateway_mock: true`（零成本；如实标注「业务周中抽取为规则、Jev 为桩」）。
- 按 `script.jsonl` 推进时钟：
  - `session`：`SimCustomer`（模板模式）开场 → 业务员按觉的提示追问（取第一条提示的话术）→ 客户回答 → 直到推荐或升级，最多 8 轮；没有提示仍未推荐时调用 `recommend_now`；
  - `trial`：`record_trial`；
  - `query`：以该业务员身份发起一句提问（新会话中的一轮）。
- 每 2 个业务小时 `scan` 一次。`discoverer="jue_proto"` 用 `config/templates/`；`"rule_alert"` 用 `config/baselines/rule_alert/`（同一原型、规则模式）。
- **模拟人处置**：`policy="handle"` 时，新出现的定时问题在 2 业务小时后按 family 处置（立项 → 起草、确认，1 个业务日后发布种子中覆盖该主题的研发中产品；更新说明书；冻结）；`policy="ignore"` 时不处置。`escalate_need` 两个分支都只记录，不处理。
- 运行器可以读需求卡（它在扮演客户）；**注入清单只在第 2 步算指标时读取**。

### 2. 指标 `eval/metrics.py` → `docs/reports/week/`
- **发现**：每类注入是否在 `[earliest, latest]` 内被发现（问题 `object_id` 与注入一致）、提前量；困难负样本误报数；发现环节大模型调用次数（应为 0）。觉 与 规则告警 各一行。
- **后果**（处置 vs 不处置）：机会汇聚——发现后同主题的升级次数（产品经理被打扰次数）与 L1 直接命中次数；知识冲突——冲突开始后对该产品 × 该面料的错误推荐次数；泄露风险——冻结后该业务员套问仍被受理的次数。
- 图：按天的升级次数（两个分支对比）；发现时间线（注入区间与发现时刻）。`README.md` 一页说明，如实写；规则告警在某类上更好就照写。

### 3. 觉视图 `ui/pages/4_觉视图.py`
- 实时：选一个会话，按轮显示每个槽位的 `p_need`（热力表）、当轮发出的提示、`scored_by`、本轮耗时与大模型调用数（应为 0）。
- 定时：「执行一次扫描」按钮；觉发现的问题列表（概率、证据、负责人）；主管身份下对泄露风险显示「冻结访问」，其他身份显示负责人。
- 一句说明：觉不回答问题、不调用大模型，只判断「此刻要不要处理、处理什么」。

### 4. 评测页 `ui/pages/5_评测.py`
展示 `docs/reports/jue_k/` 与 `docs/reports/week/` 的图和关键数字，每块写明数据来源（模拟数据、种子是否占位）。

### 5. 可选（有时间且已授权大模型费用）
- 大模型轮询基线 `eval/llm_poll.py`（caller `baseline:llm_poll`），实现契约 5.5 的 `Discoverer`；
- 文本对话上的三组对照（业务员转述 / 一次性翻译 / 化言），模拟客户用大模型模式，各 20 张卡。

## 验收
1. `uv run python scripts/run_week.py --week data/week/w1` 生成两个分支、两种发现器的运行目录与 `docs/reports/week/`；同一种子重跑结果一致。
2. 首版 Demo 验收第 4 条：机会汇聚的处置与不处置差异在图上可见。
3. 觉视图、评测页能打开，数字与报告一致。

## 不做
新的发现类型；调参追求好看的结果；在测试种子上改阈值。
