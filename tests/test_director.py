"""V11.5–V11.6：导演在模板模式下送来关卡、扮演缺席的客户与岗位，只经 Api.call 动作；有人在玩的身份留给人。
每关一条离线回归：导演跑完本关，检查对象状态与事件（REPLAN-v11 第 6 节）。"""
from pathlib import Path

import yaml

from huayan.sim.director import Director
from huayan.ui import server


def _api(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    api = server.Api(None, str(path))
    api.build()
    return api


def _tick(api):
    return lambda: (api.advance(600), api.tick())


def _route(api, sid):
    return api.call("GET", "/api/route", {"id": sid, "viewer": "supervisor:M01"})


def test_levels_one_to_three_and_eight(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.play_through(8, _tick(api))      # 4–7 关还没接上，跳过
    s = director.state
    assert s["passed"] == [1, 2, 3, 8] and s["level"] == 8
    case = lambda n: s["cases"][str(n)]
    # 第 1 关：客户自助拿到推荐，业务员、产品经理、研发都没经过
    one = _route(api, case(1)[0])
    assert one["path"] == "自助解决" and all(one["roles"][r]["state"] == "none" for r in ("sales", "pm", "rd"))
    # 第 2 关：报价诉求交归属业务员，业务员接手就报价
    assert _route(api, case(2)[0])["path"] == "交业务员"
    assert any(e.kind == "sales_assigned" for e in api.app.events.query() if e.session_id == case(2)[0])
    # 第 3 关：现有产品不适用，需求直达研发，研发判已有产品适用、不立项
    assert _route(api, case(3)[0])["path"] == "研发不立项"
    # 第 8 关：两家同类需求，产品经理签机会，合成一个课题
    assert len(case(8)) == 2 and {_route(api, sid)["path"] for sid in case(8)} == {"产品机会"}
    # 导演只经 API 动作：每个代办都是浏览器也走的写接口
    assert {a["path"] for a in s["acted"]} <= set(server.POST)
    assert {(a["actor"], a["path"]) for a in s["acted"]} >= {
        ("sales:S01", "/api/turn"), ("rd:R02", "/api/decline"), ("pm:P01", "/api/merge")}   # 白地沾色指派给刘工


def test_present_roles_are_left_to_people(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.play_through(2, _tick(api))
    # 有人扮客户 C：导演只开会话不替他说话，把可以说的台词给出来
    director.step({"customer:C03", "rd:R01", "rd:R02"})
    sid = director.state["cases"]["3"][0]
    assert not api.app.view_session(sid, "customer:C03").turns
    assert director.view()["lines"] == [{"customer": "customer:C03", "session_id": sid, "text": "白地被沾色了"}]
    # 人说完两句，研发有人在玩：需求单停在研发待处理，不通关
    for line in ("白地被沾色了", "锦纶的布，尼龙用的那种料，酸性染料，缸里浸染的"):
        api.call("POST", "/api/turn", {"session_id": sid, "speaker": "customer", "text": line, "by": "customer:C03"})
    for _ in range(10):
        if not director.step({"customer:C03", "rd:R01", "rd:R02"}):
            _tick(api)()
    assert 3 not in director.state["passed"] and _route(api, sid)["roles"]["rd"]["state"] == "pending"
