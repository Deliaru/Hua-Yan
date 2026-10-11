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
from collections import OrderedDict
import traceback
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, RLock, local
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel
import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, get_clock, set_clock
from huayan.contracts import ReqItem, SheetDraft, SHANGHAI
from huayan.knowledge import PermissionDenied
from huayan.gateway.byok import Byok, public_url
from huayan.gateway.client import ReplayMiss

CONFIG = os.environ.get("HUAYAN_CONFIG", "config/app.yaml")
PORT = int(os.environ.get("HUAYAN_PORT", "8766"))
DIST = Path("web/dist")
REPORTS = Path("docs/reports")
MAINLINE = Path("demo/mainline.yaml")
REPORT_NAMES = ("distortion", "distortion_300", "jue_k", "week")   # 评测页只读这几份报告（WP-E）；300 张卡用于按「应升级」拆开；single_card 经门面按查看者读取

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
             "phenomenon": s.need.phenomenon} for s in app.sessions()]


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


GET = {
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
    "/api/ledger": lambda app, p: app.ledger.totals(),
    "/api/contributions": lambda app, p: app.contributions(p["viewer"]),
    "/api/report": report,
    "/api/agents/conversation": lambda app, p: next((c for c in app.agents.conversations(p["actor"])
                                                if c.session_id == p.get("session_id")), None),
    "/api/agents/trace": lambda app, p: app.agents.trace(p["conversation_id"]),
    "/api/agents/pending": lambda app, p: app.agents.pending(p["actor"]),
}
POST = {
    "/api/sessions": lambda app, p: app.start_session(p["customer_id"], p["sales_id"]),
    "/api/turn": lambda app, p: app.add_turn(p["session_id"], p["speaker"], p["text"]),
    "/api/recommend": lambda app, p: app.recommend_now(p["session_id"]),
    "/api/resolve": lambda app, p: app.resolve(p["question_id"], p["action"], p["by"], p.get("note", "")),
    "/api/escalate": lambda app, p: app.escalate(p["session_id"], p["by"]),
    "/api/reuse/adopt": lambda app, p: app.adopt_reuse(p["req_id"], p["by"]),
    "/api/reuse/decline": lambda app, p: app.decline_reuse(p["req_id"], p["reason"], p["by"]),
    "/api/reuse-note": lambda app, p: app.update_reuse_note(p["req_id"], p["text"], p["by"]),
    "/api/merge": lambda app, p: app.merge_requirements(p["question_id"], p["by"]),
    "/api/accept": lambda app, p: app.accept_requirement(p["req_id"], p["by"]),
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
        if method == "GET" and path == "/api/meta":
            return meta(self.app, params) | {"mode": self.mode()}
        route = {"GET": GET, "POST": POST}[method][path]
        if method == "POST":
            before = self.clock.now()
            self.clock.advance_to(before + timedelta(minutes=1))
        try:
            result = route(self.app, params)
        except (PermissionDenied, ValueError, KeyError, StopIteration):
            if method == "POST":            # 被门面拒绝的写操作不占业务时间：误点不会让回放台词的时刻错位
                self.clock = SimClock(before)
                use_clock(self.clock)
            raise
        if method == "POST":
            self.app.tick()
            self.writes += 1
        return result

    def mode(self):
        """本会话的运行方式（不含密钥）。"""
        b = self.byok
        return {"kind": "replay" if self.app.config["replay"] else "byok" if b else "local",
                "llm_model": b.llm_model if b else None, "jev_model": b.jev_model if b and b.jev_base_url else None,
                "jev_fallback": bool(b and b.jev_base_url and b.jev_fallback)}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _api(self, method, params):
        url = urlparse(self.path)
        params |= {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            sid = self.headers.get("X-Huayan-Session", "default")
            result = set_mode(sid, params) if url.path == "/api/mode" else session_api(sid).call(method, url.path, params)
            status, body = 200, dump(result)
        except PermissionDenied as e:
            status, body = 403, {"error": str(e)}
        except ReplayMiss:
            status, body = 409, {"error": "当前为演示模式，未接入真实模型：这一步不在录制好的演示主线里（缓存未命中）。"
                                          "请按导览操作；进度已乱时点右上角「重置进度」或「载入检查点」。"}
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
    byok.check()
    return session_api(sid, byok, rebuild=True).mode()


if __name__ == "__main__":
    session_api("default")   # 先构建一次：Jue-K 模型等首次加载较慢
    print(f"化言界面后端：http://127.0.0.1:{PORT}（每个浏览器一个会话，最多 {MAX_SESSIONS} 个）")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
