"""Consumer controls for signature drift, swallowed defaults and observer custody."""
from __future__ import annotations

import asyncio
import inspect
from decimal import Decimal
from unittest.mock import Mock, NonCallableMock

import httpx2
import pytest
from pydantic import ValidationError

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.spec import AcpDuplexAdapter, AcpSpecSession, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore, RedisAgentStateStore
from optimus.mcp.client_disposition import ClientMcpSessionState
from optimus.runtime.modes import ExecutionMode
from tests.conftest import FakeGatewayClient
from tests.support.contract_doubles import ContractCallLog, assert_contract_calls, checked_agent_runner
from tests.unit.acp.test_operator_verify_custody import _checked_session_factory
from tests.unit.acp.test_spec_protocol import FakeRunner, _recording_outbound
from tests.unit.agent.test_state_store import _checked_redis, plan_record
from tests.unit.mcp.test_client_sdk import FakeHttpClient


class RecordingScript:
    def __init__(self):
        self.requests = []
        self.kwargs = []

    def run(self, request, **kwargs):
        self.requests.append(request)
        self.kwargs.append(kwargs)
        return AgentRunResult(run_id=request.run_id, session_id=request.session_id,
                              execution_mode=request.execution_mode, status=AgentRunStatus.COMPLETED,
                              final_state="CHAT_ONLY", output_text="checked answer", total_cost_usd=Decimal("0"))


def _adapter(tmp_path, script):
    return AcpDuplexAdapter(runner=checked_agent_runner(script), workspace_root=tmp_path,
                            sessions=InMemoryAcpSpecSessionStore(), outbound=RecordingOutboundChannel(),
                            interactive_recovery=False)


def _request(tmp_path):
    return AgentRunRequest(run_id="contract-run", task="Explain the value", execution_mode=ExecutionMode.PLAN,
                           workspace_root=tmp_path)


def test_adapter_receives_complete_runner_runtime_contract(tmp_path):
    script = FakeRunner()
    adapter = _adapter(tmp_path, script)
    session = AcpSpecSession(session_id="contract-session", cwd=tmp_path)
    names = ("planning_progress_observer", "halt_requested", "operation_control", "context_packer",
             "stage_receipts", "route_binder", "integrity_failure", "recovery_checkin")
    sentinels = {name: object() for name in names}
    actual = adapter._runner_runtime_kwargs(session=session, **sentinels)
    assert set(actual) == set(names) | {"client_mcp_service", "mcp_permission_broker"}
    assert len(actual) == 10
    assert all(actual[name] is value for name, value in sentinels.items())
    assert actual["client_mcp_service"] is None and actual["mcp_permission_broker"] is None
    checked_signature = inspect.signature(adapter._runner.run)
    real_signature = inspect.signature(AgentRunner.run)
    assert list(checked_signature.parameters.values()) == list(real_signature.parameters.values())[1:]


def test_legacy_signature_demonstrates_the_narrow_mapping(tmp_path):
    class LegacyScript:
        def run(self, request, *, planning_progress_observer=None, client_mcp_service=None, mcp_permission_broker=None):
            raise AssertionError("signature inspection must not call the runner")
    adapter = AcpDuplexAdapter(runner=LegacyScript(), workspace_root=tmp_path,
                               sessions=InMemoryAcpSpecSessionStore(), outbound=RecordingOutboundChannel())
    session = AcpSpecSession(session_id="legacy-session", cwd=tmp_path)
    actual = adapter._runner_runtime_kwargs(session=session, planning_progress_observer=object(),
                                             stage_receipts=object(), route_binder=object())
    assert set(actual) == {"planning_progress_observer", "client_mcp_service", "mcp_permission_broker"}


@pytest.mark.parametrize("bad_call", ["missing_request", "extra_positional", "obsolete_keyword"])
def test_invalid_runner_call_fails_before_script(tmp_path, bad_call):
    script = RecordingScript()
    boundary = checked_agent_runner(script)
    request = _request(tmp_path)
    with pytest.raises(TypeError):
        if bad_call == "missing_request":
            boundary.run()
        elif bad_call == "extra_positional":
            boundary.run(request, object())
        else:
            boundary.run(request, obsolete_runtime_option=True)
    assert script.requests == []
    with pytest.raises(AttributeError):
        boundary.unknown_runner_attribute = True


