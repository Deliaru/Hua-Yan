# REPLAN-v7｜契落地

> 2026-10-19。代码基线：`main` @ `351c2c9`（V6 完成态）。设计依据：`docs/QI.md`（契 v3.3 设计文档，下称「设计」）、`docs/VISION.md` 第 1 节、`docs/PITCH.md` 第 6.1 节。
> **第 2 节的契约改动已由人批准**（含 2.8 的两处与 v7.2 新增的续跑、`ingest:draft`），之后冻结；实施中需要再改契约，先停下来问人。
> 本文与 `REPLAN-v6.md` 冲突处以本文为准。不标耗时。
> v7.1（同日）：按独立审查的 25 条意见修订，修订记录见第 7 节。
> v7.2（同日）：补上真实运行的两个缺口——从企业资料起草种子（Q4.5）、应用可续跑（Q6.5），见第 1.4 节。
> v7.3（同日）：人已批准全部契约改动（含 2.8 与 v7.2 新增）；按愿景逐条审核，修正 5 处偏离，见第 9 节。

## 0. 目标与写法

### 0.1 做完是什么样

1. **第 0 天行为不变**：现有种子迁成结论与能力后，11 个测试全绿，离线主线（`scripts/demo_mainline.py`）的推荐、升级、需求单状态与基线一致；失真对照、业务周的数字不重跑也不变。
2. **决赛主演示在离线配置下真实跑出**：三态（未授予 / 已授予 / 已撤销）、四步能力复用、重启后状态保留，以及与 V6 在同一批问题上的对照，数字全部从事件日志统计。
3. **VISION 1.2 节里标「设计完成」的几条主张变成「已实现」**，证据指向测试与演示报告。
4. **真实运行能起步、能续跑**：拿一家企业的资料，能起草出种子由人审定后启动；应用重启后会话、需求单、问题、积分、知识与能力都接着用（第 1.4 节）。

### 0.2 防止屎山的六条写法（每个包都要守）

1. **一张能力表，一条读路径。** 能力存在知识库里；引擎读知识只走 `kb.view(actor)`。删掉 `update_applicable`、`extend_solves`；视图里的产品不再带汇总的 `applicable`，任何适用判断只看 `situations`。不保留「旧字段 + 新能力」两套判断。
2. **视图就是种子形状。** `view(actor)` 返回现有的 `Seeds` 对象，引擎函数签名不变；调用方只是把 `self.seeds` / `kb.products()` 换成对应层的视图。不新造一套视图类型。
3. **只有驱动行为的能力建行。** 能力表只放四种形式：`ask`、`applicable`（各层都建行，包括同层：研发确认结论后，它在研发层的追问与适用随之生效）、跨层的 `statement`、`decrypt`。`translation` 只在同层使用，`statement` 的同层使用就是读已确认的结论，这两种同层情况都不建行；`phrase` 见 1.2。
4. **没有新框架。** 不写规则引擎、不做事件溯源、不做插件注册；替身 RAG 就是一个读文件夹的类。传播（依据 → 结论 → 能力）是数据上的引用，写成一个函数。
5. **只校验业务规则，不写防御代码。** 要校验的只有设计里的规则：授予人必须是所依据结论的确认人；配方不能作下层依据；只依据外部片段的结论不能确认；适用能力要产品经理批准；候选结论不跨层、也不经 `search`/`get`/`list` 读出。设计的第三条结构约束「只依据系统自身决定的结论不能成为能力」本轮由结构保证：结论只来自编译和研发本人，没有从决策记录生成结论的路径。内部调用之间不加 `isinstance`、不加兜底 `try`。
6. **每包一个提交，删的和加的一样多。** 每个包写明删什么；包结束时 `pytest` 11 个全绿；原子工具仍不超过 15 行；不先写后删。

## 1. 落地前的三处校正

### 1.1 演示数据换成 LV205（设计第 12 节的例子不能直接用）

设计第 12 节用 LV206 讲例子，和现有种子冲突两处：

- `HY-LV205` 已经覆盖「锦纶 × 溢流染色机」，所以「客户 C05 纯锦纶 × 溢流色花 → 客户层没有候选」不成立；
- `HY-LV206` 在种子里是 `status: project`，V6 主线和 `test_wp_a3` 都依赖它未发布；运行期发布的产品重启后也不会保留，K5 跨重启的演示不成立。

**改为用已发布的 `HY-LV205`（归属研发 R01），研发角色统一为 R01：**

| 编号 | 内容 | 来源 |
|---|---|---|
| 公开情境（第 0 天迁移） | LV205 × 色花 × {锦纶, 锦纶氨纶} × {溢流染色机, 卷染机} | 种子，即产品页 |
| K3 ask | 色花 × 染浴 pH：要追问 | R01 确认的 C4（依据 RPT-031，模拟） |
| K5 applicable | LV205 × 色花 × {锦纶氨纶} × {经轴染色机} | R01 确认的 C2（依据 RPT-044，模拟） |

四步演示：C05「锦纶氨纶 × 经轴染色机」→ 无候选，进研发，R01 依据 RPT-044 判 LV205 适用并授予 K5，产品经理批准；C07 同样条件 → 前台确认适用直接推荐；C08「锦纶 × 经轴染色机」→ 不是候选，照常进研发；另一位客户只说「锦纶氨纶」没说设备 → LV205 可能适用，卡片列出「设备为溢流染色机、卷染机或经轴染色机，请确认」；撤销或依据失效后回到研发，重启后状态保留。（已核对：色花下已发布的只有 LV101、LV120、LV205，没有别的产品会意外命中。）

两条要讲清的边界：

- V6 的 `decline_project` 要求所选产品与客户已知条件相容（`app.py:582`），LV205 不含经轴，所以 R01 的判断在 V6 里**根本记不下来**，C07、C08 每次都进研发。
- `ask` 不带条件：授予 K3 后，**所有色花客户**都会被问 pH，不只锦氨 × 经轴。演示台词按此讲，报告写为本轮表达能力的边界。

测试不用这组数据，用 `mini_seeds` 自己构造（见第 4 节）；PITCH 第 6.1、7.5 节里「锦氨 × 气流 / 纯锦纶 × 溢流」描述的是测试场景，保持不变。`docs/QI.md` 第 12 节和 PITCH 的演示台词在 Q7 按本节更新。

### 1.2 `phrase` 本轮没有入口

V6 没有「业务员改正槽位」的入口，新加这个入口不在落地主线上。`phrase` 留在形式枚举里，本轮不建行、不加入口；客户说法仍来自种子（种子说法本来就是 L0 结论）。设计第 9 节的第②类签字量在报告里写「未实现」。

### 1.3 适用的批准走 C′ 原路，不加新事件

研发授予适用情境 → 能力处于 `proposed` → 觉提出 `scope_update` → 产品经理在现有 `extend_scope` 里签字 = 批准，能力变 `active`，复用现有的 `scope_extended` 事件。`qi_grant` 授予出的适用能力也走这条路。不需要产品经理批准的只有两类，`approved_by` 直接写明：第 0 天迁移的（`"seed"`）、发布时生成的（发布签字人），以及由系统收窄出的副本（沿用原情境的批准人）。

