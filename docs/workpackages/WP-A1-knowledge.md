# WP-A1 知识库、权限、披露、审计与积分

> 负责：A｜时段：0:45–2:00｜分支：`dev/a`

## 目标
实现分级知识库与三处权限卡点中的两处（检索过滤、披露网关），以及审计和贡献积分。这是「L1 拿不到 L2/L3 内容」这条不变量的落点。

## 依赖
WP-0。用 `tests/fixtures/mini_seeds/` 开发和测试。

## 必读
`CONTRACTS.md` 第 0、①、② 节，第 ⑧ 节中 `retrieve`、`access_denied`、`access_frozen` 的 payload；`ARCHITECTURE.md` 第 3、6 节。

## 允许修改的范围
`src/huayan/knowledge/`（`__init__.py`、`store.py`、`permission.py`、`disclosure.py`、`records.py`）、`tests/test_wp_a1.py`

## 交付物与已定设计

### 1. 知识库 `knowledge/store.py`：`KnowledgeBase`
- `from_seeds`：每个已发布产品生成 4 条知识（`sheet`、`usage` 为 L1，`mechanism` 为 L3 且 `decryptable=True`，`formula` 为 L3），owner 为产品归属研发；每个案例一条 L2（`case`）；每条转化对照按种子层级一条。`status: project` 的产品不入库，只在 `seeds.products` 里供研发界面预填。
- 转化对照知识的 `title` = 原文（`scene_phrase`），`text` = 「原文 → 译文」，`phenomenon_ids` 取种子；这是转译引擎的主要候选知识。
- `list(actor, kinds, phenomenon)`（契约 v2 新增）：按层级过滤后列出，供转译引擎取候选知识。
- `products()` 返回当前已发布产品（结构化 `Product`），`add_product` 发布新品并生成 4 条知识，`update_applicable` 修改适用范围并写 `sheet_updated` 事件。
- **检索 `search`**：对全部知识打分（字符二元组重合度 + 现象匹配加分，够用即可，不上向量库）→ 分成「可读」与「越权」两组 → 只返回可读组的前 k 条；越权组中分数超过阈值的条目只写进 `retrieve` 事件（`n_blocked`、`blocked_product_ids`）。被冻结的人检索时，越权组直接视为拒绝并写 `access_denied`。
- `get`：越权抛 `PermissionDenied`，写审计 `deny` 与 `access_denied` 事件。
- `freeze` / `is_frozen`：冻结集合存在实例上。

### 2. 权限 `knowledge/permission.py`
`level_of`、`can_read` 按契约 2.3。只按层级判断，不引入角色权限表。

### 3. 披露 `knowledge/disclosure.py`
- `cap`、`render` 按契约 2.4。`render` 的各版本内容：
  - `product`：sheet；`product_usage`：sheet + usage；`full_mechanism`：+ mechanism；`internal`：+ formula + 该产品的 trial 知识。
- L2 查看者额外附上同现象的案例（`case`），作为 `CardSection`。
- `render` 内部再检查一次每个 section 的层级不超过查看者的 cap（这是唯一允许的「重复检查」，因为它守的是核心不变量）；超过直接抛异常，不静默丢弃。

### 4. 审计与积分 `knowledge/records.py`
`AuditLog`、`Ledger` 按契约 2.5，各写一个 JSONL；`Ledger.totals()` 供界面显示积分榜。积分原因按契约 v2 增加 `contributed`；`cited` 的去重规则（同一会话 / 需求单内同一知识只记一次）由调用方保证，`Ledger` 提供 `has(owner, ku_id, ref)` 方便判断。

## 验收
1. `tests/test_wp_a1.py` 只有 1 个测试（核心不变量）：在小种子上，以 `sales:S01` 身份对「配方」「机理」「色花」等 5 个查询检索，并对每个产品渲染 `cap` 允许的最高版本——返回内容中没有 level ≥ 2 的知识单元，且越权命中被记进 `retrieve` 事件。
2. 手动：分别以 sales / pm / rd 身份检索「锦纶氨纶 色花」，打印结果，三者明显不同（贴在汇报里）。

## 不做
向量检索、知识编辑界面、角色权限表、Jev 调用、会话逻辑。
