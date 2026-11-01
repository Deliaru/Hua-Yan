"""首份报告的读取入口与静态原文对照；不导入正式知识状态。"""
import hashlib
import html
import json
import os
from pathlib import Path

from PIL import Image

from .image import read_image
from .office import export_word
from .word import read_docx, read_native_labels, save_document_xml


def read_report(source, output_dir):
    path, output = Path(source["path"]), Path(output_dir).resolve()
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    if fingerprint != source["sha256"]:
        raise ValueError("原件指纹与来源清单不一致，请先核对来源变化")
    native = export_word(path, output / "native")
    blocks = read_docx(native["reading_copy"], source, native["pages"], native["images"])
    readings, pending = read_native_labels(blocks)
    chart_count = save_document_xml(native["reading_copy"], output)
    if chart_count:
        pending.append(f"文档含 {chart_count} 个原生图表，当前 Word 样例读取器尚未解析其系列，交后续补读。")
    return {"source_id": source["source_id"], "source_path": str(path), "file_sha256": fingerprint,
            **native, "reading_copy_sha256": hashlib.sha256(Path(native["reading_copy"]).read_bytes()).hexdigest(),
            "native_chart_count": chart_count, "blocks": [b.model_dump(mode="json") for b in blocks],
            "fragments": [b.fragment().model_dump(mode="json") for b in blocks],
            "readings": [r.model_dump(mode="json") for r in readings], "pending": pending,
            "image_readouts": [], "professional_confirmation": None}


def read_report_images(report, gateway):
    """优先补读已登记的曲线区域，其他选定页读整页；原生文字和表格保持完整。"""
    results = []
    regions = native_regions(report, Path(report["preview_pdf"]).parent.parent)
    report["image_regions"] = regions
    by_span = {b["span"]: b for b in report["blocks"]}
    pages = set(report.get("selected_pages", range(1, len(report["images"]) + 1)))
    curves = [r for r in regions if r["page"] in pages and "曲线" in by_span[r["span"]]["text"]]
    for region in curves:
        block = by_span[region["span"]]
        readout, response = read_image(region["image_path"],
            f'当前区域：{block["span"]}，第{region["page"]}页，组别{block["group"] or "未指定"}。'
            '只补读工艺曲线、加料位置和曲线旁注；配方表已原生读取，不重复转录。'
            '跨页缺失或读不清的内容列入pending，不据上下文补全。', gateway)
        results.append({**region, "method": "vision", "readout": readout.model_dump(mode="json"),
                        "response": response.model_dump(mode="json")})
    for page, image in enumerate(report["images"], 1):
        if page not in pages or page in {r["page"] for r in curves}:
            continue
        context = "\n\n".join(f'{b["span"]}（{b["group"] or b["section"]}）\n{b["text"]}'
            for b in report["blocks"] if page in [loc["page"] for loc in b["locations"]])
        readout, response = read_image(image, context, gateway)
        results.append({"page": page, "method": "vision", "readout": readout.model_dump(mode="json"),
                        "response": response.model_dump(mode="json")})
    return results


def native_regions(report, output):
    """仅裁取Office原生PNG，坐标来自已有Location，不解析或重绘形状。"""
    output = Path(output).resolve() / "regions"
    output.mkdir(parents=True, exist_ok=True)
    regions = []
    for block in report["blocks"]:
        for loc in block["locations"]:
            if loc["bbox"] is None:
                continue
            image = output / f'{block["span"].replace("/", "-")}-page-{loc["page"]}.png'
            with Image.open(report["images"][loc["page"] - 1]) as page:
                page.crop(loc["bbox"]).save(image)
            regions.append({"span": block["span"], "page": loc["page"], "bbox": loc["bbox"],
                            "group": block["group"], "image_path": str(image),
                            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest()})
    return regions


def render_block_images(report, spans, output):
    """各审阅页共用原生区域及同一区域的模型辅助稿，不改变Fragment。"""
    esc = html.escape
    figures = []
    for region in report.get("image_regions", []):
        if region["span"] not in spans:
            continue
        image = Path(os.path.relpath(region["image_path"], output)).as_posix()
        drafts = ""
        for item in report["image_readouts"]:
            if item["page"] == region["page"] and item.get("span") in (None, region["span"]):
                scope = "区域" if item.get("span") else "整页"
                model = esc(item["response"]["model"]) + ("（降级）" if item["response"]["fallback_used"] else "")
                drafts += f'<details><summary>{model} · {scope}辅助稿 · 待人工审阅</summary>'
                drafts += f'<pre>{esc(json.dumps(item["readout"], ensure_ascii=False, indent=2))}</pre></details>'
        figures.append(f'<figure class="native-region"><img src="{esc(image)}" alt="Office原生区域">'
                       f'<figcaption>{esc(region["span"])} · 第{region["page"]}页 · Office原生裁图</figcaption>{drafts}</figure>')
    return "".join(figures)


