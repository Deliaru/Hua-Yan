# E7 验证问题交接给 v11

2026-11-03｜v10 基点 `c22a2cf`。v11 指队友正在开发的分支；本文供用户转交队友，接续时对照 v11 实现，不代表已通知到队友本人。原主线复跑已完成，下列新旧结果均来自实际运行。

## 运行口径与证据

- 原合成 dev 主线：31 事件、12 需求卡、7 注入（3 正例、4 困难负样本），不含 99 条常规背景。原输入与注入窗口逐字一致。
- 当前真实配置：Kimi-K2.6 做抽取与助手，Cloudflare clef-flash 做 Jev 及定时三家族评分，其他觉决策沿既有规则并如实计量；缓存关闭。只跑 `jue_proto/ignore`，预测结束后才载入注入金标核对。本轮 48 条抽取事件均为 `extracted_by=llm`，无 mock/fallback 记录。
- 本轮目录：`data/knowledge_v10/validation/E7-rerun-20261103-c22a2cf/`；原始日志位于 `result/runs/week-spine-week-jue_proto-ignore/`。`report.md`、`comparison.json` 保存对照与评分/对象属性证据；`result/summary.json`、`result/details.json` 及执行问题报告保存本次结果。旧运行与共享试用状态保留，专业签字及试样结果均为模拟。
- 历史报告：`data/knowledge_v10/validation/E7-preparation-20261103/`；工程定向验证：`data/knowledge_v10/validation/E7-engineering-online-20261103/run-112518/`。这些本地运行产物不入库，交接代码仓库时不能假定远端能访问。

## 已修复的工程问题：请 v11 对照实现

1. **派单编号指令互相冲突**：旧 hub 要求所有工具都用业务对象编号、不要问题编号，但 `propose_merge` 需要 `question_id`。`c22a2cf` 已分别标出 question_id/family 与 refs，并说明需求单/合并参数含义。
2. **业务员需求卡缺现象 ID**：`find_products` 要结构化现象 ID，旧 `get_need_card` 未提供。该提交通过门面 `agent_need_card` 补既有抽取结果，复用 `view_session` 权限与披露，不改冻结 SessionView，也不在下游重新理解原话。
3. **模拟查询仍走旧读取路径**：`eval/week.py` 的 query 改为与助手相同的 `kb.explore`，补齐已有不可答事件信号。没有改排序、阈值、模板、注入窗口或金标。

v10 本轮全量离线 75 项通过（37.69s）；此前 14 次真实 Kimi 定向测试中，业务员正确传现象 ID、PM 正确使用 q:7 保存合并草稿。该定向结果不与本轮主线混为同一分母，也不表示模型参数错误归零。

代码入口：`src/huayan/agent/hub.py`（派单）、`src/huayan/agent/tools.py`（参数与工具）、`src/huayan/app.py::agent_need_card`（需求卡投影）、`src/huayan/eval/week.py::run_week`（模拟查询）；发现特征与评分分别在 `src/huayan/jue/state.py`、`src/huayan/jue/proto.py`，模板位于 `config/templates/`。

## 本轮复跑已出现的助手问题

两条均发生于模拟时间 `2026-11-03T15:00:00+08:00`，主体 `agent:rd:R01`，原门面正确拒绝：

| 工具 | 实际错误 | 接续核对方向 |
|---|---|---|
| `get_requirement` | 自造 `req:HY-LV101\|fiber=涤棉`，需求单不存在 | 知识对象没有需求单引用时，不能把 knowledge 对象拼成 req 编号；应读取实际问题引用及可用知识/试样。 |
| `read_trial_record` | 把业务试样 `wk:trial:1` 填入读取工具的 `doc_id`，报“来源不存在” | 分清业务 Trial 编号与读取侧报告来源编号；参数实际叫 `doc_id`，需要登记的来源编号，不转换或猜造编号。 |

证据在本轮 `agent_errors.jsonl`、`agent_trace.jsonl` 及 `conversations/` 对话。错误次数是尝试次数，不等于失败任务数；还需结合最终对象草稿、preparation_gap 与步数耗尽记录判断准备是否完成。

另需核对**准备状态的解释**：本轮知识冲突 `q:14` 的研发对话最后为“步数用完，已完成的部分见上”，而问题 `prepared_at` 已写入。当前该家族 `preparation_gap` 没有额外草稿缺口，Hub 据此标记准备完成，错误表也未另计 out_of_steps。这是实际状态，不应只凭 prepared_at 或“两条错误”宣称研发专业准备完整成功。v11 先对照该家族的准备定义与界面措辞，区分“已供人判断”和“助手完整完成任务”，不直接扩造契约字段或通用兜底。

