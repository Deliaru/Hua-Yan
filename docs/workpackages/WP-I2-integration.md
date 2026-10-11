# WP-I2 集成：新主线台词、沿界面路径录制与回放、检查点载入、全量测试

> 负责：A + B（A：接口层、回放、检查点；B：台词、触发点核对、Jue-K 接入）｜时段：T+16～24｜在 `main` 上进行
> 依据：`REPLAN-v5.md` 第 3.2（硬性要求 1）、3.7、4.3、7.3（录制缓存风险）节；契约 v5.3；WP-C、WP-J、WP-U2 的交付

## 目标

把 WP-C（门面与 Agent）、WP-J（觉）、WP-U2（界面）接成一条能现场演示的主线，满足三件事：

1. **主线只由觉的决策和人的签字推动**（铁律 14）：台词里只有人做的事——客户说什么、业务员发什么、人对 Agent 说什么、人按哪个签字按钮；Agent 的准备全部由觉提出问题后 `tick` 派单产生，台词里不写。
2. **录制与回放走界面同一条调用路径**：v4 的教训是界面逐次 `tick` 与命令行合批派单顺序不同，缓存对不上。本包让脚本直接调用 `ui/server.py` 的同一组接口函数，录制、回放、界面现场操作三者调用顺序完全一致。
3. **检查点 = 台词前缀的回放**：载入检查点就是新开一轮，用录制缓存把台词跑到该处；不序列化门面状态，不用离线桩，Agent 草稿与现场一致，不带「离线」标注（REPLAN 3.7）。

## 依赖

WP-C、WP-J 第 1～2 步合入 main（T+16 检查点打通「升级 → 接单 → 确认 → 评价 → 封存 → 发布」）；WP-U2 接真实接口；WP-J 第 8 项（新 Jue-K）与 WP-E2 第 2 步可在本包期间合入，影响主线模型请求的变更按第 5 项重录。

## 必读

`REPLAN-v5.md` 第 3、4.3、7.2、7.3 节；`CONTRACTS.md` 第 ④（Jev 与 OneJev）、⑩（网关与缓存）、⑫、⑭ 节；WP-C 第 2 步第 5 项（接口清单）；现有 `ui/server.py`、`gateway/client.py`、`jev/system1/onejev.py`、`scripts/demo_mainline.py`、`demo/mainline.yaml`。

## 允许修改的范围

`demo/mainline.yaml`（重写）、`scripts/demo_mainline.py`（重写）、`src/huayan/ui/server.py`（共享 `Api.call` 与路由表；新增 `demo/*` 三个接口）、`src/huayan/gateway/client.py`（只加严格回放开关与缓存未命中报错）、`src/huayan/jev/system1/onejev.py`（只补录制/回放与回放时跳过探活）、`src/huayan/app.py`（只挂接两种客户端的缓存与回放开关）、`config/app.demo.yaml`（新）、`config/app.yaml`（只改 `realtime_model` / `scheduled_model`）、`seeds/`（只为主线触发点补数据，标「（模拟）」）、`runs/demo_record/`（新缓存目录与说明）、`README.md`（命令与复用说明）、集成中发现的问题按归属改各包的文件并在汇报里列出。

不改：契约；`web/` 的界面结构（只修联调问题）；模板前置条件（触发点不成立先查数据与台词，确需改模板交给 B 并写进汇报）。

## 交付物与已定设计

### 1. 接口层可在进程内调用（A）

- `ui/server.py` 的接口函数改为接收 `app` 参数，按现有 GET/POST 表路由；HTTP 处理只做解析、调用 `Api.call`、序列化与错误映射。
- `Api(app).call(method, path, params)` 是 HTTP、脚本与检查点的同一个操作入口：**业务写操作前时钟前进 1 业务分钟，操作后调用一次 `app.tick()`**；读操作不推进时间、不派单。路由函数与 HTTP 处理不再单独调用 `tick`。
- 服务进程用 `SimClock(T0)`；新开一轮先设置新时钟与新门面，检查点在此基础上经 `Api.call` 回放台词前缀；`reset` 与 `demo/load` 不再额外执行外层的时钟推进或 `tick`。
- 演示主线只用上述 1 分钟规则，去掉可选的跨日 `advance`；试样直接模拟录入。这是演示时间压缩，写进简化清单；模拟业务周的时间推进不变。

