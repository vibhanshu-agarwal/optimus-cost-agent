"""Seam 2, checkpoint B: the serving lifecycle retains and closes the Redis runtime.

`serve_ndjson` (and the framed `serve`) close the retained `RedisRuntime` as the LAST
teardown stage, after the adapter, the client-MCP runtime, the owned writer and the reader
decision. The stage is observed asynchronously -- the ACP event loop is never blocked on a
thread join -- and its outcome is consumed: a clean record reports nothing; an incomplete
or failed teardown produces exactly one content-free diagnostic at
`server.py:serve_ndjson:redis_cleanup_incomplete` and never raises out of `finally`, so
the initiating cancellation or exception is preserved. A late runner submission after
admission closed receives a stable closed error and nothing is reopened.

Runtimes here are REAL `RedisRuntime` objects on real `RedisLoopOwner` threads; only the
pool and client are counting fakes, so the counts prove once-only resource closes.
"""

from __future__ import annotations

import asyncio
import io
import json
import threading

import pytest

from optimus.acp import server
from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context
from optimus.acp.server import StdioNdjsonLineReader
from optimus.redis import async_bridge
from optimus.redis.async_bridge import RedisLoopOwner, RedisLoopOwnerClosed
from optimus.redis.runtime import RedisRuntime, RedisRuntimeState
from tests.unit.acp.test_server_mcp_shutdown import (
    _CapturingWriter,
    _drive_eof,
    _drive_reader_incomplete,
    _Observed,
    _PhysicalWriter,
    _records,
    _server,
)

REDIS_INCOMPLETE_LOCATION = "server.py:serve_ndjson:redis_cleanup_incomplete"
BOUND_SECONDS = 5.0


@pytest.fixture
def redis_trace(tmp_path):
    path = tmp_path / "seam2b-trace.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


def _redis_records(path):
    return [r for r in _records(path) if r.get("location") == REDIS_INCOMPLETE_LOCATION]


class _CountingResource:
    def __init__(self, *, error: BaseException | None = None) -> None:
        self.count = 0
        self.threads: list[int] = []
        self.error = error

    async def aclose(self) -> None:
        self.count += 1
        self.threads.append(threading.get_ident())
        if self.error is not None:
            raise self.error


class _BlockedClient(_CountingResource):
    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    async def aclose(self) -> None:
        self.count += 1
        self.threads.append(threading.get_ident())
        while not self.release.is_set():
            try:
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                pass


def _runtime(client=None, pool=None) -> RedisRuntime:
    return RedisRuntime(
        pool=pool or _CountingResource(),
        client=client if client is not None else _CountingResource(),
        owner=RedisLoopOwner(name="seam2b-serving-owner"),
    )


class _RedisObserved(_Observed):
    """Adds the Redis stage and its diagnostic to the observed teardown sequence."""

    def __init__(self, monkeypatch) -> None:
        super().__init__(monkeypatch)
        observed = self
        real_close_async = RedisRuntime.close_async

        async def spy_close_async(inner_self, *, timeout=None):
            observed.sequence.append("redis_close")
            return await real_close_async(inner_self, timeout=timeout)

        monkeypatch.setattr(RedisRuntime, "close_async", spy_close_async)
        real_debug_log = server.acp_debug_log

        def spy_debug_log(**kwargs):
            if kwargs.get("location") == REDIS_INCOMPLETE_LOCATION:
                observed.sequence.append("redis_incomplete")
            return real_debug_log(**kwargs)

        monkeypatch.setattr(server, "acp_debug_log", spy_debug_log)


def _redis_server(tmp_path, runtime, mcp_runtime=None):
    base = _server(tmp_path, mcp_runtime)
    return server.AcpStreamServer(
        dispatcher=base._dispatcher, client_mcp_runtime=mcp_runtime, redis_runtime=runtime  # noqa: SLF001
    )


# --------------------------------------------------------------------------------------
# Normal serving teardown
# --------------------------------------------------------------------------------------


async def test_eof_teardown_closes_the_retained_runtime_last_and_exactly_once(tmp_path, monkeypatch, redis_trace):
    """MUTATION: retained close handle dropped; MUTATION: duplicate close."""
    observed = _RedisObserved(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)

    await _drive_eof(srv, writer=_PhysicalWriter())

    assert observed.sequence == ["close_all", "writer", "redis_close"], observed.sequence
    assert runtime.state is RedisRuntimeState.CLOSED
    assert runtime.teardown_record is not None and runtime.teardown_record.is_clean
    assert client.count == 1 and pool.count == 1
    assert client.threads == [runtime.owner.thread.ident]
    assert runtime.owner.is_terminated
    assert _redis_records(redis_trace) == []
    assert async_bridge._shared_tool_owner is None


