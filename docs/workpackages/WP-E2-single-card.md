# WP-E2 单卡对照数据；阶段 2 的新决策注入与语言信号样本（T+16 决定）

> 负责：B｜时段：第 1 步 T+4～8（样例），第 2 步 T+12～16，第 3 步 T+16 之后且经人批准｜分支：`dev/b`
> 依据：`REPLAN-v5.md` 第 3.6 节（单卡对照）、3.7 第一幕、4.6 阶段 2、7.1 WP-E2 行；契约 v5.3

## 目标

1. 给演示第一幕和评测页一张**单卡对照**：同一张需求卡、同一个模拟客户，左边一次性翻译，右边化言，逐轮看到觉的追问概率，底部是研发会不会退回，再接 60 张卡三组统计。单卡是讲故事用的例子，底下的 60 张卡统计才是证据。
2. 阶段 2（T+16 由人决定做不做）：新决策（转译失真、对外泄密）的模拟注入与标签；语言信号样本，检验「读信息流」是否比只读属性有增量。

## 依赖

- 失真对照（WP-E，已在 main）；WP-C 第 1 步交付 `draft_product_need` 的输入与调用适配后，本包完成评测文件其余 v5 适配及逐轮记录，先交样例，再重跑正式结果。
- 新 Jue-K（WP-J 第 8 项）：化言组的追问、回问分别按 WP-J 的最终选择运行（赢了用 Jue-K，输了用规则），使用实际阈值。
- 评测链路使用模板客户、规则抽取与规则转译，觉按上一条选用本地模型或规则，零大模型调用；报告展示沿用 WP-C 的门面身份裁剪，不运行角色 Agent。

## 必读

`REPLAN-v5.md` 第 3.6、3.7、4.6、4.7 节；`WP-E-eval.md` 第 1 节（三组的定义与指标）；`docs/reports/distortion/README.md`；现有 `eval/distortion.py`、`scripts/run_distortion.py`。

## 允许修改的范围

`src/huayan/eval/distortion.py`（WP-C 负责转译调用适配，本包负责其余 v5 适配及逐轮记录）、`src/huayan/eval/single_card.py`（新）、`scripts/run_distortion.py`、`scripts/make_single_card.py`（新）、`config/eval/`、`docs/reports/distortion/`、`docs/reports/single_card/`（新）、`web/src/fixtures/single_card.json`（只此一个文件）、`src/huayan/ui/server.py`（只接入 `single_card` 报告并传查看者）、`src/huayan/app.py`（只补单卡报告读取与身份裁剪，复用 WP-C 的门面权限）；第 3 步另见该节。

不改：门面业务流程、Agent、`jue/`（打分来源只读配置）、`web/` 其余部分、契约。

## 交付物与已定设计

### 第 1 步（T+8 前）：单卡样例

WP-C 第 1 步交付后，在现有失真对照中按契约 v5.3 适配需求单（`assigned_rd`、`rd_accepted` 等）与 `requirement_state(..., events)`，真实跑一张卡，导出 `web/src/fixtures/single_card.json`，前端据此开发（WP-U2 第 4 项）。样例阶段觉可用规则打分，正式结果按 WP-J 的最终选择重跑；两次使用同一输出结构：

```
{
  "card_id": "...", "simulated": true, "phenomenon": "...",
  "truth": {"slot": "取值", ...},                       # 必问槽位的真值（模拟客户知道的）
  "one_shot": {                                          # G2：客户开场白 → 一次匹配 → 化学语言
    "turns": [{"speaker": "customer", "text": "..."}],
    "chem_lang": [{"text": "...", "quote": "..." | null}],
    "missing": ["slot", ...], "wrong": ["slot", ...], "returned": true, "return_reason": "缺：设备、浴比"
  },
  "huayan": {                                            # G3：觉提示追问 → L2 → L3 → 回问 → 回填
    "rounds": [{"turn": {"speaker": ..., "text": ...},
                "p_need": {"slot": 0.0 | null, ...}, "scored_by": {"slot": "rule" | "jue_k", ...},
                "threshold": 0.5, "asked": "slot" | null}],
    "back_asks": [{"slot": "...", "p_need": 0.0, "scored_by": "rule" | "jue_k",
                   "threshold": 0.5, "answer": "...", "changed": true}],
    "chem_lang": [{"text": "...", "quote": "...", "owner": "rd:R01"}],
    "missing": [], "wrong": [], "returned": false
  },
  "stats": {"G1 业务员转述": {...}, "G2 一次性翻译": {...}, "G3 化言": {...}, "n_cards": 60}   # 取 metrics.json，不另算
}
```

- `rounds` 记录觉的**追问**判断（每个必问槽位一列），`back_asks` 记录回问；分数、来源与阈值均取这次运行的实际输出。`p_need` 原样保留，前置条件未通过为 `null`，不预设规则分数为 0 / 1；`ScoredDecision.scored_by` 为空时按契约取 `JueOutput.scored_by`。前端按来源标「模型」或「规则」，规则来源不标概率。
- 文本全部来自模拟客户与种子，标「模拟数据」；不出现真实企业与产品。
- fixture 只供 WP-U2 开发；接真实接口后移除运行时引用，由 WP-I2 联调确认。

