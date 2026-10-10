"""契约 5.4：定时扫描 = scheduled_state → propose → publish；回问 = requirement_state → propose → publish。"""
from datetime import datetime

from huayan.bus import QuestionBus
from huayan.contracts import JueTemplate, NeedState, Product, Question, QuestionModel, Requirement, Seeds
from huayan.events import EventLog
from huayan.jue.publish import publish
from huayan.jue.state import collect_scheduled, requirement_state


def scan(events: EventLog, at: datetime, model: QuestionModel, seeds: Seeds, products: list[Product],
         templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float,
         windows: dict | None = None) -> list[Question]:
    state, refs = collect_scheduled(events, at, seeds, products, windows)
    return publish(model.propose(state), state, templates, bus, threshold, seeds=seeds, refs=refs)


def scan_requirement(req: Requirement, need: NeedState, at: datetime, model: QuestionModel, seeds: Seeds, kb,
                     templates: dict[str, JueTemplate], bus: QuestionBus, threshold: float) -> list[Question]:
    """need = 需求单首个会话的 NeedState；回问发给该会话的业务员。门面要写 JueRecord 时可自行分三步调用。"""
    state = requirement_state(req, need, seeds, kb, at)
    refs = {oid: {"session_id": need.session_id, "sales_id": need.sales_id} for oid in state.objects}
    return publish(model.propose(state), state, templates, bus, threshold, seeds=seeds, refs=refs)
