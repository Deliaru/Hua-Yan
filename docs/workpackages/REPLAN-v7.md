# REPLAN-v7｜契落地

> 2026-10-19。代码基线：`main` @ `351c2c9`（V6 完成态）。设计依据：`docs/QI.md`（契 v3.3 设计文档，下称「设计」）、`docs/VISION.md` 第 1 节、`docs/PITCH.md` 第 6.1 节。
> **第 2 节的契约改动已由人批准**（含 2.8 的两处与 v7.2 新增的续跑、`ingest:draft`），之后冻结；实施中需要再改契约，先停下来问人。
> 本文与 `REPLAN-v6.md` 冲突处以本文为准。不标耗时。
> v7.1（同日）：按独立审查的 25 条意见修订，修订记录见第 7 节。
> v7.2（同日）：补上真实运行的两个缺口——从企业资料起草种子（Q4.5）、应用可续跑（Q6.5），见第 1.4 节。
> v7.3（同日）：人已批准全部契约改动（含 2.8 与 v7.2 新增）；按愿景逐条审核，修正 5 处偏离，见第 9 节。
> v7.4（同日）：第二轮独立审查（能否开工）报 6 处必须先改，并结合人提供的真实公开产品目录（CSV），全部并入，见第 10 节。
> v7.5（同日）：人要求觉的自进化现在就演示出来；Q6 改为「决策记录与觉的在线自进化」，Q7 加 `demo_evolution.py`，见第 11 节。
> v7.6（同日）：并入契之前那份决赛行动计划里该在 v7 做的三项——试样失败回路（Q5.5，契约改动已获批）、真实案例回测（Q7.5）、终赛资料四类入口与归属认领（Q4、Q4.5），见第 12 节。其余项见 `REPLAN-v7-after.md`。
> v7.8（同日）：开工前审查（Codex）报 5 处接口与行为边界未闭合、2 处执行清单错漏，全部并入，见第 14 节；其中 `BlockedHint.ku_id`、Jue-K 按家族分开训练两处契约改动已由人批准。
> v7.7（同日）：按访谈（`docs/reference/interview_notes.md` 第 2、5 节）补上研发之间的知识边界：同层只见归属，申请后由归属人授予并记分，配方也走授予（Q2.5，契约改动已获批，见 2.10 与第 13 节）。

## 0. 目标与写法

### 0.1 做完是什么样

1. **第 0 天行为不变**：现有种子迁成结论与能力后，11 个测试全绿，离线主线（`scripts/demo_mainline.py`）的推荐、升级、需求单状态与基线一致；失真对照、业务周的数字不重跑也不变。
2. **决赛主演示在离线配置下真实跑出**：三态（未授予 / 已授予 / 已撤销）、四步能力复用、重启后状态保留，以及与 V6 在同一批问题上的对照，数字全部从事件日志统计。
3. **VISION 1.2 节里标「设计完成」的几条主张变成「已实现」**，证据指向测试与演示报告。
4. **觉的自进化当场可见**：系统运行中按窗口重训觉、换上新模型，在世界偏离专家先验时，与冻结的觉跑同一批问题对照；同时演示觉学不到没被授予的东西（第 11 节）。
5. **真实运行能起步、能续跑**：拿一家企业的资料，能起草出种子由人审定后启动；应用重启后会话、需求单、问题、积分、知识与能力都接着用（第 1.4 节）。

### 0.2 防止屎山的六条写法（每个包都要守）

1. **一张能力表，一条读路径。** 能力存在知识库里；引擎读知识只走 `kb.view(actor)`。删掉 `update_applicable`、`extend_solves`；视图里的产品不再带汇总的 `applicable`，任何适用判断只看 `situations`。不保留「旧字段 + 新能力」两套判断。
2. **视图就是种子形状。** `view(actor)` 返回现有的 `Seeds` 对象，引擎函数签名不变；调用方只是把 `self.seeds` / `kb.products()` 换成对应层的视图。不新造一套视图类型。
3. **只有驱动行为的能力建行。** 能力表只放四种形式：`ask`、`applicable`（各层都建行，包括同层：研发确认结论后，它在研发层的追问与适用随之生效）、跨层的 `statement`、`decrypt`。`translation` 只在同层使用，`statement` 的同层使用就是读已确认的结论，这两种同层情况都不建行；`phrase` 见 1.2。
4. **没有新框架。** 不写规则引擎、不做事件溯源、不做插件注册；替身 RAG 就是一个读文件夹的类。传播（依据 → 结论 → 能力）是数据上的引用，写成一个函数。
5. **只校验业务规则，不写防御代码。** 要校验的只有设计里的规则：授予人必须是所依据结论的确认人；配方不能作下层依据；只依据外部片段的结论不能确认；适用能力要产品经理批准；候选结论不跨层、也不经 `search`/`get`/`list` 读出；同层研发的 L3 知识只对归属人与被授予的人可读（2.10）。设计的第三条结构约束「只依据系统自身决定的结论不能成为能力」本轮由结构保证：结论只来自编译和研发本人，没有从决策记录生成结论的路径。内部调用之间不加 `isinstance`、不加兜底 `try`。
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

class BlockedHint(BaseModel):            # v7.8 加一个字段（已批准）
    owner: str
    level: Level
    kind: KUKind
    ku_id: str | None = None             # 只在「同层研发、可申请查看」的存根上填写；跨层存根一律为 None
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
qi_state: null         # 有效状态文件；为 null 时用 <运行目录>/qi_state.json（每次新运行独立）；试点指向 data/qi/state.json。状态文件含运行期发布的产品与试样，只能配同一个运行目录用：接着上次运行一律走 resume（Q6.5），不让两个新运行共用一个状态文件
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

### 2.9 文档

`docs/CONTRACTS.md` 同步以上各节；`AGENTS.md`：目录加 `src/huayan/ingest/`、`seeds/rag/`、`tests/fixtures/mini_seeds/rag/`；铁律 4 补一句「引擎只读视图，行为只由能力驱动，跨层能力只来自人签的授予；同层研发的知识也只经归属人授予才可读」；开头的阅读顺序加本文与 `docs/QI.md`；第 5 节测试表按第 4 节更新。

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
  - `release_product`（`escalation/flow.py`）：按新品的情境各 `grant` 一条 `audience=0` 的适用能力，`based_on` 为 `ku:sheet:<pid>`，`granted_by` 为产品归属研发，`approved_by` 为发布签字人；`_put_product` 建产品知识单元时把 `confirmed_by` 设为产品的 `owner`（否则 Q2 的「授予人即确认人」规则会拦下发布）；新品记录写进有效状态，重启后照常存在。
- **有效状态**：每次写入后把 2.6 列出的内容整体写成 `{"version": n, ...}`（先写临时文件再改名）；`kb.add`、`add_product` 也算写入；`state_path` 为空时不写（只有直接构造知识库的测试与脚本如此，应用总有路径）。
- **删除**：`update_applicable`、`extend_solves`。（`cite_scope` 在 Q2 与它的替代一起删。）

**验收**：`pytest` 11 个全绿，断言不改；在 `351c2c9` 的 worktree 与本包上各跑一次离线主线，事件种类与计数、最终推荐、需求单状态一致；`grep -rn "\.applicable" src/huayan` 只剩 `domain.py::load_seeds` 与 `sim/`。

### Q1.5 确认适用与可能适用（第一处有意的行为变化）