def write_review(report, output_dir):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report["image_regions"] = native_regions(report, output)
    (output / "evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    esc = html.escape
    rows = []
    for reading in report["readings"]:
        cells = [reading["group"] or "未分组", reading["stage"] or "原生标签（阶段待关联）",
                 reading["value"] + " " + reading["unit"], "；".join(reading["conditions"]), reading["quote"]]
        rows.append("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in cells)
                    + f'<td><a href="#{esc(reading["span"])}">{esc(reading["span"])}</a> '
                    + esc(str(reading["cell"]) if reading["cell"] else "") + "</td></tr>")
    pages = []
    for page, image_path in enumerate(report["images"], 1):
        if page not in report.get("selected_pages", range(1, len(report["images"]) + 1)):
            continue
        texts = []
        for block in report["blocks"]:
            locations = block["locations"]
            if page not in [loc["page"] for loc in locations]:
                continue
            anchor = f' id="{esc(block["span"])}"' if page == locations[0]["page"] else ""
            texts.append(f'<section{anchor}><h3>{esc(block["span"])} · {block["group"] or "未分组"}</h3>'
                         f'<p>{esc(block["section"])}</p>{render_block_images(report, [block["span"]], output)}'
                         f'<details><summary>原生文字（不代替图线）</summary><pre>{esc(block["text"])}</pre></details></section>')
        relative_image = Path(image_path).relative_to(output).as_posix()
        pages.append(f'<h2 id="page-{page}">原生第 {page} 页</h2><div class="page"><img src="{esc(relative_image)}" '
                     f'alt="原生第 {page} 页"><div>{"".join(texts)}</div></div>')
    pending = "".join(f"<li>{esc(note)}</li>" for note in report["pending"])
    visual = []
    for item in report["image_readouts"]:
        if item.get("span"):
            continue  # 区域读稿已内联到对应原文块。
        image_rows = []
        for reading in item["readout"]["readings"]:
            cells = [reading["group"] or "共同／待确认", reading["object"], reading["stage"] or "待关联",
                     (reading["value"] or "未读清") + " " + (reading["unit"] or "单位未给出／未读清"),
                     "；".join(reading["conditions"]) or "未给出，待确认", reading["quote"] or "未读清"]
            image_rows.append("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in cells)
                              + f'<td><a href="#page-{item["page"]}">{esc(reading["position"])}</a></td></tr>')
        model = esc(item["response"]["model"]) + ("（降级）" if item["response"]["fallback_used"] else "")
        visual.append(f'<h3>第 {item["page"]} 页 · 图片模型读取 · {model}</h3>'
                      f'<pre>{esc(item["readout"]["text"])}</pre><table><thead><tr><th>组别</th><th>对象</th>'
                      '<th>阶段</th><th>值与原单位</th><th>条件</th><th>原文标签</th><th>图中位置</th></tr></thead>'
                      f'<tbody>{"".join(image_rows)}</tbody></table>')
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>报告原文与读取结果 · {esc(report["source_id"])}</title>
<style>body{{font:16px/1.6 "Microsoft YaHei",sans-serif;margin:32px;color:#183044;background:#f6f8fa}}
h1,h2{{color:#145b67}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{border:1px solid #d8e0e5;padding:8px;text-align:left}}
.page{{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}}img{{width:100%;position:sticky;top:12px}}
section{{background:white;padding:12px;margin-bottom:12px;border:1px solid #d8e0e5}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}
.native-region img{{position:static}}.native-region{{margin:12px 0}}
.notice{{padding:16px;background:#fff3d4}}@media(max-width:950px){{.page{{grid-template-columns:1fr}}img{{position:static}}}}</style>
<h1>报告原文与读取结果</h1><p>{esc(report["source_id"])} · {esc(report["renderer"])}</p>
<p class="notice">原生文字与表格／标签读数，尚未专业确认。试样报告中A＝工厂原工艺，B＝试样工艺；未分组内容保留所在节标题。曲线速率未自动关联线段。</p>
<p><a href="native/original.pdf">原生 PDF</a> · <a href="evidence.json">完整读取记录</a> · <a href="document.xml">原始 XML</a></p>
<h2>待补读</h2><ul>{pending}</ul><h2>数值与出处</h2><table><thead><tr><th>组别</th><th>阶段</th><th>值与原单位</th><th>局部条件</th><th>原文标签</th><th>出处／行列</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>{"".join(pages)}
<h2>图片辅助读稿（待人工审阅）</h2>{"".join(visual) or "<p>尚无可用的图片模型读数；当前仅完成原生解析，图片结构化读数待补。</p>"}</html>'''
    (output / "review.html").write_text(document, encoding="utf-8")
