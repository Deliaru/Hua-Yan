"""WP-C 离线门面验证：真实觉发现、Hub 起草、模拟人逐步签字；不替代 WP-I2 演示脚本。"""
import argparse
import json

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import Trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/app.yaml")
    args = parser.parse_args()
    app = HuayanApp.build(args.config)
    if not app.config["gateway_mock"]:
        raise ValueError("本脚本只用于离线门面验证；真实助手请使用 agent_cli.py")

    def ready(family, object_id, signer):
        app.tick()
        q = next(q for q in app.bus.list(family=family) if q.object_id == object_id)
        assert q.status == "open" and q.prepared_at is not None and q.signer_id == signer
        print(f"待签 {q.id} {family}，签字人 {signer}")

    text = "深一块浅一块，锦纶氨纶的，气流缸，不要APEO，pH五左右"
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", text)
    ready("escalate_need", f"session:{session.id}", "sales:S01")
    app.save_escalate_note(session.id, "（模拟）气流缸色花，现有说明书无适用产品", "sales:S01")
    req = app.escalate(session.id, "sales:S01")
    rd, oid = req.assigned_rd, f"requirement:{req.id}"
    ready("accept_requirement", oid, rd)
    print("L2", app.requirement_view(req.id, rd).requirement.product_lang)
    app.accept_requirement(req.id, rd)
    ready("confirm_translation", oid, rd)
    req = app.requirement_view(req.id, rd).requirement
    item = req.chem_lang[0]
    app.edit_req_item(req.id, 0, item.model_copy(update={"text": item.text + "；需验证低浴比稳定性"}), rd)
    ready("contribution", oid, rd)
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）在低浴比条件下控制局部急染", rd)
    ready("confirm_translation", oid, rd)
    req = app.confirm_translation(req.id, rd)
    print("L3", app.requirement_view(req.id, rd).model_dump_json(indent=2))
    app.record_trial(Trial(id="trial:1", product_id=req.product_id, requirement_id=req.id, rd=rd,
        conditions=req.known_slots, result="pass", cause="none", note="模拟试样通过", at=get_clock().now()))
    ready("market_eval", oid, "sales:S01")
    app.record_market_eval(req.id, "pass", "（模拟）客户试用通过", "sales:S01")
    ready("seal_points", oid, rd)
    app.set_public_points(req.id, "（模拟）改善低浴比匀染；使用前按工艺试样确认。", [], rd)
    ready("release", oid, rd)
    product = app.release_product(req.id, rd)
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", text)
    assert other.recommendation.product_id == product.id
    assert not app.events.query(["human_decision"])
    summary = {"mode": "离线规则骨架、模拟人签字", "product_id": product.id,
               "requirement_id": req.id, "prepared_families": sorted({e.payload["family"]
                   for e in app.events.query(["question_prepared"])}), "ledger": app.ledger.totals()}
    (app.run_dir / "escalation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("回流命中", product.id)
    print("运行证据", app.run_dir)


if __name__ == "__main__":
    main()
