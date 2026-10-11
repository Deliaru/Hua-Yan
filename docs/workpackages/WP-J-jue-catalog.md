# WP-J 觉：决策目录、会话与需求单对象、统一循环里的发现

> 负责：B｜时段：T+4～16（第 1 步 T+4～8 先交付，门面联调依赖它）｜分支：`dev/b`
> 依据：`REPLAN-v5.md` 第 4 节（D4、D5、D8、D9、D17～D20、D22）、契约 v5.1 第 ⑤ ⑥ ⑧ ⑨ 节、`WP-0v5.md` C1、C2、C5、C12、C13

## 目标

把觉从「链条两头的告警器」改成**全过程的决策点发现器**：业务里每个「谁要决定什么」都是决策目录里的一个模板，觉在每次状态变化后对受影响的「决策 × 对象」打分，超过阈值就提出问题，问题带着主人（谁准备）和签字人（谁签）进总线。流程靠这个循环往前走（铁律 14）。

本包只做「发现」：构建对象属性、写模板、打分、发布问题、按新语义重跑模拟业务周与 Jue-K 定时三类、统计目录飞轮的数据。**写后触发、问题处置、草稿、签字都在门面（WP-C）**；本包不碰门面和 Agent。

## 依赖

- 契约 v5.3（已在 main；机会汇聚的合并见 `WP-0v5.md` C14，现成产品由研发审定见 C15）。
- WP-C 第 1 步的 `leak_hits`（`escalation/translate.py`）：A 单独提交、尽早合入 main；合入前 `n_leak_hits` 先按 0 构建，**不另写一份匹配逻辑**。
- 总线 `set_prepared` 与问题事件的 `template_id` / `by` 已在 main 补齐（`bus.py`，本包只读）：模拟业务周按 `prepared_at` 判断待签，第 5 项的处置关联读这些事件字段。
- 第 3、4 步（重跑模拟业务周、重训 Jue-K）依赖 WP-C 的门面合入。

## 必读

`REPLAN-v5.md` 第 4 节全部；`CONTRACTS.md` 第 ⑤（5.1～5.4）、⑥、⑧、⑨ 节；`WP-0v5.md` C1、C2、C12、C13；现有 `src/huayan/jue/`（`state.py`、`proto.py`、`publish.py`、`jue_k.py`）。

## 允许修改的范围

`src/huayan/jue/`、`config/templates/`、`config/baselines/`（只做第 2 项末条的格式迁移）、`src/huayan/sim/`、`src/huayan/eval/week.py`、`src/huayan/eval/catalog.py`（新）、`scripts/make_jue_k_data.py`、`scripts/train_jue_k.py`、`scripts/eval_jue_k.py`、`scripts/run_week.py`、`scripts/catalog_stats.py`（新）、`models/jue_k/`、`data/week/`、`tests/test_wp_b1.py`、`tests/test_wp_b2.py`、`tests/test_wp_b3.py`、`docs/JUE_K_TRAINING.md`、`docs/reports/`

不改：`app.py`、`agent/`、`l1/`、`escalation/`、`ui/`、`web/`、契约。

## 交付物与已定设计

### 第 1 步（T+4～8，先合入）：对象、模板、发布

**1. 状态构建 `jue/state.py`**

- `session_state(sess, events, at) -> JueState`：一个 `session:<id>` 对象，属性按契约 5.2 的 session 表；`p_none`、`p_top`、`n_candidates` 取本会话最近一次 `match` 事件。
- `requirement_state(req, need, seeds, kb, at, events) -> JueState`：签名按契约（增加 `events`）；除原有 slot 对象外，**总是**产出一个 `requirement:<id>` 对象，属性按 5.2 的 requirement 表，加上 v5.1 的 `reuse_checked`、`reuse_pending`、`reuse_declined`；`status` 为 `released` / `rejected` / `reused` / `merged` 的需求单不构建。
  - `n_leak_hits` = `leak_hits(sheet.sheet + "\n" + sheet.usage, req.sealed, req.hypotheses, kb)` 的**去重句序号数**，没有说明书时为 0。
  - `n_unmapped_constraints`、`n_unquoted_items`、`n_edited_uncovered` 按契约 5.2 的定义算，只算计数，不放文本。
