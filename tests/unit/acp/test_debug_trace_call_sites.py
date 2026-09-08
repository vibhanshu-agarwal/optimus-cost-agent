"""Seam 1: every production diagnostic call site defers its payload work and is failure-contained.

Ported from sandbox tag `sandbox-seam1` (commit ad9deeb7) and adapted to main's current
call inventory. Two kinds of evidence, deliberately kept apart:

1. The AST extraction below executes each production diagnostic STATEMENT (not a copy of
   it) against the real sink, in a namespace where every diagnostic input is an opaque
   object whose ANY inspection raises a BaseException. This isolates diagnostic-only work
   from the surrounding business work, which may legitimately inspect the same objects.
2. The real-path tests at the end drive production wiring (outbound channel, a full
   ACP session, the request-exception path, teardown, and the planning loop) with
   diagnostic-only failures injected, and compare serving outcomes with tracing off/on.

No production class or enum is re-created here; expected payloads are asserted from
the records the real sink writes.
"""

from __future__ import annotations

import ast
import asyncio
import io
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from optimus.acp import debug_trace
from optimus.acp import server as server_module
from optimus.acp.debug_trace import configure_debug_trace
from optimus.acp.errors import INTERNAL_ERROR
from optimus.acp.server import NdjsonOutboundChannel, StdioNdjsonLineReader
from optimus.mcp.client_supervisor import MCPSupervisorState
from tests.integration.acp.test_server_stream import (
    InteractiveLineReader,
    MemoryLineWriter,
    configured_test_agent_server,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE_FOR_PREFIX = {
    "server.py": ROOT / "src/optimus/acp/server.py",
    "spec.py": ROOT / "src/optimus/acp/spec.py",
    "planning_loop.py": ROOT / "src/optimus/agent/planning_loop.py",
}

# Hot sites run per message or per tool call: they guard even the supplier allocation.
HOT = (
    "server.py:NdjsonOutboundChannel.notify",
    "server.py:NdjsonOutboundChannel.request",
    "server.py:NdjsonOutboundChannel.deliver_client_response",
    "server.py:process_request:entry",
    "server.py:process_request:exit",
    "server.py:serve_ndjson:inbound_client_response_raw",
    "spec.py:_emit_result_updates:tool_call",
)
# Warm sites run once per turn or per failure: a supplier is enough.
WARM = (
    "server.py:process_request:exception",
    "spec.py:handle_client_notification:session_cancel",
    "spec.py:_handle_session_prompt:entry",
    "spec.py:_handle_session_prompt:planning_done",
    "spec.py:_handle_session_prompt:permission_done",
    "spec.py:_handle_session_prompt:approved_done",
    "spec.py:_handle_session_prompt:outbound_error",
    "spec.py:_request_permission:pre_send",
    "spec.py:_emit_result_updates:plan",
    "spec.py:_emit_completion_message",
    "planning_loop.py:_invoke_planning_gateway",
    "planning_loop.py:execute_iteration",
)
# Cold reporters keep constant or two-string dict payloads (seam 4 A / 4 B contracts).
COLD = (
    "server.py:serve_ndjson:request_task_failed",
    "server.py:serve_ndjson:reader_incomplete",
)
MCP_REPORTER = "server.py:serve_ndjson:mcp_cleanup_incomplete"


def _source_tree(location):
    path = SOURCE_FOR_PREFIX[location.split(":")[0]]
    return path, ast.parse(path.read_text(encoding="utf-8"))


def _calls_for(tree, location):
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "acp_debug_log"
        and any(
            kw.arg == "location" and isinstance(kw.value, ast.Constant) and kw.value.value == location
            for kw in node.keywords
        )
    ]


def test_call_inventory_is_exactly_the_classified_sites():
    """Every production `acp_debug_log(location=...)` call is classified here, once."""
    found = set()
    for path in SOURCE_FOR_PREFIX.values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "acp_debug_log":
                [location] = [
                    kw.value.value for kw in node.keywords if kw.arg == "location" and isinstance(kw.value, ast.Constant)
                ]
                assert location not in found, f"duplicate location {location}"
                found.add(location)
    assert found == set(HOT) | set(WARM) | set(COLD) | {MCP_REPORTER}


