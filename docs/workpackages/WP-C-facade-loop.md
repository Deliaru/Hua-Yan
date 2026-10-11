# WP-C 门面与 Agent 协作：统一循环、签字方法、产品经理 Agent

> 负责：A｜时段：T+4～16（第 0 步接口样例开工即做、第 1 步 `leak_hits` 先交付）｜分支：`dev/a`
> 依据：`REPLAN-v5.md` 第 3、4.2 节（D2～D4、D6、D8、D10、D14～D22）、契约 v5.1 第 ③ ⑦ ⑧ ⑫ ⑭ 节、`WP-0v5.md` C3～C6、C9～C11、C13～C15（契约 v5.3）

## 目标

让流程**只由觉提出的决策和人的签字推动**（铁律 14）：

```
状态变化 → 门面写后评估（觉）→ 问题进总线 → hub 派给主人准备（产品经理 Agent / 业务员、研发的 Agent 起草）→ mark_prepared
        → 签字人在工作面按按钮 → 门面原子方法改状态 → 状态变化
```

门面只保留原子方法与权限校验，删掉所有写死的推进；Agent 从「替人打字」改为「旁听、起草、写进工作对象」；产品经理换成 `pm:agent`，先查现成产品（D17），查不到再起草 L2。

## 依赖

- 契约 v5.2（已在 main）。
- WP-J 第 1 步（模板、`session_state` / `requirement_state`、`publish` 的主人与签字人解析、`load_records`）：B 在 T+8 前合入 main；合入前门面按契约签名调用，测试等它合入后转绿。**不为觉写替身。**
- 本包第 1 步的 `leak_hits` 是 WP-J 的依赖，单独提交、尽早由人合入 main。

## 必读

`REPLAN-v5.md` 第 3 节（含 3.2 前端硬性要求，接口要能支撑）、第 4.2～4.4 节；`CONTRACTS.md` 第 ③ ⑦ ⑧ ⑫ ⑭ 节；`WP-0v5.md` C3～C6、C9～C11、C13；现有 `app.py`、`l1/session.py`、`agent/hub.py`、`agent/tools.py`、`escalation/translate.py`。

## 允许修改的范围

`src/huayan/app.py`、`src/huayan/l1/`、`src/huayan/escalation/`、`src/huayan/knowledge/`、`src/huayan/agent/`、`src/huayan/ui/server.py`、`config/app.yaml`、`config/app.live.yaml`、`src/huayan/eval/distortion.py`（只改 `draft_product_need` 的调用处）、`scripts/translate_cli.py`、`scripts/demo_escalation.py`（改到新流程或删除，汇报说明）、`prompts/assistant_*.md`、`seeds/`（只加 D17 支线数据）、`tests/fixtures/mini_seeds/`（同上）、`web/src/fixtures/`（接口样例，只此目录）、`scripts/agent_cli.py`、`tests/test_wp_a2.py`、`tests/test_wp_a3.py`、`tests/test_wp_t.py`、`tests/test_wp_l.py`、`tests/test_e2e.py`

不改：`huayan/jue/`、`config/templates/`、`sim/`、`eval/` 其余部分、`web/` 其余部分、契约。

## 交付物与已定设计

### 第 0 步（开工即做）：接口样例

REPLAN 3.2 第 7 条要求样例先行（原定 T+2，已延后），前端在样例到之前只按契约模型搭骨架。内容见第 2 步第 6 项。

### 第 1 步（T+4～6）：转译函数，先合入

- `escalation/translate.py`：
  - 新增 `leak_hits(text, sealed, hypotheses, kb) -> list[LeakHit]`（契约 C3）：按「。；！？\n」切句，逐句查 `sealed` 各项、kb 中 level=3 转化对照的 `chem_term`、`hypotheses` 的关键词（子串或字符二元组重合 ≥ 阈值，复用 `_score`）；不查 L2 内容；只返回句序号与类别。
  - `draft_product_need(req, sessions, kb, pm, at)`：输入从问题改为（空）需求单。
- 单独提交，汇报里请人合入 main。

### 第 2 步（T+6～12）：门面