`l1/session.py`、`app.py`、`jue/state.py`、`jue/publish.py`、`config/templates/scope_update.yaml`

- **有条件的推荐卡**：Jev 选中的候选是 `possible` 时，照常推荐，但卡片 `note` 由系统写出待确认条件：取该产品在本现象下所有相容情境的未知条件，按槽位合并取值（「设备为溢流染色机、卷染机或经轴染色机，请确认」，用槽位的中文标签）；`recommend` 事件带 `status`、`capability_id`。是否提出追问仍由觉判断，不加「可能适用只能追问」的规则。
- **C′ 改为提议完整情境**：`decline_project(..., applicable_product, claim_ids=())` 不再要求 `consistent`；用需求单已知条件里属于该现象必问条件的那几项组成情境，`grant` 一条 `audience=0`、`status=proposed` 的适用能力。`claim_ids` 是研发勾选的结论，候选的在这里一并确认；没有勾选时，用不立项原因生成一条 L3 结论 `ku:claim:<n>`，确认人为 `by`。客户会话照旧收到该产品的推荐（这一张单是研发本人判的）。
- **`scope_update`**：对象改为每条 `proposed` 的适用能力（`knowledge:cap:<id>`），属性 `{product_id, slot: "phenomenon", value: 现象, conditions, n_applicable, pending}`，前置条件 `attrs.pending`；`publish.py` 的 `_refs` 对这类对象写入 `capability_id` 与真实的 `product_id`；`extend_scope` 改为 `kb.approve(q.refs["capability_id"], by)`，写 `scope_extended`（带 `capability_id`）。
- **删除**：Q1 里 `extend_scope` 的「新现象 × 原条件」取法（`grant + approve` 的路径保留）。

**验收**：`test_wp_a1` 加「两个情境不交叉」「部分条件为 possible、全知为 confirmed」；`test_e2e` 主线结果不变（如有未问全被推荐的情况，只是卡片多一句待确认条件，断言按此更新并在提交说明里写明）；`scripts/demo_routes.py` 的 C、C′ 路线照常跑通。

### Q2 生效、撤销、记分与觉的两个新家族

`knowledge/store.py`、`knowledge/disclosure.py`、`app.py`、`l1/session.py`、`jue/state.py`、`jue/publish.py`、`config/templates/qi_grant.yaml`、`config/templates/qi_review.yaml`、`agent/hub.py`、`ui/server.py`、`web/src/`、`scripts/demo_routes.py`

- **四条业务规则**（只在 `grant`、`confirm` 里各写一次）：`based_on` 的确认人都是 `granted_by`；`audience < 3` 时 `based_on` 里不能有 `formula`；只依据外部片段的结论不能 `confirm`；`form == "applicable"` 且 `approved_by` 为空就是 `proposed`。
- **传播**：`withdraw(ku_id)` 与 `evidence_changed(ku_id)` 把所有 `based_on` 含它的 `active` 能力置 `suspended`，写 `capability_suspended`；只此一个函数。
- **确认**：`confirm_claims(req_id, ku_ids, by)`：仅需求单的接单研发；候选结论变 `active`，`confirmed_by=by`；为它提议的能力随之生效（适用类仍待批准）。
- **qi_grant**（新家族，`owner_role: rd`、`signer_role: rd`）有两种对象，本包只做第一种（第二种依赖 Q5 的「本层无能力」，放在 Q5）：
  - `knowledge:grant:<cap_id>|L<k>`：某条追问或适用能力只授予了它的结论那一层，而更低的第 k 层需要过它。形式与目标都能算出，不经 Agent 起草，问题卡直接列出形式、目标层、依据与原文位置；
  - 属性 `{product_id, slot, value, n_ask_back, n_unanswerable, granted}`：`n_ask_back` 是研发为同一现象回问同一槽位的次数（现有 `question_published` 事件里 `family=ask_back`、对象 `slot:<需求单>/<槽位>`，按需求单的现象聚合）；`n_unanswerable` 在 Q5 接上，本包为 0；
  - 前置 `not attrs.granted and (attrs.n_ask_back >= 2 or attrs.n_unanswerable >= 1)`，`rule_score` 取两者之和除以 3 封顶 1；
  - 签字人：所依据结论的确认人；结论还是候选的，取对齐产品的归属研发，签时一并确认。`publish.py` 的 `_resolve` 从 `refs["signer"]` 读签字人，不再按 `product_id` 推断；
  - `sign_qi_grant`：第一种复制该能力，`audience=k`、`granted_by=by`，适用类转入 `scope_update`。
- **qi_review**（新家族，`kind: anomaly`）：只由 `evidence_changed` 触发（撤回结论的人就是授予人，不再给他发复核）；对象 `knowledge:claim:<ku_id>`，签字人是确认人；`resolve` 里 `sign` = 保留（重新取指纹，恢复被挂起的能力），撤回走 `withdraw_claim`。
- **撤销**：`revoke_capability(cap_id, by)` 仅授予人；解密能力同样可撤。
- **解密进能力表**：`decide_decrypt` 通过时 `grant` 一条 `decrypt`（`audience=客户 id`、payload 带 `session_id`、依据该产品的 `ku:mechanism`）；`app.grants` 改为只读属性 `self.kb.decrypt_grants()`，`disclosure.cap/render` 的签名与 `test_wp_a1` 的用法不变。
- **复用审定说明进能力表**：`adopt_reuse` 把 `customer_note` 写成一条授予业务员层的 `statement`；`view_session` 从能力表取这句话，撤销后不再显示。
- **被使用记分（替代 `cite_scope`）**：推荐命中的适用能力、本轮追问用到的 `ask` 能力、渲染用到的 `statement`，各写一条 `capability_used`，给 `based_on` 的确认人记 `used` 分；适用能力另给批准它的产品经理记一份（第 0 天的 `"seed"` 不记）。同一会话同一能力只记一次。同时删除 `l1/session.py::cite_scope` 与 `extend_scope` 生成的 `ku:translation:scope:*` 条目；`app.py` 工作量统计里「同类需求客户自助解决」「此后因此自动解决的需求」改为数这些能力的 `capability_used`。**记分对象有变化**：C′ 之后的复用由作出判断的研发和批准范围的产品经理各记一份「被使用」，V6 里只记产品经理的「被引用」；`demo_routes.py` 的 C′ 断言与 `docs/reports/v6_routes/` 按此更新。现有「被引用」记分的其余部分不动。
- **界面**：研发工作面加「我授予的能力」列表（状态、依据、撤销按钮）；需求单页列出本单相关的候选结论，可勾选确认；`qi_grant`、`qi_review` 用现有问题卡。HTTP 只加对应 2.7 门面方法的几个 `POST`。

**验收**（测试数据直接用 `kb.confirm`、`kb.grant` 在 `mini_seeds` 上构造，不依赖 Q4 的编译）：`test_wp_a3` 加：授予 → 客户被追问；撤销 → 不再追问；撤销解密；撤销一个适用情境后客户、业务员、Agent 工具都不再推荐；适用能力未经产品经理批准不生效；依据他人结论的授予被拒；用同一个状态文件重建知识库（`KnowledgeBase.from_seeds(..., state_path=)`）后授予与撤销都保留（应用级的重启续跑在 Q6.5 验收）；被使用记分正确，被引用断言不变。`test_wp_b1`：家族数 21，`auto_action` 仍两种。

