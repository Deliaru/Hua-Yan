"""读取清单中的一份 Word 报告，输出原文对照与读取侧 JSON；不写正式状态。

uv run python scripts/read_report.py --source SRC-3a2130604c
配置好现有模型网关后，可加 --vision 获取原生页面的辅助读稿。
"""
import argparse
import json
from pathlib import Path

from huayan.gateway import build_gateway
from huayan.ingest.reader.image import read_image
from huayan.ingest.reader.report import read_report, write_review
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
    report = read_report(source, output)
    write_review(report, output)
    if args.vision:
        gateway = build_gateway(args.models, False, FileMeter(output, "read_report"))
        for page, image in enumerate(report["images"], 1):
            context = "\n\n".join(f'{b["span"]}（{b["group"] or b["section"]}）\n{b["text"]}'
                                  for b in report["blocks"] if page in [loc["page"] for loc in b["locations"]])
            readout, response = read_image(image, context, gateway)
            report["image_readouts"].append({"page": page, "readout": readout.model_dump(mode="json"),
                                            "response": response.model_dump(mode="json")})
            report["pending"].extend(f"图片辅助读取第{page}页：{note}" for note in readout.pending)
        write_review(report, output)
    print(f'读取 {len(report["blocks"])} 块，原生标签 {len(report["readings"])} 条；产物：{output / "review.html"}')


if __name__ == "__main__":
    main()
