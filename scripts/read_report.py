"""读取清单中的一份 Word 报告，输出原文对照与读取侧 JSON；不写正式状态。

uv run python scripts/read_report.py --source SRC-3a2130604c
Cloudflare Worker 已部署时，在 PowerShell 设置 $env:CLOUDFLARE_WORKER_KEY="unused"，再运行：
uv run python scripts/read_report.py --source SRC-3a2130604c --vision
默认读图配置为 config/models.vision.cloudflare.yaml；可用 --models 指定其他网关配置。
使用项目根目录 .env 中的环境变量时，uv run 后加 --env-file .env。不加 --vision 时仅完成原生解析。
"""
import argparse
import json
from pathlib import Path

from huayan.gateway import build_gateway
from huayan.ingest.reader.report import read_report, read_report_images, write_review
from huayan.meter import FileMeter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/knowledge_v10/manifest/sources.json")
    parser.add_argument("--source", required=True)
    parser.add_argument("--out")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--models", default="config/models.vision.cloudflare.yaml")
    args = parser.parse_args()
    sources = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["sources"]
    source = {s["source_id"]: s for s in sources}[args.source]
    output = Path(args.out) if args.out else Path("data/knowledge_v10/evidence") / args.source
    report = read_report(source, output)
    write_review(report, output)
    if args.vision:
        gateway = build_gateway(args.models, False, FileMeter(output, "read_report"))
        gateway.cache_dir = Path("data/knowledge_v10/cache/image-readings")
        report["image_readouts"] = read_report_images(report, gateway)
        for item in report["image_readouts"]:
            report["pending"].extend(f'图片辅助读取第{item["page"]}页：{note}' for note in item["readout"]["pending"])
        write_review(report, output)
    print(f'读取 {len(report["blocks"])} 块，原生标签 {len(report["readings"])} 条；产物：{output / "review.html"}')


if __name__ == "__main__":
    main()
