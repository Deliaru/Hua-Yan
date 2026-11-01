# WP-6v10｜温度一个字段的抽取与范围匹配

> 决赛必需，单字段｜状态：C2离线链路及编译接线完成；当前轮/历史分离修复保留。最新Kimi原5轮实调及严格回放通过，另5条既有未知/多阶段/否定边界通过。真实专业范围确认及下一单真实复用仍待完成｜首版只处理摄氏温度和闭区间。

## 目标

客户说出温度后，系统能判断是否落在专业人员已授予的范围内，并让下一单使用这项判断。

## 依赖

[V10.5](WP-5v10-compiler.md) 的条件样例。C2 的具体字段及兼容方式在本包开工时列清，按总计划的契约约定实施；V10.7 的首次候选审阅可以先开始。

## 必读

[QI](../QI.md) 完整情境；`l1/extract.py`、`domain.py`、`knowledge/store.py` 的视图；相关 session/seeds 契约。

## 允许修改的范围

温度需要的最小契约差异、抽取入口、领域比较、能力视图、调用门面和温度展示及相关测试。

## 交付物与设计

1. 在既有抽取入口识别摄氏温度单值/闭区间及“不清楚”，保留原话，作为当前需求的已知条件传给匹配。
2. 能力情境保存专家确认的温度范围，与现有枚举条件共同匹配。在现有 `domain.py::match_candidates` 中加入温度闭区间包含判断，客户区间需完整落在授权区间内；满足且无其他未知/限制时为 `confirmed`，温度未知为 `possible` 并进入 `unknown_slots`，超范围则不命中该情境。
3. 沿“客户抽取→当前需求→能力视图与匹配→下一单结果”完成最短链路，界面显示温度及所用能力。先处理这条链需要的字段和调用方。
4. 其他数值、单位口径和专业限制继续保存原文并交研发判断。修正后重新准备试样、重新发布等路径作为第二步扩展，现有 V9.6a 行为继续保留。

## 验收

共用回归：G2/G3。

- 其余条件满足且无未知/限制时，用合成授权 70—80℃验证现有匹配结果：75℃与 72—78℃为 `confirmed`；温度未知为 `possible`，且列入 `unknown_slots`；85℃与 75—85℃不命中该情境。
- 一段实际模型抽取的温度进入当前条件，后续同条件需求采用对应有效能力。
- 原有枚举匹配通过现有回归；真实复用的温度范围有专业依据和确认记录。

## 不做

pH/用量/时间等多字段、开区间、单位换算平台，以及数值条件修正到试样/重新发布的全链改造；决赛后按试用需要扩展。

## 完成记录

### 2026-11-01｜Kimi选型后的温度保真回归

- 按AGENTS及本包G2/G3自查，沿既有抽取入口和匹配器运行，不改任何本包源码、规则、提示或契约。业务配置固定Pro/moonshotai/Kimi-K2.6，caller=agent:extract、真实网关、无fallback。
- 原入口`uv run --env-file .env --locked --no-sync python scripts/run_online_temperature.py --config data/knowledge_v10/checks/model-choice-20261101/app.kimi.yaml --run-id temperature-kimi`，5次真实请求得到[75,75]、[72,78]、[85,85]、unknown/null、[75,85]，合成70—80℃上依次confirmed、confirmed、不命中、possible、不命中。改用app.kimi.replay.yaml及temperature-kimi-replay，5缓存、0网络且结果逐项一致。
- 同根temperature_edges.py复现已报告的5条边界：实际未知后引用说明书75℃、75℃但不确定、多阶段先60℃再75℃均清空旧已知值为unknown/possible，多阶段保留整句；局部否定“是75℃，不是85℃”保留75，“不是75℃而是85℃”为85。首次脚本错误强制一般未知也须整句引用，导致在语义已正确的第一条停下；按既有契约修正为仅多阶段要求整句，原响应保留并命中缓存，随后4次新增请求完成。未改核心校验或放松语义要求以迁就模型；本轮该边界共5次新增请求、1缓存，停止前响应亦保留。
- 原五轮及5条边界均是合成开发回归，不是产品范围、盲测或任意表达可靠性结论。全量离线62项通过（43.21秒），正式状态未动；[实跑汇总](../../data/knowledge_v10/checks/model-choice-20261101/review.html)保留逐条原话、结构及现有匹配结果，专业授予/真人复用仍待后续。

