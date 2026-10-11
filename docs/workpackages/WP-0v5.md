# WP-0v5：契约 v5 差异（草案，待人签字）

> 状态：**已应用到契约 v5**（四处取舍按建议采纳）｜2026-10-11｜依据 `REPLAN-v5.md`（D1～D16，第 4、5 节）
> 契约只能由人修改（铁律 1）。本文由 A 起草，逐条列出 `docs/CONTRACTS.md` 与 `src/huayan/contracts/` 要改什么；人确认后按本文修改，CONTRACTS 版本号升为 v5，然后打 `v4-final` 标签之后的第一个契约提交。
> 原则：只改模块之间传递的东西；能由模板、提示词、门面内部解决的不进契约。

## 0. 总览

| # | 章节 / 文件 | 改动一句话 |
|---|---|---|
| C1 | ⑤ `jue.py` | 对象类型加 `session`、`requirement`；`Family` 改为模板目录校验的字符串；模板加 `kind`、`signer_role`；5.2 补两类对象的属性 |
| C2 | ⑥ `bus.py` | 问题加签字人、准备完成时间、模板 id；处置动作改为 accept / return / sign …；总线加 `set_prepared` |
| C3 | ⑦ `escalation.py` | 需求单可以是空单；状态 `pm_confirmed` → `rd_accepted`；加指定研发、封存项、草稿字段、退回理由；`ReqItem.edited_by`；试样加客户评价；新增 `LeakHit` 与泄密匹配函数 |
| C4 | ③ `session.py` | 会话加回复草稿、升级说明草稿 |
| C5 | ⑧ `events.py` | 加 `match`、`question_prepared`、`requirement_created / accepted / returned / edited`、`market_eval`、`points_set`、`human_decision`；`requirement_confirmed` 删除；`escalate` 只在业务员签字后写 |
| C6 | ④ 4.3 | Jev 只写 `match` 事件，不再升级 |
| C7 | ① / 0 | 新增身份 `pm:agent`；积分只给人 |
| C8 | ② `knowledge.py` | `DecryptGrant.text`（第二档，D14） |
| C9 | ⑪ `config/app.yaml` | 删除 `routing`，主人与签字人随模板 |
| C10 | ⑫ `app.py` | 门面方法增删改；`jue_timeline` 视图模型 |
| C11 | ⑭ `agent.py` | `AgentMessage.target`；`pm:agent` 无生效工具；派单只派总线问题；删「确认后派单」；工具清单 |
| C12 | ⑨ 模拟 | 模拟业务周中「模拟人」对推进类决策的签字规则 |

## C1　⑤ 觉（`contracts/jue.py`，CONTRACTS 5.1～5.4）

```python
ObjectType = Literal["slot", "theme", "knowledge", "actor", "session", "requirement"]
Family = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]
# 决策 id。合法取值 = 已加载模板目录中的 family 集合：huayan.jue 加载模板时校验 family 唯一（每个 family 一个模板）、
# 校验 object_type 合法；ScoredDecision / Question 的 family 必须在目录中。新增决策点 = 人批准后新增模板文件，不改契约。

class JueTemplate(BaseModel):
    id: str
    family: Family
    kind: Literal["advance", "anomaly"]       # 新：推进类 / 异常类
    object_type: ObjectType
    decision_label: str                       # 「是否转产品经理 Agent」「研发是否接单」…
    precondition: str | None = None
    rule_score: str | None = None
    worth_prompt: str
    title: str
    owner_role: Role                          # 改义：主人（谁准备）。没有准备环节的（拼凑）与签字人相同
    signer_role: Role | None = None           # 新：签字人角色；None = 提示类（ask_slot、ask_back），不进待签
    bounty_points: int = 0
    urgency: str | None = None
```

`ScoredDecision.family`、`JueOutput`、`JueRecord`、`QuestionModel`、`Discoverer` 不变（`family` 类型随 `Family` 变）。

**5.1 对象表新增两行**

| 对象类型 | object_id | 模式 | 由谁构建 |
|---|---|---|---|
| `session` | `session:<session_id>` | 实时（写后） | `session_state(sess, events, at)` |
| `requirement` | `requirement:<req_id>` | 实时（写后）＋定时（停滞，第二档） | `requirement_state(req, need, seeds, kb, at, events)`：在原有 slot 对象之外，再产出一个 requirement 对象 |

