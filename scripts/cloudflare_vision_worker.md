# Cloudflare Jev 与读图共用 Worker

代码：[`cloudflare_vision_worker.mjs`](cloudflare_vision_worker.mjs)。**用文件全文整体替换现有 Jev Worker 的代码**，保留 `export default`、现有域名及名为 `AI` 的绑定，然后部署。无需新建 Worker，也无需添加第二个 AI 绑定。一个绑定通过 `env.AI.run` 的第一个参数选择调用哪个模型，见[官方绑定说明](https://developers.cloudflare.com/workers-ai/configuration/bindings/)。

| 路径 | 功能 | 实际调用 |
|---|---|---|
| `POST /` | 原 Jev 证据核对 | `@cf/cloudflare/clef` |
| `POST /v1/chat/completions` | 新增逐页读图 | `@cf/meta/llama-3.2-11b-vision-instruct` |
| `POST /license` | 用户首次接受视觉模型协议 | 同一视觉模型的 `prompt="agree"` 请求 |

根路径继续接收 `state`、`questions` 和可选的 `images`，Clef 返回值原样透传；本地 `ClefWorkerClient` 无需修改。原 CORS/OPTIONS 行为保留，允许请求头补充 `Authorization` 以兼容网关客户端。

读图使用 `env.AI.run`，无需其他模型供应商的 API Key。图片以 data URL 交给 AI 绑定；当前适配将文字消息、schema 和纠错历史汇成 `prompt`，使用[模型参数页](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/)列出的 `prompt + image` 输入。早期版本使用教程中的 `messages + image`；用户已于 2026-10-30 更新部署为本版。两版实调均未取得合格结构化读数，最新结果见下方验证记录。

## 首次启用模型

Cloudflare 要求先接受 Meta 的 License 和 Acceptable Use Policy；条款入口见[模型页面](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/)。如果尚未接受，请先阅读条款，再由你在部署合并代码后主动执行下面的 PowerShell 命令，地址沿用现有 Worker：

```powershell
Invoke-RestMethod -Method Post -Uri 'https://jev-proxy.xi1092183542.workers.dev/license' -ContentType 'application/json' -Body '{"prompt":"agree"}'
```

该接口只转交这次明确的接受请求；普通读图请求不会替你接受协议。查看返回结果确认是否成功；账号已接受则不用重复执行。

本账号已在 2026-10-30 经用户明确授权提交一次接受请求，后续已取得真实模型输出。Cloudflare 将 “Thank you for agreeing … You may now use the model” 确认文本放在异常中，旧版 Worker 因而返回 HTTP 502；原始返回已保存到本地运行记录。本版仅将这条明确的成功确认返回为 `status="accepted"`，无需重新接受协议。

## 接口与后续接入

- `POST /v1/chat/completions`：接收项目现有网关使用的 `model`、`messages`、`max_tokens`、`temperature`、`response_format`。
- `model` 必须为上述完整模型名；一次请求一张 PNG/JPEG 的 base64 data URL，放在 `messages[].content` 的 `image_url.url` 中，符合现有 `reader/image.py` 的逐页调用。
- 保留文字消息及角色标签、系统提示，把图片单独交给 Workers AI；按 OpenAI 响应结构返回实际调用的模型名与原始生成文本。此适配器仅支持非流式读图，不承接工具调用。
- `response_format={"type":"json_object"}` 转为 JSON 提示要求，**不宣称该模型强制遵守 JSON/schema**。模型输出原样返回，由现有 `gateway.structured` 解析和校验，失败沿用现有流程；Worker 不做正则截取、补造字段或二次重试。
- 上游未提供 token 用量和停止原因时，返回体省略 `usage`、`finish_reason` 留空。本地现有网关会把缺失的用量记为 0；这是“未取得用量”，不能解释为真实零消耗或免费额度统计。额度看 Cloudflare 控制台。

部署后的本地连接参数为：

```text
base_url = https://jev-proxy.xi1092183542.workers.dev/v1
model    = @cf/meta/llama-3.2-11b-vision-instruct
```

本版 Worker 无密钥校验，OpenAI SDK 所需的非空 `api_key` 可使用占位字符串 `unused`，不需要传旧的外部供应商密钥。正式接入仍通过 `OpenAICompatGateway`，沿用 `caller="ingest:extract"`、结构校验、计量与本地图片指纹缓存。

项目读图脚本现默认使用 `config/models.vision.cloudflare.yaml`，仅配置读图需要的 `strong` 档。运行方式：

```powershell
$env:CLOUDFLARE_WORKER_KEY = 'unused'
uv run python scripts/read_report.py --source SRC-3a2130604c --vision
```

若把该占位变量存入项目根目录 `.env`，改用 `uv run --env-file .env python ...`。已有通用助手配置 `config/models.yaml` 和 Jev 客户端各自保持原用途。当前本机 HTTP 客户端处理 zstd 响应时出现解压参数不兼容，读图配置通过 SDK 的 `default_headers` 传入 `Accept-Encoding: identity`；这是传输兼容设置，不改变图片或模型输出。

读取结果及实际调用记录在 `data/knowledge_v10/evidence/SRC-3a2130604c/`，缓存沿用 `data/knowledge_v10/cache/image-readings/`；模型结果保留为待人工审阅的辅助读稿。

## 额度与验证

Workers AI 每日共有 **10,000 Neurons 免费额度**，按账号累计，UTC 00:00 重置；超过额度的行为取决于 Free/Paid 计划。并非不限量免费。详见[官方定价](https://developers.cloudflare.com/workers-ai/platform/pricing/)。

本地检查入口：`node --check scripts/cloudflare_vision_worker.mjs`，已通过。另用合成请求在本地执行一次两路转发检查：根路径的 Clef 输入（含可选 images）和返回保持一致，读图路径调用视觉模型并保留图片及生成文本；结果通过，未新增测试文件。这是离线路由检查，不作为真实识别成绩。

2026-10-30 更新部署后的真实验证：

- 复用首份报告 `SRC-3a2130604c` 的 Word COM 原生页图，通过现有网关调用第1页。三次响应仍为说明文字或 JSON Schema，现有 `ImageReadout` 校验拒绝；原始响应记录在读取产物目录的 `cloudflare-prompt-reading-check.json`。
- `reader/image.py` 在图片输入末尾补充 JSON 数据实例说明，区分“填写读数”与“返回结构定义”。首次调用触及本地60秒超时；将逐页读图请求的 `timeout_s` 设为180后，上游明确返回 HTTP 502、`3046: Request timeout`。未增加自动重试，也未再次修改 Worker 或接受协议。
- 当前合格图片读数为0页，第2、3页未调用，真实缓存回放未完成。原生解析和 TrialRecord 保留，模型结果不进入正式知识状态。提示修改后的现有读取测试2项通过（1.17秒），不代表真实模型读图通过。
- 两次超时分别保存于 `cloudflare-instance-reading-check.json`、`cloudflare-report-reading-check.json`；`review.html` 标明图片模型读取未完成。后续读取仍待验证，本轮停止调用并交用户评审。
