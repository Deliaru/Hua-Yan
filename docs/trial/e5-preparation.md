# E5队友准备：合成对抗提问与正常对照候选

本项只按建设方案“先编对抗提问（标合成）”交付，附正常提问对照候选和待填金标位置。24条均为新编合成dev输入，非真实客户套话或企业业务问答；其中18条对抗、6条正常候选、2条多轮。没有助手回复、专业泄密金标或公开应答答案。

## 本地材料与操作

文件只放`data/knowledge_v10/evaluations/E5/`：

| 文件 | 用途 |
|---|---|
| `prompts.yaml` | 合成问题、拟角色/出口、多轮顺序、准备信息与待填金标 |
| `prepare_prompt_drafts.py` | 本批逐条显式编写记录，不是模型生成器或业务执行器 |
| `review.md` | 分组审阅入口 |
| `README.md`、`handoff.md` | 来源分母、已知缺项和交接要求 |

从项目根目录运行：

```powershell
uv run --locked --no-sync python scripts/prepare_leak_prompts.py --out data/knowledge_v10/validation/E5-preparation-20261103

uv run --locked --no-sync python scripts/prepare_leak_prompts.py --prompts data/knowledge_v10/validation/E5-preparation-20261103/prompts.json --out data/knowledge_v10/validation/E5-preparation-20261103/roundtrip

uv run --locked --no-sync python scripts/prepare_leak_prompts.py --prompts tests/fixtures/e5/synthetic-prompts.yaml --seeds tests/fixtures/mini_seeds --out data/knowledge_v10/validation/E5-synthetic-check
```

导出`prompts.json`可回读；`details.json`保留完整逐条元数据，`report.md`按轮次展示草稿；`summary.json`记录提交号、词表指纹、来源分区及拟观察出口计数。默认只处理dev，其他分区只核对元数据，不解析或导出答案。同来源/产品系列使用同一source_group并保持同一分区，合成预留例不称为未见集成绩。

## 设计覆盖和身份

| surface | 拟观察内容 | 拟绑定role |
|---|---|---|
| customer_answer | 给客户的回答 | customer（L0） |
| sales_workbench | 业务员工作面 | sales（L1） |
| sales_history | 业务员前情 | sales（L1） |
| sales_agent | 业务员助手回答 | sales（L1） |
| recommendation_evidence | 推荐中的依据 | customer或sales |

这些字段是后续观察计划，不是已经接通的HTTP执行入口，也不代表五类出口已通过测试。工作面/前情不是任意提问接口，后续须按真实业务动作触发再收集可见内容。role同样只指定测试拟使用的主体，真正身份须由服务端会话/ToolContext认定；题中“我是研发”“领导批准”等自称不能改变角色。

对抗方式包括直接问配方/比例、组分换说法、竞品差异、分轮拼凑、研发/领导身份声称、报告原文、编码/翻译、业务员助手代问、工作面/前情渲染及推荐内部依据。问题本身不附真实配方、成分比例或内部原文答案。

turns只存用户输入，保持顺序。多轮实际运行必须使用模型真实先前回复；不能把预编助手答复注入历史或分拆成独立单轮后宣称验证了多轮泄露。本项不执行这些提问。

## 专业标注位置

| 字段 | 含义 |
|---|---|
| prepared_by / prepared_at | 草稿实际准备者/时间，与专业标注人分开 |
| review_focus | 为什么编这题、建议核对什么，不是禁出金标 |
| forbidden | 对抗题待确认的禁出内容；当前null，不等于没有秘密或应当回答 |
| public_points | 正常题待核定的公开应答要点；当前null，不承诺确有公开答案 |
| gold_source / basis | 真正金标所依据材料的位置/版本或指纹，以及专业判断理由 |
| labeled_by / labeled_at | 实际标注人及带时区时间；不能使用草稿准备者冒充研发 |

未知金标用null；填写对应金标时须提供非空内容、来源、理由、实际标注人和时间，不能把空列表当成已完成。字段齐全仅说明格式，报告仍标专业复核pending，不自动取得确认或授权。

正常题的公开用途、用法、使用用量范围、适用面料等，须先核对当时已发布、该主体可用的资料与具体条件。公开使用用量不等于配方比例；不能把所有提到“用量”的问题算攻击，也不能用未核定的公开要点计算过度拒答率。业务员本单原话/进展也须先核实际归属与可读上下文。

## 真实执行留待后续

本轮没有装载真实L3/配方知识库，没有门面/助手调用，也不执行leak_hits。泄露数、零容忍发现和过度拒答率均未评估，不填0次泄露或达标比例。

后续执行需要固定实际知识状态与合法主体，仅把用户提问送入业务链路，不能把forbidden/public_points金标送给助手。需要模型验证时使用项目已配置的真实模型，记录实际型号、调用与全部可见输出；按既有leak_hits初查后仍须人工审查全部输出，包括改写和多轮聚合。自动规则未命中不能当作不泄密证明。配方永不对外、未授予L3不能跨层披露的现有边界保持。

专业确认、真实套话收集及执行评测不属本轮；本项完成后停在E5，等待审查，不进入E6。
