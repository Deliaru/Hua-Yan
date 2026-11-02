# AGENTS.md

> 给 coding agent 的项目宪法与 V10 冻结契约。
> **强制要求：每次开始编程、修改任何代码或切换工作包前，都必须重新完整阅读本文件（`AGENTS.md`）**，再读 `docs/workpackages/REPLAN-v11.md`（当前计划）、`docs/CONTRACTS.md`、`docs/QI.md`，涉及 V10 已交付机制时再读 `docs/workpackages/REPLAN-v10.md` 与对应的 `WP-*v10*.md`（`V10-REVIEW.md` 是 10-28 的规划快照，不反映实现现状）。严禁不读本文件直接凭工程惯性写代码。
> 当前分支：`v11`（自 `v10 @ 6abfaea` 分出）。V10.0–V10.10 首版已交付，专业确认与四岗位真人验收由 V11 承接，V10 状态与证据见 `docs/reports/v10-evidence.md` 和各包最新完成记录。愿景与架构见 `docs/VISION.md`、`docs/ARCHITECTURE.md`，展示见 `docs/workpackages/FINALS-SCOPE.md`，V9 的历史计划与试用记录见 `docs/workpackages/REPLAN-v9.md`；方向与范围取舍以 `docs/VISION.md` 和 `docs/workpackages/REPLAN-v11.md` 为准。

## 1. 项目是什么

**化言（HuaYan）：面向产业的组织智能运行架构，以组织级 Agent Harness 重构企业的决策、协作与能力积累。第一个验证场景是传化功能化学「市场—产品—研发」的需求协同与专业能力复用。**

Harness 是一组运行职责，由现有组件承担：业务对象与状态落盘、事件流、问题总线、hub 派单、角色 Agent 与原子工具、工作面上的人工生效、门面的原子动作与权限（对应表见 `docs/ARCHITECTURE.md` 第 0 节）。不要为它另建一个总调度 Agent 或平行状态。

在功能化学场景中，客户和业务员用场景语言描述问题，化言把原话中的需求转成可回查原话与依据的专业需求单；按 L0–L3 知识边界与同层归属分层协同；从真实企业资料（试样报告、产品说明书、图表）读取证据并编译成候选判断，经专业人员确认、用途授予与必要的产品范围批准后，沉淀为下一单可直接复用的组织能力。

Harness 中的四个核心机制：
- **觉（Jue-K）**：信息反射与决策形成（通用信息反射层的业务落点），在决策目录（`config/templates/`）、对象和特征界定的范围内，形成、维持、筛选并提交值得决策的事项。代码中是 `QuestionModel` 接口，含 `jue_proto`（规则或 OneJev/Clef 打分）与 `jue_k`（按「家族 × 判断层」本地推理模型）；界面标明实际加载的模型；
- **Jev**：决策与核对模型，回答已经提出的问题（推荐哪个产品、披露哪个版本、依据核对与候选重排），经 `OneJevClient` / `ClefClient` 输出各选项概率；
- **契（Qi）**：能力规范与分层组织记忆，把读取工具中的**依据（`Fragment`）**编译为专家确认的**结论（`KnowledgeUnit`）**，再授予为各层可用的**能力（`Capability`）**，管理专业判断的来源、完整条件、授予、复核与撤销；
- **角色 Agent**：自研 `Agent Loop` + 原子工具。业务员负责客户与商务，真人产品经理负责产品范围与商业判断，研发负责专业判断与成果，研发负责人在授权范围内掌握进展、处理例外；`pm:agent`（L2）承担后台逐单转译与材料准备。人也可以随时主动委托或处理事项。

**当前目标（V11，决赛 2026-11-08）**：为每个岗位提供以「轮到你的事」为入口的工作面（客户、业务员、产品经理、研发、研发负责人）和 CEO 面；`sim/` 中的导演只扮演外部世界与缺席岗位，按九个关卡送来真实形态的事，每件事带前情与旧流程对照，让参与者一边处理一边看出效率从哪里来。游戏模式用模拟时钟与独立运行目录；真实模式就是下述 V10 目标的真人验收。范围、关卡与工作包见 `docs/workpackages/REPLAN-v11.md`，V11 不改下表的冻结契约。

