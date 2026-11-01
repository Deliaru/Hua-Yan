"""读取清单中的一份 Word 报告，输出原文对照与读取侧 JSON；不写正式状态。

uv run --env-file .env python scripts/read_report.py --source SRC-3a2130604c
uv run --env-file .env python scripts/read_report.py --source SRC-3a2130604c --vision
默认读图配置为 config/models.yaml（SiliconFlow Qwen视觉模型）；Cloudflare仅用于Clef。
使用项目根目录 .env 中的环境变量时，uv run 后加 --env-file .env。不加 --vision 时仅完成原生解析。
"""
import argparse
import json
from hashlib import sha256
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
    parser.add_argument("--models", default="config/models.yaml")
    args = parser.parse_args()
    sources = json.loads(Path(args.manifest).read_text(encoding="utf-8"))["sources"]
    source = {s["source_id"]: s for s in sources}[args.source]
    output = Path(args.out) if args.out else Path("data/knowledge_v10/evidence") / args.source
    path = output / "evidence.json"
    if args.vision and path.exists():
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["file_sha256"] != source["sha256"] or sha256(Path(source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("原件指纹已变化，请重新原生读取并登记区域")
    else:
        report = read_report(source, output)
    write_review(report, output)
    if args.vision:
        gateway = build_gateway(args.models, False, FileMeter(output, "read_report"))
        gateway.cache_dir = Path("data/knowledge_v10/cache/image-readings")
        def trace(event, **fields):
            with (output / "gateway-trace.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
        gateway.trace = trace
        report["image_readouts"] = read_report_images(report, gateway)
        report["pending"] = [note for note in report["pending"]
                             if not note.startswith(("图片模型读取未完成：", "图片辅助读取第"))]
        for item in report["image_readouts"]:
            report["pending"].extend(f'图片辅助读取第{item["page"]}页：{note}' for note in item["readout"]["pending"])
        write_review(report, output)
    print(f'读取 {len(report["blocks"])} 块，原生标签 {len(report["readings"])} 条；产物：{output / "review.html"}')


if __name__ == "__main__":
    main()
