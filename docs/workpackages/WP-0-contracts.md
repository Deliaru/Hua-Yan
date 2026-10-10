# WP-0 契约代码、复制模块与桩

> 负责：A｜时段：0:00–0:45｜分支：`dev/a`

## 目标
把 `docs/CONTRACTS.md` 变成代码，复制 JUE 中可直接复用的模块，提供各包共用的领域函数、事件日志、问题总线和一份小种子。其他包都依赖它，必须严格忠实于契约。

## 依赖
无。JUE 源码在 `D:\Work\JUE\src\jue`（只读）。

## 必读
`CONTRACTS.md` 全文；`AGENTS.md`。

## 允许修改的范围
`pyproject.toml`、`.gitignore`、`src/huayan/__init__.py`、`src/huayan/contracts/`、`src/huayan/clock.py`、`src/huayan/meter.py`、`src/huayan/domain.py`、`src/huayan/events.py`、`src/huayan/bus.py`、`src/huayan/gateway/`、`src/huayan/jev/system1/`、`src/huayan/jue/expr.py`、其余 `src/huayan/` 子目录的空 `__init__.py`、`config/app.yaml`、`config/models.yaml`、`config/system1.yaml`、`tests/conftest.py`、`tests/fixtures/`、`tests/test_wp0.py`

## 交付物与已定设计

### 1. 项目配置
- `uv` 项目，包名 `huayan`，`src/` 布局；依赖见 `AGENTS.md` 第 2 节；pytest 配置 `addopts = "--import-mode=importlib"`。
- `.gitignore`：`runs/`（保留 `!runs/demo_record/`）、`data/`（保留 `!data/.gitkeep`）、`models/*.pkl`、`.env`、缓存。

### 2. 契约代码 `src/huayan/contracts/`
按契约章节分文件：`_base.py`（复制 JUE 的带时区 datetime 与 `extra="forbid"` 基类）、`seeds.py`、`knowledge.py`、`session.py`、`jev.py`（含 S1 题型）、`jue.py`、`bus.py`、`escalation.py`、`events.py`、`sim.py`、`gateway.py`、`meter.py`、`app.py`（`SessionView`、`RunStatus`），`__init__.py` 统一导出。常量 `ROLE_LEVEL`、`KIND_LEVEL`、`CUSTOMER_VERSIONS` 放进对应文件。`KnowledgeBase`、`HuayanApp` 等具体类不在这里定义。

### 3. 复制 JUE 模块（只改 import 和契约要求的差异，不重构）
| 来源 | 目标 | 差异 |
|---|---|---|
| `jue/gateway/client.py`、`mock.py`、`__init__.py` | `huayan/gateway/` | `MockGateway` 的零值 datetime 用 `get_clock().now()` |
| `jue/system1/onejev.py` | `huayan/jev/system1/onejev.py` | `build_system1` 增加 `impl="mock"` |
| — | `huayan/jev/system1/mock.py` | **重写**：按契约 4.1 的 caller 规则 |
| `jue/meter.py` | `huayan/meter.py` | `FileMeter(run_dir, run_id)`，字段按契约 ⑩ |
| `jue/clock.py` | `huayan/clock.py` | 增加 `WallClock`（`datetime.now(Asia/Shanghai)`）；未设置时 `get_clock()` 返回 `WallClock` |
| `jue/discovery/expr.py` | `huayan/jue/expr.py` | 只允许 `attrs.x`；`evaluate(source, attrs: dict, boolean=False)` |

文件头加一行注释：`# 复用自 JUE 赛前代码 src/jue/...`。

### 4. 共用模块
- `huayan/domain.py`：契约 1.5 的全部函数。`find_slot_values` 先匹配口语说法、再匹配取值本身，同一槽位取最长匹配。
- `huayan/events.py`：`EventLog`，内存列表 + 可选 JSONL 追加；id 递增 `ev:<n>`。
- `huayan/bus.py`：`QuestionBus`，按契约 ⑥；id 递增 `q:<n>`；每次变化向 `questions.jsonl` 追加快照（构造时传入路径，可为 None）。

### 5. 配置
`config/app.yaml` 按契约 ⑪ 填写默认值（全部离线：`system1_impl: mock`、`gateway_mock: true`、`extractor: rule`）。`models.yaml`、`system1.yaml` 复制 JUE 的格式，地址与模型名留待人填写。

### 6. 小种子 `tests/fixtures/mini_seeds/`
所有包的测试只用它。按契约 ① 的格式，`placeholder: true`：
- 3 个槽位：`fiber`（棉 / 涤纶 / 锦纶氨纶）、`equipment`（溢流染色机 / 气流染色机）、`constraint`（无 / 无APEO）；
- 2 个现象：`color_unlevel`（必问 `fiber`、`equipment`）、`poor_fastness`（必问 `fiber`）；
- 4 个产品：`T-101`（色花，涤纶）、`T-205`（色花，锦纶氨纶 + 溢流染色机）、`T-301`（牢度，棉）、`T-206`（色花，锦纶氨纶 + 气流染色机，`status: project`）；
- 1 个案例、2 条转化对照（其中一条 `chem_term` 含「pH」，供规则抽取器识别懂化学的客户）、actors（`sales:S01`、`sales:S02`、`customer:C01`–`C03`、`pm:P01`、`rd:R01`、`supervisor:M01`）。
- 这组关系必须成立：只知道「色花」时候选 2 个；知道「锦纶氨纶」后剩 `T-205`；再知道「气流染色机」后无候选（应升级）；发布 `T-206` 后命中 `T-206`。

## 验收
1. `uv sync`、`uv run pytest` 通过；`python -c "import huayan.contracts"` 无报错。
2. `tests/test_wp0.py` 只包含 2 个测试：
   - 小种子上 `match_candidates` / `correct_product` 符合第 6 节的四步关系；
   - `QuestionBus`：同 `dedup_key` 的 open 问题合并；dismiss 后抑制期内再发布被丢弃。
3. 手动：`MockGateway` 与 `MockSystem1Client` 各调用一次，`metering.jsonl` 有记录。

## 不做
任何业务实现（知识库、抽取、觉、界面）。发现契约矛盾时列在汇报中，不自行改字段。