### 1.4 真实运行的两个缺口

计划原先的「第 0 天」指**在已有的化言上打开契的那一刻**：种子结构（槽位、现象、产品）已经在，迁移把它登记成结论与能力。这对演示成立，对一家新企业不成立，而且化言本身每次启动都是新的运行。两个缺口：

1. **种子从哪来。** 现在的 `seeds/*.yaml` 是手写的模拟数据。真实企业没有这份东西；而编译只能把结论对齐到已有的槽位、现象和产品上，新产品、新概念只进报告，没有任何路径生成产品记录。→ **Q4.5 接入起草**：从企业的公开资料起草产品目录与词表草稿，人逐条审定后作为该企业的种子目录启动。系统只起草，生效仍是人。
2. **重启后工作丢失。** `HuayanApp.build` 每次新建运行目录（`app.py:66-68`，`exist_ok=False`），会话、需求单、问题、积分只在内存里有效；运行期发布的产品、沉淀的转化知识、试样记录也随之丢失。其实这些对象每次变化时已经写进了运行目录（`sessions/`、`requirements/`、`events.jsonl`、`questions.jsonl`、`ledger.jsonl`、`audit.jsonl`），只是没有读回来的路径。→ **Q6.5 可续跑**：用已有的运行目录启动时把它们读回来；知识与能力的部分全部归契的有效状态文件。

真实运行从零开始的流程（两个包做完之后）：

| 步 | 谁 | 做什么 |
|---|---|---|
| ① 接入配置 | 企业 IT + 项目组 | 写 `actors.yaml`（角色名单）；在配置里写 `sources`（公开 / 内部资料的位置）、`seeds_dir`（企业种子目录，放在 `data/` 下，不入库）、`qi_state`、`run_root` |
| ② 起草种子 | 系统 → 产品经理、研发 | `scripts/draft_seeds.py` 从公开资料起草产品目录与词表草稿；产品经理改产品与适用范围，研发改必问条件与机理字段（可留空），确认后放进企业种子目录 |
| ③ 首次启动 | 系统 | 加载种子 → 第 0 天迁移 → 状态文件为空，写出第 1 版 |
| ④ 首次编译 | 系统 → 产品经理 | `compile_qi.py` 清点全部资料，候选写进状态文件，报告列出待签数；产品经理按公开产品页核对适用情境，研发不用签 |
| ⑤ 日常运行 | 各岗位 | 客户自助读客户层视图；升级的需求进研发，研发签需求单时勾选候选；下层反复需要时觉提出 `qi_grant`；每次签字写入状态文件 |
| ⑥ 重启 | 系统 | 用同一个运行目录与状态文件启动，工作与知识原样接上 |
| ⑦ 定期重编译 | 系统 → 确认人 | 比对依据指纹，原文变了的能力挂起，觉提出 `qi_review` |

## 2. 契约变更（已批准，之后冻结）

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
```

| form | payload | 第 0 天来源 |
|---|---|---|
| `applicable` | `{product_id, phenomenon, conditions: {slot: [values]}}` | 每个已发布产品的每个 `solves` 现象 × 原 `applicable`，一行 |
| `ask` | `{phenomenon, slot, required: true}` 或 `{phenomenon, slot, prior: {value: p}}` | 现象的 `required_slots`、`slot_priors` |
| `statement` | `{text, product_id?}` | 无（第 0 天的说明书、用法、公开案例是 L0 结论，同层直接用） |
| `decrypt` | `{product_id, session_id, text}` | 无（启动时没有解密授权） |

结论与能力的新编号（`ku:claim:<n>`、`cap:<n>`）取已加载的最大序号加 1，跨重启不冲突；不用需求单号做编号（需求单号每次运行从 1 开始）。

`LedgerEntry.reason` 加 `"used"`。`DecryptGrant` 保留，改为由 `decrypt` 能力投影出来的只读类型（`approved_by = granted_by`，`session_id` 取自 payload）。

`SourceAdapter` 不定义成协议：本轮只有一种适配器（替身 RAG 的 `FolderSource`），接入企业 RAG 时再按它的三个方法 `search`、`fetch`、`list_docs` 写第二个类。

`KnowledgeBase` 的接口变化：

- `from_seeds(seeds, events, audit, *, state_path=None)`：只加一个有默认值的参数，现有三参数调用不变；
- 新增 `view(actor) -> Seeds`、`products()`（= 研发层视图的产品，只供系统内部扫描与内部各层使用）、`explore(query, actor) -> ExploreResult`、`capabilities(...)`、`decrypt_grants() -> list[DecryptGrant]`；
- 新增写入：`confirm(ku_ids, by)`、`withdraw(ku_id, by)`、`grant(cap) -> Capability`、`approve(cap_id, by)`、`revoke(cap_id, by)`、`evidence_changed(ku_id)`；每次写入后整体保存有效状态；
- 删除：`update_applicable`、`extend_solves`；
- `search`、`search_blocked`、`get`、`list` 的签名不变；可读条件加一条「结论状态为 `active`」（候选只经 `explore` 的 `candidates` 给研发，撤回的不再可读）。

### 2.2 领域（契约 1.5，`contracts/seeds.py`、`domain.py`）

```python
class Situation(BaseModel):
    phenomenon: str
    conditions: dict[str, list[str]]     # 同时成立；未列出的槽位不限
    capability_id: str

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
- `match_candidates(phenomenon, known, products)`：签名不变；取该现象下与已知条件相容的情境，每个产品取未知条件最少的那个；无未知条件为 `confirmed`，否则 `possible`。
- `correct_product`：用命中情境里**限定的槽位个数**衡量具体程度（与 V6 的 `len(applicable)` 一致）。

### 2.3 出口（契约 7.1）

- 新增 `render_refs(draft, audience, kb) -> str`（`knowledge/disclosure.py`；现有的 `render` 是推荐卡片渲染，名字和签名都不动）：把稿子里的 `[[编号]]` 换成原文。编号可以是层级 ≤ 收件层的已确认结论，或授予收件层（及以下）的 `statement`；其余编号直接抛 `PermissionDenied` 并记审计。
- `leak_hits(text, sealed, hypotheses, kb, *, audience=None)`：不传 `audience` 时与现在逐条一致；传入时增加来源 `"claim"`：与层级高于收件层的已确认结论重合。

### 2.4 事件（契约 ⑧）

新增 `claim_confirmed`、`claim_withdrawn`、`capability_granted`、`capability_revoked`、`capability_suspended`、`capability_used`、`evidence_changed`。`retrieve` 的 payload 加 `unanswerable_ku_ids` 与 `n_unanswerable`。`recommend` 的 payload 加 `status` 与 `capability_id`。批准复用现有 `scope_extended`。

### 2.5 觉（契约 5.2、5.4、⑨）

- `collect_scheduled(events, at, seeds, products, windows=None, caps=())`：加 `caps`，供 `qi_grant`、`qi_review`、`scope_update` 读能力状态。
- 新家族 `qi_grant`（推进类）与 `qi_review`（异常类），对象类型都是 `knowledge`；`scope_update` 的对象改为「待批准的适用能力」。家族数 19 → **21**，`auto_action` 仍只有 `escalate`、`assign_sales`。两个新家族都没有 Jue-K 校准器，由模板 `rule_score` 打分并标 `scored_by: rule`（`jue_k.py` 现有处理）。
- `jue/records.py` 新增只读投影 `decision_rows(records, events)` 与 `rows_for(rows, level)`。`JueRecord` 不变。

