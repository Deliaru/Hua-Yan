# CONTRACTS.md

> 跨模块的数据格式与接口契约。**冻结后只能由人修改**。代码实现在 `src/huayan/contracts/`，必须与本文件一致。
> 下列代码是规格（Python / pydantic v2 风格），字段名、类型、枚举值必须一致；函数签名必须一致，内部实现自由。
> 版本：v6｜2026-10-12
>
> **v6 追加（让需求直达正确的责任人；依据 `workpackages/REPLAN-v6.md` 第 2 节，人已批准）**：新增 L0（客户自助）：`Level` 增加 0，客户 level 0，`sheet`、`usage` 改为 L0，新增知识种类 `public_case`（L0，脱敏对外案例）与 `report`（L1，业务员可看的内部评价）；客户自助会话 `sales_id` 可为 `None`，`Session.origin` 记录来源（分配业务员后不变）；模板增加 `auto_action`，`signer_role` 为空且带 `auto_action` 的问题由觉自动执行（见 6.1 节），`Resolution.action` 增加 `auto`；事件增加 `auto_executed`、`sales_assigned`、`project_declined`、`l2_contributed`、`scope_extended`；解析表中 `pm` 作主人为 `pm:agent`、作签字人为真人产品经理；`opportunity` 签字人改为产品经理。
>
> **v5.3 追加（现成产品建议由研发审定；`WP-0v5.md` C15）**：`customer_note` 是唯一一段由 L2 写成、流向 L1 的文本，改为升级给 L3 研发审定：`reuse_product` 的签字人由业务员改为 `assigned_rd`；新增草稿方法 `update_reuse_note` 与工具 `edit_reuse_note`；`adopt_reuse` / `decline_reuse` 由研发签字；业务员在审定前只看到状态与产品名，审定后收到说明并自行转述给客户。
>
> **v5.2 追加（同类需求合并与 Agent 协作焦点，REPLAN D19、D21；`WP-0v5.md` C14）**：每次升级仍各建一张单；觉的机会汇聚到点后派给产品经理 Agent 判断几张单是否同一件事并起草合并，研发签字合并。`Requirement` 增加 `merged` 状态与 `merged_into`、`merge_from`、`merge_note`；事件 `merge_proposed`、`requirements_merged`；门面 `save_merge_proposal`、`merge_requirements`；工具 `propose_merge`；`opportunity` 的 `refs` 增加 `requirement_ids`、`assigned_rd`，签字人为研发；`AgentHub.chat` 增加 `focus`。
>
> **v5.1 追加（现成产品复用，REPLAN D17）**：升级建单后觉先提出 `reuse_product`，产品经理 Agent 用 L2 知识查现成产品，业务员签字采用后需求单 `status="reused"`、研发不介入（v5.3 改为研发审定，见上）。新增 `ReuseProposal` 与 `Requirement.reuse`；requirement 属性 `reuse_checked`、`reuse_pending`、`reuse_declined`；事件 `reuse_proposed`、`reuse_adopted`、`reuse_declined`；门面 `save_reuse_proposal`、`adopt_reuse`、`decline_reuse`；工具 `propose_reuse`；业务员视图 `ReuseView`（`SessionView.reuse`），觉视图的业务员裁剪含 `reuse_product`。
>
> **v5 变更（觉是全过程的决策点发现器；产品经理由 Agent 担任；工作面 + Agent 协作，按钮即签字；依据 `workpackages/REPLAN-v5.md` 与 `workpackages/WP-0v5.md`）**：觉的对象增加 `session`、`requirement`，`Family` / `QFamily` 改为由模板目录校验的字符串，模板增加 `kind`、`signer_role`，`ScoredDecision` 逐条标 `scored_by`；问题增加签字人、准备完成时间、模板 id，处置动作改为 sign / accept / return 等，总线增加 `set_prepared`；需求单可以是空单，`pm_confirmed` 改为 `rd_accepted`（立项 ≡ 研发接单），增加指定研发、封存项、两栏与提炼草稿、退回理由，`ReqItem.edited_by`，试样增加客户评价，新增 `LeakHit` 与 `leak_hits`；会话增加回复与升级说明草稿；事件增加 `match` 等 8 种、删除 `requirement_confirmed`；Jev 不再升级；新增身份 `pm:agent`，积分只给人；`DecryptGrant.text`；删除路由配置；门面删除 `confirm_requirement` 与内部流程推进，新增升级、接单 / 退回、客户评价、草稿、`mark_prepared`、`questions`、`jue_timeline` 等原子方法与写后评估；`AgentMessage.target`，`pm:agent` 无生效工具，派单只派总线上的问题，删除「确认后派单」。
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
| 人 | `<role>:<id>` | `sales:S01`、`customer:C01`、`pm:P01`、`rd:R01`、`supervisor:M01`；产品经理 Agent 为 `pm:agent`（v5） |
| 产品 | 虚构型号 | `HY-LV205` |
| 现象、槽位 | 小写英文 | `color_unlevel`、`fiber` |
| 知识单元 | `ku:<kind>:<ref>` | `ku:mechanism:HY-LV205` |
| 会话 / 轮次 | `sess:<n>` / `turn:<sess>:<n>` | `sess:3`、`turn:sess:3:2` |
| 问题 / 需求 / 试样 / 事件 | `q:<n>` / `req:<n>` / `trial:<n>` / `ev:<n>` | `q:12` |
| 觉的对象 | 见 5.1 | `slot:sess:3/fiber` |

- **角色与层级**（固定）

```python
Role = Literal["customer", "sales", "pm", "rd", "supervisor"]
Level = Literal[0, 1, 2, 3]                   # v6：0 = 客户自助可见
ROLE_LEVEL: dict[Role, Level] = {"customer": 0, "sales": 1, "pm": 2, "rd": 3, "supervisor": 2}

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

# seeds/actors.yaml：list[Actor]，至少包含 2 个业务员、4 个客户、1 个产品经理（L2 历史知识归属人，v5 起无工作台）、
# pm:agent（产品经理 Agent，role = pm）、2 个研发、1 个主管
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
KUKind = Literal["sheet", "usage", "public_case", "report", "case", "translation", "requirement", "mechanism", "formula", "trial"]
KIND_LEVEL: dict[KUKind, Level] = {"sheet": 0, "usage": 0, "public_case": 0, "report": 1, "case": 2, "requirement": 2,
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
        # 被冻结的人（2.3）检索 L1 以外的意图时直接返回空。（v8 Q9.8 改，见第 ⑰ 节）
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
    text: str = ""                            # v5（第二档）：研发审定的、给这一位客户的结论层面说明；不含转译过程与配方。
                                              # 经业务员转交，业务员可见；研发的转译过程始终只在 L3

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
def render(product_id: str, version: Version, viewer: Actor, kb: KnowledgeBase, *,
           session_id: str, customer_id: str, grants: list[DecryptGrant]) -> RecommendationCard: ...
    # 2026-10-11 经用户授权补齐上下文：门面校验会话访问权并传入真实客户与授权。
    # 渲染器再次验证 cap，授权审批人必须是产品归属研发；卡片绑定 session_id。
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
- **积分只给人**（v5）：`pm:agent` 不进账本；
- `cited`：知识单元被一次推荐卡片引用给其归属人记分；需求单所引知识在**研发接单时记 L2、确认转译时记 L3**（`ReqItem.ku_refs`）；同一知识在同一会话或需求单中只记一次；
- `contributed`：研发把自己修改后的转译沉淀为新的转化知识；
- `trial_pass`：试样通过；`product_released`：新品发布（给产品归属研发）；`bounty`：处理带悬赏的问题，记给签字人。

---

## ③ 会话与需求

```python
Intent = Literal["need", "product_question", "cause_question", "mechanism_request", "commercial", "smalltalk"]   # ⑰′

class Turn(BaseModel):
    id: str                                   # "turn:sess:3:2"
    session_id: str
    n: int                                    # 从 1 开始
    speaker: Literal["customer", "sales", "assistant"]   # assistant：客户自助时化言发出的追问（Q8 人批准）
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
    sales_id: str | None                      # v6：客户自助会话在交业务员前为 None
    phenomenon: str | None = None
    phenomenon_quote: str = ""
    slots: dict[str, SlotFill] = {}
    asked: dict[str, int] = {}                # 槽位 → 已追问次数（业务员或化言）
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
    product_refs: list[str] = []              # ⑰′ 这句话指到的产品编号（指代由抽取按上下文解析）

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
    escalated_question_id: str | None = None  # v5：业务员签字升级时关闭的 escalate_need 问题
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
    sales_id: str | None                      # v6：客户自助会话在交业务员前为 None
    origin: Literal["sales", "customer"] = "sales"   # v6：会话来源；后续分配业务员不改变来源
    started_at: datetime
    turns: list[Turn] = []
    need: NeedState
    hints: list[AskHint] = []                 # 当前有效的追问提示
    replies: list[AssistantReply] = []
    recommendation: Recommendation | None = None
    status: Literal["open", "recommended", "escalated", "closed"] = "open"
    reply_draft: str = ""                     # v5：Agent 起草的回复，预填进「发给客户」输入框；发出后清空
    escalate_note: str = ""                   # v5：Agent 起草的升级说明；业务员签字时写入需求单
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
  - `jev:disclose`：`profile.chem_savvy` 且选项含 `full_mechanism`（即已有解密授权）时 0.7 给它；否则 0.7 给 `product_usage`；其余平分；
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

### 4.3 推荐与升级规则（v5：Jev 只给匹配概率，不再升级）

每轮发言后：抽取 → 觉追问（5.4）→ 若现象已知且**没有追问提示**，或业务员点了「直接推荐」，则匹配并**写 `match` 事件**：
- 有把握且 `choice != "none"` → 推荐 `choice`，`disclose` 选版本，对 L1 渲染，写 `recommend` 事件、披露审计、引用积分；
- 否则不推荐、不升级。是否转产品经理 Agent 由觉的 `escalate_need`（session 对象，信号来自 `match`）在写后评估中提出，业务员签字后门面 `escalate()` 建单（第 ⑫ 节）。

---

## ⑤ 觉（`huayan.jue`，WP-B1 / WP-B3）

### 5.1 觉的输入：对象与状态

```python
ObjectType = Literal["slot", "theme", "knowledge", "actor", "session", "requirement"]

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
| `session`（v5） | `session:<session_id>` | 实时（写后） | `session_state(sess, events, at)` |
| `requirement`（v5） | `requirement:<req_id>` | 实时（写后）；停滞为定时（第二档） | `requirement_state(...)`：在 slot 对象之外再产出一个 requirement 对象 |

构建函数都在 `huayan.jue.state`（WP-B1 写前两个，WP-B3 增加 `requirement_state`，WP-J 增加 `session_state`），**只读 NeedState / 需求单 / 事件日志 / 种子 / 知识库**，不读需求卡、注入清单。

```python
def requirement_state(req: Requirement, need: NeedState, seeds: Seeds, kb: KnowledgeBase, at: datetime,
                      events: EventLog) -> JueState: ...
    # v5：status 为 released / rejected 之外的需求单都构建；总是产出一个 requirement 对象；
    # 只在 status 为 draft（layer=2）或 rd_accepted（layer=3）时为该现象每个槽位再生成一个 slot 对象；
    # need = 需求单首个会话的 NeedState，已知槽位以 req.known_slots 为准；mode="realtime"
def session_state(sess: Session, events: EventLog, at: datetime) -> JueState: ...
    # v5：只读会话与该会话的事件；产出一个 session 对象；mode="realtime"
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
| `p_fix` | float | v5.4（人已批准）：信息价值。按种子中该现象的槽位先验（没有则均匀），问到该槽位真值后推荐由错变对的概率；只在 layer 1 计算，已填或现象未知为 0。只枚举解决该现象的产品适用范围限定过的未知槽位，用 `correct_product` 判断 |

**theme（定时，机会汇聚）**：`phenomenon` str、`n_escalations` int（窗口内升级次数）、`n_customers` int（涉及客户数）、`n_matched` int（同主题被成功推荐次数）、`days_active` int（出现过的天数）、`open_project` bool（已有对应需求单在途）、`mean_p_none` float。

**knowledge（定时，知识冲突）**：`product_id` str、`slot` str、`value` str、`claimed` bool（说明书声称适用）、`n_trials` int、`n_fail` int、`n_fail_product` int（失败原因为产品本身）、`fail_ratio` float、`n_recommended` int。

**actor（定时，泄露风险）**（v8 Q9.8 改，以第 ⑰ 节为准）：`role` str、`n_queries` int、`n_mech_requests` int、`n_blocked` int（被拦截的高层级命中数）、`blocked_top_share` float（被拦截命中中最集中的产品占比）、`n_distinct_products` int、`frozen` bool。

