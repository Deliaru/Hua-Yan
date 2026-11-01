# WP-9v10｜一条定向准备与原需求回流链

> 决赛必需，一条业务｜状态：真实资料的开发者模拟回流证据保留；最新业务配置固定Kimi-K2.6，同一在线准备场景产品稿/研发转译各3条、3项缺口为空、人工重试0。该次结果改善于原35B需1次重试的运行，不推出稳定成功率；四岗位真人验收未完成，不以准备通过宣称M3完成。

## 目标

需求需要专业判断时，Agent 把选定报告和候选准备到这张单上；人处理后，结果回到原需求并可供下一单使用。

## 依赖

[V10.1](WP-1v10-sources.md) 读取入口、[V10.5](WP-5v10-compiler.md) 候选、[V10.7](WP-7v10-review.md) 生效。温度场景接 V10.6；V10.3 检索和 V10.8 来源演示均为可选接入。

## 必读

[VISION](../VISION.md) 3.0、3.0′、6.2；`jue/state.py`、`agent/hub.py`、`agent/tools.py`、`app.py` 及现有复用/授予模板。

## 允许修改的范围

现有门面、角色工具、Agent 准备上下文、相关既有模板和工作面，以及这条链的集成检查。

## 交付物与设计

1. 选择现有复用或授予事项：觉按当前规则提出，人也可以主动委托。Agent 带 req_id 和已知条件，通过统一入口按产品/来源编号读取选定资料。
2. 调用读取与编译函数，把证据、候选和待补项保存到原需求的准备材料中。先按编号定位资料即可，图文检索接通后再作为补充工具。
3. 专业确认、授予和必要批准完成后，沿现有业务路径更新原需求与下一单；事项由觉按当前对象状态更新或结案。
4. 留一张简短观察表：提出了什么、谁处理、哪些帮助有用、哪里仍需人工。历史负例作为比较材料，继续沿既有试样归因和能力使用语义处理。

## 验收

共用回归：G1/G4/G5。

- 一张单完成“事项或主动委托→Agent 准备→人处理→结果回原单”，并与 V10.7 的下一单复用接上。
- 准备材料能从原需求直接查看，处理后事项状态正确。
- 开发者记录有用、多余或遗漏的事项，交给真人试用继续反馈。

## 不做

新调度平台、所有家族一起改造、新概念自动扩目录与 Jue-K 重训；按这次试用出现的问题继续补。

## 完成记录

### 2026-11-01｜移除模型费用功能与当前说明

- **范围与自查**：按用户要求删除费用相关内容；重新完整阅读AGENTS、总计划、相关CONTRACTS/QI并按总愿景与既有架构自查。归口为本包模型配置与网关配套清理，交接材料同步V10.10；未新增抽象、兼容分支或防御性测试。
- **实现**：删除两份模型配置的价格表、System1小时价格、网关及OneJev费用计算、BYOK与配置生成脚本中的价格残留；CLI仅汇总调用次数及输入/输出token。两项现有测试只删除价格夹具。同步README、当前计划/工作包/阶段证据和本地选型报告中的预算及金额表述。
- **边界**：冻结LLMResponse.cost与MeterRecord.cost字段保持，新响应及新增计量金额为空；不修改历史原始日志或缓存，不删除真实试样报告中的业务成本原文。调用型号、caller、权限、真人签字及专业判断边界保持。
- **验证与交接**：全量离线62项通过（32.90秒），未新增测试；本地选型报告与交接入口重新生成，无新模型请求。原正式/待审状态及canonical Word证据3份SHA不变。删除配置项改变网关缓存指纹，历史11次严格命中属于清理前配置；当前配置不能据此宣称命中旧缓存。本轮不迁移或清空缓存、不重启服务。V10.3并行新增的验收记录保留，不混入本次清理提交。

### 2026-11-01｜Kimi/122B配置复审

- 已按AGENTS、项目总愿景与架构、CONTRACTS/QI及V10.2/V10.3/V10.6/V10.9范围复审。两份配置指定实际型号，均走统一网关、原地址/密钥变量、单并发、标准工具及空fallback；没有新增旧模型兼容分支或影响签字规则。
- 本轮重新运行现有62项离线回归，全部通过（32.53秒）；以当前配置严格回放122B首份4稿与2列、Kimi原五轮，11次缓存命中/0模型网络请求。只读核对原Kimi完整业务记录为3项准备缺口为空、产品/研发稿各3条、0操作方重试，仍是一次已知场景配模拟接单。
- 核对13个运行阶段的50次新增请求及13个本地缓存响应。原正式/待审状态与canonical Word证据3份SHA未变。交接脚本仍称35B为当前型号的卫生问题另归V10.10同期修复；不重启原服务、不覆盖专业候选或扩题。审查产物在data/knowledge_v10/checks/review-model-choice-20261101，不入库。


### 2026-11-01｜选型后固定Kimi并真实执行整条准备链

- **范围与实现**：按AGENTS自查并重读总计划、相关契约/QI、本包与愿景，承接5f80ad0的35B基线。用户允许自由选型。实际账号可用且Kimi探针返回标准get_requirement(req:1)，随后完整Loop使用现有注册工具；config/models.agent.yaml的fast/strong固定Pro/moonshotai/Kimi-K2.6，地址、密钥变量、关闭思考、串行及无fallback保持。仅修改两份模型配置及完成记录，未改共享网关、Hub/Loop、提示、工具、权限、签字或契约。
- **完整在线运行**：`uv run --env-file .env --locked --no-sync python scripts/run_online_preparation.py --config data/knowledge_v10/checks/model-choice-20261101/app.kimi.yaml --run-id preparation-kimi`，配置为当前业务配置的同等隔离副本，gateway_mock=false、agent_threads=object。使用同一真实报告/合成需求，经实际get_requirement/get_session、read_source、read_trial_record、read_source_image、save_source_preparation保存固定依据及待补差异；模拟接单后实际draft_chem_need，产品稿3条、研发转译3条，三项preparation_gap为空，failures为空，人工重试0。没有直接代填草稿。Kimi此次27次新增网络请求、缓存0；前次35B完整运行需1次整项重试，两次均为已知开发场景，不能推断泛化成功率或必然更优。
- **状态与待办**：模拟接单1、专业确认0、授予0、真人签字0、觉生成模型调用0。资料草稿仍是模型辅助，其中对曲线的自报核对不能替代专业审阅；条件差异、未读清和原生异常写法保留。原正式与真人待审状态未动，8769旧服务未重启。本轮没有做真实专业授权或四岗位业务验收。
- **验证与交接**：Kimi原五轮温度及五条既有失败边界通过，详见V10.6；视觉/表格另固定122B，见V10.2/V10.3。全量离线62项通过（43.21秒），未新增测试样板或构建前端。[总报告](../../data/knowledge_v10/checks/model-choice-20261101/review.html)及summary.json保留模型、meter、工具轨迹和局限。后续按这两份固定配置推进，不增加模型专用兼容补丁；真人专业判断与四岗位验收继续待办。

### 2026-11-01｜35B升级复审及旧工具协议清理

