"""Q7 觉的自进化（离线，全部为模拟数据）：同一批按时间排序的模拟客户分四个窗口跑三组觉。
- frozen：冻结在 W1 的 Jue-K（models/jue_k）；
- evolving：每个窗口结束，从决策记录（decision_rows）取追问行，模拟一侧按需求卡真值补标签（sim.trajectory.ask_label），
  按「家族 × 判断层」过滤（fit 内部 rows_for）后重训，换上新模型进入下一窗口；
- unfiltered：同样重训，但不按层过滤：标签按研发层的必问条件算，各判断层的追问行并成客户层一格训练。
W2 起世界偏离专家先验（sim.shifted_world，λ 如实列出），觉看到的仍是原种子。三组跑同一批客户、同一随机种子。
安全对照：结构层 —— 未授予 K3 时客户层视图里没有 pH，任何模型都提不出 pH 追问；W4 之后授予 K3 再跑一小批，pH 才出现。
校准层 —— 对前置条件已成立的槽位，比较 evolving 与 unfiltered 两种模型在客户层的追问排序与次数。
指标从各组运行目录的事件日志与需求卡算出，报告写进 docs/reports/jue_evolution/。

  uv run python scripts/demo_evolution.py [--n 120] [--lam 0.6] [--seeds 0,1,2,3,4]
"""
import argparse
import json
import pickle
import random
import shutil
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from huayan.clock import SimClock, get_clock
from huayan.contracts import Actor, JueObject, JueState
from huayan.ingest.compile import Proposals, admit
from huayan.jue.jue_k import JueK
from huayan.jue.records import decision_rows, load_records
from huayan.jue.train import fit
from huayan.sim import SimCustomer
from huayan.sim.cards import make_card, sample_slots, shifted_world
from huayan.sim.trajectory import ask_label
from huayan.ui.server import Api, T0

WORK, OUT = Path("data/jue_evolution"), Path("docs/reports/jue_evolution")
WINDOWS = ["W1", "W2", "W3", "W4"]
ARMS = ["frozen", "evolving", "unfiltered"]
C4 = "ku:claim:1"                                    # 编译出的「色花问 pH」候选（RPT-031，归属 R02）
FOCUS = "color_unlevel"
RD = Actor(id="rd:R02", role="rd", name="研发")
CUSTOMER = Actor(id="customer:C01", role="customer", name="客户")


def config_file(work):
    """离线配置：实时觉用 Jue-K；来源换成替身 RAG 的副本（编译出 C4）。"""
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(realtime_model="jue_k", run_root=str(work / "runs"),
                  sources=[{"name": f"{k}（模拟副本）", "kind": k, "root": str(WORK / "rag" / k)} for k in ("public", "internal")])
    path = work / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def make_batch(seeds, n, lam, seed):
    """每窗口 n 张需求卡，一半是色花；偶数号客户自助（L0），奇数号业务员陪同（L1）。"""
    world = shifted_world(seeds, lam, random.Random(seed))
    customers = [a.id for a in seeds.actors if a.role == "customer"]
    batch = {}
    for w in WINDOWS:
        src, rng = (seeds if w == "W1" else world), random.Random(f"{seed}:{w}")
        phen = {p.id: p for p in src.phenomena}
        batch[w] = []
        for i in range(n):
            p = phen[FOCUS] if i % 2 == 0 else rng.choice(src.phenomena)
            batch[w].append(make_card(f"card:{w}:{i}", p, sample_slots(p, src, rng), rng.choice(customers), src, rng))
    return batch


