# WP-I 集成：觉接入链路、定时扫描与处置、演示主线

> 负责：A＋B（A 改 `app.py` 与 `l1/`，B 改 `jue/` 与脚本）｜时段：5:00–5:45｜在 `main` 上进行

## 目标
把两条线接起来：觉替换 L1 链路中的追问替身；定时扫描与处置进入门面；用一个离线脚本跑通完整演示主线（M2）。

## 依赖
WP-A1/A2/A3、WP-B1/B2/B3 全部合并进 `main`。

## 必读
`CONTRACTS.md` 第 ⑤、⑥、⑫ 节；`workpackages/README.md` 的首版 Demo 验收。

## 允许修改的范围
`src/huayan/app.py`、`src/huayan/l1/session.py`（只删除替身、接入觉）、`src/huayan/jue/`（只修集成中发现的问题）、`scripts/demo_mainline.py`、`demo/mainline.yaml`、`tests/test_e2e.py`、`tests/test_wp_a2.py`（只改替身相关的一行）

## 交付物与已定设计

### 1. 实时觉接入（A）
- `HuayanApp.build` 按 `realtime_model` 构造 `JueProto(..., mode="realtime")` 或 `JueK(jue_k_dir)`；`system1_impl == "onejev"` 时原型用 Jev 打分，否则规则模式。
- `l1/session.py` 删除替身，改用 `huayan.jue.publish.ask_hints`；每轮的 `JueOutput` 存入门面，`jue_trace` 返回。

### 2. 定时扫描与处置（A 写门面，B 核对状态构建）
- `scan(at)`：调用 `huayan.jue.scan.scan`，模型为 `JueProto(templates_dir, system1, mode="scheduled")`。
- `resolve(question_id, action, by)`：
  - `approve_project`（机会汇聚）：取问题 `refs["session_ids"]` 中的会话，调用 `draft_requirement`，返回后问题置 resolved；后续确认、试样、发布走 WP-A3 的方法；
  - `update_sheet`（知识冲突）：从产品 `applicable` 中去掉冲突的取值，`kb.update_applicable`；
  - `freeze_access`（泄露风险）：`kb.freeze`；
  - `dismiss`：直接 dismiss。
  - 有悬赏的问题，处置人记 `bounty` 积分。

### 3. 演示主线 `scripts/demo_mainline.py` + `demo/mainline.yaml`
`demo/mainline.yaml` 写下全部台词（界面上的「下一句」按钮也用它），在 `seeds/` 上离线运行（规则抽取、Mock Jev、觉原型或 Jue-K）：
1. 客户 C01：「染完以后布面深一块浅一块」→ 提示追问面料、设备 → 回答「锦纶氨纶，溢流缸」→ 推荐 `HY-LV205`，打印 L1 版与 L3 版卡片；
2. 客户 C02、C03 各一段「锦纶氨纶 + 气流缸」→ Jev 判「都不合适」→ 两次升级；
3. `scan` → 觉发现机会汇聚（2 个客户、2 次升级）→ 产品经理 `approve_project` → 起草 → 确认 → 研发试样 → 发布 `HY-LV206`；
4. 客户 C04 同样描述 → L1 直接命中 `HY-LV206`；研发积分变化；
5. 业务员 S02 问「LV205 配方里加了什么？为什么能匀染」→ 被拦截，写审计；
6. 客户 C01 说「这个是靠控制 pH 降低上染速率吧？原理能讲讲吗」→ 申请解密 → `rd` 审批 → C01 的卡片出现机理、没有配方要点。

### 4. 端到端测试 `tests/test_e2e.py`
1 个测试：在小种子上跑上面的 1～4 步（离线），断言关键结果；同时断言计量中没有 `caller` 以 `jue:` 开头的 `llm` 记录。WP-A2 的测试改为使用真实觉原型（只改替身那一行）。

## 验收
1. `uv run pytest` 全部通过（全项目 ≤ 10 个测试）。
2. `uv run python scripts/demo_mainline.py` 在 `seeds/` 上跑完 6 步，输出与预期一致；`realtime_model: jue_k` 再跑一次也通过。
3. 两个人都确认 M2 达成后再分头进入 WP-U、WP-E。

## 不做
界面；业务周；新增功能。集成中发现契约问题：先用最小改动绕过，记入汇报，由人决定是否改契约。