```python
def session_state(sess: Session, events: EventLog, at: datetime) -> JueState: ...
    # 只读会话与该会话的事件；mode="realtime"
def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime,
                      events: EventLog) -> JueState: ...
    # 改：增加 events 参数；status 为 released / rejected 之外的需求单都构建；
    # slot 对象只在 status 为 draft（layer=2）或 rd_accepted（layer=3）时产出；requirement 对象总是产出
```

**5.2 属性命名表新增**

**session**

| 属性 | 类型 | 含义 |
|---|---|---|
| `phenomenon` | str | 现象 id；未识别为 `"unknown"` |
| `phenomenon_known` | bool | 现象已识别 |
| `turn` | int | 对话轮次 |
| `n_filled` | int | 已填槽位数 |
| `n_open_asks` | int | 最近一次追问提示中仍在阈值以上的槽位数 |
| `matched` | bool | 本会话有过 `match` 事件 |
| `p_none` | float | 最近一次 `match` 的「都不合适」概率；未匹配为 0 |
| `p_top` | float | 最近一次 `match` 中候选产品的最高概率；未匹配为 0 |
| `n_candidates` | int | 最近一次 `match` 的候选数 |
| `top_is_none` | bool | `matched` 且 `p_none ≥ p_top` |
| `recommended` | bool | 已推荐 |
| `escalated` | bool | 业务员已签字升级 |
| `chem_savvy` | bool | 客户画像 |
| `asked_mechanism` | bool | 客户明确要求了解原理 |
| `decrypt_requested` | bool | 已申请解密 |

**requirement**

| 属性 | 类型 | 含义 |
|---|---|---|
| `status` | str | 需求单状态 |
| `layer` | int | draft = 2，rd_accepted = 3，其余 0 |
| `n_product_items` | int | L2 条目数 |
| `n_chem_items` | int | L3 条目数 |
| `n_returns` | int | 被研发退回次数 |
| `n_open_ask_back` | int | 本单未答复的回问数（由 `question_published / resolved` 事件算） |
| `n_unmapped_constraints` | int | 上一层已有、本层条目未承接的已知槽位数（layer 2 对 L1 槽位，layer 3 对 L2 条目所含槽位；按 `ReqItem.slot` 计） |
| `n_unquoted_items` | int | 本层没有 `quote_refs` 的条目数 |
| `n_edited_uncovered` | int | L3 条目中 `edited_by` 为研发、且其文本未被已有 L3 转化对照的 `chem_term` 覆盖的条数 |
| `n_contributed` | int | 本单已沉淀的转化知识数 |
| `n_trials` | int | 试样次数 |
| `trial_passed` | bool | 最近一次试样通过 |
| `market_eval` | str | `"none"` / `"pass"` / `"fail"`（最近一次通过的试样上的客户评价） |
| `points_set` | bool | 研发已签字「封存 / 放出」 |
| `n_sealed` | int | 封存项数 |
| `sheet_ready` | bool | 已有说明书草稿 |
| `n_leak_hits` | int | 说明书与用法上的 `leak_hits` 命中句数（C3） |
| `released` | bool | 已发布 |
| `hours_in_status` | float | 停留在当前状态的业务小时（第二档：停滞） |

对象属性只放计数与状态，不放文本（文本类信号在构建时用规则匹配算成计数，铁律 3）。

**5.3** 模板清单改为「见 `config/templates/`，每个 family 一个文件」，删除「模板共 5 个」一句；本次新增 `escalate_need`、`accept_requirement`、`distortion`、`confirm_translation`、`contribution`、`market_eval`、`seal_points`、`seal_leak`、`release`（前置条件与打分见 REPLAN 4.3，均为规则打分）。

**5.4** `JueK` 的「一个模型覆盖全部五类」改为「覆盖有训练样本的决策（`ask_slot`、`ask_back`、`opportunity`、`knowledge_conflict`、`leak_risk`）；没有训练样本的决策由原型规则打分，同一次 `propose` 的输出中逐条标 `scored_by`」。为此：

```python
class ScoredDecision(BaseModel):
    family: Family
    object_id: str
    p_need: float | None = Field(default=None, ge=0, le=1)
    urgency: float | None = None
    precondition_passed: bool = True
    template_id: str | None = None
    scored_by: Literal["onejev", "rule", "jue_k"] | None = None   # 新：逐条打分来源；None 时取 JueOutput.scored_by
```

**publish** 改为：所有 `p_need ≥ threshold` 的非提示类组合生成问题（不再区分实时 / 定时），`ask_slot` 仍只走 `select_asks`。问题的 `owner_id` / `signer_id` 按下表解析（写在 `huayan.jue.publish`，不进模板）：