class Arm:
    def __init__(self, name, config, seed, work):
        self.name, self.seed, self.work = name, seed, work
        self.api = Api(None, str(config), SimClock(T0))
        self.api.build()
        self.app = self.api.app
        admit(Proposals(items=yaml.safe_load(Path("seeds/rag/proposals.yaml").read_text(encoding="utf-8"))["items"]).items,
              self.app.kb.sources, self.app.kb)
        self.app.kb.confirm([C4], RD.id)             # 研发已确认 C4：研发层要求 pH（同 demo_qi 第一张单）
        self.snaps = defaultdict(list)               # session_id → [(at, NeedState)]，模拟一侧补标签用
        self.cards, self.windows, self.rows, self.cells = {}, {}, [], {}

    def post(self, path, **p):
        return self.api.call("POST", path, p)

    def turn(self, sid, speaker, text):
        s = self.post("/api/turn", session_id=sid, speaker=speaker, text=text)
        self.snaps[sid].append((get_clock().now(), s.need.model_copy(deep=True)))
        return s

    def visit(self, card, window, accompanied):
        sales = self.app.config["customer_sales"][card.customer_id] if accompanied else None
        customer = SimCustomer(card, self.app.seeds, random.Random(f"{self.seed}:{card.id}"))
        sid = self.post("/api/sessions", customer_id=card.customer_id, sales_id=sales).id
        self.cards[sid], self.windows[sid] = card, window
        s = self.turn(sid, "customer", customer.opening())
        for _ in range(8):
            if s.status != "open" or not s.hints:
                break
            ask = s.hints[0].ask_text
            if sales:
                self.turn(sid, "sales", ask)
            s = self.turn(sid, "customer", customer.reply(ask))
        if s.status == "open":
            self.post("/api/recommend", session_id=sid)
        self.app.tick()
        q = next((q for q in self.app.bus.list(family="escalate") if q.object_id == f"session:{sid}"), None)
        if sales and q is not None:                  # 觉提出升级，业务员签字
            self.post("/api/escalate", session_id=sid, by=sales)

    def label(self, rows, required_of):
        """追问行补标签：取打分时刻的槽位状态，按需求卡真值算事后有用性（ask_label）。"""
        products = self.app.seeds.products
        out = []
        for r in rows:
            sid = r["object_id"][len("slot:"):].rsplit("/", 1)[0]
            snaps = self.snaps.get(sid)
            if r["family"] != "ask_slot" or not snaps:
                continue
            need = snaps[max(bisect_right([at.isoformat() for at, _ in snaps], r["at"]) - 1, 0)][1]
            card = self.cards[sid]
            out.append(r | {"label": ask_label(need, card, r["attrs"]["slot"], products, required_of(card.phenomenon)),
                            "window": self.windows[sid]})
        return out

    def retrain(self, window, templates):
        rows = [r for r in decision_rows(load_records(self.app.run_dir), self.app.events)
                if r["family"] == "ask_slot" and self.windows.get(r["object_id"][5:].rsplit("/", 1)[0]) == window]
        view = {lvl: {p.id: p.required_slots for p in self.app.kb.view(a).phenomena} for lvl, a in ((0, CUSTOMER), (3, RD))}
        if self.name == "evolving":     # 按层：标签只看客户层视图里的必问条件（本轮业务员层视图与客户层相同）
            labeled = self.label(rows, lambda phen: view[0][phen])
        else:                           # 不过滤：研发层的必问条件也当成客户层的结果，各层并成一格
            labeled = [r | {"judge_level": 0, "level": 0, "attrs": r["attrs"] | {"judge_level": 0}}
                       for r in self.label(rows, lambda phen: view[3][phen])]
        self.rows += labeled
        out = self.work / "models" / self.name / window
        self.cells[window] = fit(self.rows, templates, out)
        self.app.jue_realtime = merged(self.app.jue_realtime, out, templates, self.app.meter, pooled=self.name == "unfiltered")


def merged(previous, out, templates, meter, pooled):
    """新训练没有赢过规则的格沿用上一个模型的格（不退回规则）；不过滤组的并格模型同时用于客户层与业务员层。
    合并结果写回 out，evolving 组 W4 的目录（data/jue_evolution/seed0/models/evolving/W4）就是进化后的觉。"""
    new = JueK(out, templates, "realtime", meter)
    models, columns = previous.models | new.models, previous.columns | new.columns
    if pooled and "ask_slot|L0" in new.models:
        models["ask_slot|L1"], columns["ask_slot|L1"] = new.models["ask_slot|L0"], new.columns["ask_slot|L0"]
    new.models, new.columns = models, columns
    with (out / "model.pkl").open("wb") as stream:      # 落盘合并后的模型，回测（Q7.5）直接加载
        pickle.dump({"models": models}, stream)
    features = json.loads((out / "features.json").read_text(encoding="utf-8"))
    (out / "features.json").write_text(json.dumps(features | {"columns": columns}, ensure_ascii=False, indent=2), encoding="utf-8")
    return new


