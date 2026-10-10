# WP-A2 L1 链路：抽取、Jev、应用门面

> 负责：A｜时段：2:00–3:30｜分支：`dev/a`

## 目标
一段客户与业务员的对话，逐句进入系统：抽取需求槽位（绑定原话）→ 觉给出追问提示 → 信息够了由 Jev 匹配产品并选择披露版本 → 渲染推荐卡片；匹配不上则升级。问答类意图（问产品、套机理）走检索回答，越权内容被拦截。

## 依赖
WP-A1。觉的实时部分在 WP-I 才接入，本包用一个**替身**：对每个 `required` 且未填的槽位给 `p_need=0.8` 的 `AskHint`（放在 `l1/` 内部，WP-I 删除）。

## 必读
`CONTRACTS.md` 第 ③、④、⑩、⑪、⑫ 节；`ARCHITECTURE.md` 第 5、7.1、7.4 节。

## 允许修改的范围
`src/huayan/l1/`（`extract.py`、`answer.py`、`session.py`）、`src/huayan/jev/`（不含 `system1/`）、`src/huayan/app.py`、`prompts/extract.md`、`prompts/l1_answer.md`、`scripts/chat_cli.py`、`tests/test_wp_a2.py`

## 交付物与已定设计

### 1. 抽取 `l1/extract.py`
- `RuleExtractor`（`name="rule"`）：只用 `huayan.domain` 的三个匹配函数；客户说「不清楚 / 不知道 / 不确定」且上一句业务员问了某槽位 → 该槽位 `unknown`；含「原理」「为什么」「配方」「成分」→ `mechanism_request`；出现「是什么产品」「怎么用」→ `product_question`；客户点名要某一类助剂（文本含种子产品的 `category`，如「匀染剂」「pH 缓冲剂」）→ `chem_savvy=True`（懂化学的客户说得出成因、直接要某类助剂；不懂化学的只说现象）。
- `LLMExtractor`（`name="llm"`）：一次 `gateway.structured(..., ExtractionResult)`，caller `agent:extract`，tier fast，`temperature=0`。提示词放 `prompts/extract.md`：给出全部槽位与取值枚举、现象列表、已有 NeedState，要求每个槽位附原话片段、取值必须来自枚举。
- `apply_extraction` 按契约实现；只覆盖新抽到的槽位，不删除已有槽位；`asked` 按 `asked_slots` 累加。

### 2. Jev `jev/__init__.py`：`Jev`
按契约 4.2。三个问题的题面写成中文业务问题（如「客户的问题是……已知……以下哪个产品最可能解决？都不合适请选 none」）。`state` 按契约 4.2 的格式组装，只放 L1 内容。`grounding` 实现但默认不调用（`answer.py` 中开关，砍掉时不影响主线）。

### 3. 会话流程 `l1/session.py`
`handle_turn(session, speaker, text, deps) -> Session`，deps 包含抽取器、觉的追问函数（本包为替身）、Jev、知识库、事件日志、审计、积分、总线。每轮：
1. 记 `turn` 事件 → 抽取 → 记 `extraction` 事件；
2. 意图为 `product_question` / `mechanism_request`：`l1/answer.py` 用 L1 检索结果回答（离线模式直接拼接命中的 sheet/usage；大模型模式 caller `agent:l1_answer`，只给它可读的命中）；有越权命中时回复「这部分属于研发保密内容，可以为客户申请解密」，`blocked=True`，写审计 `deny`；
3. 意图为 `need`：算追问提示（记 `ask_hint` 事件）→ 按契约 4.3 的规则匹配、推荐或升级。升级时发布 `escalate_need` 问题（`discoverer="jev"`，`refs` 含 `session_id`、`customer_id`，证据为槽位原话），记 `escalate` 事件；
4. 推荐时：`cap`（查看者按该会话业务员）→ `disclose` → 记 `recommend` 事件、审计 `disclose`、卡片中每条知识给归属人记 `cited`。

### 4. 应用门面 `app.py`：`HuayanApp`
- `build`：读 `config/app.yaml`；建 run 目录、计量、网关（`gateway_mock` / `llm_cache_dir`）、System 1、Jev、知识库、事件、总线、审计、积分；`actors` 来自种子。
- 实现契约 ⑫ 中 L1 部分与 `status()`、`jue_trace()`（本包返回空列表）。
- `view_session`：按查看者层级裁剪——L1 只看本会话的轮次、槽位原话、提示、L1 回复、L1 版卡片；L2 增加需求单；L3 卡片渲染 `internal`。**界面不做任何权限判断，全部在这里。**
- 每轮结束覆盖写 `runs/<run>/sessions/<id>.json`。

### 5. 命令行 `scripts/chat_cli.py`
交互输入「客：…」「业：…」，打印提示、槽位原话、卡片（L1 版与 L3 版对比）。M1 演示用。

## 验收
1. `tests/test_wp_a2.py` 只有 1 个端到端测试：小种子 + `RuleExtractor` + `MockSystem1Client`，客户说「染完布面深一块浅一块」→ 出现面料、设备追问提示 → 客户答「锦纶氨纶的，溢流缸」→ 推荐 `T-205`，L1 视图版本为 `product_usage`，L3 视图包含 formula；另一会话答「气流缸」→ 升级，总线中有 `escalate_need` 问题。
2. 手动：`gateway_mock: false`、`extractor: llm` 下用 `chat_cli.py` 跑一次演示主线（需要大模型费用授权；未授权则跳过并在汇报中说明）。

## 不做
升级之后的流程（WP-A3）、觉的真实实现（WP-B1）、界面、语音、多会话并发。
