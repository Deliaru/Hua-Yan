"""和某个人的角色助手对话（契约 ⑭）。助手需要大模型：本脚本总是以 gateway_mock=false 构建应用（密钥取自环境变量）。

uv run python scripts/agent_cli.py --actor pm:P01 [--session sess:1] [--prelude]
  --prelude：先用规则抽取放两段会升级的客户对话（sess:1 C02、sess:2 C03，锦纶氨纶 + 气流缸 + 色花），供产品经理处理。
命令：/pending 待确认动作  /approve act:1  /reject act:1 [理由]  /trace 本对话轨迹  /dispatch 把总线上的新问题派给助手
      /as rd:R02 [sess:1] 切换到另一个人  /quit 退出（打印本次 agent:* 的计量）
"""
import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

from huayan.agent import AgentHub
from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied

PRELUDE = [("customer:C02", "sales:S01", ["我们染完以后布面深一块浅一块，客户老投诉", "锦氨弹力布", "气流缸，浴比很低"]),
           ("customer:C03", "sales:S02", ["锦氨布在气流机里染，颜色不匀，回修了好几次", "没什么环保要求"])]


def build(config_path: str, run_id: str | None) -> HuayanApp:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    config["gateway_mock"] = False
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as stream:
        yaml.safe_dump(config, stream, allow_unicode=True)
    return HuayanApp.build(stream.name, run_id)


def sizes(hub: AgentHub, app: HuayanApp) -> dict[str, int]:
    return {c.id: len(c.messages) for actor in app.actors for c in hub.conversations(actor)}


def show_new(hub: AgentHub, app: HuayanApp, before: dict[str, int], current: str) -> None:
    """打印本次操作后所有对话里新增的消息（含派给别人的单）与本对话的工具轨迹。"""
    for actor in app.actors:
        for conv in hub.conversations(actor):
            new = conv.messages[before.get(conv.id, 0):]
            if not new:
                continue
            if conv.id != current:
                print(f"── 派单到 {conv.id}（/as {conv.principal}{' ' + conv.session_id if conv.session_id else ''} 查看）")
            steps = [s for s in hub.trace(conv.id) if s.at >= new[0].at and s.tool]
            for k, m in enumerate(new):
                if k == 1:
                    for step in steps:
                        blocked = f"  越权：{step.blocked}" if step.blocked else ""
                        print(f"   · {step.tool}({json.dumps(step.args, ensure_ascii=False)}){blocked}")
                cards = "".join(f"\n   [确认卡 {a.id}] {a.summary}" for a in hub.pending(conv.principal)
                                if a.id in m.pending_action_ids)
                print(f"[{m.role}] {m.text}{cards}")


def metering(app: HuayanApp) -> None:
    path = app.run_dir / "metering.jsonl"
    totals = defaultdict(lambda: [0, 0, 0, 0.0])
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        r = json.loads(line)
        if r["caller"].startswith("agent:"):
            t = totals[r["caller"]]
            t[0] += 1; t[1] += r["input_tokens"]; t[2] += r["output_tokens"]; t[3] += r.get("cost") or 0.0
    for caller, (n, i, o, cost) in sorted(totals.items()):
        print(f"{caller}: {n} 步，输入 {i} / 输出 {o} tokens，费用 {cost:.4f}")
    print(f"运行目录 {app.run_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", required=True)
    ap.add_argument("--session")
    ap.add_argument("--prelude", action="store_true")
    ap.add_argument("--config", default="config/app.yaml")
    ap.add_argument("--run-id")
    args = ap.parse_args()
    app = build(args.config, args.run_id)
    hub = AgentHub(app)                       # WP-I 在 HuayanApp.build 挂上 app.agents 后改用它
    if args.prelude:
        for customer, sales, turns in PRELUDE:
            session = app.start_session(customer, sales)
            for text in turns:
                session = app.add_turn(session.id, "customer", text)
            print(f"{session.id}（{customer}）{session.status}，问题 {session.recommendation.escalated_question_id}")
    actor, session = args.actor, args.session
    print(f"和 {actor} 的助手对话（{app.actors[actor].name}）；/quit 退出")
    while True:
        try:
            text = input(f"{actor}> ").strip()
        except EOFError:
            break
        if not text:
            continue
        current, before = f"conv:{actor}:{session or 'inbox'}", sizes(hub, app)
        command, *rest = text.split(maxsplit=1)
        if command == "/quit":
            break
        try:
            handle(hub, app, actor, session, current, command, rest, text)
        except (KeyError, ValueError, PermissionDenied) as exc:      # 命令行输入的 id 写错、或不是委托人
            print(f"！{exc}")
            continue
        if command == "/as":
            actor, *maybe = rest[0].split()
            session = maybe[0] if maybe else None
            continue
        show_new(hub, app, before, current)
    metering(app)


def handle(hub, app, actor, session, current, command, rest, text):
    if command == "/pending":
        for a in hub.pending(actor):
            print(f"[确认卡 {a.id}] {a.summary}  （{a.tool} {a.args}）")
    elif command == "/approve":
        a = hub.approve(rest[0], actor)
        print(f"{a.id} 已确认：{'成功' if a.result.ok else a.result.error}")
    elif command == "/reject":
        action_id, *note = rest[0].split(maxsplit=1)
        hub.reject(action_id, actor, note[0] if note else "")
    elif command == "/trace":
        for s in hub.trace(current):
            print(f"{s.step} {s.tool or '回复'} {json.dumps(s.args, ensure_ascii=False)} → {s.result_summary}"
                  f"{'  越权：' + str(s.blocked) if s.blocked else ''}{'  ' + s.pending_action_id if s.pending_action_id else ''}")
    elif command == "/dispatch":
        hub.dispatch()
    elif command == "/as":
        target = rest[0].split()[0]
        print(f"切换到 {target}（{app.actors[target].name}）")
    else:
        hub.chat(actor, text, session)


if __name__ == "__main__":
    main()
