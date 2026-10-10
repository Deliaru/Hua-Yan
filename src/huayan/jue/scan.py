"""契约 5.4：定时扫描 = scheduled_state → propose → publish。"""
from datetime import datetime

from huayan.bus import QuestionBus
from huayan.contracts import JueTemplate, Product, Question, QuestionModel, Seeds
from huayan.events import EventLog
from huayan.jue.publish import publish
from huayan.jue.state import collect_scheduled


def scan(events: EventLog, at: datetime, model: QuestionModel, seeds: Seeds, products: list[Product],
         templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float,
         windows: dict | None = None) -> list[Question]:
    state, refs = collect_scheduled(events, at, seeds, products, windows)
    return publish(model.propose(state), state, templates, bus, threshold, seeds=seeds, refs=refs)
