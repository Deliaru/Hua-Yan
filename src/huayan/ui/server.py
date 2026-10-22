"""演示界面后端：标准库 HTTP 服务，把门面方法一对一暴露为 JSON 接口（形式参考 JUE wp/e 的 src/jue/ui/server.py）。
权限只在门面里执行；这里只做路由、序列化与错误映射。身份由界面的下拉框传入（演示无登录）。
运行：uv run python -m huayan.ui.server（从仓库根目录）；开发时前端 `npm run dev` 经 Vite 代理 /api。
web/dist 存在时同时提供构建后的前端页面。
会话隔离：界面每个浏览器带一个会话号（请求头 X-Huayan-Session），每个会话有自己的门面与业务时钟，
多人同时试用互不干扰、互不排队；不带会话号的调用（脚本、curl）共用 default。
运行方式按会话选择：录制回放（默认），或填自己的大模型 / OneJev 接口真实运行（BYOK，见 huayan.gateway.byok）。
V9.1 试用实例（--trial <运行号>）：全部浏览器共用一个门面与固定运行目录，启动即续跑，真实时间；
每个浏览器进入时选一次身份，服务端记住，写操作的 by、读操作的 viewer 由服务端填。"""
import importlib.util
import json
import os
import re
import shutil
import time
from collections import OrderedDict
import traceback
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Lock, RLock, Thread, current_thread, local
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel
import openai
import yaml

from huayan.app import HuayanApp, _human_events
from huayan.clock import SimClock, WallClock, get_clock, set_clock
from huayan.contracts import ReqItem, SheetDraft, SHANGHAI
from huayan.knowledge import PermissionDenied
from huayan.gateway.byok import Byok, public_url
from huayan.gateway.client import ReplayMiss, StructuredOutputError
from huayan.jev.system1 import OneJevClient
from huayan.agent.hub import MODEL_ERRORS
from huayan.sim.schedule import Gate

CONFIG = os.environ.get("HUAYAN_CONFIG", "config/app.yaml")
PORT = int(os.environ.get("HUAYAN_PORT", "8766"))
DIST = Path("web/dist")
REPORTS = Path("docs/reports")
MAINLINE = Path("demo/mainline.yaml")
ROUTES = Path("demo/routes.yaml")     # v6 开场入口 A–D、C′
STORY = Path("demo/story.yaml")       # V6-5.5 演示讲解：一个上午 / 按路径看
REPORT_NAMES = ("distortion", "distortion_300", "jue_k", "week", "v6_routes")   # 评测页只读这几份报告（WP-E；v6_routes 为 V6-5 岗位对照）；300 张卡用于按「应升级」拆开；single_card 经门面按查看者读取

RESUME = None      # 命令行 --run <id> --resume：默认会话续跑该运行
TRIAL = None       # 命令行 --trial <id>：试用实例的运行号（V9.1）
TICK_SECONDS = int(os.environ.get("HUAYAN_TICK_SECONDS", "60"))   # 试用实例里觉按真实时间周期检查（扫描本身每 30 分钟一次）
MAX_SESSIONS = int(os.environ.get("HUAYAN_MAX_SESSIONS", "30"))   # 超出时淘汰最久未用的会话

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=SHANGHAI)
SESSION_ID = re.compile(r"[0-9a-f-]{8,64}")


class ThreadClock:
    """进程里只装这一只时钟：处理请求的线程换上自己会话的 SimClock，会话之间可以并发（真实模型一次调用可能几十秒）。"""
    local = local()

    def now(self):
        return self.local.clock.now()

    def advance_to(self, ts):
        self.local.clock.advance_to(ts)


THREAD_CLOCK = ThreadClock()
checkpoint_lock = Lock()                          # 载入检查点共用 runs/demo_v5/checkpoint.yaml


class Activity:
    """一次写操作的处理过程（墙钟），界面的过程面板轮询读取；只在内存里。"""

    def __init__(self, path, by=None):
        self.path, self.by, self.t0, self.events, self.ms, self.error = path, by, time.monotonic(), [], None, None

    def add(self, kind, **fields):
        self.events.append({"kind": kind, "t": round(time.monotonic() - self.t0, 2), **fields})

    def view(self, viewer):
        """别人的 Agent 只给「谁、做什么、用时」：去掉工具名（铁律 4 的裁剪在服务端做，界面不判断）。"""
        owner, events = None, []
        for e in list(self.events):
            owner = e["actor"] if e["kind"] == "agent_start" else None if e["kind"] == "agent_end" else owner
            events.append({k: v for k, v in e.items() if k != "tool"} if e["kind"] == "step" and owner != viewer else e)
        elapsed = self.ms if self.ms is not None else (time.monotonic() - self.t0) * 1000
        return {"path": self.path, "running": self.ms is None, "elapsed_ms": elapsed, "error": self.error, "events": events}


class TrialGate(Gate):
    """V9.2 试用实例的会话锁：沿用模拟器的闸口（sim/schedule.py），业务状态只由持有者改，等模型返回时让出，
    别人的读写照常进行。线程名可能重复，按线程号区分。"""

    @staticmethod
    def me():
        return f"{current_thread().name}#{current_thread().ident}"

    def __enter__(self):
        self.acquire(self.me())

    def __exit__(self, *exc):
        self.release()

    def outside(self, fn):
        if self.holder != self.me():
            return fn()
        self.release()
        try:
            return fn()
        finally:
            self.acquire(self.me())


def use_clock(clock):
    ThreadClock.local.clock = clock
    set_clock(THREAD_CLOCK)


def dump(x):
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, (list, tuple)):
        return [dump(v) for v in x]
    if isinstance(x, dict):
        return {k: dump(v) for k, v in x.items()}
    return x


def meta(app, _):
    return {"status": app.status(), "actors": list(app.actors.values()), "mainline_available": False,
            "slots": [{"id": s.id, "label": s.label} for s in app.seeds.slots],
            "phenomena": [{"id": p.id, "label": p.label} for p in app.seeds.phenomena],
            "products": [{"id": p.id, "name": p.name} for p in app.kb.products()],
            # V9.6：实际加载的觉模型与学习格，其余家族规则打分
            "jue": {"realtime": app.jue_realtime.name, "scheduled": app.jue_scheduled.name,
                    "cells": sorted({*getattr(app.jue_realtime, "models", {}), *getattr(app.jue_scheduled, "models", {})})}}


def sessions(app, _):
    return [{"id": s.id, "customer_id": s.customer_id, "sales_id": s.sales_id, "status": s.status,
             "phenomenon": s.need.phenomenon, "origin": s.origin} for s in app.sessions()]