def _diagnostic_statement(location):
    path, tree = _source_tree(location)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    calls = _calls_for(tree, location)
    assert len(calls) == 1, (location, len(calls))
    statement = parents[calls[0]]
    assert isinstance(statement, ast.Expr)
    parent = parents[statement]
    if isinstance(parent, ast.If) and ast.unparse(parent.test) == "debug_trace_enabled()":
        assert parent.body == [statement] and not parent.orelse
        statement = parent
    module = ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[]))
    return compile(module, str(path), "exec")


def _mcp_reporter():
    path, tree = _source_tree(MCP_REPORTER)
    [function] = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "report_mcp_cleanup_incomplete"
    ]
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    return compile(module, str(path), "exec")


class _DiagnosticInputRead(BaseException):
    """Raised on ANY inspection of an opaque input. BaseException: no boundary may absorb it."""


class _Opaque:
    """A diagnostic input whose every inspection is an error; identity and capture are free."""

    def __getattr__(self, name):
        raise _DiagnosticInputRead(f"attribute {name!r}")

    def __getitem__(self, key):
        raise _DiagnosticInputRead(f"item {key!r}")

    def __iter__(self):
        raise _DiagnosticInputRead("iteration")

    def __len__(self):
        raise _DiagnosticInputRead("len")

    def __contains__(self, item):
        raise _DiagnosticInputRead("contains")

    def __str__(self):
        raise _DiagnosticInputRead("str")

    def __bool__(self):
        raise _DiagnosticInputRead("bool")


class _NoPayloadReads(dict):
    def __missing__(self, key):
        if key.startswith("__") and key.endswith("__"):
            raise KeyError(key)  # interpreter/pytest probes (e.g. __tracebackhide__), not diagnostic reads
        raise _DiagnosticInputRead(f"unexpected name {key!r}")


# Every diagnostic input any classified site names. Opaque here; real-shaped below.
INPUT_NAMES = (
    "method", "params", "request_id", "message", "wire", "pending_permission_id", "operation_id", "exc",
    "notification", "session_id", "request", "run_id", "turn_seq", "planning_result", "permission_result",
    "approved_result", "turn", "result", "update_payload", "tool_call", "tool_call_id", "payload",
    "completed_plan", "message_payload", "self", "planning_turn", "wire_attempt",
)


def _opaque_namespace(sink):
    namespace = _NoPayloadReads(
        acp_debug_log=sink,
        debug_trace_enabled=debug_trace.debug_trace_enabled,
        __builtins__=__builtins__,
    )
    for name in INPUT_NAMES:
        namespace[name] = _Opaque()
    return namespace


def _real_namespace(sink):
    return dict(
        acp_debug_log=sink,
        debug_trace_enabled=debug_trace.debug_trace_enabled,
        method="session/prompt", request_id=7, pending_permission_id=None, operation_id="op-1",
        session_id="session-1", run_id="run-1", turn_seq=2,
        params={"z": 1, "a": 2}, message={"id": 7, "result": {"approved": True}},
        wire={"result": {"stopReason": "end_turn"}}, notification={"params": {"sessionId": "session-1"}},
        request={"id": 7}, exc=RuntimeError("harmless diagnostic"),
        planning_result=SimpleNamespace(
            status=SimpleNamespace(value="completed"), plan_hash="plan-1",
            tool_calls=[SimpleNamespace(tool_name="file_reader"), SimpleNamespace(tool_name="other")],
        ),
        permission_result={"outcome": "approved", "metadata": {"z": 1, "a": 2}},
        approved_result=SimpleNamespace(
            status=SimpleNamespace(value="completed"), mutation_count=1,
            tool_calls=[SimpleNamespace(tool_name="file_writer")],
        ),
        result=SimpleNamespace(run_id="run-1"), turn=SimpleNamespace(session_id="session-1"),
        update_payload={"update": {"entries": []}}, payload={"update": {"sessionUpdate": "tool_call", "status": "completed"}},
        tool_call=SimpleNamespace(tool_name="file_writer"), tool_call_id="tool-1",
        completed_plan={"update": {"entries": [{}]}}, message_payload={"update": {"sessionUpdate": "agent_message_chunk"}},
        self=SimpleNamespace(_run_id="run-1", _session_id="session-1"), planning_turn=1, wire_attempt=1,
    )


