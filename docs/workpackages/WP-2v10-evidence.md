# WP-2v10｜选定资料的解析与证据读取

> 决赛必需，按样例交付｜状态：最新视觉配置固定SiliconFlow Qwen/Qwen3.5-122B-A10B。首份报告4份隔离辅助稿真实读取及严格回放通过；B组温度/保温时间拆分改善，A组两项时间仍仅在引文、原生标签中保留，待专业核对。原8B稿与canonical记录保留；35题离线扩写继续停止。

## 目标

把首份报告中的文字、表格和曲线读出来，并能回到原页核对。

## 依赖

[V10.0](WP-0v10.md) 的清单和 C1/C4；与 V10.4 围绕同一报告推进。无需等待 V10.1 的查证入口。

## 必读

v3 第 05 节；[总计划](REPLAN-v10.md) G2/G5；`ingest/folder.py`、`gateway/client.py`。

## 允许修改的范围

`src/huayan/ingest/reader/`、网关图片适配、资料处理脚本、实际使用的解析依赖及相应测试。

## 交付物与设计

1. 按文件头识别当前文件，先接通这份 DOC/DOCX 的段落、表格、文本框和必要页面渲染；遇到实际格式问题选用转换组件。
2. 每块保留来源指纹、段落/表格/页面位置与原始内容。检索用小块，读数与审阅回取表头、单位、脚注、图例和相邻条件；短报告整体抽取。
3. 优先原生数据，曲线按文本框→字符画→视觉读取处理。读数带对象、组别、值、单位、条件与出处；难读项直接给人工补读。
4. 图片读取复用现有网关。完成首份报告后，再为 V10.3 接通选定 PPT/PDF 图表题；其余格式随试用材料扩展。

## 验收

共用回归：G2/G5。

- 首份报告的表格与工艺曲线能与原页并排核对，读取函数可交给 V10.4。
- 一个数值及其单位、组别和条件能回到明确位置；人工补读项可见。
- 后续图表题需要的格式单独记录结果，格式覆盖按实际文件说明。

## 不做

全格式齐备后才交付、整本扫描书处理、完整版本与索引重建体系。

## 完成记录

### 2026-11-01｜比较视觉候选并固定122B

- **范围与自查**：用户授权在SiliconFlow账号内自行选型。已完整重读AGENTS，再读总计划、相关CONTRACTS/QI、本包及V10.9；分支v10、起点5f80ad0，工作区开始干净。原base_url、BACKUP_API_KEY和Cloudflare仅Clef保持。所有生成走既有网关、合法caller且串行，没有适配分支、额外重试、锁、冻结契约或核心代码改动；未读取或输出.env密钥明文。
- **选型与配置**：重新读取账号models列表。业务选择Pro/moonshotai/Kimi-K2.6（见V10.9）；视觉比较同一图片/提示下的Kimi与Qwen/Qwen3.5-122B-A10B，最终config/models.yaml的fast/strong固定122B、enable_thinking=false、fallbacks=[]，沿用concurrency=1和retry_waits。不添加自动换型或按块选模型机制。
- **真实输入与结果**：读取侧隔离复制既有Office COM原生PDF/3张PNG及登记bbox，直接复用read_report_images/read_image、1536px压缩、60秒超时与图片缓存，原件和canonical文件不写。Kimi4次实读后，B组仍将保温时间混入unit；122B先实读同B裁图，再完整读取4份（新增3请求、B命中前一响应）。B组温度90/110/132℃与时间5/5/30min独立保存，三段升温速率、降温/出缸及红字时间可对照原图；A组跨页标题没有编造数字，A曲线的10min/40min仍只在quote、原生标签而非独立reading中，不能算完整结构化读取。模型text还转录了非请求配方摘要，保留原稿并提示不采纳；原生0..8与图像0.8差异保留待审，不覆盖原文。
- **缓存与产物**：`uv run --env-file .env --locked --no-sync python data/knowledge_v10/checks/model-choice-20261101/read_curves.py --models config/models.yaml --name qwen122`为同等配置的重跑入口；原实调models.122b.yaml与当前配置语义完全一致。改name为qwen122-replay并加`--replay`，4份严格命中、网络0。两候选完整辅助稿与开发者核对提示位于该根vision/kimi及vision/qwen122/review.html，原模型reading/response未被改写；只在隔离report.pending补实际遗漏提示，没有回填正式TrialRecord/IR或确认。
- **计量与验证**：本轮全部候选、探针、在线业务、温度及表格共50次新增网络请求，本地缓存13次。统一[实跑报告](../../data/knowledge_v10/checks/model-choice-20261101/review.html)保留逐运行meter/trace。全量离线pytest62项通过（43.21秒）；未改web、不重复构建。两份正式/待审qi_state及canonical Word证据SHA保持，所有产物在data忽略目录；本轮未重启8769旧服务。读图辅助仍待专业确认，未宣称M1专业质量或M3真人验收完成。

### 2026-10-29｜首份报告读取与 C1 落实

