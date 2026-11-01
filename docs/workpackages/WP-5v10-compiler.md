# WP-5v10｜从试样记录形成完整条件候选

> 决赛必需｜状态：首版候选编译交付完成；专家意见对应五项L3新候选ku:claim:2—6及一项L3 proposed适用提议cap:1已入库，完整条件与IR映射可审阅；旧稿继续撤回，专业确认与用途生效交V10.7｜先编译一条值得复用的判断。

## 目标

把首份报告中的观察或操作经验，整理为研发可以确认的候选，完整保留适用条件和限制。

## 依赖

[V10.4](WP-4v10-trials.md) 的首份记录与原文；使用 V10.0 的证据映射。数值比较未接通时，条件可先以原文进入审阅。

## 必读

[QI](../QI.md) 编译与生效；`ingest/compile.py`、`knowledge/store.py` 的 admit/grant/attach_evidence；v3 第 06、07 节。

## 允许修改的范围

`src/huayan/ingest/compile.py`、IR/条件核对/审阅包模块、`scripts/compile_qi.py`、候选补充依据入口及对应测试。

## 交付物与设计

1. 最小 IR 包含陈述性质、对象、结果、条件、限制原文和证据。按材料区分观察、主张、建议、假设，先完成本次实际需要的类型。
2. 条件逐项列出“已结构化”或“保留原文待判断”，共同条件、A/B 和阶段随记录传递。修复当前 admit 只认出一部分条件就提议适用的缺口。
3. 复用 admit 生成 candidate KU、proposed ask/applicable 和 IR↔KU 映射；产品/现象先使用现有词表，未对齐原词留给人处理。
4. 相同 payload 的新依据保持候选并记下待挂接目标，交 V10.7 确认后关联。综合判断的确认人与原材料贡献分别记录。

## 验收

共用回归：G2/G3。

- 一条真实观察或经验成为候选，原文、条件和拟用方式可并排审阅。
- 材料/设备已识别、升温限制未结构化的样例，限制仍完整保留。
- 同 payload 的补充依据出现在待审列表，确认与挂接由 V10.7 完成。

## 不做

别名版本化重跑、新指标体系、自动概念归纳和知识图谱。首版由人补齐未对齐项。

## 完成记录

### 2026-10-30｜首条操作观察 IR 与完整条件审阅包

- **范围与基线**：按用户要求停止视觉模型实调，回到 M1 → M2 主线。本小项基于 `v10 @ feb4e7a` 的首份原生 TrialRecord，完成 V10.5 的 IR 材料准备；原有 Cloudflare 工作区改动保留。动手前已完整重读 AGENTS，再读总计划、相关契约/QI 和本包，按极简实现、条件保真及禁止过度防御要求自查。评审由用户进行。
- **实现**：新增 `ingest/trial_ir.py` 和 `scripts/prepare_trial_ir.py`。读取侧 IR 明确标为规则整理的单次 `observation`，保留来源文件指纹、对象原词、B组、原观察、共同/配方/曲线/现场操作条件、引文与页码。整项文字能完全对齐现有枚举时才列为已结构化，含额外信息的原句继续保留；未结构化项的逐字引文写入 `Proposal.limits`，不丢弃泵速、加料顺序、时间、缺单位和色名差异。
- **运行入口**：`.venv/Scripts/uv.exe run --no-sync python scripts/prepare_trial_ir.py --trial data/knowledge_v10/trials/SRC-3a2130604c/trial-record.json --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --product TF-213HE --group B --out data/knowledge_v10/compiler/SRC-3a2130604c`。
- **真实交付**：首条 IR 编号 `SRC-3a2130604c:B:operation-1`，11项条件，13项待处理。产物 `operation-ir.json`、现有 Proposal 格式的 `proposals.json` 与 `review.html` 均在上述不入库目录。审阅页并列观察、条件对齐状态和逐字原文，可跳转既有原页对照。运行入口核对 TrialRecord/读取记录的来源及文件指纹，并核对各引用的块指纹和逐字引文，真实材料整理成功。产品 TF-213HE 未对齐当前占位产品词表，研发归属按用户先前要求继续待安排。
- **验收边界**：完成“一条真实操作观察的 IR、条件清单及拟用方式并排审阅”；还没有导入 candidate KU 或 proposed Capability，未授予、未专业签字。当前 `form=null`，不把一次现场正常结果扩大为产品通用适用判断。IR↔KU 映射、`admit` 部分条件限制修复、同 payload 补充依据候选化和后续确认挂接留待下一小项，不能据此宣称 V10.5 整包完成。
- **模型、测试与交接**：本次没有调用生成模型、视觉模型或 Jev，没有使用金标；按用户要求不再开展模型测试或新增测试。本次验证限于执行上述真实材料准备入口。未改冻结契约、原 TrialRecord 或正式知识状态，未提交、未推送。停在本小项，交用户评审后继续候选导入链路。

