"""已核验题的读取证据核对；答案只在eval侧使用，不送入检索或读取工具。

本入口复用关键词检索，核对来源页与已返回表格的指定单元格；不生成答案、不评估模型读图。
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4

from huayan.ingest.reader.evidence import EvidenceBlock
from huayan.ingest.reader.retrieval import keyword_search


def page_chunks(paths):
    chunks = []
    for path in paths:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        blocks = [EvidenceBlock.model_validate(b) for b in report["blocks"]]
        for page in sorted({loc.page for b in blocks for loc in b.locations}):
            selected = [b for b in blocks if page in {loc.page for loc in b.locations}]
            chunks.append({"source_id": report["source_id"], "page": page, "file_sha256": report["file_sha256"],
                           "text": "\n\n".join(b.text for b in selected),
                           "fragments": [b.fragment().model_dump(mode="json") for b in selected],
                           "blocks": [b.model_dump(mode="json") for b in selected]})
    return chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="data/knowledge_v10/evaluations/questions.jsonl")
    parser.add_argument("--gold", default="data/knowledge_v10/evaluations/selected_chart.json")
    parser.add_argument("--evidence", nargs="+", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    questions = [json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line]
    # 当前只有一题完成开发者原页核验；其余题保留完整状态，不以有文字答案代替已核验。
    eligible = [q for q in questions if q["source_state"] == "verified"
                and q["answer_verification"] == "developer_compared_native_office_visual_and_xml"]
    chunks = page_chunks(args.evidence)
    output = Path(args.out) if args.out else Path("data/knowledge_v10/validation") / f"reading-evidence-{uuid4().hex[:8]}"
    output.mkdir(parents=True, exist_ok=True)
    predictions = []
    for question in eligible:
        start = perf_counter()
        # 只有原题送入既有检索；没有来源答案、正确页或金标坐标参数。
        hits = keyword_search(question["question"], chunks, top_k=1)
        predictions.append({"question_id": question["question_id"], "query": question["question"],
                            "retrieval": "keyword", "top_k": 1, "hits": hits,
                            "elapsed_ms": (perf_counter() - start) * 1000})
    (output / "predictions.json").write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    results = []
    for prediction in predictions:
        if prediction["question_id"] != gold["question_id"]:
            raise ValueError("已核验题尚缺对应核对记录，不计入本次分母")
        hit = prediction["hits"][0] if prediction["hits"] else None
        found = hit is not None and (hit["source_id"], hit["page"], hit["file_sha256"]) == (
            gold["source_id"], gold["slide"], gold["source_sha256"])
        status = "found_expected_page" if found else "not_found" if hit is None else "wrong_source_or_page"
        checks = []
        context = None
        if found:
            span = f"slide-{gold['slide']}/shape-{gold['source_table_cells']['shape_id']}"
            table = next((b for b in hit["blocks"] if b["span"] == span), None)
            if table:
                fragment = next(f for f in hit["fragments"] if f["span"] == span)
                headers = [c["text"] for c in table["cells"] if c["row"] <= 2]
                context = {"evidence": f"{fragment['doc_id']}#{span}@{fragment['fingerprint']}",
                           "column_headers_raw": headers,
                           "row_headers_raw": [c["text"] for c in table["cells"] if c["row"] > 2 and c["column"] <= 2],
                           "unit_labels_raw": re.findall(r"[（(]([^（）()]+)[）)]", "\n".join(headers)),
                           "page_context_raw": [b["text"] for b in hit["blocks"] if b["kind"] != "table"]}
            for expected in gold["checked_values"]:
                row, column = gold["source_table_cells"]["row_column_one_based"][expected["metric"]]
                cell = next((c for c in table["cells"] if (c["row"], c["column"]) == (row, column)), None) if table else None
                value = cell["text"] if cell else None
                checks.append({"metric": expected["metric"], "row": row, "column": column,
                               "actual_raw": value, "expected_raw": str(expected["value"]),
                               "matches": value == str(expected["value"])})
        results.append({"question_id": prediction["question_id"], "retrieval_status": status,
                        "native_cell_audit": checks, "native_context": context, "answer_status": "not_run",
                        "note": "单元格坐标仅由eval用于事后核对；未验证系统自主选行列、单位解释或生成答案。"})
    catalog = [{"question_id": q["question_id"], "source_state": q["source_state"],
                "answer_state": q["answer_state"], "answer_verification": q["answer_verification"],
                "run_state": "evaluated_evidence" if any(r["question_id"] == q["question_id"] for r in results)
                else "not_evaluated"} for q in questions]
    summary = {"scope": "已核验开发题，受控资料集的证据查准与原生单元格保真；非端到端问答或盲测",
               "total_questions": len(questions), "evaluated_questions": len(results),
               "skipped_questions": len(questions) - len(results),
               "source_page_hits": sum(r["retrieval_status"] == "found_expected_page" for r in results),
               "source_page_denominator": len(results),
               "native_cells_checked": sum(len(r["native_cell_audit"]) for r in results),
               "native_cells_matched": sum(c["matches"] for r in results for c in r["native_cell_audit"]),
               "model_answers_evaluated": 0, "model_calls": 0, "jev": "off", "retrieval": "keyword",
               "corpus_sources": sorted({c["source_id"] for c in chunks}), "corpus_pages": len(chunks),
               "input_sha256": {str(path): sha256(Path(path).read_bytes()).hexdigest()
                                for path in [args.questions, args.gold, *args.evidence]},
               "source_states": dict(Counter(q["source_state"] for q in questions)),
               "results": results, "catalog": catalog}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 已核验开发题：证据读取核对", "", summary["scope"], "",
             f"题库{len(questions)}题；本次证据核对{len(results)}题，未运行{summary['skipped_questions']}题。",
             f"来源页命中{summary['source_page_hits']}/{len(results)}；指定原生单元格一致{summary['native_cells_matched']}/{summary['native_cells_checked']}。",
             "模型回答可评分分母为0；不据此报告问答正确率。关键词、Jev关闭，无模型调用。", "",
             "| 题号 | 来源状态 | 答案核验状态 | 本次状态 |", "|---|---|---|---|"]
    lines += [f"| {q['question_id']} | {q['source_state']} | {q['answer_verification']} | {q['run_state']} |" for q in catalog]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(output / "report.md")


if __name__ == "__main__":
    main()
