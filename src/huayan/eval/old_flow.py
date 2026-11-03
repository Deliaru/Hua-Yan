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
# V11.4 交叉占用：(岗位, 被谁的事占用) → 哪些工位（CEO-VIEW 3.0）。补问一轮同时占用研发和产品经理。其余工位是本职，照常保留
SEGMENT = {("sales", "pm"): ("业务员答技术问题", "业务员记录需求"), ("pm", "sales"): ("产品经理查资料答复", "产品经理转述"),
           ("pm", "rd"): ("补问一轮",), ("rd", "pm"): ("补问一轮",)}
CROSS = {name for names in SEGMENT.values() for name in names}
# V12.10 第三种做法「有 Agent 没有觉」（Story.tsx 三种做法的口径）：记录、转述、查资料答复由 Agent 起草，人不再做；
# 但没有觉，没人在客户还在时提示该问什么，转述到研发的需求照样缺条件——失真对照里应升级的卡，一次性翻译与业务员转述
# 研发需退回的比例相同（docs/reports/distortion_300：G1 95.1%、G2 95.1%），所以补问、返工与旧流程相同；没有契，研发签过的判断
# 不会替他回答下一单，复用的事照旧流程走到研发。
AGENT = ("业务员记录需求", "产品经理转述", "产品经理查资料答复")


def load_params(default: Path = DEFAULT, override: Path = OVERRIDE) -> dict:
    """合并参数；assumed 列出仍用假设值的参数名，界面据此逐项标「假设」。"""
    params = yaml.safe_load(default.read_text(encoding="utf-8"))
    given = yaml.safe_load(override.read_text(encoding="utf-8")) if override.exists() else {}
    flat = lambda d: {f"minutes.{k}": v for k, v in d.get("minutes", {}).items()} | {
        k: v for k, v in d.items() if k not in ("minutes", "source", "conservative")}
    assumed = sorted(set(flat(params)) - set(flat(given)))
    params["minutes"] |= given.get("minutes", {})
    params |= {k: v for k, v in given.items() if k != "minutes"}
    return params | {"assumed": assumed}


def conservative(params: dict) -> dict:
    """V11.8「按最保守参数」：conservative 里的值盖过同名参数（minutes 逐项盖）。"""
    c = params["conservative"]
    return params | c | {"minutes": params["minutes"] | c.get("minutes", {})}


def first_reply_hours(est: dict, p: dict) -> float:
    """V11.8 旧流程里客户从提问到拿到第一个有效答复（小时，推算）：业务员能答的当场答，答不了的转产品经理查资料再原路回来；
    要研发判断的，经业务员记录、产品经理转述到研发看单，再原路回到客户（六次交接），开工前补问的照推算轮数各往返一次。"""
    m, w = p["minutes"], p["wait_hours"]
    if est["path"] in ("追问中", "自助解决", "交业务员"):
        pm = 0 if est["path"] == "交业务员" else 1 - p["sales_can_answer"]
        return w + m["sales_answer"] / 60 + pm * (2 * w + m["pm_answer"] / 60)
    return 6 * w + (m["sales_record"] + m["pm_relay"] + m["rd_review"]) / 60 + est["old"]["backs"] * (6 * w + m["back_round"] / 60)


def card_loss(card: NeedCard, seeds: Seeds, relay: dict, seed: int) -> dict:
    """在同一张需求卡上重跑 G1 业务员转述：研发收到的需求缺了什么、错了什么（只供 sim/eval）。"""
    phenomenon, told = relay_g1(card, seeds, relay, seed, RuleExtractor(seeds))
    return _gaps(card, seeds, phenomenon, told)