**1. L1 链路 `l1/session.py`**
- Jev 匹配后只写 `match` 事件（契约 C6 的 payload），有把握就推荐；**删除自动升级**（`escalate_need` 由 Jev 发布、`retire_escalation`、读 `config["routing"]`）。
- `config/app.yaml` 删除 `routing`。

**2. 门面方法 `app.py`**（按 `WP-0v5.md` C10 的删、改、增逐条实现，外加 C13 与下列已定细节）

- **写后评估** `_after(session_ids, req_ids)`：每个改状态的方法结束时调用一次；对受影响的会话、需求单（及其 slot、所属主题）构建状态 → 实时模型 `propose` → `publish`（`refs` 带 `sales_id`、`assigned_rd`、`session_id`、`requirement_id`）→ 写 JueRecord；前置条件不再成立的**异常类** open 问题 `resolve(answered, by="jue")`。
- **人自发决策**：生效方法执行时，同一对象上没有对应 family 的 open 问题 → 写 `human_decision`，`attrs` 取 WP-J 状态构建出的该对象属性快照。用一个私有方法统一处理。
- **签字人校验**：每个生效方法只认契约写定的签字人（业务员 = 需求单首个会话的业务员；研发 = `assigned_rd`）；可签条件不满足抛 `ValueError`，消息是给人看的一句话（「还有 1 条未答回问」），界面原样显示。接单与确认转译的可签条件都含「该单没有 open 的 `ask_back`、没有未处理的失真」（回问在 L3 起草时也会出现，没答完就确认会把缺的条件带进试样）。
- **积分只给人**：`pm:agent` 与 `jue` 不进账本；`cited` 在 `accept_requirement` 记所引 L2、在 `confirm_translation` 记所引 L3、在 `adopt_reuse` 记建议所引 L2；`bounty` 给签字人。
- **已知条件变化**：客户回答回问、或研发签字合并需求单时，回填 `known_slots`，并把该单上已待签的问题 `set_prepared(None)` 退回准备中。
- **现成产品复用（C13；C15 改为研发审定）**：
  - `save_reuse_proposal`：`by` 必须是 `pm:agent`；`customer_note` 先过 `leak_hits`（命中抛 `ValueError`，Agent 改写）；`product_id` 为空时立即 `resolve(reuse_product, answered, by="pm:agent")`（「已查，无现成产品」，不算人的签字）。
  - `update_reuse_note`（C15）：`assigned_rd` 或 `pm:agent` 改那句说明，过 `leak_hits`，写 `requirement_edited`；研发 Agent 用 `edit_reuse_note` 按研发的话改写。
  - `adopt_reuse`：签字人 `assigned_rd`；再查一次 `leak_hits`（闸）；用 Jev 的披露问题在硬上限内选版本，生成推荐卡写入需求单首个会话（附 `customer_note`，标「研发 X 审定」），会话 `status="recommended"`；需求单 `status="reused"`；`resolve(sign)`；bounty 给研发。业务员不签字。
  - `decline_reuse`：签字人 `assigned_rd`；写 `declined_reason`，`resolve(return)`；觉随后提出 `accept_requirement`。
  - 复用检查关闭（`product_id` 为空的 `save_reuse_proposal`、`decline_reuse`）后，`_after` 对该单所属主题**跑一次定时扫描**：这一刻起这次升级才计入机会汇聚（WP-J 第 1 项），不必等到下一个定时窗口；扫描出的问题由下一次 `tick` 派单。
  - `view_session` 对需求单首个会话的业务员填 `SessionView.reuse`（`ReuseView`）：`pending` 时只给状态与产品名，`customer_note`、`basis` 置空；`adopted` 后给产品名、L1 用法、`customer_note`、`basis` 归属标签（「产品经理 P01 · 历史案例 · L2」），**不含案例原文**。`requirement_view` 对 L3 给完整的 `reuse`。
