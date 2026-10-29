"""按首份报告的原生段落、表格和节标题读取；A/B 来自原工艺/试样工艺标题。"""
import re
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .evidence import EvidenceBlock, Location, Reading, TableCell


def read_docx(path, source, pages, images):
    document = Document(path)
    blocks = []
    paragraph_number = table_number = 0
    section, group = "", None
    for item in document.iter_inner_content():
        cells = []
        if isinstance(item, Table):  # python-docx 的 Paragraph | Table 联合类型
            table_number += 1
            span, kind = f"table-{table_number}", "table"
            seen, rows = set(), []
            for row_number, row in enumerate(item.rows, 1):
                row_text = []
                for column, cell in enumerate(row.cells, 1):
                    if cell._tc not in seen:  # 合并格的同一物理单元格只读一次
                        cells.append(TableCell(row=row_number, column=column, text=cell.text))
                        row_text.append(cell.text)
                        seen.add(cell._tc)
                rows.append("\t".join(row_text))
            text = "\n".join(rows)
            element = item._tbl
        else:
            paragraph_number += 1
            span, kind, text, element = f"paragraph-{paragraph_number}", "paragraph", item.text, item._p
            if re.match(r"^[一二三四五六七八九十]+[、．.]", text.strip()):
                section = text.strip()
                group = "A" if "工厂原工艺" in section else "B" if "试样工艺" in section else None
        locations = [Location(page=p, image_path=images[p - 1]) for p in pages[span]]
        common = dict(source_id=source["source_id"], file_sha256=source["sha256"], level=source["level"],
                      source=source["source"], section=section, group=group, locations=locations)
        if text.strip():
            blocks.append(EvidenceBlock(**common, span=span, text=text, kind=kind, cells=cells))
        for number, textbox in enumerate(element.xpath(".//w:txbxContent"), 1):
            text = "\n".join(Paragraph(p, document).text for p in textbox.findall(qn("w:p")))
            blocks.append(EvidenceBlock(**common, span=f"{span}/textbox-{number}", text=text, kind="textbox"))
    return blocks


HOLD = re.compile(r"(?P<temperature>\d+(?:\.\d+)?)(?:℃|°C)\s*[*×]\s*(?P<time>\d+(?:\.\d+)?)min")
LABEL = re.compile(r"(?<![\d.])(?P<value>\d[\d.]*)\s*(?P<unit>℃/min|°C/min|g/㎡|kg|℃|°C|min)")


def read_native_labels(blocks):
    """读明确写出的数值/单位和温度×保温时间；不从文本顺序猜曲线连线。"""
    readings, pending = [], []
    for block in blocks:
        texts = [(cell.text, (cell.row, cell.column)) for cell in block.cells] if block.kind == "table" else [(block.text, None)]
        for text, cell in texts:
            args = dict(span=block.span, cell=cell, object=block.section, group=block.group)
            holds = list(HOLD.finditer(text))
            for hold in holds:
                readings.append(Reading(**args, stage="保温", value=hold["time"], unit="min",
                                        conditions=[hold["temperature"] + "℃"], quote=hold.group()))
            for label in LABEL.finditer(text):
                if any(hold.start() <= label.start() < hold.end() for hold in holds):
                    continue
                status = "native" if re.fullmatch(r"\d+(?:\.\d+)?", label["value"]) else "needs_reading"
                readings.append(Reading(**args, value=label["value"], unit=label["unit"], quote=label.group(), status=status))
                if status == "needs_reading":
                    pending.append(f"{block.span} {cell}：原文数值 {label.group()} 写法异常，保留原样待补读。")
            if cell and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", text) and any(
                c.column == cell[1] and c.row < cell[0] and "用量" in c.text for c in block.cells
            ):
                pending.append(f"{block.span} r{cell[0]}c{cell[1]}：用量 {text.strip()} 未写单位。")
        if "工艺曲线" in block.text:
            pending.append(f"{block.span}：保温点已按原文配对；速率对应的升降温线段仍需结合原页判读。")
    return readings, pending


def save_document_xml(docx_path, output_dir):
    with ZipFile(docx_path) as archive:
        (Path(output_dir) / "document.xml").write_bytes(archive.read("word/document.xml"))
        return len([name for name in archive.namelist() if re.fullmatch(r"word/charts/chart\d+\.xml", name)])
