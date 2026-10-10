# 复用自 JUE 赛前代码 src/jue/meter.py（FileMeter(run_dir, run_id)，字段按契约 ⑩）
"""Contract-shaped JSONL metering."""

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from huayan.contracts import MeterRecord


class FileMeter:
    def __init__(self, run_dir, run_id):
        self.path = Path(run_dir) / "metering.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.s1_latency_ms = defaultdict(float)

    def record(self, *, caller, kind, **fields):
        record = MeterRecord(ts=datetime.now(timezone.utc), run_id=self.run_id, caller=caller, kind=kind, **fields)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(record.model_dump_json() + "\n")
        if kind == "s1":
            self.s1_latency_ms[caller] += record.latency_ms
