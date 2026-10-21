"""Plan 12.2 diagnosability correction plan v4 (operator-approved 2026-10-21), the host side.

C1: the trace projects every id and router stage type to a recognized form. C3: an HTTP error envelope keeps why
it was unreadable, apart from unchanged accounting. C4: every failure, refusal and context fault leaves one bounded
``error`` event in the workspace ``telemetry.jsonl`` whether or not tracing is enabled, written by the writer of
the harness that started the work. C5: every pre-run refusal keeps a fixed reason. C7: the operator line, the trace
and the telemetry record are contained separately.
"""

from __future__ import annotations

import asyncio
import errno
import functools
import io
import json
import threading
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

import optimus.acp.spec as spec_module
from optimus.acp import bootstrap as bootstrap_module
from optimus.acp.bootstrap import build_agent_harness_runtime, build_configured_server
from optimus.acp.debug_trace import configure_debug_trace, log_prompt_refusal, log_provider_attempts, reset_debug_trace_context
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.gateway import client as client_module
from optimus.gateway.attempts import attempts_from_failure, attempts_from_response, gateway_failure_facts
from optimus.gateway.client import GatewayRequest, UrllibGatewayTransport
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from tests.unit.acp.test_bootstrap import HAIKU, _fake_client_runtime, _lifetime_runtime, _server_environ
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment, new_session, prompt, rpc
from tests.unit.acp.test_context_notices import DispatchingRunner
from tests.unit.acp.test_late_receipts import _RaisingEngine

pytestmark = pytest.mark.usefixtures("isolated_windows_known_folders")

CANARY = "Bearer " + "host-correction-canary"  # synthetic; must never reach a persisted record
BARE_KEY = "sk-or-v1-" + "0123456789abcdef" * 4  # pragma: allowlist secret - synthetic credential-shaped canary
PROSE = "private note CANARY"
SESSION = f"session-{uuid.uuid4().hex}"
RUN = f"{SESSION}:2"
ROUTE = f"{RUN}:answer:1:{uuid.uuid4().hex}"
SUMMARY = f"{SESSION}:2:summary:1:{uuid.uuid4().hex}"
GW = f"gw-{uuid.uuid4().hex}"


@pytest.fixture(autouse=True)
def _isolated_trace():
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


def _writer(root: Path) -> JsonlTelemetryWriter:
    return JsonlTelemetryWriter.for_workspace(root)


def _events(root: Path) -> list[dict[str, Any]]:
    path = root / ".optimus" / "telemetry.jsonl"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    assert CANARY not in text and BARE_KEY not in text and "private note" not in text.lower()
    return [event for event in map(json.loads, text.splitlines()) if event["kind"] == "error"]


def _message(event: dict[str, Any]) -> dict[str, Any]:
    return json.loads(event["message"])


def _trace(tmp_path: Path, location: str) -> list[dict[str, Any]]:
    log = tmp_path / "trace" / "debug-acp.ndjson"
    text = log.read_text(encoding="utf-8")
    assert CANARY not in text and BARE_KEY not in text and "private note" not in text.lower()
    return [record["data"] for record in map(json.loads, text.splitlines()) if record["location"] == location]


def _transport_failure() -> GatewayHttpError:
    return GatewayHttpError(0, CANARY, failure={"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": errno.ECONNREFUSED})


# --- C1: the trace's projections ---------------------------------------------------------------------------------


def test_the_trace_projects_correlation_ids_attempt_ids_and_stage_types(tmp_path) -> None:
    configure_debug_trace(enabled=True, log_path=tmp_path / "trace" / "debug-acp.ndjson")
    refused = GatewayHttpError(
        502, CANARY, gateway_code="UPSTREAM_ATTEMPT_UNCERTAIN", retryable=False,
        route_attempts=(
            GatewayRouteAttempt(attempt=1, gateway_request_id=GW, outcome="uncertain", provider_request_id="gen-17-Ab", router_pipeline=("guardrail", PROSE)),
            GatewayRouteAttempt(attempt=2, gateway_request_id="gw-1", outcome="rejected", http_status=429, provider_request_id=BARE_KEY),
        ),
    )  # fmt: skip
    attempts = attempts_from_failure(refused)
    log_provider_attempts(stage="answer", correlation=lambda: {"run_id": RUN, "session_id": SESSION, "request_id": ROUTE}, attempts=attempts, failure=refused)
    log_provider_attempts(stage="answer", correlation=lambda: {"run_id": PROSE, "session_id": BARE_KEY, "request_id": PROSE}, attempts=attempts, failure=refused)

    real, hostile = _trace(tmp_path, "debug_trace.py:log_provider_attempts")
    assert (real["run_id"], real["session_id"], real["request_id"]) == (RUN, SESSION, ROUTE)
    assert (hostile["run_id"], hostile["session_id"], hostile["request_id"]) == ("unrecognized",) * 3
    first, second = real["attempts"]
    assert (first["gateway_request_id"], first["provider_request_id"], first["router_pipeline"]) == (GW, "gen-17-Ab", ["guardrail", "unrecognized"])
    assert (second["gateway_request_id"], second["provider_request_id"]) == ("unrecognized", "unrecognized")


