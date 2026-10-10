# WP-A3 转译流程、权责与回流、解密审批

> 负责：A｜时段：3:30–5:00｜分支：`dev/a`

## 目标
把 L1 解决不了的需求走完分层转译的流程：产品经理确认 L2 → 研发确认 L3、把修改沉淀为自己的知识 → 试样 → 反向包装 → 新品发布回 L1。在这条流程上落实**权责对等**：引用即记分、贡献可沉淀、上层知识对下层只显示归属不显示原文、解密由研发本人审批。

## 依赖
WP-A2、WP-T（转译函数）。WP-T 未合并时，先用 `MockGateway` 的 `canned` 返回固定的 `PMDraft` / `RDDraft` 开发流程。

## 必读
`CONTRACTS.md` 第 ②（2.4、2.5 积分规则）、⑥、⑦ 全节、⑫ 节；`ARCHITECTURE.md` 第 3 节（可见性与解密例外）、7.2 节～5 节。

## 允许修改的范围
`src/huayan/escalation/flow.py`、`src/huayan/escalation/__init__.py`、`src/huayan/app.py`（只增加 L2/L3 方法）、`scripts/demo_escalation.py`、`tests/test_wp_a3.py`

## 交付物与已定设计

### 1. 门面方法（`app.py`，按契约 ⑫）
- 转译函数的 `gateway` 参数：`gateway_mock` 为 true 时传 `None`（规则模式），否则传网关。
- **L2**：`draft_requirement`（只允许 pm）调用 `translate.draft_product_need`，`Requirement(status="draft", drafted_by="agent:pm")`；`confirm_requirement` 可传入修改后的 `PMDraft`，状态 `pm_confirmed`，记 `requirement_confirmed` 事件，关联问题 resolve。
- **L3**：`translate_requirement`（只允许 rd）调用 `translate.draft_chem_need`；`confirm_translation` 可传入修改后的 `RDDraft`，状态 `rd_confirmed`，记 `requirement_translated` 事件，并给两层 `ku_refs` 所引知识的归属人各记一次 `cited`（同一需求单内同一知识只记一次）。
- **沉淀**：`contribute_translation` 调用 `flow.contribute_translation`（契约 7.2）。界面上研发改完一条后点「沉淀为我的转化知识」即调用它；之后同类需求的 L3 转译会命中这条新知识。
- **视图**：`requirement_view(req_id, viewer_id)`：L1 抛 `PermissionDenied`；L2 的 `cited` 中 L3 知识 `text=None`；L3 全部可见；`quotes` 给出所有引用轮次的原话。`requirements(viewer_id)`：L1 抛 `PermissionDenied`。
- **贡献看板**：`contributions(viewer_id)` 由积分账本与知识库汇总，按 `owner, ku_id` 统计被引用次数、积分、被哪些需求单 / 会话使用；非 L3 查看者看到的 L3 知识标题替换为「研发 X 的转化知识」。
- **试样**：`record_trial` 只允许 L3；生成一条 L3 `trial` 知识；通过时记 `trial_pass`；记 `trial` 事件。
- **反向包装与发布**：`package_sheet`（只允许 pm）调用 `translate.package_sheet`，输入只有产品需求与研发填写的对外要点；`release_product` 按契约 7.2。传入的 `Product` 由界面预填：种子里覆盖该需求的 `status: project` 产品（机理、配方要点来自它），`sheet`、`usage` 用包装结果。
- **解密**：`request_decrypt` 仅当会话已有推荐、且 `profile.chem_savvy and profile.asked_mechanism` 时允许，发布 `decrypt_request` 问题，`owner_id` = 产品归属研发，审计 `decrypt_request`；`decide_decrypt` 只有 `owner_id` 本人可以审批，通过时生成 `DecryptGrant`、审计、记事件，之后该会话 L1 视图的卡片按新上限渲染 `full_mechanism`（不含配方）。

### 2. 演示脚本 `scripts/demo_escalation.py`
离线跑完：升级会话 → L2 起草与确认 → L3 起草、修改一条并沉淀、确认 → 试样 → 包装 → 发布 → 新会话同样的描述 → L1 命中新品；打印每一步的需求条目（带原话与依据）和积分变化。

## 验收
1. `tests/test_wp_a3.py` 只有 1 个测试（小种子、离线、转译引擎规则模式）：「气流缸」会话升级 → L2 确认 → L3 确认 → `rd:R02` 沉淀一条 → 试样 → 包装 → 发布 `T-206` → 新会话 L1 推荐 `T-206`；断言：
   - `rd:R01`、`rd:R02` 都有 `cited` 积分，`rd:R02` 有 `contributed` 积分；
   - `requirement_view` 对 `pm:P01` 时，L3 知识的 `text` 为 None，对 `rd:R01` 不为 None；对 `sales:S01` 抛 `PermissionDenied`。
2. 手动：解密流程——客户说「我懂一点，这个是靠控制 pH 降低上染速率吧？原理能讲讲吗」→ 申请 → 研发审批 → L1 卡片出现机理、不出现配方要点（贴输出）。

## 不做
转译函数本身（WP-T）；真实 ELN；多级审批流；需求单编辑历史；积分兑换。
