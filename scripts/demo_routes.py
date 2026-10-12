"""V6-5 演示路径与对照：离线（MockGateway）跑 A、B、C、C′、D，打印每条路径的事件序列与人工节点，并对关键结果 assert（脚本自检，不算测试）。

同一批需求（6 个会话）跑两遍，都经界面同一个入口 Api.call（每次写操作推进业务时钟并 tick，与浏览器里点按钮一致）：
- v6：客户自助会话，按 demo/routes.yaml 的台词；研发在 C 选「不立项：已有产品适用」，产品经理签扩范围与机会；
- v5：同样的台词放进业务员陪同会话，业务员签字升级，研发逐张接单；没有不立项、扩适用范围、产品经理签机会（v5 没有这些职能）。
「传统」一列按黑线流程（需求 → 业务员记录 → 产品经理转述 → 研发 → 产品经理评价 → 业务员开单）定义计数，不是测量。
结果写入 docs/reports/v6_routes/metrics.json，评测页读它。全部为模拟数据。
"""
import argparse
import json
from pathlib import Path

from huayan.app import _human_events
from huayan.clock import SimClock
from huayan.knowledge import PermissionDenied
from huayan.ui.server import Api, T0, demo_routes

OUT = Path("docs/reports/v6_routes/metrics.json")
# 同一批需求：A、B、C、C′ 各一个客户，D 由两位客户各提一次
BATCH = [("A", None), ("B", None), ("C", None), ("C′", None), ("D", None), ("D", "customer:C02")]
RELAY = ["业务员记录", "产品经理转述", "研发接收", "产品经理评价", "业务员开单"]   # 黑线上每张单经过的人工节点


class Run:
    def __init__(self, config):
        self.api = Api(None, config, SimClock(T0))
        self.api.build()
        self.app = self.api.app
        assert self.app.config["gateway_mock"], "本脚本只做离线自检，请用 gateway_mock: true 的配置"
        self.routes = {r["id"]: r for r in demo_routes()}
        self.records = []

    def get(self, path, **p):
        return self.api.call("GET", path, p)

    def post(self, path, **p):
        return self.api.call("POST", path, p)

    def events(self):
        return self.app.events.query()

    def open(self, rid, customer, sales):
        """开场：v6 走 /api/demo/open（客户自助）；v5 由业务员开会话。之后逐句发出该开场自己的台词。"""
        route = self.routes[rid]
        customer = customer or route["customer"]
        if sales:
            sid = self.post("/api/sessions", customer_id=customer, sales_id=self.app.config["customer_sales"][customer]).id
            lines = route["lines"]
        else:
            sid = self.post("/api/demo/open", route=rid, customer=customer)["session_id"]
            lines = route["lines"][1:]
        for text in lines:
            self.post("/api/turn", session_id=sid, speaker="customer", text=text)
        return sid

    def question(self, family, **refs):
        self.app.tick()
        return next(q for q in self.app.bus.list(family=family)
                    if all(q.refs.get(k) == v for k, v in refs.items()) and q.prepared_at is not None)

    def req_of(self, sid):
        return next((r for r in self.app._requirements.values() if sid in r.session_ids and r.status != "merged"), None)

    def record(self, rid, sid, start):
        """一条路径的事件切片：人工节点 = 业务员 / 产品经理 / 研发本人的处理事件（不含产品经理 Agent、觉自动执行）。"""
        evs = self.events()[start:]
        human = _human_events(evs)
        session = self.app._sessions[sid]
        print(f"\n[{rid}] {self.routes[rid]['title']} · {sid} · {self.app.route_of(sid, 'rd:R01')['path']}")
        for e in evs:
            mark = "  ● " if e in human else "    "
            print(f"{mark}{e.ts:%H:%M} {e.kind:<22} {e.actor}")
        self.records.append({"route": rid, "session_id": sid, "customer": session.customer_id, "origin": session.origin,
                             "path": self.app.route_of(sid, "rd:R01")["path"],
                             "human": [{"kind": e.kind, "actor": e.actor} for e in human],
                             "rd_touches": sum(e.actor.startswith("rd:") for e in human),
                             "events": [[e.kind, e.actor] for e in evs]})
        print(f"    人工节点 {len(human)} 个" + (f"：{'、'.join(f'{e.actor} {e.kind}' for e in human)}" if human else ""))
        return evs, human