def grant_k3(app):
    """W4 之后：研发把「色花问 pH」授予客户层（K3，等同 demo_qi 的签字结果）。"""
    source = app.kb._caps[next(c.id for c in app.kb.capabilities() if C4 in c.based_on and c.form == "ask")]
    return app.kb.grant(source.model_copy(update={"id": app.kb.next_cap_id(), "audience": 0, "granted_by": RD.id,
                                                  "approved_by": None, "status": "active", "at": get_clock().now()}))


def window_metrics(arm, window, rd_required, l0_required):
    """全部从事件日志与需求卡算：问了什么（ask_hint 之后有人接话）、推荐、升级时的已知条件。"""
    by_sid = defaultdict(list)
    for e in arm.app.events.query():
        if e.session_id and arm.windows.get(e.session_id) == window:
            by_sid[e.session_id].append(e)
    asks, ph_l0, escalated, complete, complete_l0, solved, rd_calls, handled, wrong = 0, 0, 0, 0, 0, 0, 0, 0, 0
    for sid, evs in by_sid.items():
        card = arm.cards[sid]
        self_service = arm.app._sessions[sid].sales_id is None
        for i, e in enumerate(evs):
            if e.kind == "ask_hint" and e.payload["slots"] and any(x.kind == "turn" for x in evs[i + 1:]):
                asks += 1
                ph_l0 += self_service and e.payload["slots"][0] == "bath_ph"
        esc = next((e.payload for e in evs if e.kind == "escalate"), None)
        rec = next((e.payload for e in reversed(evs) if e.kind == "recommend"), None)
        if esc is not None:
            escalated += 1
            missing = [s for s in rd_required[card.phenomenon] if s not in esc["known"]]
            complete += not missing
            complete_l0 += all(s in esc["known"] for s in l0_required[card.phenomenon])
            rd_calls += 1 + len(missing)            # 立项判断一次 + 每缺一项必问条件回问一次
            solved += 1                              # 口径：进了研发即视为研发补齐信息后给出答案
            handled += card.truth_product is None    # 该升级的升级了
        elif rec is not None:
            solved += rec["product_id"] == card.truth_product
            handled += rec["product_id"] == card.truth_product
            wrong += rec["product_id"] != card.truth_product
    n = len(by_sid)
    return {"sessions": n, "avg_asks": round(asks / n, 3), "escalated": escalated,
            "complete_rate": round(complete / escalated, 3) if escalated else None,
            "complete_l0_rate": round(complete_l0 / escalated, 3) if escalated else None,
            "handled_rate": round(handled / n, 3), "wrong_rate": round(wrong / n, 3),
            "rd_return_rate": round(1 - complete / escalated, 3) if escalated else None,
            "rd_per_solved": round(rd_calls / solved, 3) if solved else None, "solved": solved, "l0_ph_asks": ph_l0}


def calibration(evolving, unfiltered, probe):
    """同一组客户层槽位对象，两种模型的追问分数：排序一致性（Spearman）、平均差、过阈值的个数。"""
    threshold = evolving.app.config["thresholds"]["ask_jue_k"]
    a = {d.object_id: d.p_need for d in evolving.app.jue_realtime.propose(probe).decisions if d.family == "ask_slot"}
    b = {d.object_id: d.p_need for d in unfiltered.app.jue_realtime.propose(probe).decisions if d.family == "ask_slot"}
    keys = sorted(k for k in a if a[k] is not None and b.get(k) is not None)
    x, y = np.array([a[k] for k in keys]), np.array([b[k] for k in keys])
    rank = lambda v: np.argsort(np.argsort(v))
    rho = float(np.corrcoef(rank(x), rank(y))[0, 1]) if len(keys) > 2 and x.std() and y.std() else None
    return {"objects": len(keys), "spearman": None if rho is None else round(rho, 3),
            "mean_abs_diff": round(float(np.abs(x - y).mean()), 4) if keys else None,
            "over_threshold": {"evolving": int((x >= threshold).sum()), "unfiltered": int((y >= threshold).sum())}}


