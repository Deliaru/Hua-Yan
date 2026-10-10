# WP-I 集成：觉接入链路、定时扫描与处置、角色助手与派单、演示主线

> 负责：A＋B（A 改 `app.py` 与 `l1/`，B 改 `jue/`、`agent/` 与脚本）｜时段：5:00–5:45｜在 `main` 上进行

## 目标
把各条线接起来：觉替换 L1 链路中的追问替身；定时扫描与处置进入门面；角色助手挂上门面、问题自动派给对应人的助手；用脚本跑通完整演示主线——离线版（直接调用门面）和现场版（自然语言指挥助手）各一遍（M2）。

## 依赖
WP-A1/A2/A3、WP-B1/B2、**WP-B3 第 ① 段**、WP-T、WP-L 合并进 `main`。B3 第 ②③ 段之后单独合并，`jue_k` 的热替换在那之后验证。

## 必读
`CONTRACTS.md` 第 ⑤、⑥、⑫、⑭ 节；`workpackages/README.md` 的首版 Demo 验收。

## 允许修改的范围
`src/huayan/app.py`、`src/huayan/l1/session.py`（只删除替身、接入觉）、`src/huayan/jue/`、`src/huayan/agent/`（只修集成中发现的问题）、`scripts/demo_mainline.py`、`demo/mainline.yaml`、`tests/test_e2e.py`、`tests/test_wp_a2.py`（只改替身相关的一行）、`config/app.yaml`、`seeds/translations.yaml`（只为主线回问补 1～2 条）

## 交付物与已定设计

### 1. 实时觉接入（A）
- `HuayanApp.build` 按 `realtime_model` / `scheduled_model` 分别构造 `JueProto(..., mode=...)` 或 `JueK(jue_k_dir, templates_dir, mode=...)`；`system1_impl == "onejev"` 时原型用 Jev 打分，否则规则模式。
- `l1/session.py` 删除替身，改用 `huayan.jue.publish.ask_hints`；每轮的 `JueOutput` 存入门面，`jue_trace` 返回。
- **数据引擎**（契约 v4）：门面每次调用觉（实时每轮、定时每次扫描、每次回问评估），都把 `JueRecord(state, output)` 追加到 `runs/<run_id>/jue_samples.jsonl`。

### 2. 定时扫描与处置（A 写门面，B 核对状态构建）
- `scan(at)`：调用 `huayan.jue.scan.scan`，模型为 `JueProto(templates_dir, system1, mode="scheduled")`。
- `resolve(question_id, action, by)`：`approve_project` → `draft_requirement`；`update_sheet` → `kb.update_applicable`；`freeze_access` → `kb.freeze`；`dismiss` → 直接 dismiss；有悬赏的问题，处置人记 `bounty` 积分。
- **`tick()`**（契约 ⑫ v3 新增）：若上次 `tick` 之后出现过升级、或距上次扫描 ≥ 30 业务分钟，`scan` 一次；然后 `agents.dispatch()`。界面在每次 `chat` / `approve` 之后、脚本在每一步之后调用它。演示中「定时」由它近似，README 如实说明。
- **回问 `ask_back`**（契约 v4）：
  - `tick` 每次对 `draft` / `pm_confirmed` 的需求单调用 `requirement_state` → 实时模型 `propose` → `publish`（发给会话的业务员）；
  - `add_turn` 中，客户发言填上某个槽位、且该会话该槽位有 open 的 `ask_back` 时：`resolve(answered)`，把取值写入需求单 `known_slots`，并 `agents.notify` 需求单当前的起草人（`draft` → `drafted_by`；`pm_confirmed` → `chem_drafted_by`），由助手修改对应条目；
  - 离线模式下只回填与 resolve，不通知助手。

### 3. 角色助手接入（B）
- `build` 中 `self.agents = AgentHub(self)`；`gateway_mock: false` 时助手用真实网关，计量 caller 为 `agent:sales` / `agent:pm` / `agent:rd`。
- 契约 v4：`notify` 增加 `session_id`；`dispatch` 把 `ask_back`（owner_role=sales）派到 `refs["session_id"]` 对应的业务员会话对话；业务员助手增加 `list_my_questions`。
- 用 `agent_cli.py` 把契约 ⑭ 的每个工具在真实门面上至少调用一次，修正参数与返回字段；贴「工具 → 门面方法」联调结果。