def session(app, p):
    s = next(s for s in app.sessions() if s.id == p["id"])
    return {"view": app.view_session(p["id"], p["viewer"]), "phenomenon": s.need.phenomenon,
            "phenomenon_quote": s.need.phenomenon_quote,
            "ask_back": [q for q in app.bus.list(family="ask_back") if q.refs.get("session_id") == p["id"]],
            "ask_back_history": [q for q in app.bus.list(family="ask_back", status=None)
                                 if q.refs.get("session_id") == p["id"] and q.status != "open"]}


def report(app, p):
    name = p["name"]
    if name == "single_card":                         # 单卡明细按查看者裁剪，由门面决定（WP-E2）
        return app.single_card_report(p["viewer"])
    if name not in REPORT_NAMES:
        raise KeyError(name)
    return json.loads((REPORTS / name / "metrics.json").read_text(encoding="utf-8"))


def demo_actions():
    script = yaml.safe_load(MAINLINE.read_text(encoding="utf-8"))
    return [action for step in script["steps"] for action in step["actions"]]


def next_line(app, p):
    session = next(s for s in app.sessions() if s.id == p["session"])
    actions = demo_actions()
    # 台词按客户定位（不管是哪位业务员接待），试用者切错业务员也能取到下一句
    aliases = [a["start"]["session"] for a in actions if "start" in a and a["start"]["customer"] == session.customer_id]
    matching = [s.id for s in app.sessions() if s.customer_id == session.customer_id]
    index = matching.index(session.id)
    if index >= len(aliases):
        return {"text": None}
    lines = [a["customer"]["text"] for a in actions if "customer" in a and a["customer"]["session"] == aliases[index]]
    # 按客户已发送的轮数定位；点击只取文本，不消耗下一句，允许改写后发送。
    sent = sum(t.speaker == "customer" for t in session.turns)
    return {"text": lines[sent] if sent < len(lines) else None}


def demo_routes():
    return yaml.safe_load(ROUTES.read_text(encoding="utf-8"))["routes"]


def open_route(app, p):
    """v6 开场入口：只代客户说出预设的第一句话，之后由看的人在各工作面里真实操作（不锁步骤）。"""
    route = next(r for r in demo_routes() if r["id"] == p["route"])
    customer = p.get("customer") or route["customer"]     # D 要换一位客户再开一次
    session = app.start_session(customer)
    app.add_turn(session.id, "customer", route["lines"][0])
    return {"session_id": session.id, "customer_id": customer}


def route_next(app, p):
    """开场之后客户的下一句（只填进输入框，由人发出；可改写）。"""
    session = next(s for s in app.sessions() if s.id == p["session"])
    sent = [t.text for t in session.turns if t.speaker == "customer"]
    routes = [r for r in demo_routes() if sent == r["lines"][:len(sent)] and len(sent) < len(r["lines"])]
    routes.sort(key=lambda r: r["customer"] != session.customer_id)
    return {"text": routes[0]["lines"][len(sent)] if routes else None}


SESSION_STATUS = {"open": "进行中", "recommended": "已推荐", "escalated": "已转研发", "closed": "已记录，暂无方案"}


def demo_story():
    return yaml.safe_load(STORY.read_text(encoding="utf-8"))


def demo_ledger(app, p):
    """V6-5.5 生产力账本：按本会话此刻的事件日志计数，口径同 scripts/demo_routes.py 的 v6 列；传统按黑线流程定义（每个需求 5 个人工节点、一张研发单），不是测量。"""
    sessions = app.sessions()
    n = len(sessions)
    reqs = app.requirements("rd:R01")
    tickets = sum(r.status != "merged" for r in reqs)
    events = app.events.query()
    kinds = [e.kind for e in events]
    handed = sum(s.origin == "sales" or app.route_of(s.id, "rd:R01")["path"] == "交业务员" for s in sessions)
    return [
        {"label": "研发少收的单", "value": n - tickets, "note": f"{n} 个需求，进研发 {tickets} 张；传统每个需求一张"},
        {"label": "业务员少做的技术问答", "value": sum(s.origin == "customer" for s in sessions), "note": "客户自己来问，化言在客户这一层答"},
        {"label": "无需人转述的需求单", "value": sum(r.drafted_by == "pm:agent" for r in reqs), "note": "产品经理 Agent 起草，带着客户原话"},
        {"label": "老产品新增适用场景", "value": kinds.count("scope_extended"), "note": "研发判一次，产品经理签字写进产品边界"},
        {"label": "觉自动推进", "value": kinds.count("auto_executed"), "note": "低风险推进按模板自动执行，不占人签字"},
        {"label": "人工中转节点", "value": len(_human_events(events)) + handed, "base": n * 5,
         "note": f"传统按定义 {n} × 5 = {n * 5} 个：业务员记录、产品经理转述、研发接收、产品经理评价、业务员开单"},
    ]


