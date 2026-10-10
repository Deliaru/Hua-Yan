# WP-D 演示与提交材料

> 负责：A＋B｜时段：7:15–8:00｜在 `main` 上进行

## 目标
让首版 Demo 能稳定地演示、能被评委复现；材料与实现一致。

## 依赖
WP-U、WP-E。

## 必读
`docs/reference/competition.md`（提交要求与评审标准）；`docs/VISION.md` 第 6、7 节（不能说的话）。

## 允许修改的范围
`README.md`、`docs/DEMO.md`、`config/app.replay.yaml`、`runs/demo_record/`、`docs/assets/`

## 交付物与已定设计

### 1. 记录回放（A）
- 用现场配置（大模型抽取、Jev 降级或 OneJev）跑一遍演示主线，`llm_cache_dir` 写入 `runs/demo_record/llm_cache/`。
- `config/app.replay.yaml`：`replay: true`，缓存指向上面的目录。现场网络或接口出问题时切换到它，界面顶部显示「记录回放」。
- 未授权大模型费用时：录制离线模式，并在 README 中写明。

### 2. 演示脚本 `docs/DEMO.md`（B）
3 分钟版：每一步点什么、说什么、屏幕上应该看到什么；对应首版 Demo 验收 5 条；附 30 秒版本（只演示追问 → 推荐 → L1/L3 对比）。

### 3. README 重写（A 起草，B 补评测部分）
按赛事要求：团队信息、业务场景与痛点（注明来自一线业务需求交流）、核心方案（三根支柱、觉与 Jev）、技术架构（放 `docs/assets/architecture.svg`）、关键算法与模型、**数据来源（全部为模拟数据，种子为占位）**、外部依赖、运行方式（离线一条命令可跑）、测试结果（`uv run pytest` 与两份报告的关键数字）、当前限制、**复用说明**（哪些模块复用自赛前 JUE 代码、开源组件清单、人工操作环节）。

### 4. 提交前检查（两人一起）
- `git grep` 检查无密钥、无 `.env`；`seeds/` 中没有真实公司资料或其他企业名称；
- 新机器按 README 能启动（至少在另一个目录全新 clone 跑一次 `uv sync && uv run pytest && uv run streamlit run src/huayan/ui/app.py`）；
- 仓库为私有，邀请 `DsChHack`；复用 JUE 模块的范围由负责人最终确认。

## 验收
首版 Demo 验收 5 条在现场模式或回放模式下各走通一遍；README 中的每个数字都能在 `docs/reports/` 中找到出处。

## 不做
新功能；修改阈值让结果更好看；对外宣称「已接入传化数据」「零泄露」「真实业务已验证」。
