"""内存账本与 UTF-8 JSONL 记录；引用去重由业务调用方负责。"""
from pathlib import Path

from huayan.contracts import AuditRecord, LedgerEntry


def _append(path, record):
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json() + "\n")


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self._records: list[AuditRecord] = []

    def append(self, record: AuditRecord) -> None:
        self._records.append(record)
        _append(self.path, record)

    def list(self, actor: str | None = None) -> list[AuditRecord]:
        return [r for r in self._records if actor is None or r.actor == actor]


class Ledger:
    def __init__(self, path: Path | None = None, *, points: dict[str, int] | None = None):
        self.path = Path(path) if path else None
        self._entries: list[LedgerEntry] = []
        self.points = {"cited": 1, "contributed": 5, "trial_pass": 5, "product_released": 10}
        if points is not None:
            self.points.update(points)

    def add(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)
        _append(self.path, entry)

    def list(self, owner: str | None = None) -> list[LedgerEntry]:
        return [e for e in self._entries if owner is None or e.owner == owner]

    def totals(self) -> dict[str, int]:
        totals = {}
        for entry in self._entries:
            totals[entry.owner] = totals.get(entry.owner, 0) + entry.points
        return totals

    def has(self, owner: str, ku_id: str, ref: str) -> bool:
        return any(e.reason == "cited" and (e.owner, e.ku_id, e.ref) == (owner, ku_id, ref)
                   for e in self._entries)
