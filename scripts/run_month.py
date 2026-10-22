"""REPLAN-v8 Q9.4：模拟业务月，两组各跑一个进程（可同时跑）：
  觉组（--group jue）：实时与定时都用 Jue-K，第 0 周用 data/models_v8，每周末用本组的决策记录与结果重训；
  状态机组（--group sm）：全部家族规则打分；试样风险、判断过时用三条候选规则里在验证集上最强的一条，全月不变。
两组同一批客户、同一世界、同一套人设；缓存各自一份（两组从第一次追问起就分开）。
每格打一行进度、写 runs/<运行>/progress.json；结束写 sim_log、world.jsonl（世界的判定，只供 eval/）与 month_summary.json。
先运行 scripts/make_enterprise.py；密钥取环境变量 TRIAL_API_KEY（set -a; source .env）。

  uv run python scripts/run_month.py --group jue [--days 20 --seed 0 --limit 12 --timeout 20 --script-at 2 --replay]
"""
import argparse
import json
import pickle
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import roc_auc_score

from huayan.app import HuayanApp
from huayan.clock import set_clock
from huayan.contracts import JueObject, SHANGHAI
from huayan.jue.jue_k import JueK
from huayan.jue.proto import load_templates, rule_score
from huayan.jue.records import OUTCOME_FAMILIES, decision_rows, load_records
from huayan.jue.train import _split, fit
from huayan.sim.humans import LLMHumans, OPEN, load_personas
from huayan.sim.month import START, Month, copy_rag, script_days
from huayan.sim.schedule import Gate, ThreadClock, gate_gateway
from train_jue_k import sample_rows

CONFIG = Path("data/enterprise/app.yaml")
SAMPLES = Path("data/jue_k_v8/samples.csv")        # Q9.1、Q9.2 生成的训练数据（data/models_v8 由它训练）
BASE_MODEL = Path("data/models_v8")
RECENT_WEIGHT = 30     # 周末重训时，本组以结果为标签的决策行（试样风险、判断过时）重复 30 次：相当于按近期窗口加权
SM_TEMPLATES = Path("data/enterprise/templates_sm")
# 状态机组的候选规则（原文写进报告）。S3「最近 7 天失败 ≥ 2 次」没有对应的计数属性，用最近 7 天失败率与累计失败数近似
CANDIDATES = {
    "trial_risk": {"R1": "0.6 * (attrs.n_unknown_required >= 1)",
                   "R2": "0.6 * (attrs.n_unknown_required >= 1 or attrs.n_unquoted_slots >= 1)",
                   "R3": "0.6 * (attrs.hist_fail_rate >= 0.3 or attrs.n_unknown_required >= 1)"},
    "stale_capability": {"S1": "(attrs.n_fail >= 2) * attrs.fail_rate",
                         "S2": "0.6 * (attrs.n_outcomes >= 3 and attrs.fail_rate >= 0.3)",
                         "S3": "0.6 * (attrs.recent_fail_rate >= 0.4 and attrs.n_fail >= 2)"},
}


