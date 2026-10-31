"""把已核对的区域登记到读取记录；只改位置，不读取模型或写正式知识状态。

uv run python scripts/register_report_regions.py --evidence <evidence.json> --regions <regions.json>
区域文件包含source_id/file_sha256/native_pdf_sha256，以及regions中的span/page/bbox/image_sha256。
bbox为原生PNG左上原点像素；坐标必须先对照原页核对，不由此脚本自动推断。
"""
import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from huayan.ingest.reader.evidence import EvidenceBlock, Location
from huayan.ingest.reader.report import write_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--regions", required=True)
    args = parser.parse_args()
    path = Path(args.evidence).resolve()
    report = json.loads(path.read_text(encoding="utf-8"))
    regions = json.loads(Path(args.regions).read_text(encoding="utf-8"))
    if (regions["source_id"], regions["file_sha256"]) != (report["source_id"], report["file_sha256"]):
        raise ValueError("区域登记与报告来源不一致")
    pdf = Path(report["preview_pdf"])
    if sha256((pdf if pdf.is_absolute() else path.parent / pdf).read_bytes()).hexdigest() != regions["native_pdf_sha256"]:
        raise ValueError("原生PDF已变化，请重新核对区域")
    blocks = [EvidenceBlock.model_validate(b) for b in report["blocks"]]
    for entry in regions["regions"]:
        block = next((b for b in blocks if b.span == entry["span"]), None)
        location = next((loc for loc in block.locations if loc.page == entry["page"]), None) if block else None
        if location is None:
            raise ValueError(f"块在该页无定位：{entry['span']} / {entry['page']}")
        registered = Location.model_validate(location.model_dump() | {"bbox": entry["bbox"]})
        if registered.bbox is None:
            raise ValueError("区域登记须提供bbox坐标")
        image = Path(report["images"][location.page - 1])
        raw = (image if image.is_absolute() else path.parent / image).read_bytes()
        if sha256(raw).hexdigest() != entry["image_sha256"]:
            raise ValueError("原页图像已变化，请重新核对区域")
        with Image.open(BytesIO(raw)) as page:
            left, top, right, bottom = registered.bbox
            if not (0 <= left < right <= page.width and 0 <= top < bottom <= page.height):
                raise ValueError("登记区域超出原页或为空")
        location.bbox = registered.bbox
    report["blocks"] = [b.model_dump(mode="json") for b in blocks]
    write_review(report, path.parent)
    print(f"已登记 {len(regions['regions'])} 处区域：{path}")


if __name__ == "__main__":
    main()
