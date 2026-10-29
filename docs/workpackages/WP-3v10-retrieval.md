# WP-3v10｜一道图表题的检索与查证

> 可演示即可｜状态：用户提供的底层组件已核对并接通，停止扩展，回到 V10.4 → V10.5 → V10.7 → V10.6 主线｜完整展示验收未完成。

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