def run_v6(config):
    r = Run(config)
    app = r.app
    sids = {}
    for rid, customer in BATCH:
        start = len(r.events())
        sid = r.open(rid, customer, sales=False)
        if rid == "C":
            req = r.req_of(sid)
            assert req and req.status == "draft" and req.product_lang, "C：应有带 L2 草稿的需求单"
            assert all(not i.text.startswith("未转译") for i in req.product_lang), "C：L2 草稿不应有未转译条目"
            r.post("/api/decline", req_id=req.id, by=req.assigned_rd, product_id="HY-FX350",
                   reason="已有产品可覆盖：锦纶固色剂适用于锦纶酸性染料的白地沾色")
            q = r.question("scope_update", product_id="HY-FX350")
            r.post("/api/scope/extend", question_id=q.id, by="pm:P01", note="研发判定锦纶固色剂适用于锦纶酸性染料浸染的白地沾色")
        if rid == "D" and customer:
            q = r.question("opportunity")
            merged = r.post("/api/merge", question_id=q.id, by="pm:P01", note="两家锦氨气流缸厂同类色花，值得做一个低浴比匀染课题")
            r.question("accept_requirement", requirement_id=merged.id)
            r.post("/api/accept", req_id=merged.id, by=merged.assigned_rd)
        evs, human = r.record(rid, sid, start)
        sids[(rid, customer)] = sid
        kinds = [e.kind for e in evs]
        if rid == "A":
            assert not human and r.req_of(sid) is None and app._sessions[sid].status == "recommended", "A：自助解决，无人工、无需求单"
        if rid == "B":
            view = app.view_session(sid, app._sessions[sid].sales_id)
            assert "sales_assigned" in kinds and not human, "B：觉自动交业务员"
            assert view.card and [t.text for t in view.turns] == r.routes["B"]["lines"], "B：业务员看到完整原话与已推荐产品"
            assert not any(t.speaker == "sales" for t in view.turns), "B：业务员无需重新采集"
        if rid == "C":
            assert {"auto_executed", "project_declined", "scope_extended"} <= set(kinds), "C：自动升级 → 研发不立项 → 产品经理扩范围"
            assert not any(e.actor.startswith("sales:") for e in human), "C：不经业务员"
        if rid == "C′":
            assert r.req_of(sid) is None and app._sessions[sid].status == "recommended", "C′：第二次不产生需求单，自助命中"
            assert not any(e.actor.startswith("rd:") for e in human), "C′：研发 0 介入"
            assert any(x.owner == "pm:P01" and x.reason == "cited" and x.ref == sid for x in app.ledger.list(None)), "C′：pm:P01 获得引用记分"
        if rid == "D" and customer:
            assert ("requirements_merged", "pm:P01") in {(e.kind, e.actor) for e in human}, "D：产品经理签机会"
            d_reqs = {x.id for x in app._requirements.values() if {sids[("D", None)], sid} & set(x.session_ids)}
            assert sum(app._requirements[x].status != "merged" for x in d_reqs) == 1, "D：研发只收一张合并单"
    # 客户身份读内部评价 / L2 / L3 被拒
    customer = app.actors["customer:C01"]
    for kind, level in [("report", 1), ("translation", 2), ("translation", 3)]:
        unit = next(u for u in app.kb._units.values() if u.kind == kind and u.level == level)
        try:
            app.kb.get(unit.id, customer)
            raise AssertionError(f"客户不应读到 {unit.id}")
        except PermissionDenied:
            pass
    print("\nv6 自检通过：A 无人工；B 原话与推荐带到业务员；C 自动升级、不立项、扩范围；C′ 不产生需求单；D 一张合并单；客户读 report / L2 / L3 被拒")
    return r


