"""应用门面：负责身份与视图边界，界面只调用这里。"""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.agent import AgentHub
from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (AuditRecord, CitedKnowledge, ContributionDraft, ContributionStat, DecryptGrant,
    Evidence, JueRecord, JueState, KnowledgeUnit, LedgerEntry, NeedState, PointsDraft, Question, ReqItem, Requirement,
    RequirementView, Resolution, ReuseProposal, RunStatus, Session, SessionView, SheetDraft, Trial)
from huayan.domain import consistent, load_seeds
from huayan.escalation import flow
from huayan.escalation.translate import leak_hits
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.jev import Jev
from huayan.jev.system1 import build_system1
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import publish, select_asks
from huayan.jue.state import collect_scheduled, realtime_state, requirement_state, session_state
from huayan.knowledge import AuditLog, KnowledgeBase, Ledger, PermissionDenied, level_of
from huayan.knowledge.disclosure import VERSIONS, cap, render
from huayan.l1.extract import LLMExtractor, RuleExtractor
from huayan.l1.session import handle_turn, recommend, record_disclosure
from huayan.meter import FileMeter


def _find(table, key, what):
    # 调用方（助手工具的参数来自大模型）给的 id 不存在时抛 ValueError，工具层统一回给模型。
    if key not in table:
        raise ValueError(f"{what} {key} 不存在")
    return table[key]