| 角色 | 对象 | 解析为 |
|---|---|---|
| sales | session / requirement / slot | 会话的业务员（需求单取首个会话） |
| pm | 任意 | `pm:agent` |
| rd | requirement / slot（layer 2/3） | `req.assigned_rd` |
| rd | knowledge | 产品归属研发 |
| supervisor | 任意 | id 最小的主管 |

## C2　⑥ 问题总线（`contracts/bus.py`）

```python
QFamily = Family                              # 同 C1

class Resolution(BaseModel):
    action: Literal["sign", "accept", "return", "answered", "update_sheet", "freeze_access",
                    "approve_decrypt", "reject_decrypt", "dismiss"]
    # sign：签字人在工作面签字（升级、确认转译、沉淀、客户评价、封存 / 放出、发布）
    # accept / return：研发接单 / 退回（accept 同时关闭关联的 opportunity）
    # answered：回问已由客户回答；异常类问题前置条件不再成立时自动关闭
    # 删除：draft_requirement、approve_project（立项 ≡ 接单）
    by: str
    note: str = ""

class Question(BaseModel):
    # …原有字段不变，以下为改动…
    family: QFamily
    owner_role: Role                          # 主人（谁准备）
    owner_id: str | None = None
    signer_role: Role | None = None           # 新：None = 提示类
    signer_id: str | None = None              # 新
    prepared_at: datetime | None = None       # 新：None = 准备中；有值 = 待签
    template_id: str | None = None            # 新：被忽略率按模板统计
    discoverer: Literal["jue_proto", "jue_k", "rule_alert", "llm_poll", "human"]   # 删除 jev

class QuestionBus:
    # 新增
    def set_prepared(self, qid: str, at: datetime | None) -> Question: ...
        # at 有值：进入待签，写 question_prepared 事件；None：退回准备中（需求单已知条件变化时由门面调用）
```

路由一节删除，改为「发布方按模板的 `owner_role` / `signer_role` 与 C1 的解析表填写」。

## C3　⑦ 升级、分层转译与回流（`contracts/escalation.py`）

```python
class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []
    ku_refs: list[str] = []
    edited_by: str | None = None              # 新：最后一次由人修改的 actor id；None = 骨架或 Agent 起草（界面标「Agent 起草」）

class LeakHit(BaseModel):                     # 新：泄密匹配结果，只给句序号与类别，不含命中内容
    index: int                                # 按「。；！？\n」切句后的序号，从 0 开始
    source: Literal["sealed", "l3_term", "hypothesis"]

class PointsDraft(BaseModel):                 # 新：封存 / 放出两栏草稿（只对 L3 可见）
    public: str                               # 拟放出的对外要点
    sealed: list[str]                         # 拟封存的窗户纸
    self_check: list[LeakHit] = []            # 对 public 的泄露自查结果

class ContributionDraft(BaseModel):           # 新：Agent 提炼的可沉淀转化知识（只对 L3 可见）
    item_index: int
    scene_phrase: str
    chem_term: str
    note: str = ""                            # 泛化说明、与已有知识相近或冲突之处

class Requirement(BaseModel):
    id: str
    question_id: str                          # 产生它的 escalate_need 或 opportunity 问题
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    assigned_rd: str                          # 新：接单与签字的研发；建单时取该现象 L3 转化对照条数最多的研发（并列取 id 最小）
    escalate_note: str = ""                   # 新：业务员签字时的升级说明（L2/L3 可见）
    direction: str = ""                       # 改：可为空（空单）
    product_lang: list[ReqItem] = []          # 改：可为空（空单）
    chem_lang: list[ReqItem] = []
    hypotheses: list[str] = []                # 研发方向假设（L3 可见）；也是泄密匹配的来源之一
    status: Literal["draft", "rd_accepted", "rd_confirmed", "released", "rejected"]   # 改：pm_confirmed → rd_accepted
    drafted_by: str = "pm:agent"              # 改义：L2 草稿起草者
    chem_drafted_by: str | None = None
    rd_accepted_by: str | None = None         # 改名：原 pm_confirmed_by
    rd_confirmed_by: str | None = None
    return_notes: list[str] = []              # 新：研发退回理由（提交前经 L3 术语自查，L2 可见）
    contribution_drafts: list[ContributionDraft] = []   # 新：只对 L3 可见
    points_draft: PointsDraft | None = None   # 新：只对 L3 可见
    public_points: str = ""                   # 研发签字放出的对外要点：L3 内容流向下层的唯一出口
    sealed: list[str] = []                    # 新：研发签字封存的窗户纸，只对 L3 可见
    sheet: SheetDraft | None = None
    product_id: str | None = None
    created_at: datetime

class Trial(BaseModel):
    # …原有字段不变…
    market_eval: Literal["pass", "fail"] | None = None   # 新：客户评价，业务员录入
    market_eval_by: str | None = None
    market_eval_note: str = ""
```