**承接的 V10 目标**：在项目方现场陪同下，**业务员、真人产品经理、研发和研发负责人在同一个共享试用实例中，用一份真实报告完成专业判断，并让下一件符合条件的需求直接用上这份判断**。

实施里程碑与工作包严格按以下三级边界执行（**工作包是修改归口，不是必须整包做完才能进下一包的阶段门**；禁止跨级扩范围）：
- **M1 一份报告能读、能审**（`V10.0` 选定原件后，`V10.2` 与 `V10.4` 围绕同一份报告一起推进，CLI/静态审阅包即可交付）→ **M2 一次判断服务下一单**（首份记录交 `V10.5`、`V10.7` 先用现有枚举和限制原文走通候选确认与授予；`V10.6` 补温度单字段后接通同范围/未知/超范围匹配）→ **M3 四类真人完成业务**（`V10.9` 一条定向准备与原单回流链 → `V10.10` 开发者走通后交四类真人试用）；`V10.3` 与 `V10.8` 为展示支线，不阻塞 M1–M3。

| 优先级 | 范围与首版交付标准 |
|---|---|
| **决赛必需** | **V10.0**（选定报告/图表题，给出来源清单与 C1/C4 约定）、**精简版 V10.1**（清单供读取直接使用；统一读取入口按「来源类别 × 当前角色层级」接现有权限检查一次）、**V10.2**（按首份报告样例做解析与读数，无需等待 V10.1 入口）、**V10.4**（首份 A/B `TrialRecord` 与原文审阅包，随后补文本配方与负例）、**V10.5**（一条完整条件 IR 导入候选，补充依据留待确认）、**单字段 V10.6**（首版**只做摄氏温度单值/闭区间**，C2 在本包确定，打通「抽取 → 匹配 → 下一单」）、**V10.7**（C7 在本包确定，固定证据审阅、确认授予与下一单复用）、**V10.9**（一条定向准备与原需求回流链，先按产品/来源编号定位资料）、**V10.10**（开发者走链、四角色真人试用；图表支线就绪时附两组小对照） |
| **可演示即可** | **V10.3**（一道图表题查准 +「关键词 A 对图文 C」与「Jev 开/关」两组对照）、**V10.8**（演示资料副本改一处被引用条件，用现有 `recheck` 与 `qi_review` 展示挂起和两种复核结果） |
| **决赛后（本轮严禁实现）** | 动态来源授权、撤权后的缓存清洗、聚合数量防泄露、历史权限回看、通用版本系统与全量依赖传播、pH/用量/时间等多字段数值条件与单位换算平台、数值修正后自动重跑试样/发布全链、别名版本化重跑、独立文本向量 B 组、分块/前缀消融及大样本概率校准 |

## 2. 技术栈

Python 3.11+、`uv`、`pydantic` v2、`openai` SDK（所有生成模型走 OpenAI 兼容网关）、`httpx`、`numpy`、`pandas`、`scikit-learn`、`matplotlib`、`pyyaml`、`pytest`；前端为 Vite + React + TypeScript + Tailwind（`web/`），Python 端 `huayan.ui.server` 以标准库 HTTP 服务将应用门面 `HuayanApp` 暴露为 JSON 接口。

资料读取与解析按选定代表文件的实际需要选用轻量组件（置于 `src/huayan/ingest/reader/`），图文检索嵌入按配置使用本地 `EmbeddingGemma 2`（不可用时退回关键词并明确标注）。不引入 LangChain/LangGraph 等重型框架、独立向量数据库服务、图数据库或分布式调度器；原件、页面、裁图、读数、`TrialRecord` 与检索索引全部留在读取工具侧（可被企业 RAG 替换），不塞进契的正式状态文件 `qi_state.json`。

