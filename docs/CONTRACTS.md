# CONTRACTS.md

> 跨模块的数据格式与接口契约。**冻结后只能由人修改**。代码实现在 `src/huayan/contracts/`，必须与本文件一致。
> 下列代码是规格（Python / pydantic v2 风格），字段名、类型、枚举值必须一致；函数签名必须一致，内部实现自由。
> 版本：v4｜2026-10-11
>
> **v4 变更（觉回到「发现需要决策的情况，并给出校准概率」）**：Jue-K 从「只做追问」扩为**一个模型覆盖全部决策类型**，实时与定时都可以替换原型；新增决策类型 `ask_back`（需求单在 L2/L3 起草时发现缺一个会改变转译的信息，派回原业务员向客户回问），slot 对象增加 `layer`、`trans_splits`，新增 `requirement_state`；模板增加 `urgency` 表达式，`ScoredDecision.urgency`、`Question.urgency` 照填；新增 `JueRecord` 与 `jue_samples.jsonl`（每次觉调用的完整状态与输出，数据引擎）；`Discoverer` 增加 `jue_k`；`QFamily` 增加 `ask_back`，处置增加 `answered`，路由 `ask_back → sales`；配置增加 `scheduled_model`，`RunStatus` 增加同名字段；Jue-K 训练数据改为 `data/jue_k/samples.csv`，`features.build(obj, family)`；门面 `tick` / `add_turn` 增加回问的发布与回填；助手 `notify` 增加 `session_id`，业务员助手增加 `list_my_questions`。
>
> **v3 变更（角色助手）**：每个 L1/L2/L3 的人配一个角色助手（Agent Loop + 原子工具，第 ⑭ 节）。人用自然语言指挥助手，觉发现的问题派给对应人的助手主动处理；生效类动作由助手提议、委托人在确认卡上确认后执行。随之：转译引擎只保留规则模式（大模型通过助手参与），删去 `agent:pm_draft` / `agent:rd_translate` / `agent:package` 三个单次调用，caller 改为 `agent:sales` / `agent:pm` / `agent:rd`；`Requirement` 增加 `chem_drafted_by`、`public_points`、`sheet`；知识库增加 `search_blocked`；门面第 ⑫ 节的 L2/L3 方法改为原子方法，增加 `tick`；事件增加 `agent_action_proposed`、`agent_action_decided`。
>
> **v2 变更（围绕「分层转译」与「权责对等」）**：转化对照增加 `phenomenon_ids`；知识库增加 `list`；知识来源与积分原因增加 `contributed`；第 ⑦ 节改为两步转译（L2 产品需求 → L3 化学语言）＋反向包装，需求条目增加 `ku_refs`，新增 `RDDraft`、`SheetDraft`、`CitedKnowledge`、`RequirementView`、`ContributionStat`；事件增加 `requirement_translated`、`knowledge_contributed`；门面第 ⑫ 节 L2/L3 方法相应调整。其余章节不变。
>
> 本文件只规定**模块之间**传递什么。模块内部的数据怎么组织，由各工作包自己决定，不要为了「统一」把内部结构也写进契约。

---

## 0. 通用约定

- 所有 `datetime` 必须带时区，统一转换为 `Asia/Shanghai`；不带时区的输入直接报错。基类 `huayan.contracts._base.BaseModel`，所有模型 `extra="forbid"`。
- 文件读写显式 `encoding="utf-8"`；面向 Excel 的 CSV 用 `utf-8-sig`。JSONL 一行一个对象。
- 业务时间一律来自 `huayan.clock`：`get_clock().now()`。默认是 `WallClock`（现场演示），模拟业务周使用 `SimClock`。
- 随机数一律显式传入 `random.Random(seed)`，不使用全局随机数。
- **ID 格式**

| 对象 | 格式 | 例子 |
|---|---|---|
| 人 | `<role>:<id>` | `sales:S01`、`customer:C01`、`pm:P01`、`rd:R01`、`supervisor:M01` |
| 产品 | 虚构型号 | `HY-LV205` |
| 现象、槽位 | 小写英文 | `color_unlevel`、`fiber` |
| 知识单元 | `ku:<kind>:<ref>` | `ku:mechanism:HY-LV205` |
| 会话 / 轮次 | `sess:<n>` / `turn:<sess>:<n>` | `sess:3`、`turn:sess:3:2` |
| 问题 / 需求 / 试样 / 事件 | `q:<n>` / `req:<n>` / `trial:<n>` / `ev:<n>` | `q:12` |
| 觉的对象 | 见 5.1 | `slot:sess:3/fiber` |

- **角色与层级**（固定）

```python
Role = Literal["customer", "sales", "pm", "rd", "supervisor"]
Level = Literal[1, 2, 3]
ROLE_LEVEL: dict[Role, Level] = {"customer": 1, "sales": 1, "pm": 2, "rd": 3, "supervisor": 2}

class Actor(BaseModel):
    id: str                  # "sales:S01"
    role: Role
    name: str
```

---

## ① 种子数据（`seeds/`）

全部是**虚构的模拟数据**。每个文件结构为：

```yaml
placeholder: true            # true = 大模型生成的占位内容，待企业数据替换
source: "说明来源，如：占位，由大模型按行业常识生成"
items: [...]
```

### 1.1 槽位 `seeds/slots.yaml`

```python
class SlotDef(BaseModel):
    id: str                                   # "fiber"
    label: str                                # "面料成分"
    values: list[str]                         # 枚举取值，如 ["棉", "涤纶", "锦纶", "锦纶氨纶", ...]
    ask_text: str                             # 业务员追问话术，如「请问是什么面料？」
    ask_keywords: list[str]                   # 识别业务员在问这个槽位的关键词，如 ["面料", "什么布", "成分"]
    customer_phrases: dict[str, list[str]]    # 取值 → 客户口语说法（≥1 条）；不同取值之间的说法不得重复
```

槽位集合由种子决定，代码不得写死槽位 id（演示脚本和测试夹具除外）。

### 1.2 现象 `seeds/phenomena.yaml`

```python
class Phenomenon(BaseModel):
    id: str                                   # "color_unlevel"
    label: str                                # "色花（匀染性差）"
    customer_phrases: list[str]               # 客户的宏观描述，如「深一块浅一块」
    required_slots: list[str]                 # 研发判断前必须问清的槽位（种子①；B1 基线使用）
    causes: str                               # 常见原因与机理（L3 知识）
    slot_priors: dict[str, dict[str, float]] = {}   # 种子③：该现象下各槽位取值的比例，每个槽位内和为 1
```

### 1.3 产品 `seeds/products.yaml`

```python
class Product(BaseModel):
    id: str                                   # 虚构型号
    name: str
    category: str                             # 匀染剂 / 分散剂 / 防皱剂 …
    solves: list[str]                         # 现象 id
    applicable: dict[str, list[str]] = {}     # 槽位 → 适用取值；未列出的槽位不限
    sheet: str                                # 产品说明（L1）
    usage: str                                # 用法用量（L1）
    mechanism: str                            # 作用机理（L3，可经审批解密）
    formula: str                              # 配方要点（L3，永不对外）
    owner: str                                # 知识归属研发，如 "rd:R01"
    status: Literal["released", "project"] = "released"   # project = 研发中，不参与匹配，回流演示时发布
```

### 1.4 其他种子

```python
class Case(BaseModel):                        # seeds/cases.yaml，历史案例（L2）
    id: str
    phenomenon: str
    slots: dict[str, str]
    product_id: str | None                    # None = 当时没有解决
    scene_text: str                           # 客户原话摘要
    pm_translation: str                       # 产品经理的转述
    owner: str                                # "pm:P01"

class Translation(BaseModel):                 # seeds/translations.yaml，转化对照：转译的核心知识
    id: str
    scene_phrase: str                         # 原文：L2 条目为客户场景说法，如「深一块浅一块」；
                                              #       L3 条目为产品需求说法，如「匀染」「低浴比」
    chem_term: str                            # 译文：L2 条目为产品需求语言，如「需要匀染类助剂」；
                                              #       L3 条目为化学语言，如「对酸性染料有缓染作用的阴离子型组分」
    level: Literal[2, 3]                      # 2 = 产品经理的「场景 → 产品需求」；3 = 研发的「产品需求 → 化学语言」
    owner: str                                # 归属人：L2 条目为产品经理，L3 条目为具体某位研发
    phenomenon_ids: list[str] = []

# seeds/actors.yaml：list[Actor]，至少包含 2 个业务员、4 个客户、1 个产品经理、2 个研发、1 个主管
```

### 1.5 领域函数 `huayan.domain`（WP-0 提供，所有包共用，不得各写一套）

