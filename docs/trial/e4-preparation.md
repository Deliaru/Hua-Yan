# E4队友准备：判断复用边界配对

本轮按建设方案“先按每条判断编边界配对，再交研发标”交付，不代研发填写“同范围/条件未知/超范围”，不运行抽取、匹配或模型。配对的客户原话均明确标为合成；所依据判断来自已有真实资料，两个来源口径分别记录。

## 本地交付与使用

材料留在`data/knowledge_v10/evaluations/E4/`，不入库：

| 文件 | 用途 |
|---|---|
| `pairs.yaml` | 18条合成dev新需求及待填三分类，关联同一条applicable判断 |
| `knowledge-state.json` | 所选已有qi_state的原字节副本，固定标注依据 |
| `snapshot-origin.json` | 原路径、SHA-256、固定时间与签字性质说明 |
| `judgment-catalog.json` | 6条相关contributed记录的状态和编配对/未纳入原因；其中1条历史withdrawn、4条观察/说明、1条有applicable |
| `README.md`、`review.md` | 来源分母、边界清单及审阅入口 |

从项目根目录运行：

```powershell
uv run --locked --no-sync python scripts/prepare_reuse_pairs.py --out data/knowledge_v10/validation/E4-preparation-20261103

# JSON导出结果可回读，仍使用相同快照。
uv run --locked --no-sync python scripts/prepare_reuse_pairs.py --pairs data/knowledge_v10/validation/E4-preparation-20261103/pairs.json --out data/knowledge_v10/validation/E4-preparation-20261103/roundtrip

# 入库的独立合成夹具，仅用于文件流转回归。
uv run --locked --no-sync python scripts/prepare_reuse_pairs.py --pairs tests/fixtures/e4/synthetic-pairs.yaml --seeds tests/fixtures/mini_seeds --out data/knowledge_v10/validation/E4-synthetic-check
```

输出`pairs.json`为所选分区规范化附表，`details.json`逐条保留KU、能力、情境与limits原文，`report.md`可直接逐条审阅，`summary.json`记录提交号、词表/状态指纹和准备分母。JSON和YAML均可作为下一次`--pairs`输入，路径按项目根目录解释。

## 为什么只围绕一条适用判断

当前选定快照中，只有`ku:claim:5 / cap:1`有明确applicable情境。其余有效判断是现场观察、品质负例或statement用途，没有相应applicable，不能据此推导正向适用边界；另有一条withdrawn历史观察，不用于新需求。目录保留全部相关记录和原因，不声称已覆盖全部产品系列或所有判断形式。

所选能力的枚举、125–130℃闭区间和原文limits完整保留，不删限制凑“同范围”。能力受众为L3，配对的查看主体为现有研发账号；客户原话只是新需求输入，不能因为文字来自客户就宣称客户L0可用这项L3能力。真正运行时还需按实际授权主体使用知识视图。

历史账号签字已由项目记录澄清为开发者测试。快照中的active、confirmed_by和approved_by只是实际存储值，本项不会把它们称为真人专业验收。`signature_nature`与报告对此明示，professional_review始终pending；冻结副本也不是新建业务状态或办理确认/授予。

## 配对与标注规则

- 用`judgment_id`和`capability_id`关联；检查该能力必须为applicable且based_on包含该判断。状态指纹不符、关联错误或配对编号重复会拒绝。
- 新需求只填写`first_words`原话，不直接注入NeedState或枚举/温度结构。`design`记录为何编这条边界，不是专业答案；以后运行时仍须走既有抽取入口。
- `prepared_by/at`是草稿准备人/时间，和实际`labeled_by/at`分开。选择`expected`后必须填basis、实际标注人及带时区时间；字段完整仍只说明格式齐全，不能自动通过专业复核。
- 三分类为`同范围`、`条件未知`、`超范围`。判断须结合当时主体、完整条件、温度和原文limits；“超范围”针对这条判断，不自动表示整个产品永不可用。
- 完整枚举与范围内温度的样例也留空；带limits时不能预设confirmed。原文限制与未知须由专业人员判断，不能当成“不限”或用脚本预测替代金标。
- 所有同一资料/产品系列的配对保持同一source_group及分区，默认只处理dev。其他分区仅统计元数据，不解析/导出答案；显式`--split heldout`仅在正式评测时使用。合成预留样例不是未见集成绩。

18条草稿覆盖：完整枚举与128℃、缺面料、明确未知面料、另一面料、缺设备、另一设备、缺温度、明确未知温度、125/130℃两端点、125–130℃完整区间、126–129℃内部区间、124/131℃单值、两侧部分重叠区间，以及敏感色/低浴比限制和明确否定限制的对照。没有为这些设计预填三分类或候选结果。

本项检查只是文件准备：不会实例化HuayanApp、调用confirm/grant、读取模型或计算match_candidates。后续模型能力验证须使用当前配置的真实模型并记录实际调用；本轮的合成CLI回归、已知状态与未标注配对不能当作复用命中率或零容忍成绩。E4完成后停下等待审查，不进入E5。
