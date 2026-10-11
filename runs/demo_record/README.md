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

界面接口：

- `GET /api/demo/next?session=sess:1` 返回 `{text: string | null}`。按客户与业务员匹配台词会话，同一组合按开会话顺序对应；按已发送的客户轮数取下一句，允许改写后发出。反复点击不消耗台词，台词结束或无对应会话返回 `null`。
- `GET /api/demo/checkpoints` 返回检查点名称数组；仅以 `app.demo.yaml` 配置启动时返回列表，其余配置返回 `[]`，供 U 隐藏入口。
- `POST /api/demo/load {name}` 用新门面从起点严格回放至指定检查点，成功后替换工作面，网关和 OneJev 一起切回现场，缓存继续有效。只推进台词内业务操作的时间、派单，不增加外层一分钟或 tick。失败保留原门面及业务时钟；缓存缺失返回 HTTP 409，错误包含 caller。

启动演示服务（PowerShell）：

```powershell
$env:HUAYAN_CONFIG = "config/app.demo.yaml"
uv run python -m huayan.ui.server
```

2026-10-11 正式录制 `run-5cc33544feaa` 已跑完主线与 D17 支线；11 次签字的前置断言全部通过，新客户命中 HY-LV206。大模型 82 次、OneJev 3 次，均成功，录制无缓存命中。服务响应模型名为 `gemini-3.8-flash-n`，请求名为 `gemini-3.8-flash-high`；单价未配置，费用未知。

回放 `run-d749989c1ef5` 在禁止 socket.connect 的进程内完整通过，事件序列与录制一致（忽略事件 id）。四个正式检查点均已通过断网载入验证，并确认网关、OneJev 一起切回现场。签字时刻、计数、对话与草稿见 [transcript_v5.md](transcript_v5.md)，本机验收摘要见 `runs/wp_i2_live_review/summary.json`。

尚未完成：四个检查点在界面上连续操作、临场改话后的真实调用验证及录屏。本次浏览器检查仅确认工作台首页真实渲染，不代表整段界面验收。临时 SSH 转发已随录制进程关闭，现场演示前需重新建立连接。