### Q2.5 研发之间：用到才看、看了记分、想看先申请（第二处有意的行为变化）

`knowledge/permission.py`、`knowledge/store.py`、`escalation/translate.py`、`app.py`、`jue/state.py`、`jue/publish.py`、`config/templates/qi_grant.yaml`、`agent/tools.py`、`ui/server.py`、`web/src/`

依赖 Q2 的能力表、`sign_qi_grant`、`revoke_capability`。按 2.10 实现：

- **读权限**：`can_read` 加同层规则；`search`、`search_blocked`、`get`、`list` 都经 `_readable`，所以同事的 L3 知识自动从命中里去掉、出现在存根里（归属人、层级、类别），不另写过滤。Agent 工具 `search_knowledge`、`get_knowledge` 不改代码，行为随之改变。
- **转译引擎**：`draft_chem_need` 改以 `system:translate` 读知识，写 `req.engine_refs`；同事的机理只写归属，不写首句。
- **门面**：`requirement_view` 的「引用的知识」、`_validate_item`、`confirm_translation` 读 `ku_refs` 时，`engine_refs` 里的按「工作中用到」处理，其余照常 `kb.get`；`contributions()` 的标题改用 `can_read` 判断，不再只比层级；`requirement_view`、`requirements()` 对非接单研发按 2.10 裁剪正文。
- **存根**：`search_blocked` 给同层研发的存根填 `ku_id`（2.10）。
- **申请与授予**：门面 `request_share`；`jue/state.py` 从 `share_requested` 事件与 `share` 能力算出申请对象的属性；`qi_grant.yaml` 加这种对象；`sign_qi_grant` 授予 `share` 并记 `shared` 分；撤销走 Q2 的 `revoke_capability`。
- **界面**：存根上加「申请查看」按钮；研发工作面「我授予的能力」里同时列出授予同事的 `share`（可撤销）；问题卡复用现有 `qi_grant` 卡。HTTP 只加 `POST request_share`。
- **第 0 天起生效**：种子里的转化知识、机理、配方都有研发归属，所以从启动起 R01 就读不到 R02 的知识原文。这是有意的行为变化，提交说明里写明；离线主线里研发方向假设的文字会变，`test_e2e` 若断言了这段文字，按此更新。
- **删除**：无。（没有旧的同层共享开关要保留。）

**验收**：`test_wp_a3` 加：R02 检索 R01 的转化知识只得存根（带 `ku_id`），`get` 被拒；业务员、产品经理的存根不带 `ku_id`；R02 打开 R01 接单的需求单，看不到 L3 条目正文、假设与封存项；转译引擎为 R02 的单子引用了 R01 的转化知识 → R02 在单子上看到原文，技术确认后 R01 记「被引用」；R02 往条目里手加 R01 未授予的编号 → 校验被拒；R02 申请 → 觉在总线上提出 `qi_grant`（主人、签字人为 R01）→ hub 派给 R01 的研发 Agent → R01 在工作面上签字 → R02 可读、R01 记 `shared`；R01 撤销 → R02 又读不到；R01 的配方同样可申请、可授予。`test_wp_t` 的「L3 条目引用两位研发的知识」断言不改。`test_wp_b1` 家族数不变。

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

- **替身 RAG**：`ingest/folder.py` 一个类 `FolderSource(name, kind, root, level=None)`：`list_docs()` 列出文档 id，`fetch(doc_id, span=None)` 取一段（`span=None` 返回该文档全部段）。分段只有两种写法：`.md`/`.txt` 按空行分段，span 为 `p<序号>`；`.csv` 每条记录是一个文档、每列是一段，doc_id 为 `<文件名>#<首列唯一键>`（产品目录用「产品ID」，型号有重复），span 为列名。`search(query, k)` 用现有二元组打分；片段密级按来源：公开 0、外部 0、内部取 `level` 或片段密级表，都没有就是 3。
- **编译** `ingest/compile.py`，三个函数：
  - `propose(fragments, gateway)`：经网关（caller `ingest:extract`）让模型从片段里提出结论，每条带引文与对齐建议（现象、槽位取值、产品、形式）；
  - `admit(proposals, sources, kb)`（经知识库写入、可与现有能力去重）：用 `fetch` 核对引文确在原文里，查不到就丢；结论 `status=candidate`、`level` = 所依据片段的最高密级、`evidence` 只存位置与指纹；用 `find_phenomenon`、`find_slot_values` 对齐，生成同层的能力提议（`ask`、`applicable`）；与现有能力完全相同的丢弃、取值冲突的列入报告；
  - `recheck(kb, sources)`：逐条 `fetch` 依据并比指纹，取不回或对不上就 `kb.evidence_changed`。
- **脚本** `scripts/compile_qi.py --state <file> [--proposals <yaml>]`：清点所有 `list_docs()` 的文档 → `propose`（给了 `--proposals` 就读录制好的提议，不调模型；校验、定级、指纹照常执行）→ `admit` → 经 `KnowledgeBase` 写入状态文件（脚本只在应用停着时运行；演示脚本在进程内调用同一函数，不另起脚本）→ 写 `data/ingest/report.md`（查询、片段、候选、提议、冲突、按设计第 9 节分类的待签数）。
- **终赛资料的四类入口**（拿到资料时按此放，`sources` 配置写明）：
  | 资料 | 进哪里 | 说明 |
  |---|---|---|
  | 产品与工艺资料（公开的说明书、产品页、产品目录） | 公开来源（L0） | 同时是 Q4.5 起草种子的输入 |
  | 实验与应用案例、内部工艺资料 | 内部来源（默认 L3） | **不复制进种子**：留在适配器后面，编译成候选，由研发确认、授予 |
  | 外部专业知识 | 外部来源（L0，只作补充） | 不能单独成为结论 |
  | 业务问答样例 | **不进任何来源** | 只作 Q7.5 回测的评测集，防止评测标签泄进系统（铁律 5） |
- **模拟资料**：演示用 `seeds/rag/public/LV205.md`、`seeds/rag/internal/RPT-031.md`、`RPT-044.md` 与录制的提议 `seeds/rag/proposals.yaml`；测试用 `tests/fixtures/mini_seeds/rag/`，按 `mini_seeds` 的 T-205 与现有槽位写（追问用 `constraint`，适用情境用夹具里已有的面料与设备取值），不往 `mini_seeds` 加槽位或取值。全部标「模拟」。决赛原始资料放 `data/finals/`，与由它编译出的一切都不入库。
- 门面 `recheck_evidence()`、`set_doc_level()`；`HuayanApp.build` 按 `config["sources"]` 建适配器。

**验收**：`test_wp_a3` 里用 `tests/fixtures/mini_seeds/rag/` 的临时副本：`admit` 产出的候选不进入任何更低层的视图，也不经 `search` 读出；只依据外部片段的结论不能确认；改动一段原文后 `recheck` → 依据它的能力挂起、觉提出 `qi_review`。不调模型。

### Q4.5 接入起草：从企业资料起草种子

`ingest/draft.py`（新）、`scripts/draft_seeds.py`（新）、`config/app.pilot.yaml`（新）

