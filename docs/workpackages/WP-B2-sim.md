# WP-B2 模拟世界：需求卡、模拟客户、模拟业务周

> 负责：B｜时段：2:15–3:30（可与 WP-B1 同时开 Agent）｜分支：`dev/b`

## 目标
生成「藏着真实答案」的模拟需求和一段模拟业务周，供现场演示、Jue-K 训练和定时发现评测使用。这里的数据只能被模拟器和离线评估读取。

## 依赖
WP-0、WP-S（开发时先用小种子）。

## 必读
`CONTRACTS.md` 第 ①、⑦（Trial）、⑨ 节；`ARCHITECTURE.md` 第 8 节；`JUE_K_TRAINING.md` 第 4 节。

## 允许修改的范围
`src/huayan/sim/`、`prompts/sim_customer.md`、`scripts/make_sim.py`、`tests/test_wp_b2.py`

## 交付物与已定设计

### 1. 需求卡 `sim/cards.py`：`make_cards(seeds, n, rng)`
- 现象均匀抽样；槽位取值按 `slot_priors` 抽样，没有先验的均匀抽样；`unknown_slots` 以 10% 概率抽 1 个（不抽 `required` 中的第一个）；`opening_slots` 随机 0～2 个；`chem_savvy` 15%，其中一半 `wants_mechanism`。
- `truth_product = correct_product(...)`。整体上约 20% 的卡应升级（`None`），不够时调整抽样后在汇报中说明比例。
- 不调用大模型。

### 2. 模拟客户 `sim/customer.py`：`SimCustomer`
- 模板模式（默认，零成本）：`opening` = 现象口语说法 + `opening_slots` 的口语说法；`reply` 用 `detect_asked_slots` 判断被问了什么，按真值回答口语说法；`unknown_slots` 回答「这个不太清楚」；`wants_mechanism` 的客户在收到推荐后追问「原理是什么？是调 pH 吧」这类带术语的话。
- 大模型模式（`gateway` 不为 None）：caller `sim:customer`，提示词 `prompts/sim_customer.md`：只描述宏观现象，被问到才透露，不主动说化学术语（懂化学的客户除外）。演示中可选。

### 3. 模拟业务周 `sim/week.py`：`make_week(seeds, start, days, rng)`
5 个业务日，每天 9:00–18:00：
- **常规会话**约 100 次（每天约 20 次），由需求卡驱动，业务员轮流；
- **注入**（写进 `Injection`，`object_id` 按契约 5.1 格式）：
  - 机会汇聚：第 1～4 天，3～4 个不同客户共 5 次「同一现象 + 同一组必问槽位取值」且无已发布产品适用的会话（`earliest` = 第 2 次出现时刻，`latest` = 第 4 天结束）；
  - 知识冲突：第 2～4 天，某产品在其声称适用的某面料上 3 次试样失败、原因 `product`；
  - 泄露风险：第 3 天，某业务员 2 小时内 6 次换角度问同一产品的原理和配方（`query` 项）。
- **困难负样本**（也写进 `Injection`，`hard_negative=True`）：同一个客户就同一个无解需求反复咨询 3 次（都会升级，但只涉及一个客户）；同一现象 3 次但都有产品解决；1 次试样失败、原因 `equipment`；一个业务员正常地连续问 6 个不同产品的用法。
- 输出 `data/week/<week_id>/script.jsonl`、`cards.jsonl`、`injections.jsonl`。

### 4. 脚本 `scripts/make_sim.py`
`--seed --n-cards --week-days`，生成 `data/sim/cards.jsonl` 与 `data/week/w1/`；打印统计（现象分布、应升级比例、注入数）。

## 验收
1. `tests/test_wp_b2.py` 只有 1 个测试，覆盖两个不变量：
   - 同一种子生成两次，`cards.jsonl`、`script.jsonl`、`injections.jsonl` 完全一致；
   - 源码扫描：`src/huayan/` 下除 `sim/`、`eval/` 外，没有任何文件引用 `injections`、`NeedCard`、`cards.jsonl`、`truth_product`。
2. 手动：打印 10 段「模板客户 × 按提示追问的业务员」对话，人工看是否像真的（贴 2 段在汇报里）。

## 不做
Jue-K 的轨迹与标签（WP-B3）；运行业务周（WP-E）；通用仿真框架。
