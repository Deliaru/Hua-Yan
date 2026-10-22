"""V9.1 试用实例：主体由服务端认定；换模型只换网关与 Jev，业务原样保留；固定运行目录重启续跑。"""

from pathlib import Path

import pytest
import yaml

from huayan.app import HuayanApp
from huayan.knowledge import PermissionDenied
from huayan.ui import server


def _config(tmp_path):
    config = yaml.safe_load(Path("config/app.yaml").read_text(encoding="utf-8"))
    config.update(seeds_dir="tests/fixtures/mini_seeds", run_root=str(tmp_path / "runs"))
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


def test_trial_params_take_identity_from_server(monkeypatch):
    monkeypatch.setattr(server, "trial_roles", {"s-sales": "sales:S01", "s-rd": "rd:R01"})
    with pytest.raises(PermissionDenied):
        server.trial_params("s-none", "POST", "/api/escalate", {"session_id": "sess:1"})
    assert server.trial_params("s-none", "GET", "/api/meta", {}) == {}
    p = server.trial_params("s-rd", "POST", "/api/accept", {"req_id": "req:1", "by": "pm:P01", "viewer": "pm:P01"})
    assert p["by"] == p["viewer"] == "rd:R01"
    assert server.trial_params("s-rd", "POST", "/api/agents/chat", {"actor": "pm:P01", "text": "x"})["actor"] == "rd:R01"
    assert server.trial_params("s-sales", "POST", "/api/sessions", {"customer_id": "customer:C01", "sales_id": "sales:S02"})["sales_id"] == "sales:S01"
    assert server.trial_params("s-sales", "POST", "/api/turn", {"session_id": "sess:1", "speaker": "customer", "text": "x"})
    with pytest.raises(PermissionDenied):
        server.trial_params("s-rd", "POST", "/api/turn", {"session_id": "sess:1", "speaker": "sales", "text": "x"})
    with pytest.raises(PermissionDenied):
        server.trial_params("s-rd", "POST", "/api/sessions", {"customer_id": "customer:C01"})


def test_switch_models_keeps_business_and_resume(tmp_path):
    config = _config(tmp_path)
    app = HuayanApp.build(config, run_id="trial")
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "布面染花，上染不均匀")
    old_gateway = app.gateway
    app.switch_models(system1_impl="llm_fallback")
    assert app.gateway is not old_gateway and app.config["system1_impl"] == "llm_fallback"
    assert [s.id for s in app.sessions()] == [session.id]
    with pytest.raises(Exception):
        app.switch_models(system1_impl="no_such_impl")
    assert app.config["system1_impl"] == "llm_fallback" and app.jev.system1 is app.system1
    with pytest.raises(ValueError):
        app.switch_models(run_root="elsewhere")
    resumed = HuayanApp.build(config, run_id="trial", resume=True)
    assert [len(s.turns) for s in resumed.sessions()] == [len(app.sessions()[0].turns)]