def sm_templates(rows: list[dict]) -> dict:
    """在验证集上比较候选规则的 AUC，把最强的一条写进状态机组的模板副本。"""
    shutil.rmtree(SM_TEMPLATES, ignore_errors=True)
    shutil.copytree("config/templates", SM_TEMPLATES)
    templates = {t.family: t for t in load_templates(SM_TEMPLATES).values()}
    chosen = {}
    for family, rules in CANDIDATES.items():
        val = [r for r in rows if r["family"] == family and _split(r) == "val"]
        objs = [JueObject(object_id=r["object_id"], object_type=r["object_type"], attrs=r["attrs"]) for r in val]
        y = np.array([r["label"] for r in val])
        aucs = {k: round(float(roc_auc_score(y, [rule_score(templates[family].model_copy(update={"rule_score": e}), o)
                                                  for o in objs])), 3) for k, e in rules.items()}
        best = max(aucs, key=aucs.get)
        path = SM_TEMPLATES / f"{family}.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["rule_score"] = rules[best]
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        chosen[family] = {"rule": best, "expr": rules[best], "val_auc": aucs, "n_val": len(val)}
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["jue", "sm"], required=True)
    ap.add_argument("--days", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=12, help="同时在途的模型调用上限")
    ap.add_argument("--timeout", type=float, default=20, help="单次模型调用超时（秒），超时由网关重试")
    ap.add_argument("--script-at", type=int, help="冒烟用：全部剧本事件挪到这一天")
    ap.add_argument("--replay", action="store_true", help="只用录制缓存并按录制的并发顺序走，未命中即报错")
    args = ap.parse_args()

    tag = f"month-{args.group}-{args.seed}-d{args.days}" + (f"-s{args.script_at}" if args.script_at else "")
    run_id = f"{tag}-{'replay' if args.replay else 'record'}"
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    # v8 Q9.8：leak_risk 属性已改（只看业务员），旧格作废；新特征下重训之前两组都用同一条规则
    base = [r for r in sample_rows(pd.read_csv(SAMPLES, low_memory=False), "config/templates") if r["family"] != "leak_risk"]
    rag = copy_rag(Path("data/enterprise/rag") / run_id)
    run_dir = Path(config["run_root"]) / run_id
    shutil.rmtree(run_dir, ignore_errors=True)
    config.update(replay=args.replay, llm_cache_dir=str(Path(config["llm_cache_dir"]) / args.group),
                  sources=[{"name": f"{k}（模拟副本）", "kind": k, "root": str(rag / k)} for k in ("public", "internal")])
    chosen = {}
    if args.group == "jue":
        models = run_dir.parent / f"{run_id}-models"
        shutil.rmtree(models, ignore_errors=True)
        shutil.copytree(BASE_MODEL, models / "w0")
        artifact = pickle.loads((models / "w0" / "model.pkl").read_bytes())
        artifact["models"] = {c: m for c, m in artifact["models"].items() if not c.startswith("leak_risk|")}
        (models / "w0" / "model.pkl").write_bytes(pickle.dumps(artifact))
        config.update(realtime_model="jue_k", scheduled_model="jue_k", jue_k_dir=str(models / "w0"))
    else:
        chosen = sm_templates(base)
        config.update(templates_dir=str(SM_TEMPLATES))
    path = CONFIG.with_name(f"app.{run_id}.yaml")
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    clock = ThreadClock(datetime.combine(START, OPEN, tzinfo=SHANGHAI) - timedelta(minutes=1))
    set_clock(clock)
    app = HuayanApp.build(str(path), run_id)
    record_dir = run_dir.with_name(f"{tag}-record")
    gate = Gate(json.loads((record_dir / "schedule.json").read_text(encoding="utf-8")) if args.replay else None)
    gate_gateway(app.gateway, gate, args.limit, args.timeout)
    humans = LLMHumans(app, load_personas())
    versions = []

    def retrain(app, week):
        """周末重训：第 0 周的训练行 + 本组到目前为止有标签的决策行（以结果为标签的加权）；新模型换上实时与定时两处。"""
        own = [r for r in decision_rows(load_records(app.run_dir), app.events) if r["family"] != "leak_risk"]
        rows = base + [r for r in own for _ in range(RECENT_WEIGHT if r["family"] in OUTCOME_FAMILIES else 1)]
        out = Path(app.config["jue_k_dir"]).parent / f"w{week}"
        summary = fit(rows, app.config["templates_dir"], out)
        app.config["jue_k_dir"] = str(out)
        path.write_text(yaml.safe_dump(app.config, allow_unicode=True), encoding="utf-8")   # 时间线页读当前版本
        app.jue_realtime = JueK(out, app.config["templates_dir"], "realtime", app.meter)
        app.jue_scheduled = JueK(out, app.config["templates_dir"], "scheduled", app.meter)
        versions.append({"week": week, "rows_from_run": len(own), "outcome_rows": sum(r["family"] in OUTCOME_FAMILIES for r in own),
                         "cells": {c: s["scored_by"] for c, s in summary.items()}})
        return f"w{week}，本组决策行 {len(own)}，Jue-K 格 {sum(s['scored_by'] == 'jue_k' for s in summary.values())}"

    month = Month(app, humans, gate, clock, config, args.seed, args.group, script_days(args.script_at), rag,
                  retrain if args.group == "jue" else None, log=lambda s: print(s, flush=True))
    zero = month.day_zero()
    print(f"[{args.group}] 第 0 周：{zero}；状态机规则：{ {f: c['rule'] for f, c in chosen.items()} }", flush=True)
    month.run(args.days)

    if not args.replay:
        (app.run_dir / "schedule.json").write_text(json.dumps(gate.order), encoding="utf-8")
    (app.run_dir / "sim_log.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in humans.log),
                                               encoding="utf-8")
    (app.run_dir / "world.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in humans.verdicts),
                                             encoding="utf-8")
    (app.run_dir / "cards.json").write_text(json.dumps({sid: c.model_dump() for sid, c in humans.cards.items()},
                                                       ensure_ascii=False), encoding="utf-8")
    summary = {"run": run_id, "group": args.group, "days": args.days, "day_zero": zero, "sm_rules": chosen,
               "retrain": versions, **month.progress,
               "actions": Counter(r["family"] for r in humans.log),
               "questions": Counter(q.family for q in app.bus.list(status=None)),
               "agent_errors": Counter(f"{e['agent']}|{e['kind']}" for e in app.agents.errors())}
    (app.run_dir / "month_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
