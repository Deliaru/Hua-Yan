"""契约 5.4：读取门面写的 JueRecord，以及问题的处置（标签）。标签不另存，全部来自 question_resolved 事件。"""
from collections import defaultdict
from pathlib import Path

from huayan.contracts import ROLE_LEVEL, JueRecord
from huayan.events import EventLog


def load_records(run_dir: str | Path) -> list[JueRecord]:
    path = Path(run_dir) / "jue_samples.jsonl"
    if not path.exists():
        return []
    return [JueRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def outcomes(events: EventLog) -> dict[str, str]:
    """question_id → 处置动作（sign / accept / return / answered / dismiss …）；未处置的问题不在其中。"""
    return {e.payload["question_id"]: e.payload["action"] for e in events.query(["question_resolved"])}


def _human_level(by: str) -> int | None:
    """处置人所在层；觉（jue、jue:auto）、Agent（pm:agent）与系统的决定不是人的判断，永不当标签。"""
    role = by.split(":", 1)[0]
    return None if by == "pm:agent" or role not in ROLE_LEVEL else ROLE_LEVEL[role]


def decision_rows(records: list[JueRecord], events: EventLog) -> list[dict]:
    """决策投影（纯函数，不落盘）。一行 = 觉提出的一个决策点：当时的属性与 p_need、谁怎么处置、用到的能力；
    另加与觉无关的结果：试样因需求条件缺失失败、客户评价不通过所指向的条件，作为该需求单回问对象的正例。
    label：人处置为 dismiss 记 0，其余处置记 1，没有人的处置为 None；
    judge_level：代哪一层判断（槽位对象自带，其余取处置人所在层）；level：结果来自哪一层的判断（不低于 judge_level）。"""
    scored = defaultdict(list)
    for record in records:
        for d in record.output.decisions:
            scored[d.object_id].append((record.state.at, record, d))
    resolved = {e.payload["question_id"]: e for e in events.query(["question_resolved"])}
    used = defaultdict(list)
    for e in events.query(["capability_used"]):
        used[e.session_id].append(e.payload["capability_id"])

    def row(at, record, d, by, action, label, level):
        obj = record.state.objects[d.object_id]
        judge = obj.attrs.get("judge_level", level)
        return {"family": d.family, "object_type": obj.object_type, "object_id": d.object_id, "at": at.isoformat(),
                "attrs": obj.attrs, "p_need": d.p_need, "by": by, "action": action, "label": label,
                "judge_level": judge, "level": None if level is None else max(judge, level)}

    rows = []
    for pub in events.query(["question_published"]):
        p = pub.payload
        earlier = [x for x in scored[p["object_id"]] if x[2].family == p["family"] and x[2].p_need is not None
                   and x[0] <= pub.ts]
        if not earlier:
            continue        # 不是觉提出的（人手工发布）
        res = resolved.get(p["question_id"])
        by, action = (res.payload["by"], res.payload["action"]) if res else (None, None)
        level = _human_level(by) if by else None
        label = None if level is None else int(action != "dismiss")
        rows.append(row(*earlier[-1], by, action, label, level) | {"capabilities": used[pub.session_id] if pub.session_id else []})
    # 结果：哪个条件导致失败是研发的判断（L3）；客户评价不通过时由业务员按客户反馈勾选（L1）
    for e in events.query(["trial", "market_eval"]):
        p = e.payload
        if e.kind == "trial" and p["result"] == "fail" and p["cause"] == "requirement":
            slots, level = p["missing_slots"], 3
        elif e.kind == "market_eval" and p["result"] == "fail":
            slots, level = p["missing_slots"], 1
        else:
            continue
        for slot in slots:
            earlier = [x for x in scored[f"slot:{p['requirement_id']}/{slot}"] if x[2].family == "ask_back" and x[0] <= e.ts]
            if earlier:
                rows.append(row(*earlier[-1], e.actor, f"{e.kind}_missing", 1, level) | {"capabilities": []})
    return rows


def rows_for(rows: list[dict], level: int) -> list[dict]:
    """只留结果层级不高于 level 的行：客户层的习惯只从客户层的结果里学。"""
    return [r for r in rows if r["level"] is not None and r["level"] <= level]
