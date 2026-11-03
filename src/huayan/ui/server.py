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
from collections import OrderedDict, defaultdict
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
from huayan.eval import old_flow, rag_baseline
from huayan.sim import director
from huayan.ingest.reader import library

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
PLAY = None        # 命令行 --play <id>：游戏模式（V11.5）。沿用试用实例的共享门面与角色会话，时钟换成可控的 SimClock
DIRECTOR = None    # 游戏模式的导演（sim/director.py）；每局一个运行目录 <id>-r<局号>
PLAY_TICK = 3      # 游戏模式后台每几秒看一眼：推进时钟、觉检查、导演代办
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
            "slots": [{"id": s.id, "label": s.label, "values": s.values} for s in app.seeds.slots],
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


def old_flow_of(app, p):
    """V11.2：这件事按旧流程走会怎样（推算）。界面只拿实际路径去推算，不读需求卡；参数每次重读，改了即生效。"""
    route = app.route_of(p["id"], p["viewer"])
    rid = route["requirement_id"]
    cases = len(app._requirements[rid].session_ids) if rid else 1
    return old_flow.estimate(route, old_flow.load_params(), cases, story=app.case_story(p["id"], p["viewer"])["story"])


def time_bar_of(app, p):
    """V11.4：我的时间构成从现状到这一局（推算）。业务员算自己客户的会话，研发算指派给自己的单，产品经理算全部会话；
    每段会话按一件事推算（合并成课题的各自算一次）。"""
    viewer, role = p["viewer"], p["viewer"].split(":")[0]
    mine = {"sales": lambda s: s.sales_id == viewer, "pm": lambda s: True,
            "rd": lambda s: any(s.id in r.session_ids and r.assigned_rd == viewer for r in app._requirements.values())}[role]
    params = old_flow.load_params()
    estimates = [old_flow.estimate(app.route_of(s.id, viewer), params, story=app.case_story(s.id, viewer)["story"])
                 for s in app.sessions() if mine(s)]
    return old_flow.time_bar(estimates, params, role)


def live_of(app, p):
    """V12.8 组织运行实况（主管只读）：这一局每件事的前情（带主体，界面分到觉 / Jev / 契 / Agent / 人几条泳道），
    同一现象的几件事排在一起；每件事附旧流程要经过、这一次没有让人经手的岗位（推算）。"""
    viewer, params = p["viewer"], old_flow.load_params()
    sessions = {s.id: s for s in app.sessions()}
    cases = []
    for c in app.pipeline(viewer):
        s = sessions[c["session_id"]]
        route, story = app.route_of(s.id, viewer), app.case_story(s.id, viewer)
        est = old_flow.estimate(route, params, story=story["story"])
        cases.append({"session_id": s.id, "requirement_id": story["requirement_id"], "customer_id": s.customer_id,
                      "phenomenon": s.need.phenomenon, "path": route["path"], "story": story["story"], "waiting": story["waiting"],
                      "old_roles": est["old"]["roles"], "now_roles": est["now"]["roles"]})
    return {"cases": cases}


SPOTLIGHT = {"query": "", "doc_id": None}   # V12.9 四屏并排：几个窗口（各自的身份）一起看的同一句话、同一份报告；只是画面状态


def rag_baseline_of(app, p):
    """V12.9 普通 RAG 对照（eval/rag_baseline）真跑一次；右边是化言这一局里同一句话的实际经过。普通 RAG 的检索不分层，
    回答里可能带出内部资料，所以只给研发看。"""
    app._actor(p["viewer"], {"rd"})
    said = [s for s in app.sessions() if any(t.speaker == "customer" and t.text == p["question"] for t in s.turns)]
    huayan = None
    if said:
        route, story = app.route_of(said[-1].id, p["viewer"]), app.case_story(said[-1].id, p["viewer"])
        huayan = {"path": route["path"], "story": story["story"]}
    return {"rag": rag_baseline.answer(app.kb.sources, p["question"], app.gateway), "huayan": huayan}


