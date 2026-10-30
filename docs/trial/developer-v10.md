# V10 开发者走链

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

脚本仅在合成实例撤销旧的无温度限制种子，导入 candidate/proposed，取得实际审阅指纹后模拟研发确认，再模拟内部范围批准。客户层查证缺口让现有觉提出 `qi_grant`；模拟研发授予后客户层能力仍是 proposed，须模拟真人产品经理批准才 active。原会话显式调用 `recommend_now` 后取得推荐，随后三个新会话分别检查75℃ confirmed、未知 possible（待补 temperature_c）、85℃无推荐且问用法时说明不适用。

运行目录保存 `summary.json`、`report.md`、实际事件、会话与知识状态。摘要包含各阶段能力快照、审阅指纹、模拟确认/批准次数、使用事件和实际运行配置；本入口使用 mock 网关/System1及规则抽取/觉，模型调用数从计量记录统计。脚本没有测试Agent自主准备，没有创建升级需求单，也不声称验证其自动回流。真人专业范围与四岗位试用继续待办。

## 合成来源修改与复核

先运行上面的温度入口，再将其终端输出所对应的运行目录传入：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/run_v10_revision_chain.py --from-run data/knowledge_v10/validation/temperature-chain-3dc66943
```

命令中的编号是本地已通过样例，可替换成新的合成温度运行目录。入口只接受合成温度摘要，将状态与来源各复制成两个独立演示实例；输出为新的 `revision-chain-<编号>/`。原合成状态及夹具只读，真实企业资料不参与。

两分支都先给75℃会话产生推荐，再修改引用片段、手工recheck，查看结论待复核、能力挂起、推荐撤回与qi_review。`restore`只将70—80℃连接符改为70～80℃，模拟研发显式审阅新指纹后签字，原能力恢复；`replace`把范围缩为70—74℃，模拟研发撤回旧判断，重新导入、审阅确认及授予，再模拟产品经理批准。后者旧能力持续挂起，75℃仍无推荐，72℃下一会话用新能力。

`summary.json`记录修改前后片段、新旧证据、挂起快照、总线中的复核最终状态、能力和使用事件；`report.md`对照两种处置。全部专业判断与签字合成，mock/规则运行，无模型实调；恢复后的原会话由脚本显式重匹配。此入口验证软件演示，不代表真实岗位复核或Agent自主准备已完成。
