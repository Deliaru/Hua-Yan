"""REPLAN-v8 Q9.3：用企业编制跑一个模拟日（大模型版），记下调用数、耗时与用量；同种子第二次运行走录制缓存重放。
人由大模型扮演（sim/humans.py），世界由程序决定。业务钟每 15 分钟一格：这一格里来找的客户（多数先在自助页问化言，
少数直接打给业务员）、到点查看工作台的人、回自助页看看的客户同时进行（业务员通话时不看），助手随时准备觉提出的问题；
人在工作台上签字，也对自己的助手说话、确认它的提议；觉在 11、13、15、17 点定时发现。
第一天 9–18 点有客户来电，第二天不再来电，试样（确认后次日）与积压在这天消化；每天收工时各助手归纳记忆。
并发的先后由 sim/schedule.Gate 记下（schedule.json），重放按同一顺序走，结果与录制逐字一致。
先运行 scripts/make_enterprise.py；密钥取环境变量 TRIAL_API_KEY（set -a; source .env）。

  uv run python scripts/run_sim_day.py [--sessions 40 --seed 0 --replay]
"""
import argparse
import json
import random
import time
from collections import Counter
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import set_clock
from huayan.contracts import SHANGHAI
from huayan.sim.cards import make_card, sample_slots
from huayan.sim.humans import CLOSE, CUSTOMER_EVERY, OPEN, LLMHumans, load_personas
from huayan.sim.schedule import Gate, ThreadClock, gate_gateway
from huayan.sim.week_events import TICK_HOURS

CONFIG = Path("data/enterprise/app.yaml")
DAY = datetime(2026, 10, 19, 9, 0, tzinfo=SHANGHAI)
STEP = timedelta(minutes=15)
DAYS = 2


