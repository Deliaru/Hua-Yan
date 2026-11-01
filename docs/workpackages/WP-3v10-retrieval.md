# WP-3v10｜一道图表题的检索与查证

> 可演示即可｜状态：单题首版演示交付完成。25页同源对照中，关键词A及图文C+Jev均正确选页并取回7.21S/9.22S；C单独使用选错页。原生表格优先、固定Qwen选择、原图审阅及严格回放已通；仅一个已知开发题，不代表全库成绩，不恢复35题扩写。

## 目标

从一道来源齐全的真实问题，展示找到正确页、读出结果和回看出处。

## 依赖

[V10.1](WP-1v10-sources.md) 统一入口、[V10.2](WP-2v10-evidence.md) 对应文件的证据与读取能力。报告编译主链不等待本包。

## 必读

v3 第 10、10B 节；[总计划](REPLAN-v10.md)；现有 `System1Client`、网关与资料检索入口。

## 允许修改的范围

读取侧索引、检索和查证模块；配置、脚本、现有工作面的查证结果组件及对应测试。

## 交付物与设计

1. 按产品和明确版本筛选资料，先交关键词检索 A，再接 EmbeddingGemma 2 图文检索 C。命中后回取完整证据，答案展示数值、单位、条件和出处。
2. 使用同一题目、来源、解析、读取模型和页数预算比较 A/C，逐题记找到或漏掉了什么，据此选择默认配置。
3. Jev 核对/重排作为另一个开关，记录它修正或误判的案例；首轮用于辅助核对和排序。
4. 一道题通过后扩到现有可评分题；跨报告汇总直接使用 V10.4 的结构化表。

## 验收

共用回归：G1/G2/G5/G6。

- 一道图表题能从问题走到正确页面、正确读数与可回看的引用。
- A/C 及 Jev 开关各有同条件的逐例记录，失败能归到解析、检索或读取环节。
- 配置和实际处理范围写入演示说明。

## 不做

独立文本向量 B 组、分块/前缀消融、大样本概率校准、全库索引优化；这些留给决赛后按失败问题开展。

## 完成记录

### 2026-11-01｜单题25页真实对照与失败归因

