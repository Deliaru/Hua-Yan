"""读取已选定课件的一页，复用已核对的PowerPoint COM原生导出，不调用模型。

uv run python scripts/read_pptx_slide.py --source SRC-18358d2dd7 --page 15
原生导出来自V10.0清单；本入口先交付文字/表格页，其他形状保留待补。
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil

from huayan.ingest.reader.powerpoint import read_pptx_slide
from huayan.ingest.reader.report import write_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="data/knowledge_v10/manifest/sources.json")
    parser.add_argument("--source", required=True)
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--out")
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
    write_review(report, output)
    print(f"读取第{args.page}页，{len(report['blocks'])}个原生块；产物：{output / 'review.html'}")


if __name__ == "__main__":
    main()
