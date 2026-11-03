"""V12.4 资料库试样报告整批编译（应用停止时离线跑）：每份试样报告的全部页经 V11.10 观察编译器提议（caller ingest:extract），
再在一份临时知识库里核对、对齐，只产生候选；不写任何应用实例的 qi_state。产物在 data/library/compiled/（含原文摘录，不入库）：
proposals/<doc_id>.json 每份的提议；report.json 核对结果；coverage.json 跨文档覆盖（产品 × 条件 × 温度 × 结果）；
aliases.json 槽位词表认不出的条件说法；hypotheses.json 同产品可比条件下结果不同的研究假设。

uv run --env-file .env python scripts/compile_library.py            # 提议（失败的报告打印出来，重跑即续跑），再出报告
uv run python scripts/compile_library.py --report                   # 只按已有提议重出报告
"""
import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from huayan.agent.hub import MODEL_ERRORS
from huayan.contracts import LLMRequest, Message, Tier
from huayan.contracts._base import BaseModel
from huayan.domain import find_slot_values, load_seeds
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.ingest.compile import Proposal, admit, propose
from huayan.ingest.reader.library import LibrarySource
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.meter import FileMeter

LIBRARY, OUT = Path("data/library"), Path("data/library/compiled")
SEEDS = OUT / "seeds"          # 试玩真实报告版的种子副本加上 TF-213Q（两个产品的试样报告都对得上产品）


