"""V11.13 原始资料库（scripts/build_library.py 的产物）：一份资料一页一块（span p<页号>）。
检索在调用方已按统一入口筛好的文档里做：有离线页向量且本机能加载 EmbeddingGemma 2 时用它，同时保留关键词；
模型不可用就只用关键词，并在结果里写明。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

from huayan.contracts import Fragment
from huayan.knowledge.store import _grams

READER = Path("config/reader.yaml")
_model = None


def page_key(doc_id, page, text):
    """页向量的键：页文字变了就重编码。"""
    return f"{doc_id}#p{page}@{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}"


class LibrarySource:
    def __init__(self, name, kind, root):
        self.name, self.kind, self.root = name, kind, Path(root)
        sources = json.loads((self.root / "sources.json").read_text(encoding="utf-8"))["sources"]
        self.docs = {s["source_id"]: s for s in sources if s["kind"] == kind}
        self.owners = {d: s["owner_actor_id"] for d, s in self.docs.items() if s["owner_actor_id"]}
        self._pages, self._grams, self._vectors = {}, {}, None

    def list_docs(self):
        return list(self.docs)

    def pages(self, doc_id):
        if doc_id not in self._pages:
            self._pages[doc_id] = json.loads((self.root / "docs" / f"{doc_id}.json").read_text(encoding="utf-8"))["pages"]
        return self._pages[doc_id]

    def images(self, doc_id):
        return json.loads((self.root / "docs" / f"{doc_id}.json").read_text(encoding="utf-8"))["images"]

    def fetch(self, doc_id, span=None):
        fragments = [Fragment(doc_id=doc_id, span=f"p{n}", text=t, level=3 if self.kind == "internal" else 0, source=self.kind,
                              fingerprint=hashlib.sha256(t.encode("utf-8")).hexdigest()[:12])
                     for n, t in enumerate(self.pages(doc_id), 1)]
        return fragments if span is None else next(f for f in fragments if f.span == span)

    def keyword(self, query, k=5, docs=None):
        """关键词：查询的字词有多少出现在这一页（与 FolderSource 同一分词）；返回 (分数, 文档, 页号)。"""
        grams = _grams(query)
        scored = []
        for doc_id in self.docs if docs is None else [d for d in self.docs if d in docs]:
            for n, text in enumerate(self.pages(doc_id), 1):
                if (doc_id, n) not in self._grams:
                    self._grams[(doc_id, n)] = _grams(text)
                if grams and grams & self._grams[(doc_id, n)]:
                    scored.append((len(grams & self._grams[(doc_id, n)]) / len(grams), doc_id, n))
        return sorted(scored, key=lambda x: (-x[0], x[1], x[2]))[:k]

    def search(self, query, k=5) -> list[Fragment]:
        return [self.fetch(d, f"p{n}") for _, d, n in self.keyword(query, k)]

    def vectors(self):
        """离线建好的页向量（scripts/build_library.py --index），读一次。"""
        if self._vectors is None and (self.root / "vectors.npz").exists():
            data = np.load(self.root / "vectors.npz")
            keys = data["keys"].tolist()
            mine = [i for i, key in enumerate(keys) if key.split("#", 1)[0] in self.docs]
            self._vectors = [keys[i] for i in mine], data["vectors"][mine].astype(np.float32)
        return self._vectors


def _retriever():
    """进程里只加载一次；本机没装 torch 或没有本地权重时返回原因，调用方退回关键词。"""
    global _model
    if _model is None:
        from .retrieval import LocalGemmaRetriever

        reader = yaml.safe_load(READER.read_text(encoding="utf-8"))["embedding"]
        try:
            _model = LocalGemmaRetriever(reader["model_id"], cache_dir=reader["cache_dir"])
        except (ImportError, OSError) as e:      # 部署环境没有模型：如实退回关键词
            _model = f"{type(e).__name__}: {e}"
    return _model


def search_library(sources, query, readable, k=5):
    """在 readable（已按统一入口筛过）里检索；返回每条命中的指针、页、摘录、相关度与实际用的方法。"""
    hits, note = {}, None
    for source in sources:
        if not isinstance(source, LibrarySource):
            continue
        for score, doc_id, n in source.keyword(query, k, readable):
            hits[(doc_id, f"p{n}")] = {"source": source, "keyword": round(score, 3)}
        loaded = source.vectors()
        model = _retriever() if loaded else "资料库还没有建页向量"
        if isinstance(model, str):
            note = f"语义检索不可用（{model}），只用了关键词"
            continue
        keys, matrix = loaded
        allowed = [i for i, key in enumerate(keys) if key.split("#", 1)[0] in readable]
        if not allowed:
            continue
        scores = matrix[allowed] @ model.encode_query(query)
        for i in np.argsort(-scores)[:k]:
            doc_id, span = keys[allowed[i]].split("@", 1)[0].split("#", 1)
            hits.setdefault((doc_id, span), {"source": source})["semantic"] = round(float(scores[i]), 3)
    out = []
    for (doc_id, span), h in hits.items():
        f = h["source"].fetch(doc_id, span)
        out.append({"pointer": f"{doc_id}#{span}@{f.fingerprint}", "doc_id": doc_id, "title": h["source"].docs[doc_id]["title"],
                    "page": int(span[1:]), "excerpt": f.text[:240], "level": f.level,
                    "method": "+".join(m for m in ("semantic", "keyword") if m in h),
                    "semantic": h.get("semantic"), "keyword": h.get("keyword")})
    # 语义命中按相似度在前，只有关键词命中的排在后面；两种分数不在一个尺度上，不混排
    out.sort(key=lambda x: (x["semantic"] is None, -(x["semantic"] or 0), -(x["keyword"] or 0)))
    return {"hits": out, "note": note}