@pytest.mark.parametrize("kind", ["real", "subclass", "mock", "noncallable_mock", "already_checked", "missing_run"])
def test_runner_factory_requires_explicit_script_opt_in(kind):
    class Subclass(AgentRunner):
        pass
    if kind == "real":
        value = object.__new__(AgentRunner)
    elif kind == "subclass":
        value = object.__new__(Subclass)
    elif kind == "mock":
        value = Mock()
    elif kind == "noncallable_mock":
        value = NonCallableMock()
    elif kind == "already_checked":
        value = checked_agent_runner(RecordingScript())
    else:
        value = object()
    with pytest.raises(TypeError):
        checked_agent_runner(value)


def test_dispatcher_uses_checked_runner_and_real_result(tmp_path):
    script = RecordingScript()
    dispatcher = JsonRpcDispatcher(agent_runner=checked_agent_runner(script), workspace_root=tmp_path)
    reply = dispatcher.dispatch({"jsonrpc": "2.0", "id": "r", "method": "optimus.agent.run", "params": {
        "run_id": "contract-run", "task": "Explain the value", "execution_mode": "plan", "workspace_root": str(tmp_path)}})
    assert reply["result"]["output_text"] == "checked answer"
    assert reply["result"]["status"] == "completed"
    assert len(script.requests) == 1 and isinstance(script.requests[0], AgentRunRequest)
    assert script.requests[0].workspace_root == tmp_path.resolve()


async def test_adapter_passes_real_callbacks_and_non_none_mcp_state(tmp_path):
    script = RecordingScript()
    adapter = _adapter(tmp_path, script)
    opened = await adapter.handle_client_request({"jsonrpc": "2.0", "id": "n", "method": "session/new", "params": {"cwd": str(tmp_path)}})
    sid = opened.response["result"]["sessionId"]
    session = adapter._sessions.get(sid)
    session.client_mcp_state = ClientMcpSessionState(session_id=sid)
    reply = await adapter.handle_client_request({"jsonrpc": "2.0", "id": "p", "method": "session/prompt", "params": {
        "sessionId": sid, "prompt": [{"type": "text", "text": "Explain the value"}]}})
    assert reply.response["result"]["stopReason"] == "end_turn"
    assert len(script.requests) == 1
    kwargs = script.kwargs[0]
    assert kwargs["client_mcp_service"] is session.client_mcp_state.tool_service
    assert kwargs["mcp_permission_broker"] is not None
    assert kwargs["stage_receipts"] == session.cost_settlement.record_attempt
    assert kwargs["stage_receipts"].__self__ is session.cost_settlement
    assert kwargs["integrity_failure"] == session.cost_settlement.record_integrity_failure
    assert kwargs["halt_requested"] == kwargs["operation_control"].halt_requested
    assert kwargs["halt_requested"].__self__ is kwargs["operation_control"]
    assert callable(kwargs["planning_progress_observer"])
    assert adapter._runner.event_sink is None
    assert not hasattr(adapter._runner, "_planning_progress_observer")


def test_runner_delegate_tracks_override_and_exception_identity(tmp_path):
    script = RecordingScript()
    boundary = checked_agent_runner(script)
    first = boundary.run(_request(tmp_path))
    assert isinstance(first, AgentRunResult)
    failure = RuntimeError("intentional scripted failure")
    def fail(_request, **_kwargs):
        raise failure
    script.run = fail
    with pytest.raises(RuntimeError) as caught:
        boundary.run(_request(tmp_path))
    assert caught.value is failure


def test_unexpected_runner_member_has_a_recorded_failure(contract_call_log):
    boundary = checked_agent_runner(RecordingScript())
    log = contract_call_log[-1]
    log.expect("_flush_event_sink")
    with pytest.raises(AssertionError, match="unscripted.*_flush_event_sink"):
        boundary._flush_event_sink()
    assert log.calls == ["_flush_event_sink"]


def test_unscripted_redis_operation_is_loud(contract_call_log):
    client = _checked_redis(object())
    log = contract_call_log[-1]
    log.expect("ping")
    with pytest.raises(AssertionError, match="unscripted.*ping"):
        client.ping()
    assert log.calls == ["ping"]
    assert not hasattr(client, "aclose")


