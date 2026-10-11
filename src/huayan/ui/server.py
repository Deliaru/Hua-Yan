"""演示界面后端：标准库 HTTP 服务，把门面方法一对一暴露为 JSON 接口（形式参考 JUE wp/e 的 src/jue/ui/server.py）。
权限只在门面里执行；这里只做路由、序列化与错误映射。身份由界面的下拉框传入（演示无登录）。
运行：uv run python -m huayan.ui.server（从仓库根目录）；开发时前端 `npm run dev` 经 Vite 代理 /api。
web/dist 存在时同时提供构建后的前端页面。"""
import importlib.util
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied

CONFIG = os.environ.get("HUAYAN_CONFIG", "config/app.yaml")
PORT = int(os.environ.get("HUAYAN_PORT", "8766"))
DIST = Path("web/dist")
MAINLINE = Path("scripts/demo_mainline.py")      # WP-I 提供 run_offline(app)
REPORTS = Path("docs/reports")
REPORT_NAMES = ("distortion", "jue_k", "week")   # 评测页只读这三份报告（WP-E）

app = HuayanApp.build(CONFIG)
lock = Lock()                                     # 门面不是线程安全的，一次只处理一个请求


def dump(x):
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, (list, tuple)):
        return [dump(v) for v in x]
    if isinstance(x, dict):
        return {k: dump(v) for k, v in x.items()}
    return x


def reset(_):
    global app
    app = HuayanApp.build(CONFIG)
    return {"run_id": app.run_id}


def meta(_):
    return {"status": app.status(), "actors": list(app.actors.values()), "mainline_available": MAINLINE.exists(),
            "slots": [{"id": s.id, "label": s.label} for s in app.seeds.slots],
            "phenomena": [{"id": p.id, "label": p.label} for p in app.seeds.phenomena],
            "products": [{"id": p.id, "name": p.name} for p in app.kb.products()]}


def sessions(_):
    return [{"id": s.id, "customer_id": s.customer_id, "sales_id": s.sales_id, "status": s.status,
             "phenomenon": s.need.phenomenon} for s in app.sessions()]


def session(p):
    s = next(s for s in app.sessions() if s.id == p["id"])
    return {"view": app.view_session(p["id"], p["viewer"]), "phenomenon": s.need.phenomenon,
            "phenomenon_quote": s.need.phenomenon_quote,
            "ask_back": [q for q in app.bus.list(family="ask_back") if q.refs.get("session_id") == p["id"]],
            "ask_back_history": [q for q in app.bus.list(family="ask_back", status=None)
                                 if q.refs.get("session_id") == p["id"] and q.status != "open"]}


def questions(p):
    return [q for q in app.bus.list(owner_role=p["role"]) if q.owner_id in (None, p["viewer"])]


def report(p):
    name = p["name"]
    if name not in REPORT_NAMES:
        raise KeyError(name)
    return json.loads((REPORTS / name / "metrics.json").read_text(encoding="utf-8"))


def offline_mainline(_):
    if not app.status().gateway_mock:
        raise ValueError("载入离线主线只用于角色助手离线模式")
    spec = importlib.util.spec_from_file_location("demo_mainline", MAINLINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run_offline(app)
    return {"ok": True}


def turn(p):
    # 离线模式直接录入发言；和 chat 一样之后 tick，问题队列与回问才会更新
    session = app.add_turn(p["session_id"], p["speaker"], p["text"])
    app.tick()
    return session


def reply_draft(p):
    session = app.save_reply_draft(p["session_id"], p["text"], p["by"])
    app.tick()
    return session


def escalate_note(p):
    session = app.save_escalate_note(p["session_id"], p["text"], p["by"])
    app.tick()
    return session


def chat(p):
    conv = app.agents.chat(p["actor"], p["text"], p.get("session_id"))
    app.tick()
    return conv


def decide(p, approve: bool):
    action = (app.agents.approve(p["action_id"], p["by"]) if approve
              else app.agents.reject(p["action_id"], p["by"], p.get("note", "")))
    app.tick()
    return action


GET = {
    "/api/meta": meta,
    "/api/sessions": sessions,
    "/api/session": session,
    "/api/questions": questions,
    "/api/requirements": lambda p: [{"id": r.id, "status": r.status, "phenomenon": r.phenomenon}
                                    for r in app.requirements(p["viewer"])],
    "/api/requirement": lambda p: app.requirement_view(p["id"], p["viewer"]),
    "/api/ledger": lambda p: app.ledger.totals(),
    "/api/contributions": lambda p: app.contributions(p["viewer"]),
    "/api/report": report,
    "/api/agents/conversation": lambda p: next((c for c in app.agents.conversations(p["actor"])
                                                if c.session_id == p.get("session_id")), None),
    "/api/agents/trace": lambda p: app.agents.trace(p["conversation_id"]),
    "/api/agents/pending": lambda p: app.agents.pending(p["actor"]),
}
POST = {
    "/api/reset": reset,
    "/api/offline-mainline": offline_mainline,
    "/api/sessions": lambda p: app.start_session(p["customer_id"], p["sales_id"]),
    "/api/turn": turn,
    "/api/reply-draft": reply_draft,
    "/api/escalate-note": escalate_note,
    "/api/agents/chat": chat,
    "/api/agents/approve": lambda p: decide(p, True),
    "/api/agents/reject": lambda p: decide(p, False),
}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _api(self, routes, params):
        url = urlparse(self.path)
        params |= {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            with lock:
                status, body = 200, dump(routes[url.path](params))
        except PermissionDenied as e:
            status, body = 403, {"error": str(e)}
        except ValueError as e:
            status, body = 400, {"error": str(e)}
        except (KeyError, StopIteration) as e:
            status, body = 404, {"error": f"不存在：{e}"}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._api(GET, {})
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
        self._api(POST, json.loads(self.rfile.read(length) or b"{}"))


if __name__ == "__main__":
    print(f"化言界面后端：http://127.0.0.1:{PORT}（run {app.run_id}）")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