### 2026-11-01｜35B升级后重跑多轮温度保真

- **范围与自查**：用户要求升级角色模型并验证主线，按AGENTS及本包G2/G3复用原5轮失败回归。只使用既有LLMExtractor→validate_extraction→apply_extraction→match_candidates；本包没有新增代码、规则、契约或测试样板，当前轮/历史分离保持。实际模型为Qwen/Qwen3.6-35B-A3B，仍SiliconFlow同地址、BACKUP_API_KEY、统一网关caller=agent:extract，无降级。
- **真实结果**：`uv run --env-file .env --locked --no-sync python scripts/run_online_temperature.py --config data/knowledge_v10/checks/model-upgrade-20261101/app.online.yaml --run-id temperature-qwen35`，5次新增网络请求、0缓存。75℃、72—78℃、改口85℃、实际温度不清楚、75—85℃依次为[75,75]、[72,78]、[85,85]、unknown/null、[75,85]；当前quote与轮次对应，明确未知没有继承旧85℃。合成70—80℃范围上依次confirmed、confirmed、不命中、possible、不命中，未知列入temperature_c；该范围不是TF-213HE专业授权。
- **严格回放与边界**：同入口改用app.replay.yaml、run-id=temperature-qwen35-replay，5缓存命中、网络0，逐轮输出及匹配与实调一致。原始结果、meter和trace留在上述检查根的online-runs；[汇总](../../data/knowledge_v10/checks/model-upgrade-20261101/review.html)明确区分真实模型/合成情境。全量离线pytest62项通过（33.26秒）；原正式状态、真人待审状态和canonical读取文件指纹未变。只报告原五轮回归，不推断任意表达可靠或专业复用完成。

### 2026-11-01｜P1：分开当前发言与历史，修复Qwen多轮温度旧值残留

- **范围与自查**：按用户最新要求暂停提交及配置卫生，只修温度P1。已重新完整阅读AGENTS，再读总计划、相关CONTRACTS/QI及本包，遵守G2、统一网关与caller、极简及禁止过度防御要求；保留已有工作区改动，没有提交或推送、改Worker配置、切换型号或扩展冻结契约。
- **原因与最小修复**：LLMExtractor原输入把历史与本次发言混在同一turns数组；实调Qwen返回历史轮次及旧温度，单纯追加提示没有解决。现在只把读取侧模型输入拆成history=turns[:-1]与current_turn=turns[-1]，previous仍保留已保存状态、asking保留追问。prompts/extract.md明确只抽当前发言的增量及纠正，历史仅解释指代；Python不再追加行为提示。没有规则覆盖模型输出、额外模型调用、另建重试或修改validate_extraction/apply_extraction及匹配器来掩盖错误。
- **同一失败序列真实验证**：固定Qwen/Qwen3-VL-8B-Instruct，实际执行`uv run --env-file .env --locked --no-sync python scripts/run_online_temperature.py --run-id temperature-qwen-current-turn-20261101`。原来的5轮输入依次得到[75,75]、[72,78]、[85,85]、unknown/null、[75,85]；在合成70—80℃授权上依次confirmed、confirmed、不命中、possible（unknown_slots含temperature_c）、不命中。每轮quote逐字来自本轮，turn_id依次为当前1—5轮，未知不再沿用旧85℃。这不是TF-213HE产品范围或专业签字。
- **计量与严格回放**：5次真实网络请求/5成功响应、失败0、缓存0；caller全部agent:extract，实际模型均上述固定型号，无降级、规则替代或觉生成模型调用。使用本地replay=true副本配置重跑同入口，5份缓存命中、网络0，结构化读数、引文轮次与匹配结果逐项一致。原失败缓存未删除；输入和提示改变自然产生新缓存键。记录位于data/knowledge_v10/checks/qwen-temperature-p1-20261101/summary.json及review.html，原运行计量保留在online/runs对应目录，均不入库。
- **离线回归与边界**：已有test_conditions_v10.py补1个当前轮/历史分离的边界回归，使用合成结构化输出检查输入分离及旧已知值被明确unknown替换；不把该夹具当模型语义成绩。全量`uv run --locked --no-sync pytest -q`为60项通过（32.22秒），git diff --check通过。未改前端，不重复构建。本次覆盖已复现的5轮回归，不宣称任意表达均可靠；专业曲线核对、真人确认与四岗位试用继续保留。

