"""演示主线（WP-I）：按 demo/mainline.yaml 的台词跑完 6 步。

uv run python scripts/demo_mainline.py            离线：规则抽取、Mock Jev、规则骨架；台词里的工具直接经 AgentHub 调用
uv run python scripts/demo_mainline.py --jue-k    离线，实时与定时觉都换成 Jue-K
uv run python scripts/demo_mainline.py --live     现场：人的话交给各自的角色助手（gateway_mock=false），缓存写入 runs/demo_record/llm_cache/
确认步骤由脚本代替委托人调用 agents.approve，并打印确认卡。run_offline(app) 供界面离线模式在同一进程内复用。
"""
import argparse
import json
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, set_clock
from huayan.contracts import SHANGHAI

MAINLINE = Path("demo/mainline.yaml")
LANG = {"pm": "product_lang", "rd": "chem_lang"}
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=SHANGHAI)


class Mainline:
    def __init__(self, app: HuayanApp, live: bool):
        self.app, self.live = app, live
        self.script = yaml.safe_load(MAINLINE.read_text(encoding="utf-8"))
        self.sessions: dict[str, str] = {}

    def run(self) -> None:
        for step in self.script["steps"]:
            print(f"\n══════ {step['title']}")
            for action in step["actions"]:
                (kind, body), = action.items()
                getattr(self, kind)(body)
            self.app.tick()

    # ---- 动作 ----

    def relay(self, body: dict) -> None:
        sid = self.session(body["session"])
        if self.live:
            self.chat(self._sales(sid), f"客户说：{body['text']}", sid)
            return
        s = self.app.add_turn(sid, "customer", body["text"])
        rec = s.recommendation
        print(f"[客户 {s.customer_id} @ {sid}] {body['text']}")
        print(f"   槽位 {s.need.known()}  追问提示 {[h.ask_text for h in s.hints]}  状态 {s.status}"
              f"{'  推荐 ' + rec.product_id if rec and rec.product_id else ''}"
              f"{'  升级 ' + rec.escalated_question_id if rec and rec.escalated_question_id else ''}")

    def say(self, body: dict) -> None:
        sid = self.session(body["session"]) if "session" in body else None
        if self.live:
            self.chat(body["actor"], body["text"], sid)
            return
        print(f"[{body['actor']}] {body['text']}")
        self.assistant(body)

    def assistant(self, body: dict) -> None:
        if self.live:                         # 现场：助手在收到派单 / 通知时已自己处理
            return
        sid = self.session(body["session"]) if "session" in body else None
        ctx = self.app.agents.context(body["actor"], sid)
        for op in body["offline"]:
            args = {k: self.resolve(v) for k, v in op.items() if k not in ("tool", "expect_denied")}
            if "append" in args:              # 在原条目后追加：保留原话与依据
                old = getattr(self.app.requirement_view(args["req_id"], body["actor"]).requirement,
                              LANG[ctx.principal.role])[args["index"]]
                args = {"req_id": args["req_id"], "index": args["index"], "text": old.text + args.pop("append"),
                        "quote_refs": old.quote_refs, "ku_refs": old.ku_refs}
            result = self.app.agents.call_tool(ctx, op["tool"], args)
            if result.ok == op.get("expect_denied", False):
                raise RuntimeError(f"{op['tool']} 结果不符合台词：{result.error or result.data}")
            shown = f"被拒绝：{result.error}" if not result.ok else \
                f"确认卡 {result.pending_action_id}：{result.data['summary']}" if result.pending_action_id \
                else json.dumps(result.data, ensure_ascii=False)[:200]
            print(f"   · {op['tool']}({json.dumps(args, ensure_ascii=False)}) → {shown}")

    def approve(self, body: dict) -> None:
        cards = [a for a in self.app.agents.pending(body["by"]) if a.tool == body["tool"]]
        if not cards:
            raise RuntimeError(f"{body['by']} 没有 {body['tool']} 的待确认动作")
        before = self.sizes()
        action = self.app.agents.approve(cards[-1].id, body["by"])
        outcome = "已执行" if action.result.ok else f"执行失败：{action.result.error}"
        print(f"   ✔ [确认卡 {action.id}] {body['by']} 确认：{action.summary} → {outcome}（脚本代替委托人）")
        if not action.result.ok:
            raise RuntimeError(action.result.error)
        self.print_new(before)

    def tick(self, _) -> None:
        before = self.sizes()
        found = self.app.tick()
        print(f"   ⟳ tick：觉发现 {[f'{q.id} {q.family}：{q.title}' for q in found] or '无新问题'}")
        for q in found:
            print(f"     {q.id} 派给 {q.owner_id or q.owner_role}  p={q.p_need:.2f}  证据：{'；'.join(e.summary for e in q.evidence)}")
        self.print_new(before)

    def show(self, body: dict) -> None:
        (what, arg), = body.items()
        getattr(self, f"show_{what}")(arg)

    # ---- 展示 ----

    def show_cards(self, alias: str) -> None:
        sid = self.session(alias)
        for viewer in (self._sales(sid), "rd:R01"):
            card = self.app.view_session(sid, viewer).card
            print(f"   ▣ {viewer} 看到的卡片（{card.product_id}，{card.version}）")
            for s in card.sections:
                print(f"       [L{s.level} {s.title}] {s.text}")

    def show_layers(self, _) -> None:
        req_id = self.resolve("$req")
        rd = self.app.requirement_view(req_id, "rd:R01")
        req, quotes = rd.requirement, rd.quotes
        print(f"   ▣ 需求单 {req.id}（{req.status}，产品 {req.product_id}）  起草 {req.drafted_by} · 确认 {req.pm_confirmed_by}"
              f" · 化学起草 {req.chem_drafted_by} · 化学确认 {req.rd_confirmed_by}")
        print("   L1 场景需求卡（客户原话）：")
        for sid in req.session_ids:
            view = self.app.view_session(sid, self._sales(sid))
            print(f"       {sid}：" + "；".join(f"{f.slot}={f.value}「{f.quote}」" for f in view.slots))
        for title, viewer, layer in (("L2 产品需求（产品经理视图）", "pm:P01", "product_lang"),
                                     ("L3 化学语言（研发视图）", "rd:R01", "chem_lang")):
            view = self.app.requirement_view(req_id, viewer)
            cited = {c.ku_id: c for c in view.cited}
            print(f"   {title}：")
            for i, item in enumerate(getattr(view.requirement, layer), 1):
                basis = "；".join(f"{cited[r].owner}「{cited[r].title}」" for r in item.ku_refs)
                print(f"       {i}. {item.text}\n          原话 {[quotes[q] for q in item.quote_refs]}  依据 {basis or '无'}")
        l3 = [c for c in self.app.requirement_view(req_id, "pm:P01").cited if c.level == 3]
        owners = Counter(c.owner for c in l3)
        print(f"   产品经理视图里所引 {len(l3)} 条 L3 知识：只显示归属 "
              + "、".join(f"{o} ×{n}" for o, n in sorted(owners.items()))
              + f"，原文可见 {sum(c.text is not None for c in l3)} 条")

    def show_contributions(self, _) -> None:
        print("   ▣ 贡献看板（产品经理视图）")
        for r in sorted(self.app.contributions("pm:P01"), key=lambda r: (r.owner, r.ku_id)):
            print(f"       {r.owner}  {r.title}  被引 {r.n_cited}  积分 {r.points}  用于 {r.used_by}")

    def show_audit(self, actor: str) -> None:
        print(f"   ▣ {actor} 的审计记录")
        for r in self.app.audit.list(actor):
            print(f"       {r.action} {r.object_ids} {r.reason}")

    def show_customer_card(self, alias: str) -> None:
        sid = self.session(alias)
        session = next(s for s in self.app.sessions() if s.id == sid)
        card = self.app.view_session(sid, session.customer_id).card
        print(f"   ▣ 客户 {session.customer_id} 看到的卡片（{card.product_id}，{card.version}）")
        for s in card.sections:
            print(f"       [L{s.level} {s.title}] {s.text}")

    # ---- 工具 ----

    def session(self, alias: str) -> str:
        if alias not in self.sessions:
            customer, sales = self.script["sessions"][alias]
            self.sessions[alias] = self.app.start_session(customer, sales).id
        return self.sessions[alias]

    def _sales(self, sid: str) -> str:
        return next(s.sales_id for s in self.app.sessions() if s.id == sid)

    def resolve(self, value):
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        if value == "$req":
            return [r for r in self.app.requirements("pm:P01") if r.status != "rejected"][-1].id
        if value.startswith("$q:"):
            return [q for q in self.app.bus.list(status=None, family=value[3:])][-1].id
        return self.session(value.removeprefix("$session:"))

    def chat(self, actor: str, text: str, sid: str | None) -> None:
        before = self.sizes()
        print(f"[{actor}{' @ ' + sid if sid else ''}] {text}")
        self.app.agents.chat(actor, text, sid)
        self.print_new(before, skip_first=f"conv:{actor}:{sid or 'inbox'}")

    def sizes(self) -> dict[str, tuple[int, int]]:
        hub = self.app.agents
        return {c.id: (len(c.messages), len(hub.trace(c.id))) for a in self.app.actors for c in hub.conversations(a)}

    def print_new(self, before: dict[str, tuple[int, int]], skip_first: str | None = None) -> None:
        """打印新增的助手消息（含派给别人的单）与工具轨迹。"""
        if not self.live:
            return
        hub = self.app.agents
        for actor in self.app.actors:
            for conv in hub.conversations(actor):
                n_messages, n_steps = before.get(conv.id, (0, 0))
                new = conv.messages[n_messages:]
                if conv.id == skip_first:
                    new = new[1:]             # 第一条是刚才说的话，已打印
                if not new:
                    continue
                print(f"   ── {conv.id}")
                for m in new:
                    if m.role != "assistant":         # 通知、确认结果在前，工具轨迹和助手回复在后
                        print(f"      [{m.role}] {m.text}")
                for step in (s for s in hub.trace(conv.id)[n_steps:] if s.tool):
                    print(f"      · {step.tool}({json.dumps(step.args, ensure_ascii=False)})"
                          f"{'  越权：' + str(step.blocked) if step.blocked else ''}")
                for m in new:
                    if m.role == "assistant":
                        print(f"      [{m.role}] {m.text}")