EXPECTED = {
    HOT[0]: {"method": "session/prompt", "param_keys": ["a", "z"]},
    HOT[1]: {"request_id": 7, "method": "session/prompt", "param_keys": ["a", "z"], "has_toolCall": False},
    HOT[2]: {"request_id": 7, "has_result": True, "has_error": False, "mapped_to_cancelled": False,
             "propagated_error": False, "result_keys": ["approved"]},
    HOT[3]: {"request_id": 7, "method": "session/prompt", "pending_permission_id": None, "operation_id": "op-1"},
    HOT[4]: {"request_id": 7, "method": "session/prompt", "has_error": False, "stop_reason": "end_turn"},
    HOT[5]: {"id": 7, "has_result": True, "has_error": False, "error": None, "result": {"approved": True}},
    HOT[6]: {"session_id": "session-1", "tool_call_id": "tool-1", "session_update": "tool_call",
             "tool_name": "file_writer", "status": "completed"},
    WARM[0]: {"request_id": 7, "method": "session/prompt", "pending_permission_id": None,
              "exception_type": "RuntimeError", "exception_message": "harmless diagnostic"},
    WARM[1]: {"session_id": "session-1"},
    WARM[2]: {"session_id": "session-1", "request_id": 7, "run_id": "run-1", "turn_seq": 2},
    WARM[3]: {"run_id": "run-1", "status": "completed", "plan_hash": "plan-1", "read_tool_calls": 1},
    WARM[4]: {"run_id": "run-1", "outcome": "approved", "has_metadata": True,
              "metadata_keys": ["a", "z"], "top_level_keys": ["metadata", "outcome"]},
    WARM[5]: {"run_id": "run-1", "status": "completed", "mutation_count": 1, "tool_call_count": 1,
              "tool_names": ["file_writer"]},
    WARM[6]: {"run_id": "run-1", "code": -32001, "message": "client rejected"},
    WARM[7]: {"session_id": "session-1", "run_id": "run-1", "param_keys": ["a", "z"], "has_toolCall": False},
    WARM[8]: {"session_id": "session-1", "update_keys": ["entries"], "has_entries": True},
    WARM[9]: {"session_id": "session-1", "plan_entry_count": 1, "message_preview": "done",
              "has_agent_message_chunk": True},
    WARM[10]: {"run_id": "run-1", "session_id": "session-1", "planning_turn": 1, "wire_attempt": 1,
               "error_type": "RuntimeError"},
    WARM[11]: {"run_id": "run-1", "session_id": "session-1", "stop_reason": "PLANNING_READ_FILE_NOT_FOUND",
               "rejected_path": "policy.txt", "start_byte": 0, "end_byte": 1024},
}
MESSAGES = {WARM[0]: "client request failed"}


def _site_namespace(location, sink):
    namespace = _real_namespace(sink)
    if location == WARM[6]:
        namespace["exc"] = SimpleNamespace(code=-32001, message="client rejected")
    elif location == WARM[9]:
        namespace["message"] = "done"
    elif location == WARM[11]:
        namespace["exc"] = SimpleNamespace(code="PLANNING_READ_FILE_NOT_FOUND")
        namespace["request"] = SimpleNamespace(path="policy.txt", start_byte=0, end_byte=1024)
    return namespace


# --------------------------------------------------------------------------------------
# Disabled: no diagnostic input is inspected; hot sites do not even reach the sink
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("enabled", [None, False], ids=["unset", "disabled"])
@pytest.mark.parametrize("location", HOT + WARM)
def test_disabled_trace_never_evaluates_migrated_payload(location, enabled, tmp_path):
    path = tmp_path / "disabled.ndjson"
    if enabled is not None:
        configure_debug_trace(enabled=enabled, log_path=path)
    try:
        exec(_diagnostic_statement(location), _opaque_namespace(debug_trace.acp_debug_log))
    except _DiagnosticInputRead as read:
        pytest.fail(f"{location}: disabled trace evaluated a diagnostic input: {read}")
    assert not path.exists()


@pytest.mark.parametrize("location", HOT)
def test_disabled_hot_path_does_not_even_call_sink(location, tmp_path):
    configure_debug_trace(enabled=False, log_path=tmp_path / "hot.ndjson")

    def unexpected_sink(**kwargs):
        pytest.fail(f"{location}: hot disabled path allocated and passed diagnostic arguments")

    try:
        exec(_diagnostic_statement(location), _opaque_namespace(unexpected_sink))
    except _DiagnosticInputRead as read:
        pytest.fail(f"{location}: disabled trace evaluated a diagnostic input: {read}")


