"""汇总明确提供的已处理试样记录；仅供开发者/研发本地使用，不接入Agent或客户界面。"""
import argparse
import json
from pathlib import Path

from huayan.ingest.reader.summary import summarize_trials, write_trial_summary
from huayan.ingest.reader.trials import TrialRecord


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", nargs="+", type=Path, help="已生成的trial-record.json，可提供多份")
    parser.add_argument("--manifest", default="data/knowledge_v10/manifest/sources.json")
    parser.add_argument("--product", default="", help="清单产品编号，精确匹配，不推断型号别名")
    parser.add_argument("--condition", default="", help="条件/操作原文包含的文字")
    parser.add_argument("--result", default="", help="报告结果或标注时间原文包含的文字")
    parser.add_argument("--out", default="data/knowledge_v10/trial-summary")
    args = parser.parse_args()
    sources = {s["source_id"]: s for s in json.loads(Path(args.manifest).read_text(encoding="utf-8"))["sources"]}
    entries = [(p, TrialRecord.model_validate_json(p.read_text(encoding="utf-8"))) for p in args.records]
    summary = summarize_trials(entries, sources, product=args.product, condition=args.condition, result=args.result)
    write_trial_summary(summary, args.out)
    print(json.dumps({"matched_reports": summary["matched_reports"], "unique_input_reports": summary["unique_input_reports"],
                      "paired_time_reports": summary["paired_time_reports"], "review": str(Path(args.out) / "review.html")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