### 2.6 配置（契约 ⑪）与网关（契约 ⑩）

所有 `config/app*.yaml` 加：

```yaml
sources: []            # [{name, kind: public|internal|external, root, level?}]；替身 RAG 指向 seeds/rag/ 或决赛资料目录
qi_state: null         # 有效状态文件；为 null 时用 <运行目录>/qi_state.json（每次新运行独立）；试点与决赛回放指向 data/qi/state.json，多次运行共用
```

有效状态文件的内容（v7.2 扩大）：能力、`claim` 类结论、状态改过的结论、片段密级表、两个序号，**以及运行期新增的全部知识**（`source` 不是 `seed` 的知识单元：发布的产品说明、沉淀的转化知识、试样、公开案例之外的贡献）**和运行期发布的产品记录**。知识与能力的持久化只此一处。

`HuayanApp.build(config_path, run_id=None, byok=None, *, resume=False)`：`resume=True` 时 `run_id` 必须指向已有的运行目录，按 Q6.5 读回；默认行为不变。`EventLog`、`QuestionBus`、`AuditLog`、`Ledger` 的构造在文件已存在时读回已有记录（新增的只有这一个行为）。

`points` 加 `used: 1`。新 caller `ingest:extract`；编译脚本自建网关并关闭缓存（`cache_dir = None`），不另写模型配置。

### 2.7 门面（契约 ⑫）与 Agent（契约 ⑭）

- 新增：`confirm_claims(req_id, ku_ids, by)`、`sign_qi_grant(question_id, by, claim_ids=(), note="")`、`revoke_capability(cap_id, by)`、`withdraw_claim(ku_id, by)`、`set_doc_level(doc_id, level, by)`、`recheck_evidence()`、`capabilities(viewer_id)`；
- 改：`decline_project(..., applicable_product=None, claim_ids=())` 不再要求相容，改为提议一个完整情境；`extend_scope` 改为批准待批准的适用能力；`release_product` 同时授予新品的适用情境；`decide_decrypt` 写 `decrypt` 能力；`adopt_reuse` 的审定说明写 `statement`（授予业务员层）；`save_reply_draft` 先过 `render_refs` 与 `leak_hits(audience=0)`；`resolve` 处理 `qi_review`；`app.grants` 改为 `kb.decrypt_grants()` 的只读属性；
- 门面内部按「代谁」取视图（设计第 4 节规则一的表）；`self.seeds` 只用于标签、问法、抽取词表，以及读立项产品；
- Agent 工具 `search_knowledge` 改调 `explore`；写给下层的文字里，专业结论只写 `[[编号]]`。

### 2.8 独立审查后的两处修正（已批准）

1. **`qi_review` 做成独立家族，不放进 `knowledge_conflict`。** 设计原写「`knowledge_conflict` 家族的新模板」，但 `jue/proto.py:20-22` 与 `docs/CONTRACTS.md` 第 623 行规定「每个 family 只有一个模板」，`resolve` 也按 family 决定允许的动作。所以 `qi_review` 单列为家族，家族数 21。
2. **出口渲染函数叫 `render_refs`，不叫 `render`**：`disclosure.render` 已是推荐卡片渲染，`test_wp_a1` 在用。

### 2.9 文档

`docs/CONTRACTS.md` 同步以上各节；`AGENTS.md`：目录加 `src/huayan/ingest/`、`seeds/rag/`、`tests/fixtures/mini_seeds/rag/`；铁律 4 补一句「引擎只读视图，行为只由能力驱动，跨层能力只来自人签的授予」；开头的阅读顺序加本文与 `docs/QI.md`；第 5 节测试表按第 4 节更新。

## 3. 工作包（按顺序，每包一个提交，可单独回退）

### Q0 契约与文档

`contracts/`、`docs/CONTRACTS.md`、`AGENTS.md`、`config/app*.yaml`、`docs/QI.md`

- **设计文档入库（已完成）**：契 v3.3 设计从 Claude Docs 导出为 `docs/QI.md`，架构图改为 Mermaid；文首注明以本文为实现依据，第 12 节加注 1.1 的数据校正。本包再在文首的说明里逐条列出本文与设计不同的地方（第 7 节「与设计的差异」）。之后改设计只改这份文件。
- 落第 2 节的全部定义；新字段都有默认值，现有代码不用改就能跑。
- 不写实现，不加模板（模板随实现它的包一起加，免得家族数先变）。

**验收**：`pytest` 11 个全绿；`git diff --stat` 只有契约、配置与文档。

### Q1 能力表、视图与情境匹配（第 0 天行为不变）

`domain.py`、`knowledge/store.py`、`escalation/flow.py`、`escalation/translate.py`、`app.py`、`l1/session.py`、`l1/answer.py`、`agent/tools.py`、`jue/state.py`、`jev/__init__.py`、`ui/server.py`

- **情境**：`load_seeds` 填第 0 天情境；按 2.2 改 `consistent`、`match_candidates`、`correct_product`；本包里 `Candidate.status` 已算出，但没有任何调用方读它。
- **能力表**：`KnowledgeBase` 加 `_caps`；`from_seeds` 先 `migrate_seeds`，再加载状态文件（同 id 以文件为准）。
- **视图**：`view(actor)` 按 `level_of(actor)` 取 `audience ≤ 层级` 的 `active` 能力，算出现象的 `required_slots`（保持种子顺序，新授予的追加在后）与 `slot_priors`、产品的 `situations`；研发层视图的 `causes` 照旧，其余层置空；返回 `Seeds`。
- **唯一路径**：`products()` 改为研发层视图的产品；`_products` 只存产品的名称、说明等基本记录。按设计规则一切换调用方：
  - 客户自助会话的追问、匹配、Jev 推荐、L1 回答 → 客户层视图；陪同会话 → 业务员层视图（`l1/session.py`、`l1/answer.py`、`app.ask_hints`）；
  - Agent 工具 `find_products` → 委托人那一层的视图；
  - 研发的开工门槛、回问（`requirement_state`、`readiness`、`_conditions`）→ 研发层视图；
  - 定时扫描、转译、失真评测 → `products()`。
- **原来读 `applicable` 的地方改读情境**（视图里不再有汇总字段）：`jue/state.py` 的相关槽位与 `claimed`（某个情境在该槽位上列了这个取值）、`app.py` `route_of` 的「被排除的产品」（`not consistent`）、`escalation/translate.py` 的相关产品（`consistent`）、`escalation/flow.py` 的事件载荷、`jev` 的提示（情境列表）。`sim/` 读的是种子原字段，不动。
- **写入口全部改写能力**：
  - `extend_scope`：`grant`「新现象 × 原条件」的情境，并由签字的产品经理 `approve`——这就是 Q1.5 之后的通用路径，Q1.5 只改「情境条件从哪来」，不先写后删；
  - `resolve` 收窄说明书：撤销含该取值的情境，加一个去掉该取值的副本，`approved_by` 沿用原情境；
  - `release_product`（`escalation/flow.py`）：按新品的情境各 `grant` 一条 `audience=0` 的适用能力，`granted_by` 为产品归属研发，`approved_by` 为发布签字人；新品记录写进有效状态，重启后照常存在。