def test_disabled_mcp_reporter_builds_no_fields(tmp_path):
    """Classification stays with the caller; the reporter's field reads are diagnostic-only."""
    configure_debug_trace(enabled=False, log_path=tmp_path / "mcp.ndjson")
    namespace = {"acp_debug_log": debug_trace.acp_debug_log, "MCPSupervisorState": MCPSupervisorState}
    exec(_mcp_reporter(), namespace)
    try:
        namespace["report_mcp_cleanup_incomplete"](_Opaque(), "incomplete")
    except _DiagnosticInputRead as read:
        pytest.fail(f"disabled trace read an MCP outcome field: {read}")
    assert not (tmp_path / "mcp.ndjson").exists()


# --------------------------------------------------------------------------------------
# Enabled: exactly the current fields, once; message adaptation for the exception site
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("location", HOT + WARM)
def test_enabled_diagnostics_preserve_payload_fields(location, tmp_path):
    path = tmp_path / "enabled.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    exec(_diagnostic_statement(location), _site_namespace(location, debug_trace.acp_debug_log))
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    assert records[0]["location"] == location
    assert records[0]["data"] == EXPECTED[location]
    if location in MESSAGES:
        assert records[0]["message"] == MESSAGES[location]


@pytest.mark.parametrize("location", HOT + WARM)
def test_enabled_supplier_is_invoked_exactly_once_per_site(location, tmp_path):
    path = tmp_path / "once.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    evaluations = []

    def counting_sink(**kwargs):
        # Transparent observer: the supplier is NOT evaluated here. An instrumented wrapper is
        # forwarded, so only the real sink's invocation (inside its enabled check and failure
        # boundary) is counted, and the recorded value is the one the sink consumed.
        data = kwargs.get("data")
        assert callable(data), f"{location}: payload must be a supplier, not an eager {type(data).__name__}"

        def instrumented():
            value = data()
            evaluations.append(value)
            return value

        return debug_trace.acp_debug_log(**{**kwargs, "data": instrumented})

    exec(_diagnostic_statement(location), _site_namespace(location, counting_sink))
    assert len(evaluations) == 1
    assert evaluations[0] == EXPECTED[location]
    [record] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert record["data"] == EXPECTED[location], "the sink wrote exactly the evaluation that was observed"


PARAMS_READING_SITES = (HOT[0], HOT[1], WARM[7])


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("location", PARAMS_READING_SITES)
def test_stateful_input_is_read_exactly_once_only_when_enabled_unobserved(location, enabled, tmp_path):
    """No observer at all: the production statement, the real sink, and an input that counts
    its own reads. Disabled: zero reads. Enabled: exactly one (a second evaluation cannot hide
    behind an idempotent dictionary)."""
    path = tmp_path / "stateful.ndjson"
    configure_debug_trace(enabled=enabled, log_path=path)
    params = _CountingParams()
    namespace = _site_namespace(location, debug_trace.acp_debug_log)
    namespace["params"] = params
    exec(_diagnostic_statement(location), namespace)
    assert params.key_reads == int(enabled)
    if enabled:
        [record] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert record["data"]["param_keys"] == ["a", "z"]
    else:
        assert not path.exists()


def test_exception_diagnostic_has_static_message_and_redacted_lazy_detail(tmp_path):
    path = tmp_path / "exception.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    namespace = _site_namespace(WARM[0], debug_trace.acp_debug_log)
    namespace["exc"] = RuntimeError("Authorization: Bearer " + "fixture-secret")
    exec(_diagnostic_statement(WARM[0]), namespace)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["message"] == "client request failed"
    assert record["data"]["exception_type"] == "RuntimeError"
    assert "exception_message" in record["data"]
    assert "fixture-secret" not in path.read_text(encoding="utf-8")


def test_enabled_mcp_reporter_fields_and_sentinels(tmp_path):
    path = tmp_path / "mcp.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    namespace = {"acp_debug_log": debug_trace.acp_debug_log, "MCPSupervisorState": MCPSupervisorState}
    exec(_mcp_reporter(), namespace)
    reporter = namespace["report_mcp_cleanup_incomplete"]
    outcome = SimpleNamespace(
        sdk_closed=True, endpoint_closed=False, supervisor_closed=False, supervisor_state=MCPSupervisorState.STOPPING
    )
    reporter(outcome, "incomplete")
    reporter(_Opaque(), "invalid")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["data"] for record in records] == [
        {"sdk_closed": True, "endpoint_closed": False, "supervisor_closed": False, "supervisor_state": "STOPPING"},
        {"sdk_closed": False, "endpoint_closed": False, "supervisor_closed": False, "supervisor_state": "unknown"},
    ]


