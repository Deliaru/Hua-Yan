"""契约 ⑥：问题总线。同 dedup_key 合并，dismiss 后抑制，每次变化追加快照。"""
import builtins
from datetime import datetime, timedelta
from pathlib import Path

from huayan.contracts import QFamily, Question, Resolution, Role
from huayan.events import EventLog


class QuestionBus:
    def __init__(self, events: EventLog, path: Path | None = None, suppress_hours: float = 24):
        self.events = events
        self.path = Path(path) if path else None
        self.suppress = timedelta(hours=suppress_hours)
        self.questions: dict[str, Question] = {}
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _snapshot(self, q: Question) -> None:
        if self.path:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(q.model_dump_json() + "\n")

    def publish(self, q: Question) -> Question:
        same = [x for x in self.questions.values() if x.dedup_key == q.dedup_key]
        for existing in same:
            if existing.status == "open":
                existing.evidence.extend(e for e in q.evidence if e not in existing.evidence)
                self._snapshot(existing)
                return existing
        if any(x.status == "dismissed" and q.created_at - x.resolved_at < self.suppress for x in same):
            return q
        q = q.model_copy(update={"id": f"q:{len(self.questions) + 1}"})
        self.questions[q.id] = q
        self.events.append("question_published", q.discoverer,
                           {"question_id": q.id, "family": q.family, "object_id": q.object_id},
                           session_id=q.refs.get("session_id"), ts=q.created_at)
        self._snapshot(q)
        return q

    def get(self, qid: str) -> Question:
        return self.questions[qid]

    def list(self, owner_role: Role | None = None, status: str | None = "open",
             family: QFamily | None = None) -> builtins.list[Question]:
        return [q for q in self.questions.values()
                if (owner_role is None or q.owner_role == owner_role) and (status is None or q.status == status)
                and (family is None or q.family == family)]

    def resolve(self, qid: str, resolution: Resolution, at: datetime) -> Question:
        q = self.questions[qid]
        q.status = "dismissed" if resolution.action == "dismiss" else "resolved"
        q.resolution, q.resolved_at = resolution, at
        self.events.append("question_resolved", resolution.by,
                           {"question_id": q.id, "family": q.family, "object_id": q.object_id,
                            "action": resolution.action},
                           session_id=q.refs.get("session_id"), ts=at)
        self._snapshot(q)
        return q