- **有效状态**：每次写入后把 2.6 列出的内容整体写成 `{"version": n, ...}`（先写临时文件再改名）；`kb.add`、`add_product` 也算写入；`state_path` 为空时不写（只有直接构造知识库的测试与脚本如此，应用总有路径）。
- **删除**：`update_applicable`、`extend_solves`。（`cite_scope` 在 Q2 与它的替代一起删。）

**验收**：`pytest` 11 个全绿，断言不改；在 `351c2c9` 的 worktree 与本包上各跑一次离线主线，事件种类与计数、最终推荐、需求单状态一致；`grep -rn "\.applicable" src/huayan` 只剩 `domain.py::load_seeds` 与 `sim/`。

### Q1.5 确认适用与可能适用（第一处有意的行为变化）

`l1/session.py`、`app.py`、`jue/state.py`、`jue/publish.py`、`config/templates/scope_update.yaml`

- **有条件的推荐卡**：Jev 选中的候选是 `possible` 时，照常推荐，但卡片 `note` 由系统写出待确认条件：取该产品在本现象下所有相容情境的未知条件，按槽位合并取值（「设备为溢流染色机、卷染机或经轴染色机，请确认」，用槽位的中文标签）；`recommend` 事件带 `status`、`capability_id`。追问与否仍由觉决定，不加「可能适用只能追问」的规则。
- **C′ 改为提议完整情境**：`decline_project(..., applicable_product, claim_ids=())` 不再要求 `consistent`；用需求单已知条件里属于该现象必问条件的那几项组成情境，`grant` 一条 `audience=0`、`status=proposed` 的适用能力。`claim_ids` 是研发勾选的结论，候选的在这里一并确认；没有勾选时，用不立项原因生成一条 L3 结论 `ku:claim:<n>`，确认人为 `by`。客户会话照旧收到该产品的推荐（这一张单是研发本人判的）。
- **`scope_update`**：对象改为每条 `proposed` 的适用能力（`knowledge:cap:<id>`），属性 `{product_id, slot: "phenomenon", value: 现象, conditions, n_applicable, pending}`，前置条件 `attrs.pending`；`publish.py` 的 `_refs` 对这类对象写入 `capability_id` 与真实的 `product_id`；`extend_scope` 改为 `kb.approve(q.refs["capability_id"], by)`，写 `scope_extended`（带 `capability_id`）。
- **删除**：Q1 里 `extend_scope` 的「新现象 × 原条件」取法（`grant + approve` 的路径保留）。

**验收**：`test_wp_a1` 加「两个情境不交叉」「部分条件为 possible、全知为 confirmed」；`test_e2e` 主线结果不变（如有未问全被推荐的情况，只是卡片多一句待确认条件，断言按此更新并在提交说明里写明）；`scripts/demo_routes.py` 的 C、C′ 路线照常跑通。

### Q2 生效、撤销、记分与觉的两个新家族

`knowledge/store.py`、`knowledge/disclosure.py`、`app.py`、`l1/session.py`、`jue/state.py`、`jue/publish.py`、`config/templates/qi_grant.yaml`、`config/templates/qi_review.yaml`、`agent/hub.py`、`ui/server.py`、`web/src/`、`scripts/demo_routes.py`

- **四条业务规则**（只在 `grant`、`confirm` 里各写一次）：`based_on` 的确认人都是 `granted_by`；`audience < 3` 时 `based_on` 里不能有 `formula`；只依据外部片段的结论不能 `confirm`；`form == "applicable"` 且 `approved_by` 为空就是 `proposed`。
- **传播**：`withdraw(ku_id)` 与 `evidence_changed(ku_id)` 把所有 `based_on` 含它的 `active` 能力置 `suspended`，写 `capability_suspended`；只此一个函数。
- **确认**：`confirm_claims(req_id, ku_ids, by)`：仅需求单的接单研发；候选结论变 `active`，`confirmed_by=by`；为它提议的能力随之生效（适用类仍待批准）。
- **qi_grant**（新家族，`owner_role: rd`、`signer_role: rd`）有两种对象：
  - `knowledge:grant:<cap_id>|L<k>`：某条追问或适用能力只授予了它的结论那一层，而更低的第 k 层需要过它。形式与目标都能算出，不经 Agent 起草，问题卡直接列出形式、目标层、依据与原文位置；
  - `knowledge:grant:<ku_id>|L<k>`：某条已确认结论在第 k 层被检索命中、却没有任何能力（Q5 的「本层无能力」），要授予的是一句**可说的话**（`statement`）。措辞由确认人的研发 Agent 照现有准备流程起草（附那一层被问到的原话、结论原文位置），研发改定后签字；草稿先过 `leak_hits(audience=k)`。这是「研发授权一句话给前台说，前台看不到机理」的通用入口；
  - 属性 `{product_id, slot, value, n_ask_back, n_unanswerable, granted}`：`n_ask_back` 是研发为同一现象回问同一槽位的次数（现有 `question_published` 事件里 `family=ask_back`、对象 `slot:<需求单>/<槽位>`，按需求单的现象聚合）；`n_unanswerable` 在 Q5 接上，本包为 0；
  - 前置 `not attrs.granted and (attrs.n_ask_back >= 2 or attrs.n_unanswerable >= 1)`，`rule_score` 取两者之和除以 3 封顶 1；
  - 签字人：所依据结论的确认人；结论还是候选的，取对齐产品的归属研发，签时一并确认。`publish.py` 的 `_resolve` 从 `refs["signer"]` 读签字人，不再按 `product_id` 推断；
  - `sign_qi_grant`：第一种复制该能力，`audience=k`、`granted_by=by`，适用类转入 `scope_update`；第二种按研发改定的措辞新建一条 `statement`。
- **qi_review**（新家族，`kind: anomaly`）：只由 `evidence_changed` 触发（撤回结论的人就是授予人，不再给他发复核）；对象 `knowledge:claim:<ku_id>`，签字人是确认人；`resolve` 里 `sign` = 保留（重新取指纹，恢复被挂起的能力），撤回走 `withdraw_claim`。
- **撤销**：`revoke_capability(cap_id, by)` 仅授予人；解密能力同样可撤。
- **解密进能力表**：`decide_decrypt` 通过时 `grant` 一条 `decrypt`（`audience=客户 id`、payload 带 `session_id`、依据该产品的 `ku:mechanism`）；`app.grants` 改为只读属性 `self.kb.decrypt_grants()`，`disclosure.cap/render` 的签名与 `test_wp_a1` 的用法不变。
- **复用审定说明进能力表**：`adopt_reuse` 把 `customer_note` 写成一条授予业务员层的 `statement`；`view_session` 从能力表取这句话，撤销后不再显示。
- **被使用记分（替代 `cite_scope`）**：推荐命中的适用能力、本轮追问用到的 `ask` 能力、渲染用到的 `statement`，各写一条 `capability_used`，给 `based_on` 的确认人记 `used` 分；适用能力另给批准它的产品经理记一份（第 0 天的 `"seed"` 不记）。同一会话同一能力只记一次。同时删除 `l1/session.py::cite_scope` 与 `extend_scope` 生成的 `ku:translation:scope:*` 条目；`app.py` 工作量统计里「同类需求客户自助解决」「此后因此自动解决的需求」改为数这些能力的 `capability_used`。**记分对象有变化**：C′ 之后的复用由作出判断的研发和批准范围的产品经理各记一份「被使用」，V6 里只记产品经理的「被引用」；`demo_routes.py` 的 C′ 断言与 `docs/reports/v6_routes/` 按此更新。现有「被引用」记分的其余部分不动。
- **界面**：研发工作面加「我授予的能力」列表（状态、依据、撤销按钮）；需求单页列出本单相关的候选结论，可勾选确认；`qi_grant`、`qi_review` 用现有问题卡。HTTP 只加对应 2.7 门面方法的几个 `POST`。