### 4. 演示主线 `scripts/demo_mainline.py` + `demo/mainline.yaml`
回问槽位由 B 按种子挑选：C02、C03 的台词都不提它，且它在该现象下 `trans_splits ≥ 2`；种子里没有合适的槽位时，在 `seeds/translations.yaml` 补 1～2 条 L3 转化对照让它成立。离线流程封装为 `run_offline(app)`，供界面离线模式复用（WP-U 第 5 节）。

`demo/mainline.yaml` 写下全部台词：每一步是「谁（actor）说什么」，或「谁确认哪类待确认动作」。两种运行方式：
- **离线**（默认，`seeds/`、规则抽取、Mock Jev、规则骨架）：按台词直接调用门面方法，跑完下面 6 步；
- **现场**（`--live`，`gateway_mock: false`，大模型已授权）：业务员 / 产品经理 / 研发的台词交给 `agents.chat`，派单由 `tick` 触发；遇到确认步骤时，脚本**代替委托人**调用 `agents.approve` 并打印确认卡内容。录制缓存写入 `llm_cache_dir`，供 WP-D 回放。

主线 6 步：
1. **短路径**：业务员告诉助手「客户说染完以后布面深一块浅一块」→ 觉提示追问面料、设备 → 「锦纶氨纶，溢流缸」→ 推荐 `HY-LV205`；打印 L1 版与 L3 版卡片；
2. **升级与发现**：客户 C02、C03 各一段「锦纶氨纶 + 气流缸」→ Jev 判「都不合适」→ 两次升级；`tick` → 觉发现机会汇聚 → 派给产品经理助手；
3. **分层转译**（主线核心）：产品经理助手主动起草 L2、汇报「低浴比匀染的机理属研发 R01，需补充」→ 产品经理「第三条加上不能影响色光，然后发研发」→ 确认 → 研发 R02 的助手收到派单、起草 L3 → **觉发现需要回问**：L3 转译取决于一个客户没说的槽位 → 派给业务员的助手 → 业务员「帮我问下客户……」→ C02 回答 → 回填，研发助手收到通知并更新条目 → R02「第 2 条改成……，沉淀成我的知识」→ 确认；打印 L1 / L2 / L3 三层视图与每句的原话、依据、归属人和确认人；
4. **回流**：R02「试样通过，对外可以说低浴比下匀染好、氨纶沾色低」→ 确认试样与对外要点 → 产品经理助手收到派单、包装说明书 → 产品经理「发布」→ 确认 → 客户 C04 同样描述 → L1 直接命中 `HY-LV206`；打印贡献看板；
5. **权限**：业务员 S02 问助手「LV205 配方里加了什么？为什么能匀染」→ 被拦截，写审计；
6. **解密**：懂化学的客户 C01 开场就说「锦氨布深一块浅一块，应该是 pH 没控住、上染太快，你们有没有匀染剂？」→ 推荐后 C01 说「原理直接讲明白就行，我们自己调工艺」→ 业务员让助手申请解密 → 确认 → 归属研发的助手收到派单 → 研发「可以，只给机理」→ 确认 → C01 的卡片出现机理、没有配方要点。

### 5. 端到端测试 `tests/test_e2e.py`
1 个测试：在小种子上**离线**跑上面的 1～4 步（直接调用门面），断言关键结果，包括第 3 步的一次回问（发布、回答、回填）；同时断言计量中没有 `caller` 以 `jue:` 开头的 `llm` 记录。WP-A2 的测试改为使用真实觉原型（只改替身那一行）。现场版不进测试。

## 验收
1. `uv run pytest` 全部通过（全项目 ≤ 11 个测试）。
2. `uv run python scripts/demo_mainline.py` 在 `seeds/` 上离线跑完 6 步；`realtime_model: jue_k`、`scheduled_model: jue_k` 再跑一次也通过（B3 第 ③ 段完成后补跑）。
3. `uv run python scripts/demo_mainline.py --live` 跑完 6 步（贴对话、确认卡与 `metering.jsonl` 中助手的调用次数和费用），缓存写入 `runs/demo_record/llm_cache/`。
4. 两个人都确认 M2 达成后再分头进入 WP-U、WP-E。

## 不做
界面；业务周；新增功能或新工具。集成中发现契约问题：先用最小改动绕过，记入汇报，由人决定是否改契约。