def now_times(story: list[dict]) -> dict:
    """这次实际还发生了几次交叉工位（从门面 case_story 的前情数）：业务员亲自答过客户算一次答技术问题，研发每次退回或回问算一轮补问；
    记录、转述、查资料答复已由觉和产品经理 Agent 接走，不再由人做。V11.7 试样返工也照实数：每录一次未通过的试样算一轮
    （前情对任何视角都写「录入试样结果：未通过」，原因只给内部视角）。V11.8 研发看单也照实数：研发本人没处理过这件事
    （研发签过的判断由契替他回答）就是 0。"""
    return {"业务员答技术问题": int(any(x["kind"] == "turn" and x["role"] == "sales" for x in story)),
            "补问一轮": sum(x["kind"] == "requirement_returned" for x in story),
            "试样返工一轮": sum(x["kind"] == "trial" and "未通过" in x["text"] for x in story),
            "研发看单判断": int(any(x["role"] == "rd" and x["subject"] == "human" for x in story)),
            "业务员记录需求": 0, "产品经理查资料答复": 0, "产品经理转述": 0}


def estimate(route: dict, params: dict, cases: int = 1, loss: dict | None = None, labels: dict | None = None,
             story: list[dict] | None = None) -> dict:
    """route = HuayanApp.route_of 的结果；cases = 合并成一个课题的需求件数（旧流程里各走一遍）；
    loss = card_loss 的结果（没有需求卡时为 None）；labels = 槽位名称，用来写丢掉的条件；
    story = case_story 的前情，有时给交叉工位与试样返工写上这次实际的次数 now_times（本职工位照常保留，等于旧流程次数）。"""
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
    if story is not None:
        now = now_times(story)
        for r in rows:
            r["now_times"] = now.get(r["station"], r["times"])
            r["now_minutes"] = round(r["now_times"] * p["minutes"][STATION[r["station"]][1]], 1)
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
    agent = [r | {"times": 0, "minutes": 0} if r["station"] in AGENT else r for r in rows]
    now = [role for role, cell in route["roles"].items() if cell["state"] == "human" and role != "customer"]
    return {
        "path": path, "cases": cases, "source": "推算", "assumed": p["assumed"], "params_source": p["source"],
        "old": {"stations": rows, "roles": [ROLE_NAME[r] for r in roles], "handoffs": round(handoffs, 2),
                "lost": lost, "backs": round(backs, 2),
                "reworks": round(reworks, 2), "by_role_minutes": by_role, "work_hours": round(work, 2),
                "wait_hours": round(handoffs * p["wait_hours"] + reworks * p["trial_wait_hours"], 1)},
        "now": {"roles": [ROLE_NAME[r] for r in now], "human_steps": route["n_human_steps"]},
        "agent": {"stations": agent, "roles": [ROLE_NAME[r] for r in dict.fromkeys(r["role"] for r in agent if r["times"])],
                  "work_hours": round(sum(r["minutes"] for r in agent) / 60, 2)},
    }


def time_bar(estimates: list[dict], params: dict, role: str) -> dict:
    """V11.4 个人时间构成：现状比例（time_split，假设）按这批事的交叉工位「这次实际次数 / 旧流程次数」缩短，本职补足 100。
    即「如果你的交叉工作都像这几件事」，算式逐工位给出：旧流程几次、这次几次、每次几分钟。"""
    rows = [r for e in estimates for r in e["old"]["stations"]]
    split, segments = params["time_split"][role], []
    for whose, before in split.items():
        if whose == "own":
            continue
        names = SEGMENT[role, whose]
        hit = [r for r in rows if r["station"] in names]
        old, now = sum(r["minutes"] for r in hit), sum(r["now_minutes"] for r in hit)
        steps = [{"station": name, "times": round(sum(r["times"] for r in hit if r["station"] == name), 2),
                  "now_times": sum(r["now_times"] for r in hit if r["station"] == name),
                  "minutes_each": params["minutes"][STATION[name][1]]} for name in names]
        # 这批事里实际补问比旧流程的期望还多时，这一段不缩短（worse 标出），色条不画得比现状更长
        segments.append({"whose": whose, "before": before, "after": round(before * min(now / old, 1), 1) if old else before,
                         "worse": now > old, "old_minutes": round(old, 1), "saved_minutes": round(old - now, 1), "steps": steps})
    return {"role": role, "cases": len(estimates), "own_before": split["own"],
            "own_after": round(100 - sum(x["after"] for x in segments), 1), "segments": segments,
            "source": "推算", "split_source": "假设" if "time_split" in params["assumed"] else params["source"]}
