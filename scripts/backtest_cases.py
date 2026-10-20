"""Q7.5 真实案例回测（huayan.eval.backtest）。案例文件与报告都在 data/backtest/，不入库；能否公开按组委会的保密边界定。

案例文件（YAML）：
  simulated: false            # true = 不是真实案例（例如只为验证跑通），报告标题会写明
  cases:
    - {id, source: oral|raw|restored|summary, first_words, final_conditions: {槽位: 取值}, late_conditions: [槽位], phenomenon}
问答样例（可选，YAML）：questions: [同一个业务问题, ...]

  uv run python scripts/backtest_cases.py --cases data/backtest/cases.yaml [--qa data/backtest/qa.yaml]
      [--evolved data/jue_evolution/seed0/models/evolving/W4] [--live]
--live：一次性翻译组走真实强模型（config/models.yaml）；默认离线，该组为桩，报告标注。
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, set_clock
from huayan.eval.backtest import (SOURCES, fingerprint, load_cases, one_shot_impl, qa_table, run_jue, run_one_shot,
                                  run_relay, use_model)
from huayan.ui.server import T0

WORK = Path("data/backtest")
SEED = 20261020


def build(live, name, model_dir):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(realtime_model="jue_k", jue_k_dir=str(model_dir), gateway_mock=not live, run_root=str(WORK / "runs"))
    path = WORK / f"app.{name}.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(path))
    use_model(app, model_dir)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(WORK / "cases.yaml"))
    ap.add_argument("--qa")
    ap.add_argument("--frozen", default="models/jue_k")
    ap.add_argument("--evolved", default="data/jue_evolution/seed0/models/evolving/W4")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    set_clock(SimClock(T0))
    frozen = build(args.live, "frozen", args.frozen)
    evolved = build(args.live, "evolved", args.evolved)
    simulated, cases = load_cases(args.cases, frozen.seeds)
    relay = yaml.safe_load(Path("config/eval/distortion.yaml").read_text(encoding="utf-8"))["relay"]
    rows = []
    for case in cases:
        rows.append({"case": case.model_dump(), "jue_frozen": run_jue(frozen, case, SEED),
                     "jue_evolved": run_jue(evolved, case, SEED), "relay": run_relay(frozen, case, SEED, relay),
                     "one_shot": run_one_shot(frozen, case)})
    qa = qa_table(frozen, yaml.safe_load(Path(args.qa).read_text(encoding="utf-8"))["questions"]) if args.qa else []
    result = {"simulated": simulated, "cases_file": args.cases, "n": len(cases),
              "by_source": {s: sum(c.source == s for c in cases) for s in SOURCES}, "vocabulary": fingerprint(),
              "models": {"frozen": args.frozen, "evolved": args.evolved}, "one_shot": one_shot_impl(frozen),
              "relay_assumption": relay, "runs": {"frozen": str(frozen.run_dir), "evolved": str(evolved.run_dir)},
              "rows": rows, "qa": qa}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (WORK / "report.md").write_text(page(result), encoding="utf-8")
    print(page(result))


def page(r):
    groups = {"jue_frozen": "觉（冻结）", "jue_evolved": "觉（进化后）", "relay": "业务员转述", "one_shot": "一次性翻译"}
    title = "# 案例回测" + ("（模拟样本，只验证跑通，不是真实案例）" if r["simulated"] else "")
    v = r["vocabulary"]
    lines = [title, "",
             f"- 样本：`{r['cases_file']}`，{r['n']} 条；按输入类型：" + "、".join(f"{k} {n}" for k, n in r["by_source"].items()),
             f"- 冻结词表：`{v['path']}` sha256 {v['sha256']}，修改时间 {v['modified']}；看过回测答案后不改词表、不改模板",
             f"- 觉：冻结 `{r['models']['frozen']}`，进化后 `{r['models']['evolved']}`；一次性翻译：{r['one_shot']}",
             f"- 转述组按失真对照的假设参数：{r['relay_assumption']}",
             "- 口径：第一轮问到晚到条件 = 晚到条件出现在客户第一句话之后觉的提示里（转述组：在业务员习惯问的槽位里；一次性翻译：在 to_confirm 里）；"
             "完整 = 研发视图的必问条件里客户知道的，全部取值正确（觉组按会话结束时的已知条件算，不论是否升级；转述与一次性翻译本来就交给研发）", ""]
    by_source = defaultdict(list)
    for row in r["rows"]:
        by_source[row["case"]["source"]].append(row)
    lines += ["| 输入类型 | 组 | 第一轮问到晚到条件 | 必问信息完整 | 进研发 |", "|---|---|---|---|---|"]
    for source, rows in list(by_source.items()) + [("全部", r["rows"])]:
        for key, name in groups.items():
            got = [row[key] for row in rows]
            late = sum(len(x["late_first"]) for x in got)
            total_late = sum(len(row["case"]["late_conditions"]) for row in rows)
            esc = f"{sum(x['escalated'] for x in got)}/{len(got)}" if "escalated" in got[0] else "全部"
            lines.append(f"| {source} | {name} | {late}/{total_late} | {sum(x['complete'] for x in got)}/{len(got)} | {esc} |")
    worse = [row["case"]["id"] for row in r["rows"]
             if len(row["jue_evolved"]["late_first"]) < len(row["jue_frozen"]["late_first"])
             or (row["jue_frozen"]["complete"] and not row["jue_evolved"]["complete"])]
    behind = [row["case"]["id"] for row in r["rows"]
              if len(row["jue_evolved"]["late_first"]) < max(len(row["relay"]["late_first"]), len(row["one_shot"]["late_first"]))]
    lines += ["", "## 不利结果", "",
              f"- 进化后不如冻结的案例：{'、'.join(worse) or '无'}",
              f"- 觉第一轮问到的晚到条件少于某个对照组的案例：{'、'.join(behind) or '无'}",
              f"- 觉没有识别出现象的案例：{'、'.join(row['case']['id'] for row in r['rows'] if not row['jue_frozen']['phenomenon_ok']) or '无'}",
              "", "## 逐条", "", "| 案例 | 输入类型 | 晚到条件 | 觉第一轮提示（冻结 / 进化后） | 升级 | 转述 | 一次性翻译 to_confirm |",
              "|---|---|---|---|---|---|---|"]
    for row in r["rows"]:
        c, f, e = row["case"], row["jue_frozen"], row["jue_evolved"]
        lines.append(f"| {c['id']} | {c['source']} | {'、'.join(c['late_conditions'])} | {'、'.join(f['first_round']) or '无'} / "
                     f"{'、'.join(e['first_round']) or '无'} | {'是' if f['escalated'] else '否'} / {'是' if e['escalated'] else '否'} | "
                     f"{'完整' if row['relay']['complete'] else '不完整'} | {'、'.join(row['one_shot']['to_confirm']) or '无'} |")
    if r["qa"]:
        lines += ["", "## 问答样例：同一问题三个身份看到什么", "", "| 问题 | 层 | 可读结论（归属） | 能力（授予人） | 存根 |", "|---|---|---|---|---|"]
        for q in r["qa"]:
            lines.append(f"| {q['question']} | {q['level']} | {'；'.join(q['readable']) or '无'} | "
                         f"{'；'.join(q['capabilities']) or '无'} | {'；'.join(q['stubs']) or '无'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