def ceo_of(app, p):
    """V11.8 CEO 面（CEO-VIEW C1/C3）：化言线逐件路径（门面 pipeline），配上同一件事的旧流程推算与客户等第一个答复的时间，
    一份按参数文件、一份按最保守参数；三个岗位的时间构成也是两份。这一局研发新签的适用能力（有授予事件）替研发答了的事，
    旧流程里这份判断没有沉淀，下一单还要经转述找研发，按「研发不立项」的路径推算。账本、排队与来单量在界面按参数算。"""
    viewer = p["viewer"]
    cases = app.pipeline(viewer)
    granted = {e.payload["id"] for e in app.events.query(["capability_granted"])}
    params = old_flow.load_params()
    sets = {"given": params, "safe": old_flow.conservative(params)}
    for c in cases:
        route = app.route_of(c["session_id"], viewer)
        reused = route["path"] == "自助解决" and bool(granted & set(c["used"]))
        story = app.case_story(c["session_id"], viewer)["story"]
        c |= {"path": route["path"], "quote": route["quote"], "reused": reused}
        for k, ps in sets.items():
            est = old_flow.estimate({**route, "path": "研发不立项"} if reused else route, ps, story=story)
            c[k] = est | {"first_reply_hours": round(old_flow.first_reply_hours(est, ps), 2)}
    products = {x.id: x.name for x in app.kb.products()}
    phenomena = {x.id: x.label for x in app.seeds.phenomena}
    used = {u for c in cases for u in c["used"]}
    caps = [{"id": x.id, "product": products[x.payload["product_id"]], "phenomenon": phenomena[x.payload["phenomenon"]],
             "granted_by": app.actors[x.granted_by].name, "new": x.id in granted}
            for x in app.kb.capabilities() if x.id in used]
    # V12.10 组织变化热力图的「化言新增的人工」：业务员、产品经理、研发本人的签字与专业判断（含契的确认与授予）
    signs = defaultdict(int)
    for e in _human_events(app.events.query()) + [e for e in app.events.query(["claim_confirmed", "capability_granted"])
                                                   if e.actor.split(":")[0] in ("sales", "pm", "rd")]:
        signs[e.actor.split(":")[0]] += 1
    return {"cases": cases, "caps": caps, "params": sets, "names": {a.id: a.name for a in app.seeds.actors},
            "bars": {k: {role: old_flow.time_bar([c[k] for c in cases], ps, role) for role in ("sales", "pm", "rd")}
                     for k, ps in sets.items()},
            "signs": signs, "ai": _llm_usage(app.run_dir / "metering.jsonl"),
            "compile": _llm_usage(Path(app.config["trial_coverage"]) / "metering.jsonl") if app.config.get("trial_coverage") else None}


