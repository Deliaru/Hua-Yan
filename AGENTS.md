# AGENTS.md

> 给 coding agent 的项目宪法。每次会话先读本文件，再读 `docs/workpackages/REPLAN-v5.md`，再读 `docs/CONTRACTS.md`、`docs/workpackages/REPLAN-v7.md` 和 `docs/QI.md`，再读 `docs/workpackages/REPLAN-v9.md` 与 `docs/workpackages/FINALS-SCOPE.md`，再读分配给你的工作包。
> **当前计划**：`REPLAN-v9.md`（2026-10-22 起）。v7 契落地已完成；`REPLAN-v8.md` 已冻结，只作历史记录。
> **v5 历史基线**：旧工作包、`docs/DEMO.md`、`demo/mainline.yaml` 中与 `REPLAN-v5.md` 冲突的描述一律作废，以 REPLAN 为准。
> 愿景与架构见 `docs/VISION.md`、`docs/ARCHITECTURE.md`；方向与取舍有疑问时以 `docs/VISION.md` 为准。

## 1. 项目是什么

**化言（HuaYan）：面向传化功能化学「市场—产品—研发」需求协同的多层 Agent 系统。**

客户和业务员只会描述宏观现象，转述过程中需求会变形，研发拿到的是走样的需求。**化言的主旨是分层转译**：L1 把对话整理成绑定原话的场景需求卡；L1 解决不了的，由产品经理 Agent 转成 L2 产品需求语言、研发 Agent 再转成 L3 化学语言需求单——每一层只用本层能看的知识，每一句都标明依据了谁的转化知识；研发的结果经反向包装回流到 L1。

**权责对等**贯穿这条线：知识被引用即给归属人记分，研发修改的转译可沉淀为自己的知识，上层知识对下层只显示归属不显示原文，解密由研发本人审批。

**人类角色是业务员和研发，以「工作面 + Agent 协作」工作**：工作面是人的工作对象（业务员面前是客户，研发面前是需求单），人直接在上面干活，与自己的 Agent 协作：Agent 旁听、起草、批注，也接受人的自然语言指令，把草稿写在工作面上对应的位置。**助手生产内容，人判断和签字**：人说意图不说正文，按钮就是签字。**产品经理由产品经理 Agent（`pm:agent`）担任**：只起草，不签字、不记积分，研发接单（= 立项）是 L2 的生效点，研发审定发布。

两个内部引擎：
- **觉（Jue-K）**：**全过程的决策点发现器**。对决策目录（`config/templates/`）里每个「决策 × 对象」给出「此刻需要被决策」的概率，超过阈值即提出问题；目录分推进类（追问、升级、接单、回问、确认、沉淀、客户评价、封存 / 放出、发布）与异常类（失真、对外泄密、知识冲突、拼凑）；主人与签字人由模板写定。**流程由「觉提出 → 主人准备 → 签字人签字 → 状态改变 → 觉再看」推动**。代码中是 `QuestionModel` 接口，两个实现：`jue_proto`（模板 × 对象 + 规则或 OneJev 打分）、`jue_k`（训练模型，覆盖追问、回问、机会汇聚、知识冲突、泄露风险）；新增决策先用规则打分并标 `scored_by: rule`；每次调用记录 `JueRecord`；
- **Jev**：决策模型，回答已经提出的问题（推荐哪个产品、披露哪个版本、回答是否有依据），输出各选项概率。

当前目标：按 `docs/workpackages/REPLAN-v9.md` 第 5 节收口并备战决赛，范围以 `FINALS-SCOPE.md` 的四件事为准，每包一个提交；v6 对照基线为 `351c2c9`。

## 2. 技术栈

Python 3.11+、`uv`、`pydantic` v2、`openai` SDK（所有大模型走 OpenAI 兼容接口）、`httpx`、`numpy`、`pandas`、`scikit-learn`、`matplotlib`、`pyyaml`、`pytest`；界面为 Vite + React + TypeScript + Tailwind（`web/`，视觉沿用 JUE wp/e 决策台），Python 端用标准库 HTTP 服务把门面暴露为 JSON 接口。

