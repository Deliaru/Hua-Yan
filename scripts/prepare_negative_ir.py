"""从已选负例的 TrialRecord 准备报告层品质观察 IR；不自动判失败、不写正式状态。"""
import argparse
import json
import os
from pathlib import Path

from huayan.domain import load_seeds
from huayan.ingest.reader.trials import TrialRecord
from huayan.ingest.trial_ir import EvidenceReportSource, prepare_negative, write_operation_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--product", required=True, help="保留原报告型号，不能去掉后缀或擅自映射别名")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    record = TrialRecord.model_validate_json(Path(args.trial).read_text(encoding="utf-8"))
    source = EvidenceReportSource(args.evidence)
    if record.source_id != source.name or record.file_sha256 != source.file_sha256:
        raise ValueError("TrialRecord 与读取记录来源不一致")
    if not record.quality or not any(args.product in x.text for x in record.metadata if "试样产品" in x.text):
        parser.error("所选记录须有已读品质结果，产品原词须见于试样产品原文")
    ir = prepare_negative(record, load_seeds(args.seeds), args.product)
    for citation in ir.evidence:
        f = source.fetch(ir.source_id, citation.span)
        if citation.fragment != f"{f.doc_id}#{f.span}@{f.fingerprint}" or citation.quote not in f.text:
            raise ValueError(f"引文或指纹不匹配：{citation.span}")
    evidence_review = Path(os.path.relpath(Path(args.evidence).resolve().parent / "review.html", Path(args.out).resolve())).as_posix()
    write_operation_review(ir, args.out, evidence_review)
    print(json.dumps({"ir_id": ir.id, "conditions": len(ir.conditions), "evidence": len(ir.evidence),
                      "proposal_form": ir.proposal.form, "review": str(Path(args.out) / "review.html")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