def test_a_prompt_refusal_projects_its_ids_and_keeps_a_zero_rpc_id(tmp_path) -> None:
    configure_debug_trace(enabled=True, log_path=tmp_path / "trace" / "debug-acp.ndjson")
    log_prompt_refusal(session_id=SESSION, request_id=0, reason="cap")
    log_prompt_refusal(session_id=PROSE, request_id=BARE_KEY, reason="cap")
    assert _trace(tmp_path, "debug_trace.py:log_prompt_refusal") == [
        {"session_id": SESSION, "request_id": 0, "reason": "cap"},
        {"session_id": "unrecognized", "request_id": "unrecognized", "reason": "cap"},
    ]


def test_the_host_allowlists_match_the_gateways() -> None:
    from optimus.acp.debug_trace import ROUTER_STAGES
    from optimus_gateway.upstream_client import KNOWN_ROUTER_STAGES

    assert ROUTER_STAGES == KNOWN_ROUTER_STAGES


# --- C3: the HTTP-error envelope -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "envelope"),
    [
        (502, b"{not json", {"error_body_encoding": "ok", "error_body": "invalid_json", "usage_audit_code": None}),
        (502, json.dumps({"gateway_usage": {"gateway_request_id": "", "provider": "p", "billing_units": 1, "cost_usd": "0.1"}}).encode(),
         {"error_body_encoding": "ok", "error_body": "ok", "usage_audit_code": "GATEWAY_USAGE_INVALID"}),
        (502, b'{"error": "bad \xff byte"}', {"error_body_encoding": "invalid_utf8", "error_body": "ok", "usage_audit_code": None}),
        (502, b"[1]", {"error_body_encoding": "ok", "error_body": "non_object", "usage_audit_code": None}),
        (422, json.dumps({"error": "x", "code": "UNKNOWN_MODEL"}).encode(), {"error_body_encoding": "ok", "error_body": "ok", "usage_audit_code": None}),
    ],
    ids=["502-invalid-json", "502-invalid-usage", "502-invalid-utf8", "502-non-object", "422-no-usage"],
)
def test_an_http_error_envelope_keeps_why_it_was_unreadable_and_accounting_is_unchanged(monkeypatch, status: int, body: bytes, envelope: dict) -> None:
    def refuse(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:9/v1/responses", status, "error", None, io.BytesIO(body))  # type: ignore[arg-type]

    monkeypatch.setattr(client_module, "urlopen", refuse)
    with pytest.raises(GatewayHttpError) as caught:
        UrllibGatewayTransport().post_json(GatewayRequest(method="POST", url="http://127.0.0.1:9/v1/responses", headers={}, payload={}))
    assert str(caught.value) == body.decode("utf-8", errors="replace")  # the message is unchanged
    assert gateway_failure_facts(caught.value)["error_envelope"] == envelope
    assert [(a.outcome, a.cost_usd, a.http_status) for a in attempts_from_failure(caught.value)] == [("uncertain", None, status)]


# --- C4: always-on records with tracing off --------------------------------------------------------------------------


def test_a_host_transport_failure_leaves_one_error_event_with_tracing_off(tmp_path) -> None:
    failure = _transport_failure()
    correlation = lambda: {"run_id": RUN, "session_id": SESSION, "settled_turn": 1, "wire_attempt": 1}  # noqa: E731
    log_provider_attempts(stage="answer", correlation=correlation, attempts=attempts_from_failure(failure), failure=failure, telemetry=_writer(tmp_path))

    [event] = _events(tmp_path)
    assert (event["run_id"], event["session_id"], event["request_id"]) == (RUN, SESSION, RUN)
    assert (event["error_type"], event["disposition"]) == ("provider_attempt_failure", "recorded")
    assert _message(event)["gateway_failure"]["failure"]["cause"] == "ConnectionRefusedError"


def test_a_successful_request_leaves_no_error_event(tmp_path) -> None:
    usage = GatewayUsage(gateway_request_id=GW, provider="openrouter", provider_request_id="gen-1", billing_units=3, cost_usd=Decimal("0.0003"))
    response = GatewayResponse(response_id="resp-1", output_text="ok", gateway_usage=usage, raw={})
    log_provider_attempts(stage="answer", correlation=lambda: {"run_id": RUN}, attempts=attempts_from_response(response), telemetry=_writer(tmp_path))
    assert _events(tmp_path) == []


def test_a_summary_failure_takes_its_run_from_the_summary_request_id(tmp_path) -> None:
    lost = ConnectionResetError(errno.ECONNRESET, CANARY)
    log_provider_attempts(
        stage="summary", correlation=lambda: {"session_id": SESSION, "request_id": SUMMARY}, attempts=attempts_from_failure(lost), failure=lost, telemetry=_writer(tmp_path)
    )
    [event] = _events(tmp_path)
    assert (event["run_id"], event["session_id"], event["request_id"]) == (RUN, SESSION, SUMMARY)
    assert _message(event)["host_failure"] == {"exception": {"class": "ConnectionResetError", "errno": errno.ECONNRESET}}


class _RaisingWriter:
    def append(self, _event: Any) -> None:
        raise OSError(28, CANARY)


def test_a_raising_writer_changes_no_result_and_cancellation_still_propagates(tmp_path) -> None:
    failure = _transport_failure()
    assert log_provider_attempts(stage="answer", correlation=lambda: {}, attempts=attempts_from_failure(failure), failure=failure, telemetry=_RaisingWriter()) is None

    def cancelled() -> dict[str, Any]:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        log_provider_attempts(stage="answer", correlation=cancelled, attempts=(), failure=failure, telemetry=_writer(tmp_path))


def test_two_writers_for_one_file_append_whole_lines_concurrently(tmp_path) -> None:
    writers = [_writer(tmp_path), _writer(tmp_path)]
    failure = _transport_failure()
    attempts = attempts_from_failure(failure)

    def burst(writer: JsonlTelemetryWriter) -> None:
        for _ in range(50):
            log_provider_attempts(stage="answer", correlation=lambda: {"run_id": RUN}, attempts=attempts, failure=failure, telemetry=writer)

    threads = [threading.Thread(target=burst, args=(writer,)) for writer in writers for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(_events(tmp_path)) == 200  # every line parsed as one whole event


# --- C4 and C5: the adapter's records --------------------------------------------------------------------------------


def _adapter(tmp_path: Path, attachment: Any = None, runner: Any = None) -> tuple[AcpDuplexAdapter, RecordingOutboundChannel]:
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner or Runner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
        context_attachment=attachment,
        failure_telemetry=_writer(tmp_path),
    )
    return adapter, outbound


async def test_an_admission_refusal_leaves_an_error_event_with_tracing_off(tmp_path, capsys) -> None:
    adapter, outbound = _adapter(tmp_path, make_attachment(source_max=4096, reservation=1000))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    await prompt(adapter, outbound, session_id, "PRIVATE-PROMPT " + "x" * 3500, "big")

    [event] = _events(tmp_path)
    assert (event["run_id"], event["session_id"], event["request_id"]) == (f"{session_id}:pre-run", session_id, "big")
    assert (event["error_type"], _message(event)["reason"]) == ("prompt_refused", "reservation")
    assert "PRIVATE-PROMPT" not in (tmp_path / ".optimus" / "telemetry.jsonl").read_text(encoding="utf-8")


def _prompt_request(request_id: Any, params: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "session/prompt", "params": params}


async def test_every_pre_run_refusal_keeps_its_fixed_reason(tmp_path, capsys) -> None:
    adapter, _outbound = _adapter(tmp_path)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    text = [{"type": "text", "text": "PRIVATE-PROMPT"}]
    busy = await new_session(adapter, tmp_path, mode="chat")
    adapter._active_turns[busy] = object()  # noqa: SLF001 - a turn in progress, without running one
    cases = [
        (0, "x", "invalid_params", None),
        (1, {"sessionId": session_id, "prompt": "PRIVATE-PROMPT"}, "invalid_prompt_shape", session_id),
        ("abc", {"sessionId": PROSE, "prompt": text}, "unknown_session", "unrecognized"),
        (3, {"sessionId": session_id, "prompt": []}, "empty_prompt", session_id),
        (4, {"sessionId": busy, "prompt": text}, "turn_in_progress", busy),
    ]
    capsys.readouterr()
    for request_id, params, _reason, _session in cases:
        assert "error" in await rpc(adapter, _prompt_request(request_id, params))

    lines = [line for line in capsys.readouterr().err.splitlines() if line.startswith("optimus.acp: prompt refused")]
    expected_lines = [f"optimus.acp: prompt refused session_id={shown or 'none'} reason={reason}" for _id, _params, reason, shown in cases]
    assert lines == expected_lines
    events = _events(tmp_path)
    assert [(e["request_id"], e["session_id"], _message(e)["reason"], e["error_type"]) for e in events] == [
        (str(request_id), shown, reason, "pre_run_refused") for request_id, _params, reason, shown in cases
    ]
    assert [e["run_id"] for e in events] == [f"{shown or 'no-session'}:pre-run" for _id, _params, _reason, shown in cases]
    assert "PRIVATE-PROMPT" not in json.dumps(events) and "PRIVATE-PROMPT" not in "\n".join(lines)


async def test_a_context_fault_leaves_an_error_event_with_tracing_off(tmp_path, capsys) -> None:
    adapter, outbound = _adapter(tmp_path, make_attachment(engine=_RaisingEngine()), DispatchingRunner())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Prompt {n} " + "words " * 40, f"p{n}")

    faults = [event for event in _events(tmp_path) if event["error_type"] == "context_fault"]
    assert faults and all(event["run_id"].startswith(f"{session_id}:") for event in faults)
    assert {(_message(event)["category"], _message(event)["detail"]) for event in faults} >= {("engine_error", "RuntimeError")}


class _BrokenStderr:
    def write(self, _text: str) -> int:
        raise OSError(28, "No space left on device")

    def flush(self) -> None:
        raise OSError(28, "No space left on device")


async def test_a_failing_operator_line_still_lets_the_trace_and_telemetry_through(tmp_path, monkeypatch) -> None:
    configure_debug_trace(enabled=True, log_path=tmp_path / "trace" / "debug-acp.ndjson")
    adapter, outbound = _adapter(tmp_path, make_attachment(source_max=4096, reservation=1000))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    monkeypatch.setattr(spec_module.sys, "stderr", _BrokenStderr())

    await prompt(adapter, outbound, session_id, "x" * 3500, "big")

    monkeypatch.undo()
    assert [_message(event)["reason"] for event in _events(tmp_path)] == ["reservation"]
    assert [record["reason"] for record in _trace(tmp_path, "debug_trace.py:log_prompt_refusal")] == ["reservation"]


# --- C4: ownership through the real bootstrap wiring ----------------------------------------------------------------


def test_the_harness_binds_its_attempt_observer_to_its_own_workspace_writer(monkeypatch, tmp_path) -> None:
    from optimus.telemetry.fanout import TelemetryFanout

    _lifetime_runtime(monkeypatch)
    harness = build_agent_harness_runtime(environ=_server_environ(), workspace_root=tmp_path, model=HAIKU)
    observer = harness.agent_runner._provider_attempt_observer  # noqa: SLF001
    assert isinstance(observer, functools.partial) and observer.func is log_provider_attempts
    assert observer.keywords["telemetry"] is harness.telemetry_writer
    assert harness.telemetry_writer is harness.agent_runner.event_sink.jsonl_writer
    fanned: list[Any] = []
    monkeypatch.setattr(TelemetryFanout, "__call__", lambda self, event: fanned.append(event))

    failure = _transport_failure()
    observer(stage="answer", correlation=lambda: {"run_id": RUN, "session_id": SESSION}, attempts=attempts_from_failure(failure), failure=failure)
    assert len(_events(tmp_path)) == 1
    assert fanned == []  # nothing new reaches the Redis sink or the Gateway exporter


async def test_the_records_change_no_reply_and_no_accounting(tmp_path) -> None:
    async def scenario(root: Path, telemetry: bool) -> tuple[list[Any], Any]:
        root.mkdir()
        outbound = RecordingOutboundChannel()
        adapter = AcpDuplexAdapter(
            runner=DispatchingRunner(),
            workspace_root=root,
            sessions=InMemoryAcpSpecSessionStore(),
            outbound=outbound,
            context_attachment=make_attachment(engine=_RaisingEngine()),
            failure_telemetry=_writer(root) if telemetry else None,
        )
        session_id = await new_session(adapter, root, mode="chat")
        replies = [await prompt(adapter, outbound, session_id, f"Prompt {n} " + "words " * 40, f"p{n}") for n in range(3)]
        settled = adapter._sessions.get(session_id).cost_settlement.settle_all()  # noqa: SLF001
        return [reply.get("result") for reply in replies], (settled.known_subtotal_usd, settled.complete)

    with_records, without = await scenario(tmp_path / "on", True), await scenario(tmp_path / "off", False)
    assert with_records == without
    assert _events(tmp_path / "on") and _events(tmp_path / "off") == []


def test_the_summary_attachments_and_the_adapter_get_the_harness_observer_and_writer(monkeypatch, tmp_path) -> None:
    _lifetime_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: _fake_client_runtime())
    calls: list[dict[str, Any]] = []
    real_ordinary = bootstrap_module.ordinary_attachment

    def ordinary(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return real_ordinary(**kwargs)

    def stage_c(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return None, None

    monkeypatch.setattr(bootstrap_module, "ordinary_attachment", ordinary)
    monkeypatch.setattr("optimus.acp.stage_c.stage_c_attachment", stage_c)

    server = build_configured_server(environ=_server_environ(), workspace_root=tmp_path, model=HAIKU)
    build_configured_server(environ=_server_environ(), workspace_root=tmp_path, model=HAIKU, stage_c=object())

    for call in calls:
        observer = call["attempt_observer"]
        assert observer.func is log_provider_attempts and observer.keywords["telemetry"].path == tmp_path.resolve() / ".optimus" / "telemetry.jsonl"
    assert server._failure_telemetry.path == tmp_path.resolve() / ".optimus" / "telemetry.jsonl"  # noqa: SLF001


def test_a_later_composition_never_redirects_or_clears_an_earlier_harness_writer(monkeypatch, tmp_path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    _lifetime_runtime(monkeypatch)
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: _fake_client_runtime())
    harness_a = build_agent_harness_runtime(environ=_server_environ(), workspace_root=first, model=HAIKU)
    late = harness_a.agent_runner._provider_attempt_observer  # noqa: SLF001 - a worker still running after A's shutdown
    harness_a.close()
    failure = _transport_failure()

    def late_failure() -> None:
        late(stage="answer", correlation=lambda: {"run_id": RUN}, attempts=attempts_from_failure(failure), failure=failure)

    build_configured_server(environ=_server_environ(), workspace_root=second, model=HAIKU)  # B succeeds
    late_failure()
    assert (len(_events(first)), len(_events(second))) == (1, 0)

    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("B fails")))
    with pytest.raises(RuntimeError):
        build_configured_server(environ=_server_environ(), workspace_root=second, model=HAIKU)  # the server-level rollback
    late_failure()

    monkeypatch.setattr("optimus.acp.bootstrap.AgentRunner", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("B fails")))
    with pytest.raises(RuntimeError):
        build_agent_harness_runtime(environ=_server_environ(), workspace_root=second, model=HAIKU)  # the harness-level rollback
    late_failure()
    assert (len(_events(first)), len(_events(second))) == (3, 0)


def test_a_host_transport_failure_through_the_real_client_reaches_the_bound_writer(monkeypatch, tmp_path) -> None:
    def refuse(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError(errno.ECONNREFUSED, CANARY))

    monkeypatch.setattr(client_module, "urlopen", refuse)
    with pytest.raises(GatewayHttpError) as caught:
        UrllibGatewayTransport().post_json(GatewayRequest(method="POST", url="http://127.0.0.1:9/v1/responses", headers={}, payload={}))
    bound = functools.partial(log_provider_attempts, telemetry=_writer(tmp_path))
    bound(stage="answer", correlation=lambda: {"run_id": RUN}, attempts=attempts_from_failure(caught.value), failure=caught.value)
    [event] = _events(tmp_path)
    assert _message(event)["gateway_failure"]["failure"] == {"kind": "transport", "class": "URLError", "cause": "ConnectionRefusedError", "errno": errno.ECONNREFUSED}
