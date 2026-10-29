"""读取侧本地 EmbeddingGemma 2 图文检索；关键词沿用知识库的分词规则。"""
from pathlib import Path

import numpy as np

from huayan.knowledge.store import _grams


MODEL_ID = "google/embeddinggemma-2"


def keyword_search(query, chunks, top_k=3):
    grams = _grams(query)
    scored = [(len(grams & _grams(chunk["text"])) / len(grams), chunk)
              for chunk in chunks if grams]
    return [dict(chunk, similarity=score) for score, chunk in
            sorted(scored, key=lambda item: -item[0]) if score > 0][:top_k]


class LocalGemmaRetriever:
    """只加载已有本地权重；查询与文档分别使用模型规定的前缀。"""

    def __init__(self, model_id=MODEL_ID, device=None, cache_dir=None):
        import torch
        from huggingface_hub import snapshot_download
        from transformers import AutoConfig, AutoModel, AutoProcessor

        self.torch = torch
        self.model_id = model_id
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.bfloat16 if self.device.startswith("cuda") and torch.cuda.is_bf16_supported() else torch.float32
        snapshot = snapshot_download(model_id, cache_dir=cache_dir, local_files_only=True)
        config = AutoConfig.from_pretrained(snapshot, local_files_only=True)
        config.audio_config = None  # 当前只处理报告文字和页面图片。
        self.processor = AutoProcessor.from_pretrained(snapshot, local_files_only=True)
        self.model = AutoModel.from_pretrained(snapshot, config=config, dtype=self.dtype, local_files_only=True).to(self.device).eval()
        self.metadata = {"model": model_id, "revision": Path(snapshot).name, "device": self.device,
                         "dtype": str(self.dtype), "dimensions": config.text_config.embedding_dim,
                         "modalities": ["text", "image"]}

    def _embed(self, inputs):
        inputs = inputs.to(device=self.device, dtype=self.dtype)
        with self.torch.inference_mode():
            # 此模型的 last_hidden_state 已经过 512→768 投影，按有效 token 均值池化即可。
            tokens = self.model(**inputs).last_hidden_state.float()
            mask = inputs["attention_mask"].unsqueeze(-1).float()
            pooled = (tokens * mask).sum(dim=1) / mask.sum(dim=1)
            return self.torch.nn.functional.normalize(pooled, p=2, dim=1).cpu().numpy()

    def encode(self, texts, batch_size=16):
        """文档文本编码；保留原有 encode 入口。"""
        vectors = []
        for start in range(0, len(texts), batch_size):
            inputs = self.processor(text=[f"title: none | text: {text}" for text in texts[start:start + batch_size]],
                                    padding=True, truncation=True, max_length=8192, return_tensors="pt")
            vectors.append(self._embed(inputs))
        return np.vstack(vectors)

    def encode_query(self, query):
        inputs = self.processor(text=[f"task: search result | query: {query}"],
                                truncation=True, max_length=8192, return_tensors="pt")
        return self._embed(inputs)[0]

    def encode_pages(self, pages, batch_size=4):
        """pages 为 (原生文字, 原生页图路径)；一页对应一个图文向量。"""
        from PIL import Image

        vectors = []
        for start in range(0, len(pages), batch_size):
            batch = pages[start:start + batch_size]
            images = []
            for _, path in batch:
                with Image.open(path) as image:
                    images.append([image.convert("RGB")])
            inputs = self.processor(text=[f"title: none | text: {text} <|image|>" for text, _ in batch],
                                    images=images, padding=True, truncation=True, max_length=8192, return_tensors="pt")
            vectors.append(self._embed(inputs))
        return np.vstack(vectors)

    def search_and_verify(self, query, chunks, chunk_embeddings, top_k=3, verifier=None):
        """保留来源字段；Jev 只附辅助核对，不替代读数或人的确认。"""
        scores = chunk_embeddings @ self.encode_query(query)
        results = [dict(chunks[index], similarity=float(scores[index]))
                   for index in np.argsort(-scores, kind="stable")[:top_k]]
        if verifier is not None:
            for item in results:
                item["jev_verification"] = verifier.verify_evidence_gate(item["text"], query)
        return results
