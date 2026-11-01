# 专家书面意见后的记录与候选草稿

2026-11-01，归口 V10.4 / V10.5。书面专业意见已经收到，系统确认、授予、产品范围批准和发布分别办理。

## 本机材料

- 定稿输入：`data/knowledge_v10/研发专家核对包/03-研发专家核对答复（已确认定稿-20261101）.md`。使用补充核实后的温度答复，不从原表单占位符推定专业意见。
- 新审阅包：`data/knowledge_v10/professional-review/expert-feedback-20261101/review.html`。
- `expert-source/` 保存定稿字节副本、分项依据和指纹，沿用现有 `EvidenceBlock` / `Fragment`，内部 L3。
- `trials/<来源编号>/` 为两份更新后的 `TrialRecord` 和原图审阅页；`compiler/<来源编号>/` 为观察 IR 及编译预览。
- `proposals.json` 使用既有 `Proposals` 格式，含两份报告观察、认可的对外话术、正式适用范围及负例风险判断，共五项。话术先作结论草稿，不扩展编译器的能力形式。
- `compile-preview.json` 保存内存中的五条 candidate 和一条 L3 proposed 适用提议。编号只用于预览，不能当作正式实例的新编号。`summary.json` / `check.json` 保存输入指纹和核对结果。

## 处理边界

- 配方问卷展示的是 B 组，两项染料单位只在 B 组补充，并同时引用原表与专家答复；A 组未知单位保留。报告原文、模型稿和原生图均不改写。
- B 组曲线的书面核对意见独立保存，不宣布 A 组曲线或全部模型辅助稿已核验。
- 试样保温点与正式适用温度是两种判断，分别保留。正式范围采用定稿确认的 125–130℃及全部限制，不由一次试样向外扩展。
- 设备先用现有词表表达专家明确包含的溢流染色机，其余设备描述保留为限制，不映射到所有设备。
- 负例原型号后缀、同浴背景及同次合格对照保留；产品归属对齐有专家答复作为依据，不推成单一助剂的普遍因果结论。
- 对外话术的后续授予草稿按业务员层准备，未自动扩大为客户自助层授权。前置追问只是专业建议，本项不生成新的 ask 能力。
- 草稿记录仍为 draft，未填写系统专业确认字段。原实例的撤回结论不恢复，正式状态、来源清单和已有读取产物不覆盖。

## 本机复现

从项目根目录运行，环境变量由 `.env` 注入，准备脚本和原文均只留不入库目录：

```powershell
uv run --env-file .env python data/knowledge_v10/professional-review/expert-feedback-20261101/prepare.py
uv run --env-file .env python data/knowledge_v10/professional-review/expert-feedback-20261101/check.py
```

`preview-config.yaml` 仅供编译预览，包含原报告和专家意见各自的来源，运行目录独立。两份观察可分别用已有 `scripts/compile_qi.py --config <preview-config.yaml> --ir <operation-ir.json> --evidence <原报告evidence.json> --out <compile-report.md>` 检查，不传 `--state`。多来源引文按每项指针中的文档编号回取，不将专家答复当作原报告片段。

## 下一小项

先由用户评审此包。通过后再把专家依据及新稿接入现有工作面，通过 `HuayanApp` 导入候选并重新取得实际审阅指纹；正式确认、用途授予、产品范围批准与发布仍交有权人员。不能把本项的内存预览计为上述动作或下一单复用完成。
