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


def test_shared_instance_starts_offline_and_resumes(tmp_path, monkeypatch):
    """标准试用装配路径须能启动离线实例，并续跑已经录入的业务。"""
    config = _config(tmp_path)
    monkeypatch.setattr(server, "TRIAL", "offline-trial")
    api = server.Api(None, config)
    api.build()
    assert isinstance(api.lock, server.TrialGate)
    assert api.call("GET", "/api/meta", {})["status"].gateway_mock
    session = api.call("POST", "/api/sessions", {"customer_id": "customer:C01", "sales_id": "sales:S01"})
    api.call("POST", "/api/turn", {"session_id": session.id, "speaker": "customer",
        "text": "锦纶氨纶的布面染花，温度75℃", "by": "sales:S01"})
    resumed = server.Api(None, config)
    resumed.build()
    restored = resumed.app.sessions()
    assert len(restored) == 1 and restored[0].id == session.id
    assert restored[0].turns[0].text == "锦纶氨纶的布面染花，温度75℃"
    assert restored[0].need.known_temperature() == (75.0, 75.0)


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


def test_turn_and_trace_check_the_server_identity(tmp_path):
    """V9.6a：看不到的会话不能往里说话；助手轨迹只给委托人本人。"""
    app = HuayanApp.build(_config(tmp_path), run_id="trial")
    session = app.start_session("customer:C01", "sales:S01")
    for by in ("customer:C02", "sales:S02"):
        with pytest.raises(PermissionDenied):
            server.POST["/api/turn"](app, {"session_id": session.id, "speaker": "customer", "text": "布面发花", "by": by})
    assert server.POST["/api/turn"](app, {"session_id": session.id, "speaker": "customer", "text": "布面发花",
                                          "by": "sales:S01"}).turns[-1].text == "布面发花"
    with pytest.raises(PermissionDenied):
        server.GET["/api/agents/trace"](app, {"conversation_id": "conv:rd:R01:inbox", "viewer": "customer:C02"})
    assert server.GET["/api/agents/trace"](app, {"conversation_id": "conv:rd:R01:inbox", "viewer": "rd:R01"}) == []


def test_ownerless_question_gets_its_owner_when_raised_again():
    """V9.6a：自助客户当时没有归属业务员，觉提出的客户评价没人接；配上人之后再提出，补上主人与签字人。"""
    from datetime import datetime, timezone
    from huayan.bus import QuestionBus
    from huayan.contracts import Question
    from huayan.events import EventLog
    bus = QuestionBus(EventLog())
    ask = dict(id="", family="market_eval", title="客户评价", object_id="requirement:req:1", owner_role="sales",
               signer_role="sales", scored_by="rule", discoverer="jue_proto", dedup_key="market_eval:requirement:req:1",
               created_at=datetime(2026, 10, 23, tzinfo=timezone.utc))
    first = bus.publish(Question(**ask))
    assert first.owner_id is None
    again = bus.publish(Question(**ask, owner_id="sales:S01", signer_id="sales:S01"))
    assert again.id == first.id and (again.owner_id, again.signer_id) == ("sales:S01", "sales:S01")


def test_ownerless_question_is_dispatched_once_it_has_an_owner(tmp_path):
    """V9.6a：没人接的问题这一轮不派，但不记成派过；配上主人后下一次 dispatch 照常派。"""
    app = HuayanApp.build(_config(tmp_path), run_id="trial")
    from datetime import datetime, timezone
    from huayan.contracts import Question
    q = app.bus.publish(Question(id="", family="market_eval", title="客户评价", object_id="requirement:req:9",
        owner_role="sales", signer_role="sales", scored_by="rule", discoverer="jue_proto",
        dedup_key="market_eval:requirement:req:9", created_at=datetime(2026, 10, 23, tzinfo=timezone.utc)))
    app.agents.dispatch()
    assert q.id in {x.id for x in app.agents.pending_dispatch()}
    q.owner_id = q.signer_id = "sales:S01"
    app.agents.dispatch()
    assert q.id not in {x.id for x in app.agents.pending_dispatch()}
