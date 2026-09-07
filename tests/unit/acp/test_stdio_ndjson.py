from __future__ import annotations

import asyncio
import io
import json
import re
import sys

import pytest

from optimus.acp import errors, server
from optimus.acp.server import StdioNdjsonLineReader, StdioNdjsonLineWriter
from tests.integration.acp.test_server_stream import configured_test_agent_server


async def test_stdio_ndjson_line_reader_returns_bytes_and_detects_eof():
    stream = io.BytesIO(b'{"jsonrpc":"2.0","id":1}\n')
    reader = StdioNdjsonLineReader(stream)

    assert await reader.readline() == b'{"jsonrpc":"2.0","id":1}\n'
    assert await reader.readline() == b""


async def test_stdio_ndjson_line_writer_writes_bytes_to_bytesio():
    stream = io.BytesIO()
    writer = StdioNdjsonLineWriter(stream)

    await writer.write_line({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    stream.seek(0)
    assert stream.read() == b'{"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n'


async def test_handle_one_sanitizes_framing_error_in_encoded_response(monkeypatch) -> None:
    from optimus.acp.framing import FramingError

    async def failing_read_message(_reader):
        raise FramingError("OPTIMUS_API_KEY=top-secret-canary")

    class Writer:
        def __init__(self):
            self.payload = b""

        def write(self, payload):
            self.payload = payload

        async def drain(self):
            return None

    monkeypatch.setattr(server, "read_message", failing_read_message)
    writer = Writer()
    await server.AcpStreamServer().handle_one(object(), writer)
    body = json.loads(writer.payload.split(b"\r\n\r\n", 1)[1])
    assert body["error"]["code"] == -32700
    assert body["error"]["message"]
    assert "top-secret-canary" not in json.dumps(body)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_writer = Writer()
    await server.AcpStreamServer().handle_one(object(), failed_writer)
    failed_body = json.loads(failed_writer.payload.split(b"\r\n\r\n", 1)[1])
    assert failed_body["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_body)


async def test_serve_sanitizes_framing_error_before_loop_exit(monkeypatch) -> None:
    from optimus.acp.framing import FramingError

    calls = 0

    async def read_then_eof(_reader):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FramingError("OPTIMUS_API_KEY=top-secret-canary")
        raise FramingError("unexpected end of stream")

    class Writer:
        def __init__(self):
            self.payloads = []

        def write(self, payload):
            self.payloads.append(payload)

        async def drain(self):
            return None

    monkeypatch.setattr(server, "read_message", read_then_eof)
    writer = Writer()
    await server.AcpStreamServer().serve(object(), writer)
    body = json.loads(writer.payloads[0].split(b"\r\n\r\n", 1)[1])
    assert body["error"]["message"]
    assert "top-secret-canary" not in json.dumps(body)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_writer = Writer()
    calls = 0
    await server.AcpStreamServer().serve(object(), failed_writer)
    failed_body = json.loads(failed_writer.payloads[0].split(b"\r\n\r\n", 1)[1])
    assert failed_body["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_body)


async def test_serve_ndjson_exits_cleanly_on_byte_stream_eof(tmp_path):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b"")
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)


async def test_serve_ndjson_reports_invalid_json_to_stderr_and_exits(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    stream = io.BytesIO(b'{"token":"OPTIMUS_API_KEY=top-secret-canary"\n')
    reader = StdioNdjsonLineReader(stream)
    writer = _CapturingNdjsonWriter()

    await asyncio.wait_for(configured.server.serve_ndjson(reader, writer), timeout=1)

    stderr = capsys.readouterr().err
    assert "invalid ndjson line" in stderr
    assert "top-secret-canary" not in stderr

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_stream = io.BytesIO(b'{"token":"OPTIMUS_API_KEY=top-secret-canary"\n')
    await asyncio.wait_for(configured.server.serve_ndjson(StdioNdjsonLineReader(failed_stream), _CapturingNdjsonWriter()), timeout=1)
    failed_stderr = capsys.readouterr().err
    assert "internal error" in failed_stderr
    assert "top-secret-canary" not in failed_stderr


def test_protocol_error_data_redacts_nested_canary_and_drops_on_failure(monkeypatch) -> None:
    data = {"nested": {"message": "OPTIMUS_API_KEY=top-secret-canary"}}

    sanitized = errors.sanitize_protocol_error_data(data)
    assert "top-secret-canary" not in json.dumps(sanitized)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    assert errors.sanitize_protocol_error_data(data) is None


def test_protocol_error_message_redacts_canary_and_fails_safe(monkeypatch) -> None:
    canary = "OPTIMUS_API_KEY=top-secret-canary"

    assert "top-secret-canary" not in errors.sanitize_protocol_error_message(canary)
    assert errors.sanitize_protocol_error_message(canary)

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError(canary)))
    fallback = errors.sanitize_protocol_error_message(canary)
    assert fallback
    assert "top-secret-canary" not in fallback


async def test_serve_ndjson_sanitizes_request_processing_response_and_stderr(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")

    async def failing_handle_client_request(_self, _message, ownership_slot=None):
        del ownership_slot
        raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", failing_handle_client_request)

    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    async def request_error(request_id):
        reader, writer = InteractiveLineReader(), MemoryLineWriter()
        serving = None
        primary_error = None
        try:
            serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
            await reader.send({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt"})
            return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=2)
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            try:
                try:
                    reader.close()
                finally:
                    if serving is not None:
                        try:
                            done, _ = await asyncio.wait({serving}, timeout=2)
                            if done:
                                assert serving.result() is None
                        finally:
                            if not serving.done():
                                serving.cancel()
                                try:
                                    await asyncio.wait({serving}, timeout=2)
                                finally:
                                    cause = None
                                    if serving.done():
                                        state = "settled after cancellation"
                                        if not serving.cancelled():
                                            cause = serving.exception()
                                    else:
                                        state = "still pending after cancellation"
                                        serving.add_done_callback(
                                            lambda task: None if task.cancelled() else task.exception()
                                        )
                                    failure = AssertionError(f"serve_ndjson missed EOF deadline; {state}")
                                    if cause is None:
                                        raise failure
                                    raise failure from cause
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"EOF cleanup also failed: {type(cleanup_error).__name__}")

    response = await request_error(1)
    assert response["error"]["message"]
    assert "top-secret-canary" not in json.dumps(response)
    assert "top-secret-canary" not in capsys.readouterr().err

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    failed_response = await request_error(2)
    assert failed_response["error"]["message"] == "internal error"
    assert "top-secret-canary" not in json.dumps(failed_response)
    assert "top-secret-canary" not in capsys.readouterr().err


async def test_serve_ndjson_sanitizes_reader_failure_to_stderr(tmp_path, monkeypatch, capsys):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")

    class FailingReader:
        async def readline(self):
            raise RuntimeError("OPTIMUS_API_KEY=top-secret-canary")

    await asyncio.wait_for(configured.server.serve_ndjson(FailingReader(), _CapturingNdjsonWriter()), timeout=1)

    stderr = capsys.readouterr().err
    assert "ndjson reader failed" in stderr
    assert "top-secret-canary" not in stderr

    monkeypatch.setattr(errors, "sanitize_for_persistence", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("failure")))
    await asyncio.wait_for(configured.server.serve_ndjson(FailingReader(), _CapturingNdjsonWriter()), timeout=1)
    failed_stderr = capsys.readouterr().err
    assert "internal error" in failed_stderr
    assert "top-secret-canary" not in failed_stderr


class _CapturingNdjsonWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def write_line(self, message):
        self.messages.append(dict(message))


async def test_serve_ndjson_eof_cancels_pending_requests_and_closes_owned_state_once(tmp_path):
    """EOF must cancel tracked process_request tasks, close adapter/store once, then supervisor."""
    from unittest.mock import MagicMock

    from optimus.acp.dispatcher import JsonRpcDispatcher
    from optimus.acp.server import AcpStreamServer
    from optimus.guardrails.pre_tool import PreToolGuard
    from optimus.mcp.client_disposition import ClientMcpRuntime
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor

    workspace_root = tmp_path.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=workspace_root, allowed_network_hosts=())

    class SlowRunner:
        def run(self, request, **kwargs):
            import time

            time.sleep(5)
            raise AssertionError("should have been cancelled before completion")

    runner = SlowRunner()
    dispatcher = JsonRpcDispatcher(
        agent_runner=runner,
        pre_tool_guard=guard,
        workspace_root=workspace_root,
    )
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    close_counts = {"adapter": 0, "store": 0, "supervisor": 0}

    # Minimal runtime: disposition unused for empty mcpServers EOF path.
    runtime = MagicMock(spec=ClientMcpRuntime)
    runtime.supervisor = supervisor
    runtime.close = lambda: close_counts.__setitem__(
        "supervisor", close_counts["supervisor"] + 1
    ) or supervisor.close()

    server = AcpStreamServer(dispatcher=dispatcher, client_mcp_runtime=runtime)

    class SlowReader:
        def __init__(self) -> None:
            self._sent = False

        async def readline(self) -> bytes:
            if not self._sent:
                self._sent = True
                return (
                    b'{"jsonrpc":"2.0","id":1,"method":"session/new","params":{"cwd":"'
                    + str(workspace_root).replace("\\", "\\\\").encode()
                    + b'","mcpServers":[]}}\n'
                )
            await asyncio.sleep(0.05)
            return b""

    writer = _CapturingNdjsonWriter()

    async def _run():
        await asyncio.wait_for(server.serve_ndjson(SlowReader(), writer), timeout=2)

    await _run()
    # Supervisor/runtime close must happen exactly once on EOF teardown.
    assert close_counts["supervisor"] == 1