```python
class Seeds(BaseModel):
    slots: list[SlotDef]; phenomena: list[Phenomenon]; products: list[Product]
    cases: list[Case]; translations: list[Translation]; actors: list[Actor]
    placeholder: bool                         # 任一文件为占位即为 True

class Candidate(BaseModel):
    product_id: str
    unknown_slots: list[str]                  # applicable 中有限定、但当前未知的槽位

def load_seeds(seeds_dir: str | Path) -> Seeds: ...
def consistent(product: Product, known: dict[str, str]) -> bool: ...
    # 已知槽位中，凡是 product.applicable 有限定的，取值都在适用范围内
def match_candidates(phenomenon: str, known: dict[str, str], products: list[Product]) -> list[Candidate]: ...
    # status == "released" 且 phenomenon in solves 且 consistent；按 id 排序
def correct_product(phenomenon: str, slots: dict[str, str], products: list[Product]) -> str | None: ...
    # 全部真值下的候选；0 个 → None（应升级）；多个 → applicable 限定的槽位最多者，并列取 id 最小
def detect_asked_slots(text: str, slots: list[SlotDef]) -> list[str]: ...   # 按 ask_keywords
def find_slot_values(text: str, slots: list[SlotDef]) -> dict[str, tuple[str, str]]: ...
    # 按 customer_phrases 与取值本身匹配：槽位 → (取值, 命中的原话片段)；同一槽位命中多个取值时取最长匹配
def find_phenomenon(text: str, phenomena: list[Phenomenon]) -> tuple[str, str] | None: ...   # (现象 id, 原话片段)
```

---

## ② 知识、权限与披露

### 2.1 知识单元

```python
KUKind = Literal["sheet", "usage", "case", "translation", "requirement", "mechanism", "formula", "trial"]
KIND_LEVEL: dict[KUKind, Level] = {"sheet": 1, "usage": 1, "case": 2, "requirement": 2,
                                    "mechanism": 3, "formula": 3, "trial": 3}   # translation 取种子中的 level

class KnowledgeUnit(BaseModel):
    id: str                                   # "ku:<kind>:<ref>"
    level: Level
    kind: KUKind
    title: str
    text: str
    product_id: str | None = None
    phenomenon_ids: list[str] = []
    owner: str                                # 知识归属人
    decryptable: bool = False                 # 只有 mechanism 为 True
    source: Literal["seed", "released", "trial", "contributed"] = "seed"
    created_at: datetime

class KnowledgeHit(BaseModel):
    ku: KnowledgeUnit
    score: float

class BlockedHint(BaseModel):                 # 越权命中只告诉调用方「谁知道」，不给标题和正文
    owner: str
    level: Level
    kind: KUKind
```

### 2.2 知识库 `huayan.knowledge.KnowledgeBase`（WP-A1）

```python
class PermissionDenied(Exception): ...

class KnowledgeBase:
    @classmethod
    def from_seeds(cls, seeds: Seeds, events: EventLog, audit: AuditLog) -> "KnowledgeBase": ...
        # 每个产品生成 sheet/usage/mechanism/formula 四条；每个案例、转化对照各一条
    def products(self) -> list[Product]: ...                 # 当前已发布产品（含回流发布的新产品）
    def product(self, product_id: str) -> Product: ...
    def add_product(self, product: Product, at: datetime) -> list[KnowledgeUnit]: ...   # 发布，生成四条知识
    def update_applicable(self, product_id: str, slot: str, values: list[str], by: str) -> None: ...
    def add(self, ku: KnowledgeUnit) -> None: ...
    def list(self, actor: Actor, *, kinds: list[KUKind] | None = None,
             phenomenon: str | None = None) -> list[KnowledgeUnit]: ...
        # 按层级过滤后列出；phenomenon 不为 None 时只保留 phenomenon_ids 含它或为空的条目。转译引擎用它取候选知识
    def get(self, ku_id: str, actor: Actor) -> KnowledgeUnit: ...
        # 越权抛 PermissionDenied，写审计 deny 与 access_denied 事件
    def search(self, query: str, actor: Actor, *, phenomenon: str | None = None, k: int = 5,
               session_id: str | None = None) -> list[KnowledgeHit]: ...
        # 先按层级过滤再打分（关键词 / 字符二元组即可）。
        # 被过滤掉、但本来会命中的条目：只记入 retrieve 事件的 n_blocked 与 blocked_product_ids，不返回给调用方。
        # 被冻结的人（2.3）检索 L1 以外的意图时直接返回空。
    def search_blocked(self, query: str, actor: Actor, *, phenomenon: str | None = None,
                       k: int = 3) -> list[BlockedHint]: ...
        # 与 search 同样打分，只看被层级过滤掉的那一组，返回前 k 条的归属人、层级、类型（不含标题与正文）。
        # 助手据此知道「这件事研发 R01 知道」，权限不下泄、但知道该找谁。
```

### 2.3 权限 `huayan.knowledge.permission`（WP-A1）

```python
def level_of(actor: Actor) -> Level: ...
def can_read(actor: Actor, ku: KnowledgeUnit) -> bool: ...      # ku.level <= level_of(actor)

# 冻结状态存在 KnowledgeBase 实例上，不用模块级全局变量
KnowledgeBase.is_frozen(actor_id: str) -> bool
KnowledgeBase.freeze(actor_id: str, by: str, at: datetime) -> None   # 「泄露风险」处置；写 access_frozen 事件与审计
```

### 2.4 披露

```python
Version = Literal["product", "product_usage", "full_mechanism", "internal"]
# product        产品名与说明                    L1 可见
# product_usage  + 用法用量                      L1 可见（默认对外版本）
# full_mechanism + 作用机理                      仅 L3，或 L1 在该客户×该产品有解密授权时
# internal       + 配方要点 + 试样记录            仅 L3，永不对外
CUSTOMER_VERSIONS = ["product", "product_usage", "full_mechanism"]   # Jev 只在这三者中选

class DecryptGrant(BaseModel):
    id: str
    customer_id: str
    product_id: str
    session_id: str
    approved_by: str                          # 产品的知识归属研发
    at: datetime

class CardSection(BaseModel):
    title: str
    text: str
    ku_id: str
    level: Level

class RecommendationCard(BaseModel):          # 按「查看者」渲染的结果，不落盘
    session_id: str
    viewer: str
    product_id: str | None                    # None = 已升级，无推荐
    version: Version                          # 实际渲染的版本
    sections: list[CardSection]
    note: str = ""                            # 如「已转产品经理处理」「机理已经研发审批解密」

# huayan.knowledge.disclosure（WP-A1）
def cap(viewer: Actor, customer_id: str, product_id: str, grants: list[DecryptGrant]) -> Version: ...
    # L1：product_usage；存在该客户×该产品的授权时 full_mechanism
    # L2：product_usage（另可看案例与需求单，不看机理）
    # L3：internal
def render(product_id: str, version: Version, viewer: Actor, kb: KnowledgeBase) -> RecommendationCard: ...
    # 只渲染 version 允许的知识单元；调用方保证 version 不超过 cap
```

**不变量（必须有测试）**：查看者为 L1 且无授权时，渲染结果和任何 L1 回复中不出现 level ≥ 2 的知识单元；任何情况下 L1 看不到 `formula` 与 `trial`。

### 2.5 审计与积分（WP-A1）

```python
class AuditRecord(BaseModel):
    ts: datetime
    actor: str
    action: Literal["disclose", "deny", "decrypt_request", "decrypt_approve", "decrypt_reject", "freeze"]
    object_ids: list[str]                     # ku / 产品 / 会话
    version: Version | None = None
    session_id: str | None = None
    reason: str = ""

class LedgerEntry(BaseModel):
    ts: datetime
    owner: str                                # 获得积分的人
    points: int
    reason: Literal["cited", "contributed", "trial_pass", "product_released", "bounty"]
    ku_id: str | None = None
    ref: str                                  # 会话 / 试样 / 产品 / 问题 id

class AuditLog:   # append(record) / list(actor=None) ；写 runs/<run>/audit.jsonl
class Ledger:     # add(entry) / totals() -> dict[owner, points] / list(owner=None)；写 ledger.jsonl
```

积分规则在 `config/app.yaml` 的 `points`（**权责对等的落点**）：
- `cited`：知识单元被一次推荐卡片引用，或被一张确认的需求单（`ReqItem.ku_refs`）引用，给其归属人记分；同一知识在同一会话或需求单中只记一次；
- `contributed`：研发把自己修改后的转译沉淀为新的转化知识；
- `trial_pass`：试样通过；`product_released`：新品发布（给产品归属研发）；`bounty`：处理带悬赏的问题。

---

## ③ 会话与需求