### 2026-10-30｜IR 接入现有编译器，修复条件丢失与补充依据直接生效

- **范围**：按用户“继续推进”完成 V10.5 下一小项，分支 `v10`、基线 `feb4e7a`。已重新完整阅读 AGENTS、总计划、相关契约/QI 和本包，按最小增量及禁止过度防御要求自查；评审由用户进行，原有视觉读取改动保留，没有继续模型测试。
- **条件保留**：`compile.py::admit` 继续使用现有枚举对齐；某条条件未识别或只识别了句中一部分时，整句追加进 `limits`。全部条件均无法结构化时也只形成带完整限制的同层 `proposed`，不变成无限制适用。能力去重继续比较包括 `limits` 在内的完整 payload；未对齐报告新增具体原因。
- **补充依据**：`store.py::attach_evidence` 现在只保存 candidate KU，并记录待挂接能力及原贡献人；不修改原能力的 `based_on` 或状态。新增读取兼容旧状态的内部 `pending_evidence` 字典，随现有 `_save` 持久化，不新增锁、状态文件或冻结契约字段。真正确认后的挂接、固定审阅指纹检查留在 V10.7，本次不提前修改 `confirm`。
- **IR 接入**：读取侧 `EvidenceReportSource` 将既有读取记录按原 `doc_id/span/fingerprint` 提供给 `admit/recheck`，不转换段号。`scripts/compile_qi.py` 增加 `--ir/--evidence`，无 `--state` 时在内存中执行预览；有 `--state` 的正式导入仍限应用停止时使用。输出 Markdown/JSON 编译报告和 IR→KU/待挂接映射，保持原录制提议及模型编译入口。
- **真实运行**：执行 `.venv/Scripts/uv.exe run --no-sync python scripts/compile_qi.py --ir data/knowledge_v10/compiler/SRC-3a2130604c/operation-ir.json --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --out data/knowledge_v10/compiler/SRC-3a2130604c/compile-report.md`。读取真实报告提议1条，引文未被丢弃；候选0、能力提议0、待对齐1。报告明确列出“专业确认人待安排”“产品未对齐：TF-213HE”，IR 映射为 `pending_alignment`、`ku_id=null`，没有虚构归属人或把真实产品映射到模拟产品。配置中的既有来源名称标注为模拟；本条提议仅引用真实报告。
- **必要回归**：新增一项针对本包两个真实缺口的合成测试及明确标注的 `tests/fixtures/reader/synthetic-conditions.txt`；验证“材料/设备已识别，升温限制仍完整保留”和“补充依据先候选、原能力不变、贡献人与待挂接目标保存后可恢复”。执行 `.venv/Scripts/uv.exe run --no-sync pytest -q tests/test_compiler_v10.py tests/test_wp_a3.py`，4项通过（2.36秒）。没有调用生成模型、视觉模型或 Jev，也未重复开展读取测试。
- **交接**：本小项的编译路径及两处修复已完成，真实样例尚未正式入库，V10.5 整包不能记为通过。产品对齐与确认人安排仍待后续处理；确认人按用户此前要求暂缓。交 V10.7 消费待挂接记录并确定 C7 固定证据确认接口。运行产物只在 `data/`，未写共享试用状态，未提交或推送；当前停下等待用户评审。

### 2026-10-30｜补入用户提供的 SDS 与产品说明书，完善产品对齐材料