**session（v5，实时：推荐还是升级 `escalate_need`、解密时机）**

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

**requirement（v5，实时：接单、失真、确认、沉淀、客户评价、封存、泄密、发布；停滞为定时）**

| 属性 | 类型 | 含义 |
|---|---|---|
| `status` | str | 需求单状态 |
| `layer` | int | draft = 2，rd_accepted = 3，其余 0 |
| `n_product_items` | int | L2 条目数 |
| `n_chem_items` | int | L3 条目数 |
| `n_returns` | int | 被研发退回次数 |
| `n_open_ask_back` | int | 本单未答复的回问数（由 `question_published / resolved` 事件算） |
| `n_conflicting_refs` | int | v8 收口：本层条目中，所引案例（`ku:case:*`）的槽位取值与本单已知条件冲突的条数（替代 `n_unmapped_constraints`） |
| `n_unquoted_items` | int | 本层没有 `quote_refs` 的条目数 |
| `n_edited_uncovered` | int | L3 条目中 `edited_by` 为研发、且未被已有 L3 转化对照的 `chem_term` 覆盖的条数 |
| `n_contributed` | int | 本单已沉淀的转化知识数 |
| `n_trials` | int | 试样次数 |
| `trial_passed` | bool | 最近一次试样通过 |
| `market_eval` | str | `"none"` / `"pass"` / `"fail"`（最近一次通过的试样上的客户评价） |
| `points_set` | bool | 研发已签字「封存 / 放出」 |
| `n_sealed` | int | 封存项数 |
| `sheet_ready` | bool | 已有说明书草稿 |
| `n_leak_hits` | int | 说明书与用法上的 `leak_hits` 命中句数（第 7.1 节） |
| `released` | bool | 已发布 |
| `hours_in_status` | float | 停留在当前状态的业务小时（第二档：停滞） |
| `reuse_checked` | bool | v5.1：产品经理 Agent 已查过现成产品（`reuse` 不为空） |
| `reuse_pending` | bool | v5.1：有现成产品建议，尚未审定（v5.3：研发） |
| `reuse_declined` | bool | v5.1：不采用（v5.3：研发） |

对象属性只放计数与状态，不放文本；文本类信号在构建时用规则匹配算成计数（铁律 3）。

定时窗口：机会汇聚、知识冲突 7 天，泄露风险 48 小时（`config/app.yaml` 可改）。v5：`theme.n_escalations` 统计的是 `escalate` 事件，即业务员签字后的升级；v5.2：所在需求单后来被 `reuse_adopted` 的升级不计入，`requirements_merged` 与立项一样计为该主题的「已处理」时刻。

Jue-K 的特征来自以上全部对象类型的属性（`features.build(obj, family)`，缺失的属性记 0）。

### 5.3 模板 `config/templates/*.yaml`（一个模板一个文件）

```python
Family = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]
# v5：决策 id。合法取值 = 已加载模板目录中的 family 集合；huayan.jue 加载模板时校验每个 family 只有一个模板、object_type 合法。
# 新增决策点 = 人批准后新增模板文件，不改契约（AGENTS.md 铁律 1）

class JueTemplate(BaseModel):
    id: str
    family: Family
    kind: Literal["advance", "anomaly"]       # v5：推进类 / 异常类
    object_type: ObjectType
    decision_label: str                       # 「是否追问该信息」「是否立项」…
    precondition: str | None = None           # 布尔表达式，只能引用 attrs.x
    rule_score: str | None = None             # 数值表达式，规则模式下的 p_need（结果截断到 [0,1]）；为空时 1.0
    worth_prompt: str                         # Jev 是非题，含 {object}
    title: str                                # 发布后的问题标题，可含 {object} 与 {attrs.x}
    owner_role: Role                          # v5 改义：主人（谁准备）。ask_slot、ask_back 为 sales；没有准备环节的（leak_risk）与签字人相同
    signer_role: Role | None = None           # v5：签字人角色；None = 提示类（ask_slot、ask_back），不进待签
    bounty_points: int = 0
    urgency: str | None = None                # 数值表达式，截断到 [0,1]；为空时 1.0。紧急度是规则，不学习
    auto_action: str | None = None            # v6：signer_role 为 None 时，问题发布后由觉自动执行（见 6.1 节）
```

模板即**决策目录**，见 `config/templates/`，每个 family 一个文件。v4 已有：`ask_slot`（前置条件含 `attrs.layer == 1`）、`ask_back`（含 `attrs.layer >= 2`、未填、未答不清楚、`attrs.trans_splits >= 2`）、`opportunity`、`knowledge_conflict`、`leak_risk`；v5 新增 `escalate_need`、`reuse_product`（v5.1，主人 pm、签字人 rd（v5.3，原为 sales）；`accept_requirement` 的前置条件含 `attrs.reuse_checked and not attrs.reuse_pending`）、`accept_requirement`、`distortion`、`confirm_translation`、`contribution`、`market_eval`、`seal_points`、`seal_leak`、`release`（前置条件、主人、签字人见 `workpackages/REPLAN-v5.md` 第 4.3 节，均先用规则打分）。v5.2：`opportunity` 的 `decision_label` 为「同类需求是否合并立项」，签字人 rd，`refs` 含 `requirement_ids`（逗号分隔）与 `assigned_rd`。

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
    scored_by: Literal["onejev", "rule", "jue_k"] | None = None   # v5：逐条打分来源；None 时取 JueOutput.scored_by

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
- **`JueK(model_dir, templates_dir, mode)`**（WP-B3）：**一个模型覆盖有训练样本的决策**（`ask_slot`、`ask_back`、`opportunity`、`knowledge_conflict`、`leak_risk`）；v5 起没有训练样本的决策在同一次 `propose` 中由模板 `rule_score` 打分，逐条标 `ScoredDecision.scored_by="rule"`。与原型用同一套模板枚举「模板 × 对象」、同一套前置条件（不通过的 `p_need=None`）；通过者由同一个梯度提升模型一次批量推理，按 `family` 分别校准，输出校准概率；`scored_by="jue_k"`。实时（`ask_slot`、`ask_back`）与定时（三类）都可以把原型换成它，运行链路、发布层、界面不改。
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
    # v5：所有非 ask_slot 的组合 p_need ≥ threshold 即生成问题（不再区分实时 / 定时）；证据取对象属性中的关键数字与相关事件 id；
    # owner_role / signer_role 取自模板，owner_id / signer_id 按下表解析；template_id、urgency 取自 ScoredDecision；
    # ask_back：refs={session_id, requirement_id, slot}；requirement / session 对象的问题 refs 带 requirement_id / session_id
```

| 角色 | 对象 | 解析为 |
|---|---|---|
| sales | session / requirement / slot | 会话的业务员（需求单取首个会话）；v8 收口：自助单没有会话业务员时，requirement 上的问题（客户评价）取客户的归属业务员（`customer_sales`），session / slot 仍为空 |
| pm（主人） | 任意 | `pm:agent`（v8 Q9.3：被研发退回的单也由 `pm:agent` 按理由重写；v6 的「退回后归真人产品经理纠偏」取消） |
| pm（签字人，v6） | 任意 | 真人产品经理（v8：门面按产品线传入分管的产品经理，没有时取种子中 id 最小的非 Agent 产品经理）；只签产品生命周期类决策（适用范围扩展、机会汇聚） |
| rd | requirement / slot（layer 2/3） | `req.assigned_rd` |
| rd | knowledge | 产品归属研发 |
| rd | theme（v5.2，机会汇聚） | `refs.assigned_rd`（候选需求单中最早一张的研发） |
| pm（仅 `distortion`，layer 3） | requirement | `req.assigned_rd`（第 3 层的失真由研发的 Agent 准备） |
| supervisor | 任意 | id 最小的主管 |

```python

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
QFamily = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$")]   # v5：同 Family，由模板目录校验

class Evidence(BaseModel):
    summary: str
    event_ids: list[str] = []
    quote: str = ""

class Resolution(BaseModel):
    action: Literal["sign", "accept", "return", "answered", "update_sheet", "freeze_access",
                    "approve_decrypt", "reject_decrypt", "dismiss", "auto"]
    # v6：auto = 觉按模板 auto_action 自动执行，by = "jue:auto"；
    # v5：sign = 签字人在工作面签字（升级、确认转译、沉淀、客户评价、封存 / 放出、发布；v5.2：机会汇聚的合并）；
    # accept / return = 研发接单 / 退回；
    # answered = 回问已由客户回答，或觉再看时问题的前置条件不再成立（v8 收口：所有问题，by = "jue"）；删除 draft_requirement、approve_project（立项 ≡ 接单）
    by: str
    note: str = ""

class Question(BaseModel):
    id: str
    family: QFamily
    title: str
    object_id: str                            # sess:3 / theme:... / knowledge:... / actor:...
    owner_role: Role                          # v5：主人（谁准备）
    owner_id: str | None = None
    signer_role: Role | None = None           # v5：None = 提示类
    signer_id: str | None = None              # v5
    prepared_at: datetime | None = None       # v5：None = 准备中；有值 = 待签
    template_id: str | None = None            # v5：被忽略率按模板统计
    status: Literal["open", "resolved", "dismissed"] = "open"
    p_need: float | None = None
    urgency: float | None = None              # v4：觉发现的问题来自 ScoredDecision；其他来源为 None
    scored_by: str                            # onejev / llm_fallback / mock / rule / jue_k / human
    discoverer: Literal["jue_proto", "jue_k", "rule_alert", "llm_poll", "human"]   # v5：删除 jev
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
    def set_prepared(self, qid: str, at: datetime | None) -> Question: ...
        # v5：at 有值 → 进入待签，写 question_prepared 事件；None → 退回准备中（需求单已知条件变化时由门面调用）
```

### 6.1 自动执行（v6）

`signer_role: null` 且带 `auto_action` 的模板是**低风险推进**：问题发布后，hub 在派单时调用门面内部入口 `HuayanApp.auto_execute(question_id)`。该入口只按查表 `{escalate, assign_sales}` 调用对应方法的内部实现（执行者 `jue:auto`），**不经 HTTP 暴露**，外部请求无法以 `jue:auto` 身份调用任何方法；执行成功后写 `auto_executed` 事件并以 `action="auto"` 结案，防止重复触发。高影响动作（立项、技术确认、封存、发布、解密）不得配 `auto_action`。

v5：删除路由配置。发布方按模板的 `owner_role` / `signer_role` 与第 5.4 节的解析表填写主人与签字人；`decrypt_request` 由门面发布，主人与签字人都是产品归属研发。界面据 `prepared_at` 区分「准备中 / 待签」。

---

## ⑦ 升级、分层转译与回流（`huayan.escalation`）

**转译是化言的主线。** 一个 L1 解决不了的需求，按层逐步转译，每一层只用自己能看的知识，每一句都能回查客户原话、标明依据了谁的知识：

```
L1 场景需求卡（NeedState：槽位＋原话）
  → 业务员签字升级：门面建空需求单（指定研发 assigned_rd）
  → 现成产品复用（v5.1）：产品经理 Agent 用 L2 知识查现成产品 → 研发审定（v5.3）采用则推荐卡与审定后的说明给业务员、由业务员转述给客户，需求单关闭（reused）；否则继续
  → L2 产品需求语言（规则骨架 → 产品经理 Agent 用 L2 知识检索、逐条修改）→ 研发接单（= 立项）或写理由退回
  → L3 化学语言需求单（规则骨架 → 研发 Agent 用 L3 转化对照与机理起草 → 研发修改、确认）
  → 沉淀（研发 Agent 提炼 → 研发签字）
  → 试样（模拟 ELN）→ 客户评价（业务员签字）
  → 封存 / 放出（研发 Agent 起草两栏 → 研发签字）：对外要点是 L3 内容流向下层的唯一出口，封存项只对 L3 可见
  → 反向包装：L1 说明书（产品经理 Agent，只用产品需求＋对外要点）→ 研发审定发布 → 回到 L1
每一步都由觉提出（第 ⑤ 节），主人准备，签字人签字。
```

```python
class ReqItem(BaseModel):
    text: str
    slot: str | None = None
    quote_refs: list[str] = []                # turn id，可回查客户原话
    ku_refs: list[str] = []                   # 依据的知识单元（转化对照、案例、机理）；其归属人记 cited
    edited_by: str | None = None              # v5：最后一次由人修改的 actor id；None = 骨架或 Agent 起草（界面标「Agent 起草」）
                                              # v8 收口：委托人在对话里交代、助手当轮改他这一轮打开的那张单（focus），记委托人；派单准备或顺手改别的单仍为 None