```python
Intent = Literal["need", "product_question", "mechanism_request", "smalltalk"]

class Turn(BaseModel):
    id: str                                   # "turn:sess:3:2"
    session_id: str
    n: int                                    # 从 1 开始
    speaker: Literal["customer", "sales"]
    text: str
    ts: datetime

class SlotFill(BaseModel):
    slot: str
    value: str | None                         # 必须是 SlotDef.values 中的值；status=unknown 时为 None
    status: Literal["filled", "unknown"]      # unknown = 客户答「不清楚」
    confidence: float = Field(ge=0, le=1)
    quote: str                                # 客户原话片段（溯源）
    turn_id: str

class CustomerProfile(BaseModel):
    chem_savvy: bool = False                  # 从对话判断客户是否懂化学
    asked_mechanism: bool = False             # 客户是否明确要求了解原理
    evidence_quote: str = ""

class NeedState(BaseModel):
    session_id: str
    customer_id: str
    sales_id: str
    phenomenon: str | None = None
    phenomenon_quote: str = ""
    slots: dict[str, SlotFill] = {}
    asked: dict[str, int] = {}                # 槽位 → 业务员已追问次数
    turn_count: int = 0
    profile: CustomerProfile = CustomerProfile()
    last_intent: Intent = "need"
    extracted_by: Literal["llm", "rule"] = "llm"

    def known(self) -> dict[str, str]: ...    # status == "filled" 的槽位 → 取值

class ExtractedSlot(BaseModel):               # 抽取 Agent 的输出单元
    slot: str
    value: str | None
    status: Literal["filled", "unknown"]
    confidence: float = Field(ge=0, le=1)
    quote: str
    turn_n: int

class ExtractionResult(BaseModel):            # 抽取 Agent 结构化输出（caller "agent:extract"）
    intent: Intent
    phenomenon: str | None
    phenomenon_quote: str = ""
    slots: list[ExtractedSlot] = []           # 只含本次新增或改变的槽位
    asked_slots: list[str] = []               # 最新一句业务员发言追问了哪些槽位
    profile: CustomerProfile

# huayan.l1.extract（WP-A2）
class Extractor(Protocol):
    name: Literal["llm", "rule"]
    def extract(self, turns: list[Turn], prev: NeedState) -> ExtractionResult: ...
def apply_extraction(prev: NeedState, result: ExtractionResult, turns: list[Turn]) -> NeedState: ...
    # 取值不在枚举内的槽位丢弃；turn_n 换成 turn_id
```

`rule` 抽取器只用 `huayan.domain` 的 `find_phenomenon` / `find_slot_values` / `detect_asked_slots`，置信度固定 0.7，不调用大模型。模拟业务周和离线测试使用它。

```python
class AskHint(BaseModel):
    session_id: str
    slot: str
    label: str                                # 槽位中文名
    ask_text: str                             # 建议话术
    p_need: float
    scored_by: str                            # 同 JueOutput.scored_by

class Recommendation(BaseModel):              # 会话里存的「决定」，渲染另做
    product_id: str | None
    candidates: list[Candidate]
    match: JevDecision | None                 # 无候选时为 None
    disclose: JevDecision | None
    version: Version | None                   # 对 L1 披露的版本
    escalated_question_id: str | None = None
    at: datetime

class AssistantReply(BaseModel):              # 问答类意图（product_question / mechanism_request）的回复
    turn_id: str
    text: str
    ku_ids: list[str]
    blocked: bool                             # 命中了高层级内容但被拦截
    grounding: JevDecision | None = None

class Session(BaseModel):
    id: str
    customer_id: str
    sales_id: str
    started_at: datetime
    turns: list[Turn] = []
    need: NeedState
    hints: list[AskHint] = []                 # 当前有效的追问提示
    replies: list[AssistantReply] = []
    recommendation: Recommendation | None = None
    status: Literal["open", "recommended", "escalated", "closed"] = "open"
```

---

## ④ Jev（`huayan.jev`，WP-A2）

### 4.1 System 1 题型（与 JUE 一致，客户端复制自 JUE）

```python
class S1Noul(BaseModel):   kind: Literal["noul"] = "noul";     text: str
class S1Choice(BaseModel): kind: Literal["choice"] = "choice"; text: str; options: dict[str, str]
class S1Score(BaseModel):  kind: Literal["score"] = "score";   text: str; levels: list[str]
S1Question = S1Noul | S1Choice | S1Score

class S1Answer(BaseModel):
    probabilities: dict[str, float]           # noul: {"yes", "no"}
    expected: float | None = None

class S1Result(BaseModel):
    answers: dict[str, S1Answer]
    latency_ms: float
    impl: Literal["onejev", "llm_fallback", "mock"]
    degraded: bool                            # impl != "onejev"

class System1Client(Protocol):
    def ask(self, state: dict[str, Any], media: list, questions: dict[str, S1Question], caller: str) -> S1Result: ...
```

- `OneJevClient`、`LLMSystem1Fallback` 从 JUE 复制，只改 import；`build_system1(impl, config_path, gateway, meter)` 同 JUE，另支持 `impl="mock"`。
- `MockSystem1Client`（确定性规则桩，`impl="mock"`），按 caller 区分：
  - `jev:match`：候选权重 `1 / (1 + len(unknown_slots))`，`none` 权重为 0.2，归一化；
  - `jev:disclose`：`profile.chem_savvy and profile.asked_mechanism` 且选项含 `full_mechanism` 时 0.7 给它；否则 0.7 给 `product_usage`；其余平分；
  - `jev:grounding`：state 中 `hits` 非空时 `grounded` 0.7，否则 `none` 0.7；其余平分；
  - 其他 caller：均匀分布；`S1Noul` 为 0.5。

### 4.2 三个问题

```python
class JevDecision(BaseModel):
    question: Literal["match", "disclose", "grounding"]
    probabilities: dict[str, float]           # 选项 id → 概率
    choice: str                               # 概率最大的选项
    confident: bool
    scored_by: Literal["onejev", "llm_fallback", "mock", "rule"]

class Jev:
    def __init__(self, system1: System1Client, match_threshold: float = 0.5): ...
    def match(self, need: NeedState, candidates: list[Candidate], products: dict[str, Product]) -> JevDecision: ...
        # 选项 = 候选产品 id + "none"；caller "jev:match"；confident = p(choice) ≥ match_threshold 且 choice != "none"
        # 无候选时不调用 System 1：probabilities={"none": 1.0}，scored_by="rule"
    def disclose(self, need: NeedState, product_id: str, cap: Version) -> JevDecision: ...
        # 选项 = CUSTOMER_VERSIONS 中不超过 cap 的版本；只有一个选项时不调用，scored_by="rule"；caller "jev:disclose"
    def grounding(self, answer: str, hits: list[KnowledgeHit]) -> JevDecision: ...
        # 选项 grounded / partial / none；caller "jev:grounding"（可砍）
```

**传给 System 1 的 state 只含请求者权限内的内容**（第三个权限卡点）：

```json
{"need": {"phenomenon": "...", "slots": {"fiber": {"value": "锦纶氨纶", "quote": "..."}}, "profile": {...}},
 "candidates": [{"id": "HY-LV205", "name": "...", "category": "...", "applicable": {...}, "unknown_slots": [...]}],
 "hits": [{"title": "...", "text": "..."}]}
```

### 4.3 推荐与升级规则（WP-A2 实现，写死，不做配置）

每轮发言后：抽取 → 觉追问（5.4）→ 若现象已知且**没有追问提示**，或业务员点了「直接推荐」，则匹配：
- `choice == "none"`，或 `not confident` 且没有追问提示 → **升级**：发布 `escalate_need` 问题（第 ⑥ 节），`status="escalated"`；
- `not confident` 但仍有追问提示 → 不推荐，继续追问；
- 否则推荐 `choice`，`disclose` 选版本，对 L1 渲染，写 `recommend` 事件、披露审计、引用积分。

---

## ⑤ 觉（`huayan.jue`，WP-B1 / WP-B3）

### 5.1 觉的输入：对象与状态

```python
ObjectType = Literal["slot", "theme", "knowledge", "actor"]

class JueObject(BaseModel):
    object_id: str
    object_type: ObjectType
    attrs: dict[str, float | int | str | bool]    # 命名见 5.2，不得增删字段名而不改契约

class JueState(BaseModel):
    at: datetime
    mode: Literal["realtime", "scheduled"]
    objects: dict[str, JueObject]
    def to_s1_state(self, object_ids: list[str] | None = None) -> dict: ...
        # {"at": iso, "objects": {id: {"type": ..., "attrs": {...}}}}
```

| 对象类型 | object_id | 模式 | 由谁构建 |
|---|---|---|---|
| `slot` | `slot:<session_id>/<slot>`（`layer=1`，对话中）／`slot:<req_id>/<slot>`（`layer=2/3`，需求单起草中） | 实时 | `realtime_state(need, seeds, products, at)`／`requirement_state(req, need, seeds, kb, at)` |
| `theme` | `theme:<phenomenon>|<slot>=<value>,...`（该现象 required_slots 中已知的部分，按槽位 id 排序） | 定时 | `scheduled_state(events, at, seeds, products)` |
| `knowledge` | `knowledge:<product_id>|<slot>=<value>` | 定时 | 同上 |
| `actor` | `actor:<actor_id>` | 定时 | 同上 |

