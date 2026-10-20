"""应用门面：负责身份与视图边界，界面只调用这里。"""
import json
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.agent import AgentHub
from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (KIND_LEVEL, Actor, Capability, AuditRecord, CitedKnowledge, ContributionDraft, ContributionStat, DecryptGrant,
    Evidence, JueRecord, JueState, KnowledgeUnit, LedgerEntry, NeedState, PointsDraft, Question, Recommendation, ReqItem, Requirement,
    RequirementView, Resolution, ReuseProposal, ReuseView, RunStatus, Session, SessionView, SheetDraft, Trial,
    JueTimeline, TimelineNode, TimelinePoint)
from huayan.domain import consistent, load_seeds, match_candidates
from huayan.escalation import flow
from huayan.escalation.translate import leak_hits
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.jev import Jev
from huayan.jev.system1 import build_system1
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto, load_templates
from huayan.jue.publish import publish, select_asks
from huayan.jue.records import load_records
from huayan.jue.state import collect_scheduled, realtime_state, requirement_state, session_state, theme_id
from huayan.ingest.compile import recheck
from huayan.ingest.folder import FolderSource
from huayan.knowledge import AuditLog, KnowledgeBase, Ledger, PermissionDenied, level_of
from huayan.knowledge.permission import colleague_l3, holder
from huayan.knowledge.disclosure import VERSIONS, cap, render, render_refs
from huayan.l1.extract import LLMExtractor, RuleExtractor
from huayan.l1.session import handle_turn, recommend, record_disclosure, recommendation_note
from huayan.meter import FileMeter


# v6：route_of 计「人工节点」的事件：人的签字与对需求的实际处理（不含发言、查看）
_HUMAN_STEPS = {"escalate", "requirement_accepted", "requirement_returned", "project_declined", "reuse_adopted",
                "reuse_declined", "requirements_merged", "scope_extended", "requirement_edited", "market_eval",
                "requirement_translated", "points_set", "product_released", "knowledge_contributed", "l2_contributed"}


def _human_events(events):
    """业务员 / 产品经理 / 研发本人的处理事件（不含产品经理 Agent）；合并需求单时随之写下的整单改写不另计一次。"""
    merges = {(e.actor, e.ts) for e in events if e.kind == "requirements_merged"}
    return [e for e in events if e.kind in _HUMAN_STEPS and e.actor.split(":")[0] in {"sales", "pm", "rd"}
            and e.actor != "pm:agent" and not (e.kind == "requirement_edited" and (e.actor, e.ts) in merges)]


def _read_dir(path):
    return [p.read_text(encoding="utf-8") for p in sorted(path.glob("*.json"))] if path.exists() else []


def _find(table, key, what):
    # 调用方（助手工具的参数来自大模型）给的 id 不存在时抛 ValueError，工具层统一回给模型。
    if key not in table:
        raise ValueError(f"{what} {key} 不存在")
    return table[key]


