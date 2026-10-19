"""契约 ⑧：事件日志。内存列表 + 可选 JSONL 追加；文件已存在时逐行读回（续跑）。"""
from datetime import datetime
from pathlib import Path

from huayan.clock import get_clock
from huayan.contracts import Event, EventKind


class EventLog:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[Event] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self.events = [Event.model_validate_json(line)
                               for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def append(self, kind: EventKind, actor: str, payload: dict, *, session_id: str | None = None,
               ts: datetime | None = None) -> Event:
        event = Event(id=f"ev:{len(self.events) + 1}", ts=ts or get_clock().now(), kind=kind, actor=actor,
                      session_id=session_id, payload=payload)
        self.events.append(event)
        if self.path:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(event.model_dump_json() + "\n")
        return event

    def query(self, kinds: list[EventKind] | None = None, since: datetime | None = None,
              until: datetime | None = None, actor: str | None = None) -> list[Event]:
        """since、until 均为闭区间。"""
        return [e for e in self.events
                if (kinds is None or e.kind in kinds) and (since is None or e.ts >= since)
                and (until is None or e.ts <= until) and (actor is None or e.actor == actor)]