三个构建函数都在 `huayan.jue.state`（WP-B1 写前两个，WP-B3 增加 `requirement_state`），**只读 NeedState / 需求单 / 事件日志 / 种子 / 知识库**，不读需求卡、注入清单。

```python
def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime) -> JueState: ...
    # 只对 status 为 draft（layer=2）或 pm_confirmed（layer=3）的需求单；为该现象每个槽位生成一个 slot 对象；
    # need = 需求单首个会话的 NeedState，已知槽位以 req.known_slots 为准；mode="realtime"
```

### 5.2 属性命名表

**slot（实时：对话中的追问 `ask_slot`、需求单起草中的回问 `ask_back`）**

| 属性 | 类型 | 含义 |
|---|---|---|
| `slot` | str | 槽位 id |
| `phenomenon` | str | 现象 id；未识别为 `"unknown"` |
| `filled` | bool | 已填 |
| `unknown` | bool | 客户答过「不清楚」 |
| `confidence` | float | 抽取置信度，未填为 0 |
| `asked` | int | 业务员已追问次数 |
| `required` | bool | 种子①中该现象必问 |
| `turn` | int | 对话轮次 |
| `n_filled` | int | 已填槽位数 |
| `n_candidates` | int | 当前已知条件下的候选产品数 |
| `splits` | int | 该槽位取各个值时，候选集会变成几种不同的集合（≥ 2 说明问了会改变推荐）；已填为 0 |
| `prior_top` | float | 该现象下此槽位最常见取值的比例（种子③，没有则 0） |
| `chem_savvy` | bool | 客户画像 |
| `layer` | int | 1 = 对话中（`realtime_state`）；2 = L2 起草中、3 = L3 起草中（`requirement_state`） |
| `trans_splits` | int | 该槽位取各个值时，本层转化对照（layer 2 看 L2、layer 3 看 L3；layer 1 恒为 0）的命中集合会变成几种（≥ 2 说明问了会改变转译）；已填为 0。计算：text = 现象名 + 已知槽位取值（含假设取值 v）拼接，以 level=3 的内部身份调用 `match_translations(text, kb, actor, phenomenon)`，再按层级筛选；只产出计数，不外泄内容 |

**theme（定时，机会汇聚）**：`phenomenon` str、`n_escalations` int（窗口内升级次数）、`n_customers` int（涉及客户数）、`n_matched` int（同主题被成功推荐次数）、`days_active` int（出现过的天数）、`open_project` bool（已有对应需求单在途）、`mean_p_none` float。

**knowledge（定时，知识冲突）**：`product_id` str、`slot` str、`value` str、`claimed` bool（说明书声称适用）、`n_trials` int、`n_fail` int、`n_fail_product` int（失败原因为产品本身）、`fail_ratio` float、`n_recommended` int。

**actor（定时，泄露风险）**：`role` str、`n_queries` int、`n_mech_requests` int、`n_blocked` int（被拦截的高层级命中数）、`blocked_top_share` float（被拦截命中中最集中的产品占比）、`n_distinct_products` int、`frozen` bool。

定时窗口：机会汇聚、知识冲突 7 天，泄露风险 48 小时（`config/app.yaml` 可改）。

Jue-K 的特征来自以上全部对象类型的属性（`features.build(obj, family)`，缺失的属性记 0）。

### 5.3 模板 `config/templates/*.yaml`（一个模板一个文件）

```python
Family = Literal["ask_slot", "ask_back", "opportunity", "knowledge_conflict", "leak_risk"]

class JueTemplate(BaseModel):
    id: str
    family: Family
    object_type: ObjectType
    decision_label: str                       # 「是否追问该信息」「是否立项」…
    precondition: str | None = None           # 布尔表达式，只能引用 attrs.x
    rule_score: str | None = None             # 数值表达式，规则模式下的 p_need（结果截断到 [0,1]）；为空时 1.0
    worth_prompt: str                         # Jev 是非题，含 {object}
    title: str                                # 发布后的问题标题，可含 {object} 与 {attrs.x}
    owner_role: Role                          # ask_slot 为 sales（不进总线）；ask_back 为 sales（进总线，owner_id = 会话的业务员）
    bounty_points: int = 0
    urgency: str | None = None                # 数值表达式，截断到 [0,1]；为空时 1.0。紧急度是规则，不学习
```

模板共 5 个：`ask_slot`（前置条件含 `attrs.layer == 1`）、`ask_back`（含 `attrs.layer >= 2`、未填、未答不清楚、`attrs.trans_splits >= 2`）、`opportunity`、`knowledge_conflict`、`leak_risk`。

表达式求值器 `huayan.jue.expr` 复制自 JUE `discovery/expr.py`，只保留 `attrs.x`。基线（B1、B2、规则告警）也写成模板，放在 `config/baselines/<name>/`，由同一个原型在规则模式下运行。

### 5.4 觉模型接口

```python
class ScoredDecision(BaseModel):
    family: Family
    object_id: str
    p_need: float | None = Field(default=None, ge=0, le=1)   # None = 前置条件未通过
    urgency: float | None = None              # 前置条件通过时 = 模板 urgency 表达式的值；未通过为 None
    precondition_passed: bool = True
    template_id: str | None = None

class JueOutput(BaseModel):
    at: datetime
    mode: Literal["realtime", "scheduled"]
    model: Literal["jue_proto", "jue_k"]
    scored_by: Literal["onejev", "rule", "jue_k"]
    decisions: list[ScoredDecision]           # 覆盖本次评估的全部「模板 × 对象」；全部低概率即「无事」

class QuestionModel(Protocol):
    name: Literal["jue_proto", "jue_k"]
    def propose(self, state: JueState) -> JueOutput: ...
```

- **`JueProto(templates_dir, system1, mode)`**：模板 × 匹配 `object_type` 的对象枚举全部组合；前置条件不通过的 `p_need=None`。`system1` 为 `OneJevClient` 时，通过者的 worth 题**一次** `ask` 批量打分（caller `jue:proto`），`scored_by="onejev"`；否则**不调用任何模型**，用 `rule_score`，`scored_by="rule"`。
- **`JueK(model_dir, templates_dir, mode)`**（WP-B3）：**一个模型覆盖全部五类决策**。与原型用同一套模板枚举「模板 × 对象」、同一套前置条件（不通过的 `p_need=None`）；通过者由同一个梯度提升模型一次批量推理，按 `family` 分别校准，输出校准概率；`scored_by="jue_k"`。实时（`ask_slot`、`ask_back`）与定时（三类）都可以把原型换成它，运行链路、发布层、界面不改。
- **紧急度**：两个实现都用模板的 `urgency` 表达式填 `ScoredDecision.urgency`（规则，不学习，如实标注）。
- **铁律**：两个实现都不调用网关；觉每次 `propose` 写一条 `kind="jue"` 计量（耗时、对象数）；调用方（门面）把每次的状态与输出写成一条 `JueRecord`（数据引擎）。

```python
class JueRecord(BaseModel):                   # runs/<run_id>/jue_samples.jsonl，每次 propose 一行
    state: JueState
    output: JueOutput
```

记录覆盖全部组合（包括低概率的「无事」）。上线后用真实处置结果（问题被处置 / 驳回、回问后转译是否改变）回填标签，再训练与校准。

```python
# huayan.jue.publish（WP-B1）
def select_asks(out: JueOutput, state: JueState, seeds: Seeds, threshold: float, max_asks: int = 2) -> list[AskHint]: ...
    # ask_slot 中 p_need ≥ threshold 的，按 p_need 降序取前 max_asks
def publish(out: JueOutput, state: JueState, templates: dict[str, JueTemplate], bus: QuestionBus,
            threshold: float) -> list[Question]: ...
    # 定时：p_need ≥ threshold 的组合生成问题；证据取对象属性中的关键数字与相关事件 id
    # ask_back 也走 publish：owner_role=sales，owner_id=会话的业务员，refs={session_id, requirement_id, slot}；
    # 所有问题的 urgency 取自 ScoredDecision

# huayan.jue.scan（WP-B1）
def scan(events: EventLog, at: datetime, model: QuestionModel, seeds: Seeds, products: list[Product],
         templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float) -> list[Question]: ...
    # scheduled_state → propose → publish；新发布的问题列表
```

### 5.5 定时发现的对照接口（WP-E）

```python
class Discoverer(Protocol):
    name: Literal["jue_proto", "jue_k", "rule_alert", "llm_poll"]
    def discover(self, events: EventLog, at: datetime) -> list[Question]: ...
```

四者输入相同（同一事件日志），都不得读取注入清单和需求卡。

---

## ⑥ 问题总线（`huayan.bus`，WP-0 提供）