**可见性**（写进 `requirement_view` 的说明）：对 L2 查看者，`sealed`、`points_draft`、`contribution_drafts`、`hypotheses` 置空，所引 L3 知识照旧只给归属；L1 抛 `PermissionDenied`。

**7.1 转译引擎**

```python
def draft_product_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, pm: Actor, at: datetime) -> PMDraft: ...
    # 改：输入从问题改为（空）需求单
def package_sheet(req: Requirement) -> SheetDraft: ...
    # 输入只有 req.product_lang 与 req.public_points；不得读 sealed、points_draft、chem_lang、hypotheses、机理、配方
def leak_hits(text: str, sealed: list[str], hypotheses: list[str], kb: KnowledgeBase) -> list[LeakHit]: ...
    # 新：规则匹配。逐句检查：sealed 各项、kb 中 level=3 转化对照的 chem_term、hypotheses 中的关键词（字符二元组重合 ≥ 阈值或子串）；
    # 不查 L2 内容（说明书本来就由产品需求包装而来）。觉的状态构建、门面的发送拦截与发布可签条件共用这一个函数
```

不变量（测试不增加，改在 `test_wp_t`）：`package_sheet` 的输出不含 L3 内容；L2 视图里没有 `sealed`。

**7.2 流程**正文改为：升级（业务员签字，建空单）→ 产品经理 Agent 起草 L2 → 研发接单 / 退回 → 研发 Agent 起草 L3、研发确认 → 沉淀（Agent 提炼、研发签字）→ 试样（模拟 ELN）→ 客户评价（业务员签字）→ 封存 / 放出（Agent 两栏、研发签字）→ 产品经理 Agent 包装说明书 → 研发审定发布。`release_product` 的 `by` 必须是 `assigned_rd`。

## C4　③ 会话（`contracts/session.py`）

```python
class Session(BaseModel):
    # …原有字段不变…
    reply_draft: str = ""                     # 新：Agent 起草的回复，界面预填进「发给客户」输入框；发出后清空
    escalate_note: str = ""                   # 新：Agent 起草的升级说明；签字时写入需求单
```

`Recommendation.escalated_question_id` 改义为「业务员签字升级时关闭的 escalate_need 问题」。

## C5　⑧ 事件（`contracts/events.py`）

```python
EventKind = Literal["turn", "extraction", "ask_hint", "match", "recommend", "escalate", "retrieve", "access_denied",
                    "decrypt_request", "decrypt_approve", "question_published", "question_prepared",
                    "question_resolved", "requirement_created", "requirement_accepted", "requirement_returned",
                    "requirement_edited", "requirement_translated", "knowledge_contributed", "trial", "market_eval",
                    "points_set", "product_released", "sheet_updated", "access_frozen", "human_decision",
                    "agent_action_proposed", "agent_action_decided"]
# 删除 requirement_confirmed
```

| kind | payload |
|---|---|
| `match`（新） | `phenomenon, known, customer_id, candidate_ids, p_choice: {product_id: p}, p_none, scored_by` |
| `escalate`（改：只在业务员签字后写） | `question_id, requirement_id, phenomenon, known, customer_id, p_none` |
| `question_prepared`（新） | `question_id, family, by` |
| `question_published` / `question_resolved` | 增加 `template_id`；resolved 时 `action, by` |
| `requirement_created`（新） | `requirement_id, question_id, phenomenon, session_ids, assigned_rd` |
| `requirement_accepted`（新，取代 requirement_confirmed） | `requirement_id, phenomenon, known, ku_refs`（L2 所引） |
| `requirement_returned`（新） | `requirement_id, reason` |
| `requirement_edited`（新） | `requirement_id, layer, index, before, after`（index = -1 追加；after 为空 = 删除） |
| `market_eval`（新） | `requirement_id, trial_id, result` |
| `points_set`（新） | `requirement_id, n_sealed`（不含内容） |
| `human_decision`（新） | `action, object_id, object_type, attrs`（人执行生效动作时，同一对象上没有对应的 open 问题；attrs 为当时该对象的属性快照） |