def run_proposals(source, docs, models, workers):
    gateway = build_gateway(models, False, FileMeter(OUT, "compile-library"))
    gateway.cache_dir = OUT / "llm_cache"
    seeds = load_seeds(SEEDS)
    (OUT / "proposals").mkdir(parents=True, exist_ok=True)
    todo = [d for d in docs if not (OUT / "proposals" / f"{d}.json").exists()]
    print(f"试样报告 {len(docs)} 份，待编译 {len(todo)} 份", flush=True)
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(propose, source.fetch(d), gateway, seeds, 1, 1): d for d in todo}
        for done, future in enumerate(as_completed(futures), 1):
            d = futures[future]
            try:
                items = future.result()
            except MODEL_ERRORS as e:          # 网络或接口失败：这份留到重跑
                print(f"  {d} 没编出来：{type(e).__name__}: {str(e)[:120]}", flush=True)
                continue
            (OUT / "proposals" / f"{d}.json").write_text(
                json.dumps([p.model_dump() for p in items], ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {done}/{len(todo)} {d} {len(items)} 条", flush=True)


ALIAS_PROMPT = """下面是试样报告里槽位词表认不出的条件说法，以及各槽位已有的取值。逐条判断它是不是某个已有取值的另一种说法（错别字、简称、行业叫法、带了布种或规格的写法）：
是就写 slot 与 value（必须是给出的取值之一）；不是（工艺参数、用量、颜色、克重，或已有取值里没有的新类别）slot、value 写 null。reason 用一句话说明。
只输出 JSON：{"items": [{"text", "slot", "value", "reason"}]}"""


class AliasGuess(BaseModel):
    text: str
    slot: str | None = None
    value: str | None = None
    reason: str = ""


class AliasGuesses(BaseModel):
    items: list[AliasGuess]


def map_aliases(models, texts):
    """别名候选：模型提议每种说法对应哪个槽位取值，只是候选，研发确认后才进槽位说法（动态知识组织）。"""
    path = OUT / "alias_guesses.json"
    guesses = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    texts = sorted(set(texts) - set(guesses))      # 问过的说法不再问，重跑不改已有的提议
    gateway = build_gateway(models, False, FileMeter(OUT, "compile-library"))
    gateway.cache_dir = OUT / "llm_cache"
    seeds = load_seeds(SEEDS)
    values = {s.id: set(s.values) for s in seeds.slots}
    slots = [{"id": s.id, "label": s.label, "values": s.values} for s in seeds.slots]

    def ask(part):                   # 每批 40 种说法，一次全给会把输出截断
        output, _ = gateway.structured(LLMRequest(tier=Tier.FAST, caller="ingest:extract", temperature=0, timeout_s=300,
            max_tokens=8192, messages=[Message(role="system", content=ALIAS_PROMPT),
                      Message(role="user", content=json.dumps({"slots": slots, "texts": part}, ensure_ascii=False))]), AliasGuesses)
        return output.items

    with ThreadPoolExecutor(6) as pool:
        items = [g for part in pool.map(ask, [texts[i:i + 40] for i in range(0, len(texts), 40)]) for g in part]
    guesses |= {t: None for t in texts}           # 模型没给或对不上已有取值的，记为没有提议
    guesses |= {g.text: g.model_dump() for g in items if g.text in texts and g.slot in values and g.value in values[g.slot]}
    OUT.joinpath("alias_guesses.json").write_text(json.dumps(guesses, ensure_ascii=False, indent=1), encoding="utf-8")


def pointers(source, p):
    pages = {f.span: f for d in {ev.doc_id for ev in p.evidence} for f in source.fetch(d)}
    return [f"{ev.doc_id}#{ev.span}@{pages[ev.span].fingerprint}" for ev in p.evidence if ev.span in pages]


def write_report(source, docs):
    seeds = load_seeds(SEEDS)
    kb = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog(), state_path=None)
    kb.sources = [source]
    proposals = {d: [Proposal.model_validate(x) for x in json.loads((OUT / "proposals" / f"{d}.json").read_text(encoding="utf-8"))]
                 for d in docs if (OUT / "proposals" / f"{d}.json").exists()}
    report, rows = defaultdict(list), {}
    for d, items in proposals.items():             # 逐条核对，好把结果对回每条提议
        for i, p in enumerate(items):
            one = admit([p.model_copy(update={"author": source.owners.get(d)})], kb.sources, kb)
            for k, v in one.items():
                report[k] += v
            rows[(d, i)] = one
    labels = {s.id: s.label for s in seeds.slots}

    coverage, aliases = [], defaultdict(list)
    for d, items in proposals.items():
        for i, p in enumerate(items):
            if p.kind != "observation":
                continue
            matched, unmatched = {}, []
            for text in p.conditions:
                found = find_slot_values(text, seeds.slots)
                matched |= {labels[slot]: value for slot, (value, _) in found.items()}
                if not found:
                    unmatched.append(text.strip())
            for text in unmatched:
                aliases[text].append(d)
            one = rows[(d, i)]
            row = (one["admitted"] or one["pending_evidence"] or [None])[0]   # 同 payload 的新依据先作候选挂接
            coverage.append({"doc_id": d, "title": source.docs[d]["title"], "product": p.product, "phenomenon": p.phenomenon,
                             "conditions": matched, "unmatched": unmatched, "temperature_c": p.temperature_c,
                             "result": p.result, "result_quote": p.result_quote, "process": p.process,
                             "evidence": pointers(source, p),
                             "candidate": row["ku_id"] if row else None, "proposal": row and row["capability_id"],
                             "not_admitted": None if row else next((x["reasons"] for x in one["unaligned_details"]), ["引文查不到"])})

    # 研究假设：同产品、同现象、已认出的条件一样，结果却不同；温度不同的提「可能与温度有关」，温度也一样的提「同条件结果不一致」
    groups = defaultdict(list)
    for row in coverage:
        if row["candidate"] and row["result"] in ("pass", "fail", "mixed"):
            groups[(row["product"], row["phenomenon"], json.dumps(row["conditions"], ensure_ascii=False, sort_keys=True))].append(row)
    hypotheses = []
    for (product, phenomenon, conditions), rows in groups.items():
        if len({r["result"] for r in rows}) < 2:
            continue
        temps = {tuple(r["temperature_c"]) for r in rows if r["temperature_c"]}
        hypotheses.append({"product": product, "phenomenon": phenomenon, "conditions": json.loads(conditions),
                           "kind": "temperature" if len(temps) > 1 else "conflict",
                           "text": "结果可能与温度有关" if len(temps) > 1 else "同条件下结果不一致，需研发复核",
                           "rows": [{k: r[k] for k in ("doc_id", "temperature_c", "result", "result_quote", "candidate")} for r in rows]})

    OUT.joinpath("report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.joinpath("coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=1), encoding="utf-8")
    # 别名候选：模型提议的槽位取值（alias_guesses.json），对不上的留给研发指定或不收
    path = OUT / "alias_guesses.json"
    guesses = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    rows_ = [{"text": t, "docs": sorted(set(ds)), "count": len(ds), "suggest": guesses.get(t)} for t, ds in aliases.items()]
    OUT.joinpath("aliases.json").write_text(json.dumps(sorted(rows_, key=lambda x: (x["suggest"] is None, -x["count"])),
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.joinpath("hypotheses.json").write_text(json.dumps(hypotheses, ensure_ascii=False, indent=1), encoding="utf-8")
    results = defaultdict(int)
    for row in coverage:
        results[row["result"]] += 1
    print(f"编了 {len(proposals)}/{len(docs)} 份；观察 {len(coverage)} 条（{dict(results)}），进候选 {len(report['admitted'])} 条、"
          f"其中适用提议 {sum(bool(r['capability_id']) for r in report['admitted'])} 条；交人 {len(report['unaligned'])} 条，"
          f"引文查不到 {len(report['dropped'])} 条；认不出的条件说法 {len(aliases)} 种（像得上槽位取值的 {sum(r["suggest"] is not None for r in rows_)} 种）；研究假设 {len(hypotheses)} 条")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="只按已有提议重出报告，不调模型")
    ap.add_argument("--models", default="data/pilot/models.yaml")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    source = LibrarySource("library", "internal", LIBRARY)
    docs = sorted(d for d in source.list_docs() if d.startswith("trial-"))
    if not args.report:
        run_proposals(source, docs, args.models, args.workers)
    write_report(source, docs)
    if not args.report:              # 别名候选要先有认不出的说法清单，提议后再出一次报告
        map_aliases(args.models, [a["text"] for a in json.loads((OUT / "aliases.json").read_text(encoding="utf-8"))])
        write_report(source, docs)