def test_enabled_mcp_reporter_field_failure_is_contained(tmp_path):
    path = tmp_path / "mcp.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    namespace = {"acp_debug_log": debug_trace.acp_debug_log, "MCPSupervisorState": MCPSupervisorState}
    exec(_mcp_reporter(), namespace)

    class _Failing:
        def __getattr__(self, name):
            raise RuntimeError(f"field {name!r} unavailable")

    namespace["report_mcp_cleanup_incomplete"](_Failing(), "incomplete")  # must not raise
    assert not path.exists()


# --------------------------------------------------------------------------------------
# Real serving outcomes through production wiring
# --------------------------------------------------------------------------------------


class _CountingParams(dict):
    def __init__(self):
        super().__init__(z=1, a=2)
        self.key_reads = 0

    def keys(self):
        self.key_reads += 1
        return super().keys()


class _Writer:
    def __init__(self):
        self.messages = []

    async def write_line(self, message):
        self.messages.append(message)


@pytest.mark.parametrize("enabled", [False, True])
async def test_notification_preserves_wire_payload_and_only_inspects_keys_when_enabled(enabled, tmp_path):
    path = tmp_path / "notify.ndjson"
    configure_debug_trace(enabled=enabled, log_path=path)
    params, writer = _CountingParams(), _Writer()
    await NdjsonOutboundChannel(writer).notify("session/update", params)
    assert writer.messages == [{"jsonrpc": "2.0", "method": "session/update", "params": {"z": 1, "a": 2}}]
    assert params.key_reads == int(enabled)
    if enabled:
        assert json.loads(path.read_text(encoding="utf-8"))["data"] == {"method": "session/update", "param_keys": ["a", "z"]}
    else:
        assert not path.exists()


@pytest.mark.parametrize("enabled", [False, True])
async def test_request_and_response_preserve_future_settlement_and_lazy_keys(enabled, tmp_path):
    path = tmp_path / "request.ndjson"
    configure_debug_trace(enabled=enabled, log_path=path)
    params, result, writer = _CountingParams(), _CountingParams(), _Writer()
    channel = NdjsonOutboundChannel(writer)
    task = asyncio.create_task(channel.request("session/request_permission", params))
    try:
        await asyncio.sleep(0)
        assert writer.messages == [{"jsonrpc": "2.0", "id": 10000, "method": "session/request_permission", "params": params}]
        channel.deliver_client_response({"id": 10000, "result": result})
        assert await task is result
        assert params.key_reads == int(enabled)
        assert result.key_reads == int(enabled)
        if enabled:
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            assert records[0]["data"]["param_keys"] == ["a", "z"]
            assert records[1]["data"]["result_keys"] == ["a", "z"]
        else:
            assert not path.exists()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_channel_diagnostic_failure_does_not_disturb_settlement(tmp_path, monkeypatch):
    """A failing redaction on the enabled path leaves the request/response settlement intact."""
    configure_debug_trace(enabled=True, log_path=tmp_path / "broken.ndjson")

    def broken_redaction(value):
        raise RuntimeError("redaction blew up")

    monkeypatch.setattr(debug_trace, "redact_for_telemetry", broken_redaction)
    writer = _Writer()
    channel = NdjsonOutboundChannel(writer)
    await channel.notify("session/update", {"k": 1})
    task = asyncio.create_task(channel.request("session/request_permission", {"k": 1}))
    try:
        await asyncio.sleep(0)
        channel.deliver_client_response({"id": 10000, "result": {"approved": True}})
        assert await task == {"approved": True}
        assert [message.get("method") for message in writer.messages] == ["session/update", "session/request_permission"]
        assert not (tmp_path / "broken.ndjson").exists()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _broken_redaction(value):
    raise RuntimeError("redaction blew up")


def _supplier_breaker():
    """A sink wrapper that makes every supplier-shaped payload raise inside the real sink."""
    real = debug_trace.acp_debug_log

    def breaker(**kwargs):
        data = kwargs.get("data")
        if callable(data):
            def exploding():
                raise RuntimeError("supplier blew up")
            kwargs = {**kwargs, "data": exploding}
        return real(**kwargs)

    return breaker


