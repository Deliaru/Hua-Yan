"""契约 5.4：读取门面写的 JueRecord，以及问题的处置（标签）。标签不另存，全部来自 question_resolved 事件。"""
from pathlib import Path

from huayan.contracts import JueRecord
from huayan.events import EventLog


def load_records(run_dir: str | Path) -> list[JueRecord]:
    path = Path(run_dir) / "jue_samples.jsonl"
    if not path.exists():
        return []
    return [JueRecord.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def outcomes(events: EventLog) -> dict[str, str]:
    """question_id → 处置动作（sign / accept / return / answered / dismiss …）；未处置的问题不在其中。"""
    return {e.payload["question_id"]: e.payload["action"] for e in events.query(["question_resolved"])}
