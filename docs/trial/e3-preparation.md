# E3队友准备：已有报告的记录级金标草稿

本项按建设方案“用手上已有报告先写金标TrialRecord”交付。选择已有两页文本配方报告`SRC-35b83abc4f`，对照Microsoft Word 16.0 COM原生页图和python-docx底层段落独立转录，不以读取器的TrialRecord预测作为金标。它是已知dev材料的开发者草稿，研发复核pending，不是专业验收或未见样本成绩。

## 文件与入口

本地材料只留`data/knowledge_v10/evaluations/E3/`，不入库：

| 文件 | 用途 |
|---|---|
| `trial_records/SRC-35b83abc4f.json` | 复用现有读取侧TrialRecord格式的独立转录草稿 |
| `annotations/SRC-35b83abc4f.json` | 实际标注者/时间、来源分类/分区、输入文件SHA-256、原文limits与研发待复核状态 |
| `native-check/SRC-35b83abc4f.json` | python-docx直读段落、原生页图核对页码、表格/图表关系数量与原件副本指纹 |
| `review.md` | 本次逐项核对说明与原页链接 |
| `transcribe_selected_report.py` | 本份报告逐项转录记录，显式填写语义字段；仅供回查，不作为通用金标生成器 |

从项目根目录实际执行：

```powershell
uv run --locked --no-sync python scripts/prepare_trial_gold.py --record data/knowledge_v10/evaluations/E3/trial_records/SRC-35b83abc4f.json --annotation data/knowledge_v10/evaluations/E3/annotations/SRC-35b83abc4f.json --evidence data/knowledge_v10/evidence/SRC-35b83abc4f/evidence.json --out data/knowledge_v10/validation/E3-preparation-20261103
```

入口只检查Pydantic结构、原件/原生DOCX/页图内容指纹、来源关联、引用原句/片段指纹/页码，以及明确的A/B串组引用；带单元格的引用核对行列和原句。它不重新运行读取器，不判定字段专业语义是否正确，不证明页图生成方式，不输出字段准确率或零容忍成绩。报告中的引用数是出现次数，重复引用不算独立样本。

## 保真的处理

- A是原工艺、B是试样工艺；段落内部的A./B.指中深/浅色分支，不能据此重新分组。
- 两组各4项配方，分散染料X保留未知量和空单位。其余用量保留原数值与g/L，原句引用保留空格等写法，不做换算。未给浴比/布重，不计算总量。
- 两组多阶段工艺保留完整原句；两项明确的A组保温时间10分钟可单独记录，深浅分支分别保留。B组“不保温”保留原话，不改成测得0分钟。
- “度升”未写时间分母，不擅自补成℃/min。中深色每缸30分钟、浅色每缸20分钟分别留在结果原文；未列原/试样各自总时长，不填统一节时或做不成立的减法。
- 织物与设备已在共同条件中；未完全结构化的两组多阶段工艺及分色结果分别列为3条`limits`，逐字保留出处，不重复计算已单列的共同条件。
- 成本只写在目的中，实测成本列表为空；后续计划未记载也为空，均不填0。原报告署名与客户认可不代替这份金标的研发复核。

现有TrialRecord.extracted_by只允许`rule`，本次复用格式后保留这个固定值；它不表示运行了规则抽取，更不表示专业确认。金标的转录方法、标注者和复核状态以eval附表为准。`limits`也只在eval附表中，不增加冻结字段或修改读取侧类型。

## 后续使用边界

本轮只准备1份Word文本配方报告，没有扩写35题或补齐PDF/PPT/Excel/扫描件金标。原报告中无表格，python-docx读取表格数为0、底层chart关系数为0；本次不重新渲染，复用已保存的Office原生转换产物，并核对原件与副本指纹。

研发核对、其他真实资料到位以及模型/记录级评测不属于本轮。后续评测须先让读取工具在看不到金标的情况下产出预测，再由eval单独载入金标比较；需要模型能力验证时必须调用当前配置的真实模型，不能用这些准备检查或合成测试代替。原件、已有读取记录、正式知识状态与签字均不由本入口修改。
