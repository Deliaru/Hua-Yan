"""V11.5：导演在模板模式下送来关卡、扮演缺席的客户与岗位，只经 Api.call 动作；有人在玩的岗位留给人。"""
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


def test_director_plays_levels_one_to_three(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.play_through(3, api.tick)
    assert director.state["passed"] == [1, 2, 3] and director.state["level"] == 3
    paths = [api.call("GET", "/api/route", {"id": director.state["cases"][str(n)][0], "viewer": "supervisor:M01"})["path"]
             for n in (1, 2, 3)]
    assert paths == ["自助解决", "交业务员", "研发不立项"]
    # 导演代办的写动作都留了记录：客户说话、业务员报价、研发不立项
    assert {(a["actor"], a["path"]) for a in director.state["acted"]} >= {
        ("customer:C01", "/api/turn"), ("sales:S01", "/api/turn"), ("rd:R02", "/api/decline")}   # 白地沾色指派给刘工


def test_director_leaves_present_roles_to_people(tmp_path):
    api = _api(tmp_path)
    director = Director(lambda: api, tmp_path / "play.json")
    director.play_through(2, api.tick)
    for _ in range(10):
        if not director.step({"rd:R01", "rd:R02"}):
            api.tick()
    sid = director.state["cases"]["3"][0]
    assert 3 not in director.state["passed"]
    assert api.call("GET", "/api/route", {"id": sid, "viewer": "supervisor:M01"})["roles"]["rd"]["state"] == "pending"
