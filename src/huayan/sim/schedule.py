"""REPLAN-v8 Q9.3：模拟日的并发（只供 sim/）。业务状态只由持有闸口的线程改，等模型返回时让出闸口；
录制时记下闸口依次让给了谁，重放按同一顺序让——问题编号、提示词与录制逐字一致，缓存全部命中。
每段会话有自己的业务时间（线程内时钟）；各段之间互不等待，像真实企业里同时进行的通话。"""
import threading
from collections import Counter
from datetime import datetime

from huayan.clock import SimClock


class Gate:
    def __init__(self, order: list[str] | None = None):
        self._cond = threading.Condition()
        self.holder: str | None = None
        self.replay = order is not None
        self.order = list(order or [])
        self._pos = 0

    def _ready(self, name: str) -> bool:
        return self.holder is None and (not self.replay or (self._pos < len(self.order) and self.order[self._pos] == name))

    def acquire(self, name: str) -> None:
        with self._cond:
            if not self._cond.wait_for(lambda: self._ready(name), timeout=900):
                raise RuntimeError(f"重放调度与录制不一致：{name} 等不到闸口（第 {self._pos} 次）")
            self.holder = name
            if self.replay:
                self._pos += 1
            else:
                self.order.append(name)

    def release(self) -> None:
        with self._cond:
            self.holder = None
            self._cond.notify_all()

    def outside(self, fn):
        """在闸口外等模型；不是闸口持有者（主线程单独跑时）就直接调用。"""
        name = threading.current_thread().name
        if self.holder != name:
            return fn()
        self.release()
        try:
            return fn()
        finally:
            self.acquire(name)

    def run(self, jobs: list[tuple[str, object]]) -> None:
        """同时跑一批工作；名字必须唯一（录制与重放靠名字对上顺序）。任何一个出错就在主线程抛出。"""
        errors = []

        def work(fn):
            self.acquire(threading.current_thread().name)
            try:
                fn()
            except BaseException as exc:          # noqa: BLE001 —— 交给主线程抛出
                errors.append(exc)
            finally:
                self.release()

        threads = [threading.Thread(target=work, args=(fn,), name=name) for name, fn in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if errors:
            raise errors[0]


def gate_gateway(gateway, gate: Gate, limit: int | None = None, timeout_s: float | None = None) -> None:
    """把网关的一次调用（含读缓存）放到闸口外：录制与重放在同样的位置让出闸口。闸口外写计量与轨迹另加锁，免得行交错。
    v8 Q9.4：limit 限制同时在途的模型调用数；timeout_s 改写请求的超时（慢请求超时后由网关重试），也进缓存键。"""
    inner, lock, keys = gateway._complete, threading.Lock(), {}
    slots = threading.Semaphore(limit) if limit else None
    gateway.stats = stats = Counter()                       # 进度条用：调用数、失败、token、在途与峰值

    def counted(req, schema):
        with lock:
            stats["inflight"] += 1
            stats["peak"] = max(stats["peak"], stats["inflight"])
        try:
            return inner(req, schema)
        finally:
            with lock:
                stats["inflight"] -= 1

    def once(req, schema):
        if timeout_s:
            req = req.model_copy(update={"timeout_s": timeout_s})
        # 相同请求同一时刻只让一个线程调用模型，后来的等它写好缓存再读；否则两次调用各得一个回答、缓存只留一个，重放会分叉
        with lock:
            key = keys.setdefault(req.model_dump_json() + repr(schema), threading.Lock())
        with key:
            if slots is None:
                return counted(req, schema)
            with slots:
                return counted(req, schema)
    gateway._complete = lambda req, schema=None: gate.outside(lambda: once(req, schema))

    def locked(write):
        def run(*args, **kwargs):
            with lock:
                if kwargs.get("kind") == "llm":
                    stats["calls" if kwargs.get("ok", True) else "failed"] += 1
                    stats["input_tokens"] += kwargs.get("input_tokens") or 0
                    stats["output_tokens"] += kwargs.get("output_tokens") or 0
                return write(*args, **kwargs)
        return run
    gateway.meter.record = locked(gateway.meter.record)    # 与觉、Jev 共用同一个计量对象
    if gateway.trace is not None:
        gateway.trace = locked(gateway.trace)


class ThreadClock(SimClock):
    """主线程推进的业务时间；工作线程可以设自己的时间（一段会话发生在它自己的时刻）。"""

    def __init__(self, start: datetime):
        super().__init__(start)
        self._local = threading.local()

    def now(self) -> datetime:
        return getattr(self._local, "now", None) or super().now()

    def local(self, ts: datetime) -> None:
        self._local.now = ts