def _apply_condition(condition, monkeypatch, tmp_path):
    path = tmp_path / f"{condition}.ndjson"
    if condition == "trace-unset":
        return path
    if condition == "trace-on":
        configure_debug_trace(enabled=True, log_path=path)
    elif condition == "redaction-fails":
        configure_debug_trace(enabled=True, log_path=path)
        monkeypatch.setattr(debug_trace, "redact_for_telemetry", _broken_redaction)
    elif condition == "supplier-fails":
        configure_debug_trace(enabled=True, log_path=path)
        breaker = _supplier_breaker()
        # server/spec bind the name at import; planning_loop and the sink module's own
        # helpers resolve it through the module at call time.
        monkeypatch.setattr(server_module, "acp_debug_log", breaker)
        monkeypatch.setattr("optimus.acp.spec.acp_debug_log", breaker)
        monkeypatch.setattr(debug_trace, "acp_debug_log", breaker)
    elif condition == "write-fails":
        path.mkdir()
        configure_debug_trace(enabled=True, log_path=path)
    else:  # pragma: no cover - test wiring
        raise AssertionError(condition)
    return path


CONDITIONS = ("trace-unset", "trace-on", "redaction-fails", "supplier-fails", "write-fails")


def _projection(messages):
    """Wire output projected onto its stable shape (session and tool-call ids are random)."""
    projected = []
    for message in messages:
        if "method" in message:
            update = (message.get("params") or {}).get("update") or {}
            projected.append(("notify" if "id" not in message else "request", message["method"], update.get("sessionUpdate")))
        elif "error" in message:
            projected.append(("error", message["id"], message["error"]["code"]))
        else:
            result = message.get("result") or {}
            projected.append(("result", message["id"], result.get("stopReason")))
    return projected


async def _full_session(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}},
                       "clientInfo": {"name": "zed", "version": "1.0.0"}},
        })
        await asyncio.wait_for(writer.wait_for_response(1), timeout=5)
        await reader.send({"jsonrpc": "2.0", "id": 2, "method": "session/new",
                           "params": {"cwd": str(tmp_path.resolve()), "mcpServers": []}})
        session_id = (await asyncio.wait_for(writer.wait_for_response(2), timeout=5))["result"]["sessionId"]
        await reader.send({"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
                           "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]}})
        permission_request = await asyncio.wait_for(writer.wait_for_request("session/request_permission"), timeout=5)
        plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]
        await reader.send({"jsonrpc": "2.0", "id": permission_request["id"],
                           "result": {"outcome": {"outcome": "selected", "optionId": "approve"},
                                      "metadata": {"approvalId": "approval-1", "planHash": plan_hash}}})
        prompt_response = await asyncio.wait_for(writer.wait_for_response(3), timeout=5)
        assert prompt_response["result"]["stopReason"] == "end_turn"
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)
    finally:
        if not serve_task.done():
            serve_task.cancel()
        await asyncio.gather(serve_task, return_exceptions=True)
    return _projection(writer.messages), configured.fake_gateway_call_count


@pytest.mark.parametrize("condition", CONDITIONS[1:])
async def test_full_session_wire_output_is_identical_under_diagnostic_failure(condition, tmp_path, monkeypatch):
    """Initialize -> session/new -> prompt -> permission -> end_turn: same wire shape, same settlement."""
    baseline, baseline_calls = await _full_session(tmp_path / "baseline")
    assert baseline_calls == 1
    assert ("result", 3, "end_turn") in baseline

    path = _apply_condition(condition, monkeypatch, tmp_path)
    projected, calls = await _full_session(tmp_path / condition)

    assert projected == baseline
    assert calls == 1
    if condition == "trace-on":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        locations = {record["location"] for record in records}
        expected = set(HOT) | {WARM[2], WARM[3], WARM[4], WARM[5], WARM[7], WARM[8], WARM[9]}
        assert expected <= locations, expected - locations
    elif condition == "write-fails":
        assert path.is_dir()
    else:
        assert not path.exists()


class _CapturingWriter:
    def __init__(self):
        self.messages = []

    async def write_line(self, message):
        self.messages.append(dict(message))


