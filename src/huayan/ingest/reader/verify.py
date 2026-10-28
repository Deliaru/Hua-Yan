# -*- coding: utf-8 -*-
"""
src/huayan/ingest/reader/verify.py
基于 Cloudflare Workers AI 的免 Key 结构化证据审查与字段核对引擎 (Jev)
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional
import requests

logger = logging.getLogger(__name__)

# 默认使用你已部署成功的 Cloudflare Worker 地址，也支持通过环境变量覆盖
DEFAULT_WORKER_URL = os.getenv(
    "HUAYAN_JEV_WORKER_URL", 
    "https://jev-proxy.xi1092183542.workers.dev"
)


class JevVerifier:
    """Jev 结构化事实核对客户端"""

    def __init__(
        self, 
        worker_url: str = DEFAULT_WORKER_URL, 
        timeout: int = 20, 
        max_retries: int = 2
    ):
        self.worker_url = worker_url
        self.timeout = timeout
        self.max_retries = max_retries

    def _call_worker(self, state_text: str, question: str) -> Dict[str, Any]:
        """底层调用 Cloudflare Worker AI 接口"""
        payload = {
            "state": state_text,
            "question": question
        }

        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    self.worker_url, 
                    json=payload, 
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "result": bool(data.get("result", False)),
                        "confidence": float(data.get("confidence", 0.0)),
                        "reason": str(data.get("reason", ""))
                    }
                else:
                    logger.warning(f"Jev Worker HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.warning(f"Jev Worker 调用异常 (第 {attempt + 1} 次尝试): {e}")
            
            if attempt < self.max_retries:
                time.sleep(1.0)

        # 兜底返回，防止网络波动中断整个批处理管线
        return {
            "result": False,
            "confidence": 0.0,
            "reason": "网关请求超时或失败，触发安全降级"
        }

    def verify_field_direct(
        self, 
        source_text: str, 
        field_name: str, 
        extracted_value: Any
    ) -> Dict[str, Any]:
        """
        1. 字段核对：核对抽取出的字段值是否由原文明确写出或可直接推出
        """
        question = f"抽取结论：字段【{field_name}】的值为“{extracted_value}”，是否有原文明确证据支持？"
        res = self._call_worker(state_text=source_text, question=question)
        return {
            "id": f"verify_field_{field_name}",
            "type": "field_check",
            "field": field_name,
            "value": extracted_value,
            **res
        }

    def verify_evidence_gate(
        self, 
        chunk_text: str, 
        query_claim: str, 
        min_confidence: float = 0.7
    ) -> Dict[str, Any]:
        """
        2. 证据门控：判断召回的文档切片是否真正包含回答问题或支撑结论所需的证据
        """
        question = f"该原文片段是否包含能够直接支撑或回答“{query_claim}”的有效证据？"
        res = self._call_worker(state_text=chunk_text, question=question)
        passed = res["result"] and (res["confidence"] >= min_confidence)
        return {
            "id": "verify_evidence_gate",
            "type": "evidence_gate",
            "passed": passed,
            **res
        }

    def verify_conflict(
        self, 
        statement_a: str, 
        statement_b: str
    ) -> Dict[str, Any]:
        """
        3. 冲突/一致性核对：判断两条实验记录或工艺参数之间是否存在直接矛盾
        """
        state_text = f"【记录 A】：{statement_a}\n【记录 B】：{statement_b}"
        question = "【记录 A】与【记录 B】在相同实验条件下的核心结论或数值是否存在直接冲突/矛盾？（若存在矛盾则 result 为 true，一致或互补则为 false）"
        res = self._call_worker(state_text=state_text, question=question)
        return {
            "id": "verify_conflict",
            "type": "conflict_check",
            "has_conflict": res["result"],
            **res
        }


# 提供模块级快捷调用实例
default_verifier = JevVerifier()

def verify_field_direct(source_text: str, field_name: str, extracted_value: Any) -> Dict[str, Any]:
    return default_verifier.verify_field_direct(source_text, field_name, extracted_value)

def verify_evidence_gate(chunk_text: str, query_claim: str, min_confidence: float = 0.7) -> Dict[str, Any]:
    return default_verifier.verify_evidence_gate(chunk_text, query_claim, min_confidence)

def verify_conflict(statement_a: str, statement_b: str) -> Dict[str, Any]:
    return default_verifier.verify_conflict(statement_a, statement_b)