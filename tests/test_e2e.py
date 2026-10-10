import json
from pathlib import Path

import yaml

from huayan.app import HuayanApp
from huayan.clock import get_clock
from huayan.contracts import KnowledgeUnit, Trial


def test_mainline_offline(tmp_path):
    """演示主线 1～4 步离线跑通（直接调用门面），含第 3 步的一次回问：发布 → 回答 → 回填。"""
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    app = HuayanApp.build(str(path))

    # 1 短路径：觉提示追问 → 推荐
    s1 = app.start_session("customer:C01", "sales:S01").id
    assert {h.slot for h in app.add_turn(s1, "customer", "深一块浅一块").hints} == {"fiber", "equipment"}
    assert app.add_turn(s1, "customer", "锦氨的，溢流缸").recommendation.product_id == "T-205"
    assert all(s.level == 1 for s in app.view_session(s1, "sales:S01").card.sections)
    assert any(s.level == 3 for s in app.view_session(s1, "rd:R01").card.sections)

    # 2 两位客户同类需求无产品可用 → 两次升级 → tick 发现机会汇聚
    s2 = app.start_session("customer:C02", "sales:S01").id
    s3 = app.start_session("customer:C03", "sales:S02").id
    assert app.add_turn(s2, "customer", "深一块浅一块，锦氨的，气流缸").status == "escalated"
    assert app.add_turn(s3, "customer", "尼龙弹力布在气流机里染，深一块浅一块").status == "escalated"
    opportunity = next(q for q in app.tick() if q.family == "opportunity")

    # 3 L2 → L3；L3 转译取决于客户没说的环保要求 → 回问 → 回填
    app.kb.add(KnowledgeUnit(id="ku:translation:tr:e2e", level=3, kind="translation", title="无APEO",
        text="无APEO → （模拟）不得使用烷基酚聚氧乙烯醚类乳化组分", phenomenon_ids=["color_unlevel"],
        owner="rd:R02", created_at=get_clock().now()))
    req = app.draft_requirement(opportunity.id, "pm:P01")
    assert set(req.session_ids) == {s2, s3}
    app.confirm_requirement(req.id, "pm:P01")
    app.translate_requirement(req.id, "rd:R02")
    ask = next(q for q in app.tick() if q.family == "ask_back")
    assert ask.refs["slot"] == "constraint" and ask.refs["requirement_id"] == req.id and ask.owner_role == "sales"
    app.add_turn(ask.refs["session_id"], "sales", "有没有环保方面的要求？")
    app.add_turn(ask.refs["session_id"], "customer", "不要APEO")
    assert app.bus.get(ask.id).resolution.action == "answered"
    assert app.requirement_view(req.id, "rd:R02").requirement.known_slots["constraint"] == "无APEO"
    req = app.translate_requirement(req.id, "rd:R02")
    assert any("ku:translation:tr:e2e" in item.ku_refs for item in req.chem_lang)
    app.contribute_translation(req.id, 0, "低浴比匀染", "（模拟）低浴比缓染稳定性", "rd:R02")
    req = app.confirm_translation(req.id, "rd:R02")
    assert req.product_id == "T-206"

    # 4 回流：试样 → 对外要点 → 反向包装 → 发布 → 同类需求 L1 命中新品
    app.record_trial(Trial(id="trial:e2e", product_id="T-206", requirement_id=req.id, rd="rd:R02",
        conditions=req.known_slots, result="pass", cause="none", at=get_clock().now()))
    app.set_public_points(req.id, "（模拟）低浴比气流缸中匀染性好；按推荐用量使用。", "rd:R02")
    app.package_sheet(req.id, "pm:P01")
    app.release_product(req.id, "pm:P01")
    s4 = app.start_session("customer:C01", "sales:S02").id
    assert app.add_turn(s4, "customer", "锦氨布气流缸里染，深一块浅一块").recommendation.product_id == "T-206"
    owners = {r.owner for r in app.contributions("pm:P01") if req.id in r.used_by}
    assert {"pm:P01", "rd:R01", "rd:R02"} <= owners

    meter = [json.loads(line) for line in (app.run_dir / "metering.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(r["caller"].startswith("jue:") for r in meter)
    assert not any(r["kind"] == "llm" and r["caller"].startswith("jue:") for r in meter)
