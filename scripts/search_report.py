"""对一份已读取报告按页检索，默认本地 Gemma 图文；--keywords 对照，--jev 附辅助核对。

读取开发者本地 evidence.json，不是面向角色的公共资料读取入口；不写正式知识状态。
"""
import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from huayan.ingest.reader.evidence import EvidenceBlock
from huayan.ingest.reader.retrieval import LocalGemmaRetriever, keyword_search
from huayan.ingest.reader.verify import ClefWorkerClient, JevVerifier
from huayan.meter import FileMeter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--config", default="config/reader.yaml")
    parser.add_argument("--out", default="data/knowledge_v10/retrieval")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--keywords", action="store_true")
    parser.add_argument("--jev", action="store_true")
    args = parser.parse_args()
    if not args.query.strip() or args.top_k < 1:
        parser.error("query 不能为空，top-k 必须为正整数")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    blocks = [EvidenceBlock.model_validate(block) for block in evidence["blocks"]]
    chunks = []
    for page, image in enumerate(evidence["images"], 1):
        page_blocks = [block for block in blocks if page in [loc.page for loc in block.locations]]
        chunks.append({"chunk_id": f'{evidence["source_id"]}#page-{page}', "page": page,
                       "file_sha256": evidence["file_sha256"], "image_path": image,
                       "text": "\n\n".join(block.text for block in page_blocks),
                       "fragments": [block.fragment().model_dump(mode="json") for block in page_blocks]})
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    retriever = None
    metadata = {"method": "keyword", "degraded": False}
    if not args.keywords:
        try:
            retriever = LocalGemmaRetriever(**config["embedding"])
        except (ImportError, OSError) as error:
            metadata.update(degraded=True, reason=f"本地嵌入不可用，退回关键词：{error}")
    if retriever is None:
        hits = keyword_search(args.query, chunks, args.top_k)
    else:
        vectors = retriever.encode_pages([(chunk["text"], chunk["image_path"]) for chunk in chunks])
        np.save(output / "page_embeddings.npy", vectors)
        hits = retriever.search_and_verify(args.query, chunks, vectors, args.top_k)
        metadata = {"method": "embeddinggemma-2-text-image", "degraded": False, **retriever.metadata}
    report = {"query": args.query, "source_id": evidence["source_id"], "retrieval": metadata,
              "jev_status": "pending" if args.jev else "off", "hits": hits}
    path = output / "retrieval.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.jev:
        client = ClefWorkerClient(meter=FileMeter(output, "reader_search"), **config["jev"])
        try:
            verifier = JevVerifier(client)
            for hit in hits:
                hit["jev_verification"] = verifier.verify_evidence_gate(hit["text"], args.query)
            report.update(jev_status="on", jev_model=client.model)
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            client.close()
    print(json.dumps({"retrieval": metadata, "jev_status": report["jev_status"],
                      "pages": [hit["page"] for hit in hits], "output": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