### 2. 回放（A）

- `config/app.demo.yaml`：种子 `seeds/`；`gateway_mock: false`；`system1_impl: onejev`（D18）；`extractor: llm`；`realtime_model` / `scheduled_model` 取 WP-J 第 8 项的结论（新 Jue-K 赢的类用 `jue_k`，其余在 `jue_k` 模式里回落规则，不回落 OneJev）；`llm_cache_dir: runs/demo_record/llm_cache_v5`；`replay` 由命令行或环境变量切换。
- 大模型网关沿用现有录制缓存；OneJev 在同一缓存目录的 `s1/` 下保存请求与响应，以 caller 与实际请求内容（模型、state、media、questions）的确定性序列化计算缓存键。复用现有 `replay` 开关，不新增回放框架。
- `replay: true` 时两种客户端都只读缓存，**缓存未命中直接抛错**（`ReplayMiss`，消息带 caller），初始化 OneJev 也跳过 `/health`；`replay: false` 时缓存未命中才发真实请求并记录结果。输出注明命中的 caller 与来源（网关 / OneJev），状态条显示「回放」。Jue-K 本地推理不进这两种缓存。
- 旧缓存 `runs/demo_record/llm_cache/` 全部作废（触发时机变了），保留目录只为对照，`README.md` 说明。

### 3. 台词 `demo/mainline.yaml` 与运行器 `scripts/demo_mainline.py`（B 写台词，A 写运行器）

台词只有人的动作，每个动作对应一个接口：

| 动作 | 接口 | 说明 |
|---|---|---|
| `start: {session, customer, sales}` | `sessions`（POST） | 开会话，返回的会话 id 绑定到台词中的 `session` 别名 |
| `customer: {session, text}` | `turn`（speaker=customer） | 演示者扮客户 |
| `send: {session, text?}` | `turn`（speaker=sales） | 不写 `text` = 发出当前 `reply_draft`（Agent 起草的）；经过发送拦截 |
| `chat: {actor, text, session?, focus?}` | `agents/chat` | 人在「与 Agent 协作」里说的话；业务员带绑定的客户会话 |
| `sign: {actor, action, args}` | 签字类接口（`escalate`、`reuse/adopt`、`merge`、`accept`、`confirm`、`contribute`、`market-eval`、`points`、`release`、`decrypt/*`） | **签字前断言**：该对象上对应 family 的问题 open、`prepared_at` 不为空、签字人是 `actor`；不满足就停下并打印觉此刻对该对象的判断（铁律 14 的现场检查） |
| `edit: {actor, path, args}` | 草稿修改接口（`req-item`、`reuse-note`、`sheet` 等） | 人直接改 |
| `approve: {actor, tool}` | `agents/approve` | 只用于对话里 Agent 提议的生效动作 |
| `trial: {req, passed}` | `trial` | 模拟 ELN 录入 |
| `checkpoint: <名字>` | — | 标记检查点 |
| `expect: {...}` | 读接口 | 断言（如「研发收件箱只有现成产品审定」「L1 命中 新品」），失败即停 |

`sign.args` 只指定对象、条目索引与人的判断（如客户评价结果）；沉淀、封存 / 放出等内容从签字时的当前草稿读取，台词不预写 Agent 应生产的正文。研发的窗户纸通过 `edit` 或 `chat` 提供，Agent 再提炼。