async def test_the_event_loop_is_not_blocked_while_the_runtime_tears_down(tmp_path, monkeypatch):
    """MUTATION: cleanup observed by blocking the serving loop."""
    client = _BlockedClient()
    runtime = _runtime(client)
    srv = _redis_server(tmp_path, runtime)
    ticks = 0

    async def _tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    ticker = asyncio.create_task(_tick())
    serve_task = asyncio.create_task(srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), _CapturingWriter()))
    try:
        await asyncio.sleep(0.3)
        assert not serve_task.done(), "teardown returned while the client close was still parked"
        ticks_during = ticks
        assert ticks_during >= 10, f"the loop stalled during the Redis stage: {ticks_during} ticks"
        client.release.set()
        _done, pending = await asyncio.wait({serve_task}, timeout=BOUND_SECONDS)
        assert not pending
        assert serve_task.exception() is None
    finally:
        client.release.set()
        ticker.cancel()
        if not serve_task.done():
            serve_task.cancel()
            await asyncio.wait({serve_task}, timeout=BOUND_SECONDS)
    assert runtime.state is RedisRuntimeState.CLOSED


async def test_cancellation_teardown_still_closes_the_runtime_after_the_reader_decision(
    tmp_path, monkeypatch, redis_trace
):
    observed = _RedisObserved(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    runtime = _runtime()
    srv = _redis_server(tmp_path, runtime)

    outcome = await _drive_reader_incomplete(srv, writer=_PhysicalWriter())

    assert outcome == "cancelled", outcome
    assert observed.sequence == ["close_all", "writer", "reader_incomplete", "redis_close"], observed.sequence
    assert runtime.state is RedisRuntimeState.CLOSED
    assert _redis_records(redis_trace) == []


async def test_an_absent_runtime_reports_nothing(tmp_path, monkeypatch, redis_trace):
    observed = _RedisObserved(monkeypatch)
    srv = _redis_server(tmp_path, None)
    await _drive_eof(srv)
    assert "redis_close" not in observed.sequence
    assert _redis_records(redis_trace) == []


# --------------------------------------------------------------------------------------
# Incomplete or failed Redis teardown: reported once, never masking the initiator
# --------------------------------------------------------------------------------------


async def test_an_incomplete_teardown_reports_once_retains_ownership_and_returns_normally(
    tmp_path, monkeypatch, redis_trace
):
    """MUTATION: false clean outcome with a live thread."""
    monkeypatch.setattr(server, "REDIS_SHUTDOWN_OBSERVATION_SECONDS", 0.2)
    client = _BlockedClient()
    runtime = _runtime(client)
    srv = _redis_server(tmp_path, runtime)
    try:
        await _drive_eof(srv)
        records = _redis_records(redis_trace)
        assert len(records) == 1
        assert records[0]["data"] == {
            "state": "CLOSING",
            "outcome": "incomplete",
            "client": "not_attempted",
            "pool": "not_attempted",
            "owner_terminated": False,
            "admitted_work_settled": True,
        }
        assert runtime.state is RedisRuntimeState.CLOSING
        assert runtime.owner.thread_is_alive
    finally:
        client.release.set()
        record = await asyncio.to_thread(runtime.close, timeout=BOUND_SECONDS)
    assert record.is_clean
    assert client.count == 1


async def test_a_failed_resource_stage_is_reported_and_the_teardown_returns_normally(
    tmp_path, monkeypatch, redis_trace
):
    client = _CountingResource(error=RuntimeError("client close failed"))
    pool = _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)

    await _drive_eof(srv)

    records = _redis_records(redis_trace)
    assert len(records) == 1
    assert records[0]["data"] == {
        "state": "CLOSED",
        "outcome": "failed",
        "client": "failed",
        "pool": "returned",
        "owner_terminated": True,
        "admitted_work_settled": True,
    }
    assert pool.count == 1, "pool cleanup was skipped after an ordinary client failure"
    assert runtime.state is RedisRuntimeState.CLOSED


async def test_a_redis_failure_does_not_mask_the_initiating_cancellation(tmp_path, monkeypatch, redis_trace):
    client = _CountingResource(error=RuntimeError("client close failed"))
    runtime = _runtime(client)
    srv = _redis_server(tmp_path, runtime)

    outcome = await _drive_reader_incomplete(srv)

    assert outcome == "cancelled", outcome
    assert len(_redis_records(redis_trace)) == 1


