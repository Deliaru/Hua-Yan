# 化言 HuaYan

> 让需求在传递中不走样。

面向传化功能化学「市场—产品—研发」需求协同的多层 Agent 系统。参赛赛道：AI＋功能化学（自主深化「AI 化学家」推荐场景）。

**当前状态：设计阶段，尚未开始开发。** 本文件将在演示版完成后按赛事要求重写（团队信息、业务场景、核心方案、技术实现、数据来源、外部依赖、运行方式、测试结果、当前限制）。

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
- 部分基础模块（模型网关、OneJev 客户端、计量、时钟、表达式求值器）复用自团队赛前项目 JUE，文件头注明来源，开发后在此逐一列出。