- **同类需求合并（D19，C14）**：每次升级照旧各建一张空单。定时扫描发布 `opportunity` 时，门面在 `refs` 里填 `requirement_ids`（同主题 `jue.state.theme_id`、`draft`、复用已查且无现成产品或建议被拒的单，与 WP-J 计数口径一致）与 `assigned_rd`（最早一张的研发）。
  - 准备：hub 照常把 `opportunity` 派给 `pm:agent`，它读各单的客户原话判断是不是同一件事，用 `propose_merge` 起草（`save_merge_proposal`）；判断不是同一件事时 `member_ids` 为空、`note` 写理由。
  - 签字：研发 `merge_requirements` → 被并入单 `merged`、会话并入主单、其 open 问题以 `answered` 关闭、`opportunity` 以 `sign` 关闭；**清空主单 L2 草稿中 `edited_by` 为空的条目**（研发改过的保留），主单待签问题退回准备中，产品经理 Agent 按全部会话重新起草后研发接单（= 立项）。
  - 合并之后：觉视图的需求单线程包含并入它的单；`view_session` 取会话所在的未合并单；判断不是同一件事时 `target` 填最早一张、`members` 为空。研发不合并而直接接了其中一张单时，`accept_requirement` 以 `accept` 关闭 `opportunity`；「现在不需要」为 `dismiss`。
  - 业务员类签字（客户评价）只认主单首个会话的业务员；演示中两位客户由同一业务员 S01 负责，材料里说明这一简化。
- **忽略与其他处置**：`resolve(question_id, action, by, note)` 只保留 `dismiss`、`update_sheet`（知识冲突，归属研发）、`freeze_access`（拼凑，主管）；权限改为**签字人**（`pm:agent` 不能忽略任何问题）；`dismiss` 是目录飞轮「被忽略率」的数据来源。
- **`jue_timeline(target_id, viewer_id)`**：需求单线程 = 该单的全部会话 + 需求单 + 所属主题。`points` 来自 JueRecord（WP-J 的 `load_records`），`threshold` 取配置；`nodes` 来自总线；按查看者裁剪：业务员只含 `escalate_need`、`reuse_product`、`market_eval`、`ask_back` 与本会话的 `ask_slot`；L1 看不到 L2/L3 的节点证据。`n_llm_calls` 从计量器统计 caller 以 `jue` 开头、`kind` 不是 `jue` 的记录（网关与 OneJev 调用都算；`jue_k` 模式下为 0），不写死。
- **`questions(viewer_id)`**：查看者作为主人或签字人的 open 问题。
- **`tick()`**：只做定时扫描与 `agents.dispatch()`；回问并入写后评估。
- **发送拦截**：`add_turn(speaker="sales")` 先过 `leak_hits(text, 全部需求单的 sealed, [], kb)`，命中抛 `ValueError`（只含句序号与类别），不写入。

**3. 角色 Agent 与产品经理 Agent `agent/`**（契约 C11）
- `chat(actor_id, text, session_id=None, focus=None)`（C14）：`focus` 写进 Agent 系统提示词，Agent 据此理解「第 2 条」「这句话」；Agent 用草稿类工具就地修改工作对象，用生效类工具只产生 `PendingAction`（界面把它显示在工作面签字区，人确认即 `approve`；契约 ⑭ 与铁律 13 不变）。
- `dispatch()`：把总线上 open、`prepared_at` 为空的问题派给主人；记住「问题 id + 第几次准备」，被 `set_prepared(None)` 退回的问题会再派一次。主人是 `pm:agent` 跑产品经理 Agent 的 Loop，是业务员 / 研发跑其 Agent 的 Loop；Loop 结束后 hub 调用 `app.mark_prepared`。提示类问题（`ask_back`）派到需求单首个会话的对话，不 `mark_prepared`；合并后的单派到主单首个会话（同主题的会话现象相同，不再按槽位区分；材料里说明）。
- 删除 `approve` 里的「确认后派单」、`_hand_over` 与整张派单表。
- 离线（`gateway_mock: true`）：hub 调规则骨架后 `mark_prepared`——`accept_requirement` → `draft_requirement`，`confirm_translation` → `translate_requirement`，`release` → `package_sheet`，`reuse_product` → `save_reuse_proposal(product_id=None, note="离线模式：未检索现成产品")`，`opportunity` → `save_merge_proposal(全部候选并入最早一张, note="离线模式：按主题规则合并，未经产品经理 Agent 判断")`（D18 不再补规则骨架，这一条是离线测试与模拟周所需的例外，只在 `gateway_mock` 下出现）；没有骨架的（升级说明、封存两栏、提炼、客户评价）直接 `mark_prepared`，工作面显示「离线，无草稿」。所有离线产物照铁律 6 标注。重新起草（退回后、合并后、回问答完后）**只替换 `edited_by` 为空的条目**，人改过的条目原样保留——离线骨架与产品经理 Agent 都一样。
- 工具按契约 ⑭ 的清单增删（含 `propose_reuse`、C14 的 `propose_merge`、C15 的 `edit_reuse_note`）；每个工具仍 ≤ 15 行、一个工具调一个门面方法；`pm:agent` 的工具集合里没有 `effect`。