**验收**（测试数据直接用 `kb.confirm`、`kb.grant` 在 `mini_seeds` 上构造，不依赖 Q4 的编译）：`test_wp_a3` 加：授予 → 客户被追问；撤销 → 不再追问；撤销解密；撤销一个适用情境后客户、业务员、Agent 工具都不再推荐；适用能力未经产品经理批准不生效；依据他人结论的授予被拒；用同一个状态文件重建应用后授予与撤销都保留；被使用记分正确，被引用断言不变。`test_wp_b1`：家族数 21，`auto_action` 仍两种。

### Q3 出口：按编号渲染

`knowledge/disclosure.py`、`escalation/translate.py`、`l1/answer.py`、`app.py`、`prompts/`

- 按 2.3 实现 `render_refs` 与 `leak_hits(..., audience=)`。
- **接两处由大模型写给下层的文字**，都写在门面或 L1 链路里，工具不加分支：
  - L1 回答（`agent:l1_answer`）：提示词改为「专业内容只写 `[[编号]]`，编号来自给你的 hits」；回答先过 `render_refs(text, 收件层)`，再过 `leak_hits(..., audience=收件层)`；任一不过，回「这部分需要专业人员解答」并记审计。离线模式现在是拼接 hits 原文，等价于渲染，不改。
  - 门面 `save_reply_draft`（业务员 Agent 的回复草稿）：同样先 `render_refs(text, 0)`，再 `leak_hits(audience=0)`。
- 其余发往下层的文字都是人写人签的（退回理由、不立项理由、复用说明），保留现有 `leak_hits` 调用点；不改成编号渲染（列入「不做」）。

**验收**：`test_wp_t` 加：授予收件层的编号被换成原文，错层编号被拒；不传 `audience` 时 `leak_hits` 结果与现在逐条一致，传入后与上层结论重合的句子被拦截。

### Q4 依据与编译（替身 RAG）

`src/huayan/ingest/`（新）、`scripts/compile_qi.py`（新）、`seeds/rag/`（新，模拟）、`tests/fixtures/mini_seeds/rag/`（新，模拟）、`app.py`

- **替身 RAG**：`ingest/folder.py` 一个类 `FolderSource(name, kind, root, level=None)`：`list_docs()` 列出文件，`fetch(doc_id, span)` 按段号取段落，`search(query, k)` 用现有二元组打分；片段密级按来源：公开 0、外部 0、内部取 `level` 或片段密级表，都没有就是 3。
- **编译** `ingest/compile.py`，三个函数：
  - `propose(fragments, gateway)`：经网关（caller `ingest:extract`）让模型从片段里提出结论，每条带引文与对齐建议（现象、槽位取值、产品、形式）；
  - `admit(proposals, sources)`：用 `fetch` 核对引文确在原文里，查不到就丢；结论 `status=candidate`、`level` = 所依据片段的最高密级、`evidence` 只存位置与指纹；用 `find_phenomenon`、`find_slot_values` 对齐，生成同层的能力提议（`ask`、`applicable`）；与现有能力完全相同的丢弃、取值冲突的列入报告；
  - `recheck(kb, sources)`：逐条 `fetch` 依据并比指纹，取不回或对不上就 `kb.evidence_changed`。
- **脚本** `scripts/compile_qi.py --state <file> [--proposals <yaml>]`：清点所有 `list_docs()` 的文档 → `propose`（给了 `--proposals` 就读录制好的提议，不调模型；校验、定级、指纹照常执行）→ `admit` → 写入状态文件 → 写 `data/ingest/report.md`（查询、片段、候选、提议、冲突、按设计第 9 节分类的待签数）。
- **模拟资料**：演示用 `seeds/rag/public/LV205.md`、`seeds/rag/internal/RPT-031.md`、`RPT-044.md` 与录制的提议 `seeds/rag/proposals.yaml`；测试用 `tests/fixtures/mini_seeds/rag/`，按 `mini_seeds` 的 T-205 与现有槽位写（追问用 `constraint`，适用情境用夹具里已有的面料与设备取值），不往 `mini_seeds` 加槽位或取值。全部标「模拟」。决赛原始资料放 `data/finals/`，与由它编译出的一切都不入库。
- 门面 `recheck_evidence()`、`set_doc_level()`；`HuayanApp.build` 按 `config["sources"]` 建适配器。

**验收**：`test_wp_a3` 里用 `tests/fixtures/mini_seeds/rag/` 的临时副本：`admit` 产出的候选不进入任何更低层的视图，也不经 `search` 读出；只依据外部片段的结论不能确认；改动一段原文后 `recheck` → 依据它的能力挂起、觉提出 `qi_review`。不调模型。

### Q4.5 接入起草：从企业资料起草种子

`ingest/draft.py`（新）、`scripts/draft_seeds.py`（新）、`config/app.pilot.yaml`（新）

- `draft_seeds(sources, gateway, seeds_dir=None) -> dict[str, list]`：读公开来源的全部文档（`list_docs` + `fetch`），经网关（caller `ingest:draft`）起草：
  - 产品：`id`、`name`、`category`、`sheet`、`usage`（原文摘录，标出处）、`solves`、`applicable`、`owner` 留空待填，`mechanism`、`formula` 为空串；
  - 词表：新的槽位取值、现象及客户说法、问法；`required_slots` 只起草建议，标「待研发确认」。
  给了 `seeds_dir`（已有种子）时只起草其中没有的条目。
- 每条草稿带来源位置；引文用 `fetch` 核对，查不到的丢弃（同 `admit`）。
- `scripts/draft_seeds.py --sources <配置> --out <目录>` 写出与种子文件同格式的 yaml，文件头写「草稿：须由产品经理与研发逐条审定后才能作为种子」，`placeholder: false` 由人在审定后改。脚本不启动应用，不写状态文件。
- `config/app.pilot.yaml`：试点配置样例（`seeds_dir`、`sources`、`qi_state`、`run_root` 都指向 `data/` 下，不入库；`gateway_mock: false`）。
- 新 caller `ingest:draft` 写进契约 ⑩ 的 caller 表（随 Q0 一并批准）。
- **只读公开来源**：内部来源的文档一律不进草稿，种子里不出现内部资料的原文（愿景：不导出、不缓存企业文档；种子里的说明与用法本来就是对外公开的话）。
- 不做：自动合并草稿进种子、让模型填 `owner`、机理、配方或定密级。

