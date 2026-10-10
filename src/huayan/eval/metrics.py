"""WP-E 业务周指标：读运行目录（questions.jsonl、events.jsonl、metering.jsonl）与注入清单，
算发现（是否在 [earliest, latest] 内发现、提前量、困难负样本误报）与机会汇聚处置的后果。"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from huayan.contracts import Injection, Question, Seeds
from huayan.jue.state import theme_id


def _lines(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def found_questions(run_dir: Path) -> list[Question]:
    """每个问题第一次出现时的快照（发布时刻 = 被发现的扫描时刻）。"""
    first = {}
    for row in _lines(run_dir / "questions.jsonl"):
        first.setdefault(row["id"], Question.model_validate(row))
    return list(first.values())


def detection(run_dir: Path, injections: list[Injection]) -> list[dict]:
    """每条注入一行：定时发现（觉 / 规则告警）的问题中 family 与 object_id 一致的最早一条。"""
    found = [q for q in found_questions(run_dir) if q.family in ("opportunity", "knowledge_conflict", "leak_risk")]
    rows = []
    for inj in injections:
        hits = sorted(q.created_at for q in found if q.family == inj.family and q.object_id == inj.object_id)
        at = hits[0] if hits else None
        in_window = at is not None and inj.earliest <= at <= inj.latest
        rows.append({"injection": inj.id, "family": inj.family, "object_id": inj.object_id,
                     "hard_negative": inj.hard_negative, "found_at": at.isoformat() if at else None,
                     "hit": in_window and not inj.hard_negative, "false_alarm": at is not None and inj.hard_negative,
                     "early": at is not None and at < inj.earliest and not inj.hard_negative,   # 证据还不够时就报了
                     "lead_hours": round((inj.latest - at).total_seconds() / 3600, 1) if in_window and not inj.hard_negative else None,
                     "delay_hours": round((at - inj.onset).total_seconds() / 3600, 1) if at else None})
    return rows


def summary(run_dir: Path, injections: list[Injection]) -> dict:
    rows = detection(run_dir, injections)
    targets = {i.object_id for i in injections}
    found = [q for q in found_questions(run_dir) if q.family in ("opportunity", "knowledge_conflict", "leak_risk")]
    meter = _lines(run_dir / "metering.jsonl")
    positives = [r for r in rows if not r["hard_negative"]]
    return {"hits": sum(r["hit"] for r in rows), "positives": len(positives),
            "false_alarms": sum(r["false_alarm"] for r in rows),
            "hard_negatives": sum(r["hard_negative"] for r in rows),
            "mean_lead_hours": _mean([r["lead_hours"] for r in rows if r["lead_hours"] is not None]),
            "n_found": len(found), "n_found_outside_injections": sum(q.object_id not in targets for q in found),
            "jue_llm_calls": sum(r["kind"] == "llm" and r["caller"].startswith("jue:") for r in meter),
            "detection": rows}


def consequences(run_dir: Path, theme: str, seeds: Seeds) -> dict:
    """同主题：发现之后的升级次数（产品经理被打扰次数）与 L1 直接命中次数；以及按天的升级次数。"""
    found = [q.created_at for q in found_questions(run_dir) if q.family == "opportunity" and q.object_id == theme]
    since = min(found) if found else None
    events = [e for e in _lines(run_dir / "events.jsonl") if e["kind"] in ("escalate", "recommend")
              and theme_id(e["payload"]["phenomenon"], e["payload"]["known"], seeds) == theme]
    after = [e for e in events if since and datetime.fromisoformat(e["ts"]) >= since]
    return {"theme": theme, "found_at": since.isoformat() if since else None,
            "escalations_after": sum(e["kind"] == "escalate" for e in after),
            "l1_hits_after": sum(e["kind"] == "recommend" for e in after),
            "escalations_by_day": dict(sorted(Counter(e["ts"][:10] for e in events if e["kind"] == "escalate").items())),
            "all_escalations": sum(e["kind"] == "escalate" for e in _lines(run_dir / "events.jsonl"))}


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None