- **复审与实现**：按用户要求重读AGENTS，并以项目总愿景、架构、CONTRACTS/QI及V10.3/V10.6/V10.9边界核对全部升级差异。发现统一网关仍含只服务旧8B的reasoning_content/文本tool_call转换，现已删除该型号硬编码及re依赖，只认标准tool_calls。现有协议测试改为标准调用与文本不执行的同一边界回归，未新增模型专用测试或兼容分支。保留通用think结束前缀处理，因为部分旧录制缓存仍保存此前的推理前缀；旧规范化工具缓存无需旧适配即可读取，未删除或重写历史记录。
- **验证与边界**：全量离线62项通过（31.55秒）。当前35B温度严格回放5命中；同一25页图表回放Qwen3/Clef3命中，结果仍A通过、C失败、C+Jev通过，合计11命中/0新网络。回读原始业务产物，3项准备缺口为空、3条产品稿和3条研发转译、1次已明确记录的模拟操作方重试；未把旧业务缓存计为新请求。4份正式/待审状态与canonical证据指纹未变。工程卫生中的旧配置、检索入口及交接材料随后按所属包独立收口；本轮不重启现有服务，不代真人确认或授予。核对产物留data/knowledge_v10/checks/review-model-hygiene-20261101，不入库。


### 2026-11-01｜35B标准工具调用与实际草稿闭环

- **范围与自查**：用户要求表格与角色Agent升级30B以上并实跑；已按AGENTS重读总计划、相关CONTRACTS/QI、本包及愿景。模型选择与网关真实接口修复归V10.3同期记录。两份models配置均固定Qwen/Qwen3.6-35B-A3B，保留原SiliconFlow地址及BACKUP_API_KEY；关闭思考、原生tool_calls，不借8B正则适配。角色提示仍在prompts，未改Hub/Loop、觉、冻结契约或正式权限。
- **真实失败与最小修改**：研发在confirm_translation中口头声称已调用draft_chem_need却没有实际草稿，preparation_gap按既有规则拒绝通过，失败日志保留。prompts/assistant_rd.md的原确认转译条目明确本轮实际读需求并调用起草工具，以返回条目数量/依据汇报；agent/tools.py仅修正该工具过时描述为“研发已接单”，与现行接单状态一致，不变更工具权限和业务函数。
- **演练入口**：扩充既有scripts/run_online_preparation.py，隔离种子角色名标“开发者模拟”；真实资料准备后通过HuayanApp模拟接单，再dispatch确认转译并检查实际chem_lang。缺草稿时项目方仅触发一次既有Hub.retry+dispatch，记录原缺口和触发者，不代填、不另建重试器。未执行专业confirm、grant、approve或publish。实际命令为`uv run --env-file .env --locked --no-sync python scripts/run_online_preparation.py --config data/knowledge_v10/checks/model-upgrade-20261101/app.online.yaml --run-id preparation-qwen35-delivery`，仍gateway_mock=false、agent_threads=object。
- **在线产物**：真实模型经get_requirement/get_session、read_source、read_trial_record、read_source_image取得TF-213HE/SRC-3a2130604c资料与table-3第2页区域图，再save_source_preparation保存固定指纹及待补项到原req:1。产品稿3条、模拟接单后研发转译3条；reuse_product、accept_requirement、confirm_translation三项preparation_gap最终均为空，failures为空。研发转译在本次完整运行中需要1次项目方触发整项重试，不能称无帮助首轮通过；草稿全部来自真实工具调用，不是聊天自报成功。
- **计量**：最终运行11次新增网络请求（均agent:rd）、12次同型号真实历史响应缓存（agent:extract 1、agent:l1_answer 1、agent:pm 10）；所有模型均Qwen/Qwen3.6-35B-A3B，无mock或生成fallback。原始工具轨迹、metering与gateway-trace在online-runs/preparation-qwen35-delivery，初次缺草稿记录未删。专业确认0、用途授予0、真人签字0；接单1次明确为开发者模拟，觉生成模型调用0。温度新模型另做5次真实请求及5缓存回放，详见V10.6。
- **验收与交接**：全量离线pytest62项通过（33.26秒），测试不依赖外网；不改web、不重复构建。汇总[实跑报告](../../data/knowledge_v10/checks/model-upgrade-20261101/review.html)及summary.json，保护文件SHA相同，真实待审状态未动。本轮完成模型升级后的技术准备验证；既有模拟回流证据保留，真实专业判断、用途授予/批准及四岗位真人原单回流仍按V10.7/V10.10办理，不宣称整包真人验收通过。已有8769进程未重启；35B配置在本轮新建隔离运行生效，不声称老进程热切换。

### 2026-11-01｜提交追溯与Clef Worker配置卫生

- **范围与自查**：用户要求先复审温度修复，再处理提交和配置卫生；已按AGENTS重新阅读总计划、相关契约/QI及本包，确认原P1五轮严格回放正确、60项离线回归通过后执行。Qwen批次已独立提交为`06891b6`，此前因P1暂停提交及GLM过载的原因保留在下一条记录。
- **最小配置调整**：`config/system1.cloudflare-worker.yaml`以`base_url_env: CLOUDFLARE_WORKER_URL`代替个人Worker地址；`jev/system1/onejev.py::build_system1`仅在现有Worker分支读取该环境变量，仍兼容原base_url配置。实际地址迁至本机已忽略的`.env`，运行用`uv run --env-file .env ...`；更新`scripts/cloudflare_vision_worker.md`的当前配置说明。未变更Worker、调用协议、模型、权限、缓存或正式业务状态。
- **提交追溯**：阶段证据中补充8ff6e73、784586c、ac50444、cba5c4d与06891b6的工作包及交付映射，历史哈希与标题保持。后续提交标题包含工作包及具体改动，不以“修正样式”泛称交付。
- **验证**：经现有build_system1实际加载环境配置，客户端根地址与环境值一致、模型仍clef，网络请求0；受影响的`test_clef.py`与`test_reader_models_v10.py`共5项通过（1.94秒），差异格式检查通过。按测试纪律未新增getter/配置行为测试；本次没有真实模型请求或部署，原有专业核对与四岗位真人验收仍待后续。


### 2026-11-01｜复审通过后独立提交Qwen业务主线

- **独立提交原因**：原GLM队列持续过载阻断在线准备，本批改动固定Qwen业务模型、适配实际工具协议并将模型行为提示归位。此前因Qwen多轮温度旧值残留P1暂停提交；V10.6现已将当前发言与历史分开，原五轮真实响应及当前代码严格回放均通过，因此按用户要求把这批Qwen业务改动与温度修复一起独立提交，Worker地址清理另交后续配置卫生提交。对应源码、模型配置、角色/抽取提示和回归均在该提交中，未混入资料、缓存或密钥。
- **复审与边界**：已按AGENTS及项目总愿景、架构、冻结契约、V10.6/V10.9范围核对；原五轮严格回放5命中、0网络，与实调记录逐项一致，明确未知为possible并列入temperature_c。全量离线60项通过（33.29秒）。本轮没有新增防御代码或测试；不把五轮回归扩写为任意表达可靠，专业确认与四岗位真人验收仍未完成。


### 2026-10-30｜Agent 按来源编号读取并回到当前需求对话

