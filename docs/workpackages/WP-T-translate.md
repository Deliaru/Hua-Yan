# WP-T 转译引擎：L2 产品需求、L3 化学语言、反向包装

> 负责：B｜时段：2:15–3:30｜分支：`dev/b`

## 目标
实现化言的主旨——**分层转译**。三个函数：把升级会话转成 L2 产品需求语言、把产品需求转成 L3 化学语言、把研发结果反向包装成 L1 说明书。每一层只读自己能看的知识；每一句输出都标明依据的转化知识（归属人据此记分）和客户原话。

这是和「一次性翻译器」拉开差距的地方：不是一个大模型把对话直接翻成化学语言，而是**用每一层的人沉淀下来的知识，逐层转、逐句可追溯、上层知识不下泄**。

## 依赖
WP-0、WP-S。用小种子开发；需要知识库时用 `KnowledgeBase.from_seeds`（WP-A1）。A1 未合并前，先写一个最简单的替身，只实现 `list`（放在测试文件里，A1 合并后删除）。

## 必读
`CONTRACTS.md` 第 ①（1.4 转化对照）、②（2.1、2.2 的 `list`）、③（Turn、NeedState、Session）、⑦ 全节、⑩（网关）～4 节（L2、L3 各自的转述能力）。

## 允许修改的范围
`src/huayan/escalation/translate.py`、`prompts/pm_draft.md`、`prompts/rd_translate.md`、`prompts/package.md`、`scripts/translate_cli.py`、`tests/test_wp_t.py`

## 交付物与已定设计

### 1. 规则模式（`gateway is None`，零成本，必须先做）
- **候选知识**：`kb.list(actor, kinds=..., phenomenon=need.phenomenon)`，L2 用 `pm` 身份（只拿得到 case 与 L2 转化对照），L3 用 `rd` 身份。
- **匹配**：转化对照的 `scene_phrase` 与文本做子串或字符二元组匹配（阈值写死）。
- `draft_product_need`：
  1. 对会话中每一句客户发言，找命中的 L2 转化对照 → 生成一条产品需求 `ReqItem`：`text` = 「客户反映『{原话片段}』→ {chem_term}」，`quote_refs` = 该轮 id，`ku_refs` = 该转化对照；
  2. 每个已知槽位生成一条条件类条目（如「面料：锦纶氨纶」），`slot` 填上，`quote_refs` 取 `SlotFill.turn_id`；
  3. 同现象的案例作为参考，加入命中案例的 `ku_refs`；
  4. `direction` = 命中最多的 L2 译文 + 关键条件。
- `draft_chem_need`：对每条产品需求条目和槽位条件，找命中的 L3 转化对照 → 生成化学语言条目（继承上一层的 `quote_refs`，`ku_refs` 指向 L3 知识）；`hypotheses` 取同现象已发布产品机理中的关键句（引用 mechanism 知识）。
- `package_sheet`：用产品需求条目与研发的对外要点套模板，生成说明书与用法。
- 没有命中任何知识的客户原话，也要保留为一条「未转译」条目（`ku_refs` 为空），提示人工处理——**不要编造**。

### 2. 大模型模式（`gateway` 不为 None）
- 一次 `structured` 调用，caller 分别为 `agent:pm_draft`、`agent:rd_translate`、`agent:package`，tier fast，`temperature=0`。
- 提示词放 `prompts/`：给出会话轮次（带 turn id）、槽位与原话、候选知识（带 ku id 与归属人），要求每条输出至少引用一个 turn id，并列出依据的 ku id；L2 提示词写明「你是产品经理，用产品需求的语言，不要写化学机理」；L3 提示词写明「你是研发，把产品需求转成可开工的化学问题」。
- 输出校验（真实输入边界）：不在候选里的 ku id、不存在的 turn id 丢弃；一条都没有 turn id 的条目丢弃。

### 3. 命令行 `scripts/translate_cli.py`
读一段写好的对话（yaml），依次打印 L1 槽位 → L2 条目 → L3 条目，每条带原话与「依据：{归属人} 的 {ku id}」。M1 演示用。

## 验收
1. `tests/test_wp_t.py` 只有 1 个测试（规则模式、小种子）：会话「深一块浅一块 / 锦纶氨纶 / 气流缸」→
   - L2 条目引用了 `tr:1`、`tr:3`，**不含任何 L3 知识**（检查 `ku_refs` 与生成文本中不出现 L3 转化对照的译文）；
   - L3 条目引用了 `rd:R01` 与 `rd:R02` 各自的转化对照，且每条都有 `quote_refs`；
   - `package_sheet` 的输出不含 L3 转化对照的译文和任何产品的机理文字。
2. 手动：在 `seeds/` 上用 `translate_cli.py` 跑演示主线的升级对话，贴输出；授权了大模型费用的话再跑一次大模型模式，对比两种输出。

## 不做
需求单的状态流转、积分、界面（WP-A3、WP-U）；向量检索；多轮修改对话。
