"""Q7 决赛主演示（离线，全部为模拟数据）：契的三态、四步能力复用与重启。

经界面同一个入口 Api.call 跑（每次写操作推进业务时钟 1 分钟并 tick），每一步的结论从事件日志与会话文件读出，
写进 docs/reports/qi_demo/demo.json 与 demo.md。替身 RAG 复制到 data/qi_demo/rag 再编译（第 4 步要改原文）。

  uv run python scripts/demo_qi.py
"""
import json
import shutil
from pathlib import Path

import yaml

from huayan.clock import SimClock
from huayan.ingest.compile import Proposals, admit
from huayan.ui.server import Api, T0

OUT = Path("docs/reports/qi_demo")
WORK = Path("data/qi_demo")
PHRASE = "锦氨在经轴缸上染出来深一块浅一块"           # 三态的同一句客户话
MECH = "为什么会这样，是什么原理？"
SAME = "锦纶氨纶弹力布在经轴缸上染，深一块浅一块"     # 四步：锦纶氨纶 × 经轴染色机
OTHER = "纯锦纶在经轴缸上染，深一块浅一块"            # 四步：锦纶 × 经轴染色机，没人验证过
C4, C2 = "ku:claim:1", "ku:claim:2"                  # 编译出的候选：RPT-031 的 pH 追问、RPT-044 的经轴适用


class Demo:
    def __init__(self, config, resume=None):
        self.api = Api(None, str(config), SimClock(T0))
        self.api.build(resume)
        self.app = self.api.app

    def post(self, path, **p):
        return self.api.call("POST", path, p)

    def visit(self, customer, turns, sales=None):
        """turns：客户自助时是客户的话；业务员陪同时是 (speaker, text)。"""
        sid = self.post("/api/sessions", customer_id=customer, sales_id=sales).id
        for turn in turns:
            speaker, text = turn if sales else ("customer", turn)
            self.post("/api/turn", session_id=sid, speaker=speaker, text=text)
        self.app.tick()
        return sid

    def question(self, family, **refs):
        self.app.tick()
        return next(q for q in self.app.bus.list(family=family)
                    if q.prepared_at is not None and all(q.refs.get(k) == v for k, v in refs.items()))

    def ticket(self, sid):
        return next(r for r in self.app._requirements.values() if sid in r.session_ids)

    def facts(self, sid):
        """一个会话里发生了什么：只读事件日志与会话文件。"""
        evs = [e for e in self.app.events.query() if e.session_id == sid]
        session = json.loads((self.app.run_dir / "sessions" / f"{sid.replace(':', '_')}.json").read_text(encoding="utf-8"))
        rec = [e.payload for e in evs if e.kind == "recommend"]
        match = [e.payload for e in evs if e.kind == "match"]
        return {"session_id": sid, "customer": session["customer_id"], "sales": session["sales_id"],
                "asked": sorted({s for e in evs if e.kind == "ask_hint" for s in e.payload["slots"]}),
                "capabilities_used": sorted({e.payload["capability_id"] for e in evs if e.kind == "capability_used"}),
                "candidates": match[-1]["candidate_ids"] if match else [],
                "recommended": rec[-1]["product_id"] if rec else None,
                "recommend_status": rec[-1]["status"] if rec else None,
                "escalated": any(e.kind == "escalate" for e in evs) or any(
                    sid in e.payload["session_ids"] for e in self.app.events.query(["requirement_created"])),
                "reply": session["replies"][-1]["text"] if session["replies"] else None,
                "status": session["status"]}

    def caps(self, *ids):
        return {c.id: c.status for c in self.app.kb.capabilities() if c.id in ids}