- **实现范围**：`reader/office.py` 按文件头识别当前 DOC/DOCX，用 Word COM 只读处理本地原件副本，导出原生 PDF、DOCX 读取副本和页码映射；PNG 由原生 PDF 渲染。`reader/word.py` 用 python-docx 读取段落、表格、文本框与 XML，按原工艺/试样工艺标题保持 A/B，合并格的同一物理单元格只读一次。`reader/evidence.py` 保存读取侧位置和标签，映射现有 Fragment，未增加 `Fragment.meta`。
- **读数范围**：原生数值与单位逐字保留，明确写成“温度×时间”的保温点直接配对；其余标签不凭 XML 顺序推断工艺执行顺序。异常数值和用量缺单位列为待补读。曲线速率与升降温线段的关联仍留在对照页等待判读，未生成完整 TrialRecord 或推定产品适用范围。
- **C1 差异**：按 V10.0 已批准约定，在 `contracts/gateway.py` 增加 `TextContent/ImageURL/ImageContent`，`Message.content` 扩为字符串或内容列表，原默认值与调用签名不变；同步契约文档。`gateway/client.py` 仅改消息内容序列化，沿用缓存键和计量；`gateway/mock.py` 按联合类型提取文字。`reader/image.py` 经现有 `gateway.structured`、`caller="ingest:extract"` 返回辅助读稿。未新增网关、缓存、重试或权限框架。
- **入口与产物**：`uv run python scripts/read_report.py --source SRC-3a2130604c`；本机实际使用 `.venv/Scripts/uv.exe run --no-sync python scripts/read_report.py --source SRC-3a2130604c`。产物在 `data/knowledge_v10/evidence/SRC-3a2130604c/`：`review.html` 为原页与原文对照，`evidence.json` 为读取记录，`document.xml` 为原生 XML，`native/` 为原件字节副本、Word 导出与页图。可配置现有网关后加 `--vision` 获取图片辅助读稿。解析依赖加入 `pyproject.toml`：python-docx、pypdfium2、Windows pywin32。
- **真实运行**：选定的原始 DOC 实际运行成功，Word 16.0 原生导出3页，提取30个非空证据块、3张表格、33条原生标签读数（含5个保温点，A组2个、B组3个）。位置为 A 配方第1页、A 曲线表跨第1—2页、B 表格/曲线第2页；报告无原生 chart 系列。7条待补读包括4个缺单位用量、1处异常数值写法和2组曲线线段关联。含企业内容的产物均留在被忽略的 `data/`。
- **测试**：执行 `uv run --no-sync pytest -q`，既有29项通过；新增原生读取测试首次发现文本框 XML 命名空间问题，修复后运行 `uv run --no-sync pytest -q tests/test_reader_v10.py`，本包2项通过。合成夹具及生成入口在 `tests/fixtures/reader/`；覆盖 A/B 保温点、合并格、缺单位、异常写法、结果节不继承B组及文本框读取。图片通路采用离线 HTTP 传输替身验证内容序列化、相同图片缓存复用、不同图片缓存区分和 caller 计量，不作为真实模型成绩。
- **实际模型与验收边界**：本次未调用真实生成模型、Jev、嵌入或 OCR；当前终端未配置 `BACKUP_API_KEY`，图片实调未完成。首份表格、曲线原生标签及原页对照已交付，数值/单位/组别/局部条件可以回到块与表格行列，待补项可见。后续 PPT/PDF 图表题读取尚未接入本读取器。研发测试安排继续按用户要求暂缓。
- **交接**：V10.4 可直接消费 `read_docx`、`read_native_labels`、EvidenceBlock 与本次读取记录，整理首份 A/B TrialRecord。已按要求重读 AGENTS、总计划、相关契约/QI 与本包；本次只完成实现、必要测试与真实运行，由用户评审，停在本小项。未提交或推送，未写入正式知识状态。

### 2026-10-29｜按用户评审修复合并单元格原文重复，收口交主线

- **问题与修改**：原先只对 `cells` 去重，`EvidenceBlock.text` 仍按展开后的网格拼接，导致首份报告 `table-3` 的横向合并格内容重复4次。`word.py` 现以同一套物理单元格遍历同时生成原文和单元格记录，保留首次出现的行列位置，不按文字内容去重。
- **真实产物**：复用指纹一致的 Word 原生 `native/reading.docx` 和已有页码、页图重新读取，更新 `evidence.json`、`review.html` 与 Fragment 文本/指纹。该合并格内容4次变为1次；30个块、33条原生读数、7条待补项不变，全部读数逐项与修复前一致。核对记录在 `data/knowledge_v10/evidence/SRC-3a2130604c/dedup-check.json`。未改原件，未重复渲染，未写正式知识状态。
- **验证**：在已有合成报告测试中补充原文与 Fragment 的合并格单次出现断言；本次全部离线回归 `uv run --no-sync pytest -q` 为34项通过（23.25秒），含已有业务回归、读取及模型适配检查。
- **交接与归档**：按用户要求提交本包当前成果；原件、含原文产物和模型缓存保持在不入库目录。V10.4 只使用本次更新后的证据记录，首份 TrialRecord 完成后交 V10.5，再推进 V10.7、V10.6。检索组件的完成情况单独记入 V10.3，停止支线扩展。已重读 AGENTS、总计划及相关契约/QI，按本文件完成必要核对，评审由用户进行。

### 2026-10-29｜对齐总计划附注一：结构化读图与现有缓存接入

