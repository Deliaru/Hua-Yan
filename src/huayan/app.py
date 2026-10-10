"""应用门面：负责身份与视图边界，界面只调用这里。"""
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (AuditRecord, CitedKnowledge, ContributionStat, DecryptGrant,
    Evidence, KnowledgeUnit, LedgerEntry, NeedState, Question, ReqItem, Requirement,
    RequirementView, Resolution, RunStatus, Session, SessionView, SheetDraft, Trial)
from huayan.domain import consistent, load_seeds
from huayan.escalation import flow
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.jev import Jev
from huayan.jev.system1 import build_system1
from huayan.knowledge import AuditLog, KnowledgeBase, Ledger, PermissionDenied, level_of
from huayan.knowledge.disclosure import VERSIONS, cap, render
from huayan.l1.extract import LLMExtractor, RuleExtractor
from huayan.l1.session import handle_turn, recommend, record_disclosure, required_hints
from huayan.meter import FileMeter


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
        app.ask_hints = lambda need: required_hints(need, app.seeds, app.config["thresholds"]["max_asks"])
        return app

    def _actor(self, actor_id, roles=None):
        actor = self.actors.get(actor_id)
        if actor is None:
            raise PermissionDenied("未知身份")
        if roles is not None and actor.role not in roles:
            raise PermissionDenied("当前身份无权执行此动作")
        return actor

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
        return session.model_copy(deep=True)

    def add_turn(self, session_id, speaker, text):
        if speaker not in ("customer", "sales") or not text.strip():
            raise ValueError("需要有效发言角色与非空文本")
        previous = self._sessions[session_id].need
        session = handle_turn(self._sessions[session_id], speaker, text, self)
        if (previous.phenomenon, previous.known()) != (session.need.phenomenon, session.need.known()):
            for req in self._requirements.values():
                if req.status == "draft" and session_id in req.session_ids:
                    self._retire_draft(req)
        self._save_session(session)
        return session.model_copy(deep=True)

    def recommend_now(self, session_id):
        session = recommend(self._sessions[session_id], self)
        self._save_session(session)
        return session.model_copy(deep=True)

    def view_session(self, session_id, viewer_id):
        viewer, session = self._actor(viewer_id), self._sessions[session_id]
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
            requirement=req).model_copy(deep=True)

    def sessions(self):
        return [s.model_copy(deep=True) for s in self._sessions.values()]

    def jue_trace(self, session_id):
        self._sessions[session_id]
        return []

    def status(self):
        return RunStatus(run_id=self.run_id, replay=self.config["replay"],
            system1_impl=self.config["system1_impl"], realtime_model="required_stub",
            extractor=self.extractor.name, gateway_mock=self.config["gateway_mock"],
            seeds_placeholder=self.seeds.placeholder)

    def _requirement(self, req_id, by, roles, states):
        actor = self._actor(by, roles)
        if self.kb.is_frozen(by):
            raise PermissionDenied("高层级访问已冻结")
        req = self._requirements[req_id]
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
            except (KeyError, PermissionDenied) as exc:
                raise ValueError("知识引用不存在或当前身份无权读取") from exc

    def _retire_draft(self, req):
        # 契约已有 rejected 状态用于废止旧草稿，保留原内容和引用供核对。
        req.status = "rejected"
        self._save_requirement(req)
        question = self.bus.get(req.question_id)
        if question.status == "open":
            self.bus.publish(question.model_copy(update={"evidence": [Evidence(
                summary=f"草稿 {req.id} 已失效：需求条件变化，需重新起草并核对后确认")]}))

    def _draft_needs_review(self, req):
        sessions = [self._sessions[sid] for sid in req.session_ids]
        known = sessions[0].need.known()
        for session in sessions[1:]:
            known = {key: value for key, value in known.items() if session.need.known().get(key) == value}
        return (any(s.need.phenomenon != req.phenomenon for s in sessions) or known != req.known_slots or
                any(e.ts > req.created_at and e.session_id in req.session_ids and e.payload.get("conditions_changed")
                    for e in self.events.query(kinds=["extraction"], since=req.created_at)))

    def draft_requirement(self, question_id, by):
        actor = self._actor(by, {"pm"})
        if self.kb.is_frozen(by):
            raise PermissionDenied("高层级访问已冻结")
        question = self.bus.get(question_id)
        if question.family not in ("escalate_need", "opportunity") or question.status != "open":
            raise ValueError("只能为待处理的升级或机会汇聚起草需求")
        if question.owner_id is not None and question.owner_id != by:
            raise PermissionDenied("问题已指派给其他负责人")
        existing = next((r for r in reversed(list(self._requirements.values()))
                         if r.question_id == question_id and r.status != "rejected"), None)
        if existing and existing.status == "draft" and self._draft_needs_review(existing):
            self._retire_draft(existing)
            existing = None
        if existing:
            return self.requirement_view(existing.id, by).requirement
        ids = question.refs.get("session_ids", question.refs.get("session_id", "")).split(",")
        sessions = [self._sessions[sid] for sid in dict.fromkeys(ids) if sid]
        if not sessions or not sessions[0].need.phenomenon:
            raise ValueError("需求必须关联已识别现象的会话")
        phenomenon = sessions[0].need.phenomenon
        if any(s.need.phenomenon != phenomenon for s in sessions):
            raise ValueError("一个需求单必须属于同一现象")
        known = sessions[0].need.known()
        for session in sessions[1:]:
            known = {key: value for key, value in known.items() if session.need.known().get(key) == value}
        from huayan.escalation import translate  # WP-T 提供；不另造转译实现。
        draft = translate.draft_product_need(question, sessions, self.kb, actor, get_clock().now())
        req = Requirement(id=f"req:{len(self._requirements) + 1}", question_id=question_id,
            session_ids=[s.id for s in sessions], phenomenon=phenomenon, known_slots=known,
            direction=draft.direction, product_lang=draft.product_lang, status="draft", drafted_by=by,
            created_at=get_clock().now())
        for item in req.product_lang:
            self._validate_item(req, item, actor)
        self._requirements[req.id] = req
        return self._save_requirement(req, viewer_id=by)

    def edit_req_item(self, req_id, index, item: ReqItem, by):
        actor = self._actor(by, {"pm", "rd"})
        req, _ = self._requirement(req_id, by, {actor.role},
                                   {"draft"} if actor.role == "pm" else {"pm_confirmed"})
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
                                   {"draft"} if actor.role == "pm" else {"pm_confirmed"})
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

    def confirm_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"pm"}, {"draft", "rejected"})
        if req.status == "rejected" or self._draft_needs_review(req):
            if req.status == "draft":
                self._retire_draft(req)
            raise ValueError("草稿已失效，需求条件需重新核对；请重新起草并核对后确认")
        if self.bus.get(req.question_id).status != "open":
            raise ValueError("关联问题已非待处理状态，不能确认旧草稿")
        if not req.product_lang:
            raise ValueError("需求单没有产品需求条目")
        for item in req.product_lang:
            self._validate_item(req, item, actor)
        req.status, req.pm_confirmed_by = "pm_confirmed", by
        self.events.append("requirement_confirmed", by,
            {"requirement_id": req.id, "phenomenon": req.phenomenon, "known": req.known_slots})
        self.bus.resolve(req.question_id, Resolution(action="draft_requirement", by=by), get_clock().now())
        return self._save_requirement(req, viewer_id=by)

    def translate_requirement(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"pm_confirmed"})
        from huayan.escalation import translate
        draft = translate.draft_chem_need(req.model_copy(deep=True),
            [self._sessions[sid].model_copy(deep=True) for sid in req.session_ids], self.kb, actor, get_clock().now())
        for item in draft.chem_lang:
            self._validate_item(req, item, actor)
        req.chem_lang, req.hypotheses, req.chem_drafted_by = draft.chem_lang, draft.hypotheses, by
        return self._save_requirement(req, viewer_id=by)

    def confirm_translation(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"pm_confirmed"})
        if not req.chem_lang:
            raise ValueError("请先起草化学语言条目")
        for item in req.chem_lang:
            self._validate_item(req, item, actor)
        products = sorted((p for p in self.seeds.products if p.status == "project"
            and req.phenomenon in p.solves and consistent(p, req.known_slots)), key=lambda p: p.id)
        if not products:
            raise ValueError("没有覆盖该需求的研发中产品，暂不能确认")
        req.product_id, req.status, req.rd_confirmed_by = products[0].id, "rd_confirmed", by
        refs = sorted({ref for item in req.product_lang + req.chem_lang for ref in item.ku_refs})
        for ref in refs:
            unit = self.kb.get(ref, actor)
            if not self.ledger.has(unit.owner, ref, req.id):
                self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=unit.owner, ku_id=ref, ref=req.id,
                    points=self.config["points"]["cited"], reason="cited"))
        self.events.append("requirement_translated", by, {"requirement_id": req.id, "ku_refs": refs})
        return self._save_requirement(req, viewer_id=by)

    def contribute_translation(self, req_id, item_index, scene_phrase, chem_term, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"pm_confirmed", "rd_confirmed"})
        if not 0 <= item_index < len(req.chem_lang) or not scene_phrase.strip() or not chem_term.strip():
            raise ValueError("需要有效化学条目索引、原文与译文")
        unit = flow.contribute_translation(req, item_index, scene_phrase, chem_term,
            actor, self.kb, self.ledger, self.events, get_clock().now())
        if req.status == "rd_confirmed":
            self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=by, ku_id=unit.id, ref=req.id,
                                       points=self.config["points"]["cited"], reason="cited"))
        self._save_requirement(req)
        return unit

    def set_public_points(self, req_id, text, by):
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        if not text.strip():
            raise ValueError("对外要点不能为空")
        req.public_points, req.sheet = text, None
        return self._save_requirement(req, viewer_id=by)

    def requirements(self, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        return [self.requirement_view(req.id, viewer_id).requirement for req in self._requirements.values()]

    def requirement_view(self, req_id, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
        if self.kb.is_frozen(viewer.id):
            raise PermissionDenied("高层级访问已冻结")
        req = self._requirements[req_id].model_copy(deep=True)
        # 契约允许 L2 看化学需求条目，但机理假设与所引知识原文仅对 L3 开放。
        if level_of(viewer) < 3:
            req.hypotheses = []
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
        return trial.model_copy(deep=True)

    def package_sheet(self, req_id, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"rd_confirmed"})
        if not req.public_points:
            raise ValueError("请研发先确认对外要点")
        from huayan.escalation import translate
        # 传入副本且移除化学条目、假设，包装过程只得到允许的信息。
        public = req.model_copy(update={"chem_lang": [], "hypotheses": []}, deep=True)
        req.sheet = translate.package_sheet(public)
        self._save_requirement(req)
        return req.sheet.model_copy(deep=True)

    def save_sheet(self, req_id, sheet: SheetDraft, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"rd_confirmed"})
        if not req.public_points or not sheet.sheet.strip() or not sheet.usage.strip():
            raise ValueError("需要研发对外要点以及非空说明书和用法")
        req.sheet = sheet.model_copy(deep=True)
        return self._save_requirement(req, viewer_id=by)

    def release_product(self, req_id, by):
        req, _ = self._requirement(req_id, by, {"pm"}, {"rd_confirmed"})
        if not req.sheet or not req.product_id or not req.public_points:
            raise ValueError("发布需要关联产品、对外要点与说明书")
        if not any(t.requirement_id == req.id and t.result == "pass" for t in self._trials.values()):
            raise ValueError("发布前需要本需求单的通过试样")
        if any(p.id == req.product_id for p in self.kb.products()):
            raise ValueError("该产品已经发布")
        seed = next(p for p in self.seeds.products if p.id == req.product_id)
        product = seed.model_copy(update={"sheet": req.sheet.sheet, "usage": req.sheet.usage}, deep=True)
        released = flow.release_product(req, product, self.kb, self.ledger, self.events, by, get_clock().now())
        self._save_requirement(req)
        # 发布者为 L2；完整机理和配方保存在知识库，只返回公开产品字段。
        return released.model_copy(update={"mechanism": "", "formula": ""}, deep=True)

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
        session = self._sessions[session_id]
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
        question = self.bus.get(question_id)
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
