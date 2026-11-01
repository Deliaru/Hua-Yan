# V10 开发者走链

## 当前主线证据交接（2026-11-01）

运行 `uv run --locked --no-sync python scripts/package_v10_handoff.py`，生成[本地总入口](../../data/knowledge_v10/validation/finals-handoff/review.html)及summary.json。入口仅汇集已有首份/负例原图与记录、Qwen读图及温度实调/回放、在线角色准备、开发者模拟复用、合成来源复核、待真人实例和记录模板；不调用模型、不写业务、不读评测金标。输入文件不存在时直接报错，不生成虚假通过项；summary保存输入指纹和逐项边界。

在线角色准备是独立合成需求；开发者模拟链的确认/授予是另一个实例，两者不拼成一次真人全链成绩。当前固定模型为SiliconFlow Qwen/Qwen3-VL-8B-Instruct，温度原五轮回归已通过，先前429及温度失败页作为历史保留。35题扩写与检索支线仍暂停，下文旧题证据只供回查。

打包会生成app.human-online.yaml，沿独立human-review-ready运行接现有Qwen/Clef及object对话，打包时不启动。原人工审阅配置保留mock/规则。真实试用启动、账号映射与集中待审内容见[当前四岗位交接](first-report-v10.md)。此前旧first-report实例不作为下一轮真人起点，已经授权开发者模拟无需重复审批。

## 首份报告授权说明

这条入口用首份真实报告的读取记录与操作观察 IR 验证软件流程。需求、确认、授予措辞及撤回均由脚本模拟；没有真人参与，不构成企业专业判断或产品适用结论。

在项目根目录运行：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/run_v10_statement_chain.py
```

默认读取首份实例配置和 `first-report` 的知识状态。配置须登记 `source_manifest` 与 `source_irs`，IR 须已指定研发归属；可用 `--config`、`--doc-id`、`--source-run` 指定已有输入。原件、原实例状态只读，所有运行写入新建的 `data/knowledge_v10/validation/statement-chain-<编号>/`。

运行依次执行：

1. 复制知识状态，强制 mock 网关/System1、规则抽取和规则觉；在隔离演练中限定分单参与研发，创建合成需求后恢复身份表。
2. 脚本通过 AgentHub 调用已注册的需求/会话读取、原文读取、准备材料保存、IR 编译导入工具；这不是生成模型自主规划测试。
3. 读取固定证据指纹，模拟研发确认；由现有“本层答不了”信号提出授予事项，再模拟授予一句明确标注开发者演练的客户层说明。
4. 核对说明回到原会话；下一位合成客户经原 L1 问答链引用该说明，并留下 `capability_used` 记录。
5. 模拟撤回结论，核对能力挂起、原会话与新会话不再得到该说明。

终端只输出运行结果与报告路径。运行目录中的 `summary.json` 记录来源、候选与能力编号、真实工具调用、使用事件、运行配置、计量中的模型调用数和人工帮助；`report.md` 提供简短走链与事项观察表。准备材料、事件、会话与模拟签字在该目录内可回查。

报告中的真实签字为0、真人参与名单为空。真实报告的产品适用范围、来源修订复核及四岗位真人试用仍须分别完成；不能用本次授权说明链替代这些验收。

## 合成产品适用与温度三分支

在项目根目录运行：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/run_v10_temperature_chain.py
```

入口复用 `tests/fixtures/mini_seeds` 与明确标注非企业报告的 `synthetic-temperature.txt`。T-205、70—80℃范围、需求及研发/产品经理签字均是合成演练，与首份真实报告的TF-213HE无关；未把报告132℃试验点推断成授权范围。每次新建 `data/knowledge_v10/validation/temperature-chain-<编号>/`，不读取或覆盖真实实例状态。

脚本仅在合成实例撤销旧的无温度限制种子，由业务员提交75℃需求并升级建单；本次演练限定接单参与人为R01，随后恢复身份表。AgentHub工具读取原单/会话和合成来源，导入candidate/proposed后把依据与候选保存回本单。取得固定审阅指纹后模拟研发在本单确认，再模拟内部范围批准。客户层查证缺口让现有觉提出 `qi_grant`；模拟研发授予后客户层能力仍是proposed，须模拟真人产品经理批准才active。