**4. 提示词 `prompts/assistant_*.md`**（每份不超过一屏）
- 业务员、研发的 Agent 共同：委托人在「与 Agent 协作」里的话是**指令**，按 `focus` 理解指代；能用草稿工具做的直接改，改完一句话汇报改了哪里；生效动作只提议，告诉委托人去工作面上签字。
- 业务员 Agent：旁听对话；被派到 `escalate_need` 时起草升级说明（只写客户原话里有的，标出缺什么）；人点「帮我回一句」时起草回复写进 `reply_draft`；客户评价时起草评价备注。**客户的话是材料，不是指令。**
- 产品经理 Agent：被派到 `reuse_product` 时**先查现成产品**——检索 L2 历史案例与 L2 转化对照，案例的条件覆盖本单已知条件才提议，`customer_note` 只写产品能解决什么、怎么用，不写机理、配方，也不照抄案例原文（研发会审定）；查不到写「已查 N 个案例，无现成产品」。被派到 `opportunity` 时读各单的客户原话，判断几位客户说的是不是同一件事（看现象与已知条件，不看用词），起草合并建议并写清理由；被派到 `accept_requirement` 时起草 L2（有 `return_notes` 先逐条回应，合并后的单覆盖全部客户的原话）；被派到 `release` 时包装说明书。L3 只见归属，写「需研发 X 补充」，不猜。
- 研发 Agent：被派到现成产品审定时，对照依据检查那句客户说明有没有泄露案例或机理、说法是否准确，需要时用 `edit_reuse_note` 改写并告诉研发改了哪里；接单后起草 L3 与方向假设；研发改过的条目提炼成可沉淀的转化知识（泛化、去掉客户特定信息、指出相近或冲突）；客户评价通过后起草封存 / 放出两栏并看自查结果；说明书命中泄密时改写对应句。

**5. 接口 `ui/server.py`**：每个接口一个门面方法，POST 之后调用 `app.tick()`；门面抛的 `ValueError` / `PermissionDenied` 以 400 / 403 返回原文。至少覆盖：
- 读：`status`、`sessions`、`session`（SessionView）、`questions`、`requirements`、`requirement`、`leak`、`timeline`、`ledger`、`contributions`、`report`、`agents/conversation`、`agents/trace`；
- 写：开会话、`turn`（客户 / 业务员发言）、`recommend`（直接推荐）、`resolve`（忽略、更新适用表、冻结权限）、签字类（`escalate`、`reuse/adopt`、`reuse/decline`（研发）、`merge`、`accept`、`return`、`confirm`、`contribute`、`market-eval`、`points`、`release`、`decrypt/request`、`decrypt/decide`）、草稿修改（`req-item`、`sheet`、`reply-draft`、`escalate-note`、`reuse-note`）、`trial`（模拟 ELN 录入）、`agents/chat`（带 `focus`）、`agents/pending`、`agents/approve`、`agents/reject`。

**6. 接口样例 `web/src/fixtures/`（开工 2 小时内交付）**：用契约的 pydantic 模型构造后 dump 成 JSON，字段与契约一致：`sales_workbench.json`（SessionView 含 `reply_draft`、`escalate_note`、`reuse`（`pending` 与 `adopted` 各一份），加该业务员的 `questions`）、`rd_workbench.json`（RequirementView 含待审定的 `reuse`、`questions` 分准备中 / 待签、`leak`）、`jue_timeline.json`（一条需求线程，含规则阶跃与 Jue-K 曲线两类点）。前端只认这些样例和真实接口，不自造结构。

