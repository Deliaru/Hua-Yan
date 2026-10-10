# WP-A3 升级回流与解密审批

> 负责：A｜时段：3:30–5:00｜分支：`dev/a`

## 目标
把 L1 解决不了的需求走完「产品经理 → 研发 → 新品发布 → 回到 L1」的闭环，并实现解密审批这个权限例外。

## 依赖
WP-A2。

## 必读
`CONTRACTS.md` 第 ②（2.4、2.5）、⑥、⑦、⑫ 节；`ARCHITECTURE.md` 第 3 节（解密例外）、7.2 节、4 节。

## 允许修改的范围
`src/huayan/escalation/`、`src/huayan/app.py`（只增加 L2/L3 方法）、`prompts/pm_draft.md`、`scripts/demo_escalation.py`、`tests/test_wp_a3.py`

## 交付物与已定设计

### 1. 产品经理起草 `escalation/draft.py`
- `draft_requirement(q, sessions, gateway, at)`：一次 `structured(..., PMDraft)`，caller `agent:pm_draft`。输入：升级会话的全部轮次（带 turn id）、槽位与原话、同现象案例、L2 转化对照。提示词 `prompts/pm_draft.md` 要求：产品语言写「需要什么样的产品」，化学语言写「研发要解决的化学问题」，**每条必须引用至少一个 turn id**。
- 离线模式（`gateway_mock: true`）：用 `MockGateway` 的 `canned`，按槽位拼一份规则草稿（`drafted_by="agent:pm"` 不变，界面标注降级）。
- 引用的 turn id 不存在的条目丢弃（真实输入边界）。

### 2. 门面方法（`app.py`）
- `draft_requirement`：只允许 L2/L3；生成 `Requirement(status="draft")`。
- `confirm_requirement`：产品经理可以传入修改后的 `PMDraft`；状态 `confirmed`，记 `requirement_confirmed` 事件；关联问题 resolve（`draft_requirement`）。
- `requirements(viewer_id)`：L1 抛 `PermissionDenied`。
- `record_trial`：只允许 L3；生成一条 L3 `trial` 知识；通过时给研发记 `trial_pass`；记 `trial` 事件。
- `release_product`：按契约 ⑦ 的 `release_product`；产品经理发布。传入的 `Product` 由界面预填：种子中有覆盖该需求的 `status: project` 产品就用它，没有就以需求单的 `known_slots` 作为 `applicable` 生成一个。
- `request_decrypt(session_id, by)`：仅当会话已有推荐、且 `profile.chem_savvy and profile.asked_mechanism` 时允许；发布 `decrypt_request` 问题，`owner_id` = 产品归属研发；审计 `decrypt_request`。
- `decide_decrypt`：只有 `owner_id` 本人可以审批；通过时生成 `DecryptGrant`、审计 `decrypt_approve`、记事件；之后该会话 L1 视图的卡片按新 cap 重新渲染为 `full_mechanism`（不含 formula）。

### 3. 演示脚本 `scripts/demo_escalation.py`
离线跑完：升级会话 → 起草 → 确认 → 试样 → 发布 `status: project` 的对应产品 → 新会话同样的描述 → L1 命中新品；打印每一步和积分变化。

## 验收
1. `tests/test_wp_a3.py` 只有 1 个测试：小种子离线，「气流缸」会话升级 → 起草（canned）→ 确认 → 试样 → 发布 `T-206` → 新会话 L1 推荐 `T-206`；`rd:R01` 积分 > 0；需求单每条都有 `quote_refs`。
2. 手动：解密流程——客户说「我懂一点，这个是靠调 pH 吧？原理能讲讲吗」→ 申请 → 研发审批 → L1 卡片出现机理、不出现配方要点（贴输出）。

## 不做
真实 ELN、多级审批流、需求单编辑历史、积分兑换。