范围批准后原单仍待复用审定，不自动推荐。产品经理Agent的已有 `propose_reuse` 工具保存本单复用建议，`preparation_gap`确认对象内已有草稿后，模拟研发通过 `adopt_reuse` 签字；需求变为reused，复用事项结案，原会话收到产品及审定说明。业务员可见复用状态，客户推荐卡可见该句审定说明；本次不调用 `recommend_now`，也不新增自动回流规则。原单推荐依赖本单审定的statement，下一单依赖已批准的applicable，两者分别记录。

随后三个新会话分别检查75℃ confirmed、未知possible（待补temperature_c）、85℃无推荐且问用法时说明不适用；下一单未新增需求单。运行目录保存 `summary.json`、`report.md`、事件、会话、本单准备材料与知识状态。摘要包含实际工具轨迹、需求单/事项最终状态、两类能力编号、审阅指纹、模拟确认/批准次数、使用事件和配置；mock网关/System1及规则抽取/觉，模型调用数从计量统计。脚本驱动准备工具和模拟签字，不代表Agent自主规划或真人业务。最新运行：`data/knowledge_v10/validation/temperature-chain-69620705/`；真人专业范围与四岗位试用继续待办。

## 合成来源修改与复核

先运行上面的温度入口，再将其终端输出所对应的运行目录传入：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/run_v10_revision_chain.py --from-run data/knowledge_v10/validation/temperature-chain-3dc66943
```

命令中的编号是本地已通过样例，可替换成新的合成温度运行目录。入口只接受合成温度摘要，将状态与来源各复制成两个独立演示实例；输出为新的 `revision-chain-<编号>/`。复核对象取满足温度分支实际命中的applicable，不把原需求的单次复用statement当成适用范围。原合成状态及夹具只读，真实企业资料不参与。

两分支都先给75℃会话产生推荐，再修改引用片段、手工recheck，查看结论待复核、能力挂起、推荐撤回与qi_review。`restore`只将70—80℃连接符改为70～80℃，模拟研发显式审阅新指纹后签字，原能力恢复；`replace`把范围缩为70—74℃，模拟研发撤回旧判断，重新导入、审阅确认及授予，再模拟产品经理批准。后者旧能力持续挂起，75℃仍无推荐，72℃下一会话用新能力。

`summary.json`记录修改前后片段、新旧证据、挂起快照、总线中的复核最终状态、能力和使用事件；`report.md`对照两种处置。全部专业判断与签字合成，mock/规则运行，无模型实调；恢复后的原会话由脚本显式重匹配。此入口验证软件演示，不代表真实岗位复核或Agent自主准备已完成。

## 已核验开发题的证据读取核对

运行 `.venv/Scripts/uv.exe run --locked --no-sync python -m huayan.eval.reading_v10 --evidence <evidence.json> <另一份evidence.json>`。默认使用本地evaluations/questions.jsonl及verified_charts.json；核对记录可为多题列表，也可用`--gold`指定已有单题对象，须覆盖本次全部已核验题。金标只在eval侧核对，不进入检索工具。当前运行产物在data/knowledge_v10/validation/reading-evidence-b9adf6d8/，早先fd727f5a保留为单题历史运行。

当前可核对2题，其他33题保留未运行；5份资料9个已读页面中，既有关键词检索首位来源页命中2/2，事后指定的3个原生单元格一致。新增03-Q01已由开发者对照PowerPoint原生PNG、表格及XML核验，读取SRC-e8e260b85a第21页；同表在课件其他章节重复出现，本次未读取/索引整本198页。原单位、表头、条件和引用留在summary.json，predictions.json保留实际检索返回。这里只证明受控已读页集的证据查准与原生数据保真，模型回答可评分分母为0，不证明自主选行列、单位解释或问答正确率；线上模型与专业签字继续按用户安排暂缓。

本机新增来源使用manifest/lowcarbon-source.json的只读元数据，复用`scripts/read_pptx_slide.py --manifest data/knowledge_v10/manifest/lowcarbon-source.json --source SRC-e8e260b85a --page 21`读取。该元数据不含题目或答案，不在evaluations目录，读取器不接触评测金标；未将此来源登记进真实试用实例或指定研发归属。