所有事件的 `actor` 字段即操作人；签字类事件的 `actor` 就是签字人。

## C6　④ 4.3 推荐与升级规则（重写）

每轮发言后：抽取 → 觉追问 → 若现象已知且没有追问提示，或业务员点了「直接推荐」，则匹配并**写 `match` 事件**：
- 有把握且 `choice != "none"` → 推荐、披露、记账（不变）；
- 否则不推荐、不升级。是否转产品经理 Agent 由觉的 `escalate_need`（session 对象，信号来自 `match`）在写后评估中提出，业务员签字后门面 `escalate()` 建单。

## C7　0 / ① 身份

- ID 表增加 `pm:agent`（产品经理 Agent，role = pm，L2）。`seeds/actors.yaml` 增加一行 `{id: "pm:agent", role: pm, name: 产品经理 Agent}`；`pm:P01` 保留，为 L2 历史知识（案例、L2 转化对照）的归属人，不再有工作台。
- 2.5 积分规则补：**积分只给人**，`pm:agent` 不进账本；`cited` 的记分时点改为「研发接单时记所引 L2 知识、确认转译时记所引 L3 知识」；`bounty` 记给签字人。

## C8　② 解密（第二档，D14）

```python
class DecryptGrant(BaseModel):
    # …原有字段不变…
    text: str = ""                            # 新：研发审定的、给这一位客户的结论层面说明；不含转化对照（转译过程）与配方
```

说明：解密说明经业务员转交，业务员可见；研发的转译过程（场景语言如何对应到化学语言）始终只在 L3。`decide_decrypt(question_id, by, approve, text="")`。

## C9　⑪ 配置

删除 `routing`；主人与签字人由模板决定（C1）。`thresholds.publish` 不变；规则打分的决策前置条件通过即 1.0。

## C10　⑫ 门面（`huayan.app.HuayanApp`）

**删除**：`confirm_requirement`；`add_turn` 内的自动升级；`tick` 中写死的回问发布逻辑并入统一的写后评估；`resolve` 的 `approve_project` 分支。

**改**

| 方法 | 改动 |
|---|---|
| `add_turn(session_id, speaker, text)` | 业务员发言先过发送拦截：`leak_hits(text, 全部需求单的 sealed, [], kb)` 有命中则抛 `ValueError`（消息只含命中句序号与类别），不写入；客户发言答复了 open 回问时，回填 `known_slots`、resolve(answered)，并把该需求单上已待签的问题 `set_prepared(None)` 退回准备中 |
| `draft_requirement(req_id, by)` | 改签名：对空单写入 L2 骨架；`by` 必须是 `pm:agent` |
| `confirm_translation(req_id, by)` | `by` 必须是 `assigned_rd`；只给所引 L3 知识记 cited |
| `set_public_points(req_id, text, sealed, by)` | 加 `sealed`；需客户评价通过；写 `points_set` |
| `package_sheet(req_id, by)` | `by` 为 `pm:agent`（草稿，不是生效动作） |
| `save_sheet(req_id, sheet, by)` | `by` 为 `pm:agent` 或 `assigned_rd`（研发 Agent 改写泄密句） |
| `release_product(req_id, by)` | `by` 必须是 `assigned_rd`；可签条件：说明书与用法 `leak_hits` 为空 |
| `record_trial(trial)` | 来自模拟 ELN，不写 `human_decision` |
| `decide_decrypt(question_id, by, approve, text="")` | 加 `text`（第二档） |
| `requirement_view(req_id, viewer_id)` | 按 C3 的可见性裁剪 |

**新增**（每个一个动作；生效类在签字人与可签条件不满足时抛 `PermissionDenied` / `ValueError`）