- `draft_seeds(sources, gateway, seeds_dir=None) -> dict[str, list]`：读公开来源的全部文档（`list_docs` + `fetch`），经网关（caller `ingest:draft`）起草：
  - 产品：`id`（型号；同一型号对应不同产品时加「产品ID」后缀）、`name`、`category`、`sheet`、`usage`（原文摘录，标出处）、`solves`、`applicable`（只起草资料里写明的纤维、染料类别；产品自身的 pH 不是染浴 pH，不起草）、`owner` 留空待填，`mechanism`、`formula` 为空串；
  - 词表：新的槽位取值、现象及客户说法、问法、成因（`causes` 必填，起草为「待研发补写」）；`required_slots` 只起草建议，标「待研发确认」。资料里没有这些内容的原文，所以**词表草稿不做引文核对，逐条标「无出处，待人写」**；
  - 同时写出空的 `cases.yaml`、`translations.yaml`（`load_seeds` 要求六个文件都在），`actors.yaml` 由人写。
  给了 `seeds_dir`（已有种子）时只起草其中没有的条目。
- 产品草稿带来源位置，引文用 `fetch` 核对，查不到的丢弃（同 `admit`）；词表草稿见上，不核对。
- `scripts/draft_seeds.py --sources <配置> --out <目录>` 写出与种子文件同格式的 yaml，文件头写「草稿：须由产品经理与研发逐条审定后才能作为种子」，`placeholder: false` 由人在审定后改。脚本不启动应用，不写状态文件。
- `config/app.pilot.yaml`：试点配置样例（`seeds_dir`、`sources`、`qi_state`、`run_root` 都指向 `data/` 下，不入库；`gateway_mock: false`）。
- 新 caller `ingest:draft` 写进契约 ⑩ 的 caller 表（随 Q0 一并批准）。
- **只读公开来源**：内部来源的文档一律不进草稿，种子里不出现内部资料的原文（愿景：不导出、不缓存企业文档；种子里的说明与用法本来就是对外公开的话）。
- **归属待认领**：草稿里产品的 `owner` 从资料自带的作者或部门推断，推断不出就写 `待认领`；审定时必须全部认领完（没有归属，记分与签字人都无从谈起）。内部资料编译出的候选结论同理：资料有作者就记为建议确认人，没有就交对齐产品的归属研发。
- 不做：自动合并草稿进种子、让模型填机理、配方或定密级。

**验收**：用决赛资料（或 `seeds/rag/public/`）真实跑一次，草稿能被 `load_seeds` 读入、人工补齐 `owner` 后应用能启动；不写测试（AGENTS.md 第 5 节：能用一次真实运行验证的不写测试）。

### Q5 分层召回

`knowledge/store.py`、`agent/tools.py`、`l1/answer.py`、`jue/state.py`、`app.py`、`prompts/l1_answer.md`

- `explore(query, actor)`（只读，四步）：
  1. 用全部转化对照把查询往上扩展（扩展词只在内部用）；
  2. 用 `_rank` 在全部已确认结论里找，再经适配器查片段、按 `evidence` 的 `doc_id` 接回结论；
  3. 命中结论本层可读 → `units`；授予本层的、`based_on` 含命中结论的能力 → `capabilities`；命中但本层没有能力 → 记入 `unanswerable_ku_ids`，内部各层给存根（与 `search_blocked` 相同），客户层什么都不给；研发层里同事未授予的 L3 知识同样只给存根（可读条件沿用 Q2.5 的 `can_read`）；
  4. 提示只从本层视图算：查询里出现本层视图的槽位取值、现象或已发布产品时，给「相关条件：设备」「相关产品：HY-LV205」。
  写一条 `retrieve` 事件（payload 同 `search`，加 `unanswerable_ku_ids`、`n_unanswerable`）。研发层另带本层候选，标「候选」。
- Agent 工具 `search_knowledge` 改调 `explore`；`search` 本身不变。
- **L1 回答用上授予的话**：`l1/answer.py` 的检索改调 `explore`，可用材料 = `units`（本层可读的结论，含现有的说明书、用法）+ `capabilities` 里授予收件层的 `statement`。离线模式按现有的拼接方式输出：结论原文，加上 `render_refs` 渲染出的 `statement` 原文；在线模式把 `statement` 以编号交给模型，模型只写 `[[编号]]`，回答经 Q3 的 `render_refs` 与 `leak_hits(audience=)` 后发出。渲染用到的 `statement` 写 `capability_used`（Q2）。问原理（`mechanism_request`）时，只要有授予收件层且命中的 `statement`，就用它回答，不再一律回「研发保密」；没有时照旧。撤销后它不在 `explore` 结果里，编号渲染也会被拒，回答回到「需要专业人员解答」。
- `qi_grant` 的 `n_unanswerable` 从 `retrieve` 事件按「结论 × 提问者层级」计数。
- **`qi_grant` 的第二种对象（从 Q2 移来）** `knowledge:grant:<ku_id>|L<k>`：某条已确认结论在第 k 层被检索命中、却没有任何能力，要授予的是一句**可说的话**（`statement`）。问题卡附那一层被问到的原话与结论的原文位置；研发 Agent 在线时照现有准备流程起草措辞，离线时没有草稿（与其他家族一致）；研发签字时把改定的措辞经 `sign_qi_grant(..., note=措辞)` 传入，先过 `leak_hits(audience=k)`，再新建一条 `statement`。这是「研发授权一句话给前台说，前台看不到机理」的通用入口。

**验收**：`test_wp_l` 加：客户层命中上层时的返回与「没找到」完全相同；L1、L2 只拿到本层内容、能力、提示与存根，不出现 L3 原文；L1 命中一条 L3 结论 → 觉提出 `qi_grant` → 研发签字授予一句话 → 同一个问题再问一次，**L1 回答的文字里出现这句话**、不出现结论原文 → 研发撤销 → 再问，回答回到「需要专业人员解答」。

### Q5.5 试样失败回路

`app.py`、`jue/state.py`、`config/templates/trial_rework.yaml`、`config/templates/ask_back.yaml`、`web/src/`、`ui/server.py`

现状有两个缺口：产品原因的失败已由 `knowledge_conflict` 处理，但**需求条件没问到导致的失败**、以及**客户评价不通过**之后都没有回路；工作面录入试样时 `cause` 还写死为 `"none"`（`app.py:1037`），原因根本进不来。

- **录入**：工作面的试样录入加「失败原因」选择（产品 / 设备 / 操作 / 需求条件缺失），选「需求条件缺失」时勾选缺了哪些槽位；客户评价不通过时，业务员可按客户反馈勾选缺失的条件。门面按 2.8′ 收参数，不再写死。
- **觉提出 `trial_rework`**：对象是需求单，属性 `n_missing`（失败或评价不通过所指向、且还没补问的槽位数）、`last_result`；前置条件 `attrs.n_missing >= 1`。研发签字 = 需求单退回到「已接单、待重新转译」，`requirement_state` 给这些槽位对象带上 `failed_on: true`（该槽位在最近一次失败或评价不通过的缺失清单里，且此后还没有新的回答）。只改打分不够：现有 `ask_back` 的前置条件要求未填、没答过「不清楚」且 `trans_splits >= 2`，失败暴露的条件往往不满足。所以 `ask_back.yaml` 的前置条件改为 `attrs.layer >= 2 and (attrs.failed_on or (not attrs.filled and not attrs.unknown and attrs.trans_splits >= 2))`，打分加 `0.5 * attrs.failed_on`：失败指向的条件，不论原来填过（可能填错）还是答过「不清楚」，都可以再被提出；回问的答案覆盖原值，`failed_on` 随之消失。觉照此提出回问，补上条件后重新转译。推进只来自觉提出的问题与签字，不在门面里顺手发回问（铁律 14）。
- **失败结果进入学习，但守契的规则**：「是哪个条件导致失败」是研发的判断（L3）。所以它：
  - 作为研发层回问（`ask_back`）的真实正例进入 Q6 的决策记录，重训后觉对这个条件更早提出回问；
  - 计入 `qi_grant` 的理由（属性 `n_trial_missing`，与 `n_ask_back` 并列）：同一现象反复因同一条件失败，觉提出 `qi_grant`（主人、签字人为研发），由研发决定要不要让前台直接问；
  - **不**直接成为客户层追问（`ask_slot`）的训练标签——要客户侧以后都问，只能经研发授予（设计第 10 节）。原计划写的「失败条件直接作为 `ask_slot` 正例」改为这样。
