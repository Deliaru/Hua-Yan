# WP-2v10｜选定资料的解析与证据读取

> 决赛必需，按样例交付｜状态：首份Word原生读取及4处表格页区域已登记，选定课件第15页原生文字/表格与区域回取已验证；MinerU自动版面/OCR、合格图片模型读数及读取题核验仍待完成｜先处理实际选定材料。

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
- **入口与实现**：新增reader/powerpoint.py与scripts/read_pptx_slide.py；运行`.venv/Scripts/uv.exe run --locked --no-sync python scripts/read_pptx_slide.py --source SRC-18358d2dd7 --page 15`。python-pptx直接读取原件文字和表格单元格，六字段Fragment继续由既有EvidenceBlock生成；合并格只取原单元格，同时在读取侧table_layout保留行列和合并跨度，原始slide XML另存document.xml。形状位置按实际原生PNG尺寸换算为Location.bbox；不是MinerU/OCR或模型推定坐标。当前入口针对文字/表格页，其他形状保留待补，不宣称全格式或原生chart系列解析完成。
- **原生导出与审阅**：核对V10.0清单中的PPTX原件、字节相同的COM输入副本和原生PDF指纹，复用已批准的PowerPoint COM原生25页PNG/PDF，没有重新转换或使用LibreOffice。读取产物在data/knowledge_v10/evidence/SRC-18358d2dd7/：evidence.json、review.html、document.xml、table-region.png及native副本。为保持既有页码回取接口的索引，保留25张原生页图副本；仅第15页形成证据块，selected_pages使审阅页只展示这一页。report.py只补该选择并将Word专用页图说明改为通用“原生页”，原Word报告仍默认显示全部页面。
- **真实结果**：第15页为4个文字块和1张6行8列表格，24个数值正文单元格、6处合并关系均与原件逐项一致。标题、列头、用量/单位及测试方法文字保留原样，未将其编成适用范围或把S自动换算为其他单位。本页native_chart_count=0，属于原生表格而不是chart系列；未虚构系列值。readings为空表示尚未另行展开带完整多层表头的Reading记录，不代表表格没有数值或模型结构化读取已通过。
- **隔离核对与归属**：data/knowledge_v10/checks/ppt-slide-363ac910/summary.json。原始slide XML、单元格/文字及第15页PNG逐项/逐字节一致；EvidenceReportSource的fetch/search能回取当前片段。来源清单owner仍为None，正常统一入口按原规则拒绝；仅在隔离应用内存临时指定已存在研发账号核对回取软件，表格裁图kind=region、密级L3，裁图已查看且表头、行列和数值完整。没有把该课件登记为真实研发所有或挂入正式实例，没有导入候选/能力；原课件、清单、原配置及qi_state字节未变，隔离装载后的qi_state也未因读取改变。
- **依赖与检查**：声明本次实际使用的python-pptx>=1.0.2。uv lock --offline因跨Python版本缓存缺httpx元数据失败，随后正常uv lock完成，uv lock --check通过；同步锁文件也补入此前已在清单声明而未入锁的Word/PDF及可选reader-embedding依赖。未新增嵌入功能、下载模型或执行GPU安装，实际原生读取使用本机已有python-pptx 1.0.2。受影响读取/来源7项通过（1.80秒）；全量pytest57项通过（28.70秒），差异格式检查通过。按一次真实原生读取核对交付，没有新增镜像测试；未改web，不重复构建。
- **交接**：本小项只交付选定页的原生证据与回取，不报告题库通过率。模型、Jev、嵌入或OCR实调0，隔离应用为mock网关/System1、规则抽取。下一小项可由eval侧消费这些证据核验已核验题子集；MinerU自动版面/OCR、真实图片模型读数和最终证据整理仍待完成，专业归属、判断及真人试用按用户后续安排。非研发部分尚未全部完成；未提交或推送，停下等待用户评审。
