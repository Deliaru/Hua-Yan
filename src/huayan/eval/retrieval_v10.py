"""单题A/C与Jev开关展示；答案只在预测落盘后用于事后核对。"""
import argparse
from base64 import b64decode
from hashlib import sha256
import html
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml

from huayan.app import HuayanApp
from huayan.gateway import build_gateway
from huayan.ingest.reader.chart_qa import answer_chart
from huayan.ingest.reader.image import image_data_url
from huayan.ingest.reader.retrieval import LocalGemmaRetriever, keyword_search, source_pages
from huayan.ingest.reader.verify import JevVerifier
from huayan.jev.system1 import build_system1
from huayan.meter import FileMeter


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="隔离演示配置，来源须事先登记归属")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--question-id", default="03-Q03")
    parser.add_argument("--questions", default="data/knowledge_v10/evaluations/questions.jsonl")
    parser.add_argument("--gold", default="data/knowledge_v10/evaluations/verified_charts.json")
    parser.add_argument("--reader", default="config/reader.yaml")
    parser.add_argument("--models", default="config/models.yaml")
    parser.add_argument("--system1", default="config/system1.cloudflare-worker.yaml")
    parser.add_argument("--out", required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    question = next(json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
                    if line and json.loads(line)["question_id"] == args.question_id)
    query = question["question"].strip()
    app = HuayanApp.build(args.config, "retrieval-demo", resume=True)
    state_before = sha256(app.kb.state_path.read_bytes()).hexdigest()
    doc_ids = [s.name for s in app.kb.sources]
    chunks = source_pages(app.kb, app.actors[args.actor], app.source_owners, doc_ids)
    inputs = {str(s.path): sha256(s.path.read_bytes()).hexdigest() for s in app.kb.sources}
    inputs.update({c["image_path"]: sha256(Path(c["image_path"]).read_bytes()).hexdigest() for c in chunks})
    inputs.update({p: sha256(Path(p).read_bytes()).hexdigest() for p in
        [args.config, args.models, args.reader, args.system1, "prompts/chart_qa.md"]})
    reader = yaml.safe_load(Path(args.reader).read_text(encoding="utf-8"))
    started = perf_counter()
    retriever = LocalGemmaRetriever(**reader["embedding"])
    # 两组使用同一批页面；图文向量只在本机生成，不下载权重。
    vectors = retriever.encode_pages([(c["text"], c["image_path"]) for c in chunks], batch_size=1)
    np.save(output / "page_embeddings.npy", vectors)
    indexing_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    a_hits = keyword_search(query, chunks, top_k=3)
    a_ms = (perf_counter() - started) * 1000
    started = perf_counter()
    c_hits = retriever.search_and_verify(query, chunks, vectors, top_k=3)
    c_ms = (perf_counter() - started) * 1000
    write_json(output / "retrieval.json", {"query": query, "A": a_hits, "C": c_hits})
    meter = FileMeter(output, "v10.3-retrieval")
    gateway = build_gateway(args.models, False, meter)
    gateway.cache_dir = Path("data/knowledge_v10/cache/retrieval-qa")
    gateway.replay = args.replay
    traces = []

    def trace(event, **fields):
        row = {"event": event, **fields}
        traces.append(row)
        with (output / "gateway-trace.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    gateway.trace = trace
    jev = build_system1("onejev", args.system1, gateway, meter)
    jev.trace = trace
    verifier = JevVerifier(jev)
    predictions = []
    try:
        for name, original, retrieval_ms, jev_on in [("A关键词", a_hits, a_ms, False),
                ("C图文", c_hits, c_ms, False), ("C图文+Jev", c_hits, c_ms, True)]:
            start = perf_counter()
            trace_start = len(traces)
            hits = [dict(hit) for hit in original]
            if jev_on:
                for hit in hits:
                    hit["verification"] = verifier.verify_evidence_gate(hit["text"], query)
                hits.sort(key=lambda h: -h["verification"]["probabilities"]["yes"])
            hit = hits[0] if hits else None
            record = {"configuration": name, "retrieval_ms": retrieval_ms, "jev": jev_on,
                      "candidates": [{"source_id": h["source_id"], "page": h["page"],
                          "similarity": h["similarity"], "verification": h.get("verification")} for h in hits],
                      "selected": None, "answer": None, "response": None}
            if hit is not None and (not jev_on or hit["verification"]["passed"]):
                # 仅回取实际选中的1页；Jev只看同一候选池的原生文字，不读金标或其他页图。
                image = app.read_source_image(hit["source_id"], hit["page"], args.actor)
                url = image_data_url(b64decode(image["image_url"].split(",", 1)[1]))
                answer, response = answer_chart(query, hit, url, gateway)
                record.update(selected={"source_id": hit["source_id"], "page": hit["page"],
                    "file_sha256": hit["file_sha256"], "fragments": hit["fragments"],
                    "image_fingerprint": image["fingerprint"]}, answer=answer.model_dump(mode="json"),
                    response={"model": response.model, "fallback_used": response.fallback_used}, image_url=url)
            record["elapsed_ms"] = (perf_counter() - start) * 1000 + retrieval_ms
            activity = traces[trace_start:]
            record["llm_network_requests"] = sum(t["event"] == "llm_request" for t in activity)
            record["llm_cache_hits"] = sum(t["event"] == "llm" and t["cached"] for t in activity)
            record["s1_cache_hits"] = sum(t["event"] == "s1" and t["cached"] for t in activity)
            predictions.append(record)
            write_json(output / "predictions.json", {"query": query, "results": predictions})
    finally:
        jev.close()
        app.system1.close()
        for client in gateway.clients.values():
            client.close()
    # 金标从这里才进入核对；不送入检索、Jev、视觉模型或正式业务。
    gold = next(g for g in json.loads(Path(args.gold).read_text(encoding="utf-8")) if g["question_id"] == args.question_id)
    for record in predictions:
        chosen = record["selected"]
        page_match = chosen is not None and (chosen["source_id"], chosen["page"], chosen["file_sha256"]) == (
            gold["source_id"], gold["slide"], gold["source_sha256"])
        values = record["answer"]["values"] if record["answer"] else []
        checks = []
        for expected in gold["checked_values"]:
            found = [v for v in values if v["metric"] == expected["metric"]]
            checks.append({"metric": expected["metric"], "expected": expected,
                "actual": found, "matches": any(v["value"] == str(expected["value"])
                    and v["unit"] == expected["unit_raw"]
                    and v["cell"] == gold["source_table_cells"]["row_column_one_based"][expected["metric"]] for v in found)})
        condition_text = "".join("".join(v["conditions"]) for v in values).replace(" ", "")
        conditions_match = (all(v["object"] == gold["cell_selection"]["product"] for v in values)
            and all(gold["cell_selection"][key] in condition_text for key in ["dosage_raw", "NaOH_raw"]))
        fragments = {f["span"]: f["text"] for f in chosen["fragments"]} if chosen else {}
        citations_match = bool(values) and all(v["span"] in fragments and v["quote"]
            and v["quote"] in fragments[v["span"]] for v in values)
        record["evaluation"] = {"page_matches": page_match, "values": checks,
            "query_conditions_present": conditions_match,
            "citations_match": citations_match,
            "passed": page_match and all(c["matches"] for c in checks) and conditions_match and citations_match}
    assert state_before == sha256(app.kb.state_path.read_bytes()).hexdigest()
    assert all(sha256(Path(p).read_bytes()).hexdigest() == value for p, value in inputs.items())
    summary = {"question_id": args.question_id, "query": query, "scope": "单个已知开发题，非盲测或全库正确率",
        "actor": args.actor, "simulated_source_assignment": True, "corpus_sources": doc_ids, "corpus_pages": len(chunks),
        "candidate_pool": 3, "answer_page_budget": 1, "indexing_ms": indexing_ms,
        "embedding": retriever.metadata, "models_config": args.models, "replay": args.replay,
        "input_sha256": inputs, "knowledge_state_sha256": state_before,
        "llm_network_requests": sum(t["event"] == "llm_request" for t in traces),
        "llm_cache_hits": sum(t["event"] == "llm" and t["cached"] for t in traces),
        "s1_network_responses": sum(t["event"] == "s1" and not t["cached"] for t in traces),
        "s1_cache_hits": sum(t["event"] == "s1" and t["cached"] for t in traces),
        "inputs_unchanged": True, "knowledge_state_unchanged": True, "results": predictions}
    write_json(output / "summary.json", summary)
    render(summary, output)
    print(json.dumps({"output": str(output / "review.html"), "passed": [r["evaluation"]["passed"] for r in predictions],
        "llm_network_requests": summary["llm_network_requests"], "llm_cache_hits": summary["llm_cache_hits"]}, ensure_ascii=False))


def render(summary, output):
    e = html.escape
    rows, sections = [], []
    for r in summary["results"]:
        selected = r["selected"]
        location = f'{selected["source_id"]} · 第{selected["page"]}页' if selected else "未通过证据门控"
        rows.append(f'<tr><td>{e(r["configuration"])}</td><td>{e(location)}</td><td>{r["evaluation"]["passed"]}</td>'
                    f'<td>{r["elapsed_ms"]/1000:.2f}s</td><td>网络{r["llm_network_requests"]} / 缓存{r["llm_cache_hits"]}</td></tr>')
        sections.append(f'<section><h2>{e(r["configuration"])}</h2><p>{e(location)}</p>')
        if not r["evaluation"]["passed"]:
            sections.append('<p class="notice">本配置未通过本题核对。以下为失败辅助稿，不是正确答案或可直接使用的工艺说明。</p>')
        sections.append('<p>开发用原生核对值：' + e('；'.join(
            f'{c["metric"]} {c["expected"]["value"]}{c["expected"]["unit_raw"]}' for c in r["evaluation"]["values"])) + '</p>')
        if r["answer"]:
            sections.append(f'<p>{e(r["answer"]["answer"])}</p><p>模型：{e(r["response"]["model"])}；'
                f'降级：{r["response"]["fallback_used"]}；待人工审阅</p><img src="{r["image_url"]}" alt="命中页原生图">')
            sections.append('<p>原生合并表格优先由模型选择记录、读取器取回原值/单位/所属表头；此时原页图仅供审阅，不发送给作答模型。无原生合并表记录的页面才用图片辅助。</p>')
            table_spans = {v["span"] for v in r["answer"]["values"]}
            sections.append('<h3>原页方法与上下文（原文）</h3><ul>' + ''.join(
                '<li>' + e(f["text"]) + '</li>' for f in selected["fragments"] if f["span"] not in table_spans) + '</ul>')
        sections.append('<details><summary>读数、条件、出处及逐项核对</summary><pre>' +
            e(json.dumps({k: v for k, v in r.items() if k != "image_url"}, ensure_ascii=False, indent=2)) + '</pre></details></section>')
    document = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V10.3 单题检索与查证</title>'
    document += '<style>body{font:16px/1.7 Microsoft YaHei,sans-serif;max-width:1200px;margin:30px auto;padding:0 20px;color:#173047}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd7e3;padding:12px}section{margin:30px 0;padding:20px;border:1px solid #ccd7e3;border-radius:12px}img{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5fa;padding:16px}.notice{padding:18px;background:#fff3db}</style>'
    document += '<h1>V10.3 · 一道图表题，从检索到引用</h1><p class="notice">真实内部PPT、真实本地Gemma、Qwen视觉与Cloudflare Clef；'
    document += '单个已知开发题，不是盲测。来源归属为隔离演示指定，不改原清单；无专业签字、授权或正式业务写入。</p>'
    document += f'<p>{e(summary["query"])}</p><p>来源{len(summary["corpus_sources"])}份 / {summary["corpus_pages"]}页；候选池3页，作答预算1页；'
    document += f'模型索引耗时{summary["indexing_ms"]/1000:.2f}s单列，不计入逐题耗时。关键词与图文共用原生解析、问题、读取模型及预算。</p>'
    document += '<table><tr><th>配置</th><th>实际选页</th><th>本题页/值/单位/问题条件核对</th><th>检索+核对+作答实耗时</th><th>作答调用</th></tr>' + ''.join(rows) + '</table>'
    document += '<p>耗时不包含索引及应用装载。相同模型请求命中缓存时是回放耗时，不当作独立网络性能对照。Jev只核对候选页文字是否足以作答，概率不是答案真值；模型其他条件完整性仍需人工审阅。</p>'
    document += '<p class="notice">本题建议关键词A作为查证起点，不修改应用全局检索配置。图文+Jev修正了该次选页，但只有一道已知开发题，不能推广为整体优劣结论。各配置是否通过以逐项核对为准，原图读稿、坐标和单位仍可人工回查。</p>'
    document += ''.join(sections) + '<a href="summary.json">完整计量与核对</a></html>'
    (output / "review.html").write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