- **范围与基线**：分支 `v10 @ 44178ff`，开始时工作区干净。按用户授权完善当前 V10.5 材料，未切换到其他包。编程前已完整重读 AGENTS，再读总计划、相关契约/QI 与本包，按条件保真、最小改动和禁止过度防御要求自查；评审由用户进行。
- **真实来源**：用户提供《SDS-分散匀染剂 TF-213HE-V6.1.pdf》8页和《说明书-分散匀染剂TF-213HE.pdf》1页。`scripts/prepare_product_sources.py` 用 PDFium 提取原生文字、生成首页图并保存原件字节副本；来源编号分别为 `SRC-38a27ac7a5`、`SRC-eb043d626f`。页码映射到现有 Fragment 的 `page-N` 段号和文本指纹，未增加契约字段。当前未取得来源已公开的确认，均按内部 L3 保存；没有将两份资料的内容直接发布为低层产品说明。
- **产品材料**：在不入库目录 `data/knowledge_v10/products/TF-213HE/` 整理 `product-alignment.json`，逐字引用9项事实：中英文名、供应商、SDS版本与日期、说明书名称、两份文件的用途表述、说明书常规用法与调整前提、SDS用途边界。各项引文通过读取侧来源指纹和原文包含核对；这是人工整理的资料对齐草稿，不是模型生成或专业适用确认。两份原件及页图、原文分别在 `sds/`、`sheet/`，均提供本地 `review.html`。
- **接入与修改**：读取侧 `ProductAlignment` 只承载资料事实、出处和待办，不另造引擎 Product 或候选匹配链。`prepare_trial_ir.py --product-alignment <json>` 将该材料接入首份 IR，校验型号、引文及块指纹；原观察的证据仍引用试样报告，说明书常规条件不替换报告实际条件。`compile_qi.py` 的报告新增产品身份依据与正式目录登记的区分，产品目录尚未登记时仍交既有 `admit` 处理，不绕过导入前置条件。
- **待审差异**：说明书常规染色温度125–130℃，试样报告B组有132℃保温点；说明书注明“具体工艺请用户通过试样酌情调整”，两份原文保留并列，交研发判断。SDS修订日期2024.8.27晚于试样报告日期2024年3月14日，不据此推定当时使用同版资料。用量0.2–0.5g/L、浴比1:10、保温时间30–60min仅作为说明书常规方法原文保存，不擅自换算本报告用量或扩大适用范围。
- **真实运行入口**：先执行 `scripts/prepare_product_sources.py --sds <用户提供的SDS绝对路径> --sheet <用户提供的说明书绝对路径> --out data/knowledge_v10/products/TF-213HE`。将上述逐字摘录整理为 `product-alignment.json` 后，运行此前 `prepare_trial_ir.py` 命令并增加 `--product-alignment data/knowledge_v10/products/TF-213HE/product-alignment.json`，再执行既有 `compile_qi.py --ir ... --evidence ... --out ...` 内存预览。
- **结果与验收边界**：已更新 `data/knowledge_v10/compiler/SRC-3a2130604c/` 的 IR、审阅页与编译报告。原11项条件不变，产品资料新增9项事实，待办现为16项。预览引文丢弃0、真实候选0，报告列明“专业确认人待安排”“产品身份已有依据，正式目录登记待归属”；`identity_supported=true`、`catalog_registered=false`，IR映射仍为 `pending_alignment`。型号身份和用途资料缺口已补齐；正式目录登记及候选入库尚未完成，不能标记整包通过。
- **必要验证与交接**：执行当前真实材料读取、IR准备和内存编译预览；受影响既有回归 `pytest -q tests/test_compiler_v10.py tests/test_reader_v10.py` 为3项通过（1.22秒），未新增冗余测试，未调用模型或 Jev。确认人与真实签字按用户要求暂缓，不新增占位身份；后续继续完成 V10.7 的固定证据审阅与确认挂接功能。未写共享试用状态、未改冻结契约、未提交或推送。本小项停下交用户评审。

### 2026-10-30｜按用户指定登记研发归属 JianChao Xi

