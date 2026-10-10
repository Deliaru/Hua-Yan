"""契约 ⑨ / JUE_K_TRAINING 第 11 节：Jue-K 定时三类的样本。事件来自真实链路跑出的业务周（`eval.week.chain_events`，
与线上定时发现用同一条链路、同一个状态构建），每 2 个业务小时构建一次定时状态，按注入窗口打标签。"""
from datetime import datetime, time, timedelta

from huayan.contracts import Injection, Product, QuestionModel, Seeds
from huayan.events import EventLog
from huayan.jue.state import collect_scheduled

TICK_HOURS = (11, 13, 15, 17)          # 每个业务日 9:00 开工后每 2 小时扫描一次


def window_label(family: str, object_id: str, at: datetime, injections: list[Injection]) -> int:
    """落在某条非困难负样本注入的 [earliest, latest] 内、family 与 object_id 一致为 1。"""
    return int(any(not i.hard_negative and i.family == family and i.object_id == object_id
                   and i.earliest <= at <= i.latest for i in injections))


def week_rows(events: EventLog, injections: list[Injection], seeds: Seeds, products: list[Product],
              model: QuestionModel, start: datetime, days: int, source_id: str) -> list[dict]:
    targets = {i.object_id for i in injections}
    rows = []
    for d in range(days):
        for hour in TICK_HOURS:
            at = datetime.combine(start.date() + timedelta(days=d), time(hour), tzinfo=start.tzinfo)
            state, _ = collect_scheduled(events, at, seeds, products)
            for dec in model.propose(state).decisions:
                obj = state.objects[dec.object_id]
                # 注入外、已有 2 位以上客户升级的主题按觉的定义就是机会汇聚，只是不在注入清单里：标签不确定，不进样本
                natural = dec.family == "opportunity" and dec.object_id not in targets and obj.attrs["n_customers"] >= 2
                if dec.precondition_passed and not natural:
                    rows.append({"family": dec.family, "object_type": obj.object_type, "object_id": dec.object_id,
                                 "at": at.isoformat(), "source_id": source_id,
                                 "label": window_label(dec.family, dec.object_id, at, injections), **obj.attrs})
    return rows