GET = {
    "/api/capabilities": lambda app, p: app.capabilities(p["viewer"]),
    "/api/claims": lambda app, p: app.candidate_claims(p["req_id"], p["viewer"]),
    "/api/demo/ledger": demo_ledger,
    "/api/demo/route-next": route_next,
    "/api/demo/next": next_line,
    "/api/status": lambda app, p: app.status(),
    "/api/sessions": sessions,
    "/api/session": session,
    "/api/questions": lambda app, p: app.questions(p["viewer"]),
    "/api/requirements": lambda app, p: [{"id": r.id, "status": r.status, "phenomenon": r.phenomenon,
                                          "customer_ids": [s.customer_id for s in app.sessions() if s.id in r.session_ids]}
                                    for r in app.requirements(p["viewer"])],
    "/api/frozen": lambda app, p: {"frozen": app.kb.is_frozen(p["actor"])},
    "/api/frozen_actors": lambda app, p: app.frozen_actors(p["viewer"]),          # v8 Q9.8
    "/api/requirement": lambda app, p: app.requirement_view(p["id"], p["viewer"]),
    "/api/matched_limits": lambda app, p: app.matched_limits(p["id"], p["viewer"]),
    "/api/leak": lambda app, p: app.leak_check(p["id"], p["viewer"]),
    "/api/timeline": lambda app, p: app.jue_timeline(p["target_id"], p["viewer"]),
    "/api/route": lambda app, p: app.route_of(p["id"], p["viewer"]),   # v6：需求轨迹条
    "/api/readiness": lambda app, p: app.readiness(p["id"], p["viewer"]),   # v6.1：开工门槛
    "/api/session-readiness": lambda app, p: app.session_readiness(p["id"], p["viewer"]),   # v6.1 E1
    "/api/workload": lambda app, p: app.workload(p["viewer"]),   # v6.1 E6
    "/api/demo/routes": lambda app, p: demo_routes(),
    "/api/ledger": lambda app, p: app.ledger.totals(),
    "/api/contributions": lambda app, p: app.contributions(p["viewer"]),
    "/api/report": report,
    "/api/agents/conversation": lambda app, p: app.agents.conversation(p["actor"], p.get("session_id"), p.get("thread")),
    "/api/agents/memory": lambda app, p: app.memories(p["actor"]),           # v8：助手记忆，人能看能删
    "/api/agents/trace": lambda app, p: own_trace(app, p["conversation_id"], p.get("viewer")),
    "/api/agents/pending": lambda app, p: app.agents.pending(p["actor"]),
    "/api/agents/failures": lambda app, p: app.agents.failures_for(p["viewer"]),     # V9.2：因模型接口失败没准备成的问题
    "/api/trial/stamp": lambda app, p: {"events": len(app.events.events), "failures": len(app.agents.failures)},
}
POST = {
    "/api/agents/forget": lambda app, p: app.forget(p["id"], p["by"]),
    "/api/qi/confirm": lambda app, p: app.confirm_claims(p["req_id"], p["ku_ids"], p["by"]),
    "/api/qi/grant": lambda app, p: app.sign_qi_grant(p["question_id"], p["by"], p.get("claim_ids", ()), p.get("note", "")),
    "/api/qi/revoke": lambda app, p: app.revoke_capability(p["cap_id"], p["by"]),
    "/api/qi/request-share": lambda app, p: app.request_share(p["ku_id"], p["by"]),
    "/api/qi/withdraw": lambda app, p: app.withdraw_claim(p["ku_id"], p["by"]),
    "/api/sessions": lambda app, p: app.start_session(p["customer_id"], p.get("sales_id")),
    "/api/turn": lambda app, p: app.add_turn(*writable_turn(app, p), p["text"]),
    "/api/recommend": lambda app, p: app.recommend_now(p["session_id"]),
    "/api/resolve": lambda app, p: app.resolve(p["question_id"], p["action"], p["by"], p.get("note", "")),
    "/api/unfreeze": lambda app, p: app.unfreeze_access(p["actor_id"], p["by"]),     # v8 Q9.8
    "/api/escalate": lambda app, p: app.escalate(p["session_id"], p["by"]),
    "/api/reuse/adopt": lambda app, p: app.adopt_reuse(p["req_id"], p["by"]),
    "/api/reuse/decline": lambda app, p: app.decline_reuse(p["req_id"], p["reason"], p["by"]),
    "/api/reuse-note": lambda app, p: app.update_reuse_note(p["req_id"], p["text"], p["by"]),
    "/api/merge": lambda app, p: app.merge_requirements(p["question_id"], p["by"], p.get("note", "")),
    "/api/scope/extend": lambda app, p: app.extend_scope(p["question_id"], p["note"], p["by"]),   # v6
    "/api/contribute_l2": lambda app, p: app.contribute_l2(p["req_id"], p["item_index"], p["scene_phrase"],
                                                           p["product_term"], p["by"]),   # v6
    "/api/prepared": lambda app, p: app.mark_prepared(p["question_id"], p["by"]),   # v6 退回纠偏：修改完成，交研发
    "/api/demo/open": open_route,   # v6 开场入口
    "/api/accept": lambda app, p: app.accept_requirement(p["req_id"], p["by"]),
    "/api/decline": lambda app, p: app.decline_project(p["req_id"], p["reason"], p["by"], p.get("product_id"), p.get("claim_ids", ()),
                                                     p.get("limits", "")),   # v7
    "/api/return": lambda app, p: app.return_requirement(p["req_id"], p["reason"], p["by"]),
    "/api/req-item": lambda app, p: app.edit_req_item(p["req_id"], p["index"], ReqItem.model_validate(p["item"]), p["by"]),
    "/api/confirm": lambda app, p: app.confirm_translation(p["req_id"], p["by"]),
    "/api/contribute": lambda app, p: app.contribute_translation(p["req_id"], p["item_index"],
        p["scene_phrase"], p["chem_term"], p["by"]),
    "/api/market-eval": lambda app, p: app.record_market_eval(p["req_id"], p["result"], p["note"], p["by"],
                                                              p.get("missing_slots", ())),
    "/api/rework": lambda app, p: app.rework_requirement(p["req_id"], p["by"]),
    "/api/return_for_conditions": lambda app, p: app.return_for_conditions(p["req_id"], p["slots"], p["by"]),
    "/api/ask_before_accept": lambda app, p: app.ask_before_accept(p["req_id"], p["slots"], p["by"]),
    "/api/qi/narrow": lambda app, p: app.narrow_capability(p["cap_id"], p["conditions"], p["by"]),
    "/api/points": lambda app, p: app.set_public_points(p["req_id"], p["text"], p["sealed"], p["by"]),
    "/api/sheet": lambda app, p: app.save_sheet(p["req_id"], SheetDraft.model_validate(p["sheet"]), p["by"]),
    "/api/release": lambda app, p: app.release_product(p["req_id"], p["by"], p.get("name"), p.get("category")),
    "/api/trial": lambda app, p: app.record_requirement_trial(p["req_id"], p["result"], p["by"],
                                                              p.get("cause", "none"), p.get("missing_slots", ())),
    "/api/decrypt/request": lambda app, p: app.request_decrypt(p["session_id"], p["by"]),
    "/api/decrypt/decide": lambda app, p: app.decide_decrypt(p["question_id"], p["by"], p["approve"], p.get("text", "")),
    "/api/reply-draft": lambda app, p: app.save_reply_draft(p["session_id"], p["text"], p["by"]),
    "/api/escalate-note": lambda app, p: app.save_escalate_note(p["session_id"], p["text"], p["by"]),
    "/api/agents/chat": lambda app, p: app.agents.chat(p["actor"], p["text"], p.get("session_id"), focus=p.get("focus")),
    "/api/agents/approve": lambda app, p: app.agents.approve(p["action_id"], p["by"]),
    "/api/agents/reject": lambda app, p: app.agents.reject(p["action_id"], p["by"], p.get("note", "")),
    "/api/agents/retry": lambda app, p: app.agents.retry(p["question_id"], p["by"]),   # V9.2：整项重跑
}


