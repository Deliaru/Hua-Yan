# E8队友准备：演示副本的变更与复核

本项直接复用现有`HuayanApp.recheck_evidence → compile.recheck → kb.evidence_changed → qi_review`链路，准备并实际运行4个合成变更。没有新版本系统、自动专业裁决或真实资料修订；全部范围、确认、批准、复核签字由开发者在独立合成实例中模拟，研发复核仍pending。

## 样例与预期

| 变更 | 具体修改 | 开发者合成预期 |
|---|---|---|
| SYN-E8-condition | 引用p1温度70—80℃改为70—74℃ | 原温度判断受影响、能力挂起；旧判断撤回，重建新范围 |
| SYN-E8-unrelated | 未引用p2归档备注甲改乙 | p1判断不受影响，无复核事项 |
| SYN-E8-whitespace | p1段首尾增空格 | 现有FolderSource.strip后正文/指纹不变，不挂起 |
| SYN-E8-typography | p1的70—80℃改为70～80℃ | 指纹变化先挂起；合成复核认为闭区间含义仍成立，显式新指纹恢复 |

这是开发者写明的合成预期，不是企业研发金标。纯格式样例只代表段首尾空白，不能扩为任意Office格式或排版变化均不挂起。连接符样例说明文本指纹变化与语义变化不同：系统先保守挂起，再由模拟复核恢复，不添加自动语义归一化。

每个样例另有synthetic-control独立来源的已确认观察，作为不受影响对照。正文中无企业配方、真实试样或真实范围；同一合成来源组均为dev，不称未见样本。

## 入口与文件

入库夹具在`tests/fixtures/e8/`，包括两份明确合成文本及synthetic-changes.yaml；此金标清单只由eval使用。运行入口：

```powershell
# 只准备输入，status=not_run，不验证模型或状态链。
uv run --locked --no-sync python scripts/prepare_source_changes.py --out data/knowledge_v10/validation/E8-input-example

# 实际门面状态链；使用当前真实应用配置构建组件，不调用模型推理。
uv run --env-file .env --locked --no-sync python scripts/prepare_source_changes.py --config config/app.online.yaml --out data/knowledge_v10/validation/E8-new-run
```

输出目录须为新路径，不覆盖已有证据。每例把源文本复制到自己的sources目录，在全新run_root、qi_state=null下调用HuayanApp；mini_seeds替代真实企业资料。真实模型配置中的mock/fallback/replay会拒绝，原外部sources/source_manifest/trials/IR全部换为合成副本或置空。原件与共享试用状态不参与。

每例通过门面导入候选、显式审阅确认和产品经理范围批准建立内部L3适用能力；仅在这个全新实例内撤销同产品的默认种子能力以免掩盖效果。确认和批准仍分开，状态写入只由HuayanApp完成。

| 产物 | 含义 |
|---|---|
| changes.json | 输入的规范化合成变更及预期，可作为后续准备输入 |
| summary.json / report.md / details.json | 代码、输入/词表指纹、分母、实际核对与运行口径 |
| 各样例source前后文本（prediction.json内） | 副本的具体修改，不改原夹具 |
| 各样例after-recheck.json | 实际changed名单、KU/能力状态、qi_review与75℃匹配 |
| 各样例prediction.json | 实际复核前后证据指纹、旧能力、新判断与72/75℃结果 |
| 各样例runs/synthetic-change | 原始事件、总线、计量、独立qi_state等 |

本次最终报告目录为`data/knowledge_v10/validation/E8-preparation-20261103-final`；前一轮相同样例运行保留在`E8-preparation-20261103`，没有清空覆盖。

## 复核与使用检查的边界

条件变更与连接符变更均实际得到candidate KU、suspended能力和1条qi_review；变化发生到显式recheck之间不声称实时检测。挂起后使用研发当前`kb.view(actor)`配原`match_candidates`，固定的合成75℃条件不能命中该能力。

连接符恢复分支把`review_claims`取到的新指纹显式传给复核签字，核对复核事项resolved、原KU/能力恢复active、证据指纹确实更新且75℃仍用同能力。收窄分支撤回旧KU、保留旧能力suspended，再导入新candidate/proposed、确认与范围批准；核对复核事项结案、新KU不同，75℃无候选、72℃用新能力。

这些输入是固定结构条件，用于验证来源失效后的能力视图与既有匹配语义。没有客户会话、原话抽取、推荐模型回答或capability_used事件，不称完整“真实下一单使用”验收；L3能力也没有授予客户。结构匹配结果中的confirmed是当前函数返回值，不是企业范围确认。

读取/复核不需要模型推理。本次抽取、Jev和助手未运行，qi_review由规则觉提出（scored_by=rule），真实模型组件仅构建、不发请求，模型调用0。没有用mock模型输出验证模型能力。

预测状态先写prediction.json，再由eval比对expected_affected和复核预期；金标不提供给编译/recheck/知识库或角色助手。模拟review_action是脚本的人工处置安排，不是模型选出的专业结论。

报告只计本次受影响阶段的结构匹配不符次数，不扩为所有业务出口的零错误证明。其他专业复核、真实资料变化、未见样本仍待完成；E8交付后停止等待审查。