**验收**：用决赛资料（或 `seeds/rag/public/`）真实跑一次，草稿能被 `load_seeds` 读入、人工补齐 `owner` 后应用能启动；不写测试（AGENTS.md 第 5 节：能用一次真实运行验证的不写测试）。

### Q5 分层召回

`knowledge/store.py`、`agent/tools.py`、`l1/answer.py`、`jue/state.py`

- `explore(query, actor)`（只读，四步）：
  1. 用全部转化对照把查询往上扩展（扩展词只在内部用）；
  2. 用 `_rank` 在全部已确认结论里找，再经适配器查片段、按 `evidence` 的 `doc_id` 接回结论；
  3. 命中结论本层可读 → `units`；授予本层的、`based_on` 含命中结论的能力 → `capabilities`；命中但本层没有能力 → 记入 `unanswerable_ku_ids`，内部各层给存根（与 `search_blocked` 相同），客户层什么都不给；
  4. 提示只从本层视图算：查询里出现本层视图的槽位取值、现象或已发布产品时，给「相关条件：设备」「相关产品：HY-LV205」。
  写一条 `retrieve` 事件（payload 同 `search`，加 `unanswerable_ku_ids`、`n_unanswerable`）。研发层另带本层候选，标「候选」。
- Agent 工具 `search_knowledge` 改调 `explore`；`l1/answer.py` 的检索改调 `explore`，用 `units`。`search` 本身不变。
- `qi_grant` 的 `n_unanswerable` 从 `retrieve` 事件按「结论 × 提问者层级」计数。

**验收**：`test_wp_l` 加：客户层命中上层时的返回与「没找到」完全相同；L1、L2 只拿到本层内容、能力、提示与存根，不出现 L3 原文。

### Q6 决策投影（只做有使用方的部分）

`jue/records.py`、`eval/catalog.py`、`scripts/catalog_stats.py`

- `decision_rows(records, events)`：一行 = 决策点、当时属性与 `p_need`、谁、怎么处置、后来的结果（退回、试样、市场评价、复用拒绝、不立项）、用到的能力；`level` = 做决定的人的层级与所引内容层级取高。纯函数，不落盘。
- `rows_for(rows, level)`：只留 `level ≤ k` 的行。
- 使用方：现有的 `scripts/catalog_stats.py`（目录飞轮统计）按层级输出决策行数与处置、结果分布，决赛资料回放时用它报告真实的处置与结果记录。
- 不改 Jue-K 的训练数据与模型；不做追问提示的探索比例（列入「不做」）。

**验收**：`test_wp_b1` 加：决策投影的行与层级正确；`rows_for(rows, 0)` 里没有高于客户层的行。

### Q6.5 可续跑

`app.py`、`events.py`、`bus.py`、`knowledge/records.py`、`knowledge/store.py`、`ui/server.py`

- 四个日志类的构造：文件已存在就逐行读回（事件、审计、积分照原样；问题按 id 取最后一个快照）。
- `HuayanApp.build(..., resume=True)`：不新建运行目录；读回 `sessions/*.json`、`requirements/*.json`；`_trials` 从有效状态里 `trial` 类知识的正文（试样 JSON）重建；知识与能力已在 `from_seeds` 加载状态文件时恢复。
- 不恢复：觉的推理轨迹 `_jue_trace`（原始记录在 `jue_samples.jsonl`，只影响界面上的轨迹显示）、回问答案到发言的映射 `_answers`（只影响界面上的引用跳转）。
- `ui/server.py` 加 `--run <id> --resume`。
- 编号（需求单、事件、问题、试样）都是「已有数量 + 1」，读回后自然续上，不另加计数器。

**验收**：`test_e2e` 里在主线中途（需求单已接单、产品已发布之后）用 `resume=True` 重建应用，余下步骤照常跑完，断言不变。Q7 的「重启」演示用这条路径。

### Q7 决赛主演示与 V6 对照

`scripts/demo_qi.py`（新）、`scripts/compare_v6_qi.py`（新）、`config/app.demo.qi.yaml`（新）、`docs/reports/qi_demo/`、`README.md`、`docs/VISION.md`、`docs/PITCH.md`、`docs/QI.md`

- **`demo_qi.py`**（离线配置，状态文件放本次运行目录）：
  1. 编译 `seeds/rag`（录制的提议）；
  2. 三态：同一句客户话「锦氨在经轴缸上染出来深一块浅一块」，A 未授予（R01 已确认 C4，只在研发开工门槛要求 pH）→ B R01 签 `qi_grant` 授予 K3 → C 撤销 K3，记录每一态客户是否被追问 pH、问原理时得到什么；
  3. 四步：C05 → C07 → C08 与「只说锦纶氨纶」→ 撤销 K5 / 改 RPT-044 后 `recheck_evidence`；
  4. 重启：用 `resume=True` 重建应用（Q6.5），重放 C07 的问题，并确认未办完的需求单与积分都还在。
  每一步的结论从事件日志读出，写进 `docs/reports/qi_demo/demo.json` 与一页 `demo.md`，不写死文案。
- **`compare_v6_qi.py`**：问题批次（按时间排序的模拟问题，含 C05、C07、C08 的同类问题若干，以及每个问题的「研发判断」）与五个指标的统计函数两边共用；两个驱动函数各自只调用本版本已有的接口：契的驱动用 `decline_project(..., claim_ids)`、`extend_scope`；V6 的驱动在 `351c2c9` 的 worktree 里运行，研发判断与产品不相容时按 V6 的真实做法不带产品不立项。指标：正确的自助处理数、研发重复参与次数、未经授权的确定推荐数（确定推荐没有落在研发判断写定的任何完整情境内）、撤销或失效后的行为、重启后的授权状态；另按时间窗画「每解决一个客户问题需要几次研发判断」（VISION 6.2 的衡量指标，由授予机制算出，不是学习曲线）。报告写进 `docs/reports/qi_demo/compare.md`，注明数据为模拟、处置为脚本写定。
- **材料**：按 1.1 更新 `docs/QI.md` 第 12 节（并删去该节开头的校正注）与 PITCH 的演示台词；VISION 1.2 证据表里已实现的行改为「已实现」并指向测试与报告；README 加一节「契」（三句话 + 演示命令 + 报告链接）。

**验收**：两个脚本在离线配置下从头跑通；报告里的数字能用事件日志复算。

### Q8 独立审查

照 V6-3.1：由一个没参与实现的子代理只读审查，对照 AGENTS.md 铁律、本文第 0.2 节与设计第 13 节「边界与措辞」。重点查：有没有绕开视图读种子做判断的地方；有没有能力之外改变下层行为的写入；有没有防御代码和只为测试存在的分支；Agent 能否写出不经渲染的专业结论。阻断与应修项按最小修改修复，不新增测试、不改契约，结果补进本节。

## 4. 测试：仍是 11 个，场景写进现有测试函数，只用 `mini_seeds`