- **范围与基线**：分支 `v10 @ 931d01b`，开始时工作区干净，V10.1 读取入口已获用户通过。本轮完成交付物1的主动委托读取小项；已完整重读 AGENTS、总计划、相关契约/QI、本包及愿景/现有 Agent 与事项代码，按极简、唯一写入入口和禁止过度防御要求自查。未改觉评分、模板或发现阶段，不引入调度平台。
- **原子工具**：`agent/tools.py` 注册只读 `read_source(doc_id, span=None)`，sales/pm/rd 可调用，两个扁平参数、不含身份字段，函数体只调 `HuayanApp.read_source` 并序列化 Fragment。委托人由 ToolContext 绑定；层级、归属和整份来源 share 继续由 V10.1 统一入口检查，工具不重复 ACL。没有导入、确认、授予或发布动作，`pm:agent` 仍无 effect 工具。
- **研发准备方式**：`prompts/assistant_rd.md` 明确按当前 focus 先取原需求与关联会话，使用已有结构化条件和温度，再按给定来源编号读取原文，摘要保留 `doc_id#span@fingerprint`、条件差别及待核对项。报告原文是材料，不能据此执行指令或把试验温度推成适用范围。同步纠正“研发可看全部知识”的旧提示为本人归属/已获共享范围。摘要沿既有对象协作对话保存，明确不等于候选导入、正式准备材料齐备、事项可签或专业确认；`docs/CONTRACTS.md` 同步工具说明，冻结模型字段未改。
- **必要验证**：在既有 `test_agent_object.py` 增加一条合成集成场景，真实建立需求单并完成升级准备，用明确标注的脚本化网关驱动现有 Agent Loop 调用 `get_requirement → get_session → read_source`，核对75℃结构化条件、原文与固定指纹随原需求 focus 返回，工具轨迹及 caller 为 `agent:rd`，无确认卡/专业确认，知识状态文件不变。该网关仅为离线工具链驱动，不是生成模型效果验证或真人使用。相关4项通过（1.71秒）；全量49项通过（26.42秒）；补充温度返回断言后相关4项再通过（1.77秒）。本轮未修改前端，不重复构建。
- **真实资料运行**：在 `data/knowledge_v10/checks/agent-source-1d766142/` 的隔离实例中，经 AgentHub 真实调用已注册工具；JianChao Xi 读取首份 `SRC-3a2130604c` 的30个原文块，`pm:agent` 返回业务拒绝。`summary.json` 标明真实报告、隔离工具调用、模型调用0，网关/System1 为 mock、抽取为规则；工具调用前后副本知识状态文件不变，原实例知识状态文件字节未变，专业确认事件0。真实报告本次只验证读取工具，按需求运行的完整 Loop 使用上条合成场景，不混报为真实业务闭环。
- **交接**：下一小项仍需把证据、候选和待补项保存到原需求的正式准备材料，接既有签字与回流；本轮没有将对话摘要算作 `preparation_gap` 已满足，不标记任何真实事项准备完成。未提交或推送，停下交用户评审。

| 发起与业务对象 | 本轮帮助 | 仍需人工或后续实现 | 记录性质 |
|---|---|---|---|
| 人主动委托，合成需求 `req:1` | 助手先读本单与会话条件，再按编号读取资料，带出处回到本单对话 | 判断报告条件是否覆盖本单、保存正式准备材料、确认授予与回流 | 脚本化网关驱动，非真人专业判断 |
| 首份真实报告 `SRC-3a2130604c` | 研发助手可直接按来源编号取回原文，产品经理 Agent 不能读取 L3 | 真人审阅及专业判断；尚无真实需求单回流 | 隔离工具调用，模型未实调 |

### 2026-10-30｜资料准备材料保存到原需求并展示

- **范围与基线**：`v10 @ 11f7b51`，工作区开始时干净，用户已通过上轮读取工具小项。本轮补交付物2中的材料保存与查看；按 AGENTS 重读总计划、相关契约/QI 和本包，按唯一门面写入、G1/G2/G4/G5、极简与禁止过度防御要求自查。评审仍由用户进行，不推进后续签字小项。
- **保存门面**：新增 `save_source_preparation(req_id, evidence, claim_ids, pending, by)`，接单研发在 draft/rd_accepted 阶段保存。依据指针通过既有统一读取入口一次取回各来源，核对块与指纹；候选编号复用 `candidate_claims` 的本单现象及归属边界，关联已有 candidate，不导入或确认。材料包含依据指针、候选编号、待补原文，以及保存时本单已知条件、各关联会话温度状态/原话、起草人与业务时间，写在本运行 `source_preparations/req_<n>.json`；再次保存替换本单草稿。原文与读数不复制到领域状态，未改冻结 Requirement/Fragment/Capability 模型，未向 qi_state 塞读取产物，没有增加锁、回滚、重试或版本平台。
- **查看与工作面**：新增只读 `source_preparation` 和 GET/POST `/api/source-preparation`，HTTP 仅透传门面参数。草稿仅接单研发可读，其他内部角色或同事获得 None，冻结主体拒绝；保存仍校验接单研发。`Rd.tsx` 在本单抬头后展示资料准备草稿、保存时条件、温度原话、出处指纹、候选编号与待补说明，提示结合当前需求和候选状态核对。`api.ts/types.ts` 同步返回结构，没有界面权限判断或新的审批平台。
- **Agent 接入**：新增四个扁平参数的 draft 工具 `save_source_preparation` 和单参数 read 工具 `get_source_preparation`，均只调用一个门面且不含身份字段。研发提示要求先读旧草稿、按已读取的依据保存，工具成功后才报告已保存，不编造候选编号；草稿不生成确认卡、不确认/授予，也不调用 mark_prepared，现有 preparation_gap 仍按事项原有业务产物判断。契约说明已同步。
- **必要验证**：扩展上轮同一个合成 Agent Loop 集成场景为 `get_requirement → get_session → read_source → save_source_preparation`，核对已有待审候选关联、本单条件与75℃状态、出处指纹及待补说明实际落到本单材料；同事/pm:agent 拿不到草稿，非接单人不能保存，旧指纹或不在本单待审列表的候选拒绝且不覆盖旧稿。客户随后明确温度未知，再次保存得到 unknown/null；候选保持 candidate，无确认卡/确认事件，保存不改知识状态。受影响10项通过（2.58秒），全量49项通过（26.45秒）；`npm --prefix web run build` 与 `git diff --check` 通过，仅既有 chunk 体积提示。脚本化网关只驱动离线工具链，不作为真实模型效果验证。
- **真实资料隔离运行**：`data/knowledge_v10/checks/source-preparation-02be7e86/summary.json`。真实报告副本上用原门面创建明确标注的合成需求，创建时仅在隔离内存中限定参与研发为 JianChao Xi，沿原分单规则归到来源既定归属人，随后恢复完整身份表。通过 AgentHub 草稿工具保存15条真实依据指针与既有 `ku:claim:1` 候选关联，待补项明确指出合成需求与报告的纤维/温度差别，未作适用判断。pm:agent/同事不能读取材料，续跑后材料一致；保存本身不改副本 qi_state，原实例 qi_state 文件字节未变，确认事件0，模型调用0，网关/System1 为 mock、抽取为规则。不是一次真人业务或专业签字。
- **交接**：本轮完成“原需求能直接查看已保存的资料准备草稿”，下一小项仍需接编译候选与既有专业签字、用途授予和原需求回流。既有候选编号的关联不宣称已经完成编译导入；真实判断与复用仍待真人办理。未提交或推送，停下等待用户评审。

### 2026-10-30｜从本单完整依据导入操作观察 IR 候选