- **用户指定与范围**：用户明确指定研发人员为 JianChao Xi。当前基线 `v10 @ d35d159`，开始时工作区干净；已完整重读 AGENTS、总计划、相关契约/QI 与本包并按要求自查。此次完成候选归属材料的小项，不替本人执行确认或授予。
- **身份记录**：现有种子和本地试点资料中未找到同名账号，建立读取侧本地 Actor 资料 `data/knowledge_v10/actors/jianming-xi.json`：`id=rd:JianChaoXi`、`role=rd`、`name=JianChao Xi`。这是为用户指定人准备的本地标识，尚未写入共享试用实例的角色/登录配置；保留所有既有模拟人物，不冒用 R01/R02。姓名指定不等于专业签字。
- **接入**：`OperationIR` 增加读取侧可选字段 `assigned_rd: Actor | None = None`，不改冻结契约。`prepare_trial_ir.py --reviewer <Actor JSON>` 将指定人写入 IR 和现有 Proposal 的候选归属字段 `author`，删除“专业确认人待安排”的过时提示，审阅页与编译报告显示姓名及标识。报告原来的试样人员与原始引文保留，不将新指定的确认人写成原报告作者。
- **真实运行**：在原 IR 准备入口加 `--reviewer data/knowledge_v10/actors/jianming-xi.json` 重跑，更新原11项条件、产品材料、审阅页和确认准备记录；再执行现有编译内存预览。结果引文丢弃0、候选0、待对齐1，剩余原因仅为“产品身份已有依据，正式目录登记待完成”；确认准备记录改为 `awaiting_candidate`，`confirmation_submitted=false`。研发归属缺口已经解决，正式 Product 登记和候选入库仍未完成。
- **验证与交接**：本次验证限于上述真实材料整理与编译预览，不为可选字段或 Pydantic 行为添加冗余测试；没有调用模型、没有写共享实例状态、没有专业签字或授予。后续小项为真实产品目录登记与候选导入，并将该研发标识接入实际试用角色配置。未提交或推送，当前停下交用户评审。

### 2026-10-30｜本地产品目录登记与首条真实候选入库

- **范围与基线**：沿 `v10 @ d35d159` 和上次研发归属材料的未提交改动推进当前小项。编程前已完整重读 AGENTS、总计划、相关契约/QI 与本包，并按最小实现、密级和禁止过度防御要求自查；评审由用户进行。用户明确允许暂缓真人签字，继续完成产品登记和候选入库。
- **产品与角色登记**：新增 `scripts/import_first_report.py`，从既有真实 IR 和资料身份记录准备独立本地种子/实例配置。`TF-213HE` 使用现有 `Product` 结构登记为 `status="project"`：只表示尚未在化言发布，不推断其实际市场发布状态；`solves=[]`、无适用情境、发布文本为空。SDS/说明书原文及配方仍在 L3 读取侧，未复制进 L1 的 `sheet/usage`。JianChao Xi（`rd:JianChaoXi`）已加入该实例角色配置，既有模拟底座保留并明确标注，未修改仓库通用模拟种子。
- **最小接线**：`admit` 的产品识别读取已登记种子目录并叠加当前知识库产品，因此能接受未发布条目的观察候选，不另建匹配链。新增 `HuayanApp.import_proposals`，只允许导入已指定本人负责的提议，正式候选写入经门面完成。应用/既有编译脚本的来源入口复用 `EvidenceReportSource` 读取配置中明确指向 `.json` 的读取记录；原文件夹来源保留。这样实例续跑仍可按原段号和指纹取回依据，而不需要临时挂接内存来源。未新增冻结契约或配置开关。
- **真实运行入口**：`.venv/Scripts/uv.exe run --no-sync python scripts/import_first_report.py --ir data/knowledge_v10/compiler/SRC-3a2130604c/operation-ir.json --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --out data/knowledge_v10/instance-first-report`。该首次导入入口要求新建输出目录，已有实例使用现有续跑方式，不覆盖重建或重置。实例配置为 `data/knowledge_v10/instance-first-report/app.yaml`，运行号 `first-report`，状态在该目录的 `runs/first-report/qi_state.json`。
- **结果与编号**：实际写入 `ku:claim:1`（L3、`candidate`、产品 `TF-213HE`、归属 `rd:JianChaoXi`），IR映射为 `SRC-3a2130604c:B:operation-1` → `ku:claim:1`。候选1、未对齐0、引文丢弃0；当前只承载单次操作观察，`form=null`、能力提议0，不将现场结果升级成通用适用判断。`import-report.json` 保存实际入库结果；原审阅页显示真实候选编号，确认准备记录为 `awaiting_professional_confirmation`，不再显示待指定研发/待入库的过时状态。
- **验证**：针对本包实际问题新增一项合成回归，验证未发布目录产品可形成候选、不会因此进入推荐；执行 `pytest -q tests/test_compiler_v10.py tests/test_wp_a3.py tests/test_trial.py`，13项通过（3.02秒）。在真实本地实例上续跑读取，研发角色可取得候选的固定审阅依据；客户检索不可读该候选，目标产品无生效能力且不在推荐产品视图中，`claim_confirmed` 事件为0。只读准备、状态与运行配置记录在 `readiness-check.json` 和既有 `confirmation-preparation.json`。实例仍使用明确标注的 mock 网关/System1 与规则抽取配置，本次未调用生成模型或远端 Jev。
- **交接**：本小项的目录登记、真实候选入库和实例角色登记已完成。启动已有实例可用 `uv run python -m huayan.ui.server --trial first-report --config data/knowledge_v10/instance-first-report/app.yaml`；本次未启动服务。后续在工作面组织该候选的审阅，真人确认/授予/必要批准、下一单复用和温度链路仍待完成，负例材料后续补充。未更改其他共享试用实例，未提交或推送；当前停下交用户评审。