def test_persistence_cannot_hide_a_recorded_missing_script(contract_call_log):
    client = _checked_redis(object())
    log = contract_call_log[-1]
    log.expect("hset")
    outcome = RedisAgentStateStore(client=client).persist_plan(plan_record())
    assert outcome.outcome.value == "persistence_failed"
    assert log.calls == ["hset"]
    # An ordinary scenario's empty expectation still rejects the absorbed error.
    with pytest.raises(AssertionError, match="unexpected contract calls"):
        assert_contract_calls([ContractCallLog("ordinary Redis", calls=log.calls)])
    assert log.calls == ["hset"]


def test_session_default_is_recorded_even_when_cleanup_absorbs_it(contract_call_log):
    class EmptySession:
        def __init__(self, **kwargs):
            pass
    factory = _checked_session_factory(EmptySession)
    session = factory(process=object(), transcript=object())
    log = contract_call_log[-1]
    log.expect("close_stdin")
    error = RuntimeError("original failure")
    try:
        session.close_stdin()
    except AssertionError as secondary:
        error.add_note(str(secondary))
    assert log.calls == ["close_stdin"] and "unscripted" in error.__notes__[0]
    with pytest.raises(AssertionError, match="unexpected contract calls"):
        assert_contract_calls([ContractCallLog("ordinary session", calls=log.calls)])


def test_model_validation_is_separate_from_autospec():
    with pytest.raises(ValidationError):
        AgentRunResult(run_id="bad", execution_mode=ExecutionMode.PLAN, final_state="CHAT_ONLY", output_text="missing status")


def test_http_contract_needs_no_real_client_template(monkeypatch):
    def forbidden_init(*_args, **_kwargs):
        raise AssertionError("real HTTP client template allocated")
    monkeypatch.setattr(httpx2.AsyncClient, "__init__", forbidden_init)
    client = FakeHttpClient(follow_redirects=False, trust_env=False)
    assert client.checked.follow_redirects is False and client.checked.trust_env is False
    with pytest.raises(AttributeError):
        client.checked.unknown_http_attribute = True
    with pytest.raises(AttributeError):
        _ = client.checked.unknown_http_attribute


@pytest.mark.parametrize("fail_inside_stream", [False, True])
async def test_checked_http_stream_preserves_real_response_close(fail_inside_stream):
    client = FakeHttpClient(follow_redirects=False, trust_env=False, stream_chunks=[b"one", b"two"])
    response = None
    try:
        async with client.checked.stream("GET", "https://offline.invalid/stream") as response:
            assert await response.aread() == b"onetwo"
            if fail_inside_stream:
                raise ValueError("consumer failed")
    except ValueError:
        assert fail_inside_stream
    assert response is not None and response.is_closed
    assert client.opened_urls == ["https://offline.invalid/stream"]
    await client.checked.aclose()


async def test_checked_outbound_keeps_real_lists_futures_and_cancel_results():
    channel = _recording_outbound()
    await channel.notify("session/update", {"text": "one"}, require_flushed=True)
    assert channel.notifications == [{"jsonrpc": "2.0", "method": "session/update", "params": {"text": "one"}}]
    task = asyncio.create_task(channel.request("permission", {"value": "two"}))
    request = await channel.wait_for_request("permission")
    assert channel.requests[0] is request and request["params"] == {"value": "two"}
    channel.respond(request["id"], {"approved": True})
    assert await task == {"approved": True}
    cancelled = asyncio.create_task(channel.request("cancelled", {"value": "three"}))
    request = await channel.wait_for_request("cancelled")
    channel.cancel_request(request["id"], {"approved": False})
    assert await cancelled == {"approved": False}


def test_shared_live_gateway_definition_drives_real_hermetic_runner(tmp_path):
    (tmp_path / "example.py").write_text("value = 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("READ example.py\nExplain the value.")
    with pytest.raises(TypeError):
        gateway.checked.create_response(model="glm-5.2", input_text="probe", obsolete_route=True)
    assert gateway.calls == []
    response = gateway.checked.create_response(model="glm-5.2", input_text="signature probe", route_binding=None)
    assert response.output_text == "READ example.py\nExplain the value."
    runner = AgentRunner(gateway_client=gateway.checked, model="glm-5.2", state_store=InMemoryAgentStateStore())
    result = runner.run(_request(tmp_path))
    assert result.status is AgentRunStatus.COMPLETED
    assert result.mutation_count == 0 and result.total_cost_usd == Decimal("0.002")
    assert len(gateway.calls) == 2 and gateway.calls[1]["model"] == "glm-5.2"