def run_offline(app: HuayanApp) -> None:
    """离线主线：不设全局时钟、不调用大模型，界面在同一进程内复用。"""
    Mainline(app, live=False).run()


def build(args) -> HuayanApp:
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    if args.jue_k:
        config.update(realtime_model="jue_k", scheduled_model="jue_k")
    if args.live:
        config.update(gateway_mock=False, llm_cache_dir="runs/demo_record/llm_cache")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, allow_unicode=True)
    return HuayanApp.build(stream.name, args.run_id)


def metering(app: HuayanApp) -> None:
    path = app.run_dir / "metering.jsonl"
    totals = defaultdict(lambda: [0, 0, 0, 0.0])
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        r = json.loads(line)
        t = totals[r["caller"]]
        t[0] += 1; t[1] += r["input_tokens"]; t[2] += r["output_tokens"]; t[3] += r.get("cost") or 0.0
    print("\n══════ 计量")
    for caller, (n, i, o, cost) in sorted(totals.items()):
        print(f"{caller}: {n} 次，输入 {i} / 输出 {o} tokens，费用 {cost:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--jue-k", action="store_true")
    ap.add_argument("--config", default="config/app.yaml")
    ap.add_argument("--run-id")
    args = ap.parse_args()
    set_clock(SimClock(T0))                   # 固定业务时间：可复现，现场版的缓存可回放
    app = build(args)
    status = app.status()
    print(f"运行 {app.run_id}：{'现场' if args.live else '离线'}  觉 {status.realtime_model}/{status.scheduled_model}"
          f"  抽取 {status.extractor}  Jev {status.system1_impl}")
    Mainline(app, args.live).run()
    metering(app)
    print(f"运行目录 {app.run_dir}")


if __name__ == "__main__":
    main()
