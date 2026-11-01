# V10 已处理试样记录受控汇总

此入口仅供开发者/研发本地审阅明确提供的TrialRecord，不接入客户页或Agent工具，不写正式知识状态。含内部原文的产物留在 `data/`，来源层级继承全部输入中的最高层级；不是专业确认或产品适用结论。

在项目根目录运行：

```powershell
$records = @(
  'data/knowledge_v10/trials/SRC-3a2130604c/trial-record.json',
  'data/knowledge_v10/trials/SRC-35b83abc4f/trial-record.json',
  'data/knowledge_v10/trials/SRC-fa320dba1c/trial-record.json'
)
.venv/Scripts/uv.exe run --env-file .env --no-sync python scripts/summarize_trials.py @records --product TF-213HE
```

默认从本地来源清单读取产品编号、标题与原件指纹，核对记录的来源指纹；同一原件SHA-256只计一份，重复输入另行列出。只消费已有记录，不扫描新报告、不重跑Office或模型。产品按清单编号精确筛选，型号后缀与配合方案仍须回原文确认。

默认输出 `data/knowledge_v10/trial-summary/`：

- `review.html`：条件、结果、时间、成本并列表，可回到单份审阅包和原页。
- `summary.json`：完整记录、原始引用、筛选条件、去重清单及计数。
- `summary.csv`：同口径文本表格，供本地筛选。

用 `--condition` 和 `--result` 做原文字面筛选；条件覆盖共同条件、操作、配方说明以及各组已读配方/曲线引用原文。配方/曲线依据在导出中标明A/B组及出处指纹、页码、单元格。三种筛选同时提供时须同时满足。例如查某种织物的品质负例：

```powershell
.venv/Scripts/uv.exe run --env-file .env --no-sync python scripts/summarize_trials.py @records --product TF-213HE --condition 300双面无光 --result 不合格 --out data/knowledge_v10/trial-summary/negative-readback
```

命中的是整份报告，须继续看织物对应条件和完整结果；不能把同报告中的合格样本也算成失败。缺失时间/成本不补零，原文未结构化的分条件结果仍原样显示。

当前三份样例中，只有首份具有可核对的A/B标注升温总时长，另外两份分别是分条件节时原文和未记载总节时。汇总显示这一口径的纳入份数和来源，不跨织物/工艺求平均、合计或计算成功率。这个数量也不表示整份报告的所有条件均已核验。

本轮已用三份实际记录核对汇总问题，并重复输入负例验证去重；查询答案与出处记录在本地 `data/knowledge_v10/trial-summary/readback.md`。全部输入仍为草稿、未专业确认；开发者原文对照不替代真人签字。

2026-11-01最新汇总使用专家意见版正例、负例记录，另外保留原文本配方记录。新入口为`data/knowledge_v10/professional-review/expert-feedback-20261101/trial-summary/review.html`，其`check.json`保存三份报告、一个A/B标注总时间分母、配方单位/曲线条件/品质负例筛选及重复输入核对。B组补充单位指向专家答复，A组未知单位保持；两份新记录已配置进工作面，但记录仍draft、候选未系统确认。旧汇总与其readback保留为历史输入结果。
