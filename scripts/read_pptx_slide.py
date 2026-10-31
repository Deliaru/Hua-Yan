"""读取已选定课件的一页；--vision 使用PowerPoint COM原生导出和统一智谱网关。

uv run --env-file .env python scripts/read_pptx_slide.py --source SRC-18358d2dd7 --page 15 --vision
原生导出来自V10.0清单；本入口先交付文字/表格页，其他形状保留待补。
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

from huayan.ingest.reader.powerpoint import read_pptx_slide
from huayan.ingest.reader.report import write_review
from huayan.ingest.reader.report import read_report_images
from huayan.ingest.reader.office import export_powerpoint
from huayan.gateway import build_gateway
from huayan.meter import FileMeter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/knowledge_v10/manifest/sources.json")
    parser.add_argument("--source", required=True)
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--out")
    parser.add_argument("--vision", action="store_true")
    parser.add_argument("--models", default="config/models.yaml")
    args = parser.parse_args()
    source = next(s for s in json.loads(Path(args.manifest).read_text(encoding="utf-8"))["sources"]
                  if s["source_id"] == args.source)
    native_pdf = Path(source["review_pdf"])
    native_input = native_pdf.parent / "input" / f"{args.source}.pptx"
    if (sha256(native_pdf.read_bytes()).hexdigest() != source["review_pdf_sha256"]
            or sha256(native_input.read_bytes()).hexdigest() != source["sha256"]):
        raise ValueError("原生Office导出与清单不一致，请先重新核对")
    # 使用V10.0已完成的25页COM导出，只有指定页进入证据块和审阅页。
    original_images = [native_pdf.parent / f"{args.source}-slides" / f"幻灯片{p}.PNG"
                       for p in range(1, source["review_page_count"] + 1)]
    extracted = read_pptx_slide(source["path"], source, args.page, [str(p) for p in original_images])
    output = Path(args.out) if args.out else Path("data/knowledge_v10/evidence") / args.source
    output = output.resolve()
    (output / "native").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(native_pdf, output / "native/original.pdf")
    shutil.copyfile(native_input, output / "native/original.pptx")
    images = []
    for p, image in enumerate(original_images, 1):
        target = output / "native" / f"page-{p:02d}.png"
        shutil.copyfile(image, target)
        images.append(str(target))
    (output / "document.xml").write_bytes(extracted.pop("slide_xml"))
    for block in extracted["blocks"]:
        block["locations"][0]["image_path"] = images[args.page - 1]
    report = {"source_id": args.source, "source_path": source["path"], "file_sha256": source["sha256"],
              "format": "pptx", "renderer": "PowerPoint COM原生导出（复用V10.0，python-pptx原生读取）",
              "preview_pdf": str(output / "native/original.pdf"), "images": images, "selected_pages": [args.page],
              **extracted, "readings": [], "image_readouts": [], "professional_confirmation": None}
    if args.vision:
        native = export_powerpoint(source["path"], output / "native")
        # 原生COM新图的实际尺寸用于区域映射；不重绘形状。
        reread = read_pptx_slide(source["path"], source, args.page, native["images"])
        reread.pop("slide_xml")
        report.update(native | reread)
    write_review(report, output)
    if args.vision:
        gateway = build_gateway(args.models, False, FileMeter(output, "read_pptx_slide"))
        gateway.cache_dir = Path("data/knowledge_v10/cache/image-readings")
        def trace(event, **fields):
            with (output / "gateway-trace.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
        gateway.trace = trace
        report["image_readouts"] = read_report_images(report, gateway)
        write_review(report, output)
    print(f"读取第{args.page}页，{len(report['blocks'])}个原生块；产物：{output / 'review.html'}")


if __name__ == "__main__":
    main()