def config_file():
    """离线配置（config/app.yaml），来源换成替身 RAG 的副本。"""
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree("seeds/rag", WORK / "rag")
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config["sources"] = [{"name": f"{kind}（模拟副本）", "kind": kind, "root": str(WORK / "rag" / kind)}
                         for kind in ("public", "internal")]
    path = WORK / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def main():
    config = config_file()
    d = Demo(config)
    app, out = d.app, {"run_id": d.app.run_id}

    # 0 编译替身 RAG（录制的提议，引文核对、定级、指纹照常执行）
    items = yaml.safe_load((WORK / "rag" / "proposals.yaml").read_text(encoding="utf-8"))["items"]
    report = admit(Proposals(items=items).items, app.kb.sources, app.kb)
    out["compile"] = {"admitted": report["admitted"], "dropped": report["dropped"], "duplicates": report["duplicates"]}

    # 三态之前：两位客户自助升级，研发 R02 接单、在第一张单上确认 C4（研发层开工门槛要求 pH），两张单都回问 pH
    prep = []
    for customer in ("customer:C01", "customer:C02"):
        sid = d.visit(customer, [PHRASE, MECH])
        req = d.ticket(sid)
        d.question("accept_requirement", requirement_id=req.id)
        d.post("/api/accept", req_id=req.id, by=req.assigned_rd)
        if not prep:
            reviewed = d.post("/api/qi/review", ku_ids=[C4], by=req.assigned_rd)["reviewed_evidence"]
            d.post("/api/qi/confirm", req_id=req.id, ku_ids=[C4], by=req.assigned_rd, reviewed_evidence=reviewed)
        prep.append({"session_id": sid, "requirement_id": req.id, "rd": req.assigned_rd})
    app.scan()
    grant = d.question("qi_grant", audience="0")
    backs = [e.payload["object_id"] for e in app.events.query(["question_published"]) if e.payload["family"] == "ask_back"]
    out["prep"] = {"tickets": prep, "ask_back": backs, "qi_grant": {"question_id": grant.id, "object_id": grant.object_id,
                                                                   "signer": grant.signer_id}}

    # 三态：同一句客户话、同一份研发资料，唯一的变量是授权状态
    a = d.visit("customer:C03", [PHRASE, MECH])
    k3 = d.post("/api/qi/grant", question_id=grant.id, by=grant.signer_id)
    b = d.visit("customer:C04", [PHRASE, MECH])
    d.post("/api/qi/revoke", cap_id=k3.id, by=grant.signer_id)
    c = d.visit("customer:C01", [PHRASE, MECH])
    mechanism = app.kb._units["ku:mechanism:HY-LV205"].text
    out["three_states"] = [d.facts(sid) | {"state": state, "mechanism_leaked": mechanism in (d.facts(sid)["reply"] or "")}
                           for state, sid in (("A 未授予", a), ("B 已授予 K3", b), ("C 已撤销 K3", c))]
    out["k3"] = k3.id

    # 四步 ① 第一次咨询：客户层没有候选，自动升级；R02 依据 RPT-044 判 LV205 适用（确认 C2），产品经理批准情境
    s1 = d.visit("customer:C02", [SAME])
    req = d.ticket(s1)
    d.question("accept_requirement", requirement_id=req.id)
    reviewed = d.post("/api/qi/review", ku_ids=[C2], by=req.assigned_rd)["reviewed_evidence"]
    d.post("/api/decline", req_id=req.id, by=req.assigned_rd, product_id="HY-LV205", claim_ids=[C2], reviewed_evidence=reviewed,
           reason="已有产品适用：HY-LV205 可用于锦纶氨纶弹力面料的经轴染色")
    scope = d.question("scope_update", requirement_ids=req.id)
    k5 = scope.refs["capability_id"]
    d.post("/api/scope/extend", question_id=scope.id, by="pm:P01", note="（模拟）按研发判断批准锦纶氨纶 × 经轴染色机")
    step1 = d.facts(s1) | {"requirement_id": req.id, "declined_by": req.assigned_rd, "k5": k5,
                           "k5_status": d.caps(k5)[k5], "approved_by": app.kb._caps[k5].approved_by}
    # ② 同类咨询：前台按 K5 确认适用，直接推荐，不进研发
    s2 = d.visit("customer:C03", [SAME])
    used = [e.owner for e in app.ledger.list() if e.reason == "used" and e.ref == s2]
    # ③ 不同的工艺条件：锦纶 × 经轴没人验证过，照常进研发；只说面料、设备不清楚的，只是「可能适用」
    s3 = d.visit("customer:C04", [OTHER])
    s4 = d.visit("customer:C01", [("customer", "锦纶氨纶的布，深一块浅一块"), ("sales", "用的是什么染色设备？"),
                                  ("customer", "设备不清楚")], sales="sales:S01")
    note = app.view_session(s4, "sales:S01").card.note
    # ④ 依据失效与撤销：RPT-044 原文改了 → K5 挂起、觉提出复核；同类咨询回到研发。R02 随后撤销 K5
    report_path = WORK / "rag" / "internal" / "RPT-044.md"
    report_path.write_text(report_path.read_text(encoding="utf-8").replace("三缸试样均无色花", "三缸试样有一缸轻微色花"),
                           encoding="utf-8")
    changed = app.recheck_evidence()
    review = [q.id for q in app.bus.list(family="qi_review") if q.refs["ku_id"] == C2]
    suspended = d.caps(k5)[k5]
    s5 = d.visit("customer:C02", [SAME])
    d.post("/api/qi/revoke", cap_id=k5, by=req.assigned_rd)
    out["four_steps"] = [step1, d.facts(s2) | {"used_by": used}, d.facts(s3), d.facts(s4) | {"note": note},
                         d.facts(s5) | {"evidence_changed": changed, "k5_after_recheck": suspended, "qi_review": review,
                                        "k5_after_revoke": d.caps(k5)[k5]}]

    # 重启：同一运行目录续跑，重放同类问题；授予与撤销、未办完的需求单与积分都还在
    before = {"caps": d.caps(k3.id, k5), "ledger": app.ledger.totals(),
              "open_requirements": sorted(r.id for r in app._requirements.values() if r.status in {"draft", "rd_accepted"})}
    r = Demo(config, resume=app.run_id)
    after = {"caps": r.caps(k3.id, k5), "ledger": r.app.ledger.totals(),
             "open_requirements": sorted(x.id for x in r.app._requirements.values() if x.status in {"draft", "rd_accepted"})}
    s6 = r.visit("customer:C03", [SAME])
    out["restart"] = {"before": before, "after": after, "replay": r.facts(s6)}

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "demo.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "demo.md").write_text(page(out), encoding="utf-8")
    print(page(out))


