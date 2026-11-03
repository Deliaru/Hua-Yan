# REPLAN v12｜扫描资料补读与检索排序修正

分支 `v12`，自 `v11 @ bb0a09f` 分出。V11.13 的资料库（`data/library/`、`LibrarySource`、`search_sources`）上做增量，不改冻结契约，不碰 `knowledge/`、`jue/`、`sim/`、`agent/loop.py`、`web/`。

起因：V11.13 登记的 4644 页里 1612 页没抽出文字，全部是考点一的四本扫描教材和一份国标，检索不到；检索排序把「有语义分数的」一律排在只被关键词命中的前面，V11.13 真实链路里目标报告正是只被关键词召回（第 5 名）。Agent 读扫描页本来就能读页图，所以 OCR 补的是「能被检索到」；业务报告没有待补读页，TF-213HE 业务链不受影响。

检索评测不作为主要证据（同 V11.13）；不建页内块结构、章节索引、证据单元分离，等 OCR 后真跑出具体失败的查询再说。

### V12.0｜OCR 选型

在 11 页样本上比本地 RapidOCR 与网关视觉模型，选一条。

**完成记录（2026-11-04）**

- 选定网关视觉模型 `deepseek-v4.1-flash`（`caller=ingest:extract`，经 `data/pilot/models.yaml`）。正文两条路相当（汉字序列相似度 0.97–1.00），表格、公式、双栏图题、标题层级视觉模型明显好；本地 OCR 表格一格一行、公式打散。依据与指标见 `docs/reports/v12-ocr-selection.md`；
- 确认待补读分布：1612 页全在考点一，四本教材 1599 页、国标 12 页、另一本 1 页；
- 代码未改；对照脚本与样本转写在 `data/scratch/v12ocr/`（不入库）；RapidOCR 只装进 `.venv-win` 用于对照；
- 发现的问题：模型转写在多值合并格、公式上下标上会有个别错误，所以转写页要标明是模型读稿。

### V12.1｜扫描页补读

1. `scripts/build_library.py --ocr-pending`：对每份资料里仍是待补读的页，从 PDF 按宽 2000 px 重渲，经网关视觉模型转写成 Markdown（提示词同选型脚本），替换 `pages[]` 里的待补读占位；在该资料的 `docs/<doc_id>.json` 里记 `"ocr": {"<页号>": "<模型>"}`。失败的页打印出来，保持待补读；空白页写明空白。已不是待补读的页跳过，重跑即续跑；
2. `sources.json` 的 `pending_pages` 随之更新；之后照旧 `--index`，文字变了的页按 `page_key` 重算向量；
3. `LibrarySource` 读到 `ocr` 里的页时，检索结果和 `read_source` 摘录标明「模型转写，引用前对照原图」；指针仍是 `doc_id#p<页号>@指纹`；
4. 验证：真实跑完 1612 页，报成功、失败、空白页数；抽几页对照原图。

实现时第 3 条改得更短：「模型转写，引用前对照原图」直接写在页文字开头，`read_source`、检索摘录、Agent 看到的都是同一段，`LibrarySource` 不用改。

**完成记录（2026-11-04）**

- 代码：
  - `ingest/reader/image.py`：新增 `transcribe_page(raw, gateway)`，整页图经网关转写成 Markdown（`caller=ingest:extract`，`max_tokens` 8192）；
  - `scripts/build_library.py --ocr-pending`：只处理还是待补读的页，从 PDF 按宽 2000 px 重渲，4 路并发调网关（pdfium 渲染串行），页文字写成「【模型转写（模型），引用前对照原图】」+ 转写，`docs/<doc_id>.json` 记 `ocr: {页号: 模型}`，每 20 页落盘一次并更新 `sources.json` 的 `pending_pages`；没转写出来的页打印、保持待补读，重跑即重试；
- 真实运行（`deepseek-v4.1-flash` 经 `data/pilot/models.yaml`，计量在 `data/library/metering.jsonl`）：
  - 第一遍约 1 小时 50 分，1598 页转写成功，14 页返回空内容（都是公式或大表密集页，输出顶到 4096 token 被截空），保持待补读；
  - `max_tokens` 提到 8192 后重跑，14 页全部成功；
  - 结果：1612 页全部转写，待补读 0 页；其中 3 页是国标的空白页，标为空白；没有出现重复循环的输出；共 1684 次调用，约 313 万输入、87 万输出 token；
  - 抽查：重试的公式页（式 2-4、2-5 推导）与原图逐项对得上；选型时的 11 页误差见 `docs/reports/v12-ocr-selection.md`；
- `--index` 重建：只重算转写过的 1612 页，旧的待补读页向量随之去掉；
- 检索抽查（R01 权限，`data/scratch/v12ocr/probe.py`，不是金标）：分配比计算、腈纶阳离子染料匀染、吸湿速干性吸水率测法、聚氧乙烯醚红外特征吸收、季铵盐核磁解析 5 句，前 6 名都落在对应的扫描教材或国标页上；同时看到关键词强命中（如 0.923）被弱语义命中压到第 6 名，正是 V12.2 要修的排序；
- 离线 87 项通过；本包没有新增测试（转写效果靠真实运行看）；
- 遗留：模型转写在多值合并格、个别上下标上会出错，靠页首标注和 `read_source_image` 回看原图兜住；原数据备份在 `data/scratch/v12ocr/backup/`。

### V12.2｜检索排序与扫描页走链

1. `search_library` 把关键词与语义两路各自排名后按 RRF 融合，按（资料，页）去重，每条保留两路的名次与分数和 `method`；关键词打分把资料标题算进去（问型号时说明书不再被 MSDS 挤掉）；
2. 测试 1 项：只被关键词强命中的页不被弱语义命中压到后面；
3. 验证：V11.13 的 5 句查询加几句教材查询，重跑对照（`data/scratch/compare_library.py`，失败也记）；真实模型下研发 Agent 问一个教材里的问题（含公式或表格），走 `search_sources` → `read_source` → `read_source_image` 核对 → 引用作答。

不做：页内块与 bbox、章节/条款索引、检索单元与证据单元分离、上下文前缀、标准编号登记表、Jev 重排、Recall/MRR 指标体系与三组对照、权限新测试（OCR 文字走同一读取入口，`test_library_v1113.py` 已覆盖）。
