"""生成测试专用合成材料；所有名称与数值均不对应企业报告。"""
import json
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml


root = Path(__file__).parent
doc = Document()
doc.add_paragraph("合成试样报告，不是真实实验数据")
doc.add_paragraph("二、试样基本信息")
doc.add_paragraph("合成样品，液量100kg")
for heading, name, amount, curve in [
    ("三、工厂原工艺及配方", "SYNTH-A", "7", "工艺曲线\n85℃*12min\n0..7℃/min"),
    ("四、试样工艺及配方", "SYNTH-B", "2kg", "试样工艺曲线\n95℃*6min\n1.2℃/min"),
]:
    doc.add_paragraph(heading)
    table = doc.add_table(rows=3, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "项目", "用量"
    table.cell(1, 0).text, table.cell(1, 1).text = name, amount
    table.cell(2, 0).merge(table.cell(2, 1)).text = curve
doc.add_paragraph("五、试样结果分析")
doc.add_paragraph("合成结果：总时间90min。")
paragraph = doc.add_paragraph()
paragraph._p.append(parse_xml('''<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
xmlns:v="urn:schemas-microsoft-com:vml"><w:pict><v:shape><v:textbox><w:txbxContent>
<w:p><w:r><w:t>合成文本框 30℃</w:t></w:r></w:p>
</w:txbxContent></v:textbox></v:shape></w:pict></w:r>'''))
doc.save(root / "synthetic.docx")
pages = {f"paragraph-{i}": [1] for i in range(1, len(doc.paragraphs) + 1)}
pages.update({f"table-{i}": [1] for i in range(1, len(doc.tables) + 1)})
(root / "pages.json").write_text(json.dumps(pages, indent=2) + "\n", encoding="utf-8")
