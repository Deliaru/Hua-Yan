"""应用门面：负责身份与视图边界，界面只调用这里。"""
import json
import threading
import time
from contextlib import contextmanager
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.agent import AgentHub
from huayan.bus import QuestionBus
from huayan.clock import get_clock
from huayan.contracts import (KIND_LEVEL, Actor, Candidate, Capability, AuditRecord, CitedKnowledge, ContributionDraft, ContributionStat, DecryptGrant,
    Evidence, JueRecord, JueState, KnowledgeUnit, LedgerEntry, MemoryEntry, NeedState, PendingAsk, PointsDraft, Question, Recommendation, ReqItem, Requirement,
    RequirementView, Resolution, ReuseProposal, ReuseView, RunStatus, Session, SessionView, SheetDraft, Trial,
    JueTimeline, Product, SHANGHAI, Situation, TimelineNode, TimelinePoint)
from huayan.domain import consistent, load_seeds, match_candidates, temperature_match
from huayan.escalation import flow
from huayan.escalation.translate import leak_hits
from huayan.events import EventLog
from huayan.gateway import build_gateway
from huayan.jev import Jev
from huayan.jev.system1 import build_system1
from huayan.jue.jue_k import JueK
from huayan.jue.proto import JueProto, judge_level, load_templates, rule_score
from huayan.jue.publish import describe, publish, select_asks
from huayan.jue.records import _human_level, load_records
from huayan.jue.state import collect_scheduled, realtime_state, requirement_state, session_state, theme_id
from huayan.ingest.compile import admit, propose, recheck
from huayan.ingest.folder import FolderSource
from huayan.ingest.trial_ir import EvidenceReportSource, OperationIR
from huayan.ingest.reader.source import read_source, read_trial_record, read_source_image, readable_sources
from huayan.ingest.reader.library import LibrarySource, search_library, search_many
from huayan.ingest.reader.image import ask_image
from huayan.knowledge import AuditLog, KnowledgeBase, Ledger, PermissionDenied, level_of
from huayan.knowledge.permission import colleague_l3, holder, can_read
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


