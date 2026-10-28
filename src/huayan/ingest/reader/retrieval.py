# src/huayan/ingest/reader/retrieval.py
import os
import torch
import torch.nn.functional as F
from PIL import Image
from typing import List
from transformers import AutoProcessor, AutoModel

class EmbeddingGemmaEngine:
    """
    化言方案 B v3 本地多模态检索模块：
    1. 跑在 RTX 4060 本地 GPU 上 (bfloat16)
    2. 输出规范 768 维 L2 归一化向量
    3. 承接切片前缀与查询前缀
    """
    def __init__(self, model_id: str = "google/embeddinggemma-2"):
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.bfloat16 if self.device.type == "cuda" else torch.float32

        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(
            model_id,
            torch_dtype=self.dtype,
            device_map=self.device
        )
        self.model.eval()

    def encode_documents(self, titles: List[str], texts: List[str]) -> torch.Tensor:
        """
        对文档/切片批量编码。
        文档规范要求：挂接条件头作为 title，无标题填 none。
        """
        formatted = [
            f"title: {t.strip() if t else 'none'} | text: {txt.strip()}"
            for t, txt in zip(titles, texts)
        ]
        inputs = self.processor(
            text=formatted,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            embeddings = F.normalize(outputs.sentence_embedding, p=2, dim=1)
        return embeddings

    def encode_query(self, query: str, task: str = "search result") -> torch.Tensor:
        """
        对提问 Query 编码。
        """
        formatted = f"task: {task} | query: {query.strip()}"
        inputs = self.processor(text=[formatted], return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            embeddings = F.normalize(outputs.sentence_embedding, p=2, dim=1)
        return embeddings

    def encode_images(self, images: List[Image.Image]) -> torch.Tensor:
        """
        对原页渲染图或图表裁图编码（不加前缀）。
        """
        inputs = self.processor(images=images, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            embeddings = F.normalize(outputs.sentence_embedding, p=2, dim=1)
        return embeddings