def page(o):
    yes = lambda x: "是" if x else "否"
    rec = lambda f: f"推荐 {f['recommended']}（{f['recommend_status']}）" if f["recommended"] else (
        "升级到研发" if f["escalated"] else "未推荐")
    lines = ["# 契的决赛主演示（离线，模拟数据）", "",
             f"> 由 `scripts/demo_qi.py` 生成，运行 `{o['run_id']}`；每一行从事件日志与会话文件读出。客户、资料、处置全部为模拟。", "",
             "## 编译", "",
             f"- 候选结论：{'；'.join(a['title'] + '（L' + str(a['level']) + '）' for a in o['compile']['admitted'])}",
             f"- 丢弃（引文与原文不符）：{'；'.join(o['compile']['dropped']) or '无'}；与现有能力相同：{'；'.join(o['compile']['duplicates']) or '无'}",
             f"- 三态之前：{len(o['prep']['tickets'])} 位客户自助升级，研发 {o['prep']['tickets'][0]['rd']} 接单并确认 C4；"
             f"两张单在研发层都缺 pH，觉为客户层提出回问 {len(o['prep']['ask_back'])} 次 → 觉提出把「追问 pH」授予客户层的 `qi_grant`（{o['prep']['qi_grant']['object_id']}，签字人 {o['prep']['qi_grant']['signer']}）", "",
             f"## 三态：同一句「{PHRASE}」", "",
             "| 状态 | 会话 | 客户被追问 | 用到的能力 | 问原理得到 | 含机理原文 |", "|---|---|---|---|---|---|"]
    for f in o["three_states"]:
        lines.append(f"| {f['state']} | {f['session_id']} | {'、'.join(f['asked']) or '无'} | {'、'.join(f['capabilities_used']) or '无'} "
                     f"| {f['reply']} | {yes(f['mechanism_leaked'])} |")
    s1, s2, s3, s4, s5 = o["four_steps"]
    lines += ["", "## 四步：一次判断变成前台的能力", "",
              "| 步骤 | 会话 | 客户层候选 | 结果 | 说明 |", "|---|---|---|---|---|",
              f"| ① 第一次咨询（锦纶氨纶 × 经轴） | {s1['session_id']} | {'、'.join(s1['candidates']) or '无'} | {rec(s1)} "
              f"| {s1['declined_by']} 不立项、判 LV205 适用并确认 C2；能力 {s1['k5']} 由 {s1['approved_by']} 批准，状态 {s1['k5_status']} |",
              f"| ② 同类咨询 | {s2['session_id']} | {'、'.join(s2['candidates'])} | {rec(s2)} | 用到 {'、'.join(s2['capabilities_used'])}；记「被使用」：{'、'.join(s2['used_by'])} |",
              f"| ③ 锦纶 × 经轴 | {s3['session_id']} | {'、'.join(s3['candidates']) or '无'} | {rec(s3)} | 没人验证过的组合不被推广 |",
              f"| ③ 只说面料、设备不清楚（陪同） | {s4['session_id']} | {'、'.join(s4['candidates'])} | {rec(s4)} | 卡片：{s4['note']} |",
              f"| ④ RPT-044 原文改了 | {s5['session_id']} | {'、'.join(s5['candidates']) or '无'} | {rec(s5)} "
              f"| 依据变化 {'、'.join(s5['evidence_changed'])} → K5 {s5['k5_after_recheck']}，复核问题 {'、'.join(s5['qi_review'])}；随后撤销，K5 {s5['k5_after_revoke']} |",
              "", "## 重启", "",
              f"- 重启前后能力状态：{o['restart']['before']['caps']} → {o['restart']['after']['caps']}",
              f"- 积分：{o['restart']['before']['ledger']} → {o['restart']['after']['ledger']}",
              f"- 未办完的需求单：{'、'.join(o['restart']['before']['open_requirements'])} → {'、'.join(o['restart']['after']['open_requirements'])}",
              f"- 重放同类问题（{o['restart']['replay']['session_id']}）：{rec(o['restart']['replay'])}", "",
              "## 边界", "",
              "- `ask` 不带条件：授予 K3 后所有色花客户都会被问 pH，不只锦氨 × 经轴（本轮表达能力的边界）。",
              "- 研发角色是 R02：色花需求单按 L3 转化对照归属派给 R02，所以两份研发报告（模拟）写为 R02 所作；LV205 仍归 R01。"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
