"""把 V10.2 的原生证据整理成一份 A/B TrialRecord；无模型调用，不写业务状态。"""
import argparse
import json
from pathlib import Path

from huayan.ingest.reader.evidence import EvidenceBlock, Reading
from huayan.ingest.reader.trial_review import write_trial_review
from huayan.ingest.reader.trials import build_trial_record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="read_report.py 生成的 evidence.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    evidence = Path(args.evidence)
    report = json.loads(evidence.read_text(encoding="utf-8"))
    blocks = [EvidenceBlock.model_validate(x) for x in report["blocks"]]
    readings = [Reading.model_validate(x) for x in report["readings"]]
    record = build_trial_record(blocks, readings, report["pending"])
    output = Path(args.out) if args.out else Path("data/knowledge_v10/trials") / record.source_id
    write_trial_review(record, blocks, report, evidence.parent, output)
    print(f'{record.source_id}：A/B 配方 {len(record.groups[0].formula)}/{len(record.groups[1].formula)} 项，'
          f'变化 {len(record.changes)} 项；草稿：{output / "review.html"}')


if __name__ == "__main__":
    main()
