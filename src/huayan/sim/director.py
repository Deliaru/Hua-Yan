"""V11.5 导演：游戏模式里扮演外部世界（客户）和这一局没人玩的岗位，按 demo/levels.yaml 的骨架送来事情。
V11.12：各岗位自己的业务开局一起送来，关卡（一条完整的业务流程）一步过了才送下一步；路演局里各岗位的事都留给人。
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
VIEWER = "supervisor:M01"        # 导演读前情、需求单用主管视角（L2，看得到需求单上的经过）
PM = "pm:P01"
SHOWN = ("id", "kind", "title", "brief", "to", "decide", "mechanism", "point")
ROLE = {"customer": "客户", "sales": "业务员", "pm": "产品经理", "rd": "研发"}


def load_levels(path: Path = LEVELS) -> list[dict]:
    """业务按岗位编号（研发业务 1……），关卡按顺序编号（关卡第 1 步……）。"""
    data, count, out = yaml.safe_load(path.read_text(encoding="utf-8")), {}, []
    for x in data["business"]:
        count[x["to"]] = count.get(x["to"], 0) + 1
        out.append(x | {"id": f"{ROLE[x['to']]}业务 {count[x['to']]}", "kind": "business"})
    return out + [x | {"id": f"关卡第 {i} 步", "kind": "stage"} for i, x in enumerate(data["stage"], 1)]


def prepare_round(config_path: str, run_dir: Path, real: Path | None = None) -> Path:
    """开一局、应用还没起来时：内部资料复制一份给这一局（第 9 关改的是副本），再照 scripts/compile_qi.py 把录制的
    编译提议导入成待研发审的候选（第 4 关）。返回这一局的配置；已经有了就照用（服务重启后续上这一局）。
    real：真实报告版的目录（配置 play_real_report，不入库），这一局换成它 round.yaml 里的种子副本与资料来源。"""
    path = run_dir / "app.yaml"
    if path.exists():
        return path
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if real is not None:
        config.update(yaml.safe_load((real / "round.yaml").read_text(encoding="utf-8")))
    for i, s in enumerate(config["sources"]):
        if s["kind"] == "internal":
            s["root"] = str(shutil.copytree(s["root"], run_dir / "sources" / str(i)))
    config["qi_state"] = str(run_dir / "qi_state.json")
    kb = KnowledgeBase.from_seeds(load_seeds(config["seeds_dir"]), EventLog(), AuditLog(), state_path=config["qi_state"])
    kb.sources = [FolderSource(s["name"], s["kind"], s["root"], s.get("level"), kb._doc_levels) for s in config["sources"]]
    proposals = Path(config["seeds_dir"]) / "rag" / "proposals.yaml"     # 录制的编译提议，代替模型编译
    admit(Proposals(items=yaml.safe_load(proposals.read_text(encoding="utf-8"))["items"]).items, kb.sources, kb)
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def fresh(round_: int = 1, speed: int = 60, real: bool = False, roadshow: bool = False) -> dict:
    """一局的进度：cases 每件事送来的会话，done 导演代办过的动作，acted 导演代谁做了什么（前情标「模拟」）；
    real 这一局的关卡用真实报告；roadshow 路演局：导演只扮演外部世界和事到你手上之前的那几步。"""
    return {"round": round_, "speed": speed, "paused": False, "real": real, "roadshow": roadshow,
            "cases": {}, "done": [], "passed": [], "seen": {}, "acted": []}


class Director:
    def __init__(self, api: Callable[[], object], path: Path, levels: list[dict] | None = None, real: Path | None = None):
        """api：取当前这一局的 Api（重开本关后换成新的一局）；path：进度文件；real：真实报告版的目录，没配就只有模拟报告。"""
        self.api, self.path, self.real = api, path, real
        self.state = fresh() | (json.loads(path.read_text(encoding="utf-8")) if path.exists() else {})
        self.levels = levels or self._levels()
        self.customers: dict[str, SimCustomer] = {}
        self.error: str | None = None

    def _levels(self) -> list[dict]:
        return load_levels(self.real / "levels.yaml" if self.state["real"] else LEVELS)

    def new_round(self, real: bool, roadshow: bool) -> None:
        """开新的一局（重开这一局、换报告、换路演局），骨架跟着这一局用的报告。"""
        if real and self.real is None:
            raise ValueError("没有配置真实报告版（play_real_report）")
        self.state = fresh(round_=self.state["round"] + 1, speed=self.state["speed"], real=real, roadshow=roadshow)
        self.levels, self.customers = self._levels(), {}

    def save(self) -> None:
        self.path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    def open(self) -> list[dict]:
        """该送来、还没通过的事：业务全部，关卡只到第一个没通过的那一步。"""
        stage = [x for x in self.levels if x["kind"] == "stage" and x["id"] not in self.state["passed"]][:1]
        return [x for x in self.levels if x["kind"] == "business" and x["id"] not in self.state["passed"]] + stage

    def view(self) -> dict:
        s, now = self.state, self.open()
        status = lambda x: "passed" if x["id"] in s["passed"] else "open" if x in now else "waiting"
        return {"levels": [{k: x.get(k) for k in SHOWN} | {"status": status(x), "cases": s["cases"].get(x["id"], []),
                            "who": self._who(x) if x in now else None} for x in self.levels],
                "round": s["round"], "real": s["real"], "real_ready": self.real is not None, "roadshow": s["roadshow"],
                "speed": s["speed"], "paused": s["paused"], "done": s["passed"], "acted": s["acted"], "error": self.error,
                "lines": [x for lv in now for x in self._lines(lv)], "notes": [x for lv in now for x in self._notes(lv)]}

    def _who(self, lv: dict) -> str | None:
        """这件事在等谁：送达工作面上的那个人（路演时点一件就以他进入）；还没落到具体的人手上就是 None。"""
        sids = self.state["cases"].get(lv["id"], [])
        if not sids:
            return None
        if lv["to"] == "customer":
            return self._customer_of(sids[0])
        if lv["to"] == "pm":
            return PM
        if lv["to"] == "sales":
            return next(x["sales_id"] for x in self._get("/api/sessions") if x["id"] == sids[0])
        req = self._req(sids[0])
        return req.assigned_rd if req else None

    def _lines(self, lv: dict) -> list[dict]:
        """客户由人来扮时，各位客户接下来可以说的那句台词（只是提示，可以改写）。"""
        out = []
        for sid in self.state["cases"].get(lv["id"], []):
            customer = self._customer_of(sid)
            view = self._get("/api/session", id=sid, viewer=customer)["view"]
            said = sum(t.speaker == "customer" for t in view.turns)
            if said < len(lv["lines"]):
                out.append({"customer": customer, "session_id": sid, "text": lv["lines"][said]})
        return out

    def _notes(self, lv: dict) -> list[dict]:
        """研发由人来扮时，外部世界给他的试样结果（只是提示，录入照常在研发面上做）。"""
        out = []
        for sid in self.state["cases"].get(lv["id"], []) if "trial" in lv else []:
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

    # 一件事 --------------------------------------------------------------------------------------
    def step(self, present: set[str]) -> bool:
        """导演看一眼所有还没通过的事，返回这一眼做没做事。present = 这一局有人在玩的身份；他们的事留给人做。"""
        acted = False
        for lv in self.open():
            acted |= self._step(lv, self._present(lv, present))
        self.save()
        return acted

    def _present(self, lv: dict, present: set[str]) -> set[str]:
        """路演局：业务只把它送达的岗位留给人（之前别的岗位那几步导演做完），关卡各步的岗位都留给人；
        客户只在事送到客户面时留给人。不是路演局就照这一局有人在玩的身份。"""
        if not self.state["roadshow"]:
            return present
        return {a.id for a in self.api().app.seeds.actors
                if a.role == lv["to"] or (lv["kind"] == "stage" and a.role != "customer")}

    def _step(self, lv: dict, present: set[str]) -> bool:
        """这件事还没送来就送来；缺席的客户、岗位各做该做的一步；到了通过条件就记下。"""
        s, key = self.state, lv["id"]
        acted = False
        if key not in s["cases"]:       # 送来：这一关的每位客户开一段会话；没人扮的客户说出开场白，有人扮的由人自己说
            s["cases"][key] = []
            for customer in [lv["customer"], *lv.get("also", [])] if "customer" in lv else []:
                sid = self._act(customer, "/api/sessions", customer_id=customer).id
                s["cases"][key].append(sid)
                if customer not in present:
                    self._act(customer, "/api/turn", session_id=sid, speaker="customer", text=self._line(lv, sid, customer, 0, ""))
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
            text = self._line(lv, sid, customer, said, view.turns[-1].text)
        elif view.asks:                 # 研发回问：客户在自助页按心里的真值回答
            text = self._sim_customer(lv, sid, customer).reply(view.asks[0].ask_text)
        elif view.hints and view.turns[-1].speaker != "customer":
            text = self._sim_customer(lv, sid, customer).reply(view.turns[-1].text)
        else:
            return False
        self._act(customer, "/api/turn", session_id=sid, speaker="customer", text=text)
        return True

    def _line(self, lv: dict, sid: str, customer: str, said: int, heard: str) -> str:
        """客户的第 said 句台词。模板模式照台词说；大模型模式（网关不是桩）由模拟客户（caller sim:customer）用自己的话
        说出台词的意思，心里的真值照关卡，剧情与通关条件不变。heard 是化言或业务员刚说的话。"""
        line = lv["lines"][said]
        app = self.api().app
        if app.config["gateway_mock"]:
            return line
        sim = self._sim_customer(lv, sid, customer)
        cue = f"（这一句请用你自己的话、一两句说出这个意思：「{line}」。不要补充别的条件。）"
        return sim.opening(cue) if said == 0 else sim.reply(f"{heard}\n{cue}")

    def _sim_customer(self, lv: dict, sid: str, customer: str) -> SimCustomer:
        """台词说完以后觉还在追问：按这位客户心里的真值回答（没写的槽位按种子先验抽，随机数按局与会话定）。
        大模型模式下客户的每一句都由它说（网关同一个，计量记在 sim:customer 名下）。"""
        if sid not in self.customers:
            seeds = self.api().app.seeds
            phen = next(p for p in seeds.phenomena if p.id == lv["card"]["phenomenon"])
            rng = random.Random(f"{self.state['round']}:{sid}")
            slots = sample_slots(phen, seeds, rng, lv["card"]["slots"])
            card = NeedCard(id=f"level:{lv['id']}", phenomenon=phen.id, slots=slots, unknown_slots=[], opening_slots=[],
                            customer_id=customer, chem_savvy=False, wants_mechanism=False,
                            truth_product=correct_product(phen.id, slots, seeds.products))
            app = self.api().app
            self.customers[sid] = SimCustomer(card, seeds, rng, gateway=None if app.config["gateway_mock"] else app.gateway)
        return self.customers[sid]

    def _do(self, lv: dict, a: dict, present: set[str]) -> bool:
        """缺席岗位的一步模板解法；前提还没出现（还没交到这个岗位、Agent 还没准备好、客户还没答回问）或有人在玩这个岗位时不做。
        同一个动作要做两次（再确认、再试样）就在关卡里写两遍，前提保证它们一前一后。"""
        sids = self.state["cases"][lv["id"]]
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
            q = next((q for q in self._open("qi_review").values() if q.id in self.state["seen"][lv["id"]]
                      and q.prepared_at and q.signer_id not in present), None)
            if q is None:
                return False
            review = self._act(q.signer_id, "/api/qi/review", ku_ids=[q.refs["ku_id"]])
            self._act(q.signer_id, "/api/resolve", question_id=q.id, action="sign", note=a["review"],
                      reviewed_evidence=review["reviewed_evidence"])
            return True
        if "reuse" in a:
            # 研发不采用产品经理 Agent 建议的现成产品（在线时 Agent 真的去查了现成产品；离线骨架不查，这一步直接算做完）。
            # 每张单都等产品经理 Agent 查完现成产品、都处理完才算做完
            mine = [self._req(x) for x in sids]
            if not all(r and r.reuse for r in mine):
                return False
            reqs = [r for r in mine if r.status == "draft" and r.reuse.product_id and not r.reuse.declined_reason]
            for r in reqs:
                if r.assigned_rd not in present:
                    self._act(r.assigned_rd, "/api/reuse/decline", req_id=r.id, reason=a["reuse"])
            return all(r.assigned_rd not in present for r in reqs)
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
        key = lv["id"]
        for want in lv["pass"]:
            if want.startswith("settled:") and set(self.state["seen"][key]) - set(self._open(want.removeprefix("settled:"))):
                return True
        return any(hit(want, x) for sid in self.state["cases"][key] for x in self._story(sid) for want in lv["pass"])

    # 一局 ----------------------------------------------------------------------------------------
    def play_all(self, tick: Callable[[], None]) -> None:
        """全部岗位都由导演代办，把业务和关卡都跑完（备 CEO 面看的局）。tick：导演没事可做时推进一拍
        （业务时间往前走、觉检查、Agent 准备），产品机会要等觉的定时扫描。"""
        for _ in range(30 * len(self.levels)):
            if not self.open():
                return
            if not self.step(set()):
                tick()
        raise ValueError(f"自动跑不通，停在：{'、'.join(x['id'] for x in self.open())}")
