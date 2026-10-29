"""当前样例的 DOC/DOCX 原生 Word 转换；不使用 LibreOffice。"""
import shutil
from pathlib import Path
from zipfile import ZipFile


def word_format(path):
    with Path(path).open("rb") as stream:
        header = stream.read(8)
    if header == bytes.fromhex("d0cf11e0a1b11ae1"):
        return "doc"
    if header.startswith(b"PK\x03\x04"):
        with ZipFile(path) as archive:
            if "word/document.xml" in archive.namelist():
                return "docx"
    raise ValueError("当前读取器仅处理 Word DOC/DOCX；文件头不匹配")


def export_word(path, output_dir):
    import pythoncom
    import win32com.client
    import pypdfium2 as pdfium

    file_format = word_format(path)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    local = output / f"original.{file_format}"
    shutil.copyfile(path, local)
    docx, pdf = output / "reading.docx", output / "original.pdf"
    pages = {}
    pythoncom.CoInitialize()
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible, word.DisplayAlerts, word.AutomationSecurity = False, 0, 3
        try:
            document = word.Documents.Open(str(local), ReadOnly=True, AddToRecentFiles=False, Visible=False)
            try:
                document.Repaginate()
                document.SaveAs(str(pdf), FileFormat=17)
                document.SaveAs(str(docx), FileFormat=12)

                def page_numbers(rng):
                    first = document.Range(rng.Start, rng.Start).Information(3)
                    last = document.Range(rng.End - 1, rng.End - 1).Information(3)
                    return list(range(first, last + 1))

                paragraph_number = 0
                for paragraph in document.Paragraphs:
                    if not paragraph.Range.Information(12):  # wdWithInTable；与 python-docx 顶层段落一致
                        paragraph_number += 1
                        pages[f"paragraph-{paragraph_number}"] = page_numbers(paragraph.Range)
                for number, table in enumerate(document.Tables, 1):
                    pages[f"table-{number}"] = page_numbers(table.Range)
                renderer = f"Microsoft Word {word.Version} COM"
            finally:
                document.Close(SaveChanges=False)
        finally:
            if word.Documents.Count == 0:
                word.Quit()
    finally:
        pythoncom.CoUninitialize()

    images = []
    with pdfium.PdfDocument(str(pdf)) as rendered:
        for number in range(len(rendered)):
            image_path = output / f"page-{number + 1:02d}.png"
            page = rendered[number]
            bitmap = page.render(scale=1.8)
            bitmap.to_pil().save(image_path)
            bitmap.close()
            page.close()
            images.append(str(image_path))
    return {"format": file_format, "reading_copy": str(docx), "preview_pdf": str(pdf),
            "images": images, "pages": pages, "renderer": renderer}
