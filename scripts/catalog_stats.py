"""目录飞轮统计（WP-J）：读一个运行目录的事件日志，按模板统计提出与处置、按「动作 × 对象类型」统计人自发决策，
写 runs/<run_id>/catalog_stats.json 与一页 docs/reports/catalog_stats.md。只报计数与比率，不给阈值建议。

uv run python scripts/catalog_stats.py --run runs/week-w1-jue_k-handle --injections data/week/w1/injections.jsonl
"""
import argparse
import json
from pathlib import Path

from huayan.contracts import Event, Injection
from huayan.eval.catalog import human_decisions, template_stats
from huayan.jue.proto import load_templates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--templates", default="config/templates")
    ap.add_argument("--injections", default=None, help="注入清单；给出时计算定时三类的误报率")
    ap.add_argument("--out", default="docs/reports/catalog_stats.md")
    args = ap.parse_args()

    run = Path(args.run)
    events = [Event.model_validate_json(l) for l in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    injections = None
    if args.injections:
        injections = [Injection.model_validate_json(l)
                      for l in Path(args.injections).read_text(encoding="utf-8").splitlines()]
    result = {"run": str(run), "injections": args.injections,
              "templates": template_stats(events, load_templates(args.templates), injections),
              "human_decisions": human_decisions(events)}
    (run / "catalog_stats.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out).write_text(_markdown(result), encoding="utf-8")
    print(_markdown(result))
    print(f"写出 {run / 'catalog_stats.json'}、{args.out}")


def _fmt(x) -> str:
    return "—" if x is None else f"{x:.0%}" if isinstance(x, float) else str(x)


def _markdown(r: dict) -> str:
    lines = ["# 决策目录统计（目录飞轮的数据）", "",
             f"运行：`{r['run']}`；注入清单：`{r['injections'] or '无'}`。", "",
             "只报计数与比率，**不给阈值建议**：模拟业务周的处置由脚本定，按它调阈值是循环论证（REPLAN 4.5）。"
             "被忽略率 = dismiss / 提出；机会汇聚里产品经理 Agent 判断「不是同一件事」后的 dismiss 单列，不计入被忽略。"
             "误报率只对定时三类、且给出注入清单时计算：提出的问题中不对应正注入的比例。", "",
             "| 模板 | 类 | 提出 | 签字 | 退回 | dismiss | 不是同一件事 | 自动关闭 | 未处置 | 被忽略率 | 误报率 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for tid, s in r["templates"].items():
        lines.append(f"| `{tid}` | {'推进' if s['kind'] == 'advance' else '异常'} | {s['proposed']} | {s['signed']} | "
                     f"{s['returned']} | {s['dismissed']} | {s['dismissed_not_same']} | {s['auto_closed']} | {s['open']} | "
                     f"{_fmt(s['ignored_rate'])} | {_fmt(s.get('false_alarm_rate'))} |")
    lines += ["", "## 人自发决策（执行生效动作时同一对象上没有对应的已提出问题）", ""]
    if not r["human_decisions"]:
        lines.append("本次运行没有人自发决策（模拟业务周不产生 `human_decision`，C12）。")
    for key, g in r["human_decisions"].items():
        attrs = "，".join(f"{k} {v}" for k, v in g["attrs_mean"].items())
        lines.append(f"- {key}：{g['n']} 次；属性快照均值：{attrs or '—'}")
    lines += ["", "按「动作 × 对象类型」聚类、学出候选前置条件属于第 3 阶段，本次只记录数据。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