class Api:
    """HTTP 与演示脚本共用入口；调用方先设置 SimClock，再构建门面。"""

    def __init__(self, app, config_path=CONFIG, clock=None, byok=None):
        self.app, self.config_path, self.byok = app, config_path, byok
        self.clock = clock or get_clock()   # 本会话的业务时钟；每次调用先在当前线程换上它
        self.lock = TrialGate() if TRIAL else RLock()
        self.writes = 0     # 本轮成功的写操作数；回放部署里按它对齐台词的下一步
        self.activity = None                # 正在进行或最近一次写操作的处理过程
        self.current = local()              # V9.2：试用实例里各人的请求并行，过程记在发起它的线程上
        self.recent = {}                    # 试用实例：每个人最近一次写操作的处理过程
        self.agent_runs = {}                # (对话 id, 回复序号) → 这一轮 Agent 的过程，供对话里展开
        self.story_done, self.story_handles = 0, {}   # V6-5.5 讲解已执行到第几步；句柄 → 会话、开场、已说几句
        self.story_last = None                        # 上一步的耗时、模型调用次数与是否偏离剧本
        self.story_mark = None                        # 下一步已开始、等看的人在工作面上操作时：开始时的模型调用计数
        if app is not None:
            self.attach(app)

    def attach(self, app):
        """把门面、网关、OneJev 的进度回调接到本会话的过程记录上。"""
        app.progress = app.gateway.trace = self.emit
        for client in (app.system1, getattr(app.system1, "onejev", None)):
            if isinstance(client, OneJevClient):
                client.trace = self.emit
        if TRIAL:      # 等模型时让出会话锁；计量在锁外写，另加一把锁免得行交错
            complete, ask = app.gateway._complete, app.system1.ask
            app.gateway._complete = lambda req, schema=None: self.lock.outside(lambda: complete(req, schema))
            app.system1.ask = lambda *a, **k: self.lock.outside(lambda: ask(*a, **k))
            if not hasattr(app.meter, "unlocked_record"):
                app.meter.unlocked_record, meter_lock = app.meter.record, Lock()

                def record(**kw):
                    with meter_lock:
                        return app.meter.unlocked_record(**kw)
                app.meter.record = record

    def emit(self, kind, **fields):
        activity = getattr(self.current, "activity", None) if TRIAL else self.activity
        if activity is None or activity.ms is not None:
            return
        activity.add(kind, **fields)
        if kind == "agent_end":
            events = activity.events
            start = max(i for i, e in enumerate(events) if e["kind"] == "agent_start" and e["conversation_id"] == fields["conversation_id"])
            self.agent_runs[(fields["conversation_id"], fields["index"])] = {
                "events": events[start:], "ms": (events[-1]["t"] - events[start]["t"]) * 1000}

    def progress(self, viewer):
        activity = self.recent.get(viewer) if TRIAL else self.activity
        return activity.view(viewer) if activity else None

    def agent_process(self, conversation_id, viewer):
        """自己的对话里每轮 Agent 回复的过程；只给对话的委托人本人。"""
        if not conversation_id.startswith(f"conv:{viewer}:"):
            raise PermissionDenied("只能查看自己 Agent 的过程")
        return {str(i): run for (c, i), run in self.agent_runs.items() if c == conversation_id}

    def checkpoints(self):
        if self.byok or Path(self.config_path).name not in ("app.demo.yaml", "app.demo.replay.yaml"):
            return []
        return [a["checkpoint"] for a in demo_actions() if "checkpoint" in a]

    def load_checkpoint(self, name):
        with checkpoint_lock:
            return self._load_checkpoint(name)

    def _load_checkpoint(self, name):
        if name not in self.checkpoints():
            raise ValueError("检查点不存在或未使用 app.demo.yaml 启动")
        spec = importlib.util.spec_from_file_location("huayan_demo_mainline", "scripts/demo_mainline.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = yaml.safe_load(Path(self.config_path).read_text(encoding="utf-8"))
        deployed_replay = bool(config.get("replay"))
        config["replay"] = True
        directory = Path(config["run_root"]) / "demo_v5"
        directory.mkdir(parents=True, exist_ok=True)
        replay_config = directory / "checkpoint.yaml"
        replay_config.write_text(yaml.safe_dump(config), encoding="utf-8")
        loaded, clock = None, SimClock(T0)
        try:
            use_clock(clock)
            loaded = HuayanApp.build(str(replay_config))
            inner = Api(loaded, str(replay_config), clock)
            module.Mainline(inner, MAINLINE).run(name)
        except Exception:
            use_clock(self.clock)
            if loaded is not None:
                loaded.system1.close()
            raise
        # 回放成功后才替换工作面，并把两个客户端一起切回服务启动时的模式（演示部署保持回放）。
        loaded.config["replay"] = loaded.gateway.replay = loaded.system1.replay = deployed_replay
        self.app.system1.close()
        self.app, self.writes, self.clock = loaded, inner.writes, inner.clock
        self.agent_runs = inner.agent_runs
        self.attach(loaded)
        return {"run_id": loaded.run_id, "checkpoint": name}

    def next_action(self):
        """回放部署：台词里下一步人要做的事（按成功写操作数对齐）；现场模式不按台词走，返回空。"""
        if not self.app.config["replay"]:
            return None
        actions = demo_actions()
        writes = [a for a in actions if "expect" not in a and "checkpoint" not in a]
        sessions = {a["start"]["session"]: a["start"] for a in actions if "start" in a}
        script = yaml.safe_load(MAINLINE.read_text(encoding="utf-8"))
        chapters = [step["title"] for step in script["steps"] for a in step["actions"] if "expect" not in a and "checkpoint" not in a]
        done = self.writes >= len(writes)
        return {"index": self.writes, "total": len(writes), "sessions": sessions,
                "action": None if done else writes[self.writes], "chapter": None if done else chapters[self.writes]}

    def call(self, method, path, params):
        with self.lock:
            use_clock(self.clock)
            return self._call(method, path, params)

    def build(self, resume=None):
        """resume：续跑已有运行（--run <id> --resume），业务时间接着最后一条事件。试用实例用真实时间，运行目录已有就续跑。"""
        if TRIAL:
            self.clock = WallClock()
            use_clock(self.clock)
            run_root = Path(yaml.safe_load(Path(self.config_path).read_text(encoding="utf-8"))["run_root"])
            self.app, self.writes = HuayanApp.build(self.config_path, run_id=TRIAL, resume=(run_root / TRIAL).exists()), 0
        else:
            self.clock = SimClock(T0)
            use_clock(self.clock)
            self.app, self.writes = HuayanApp.build(self.config_path, run_id=resume, byok=self.byok, resume=bool(resume)), 0
            if self.app.events.events:
                self.clock.advance_to(self.app.events.events[-1].ts)
        self.activity, self.agent_runs = None, {}
        self.story_done, self.story_handles, self.story_last, self.story_mark = 0, {}, None, None
        self.attach(self.app)

    def story_state(self):
        story = demo_story()
        view = self._story_view(story["steps"][self.story_done - 1]["view"]) if self.story_done else None
        begun = self.story_mark is not None
        return story | {"done": self.story_done, "view": view, "last": self.story_last,
                        "begun": begun, "guide": self._story_guide() if begun else None}

    def story_begin(self):
        """讲解的下一步分两段：先由服务端执行开场（客户来了、说出第一句），再由讲解栏引导看的人在工作面上亲手点该点的按钮
        （替客户回答追问、签字、接单）；做完（或点「替我做这一步」）由 story_next 收尾、切到讲解。没有要人做的动作时直接收尾。"""
        self.story_mark = self._model_calls()
        step = demo_story()["steps"][self.story_done]
        self._story_run([a for a in step.get("do", []) if "open" in a])
        return self.story_state() if self._story_guide() else self.story_next()

    def story_next(self):
        """讲解这一步收尾：真的执行 do 里还没做的写操作（经 _call，与浏览器里点按钮、scripts/demo_routes.py 同一个入口）。
        看的人已经在工作面上自己做过的动作（开过、发过这句、签过、接过）跳过，接着往下讲；所以失败后再点一次就是重试。"""
        step = demo_story()["steps"][self.story_done]
        mark = self.story_mark or self._model_calls()
        self._story_run(step.get("do", []))
        self.story_done += 1
        self.story_mark = None
        n, tokens, ms = (a - b for a, b in zip(self._model_calls(), mark))
        self.story_last = {"seconds": round(ms / 1000, 1), "calls": n, "tokens": tokens,
                           "diverged": self._story_diverged(step.get("expect", {}))}
        return self.story_state()

    def _story_run(self, actions):
        try:
            for action in actions:
                self._story_do(action)
        except (openai.APIError, StructuredOutputError) as e:
            raise ValueError(f"模型这一步调用失败（{type(e).__name__}: {e}）。再点一次重试，已经做完的动作会跳过。") from e
        except (PermissionDenied, ValueError, KeyError, StopIteration) as e:
            raise ValueError(f"这一步没能执行（{type(e).__name__}: {e}）。前面的走向和剧本不同（自己操作过，或真实模型判断不同），"
                             "可以在目录里点这一章，从头快进到它的开头重新看。") from e

    def story_goto(self, index):
        """从头重建，再执行到第 index 步（目录里点某一步 / 某一章）。
        接入自己的模型时每一步都真实调用、又慢又花钱，只补跑这一章和它依赖的章（如 C′ 依赖 C），其余章跳过。"""
        self.app.system1.close()
        self.build()
        story = demo_story()
        chapter = story["steps"][index - 1]["chapter"] if index else None
        needed = {chapter, *next((c.get("needs", []) for c in story["chapters"] if c["id"] == chapter), [])}
        for i in range(index):
            if self.byok and story["steps"][i]["chapter"] not in needed:
                self.story_done += 1
                continue
            self.story_next()
        return self.story_state()

    def _model_calls(self):
        """本会话到此刻的大模型调用次数、token 数与模型用时（计量文件里 kind=llm 的记录；回放时是录制下来的输出）。"""
        path = Path(self.app.meter.path)
        records = [json.loads(line) for line in path.open(encoding="utf-8")] if path.exists() else []
        llm = [r for r in records if r["kind"] == "llm"]
        return len(llm), sum(r["input_tokens"] + r["output_tokens"] for r in llm), sum(r["latency_ms"] for r in llm)

    def _story_diverged(self, expect):
        """这一步剧本预期的会话状态没出现时，如实说出真实运行跑到了哪里（真实模型的判断可能和录制时不同）。"""
        out = []
        for handle, status in expect.items():
            sid = self.story_handles.get(handle, {}).get("session")
            session = next((s for s in self.app.sessions() if s.id == sid), None)
            if session is None or session.status == status:
                continue
            asking = "、".join(h.label for h in session.hints)
            out.append(f"剧本预期这里「{SESSION_STATUS[status]}」，实际是「{SESSION_STATUS[session.status]}」"
                       + (f"：觉还在追问{asking}" if asking else ""))
        return "；".join(out) or None

    def _story_do(self, a):
        h = self.story_handles
        if "open" in a:
            if a["as"] in h:
                return
            opened = self._call("POST", "/api/demo/open", {"route": a["open"], "customer": a.get("customer")})
            h[a["as"]] = {"session": opened["session_id"], "route": a["open"], "said": 1}
        elif "say" in a:
            s = h[a["say"]]
            session = next(x for x in self.app.sessions() if x.id == s["session"])
            if sum(t.speaker == "customer" for t in session.turns) <= s["said"]:
                line = next(r for r in demo_routes() if r["id"] == s["route"])["lines"][s["said"]]
                self._call("POST", "/api/turn", {"session_id": s["session"], "speaker": "customer", "text": line})
            s["said"] += 1
        elif "decline" in a:
            req = self._story_req(a["decline"])
            if req.status == "draft":
                self._call("POST", "/api/decline", {"req_id": req.id, "by": req.assigned_rd, "product_id": a["product"], "reason": a["reason"]})
        elif "scope" in a:
            if q := self._story_question("scope_update", product_id=a["scope"]):
                self._call("POST", "/api/scope/extend", {"question_id": q.id, "by": "pm:P01", "note": a["note"]})
        elif "merge" in a:
            if q := self._story_question("opportunity"):
                self._call("POST", "/api/merge", {"question_id": q.id, "by": "pm:P01", "note": a["merge"]})
        else:
            req = self._story_req(a["accept"])
            if req.status == "draft":
                self._call("POST", "/api/accept", {"req_id": req.id, "by": req.assigned_rd})

    def _story_guide(self):
        """这一步还没做的第一个人工动作：谁来做（who）、点哪个按钮（target）、「演示自动填入」填什么（arg）、在哪个工作面（view）。
        都做完了返回 None。只读，不推进；前提没出现（真实模型走向不同）时 view 为空，由「替我做这一步」报出原因。"""
        said = {}
        for a in demo_story()["steps"][self.story_done].get("do", []):
            try:
                if "say" in a:
                    s = self.story_handles[a["say"]]
                    k = s["said"] + said.get(a["say"], 0)
                    said[a["say"]] = said.get(a["say"], 0) + 1
                    session = next(x for x in self.app.sessions() if x.id == s["session"])
                    if sum(t.speaker == "customer" for t in session.turns) > k:
                        continue
                    line = next(r for r in demo_routes() if r["id"] == s["route"])["lines"][k]
                    return {"target": a.get("press", "say"), "who": session.customer_id, "arg": line,
                            "view": {"page": "customer", "focus": session.id, "who": session.customer_id}}
                if "decline" in a or "accept" in a:
                    req = self._story_req(a.get("decline") or a["accept"])
                    if req.status != "draft":
                        continue
                    arg = json.dumps({"product": a["product"], "reason": a["reason"]}, ensure_ascii=False) if "decline" in a else None
                    return {"target": "decline" if "decline" in a else "sign:accept_requirement", "who": req.assigned_rd, "arg": arg,
                            "view": {"page": "rd", "focus": req.id, "who": req.assigned_rd}}
                if "scope" in a or "merge" in a:
                    family = "scope_update" if "scope" in a else "opportunity"
                    q = next((q for q in reversed(self.app.bus.list(status=None, family=family))
                              if "merge" in a or q.refs.get("product_id") == a["scope"]), None)
                    if q is not None and q.status != "open":
                        continue
                    focus = (q.refs.get("requirement_id") or q.refs.get("requirement_ids", "").split(",")[0]) if q else None
                    return {"target": "scope" if "scope" in a else "merge", "who": "pm:P01", "arg": a.get("note") or a["merge"],
                            "view": {"page": "pm", "focus": focus, "who": "pm:P01"}}
            except (KeyError, StopIteration):
                return {"target": next(iter(a)), "who": None, "arg": None, "view": None}
        return None

    def _story_req(self, handle):
        sid = self.story_handles[handle]["session"]
        return next(r for r in self.app.requirements("rd:R01") if sid in r.session_ids and r.status != "merged")

    def _story_question(self, family, **refs):
        """待产品经理签的问题；已经签过（不再 open）返回 None 跳过，Agent 还没准备好则报错，再点一次重试。"""
        self.app.tick()
        q = next((q for q in self.app.questions("pm:P01") if q.family == family and q.status == "open"
                  and all(q.refs.get(k) == v for k, v in refs.items())), None)
        if q is not None and q.prepared_at is None:
            raise ValueError("产品经理 Agent 还没准备好这一项")
        return q

    def _story_view(self, v):
        """执行后切到哪个工作面看哪个对象：研发页的身份取需求单的指派研发，客户页取会话的客户；看的人自己操作过、对象对不上时只切页面。"""
        try:
            if v.get("focus", "").startswith("req:"):
                req = self._story_req(v["focus"][4:])
                return {"page": v["page"], "focus": req.id, "who": v.get("who") or req.assigned_rd}
            if v.get("focus"):
                sid = self.story_handles[v["focus"]]["session"]
                return {"page": v["page"], "focus": sid, "who": v.get("who") or next(s.customer_id for s in self.app.sessions() if s.id == sid)}
        except (KeyError, StopIteration):
            pass
        return {"page": v["page"], "focus": None, "who": v.get("who")}

    def _call(self, method, path, params):
        if TRIAL and (path in TRIAL_BLOCKED or path.startswith("/api/demo/")):
            if method == "GET":
                return [] if path == "/api/demo/checkpoints" else None
            raise ValueError("试用实例是大家共用的一份业务，不能重置或走演示讲解")
        if method == "GET" and path == "/api/demo/checkpoints":
            return self.checkpoints()
        if method == "GET" and path == "/api/demo/next-action":
            return self.next_action()
        if method == "POST" and path == "/api/demo/load":
            return self.load_checkpoint(params["name"])
        if method == "POST" and path == "/api/reset":
            self.app.system1.close()
            self.build()
            return {"run_id": self.app.run_id}
        if method == "GET" and path == "/api/demo/story":
            return self.story_state()
        if method == "POST" and path == "/api/demo/story/begin":
            return self.story_begin()
        if method == "POST" and path == "/api/demo/story/next":
            return self.story_next()
        if method == "POST" and path == "/api/demo/story/goto":
            return self.story_goto(int(params["index"]))
        if method == "GET" and path == "/api/meta":
            return meta(self.app, params) | {"mode": self.mode()}
        route = {"GET": GET, "POST": POST}[method][path]
        if method == "GET":
            return route(self.app, params)
        before = self.clock.now()
        if not TRIAL:                   # 试用实例是真实时间，不推进
            self.clock.advance_to(before + timedelta(minutes=1))
        activity = self.activity = self.current.activity = Activity(path, params.get("by"))
        if activity.by:
            self.recent[activity.by] = activity
        try:
            try:
                result = route(self.app, params)
            except (PermissionDenied, ValueError, KeyError, StopIteration):
                # 被门面拒绝的写操作不占业务时间：误点不会让回放台词的时刻错位
                if not TRIAL:
                    self.clock = SimClock(before)
                    use_clock(self.clock)
                raise
            if TRIAL:
                WAKE.set()          # 觉提出的问题交给后台准备，不让这次写操作等 Agent
            else:
                self.app.tick()
        except Exception as e:
            activity.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            activity.ms = (time.monotonic() - activity.t0) * 1000
        self.writes += 1
        return result

    def switch_models(self, changes):
        """V9.1：试用中换模型配置，只重接网关与 Jev，门面与业务原样保留。配置文件只取仓库 config/ 与 data/ 下已有的。"""
        for key in ("models_config", "system1_config"):
            if key in changes:
                path = Path(changes[key])
                if path.suffix != ".yaml" or not path.is_file() or not path.resolve().is_relative_to(Path.cwd()) \
                        or path.resolve().relative_to(Path.cwd()).parts[0] not in ("config", "data"):
                    raise ValueError(f"{key} 要是 config/ 或 data/ 下已有的 yaml 文件")
        with self.lock:
            use_clock(self.clock)
            status = self.app.switch_models(**changes)
            self.attach(self.app)
            return {"status": status, "mode": self.mode()}

    def tick(self):
        """试用实例的后台周期：觉按真实时间检查到点的扫描，并派发待准备的问题。"""
        with self.lock:
            use_clock(self.clock)
            self.current.activity = Activity("/tick", "jue")
            try:
                self.app.tick()
            finally:
                self.current.activity.ms = (time.monotonic() - self.current.activity.t0) * 1000

    def mode(self):
        """本会话的运行方式与所用模型名（不含密钥）。"""
        b, config = self.byok, self.app.config
        llm = None if config["gateway_mock"] else self.app.gateway.tiers["fast"]["model"]
        jev = (b.jev_model if b.jev_base_url else None) if b else self.app.system1.model if config["system1_impl"] == "onejev" else None
        return {"kind": "replay" if config["replay"] else "byok" if b else "local", "llm_model": llm, "jev_model": jev,
                "jev_fallback": bool(b and b.jev_base_url and b.jev_fallback)}


TRIAL_BLOCKED = {"/api/reset", "/api/mode"}
trial_roles: dict[str, str] = {}      # 浏览器会话号 → 身份；存在运行目录的 roles.json，重启后不用重选
trial_lock = Lock()


def _roles_path():
    return session_api("default").app.run_dir / "roles.json"


def load_trial_roles():
    path = _roles_path()
    trial_roles.update(json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})