- 讲法：说「失败条件进入研发层的训练正例，并成为授予的理由」；样本少时统计门槛会让它回落规则，不说「觉已经学会了」。

**验收**：`test_wp_a3` 加：研发录入「需求条件缺失：设备」（设备在单上已填过）→ 觉提出 `trial_rework` → 签字后需求单回到待重新转译、觉对设备提出回问 → 回答后新值覆盖原值、不再提出；`test_wp_b1` 家族数 22。

### Q6 决策记录与觉的在线自进化

`jue/records.py`、`jue/train.py`（新，从 `scripts/train_jue_k.py` 移出训练函数）、`scripts/train_jue_k.py`、`eval/catalog.py`、`scripts/catalog_stats.py`

觉必须在系统运行中自进化，而且现在就要演示出来，不等企业试用（人的要求，v7.5）。做法是把已有的离线训练接成运行中的闭环：

- `decision_rows(records, events)`：一行 = 决策点、当时属性与 `p_need`、谁、怎么处置、后来的结果（回问、退回、试样及其原因与缺失条件、市场评价、复用拒绝、不立项）、用到的能力；`level` = 结果来自哪一层的判断（例如研发在需求单上回问某个槽位，这个结果算 L3）。纯函数，不落盘。
- **标签只有两种来源**：人的处置，以及与觉无关的结果（客户实际的条件、研发最终需要的信息、试样与评价）。Agent 和系统自己的决定永不当标签。模拟运行里「结果」来自需求卡的真值，复用 `sim/trajectory.py` 的 `ask_label`、`back_label`，不新写一套标注规则。
- `rows_for(rows, level)`：只留 `level ≤ k` 的行。觉在客户层提出的追问只用客户层的行来学，研发的回问学不成客户侧的习惯，只会成为 `qi_grant` 的理由（设计第 10 节）。
- `jue/train.py::fit(rows) -> model_dir`：把 `scripts/train_jue_k.py` 里的训练、校准、与规则比较三步移成函数（脚本改为调它，行为不变）；只对样本够的家族保存模型，其余照旧回落规则打分。本地 CPU，几秒到几十秒。
- **按家族分开训练，层级过滤落在家族上**（v7.8，模型文件格式已批准）：现有 Jue-K 是所有家族共用一个分类器、各家族一个校准器，L3 的行会经共用分类器影响客户层的分数，`rows_for` 管不住。改为每个家族一个分类器加一个校准器（`model.pkl` 里 `classifiers: {family: ...}`），每个家族只用 `rows_for(rows, 该家族所代表的层)` 训练：`ask_slot` 代表客户与业务员（≤ 1），`ask_back` 代表研发（3），其余按模板的签字人所在层。推理时 `JueK` 按问题所属家族取对应分类器，接口不变。第 0 天用现有训练数据按家族重训一次，与现有模型在 `docs/reports/jue_k/` 的指标上对照，不劣才替换。
- **换模型**：配置 `jue_k_dir` 指向新模型目录，续跑（Q6.5）时生效；演示脚本在进程内直接换 `app.jue_realtime`。不加「自动重训」的决策点，也不在门面里加重训入口。
- `catalog_stats.py` 按层级输出决策行数、处置与结果分布，并列出「人自发做了、觉没提」的决定（结构进化的原料，只统计，不自动生成模板）。

**验收**：`test_wp_b1` 加：决策投影的行与层级正确；研发回问产生的结果行在 `rows_for(rows, 0)` 里不出现。自进化的效果由 Q7 的 `demo_evolution.py` 证明，不进测试。

### Q6.5 可续跑

`app.py`、`events.py`、`bus.py`、`knowledge/records.py`、`knowledge/store.py`、`ui/server.py`

- 四个日志类的构造：文件已存在就逐行读回（事件、审计、积分照原样；问题按 id 取最后一个快照）。
- `HuayanApp.build(..., resume=True)`：不新建运行目录；读回 `sessions/*.json`、`requirements/*.json`；`_trials` 从有效状态里 `trial` 类知识的正文（试样 JSON）重建；知识与能力已在 `from_seeds` 加载状态文件时恢复。
- 不恢复：觉的推理轨迹 `_jue_trace`（原始记录在 `jue_samples.jsonl`，只影响界面上的轨迹显示）、回问答案到发言的映射 `_answers`（只影响界面上的引用跳转）、Agent 对话与待确认卡（`hub._pending`、`conversations/`，重启后对话从头开始，未确认的提议作废）。
- `ui/server.py` 加 `--run <id> --resume`。
- 编号（需求单、事件、问题、试样）都是「已有数量 + 1」，读回后自然续上，不另加计数器。

**验收**：`test_e2e` 里在主线中途（需求单已接单、产品已发布之后）用 `resume=True` 重建应用，余下步骤照常跑完，断言不变。Q7 的「重启」演示用这条路径。

### Q7 决赛主演示与 V6 对照

`scripts/demo_qi.py`（新）、`scripts/compare_v6_qi.py`（新）、`config/app.demo.qi.yaml`（新）、`docs/reports/qi_demo/`、`README.md`、`docs/VISION.md`、`docs/PITCH.md`、`docs/QI.md`

- **`demo_qi.py`**（离线配置，状态文件放本次运行目录）：
  1. 建应用后在进程内编译 `seeds/rag`（录制的提议，调用 `admit(..., kb)`）；
  2. 三态：同一句客户话「锦氨在经轴缸上染出来深一块浅一块」，A 未授予（R01 已确认 C4，只在研发开工门槛要求 pH）→ B R01 签 `qi_grant` 授予 K3 → C 撤销 K3，记录每一态客户是否被追问 pH、问原理时得到什么；
  3. 四步：C05 → C07 → C08 与「只说锦纶氨纶」→ 撤销 K5 / 改 RPT-044 后 `recheck_evidence`；
  4. 重启：用 `resume=True` 重建应用（Q6.5），重放 C07 的问题，并确认未办完的需求单与积分都还在。
  每一步的结论从事件日志读出，写进 `docs/reports/qi_demo/demo.json` 与一页 `demo.md`，不写死文案。