## 发现质量问题：修复后仍复现

| 注入 | 两轮结果 | 旧评分 → 本次评分与输入 |
|---|---|---|
| inj:2，同一客户反复咨询的机会困难负样本 | 均误报，首次均为 11-04 15:00 | n_escalations=2、n_customers=1，Clef 路径 `scored_by=onejev` 给 p_need=0.772 → 0.6241，均超过 0.5 阈值。 |
| inj:4，知识冲突正例 | 均过早，首次均为 11-03 15:00 | 仅 1 次产品原因失败时，Clef 给 p_need=0.58 → 0.5457，早于原金标要求的第二次失败窗口。 |
| inj:6，集中询问同一产品的泄密风险正例 | 均未发现 | 旧最高分 0.3134，当时 top_product_share≈0.2727；本次最高分 0.2174，当时 n_queries=6、top_product=TF-231A、top_product_share=0.5。最大分采样时刻不同，不能当作同状态下的模型优劣对照。 |

发现评分由 Clef 负责，助手工具参数由 Kimi 生成，不能把两者统一归因于 Kimi。前两项已有“前置条件通过、Clef 评分越过阈值”的直接证据；泄密风险还涉及检索行为特征是否保留了注入所设的“同一产品集中询问”。模型接收到的是实际检索命中汇总，而非原始问句意图；未隔离根因，不断言只换模型即可解决。

## 原主线复跑结果

| 项目 | 修复前 | 本次 |
|---|---|---|
| 窗口命中 | 1/3 | 1/3 |
| 困难负样本误报 | 1/4 | 1/4 |
| 真实模型请求计量 | Kimi 199 + Clef 26 = 225 | Kimi 224 + Clef 26 = 250 |
| 失败 / 降级模型记录 | 0 / 0 | 0 / 0 |
| 工具拒绝（尝试次数） | 9 | 2 |
| 原 12 条 query 具有不可答事件字段 | 0/12 | 12/12 |
| 觉生成网关调用 | 0 | 0 |

7 条注入逐条发现状态及首次发现时间均未变；无注入外新发现。查询事件接线已验证生效，但没有带来本次发现指标改善。工具拒绝少了 7 次不等于任务成功率提升，Kimi 调用也从 199 增至 224；单次复跑不能隔离代码修改与模型输出波动。

输入/注入的 full-week、spine-week 六个文件均逐字节相同；生成对照报告时，旧运行、共享 qi_state 与运行前已跟踪文件指纹全部一致。随后仅补充本轮交接及完成记录，没有改业务代码、模型配置、提示词或专业状态。

复跑命令（旧独立配置仍使用当前模型且缓存关闭，输出和数据集必须换新路径）：

```powershell
.venv/Scripts/uv.exe --cache-dir data/.uv-cache run --env-file .env --locked --no-sync python -B scripts/prepare_discovery_week.py --config data/knowledge_v10/validation/E7-preparation-20261103/app.online.yaml --dataset data/knowledge_v10/evaluations/E7/rerun-20261103-c22a2cf --out data/knowledge_v10/validation/E7-rerun-20261103-c22a2cf/result
```

本命令为实际运行记录，当前输出已存在，不能原样覆盖执行。新检出环境须先按 [E7 使用说明](e7-preparation.md) 建立独立配置与本机凭据；本地材料不会随代码提交。

## 接续边界

- 用户要求模型能力问题暂缓，留待换型；本轮仅验证，不调提示词、阈值、规则或检索排序，不修改金标。
- 原主线对照已完成，下一步由用户与 v11 队友审阅决定；本轮不继续修模型或其他工作包。单次复跑无法隔离代码修改与模型响应波动，不能直接宣称稳定提升。
- 泄密漏报还需区分检索行为特征与 Clef 判断，当前证据不足以断言只换模型即可解决。没有评估实际对外泄露数，不能写“零泄露”。
- v11 接续先对照当前实现，避免覆盖队友已有改动；只对实际缺口做最小修复，不扩大冻结契约、权限或正式签字范围，不用自动改编号、吞异常或放宽门面校验掩盖模型错误。

交接状态：已成文，供用户转交 v11 队友；当前分支保持 v10，未提交、未推送或合并到 v11。