### 2026-10-30｜C2 最小范围字段与现有候选匹配

- **范围与基线**：分支 `v10 @ 7d1b773`，开始时工作区干净。按用户要求进入 M2 的 V10.6 首个小项；编程前已完整重读 AGENTS、总计划、相关契约/QI 和本包，按最小增量、条件保真及禁止过度防御要求自查。真人签字继续留待研发测试，不代替 JianChao Xi 确认真实范围。
- **C2 最小差异**：`contracts/seeds.py::Situation` 只增加 `temperature_c: tuple[float, float] | None = None`，表示摄氏闭区间；单值用相同端点。保留枚举 `conditions` 和旧情境默认含义。`match_candidates` 只增加有默认值的关键字参数 `temperature_c=None`，原有调用兼容。`applicable.payload` 使用可选 `[lower, upper]`；未加温度时不新增 payload 键，现有种子迁移和能力视图保留已表达的范围。已同步 `docs/CONTRACTS.md`，未建设通用数值条件平台。
- **实现**：`domain.temperature_match` 统一返回满足/待补/超范围，直接接入原 `match_candidates`。完整包含且枚举条件已知、无原文限制才为 `confirmed`；温度未知则 `possible` 并增加 `unknown_slots=["temperature_c"]`；任一端超范围则该情境不命中。选择同一产品的情境时把温度待补计入未知条件数量，保持温度与该情境的其他条件绑定。没有新增匹配链路、重试或重复权限检查。
- **必要回归**：新增 `tests/test_conditions_v10.py` 两项合成行为测试，验证迁移→有效能力视图→匹配，75℃、72—78℃与闭区间边界70—80℃命中，未知温度待补，85℃和75—85℃不命中；同时覆盖原文限制仍为可能、不同情境的温度/面料不交叉组合、优先选择已满足情境。运行 `uv run --no-sync pytest -q tests/test_conditions_v10.py tests/test_wp0.py tests/test_applicable_limits.py tests/test_compiler_v10.py`，14项通过（2.22秒）。
- **运行与真实资料边界**：运行合成70—80℃案例并只读核对真实 `first-report` 状态，产物为 `data/knowledge_v10/checks/temperature-core-first-report.json`。五个指定案例依次为 `confirmed / confirmed / possible / 不命中 / 不命中`。真实报告 `ku:claim:1` 的15条依据指纹仍一致，状态仍为 `candidate`，未写入真实温度授权，原正式状态文件字节未变。本次没有生成模型、视觉模型或 Jev 调用；上述范围仅为合成测试授权，不代表 TF-213HE 的适用结论。
- **交接与未完成**：首个小项完成，未提交或推送，停下交用户评审。下一小项在同包接入抽取输出、`NeedState` 与会话匹配及温度展示，保持未提及与明确不清楚的区别；实际模型抽取、真实专业范围确认、授予及下一单复用仍待完成，不能将 V10.6 整包记为通过。

### 2026-10-30｜客户温度抽取、会话匹配与展示