- **范围与基线**：`v10 @ d4f0274`，开始时工作区干净，用户已通过准备材料保存小项。本轮完成交付物2中的已有 IR 候选导入；已按 AGENTS 重读总计划、相关契约/QI、本包及 V10.5 的编译入口，按 G1/G2/G3/G5、最小增量与禁止过度防御要求自查。只消费首份报告已有操作观察，不扩展检索、模型实调或其他数值字段。
- **编译门面**：`compile_source_preparation(req_id, doc_id, by)` 只允许接单研发在 draft/rd_accepted 阶段调用。`source_irs` 在服务端按来源编号登记 V10.5 IR 路径，Agent/HTTP 不传文件路径。要求本单已保存完整依据，通过统一入口核对当前指纹，再检查 IR 与试样读取记录的文件指纹、来源及完整证据集；已有候选状态变化时先重新准备。只接本单现象一致、form=null 的单次操作观察，不能借客户条件改写报告或创建适用范围。保存与编译共用原有依据核对代码，底层适配器不重复写 ACL。
- **正式候选与原单材料**：沿已有 `import_proposals → admit` 导入，候选正文包含组别、完整条件、限制原文与 IR 待核对项，L3 保留原密级，状态 candidate。该入口不生成用途能力、专业确认、授予或签字事件；导入的预指定确认人仍仅表示归属。IR 编号、编译时间与实际 admit 报告写回本单 compilation，候选编号并入 claim_ids，原待补说明和 IR 待补项合并保留；保存时条件/时间不被编译静默刷新。不新增冻结模型字段或独立匹配、版本、重试机制。
- **工具与展示**：新增 rd draft 工具 `compile_source_preparation(req_id, doc_id)`，只调一个门面，两个扁平参数且不含身份；POST `/api/source-preparation/compile` 只透传。研发提示要求先保存完整依据，按实际 admitted/unaligned/dropped 汇报；工作面准备卡显示 IR、编译时间、实际导入数量、待对齐及引文未通过项，候选仍在原审阅区由人处理。更新 `docs/CONTRACTS.md`，未改觉发现或 preparation_gap，不把入库当成事项已准备完成。
- **必要验证**：增加明确标注合成数据的 `tests/fixtures/reader/synthetic-operation-ir.json`，在既有 Agent 对象测试中走真实需求、来源、准备材料与 AgentHub 工具。覆盖缺完整依据拒绝且不写知识状态、完整依据导入、候选编号与报告回到原单、B组/全部条件/升温限制和待补项保留、candidate/L3/无用途能力、无确认事件和确认卡。受影响11项通过（2.43秒）；全量50项通过（26.45秒）。编译结果改为保留原准备条件/时间并单列编译时间后，相关11项再通过（2.40秒），前端构建再次通过，仅既有 chunk 体积提示；差异格式检查通过。未为共用权限或匹配机制另建防护测试。
- **真实资料隔离运行**：本地首份实例配置登记 `SRC-3a2130604c → operation-ir.json`；仅更新读取产物定位，不作真实专业签字。最终运行记录在 `data/knowledge_v10/checks/prepared-ir-import-336367ab/summary.json`：沿用上轮真实报告副本上的合成需求，通过 AgentHub 工具导入新 candidate `ku:claim:2`，保留B组、11项条件、15条依据和完整 limits，原准备条件/时间保留；实际 admit 报告回写原需求，新增能力0、确认事件0、模型调用0。原实例 qi_state 文件字节未变，网关/System1 为 mock、抽取为规则；这是隔离软件走链，不是真人专业判断或下一单真实复用。
- **交接**：本小项完成，原单已能关联从读取侧 IR 新导入的候选；专业确认、用途判断、必要批准及业务回流继续沿既有入口接续。未提交或推送，停下等待用户评审。

### 2026-10-30｜既有签字与用途状态回显到原需求

- **范围与基线**：`v10 @ 8bea02d`，开始时工作区干净，上轮 IR 导入已获用户通过。已完整重读 AGENTS、总计划、相关契约/QI 与本包，按极简、当前有效状态及禁止过度防御要求自查。本轮补交付物3中处理结果在原单可见这一小项，真实专业签字仍由真人办理。
- **缺口与实现**：准备卡此前固定显示“尚未确认或授予”，即使关联候选已经经原确认入口生效也不更新。新增只读门面 `source_preparation_status` 与 GET `/api/source-preparation/status`，沿原准备材料的接单研发边界，复用 `can_read` 和 `capabilities(by)` 投影本单关联结论/本人用途能力的当前状态。candidate 不返回预指定确认人，active 显示实际确认人，撤回后显示 withdrawn；相关能力沿既有状态显示 proposed/active/suspended/revoked 及批准人。不返回结论或能力正文，不扩大同事或产品经理权限，不另建权限机制。
- **工作面**：`Rd.tsx` 的准备卡保留原准备条件、出处、待补说明及编译结果，将“待审候选”改为“关联结论”，增加当前确认/用途状态。无相关能力时明确确认观察不等于可用于推荐；已确认、撤回或挂起的结果由当前知识库读取，不靠前端推断权限或写回标记。`api.ts/types.ts` 只增加该读取投影，未改冻结模型、签字工具、觉规则、事件或 preparation_gap。
- **合成业务检查**：扩展同一个 `test_agent_object.py` 的完整条件 IR 场景：读取实际审阅指纹后，经原 HTTP 确认入口模拟研发确认，核对原单从 candidate/无实际确认人变为 active/本人；通过现有低层检索“本层答不了”信号让觉提出 qi_grant，模拟研发在原授予入口签一条明确标注合成的 statement，原单显示用途 active；再经原撤回入口撤回结论，原单显示 withdrawn、能力 suspended。全程准备文件字节不变；pm:agent 仍拿不到投影。这里只验证软件链路，签字、措辞均为测试临时实例中的模拟，不作为真实研发判断、真实授予或产品适用成绩。
- **验证**：受影响17项通过（3.43秒），全量 `.venv/Scripts/uv.exe run --no-sync pytest -q`，50项通过（25.05秒）；`npm --prefix web run build` 与 `git diff --check` 通过，仅既有 chunk 体积提示。新增断言放在已有集成场景中，未另建重复的横切权限或状态测试文件。
- **真实报告只读核对**：`data/knowledge_v10/checks/preparation-status-7f2dcfd0/summary.json`，复用上轮真实报告副本与合成需求，仅查询新投影。两个关联结论均为 candidate、实际确认人 None，相关用途能力0；pm:agent/同事返回 None。投影前后副本 qi_state 与准备文件字节不变，原实例 qi_state 字节未变，确认事件0、模型调用0，运行配置为 mock 网关/System1、规则抽取。真实报告没有执行专业确认、授予或撤回。
- **交接**：本轮完成处理结果在原需求准备卡上的实时回显，未宣称已完成面向客户的业务回流或真实下一单复用；相关用途范围判断与生效仍沿既有专业入口推进。未提交或推送，停下等待用户评审。

### 2026-10-30｜已授权说明回原会话与既有 L1 复用