```python
QFamily = Literal["escalate_need", "ask_back", "opportunity", "knowledge_conflict", "leak_risk", "decrypt_request"]

class Evidence(BaseModel):
    summary: str
    event_ids: list[str] = []
    quote: str = ""

class Resolution(BaseModel):
    action: Literal["draft_requirement", "approve_project", "update_sheet", "freeze_access",
                    "approve_decrypt", "reject_decrypt", "dismiss", "answered"]   # answered：回问已由客户回答
    by: str
    note: str = ""

class Question(BaseModel):
    id: str
    family: QFamily
    title: str
    object_id: str                            # sess:3 / theme:... / knowledge:... / actor:...
    owner_role: Role
    owner_id: str | None = None               # 指定到人（解密审批、知识冲突给知识归属人）
    status: Literal["open", "resolved", "dismissed"] = "open"
    p_need: float | None = None
    urgency: float | None = None              # v4：觉发现的问题来自 ScoredDecision；其他来源为 None
    scored_by: str                            # onejev / llm_fallback / mock / rule / jue_k / human
    discoverer: Literal["jev", "jue_proto", "jue_k", "rule_alert", "llm_poll", "human"]
    evidence: list[Evidence] = []
    refs: dict[str, str] = {}                 # session_id / requirement_id / product_id / customer_id …
    bounty_points: int = 0
    dedup_key: str                            # f"{family}:{object_id}"
    created_at: datetime
    resolved_at: datetime | None = None
    resolution: Resolution | None = None

class QuestionBus:
    def __init__(self, events: EventLog, path: Path | None = None, suppress_hours: float = 24): ...
        # path：questions.jsonl，每次变化追加一行快照；None 时只在内存
    def publish(self, q: Question) -> Question: ...
        # 同 dedup_key 有 open 问题：合并证据，返回已有问题；
        # 同 dedup_key 在 suppress_hours 内被 dismissed：丢弃，返回被丢弃的问题本身（status 不变）；
        # 否则入库，写 question_published 事件。id 由总线分配。
    def get(self, qid: str) -> Question: ...
    def list(self, owner_role: Role | None = None, status: str | None = "open", family: QFamily | None = None) -> list[Question]: ...
    def resolve(self, qid: str, resolution: Resolution, at: datetime) -> Question: ...
        # dismiss → status=dismissed，其余 → resolved；写 question_resolved 事件
```

路由在 `config/app.yaml` 的 `routing`：`escalate_need → pm`、`ask_back → sales`（owner_id = 会话的业务员）、`opportunity → pm`、`knowledge_conflict → rd`（owner_id = 产品归属人）、`leak_risk → supervisor`、`decrypt_request → rd`（owner_id = 产品归属人）。发布方负责按路由填写 `owner_role` / `owner_id`。

---

## ⑦ 升级、分层转译与回流（`huayan.escalation`）

**转译是化言的主线。** 一个 L1 解决不了的需求，按层逐步转译，每一层只用自己能看的知识，每一句都能回查客户原话、标明依据了谁的知识：

```
L1 场景需求卡（NeedState：槽位＋原话）
  → L2 产品需求语言（规则骨架 → 产品经理助手用 L2 知识检索、逐条修改 → 产品经理在确认卡上确认）
  → L3 化学语言需求单（规则骨架 → 研发助手用 L3 转化对照与机理修改 → 研发确认；修改可沉淀为自己的转化知识）
  → 试样 → 研发确认「对外要点」（L3 内容流向下层的唯一出口）
  → 反向包装：L1 说明书（只用产品需求＋对外要点，不接触机理与配方；产品经理助手可修改）→ 产品经理确认发布 → 回到 L1
```

```python
class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []                # turn id，可回查客户原话
    ku_refs: list[str] = []                   # 依据的知识单元（转化对照、案例、机理）；其归属人记 cited

class PMDraft(BaseModel):                     # L2：场景语言 → 产品需求语言（规则骨架，产品经理助手编辑）
    direction: str                            # 产品方向，如「低浴比条件下的锦纶氨纶匀染助剂」
    product_lang: list[ReqItem]

class RDDraft(BaseModel):                     # L3：产品需求 → 化学语言（规则骨架，研发助手编辑）
    chem_lang: list[ReqItem]
    hypotheses: list[str] = []                # 研发方向假设

class SheetDraft(BaseModel):                  # 反向包装：产品需求＋对外要点 → L1 说明书（规则模板，产品经理助手编辑）
    sheet: str
    usage: str

class Requirement(BaseModel):
    id: str                                   # "req:<n>"
    question_id: str
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    direction: str
    product_lang: list[ReqItem]               # L2/L3 可见
    chem_lang: list[ReqItem] = []             # L2/L3 可见；所引 L3 知识的原文只有 L3 可见
    hypotheses: list[str] = []
    status: Literal["draft", "pm_confirmed", "rd_confirmed", "released", "rejected"]
    drafted_by: str                           # L2 草稿的委托人（产品经理 actor id）
    chem_drafted_by: str | None = None        # L3 草稿的委托人（研发 actor id）
    pm_confirmed_by: str | None = None
    rd_confirmed_by: str | None = None
    public_points: str = ""                   # 研发确认可以对外的要点：L3 内容流向 L2/L1 的唯一出口
    sheet: SheetDraft | None = None           # 反向包装草稿
    product_id: str | None = None             # 目标产品：L3 确认时关联种子中 status=project 的产品；发布后即新产品
    created_at: datetime

class Trial(BaseModel):
    id: str
    product_id: str
    requirement_id: str | None = None
    rd: str
    conditions: dict[str, str]                # 试样条件（槽位 → 取值）
    result: Literal["pass", "fail"]
    cause: Literal["none", "product", "equipment", "operation"]
    note: str = ""
    at: datetime

class CitedKnowledge(BaseModel):              # 需求单中被引用的知识，按查看者裁剪
    ku_id: str
    owner: str
    level: Level
    title: str
    text: str | None                          # 查看者无权阅读时为 None，界面只显示「研发 R01 的转化知识（L3）」
    n_cited: int                              # 全系统累计被引用次数

class RequirementView(BaseModel):
    viewer: str
    viewer_level: Level
    requirement: Requirement
    quotes: dict[str, str]                    # turn id → 客户原话
    cited: list[CitedKnowledge]

class ContributionStat(BaseModel):            # 贡献看板的一行
    owner: str
    ku_id: str
    level: Level
    title: str
    n_cited: int
    points: int
    used_by: list[str]                        # 需求单 / 会话 id
```

### 7.1 转译引擎 `huayan.escalation.translate`（WP-T）

```python
def match_translations(text: str, kb: KnowledgeBase, actor: Actor,
                       phenomenon: str | None = None) -> list[KnowledgeHit]: ...
    # 在 kb.list(actor, kinds=["translation"], phenomenon=...) 中按 scene_phrase 与 text 的子串 / 字符二元组匹配；
    # 规则骨架与助手工具 match_translations 共用
def draft_product_need(q: Question, sessions: list[Session], kb: KnowledgeBase, pm: Actor, at: datetime) -> PMDraft: ...
    # 输入：会话轮次（带 turn id）、NeedState 槽位与原话、kb.list(pm, kinds=["case", "translation"], phenomenon=...)
def draft_chem_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, rd: Actor, at: datetime) -> RDDraft: ...
    # 输入：产品需求条目、原话、kb.list(rd, kinds=["translation", "mechanism"], phenomenon=...)
def package_sheet(req: Requirement) -> SheetDraft: ...
    # 输入只有 req.product_lang 与 req.public_points；不得读机理、配方、L3 转化对照
```

- 三个函数都是**规则实现**（零成本、确定；离线演示、测试与评测用）：按转化对照的 `scene_phrase` 与原话 / 上一层条目文字的匹配逐条生成，`ku_refs` 指向命中的转化对照，`quote_refs` 指向命中的轮次；没有命中知识的原话保留为「未转译」条目，不编造。
- 大模型参与转译的方式是**角色助手**（第 ⑭ 节）：助手先调用规则骨架，再用工具检索、逐条修改。
- **不变量（有测试）**：`draft_product_need` 的输出不含任何 L3 知识；`package_sheet` 的输出不含 L3 内容。

### 7.2 流程 `huayan.escalation.flow`（WP-A3）

```python
def contribute_translation(req: Requirement, item_index: int, scene_phrase: str, chem_term: str,
                           by: Actor, kb, ledger, events, at) -> KnowledgeUnit: ...
    # 研发把修改后的一条 chem_lang 沉淀为 L3 转化对照：kind="translation"，level=3，owner=by，source="contributed"；
    # 记 contributed 积分与 knowledge_contributed 事件；该条 ReqItem.ku_refs 追加新知识
def release_product(req: Requirement, product: Product, kb, ledger, events, by: str, at) -> Product: ...
    # product.status 改为 released → kb.add_product → 给 product.owner 记 product_released
    # → 写 product_released 事件 → req.status = "released"
```