def set_trial_role(sid, p):
    """进入试用时选身份（人，不含 Agent）；actor 为空表示退出、重选。"""
    if not SESSION_ID.fullmatch(sid):
        raise ValueError("会话号格式不对")
    actor = p.get("actor")
    app = session_api(sid).app
    if actor is not None and (actor not in app.actors or actor == "pm:agent"):
        raise ValueError("没有这个身份")
    with trial_lock:
        if actor is None:
            trial_roles.pop(sid, None)
        else:
            trial_roles[sid] = actor
        _roles_path().write_text(json.dumps(trial_roles, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"actor": actor}


SPEAKERS = {"customer": {"customer"}, "sales": {"customer", "sales"}}

def writable_turn(app, p):
    """V9.6a：试用里（by 由服务端认定）只有会话的客户本人或负责它的业务员能在会话里说话。"""
    if "by" in p:
        session = next((s for s in app.sessions() if s.id == p["session_id"]), None)
        if session is None or p["by"] not in (session.customer_id, session.sales_id):
            raise PermissionDenied("只能在自己参与的会话里说话")
    return p["session_id"], p["speaker"]


def own_trace(app, conversation_id, viewer):
    """V9.6a：助手轨迹的工具结果里有委托人这一层的知识原文，只给对话的委托人本人。"""
    if not viewer or not conversation_id.startswith(f"conv:{viewer}:"):
        raise PermissionDenied("只能查看自己 Agent 的轨迹")
    return app.agents.trace(conversation_id)   # 业务员可以替客户录入原话


def trial_params(sid, method, path, params):
    """试用实例：主体由服务端认定。读写都用本会话选定的身份，覆盖请求里带的 viewer / by / actor；权限照旧由门面执行。"""
    role = trial_roles.get(sid)
    if role is None:
        if method == "GET" and path in ("/api/meta", "/api/status"):
            return params
        raise PermissionDenied("请先选择你在试用中的身份")
    params = params | {"viewer": role, "by": role}
    if path.startswith("/api/agents/"):
        params["actor"] = role
    kind = role.split(":")[0]
    if method == "POST" and path == "/api/sessions":
        if kind == "customer":
            params["customer_id"] = role
        elif kind == "sales":
            params["sales_id"] = role
        else:
            raise PermissionDenied("客户会话由客户或业务员发起")
    if method == "POST" and path == "/api/turn" and params.get("speaker") not in SPEAKERS.get(kind, set()):
        raise PermissionDenied("只有客户本人或业务员能在客户会话里说话")
    return params


WAKE = Event()       # 写操作或重跑之后叫醒后台，不用等满一个周期


def trial_ticker():
    while True:
        WAKE.wait(TICK_SECONDS)
        WAKE.clear()
        try:
            session_api("default").tick()
        except Exception:
            traceback.print_exc()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _api(self, method, params):
        url = urlparse(self.path)
        params |= {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            sid = self.headers.get("X-Huayan-Session", "default")
            if TRIAL and url.path not in MONTH and not url.path.startswith("/api/trial/"):
                params = trial_params(sid, method, url.path, params)
            if TRIAL and url.path == "/api/trial/stamp":         # 界面轮询有没有别人的变化，不排会话锁
                result = GET[url.path](session_api(sid).app, params)
            elif TRIAL and url.path == "/api/trial/role":
                result = set_trial_role(sid, params)
            elif TRIAL and url.path == "/api/trial/models":
                result = session_api(sid).switch_models(params)
            # 过程面板的两个读接口不排会话锁：会话锁正被那次耗时的写操作占着
            elif url.path == "/api/mode":
                result = set_mode(sid, params)
            elif url.path == "/api/progress":
                result = session_api(sid).progress(params["viewer"])
            elif url.path in MONTH:                   # 业务月的运行不属于任何浏览器会话
                result = MONTH[url.path](params)
            elif url.path == "/api/agents/process":
                result = session_api(sid).agent_process(params["conversation_id"], params["viewer"])
            else:
                result = session_api(sid).call(method, url.path, params)
                if TRIAL and url.path == "/api/agents/retry":
                    WAKE.set()
            if TRIAL and url.path == "/api/meta":
                result = dump(result) | {"trial": {"actor": trial_roles.get(sid)}}
            status, body = 200, dump(result)
        except PermissionDenied as e:
            status, body = 403, {"error": str(e)}
        except ReplayMiss:
            status, body = 409, {"error": "当前是录制回放，只能沿演示讲解一步步走（这一步不在录制里）。想自由操作，"
                                          "点右上角「接入真实模型」用你自己的模型真实运行；进度乱了可以在讲解目录里点某一章重看。"}
        except MODEL_ERRORS as e:
            status, body = 503, {"error": f"模型接口暂时不可用（{type(e).__name__}: {str(e)[:200]}）。已提交的内容都在，恢复后再点一次就是重跑。"}
        except AssertionError as e:
            status, body = 409, {"error": str(e)}
        except ValueError as e:
            status, body = 400, {"error": str(e)}
        except (KeyError, StopIteration) as e:
            status, body = 404, {"error": f"不存在：{e}"}
        except Exception as e:                          # 模型服务、网络等意外错误原样报给界面，不断开连接
            traceback.print_exc()
            status, body = 500, {"error": f"服务出错：{type(e).__name__}: {e}"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._api("GET", {})
        elif self.path.startswith("/reports/"):                # 评测页的图：docs/reports/<报告>/<图>.png
            _, _, name, file = self.path.split("?")[0].split("/", 3)
            path = REPORTS / name / file
            if name not in REPORT_NAMES or "/" in file or path.suffix != ".png" or not path.exists():
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self._api("POST", json.loads(self.rfile.read(length) or b"{}"))


# v8 Q9.5：模拟业务月（scripts/run_month.py）的运行状态与主管时间线。正在跑的运行由另一个进程写，
# 这里复制一份快照（截掉写了一半的行）再读回门面，不碰原运行目录；事件有变化时至多每 3 秒重建一次。
MONTH_RUNS, MONTH_VIEWS = Path("data/enterprise/runs"), Path("data/enterprise/views")
MONTH_RUN = re.compile(r"month-[\w-]+")
month_views: dict = {}
month_lock = Lock()


def month_runs(p):
    runs = [{"run_id": d.name, **json.loads((d / "progress.json").read_text(encoding="utf-8"))}
            for d in MONTH_RUNS.glob("month-*") if (d / "progress.json").exists()]
    return sorted(runs, key=lambda r: r["updated"], reverse=True)


def _month_dir(run):
    if not MONTH_RUN.fullmatch(run) or not (MONTH_RUNS / run / "progress.json").exists():
        raise KeyError(run)
    return MONTH_RUNS / run


def month_app(run):
    src = _month_dir(run)
    stamp = (src / "events.jsonl").stat().st_mtime_ns
    with month_lock:
        cached = month_views.get(run)
        if cached and (cached[0] == stamp or time.monotonic() - cached[2] < 3):
            return cached[1]
        root = MONTH_VIEWS / run
        shutil.rmtree(root, ignore_errors=True)
        shutil.copytree(src, root / run, ignore=shutil.ignore_patterns(
            "jue_samples.jsonl", "metering.jsonl", "agent_trace.jsonl", "conversations"),
            copy_function=lambda a, b: Path(b).write_bytes(Path(a).read_bytes()))   # Windows 上系统复制会锁住正在追加的源文件
        for f in (root / run).glob("*.jsonl"):
            text = f.read_text(encoding="utf-8")
            f.write_text(text[:text.rfind("\n") + 1], encoding="utf-8")
        config = yaml.safe_load(Path(f"data/enterprise/app.{run}.yaml").read_text(encoding="utf-8"))
        config.update(run_root=str(root), gateway_mock=True, replay=True, llm_cache_dir=None)
        (root / "app.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
        use_clock(SimClock(datetime.now(SHANGHAI)))
        app = HuayanApp.build(str(root / "app.yaml"), run, resume=True)
        month_views[run] = (stamp, app, time.monotonic())
        return app


def month_timeline(p):
    app = month_app(p["run"])
    use_clock(SimClock(datetime.now(SHANGHAI)))
    return app.timeline(p["day"], p["viewer"])


MONTH = {
    "/api/month/runs": month_runs,
    "/api/month/progress": lambda p: json.loads((_month_dir(p["run"]) / "progress.json").read_text(encoding="utf-8")),
    "/api/month/timeline": month_timeline,
}


apis: OrderedDict[str, Api] = OrderedDict()
apis_lock = Lock()


def session_api(sid, byok=None, rebuild=False):
    if sid != "default" and not SESSION_ID.fullmatch(sid):
        raise ValueError("会话号格式不对")
    if TRIAL:
        sid = "default"            # 试用实例：所有浏览器共用一个门面，身份另记在 trial_roles
    with apis_lock:
        if sid not in apis or rebuild:
            api = Api(None, CONFIG, byok=byok)
            api.build(RESUME if sid == "default" and not rebuild else None)
            if sid in apis:
                apis[sid].app.system1.close()
            apis[sid] = api
            if len(apis) > MAX_SESSIONS:
                _, old = apis.popitem(last=False)
                old.app.system1.close()
        apis.move_to_end(sid)
        return apis[sid]


def set_mode(sid, p):
    """切换本会话的运行方式：replay = 录制回放；byok = 用试用者填的大模型与（可选）OneJev 真实运行。切换后从头开始。"""
    if TRIAL:
        raise ValueError("试用实例的模型由项目方在服务端切换（/api/trial/models），业务原样保留")
    if p["mode"] == "replay":
        return session_api(sid, rebuild=True).mode()
    jev = (p.get("jev_base_url") or "").strip()
    byok = Byok(public_url(p["llm_base_url"].strip()), p["llm_model"].strip(), p["llm_key"].strip(),
                public_url(jev) if jev else None, (p.get("jev_model") or "OneJev-9B").strip(),
                (p.get("jev_key") or "").strip() or None, bool(p.get("jev_fallback", True)))
    if not (byok.llm_model and byok.llm_key):
        raise ValueError("请填写大模型的模型名和密钥")
    probe = byok.check()
    return session_api(sid, byok, rebuild=True).mode() | {"probe": probe}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="运行目录名（runs/ 下）；与 --resume 一起用")
    ap.add_argument("--resume", action="store_true", help="在 --run 指定的运行上续跑：默认会话读回事件、问题、知识与需求单")
    ap.add_argument("--trial", help="试用实例的运行号：全部浏览器共用一份业务，运行目录已有就续跑（V9.1）")
    ap.add_argument("--config", help="应用配置（默认 HUAYAN_CONFIG 或 config/app.yaml）")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址；试用时让同一网络里的人访问可设 0.0.0.0")
    args = ap.parse_args()
    if args.resume != bool(args.run):
        ap.error("--run 与 --resume 要一起给")
    if args.trial and args.run:
        ap.error("--trial 自带续跑，不和 --run 一起用")
    if args.trial and not re.fullmatch(r"[\w-]+", args.trial):
        ap.error("--trial 运行号只用字母、数字、下划线和短横线")
    CONFIG = args.config or CONFIG
    RESUME, TRIAL = args.run, args.trial
    session_api("default")   # 先构建一次：Jue-K 模型等首次加载较慢
    if TRIAL:
        load_trial_roles()
        Thread(target=trial_ticker, daemon=True).start()
        app = session_api("default").app
        print(f"化言试用实例：http://{args.host}:{PORT}（运行 {app.run_dir}，{len(app.sessions())} 个会话、"
              f"{len(app._requirements)} 张需求单，已登记身份 {len(trial_roles)} 个）")
    else:
        print(f"化言界面后端：http://{args.host}:{PORT}（每个浏览器一个会话，最多 {MAX_SESSIONS} 个）")
    ThreadingHTTPServer((args.host, PORT), Handler).serve_forever()