class _Held(threading.local):
    ids = None      # 助手起草期间暂存的 (会话, 需求单)；None = 不暂存。按线程分开，模拟器并发准备互不影响
    agent_drafting = False   # Hub 工具执行期间的来源标记；按线程分开，试用实例里等模型时别人的写操作不会被记成 Agent 起草


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
        for q in app.bus.list(family="scope_update"):   # 续跑时产品线编制若已改，待批准范围交现任产品经理签字
            pm = app._line_pm(q.refs.get("phenomenon"))   # V8 的旧运行里扩范围决策没有记现象，照原签字人
            if pm and q.signer_id != pm:
                q.signer_id = pm
                app.bus.publish(q)                      # 同 dedup_key 的开放问题：只追加快照落盘
        app.kb = KnowledgeBase.from_seeds(app.seeds, app.events, app.audit,
            state_path=app.config.get("qi_state") or app.run_dir / "qi_state.json")
        app._load_public(Path(app.config["seeds_dir"]) / "public.yaml")
        app.kb.sources = [EvidenceReportSource(s["root"]) if Path(s["root"]).suffix == ".json" else
                         LibrarySource(s["name"], s["kind"], s["root"]) if s.get("library") else
                         FolderSource(s["name"], s["kind"], s["root"], s.get("level"), app.kb._doc_levels)
                          for s in app.config["sources"]]
        manifest = app.config.get("source_manifest")
        app.source_owners = {s["source_id"]: s["owner_actor_id"] for s in
                            json.loads(Path(manifest).read_text(encoding="utf-8"))["sources"]} if manifest else {}
        for source in app.kb.sources:
            if isinstance(source, LibrarySource):
                app.source_owners |= source.owners      # V11.13 资料库的归属在它自己的清单里
        app._wire_models(byok)
        app._sessions = {s.id: s for s in map(Session.model_validate_json, _read_dir(app.run_dir / "sessions"))}
        app._requirements = {r.id: r for r in map(Requirement.model_validate_json, _read_dir(app.run_dir / "requirements"))}
        app.seeds.products += [Product.model_validate(e.payload["product"]) for e in app.events.query(["project_opened"])]
        memory = app.run_dir / "memory.json"
        app._memory = {m.id: m for m in map(MemoryEntry.model_validate,
                                            json.loads(memory.read_text(encoding="utf-8")) if memory.exists() else [])}
        app._trials = {t.id: t for t in (Trial.model_validate_json(u.text) for u in app.kb._units.values()
                                         if u.kind == "trial" and u.source == "trial")}
        app.templates = load_templates(app.config["templates_dir"])
        app._wire_jue()
        app._jue_trace, app._answers = {}, {}
        app._watch, app._shadow = {}, {}    # V12.8 觉雷达：每个对象最近一次被觉评估的结果；对照用的 Jue-K
        app._last_scan = None
        app._held = _Held()
        app._drafts = {}     # 线程 → 它正在起草的需求单；别的线程写后评估时跳过，由起草的线程结束时评估
        app.progress = None          # 界面过程面板的进度回调（ui.server 设置）；只报「谁在做什么、用时」
        app.agents = AgentHub(app)
        return app

    @property
    def _agent_drafting(self):
        """Hub 工具执行期间的来源标记，不由模型或 HTTP 参数指定。"""
        return self._held.agent_drafting

    @_agent_drafting.setter
    def _agent_drafting(self, value):
        self._held.agent_drafting = value

    def _wire_models(self, byok=None):
        """网关、Jev（System 1）与抽取器；换模型配置时只重接这几样，业务对象原样保留。"""
        if byok:
            self.gateway = byok.gateway(self.meter)
            self.system1 = byok.system1(self.gateway, self.meter)
        else:
            self.gateway = build_gateway(self.config["models_config"], self.config["gateway_mock"], self.meter)
            if not self.config["gateway_mock"]:
                cache = self.config.get("llm_cache_dir")
                self.gateway.cache_dir = Path(cache) if cache else None
                self.gateway.replay = self.config["replay"]
            self.system1 = build_system1(self.config["system1_impl"], self.config.get("system1_config", "config/system1.yaml"),
                                         self.gateway, self.meter)
        self.jev = Jev(self.system1, self.config["thresholds"]["match"])
        self.extractor = (RuleExtractor(self.seeds) if self.config["extractor"] == "rule"
                          else LLMExtractor(self.seeds, self.gateway))

    def _wire_jue(self):
        self.jue_realtime = self._jue_model(self.config["realtime_model"], "realtime")
        self.jue_scheduled = self._jue_model(self.config["scheduled_model"], "scheduled")

    def switch_models(self, **changes):
        """V9.1：试用中换模型配置（models_config、system1_impl、system1_config）。新客户端建好后才替换，门面与业务原样保留。"""
        unknown = set(changes) - {"models_config", "system1_impl", "system1_config"}
        if unknown:
            raise ValueError(f"只能换模型配置：{sorted(unknown)}")
        names = ("config", "gateway", "system1", "jev", "extractor", "jue_realtime", "jue_scheduled")
        old = {n: getattr(self, n) for n in names}
        self.config = old["config"] | changes
        try:
            self._wire_models()
            self._wire_jue()
        except Exception:
            if self.system1 is not old["system1"]:
                self.system1.close()
            for n, v in old.items():
                setattr(self, n, v)
            raise
        old["system1"].close()
        return self.status()

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
        model = (JueK(self.config["jue_k_dir"], self.config["templates_dir"], mode, self.meter) if name == "jue_k"
                 else JueProto(self.config["templates_dir"], self.system1, mode, self.meter))
        off = set(self.config.get("jue_off", ()))      # V9.6a：配置里停用的觉家族（试用停用 leak_risk）
        model.templates = {k: t for k, t in model.templates.items() if t.family not in off}
        return model

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
        if out.mode == "scheduled":       # 定时扫描每次看全部对象，上一次看过、这次不在的不再算「正在看」
            self._watch = {k: v for k, v in self._watch.items() if v[0] == "realtime"}
        passed = defaultdict(list)
        for d in out.decisions:
            if d.precondition_passed:
                passed[d.object_id].append(d)
        self._watch |= {oid: (out.mode, out.model, obj, passed[oid], out.at) for oid, obj in state.objects.items()}
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

    def _close_stale(self, out, object_ids, req_ids=()):
        """觉再看（v8 收口，所有问题）：评估过的对象上，前提不再成立或对象已不在活动中的问题由觉结案；
        签字人的签字由门面方法结案自己的问题，门面方法不替别的问题结案。"""
        live = {(d.family, d.object_id) for d in out.decisions if d.precondition_passed}
        prefixes = tuple(f"slot:{rid}/" for rid in req_ids)
        for q in self.bus.list():
            seen = q.object_id in object_ids or (prefixes and q.object_id.startswith(prefixes))
            if seen and (q.family, q.object_id) not in live:
                self.bus.resolve(q.id, Resolution(action="answered", by="jue", note="情况已变"), out.at)

    @contextmanager
    def drafting(self):
        """v8 收口：助手起草期间写后评估先记下受影响的会话与需求单，起草结束后评估一次——觉看的是准备好的对象，
        不是中间稿。可嵌套，最外层结束时评估。"""
        if self._held.ids is not None:
            yield
            return
        self._held.ids = (set(), set())
        self._drafts[threading.get_ident()] = self._held.ids[1]
        try:
            yield
        finally:
            (session_ids, req_ids), self._held.ids = self._held.ids, None
            self._drafts.pop(threading.get_ident())
            if session_ids or req_ids:
                self._after(session_ids, req_ids)

    def _after(self, session_ids=(), req_ids=()):
        """写后评估会话及关联需求单；只提出决策，不派单或执行下一步。"""
        if self._held.ids is not None:
            self._held.ids[0].update(session_ids)
            self._held.ids[1].update(req_ids)
            return []
        at = get_clock().now()
        session_ids = set(session_ids)
        req_ids = set(req_ids) | {r.id for r in self._requirements.values()
                                 if session_ids.intersection(r.session_ids)}
        req_ids -= set().union(*list(self._drafts.values()))     # 别的线程还在起草的单，等它起草完再评估
        state = JueState(at=at, mode="realtime", objects={})
        refs = {}
        for sid in sorted(session_ids):
            sess = self._sessions[sid]
            objects = session_state(sess, self.events, at).objects
            state.objects.update(objects)
            refs.update({oid: {"session_id": sid, "sales_id": sess.sales_id,
                               "account_sales": self.config["customer_sales"].get(sess.customer_id)} for oid in objects})
        for rid in sorted(req_ids):
            req = self._requirements[rid]
            sess = self._sessions[req.session_ids[0]]
            objects = requirement_state(req, sess.need, self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, at, self.events).objects
            state.objects.update(objects)
            refs.update({oid: {"session_id": sess.id, "sales_id": sess.sales_id, "requirement_id": rid,
                               "account_sales": self.config["customer_sales"].get(sess.customer_id),
                               "assigned_rd": req.assigned_rd, "pm": self._line_pm(req.phenomenon)} for oid in objects})
        out = self._propose(self.jue_realtime, state)
        for sid in session_ids:
            self._jue_trace.setdefault(sid, []).append(out)
        self._close_stale(out, set(state.objects) | {f"requirement:{rid}" for rid in req_ids}, req_ids)
        thresholds = self.config["thresholds"]
        ready = out.model_copy(update={"decisions": [d for d in out.decisions
            if d.p_need is not None and d.p_need >= thresholds[
                "ask_jue_k" if d.family == "ask_back" and out.model == "jue_k" else "publish"]]})
        return publish(ready, state, self.templates, self.bus, 0, seeds=self.seeds, refs=refs)

    def _line_pm(self, phenomenon):
        """v8 企业编制：分管该现象产品线的产品经理；没有配置时为 None，解析表取唯一的真人产品经理。"""
        return self.config["pm_lines"].get(phenomenon)

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
        session = handle_turn(current, speaker, text, self, answering=bool(asks),
                              asking=[q.refs["slot"] for q in asks[:1]])     # V9.3：自助页一次显示一条回问
        answered = self._answer_ask_back(session, asks) if speaker == "customer" else set()
        # v8 收口：客户补条件只走一条路——会话里补的、回问答的，起草中的单都按会话条件重写，未经人改的条目清掉重写
        changed = (previous.phenomenon, previous.known(), previous.known_temperature()) != (
            session.need.phenomenon, session.need.known(), session.need.known_temperature())
        for req in self._requirements.values():
            if req.status == "draft" and session_id in req.session_ids and (changed or req.id in answered):
                req.phenomenon, req.known_slots = session.need.phenomenon, session.need.known()
                req.product_lang = [item for item in req.product_lang if item.edited_by]
                self._return_to_preparation(req)
                self._save_requirement(req)
            elif req.status == "rd_accepted" and session_id in req.session_ids and (changed or req.id in answered):
                self._conditions_changed(req, session.need.known() if changed else req.known_slots)
        if speaker == "sales":
            session.reply_draft = ""
        self._save_session(session)
        self._after([session_id])
        return session.model_copy(deep=True)

    def _conditions_changed(self, req, known):
        """V9.6a：已接单的单在返工中条件变了——产品稿里 Agent 起草的部分按新条件重写，化学稿里 Agent 起草的条目清掉、
        由研发 Agent 重新起草；人改过的条目保留，退回说明里请研发按新条件重新确认。待签问题回到准备中。"""
        req.known_slots = dict(known)
        from huayan.escalation import translate
        draft = translate.draft_product_need(req, [self._sessions[sid] for sid in req.session_ids],
                                              self.kb, self._actor("pm:agent"), get_clock().now())
        edited = [i for i in req.product_lang if i.edited_by]
        req.product_lang = edited + [i for i in draft.product_lang if not any(
            (i.slot == old.slot if i.slot or old.slot else set(i.quote_refs) & set(old.quote_refs)) for old in edited)]
        req.chem_lang = [i for i in req.chem_lang if i.edited_by]
        if edited or req.chem_lang:
            req.return_notes.append("客户条件有变化，人改过的条目请按新条件重新确认")
        self._return_to_preparation(req)
        self._save_requirement(req)

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
        # v8：回问提出之后客户开口时，这个槽位已有答案（填上或答了不清楚）就结案，不论答案出自哪一句——
        # 客户一句答好几项、或在研发回问之前就顺口说过时，槽位的出处是更早的一句。
        # 结案时把客户在会话里已说清、需求单还没有的条件一并补上，研发不必再为它们回问。
        # 重问（单上已有这个条件，或客户先前答过不清楚——试样失败、客户评价不通过后再问）只认回问提出之后的答复。
        answered = set()
        said_at = {t.id: t.ts for t in session.turns}
        for q in asks:
            fill = session.need.slots.get(q.refs["slot"])
            if fill is None:
                continue
            req = self._requirements[q.refs["requirement_id"]]
            if said_at[fill.turn_id] < q.created_at and (fill.slot in req.known_slots or fill.status == "unknown"):
                continue
            for f in session.need.slots.values():
                if f.status == "filled" and (f.slot == fill.slot or f.slot not in req.known_slots):
                    req.known_slots[f.slot] = f.value
            self._answers.setdefault(req.id, {})[fill.slot] = fill.turn_id
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

    def _pending_asks(self, session_id):
        """v8：本会话上未答的回问，只给槽位问法；自助会话里客户直接在自助页回答（V9.3：页面一次显示第一条）。"""
        slots = {s.id: s for s in self.seeds.slots}
        return [PendingAsk(question_id=q.id, slot=q.refs["slot"], label=slots[q.refs["slot"]].label,
                           ask_text=slots[q.refs["slot"]].ask_text)
                for q in self.bus.list(family="ask_back") if q.refs["session_id"] == session_id]

    def view_session(self, session_id, viewer_id):
        viewer, session = self._actor(viewer_id), _find(self._sessions, session_id, "会话")
        level = level_of(viewer)
        # v8 收口：客户的归属业务员可以看自己客户的自助会话（自助单的客户评价由他跟进）
        if level <= 1 and viewer_id not in (session.customer_id, session.sales_id,
                                            self.config["customer_sales"].get(session.customer_id)):
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
            temperature=session.need.temperature,
            card=card, status=session.status, escalation_question_id=rec.escalated_question_id if rec else None,
            requirement=req, reuse=reuse, asks=self._pending_asks(session_id),
            reply_draft=session.reply_draft if viewer_id == session.sales_id else "",
            escalate_note=session.escalate_note if viewer_id == session.sales_id or level > 1 else ""
            ).model_copy(deep=True)

    def agent_need_card(self, session_id, by):
        """业务员助手的会话投影；现象直接取抽取结果，复用view_session的归属与披露。"""
        v = self.view_session(session_id, by)
        return {"status": v.status, "phenomenon": self._sessions[session_id].need.phenomenon,
                "slots": [{"slot": f.slot, "value": f.value, "quote": f.quote} for f in v.slots],
                "temperature": v.temperature.model_dump() if v.temperature is not None else None,
                "turns": [{"turn_id": t.id, "speaker": t.speaker, "text": t.text} for t in v.turns],
                "ask_hints": [h.ask_text for h in v.hints], "escalation_question_id": v.escalation_question_id,
                "reply_draft": v.reply_draft, "escalate_note": v.escalate_note,
                "reuse": v.reuse and v.reuse.model_dump(),
                "card": v.card and {"product_id": v.card.product_id, "version": v.card.version,
                                    "note": v.card.note, "sections": [f"{s.title}：{s.text}" for s in v.card.sections]}}

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
        turns = [t.id for sid in req.session_ids for t in self._sessions[sid].turns if t.speaker == "customer"]
        if bad := [ref for ref in item.quote_refs if ref not in turns]:
            # V9.4：说清哪条引不上、能引哪些（业务员和化言的问话不算客户原话）
            raise ValueError(f"原话引用必须属于本需求单的客户发言：{'、'.join(bad)} 不是；可引用 {'、'.join(turns)}")
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
        """v8 收口：接单是研发的判断，同单的回问、失真提示只作证据，不挡接单；它们由觉再看结案。"""
        req, actor = self._requirement(req_id, by, {"rd"}, {"draft"})
        if not req.product_lang or req.reuse is None or (req.reuse.product_id and not req.reuse.declined_reason):
            raise ValueError("接单需要产品需求草稿，且现成产品检查已结束")
        for item in req.product_lang:
            self._validate_item(req, item, actor)
        units = [self.kb.get(ref, actor) for ref in sorted({ref for item in req.product_lang for ref in item.ku_refs})]
        units = [u for u in units if u.level == 2]
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("accept_requirement", "accept_requirement", state.objects[f"requirement:{req_id}"], by)
        req.status, req.rd_accepted_by = "rd_accepted", by
        if not self._covering_projects(req):      # 接单即立项：没有覆盖本单的研发中项目就立一个（契约 ⑯）
            project = Product(id=f"proj:{req.id}", name=f"{next(p.label for p in self.seeds.phenomena if p.id == req.phenomenon)}在研项目（{req.id}）",
                category=next((p.category for p in self.seeds.products if req.phenomenon in p.solves), "在研"),
                solves=[req.phenomenon], applicable={s: [v] for s, v in req.known_slots.items()},
                sheet="", usage="", mechanism="", formula="", owner=by, status="project")
            self.seeds.products.append(project)
            self.events.append("project_opened", by, {"requirement_id": req.id, "product": project.model_dump()})
        for unit in units:
            if unit.owner != "pm:agent" and not self.ledger.has(unit.owner, unit.id, req.id):
                self.ledger.add(LedgerEntry(ts=get_clock().now(), owner=unit.owner, ku_id=unit.id, ref=req.id,
                    points=self.config["points"]["cited"], reason="cited"))
        self.events.append("requirement_accepted", by, {"requirement_id": req.id,
            "phenomenon": req.phenomenon, "known": req.known_slots, "ku_refs": [u.id for u in units]})
        if question:
            self._settle(question.id, Resolution(action="accept", by=by))
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

    def ask_before_accept(self, req_id, slots, by):
        """v8 研发签接单「先回问客户」：缺的是客户才知道的条件时，不接单、不退回产品经理；单子仍待接单，
        这些条件的回问由觉提出，客户答完后觉再提接单（模板前提 n_missing == 0）。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft"})
        self._check_slots(slots, True)
        if not slots:
            raise ValueError("请勾选要回问的条件")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("accept_requirement", "ask_before_accept", state.objects[f"requirement:{req_id}"], by)
        reason = f"接单前回问：{'、'.join(slots)}"
        req.return_notes.append(reason)
        self.events.append("requirement_returned", by, {"requirement_id": req_id, "reason": reason, "slots": list(slots)})
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
        self._save_requirement(req)
        self._after(req_ids=[req_id])      # 查无产品时复用问题的前提不再成立，由觉结案
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
        unit = KnowledgeUnit(id=self.kb.next_claim_id(), kind="claim", level=3,
            title="研发审定的复用说明", text=proposal.customer_note, product_id=proposal.product_id,
            phenomenon_ids=[req.phenomenon], owner=by, confirmed_by=by, source="contributed", created_at=at)
        self.kb.add(unit)
        said = self.kb.grant(Capability(id=self.kb.next_cap_id(), form="statement", audience=0,   # 写给客户的话，研发审过后回到客户
            payload={"text": proposal.customer_note, "product_id": proposal.product_id},
            based_on=[unit.id], granted_by=by, status="active", at=at))
        self._recommend_product(session, proposal.product_id, at, said.id)
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

    def _recommend_product(self, session, product_id, at, basis):
        """把一个已发布产品按公开版本推荐到会话（研发审定的复用、研发判定已有产品适用、本单发布）。
        V9.6a：basis 是这张推荐所依据的能力，依据失效时推荐随之撤回（_invalidate_capabilities）。"""
        viewer = self.actors[session.sales_id or session.customer_id]
        maximum = "product_usage" if self.kb.is_frozen(viewer.id) else cap(
            viewer, session.customer_id, product_id, self.grants)
        disclosure = self.jev.disclose(session.need, product_id, maximum)
        card = render(product_id, disclosure.choice, viewer, self.kb, session_id=session.id,
                      customer_id=session.customer_id, grants=self.grants)
        session.recommendation = Recommendation(product_id=product_id, match=None,
            candidates=[Candidate(product_id=product_id, unknown_slots=[], capability_id=basis)],
            disclose=disclosure, version=disclosure.choice, at=at)
        session.status = "recommended"
        record_disclosure(card, self)

    def decline_project(self, req_id, reason, by, applicable_product=None, claim_ids=(), limits="", reviewed_evidence=None):
        """v6：研发不立项。给出 applicable_product = 已有产品适用（只是超出标注范围），客户会话收到该产品推荐；
        否则客户收到「暂无方案、已记录」（会话 closed）。V9.5：limits = 槽位表达不了的限制原文，随适用能力保存。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft"})
        if not reason.strip():
            raise ValueError("请填写不立项的原因")
        if leak_hits(reason, [], [], self.kb):
            raise ValueError("不立项原因含研发术语，请改写为产品需求说明")
        limits = limits.strip()
        if limits and leak_hits(limits, [], [], self.kb):
            raise ValueError("限制条件含研发术语，请改写为产品级说法")
        at = get_clock().now()
        state = requirement_state(req, self._sessions[req.session_ids[0]].need, self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, at, self.events)
        question = self._decision("accept_requirement", "decline_project", state.objects[f"requirement:{req_id}"], by)
        if applicable_product:
            self.kb.product(applicable_product)
            if claim_ids:
                self.kb.confirm(claim_ids, by, reviewed_evidence=reviewed_evidence)
            else:
                unit = KnowledgeUnit(id=self.kb.next_claim_id(), kind="claim", level=3,
                    title="研发判定已有产品适用", text=reason, product_id=applicable_product,
                    phenomenon_ids=[req.phenomenon], owner=by, confirmed_by=by, source="contributed", created_at=at)
                self.kb.add(unit)
                claim_ids = [unit.id]
            required = next(p.required_slots for p in self.kb.view(self._actor(by)).phenomena if p.id == req.phenomenon)
            payload = {"product_id": applicable_product, "phenomenon": req.phenomenon,
                       "conditions": {slot: [value] for slot, value in req.known_slots.items() if slot in required}}
            if limits:
                payload["limits"] = limits
            if (temperature := self._sessions[req.session_ids[0]].need.known_temperature()) is not None:
                payload["temperature_c"] = list(temperature)     # 研发按这张单的温度判定适用，范围只到这个温度
            basis = self.kb.grant(Capability(id=self.kb.next_cap_id(), form="applicable", audience=0, payload=payload,
                based_on=list(claim_ids), granted_by=by, status="proposed", at=at))
        req.status = "rejected"
        for sid in req.session_ids:
            if applicable_product:
                self._recommend_product(self._sessions[sid], applicable_product, at, basis.id)
            else:
                self._sessions[sid].status = "closed"
        self.events.append("project_declined", by, {"requirement_id": req_id, "reason": reason,
            "product_id": applicable_product, "limits": limits, "phenomenon": req.phenomenon, "known": req.known_slots,
            "session_ids": req.session_ids})
        if question:
            self._settle(question.id, Resolution(action="dismiss", by=by, note=reason))
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

    def extend_scope(self, question_id, note, by, reviewed_evidence=None):
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
        capability = self.kb.approve(q.refs["capability_id"], by, reviewed_evidence=reviewed_evidence)
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
        if level_of(viewer) <= 1 and viewer_id not in (session.customer_id, session.sales_id,
                                                       self.config["customer_sales"].get(session.customer_id)):
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
        q = _find(self.bus.questions, question_id, "问题")
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
        q = _find(self.bus.questions, question_id, "问题")
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
        session = self._sessions[req.session_ids[0]]
        if by not in {session.sales_id, self.config["customer_sales"].get(session.customer_id)}:   # v8 收口：自助单由客户的归属业务员跟进
            raise PermissionDenied("只能录入自己客户的评价")
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

    def _covering_projects(self, req):
        return sorted((p for p in self.seeds.products if p.status == "project"
            and req.phenomenon in p.solves and consistent(p, req.known_slots)), key=lambda p: p.id)

    def confirm_translation(self, req_id, by):
        req, actor = self._requirement(req_id, by, {"rd"}, {"rd_accepted"})
        if not req.chem_lang:
            raise ValueError("请先起草化学语言条目")
        for item in req.chem_lang:
            self._validate_item(req, item, actor)
        products = self._covering_projects(req) or [p for p in self.seeds.products if p.id == f"proj:{req.id}"]
        if not products:
            raise ValueError("没有覆盖该需求的研发中产品，暂不能确认")
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
        return [self.requirement_view(req.id, viewer_id).requirement for req in self._requirements.values()]

    def matched_limits(self, req_id, by):
        """V9.5 只读：与本单现象和已知条件相符、带研发限制原文的生效适用，给研发和产品经理对照处理。"""
        self._actor(by, {"pm", "rd", "supervisor"})
        req = _find(self._requirements, req_id, "需求单")
        limits = self.kb.limits()
        return [{"product_id": c.payload["product_id"], "capability_id": c.id, "granted_by": c.granted_by,
                 "conditions": c.payload["conditions"], "limits": limits[c.id]}
                for c in self.kb.capabilities() if c.id in limits and c.payload["phenomenon"] == req.phenomenon
                and all(value in c.payload["conditions"][slot] for slot, value in req.known_slots.items()
                        if slot in c.payload["conditions"])]

    def requirement_view(self, req_id, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
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
                title=unit.title if readable else      # 第 0 天迁移的现象结论归属 seed，不是某个人
                    f"{'种子' if unit.owner == 'seed' else self.actors[unit.owner].name}的知识（L{unit.level}，仅显示归属）",
                text=unit.text if readable else None,
                n_cited=sum(e.reason == "cited" and e.ku_id == ref for e in self.ledger.list())))
        quote_refs = {ref for item in req.product_lang + req.chem_lang for ref in item.quote_refs}
        quotes = {t.id: t.text for sid in req.session_ids for t in self._sessions[sid].turns if t.id in quote_refs}
        return RequirementView(viewer=viewer_id, viewer_level=level_of(viewer), requirement=req,
                               quotes=quotes, cited=cited)

    def leak_check(self, req_id, viewer_id):
        viewer = self._actor(viewer_id, {"pm", "rd", "supervisor"})
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

    def return_for_conditions(self, req_id, slots, by):
        """v8 研发签 trial_risk「先回问」：需求单退回到已接单、待重新转译；这些条件的回问由觉提出。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"rd_confirmed"})
        self._check_slots(slots, True)
        if not slots:
            raise ValueError("请勾选要回问的条件")
        state = requirement_state(req, self._sessions[req.session_ids[0]].need,
                                  self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")), self.kb, get_clock().now(), self.events)
        question = self._decision("trial_risk", "return_for_conditions", state.objects[f"requirement:{req_id}"], by)
        reason = f"试样前回问：{'、'.join(slots)}"
        req.status = "rd_accepted"
        req.return_notes.append(reason)
        self.events.append("requirement_returned", by, {"requirement_id": req_id, "reason": reason, "slots": list(slots)})
        if question:
            self._settle(question.id, Resolution(action="sign", by=by, note=reason))
        self._save_requirement(req)
        self._after(req_ids=[req_id])
        return self.requirement_view(req_id, by).requirement

    def record_trial(self, trial: Trial):
        actor = self._actor(trial.rd, {"rd"})
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

    def release_product(self, req_id, by, name=None, category=None):
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
        update = {"sheet": req.sheet.sheet, "usage": req.sheet.usage}
        if seed.id == f"proj:{req.id}":          # 接单时立的项目：机理取转译出来的化学语言条目，第一条适用情境取最后一次通过试样的条件
            passed = [t for t in self._trials.values() if t.requirement_id == req.id and t.result == "pass"][-1]
            mechanism = "\n".join(i.text for i in req.chem_lang if i.ku_refs or i.edited_by)
            update |= {"mechanism": mechanism or "（研发未录入机理）", "formula": "（模拟）配方不录入本系统",
                       "situations": [Situation(phenomenon=req.phenomenon, capability_id=self.kb.next_cap_id(),
                                                conditions={s: [v] for s, v in passed.conditions.items()})]}
        if seed.id == f"proj:{req.id}" and not ((name or "").strip() and (category or "").strip()):
            raise ValueError("新立项目发布时请填写产品名称和类别")
        update |= {k: v.strip() for k, v in (("name", name), ("category", category)) if v and v.strip()}
        product = seed.model_copy(update=update, deep=True)
        at = get_clock().now()
        released = flow.release_product(req, product, self.kb, self.ledger, self.events, by, at)
        for sid in req.session_ids:            # V9.6a：原会话收到新产品，依据是本单发布的适用情境
            session = self._sessions[sid]
            situation = next((x for x in released.situations if x.phenomenon == session.need.phenomenon
                              and consistent(released, session.need.known(),
                                             temperature_c=session.need.known_temperature())), None)
            if session.status != "closed" and situation:
                self._recommend_product(session, released.id, at, situation.capability_id)
                self._save_session(session)
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

    def import_proposals(self, proposals, by):
        """导入本人负责的已准备提议，只产生候选；专业签字仍走独立入口。"""
        self._actor(by, {"rd"})
        if any(p.author != by for p in proposals):
            raise ValueError("只能导入已指定本人负责的提议")
        report = admit(proposals, self.kb.sources, self.kb)
        self.scan()
        return report

    def candidate_claims(self, req_id, viewer_id):
        if req_id is None:
            actor = self._actor(viewer_id, {"rd"})
            req = None
        else:
            req, actor = self._requirement(req_id, viewer_id, {"rd"},
                {"draft", "rd_accepted", "rd_confirmed", "released", "rejected", "reused", "merged"})
        shared = self.kb._shared(actor)
        return [u.model_copy(deep=True) for u in self.kb._units.values()
                if u.kind == "claim" and u.status == "candidate"
                and (u.owner == viewer_id if u.confirmed_by is None else can_read(actor, u, shared))
                and (req.phenomenon in u.phenomenon_ids if req else (u.confirmed_by or u.owner) == viewer_id)]

    def revise_claim(self, ku_id, text, by):
        """保留旧稿，修订为新的本人待审候选；不替代专业确认或用途授予。"""
        unit = next((u for u in self.candidate_claims(None, by) if u.id == ku_id), None)
        if unit is None:
            raise ValueError("只能修订本人负责的待审候选")
        if not text.strip():
            raise ValueError("候选正文不能为空")
        revised = unit.model_copy(update={"id": self.kb.next_claim_id(), "text": text.strip(),
                                          "created_at": get_clock().now()}, deep=True)
        self.withdraw_claim(ku_id, by)
        self.kb.add(revised)
        self.scan()
        return revised.model_copy(deep=True)

    def search_sources(self, query, by, k=5, req_id=None):
        """V11.13 原始资料检索：先按统一读取入口划出委托人能读的整份来源，只在这里面找；命中只是依据，不是结论。
        V12.5 给了需求单时，再用单上的现象与已知条件、客户原话各查一次并融合：说法不同也能落到同一页。"""
        actor = _find(self.actors, by, "主体")
        readable = readable_sources(self.kb, actor, self.source_owners)
        if req_id is None:
            return search_library(self.kb.sources, query, readable, k)
        req, _ = self._requirement(req_id, by, {"pm", "rd"}, {"draft", "reused", "merged", "rd_accepted", "rd_confirmed", "released", "rejected"})
        return search_many(self.kb.sources, [query, *self._need_queries(req)], readable, k)

    def _need_queries(self, req):
        """需求单的两种说法：专业的（现象、已知条件、温度）与客户原话（前两句）。"""
        label = next(p.label for p in self.seeds.phenomena if p.id == req.phenomenon)
        temps = [f"{t.celsius[0]:g}℃" for sid in req.session_ids
                 for t in [self._sessions[sid].need.temperature] if t is not None and t.status == "filled"]
        said = [x.text for sid in req.session_ids for x in self._sessions[sid].turns if x.speaker == "customer"][:2]
        slots = {s.id: s for s in self.kb.view(Actor(id="system:requirement", role="rd", name="研发需求")).slots}
        aliases = [a for k, v in req.known_slots.items() for a in slots[k].customer_phrases.get(v, [])]   # 契里确认过的说法
        return [" ".join([label, *req.known_slots.values(), *temps]), " ".join(said), *([" ".join([label, *aliases])] if aliases else [])]

    def alias_candidates(self, by):
        """V12.9 动态别名：整批编译时模型提议的「已有取值的另一种说法」，研发只看到出自自己按统一读取入口能读的资料的；
        确认过的标出来。只是候选，模型也会对错，研发逐条确认。"""
        actor = self._actor(by, {"rd"})
        if not self.config.get("trial_coverage"):
            raise ValueError("本实例没有配置整批编译的产物目录 trial_coverage")
        readable = readable_sources(self.kb, actor, self.source_owners)
        done = {(c.payload["text"], c.payload["slot"]): c.payload["value"] for c in self.kb.capabilities()
                if c.form == "phrase" and c.status == "active"}
        rows = json.loads((Path(self.config["trial_coverage"]) / "aliases.json").read_text(encoding="utf-8"))
        return [{"text": r["text"], "slot": r["suggest"]["slot"], "value": r["suggest"]["value"], "reason": r["suggest"]["reason"],
                 "docs": docs, "confirmed": done.get((r["text"], r["suggest"]["slot"]))}
                for r in rows if r["suggest"] and (docs := [d for d in r["docs"] if d in readable])]

    def confirm_alias(self, text, slot, value, by):
        """研发确认一条说法（可改成同槽位的另一个已有取值）：一条研发确认的结论，授为研发层的 phrase 能力；
        之后编译读报告、从需求单检索都认得这个说法（知识库视图并进口语说法）。内部资料来的说法由研发签（QI.md 第⑤类）。"""
        row = next((r for r in self.alias_candidates(by) if r["text"] == text and r["slot"] == slot), None)
        if row is None or row["confirmed"]:
            raise ValueError("没有这条待确认的别名候选")
        slot_def = next(s for s in self.seeds.slots if s.id == slot)
        if value not in slot_def.values:
            raise ValueError(f"只能对到{slot_def.label}的已有取值")
        at = get_clock().now()
        unit = KnowledgeUnit(id=self.kb.next_claim_id(), kind="claim", level=3, title=f"说法「{text}」",
            text=f"「{text}」是{slot_def.label}「{value}」的另一种说法（见于 {'、'.join(row['docs'])}）",
            owner=by, confirmed_by=by, source="contributed", created_at=at)
        self.kb.add(unit)
        return self.kb.grant(Capability(id=self.kb.next_cap_id(), form="phrase", audience=3,
            payload={"slot": slot, "value": value, "text": text}, based_on=[unit.id], granted_by=by, status="active", at=at))

    def trial_coverage(self, product, by, phenomenon=None):
        """V12.5 跨报告的试样覆盖（V12.4 整批编译的读取侧产物）：委托人能读的试样里，这个产品试过哪些条件、结果怎样，
        以及同产品可比条件下结果不同的研究假设。只是读稿，不是已确认结论。"""
        actor = _find(self.actors, by, "主体")
        readable = readable_sources(self.kb, actor, self.source_owners)
        if not self.config.get("trial_coverage"):
            raise ValueError("本实例没有配置试样覆盖（V12.4 整批编译的产物目录 trial_coverage）")
        root = Path(self.config["trial_coverage"])
        keep = lambda r: r["product"] == product and r["doc_id"] in readable and phenomenon in (None, r["phenomenon"])
        rows = [r for r in json.loads((root / "coverage.json").read_text(encoding="utf-8")) if keep(r)]
        hypotheses = [h | {"rows": [r for r in h["rows"] if r["doc_id"] in readable]}
                      for h in json.loads((root / "hypotheses.json").read_text(encoding="utf-8"))
                      if h["product"] == product and phenomenon in (None, h["phenomenon"])]
        return {"rows": rows, "hypotheses": [h for h in hypotheses if len(h["rows"]) > 1], "read_by": "整批编译的读稿，未经研发确认"}

    def save_plan_draft(self, req_id, evidence, comparison, transferable, open_items, by):
        """V12.5 方案推演：从历史试样推一个值得验证的方案，存为本单准备材料。方案不是能力，不进客户侧，由接单研发采用或改写。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft", "rd_accepted"})
        if not evidence:
            raise ValueError("方案要带依据指针")
        self._source_fragments(evidence, by)
        record = {"req_id": req.id, "evidence": list(evidence), "comparison": list(comparison), "transferable": list(transferable),
                  "open_items": list(open_items), "by": f"agent:{by}" if self._agent_drafting else by,
                  "at": get_clock().now().isoformat(), "adopted_by": None, "adopted_at": None}
        self._write_plan(req, record)
        return record

    def plan_draft(self, req_id, by):
        actor = self._actor(by, {"rd"})
        req = _find(self._requirements, req_id, "需求单")
        path = self.run_dir / "plan_drafts" / f"{req.id.replace(':', '_')}.json"
        return json.loads(path.read_text(encoding="utf-8")) if actor.id == req.assigned_rd and path.exists() else None

    def adopt_plan(self, req_id, by):
        """接单研发采用 Agent 推出的方案（工作面签字，Agent 没有这个工具）；采用不改适用范围，也不算试样结果。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft", "rd_accepted"})
        record = self.plan_draft(req_id, by)
        if record is None:
            raise ValueError("本单还没有方案草稿")
        record |= {"adopted_by": by, "adopted_at": get_clock().now().isoformat()}
        self._write_plan(req, record)
        return record

    def _write_plan(self, req, record):
        path = self.run_dir / "plan_drafts"
        path.mkdir(exist_ok=True)
        (path / f"{req.id.replace(':', '_')}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    def read_source(self, doc_id, by, span=None):
        """内部查证只返回原文与出处键，不产生结论、能力或专业签字。"""
        actor = _find(self.actors, by, "主体")
        return read_source(self.kb, doc_id, actor, self.source_owners, span)

    def read_trial_record(self, doc_id, by):
        """回取来源关联的读取侧试样记录，不写正式知识状态。"""
        actor = _find(self.actors, by, "主体")
        return read_trial_record(self.kb, doc_id, actor, self.source_owners,
                                 self.config.get("source_trials", {}).get(doc_id))

    def read_source_image(self, doc_id, page, by, span=None):
        """按证据来源键取回页图或已登记区域，不向调用方提供本地路径。"""
        actor = _find(self.actors, by, "主体")
        return read_source_image(self.kb, doc_id, actor, self.source_owners, page, span)

    def ask_source_image(self, doc_id, page, question, by):
        """V12.2 单独问原页图：同一统一入口取图，只把原图和问题交模型，不带转写；回答是模型读稿，不是原文。"""
        actor = _find(self.actors, by, "主体")
        image = read_source_image(self.kb, doc_id, actor, self.source_owners, page)
        answer, model = ask_image(image["image_url"], question, self.gateway)
        return {"doc_id": doc_id, "page": page, "question": question, "answer": answer,
                "read_by": f"模型读图（{model}），不是原文", "image_fingerprint": image["fingerprint"]}

    def save_source_preparation(self, req_id, evidence, claim_ids, pending, by):
        """保存本单资料准备草稿；原文仍在读取侧，不确认或授予。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft", "rd_accepted"})
        if not evidence and not claim_ids:
            raise ValueError("准备材料需要依据或待审候选")
        candidates = {u.id for u in self.candidate_claims(req_id, by)}
        if not set(claim_ids) <= candidates:
            raise ValueError("候选必须属于本单可审阅的待审列表")
        self._source_fragments(evidence, by)
        record = {"req_id": req.id, "evidence": list(evidence), "claim_ids": list(claim_ids),
                  "pending": pending, "known_slots": dict(req.known_slots),
                  "temperatures": {sid: self._sessions[sid].need.temperature.model_dump(mode="json")
                                   if self._sessions[sid].need.temperature is not None else None for sid in req.session_ids},
                  "by": f"agent:{by}" if self._agent_drafting else by, "at": get_clock().now().isoformat()}
        path = self.run_dir / "source_preparations"
        path.mkdir(exist_ok=True)
        (path / f"{req.id.replace(':', '_')}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def _source_fragments(self, evidence, by):
        documents = {}
        fragments = []
        for ref in evidence:
            if "@" not in ref or "#" not in ref.rsplit("@", 1)[0]:
                raise ValueError("evidence须为doc_id#span@fingerprint指针数组；请复制read_trial_record中evidence[].fragment，不能填写原文或摘要")
            location, fingerprint = ref.rsplit("@", 1)
            doc_id, span = location.rsplit("#", 1)
            if doc_id not in documents:
                documents[doc_id] = {f.span: f for f in self.read_source(doc_id, by)}
            fragment = documents[doc_id].get(span)
            if fragment is None or fragment.fingerprint != fingerprint:
                raise ValueError("准备依据已变化或无法取回，请重新读取")
            fragments.append(fragment)
        return fragments

    def compile_source_preparation(self, req_id, doc_id, by):
        """将读取侧已准备的操作或负例观察 IR 导入本单候选；不推断用途范围。"""
        req, _ = self._requirement(req_id, by, {"rd"}, {"draft", "rd_accepted"})
        prepared = self.source_preparation(req_id, by)
        ir_path = self.config.get("source_irs", {}).get(doc_id)
        if prepared is None:
            raise ValueError("请先保存本单依据")
        fragments = self._source_fragments(prepared["evidence"], by)
        if ir_path is None:
            return self._compile_observations(req, prepared, [f for f in fragments if f.doc_id == doc_id], by)
        candidates = {u.id for u in self.candidate_claims(req_id, by)}
        if not set(prepared["claim_ids"]) <= candidates:
            raise ValueError("准备关联的候选状态已变化，请重新准备")
        ir = OperationIR.model_validate_json(Path(ir_path).read_text(encoding="utf-8"))
        source = next(s for s in self.kb.sources if doc_id in s.list_docs())
        if not isinstance(source, EvidenceReportSource) or ir.file_sha256 != source.file_sha256:
            raise ValueError("IR 与试样读取记录的文件指纹不一致")
        if ir.source_id != doc_id or not {c.fragment for c in ir.evidence} <= set(prepared["evidence"]):
            raise ValueError("请先将该 IR 的完整依据保存到本单准备材料")
        if ir.proposal.phenomenon != req.phenomenon or ir.proposal.form is not None:
            raise ValueError("本入口只导入与本单现象一致的观察，不推断适用范围")
        scope = f"{ir.group}组" if ir.group else "报告层"
        conditions = [f"[{c.group + '组' if c.group else '原文范围' if c.stage else '共同'}"
                      f" / {c.stage or '条件'}] {c.text}" for c in ir.conditions]
        text = "\n".join([f"{scope}单次观察：{ir.proposal.text}", "报告完整条件：",
                          *conditions, "限制原文：", ir.proposal.limits,
                          "待核对：", *ir.pending])
        report = self.import_proposals([ir.proposal.model_copy(update={"text": text})], by)
        claim_ids = prepared["claim_ids"] + [row["ku_id"] for row in report["admitted"]]
        pending = "\n".join(dict.fromkeys([prepared["pending"], *ir.pending]))
        record = prepared | {"claim_ids": claim_ids, "pending": pending,
                             "compilation": {"ir_id": ir.id, "at": get_clock().now().isoformat(), "report": report}}
        path = self.run_dir / "source_preparations" / f"{req.id.replace(':', '_')}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def _compile_observations(self, req, prepared, fragments, by):
        """V11.13 没登记 IR 的来源（资料库）：用本单存下的依据页现编观察（V11.10 编译器），只产生候选。"""
        if not fragments:
            raise ValueError("本单准备材料里没有这份来源的依据，请先读原文并保存依据")
        proposals = [p.model_copy(update={"author": by}) for p in propose(fragments, self.gateway, self.seeds)]
        report = self.import_proposals(proposals, by)
        mine = {u.id for u in self.candidate_claims(req.id, by)}
        admitted = [row["ku_id"] for row in report["admitted"]]
        record = prepared | {"claim_ids": list(dict.fromkeys(prepared["claim_ids"] + [k for k in admitted if k in mine])),
                             "compilation": {"method": "observation", "doc_id": fragments[0].doc_id,
                                             "other_phenomenon": [k for k in admitted if k not in mine],
                                             "at": get_clock().now().isoformat(), "report": report}}
        path = self.run_dir / "source_preparations" / f"{req.id.replace(':', '_')}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def source_preparation(self, req_id, by):
        """准备草稿仅供接单研发查看；其他工作面沿原边界不返回 L3 材料。"""
        actor = self._actor(by, {"pm", "rd", "supervisor"})
        req = _find(self._requirements, req_id, "需求单")
        if actor.id != req.assigned_rd:
            return None
        if self.kb.is_frozen(by):
            raise PermissionDenied("上层知识读取已冻结")
        path = self.run_dir / "source_preparations" / f"{req.id.replace(':', '_')}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def authorized_source_replies(self, session_id, by):
        """把原需求关联结论的已授权说明回到本会话，不返回内部准备材料。"""
        actor = self._actor(by, {"customer", "sales"})
        self.view_session(session_id, by)
        if self.kb.is_frozen(by):
            return []
        claim_ids = set()
        for req in self._requirements.values():
            if session_id not in req.session_ids:
                continue
            path = self.run_dir / "source_preparations" / f"{req.id.replace(':', '_')}.json"
            if path.exists():
                claim_ids.update(json.loads(path.read_text(encoding="utf-8"))["claim_ids"])
        return [{"ref": c.id, "text": render_refs(f"[[{c.id}]]", level_of(actor), self.kb), "audience": c.audience}
                for c in self.kb._visible_caps(actor)
                if c.form == "statement" and claim_ids.intersection(c.based_on)]

    def source_preparation_status(self, req_id, by):
        """由当前结论和能力投影本单处理结果，不回写准备材料。"""
        prepared = self.source_preparation(req_id, by)
        if prepared is None:
            return None
        actor, shared = self.actors[by], self.kb._shared(self.actors[by])
        units = [self.kb._units[uid] for uid in prepared["claim_ids"]]
        units = [u for u in units if (u.owner == by if u.confirmed_by is None else can_read(actor, u, shared))]
        ids = {u.id for u in units}
        return {"claims": [{"id": u.id, "status": u.status,
                            "confirmed_by": u.confirmed_by if u.status == "active" else None} for u in units],
                "capabilities": [{"id": c.id, "form": c.form, "audience": c.audience, "status": c.status,
                                  "granted_by": c.granted_by, "approved_by": c.approved_by}
                                 for c in self.capabilities(by) if ids.intersection(c.based_on)]}

    def review_claims(self, ku_ids, by):
        """读取本次审阅原文与固定指纹；返回值由人审阅后随确认提交，不写正式状态。"""
        actor = self._actor(by, {"rd", "pm"})
        if by == "pm:agent":
            raise PermissionDenied("审阅确认须由真人负责")
        units = [self.kb._units[ku_id] for ku_id in ku_ids]
        if any(unit.owner != by if unit.confirmed_by is None else
               not can_read(actor, unit, self.kb._shared(actor)) for unit in units):
            raise PermissionDenied("无权审阅所选结论")
        if self.kb.is_frozen(by) and any(unit.level > 1 for unit in units):
            raise PermissionDenied("上层知识读取已冻结")
        fragments = {u.id: self.kb._fragments(u) for u in units}
        return {"claims": [u.model_copy(deep=True) for u in units],
            "fragments": fragments,
            "reviewed_evidence": {ku_id: [f"{f.doc_id}#{f.span}@{f.fingerprint}" for f in items]
                                  for ku_id, items in fragments.items()},
            "pending_evidence": {u.id: dict(self.kb._pending_evidence[u.id]) for u in units
                                 if u.id in self.kb._pending_evidence}}

    def confirm_claims(self, req_id, ku_ids, by, reviewed_evidence=None):
        candidates = {u.id for u in self.candidate_claims(req_id, by)}
        if not set(ku_ids) <= candidates:
            raise ValueError("只能确认当前待审列表中的候选结论")
        self.kb.confirm(ku_ids, by, reviewed_evidence=reviewed_evidence)
        if req_id is not None:
            self._after(req_ids=[req_id])
        self.scan()
        return self.requirement_view(req_id, by).requirement if req_id is not None else None

    def sign_qi_grant(self, question_id, by, claim_ids=(), note="", reviewed_evidence=None, scope=None):
        """scope：研发授予适用能力时放宽试过的范围（V11.10），{conditions, temperature_c, limits} 由他改定；不给就照原范围。"""
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
            self.kb.confirm(claim_ids, by, reviewed_evidence=reviewed_evidence)
        audience, payload = int(q.refs["audience"]), source.payload
        if scope is not None:
            values, t = {s.id: s.values for s in self.seeds.slots}, scope.get("temperature_c")
            if source.form != "applicable" or (t is not None and t[0] > t[1]) or any(
                    slot not in values or not v or not set(v) <= set(values[slot]) for slot, v in scope["conditions"].items()):
                raise ValueError("只能改适用能力的范围：条件须是已知槽位的取值，温度下限不高于上限")
            payload = {k: v for k, v in {**source.payload, "conditions": scope["conditions"], "temperature_c": t,
                                         "limits": scope.get("limits", "").strip()}.items() if v is not None and v != ""}
        cap = next((c for c in self.kb.capabilities() if c.form == source.form and c.payload == payload
                    and c.based_on == source.based_on and c.granted_by == by and c.audience == audience
                    and c.status in {"active", "proposed"}), None)
        if cap is None:
            cap = self.kb.grant(source.model_copy(update={"id": self.kb.next_cap_id(), "payload": payload,
                "audience": audience, "granted_by": by, "approved_by": None,
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
        for q in self.bus.list(family="scope_update"):
            if q.refs["capability_id"] == cap_id:
                self._settle(q.id, Resolution(action="answered", by=by, note="能力已撤销，无需批准"))
        self._settle_stale(cap_id, by, "撤销")
        self._invalidate_capabilities(by)
        self.scan()

    def narrow_capability(self, cap_id, conditions, by):
        """v8 研发签 stale_capability「收窄」：撤销原适用能力，按更窄的条件授予一条新能力，依据与批准人不变。"""
        self._actor(by, {"rd"})
        cap = _find(self.kb._caps, cap_id, "能力")
        if cap.form != "applicable" or cap.status != "active":
            raise ValueError("只能收窄生效中的适用能力")
        self._check_slots(conditions, True)
        values = {s.id: s.values for s in self.seeds.slots}
        old = {slot: cap.payload["conditions"].get(slot, values[slot]) for slot in conditions}
        if not conditions or any(not v or not set(v) <= set(old[s]) for s, v in conditions.items()) \
                or all(set(v) == set(old[s]) for s, v in conditions.items()):
            raise ValueError("新条件必须比原条件窄，且每个条件至少留一个取值")
        self.kb.revoke(cap_id, by)
        payload = {**cap.payload, "conditions": {**cap.payload["conditions"], **conditions}}
        new = self.kb.grant(cap.model_copy(update={"id": self.kb.next_cap_id(), "payload": payload, "status": "active",
                                                   "granted_by": by, "at": get_clock().now()}))
        self._settle_stale(cap_id, by, f"收窄为 {new.id}")
        self._invalidate_capabilities(by)
        self.scan()
        return new

    def _settle_stale(self, cap_id, by, note):
        question = next((q for q in self.bus.list(family="stale_capability")
                         if q.object_id == f"knowledge:stale:{cap_id}"), None)
        if question:      # 能力已撤销，问题随之结束（产品归属研发代为撤销时也一样）
            self._settle(question.id, Resolution(action="sign", by=by, note=note))

    def withdraw_claim(self, ku_id, by):
        self._actor(by, {"rd"})
        self.kb.withdraw(ku_id, by)
        for q in self.bus.list(family="qi_review"):
            if q.refs["ku_id"] == ku_id:
                self._settle(q.id, Resolution(action="answered", by=by, note="撤回结论"))
        self._invalidate_capabilities(by)
        self.scan()

    def _invalidate_capabilities(self, by):
        """V9.6a：每张推荐都要有一条仍有效的依据。依据撤销或挂起时，换成同一产品仍有效、不带研发限制的情境
        （收窄后仍覆盖已知条件的推荐因此保留）；没有可替代的就撤回，重新匹配并留下 match 事件，
        仍无合适产品时觉照常提出升级，客户不会停在没有下文的会话里。研发直接给的依据在产品经理批准前是 proposed，照样有效。"""
        caps, limited, withdrawn = {c.id: c for c in self.kb.capabilities()}, self.kb.limits(), []
        for session in self._sessions.values():
            rec = session.recommendation
            selected = next((c for c in rec.candidates if c.product_id == rec.product_id), None) if rec else None
            basis = caps.get(selected.capability_id) if selected and selected.capability_id else None
            if session.status not in {"escalated", "closed"} and basis and basis.status not in {"active", "proposed"}:
                products = self.kb.view(self._actor(session.sales_id or session.customer_id)).products
                other = next((c for c in match_candidates(session.need.phenomenon, session.need.known(), products, limited,
                                                        temperature_c=session.need.known_temperature())
                              if c.product_id == rec.product_id and c.capability_id not in limited), None)
                if other:
                    selected.capability_id = other.capability_id
                    selected.status, selected.unknown_slots = other.status, other.unknown_slots
                else:
                    self.events.append("recommendation_withdrawn", by, {"product_id": rec.product_id,
                                       "capability_id": basis.id}, session_id=session.id)
                    recommend(session, self)
                    withdrawn.append(session.id)
            session.hints = self.ask_hints(session.need)
            self._save_session(session)
        self._after(withdrawn)

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
        """业务员替客户申请，或客户在 Client-View 上自己申请（V12.6）；都交产品归属研发审批。"""
        actor = self._actor(by, {"sales", "customer"})
        session = _find(self._sessions, session_id, "会话")
        if by not in (session.sales_id, session.customer_id) or self.kb.is_frozen(by):
            raise PermissionDenied("只能为自己的有效会话申请解密")
        rec, profile = session.recommendation, session.need.profile
        if not rec or not rec.product_id:
            raise ValueError("解密需要已有推荐")
        product = self.kb.product(rec.product_id)
        at = get_clock().now()
        granted = [c.payload["product_id"] for c in self.kb.capabilities()
                   if c.form == "decrypt" and c.status == "active" and c.audience == session.customer_id]
        mine = [e.payload for e in self.events.query(["decrypt_request"], since=at - timedelta(days=30)) if e.actor == by]
        evidence = [Evidence(summary=f"客户画像：{'懂化学' if profile.chem_savvy else '未表现出化学背景'}"
                             f"{'，问过机理' if profile.asked_mechanism else ''}", quote=profile.evidence_quote),
                    Evidence(summary=f"该客户已获批的解密：{'、'.join(granted) or '无'}"),
                    Evidence(summary=f"申请人近 30 天的解密申请 {len(mine)} 次，涉及客户 {len({m['customer_id'] for m in mine})} 位、"
                                     f"产品 {len({m['product_id'] for m in mine})} 个")]
        q = self.bus.publish(Question(id="", family="decrypt_request", title="客户申请了解产品机理",
            object_id=f"{session_id}/{product.id}", owner_role="rd", owner_id=product.owner,
            signer_role="rd", signer_id=product.owner,
            scored_by="human", discoverer="human", created_at=get_clock().now(),
            dedup_key=f"decrypt_request:{session_id}/{product.id}",
            evidence=evidence,
            refs={"session_id": session_id, "customer_id": session.customer_id, "product_id": product.id}))
        self.audit.append(AuditRecord(ts=get_clock().now(), actor=actor.id, action="decrypt_request",
            object_ids=[q.id, product.id], session_id=session_id))
        self.events.append("decrypt_request", by, {"question_id": q.id, "customer_id": session.customer_id,
            "product_id": product.id}, session_id=session_id)
        return q.model_copy(deep=True)

    def client_messages(self, by):
        """V12.6 Client-View 的主动消息：研发批准给这位客户的机理说明（`decrypt` 能力，受众就是这位客户）；
        V12.7 业务员按研发新判断回访（`capability_recall` 签字）、这位客户提过的需求做成了新品发布。"""
        self._actor(by, {"customer"})
        names = {p.id: p.name for p in self.kb.products()}
        mine = {s.id for s in self._sessions.values() if s.customer_id == by}
        out = [{"kind": "decrypt", "session_id": c.payload["session_id"], "product": names[c.payload["product_id"]],
                "text": c.payload["text"], "by": c.granted_by, "at": c.at.isoformat()}
               for c in self.kb.capabilities() if c.form == "decrypt" and c.status == "active" and c.audience == by]
        out += [{"kind": "callback", "session_id": q.refs["session_id"], "product": names[q.refs["product_id"]],
                 "text": q.resolution.note, "by": q.resolution.by, "at": q.resolved_at.isoformat()}
                for q in self.bus.list(family="capability_recall", status="resolved") if q.refs["session_id"] in mine]
        out += [{"kind": "release", "session_id": sid, "product": names[e.payload["product_id"]], "text": "", "by": e.actor,
                 "at": e.ts.isoformat()} for e in self.events.query(["product_released"])
                for sid in self._requirements[e.payload["requirement_id"]].session_ids if sid in mine]
        return sorted(out, key=lambda m: m["at"], reverse=True)

    def decide_decrypt(self, question_id, by, approve, text=""):
        self._actor(by, {"rd"})
        question = _find(self.bus.questions, question_id, "问题")
        if question.family != "decrypt_request" or question.status != "open":
            raise ValueError("只能审批待处理的解密申请")
        if question.owner_id != by:
            raise PermissionDenied("只有产品归属研发本人可审批")
        at, refs = get_clock().now(), question.refs
        if approve:
            cap_id = self.kb.next_cap_id()
            self.kb.grant(Capability(id=cap_id, form="decrypt", audience=refs["customer_id"],
                payload={"product_id": refs["product_id"], "session_id": refs["session_id"], "text": text},
                based_on=[f"ku:mechanism:{refs['product_id']}"], granted_by=by, status="active", at=at))
            self.events.append("decrypt_approve", by, {"question_id": question.id, "capability_id": cap_id,
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
        for oid, obj in state.objects.items():      # v8：机会汇聚、适用范围扩展派给分管该现象的产品经理
            a = obj.attrs
            refs[oid]["pm"] = self._line_pm(a.get("phenomenon") or (a["value"] if a.get("slot") == "phenomenon" else None))
            if oid.startswith("knowledge:recall:"):     # V12.7 回访交这段会话的业务员；自助会话交客户的归属业务员
                session = self._sessions[refs[oid]["session_id"]]
                refs[oid]["sales_id"] = session.sales_id or self.config["customer_sales"].get(session.customer_id)
        out = self._propose(self.jue_scheduled, state)
        self._close_stale(out, set(state.objects))
        self._last_scan = at
        return publish(out, state, self.templates, self.bus, self.config["thresholds"]["publish"],
                       seeds=self.seeds, refs=refs)

    def resolve(self, question_id, action, by, note="", reviewed_evidence=None):
        actor = self._actor(by)
        q = _find(self.bus.questions, question_id, "问题")
        if q.status != "open":
            raise ValueError("问题已处理")
        if by == "pm:agent" or q.signer_id != actor.id:
            raise PermissionDenied("只有问题的签字人可以处置")
        allowed = {"knowledge_conflict": "update_sheet", "leak_risk": "freeze_access", "qi_review": "sign",
                   "mechanism_followup": "take_over", "capability_recall": "sign", "sheet_mismatch": "update_sheet"}
        if action != "dismiss" and allowed.get(q.family) != action:
            raise ValueError(f"{q.family} 问题不能执行 {action}")
        if q.family == "sheet_mismatch" and action == "update_sheet":
            self._revise_sheet(q, note, by)
        elif q.family == "capability_recall" and action == "sign":
            session = self._sessions[q.refs["session_id"]]
            session.status = "open"          # 不立项关掉的会话按新判断重新匹配；当时没问到的条件照常由觉追问
            recommend(session, self)
            session.hints = self.ask_hints(session.need)
            self._save_session(session)
            self._after([session.id])
        elif action == "update_sheet":
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
            self.kb.confirm([q.refs["ku_id"]], by, reviewed_evidence=reviewed_evidence)
        elif action == "freeze_access":
            self.kb.freeze(q.refs["actor_id"], by, get_clock().now())
        result = self._settle(question_id, Resolution(action=action, by=by, note=note))
        session = self._sessions[q.refs["session_id"]] if action == "take_over" else None
        if session and session.sales_id is None:      # v8 Q9.8：自助会话由客户归属业务员接手
            self._assign_sales(session, by)
        return result.model_copy(deep=True)

    def _revise_sheet(self, q, text, by):
        """V12.7 说明书跟上研发判断：产品经理签字，把补充句（默认用产品经理 Agent 的草稿）接到说明书后面，回到公开层。"""
        text = (text or self.sheet_revision(q.id, by)["text"]).strip()
        if not text:
            raise ValueError("请写明说明书补充的句子")
        # 补充句写的是已授予客户层的适用条件（推荐卡上本来就显示），只查 L3 术语，不按与研发结论原文重合拦
        if leak_hits(text, [], [], self.kb):
            raise ValueError("补充句含 L3 术语，请改写")
        unit = self.kb._units[f"ku:sheet:{q.refs['product_id']}"]
        self.kb.add(unit.model_copy(update={"text": f"{unit.text}\n{text}"}))
        self.events.append("sheet_updated", by, {"product_id": q.refs["product_id"], "capability_id": q.refs["capability_id"],
                                                 "added": text})

    def _sheet_path(self, question_id):
        return self.run_dir / "sheet_revisions" / f"{question_id.replace(':', '_')}.json"

    def draft_sheet_revision(self, question_id, text, by):
        """V12.7 产品经理 Agent 起草说明书补充句（对外可说的话）；签字仍由真人产品经理。"""
        q = _find(self.bus.questions, question_id, "问题")
        if q.family != "sheet_mismatch" or q.status != "open" or by != q.owner_id:
            raise PermissionDenied("只能为交给自己准备的说明书更新起草")
        if leak_hits(text, [], [], self.kb):
            raise ValueError("补充句含 L3 术语，请改写")
        path = self._sheet_path(question_id)
        path.parent.mkdir(exist_ok=True)
        record = {"question_id": question_id, "text": text.strip(), "by": by, "at": get_clock().now().isoformat()}
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return record

    def sheet_revision(self, question_id, by):
        q = _find(self.bus.questions, question_id, "问题")
        if by not in (q.owner_id, q.signer_id):
            raise PermissionDenied("只有准备人和签字人能看说明书补充稿")
        path = self._sheet_path(question_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"text": ""}

    def unfreeze_access(self, actor_id, by):
        """v8 Q9.8：主管解冻；之后的泄露风险证据从解冻起重新累计。"""
        self._actor(by, {"supervisor"})
        if not self.kb.is_frozen(actor_id):
            raise ValueError("该身份未被冻结")
        self.kb.unfreeze(actor_id, by, get_clock().now())

    def frozen_actors(self, viewer_id):
        """v8 Q9.8：主管看被冻结的人、冻结依据、之后被挡下的检索次数与涉及客户。"""
        self._actor(viewer_id, {"supervisor"})
        rows = []
        for actor_id in sorted(self.kb._frozen):
            freeze = next(e for e in reversed(self.events.query(["access_frozen"])) if e.payload["actor_id"] == actor_id)
            q = next((q for q in reversed(self.bus.list()) if q.family == "leak_risk" and q.object_id == f"actor:{actor_id}"
                      and q.resolution and q.resolution.action == "freeze_access"), None)
            denied = [e for e in self.events.query(["retrieve"], since=freeze.ts)
                      if e.actor.removeprefix("agent:") == actor_id and e.payload.get("denied")]
            customers = {self._sessions[e.session_id].customer_id for e in denied if e.session_id in self._sessions}
            rows.append({"actor_id": actor_id, "name": self.actors[actor_id].name, "frozen_at": freeze.ts.isoformat(),
                         "frozen_by": freeze.actor, "evidence": [ev.summary for ev in q.evidence] if q else [],
                         "n_denied": len(denied), "customers": sorted(customers)})
        return rows

    def questions(self, viewer_id):
        viewer = self._actor(viewer_id, {"sales", "pm", "rd", "supervisor"})
        labels = {s.id: s.label for s in self.seeds.slots}
        questions = [q.model_copy(deep=True) for q in self.bus.list()
                     if viewer_id in (q.owner_id, q.signer_id) or (q.family == "decrypt_request"
                         and self._sessions[q.refs["session_id"]].sales_id == viewer_id)]
        unfinished = {r["question_id"] for r in self.agents.errors() if r["kind"] == "unfinished"}
        for q in questions:
            if q.prepared_at and q.id in unfinished:
                q.evidence.append(Evidence(summary="助手步数用完，没有做完；已完成的部分见对话。签字前要有的材料已齐，可以直接判断"))
            if q.family == "qi_grant" and "requester" in q.refs:
                unit = self.kb._units[q.refs["ku_id"]]
                q.evidence.append(Evidence(summary=f"{self.actors[q.refs['requester']].name}申请查看：{unit.title}"))
                others = [e for e in self.events.query(["share_requested"], since=q.created_at - timedelta(days=30))
                          if e.actor == q.refs["requester"] and e.payload.get("ku_id") != q.refs["ku_id"]]
                q.evidence.append(Evidence(summary=f"申请人近 30 天的其他查看申请 {len(others)} 次"))
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
                if cap.form == "applicable":
                    conditions = "；".join(f"{labels[s]}：{'、'.join(v)}" for s, v in cap.payload["conditions"].items())
                    q.evidence.append(Evidence(summary=f"枚举条件：{conditions or '未限定枚举条件'}"))
                    if cap.payload.get("temperature_c") is not None:
                        lower, upper = cap.payload["temperature_c"]
                        q.evidence.append(Evidence(summary=f"适用温度：{lower:g}—{upper:g}℃"))
                    if cap.payload.get("limits"):
                        q.evidence.append(Evidence(summary=f"限制原文：{cap.payload['limits']}"))
                    q.refs["scope"] = json.dumps({"conditions": cap.payload["conditions"], "limits": cap.payload.get("limits", ""),
                        "temperature_c": cap.payload.get("temperature_c")}, ensure_ascii=False)   # 授予时可放宽（V11.10）
                for uid in cap.based_on:
                    unit = self.kb._units[uid]
                    q.evidence.append(Evidence(summary=f"{unit.title}；依据位置：{'；'.join(unit.evidence) or '研发直接判断'}",
                                               quote=unit.text))
            elif q.family == "scope_update":
                q.refs["temperature_c"] = json.dumps(self.kb._caps[q.refs["capability_id"]].payload.get("temperature_c"))
        return questions

    def _threshold(self, family, mode, model):
        """与 ask_hints、实时评估、定时扫描用的门槛一致。"""
        th = self.config["thresholds"]
        if family == "ask_slot":
            return th["ask_jue_k"] if model == "jue_k" else th["ask"]
        return th["ask_jue_k"] if family == "ask_back" and mode == "realtime" and model == "jue_k" else th["publish"]

    def _jue_k_view(self, mode, objects, at):
        """有 Jue-K 模型的格并排一根 Jue-K 分。这一局本来用规则打分时另载一份 Jue-K 只作对照，不参与决策、不记样本；
        已停用的 leak_risk|L2 不恢复。"""
        engine = self.jue_scheduled if mode == "scheduled" else self.jue_realtime
        if engine.name != "jue_k" and mode not in self._shadow:
            shadow = JueK(self.config["jue_k_dir"], self.config["templates_dir"], mode)
            shadow.templates = engine.templates
            shadow.models.pop("leak_risk|L2", None)
            self._shadow[mode] = shadow
        model = engine if engine.name == "jue_k" else self._shadow[mode]
        out = model.propose(JueState(at=at, mode=mode, objects=objects)) if objects else None
        return model, {(d.template_id, d.object_id): d.p_need for d in out.decisions if d.scored_by == "jue_k"} if out else {}

    def jue_radar(self, by):
        """V12.8 觉雷达（主管只读）：觉正在看的每个对象上前提成立的决策，这一局实际用的分数、门槛、报没报出；
        有 Jue-K 模型的格另给规则分与 Jue-K 分对照。另附「觉在学习」：这一局人处置觉提出的事项的次数（每次是一条学习样本）。"""
        self._actor(by, {"supervisor"})
        questions = {q.dedup_key: q for q in self.bus.list(status=None)}
        names = {s.id: self.actors[s.customer_id].name.replace("（模拟）", "") if s.customer_id in self.actors else "样例客户"
                 for s in self._sessions.values()}
        rows, cells = [], {}
        for mode in ("scheduled", "realtime"):
            watched = {oid: v for oid, v in self._watch.items() if v[0] == mode}
            at = max((v[4] for v in watched.values()), default=get_clock().now())
            shadow, k = self._jue_k_view(mode, {oid: v[2] for oid, v in watched.items()}, at)
            cells[mode] = sorted(shadow.models)
            for oid, (_, model, obj, decisions, seen) in watched.items():
                sid = oid.removeprefix("slot:").split("/")[0] if oid.startswith("slot:") else oid.removeprefix("session:")
                req = self._requirements.get(oid.removeprefix("requirement:"))
                for d in decisions:
                    t = self.templates[d.template_id]
                    title, why = describe(t, obj, self.seeds)
                    q = questions.get(f"{d.family}:{oid}")
                    rows.append({"mode": mode, "object_id": oid, "family": d.family, "decision": t.decision_label,
                                 "title": title, "why": why, "who": names.get(req.session_ids[0] if req else sid),
                                 "p": d.p_need, "scored_by": d.scored_by, "rule": rule_score(t, obj),
                                 "jue_k": k.get((d.template_id, oid)), "cell": f"{d.family}|L{judge_level(t, obj)}",
                                 "threshold": self._threshold(d.family, mode, model), "at": seen.isoformat(),
                                 "question": q and {"id": q.id, "status": q.status}})
        resolved = [e for e in self.events.query(["question_resolved"]) if _human_level(e.actor) is not None]
        last = resolved[-1] if resolved else None
        metrics = Path(self.config["jue_k_dir"]) / "metrics.json"
        return {"rows": rows, "jue_k_cells": cells,
                "engine": {"scheduled": self.jue_scheduled.name, "realtime": self.jue_realtime.name},
                "learning": {"samples": len(resolved),
                             "trained": json.loads(metrics.read_text(encoding="utf-8"))["rows"] if metrics.exists() else None,
                             "last": last and {"family": last.payload["family"], "action": last.payload["action"],
                                               "by": last.actor, "at": last.ts.isoformat()}}}

    def decision_catalog(self, by):
        """V12.8 决策目录墙（主管只读）：每类决策这一局触发了几次（追问按提示次数，其余按发布的问题），最近一次在什么时候；
        另按调用方统计这一局的大模型调用，觉的发现环节不经网关，恒为 0。"""
        self._actor(by, {"supervisor"})
        fired = defaultdict(list)
        for q in self.bus.list(status=None):
            fired[q.family].append(q.created_at)
        fired["ask_slot"] = [e.ts for e in self.events.query(["ask_hint"]) if e.payload["slots"]]
        cells = {*getattr(self.jue_realtime, "models", {}), *getattr(self.jue_scheduled, "models", {})}
        meter = self.run_dir / "metering.jsonl"
        calls = defaultdict(int)
        for line in meter.read_text(encoding="utf-8").splitlines() if meter.exists() else []:
            r = json.loads(line)
            if r["kind"] == "llm":
                calls[r["caller"].split(":")[0]] += 1
        off = set(self.config.get("jue_off", ()))
        return {"templates": [{"family": t.family, "decision": t.decision_label, "kind": t.kind, "owner_role": t.owner_role,
                               "signer_role": t.signer_role, "off": t.family in off, "n": len(fired[t.family]),
                               "last": max(fired[t.family]).isoformat() if fired[t.family] else None,
                               "jue_k": sorted(c for c in cells if c.startswith(f"{t.family}|"))}
                              for t in self.templates.values()],
                "llm_calls": {"jue": 0, **calls}}

    def question_board(self, by):
        """V12.8 问题总线（主管只读）：觉提出的全部问题，新的在前。"""
        self._actor(by, {"supervisor"})
        return [{"id": q.id, "family": q.family, "title": q.title, "status": q.status, "owner_id": q.owner_id,
                 "signer_id": q.signer_id, "created_at": q.created_at.isoformat(), "prepared": q.prepared_at is not None,
                 "by": q.resolution and q.resolution.by}
                for q in sorted(self.bus.list(status=None), key=lambda q: q.created_at, reverse=True)]

    def question_life(self, question_id, by):
        """V12.8 一件事在问题总线上的一生：觉提出（分数与依据）→ 派给谁 → Agent 用了哪些工具、哪次被门面拒绝、
        对象上还缺什么（preparation_gap）→ 谁签了什么。主管是 L2：只给工具名与拒绝原因，不给工具参数与结果（里面有委托人那一层的原文）。"""
        self._actor(by, {"supervisor"})
        q = _find(self.bus.questions, question_id, "问题")
        end = q.resolved_at or get_clock().now()
        rejected = '{"ok":false,"error":"'      # 轨迹里的结果只存前 200 字，按前缀取拒绝原因
        steps = [{"at": s.at.isoformat(), "tool": s.tool, "blocked": bool(s.blocked),
                  "error": s.result_summary.removeprefix(rejected).split('"')[0] if s.result_summary.startswith(rejected) else None}
                 for s in self.agents.trace(self.agents.conversation_of(q)) if q.created_at <= s.at <= end and s.tool]
        errors = [{"at": r["at"], "kind": r["kind"], "detail": r.get("detail")}
                  for r in self.agents.errors(q.owner_id) if r.get("question_id") == q.id]
        return {"question": q.model_dump(mode="json"), "decision": self.templates[q.template_id].decision_label if q.template_id else None,
                "gap": self.preparation_gap(q.id) if q.status == "open" and q.signer_role else None,
                "steps": steps, "errors": errors}

    def _doc_title(self, doc_id):
        source = next(s for s in self.kb.sources if doc_id in s.list_docs())
        return source.docs[doc_id]["title"] if isinstance(source, LibrarySource) else doc_id

    def report_list(self, by):
        """V12.9 契画布可选的报告：研发按统一读取入口能读、且编译出过结论的来源，授出能力多的在前。"""
        actor = self._actor(by, {"rd"})
        readable = readable_sources(self.kb, actor, self.source_owners)
        docs = defaultdict(set)
        for u in self.kb._units.values():
            for d in {e.split("#")[0] for e in u.evidence}:
                docs[d].add(u.id)
        caps = lambda ids: sum(bool(set(c.based_on) & ids) for c in self.kb.capabilities())
        rows = [{"doc_id": d, "title": self._doc_title(d), "n_units": len(ids), "n_caps": caps(ids)} for d, ids in docs.items() if d in readable]
        return sorted(rows, key=lambda r: (-r["n_caps"], -r["n_units"]))

    def report_life(self, doc_id, by):
        """V12.9 契画布：一份报告的一生，每一站都是真对象。资料库 → 读取（这份的页与指纹）→ 编译（录制的提议各自的核对结果）
        → 契纳入（候选结论、能力提议、限制原文）→ 专业生效（确认绑定的指纹、授予、批准）→ 使用与记分 → 变化（改版、挂起、撤下、复核）。
        只给研发，先过统一读取入口；同层别人的结论只给标题与归属。"""
        actor = self._actor(by, {"rd"})
        fragments = read_source(self.kb, doc_id, actor, self.source_owners)
        source = next(s for s in self.kb.sources if doc_id in s.list_docs())
        library = [s for s in self.kb.sources if isinstance(s, LibrarySource)]
        units = [u for u in self.kb._units.values() if any(e.startswith(f"{doc_id}#") for e in u.evidence)]
        ids = {u.id for u in units}
        caps = [c for c in self.kb.capabilities() if set(c.based_on) & ids]
        cap_ids = {c.id for c in caps}
        compiled = []
        if self.config.get("compile_report"):            # 这一局开局时导入的录制提议，逐条的核对结果（导演 prepare_round 写）
            rows = json.loads(Path(self.config["compile_report"]).read_text(encoding="utf-8"))
            compiled = [r for r in rows if doc_id in r["docs"]]
        concerned = lambda e: (e.payload.get("ku_id") in ids or e.payload.get("capability_id") in cap_ids
                               or e.kind == "capability_granted" and e.payload["id"] in cap_ids)
        events = [{"ts": e.ts.isoformat(), "kind": e.kind, "actor": e.actor, "session_id": e.session_id,
                   "ku_id": e.payload.get("ku_id"), "capability_id": e.payload.get("capability_id", e.payload.get("id")),
                   "note": e.payload.get("note") or e.payload.get("reason")}
                  for e in self.events.query() if e.kind in _QI_KINDS | {"recommendation_withdrawn"} and concerned(e)]
        used = [e for e in events if e["kind"] == "capability_used"]
        escalated = {}                   # 会话第一次进研发的时刻；用这份能力时还没进过研发的，算替研发答了
        for e in self.events.query(["requirement_created"]):
            for sid in e.payload["session_ids"]:
                escalated.setdefault(sid, e.ts.isoformat())
        points = defaultdict(int)
        for entry in self.ledger.list():
            if entry.ku_id in ids:
                points[entry.reason] += entry.points
        visible = lambda u: u.owner == by or self.kb._readable(actor, u)
        return {
            "doc": {"doc_id": doc_id, "title": self._doc_title(doc_id), "source": source.name, "kind": source.kind,
                    "owner": self.source_owners.get(doc_id), "level": max([3 if source.kind == "internal" else 0, *(f.level for f in fragments)])},
            "library": {"docs": sum(len(s.list_docs()) for s in self.kb.sources),
                        "library_docs": sum(len(s.docs) for s in library), "pages": sum(x["pages"] for s in library for x in s.docs.values()),
                        "pending": sum(x["pending_pages"] for s in library for x in s.docs.values()),
                        "internal": sum(len(s.list_docs()) for s in self.kb.sources if s.kind == "internal")},
            "pages": [{"span": f.span, "fingerprint": f.fingerprint, "excerpt": f.text[:160]} for f in fragments],
            "compiled": compiled,
            "units": [{"id": u.id, "kind": u.kind, "level": u.level, "status": u.status, "owner": u.owner, "confirmed_by": u.confirmed_by,
                       "title": u.title if visible(u) else None, "text": u.text if visible(u) else None, "evidence": u.evidence,
                       "product_id": u.product_id} for u in units],
            "capabilities": [c.model_dump(mode="json") for c in caps],
            "events": events,
            "used": {"n": len(used), "sessions": sorted({e["session_id"] for e in used if e["session_id"]}),
                     "answered_for_rd": len({e["session_id"] for e in used if e["session_id"] and e["ts"] < escalated.get(e["session_id"], "~")})},
            "points": dict(points),
        }

    def capability_view(self, doc_id, by):
        """V12.9 四屏的能力层：同一份报告编译出的能力，这个身份按知识库的可见规则（当前 active、受众不高于本层）看到哪些；
        能读到的结论另给原文。每屏用自己的身份读，裁剪在知识库里，不给报告本身。"""
        actor = self._actor(by)
        ids = {u.id for u in self.kb._units.values() if any(e.startswith(f"{doc_id}#") for e in u.evidence)}
        return {"level": level_of(actor),
                "capabilities": [c.model_dump(mode="json") for c in self.kb._visible_caps(actor) if set(c.based_on) & ids],
                "units": [{"id": u.id, "title": u.title, "text": u.text} for u in self.kb._units.values()
                          if u.id in ids and self.kb._readable(actor, u)]}

    def jue_timeline(self, target_id, viewer_id):
        viewer = self._actor(viewer_id, {"sales", "pm", "rd", "supervisor"})
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

    def _case(self, object_id, viewer_id):
        """一件事：一段会话和由它生成的需求单，以及与它们相关的事件和挂在知识对象上的决策。route_of 与 case_story 共用。"""
        viewer = self._actor(viewer_id)
        if object_id in self._requirements:
            object_id = self._requirements[object_id].session_ids[0]
        session = _find(self._sessions, object_id, "会话")
        if level_of(viewer) <= 1 and viewer_id not in (session.customer_id, session.sales_id,
                                                       self.config["customer_sales"].get(session.customer_id)):
            raise PermissionDenied("只能查看自己参与的会话")
        reqs = [r for r in self._requirements.values() if session.id in r.session_ids]
        rids = {r.id for r in reqs}
        events = [e for e in self.events.query() if e.session_id == session.id
                  or e.payload.get("requirement_id") in rids or e.payload.get("target") in rids
                  or rids & set(e.payload.get("requirement_ids", []))]
        linked = [q for q in self.bus.list(status=None)        # 挂在知识对象上、由这张单引出的决策（扩适用范围）
                  if rids & set(q.refs.get("requirement_ids", "").split(","))]
        return viewer, session, reqs, events, linked

    def route_of(self, object_id, viewer_id):
        """v6：一份需求当前走哪条路、经过了谁、绕过了谁。全部由事件与状态推出，不另存。
        四格状态：human = 该角色的人真实处理过；auto = 由 Agent / 觉代办；pending = 已到该角色、待处理；none = 未经过。"""
        viewer, session, reqs, events, linked = self._case(object_id, viewer_id)
        main = next((r for r in reversed(reqs) if r.status != "merged"), None)
        rids = {r.id for r in reqs}
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
            temp = tuple(match["temperature_c"]) if match.get("temperature_c") else None
            mismatches = {p.id: [{"slot": k, "value": known[k], "allowed": v}
                                 for situation in p.situations for k, v in situation.conditions.items()
                                 if k in known and known[k] not in v]
                                + [{"slot": "温度", "value": f"{temp[0]:g}℃" if temp[0] == temp[1] else f"{temp[0]:g}—{temp[1]:g}℃",
                                    "allowed": [f"{s.temperature_c[0]:g}—{s.temperature_c[1]:g}℃"]}
                                   for s in p.situations if temperature_match(temp, s.temperature_c) == "outside"]
                          for p in self.kb.products() if p.status == "released" and match["phenomenon"] in p.solves
                          and p.id not in match["candidate_ids"] and not consistent(p, known, temperature_c=temp)}
            excluded = [{"product_id": pid, "mismatch": m} for pid, m in mismatches.items() if m]
            why = {"by": esc.actor, "phenomenon": match["phenomenon"], "p_none": match["p_none"],
                   "scored_by": match["scored_by"], "excluded": excluded,
                   "candidates": [{"product_id": pid, "p": match["p_choice"][pid]} for pid in match["candidate_ids"]]}
        return {"session_id": session.id, "requirement_id": main.id if main else None, "origin": session.origin,
                "path": path, "roles": roles, "basis": basis, "why": why,
                "quote": next((t.text for t in session.turns if t.speaker == "customer"), ""),
                "n_human_steps": len(steps)}

    def pipeline(self, by):
        """V11.8（CEO-VIEW C1）：化言线上每件货（一段会话）按事件依次经过的工位，主管只读。相邻同一工位合并，记进入、离开时刻、
        经手人、是否绕回（需求单退回、试样未通过、推荐撤回改道）；arrived 是客户第一句，answered 是第一个有效答复（推荐、
        业务员答复或产品经理、研发本人处理）；used 是这件事用过的适用能力。只有工位与人，没有研发写的话。不另存。"""
        self._actor(by, {"supervisor"})
        cases = []
        for s in self.sessions():
            _, session, _, events, _ = self._case(s.id, by)
            human = {id(e) for e in _human_events(events)}
            stations = []
            for e in events:
                name, actor = _station(e), e.actor.removeprefix("agent:")
                loop = e.kind in ("requirement_returned", "recommendation_withdrawn") or e.kind == "trial" and e.payload["result"] != "pass"
                if stations and stations[-1]["station"] == name:
                    last = stations[-1]
                    last["leave"], last["loop"] = e.ts.isoformat(), last["loop"] or loop
                    last["by"] += [actor] if actor not in last["by"] else []
                else:
                    stations.append({"station": name, "enter": e.ts.isoformat(), "leave": e.ts.isoformat(), "by": [actor], "loop": loop})
            answered = next((e.ts for e in events if e.kind == "recommend" or id(e) in human
                             or e.kind == "turn" and e.actor.startswith("sales:")), None)
            cases.append({"session_id": session.id, "stations": stations, "arrived": events[0].ts.isoformat(),
                          "answered": answered.isoformat() if answered else None,
                          "used": sorted({e.payload["capability_id"] for e in events
                                          if e.kind == "capability_used" and e.payload["form"] == "applicable"})})
        return cases

    def case_story(self, object_id, viewer_id):
        """V11.1：一件事到现在的前情，按时间排列。每行写谁做的（主体：human 人 / agent Agent / jue 觉 / jev Jev / qi 契 /
        system 系统）、属于哪个角色、做了什么；waiting 是这件事上还开着的决策。全部由事件与问题总线推出，不另存。
        L0/L1 只看会话上的经过；需求单内部的起草、退回、决策与研发备注只给 L2 以上和决策的主人、签字人。"""
        viewer, session, reqs, events, linked = self._case(object_id, viewer_id)
        inner = level_of(viewer) >= 2
        rids = {r.id for r in reqs}
        slot = {s.id: s.label for s in self.seeds.slots}
        slots = lambda ids: "、".join(slot.get(s, s) for s in ids)
        phen = {p.id: p.label for p in self.seeds.phenomena}
        name = lambda a: self.actors[a].name.replace("（模拟）", "") if a in self.actors else a
        named = lambda a: name(a) + (" " if name(a)[-1:].isascii() else "")    # 「产品经理 Agent 准备」
        product = lambda pid: next((p.name.replace("（模拟）", "") for p in self.kb.products() if p.id == pid), pid)
        decision = {t.family: t.decision_label for t in self.templates.values()} | {"decrypt_request": "客户申请了解产品机理"}   # 解密申请不走模板
        questions = {q.id: q for q in self.bus.list(status=None)}
        mine = lambda q: inner or viewer_id in (q.owner_id, q.signer_id)

        def line(e):
            """(主体, 角色, 谁, 说明)；None = 不进前情（抽取、检索等过程记录，或与另一行说的是同一件事）。"""
            p, who = e.payload, e.actor
            act = lambda text: ("human", who.split(":")[0], who, text)
            if e.kind == "turn":
                if p["speaker"] == "customer":
                    return "human", "customer", session.customer_id, f"说：「{p['text']}」"
                if p["speaker"] == "assistant":      # 客户自助页上的化言
                    return "agent", None, "huayan", f"对客户说：「{p['text']}」"
                return "human", "sales", session.sales_id, f"对客户说：「{p['text']}」"
            if e.kind == "ask_hint" and p["slots"]:
                return "jue", None, "jue", f"判断还缺{slots(p['slots'])}，需要向客户问清"
            if e.kind == "match":
                n = len(p["candidate_ids"])
                return "jev", None, "jev", f"按已知条件查现有产品，{f'找到 {n} 个候选' if n else '没有合适的'}"
            if e.kind == "recommend":
                return "jev", None, "jev", f"推荐{product(p['product_id'])}"
            if e.kind == "escalate":
                if who == "jue:auto":
                    return "jue", None, who, "判断现有产品解决不了，把需求连同客户原话直接交给研发"
                return act("签字升级，需求交给研发")
            if e.kind == "requirement_created":
                what = phen.get(p["phenomenon"], "未识别现象")
                return "system", None, who, f"生成需求单（{what}），指派研发{name(p['assigned_rd'])}"
            if e.kind == "sales_assigned":
                return "jue", None, who, f"判断这是商务诉求，交给业务员{name(p['sales_id'])}"
            if e.kind == "reuse_proposed" and inner:
                return "agent", "pm", who, (f"查了现成产品，建议复用{product(p['product_id'])}" if p["product_id"]
                                            else "查了现成产品，没有可以直接复用的")
            if e.kind == "reuse_adopted":
                return act(f"采用现成产品{product(p['product_id'])}")
            if e.kind == "reuse_declined" and inner:
                return act("不采用复用建议")
            if e.kind == "question_published":
                q = questions[p["question_id"]]
                if not mine(q) or (q.resolution and q.resolution.by == "jue:auto"):
                    return None       # 觉自动执行的，由执行结果那一行说
                to = f"由{named(q.owner_id)}准备、{named(q.signer_id)}签字" if q.signer_id else f"交给{name(q.owner_id)}" if q.owner_id else "请客户在自助页回答"
                return "jue", None, "jue", f"提出决策「{decision[q.family]}」，{to}"
            if e.kind == "question_prepared" and mine(questions[p["question_id"]]):
                q = questions[p["question_id"]]
                return "agent", q.owner_role, p["by"], f"准备好了「{decision[q.family]}」"   # 谁的 Agent 由界面按 who 写
            if e.kind == "question_resolved" and p.get("action") == "dismiss" and mine(questions[p["question_id"]]):
                return act(f"判断「{decision[p['family']]}」现在不需要")
            if e.kind == "requirement_accepted":
                return act("接单立项")
            if e.kind == "requirement_returned" and inner:
                return act(f"先回问客户：{slots(p['slots'])}" if p.get("slots") else f"退回需求：{p['reason']}")
            if e.kind == "requirement_edited" and inner:
                what = "化学要点" if p["layer"] == 3 else "产品需求"
                return ("agent", "pm", who, f"起草{what}条目") if who == "pm:agent" else act(f"修改{what}条目")
            if e.kind == "requirement_translated":
                return act("确认化学要点")
            if e.kind == "project_declined":
                found = f"，已有产品{product(p['product_id'])}适用" if p["product_id"] else ""
                return act(f"判断不立项{found}" + (f"：{p['reason']}" if inner else ""))
            if e.kind == "trial":
                ok = p["result"] == "pass"
                cause = {"product": "产品本身", "equipment": "设备", "operation": "操作", "requirement": "需求条件缺失"}
                return act(f"录入试样结果：{'通过' if ok else '未通过'}" + ("" if ok or not inner else f"（{cause[p['cause']]}）"))
            if e.kind == "market_eval":
                return act(f"录入客户评价：{'满意' if p['result'] == 'pass' else '不满意'}")
            if e.kind == "requirements_merged":
                return act(f"签产品机会，把 {len(p['members']) + 1} 张同类需求合成一个课题")
            if e.kind == "scope_extended":
                return act(f"扩展{product(p['product_id'])}的适用范围")
            if e.kind == "product_released":
                return act(f"发布新品{product(p['product_id'])}")
            if e.kind == "capability_used":
                by = p["granted_by"]
                src = "产品资料" if by == "seed" else f"{name(by)}签过的判断"
                return "qi", None, by, f"按{src}确定要问哪些条件" if p["form"] == "ask" else f"按{src}确认产品适用"
            if e.kind == "decrypt_request":
                return act(f"申请了解{product(p['product_id'])}的作用原理，交研发审批")
            if e.kind == "decrypt_approve":
                return act(f"批准说明{product(p['product_id'])}的作用原理")
            if e.kind == "recommendation_withdrawn":
                return "qi", None, who, f"依据变了，{product(p['product_id'])}的推荐先停下，等研发复核"
            return None

        story = []
        for e in events:
            got = line(e)
            if got is None:
                continue
            subject, role, who, text = got
            if story and (story[-1]["who"], story[-1]["text"]) == (who, text):
                continue          # 同一人连着起草多条，只记一行
            if e.kind == "question_resolved" and story and story[-1]["who"] == who and story[-1]["ts"][:19] == e.ts.isoformat()[:19]:
                continue          # 不立项等动作同一刻顺带关掉的决策，由动作那一行说
            story.append({"ts": e.ts.isoformat(), "kind": e.kind, "subject": subject, "role": role, "who": who, "text": text})
            if e.kind == "match":         # V12.8 实况：Jev 的概率写在格子里
                story[-1]["jev"] = {"p_none": e.payload["p_none"], "p_choice": e.payload["p_choice"], "scored_by": e.payload["scored_by"]}
            elif e.kind == "recommend":
                story[-1]["jev"] = {"p": e.payload["p_choice"], "version": e.payload["version"]}
        waiting = [{"question_id": q.id, "family": q.family, "decision": decision[q.family], "owner_id": q.owner_id,
                    "signer_id": q.signer_id, "prepared": q.prepared_at is not None}
                   for q in self.bus.list(status="open") if mine(q) and (
                       q.refs.get("session_id") == session.id or q.refs.get("requirement_id") in rids or q in linked)]
        main = next((r for r in reversed(reqs) if r.status != "merged"), None)
        return {"session_id": session.id, "requirement_id": main.id if main else None, "story": story, "waiting": waiting}

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
        gap = self.preparation_gap(question_id)
        if gap:
            raise ValueError(gap)
        return self.bus.set_prepared(question_id, get_clock().now()).model_copy(deep=True)

    def preparation_gap(self, question_id):
        """v8：准备是否已经落在对象上——Agent 说做完了不算。缺什么返回什么，齐了返回空串；
        只查签字时门面要求先有的草稿，其余问题主人只需告知委托人。"""
        q = _find(self.bus.questions, question_id, "问题")
        req = self._requirements.get(q.refs.get("requirement_id"))
        if q.family == "accept_requirement" and not req.product_lang:
            return f"{req.id} 还没有产品需求条目，请用 draft_product_need 起草"
        # 接单前回问（带 slots）不是退回给产品经理，不要求改条目
        if q.family == "accept_requirement" and (last := ([
                e for e in self.events.query(["requirement_returned", "requirement_edited"])
                if e.payload["requirement_id"] == req.id and not e.payload.get("slots")] or [None])[-1])                 and last.kind == "requirement_returned":
            return f"{req.id} 被研发退回（{last.payload['reason']}），还没按理由修改产品需求条目，请用 edit_item 修改"
        if q.family == "reuse_product" and req.reuse is None:
            return f"{req.id} 还没有复用建议，查过后请用 propose_reuse 写下（没有可用产品也要写下）"
        if q.family == "confirm_translation" and not req.chem_lang:
            return f"{req.id} 还没有化学语言条目，请用 draft_chem_need 起草"
        if q.family == "confirm_translation" and (missing := [s for s in req.known_slots
                                                               if not any(i.slot == s for i in req.chem_lang)]):
            return f"{req.id} 的化学语言条目还没有承接条件 {'、'.join(missing)}，请用 draft_chem_need 按当前条件重新起草"
        if q.family == "release" and req.sheet is None:
            return f"{req.id} 还没有说明书草稿，请用 package_sheet 生成"
        if q.family in {"release", "seal_leak"} and (hits := self.leak_check(req.id, req.assigned_rd)):
            return (f"{req.id} 的说明书与用法仍有 {len(hits)} 句命中保密内容（句序号 "
                    f"{'、'.join(str(h.index) for h in hits)}，按「。；！？换行」切句、用法接续说明书编号），请用 edit_sheet 改写")
        if q.family == "sheet_mismatch" and not self._sheet_path(q.id).exists():
            return "还没有说明书补充句，请用 draft_sheet_revision 起草"
        if q.family == "opportunity" and not any(e.payload["question_id"] == q.id
                                                 for e in self.events.query(["merge_proposed"])):
            return "还没有合并建议，请用 propose_merge 写下"
        return ""

    # ---- v8：助手记忆（按委托人存；助手自己记，收工时归纳；人能看能删）----

    def memories(self, by):
        return [m.model_copy(deep=True) for m in self._memory.values() if m.principal == by and m.status == "active"]

    def recall_memory(self, query, by):
        grams = {query[i:i + 2] for i in range(len(query) - 1)}
        score = lambda m: len(grams & {t[i:i + 2] for t in [m.text + m.why] for i in range(len(t) - 1)})
        return sorted((m for m in self.memories(by) if score(m)), key=score, reverse=True)[:5]

    def remember(self, kind, text, why, refs, by):
        actor = self._actor(by, {"sales", "pm", "rd"})
        if not text.strip():
            raise ValueError("记忆不能为空")
        if leak_hits(f"{text}。{why}", [], [], self.kb, audience=level_of(actor)):
            raise ValueError("记忆里有高于委托人层级的内容，不能记")
        entry = MemoryEntry(id=f"mem:{len(self._memory) + 1}", principal=by, kind=kind, text=text.strip(),
                            why=why.strip(), refs=refs, at=get_clock().now())
        self._memory[entry.id] = entry
        self._save_memory()
        return entry.model_copy(deep=True)

    def forget(self, memory_id, by):
        entry = _find(self._memory, memory_id, "记忆")
        if entry.principal != by:
            raise PermissionDenied("只能删自己助手的记忆")
        entry.status = "deleted"
        self._save_memory()

    def _save_memory(self):
        (self.run_dir / "memory.json").write_text(json.dumps([m.model_dump(mode="json") for m in self._memory.values()],
                                                              ensure_ascii=False), encoding="utf-8")

    def decision_records(self, by, since):
        """收工归纳的材料，程序从事件生成、不调用大模型：这位委托人主人或签字的问题怎么被处理的、
        研发的退回理由、业务员当天的会话；只含委托人这一层看得到的内容。"""
        actor = self._actor(by, {"sales", "pm", "rd"})
        rows = []
        for e in self.events.query(["question_resolved"], since=since):
            q = self.bus.questions[e.payload["question_id"]]
            if by in (q.owner_id, q.signer_id):
                note = q.resolution.note if q.resolution else ""
                rows.append(f"{q.id} {q.title}｜主人 {q.owner_id}，签字人 {q.signer_id}｜{e.payload['by']} 处理：{e.payload['action']}"
                            + (f"，说明：{note}" if note else ""))
        mine = {q.refs.get("requirement_id") for q in self.bus.questions.values() if by in (q.owner_id, q.signer_id)}
        returned = [e for e in self.events.query(["requirement_returned"], since=since) if e.payload["requirement_id"] in mine]
        if actor.role == "sales":          # 退回理由是研发的话（L2/L3）；业务员只看要回问客户的条件
            labels = {s.id: s.label for s in self.seeds.slots}
            rows += [f"{e.payload['requirement_id']} 研发要回问客户：{'、'.join(labels[s] for s in e.payload['slots'])}"
                     for e in returned if e.payload.get("slots")]
        else:
            rows += [f"{e.payload['requirement_id']} 被 {e.actor} 退回：{e.payload['reason']}" for e in returned]
        if actor.role == "sales":
            for s in self._sessions.values():
                if s.sales_id == by and s.started_at >= since:
                    known = "、".join(f"{k}={v.value}" for k, v in s.need.slots.items() if v.status == "filled") or "无"
                    unknown = "、".join(k for k, v in s.need.slots.items() if v.status == "unknown") or "无"
                    rows.append(f"{s.id} 客户 {s.customer_id}：现象 {s.need.phenomenon}；说清的 {known}；说不清的 {unknown}；"
                                f"结果 {s.status}")
        return rows

    def timeline(self, day, by):
        """v8 Q9.5：主管只读的一天。泳道（客户、各人与其助手、产品经理 Agent、觉、契）上的事件、当天结束时的状态看板、
        KPI、模板小结与三件高光；不调大模型。研发的话与上层结论只给存根「研发知识 · 归属某人」。"""
        self._actor(by, {"supervisor"})
        day = date.fromisoformat(str(day))
        events = self.events.query()
        names = {a.id: a.name for a in self.seeds.actors}
        today = [e for e in events if e.ts.date() == day]
        until = [e for e in events if e.ts.date() <= day]
        questions = {q.id: q for q in self.bus.list(status=None)}
        upper = [u.text for u in self.kb._units.values() if u.level > 2 and u.kind != "trial"]

        def lane(e):
            actor = e.actor.removeprefix("agent:")
            if e.kind in _QI_KINDS:
                return "qi"
            if actor.startswith("jue") or e.kind == "question_published":
                return "jue"
            if actor.startswith("customer:"):
                return "customer"
            return actor if actor in names else "jue" if actor.startswith("system") else None

        def stub(owner):
            return f"研发知识 · 归属{names.get(owner, owner)}"

        def safe(text, owner=None):
            """研发写的话一律给存根；其余文字若与上层结论重合也给存根。"""
            if owner and owner.removeprefix("agent:").startswith("rd:"):
                return stub(owner.removeprefix("agent:"))
            return stub("研发") if leak_hits(text, upper, [], self.kb, audience=2) else text

        def detail(e):
            p = e.payload
            if e.kind == "question_published":
                q = questions.get(p["question_id"])
                return f"觉提出：{q.title if q else p['family']}（{p['family']}）"
            if e.kind == "question_resolved":
                q = questions.get(p["question_id"])
                note = q.resolution.note if q and q.resolution else ""
                return f"{names.get(p['by'], p['by'])} {_ACTIONS.get(p['action'], p['action'])}：{p['family']}" + (
                    f"；{safe(note, p['by'])}" if note else "")
            if e.kind == "requirement_returned":
                return f"{p['requirement_id']} 退回" + (f"，回问 {'、'.join(p['slots'])}" if p.get("slots") else "") + \
                    f"；理由：{stub(e.actor)}"
            if e.kind == "requirement_translated":
                return f"{p['requirement_id']} 化学要点 {len(p['ku_refs'])} 条：{stub(e.actor)}"
            if e.kind == "requirement_edited":
                return f"{p['requirement_id']} 第 {p['layer']} 层第 {p['index'] + 1} 条" + (
                    f"：{stub(e.actor)}" if p["layer"] == 3 else "改写")
            if e.kind == "trial":
                return (f"{p['product_id']} 试样{'通过' if p['result'] == 'pass' else '失败'}"
                        f"（{p.get('requirement_id') or '客户送样'}；原因 {p['cause']}）")
            if e.kind == "capability_granted":
                return f"{names.get(e.actor, e.actor)} 授予 {p['id']}（{p['form']} → L{p['audience']}）"
            if e.kind == "capability_used":
                return f"{p['capability_id']} 被使用（{p['form']}）"
            keys = ("requirement_id", "product_id", "capability_id", "ku_id", "actor_id", "customer_id", "sales_id")
            return " ".join([_KIND_LABEL.get(e.kind, e.kind)] + [str(p[k]) for k in keys if p.get(k)])

        items = [{"id": e.id, "lane": lane(e), "at": e.ts.isoformat(), "kind": e.kind, "actor": e.actor,
                  "family": e.payload.get("family"), "session_id": e.session_id, "text": detail(e)}
                 for e in sorted(today, key=lambda e: e.ts) if e.kind not in _QUIET and lane(e)]
        sessions = []
        for sid in dict.fromkeys(e.session_id for e in today if e.kind == "turn" and e.session_id):
            s = self._sessions[sid]
            turns = [e for e in events if e.kind == "turn" and e.session_id == sid]
            sessions.append({"id": sid, "customer": s.customer_id, "sales": s.sales_id, "status": s.status,
                             "phenomenon": s.need.phenomenon, "start": min(t.ts for t in turns if t.ts.date() == day).isoformat(),
                             "end": max(t.ts for t in turns if t.ts.date() == day).isoformat(),   # 回问的回答可能在别的天
                             "turns": [{"at": t.ts.isoformat(), "speaker": t.payload["speaker"],
                                        "text": safe(t.payload["text"]) if t.payload["speaker"] != "customer" else t.payload["text"]}
                                       for t in turns]})
        status = {}
        for e in until:
            for rid in (e.payload.get("members") or [e.payload.get("requirement_id")]):
                if rid and e.kind in _REQ_STATE:
                    status[rid] = _REQ_STATE[e.kind](e.payload)
        board = {"requirements": {k: sorted(r for r, v in status.items() if v == k) for k in dict.fromkeys(status.values())},
                 "capabilities": dict(Counter(_CAP_STATE[e.kind] for e in until if e.kind in _CAP_STATE)),
                 "jue": {"model": self.jue_realtime.name, "version": Path(self.config["jue_k_dir"]).name
                         if self.jue_realtime.name == "jue_k" else None}}
        count = Counter(e.kind for e in today)
        raised = Counter(e.payload["family"] for e in today if e.kind == "question_published")
        trials = [e for e in today if e.kind == "trial"]
        kpi = {"sessions": len(sessions), "recommended": count["recommend"], "escalated": count["escalate"],
               "raised": sum(raised.values()), "interrupts": raised["trial_risk"] + raised["stale_capability"],
               "signed": sum(e.kind == "question_resolved" and not e.payload["by"].startswith("jue") for e in today),
               "auto": count["auto_executed"], "trials": len(trials),
               "trial_fail": sum(e.payload["result"] == "fail" for e in trials), "released": count["product_released"]}
        summary = (f"{day:%m月%d日}：客户来访 {kpi['sessions']} 段，给出推荐 {kpi['recommended']} 次，升级 {kpi['escalated']} 单；"
                   f"觉提出 {kpi['raised']} 个问题（试样风险 {raised['trial_risk']}、判断过时 {raised['stale_capability']}），"
                   f"人签字 {kpi['signed']} 次、觉自动执行 {kpi['auto']} 次；试样 {kpi['trials']} 次，失败 {kpi['trial_fail']} 次。")
        rank = lambda i: (-_HIGHLIGHT.get(i["family"] or i["kind"], 0), i["at"])   # noqa: E731
        highlights = [i for i in sorted(items, key=rank) if _HIGHLIGHT.get(i["family"] or i["kind"])][:3]
        lanes = ([{"id": "customer", "label": "客户"}]
                 + [{"id": a.id, "label": a.name} for a in self.seeds.actors if a.role in ("sales", "pm", "rd", "supervisor")]
                 + [{"id": "jue", "label": "觉"}, {"id": "qi", "label": "契"}])
        cases, discoveries = self._cases(day, until, questions, names, safe)
        return {"day": day.isoformat(), "days": sorted({e.ts.date().isoformat() for e in events if e.kind == "turn"}),
                "lanes": lanes, "items": items, "sessions": sessions, "board": board, "kpi": kpi,
                "summary": summary, "highlights": highlights, "cases": cases, "discoveries": discoveries,
                "qi": self._qi_day(day, until, names, upper)}

    def _cases(self, day, until, questions, names, safe):
        """v8 Q9.5 案件：以一段客户会话为起点，串上它的需求单、觉的问题（提出 → 准备 → 签字）与试样，截至当天结束。
        当天有动静的案件才列出。返回 (案件, 当天觉提出的发现类问题)。"""
        end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=SHANGHAI)
        labels = {t.family: t.decision_label for t in self.templates.values()}
        phen = {p.id: p.label for p in self.seeds.phenomena}
        slots = {s.id: s for s in self.seeds.slots}
        sess_req = {}
        for r in self._requirements.values():
            for sid in r.session_ids:
                sess_req.setdefault(sid, []).append(r.id)
        req_sess = {rid: sid for sid, rids in sess_req.items() for rid in rids}

        def case_of(object_id):
            kind, _, rest = object_id.partition(":")
            if kind == "slot":
                rest = rest.rsplit("/", 1)[0]
            if rest in self._sessions:
                return rest
            return req_sess.get(rest)

        def who(actor):
            if actor.startswith("jue"):
                return "觉"
            return names.get(actor.removeprefix("agent:"), actor)

        def decision(q):
            res = q.resolution if q.resolved_at and q.resolved_at < end else None
            step = {"at": q.created_at.isoformat(), "kind": "decision", "family": q.family,
                    "label": labels.get(q.family, q.family), "discovery": q.family in _DISCOVERY,
                    "scored_by": q.scored_by, "p": q.p_need, "object": q.object_id,
                    "owner": who(q.owner_id) if q.owner_id else None,
                    "prepared_at": q.prepared_at.isoformat() if q.prepared_at and q.prepared_at < end else None,
                    "signer": who(q.signer_id) if q.signer_id else None, "status": "open"}
            if q.family == "ask_back":
                step["ask"] = slots[q.refs["slot"]].ask_text
            if res:
                step.update(status=q.status, done_at=q.resolved_at.isoformat(), by=who(res.by),
                            action=_ACTIONS.get(res.action, res.action), note=safe(res.note, res.by) if res.note else "")
            return step

        steps, touched = {}, set()
        for q in questions.values():
            sid = case_of(q.object_id) if q.created_at < end else None
            if sid:
                steps.setdefault(sid, []).append(decision(q))
                touched |= {sid} if q.created_at.date() == day or (q.resolved_at and q.resolved_at.date() == day) else set()
        for e in until:
            sid = e.session_id or req_sess.get(e.payload.get("requirement_id"))
            if not sid or e.kind not in _CASE_FACTS:
                continue
            p = e.payload
            fact = {"at": e.ts.isoformat(), "kind": e.kind, "by": who(e.actor), "text": _CASE_FACTS[e.kind](p, names)}
            if e.kind == "trial":
                fact["tone"] = "ok" if p["result"] == "pass" else "fail"
            if e.kind == "capability_used":
                unit = self.kb._units.get((p.get("based_on") or [""])[0])
                fact["owner"] = names.get(unit.owner, "企业资料（第 0 天迁移）") if unit else "企业资料（第 0 天迁移）"
                fact["text"] = f"{fact['owner']}的{_FORMS.get(p['form'], p['form'])}"
            steps.setdefault(sid, []).append(fact)
            touched |= {sid} if e.ts.date() == day else set()
        cases = []
        for sid in sorted(touched, key=lambda s: self._sessions[s].started_at):
            s = self._sessions[sid]
            turns = [e for e in until if e.kind == "turn" and e.session_id == sid]
            story = sorted(steps.get(sid, []) + [
                {"at": t.ts.isoformat(), "kind": "turn", "speaker": t.payload["speaker"],
                 "text": t.payload["text"] if t.payload["speaker"] == "customer" else safe(t.payload["text"])}
                for t in turns], key=lambda x: (x["at"], x["kind"] != "turn"))
            cases.append({"id": sid, "key": f"{s.customer_id}|{s.started_at.isoformat()}", "customer": s.customer_id,
                          "customer_name": names.get(s.customer_id, s.customer_id), "sales": who(s.sales_id) if s.sales_id else None,
                          "phenomenon": phen.get(s.need.phenomenon, s.need.phenomenon or "未判明"),
                          "opening": next((t.payload["text"] for t in turns if t.payload["speaker"] == "customer"), ""),
                          "started_at": s.started_at.isoformat(), "requirements": sess_req.get(sid, []),
                          "story": story, "outcome": _outcome(story, s.status)})
        discoveries = [decision(q) | {"case": case_of(q.object_id), "title": q.title}
                       for q in sorted(questions.values(), key=lambda q: q.created_at)
                       if q.family in _DISCOVERY and q.family not in ("ask_slot", "ask_back") and q.created_at.date() == day]
        return cases, discoveries

    def _qi_day(self, day, until, names, upper):
        """v8 Q9.5 契的一天：谁的判断被用了几次、当天人签的授予与撤销（附授予后至今的使用次数）、拦下的越层读取、
        对外的话里与上层结论重合的句数（应为 0）、当天记分。"""
        today = [e for e in until if e.ts.date() == day]
        used = Counter()
        for e in today:
            if e.kind == "capability_used":
                unit = self.kb._units.get((e.payload.get("based_on") or [""])[0])
                used[names.get(unit.owner, "种子资料") if unit else "种子资料"] += 1
        uses = Counter(e.payload["capability_id"] for e in until if e.kind == "capability_used")
        grants = [{"at": e.ts.isoformat(), "kind": _CAP_STATE[e.kind], "by": names.get(e.actor, e.actor),
                   "capability": e.payload.get("id") or e.payload.get("capability_id"),
                   "form": _FORMS.get(e.payload.get("form"), e.payload.get("form")),
                   "audience": e.payload.get("audience"),
                   "uses_since": uses[e.payload.get("id") or e.payload.get("capability_id")]}
                  for e in today if e.kind in _CAP_STATE and not e.actor.startswith(("seed", "system"))]
        outbound = [e.payload["text"] for e in today if e.kind == "turn" and e.payload["speaker"] == "assistant"]
        leaked = sum(bool(leak_hits(t, upper, [], self.kb, audience=1)) for t in outbound)
        points = Counter()
        for r in self.ledger.list():
            if r.ts.date() == day:
                points[names.get(r.owner, r.owner)] += r.points
        return {"used_by_owner": dict(used.most_common()), "used_total": sum(used.values()), "grants": grants,
                "denied": sum(e.kind == "access_denied" for e in today), "outbound": len(outbound), "leaked": leaked,
                "points": dict(points.most_common())}

    def close_day(self, since):
        """v8：收工时各助手归纳当天的记忆（agent_memory 打开时）；只整理助手自己的记忆，不推进业务。"""
        if not self.config["agent_memory"]:
            return {}
        principals = [a.id for a in self.seeds.actors if a.role in ("sales", "rd")] + ["pm:agent"]
        return {p: self.agents.consolidate(p, since) for p in principals}

    def tick(self):
        now = get_clock().now()
        found = []
        if self._last_scan is None or now - self._last_scan >= timedelta(minutes=30):
            found += self.scan(now)
        self.agents.dispatch()
        return [q.model_copy(deep=True) for q in found]


def _station(e):
    """V11.8 化言线的工位：试样；产品经理 Agent；业务员 / 产品经理 / 研发本人；契（匹配、推荐、能力）；客户；其余是觉（抽取、追问、决策、升级）。"""
    actor = e.actor.removeprefix("agent:")
    role = actor.split(":")[0]
    if e.kind == "trial":
        return "试样"
    if actor == "pm:agent":
        return "Agent"
    if role in ("sales", "pm", "rd"):
        return {"sales": "业务员", "pm": "产品经理", "rd": "研发"}[role]
    if e.kind in ("match", "recommend", "recommendation_withdrawn") or e.kind in _QI_KINDS:
        return "契"
    return "客户" if e.kind == "turn" and role == "customer" else "觉"


# v8 Q9.5 主管时间线 -------------------------------------------------------------------------------
_QUIET = {"turn", "extraction", "retrieve", "ask_hint", "match"}          # 原话进会话块；检索与打分不上泳道
_QI_KINDS = {"capability_granted", "capability_revoked", "capability_suspended", "capability_used", "claim_confirmed",
             "claim_withdrawn", "evidence_changed", "scope_extended", "share_requested"}
_ACTIONS = {"sign": "签字", "answered": "结案", "auto": "自动执行", "dismiss": "越过", "accept": "接单", "return": "退回",
            "freeze_access": "冻结", "take_over": "接手", "update_sheet": "改说明书", "reject_decrypt": "拒绝解密"}
_KIND_LABEL = {"recommend": "推荐", "escalate": "升级", "requirement_created": "建单", "requirement_accepted": "接单",
               "reuse_proposed": "复用提议", "sales_assigned": "派业务员", "auto_executed": "觉自动执行",
               "question_prepared": "助手准备好", "project_opened": "立项", "market_eval": "客户评价",
               "points_set": "封存与放出", "knowledge_contributed": "沉淀", "product_released": "发布新品",
               "decrypt_request": "申请解密", "decrypt_approve": "批准解密", "access_frozen": "冻结上层知识检索", "access_unfrozen": "解冻",
               "access_denied": "拦下越权读取", "agent_action_proposed": "助手提议", "agent_action_decided": "人确认提议",
               "capability_revoked": "撤销能力", "capability_suspended": "能力挂起", "claim_confirmed": "确认结论",
               "evidence_changed": "依据变了", "scope_extended": "扩展适用范围", "share_requested": "申请查看同事知识",
               "requirements_merged": "合并需求", "sheet_updated": "改说明书", "human_decision": "人直接决定"}
_REQ_STATE = {"requirement_created": lambda p: "待接单", "requirement_accepted": lambda p: "已接单",
              "requirement_returned": lambda p: "退回补条件", "requirement_translated": lambda p: "要点已确认",
              "trial": lambda p: "试样通过" if p["result"] == "pass" else "试样失败",
              "market_eval": lambda p: "客户评价通过" if p["result"] == "pass" else "客户评价不通过",
              "product_released": lambda p: "已发布", "requirements_merged": lambda p: "已合并",
              "reuse_adopted": lambda p: "复用已有产品"}
_CAP_STATE = {"capability_granted": "授予", "capability_revoked": "撤销", "capability_suspended": "挂起",
              "claim_confirmed": "结论确认", "evidence_changed": "待复核"}
# 觉的发现（打分可以学；其余为流程推进点，两组都是规则到点）
_DISCOVERY = {"ask_slot", "ask_back", "trial_risk", "stale_capability", "opportunity", "knowledge_conflict", "leak_risk",
              "mechanism_followup", "distortion", "seal_leak", "qi_review"}
_FORMS = {"ask": "追问", "applicable": "适用判断", "statement": "对外说法", "phrase": "说法", "translation": "转化对照",
          "decrypt": "解密", "share": "同层共享"}
_CASE_FACTS = {
    "recommend": lambda p, n: f"推荐 {p['product_id']}" if p.get("product_id") else "没有合适的已发布产品",
    "requirement_created": lambda p, n: f"建需求单 {p['requirement_id']}，派给{n.get(p.get('assigned_rd'), '研发')}",
    "requirement_translated": lambda p, n: f"{p['requirement_id']} 化学要点 {len(p['ku_refs'])} 条（研发知识，只显示归属）",
    "requirement_returned": lambda p, n: f"{p['requirement_id']} 退回" + (f"，回问 {'、'.join(p['slots'])}" if p.get("slots") else ""),
    "trial": lambda p, n: f"{p['product_id']} 试样{'通过' if p['result'] == 'pass' else '失败'}"
                          + ("" if p["result"] == "pass" else f"（{_CAUSE.get(p['cause'], p['cause'])}）"),
    "market_eval": lambda p, n: f"客户评价{'通过' if p['result'] == 'pass' else '不通过'}",
    "project_opened": lambda p, n: "立项",
    "product_released": lambda p, n: f"发布新品 {p['product_id']}",
    "sales_assigned": lambda p, n: f"交给{n.get(p.get('sales_id'), '业务员')}跟进",
    "access_frozen": lambda p, n: f"冻结了{n.get(p['actor_id'], p['actor_id'])}的上层知识检索",
    "access_unfrozen": lambda p, n: f"解冻{n.get(p['actor_id'], p['actor_id'])}",
    "decrypt_request": lambda p, n: "客户申请了解原理（解密）",
    "decrypt_approve": lambda p, n: "研发批准解密",
    "capability_used": lambda p, n: "",
}
_CAUSE = {"requirement": "需求条件缺失", "product": "产品本身不合用", "equipment": "设备、操作原因"}


def _outcome(story: list[dict], status: str) -> dict:
    """案件截至当天的结局：已解决 / 失败 / 等谁做什么。"""
    trials = [x for x in story if x["kind"] == "trial"]
    evals = [x for x in story if x["kind"] == "market_eval"]
    waiting = [x for x in story if x["kind"] == "decision" and x["status"] == "open"
               and x["family"] not in ("ask_slot", "contribution", "contribution_pm", "seal_points")]
    if evals and evals[-1]["text"].endswith("通过") and not evals[-1]["text"].endswith("不通过"):
        return {"state": "done", "text": "试样通过、客户评价通过"}
    if waiting:
        w = waiting[-1]
        actor = "客户" if w["family"] == "ask_back" else (w["signer"] if w["prepared_at"] or not w["owner"] else w["owner"])
        verb = "回答回问" if w["family"] == "ask_back" else f"{'签字' if w['prepared_at'] else '准备'}：{w['label']}"
        return {"state": "open", "text": f"等{actor}{verb}", "since": w["at"]}
    if trials:
        return {"state": "done" if trials[-1]["tone"] == "ok" else "fail", "text": trials[-1]["text"]}
    rec = [x for x in story if x["kind"] == "recommend"]
    if rec and rec[-1]["text"].startswith("推荐"):
        return {"state": "done", "text": f"L1 {rec[-1]['text']}"}
    return {"state": "open", "text": {"open": "会话进行中", "escalated": "已升级，研发处理中", "recommended": "已推荐产品", "closed": "已结束"}[status]}


_HIGHLIGHT = {"product_released": 9, "access_frozen": 8, "access_unfrozen": 7, "mechanism_followup": 6, "trial_risk": 8, "stale_capability": 8, "knowledge_conflict": 7,
              "leak_risk": 7, "opportunity": 7, "decrypt_approve": 7, "capability_suspended": 6, "evidence_changed": 6,
              "scope_extended": 5, "share_requested": 5}