演示中新产品取自种子里 `status="project"` 的产品（`confirm_translation` 时由门面关联到 `req.product_id`，机理与配方要点来自它），模拟「研发在 ELN 中完成开发」；L1 说明书与用法来自 `req.sheet`（反向包装，产品经理助手可修改），产品经理确认后发布。

---

## ⑧ 事件日志（`huayan.events`，WP-0 提供）

```python
EventKind = Literal["turn", "extraction", "ask_hint", "recommend", "escalate", "retrieve", "access_denied",
                    "decrypt_request", "decrypt_approve", "question_published", "question_resolved",
                    "requirement_confirmed", "requirement_translated", "knowledge_contributed", "trial",
                    "product_released", "sheet_updated", "access_frozen", "agent_action_proposed",
                    "agent_action_decided"]

class Event(BaseModel):
    id: str                                   # 日志分配
    ts: datetime
    kind: EventKind
    actor: str
    session_id: str | None = None
    payload: dict[str, Any] = {}

class EventLog:
    def __init__(self, path: Path | None = None): ...          # path 为 None 时只在内存
    def append(self, kind: EventKind, actor: str, payload: dict, *, session_id: str | None = None,
               ts: datetime | None = None) -> Event: ...        # ts 默认 get_clock().now()
    def query(self, kinds: list[EventKind] | None = None, since: datetime | None = None,
              until: datetime | None = None, actor: str | None = None) -> list[Event]: ...
```

**payload 字段（觉的定时状态只依赖这些字段）**

| kind | payload |
|---|---|
| `turn` | `turn_id, speaker, text` |
| `extraction` | `intent, phenomenon, filled: {slot: value}, extracted_by` |
| `ask_hint` | `slots: [slot], p: {slot: p}, model` |
| `recommend` | `product_id, version, p_choice, candidate_ids, phenomenon, known: {slot: value}, customer_id` |
| `escalate` | `question_id, phenomenon, known, customer_id, p_none` |
| `retrieve` | `query, intent, actor_level, hit_ku_ids, n_blocked, blocked_product_ids` |
| `access_denied` | `object_id, reason` |
| `decrypt_request` / `decrypt_approve` | `question_id, customer_id, product_id` |
| `question_published` / `question_resolved` | `question_id, family, object_id, action`（resolved 时） |
| `requirement_confirmed` | `requirement_id, phenomenon, known`（产品经理确认 L2） |
| `requirement_translated` | `requirement_id, ku_refs`（研发确认 L3） |
| `knowledge_contributed` | `ku_id, owner, requirement_id` |
| `trial` | `trial_id, product_id, conditions, result, cause` |
| `product_released` | `product_id, requirement_id, phenomenon, applicable` |
| `sheet_updated` | `product_id, slot, values` |
| `access_frozen` | `actor_id` |
| `agent_action_proposed` | `action_id, tool, principal, conversation_id` |
| `agent_action_decided` | `action_id, tool, principal, status`（approved / rejected） |

---

## ⑨ 模拟与评测数据（`huayan.sim` WP-B2，`huayan.eval` WP-E）

**以下文件只有模拟器和离线评估可以读。** 觉、Jev、Agent、应用门面都不得 import 读取它们的代码。

```python
class NeedCard(BaseModel):                    # data/sim/cards.jsonl
    id: str
    phenomenon: str
    slots: dict[str, str]                     # 全部槽位真值
    unknown_slots: list[str] = []             # 客户自己也说不清的槽位
    opening_slots: list[str] = []             # 首句主动透露的槽位
    customer_id: str
    chem_savvy: bool
    wants_mechanism: bool
    truth_product: str | None                 # domain.correct_product；None = 应升级

class Injection(BaseModel):                   # data/week/<week_id>/injections.jsonl
    id: str
    family: Literal["opportunity", "knowledge_conflict", "leak_risk"]
    object_id: str                            # 按 5.1 的格式
    hard_negative: bool
    onset: datetime
    earliest: datetime                        # 最早合理发现时刻
    latest: datetime                          # 最晚有效发现时刻

class WeekItem(BaseModel):                    # data/week/<week_id>/script.jsonl，驱动真实链路的剧本
    at: datetime
    kind: Literal["session", "trial", "query"]
    actor: str                                # 业务员 / 研发
    card_id: str | None = None                # session：模拟客户按这张卡回答
    text: str = ""                            # query：业务员的提问
    trial: Trial | None = None
```

```python
# huayan.sim（WP-B2）
class SimCustomer:
    def __init__(self, card: NeedCard, seeds: Seeds, rng: random.Random, gateway=None): ...
        # gateway 为 None：模板模式（用种子中的口语说法，零成本）；否则大模型扮演（caller "sim:customer"）
    def opening(self) -> str: ...             # 只说现象 + opening_slots
    def reply(self, sales_text: str) -> str: ...   # 被问到才透露；unknown_slots 答「不太清楚」

def make_cards(seeds: Seeds, n: int, rng) -> list[NeedCard]: ...
def make_week(seeds: Seeds, start: datetime, days: int, rng) -> tuple[list[WeekItem], list[NeedCard], list[Injection]]: ...
```

**Jue-K 训练数据** `data/jue_k/samples.csv`：每行 = 某时刻 × 某个「模板 × 对象」组合（只收前置条件通过的，与推理一致）；列 = `family, object_type, object_id, at, source_id, label, split` + 5.2 全部属性的并集（缺失留空）。来源两类（`JUE_K_TRAINING.md` v3）：
- `ask_slot` / `ask_back`：程序生成的对话轨迹（`source_id` = 卡 id），标签为事后有用性；
- `opportunity` / `knowledge_conflict` / `leak_risk`：多个随机种子的模拟业务周（`source_id` = 周 id），由剧本与需求卡直接合成事件、每 2 个业务小时构建一次定时状态；标签 = 该组合落在某条**非困难负样本**注入的 `[earliest, latest]` 内且 `object_id` 一致。

`split ∈ {train, val, test, heldout}`：轨迹按卡划分，另留 2 个现象为 heldout；业务周按周划分。

**Jue-K 产物** `models/jue_k/`：`model.pkl`（模型 + 按 family 的 isotonic 校准层）、`features.json`（特征名与编码）、`model_card.md`、`metrics.json`。特征构建 `huayan.jue.features.build(obj: JueObject, family: Family) -> dict[str, float]` 训练与推理共用。

**评测产物** `docs/reports/<name>/`：`metrics.json`、图（png）、`README.md`（一页说明，结果如实写）。

---

## ⑩ 模型网关与计量（复制自 JUE）

```python
class Tier(str, Enum):
    FAST = "fast"; STRONG = "strong"; BACKUP = "backup"; MOCK = "mock"

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[LLMToolCall] = []

class LLMRequest(BaseModel):
    tier: Tier
    caller: str                               # "<模块>:<用途>"，见下表
    messages: list[Message]
    tools: list[dict] | None = None
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout_s: float = 60

class LLMToolCall(BaseModel):  call_id: str; name: str; arguments: dict[str, Any]
class Usage(BaseModel):        input_tokens: int; output_tokens: int

class LLMResponse(BaseModel):
    content: str | None
    tool_calls: list[LLMToolCall] = []
    usage: Usage
    latency_ms: float
    model: str
    tier: Tier
    cost: float | None
    fallback_used: bool = False

class ModelGateway(Protocol):
    def complete(self, req: LLMRequest) -> LLMResponse: ...
    def structured(self, req: LLMRequest, schema: type[BaseModel]) -> tuple[BaseModel, LLMResponse]: ...
```

- `OpenAICompatGateway`（重试、降级、录制/回放缓存）与 `MockGateway`（`canned[caller]`）从 JUE 复制，只改 import。**录制/回放缓存就是「记录回放」演示模式的实现**：现场跑一次写缓存，回放时同样的输入直接命中。
- caller 一览：`agent:extract`、`agent:l1_answer`、`agent:sales`、`agent:pm`、`agent:rd`（三个角色助手的每一步）、`jev:match`、`jev:disclose`、`jev:grounding`（Jev 走大模型降级时透传）、`sim:customer`、`baseline:llm_poll`、`baseline:one_shot`。**不得出现 `jue:` 开头的大模型调用。**

```python
class MeterRecord(BaseModel):
    ts: datetime                              # 墙钟
    run_id: str
    caller: str
    kind: Literal["llm", "s1", "jue"]
    model: str | None = None
    impl: str | None = None
    degraded: bool = False
    n_questions: int | None = None
    n_objects: int | None = None              # jue：本次评估的对象数
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    cost: float | None = None
    ok: bool = True
    fallback_used: bool = False

class FileMeter:  # FileMeter(run_dir, run_id).record(*, caller, kind, **fields)；写 metering.jsonl
```

---

## ⑪ 配置 `config/app.yaml`