- **`compare_v6_qi.py`**：问题批次（按时间排序的模拟问题，含 C05、C07、C08 的同类问题若干，以及每个问题的「研发判断」）与五个指标的统计函数两边共用；两个驱动函数各自只调用本版本已有的接口：契的驱动用 `decline_project(..., claim_ids)`、`extend_scope`；V6 的驱动在 `351c2c9` 的 worktree 里运行，研发判断与产品不相容时按 V6 的真实做法不带产品不立项。指标：正确的自助处理数、研发重复参与次数、未经授权的确定推荐数（确定推荐没有落在研发判断写定的任何完整情境内）、撤销或失效后的行为、重启后的授权状态；另按时间窗画「每解决一个客户问题需要几次研发判断」（VISION 6.2 的衡量指标，由授予机制算出，不是学习曲线）。报告写进 `docs/reports/qi_demo/compare.md`，注明数据为模拟、处置为脚本写定。
- **`demo_evolution.py`（觉的自进化）**：同一个应用、同一批按时间排序的模拟客户，分四个窗口跑：
  1. W1 用现有 Jue-K；W2 起世界偏离专家先验（`sim.shifted_world`，偏离程度 λ 如实列出），客户的真实条件分布变了；
  2. 每个窗口结束，从这一窗口的决策记录取结果标签，`rows_for` 过滤后 `fit`，换上新模型进入下一窗口；
  3. 对照组是冻结在 W1 的觉，跑同一批客户（同一随机种子）；
  4. 每个窗口报：应升级的单进研发时必问信息完整率、研发退回比例、每解决一个客户问题需要几次研发判断、平均追问次数；
  5. **安全对照，分两层报告，结果照实写，不预设**：
     - **结构层**：未授予 K3 时，色花的 pH 在客户层视图里既不是必问条件，也不区分任何候选，`ask_slot` 的前置条件不成立，模型分数再高也提不出来。用「不过滤训练出的模型」跑同一批客户，统计客户层 pH 追问次数，预期为 0；授予 K3 后才出现。这说明客户层能问什么由视图决定，学习改不了。
     - **校准层**：对前置条件已经成立的槽位，比较「按层过滤」与「不过滤」两种训练下，客户层追问的排序与次数有没有被研发层的结果带偏，报告差异，不预写结论。
     同时记录：研发反复回问 pH 的那些行，在过滤下只进入 `qi_grant` 的理由（觉提出授予请求，由研发签字决定）。
  报告写进 `docs/reports/jue_evolution/`，注明：世界与客户是模拟的、偏离程度是假设、标签来自模拟世界的结果。**真实数据版本**：用 Q4.5 从真实产品目录起草并经人审定的种子作为世界（真实的产品与适用结构），在现场机器上跑同一脚本，报告不入库。
- **材料**：按 1.1 更新 `docs/QI.md` 第 12 节（并删去该节开头的校正注）与 PITCH 的演示台词；VISION 1.2 证据表里已实现的行改为「已实现」并指向测试与报告；README 加一节「契」（三句话 + 演示命令 + 报告链接）。

**验收**：两个脚本在离线配置下从头跑通；报告里的数字能用事件日志复算。

### Q7.5 真实案例回测

`scripts/backtest_cases.py`（新）、`eval/backtest.py`（新）

把「指标是模拟的」变成真实数字的唯一办法。案例收集现在就开始（见 `REPLAN-v7-after.md` 第 1 节），脚本在 Q6 之后写，测的是最终版的觉。

- **案例格式**（`data/backtest/cases.yaml`，不入库）：每条 `{id, source, first_words, final_conditions: {槽位: 取值}, late_conditions: [槽位], phenomenon}`。`source` 取 `oral`（研发口述）、`raw`（案例里留有客户原始描述）、`restored`（研发按案例还原的客户最初说法）、`summary`（需求概述去掉工艺条件），四种分开统计。
- **防标签泄漏（铁律 5）**：标注开始前冻结词表（`slots.yaml`），报告写明冻结时的文件指纹与时间；冻结后新增槽位必须由一线研发凭业务常识提出并记录时间；看过回测答案后不改词表、不改模板。口述案例只做测试，不进训练。
- **跑法**：`first_words` 作为客户第一句话进入 L1 抽取；模拟客户按 `final_conditions` 如实回答被问到的条件（复用 `sim/customer.py`）；觉照常提出追问，由会话按槽位问法问出；需求升级时统计。
- **指标**：
  - 觉在第一轮就对 `late_conditions` 提出追问（后来导致补样或返工的条件）的比例；
  - 需求进入研发时必问信息完整率；
  - 同一批案例上的两个对照组：业务员原样转述（现有失真对照的转述组）、**真实强模型的一次性翻译**（经网关，caller `eval:one_shot`，不再用规则实现）；
  - 冻结的觉与 Q6 进化后的觉各跑一次——这就是「自进化在真实案例上有没有用」的答案，不利的结果照实列出。
- **问答样例**：终赛的业务问答样例做一张 L0 / L1 / L3 的回答与归属对照表（同一问题三个身份看到什么、依据谁的知识），不和别的系统比准确率。
- 报告写进 `data/backtest/report.md`（本地）；能否公开、公开哪些汇总数字，按组委会的保密边界定。

**验收**：用口述案例（哪怕只有 5 条）跑通一次，报告写明样本来源、输入类型、样本量、口径与不利结果。

### Q8 独立审查

照 V6-3.1：由一个没参与实现的子代理只读审查，对照 AGENTS.md 铁律、本文第 0.2 节与设计第 13 节「边界与措辞」。重点查：有没有绕开视图读种子做判断的地方；有没有能力之外改变下层行为的写入；有没有防御代码和只为测试存在的分支；Agent 能否写出不经渲染的专业结论。阻断与应修项按最小修改修复，不新增测试、不改契约，结果补进本节。

## 4. 测试：仍是 11 个，场景写进现有测试函数，只用 `mini_seeds`

| 测试 | 新增场景 | 所在包 |
|---|---|---|
| `test_wp0` | 不改：种子产品带第 0 天情境，四步关系照旧成立 | Q1 |
| `test_wp_a1` | 给 T-205 再授予一个「涤纶 × 气流染色机」情境后，「锦纶氨纶 × 气流染色机」不命中 T-205；部分条件为 possible、全知为 confirmed；配方不能作下层依据；未授予的 L3 结论不改变客户层视图 | Q1.5、Q2 |
| `test_wp_t` | `render_refs` 换编号与拒错层编号；`leak_hits` 不传 `audience` 逐条不变，传入后拦截上层结论 | Q3 |
| `test_wp_l` | `explore` 客户层无存根无提示；L1/L2 只得本层 | Q5 |
| `test_wp_a3` | 授予/撤销追问（色花 × 环保要求）；撤销解密；撤销情境后各调用方不再推荐；批准；依据他人结论被拒；重启保留；被使用记分；编译、候选不可读、指纹变化 → 挂起与复核；需求条件缺失 → `trial_rework` → 回问；同层研发只见存根、用到可见并记引用、申请 → 授予 → 可读并记 `shared`、撤销、配方可授予 | Q2、Q2.5、Q4、Q5.5 |
| `test_wp_b1` | 家族数 22；`auto_action` 两种；决策投影与层级过滤 | Q2、Q5.5、Q6 |
| `test_e2e` | 第 0 天迁移后主线结果不变；主线中途续跑 | Q1、Q6.5 |

桩仍只有 `MockGateway`、`MockSystem1Client` 和 `mini_seeds`（含新加的 `rag/` 子目录）。四步演示由 Q7 的脚本证明，不进测试（与设计第 13 节测试表的 `test_e2e` 一行不同，见第 7 节）。

## 5. 检查点