- **范围与基线**：分支 `v10 @ 30cd425`，第二小项开始时工作区干净。本次按用户评审在同一基线的既有未提交修改上修复四处缺口，保留其余工作区改动。编程前已重新完整阅读 AGENTS，再读总计划、相关契约/QI 与本包，按极简实现、语义只在抽取入口理解及禁止过度防御要求自查；评审仍由用户进行。
- **C2 最小增量**：`contracts/session.py` 增加具体类型 `ExtractedTemperature` / `TemperatureFill`，仅含摄氏闭区间、`filled/unknown`、逐字原话和对应客户轮次（输出为 `turn_n`，状态为 `turn_id`）。`ExtractionResult.temperature`、`NeedState.temperature` 和 `SessionView.temperature` 均默认 `None`，兼容已有输出、会话及视图；枚举 `slots/known()` 保持原状。`NeedState.known_temperature()` 供下游消费，契约文档已同步。
- **抽取与保真**：`l1/extract.py` 接入规则降级读数；`prompts/extract.md` 明确模型按同一结构返回温度，不把产品说明、假设或否定旧值当成当前条件。已有 `validate_extraction` 外部边界核对客户原话、轮次、状态与升序区间，`apply_extraction` 只在本轮有温度结果时更新。漏提不清空，明确不清楚/否定无新值转待补。本次修复 `_CELSIUS/_temperature`：明确摄氏单位直接识别；裸“度”须有本句或上一轮追问的温度语境，并排除紧邻硬度/牢度/白度/浓度/粘度/酸度/碱度的数值。正向收集未被局部否定、无开区间后缀且升序的有效匹配，否定前缀仅取前一匹配及最近分句标点之后的局部片段。仅一个有效匹配时返回 `filled`；多个有效匹配时，仅在最后两项之间含“不对/说错/改成/改为/其实/更正”等显式更正词时采用最后一项，否则保留整句为 `unknown`、`celsius=null`；全部匹配不可用也保留整句待澄清。“我们温度是75℃，不是85℃”保留75℃，“不是75℃而是85℃”采用85℃；“先60℃保温再升到75℃”不能丢弃前段而确认适用。没有另建语义解析链或单位换算平台。
- **现有链路接线**：`l1/session.py`、`app.py` 在当前推荐及能力失效后的替代匹配中透传结构化温度；温度变化触发原有条件变化/重匹配，抽取和匹配事件记录温度。推荐说明只引用所选能力的完整情境，列出授权温度、温度待补提示与能力编号。替代情境同时更新候选状态及未知条件。本次补齐 `domain.consistent(..., temperature_c=None)`，在同一情境中核对枚举与温度，L1 回答、发布后原会话匹配及 `route_of` 均透传温度；轨迹读取既有 match 事件中的温度并补 `slot="温度"` 的不匹配项，前端沿既有 `WhyRd` 展示。契约说明同步，未新增契约字段、Jue-K 特征或枚举追问槽位。
- **候选比较修复**：`ingest/compile.py::_key` 将非空 `temperature_c` 归一为 tuple，与既有条件集合比较一起使用，避免 JSON list 与内存 tuple 导致相同 payload 被误判为不同；不同温度范围仍不同。
- **助手与工作面**：`agent/tools.py` 的现有需求卡/会话读取返回温度，`find_products` 增加一个默认 `None` 的扁平温度参数并只透传原匹配函数。`web/src/types.ts`、`components/ui.tsx`、客户页与业务员页显示温度单值/范围、原话及“尚未提供/温度待补充”的区别；能力范围及编号沿既有推荐卡说明展示，不增加审批平台。
- **必要验证**：`tests/test_conditions_v10.py` 保留第二小项的抽取→会话→推荐与保真测试，按本次真实缺陷新增两项断言组：摄氏单位/裸度语境及局部否定、温度 list/tuple payload 等价；在既有场景补充同情境 `consistent` 判断、85℃问“T-205怎么用”附不适用说明、轨迹温度排除项。多阶段回归先填入75℃，再输入“先60℃再75℃”及“先60℃保温再升到75℃”，断言整句保留为 `unknown`、已知温度清空、候选为 `possible`；随后否定旧温度仍不残留已知值。单值、闭区间、局部否定及显式更正保持 `filled`。修复多阶段回归后运行全套 `uv run --no-sync pytest -q`，45项通过（23.25秒）；此前 `npm --prefix web run build` 已通过，仅有既有打包体积提示，本次仅文档同步不重复构建。没有新增横切防御测试。
- **真实样例与模型边界**：既有 `data/knowledge_v10/checks/temperature-session-first-report.json` 记录以报告已有132℃为开发者合成对话输入，规则抽取得到 `[132,132]`，后续“谢谢”保留事实，“温度其实不清楚”转 `unknown`。本次修复后只读重核：132℃仍正确抽取，真实 `ku:claim:1` 仍为 `candidate`，15条依据指纹一致；未写正式状态或替 JianChao Xi 签字。这不是实际客户发言或实际模型抽取成绩。无生成模型、视觉模型或远端 Jev 调用，离线推荐用明确标注的 mock System1。
- **交接**：本小项完成，未提交或推送；停下等待用户评审。模型路径已接好但实调未验，真实专业范围及授予、范围批准和下一单真实复用仍待 V10.7/V10.9 后续完成，V10.6 整包不能记为通过。

