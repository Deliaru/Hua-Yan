# v5 演示录制

v5 使用 `config/app.demo.yaml`，网关缓存写入 `llm_cache_v5/`，OneJev 请求与响应写入其 `s1/` 子目录。

旧 `llm_cache/` 与旧版对话仅保留作对照，不用于 v5 验收；调用时机与请求内容已经改变。

`replay: true` 时两种客户端只读缓存，未命中抛出带 caller 的 `ReplayMiss`；OneJev 初始化跳过健康检查。缓存命中在终端打印来源与 caller。Jue-K 在本地推理，不经过缓存。

费用与调用次数只汇总录制运行的计量文件；网关沿用原有计量语义，回放记录不能作为新增费用统计。试样与每次业务写操作推进一分钟均为演示时间压缩。

运行器命令：

```bash
uv run python scripts/demo_mainline.py --record
uv run python scripts/demo_mainline.py --replay
uv run python scripts/demo_mainline.py --record --until 研发待接单
uv run python scripts/demo_mainline.py --replay --until 研发待接单
```

每条动作经 `Api.call`；签字前检查问题为 open、已准备且签字人匹配。沉淀、封存 / 放出使用当前草稿，草稿为空即停止。`transcript_v5.md` 与 `signatures.json` 写入该次运行目录，失败也保留诊断。成功录制后才更新本目录的 `record_v5.json`（台词摘要、停止点与事件基线）；回放须使用同一台词与停止点，逐条比较事件，仅忽略事件 id。

本目录目前尚无 v5 完整主线录制。运行器的离线核对使用独立台词与规则骨架，不算正式台词的真实 Agent 验收；检查点 HTTP 载入和真实录制/回放对照在后续步骤交付。
