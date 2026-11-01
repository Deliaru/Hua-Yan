"""真实模型准备真实报告；需求为隔离开发者演练，不代表JianChao Xi本人操作。

不确认结论、不授予、不批准范围、不发布。所有业务写入均经HuayanApp。
uv run --env-file .env python scripts/run_online_preparation.py
"""
import argparse
import json
import shutil
from pathlib import Path
from uuid import uuid4

import yaml

from huayan.app import HuayanApp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/app.online.yaml")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    setup = Path("data/knowledge_v10/online") / f"preparation-input-{uuid4().hex[:8]}"
    shutil.copytree(config["seeds_dir"], setup / "seeds")
    # 本次只准备真实TF-213HE；不让历史演示HY产品和虚构案例冒充本单的现成方案。
    for name in ("products", "cases", "translations", "public"):
        path = setup / "seeds" / f"{name}.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["items"] = [p for p in doc["items"] if p["id"] == "TF-213HE"] if name == "products" else []
        path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    config["seeds_dir"] = str(setup / "seeds")
    config_path = setup / "app.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    app = HuayanApp.build(str(config_path), run_id=args.run_id)
    trace = app.run_dir / "gateway-trace.jsonl"
    def tracing(event, **fields):
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n")
        if event in {"llm", "s1"}:
            print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)
    app.gateway.trace = app.system1.trace = tracing
    rd = "rd:JianChaoXi"
    actors = app.actors
    # 隔离演练只选这位来源归属研发接收合成需求；不改原实例编制或来源归属。
    app.actors = {k: a for k, a in actors.items() if a.role != "rd" or k == rd}
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "（开发者合成需求）涤纶在经轴染色机上深一块浅一块，实际温度75℃。需要核对TF-213HE的操作和升温条件。")
    app.save_escalate_note(session.id, "开发者隔离在线准备：对照SRC-3a2130604c及TF-213HE资料，条件差异和未知交研发，不推定适用。", "sales:S01")
    for q in app.bus.list(family="escalate_need"):
        if q.refs["session_id"] == session.id:
            app.mark_prepared(q.id, q.owner_id)
    req = app.escalate(session.id, "sales:S01")
    app.actors = actors
    prepared = []
    for family in ("reuse_product", "accept_requirement"):
        questions = [q for q in app.bus.list(family=family) if q.refs.get("requirement_id") == req.id]
        if not questions:
            raise ValueError(f"本单尚未提出{family}，请查看实际模型输出及需求缺口：{app.run_dir}")
        app.agents.dispatch(only={q.id for q in questions})
        for q in questions:
            gap = app.preparation_gap(q.id)
            prepared.append({"question_id": q.id, "family": family, "gap": gap})
            if gap:
                raise ValueError(gap)
    app.agents.chat(rd, f"这是隔离在线演练。请为{req.id}做定向资料准备：先get_requirement和关联get_session；"
        "按编号read_source读取SRC-3a2130604c，read_trial_record读取同报告A/B记录，"
        "read_source_image回看该报告table-3第2页原生区域。"
        "对照本单实际温度和报告条件，从TrialRecord的evidence[].fragment逐字复制table-2、table-3依据指针；"
        "evidence是doc_id#span@fingerprint字符串数组，不能填原文或摘要。"
        "用save_source_preparation保存回原单，claim_ids=[]，pending保留组别、阶段、单位、"
        "未读清和条件差异。只保存准备草稿，不编译、不确认、不授予，不推定适用范围。", focus=req.id)
    preparation = app.source_preparation(req.id, rd)
    steps = [s.model_dump(mode="json") for s in app.agents._steps]
    metering = [json.loads(line) for line in app.meter.path.read_text(encoding="utf-8").splitlines()]
    summary = {"data_kind": "real_models_and_report_with_synthetic_request_no_signature",
        "run_dir": str(app.run_dir), "requirement_id": req.id,
        "professional_confirmations": len(app.events.query(["claim_confirmed"])),
        "grants": len(app.events.query(["capability_granted"])),
        "acceptances": len(app.events.query(["requirement_accepted"])), "real_human_signatures": 0,
        "prepared": prepared,
        "preparation": preparation, "steps": steps, "failures": app.agents.failures,
        "jue_llm_calls": sum(r["kind"] == "llm" and r["caller"].startswith("jue:") for r in metering)}
    (app.run_dir / "online-preparation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert all(not q["gap"] for q in prepared) and preparation is not None and preparation["evidence"]
    used = {s["tool"] for s in steps}
    assert {"read_source", "read_trial_record", "read_source_image", "save_source_preparation"} <= used
    assert not summary["jue_llm_calls"]
    print(app.run_dir / "online-preparation.json")
    app.system1.close()


if __name__ == "__main__":
    main()