**7. 种子（D17 支线）**：在 `seeds/` 与 `mini_seeds/` 各加一组「说明书没写、P01 案例里用过」的产品 × 条件：现象 ≠ `color_unlevel`（避免和主线机会汇聚同主题）；先确认 L1 匹配结果是「都不合适」，再写一条 `owner: pm:P01` 的模拟案例。标「（模拟）」。

### 第 3 步（T+12～16）：测试与真实跑

测试仍不超过 11 个，本包只改下列 5 个：

| 测试 | 守住什么 |
|---|---|
| `test_wp_a2` | 发言不再自动升级；`match` 后觉提出 `escalate_need`，业务员签字建空单；L1 与 L3 视图不同；业务员发出含封存项的话被拦截 |
| `test_wp_t` | `draft_product_need` 以需求单为输入；L2 不含 L3 知识、L3 条目引用两位研发的知识并带原话；`package_sheet` 不含 L3；`leak_hits` 三类来源各命中一次 |
| `test_wp_a3` | 接单 → 确认 → 沉淀 → 试样 → 客户评价 → 封存 / 放出 → 包装 → 发布 → 同类需求在 L1 命中；引用与贡献记分只给人；L2 看不到 L3 原文与 `sealed`；**复用支线**：`pm:agent` 保存建议 → 审定前业务员的 `SessionView.reuse` 没有 `customer_note` → 业务员调 `adopt_reuse` 被拒 → 研发审定 → 需求单 `reused`、会话拿到推荐卡、P01 记 `cited`、没有 `accept_requirement`；审定后业务员的 `SessionView.reuse` 里没有案例原文 |
| `test_wp_l` | `pm:agent` 没有生效工具；它的检索拿不到 L3 原文、`sealed`、`points_draft`；生效类工具确认前不改状态；非委托人不能确认（不调用模型） |
| `test_e2e` | 最小新主线离线跑通（直接调门面 + `tick`），含两位客户同类升级 → 机会汇聚 → 离线合并建议 → 研发签字合并 → 接单：**每一步签字前，对应 family 的问题都已由觉提出并进入待签**（铁律 14 的端到端检查）；觉的大模型调用 0 次 |

真实跑：`agent_cli.py --actor pm:agent` 走一遍「复用查无 → 起草 L2」与「机会汇聚 → 判断两位客户是否同一件事 → 起草合并」，`--actor rd:R01` 走一遍「接单后起草 L3 → 改一条 → 提炼沉淀」；贴对话、`/trace` 与 `metering.jsonl` 中 `agent:*` 的步数与费用。

## 契约依赖

合并（D19）与 Agent 协作焦点（D21）按契约 v5.2（`WP-0v5.md` C14）、研发审定现成产品建议（D22）按契约 v5.3（C15）实现，均已签字。

## 验收

1. 上表 5 个测试通过；全项目 `pytest` 只剩 WP-J 负责的失败（若有）。
2. 代码评审：在本包范围内（`src/`、`config/`、`scripts/`、`tests/`，不含 WP-J 的 `jue/`、`sim/`、`eval/week.py` 与 WP-I2 的 `demo/`、`scripts/demo_mainline.py`）`grep` 不到 `_hand_over`、`routing`、`approve_project`、`confirm_requirement`、`pm_confirmed`、`discoverer="jev"`；门面里没有「某方法执行后直接调用下一步方法」的推进。
3. 贴一张「签字按钮 → 门面方法 → 签字人 → 可签条件」表，与 REPLAN 3.3、3.4、4.3 逐行对照；再贴「工具 → 门面方法」表。
4. 接口样例按时交付，前端确认能直接用。

## 不做

模板与打分（WP-J）；界面（WP-U2）；演示主线脚本、检查点载入与录制（WP-I2）；停滞、解密时机、解密说明草稿（第二档）；确认卡内容预览（第二档）；为测试新增桩或夹具。