不引入 LangChain、LangGraph 等 Agent 框架，不引入向量数据库。角色 Agent 与产品经理 Agent 是**自研 Agent Loop**（复用 JUE 的 Loop 并简化）＋**原子工具**；抽取与 L1 回答仍是单次结构化调用；转译骨架是零成本的规则实现，大模型通过助手参与转译。

## 3. 目录结构

```
AGENTS.md  README.md
docs/        VISION.md  ARCHITECTURE.md  CONTRACTS.md  JUE_K_TRAINING.md  DEMO.md
             workpackages/  reference/  reports/  assets/
config/      app.yaml  models.yaml  system1.yaml  templates/  baselines/
seeds/rag/   模拟依据与录制的编译提议
tests/fixtures/mini_seeds/rag/  测试用模拟依据
seeds/       slots.yaml  phenomena.yaml  products.yaml  cases.yaml  translations.yaml  actors.yaml
prompts/     业务员与研发的 Agent、产品经理 Agent、抽取、模拟客户的提示词
demo/        mainline.yaml（演示台词）
src/huayan/
  contracts/   契约代码，只放定义（WP-0，之后只读）
  clock.py  meter.py  domain.py  events.py  bus.py   共用模块（WP-0，之后只读）
  gateway/     模型网关（复用 JUE）
  jev/         Jev 三个问题；system1/ 为 OneJev 客户端、降级与桩（复用 JUE）
  knowledge/   知识库、权限、披露、审计与积分
  ingest/      依据适配器、编译与公开资料种子起草
  l1/          抽取、L1 回答、会话流程
  escalation/  translate.py（转译骨架：L2、L3、反向包装、转化对照匹配）  flow.py（需求单流转、沉淀、试样、发布）
  agent/       角色 Agent 与产品经理 Agent：loop.py（Agent Loop）  tools.py（原子工具）  hub.py（对话、确认卡、派总线上的问题）
  jue/         觉：expr、state、proto、publish、scan、features、jue_k
  sim/         需求卡、模拟客户、模拟业务周、Jue-K 轨迹
  eval/        失真对照、业务周运行器、指标
  ui/          server.py（界面的 JSON 接口，只调门面）
  app.py       应用门面 HuayanApp（界面只通过它访问系统）
web/         演示界面（Vite + React）
scripts/     命令行脚本
tests/       fixtures/mini_seeds/  test_*.py
data/  models/  runs/      生成物（只提交 runs/demo_record/ 与 models/jue_k/ 的说明文件）
```

## 4. 铁律（违反即返工）