```yaml
seeds_dir: seeds
templates_dir: config/templates
run_root: runs
system1_impl: mock            # mock | llm_fallback | onejev
gateway_mock: true            # true 时用 MockGateway（离线），角色助手不运行（第 ⑭ 节）；现场演示设 false
extractor: rule               # rule | llm
realtime_model: jue_proto     # jue_proto | jue_k
scheduled_model: jue_proto    # jue_proto | jue_k（v4）
jue_k_dir: models/jue_k
llm_cache_dir: runs/llm_cache # 录制/回放缓存；为空则不缓存
replay: false                 # true = 记录回放模式，界面标明
thresholds: {ask: 0.5, max_asks: 2, match: 0.5, publish: 0.5}
windows: {theme_days: 7, knowledge_days: 7, actor_hours: 48}
routing: {escalate_need: pm, ask_back: sales, opportunity: pm, knowledge_conflict: rd, leak_risk: supervisor, decrypt_request: rd}
points: {cited: 1, contributed: 5, trial_pass: 5, product_released: 10}
```

`config/models.yaml`、`config/system1.yaml` 格式同 JUE。

---

## ⑫ 应用门面 `huayan.app.HuayanApp`（WP-A2 创建，A3、I 补全）

界面**只**通过它访问系统；按身份裁剪在门面内完成，界面不做权限判断。

```python
class SessionView(BaseModel):
    session_id: str
    viewer: str
    viewer_level: Level
    turns: list[Turn]
    slots: list[SlotFill]                     # 槽位 + 原话
    hints: list[AskHint]
    replies: list[AssistantReply]             # 已按查看者层级过滤
    card: RecommendationCard | None
    status: str
    escalation_question_id: str | None = None
    requirement: Requirement | None = None    # 只对 L2/L3 返回

class RunStatus(BaseModel):
    run_id: str
    replay: bool
    system1_impl: str                         # Jev 实际实现
    realtime_model: str                       # 觉实时模型
    extractor: str
    gateway_mock: bool
    simulated_data: bool = True
    seeds_placeholder: bool
    scheduled_model: str = "jue_proto"       # 觉定时模型（v4）

class HuayanApp:
    @classmethod
    def build(cls, config_path: str = "config/app.yaml", run_id: str | None = None) -> "HuayanApp": ...
    seeds: Seeds; kb: KnowledgeBase; bus: QuestionBus; events: EventLog
    audit: AuditLog; ledger: Ledger; actors: dict[str, Actor]

    # L1（WP-A2）
    def start_session(self, customer_id: str, sales_id: str) -> Session: ...
    def add_turn(self, session_id: str, speaker: Literal["customer", "sales"], text: str) -> Session: ...
        # v4：客户发言填上某个槽位、且该会话该槽位有 open 的 ask_back 问题时：resolve(answered)，取值写入需求单 known_slots，
        # 并 agents.notify 需求单当前的起草人（draft → drafted_by；pm_confirmed → chem_drafted_by）
    def recommend_now(self, session_id: str) -> Session: ...
    def view_session(self, session_id: str, viewer_id: str) -> SessionView: ...
    def sessions(self) -> list[Session]: ...
    def jue_trace(self, session_id: str) -> list[JueOutput]: ...         # 该会话每轮的实时觉输出，觉视图用
    def status(self) -> RunStatus: ...

    # L2 / L3：分层转译、权责与回流（WP-A3）。每个方法一个动作，角色助手的工具一对一调用它们（第 ⑭ 节）
    def draft_requirement(self, question_id: str, by: str) -> Requirement: ...
        # 产品经理；escalate_need 或 opportunity 问题 → L2 规则骨架，status=draft，drafted_by=by
    def edit_req_item(self, req_id: str, index: int, item: ReqItem, by: str) -> Requirement: ...
        # 产品经理改 product_lang（draft 状态），研发改 chem_lang（pm_confirmed 状态）；index = -1 表示追加。
        # 校验（大模型输出的真实边界）：quote_refs 必须是该需求单会话中的轮次，ku_refs 必须存在且 by 可读，否则 ValueError
    def remove_req_item(self, req_id: str, index: int, by: str) -> Requirement: ...  # 层的规则同上
    def set_direction(self, req_id: str, text: str, by: str) -> Requirement: ...      # 产品经理，draft 状态
    def confirm_requirement(self, req_id: str, by: str) -> Requirement: ...
        # → pm_confirmed；关联问题 resolve
    def translate_requirement(self, req_id: str, by: str) -> Requirement: ...
        # 研发；L3 规则骨架写入 chem_lang 与 hypotheses，chem_drafted_by=by
    def confirm_translation(self, req_id: str, by: str) -> Requirement: ...
        # → rd_confirmed；关联 product_id（种子中覆盖该现象与已知槽位的 status=project 产品）；给两层所引知识的归属人记 cited
    def contribute_translation(self, req_id: str, item_index: int, scene_phrase: str, chem_term: str,
                               by: str) -> KnowledgeUnit: ...
    def set_public_points(self, req_id: str, text: str, by: str) -> Requirement: ...   # 研发，rd_confirmed 之后
    def requirements(self, viewer_id: str) -> list[Requirement]: ...      # L1 调用抛 PermissionDenied
    def requirement_view(self, req_id: str, viewer_id: str) -> RequirementView: ...   # L1 抛 PermissionDenied
    def record_trial(self, trial: Trial) -> Trial: ...
    def package_sheet(self, req_id: str, by: str) -> SheetDraft: ...
        # 产品经理；translate.package_sheet(req)，结果写入 req.sheet
    def save_sheet(self, req_id: str, sheet: SheetDraft, by: str) -> Requirement: ...  # 产品经理修改说明书草稿
    def release_product(self, req_id: str, by: str) -> Product: ...
        # 以 req.product_id 的种子产品为底，sheet / usage 用 req.sheet，调用 flow.release_product
    def contributions(self, viewer_id: str) -> list[ContributionStat]: ...
        # 贡献看板；L3 知识的标题对非 L3 查看者显示为「研发 X 的转化知识」
    def request_decrypt(self, session_id: str, by: str) -> Question: ...
    def decide_decrypt(self, question_id: str, by: str, approve: bool) -> Question: ...

    # 角色助手（第 ⑭ 节；WP-L 实现 AgentHub，WP-I 在 build 中挂上）
    agents: AgentHub

    # 觉定时发现与处置（WP-I）
    def scan(self, at: datetime | None = None) -> list[Question]: ...
    def resolve(self, question_id: str, action: str, by: str, note: str = "") -> Question: ...
        # approve_project → 起草需求单；update_sheet → kb.update_applicable；freeze_access → permission.freeze
    def tick(self) -> list[Question]: ...
        # 上次 tick 后出现过升级、或距上次扫描 ≥ 30 业务分钟则 scan；
        # v4：每次对 draft / pm_confirmed 的需求单 requirement_state → 实时模型 propose → publish（ask_back）；
        # 然后 agents.dispatch()；返回本次新发现的问题。门面每次调用觉都追加一条 JueRecord
        # 界面在每次 chat / approve 之后、脚本在每一步之后调用
```

---

## ⑬ 运行产物 `runs/<run_id>/`

`events.jsonl`、`audit.jsonl`、`ledger.jsonl`、`metering.jsonl`、`questions.jsonl`（每次变化追加一行快照）、`sessions/<session_id>.json`（会话结束或每轮后覆盖写）、`conversations/<conv_id>.json`（助手对话，每轮覆盖写）、`pending.jsonl`、`agent_trace.jsonl`、`jue_samples.jsonl`（v4，`JueRecord`）。`runs/` 不入库，演示用的记录回放目录除外（`runs/demo_record/`）。

---

## ⑭ 角色助手（`huayan.agent`，WP-L）

每个 L1 / L2 / L3 的人配一个**角色助手**：业务员助手、产品经理助手、研发助手。助手 = **Agent Loop + 原子工具**：人用自然语言说要做什么，或者问题 / 需求单被派到他名下，助手理解意图、自己调用工具处理。

- 助手**没有自己的身份和权限**，借用委托人的权限：工具在代码里绑定委托人，模型看不到也改不了；
- `read` / `draft` 工具自动执行，草稿未生效；
- `effect` 工具**只能提议**：Loop 创建 `PendingAction`，对话里出现确认卡，**委托人点确认后才执行**。确认卡是委托人的签字，不是调度入口；助手没有、也不能有「确认」工具；
- 觉不是助手，不调用大模型；它发现的问题经总线派给对应人的助手。