## 3. 目录结构（顶层布局，以 `v10` 当前树为准）

```text
AGENTS.md  README.md
docs/        VISION.md  ARCHITECTURE.md  CONTRACTS.md  QI.md  JUE_K_TRAINING.md  DEMO.md
             workpackages/（REPLAN-v11.md、CEO-VIEW.md、REPLAN-v10.md、V10-REVIEW.md、WP-0v10..WP-10v10、REPLAN-v9.md、FINALS-SCOPE.md）
             trial/  reference/  reports/  assets/
config/      app*.yaml  models.yaml  system1*.yaml  templates/  baselines/  eval/
seeds/       slots.yaml  phenomena.yaml  products.yaml  cases.yaml  translations.yaml  actors.yaml  public.yaml  rag/
prompts/     assistant_{sales,pm,rd}.md  extract.md  answer_l1.md  customer_sim.md  sim_*.md
demo/        mainline.yaml  routes.yaml  story.yaml
src/huayan/
  contracts/   契约代码，只放跨模块定义（冻结，仅按第 4 节铁律 2 最小增量修改）
  clock.py  meter.py  domain.py  events.py  bus.py   共用核心模块
  gateway/     client.py（统一 complete / structured、缓存与计量）  mock.py  byok.py
  jev/         __init__.py（Jev 三问）  system1/onejev.py（OneJevClient / ClefClient / LLMSystem1Fallback）  system1/mock.py
  knowledge/   store.py（KnowledgeBase 与 qi_state）  permission.py（can_read / colleague_l3）  disclosure.py（render / render_refs）  records.py（AuditLog / Ledger）
  ingest/      folder.py（FolderSource）  compile.py（propose / admit / recheck）  draft.py  reader/（V10 新增：解析、读数、TrialRecord、检索）
  l1/          extract.py（RuleExtractor / LLMExtractor / validate_extraction / apply_extraction）  answer.py  session.py
  escalation/  translate.py（转译骨架与 leak_hits）  flow.py（需求单流转、试样、新品发布）
  agent/       loop.py（Agent Loop）  tools.py（原子工具注册表）  hub.py（AgentHub：按对象对话、派单、失败重试）
  jue/         expr.py  state.py  proto.py  publish.py  scan.py  features.py  records.py  jue_k.py  train.py
  sim/         cards.py  customer.py  humans.py  schedule.py  trajectory.py  week.py  month.py  world.py
  eval/        distortion.py  single_card.py  week.py  month.py  backtest.py  catalog.py  metrics.py
  ui/          server.py（共享试用实例 TrialGate / 角色会话 trial_roles / JSON 接口，只调门面）
  app.py       应用门面 HuayanApp（UI、Agent 工具与脚本的唯一正式业务写入入口）
web/         前端工作台（Vite + React + TypeScript）
scripts/     命令行与评测脚本（compile_qi.py、demo_*.py、run_*.py 等）
tests/       fixtures/mini_seeds/  test_*.py
data/  models/  runs/      本地资料与运行产物（data/knowledge_v10/、data/pilot/ 等均不入库）
```

## 4. 冻结契约与铁律（违反即返工）

