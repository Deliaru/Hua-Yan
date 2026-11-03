# E6队友准备：旧流程参数访谈表

本项按建设方案“把old_flow.default.yaml的每项翻成一句可以直接问的问题”交付。已按用户要求执行`git fetch origin v11`，重新读取FETCH_HEAD并确认远端提交为`87f22c84c8e15a51e0c9fc17f0fab4d94b9565c1`，参数定义及消费实现与此前读取一致。固定该提交作只读参考，在v10准备问题；不移植推算器、前情耗时或界面。问题清单为`config/eval/e6-questions.yaml`。

## 文件与操作

本地材料在`data/knowledge_v10/evaluations/E6/`：

| 文件 | 用途 |
|---|---|
| `old_flow.default.yaml` | 原提交中参数定义的字节快照，数值全为假设 |
| `defaults-origin.json` | 参考提交号、原路径、SHA-256、固定时间及来源性质 |
| `interview.yaml` | 16项问题、原默认参考、口径、建议访谈对象和空白回答/来源位置 |
| `old_flow_cases.yaml` | 旧流程真实案例入口，当前cases为空 |
| `review.md`、`README.md`、`handoff.md` | 审阅入口、缺项和后续交接 |

实际参数覆盖位置为`data/pilot/old_flow.yaml`。本次确认原文件不存在后，仅创建`source: 假设`及空`minutes: {}`，没有数值覆盖；已有文件须保留，不以默认表覆盖。

从项目根目录运行：

```powershell
uv run --locked --no-sync python scripts/prepare_old_flow_interview.py --origin data/knowledge_v10/evaluations/E6/defaults-origin.json --out data/knowledge_v10/validation/E6-preparation-20261103

# 合成夹具：仅验证问题覆盖和假设标记，不是企业访谈数据。
uv run --locked --no-sync python scripts/prepare_old_flow_interview.py --defaults tests/fixtures/e6/synthetic-old-flow.yaml --seeds tests/fixtures/mini_seeds --out data/knowledge_v10/validation/E6-synthetic-check
```

输出为`interview-template.yaml`、无数值覆盖模板、`summary.json`、`report.md`和`details.json`。每个原参数路径恰好对应一个问题，缺漏、多项或重复映射会拒绝。`--origin`提供时核对原默认快照内容指纹。

该入口每次生成空白模板，不导入或认定访谈答案。请另存已填写表，例如interview-responses-日期.yaml，保留模板和原资料；不要用重新生成的空表覆盖回答。脚本不会写pilot或运行效率推算，本次pilot占位仅为一次本地准备。

## 数量与口径

16个原路径为10个`minutes.*`工位、2个小时项、3个比例和1个`source`来源元字段；15个数值默认均是假设，不是回答或业务案例。source不能当成第16个耗时数值。

- 工位分钟是该岗位实际动手人时，排除单独的交接等待；报价和开单、首次整理和补问分别记。
- `minutes.back_round`是整轮往返中各方动手分钟合计，不是只问研发一人，也不是整轮日历耗时。
- `wait_hours`是一次交接等待，需记起止事件、客户到业务员是否纳入口径、自然小时或工作小时。
- `trial_wait_hours`保留原定义“一轮试样从做样到拿到结果”。应注明是否包含做样动手时间；后续不能未经核对就与返工人时相加，重复计时。
- `sales_can_answer`分母是全部常规技术询问件数，分子是业务员可独立回答的件数。
- `return_rate`分母是进入研发的需求单数，分子是因条件不全补问或返工的去重单数；一单多轮不能当多件。
- `caught_by_rd`分母是这些条件不全的单，分子是研发开工前发现并回问的单，不能以全部入研单作分母。
- 比例填写0–1，同时记录原始分子、分母和同一观察期间；百分数60%对应0.6，缺少计数仍可记录为估计，不能冒充实测。

## 来源记录和参数覆盖

访谈表每项保留空白answer、answer_kind、实际respondent/answered_at、观察period、样本量和比例原始计数、evidence_source/quote。建议访谈对象是提问计划，不表示已联系或确认。

后续实际材料可按以下口径另记：系统可回查记录标“实测”；人员估计明确写估计者与岗位；尚未提供的数据继续保留“假设”，不能抄默认值作为回答。估计值也不是实测。

原消费方按override中**哪些数值字段已出现**判断是否仍是假设。因此无数据时覆盖模板只有source和空minutes，15个数值继续取原默认并保留假设身份。逐参数来源单独存在访谈表，不把额外的来源字段塞进旧参数结构；混合实测/估计的批次也不能靠一个全局source标签冒充全部实测。本轮没有实际回答，不执行任何估计或实测数值覆盖。

## 旧流程案例：字段与脱敏

当前真实案例0，`old_flow_cases.yaml`保持空表。本轮只列收集字段，不索取资料或编造案例：

| 字段 | 应记录的内容 |
|---|---|
| id / e1_case_id | 旧案例匿名编号及可用的E1关联；无关联时留空，不假配成同一件 |
| source / source_group / kind / split | 记录或口述来源、同一资料/产品系列分组、真实/还原性质及dev/heldout |
| labeled_by / labeled_at / basis | 实际整理/核对者、带时区时间及依据；准备者不代签 |
| first_words / later_conditions | 脱敏客户首句及后来补知条件，保留原意、数值和单位 |
| steps | 逐次岗位、匿名经手人、接收/开始/完成时刻、实际动手分钟及原记录出处 |
| handoffs | 每次交接双方、发出/接手时刻和回查记录，反复来回分别保留 |
| back_rounds / rework_rounds / reasons | 真实补问/返工轮数与原因，不拿期望比例反推实有轮数 |
| received_at / completed_at / calendar_basis | 从提出到完成的时间及自然/工作日口径；缺时刻用null，不填零 |
| evidence_refs / known_gaps | 原始资料位置/指纹和待核问题；口述、系统记录与重建信息分别标 |

客户和人员用稳定匿名码，脱敏映射仅留本地受控资料；同一人/单跨表保持一致以便去重。移除手机号、联系地址和无关身份信息，保留判断必要的工艺与条件；需遮盖的保密内容不对外发布，含原文材料全部留data。单据/事件指纹用于去重，不按姓名或一句相似原话合并案例。来自同一来源组的案例不跨开发/未见分区。

## 本轮边界

本项只有问题与参数来源准备：无访谈答案、企业实测参数、真实旧案例、事件耗时或提效百分比。既有业务/正式状态不改，不执行旧流程推算器或GET /api/old-flow，也不实现V11.4。模型调用0；后续如验证模型能力仍须用当前真实配置。本项完成后停在E6等审查，不进入E7。
