from datetime import datetime
from pathlib import Path

import pytest

from huayan.clock import SimClock, set_clock
from huayan.contracts import SHANGHAI
from huayan.domain import load_seeds

MINI_SEEDS = Path(__file__).parent / "fixtures" / "mini_seeds"
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=SHANGHAI)


@pytest.fixture(autouse=True)
def sim_clock():
    """每个测试使用固定起点的模拟时钟，结束后恢复墙钟。"""
    clock = SimClock(T0)
    set_clock(clock)
    yield clock
    set_clock(None)


@pytest.fixture
def mini_seeds():
    return load_seeds(MINI_SEEDS)
