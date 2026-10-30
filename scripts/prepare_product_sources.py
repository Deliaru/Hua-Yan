"""为当前产品对齐准备 SDS/说明书原生文字和页码依据；仅输出读取侧材料。"""
import argparse
import hashlib
import html
import json
from pathlib import Path

import pypdfium2 as pdfium

from huayan.ingest.reader.evidence import EvidenceBlock


def read_pdf(path, output):
    path, output = Path(path), Path(output)
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    source_id = "SRC-" + fingerprint[:10]
    output.mkdir(parents=True, exist_ok=True)
    (output / "original.pdf").write_bytes(path.read_bytes())
    pdf = pdfium.PdfDocument(path)
    blocks = []
    for index in range(len(pdf)):
        page = pdf[index]
        textpage = page.get_textpage()
        text = textpage.get_text_range().replace("\r", "")
        blocks.append(EvidenceBlock(source_id=source_id, file_sha256=fingerprint, span=f"page-{index + 1}",
            text=text, level=3, source="internal", kind="paragraph", section=f"原生 PDF 第{index + 1}页"))
        if index == 0:
            bitmap = page.render(scale=1.5)
            bitmap.to_pil().save(output / "page-1.png")
            bitmap.close()
        textpage.close()
        page.close()
    pdf.close()
    data = {"source_id": source_id, "file_sha256": fingerprint, "source_path": str(path.resolve()),
        "renderer": "PDF 原生文字；PDFium 首页图", "fragments": [b.fragment().model_dump(mode="json") for b in blocks]}
    (output / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pages = "".join(f'<h2 id="{b.span}">第{i + 1}页</h2><pre>{html.escape(b.text)}</pre>' for i, b in enumerate(blocks))
    (output / "review.html").write_text(f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>产品资料原文</title><style>body{{font:16px/1.6 sans-serif;margin:32px}}pre{{white-space:pre-wrap}}
img{{max-width:900px;width:100%}}</style><h1>{html.escape(path.name)}</h1>
<p>L3 内部资料，待审；原生文字提取，无模型调用。文件指纹：{fingerprint}</p>
<a href="original.pdf">原始 PDF</a><p><img src="page-1.png" alt="原生首页"></p>{pages}</html>''', encoding="utf-8")
    print(f"{source_id}：{len(blocks)}页；{output / 'evidence.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sds", required=True)
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    read_pdf(args.sds, Path(args.out) / "sds")
    read_pdf(args.sheet, Path(args.out) / "sheet")


if __name__ == "__main__":
    main()
