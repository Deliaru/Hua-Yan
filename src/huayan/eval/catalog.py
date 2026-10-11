"""WP-J 目录飞轮的数据：按模板统计提出与处置，按「动作 × 对象类型」统计人自发决策。
只报计数与比率，不给阈值建议（模拟周的处置由脚本定，按它调阈值是循环论证，REPLAN 4.5）。
注入清单只在这里读（铁律 5），用于定时三类的误报率。"""
from collections import Counter, defaultdict

from huayan.contracts import Event, Injection, JueTemplate

SCHEDULED = ("opportunity", "knowledge_conflict", "leak_risk")


def template_stats(events: list[Event], templates: dict[str, JueTemplate],
                   injections: list[Injection] | None = None) -> dict[str, dict]:
    """每个模板：提出、签字（sign / accept）、退回、dismiss、异常类自动关闭、被忽略率；定时三类另有误报率。
    机会汇聚中产品经理 Agent 判断「不是同一件事」（merge_proposed 的 members 为空）之后的 dismiss 单列，不算觉提多了。"""
    published = {e.payload["question_id"]: e for e in events if e.kind == "question_published"}
    resolved = {e.payload["question_id"]: e.payload for e in events if e.kind == "question_resolved"}
    not_same = {e.payload["question_id"] for e in events if e.kind == "merge_proposed" and not e.payload["members"]}
    positives = {(i.family, i.object_id) for i in injections or [] if not i.hard_negative}
    stats = {}
    for tid, t in templates.items():
        qids = [qid for qid, e in published.items() if e.payload["template_id"] == tid]
        actions = Counter(resolved[qid]["action"] for qid in qids if qid in resolved)
        dismiss_not_same = sum(qid in not_same and resolved.get(qid, {}).get("action") == "dismiss" for qid in qids)
        n_dismiss = actions["dismiss"] - dismiss_not_same
        row = {"family": t.family, "kind": t.kind, "proposed": len(qids),
               "signed": actions["sign"] + actions["accept"], "returned": actions["return"],
               "dismissed": n_dismiss, "dismissed_not_same": dismiss_not_same,
               "auto_closed": sum(resolved[qid]["action"] == "answered" and resolved[qid]["by"] == "jue"
                                  for qid in qids if qid in resolved) if t.kind == "anomaly" else 0,
               "open": len(qids) - sum(actions.values()),
               "ignored_rate": round(n_dismiss / len(qids), 3) if qids else None,
               "actions": dict(actions)}
        if injections is not None and t.family in SCHEDULED:
            false = sum((t.family, published[qid].payload["object_id"]) not in positives for qid in qids)
            row["false_alarms"] = false
            row["false_alarm_rate"] = round(false / len(qids), 3) if qids else None
        stats[tid] = row
    return stats


def human_decisions(events: list[Event]) -> dict[str, dict]:
    """人自发决策按「动作 × 对象类型」计数，并给出每组数值属性快照的均值（不聚类、不生成候选模板）。"""
    groups = defaultdict(list)
    for e in events:
        if e.kind == "human_decision":
            groups[f"{e.payload['action']} × {e.payload['object_type']}"].append(e.payload["attrs"])
    out = {}
    for key, snaps in sorted(groups.items()):
        numeric = defaultdict(list)
        for attrs in snaps:
            for k, v in attrs.items():
                if isinstance(v, (bool, int, float)):
                    numeric[k].append(float(v))
        out[key] = {"n": len(snaps), "attrs_mean": {k: round(sum(v) / len(v), 3) for k, v in sorted(numeric.items())}}
    return out