async def test_serve_ndjson_handler_exception_still_tears_down_owned_state(tmp_path, monkeypatch):
    configured = configured_test_agent_server(tmp_path, output_text="READ example.py\n")
    closes = {"n": 0}

    def tracking_close_all(self):
        closes["n"] += 1

    monkeypatch.setattr(server.AcpDuplexAdapter, "close_all", tracking_close_all)
    reader = StdioNdjsonLineReader(
        io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"session/prompt","params":{}}\n')
    )
    await asyncio.wait_for(configured.server.serve_ndjson(reader, _CapturingNdjsonWriter()), timeout=2)
    assert closes["n"] == 1


# --------------------------------------------------------------------------------------
# Seam 4 A (ported from sandbox tag `sandbox-seam4`, commit 0c718486): escaped request-task
# failures must be accounted for, once, under both schedules.
#
# An ordinary handler failure does NOT escape: the broad `except Exception` in
# `process_request` logs it, prints a sanitized stderr line and delivers an INTERNAL_ERROR
# response. What escapes:
#   A1 (still serving)  -- a failure delivering that error response, discarded by the
#                          done-callback (`request_tasks.discard`) without retrieval.
#   A2 (at shutdown)    -- cancellation cleanup itself raising, collected by the shutdown
#                          `gather(..., return_exceptions=True)` and then ignored.
#
# Adapted to main: main has no `acp.lifecycle` event stream, so "reporting precedes shutdown"
# is asserted via the still-running serve task rather than a `shutdown_begin` event, and the
# minted-id correlation reads main's own `process_request:entry` trace record.
# --------------------------------------------------------------------------------------

