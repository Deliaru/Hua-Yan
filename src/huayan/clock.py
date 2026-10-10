# 复用自 JUE 赛前代码 src/jue/clock.py（增加 WallClock，未设置时默认墙钟）
from datetime import datetime
from typing import Protocol

from pydantic import TypeAdapter

from huayan.contracts import SHANGHAI
from huayan.contracts._base import datetime as AwareShanghaiDatetime

_timestamp = TypeAdapter(AwareShanghaiDatetime)


class Clock(Protocol):
    def now(self) -> datetime: ...


class WallClock:
    def now(self) -> datetime:
        return datetime.now(SHANGHAI)


class SimClock:
    def __init__(self, start: datetime):
        self._now = _timestamp.validate_python(start)

    def now(self) -> datetime:
        return self._now

    def advance_to(self, ts: datetime) -> None:
        ts = _timestamp.validate_python(ts)
        if ts < self._now:
            raise ValueError("Simulation time cannot move backwards")
        self._now = ts


_clock: Clock | None = None


def get_clock() -> Clock:
    return WallClock() if _clock is None else _clock


def set_clock(clock: Clock | None) -> None:
    global _clock
    _clock = clock