def _llm_usage(meter):
    """V12.10 网关计量里的大模型调用：按 caller 前缀汇总调用次数与 token；费用在界面按参数单价折算。"""
    out = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    for line in meter.read_text(encoding="utf-8").splitlines() if meter.exists() else []:
        r = json.loads(line)
        if r["kind"] == "llm":
            row = out[r["caller"].split(":")[0]]
            row["calls"] += 1
            row["input_tokens"] += r["input_tokens"]
            row["output_tokens"] += r["output_tokens"]
    return dict(out)


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
    "/api/source-preparation/replies": lambda app, p: app.authorized_source_replies(p["session_id"], p["viewer"]),
    "/api/source-preparation/status": lambda app, p: app.source_preparation_status(p["req_id"], p["viewer"]),
    "/api/source-preparation": lambda app, p: app.source_preparation(p["req_id"], p["viewer"]),
    "/api/sources/read": lambda app, p: app.read_source(p["doc_id"], p["viewer"], p.get("span")),
    "/api/sources/trial": lambda app, p: app.read_trial_record(p["doc_id"], p["viewer"]),
    "/api/sources/image": lambda app, p: app.read_source_image(p["doc_id"], int(p["page"]), p["viewer"], p.get("span")),
    "/api/sources/search": lambda app, p: app.search_sources(p["query"], p["viewer"], int(p.get("k", 5)), p.get("req_id")),   # V12.3
    "/api/plan": lambda app, p: app.plan_draft(p["req_id"], p["viewer"]),                                                   # V12.5
    "/api/capabilities": lambda app, p: app.capabilities(p["viewer"]),
    "/api/claims": lambda app, p: app.candidate_claims(p.get("req_id"), p["viewer"]),
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
    "/api/case-story": lambda app, p: app.case_story(p["id"], p["viewer"]),   # V11.1：一件事的前情
    "/api/client/messages": lambda app, p: app.client_messages(p["viewer"]),   # V12.6 Client-View 主动消息
    "/api/sheet-revision": lambda app, p: app.sheet_revision(p["question_id"], p["viewer"]),   # V12.7 说明书补充稿
    "/api/live": live_of,   # V12.8 组织运行实况
    "/api/qi/reports": lambda app, p: app.report_list(p["viewer"]),   # V12.9 契画布
    "/api/qi/report-life": lambda app, p: app.report_life(p["doc_id"], p["viewer"]),
    "/api/qi/capability-view": lambda app, p: app.capability_view(p["doc_id"], p["viewer"]),   # V12.9 四屏的能力层
    "/api/spotlight": lambda app, p: SPOTLIGHT,
    "/api/supervisor/exceptions": lambda app, p: app.exceptions_board(p["viewer"]),   # V12.11 研发负责人：风险与例外
    "/api/supervisor/lineage": lambda app, p: app.capability_lineage(p["viewer"]),     # V12.11 研发负责人：能力谱系
    "/api/qi/coverage-map": lambda app, p: app.coverage_map(p["viewer"]),   # V12.11 跨文档覆盖图（答辩备用）
    "/api/harness": lambda app, p: app.harness_counts(p["viewer"]),   # V12.11 活的架构图
    "/api/qi/aliases": lambda app, p: app.alias_candidates(p["viewer"]),   # V12.9 动态别名
    "/api/jue/radar": lambda app, p: app.jue_radar(p["viewer"]),   # V12.8 觉雷达与觉在学习
    "/api/jue/catalog": lambda app, p: app.decision_catalog(p["viewer"]),   # V12.8 决策目录墙
    "/api/bus": lambda app, p: app.question_board(p["viewer"]),   # V12.8 问题总线
    "/api/bus/life": lambda app, p: app.question_life(p["question_id"], p["viewer"]),
    "/api/old-flow": old_flow_of,   # V11.2：同一件事按旧流程走的推算
    "/api/time-bar": time_bar_of,   # V11.4：我的时间构成从现状到这一局
    "/api/ceo": ceo_of,   # V11.8：CEO 面的两条流水线与账本（主管只读）
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
    "/api/trial/stamp": lambda app, p: {"events": len(app.events.events), "failures": len(app.agents.failures),
                                       "sessions": len(app._sessions)},   # 开新会话不记事件，单独数
}
POST = {
    "/api/baseline/rag": rag_baseline_of,   # V12.9 普通 RAG 对照
    "/api/spotlight": lambda app, p: SPOTLIGHT.update({k: p[k] for k in ("query", "doc_id") if k in p}) or SPOTLIGHT,
    "/api/qi/alias": lambda app, p: app.confirm_alias(p["text"], p["slot"], p["value"], p["by"]),
    "/api/plan/adopt": lambda app, p: app.adopt_plan(p["req_id"], p["by"]),
    "/api/sources/ask-image": lambda app, p: app.ask_source_image(p["doc_id"], int(p["page"]), p["question"], p["by"]),
    "/api/source-preparation/compile": lambda app, p: app.compile_source_preparation(p["req_id"], p["doc_id"], p["by"]),
    "/api/source-preparation": lambda app, p: app.save_source_preparation(
        p["req_id"], p["evidence"], p.get("claim_ids", []), p.get("pending", ""), p["by"]),
    "/api/agents/forget": lambda app, p: app.forget(p["id"], p["by"]),
    "/api/qi/review": lambda app, p: app.review_claims(p["ku_ids"], p["by"]),
    "/api/qi/revise": lambda app, p: app.revise_claim(p["ku_id"], p["text"], p["by"]),
    "/api/qi/confirm": lambda app, p: app.confirm_claims(p.get("req_id"), p["ku_ids"], p["by"], p.get("reviewed_evidence")),
    "/api/qi/grant": lambda app, p: app.sign_qi_grant(p["question_id"], p["by"], p.get("claim_ids", ()), p.get("note", ""),
                                                  p.get("reviewed_evidence"), p.get("scope")),
    "/api/qi/revoke": lambda app, p: app.revoke_capability(p["cap_id"], p["by"]),
    "/api/sources/recheck": lambda app, p: app.recheck_evidence(),   # V11.7：来源改版后重取依据比指纹
    "/api/qi/request-share": lambda app, p: app.request_share(p["ku_id"], p["by"]),
    "/api/qi/withdraw": lambda app, p: app.withdraw_claim(p["ku_id"], p["by"]),
    "/api/sessions": lambda app, p: app.start_session(p["customer_id"], p.get("sales_id")),
    "/api/turn": lambda app, p: app.add_turn(*writable_turn(app, p), p["text"]),
    "/api/recommend": lambda app, p: app.recommend_now(p["session_id"]),
    "/api/resolve": lambda app, p: app.resolve(p["question_id"], p["action"], p["by"], p.get("note", ""), p.get("reviewed_evidence")),
    "/api/unfreeze": lambda app, p: app.unfreeze_access(p["actor_id"], p["by"]),     # v8 Q9.8
    "/api/escalate": lambda app, p: app.escalate(p["session_id"], p["by"]),
    "/api/reuse/adopt": lambda app, p: app.adopt_reuse(p["req_id"], p["by"]),
    "/api/reuse/decline": lambda app, p: app.decline_reuse(p["req_id"], p["reason"], p["by"]),
    "/api/reuse-note": lambda app, p: app.update_reuse_note(p["req_id"], p["text"], p["by"]),
    "/api/merge": lambda app, p: app.merge_requirements(p["question_id"], p["by"], p.get("note", "")),
    "/api/scope/extend": lambda app, p: app.extend_scope(p["question_id"], p["note"], p["by"], p.get("reviewed_evidence")),
    "/api/contribute_l2": lambda app, p: app.contribute_l2(p["req_id"], p["item_index"], p["scene_phrase"],
                                                           p["product_term"], p["by"]),   # v6
    "/api/prepared": lambda app, p: app.mark_prepared(p["question_id"], p["by"]),   # v6 退回纠偏：修改完成，交研发
    "/api/demo/open": open_route,   # v6 开场入口
    "/api/accept": lambda app, p: app.accept_requirement(p["req_id"], p["by"]),
    "/api/decline": lambda app, p: app.decline_project(p["req_id"], p["reason"], p["by"], p.get("product_id"), p.get("claim_ids", ()),
                                                     p.get("limits", ""), p.get("reviewed_evidence")),   # v7
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
            if not app.config["gateway_mock"]:
                complete = app.gateway._complete
                app.gateway._complete = lambda req, schema=None: self.lock.outside(lambda: complete(req, schema))
            ask = app.system1.ask
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
            run = f"{PLAY}-r{DIRECTOR.state['round']}" if PLAY else TRIAL
            self.clock = SimClock(T0) if PLAY else WallClock()
            use_clock(self.clock)
            run_root = Path(yaml.safe_load(Path(self.config_path).read_text(encoding="utf-8"))["run_root"])
            if PLAY:      # 每局一份资料副本与编译好的待审候选，应用起来之前离线导入
                path = str(director.prepare_round(self.config_path, run_root / run, DIRECTOR.real if DIRECTOR.state["real"] else None))
                self.app, self.writes = HuayanApp.build(path, run_id=run, resume=True), 0
            else:
                self.app, self.writes = HuayanApp.build(self.config_path, run_id=run, resume=(run_root / run).exists()), 0
            if PLAY and self.app.events.events:
                self.clock.advance_to(self.app.events.events[-1].ts)
            Thread(target=library.warm, args=(self.app.kb.sources,), daemon=True).start()
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
        if not TRIAL or PLAY:           # 试用实例是真实时间，不推进
            self.clock.advance_to(before + timedelta(minutes=1))
        activity = self.activity = self.current.activity = Activity(path, params.get("by"))
        if activity.by:
            self.recent[activity.by] = activity
        try:
            try:
                result = route(self.app, params)
            except (PermissionDenied, ValueError, KeyError, StopIteration):
                # 被门面拒绝的写操作不占业务时间：误点不会让回放台词的时刻错位
                if not TRIAL or PLAY:
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

    def advance(self, seconds):
        """游戏模式：业务时间往前走（倍速 × 真实经过的秒数）。"""
        with self.lock:
            use_clock(self.clock)
            self.clock.advance_to(self.clock.now() + timedelta(seconds=seconds))

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


def play_tick(elapsed):
    """游戏模式的一拍：没暂停时按倍速推进业务时间，觉检查、Agent 准备，导演替缺席的客户与岗位做该做的事。"""
    api, d = session_api("default"), DIRECTOR
    if d.state["paused"]:
        return
    # 一镜到底每拍推进固定的业务时间，不按墙上时间：彩排那一局写进录制缓存，现场重开同输入命中（V12.12）
    api.advance(d.state["speed"] * (PLAY_TICK if d.state["oneshot"] else elapsed))
    api.tick()
    act = next((x.get("act") for x in d.open()), None)
    for _ in range(1 if d.state["oneshot"] else 10):     # 一镜到底一拍只走一步，台下看得清每次交接
        if not d.step(set(trial_roles.values())):
            break
        api.tick()
    if d.state["oneshot"] and act != next((x.get("act") for x in d.open()), act):
        d.state["paused"] = True      # 一镜到底每幕走完停下，讲完点「继续」进下一幕（V12.12）


def play_ticker():
    last = time.monotonic()
    while True:
        WAKE.wait(PLAY_TICK)
        WAKE.clear()
        now = time.monotonic()
        try:
            with play_lock:
                play_tick(now - last)
                DIRECTOR.save()
            DIRECTOR.error = None
        except Exception as e:          # 导演这一拍没做成：记下来给界面看，下一拍再试
            DIRECTOR.error = f"{type(e).__name__}: {e}"
            traceback.print_exc()
        last = now


play_lock = Lock()


def play_restart(p):
    """重开这一局：开新的一局（新的运行目录），业务与关卡第 1 步重新送来。
    real：换报告（真实报告版 / 模拟报告）；roadshow：路演局（各岗位的事都留给人）；oneshot：一镜到底（导演按幕一件一件做完）；
    不给就照这一局的。"""
    d = DIRECTOR
    d.new_round(bool(p.get("real", d.state["real"])), bool(p.get("roadshow", d.state["roadshow"])),
                bool(p.get("oneshot", d.state["oneshot"])))
    session_api("default", rebuild=True)
    _roles_path().write_text(json.dumps(trial_roles, ensure_ascii=False, indent=1), encoding="utf-8")
    WAKE.set()
    return d.view()


def play_control(p):
    """暂停 / 继续、倍速（业务时间每真实一秒走几秒）。"""
    if "paused" in p:
        DIRECTOR.state["paused"] = bool(p["paused"])
    if "speed" in p:
        DIRECTOR.state["speed"] = int(p["speed"])
    return DIRECTOR.view()        # 进度由导演这一拍落盘（play_ticker），这里不和它抢着写文件


def play_settle(_):
    """V11.9 结算：各件业务与关卡各步送来的事走了哪条路，三个岗位的时间构成与这一局的账本（同 CEO 面的口径，两份参数）。
    这是游戏世界的总账，由导演以 CEO 身份读汇总，只给各件的路径与旧流程推算，不给原话与经手人，谁都能看。
    rerouted：推荐后来被撤下、改道交研发（关卡里来源改版挂起能力时，前面用过它的事会这样）。"""
    data = session_api("default").call("GET", "/api/ceo", {"viewer": "supervisor:CEO"})
    keep = ("session_id", "path", "reused", "arrived", "answered", "given", "safe")
    return {"params": data["params"], "bars": data["bars"],
            "cases": [{k: c[k] for k in keep} | {"rerouted": any(x["station"] == "契" and x["loop"] for x in c["stations"])}
                      for c in data["cases"]],
            "levels": [{"id": x["id"], "kind": x["kind"], "title": x["title"], "point": x["point"],
                        "passed": x["id"] in DIRECTOR.state["passed"], "cases": DIRECTOR.state["cases"].get(x["id"], [])}
                       for x in DIRECTOR.levels]}


PLAY_NOWAIT = {
    "/api/play/state": lambda p: DIRECTOR.view() | {"now": session_api("default").clock.now().isoformat()},
    "/api/play/control": play_control,
    "/api/play/settle": play_settle,
}
PLAY_API = {"/api/play/restart": play_restart}


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

    def end_headers(self):
        # V11.0：入口页每次回服务端核对，重新构建后试用者刷新就是新界面（assets 文件名带哈希，照常缓存）
        if not self.path.startswith(("/assets/", "/api/")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _api(self, method, params):
        url = urlparse(self.path)
        params |= {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            sid = self.headers.get("X-Huayan-Session", "default")
            if TRIAL and url.path not in MONTH and not url.path.startswith(("/api/trial/", "/api/play/")):
                params = trial_params(sid, method, url.path, params)
            if PLAY and url.path in PLAY_NOWAIT:           # V12.3 读进度、暂停与倍速不等导演这一拍：真实模型下一拍要几分钟
                result = PLAY_NOWAIT[url.path](params)
            elif PLAY and url.path in PLAY_API:          # 重开这一局：和导演这一拍排队
                with play_lock:
                    result = PLAY_API[url.path](params)
            elif TRIAL and url.path == "/api/trial/stamp":         # 界面轮询有没有别人的变化，不排会话锁
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
                result = dump(result) | {"trial": {"actor": trial_roles.get(sid)}, "play": bool(PLAY)}
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
    "/api/month/ceo": lambda p: ceo_of(month_app(p["run"]), p),
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
    ap.add_argument("--play", help="游戏模式的局名（V11.5）：导演按 demo/levels.yaml 送来各岗位的业务与关卡，缺席的岗位由导演代办；"
                                   "大家共用一局，身份同试用实例；每重开一次是新的一局")
    ap.add_argument("--config", help="应用配置（默认 HUAYAN_CONFIG 或 config/app.yaml）")
    ap.add_argument("--host", default="127.0.0.1", help="监听地址；试用时让同一网络里的人访问可设 0.0.0.0")
    args = ap.parse_args()
    if args.resume != bool(args.run):
        ap.error("--run 与 --resume 要一起给")
    if args.trial and args.run:
        ap.error("--trial 自带续跑，不和 --run 一起用")
    if args.trial and not re.fullmatch(r"[\w-]+", args.trial):
        ap.error("--trial 运行号只用字母、数字、下划线和短横线")
    if args.play and (args.trial or args.run or not re.fullmatch(r"[\w-]+", args.play)):
        ap.error("--play 局名只用字母、数字、下划线和短横线，不和 --trial、--run 一起用")
    CONFIG = args.config or CONFIG
    RESUME, TRIAL, PLAY = args.run, args.trial or args.play, args.play
    if PLAY:
        cfg = yaml.safe_load(Path(CONFIG).read_text(encoding="utf-8"))
        run_root = Path(cfg["run_root"])
        run_root.mkdir(parents=True, exist_ok=True)
        real = cfg.get("play_real_report")          # 可选：真实报告版的目录（不入库），配了浏览器里才能换报告
        DIRECTOR = director.Director(lambda: session_api("default"), run_root / f"{PLAY}.play.json", real=real and Path(real))
    session_api("default")   # 先构建一次：Jue-K 模型等首次加载较慢
    # V11.0：试用机拉了新代码却没重新构建前端时，浏览器里还是旧界面；启动时提醒一次
    built = (DIST / "index.html").stat().st_mtime if (DIST / "index.html").exists() else 0
    if built < max(f.stat().st_mtime for f in [*Path("web/src").rglob("*"), Path("web/index.html")] if f.is_file()):
        print("注意：web/dist 不存在或比 web/src 旧，浏览器看到的不是当前界面；先运行 npm --prefix web run build")
    if TRIAL:
        load_trial_roles()
        Thread(target=play_ticker if PLAY else trial_ticker, daemon=True).start()
        app = session_api("default").app
        print(f"化言试用实例：http://{args.host}:{PORT}（运行 {app.run_dir}，{len(app.sessions())} 个会话、"
              f"{len(app._requirements)} 张需求单，已登记身份 {len(trial_roles)} 个）")
    else:
        print(f"化言界面后端：http://{args.host}:{PORT}（每个浏览器一个会话，最多 {MAX_SESSIONS} 个）")
    ThreadingHTTPServer((args.host, PORT), Handler).serve_forever()
