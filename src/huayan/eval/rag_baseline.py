"""V12.9 普通 RAG 对照（只在 eval/，业务代码不引用）：同一批资料、同一个模型，检索到的页原文直接交模型作答，
不经过觉、Jev、契，也不按岗位分层——资料库里全部资料（内部 + 公开）都进检索，这就是常见企业 RAG 的做法。caller baseline:rag。"""
from huayan.contracts import LLMRequest, Message, Tier
from huayan.ingest.reader.library import search_library

PROMPT = ("你是印染助剂企业的客服助手。根据下面检索到的资料回答客户的问题，给出推荐的产品和用法；"
          "资料里没有依据的不要编。回答用中文，不超过 150 字。")


def answer(sources, question, gateway, k=5):
    every = {d for s in sources for d in s.list_docs()}
    hits = search_library(sources, question, every, k)["hits"]
    context = "\n\n".join(f"【{h['title']} 第 {h['page']} 页】\n{h['excerpt']}" for h in hits)
    response = gateway.complete(LLMRequest(tier=Tier.FAST, caller="baseline:rag", temperature=0, messages=[
        Message(role="system", content=PROMPT), Message(role="user", content=f"资料：\n{context}\n\n客户：{question}")]))
    return {"question": question, "answer": response.content or "", "model": response.model,
            "hits": [{k: h[k] for k in ("doc_id", "title", "page", "level", "excerpt")} for h in hits]}
