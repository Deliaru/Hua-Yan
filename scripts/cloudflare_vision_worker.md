# Cloudflare Jev 与读图共用 Worker

代码：[`cloudflare_vision_worker.mjs`](cloudflare_vision_worker.mjs)。**用文件全文整体替换现有 Jev Worker 的代码**，保留 `export default`、现有域名及名为 `AI` 的绑定，然后部署。无需新建 Worker，也无需添加第二个 AI 绑定。一个绑定通过 `env.AI.run` 的第一个参数选择调用哪个模型，见[官方绑定说明](https://developers.cloudflare.com/workers-ai/configuration/bindings/)。

| 路径 | 功能 | 实际调用 |
|---|---|---|
| `POST /` | 原 Jev 证据核对 | `@cf/cloudflare/clef` |
| `POST /v1/chat/completions` | 新增逐页读图 | `@cf/meta/llama-3.2-11b-vision-instruct` |
| `POST /license` | 用户首次接受视觉模型协议 | 同一视觉模型的 `prompt="agree"` 请求 |

根路径继续接收 `state`、`questions` 和可选的 `images`，Clef 返回值原样透传；本地 `ClefWorkerClient` 无需修改。原 CORS/OPTIONS 行为保留，允许请求头补充 `Authorization` 以兼容网关客户端。

读图使用 `env.AI.run`，无需其他模型供应商的 API Key。图片以 data URL 交给 AI 绑定，依据 [Cloudflare 官方视觉模型示例](https://developers.cloudflare.com/workers-ai/guides/tutorials/llama-vision-tutorial/)。

## 首次启用模型

Cloudflare 要求先接受 Meta 的 License 和 Acceptable Use Policy；条款入口见[模型页面](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/)。如果尚未接受，请先阅读条款，再由你在部署合并代码后主动执行下面的 PowerShell 命令，地址沿用现有 Worker：

```powershell
Invoke-RestMethod -Method Post -Uri 'https://jev-proxy.xi1092183542.workers.dev/license' -ContentType 'application/json' -Body '{"prompt":"agree"}'
```

该接口只转交这次明确的接受请求；普通读图请求不会替你接受协议。查看返回结果确认是否成功；账号已接受则不用重复执行。

## 接口与后续接入

- `POST /v1/chat/completions`：接收项目现有网关使用的 `model`、`messages`、`max_tokens`、`temperature`、`response_format`。
- `model` 必须为上述完整模型名；一次请求一张 PNG/JPEG 的 base64 data URL，放在 `messages[].content` 的 `image_url.url` 中，符合现有 `reader/image.py` 的逐页调用。
- 保留文字消息与系统提示，把图片单独交给 Workers AI；按 OpenAI 响应结构返回实际调用的模型名与原始生成文本。此适配器仅支持非流式读图，不承接工具调用。
- `response_format={"type":"json_object"}` 转为 JSON 提示要求，**不宣称该模型强制遵守 JSON/schema**。模型输出原样返回，由现有 `gateway.structured` 解析和校验，失败沿用现有流程；Worker 不做正则截取、补造字段或二次重试。
- 上游未提供 token 用量和停止原因时，返回体省略 `usage`、`finish_reason` 留空。本地现有网关会把缺失的用量记为 0；这是“未取得用量”，不能解释为真实零消耗或免费额度统计。额度看 Cloudflare 控制台。

部署后的本地连接参数为：

```text
base_url = https://jev-proxy.xi1092183542.workers.dev/v1
model    = @cf/meta/llama-3.2-11b-vision-instruct
```

本版 Worker 无密钥校验，OpenAI SDK 所需的非空 `api_key` 可使用占位字符串 `unused`，不需要传旧的外部供应商密钥。正式接入仍通过 `OpenAICompatGateway`，沿用 `caller="ingest:extract"`、结构校验、计量与本地图片指纹缓存。

当前只交付合并代码供用户更新原 Worker；项目 `config/models.yaml` 尚未切换，未调用 Cloudflare 模型，也未上传企业报告。用户部署并确认后，再接入首份报告读图。

## 额度与验证

Workers AI 每日共有 **10,000 Neurons 免费额度**，按账号累计，UTC 00:00 重置；超过额度的行为取决于 Free/Paid 计划。并非不限量免费。详见[官方定价](https://developers.cloudflare.com/workers-ai/platform/pricing/)。

本地检查入口：`node --check scripts/cloudflare_vision_worker.mjs`，已通过。另用合成请求在本地执行一次两路转发检查：根路径的 Clef 输入（含可选 images）和返回保持一致，读图路径调用视觉模型并保留图片及生成文本；结果通过，未新增测试文件。这是离线路由检查，未发出网络请求；Cloudflare 绑定、协议接受、真实图片识别与 JSON 输出质量仍需部署后验证。