- **范围与基线**：开始时为 `v10 @ 8bea02d`，工作区包含用户已审查通过的状态回显改动，均保留；工作过程中该项由用户提交为 `5fa1da8`。本轮按 AGENTS 重读总计划、相关契约/QI 与本包，按极简、当前生效能力及禁止过度防御要求自查，只接交付物3的授权说明回流，不新增审批或推荐链路。
- **回流门面**：新增 `authorized_source_replies(session_id, by)`，先复用原会话归属检查；在服务端按该会话所属需求的准备材料关联结论，只选择 `kb._visible_caps(actor)` 中的 active statement，经原 `render_refs` 返回授权文字、能力编号和受众。不向低层返回内部准备材料、候选编号或报告原文；冻结主体返回空。查询本身不生成签字、使用计数或状态迁移，statement 不转成 applicable，也不自动判定产品适用。
- **工作面与助手**：GET `/api/source-preparation/replies` 只调门面。`AuthorizedReplies.tsx` 共用于客户和业务员工作面，仅在有可用说明时展示原授权文字，区分客户可见与仅供业务员处理。业务员增加无参数只读工具 `get_authorized_replies`，会话和主体从 ToolContext 绑定；提示继续使用原客户层引用校验保存对客回复草稿。未代发客户消息，未给 Agent 新增生效工具，未改冻结模型或事件。
- **合成纵向验证**：扩展已有同一 IR 集成场景：未确认/仅确认时原会话无授权说明；研发经原入口授予业务员后，业务员可见、客户不可见，业务员不能用这条内部授权保存客户回复。另行模拟客户层授予后，客户只得到该句授权文字；非本单会话不收到本单回流、其他客户不能读取原会话。下一位客户通过原 `add_turn → L1 answer → kb.explore/render_refs` 复用客户层说明并产生既有 capability_used 记录，未看见 L3 原文。最后原结论撤回、能力挂起，原会话不再返回说明；准备文件保持不变。签字和措辞全部为测试临时实例的明确合成动作，不是企业专业判断或产品推荐成绩。
- **验证结果**：受影响11项通过（2.69秒）；加入下一客户实际问答复用断言后，全量 `.venv/Scripts/uv.exe run --no-sync pytest -q`，50项通过（23.88秒）。`npm --prefix web run build` 与 `git diff --check` 通过，仅既有 chunk 体积提示。没有新增横切权限体系、匹配器、重试框架或冗余测试文件。
- **真实报告只读运行**：`data/knowledge_v10/checks/authorized-reply-0a209487/summary.json`。复用真实报告副本与既有合成需求，由业务员和原客户身份查询新入口，均返回空列表：当前仍是待审观察，没有授权说明，不能被下发。原实例与副本知识状态、准备文件均未由本次查询改动，确认事件0、模型调用0，网关/System1 为 mock、抽取为规则；真实资料未签字、授予或撤回。
- **交接**：本轮完成一条“研发确认/授予后，授权说明回原会话并供后续 L1 问答复用”的软件合成链路。原真实报告的专业判断、用途范围与必要批准仍待真人，未宣称产品适用主线或四岗位真实试用完成。未提交或推送，停下等待用户评审。

### 本轮｜报告层负例接入原需求准备与既有编译入口

- **范围与基线**：`v10 @ e13aaea`，开始时工作区干净，用户已通过负例IR准备。按AGENTS完整重读项目规则、总计划、相关CONTRACTS/QI、本包及既有门面；按G2/G3、极简和禁止过度防御要求核对。本轮只接已有负例观察，不扩检索、能力形式、数值条件或调度机制。
- **实现**：`app.py::compile_source_preparation`沿原入口消费操作或负例观察，`group=None`显示“报告层单次观察”，不再生成“None组”；候选的条件逐项保留A/B、阶段或原文范围，防止报告层混合观察抹去两组曲线和不同织物列。form=null、完整依据核对、导入权限及admit均复用既有实现，没有新增校验体系或冻结模型字段。工具说明、研发提示和CONTRACTS文字同步，助手须保留混合品质及待办，不自行认领报告、折叠型号后缀或推定产品通用不适用。
- **合成验证**：在`test_agent_object.py`用已有synthetic-negative.docx补一条核心集成场景。建立合成需求，经原准备门面保存完整依据；未指定本条归属时拒绝，临时指定本人后未对齐的试样型号写回本单编译报告且不入库；再明确登记独立合成型号，经AgentHub原工具得到L3/candidate，保留同次合格与不合格、A/B曲线、原配方对象、完整limits和待办。无用途能力、专业确认或对客说明，需求75℃不被报告工艺覆盖。该登记仅为测试材料，不推定真实型号关系。
- **真实运行**：`data/knowledge_v10/checks/negative-preparation-499abcfa/summary.json`。独立本地实例中的合成需求经AgentHub读取SRC-fa320dba1c、保存28条真实依据及全部待补说明；编译因本条author未指定被原导入规则拒绝，claim_ids为空。隔离实例临时设置来源可读归属只是软件准备演练，不改变真实来源清单、IR归属或共享授予。真实IR、原实例qi_state和隔离编译前后的qi_state字节未变；没有真实候选新增、专业签字、模型调用或自主规划验证。27项条件与混合品质原文仍留在读取侧审阅包。
- **检查结果**：受影响12项通过（3.01秒）；全量pytest55项通过（27.19秒），差异格式检查通过。未修改web，不重复前端构建。网关/System1为mock、抽取为rule；原子工具仍只调一个门面，无身份参数或新增业务分支。
- **交接**：软件已支持报告层负例的准备与候选消费；本条真实负例仍待人指定归属、对齐后缀型号，尚未登记到真实实例source_irs或正式入库。后续沿已有C7审阅、专业确认与用途授予办理，不把历史负例当成能力过时事件或产品通用不适用判断。未提交或推送，本小项结束，停下等待用户评审。

| 对象 | 已准备 | 仍待处理 | 性质 |
|---|---|---|---|
| 合成负例与合成需求 | 本人归属、独立型号登记后生成完整条件候选 | 未执行确认/授予 | 离线软件集成验证 |
| SRC-fa320dba1c与隔离合成需求 | 28条依据、完整待办回到原单 | 本条归属、后缀型号对齐、真人判断 | 真实资料准备，未正式入库 |

### 2026-10-31｜试样记录接入助手和研发资料工作面

- **范围与基线**：`v10 @ ca05a4c`，开始时工作区干净。用户要求继续完成不依赖研发的内容，并在全部推进完时明确报告；专业审阅继续暂缓。已按AGENTS完整重读项目规则、REPLAN、相关CONTRACTS/QI、本包及既有工具/工作面代码，按极简、G1/G2/G5和禁止过度防御要求核对。本轮只消费V10.1已交付的TrialRecord回取入口，不修改正式状态、匹配器、读取模型或授予机制。
- **助手接线**：新增只读原子工具read_trial_record(doc_id)，sales/pm/rd可请求，委托人由ToolContext绑定，单个扁平参数、不含身份或本地路径，函数体仅调用一个门面并序列化。返回已整理条件、A/B、原观察、时间口径和出处/待补项；省略文件指纹、重复差值清单和专业签字字段，不把草稿当正式业务Trial或能力。研发提示同步来源键、原单位/阶段、多对象混合结果及不得扩大范围的使用方式；没有effect动作或准备完成标记。
- **工作面**：新增SourceTrial.tsx，复用现有Act显示服务端拒绝原因和请求状态；从所选候选已经读取的依据、或本单资料准备卡中的来源编号主动回取。展示报告信息、共同条件、A/B配方原单位及基准、曲线标签、原操作、报告标注时间及差值口径、品质/成本/后续和待补项，出处可展开逐字原文、页码、单元格及指纹。曲线列表明确不代表连线顺序。收起只清界面；重新读取先清旧显示，失败时不继续展示旧稿。没有前端ACL、签字按钮或任意文件路径输入，也不改变原候选审阅指纹。
- **类型与文档**：api.ts只消费GET /api/sources/trial，types.ts声明读取侧显示字段，与正式业务Trial区分；未新增冻结模型。CONTRACTS、四岗位交接说明和V10.1状态同步。本轮不把专业审阅重新排给JianChao Xi；后续由用户找到专业研发后集中办理。
- **验证**：扩展既有test_sources_v10同一场景，真实调用AgentHub工具，核对A/B配方、单位和待补项、pm:agent被原入口拒绝、无待签动作及无知识状态变化。受影响7项通过（2.49秒）；全量pytest56项通过（25.96秒），npm --prefix web run build及git diff --check通过，仅既有chunk体积提示。未新增镜像测试或模型实调。
- **真实资料运行**：data/knowledge_v10/checks/trial-consumer-bdb4363c/summary.json及web-record.json。首份真实报告副本上调用已注册工具与工作面HTTP对应门面，两者A/B条件和8项pending一致，A/B各5项配方；工具不含文件路径，pm:agent返回业务拒绝。副本和原实例qi_state、原配置均未因本次读取改变，无确认卡、专业签字或模型调用。使用mock网关/System1、规则抽取；这是软件工具核对，浏览器视觉和真人操作未验证，不能作为真实Agent自主准备或岗位试用成绩。
- **交接与余项**：本小项完成“已整理试样记录→助手/工作面”。非研发部分尚未全部完成：页面/区域统一回取、相关读取验证及最终证据整理仍待推进；视觉模型实调沿用户此前暂停安排保留待验证。专业判断、负例归属/型号关系、用途范围、签字及真实业务验收仍留待后续专业人员集中处理。未提交或推送，按小项汇报后停下等待用户评审。

