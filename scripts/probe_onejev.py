"""OneJev 区分度探针（觉「监控全过程信息流」方案的第 5 步）：同一批定时发现样本上，比较
  rule       原型规则分（前置条件不通过记 0）
  attrs      OneJev，只看对象属性 + 现有 worth_prompt（= 今天的「原型 + OneJev」）
  evidence   OneJev，属性 + 窗口内原始事件证据（客户原话、提问文本、试样记录）+ 只陈述决定的中性题面
  evidence_ctx  同 evidence，题面换成现有 worth_prompt（带业务背景）
样本按 JUE WP-P：每条注入在 [earliest, latest] 内取 3 个扫描时刻为正；每条困难负样本在其窗口内取 3 个时刻；
平静负样本为同类型、不在注入清单中的对象（注入外已有 ≥ 2 位客户升级的主题单列为 natural，不进 AUC）。
事件来自生成周在真实链路上跑出的事件（eval.week.chain_events）。不改契约，证据只在本脚本里拼进 OneJev 的状态。

uv run python scripts/probe_onejev.py [--weeks 34-39 --w1]   （需要 OneJev 服务，见 config/system1.yaml）
"""
import argparse
import json
import random
import tempfile
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from huayan.contracts import SHANGHAI, Injection, NeedCard, S1Noul, WeekItem
from huayan.domain import load_seeds
from huayan.eval.week import chain_events
from huayan.events import EventLog
from huayan.jev.system1 import build_system1
from huayan.jue.expr import evaluate
from huayan.jue.proto import load_templates, render
from huayan.jue.state import WINDOWS, collect_scheduled, theme_id
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.meter import FileMeter
from huayan.sim import make_week
from huayan.sim.week_events import TICK_HOURS

OUT = Path("docs/reports/onejev_probe")
PLAIN = {   # 中性题面：只陈述要做的决定，不给判断规则
    "opportunity": "需求主题 {object}。证据是近 7 天该主题的升级（业务员在会话中找不到适用的现有产品、转给了产品经理）与推荐记录，以及客户原话。产品经理此刻是否需要决定：要不要为这个主题立项开发新产品？",
    "knowledge_conflict": "知识对象 {object}：某产品在某个条件上的说明书声明。证据是近 7 天该产品的试样记录与推荐记录。研发此刻是否需要决定：要不要更新这条说明书？",
    "leak_risk": "提问者 {object}（只有 L1 权限的业务员）。证据是他近 48 小时向知识库提的全部问题。主管此刻是否需要决定：要不要冻结他的高层级检索权限？",
}


def ticks(start: datetime, days: int) -> list[datetime]:
    return [datetime.combine(start.date() + timedelta(days=d), time(h), tzinfo=start.tzinfo)
            for d in range(days) for h in TICK_HOURS]


def evidence(obj, at: datetime, events: EventLog, seeds) -> list[str]:
    """对象在窗口内的原始事件，按时间排列，条数有上限。"""
    if obj.object_type == "theme":
        esc = [e for e in events.query(["escalate", "recommend"], since=at - timedelta(days=WINDOWS["theme_days"]), until=at)
               if theme_id(e.payload["phenomenon"], e.payload["known"], seeds) == obj.object_id][-8:]
        turns = defaultdict(list)
        for e in events.query(["turn"], until=at):
            if e.payload["speaker"] == "customer":
                turns[e.session_id].append(e.payload["text"])
        return [f"{e.ts:%m-%d %H:%M} {'升级' if e.kind == 'escalate' else '推荐 ' + e.payload['product_id']}"
                f"｜客户 {e.payload['customer_id']}｜已知 {e.payload['known']}｜客户原话：" + " / ".join(turns[e.session_id][:3])
                for e in esc]
    if obj.object_type == "knowledge":
        pid = obj.attrs["product_id"]
        trials = [e for e in events.query(["trial"], since=at - timedelta(days=WINDOWS["knowledge_days"]), until=at)
                  if e.payload["product_id"] == pid][-10:]
        return [f"{e.ts:%m-%d %H:%M} 试样 {pid}｜条件 {e.payload['conditions']}｜结果 {e.payload['result']}｜原因 {e.payload['cause']}"
                for e in trials]
    actor = obj.object_id.split(":", 1)[1]
    qs = [e for e in events.query(["retrieve"], since=at - timedelta(hours=WINDOWS["actor_hours"]), until=at)
          if e.actor == actor][-12:]
    return [f"{e.ts:%m-%d %H:%M} 提问：{e.payload['query']}" for e in qs]


def samples(events: EventLog, injections: list[Injection], start: datetime, days: int, seeds, products, rng, week: str):
    """(组, 类别, family, at, obj)。类别：pos / hard / calm / natural。"""
    by_tick = {at: collect_scheduled(events, at, seeds, products)[0] for at in ticks(start, days)}
    family_of = {"theme": "opportunity", "knowledge": "knowledge_conflict", "actor": "leak_risk"}
    out = []
    targets = {i.object_id for i in injections}
    for inj in injections:
        inside = [at for at, st in by_tick.items() if inj.earliest <= at <= inj.latest and inj.object_id in st.objects]
        for at in [inside[k] for k in sorted({round(x) for x in np.linspace(0, len(inside) - 1, 3)})] if inside else []:
            out.append((f"{week}/{inj.id}", "hard" if inj.hard_negative else "pos", inj.family, at, by_tick[at].objects[inj.object_id]))
    for at, st in by_tick.items():
        for obj in st.objects.values():
            if obj.object_id in targets:
                continue
            natural = obj.object_type == "theme" and obj.attrs["n_customers"] >= 2
            out.append((f"{week}/{obj.object_id}", "natural" if natural else "calm", family_of[obj.object_type], at, obj))
    calm = [s for s in out if s[1] == "calm"]
    keep = {id(s) for s in rng.sample(calm, min(len(calm), 15))}      # 平静负样本每周抽 15 个
    return [s for s in out if s[1] != "calm" or id(s) in keep]