@pytest.mark.parametrize("condition", CONDITIONS)
async def test_request_exception_path_still_delivers_internal_error(condition, tmp_path, monkeypatch, capsys):
    """The exception site's diagnostic (now lazy and literal) cannot alter the error response."""
    path = _apply_condition(condition, monkeypatch, tmp_path)
    configured = configured_test_agent_server(tmp_path, output_text="unused")

    async def exploding(self, request, *, ownership_slot=None):
        raise RuntimeError("Authorization: Bearer " + "fixture-secret")

    monkeypatch.setattr(server_module.AcpDuplexAdapter, "handle_client_request", exploding)
    reader = StdioNdjsonLineReader(io.BytesIO(b'{"jsonrpc":"2.0","id":9,"method":"session/prompt","params":{}}\n'))
    writer = _CapturingWriter()
    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=5)

    [response] = [message for message in writer.messages if message.get("id") == 9]
    assert response["error"]["code"] == INTERNAL_ERROR
    assert "fixture-secret" not in json.dumps(writer.messages)
    stderr = capsys.readouterr().err
    assert "process_request failed id=9" in stderr
    assert "fixture-secret" not in stderr
    if condition == "trace-on":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        [record] = [record for record in records if record["location"] == WARM[0]]
        assert record["message"] == "client request failed"
        assert record["data"]["exception_type"] == "RuntimeError"
        assert record["data"]["request_id"] == 9
        assert "fixture-secret" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("condition", CONDITIONS)
async def test_teardown_outcomes_are_unchanged_under_diagnostic_failure(condition, tmp_path, monkeypatch):
    """Reader-incomplete teardown (seam 4 B / 5 real path) settles as cancelled whatever the diagnostics do."""
    from tests.unit.acp.test_server_mcp_shutdown import _drive_reader_incomplete, _NoneRuntime, _server

    _apply_condition(condition, monkeypatch, tmp_path)
    srv = _server(tmp_path, _NoneRuntime())
    outcome = await _drive_reader_incomplete(srv)
    assert outcome == "cancelled", f"{condition}: diagnostic behaviour changed the teardown outcome: {outcome!r}"


@pytest.mark.parametrize("condition", CONDITIONS)
def test_planning_read_rejection_outcome_is_unchanged_under_diagnostic_failure(condition, tmp_path, monkeypatch):
    from tests.unit.agent.test_planning_loop_runner import ScriptingGateway, _runner

    path = _apply_condition(condition, monkeypatch, tmp_path)
    gateway = ScriptingGateway([("OBSERVE: need policy\nREAD: policy.txt#bytes=0:1024\n", Decimal("0.001"), "gw-1")])
    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-read-reject", session_id="session-read-reject", task="Update target.py", initial_workspace_context=""
    )
    assert result.stop_reason == "PLANNING_READ_FILE_NOT_FOUND"
    assert "policy.txt" not in result.corrective_text
    if condition == "trace-on":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        [record] = [record for record in records if record["hypothesisId"] == "P9.87-READ-REJECT"]
        assert record["data"]["rejected_path"] == "policy.txt"
    elif condition != "write-fails":
        assert not path.exists()


@pytest.mark.parametrize("condition", CONDITIONS)
def test_planning_unknown_cost_outcome_is_unchanged_under_diagnostic_failure(condition, tmp_path, monkeypatch):
    from tests.unit.agent.test_planning_loop_runner import UnexpectedExceptionGateway, _runner

    path = _apply_condition(condition, monkeypatch, tmp_path)
    gateway = UnexpectedExceptionGateway()
    result = _runner(tmp_path, gateway=gateway).run(
        run_id="run-unexpected", session_id="session-unexpected", task="Update src/a.py", initial_workspace_context=""
    )
    assert gateway.attempts == 1
    assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
    assert result.unknown_cost_attempt_count == 1
    assert "SENTINEL-PAYLOAD-BUG" not in result.corrective_text
    if condition == "trace-on":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        [record] = [record for record in records if record["hypothesisId"] == "P9.95-USAGE-UNKNOWN"]
        assert record["data"]["error_type"] == "TypeError"
        assert "SENTINEL-PAYLOAD-BUG" not in json.dumps(record)
    elif condition != "write-fails":
        assert not path.exists()


def test_no_production_site_formats_its_message_dynamically():
    """Static companion to the ast-grep gate: every message keyword is literal string syntax."""
    for path in SOURCE_FOR_PREFIX.values():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "acp_debug_log":
                [message] = [kw.value for kw in node.keywords if kw.arg == "message"]
                assert isinstance(message, ast.Constant) and isinstance(message.value, str), (
                    f"{path.name}:{node.lineno}: message must be a string literal, got {ast.unparse(message)}"
                )
