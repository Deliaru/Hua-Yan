"""契约 ⑥：问题总线。同 dedup_key 合并，dismiss 后抑制，每次变化追加快照；v5 增加 set_prepared。"""
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
            if self.path.exists():      # 续跑：每个问题取最后一个快照
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line:
                        q = Question.model_validate_json(line)
                        self.questions[q.id] = q

    def _snapshot(self, q: Question) -> None:
        if self.path:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(q.model_dump_json() + "\n")

    def publish(self, q: Question) -> Question:
        same = [x for x in self.questions.values() if x.dedup_key == q.dedup_key]
        for existing in same:
            if existing.status == "open":
                existing.evidence.extend(e for e in q.evidence if e not in existing.evidence)
                existing.refs.update(q.refs)        # 引用随对象最新状态（如又有一张单判过同一适用）
                self._snapshot(existing)
                return existing
        if any(x.status == "dismissed" and q.created_at - x.resolved_at < self.suppress for x in same):
            return q
        q = q.model_copy(update={"id": f"q:{len(self.questions) + 1}"})
        self.questions[q.id] = q
        self.events.append("question_published", q.discoverer,
                           {"question_id": q.id, "family": q.family, "object_id": q.object_id,
                            "template_id": q.template_id},
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
                            "template_id": q.template_id, "action": resolution.action, "by": resolution.by},
                           session_id=q.refs.get("session_id"), ts=at)
        self._snapshot(q)
        return q

    def set_prepared(self, qid: str, at: datetime | None) -> Question:
        # 契约签名没有 by：准备完成的就是主人
        q = self.questions[qid]
        q.prepared_at = at
        if at is not None:
            by = q.owner_id or q.owner_role
            self.events.append("question_prepared", by, {"question_id": q.id, "family": q.family, "by": by},
                               session_id=q.refs.get("session_id"), ts=at)
        self._snapshot(q)
        return q