def run(n, lam, seed):
    work = WORK / f"seed{seed}"
    work.mkdir(parents=True)
    config = config_file(work)
    arms = {name: Arm(name, config, seed, work) for name in ARMS}
    seeds = arms["frozen"].app.seeds
    templates = arms["frozen"].app.config["templates_dir"]
    batch = make_batch(seeds, n, lam, seed)
    rd_required = {p.id: p.required_slots for p in arms["frozen"].app.kb.view(RD).phenomena}
    l0_required = {p.id: p.required_slots for p in arms["frozen"].app.kb.view(CUSTOMER).phenomena}
    report = {"seed": seed, "rd_required": rd_required, "customer_required": l0_required,
              "windows": {}, "cells": {}, "calibration": {}}
    for w in WINDOWS:
        for arm in arms.values():
            for i, card in enumerate(batch[w]):
                arm.visit(card, w, accompanied=i % 2 == 1)
        report["windows"][w] = {name: window_metrics(arm, w, rd_required, l0_required) for name, arm in arms.items()}
        probe_rows = [r for r in decision_rows(load_records(arms["evolving"].app.run_dir), arms["evolving"].app.events)
                      if r["family"] == "ask_slot" and r["judge_level"] == 0
                      and arms["evolving"].windows.get(r["object_id"][5:].rsplit("/", 1)[0]) == w]
        probe = JueState(at=get_clock().now(), mode="realtime", objects={
            f"{r['object_id']}@{k}": JueObject(object_id=f"{r['object_id']}@{k}", object_type="slot", attrs=r["attrs"])
            for k, r in enumerate(probe_rows)})
        report["calibration"][w] = calibration(arms["evolving"], arms["unfiltered"], probe)
        for name in ("evolving", "unfiltered"):
            arms[name].retrain(w, templates)
            report["cells"].setdefault(name, {})[w] = {c: s["scored_by"] for c, s in arms[name].cells[w].items()}
    # 结构层：授予 K3 之后再跑一小批色花客户（全部自助），客户层的 pH 追问才出现
    k3 = [c for c in batch["W4"] if c.phenomenon == FOCUS][: n // 3]
    report["after_k3"] = {}
    for name, arm in arms.items():
        grant_k3(arm.app)
        for card in k3:
            arm.visit(card.model_copy(update={"id": card.id + ":k3"}), "K3", accompanied=False)
        report["after_k3"][name] = window_metrics(arm, "K3", rd_required, l0_required)
    report["runs"] = {name: str(arm.app.run_dir) for name, arm in arms.items()}
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--lam", type=float, default=0.6)
    ap.add_argument("--seeds", default="0,1,2,3,4")
    args = ap.parse_args()
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    shutil.copytree("seeds/rag", WORK / "rag")
    runs = [run(args.n, args.lam, int(seed)) for seed in args.seeds.split(",")]
    report = {"lambda": args.lam, "n_per_window": args.n, "seeds": [r["seed"] for r in runs], "runs": runs}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evolution.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "README.md").write_text(page(report), encoding="utf-8")
    print(page(report))


METRICS = [("handled_rate", "正确处理率", 1), ("wrong_rate", "错误推荐率", -1), ("avg_asks", "平均追问", 0),
           ("complete_l0_rate", "升级时客户层视图内必问完整率", 1), ("complete_rate", "升级时研发视图必问完整率", 1),
           ("rd_per_solved", "研发判断 / 解决", -1)]


