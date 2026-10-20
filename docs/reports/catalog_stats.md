# 决策目录统计（目录飞轮的数据）

运行：`runs/week-w1-jue_k-handle`；注入清单：`data/week/w1/injections.jsonl`。

只报计数与比率，**不给阈值建议**：模拟业务周的处置由脚本定，按它调阈值是循环论证（REPLAN 4.5）。被忽略率 = dismiss / 提出；机会汇聚里产品经理 Agent 判断「不是同一件事」后的 dismiss 单列，不计入被忽略。误报率只对定时三类、且给出注入清单时计算：提出的问题中不对应正注入的比例。

| 模板 | 类 | 提出 | 签字 | 退回 | dismiss | 不是同一件事 | 自动关闭 | 未处置 | 被忽略率 | 误报率 |
|---|---|---|---|---|---|---|---|---|---|---|
| `accept_requirement` | 推进 | 16 | 1 | 0 | 0 | 0 | 0 | 14 | 0% | — |
| `ask_back` | 推进 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `ask_slot` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `confirm_translation` | 推进 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `contribution` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `contribution_pm` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `distortion` | 异常 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `escalate_need` | 推进 | 16 | 16 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `handoff_sales` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `knowledge_conflict` | 异常 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0% | 0% |
| `leak_risk` | 异常 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0% | 0% |
| `market_eval` | 推进 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `opportunity` | 推进 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0% | 0% |
| `qi_grant` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `qi_review` | 异常 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `release` | 推进 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `reuse_product` | 推进 | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `route_rd` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `scope_update` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `seal_leak` | 异常 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| `seal_points` | 推进 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0% | — |
| `trial_rework` | 推进 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |

## 决策行（按结果层级；觉在客户层的追问只学 L0 的行，研发的判断只成为授予的理由）

| 层级 | 行数 | 家族 | 处置 | 标签 |
|---|---|---|---|---|
| L1 | 580 | ask_slot 563，escalate_need 16，market_eval 1 | 未处置 563，sign 17 | None 563，1 17 |
| L2 | 3 | accept_requirement 1，opportunity 1，leak_risk 1 | answered 1，sign 1，freeze_access 1 | 1 3 |
| L3 | 6 | accept_requirement 1，ask_back 1，confirm_translation 1，seal_points 1，release 1，knowledge_conflict 1 | accept 1，answered 1，sign 3，update_sheet 1 | 1 6 |
| 无标签 | 30 | reuse_product 16，accept_requirement 14 | answered 16，未处置 14 | None 30 |

## 人自发决策（执行生效动作时同一对象上没有对应的已提出问题）

本次运行没有人自发决策（模拟业务周不产生 `human_decision`，C12）。

按「动作 × 对象类型」聚类、学出候选前置条件属于第 3 阶段，本次只记录数据。