| 完成 | 必须成立 |
|---|---|
| Q1 | 11 个全绿且断言不改；离线主线与 `351c2c9` 基线一致；`update_applicable`、`extend_solves` 已删除；视图里没有 `applicable` |
| Q1.5 | 「锦纶氨纶 × 经轴」可被研发授予并经产品经理批准；只给部分条件时卡片列出待确认条件；`demo_routes.py` 照常跑通 |
| Q2 | 三态在测试里成立；重启保留；家族数 21 |
| Q2.5 | 研发检索同事的 L3 知识只得存根；单子上用到的可见并记引用；申请经归属人授予后可读并记 `shared`，撤销后不可读；`test_wp_t` 断言不改；家族数仍 21 |
| Q4 | `compile_qi.py --proposals seeds/rag/proposals.yaml` 跑通；改一段原文即挂起 |
| Q4.5 | 用公开资料起草出的种子经人补齐后，应用能启动 |
| Q5.5 | 失败原因能录入；需求条件缺失时觉提出 `trial_rework` 并回问；家族数 22 |
| Q6 | 运行中重训一次、换上新模型，觉的追问分布随之改变 |
| Q6.5 | 主线中途续跑，结果不变 |
| Q7 | 三份报告（主演示、V6 对照、自进化）生成；VISION 1.2 的状态更新 |
| Q7.5 | 口述案例回测跑通，报告含不利结果 |

任何一个检查点不成立，先修，不往下做。

## 6. 不做

- `phrase` 的入口与业务员说法授予（1.2）；`translation` 建行（同层直接用）。
- `public_points` 建 `statement` 行：发布前不对外，发布后随说明书成为 L0 结论。
- 人写人签的下行文字（退回理由、不立项理由、复用说明）改成编号渲染：保留现有 `leak_hits`。
- Jev 第三问（依据核对）接入 `scope_update`；`qi_grant` 由 Agent 起草。
- 增量编译、热加载、原文快照、在 RAG 侧写标签、让模型定级或建议降密、遍历企业 RAG 全库。
- 追问提示的探索比例；自动生成新的决策模板；用脚本写定的人的处置当标签画学习曲线；说「觉在真实数据上越用越准」。
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
| 12 | 追问提示留一小部分探索比例；Jue-K 训练行按层过滤；决赛不报学习曲线 | 探索比例不做；按层过滤并在运行中重训觉，用结果标签与冻结模型对照（Q6、Q7） | 人要求自进化现在就可见；结果标签与觉无关，不是循环论证 |
| 13 | 种子里没有归属人的条目登记到配置指定的维护人 | 确认人统一记为 `"seed"`，不加配置项 | 第 0 天授予是历史默认，不代表某人确认过 |
| 14 | 有效状态只含结论、能力、片段密级表 | 还含运行期新增的全部知识与发布的产品；默认放运行目录 | 真实运行要续跑（1.4） |
| 15 | 种子由人编写，新概念只进编译报告 | 新增 Q4.5，从公开资料起草种子草稿，由人审定 | 真实企业没有现成种子（1.4） |
| 16 | 测试表：`test_e2e` 跑通决赛主演示四步 | 四步由 `demo_qi.py` 证明；`test_e2e` 只守第 0 天不变与续跑 | 测试只用 `mini_seeds`，四步依赖演示数据 |
| 17 | 测试的适配器指向 `tests/fixtures/` 下的小目录 | `tests/fixtures/mini_seeds/rag/`，按 T-205 与现有槽位写 | AGENTS.md 只允许 `mini_seeds` 一份夹具 |
| 18 | 视图里的产品带汇总的适用字段（隐含） | 视图里的产品 `applicable` 置空，只看 `situations` | 防止汇总字段被当成适用判断 |
| 19 | 决赛：「重启应用后 K5 仍是撤销或挂起状态」 | 用续跑（Q6.5）重启，同时验证未办完的工作也在 | 真实的重启就是续跑 |
| 20 | 结论按密级读：L3 结论所有研发都能读，「可用不可见」只对下层成立 | 同层也「可用不可见」：研发只读自己的和被授予的 L3 知识，工作中用到的可见并记分，想看原文向归属人申请（2.10、Q2.5） | 访谈：转化语言是每位研发自己的价值，研发之间共享应有补偿或互换（第 13 节） |

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

## 10. 第二轮独立审查（能否开工）与真实公开资料（v7.4）

结论是「改完以下几处再开始」，6 处已全部并入：

| # | 问题 | 处理 |
|---|---|---|
| 1 | 状态文件「多次运行共用」与 v7.2 冲突：第二个新运行会报「该产品已经发布」（`app.py:1096`），试样知识按数量编号会被覆盖 | 删掉共用；接着上次一律走 resume（2.6） |
| 2 | 编译结果怎么进应用没写清：应用整份保存会冲掉脚本写的文件；`admit` 拿不到现有能力 | `admit(proposals, sources, kb)` 经知识库写入；脚本只在应用停着时跑，演示在进程内调用（Q4、Q7） |
| 3 | 「段」没定义：CSV 没有空行、多行单元格按行会被切断 | md 按空行、csv 每条记录一文档每列一段；`fetch(doc_id, span=None)` 取全部段（Q4） |
| 4 | `qi_grant` 第二种对象放在 Q2 永远触发不了、也没人验收 | 挪到 Q5，措辞经 `note` 传入，`test_wp_l` 验收（Q2、Q5） |
| 5 | 发布新品会被「授予人即确认人」规则拦下 | 发布的适用能力依据 `ku:sheet:<pid>`，`_put_product` 设 `confirmed_by=owner`（Q1） |
| 6 | Q4.5 草稿三处不可行：词表在资料里没有原文会全被丢；`load_seeds` 要六个文件且 `causes` 必填；型号重复 | 词表不核对、标「无出处」；写出空文件；重复型号加产品ID（Q4.5） |

审查还指出、已顺手补上：Q6.5 的「不恢复」补上 Agent 对话与待确认卡。

**人提供的真实公开资料**：一家企业官网的染色系列产品目录（CSV，177 条、168 个型号、16 个分类），放在 `data/finals/public/catalog.csv`，不入库。核对过的事实：

- 每条都有产品简介（离子性、pH、用途、用量）与来源页面，可以直接作为公开来源（L0）读入，按产品ID 分文档；
- 9 个型号重复出现，其中 4 个同号不同品；
- 能起草出：型号、名称、品类、说明、用量、资料里写明的适用纤维与染料类别，以及可推断的适用现象（匀染剂对应色花、固色剂对应牢度差，需人确认）；
- 起草不出：设备条件（简介里没有一条提到溢流、气流、经轴、卷染）、现象、必问条件、客户口语说法、先验、归属研发、机理、内部依据；
- 所以它能真跑 Q4.5（起草种子）与 Q4（公开来源编译、客户层原样引用）；决赛的三态与四步仍要内部资料（缺时用模拟的内部资料，界面与报告标明），对照数字仍来自模拟问题。由它产出的一切都不入库（铁律 7）。

## 11. 觉的自进化现在就要演示（v7.5）

人的要求：觉不可能等企业试用才开始重训，必须演示出自进化能力。原计划（与 VISION 6.2、第 7 节一致）只演示「能力进化」（`qi_grant`），把「校准进化」留到影子模式，理由是模拟业务周里人的处置由脚本写定，拿它画曲线是循环论证。

这个理由只排除「用脚本写定的处置当标签」，不排除自进化本身。改为：