```python
def escalate(self, session_id: str, by: str) -> Requirement: ...
    # 业务员签字：建空单（assigned_rd、escalate_note ← session.escalate_note）、resolve escalate_need(sign)、
    # session.status="escalated"、写 escalate 与 requirement_created
def accept_requirement(self, req_id: str, by: str) -> Requirement: ...
    # assigned_rd；可签条件：无 open 回问、无 open 失真；→ rd_accepted；给所引 L2 知识记 cited；
    # resolve accept_requirement(accept)，并关闭 refs 指向本单的 opportunity(accept)
def return_requirement(self, req_id: str, reason: str, by: str) -> Requirement: ...
    # assigned_rd；reason 过 leak_hits（只查 l3_term），命中抛 ValueError；追加 return_notes；resolve(return)；状态仍为 draft
def record_market_eval(self, req_id: str, result: Literal["pass", "fail"], note: str, by: str) -> Trial: ...
    # 需求单首个会话的业务员；写到最近一次通过的试样上
def save_reply_draft(self, session_id: str, text: str, by: str) -> Session: ...          # 业务员（Agent）
def save_escalate_note(self, session_id: str, text: str, by: str) -> Session: ...        # 业务员（Agent）
def save_points_draft(self, req_id: str, public: str, sealed: list[str], by: str) -> Requirement: ...
    # assigned_rd（Agent）；自动填 self_check = leak_hits(public, sealed, hypotheses, kb)
def save_contribution_draft(self, req_id: str, draft: ContributionDraft, by: str) -> Requirement: ...   # assigned_rd（Agent）
def leak_check(self, req_id: str, viewer_id: str) -> list[LeakHit]: ...
    # 说明书与用法的命中；L2 查看者也可调用（只得到序号与类别）
def mark_prepared(self, question_id: str, by: str) -> Question: ...
    # 只由 AgentHub 在主人的 Loop 结束后调用（离线时在规则骨架起草后调用）；不注册为工具
def questions(self, viewer_id: str) -> list[Question]: ...
    # 查看者作为主人或签字人的 open 问题；界面据 prepared_at 分「准备中 / 待签」
def jue_timeline(self, target_id: str, viewer_id: str) -> JueTimeline: ...
```

**写后评估**：每个改状态的方法结束时，门面对受影响的 session / requirement（及其 slot）构建状态 → 实时模型 `propose` → `publish`，写 `JueRecord`；前置条件不再成立的异常类 open 问题 resolve(answered)；执行生效动作时若同一对象上没有对应的 open 问题，写 `human_decision`。`tick` 只负责定时部分与 `agents.dispatch()`。

**觉视图模型**（`contracts/app.py`）

```python
class TimelinePoint(BaseModel):               # 觉的一次判断中的一个组合
    at: datetime
    family: Family
    object_id: str
    p_need: float | None
    threshold: float
    scored_by: str
    raised: bool                              # 这一次是否提出了问题

class TimelineNode(BaseModel):                # 一个被提出的问题的全过程
    question_id: str
    family: Family
    owner_id: str | None
    signer_id: str | None
    created_at: datetime
    prepared_at: datetime | None
    resolved_at: datetime | None
    action: str | None
    by: str | None

class JueTimeline(BaseModel):
    target_id: str                            # sess:<n> 或 req:<n>；需求单线程含其全部会话
    viewer: str
    points: list[TimelinePoint]               # 按查看者裁剪：业务员只含 escalate_need、market_eval、ask_back 与本会话的 ask_slot
    nodes: list[TimelineNode]
    n_judgments: int                          # 觉的判断次数（JueRecord 条数）
    n_llm_calls: int                          # 计量中 caller 以 "jue" 开头的大模型调用数（应为 0，不写死）
    n_questions: int
    n_signatures: int
```

`SessionView` 增加 `reply_draft: str = ""`、`escalate_note: str = ""`；`RunStatus` 不变。

## C11　⑭ 角色 Agent 与产品经理 Agent（`contracts/agent.py`）

```python
class AgentMessage(BaseModel):
    role: Literal["principal", "assistant", "system"]
    text: str
    at: datetime
    pending_action_ids: list[str] = []
    target: str | None = None                 # 新：批注挂的位置，如 "req:3/chem/2"、"sess:5/reply"；None = 普通消息
```

`Conversation.principal` 可为 `pm:agent`（role = pm）。`PendingAction` 只用于对话里 Agent 的提议；工作面上的签字按钮直接调门面，不经过 `PendingAction`。

**AgentHub 改动**
- `dispatch()`：只把总线上 open、`prepared_at` 为空、尚未派过的问题 notify 给主人（`owner_id`）；主人是 `pm:agent` 时跑产品经理 Agent 的 Loop，是业务员 / 研发时跑其 Agent 的 Loop；Loop 结束后调用 `app.mark_prepared`。提示类（`signer_role` 为空）问题照旧派送（回问派到会话对话）。
- 删除 `approve` 中的「确认后派单」与整张派单表：下一步由觉的写后评估提出。
- `gateway_mock` 为 true（离线）时，hub 对主人调用对应的规则骨架（`draft_requirement` / `translate_requirement` / `package_sheet`），再 `mark_prepared`；没有骨架的（升级说明、封存两栏、提炼）用录制缓存或标注「离线，无草稿」。

