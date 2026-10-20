"""契的编译：清点来源 → 提议结论（模型，或读录制的提议）→ 核对引文、定级、对齐 → 写入有效状态文件 → 编译报告。

只在应用停着时运行（应用会整份保存状态文件）；演示在进程内直接调用 huayan.ingest.compile.admit。
  uv run python scripts/compile_qi.py --state runs/<运行>/qi_state.json --proposals seeds/rag/proposals.yaml
"""
import argparse
from collections import Counter
from pathlib import Path

import yaml

from huayan.domain import load_seeds
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.ingest.compile import Proposals, admit, propose, recheck
from huayan.ingest.folder import FolderSource
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.meter import FileMeter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/app.yaml")
    parser.add_argument("--state", required=True)
    parser.add_argument("--proposals")
    parser.add_argument("--out", default="data/ingest/report.md")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    kb = KnowledgeBase.from_seeds(load_seeds(config["seeds_dir"]), EventLog(), AuditLog(), state_path=args.state)
    kb.sources = [FolderSource(s["name"], s["kind"], s["root"], s.get("level"), kb._doc_levels)
                  for s in config["sources"]]
    fragments = [f for s in kb.sources for doc_id in s.list_docs() for f in s.fetch(doc_id)]
    if args.proposals:
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
    write_report(Path(args.out), kb, fragments, proposals, report, changed, args)
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
             f"- 提议：{len(proposals)} 条（{'录制：' + args.proposals if args.proposals else '模型 ingest:extract'}）",
             f"- 候选结论：{len(admitted)} 条；能力提议 {sum(a['capability_id'] is not None for a in admitted)} 条",
             f"- 丢弃（引文与原文不符）：{'；'.join(report['dropped']) or '无'}",
             f"- 与现有能力完全相同（已挂为其依据）：{'；'.join(report['duplicates']) or '无'}",
             f"- 冲突（同一目标不同取值）：{'；'.join(report['conflicts']) or '无'}",
             f"- 对不上的新概念或待认领：{'；'.join(report['unaligned']) or '无'}",
             f"- 依据已变化、待复核：{'、'.join(changed) or '无'}", "",
             "## 候选结论", "", "| 编号 | 层级 | 形式 | 能力提议 | 标题 |", "|---|---|---|---|---|"]
    lines += [f"| {a['ku_id']} | L{a['level']} | {a['form'] or '只是结论'} | {a['capability_id'] or '—'} | {a['title']} |"
              for a in admitted]
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