class HuayanApp:
    @classmethod
    def build(cls, config_path: str = "config/app.yaml", run_id: str | None = None):
        app = cls()
        app.config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        app.run_id = run_id or f"run-{uuid4().hex[:12]}"
        if Path(app.run_id).name != app.run_id or any(c in app.run_id for c in '/\\:'):
            raise ValueError("run_id 必须是单个目录名")
        app.run_dir = Path(app.config["run_root"]) / app.run_id
        app.run_dir.mkdir(parents=True, exist_ok=False)
        app.seeds = load_seeds(app.config["seeds_dir"])
        app.actors = {a.id: a for a in app.seeds.actors}
        app.meter = FileMeter(app.run_dir, app.run_id)
        app.events = EventLog(app.run_dir / "events.jsonl")
        app.audit = AuditLog(app.run_dir / "audit.jsonl")
        app.ledger = Ledger(app.run_dir / "ledger.jsonl", points=app.config["points"])
        app.bus = QuestionBus(app.events, app.run_dir / "questions.jsonl")
        app.kb = KnowledgeBase.from_seeds(app.seeds, app.events, app.audit)
        app.gateway = build_gateway("config/models.yaml", app.config["gateway_mock"], app.meter)
        if not app.config["gateway_mock"]:
            cache = app.config.get("llm_cache_dir")
            app.gateway.cache_dir = Path(cache) if cache else None
        app.system1 = build_system1(app.config["system1_impl"], "config/system1.yaml", app.gateway, app.meter)
        app.jev = Jev(app.system1, app.config["thresholds"]["match"])
        app.extractor = (RuleExtractor(app.seeds) if app.config["extractor"] == "rule"
                         else LLMExtractor(app.seeds, app.gateway))
        app._sessions, app._requirements, app._trials = {}, {}, {}
        app.grants = []
        app.templates = load_templates(app.config["templates_dir"])
        app.jue_realtime = app._jue_model(app.config["realtime_model"], "realtime")
        app.jue_scheduled = app._jue_model(app.config["scheduled_model"], "scheduled")
        app._jue_trace, app._answers = {}, {}
        app._last_scan = None
        app.agents = AgentHub(app)
        return app

    def _jue_model(self, name, mode):
        # 原型在 system1 为 OneJev 时用它打分，否则规则模式；Jue-K 只做本地推理。
        if name == "jue_k":
            return JueK(self.config["jue_k_dir"], self.config["templates_dir"], mode, self.meter)
        return JueProto(self.config["templates_dir"], self.system1, mode, self.meter)

    def _propose(self, model, state):
        out = model.propose(state)
        with (self.run_dir / "jue_samples.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(JueRecord(state=state, output=out).model_dump_json() + "\n")
        return out

    def ask_hints(self, need):
        """实时觉：每轮对话后给业务员的追问提示；输出记入 jue_trace。"""
        state = realtime_state(need, self.seeds, self.kb.products(), get_clock().now())
        out = self._propose(self.jue_realtime, state)
        self._jue_trace.setdefault(need.session_id, []).append(out)
        thresholds = self.config["thresholds"]
        threshold = thresholds["ask_jue_k"] if self.jue_realtime.name == "jue_k" else thresholds["ask"]
        return select_asks(out, state, self.seeds, threshold, thresholds["max_asks"])

    def _actor(self, actor_id, roles=None):
        actor = self.actors.get(actor_id)
        if actor is None:
            raise PermissionDenied("未知身份")
        if roles is not None and actor.role not in roles:
            raise PermissionDenied("当前身份无权执行此动作")
        return actor

    def _close_anomalies(self, out, object_ids):
        inactive = {(d.family, d.object_id) for d in out.decisions if not d.precondition_passed}
        anomalies = {t.family for t in self.templates.values() if t.kind == "anomaly"}
        for q in self.bus.list():
            if q.object_id in object_ids and q.family in anomalies and (q.family, q.object_id) in inactive:
                self.bus.resolve(q.id, Resolution(action="answered", by="jue"), out.at)

    def _after(self, session_ids=(), req_ids=()):
        """写后评估会话及关联需求单；只提出决策，不派单或执行下一步。"""
        at = get_clock().now()
        session_ids = set(session_ids)
        req_ids = set(req_ids) | {r.id for r in self._requirements.values()
                                 if session_ids.intersection(r.session_ids)}
        state = JueState(at=at, mode="realtime", objects={})
        refs = {}
        for sid in sorted(session_ids):
            sess = self._sessions[sid]
            objects = session_state(sess, self.events, at).objects
            state.objects.update(objects)
            refs.update({oid: {"session_id": sid, "sales_id": sess.sales_id} for oid in objects})
        for rid in sorted(req_ids):
            req = self._requirements[rid]
            sess = self._sessions[req.session_ids[0]]
            objects = requirement_state(req, sess.need, self.seeds, self.kb, at, self.events).objects
            state.objects.update(objects)
            refs.update({oid: {"session_id": sess.id, "sales_id": sess.sales_id,
                               "requirement_id": rid, "assigned_rd": req.assigned_rd} for oid in objects})
        out = self._propose(self.jue_realtime, state)
        for sid in session_ids:
            self._jue_trace.setdefault(sid, []).append(out)
        self._close_anomalies(out, set(state.objects) | {f"requirement:{rid}" for rid in req_ids})
        thresholds = self.config["thresholds"]
        ready = out.model_copy(update={"decisions": [d for d in out.decisions
            if d.p_need is not None and d.p_need >= thresholds[
                "ask_jue_k" if d.family == "ask_back" and out.model == "jue_k" else "publish"]]})
        return publish(ready, state, self.templates, self.bus, 0, seeds=self.seeds, refs=refs)

    def _save_session(self, session):
        path = self.run_dir / "sessions"
        path.mkdir(exist_ok=True)
        # 逻辑 ID 带冒号，Windows 文件名用下划线，JSON 内保留原始 ID。
        (path / f"{session.id.replace(':', '_')}.json").write_text(session.model_dump_json(), encoding="utf-8")

    def start_session(self, customer_id, sales_id):
        self._actor(customer_id, {"customer"})
        self._actor(sales_id, {"sales"})
        sid = f"sess:{len(self._sessions) + 1}"
        session = Session(id=sid, customer_id=customer_id, sales_id=sales_id, started_at=get_clock().now(),
            need=NeedState(session_id=sid, customer_id=customer_id, sales_id=sales_id,
                           extracted_by=self.extractor.name))
        self._sessions[sid] = session
        self._save_session(session)
        self._after([sid])
        return session.model_copy(deep=True)

    def add_turn(self, session_id, speaker, text):
        if speaker not in ("customer", "sales") or not text.strip():
            raise ValueError("需要有效发言角色与非空文本")
        current = _find(self._sessions, session_id, "会话")
        if speaker == "sales":
            sealed = [item for req in self._requirements.values() for item in req.sealed]
            hits = leak_hits(text, sealed, [], self.kb)
            if hits:
                raise ValueError([hit.model_dump() for hit in hits])
        previous = current.need
        asks = [q for q in self.bus.list(family="ask_back") if q.refs["session_id"] == session_id]
        session = handle_turn(current, speaker, text, self, answering=bool(asks))
        answered = self._answer_ask_back(session, asks) if speaker == "customer" else set()
        if (previous.phenomenon, previous.known()) != (session.need.phenomenon, session.need.known()):
            for req in self._requirements.values():
                if req.status == "draft" and session_id in req.session_ids and req.id not in answered:
                    req.phenomenon, req.known_slots = session.need.phenomenon, session.need.known()
                    req.product_lang = [item for item in req.product_lang if item.edited_by]
                    self._return_to_preparation(req)
                    self._save_requirement(req)
        if speaker == "sales":
            session.reply_draft = ""
        self._save_session(session)
        self._after([session_id])
        return session.model_copy(deep=True)

    def _sales_session(self, session_id, by):
        self._actor(by, {"sales"})
        session = _find(self._sessions, session_id, "会话")
        if session.sales_id != by:
            raise PermissionDenied("只能修改自己负责的会话草稿")
        return session

    def save_reply_draft(self, session_id, text, by):
        session = self._sales_session(session_id, by)
        session.reply_draft = text
        self._save_session(session)
        self._after([session_id])
        return session.model_copy(deep=True)

    def save_escalate_note(self, session_id, text, by):
        session = self._sales_session(session_id, by)
        session.escalate_note = text
        self._save_session(session)
        self._after([session_id])
        return session.model_copy(deep=True)

    def _answer_ask_back(self, session, asks):
        """回问结案并回填条件；已有待签问题退回准备，由 hub 再派给主人。"""
        turn, answered = session.turns[-1], set()
        for q in asks:
            fill = session.need.slots.get(q.refs["slot"])
            if fill is None or fill.turn_id != turn.id:
                continue
            req = self._requirements[q.refs["requirement_id"]]
            if fill.status == "filled":
                req.known_slots[fill.slot] = fill.value
            self._answers.setdefault(req.id, {})[fill.slot] = turn.id
            self.bus.resolve(q.id, Resolution(action="answered", by=session.customer_id,
                                              note=fill.value or "客户不清楚"), get_clock().now())
            self._return_to_preparation(req)
            self._save_requirement(req)
            answered.add(req.id)
        return answered

    def recommend_now(self, session_id):
        session = recommend(_find(self._sessions, session_id, "会话"), self)
        self._save_session(session)
        self._after([session_id])
        return session.model_copy(deep=True)

    def view_session(self, session_id, viewer_id):
        viewer, session = self._actor(viewer_id), _find(self._sessions, session_id, "会话")
        level = level_of(viewer)
        if level == 1 and viewer_id not in (session.customer_id, session.sales_id):
            raise PermissionDenied("只能查看自己参与的会话")
        rec = session.recommendation
        card = None
        if rec and rec.product_id:
            maximum = cap(viewer, session.customer_id, rec.product_id, self.grants)
            version = maximum if level == 3 or maximum == "full_mechanism" else rec.version
            if VERSIONS.index(version) > VERSIONS.index(maximum):
                version = maximum
            card = render(rec.product_id, version, viewer, self.kb, session_id=session_id,
                          customer_id=session.customer_id, grants=self.grants)
            if level == 1:
                record_disclosure(card, self)
        req = next((r for r in reversed(list(self._requirements.values()))
                    if session_id in r.session_ids and r.status != "rejected"), None) if level > 1 else None
        if req is not None:
            req = self.requirement_view(req.id, viewer_id).requirement
        return SessionView(session_id=session_id, viewer=viewer_id, viewer_level=level, turns=session.turns,
            slots=list(session.need.slots.values()), hints=session.hints, replies=session.replies,
            card=card, status=session.status, escalation_question_id=rec.escalated_question_id if rec else None,
            requirement=req,
            reply_draft=session.reply_draft if viewer_id == session.sales_id else "",
            escalate_note=session.escalate_note if viewer_id == session.sales_id or level > 1 else ""
            ).model_copy(deep=True)

    def sessions(self):
        return [s.model_copy(deep=True) for s in self._sessions.values()]

    def jue_trace(self, session_id):
        _find(self._sessions, session_id, "会话")
        return [out.model_copy(deep=True) for out in self._jue_trace.get(session_id, [])]

    def status(self):
        return RunStatus(run_id=self.run_id, replay=self.config["replay"],
            system1_impl=self.config["system1_impl"], realtime_model=self.jue_realtime.name,
            scheduled_model=self.jue_scheduled.name, extractor=self.extractor.name,
            gateway_mock=self.config["gateway_mock"], seeds_placeholder=self.seeds.placeholder)

    def _requirement(self, req_id, by, roles, states):
        actor = self._actor(by, roles)
        if self.kb.is_frozen(by):
            raise PermissionDenied("高层级访问已冻结")
        req = _find(self._requirements, req_id, "需求单")
        if actor.role == "rd" and actor.id != req.assigned_rd:
            raise PermissionDenied("只有接单研发可以修改或签字")
        if req.status not in states:
            raise ValueError(f"当前状态 {req.status}，需要状态 {', '.join(sorted(states))}")
        return req, actor

    def _save_requirement(self, req, *, viewer_id=None):
        path = self.run_dir / "requirements"
        path.mkdir(exist_ok=True)
        (path / f"{req.id.replace(':', '_')}.json").write_text(req.model_dump_json(), encoding="utf-8")
        for sid in req.session_ids:
            self._save_session(self._sessions[sid])
        if viewer_id is not None:
            return self.requirement_view(req.id, viewer_id).requirement

    def _validate_item(self, req, item, actor):
        turns = {t.id for sid in req.session_ids for t in self._sessions[sid].turns if t.speaker == "customer"}
        if any(ref not in turns for ref in item.quote_refs):
            raise ValueError("原话引用必须属于本需求单的客户发言")
        for ref in item.ku_refs:
            try:
                self.kb.get(ref, actor)
            except (ValueError, PermissionDenied) as exc:
                raise ValueError("知识引用不存在或当前身份无权读取") from exc

    def _decision(self, family, action, obj, by):
        question = next((q for q in self.bus.list(family=family) if q.object_id == obj.object_id), None)
        if question:
            if question.signer_id != by:
                raise PermissionDenied("只有指定签字人可以签字")
            if question.prepared_at is None:
                raise ValueError("问题尚在准备中")
        else:
            self.events.append("human_decision", by, {"action": action, "object_id": obj.object_id,
                "object_type": obj.object_type, "attrs": obj.attrs})
        return question

    def escalate(self, session_id, by):
        session = self._sales_session(session_id, by)
        if not session.need.phenomenon or session.status in {"escalated", "closed"}:
            raise ValueError("只有已识别现象且尚未升级的会话可以升级")
        at = get_clock().now()
        obj = session_state(session, self.events, at).objects[f"session:{session_id}"]
        question = self._decision("escalate_need", "escalate", obj, by)
        assigned_rd = min((a for a in self.actors.values() if a.role == "rd"), key=lambda a: (
            -sum(t.level == 3 and t.owner == a.id and session.need.phenomenon in t.phenomenon_ids
                 for t in self.seeds.translations), a.id)).id
        req = Requirement(id=f"req:{len(self._requirements) + 1}", question_id=question.id if question else "",
            session_ids=[session_id], phenomenon=session.need.phenomenon, known_slots=session.need.known(),
            assigned_rd=assigned_rd, escalate_note=session.escalate_note, status="draft", created_at=at)
        self._requirements[req.id] = req
        session.status, session.recommendation = "escalated", None
        self.events.append("escalate", by, {"question_id": req.question_id, "requirement_id": req.id,
            "phenomenon": req.phenomenon, "known": req.known_slots, "customer_id": session.customer_id,
            "p_none": obj.attrs["p_none"]}, session_id=session_id)
        self.events.append("requirement_created", by, {"requirement_id": req.id, "question_id": req.question_id,
            "phenomenon": req.phenomenon, "session_ids": req.session_ids, "assigned_rd": assigned_rd})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after([session_id], [req.id])
        return req.model_copy(deep=True)  # 此时为空单，仅有业务员原话与归属。

    def accept_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"draft"})
        if not req.product_lang or req.reuse is None or (req.reuse.product_id and not req.reuse.declined_reason):
            raise ValueError("接单需要产品需求草稿，且现成产品检查已结束")
        blockers = [q for q in self.bus.list() if q.refs.get("requirement_id") == req_id
                    and q.family in {"ask_back", "distortion"}]
        if blockers:
            raise ValueError(f"还有 {len(blockers)} 条未答回问或未处理失真")
        for item in req.product_lang:
            self._validate_item(req, item, actor)
        units = [self.kb.get(ref, actor) for ref in sorted({ref for item in req.product_lang for ref in item.ku_refs})]
        units = [u for u in units if u.level == 2]
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        question = self._decision("accept_requirement", "accept_requirement", state.objects[f"requirement:{req_id}"], by)
        req.status, req.rd_accepted_by = "rd_accepted", by
        for unit in units:
            if unit.owner != "pm:agent" and not self.ledger.has(unit.owner, unit.id, req.id):
                self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=unit.owner, ku_id=unit.id, ref=req.id,
                    points=self.config["points"]["cited"], reason="cited"))
        self.events.append("requirement_accepted", by, {"requirement_id": req.id,
            "phenomenon": req.phenomenon, "known": req.known_slots, "ku_refs": [u.id for u in units]})
        if question:
            self._settle(question.id, Resolution(action="accept", by=by))
        for q in self.bus.list(family="opportunity"):
            if req_id in q.refs.get("requirement_ids", "").split(","):
                self.bus.resolve(q.id, Resolution(action="accept", by=by), get_clock().now())
        self._save_requirement(req)
        self._after(req_ids=[req.id])
        return self.requirement_view(req.id, by).requirement

    def save_reuse_proposal(self, req_id, product_id, ku_refs, customer_note, note, by):
        req, actor = self._requirement(req_id, by, {"pm"}, {"draft"})
        if by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 可以起草复用建议")
        if product_id is not None:
            self.kb.product(product_id)
        for ref in ku_refs:
            unit = self.kb.get(ref, actor)
            if unit.level != 2 or unit.kind not in {"case", "translation"}:
                raise ValueError("复用依据必须是 L2 案例或转化知识")
        hits = leak_hits(customer_note, req.sealed, req.hypotheses, self.kb)
        if hits:
            raise ValueError([hit.model_dump() for hit in hits])
        req.reuse = ReuseProposal(product_id=product_id, ku_refs=ku_refs, customer_note=customer_note, note=note)
        self.events.append("reuse_proposed", by, {"requirement_id": req_id, "product_id": product_id, "ku_refs": ku_refs})
        if product_id is None:
            for q in self.bus.list(family="reuse_product"):
                if q.object_id == f"requirement:{req_id}":
                    self.bus.resolve(q.id, Resolution(action="answered", by=by), get_clock().now())
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        if product_id is None:
            self.scan()
        return self.requirement_view(req_id, by).requirement

    def record_market_eval(self, req_id, result, note, by):
        req, _ = self._requirement(req_id, by, {"sales"}, {"rd_confirmed"})
        self._sales_session(req.session_ids[0], by)
        if result not in {"pass", "fail"}:
            raise ValueError("客户评价必须为 pass 或 fail")
        trial = next((t for t in reversed(list(self._trials.values()))
                      if t.requirement_id == req_id and t.result == "pass"), None)
        if trial is None or trial.market_eval is not None:
            raise ValueError("需要尚未录入客户评价的通过试样")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        question = self._decision("market_eval", "record_market_eval", state.objects[f"requirement:{req_id}"], by)
        trial.market_eval, trial.market_eval_by, trial.market_eval_note = result, by, note
        unit = self.kb._units[f"ku:trial:{trial.id}"]
        self.kb.add(unit.model_copy(update={"text": trial.model_dump_json()}))
        self.events.append("market_eval", by, {"requirement_id": req.id, "trial_id": trial.id, "result": result})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._after(req_ids=[req.id])
        return trial.model_copy(deep=True)

    def _return_to_preparation(self, req):
        for q in self.bus.list():
            if q.refs.get("requirement_id") == req.id and q.prepared_at is not None:
                self.bus.set_prepared(q.id, None)

    def draft_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"pm"}, {"draft"})
        if by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 可以起草产品需求")
        from huayan.escalation import translate
        draft = translate.draft_product_need(req, [self._sessions[sid] for sid in req.session_ids],
                                              self.kb, actor, get_clock().now())
        edited = [i for i in req.product_lang if i.edited_by]
        items = edited + [i for i in draft.product_lang
                          if not any((i.slot and i.slot == old.slot) or set(i.quote_refs) & set(old.quote_refs)
                                     for old in edited)]
        for item in items:
            self._validate_item(req, item, actor)
        req.direction, req.product_lang, req.drafted_by = draft.direction, items, by
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def edit_req_item(self, req_id, index, item: ReqItem, by):
        actor = self._actor(by, {"pm", "rd"})
        req, _ = self._requirement(req_id, by, {actor.role},
                                   {"draft"} if actor.role == "pm" else {"rd_accepted"})
        self._validate_item(req, item, actor)
        items = req.product_lang if actor.role == "pm" else req.chem_lang
        if index == -1:
            items.append(item.model_copy(deep=True))
        elif 0 <= index < len(items):
            items[index] = item.model_copy(deep=True)
        else:
            raise ValueError("条目索引不存在；追加请使用 -1")
        if actor.role == "rd":
            req.chem_drafted_by = by
        return self._save_requirement(req, viewer_id=by)

    def remove_req_item(self, req_id, index, by):
        actor = self._actor(by, {"pm", "rd"})
        req, _ = self._requirement(req_id, by, {actor.role},
                                   {"draft"} if actor.role == "pm" else {"rd_accepted"})
        items = req.product_lang if actor.role == "pm" else req.chem_lang
        if not 0 <= index < len(items):
            raise ValueError("条目索引不存在")
        items.pop(index)
        return self._save_requirement(req, viewer_id=by)

    def set_direction(self, req_id, text, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"draft"})
        if not text.strip():
            raise ValueError("产品方向不能为空")
        req.direction = text
        return self._save_requirement(req, viewer_id=by)

    def translate_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"rd_accepted"})
        from huayan.escalation import translate
        draft = translate.draft_chem_need(req.model_copy(deep=True),
            [self._sessions[sid].model_copy(deep=True) for sid in req.session_ids], self.kb, actor, get_clock().now())
        for item in draft.chem_lang:
            self._validate_item(req, item, actor)
        req.chem_lang, req.hypotheses, req.chem_drafted_by = draft.chem_lang, draft.hypotheses, by
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def confirm_translation(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"rd_accepted"})
        if not req.chem_lang:
            raise ValueError("请先起草化学语言条目")
        for item in req.chem_lang:
            self._validate_item(req, item, actor)
        products = sorted((p for p in self.seeds.products if p.status == "project"
            and req.phenomenon in p.solves and consistent(p, req.known_slots)), key=lambda p: p.id)
        if not products:
            raise ValueError("没有覆盖该需求的研发中产品，暂不能确认")
        if any(q.family in {"ask_back", "distortion"} and q.refs.get("requirement_id") == req_id
               for q in self.bus.list()):
            raise ValueError("仍有未答回问或未处理失真")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        question = self._decision("confirm_translation", "confirm_translation", state.objects[f"requirement:{req_id}"], by)
        req.product_id, req.status, req.rd_confirmed_by = products[0].id, "rd_confirmed", by
        refs = sorted({ref for item in req.chem_lang for ref in item.ku_refs})
        for ref in refs:
            unit = self.kb.get(ref, actor)
            if unit.level == 3 and unit.owner != "pm:agent" and not self.ledger.has(unit.owner, ref, req.id):
                self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=unit.owner, ku_id=ref, ref=req.id,
                    points=self.config["points"]["cited"], reason="cited"))
        self.events.append("requirement_translated", by, {"requirement_id": req.id, "ku_refs": refs})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def save_contribution_draft(self, req_id, draft: ContributionDraft, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_accepted", "rd_confirmed"})
        if not 0 <= draft.item_index < len(req.chem_lang) or not draft.scene_phrase.strip() or not draft.chem_term.strip():
            raise ValueError("需要有效化学条目索引、场景说法与化学术语")
        req.contribution_drafts = [d for d in req.contribution_drafts if d.item_index != draft.item_index]
        req.contribution_drafts.append(draft.model_copy(deep=True))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def contribute_translation(self, req_id, item_index, scene_phrase, chem_term, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"rd_accepted", "rd_confirmed"})
        if not 0 <= item_index < len(req.chem_lang) or not scene_phrase.strip() or not chem_term.strip():
            raise ValueError("需要有效化学条目索引、原文与译文")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        question = self._decision("contribution", "contribute_translation", state.objects[f"requirement:{req_id}"], by)
        unit = flow.contribute_translation(req, item_index, scene_phrase, chem_term,
            actor, self.kb, self.ledger, self.events, get_clock().now())
        if req.status == "rd_confirmed":
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=by, ku_id=unit.id, ref=req.id,
                                       points=self.config["points"]["cited"], reason="cited"))
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return unit

    def save_points_draft(self, req_id, public, sealed, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        req.points_draft = PointsDraft(public=public, sealed=sealed,
            self_check=leak_hits(public, sealed, req.hypotheses, self.kb))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def set_public_points(self, req_id, text, sealed, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        if not text.strip():
            raise ValueError("对外要点不能为空")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        obj = state.objects[f"requirement:{req_id}"]
        if obj.attrs["market_eval"] != "pass":
            raise ValueError("客户评价通过后才能签字封存／放出")
        question = self._decision("seal_points", "set_public_points", obj, by)
        req.public_points, req.sealed, req.sheet = text, list(sealed), None
        self.events.append("points_set", by, {"requirement_id": req_id, "n_sealed": len(sealed)})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def requirements(self, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        return [self.requirement_view(req.id, viewer_id).requirement for req in self._requirements.values()]

    def requirement_view(self, req_id, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        req = _find(self._requirements, req_id, "需求单").model_copy(deep=True)
        # L2 可看转译条目；研发内部假设、封存项及两类草稿只对 L3 开放。
        if level_of(viewer) < 3:
            req.hypotheses = []
            req.sealed = []
            req.points_draft = None
            req.contribution_drafts = []
        refs = sorted({ref for item in req.product_lang + req.chem_lang for ref in item.ku_refs})
        cited = []
        for ref in refs:
            unit = self.kb._units[ref]
            readable = unit.level <= level_of(viewer)
            cited.append(CitedKnowledge(ku_id=ref, owner=unit.owner, level=unit.level,
                title=unit.title if readable else f"研发 {unit.owner} 的转化知识（L3）",
                text=unit.text if readable else None,
                n_cited=sum(e.reason == "cited" and e.ku_id == ref for e in self.ledger.list())))
        quote_refs = {ref for item in req.product_lang + req.chem_lang for ref in item.quote_refs}
        quotes = {t.id: t.text for sid in req.session_ids for t in self._sessions[sid].turns if t.id in quote_refs}
        return RequirementView(viewer=viewer_id, viewer_level=level_of(viewer), requirement=req,
                               quotes=quotes, cited=cited)

    def leak_check(self, req_id, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        req = _find(self._requirements, req_id, "需求单")
        if req.sheet is None:
            return []
        # 用完整内部来源检查，返回值仅含句序号与类别；用法接续说明书编号。
        return leak_hits(f"{req.sheet.sheet}\n{req.sheet.usage}", req.sealed, req.hypotheses, self.kb)

    def record_trial(self, trial: Trial):
        actor = self._actor(trial.rd, {"rd"})
        if self.kb.is_frozen(actor.id):
            raise PermissionDenied("高层级访问已冻结")
        if trial.id in self._trials:
            raise ValueError("试样记录已经存在")
        if trial.requirement_id:
            req, _ = self._requirement(trial.requirement_id, trial.rd, {"rd"}, {"rd_confirmed"})
            if req.product_id != trial.product_id:
                raise ValueError("试样产品与需求单不一致")
        else:
            self.kb.product(trial.product_id)
        unit = KnowledgeUnit(id=f"ku:trial:{trial.id}", level=3, kind="trial", title=f"试样 {trial.id}",
            text=trial.model_dump_json(), product_id=trial.product_id, owner=trial.rd,
            source="trial", created_at=trial.at)
        self.kb.add(unit)
        self._trials[trial.id] = trial.model_copy(deep=True)
        self.events.append("trial", trial.rd, {"trial_id": trial.id, "product_id": trial.product_id,
            "conditions": trial.conditions, "result": trial.result, "cause": trial.cause}, ts=trial.at)
        if trial.result == "pass":
            self.ledger.add(LedgerEntry(ts=trial.at, owner=trial.rd, ku_id=unit.id,
                points=self.config["points"]["trial_pass"], reason="trial_pass", ref=trial.id))
        if trial.requirement_id:
            self._after(req_ids=[trial.requirement_id])
        return trial.model_copy(deep=True)

    def package_sheet(self, req_id, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"rd_confirmed"})
        if by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 可以包装说明书")
        if not req.public_points:
            raise ValueError("请研发先确认对外要点")
        from huayan.escalation import translate
        # 包装只用 L2 视图与对外要点，不传入研发内部内容。
        public = self.requirement_view(req_id, by).requirement.model_copy(update={"chem_lang": []}, deep=True)
        req.sheet = translate.package_sheet(public)
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return req.sheet.model_copy(deep=True)

    def save_sheet(self, req_id, sheet: SheetDraft, by):
        req, actor = self._requirement(req_id, by, {"pm", "rd"}, {"rd_confirmed"})
        if actor.role == "pm" and by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 或接单研发可以修改说明书")
        if not req.public_points or not sheet.sheet.strip() or not sheet.usage.strip():
            raise ValueError("需要研发对外要点以及非空说明书和用法")
        req.sheet = sheet.model_copy(deep=True)
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def release_product(self, req_id, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        if not req.sheet or not req.product_id or not req.public_points:
            raise ValueError("发布需要关联产品、对外要点与说明书")
        if not any(t.requirement_id == req.id and t.result == "pass" for t in self._trials.values()):
            raise ValueError("发布前需要本需求单的通过试样")
        if any(p.id == req.product_id for p in self.kb.products()):
            raise ValueError("该产品已经发布")
        if self.leak_check(req_id, by):
            raise ValueError("说明书或用法存在泄密命中，请改写后再发布")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.seeds, self.kb, get_clock().now(), self.events)
        question = self._decision("release", "release_product", state.objects[f"requirement:{req_id}"], by)
        seed = next(p for p in self.seeds.products if p.id == req.product_id)
        product = seed.model_copy(update={"sheet": req.sheet.sheet, "usage": req.sheet.usage}, deep=True)
        released = flow.release_product(req, product, self.kb, self.ledger, self.events, by, get_clock().now())
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return released.model_copy(deep=True)

    def contributions(self, viewer_id):
        viewer = self._actor(viewer_id)
        result = []
        for unit in self.kb._units.values():
            entries = [e for e in self.ledger.list(unit.owner) if e.ku_id == unit.id or (
                e.ku_id is None and e.reason == "product_released" and unit.kind == "sheet"
                and e.ref == unit.product_id)]
            if not entries:
                continue
            result.append(ContributionStat(owner=unit.owner, ku_id=unit.id, level=unit.level,
                title=unit.title if unit.level <= level_of(viewer) else f"研发 {unit.owner} 的转化知识",
                n_cited=sum(e.reason == "cited" for e in entries), points=sum(e.points for e in entries),
                used_by=sorted({e.ref for e in entries})))
        return result

    def request_decrypt(self, session_id, by):
        actor = self._actor(by, {"sales"})
        session = _find(self._sessions, session_id, "会话")
        if by != session.sales_id or self.kb.is_frozen(by):
            raise PermissionDenied("只能为自己的有效会话申请解密")
        rec, profile = session.recommendation, session.need.profile
        if not rec or not rec.product_id or not profile.chem_savvy:
            raise ValueError("解密需要已有推荐，且客户懂化学")
        product = self.kb.product(rec.product_id)
        q = self.bus.publish(Question(id="", family="decrypt_request", title="客户申请了解产品机理",
            object_id=f"{session_id}/{product.id}", owner_role="rd", owner_id=product.owner,
            scored_by="human", discoverer="human", created_at=get_clock().now(),
            dedup_key=f"decrypt_request:{session_id}/{product.id}",
            evidence=[Evidence(summary="客户明确要求机理", quote=profile.evidence_quote)],
            refs={"session_id": session_id, "customer_id": session.customer_id, "product_id": product.id}))
        self.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="decrypt_request",
            object_ids=[q.id, product.id], session_id=session_id))
        self.events.append("decrypt_request", by, {"question_id": q.id, "customer_id": session.customer_id,
            "product_id": product.id}, session_id=session_id)
        return q.model_copy(deep=True)

    def decide_decrypt(self, question_id, by, approve):
        self._actor(by, {"rd"})
        question = _find(self.bus.questions, question_id, "问题")
        if question.family != "decrypt_request" or question.status != "open":
            raise ValueError("只能审批待处理的解密申请")
        if question.owner_id != by or self.kb.is_frozen(by):
            raise PermissionDenied("只有产品归属研发本人可审批")
        at, refs = get_clock().now(), question.refs
        if approve:
            self.grants.append(DecryptGrant(id=f"grant:{len(self.grants) + 1}",
                customer_id=refs["customer_id"], product_id=refs["product_id"],
                session_id=refs["session_id"], approved_by=by, at=at))
            self.events.append("decrypt_approve", by, {"question_id": question.id,
                "customer_id": refs["customer_id"], "product_id": refs["product_id"]}, session_id=refs["session_id"])
        self.audit.append(AuditRecord(ts=at, actor=by, action="decrypt_approve" if approve else "decrypt_reject",
            object_ids=[question_id, refs["product_id"]], session_id=refs["session_id"]))
        result = self.bus.resolve(question_id, Resolution(action="approve_decrypt" if approve else "reject_decrypt",
                                                         by=by), at)
        return result.model_copy(deep=True)

    # 觉定时发现与处置（WP-I）
    def _settle(self, question_id, resolution):
        """人处置问题：带悬赏的给处置人记 bounty 积分。"""
        q = self.bus.resolve(question_id, resolution, get_clock().now())
        if q.bounty_points and resolution.action != "dismiss" and resolution.by not in {"pm:agent", "jue"}:
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=resolution.by, points=q.bounty_points,
                                        reason="bounty", ref=q.id))
        return q

    def scan(self, at=None):
        at = at or get_clock().now()
        state, refs = collect_scheduled(self.events, at, self.seeds, self.kb.products(), self.config["windows"])
        out = self._propose(self.jue_scheduled, state)
        self._close_anomalies(out, set(state.objects))
        self._last_scan = at
        return publish(out, state, self.templates, self.bus, self.config["thresholds"]["publish"],
                       seeds=self.seeds, refs=refs)

    def resolve(self, question_id, action, by, note=""):
        actor = self._actor(by)
        q = _find(self.bus.questions, question_id, "问题")
        if q.status != "open":
            raise ValueError("问题已处理")
        if by == "pm:agent" or q.signer_id != actor.id:
            raise PermissionDenied("只有问题的签字人可以处置")
        allowed = {"knowledge_conflict": "update_sheet", "leak_risk": "freeze_access"}
        if action != "dismiss" and allowed.get(q.family) != action:
            raise ValueError(f"{q.family} 问题不能执行 {action}")
        if action == "update_sheet":
            pid, slot, value = q.refs["product_id"], *q.object_id.split("|")[1].split("=")
            current = self.kb.product(pid).applicable.get(slot) or next(
                s.values for s in self.seeds.slots if s.id == slot)
            self.kb.update_applicable(pid, slot, [v for v in current if v != value], by)
        elif action == "freeze_access":
            self.kb.freeze(q.refs["actor_id"], by, get_clock().now())
        return self._settle(question_id, Resolution(action=action, by=by, note=note)).model_copy(deep=True)

    def questions(self, viewer_id):
        viewer = self._actor(viewer_id, {"sales", "pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        return [q.model_copy(deep=True) for q in self.bus.list()
                if viewer_id in (q.owner_id, q.signer_id)]

    def mark_prepared(self, question_id, by):
        """由 hub 在主人准备完毕后调用；只标待签，不签字、不推进业务。"""
        actor = self._actor(by, {"sales", "pm", "rd", "supervisor"})
        if self.kb.is_frozen(actor.id):
            raise PermissionDenied("高层级访问已冻结")
        question = _find(self.bus.questions, question_id, "问题")
        if question.owner_id != by:
            raise PermissionDenied("只有问题主人能标记准备完成")
        if question.status != "open" or question.signer_role is None:
            raise ValueError("只有待处理的签字问题能标记准备完成")
        return self.bus.set_prepared(question_id, get_clock().now()).model_copy(deep=True)

    def tick(self):
        now = get_clock().now()
        found = []
        if self._last_scan is None or now - self._last_scan >= timedelta(minutes=30):
            found += self.scan(now)
        self.agents.dispatch()
        return [q.model_copy(deep=True) for q in found]