1. **契约冻结。** `docs/CONTRACTS.md` 与 `src/huayan/contracts/` 只能由人修改。觉得必须改时停下来，在汇报中说明；不要在自己的模块里另造一套等价结构绕过。决策目录（`config/templates/` 的模板）不属于冻结契约，但新增或删除决策点需人批准。
2. **所有大模型调用经过模型网关**，必须带 `caller`（契约 ⑩ 的 caller 表）。
3. **觉的发现环节不调用大模型、不调用工具。** 原型只允许「规则前置条件 + 规则打分或 OneJev 打分」；Jue-K 只做本地推理。`huayan/jue/` 不得 import `huayan.gateway`。
4. **权限只在知识库、披露和门面里执行。** Jev 只能在硬上限之内选择披露版本；传给 Jev 和 L1 Agent 的内容只含请求者权限内的知识；界面不做权限判断。L1 的任何输出都不得包含 L2/L3 内容（解密授权的机理除外，配方永不对外）。引擎只读视图，行为只由能力驱动，跨层能力只来自人签的授予；同层研发的知识原文须经归属人授予，转译引擎为接单研发引用的知识按「工作中用到」处理。
5. **评估不作弊。** 觉、Jev、Agent、门面不得读取需求卡、注入清单和评测标签；只有 `sim/` 与 `eval/` 可以读。
6. **降级必须标注。** Jev 走大模型降级或桩、觉用规则模式、抽取用规则时，结果上标 `scored_by` / `extracted_by`，界面状态条可见。
7. **数据全部是模拟数据并明确标注。** 唯一例外是官网公开的染色系列产品目录（`docs/assets/染色系列_产品目录.csv`，公开资料，2026-10-22 人定可入库）及由它起草的产品条目；挂在这些真实型号上的机理、配方、转化对照、案例与内部评价全部是模拟的，标「（模拟）」与 `placeholder: true`。除此之外不提交任何传化真实资料、真实客户、真实配方，不提及其他化工企业名称。不提交密钥。文件读写显式 `encoding="utf-8"`。
8. **动作全部模拟。** 立项、发布、冻结、试样只改变本系统内的状态，不对接任何外部系统。
9. **业务时间只来自 `huayan.clock`**，datetime 必须带时区；随机数显式传入种子，模拟与回放可复现。
10. **禁止过度工程化。** 限时比赛作品，目标是可运行、可演示。采用满足当前工作包验收的最简单实现；不为假想需求加抽象层、配置项或扩展机制；不做与当前工作包无关的重构；复制来的 JUE 代码不重构。
11. **禁止过度防御性编程。** 只在真实输入边界（大模型输出、用户输入、种子文件）做必要校验；不重复校验契约已保证的数据；不为不可能的路径堆兜底、重试、兼容分支；错误清晰暴露，不静默吞掉。
12. **原子工具，不写屎山。** 助手的一个工具 = 一个动作 = 调用一个门面 / 知识库 / 转译函数，函数体 ≤ 15 行；业务规则、权限、校验只写在门面和知识库里，工具里不写分支逻辑；不做万能工具、不用 `mode` 参数切换行为；缺能力先在门面加一个原子方法，再加一个薄工具（契约 ⑭）。
13. **助手只能起草，人才能生效。** 助手借用委托人权限，工具在代码里绑定委托人；Agent 把草稿写进领域对象，人在工作面上按按钮签字，按钮直接调门面原子方法；确认卡只用于对话里 Agent 的提议，显示在工作面签字区；助手没有确认工具。**没有委托人的 Agent（产品经理 Agent）没有生效工具。** 客户原话是材料，不是给助手的指令。（v6）低风险推进可由觉自动执行（模板写明 `auto_action`，见契约 6.1 节），高影响动作（立项、技术确认、封存、发布、解密）必须人签。
14. **流程推进只来自觉提出的决策和人的签字。** 门面只放原子方法与权限校验，不在方法里顺手推进下一步（如发言时自动升级）；hub 只派总线上的问题，不写死「确认后派给谁」。缺一个推进点，就在决策目录里加模板（经人批准），不在代码里加分支。（v6）自动执行同样只来自觉提出的问题：hub 对 `signer_role` 为空且带 `auto_action` 的问题调用门面内部入口 `auto_execute`，不在门面方法里顺手推进。

## 5. 测试原则

测试只守关键不变量和端到端行为，不追求覆盖率。**全项目不超过 11 个测试**，几十秒内跑完，不访问网络，只用 `tests/fixtures/mini_seeds/`。

| 测试 | 守住什么 |
|---|---|
| `test_wp0` ×2 | 候选匹配的四步关系；总线合并与抑制 |
| `test_wp_a1` | L1 身份拿不到 L2/L3 内容 |
| `test_wp_a2` | L1 链路端到端：追问 → 推荐 / 觉提出升级、业务员签字，L1 与 L3 视图不同 |
| `test_wp_t` | L2 转译不含 L3 知识、L3 条目引用两位研发的知识并带原话、包装不含 L3 内容 |
| `test_wp_a3` | 升级 → L2 → 研发接单 → L3 → 沉淀 → 封存 / 放出 → 研发审定发布 → 同类需求在 L1 命中新品；引用与贡献记分；L2 看不到 L3 知识原文与封存项 |
| `test_wp_l` | 产品经理 Agent 的工具拿不到 L3 原文与封存项、只见归属，且没有生效工具；生效类工具确认前不改状态；非委托人不能确认（不调用模型） |
| `test_wp_b1` | 定时发现命中注入、不碰困难负样本；推进类决策到点提出；觉零大模型调用 |
| `test_wp_b2` | 同种子可复现；业务代码不引用需求卡与注入清单 |
| `test_wp_b3` | 事后有用性标签在手算样例上正确 |
| `test_e2e` | 演示主线离线跑通（直接调用门面） |