def response(log):
    """人从问题被提出到处理它隔了多少业务分钟，按角色给中位数与最长。"""
    waits = {}
    for r in log:
        if r["raised_at"]:
            minutes = (datetime.fromisoformat(r["at"]) - datetime.fromisoformat(r["raised_at"])).total_seconds() / 60
            waits.setdefault(r["by"].split(":")[0], []).append(minutes)
    return {role: {"n": len(w), "median": round(sorted(w)[len(w) // 2]), "max": round(max(w))} for role, w in waits.items()}


def drive(log, app):
    """谁在推动工作：人做的每一步是觉推来的还是自己发起的；签字、对助手说、确认助手的提议各多少；觉自动执行多少。"""
    return {"steps": Counter(f"{r['by'].split(':')[0]}|{r['kind']}" for r in log if r["kind"]),
            "pushed_by_jue": sum(bool(r["raised_at"]) and not r["action"].startswith("被拒") for r in log),
            "agent_proposals": len(app.events.query(["agent_action_proposed"])),
            "auto_executed": Counter(e.payload["action"] for e in app.events.query(["auto_executed"]))}


def customer_paths(app):
    """客户从哪里进来、最后落在哪：自助拿到推荐 / 直达研发 / 交业务员 / 没结果离开；直接打给业务员的另计。"""
    def path(s):
        if s.origin == "sales":
            return "直接打给业务员"
        return "交业务员" if s.sales_id else {"recommended": "自助拿到推荐", "escalated": "直达研发"}.get(s.status, "没结果离开")
    return Counter(path(s) for s in app.sessions())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--replay", action="store_true", help="只用录制缓存并按录制的并发顺序走，未命中即报错")
    args = ap.parse_args()

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["replay"] = args.replay
    path = CONFIG.with_name(f"app.day{args.seed}.yaml")
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    clock = ThreadClock(DAY)
    set_clock(clock)
    run_id = f"day-{args.seed}-{'replay' if args.replay else 'record'}"
    app = HuayanApp.build(str(path), run_id)
    record_dir = Path(config["run_root"]) / f"day-{args.seed}-record"
    gate = Gate(json.loads((record_dir / "schedule.json").read_text(encoding="utf-8")) if args.replay else None)
    gate_gateway(app.gateway, gate)
    humans = LLMHumans(app, load_personas())
    rng = random.Random(args.seed)
    customers = sorted(config["customer_sales"])
    sessions = []
    for i in range(args.sessions):
        phen, customer = rng.choice(app.seeds.phenomena), rng.choice(customers)
        card = make_card(f"day:card:{i + 1}", phen, sample_slots(phen, app.seeds, rng), customer, app.seeds, rng)
        sessions.append((DAY + timedelta(minutes=rng.randrange(8 * 60)), card))
    sessions.sort(key=lambda x: (x[0], x[1].id))
    days = [DAY.date() + timedelta(days=d) for d in range(DAYS)]
    scans = {datetime.combine(d, dtime(h), tzinfo=SHANGHAI) for d in days for h in TICK_HOURS}
    people = sorted(a for a in humans.personas if a.split(":")[0] in ("sales", "rd", "pm"))
    look_rng = {a: random.Random(f"{args.seed}:look:{a}") for a in people + customers}
    next_at = {a: humans.next_look(a, DAY - timedelta(minutes=humans.personas[a].get("every", CUSTOMER_EVERY)[1]),
                                   look_rng[a]) for a in people + customers}                # 早上 9 点后陆续打开工作台（客户：自助页）
    tried = set()

    def talk(at, card):
        clock.local(at)
        humans.visit(card, config["customer_sales"][card.customer_id], random.Random(f"{args.seed}:{card.id}"))

    def look(at, actor):
        clock.local(at)
        humans.customer_look(actor) if actor.startswith("customer:") else humans.look(actor)

    started = time.perf_counter()
    memory = {}
    for day in days:
        t = datetime.combine(day, OPEN, tzinfo=SHANGHAI)
        while t.time() < CLOSE:
            clock.advance_to(max(t, clock.now()))
            nxt = t + STEP
            for due, req_id, rd in sorted(humans.trials):  # 确认后次日试样，结果由世界给出
                if due < nxt and (req_id, due) not in tried:
                    tried.add((req_id, due))
                    humans.trial(req_id, rd, due)
            if t in scans:
                app.scan(t)
            humans.prepare(gate.run)
            calls = [(at, c) for at, c in sessions if t <= at < nxt]
            busy = {c.customer_id for _, c in calls} | {config["customer_sales"][c.customer_id] for _, c in calls
                                                       if humans.personas[c.customer_id].get("direct")}
            lookers = [a for a in people + customers if next_at[a] < nxt and a not in busy]
            for a in lookers:
                next_at[a] = humans.next_look(a, max(next_at[a], t), look_rng[a])
            gate.run([(card.id, lambda at=at, card=card: talk(at, card)) for at, card in calls] +
                     [(f"look:{a}:{t:%d%H%M}", lambda a=a: look(t, a)) for a in lookers])
            humans.prepare(gate.run)
            t = nxt
        memory = app.close_day(datetime.combine(day, OPEN, tzinfo=SHANGHAI))   # 收工：各助手归纳当天的记忆
    elapsed = time.perf_counter() - started

    if not args.replay:
        (app.run_dir / "schedule.json").write_text(json.dumps(gate.order), encoding="utf-8")
    (app.run_dir / "sim_log.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in humans.log),
                                               encoding="utf-8")
    meter = [json.loads(l) for l in (app.run_dir / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    llm = [m for m in meter if m.get("kind") == "llm"]
    summary = {"run": run_id, "sessions": args.sessions, "elapsed_s": round(elapsed, 1),
               "llm_calls": Counter(m["caller"] for m in llm),
               "input_tokens": sum(m.get("input_tokens") or 0 for m in llm),
               "output_tokens": sum(m.get("output_tokens") or 0 for m in llm),
               "failed_calls": sum(m.get("ok") is False for m in llm),
               "actions": Counter(r["family"] for r in humans.log),
               "response_minutes": response(humans.log),
               "drive": drive(humans.log, app),
               "customer_paths": customer_paths(app),
               "looks": {r: {"looks": sum(l["by"].startswith(r) for l in humans.looks),
                             "empty": sum(l["by"].startswith(r) and not l["todo"] for l in humans.looks)}
                         for r in ("sales", "rd", "pm", "customer")},
               "backlog": Counter(f"{a}|{q.family}" for a in people for q in humans.todo(a)),
               "asks_per_requirement": Counter(e.payload["requirement_id"] for e in app.events.query(["requirement_returned"])
                                               if e.payload.get("slots")),
               "trials_not_run": sum((r, d) not in tried for d, r, _ in humans.trials),
               "rejected_actions": sum(r["action"].startswith("被拒") for r in humans.log),
               "requirements": Counter(r.status for r in app._requirements.values()),
               "questions": Counter(q.family for q in app.bus.list(status=None)),
               "unprepared_open": Counter(q.family for q in app.bus.list() if q.prepared_at is None and q.signer_role),
               "agent_errors": Counter(f"{e['agent']}|{e['kind']}" for e in app.agents.errors()),
               "memory": {p: len(app.memories(p)) for p in memory}}
    (app.run_dir / "sim_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
