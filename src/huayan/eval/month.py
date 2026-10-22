"""REPLAN-v8 Q9.4：业务月的指标与功能覆盖表（只读运行目录；world.jsonl 是世界的判定，只有 eval/ 读）。
打扰、拦下与漏掉的失败、判断过时的提前量、业务指标、换算；覆盖表列出每项功能第一次出现在第几天、哪个对象。"""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

from huayan.sim.month import START, business_days

TRIAL_COST = 3000          # 假设：一次试样的材料与工时（元）
TRIAL_DAYS = 3             # 假设：一次失败试样耽误的天数


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _day(ts: str, index: dict) -> int:
    d = datetime.fromisoformat(ts).date()
    return 0 if d < START else index.get(d, max(index.values()))


def load(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    questions = {}
    for q in _lines(run_dir / "questions.jsonl"):        # 快照日志：同一问题取最后一行
        questions[q["id"]] = q
    return {"events": _lines(run_dir / "events.jsonl"), "questions": questions,
            "world": _lines(run_dir / "world.jsonl"), "ledger": _lines(run_dir / "ledger.jsonl"),
            "summary": json.loads((run_dir / "month_summary.json").read_text(encoding="utf-8"))
            if (run_dir / "month_summary.json").exists() else {}}


def metrics(run_dir: Path) -> dict:
    data = load(run_dir)
    events, questions = data["events"], data["questions"]
    index = {d: i for i, d in enumerate(business_days(60), 1)}
    day = lambda ts: _day(ts, index)                                  # noqa: E731

    # 研发被打扰：两个新家族提给研发的次数，按天
    interrupts = defaultdict(Counter)
    for q in questions.values():
        if q["family"] in ("trial_risk", "stale_capability"):
            interrupts[q["family"]][day(q["created_at"])] += 1

    # 试样风险：每次技术确认时世界判一次；之后到下次确认前有没有提出、研发签了没有
    raised = defaultdict(list)
    for q in questions.values():
        if q["family"] == "trial_risk":
            raised[q["object_id"].split(":", 1)[1]].append(q)
    verdicts = defaultdict(list)
    for v in data["world"]:
        verdicts[v["requirement_id"]].append(v)
    risk = Counter()
    for rid, vs in verdicts.items():
        vs.sort(key=lambda v: v["at"])
        for i, v in enumerate(vs):
            end = vs[i + 1]["at"] if i + 1 < len(vs) else "9999"
            qs = [q for q in raised[rid] if v["at"] <= q["created_at"] < end]
            returned = any(q["resolution"] and q["resolution"]["note"].startswith("试样前回问") for q in qs)
            bad = v["result"] == "fail" and v["cause"] == "requirement"
            risk["confirmations"] += 1
            risk["would_fail_requirement"] += bad
            risk["raised"] += bool(qs)
            risk["intercepted"] += bad and returned
            risk["missed"] += bad and not returned
            risk["false_alarm"] += bool(qs) and not bad
            risk["returned_not_bad"] += returned and not bad
    trials = [e for e in events if e["kind"] == "trial" and day(e["ts"]) >= 1]     # 第 0 周导入的历史试样不算
    risk["req_trial_fail"] = sum(t["payload"]["result"] == "fail" and t["payload"]["cause"] == "requirement"
                                 and bool(t["payload"].get("requirement_id")) for t in trials)

    # 判断过时：运行中人签出的适用能力，授予后到被提出之间产品原因失败了几次
    grants = {e["payload"]["id"]: e for e in events if e["kind"] == "capability_granted"
              and e["payload"]["form"] == "applicable" and not e["actor"].startswith(("seed", "system"))}
    stale_q = {q["object_id"].removeprefix("knowledge:stale:"): q for q in questions.values()
               if q["family"] == "stale_capability"}
    stale = []
    for cap_id, g in grants.items():
        pid = g["payload"]["payload"]["product_id"]
        q = stale_q.get(cap_id)
        until = q["created_at"] if q else "9999"
        fails = [t for t in trials if t["payload"]["product_id"] == pid and t["payload"]["cause"] == "product"
                 and g["ts"] <= t["ts"] < until]
        if q or fails:
            stale.append({"capability": cap_id, "product": pid, "granted_day": day(g["ts"]),
                          "raised_day": day(q["created_at"]) if q else None, "fails_before_raise": len(fails),
                          "resolution": (q["resolution"] or {}).get("note") if q else None})

    # 业务指标
    sessions = {e["session_id"] for e in events if e["kind"] == "turn" and e["actor"].startswith("customer:")}
    recommended = {e["session_id"] for e in events if e["kind"] == "recommend" and e["payload"].get("product_id")}
    released = {e["payload"]["product_id"]: e["ts"] for e in events if e["kind"] == "product_released"}
    hits = [e for e in events if e["kind"] == "recommend" and e["payload"].get("product_id") in released
            and e["ts"] >= released[e["payload"]["product_id"]]]
    created = {e["payload"]["requirement_id"]: e["ts"] for e in events if e["kind"] == "requirement_created"}
    passed = {}
    for t in trials:
        rid = t["payload"].get("requirement_id")
        if rid and t["payload"]["result"] == "pass":
            passed.setdefault(rid, t["ts"])
    cycle = [(datetime.fromisoformat(passed[r]) - datetime.fromisoformat(created[r])).total_seconds() / 86400
             for r in passed if r in created]
    by_week = lambda kind: Counter((day(e["ts"]) - 1) // 5 + 1 for e in events if e["kind"] == kind)  # noqa: E731
    business = {
        "sessions": len(sessions), "l1_resolved": len(recommended & sessions),
        "l1_rate": round(len(recommended & sessions) / max(len(sessions), 1), 3),
        "escalations": sum(e["kind"] == "escalate" for e in events),
        "requirements": len(created), "trials": len(trials),
        "trial_fail": Counter(t["payload"]["cause"] for t in trials if t["payload"]["result"] == "fail"),
        "cycle_days_mean": round(sum(cycle) / len(cycle), 2) if cycle else None,
        "releases": len(released), "new_product_hits": len(hits),
        "points": _points(data["ledger"]),
        "escalations_by_week": by_week("escalate"), "trials_by_week": by_week("trial"),
    }
    saved = risk["intercepted"]
    return {"interrupts": {f: dict(sorted(c.items())) for f, c in interrupts.items()},
            "interrupts_total": {f: sum(c.values()) for f, c in interrupts.items()},
            "trial_risk": dict(risk), "stale": stale, "business": business,
            "savings": {"trials_saved": saved, "cost_saved": saved * TRIAL_COST, "days_saved": saved * TRIAL_DAYS,
                        "assumption": f"一次试样 {TRIAL_COST} 元、失败耽误 {TRIAL_DAYS} 天（假设）"},
            "coverage": coverage(data, day)}


def _points(ledger: list[dict]) -> dict:
    out = Counter()
    for r in ledger:
        if datetime.fromisoformat(r["ts"]).date() >= START:
            out[r["owner"]] += r["points"]
    return dict(out)


def coverage(data: dict, day) -> dict:
    """功能覆盖表：功能 → (第几天, 对象)。没出现的为 None。"""
    events, questions = data["events"], data["questions"]
    released = {e["payload"]["product_id"]: e["ts"] for e in events if e["kind"] == "product_released"}
    obj = lambda e: e["session_id"] or next((str(v) for k, v in e["payload"].items()  # noqa: E731
                                             if k.endswith("_id") or k == "id"), "")
    ev = {
        "追问": lambda e: e["kind"] == "ask_hint",
        "推荐": lambda e: e["kind"] == "recommend" and e["actor"].startswith("sales:"),
        "客户自助": lambda e: e["kind"] == "recommend" and e["actor"].startswith("customer:"),
        "升级": lambda e: e["kind"] == "escalate",
        "产品经理 Agent 起草 L2": lambda e: e["kind"] == "requirement_edited" and e["actor"] == "pm:agent",
        "接单": lambda e: e["kind"] == "requirement_accepted",
        "L3 转译": lambda e: e["kind"] == "requirement_translated",
        "试样通过": lambda e: e["kind"] == "trial" and e["payload"]["result"] == "pass",
        "试样失败": lambda e: e["kind"] == "trial" and e["payload"]["result"] == "fail",
        "沉淀": lambda e: e["kind"] == "knowledge_contributed",
        "封存与放出": lambda e: e["kind"] == "points_set",
        "发布": lambda e: e["kind"] == "product_released",
        "新品命中": lambda e: e["kind"] == "recommend" and e["payload"].get("product_id") in released
                    and e["ts"] >= released[e["payload"]["product_id"]],
        "客户评价": lambda e: e["kind"] == "market_eval",
        "冻结": lambda e: e["kind"] == "access_frozen",
        "解冻": lambda e: e["kind"] == "access_unfrozen",
        "编译后确认": lambda e: e["kind"] == "claim_confirmed",
        "授予": lambda e: e["kind"] == "capability_granted" and not e["actor"].startswith(("seed", "system")),
        "撤销": lambda e: e["kind"] == "capability_revoked",
        "挂起": lambda e: e["kind"] == "capability_suspended",
        "适用范围扩展": lambda e: e["kind"] == "scope_extended",
        "同层申请": lambda e: e["kind"] == "share_requested",
        "解密审批": lambda e: e["kind"] in ("decrypt_approve",),
    }
    families = {"回问": "ask_back", "退回重新转译": "trial_rework", "机会汇聚": "opportunity",
                "知识冲突": "knowledge_conflict", "泄露风险": "leak_risk", "追问产品内部": "mechanism_followup", "失真": "distortion",
                "试样风险": "trial_risk", "判断过时": "stale_capability", "复核": "qi_review"}
    out = {}
    for name, test in ev.items():
        e = next((e for e in events if day(e["ts"]) >= 1 and test(e)), None)
        out[name] = {"day": day(e["ts"]), "object": obj(e)} if e else None
    qs = sorted(questions.values(), key=lambda q: q["created_at"])
    for name, family in families.items():
        q = next((q for q in qs if q["family"] == family), None)
        out[name] = {"day": day(q["created_at"]), "object": q["object_id"]} if q else None
    signed = lambda pred: next((q for q in sorted(questions.values(), key=lambda q: q["resolved_at"] or "9999")  # noqa: E731
                                if q["resolution"] and pred(q)), None)
    for name, pred in {
        "收窄": lambda q: q["family"] == "stale_capability" and q["resolution"]["note"].startswith("收窄"),
        "同层授予": lambda q: q["family"] == "qi_grant" and "requester" in q["refs"] and q["resolution"]["action"] == "sign",
        "试样风险先回问": lambda q: q["family"] == "trial_risk" and q["resolution"]["note"].startswith("试样前回问"),
    }.items():
        q = signed(pred)
        out[name] = {"day": day(q["resolved_at"]), "object": q["object_id"]} if q else None
    zero = data["summary"].get("day_zero", {})
    out["编译"] = {"day": 0, "object": f"{zero.get('compiled', 0)} 条候选结论"} if zero.get("compiled") else None
    return out


def _requirements_by_session(events: list[dict]) -> dict:
    out = defaultdict(list)
    for e in events:
        if e["kind"] == "requirement_created":
            for sid in e["payload"]["session_ids"]:
                out[sid].append(e["payload"]["requirement_id"])
    return out


def _visits(events: list[dict]) -> dict:
    """(客户, 来访时刻) → 会话：两组同一批客户在同一时刻来访，用它把两组的同一件事配对。"""
    out = {}
    for e in events:
        if e["kind"] == "turn" and e["actor"].startswith("customer:") and e["session_id"] not in out.values():
            out.setdefault((e["actor"], e["ts"][:16]), e["session_id"])
    return out


def _case(data: dict, sid: str, reqs: dict) -> dict:
    rids = set(reqs.get(sid, []))
    verdicts = [v for v in data["world"] if v["requirement_id"] in rids]
    trials = [e["payload"] for e in data["events"] if e["kind"] == "trial" and e["payload"].get("requirement_id") in rids]
    qs = [q for q in data["questions"].values() if q["object_id"].split(":", 1)[-1] in rids or q["object_id"] == f"session:{sid}"]
    returned = [q for q in qs if q["family"] == "trial_risk" and q["resolution"] and q["resolution"]["note"].startswith("试样前回问")]
    return {"session": sid, "requirements": sorted(rids),
            "would_fail_requirement": sum(v["result"] == "fail" and v["cause"] == "requirement" for v in verdicts),
            "trial_risk_raised": sum(q["family"] == "trial_risk" for q in qs), "returned_before_trial": len(returned),
            "failed_requirement": sum(t["result"] == "fail" and t["cause"] == "requirement" for t in trials),
            "passed": sum(t["result"] == "pass" for t in trials),
            "missing_slots": sorted({s for t in trials for s in t["missing_slots"]})}


def forks(jue_dir: Path, sm_dir: Path) -> dict:
    """两组同一件事（同客户、同来访时刻）走得不一样的地方：一边因需求条件缺失试样失败、另一边试样前就回问了。"""
    a, b = load(jue_dir), load(sm_dir)
    va, vb = _visits(a["events"]), _visits(b["events"])
    ra, rb = _requirements_by_session(a["events"]), _requirements_by_session(b["events"])
    out = []
    for key in sorted(va.keys() & vb.keys(), key=lambda k: k[1]):
        ja, sb = _case(a, va[key], ra), _case(b, vb[key], rb)
        if (ja["failed_requirement"], ja["returned_before_trial"]) != (sb["failed_requirement"], sb["returned_before_trial"]):
            out.append({"customer": key[0], "at": key[1], "jue": ja, "sm": sb})
    win = lambda x, y: x["failed_requirement"] < y["failed_requirement"]     # noqa: E731
    return {"pairs": len(va.keys() & vb.keys()), "differ": len(out),
            "jue_better": sum(win(f["jue"], f["sm"]) for f in out), "sm_better": sum(win(f["sm"], f["jue"]) for f in out),
            "cases": out}


def grant_effects(run_dir: Path) -> list[dict]:
    """运行中人签的授予：授予后被用了几次、撤销或挂起之后还有没有被用（应为 0）。"""
    events = load(run_dir)["events"]
    ends = {e["payload"]["capability_id"]: e["ts"] for e in events if e["kind"] in ("capability_revoked", "capability_suspended")}
    used = defaultdict(list)
    for e in events:
        if e["kind"] == "capability_used":
            used[e["payload"]["capability_id"]].append(e["ts"])
    out = []
    for e in events:
        if e["kind"] == "capability_granted" and not e["actor"].startswith(("seed", "system")):
            cid, end = e["payload"]["id"], ends.get(e["payload"]["id"])
            out.append({"capability": cid, "form": e["payload"]["form"], "by": e["actor"], "at": e["ts"],
                        "audience": e["payload"]["audience"], "uses": sum(e["ts"] <= t < (end or "9999") for t in used[cid]),
                        "ended": end, "uses_after_end": sum(end is not None and t >= end for t in used[cid])})
    return out


def rules_on_month(run_dir: Path, templates_dir: str = "config/templates") -> dict:
    """试样风险：本组实际打分与三条候选规则，在本月每次技术确认后的第一次打分上比；标签是世界在那次确认时的判定
    （照原样试样会不会因需求条件缺失失败），与有没有被拦下无关。"""
    from huayan.contracts import JueObject
    from huayan.jue.proto import load_templates, rule_score
    from huayan.jue.records import load_records
    from sklearn.metrics import roc_auc_score
    from run_month import CANDIDATES

    data = load(run_dir)
    tpl = {t.family: t for t in load_templates(templates_dir).values()}["trial_risk"]
    scored = defaultdict(list)
    for r in load_records(run_dir):
        for d in r.output.decisions:
            if d.family == "trial_risk" and d.p_need is not None:
                scored[d.object_id.split(":", 1)[1]].append((r.state.at.isoformat(), d.p_need, r.state.objects[d.object_id]))
    verdicts = defaultdict(list)
    for v in data["world"]:
        verdicts[v["requirement_id"]].append(v)
    y, own, objs = [], [], []
    for rid, vs in verdicts.items():
        vs.sort(key=lambda v: v["at"])
        for i, v in enumerate(vs):
            end = vs[i + 1]["at"] if i + 1 < len(vs) else "9999"
            first = next((s for s in sorted(scored[rid], key=lambda s: s[0]) if v["at"] <= s[0] < end), None)
            if first:
                y.append(int(v["result"] == "fail" and v["cause"] == "requirement"))
                own.append(first[1])
                objs.append(first[2])
    y = np.array(y)
    out = {"n": len(y), "would_fail": int(y.sum())}
    scores = {"本组": np.array(own)} | {k: np.array([rule_score(tpl.model_copy(update={"rule_score": e}), o) for o in objs])
                                       for k, e in CANDIDATES["trial_risk"].items()}
    for name, s in scores.items():
        hit = s >= 0.5
        out[name] = {"auc": round(float(roc_auc_score(y, s)), 3) if len(set(y)) > 1 and len(set(s)) > 1 else None,
                     "raised": int(hit.sum()), "caught": int((hit & (y == 1)).sum())}
    return out


def report(jue_dir: Path, sm_dir: Path, out: Path) -> dict:
    result = {"jue": metrics(jue_dir), "sm": metrics(sm_dir), "forks": forks(jue_dir, sm_dir),
              "grants": {"jue": grant_effects(jue_dir), "sm": grant_effects(sm_dir)},
              "rules": {"jue": rules_on_month(jue_dir), "sm": rules_on_month(sm_dir, "data/enterprise/templates_sm")}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return result


if __name__ == "__main__":       # python -m huayan.eval.month <觉组运行目录> <状态机组运行目录> [输出]
    import sys
    report(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3] if len(sys.argv) > 3 else "docs/reports/month/month.json"))
