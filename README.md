# 化言 HuaYan

> 让需求在传递中不走样。

面向传化功能化学「市场—产品—研发」需求协同的多层 Agent 系统。参赛赛道：AI＋功能化学（自主深化「AI 化学家」推荐场景）。

**当前状态：v5 主线已录制（WP-I2），断网回放与四个检查点载入已核对；演示脚本与材料由 WP-D2 整理。**

## 运行

在仓库根目录执行，需 Python 3.11+、uv 与 Node.js：

```bash
uv sync
npm --prefix web ci
npm --prefix web run build
uv run pytest
uv run python -m huayan.ui.server
```

默认使用离线配置，界面地址为 `http://127.0.0.1:8766`。现场演示需在本机环境配置 `BACKUP_API_KEY`，按 `config/system1.yaml` 建立 OneJev 本地转发（以 `app.demo.yaml` 启动时会先检查 OneJev，未启动则服务起不来），并将 B 提供的模型放到 `models/jue_k/model.pkl`（不入库）。PowerShell 启动：

```powershell
$env:HUAYAN_CONFIG = "config/app.demo.yaml"
uv run python -m huayan.ui.server
```

正式台词与界面共用业务入口；录制后才能严格回放或载入正式检查点：

```bash
uv run python scripts/demo_mainline.py --record
uv run python scripts/demo_mainline.py --replay
```

`--replay` 只读 `runs/demo_record/llm_cache_v5/`，不需要密钥与 OneJev，也不访问网络；缓存缺失直接报错，不转为现场调用。检查点、环境要求与验收范围见 [录制说明](runs/demo_record/README.md)。

## 文档

| 文件 | 内容 |
|---|---|
| [AGENTS.md](AGENTS.md) | 开发约束，给 coding agent 读 |
| [docs/VISION.md](docs/VISION.md) | 愿景、痛点、定位、边界 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构与运行链路 |
| [docs/JUE_K_TRAINING.md](docs/JUE_K_TRAINING.md) | 觉（Jue-K）训练方案 |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | 数据格式与模块接口（冻结） |
| [docs/workpackages/](docs/workpackages/README.md) | 8 小时首版 Demo 的双人并行工作包 |
| [docs/reference/](docs/reference/) | 赛事要求摘要 |

## 声明

- 本项目使用的全部数据为模拟数据，不包含传化真实资料。
- 部分基础模块复用或改写自团队赛前项目 JUE，文件头注明来源：
  - 复用（按契约与录制回放做了少量调整）：`src/huayan/clock.py`、`meter.py`、`contracts/_base.py`、`contracts/gateway.py`、`gateway/__init__.py`、`gateway/client.py`、`gateway/mock.py`、`jev/system1/onejev.py`、`jue/expr.py`；
  - 改写或参照：`agent/loop.py`（JUE 的 Agent Loop 简化）、`agent/tools.py`（工具注册表写法）、`ui/server.py`（JUE 决策台的服务形式）、`scripts/train_jue_k.py` 与 `scripts/eval_jue_k.py`（JUE-r2 的训练与校准做法）、`scripts/probe_onejev.py`；界面视觉沿用 JUE 决策台。