async def test_a_redis_failure_does_not_skip_or_reorder_the_earlier_stages(tmp_path, monkeypatch, redis_trace):
    from optimus.mcp.client_disposition import ClientMcpRuntime
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor

    observed = _RedisObserved(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    sup = MCPAsyncSupervisor()
    sup.start()

    class _Sdk:
        def close_all(self):
            return None

    mcp = ClientMcpRuntime(disposition=object(), supervisor=sup, sdk_adapter=_Sdk())
    runtime = _runtime(_CountingResource(error=RuntimeError("client close failed")))
    srv = _redis_server(tmp_path, runtime, mcp_runtime=observed.wrap_runtime(mcp))

    await _drive_eof(srv, writer=_PhysicalWriter())

    assert observed.sequence == ["close_all", "mcp_close", "writer", "redis_close", "redis_incomplete"], (
        observed.sequence
    )


# --------------------------------------------------------------------------------------
# Late worker submissions after admission closed
# --------------------------------------------------------------------------------------


async def test_a_late_worker_submission_after_teardown_gets_a_stable_closed_error_and_reopens_nothing(
    tmp_path, monkeypatch
):
    """MUTATION: replacement owner after admission closes, from the serving side."""
    runtime = _runtime()
    owner = runtime.owner
    store = runtime.sync_state_store()
    srv = _redis_server(tmp_path, runtime)
    await _drive_eof(srv)

    async def _late():  # pragma: no cover - must never be entered
        raise AssertionError("work was admitted after serving teardown")

    def _worker():
        return store.submit(lambda: _late())

    with pytest.raises(RedisLoopOwnerClosed):
        await asyncio.to_thread(_worker)
    assert runtime.owner is owner and owner.is_terminated
    assert async_bridge._shared_tool_owner is None
    assert runtime.state is RedisRuntimeState.CLOSED


# --------------------------------------------------------------------------------------
# Framed transport keeps the same custody
# --------------------------------------------------------------------------------------


async def test_the_framed_serve_loop_also_closes_the_retained_runtime(tmp_path, monkeypatch):
    from tests.integration.acp.test_server_stream import MemoryReader, MemoryWriter

    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)

    await srv.serve(MemoryReader([]), MemoryWriter())

    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1


def test_the_redis_diagnostic_payload_is_content_free():
    payload = server.redis_cleanup_payload
    assert callable(payload)
    text = json.dumps(payload(None))
    assert set(json.loads(text)) == {"state", "outcome", "client", "pool", "owner_terminated", "admitted_work_settled"}


# --------------------------------------------------------------------------------------
# R1: custody protection spans the WHOLE serving lifetime -- setup and earlier cleanup
# --------------------------------------------------------------------------------------


async def test_a_setup_failure_after_the_handoff_still_closes_the_runtime(tmp_path, monkeypatch):
    """R1 MUTATION: adapter construction fails before the serving try; Redis must still close."""
    from optimus.acp import spec

    def _boom(*args, **kwargs):
        raise ValueError("adapter construction fault")

    monkeypatch.setattr(spec.AcpDuplexAdapter, "__init__", _boom)
    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)

    with pytest.raises(ValueError, match="adapter construction fault"):
        await srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), _CapturingWriter())
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


async def test_an_earlier_cleanup_stage_failure_still_closes_the_runtime_and_keeps_its_error(
    tmp_path, monkeypatch
):
    """R1 MUTATION: adapter.close_all raises inside teardown; Redis closes and the error survives."""
    from optimus.acp import spec

    def _boom(self):
        raise ValueError("adapter close fault")

    monkeypatch.setattr(spec.AcpDuplexAdapter, "close_all", _boom)
    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)

    with pytest.raises(ValueError, match="adapter close fault"):
        await srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), _CapturingWriter())
    assert runtime.state is RedisRuntimeState.CLOSED
    assert client.count == 1 and pool.count == 1
    assert runtime.owner.is_terminated


async def test_a_failing_mcp_stage_does_not_strand_the_runtime(tmp_path, monkeypatch):
    class _McpRuntime:
        def close(self):
            raise RuntimeError("mcp close fault")

    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime, mcp_runtime=_McpRuntime())
    with pytest.raises(RuntimeError, match="mcp close fault"):
        await srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), _CapturingWriter())
    assert runtime.state is RedisRuntimeState.CLOSED and client.count == 1 and pool.count == 1


async def test_the_framed_serve_loop_closes_the_runtime_when_setup_fails(tmp_path, monkeypatch):
    from optimus.acp import server as server_module

    def _boom(reader):
        raise ValueError("framed setup fault")

    monkeypatch.setattr(server_module, "read_message", _boom)
    from tests.integration.acp.test_server_stream import MemoryReader, MemoryWriter

    client, pool = _CountingResource(), _CountingResource()
    runtime = _runtime(client, pool)
    srv = _redis_server(tmp_path, runtime)
    with pytest.raises(ValueError, match="framed setup fault"):
        await srv.serve(MemoryReader([b"x"]), MemoryWriter())
    assert runtime.state is RedisRuntimeState.CLOSED and client.count == 1 and pool.count == 1
