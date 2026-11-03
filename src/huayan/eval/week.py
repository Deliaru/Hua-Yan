"""WP-E / WP-J 业务周运行器：按剧本驱动真实链路（门面），每 2 个业务小时做一次定时发现。
默认抽取为规则、Jev 为桩；显式config_path时沿所给真实模型配置运行。流程只由觉提出的问题推进：hub 派单准备，
「模拟人」在问题进入待签后按 C12 签字（模拟退回率 0，不产生 human_decision）。
运行器扮演客户所以读需求卡；处置分支读注入清单决定定时三类签不签（铁律 5：只有 sim/、eval/ 可读）。"""
import json
import random
import shutil
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, get_clock, set_clock
from huayan.contracts import Event, Injection, NeedCard, Question, Trial, WeekItem
from huayan.events import EventLog
from huayan.jue.proto import JueProto, load_templates
from huayan.sim import SimCustomer, to_jsonl
from huayan.sim.week_events import TICK_HOURS

RULE_ALERT = "config/baselines/rule_alert"
SCHEDULED = ("opportunity", "knowledge_conflict", "leak_risk")
TRIAL_DELAY = timedelta(days=1)                            # 确认转译 1 个业务日后模拟 ELN 录入试样通过


def run_week(week_dir: str | Path, policy: str, discoverer: str, run_root: str = "runs", seed: int = 0,
             *, config_path: str | Path | None = None) -> Path:
    """policy ∈ {handle, ignore}；discoverer ∈ {jue_proto, rule_alert, jue_k}。返回运行目录。
    ignore：定时三类与接单都不签（机会汇聚无人处理）；handle：定时三类按注入清单签，其余 dismiss。"""
    week_dir = Path(week_dir)
    items = [WeekItem.model_validate_json(l) for l in (week_dir / "script.jsonl").read_text(encoding="utf-8").splitlines()]
    cards = {c.id: c for c in (NeedCard.model_validate_json(l)
                               for l in (week_dir / "cards.jsonl").read_text(encoding="utf-8").splitlines())}
    positives = set()
    if policy == "handle":
        positives = {(i.family, i.object_id) for i in (Injection.model_validate_json(l) for l in
                     (week_dir / "injections.jsonl").read_text(encoding="utf-8").splitlines()) if not i.hard_negative}
    start = datetime.combine(items[0].at.date(), time(9), tzinfo=items[0].at.tzinfo)
    clock = SimClock(start)
    set_clock(clock)
    app = _build(run_root, f"week-{week_dir.name}-{discoverer}-{policy}", discoverer, config_path)
    humans = _Humans(app, policy, positives)

    days = (items[-1].at.date() - start.date()).days + 1
    scans = [datetime.combine(start.date() + timedelta(days=d), time(h), tzinfo=start.tzinfo)
             for d in range(days) for h in TICK_HOURS]
    timeline = sorted([(it.at, 1, it) for it in items] + [(at, 0, None) for at in scans], key=lambda x: (x[0], x[1]))
    for at, _, item in timeline:
        for due, req_id, rd in sorted(t for t in humans.trials if t[0] <= at):
            humans.trials.remove((due, req_id, rd))
            clock.advance_to(max(due, clock.now()))
            humans.trial(req_id, rd)
            humans.settle()
        clock.advance_to(at)
        if item is None:
            app.scan(at)
        elif item.kind == "session":
            humans.session(cards[item.card_id], item.actor, random.Random(f"{seed}:{item.card_id}"))
        elif item.kind == "trial":
            app.record_trial(item.trial)
        else:
            app.kb.search(item.text, app.actors[item.actor])        # 以该业务员身份提问
        humans.settle()
    (app.run_dir / "week_log.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in humans.log),
                                                encoding="utf-8")
    set_clock(None)
    return app.run_dir


