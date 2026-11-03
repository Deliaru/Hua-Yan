"""V11.5 导演：游戏模式里扮演外部世界（客户）和这一局没人玩的岗位，按 demo/levels.yaml 的关卡骨架一件件送来事情。
导演不是 Harness 的调度者：觉、总线、hub、Agent、门面照常运行。导演的每个写动作都走 Api.call（与浏览器同一个入口），
读也只用同一套只读接口；做过的动作记在 acted 里，前情据此把这些行标「模拟」。真值（客户心里的需求卡）只在导演这一侧。
模板模式零调用：客户按关卡台词说话，台词说完后只在觉还在追问、或研发回问时由模拟客户（sim/customer.py）按真值回答。
V11.7：外部世界还给出试样结果（关卡写明哪些条件不问清就会失败）和资料改版（改这一局的资料副本，再请系统重取依据）。"""
from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import Callable

import yaml

from huayan.clock import get_clock
from huayan.contracts import NeedCard
from huayan.domain import correct_product, load_seeds
from huayan.events import EventLog
from huayan.ingest.compile import Proposals, admit
from huayan.ingest.folder import FolderSource
from huayan.knowledge import AuditLog, KnowledgeBase
from huayan.sim.cards import sample_slots
from huayan.sim.customer import SimCustomer

LEVELS = Path("demo/levels.yaml")
PROPOSALS = Path("seeds/rag/proposals.yaml")    # 录制的编译提议（模拟），代替模型编译
VIEWER = "supervisor:M01"        # 导演读前情、需求单用主管视角（L2，看得到需求单上的经过）
PM = "pm:P01"
SHOWN = ("id", "title", "brief", "to", "decide", "mechanism", "point")


def load_levels(path: Path = LEVELS) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["levels"]