### 2026-10-31｜研发试样出处接入原页图像查看

- **范围与基线**：`v10 @ 5da5690`，开始时工作区干净，上轮HTTP路由补丁已提交。已完整重读AGENTS、REPLAN、相关CONTRACTS/QI、本包及V10.1/V10.2读取约定，按G1/G2/G6、极简和禁止过度防御要求自查。本轮只完成一个工作面消费小项，专业审阅与视觉模型实调继续暂缓，不代签、不扩大适用范围。
- **实现**：SourceTrial每条出处按已有pages列出“查看第N页／区域”，点击仅传来源编号、span和页码到GET /api/sources/image。新增SourceImage.tsx使用原生dialog显示图像，关闭按钮或Escape收起；明确区分已登记区域与“此块未登记区域，展示整页”，保留密级、尺寸和图像指纹。请求失败显示原服务端错误，没有重复ACL、自由文件路径/坐标、自动读图、持久化缓存或正式状态写入。api.ts/types.ts只补已有接口的消费与显示字段，冻结模型及后端代码未变；CONTRACTS及V10.1状态同步。
- **验证**：全量pytest为56项通过（26.96秒），npm --prefix web run build通过，仅既有chunk大于500kB提示；未新增测试。实际浏览器通过原候选审阅区读取试样记录，展开B组曲线出处，按table-3/第2页取回1072×1516原生页图，图片解码完成，整页提示和图像指纹可见；Escape收起后回到原出处。原件未重新渲染，不将整页显示算作区域定位、模型读数或真人试用。
- **真实资料与快照**：运行产物为data/knowledge_v10/checks/source-image-ui-caafe243/summary.json及page-2.png。当前首份实例ku:claim:1已是active且有1条既有确认事件，本轮未作该操作，也不据此认定专业验收；待审区显示核对使用trial-consumer-bdb4363c的既有candidate快照，原文及页图仍取首份真实来源。原配置、原qi_state、evidence和TrialRecord文件字节均未改变。原门面装载隔离快照时更新4条种子created_at及版本，不能说副本文件逐字不变；首份候选与全部能力和快照一致，新增专业签字0、模型调用0，网关/System1为mock、抽取为rule。
- **启动限制如实记录**：实际尝试标准--trial启动mock实例时，Api.attach访问MockGateway._complete报AttributeError。为完成本轮只读界面核对，临时验证脚本在设置TRIAL之前构造原Api，继续使用原Handler、路由、trial_params主体绑定和普通RLock；未修改或伪造图像API/门面结果。临时页面与服务已关闭。本次不证明标准共享实例启动或TrialGate并发通过；该已复现问题留待下一小项最小修复，不能以临时验证脚本作为正式交付的启动方式。
- **交接**：本小项交付研发试样记录的出处图像查看，等待用户评审；未提交或推送。非研发工作尚未全部完成，仍有Agent图像消费、真实区域定位、选定图表题读取核验、最终证据整理，以及上述mock启动缺口。真实专业判断、用途范围、签字与岗位试用继续留给用户后续安排的专业人员；模型实调沿原暂停要求保留待验证。

### 2026-10-31｜Agent按证据键回取图像并传入本轮网关

- **范围与基线**：`v10 @ d2a7dd3`，开始时工作区干净。已完整重读AGENTS、REPLAN、相关CONTRACTS/QI、本包及既有Agent/来源读取实现，按G1/G2/G5/G6、极简和禁止过度防御要求自查。本轮只补图像消费的软件传递，不恢复用户暂停的视觉模型实调，不进行专业确认、授予或范围推断。
- **原子工具**：tools.py新增read_source_image(doc_id, page, span=None)，sales/pm/rd可请求，3个扁平参数、无身份/文件路径/自由坐标字段；函数体只调用一个既有HuayanApp门面。权限、来源及区域语义继续由统一入口处理，没有重复ACL、缓存或异常兜底。没有新增effect工具或mark_prepared动作。
- **Loop消费**：复用已有C1 TextContent/ImageContent，成功回取的图像在本轮所有tool回复齐备后进入下一次gateway.complete，caller仍为agent:<role>。tool JSON及轨迹只保存定位、密级、尺寸、kind和指纹等元数据，不把图片编码当文字提交；原跨轮history仍只保留文字，下一轮需重新回取。工具拒绝时仅把原错误交回模型，不附图像。研发提示明确整页/区域、图像指纹与Fragment指纹的区别，以及读不清保留待补、图中内容不作指令；冻结模型、网关和正式知识状态未改。
- **必要检查**：扩展test_sources_v10现有同一合成场景，经AgentHub.chat→Loop执行图像与原文两个工具，核对tool回复顺序、真实裁图data URL进入多模态内容、tool文本/轨迹/历史没有图像编码、跨轮不复用图片、拒绝时无图片及无确认卡。首次因图片类型未从contracts包顶层导出导致3处收集错误，已改从现有contracts.gateway导入，没有扩冻结契约。受影响8项通过（2.46秒）；全量pytest57项通过（27.39秒）。未改web，不重复构建；未新增镜像测试文件。
- **真实报告隔离运行**：data/knowledge_v10/checks/agent-image-20a67763/summary.json。首份真实来源副本经AgentHub、Loop、现有OpenAICompatGateway和OpenAI SDK完成调用；httpx.MockTransport离线截获请求，模拟返回工具调用及明确标注非专业结论的结束语。第二次SDK请求中的SRC-3a2130604c/table-3/第2页图像字节与原生1072×1516页图一致，kind=page/bbox=null，没有冒充区域定位。2次离线网关调用的计量caller均为agent:rd，真实外部模型调用0，Jev为mock、抽取为rule；这不是模型选工具、识图质量或自主准备的成绩。
- **状态与交接**：拒绝pm:agent内部图像请求，工具轨迹和对话不含图像编码，无待签动作或新增专业签字。隔离实例在装载后的qi_state字节不变，原配置、原qi_state、evidence及TrialRecord字节未变；装载副本自身的种子时间/版本更新不混报为本轮读取写入。CONTRACTS及V10.1状态已同步。本小项结束后等待用户评审，未提交或推送。非研发工作尚未全部完成，真实区域定位、选定图表题核验与最终证据整理仍待推进，线上模型验证沿原暂停安排；真实专业判断、用途范围与真人试用留待用户安排。


