"""V9.1–V9.2 试用实例：主体由服务端认定；换模型只换网关与 Jev，业务原样保留；固定运行目录重启续跑；模型失败可见、可重跑。"""

from pathlib import Path

import httpx
import openai
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


class _DownGateway:
    """模型接口断开：每次调用都连不上。"""
    cache_dir = replay = trace = None

    def complete(self, req):
        raise openai.APIConnectionError(request=httpx.Request("POST", "http://down"))

    def structured(self, req, schema):
        return self.complete(req)


def test_model_failure_is_reported_and_rerun(tmp_path):
    """V9.2：模型失败时助手这一轮整个撤回；准备失败记在问题上、不占派单次数，重跑后再派。"""
    app = HuayanApp.build(_config(tmp_path), run_id="trial")
    session = app.start_session("customer:C01", "sales:S01")
    app.add_turn(session.id, "customer", "染完布面深一块浅一块")
    app.add_turn(session.id, "customer", "锦纶氨纶的，溢流缸")
    app.escalate(session.id, "sales:S01")
    app.config["gateway_mock"], app.gateway = False, _DownGateway()

    pending = [q.id for q in app.agents.pending_dispatch() if q.owner_id == "pm:agent"]
    assert pending
    app.agents.dispatch()                                    # 不抛出：失败记下，别的问题照派
    assert set(pending) <= set(app.agents.failures)
    assert set(pending) <= {q.id for q in app.agents.pending_dispatch()}    # 不占派单次数：下一次 dispatch 自动重跑
    rd_visible = app.agents.failures_for("rd:R01")
    assert rd_visible and set(rd_visible) <= set(pending)
    with pytest.raises(PermissionDenied):
        app.agents.retry(pending[0], "sales:S02")
    qid = next(iter(rd_visible))
    app.agents.retry(qid, "rd:R01")
    assert qid not in app.agents.failures and qid in {q.id for q in app.agents.pending_dispatch()}

    with pytest.raises(openai.APIConnectionError):
        app.agents.chat("rd:R01", "这张单下一步做什么", focus=app.requirements("rd:R01")[0].id)
    conv = app.agents.conversation("rd:R01", thread=app.requirements("rd:R01")[0].id)
    assert conv is None or all(m.text != "这张单下一步做什么" for m in conv.messages)


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