**工具清单改动**（原则不变：一个工具 = 一个门面方法）

| 工具 | 类别 | 角色 | 变化 |
|---|---|---|---|
| `record_customer_turn` / `record_sales_turn` / `recommend_now` | — | — | **删除**：客户原话不经过 Agent，发言与推荐在工作面上 |
| `save_reply_draft(text)` | draft | sales | 新 |
| `save_escalate_note(text)` | draft | sales | 新 |
| `draft_product_need(req_id)` | draft | pm | 改参数 |
| `confirm_requirement` / `dismiss_question` / `release_product` | — | pm | **删除**：`pm:agent` 没有生效工具 |
| `leak_check(req_id)` | read | pm rd | 新 |
| `edit_sheet(req_id, sheet, usage)` | draft | pm rd | 研发也可用（改写泄密句） |
| `save_points_draft(req_id, public, sealed)` | draft | rd | 新 |
| `save_contribution_draft(req_id, index, scene_phrase, chem_term, note)` | draft | rd | 新 |
| `record_trial` | — | rd | **删除**：试样来自模拟 ELN |
| `confirm_translation` / `contribute_translation` / `set_public_points(req_id, text, sealed)` / `decide_decrypt` | effect | rd | 保留，仅对话提议用 |
| `request_decrypt` | effect | sales | 保留，仅对话提议用 |

不变量（`test_wp_l`，不增加测试）：`pm:agent` 的工具集合中没有 `effect` 工具；它的 `search_knowledge` / `get_knowledge` / `get_requirement` 拿不到 L3 原文、`sealed` 与 `points_draft`；`effect` 工具在 `approve` 之前不改状态；非委托人 `approve` 抛 `PermissionDenied`。

## C12　⑨ 模拟业务周

模拟业务周照常走真实链路；推进类决策由「模拟人」签字：问题提出即签（`sign` / `accept`），模拟退回率为 0；`human_decision` 不在模拟周中产生。机会汇聚的属性 `n_escalations` 改为统计 `escalate` 事件（即业务员签字后的升级）。需求卡、注入清单仍只有 `sim/`、`eval/` 可读（铁律 5）。

## C13　v5.1 追加：现成产品复用（D17，已签字）

```python
# ⑦ escalation.py
class ReuseProposal(BaseModel):               # 产品经理 Agent 查 L2 知识后的现成产品建议
    product_id: str | None                    # None = 已查，无现成产品
    ku_refs: list[str] = []                   # 依据的 L2 知识（案例、L2 转化对照）；采用时给归属人记 cited
    customer_note: str = ""                   # 面向客户的一句说明（L1 可见，发出前过 leak_hits）
    note: str = ""                            # 给业务员的依据说明，只写归属，不写案例原文
    declined_reason: str = ""                 # 业务员不采用的理由

class Requirement(BaseModel):
    # …
    status: Literal["draft", "reused", "rd_accepted", "rd_confirmed", "released", "rejected"]   # 增加 reused
    reuse: ReuseProposal | None = None        # None = 还没查
```

- ⑤ requirement 属性：`reuse_checked` bool（`reuse` 不为空）、`reuse_pending` bool（有产品、未采用、未拒绝）、`reuse_declined` bool。
- ⑧ 事件：`reuse_proposed`（`requirement_id, product_id, ku_refs`）、`reuse_adopted`（`requirement_id, product_id, session_id`）、`reuse_declined`（`requirement_id, product_id, reason`）。
- ⑫ 门面：`save_reuse_proposal(req_id, product_id, ku_refs, customer_note, note, by)`（`pm:agent`，草稿）；`adopt_reuse(req_id, by)`（首个会话的业务员签字：按 Jev 披露版本给会话生成推荐卡，客户说明附在卡上，`customer_note` 过 `leak_hits`，所引 L2 知识记 cited，`status="reused"`，resolve `reuse_product`(sign)）；`decline_reuse(req_id, reason, by)`（业务员，resolve(return)，觉随后提出 `accept_requirement`）。业务员视图里的 `reuse` 只给产品（L1）、`customer_note` 与归属。
- ⑭ 工具：`propose_reuse(req_id, product_id, ku_refs, customer_note, note)`，draft，pm。
- ⑫ 视图（补漏）：`ReuseView(requirement_id, product_id, product_name, usage, customer_note, basis, status)`，`SessionView.reuse: ReuseView | None`；`basis` 是归属标签，不含案例原文；`JueTimeline` 对业务员的裁剪增加 `reuse_product`。
- 决策目录：新增 `reuse_product`（推进类，对象 requirement，主人 pm，签字人 sales）；`accept_requirement` 前置条件补 `attrs.reuse_checked and not attrs.reuse_pending and attrs.status == "draft"`。