| 测试 | 新增场景 | 所在包 |
|---|---|---|
| `test_wp0` | 不改：种子产品带第 0 天情境，四步关系照旧成立 | Q1 |
| `test_wp_a1` | 给 T-205 再授予一个「涤纶 × 气流染色机」情境后，「锦纶氨纶 × 气流染色机」不命中 T-205；部分条件为 possible、全知为 confirmed；配方不能作下层依据；未授予的 L3 结论不改变客户层视图 | Q1.5、Q2 |
| `test_wp_t` | `render_refs` 换编号与拒错层编号；`leak_hits` 不传 `audience` 逐条不变，传入后拦截上层结论 | Q3 |
| `test_wp_l` | `explore` 客户层无存根无提示；L1/L2 只得本层 | Q5 |
| `test_wp_a3` | 授予/撤销追问（色花 × 环保要求）；撤销解密；撤销情境后各调用方不再推荐；批准；依据他人结论被拒；重启保留；被使用记分；编译、候选不可读、指纹变化 → 挂起与复核 | Q2、Q4 |
| `test_wp_b1` | 家族数 21；`auto_action` 两种；决策投影与层级过滤 | Q2、Q6 |
| `test_e2e` | 第 0 天迁移后主线结果不变；主线中途续跑 | Q1、Q6.5 |

桩仍只有 `MockGateway`、`MockSystem1Client` 和 `mini_seeds`（含新加的 `rag/` 子目录）。四步演示由 Q7 的脚本证明，不进测试（与设计第 13 节测试表的 `test_e2e` 一行不同，见第 7 节）。

## 5. 检查点

| 完成 | 必须成立 |
|---|---|
| Q1 | 11 个全绿且断言不改；离线主线与 `351c2c9` 基线一致；`update_applicable`、`extend_solves` 已删除；视图里没有 `applicable` |
| Q1.5 | 「锦纶氨纶 × 经轴」可被研发授予并经产品经理批准；只给部分条件时卡片列出待确认条件；`demo_routes.py` 照常跑通 |
| Q2 | 三态在测试里成立；重启保留；家族数 21 |
| Q4 | `compile_qi.py --proposals seeds/rag/proposals.yaml` 跑通；改一段原文即挂起 |
| Q4.5 | 用公开资料起草出的种子经人补齐后，应用能启动 |
| Q6.5 | 主线中途续跑，结果不变 |
| Q7 | 两份报告生成；VISION 1.2 的状态更新 |

任何一个检查点不成立，先修，不往下做。

## 6. 不做

- `phrase` 的入口与业务员说法授予（1.2）；`translation` 建行（同层直接用）。
- `public_points` 建 `statement` 行：发布前不对外，发布后随说明书成为 L0 结论。
- 人写人签的下行文字（退回理由、不立项理由、复用说明）改成编号渲染：保留现有 `leak_hits`。
- Jev 第三问（依据核对）接入 `scope_update`；`qi_grant` 由 Agent 起草。
- 增量编译、热加载、原文快照、在 RAG 侧写标签、让模型定级或建议降密、遍历企业 RAG 全库。
- 用决策投影重训 Jue-K；追问提示的探索比例；报告模拟业务周的「越用越准」。
- V6 兼容开关：V6 对照用基线的 worktree 跑，代码里不留旧语义。
- 种子改动后的状态文件合并（状态文件以 id 覆盖迁移结果；改种子后由人删除或复核状态文件）。

## 7. 修订记录：v7.1 独立审查（2026-10-19）

由一个未参与编写的子代理对照 AGENTS.md、`docs/CONTRACTS.md`、`docs/QI.md` 与 `351c2c9` 的代码只读审查，报 5 条阻断、15 条应修、5 条建议，均已核实并按最小修改并入本文：

| # | 问题 | 处理 |
|---|---|---|
| 1 | 测试、`sim/`、`confirm_translation` 直接拿种子产品调匹配函数，只读 `situations` 会全部失效（`sim/week.py:76` 会死循环） | `load_seeds` 填第 0 天情境（2.2） |
| 2 | 新品发布不写适用能力，发布后永远匹配不到 | `release_product` 授予情境（Q1、2.7） |
| 3 | `qi_review` 放进 `knowledge_conflict` 违反「一个 family 一个模板」 | 独立家族，家族数 21（2.8，需人确认） |
| 4 | 新 `render` 与现有 `disclosure.render` 重名 | 改名 `render_refs`（2.8，需人确认） |
| 5 | 测试夹具没有 pH、经轴、LV205 | 测试改用 `mini_seeds` 与 `mini_seeds/rag/`（第 4 节） |
| 6 | `from_seeds` 新增必填参数打断现有调用 | 去掉 `maintainer`，确认人用 `"seed"` |
| 7 | `publish.py` 不在清单里，新对象缺 `slot`、签字人推断错 | 列入 Q1.5、Q2，属性带 `product_id`、`slot`，签字人走 `refs` |
| 8 | 「同层不建行」与研发层追问矛盾 | 改写 0.2 第 3 条 |
| 9 | 删 `cite_scope` 影响工作量统计与 `demo_routes` | 删除与替代同在 Q2，写明记分对象变化 |
| 10 | 系统收窄、发布出的适用能力会变成待批准 | 1.3 写明 `approved_by` |
| 11 | `ku:claim:<req_id>` 跨重启冲突 | 持久化序号（2.1） |
| 12 | `decrypt` 投影不出 `DecryptGrant` | payload 加 `session_id`，`approved_by = granted_by` |
| 13 | 仍有三处用汇总字段做适用判断 | 视图不再汇总 `applicable`，三处改读情境（Q1） |
| 14 | 候选、撤回的结论仍能经 `search` 读到 | 可读条件加「`active`」（2.1） |
| 15 | Q2 验收依赖 Q4 | Q2 测试直接构造数据 |
| 16 | `hash()` 不可复现 | 探索比例整体不做 |
| 17 | 回复草稿的渲染应在门面 | 写在 `app.save_reply_draft`（Q3） |
| 18 | 可能适用打平时卡片文案矛盾 | 卡片取所有相容情境的未知条件并集（Q1.5） |
| 19 | 迁移写事件会改变事件计数 | 迁移不写事件；基线用 worktree 跑（Q1） |
| 20 | 与设计第 13 节的覆盖缺口 | 发布补进 Q1；其余列入「不做」或下表 |
| 21 | Q6 没有运行期使用方 | 接到 `catalog_stats.py`，探索比例不做 |
| 22 | 撤回结论触发 `qi_review` 多余 | 只由依据失效触发；不加 `qi_maintainer` |
| 23 | Q1 先写后删 | Q1 直接写 `grant + approve` 通用路径 |
| 24 | V6 对照脚本会出现按版本分支 | 共用批次与统计，两个驱动各用本版本接口 |
| 25 | K3 会让所有色花客户都被问 pH | 演示台词与报告按此讲（1.1） |

**v7.2 真实运行补充**：新增 Q4.5（接入起草）与 Q6.5（可续跑）；有效状态文件默认放运行目录，并扩大为全部运行期知识与发布的产品（2.6）。