def chain_events(items: list[WeekItem], cards: list[NeedCard], work_dir: Path, name: str) -> EventLog:
    """Jue-K 定时样本用：把一个生成的业务周写到 work_dir/name，按 ignore 分支在真实链路上跑一遍，读回事件日志。"""
    week_dir = work_dir / name
    week_dir.mkdir(parents=True, exist_ok=True)
    (week_dir / "script.jsonl").write_text(to_jsonl(items), encoding="utf-8")
    (week_dir / "cards.jsonl").write_text(to_jsonl(cards), encoding="utf-8")
    run = run_week(week_dir, "ignore", "jue_proto", str(work_dir))
    events = EventLog()
    events.events = [Event.model_validate_json(l) for l in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return events


def _build(run_root: str, run_id: str, discoverer: str, config_path=None) -> HuayanApp:
    config = yaml.safe_load(Path(config_path or "config/app.yaml").read_text(encoding="utf-8"))
    config.update(run_root=run_root, scheduled_model="jue_k" if discoverer == "jue_k" else "jue_proto")
    run_dir = Path(run_root) / run_id
    if config_path is None:
        config.update(extractor="rule", system1_impl="mock", gateway_mock=True)
        shutil.rmtree(run_dir, ignore_errors=True)         # 兼容既有离线评测重跑。
    else:
        if config["gateway_mock"] or config["system1_impl"] != "onejev" or config["extractor"] != "llm" or config["replay"]:
            raise ValueError("显式业务周配置须使用真实抽取/助手及System1，不接受mock、fallback或回放")
        if config["qi_state"] is not None:
            raise ValueError("在线模拟周须qi_state=null，不能写入既有知识状态")
        if run_dir.exists():
            raise ValueError("在线模拟周运行目录已存在，请另选输出目录保留原记录")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, allow_unicode=True)
    app = HuayanApp.build(stream.name, run_id)
    if discoverer == "rule_alert":                         # 常见告警规则：同一主题升级 ≥ 3 次；只替换定时三类的模板
        app.jue_scheduled = JueProto(RULE_ALERT, app.system1, "scheduled", app.meter)
        app.jue_scheduled.name = "rule_alert"
        app.templates = {**{k: t for k, t in app.templates.items() if t.family not in SCHEDULED},
                         **load_templates(RULE_ALERT)}
    return app