```python
ToolKind = Literal["read", "draft", "effect"]

class ToolSpec(BaseModel):
    name: str                                 # 动词_名词，如 search_knowledge
    kind: ToolKind
    roles: list[Role]                         # 哪些角色的助手拥有它
    description: str                          # 给模型看的一句话
    params: type[BaseModel]                   # 参数模型：扁平、字段少；不得含委托人 / 身份字段（运行时绑定）
    confirm_text: str = ""                    # effect 工具确认卡模板，用 args 格式化，如「确认需求单 {req_id} 并交研发」

class ToolResult(BaseModel):
    ok: bool = True
    data: Any = None                          # 精简 JSON：只含委托人权限内的内容，不含当前时间
    error: str | None = None                  # 参数错误 / 权限拒绝 / 校验失败；原样回给模型
    pending_action_id: str | None = None      # effect 工具：已挂起，等待委托人确认

class PendingAction(BaseModel):
    id: str                                   # "act:<n>"
    conversation_id: str
    principal: str                            # 委托人 actor id；只有他能确认
    tool: str
    args: dict[str, Any]
    summary: str                              # 确认卡上的人话：要做什么、影响谁
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime
    decided_at: datetime | None = None
    result: ToolResult | None = None          # 确认后执行的结果

class AgentStep(BaseModel):                   # 执行轨迹的一步，写 runs/<run_id>/agent_trace.jsonl
    conversation_id: str
    step: int
    principal: str
    tool: str | None                          # None = 本轮最终的文字回复
    args: dict[str, Any] = {}
    result_summary: str = ""
    blocked: list[str] = []                   # 越权命中，只有「研发 R01 · L3」这样的提示
    pending_action_id: str | None = None
    at: datetime

class AgentMessage(BaseModel):
    role: Literal["principal", "assistant", "system"]   # system = 派单通知、确认结果
    text: str
    at: datetime
    pending_action_ids: list[str] = []

class Conversation(BaseModel):
    id: str                                   # "conv:<actor_id>:<session_id 或 inbox>"
    principal: str
    role: Role                                # sales / pm / rd
    session_id: str | None = None             # 业务员助手绑定的客户会话
    messages: list[AgentMessage] = []
```

```python
# huayan.agent（WP-L）
class AgentHub:                               # HuayanApp.agents
    def __init__(self, app: "HuayanApp"): ...
    def chat(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation: ...
        # 委托人说一句话 → 跑一轮 Loop → 返回整段对话；业务员必须带 session_id
    def notify(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation: ...
        # 派单：写一条 system 消息到该人的 inbox 对话（带 session_id 时写到该会话的对话）并跑一轮 Loop（助手主动处理，如起草）
    def dispatch(self) -> list[Conversation]: ...
        # 把总线上新出现、尚未派过的 open 问题（owner_role 为 pm / rd / sales）notify 给负责人（owner_id，空则该角色 id 最小的人）；
        # sales 的 ask_back 按 refs["session_id"] 派到该会话的对话
    def approve(self, action_id: str, by: str) -> PendingAction: ...
        # by 必须是 principal，否则 PermissionDenied；执行该工具，结果写回对话，写 agent_action_decided；再按「确认后派单」notify 下一棒
    def reject(self, action_id: str, by: str, note: str = "") -> PendingAction: ...
    def pending(self, actor_id: str) -> list[PendingAction]: ...
    def conversations(self, actor_id: str) -> list[Conversation]: ...
    def trace(self, conversation_id: str) -> list[AgentStep]: ...
```

**Loop**（`huayan/agent/loop.py`，复用 JUE `src/jue/agent/__init__.py` 并简化，去掉派生与钩子）：
- 每轮：系统提示词（`prompts/assistant_<role>.md` + 委托人身份 + 当前待确认动作）+ 对话历史 → `gateway.complete(tools=该角色的工具, caller="agent:<role>", tier=fast, temperature=0)` → 执行工具调用，结果追加为 tool 消息 → 直到没有工具调用或满 8 步 → 最后的文字作为助手回复；
- 本轮的工具消息只在本轮保留，跨轮只保留文字消息（含确认结果的 system 消息）；
- 每一步写一条 `AgentStep`；
- `gateway_mock` 为 true 时不跑 Loop：`chat` / `notify` 只追加一条「助手需要大模型（当前离线）」的 system 消息。离线演示走 `scripts/demo_mainline.py`（直接调用门面）。

**原子工具**（`huayan/agent/tools.py`；规则写死，评审时逐条检查）：
1. 一个工具 = 一个动作 = 调用**一个**门面 / 知识库 / 转译函数；组装参数时最多先读一次当前状态。业务规则、权限、校验都在门面和知识库里，工具里不写业务分支；
2. 签名 `fn(ctx: ToolContext, args: Params) -> ToolResult`；`ToolContext` 由 Loop 绑定（`app`、`principal: Actor`、`conversation_id`、`session_id`）；
3. 参数模型扁平、字段 ≤ 5、不含身份字段；不允许用 `mode` / `action` 之类的参数让一个工具干几件事；
4. 返回精简 JSON（id、标题、短文本），不返回整个对象，不含当前时间（记录回放要求同输入同输出）；
5. 门面抛出的 `PermissionDenied` / `ValueError` 转为 `ToolResult(ok=False, error=...)` 回给模型，不吞掉、不重试；
6. `effect` 工具在 Loop 中只创建 `PendingAction`、写 `agent_action_proposed`、返回 `pending_action_id`；真正执行在 `approve`；
7. 注册表是一个 `dict[str, tuple[ToolSpec, Callable]]`，按角色取子集；新增能力 = 先在门面加一个方法，再加一个薄工具。

**工具清单**（第一版就这些，不多加）：

| 工具 | 类别 | 角色 | 调用 |
|---|---|---|---|
| `search_knowledge(query, kind?)` | read | sales pm rd | `kb.search` ＋ `kb.search_blocked`（越权只给归属人与层级） |
| `get_knowledge(ku_id)` | read | sales pm rd | `kb.get` |
| `record_customer_turn(text)` | draft | sales | `app.add_turn(session, "customer", text)`；返回槽位、觉的追问提示、推荐 / 升级状态 |
| `record_sales_turn(text)` | draft | sales | `app.add_turn(session, "sales", text)` |
| `get_need_card()` | read | sales | `app.view_session(session, principal)` |
| `recommend_now()` | draft | sales | `app.recommend_now(session)` |
| `request_decrypt()` | effect | sales | `app.request_decrypt(session, principal)` |
| `list_my_questions()` | read | sales pm rd | `app.bus.list(owner_role=角色)`，只留 owner_id 为空或为本人的 |
| `get_session(session_id)` | read | pm rd | `app.view_session(session_id, principal)` |
| `match_translations(text)` | read | pm rd | `translate.match_translations` |
| `find_products(phenomenon, slots)` | read | pm rd | `domain.match_candidates(phenomenon, slots, kb.products())` |
| `draft_product_need(question_id)` | draft | pm | `app.draft_requirement` |
| `get_requirement(req_id)` | read | pm rd | `app.requirement_view` |
| `edit_item(req_id, index, text, quote_refs, ku_refs)` | draft | pm rd | `app.edit_req_item` |
| `remove_item(req_id, index)` | draft | pm rd | `app.remove_req_item` |
| `set_direction(req_id, text)` | draft | pm | `app.set_direction` |
| `confirm_requirement(req_id)` | effect | pm | `app.confirm_requirement` |
| `dismiss_question(question_id, note)` | effect | pm | `app.resolve(question_id, "dismiss", ...)` |
| `package_sheet(req_id)` | draft | pm | `app.package_sheet` |
| `edit_sheet(req_id, sheet, usage)` | draft | pm | `app.save_sheet` |
| `release_product(req_id)` | effect | pm | `app.release_product` |
| `draft_chem_need(req_id)` | draft | rd | `app.translate_requirement` |
| `confirm_translation(req_id)` | effect | rd | `app.confirm_translation` |
| `contribute_translation(req_id, index, scene_phrase, chem_term)` | effect | rd | `app.contribute_translation` |
| `set_public_points(req_id, text)` | effect | rd | `app.set_public_points` |
| `record_trial(req_id, result, cause, note)` | effect | rd | `app.record_trial`（`product_id`、`conditions` 取自需求单） |
| `decide_decrypt(question_id, approve)` | effect | rd | `app.decide_decrypt` |
| `my_contributions()` | read | pm rd | `app.contributions(principal)` |

**确认后派单**（`approve` 执行成功后，写死在 `AgentHub` 里）：

| 已确认的工具 | notify 谁 |
|---|---|
| `confirm_requirement` | 该现象 L3 转化对照条数最多的研发（并列取 id 最小） |
| `set_public_points` | 需求单的 `pm_confirmed_by` |
| `request_decrypt` | 解密问题的 `owner_id`（产品归属研发） |

**不变量（有测试，`tests/test_wp_l.py`，不调用模型）**：产品经理助手的 `search_knowledge` / `get_knowledge` 拿不到 L3 原文（只有 `BlockedHint`）；`effect` 工具在 `approve` 之前不改变任何状态；非委托人 `approve` 抛 `PermissionDenied`。