class PMDraft(BaseModel):                     # L2：场景语言 → 产品需求语言（规则骨架，产品经理 Agent 编辑）
    direction: str                            # 产品方向，如「低浴比条件下的锦纶氨纶匀染助剂」
    product_lang: list[ReqItem]

class RDDraft(BaseModel):                     # L3：产品需求 → 化学语言（规则骨架，研发 Agent 编辑）
    chem_lang: list[ReqItem]
    hypotheses: list[str] = []                # 研发方向假设

class SheetDraft(BaseModel):                  # 反向包装：产品需求＋对外要点 → L1 说明书（规则模板，产品经理 Agent 编辑）
    sheet: str
    usage: str

class ReuseProposal(BaseModel):               # v5.1：产品经理 Agent 查 L2 知识后的现成产品建议
    product_id: str | None                    # None = 已查，无现成产品
    ku_refs: list[str] = []                   # 依据的 L2 知识（案例、L2 转化对照）；采用时给归属人记 cited
    customer_note: str = ""                   # 面向客户的一句说明（v5.3：研发审定后才对 L1 可见；保存与审定时过 leak_hits）
    note: str = ""                            # 给业务员的依据说明，只写归属，不写案例原文
    declined_reason: str = ""                 # 研发不采用的理由（v5.3）

class LeakHit(BaseModel):                     # v5：泄密匹配结果，只给句序号与类别，不含命中内容
    index: int                                # 按「。；！？\n」切句后的序号，从 0 开始
    source: Literal["sealed", "l3_term", "hypothesis"]

class PointsDraft(BaseModel):                 # v5：封存 / 放出两栏草稿（只对 L3 可见）
    public: str                               # 拟放出的对外要点
    sealed: list[str]                         # 拟封存的窗户纸
    self_check: list[LeakHit] = []            # 对 public 的泄露自查结果

class ContributionDraft(BaseModel):           # v5：Agent 提炼的可沉淀转化知识（只对 L3 可见）
    item_index: int
    scene_phrase: str
    chem_term: str
    note: str = ""                            # 泛化说明、与已有知识相近或冲突之处

class Requirement(BaseModel):
    id: str                                   # "req:<n>"
    question_id: str                          # 产生它的 escalate_need 或 opportunity 问题
    session_ids: list[str]
    phenomenon: str
    known_slots: dict[str, str]
    assigned_rd: str                          # v5：接单与签字的研发；建单时取该现象 L3 转化对照条数最多的研发（并列取 id 最小）
    escalate_note: str = ""                   # v5：业务员签字时的升级说明（L2/L3 可见）
    reuse: ReuseProposal | None = None        # v5.1：现成产品建议；None = 还没查
    merged_into: str | None = None            # v5.2：被并入的单指向主单
    merge_from: list[str] = []                # v5.2：产品经理 Agent 起草的合并建议，拟并入本单的需求单 id（研发签字前是草稿）
    merge_note: str = ""                      # v5.2：判断依据——几位客户说的是不是同一件事（L2/L3 可见）
    direction: str = ""                       # v5：空单时为空
    product_lang: list[ReqItem] = []          # L2/L3 可见；v5：空单时为空
    chem_lang: list[ReqItem] = []             # L2/L3 可见；所引 L3 知识的原文只有 L3 可见
    hypotheses: list[str] = []                # 研发方向假设（v5：只对 L3 可见）；泄密匹配的来源之一
    status: Literal["draft", "reused", "merged", "rd_accepted", "rd_confirmed", "released", "rejected"]
    # v5：pm_confirmed → rd_accepted；v5.1：reused = 采用了现成产品（v5.3：研发审定），需求单关闭；v5.2：merged = 已并入另一张单
    drafted_by: str = "pm:agent"              # v5：L2 草稿的起草者
    chem_drafted_by: str | None = None        # L3 草稿的委托人（研发 actor id）
    rd_accepted_by: str | None = None         # v5：研发接单（= 立项），原 pm_confirmed_by
    rd_confirmed_by: str | None = None
    return_notes: list[str] = []              # v5：研发退回理由（提交前经 L3 术语自查，L2 可见）
    contribution_drafts: list[ContributionDraft] = []   # v5：只对 L3 可见
    points_draft: PointsDraft | None = None   # v5：只对 L3 可见
    public_points: str = ""                   # 研发签字放出的对外要点：L3 内容流向 L2/L1 的唯一出口
    sealed: list[str] = []                    # v5：研发签字封存的窗户纸，只对 L3 可见
    sheet: SheetDraft | None = None           # 反向包装草稿
    product_id: str | None = None             # 目标产品：L3 确认时关联研发中项目（种子 status=project，或接单时立的 proj:<req_id>，v8 Q9.3）；发布后即新产品
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
    market_eval: Literal["pass", "fail"] | None = None   # v5：客户评价，业务员录入
    market_eval_by: str | None = None
    market_eval_note: str = ""

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
    # v5：对 L2 查看者，requirement 中的 sealed、points_draft、contribution_drafts、hypotheses 置空；L1 抛 PermissionDenied
    # v5.1：业务员通过会话视图看到的现成产品建议只含产品（L1）、customer_note 与知识归属，不含案例原文
    # v5.3：L3 查看者看到完整的 reuse（ku_refs 原文可展开），审定在研发工作面上进行

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
def draft_product_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, pm: Actor, at: datetime) -> PMDraft: ...
    # v5：输入从问题改为（空）需求单
    # 输入：会话轮次（带 turn id）、NeedState 槽位与原话、kb.list(pm, kinds=["case", "translation"], phenomenon=...)
def draft_chem_need(req: Requirement, sessions: list[Session], kb: KnowledgeBase, rd: Actor, at: datetime) -> RDDraft: ...
    # 输入：产品需求条目、原话、kb.list(rd, kinds=["translation", "mechanism"], phenomenon=...)
def package_sheet(req: Requirement) -> SheetDraft: ...
    # 输入只有 req.product_lang 与 req.public_points；不得读 sealed、points_draft、chem_lang、hypotheses、机理、配方、L3 转化对照
def leak_hits(text: str, sealed: list[str], hypotheses: list[str], kb: KnowledgeBase) -> list[LeakHit]: ...
    # v5：规则匹配，逐句检查 sealed 各项、kb 中 level=3 转化对照的 chem_term、hypotheses 的关键词（子串或字符二元组重合）；
    # 不查 L2 内容（说明书本来就由产品需求包装而来）。觉的状态构建、门面的发送拦截、退回理由自查与发布可签条件共用
```

- 三个函数都是**规则实现**（零成本、确定；离线演示、测试与评测用）：按转化对照的 `scene_phrase` 与原话 / 上一层条目文字的匹配逐条生成，`ku_refs` 指向命中的转化对照，`quote_refs` 指向命中的轮次；没有命中知识的原话保留为「未转译」条目，不编造。
- 大模型参与转译的方式是**角色助手**（第 ⑭ 节）：助手先调用规则骨架，再用工具检索、逐条修改。
- **不变量（有测试）**：`draft_product_need` 的输出不含任何 L3 知识；`package_sheet` 的输出不含 L3 内容；L2 视图里没有 `sealed`。
- 对外泄密是规则匹配，挡不住换说法的泄露；最后一道闸是研发审定发布（D16）。

### 7.2 流程 `huayan.escalation.flow`（WP-A3）

```python
def contribute_translation(req: Requirement, item_index: int, scene_phrase: str, chem_term: str,
                           by: Actor, kb, ledger, events, at) -> KnowledgeUnit: ...
    # 研发把修改后的一条 chem_lang 沉淀为 L3 转化对照：kind="translation"，level=3，owner=by，source="contributed"；
    # 记 contributed 积分与 knowledge_contributed 事件；该条 ReqItem.ku_refs 追加新知识
def release_product(req: Requirement, product: Product, kb, ledger, events, by: str, at) -> Product: ...
    # product.status 改为 released → kb.add_product → 给 product.owner 记 product_released
    # → 写 product_released 事件 → req.status = "released"；v5：by 必须是 req.assigned_rd
```

演示中新产品取自种子里 `status="project"` 的产品（`confirm_translation` 时由门面关联到 `req.product_id`，机理与配方要点来自它），模拟「研发在 ELN 中完成开发」；L1 说明书与用法来自 `req.sheet`（反向包装，产品经理 Agent 起草，研发 Agent 可改写泄密句），**研发审定后发布**（v5）。窗户纸默认本单封存并沉淀为研发自己的 L3 知识，研发可在沉淀处拒签（D15）。

---

## ⑧ 事件日志（`huayan.events`，WP-0 提供）

```python
EventKind = Literal["turn", "extraction", "ask_hint", "match", "recommend", "escalate", "retrieve", "access_denied",
                    "decrypt_request", "decrypt_approve", "question_published", "question_prepared",
                    "question_resolved", "requirement_created", "requirement_accepted", "requirement_returned",
                    "requirement_edited", "requirement_translated", "knowledge_contributed", "trial", "market_eval",
                    "points_set", "reuse_proposed", "reuse_adopted", "reuse_declined", "merge_proposed", "requirements_merged", "product_released", "sheet_updated",
                    "access_frozen", "human_decision",
                    "agent_action_proposed", "agent_action_decided",
                    "auto_executed", "sales_assigned", "project_declined", "l2_contributed", "scope_extended"]   # v6
# v5：删除 requirement_confirmed

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
| `match`（v5） | `phenomenon, known, customer_id, candidate_ids, p_choice: {product_id: p}, p_none, scored_by` |
| `recommend` | `product_id, version, p_choice, candidate_ids, phenomenon, known: {slot: value}, customer_id` |
| `escalate` | `question_id, requirement_id, phenomenon, known, customer_id, p_none`（v5：只在业务员签字后写） |
| `retrieve` | `query, intent, actor_level, hit_ku_ids, n_blocked, blocked_product_ids`；v8：`principal`（权限所属的身份）；`actor` 是真正提问的一方：客户说的话记客户，助手的检索记 `agent:<委托人>` |
| `access_denied` | `object_id, reason` |
| `decrypt_request` / `decrypt_approve` | `question_id, customer_id, product_id` |
| `question_published` / `question_resolved` | `question_id, family, object_id, template_id`；resolved 时另有 `action, by` |
| `question_prepared`（v5） | `question_id, family, by` |
| `requirement_created`（v5） | `requirement_id, question_id, phenomenon, session_ids, assigned_rd` |
| `requirement_accepted`（v5） | `requirement_id, phenomenon, known, ku_refs`（研发接单；ku_refs 为 L2 所引） |
| `requirement_returned`（v5） | `requirement_id, reason`；v8 可带 `slots`（研发「试样前回问」或「接单前回问」勾选的条件，觉据此对这些条件提出回问） |
| `requirement_edited`（v5） | `requirement_id, layer, index, before, after`（index = -1 追加；after 为空 = 删除） |
| `requirement_translated` | `requirement_id, ku_refs`（研发确认 L3） |
| `knowledge_contributed` | `ku_id, owner, requirement_id` |
| `trial` | `trial_id, product_id, conditions, result, cause` |
| `market_eval`（v5） | `requirement_id, trial_id, result` |
| `points_set`（v5） | `requirement_id, n_sealed`（不含内容） |
| `reuse_proposed`（v5.1） | `requirement_id, product_id, ku_refs`（product_id 为空 = 已查无现成产品） |
| `reuse_adopted`（v5.1） | `requirement_id, product_id, session_id` |
| `reuse_declined`（v5.1） | `requirement_id, product_id, reason` |
| `merge_proposed`（v5.2） | `question_id, target, members`（members 为空 = 判断不是同一件事） |
| `requirements_merged`（v5.2） | `question_id, target, members` |
| `product_released` | `product_id, requirement_id, phenomenon, applicable` |
| `project_opened`（v8 Q9.3） | `requirement_id, product`（接单即立项：没有覆盖本单的研发中项目时立 `proj:<req_id>`；product 为项目快照，说明书、机理、配方为空，续跑时据此重建） |
| `sheet_updated` | `product_id, slot, values` |
| `access_frozen` | `actor_id` |
| `human_decision`（v5） | `action, object_id, object_type, attrs`（人执行生效动作时同一对象上没有对应的 open 问题；attrs 为当时的属性快照） |
| `agent_action_proposed` | `action_id, tool, principal, conversation_id` |
| `agent_action_decided` | `action_id, tool, principal, status`（approved / rejected） |

所有事件的 `actor` 即操作人；签字类事件的 `actor` 就是签字人。

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

**v5 模拟业务周**：照常走真实链路；推进类决策由「模拟人」签字——问题提出即签（`sign` / `accept`），退回率为 0；模拟周中不产生 `human_decision`。需求卡、注入清单仍只有 `sim/`、`eval/` 可读。