A_FAILURE_LOCATION = "server.py:serve_ndjson:request_task_failed"
A_FAILURE_DATA_KEYS = {"operation_id", "request_method"}
A_BOUND_SECONDS = 5.0
A_UNRETRIEVED = "Task exception was never retrieved"
_HEX32 = re.compile(r"\A[0-9a-f]{32}\Z")


@pytest.fixture
def seam4_trace(tmp_path):
    """Configure the process-local trace context and always reset it.

    The context is module state, so a test that fails mid-way would otherwise leak an enabled
    trace into every later test in the session. Reset happens in `finally`, after the yield.
    """
    from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context

    path = tmp_path / "seam4-trace.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


@pytest.fixture
def seam4_trace_off(tmp_path):
    """Trace explicitly disabled, with the same guaranteed reset."""
    from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context

    path = tmp_path / "seam4-trace-off.ndjson"
    configure_debug_trace(enabled=False, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


def _seam4_records(path):
    if not path.exists() or path.is_dir():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _seam4_failure_records(path):
    return [r for r in _seam4_records(path) if r.get("location") == A_FAILURE_LOCATION]


def _seam4_minted_by_method(path):
    """method -> operation_id, from `process_request:entry`, present for every request before

    its handler runs -- so it correlates the CancelledError path (A2) too.
    """
    found = {}
    for record in _seam4_records(path):
        if record.get("location") == "server.py:process_request:entry":
            found[record["data"]["method"]] = record["data"]["operation_id"]
    return found


async def _seam4_wait_for(predicate, timeout=A_BOUND_SECONDS):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()


async def _seam4_join_eof(reader, serve_task):
    """EOF must produce a NORMAL return. Bounded with `asyncio.wait`, never `wait_for`.

    `wait_for` would try to cancel a resisted serve task on timeout and then wait on that
    cancellation, which is itself unbounded; `asyncio.wait` neither cancels nor waits past its
    timeout. A pending task, a cancelled task, or a raised exception are each surfaced
    explicitly rather than hidden behind a fallback cancellation.
    """
    reader.close()
    _done, pending = await asyncio.wait({serve_task}, timeout=A_BOUND_SECONDS)
    if pending:
        pytest.fail("serve did not return after EOF within bound")
    if serve_task.cancelled():
        pytest.fail("normal EOF must return normally, not by cancellation")
    exc = serve_task.exception()
    if exc is not None:
        raise exc
    return serve_task.result()


async def _seam4_finally(reader, serve_task):
    """Tolerant `finally` cleanup that still refuses to lie.

    It must not mask a primary test failure already propagating, but absent one it must not
    return with the serve task still pending, nor silently drop an unexpected serve exception.
    """
    reader.close()
    _done, pending = await asyncio.wait({serve_task}, timeout=A_BOUND_SECONDS)
    if pending:
        serve_task.cancel()
        _done, pending = await asyncio.wait({serve_task}, timeout=A_BOUND_SECONDS)
    if sys.exc_info()[0] is not None:
        return  # a real failure is already propagating; do not mask it
    if pending:
        pytest.fail("cleanup left the serve task pending; it is resisting teardown")
    if not serve_task.cancelled() and serve_task.exception() is not None:
        raise serve_task.exception()


async def _seam4_wait_attempts(writer, at_least, timeout=A_BOUND_SECONDS):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if writer.attempts >= at_least:
            return True
        await asyncio.sleep(0.02)
    return writer.attempts >= at_least


class _ErrorDeliveryFailingWriter:
    """Records everything, but fails the error response so the failure escapes the error path."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.attempts = 0
        self._events: dict = {}

    async def write_line(self, message):
        self.attempts += 1
        if "error" in message:
            raise RuntimeError("error-response delivery failed")
        self.messages.append(dict(message))
        rid = message.get("id")
        if rid is not None:
            self._events.setdefault(rid, asyncio.Event()).set()

    async def wait_for_response(self, request_id, timeout=A_BOUND_SECONDS):
        async def _poll():
            while True:
                for message in self.messages:
                    if message.get("id") == request_id:
                        return message
                event = self._events.setdefault(request_id, asyncio.Event())
                event.clear()
                await event.wait()

        return await asyncio.wait_for(_poll(), timeout=timeout)


async def test_seam4_a1_delivery_failure_is_reported_once_before_shutdown(
    tmp_path, monkeypatch, caplog, seam4_trace
):
    """A1: a failure delivering the error response must be accounted for while still serving.

    Guards `task.add_done_callback(request_tasks.discard)`: a bare discard never retrieved the
    task's exception, so nothing observed the failure. Verifies it is reported.
    """
    import gc
    import logging

    from tests.integration.acp.test_server_stream import InteractiveLineReader

    trace_path = seam4_trace
    configured = configured_test_agent_server(tmp_path, output_text="done")

    both_in_flight = asyncio.Event()
    arrived = []

    async def barriered_exploding_handle(self, request, *, ownership_slot=None):
        arrived.append(request.get("method"))
        if len(arrived) >= 2:
            both_in_flight.set()
        await both_in_flight.wait()
        raise RuntimeError("handler failed")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", barriered_exploding_handle)

    reader, writer = InteractiveLineReader(), _ErrorDeliveryFailingWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        with caplog.at_level(logging.ERROR, logger="asyncio"):
            await reader.send({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}})
            await reader.send(
                {"jsonrpc": "2.0", "id": 3, "method": "session/new", "params": {"cwd": str(tmp_path)}}
            )

            minted_ok = await _seam4_wait_for(lambda: len(_seam4_minted_by_method(trace_path)) == 2)
            assert minted_ok, f"both requests must enter the error path (saw {_seam4_minted_by_method(trace_path)})"

            observed = await _seam4_wait_for(lambda: len(_seam4_failure_records(trace_path)) == 2)
            failures = _seam4_failure_records(trace_path)
            assert observed, (
                "escaped request-task failures were never reported while the server was still "
                f"serving; saw {len(failures)} of 2. The done-callback discards without retrieval."
            )

            assert not serve_task.done(), "reports must arrive while the server is still serving"
            assert writer.attempts == 2, (
                f"exactly one error-delivery attempt per request (2 total), saw {writer.attempts}"
            )

            minted = _seam4_minted_by_method(trace_path)
            for record in failures:
                assert set(record["data"]) == A_FAILURE_DATA_KEYS
                assert _HEX32.match(record["data"]["operation_id"]), (
                    "operation id must be a 32-char hex uuid, not a distinct-but-invalid placeholder"
                )
                method = record["data"]["request_method"]
                assert method in minted, f"unexpected method category {method!r}"
                assert record["data"]["operation_id"] == minted[method], (
                    f"report for {method!r} carried {record['data']['operation_id']!r}, but that "
                    f"request minted {minted[method]!r}: ids crossed or re-minted"
                )
            assert {r["data"]["request_method"] for r in failures} == {"initialize", "session/new"}
            assert len({r["data"]["operation_id"] for r in failures}) == 2, (
                "each request must report its OWN distinct operation id; a single id reused across "
                "both requests must fail here (the per-method mint map alone cannot catch that)"
            )

            await _seam4_join_eof(reader, serve_task)
            assert len(_seam4_failure_records(trace_path)) == 2, "shutdown must not re-report via gather"
            assert writer.attempts == 2, "shutdown must not add a delivery attempt"

            gc.collect()
            unretrieved = [r for r in caplog.records if A_UNRETRIEVED in r.getMessage()]
            assert unretrieved == [], (
                "the observer must RETRIEVE the escaped exception, not merely log alongside it; "
                f"asyncio still reported {len(unretrieved)} unretrieved task exception(s)"
            )
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a2_cancellation_cleanup_failure_is_reported_once(tmp_path, monkeypatch, seam4_trace):
    """A2: an ordinary exception from cancellation cleanup at shutdown must be reported once.

    Guards the shutdown `gather(..., return_exceptions=True)` path, whose collected failures were
    ignored. Armed only inside the target task; the outer shutdown loop cannot reach the bound turn.
    """
    from optimus.acp.lifecycle import TurnControl
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    trace_path = seam4_trace
    configured = configured_test_agent_server(tmp_path, output_text="done")

    real_handle = server.AcpDuplexAdapter.handle_client_request
    started = asyncio.Event()
    captured = {}

    async def prompt_binds_turn_then_blocks(self, request, *, ownership_slot=None):
        if request.get("method") != "session/prompt":
            return await real_handle(self, request, ownership_slot=ownership_slot)
        ownership_slot.bind_turn(TurnControl(session_id=request["params"]["sessionId"], turn_seq=1))
        captured["task"] = asyncio.current_task()
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", prompt_binds_turn_then_blocks)

    real_teardown = TurnControl.request_transport_teardown

    def failing_teardown(self):
        if asyncio.current_task() is captured.get("task"):
            raise RuntimeError("cancellation cleanup failed")
        return real_teardown(self)

    monkeypatch.setattr(TurnControl, "request_transport_teardown", failing_teardown)

    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 6, "method": "session/new", "params": {"cwd": str(tmp_path)}})
        session = await asyncio.wait_for(writer.wait_for_response(6), timeout=A_BOUND_SECONDS)
        assert "result" in session, f"session/new must succeed: {session}"

        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "session/prompt",
                "params": {"sessionId": session["result"]["sessionId"], "prompt": [{"type": "text", "text": "hold"}]},
            }
        )
        await asyncio.wait_for(started.wait(), timeout=A_BOUND_SECONDS)

        await _seam4_join_eof(reader, serve_task)

        observed = await _seam4_wait_for(lambda: len(_seam4_failure_records(trace_path)) == 1)
        failures = _seam4_failure_records(trace_path)
        assert observed, (
            "the exception from cancellation cleanup was never reported; the shutdown gather "
            f"collected it with return_exceptions=True and ignored it. Saw {len(failures)}."
        )
        assert set(failures[0]["data"]) == A_FAILURE_DATA_KEYS
        assert failures[0]["data"]["request_method"] == "session/prompt"
        minted = _seam4_minted_by_method(trace_path)
        assert _HEX32.match(failures[0]["data"]["operation_id"]), "operation_id must be 32-char hex"
        assert failures[0]["data"]["operation_id"] == minted["session/prompt"], (
            "the report must reuse the prompt request's minted operation_id"
        )
        assert captured["task"].cancelled() is False, (
            "cleanup raised an ordinary exception, so the task's final state is failed, not cancelled"
        )
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a_unknown_method_is_reported_as_unknown_never_raw(tmp_path, monkeypatch, seam4_trace):
    """An escaped failure on an unapproved method is reported, categorized "unknown",

    and must never echo the raw method string. Establishes the escape first (the delivery
    attempt), then requires the diagnostic -- not merely that nothing leaked.
    """
    from tests.integration.acp.test_server_stream import InteractiveLineReader

    trace_path = seam4_trace
    configured = configured_test_agent_server(tmp_path, output_text="done")
    secret_method = "danger/secret-method"  # pragma: allowlist secret

    async def failing_handle(self, request, *, ownership_slot=None):
        raise RuntimeError("handler failed")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", failing_handle)

    reader, writer = InteractiveLineReader(), _ErrorDeliveryFailingWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 12, "method": secret_method, "params": {}})
        established = await _seam4_wait_attempts(writer, 1)
        assert established, "the escape was never established: no error-delivery attempt occurred"

        observed = await _seam4_wait_for(lambda: len(_seam4_failure_records(trace_path)) == 1)
        failures = _seam4_failure_records(trace_path)
        assert observed, f"the escaped failure on an unapproved method was never reported (saw {len(failures)})"
        assert failures[0]["data"]["request_method"] == "unknown", "an unapproved method must map to 'unknown'"
        assert secret_method not in json.dumps(failures[0]), "the raw method must never appear in a report"

        await _seam4_join_eof(reader, serve_task)
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a_control_success_and_real_cancellation_produce_no_failure_report(
    tmp_path, monkeypatch, caplog, seam4_trace
):
    """A control: neither a successful request nor a genuinely cancelled one is a failure -- and

    classifying an ordinary cancellation must never raise into the loop. Removing the observer's
    `task.cancelled()` guard makes `task.exception()` raise on the cancelled task, which the event
    loop reports as "Exception in callback"; this control trips on that.
    """
    import logging

    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    trace_path = seam4_trace
    configured = configured_test_agent_server(tmp_path, output_text="done")

    real_handle = server.AcpDuplexAdapter.handle_client_request
    pending_started = asyncio.Event()
    cancellation_seen = asyncio.Event()
    captured = {}

    async def pending_for_prompt(self, request, *, ownership_slot=None):
        if request.get("method") != "session/prompt":
            return await real_handle(self, request, ownership_slot=ownership_slot)
        captured["task"] = asyncio.current_task()
        pending_started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancellation_seen.set()
            raise

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", pending_for_prompt)

    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 4, "method": "session/new", "params": {"cwd": str(tmp_path)}})
        session = await asyncio.wait_for(writer.wait_for_response(4), timeout=A_BOUND_SECONDS)
        assert "result" in session, f"the successful request must succeed: {session}"

        await reader.send(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "session/prompt",
                "params": {"sessionId": session["result"]["sessionId"], "prompt": [{"type": "text", "text": "hold"}]},
            }
        )
        await asyncio.wait_for(pending_started.wait(), timeout=A_BOUND_SECONDS)

        with caplog.at_level(logging.ERROR, logger="asyncio"):
            await _seam4_join_eof(reader, serve_task)

        assert cancellation_seen.is_set(), "the control never established cancellation"
        assert captured["task"].cancelled(), "the pending request task's final state must be cancelled"
        assert _seam4_failure_records(trace_path) == [], (
            "success and ordinary cancellation are not failures and must produce no diagnostic"
        )
        callback_errors = [r for r in caplog.records if "Exception in callback" in r.getMessage()]
        assert callback_errors == [], (
            "classifying the ordinary cancellation raised into the event loop; asyncio reported "
            f"{len(callback_errors)} callback exception(s)"
        )
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a_control_handled_error_with_successful_delivery_is_not_reported(
    tmp_path, monkeypatch, seam4_trace
):
    """A control: a handler error whose INTERNAL_ERROR response IS delivered is not an escape."""
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    trace_path = seam4_trace
    configured = configured_test_agent_server(tmp_path, output_text="done")

    async def failing_handle(self, request, *, ownership_slot=None):
        raise RuntimeError("handler failed")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", failing_handle)

    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 8, "method": "session/new", "params": {"cwd": str(tmp_path)}})
        response = await asyncio.wait_for(writer.wait_for_response(8), timeout=A_BOUND_SECONDS)
        assert "error" in response, f"the handled error must be delivered as an error response: {response}"

        await _seam4_join_eof(reader, serve_task)
        assert _seam4_failure_records(trace_path) == [], (
            "a handled error whose response was delivered must not be reported as an escaped failure"
        )
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a_control_one_escape_does_not_break_a_sibling(tmp_path, monkeypatch, seam4_trace):
    """A control (containment): an escaped failure must not strand or break a concurrent request."""
    from tests.integration.acp.test_server_stream import InteractiveLineReader

    configured = configured_test_agent_server(tmp_path, output_text="done")

    real_handle = server.AcpDuplexAdapter.handle_client_request

    async def fail_only_the_marked_session(self, request, *, ownership_slot=None):
        params = request.get("params") or {}
        if request.get("method") == "session/new" and params.get("cwd", "").endswith("boom"):
            raise RuntimeError("handler failed")
        return await real_handle(self, request, ownership_slot=ownership_slot)

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", fail_only_the_marked_session)

    reader, writer = InteractiveLineReader(), _ErrorDeliveryFailingWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        boom = tmp_path / "boom"
        boom.mkdir()
        await reader.send({"jsonrpc": "2.0", "id": 9, "method": "session/new", "params": {"cwd": str(boom)}})
        await reader.send({"jsonrpc": "2.0", "id": 10, "method": "session/new", "params": {"cwd": str(tmp_path)}})

        # Establish the escape, then require the sibling still completes and settles.
        assert await _seam4_wait_attempts(writer, 1), "the escape was never established"
        sibling = await asyncio.wait_for(writer.wait_for_response(10), timeout=A_BOUND_SECONDS)
        assert "result" in sibling, f"the sibling must complete despite the escape: {sibling}"

        await _seam4_join_eof(reader, serve_task)
    finally:
        await _seam4_finally(reader, serve_task)


async def test_seam4_a_control_trace_disabled_reports_without_leaking_raw_content(
    tmp_path, monkeypatch, capsys, seam4_trace_off
):
    """A control: with trace DISABLED, an established escape still yields a content-free stderr

    diagnostic -- so failures are not silently lost -- and never the raw exception content.
    """
    from tests.integration.acp.test_server_stream import InteractiveLineReader

    trace_path = seam4_trace_off
    configured = configured_test_agent_server(tmp_path, output_text="done")
    # A credential-shaped token: the sanitizer masks these, so a leak here is a real defect
    # rather than an artifact of arbitrary free text. (Content-free-ness of the seam-4 RECORD
    # itself is enforced structurally by A1's exact-keys assertion.)
    secret_pw = "SUPERSECRETpw"  # pragma: allowlist secret

    async def failing_handle(self, request, *, ownership_slot=None):
        raise RuntimeError(f"connect failed for https://user:{secret_pw}@host/db")

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", failing_handle)

    reader, writer = InteractiveLineReader(), _ErrorDeliveryFailingWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await reader.send({"jsonrpc": "2.0", "id": 11, "method": "session/new", "params": {"cwd": str(tmp_path)}})
        assert await _seam4_wait_attempts(writer, 1), "the escape was never established"
        await _seam4_join_eof(reader, serve_task)
    finally:
        await _seam4_finally(reader, serve_task)

    captured = capsys.readouterr()
    assert not trace_path.exists(), "no trace file may be written while debug trace is disabled"
    assert captured.err.strip(), "an established escape must still surface a stderr diagnostic when trace is off"
    assert secret_pw not in captured.out, "a credential must never reach stdout"
    assert secret_pw not in captured.err, "a credential must not reach stderr even with trace disabled"


async def test_seam4_a_control_diagnostic_sink_failure_does_not_break_processing(tmp_path, monkeypatch):
    """A control: the diagnostic sink itself failing must not strand a task or break a sibling.

    Distinct from A1's error-response delivery failure: here the trace sink cannot write at all
    (its path is a directory), so every diagnostic write fails. A concurrent success must still
    complete and the serve loop must still return normally.
    """
    from optimus.acp import debug_trace
    from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context
    from tests.integration.acp.test_server_stream import InteractiveLineReader

    sink_dir = tmp_path / "sink_is_a_dir"
    sink_dir.mkdir()  # opening this for append raises -> every diagnostic write fails
    configure_debug_trace(enabled=True, log_path=sink_dir)
    configured = configured_test_agent_server(tmp_path, output_text="done")

    # Spy on the sink so removing the observer is caught here too: the reporter must still be
    # INVOKED for the escaped failure even though the sink cannot persist it. Without this the
    # control only proves containment and survives an observer that never runs at all.
    reporter_calls = []
    reporter_reached = asyncio.Event()
    real_debug_log = debug_trace.acp_debug_log

    def spy_debug_log(**kwargs):
        if kwargs.get("location") == A_FAILURE_LOCATION:
            reporter_calls.append(kwargs.get("data"))
            reporter_reached.set()
        return real_debug_log(**kwargs)

    monkeypatch.setattr(server, "acp_debug_log", spy_debug_log)

    real_handle = server.AcpDuplexAdapter.handle_client_request
    # Deterministic barrier: both requests must be in flight before either resolves.
    both_in_flight = asyncio.Event()
    arrived = []

    async def fail_only_boom(self, request, *, ownership_slot=None):
        arrived.append(request.get("params", {}).get("cwd", ""))
        if len(arrived) >= 2:
            both_in_flight.set()
        await both_in_flight.wait()
        params = request.get("params") or {}
        if request.get("method") == "session/new" and params.get("cwd", "").endswith("boom"):
            raise RuntimeError("handler failed")
        # The sibling must remain ACTIVE across the reporter call: it does not complete until the
        # reporter has run for the escaped failure. So a reporter that cancels active siblings would
        # cancel THIS still-pending task before it can answer, and the response below never arrives.
        await reporter_reached.wait()
        return await real_handle(self, request, ownership_slot=ownership_slot)

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", fail_only_boom)

    reader, writer = InteractiveLineReader(), _ErrorDeliveryFailingWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        boom = tmp_path / "boom"
        boom.mkdir()
        await reader.send({"jsonrpc": "2.0", "id": 13, "method": "session/new", "params": {"cwd": str(boom)}})
        await reader.send({"jsonrpc": "2.0", "id": 14, "method": "session/new", "params": {"cwd": str(tmp_path)}})

        await asyncio.wait_for(both_in_flight.wait(), timeout=A_BOUND_SECONDS)  # concurrency established
        assert await _seam4_wait_attempts(writer, 1), "the escape was never established"
        await asyncio.wait_for(reporter_reached.wait(), timeout=A_BOUND_SECONDS)  # reporter has now run
        # The sibling was still pending when the reporter ran; it must survive and answer.
        sibling = await asyncio.wait_for(writer.wait_for_response(14), timeout=A_BOUND_SECONDS)
        assert "result" in sibling, f"a failing diagnostic sink must not break an active sibling: {sibling}"

        result = await _seam4_join_eof(reader, serve_task)
        assert result is None, "the serve loop must return normally despite the failing sink"
        assert reporter_calls, "the observer must still be invoked for the escape even when the sink fails"
    finally:
        await _seam4_finally(reader, serve_task)
        reset_debug_trace_context()


async def _seam4_drive_a2_escape(tmp_path, monkeypatch, reader, writer, serve_task):
    """Drive a cancellation-cleanup escape (A2 shape) and return once it has occurred.

    The escape path runs through the CancelledError branch, which -- unlike the handled-error
    branch -- prints nothing to stderr, so the observer's diagnostic is the ONLY stderr writer.
    """
    from optimus.acp.lifecycle import TurnControl

    real_handle = server.AcpDuplexAdapter.handle_client_request
    started = asyncio.Event()
    captured = {}

    async def prompt_binds_turn_then_blocks(self, request, *, ownership_slot=None):
        if request.get("method") != "session/prompt":
            return await real_handle(self, request, ownership_slot=ownership_slot)
        ownership_slot.bind_turn(TurnControl(session_id=request["params"]["sessionId"], turn_seq=1))
        captured["task"] = asyncio.current_task()
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", prompt_binds_turn_then_blocks)

    real_teardown = TurnControl.request_transport_teardown

    def failing_teardown(self):
        if asyncio.current_task() is captured.get("task"):
            raise RuntimeError("cancellation cleanup failed")
        return real_teardown(self)

    monkeypatch.setattr(TurnControl, "request_transport_teardown", failing_teardown)

    await reader.send({"jsonrpc": "2.0", "id": 20, "method": "session/new", "params": {"cwd": str(tmp_path)}})
    session = await asyncio.wait_for(writer.wait_for_response(20), timeout=A_BOUND_SECONDS)
    assert "result" in session, f"session/new must succeed: {session}"
    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "session/prompt",
            "params": {"sessionId": session["result"]["sessionId"], "prompt": [{"type": "text", "text": "hold"}]},
        }
    )
    await asyncio.wait_for(started.wait(), timeout=A_BOUND_SECONDS)
    return await _seam4_join_eof(reader, serve_task)  # EOF -> cancel -> cleanup raises -> escape


async def test_seam4_a2_escape_surfaces_content_free_stderr_when_trace_disabled(
    tmp_path, monkeypatch, capsys, seam4_trace_off
):
    """Isolates the observer's stderr diagnostic. RED if that stderr line is removed.

    The A2 (cancellation-cleanup) escape prints nothing to stderr on its own, so unlike A1 there
    is no pre-existing except-branch line to mask a missing observer diagnostic. With trace off,
    the observer's content-free stderr line is the only thing that keeps the failure from being
    silently lost -- so it must be present, and content-free.
    """
    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    trace_path = seam4_trace_off
    configured = configured_test_agent_server(tmp_path, output_text="done")

    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        await _seam4_drive_a2_escape(tmp_path, monkeypatch, reader, writer, serve_task)
    finally:
        await _seam4_finally(reader, serve_task)

    captured = capsys.readouterr()
    assert not trace_path.exists(), "no trace file may be written while debug trace is disabled"
    assert "request task failed" in captured.err, (
        "with trace off, the observer must still surface the escaped failure on stderr; "
        f"none seen (stderr={captured.err!r})"
    )
    assert "method=session/prompt" in captured.err, "the content-free diagnostic must carry the approved category"
    assert "cancellation cleanup failed" not in captured.err, "the raw exception message must never be echoed"
    assert "traceback" not in captured.err.lower(), "no traceback content in the diagnostic"


async def test_seam4_reporter_contains_a_failing_stderr_write(
    tmp_path, monkeypatch, caplog, seam4_trace_off
):
    """The observer must never raise into the loop. RED if the reporter's containment is removed.

    Trace is off, so the observer takes its stderr path; stderr is replaced with a writer that
    raises. The reporter must swallow that failure -- the serve loop returns normally and asyncio
    logs no "Exception in callback".
    """
    import logging

    from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter

    configured = configured_test_agent_server(tmp_path, output_text="done")

    class _FailingStderr:
        def write(self, *_a, **_k):
            raise RuntimeError("stderr is broken")

        def flush(self, *_a, **_k):
            raise RuntimeError("stderr is broken")

    monkeypatch.setattr(sys, "stderr", _FailingStderr())

    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serve_task = asyncio.create_task(configured.server.serve_ndjson(reader, writer))
    try:
        with caplog.at_level(logging.ERROR, logger="asyncio"):
            result = await _seam4_drive_a2_escape(tmp_path, monkeypatch, reader, writer, serve_task)
            assert result is None, "a failing stderr diagnostic must not stop the serve loop returning"
            callback_errors = [r for r in caplog.records if "Exception in callback" in r.getMessage()]
            assert callback_errors == [], (
                "the observer raised into the event loop instead of containing the stderr failure; "
                f"asyncio reported {len(callback_errors)} callback exception(s)"
            )
    finally:
        await _seam4_finally(reader, serve_task)