主线（REPLAN 3.7，B 按真实种子定台词）：追问 → 升级 → 产品经理 Agent 查无现成产品 → 第二位客户同类升级 → 查无 → 机会汇聚到点 → 产品经理 Agent 判断同一件事、起草合并 → 研发签字合并 → 重新起草 L2 → 研发接单（打开「知识与积分」）→ 研发 Agent 起草 L3 → 回问 → 客户回答 → 研发改一条、确认 → 沉淀 → 试样（模拟 ELN）→ 客户评价 → 封存 / 放出 → 产品经理 Agent 包装 → 发布 → 新客户在 L1 命中新品。**D17 支线**单独一段：另一现象 → 升级 → 产品经理 Agent 找到 P01 案例里的现成产品 → 研发审定（改一个词）→ 业务员拿到说明并转述（C15）。

检查点至少：`研发待接单`（合并之后）、`回问待答`、`封存待签`、`支线·现成产品待审定`。

运行器三种模式：
- `--record`：现场配置，`replay: false`，按台词跑完并写缓存；打印每一步的觉判断（family、对象、`p_need`、`scored_by`）、Agent 的 `/trace` 摘要、签字人。
- `--replay`：两种客户端都设 `replay: true`，同一台词再跑一遍，零真实模型请求且不探活；结束时比较两次的事件序列（忽略 `id`）一致。
- `--until <检查点>`：只跑到该检查点（检查点载入复用它）。

`test_e2e` 仍是 WP-C 写的离线最小主线（`gateway_mock: true`，小种子），本包只让它通过，不改成回放。

### 4. 检查点与「下一句」接口（A）

- `GET demo/checkpoints`：台词里的检查点列表。
- `POST demo/load {name}`：以 `SimClock(T0)` 和回放配置新建门面 → `Api.call` 跑台词到该检查点 → **两种客户端一起切回现场**（`replay: false`，缓存仍开着：照台词操作命中缓存，演示者临场改的话走真实模型）。界面从这里继续；载入本身不再多走一次业务操作的时钟推进或 `tick`。
- `GET demo/next?session=`：该会话在台词里下一句尚未出现的客户发言，界面「下一句」按钮把它填进「客户说」输入框（REPLAN 3.2 硬性要求 1）；由人发出，可改。
- 三个接口只读台词与缓存，不绕过门面；界面上的「载入检查点」只在服务以 `app.demo.yaml` 启动时出现。

### 5. 触发点在真实种子上核对（B）

- 用 `--record` 在 `seeds/` 上跑主线，逐个确认 REPLAN 4.3 每个推进决策在台词预期的位置到点；**回问**要在 L2 或 L3 起草时真实出现（槽位：主线客户台词都没提、且在该现象下改变转译；种子不够就在 `seeds/translations.yaml` 补 1～2 条 L3 转化对照，标模拟）；**机会汇聚**要在第二张单查完复用之后才到点（WP-J 第 1 项口径）；D17 支线研发只有 `reuse_product` 一项。
- 贴一张「台词步 → 觉提出的问题（family、`scored_by`、`p_need`、提出 / 准备完成 / 签字的业务时间）→ 签字人」表。
- 新 Jue-K，或影响主线模型请求的接口、提示词、种子变更合入后重录（录制成本贴在汇报里）；仅 WP-E2 报告数据更新不触发重录。
- WP-E2 报告接入后确认：单卡明细由门面按身份返回，业务员只看统计；前端已移除开发 fixture 的运行时引用。

### 6. 交给 WP-D2 的材料

- `runs/demo_record/transcript_v5.md`：录制那次的全部对话、Agent 草稿、签字与觉的计数（`n_judgments`、`n_llm_calls`、`n_questions`、`n_signatures`）；
- 录制费用与调用次数（只汇总录制那次的 `metering.jsonl`；回放记录不作为新增费用的依据，不为缓存命中改计量契约）；
- 简化清单：两位客户由同一业务员 S01 负责；合并单的回问派到主单首个会话；演示每次业务写操作推进 1 分钟、试样直接模拟录入，研发耗时被压缩；推进类决策由规则到点；模拟周处置由脚本决定；L2 知识本次不增长；研发之间共享知识列为后期。
- 只用本次重跑的数字；`jue_proto` + OneJev 跑过的部分不说「零模型调用」。

