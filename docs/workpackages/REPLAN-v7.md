# REPLAN-v7｜契落地

> 2026-10-19。代码基线：`main` @ `351c2c9`（V6 完成态）。设计依据：契 v3.3 设计文档（[链接](https://claude.ai/code/artifact/c4b96c26-b91f-4ab6-a261-5ca22cff07f5)，下称「设计」）、`docs/VISION.md` 第 1 节、`docs/PITCH.md` 第 6.1 节。
> **第 2 节的全部契约改动已由人一次批准**，之后冻结；实施中需要再改契约，先停下来问人。
> 本文与 `REPLAN-v6.md` 冲突处以本文为准。不标耗时。

## 0. 目标与写法

### 0.1 做完是什么样

1. **第 0 天行为不变**：现有种子迁成结论与能力后，11 个测试全绿，离线主线（`scripts/demo_mainline.py`）的推荐、升级、需求单状态与迁移前一致；失真对照、业务周的数字不重跑也不变。
2. **决赛主演示在离线配置下真实跑出**：三态（未授予 / 已授予 / 已撤销）、四步能力复用、重启后状态保留，以及与 V6 在同一批问题上的对照，数字全部从事件日志统计。
3. **VISION 1.2 节里标「设计完成」的几条主张变成「已实现」**，证据指向测试与演示报告。

### 0.2 防止屎山的六条写法（每个包都要守）

1. **一张能力表，一条读路径。** 能力存在知识库里；引擎读知识只走 `kb.view(actor)`。删掉 `update_applicable`、`extend_solves`，知识库不再持有可改的产品适用字段，也不保留「旧字段 + 新能力」两套判断。
2. **视图就是种子形状。** `view(actor)` 返回现有的 `Seeds` 对象（槽位、现象、产品……），引擎函数签名不变；调用方只是把 `self.seeds` / `kb.products()` 换成对应层的视图。不新造一套视图类型。
3. **同层不建行。** 设计第 6 节：同层自用不需要授予。所以已确认的结论在它自己那一层直接可用（现有 `can_read` 已经做到），**能力表只放四种行**：所有适用情境（`applicable`）、给更低层的追问（`ask`，含第 0 天迁移的必问与先验）、跨层的可说的话（`statement`）、解密（`decrypt`）。`translation` 只在同层使用，不建行；`phrase` 见 1.2。
4. **没有新框架。** 不写规则引擎、不做事件溯源、不做插件注册；适配器就是一个读文件夹的类。传播（依据 → 结论 → 能力）是数据上的引用，写成一个函数。
5. **只校验业务规则，不写防御代码。** 要校验的只有设计里的规则：授予人必须是所依据结论的确认人、配方不能作下层依据、只依据外部片段不能确认、适用能力要产品经理批准、候选结论不跨层。内部调用之间不加 `isinstance`、不加兜底 `try`、不给不存在的情况写分支。
6. **每包一个提交，删的和加的一样多。** 每个包写明删什么；包结束时 `pytest` 11 个全绿；原子工具仍不超过 15 行。

## 1. 落地前的三处校正

### 1.1 演示数据换成 LV205（设计第 12 节的例子不能直接用）

设计第 12 节用 LV206 讲例子，和现有种子冲突两处：

- `HY-LV205` 已经覆盖「锦纶 × 溢流染色机」，所以「客户 C05 纯锦纶 × 溢流色花 → 客户层没有候选」不成立，C05 会直接拿到 LV205；
- `HY-LV206` 在种子里是 `status: project`，V6 主线和 `test_wp_a3` 都依赖「LV206 未发布、需立项」这条路；而重启后运行期发布的产品不会保留，K5 跨重启的演示也就不成立。

**改为用已发布的 `HY-LV205`（归属研发 R01），研发角色统一为 R01：**

| 编号 | 内容 | 来源 |
|---|---|---|
| 公开情境（第 0 天迁移） | LV205 × 色花 × {锦纶, 锦纶氨纶} × {溢流染色机, 卷染机} | 种子，即产品页 |
| K3 ask | 色花 × 染浴 pH：要追问 | R01 确认的 C4（依据 RPT-031，模拟） |
| K5 applicable | LV205 × 色花 × {锦纶氨纶} × {经轴染色机} | R01 确认的 C2（依据 RPT-044，模拟） |

四步演示随之改为：C05「锦纶氨纶 × 经轴染色机」→ 无候选，进研发，R01 依据 RPT-044 判 LV205 适用并授予 K5，产品经理批准；C07 同样条件 → 前台确认适用直接推荐；C08「锦纶 × 经轴染色机」→ 不是候选（K5 只覆盖锦纶氨纶，公开情境不含经轴），照常进研发；另一位客户只说「锦纶氨纶」没说设备 → LV205 可能适用，卡片列出「设备为溢流染色机、卷染机或经轴染色机，请确认」；撤销或依据失效后回到研发，重启后状态保留。

V6 在这组数据上的真实表现也更清楚：V6 的 `decline_project` 要求所选产品与客户已知条件相容（V6-3.1 S4），LV205 不含经轴，所以 R01 的判断在 V6 里**根本记不下来**，C07、C08 每次都进研发。

测试里「两个情境不交叉」的断言用 `mini_seeds` 自己构造，不依赖这组数据；PITCH 第 6.1、7.5 节里「锦氨 × 气流 / 纯锦纶 × 溢流」的写法描述的是测试，保持不变。设计第 12 节和 PITCH 的演示台词在 Q7 按本节更新。

### 1.2 `phrase` 本轮没有入口

V6 没有「业务员改正槽位」的入口，新加这个入口不在落地主线上。`phrase` 留在形式枚举里，本轮不建行、不加入口；客户说法仍来自种子（种子说法本来就是 L0 结论，在客户层直接可用）。设计第 9 节的第②类签字量在报告里写「未实现」。

### 1.3 适用的批准走 C′ 原路，不加新事件

研发授予适用情境 → 能力处于 `proposed` → 觉照常提出 `scope_update` → 产品经理在现有 `extend_scope` 里签字 = 批准，能力变 `active`，复用现有的 `scope_extended` 事件。`qi_grant` 授予出的适用能力也走这条路。

## 2. 契约变更（已批准，之后冻结）

### 2.1 知识（契约 ②，`contracts/knowledge.py`）

```python
KUKind = Literal[..., "claim"]          # 新增：编译出的、或研发直接写下的结论；level 由依据定，不进 KIND_LEVEL

class KnowledgeUnit(BaseModel):          # 加三个字段，默认值保持现有行为
    ...
    evidence: list[str] = []             # "<doc_id>#<span>@<fingerprint>"，只存位置与指纹
    confirmed_by: str | None = None      # 迁移进来的取原 owner
    status: Literal["candidate", "active", "withdrawn"] = "active"

Form = Literal["phrase", "ask", "applicable", "translation", "statement", "decrypt"]

class Capability(BaseModel):
    id: str                              # 第 0 天：cap:applicable:<pid>:<ph>、cap:ask:<ph>:<slot>、cap:prior:<ph>:<slot>；之后：cap:<n>
    form: Form
    audience: Level | str                # decrypt 为客户 id
    payload: dict                        # 见下表
    based_on: list[str]                  # 结论 id，至少一条，确认人都是 granted_by
    granted_by: str
    approved_by: str | None = None       # 只有 applicable 需要；第 0 天为 "seed"
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
```

| form | payload | 第 0 天来源 |
|---|---|---|
| `applicable` | `{product_id, phenomenon, conditions: {slot: [values]}}` | 每个已发布产品的每个 `solves` 现象 × 原 `applicable`，一行 |
| `ask` | `{phenomenon, slot, required: true}` 或 `{phenomenon, slot, prior: {value: p}}` | 现象的 `required_slots`、`slot_priors` |
| `statement` | `{text, product_id?}` | 无（第 0 天的说明书、用法、公开案例是 L0 结论，同层直接用） |
| `decrypt` | `{product_id, text}` | 无（启动时没有解密授权） |

`LedgerEntry.reason` 加 `"used"`。`DecryptGrant` 保留，改为由 `decrypt` 能力投影出来的只读类型。

`KnowledgeBase` 的接口变化：

- 新增 `view(actor) -> Seeds`、`products()`（= 研发层视图的产品，只供系统内部扫描与内部各层使用）、`explore(query, actor) -> ExploreResult`、`capabilities(...)`、`decrypt_grants() -> list[DecryptGrant]`；
- 新增写入：`confirm(ku_ids, by)`、`withdraw(ku_id, by)`、`grant(cap) -> Capability`、`approve(cap_id, by)`、`revoke(cap_id, by)`、`evidence_changed(ku_id)`；每次写入后整体保存有效状态（2.6）；
- 删除：`update_applicable`、`extend_solves`；
- `search`、`search_blocked`、`get`、`list` 不变。

### 2.2 领域（契约 1.5，`contracts/seeds.py`、`domain.py`）

```python
class Situation(BaseModel):
    phenomenon: str
    conditions: dict[str, list[str]]     # 同时成立；未列出的槽位不限
    capability_id: str

class Product(BaseModel):
    ...                                  # 种子格式不变
    situations: list[Situation] = []     # 只由视图填；种子里不写

class Candidate(BaseModel):
    product_id: str
    unknown_slots: list[str]             # 命中情境里未知的条件
    status: Literal["confirmed", "possible"] = "confirmed"
    capability_id: str | None = None
```

- `consistent(product, known)`：存在一个情境与已知条件相容（不看现象）。
- `match_candidates(phenomenon, known, products)`：签名不变；取该现象下与已知条件相容的情境，每个产品取未知条件最少的那个；无未知条件为 `confirmed`，否则 `possible`。
- `correct_product`：用命中情境的条件数衡量具体程度。
- 新增 `migrate_seeds(seeds, maintainer, at) -> tuple[list[KnowledgeUnit], list[Capability]]`：按 2.1 表生成第 0 天的能力；每个现象生成一条 L3 结论 `ku:claim:phen:<id>`（必问与先验的依据，确认人为配置的维护人）。
- 视图里的 `Product.solves` 与 `Product.applicable` 由情境汇总（现象取并集、每个槽位的取值取并集），**只供展示和觉的属性**；任何适用判断只看 `situations`。

### 2.3 出口（契约 7.1）

- 新增 `render(draft, audience, kb) -> str`（`knowledge/disclosure.py`）：把稿子里的 `[[编号]]` 换成原文。编号可以是层级 ≤ 收件层的已确认结论，或授予收件层（及以下）的 `statement`；其余编号直接抛 `PermissionDenied` 并记审计。
- `leak_hits(text, sealed, hypotheses, kb, *, audience=None)`：不传 `audience` 时与现在逐条一致；传入时增加来源 `"claim"`：与层级高于收件层的已确认结论重合。

### 2.4 事件（契约 ⑧）

新增 `claim_confirmed`、`claim_withdrawn`、`capability_granted`、`capability_revoked`、`capability_suspended`、`capability_used`、`evidence_changed`。`retrieve` 的 payload 加 `unanswerable_ku_ids`（命中但本层没有能力的结论）与 `n_unanswerable`。`recommend` 的 payload 加 `status` 与 `capability_id`。批准复用现有 `scope_extended`。

### 2.5 觉（契约 5.2、5.4、⑨）

- `collect_scheduled(events, at, seeds, products, windows=None, caps=())`：加 `caps`，供 `qi_grant`、`scope_update` 读能力状态。
- 新家族 `qi_grant`（推进类，对象类型 `knowledge`）；`knowledge_conflict` 家族加模板 `qi_review`；`scope_update` 的对象改为「待批准的适用能力」。家族数 19 → 20，`auto_action` 仍只有 `escalate`、`assign_sales`。
- `jue/records.py` 新增只读投影 `decision_rows(records, events)` 与 `rows_for(rows, level)`。`JueRecord` 不变。
- 追问提示加探索比例 `thresholds.ask_explore`（演示与测试配置为 0）。

### 2.6 配置（契约 ⑪）与网关（契约 ⑩）

所有 `config/app*.yaml` 加：

```yaml
sources: []            # [{name, kind: public|internal|external, root, level?}]；替身 RAG 指向 seeds/rag/ 或决赛资料目录
qi_state: null         # 有效状态文件；演示、测试为 null（每次运行独立）；试点与决赛回放指向 data/qi/state.json
qi_maintainer: rd:R01  # 种子里没有归属人的现象，迁移时登记给谁
```

`points` 加 `used: 1`；`thresholds` 加 `ask_explore: 0`。新 caller `ingest:extract`；编译脚本自建网关并关闭缓存（`cache_dir = None`），不另写模型配置。

### 2.7 门面（契约 ⑫）与 Agent（契约 ⑭）

- 新增：`confirm_claims(req_id, ku_ids, by)`、`sign_qi_grant(question_id, by, claim_ids=(), note="")`、`revoke_capability(cap_id, by)`、`withdraw_claim(ku_id, by)`、`set_doc_level(doc_id, level, by)`、`recheck_evidence()`、`capabilities(viewer_id)`；
- 改：`decline_project(..., applicable_product=None, claim_ids=())` 不再要求相容，改为提议一个完整情境；`extend_scope` 改为批准待批准的适用能力；`decide_decrypt` 写 `decrypt` 能力；`adopt_reuse` 的审定说明写 `statement`（授予业务员层）；`resolve` 处理 `knowledge_conflict` 与 `qi_review`；`app.grants` 改为 `kb.decrypt_grants()` 的只读属性；
- 门面内部按「代谁」取视图（设计第 4 节规则一的表）；`self.seeds` 只用于标签、问法、抽取词表；
- Agent 工具 `search_knowledge` 改调 `explore`；写给下层的文字里，专业结论只写 `[[编号]]`。

### 2.8 文档

`docs/CONTRACTS.md` 同步以上各节；`AGENTS.md`：目录加 `src/huayan/ingest/`、`seeds/rag/`；铁律 4 补一句「引擎只读视图，行为只由能力驱动，跨层能力只来自人签的授予」；开头的阅读顺序加本文。

## 3. 工作包（按顺序，每包一个提交，可单独回退）

### Q0 契约与文档

`contracts/`、`docs/CONTRACTS.md`、`AGENTS.md`、`config/app*.yaml`

- 落第 2 节的全部定义；新字段都有默认值，现有代码不用改就能跑。
- 不写任何实现，不加模板（模板随实现它的包一起加，免得家族数先变）。

**验收**：`pytest` 11 个全绿；`git diff --stat` 只有契约、配置与文档。

### Q1 能力表、视图与情境匹配（第 0 天行为不变）

`knowledge/store.py`、`domain.py`、`app.py`、`l1/session.py`、`l1/answer.py`、`agent/tools.py`、`jue/state.py`、`jev/__init__.py`、`escalation/translate.py`、`ui/server.py`

- **能力表**：`KnowledgeBase` 加 `_caps: dict[str, Capability]`；`from_seeds(seeds, events, audit, *, maintainer, state_path=None)` 先 `migrate_seeds`，再加载状态文件（同 id 以文件为准）。
- **视图**：`view(actor)` 从种子的 L0 结构出发，按 `level_of(actor)` 取 `audience ≤ 层级` 的 `active` 能力，算出现象的 `required_slots`（保持种子顺序，新授予的追加在后）与 `slot_priors`、产品的 `situations` 与汇总的 `solves`/`applicable`；返回 `Seeds`。研发层视图里，现象的 `causes` 照旧；其余层置空。
- **唯一路径**：`products()` 改为 `view(研发).products`；`_products` 只存产品的名称、说明等基本记录，不再存适用。按设计规则一切换调用方：
  - 客户自助会话的追问、匹配、Jev 推荐、L1 回答 → 客户层视图；陪同会话 → 业务员层视图（`l1/session.py`、`l1/answer.py`、`app.ask_hints`）；
  - Agent 工具 `find_products` → 委托人那一层的视图；
  - 研发的开工门槛、回问（`requirement_state`、`readiness`、`_conditions`）→ 研发层视图；
  - 定时扫描、转译、失真评测 → `products()`。
- **情境匹配**：按 2.2 改 `consistent`、`match_candidates`、`correct_product`；`jev` 的提示里把 `applicable` 换成情境列表。
- **两个写入口改写能力**：`extend_scope` 在本包里先保持 V6 语义——给该产品加一个「新现象 × 原条件」的情境，立即生效；`resolve` 收窄说明书时，撤销含该取值的情境、加一个去掉该取值的副本。
- **有效状态**：`_save()` 在每次写入后把能力、`claim` 类结论、状态改过的结论、片段密级表整体写成 `{"version": n, ...}`（先写临时文件再改名）；`state_path` 为空时不写。
- **删除**：`update_applicable`、`extend_solves`、`l1/session.py::cite_scope` 与 `extend_scope` 生成的 `ku:translation:scope:*` 条目（记分由 Q2 的「被使用」接替；`app.py` 工作量统计里读这些 id 的地方改读 `scope_extended` 事件）。

**验收**：`pytest` 11 个全绿，断言不改；离线主线脚本的事件种类与计数、最终推荐、需求单状态与基线一致；全仓库没有对产品 `applicable`、`solves` 的写入，适用判断只在 `domain.py` 里读 `situations`。

### Q1.5 确认适用与可能适用（第一处有意的行为变化）

`domain.py`、`l1/session.py`、`app.py`、`jue/state.py`、`config/templates/scope_update.yaml`

- **有条件的推荐卡**：Jev 选中的候选是 `possible` 时，照常推荐，但卡片 `note` 由系统按情境写出待确认条件（「适用于设备为溢流染色机或卷染机，请确认您的设备」，取值用槽位的中文标签）；`recommend` 事件带 `status`、`capability_id`。追问与否仍由觉决定，不加「可能适用只能追问」的规则。
- **C′ 改为提议完整情境**：`decline_project(..., applicable_product, claim_ids=())` 不再要求 `consistent`；用需求单已知条件里属于该现象必问条件的那几项，组成情境 `{product, phenomenon, conditions: {slot: [value]}}`，`grant` 一条 `audience=0`、`status=proposed` 的适用能力。`claim_ids` 是研发勾选的结论，候选的在这里一并确认（`kb.confirm`）；没有勾选时，用不立项原因生成一条 L3 结论 `ku:claim:<req_id>`，确认人为 `by`。客户会话照旧收到该产品的推荐（这一张单是研发本人判的）。
- **`scope_update`**：对象改为每条 `proposed` 的适用能力（`knowledge:cap:<id>`），属性 `{product_id, value: 现象, conditions, n_applicable}`，前置条件 `attrs.pending`；`extend_scope` 改为 `kb.approve(cap_id, by)`，写 `scope_extended`（带 `capability_id`）。
- **删除**：Q1 里 `extend_scope` 的临时「新现象 × 原条件」写法。

**验收**：`test_wp_a1` 加「两个情境不交叉」「只知道部分条件为 possible、全知为 confirmed」；`test_e2e` 主线结果不变（主线里没有未知条件被推荐的情况；如有，只是卡片多一句待确认条件，断言按此更新并在提交说明里写明）。

### Q2 生效、撤销、记分与觉的两个新模板

`knowledge/store.py`、`knowledge/disclosure.py`、`app.py`、`jue/state.py`、`config/templates/qi_grant.yaml`、`config/templates/qi_review.yaml`、`agent/hub.py`、`ui/server.py`、`web/src/`

- **四条业务规则**（只在 `grant`、`confirm` 里各写一次）：`based_on` 的确认人都是 `granted_by`；`audience < 3` 时 `based_on` 里不能有 `formula`；只依据外部片段的结论不能 `confirm`；`form == "applicable"` 时 `approved_by` 为空就是 `proposed`。
- **传播**：`withdraw(ku_id)` 与 `evidence_changed(ku_id)` 把所有 `based_on` 含它的 `active` 能力置 `suspended`，写 `capability_suspended`；只此一个函数，不做规则引擎。
- **确认**：`confirm_claims(req_id, ku_ids, by)`：仅需求单的接单研发；候选结论变 `active`，`confirmed_by=by`；编译时为它提议的同层能力随之生效（适用类仍待批准）。
- **qi_grant**（新家族，`owner_role: rd`、`signer_role: rd`，不经 Agent 起草，问题卡直接列出形式、目标层、依据与原文位置）：
  - 对象 `knowledge:grant:<cap_id>|L<k>`：某条能力只在它的结论那一层生效，而更低的第 k 层需要过它；
  - 属性：`n_ask_back`（研发为同一现象回问同一槽位的次数：现有 `question_published` 事件里 `family=ask_back`、对象 `slot:<需求单>/<槽位>`，按需求单的现象聚合）、`n_unanswerable`（Q5 接上，本包为 0）、`granted`；
  - 前置 `not attrs.granted and (attrs.n_ask_back >= 2 or attrs.n_unanswerable >= 1)`，`rule_score` 取两者之和除以 3 封顶 1；
  - 签字 `sign_qi_grant`：复制该能力，`audience=k`、`granted_by=by`；依据还是候选的，由对齐产品或现象的归属研发签，签时一并确认；适用类转入 `scope_update`。
- **qi_review**（`knowledge_conflict` 家族新模板，`kind: anomaly`）：对象 `knowledge:claim:<ku_id>`，来自 `evidence_changed`、`claim_withdrawn`；签字人是确认人；`resolve` 里 `sign` = 保留（重新取指纹，恢复被挂起的能力），撤回走 `withdraw_claim`。
- **撤销**：`revoke_capability(cap_id, by)` 仅授予人；解密能力同样可撤。
- **解密进能力表**：`decide_decrypt` 通过时 `grant` 一条 `decrypt`（`audience=客户 id`、`approved_by` 不填、依据该产品的 `ku:mechanism`）；`app.grants` 改为只读属性 `self.kb.decrypt_grants()`，`disclosure.cap/render` 的签名与 `test_wp_a1` 的用法不变。
- **复用审定说明进能力表**：`adopt_reuse` 把 `customer_note` 写成一条授予业务员层的 `statement`；`view_session` 从能力表取这句话，撤销后不再显示。
- **被使用记分**：推荐命中的适用能力、本轮追问用到的 `ask` 能力、渲染用到的 `statement`，各写一条 `capability_used`，并给 `based_on` 的确认人记 `used` 分（同一会话同一能力只记一次）。现有「被引用」记分不动。
- **界面**：研发工作面加「我授予的能力」列表（状态、依据、撤销按钮）；需求单页列出本单相关的候选结论，可勾选确认；`qi_grant`、`qi_review` 用现有问题卡。HTTP 只加对应 2.7 门面方法的几个 `POST`。

**验收**：`test_wp_a3` 加：授予 → 客户被追问 pH；撤销 → 不再追问；撤销解密；撤销一个适用情境后客户、业务员、Agent 工具都不再推荐；撤回结论 → 能力挂起、觉提出 `qi_review`；适用能力未经产品经理批准不生效；依据他人结论的授予被拒；用同一个状态文件重建应用后授予与撤销都保留；被使用记分正确，被引用断言不变。`test_wp_b1`：家族数 20，`auto_action` 仍两种。

### Q3 出口：按编号渲染

`knowledge/disclosure.py`、`escalation/translate.py`、`l1/answer.py`、`agent/tools.py`、`prompts/`

- 按 2.3 实现 `render` 与 `leak_hits(..., audience=)`。
- **接两处真正由大模型写给下层的文字**：
  - L1 回答（`agent:l1_answer`）：提示词改为「专业内容只写 `[[编号]]`，编号来自给你的 hits」；回答先过 `render(text, 收件层)`，再过 `leak_hits(..., audience=收件层)`；任一不过，回「这部分需要专业人员解答」并记审计。离线模式现在是拼接 hits 原文，等价于渲染，不改。
  - 业务员 Agent 的回复草稿 `save_reply_draft`：同样先 `render(text, 0)`，再 `leak_hits(audience=0)`。
- 其余现有 `leak_hits` 调用点原样保留。

**验收**：`test_wp_t` 加：授予收件层的编号被换成原文，错层编号被拒；不传 `audience` 时 `leak_hits` 结果与现在逐条一致，传入后与上层结论重合的句子被拦截。

### Q4 依据与编译（替身 RAG）

`src/huayan/ingest/`（新）、`scripts/compile_qi.py`（新）、`seeds/rag/`（新，模拟）、`app.py`

- **替身 RAG**：`ingest/folder.py` 一个类 `FolderSource(name, kind, root, level=None)`：`list_docs()` 列出文件，`fetch(doc_id, span)` 按段号取段落，`search(query, k)` 用现有二元组打分；片段密级按来源：公开 0、外部 0、内部取 `level` 或片段密级表，都没有就是 3。不读文件之外的任何东西。
- **编译** `ingest/compile.py`，三个函数：
  - `propose(fragments, gateway)`：经网关（caller `ingest:extract`）让模型从片段里提出结论，每条带引文与对齐建议（现象、槽位取值、产品、形式）；
  - `admit(proposals, sources)`：用 `fetch` 核对引文确在原文里，查不到就丢；结论 `status=candidate`、`level` = 所依据片段的最高密级、`evidence` 只存位置与指纹；按设计第 5 节第二段用 `find_phenomenon`、`find_slot_values` 对齐，生成同层的能力提议；与现有能力完全相同的丢弃、取值冲突的列入报告；
  - `recheck(kb, sources)`：逐条 `fetch` 依据并比指纹，取不回或对不上就 `kb.evidence_changed`。
- **脚本** `scripts/compile_qi.py --state <file> [--proposals <yaml>]`：清点所有 `list_docs()` 的文档 → `propose`（给了 `--proposals` 就读录制好的提议，不调模型）→ `admit` → 写入状态文件 → 写 `data/ingest/report.md`（查询、片段、候选、提议、冲突、按设计第 9 节分类的待签数）。
- **模拟资料** `seeds/rag/public/LV205.md`、`seeds/rag/internal/RPT-031.md`、`seeds/rag/internal/RPT-044.md`，以及录制的提议 `seeds/rag/proposals.yaml`（全部标「模拟」）。决赛原始资料放 `data/finals/`，与由它编译出的一切都不入库。
- 门面 `recheck_evidence()`、`set_doc_level()`；`HuayanApp.build` 按 `config["sources"]` 建适配器。

**验收**：`test_wp_a3` 里用 `seeds/rag` 的临时副本：`admit` 产出的候选不进入任何更低层的视图；只依据外部片段的结论不能确认；改动 RPT-044 一段文字后 `recheck` → K5 挂起、觉提出 `qi_review`。不调模型。

### Q5 分层召回

`knowledge/store.py`、`agent/tools.py`、`l1/answer.py`、`jue/state.py`

- `explore(query, actor)`（只读，四步，每步几行）：
  1. 用全部转化对照把查询往上扩展（扩展词只在内部用）；
  2. 用 `_rank` 在全部结论里找，再经适配器查片段、按 `evidence` 的 `doc_id` 接回结论；
  3. 命中结论本层可读且已确认 → `units`；授予本层的、`based_on` 含命中结论的能力 → `capabilities`；命中但本层没有能力 → 记入 `unanswerable_ku_ids`，内部各层给存根（与 `search_blocked` 相同），客户层什么都不给；
  4. 提示只从本层视图算：查询里出现本层视图的槽位取值、现象或已发布产品时，给「相关条件：设备」「相关产品：HY-LV205」。
  写一条 `retrieve` 事件（payload 同 `search`，加 `unanswerable_ku_ids`、`n_unanswerable`）。研发层另带本层候选，标「候选」。
- Agent 工具 `search_knowledge` 改调 `explore`；`l1/answer.py` 的检索改调 `explore`，用 `units`。`search` 本身不变。
- `qi_grant` 的 `n_unanswerable` 从 `retrieve` 事件按「结论 × 提问者层级」计数。

**验收**：`test_wp_l` 加：客户层命中上层时的返回与「没找到」完全相同；L1、L2 只拿到本层内容、能力、提示与存根，不出现 L3 原文。

### Q6 决策投影（觉自进化的燃料）

`jue/records.py`、`app.py`

- `decision_rows(records, events)`：一行 = 决策点、当时属性与 `p_need`、谁、怎么处置、后来的结果（退回、试样、市场评价、复用拒绝、不立项）、用到的能力；`level` = 做决定的人的层级与所引内容层级取高。纯函数，不落盘。
- `rows_for(rows, level)`：只留 `level ≤ k` 的行（觉为第 k 层学习时只用这些）。
- 追问提示探索：低于阈值的点，按 `hash(session_id, slot)` 取 `ask_explore` 比例照样提示，`ask_hint` 事件标 `explore: true`；演示与测试配置为 0，所以行为不变。
- 不改 Jue-K 的训练数据与模型（仍用模拟轨迹，见设计第 10 节「怎么评估」）。

**验收**：`test_wp_b1` 加：决策投影的行与层级正确；`rows_for(rows, 0)` 里没有高于客户层的行。

### Q7 决赛主演示与 V6 对照

`scripts/demo_qi.py`（新）、`scripts/compare_v6_qi.py`（新）、`config/app.demo.qi.yaml`（新）、`docs/reports/qi_demo/`、`README.md`、`docs/VISION.md`、`docs/PITCH.md`、设计文档第 12 节

- **`demo_qi.py`**（离线配置，状态文件放本次运行目录）：
  1. 编译 `seeds/rag`（录制的提议）；
  2. 三态：同一句客户话「锦氨在经轴缸上染出来深一块浅一块」，A 未授予（R01 已确认 C4，只在研发开工门槛要求 pH）→ B R01 签 `qi_grant` 授予 K3 → C 撤销 K3，记录每一态客户是否被追问 pH、问原理时得到什么；
  3. 四步：C05 → C07 → C08 与「只说锦纶氨纶」→ 撤销 K5 / 改 RPT-044 后 `recheck_evidence`；
  4. 重启：用同一个状态文件重建应用，重放 C07 的问题。
  每一步的结论从事件日志读出，写进 `docs/reports/qi_demo/demo.json` 与一页 `demo.md`，不写死文案。
- **`compare_v6_qi.py`**：一批按时间排序的模拟问题（含 C05、C07、C08 的同类问题若干），分别在契与 V6 基线（`git worktree add <dir> 351c2c9` 后用该目录运行同一脚本）上跑一次；研发的处置按脚本里写定的「研发判断」执行，V6 里 `decline_project` 因相容检查报错时，按 V6 的真实做法改为不带产品的不立项。五个指标都从两边的事件日志统计：正确的自助处理数、研发重复参与次数、未经授权的确定推荐数（确定推荐没有落在研发判断写定的任何完整情境内）、撤销或失效后的行为、重启后的授权状态。报告写进 `docs/reports/qi_demo/compare.md`，注明数据为模拟、处置为脚本写定。
- **材料**：按 1.1 更新设计第 12 节与 PITCH 的演示台词；VISION 1.2 证据表里已实现的行改为「已实现」并指向测试与报告；README 加一节「契」（三句话 + 演示命令 + 报告链接）。

**验收**：两个脚本在离线配置下从头跑通；报告里的数字能用事件日志复算。

### Q8 独立审查

照 V6-3.1：由一个没参与实现的子代理只读审查，对照 AGENTS.md 铁律、本文第 0.2 节与设计第 13 节「边界与措辞」。重点查：有没有绕开视图读种子做判断的地方；有没有能力之外改变下层行为的写入；有没有防御代码和只为测试存在的分支；Agent 能否写出不经渲染的专业结论。阻断与应修项按最小修改修复，不新增测试、不改契约，结果补进本节。

## 4. 测试：仍是 11 个，场景写进现有测试函数

| 测试 | 新增场景 | 所在包 |
|---|---|---|
| `test_wp_a1` | 两个情境不交叉；部分条件为 possible、全知为 confirmed；配方不能作下层依据；候选不进更低层视图；未授予的 L3 结论不改变客户层视图 | Q1.5、Q2、Q4 |
| `test_wp_t` | `render` 换编号与拒错层编号；`leak_hits` 不传 `audience` 逐条不变，传入后拦截上层结论 | Q3 |
| `test_wp_l` | `explore` 客户层无存根无提示；L1/L2 只得本层 | Q5 |
| `test_wp_a3` | 授予/撤销追问；撤销解密；撤销情境后各调用方不再推荐；挂起与复核；批准；依据他人结论被拒；重启保留；被使用记分；编译与指纹 | Q2、Q4 |
| `test_wp_b1` | 家族数 20；`auto_action` 两种；决策投影与层级过滤 | Q2、Q6 |
| `test_e2e` | 第 0 天迁移后主线结果不变 | Q1 |

测试里的适配器用 `seeds/rag` 的临时副本，不新造桩；桩仍只有 `MockGateway`、`MockSystem1Client` 和 `mini_seeds`。四步演示由 Q7 的脚本证明，不进测试。

## 5. 检查点

| 完成 | 必须成立 |
|---|---|
| Q1 | 11 个全绿且断言不改；离线主线与基线一致；`update_applicable`、`extend_solves` 已删除 |
| Q1.5 | 「锦纶氨纶 × 经轴」可被研发授予并经产品经理批准；只给部分条件时卡片列出待确认条件 |
| Q2 | 三态在测试里成立；重启保留 |
| Q4 | `compile_qi.py --proposals seeds/rag/proposals.yaml` 跑通；改一段原文即挂起 |
| Q7 | 两份报告生成；VISION 1.2 的状态更新 |

任何一个检查点不成立，先修，不往下做。

## 6. 不做

- `phrase` 的入口与业务员说法授予（1.2）；`translation` 建行（同层直接用）。
- `public_points` 建 `statement` 行：发布前不对外，发布后随说明书成为 L0 结论。
- Jev 第三问（依据核对）接入 `scope_update`；`qi_grant` 由 Agent 起草。
- 增量编译、热加载、原文快照、在 RAG 侧写标签、让模型定级或建议降密、遍历企业 RAG 全库。
- 用决策投影重训 Jue-K；报告模拟业务周的「越用越准」。
- V6 兼容开关：V6 对照用基线的 worktree 跑，代码里不留旧语义。
- 种子改动后的状态文件合并（状态文件以 id 覆盖迁移结果；改种子后由人删除或复核状态文件）。
