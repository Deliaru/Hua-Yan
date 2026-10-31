# 首份报告的本地版面与OCR

仅处理已经由本机Word/PowerPoint COM导出的PDF。原生XML、表格及读数继续作为独立依据；本入口另存MinerU辅助稿，不覆盖evidence.json、TrialRecord或正式知识状态，也不自动登记原生块的区域。

使用MinerU 4.1.3的Basic档、ONNX CPU。该档无需VLM，生成模型及Cloudflare实调仍保持暂停。安装在被忽略的data/tools中，不改变项目运行环境、pyproject.toml或uv.lock。只下载公开模型文件，不上传报告。

首次准备（项目根目录，PowerShell）：

```powershell
$env:UV_CACHE_DIR=Join-Path (Get-Location) 'data/.uv-cache'
.venv/Scripts/uv.exe venv data/tools/mineru --python .venv/Scripts/python.exe
.venv/Scripts/uv.exe pip install --python data/tools/mineru/Scripts/python.exe 'mineru==4.1.3'
$env:MINERU_HOME=Join-Path (Get-Location) 'data/tools/mineru-home'
$env:MODELSCOPE_CACHE=Join-Path (Get-Location) 'data/tools/modelscope-cache'
$env:MINERU_TELEMETRY_DISABLED='1'
$env:PYTHONIOENCODING='utf-8'
data/tools/mineru/Scripts/mineru-kit.exe models download --tier basic --small-backend onnx --source modelscope
```

运行（无需下载或调用远程模型）：

```powershell
.venv/Scripts/uv.exe run --locked --no-sync python scripts/read_report_layout.py --evidence data/knowledge_v10/evidence/SRC-3a2130604c/evidence.json --out data/knowledge_v10/evidence/SRC-3a2130604c/layout-mineru
```

输出包括原始middle.json、parse.log、带来源/输入指纹及原生PNG像素坐标的layout.json、原生页图副本和review.html。红框对应自动版面块，右侧保留原始OCR结构；table_body中的HTML作为文字展示，不执行。块编号仅属于本次辅助结果，不替换原生Fragment编号或指纹。没有定位的块保留bbox=null。

首份实际运行得到3页36块（2表、1图像、其余为文字/标题/页码），均有坐标。A组曲线被归为图像，B组曲线位于表格区域但标签未完整读取，OCR未读出132℃。因此只完成本地版面/OCR辅助读取，不代表完整曲线、专业条件或视觉模型结构化读数通过。组别均不自动赋值；原生30块、33条标签和待补项不变。

官方依据：[模型下载及Basic档边界](https://opendatalab.github.io/MinerU/usage/model_source/)、[输出协议与归一化区域](https://opendatalab.github.io/MinerU/reference/output_files/)。本入口仅接收docvortex.middle 2.0，升级工具后须按实际协议调整。