## 验收

1. `uv run pytest` 全部通过（≤ 11 个测试）。
2. `uv run python scripts/demo_mainline.py --record` 在 `seeds/` 上跑完主线与 D17 支线，每个 `sign` 前的断言都成立；贴第 5 项的表。
3. `--replay` 真实跑完：核对网关与 OneJev 均从缓存读取，初始化不访问 `/health`，两次事件序列一致；未命中时报错，不发真实模型请求。直接用运行输出与请求路径核对，不要求新增 `cached` 计量字段。
4. 界面：服务以 `app.demo.yaml` 启动，载入每个检查点后照台词在界面上操作到下一个检查点，网关与 OneJev 全部命中缓存；临场改一句话能走真实模型并继续；录屏放 `docs/assets/demo/`。确认单卡报告按身份展示，正式页面不再读取开发 fixture。
5. 状态条如实显示：现场 / 回放、觉的模式、Jev 实现、抽取器；Agent 草稿上没有「离线」标注。

## 不做

演示脚本与材料（WP-D2）；新功能、新决策、新工具；剧本播放器（台词只给「下一句」和检查点，人按按钮）；序列化门面状态的快照；为回放写新的桩或测试；缓存计量字段改造；跨日时间控制入口。

## 完成情况（2026-10-11 收尾，A 线停止后由 B 接手）

| 验收 | 结果 |
|---|---|
| 1 | `uv run pytest` 11 passed |
| 2 | A 的录制 `run-1a432a62f626` 在 `seeds/` 上跑完主线与 D17 支线，11 个 `sign` 前断言全部成立；第 5 项的表见 `runs/demo_record/README.md`「触发点核对」 |
| 3 | `--replay` 在无 OneJev、无网络的环境下跑完（约 5 秒），网关与 OneJev 全部命中缓存，初始化不探活，事件与录制逐条一致；缓存外的请求抛 `ReplayMiss`（带 caller），不发真实请求，回放全程不需要密钥 |
| 4 | 接口路径：四个检查点经 `Api.load_checkpoint` 载入后切回现场，从每个检查点按台词走到下一个检查点全部命中缓存；A 已验证临场改写 pH 答复走真实模型并继续。单卡报告由门面按身份返回，前端运行时不再引用开发样例。另以 `app.demo.yaml` 起 HTTP 服务（OneJev 经转发在线）核对：状态为现场、检查点列表、`demo/load` 载入「研发待接单」「回问待答」「封存待签」后收件箱与需求单摘要正确、`demo/next` 给出下一句客户台词。浏览器录屏只有 A 的联验证据（`docs/assets/demo/wp-i2-a/`），新缓存下「封存 → 发布」「复用 → 发送」两段未在浏览器里重走，正式演示视频随 WP-D2 |
| 5 | 状态条显示现场 / 回放、觉的模式、Jev 实现、抽取器；Agent 离线时草稿才标「离线 · 规则生成」 |

第 6 项交给 WP-D2 的材料：`runs/demo_record/transcript_v5.md`（对话、草稿、签字）、`runs/demo_record/README.md`（觉的计数、录制调用次数与费用、简化清单）。

集成中顺带修改（按归属列出）：`jue/state.py` 沉淀覆盖口径（WP-J）；`seeds/cases.yaml` 支线案例补「浸染」（模拟）；WP-U2 遗留 1、3、9、10（`agent/hub.py`、`l1/answer.py`、`app.py` 的 `questions`、`ui/server.py` 的 `frozen` 与需求单摘要、`web/src` 的业务员冻结提示与需求单客户名）。

未做：回问按类单独设阈值（仍与追问共用 0.15，写入简化清单）；契约问题（需求单视图的试样状态、条目的条件 / 未转译类型）待人修订冻结契约。
