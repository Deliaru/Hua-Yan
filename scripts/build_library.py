"""V11.13 全库登记：OriginalData 每份资料转成 PDF，按页抽文字、渲染页图，按目录定类别与归属；
--index 在本机 GPU 上用 EmbeddingGemma 2 为每页（文字 + 页图）建向量，页指纹没变不重算。
产物在 data/library/（含原文，不入库），由 LibrarySource 读取。

uv run python scripts/build_library.py                # 登记与抽页（Word / PowerPoint 转 PDF，需本机 Office）
uv run python scripts/build_library.py --index        # 建页向量
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT, OUT = Path("OriginalData"), Path("data/library")
# 归属规则（人定，可改）：路径含该段的第一条命中；考点一的题目表、题图、专家反馈含预期答案，按扩展名不登记
RULES = [("染色-MSDS", "public", None, "msds"), ("染色-说明书", "public", None, "sheet"),
         ("染色-试样报告", "internal", "rd:R02", "trial"), ("染色-实验报告", "internal", "rd:R01", "lab"),
         ("染色-产品培训", "internal", "rd:R01", "train"), ("考点一", "internal", "rd:R01", "kd1")]
OFFICE = {".doc": "word", ".docx": "word", ".ppt": "powerpoint", ".pptx": "powerpoint"}
PENDING = "（这一页没有抽出文字，可能是扫描件或图片，待研发补读）"


def to_pdf(path, out, apps):
    """Word / PowerPoint 另存为 PDF；同一个 Office 进程转全部文件。"""
    import win32com.client

    kind = OFFICE[path.suffix.lower()]
    if kind not in apps:
        apps[kind] = win32com.client.DispatchEx("Word.Application" if kind == "word" else "PowerPoint.Application")
        if kind == "word":
            apps[kind].Visible, apps[kind].DisplayAlerts = False, 0
    if kind == "word":
        doc = apps[kind].Documents.Open(str(path.resolve()), ReadOnly=True, AddToRecentFiles=False, Visible=False)
        doc.SaveAs(str(out.resolve()), FileFormat=17)
        doc.Close(SaveChanges=False)
    else:
        deck = apps[kind].Presentations.Open(str(path.resolve()), ReadOnly=True, WithWindow=False)
        deck.SaveAs(str(out.resolve()), 32)
        deck.Close()


def pages_of(pdf, image_dir):
    import pypdfium2 as pdfium

    image_dir.mkdir(parents=True, exist_ok=True)
    texts, images = [], []
    document = pdfium.PdfDocument(pdf)
    for number, page in enumerate(document, 1):
        text = re.sub(r"[ \t]+", " ", page.get_textpage().get_text_range()).strip()
        texts.append(text or PENDING)
        image = image_dir / f"{number}.jpg"
        page.render(scale=1024 / page.get_width()).to_pil().convert("RGB").save(image, quality=80)
        images.append(image.as_posix())
    document.close()
    return texts, images


def register():
    import pythoncom

    pythoncom.CoInitialize()
    (OUT / "docs").mkdir(parents=True, exist_ok=True)
    manifest = OUT / "sources.json"
    known = {s["file"]: s for s in json.loads(manifest.read_text(encoding="utf-8"))["sources"]} if manifest.exists() else {}
    sources, apps = [], {}
    files = [p for p in sorted(ROOT.rglob("*")) if p.suffix.lower() in (".pdf", *OFFICE)]
    for n, path in enumerate(files, 1):
        rule = next((r for r in RULES if r[0] in path.as_posix()), None)
        if rule is None:
            print(f"[{n}/{len(files)}] 没有归属规则，未登记：{path}", flush=True)
            continue
        _, kind, owner, prefix = rule
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        doc_id = f"{prefix}-{sha[:10]}"
        entry = {"source_id": doc_id, "owner_actor_id": owner, "kind": kind, "file": path.as_posix(), "sha256": sha}
        old = known.get(entry["file"])
        if old and old["sha256"] == sha and (OUT / "docs" / f"{doc_id}.json").exists():
            sources.append(old)
            continue
        try:
            pdf = path if path.suffix.lower() == ".pdf" else OUT / "pdf" / f"{doc_id}.pdf"
            if pdf != path:
                pdf.parent.mkdir(parents=True, exist_ok=True)
                to_pdf(path, pdf, apps)
            texts, images = pages_of(pdf, OUT / "pages" / doc_id)
        except Exception as e:     # 坏文件或 Office 打不开：记下来交人处理，其余照登记
            print(f"[{n}/{len(files)}] 读不了 {path}：{type(e).__name__}: {e}", flush=True)
            continue
        (OUT / "docs" / f"{doc_id}.json").write_text(json.dumps(
            {"doc_id": doc_id, "title": path.name, "pages": texts, "images": images}, ensure_ascii=False), encoding="utf-8")
        sources.append(entry | {"title": path.name, "pages": len(texts), "pending_pages": texts.count(PENDING)})
        print(f"[{n}/{len(files)}] {doc_id} {path.name} {len(texts)} 页", flush=True)
        manifest.write_text(json.dumps({"sources": sources + [s for f, s in known.items()
                            if f not in {x["file"] for x in sources}]}, ensure_ascii=False, indent=1), encoding="utf-8")
    for app in apps.values():
        app.Quit()
    manifest.write_text(json.dumps({"sources": sources}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"登记 {len(sources)} 份，{sum(s['pages'] for s in sources)} 页，待补读 {sum(s['pending_pages'] for s in sources)} 页")


def index():
    from huayan.ingest.reader.retrieval import LocalGemmaRetriever
    from huayan.ingest.reader.library import page_key

    reader = yaml.safe_load(Path("config/reader.yaml").read_text(encoding="utf-8"))["embedding"]
    model = LocalGemmaRetriever(reader["model_id"], cache_dir=reader["cache_dir"])
    path = OUT / "vectors.npz"
    old = dict(np.load(path)) if path.exists() else {"keys": np.array([]), "vectors": np.zeros((0, 768), np.float16)}
    have = dict(zip(old["keys"].tolist(), old["vectors"]))
    todo = []
    for s in json.loads((OUT / "sources.json").read_text(encoding="utf-8"))["sources"]:
        doc = json.loads((OUT / "docs" / f"{s['source_id']}.json").read_text(encoding="utf-8"))
        todo += [(page_key(s["source_id"], n, t), t, img) for n, (t, img) in enumerate(zip(doc["pages"], doc["images"]), 1)]
    missing = [x for x in todo if x[0] not in have]
    print(f"共 {len(todo)} 页，要编码 {len(missing)} 页（{model.metadata}）", flush=True)
    for start in range(0, len(missing), 64):
        batch = missing[start:start + 64]
        for (key, _, _), vector in zip(batch, model.encode_pages([(t, img) for _, t, img in batch])):
            have[key] = vector.astype(np.float16)
        print(f"  {start + len(batch)}/{len(missing)}", flush=True)
        keys = [x[0] for x in todo if x[0] in have]
        np.savez(path, keys=np.array(keys), vectors=np.stack([have[k] for k in keys]),
                 model=np.array(json.dumps(model.metadata)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", action="store_true")
    index() if parser.parse_args().index else register()