- **范围与自查**：用户明确恢复本包；核对分支v10（本轮HEAD为3b5670e），工作区原先干净。完整重读AGENTS、REPLAN、相关CONTRACTS/QI及本包，按G1/G2/G5/G6、极简及禁止过度防御要求自查。只运行已选03-Q03，不扩题，不改冻结契约、觉或正式业务路径。
- **同条件输入**：仅使用SRC-18358d2dd7同一已选PPT的25张既有PowerPoint COM原生PNG；复用read_pptx_slide读取25页129个原生块及15张表的合并关系，落到独立data/knowledge_v10/retrieval/v10.3-20261101/evidence.json。没有重绘Office形状、使用LibreOffice或更改原件与canonical读取记录。内部来源只在隔离清单指定rd:JianChaoXi演示归属，原清单仍未指定，不当作实际作者。隔离HuayanApp按既有read_source入口检查后才建索引，选页图继续经read_source_image回取；未向客户或业务员开放原文。
- **实现**：retrieval.py补source_pages，按块的实际页号建页级图文输入并保留合并关系；chart_qa.py与prompts/chart_qa.md负责命中页辅助读取。原文重排引句无法回查的真实失败后，改为按模型所选原值在原表内唯一定位，保存原值、单元格坐标和逐字引文；重复值或原表单位歧义待人工核对。按原生合并关系附上列头/行头，不按答案挑格。image.py仅抽出共用1536px编码函数，沿用原SHA缓存、60秒请求和网关重试，无新锁/重试/权限体系。新类型均留读取侧，不写契。
- **评估隔离**：新增`python -m huayan.eval.retrieval_v10`；只把原题query交检索、Jev和读取。预测先落predictions.json，随后eval才读取verified_charts核对来源SHA/页码、值、原单位、实际坐标、对象与问题条件。金标不进入reader、Agent、Jev或觉。本题是已知开发回归，调试输入不能当盲测；多个配置不当作多道题。
- **真实选页**：A关键词排序15/18/14，C图文排序14/15/18；C+Jev在同一3页候选池中重排为15/18/14。Clef对15页返回yes=0.9646，14页0.0108、18页0.0327。三个配置共用解析、Qwen/Qwen3-VL-8B-Instruct、3页候选池和1页作答预算。Gemma实际加载google/embeddinggemma-2、本地快照f9972ac22e696a105c482202646979e33e4b5a1e、CUDA/bfloat16、768维，25页向量已保存，未退回关键词冒充C。gemma_env缺Office读取依赖的初次失败后，只补python-docx/python-pptx/pypdf及依赖，不替换torch/transformers、不下载权重、不改项目锁文件。
- **调试失败保留**：native-headers阶段运行中A及C+Jev虽选中15页，Qwen误取TF-1871Y/0.25%列的9.92S与13.56S；本题目标是TF-1871/0.4%列7.21S与9.22S。C选到14页且未得到合格读数。该阶段三配置完整验收均失败；Jev只纠正选页，不保证图片辅助模型选对列。引句改写、坐标失败、错列及HTTP500的早期尝试保留为调试历史，不挑早期偶然数字正确冒充最终通过。报告在失败辅助稿前明确标不可使用，未写客户答案或工艺指令。
- **原生优先后的结果**：按项目已有原生表格优先要求，完整合并表记录交固定Qwen选择原值，原值/坐标/指标/单位及所属列头和行条件由原生记录取回；无完整合并表记录的页仍使用图片辅助。不是把金标坐标传模型，也不是按题目关键词写取值规则。native-first实调已返回7.21/9.22及正确条件，随后原生归属解析从实际列头取TF-1871，避免把模型误写的指标标题当产品。final-replay和delivery均得到A通过、C失败、C+Jev通过，正确原值坐标为r5c6/r6c6、原单位S；原页25℃、100ml、标准棉帆布等方法原文保留在审阅页。图文单独使用选14页的失败不隐藏。
- **计量**：native-first阶段Qwen新增网络请求1次、缓存2次；选中15页的请求使用原生表记录，不发送该页图像；14页仍走图像辅助并复用先前同请求缓存，原生页图在审阅材料中完整保留。首次live-final中Clef确有3次真实响应，此后同3个候选状态走现有S1缓存。全轮调试累计16次Qwen网络尝试，11次成功响应、5次HTTP500失败，计量/trace均保留。最终严格回放Qwen3命中、Clef3命中，新增网络0；正确值来自既有真实模型选择及原生表，不改写早期失败文件。索引耗时约16秒单列，不拿缓存行耗时宣称性能胜负。生成caller=ingest:extract，Clef为jev:grounding；觉大模型及专业签字0。
- **入口与产物**：`uv run --env-file .env --locked --no-sync gemma_env/Scripts/python.exe -m huayan.eval.retrieval_v10 --config data/knowledge_v10/retrieval/v10.3-20261101/app.yaml --actor rd:JianChaoXi --out data/knowledge_v10/retrieval/v10.3-20261101/native-first`；改out为delivery并加`--replay`严格回放。各目录有review.html、summary.json、排名、预测、向量、metering与trace，全部留忽略的data。无.env明文、正式确认/授予/批准；来源输入及隔离知识状态在每次运行内指纹不变。
- **检查与交接**：全量离线pytest62项通过（38.58秒），覆盖合并表头/行条件、原生定位/单位、统一权限及现有图片通路；未改web不重复构建，git diff --check通过。本题展示默认选择关键词A（最低模型依赖且选页正确），C+Jev作为重排改善对照；不改应用全局默认检索或冻结模型。已满足一道图表题、两组同条件对照、原生值/单位/条件/引用和失败归因的首版可演示范围。只是一题开发回归，不推出全局优劣、盲测准确率或纯视觉正确率；人工专业确认、主线四岗位业务仍按V10.7/V10.10办理。本包首版交付后停下交用户评审，未提交或推送。

### 2026-10-29｜按用户要求核对本地模型与 Jev 组件