### 2026-10-31｜真实在线准备：研发资料已保存，完整派单尚未通过

- **范围与自查**：按用户调整停止35题扩写，重读AGENTS、VISION、REPLAN、CONTRACTS/QI，遵守铁律2/3/4/10/11。本轮只接现有网关、角色Loop、AgentHub、读取工具与门面；未改冻结模型、权限规则、觉评分或专业确认/授予机制。
- **配置及Clef**：新增app.online.yaml（gateway_mock=false、extractor=llm、agent_threads=object、缓存均在data/knowledge_v10/cache）。原读取侧ClefWorkerClient原样移至jev/system1并由build_system1接入，旧导入位置继续兼容；system1.cloudflare-worker.yaml使用现有Worker根路径。实际jev:match与jev:disclose均取得Clef概率，未更新或部署Worker，Cloudflare没有视觉请求。
- **真实接口差异**：glm-4.6v-flash的最小探针返回原生tool_calls；glm-4.1v-thinking-flash在同请求下只返回执行说明而非工具调用，不能将其算成准备成功。视觉仍使用用户指定models.yaml主/备；业务Agent单列models.agent.yaml，使用同一智谱API与BACKUP_API_KEY，仅4.6V工具模型，沿既有退避[5,15,30,60]重试，失败留待重跑。不把文字说明转换成假工具调用。另有1次glm-4-flash接口探针，未纳入默认配置或业务结果。
- **最小上下文修正**：Loop请求预算4096/180秒，明确必须实际调用工具；需求派单首先按完整req_id调用get_requirement，不能把工具说明复制为需求。实调研发把摘要误填为evidence后，SourcePreparationArgs只补字段说明，门面原指针解析处给出具体格式拒绝信息，要求复制TrialRecord中的固定指纹指针。没有扩Fragment字段、重建ACL或增加重试框架。
- **真实资料与隔离需求**：scripts/run_online_preparation.py准备独立副本，只保留真实TF-213HE目录条目，移除该演练输入中的虚构HY产品/案例/转化及其public副本，防止历史演示产品冒充本单现成方案。客户需求明确标为开发者合成，JianChao Xi仅为隔离助手读取角色，未冒称本人参与。原实例配置、正式IR与qi_state均未因本轮准备改写；没有接单、专业确认、授予、范围批准或发布。
- **已取得的在线行为**：preparation-online-3中，agent:rd经AgentHub主动委托实际完成get_requirement、get_session、read_source、read_trial_record、read_source_image（已登记区域）与save_source_preparation；模型最初的错误依据被拒绝，明确指针说明后实际保存两条可取回的固定指纹依据、本单温度、枚举条件及待核对说明到原需求source_preparations/req_1.json。读图与原文均是真实资料，条目和图片读稿仍是草稿，不转成适用能力。
- **尚未通过**：agent:pm经AgentHub.dispatch已实际读取本单和检索转化，后续连续429/1305；曾出现的错误参数由现有Pydantic边界拒绝，没有自动补造。备用模型的文字描述也未当成执行。最终reuse仍为None、product_lang为空，复用事项的preparation_gap不为空；完整“派单→产品需求→接单后研发转译”在线闭环不能记通过。研发草稿保存后的额外总结请求也遇429，但已保存文件保留，不能把这个成功局部扩写为整轮自主完成。
- **计量与验证**：各真实请求、失败、模型与缓存标记见data/knowledge_v10/checks/glm-online及online/runs/preparation-online-*/gateway-trace*.jsonl、metering.jsonl、agent_trace.jsonl。觉本轮生成模型调用0，保留规则评分标记；未训练Jue-K。全量离线pytest57项通过（27.57秒），新增断言沿已有读图测试覆盖Retry-After、推理前缀、图片/模型缓存及未读清字段；未将线上成绩混入离线测试。
- **交接**：模型读取、温抽与部分准备已经真跑；完整自动派单仍有一项技术验收未完成，原因是指定主模型持续过载，当前不缺密钥、Worker代码或研发材料。停止本轮重复请求，等待接口恢复后沿现有整项重跑继续。真实专业审阅、用途与签字仍按用户安排留待专业人员，不能以本次模型稿替代。运行命令、修改文件全表、分项计量及具体审阅页统一记在data/knowledge_v10/checks/glm-online/report.md。

### 2026-11-01｜现有在线主线重跑，仍受模型服务过载阻断

- **范围与自查**：完整重读AGENTS、总计划、相关CONTRACTS/QI和本包，保留既有未提交改动。使用当前rd:JianChaoXi / pm:HongZongLi及V10.1接入的专家意见版记录，不恢复35题扩写、不改Worker、不增加锁或重试框架。密钥只由`uv run --env-file .env`注入。
- **完整入口**：运行`scripts/run_online_preparation.py --run-id preparation-online-20261101-1`，真实需求抽取首响应将temperature重复放入slots，被既有Schema校验拒绝；纠错阶段连续429/1305，沿网关[5,15,30,60]退避后仍失败。7次网络尝试（1响应、6失败），尚未形成可继续处理的LLM抽取需求，没有以规则结果冒充该入口通过。
- **隔离定位**：本地`data/knowledge_v10/checks/online-preparation-20261101/run.py`仅为定位角色准备问题，通过HuayanApp以RuleExtractor建立明确标注的合成需求，再经AgentHub.dispatch和chat调用实际glm-4.6v-flash。PM与研发各成功调用一次get_requirement，后续仍429/1305。角色阶段15次网络尝试（PM9、研发6），2响应、13失败，缓存命中0；无新重试实现，也没有强行把文字描述变成工具执行。
- **最终结果**：`summary.json`和两份运行目录的run-counts.json保存计量；合计22次真实请求、3响应、19失败，模型全部glm-4.6v-flash，合法caller为agent:extract/pm/rd。复用建议仍空，产品需求条目0，本轮资料草稿未保存，preparation_gap仍非空；不能记作整包完成或自主准备通过。规则建立输入的隔离尝试单独标明，不与此前实际LLM温抽成绩混报。
- **边界与后续**：原正式qi_state指纹未变，专业确认、授予、批准、接单和发布均0；觉生成模型调用0。原有8766在线预览未发生模型请求，8767为mock人工审阅实例，本轮不修改其模型或业务。当前不缺新密钥、Worker代码或专家材料；停止本轮重复请求，保留现有Hub整项重跑方式，模型恢复后继续。真人生效动作另由有权人员办理；转做不依赖接口恢复的读取侧收口。本轮未改业务代码，不重复离线测试或前端构建，不把此前58项成绩写成新重跑。


### 2026-11-01｜接续原在线准备需求，保留实际失败与缓存计量