### 2026-10-30｜补齐读取记录来源的 explore 检索接线

- **范围**：按用户指定的两点最小修复，已重读 AGENTS、总计划、契约/QI 与本包，并按极简实现及禁止过度防御要求自查。
- **修改**：`trial_ir.py::EvidenceReportSource.search` 复用 `knowledge.store._grams`，沿用 `FolderSource.search` 的重叠比例评分、文档/段号排序与前 k 项返回；权限继续复用知识库。`docs/CONTRACTS.md` 门面说明补入 `HuayanApp.import_proposals(proposals, by)`，不增加契约字段。
- **验证**：`tests/test_compiler_v10.py` 新增一项合成回归，覆盖该来源挂入 `kb.sources` 后研发可从 `.candidates` 看到本人候选、客户不可见且查询不报错。运行 `uv run --no-sync pytest -q tests/test_compiler_v10.py`，5项通过（1.48秒）。续跑真实 `first-report` 本地实例，三个读取记录来源均接入，`rd:JianChaoXi` 可检索 `ku:claim:1`，客户不可见；候选仍为 `candidate`，未执行确认、授予或模型调用。
- **交接**：此次修复完成，未提交或推送；停下等待用户评审，不开始下一小项。

### 2026-10-30｜消费 V10.6 的显式温度范围提议

- `compile.Proposal` 的读取侧内部类型增加默认 None 的摄氏闭区间字段；`admit` 只在明确提供时写入同一适用 payload，保留原有 conditions/limits、证据核对和 candidate/proposed 状态。编译提示不把单次试验温度或多阶段曲线推断为适用范围，未修改冻结模型。
- 新增合成材料及纵向验证归 V10.6，现有授予/批准展示归 V10.7；全量47项通过，前端构建通过。首份真实 IR 的内存预览仍只有观察候选，能力提议0、无温度授权，详见 V10.6 同日完成记录。已按 AGENTS 自查，未调用模型、写真实确认、提交或推送，停下等待用户评审。

### 2026-10-30｜真实负例的完整条件观察IR与内存编译预览

