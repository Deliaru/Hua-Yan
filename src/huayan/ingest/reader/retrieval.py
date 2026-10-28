# -*- coding: utf-8 -*-
"""
src/huayan/ingest/reader/retrieval.py
基于本地 google/embeddinggemma-2 (768-dim, bfloat16) 的向量编码与检索模块
"""

import os
from typing import List, Dict, Any, Optional
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModel

# 强制指向 D 盘缓存，保护 C 盘空间
os.environ["HF_HOME"] = "D:/hf_cache"
os.environ["HF_HUB_CACHE"] = "D:/hf_cache/hub"

MODEL_ID = "google/embeddinggemma-2"


class LocalGemmaRetriever:
    """本地 EmbeddingGemma-2 768维检索器"""

    def __init__(self, model_id: str = MODEL_ID, device: Optional[str] = None):
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.bfloat16 if self.device == "cuda" else torch.float32

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, 
            cache_dir="D:/hf_cache"
        )
        self.model = AutoModel.from_pretrained(
            self.model_id,
            torch_dtype=self.dtype,
            cache_dir="D:/hf_cache"
        ).to(self.device)
        self.model.eval()

    @torch.no_grad()
    def encode(self, texts: List[str], batch_size: int = 16) -> np.ndarray:
        """
        将文本列表编码为 (N, 768) 的 L2 归一化向量矩阵
        """
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            inputs = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=1024,
                return_tensors="pt"
            ).to(self.device)

            outputs = self.model(**inputs)
            
            # Mean Pooling (结合 attention_mask 均值池化)
            token_embeddings = outputs.last_hidden_state
            attention_mask = inputs["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
            sum_embeddings = torch.sum(token_embeddings.float() * attention_mask, dim=1)
            sum_mask = torch.clamp(attention_mask.sum(dim=1), min=1e-9)
            pooled = sum_embeddings / sum_mask

            # L2 归一化，便于直接用矩阵点积计算余弦相似度
            normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
            all_embeddings.append(normalized.cpu().numpy())

        return np.vstack(all_embeddings)

    def search_and_verify(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        chunk_embeddings: np.ndarray,
        top_k: int = 3,
        enable_jev_gate: bool = True
    ) -> List[Dict[str, Any]]:
        """
        向量 Top-K 召回 + Cloudflare Jev 证据门控二阶段精筛
        chunks 格式示例: [{"chunk_id": "c1", "text": "..."}, ...]
        """
        from .verify import verify_evidence_gate

        query_vec = self.encode([query])[0]  # (768,)
        scores = np.dot(chunk_embeddings, query_vec)  # (N,)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            item = dict(chunks[idx])
            item["similarity"] = float(scores[idx])

            if enable_jev_gate:
                gate_res = verify_evidence_gate(
                    chunk_text=item.get("text", ""),
                    query_claim=query
                )
                item["jev_verification"] = gate_res
                item["verified_passed"] = gate_res["passed"]
            
            results.append(item)

        return results