def prepare_round(config_path: str, run_dir: Path) -> Path:
    """开一局、应用还没起来时：内部资料复制一份给这一局（第 9 关改的是副本），再照 scripts/compile_qi.py 把录制的
    编译提议导入成待研发审的候选（第 4 关）。返回这一局的配置；已经有了就照用（服务重启后续上这一局）。"""
    path = run_dir / "app.yaml"
    if path.exists():
        return path
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    for i, s in enumerate(config["sources"]):
        if s["kind"] == "internal":
            s["root"] = str(shutil.copytree(s["root"], run_dir / "sources" / str(i)))
    config["qi_state"] = str(run_dir / "qi_state.json")
    kb = KnowledgeBase.from_seeds(load_seeds(config["seeds_dir"]), EventLog(), AuditLog(), state_path=config["qi_state"])
    kb.sources = [FolderSource(s["name"], s["kind"], s["root"], s.get("level"), kb._doc_levels) for s in config["sources"]]
    admit(Proposals(items=yaml.safe_load(PROPOSALS.read_text(encoding="utf-8"))["items"]).items, kb.sources, kb)
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


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
        return {"levels": [{k: x.get(k) for k in SHOWN} | {"ready": "pass" in x} for x in self.levels],
                "level": s["level"], "round": s["round"], "speed": s["speed"], "paused": s["paused"],
                "passed": lv["id"] in s["passed"], "done": s["passed"], "cases": s["cases"].get(str(lv["id"]), []),
                "acted": s["acted"], "error": self.error, "lines": self._lines(lv), "notes": self._notes(lv)}

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

    def _notes(self, lv: dict) -> list[dict]:
        """研发由人来扮时，外部世界给他的试样结果（只是提示，录入照常在研发面上做）。"""
        out = []
        for sid in self.state["cases"].get(str(lv["id"]), []) if "trial" in lv else []:
            req = self._req(sid)
            if req and req.status == "rd_confirmed":
                result, _, missing = self._trial(lv, req)
                labels = "、".join(s.label for s in self.api().app.seeds.slots if s.id in missing)
                out.append({"who": req.assigned_rd, "text": "这一单的试样做完了：通过。" if result == "pass" else
                            f"这一单的试样做完了：未通过，「{labels}」没问到。录入时原因选「需求条件缺失」并勾上「{labels}」。"})
        return out

    def _trial(self, lv: dict, req) -> tuple[str, str, list[str]]:
        """世界规律（关卡写死）：needs 里的条件不在需求单上，试样就因需求条件缺失失败。"""
        missing = [s for s in lv["trial"]["needs"] if s not in req.known_slots]
        return ("fail", "requirement", missing) if missing else ("pass", "none", [])

    def _req(self, sid: str):
        rid = self._get("/api/route", id=sid, viewer=VIEWER)["requirement_id"]
        return self._get("/api/requirement", id=rid, viewer=VIEWER).requirement if rid else None

    def _open(self, family: str) -> dict:
        """各岗位收件箱里还开着的这一类决策 {问题编号: 问题}。"""
        return {q.id: q for a in self.api().app.seeds.actors if a.role in ("sales", "pm", "rd", "supervisor")
                for q in self._get("/api/questions", viewer=a.id) if q.family == family}

    def _story(self, sid: str) -> list[dict]:
        return self._get("/api/case-story", id=sid, viewer=VIEWER)["story"]

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
        if "pass" not in lv or lv["id"] in s["passed"]:
            return False
        acted = False
        if key not in s["cases"]:       # 送来：这一关的每位客户开一段会话；没人扮的客户说出开场白，有人扮的由人自己说
            s["cases"][key] = []
            for customer in [lv["customer"], *lv.get("also", [])] if "customer" in lv else []:
                sid = self._act(customer, "/api/sessions", customer_id=customer).id
                s["cases"][key].append(sid)
                if customer not in present:
                    self._act(customer, "/api/turn", session_id=sid, speaker="customer", text=lv["lines"][0])
            if "revise" in lv:
                self._revise(lv["revise"])
            s["seen"][key] = [q for want in lv["pass"] if want.startswith("settled:")
                              for q in self._open(want.removeprefix("settled:"))]
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
        if view.turns[-1].speaker == "customer" and seen.get(sid) == card and not view.asks:
            return False
        seen[sid] = card
        said = sum(t.speaker == "customer" for t in view.turns)
        if said < len(lv["lines"]):
            text = lv["lines"][said]
        elif view.asks:                 # 研发回问：客户在自助页按心里的真值回答
            text = self._sim_customer(lv, sid, customer).reply(view.asks[0].ask_text)
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
        """缺席岗位的一步模板解法；前提还没出现（还没交到这个岗位、Agent 还没准备好、客户还没答回问）或有人在玩这个岗位时不做。
        同一个动作要做两次（再确认、再试样）就在关卡里写两遍，前提保证它们一前一后。"""
        sids = self.state["cases"][str(lv["id"])]
        if "merge" in a or "scope" in a:
            # 产品经理：签产品机会（觉合并、Agent 准备之后）；批准这张单上研发判定的适用范围（报告导入的研发层适用与
            # 不立项给客户层的适用各一条，都准备好了一起批）
            rids = {self._get("/api/route", id=x, viewer=VIEWER)["requirement_id"] for x in sids}
            qs = [q for q in self._get("/api/questions", viewer=PM) if q.status == "open"
                  and q.family == ("opportunity" if "merge" in a else "scope_update")
                  and rids & set(q.refs.get("requirement_ids", "").split(","))]
            if PM in present or not qs or not all(q.prepared_at for q in qs):
                return False
            for q in qs[:1] if "merge" in a else qs:
                self._act(PM, "/api/merge" if "merge" in a else "/api/scope/extend", question_id=q.id,
                          note=a.get("merge") or a["scope"])
            return True
        if "review" in a:                   # 研发复核依据已变化的结论：读本次原文，签字保留
            q = next((q for q in self._open("qi_review").values() if q.id in self.state["seen"][str(lv["id"])]
                      and q.prepared_at and q.signer_id not in present), None)
            if q is None:
                return False
            review = self._act(q.signer_id, "/api/qi/review", ku_ids=[q.refs["ku_id"]])
            self._act(q.signer_id, "/api/resolve", question_id=q.id, action="sign", note=a["review"],
                      reviewed_evidence=review["reviewed_evidence"])
            return True
        sid = sids[0]
        if a["as"] == "sales":
            actor = next(x["sales_id"] for x in self._get("/api/sessions") if x["id"] == sid)
            view = self._get("/api/session", id=sid, viewer=actor)["view"] if actor else None
            if actor is None or actor in present or any(t.speaker == "sales" for t in view.turns):
                return False
            self._act(actor, "/api/turn", session_id=sid, speaker="sales", text=a["say"])
            return True
        req = self._req(sid)                # 其余是需求单上指派研发的动作
        if req is None or req.assigned_rd in present:
            return False
        rd, rid = req.assigned_rd, req.id
        prepared = lambda family: any(q.family == family and q.refs.get("requirement_id") == rid and q.prepared_at
                                      and q.status == "open" for q in self._get("/api/questions", viewer=rd))
        story = [x["kind"] for x in self._story(sid)]
        if "decline" in a and req.status == "draft":
            d = a["decline"]
            params = {"req_id": rid, "reason": d["reason"], "product_id": d.get("product")}
            if "claims" in d:              # 以这份报告编译出的本人候选为依据，审过原文、随不立项一起签字确认
                ids = [c.id for c in self._get("/api/claims", req_id=rid, viewer=rd)
                       if c.owner == rd and any(e.startswith(f"{d['claims']}#") for e in c.evidence)]
                review = self._act(rd, "/api/qi/review", ku_ids=ids)
                params |= {"claim_ids": ids, "reviewed_evidence": review["reviewed_evidence"]}
            self._act(rd, "/api/decline", **params)
            return True
        if "accept" in a and req.status == "draft" and prepared("accept_requirement"):
            self._act(rd, "/api/accept", req_id=rid)
            return True
        if "confirm" in a and req.status == "rd_accepted" and prepared("confirm_translation") \
                and not self._get("/api/session", id=sid, viewer=self._customer_of(sid))["view"].asks:
            self._act(rd, "/api/confirm", req_id=rid)
            return True
        if "trial" in a and req.status == "rd_confirmed" and story.count("trial") < story.count("requirement_translated"):
            result, cause, missing = self._trial(lv, req)
            self._act(rd, "/api/trial", req_id=rid, result=result, cause=cause, missing_slots=missing)
            return True
        if "rework" in a and req.status == "rd_confirmed" and prepared("trial_rework"):
            self._act(rd, "/api/rework", req_id=rid)
            return True
        return False

    def _revise(self, r: dict) -> None:
        """外部世界：资料来源改版。改这一局的资料副本，再请系统重取依据比指纹（与浏览器同一个入口）。"""
        source = next(s for s in self.api().app.kb.sources if r["doc"] in s.list_docs())
        path = source.root / f"{r['doc']}.md"
        path.write_text(path.read_text(encoding="utf-8").replace(r["old"], r["new"]), encoding="utf-8")
        self._act("system:source", "/api/sources/recheck")

    def _passed(self, lv: dict) -> bool:
        """通关条件，任一条成立：前情里出现 kind（或 kind:role；kind~文字 还要求这一行含这段文字）；
        settled:<决策> = 送来时开着的这类决策已经有人处理了。"""
        def hit(want, x):
            kind, _, text = want.partition("~")
            return kind in (x["kind"], f"{x['kind']}:{x['role']}") and text in x["text"]
        key = str(lv["id"])
        for want in lv["pass"]:
            if want.startswith("settled:") and set(self.state["seen"][key]) - set(self._open(want.removeprefix("settled:"))):
                return True
        return any(hit(want, x) for sid in self.state["cases"][key] for x in self._story(sid) for want in lv["pass"])

    # 一局 ----------------------------------------------------------------------------------------
    def next_level(self) -> None:
        """到下一个接上了导演的关（还没接上的跳过）。"""
        if self.level()["id"] not in self.state["passed"]:
            raise ValueError("这一关还没通过")
        later = [i for i in range(self.state["level"] + 1, len(self.levels)) if "pass" in self.levels[i]]
        if not later:
            raise ValueError("后面没有接上的关了")
        self.state["level"] = later[0]
        self.save()

    def play_through(self, upto: int, tick: Callable[[], None]) -> None:
        """全部岗位都由导演代办，从第 1 关跑到第 upto + 1 关开头（重开本关时，新的一局先补上前面几关）。
        tick：导演没事可做时推进一拍（业务时间往前走、觉检查、Agent 准备），产品机会要等觉的定时扫描。"""
        for n in [i for i in range(upto) if "pass" in self.levels[i]]:
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