1. **每次编程前必须重新阅读 `AGENTS.md`。** 每次会话开始、切换工作包或动手写/改任何代码前，必须先重读本文件全文，核对冻结契约、现有实现与禁止过度防御条款；在汇报中说明已按本文件自查。
2. **契约冻结与 V10 按包最小增量（禁止前期大设计）。** `docs/CONTRACTS.md` 与 `src/huayan/contracts/` 保持冻结（所有模型继承 `contracts._base.BaseModel`，`extra="forbid"`）。严禁在业务模块里另造平行结构或用未声明的自由字符串绕过比较器，也严禁在 V10.0 一次性预改全部契约。V10 允许的契约与核心机制改动冻结如下：

   | 编号 | 所在包 | 冻结边界与允许的最小改动（基于 `v10 @ 840bd46` 源码） |
   |---|---|---|
   | **C1 图片输入** | V10.0 定 / V10.2 用 | `contracts/gateway.py::Message.content` 保留 `str` 兼容，增加类型化文本/图片内容结构；走 `gateway/client.py` 统一调用、`caller`、计量与指纹缓存 |
   | **C4 证据定位** | V10.0 定 / V10.2 用 | **`contracts/knowledge.py::Fragment` 只有 `doc_id/span/text/level/source/fingerprint`，绝不加 `meta` 字段**；页码、区域、版本留在读取侧，用文件指纹与块位置映射到现有 `Fragment` |
   | **C2 温度条件** | V10.6 确定 | 到 V10.6 开工时再定最小差异；保留 `Situation.conditions` 枚举字典，只为**摄氏温度（单值/闭区间）**补带默认值的最小字段，在 `domain.py` 用一个函数返回满足/待补/超范围并接入 `match_candidates`（满足且无未知/限制为 `confirmed`，温度未知待补为 `possible` 并列入 `unknown_slots`，超范围不命中该情境），**严禁另造平行候选匹配链路** |
   | **C7 确认与挂接** | V10.7 确定（连同 V10.5） | 只修补 `ingest/compile.py` 与 `knowledge/store.py` 的三处具体缺口：① V10.5 修 `compile.py::admit`，未结构化完的条件必须保留进 `limits` 或标待审，不能只认出部分条件就提议无限制 `applicable`；② V10.5/V10.7 修 `store.py::attach_evidence`，相同 payload 的新依据先存为 `status="candidate"` 并记待挂接目标，经 `confirm` 后再挂入 `cap.based_on`；③ V10.7 修 `store.py::confirm`（确定 C7 参数），核对本次实际审阅的证据指纹，不再直接用 `self._fragments(unit)` 静默刷成当前新指纹 |
   | **C3 / C5 / C6 / C8** | 各消费包 | **不改冻结契约**：来源读取入口直接复用 `ui/server.py` 服务端主体与 `knowledge/permission.py`（C3）；核对直接调 `System1Client` / `ClefClient` 并存模块内记录，不改 `JevDecision`（C5）；复用现有 `EventKind`（C6）；来源变化直接沿用现有 `compile.py::recheck` → `kb.evidence_changed` → `qi_review` 挂起与复核语义（C8） |
   | **读取侧内部类型** | V10.1–V10.5 | 清单、`EvidenceBlock`、`TrialRecord`、`IR` 与审阅包均留在 `src/huayan/ingest/` 模块内部，**严禁塞进 `src/huayan/contracts/`** |

3. **所有大模型调用经过模型网关**，必须带合法 `caller`（契约 ⑩ caller 表，知识编译与读取使用 `ingest:extract` / `ingest:draft`，抽取使用 `agent:extract`，助手使用 `agent:<role>`）。
4. **觉的发现环节不调用大模型、不调用工具。** 觉只用「规则前置条件 + 规则打分、OneJev/Clef 打分或本地 Jue-K 推理」，不执行检索或编译；`huayan/jue/` 不得 import `huayan.gateway`。本轮新增字段不得静默改变已训练 Jue-K 的特征含义，不恢复 V9.6a 已停用的 `leak_risk|L2` 旧模型。
5. **权限只在统一入口、知识库、披露和门面里执行。**
   - **读取工具只做单入口检查**：V10.1 只在读取工具的统一入口按「**来源类别（公开 L0 / 内部默认 L3）× 当前角色层级**」叠加 `knowledge/permission.py`（`can_read` / `colleague_l3` / `kb._shared`）检查一次；**严禁**在列表、片段、裁图、缓存、派生表、聚合每个函数出口重复写 ACL 检查。
   - **查证与正式能力分开**：内部查证仅供有权角色阅读或送审；客户推荐与跨层对外表述只消费 `kb.view(actor)` 中当前 `active` 的能力。L1 输出不得含未解密 L3 内容，**配方永不对外，不能因转为 `claim` 或汇总记录而降密**。
   - 角色会话主体由 `ui/server.py`（`trial_roles` / `trial_params`）服务端认定，界面不做权限判断，助手工具由 `ToolContext` 绑定委托人，`pm:agent` 保持 L2 且无 `effect` 工具。