**评测产物** `docs/reports/<name>/`：`metrics.json`、图（png）、`README.md`（一页说明，结果如实写）。

---

## ⑩ 模型网关与计量（复制自 JUE）

```python
class Tier(str, Enum):
    FAST = "fast"; STRONG = "strong"; BACKUP = "backup"; MOCK = "mock"

class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageURL(BaseModel):
    url: str

class ImageContent(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: ImageURL

class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[TextContent | ImageContent]  # V10 C1；旧字符串消息不变
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
# v5：删除 routing，主人与签字人随模板（第 ⑤ 节）
points: {cited: 1, contributed: 5, trial_pass: 5, product_released: 10}
```

`config/models.yaml`、`config/system1.yaml` 格式同 JUE。

---

## ⑫ 应用门面 `huayan.app.HuayanApp`（WP-A2 创建，A3、I 补全）

界面**只**通过它访问系统；按身份裁剪在门面内完成，界面不做权限判断。

```python
class ReuseView(BaseModel):                   # v5.1：业务员看到的现成产品建议（不含案例原文）
    requirement_id: str
    product_id: str | None                    # None = 已查，无现成产品
    product_name: str = ""
    usage: str = ""                           # 产品的 L1 用法
    customer_note: str = ""                   # 研发审定后的面向客户的说明（v5.3：pending 时为空，basis 也为空）
    basis: list[str] = []                     # 归属标签，如「产品经理 P01 · 历史案例 · L2」
    status: Literal["pending", "adopted", "declined", "none"]


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
    reply_draft: str = ""                     # v5
    escalate_note: str = ""                   # v5
    reuse: ReuseView | None = None            # v5.1：会话所升级需求单上的现成产品建议
    asks: list[PendingAsk] = []               # v8：待答回问（open 的 ask_back）；客户在自助页直接回答，研发的问题直达客户

class PendingAsk(BaseModel):                 # v8：只给槽位问法，不含研发内容
    question_id: str
    slot: str
    label: str
    ask_text: str

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

class TimelinePoint(BaseModel):               # v5：觉的一次判断中的一个「决策 × 对象」
    at: datetime
    family: Family
    object_id: str
    p_need: float | None
    threshold: float
    scored_by: str
    raised: bool                              # 这一次是否提出了问题

class TimelineNode(BaseModel):                # v5：一个被提出的问题的全过程
    question_id: str
    family: Family
    owner_id: str | None
    signer_id: str | None
    created_at: datetime
    prepared_at: datetime | None
    resolved_at: datetime | None
    action: str | None
    by: str | None

class JueTimeline(BaseModel):                 # v5：觉视图
    target_id: str                            # sess:<n> 或 req:<n>；需求单线程含其全部会话
    viewer: str
    points: list[TimelinePoint]               # 按查看者裁剪：业务员只含 escalate_need、reuse_product（v5.1）、market_eval、ask_back 与本会话的 ask_slot
    nodes: list[TimelineNode]
    n_judgments: int                          # 觉的判断次数（JueRecord 条数）
    n_llm_calls: int                          # 计量中 caller 以 "jue" 开头的大模型调用数（应为 0，取自计量，不写死）
    n_questions: int
    n_signatures: int

class HuayanApp:
    @classmethod
    def build(cls, config_path: str = "config/app.yaml", run_id: str | None = None) -> "HuayanApp": ...
    seeds: Seeds; kb: KnowledgeBase; bus: QuestionBus; events: EventLog
    audit: AuditLog; ledger: Ledger; actors: dict[str, Actor]

    # L1（WP-A2）
    def start_session(self, customer_id: str, sales_id: str | None = None) -> Session: ...
        # v6：sales_id 为 None = 客户自助会话（origin="customer"），只接受客户发言，升级由觉自动执行
    # v6 路由（REPLAN-v6 V6-1）
    def decline_project(self, req_id: str, reason: str, by: str, applicable_product: str | None = None,
                        claim_ids: Sequence[str] = (), limits: str = "") -> Requirement: ...
        # V9.5：limits 非空时与 reason 同样过研发术语自查，原文写入适用能力 payload["limits"]
        # assigned_rd，draft；status="rejected"，写 project_declined（reason、product_id）；accept_requirement resolve(dismiss)，
        # 需求单其余 open 问题 resolve(answered)；给出 applicable_product 时各会话按公开版本推荐该产品，否则会话 closed
    def route_of(self, object_id: str, viewer_id: str) -> dict: ...
        # 只读：会话（或需求单所在会话）当前路径（自助解决 / 交业务员 / 入研 / 复用 / 产品机会 / 研发不立项 / 追问中）、
        # 四个角色格的状态（human / auto / pending / none）与依据（觉的问题、分数、结案人）；全部由事件与状态推出
    def auto_execute(self, question_id: str) -> Question: ...
        # 内部入口（6.1 节），只由 hub 调用，不经 HTTP；查表 {escalate, assign_sales}，执行者 jue:auto，写 auto_executed，resolve(auto)
        # assign_sales：按 config/app.yaml 的 customer_sales 写入会话业务员，写 sales_assigned；会话 origin 不变
    # v6 产品经理协作（V6-3）；by 必须是真人产品经理（pm:agent 只能起草）
    def extend_scope(self, question_id: str, note: str, by: str) -> KnowledgeUnit: ...
        # scope_update 的签字人；把现象加进本门面内该产品的 solves（不改种子），生成本人名下 L2 知识
        # ku:translation:scope:<pid>:<ph>，记 contributed；写 scope_extended；此后 L1 因它命中时给归属人记 cited
    def contribute_l2(self, req_id: str, item_index: int, scene_phrase: str, product_term: str, by: str) -> KnowledgeUnit: ...
        # 只能沉淀本人修正过的 L2 条目；生成 ku:translation:<req>:l2:<i>（L2），记 contributed；写 l2_contributed；resolve contribution_pm(sign)
    def merge_requirements(self, question_id: str, by: str, note: str = "") -> Requirement: ...
        # v6：签字人改为真人产品经理，note = 商业价值判断，写入结案备注与 requirements_merged
    def readiness(self, req_id: str, viewer_id: str) -> dict: ...
        # v6.1 开工门槛（只读，L2/L3）：必问条件逐项的取值、原话、是否出现在客户开场白、是否由觉追问得到；
        # 未答回问、未处理失真数；ready = 必问条件齐全且无阻断
    def add_turn(self, session_id: str, speaker: Literal["customer", "sales"], text: str) -> Session: ...
        # v5：不再自动升级。业务员发言先过发送拦截：leak_hits(text, 全部需求单的 sealed, [], kb) 有命中则抛 ValueError
        # （消息只含命中句序号与类别），不写入；客户发言答复了 open 回问时：resolve(answered)，取值写入需求单 known_slots，
        # 并把该需求单上已待签的问题 bus.set_prepared(None) 退回准备中
        # （v8）「答复了」= 客户开口时该槽位已有答案（填上或不清楚），不论出自哪一句；会话里已填、需求单还没有的条件一并写入
    def recommend_now(self, session_id: str) -> Session: ...
    def view_session(self, session_id: str, viewer_id: str) -> SessionView: ...
    def sessions(self) -> list[Session]: ...
    def jue_trace(self, session_id: str) -> list[JueOutput]: ...         # 该会话每轮的实时觉输出，觉视图用
    def status(self) -> RunStatus: ...

    # L2 / L3：分层转译、权责与回流（WP-A3）。每个方法一个动作，角色助手的工具一对一调用它们（第 ⑭ 节）
    def escalate(self, session_id: str, by: str) -> Requirement: ...
        # v5：业务员签字。建空需求单（assigned_rd；escalate_note ← session.escalate_note）、resolve escalate_need(sign)、
        # session.status="escalated"、写 escalate 与 requirement_created
    def save_reuse_proposal(self, req_id: str, product_id: str | None, ku_refs: list[str], customer_note: str,
                            note: str, by: str) -> Requirement: ...
        # v5.1：pm:agent，草稿；product_id 为空 = 已查无现成产品；customer_note 过 leak_hits；写 reuse_proposed
    def update_reuse_note(self, req_id: str, text: str, by: str) -> Requirement: ...
        # v5.3：草稿修改，by 为 assigned_rd 或 pm:agent；过 leak_hits；写 requirement_edited
    def adopt_reuse(self, req_id: str, by: str) -> Session: ...
        # v5.1 / v5.3：assigned_rd 审定签字；customer_note 过 leak_hits；按 Jev 披露版本给需求单首个会话生成推荐卡（附客户说明，标审定研发）；
        # 所引 L2 知识记 cited，bounty 给研发；status="reused"；resolve reuse_product(sign)；写 reuse_adopted；业务员不签字，自行转述
    def decline_reuse(self, req_id: str, reason: str, by: str) -> Requirement: ...
        # v5.1 / v5.3：assigned_rd；写 declined_reason，resolve(return)，写 reuse_declined；觉随后提出 accept_requirement
    def save_merge_proposal(self, question_id: str, target_req_id: str, member_ids: list[str], note: str,
                            by: str) -> Requirement: ...
        # v5.2：pm:agent，草稿；target 与 members 必须在 opportunity 的 requirement_ids 里；写 merge_from、merge_note、merge_proposed；
        # 判断不是同一件事时 target 填最早一张、members 为空
    def merge_requirements(self, question_id: str, by: str) -> Requirement: ...
        # v5.2：主单的 assigned_rd 签字；merge_from 为空抛 ValueError；被并入单的会话追加到主单，被并入单 status="merged"、
        # merged_into=主单，其 open 问题 resolve(answered)；resolve opportunity(sign)；清空主单 L2 草稿（product_lang、direction），
        # 主单待签问题 set_prepared(None)，产品经理 Agent 按全部会话重新起草；写 requirements_merged
    def draft_requirement(self, req_id: str, by: str) -> Requirement: ...
        # v5：by 必须是 pm:agent；对空单（draft）写入 L2 规则骨架
    def accept_requirement(self, req_id: str, by: str) -> Requirement: ...
        # v5：by = assigned_rd；→ rd_accepted；给所引 L2 知识记 cited；
        # v8 收口：不因 open 回问或失真被拒（二者只作证据）；机会汇聚由觉再看结案
        # resolve accept_requirement(accept)；写 requirement_accepted
    def return_requirement(self, req_id: str, reason: str, by: str) -> Requirement: ...
        # v5：by = assigned_rd；reason 过 leak_hits（只看 l3_term），命中抛 ValueError；追加 return_notes；resolve(return)；状态仍为 draft
    def edit_req_item(self, req_id: str, index: int, item: ReqItem, by: str) -> Requirement: ...
        # pm:agent 改 product_lang（draft），研发改 chem_lang（rd_accepted）；index = -1 表示追加；
        # v5：人改的条目写 edited_by，写 requirement_edited 事件。
        # 校验（大模型输出的真实边界）：quote_refs 必须是该需求单会话中的轮次，ku_refs 必须存在且 by 可读，否则 ValueError
    def remove_req_item(self, req_id: str, index: int, by: str) -> Requirement: ...  # 层的规则同上
    def set_direction(self, req_id: str, text: str, by: str) -> Requirement: ...      # pm:agent，draft 状态
    # v5：删除 confirm_requirement（立项 ≡ 研发接单）
    def translate_requirement(self, req_id: str, by: str) -> Requirement: ...
        # 研发（assigned_rd）；L3 规则骨架写入 chem_lang 与 hypotheses，chem_drafted_by=by
    def confirm_translation(self, req_id: str, by: str) -> Requirement: ...
        # by = assigned_rd；→ rd_confirmed；关联 product_id（种子中覆盖该现象与已知槽位的 status=project 产品）；
        # v5：只给所引 L3 知识的归属人记 cited（L2 已在接单时记）
    def contribute_translation(self, req_id: str, item_index: int, scene_phrase: str, chem_term: str,
                               by: str) -> KnowledgeUnit: ...
    def set_public_points(self, req_id: str, text: str, sealed: list[str], by: str) -> Requirement: ...
        # v5：assigned_rd 签字「封存 / 放出」；需客户评价通过；写 public_points 与 sealed，写 points_set
    def save_reply_draft(self, session_id: str, text: str, by: str) -> Session: ...          # v5：业务员（Agent）
    def save_escalate_note(self, session_id: str, text: str, by: str) -> Session: ...        # v5：业务员（Agent）
    def save_points_draft(self, req_id: str, public: str, sealed: list[str], by: str) -> Requirement: ...
        # v5：assigned_rd（Agent）；自动填 self_check = leak_hits(public, sealed, hypotheses, kb)
    def save_contribution_draft(self, req_id: str, draft: ContributionDraft, by: str) -> Requirement: ...   # v5：assigned_rd（Agent）
    def record_market_eval(self, req_id: str, result: Literal["pass", "fail"], note: str, by: str) -> Trial: ...
        # v5：需求单首个会话的业务员签字（v8 收口：自助单由客户的归属业务员签）；写到最近一次通过的试样上；写 market_eval
    def leak_check(self, req_id: str, viewer_id: str) -> list[LeakHit]: ...
        # v5：说明书与用法的命中；L2 查看者也可调用（只得到序号与类别）
    def requirements(self, viewer_id: str) -> list[Requirement]: ...      # L1 调用抛 PermissionDenied
    def requirement_view(self, req_id: str, viewer_id: str) -> RequirementView: ...   # L1 抛 PermissionDenied
    def record_trial(self, trial: Trial) -> Trial: ...        # v5：来自模拟 ELN，不写 human_decision
    def package_sheet(self, req_id: str, by: str) -> SheetDraft: ...
        # v5：by 为 pm:agent（草稿，不是生效动作）；translate.package_sheet(req)，结果写入 req.sheet
    def save_sheet(self, req_id: str, sheet: SheetDraft, by: str) -> Requirement: ...
        # v5：pm:agent 修改说明书草稿，或 assigned_rd（研发 Agent 改写泄密句）
    def release_product(self, req_id: str, by: str) -> Product: ...
        # v5：by = assigned_rd；可签条件：说明书与用法 leak_hits 为空；
        # 以 req.product_id 的种子产品为底，sheet / usage 用 req.sheet，调用 flow.release_product
    def contributions(self, viewer_id: str) -> list[ContributionStat]: ...
        # 贡献看板；L3 知识的标题对非 L3 查看者显示为「研发 X 的转化知识」
    def request_decrypt(self, session_id: str, by: str) -> Question: ...
    def decide_decrypt(self, question_id: str, by: str, approve: bool, text: str = "") -> Question: ...   # v5：text 为第二档

    # 角色助手（第 ⑭ 节；WP-L 实现 AgentHub，WP-I 在 build 中挂上）
    agents: AgentHub

    # 统一循环（v5）
    def mark_prepared(self, question_id: str, by: str) -> Question: ...
        # 只由 AgentHub 在主人的 Loop 结束后调用（离线时在规则骨架起草后调用）；不注册为工具
    def questions(self, viewer_id: str) -> list[Question]: ...
        # 查看者作为主人或签字人的 open 问题；界面据 prepared_at 分「准备中 / 待签」
    def jue_timeline(self, target_id: str, viewer_id: str) -> JueTimeline: ...

    # 觉定时发现与处置（WP-I）
    def scan(self, at: datetime | None = None) -> list[Question]: ...
    def resolve(self, question_id: str, action: str, by: str, note: str = "") -> Question: ...
        # update_sheet → kb.update_applicable；freeze_access → permission.freeze；dismiss；v5：删除 approve_project
    def tick(self) -> list[Question]: ...
        # 距上次扫描 ≥ 30 业务分钟则 scan（定时部分）；然后 agents.dispatch()；返回本次新发现的问题
        # 界面在每次操作之后、脚本在每一步之后调用
```

