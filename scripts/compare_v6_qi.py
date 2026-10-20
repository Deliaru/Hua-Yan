"""Q7 与 V6 对照（离线，全部为模拟数据，研发处置由本脚本写定）：同一批按时间排序的客户问题，V6 原方案与契各跑一次。

问题批次与指标的统计函数两边共用；两个驱动各自只调用本版本已有的接口，经界面同一个入口 Api.call：
- 契：编译替身 RAG；研发判「已有产品适用」时用 decline_project(..., claim_ids) 确认依据，产品经理 extend_scope 批准；
- V6：在 351c2c9 的 worktree 里以子进程运行本脚本（--driver v6）。研发判断与产品不相容时 V6 记不下来，按 V6 的真实做法不带产品不立项。
重启：契在同一运行目录续跑；V6 没有续跑，重启就是新的运行。撤销：契由研发撤销能力；V6 没有撤销接口。
指标全部从两边的事件日志算出，写进 docs/reports/qi_demo/compare.md 与 compare.json。

  git worktree add --detach ../Huayan-v6 351c2c9
  uv run python scripts/compare_v6_qi.py [--v6 ../Huayan-v6]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from huayan.clock import SimClock
from huayan.ui.server import Api, T0

OUT = Path("docs/reports/qi_demo")
SAME = "锦纶氨纶弹力布在经轴缸上染，深一块浅一块"
OTHER = "纯锦纶在经轴缸上染，深一块浅一块"
OVERFLOW = "锦氨弹力布在溢流缸上染，深一块浅一块"
PUBLIC = "纯锦纶在溢流缸上染，深一块浅一块"           # 产品页写明的情境：两边都应能自助
PARTIAL = [("customer", "锦纶氨纶的布，深一块浅一块"), ("sales", "用的是什么染色设备？"), ("customer", "设备不清楚")]
# 问题批次：(窗口, 客户, 话, 研发判断的产品)；研发判断 = 进了研发时研发写定的处置。"restart" / "revoke" 是两个时刻。
BATCH = [
    ("W1", "customer:C01", SAME, "HY-LV205"), ("W1", "customer:C02", OVERFLOW, "HY-LV205"), ("W1", "customer:C03", OTHER, None),
    ("W1", "customer:C04", PUBLIC, "HY-LV205"),
    ("W2", "customer:C04", SAME, "HY-LV205"), ("W2", "customer:C01", PARTIAL, None), ("W2", "customer:C02", SAME, "HY-LV205"),
    "restart",
    ("W3", "customer:C03", SAME, "HY-LV205"), ("W3", "customer:C04", OTHER, None), ("W3", "customer:C01", SAME, "HY-LV205"),
    ("W3", "customer:C02", PUBLIC, "HY-LV205"),
    "revoke",       # 研发撤回「LV205 适用锦纶氨纶 × 经轴」：此后这类问题应回到研发，研发判无产品
    ("W4", "customer:C02", SAME, None), ("W4", "customer:C03", SAME, None), ("W4", "customer:C04", PUBLIC, "HY-LV205"),
]
JUDGED = {"product_id": "HY-LV205", "conditions": {"fiber": ["锦纶氨纶"], "equipment": ["经轴染色机"]}}
C2 = "ku:claim:2"
REASON = {"HY-LV205": "已有产品适用：HY-LV205 可用于锦纶氨纶弹力面料的经轴染色", None: "暂无适用产品，已记录需求"}


class Driver:
    def __init__(self, config, resume=None):
        self.config = config
        self.api = Api(None, config, SimClock(T0))
        self.api.build(resume) if resume else self.api.build()
        self.runs = [self.api.app.run_id]

    @property
    def app(self):
        return self.api.app

    def post(self, path, **p):
        return self.api.call("POST", path, p)

    def ask(self, customer, turns):
        sales = self.app.config["customer_sales"][customer] if isinstance(turns, list) else None
        sid = self.post("/api/sessions", customer_id=customer, sales_id=sales).id
        for speaker, text in turns if sales else [("customer", turns)]:
            self.post("/api/turn", session_id=sid, speaker=speaker, text=text)
        self.app.tick()
        return sid

    def ticket(self, sid):
        self.app.tick()
        return next((r for r in self.app._requirements.values() if sid in r.session_ids), None)

    def events(self):
        """事件带上所属运行：V6 重启是新的运行，会话号从头开始。"""
        return [e.model_dump(mode="json") | {"run": self.app.run_id} for e in self.app.events.query()]


class QiDriver(Driver):
    def __init__(self, config):
        super().__init__(config)
        from huayan.ingest.compile import Proposals, admit
        items = yaml.safe_load(Path("seeds/rag/proposals.yaml").read_text(encoding="utf-8"))["items"]
        admit(Proposals(items=items).items, self.app.kb.sources, self.app.kb)
        self.k5, self.done = None, []

    def judge(self, req, product):
        claims = [C2] if product and self.k5 is None else []
        self.post("/api/decline", req_id=req.id, by=req.assigned_rd, product_id=product, reason=REASON[product],
                  claim_ids=claims)
        if claims:
            self.app.tick()
            q = next(q for q in self.app.bus.list(family="scope_update") if q.refs.get("requirement_ids") == req.id)
            self.k5 = q.refs["capability_id"]
            self.post("/api/scope/extend", question_id=q.id, by="pm:P01", note="（模拟）按研发判断批准锦纶氨纶 × 经轴染色机")

    def restart(self):
        self.done += self.events()
        run_id = self.app.run_id
        self.api = Api(None, self.config, SimClock(T0))
        self.api.build(run_id)

    def revoke(self):
        self.post("/api/qi/revoke", cap_id=self.k5, by=self.app.kb._caps[self.k5].granted_by)

    def all_events(self):
        return self.events()          # 续跑读回了此前的全部事件


class V6Driver(Driver):
    def __init__(self, config):
        super().__init__(config)
        self.done = []

    def judge(self, req, product):
        from huayan.domain import consistent
        if product and not consistent(self.app.kb.product(product), req.known_slots):
            product = None              # V6 只能选与客户已知条件相容的产品，研发的判断记不下来
        self.post("/api/decline", req_id=req.id, by=req.assigned_rd, product_id=product, reason=REASON[product])

    def restart(self):                  # V6 没有续跑：重启就是一次新的运行
        self.done += self.events()
        self.api = Api(None, self.config, SimClock(T0))
        self.api.build()
        self.runs.append(self.app.run_id)

    def revoke(self):
        pass                            # V6 没有撤销接口

    def all_events(self):
        return self.done + self.events()


def drive(kind):
    d = (QiDriver if kind == "qi" else V6Driver)("config/app.yaml")
    asked = []
    for item in BATCH:
        if isinstance(item, str):
            getattr(d, item)()
            asked.append({"marker": item})
            continue
        window, customer, turns, product = item
        sid = d.ask(customer, turns)
        req = d.ticket(sid)
        if req is not None:
            d.judge(req, product)
        asked.append({"window": window, "session_id": sid, "run_id": d.app.run_id})
    return {"runs": d.runs, "asked": asked, "events": d.all_events()}


def metrics(result, products):
    """两边共用：只读事件日志（两边都有的 recommend、requirement_created、project_declined 事件）。"""
    by_session, declined, created = {}, {}, set()
    for e in result["events"]:
        if e["session_id"]:
            by_session.setdefault((e["run"], e["session_id"]), []).append(e)
        if e["kind"] == "project_declined":
            for sid in e["payload"]["session_ids"]:
                declined[(e["run"], sid)] = e["payload"]["product_id"]
        if e["kind"] == "requirement_created":
            created |= {(e["run"], sid) for sid in e["payload"]["session_ids"]}
    rows, judged, effective = [], set(), True
    for item, batch in zip(result["asked"], BATCH):
        if isinstance(batch, str):
            effective = effective and batch != "revoke"
            if batch == "revoke":
                judged.discard(("锦纶氨纶", "经轴染色机"))
            continue
        window, _, turns, truth = batch
        key = (item["run_id"], item["session_id"])
        evs = by_session.get(key, [])
        rec = [e["payload"] for e in evs if e["kind"] == "recommend"]
        known = rec[-1]["known"] if rec else next((e["payload"]["filled"] for e in reversed(evs) if e["kind"] == "extraction"), {})
        to_rd = key in created
        cls = (known.get("fiber"), known.get("equipment"))
        self_served = bool(rec) and not to_rd
        confirmed = self_served and rec[-1].get("status", "confirmed") == "confirmed"
        rd_answer = declined.get(key)
        authorized = confirmed and inside(rec[-1]["product_id"], known, products, effective)
        rows.append({"window": window, "session_id": item["session_id"], "class": cls, "truth": truth, "known": known,
                     "self_served": self_served, "confirmed": confirmed, "product": rec[-1]["product_id"] if rec else None,
                     "to_rd": to_rd, "rd_answer": rd_answer, "repeat": to_rd and cls in judged,
                     "unauthorized": confirmed and not authorized,
                     "solved": (confirmed and rec[-1]["product_id"] == truth) or (to_rd and rd_answer == truth)})
        if to_rd:
            judged.add(cls)
    windows = {}
    for r in rows:
        w = windows.setdefault(r["window"], {"questions": 0, "solved": 0, "rd": 0})
        w["questions"] += 1
        w["solved"] += r["solved"]
        w["rd"] += r["to_rd"]
    for w in windows.values():
        w["rd_per_solved"] = round(w["rd"] / w["solved"], 2) if w["solved"] else "—"
    after_revoke = [r for r, b in zip(rows, [b for b in BATCH if not isinstance(b, str)]) if b[0] == "W4"]
    before = {r["class"] for r in rows if r["window"] in ("W1", "W2") and r["confirmed"] and not r["unauthorized"]}
    after_restart = [r for r in rows if r["window"] == "W3" and r["class"] in before]
    after_revoke = [r for r in after_revoke if r["class"] == ("锦纶氨纶", "经轴染色机")]
    return {"rows": rows, "windows": windows,
            "correct_self_service": sum(r["self_served"] and r["confirmed"] and r["product"] == r["truth"] for r in rows),
            "rd_repeats": sum(r["repeat"] for r in rows),
            "unauthorized_confirmed": sum(r["unauthorized"] for r in rows),
            "after_revoke_back_to_rd": f"{sum(r['to_rd'] for r in after_revoke)}/{len(after_revoke)}",
            "after_restart_kept": f"{sum(r['confirmed'] for r in after_restart)}/{len(after_restart)}",
            "in_public_scope": sum(r["truth"] is not None and inside(r["truth"], r["known"], products, False) for r in rows),
            "needs_judgment": sum(r["truth"] is not None and not inside(r["truth"], r["known"], products, False) for r in rows)}


def inside(product, known, products, judged_in_effect):
    """确定推荐是否落在某个完整情境内：产品页写明的范围（各槽位取值组合），或仍有效的研发判断。"""
    situations = [products[product]] + ([JUDGED["conditions"]] if judged_in_effect and product == JUDGED["product_id"] else [])
    return any(all(slot in known and known[slot] in values for slot, values in s.items()) for s in situations)


def page(qi, v6):
    row = lambda name, a, b: f"| {name} | {a} | {b} |"
    lines = ["# 契与 V6 对照（离线，模拟数据）", "",
             "> 由 `scripts/compare_v6_qi.py` 生成。同一批按时间排序的客户问题，研发处置由脚本写定（不是测量人的行为）；指标从两边的事件日志算出。",
             "> V6 在 `351c2c9` 的 worktree 里运行；它不能记录与产品标注不相容的「已有产品适用」，按它的真实做法不带产品不立项。", "",
             "| 指标 | V6 | 契 |", "|---|---|---|",
             row("正确的自助处理数", v6["correct_self_service"], qi["correct_self_service"]),
             row("研发重复参与次数（同一类判断第二次及以后仍进研发）", v6["rd_repeats"], qi["rd_repeats"]),
             row("未经授权的确定推荐数（没有落在产品页或有效研发判断的完整情境内）", v6["unauthorized_confirmed"], qi["unauthorized_confirmed"]),
             row("撤销后同类问题回到研发", "不适用（V6 没有撤销；判断本来就记不下，同类问题一直进研发）", qi["after_revoke_back_to_rd"]),
             row("重启前已能自助的同类问题，重启后仍自助", v6["after_restart_kept"], qi["after_restart_kept"]), "",
             f"批次构成：{len(qi['rows'])} 个问题，其中 {qi['in_public_scope']} 个落在产品页写明的情境内（两边都能自助），"
             f"{qi['needs_judgment']} 个要靠研发「已有产品适用」的判断（V6 记不下这类判断，批次有意包含它们，这是对照要看的差别），"
             "其余是研发判无产品或条件不全。「未经授权」按契的口径：确定推荐的已知条件没有完整落在产品页情境或仍有效的研发判断内。", "",
             "## 每解决一个客户问题需要几次研发判断（按窗口）", "",
             "| 窗口 | V6 研发判断 / 解决 | 契 研发判断 / 解决 |", "|---|---|---|"]
    for w in qi["windows"]:
        a, b = v6["windows"][w], qi["windows"][w]
        lines.append(f"| {w} | {a['rd']} / {a['solved']} = {a['rd_per_solved']} | {b['rd']} / {b['solved']} = {b['rd_per_solved']} |")
    lines += ["", "W2 与 W3 之间重启，W3 与 W4 之间研发撤回「LV205 适用锦纶氨纶 × 经轴」。这条曲线由授予机制算出，不是学习曲线。",
              "「无产品」的判断两边都不沉淀为能力，所以同类问题仍进研发，计入重复参与。", "",
              "## 逐题", "", "| 窗口 | 条件 | 研发判断 | V6 | 契 |", "|---|---|---|---|---|"]
    show = lambda r: ("确定推荐 " + r["product"] if r["confirmed"] else "可能适用 " + r["product"] if r["self_served"] else
                      f"进研发 → {r['rd_answer'] or '无产品'}") + ("（未经授权）" if r["unauthorized"] else "")
    for a, b in zip(v6["rows"], qi["rows"]):
        lines.append(f"| {b['window']} | {' × '.join(x or '?' for x in b['class'])} | {b['truth'] or ('—（条件不全，应先问清）' if None in b['class'] else '无产品')} | {show(a)} | {show(b)} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", choices=["qi", "v6"])
    ap.add_argument("--json")
    ap.add_argument("--v6", default="../Huayan-v6")
    args = ap.parse_args()
    if args.driver:            # 子进程：只跑一边，结果写 JSON
        Path(args.json).write_text(json.dumps(drive(args.driver), ensure_ascii=False), encoding="utf-8")
        return
    v6_root = Path(args.v6).resolve()
    if not (v6_root / "src" / "huayan").exists():
        sys.exit(f"找不到 V6 worktree：{v6_root}（git worktree add --detach ../Huayan-v6 351c2c9）")
    work = Path("data/compare_v6").resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    env = os.environ | {"PYTHONPATH": str(v6_root / "src"), "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--driver", "v6", "--json", str(work / "v6.json")],
                   cwd=v6_root, env=env, check=True)
    v6_raw = json.loads((work / "v6.json").read_text(encoding="utf-8"))
    qi_raw = drive("qi")
    seeds = yaml.safe_load(Path("seeds/products.yaml").read_text(encoding="utf-8"))["items"]
    products = {p["id"]: p["applicable"] for p in seeds}
    qi, v6 = metrics(qi_raw, products), metrics(v6_raw, products)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "compare.json").write_text(json.dumps({"qi": qi | {"runs": qi_raw["runs"]}, "v6": v6 | {"runs": v6_raw["runs"]}},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "compare.md").write_text(page(qi, v6), encoding="utf-8")
    print(page(qi, v6))


if __name__ == "__main__":
    main()
