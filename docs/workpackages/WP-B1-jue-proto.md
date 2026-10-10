# WP-B1 觉原型：状态构建、模板、追问选择、定时扫描

> 负责：B｜时段：0:45–2:15｜分支：`dev/b`
>
> **v4 说明**：契约 v4 新增的 `layer` / `trans_splits`、`requirement_state`、`ask_back` 模板与 `urgency` 由 WP-B3 第 ① 段在本包代码上补，本包不返工。

## 目标
实现觉的第一个实现 `jue_proto`：把会话和事件日志变成「对象 × 属性」的状态，模板 × 对象枚举全部组合，判断此刻是否需要处理。实时输出追问提示，定时输出发布到总线的问题。**发现环节不调用任何大模型。**

## 依赖
WP-0。用小种子、手写的 `NeedState` 和用 `EventLog.append` 手写的事件开发，不等 A 线。

## 必读
`CONTRACTS.md` 第 ③（NeedState、AskHint）、⑤、⑥、⑧ 节；`ARCHITECTURE.md` 第 4 节；JUE 的 `docs/workpackages/WP-C-discovery.md`（同一思路的物流版，参考写法）。

## 允许修改的范围
`src/huayan/jue/`（不含 `expr.py`、`jue_k.py`、`features.py`）、`config/templates/`、`config/baselines/`、`tests/test_wp_b1.py`

## 交付物与已定设计

### 1. 状态构建 `jue/state.py`
- `realtime_state(need, seeds, products, at)`：为**每个槽位**生成一个 `slot` 对象，属性严格按契约 5.2。`splits` 的算法：对该槽位的每个取值 v，计算 `match_candidates(phenomenon, known ∪ {slot: v})` 的候选 id 集合，统计不同集合的个数；已填或现象未知时为 0。`n_candidates` 现象未知时为 0。
- `scheduled_state(events, at, seeds, products, windows)`：只读事件日志（payload 字段见契约 ⑧）和当前已发布产品：
  - `theme`：由 `escalate` 与 `recommend` 事件按「现象 + 必问槽位已知取值」聚合；`open_project` 看是否有该主题的 `requirement_confirmed` 且未 `product_released`；
  - `knowledge`：由 `trial` 事件按「产品 × 每个条件槽位取值」聚合；`claimed` 看当前产品 `applicable`；
  - `actor`：由 `retrieve` 事件按发起人聚合；`frozen` 看 `access_frozen` 事件。
- 不读取需求卡、注入清单、任何 `data/sim`、`data/week` 下的文件。

### 2. 模板 `config/templates/`（一个模板一个 yaml，按契约 5.3）
| 模板 | 前置条件（思路） | 规则打分（思路） |
|---|---|---|
| `ask_slot` | 未填、未答不清楚、追问次数 < 2、现象已知、`splits ≥ 2` 或（`required` 且候选 ≥ 2） | 随 `splits` 增大、随 `prior_top` 增大而减小 |
| `opportunity` | 升级 ≥ 2 次、涉及客户 ≥ 2 个、无在途需求单 | 随升级次数、客户数、`mean_p_none` 增大 |
| `knowledge_conflict` | `claimed`、试样 ≥ 2、产品原因失败 ≥ 2 | `fail_ratio` |
| `leak_risk` | 未冻结、被拦截命中 ≥ 3 | 随 `n_blocked`、`blocked_top_share` 增大 |

`worth_prompt` 写成 Jev 能回答的是非题，如「会话中客户反映 {object}……此刻是否需要追问该信息？」。`title` 写给人看，如「锦纶氨纶色花需求反复出现，是否立项？」。悬赏积分：机会汇聚 10、知识冲突 5、泄露风险 0。

### 3. 原型 `jue/proto.py`：`JueProto(templates_dir, system1, mode)`
按契约 5.4。`system1` 为 `OneJevClient` 时才调用 Jev（一次批量，caller `jue:proto`）；其余情况用 `rule_score`，`scored_by="rule"`。每次 `propose` 写一条 `kind="jue"` 计量。不 import `huayan.gateway`。

### 4. 发布 `jue/publish.py` 与扫描 `jue/scan.py`
- `select_asks`、`publish`、`scan` 按契约。`publish` 按 `config/app.yaml` 的 `routing` 填写 `owner_role`；知识冲突的 `owner_id` 为产品归属研发；`discoverer="jue_proto"`；证据写出触发它的关键属性（如「5 天内 4 次升级，涉及 3 个客户」）和相关事件 id。机会汇聚问题的 `refs["session_ids"]` 填相关会话 id（逗号分隔），WP-I 立项时据此起草需求单。
- 便捷函数 `ask_hints(need, seeds, products, model, threshold, max_asks) -> tuple[list[AskHint], JueOutput]`：WP-I 接入 L1 链路时直接用。

### 5. 基线模板 `config/baselines/`
- `b1_required/ask_slot.yaml`：必问清单（`required` 且未填就问）；
- `b2_info_value/ask_slot.yaml`：信息价值规则（`splits ≥ 2` 就问，不看先验）；
- `rule_alert/`：三类定时发现的常见告警写法（如同一现象升级 ≥ 3 次、任一试样失败、被拦截 ≥ 3 次）——**合理、不刻意弱化**，汇报中列出供人审阅。

## 验收
`tests/test_wp_b1.py` 只有 1 个测试：
- 小种子，手写一段事件：3 个客户 4 次「锦纶氨纶 + 气流染色机」色花升级（注入）；困难负样本两种——同一个客户就另一个无解需求反复升级 3 次、同现象 3 次成功推荐 `T-205`；`scan` 只发布 1 个 `opportunity` 问题，对象是注入的主题；
- 同一测试中：`realtime_state` + `ask_hints` 在「只知道色花」时给出 `fiber` 和 `equipment` 的提示；
- 全过程 `MockGateway` 调用次数为 0（传入一个调用即失败的网关替身也可以）。

## 不做
Jue-K（WP-B3）、模拟数据生成（WP-B2）、接入 L1 链路（WP-I）、大模型轮询基线（WP-E，可选）。