def run_v5(config):
    r = Run(config)
    for rid, customer in BATCH:
        start = len(r.events())
        sid = r.open(rid, customer, sales=True)
        if r.app._sessions[sid].status != "recommended":
            q = r.question("escalate_need", session_id=sid)
            req = r.post("/api/escalate", session_id=sid, by=q.signer_id)
            r.question("accept_requirement", requirement_id=req.id)
            r.post("/api/accept", req_id=req.id, by=req.assigned_rd)
        r.record(rid, sid, start)
    return r


def summarize(v6, v5):
    def count(run, kind, role=None):
        return sum(h["kind"] == kind and (role is None or h["actor"].startswith(role)) for rec in run.records for h in rec["human"])

    def facts(run):
        app, recs = run.app, run.records
        reqs = [x for x in app._requirements.values() if x.status != "merged"]
        resolved = [q for q in app.bus.list(status=None) if q.resolution and q.resolution.action in {"sign", "dismiss", "accept"}
                    and q.resolution.by.split(":")[0] in {"sales", "pm", "rd"}]
        d_sids = {rec["session_id"] for rec in recs if rec["route"] == "D"}
        return {
            "n_sessions": len(recs),
            "accompanied": sum(rec["origin"] == "sales" for rec in recs),
            "escalations": sum(k == "escalate" for rec in recs for k, _ in rec["events"]),
            "sales_escalations": count(run, "escalate", "sales:"),
            "drafted_by_agent": sum(x.drafted_by == "pm:agent" for x in app._requirements.values()),
            "drafted": len(app._requirements),
            "pm_l2_edits": sum(e.kind == "requirement_edited" and e.actor == "pm:P01" and e.payload.get("index", -1) >= 0
                               for e in app.events.query()),
            "pm_judgments": count(run, "scope_extended", "pm:") + count(run, "requirements_merged", "pm:"),
            "returned_or_asked_back": count(run, "requirement_returned") + len(app.bus.list(family="ask_back", status=None)),
            "rd_same_kind": sum(rec["rd_touches"] for rec in recs if rec["route"] in {"C", "C′"}),
            "rd_tickets_dup": sum(bool(d_sids & set(x.session_ids)) for x in reqs),
            "human_nodes": sum(len(rec["human"]) for rec in recs)
                           + sum(rec["origin"] == "sales" or rec["path"] == "交业务员" for rec in recs),
            "self_served": sum(rec["origin"] == "customer" and rec["path"] == "自助解决" for rec in recs),
            "rd_touches": sum(rec["rd_touches"] for rec in recs),
            "rd_tickets": len(reqs),
            "signatures": len(resolved),
            "low_risk": sum(q.family in {"escalate_need", "reuse_product"} for q in resolved),
        }

    a, b = facts(v5), facts(v6)
    n = a["n_sessions"]
    roles = [
        {"role": "业务员", "duty": "回答技术问题、记录需求", "traditional": "每单",
         "v5": f"每单（陪同 {a['accompanied']}/{n}）", "v6": f"不再做（陪同 {b['accompanied']}/{n}；A 客户自助）"},
        {"role": "业务员", "duty": "签字升级", "traditional": "每单",
         "v5": f"每单（{a['sales_escalations']}/{a['escalations']} 次）", "v6": f"不再做（{b['sales_escalations']}/{b['escalations']} 次，觉自动升级 {b['escalations'] - b['sales_escalations']} 次）"},
        {"role": "产品经理", "duty": "把需求转述成产品语言", "traditional": "每单",
         "v5": f"Agent（{a['drafted_by_agent']}/{a['drafted']} 张）", "v6": f"Agent（{b['drafted_by_agent']}/{b['drafted']} 张），例外才纠偏（{b['pm_l2_edits']} 次）"},
        {"role": "产品经理", "duty": "判断产品机会、维护适用范围", "traditional": "没空做",
         "v5": f"无（{a['pm_judgments']} 次）", "v6": f"做（{b['pm_judgments']} 次：C′ 扩范围、D 签机会）"},
        {"role": "研发", "duty": "补问信息、纠正需求", "traditional": "每单",
         "v5": f"退回 + 回问 {a['returned_or_asked_back']} 次 / {a['rd_tickets']} 张单",
         "v6": f"退回 + 回问 {b['returned_or_asked_back']} 次 / {b['rd_tickets']} 张单",
         "note": "v6 的 C 在研发转译前就判为不立项，没走到回问那一步，这一行两列不能直接比大小"},
        {"role": "研发", "duty": "对同一类超范围用法做判断（C、C′）", "traditional": "每单",
         "v5": f"每单（{a['rd_same_kind']} 次）", "v6": f"只判一次（{b['rd_same_kind']} 次）"},
        {"role": "研发", "duty": "逐张处理重复需求（D）", "traditional": "每张",
         "v5": f"每张（{a['rd_tickets_dup']} 张）", "v6": f"合并后一张（{b['rd_tickets_dup']} 张）"},
    ]
    metrics = [
        {"label": "人工中转节点数", "traditional": n * len(RELAY), "v5": a["human_nodes"], "v6": b["human_nodes"],
         "note": f"传统按定义：每个需求经过 {'、'.join(RELAY)} {len(RELAY)} 个人工节点；v5 / v6 为事件日志里业务员、产品经理、研发本人的处理事件，业务员接手的会话（陪同，或客户的商务诉求交给业务员）另计 1"},
        {"label": "客户自助解决", "traditional": f"0/{n}", "v5": f"{a['self_served']}/{n}", "v6": f"{b['self_served']}/{n}",
         "note": "客户自助会话里拿到推荐、没有产生需求单、没有交业务员"},
        {"label": "研发介入次数 / 进研发的需求单", "traditional": f"{n} / {n}", "v5": f"{a['rd_touches']} / {a['rd_tickets']}",
         "v6": f"{b['rd_touches']} / {b['rd_tickets']}", "note": "介入 = 研发本人的接单、不立项等处理事件；需求单不含被合并的单"},
        {"label": "人工签字次数（其中低风险）", "traditional": "—", "v5": f"{a['signatures']}（{a['low_risk']}）",
         "v6": f"{b['signatures']}（{b['low_risk']}）", "note": "签字 = 人对觉提出的决策签字、接单或驳回；低风险 = 业务员签升级、研发审定已有产品复用，v6 改由觉自动执行"},
    ]
    return {"generated_by": "scripts/demo_routes.py", "simulated": True,
            "batch": [{"route": rid, "customer": c or v6.routes[rid]["customer"], "title": v6.routes[rid]["title"]} for rid, c in BATCH],
            "jue_model": v6.app.jue_realtime.name, "roles": roles, "metrics": metrics,
            "rd_tickets": {"traditional": n, "v5": a["rd_tickets"], "v6": b["rd_tickets"]},
            "routes": {"v6": v6.records, "v5": v5.records},
            "definitions": {"traditional": "按黑线流程定义计数，不是测量", "v5": "同一套代码以业务员陪同会话运行：业务员签升级、研发逐张接单，不使用不立项、扩适用范围、产品经理签机会",
                            "v6": "客户自助会话按 demo/routes.yaml 台词运行；研发在 C 选「不立项：已有产品适用」"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/app.yaml")
    args = parser.parse_args()
    print("==== v6 ====")
    v6 = run_v6(args.config)
    print("\n==== v5（同一批台词，业务员陪同） ====")
    v5 = run_v5(args.config)
    result = summarize(v6, v5)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n岗位判别表")
    for row in result["roles"]:
        print(f"  {row['role']}｜{row['duty']}：传统 {row['traditional']} · v5 {row['v5']} · v6 {row['v6']}")
    print("对照数字")
    for m in result["metrics"]:
        print(f"  {m['label']}：传统 {m['traditional']} · v5 {m['v5']} · v6 {m['v6']}")
    print(f"\n写入 {OUT}")


if __name__ == "__main__":
    main()
