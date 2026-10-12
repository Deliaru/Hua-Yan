# WP-T 转译引擎：规则骨架与转化对照匹配

> 负责：B｜时段：2:15–3:30（与 WP-L 同时开两个 Agent）｜分支：`dev/b`

## 目标
实现化言主旨「分层转译」的**确定性底座**：把升级会话转成 L2 产品需求骨架、把产品需求转成 L3 化学语言骨架、把对外要点套成 L1 说明书，以及给角色助手用的转化对照匹配。每一层只读自己能看的知识；每一句都标明依据的转化知识（归属人据此记分）和客户原话。

大模型如何参与：**通过角色助手（WP-L）**——助手先调用这里的骨架，再用工具检索、逐条修改。本包不调用大模型。规则骨架同时是离线演示、测试和失真对照（WP-E）的转译实现。

## 依赖
WP-0、WP-S、WP-A1（`kb.list`）。A1 未合并前，在测试文件里写一个只实现 `list` 的最简替身，A1 合并后删除。

## 必读
`CONTRACTS.md` 第 ①（1.4 转化对照）、②（2.1、2.2 的 `list`）、③（Turn、NeedState、Session）、⑦ 全节。

## 允许修改的范围
`src/huayan/escalation/translate.py`、`scripts/translate_cli.py`、`tests/test_wp_t.py`

## 交付物与已定设计（契约 7.1）

- **`match_translations(text, kb, actor, phenomenon)`**：在 `kb.list(actor, kinds=["translation"], phenomenon=...)` 中，`scene_phrase` 是 `text` 的子串，或字符二元组重合度 ≥ 0.5（写死），按分数降序返回。下面三个函数和助手工具都用它。
- **`draft_product_need`**（L2，用 `pm` 身份取知识，只拿得到案例与 L2 转化对照）：
  1. 对会话中每一句客户发言做 `match_translations` → 一条产品需求 `ReqItem`：`text` = 「客户反映『{原话片段}』→ {译文}」，`quote_refs` = 该轮 id，`ku_refs` = 命中的转化对照；
  2. 每个已知槽位一条条件类条目（如「面料：锦纶氨纶」），`slot` 填上，`quote_refs` 取 `SlotFill.turn_id`；
  3. 同现象的案例作为参考，加进命中条目的 `ku_refs`；
  4. `direction` = 命中最多的 L2 译文 + 关键条件。
- **`draft_chem_need`**（L3，`rd` 身份）：对每条产品需求条目和槽位条件做 `match_translations` → 化学语言条目（继承上一层的 `quote_refs`，`ku_refs` 指向 L3 知识）；`hypotheses` 取同现象已发布产品机理中的关键句（引用 mechanism 知识）。
- **`package_sheet(req)`**：只用 `req.product_lang` 与 `req.public_points` 套模板，生成说明书与用法。
- 没有命中任何知识的客户原话保留为一条「未转译」条目（`ku_refs` 为空），提示人工处理——**不编造**。

### 命令行 `scripts/translate_cli.py`
读一段写好的对话（yaml），依次打印 L1 槽位 → L2 条目 → L3 条目，每条带原话与「依据：{归属人} 的 {ku id}」。M1 演示用。

## 验收
1. `tests/test_wp_t.py` 只有 1 个测试（小种子）：会话「深一块浅一块 / 锦纶氨纶 / 气流缸」→
   - L2 条目引用了 `tr:1`、`tr:3`，**不含任何 L3 知识**（检查 `ku_refs` 与文本中不出现 L3 转化对照的译文）；
   - L3 条目引用了 `rd:R01` 与 `rd:R02` 各自的转化对照，且每条都有 `quote_refs`；
   - `package_sheet` 的输出不含 L3 转化对照的译文和任何产品的机理文字。
2. 手动：在 `seeds/` 上用 `translate_cli.py` 跑演示主线的升级对话，贴输出。

## 不做
大模型调用（由 WP-L 的助手负责）；需求单的状态流转、积分、界面（WP-A3、WP-U）；向量检索；多轮修改。
