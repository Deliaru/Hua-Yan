"""契的编译：清点来源 → 提议结论（模型，或读录制的提议）→ 核对引文、定级、对齐 → 写入有效状态文件 → 编译报告。

只在应用停着时运行（应用会整份保存状态文件）；演示在进程内直接调用 huayan.ingest.compile.admit。
  uv run python scripts/compile_qi.py --state runs/<运行>/qi_state.json --proposals seeds/rag/proposals.yaml
  仅预览 IR：--ir <operation-ir.json> --evidence <evidence.json> --out <report.md>（不传 --state）
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import yaml

from huayan.domain import load_seeds
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.ingest.compile import Proposals, admit, propose, recheck
from huayan.ingest.folder import FolderSource
from huayan.ingest.trial_ir import OperationIR, EvidenceReportSource
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.meter import FileMeter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/app.yaml")
    parser.add_argument("--state")
    parser.add_argument("--proposals")
    parser.add_argument("--ir", help="操作观察 IR；不传 --state 时仅在内存中预览")
    parser.add_argument("--evidence", help="IR 对应的 evidence.json")
    parser.add_argument("--out", default="data/ingest/report.md")
    args = parser.parse_args()
    if args.ir and (not args.evidence or args.proposals):
        parser.error("--ir 必须配合 --evidence，且不与 --proposals 同用")
    if not args.ir and not args.state:
        parser.error("正式编译须提供 --state；仅 IR 支持内存预览")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    kb = KnowledgeBase.from_seeds(load_seeds(config["seeds_dir"]), EventLog(), AuditLog(), state_path=args.state)
    kb.sources = [EvidenceReportSource(s["root"]) if Path(s["root"]).suffix == ".json" else
                  FolderSource(s["name"], s["kind"], s["root"], s.get("level"), kb._doc_levels)
                  for s in config["sources"]]
    if args.ir:
        ir = OperationIR.model_validate_json(Path(args.ir).read_text(encoding="utf-8"))
        source = EvidenceReportSource(args.evidence)
        if ir.source_id != source.name or ir.file_sha256 != source.file_sha256:
            raise ValueError("IR 与读取记录来源不一致")
        for citation in ir.evidence:
            f = source.fetch(ir.source_id, citation.span)
            if citation.fragment != f"{f.doc_id}#{f.span}@{f.fingerprint}":
                raise ValueError(f"IR 引用指纹已变化：{citation.span}")
        if not any(source.name in s.list_docs() for s in kb.sources):
            kb.sources.append(source)
    fragments = [f for s in kb.sources for doc_id in s.list_docs() for f in s.fetch(doc_id)]
    if args.ir:
        proposals = [ir.proposal]
    elif args.proposals:
        recorded = yaml.safe_load(Path(args.proposals).read_text(encoding="utf-8"))["items"]
        proposals = Proposals(items=recorded).items
    else:
        gateway = build_gateway("config/models.yaml", False, FileMeter(Path(args.out).parent, "compile_qi"))
        gateway.cache_dir = None                    # 编译不缓存资料片段
        proposals = propose(fragments, gateway, kb.seeds)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)   # 留下提议，可用 --proposals 回放
        (Path(args.out).parent / "proposals.yaml").write_text(yaml.safe_dump(
            {"items": [p.model_dump() for p in proposals]}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    changed = recheck(kb, kb.sources)
    report = admit(proposals, kb.sources, kb)
    if args.ir:
        if ir.assigned_rd is not None:
            report["assigned_rd"] = ir.assigned_rd.model_dump(mode="json")
        if ir.product_alignment is not None:
            report["product_alignment"] = {"product_id": ir.product_alignment.product_id,
                "name": ir.product_alignment.name, "identity_supported": True,
                "catalog_registered": ir.proposal.product in {p.id for p in kb.seeds.products} | set(kb._products),
                "published": ir.proposal.product in kb._products,
                "pending": ir.product_alignment.pending}
            for item in report["unaligned_details"]:
                item["reasons"] = [("产品身份已有依据，正式目录登记待完成" if ir.assigned_rd is not None else
                                    "产品身份已有依据，正式目录登记待归属") if reason == f"产品未对齐：{ir.product_raw}"
                                   else reason for reason in item["reasons"]]
        entries = report["admitted"] or report["pending_evidence"]
        report["ir_mapping"] = {"ir_id": ir.id, "ku_id": entries[0]["ku_id"] if entries else None,
            "status": "pending_evidence" if report["pending_evidence"] else "candidate" if entries else "pending_alignment",
            "preview": args.state is None}
    write_report(Path(args.out), kb, fragments, proposals, report, changed, args)
    Path(args.out).with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"候选 {len(report['admitted'])} 条，丢弃 {len(report['dropped'])}，重复 {len(report['duplicates'])}，"
          f"冲突 {len(report['conflicts'])}，未对齐 {len(report['unaligned'])}，依据变化 {len(changed)}；报告 {args.out}")


def write_report(path, kb, fragments, proposals, report, changed, args):
    by_source = Counter(f.source for f in fragments)
    admitted = report["admitted"]
    public = [a for a in admitted if a["level"] == 0]
    internal = [a for a in admitted if a["level"] > 0]
    lines = ["# 编译报告（替身 RAG）", "",
             f"- 来源：{', '.join(f'{s.name}（{s.kind}）' for s in kb.sources)}；清点模式，按资料清单逐份读取，不发查询",
             f"- 片段：{len(fragments)} 段（" + "、".join(f"{k} {v}" for k, v in by_source.items()) + "）",
             f"- 提议：{len(proposals)} 条（{'IR：' + args.ir if args.ir else '录制：' + args.proposals if args.proposals else '模型 ingest:extract'}）",
             f"- 写入方式：{'正式离线状态文件' if args.state else '内存预览，未写 qi_state'}",
             f"- 候选结论：{len(admitted)} 条；能力提议 {sum(a['capability_id'] is not None for a in admitted)} 条",
             f"- 丢弃（引文与原文不符）：{'；'.join(report['dropped']) or '无'}",
             f"- 与现有能力完全相同（补充依据候选，待确认挂接）：{'；'.join(report['duplicates']) or '无'}",
             f"- 冲突（同一目标不同取值）：{'；'.join(report['conflicts']) or '无'}",
             f"- 对不上的新概念或待认领（交产品经理审定种子时决定是否扩展词表）：{'；'.join(report['unaligned']) or '无'}",
             f"- 依据已变化、待复核：{'、'.join(changed) or '无'}", "",
             "## 候选结论", "", "| 编号 | 层级 | 形式 | 能力提议 | 标题 |", "|---|---|---|---|---|"]
    lines += [f"| {a['ku_id']} | L{a['level']} | {a['form'] or '只是结论'} | {a['capability_id'] or '—'} | {a['title']} |"
              for a in admitted]
    lines += ["", "## 待对齐与待挂接", ""]
    if "assigned_rd" in report:
        actor = report["assigned_rd"]
        lines += [f"- 候选研发归属：{actor['name']}（{actor['id']}）；专业确认和授予待本人签字。"]
    if "product_alignment" in report:
        alignment = report["product_alignment"]
        lines += [f"- 产品身份已有资料依据：{alignment['name']}（{alignment['product_id']}）；"
                  f"正式目录已登记：{alignment['catalog_registered']}"]
        lines += [f"- {note}" for note in alignment["pending"]]
    lines += [f"- {item['title']}：{'；'.join(item['reasons'])}" for item in report["unaligned_details"]]
    lines += [f"- {item['ku_id']} → {item['capability_id']}：待确认，尚未挂接" for item in report["pending_evidence"]]
    lines += ["", "## 待签（按设计第 9 节分类）", "",
              f"- ① 公开来源：{len(public)} 条，其中适用情境 {sum(a['form'] == 'applicable' for a in public)} 条由产品经理按产品页核对",
              "- ② 会话里的客户说法：本轮未实现",
              "- ③ 由公开适用情境推出的追问：无需签",
              f"- ④ 内部资料同层使用：{len(internal)} 条，研发签需求单时勾选确认",
              "- ⑤ 内部判断给更低的层用：编译不提议跨层授予；只在下层真正需要时由觉提出 qi_grant，研发逐条签", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
