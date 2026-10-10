"""WP-E 业务周运行器：按剧本驱动真实链路（门面），每 2 个业务小时做一次定时发现。
抽取为规则、Jev 为桩、转译为规则模式（零成本）。运行器扮演客户所以读需求卡；注入清单只在 eval/metrics.py 里读。"""
import json
import random
import shutil
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, get_clock, set_clock
from huayan.contracts import Event, NeedCard, Trial, WeekItem
from huayan.events import EventLog
from huayan.jue.proto import JueProto, load_templates
from huayan.sim import SimCustomer, to_jsonl
from huayan.sim.week_events import TICK_HOURS

RULE_ALERT = "config/baselines/rule_alert"
PM, RD = "pm:P01", "rd:R02"
HANDLE_DELAY, RELEASE_DELAY = timedelta(hours=2), timedelta(days=1)


def run_week(week_dir: str | Path, policy: str, discoverer: str, run_root: str = "runs", seed: int = 0) -> Path:
    """policy ∈ {handle, ignore}；discoverer ∈ {jue_proto, rule_alert, jue_k}。返回运行目录。"""
    week_dir = Path(week_dir)
    items = [WeekItem.model_validate_json(l) for l in (week_dir / "script.jsonl").read_text(encoding="utf-8").splitlines()]
    cards = {c.id: c for c in (NeedCard.model_validate_json(l)
                               for l in (week_dir / "cards.jsonl").read_text(encoding="utf-8").splitlines())}
    start = datetime.combine(items[0].at.date(), time(9), tzinfo=items[0].at.tzinfo)
    clock = SimClock(start)
    set_clock(clock)
    app = _build(run_root, f"week-{week_dir.name}-{discoverer}-{policy}", discoverer)

    days = (items[-1].at.date() - start.date()).days + 1
    scans = [datetime.combine(start.date() + timedelta(days=d), time(h), tzinfo=start.tzinfo)
             for d in range(days) for h in TICK_HOURS]
    timeline = sorted([(it.at, 1, it) for it in items] + [(at, 0, None) for at in scans], key=lambda x: (x[0], x[1]))
    pending: list[tuple[datetime, str, str]] = []          # (到期时刻, 动作, 问题 / 需求单 id)
    log = []
    for at, _, item in timeline:
        for due, action, ref in sorted(p for p in pending if p[0] <= at):
            pending.remove((due, action, ref))
            clock.advance_to(max(due, clock.now()))
            log.append(_handle(app, action, ref, pending))
        clock.advance_to(at)
        if item is None:
            for q in app.scan(at):
                log.append({"at": at.isoformat(), "action": "found", "question_id": q.id, "family": q.family,
                            "object_id": q.object_id})
                if policy == "handle" and q.family == "opportunity":
                    pending.append((at + HANDLE_DELAY, "approve", q.id))
        elif item.kind == "session":
            _session(app, cards[item.card_id], item.actor, random.Random(f"{seed}:{item.card_id}"))
        elif item.kind == "trial":
            app.record_trial(item.trial)
        else:
            app.kb.search(item.text, app.actors[item.actor])        # 以该业务员身份提问
    (app.run_dir / "week_log.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in log),
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


def _build(run_root: str, run_id: str, discoverer: str) -> HuayanApp:
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(extractor="rule", system1_impl="mock", gateway_mock=True, run_root=run_root,
                  scheduled_model="jue_k" if discoverer == "jue_k" else "jue_proto")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, allow_unicode=True)
    run_dir = Path(run_root) / run_id
    shutil.rmtree(run_dir, ignore_errors=True)             # 同名运行目录重跑时覆盖
    app = HuayanApp.build(stream.name, run_id)
    if discoverer == "rule_alert":                         # 常见告警规则：同一主题升级 ≥ 3 次
        app.jue_scheduled = JueProto(RULE_ALERT, app.system1, "scheduled", app.meter)
        app.jue_scheduled.name = "rule_alert"
        app.templates = load_templates(RULE_ALERT)
    return app


def _session(app: HuayanApp, card: NeedCard, sales: str, rng: random.Random) -> None:
    """模拟客户开场 → 按觉的提示追问 → 直到推荐或升级（最多 8 轮）；没有提示仍未推荐时 recommend_now。"""
    customer = SimCustomer(card, app.seeds, rng)
    sid = app.start_session(card.customer_id, sales).id
    s = app.add_turn(sid, "customer", customer.opening())
    for _ in range(8):
        if s.status != "open" or not s.hints:
            break
        ask = s.hints[0].ask_text
        app.add_turn(sid, "sales", ask)
        s = app.add_turn(sid, "customer", customer.reply(ask))
    if s.status == "open":
        app.recommend_now(sid)


def _handle(app: HuayanApp, action: str, ref: str, pending: list) -> dict:
    """机会汇聚处置：立项 → L2 确认 → L3 确认；1 个业务日后试样、对外要点、包装并发布研发中产品。"""
    now = get_clock().now()
    if action == "approve":
        app.resolve(ref, "approve_project", PM)
        req = [r for r in app.requirements(PM) if r.question_id == ref][-1]
        app.confirm_requirement(req.id, PM)
        app.translate_requirement(req.id, RD)
        try:
            req = app.confirm_translation(req.id, RD)
        except ValueError as exc:                          # 该主题没有研发中产品：立项后停在 L3
            return {"at": now.isoformat(), "action": "approve", "question_id": ref, "requirement_id": req.id,
                    "product_id": None, "note": str(exc)}
        pending.append((now + RELEASE_DELAY, "release", req.id))
        return {"at": now.isoformat(), "action": "approve", "question_id": ref, "requirement_id": req.id,
                "product_id": req.product_id}
    req = app.requirement_view(ref, RD).requirement
    app.record_trial(Trial(id=f"trial:{req.id}", product_id=req.product_id, requirement_id=req.id, rd=RD,
                           conditions=req.known_slots, result="pass", cause="none", at=now))
    app.set_public_points(req.id, "（模拟）按需求单条件试样通过；按推荐用量使用。", RD)
    app.package_sheet(req.id, PM)
    product = app.release_product(req.id, PM)
    return {"at": now.isoformat(), "action": "release", "requirement_id": req.id, "product_id": product.id}
