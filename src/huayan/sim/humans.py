"""REPLAN-v8 Q9.3：大模型扮演的客户、业务员、研发、产品经理（只供 sim/ 与 eval/）。
人像真的坐在电脑前：按自己的作息（prompts/personas.yaml 的 every、away）隔一阵打开工作台看一眼，
待办与确认卡都为空就不调模型；有就看着整张工作台做一步，可以先放着。助手是机器，觉提出就去准备（prepare）。
人有两个入口，与之后接入钉钉时相同：签字按钮直接调门面原子方法；对自己的助手说话（hub.chat），助手起草、
查资料，生效动作只出确认卡，由本人确认。客户多数先在自助页问化言，点名要人或有商务诉求时觉交业务员。
卡片上只有本人工作面上看得到的内容和按钮。
模拟人看不到需求卡、注入清单与世界规律；只有模拟客户知道真值。试样结果、客户评价由世界规律（sim/world.py）给出。
v8 Q9.4：主管（sim:supervisor）看泄露风险、决定冻不冻结，主管没有助手（Q9.8：冻结后被拦的人还在要原理时，主管也看到可以解冻）；客户拿到推荐后送样试用，结果由产品归属研发录入；
研发确认化学要点时，世界按当时的已知条件记下「这单照此试样会不会失败」（verdicts，只供 eval/）。"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, create_model

from huayan.clock import get_clock
from huayan.contracts import LLMRequest, Message, NeedCard, Question, Tier, Trial
from huayan.knowledge import PermissionDenied
from huayan.sim.customer import SimCustomer
from huayan.sim.world import market_outcome, trial_outcome

PROMPTS = Path(__file__).parents[3] / "prompts"
TRIAL_DELAY = timedelta(days=1)          # 确认化学要点 1 个业务日后试样（模拟 ELN 录入）
SAMPLE_DELAY = timedelta(days=2)         # v8 Q9.4：客户拿到推荐 2 天后送样试用，反馈由产品归属研发录入
MAX_TURNS = 8
LOOK_STEPS = 4                           # 一次查看最多做几步（处理一件、对助手说一句、确认一张卡都算一步）
CUSTOMER_EVERY = [60, 180]               # 客户隔一两个小时回自助页看一眼
SELF_SERVE = ("你现在在供应商的客户自助页面上，和页面里的助手「化言」打字交流（不是真人）。"
              "化言给出推荐后：觉得合适可以要报价或送样；拿不准、想找人细谈，可以说请业务员联系你；觉得不对路就直说。")
DETAIL = 3                               # 工作台卡片上展开材料的件数（最早的几件）
AWAY = ["12:00-13:00"]                   # 所有人午休
OPEN, CLOSE = time(9), time(18)


@dataclass
class Button:
    label: str
    run: Callable[["Choice"], object]
    needs: str = ""                       # "" | "text" | "slots"
    question: Question | None = None      # 工作台上的按钮属于哪件待办
    kind: str = "sign"                    # sign 签字生效 | chat 对助手说 | card 确认/驳回助手的提议 | talk 对客户说


class Choice(BaseModel):
    button: str
    text: str = ""
    slots: list[str] = []
    reason: str


def load_personas(path: Path = PROMPTS / "personas.yaml") -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {actor: p for role in doc.values() for actor, p in role.items()}


class LLMHumans:
    def __init__(self, app, personas: dict, drift: bool = False):
        self.app, self.personas, self.drift = app, personas, drift
        self.applicable = {p.id: p.applicable for p in app.seeds.products}   # 世界规律用种子适用表；新立的产品为空
        self.samples: list[tuple[datetime, str]] = []      # (到期, 会话)：客户送样试用
        self.sampled: set[str] = set()
        self.verdicts: list[dict] = []                      # 确认化学要点时世界的判定（只供 eval/）
        self.customers: dict[str, SimCustomer] = {}
        self.cards: dict[str, NeedCard] = {}               # 会话 → 需求卡（只给模拟客户与世界规律用）
        self.trials: list[tuple[datetime, str, str]] = []
        self.tested: dict[str, dict[str, str]] = {}        # 需求单 → 最近一次试样时的已知条件（客户评价按它对照真值）
        self.looks: list[dict] = []                         # 每次查看：谁、何时、待办几件
        self.log: list[dict] = []
        self.slot_label = {s.id: s.label for s in app.seeds.slots}
        self.answered: set[str] = set()                     # 客户在自助页答过的回问
        self.seen: dict[str, str | None] = {}               # 客户在自助页看过的推荐
        self.called: set[str] = set()                       # 业务员打过电话的会话
        self.denied_seen: dict[str, int] = {}               # 主管看过的「冻结后被拦」次数

    # 模型选按钮 ------------------------------------------------------------------------------------
    def _choose(self, actor: str, card: str, buttons: dict[str, Button]) -> Choice:
        role = actor.split(":")[0]
        p = self.personas[actor]
        system = (PROMPTS / f"sim_{role}.md").read_text(encoding="utf-8").format(
            name=p["name"], persona=p["persona"], direction=p.get("direction", ""), line=p.get("line", ""))
        menu = "\n".join(f"- {k}：{b.label}" + {"text": "（需要 text）", "slots": "（需要 slots）"}.get(b.needs, "")
                         for k, b in buttons.items())
        schema = create_model("SimChoice", __base__=Choice, button=(Literal[tuple(buttons)], ...))
        choice, _ = self.app.gateway.structured(LLMRequest(tier=Tier.FAST, caller=f"sim:{role}", temperature=0.3,
            max_tokens=400, messages=[Message(role="system", content=system),
                                      Message(role="user", content=f"{card}\n\n可以点的按钮：\n{menu}")]), schema)
        return choice

    def _decide(self, actor: str, family: str, object_id: str, card: str, buttons: dict[str, Button],
                question_id: str = "") -> str:
        for attempt in range(2):                           # 门面拒绝（含权限）：记入日志，带着拒绝原因再选一次
            choice = self._choose(actor, card, buttons)
            button = buttons[choice.button]
            if button.question:
                q = button.question
                family, object_id, question_id = q.family, q.object_id, q.id
            try:
                button.run(choice)
                action = button.label
                break
            except (ValueError, PermissionDenied) as exc:
                action = f"被拒：{button.label}（{exc}）"
                if attempt == 0:
                    self._log(family, object_id, action, actor, question_id, choice.reason, choice.text, choice.slots,
                              raised=button.question, kind=button.kind)
                    card += (f"\n你刚才选了「{button.label}」" + (f"，写的是：{choice.text}" if choice.text else "")
                             + f"。系统拒绝：{exc}。请据此改正后重新选择。")
        return self._log(family, object_id, action, actor, question_id, choice.reason, choice.text, choice.slots,
                         raised=button.question, kind=button.kind)

    # 客户来找：多数客户先在自助页问化言；点名要人或有商务诉求时觉交业务员；少数客户（direct）直接打给业务员 ----------
    def visit(self, card: NeedCard, sales: str, rng: random.Random, direct: bool | None = None, intent: str = "") -> None:
        """direct、intent：Q9.4 剧本事件用（这次直接打给业务员；这次另有来意，追加在人设后）。"""
        app, p = self.app, self.personas[card.customer_id]
        direct = p.get("direct", False) if direct is None else direct
        customer = SimCustomer(card, app.seeds, rng, app.gateway, persona=p["persona"] + intent,
                               channel="" if direct else SELF_SERVE)
        sid = app.start_session(card.customer_id, sales if direct else None).id
        self.customers[sid], self.cards[sid] = customer, card
        if direct:
            app.add_turn(sid, "customer", customer.opening())
            self.call(sid, sales)
            return
        app.add_turn(sid, "customer", customer.opening("（你打开了供应商的客户自助页面，请用一两句话说出你遇到的问题。）"))
        for _ in range(MAX_TURNS):
            if not self._portal(sid):
                break

    def _portal(self, sid: str) -> bool:
        """客户在自助页看化言刚说了什么（追问、回答、推荐、研发的回问），回一句；没有新内容就离开。"""
        app, customer = self.app, self.customers[sid]
        cid = customer.card.customer_id
        view = app.view_session(sid, cid)
        if self._handed(sid):
            return False
        asks = [a for a in view.asks if a.question_id not in self.answered]       # 客户只看得到自助页上的回问
        last = view.turns[-1]
        if view.status == "escalated" and not view.card and not asks:
            return False
        if asks:
            self.answered.add(asks[0].question_id)
            text = f"化言：研发想确认一下——{asks[0].ask_text}"
        elif last.speaker == "assistant":
            text = f"化言：{last.text}"
        elif view.replies and view.replies[-1].turn_id == last.id:
            text = f"化言：{view.replies[-1].text}"
        elif view.card and self.seen.get(sid) != view.card.product_id:
            self.seen[sid] = view.card.product_id
            text = "化言给你的推荐：" + "；".join(f"{s.title}：{s.text}" for s in view.card.sections) + (
                f"（{view.card.note}）" if view.card.note else "")
        else:
            return False
        app.add_turn(sid, "customer", customer.reply(text))
        self._log("portal", sid, "客户在自助页回复", cid, note=text[:80])
        return True

    def _handed(self, sid: str) -> bool:
        return any(s.id == sid and s.sales_id for s in self.app.sessions())    # 自助会话有了业务员 = 已交业务员

    def customer_look(self, customer: str) -> None:
        """客户隔一阵回自助页看看：研发的回问、新品推荐，有就回一句（交给业务员的会话不再看）。"""
        replied = sum(self._portal(s.id) for s in self.app.sessions()
                      if s.customer_id == customer and s.sales_id is None and s.id in self.customers)
        self.looks.append({"at": get_clock().now().isoformat(), "by": customer, "todo": replied})

    # 业务员通话：看觉的提示、助手的草稿决定怎么说，也可以先问自己的助手 ------------------------------------
    def handed(self, sales: str) -> list[str]:
        """觉交给这位业务员、还没回过电话的自助会话。"""
        return [s.id for s in self.app.sessions() if s.sales_id == sales and s.origin == "customer"
                and s.id not in self.called]

    def call(self, sid: str, sales: str) -> None:
        app = self.app
        self.called.add(sid)
        notes, relayed = [], False
        for _ in range(MAX_TURNS):
            view = app.view_session(sid, sales)
            if view.status == "escalated" or (view.card and relayed):
                break
            buttons = {"ask": Button("对客户说一句（追问、解释，或改好助手起草的回复再说）", lambda c: self._say(sid, c.text),
                                     "text", kind="talk"),
                       "assistant": Button("对助手说（text 写你要它做的事：从已发布产品里找、起草回复、查资料）",
                                           lambda c: notes.append(self._chat(sales, c.text, session_id=sid)), "text",
                                           kind="chat"),
                       "end": Button("结束本次通话", lambda c: None, kind="talk")}
            if view.card:
                buttons = {"relay": Button("把化言的推荐转述给客户", lambda c: self._say(sid, c.text), "text", kind="talk"),
                           "decrypt": Button("客户想了解作用原理，替客户申请解密", lambda c: app.request_decrypt(sid, sales)),
                           **buttons}
            elif view.status == "open":
                buttons["recommend"] = Button("请化言按现有信息给推荐", lambda c: app.recommend_now(sid))
            buttons.update(self._card_buttons(sales, sid))
            choice = self._decide(sales, "session", sid, self._session_card(view, notes), buttons)
            relayed = relayed or choice.startswith("把化言的推荐")
            # 化言按现有信息也给不出推荐时，由觉判断要不要升级（escalate_need），业务员这通电话先到此
            if choice in ("结束本次通话", "客户想了解作用原理，替客户申请解密") or (
                    choice == "请化言按现有信息给推荐" and not app.view_session(sid, sales).card):
                break
        if app.view_session(sid, sales).status == "open":
            app.recommend_now(sid)

    def _say(self, sid: str, text: str) -> None:
        first = all(t.speaker != "sales" for t in self.app.view_session(sid, self.cards[sid].customer_id).turns)
        self.app.add_turn(sid, "sales", text)
        cue = "（业务员给你打来电话）" if first and self.customers[sid].channel else ""
        self.app.add_turn(sid, "customer", self.customers[sid].reply(cue + text))

    def _session_card(self, view, notes: list[str]) -> str:
        who = {"customer": "客户", "sales": "你", "assistant": "化言（客户自助页）"}
        talk = "\n".join(f"{who[t.speaker]}：{t.text}" for t in view.turns)
        hints = "；".join(f"{h.label}（建议问法：{h.ask_text}）" for h in view.hints) or "没有"
        rec = ("化言的推荐卡：" + "；".join(f"{s.title}：{s.text}" for s in view.card.sections) +
               (f"（{view.card.note}）" if view.card.note else "")) if view.card else "还没有推荐"
        lines = [f"你正在和客户通话。\n对话：\n{talk}\n\n觉提示可以问：{hints}\n{rec}"]
        if view.reply_draft:
            lines.append(f"助手起草的回复（你可以改了再说）：{view.reply_draft}")
        return "\n".join(lines + notes)

    # 和自己的助手：说一句话、确认它的提议（与钉钉里对机器人说话、点确认卡相同） -------------------------------
    def _chat(self, actor: str, text: str, session_id: str | None = None, focus: str | None = None) -> str:
        conv = self.app.agents.chat(actor, text, session_id, focus)
        reply = next((m.text for m in reversed(conv.messages) if m.role == "assistant"), "（助手没有回复）")
        return f"你刚才对助手说：{text}\n助手答：{reply}"

    def _card_buttons(self, actor: str, session_id: str | None = None) -> dict[str, Button]:
        """助手提议、等本人确认的确认卡（试样结果只由世界给出，录入试样的提议不在模拟里）。"""
        buttons = {}
        for j, a in enumerate(self.app.agents.pending(actor), 1):
            if a.tool == "record_trial" or (session_id and a.conversation_id != f"conv:{actor}:{session_id}"):
                continue
            buttons[f"c{j}/approve"] = Button(f"确认助手的提议 {a.id}：{a.summary}", lambda c, a=a: self._approve(a, actor),
                                              kind="card")
            buttons[f"c{j}/reject"] = Button(f"驳回助手的提议 {a.id}（text 写理由）",
                                             lambda c, a=a: self.app.agents.reject(a.id, actor, c.text), "text", kind="card")
        return buttons

    def _approve(self, a, by: str) -> None:
        done = self.app.agents.approve(a.id, by)
        if not done.result.ok:
            raise ValueError(done.result.error)
        if a.tool == "confirm_translation":
            self.trials.append((get_clock().now() + TRIAL_DELAY, a.args["req_id"], by))
            self._verdict(a.args["req_id"])

    # 研发的试样：结果由世界规律给出 -----------------------------------------------------------------
    def trial(self, req_id: str, rd: str, due: datetime) -> None:
        """到点试样；单子已不在技术确认（研发先回问、退回重新转译），或之后又重新确认排了新的一次，这次就不做。"""
        req = self.app.requirement_view(req_id, rd).requirement
        if req.status != "rd_confirmed" or due != max(d for d, r, _ in self.trials if r == req_id):
            self._log("trial", req_id, "试样取消", rd, note=f"单子状态 {req.status}，或已重新确认另排")
            return
        result, cause, missing = trial_outcome(self.cards[req.session_ids[0]], req.known_slots, self.drift,
                                               self._product(req.product_id))
        self.tested[req_id] = dict(req.known_slots)
        self.app.record_trial(Trial(id=f"trial:{req_id}:{len(self.log)}", product_id=req.product_id,
                                    requirement_id=req_id, rd=rd, conditions=req.known_slots, result=result,
                                    cause=cause, missing_slots=missing, at=get_clock().now()))
        self._log("trial", req_id, f"试样{'通过' if result == 'pass' else '失败'}", rd, note=f"（世界）原因 {cause} {missing}")

    def _product(self, product_id: str) -> tuple[str, dict]:
        return product_id, self.applicable.get(product_id, {})

    def _verdict(self, rid: str) -> None:
        """确认化学要点时，世界按当时的已知条件判一次：照此试样会不会失败、是不是因需求条件缺失（只供 eval/）。"""
        req = self.app._requirements[rid]
        result, cause, missing = trial_outcome(self.cards[req.session_ids[0]], req.known_slots, self.drift,
                                               self._product(req.product_id))
        self.verdicts.append({"requirement_id": rid, "at": get_clock().now().isoformat(), "result": result,
                              "cause": cause, "missing_slots": missing})

    # 客户送样试用：拿到推荐的客户 2 天后试用，结果由世界给出、产品归属研发录入 ------------------------------
    def schedule_samples(self) -> None:
        for s in self.app.sessions():
            if s.id in self.cards and s.id not in self.sampled and s.status == "recommended" \
                    and s.recommendation and s.recommendation.product_id:
                self.sampled.add(s.id)
                self.samples.append((get_clock().now() + SAMPLE_DELAY, s.id))

    def sample(self, sid: str) -> None:
        session = next(s for s in self.app.sessions() if s.id == sid)
        if session.recommendation is None:       # 之后客户又升级了，推荐已撤下，不再送样
            self._log("sample", sid, "送样取消", session.customer_id, note=f"会话状态 {session.status}")
            return
        pid = session.recommendation.product_id
        rd = self.app.kb.product(pid).owner
        known = {k: v.value for k, v in session.need.slots.items() if v.status == "filled"}
        result, cause, missing = trial_outcome(self.cards[sid], known, self.drift, self._product(pid))
        self.app.record_trial(Trial(id=f"sample:{sid}", product_id=pid, rd=rd, conditions=known, result=result,
                                    cause=cause, missing_slots=missing, note="（模拟）客户送样试用反馈",
                                    at=get_clock().now()))
        self._log("sample", sid, f"送样试用{'通过' if result == 'pass' else '失败'}", rd,
                  note=f"（世界）{pid} 原因 {cause} {missing}")

    # 剧本事件：研发在需求单上看到同事知识的存根，决定要不要申请查看（Q9.4） -----------------------------------
    def peer_look(self, rd: str) -> None:
        for req in self.app.requirements(rd):
            if req.assigned_rd != rd:
                continue
            phen = next(p for p in self.app.seeds.phenomena if p.id == req.phenomenon)
            stubs = [h for h in self.app.kb.search_blocked(phen.label, self.app.actors[rd], phenomenon=phen.id)
                     if h.ku_id]
            if stubs:
                h = stubs[0]
                card = (f"你在看需求单 {req.id}（现象 {phen.label}）时，检索到同事 {self.app.actors[h.owner].name} 的一条"
                        f" {h.kind} 类研发知识，你只看得到存根（归属与类型），看不到原文。")
                buttons = {"apply": Button("申请查看（同事本人审批）", lambda c: self.app.request_share(h.ku_id, rd)),
                           "skip": Button("不申请", lambda c: None, kind="later")}
                self._decide(rd, "peer_request", h.ku_id, card, buttons)
                return

    # 助手准备 --------------------------------------------------------------------------------------
    def prepare(self, run=lambda jobs: [fn() for _, fn in jobs]) -> None:
        """助手一直在线：觉提出的问题按对话分组派给助手准备（同一段对话里顺序做），直到没有可派的；
        run 给 sim/schedule.Gate.run 时各组同时进行。"""
        hub = self.app.agents
        while groups := self._groups(hub):
            run([(f"prep:{key}:{len(self.looks)}", lambda ids=ids: hub.dispatch(only=ids)) for key, ids in groups.items()])

    @staticmethod
    def _groups(hub) -> dict[str, set[str]]:
        groups: dict[str, set[str]] = {}
        for q in hub.pending_dispatch():
            groups.setdefault(hub.conversation_of(q), set()).add(q.id)
        return groups

    # 人看工作台 -------------------------------------------------------------------------------------
    def next_look(self, actor: str, after: datetime, rng: random.Random) -> datetime:
        """下一次查看工作台（客户：自助页）的时刻：隔 every 分钟；落在午休、away 或下班后就推到那段结束（下班后推到次日 9 点后）。"""
        p = self.personas[actor]
        at = after + timedelta(minutes=rng.randint(*p.get("every", CUSTOMER_EVERY)))
        for _ in range(4):
            for span in AWAY + p.get("away", []):
                a, b = (time.fromisoformat(x) for x in span.split("-"))
                if a <= at.time() < b:
                    at = at.replace(hour=b.hour, minute=b.minute) + timedelta(minutes=rng.randrange(10))
            if at.time() >= CLOSE or at.time() < OPEN:
                day = at.date() + timedelta(days=at.time() >= CLOSE)
                at = datetime.combine(day, OPEN, tzinfo=at.tzinfo) + timedelta(minutes=rng.randrange(30))
        return at

    def todo(self, actor: str) -> list[Question]:
        """轮到这个人动手的事（与界面工作台同一份待办）：自己签字且助手已准备好的，业务员的回问；最早的在前，
        试样风险置顶（它有期限：确认后次日就试样，两组一样）。"""
        try:
            questions = self.app.questions(actor)
        except PermissionDenied:                 # 被冻结的人打不开工作台
            return []
        return sorted((q for q in questions
                       if (q.family == "ask_back" and q.owner_id == actor)
                       or (q.signer_id == actor and q.prepared_at is not None and q.family != "ask_back")),
                      key=lambda q: (q.family != "trial_risk", q.created_at, q.id))

    def look(self, actor: str) -> None:
        """打开工作台看一眼：没有待办、没有确认卡就不调模型；有就看着整张工作台做一步——处理一件、对助手说一句、
        确认助手的提议，或先放着——最多 LOOK_STEPS 步。业务员先给觉交过来的客户回电话。"""
        if actor.startswith("sales:"):
            for sid in self.handed(actor):
                self.call(sid, actor)
        todo = self.todo(actor)
        self.looks.append({"at": get_clock().now().isoformat(), "by": actor, "todo": len(todo)})
        for q in [q for q in todo if q.family == "market_eval"]:     # 客户评价由世界给出，业务员只录入
            rid = q.refs["requirement_id"]
            result, missing = market_outcome(self.cards[q.refs["session_id"]], self.tested[rid], self.drift)
            note = "（模拟）客户大货" + ("通过" if result == "pass" else "不满意，客户反馈的条件：" + "、".join(missing))
            self.app.record_market_eval(rid, result, note, actor, missing_slots=missing)
            self._log(q.family, q.object_id, f"录入客户评价：{'通过' if result == 'pass' else '不通过'}", actor, q.id,
                      note=f"（世界）{note}", raised=q, kind="sign")
        done, notes = set(), []                         # 这一次查看里处理过的不再拿起来（回问打过电话就等下次）
        anomalies = {t.family for t in self.app.templates.values() if t.kind == "anomaly"}
        for _ in range(LOOK_STEPS):
            todo = [q for q in self.todo(actor) if q.id not in done]
            cards = self._card_buttons(actor)
            frozen = self.app.frozen_actors(actor) if actor.startswith("supervisor:") else []
            fresh = [r for r in frozen if r["n_denied"] > self.denied_seen.get(r["actor_id"], 0)]
            if not todo and not cards and not fresh:
                return
            for r in frozen:                             # v8 Q9.8：有待办或冻结后又被拦时，主管同时看到解冻
                self.denied_seen[r["actor_id"]] = r["n_denied"]
                cards[f"u/{r['actor_id']}"] = Button(
                    f"解冻 {r['name']}（{r['frozen_at'][5:16]} 冻结；之后被拦的原理请求 {r['n_denied']} 次，"
                    f"涉及客户 {'、'.join(r['customers']) or '无'}；冻结依据：{'；'.join(r['evidence'])}）",
                    lambda c, a=r["actor_id"]: self.app.unfreeze_access(a, actor))
            shown, buttons = todo[:DETAIL], {}
            for i, q in enumerate(shown, 1):
                dismiss = {} if q.family not in anomalies else {   # 推进类不给忽略，不想处理就先放着
                    "dismiss": Button("越过，判断无须处理（text 写理由）",
                                      lambda c, q=q: self.app.resolve(q.id, "dismiss", actor, c.text), "text")}
                chat = {} if actor.startswith("supervisor:") else {   # 主管没有助手
                    "chat": Button("对助手说（text 写你要它做的事：查资料、改草稿、解释证据）",
                                   lambda c, q=q: notes.append(self._chat_on(actor, c.text, q)), "text", kind="chat")}
                for key, b in {**self._buttons(q, actor, q.refs.get("requirement_id")), **dismiss, **chat}.items():
                    buttons[f"{i}/{key}"] = replace(b, label=f"第 {i} 件：{b.label}", question=q)
            buttons.update(cards)
            buttons["later"] = Button("这次先到这里，其余稍后再看", lambda c: None, kind="later")
            card = "\n".join([self._desk(actor, todo, shown)] + notes)
            action = self._decide(actor, "desk", actor, card, buttons)
            if action == buttons["later"].label:
                return
            if (m := re.match(r"第 (\d+) 件：", action)) and "对助手说" not in action:
                done.add(shown[int(m.group(1)) - 1].id)

    def _chat_on(self, actor: str, text: str, q: Question) -> str:
        if actor.startswith("sales:"):                  # 业务员助手绑定客户会话
            return self._chat(actor, text, session_id=q.refs["session_id"])
        return self._chat(actor, text, focus=q.refs.get("requirement_id") or q.object_id)

    def _desk(self, actor: str, todo: list[Question], shown: list[Question]) -> str:
        now = get_clock().now()
        wait = lambda q: f"{int((now - q.created_at).total_seconds() // 60)} 分钟"
        lines = [f"现在是 {now:%m-%d %H:%M}，你打开化言工作台，待办 {len(todo)} 件（最早的在前）："]
        lines += [f"- {f'[{i}] ' if i <= len(shown) else ''}{q.title}（已等 {wait(q)}）" for i, q in enumerate(todo[:12], 1)]
        for i, q in enumerate(shown, 1):
            lines += ["", f"—— 第 {i} 件（按钮前缀 {i}/）——", self._card(q, actor, q.refs.get("requirement_id"))]
        return "\n".join(lines)

    def _buttons(self, q: Question, by: str, rid: str | None) -> dict[str, Button]:
        app, f = self.app, q.family
        values = lambda c: [s for s in c.slots if s in self.slot_label]
        table = {
            "ask_back": {"ask": Button("回问客户（写出你要问的话）", lambda c: self._say(q.refs["session_id"], c.text), "text")},
            "escalate_need": {"escalate": Button("升级给研发", lambda c: app.escalate(q.refs["session_id"], by))},
            "reuse_product": {"adopt": Button("采用现成产品", lambda c: app.adopt_reuse(rid, by)),
                              "decline": Button("不采用，写明理由", lambda c: app.decline_reuse(rid, c.text, by), "text")},
            "accept_requirement": {"accept": Button("接单立项", lambda c: app.accept_requirement(rid, by)),
                                   "decline": Button("不立项，写明理由", lambda c: app.decline_project(rid, c.text, by), "text"),
                                   "ask": Button("先回问客户勾选的条件（不接单、不退回产品经理）",
                                                 lambda c: app.ask_before_accept(rid, values(c), by), "slots"),
                                   "return": Button("退回产品经理，写明理由", lambda c: app.return_requirement(rid, c.text, by), "text")},
            "confirm_translation": {"confirm": Button("确认化学要点", lambda c: self._confirm(rid, by))},
            "trial_risk": {"return": Button("先回问勾选的条件再试样", lambda c: app.return_for_conditions(rid, values(c), by), "slots")},
            "trial_rework": {"rework": Button("退回重新转译", lambda c: app.rework_requirement(rid, by))},
            "seal_points": {"points": Button("签字放出对外要点（写在 text）", lambda c: app.set_public_points(rid, c.text, [], by), "text")},
            "release": {"release": Button("审定发布", lambda c: app.release_product(rid, by, *next(
                (p.name, p.category) for p in app.seeds.products if p.id == app._requirements[rid].product_id)))},
            "qi_grant": {"grant": Button("签字授予", lambda c: app.sign_qi_grant(q.id, by, note=c.text),
                                         "text" if q.refs.get("form") == "statement" else "")},
            "qi_review": {"keep": Button("复核后保留", lambda c: app.resolve(q.id, "sign", by)),
                          "withdraw": Button("撤回结论", lambda c: app.withdraw_claim(q.refs["ku_id"], by))},
            "knowledge_conflict": {"update": Button("更新适用表", lambda c: app.resolve(q.id, "update_sheet", by))},
            "decrypt_request": {"approve": Button("批准，写机理说明", lambda c: app.decide_decrypt(q.id, by, True, c.text), "text"),
                                "reject": Button("拒绝", lambda c: app.decide_decrypt(q.id, by, False))},
            "stale_capability": {"narrow": Button("收窄：去掉勾选的取值", lambda c: self._narrow(q, c.slots, by), "slots"),
                                 "revoke": Button("撤销这条判断", lambda c: app.revoke_capability(q.refs["capability_id"], by))},
            "opportunity": {"merge": Button("合并立项", lambda c: app.merge_requirements(q.id, by, c.text), "text")},
            "scope_update": {"extend": Button("批准纳入适用范围", lambda c: app.extend_scope(q.id, c.text, by), "text")},
            "leak_risk": {"freeze": Button("冻结其上层知识检索与解密申请", lambda c: app.resolve(q.id, "freeze_access", by))},
            "mechanism_followup": {"take": Button("接手：给客户回电话，讲用法与公开信息，确有需要就替客户申请解密",
                                                  lambda c: self._take_over(q, by))},
        }
        buttons = table.get(f, {})
        if f in {"accept_requirement", "confirm_translation"} and self.app.candidate_claims(rid, by):
            buttons["claims"] = Button("确认勾选的候选结论（编号写进 slots）",
                                       lambda c: app.confirm_claims(rid, c.slots, by), "slots")
        return buttons

    def _take_over(self, q: Question, by: str) -> None:
        sid = q.refs["session_id"]
        self.app.resolve(q.id, "take_over", by)
        self.called.discard(sid)
        self.call(sid, by)

    def _confirm(self, rid: str, by: str) -> None:
        self.app.confirm_translation(rid, by)
        self.trials.append((get_clock().now() + TRIAL_DELAY, rid, by))
        self._verdict(rid)

    def _narrow(self, q: Question, drop: list[str], by: str) -> None:
        scope = json.loads(q.refs["scope"])
        conditions = {s: [v for v in vs if f"{s}={v}" not in drop] for s, vs in scope.items()}
        self.app.narrow_capability(q.refs["capability_id"], {s: vs for s, vs in conditions.items()
                                                             if len(vs) != len(scope[s])}, by)

    def _card(self, q: Question, by: str, rid: str | None) -> str:
        lines = [f"待处理：{q.title}"] + [f"证据：{e.summary}" for e in q.evidence]
        if rid and not by.startswith("sales:"):          # 业务员的工作面上没有需求单
            req = self.app.requirement_view(rid, by).requirement
            lines.append(f"需求单：现象 {req.phenomenon}；已知条件 " +
                         ("、".join(f"{self.slot_label[s]}={v}" for s, v in req.known_slots.items()) or "无") +
                         f"；状态 {req.status}；产品 {req.product_id or '未定'}")
            lines += [f"产品需求：{it.text}" for it in req.product_lang[:6]]
            lines += [f"化学要点：{it.text}" for it in req.chem_lang[:6]]
            lines += [f"退回与回问记录：{note}" for note in req.return_notes]
            for a in self.app.bus.list(status=None):   # 界面时间线上同样看得到回问的结案
                if a.family == "ask_back" and a.refs.get("requirement_id") == rid:
                    answer = (f"客户答：{a.resolution.note}" if a.resolution and a.resolution.action == "answered"
                              else "已结案" if a.resolution else "还在等客户答复")
                    lines.append(f"已回问 {self.slot_label[a.refs['slot']]}（{a.created_at:%m-%d %H:%M}）：{answer}")
            if req.points_draft:
                lines.append(f"助手起草的对外要点：{req.points_draft.model_dump_json()}")
        if q.family == "qi_grant" and "requester" in q.refs:   # 同层研发申请查看：归属人看得到原文
            ku = self.app.kb.get(q.refs["ku_id"], self.app.actors[by])
            lines.append(f"{self.app.actors[q.refs['requester']].name}申请查看你的这条知识（原文）：{ku.text}")
        elif q.family == "qi_grant" and "ku_id" in q.refs:   # 人记得自己的结论；扮演的模型没有记忆，把原文放进卡片
            ku = self.app.kb.get(q.refs["ku_id"], self.app.actors[by])
            lines.append(f"这条结论是你的（你看得到原文，L{q.refs['audience']} 看不到）：{ku.text}")
            lines.append(f"给 L{q.refs['audience']} 的一句话只说效果和适用场合（例如「某工序里能减少某种问题」），"
                         "不说怎么起作用、靠什么成分或原理。")
        if q.family in {"accept_requirement", "confirm_translation"}:   # 工作台签字区同样列出同单还开着的失真提示，供参考
            lines += [f"同单还开着的失真提示（供参考）：{e.summary}" for d in self.app.questions(by)
                      if d.family == "distortion" and d.refs.get("requirement_id") == rid for e in d.evidence]
        if q.family in {"accept_requirement", "confirm_translation"} and not by.startswith("sales:"):
            lines += [f"契从资料里编出的候选结论（等你确认，可勾选编号）：{u.id}｜{u.title}：{u.text}"
                      for u in self.app.candidate_claims(rid, by)]
        if q.family in {"trial_risk", "accept_requirement"}:
            lines.append("可勾选的条件编号：" + "、".join(f"{s}（{l}）" for s, l in self.slot_label.items()))
        if q.family == "stale_capability":
            lines.append("失败集中的取值（可勾选编号，多到少）：" + q.refs.get("fail_values", "无"))
        if q.family == "ask_back":
            lines.append(f"需要向客户回问：{self.slot_label[q.refs['slot']]}")
        return "\n".join(lines)

    def _log(self, family: str, object_id: str, action: str, by: str, question_id: str = "", reason: str = "",
             text: str = "", slots=(), note: str = "", raised: Question | None = None, kind: str = "") -> str:
        self.log.append({"at": get_clock().now().isoformat(), "family": family, "object_id": object_id, "action": action,
                         "kind": kind,
                         "raised_at": raised.created_at.isoformat() if raised else "",
                         "by": by, "question_id": question_id, "reason": reason, "text": text, "slots": list(slots),
                         "note": note})
        return action