**与设计（`docs/QI.md`）的差异**，Q0 在设计文首逐条加注，清单见第 8 节。

## 8. 与设计 `docs/QI.md` 的差异清单

| # | 设计里写的 | 本计划的做法 | 原因 |
|---|---|---|---|
| 1 | 第 12 节例子：LV206、研发 R02、K5 =「纯锦纶 × 溢流」 | LV205、研发 R01、K5 =「锦纶氨纶 × 经轴」，C08 =「锦纶 × 经轴」 | LV205 已覆盖锦纶 × 溢流；LV206 是立项产品（1.1） |
| 2 | `qi_review` 是 `knowledge_conflict` 家族的新模板，家族数 20 | 独立家族，家族数 21 | 一个家族只能一个模板（2.8，待人确认） |
| 3 | 出口函数 `render(draft, audience)` | `render_refs` | 与现有卡片渲染重名（2.8，待人确认） |
| 4 | `qi_review` 由依据失效、结论撤回、试样或市场评价矛盾触发 | 只由依据失效触发；试样矛盾仍走现有 `knowledge_conflict` | 撤回人就是授予人，不必再复核 |
| 5 | 契约定义 `SourceAdapter` 协议；网关另加不带缓存的 `ingest` 配置 | 只有 `FolderSource` 一个类；编译脚本自建网关、关缓存 | 只有一种适配器；少一份配置 |
| 6 | 第 0 天把种子全部迁成能力，含 `phrase`、`translation`、`statement` | 只建 `applicable`、`ask` 行；说法、转化对照、说明书是同层结论，直接用 | 同层不需要授予，建行无行为差别 |
| 7 | 业务员改正槽位时确认并授予说法（第②类签字） | 本轮不做，`phrase` 无入口 | V6 没有改正槽位的入口（1.2） |
| 8 | `qi_grant` 由确认人的 Agent 准备（附原话、建议措辞） | 追问、适用两种不经 Agent（形式与目标能算出）；授予可说的话时由研发 Agent 起草措辞 | 只有措辞需要起草 |
| 9 | `scope_update` 里由 Jev 标出与原文对不上的条目 | 不做 | Jev 第三问尚未接入 |
| 10 | 放出对外要点 → 若干条 `statement` 授予客户层 | 不建行，发布后随说明书成为 L0 结论 | 发布前不对外 |
| 11 | 所有发往下层的文字先经渲染 | 只接两处大模型写的（L1 回答、业务员回复草稿）；人写人签的保留 `leak_hits` | 人签的文字不是 Agent 自称引用 |
| 12 | 追问提示留一小部分探索比例；Jue-K 训练行按层过滤 | 探索比例不做；决策投影接到 `catalog_stats.py`，不重训 Jue-K | 没有真实数据前没有使用方 |
| 13 | 种子里没有归属人的条目登记到配置指定的维护人 | 确认人统一记为 `"seed"`，不加配置项 | 第 0 天授予是历史默认，不代表某人确认过 |
| 14 | 有效状态只含结论、能力、片段密级表 | 还含运行期新增的全部知识与发布的产品；默认放运行目录 | 真实运行要续跑（1.4） |
| 15 | 种子由人编写，新概念只进编译报告 | 新增 Q4.5，从公开资料起草种子草稿，由人审定 | 真实企业没有现成种子（1.4） |
| 16 | 测试表：`test_e2e` 跑通决赛主演示四步 | 四步由 `demo_qi.py` 证明；`test_e2e` 只守第 0 天不变与续跑 | 测试只用 `mini_seeds`，四步依赖演示数据 |
| 17 | 测试的适配器指向 `tests/fixtures/` 下的小目录 | `tests/fixtures/mini_seeds/rag/`，按 T-205 与现有槽位写 | AGENTS.md 只允许 `mini_seeds` 一份夹具 |
| 18 | 视图里的产品带汇总的适用字段（隐含） | 视图里的产品 `applicable` 置空，只看 `situations` | 防止汇总字段被当成适用判断 |
| 19 | 决赛：「重启应用后 K5 仍是撤销或挂起状态」 | 用续跑（Q6.5）重启，同时验证未办完的工作也在 | 真实的重启就是续跑 |

## 9. 愿景审核（v7.3）

人批准契约改动时要求：改动不能偏离愿景。逐条对照 `docs/VISION.md` 第 1 节八条主张、1.3 升级点、6.2 觉的自进化、第 7 节边界、第 10 节评委追问，以及 `AGENTS.md` 第 1 节「权责对等」，结论如下。

**不偏离、且是愿景要求的**：情境匹配与可能适用（主张 6、1.3「条件没问全时只说可能适用」）；`render_refs` 与 `leak_hits(audience)`（主张 5）；能力表与唯一读路径、撤销（主张 4、5）；有效状态与续跑（主张 5「重启后仍是撤销状态」、第 11 节试点路径）；替身 RAG、只存位置与指纹（主张 7、第 11 节「不导出、不缓存」）；`qi_review` 独立家族（主张 5，只是目录里多一个模板）；决策投影与层级过滤（6.2「代谁判断，就只用谁那一层的决策来学」）。

**偏离，已修正**：

| # | 改动 | 偏离了什么 | 修正 |
|---|---|---|---|
| 1 | C′ 之后的复用只给研发记「被使用」 | AGENTS.md「权责对等」、VISION 第 10 节「产品经理的判断记在本人名下」：V6 里产品经理扩范围后被引用即记分，改后产品经理没有了 | 适用能力被使用时，确认的研发与批准的产品经理各记一份（Q2） |
| 2 | `qi_grant` 只覆盖追问与适用 | 主张 4、5 与设计例子「对客户层可以说『无需另加醋酸』」：研发把一句话授权给前台说的通用入口缺失，只剩复用审定一处 | `qi_grant` 加第二种对象：已确认结论在下层被需要却无能力时，授予一句 `statement`，措辞由研发 Agent 起草、研发签（Q2，依赖 Q5 的「本层无能力」） |
| 3 | `phrase` 本轮无入口 | VISION 第 10 节与 PITCH 第 13 节写着「客户说法由业务员顺手授予」，说了做不到 | 删掉这半句（本次已改），1.2 不变 |
| 4 | Q4.5 从资料起草种子 | 第 11 节「不导出、不缓存企业文档」：草稿若读内部资料，内部原文会进种子文件 | 草稿只读公开来源（Q4.5） |
| 5 | V6 对照只报五个计数 | 6.2 的衡量指标是「每解决一个客户问题需要几次研发判断」随时间下降，决赛要展示 | 对照报告按时间窗画这条线（Q7） |

**愿景文字收窄（实现不跟着扩）**：VISION 6.2「能力进化」列了三种燃料，其中「单子因为缺同一项信息被退回」本轮不作为 `qi_grant` 的信号（退回理由是自由文本；缺信息的情况已由「反复回问同一槽位」覆盖），本次把这半句删掉。

**新增一条边界**（写入 VISION 第 7 节）：第 0 天迁移进来的种子内容没有依据指纹，「资料一改自动复核」只覆盖经编译、带依据的结论；试点时种子由 Q4.5 从公开资料起草，再编译一次公开来源即可补上依据。