**写后评估（v5）**：每个改状态的方法结束时，门面对受影响的 session / requirement（及其 slot）构建状态 → 实时模型 `propose` → `publish`，每次追加一条 `JueRecord`；被评估对象（及需求单的 slot）上前置条件不再成立、或对象已不活动的 open 问题 resolve(answered, by="jue")（v8 收口：从异常类扩到全部问题；门面方法只结案本次签字对应的问题，不替别的问题结案）；执行生效动作时若同一对象上没有对应的 open 问题，写 `human_decision`。v8 收口：助手起草期间（`AgentHub` 的一轮对话，派单准备含退回再做）门面先记下受影响的会话与需求单，起草结束后评估一次（门面 `drafting()` 上下文，按线程分开），中间稿不触发问题；别的线程这时的写后评估跳过正在起草的需求单，由起草的线程结束时评估。门面方法内部不推进下一步（AGENTS.md 铁律 14）。

---

## ⑬ 运行产物 `runs/<run_id>/`

`events.jsonl`、`audit.jsonl`、`ledger.jsonl`、`metering.jsonl`、`questions.jsonl`（每次变化追加一行快照）、`sessions/<session_id>.json`（会话结束或每轮后覆盖写）、`conversations/<conv_id>.json`（助手对话，每轮覆盖写）、`pending.jsonl`、`agent_trace.jsonl`、`jue_samples.jsonl`（v4，`JueRecord`）。`runs/` 不入库，演示用的记录回放目录除外（`runs/demo_record/`）。

---

## ⑭ 角色 Agent 与产品经理 Agent（`huayan.agent`，WP-L；v5 改）

v5：业务员、研发各有一个**协作 Agent**，产品经理由**产品经理 Agent**（`pm:agent`）担任。三者都是 **Agent Loop + 原子工具**：觉的问题派给主人后，Agent 查会话、检索、起草，把草稿写进领域对象（需求单、会话的草稿字段）；人在工作面上看、改、按按钮签字。私聊用于开放式请求与查询。

- 助手**没有自己的权限**，借用委托人的权限：工具在代码里绑定委托人，模型看不到也改不了；v8：助手以自己的名义（`agent:<委托人>`，产品经理 Agent 为 `pm:agent`）记检索事件与错误，它的错不算到委托人头上；
- `read` / `draft` 工具自动执行，草稿未生效；
- `effect` 工具**只能提议**，且只用于对话里的提议：Loop 创建 `PendingAction`，确认卡出现在工作面签字区，**委托人点确认后才执行**；助手没有、也不能有「确认」工具。工作面上的签字按钮直接调门面原子方法，不经过 `PendingAction`；
- **没有委托人的 Agent 没有生效工具**：`pm:agent` 只有 read / draft 工具；
- 觉不是助手，不调用大模型；它提出的问题经总线派给主人准备。

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
    target: str | None = None                 # v5：批注挂的位置，如 "req:3/chem/2"、"sess:5/reply"；None = 普通消息

class Conversation(BaseModel):
    id: str                                   # "conv:<actor_id>:<session_id 或 inbox>"；v8 agent_threads=object 时收件箱按对象分段 "conv:<actor_id>:<req_id 或 object_id>"
    principal: str                            # v5：产品经理 Agent 为 pm:agent
    role: Role                                # sales / pm / rd
    session_id: str | None = None             # 业务员助手绑定的客户会话
    messages: list[AgentMessage] = []
```

```python
# huayan.agent（WP-L）
class AgentHub:                               # HuayanApp.agents
    def __init__(self, app: "HuayanApp"): ...
    def chat(self, actor_id: str, text: str, session_id: str | None = None, focus: str | None = None) -> Conversation: ...
        # v5.2：focus = 委托人此刻在工作面上打开的对象（sess:<n> / req:<n>），写进 Agent 的系统提示词
        # 委托人说一句话 → 跑一轮 Loop → 返回整段对话；业务员必须带 session_id
    def notify(self, actor_id: str, text: str, session_id: str | None = None) -> Conversation: ...
        # 派单：写一条 system 消息到该人的 inbox 对话（带 session_id 时写到该会话的对话）并跑一轮 Loop（助手主动处理，如起草）
    def dispatch(self) -> list[Conversation]: ...
        # v5：只把总线上 open、prepared_at 为空、尚未派过的问题 notify 给主人（owner_id）；主人是 pm:agent 时跑产品经理 Agent 的 Loop，
        # 是业务员 / 研发时跑其 Agent 的 Loop；有签字人的问题在 Loop 结束后调用 app.mark_prepared；
        # 提示类（signer_role 为空）照旧派送，sales 的 ask_back 按 refs["session_id"] 派到该会话的对话
    def approve(self, action_id: str, by: str) -> PendingAction: ...
        # by 必须是 principal，否则 PermissionDenied；执行该工具，结果写回对话，写 agent_action_decided；v5：不再派下一棒
    def reject(self, action_id: str, by: str, note: str = "") -> PendingAction: ...
    def pending(self, actor_id: str) -> list[PendingAction]: ...
    def conversations(self, actor_id: str) -> list[Conversation]: ...
    def trace(self, conversation_id: str) -> list[AgentStep]: ...
```

**Loop**（`huayan/agent/loop.py`，复用 JUE `src/jue/agent/__init__.py` 并简化，去掉派生与钩子）：
- 每轮：系统提示词（`prompts/assistant_<role>.md` + 委托人身份 + 当前待确认动作）+ 对话历史 → `gateway.complete(tools=该角色的工具, caller="agent:<role>", tier=fast, temperature=0)` → 执行工具调用，结果追加为 tool 消息 → 直到没有工具调用或满 8 步 → 最后的文字作为助手回复；
- 本轮的工具消息只在本轮保留，跨轮只保留文字消息（含确认结果的 system 消息）；
- 每一步写一条 `AgentStep`；
- `gateway_mock` 为 true 时不跑 Loop：`chat` 只追加一条「助手需要大模型（当前离线）」的 system 消息；v5：`dispatch` 对主人调用对应的规则骨架（`draft_requirement` / `translate_requirement` / `package_sheet`）后 `mark_prepared`，没有骨架的（升级说明、封存两栏、提炼）用录制缓存或标注「离线，无草稿」。

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
| `get_need_card()` | read | sales | `app.view_session(session, principal)` |
| `save_reply_draft(text)` | draft | sales | `app.save_reply_draft`（v5） |
| `save_escalate_note(text)` | draft | sales | `app.save_escalate_note`（v5） |
| `request_decrypt()` | effect | sales | `app.request_decrypt(session, principal)`（对话提议） |
| `list_my_questions()` | read | sales pm rd | `app.bus.list(owner_role=角色)`，只留 owner_id 为空或为本人的 |
| `get_session(session_id)` | read | pm rd | `app.view_session(session_id, principal)` |
| `match_translations(text)` | read | pm rd | `translate.match_translations` |
| `find_products(phenomenon, slots)` | read | sales pm rd | `domain.match_candidates(phenomenon, slots, kb.products())` |
| `propose_reuse(req_id, product_id, ku_refs, customer_note, note)` | draft | pm | `app.save_reuse_proposal`（v5.1） |
| `edit_reuse_note(req_id, text)` | draft | pm rd | `app.update_reuse_note`（v5.3） |
| `propose_merge(question_id, target_req_id, member_ids, note)` | draft | pm | `app.save_merge_proposal`（v5.2） |
| `draft_product_need(req_id)` | draft | pm | `app.draft_requirement`（v5 改参数） |
| `get_requirement(req_id)` | read | pm rd | `app.requirement_view` |
| `edit_item(req_id, index, text, quote_refs, ku_refs)` | draft | pm rd | `app.edit_req_item` |
| `remove_item(req_id, index)` | draft | pm rd | `app.remove_req_item` |
| `set_direction(req_id, text)` | draft | pm | `app.set_direction` |
| `package_sheet(req_id)` | draft | pm | `app.package_sheet` |
| `edit_sheet(req_id, sheet, usage)` | draft | pm rd | `app.save_sheet`（v5：研发 Agent 改写泄密句） |
| `leak_check(req_id)` | read | pm rd | `app.leak_check`（v5；只得到句序号与类别） |
| `draft_chem_need(req_id)` | draft | rd | `app.translate_requirement` |
| `save_points_draft(req_id, public, sealed)` | draft | rd | `app.save_points_draft`（v5） |
| `save_contribution_draft(req_id, index, scene_phrase, chem_term, note)` | draft | rd | `app.save_contribution_draft`（v5） |
| `confirm_translation(req_id)` | effect | rd | `app.confirm_translation`（对话提议） |
| `contribute_translation(req_id, index, scene_phrase, chem_term)` | effect | rd | `app.contribute_translation`（对话提议） |
| `set_public_points(req_id, text, sealed)` | effect | rd | `app.set_public_points`（对话提议） |
| `decide_decrypt(question_id, approve)` | effect | rd | `app.decide_decrypt`（对话提议） |

v5 删除：`record_customer_turn`、`record_sales_turn`、`recommend_now`（客户原话不经过 Agent，发言与推荐在工作面上）；`confirm_requirement`、`dismiss_question`、`release_product`（`pm:agent` 没有生效工具）；`record_trial`（试样来自模拟 ELN）。
| `my_contributions()` | read | pm rd | `app.contributions(principal)` |

**v5 删除「确认后派单」**：下一步由觉的写后评估提出（AGENTS.md 铁律 14）。

**不变量（有测试，`tests/test_wp_l.py`，不调用模型）**：`pm:agent` 的工具集合中没有 `effect` 工具；它的 `search_knowledge` / `get_knowledge` / `get_requirement` 拿不到 L3 原文（只有 `BlockedHint` 与归属）、`sealed` 与 `points_draft`；`effect` 工具在 `approve` 之前不改变任何状态；非委托人 `approve` 抛 `PermissionDenied`。


## ⑮ 契 v7（2026-10-19，人已批准，之后冻结）

本节为 v7 的契约差异，覆盖前文同名定义与接口；未列出的部分保持不变。执行包见 `workpackages/REPLAN-v7.md`。


### 2.1 知识（契约 ②，`contracts/knowledge.py`）

```python
KUKind = Literal[..., "claim"]          # 新增：编译出的、或研发直接写下的结论；level 由依据定，不进 KIND_LEVEL