### 2026-10-30｜修复用户指出的 P1：明确未知温度被前文数字覆盖

- **范围与实现**：当前 `v10 @ a7b6a68`，按用户审查修补既有 `_temperature`，不改匹配器或契约字段。已重读 AGENTS、总计划、相关契约/QI 和本包，按 G2 与禁止过度防御要求自查。首版按数字与未知词的位置比较仍遗漏反序资料引用和省略主语的不确定表述，用户复审暂未通过；本次移除该比较，先排除局部前缀明确为说明书/资料/报告引用的数字，再识别涉及温度或独立“不确定”等分句。实际温度未知不能由后面的资料或裸数字解除，只有后续带“问过/实测/确认”等明确补充信息的实际读数才能恢复 filled；不能确认时沿原路径保留整句 `unknown`、`celsius=None`。裸度语境、局部否定和多阶段保真逻辑继续复用，没有新增语义处理平台。
- **验证**：`test_conditions_v10.py` 现有会话测试先填75℃形成 confirmed，再覆盖原两条失败输入以及本轮“实际温度不知道，说明书写75℃”“温度75℃，不确定”，均断言旧值清空、原话完整保留、候选为 possible 且 `unknown_slots=["temperature_c"]`。同一断言组补充裸数字/资料确认不能解除实际未知；正例保留问过或实测后明确补出温度、说明书与实际值区分、水硬度不清楚不覆盖已知温度。单值、闭区间、多阶段、否定更正等既有断言继续通过。本包6项通过（1.42秒），全量 `uv run --no-sync pytest -q` 46项通过（23.25秒）。本次未改前端，不重复构建。
- **真实材料边界与交接**：本次只读核对首份报告15条依据指纹和 candidate 状态，以报告132℃作明确标注的合成输入，“实际温度不知道，说明书写132℃”与“温度132℃，不确定”均转 unknown 并保留整句。未写正式状态、未调用模型、未替 JianChao Xi 签字。用户已通过候选列表归属修复，温度 P1 的补充修复待再次复审；不声明整包或全仓库审查通过，未提交或推送。

### 2026-10-30｜C2 从编译提议传入原有授予与批准链

