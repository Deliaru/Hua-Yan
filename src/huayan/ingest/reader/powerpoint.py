"""选定PPTX页的原生文字与表格；位置映射到PowerPoint原生PNG。"""
from hashlib import sha256
from math import ceil, floor
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from pptx import Presentation

from .evidence import EvidenceBlock, Location, TableCell


def read_pptx_slide(path, source, page, images):
    path = Path(path)
    if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
        raise ValueError("课件原件指纹已变化，请重新核对来源")
    with ZipFile(path) as archive:
        if "ppt/presentation.xml" not in archive.namelist():
            raise ValueError("当前入口仅处理PPTX")
    deck = Presentation(path)
    if not 1 <= page <= len(deck.slides):
        raise ValueError("课件没有指定页")
    slide = deck.slides[page - 1]
    title = slide.shapes.title.text if slide.shapes.title is not None else f"第{page}页"
    with Image.open(images[page - 1]) as image:
        width, height = image.size
    sx, sy = width / deck.slide_width, height / deck.slide_height
    blocks, layout, pending = [], {}, []
    for shape in slide.shapes:
        span = f"slide-{page}/shape-{shape.shape_id}"
        cells = []
        if shape.has_table:
            rows, merged = [], []
            for r, row in enumerate(shape.table.rows, 1):
                texts = []
                for c, cell in enumerate(row.cells, 1):
                    if cell.is_spanned:
                        continue
                    cells.append(TableCell(row=r, column=c, text=cell.text))
                    texts.append(cell.text)
                    merged.append({"row": r, "column": c, "row_span": cell.span_height, "column_span": cell.span_width})
                rows.append("\t".join(texts))
            text, kind = "\n".join(rows), "table"
            layout[span] = merged
        elif shape.has_text_frame:
            text, kind = shape.text, "textbox"
        else:
            pending.append(f"{span}：本入口尚未解析此形状，须结合原页补读。")
            continue
        if not text.strip():
            continue
        bbox = (max(0, floor(shape.left * sx)), max(0, floor(shape.top * sy)),
                min(width, ceil((shape.left + shape.width) * sx)), min(height, ceil((shape.top + shape.height) * sy)))
        blocks.append(EvidenceBlock(source_id=source["source_id"], file_sha256=source["sha256"], span=span,
            text=text, level=source["level"], source=source["source"], kind=kind, section=title, cells=cells,
            locations=[Location(page=page, image_path=images[page - 1], bbox=bbox)]))
    return {"blocks": [b.model_dump(mode="json") for b in blocks],
            "fragments": [b.fragment().model_dump(mode="json") for b in blocks],
            "table_layout": layout, "pending": pending, "native_chart_count": sum(s.has_chart for s in slide.shapes),
            "slide_xml": slide.part.blob, "slide_count": len(deck.slides)}
