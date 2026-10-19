"""替身 RAG：一个来源就是一个文件夹。.md/.txt 按空行分段（span 为 p<序号>）；
.csv 每条记录是一个文档（doc_id 为 <文件名>#<首列>），每列一段（span 为列名）。"""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

from huayan.contracts import Fragment
from huayan.knowledge.store import _grams


class FolderSource:
    def __init__(self, name, kind, root, level=None, doc_levels=None):
        self.name, self.kind, self.root, self.level = name, kind, Path(root), level
        self.doc_levels = {} if doc_levels is None else doc_levels     # 片段密级表（按文档，人设定）

    def _docs(self) -> dict[str, list[tuple[str, str]]]:
        docs = {}
        for path in sorted(self.root.rglob("*")):
            stem = path.relative_to(self.root).with_suffix("").as_posix()
            if path.suffix in (".md", ".txt"):
                parts = [p.strip() for p in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")) if p.strip()]
                docs[stem] = [(f"p{n}", text) for n, text in enumerate(parts, 1)]
            elif path.suffix == ".csv":
                with path.open(encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        key = next(iter(row.values()))
                        docs[f"{stem}#{key}"] = [(col, text) for col, text in row.items() if text]
        return docs

    def _level(self, doc_id):
        if self.kind != "internal":
            return 0
        return self.doc_levels.get(doc_id, 3 if self.level is None else self.level)

    def _fragment(self, doc_id, span, text):
        return Fragment(doc_id=doc_id, span=span, text=text, level=self._level(doc_id), source=self.kind,
                        fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12])

    def list_docs(self) -> list[str]:
        return list(self._docs())

    def fetch(self, doc_id, span=None):
        """span 为空时返回该文档的全部段；文档或段不存在抛 KeyError（= 指针失效）。"""
        parts = dict(self._docs()[doc_id])
        if span is None:
            return [self._fragment(doc_id, s, t) for s, t in parts.items()]
        return self._fragment(doc_id, span, parts[span])

    def search(self, query, k=5) -> list[Fragment]:
        grams = _grams(query)
        scored = [(len(grams & _grams(text)) / len(grams), doc_id, span, text)
                  for doc_id, parts in self._docs().items() for span, text in parts if grams]
        return [self._fragment(d, s, t) for score, d, s, t in sorted(scored, key=lambda x: (-x[0], x[1], x[2]))
                if score > 0][:k]