- 主题对象（定时）：`open_project` 改为「该主题有 `rd_accepted` / `rd_confirmed` 的需求单且未发布」，由 `requirement_accepted` 与 `product_released` 事件算（`requirement_confirmed` 已删除）；`n_escalations` 只统计 `escalate` 事件（业务员签字后才写），且**只计复用检查已关闭且没有现成产品的那些**：所在需求单有 `product_id` 为空的 `reuse_proposed`，或有 `reuse_declined`；复用还没查完的、被 `reuse_adopted` 的都不计入（第二位客户升级后，要等产品经理 Agent 查完现成产品，机会汇聚才可能到点，否则会在复用卡前抢先提出）；`requirements_merged` 事件与立项一样计为该主题的「已处理」时刻（沿用现有 `handled` 机制），合并后不会再次到点。主题 id 一律用 `theme_id()`，门面给机会汇聚填候选需求单（`requirement_ids`）时也调它。

**2. 模板 `config/templates/`**（每个 family 一个文件；新增 10 个，原 5 个只核对 `kind` / `signer_role`）

| 文件 | kind | 对象 | 前置条件（建议写法，属性名以契约 5.2 为准） | owner | signer |
|---|---|---|---|---|---|
| `escalate_need` | advance | session | `attrs.phenomenon_known and attrs.top_is_none and not attrs.escalated` | sales | sales |
| `reuse_product` | advance | requirement | `attrs.status == "draft" and not attrs.reuse_checked` | pm | rd（C15） |
| `accept_requirement` | advance | requirement | `attrs.status == "draft" and attrs.reuse_checked and not attrs.reuse_pending` | pm | rd |
| `distortion` | anomaly | requirement | `((attrs.layer == 2 and attrs.n_product_items >= 1) or (attrs.layer == 3 and attrs.n_chem_items >= 1)) and (attrs.n_unmapped_constraints >= 1 or attrs.n_unquoted_items >= 1)`（空单、刚接单还没有条目时不到点） | pm（layer 2）/ rd（layer 3）见下 | rd |
| `confirm_translation` | advance | requirement | `attrs.status == "rd_accepted"` | rd | rd |
| `contribution` | advance | requirement | `attrs.n_edited_uncovered >= 1` | rd | rd |
| `market_eval` | advance | requirement | `attrs.trial_passed and attrs.market_eval == "none"` | sales | sales |
| `seal_points` | advance | requirement | `attrs.market_eval == "pass" and not attrs.points_set` | rd | rd |
| `seal_leak` | anomaly | requirement | `attrs.n_leak_hits >= 1` | rd | rd |
| `release` | advance | requirement | `attrs.points_set and not attrs.released`（说明书由主人在准备阶段写，不作前置条件） | pm | rd |

- 全部规则打分：`rule_score: "1"`（前置条件通过即 1.0，觉视图画「到点」阶跃）。
- `distortion` 的主人随层：模板只能写一个 `owner_role`，写 `pm`；layer 3 的失真由 `publish` 按「layer 3 → rd」改写主人（写在解析表里，一行；已确认）。
- 每个模板的 `decision_label` / `title` / `worth_prompt` 用业务语言写（「研发是否接单」「是否有现成产品可用」），不出现属性名。
- **基线迁移 `config/baselines/`**：`b1_required`、`b2_info_value` 的 `ask_slot` 与 `rule_alert` 的三个模板按新格式补 `kind`（与 `config/templates/` 同 family 一致），`rule_alert` 的 `owner_role` / `signer_role` 与同 family 新模板一致（`opportunity`：pm / rd；`knowledge_conflict`：rd / rd；`leak_risk`：supervisor / supervisor），`ask_slot` 不填 `signer_role`；前置条件、打分与阈值一字不改（它们是对照组）。`eval/week.py` 与 `scripts/eval_ask_policies.py` 加载这三个目录不报错即可，脚本不改。
- `opportunity`（D19，契约 v5.2 / C14）：`decision_label` 改为「同类需求是否合并立项」，`signer_role: rd`；`worth_prompt` 里「已转给产品经理」改为「已转给产品经理 Agent」。前置条件不变。

**3. 发布 `jue/publish.py`**