- **范围复核**：已阅读用户提交 `6a3de2d` 的总计划附注一。此前的原生 Office 解析、合并格去重和 Gemma/Clef 适配继续保留；原图片接口只有文字读稿，且开发者读取脚本未启用网关缓存，需要补齐。本小项归 V10.2，不扩检索对照；后续编译按新范围仅处理操作经验与负例，V10.8 保留一条来源变化复核链。
- **修改**：`reader/image.py` 的读取侧 `ImageReading` 保留对象、A/B 组别、阶段、值、原单位、条件、图中位置描述与原文标签；未知值、单位、组别可为空，缺失与冲突交 `pending`。`reader/report.py::read_report_images` 用整份短报告原生文字作为上下文，逐页读取当前图片，保存页码、`method="vision"` 和网关实际响应；审阅页显示结构化读数、原页跳转、实际模型与降级标记。位置当前为原生页码加模型给出的标题／相对位置，尚非 MinerU 区域坐标。
- **缓存与调用**：`scripts/read_report.py --source SRC-3a2130604c --vision` 启用现有网关的 `data/knowledge_v10/cache/image-readings/` 缓存。原缓存键已包含图片字节、提示上下文、输出结构和模型配置，图片或配置模型版本改变会重新读取；不另建缓存框架。查询词不进入报告读图提示，审阅与后续编译消费保存的同一份读取记录。模型版本按配置中的模型标识区分，实际返回名保存在响应中；服务端若在同一别名下换模型，需更新配置标识，不能据此宣称能自动识别服务端换版。
- **原生解析与完整读取的区别**：不加 `--vision` 仍只输出原生解析，审阅页明确显示图片结构化读数待补；该产物不作为附注要求的“试样报告已完成全部读取”。试样报告可用上述入口逐页读图，普通资料按需读图与按证据键回取由后续统一读取入口接入。
- **验证**：执行 `.venv/Scripts/uv.exe run --no-sync pytest -q tests/test_reader_v10.py`，2 项通过（1.25 秒）。扩展已有合成 HTTP 通路测试，覆盖 A/B 条件和值的保留、相同图片与模型复用、图片变化及模型版本变化重新调用；这是离线传输验证，不是实际模型成绩。真实报告复用经原件与读取副本指纹核对的 Word 原生 DOCX 和页图重跑解析、更新审阅包，仍为 30 块、33 条原生读数、7 项待补读，原生读数逐项不变。记录在 `data/knowledge_v10/evidence/SRC-3a2130604c/structured-reading-check.json`，没有重新转换 Office 文档。
- **未完成与交接**：本机进程、用户和机器环境均未配置 `BACKUP_API_KEY`，已向用户询问可用本地配置位置；真实结构化读图尚未执行，未使用模拟结果填充真实报告。新增附注中的 MinerU 版面/OCR、区域坐标仍待实现；Agent/UI 的证据键回取和单入口权限检查归 V10.1，当前脚本仅供开发者本地运行，尚未接入 Agent/UI。未改冻结契约、正式知识状态或研发确认状态。已在编程前重读 AGENTS、总计划及相关契约/QI/本包，完成必要测试与真实原生读取；本小项停下由用户评审，未开始 V10.4，未提交或推送。

### 2026-10-30｜加载 .env；真实模型验证按用户要求跳过

- **当前基线**：结构化读图与缓存接入已在 `64bbf10` 提交。已重新阅读 AGENTS、总计划、相关契约/QI 与本包。未扩展契约、权限或重试机制。
- **配置已解决**：按用户提供的位置，用 uv 自带的 `--env-file .env` 成功加载项目根目录的 `BACKUP_API_KEY`；只检查是否加载，不输出密钥，不引入额外环境加载依赖。运行方式已补入 `scripts/read_report.py` 的说明：`.venv/Scripts/uv.exe run --env-file .env --no-sync python scripts/read_report.py --source SRC-3a2130604c --vision`。`.env` 仍由现有规则忽略。
- **实际调用结果**：用户已明确允许向 `https://api.soranori.com/v1` 发送本报告三页图片与原生文字上下文。首次运行完成 Word 原生导出，但生成模型连续失败，未生成图片读数或缓存。续跑复用现有原生页图，经统一网关取得明确错误：HTTP 500，服务端访问 `https://oauth2.googleapis.com/token` 时 `TLS handshake timeout`。这是网关上游故障，不再记为缺少密钥。
- **本次边界**：用户要求先跳过需要该模型的部分，因此停止进一步调用；真实结构化读图与真实缓存回放均记为“按用户要求跳过／未完成”，没有用模拟结果补入真实报告。审阅页的无结果提示改为“尚无可用的图片模型读数”，同时保留模型调用失败的说明。运行记录在 `data/knowledge_v10/evidence/SRC-3a2130604c/structured-reading-check.json`。
- **验证与交接**：本次仅补运行说明、提示文案和实际运行记录，未新增或重复执行测试；已有 2 项读取测试的通过记录继续有效，不当作真实模型读取成绩。首份报告原生 30 块、33 条标签和 7 项原生待补读保留，额外标明模型读取未完成；没有专业签字或正式知识写入。待用户评审后继续 V10.4，未自行推进下一包；MinerU 区域解析与 V10.1 统一回取入口仍按前条记录待办。

### 2026-10-30｜按用户要求准备 Cloudflare 视觉 Worker

