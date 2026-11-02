"""V11.2（CEO-VIEW C2）：旧流程推算。同一件事如果按原来的流程走（客户 → 业务员记录 → 产品经理转述 → 研发开发 →
产品经理评价 → 业务员开单），要经过几个岗位、几次交接、丢哪些条件、补问与返工几轮、大约多少工时和等待。
流程结构依据访谈与研发提供的流程图；时间与比例是参数（config/old_flow.default.yaml 全部为假设，data/pilot/old_flow.yaml
有同名字段时覆盖）。按期望值推算，不抽签。有需求卡时（只有 sim/eval 有）在这张卡上重跑失真对照 G1 的转述，得出实际丢掉的
条件；没有卡时（真实试用）按参数里的退回比例推算。输入是门面 route_of 的结果，不读业务对象。"""
from __future__ import annotations

from pathlib import Path

import yaml

from huayan.contracts import NeedCard, Seeds
from huayan.eval.distortion import _gaps, relay_g1
from huayan.l1.extract import RuleExtractor

DEFAULT = Path("config/old_flow.default.yaml")
OVERRIDE = Path("data/pilot/old_flow.yaml")
ROLE_NAME = {"customer": "客户", "sales": "业务员", "pm": "产品经理", "rd": "研发"}
# 工位 → (角色, 处理时间参数)；补问一轮由几方合计，角色记在研发名下（是研发发起、研发等）
STATION = {
    "业务员答技术问题": ("sales", "sales_answer"), "产品经理查资料答复": ("pm", "pm_answer"),
    "业务员记录需求": ("sales", "sales_record"), "业务员报价": ("sales", "sales_quote"),
    "产品经理转述": ("pm", "pm_relay"), "研发看单判断": ("rd", "rd_review"), "补问一轮": ("rd", "back_round"),
    "试样返工一轮": ("rd", "rework"), "产品经理评价": ("pm", "pm_eval"), "业务员开单": ("sales", "sales_order"),
}


def load_params(default: Path = DEFAULT, override: Path = OVERRIDE) -> dict:
    """合并参数；assumed 列出仍用假设值的参数名，界面据此逐项标「假设」。"""
    params = yaml.safe_load(default.read_text(encoding="utf-8"))
    given = yaml.safe_load(override.read_text(encoding="utf-8")) if override.exists() else {}
    flat = lambda d: {f"minutes.{k}": v for k, v in d.get("minutes", {}).items()} | {
        k: v for k, v in d.items() if k not in ("minutes", "source")}
    assumed = sorted(set(flat(params)) - set(flat(given)))
    params["minutes"] |= given.get("minutes", {})
    params |= {k: v for k, v in given.items() if k != "minutes"}
    return params | {"assumed": assumed}


def card_loss(card: NeedCard, seeds: Seeds, relay: dict, seed: int) -> dict:
    """在同一张需求卡上重跑 G1 业务员转述：研发收到的需求缺了什么、错了什么（只供 sim/eval）。"""
    phenomenon, told = relay_g1(card, seeds, relay, seed, RuleExtractor(seeds))
    return _gaps(card, seeds, phenomenon, told)


def estimate(route: dict, params: dict, cases: int = 1, loss: dict | None = None, labels: dict | None = None) -> dict:
    """route = HuayanApp.route_of 的结果；cases = 合并成一个课题的需求件数（旧流程里各走一遍）；
    loss = card_loss 的结果（没有需求卡时为 None）；labels = 槽位名称，用来写丢掉的条件。"""
    path, p = route["path"], params
    rate = (1.0 if loss["returned"] else 0.0) if loss else p["return_rate"]
    if path in ("追问中", "自助解决"):
        stations = [("业务员答技术问题", 1), ("产品经理查资料答复", 1 - p["sales_can_answer"])]
    elif path == "交业务员":
        stations = [("业务员答技术问题", 1), ("业务员报价", 1)]
    else:   # 入研、研发不立项、复用、产品机会：都要经过转述到研发；只有入研开发要试样
        develop = path in ("入研", "产品机会")
        stations = [("业务员记录需求", 1), ("产品经理转述", 1), ("研发看单判断", 1),
                    ("补问一轮", rate * (p["caught_by_rd"] if develop else 1))]
        if develop:
            stations += [("试样返工一轮", rate * (1 - p["caught_by_rd"])), ("产品经理评价", 1)]
        stations += [("业务员开单", 1)]
    stations = [(name, n * cases) for name, n in stations if n]
    rows = [{"station": name, "role": STATION[name][0], "times": round(n, 3),
             "minutes": round(n * p["minutes"][STATION[name][1]], 1)} for name, n in stations]
    roles = list(dict.fromkeys(r["role"] for r in rows))
    times = lambda name: sum(r["times"] for r in rows if r["station"] == name)
    backs, reworks = times("补问一轮"), times("试样返工一轮")
    # 交接：客户交给第一个岗位一次；之后每换一个岗位一次（按期望次数）；每轮补问在研发、产品经理、业务员、客户之间往返六次
    handoffs = cases + sum(b["times"] for a, b in zip(rows, rows[1:]) if a["role"] != b["role"]) + 6 * backs
    by_role = {role: round(sum(r["minutes"] for r in rows if r["role"] == role), 1) for role in roles}
    work = sum(r["minutes"] for r in rows) / 60
    lost = None
    if loss:
        names = (labels or {}) | {"phenomenon": "现象"}
        lost = [names.get(s, s) for s in loss["missing"] + loss["wrong"]]
    now = [role for role, cell in route["roles"].items() if cell["state"] == "human" and role != "customer"]
    return {
        "path": path, "cases": cases, "source": "推算", "assumed": p["assumed"], "params_source": p["source"],
        "old": {"stations": rows, "roles": [ROLE_NAME[r] for r in roles], "handoffs": round(handoffs, 2),
                "lost": lost, "backs": round(backs, 2),
                "reworks": round(reworks, 2), "by_role_minutes": by_role, "work_hours": round(work, 2),
                "wait_hours": round(handoffs * p["wait_hours"] + reworks * p["trial_wait_hours"], 1)},
        "now": {"roles": [ROLE_NAME[r] for r in now], "human_steps": route["n_human_steps"]},
    }