class KnowledgeUnit(BaseModel):          # 加三个字段，默认值保持现有行为
    ...
    evidence: list[str] = []             # "<doc_id>#<span>@<fingerprint>"，只存位置与指纹
    confirmed_by: str | None = None      # 迁移进来的取原 owner；现象的必问与先验为 "seed"
    status: Literal["candidate", "active", "withdrawn"] = "active"

Form = Literal["phrase", "ask", "applicable", "translation", "statement", "decrypt"]

class Capability(BaseModel):
    id: str                              # 第 0 天：cap:applicable:<pid>:<ph>、cap:ask:<ph>:<slot>、cap:prior:<ph>:<slot>；之后：cap:<n>
    form: Form
    audience: Level | str                # decrypt 为客户 id
    payload: dict                        # 见下表
    based_on: list[str]                  # 结论 id，至少一条，确认人都是 granted_by
    granted_by: str
    approved_by: str | None = None       # 只有 applicable 需要，见 1.3
    status: Literal["proposed", "active", "suspended", "revoked"]
    at: datetime

class Fragment(BaseModel):
    doc_id: str
    span: str                            # 段号，如 "p3"
    text: str
    level: Level
    source: Literal["public", "internal", "external"]
    fingerprint: str                     # sha256(text) 前 12 位

class ExploreResult(BaseModel):
    units: list[KnowledgeUnit]           # 本层可读、已确认的结论
    capabilities: list[Capability]       # 授予本层（及以下）的能力
    hints: list[str]                     # 只从本层视图算出
    stubs: list[BlockedHint] = []        # 只对 L1–L3；客户层永远为空
    candidates: list[KnowledgeUnit] = [] # 只对研发层：本层候选，标「候选」

class BlockedHint(BaseModel):            # v7.8 加一个字段（已批准）
    owner: str
    level: Level
    kind: KUKind
    ku_id: str | None = None             # 只在「同层研发、可申请查看」的存根上填写；跨层存根一律为 None
```

| form | payload | 第 0 天来源 |
|---|---|---|
| `applicable` | `{product_id, phenomenon, conditions: {slot: [values]}, limits?: str}`；V9.5：`limits` 为槽位表达不了的限制原文（产品级用语），带限制的适用只给研发和产品经理看、不在客户自助阶段自动推荐 | 每个已发布产品的每个 `solves` 现象 × 原 `applicable`，一行 |
| `ask` | `{phenomenon, slot, required: true}` 或 `{phenomenon, slot, prior: {value: p}}` | 现象的 `required_slots`、`slot_priors` |
| `statement` | `{text, product_id?}` | 无（第 0 天的说明书、用法、公开案例是 L0 结论，同层直接用） |
| `decrypt` | `{product_id, session_id, text}` | 无（启动时没有解密授权） |

结论与能力的新编号（`ku:claim:<n>`、`cap:<n>`）取已加载的最大序号加 1，跨重启不冲突；不用需求单号做编号（需求单号每次运行从 1 开始）。

`LedgerEntry.reason` 加 `"used"`。`DecryptGrant` 保留，改为由 `decrypt` 能力投影出来的只读类型（`approved_by = granted_by`，`session_id` 取自 payload）。

`SourceAdapter` 不定义成协议：本轮只有一种适配器（替身 RAG 的 `FolderSource`），接入企业 RAG 时再按它的三个方法 `search`、`fetch`、`list_docs` 写第二个类。

`KnowledgeBase` 的接口变化：

- `from_seeds(seeds, events, audit, *, state_path=None)`：只加一个有默认值的参数，现有三参数调用不变；
- 新增 `view(actor) -> Seeds`、`products()`（= 研发层视图的产品，只供系统内部扫描与内部各层使用）、`explore(query, actor) -> ExploreResult`、`capabilities(...)`、`decrypt_grants() -> list[DecryptGrant]`；
- 新增写入：`confirm(ku_ids, by, *, reviewed_evidence=None)`、`withdraw(ku_id, by)`、`grant(cap) -> Capability`、`approve(cap_id, by, *, reviewed_evidence=None)`、`revoke(cap_id, by)`、`evidence_changed(ku_id)`；每次写入后整体保存有效状态；
- 删除：`update_applicable`、`extend_solves`；
- `search`、`search_blocked`、`get`、`list` 的签名不变；可读条件加一条「结论状态为 `active`」（候选只经 `explore` 的 `candidates` 给研发，撤回的不再可读）。

V10.7 C7 最小参数差异：`reviewed_evidence: dict[str, list[str]] | None = None` 为本次实际审阅的
`{ku_id: ["doc_id#span@fingerprint", ...]}`。无来源的直接判断仍兼容原调用；有来源的结论必须显式提交。
确认时将提交值与一次取回的当前依据比对，缺少或不一致即拒绝，不自动刷新旧指纹。
相同 payload 的补充依据经确认才挂接到待挂接能力，沿现有 `claim_confirmed` 事件记录指纹、目标与原贡献人。
`HuayanApp.review_claims(ku_ids, by)` 向有权的真人研发/产品经理提供本次原文与指纹，拒绝 `pm:agent`；
确认、授予、不立项引用、复核及 `extend_scope(..., reviewed_evidence=None)` 门面透传该可选参数。
服务端不得在签字时自行取当前指纹替代审阅值。公开来源 `applicable` 批准的兼容路径：当有待确认结论且
未显式传参时，`approve` 只使用候选中保存的编译时指纹交 `confirm` 比对，来源改变仍拒绝；不改用当前来源新指纹。
没有新增冻结模型字段。

### 2.2 领域（契约 1.5，`contracts/seeds.py`、`domain.py`）

```python
class Situation(BaseModel):
    phenomenon: str
    conditions: dict[str, list[str]]     # 同时成立；未列出的槽位不限
    capability_id: str
    temperature_c: tuple[float, float] | None = None  # V10.6 C2：摄氏闭区间，单值两端相同

class Product(BaseModel):
    ...                                  # 种子文件格式不变
    situations: list[Situation] = []     # 不写在种子文件里，见下

class Candidate(BaseModel):
    product_id: str
    unknown_slots: list[str]             # 命中情境里未知的条件
    status: Literal["confirmed", "possible"] = "confirmed"
    capability_id: str | None = None
