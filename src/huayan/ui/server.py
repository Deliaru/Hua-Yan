"""演示界面后端：标准库 HTTP 服务，把门面方法一对一暴露为 JSON 接口（形式参考 JUE wp/e 的 src/jue/ui/server.py）。
权限只在门面里执行；这里只做路由、序列化与错误映射。身份由界面的下拉框传入（演示无登录）。
运行：uv run python -m huayan.ui.server（从仓库根目录）；开发时前端 `npm run dev` 经 Vite 代理 /api。
web/dist 存在时同时提供构建后的前端页面。
会话隔离：界面每个浏览器带一个会话号（请求头 X-Huayan-Session），每个会话有自己的门面与业务时钟，
多人同时试用互不干扰、互不排队；不带会话号的调用（脚本、curl）共用 default。
运行方式按会话选择：录制回放（默认），或填自己的大模型 / OneJev 接口真实运行（BYOK，见 huayan.gateway.byok）。"""
import importlib.util
import json
import os
import re
import time
from collections import OrderedDict
import traceback
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, RLock, local
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel
import openai
import yaml

from huayan.app import HuayanApp, _human_events
from huayan.clock import SimClock, get_clock, set_clock
from huayan.contracts import ReqItem, SheetDraft, SHANGHAI
from huayan.knowledge import PermissionDenied
from huayan.gateway.byok import Byok, public_url
from huayan.gateway.client import ReplayMiss, StructuredOutputError
from huayan.jev.system1 import OneJevClient

CONFIG = os.environ.get("HUAYAN_CONFIG", "config/app.yaml")
PORT = int(os.environ.get("HUAYAN_PORT", "8766"))
DIST = Path("web/dist")
REPORTS = Path("docs/reports")
MAINLINE = Path("demo/mainline.yaml")
ROUTES = Path("demo/routes.yaml")     # v6 开场入口 A–D、C′
STORY = Path("demo/story.yaml")       # V6-5.5 演示讲解：一个上午 / 按路径看
REPORT_NAMES = ("distortion", "distortion_300", "jue_k", "week", "v6_routes")   # 评测页只读这几份报告（WP-E；v6_routes 为 V6-5 岗位对照）；300 张卡用于按「应升级」拆开；single_card 经门面按查看者读取

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

    def __init__(self, path):
        self.path, self.t0, self.events, self.ms, self.error = path, time.monotonic(), [], None, None

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
            "products": [{"id": p.id, "name": p.name} for p in app.kb.products()]}


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
    "/api/requirement": lambda app, p: app.requirement_view(p["id"], p["viewer"]),
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
    "/api/agents/conversation": lambda app, p: next((c for c in app.agents.conversations(p["actor"])
                                                if c.session_id == p.get("session_id")), None),
    "/api/agents/trace": lambda app, p: app.agents.trace(p["conversation_id"]),
    "/api/agents/pending": lambda app, p: app.agents.pending(p["actor"]),
}
POST = {
    "/api/sessions": lambda app, p: app.start_session(p["customer_id"], p.get("sales_id")),
    "/api/turn": lambda app, p: app.add_turn(p["session_id"], p["speaker"], p["text"]),
    "/api/recommend": lambda app, p: app.recommend_now(p["session_id"]),
    "/api/resolve": lambda app, p: app.resolve(p["question_id"], p["action"], p["by"], p.get("note", "")),
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
    "/api/decline": lambda app, p: app.decline_project(p["req_id"], p["reason"], p["by"], p.get("product_id")),   # v6
    "/api/return": lambda app, p: app.return_requirement(p["req_id"], p["reason"], p["by"]),
    "/api/req-item": lambda app, p: app.edit_req_item(p["req_id"], p["index"], ReqItem.model_validate(p["item"]), p["by"]),
    "/api/confirm": lambda app, p: app.confirm_translation(p["req_id"], p["by"]),
    "/api/contribute": lambda app, p: app.contribute_translation(p["req_id"], p["item_index"],
        p["scene_phrase"], p["chem_term"], p["by"]),
    "/api/market-eval": lambda app, p: app.record_market_eval(p["req_id"], p["result"], p["note"], p["by"]),
    "/api/points": lambda app, p: app.set_public_points(p["req_id"], p["text"], p["sealed"], p["by"]),
    "/api/sheet": lambda app, p: app.save_sheet(p["req_id"], SheetDraft.model_validate(p["sheet"]), p["by"]),
    "/api/release": lambda app, p: app.release_product(p["req_id"], p["by"]),
    "/api/trial": lambda app, p: app.record_requirement_trial(p["req_id"], p["result"], p["by"]),
    "/api/decrypt/request": lambda app, p: app.request_decrypt(p["session_id"], p["by"]),
    "/api/decrypt/decide": lambda app, p: app.decide_decrypt(p["question_id"], p["by"], p["approve"], p.get("text", "")),
    "/api/reply-draft": lambda app, p: app.save_reply_draft(p["session_id"], p["text"], p["by"]),
    "/api/escalate-note": lambda app, p: app.save_escalate_note(p["session_id"], p["text"], p["by"]),
    "/api/agents/chat": lambda app, p: app.agents.chat(p["actor"], p["text"], p.get("session_id"), focus=p.get("focus")),
    "/api/agents/approve": lambda app, p: app.agents.approve(p["action_id"], p["by"]),
    "/api/agents/reject": lambda app, p: app.agents.reject(p["action_id"], p["by"], p.get("note", "")),
}