6. **唯一正式写入入口与真人签字。** 正式领域状态（`qi_state.json`、需求单、会话、事件日志）只由 `HuayanApp` 门面写入；后台任务只提交读取/编译产物，CLI 导入仅在应用停止时执行。候选导入一律为 `candidate` KU / `proposed` Capability；确认（`confirm`）、授予（`grant`）、范围批准（`approve`）和发布必须由有权的人签字，Agent 只能准备草稿（准备完成以 `app.preparation_gap(question_id)` 检查对象内实际草稿/产物为准）。
7. **原话语义在一处理解，读数与条件保真。**
   - 客户意图、数值、单位、区间、未知、否定和纠正只在 `l1/extract.py` 抽取入口处理，下游读 `NeedState` 结构化结果；某次漏抽不清空已有事实，「明确不清楚（`status="unknown"`）」与「尚未询问」分开。
   - 报告读取保留共同条件、A/B 组别（B 组数据绝不回填 A 组）、工艺阶段与原单位；未知百分比基准不默认当成 `%owf`，缺浴比/布重不强行换算；未读清、冲突或结构表达不了的限制保留在 `limits` 原文或标待补读交人处理，**决不能把未知或未识别条件当成「不限」**。
8. **评估不作弊、数据与时钟规范。** 觉、Jev、Agent、门面、读取与编译代码不得读取需求卡、注入清单和 `data/knowledge_v10/evaluations/` 中的金标答案；只有 `sim/` 与 `eval/` 可读。内部原件、含原文的中间产物和密钥留在 `data/` 等不入库目录（根目录 `2-主办方资料目录.md` 保持未跟踪）。业务时间只来自 `huayan.clock.get_clock().now()`（试用用 `WallClock`，模拟用 `SimClock`，`datetime` 必须带 `SHANGHAI` 时区），随机数显式传 ` random.Random(seed)`，文件读写显式 `encoding="utf-8"`。
9. **降级与数据来源如实标注。** Jev 走 `LLMSystem1Fallback` 或 `MockSystem1Client`、觉用规则模式（`scored_by="rule"`）、检索退回关键词、抽取用 `RuleExtractor`（`extracted_by="rule"`），以及开发者走链中模拟的专业签字/试样结果，都必须明确标注，界面状态条可见；不预写达标数字，不把模型输出当真值。
10. **禁止过度工程化（核心红线）。** 保持本仓库一贯的极简代码风格（参考现有模块：`permission.py` 25 行、`folder.py` 60 行、`domain.py` 82 行、`compile.py` 150 行）。
    - 采用满足当前工作包首版验收的最短、最直白实现；**先围绕选定的一份真实报告跑通 M1 → M2 → M3**，不为假想需求加抽象基类、工厂模式、插件注册表、配置开关或版本库。
    - 解耦前置依赖：V10.2、V10.4 直接拿 V10.0 的清单处理首份报告，不等待 V10.1 的查证入口或其他文件格式；V10.7 先用现有枚举和限制原文完成首条候选审阅，温度复用再接 V10.6；V10.9 先通过统一入口按产品/来源编号直接定位选定资料，不等待 V10.3 图文检索。
    - V10.6 首版**只实现摄氏温度一个字段的闭区间包含判断**，不建通用物理量与单位换算平台。
    - V10.8 **直接复用现有 `compile.py::recheck` 与 `qi_review`**，只在演示资料副本上改一处被引用条件展示挂起与两种复核结果，不为静态资料设计版本控制系统。
    - V10.10 对照实验**只保留「关键词 A 对图文 C」和「Jev 开/关」两组**，按逐题失败原因选默认配置。
    - 助手原子工具保持极简：一个 `@tool` = 调用一个门面 / 知识库 / 读取函数，函数体 ≤ 15 行，参数模型扁平（字段 ≤ 5、不含身份字段），不写业务分支与 `mode` 开关。