- **本小项**：用户改为使用已有 Cloudflare `AI` 绑定，要求先提供代码自行部署。开始时分支 `v10`、基线 `052a487`，首份原生 TrialRecord 已提交。本次按 V10.2 的网关图片适配范围交付，已重读 AGENTS 全文、总计划及相关契约/QI/本包，并按最小实现要求核对；评审由用户进行。
- **文件与入口**：新增 `scripts/cloudflare_vision_worker.mjs` 与同名 `.md` 部署说明。Worker 的 `POST /v1/chat/completions` 将当前网关的文字/单张图片消息转成 Workers AI 的 `messages + image`，固定调用 `@cf/meta/llama-3.2-11b-vision-instruct`；`POST /license` 仅转交用户主动发送的 `prompt="agree"`，普通读取不自动接受条款。调用格式依据 [Cloudflare 官方教程](https://developers.cloudflare.com/workers-ai/guides/tutorials/llama-vision-tutorial/)。
- **契约与错误处理**：保持本地 `OpenAICompatGateway`、`caller="ingest:extract"`、结构校验及缓存路径；Worker 只适配当前非流式逐页读图。返回指定调用模型名和原始生成文本，不正则截取 JSON、不伪造读数、概率或 token 数；`json_object` 仅转换为提示要求，结构是否合格仍由本地 `structured` 决定。HTTP 输入不符和上游失败明确返回错误，不增设重试、缓存或权限框架。冻结契约和当前模型配置未修改。
- **验证与边界**：`node --check scripts/cloudflare_vision_worker.mjs` 通过，未新增冗余测试。未部署、未调用 Cloudflare 模型、未接受协议、未上传真实报告；没有真实模型或缓存回放成绩。免费额度按 Cloudflare 官方定价如实说明，部署说明列明下一步所需连接参数。
- **交接**：本小项代码交用户评审与部署；取得部署地址后再接回首份报告读图。原 Jev/Clef 核对接口继续保留。当前停下，不推进候选编译或其他工作包；未提交或推送。

### 2026-10-30｜按用户现有 Jev Worker 合并读图入口

- **修改**：用户提供了正在使用的 Clef Worker 代码，要求共用现有部署。更新 `scripts/cloudflare_vision_worker.mjs` 与部署说明，作为现有 Worker 的整体替换文件；根路径 `/` 保留 `state/questions/images` 输入与 Clef 原始返回，新增 `/v1/chat/completions` 供视觉模型读取，`/license` 继续只处理用户主动的协议接受请求。三个路径共用现有 `AI` 绑定和 `jev-proxy.xi1092183542.workers.dev` 域名，无需新建 Worker。
- **兼容**：读取侧 `ClefWorkerClient.path="/"` 已核对，无需修改 Python 客户端；CORS/OPTIONS 保留，允许请求头加入 `Authorization`。现有网关、模型配置和契约均未修改，没有扩展检索或编译工作包。
- **验证**：JavaScript 语法检查通过；使用合成请求在本地进行一次两路转发检查，确认 Clef 输入与返回原样保留、视觉请求送到指定视觉模型并保留图片和生成文本，全部通过。未新增测试文件，未调用真实模型或上传企业资料，不作为读图效果成绩。
- **交接**：已重新完整阅读 AGENTS，再读总计划、相关契约/QI 与本包，按其约束完成本小项。用户可将合并文件全文替换原 Worker 后部署；当前停下等待用户评审，真实接入和读图仍待完成，未提交或推送。工作区原有的 `huayan_knowledge_compiler_design_v3.html` 未改动。

### 2026-10-30｜Cloudflare 接入与首轮真实调用，待部署输入修正

- **配置**：当前基线 `feb4e7a`。新增 `config/models.vision.cloudflare.yaml`，仅读图使用 `strong` 档、现有 Worker `/v1` 地址和实际 Llama 3.2 11B 模型名；`scripts/read_report.py --vision` 默认使用该配置。SDK 的环境变量 `CLOUDFLARE_WORKER_KEY` 使用占位字符串 `unused`，未读取或发送旧供应商密钥。上游失败不自动重试，JSON 结构仍走现有 `gateway.structured` 的限定尝试。
- **协议**：先验证已部署路径，再通过现有网关发送首份报告第1页与原生上下文，模型返回未接受协议的 5016。用户将误选的“跳过”明确更正为同意后，向 `/license` 提交一次 `prompt="agree"`。上游确认接受，但旧 Worker 将该确认包装为 HTTP 502；随后已取得真实模型响应，协议已生效。原始确认保存在读取侧 `cloudflare-license-acceptance.json`，未重复提交。
- **实际兼容问题**：本机 SDK 的 HTTP 客户端在解压响应时出现 `Decompressor.decompress() got an unexpected keyword argument 'output_buffer_limit'`。`gateway/client.py` 仅增加向 SDK 透传配置可选 `default_headers`；本读图配置设置 `Accept-Encoding: identity` 后已正常取得响应。其余配置不传该字段，保持 SDK 默认行为；未扩展冻结契约或重试框架。
- **真实结果**：复用 Word COM 的原生3页图，原件指纹核对一致。第1页首轮返回英文摘要，两次结构纠错仍未生成规定 JSON，校验明确失败；第2、3页未调用，没有合格结构化读数，也没有完成真实缓存回放。3条无效模型响应保存在 `cloudflare-reading-check.json`，仅清除对应3个无效缓存文件，以便部署修正后重跑；原生30块、33条读数与7项原生待补读保持，审阅页新增当前失败说明。未把摘要补造为读数或专业判断。
- **最小输入修正**：`scripts/cloudflare_vision_worker.mjs` 将视觉请求从 `messages + image` 改为模型参数页列出的 `prompt + image`，在 prompt 中保留角色标签、schema、任务、上下文及纠错历史；仅对已实际出现的协议接受成功确认做明确返回。Clef 根路径及透传内容保留。该修正是针对真实失败的适配，效果待用户更新 Worker 后实调验证；不宣称模型已能稳定读准。
- **验证与交接**：受影响的现有读取测试2项通过（1.15秒）；Worker 语法及一次合成转发检查通过，确认 schema/任务/上下文/纠错历史进入 prompt、Clef 输入保持。未新增测试文件。编程前按要求重读 AGENTS、总计划、相关契约/QI 和本包，评审由用户进行。目前等待用户重新部署本地 Worker 文件，协议无需再接受；本小项未完成真实读图，未推进 V10.5，未提交或推送。

### 2026-10-30｜用户更新部署后的实调，结构化读图仍未完成

- **本轮范围**：用户确认已部署 `prompt + image` 版本后继续验证同一份报告，分支仍为 `v10`、基线 `feb4e7a`。编程前已重新完整阅读 AGENTS，再读总计划、相关契约/QI 与本包，并按最小改动和禁止过度防御要求自查；评审由用户进行。没有再次接受协议，没有扩展检索或推进 V10.5。
- **部署验证**：复用指纹一致的 Word COM 三页原图及原生上下文；第1页经统一网关、`caller="ingest:extract"` 取得3次真实响应，返回模型名为 `@cf/meta/llama-3.2-11b-vision-instruct`，无降级。两次为说明文字、一次为带说明的 JSON Schema，均未通过既有 `ImageReadout` 结构校验。实际响应和调用记录保存于 `data/knowledge_v10/evidence/SRC-3a2130604c/cloudflare-prompt-reading-check.json`。
- **最小修改**：`reader/image.py` 在图片输入末尾明确要求输出 JSON 数据实例，并提供不含真实业务数值的结构示例，针对已复现的“返回结构定义而非读数”问题；校验、缓存和错误处理继续沿用现有网关。该提示首次调用触及60秒本地超时，因此仅将逐页读图请求的现有 `timeout_s` 设为180，未增加重试或降级机制，Worker 无需再次部署。
- **最终真实结果**：延长等待后得到上游 HTTP 502、`3046: Request timeout`，不是模型协议未接受。两次超时分别记录在 `cloudflare-instance-reading-check.json` 和 `cloudflare-report-reading-check.json`。本轮没有合格图片读数，第2、3页未调用，真实缓存回放未完成；结构化读图验收明确未通过，未将输出补造为成功结果。
- **产物与检查**：`evidence.json`、`review.html` 已更新为本轮失败说明；原生30块、33条标签及7项原生待补读保持，图片读数为空，专业确认仍为空。已有首份原生 TrialRecord 未修改。提示修改后运行 `.venv/Scripts/uv.exe run --no-sync pytest -q tests/test_reader_v10.py`，2项通过（1.17秒）；后续等待参数由本次实际调用验证，无新增或重复测试文件。含企业内容的响应和缓存继续只留在被忽略的 `data/`。
- **交接**：本轮验证停止并交用户评审；Cloudflare 接口已取得真实响应，但完整读图和缓存回放仍待完成。首份原生报告与 TrialRecord 继续保留，后续主线按用户评审结果推进。未写正式知识状态，未提交或推送。

### 2026-10-31｜首份报告已核对表格页区域登记

- **范围与基线**：`v10 @ 001637c`，开始时工作区干净。已完整重读AGENTS、REPLAN、相关CONTRACTS/QI与本包，按G2/G6、Office原生转换、极简及禁止过度防御要求自查；应用PDF技能仅检查已有原生PDF及PNG，没有编辑PDF、使用LibreOffice或调用图片模型。本轮只补首份实际区域坐标，不宣称自动版面/OCR或专业判读完成。
- **最小入口**：新增scripts/register_report_regions.py，命令为`.venv/Scripts/uv.exe run --no-sync python scripts/register_report_regions.py --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --regions data/knowledge_v10/evidence/SRC-3a2130604c/region-locations.json`。外部登记文件携带来源/原件指纹、原生PDF指纹、各span/page/bbox及对应PNG指纹；复用EvidenceBlock/Location解析，核对页内非空区域后仅更新读取侧Location.bbox并重写原文审阅包。全部条目核对后才调用既有write_review，没有正式状态写入、Fragment字段改动、ACL、模型、重试、锁或版本系统。重新导出PDF/PNG后须重新核对登记，旧指纹不静默沿用。
- **坐标来源与实际交付**：本机未安装MinerU。本次读取既有Word COM导出的原生PDF路径边框，开发者对照完整第1、2页核对表格范围；按实际PNG尺寸换算为左上原点像素并外扩2像素保留边框。登记A组配方table-1/第1页、A组曲线table-2/第1页标题及第2页正文、B组配方与曲线table-3/第2页，共4处。region-locations.json在读取侧保留原生PDF边框与换算后坐标、原页指纹和开发者核对方法；它是定位记录，不是研发签字、MinerU输出或曲线线段专业确认。原生XML/单元格读数继续独立保留，未靠图像替换。
- **真实回取**：data/knowledge_v10/checks/report-regions-2b2576c3/summary.json及4张裁图。首份状态副本经既有GET对应门面回取4处，均kind=region，图像像素与原生PNG按登记bbox裁取完全一致，裁图逐张查看，表头、单位、曲线标签和边框完整。A组跨页标题与正文各在原页，不拼成同页；B组裁图873×549，经AgentHub已有read_source_image工具返回同一区域。未改UI，未将门面检查混报为本轮浏览器验收。
- **保真与边界检查**：原文块、单元格、A/B组别、fragments/指纹、33条原生读数及现有pending逐项不变；TrialRecord回取仍通过、A/B各5项配方。原件、原生PDF、原生DOCX、TrialRecord、原实例qi_state字节未变；隔离装载后的qi_state也未因读取改变。对实际登记文件只改一处图像指纹，CLI拒绝且evidence不被部分覆盖。含企业原文和坐标的产物仅留data，不入库；未用图中可见写法静默修正原生异常标签或关闭待补项。
- **验证与交接**：受影响读取/来源7项通过（1.52秒），全量pytest57项通过（27.55秒），不为已真实运行的CLI增加镜像测试；未改web，不重复构建。真实模型调用和新增专业签字0，隔离应用为mock网关/System1、规则抽取。MinerU自动版面/OCR、真实结构化读图与缓存回放、选定PPT图表题及最终证据整理继续待办，非研发部分尚未全部完成；真实专业判断仍按用户安排暂缓。本小项完成后停下等待评审，未提交或推送。

### 2026-10-31｜选定课件第15页原生文字、表格与位置

- **范围与基线**：`v10 @ 7c70118`，开始时工作区干净。按要求完整重读AGENTS、REPLAN、相关CONTRACTS/QI、本包和V10.0选样约定，按G2/G6、Office原生读取、极简及禁止过度防御要求自查。本轮仅处理既定来源SRC-18358d2dd7第15页，没有读取evaluations金标、扩展全题库、调用模型或进行专业签字。
- **入口与实现**：新增reader/powerpoint.py与scripts/read_pptx_slide.py；运行`.venv/Scripts/uv.exe run --locked --no-sync python scripts/read_pptx_slide.py --source SRC-18358d2dd7 --page 15`。python-pptx直接读取原件文字和表格单元格，六字段Fragment继续由既有EvidenceBlock生成；合并格只取原单元格，同时在读取侧table_layout保留行列和合并跨度，python-pptx重序列化的slide XML另存document.xml，保留原始ZIP条目的XML语义，不保证原始字节。形状位置按实际原生PNG尺寸换算为Location.bbox；不是MinerU/OCR或模型推定坐标。当前入口针对文字/表格页，其他形状保留待补，不宣称全格式或原生chart系列解析完成。
- **原生导出与审阅**：核对V10.0清单中的PPTX原件、字节相同的COM输入副本和原生PDF指纹，复用已批准的PowerPoint COM原生25页PNG/PDF，没有重新转换或使用LibreOffice。读取产物在data/knowledge_v10/evidence/SRC-18358d2dd7/：evidence.json、review.html、document.xml、table-region.png及native副本。为保持既有页码回取接口的索引，保留25张原生页图副本；仅第15页形成证据块，selected_pages使审阅页只展示这一页。report.py只补该选择并将Word专用页图说明改为通用“原生页”，原Word报告仍默认显示全部页面。
- **真实结果**：第15页为4个文字块和1张6行8列表格，24个数值正文单元格、6处合并关系均与原件逐项一致。标题、列头、用量/单位及测试方法文字保留原样，未将其编成适用范围或把S自动换算为其他单位。本页native_chart_count=0，属于原生表格而不是chart系列；未虚构系列值。readings为空表示尚未另行展开带完整多层表头的Reading记录，不代表表格没有数值或模型结构化读取已通过。
- **隔离核对与归属**：data/knowledge_v10/checks/ppt-slide-363ac910/summary.json。slide XML与原始ZIP条目语义一致，单元格/文字逐项一致，第15页PNG逐字节一致；EvidenceReportSource的fetch/search能回取当前片段。来源清单owner仍为None，正常统一入口按原规则拒绝；仅在隔离应用内存临时指定已存在研发账号核对回取软件，表格裁图kind=region、密级L3，裁图已查看且表头、行列和数值完整。没有把该课件登记为真实研发所有或挂入正式实例，没有导入候选/能力；原课件、清单、原配置及qi_state字节未变，隔离装载后的qi_state也未因读取改变。
- **依赖与检查**：声明本次实际使用的python-pptx>=1.0.2。uv lock --offline因跨Python版本缓存缺httpx元数据失败，随后正常uv lock完成，uv lock --check通过；同步锁文件也补入此前已在清单声明而未入锁的Word/PDF及可选reader-embedding依赖。未新增嵌入功能、下载模型或执行GPU安装，实际原生读取使用本机已有python-pptx 1.0.2。受影响读取/来源7项通过（1.80秒）；全量pytest57项通过（28.70秒），差异格式检查通过。按一次真实原生读取核对交付，没有新增镜像测试；未改web，不重复构建。
- **交接**：本小项只交付选定页的原生证据与回取，不报告题库通过率。模型、Jev、嵌入或OCR实调0，隔离应用为mock网关/System1、规则抽取。下一小项可由eval侧消费这些证据核验已核验题子集；MinerU自动版面/OCR、真实图片模型读数和最终证据整理仍待完成，专业归属、判断及真人试用按用户后续安排。非研发部分尚未全部完成；未提交或推送，停下等待用户评审。


### 2026-10-31｜P3更正：slide XML验收口径

- `v10 @ 643208e`，按用户评审仅更正记录。已按AGENTS重读相关规则与工作包：document.xml保存的是python-pptx重序列化的slide.part.blob，不能称为原始ZIP条目的逐字节副本。上条入口说明与核对结论已改为“XML语义一致”，原生PNG的逐字节一致结论保留。
- 从实际PPTX ZIP条目取回第15页XML，与document.xml解析后比较，语义一致、原始字节不一致；本地ppt-slide-363ac910/summary.json同步明确这两个结果及输出来源。未修改主体代码、XML输出、表格或正式状态；仅做这次定点核对与差异格式检查，不新增测试或重跑无关测试。停下等待用户评审，未推进下一小项。

### 2026-10-31｜首份报告本地MinerU版面与OCR辅助稿

- **范围与基线**：`v10 @ 072f741`，开始时工作区干净。已完整重读AGENTS、REPLAN、相关CONTRACTS/QI和本包，按G2/G5/G6、原生Office规则、极简与禁止过度防御要求自查。本小项完成首份报告的本地版面/OCR运行，不恢复用户暂停的生成模型实调，不进行研发签字。
- **入口与依赖**：新增`scripts/read_report_layout.py`及同名`.md`。从既有evidence.json定位Word COM导出的PDF，调用独立工具环境中的MinerU 4.1.3，固定Basic、OCR、ONNX CPU及local模型来源；输出日志、原始middle.json、带来源/输入指纹和像素坐标的layout.json、原生PNG副本及红框审阅页。只在外部CLI/协议边界检查PDF头、输出协议与坐标；不新增框架、契约、ACL、自动挂接或正式写入。工具和公开模型下载在被忽略的data/tools，ModelScope缓存也定向到该目录，遥测关闭，项目pyproject.toml、uv.lock及运行环境不变。
- **真实运行与模型**：`.venv/Scripts/uv.exe run --locked --no-sync python scripts/read_report_layout.py --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --out data/knowledge_v10/evidence/SRC-3a2130604c/layout-mineru`。同一份3页原生PDF实际完成，工具耗时11.54秒（含启动，日志推理7.44秒）；返回36块，逐页20/6/10，含2表、1图像，全部有归一化及原生PNG像素坐标。日志实际加载OCR检测/识别、版面及UNet模型，均为CPUExecutionProvider；没有VLM、外部生成模型、Jev或嵌入调用。没有将本地OCR当成专业真值。
- **结果与局限**：`layout-mineru/review.html`将原生页图、自动区域与原始OCR结构并排展示，HTML表格内容转义显示。实际查看第2页区域覆盖了A组曲线及B组表格，但A曲线仅作为image，B曲线标签未完整读取，OCR中132匹配数为0；不能以区域已找到代替读数已读出。辅助块全部needs_review、group=null，不从前后次序自动赋予A/B，不覆盖既有人工核对区域、原生Fragment、单位或未决条件。完整曲线及图片模型结构化读数仍待补。
- **保真与验证**：`data/knowledge_v10/checks/mineru-first-report/summary.json`记录输入字节核对、逐页/类型计数与局限，附第2页区域核对图。evidence.json、原生DOC/PDF/DOCX、TrialRecord、原实例qi_state及依赖清单/锁文件字节均未变；原生仍30块、33条标签，现有pending保留。全量pytest57项通过（28.34秒）；按真实运行核对，不新增镜像测试。未改web，不重复构建；含企业原文的产物和工具缓存不入库。
- **交接**：本地版面/OCR辅助入口可复现，尚未自动挂接为原生证据。真实模型读图与缓存回放、线上Agent模型走链、最终证据整理仍有未完成部分，非研发事项尚未全部完成；专业判断及四类真人试用继续按用户后续安排。本小项停下等待评审，未提交或推送。


### 2026-10-31｜停止扩题，改用智谱在线读取与原生曲线审阅

- **范围与自查**：按用户新指令停止35题扩写和规则刷题，重读AGENTS、VISION、REPLAN、CONTRACTS/QI；遵守铁律2/3/4/10/11，冻结Fragment及其他领域契约不变。根目录资料目录已从索引移除且本地保留，.env/data/runs继续忽略，未读取或打印密钥；运行均经`uv run --env-file .env`。Cloudflare只保留Clef，本轮不修改或部署Worker。
- **网关**：默认config/models.yaml改为智谱glm-4.6v-flash，备用glm-4.1v-thinking-flash，同一BACKUP_API_KEY引用。真实image_url+json_object请求已取得两模型响应；实调发现推理前缀（含省略起始标签）、短预算截断及Schema回传，前缀只在OpenAICompatGateway边界处理，结构不合格沿既有structured纠错并保留失败记录，不截取任意JSON或补造数据。单并发仅在网关统一约束，重试沿既有retry_waits=[5,15,30]，429优先使用Retry-After秒数；SDK不另做重试。
- **原生图与审阅**：report.py仅按已登记bbox裁切Office原生PNG，不解析或重绘VML/DrawingML形状。read_report默认智谱，复用指纹一致的Word COM原生3页和登记区域，顺序读取3张整页及3个曲线区域；report/trial_review/trial_ir内联原生裁图及实际模型名、待人工审阅辅助稿。首份报告无原生chart series，原生文字/单元格及33条标签保持；model quote=null允许留空，缺值/单位/标签列入pending。
- **真实运行与缓存**：`uv run --env-file .env python scripts/read_report.py --source SRC-3a2130604c --vision`成功，紧接着同参数第二遍10条响应全命中已有网关缓存（含结构纠错响应），新增网络请求0，记录`data/knowledge_v10/checks/glm-online/first-report-replay.json`。cache位于data/knowledge_v10/cache/，键包含图片完整内容和请求/Schema/模型参数；meter不等于网络次数，实际请求以gateway-trace.jsonl的llm_request计。
- **A/B核对结果与限制**：原生图保留两组各自的升降温走线、保温点、原单位、终点操作和红字时间口径，具体值与核对说明仅保存在被忽略的native-curve-check.json。模型尚不能视作准确的完整工艺：table-2第1页标题区域输出了区域不可见的数值，部分阶段/单位拆分不全；原始模型稿保留并在三类审阅页明确待审，没有并入正式判断或覆盖原生读数。
- **PPT真实读取**：`uv run --env-file .env python scripts/read_pptx_slide.py --source SRC-18358d2dd7 --page 15 --vision`由PowerPoint16.0 COM后台SaveAs原生PNG/PDF，python-pptx同步读取原生表格；该页原生chart数0，不将表格冒称系列图。5次网络尝试（主模型4次429后备用成功），glm-4.1v-thinking-flash返回24条数值辅助稿，24条缺单位待补；原生24个数值单元格继续可回查，不将模型稿当真值。
- **产物与交接**：evidence/SRC-3a2130604c/review.html、trials/SRC-3a2130604c/review.html、professional-review/glm-first-report/review.html及evidence/SRC-18358d2dd7/review.html均在data/knowledge_v10下。专业审阅包是新读取侧副本，原正式IR/知识状态不由本轮读取改写。在线读取通道已通，读数专业审阅仍未完成；真实签字、授予与范围批准继续等待人，不以模型输出替代。

### 2026-11-01｜P2修正：内联辅助稿补齐降级标识

- 按用户评审重读AGENTS全文、总计划、相关CONTRACTS/QI及本包，并按铁律4.9、极简与禁止过度防御要求自查。仅在report.py::render_block_images沿用整页辅助稿的既有格式：fallback_used为true时在实际模型名后追加“（降级）”，保留区域／整页范围及“待人工审阅”。未改契约、读数、签字逻辑或网关调用。
- 离线使用首份报告table-2第2页已有备用响应核对标识，并用同一响应副本验证fallback_used=false时不标降级；刷新首份原文、试样、专业审阅副本及选定PPT页的既有HTML标签，不重读模型、不重渲染Office、不改读取JSON或正式状态。已有三个前端文件改动原样保留。
- 验证：`uv run --env-file .env --locked --no-sync pytest -q`全量57项通过（33.19秒），`git diff --check`通过；未新增测试文件或线上模型请求。本修复未修改前端，不重复构建。
- 本小项只修正降级披露，不据此认定专业确认、用途授予、完整在线派单或四岗位真人试用完成；停止在本修复项交用户评审。

### 2026-11-01｜SiliconFlow Qwen3视觉实调与缓存回放

- **自查与配置**：已按AGENTS及本包自查，契约冻结、统一网关与caller、觉零大模型、极简及禁止过度防御要求保持。按用户最新指定，config/models.yaml的fast/strong改为https://api.siliconflow.cn/v1、Qwen/Qwen3-VL-8B-Instruct、BACKUP_API_KEY；concurrency=1，沿用网关retry_waits及429退避，不设失效的GLM备用。Cloudflare仍仅Clef，不需用户重新部署Worker。没有读取或打印.env密钥。
- **图片与超时**：reader/image.py在Base64编码前用Pillow等比例缩小长边超过1536px的图片；小图字节不变，磁盘原图不改。单次请求timeout_s=60，复用data/knowledge_v10/cache/image-readings中的现有请求哈希缓存。Pillow由可选依赖移入实际读取必需依赖；锁文件未改变既有包版本。
- **真实超时后的最小调整**：整页长输出复现60秒超时，report.py改为先补读已登记的原生曲线区域；这些页的文字、表格继续保留完整原生解析，其余选定页再读整页。不向曲线提示重复塞整份报告，不另造裁图坐标、重试器、锁或缓存。区域原图仍由已登记Location.bbox裁自Office原生PNG。
- **首份实调**：先对B组原生裁图完成1次真实请求及1次缓存回放；随后首份报告当前请求得到4份合格结构辅助稿（A跨页区域2份、B区域1份、第3页1份），实际模型均Qwen/Qwen3-VL-8B-Instruct，无降级，caller=ingest:extract。4份响应分别约2.22/16.16/50.27/10.01秒，共23条辅助reading，另有原生33条标签。首份来源trace中本次累计9次Qwen3网络尝试，包含前期整页失败与中止，不能只以成功4份报告总调用次数。
- **回放与保真**：紧接着以相同命令重跑，4份全部缓存命中，新增网络请求0；原生30块、Fragment、33条原生读数和3张完整PNG不变，3份业务qi_state指纹不变。刷新原文、canonical TrialRecord及专家反馈副本的试样/IR审阅HTML；TrialRecord与IR结构内容语义不变，没有把模型读数写成正式结论或签字。核对及计量见data/knowledge_v10/checks/siliconflow-vision-20261101/qwen3-vl-8b/report-summary.json、来源目录gateway-trace.jsonl与metering.jsonl。
- **A/B核对局限**：模型保留两组各自高温保温及红字升温时间口径；开发者对照原图发现A漏一个保温点，B漏加料时间、重复速率标签且有速率位置错配，部分value混入单位或定性词。问题已列原文审阅pending，原图及原生标签优先供人核对；不以辅助稿冒充准确完整工艺，不将B数据补给A，不扩大产品适用范围。具体原文只留data，不入库。
- **选定PPT实调**：继续以同一入口读取SRC-18358d2dd7的既定第15页，复用PowerPoint COM原生PNG/PDF及python-pptx原生表格。首次请求60秒超时，既有网关退避后第二次约52.47秒成功，无降级；42条辅助reading中24条小数数值集合与24个原生数值单元格一致，但unit全部为空，42条待补读保留，集合一致不代表行列条件关联已正确。紧接着同参数回放1份响应命中缓存、新增网络请求0，记录同目录ppt-summary.json。没有扩展选题或宣称题目正确率。
- **命令与检查**：`uv run --env-file .env --locked --no-sync python scripts/read_report.py --source SRC-3a2130604c --vision`执行两遍；读取离线测试扩展已有图片通路，覆盖3072×768缩至1536×384、小图字节不变、timeout=60与缓存；全量`uv run --locked --no-sync pytest -q`为58项通过（34.02秒）。本轮未改web或冻结契约，未提交data/runs/.env，未新增专业签字。业务Agent在线模型配置没有随视觉配置静默切换，V10.9在线准备未据此宣布完成。