### 第 2 步（T+12～16）：数据接口与按新语义重跑

**1. `eval/single_card.py`：`single_card(card, trace, stats) -> dict`**
- 在 `run_distortion` 现有 G2、G3 链路中增加逐轮记录：`trace=True` 时同时返回统计行与按卡保存的轨迹；统计口径保持不变，数值以实际重跑为准。`single_card` 只把选中卡的轨迹与统计组装成上面的展示数据。
- 一次跑完 60 张卡，同时留下逐轮轨迹；选卡后直接取这次运行的轨迹，不重新生成客户对话或另跑该卡。追问、回问调用 WP-J 交付的觉实现，不在评测里另算分数。
- **选卡规则写死，不挑**：现象与演示主线相同（`color_unlevel`）、G2 被研发退回、G3 不被退回的卡中 id 最小的一张；报告里写明「60 张卡中有 N 张满足这个条件」，让单卡的代表性一目了然。没有满足条件的卡就照实展示第一张同现象卡，不改参数凑例子。

**2. `scripts/make_single_card.py`**：用上述 60 张卡的同一次运行生成 `docs/reports/distortion/` 与 `docs/reports/single_card/metrics.json`（即上面的结构）、一页 `README.md`，同时覆盖开发用 `web/src/fixtures/single_card.json`。复用 `run_distortion.py` 的报告导出代码，单卡底部统计直接取这次生成的失真报告。

评测页经 `report?name=single_card&viewer=...` 读取；接口将查看者传给门面，门面复用 WP-C 的身份校验，L2/L3 返回单卡明细，L1 只返回 `simulated` 与 `stats`。门面只读已生成的报告，不调用评测链路或读取需求卡；前端按返回内容展示。

**3. 按新语义重跑失真对照**：WP-C 改了 `draft_product_need` 的输入、WP-J 换了追问的打分来源之后，重跑 `run_distortion.py --n 60`，**替换**报告里的数字（变好变坏照写）；`README.md` 原有的两条如实说明（G1 噪声是假设参数；模板客户与规则抽取共用口语说法表，G3 的槽位错误率偏乐观）保留，再加一条「单卡是按固定规则选出的例子」。

### 第 3 步（阶段 2，T+16 由人决定；没批准不做）

人在 T+16 检查点决定做哪几项，再追加允许修改的范围（`src/huayan/sim/`、`data/week/`、`scripts/make_jue_k_data.py`、`docs/JUE_K_TRAINING.md`）。若沿用契约⑨的 `Injection` 清单，先由人扩充其 `family`：v5.3 仍只有原三类，觉的 `Family` 字符串化没有改变它。阶段 1 不改该契约。

- **新决策的注入与标签**：在模拟业务周里注入转译失真（L2 漏掉客户说过的约束、条目无原话）与对外泄密（说明书一句话换说法提到封存项）各几例，加对应的困难负样本（说法相近但没有泄露）；标签只给 `sim/`、`eval/` 读（铁律 5）。本项先测规则的命中 / 误报，结论写进报告；是否按 REPLAN D20 追加新增决策训练，由人在 T+16 一并决定并追加范围。
- **语言信号样本**：换说法的套问、同义不同词的需求、写在试样备注里的失败原因；每类正负各若干。比较「只读属性」与「属性 + 原始事件文本」两种 OneJev 题面（沿用探针 `probe_onejev.py` 的做法）：有增量才在材料里说「读信息流」，没有就照写没有（上一次探针的结论是证据无增量）。
- 两项的数字只进 `docs/reports/`，不进演示主线。

## 验收

1. T+8 前 `web/src/fixtures/single_card.json` 已合入 main，前端确认能直接用（结构见第 1 步）。
2. `uv run python scripts/make_single_card.py` 一次运行生成失真报告与单卡报告，同一种子重跑结果一致；大模型调用为 0。分数、来源、阈值与逐轮觉输出一致，单卡对话取自这次 60 张卡运行。
3. 评测页经 `report?name=single_card&viewer=...` 读取：L2/L3 能看单卡明细，L1 只得到统计；单卡底部三组统计与 `docs/reports/distortion/metrics.json` 一致。接真实接口后页面不再引用开发 fixture（WP-U2 接入，WP-I2 联调确认）。
4. 失真对照按新语义重跑，报告数字已替换，汇报里贴新旧对比表并说明变化原因。
5. 第 3 步（若做）：每项一页报告，结论按数字写，没有增量就写没有。

## 不做

单卡对照的界面（WP-U2）；为单卡调参或手写对话；用大模型跑单卡（演示第一幕要的是同一张卡上的对照，规则链路足够且可复现）；新增测试文件；阶段 2 没批准前的任何注入。
