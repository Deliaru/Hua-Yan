# WP-D 演示与提交材料

> **已被 `WP-D2-demo.md` 替代（REPLAN-v5 第 7.1 节），本文件只作历史参考。**

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
- 用现场配置（角色助手、大模型抽取、Jev 降级或 OneJev）跑一遍 `scripts/demo_mainline.py --live`（WP-I 已录制的可直接用），`llm_cache_dir` 写入 `runs/demo_record/llm_cache/`。回放时按 `demo/mainline.yaml` 的台词逐句发送才能命中缓存；现场改了台词就是真实调用。
- `config/app.replay.yaml`：`replay: true`，缓存指向上面的目录。现场网络或接口出问题时切换到它，界面顶部显示「记录回放」。

### 2. 演示脚本 `docs/DEMO.md`（B）
3 分钟版：每一步点什么、说什么、屏幕上应该看到什么；对应首版 Demo 验收 7 条，**以分层转译为主线、由角色助手驱动**（追问 → 场景需求卡 → 觉派单、产品经理助手起草 L2 → 研发助手起草 L3、研发一句话修改并沉淀 → 三层对照 → 确认卡与积分 → 回流命中），推荐短路径和定时发现各一句话带过；附 30 秒版本（只演示一段需求从场景语言到化学语言、每句可回查原话与归属）。

### 3. README 重写（A 起草，B 补评测部分）
按赛事要求：团队信息、业务场景与痛点（注明来自一线业务需求交流）、核心方案（分层转译为主线；会追问、分层可见、权责对等、失真可度量；每人一个角色助手；觉与 Jev）、技术架构（放 `docs/assets/architecture.svg`）、关键算法与模型、**数据来源（全部为模拟数据，种子为占位）**、外部依赖、运行方式（离线一条命令可跑）、测试结果（`uv run pytest` 与两份报告的关键数字）、当前限制、**复用说明**（哪些模块复用自赛前 JUE 代码、开源组件清单、人工操作环节）。

### 4. 提交前检查（两人一起）
- `git grep` 检查无密钥、无 `.env`；`seeds/` 中没有真实公司资料或其他企业名称；
- 新机器按 README 能启动（至少在另一个目录全新 clone 跑一次 `uv sync && uv run pytest && npm --prefix web install && npm --prefix web run build && uv run python -m huayan.ui.server`）；
- 仓库为私有，邀请 `DsChHack`；复用 JUE 模块的范围由负责人最终确认。

## 验收
首版 Demo 验收 7 条在现场模式或回放模式下各走通一遍；README 中的每个数字都能在 `docs/reports/` 中找到出处。

## 不做
新功能；修改阈值让结果更好看；对外宣称「已接入传化数据」「零泄露」「真实业务已验证」。
