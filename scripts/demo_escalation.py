"""WP-A3 离线门面验收；需要先集成 B 线 WP-T，不使用转译替身。"""
import argparse

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import ReqItem, Trial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/app.yaml")
    args = parser.parse_args()
    try:
        from huayan.escalation import translate
    except ImportError as exc:
        raise SystemExit("缺少 B 线 WP-T（huayan.escalation.translate），请集成后运行完整验收。") from exc
    app = HuayanApp.build(args.config)
    session = app.start_session("customer:C01", "sales:S01")
    session = app.add_turn(session.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    if session.status != "escalated":
        raise RuntimeError("种子不满足升级主线：锦纶氨纶 + 气流缸色花")
    req = app.draft_requirement(session.recommendation.escalated_question_id, "pm:P01")
    print("L2", req.model_dump_json(indent=2))
    app.set_direction(req.id, req.direction + "；不能影响色光", "pm:P01")
    app.confirm_requirement(req.id, "pm:P01")
    req = app.translate_requirement(req.id, "rd:R02")
    item = req.chem_lang[0]
    app.edit_req_item(req.id, 0, ReqItem(text=item.text + "；需验证低浴比稳定性",
        quote_refs=item.quote_refs, ku_refs=item.ku_refs), "rd:R02")
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）在低浴比条件下控制局部急染", "rd:R02")
    req = app.confirm_translation(req.id, "rd:R02")
    print("L3", app.requirement_view(req.id, "rd:R02").model_dump_json(indent=2))
    app.record_trial(Trial(id="trial:1", product_id=req.product_id, requirement_id=req.id, rd="rd:R02",
        conditions=req.known_slots, result="pass", cause="none", note="模拟试样通过", at=get_clock().now()))
    app.set_public_points(req.id, "（模拟）低浴比下改善匀染、降低氨纶沾色；使用前按工艺试样确认。", "rd:R02")
    print("包装", app.package_sheet(req.id, "pm:P01").model_dump_json())
    product = app.release_product(req.id, "pm:P01")
    other = app.start_session("customer:C02", "sales:S01")
    other = app.add_turn(other.id, "customer", "深一块浅一块，锦纶氨纶的，气流缸")
    assert other.recommendation.product_id == product.id
    print("回流命中", product.id)
    print("积分", app.ledger.totals())


if __name__ == "__main__":
    main()