class _Humans:
    """模拟业务员、研发、主管：只签进入待签（prepared_at 有值）的问题，签法见 WP-J 第 7 项（C12）。"""

    def __init__(self, app: HuayanApp, policy: str, positives: set[tuple[str, str]]):
        self.app, self.policy, self.positives = app, policy, positives
        self.customers: dict[str, SimCustomer] = {}
        self.approved: set[str] = set()                    # 机会汇聚指向、研发愿意接的需求单
        self.trials: list[tuple[datetime, str, str]] = []  # (到期时刻, 需求单, 研发)
        self.done: set[tuple[str, datetime | None]] = set()
        self.log: list[dict] = []

    def session(self, card: NeedCard, sales: str, rng: random.Random) -> None:
        """模拟客户开场 → 按觉的提示追问 → 直到推荐或没有提示（最多 8 轮）；仍未推荐时 recommend_now。"""
        app = self.app
        customer = SimCustomer(card, app.seeds, rng)
        sid = app.start_session(card.customer_id, sales).id
        self.customers[sid] = customer
        s = app.add_turn(sid, "customer", customer.opening())
        for _ in range(8):
            if s.status != "open" or not s.hints:
                break
            ask = s.hints[0].ask_text
            app.add_turn(sid, "sales", ask)
            s = app.add_turn(sid, "customer", customer.reply(ask))
        if s.status == "open":
            app.recommend_now(sid)

    def trial(self, req_id: str, rd: str) -> None:
        req = self.app.requirement_view(req_id, rd).requirement
        self.app.record_trial(Trial(id=f"trial:{req_id}", product_id=req.product_id, requirement_id=req_id, rd=rd,
                                    conditions=req.known_slots, result="pass", cause="none", at=get_clock().now()))
        self._log("trial", req_id, "record_trial", rd)

    def settle(self) -> None:
        """派单 → 签所有待签问题、回答回问，直到没有新动作。"""
        while True:
            self.app.agents.dispatch()
            acted = False
            for q in self.app.bus.list():
                if (q.id, q.prepared_at) in self.done or (q.prepared_at is None and q.family != "ask_back"):
                    continue
                action = self._act(q)
                if action is None:
                    continue
                self.done.add((q.id, q.prepared_at))
                acted = True
            if not acted:
                return

    def _act(self, q: Question) -> str | None:
        """返回所做的动作；None = 现在不处理（保持待签）。门面拒绝时记入日志，不重试。"""
        app, f, by = self.app, q.family, q.signer_id
        req_id = q.refs.get("requirement_id")
        try:
            if f == "ask_back":
                return self._ask_back(q)
            if f in SCHEDULED:
                return self._scheduled(q)
            if f == "escalate_need":
                app.escalate(q.refs["session_id"], by)
            elif f == "reuse_product":
                app.adopt_reuse(req_id, by)
            elif f == "accept_requirement":
                if req_id not in self.approved:
                    return None
                app.accept_requirement(req_id, by)
            elif f == "confirm_translation":
                app.confirm_translation(req_id, by)
                self.trials.append((get_clock().now() + TRIAL_DELAY, req_id, by))
            elif f == "market_eval":
                app.record_market_eval(req_id, "pass", "（模拟）客户试用通过", by)
            elif f == "seal_points":
                app.set_public_points(req_id, "（模拟）按需求单条件试样通过；按推荐用量使用。", [], by)
            elif f == "release":
                product = next(p for p in app.seeds.products if p.id == app._requirements[req_id].product_id)
                app.release_product(req_id, by, product.name, product.category)   # 模拟研发沿用立项时的名称与类别
            else:                                          # 失真、对外泄密、沉淀等：模拟人不处理内容，直接 dismiss
                app.resolve(q.id, "dismiss", by)
                return self._log(f, q.object_id, "dismiss", by, q.id)
        except ValueError as exc:
            return self._log(f, q.object_id, "rejected", by, q.id, str(exc))
        return self._log(f, q.object_id, "sign", by, q.id)

    def _ask_back(self, q: Question) -> str:
        """业务员向客户回问一句，客户按需求卡回答；门面据回答结案并回填。"""
        sid = q.refs["session_id"]
        ask = next(s.ask_text for s in self.app.seeds.slots if s.id == q.refs["slot"])
        self.app.add_turn(sid, "sales", ask)
        self.app.add_turn(sid, "customer", self.customers[sid].reply(ask))
        return self._log("ask_back", q.object_id, "answered", q.owner_id, q.id)

    def _scheduled(self, q: Question) -> str | None:
        if self.policy != "handle":
            return None
        app, by = self.app, q.signer_id
        if (q.family, q.object_id) not in self.positives:
            app.resolve(q.id, "dismiss", by)
            return self._log(q.family, q.object_id, "dismiss", by, q.id)
        if q.family != "opportunity":
            app.resolve(q.id, {"knowledge_conflict": "update_sheet", "leak_risk": "freeze_access"}[q.family], by)
            return self._log(q.family, q.object_id, "sign", by, q.id)
        proposal = next(e.payload for e in reversed(app.events.query(["merge_proposed"]))
                        if e.payload["question_id"] == q.id)
        self.approved.add(proposal["target"])
        if proposal["members"]:
            app.merge_requirements(q.id, by)               # 只有一张候选单时不合并，由接单以 accept 关闭机会汇聚
        return self._log(q.family, q.object_id, "merge" if proposal["members"] else "approve", by, q.id,
                         f"{proposal['target']} ← {proposal['members']}")

    def _log(self, family: str, object_id: str, action: str, by: str, question_id: str = "", note: str = "") -> str:
        self.log.append({"at": get_clock().now().isoformat(), "family": family, "object_id": object_id,
                         "action": action, "by": by, "question_id": question_id, "note": note})
        return action