- **范围**：修正用户预置的 `reader/retrieval.py`、`reader/verify.py`，增加 `config/reader.yaml`、本地试运行入口 `scripts/search_report.py` 和必要回归，另交付供用户部署的 Worker 替换稿。替换稿交付后已从工作区移除，保留当前工作区状态，服务端由用户维护。未修改冻结的 System1/Jev 契约、正式状态或角色工作面；未继续做图表问答展示、全库索引或对照扩样。
- **本地嵌入**：保留现有均值池化。已安装的 Transformers 5.21 模型实现会先将 token 隐藏层投影为768维，均值池化有效；修正点为查询/文档前缀、只读本地缓存、缓存目录与图片输入。目录由配置指定为 `D:/hf_cache/hub`，移除导入时修改全局 HF 环境变量的行为。图文使用原生页图和同页原文，未启用音频编码器。依赖列入可选项 `reader-embedding`。
- **Jev**：用户提供的旧 Worker 实际调用 `llama-3.1-8b-instruct-fp8-fast`，由生成文本给出布尔值与自报置信度，解析失败还补固定数字。替换稿调用 `@cf/cloudflare/clef`，使用 `state + questions`，保留原始 `model/answers/usage`；失败返回 HTTP 错误，不伪造否定结果。本地 `ClefWorkerClient` 只适配 Worker 地址与响应外层，复用既有 Clef/OneJev 请求、概率解析、计量和可选缓存；`JevVerifier` 注入 `System1Client`，使用 `caller="jev:grounding"`，不自行重试。阈值仅用于辅助提示，不能代替专业确认。
- **实际运行**：使用本机 `gemma_env/Scripts/python.exe`、已有 EmbeddingGemma 2 快照 `f9972ac22e696a105c482202646979e33e4b5a1e`、RTX 4060 Laptop GPU、bfloat16。首份报告3页成功编码为 `(3, 768)`，向量有限且归一化；对时间改善问题排序为第3、2、1页。缺少 Transformers 的 `.venv` 实跑退回关键词并明确记录 `degraded=true`。`gemma_env` 补齐了本次脚本使用的 pydantic/httpx/openai/tzdata 及项目导入，未替换已部署的 torch/transformers 或下载模型。
- **Worker 联通**：初始自定义协议实测后，交付替换稿；后续同一端点已返回 `model="clef"` 与正式概率。合成字段核对和首份报告3页的辅助证据核对均完成，计量留在 `data/knowledge_v10/retrieval/model-check/`。本次没有代用户部署 Worker；Gemma 检索在本机，Clef 辅助核对调用用户指定的 Cloudflare Worker。
- **运行入口**：`gemma_env/Scripts/python.exe scripts/search_report.py --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --query "试样工艺缩短了多少染色时间？" --jev --out data/knowledge_v10/retrieval/model-check/gemma-jev`。`--keywords` 使用关键词，去掉 `--jev` 关闭核对。此入口只读开发者本地报告产物，尚未接 V10.1 的角色读取入口，不是正式用户查证服务。
- **验证**：相关7项测试通过，Worker JavaScript 语法检查通过；随后与 Word 合并格修复一起执行全部离线回归，34项通过。新回归针对旧 Worker 协议不符、HTTP失败不得变成否定证据，以及正式概率与计量。真实运行是组件联通验证，不计作金标评测或专业判断。
- **归档边界**：`model-check/` 是合并格原文去重前的历史联通记录，含旧片段文本与指纹，已写明说明，不供 V10.4/V10.5 使用；主线读取更新后的 `evidence/SRC-3a2130604c/evidence.json`。工作区已删除的旧自定义协议探测脚本 `test_cf_ai.py` 随本次归档保留删除。未完成完整图表题读取或同条件 A/C、Jev 开/关评估，不据此宣布 V10.3 完成或选定默认配置。
- **主线交接**：停止本包扩展。下一小项为 V10.4 首份 A/B TrialRecord，之后 V10.5 候选编译、V10.7 人审确认授予与复用，再接 V10.6 温度条件。按用户要求逐项完成后停下报告；真人研发测试继续暂缓，不能由模型核对代替签字。

接口依据：[EmbeddingGemma 2 模型说明](https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2)、[Cloudflare Clef 正式协议](https://developers.cloudflare.com/workers-ai/models/clef/)，并与本机已安装源码及端点实测相互核对。