- 所有 `p_need ≥ threshold` 且模板 `signer_role` 不为空的组合生成问题，不再区分实时 / 定时；`ask_slot` 仍只走 `select_asks`，`ask_back` 照旧发布（提示类，`signer_role` 为空，进总线但不进待签）。
- 填 `template_id`、`signer_role`，按契约 C1 的解析表填 `owner_id` / `signer_id`。解析所需的 id 由门面经 `refs` 传入（`sales_id`、`assigned_rd`）；knowledge 对象的归属研发从种子产品取，theme 对象的研发取 `refs.assigned_rd`（C14），supervisor 取 id 最小的主管。
- 加载模板时校验：family 唯一、`object_type` 合法、`kind` 合法；引用未加载 family（不在本次加载的模板目录里）的 `ScoredDecision` 直接抛错，不写死 family 枚举。
- `huayan/jue/` 不 import 网关（铁律 3），也不 import `huayan.app`。

**4. 打分来源 `jue/proto.py`、`jue/jue_k.py`**

- 10 个新模板一律规则打分（前置条件到点），不走 Jue-K，也不走 OneJev（概率未校准，REPLAN 4.7）。
- 两种模式，由配置 `realtime_model` / `scheduled_model` 选：
  - **`jue_k`（演示与模拟周用这个）**：五类有样本的决策按第 8 项新训练的 Jue-K 打分；新模型没覆盖或评估输给规则的 family **回落到规则打分，不回落到 OneJev**。这个模式下觉不发出任何大模型或 OneJev 调用。
  - `jue_proto`（对照与降级）：`JueProto` 对原有的 `knowledge_conflict`、`leak_risk`、`opportunity` 在 OneJev 可用时用 OneJev 打分，其余规则；状态条标「觉：原型」。
  - 同一次输出里**逐条**填 `ScoredDecision.scored_by`。
- 觉视图底部的 `n_llm_calls` 由门面统计计量中 caller 以 `jue` 开头、`kind` 不是 `jue` 的记录（网关调用与 OneJev 调用都算）：`jue_k` 模式下为 0，`jue_proto` + OneJev 时如实显示次数。不改契约。
- 读取函数 `jue/records.py: load_records(run_dir) -> list[JueRecord]` 也放在这一步交付（WP-C 的觉视图要用）。

### 第 2 步（T+8～12）：处置关联与目录飞轮的数据

**5. JueRecord 与处置关联**：门面写的 `jue_samples.jsonl`（JueRecord）+ `question_published` / `question_resolved` 事件（带 `template_id`、`action`、`by`）就是全部数据；本包在 `jue/records.py` 再加 `outcomes(events) -> dict[question_id, action]`，供统计复用。不另存一份标签。

**6. 目录飞轮统计 `eval/catalog.py` + `scripts/catalog_stats.py`**

- 按模板统计：提出次数、签字（`sign` / `accept`）、退回、`dismiss`（被忽略；机会汇聚中「产品经理 Agent 判断不是同一件事后被 dismiss」单列，不算觉提多了）、异常类自动关闭数、被忽略率；定时三类另按注入清单算误报率。**只报计数与比率，不给阈值建议**（模拟周的处置是脚本定的，按它调阈值是循环论证）。
- `human_decision` 事件按「动作 × 对象类型」计数，列出每组的属性快照均值。**不做聚类、不生成候选模板**（第 3 阶段，只写进材料）。
- 输出 `runs/<run_id>/catalog_stats.json` 与一页 `docs/reports/catalog_stats.md`。

### 第 3 步（T+12～16，依赖 WP-C 合入）：按新语义重跑

**7. 模拟业务周 `eval/week.py`**（C12）