```

- `load_seeds` 给每个产品（含立项产品）按 `solves × applicable` 填好第 0 天情境，`capability_id = cap:applicable:<pid>:<ph>`。这样直接拿种子产品调匹配函数的地方（测试、`sim/`、`confirm_translation` 找立项产品）行为不变，也不需要兜底分支。
- `migrate_seeds(seeds, at) -> tuple[list[KnowledgeUnit], list[Capability]]`：直接读已发布产品的这些情境生成适用能力，按 2.1 表生成追问能力；每个现象生成一条 L3 结论 `ku:claim:phen:<id>`（必问与先验的依据，确认人 `"seed"`）。**迁移不写事件。**
- `view()` 用能力表重新算出情境，覆盖种子里的第 0 天情境；视图里的 `Product.solves` 取情境的现象并集，`Product.applicable` 置空。
- `consistent(product, known)`：存在一个情境与已知条件相容（不看现象）。
- `match_candidates(phenomenon, known, products, limited=(), *, temperature_c=None)`：取该现象下与已知条件相容的情境，每个产品优先取无限制且未知条件最少的那个；无未知/限制为 `confirmed`，否则 `possible`。新增温度关键字参数有默认值，原有枚举调用兼容。
- `correct_product`：用命中情境里**限定的槽位个数**衡量具体程度（与 V6 的 `len(applicable)` 一致）。

V10.6 C2 首个最小差异：只增加上述 `Situation.temperature_c` 默认字段及匹配关键字参数，保留枚举 `conditions`。
`applicable.payload` 可选 `temperature_c: [lower, upper]`，固定为摄氏闭区间，单值写作 `[value, value]`；
现有迁移与能力视图保留该范围，旧能力缺省为 `None`。`domain.temperature_match(actual, allowed)` 返回
`satisfied / unknown / outside`：客户区间完整包含于授权区间才满足，任一端越界即不命中；授权有范围而需求温度
未知时为 `possible`，`unknown_slots` 增加 `temperature_c`。没有温度限制的旧情境保持既有含义。
本小项不改 `NeedState` 或抽取输出，客户温度原话、未知状态与匹配调用接线由本包后续小项完成。

### 2.3 出口（契约 7.1）

- 新增 `render_refs(draft, audience, kb) -> str`（`knowledge/disclosure.py`；现有的 `render` 是推荐卡片渲染，名字和签名都不动）：把稿子里的 `[[编号]]` 换成原文。编号可以是层级 ≤ 收件层的已确认结论，或授予收件层（及以下）的 `statement`；其余编号直接抛 `PermissionDenied` 并记审计。
- `leak_hits(text, sealed, hypotheses, kb, *, audience=None)`：不传 `audience` 时与现在逐条一致；传入时增加来源 `"claim"`：与层级高于收件层的已确认结论重合。

### 2.4 事件（契约 ⑧）

新增 `claim_confirmed`、`claim_withdrawn`、`capability_granted`、`capability_revoked`、`capability_suspended`、`capability_used`、`evidence_changed`。`retrieve` 的 payload 加 `unanswerable_ku_ids` 与 `n_unanswerable`。`recommend` 的 payload 加 `status` 与 `capability_id`。批准复用现有 `scope_extended`。

（Q8，2026-10-20 人批准）新增 `recommendation_withdrawn`：能力撤销、挂起或产品页收窄后，已推荐的会话按本层现有情境重新匹配不再覆盖时退回 open，记这一事件；payload `{product_id, capability_id}`，`session_id` 为该会话，actor 为触发撤销的人。

（Q8，2026-10-20 人批准）`Turn.speaker` 加 `assistant`：客户自助会话（没有业务员）里，觉算出追问提示后，门面把第一条提示的问法作为化言的发言写进对话（一次只问一个），事件 `turn` 的 actor 为 `system`，并给该槽位的 `asked` 加 1；抽取把它和业务员的问话同样看待（客户答「不清楚」记为未知）。`add_turn` 仍只接受 `customer`、`sales`。

### 2.5 觉（契约 5.2、5.4、⑨）

- `collect_scheduled(events, at, seeds, products, windows=None, caps=())`：加 `caps`，供 `qi_grant`、`qi_review`、`scope_update` 读能力状态。
- 新家族 `qi_grant`（推进类）与 `qi_review`（异常类），对象类型都是 `knowledge`；`scope_update` 的对象改为「待批准的适用能力」。家族数 19 → **21**，`auto_action` 仍只有 `escalate`、`assign_sales`。两个新家族都没有 Jue-K 校准器，由模板 `rule_score` 打分并标 `scored_by: rule`（`jue_k.py` 现有处理）。
- `jue/records.py` 新增只读投影 `decision_rows(records, events)` 与 `rows_for(rows, level)`。`JueRecord` 不变。

### 2.6 配置（契约 ⑪）与网关（契约 ⑩）

所有 `config/app*.yaml` 加：

```yaml
sources: []            # [{name, kind: public|internal|external, root, level?}]；替身 RAG 指向 seeds/rag/ 或决赛资料目录
qi_state: null         # 有效状态文件；为 null 时用 <运行目录>/qi_state.json（每次新运行独立）；试点指向 data/qi/state.json。状态文件含运行期发布的产品与试样，只能配同一个运行目录用：接着上次运行一律走 resume（Q6.5），不让两个新运行共用一个状态文件
```

有效状态文件的内容（v7.2 扩大）：能力、`claim` 类结论、状态改过的结论、片段密级表、两个序号，**以及运行期新增的全部知识**（`source` 不是 `seed` 的知识单元：发布的产品说明、沉淀的转化知识、试样、公开案例之外的贡献）**和运行期发布的产品记录**。知识与能力的持久化只此一处。

`HuayanApp.build(config_path, run_id=None, byok=None, *, resume=False)`：`resume=True` 时 `run_id` 必须指向已有的运行目录，按 Q6.5 读回；默认行为不变。`EventLog`、`QuestionBus`、`AuditLog`、`Ledger` 的构造在文件已存在时读回已有记录（新增的只有这一个行为）。

`points` 加 `used: 1`。新 caller `ingest:extract`；编译脚本自建网关并关闭缓存（`cache_dir = None`），不另写模型配置。

### 2.7 门面（契约 ⑫）与 Agent（契约 ⑭）

- `HuayanApp.import_proposals(proposals, by)`：研发通过门面导入本人负责的提议，复用 `admit` 生成 candidate 结论与 proposed 能力提议，不执行确认或授予。
- 新增：`confirm_claims(req_id, ku_ids, by)`、`sign_qi_grant(question_id, by, claim_ids=(), note="")`、`revoke_capability(cap_id, by)`、`withdraw_claim(ku_id, by)`、`set_doc_level(doc_id, level, by)`、`recheck_evidence()`、`capabilities(viewer_id)`；
- 改：`decline_project(..., applicable_product=None, claim_ids=())` 不再要求相容，改为提议一个完整情境；`extend_scope` 改为批准待批准的适用能力；`release_product` 同时授予新品的适用情境；`decide_decrypt` 写 `decrypt` 能力；`adopt_reuse` 的审定说明写 `statement`（授予业务员层）；`save_reply_draft` 先过 `render_refs` 与 `leak_hits(audience=0)`；`resolve` 处理 `qi_review`；`app.grants` 改为 `kb.decrypt_grants()` 的只读属性；
- 门面内部按「代谁」取视图（设计第 4 节规则一的表）；`self.seeds` 只用于标签、问法、抽取词表，以及读立项产品；
- Agent 工具 `search_knowledge` 改调 `explore`；写给下层的文字里，专业结论只写 `[[编号]]`。

### 2.8 独立审查后的两处修正（已批准）

1. **`qi_review` 做成独立家族，不放进 `knowledge_conflict`。** 设计原写「`knowledge_conflict` 家族的新模板」，但 `jue/proto.py:20-22` 与 `docs/CONTRACTS.md` 第 623 行规定「每个 family 只有一个模板」，`resolve` 也按 family 决定允许的动作。所以 `qi_review` 单列为家族，家族数 21。
2. **出口渲染函数叫 `render_refs`，不叫 `render`**：`disclosure.render` 已是推荐卡片渲染，`test_wp_a1` 在用。

### 2.8′ 试样失败回路与回测（v7.6，已批准）

- `Trial.cause` 增加 `"requirement"`（需求条件缺失），`Trial` 加 `missing_slots: list[str] = []`（研发填写缺了哪几个条件）与 `market_eval_missing: list[str] = []`（客户评价不通过时，业务员按客户反馈勾选的条件）。
- 新家族 `trial_rework`（推进类，对象类型 `requirement`，主人与签字人都是研发），家族数 21 → **22**；`auto_action` 不变。
- `record_requirement_trial(req_id, result, by, cause="none", missing_slots=())`、`record_market_eval(req_id, result, note, by, missing_slots=())`：多两个带默认值的参数。
- 新 caller `eval:one_shot`（回测里「强模型一次性翻译」对照组）。

### 2.10 研发之间的知识边界（v7.7，已批准）

规则一句话：**同层的研发知识，用到才看、看了就记分；随手检索只见归属，想看原文向归属人申请。** 理由见第 13 节。

- **读权限（契约 ②，`knowledge/permission.py::can_read`）**：在层级判断之外加一条——知识 `level == 3`、归属人是真人研发（`owner` 以 `rd:` 开头；结论取 `confirmed_by`）、读者是另一位研发时，只有存在授予读者本人的 `active` 的 `share` 能力才可读。归属人本人照常可读；系统内部身份（id 以 `system:` 开头，如觉现有的 `system:jue`）不受此限。适用于转化知识、机理、配方、试样、结论各类，配方同样可以授予。
- **能力形式**：`Form` 加 `"share"`：`audience` 为读者的研发 id，payload `{ku_id}`，`based_on = [ku_id]`，`granted_by` = 归属人，不需要产品经理批准；可由归属人撤销。结构约束不变：配方仍不能作 `audience < 3` 的依据，`share` 的读者本来就在 L3。
- **工作中用到**：`Requirement` 加 `engine_refs: list[str] = []`，由转译引擎起草 L3 条目时写入它引用的知识编号。门面**只对这张单的接单研发（`assigned_rd`）**，把 `engine_refs` 里的知识按「工作中用到」处理：需求单页显示原文、技术确认时可通过校验、确认时照常记「被引用」分。研发自己往条目里加的编号仍须本人可读（自己的或被授予的），不能靠猜编号读到同事的知识。这个判断只写在门面一处。
- **需求单正文也按接单研发裁剪**：L3 条目（`chem_lang`）的正文本身就含转化知识，研发假设、封存项、两类草稿同理。`requirement_view` 对非接单研发与对 L2 一视同仁：只给产品需求条目（`product_lang`，L2）、状态、现象、已知条件与接单人，L3 条目正文、假设、封存项、草稿置空；「引用的知识」按 `can_read` 显示原文或只显示归属。这样「打开同事的单子」读不到同事的知识。
- **可申请的存根**：`BlockedHint` 加 `ku_id`（已批准）。`search_blocked` 与 `explore` 只在「读者是研发、命中的是同事的 L3 知识」时填写，界面据此显示「申请查看」；跨层存根（L1、L2 看到上层）仍不填，客户层仍什么都不返回。`request_share` 的 `ku_id` 就取自这里。
- **转译引擎**：`draft_chem_need` 以内部身份 `system:translate` 读转化对照与机理。研发方向假设只对归属人本人写出机理首句；同事的机理写成「`<产品>` 有相关机理（归属 `<研发>`，可申请查看）」。
- **申请与授予**：门面新增 `request_share(ku_id, by)`（仅研发，对象必须是本人当前不可读的同层知识），写 `share_requested` 事件；觉的 `qi_grant` 加第三种对象 `knowledge:share:<ku_id>|<申请人>`，属性 `{product_id, pending, granted}`，前置条件 `attrs.pending and not attrs.granted`，`rule_score` 恒为 1（人主动申请，必提）；`refs` 写明主人与签字人都是归属人。觉只在总线上提出「此刻需要归属人决定是否授予」，问题的证据写明谁申请、哪条知识；觉不通知人、不起草、不签字。之后照现有流程：hub 把问题派给主人（归属人）的研发 Agent，Agent 在归属人的助手对话里告知并附上申请人的哪些单子碰到过这条知识（离线时无草稿，与其他家族一致）；问题卡出现在归属人工作面的签字区，归属人签字或忽略。`sign_qi_grant` 对这种对象 `grant` 一条 `share` 能力，并给归属人记一笔 `shared`。拒绝走现有的 `dismiss`。不新增家族，家族数不变。
- **记分**：`LedgerEntry.reason` 加 `"shared"`；配置 `points` 加 `shared: 2`。
- **事件**：新增 `share_requested`；授予与撤销复用 `capability_granted`、`capability_revoked`。


补充 caller：`ingest:draft`（公开来源起草种子）；`eval:one_shot`（真实案例的一次性翻译对照）。

Jue-K 模型按「家族 × 判断层」保存：`models: {"<family>|L<k>": (classifier, calibrator)}`。对象属性 `judge_level` 标明代谁判断；每格只使用同家族、同判断层且结果层级不高于该层的行训练，无模型的格按规则打分。

## ⑯ 觉的预判与业务月 v8（2026-10-21，人已批准，之后冻结）

依据 `docs/workpackages/REPLAN-v8.md`。

- **属性（契约 5.2）**
  - requirement 加：`n_unknown_required` int（现象必问槽位里客户答「不清楚」的个数）、`unknown:<slot>` 0/1（每个槽位是否答了「不清楚」）、`n_unquoted_slots` int（已填条件里没有客户原话依据的个数）、`match_possible` bool（需求单产品在当前条件下只是「可能适用」）、`hist_n_trials` int 与 `hist_fail_rate` float（同产品、条件被本单条件覆盖的历史试样数与失败率）、`hist_req_fail_rate` float（同现象历史试样里因需求条件缺失失败的比率）。实施 Q9.1 时补（人已批准，2026-10-21）：`missing:<slot>` 0/1（未填且客户没答过「不清楚」）、`value:<slot>=<取值>` 1（已知条件的取值独热）；没有这两组，学习模型看不到「哪个条件缺了 × 其他条件是什么」的交叉。
  - 新增定时对象「能力效果」`knowledge:stale:<cap_id>`（对象类型 `knowledge`），只针对运行中由人签出、生效中的适用能力（`approved_by != "seed"`）：`n_used`、`n_outcomes`、`n_fail` int，`fail_rate`、`recent_fail_rate`（最近 7 天）、`early_fail_rate`（此前）、`fail_concentration`（失败集中在某一「槽位 = 取值」上的最大比例）float，`days_since_grant` float，`n_market_fail` int。
  - knowledge（知识冲突）的 `claimed` 只认第 0 天情境。
- **家族**：新增 `trial_risk`（推进类，对象 `requirement`，主人与签字人为研发）、`stale_capability`（推进类，对象 `knowledge`，主人与签字人为授予人），家族数 22 → **24**；`auto_action` 不变。
- **门面（契约 ⑫）**：新增 `return_for_conditions(req_id, slots, by)`（研发；`rd_confirmed` → `rd_accepted`，写 `requirement_returned`，payload 带 `slots`）、`narrow_capability(cap_id, conditions, by)`（授予人；撤销原能力并按更窄条件授予，依据不变）、`timeline(day, by)`（主管只读；L3 内容只给存根）。
- **网关（契约 ⑩）**：新 caller `sim:sales`、`sim:rd`、`sim:pm`（业务月里大模型扮演的业务员、研发、产品经理）；Q9.4 加 `sim:supervisor`（主管，人已批准，2026-10-22）。
- **事件**：不新增；`requirement_returned` 的 payload 可带 `slots`。

实施 Q9.3 时补（人已批准，2026-10-21）：

- **准备以对象为准**：门面 `preparation_gap(question_id) -> str` 返回主人准备还缺什么（接单要产品需求条目、复用要复用建议、确认转译要化学语言条目、发布要说明书草稿、机会汇聚要合并建议），齐了返回空串；`mark_prepared` 有缺口时抛 `ValueError`。`AgentHub.dispatch` 在 Agent 回复后按缺口退回给它再做一次（`PUSHBACKS = 1`），同一问题最多派 2 次（`ATTEMPTS`），仍没准备好就留在「准备中」并记 Agent 错误；Agent 说「已就绪」不算。
- **Agent 的错误记在 Agent 名下**：`runs/<run_id>/agent_errors.jsonl`，每行 `at, agent, principal, kind, …`；`kind`：`tool_rejected`（门面或参数拒绝）、`prepare_missing`（准备后对象上缺草稿）、`prepare_failed`、`out_of_steps`、`memory_rejected`。不进事件日志（不改事件编号）。`retrieve` 事件的 `actor` 是真正提问的一方（见第 ⑧ 节）。
- **助手记忆（契约 ⑭）**：`MemoryEntry{id, principal, kind: habit|fact|lesson, text, why, refs, at, status}`，按委托人存，写 `runs/<run_id>/memory.json`、重启读回。门面：`memories(by)`、`recall_memory(query, by)`、`remember(kind, text, why, refs, by)`（`leak_hits` 按委托人层级校验，含上层内容拒绝）、`forget(memory_id, by)`（只能删自己助手的）、`decision_records(by, since)`（程序生成的当天决策记录，不调用大模型）、`close_day(since)`（收工时各助手归纳）。工具：`remember`（draft）、`recall_memory`（read），三类角色都有。`agent_memory` 打开时，每段对话开头注入最近 30 条记忆索引；`AgentHub.consolidate(principal, since)` 用该助手自己的 caller（`agent:<role>`）归纳：增、删记忆，写入仍经门面校验。
- **AgentHub**：`conversation(actor_id, session_id, thread)`、`conversation_of(question)`、`pending_dispatch()`、`dispatch(only=None)`（只派这几个问题，模拟器按对话分组并发用）、`error(principal, kind, **detail)`、`errors(principal)`。
- **配置**：`agent_threads: inbox | object`、`agent_memory: bool`。演示与默认配置为 `inbox` / `false`（录制缓存是旧对话结构）；企业编制为 `object` / `true`。
- **界面接口**：`GET /api/agents/conversation` 加 `thread`；`GET /api/agents/memory`；`POST /api/agents/forget`。
- **接单即立项**：`accept_requirement` 时若没有覆盖本单的研发中项目（`status=project`、解决本现象、与已知条件一致），门面立一个 `proj:<req_id>`（适用条件为接单时的已知条件，归属接单研发，说明书、机理、配方为空），写 `project_opened` 事件，续跑时据此重建；已有覆盖的项目则不立，技术确认照旧关联它。`confirm_translation` 先找覆盖的研发中项目，没有就用本单立的项目。发布接单时立的项目：机理取化学语言条目，配方为模拟占位，第一条适用情境取本单通过试样的条件。立项是研发接单这次签字的效果，不另设决策点。
- **产品经理退出逐单转述**（依据 2026-10-12 与研发研究员的交流：目标是客户—研发需求直达，产品经理专注产品全生命周期）：被研发退回的单主人仍为 `pm:agent`，按退回理由重写；`preparation_gap` 对接单要求最近一次退回之后有产品需求条目被修改，否则返回缺口。真人产品经理只签适用范围扩展与机会汇聚。
- **说明书清干净才算准备好**：`release` 与 `seal_leak` 的 `preparation_gap` 在说明书或用法仍有泄密命中时返回缺口（只给句序号），主人用 `edit_sheet` 改写；命中清除后 `seal_leak` 由觉自动结案。
- **接单前先回问客户**（人已批准，2026-10-21）：门面 `ask_before_accept(req_id, slots, by)`（接单研发签 `accept_requirement`；单子仍为 `draft`，写 `return_notes` 与带 `slots` 的 `requirement_returned`，接单问题以 `return` 结案，不经产品经理）；觉对勾选的条件向业务员提出 `ask_back`。模板 `accept_requirement` 的前提加 `attrs.n_missing == 0`：客户答完之前不再提接单。界面接口 `POST /api/ask_before_accept`。缺的是只有客户知道的条件时用它；需求写得不清楚才 `return_requirement` 退回产品经理 Agent。
- **收口（人已批准，2026-10-21，见 REPLAN-v8 Q9.3 收口方案 A–G）**：
  - 门面只拒绝权限、做不到、红线三类；「该不该、何时」只在觉的模板。`accept_requirement(req_id, by)` 不再有 `note`，接单与 `confirm_translation` 不因未答回问或失真提示被拒，二者只作证据列在签字区；撤回上面「越过失真提示接单」一条。
  - 觉再看统一结案（写后评估与定时扫描，见第 ⑫ 节）；`accept_requirement` 不再关闭机会汇聚，`save_reuse_proposal` 不再关复用问题、不再调用 `scan()`，`decline_project`、`merge_requirements` 不再关同单问题。模板 `reuse_product` 前提为 `status == 'draft' and (not reuse_checked or reuse_pending)`。
  - 推进类问题没有「忽略」，不想处理就留在待办；异常类问题可「越过」，`resolve(dismiss)` 带理由。
  - requirement 属性 `n_unmapped_constraints` 改为 `n_conflicting_refs`（契约 5.2）；模板 `distortion` 前提改用它与 `n_unquoted_items`。
  - `ReqItem.edited_by`：委托人在对话里交代（`AgentHub.chat`）、助手当轮改的条目记委托人；派单准备时仍为 `None`。
  - 自助单的客户评价由客户的归属业务员签（解析表见 5.4 节），`record_market_eval` 允许会话业务员或归属业务员；`view_session` 允许归属业务员查看自己客户的自助会话（其助手准备客户评价要绑定该会话）。
  - 写后评估在助手起草结束后做（见第 ⑫ 节）：Agent 一次准备里的中间稿不再让觉提出又结案。
  - 客户补条件只走一条路：会话里补的与回问答的，起草中的单都按会话条件更新已知条件、清掉未经人改的产品需求条目，由产品经理 Agent 重写；已接单的单照旧只把答复补进已知条件。
- **评审后修正（人已批准，2026-10-22）**：
  - 研发的问题直达客户：`SessionView.asks`（`PendingAsk`：问题编号、槽位、槽位名、问法，不含研发内容）列出本会话上未答的回问；客户自助页显示「研发想确认」，客户直接在自助页回答，归属业务员不必先接手会话。
  - 重问只认回问之后的答复：单上已有这个条件、或客户先前答过「不清楚」时（试样失败、客户评价不通过后再问），回问只由回问提出之后的那句答复结案。
  - `ReqItem.edited_by` 记委托人只限他这一轮打开的那张单（对话的 `focus`，`req:3` 或 `req:3/chem/2`）；助手顺手改别的单仍记 Agent 起草。
  - `decision_records`（收工归纳材料）给业务员时不含研发的退回理由，只列要回问客户的条件名。
  - 决策投影（5.4）：`trial_risk`、`stale_capability` 的问题没有人的处置时，用之后的结果补标签（口径同 Q9.1、Q9.2 轨迹），`level = 3`；结果未出为 `None`。
- **步数用完也看对象**：Agent 步数用完时同样按 `preparation_gap` 判断，对象齐了照常标记已准备，有缺口才记 `out_of_steps`。派单文字以对象编号开头（需求单、会话），问题编号放在后面。

## ⑰ 泄露判断分层 v8 Q9.8（2026-10-22，人已批准，之后冻结）

依据 `docs/workpackages/REPLAN-v8.md` Q9.8。与前文冲突处以本节为准（2.3 冻结、5.2 actor 属性、`_intent` 关键词）。

- **意图（契约 ③）**：`Intent` 类型不变。`mechanism_request` 只指问产品内部（成分配比、机理、配方、配法、作用原理）；问自己的毛病为什么出现、问用法、问说明书与安全技术说明书上本就公开的合规信息（APEO、甲醛、离子性、固含量、pH）都不算。抽取提示词随之改。知识库按关键词判检索意图时只认「配方、配比、机理、原理、成分、染座」，不再认「为什么」「pH」。
- **事件（契约 ⑧）**：
  - 新增 `access_unfrozen`（payload `actor_id`）。
  - `retrieve` 的 payload 加 `target_products`（查询里出现的产品编号或名称）、`capability_ids`（本次返回的 `statement` 能力）、`denied`（冻结后被拒）。
  - `extraction` 的 payload 加 `speaker`（customer / sales）、`customer_id`、`after_rec`（这句话说出时会话已有推荐）、`products`（意图为 `mechanism_request` 时这句话指到的产品：型号或已推荐产品，按 L1 回答同一解析）。
  - `decrypt_approve` 的 payload 加 `capability_id`。
- **审计（契约 ②）**：`AuditRecord.action` 加 `unfreeze`。
- **冻结（2.3）**：冻结的效果只有四项：指到产品的原理请求（意图为 `mechanism_request` 且 `target_products` 非空）返回空并记拒绝；`explore` 不返回授予给本层的 `statement` 能力；披露上限为用法；不能申请解密。其余工作照常：门面不再因冻结拒绝看工作台、看需求单与时间线、录试样、审批解密。新增 `KnowledgeBase.unfreeze(actor_id, by, at)`：写 `access_unfrozen` 事件与审计 `unfreeze`。重启续跑时按冻结、解冻事件的先后恢复。
- **属性（契约 5.2）**：
  - **actor（定时，泄露风险）**：对象只取业务员本人：`retrieve` 的 `actor` 为 `sales:<id>` 或 `agent:sales:<id>` 的都记到 `sales:<id>`；客户、`pm:agent`、研发及其助手不是 actor 对象。窗口为配置 `windows.actor_hours`（企业编制 168 小时），且从该业务员最近一次解冻起算。属性：`role` str、`n_queries` int、`n_mech_requests` int（意图为 `mechanism_request`、指到产品、未被拒的检索）、`n_statements_top` int（读到的授予结论里同一产品最多的条数）、`top_product` str 与 `top_product_share` float（原理请求与读到的授予结论按产品计，最集中的产品及其占比）、`n_decrypt_requests` int、`n_decrypt_products` int、`n_decrypt_customers` int、`frozen` bool（按冻结、解冻事件先后）。去掉 `n_blocked`、`blocked_top_share`、`n_distinct_products`。
  - **session（实时）** 加：`n_internals_after_rec` int（本会话推荐之后客户问产品内部、且指到产品的轮数）、`customer_internal_products` int（该客户 48 小时内各会话问过内部的不同产品数）、`customer_decrypts` int（该客户已获批且未撤销的解密数）、`followup_handled` bool（本会话的 `mechanism_followup` 已结案）。全部从事件日志算，`session_state` 签名不变。
- **家族**：新增 `mechanism_followup`（异常类，对象 `session`，主人与签字人为业务员），家族数 24 → **25**。改写 `leak_risk`（对象只取业务员；证据不再提「被拦截」）。
- **解析表（5.4）**：`sales` 角色在会话对象上为会话业务员，自助会话（尚无业务员）为客户的归属业务员（门面在会话对象的引用里传 `account_sales`）。
- **Jue-K（5.4）**：`leak_risk|L2` 旧模型作废；新特征下重训之前不用，两组都用模板规则打分，标 `scored_by: rule`。
- **门面（契约 ⑫）**：
  - 新增 `unfreeze_access(actor_id, by)`（只给主管；对象须已冻结）。
  - 新增 `frozen_actors(viewer_id)`（只给主管）：每个被冻结的人一行：`actor_id`、`name`、`frozen_at`、`frozen_by`、`evidence`（冻结时问题的证据摘要）、`n_denied`（冻结以来被拒次数）、`customers`（手上在跟的客户）。
  - `resolve`：`mechanism_followup` 允许动作 `take_over`：会话尚无业务员时按客户归属交给业务员（同 `assign_sales`）；问题以 `take_over` 结案，`followup_handled` 为真，不再重复提出。
  - `request_decrypt` 去掉「客户须懂化学」的拦截，只留权限（自己的会话、未被冻结）与做不到（没有推荐）。解密申请问题带事实证据：客户画像（懂不懂化学、依据原话）、该客户已获批的解密（产品、批准研发、日期）、申请业务员近 30 天为哪些客户、哪些产品申请过解密。只列事实，不判断。
  - 同层研发申请查看知识（`qi_grant` 带 `requester`）的问题证据加申请人近 30 天的其他申请。
- **界面接口**：`POST /api/unfreeze`、`GET /api/frozen_actors`。

## ⑰′ 理解只在一处（2026-10-22 晚，人已批准，之后冻结）

依据 `docs/workpackages/REPLAN-v8.md` 第 9 节。与 ⑰ 冲突处以本节为准。原则：每段输入只在一处被理解（客户的话由抽取理解一次），下游只读结构化字段，不再各自用关键词重判语义；规则抽取器只作离线降级，标 `extracted_by: rule`。

- **意图（契约 ③）**：`Intent` 取值为 `need`、`product_question`（问用法、问适不适用、问管不管用）、`cause_question`（问自己的毛病为什么出现）、`mechanism_request`（只指问产品内部：成分配比、机理、配方）、`commercial`（报价、采购、送样、要找业务员或人工）、`smalltalk`。问说明书与安全技术说明书上本就公开的合规信息（APEO、甲醛、离子性、固含量、pH）算 `product_question`。⑰ 中「知识库按关键词判检索意图」一条作废。
- **抽取（契约 ③）**：`ExtractionResult` 加 `product_refs: list[str]`：这句话指到的产品编号，「推荐的那个」「前者」这类指代由抽取按上下文解析成编号；抽取校验丢掉本层视图里没有的编号。
- **事件（契约 ⑧）**：
  - `extraction` 的 `products` 记本轮 `product_refs`，不再限于要原理的轮次；`intent` 照旧。
  - `retrieve` 的 `intent` 由调用方传入：客户会话传本轮抽取的 `intent`，助手检索传 `purpose`（可空），其余为空；知识库不再自己判。`target_products` 为调用方传入的产品编号（客户会话为本轮 `product_refs`），知识库不从查询文字里猜。
- **冻结（2.3）**：效果第 1 项改为「`explore` 不再返回上层存根（谁知道）」；其余三项（不返回授予给本层的 `statement` 能力、披露上限为用法、不能申请解密）不变。被冻结者的检索照常记 `denied`（本次有存根或授予结论被挡下）。
- **属性（契约 5.2）**：
  - **actor**：去掉 `n_mech_requests`；加 `n_stubs_top` int（窗口内碰到的上层存根里同一产品最多几条，按 `retrieve` 的 `blocked_product_ids` 计）；`top_product`、`top_product_share` 改按「读到的授予结论 + 碰到的上层存根 + 解密申请」三者按产品合计；其余不变。
  - **session**：`n_internals_after_rec`、`customer_internal_products` 由客户发言的 `extraction` 事件（`intent == mechanism_request` 且 `products` 非空）算；`purchase_intent` 为本会话有客户发言的 `intent == commercial`。
- **Agent 工具（契约 ⑭）**：`search_knowledge` 加可选参数 `purpose`（`usage` / `cause` / `internal` / 空），原样作为 `retrieve` 的 `intent` 记进事件，只作参考，不进泄露判断。
