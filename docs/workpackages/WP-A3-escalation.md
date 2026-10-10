# WP-A3 转译流程、权责与回流、解密审批

> 负责：A｜时段：3:30–5:00｜分支：`dev/a`

## 目标
把 L1 解决不了的需求走完分层转译的流程：L2 起草与确认 → L3 起草、修改、沉淀、确认 → 试样与对外要点 → 反向包装 → 新品发布回 L1。在这条流程上落实**权责对等**：引用即记分、贡献可沉淀、上层知识对下层只显示归属不显示原文、解密由研发本人审批。

门面方法是**原子**的：每个方法一个动作，角色助手的工具一对一调用它们（契约 ⑭）。业务规则、权限与校验都写在这里，不留给工具。

## 依赖
WP-A2、WP-T（规则骨架）。

## 必读
`CONTRACTS.md` 第 ②（2.4、2.5 积分规则）、⑥、⑦ 全节、⑫、⑭ 节；`ARCHITECTURE.md` 第 3 节（可见性与解密例外）、7.2 节～5 节。

## 允许修改的范围
`src/huayan/escalation/flow.py`、`src/huayan/escalation/__init__.py`、`src/huayan/app.py`（只增加 L2/L3 方法）、`scripts/demo_escalation.py`、`tests/test_wp_a3.py`

## 交付物与已定设计

### 1. 门面方法（`app.py`，按契约 ⑫）
- **通用**：每个方法开头检查 `by` 的角色（不符抛 `PermissionDenied`）和需求单状态（不符抛 `ValueError`，消息写清当前状态和需要的状态——助手会把它原样读给模型）。
- **L2**：`draft_requirement`（pm）调用 `translate.draft_product_need`，`status="draft"`、`drafted_by=by`；`edit_req_item` / `remove_req_item` / `set_direction` 修改草稿；`confirm_requirement` → `pm_confirmed`，记 `requirement_confirmed` 事件，关联问题 resolve。
- **引用校验**（`edit_req_item` 内，大模型输出的真实边界）：`quote_refs` 必须是该需求单 `session_ids` 中的轮次；`ku_refs` 必须存在且 `by` 可读（`can_read`）。不合格抛 `ValueError`，不静默丢弃。层由 `by` 的角色决定：pm 改 `product_lang`，rd 改 `chem_lang`。
- **L3**：`translate_requirement`（rd）调用 `translate.draft_chem_need`，`chem_drafted_by=by`；`confirm_translation` → `rd_confirmed`，按「现象在 `solves` 中、已知槽位与 `applicable` 一致」关联种子中 `status: project` 的产品到 `product_id`（取 id 最小），记 `requirement_translated` 事件，并给两层 `ku_refs` 所引知识的归属人各记一次 `cited`（同一需求单内同一知识只记一次）。
- **沉淀**：`contribute_translation` 调用 `flow.contribute_translation`（契约 7.2）；之后同类需求的 L3 骨架会命中这条新知识。
- **对外要点**：`set_public_points`（rd，`rd_confirmed` 之后）写 `req.public_points`。这是 L3 内容流向下层的唯一出口。
- **视图**：`requirement_view(req_id, viewer_id)`：L1 抛 `PermissionDenied`；L2 的 `cited` 中 L3 知识 `text=None`；L3 全部可见；`quotes` 给出所有引用轮次的原话。`requirements(viewer_id)`：L1 抛 `PermissionDenied`。
- **贡献看板**：`contributions(viewer_id)` 由积分账本与知识库汇总，按 `owner, ku_id` 统计被引用次数、积分、被哪些需求单 / 会话使用；非 L3 查看者看到的 L3 知识标题替换为「研发 X 的转化知识」。
- **试样**：`record_trial` 只允许 L3；生成一条 L3 `trial` 知识；通过时记 `trial_pass`；记 `trial` 事件。
- **反向包装与发布**：`package_sheet`（pm）调用 `translate.package_sheet(req)`，结果写入 `req.sheet`；`save_sheet` 修改；`release_product`（pm，需 `req.sheet` 与 `req.product_id`）以种子中的 `product_id` 产品为底（机理、配方要点来自它），`sheet`、`usage` 用 `req.sheet`，调用 `flow.release_product`。
- **解密**：`request_decrypt` 仅当会话已有推荐、且 `profile.chem_savvy` 时允许（懂化学的客户本来就可以直接讲明白；是否看到机理仍由归属研发审批），发布 `decrypt_request` 问题，`owner_id` = 产品归属研发，审计 `decrypt_request`；`decide_decrypt` 只有 `owner_id` 本人可以审批，通过时生成 `DecryptGrant`、审计、记事件，之后该会话 L1 视图的卡片按新上限渲染 `full_mechanism`（不含配方）。

### 2. 演示脚本 `scripts/demo_escalation.py`
离线、直接调用门面：升级会话 → L2 起草、改一条、确认 → L3 起草、改一条并沉淀、确认 → 试样 → 对外要点 → 包装 → 发布 → 新会话同样的描述 → L1 命中新品；打印每一步的需求条目（带原话与依据）和积分变化。

## 验收
1. `tests/test_wp_a3.py` 只有 1 个测试（小种子、离线、规则骨架）：「气流缸」会话升级 → L2 起草与确认 → L3 起草 → `rd:R02` 用 `edit_req_item` 改一条并 `contribute_translation` → 确认 → 试样 → 对外要点 → 包装 → 发布 `T-206` → 新会话 L1 推荐 `T-206`；断言：
   - `rd:R01`、`rd:R02` 都有 `cited` 积分，`rd:R02` 有 `contributed` 积分；
   - `edit_req_item` 传入不存在的 turn id 抛 `ValueError`；
   - `requirement_view` 对 `pm:P01` 时，L3 知识的 `text` 为 None，对 `rd:R01` 不为 None；对 `sales:S01` 抛 `PermissionDenied`。
2. 手动：解密流程——懂化学的客户说「应该是 pH 没控住、上染太快，你们有没有匀染剂？」，推荐后说「原理直接讲明白就行」→ 申请 → 研发审批 → L1 卡片出现机理、不出现配方要点（贴输出）。

## 不做
转译骨架本身（WP-T）；助手与工具（WP-L）；真实 ELN；多级审批流；需求单编辑历史；积分兑换。
