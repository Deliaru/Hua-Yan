# V10 已选负例的观察提议准备

入口消费已经开发者选定并核对过原页的负例报告，不自动搜索或判定失败。品质原文可能同时包含合格与不合格结果，均须保留；报告分析不提升为系统确认的因果结论。

在项目根目录运行当前样例：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/prepare_negative_ir.py --trial data/knowledge_v10/trials/SRC-fa320dba1c/trial-record.json --evidence data/knowledge_v10/evidence/SRC-fa320dba1c/evidence.json --product 'TF-213HE（LCY）' --seeds data/knowledge_v10/instance-first-report/seeds --out data/knowledge_v10/compiler/SRC-fa320dba1c
```

型号原词保留报告后缀，配合方案另附原文依据；不能因为基础型号已登记，就把试样版自动映射为同一产品。脚本核对TrialRecord和读取记录的来源/文件指纹，以及每条引用的当前块指纹和逐字原文，不调用模型、不写qi_state。

输出沿用 `operation-ir.json`、`proposals.json` 和 `review.html`。复用读取侧OperationIR，性质仍是observation；负例观察位于报告层，group为null，不把两种织物或混合品质结果冒认成工艺B组。条件中的A/B曲线仍保留各自组别，多织物配方表保持原列与原对象。提议form为null，温度适用范围为null，没有生成否定适用或新的能力形式。

用现有编译器执行内存预览：

```powershell
.venv/Scripts/uv.exe run --no-sync python scripts/compile_qi.py --config data/knowledge_v10/instance-first-report/app.yaml --ir data/knowledge_v10/compiler/SRC-fa320dba1c/operation-ir.json --evidence data/knowledge_v10/evidence/SRC-fa320dba1c/evidence.json --out data/knowledge_v10/compiler/SRC-fa320dba1c/compile-report.md
```

当前样例27项条件、28条依据，完整保留配方列、两组曲线、操作、结果分析及后续原文；未记载总节时/成本变化的待办继续保留。预览丢弃0条、待对齐1条，原因是本提议研发归属未分配、带后缀产品未对齐。当前没有导入候选、授予或专业签字。

后续归属及型号对齐后，继续沿既有候选导入与C7审阅机制办理，不在本入口绕过对齐、确认或授权；报告层IR尚未登记到真实实例的source_irs。原单消费入口现已支持报告层负例，正式导入必须通过HuayanApp或应用停止时的既有CLI入口。

原单接线复用 `save_source_preparation → compile_source_preparation`：group=null 的候选正文开头显示“报告层单次观察”，各条件分别标明A/B组、阶段或原文范围。未指定本人负责的提议沿原规则拒绝导入；已指定本人但型号未对齐时，编译报告的具体原因留在原单 compilation，claim_ids 仍为空。助手不得据此认领报告或把带后缀型号折叠到基础产品。

真实资料隔离记录位于 `data/knowledge_v10/checks/negative-preparation-499abcfa/summary.json`：合成需求保存28条真实依据及完整待补说明，随后因未指定本条归属被拒绝导入。临时来源可读归属仅用于隔离演练，不改真实清单；真实实例及IR未变、模型调用0、实际候选新增0、专业签字0。报告层候选入库的正向分支使用现有合成负例夹具验证，不能当作本报告已正式入库。
