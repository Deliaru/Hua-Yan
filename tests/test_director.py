"""V11.5–V11.7、V11.12：导演在模板模式下送来各岗位的业务与关卡，扮演外部世界与缺席的客户、岗位，只经 Api.call 动作；
有人在玩的身份留给人，路演局里各岗位的事都留给人。导演跑完后检查对象状态与事件（REPLAN-v11 第 6 节）。
专业签字、试样结果均为模拟。"""
from pathlib import Path

import pytest
import yaml

from huayan.knowledge import PermissionDenied
from huayan.sim.director import Director, prepare_round
from huayan.ui import server


def _api(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    api = server.Api(None, str(prepare_round(str(path), tmp_path / "round")))   # 一局的资料副本与待审候选
    api.build()
    return api


def _tick(api):
    return lambda: (api.advance(600), api.tick())


def _route(api, sid):
    return api.call("GET", "/api/route", {"id": sid, "viewer": "supervisor:M01"})


def test_business_all_at_once_then_stage_in_order(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    # 开局：各岗位的业务一起送来，关卡只送第 1 步
    assert [x["id"] for x in director.open()] == ["客户业务 1", "业务员业务 1", "业务员业务 2", "研发业务 1", "研发业务 2", "产品经理业务 1", "关卡第 1 步"]
    director.play_all(_tick(api))
    s = director.state
    assert sorted(s["passed"]) == sorted(x["id"] for x in director.levels)
    case = lambda n: s["cases"][n]
    # 客户业务 1：客户自助拿到推荐，业务员、产品经理、研发都没经过
    one = _route(api, case("客户业务 1")[0])
    assert one["path"] == "自助解决" and all(one["roles"][r]["state"] == "none" for r in ("sales", "pm", "rd"))
    # 业务员业务 1：报价诉求交归属业务员，业务员接手就报价
    assert _route(api, case("业务员业务 1")[0])["path"] == "交业务员"
    assert any(e.kind == "sales_assigned" for e in api.app.events.query() if e.session_id == case("业务员业务 1")[0])
    # 研发业务 1：现有产品不适用，需求直达研发，研发判已有产品适用、不立项
    assert _route(api, case("研发业务 1")[0])["path"] == "研发不立项"
    # 产品经理业务 1：两家同类需求，产品经理签机会，合成一个课题
    assert len(case("产品经理业务 1")) == 2 and {_route(api, sid)["path"] for sid in case("产品经理业务 1")} == {"产品机会"}
    # 导演只经 API 动作：每个代办都是浏览器也走的写接口
    assert {a["path"] for a in s["acted"]} <= set(server.POST)
    assert {(a["actor"], a["path"]) for a in s["acted"]} >= {
        ("sales:S01", "/api/turn"), ("rd:R02", "/api/decline"), ("pm:P01", "/api/merge")}   # 白地沾色指派给刘工


def test_present_roles_are_left_to_people(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    # 有人扮客户 C：导演只开会话不替他说话，把可以说的台词给出来
    director.step({"customer:C03", "rd:R01", "rd:R02"})
    sid = director.state["cases"]["研发业务 1"][0]
    assert not api.app.view_session(sid, "customer:C03").turns
    assert {"customer": "customer:C03", "session_id": sid, "text": "白地被沾色了"} in director.view()["lines"]
    # 人说完两句，研发有人在玩：需求单停在研发待处理，不通关
    for line in ("白地被沾色了", "锦纶的布，尼龙用的那种料，酸性染料，缸里浸染的"):
        api.call("POST", "/api/turn", {"session_id": sid, "speaker": "customer", "text": line, "by": "customer:C03"})
    for _ in range(10):
        if not director.step({"customer:C03", "rd:R01", "rd:R02"}):
            _tick(api)()
    assert "研发业务 1" not in director.state["passed"] and _route(api, sid)["roles"]["rd"]["state"] == "pending"


def test_roadshow_leaves_every_role_its_business(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.state["roadshow"] = True
    for _ in range(20):
        if not director.step(set()):
            _tick(api)()
    s, view = director.state, director.view()
    status = {x["id"]: x["status"] for x in view["levels"]}
    # 业务流程演示一次只送一件：第一件送到客户面，留给人在客户面说，后面的都还没送
    assert not api.app.view_session(s["cases"]["客户业务 1"][0], "customer:C01").turns
    assert list(s["cases"]) == ["客户业务 1"] and status["客户业务 1"] == "open"
    assert all(v == "waiting" for k, v in status.items() if k != "客户业务 1")


def test_stage_follows_report_to_next_order_and_revision(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.play_all(_tick(api))
    s, app = director.state, api.app
    case = lambda n: s["cases"][n][0]
    four, five, six, seven = case("关卡第 1 步"), case("关卡第 2 步"), case("关卡第 3 步"), case("研发业务 2")
    # 关卡第 1 步：研发以报告候选为依据判定已有产品适用，产品经理批准；这条能力给客户层、条件写清、依据是报告结论
    declined = next(e for e in app.events.query(["project_declined"]) if four in e.payload["session_ids"])
    cap = next(c for c in app.kb.capabilities() if c.form == "applicable" and c.audience == 0
               and c.payload["conditions"] == {"fiber": ["锦纶氨纶"], "equipment": ["经轴染色机"]})
    assert declined.actor == "rd:R02" and cap.approved_by == "pm:P01"
    assert all(app.kb._units[u].evidence[0].startswith("RPT-044#") for u in cap.based_on)
    # 关卡第 2 步：同条件的下一单用上这条能力，没有经过研发
    used = [e for e in app.events.query(["capability_used"]) if e.session_id == five]
    suspended = next(e for e in app.events.query(["capability_suspended"]) if e.payload["capability_id"] == cap.id)
    escalated = [e for e in app.events.query(["escalate"]) if e.session_id == five]
    assert cap.id in {e.payload["capability_id"] for e in used} and all(e.ts >= suspended.ts for e in escalated)
    # 关卡第 3 步：纯锦纶不在授予条件里，回到研发，研发不扩范围
    assert _route(api, six)["path"] == "研发不立项"
    # 研发业务 2：染浴 pH 没问到，第一次试样失败；研发退回、客户在自助页答了回问，第二次试样通过
    trials = [e.payload for e in app.events.query(["trial"]) if e.payload["requirement_id"]]
    assert [(t["result"], t["missing_slots"]) for t in trials] == [("fail", ["bath_ph"]), ("pass", [])]
    assert trials[1]["conditions"]["bath_ph"] == "碱性"
    rework = next(r for r in api.call("GET", "/api/old-flow", {"id": seven, "viewer": "supervisor:M01"})["old"]["stations"]
                  if r["station"] == "试样返工一轮")
    assert rework["now_times"] == 1 and rework["times"] < 1      # 这次实测返工一轮，对照旧流程按比例推算的期望
    # 关卡第 4 步：资料改版，依据变了的结论挂起依赖它的能力，研发复核原文后签字保留，能力恢复
    review = next(q for q in app.bus.list(status=None, family="qi_review"))
    assert review.status == "resolved" and review.refs["ku_id"] in cap.based_on
    assert app.kb._caps[cap.id].status == "active"
    assert escalated      # 挂起那一刻用过它的客户改道交研发（撤销后改道），不等复核
    assert {a["path"] for a in s["acted"]} <= set(server.POST)
    # V12.7 关卡第 5 步：这条能力生效后，觉找回早先研发不立项的同条件客户，业务员回访，那段会话按新判断拿到推荐
    old = case("业务员业务 2")
    recall = next(q for q in app.bus.list(status=None, family="capability_recall"))
    assert recall.refs["session_id"] == old and recall.status == "resolved" and recall.scored_by == "rule"
    assert app.view_session(old, "customer:C01").card.product_id == "HY-LV205"
    assert [m["kind"] for m in app.client_messages("customer:C01")] == ["callback"]
    assert not any(q.refs.get("session_id") == six for q in app.bus.list(status=None, family="capability_recall"))   # 纯锦纶不在条件里
    # 关卡第 6 步：研发签出的经轴染色机超出说明书，产品经理签字后补充句接进说明书，客户层看得到
    sheet = next(q for q in app.bus.list(status=None, family="sheet_mismatch"))
    assert sheet.status == "resolved" and "经轴染色机" in sheet.refs["beyond"]
    assert "经轴染色机上染色同样适用" in app.kb._units["ku:sheet:HY-LV205"].text
    # V11.8 CEO 面：逐件路径只给主管；研发业务 2 第一次试样未通过记为绕回
    ceo = api.call("GET", "/api/ceo", {"viewer": "supervisor:CEO"})
    seven = next(c for c in ceo["cases"] if c["session_id"] == seven)
    assert next(x for x in seven["stations"] if x["loop"])["station"] == "试样"
    with pytest.raises(PermissionDenied):
        api.call("GET", "/api/ceo", {"viewer": "rd:R01"})