- 模拟周照常走真实链路；推进类问题由「模拟人」在问题进入待签后签字，模拟退回率为 0；模拟周不产生 `human_decision`：
  - 业务员：`escalate_need` 即签；`market_eval` 录「通过」；
  - 研发：`reuse_product` 进入待签（只有现场产品经理 Agent 找到产品时才会有）即审定采用；离线路径一律「无现成产品」，模拟周里不出现；
  - **研发只接机会汇聚指向的需求单**：`accept_requirement` 在没有 `opportunity` 指向该单时不签（保持待签）——否则首次升级就被接单，`open_project` 一直为真，机会汇聚永远不到点；机会汇聚进入待签后，模拟研发签字合并（合并建议由 hub 离线路径起草），再接主单；
  - 接单后：`confirm_translation` 即签 → 1 个业务日后由模拟 ELN 录入试样通过（沿用现有 `record_trial`）→ `market_eval` → `seal_points`（模拟对外要点）→ `release` 即签；
  - **定时三类的处置顺序**：问题进入待签时先查注入清单（`sim/`、`eval/` 可读，铁律 5）——在清单里的按上面签（机会汇聚签合并、知识冲突更新适用表、拼凑冻结），不在清单里的一律 `dismiss`；「同一客户反复升级」这类困难负样本不在清单里，因此不会被签合并。`dismiss` 给目录飞轮统计提供被忽略率。
- 删除 `_handle` 里的 `approve_project`、`confirm_requirement` 调用；立项 ≡ 研发接单。
- 起草与「无现成产品」都由门面的 hub 离线路径完成（WP-C），本包不写起草逻辑，也不另记复用结果。

**8. 训练新的 Jue-K（D20）**（第 4 项 `jue_k` 模式的模型来源）：不沿用旧模型与旧数字，五类全部按 v5 语义重新生成样本、训练、评估。
- 实时两类（追问、回问）：`sim/trajectory.py` 改走 v5 链路（业务员签字升级 → 空单 → 产品经理 Agent 起草 L2 → 研发接单 → 起草 L3），**回问样本取 L2、L3 起草时的需求单状态**，标签沿用「补上真实值后本层转化对照的命中是否改变」；
- 定时三类（机会汇聚、知识冲突、拼凑）：用第 7 项重跑的模拟业务周事件生成样本；
- 评估：每类 AUC、Brier、ECE，与规则打分在同一组合上对比；**新模型赢的用模型，输的回落规则**，结论写进 `docs/JUE_K_TRAINING.md`；阈值按类校准（回问不再借用追问的阈值）；
- 重跑 w1，在文档与报告里**替换**旧的「3/3 命中、0/4 误报」，新数字是多少写多少；做不完则材料中不再引用 w1 数字（REPLAN 7.2 可砍清单最后一项）。
- 新增的推进类不训练；失真、对外泄密的注入与标签属于阶段 2。

### 附：单卡对照样例

B 在 T+8 前交付 `web/src/fixtures/single_card.json`，属于 WP-E2 第 1 步（见 `WP-E2-single-card.md`），不在本包范围内。

## 验收

1. `tests/test_wp_b1.py`（仍 1 个测试，小种子，零网络）：
   - 加载模板目录：15 个 family 全部通过校验，`config/baselines/` 三个目录也能加载；构造一条引用未加载 family 的 `ScoredDecision`，`publish` 时被拒（合法 family 由已加载的模板目录定义，代码里不写死 family 枚举）；
   - 构造 4 个需求单状态（刚建单未查复用、已查无产品、有待签复用建议、已接单），`propose` 后只有对应的推进决策到点：`reuse_product` → `accept_requirement` → 无 → `confirm_translation`；
   - 原有「定时发现命中注入、不碰困难负样本」照旧通过；
   - 计量里 caller 以 `jue` 开头的大模型调用为 0。
2. `test_wp_b2`、`test_wp_b3` 通过（b3 当前因门面仍用 `jev` 升级而失败，WP-C 合入后再确认；手算样例若因新语义变化，改样例并在汇报里说明）。
3. 真实跑一次：`run_week.py --week data/week/w1`（WP-C 合入后），贴出每个推进决策的提出次数、自动签字次数、机会汇聚命中 / 误报；`catalog_stats.py` 输出一页报告（含定时三类的被忽略率）。
4. 汇报里贴一张「模板 → 前置条件 → 打分来源」表，与 REPLAN 4.3 逐行对照；再贴新 Jue-K 五类的评估表（模型 vs 规则，最终用哪个）。

## 不做

写后触发与问题处置（WP-C）；草稿与起草逻辑（WP-C）；觉视图的接口与界面（WP-C、WP-U2）；决策目录的自动挖掘与候选模板生成；停滞、解密时机等第二档决策（T+16 决定）；单卡对照的数据接口（WP-E2，样例除外）；新增测试文件。