- **范围与基线**：`v10 @ aeef49b`，开始时工作区干净，上一项受控汇总及P2修复已获用户评审通过。重读AGENTS全文、REPLAN、相关CONTRACTS/QI与本包，按条件/出处保真、极简与禁止过度防御要求自查。本轮只补负例观察提议和审阅包，不修改真实知识状态、不代签或扩展能力形式。
- **实现**：`trial_ir.py::prepare_negative`消费V10.4已选报告的品质原文，复用OperationIR、Proposal及原来的枚举对齐/limits处理。只将读取侧OperationIR.group允许为None，表示报告层观察；条件内的A/B曲线组别不变，未改冻结契约。原操作观察的共有整理逻辑提取为一个私有函数供两条入口复用，首份输出保持一致。审阅页对有阶段但未标A/B的条件显示“原文范围”，避免将织物列或报告分析写成共同工艺条件。
- **资料与条件**：沿用 `SRC-fa320dba1c` 的TrialRecord与当前证据，观察保留同次合格/不合格两种结果。条件包括共同原文、产品及配合方案、完整多织物配方列、A/B曲线、操作、报告分析及后续。报告原分析以原文材料保留，不作为系统因果确认；具体对象和限制没有抽成产品通用不适用。报告未记载完整A/B总时长、成本变化的待办保留，不填零或估算。
- **入口与产物**：新增 `scripts/prepare_negative_ir.py`，来源/文件指纹及每条引文/块指纹在外部文件边界核对；操作见 [负例观察准备](../trial/negative-ir-v10.md)。真实产物在 `data/knowledge_v10/compiler/SRC-fa320dba1c/`，IR编号 `SRC-fa320dba1c:negative-1`，27项条件、28条依据，性质observation、group=null、form=null、temperature_c=null。产品原词保留后缀，未自动套用基础型号的SDS/说明书或身份记录；本提议研发归属尚未分配，不把原报告作者或首份候选归属自动当本条确认人。
- **编译结果**：经既有 `compile_qi.py --ir ... --evidence ...` 不带state进行内存预览，丢弃0、候选0、待对齐1，原因明确为“专业确认人待安排”“产品未对齐：TF-213HE（LCY）”。IR映射pending_alignment、preview=true、ku_id=null；没有虚构候选编号或产生能力。型号身份与专业复用范围仍待审，当前不登记为原单source_irs，不宣称已接通负例原单回流。
- **验证**：复用合成负例DOCX，在test_compiler_v10补一项回归，核对混合品质、配方列、两组曲线、警告/后续、完整limits、原词后缀和未推定能力/温度。相关7项通过（1.74秒），全量pytest 54项通过（27.16秒），git diff --check通过；首份操作观察使用相同记录/种子分别运行已提交和当前实现，全部IR字段一致。未改web不重复构建。
- **交接**：本轮无生成模型、Jev、嵌入或Office调用；只写读取侧产物和文档，未写正式状态或真实签字。完成本次负例准备小项；后续按既有机制完成归属、型号对齐及必要的原单消费接线，再送研发确认，不将软件草稿当专业判断。本小项结束后停下等待用户评审，未提交或推送。

### 2026-11-01｜专家书面意见接入候选新草稿与多来源依据