## C14　v5.2：同类需求合并（D19）、Agent 协作焦点（D21）——已签字，已应用到契约 v5.2

```python
# ⑦ escalation.py
class Requirement(BaseModel):
    # …
    status: Literal["draft", "reused", "merged", "rd_accepted", "rd_confirmed", "released", "rejected"]   # 增加 merged
    merged_into: str | None = None            # 被并入的单指向主单
    merge_from: list[str] = []                # 产品经理 Agent 起草的合并建议：拟并入本单的需求单 id（研发签字前是草稿）
    merge_note: str = ""                      # 判断依据：几位客户说的是不是同一件事（L2 语言，L2/L3 可见）
```

- ⑤ 模板 `opportunity`：`decision_label` 改为「同类需求是否合并立项」，`signer_role: rd`；`refs` 增加 `requirement_ids`（逗号分隔，该主题 `draft`、已查过复用且无待签建议的单）与 `assigned_rd`（其中最早一张的研发）；C1 解析表增加一行「rd | theme → `refs.assigned_rd`」。
- ⑥ `opportunity` 的处置：研发合并 `sign`；研发直接接了其中一张单 `accept`；「现在不需要」`dismiss`。
- ⑧ 事件：`merge_proposed`（`question_id, target, members`；members 为空 = 判断不是同一件事）、`requirements_merged`（`question_id, target, members`）。
- ⑫ 门面：
  - `save_merge_proposal(question_id, target_req_id, member_ids, note, by)`：`pm:agent`，草稿；`target` 与 `members` 必须在问题的 `requirement_ids` 里；写 `merge_from`、`merge_note`。
  - `merge_requirements(question_id, by)`：主单的 `assigned_rd` 签字；`merge_from` 为空抛 `ValueError`；被并入单的会话追加到主单 `session_ids`，被并入单 `status="merged"`、`merged_into=主单`，其 open 问题 `resolve(answered, note="已并入 req:n")`；`resolve(opportunity, sign)`；**清空主单的 L2 草稿**（`product_lang`、`direction`，写 `requirement_edited`），主单待签问题 `set_prepared(None)`，产品经理 Agent 按合并后的全部会话重新起草（`draft_requirement` 照旧只对空单起草）。
  - `requirement_view` 的 `merge_from`、`merge_note` 对 L2/L3 可见。
  - 判断不是同一件事时：`target_req_id` 填 `requirement_ids` 中最早一张，`member_ids` 为空，`merge_note` 写理由。
  - 合并之后：`merged` 的单不再构建觉的状态；觉视图的需求单线程包含 `merged_into` 指向本单的单；`view_session` 取会话所在的未合并单。
  - 主题：`requirements_merged` 事件计为该主题「已处理」的时刻（与立项同样处理），合并后机会汇聚不会再次到点。
- ⑭ 工具：`propose_merge(question_id, target_req_id, member_ids, note)`，draft，pm。
- ⑭ `AgentHub.chat(actor_id, text, session_id=None, focus=None)`：`focus` 为委托人此刻在工作面上打开的对象（`sess:<n>` / `req:<n>`），写进 Agent 的系统提示词；Agent 据此理解「第 2 条」「这句话」指什么。
- 不改：每次升级仍各建一张单（REPLAN 4.2 原文）；立项 ≡ 研发接单（D11）。

## 待人确认的几处取舍

1. **`Family` 用带格式约束的字符串**（C1）：代价是类型检查不再能发现拼错的 family，由模板加载时校验兜住。
2. **`ScoredDecision.scored_by` 逐条**（C1）：同一次觉的输出里会同时有 Jue-K 和规则打分，界面按条显示；不加这个字段就只能整批标一个来源，觉视图会标错。
3. **草稿放进领域对象**（C3、C4）而不是单独的草稿表：字段多了几个，但工作面直接读对象就能就地显示，符合 D2「Agent 把草稿写进工作对象」。
4. **发送拦截查全部需求单的封存项**（C10）：不知道这句回复对应哪张单，只能全查；封存项少，代价可忽略。
5. 本差异**不改**：`Version`、披露上限、知识库接口、Jev 三个问题、网关与计量、种子格式（除 actors 一行）。