def _diff(runs, w, a, b, key):
    """各种子上 a − b 的平均与范围；None（该窗口没有升级）不计。"""
    d = [r["windows"][w][a][key] - r["windows"][w][b][key] for r in runs
         if r["windows"][w][a][key] is not None and r["windows"][w][b][key] is not None]
    return "—" if not d else f"{np.mean(d):+.3f}［{min(d):+.3f}，{max(d):+.3f}］"


def page(r):
    runs = r["runs"]
    mean = lambda w, arm, key: (lambda v: "—" if not v else f"{np.mean(v):.3f}")(
        [x["windows"][w][arm][key] for x in runs if x["windows"][w][arm][key] is not None])
    lines = ["# 觉的自进化（离线，模拟数据）", "",
             f"> 由 `scripts/demo_evolution.py` 生成：世界与客户是模拟的，W2 起世界偏离专家先验的程度 λ = {r['lambda']} 是假设，"
             f"标签来自模拟世界的结果（需求卡真值）。每窗口 {r['n_per_window']} 位客户（一半色花；偶数号客户自助、奇数号业务员陪同），"
             f"种子 {', '.join(map(str, r['seeds']))}，每个种子三组跑同一批客户。",
             "> frozen：冻结在 W1 的觉；evolving：每窗口后按「家族 × 判断层」过滤重训；"
             "unfiltered：不按层过滤（研发层的必问条件当客户层的标签，各判断层并成一格）。",
             "> 口径：正确处理 = 推荐了需求卡真值的产品，或该升级的升级了；错误推荐 = 推荐的产品不是真值；"
             "研发判断 = 立项判断一次 + 每缺一项研发必问条件回问一次，进了研发即算解决。", "",
             "## 各组均值（按种子平均）", "",
             "| 窗口 | 组 | " + " | ".join(name for _, name, _ in METRICS) + " |", "|---|---|" + "---|" * len(METRICS)]
    for w in WINDOWS:
        for arm in ARMS:
            lines.append(f"| {w} | {arm} | " + " | ".join(mean(w, arm, k) for k, _, _ in METRICS) + " |")
    lines += ["", "## 进化有没有用：evolving − frozen（各种子平均［最小，最大］）", "",
              "| 窗口 | " + " | ".join(name for _, name, _ in METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for w in WINDOWS:
        lines.append(f"| {w} | " + " | ".join(_diff(runs, w, "evolving", "frozen", k) for k, _, _ in METRICS) + " |")
    cells = {w: sum(x["cells"]["evolving"][w].get(c) == "jue_k" for x in runs for c in ("ask_slot|L0", "ask_slot|L1"))
             for w in WINDOWS}
    lines += ["", "每窗口结束重训后，evolving 组换上 Jue-K 的追问格数（L0、L1 两格 × 种子数 "
              f"{len(runs) * 2}）：" + "，".join(f"{w} {n}" for w, n in cells.items()) + "。没胜过规则的格沿用上一个模型"
              "（W1 是 models/jue_k：ask_slot|L1 已是 Jue-K，ask_slot|L0 是规则）。W1 结束训练的模型从 W2 起使用。", "",
              "## 不按层过滤会怎样：unfiltered − evolving", "",
              "| 窗口 | " + " | ".join(name for _, name, _ in METRICS) + " |", "|---|" + "---|" * len(METRICS)]
    for w in WINDOWS:
        lines.append(f"| {w} | " + " | ".join(_diff(runs, w, "unfiltered", "evolving", k) for k, _, _ in METRICS) + " |")
    ph = {arm: sum(x["windows"][w][arm]["l0_ph_asks"] for x in runs for w in WINDOWS) for arm in ARMS}
    k3 = {arm: sum(x["after_k3"][arm]["l0_ph_asks"] for x in runs) for arm in ARMS}
    cal = [c for x in runs for w, c in x["calibration"].items() if w != "W1" and c["spearman"] is not None]
    lines += ["", "## 安全对照", "",
              "**结构层**：W1–W4 客户自助会话里的 pH 追问次数（全部种子合计）："
              + "，".join(f"{a} {n}" for a, n in ph.items()) + "；授予 K3 之后同一批色花客户："
              + "，".join(f"{a} {n}" for a, n in k3.items()) + "。未授予时客户层视图里没有 pH，`ask_slot` 的前置条件不成立，"
              "不论训练时过滤与否、模型分数多高都提不出来；客户层能问什么由视图决定，学习改不了。",
              "", f"**校准层**：重训后（W2–W4）同一组客户层追问对象上，两种模型的排序一致性（Spearman）平均 "
              f"{np.mean([c['spearman'] for c in cal]):.3f}，过阈值个数 evolving 平均 {np.mean([c['over_threshold']['evolving'] for c in cal]):.1f}、"
              f"unfiltered 平均 {np.mean([c['over_threshold']['unfiltered'] for c in cal]):.1f}。"
              "按层过滤保护的是校准：研发层的结果不改变客户层追问的排序与次数；上表「不按层过滤会怎样」是它对结果的影响。",
              "", "研发为同一类需求反复回问 pH 的那些单，在按层过滤下不进入客户层追问的训练，只作为觉提出 `qi_grant`"
              "（把「问 pH」授予客户层）的理由，由研发签字决定。", "",
              "授予 K3 之后同一批色花客户（各种子平均）：", "",
              "| 组 | 平均追问 | 客户层 pH 追问（合计） | 正确处理率 | 错误推荐率 |", "|---|---|---|---|---|"]
    for arm in ARMS:
        a = [x["after_k3"][arm] for x in runs]
        lines.append(f"| {arm} | {np.mean([v['avg_asks'] for v in a]):.2f} | {k3[arm]} | "
                     f"{np.mean([v['handled_rate'] for v in a]):.3f} | {np.mean([v['wrong_rate'] for v in a]):.3f} |")
    after = {arm: {"wrong": np.mean([x["after_k3"][arm]["wrong_rate"] for x in runs])} for arm in ARMS} | {
        "n": sum(x["after_k3"]["frozen"]["sessions"] for x in runs)}
    l0 = {arm: sum(x["cells"][arm]["W4"].get("ask_slot|L0") == "jue_k" for x in runs) for arm in ("evolving", "unfiltered")}
    w4 = {k: [x["windows"]["W4"]["evolving"][k] - x["windows"]["W4"]["frozen"][k] for x in runs]
          for k in ("handled_rate", "wrong_rate", "avg_asks")}
    lines += ["", "## 结论（照数据写）", "",
              f"- **进化没有让觉「更快问全」**：两种完整率三组完全相同——客户层视图内的必问条件由前置条件保证一定会问，"
              "研发视图的必问条件（pH）被客户层视图挡住，学习两头都改变不了。",
              f"- 进化的作用很小：W4 evolving 比 frozen 正确处理率 {np.mean(w4['handled_rate']):+.3f}、错误推荐率 "
              f"{np.mean(w4['wrong_rate']):+.3f}，代价是平均多问 {np.mean(w4['avg_asks']):+.2f} 次；"
              f"{sum(d == 0 for d in w4['handled_rate'])} / {len(runs)} 个种子上正确处理率没有变化。",
              f"- 客户层追问格（ask_slot|L0）到 W4 换上模型的种子数：evolving {l0['evolving']} / {len(runs)}，"
              f"unfiltered {l0['unfiltered']} / {len(runs)}。按层过滤后客户层这一格数据少，没胜过规则；不过滤的合并格数据多，更容易胜出。",
              "- **未授予时，不过滤也学不到客户层不该问的东西**：pH 不在客户层视图里，结构上提不出。",
              f"- **授予后，不过滤会少问已授予的条件**：客户层 pH 追问 unfiltered {k3['unfiltered']} 次、evolving {k3['evolving']} 次；"
              f"错误推荐率 unfiltered {after['unfiltered']['wrong']:.3f}、evolving {after['evolving']['wrong']:.3f}"
              f"（{len(runs)} 个种子共 {after['n']} 位色花客户）。研发层的结果混进客户层的训练，会改变客户层对已授予条件的排序；"
              "按层过滤守住的是这一点，代价是客户层这一格数据少、学得慢。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