- **范围与自查**：分支 v10，完整重读 AGENTS、总计划、相关 CONTRACTS/QI、V10.4/V10.5，按 C4/C7、G2/G3/G6、极简与禁止过度防御要求自查。保留原有三个前端文件改动和暂存状态。本小项归档用户取得的定稿答复，更新读取侧草稿与内存编译预览，不执行正式导入或签字。
- **实际材料**：以核对包中已确认定稿为准，未从原始表单占位符推定温度。专家意见保存为独立内部 L3 来源，按分项保留原文及指纹；原始试样、说明书/SDS与专家答复各有出处。两份更新后的 TrialRecord、观察IR、五项 Proposal、预览结果和审阅入口均在 `data/knowledge_v10/professional-review/expert-feedback-20261101/`，复现与处理边界见[准备说明](../trial/expert-feedback-v10.md)。
- **草稿与条件**：准备正例单次观察、负例混合结果观察、对外话术判断、正式适用判断、负例风险判断，共五项。型号后缀依书面意见对齐到已登记主产品，原词与同浴条件仍留在观察/限制中。话术保持既有 form=null 的结论草稿，后续按业务员受众准备 statement，不扩编译能力形式；Q6仅保存建议、不生成 ask。正式适用采用专家认可的125–130℃，保留全部限制和设备原文，只用现有枚举表达明确包含的设备子范围；不把试样保温点写入正式温度范围，也不宣称带限制的判断已能在客户自助侧形成确定推荐。
- **最小修改**：`trial_ir.py` 按每项 Citation 的文档编号生成 EvidenceRef，修复新专家引用被写成原报告编号的实际接线问题；IR审阅页与 `trial_review.py` 支持可选来源链接映射。`compile_qi.py --ir` 在配置来源中按引用文档回取并核对原文/指纹，复用原 admit；无新冻结字段、权限机制、重试框架或正式写入入口。
- **真实运行**：运行本机 `prepare.py` 后，既有 admit 在无 state_path 的内存知识库中得到五条 L3 candidate、一条 L3 proposed applicable，丢弃0、未对齐0，原候选未恢复。预览编号与正式编号明确区分。再分别运行 `uv run --env-file .env python scripts/compile_qi.py --config <preview-config.yaml> --ir <两份新IR之一> --evidence <对应原报告evidence.json> --out <compile-report.md>`，均为候选1、丢弃0、未对齐0，不传 --state。
- **验证**：扩展既有合成负例回归，覆盖专家补充 Citation 经 IR 转换仍指向独立来源，不新增测试文件。最终 `.venv/Scripts/uv.exe run --env-file .env --locked --no-sync pytest -q` 为57项通过（32.64秒）。本地 `check.py` 核对210处链接及锚点（含13处专家来源链接）、10份输入SHA不变；`git diff --check`通过。未修改本项以外的前端，不重复构建；未触碰冻结契约，data/runs未入库，密钥仅由 --env-file 注入。
- **交接**：本项真实模型调用0、正式状态写入0、正式确认/授予/范围批准0；原实例旧稿仍为withdrawn，产品仍未在化言发布。书面意见已收到不再列为缺失，但新稿尚未导入工作面或生效；下一步在用户评审后接来源与候选，再由有权人员办理系统生效动作。未提交或推送，完成本小项后停止等待用户评审。

### 2026-11-01｜首版收口：五项新候选经门面正式导入

- **范围与自查**：切包前再次完整重读AGENTS、总计划、相关CONTRACTS/QI及本包；保留V10.1未提交改动，按C7、G2/G3/G6及极简要求自查。本包只处理完整条件候选和同层提议，不代办专业确认、下行授予、产品批准或发布。
- **实际导入**：确认本地8766未运行服务后，使用`uv run --env-file .env --locked --no-sync python data/knowledge_v10/professional-review/expert-feedback-20261101/import_candidates.py`续跑first-report。只通过HuayanApp.import_proposals导入既有五项提议，没有改写qi_state或直接调用底层写入口。得到ku:claim:2（正例操作观察）、3（负例混合结果观察）、4（拟对外话术判断）、5（正式范围判断）、6（负例风险判断），均为L3 candidate；cap:1为audience=3、status=proposed的适用提议，保留125–130℃、枚举子范围及完整limits。
- **来源与状态**：原报告组别、阶段、单位及限制仍保存在两份读取侧记录/IR和候选完整指纹引用中；两份观察IR对应正式编号写入mapping，话术与风险保持逐字专业表述。ku:claim:1仍withdrawn，未恢复或复签；产品仍project。编译器预指定confirmed_by不计专业签字，capability_granted中的proposed记录不计正式授予。
- **核对与产物**：`formal-import/import-report.json`保存实际编号、IR映射和状态，review.html为当前交接入口；开发者经现有GET /api/claims及POST /api/qi/review回取五条候选的全部依据，指纹顺序与候选一致，同事拒绝、客户检索不可见。回取快照仅供交接，签字前仍须在工作台重新读取。此包复用V10.1最终57项离线回归，未改业务源码或新增镜像测试；真实导入检查通过，新增专业确认/正式授予/批准/发布/模型调用均0。
- **交接工作面**：当前first-report共享实例已用原CLI后台启动，http://127.0.0.1:8766/及/api/meta均200；使用既有mock/System1与规则抽取供人工审阅，不能把它记成在线模型业务验证。原审阅入口标明预览历史，链接实际入库交接。整包首版候选与补充依据候选机制已交付，正式签字、范围批准和下一单复用归V10.7；用户现在无需重复提供已取得的专家判断。未提交或推送，按工作包汇报后继续可独立推进的内容。