class HuayanApp:
    @classmethod
    def build(cls, config_path: str = "config/app.yaml", run_id: str | None = None, byok=None, resume: bool = False):
        # byok：试用者自带的大模型 / OneJev（huayan.gateway.byok.Byok），真实调用、不读写录制缓存；密钥只在内存里
        # resume：在已有运行目录上续跑（Q6.5）；日志类读回各自的文件，会话、需求单、试样在下面读回。
        # 不恢复觉的推理轨迹、回问答案到发言的映射、Agent 对话与待确认卡（重启后对话从头开始，未确认的提议作废）
        app = cls()
        app.config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        if byok:
            app.config |= {"replay": False, "gateway_mock": False, "llm_cache_dir": None, "system1_impl": byok.system1_impl}
        app.run_id = run_id or f"run-{uuid4().hex[:12]}"
        if Path(app.run_id).name != app.run_id or any(c in app.run_id for c in '/\\:'):
            raise ValueError("run_id 必须是单个目录名")
        app.run_dir = Path(app.config["run_root"]) / app.run_id
        app.run_dir.mkdir(parents=True, exist_ok=resume)
        app.seeds = load_seeds(app.config["seeds_dir"])
        app.actors = {a.id: a for a in app.seeds.actors}
        app.meter = FileMeter(app.run_dir, app.run_id)
        app.events = EventLog(app.run_dir / "events.jsonl")
        app.audit = AuditLog(app.run_dir / "audit.jsonl")
        app.ledger = Ledger(app.run_dir / "ledger.jsonl", points=app.config["points"])
        app.bus = QuestionBus(app.events, app.run_dir / "questions.jsonl")
        app.kb = KnowledgeBase.from_seeds(app.seeds, app.events, app.audit,
            state_path=app.config.get("qi_state") or app.run_dir / "qi_state.json")
        app._load_public(Path(app.config["seeds_dir"]) / "public.yaml")
        app.kb.sources = [FolderSource(s["name"], s["kind"], s["root"], s.get("level"), app.kb._doc_levels)
                          for s in app.config["sources"]]
        if byok:
            app.gateway = byok.gateway(app.meter)
            app.system1 = byok.system1(app.gateway, app.meter)
        else:
            app.gateway = build_gateway("config/models.yaml", app.config["gateway_mock"], app.meter)
            if not app.config["gateway_mock"]:
                cache = app.config.get("llm_cache_dir")
                app.gateway.cache_dir = Path(cache) if cache else None
                app.gateway.replay = app.config["replay"]
            app.system1 = build_system1(app.config["system1_impl"], "config/system1.yaml", app.gateway, app.meter)
        app.jev = Jev(app.system1, app.config["thresholds"]["match"])
        app.extractor = (RuleExtractor(app.seeds) if app.config["extractor"] == "rule"
                         else LLMExtractor(app.seeds, app.gateway))
        app._sessions = {s.id: s for s in map(Session.model_validate_json, _read_dir(app.run_dir / "sessions"))}
        app._requirements = {r.id: r for r in map(Requirement.model_validate_json, _read_dir(app.run_dir / "requirements"))}
        app._trials = {t.id: t for t in (Trial.model_validate_json(u.text) for u in app.kb._units.values()
                                         if u.kind == "trial" and u.source == "trial")}
        app.templates = load_templates(app.config["templates_dir"])
        app.jue_realtime = app._jue_model(app.config["realtime_model"], "realtime")
        app.jue_scheduled = app._jue_model(app.config["scheduled_model"], "scheduled")
        app._jue_trace, app._answers = {}, {}
        app._last_scan = None
        app._agent_drafting = False  # Hub 工具执行期间的来源标记，不由模型或 HTTP 参数指定。
        app.progress = None          # 界面过程面板的进度回调（ui.server 设置）；只报「谁在做什么、用时」
        app.agents = AgentHub(app)
        return app

    def _load_public(self, path):
        """v6：L0 公开案例与 L1 内部评价（seeds/public.yaml，不属于 Seeds 契约）；测试夹具没有该文件。"""
        if not path.exists():
            return
        cases = {c.id: c for c in self.seeds.cases}
        for item in yaml.safe_load(path.read_text(encoding="utf-8"))["items"]:
            source = cases.get(item.get("source_case"))
            ref = item["source_case"] if source else item["product_id"]
            self.kb.add(KnowledgeUnit(id=f"ku:{item['kind']}:{ref}", level=KIND_LEVEL[item["kind"]], kind=item["kind"],
                title=item["title"], text=item["text"], product_id=item["product_id"],
                phenomenon_ids=[source.phenomenon] if source else [], owner=source.owner if source else item["owner"],
                created_at=get_clock().now()))

    def _jue_model(self, name, mode):
        # 原型在 system1 为 OneJev 时用它打分，否则规则模式；Jue-K 只做本地推理。
        if name == "jue_k":
            return JueK(self.config["jue_k_dir"], self.config["templates_dir"], mode, self.meter)
        return JueProto(self.config["templates_dir"], self.system1, mode, self.meter)

    def emit(self, kind, **fields):
        if self.progress:
            self.progress(kind, **fields)

    def _propose(self, model, state):
        started = time.perf_counter()
        out = model.propose(state)
        self.emit("jue", mode=out.mode, model=out.model, n=sum(d.precondition_passed for d in out.decisions),
                  latency_ms=(time.perf_counter() - started) * 1000)
        with (self.run_dir / "jue_samples.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(JueRecord(state=state, output=out).model_dump_json() + "\n")
        return out

    def ask_hints(self, need):
        """实时觉：每轮对话后给业务员的追问提示；输出记入 jue_trace。"""
        session = self._sessions[need.session_id]
        view = self.kb.view(self._actor(session.sales_id or session.customer_id))
        state = realtime_state(need, view, view.products, get_clock().now())
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
            objects = requirement_state(req, sess.need, self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, at, self.events).objects
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

    def start_session(self, customer_id, sales_id=None):
        """v6：sales_id 为 None = 客户自助会话，不分配假业务员。"""
        self._actor(customer_id, {"customer"})
        if sales_id is not None:
            self._actor(sales_id, {"sales"})
        sid = f"sess:{len(self._sessions) + 1}"
        session = Session(id=sid, customer_id=customer_id, sales_id=sales_id, started_at=get_clock().now(),
            origin="sales" if sales_id else "customer",
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
        if speaker == "sales" and current.sales_id is None:
            raise ValueError("该会话还没有业务员，只接受客户发言")
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
        text = render_refs(text, 0, self.kb)       # 专业结论只能以编号写入，按客户层渲染
        if leak_hits(text, [], [], self.kb, audience=0):
            raise ValueError("回复草稿含客户层不可见的内容，请改写")
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
        if level <= 1 and viewer_id not in (session.customer_id, session.sales_id):
            raise PermissionDenied("只能查看自己参与的会话")
        rec = session.recommendation
        card = None
        if rec and rec.product_id:
            maximum = "product_usage" if self.kb.is_frozen(viewer.id) else cap(
                viewer, session.customer_id, rec.product_id, self.grants)
            version = maximum if level == 3 or maximum == "full_mechanism" else rec.version
            if VERSIONS.index(version) > VERSIONS.index(maximum):
                version = maximum
            card = render(rec.product_id, version, viewer, self.kb, session_id=session_id,
                          customer_id=session.customer_id, grants=self.grants)
            card.note = "；".join(filter(None, [card.note, recommendation_note(session, self)]))
            if level <= 1:
                record_disclosure(card, self)
        req = next((r for r in reversed(list(self._requirements.values()))
                    if session_id in r.session_ids and r.status not in {"rejected", "merged"}), None)
        reuse = None
        if req and req.reuse and req.session_ids[0] == session_id:
            proposal = req.reuse
            adopted = req.status == "reused"
            statement = next((c for c in reversed(self.kb.capabilities()) if c.form == "statement"
                and c.status == "active" and c.audience in range(level + 1)
                and c.payload.get("product_id") == proposal.product_id
                and c.payload["text"] == proposal.customer_note and c.granted_by == req.assigned_rd), None)
            customer_note = statement.payload["text"] if statement else ""
            if statement and adopted and level <= 1:
                self._use_capability(statement.id, session_id, viewer_id)
            if card and adopted and customer_note and card.product_id == proposal.product_id:
                card.note = "；".join(filter(None, [card.note, f"研发 {req.assigned_rd} 审定：{customer_note}"]))
            if viewer_id == session.sales_id:
                product = self.kb.product(proposal.product_id) if proposal.product_id else None
                reuse = ReuseView(requirement_id=req.id, product_id=proposal.product_id,
                    product_name=product.name if product else "",
                    status="adopted" if adopted else "declined" if proposal.declined_reason else "pending" if product else "none")
                if adopted:
                    reuse.usage, reuse.customer_note = product.usage, customer_note
                    for ref in dict.fromkeys(proposal.ku_refs):
                        unit = self.kb._units[ref]
                        label = "历史案例" if unit.kind == "case" else "转化知识"
                        reuse.basis.append(f"{self.actors[unit.owner].name}（{unit.owner}） · {label} · L{unit.level}")
        req = self.requirement_view(req.id, viewer_id).requirement if req and level > 1 else None
        return SessionView(session_id=session_id, viewer=viewer_id, viewer_level=level, turns=session.turns,
            slots=list(session.need.slots.values()), hints=session.hints, replies=session.replies,
            card=card, status=session.status, escalation_question_id=rec.escalated_question_id if rec else None,
            requirement=req, reuse=reuse,
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
        if actor.role != "sales" and self.kb.is_frozen(by):
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
                self._work_unit(req, ref, actor)
            except (ValueError, PermissionDenied) as exc:
                raise ValueError("知识引用不存在或当前身份无权读取") from exc

    def _work_unit(self, req, ref, actor):
        """接单研发对转译引擎为本单引用的知识按「工作中用到」处理（契约 2.10）；其余照常按权限读。"""
        if actor.id == req.assigned_rd and ref in req.engine_refs:
            return self.kb._units[ref].model_copy(deep=True)
        return self.kb.get(ref, actor)

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
        return self._escalate(self._sales_session(session_id, by), by)

    def _escalate(self, session, by, question=None):
        """业务员签字升级；v6 自助会话由 auto_execute 传入 route_rd 问题，by = jue:auto。"""
        session_id = session.id
        if not session.need.phenomenon or session.status in {"escalated", "closed"}:
            raise ValueError("只有已识别现象且尚未升级的会话可以升级")
        at = get_clock().now()
        obj = session_state(session, self.events, at).objects[f"session:{session_id}"]
        question = question or self._decision("escalate_need", "escalate", obj, by)
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
            self._settle(question.id, Resolution(action="auto" if by == "jue:auto" else "sign", by=by))
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
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
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

    def return_requirement(self, req_id, reason, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft"})
        if not reason.strip():
            raise ValueError("请填写退回理由")
        if leak_hits(reason, [], [], self.kb):
            raise ValueError("退回理由含研发术语，请改写为产品需求说明")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("accept_requirement", "return_requirement", state.objects[f"requirement:{req_id}"], by)
        req.return_notes.append(reason)
        self.events.append("requirement_returned", by, {"requirement_id": req_id, "reason": reason})
        if question:
            self._settle(question.id, Resolution(action="return", by=by, note=reason))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

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

    def update_reuse_note(self, req_id, text, by):
        req, actor = self._requirement(req_id, by, {"pm", "rd"}, {"draft"})
        if actor.role == "pm" and by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 或接单研发可以改写复用说明")
        if req.reuse is None or req.reuse.product_id is None:
            raise ValueError("需要先起草现成产品建议")
        hits = leak_hits(text, req.sealed, req.hypotheses, self.kb)
        if hits:
            raise ValueError([hit.model_dump() for hit in hits])
        before = req.reuse.customer_note
        req.reuse.customer_note = text
        self.events.append("requirement_edited", by, {"requirement_id": req_id, "layer": 2,
            "index": -1, "field": "reuse.customer_note", "before": before, "after": text})
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def adopt_reuse(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"draft"})
        if req.reuse is None or req.reuse.product_id is None or req.reuse.declined_reason:
            raise ValueError("没有待审定的现成产品建议")
        proposal = req.reuse
        hits = leak_hits(proposal.customer_note, req.sealed, req.hypotheses, self.kb)
        if hits:
            raise ValueError([hit.model_dump() for hit in hits])
        units = [self.kb.get(ref, actor) for ref in sorted(set(proposal.ku_refs))]
        session = self._sessions[req.session_ids[0]]
        at = get_clock().now()
        state = requirement_state(req, session.need, self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, at, self.events)
        question = self._decision("reuse_product", "adopt_reuse", state.objects[f"requirement:{req_id}"], by)
        self._recommend_product(session, proposal.product_id, at)
        unit = KnowledgeUnit(id=self.kb.next_claim_id(), kind="claim", level=3,
            title="研发审定的复用说明", text=proposal.customer_note, product_id=proposal.product_id,
            phenomenon_ids=[req.phenomenon], owner=by, confirmed_by=by, source="contributed", created_at=at)
        self.kb.add(unit)
        self.kb.grant(Capability(id=self.kb.next_cap_id(), form="statement", audience=0,   # 写给客户的话，研发审过后回到客户
            payload={"text": proposal.customer_note, "product_id": proposal.product_id},
            based_on=[unit.id], granted_by=by, status="active", at=at))
        req.status = "reused"
        for unit in units:
            if unit.level == 2 and unit.owner not in {"pm:agent", "jue"} and not self.ledger.has(unit.owner, unit.id, req.id):
                self.ledger.add(LedgerEntry(ts=at, owner=unit.owner, ku_id=unit.id, ref=req.id,
                    points=self.config["points"]["cited"], reason="cited"))
        self.events.append("reuse_adopted", by, {"requirement_id": req_id, "product_id": proposal.product_id,
            "session_id": session.id, "phenomenon": req.phenomenon, "session_ids": req.session_ids}, session_id=session.id)
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after([session.id], [req_id])
        self.scan()
        return session.model_copy(deep=True)

    def decline_reuse(self, req_id, reason, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft"})
        if req.reuse is None or req.reuse.product_id is None or req.reuse.declined_reason:
            raise ValueError("没有待审定的现成产品建议")
        if not reason.strip():
            raise ValueError("请填写不采用的理由")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("reuse_product", "decline_reuse", state.objects[f"requirement:{req_id}"], by)
        req.reuse.declined_reason = reason
        self.events.append("reuse_declined", by, {"requirement_id": req_id,
            "product_id": req.reuse.product_id, "reason": reason})
        if question:
            self._settle(question.id, Resolution(action="return", by=by, note=reason))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        self.scan()
        return self.requirement_view(req_id, by).requirement

    def _assign_sales(self, session, by):
        """v6：按客户归属写入业务员；原话、已知条件、推荐结果原样留在会话里，业务员不重新采集。"""
        if session.sales_id is not None:
            raise ValueError("该会话已有业务员")
        session.sales_id = session.need.sales_id = self.config["customer_sales"][session.customer_id]
        self.events.append("sales_assigned", by, {"sales_id": session.sales_id, "customer_id": session.customer_id},
                           session_id=session.id)
        self._save_session(session)
        self._after([session.id])
        return session.model_copy(deep=True)

    def _recommend_product(self, session, product_id, at):
        """把一个已发布产品按公开版本推荐到会话（研发审定的复用、研发判定已有产品适用）。"""
        viewer = self.actors[session.sales_id or session.customer_id]
        maximum = "product_usage" if self.kb.is_frozen(viewer.id) else cap(
            viewer, session.customer_id, product_id, self.grants)
        disclosure = self.jev.disclose(session.need, product_id, maximum)
        card = render(product_id, disclosure.choice, viewer, self.kb, session_id=session.id,
                      customer_id=session.customer_id, grants=self.grants)
        session.recommendation = Recommendation(product_id=product_id, candidates=[], match=None,
            disclose=disclosure, version=disclosure.choice, at=at)
        session.status = "recommended"
        record_disclosure(card, self)

    def decline_project(self, req_id, reason, by, applicable_product=None, claim_ids=()):
        """v6：研发不立项。给出 applicable_product = 已有产品适用（只是超出标注范围），客户会话收到该产品推荐；
        否则客户收到「暂无方案、已记录」（会话 closed）。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft"})
        if not reason.strip():
            raise ValueError("请填写不立项的原因")
        if leak_hits(reason, [], [], self.kb):
            raise ValueError("不立项原因含研发术语，请改写为产品需求说明")
        at = get_clock().now()
        state = requirement_state(req, self._sessions[req.session_ids[0]].need, self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, at, self.events)
        question = self._decision("accept_requirement", "decline_project", state.objects[f"requirement:{req_id}"], by)
        if applicable_product:
            self.kb.product(applicable_product)
            if claim_ids:
                self.kb.confirm(claim_ids, by)
            else:
                unit = KnowledgeUnit(id=self.kb.next_claim_id(), kind="claim", level=3,
                    title="研发判定已有产品适用", text=reason, product_id=applicable_product,
                    phenomenon_ids=[req.phenomenon], owner=by, confirmed_by=by, source="contributed", created_at=at)
                self.kb.add(unit)
                claim_ids = [unit.id]
            required = next(p.required_slots for p in self.kb.view(self._actor(by)).phenomena if p.id == req.phenomenon)
            self.kb.grant(Capability(id=self.kb.next_cap_id(), form="applicable", audience=0,
                payload={"product_id": applicable_product, "phenomenon": req.phenomenon,
                         "conditions": {slot: [value] for slot, value in req.known_slots.items() if slot in required}},
                based_on=list(claim_ids), granted_by=by, status="proposed", at=at))
        req.status = "rejected"
        for sid in req.session_ids:
            if applicable_product:
                self._recommend_product(self._sessions[sid], applicable_product, at)
            else:
                self._sessions[sid].status = "closed"
        self.events.append("project_declined", by, {"requirement_id": req_id, "reason": reason,
            "product_id": applicable_product, "phenomenon": req.phenomenon, "known": req.known_slots,
            "session_ids": req.session_ids})
        if question:
            self._settle(question.id, Resolution(action="dismiss", by=by, note=reason))
        for q in self.bus.list():
            if q.refs.get("requirement_id") == req_id:
                self.bus.resolve(q.id, Resolution(action="answered", by=by, note="研发不立项"), at)
        self._save_requirement(req)
        self._after(req.session_ids, [req_id])
        if applicable_product:
            self.scan()        # 觉随即看「是否扩展该产品适用范围」
        return self.requirement_view(req_id, by).requirement

    def _human_pm(self, by):
        actor = self._actor(by, {"pm"})
        if by == "pm:agent":
            raise PermissionDenied("产品经理 Agent 只能起草，不能签字")
        return actor

    def extend_scope(self, question_id, note, by):
        """v6：产品经理签字扩展产品适用范围。写进本门面内该产品的 solves（不改种子文件），
        沉淀为产品经理名下的 L2 知识；此后同类需求在 L1 匹配时命中，被引用时给本人记分。"""
        actor = self._human_pm(by)
        q = _find(self.bus.questions, question_id, "问题")
        if q.family != "scope_update" or q.status != "open":
            raise ValueError("需要待处理的适用范围问题")
        if q.signer_id != by:
            raise PermissionDenied("只有指定签字人可以签字")
        if q.prepared_at is None:
            raise ValueError("问题尚在准备中")
        if not note.strip():
            raise ValueError("请写明扩展依据")
        capability = self.kb.approve(q.refs["capability_id"], by)
        self.events.append("scope_extended", by, {"question_id": q.id,
            "product_id": capability.payload["product_id"], "phenomenon": capability.payload["phenomenon"],
            "capability_id": capability.id, "note": note,
            "requirement_ids": q.refs.get("requirement_ids", "").split(",")})
        self._settle(q.id, Resolution(action="sign", by=by, note=note))
        return capability

    def contribute_l2(self, req_id, item_index, scene_phrase, product_term, by):
        """v6：产品经理把自己修正的 L2 条目沉淀为本人名下的 L2 转化知识（照 flow.contribute_translation）。"""
        actor = self._human_pm(by)
        req, _ = self._requirement(req_id, by, {"pm"}, {"draft", "rd_accepted", "rd_confirmed"})
        if not 0 <= item_index < len(req.product_lang) or not scene_phrase.strip() or not product_term.strip():
            raise ValueError("需要有效产品需求条目索引、场景说法与产品需求说法")
        if req.product_lang[item_index].edited_by != by:
            raise ValueError("只能沉淀本人修正过的条目")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("contribution_pm", "contribute_l2", state.objects[f"requirement:{req_id}"], by)
        at = get_clock().now()
        unit = KnowledgeUnit(id=f"ku:translation:{req.id}:l2:{item_index}", level=2, kind="translation",
            title=scene_phrase, text=f"{scene_phrase} → {product_term}", phenomenon_ids=[req.phenomenon],
            owner=actor.id, source="contributed", created_at=at)
        self.kb.add(unit)
        item = req.product_lang[item_index]
        item.ku_refs = [*item.ku_refs, unit.id]
        self.ledger.add(LedgerEntry(ts=at, owner=actor.id, ku_id=unit.id, ref=req.id,
                                    points=self.config["points"]["contributed"], reason="contributed"))
        self.events.append("l2_contributed", by, {"requirement_id": req.id, "item_index": item_index, "ku_id": unit.id})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return unit.model_copy(deep=True)

    def readiness(self, req_id, viewer_id):
        """v6.1 开工门槛（只读）：该现象的必问条件是否已明确、各自出自哪句原话、是不是觉追问出来的；
        未答回问与未处理失真数。E3「如果只靠开场白」= 客户第一句话里已有的必问条件。全部由现有数据推出。"""
        self._actor(viewer_id, {"pm", "rd", "supervisor"})
        req = _find(self._requirements, req_id, "需求单")
        items = self._conditions(req.session_ids, req.phenomenon, req.known_slots)
        blockers = [q for q in self.bus.list() if q.refs.get("requirement_id") == req_id
                    and q.family in {"ask_back", "distortion"}]
        n_known = sum(i["value"] is not None for i in items)
        return {"requirement_id": req_id, "items": items, "n_required": len(items), "n_known": n_known,
                "n_in_opening": sum(i["in_opening"] for i in items),
                "n_asked_by_jue": sum(i["asked_by_jue"] and i["value"] is not None for i in items),
                "n_open_ask_back": sum(q.family == "ask_back" for q in blockers),
                "n_open_distortion": sum(q.family == "distortion" for q in blockers),
                "n_items_with_quote": sum(bool(i.quote_refs) for i in req.product_lang + req.chem_lang),
                "n_items": len(req.product_lang) + len(req.chem_lang),
                "ready": n_known == len(items) and not blockers}

    def session_readiness(self, session_id, viewer_id):
        """v6.1 E1：会话上「研发开工需要的条件」，按会话裁剪：只含条件名、取值、本会话客户原话、是否觉追问所得。
        客户与业务员只能看自己参与的会话；不含需求单、回问与失真（那些属于 L2/L3 视图）。"""
        viewer, session = self._actor(viewer_id), _find(self._sessions, session_id, "会话")
        if level_of(viewer) <= 1 and viewer_id not in (session.customer_id, session.sales_id):
            raise PermissionDenied("只能查看自己参与的会话")
        phen = session.need.phenomenon
        items = self._conditions([session.id], phen, session.need.known()) if phen else []
        return {"session_id": session.id, "phenomenon": phen, "items": items, "n_required": len(items),
                "n_known": sum(i["value"] is not None for i in items),
                "n_in_opening": sum(i["in_opening"] for i in items),
                "n_asked_by_jue": sum(i["asked_by_jue"] and i["value"] is not None for i in items)}

    def _conditions(self, session_ids, phenomenon, known):
        """该现象的必问条件逐项：取值、出自哪句原话、是客户开场就说了还是觉追问所得。"""
        required = next(p.required_slots for p in self.kb.view(
            Actor(id="system:requirement", role="rd", name="研发需求")).phenomena if p.id == phenomenon)
        slots = {s.id: s for s in self.seeds.slots}
        turns = {t.id: t for sid in session_ids for t in self._sessions[sid].turns}
        fills, asked = {}, set()
        for sid in session_ids:
            fills.update({k: v for k, v in self._sessions[sid].need.slots.items() if v.status == "filled"})
        for e in self.events.query(["ask_hint"]):
            if e.session_id in session_ids:
                asked.update(e.payload["slots"])
        first = {next((t.id for t in self._sessions[sid].turns if t.speaker == "customer"), None) for sid in session_ids}
        items = []
        for slot in required:
            fill = fills.get(slot)
            opening = bool(fill) and fill.turn_id in first
            items.append({"slot": slot, "label": slots[slot].label, "value": known.get(slot),
                          "quote": turns[fill.turn_id].text if fill and fill.turn_id in turns else "",
                          "in_opening": opening, "asked_by_jue": slot in asked and not opening})
        return items

    def save_merge_proposal(self, question_id, target_req_id, member_ids, note, by):
        if by != "pm:agent":
            raise PermissionDenied("只有产品经理 Agent 可以起草合并建议")
        q = self.bus.get(question_id)
        if q.family != "opportunity" or q.status != "open":
            raise ValueError("需要待处理的机会汇聚问题")
        candidates = q.refs["requirement_ids"].split(",")
        if target_req_id not in candidates or any(rid not in candidates for rid in member_ids):
            raise ValueError("合并对象必须来自本问题的候选需求单")
        if target_req_id in member_ids or len(set(member_ids)) != len(member_ids):
            raise ValueError("被并入单不能重复或包含主单")
        req, _ = self._requirement(target_req_id, by, {"pm"}, {"draft"})
        for rid in member_ids:
            self._requirement(rid, by, {"pm"}, {"draft"})
        previous = next((e.payload for e in reversed(self.events.query(["merge_proposed"]))
                         if e.payload["question_id"] == question_id), None)
        if previous and previous["target"] != target_req_id:
            old = self._requirements[previous["target"]]
            old.merge_from, old.merge_note = [], ""
            self._save_requirement(old)
        req.merge_from, req.merge_note = list(member_ids), note
        if q.prepared_at is not None:
            self.bus.set_prepared(q.id, None)
        self.events.append("merge_proposed", by, {"question_id": question_id,
            "target": target_req_id, "members": list(member_ids)})
        self._save_requirement(req)
        self._after(req_ids=[target_req_id])
        return self.requirement_view(target_req_id, by).requirement

    def merge_requirements(self, question_id, by, note=""):
        """v6：真人产品经理签字合并，note = 商业价值与产品方向判断（随问题结案、合并事件交研发）。"""
        q = self.bus.get(question_id)
        if q.family != "opportunity" or q.status != "open":
            raise ValueError("需要待处理的机会汇聚问题")
        proposal = next((e.payload for e in reversed(self.events.query(["merge_proposed"]))
                         if e.payload["question_id"] == question_id), None)
        if proposal is None:
            raise ValueError("请先准备合并建议")
        req, _ = self._requirement(proposal["target"], by, {"pm"}, {"draft"})
        if by == "pm:agent" or q.signer_id != by:
            raise PermissionDenied("只有指定签字人可以合并需求单")
        if q.prepared_at is None:
            raise ValueError("问题尚在准备中")
        if not req.merge_from:
            raise ValueError("合并建议没有被并入单，可选择现在不需要")
        members = [self._requirements[rid] for rid in req.merge_from]
        known = dict(req.known_slots)
        for member in [req, *members]:
            if member.status != "draft" or member.reuse is None or (member.reuse.product_id and not member.reuse.declined_reason):
                raise ValueError("只能合并尚未接单且复用检查已结束的需求单")
            for slot, value in member.known_slots.items():
                if slot in known and known[slot] != value:
                    raise ValueError("需求单的已知条件存在冲突，请先核对")
                known[slot] = value
        at = get_clock().now()
        for member in members:
            req.session_ids.extend(sid for sid in member.session_ids if sid not in req.session_ids)
            member.status, member.merged_into = "merged", req.id
            for question in self.bus.list():
                if question.refs.get("requirement_id") == member.id:
                    self.bus.resolve(question.id, Resolution(action="answered", by=by, note=f"已并入 {req.id}"), at)
            self._save_requirement(member)
        before = {"product_lang": [item.model_dump() for item in req.product_lang], "direction": req.direction}
        req.known_slots, req.direction = known, ""
        req.product_lang = [item for item in req.product_lang if item.edited_by]
        self.events.append("requirement_edited", by, {"requirement_id": req.id, "layer": 2, "index": -1,
            "before": before, "after": {"product_lang": [item.model_dump() for item in req.product_lang], "direction": ""}})
        self.events.append("requirements_merged", by, {"question_id": q.id, "target": req.id,
            "members": list(req.merge_from), "note": note})
        self._settle(q.id, Resolution(action="sign", by=by, note=note))
        self._return_to_preparation(req)
        self._save_requirement(req)
        self._after(req.session_ids, [req.id, *req.merge_from])
        return self.requirement_view(req.id, by).requirement

    def record_market_eval(self, req_id, result, note, by, missing_slots=()):
        """missing_slots：评价不通过时，业务员按客户反馈勾选的没问到的条件。"""
        req, _ = self._requirement(req_id, by, {"sales"}, {"rd_confirmed"})
        self._sales_session(req.session_ids[0], by)
        if result not in {"pass", "fail"}:
            raise ValueError("客户评价必须为 pass 或 fail")
        self._check_slots(missing_slots, result == "fail")
        trial = next((t for t in reversed(list(self._trials.values()))
                      if t.requirement_id == req_id and t.result == "pass"), None)
        if trial is None or trial.market_eval is not None:
            raise ValueError("需要尚未录入客户评价的通过试样")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("market_eval", "record_market_eval", state.objects[f"requirement:{req_id}"], by)
        trial.market_eval, trial.market_eval_by, trial.market_eval_note = result, by, note
        trial.market_eval_missing = list(missing_slots)
        unit = self.kb._units[f"ku:trial:{trial.id}"]
        self.kb.add(unit.model_copy(update={"text": trial.model_dump_json()}))
        self.events.append("market_eval", by, {"requirement_id": req.id, "trial_id": trial.id, "result": result,
                                               "missing_slots": list(missing_slots)})
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
                          if not any((i.slot == old.slot if i.slot or old.slot else set(i.quote_refs) & set(old.quote_refs))
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
        item = item.model_copy(deep=True, update={"edited_by": None if self._agent_drafting or by == "pm:agent" else by})
        before = None
        if index == -1:
            items.append(item)
        elif 0 <= index < len(items):
            before = items[index].model_dump()
            items[index] = item
        else:
            raise ValueError("条目索引不存在；追加请使用 -1")
        if actor.role == "rd":
            req.chem_drafted_by = by
        self.events.append("requirement_edited", by, {"requirement_id": req_id,
            "layer": 2 if actor.role == "pm" else 3, "index": index, "before": before, "after": item.model_dump()})
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def remove_req_item(self, req_id, index, by):
        actor = self._actor(by, {"pm", "rd"})
        req, _ = self._requirement(req_id, by, {actor.role},
                                   {"draft"} if actor.role == "pm" else {"rd_accepted"})
        items = req.product_lang if actor.role == "pm" else req.chem_lang
        if not 0 <= index < len(items):
            raise ValueError("条目索引不存在")
        before = items.pop(index).model_dump()
        self.events.append("requirement_edited", by, {"requirement_id": req_id,
            "layer": 2 if actor.role == "pm" else 3, "index": index, "before": before, "after": None})
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def set_direction(self, req_id, text, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"draft"})
        if not text.strip():
            raise ValueError("产品方向不能为空")
        before = req.direction
        req.direction = text
        self.events.append("requirement_edited", by, {"requirement_id": req_id, "layer": 2, "index": -1,
            "before": {"direction": before}, "after": {"direction": text}})
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def translate_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"rd_accepted"})
        from huayan.escalation import translate
        draft = translate.draft_chem_need(req.model_copy(deep=True),
            [self._sessions[sid].model_copy(deep=True) for sid in req.session_ids], self.kb, actor, get_clock().now())
        edited = [item for item in req.chem_lang if item.edited_by]
        items = edited + [item for item in draft.chem_lang
                          if not any((item.slot == old.slot if item.slot or old.slot else set(item.quote_refs) & set(old.quote_refs))
                                     for old in edited)]
        req.engine_refs = sorted(set(req.engine_refs) | {ref for item in draft.chem_lang for ref in item.ku_refs})
        for item in items:
            self._validate_item(req, item, actor)
        req.chem_lang, req.hypotheses, req.chem_drafted_by = items, draft.hypotheses, by
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
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("confirm_translation", "confirm_translation", state.objects[f"requirement:{req_id}"], by)
        req.product_id, req.status, req.rd_confirmed_by = products[0].id, "rd_confirmed", by
        refs = sorted({ref for item in req.chem_lang for ref in item.ku_refs})
        for ref in refs:
            unit = self._work_unit(req, ref, actor)
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
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
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
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
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
        refs = sorted({ref for item in req.product_lang + req.chem_lang for ref in item.ku_refs})
        colleague = viewer.role == "rd" and viewer.id != req.assigned_rd
        # L2 可看转译条目；研发内部假设、封存项及两类草稿只对 L3 开放。非接单研发与 L2 同样裁剪，且看不到 L3 条目正文。
        if level_of(viewer) < 3 or colleague:
            req.hypotheses = []
            req.sealed = []
            req.points_draft = None
            req.contribution_drafts = []
        if colleague:
            req.chem_lang = []
        cited = []
        for ref in refs:
            unit = self.kb._units[ref]
            readable = (viewer.id == req.assigned_rd and ref in req.engine_refs) or self.kb._readable(viewer, unit)
            cited.append(CitedKnowledge(ku_id=ref, owner=unit.owner, level=unit.level,
                title=unit.title if readable else f"{self.actors[unit.owner].name}的知识（L{unit.level}，仅显示归属）",
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

    def record_requirement_trial(self, req_id, result, by, cause="none", missing_slots=()):
        """工作面模拟 ELN 录入；关联信息与业务时间由后端生成。cause = requirement 时研发勾选缺了哪些条件。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        if (result == "pass") != (cause == "none"):
            raise ValueError("通过的试样不填失败原因，失败的试样必须填原因")
        self._check_slots(missing_slots, cause == "requirement")
        number = len(self._trials) + 1
        while f"trial:{number}" in self._trials:
            number += 1
        return self.record_trial(Trial(id=f"trial:{number}", product_id=req.product_id,
            requirement_id=req.id, rd=by, conditions=dict(req.known_slots), result=result,
            cause=cause, missing_slots=list(missing_slots), note="（模拟）工作面录入", at=get_clock().now()))

    def _check_slots(self, slots, allowed):
        if (bool(slots) and not allowed) or not set(slots) <= {s.id for s in self.seeds.slots}:
            raise ValueError("缺失条件只在需求条件缺失或评价不通过时勾选，且必须是已知槽位")

    def rework_requirement(self, req_id, by):
        """研发签 trial_rework：需求单退回到已接单、待重新转译；缺失条件的回问由觉提出。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        obj = state.objects[f"requirement:{req_id}"]
        if not obj.attrs["n_missing"]:
            raise ValueError("没有待补问的缺失条件")
        question = self._decision("trial_rework", "rework_requirement", obj, by)
        reason = f"{obj.attrs['last_result']}：需求条件缺失，退回重新转译"
        req.status = "rd_accepted"
        req.return_notes.append(reason)
        self.events.append("requirement_returned", by, {"requirement_id": req_id, "reason": reason})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by, note=reason))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

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
            "conditions": trial.conditions, "result": trial.result, "cause": trial.cause,
            "requirement_id": trial.requirement_id, "missing_slots": trial.missing_slots}, ts=trial.at)
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
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("release", "release_product", state.objects[f"requirement:{req_id}"], by)
        seed = next(p for p in self.seeds.products if p.id == req.product_id)
        product = seed.model_copy(update={"sheet": req.sheet.sheet, "usage": req.sheet.usage}, deep=True)
        released = flow.release_product(req, product, self.kb, self.ledger, self.events, by, get_clock().now())
        if question:
            self._settle(question.id, Resolution(action="sign", by=by))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return released.model_copy(deep=True)

    def single_card_report(self, viewer_id):
        """WP-E2：只读已生成的单卡对照报告；L2/L3 看单卡明细，L1 只给模拟标注与三组统计。不跑评测、不读需求卡。"""
        level = level_of(self._actor(viewer_id))
        report = json.loads(Path("docs/reports/single_card/metrics.json").read_text(encoding="utf-8"))
        return report if level > 1 else {"simulated": report["simulated"], "stats": report["stats"]}

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
                title=unit.title if self.kb._readable(viewer, unit) else
                    f"{self.actors[unit.owner].name}的知识（L{unit.level}，仅显示归属）",
                n_cited=sum(e.reason == "cited" for e in entries), points=sum(e.points for e in entries),
                used_by=sorted({e.ref for e in entries})))
        return result

    @property
    def grants(self):
        return self.kb.decrypt_grants()

    def capabilities(self, viewer_id):
        self._actor(viewer_id, {"rd"})
        return [c for c in self.kb.capabilities() if c.granted_by == viewer_id and c.approved_by != "seed"]

    def candidate_claims(self, req_id, viewer_id):
        req, _ = self._requirement(req_id, viewer_id, {"rd"},
            {"draft", "rd_accepted", "rd_confirmed", "released", "rejected", "reused", "merged"})
        return [u.model_copy(deep=True) for u in self.kb._units.values()
                if u.kind == "claim" and u.status == "candidate"
                and req.phenomenon in u.phenomenon_ids]

    def confirm_claims(self, req_id, ku_ids, by):
        candidates = {u.id for u in self.candidate_claims(req_id, by)}
        if not set(ku_ids) <= candidates:
            raise ValueError("只能确认本单相关的候选结论")
        self.kb.confirm(ku_ids, by)
        self._after(req_ids=[req_id])
        self.scan()
        return self.requirement_view(req_id, by).requirement

    def sign_qi_grant(self, question_id, by, claim_ids=(), note=""):
        self._actor(by, {"rd"})
        q = _find(self.bus.questions, question_id, "问题")
        if q.family != "qi_grant" or q.status != "open" or q.prepared_at is None:
            raise ValueError("需要已准备的授予问题")
        if q.signer_id != by:
            raise PermissionDenied("只有结论确认人可以授予")
        if "requester" in q.refs:      # 同层申请查看：授予申请人本人，给归属人记「授予」分
            cap = self.kb.grant(Capability(id=self.kb.next_cap_id(), form="share", audience=q.refs["requester"],
                payload={"ku_id": q.refs["ku_id"]}, based_on=[q.refs["ku_id"]], granted_by=by,
                status="active", at=get_clock().now()))
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=by, points=self.config["points"]["shared"],
                                        reason="shared", ku_id=q.refs["ku_id"], ref=cap.id))
            self._settle(q.id, Resolution(action="sign", by=by, note=note))
            return cap
        if q.refs["form"] == "statement":     # 授予一句可说的话：措辞由研发改定，不得含结论原文或收件层看不到的结论
            unit, audience = self.kb._units[q.refs["ku_id"]], int(q.refs["audience"])
            if not note.strip() or leak_hits(note, [unit.text], [], self.kb, audience=audience):
                raise ValueError("措辞为空，或含结论原文、收件层不可见的内容")
            cap = self.kb.grant(Capability(id=self.kb.next_cap_id(), form="statement", audience=audience,
                payload={"text": note.strip(), "product_id": unit.product_id}, based_on=[unit.id],
                granted_by=by, status="active", at=get_clock().now()))
            self._settle(q.id, Resolution(action="sign", by=by, note=note))
            self.scan()
            return cap
        source = self.kb._caps[q.refs["capability_id"]]
        if claim_ids:
            if not set(claim_ids) <= set(source.based_on):
                raise ValueError("只能确认此项能力依据的结论")
            self.kb.confirm(claim_ids, by)
        cap = self.kb.grant(source.model_copy(update={"id": self.kb.next_cap_id(),
            "audience": int(q.refs["audience"]), "granted_by": by, "approved_by": None,
            "status": "active", "at": get_clock().now()}))
        self._settle(q.id, Resolution(action="sign", by=by, note=note))
        self.scan()
        return cap

    def request_share(self, ku_id, by):
        actor = self._actor(by, {"rd"})
        unit = _find(self.kb._units, ku_id, "知识")
        if unit.status != "active" or not colleague_l3(actor, unit) or self.kb._readable(actor, unit):
            raise ValueError("只能申请查看本人当前不可读的同层研发知识")
        self.events.append("share_requested", by, {"ku_id": ku_id, "owner": holder(unit),
                                                   "product_id": unit.product_id})
        return self.scan()

    def set_doc_level(self, doc_id, level, by):
        """人给内部文档定密级（片段密级表）；之后编译出的结论按新密级定级。"""
        self._actor(by, {"rd", "supervisor"})
        if not any(s.kind == "internal" and doc_id in s.list_docs() for s in self.kb.sources):
            raise ValueError(f"内部来源里没有文档 {doc_id}")
        self.kb._doc_levels[doc_id] = level
        self.kb._save()

    def recheck_evidence(self):
        """重取依据比指纹：变了的结论待复核、依赖它的能力挂起，由觉提出 qi_review。"""
        changed = recheck(self.kb, self.kb.sources)
        self._invalidate_capabilities("system")
        self.scan()
        return changed

    def revoke_capability(self, cap_id, by):
        self._actor(by, {"rd"})
        self.kb.revoke(cap_id, by)
        self._invalidate_capabilities(by)
        self.scan()

    def withdraw_claim(self, ku_id, by):
        self._actor(by, {"rd"})
        self.kb.withdraw(ku_id, by)
        for q in self.bus.list(family="qi_review"):
            if q.refs["ku_id"] == ku_id:
                self._settle(q.id, Resolution(action="answered", by=by, note="撤回结论"))
        self._invalidate_capabilities(by)
        self.scan()

    def _invalidate_capabilities(self, by):
        active = {c.id for c in self.kb.capabilities() if c.status == "active"}
        for session in self._sessions.values():
            if session.status in {"escalated", "closed"}:
                continue
            rec = session.recommendation
            selected = next((c for c in rec.candidates if c.product_id == rec.product_id), None) if rec else None
            # 命中的情境失效后，按本层现有情境重新匹配；收窄后仍覆盖已知条件的推荐保留
            if selected and selected.capability_id not in active and rec.product_id not in {
                    c.product_id for c in match_candidates(session.need.phenomenon, session.need.known(),
                        self.kb.view(self._actor(session.sales_id or session.customer_id)).products)}:
                session.recommendation, session.status = None, "open"
                self.events.append("recommendation_withdrawn", by, {"product_id": rec.product_id,
                                   "capability_id": selected.capability_id}, session_id=session.id)
            session.hints = self.ask_hints(session.need)
            self._save_session(session)

    def _use_capability(self, cap_id, session_id, by):
        capability = self.kb._caps[cap_id]
        if capability.status != "active":
            return
        if any(e.session_id == session_id and e.payload["capability_id"] == cap_id
               for e in self.events.query(["capability_used"])):
            return
        self.events.append("capability_used", by, {"capability_id": cap_id, "form": capability.form,
            "based_on": capability.based_on, "granted_by": capability.granted_by,
            "approved_by": capability.approved_by}, session_id=session_id)
        if capability.approved_by == "seed":   # 第 0 天迁移出的情境不是运行中人签的判断，不记分
            return
        owners ={self.kb._units[uid].confirmed_by for uid in capability.based_on}
        if capability.form == "applicable":
            owners.add(capability.approved_by)
        for owner in sorted(owners - {None, "seed", "pm:agent"}):
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=owner,
                points=self.config["points"]["used"], reason="used", ku_id=capability.based_on[0], ref=session_id))

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
            signer_role="rd", signer_id=product.owner,
            scored_by="human", discoverer="human", created_at=get_clock().now(),
            dedup_key=f"decrypt_request:{session_id}/{product.id}",
            evidence=[Evidence(summary="客户明确要求机理", quote=profile.evidence_quote)],
            refs={"session_id": session_id, "customer_id": session.customer_id, "product_id": product.id}))
        self.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="decrypt_request",
            object_ids=[q.id, product.id], session_id=session_id))
        self.events.append("decrypt_request", by, {"question_id": q.id, "customer_id": session.customer_id,
            "product_id": product.id}, session_id=session_id)
        return q.model_copy(deep=True)

    def decide_decrypt(self, question_id, by, approve, text=""):
        self._actor(by, {"rd"})
        question = _find(self.bus.questions, question_id, "问题")
        if question.family != "decrypt_request" or question.status != "open":
            raise ValueError("只能审批待处理的解密申请")
        if question.owner_id != by or self.kb.is_frozen(by):
            raise PermissionDenied("只有产品归属研发本人可审批")
        at, refs = get_clock().now(), question.refs
        if approve:
            self.kb.grant(Capability(id=self.kb.next_cap_id(), form="decrypt", audience=refs["customer_id"],
                payload={"product_id": refs["product_id"], "session_id": refs["session_id"], "text": text},
                based_on=[f"ku:mechanism:{refs['product_id']}"], granted_by=by, status="active", at=at))
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
        if q.bounty_points and resolution.action != "dismiss" and resolution.by not in {"pm:agent", "jue", "jue:auto"}:
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=resolution.by, points=q.bounty_points,
                                        reason="bounty", ref=q.id))
        return q

    def scan(self, at=None):
        at = at or get_clock().now()
        state, refs = collect_scheduled(self.events, at, self.seeds, self.kb.products(), self.config["windows"],
                                        self.kb.capabilities(), self.kb._units)
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
        allowed = {"knowledge_conflict": "update_sheet", "leak_risk": "freeze_access", "qi_review": "sign"}
        if action != "dismiss" and allowed.get(q.family) != action:
            raise ValueError(f"{q.family} 问题不能执行 {action}")
        if action == "update_sheet":
            pid, slot, value = q.refs["product_id"], *q.object_id.split("|")[1].split("=")
            for capability in self.kb.capabilities():
                if capability.form != "applicable" or capability.status != "active" or capability.payload["product_id"] != pid:
                    continue
                conditions = capability.payload["conditions"]
                current = conditions.get(slot, next(s.values for s in self.seeds.slots if s.id == slot))
                if value in current:
                    self.kb.revoke(capability.id, by)
                    payload = {**capability.payload, "conditions": {**conditions, slot: [v for v in current if v != value]}}
                    self.kb.grant(capability.model_copy(update={"id": self.kb.next_cap_id(), "payload": payload}))
            self.events.append("sheet_updated", by, {"product_id": pid, "slot": slot, "removed": value})
            self._invalidate_capabilities(by)
        elif q.family == "qi_review" and action == "sign":
            self.kb.confirm([q.refs["ku_id"]], by)
        elif action == "freeze_access":
            self.kb.freeze(q.refs["actor_id"], by, get_clock().now())
        return self._settle(question_id, Resolution(action=action, by=by, note=note)).model_copy(deep=True)

    def questions(self, viewer_id):
        viewer = self._actor(viewer_id, {"sales", "pm", "rd", "supervisor"})
        if viewer.role != "sales" and self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        questions = [q.model_copy(deep=True) for q in self.bus.list()
                     if viewer_id in (q.owner_id, q.signer_id) or (q.family == "decrypt_request"
                         and self._sessions[q.refs["session_id"]].sales_id == viewer_id)]
        for q in questions:
            if q.family == "qi_grant" and "requester" in q.refs:
                unit = self.kb._units[q.refs["ku_id"]]
                q.evidence.append(Evidence(summary=f"{self.actors[q.refs['requester']].name}申请查看：{unit.title}"))
            elif q.family == "qi_grant" and q.refs["form"] == "statement":
                unit = self.kb._units[q.refs["ku_id"]]
                ids = set(q.refs["retrieve_ids"].split(","))
                q.evidence += [Evidence(summary=f"L{q.refs['audience']} 被问到：{e.payload['query']}")
                               for e in self.events.query(["retrieve"]) if e.id in ids]
                q.evidence.append(Evidence(summary=f"{unit.title}；依据位置：{'；'.join(unit.evidence) or '研发直接判断'}",
                                           quote=unit.text))
            elif q.family == "qi_grant":
                cap = self.kb._caps[q.refs["capability_id"]]
                q.evidence.append(Evidence(summary=f"形式：{cap.form}；目标层：L{q.refs['audience']}"))
                for uid in cap.based_on:
                    unit = self.kb._units[uid]
                    q.evidence.append(Evidence(summary=f"{unit.title}；依据位置：{'；'.join(unit.evidence) or '研发直接判断'}",
                                               quote=unit.text))
        return questions

    def jue_timeline(self, target_id, viewer_id):
        viewer = self._actor(viewer_id, {"sales", "pm", "rd", "supervisor"})
        if viewer.role != "sales" and self.kb.is_frozen(viewer_id):
            raise PermissionDenied("高层级访问已冻结")
        if target_id in self._sessions:
            session = self._sessions[target_id]
            if viewer.role == "sales" and session.sales_id != viewer_id:
                raise PermissionDenied("只能查看自己负责的会话")
            sids = {target_id}
            req = next((r for r in reversed(list(self._requirements.values()))
                        if target_id in r.session_ids and r.status != "merged"), None)
        else:
            req = _find(self._requirements, target_id, "需求单")
            while req.merged_into:
                req = self._requirements[req.merged_into]
            sids = set(req.session_ids)
            if viewer.role == "sales":
                sids = {sid for sid in sids if self._sessions[sid].sales_id == viewer_id}
                if not sids:
                    raise PermissionDenied("只能查看自己负责的需求线程")
        rids = set()
        if req:
            rids.add(req.id)
            # 已实际合并的单属于线程；merge_from 在签字前仅是建议。
            for member in self._requirements.values():
                parent = member
                while parent.merged_into:
                    parent = self._requirements[parent.merged_into]
                if parent.id == req.id:
                    rids.add(member.id)
            if viewer.role != "sales":
                sids.update(req.session_ids)
        themes = {theme_id(e.payload["phenomenon"], e.payload["known"], self.seeds)
                  for e in self.events.query(["escalate"]) if e.session_id in sids}
        themes.update(theme_id(self._requirements[rid].phenomenon, self._requirements[rid].known_slots, self.seeds)
                      for rid in rids)
        objects = {f"session:{sid}" for sid in sids} | {f"requirement:{rid}" for rid in rids} | themes
        owners = sids | rids

        def visible(family, oid):
            if viewer.role == "sales":
                if family not in {"ask_slot", "escalate_need", "reuse_product", "market_eval", "ask_back"}:
                    return False
                if family in {"reuse_product", "market_eval", "ask_back"}:
                    rid = oid.removeprefix("slot:").rsplit("/", 1)[0] if family == "ask_back" else oid.removeprefix("requirement:")
                    if rid not in rids or self._requirements[rid].session_ids[0] not in sids:
                        return False
            return oid in objects or (oid.startswith("slot:") and oid[5:].rsplit("/", 1)[0] in owners)

        questions = [q for q in self.bus.list(status=None) if visible(q.family, q.object_id)]
        raised = {(q.family, q.object_id, q.created_at) for q in questions}
        points, judgments = [], 0
        for record in load_records(self.run_dir):
            ask_threshold = self.config["thresholds"]["ask_jue_k" if record.output.model == "jue_k" else "ask"]
            hints = {f"slot:{h.session_id}/{h.slot}" for h in select_asks(record.output, record.state,
                self.seeds, ask_threshold, self.config["thresholds"]["max_asks"])}
            decisions = [d for d in record.output.decisions if visible(d.family, d.object_id)]
            judgments += bool(decisions)
            for d in decisions:
                key = ("ask_jue_k" if record.output.model == "jue_k" else "ask") if d.family == "ask_slot" else (
                    "ask_jue_k" if d.family == "ask_back" and record.output.model == "jue_k" else "publish")
                points.append(TimelinePoint(at=record.output.at, family=d.family, object_id=d.object_id,
                    p_need=d.p_need, threshold=self.config["thresholds"][key],
                    scored_by=d.scored_by or record.output.scored_by,
                    raised=(d.family, d.object_id, record.output.at) in raised or
                           (d.family == "ask_slot" and d.object_id in hints)))
        nodes = [TimelineNode(question_id=q.id, family=q.family, owner_id=q.owner_id, signer_id=q.signer_id,
                    created_at=q.created_at, prepared_at=q.prepared_at, resolved_at=q.resolved_at,
                    action=q.resolution.action if q.resolution else None, by=q.resolution.by if q.resolution else None)
                 for q in questions]
        meter = [json.loads(line) for line in self.meter.path.read_text(encoding="utf-8").splitlines()] if self.meter.path.exists() else []
        return JueTimeline(target_id=target_id, viewer=viewer_id, points=sorted(points, key=lambda p: p.at),
            nodes=sorted(nodes, key=lambda n: n.created_at), n_judgments=judgments,
            n_llm_calls=sum(m["caller"].startswith("jue") and m["kind"] != "jue" for m in meter),
            n_questions=len(nodes), n_signatures=sum(q.resolution is not None and q.signer_id is not None
                and q.resolution.by == q.signer_id and q.resolution.action != "answered" for q in questions))

    _AUTO = {"escalate", "assign_sales"}

    def auto_execute(self, question_id):
        """契约 6.1：觉自动执行的内部入口，只由 hub 调用，不经 HTTP 暴露；只查表执行低风险推进。"""
        q = _find(self.bus.questions, question_id, "问题")
        action = self.templates[q.template_id].auto_action if q.template_id else None
        if q.status != "open" or q.signer_role is not None or action not in self._AUTO:
            raise ValueError("只能自动执行待处理、无签字人且带 auto_action 的问题")
        session = self._sessions[q.refs["session_id"]]
        if action == "escalate":
            self._escalate(session, "jue:auto", q)   # 内部以 action="auto" 结案
        else:
            self._assign_sales(session, "jue:auto")
            self.bus.resolve(q.id, Resolution(action="auto", by="jue:auto"), get_clock().now())
        self.events.append("auto_executed", "jue:auto", {"question_id": q.id, "family": q.family, "action": action,
            "p_need": q.p_need, "scored_by": q.scored_by}, session_id=session.id)
        return self.bus.get(q.id).model_copy(deep=True)

    def route_of(self, object_id, viewer_id):
        """v6：一份需求当前走哪条路、经过了谁、绕过了谁。全部由事件与状态推出，不另存。
        四格状态：human = 该角色的人真实处理过；auto = 由 Agent / 觉代办；pending = 已到该角色、待处理；none = 未经过。"""
        viewer = self._actor(viewer_id)
        if object_id in self._requirements:
            object_id = self._requirements[object_id].session_ids[0]
        session = _find(self._sessions, object_id, "会话")
        if level_of(viewer) <= 1 and viewer_id not in (session.customer_id, session.sales_id):
            raise PermissionDenied("只能查看自己参与的会话")
        reqs = [r for r in self._requirements.values() if session.id in r.session_ids]
        main = next((r for r in reversed(reqs) if r.status != "merged"), None)
        rids = {r.id for r in reqs}
        events = [e for e in self.events.query() if e.session_id == session.id
                  or e.payload.get("requirement_id") in rids or e.payload.get("target") in rids
                  or rids & set(e.payload.get("requirement_ids", []))]
        linked = [q for q in self.bus.list(status=None)        # 挂在知识对象上、由这张单引出的决策（扩适用范围）
                  if rids & set(q.refs.get("requirement_ids", "").split(","))]
        steps = _human_events(events)
        humans = lambda role: sorted({e.actor for e in steps if e.actor.startswith(f"{role}:")})
        sales, pm, rd = humans("sales"), humans("pm"), humans("rd")
        if any(t.speaker == "sales" for t in session.turns) and session.sales_id not in sales:
            sales = sorted([*sales, session.sales_id])
        open_rd = main is not None and main.status == "draft"
        roles = {
            "customer": {"state": "human" if any(t.speaker == "customer" for t in session.turns) else "none",
                         "by": [session.customer_id]},
            "sales": {"state": "human" if sales else "pending" if session.sales_id else "none",
                      "by": sales or ([session.sales_id] if session.sales_id else [])},
            "pm": {"state": "human" if pm else "pending" if any(q.status == "open" for q in linked) else "auto" if main else "none",
                   "by": pm or sorted({q.signer_id for q in linked if q.signer_id}) or (["pm:agent"] if main else [])},
            "rd": {"state": "human" if rd else "pending" if open_rd else "none",
                   "by": rd or ([main.assigned_rd] if open_rd else [])},
        }
        path = ("产品机会" if any(e.kind == "requirements_merged" for e in events) else
                "复用" if main and main.status == "reused" else
                "研发不立项" if main and main.status == "rejected" else "入研" if main else
                "交业务员" if session.origin == "customer" and session.sales_id else
                "自助解决" if session.status == "recommended" else "追问中")
        inner = level_of(viewer) >= 2      # L0/L1 只看会话上的决策，不看研发、产品经理的结案备注
        objects = {f"session:{session.id}"} | ({f"requirement:{rid}" for rid in rids} if inner else set())
        merges = {e.payload["question_id"] for e in events if e.kind == "requirements_merged"} if inner else set()
        basis = [{"question_id": q.id, "family": q.family, "title": q.title, "p_need": q.p_need,
                  "scored_by": q.scored_by, "status": q.status,
                  "action": q.resolution.action if q.resolution else None,
                  "by": q.resolution.by if q.resolution else None,
                  "note": q.resolution.note if q.resolution and inner else ""}
                 for q in self.bus.list(status=None) if q.object_id in objects or q.id in merges
                 or (inner and q in linked)]
        # 为什么直达研发：升级时那次匹配查过哪些现有产品、Jev 判「都不合适」的概率、由谁升级；
        # 以及声明能解决这类现象、但按客户条件被排除的已发布产品（适用范围是说明书上的公开信息）；
        # 与客户条件不冲突却不在候选里的，是升级之后才扩进这类现象的（如 C′ 扩范围），不算当时被排除
        esc = next((e for e in events if e.kind == "escalate"), None)
        match = next((e.payload for e in reversed(events) if e.kind == "match" and e.ts <= esc.ts), None) if esc else None
        why = None
        if match:
            known = match["known"]
            mismatches = {p.id: [{"slot": k, "value": known[k], "allowed": v}
                                 for situation in p.situations for k, v in situation.conditions.items()
                                 if k in known and known[k] not in v]
                          for p in self.kb.products() if p.status == "released" and match["phenomenon"] in p.solves
                          and p.id not in match["candidate_ids"] and not consistent(p, known)}
            excluded = [{"product_id": pid, "mismatch": m} for pid, m in mismatches.items() if m]
            why = {"by": esc.actor, "phenomenon": match["phenomenon"], "p_none": match["p_none"],
                   "scored_by": match["scored_by"], "excluded": excluded,
                   "candidates": [{"product_id": pid, "p": match["p_choice"][pid]} for pid in match["candidate_ids"]]}
        return {"session_id": session.id, "requirement_id": main.id if main else None, "origin": session.origin,
                "path": path, "roles": roles, "basis": basis, "why": why,
                "quote": next((t.text for t in session.turns if t.speaker == "customer"), ""),
                "n_human_steps": len(steps)}

    def workload(self, viewer_id):
        """v6.1 E6：本人的工作分两组——被系统拿掉的无效工作（因信息缺失、转述、重复而被迫发生的）与保留的专业判断。
        全部由事件日志计数，不另存。"""
        viewer = self._actor(viewer_id, {"sales", "pm", "rd"})
        events = self.events.query()
        count = lambda kind, **kw: sum(e.kind == kind and all(e.payload.get(k) == v for k, v in kw.items())
                                       for e in events)
        by_me = lambda kind: sum(e.kind == kind and e.actor == viewer_id for e in events)
        scope_hits = lambda caps: sum(e.kind == "capability_used" and e.payload["capability_id"] in caps for e in events)
        mine_cust = lambda s: viewer.role != "sales" or self.config["customer_sales"].get(s.customer_id) == viewer_id
        confirmed = lambda s: any(c.product_id == s.recommendation.product_id and c.status == "confirmed"
                                  for c in s.recommendation.candidates)   # 「可能适用」不算自助解决
        self_served = sum(s.origin == "customer" and s.status == "recommended" and confirmed(s) and mine_cust(s) and
                          not any(s.id in r.session_ids for r in self._requirements.values())
                          for s in self._sessions.values())
        auto_escalated = sum(e.kind == "auto_executed" and e.payload["action"] == "escalate"
                             and mine_cust(self._sessions[e.session_id]) for e in events)
        if viewer.role == "rd":
            judged = {c.id for c in self.kb.capabilities() if c.form == "applicable" and c.granted_by == viewer_id
                      and c.approved_by != "seed"}
            mine = [r for r in self._requirements.values() if r.assigned_rd == viewer_id]
            asked = sum(self.readiness(r.id, viewer_id)["n_asked_by_jue"] for r in mine if r.status != "merged")
            merged = sum(len(e.payload["members"]) for e in events if e.kind == "requirements_merged"
                         and self._requirements[e.payload["target"]].assigned_rd == viewer_id)
            removed = [("开工前觉已替你问清的必问条件", asked, "不用拿着半截需求回头找业务员补问"),
                       ("因信息不全退回", by_me("requirement_returned"), "退回越少，说明进研发的需求越完整"),
                       ("重复需求合并，少收的单", merged, "产品经理附商业判断汇成一个课题"),
                       ("同类需求客户自助解决（不再进研发）", scope_hits(judged), "你判一次「已有产品适用」，组织记住"),
                       ("常规问题客户自助解决", self_served, "现有产品能解决的，不占用研发")]
            kept = [("接单立项", by_me("requirement_accepted")), ("不立项判断", by_me("project_declined")),
                    ("确认化学要点", by_me("requirement_translated")), ("试样", by_me("trial")),
                    ("审定发布", by_me("product_released"))]
        elif viewer.role == "pm":
            removed = [("逐单转述（产品经理 Agent 已后台转译）", sum(r.drafted_by == "pm:agent" for r in self._requirements.values()),
                        "你不用再把每张单转述一遍")]
            extended = {e.payload["capability_id"] for e in events if e.kind == "scope_extended" and e.actor == viewer_id}
            kept = [("扩展产品适用范围", len(extended)), ("此后因此自动解决的需求", scope_hits(extended)),
                    ("签产品机会（附商业判断）", by_me("requirements_merged")),
                    ("纠正研发退回的需求", sum(e.kind == "requirement_edited" and e.actor == viewer_id
                                             and e.payload.get("layer") == 2 and e.payload["index"] >= 0 for e in events)),
                    ("沉淀产品需求知识", by_me("l2_contributed"))]
        else:
            removed = [("回答技术问题（客户自助解决）", self_served, "常规问题客户自己就拿到推荐和公开案例"),
                       ("签字升级（觉自动升级）", auto_escalated, "现有产品解决不了时，需求带原话直达研发"),
                       ("转述与重填需求", 0, "转来的商务事项带完整原话和已推荐产品")]
            kept = [("商务事项（报价、采购）", count("sales_assigned", sales_id=viewer_id)),
                    ("录入客户评价", by_me("market_eval"))]
        return {"removed": [{"label": l, "n": n, "note": note} for l, n, note in removed],
                "kept": [{"label": l, "n": n} for l, n in kept]}

    def mark_prepared(self, question_id, by):
        """由 hub 在主人准备完毕后调用；只标待签，不签字、不推进业务。"""
        self._actor(by, {"sales", "pm", "rd", "supervisor"})
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
