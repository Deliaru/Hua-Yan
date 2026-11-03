# E7队友准备：现有模拟周发现链

本轮按建设方案“用现有模拟周剧本先跑通”交付一条固定真实配置的开发链。复用现有make_week生成器、eval.week门面运行器与metrics核对；不收集企业业务节奏，不重训Jue-K，不作规则/冻结/进化全比较。

## 数据与选取口径

固定随机种子11、5个模拟日，起点为2026-11-02 09:00（Asia/Shanghai）。完整源周保存130个事件、111张需求卡；本次运行只选生成器在常规背景之前构造的全部注入主线，以及原剧本最后一个事件保留5日结束边界。实际所选31事件、12张需求卡，7条注入（3正例、4困难负样本）和原始窗口不改。

原完整周与所选主线分别放在数据集目录的full-week和spine-week；它们各自保留script.jsonl、cards.jsonl、injections.jsonl。注入副本是同一份7条金标，不计为14条；移除的99条常规背景没有运行，不能称完整周运行。annotations.json在eval侧记录程序注入的来源、分区、生成规则及准备时间，不改冻结Injection字段。

全部为占位种子上的合成dev材料：客户、企业知识、专业签字与试样结果都是模拟。程序设定的注入窗口不等于专业人员核验，非企业节奏、真人试用或未见样本。数据仅留data，不入库。

## 使用方法

```powershell
# 仅准备输入；不调用或验证模型。dataset和报告目录须为新的路径。
uv run --locked --no-sync python scripts/prepare_discovery_week.py --dataset data/knowledge_v10/evaluations/E7/prep-example --out data/knowledge_v10/validation/E7-input-example

# 实际模型主线：使用已核对的独立配置，换新的dataset/out以保留已有证据。
uv run --env-file .env --locked --no-sync python scripts/prepare_discovery_week.py --config data/knowledge_v10/validation/E7-preparation-20261103/app.online.yaml --dataset data/knowledge_v10/evaluations/E7/repeat-example --out data/knowledge_v10/validation/E7-repeat-example
```

本次实际使用dataset为`data/knowledge_v10/evaluations/E7/dev-week`，报告根为`data/knowledge_v10/validation/E7-preparation-20261103`。运行前的新目录检查保护原输入/标注元数据及报告；不要清空旧运行来重跑。

旧scripts/run_week.py仍是原有离线对照入口，固定规则抽取和桩；不能将其当成本轮真实模型验证。本轮新入口仅在显式--config时调用run_week的真实配置路径；未给配置只产生输入，online_status为not_run，detection留空。

## 真实配置与隔离

独立app.online.yaml沿config/app.yaml的合成种子及来源，模型相关字段来自当前config/app.online.yaml：抽取/助手为config/models.agent.yaml中的Kimi-K2.6，Jev/觉原型使用config/system1.clef.yaml中的Cloudflare clef-flash。缓存关闭、replay=false，所有需要模型的调用使用现有真实服务，不造助手响应。

qi_state必须为null，run_root在独立报告根内。显式模式拒绝mock、llm_fallback、规则抽取或回放配置，且拒绝已有运行目录；已有共享试用实例和知识状态不参与本周。旧离线函数调用保留原行为，供既有离线测试使用，不作为本轮模型证据。

只跑jue_proto/ignore：定时三类问题不依据注入答案处置。模拟人仍沿原运行器处理其他问题/回问，所有签字与结果明确为模拟。客户按需求卡提供原话/回复，这些真值仅由模拟器使用；觉/Jev/Agent不载入注入答案。运行预测落盘后，eval才读注入清单做事后核对。

觉发现不调用生成模型网关或工具，沿现有JueProto使用规则前置条件和Clef直接评分。discovery_gateway_calls从真实计量核对；模型请求数、实际模型名、失败请求及降级计量均如实记录。

## 结果与执行问题分开

| 产物 | 用途 |
|---|---|
| summary.json、report.md | 输入范围、提交/词表/模型配置指纹、真实模型计量与在线状态 |
| details.json、discovery-report.md | 逐条注入命中、过早/迟到、未发现、困难负样本误报 |
| execution-issues.json、execution-report.md | 原始助手错误及模拟人处置拒绝，不能藏在成功请求数中 |
| runs/.../ | 门面状态、事件、问题、会话、计量、助手trace及错误、模拟人日志 |

完成态仅表示该链路执行完并产生结果，不表示每条正例命中、每个工具调用成功或全部专业准备通过。错误计数按原始尝试次数，不当成独立失败任务数；注入外发现不能未经核对就全部算误报或正例。当前指标只针对这条合成主线，不能外推为真实业务准确率或打扰减少。

入口捕获的模型/网络/值域/运行错误会保留failed状态和已有日志并重新抛出；其他未捕获异常由进程原样报错，均不转成空成功结果。audit_execution可对已经completed的真实产物重新生成执行问题及逐注入审阅，不发模型请求；未完成不能冒充完成。

本轮没有规则/Jue-K冻结/进化三版比较、处理/忽略后果对照、完整背景周或真人每天打扰次数，零容忍也未单独评估。实际发现错误和助手问题均交审阅，不预写达标。E7交付后停止，不进入E8。

## 2026-11-03审查后的工程接续

用户随后要求修复已暴露问题，并明确模型能力问题留待切换模型。此轮只修三个接线：派单明确question_id和refs中的业务编号；get_need_card补抽取入口已理解的现象ID（通过门面投影，冻结SessionView不变）；模拟query与助手共同走explore。输入、金标、窗口、发现模板/阈值、角色提示词、检索排序均未调。

离线75项通过，原12条query的读取/事件路径实际核对通过。另在独立合成实例用当前Kimi实际测试业务员、机会合并和知识事项，共14次真实请求；前两项正确使用现象/问题编号并成功保存，研发一次自造req:8被拒后读资料并用满8步，保留为模型局限，不算完整准备成功。专业签字0，共享状态不变，没有重跑完整E7或给发现准确率新成绩。

实际证据见`data/knowledge_v10/validation/E7-engineering-online-20261103/run-112518/summary.json`及其runs/engineering中的会话/工具/事件；入口在同目录上级run.py，只写新建的带时间运行目录。输入设置为明确合成、规则抽取，不冒充LLM抽取或真人专业判断。模型错误原样保留，本轮不追求将9条历史拒绝逐条调至零。