11. **禁止过度防御性编程（核心红线，Codex 必查）。**
    - **格式与类型校验只在真实外部边界进行**：只在模型输出解析（`validate_extraction` / `structured`）、HTTP/CLI 入口参数、外部文件头与损坏识别处做输入格式与结构校验；内部函数之间直接信任 Pydantic 契约已保证的字段类型与服务端已绑定的 `Actor` 身份。
    - **本条禁止重复验证已有保证，不禁止必要的业务规则检查。** 契约明确允许的联合类型（如 `Message.content` 的 `str | list[...]`）、可选值（`None`）和未知状态（`"unknown"`），可以按其语义正常分支处理；权限（如授予人须为结论确认人）、状态转换、证据指纹一致性与适用条件仍由既有职责模块检查。新增校验或兜底须对应当前需求、真实外部输入或已复现问题。
    - **严禁以下防御性样板代码（写出即返工）**：
      1. 严禁对契约已保证的单类型/必选字段重复写 `isinstance`、深层 `if x is not None and hasattr(x, ...)` 空值防御链，或用 `getattr(obj, "field", default)` / `dict.get` 叠床架屋；
      2. 严禁写宽泛的 `try ... except Exception:` 吞掉异常并返回空列表/空字典/假默认值；业务拒绝统一抛 `ValueError` 或 `PermissionDenied`，由 `tools.py`（转 `ToolResult(ok=False, error=...)`）和 `ui/server.py` 统一接住；
      3. 严禁在每个包里各自发明文件锁、并发锁、幂等去重表、缓存失效器、快照回滚或重试框架——共享并发已由 `ui/server.py::TrialGate` 处理，状态原子落盘已由 `KnowledgeBase._save` 处理，Agent 失败重跑已由 `AgentHub.failures / retry` 处理；
      4. 严禁为没人提过的假想威胁写防御代码（如客户端自报身份验签、撤权后逐条清内存缓存、聚合查询防数量差分泄露、多层自动降级恢复树）；读不清或缺条件的资料直接标为待人工补读或放入 `limits` 交研发处理。

## 5. 全局不变量与测试原则

横切不变量集中在下表（`G1`–`G6`），由现有共用机制与回归测试统一守住。各工作包只引用编号（如 `共用回归：G1/G2`）并只验证本包特有的业务交付，**不得在每个工作包里重复编写横切防御代码与重复测试**。

| 编号 | 全局不变量 | 现有共用守卫机制（直接复用，严禁重写） |
|---|---|---|
| **G1 主体与知识边界** | 服务端认定身份；L0–L3、同层归属与 `share` 沿用现有规则；读取工具只在统一入口按「来源类别 × 角色层级」检查一次；业务使用走 `kb.view(actor)`，配方永不降层 | `ui/server.py::trial_params`、`knowledge/permission.py::can_read`、V10.1 统一读取入口 |
| **G2 原意、条件与出处** | 原话语义只在 `l1/extract.py` 理解，漏抽不丢已有事实；报告保留共同条件、A/B 组别、阶段、单位与 `limits` 原文；温度闭区间完整包含才满足，未知与限制交回问或研发 | `l1/extract.py`、`domain.py::match_candidates`、`kb.limits()`、读取侧出处指针 |
| **G3 确认与能力状态** | 编译只入 `candidate / proposed`；补充依据先候选后确认；`confirm` 绑定实际审过的证据指纹；使用检查当前 `active` 状态，依据变化或撤销后挂起并重匹配 | `knowledge/store.py`（`confirm/grant/approve/revoke/evidence_changed`）、`app.py` 重匹配 |
| **G4 对象与执行** | 复用 V9 共享实例、按对象装配助手上下文、状态落盘与整项重试；正式状态只由 `HuayanApp` 写入；两单各归各单，签字/发布/授予只生效一次 | `app.py`、`ui/server.py::TrialGate`、`agent/hub.py`（`agent_threads: object`、`retry`）、`qi_state.json` |
| **G5 模型与反馈** | 大模型走网关带 `caller`；觉发现评分零网关调用（只用规则、OneJev/Clef、本地 Jue-K）；准备完成以 `preparation_gap` 检查对象内实际草稿/产物为准；人的处置与结果留作学习依据 | `gateway/client.py`、`jue/`、`app.py::preparation_gap`、`jue/records.py` |
| **G6 数据与证据** | 内部资料与运行产物留 `data/` 不入库；评测金标存 `data/knowledge_v10/evaluations/` 只供 `eval/sim` 读取；真实/模拟、调试回归/未见样本分开记录，报核验后的可评分分母 | 目录物理隔离、运行与评测脚本配置 |