class Api:
    """HTTP 与演示脚本共用入口；调用方先设置 SimClock，再构建门面。"""

    def __init__(self, app, config_path=CONFIG, clock=None, byok=None):
        self.app, self.config_path, self.byok = app, config_path, byok
        self.clock = clock or get_clock()   # 本会话的业务时钟；每次调用先在当前线程换上它
        self.lock = RLock()
        self.writes = 0     # 本轮成功的写操作数；回放部署里按它对齐台词的下一步
        self.activity = None                # 正在进行或最近一次写操作的处理过程
        self.agent_runs = {}                # (对话 id, 回复序号) → 这一轮 Agent 的过程，供对话里展开
        self.story_done, self.story_handles = 0, {}   # V6-5.5 讲解已执行到第几步；句柄 → 会话、开场、已说几句
        self.story_last = None                        # 上一步的耗时、模型调用次数与是否偏离剧本
        if app is not None:
            self.attach(app)

    def attach(self, app):
        """把门面、网关、OneJev 的进度回调接到本会话的过程记录上。"""
        app.progress = app.gateway.trace = self.emit
        for client in (app.system1, getattr(app.system1, "onejev", None)):
            if isinstance(client, OneJevClient):
                client.trace = self.emit

    def emit(self, kind, **fields):
        activity = self.activity
        if activity is None or activity.ms is not None:
            return
        activity.add(kind, **fields)
        if kind == "agent_end":
            events = activity.events
            start = max(i for i, e in enumerate(events) if e["kind"] == "agent_start" and e["conversation_id"] == fields["conversation_id"])
            self.agent_runs[(fields["conversation_id"], fields["index"])] = {
                "events": events[start:], "ms": (events[-1]["t"] - events[start]["t"]) * 1000}

    def progress(self, viewer):
        return self.activity.view(viewer) if self.activity else None

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

    def build(self):
        self.clock = SimClock(T0)
        use_clock(self.clock)
        self.app, self.writes = HuayanApp.build(self.config_path, byok=self.byok), 0
        self.activity, self.agent_runs = None, {}
        self.story_done, self.story_handles, self.story_last = 0, {}, None
        self.attach(self.app)

    def story_state(self):
        story = demo_story()
        view = self._story_view(story["steps"][self.story_done - 1]["view"]) if self.story_done else None
        return story | {"done": self.story_done, "view": view, "last": self.story_last}

    def story_next(self):
        """讲解的下一步：真的执行 do 里的写操作（经 _call，与浏览器里点按钮、scripts/demo_routes.py 同一个入口）。
        看的人已经在工作面上自己做过的动作（开过、发过这句、签过、接过）跳过，接着往下讲；所以失败后再点一次就是重试。"""
        step = demo_story()["steps"][self.story_done]
        calls, started = self._model_calls(), time.monotonic()
        try:
            for action in step.get("do", []):
                self._story_do(action)
        except (openai.APIError, StructuredOutputError) as e:
            raise ValueError(f"模型这一步调用失败（{type(e).__name__}: {e}）。再点一次「下一步」重试，已经做完的动作会跳过。") from e
        except (PermissionDenied, ValueError, KeyError, StopIteration) as e:
            raise ValueError(f"这一步没能执行（{type(e).__name__}: {e}）。前面的走向和剧本不同（自己操作过，或真实模型判断不同），"
                             "可以在目录里点这一章，从头快进到它的开头重新看。") from e
        self.story_done += 1
        n, tokens = (a - b for a, b in zip(self._model_calls(), calls))
        self.story_last = {"seconds": round(time.monotonic() - started, 1), "calls": n, "tokens": tokens,
                           "diverged": self._story_diverged(step.get("expect", {}))}
        return self.story_state()

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
        """本会话到此刻的大模型调用次数与 token 数（计量文件里 kind=llm 的记录；回放时是录制下来的输出）。"""
        path = Path(self.app.meter.path)
        records = [json.loads(line) for line in path.open(encoding="utf-8")] if path.exists() else []
        llm = [r for r in records if r["kind"] == "llm"]
        return len(llm), sum(r["input_tokens"] + r["output_tokens"] for r in llm)

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
        self.clock.advance_to(before + timedelta(minutes=1))
        activity = self.activity = Activity(path)
        try:
            try:
                result = route(self.app, params)
            except (PermissionDenied, ValueError, KeyError, StopIteration):
                # 被门面拒绝的写操作不占业务时间：误点不会让回放台词的时刻错位
                self.clock = SimClock(before)
                use_clock(self.clock)
                raise
            self.app.tick()
        except Exception as e:
            activity.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            activity.ms = (time.monotonic() - activity.t0) * 1000
        self.writes += 1
        return result

    def mode(self):
        """本会话的运行方式与所用模型名（不含密钥）。"""
        b, config = self.byok, self.app.config
        llm = None if config["gateway_mock"] else self.app.gateway.tiers["fast"]["model"]
        jev = (b.jev_model if b.jev_base_url else None) if b else self.app.system1.model if config["system1_impl"] == "onejev" else None
        return {"kind": "replay" if config["replay"] else "byok" if b else "local", "llm_model": llm, "jev_model": jev,
                "jev_fallback": bool(b and b.jev_base_url and b.jev_fallback)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _api(self, method, params):
        url = urlparse(self.path)
        params |= {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            sid = self.headers.get("X-Huayan-Session", "default")
            # 过程面板的两个读接口不排会话锁：会话锁正被那次耗时的写操作占着
            if url.path == "/api/mode":
                result = set_mode(sid, params)
            elif url.path == "/api/progress":
                result = session_api(sid).progress(params["viewer"])
            elif url.path == "/api/agents/process":
                result = session_api(sid).agent_process(params["conversation_id"], params["viewer"])
            else:
                result = session_api(sid).call(method, url.path, params)
            status, body = 200, dump(result)
        except PermissionDenied as e:
            status, body = 403, {"error": str(e)}
        except ReplayMiss:
            status, body = 409, {"error": "当前是录制回放，只能沿演示讲解一步步走（这一步不在录制里）。想自由操作，"
                                          "点右上角「接入真实模型」用你自己的模型真实运行；进度乱了可以在讲解目录里点某一章重看。"}
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


apis: OrderedDict[str, Api] = OrderedDict()
apis_lock = Lock()


def session_api(sid, byok=None, rebuild=False):
    if sid != "default" and not SESSION_ID.fullmatch(sid):
        raise ValueError("会话号格式不对")
    with apis_lock:
        if sid not in apis or rebuild:
            api = Api(None, CONFIG, byok=byok)
            api.build()
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
    session_api("default")   # 先构建一次：Jue-K 模型等首次加载较慢
    print(f"化言界面后端：http://127.0.0.1:{PORT}（每个浏览器一个会话，最多 {MAX_SESSIONS} 个）")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
