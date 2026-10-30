# WP-5v10｜从试样记录形成完整条件候选

> 决赛必需｜状态：首条 IR、条件保留与补充依据候选化已实现；TF-213HE 已补 SDS/说明书身份依据，正式目录登记与真实候选入库待归属安排，确认挂接交 V10.7｜先编译一条值得复用的判断。

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
