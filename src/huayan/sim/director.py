"""V11.5 导演：游戏模式里扮演外部世界（客户）和这一局没人玩的岗位，按 demo/levels.yaml 的关卡骨架一件件送来事情。
导演不是 Harness 的调度者：觉、总线、hub、Agent、门面照常运行。导演的每个写动作都走 Api.call（与浏览器同一个入口），
读也只用同一套只读接口；做过的动作记在 acted 里，前情据此把这些行标「模拟」。真值（客户心里的需求卡）只在导演这一侧。
模板模式零调用：客户按关卡台词说话，台词说完后只在觉还在追问时由模拟客户（sim/customer.py）按真值回答。"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable

import yaml

from huayan.clock import get_clock
from huayan.contracts import NeedCard
from huayan.domain import correct_product
from huayan.sim.cards import sample_slots
from huayan.sim.customer import SimCustomer

LEVELS = Path("demo/levels.yaml")
VIEWER = "supervisor:M01"        # 导演读前情、需求单用主管视角（L2，看得到需求单上的经过）
PM = "pm:P01"
SHOWN = ("id", "title", "brief", "to", "decide", "mechanism", "point")


def load_levels(path: Path = LEVELS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["levels"]


def fresh(level: int = 0, round_: int = 1, speed: int = 60) -> dict:
    """一局的进度：cases 每关送来的会话，done 导演代办过的动作，acted 导演代谁做了什么（前情标「模拟」）。"""
    return {"level": level, "round": round_, "speed": speed, "paused": False,
            "cases": {}, "done": [], "passed": [], "seen": {}, "acted": []}


class Director:
    def __init__(self, api: Callable[[], object], path: Path, levels: list[dict] | None = None):
        """api：取当前这一局的 Api（重开本关后换成新的一局）；path：进度文件。"""
        self.api, self.path = api, path
        self.levels = levels or load_levels()
        self.state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else fresh()
        self.customers: dict[str, SimCustomer] = {}
        self.error: str | None = None

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    def level(self) -> dict:
        return self.levels[self.state["level"]]

    def view(self) -> dict:
        lv, s = self.level(), self.state
        return {"levels": [{k: x.get(k) for k in SHOWN} | {"ready": "lines" in x} for x in self.levels],
                "level": s["level"], "round": s["round"], "speed": s["speed"], "paused": s["paused"],
                "passed": lv["id"] in s["passed"], "done": s["passed"], "cases": s["cases"].get(str(lv["id"]), []),
                "acted": s["acted"], "error": self.error, "lines": self._lines(lv)}

    def _lines(self, lv: dict) -> list[dict]:
        """客户由人来扮时，各位客户接下来可以说的那句台词（只是提示，可以改写）。"""
        out = []
        for sid in self.state["cases"].get(str(lv["id"]), []):
            customer = self._customer_of(sid)
            view = self._get("/api/session", id=sid, viewer=customer)["view"]
            said = sum(t.speaker == "customer" for t in view.turns)
            if said < len(lv["lines"]):
                out.append({"customer": customer, "session_id": sid, "text": lv["lines"][said]})
        return out

    def _customer_of(self, sid: str) -> str:
        return next(x["customer_id"] for x in self._get("/api/sessions") if x["id"] == sid)

    # 动作与读取：与浏览器同一个入口 ------------------------------------------------------------------
    def _get(self, path: str, **params):
        return self.api().call("GET", path, params)

    def _act(self, actor: str, path: str, **params):
        result = self.api().call("POST", path, params | {"by": actor})
        self.state["acted"].append({"ts": get_clock().now().isoformat(), "actor": actor, "path": path})
        return result

    # 一关 ----------------------------------------------------------------------------------------
    def step(self, present: set[str]) -> bool:
        """导演看一眼：这一关还没送来就送来；缺席的客户、岗位各做该做的一步；到了通关条件就记下。返回这一眼做没做事。
        present = 这一局有人在玩的身份；他们的事留给人做。"""
        lv, s = self.level(), self.state
        key = str(lv["id"])
        if "lines" not in lv or lv["id"] in s["passed"]:
            return False
        acted = False
        if key not in s["cases"]:       # 送来：这一关的每位客户开一段会话；没人扮的客户说出开场白，有人扮的由人自己说
            s["cases"][key] = []
            for customer in [lv["customer"], *lv.get("also", [])]:
                sid = self._act(customer, "/api/sessions", customer_id=customer).id
                s["cases"][key].append(sid)
                if customer not in present:
                    self._act(customer, "/api/turn", session_id=sid, speaker="customer", text=lv["lines"][0])
            acted = True
        for sid in s["cases"][key]:
            customer = self._customer_of(sid)
            if customer not in present:
                acted |= self._customer(lv, sid, customer)
        for i, a in enumerate(lv.get("do", [])):
            if f"{key}:{i}" not in s["done"] and self._do(lv, a, present):
                s["done"].append(f"{key}:{i}")
                acted = True
        if self._passed(lv):
            s["passed"].append(lv["id"])
            acted = True
        self.save()
        return acted

    def _customer(self, lv: dict, sid: str, customer: str) -> bool:
        """客户看化言或业务员刚说了什么（或刚出现的推荐卡），回一句；没有新内容就不说。"""
        view = self._get("/api/session", id=sid, viewer=customer)["view"]
        seen = self.state["seen"]
        card = view.card.product_id if view.card else None
        if view.turns[-1].speaker == "customer" and seen.get(sid) == card:
            return False
        seen[sid] = card
        said = sum(t.speaker == "customer" for t in view.turns)
        if said < len(lv["lines"]):
            text = lv["lines"][said]
        elif view.hints and view.turns[-1].speaker != "customer":
            text = self._sim_customer(lv, sid, customer).reply(view.turns[-1].text)
        else:
            return False
        self._act(customer, "/api/turn", session_id=sid, speaker="customer", text=text)
        return True

    def _sim_customer(self, lv: dict, sid: str, customer: str) -> SimCustomer:
        """台词说完以后觉还在追问：按这位客户心里的真值回答（没写的槽位按种子先验抽，随机数按局与会话定）。"""
        if sid not in self.customers:
            seeds = self.api().app.seeds
            phen = next(p for p in seeds.phenomena if p.id == lv["card"]["phenomenon"])
            rng = random.Random(f"{self.state['round']}:{sid}")
            slots = sample_slots(phen, seeds, rng, lv["card"]["slots"])
            card = NeedCard(id=f"level:{lv['id']}", phenomenon=phen.id, slots=slots, unknown_slots=[], opening_slots=[],
                            customer_id=customer, chem_savvy=False, wants_mechanism=False,
                            truth_product=correct_product(phen.id, slots, seeds.products))
            self.customers[sid] = SimCustomer(card, seeds, rng)
        return self.customers[sid]

    def _do(self, lv: dict, a: dict, present: set[str]) -> bool:
        """缺席岗位的一步模板解法；前提还没出现（还没交到这个岗位、Agent 还没准备好）或有人在玩这个岗位时不做。"""
        sids = self.state["cases"][str(lv["id"])]
        sid = sids[0]
        if a["as"] == "pm":             # 产品经理签产品机会：觉把这几张同类需求提成一个机会、产品经理 Agent 准备好之后
            rids = {self._get("/api/route", id=x, viewer=VIEWER)["requirement_id"] for x in sids}
            q = next((q for q in self._get("/api/questions", viewer=PM) if q.family == "opportunity" and q.status == "open"
                      and q.prepared_at and rids & set(q.refs.get("requirement_ids", "").split(","))), None)
            if PM in present or q is None:
                return False
            self._act(PM, "/api/merge", question_id=q.id, note=a["merge"])
            return True
        if a["as"] == "sales":
            actor = next(x["sales_id"] for x in self._get("/api/sessions") if x["id"] == sid)
            view = self._get("/api/session", id=sid, viewer=actor)["view"] if actor else None
            if actor is None or actor in present or any(t.speaker == "sales" for t in view.turns):
                return False
            self._act(actor, "/api/turn", session_id=sid, speaker="sales", text=a["say"])
            return True
        rid = self._get("/api/route", id=sid, viewer=VIEWER)["requirement_id"]
        req = self._get("/api/requirement", id=rid, viewer=VIEWER).requirement if rid else None
        if req is None or req.assigned_rd in present or req.status != "draft":
            return False
        if "decline" in a:
            self._act(req.assigned_rd, "/api/decline", req_id=rid, product_id=a["decline"]["product"],
                      reason=a["decline"]["reason"])
            return True
        if not any(q.family == "accept_requirement" and q.refs.get("requirement_id") == rid and q.prepared_at
                   for q in self._get("/api/questions", viewer=req.assigned_rd)):
            return False
        self._act(req.assigned_rd, "/api/accept", req_id=rid)
        return True

    def _passed(self, lv: dict) -> bool:
        want = set(lv["pass"])
        return any(x["kind"] in want or f"{x['kind']}:{x['role']}" in want
                   for sid in self.state["cases"][str(lv["id"])]
                   for x in self._get("/api/case-story", id=sid, viewer=VIEWER)["story"])

    # 一局 ----------------------------------------------------------------------------------------
    def next_level(self) -> None:
        """到下一个接上了导演的关（还没接上的跳过）。"""
        if self.level()["id"] not in self.state["passed"]:
            raise ValueError("这一关还没通过")
        later = [i for i in range(self.state["level"] + 1, len(self.levels)) if "lines" in self.levels[i]]
        if not later:
            raise ValueError("后面没有接上的关了")
        self.state["level"] = later[0]
        self.save()

    def play_through(self, upto: int, tick: Callable[[], None]) -> None:
        """全部岗位都由导演代办，从第 1 关跑到第 upto + 1 关开头（重开本关时，新的一局先补上前面几关）。
        tick：导演没事可做时推进一拍（业务时间往前走、觉检查、Agent 准备），产品机会要等觉的定时扫描。"""
        for n in [i for i in range(upto) if "lines" in self.levels[i]]:
            self.state["level"] = n
            for _ in range(30):
                if self.level()["id"] in self.state["passed"]:
                    break
                if not self.step(set()):
                    tick()
            else:
                raise ValueError(f"第 {self.level()['id']} 关自动跑不通，停在这里")
        self.state["level"] = upto
        self.save()