def auc_ci(y, p, groups, rng, n=500):
    y, p, groups = np.asarray(y), np.asarray(p), np.asarray(groups)
    if len(set(y)) < 2:
        return None
    uniq = np.unique(groups)
    idx = {g: np.where(groups == g)[0] for g in uniq}
    boots = []
    for _ in range(n):
        take = np.concatenate([idx[g] for g in rng.choice(uniq, len(uniq))])
        if len(set(y[take])) == 2:
            boots.append(roc_auc_score(y[take], p[take]))
    return {"auc": float(roc_auc_score(y, p)), "lo": float(np.percentile(boots, 2.5)), "hi": float(np.percentile(boots, 97.5))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", default="34-39", help="生成周序号（种子 1000 + w，与 make_jue_k_data 的 test 周一致）")
    ap.add_argument("--no-w1", action="store_true")
    args = ap.parse_args()

    seeds = load_seeds("seeds")
    products = KnowledgeBase.from_seeds(seeds, EventLog(), AuditLog()).products()
    templates = {t.family: t for t in load_templates("config/templates").values() if t.object_type != "slot"}
    OUT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    s1 = build_system1("onejev", "config/system1.yaml", None, FileMeter(work, "onejev_probe"))
    rng = random.Random(0)
    start = datetime(2026, 10, 12, tzinfo=SHANGHAI)

    weeks = []
    lo, hi = map(int, args.weeks.split("-"))
    for w in range(lo, hi + 1):
        items, cards, injections = make_week(seeds, start, 5, random.Random(1000 + w))
        weeks.append((f"w{w}", chain_events(items, cards, work, f"w{w}"), injections))
    if not args.no_w1:
        d = Path("data/week/w1")
        items = [WeekItem.model_validate_json(l) for l in (d / "script.jsonl").read_text(encoding="utf-8").splitlines()]
        cards = [NeedCard.model_validate_json(l) for l in (d / "cards.jsonl").read_text(encoding="utf-8").splitlines()]
        injections = [Injection.model_validate_json(l) for l in (d / "injections.jsonl").read_text(encoding="utf-8").splitlines()]
        weeks.append(("w1", chain_events(items, cards, work, "w1"), injections))

    rows = []
    for week, events, injections in weeks:
        for group, cat, family, at, obj in samples(events, injections, start, 5, seeds, products, rng, week):
            t = templates[family]
            passed = evaluate(t.precondition, obj.attrs, boolean=True)
            rule = float(evaluate(t.rule_score, obj.attrs)) if passed else 0.0
            base = {"type": obj.object_type, "attrs": dict(obj.attrs)}
            ev = evidence(obj, at, events, seeds)
            a = s1.ask({"at": at.isoformat(), "objects": {obj.object_id: base}}, [],
                       {"q": S1Noul(text=render(t.worth_prompt, obj))}, caller="jue:proto")
            b = s1.ask({"at": at.isoformat(), "objects": {obj.object_id: {**base, "evidence": ev}}}, [],
                       {"plain": S1Noul(text=PLAIN[family].format(object=obj.object_id)),
                        "ctx": S1Noul(text=render(t.worth_prompt, obj))}, caller="jue:proto")
            rows.append({"week": week, "group": group, "cat": cat, "family": family, "at": at.isoformat(),
                         "object_id": obj.object_id, "precondition": passed, "n_evidence": len(ev),
                         "rule": rule, "attrs": a.answers["q"].probabilities["yes"],
                         "evidence": b.answers["plain"].probabilities["yes"],
                         "evidence_ctx": b.answers["ctx"].probabilities["yes"]})
        print(f"{week}: 累计 {len(rows)} 个样本")
    (OUT / "samples.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    brng = np.random.default_rng(0)
    arms = ["rule", "attrs", "evidence", "evidence_ctx"]
    result = {"n": {c: sum(r["cat"] == c for r in rows) for c in ("pos", "hard", "calm", "natural")}, "auc": {}}
    for family in [None, "opportunity", "knowledge_conflict", "leak_risk"]:
        sub = [r for r in rows if family is None or r["family"] == family]
        for scope, cats in (("all", ("pos", "hard", "calm")), ("hard", ("pos", "hard"))):
            s = [r for r in sub if r["cat"] in cats]
            key = f"{family or 'overall'}/{scope}"
            result["auc"][key] = {arm: auc_ci([r["cat"] == "pos" for r in s], [r[arm] for r in s], [r["group"] for r in s], brng)
                                  for arm in arms}
            result["auc"][key]["n"] = {"pos": sum(r["cat"] == "pos" for r in s), "neg": sum(r["cat"] != "pos" for r in s)}
    result["mean_p"] = {c: {arm: float(np.mean([r[arm] for r in rows if r["cat"] == c] or [np.nan])) for arm in arms}
                        for c in ("pos", "hard", "calm", "natural")}
    (OUT / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["n"], ensure_ascii=False))
    for key, v in result["auc"].items():
        cells = "  ".join(f"{arm} {v[arm]['auc']:.3f}[{v[arm]['lo']:.2f},{v[arm]['hi']:.2f}]" if v[arm] else f"{arm} —" for arm in arms)
        print(f"{key:28s} n={v['n']}  {cells}")
    for c, v in result["mean_p"].items():
        print(f"平均 p · {c:8s} " + "  ".join(f"{arm} {x:.3f}" for arm, x in v.items()))


if __name__ == "__main__":
    main()
