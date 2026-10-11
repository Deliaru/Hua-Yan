# WP-D2 演示脚本、提交材料与排练

> 负责：B + 人｜时段：T+24～30（不依赖数字的部分 T+16 后可先起草，不挡开发）｜在 `main` 上进行
> 依据：`REPLAN-v5.md` 第 3.7、4.7、7.1～7.3 节；`VISION.md` 第 7、8 节；`docs/reference/competition.md`；WP-I2 第 6 项
> 替代：`WP-D-demo.md` 与旧 `docs/DEMO.md`（v4 的产品经理页、离线主线、`config/app.replay.yaml` 一律作废）

## 目标

材料与实现一致、能被评委复现：一份按 REPLAN 3.7 写的演示脚本，一份按赛事要求重写的 README，提交前检查与两遍以上排练。**不加功能，不改台词与阈值。**

## 依赖

- WP-I2 第 6 项交给本包的材料：`runs/demo_record/transcript_v5.md`、录制费用与调用次数、简化清单；检查点（`研发待接单`、`回问待答`、`封存待签`、`支线·现成产品待审定`）与 `config/app.demo.yaml`。
- 数字来源：WP-E2（`docs/reports/distortion/`、`docs/reports/single_card/`）、WP-J（`docs/reports/catalog_stats.md`、`docs/JUE_K_TRAINING.md`、重跑后的 `docs/reports/week/`）。某项被 REPLAN 7.2 砍掉，材料里就不出现它的数字。

## 必读

`REPLAN-v5.md` 第 3.7、4.7 节；`VISION.md` 第 7、8 节；`docs/reference/competition.md`（提交要求与五项评审标准）；WP-I2 第 6 项；`runs/demo_record/transcript_v5.md`。

## 允许修改的范围

`docs/DEMO.md`（重写）、`README.md`（WP-I2 写的命令与复用说明两节只核对，其余由本包写）、`docs/assets/`（架构图更新、截图；演示视频放 `docs/assets/demo/`）

不改：`src/`、`web/`、`config/`、`seeds/`、`demo/mainline.yaml`、`runs/`、`docs/reports/`、契约。排练中发现的问题按归属交回（台词与触发点 → WP-I2，界面 → WP-U2，门面与 Agent → WP-C，觉 → WP-J），写进汇报。

## 交付物与已定设计

### 1. 演示脚本 `docs/DEMO.md`（B）

- **开场前**：启动方式只有两种——现场（`app.demo.yaml`，回放关）与回放（`replay: true`）；各自的启动命令、状态条上应看到什么、什么时候切换。没有「离线脚本代替确认」。
- **3 分钟版**：按 REPLAN 3.7 的顺序（开场失败案例 → 第一幕单卡对照 → 第二幕在觉视图上走一遍循环 → 回问高潮 → 封存、发布、L1 命中 → 收尾计数器与飞轮），每一步一行：屏幕位置 | 谁按哪个按钮 / 说哪句 | 解说词 | 应看到什么 | 出问题时载入哪个检查点。客户的话由「下一句」填入、人发出；签字由人按按钮，不播放脚本。
- **支线（20～30 秒，D17）**：从 `支线·现成产品待审定` 载入，研发改一个词审定、业务员转述；解说词用 REPLAN 3.7 的原句。
- **30 秒版**：沿用 `VISION.md` 第 8 节的 30 秒介绍，配一条需求从场景语言到化学语言、每句可回查原话与归属的画面。
- **屏幕上的数字**：只用这次录制或回放真实显示的（觉的判断次数、大模型调用次数、提出决策数、签字数取自 `transcript_v5.md`）；规则打分的推进决策说「到点」，不说概率。
- **不能说的话**：逐条抄 `VISION.md` 第 7 节与 `REPLAN-v5.md` 第 4.7 节，外加 WP-I2 简化清单里会被追问的几条（两位客户同一业务员、演示时间压缩、模拟周处置由脚本决定）。

### 2. README 重写（B 起草，人定稿）

按 `competition.md` 的提交要求逐项写：团队信息、业务场景与痛点（注明来自一线业务需求交流）、核心方案（分层转译为主线；觉是全过程的决策点发现器、流程由觉提出与人签字推动；产品经理 Agent 承担转述与衔接；权责对等）、技术架构（`docs/assets/architecture.svg`，与 v5 不符就更新）、关键算法与模型（觉、Jue-K、Jev / OneJev）、**数据来源（全部为模拟数据）**、外部依赖、运行方式、测试结果（`uv run pytest` 与报告的关键数字）、当前限制（REPLAN 4.7 全部条目 + WP-I2 简化清单）、**复用说明**（复用自赛前 JUE 的模块、开源组件、人工操作环节：演示者扮客户、人签字、模拟周处置由脚本决定）。

- 每个数字后面写出处路径；旧的 w1「3/3 命中、0/4 误报」只在 WP-J 重跑后用新数字替换，没重跑就删掉。
- 只用本次重跑的数字；`jue_proto` + OneJev 跑过的部分不说「零模型调用」。

### 3. 提交前检查（B + 人）

- `git grep` 无密钥、无 `.env`；`seeds/` 与材料中没有真实企业资料或其他化工企业名称；
- 另一个目录全新 clone，按 README 跑一次 `uv sync && uv run pytest && npm --prefix web install && npm --prefix web run build && uv run python -m huayan.ui.server`；
- 仓库为私有，邀请 `DsChHack`；复用 JUE 模块的范围与知识产权归属由人最终确认（人）。

### 4. 排练与演示视频（B + 人）

- 至少完整排练两遍并计时；每个检查点各载入一次，从载入处照脚本走到下一个检查点；
- 记下每次卡点（触发点不出现、缓存未命中、按钮不可签），按归属交回，修好后再排一遍；
- 定稿后由人按 `DEMO.md` 录一遍 3 分钟视频，放 `docs/assets/demo/`（赛事 Demo 展示为可选，网盘链接须在评审期有效）。

## 验收

1. `DEMO.md` 的 3 分钟版在现场与回放两种模式下各走通一遍，计时不超过 3 分钟；支线与四个检查点的载入都试过。
2. 汇报里贴一张「材料中的数字 → 出处文件」表，README 与 `DEMO.md` 的每个数字都能在 `docs/reports/` 或 `runs/demo_record/` 找到。
3. 对照 `VISION.md` 第 7 节逐条检查材料，没有「已接入传化数据」「零泄露」「真实业务已验证」「取代产品经理」「觉已自动发现新的决策点」等说法。
4. 全新 clone 按 README 跑通（第 3 项）。

## 不做

新功能；修改台词、模板、阈值或种子让结果更好看（台词改动交回 WP-I2 重录）；决赛路演 PPT（晋级后再做）；对外宣称 `VISION.md` 第 7 节列出的任何说法。
