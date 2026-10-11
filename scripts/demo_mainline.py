"""WP-I2：人的台词经 Api.call 执行；--record / --replay [--until 检查点]。"""
import argparse
import hashlib
import json
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import SimClock, set_clock
from huayan.jue.records import load_records
from huayan.ui.server import Api, T0, dump

MAINLINE = Path("demo/mainline.yaml")
FAMILIES = {"escalate": "escalate_need", "merge": "opportunity", "accept": "accept_requirement",
            "confirm": "confirm_translation", "contribute": "contribution", "market-eval": "market_eval",
            "points": "seal_points", "release": "release", "reuse/adopt": "reuse_product"}


class Mainline:
    def __init__(self, api, script=MAINLINE):
        self.api = api
        self.script = yaml.safe_load(Path(script).read_text(encoding="utf-8"))
        self.sessions, self.requirements, self.sales = {}, {}, {}
        self.transcript, self.signatures = [], []
        self.record_count = self.trace_count = 0

    def log(self, text):
        print(text)
        self.transcript.append(text)

    def call(self, method, path, **params):
        return self.api.call(method, f"/api/{path}", params)

    def requirement(self, alias, viewer="pm:agent"):
        return self.call("GET", "requirement", id=self.requirements[alias], viewer=viewer).requirement

    def view(self, alias):
        return self.call("GET", "session", id=self.sessions[alias], viewer=self.sales[alias])["view"]

    def checkpoints(self):
        return [a["checkpoint"] for step in self.script["steps"] for a in step["actions"] if "checkpoint" in a]

    def diagnostics(self):
        records = load_records(self.api.app.run_dir)
        for record in records[self.record_count:]:
            for d in record.output.decisions:
                probability = "未满足前置条件" if d.p_need is None else f"{d.p_need:.3f}"
                self.log(f"  觉 {d.family} {d.object_id} p_need={probability} "
                         f"scored_by={d.scored_by or record.output.scored_by}")
        self.record_count = len(records)
        path = self.api.app.run_dir / "agent_trace.jsonl"
        rows = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        for line in rows[self.trace_count:]:
            row = json.loads(line)
            self.log(f"  Agent {row['principal']} step={row['step']} tool={row['tool']}: {row['result_summary']}")
        self.trace_count = len(rows)

    def run(self, until=None):
        if until is not None and until not in self.checkpoints():
            raise ValueError(f"未知检查点：{until}")
        try:
            for step in self.script["steps"]:
                self.log(f"\n{step['title']}")
                for action in step["actions"]:
                    (kind, body), = action.items()
                    self.log(f"{kind}: {json.dumps(body, ensure_ascii=False)}")
                    if kind == "checkpoint":
                        if body == until:
                            return
                        continue
                    try:
                        getattr(self, kind)(body)
                    finally:
                        self.diagnostics()
        except Exception as error:
            self.log(f"停止：{type(error).__name__}: {error}")
            raise
        finally:
            root = self.api.app.run_dir
            (root / "transcript_v5.md").write_text("\n".join(self.transcript), encoding="utf-8")
            (root / "signatures.json").write_text(json.dumps(self.signatures, ensure_ascii=False, indent=2), encoding="utf-8")

    def start(self, body):
        alias = body["session"]
        session = self.call("POST", "sessions", customer_id=body["customer"], sales_id=body["sales"])
        self.sessions[alias], self.sales[alias] = session.id, body["sales"]

    def customer(self, body):
        self.call("POST", "turn", session_id=self.sessions[body["session"]], speaker="customer", text=body["text"])

    def send(self, body):
        text = body["text"] if "text" in body else self.view(body["session"]).reply_draft
        if not text.strip():
            raise ValueError("回复草稿为空，不能代替助手编写客户回复")
        self.call("POST", "turn", session_id=self.sessions[body["session"]], speaker="sales", text=text)

    def chat(self, body):
        focus = body.get("focus", body.get("session"))
        if focus:
            alias, separator, rest = focus.partition("/")
            focus = {**self.sessions, **self.requirements}[alias] + separator + rest
        self.call("POST", "agents/chat", actor=body["actor"], text=body["text"], focus=focus,
                  session_id=self.sessions[body["session"]] if "session" in body else None)

    def sign(self, body):
        action, actor, args = body["action"], body["actor"], body["args"]
        params, oid = {"by": actor}, None
        if "session" in args:
            params["session_id"] = self.sessions[args["session"]]
            oid = f"session:{params['session_id']}"
        if "req" in args:
            params["req_id"] = self.requirements[args["req"]]
            oid = f"requirement:{params['req_id']}"
        family = FAMILIES[action]
        questions = [q for q in self.call("GET", "questions", viewer=actor)
                     if q.family == family and (oid is None or q.object_id == oid)]
        if len(questions) != 1 or questions[0].status != "open" or questions[0].prepared_at is None or questions[0].signer_id != actor:
            raise ValueError(f"不能签字：{family} {oid} 签字人={actor}；需要唯一 open 且已准备的问题；"
                             f"当前问题={json.dumps(dump(questions), ensure_ascii=False)}")
        question = questions[0]
        if action == "merge":
            params["question_id"] = question.id
        elif action == "contribute":
            req = self.requirement(args["req"], actor)
            if not req.contribution_drafts:
                raise ValueError("沉淀草稿为空")
            draft = req.contribution_drafts[0]
            params.update(item_index=draft.item_index, scene_phrase=draft.scene_phrase, chem_term=draft.chem_term)
        elif action == "points":
            draft = self.requirement(args["req"], actor).points_draft
            if draft is None:
                raise ValueError("封存 / 放出草稿为空")
            params.update(text=draft.public, sealed=draft.sealed)
        elif action == "market-eval":
            params.update(result=args["result"], note=args["note"])
        self.log(f"  签字 {actor}: {family} {question.object_id}，准备于 {question.prepared_at.isoformat()}")
        result = self.call("POST", action, **params)
        if "as" in body:
            self.requirements[body["as"]] = result.id
        target = params.get("req_id") or params.get("session_id") or result.id
        timeline = self.call("GET", "timeline", target_id=target, viewer=actor)
        node = next(n for n in timeline.nodes if n.question_id == question.id)
        self.signatures.append(dump(node))

    def edit(self, body):
        args, actor = body["args"], body["actor"]
        req = self.requirement(args["req"], actor)
        if body["path"] == "req-item":
            index = next(i for i, item in enumerate(req.chem_lang) if args["contains"] in item.text)
            item = req.chem_lang[index].model_copy(update={"text": req.chem_lang[index].text + args["append"]})
            self.call("POST", "req-item", req_id=req.id, index=index, item=dump(item), by=actor)
        elif body["path"] == "reuse-note":
            old, new = args["replace"]
            if old not in req.reuse.customer_note:
                raise ValueError(f"复用说明中没有待替换文字：{old}")
            self.call("POST", "reuse-note", req_id=req.id, text=req.reuse.customer_note.replace(old, new), by=actor)
        else:
            raise ValueError(f"未知编辑接口：{body['path']}")

    def trial(self, body):
        req = self.requirement(body["req"])
        self.call("POST", "trial", req_id=req.id, result="pass" if body["passed"] else "fail", by=req.assigned_rd)

    def approve(self, body):
        actions = [a for a in self.call("GET", "agents/pending", actor=body["actor"]) if a.tool == body["tool"]]
        if len(actions) != 1:
            raise ValueError("需要唯一的待确认动作")
        action = self.call("POST", "agents/approve", action_id=actions[0].id, by=body["actor"])
        if not action.result.ok:
            raise ValueError(action.result.error)

    def expect(self, body):
        for kind, args in body.items():
            if kind == "hints":
                actual, expected = {h.slot for h in self.view(args["session"]).hints}, set(args["slots"])
            elif kind == "recommend":
                card = self.view(args["session"]).card
                actual, expected = card.product_id if card else None, args["product"]
            elif kind in {"inbox", "preparing"}:
                qs = self.call("GET", "questions", viewer=args["actor"])
                actual = {q.family for q in qs if q.signer_id == args["actor"] and
                          (q.prepared_at is not None) == (kind == "inbox")}
                expected = set(args["families"])
                if kind == "preparing":
                    actual = actual & expected
            elif kind == "reply":
                actual, expected = args["contains"] in self.view(args["session"]).reply_draft, True
            elif kind == "status":
                actual, expected = self.requirement(args["req"]).status, args["status"]
            else:
                raise ValueError(f"未知断言：{kind}")
            if actual != expected:
                raise AssertionError(f"{kind}: 预期 {expected}，实际 {actual}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", action="store_true")
    mode.add_argument("--replay", action="store_true")
    parser.add_argument("--until")
    args = parser.parse_args()
    script_hash = hashlib.sha256(MAINLINE.read_bytes()).hexdigest()
    baseline_path = Path("runs/demo_record/record_v5.json")
    baseline = None
    if args.replay:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline["script_sha256"] != script_hash or baseline["until"] != args.until:
            raise ValueError("录制台词或停止点不一致，请使用同一台词和 --until 重录后回放")
    config = yaml.safe_load(Path("config/app.demo.yaml").read_text(encoding="utf-8"))
    config["replay"] = args.replay
    work = Path(config["run_root"]) / "demo_v5"
    work.mkdir(parents=True, exist_ok=True)
    config_path = work / ("replay.yaml" if args.replay else "record.yaml")
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    set_clock(SimClock(T0))
    app = HuayanApp.build(str(config_path))
    runner = Mainline(Api(app, str(config_path)))
    try:
        runner.run(args.until)
        events = [e.model_dump(mode="json", exclude={"id"}) for e in app.events.query()]
        if args.replay:
            if events != baseline["events"]:
                raise AssertionError(f"回放事件与录制不一致，查看 {app.run_dir}")
            print("回放与录制事件一致（忽略事件 id）。")
        else:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(json.dumps({"run_id": app.run_id, "run_dir": str(app.run_dir),
                "script_sha256": script_hash, "until": args.until, "events": events}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"完成：{app.run_dir}；停止点：{args.until or '完整主线与支线'}")
    finally:
        app.system1.close()
        set_clock(None)


if __name__ == "__main__":
    main()