- **闭环在系统里真实运行**：运行 → 决策记录 → 结果标签 → 按层过滤 → 本地重训 → 换上新模型 → 下一窗口行为改变（Q6）。
- **标签用结果，不用脚本写定的处置**：模拟世界里客户的真实条件、研发最终需要的信息，与觉怎么判断无关。这与 `docs/reports/jue_k/` 已报告的学习曲线是同一种证据，只是从离线批量训练变成了运行中的闭环。
- **对照冻结模型、世界中途偏离**：只有世界偏离专家先验时，学习才有东西可学（`JUE_K_TRAINING.md` 第 12 节：先验准确时 Jue-K 与规则持平）。所以演示让世界从 W2 起偏离，看进化的觉与冻结的觉在同一批客户上的差别；偏离程度是假设，整条如实列出。
- **三层自进化都有当场可见的东西**：能力进化（`qi_grant`，研发授予后一线自己解决）、校准进化（重训后追问更贴近研发需要）、结构进化（列出「人自发做了、觉没提」的决定，只统计）。
- **觉学不到没被授予的东西**：靠两层保证——客户层能提出的追问由视图决定（未授予的条件过不了前置条件），学习只校准已经能提的追问且按层过滤；两层都在 Q7 的安全对照里实测（v7.8 修正：原写「去掉过滤就会问 pH」，与前置条件矛盾）。
- **真实数据**：世界结构可以换成真实产品目录起草出的种子；客户行为与结果仍是模拟的。

可以说：觉在运行中按结果重训、换上新模型；世界偏离专家先验时，进化的觉比冻结的觉更快把研发需要的信息问全；觉的学习按层过滤，学不到没被授予的东西。
不能说：觉在真实客户上越用越准（要真实处置数据）；偏离程度、增益幅度是真实世界的数字。

VISION 6.2「校准进化」的现状、第 7 节与第 10 节、PITCH 第 7.5 节与第 13 节、`docs/QI.md` 第 10 节的相应说法已同步改写。

## 12. 并入契之前的决赛行动计划（v7.6）

契之前有一份决赛行动计划（内部材料，不入库）。逐项判断后：

- **已被 v7 取代**：C′ 路径给研发记分（v7 Q2：适用能力被使用时研发与产品经理各记一份）；企业 RAG 只换检索排序（v7 改为适配器接入）；终赛数据流水线的大部分（v7 Q4、Q4.5）。原计划里「实验案例写进种子当 L3 知识」与契冲突，不采用：内部资料留在适配器后面。
- **并入 v7**：
  - 试样失败回路 → Q5.5。原计划写「失败条件直接作为客户层追问的正例」，按契的规则改为「研发层回问的正例 + 授予的理由」。
  - 真实案例回测 → Q7.5，加上「冻结的觉 vs 进化的觉」一组。
  - 终赛资料四类入口与归属「待认领」 → Q4、Q4.5。
- **v7 之后或与 v7 并行**：见 `REPLAN-v7-after.md`。

## 13. 研发之间的知识边界（v7.7）

**问题**：契的「研发的知识不给你看，但可以授权给你用」原本只对下层成立。研发之间按层级共读 L3：任何一位研发检索就能读到同事的全部转化知识、机理和配方原文，而检索不记分，只有在需求单条目里被正式引用、经技术确认时才给归属人记一次「被引用」（`app.py` 的 `confirm_translation`）。也就是说，同事可以随手翻、记住、换成自己的话再写，归属人一无所获。

**为什么必须改**：访谈（`docs/reference/interview_notes.md`）说得很清楚：

- 第 2 节：实验报告已做成共享的知识库，但「场景需求 → 专业语言」的转化「存在每个研发人员的脑子里」。化言沉淀和记分的正是这套转化知识，它今天在研发之间并不共享；
- 第 5 节：转化能力是「研发的存在价值」，交出去研发可能被替代；研发之间共享知识盲点「也应有补偿，例如积分奖励或互换知识」。

所以不能拿「研发内部本来就共享资料」来解释：共享的是报告，不是转化知识。不改的话，化言会让研发最在意的那部分知识在同事之间变得免费可读，与「权责对等」相反。

**做法**（2.10、Q2.5）：同层也「可用不可见」。

| 情况 | 研发看到什么 | 归属人得到什么 |
|---|---|---|
| 工作中用到：转译引擎为单子引用了同事的知识 | 单子上的原文 | 技术确认时记「被引用」（现有） |
| 随手检索 | 只见归属：「R01 持有相关转化知识（L3）」 | 无，因为没有读到 |
| 想看原文 | 申请 → 觉在总线上提出「需要归属人决定是否授予」→ hub 派给归属人的研发 Agent，Agent 告知归属人 → 归属人在工作面上签字授予后可读，可随时撤销 | 每次授予记 `shared` |
| 自己的知识 | 全文 | — |

对下层授予给「某一层」，对同事授予给「某一个人」，是同一种能力；解密授予给某一位客户，已经是这种用法。配方也走授予，给不给由研发本人决定。

**答辩口径**：可以说「研发的知识对下层可用不可见，对同事也一样：用到才看、看了就记功、想看原文要本人同意」。不能说「每个人的知识只有自己能看」：转译引擎（系统）用全部知识起草，单子上用到的会给接单研发看。

## 14. 开工前审查（v7.8）

Codex 对照计划、契约与 `351c2c9` 的代码只读审查（基线 11 个测试全绿），结论是方向可落地、先补清以下边界再从 Q0 开工。逐条核实属实，按最小修改并入：

| # | 问题 | 处理 |
|---|---|---|
| 1 | 申请查看要 `ku_id`，存根 `BlockedHint` 只有归属人、层级、类别，同一研发的多条知识分不开 | `BlockedHint` 加 `ku_id`，只在同层研发的存根上填，跨层与客户层不给（2.1、2.10，**契约改动已批准**） |
| 2 | 只隐藏「引用的知识」不够：`requirement_view` 对所有研发返回完整需求单，L3 条目正文就含转化知识 | 非接单研发与 L2 同样裁剪：看不到 L3 条目正文、假设、封存项、草稿；`engine_refs` 例外只对接单研发（2.10、Q2.5） |
| 3 | 只改打分不够：`ask_back` 前置条件要求 `trans_splits >= 2` 且未填、未答不清楚，失败暴露的条件提不出来 | 前置条件加 `attrs.failed_on` 分支，填过或答过不清楚的也能再问，答案覆盖原值（Q5.5） |
| 4 | Jue-K 共用一个分类器，`rows_for` 隔离不了层；安全对照预写「不过滤就会问 pH」，与 `ask_slot` 前置条件矛盾 | 每个家族一个分类器、按家族所代表的层过滤训练行（Q6，**模型文件格式已批准**）；安全对照改为结构层与校准层两组实测，不预设结果（Q7、第 11 节） |
| 5 | 授予的 `statement` 进了 `ExploreResult.capabilities`，L1 回答却只用 `units`，前台用不上 | L1 回答的材料加上授予收件层的 `statement`，经 `render_refs` 渲染并记 `capability_used`；验收看实际回答文字与撤销后的回答（Q5） |
| 6 | Q2「重建应用后保留」依赖 Q6.5 的续跑 | Q2 改为在知识库层验收，应用级重启留到 Q6.5 |
| 7 | Q5 要改 `sign_qi_grant`，允许修改范围没列 `app.py` | 补上 `app.py` 与 `prompts/l1_answer.md` |

没有扩大功能范围；家族数、测试数不变。