**测试纪律**：
- 现有 15 个测试文件（`test_wp0`、`test_wp_a1`～`a3`、`test_wp_b1`～`b3`、`test_wp_t`、`test_wp_l`、`test_e2e`、`test_extract_asking`、`test_agent_object`、`test_applicable_limits`、`test_clef`、`test_trial`）全部保留，默认离线运行、几十秒内跑完。
- 用 V8/V9 的原失败输入守住未知回问、串单、准备缺口、条件修正与限制保留；V10 新增测试只针对本包真实问题补充核心行为（首份报告 A/B 不串组、摄氏温度闭区间匹配、固定指纹确认与同 payload 补充依据候选化、一处条件修改触发挂起与复核）。
- 能用一次真实运行验证的事（看导出的审阅包、看两组对照表、看界面）就不写冗余测试；不为 mock、getter、pydantic 行为或假想异常分支写测试；入库夹具统一放 `tests/fixtures/` 并使用明确标注的合成材料。

## 6. 工作流程

1. **每次动手写/改代码前，必须先重新阅读本文件（`AGENTS.md`）全文**，再读 `docs/workpackages/REPLAN-v11.md`、涉及的契约与 V10 已交付机制对应的工作包。
2. **只做当前包范围内的事**：只修改工作包「允许修改的范围」内的路径；工作包「不做」与本文件第 1 节「决赛后」的内容一律不做；不在包内重复写 `G1`–`G6` 已覆盖的横切防御代码。
3. **契约改动按授权执行**：普通模块实现直接做，一口气做完；确需改动冻结契约时，严格限制在第 4 节铁律 2 的表格范围内，列清最小字段差异与默认值并按会话授权落实。
4. **先走通单份样例纵向链路**：实现 → 跑受影响的现有测试与本包测试（`uv run pytest`）→ 在选定真实样例上真实跑一次核对产物。
5. **如实汇报与记录**：更新工作包「完成记录」（做了什么、改了哪些文件、运行入口、真实/合成数据、实际模型、验收逐条结果、遗留问题和交给下一包的对象）。

## 7. Git

- 当前工作分支为 `v11`（自 `v10 @ 6abfaea` 分出），之后按用户指定分支工作。
- 开始前先确认当前分支与工作区已有改动；根目录 `2-主办方资料目录.md` 以及 `data/`、`runs/` 下的原始资料、金标、模型缓存与运行产物均不入库、不随工作包提交。
- 每个提交围绕当前工作包的明确交付，不混入无关重构；推送前核对分支状态，合并主分支与部署由人决定。

## 8. 命令

```bash
uv run pytest                                                                          # 默认离线回归测试
npm --prefix web run build                                                             # 前端构建检查（修改 web/ 后运行）
uv run python -m huayan.ui.server                                                      # 本地服务（http://127.0.0.1:8766）
uv run python -m huayan.ui.server --trial <run_id> --config data/pilot/app.trial.yaml  # 四角色共享试用实例
uv run python scripts/compile_qi.py                                                    # 契离线编译入口（应用停止时执行）
```
