# WP-C 第 0 步：v5.3 接口样例

全部为手工构造的模拟数据，仅供 WP-U2 开发工作面；不是业务门面运行结果、模型评分或验收证据。冻结契约未修改。研发案例、转化知识的 `fixture` ID 仅在这些样例中有效；复用场景不代表 D17 支线种子已经交付。

在项目根目录生成：

```powershell
uv run python web/src/fixtures/generate.py
```

生成器直接构造现有 Pydantic 契约模型，使用 `model_dump(mode="json")` 导出；时间来自固定起点的 `SimClock`（UTC+08:00）。不调用模型、业务流程或网络。

| 文件 | 读取路径 | 契约 / 用途 |
|---|---|---|
| `sales_workbench.json` | `scenarios.<名称>.session` | `SessionView`，对应 `view_session` 返回值 |
| 同上 | `scenarios.<名称>.questions` | `list[Question]`，对应该业务员的 open 问题 |
| `rd_workbench.json` | `scenarios.<名称>.requirement` | `RequirementView`，对应 `requirement_view` 返回值 |
| 同上 | `scenarios.<名称>.questions` | `list[Question]`，对应该研发的 open 问题 |
| 同上 | `scenarios.<名称>.leak` | `list[LeakHit]`，对应 `leak_check` 的说明书／用法检查结果，只含句序号和类别 |
| `jue_timeline.json` | 根对象 | `JueTimeline`，对应 `jue_timeline` 返回值 |

`simulated`、`scenarios`、`label` 只用于样例文件组织和选择场景，不是新增接口字段，也不是未来 HTTP 接口的包装约定。各场景是独立快照，不能拼接为同一时刻的响应。接真实接口后移除运行时 fixture 引用。

业务员场景：

- `asking`：槽位追问提示、回复草稿。
- `escalation_ready`：升级说明和待签升级问题；尚未升级。
- `pending`：复用审定中；仅有产品名与状态，`customer_note`、`basis`、`usage` 为空，无推荐卡。
- `adopted`：研发审定后有公开说明、用法及知识归属标签，推荐卡标明研发 R02 审定。业务员不签复用；两个复用快照的 `questions` 都不包含研发的待签问题。

研发场景：

- `reuse_pending`：查看完整复用建议、L2 案例原文，复用问题待研发签字。
- `preparing`：另一条新产品线程，产品经理 Agent 正在准备 L2；`prepared_at=null`，不展示签字按钮。
- `points_ready`：该新产品线程后续快照，含原话、L2/L3 条目、引用归属、研发假设、沉淀草稿、封存／放出草稿。`prepared_at` 有值代表草稿准备完成，不保证能通过签字校验；第 2 句自查命中须改写，句序号从 0 起。当前 `sealed` 仍为空，拟封存内容在 `points_draft.sealed`。
- `sheet_leak`：再后续的说明书改写场景；已签字的 `sealed` 有值，说明书第 2 句命中，`leak` 返回 `{index: 1, source: "sealed"}`。与两栏草稿的 `self_check` 分开，未包装说明书的场景中 `leak` 为空。
  同时保留两个 open 问题：`release` 由产品经理 Agent 准备、研发 R02 签字，说明书已准备所以处于待签；`seal_leak` 由研发 Agent 准备改写，处于准备中。泄密命中阻止发布生效，发布审定入口仍然存在；待签不代表可发布，最终由门面校验并返回拒绝原因。

收件箱保持接口原有 `questions` 列表，按 `prepared_at` 展示准备中／待签；不新增这两种问题状态，也不在前端计算业务可签条件。

时间线展示现成产品线程（研发视角）：追问 → 升级签字 → 复用审定签字。`ask_slot` 只出提示，不创建总线节点；规则分数显示阶跃与「规则」，Jue-K 显示曲线与阈值。前置条件不成立的 `p_need=null` 保留，不当成模型给出的 0 概率。`object_id` 保留状态对象前缀，节点用问题 ID 关联。

时间线的分数、7 次判断、2 个问题和 2 次签字全部是演示用设定值，`n_judgments` 不等于点数。`n_llm_calls=0` 也是本样例的设定；实际接口必须从计量器读取，不能沿用这里的常量。

本模块只交付数据与再生成方法；前端消费确认、权限门面实现、真实决策打分和全流程验收由后续模块完成。