- **范围与基线**：`v10 @ 6232483`，开始时工作区干净，用户已通过上一轮评审。已完整重读 AGENTS、总计划、相关契约/QI 与涉及的 V10.5/V10.7 工作包，按最小增量、G2/G3 与禁止过度防御要求自查。本次只补温度字段在编译及原有签字材料中的消费，不增加能力形式、匹配链或审批入口。
- **实现**：读取侧内部 `compile.Proposal` 增加 `temperature_c: tuple[float, float] | None = None`，有值时由 `admit` 原样写入既有适用 payload，现有 `limits` 仍完整保留。编译提示明确区分原文适用范围与单次试验/多阶段温度；旧提议缺字段保持兼容。`app.questions` 的人类材料增加温度展示，正式授予继续复制原 payload。未改冻结模型字段、觉特征、目录或权限机制。
- **纵向验证**：新增一项基于 `tests/fixtures/reader/synthetic-temperature.txt` 的合成集成测试，经现有门面完成候选导入→固定证据确认→同层适用批准→既有 qi_grant 研发授予→客户范围批准→下一单匹配。全程保持70—80℃；待批准能力不进入客户视图，批准后75℃为 confirmed、未知为 possible、85℃不命中。签字均为测试临时实例中的模拟，不计作真人专业确认。全量 `uv run --no-sync pytest -q` 47项通过（23.09秒），前端构建通过（仅既有体积提示），差异格式检查通过。
- **真实报告**：使用既有 `scripts/compile_qi.py --config data/knowledge_v10/instance-first-report/app.yaml --ir data/knowledge_v10/compiler/SRC-3a2130604c/operation-ir.json --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --out data/knowledge_v10/checks/temperature-proposal-first-report/compile-report.md` 进行内存预览。候选1、引文丢弃0、未对齐0、能力提议0；原 IR 仍为 observation、form=null、temperature_c=None。实际 `ku:claim:1` 仍 candidate，TF-213HE 无适用能力，不从报告132℃推断授权范围。摘要在同目录 `summary.json`，未写正式状态、未调用模型或替真人签字。
- **交接**：本小项完成，签字材料展示详见 V10.7 同日记录。实际模型抽取、JianChao Xi 的专业判断、真实用途授予、必要批准及下一单真实复用仍待后续。未提交或推送，停下等待用户评审。


### 2026-10-31｜智谱LLMExtractor在线温度主线

- **实际入口**：`uv run --env-file .env python scripts/run_online_temperature.py --run-id temperature-online-2`。运行时使用config/app.online.yaml（gateway_mock=false、extractor=llm、agent_threads=object，models_config当时为config/models.yaml；后续Agent配置调整单列V10.9记录），调用现有LLMExtractor→validate_extraction→apply_extraction→domain.match_candidates，没有添加温度规则或第二条匹配链。
- **针对真实接口问题的最小调整**：实调返回了只含结束标签的推理前缀、非数据Schema及2048 token截断；前缀处理归统一网关。LLMExtractor仅将请求预算改为4096/180秒并要求返回单个temperature对象、逐字quote和JSON数据实例；字段、领域比较及未知语义均保持。首轮失败与中止记录保留，不用规则结果代替模型。
- **在线结果**：依次输入75℃、72—78℃、改口85℃、实际温度不清楚、75—85℃，得到[75,75]、[72,78]、[85,85]、unknown/null、[75,85]；进入现有匹配器后为confirmed、confirmed、不命中、possible（unknown_slots含temperature_c）、不命中。未知已覆盖旧85℃事实。70—80℃只是在内存中的合成软件范围，不导入为TF-213HE授权、不声称专业适用。
- **计量**：temperature-online-2/gateway-trace.jsonl为23次真实网络尝试：glm-4.6v-flash20次、glm-4.1v-thinking-flash3次；获得7条响应（主4/备3，包含结构纠错），最后形成5次合格抽取，缓存命中0。meter、原始缓存及逐轮temperature-check.json留在data/knowledge_v10下。caller全为agent:extract，未写专业结论或用途能力。
- **验证与边界**：全量离线pytest57项通过（27.43秒），不依赖外网或密钥；真实模型调用单独运行，不并入测试成绩。已按AGENTS铁律2/3/4/10/11自查。线上抽取和三态匹配已通，真实范围判断、确认授予及下一单专业复用仍需研发办理，不能由合成范围或模型代替。