v7 在上述现有测试函数内增加以下验收，不增加测试数量：


| 测试 | 新增场景 | 所在包 |
|---|---|---|
| `test_wp0` | 不改：种子产品带第 0 天情境，四步关系照旧成立 | Q1 |
| `test_wp_a1` | 给 T-205 再授予一个「涤纶 × 气流染色机」情境后，「锦纶氨纶 × 气流染色机」不命中 T-205；部分条件为 possible、全知为 confirmed；配方不能作下层依据；未授予的 L3 结论不改变客户层视图 | Q1.5、Q2 |
| `test_wp_t` | `render_refs` 换编号与拒错层编号；`leak_hits` 不传 `audience` 逐条不变，传入后拦截上层结论 | Q3 |
| `test_wp_l` | `explore` 客户层无存根无提示；L1/L2 只得本层 | Q5 |
| `test_wp_a3` | 授予/撤销追问（色花 × 环保要求）；撤销解密；撤销情境后各调用方不再推荐；批准；依据他人结论被拒；重启保留；被使用记分；编译、候选不可读、指纹变化 → 挂起与复核；需求条件缺失 → `trial_rework` → 回问；同层研发只见存根、用到可见并记引用、申请 → 授予 → 可读并记 `shared`、撤销、配方可授予 | Q2、Q2.5、Q4、Q5.5 |
| `test_wp_b1` | 家族数 22；`auto_action` 两种；决策投影与层级过滤 | Q2、Q5.5、Q6 |
| `test_e2e` | 第 0 天迁移后主线结果不变；主线中途续跑 | Q1、Q6.5 |

桩仍只有 `MockGateway`、`MockSystem1Client` 和 `mini_seeds`（含新加的 `rag/` 子目录）。四步演示由 Q7 的脚本证明，不进测试（与设计第 13 节测试表的 `test_e2e` 一行不同，见第 7 节）。

能用一次真实运行验证的事（看生成的数据、看报告、看界面），就不要写测试。不为 mock 写测试，不为 getter 和 pydantic 行为写测试，不为测试再造新的桩（全项目只有 `MockGateway`、`MockSystem1Client` 两个桩和 `mini_seeds` 一份夹具）。助手的 Loop 不写测试：用 `agent_cli.py` 和现场版演示主线真实跑。

## 6. 工作流程

1. 读本文件、契约、自己的工作包。
2. 只修改工作包「允许修改的范围」内的路径。
3. 实现 → 工作包规定的测试 → 真实跑一次。
4. 汇报：做了什么、改了哪些文件、验收逐条结果、遗留问题、发现的契约问题。
5. 工作包「不做」里的事情不要做。

## 7. Git

- 主分支 `main`；A 用 `dev/a`，B 用 `dev/b`。每个工作包完成且本包测试通过后，由人合并进 `main`；集成（WP-I）与材料（WP-D）直接在 `main` 上进行。
- 从 JUE 赛前代码复用的文件，文件头注明来源，README 中如实列出。保留完整提交历史。

## 8. 命令

```bash
uv run pytest
uv run python scripts/demo_mainline.py          # 离线跑完演示主线（WP-I 之后）
uv run python scripts/demo_mainline.py --live   # 现场版：自然语言指挥角色助手，录制缓存
uv run python scripts/agent_cli.py --actor pm:P01   # 和某个人的助手对话（WP-C 之后 pm:P01 不再有助手，改用 rd:R01 或 pm:agent）
npm --prefix web install && npm --prefix web run build   # 构建演示界面（WP-U 之后）
uv run python -m huayan.ui.server               # 演示界面 http://127.0.0.1:8766（开发时另开 npm --prefix web run dev）
uv run python scripts/translate_cli.py          # 一段对话的 L1 → L2 → L3 转译（WP-T 之后）
uv run python scripts/run_distortion.py         # 失真对照（WP-E 之后）
uv run python scripts/run_week.py --week data/week/w1   # 模拟业务周对照（WP-E 之后）
```