- **范围**：按AGENTS自查后续跑既有preparation-role-online-20261101/req:1，没有另建需求、换模型、增加重试框架或执行签字。该输入仍明确属于开发者合成需求、规则抽取；不能记作本轮真实LLM抽取或真人操作。
- **入口与实际调用**：`uv run --env-file .env --locked --no-sync python data/knowledge_v10/checks/online-preparation-20261101/resume.py`；使用现有AgentHub.retry及dispatch。agent:pm取得一次缓存的get_requirement响应，随后实际调用search_knowledge；首次kind误填多种类型由既有边界拒绝，模型自行改为case并完成检索。之后指定glm-4.6v-flash继续429/1305，沿现有网关退避结束，没有强行补写模型未执行的工具。
- **本轮增量计量**：11次网络尝试，2次成功响应、9次失败；另有1次本地缓存响应，总计12条llm计量、3条ok。合法caller为agent:pm，无降级，觉生成模型调用0。resume-summary.json与gateway-trace-resume.jsonl留存上述增量；不与前一轮22次请求混算。
- **结果与阻断**：复用建议仍为空、产品条目0、q:2的preparation_gap非空，故本轮不继续派发后续研发步骤、不标记准备完成。正式实例qi_state在此次在线准备期间未变，新签字0。本轮停止重复网络请求，当前不缺密钥或Worker更新；完整在线准备仍未通过。
- **主线新状态**：另一正式实例的五项真人确认及L3适用范围批准已回读，见V10.7同日记录；下行用途尚未授予，不能将这些动作计入本隔离在线需求的原单回流。未修改业务源码/前端，不重复离线回归或构建。


### 2026-11-01｜用户允许开发者代办，软件回流完成，在线仍未通过

- **自查与授权**：按AGENTS及本包自查。用户澄清此前授权/话语都是测试，允许开发者代办以推进软件工作；所有签字按模拟记录，不据账号名认定真人参与。V10.7的独立developer-authorized实例已完成实际资料准备、固定指纹确认、原单回流和下一单说明使用，具体事件及范围见该包记录。脚本工具准备仍不等于在线Agent规划成功。
- **第一轮接续**：本地resume-authorized.py沿现有AgentHub.retry/dispatch继续原req:1，3条先前模型响应命中缓存，实际执行get_requirement及一次参数拒绝后的search_knowledge。随后glm-4.6v-flash的5次网络尝试均429/1305，PM建议未落盘；已结案事项不因prepared_at为空误判为未完成，接续脚本按真实status判断，未修改业务模块。
- **定向委托**：进一步用AgentHub.chat明确给出前次真实空检索结果及需保存的原子工具，directed.py未调用脚本代填草稿；该入口仍5次网络尝试均429、响应0。未进入后续研发在线准备，也未伪造source_preparation或prepared状态。两种入口严格串行，沿统一网关既有退避，无新重试、并发或模型替换。
- **本轮计量**：合计10次网络尝试、10次失败，另有3次缓存成功回放；真实模型均为glm-4.6v-flash、caller为agent:pm，觉生成模型调用0。resume-authorized-summary.json、directed-summary.json和对应gateway-trace保留增量，不能把缓存回放计为本轮网络成功。
- **结论**：离线/脚本驱动的原单回流与说明复用已完成；完整在线准备的preparation_gap仍非空，不能将整包在线验收改成通过。当前阻断是外部模型过载，不是缺研发授权、密钥或Worker。停止本轮重复请求，保留原需求及既有Hub重跑入口；不改冻结契约和专业条件。

### 2026-11-01｜在线准备跑通，收口网关与模型行为提示

- **规则与已有修改**：已完整重读AGENTS并按铁律2/3/4/10/11自查，读取总计划、相关CONTRACTS/QI及本包；保留用户正在进行的清理。冻结契约、权限、reviewed_evidence签字传参均未改。修复清理中残留的未定义_condition_scope调用，恢复原有三类条件范围展示，不新增辅助结构。
- **模型固定与网关**：本轮主线固定SiliconFlow Qwen/Qwen3-VL-8B-Instruct（视觉仍用models.yaml、业务用models.agent.yaml），无自动换型及GLM回退，Cloudflare只Clef。早期最小探针对文本Qwen3-8B、视觉32B做过协议诊断，没有把它们设为默认或宣称业务通过。客户端及BYOK删除GLM思考参数硬编码，专有请求参数仅从配置extra_body透传；既有think尾标识处理保留在网关边界，不追加业务补丁。
- **真实接口适配**：SiliconFlow的指定8B Instruct实调把完整工具协议放入reasoning_content、content为空。仅对这一确切型号、无标准tool_calls且无正文的响应识别完整独立tool_call协议；解释文字中的示例不会转成执行。正规工具仍由既有Hub/Pydantic/权限及签字机制处理，不从自由文字猜动作，不在Hub另建适配。合成离线回归覆盖完整协议和解释示例不执行。
- **提示词归位**：用户已将“先读get_requirement”“实际调用工具而非文字说明”移入assistant_pm/rd/sales.md，将JSON实例、温度顶层字段及逐字引文要求移入extract.md。Python仅装配对象、结构化输入与工具结果，不重复拼接这些行为提示；本次在extract.md明确最新轮次与旧状态区别，未写规则兜底。scope_update签字人更新已从scan移至启动续跑，复用_line_pm及公开bus.publish；新问题原本就从refs.pm解析签字人，不再每次扫描调用bus._snapshot。
- **在线主线结果**：`uv run --env-file .env --locked --no-sync python scripts/run_online_preparation.py --run-id preparation-qwen-clean-20261101`使用新提示文件，真实LLM抽取合成需求后，AgentHub.dispatch的PM保存复用查证与3条产品需求；研发按明确来源主动委托实际调用get_requirement/get_session/read_source/read_trial_record/read_source_image/save_source_preparation，原单保存A/B固定指纹及待核对项。开发者按用户授权在独立演练实例模拟接单，再dispatch研发实际调用draft_chem_need，生成3条转译；reuse_product/accept_requirement/confirm_translation的preparation_gap均为空，转译仍待签。没有由脚本代填模型未执行的草稿。
- **计量与人工帮助**：清理后这条完整运行合计20次真实请求及20响应，缓存0、失败0，caller为agent:extract 1次、agent:pm 9次、agent:rd 10次；实际模型均指定8B，无降级，觉生成模型调用0。早期清理前另一运行14次请求另存，探针与温度验收不混入上述20次。角色曾给出错误会话编号及检索参数，由原工具拒绝后模型自行更正。需求、升级说明、研发来源编号委托及一次接单由开发者提供/模拟；真实参与人和专业签字0。旧测试实例与human-review-ready的qi_state指纹不变。
- **尚未通过的温度验收**：同一固定配置执行`run_online_temperature.py --run-id temperature-qwen-current-20261101`，5次网络响应均合格JSON，但模型在闭区间和明确未知轮次返回了历史温度，既有末尾业务断言失败。未继续换型号、未把离线59项通过写成该实调通过。该缺陷归V10.6，修复后才能称在线完整条件验收通过；不把单次成功的75℃抽取扩写成多轮可靠。
- **产物与回归**：data/knowledge_v10/checks/qwen-business-20261101/review.html与summary.json汇总真实请求、工具轨迹、准备缺口及温度失败；online/runs/preparation-qwen-clean-20261101保存正式原单草稿，均不入库。最终全量离线pytest59项通过（28.41秒），含启动续跑签字人归属和编译完整条件回归；git diff --check通过。未改web，不重复构建。专业曲线核对、真实确认/授予/范围批准及四岗位试用仍待用户之后组织，不由模拟接单替代。
