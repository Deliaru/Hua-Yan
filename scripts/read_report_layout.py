"""对已有原生Office PDF运行本地MinerU Basic OCR，另存版面审阅包。

安装与运行见 scripts/read_report_layout.md；不覆盖原生证据、TrialRecord或契状态。
"""
import argparse
from hashlib import sha256
import html
import json
from math import ceil, floor
import os
from pathlib import Path
import shutil
import subprocess
from time import perf_counter

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mineru", default="data/tools/mineru/Scripts/mineru-kit.exe")
    args = parser.parse_args()
    evidence = Path(args.evidence).resolve()
    report = json.loads(evidence.read_text(encoding="utf-8"))
    pdf = Path(report["preview_pdf"])
    pdf = pdf if pdf.is_absolute() else evidence.parent / pdf
    if pdf.read_bytes()[:5] != b"%PDF-":
        raise ValueError("需要已有的原生Office导出PDF")
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ | {
        "MINERU_HOME": str(Path("data/tools/mineru-home").resolve()),
        "MINERU_MODEL_SOURCE": "local", "MINERU_MODEL_SMALL_BACKEND": "onnx",
        "MINERU_MODEL_ONNX_DEVICE": "cpu", "MINERU_TELEMETRY_DISABLED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    command = [str(Path(args.mineru).resolve()), "parse", str(pdf), "--output", str(output / "middle.json"),
               "--format", "middle_json", "--tier", "basic", "--ocr-mode", "ocr"]
    started = perf_counter()
    with (output / "parse.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    elapsed = perf_counter() - started
    middle = json.loads((output / "middle.json").read_text(encoding="utf-8"))
    if (middle["schema"], middle["schema_version"]) != ("docvortex.middle", "2.0"):
        raise ValueError("当前只接收MinerU的docvortex.middle 2.0输出")
    if middle["extensions"]["mineru"] != {"tier": "basic", "parse_mode": "ocr"}:
        raise ValueError("当前只接收Basic本地OCR结果")
    records, pages = [], []
    esc = html.escape
    for page in middle["pages"]:
        number = page["page_idx"] + 1
        image = Path(report["images"][number - 1])
        image = image if image.is_absolute() else evidence.parent / image
        image_name = f"page-{number}.png"
        shutil.copyfile(image, output / image_name)
        with Image.open(image) as native:
            width, height = native.size
        boxes, texts = [], []
        for block in page["blocks"]:
            key = f'mineru/page-{number}/block-{block["index"]}'
            bbox = block.get("bbox")  # 外部版面协议允许缺少定位。
            pixels = None
            if bbox is not None:
                left, top, right, bottom = bbox
                if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
                    raise ValueError(f"无效的归一化区域：{key}")
                pixels = [floor(left * width), floor(top * height), ceil(right * width), ceil(bottom * height)]
                x0, y0, x1, y1 = pixels
                boxes.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}"/>'
                             f'<text x="{x0}" y="{max(y0, 15)}">{block["index"]}</text>')
            records.append({"key": key, "page": number, "bbox": pixels, "normalized_bbox": bbox,
                            "image_sha256": sha256(image.read_bytes()).hexdigest(),
                            "group": None, "status": "needs_review", "raw": block})
            texts.append(f'<h3>{esc(key)} · {esc(block["type"])}</h3><pre>'
                         + esc(json.dumps(block, ensure_ascii=False, indent=2)) + "</pre>")
        pages.append(f'<h2>原生第{number}页</h2><div class="page"><svg viewBox="0 0 {width} {height}">'
                     f'<image href="{image_name}" width="{width}" height="{height}"/>{"".join(boxes)}</svg>'
                     f'<div>{"".join(texts)}</div></div>')
    result = {"source_id": report["source_id"], "file_sha256": report["file_sha256"],
              "evidence_sha256": sha256(evidence.read_bytes()).hexdigest(),
              "native_pdf_sha256": sha256(pdf.read_bytes()).hexdigest(),
              "middle_sha256": sha256((output / "middle.json").read_bytes()).hexdigest(),
              "producer": middle["metadata"]["producer"], "method": "local_basic_ocr_onnx_cpu",
              "command": command, "elapsed_s": elapsed, "blocks": records,
              "pending": ["OCR辅助稿待核对，不自动赋予A/B组别、推断曲线关系或补齐单位；原生证据独立保留。",
                          "图像块及表格中的曲线仍须对照原页补读；本结果不等于视觉模型结构化读数。"]}
    (output / "layout.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "review.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>本地版面与OCR审阅</title><style>'
        'body{font:16px/1.6 "Microsoft YaHei",sans-serif;margin:24px}.page{display:grid;grid-template-columns:1fr 1fr;gap:24px}'
        'svg{width:100%;position:sticky;top:0}rect{fill:none;stroke:#c0392b;stroke-width:2}'
        'text{fill:#c0392b;font-size:18px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        f'<h1>{esc(report["source_id"])} · MinerU本地OCR辅助稿</h1>'
        f'<p>{esc("；".join(result["pending"]))}</p><p>红框与编号为自动版面结果；不是已确认的原生块定位。</p>'
        '<p><a href="layout.json">带来源指纹与像素坐标的记录</a> · <a href="middle.json">原始MinerU输出</a></p>'
        + "".join(pages), encoding="utf-8")
    print(f'{len(middle["pages"])}页，{len(records)}个辅助块：{output / "review.html"}')


if __name__ == "__main__":
    main()
