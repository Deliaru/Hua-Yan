"""从一份 TrialRecord 准备操作经验 IR 与原文审阅包；不调用模型、不写 qi_state。"""
import argparse
import json
import os
from pathlib import Path

from huayan.contracts import Actor, Fragment
from huayan.domain import load_seeds
from huayan.ingest.reader.trials import TrialRecord
from huayan.ingest.trial_ir import prepare_operation, write_operation_review, read_product_alignment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--group", choices=["A", "B"], default="B")
    parser.add_argument("--seeds", default="seeds")
    parser.add_argument("--out", required=True)
    parser.add_argument("--product-alignment", help="已有来源引文的产品对齐材料")
    parser.add_argument("--reviewer", help="用户指定的研发 Actor JSON；仅分配候选归属，不执行确认")
    args = parser.parse_args()
    record = TrialRecord.model_validate_json(Path(args.trial).read_text(encoding="utf-8"))
    evidence_path = Path(args.evidence)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if record.source_id != evidence["source_id"] or record.file_sha256 != evidence["file_sha256"]:
        raise ValueError("TrialRecord 与读取记录来源不一致")
    group = next(g for g in record.groups if g.group == args.group)
    if not group.operations or args.product not in {x.name for x in group.formula}:
        raise ValueError("所选组须有现场操作记录，产品须见于该组配方")
    record.pending = [n for n in record.pending if not n.startswith("图片模型读取未完成：")]
    record.pending += [n for n in evidence["pending"] if n.startswith("图片模型读取未完成：")]
    ir = prepare_operation(record, load_seeds(args.seeds), args.group, args.product)
    if args.product_alignment:
        alignment_path = Path(args.product_alignment).resolve()
        alignment = read_product_alignment(alignment_path, args.product)
        alignment.source_records = [str((alignment_path.parent / p).resolve()) for p in alignment.source_records]
        ir.product_alignment = alignment
        ir.pending = [note for note in ir.pending if note != f"产品原词 {args.product} 尚未对齐现有产品词表。"]
        ir.pending += alignment.pending
    if args.reviewer:
        reviewer = Actor.model_validate_json(Path(args.reviewer).read_text(encoding="utf-8"))
        if reviewer.role != "rd":
            raise ValueError("候选专业确认归属须为研发角色")
        ir.assigned_rd, ir.proposal.author = reviewer, reviewer.id
        ir.pending = [note for note in ir.pending if note != "专业确认人与用途授予待安排；单次观察的复用范围待研发判断。"]
        ir.pending.append(f"研发归属已指定为 {reviewer.name}；单次观察的复用范围、专业确认与用途授予待本人处理。")
    fragments = {f.span: f for f in [Fragment.model_validate(item) for item in evidence["fragments"]]}
    for citation in ir.evidence:
        fragment = fragments[citation.span]
        if citation.fragment != f"{fragment.doc_id}#{fragment.span}@{fragment.fingerprint}" or citation.quote not in fragment.text:
            raise ValueError(f"引文或指纹不匹配：{citation.span}")
    relative_review = Path(os.path.relpath(evidence_path.parent / "review.html", args.out)).as_posix()
    write_operation_review(ir, args.out, relative_review)
    print(f"IR {ir.id}；条件 {len(ir.conditions)} 项；待处理 {len(ir.pending)} 项；审阅包 {args.out}/review.html")


if __name__ == "__main__":
    main()
