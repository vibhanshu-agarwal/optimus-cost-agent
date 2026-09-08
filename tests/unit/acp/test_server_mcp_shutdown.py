"""Seam 5: the server consumes the client-MCP shutdown outcome and reports incomplete cleanup.

`serve_ndjson` closes the client-MCP runtime inside its teardown. Before this seam the return
value was discarded, so a runtime whose supervisor was still draining -- or whose SDK stage
had raised and been contained -- was indistinguishable from a clean one. Now the outcome is
consumed: only an ABSENT runtime is an implicit clean/no-resource case; a present runtime must
return a `ClientMcpShutdownOutcome` whose `complete` is true, and anything else (a non-complete
outcome, `None`, a foreign object) produces exactly one content-free diagnostic at
`server.py:serve_ndjson:mcp_cleanup_incomplete`.

Adapted to main from sandbox tag `sandbox-seam5` (commit 0071b424). Main has no lifecycle event
stream, no `shutdown_complete` event and no Redis-runtime teardown member, so the port proves
the runtime's explicit result and the server's reporting of a non-clean result -- not a gated
completion event. The diagnostic is made right after the runtime close, so it is attempted
whenever the runtime returned; the existing order (adapter, MCP runtime, owned writer, reader
decision) is preserved and observed with forwarding spies.

Ownership claims use a REAL `MCPAsyncSupervisor` whose owner thread is held inside acknowledged
cancellation cleanup; an outstanding physical read uses a REAL OS pipe under the real
`StdioNdjsonLineReader`. Doubles are used only to inject a stage exception or to return an
invalid result. Every held worker is released in `finally`, joins are checked, and a finished
serve task's exception is always retrieved.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import threading
from dataclasses import dataclass

import pytest

from optimus.acp import server
from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context
from optimus.acp.outbound_writer import DedicatedOutboundWriter
from optimus.acp.server import StdioNdjsonLineReader
from optimus.mcp.client_disposition import ClientMcpRuntime, ClientMcpShutdownOutcome
from optimus.mcp.client_supervisor import MCPAsyncSupervisor, MCPSupervisorError, MCPSupervisorState
from tests.integration.acp.test_server_stream import configured_test_agent_server

BOUND_SECONDS = 5.0
HELD_JOIN_BUDGET_SECONDS = 0.05

MCP_INCOMPLETE_LOCATION = "server.py:serve_ndjson:mcp_cleanup_incomplete"
READER_INCOMPLETE_LOCATION = "server.py:serve_ndjson:reader_incomplete"

# The only payload shapes the diagnostic may carry: three stage booleans plus a real
# supervisor state value, or the fixed sentinel payload for an invalid/foreign result.
SENTINEL_PAYLOAD = {
    "sdk_closed": False,
    "endpoint_closed": False,
    "supervisor_closed": False,
    "supervisor_state": "unknown",
}


# --------------------------------------------------------------------------------------
# Trace fixtures
# --------------------------------------------------------------------------------------


@pytest.fixture
def mcp_trace(tmp_path):
    path = tmp_path / "seam5-trace.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


@pytest.fixture
def mcp_trace_off(tmp_path):
    path = tmp_path / "seam5-trace-off.ndjson"
    configure_debug_trace(enabled=False, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


def _records(path):
    if not path.exists() or path.is_dir():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _mcp_records(path):
    return [r for r in _records(path) if r.get("location") == MCP_INCOMPLETE_LOCATION]


def _reader_records(path):
    return [r for r in _records(path) if r.get("location") == READER_INCOMPLETE_LOCATION]


# --------------------------------------------------------------------------------------
# Runtime doubles (stage injection only) and the real held supervisor
# --------------------------------------------------------------------------------------


class _SdkAdapter:
    """Unrelated-resource double: injects an ordinary SDK stage failure on request."""

    def __init__(self, *, raise_on_close: bool = False) -> None:
        self._raise_on_close = raise_on_close

    def close_all(self) -> None:
        if self._raise_on_close:
            raise RuntimeError("sdk close failed")


@dataclass
class _HeldSupervisor:
    """A real supervisor whose owner thread is held inside acknowledged cancellation cleanup."""

    supervisor: MCPAsyncSupervisor
    owner: threading.Thread
    worker: threading.Thread
    release: threading.Event
    worker_outcome: list

    def finish(self) -> None:
        """Release the held cleanup, join everything, finalize, and check the joins."""
        self.release.set()
        self.worker.join(BOUND_SECONDS)
        self.owner.join(BOUND_SECONDS)
        self.supervisor.close()
        assert not self.worker.is_alive(), "the submitting worker did not return"
        assert not self.owner.is_alive(), "the owner thread did not terminate after release"
        assert self.worker_outcome == ["SUBMIT_TIMEOUT"], self.worker_outcome
        assert self.supervisor.state is MCPSupervisorState.DEAD


def _start_held_supervisor() -> _HeldSupervisor:
    started = threading.Event()
    cleanup_entered = threading.Event()
    release = threading.Event()
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=HELD_JOIN_BUDGET_SECONDS)
    sup.start()
    owner = sup._thread  # noqa: SLF001
    assert owner is not None

    async def op() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup_entered.set()
            release.wait(timeout=30)
            raise

    worker_outcome: list = []

    def worker() -> None:
        try:
            sup.submit(op(), timeout_seconds=HELD_JOIN_BUDGET_SECONDS)  # the timeout cancels op
            worker_outcome.append("UNEXPECTED-RETURN")
        except MCPSupervisorError as exc:
            worker_outcome.append(exc.code)
        except BaseException as exc:  # noqa: BLE001 - recorded, asserted by finish()
            worker_outcome.append(exc)

    w = threading.Thread(target=worker, name="seam5-held-submit")
    w.start()
    try:
        assert started.wait(BOUND_SECONDS), "held op never started"
        # The acknowledgement arrives BEFORE the server teardown is driven.
        assert cleanup_entered.wait(BOUND_SECONDS), "cancellation cleanup was not acknowledged"
    except BaseException:
        release.set()
        w.join(BOUND_SECONDS)
        sup.close()
        raise
    return _HeldSupervisor(sup, owner, w, release, worker_outcome)


def _clean_runtime() -> ClientMcpRuntime:
    sup = MCPAsyncSupervisor()  # default budget; nothing is held, so it reaches DEAD
    sup.start()
    return ClientMcpRuntime(disposition=object(), supervisor=sup, sdk_adapter=_SdkAdapter())


# --------------------------------------------------------------------------------------
# Observation: forwarding spies for the teardown sequence and the diagnostic attempts
# --------------------------------------------------------------------------------------


_UNEVALUATED = object()


class _Attempt:
    """One reporting attempt, observed transparently.

    Seam 1 made the reporter's field reads lazy: the sink receives a zero-argument supplier
    and evaluates it inside its own failure boundary, only with tracing enabled. The spy
    must not evaluate that supplier itself (that would add an evaluation outside the sink's
    enabled check and boundary). Instead it forwards an INSTRUMENTED supplier: when -- and
    only when -- the real sink invokes it, the value or the failure is recorded here, the
    same value is returned, and every exception propagates unchanged. A disabled attempt
    therefore stays unevaluated, which is itself asserted below.
    """

    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.evaluations = 0
        self.value = _UNEVALUATED
        self.failure: BaseException | None = None

    def instrumented(self):
        original = self.kwargs.get("data")
        if not callable(original):
            return original

        def supplier():
            self.evaluations += 1
            try:
                value = original()
            except BaseException as failure:
                self.failure = failure
                raise
            self.value = value
            return value

        return supplier

    @property
    def unevaluated(self) -> bool:
        return self.evaluations == 0

    @property
    def payload(self):
        assert self.evaluations == 1, f"expected exactly one supplier evaluation, saw {self.evaluations}"
        assert self.failure is None, f"the supplier failed: {self.failure!r}"
        return self.value


class _Observed:
    """Records the real teardown sequence and every diagnostic ATTEMPT (not just disk)."""

    def __init__(self, monkeypatch) -> None:
        self.sequence: list[str] = []
        self.mcp_attempts: list[dict] = []
        self.returned_outcomes: list[object] = []

        real_close_all = server.AcpDuplexAdapter.close_all

        def spy_close_all(inner_self):
            self.sequence.append("close_all")
            return real_close_all(inner_self)

        monkeypatch.setattr(server.AcpDuplexAdapter, "close_all", spy_close_all)

        real_debug_log = server.acp_debug_log

        def spy_debug_log(**kwargs):
            location = kwargs.get("location")
            if location == MCP_INCOMPLETE_LOCATION:
                self.sequence.append("mcp_incomplete")
                attempt = _Attempt(kwargs)
                self.mcp_attempts.append(attempt)
                return real_debug_log(**{**kwargs, "data": attempt.instrumented()})
            if location == READER_INCOMPLETE_LOCATION:
                self.sequence.append("reader_incomplete")
            return real_debug_log(**kwargs)

        monkeypatch.setattr(server, "acp_debug_log", spy_debug_log)

    def wrap_runtime(self, runtime):
        """Forwarding spy on the runtime close: entry is recorded, the real close still runs."""
        observed = self

        class _ObservedRuntime:
            def close(self):
                observed.sequence.append("mcp_close")
                result = runtime.close()
                observed.returned_outcomes.append(result)
                return result

        return _ObservedRuntime()

    def observe_owned_writer(self, monkeypatch) -> None:
        observed = self

        class _RecordingDedicatedWriter(DedicatedOutboundWriter):
            def close_and_join(self, *args, **kwargs):
                observed.sequence.append("writer")
                return super().close_and_join(*args, **kwargs)

        monkeypatch.setattr(server, "DedicatedOutboundWriter", _RecordingDedicatedWriter)


class _NoneRuntime:
    def close(self):
        return None


class _ForeignOutcome:
    sdk_closed = True
    endpoint_closed = True
    supervisor_closed = True
    supervisor_state = "INJECTED-ARBITRARY-STATE-9f3a"
    complete = True  # a self-declared completion from a foreign object must not be trusted


class _ForeignRuntime:
    def close(self):
        return _ForeignOutcome()


class _CapturingWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def write_line(self, message):
        self.messages.append(dict(message))


class _PhysicalWriter(_CapturingWriter):
    """Exposes write_bytes/flush so serve_ndjson builds and OWNS a DedicatedOutboundWriter."""

    def write_bytes(self, payload: bytes) -> None:
        return None

    def flush(self) -> None:
        return None


def _server(tmp_path, runtime=None):
    configured = configured_test_agent_server(tmp_path, output_text="done")
    return server.AcpStreamServer(dispatcher=configured.server._dispatcher, client_mcp_runtime=runtime)  # noqa: SLF001


# --------------------------------------------------------------------------------------
# Driving the two reader outcomes: cooperative EOF, and an outstanding physical read
# --------------------------------------------------------------------------------------


async def _settle(task, *, what="serve task"):
    """Cancel if needed and settle under a real deadline; always retrieve the exception."""
    if not task.done():
        task.cancel()
    _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
    if pending:
        pytest.fail(f"{what} did not settle within {BOUND_SECONDS}s of cancellation")
    if task.cancelled():
        return "cancelled"
    exc = task.exception()
    if exc is not None:
        return exc
    return ("returned", task.result())


async def _drive_eof(srv, writer=None) -> None:
    """Cooperative EOF must return NORMALLY within the bound."""
    task = asyncio.create_task(srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), writer or _CapturingWriter()))
    try:
        _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
        assert not pending, "serve_ndjson did not return on EOF within the bound"
        assert not task.cancelled(), "EOF must return normally, not by cancellation"
        exc = task.exception()
        assert exc is None, exc
    finally:
        if not task.done():
            await _settle(task)


class _AcknowledgingStream:
    """Real pipe read end that acknowledges entry to and return from the blocking read."""

    def __init__(self, raw, loop) -> None:
        self._raw = raw
        self._loop = loop
        self.entered = 0
        self.returned = 0
        self._changed = asyncio.Event()

    def readline(self):  # executor worker thread
        self._loop.call_soon_threadsafe(self._bump, "entered")
        data = self._raw.readline()
        self._loop.call_soon_threadsafe(self._bump, "returned")
        return data

    def _bump(self, which: str) -> None:
        setattr(self, which, getattr(self, which) + 1)
        self._changed.set()

    @property
    def outstanding(self) -> int:
        return self.entered - self.returned

    async def wait_until(self, predicate, timeout=BOUND_SECONDS) -> bool:
        async def _poll():
            while not predicate():
                self._changed.clear()
                if predicate():
                    return
                await self._changed.wait()

        try:
            await asyncio.wait_for(_poll(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError):
            return False
        return True


class _Pipe:
    """A real OS pipe under the real reader; the producer is released in `aclose`, always."""

    def __init__(self, loop) -> None:
        read_fd, write_fd = os.pipe()
        self._raw_read = os.fdopen(read_fd, "rb", buffering=0)
        self.producer = os.fdopen(write_fd, "wb", buffering=0)
        self.stream = _AcknowledgingStream(self._raw_read, loop)
        self.reader = StdioNdjsonLineReader(self.stream)

    def release(self) -> None:
        if not self.producer.closed:
            try:
                self.producer.close()
            except OSError:
                pass

    async def aclose(self) -> None:
        primary_failure = sys.exc_info()[0] is not None
        self.release()
        worker_returned = await self.stream.wait_until(lambda: self.stream.outstanding == 0)
        if worker_returned:
            try:
                self._raw_read.close()
            except OSError:
                pass
        if not primary_failure:
            assert worker_returned, "cleanup left a worker thread blocked inside readline"


async def _drive_reader_incomplete(srv, writer=None):
    """Establish a real outstanding read, cancel the server, and return the settled outcome.

    The pipe is released and settled here on every path, so the caller never waits on input.
    """
    loop = asyncio.get_running_loop()
    pipe = _Pipe(loop)
    task = asyncio.create_task(srv.serve_ndjson(pipe.reader, writer or _CapturingWriter()))
    try:
        assert await pipe.stream.wait_until(lambda: pipe.stream.entered >= 1 and pipe.stream.outstanding == 1), (
            "precondition not established: no physical read was entered and left outstanding"
        )
        task.cancel()
        _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
        assert not pending, "teardown did not complete while the producer was still open"
        assert pipe.stream.outstanding == 1, "the physical read must still be outstanding at the decision"
        if task.cancelled():
            return "cancelled"
        return task.exception()
    finally:
        try:
            if not task.done():
                await _settle(task)
        finally:
            await pipe.aclose()


# --------------------------------------------------------------------------------------
# Row: reader EOF x {absent, clean, pending, failed} MCP
# --------------------------------------------------------------------------------------


async def test_eof_with_absent_runtime_is_clean_and_reports_nothing(tmp_path, monkeypatch, mcp_trace):
    """Control: no client-MCP runtime is the implicit clean/no-resource case."""
    observed = _Observed(monkeypatch)
    srv = _server(tmp_path)
    assert srv.client_mcp_runtime is None
    await _drive_eof(srv)
    assert observed.sequence == ["close_all"], observed.sequence
    assert observed.mcp_attempts == []
    assert _mcp_records(mcp_trace) == []
    assert _reader_records(mcp_trace) == []


async def test_eof_with_clean_runtime_consumes_a_complete_outcome_and_reports_nothing(
    tmp_path, monkeypatch, mcp_trace
):
    observed = _Observed(monkeypatch)
    runtime = _clean_runtime()
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        await _drive_eof(srv)
    finally:
        runtime.supervisor.close()
    assert observed.sequence == ["close_all", "mcp_close"], observed.sequence
    assert len(observed.returned_outcomes) == 1
    outcome = observed.returned_outcomes[0]
    assert isinstance(outcome, ClientMcpShutdownOutcome), outcome
    assert outcome.complete is True
    assert outcome.supervisor_state is MCPSupervisorState.DEAD
    assert observed.mcp_attempts == [], "a clean outcome must not be reported"
    assert _mcp_records(mcp_trace) == []


async def test_eof_with_pending_runtime_reports_incomplete_once_with_stage_payload(
    tmp_path, monkeypatch, mcp_trace
):
    """A supervisor still draining at the decision is non-clean: one diagnostic, real state."""
    observed = _Observed(monkeypatch)
    held = _start_held_supervisor()
    runtime = ClientMcpRuntime(disposition=object(), supervisor=held.supervisor, sdk_adapter=_SdkAdapter())
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        await _drive_eof(srv)
        # The real owner chain was still holding cleanup at the decision point.
        assert held.owner.is_alive(), "precondition: the owner thread must still be draining"
        assert held.supervisor.state is MCPSupervisorState.STOPPING
        assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete"], observed.sequence
        [outcome] = observed.returned_outcomes
        assert isinstance(outcome, ClientMcpShutdownOutcome)
        assert outcome.complete is False
        assert outcome.supervisor_closed is True, "no stage exception: pending, not a failure"
        assert len(observed.mcp_attempts) == 1
        assert observed.mcp_attempts[0].payload == {
            "sdk_closed": True,
            "endpoint_closed": True,
            "supervisor_closed": True,
            "supervisor_state": "STOPPING",
        }
        records = _mcp_records(mcp_trace)
        assert len(records) == 1, records
        assert records[0]["data"] == observed.mcp_attempts[0].payload
        assert _reader_records(mcp_trace) == [], "a completed reader must not be blamed"
    finally:
        held.finish()


async def test_eof_with_failed_stage_reports_incomplete_with_dead_supervisor(tmp_path, monkeypatch, mcp_trace):
    """An ordinary SDK stage failure is contained by the runtime and reported by the server."""
    observed = _Observed(monkeypatch)
    sup = MCPAsyncSupervisor()
    sup.start()
    runtime = ClientMcpRuntime(disposition=object(), supervisor=sup, sdk_adapter=_SdkAdapter(raise_on_close=True))
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        await _drive_eof(srv)
    finally:
        sup.close()
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete"], observed.sequence
    [outcome] = observed.returned_outcomes
    assert outcome.sdk_closed is False and outcome.supervisor_closed is True
    assert outcome.supervisor_state is MCPSupervisorState.DEAD
    assert outcome.complete is False
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == {
        "sdk_closed": False,
        "endpoint_closed": True,
        "supervisor_closed": True,
        "supervisor_state": "DEAD",
    }
    assert len(_mcp_records(mcp_trace)) == 1


# --------------------------------------------------------------------------------------
# Row: reader incomplete (real outstanding physical read) x {clean, pending} MCP
# --------------------------------------------------------------------------------------


async def test_reader_incomplete_with_clean_runtime_reports_only_the_reader(tmp_path, monkeypatch, mcp_trace):
    """A clean MCP outcome must not be blamed for an incomplete reader."""
    observed = _Observed(monkeypatch)
    runtime = _clean_runtime()
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        outcome = await _drive_reader_incomplete(srv)
        assert outcome == "cancelled", f"the initiating cancellation must be preserved, got {outcome!r}"
    finally:
        runtime.supervisor.close()
    assert observed.sequence == ["close_all", "mcp_close", "reader_incomplete"], observed.sequence
    assert observed.mcp_attempts == []
    assert _mcp_records(mcp_trace) == []
    assert len(_reader_records(mcp_trace)) == 1


async def test_reader_incomplete_with_pending_runtime_reports_both_and_preserves_cancellation(
    tmp_path, monkeypatch, mcp_trace
):
    observed = _Observed(monkeypatch)
    held = _start_held_supervisor()
    runtime = ClientMcpRuntime(disposition=object(), supervisor=held.supervisor, sdk_adapter=_SdkAdapter())
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        outcome = await _drive_reader_incomplete(srv)
        assert outcome == "cancelled", f"the initiating cancellation must be preserved, got {outcome!r}"
        assert held.supervisor.state is MCPSupervisorState.STOPPING
        assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "reader_incomplete"], (
            observed.sequence
        )
        assert len(observed.mcp_attempts) == 1
        assert observed.mcp_attempts[0].payload["supervisor_state"] == "STOPPING"
        assert len(_mcp_records(mcp_trace)) == 1
        assert len(_reader_records(mcp_trace)) == 1
    finally:
        held.finish()


async def test_teardown_order_mcp_then_owned_writer_then_reader_decision(tmp_path, monkeypatch, mcp_trace):
    """The existing order is preserved and the diagnostic sits right after the runtime close."""
    observed = _Observed(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    held = _start_held_supervisor()
    runtime = ClientMcpRuntime(disposition=object(), supervisor=held.supervisor, sdk_adapter=_SdkAdapter())
    srv = _server(tmp_path, observed.wrap_runtime(runtime))
    try:
        outcome = await _drive_reader_incomplete(srv, writer=_PhysicalWriter())
        assert outcome == "cancelled", outcome
        assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "writer", "reader_incomplete"], (
            observed.sequence
        )
    finally:
        held.finish()


# --------------------------------------------------------------------------------------
# Row: present runtime with an invalid result -- None, or a foreign object
# --------------------------------------------------------------------------------------


async def test_present_runtime_returning_none_is_not_clean_and_teardown_continues(
    tmp_path, monkeypatch, mcp_trace
):
    observed = _Observed(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_NoneRuntime()))
    await _drive_eof(srv, writer=_PhysicalWriter())
    assert observed.returned_outcomes == [None]
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "writer"], observed.sequence
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == SENTINEL_PAYLOAD
    records = _mcp_records(mcp_trace)
    assert len(records) == 1 and records[0]["data"] == SENTINEL_PAYLOAD


async def test_foreign_outcome_is_not_clean_and_cannot_inject_state_into_the_diagnostic(
    tmp_path, monkeypatch, mcp_trace
):
    """A foreign object is never trusted: not its `complete`, not its stage flags, not its state."""
    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_ForeignRuntime()))
    await _drive_eof(srv)
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete"], observed.sequence
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == SENTINEL_PAYLOAD
    records = _mcp_records(mcp_trace)
    assert len(records) == 1 and records[0]["data"] == SENTINEL_PAYLOAD
    assert _ForeignOutcome.supervisor_state not in mcp_trace.read_text(encoding="utf-8")


async def test_real_outcome_with_a_non_state_value_degrades_to_the_sentinel_state(tmp_path, monkeypatch, mcp_trace):
    """Even a genuine outcome instance may only echo a real MCPSupervisorState value."""
    poison = "INJECTED-ARBITRARY-STATE-77c1"

    class _PoisonedRuntime:
        def close(self):
            return ClientMcpShutdownOutcome(
                sdk_closed=True,
                endpoint_closed=True,
                supervisor_closed=True,
                supervisor_state=poison,  # type: ignore[arg-type]
                complete=False,
            )

    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_PoisonedRuntime()))
    await _drive_eof(srv)
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == {
        "sdk_closed": True,
        "endpoint_closed": True,
        "supervisor_closed": True,
        "supervisor_state": "unknown",
    }
    assert poison not in mcp_trace.read_text(encoding="utf-8")


async def test_a_self_declared_complete_outcome_that_is_not_dead_is_still_reported(tmp_path, monkeypatch, mcp_trace):
    """`complete` is trusted only on a real outcome instance, and the value itself must be True.

    A truthy non-boolean smuggled into `complete` must not pass as clean.
    """

    class _TruthyRuntime:
        def close(self):
            return ClientMcpShutdownOutcome(
                sdk_closed=True,
                endpoint_closed=True,
                supervisor_closed=True,
                supervisor_state=MCPSupervisorState.STOPPING,
                complete="yes",  # type: ignore[arg-type]
            )

    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_TruthyRuntime()))
    await _drive_eof(srv)
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload["supervisor_state"] == "STOPPING"


# --------------------------------------------------------------------------------------
# Row: the diagnostic is bounded and inert -- trace off, sink failure, payload failure
# --------------------------------------------------------------------------------------


async def test_trace_off_still_attempts_exactly_once_and_writes_nothing(tmp_path, monkeypatch, mcp_trace_off):
    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_NoneRuntime()))
    await _drive_eof(srv)
    assert len(observed.mcp_attempts) == 1, "the attempt is made regardless of tracing"
    assert observed.mcp_attempts[0].unevaluated, "with tracing off the sink must not evaluate the payload"
    assert not mcp_trace_off.exists(), "no trace file may be written while trace is disabled"


async def test_observer_is_transparent_stateful_supplier_evaluated_by_the_sink_alone(tmp_path, monkeypatch):
    """Mirror of the reviewer's probe: through the real spy and the real sink, a stateful
    supplier is evaluated zero times with tracing off and exactly once with tracing on, and
    the recorded payload IS the evaluation the sink wrote."""
    def probe(enabled: bool) -> None:
        path = tmp_path / ("stateful-on.ndjson" if enabled else "stateful-off.ndjson")
        configure_debug_trace(enabled=enabled, log_path=path)
        calls: list[int] = []

        def supplier():
            calls.append(1)
            return {"attempt": len(calls)}

        with pytest.MonkeyPatch.context() as inner:
            observed = _Observed(inner)
            server.acp_debug_log(location=MCP_INCOMPLETE_LOCATION, message="probe", data=supplier)
        assert len(observed.mcp_attempts) == 1
        assert len(calls) == int(enabled)
        if enabled:
            assert observed.mcp_attempts[0].payload == {"attempt": 1}
            assert _mcp_records(path)[0]["data"] == {"attempt": 1}
        else:
            assert observed.mcp_attempts[0].unevaluated
            assert not path.exists()
        reset_debug_trace_context()

    probe(False)
    probe(True)


async def test_observer_records_a_fail_once_supplier_without_retry_or_swallowing(tmp_path, monkeypatch):
    path = tmp_path / "fail-once.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    calls: list[int] = []

    def fail_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first evaluation fails")
        return {"attempt": len(calls)}

    with pytest.MonkeyPatch.context() as inner:
        observed = _Observed(inner)
        server.acp_debug_log(location=MCP_INCOMPLETE_LOCATION, message="probe", data=fail_once)  # contained by the sink
    assert calls == [1], "the sink must not retry a failing supplier"
    assert isinstance(observed.mcp_attempts[0].failure, RuntimeError)
    assert not path.exists()

    class _Interrupt(BaseException):
        pass

    def interrupting():
        raise _Interrupt()

    with pytest.MonkeyPatch.context() as inner:
        observed = _Observed(inner)
        with pytest.raises(_Interrupt):
            server.acp_debug_log(location=MCP_INCOMPLETE_LOCATION, message="probe", data=interrupting)
    assert isinstance(observed.mcp_attempts[0].failure, _Interrupt), "control flow keeps its identity through the observer"


async def test_diagnostic_sink_failure_cannot_mask_the_initiating_cancellation(tmp_path, monkeypatch, mcp_trace):
    """An ordinary failure of the diagnostic sink is contained; teardown continues to the reader."""
    observed = _Observed(monkeypatch)
    spied = server.acp_debug_log  # the forwarding spy installed by _Observed
    attempts: list[dict] = []

    def failing_debug_log(**kwargs):
        if kwargs.get("location") == MCP_INCOMPLETE_LOCATION:
            attempts.append(kwargs)
            raise RuntimeError("diagnostic sink is broken")
        return spied(**kwargs)

    monkeypatch.setattr(server, "acp_debug_log", failing_debug_log)
    srv = _server(tmp_path, observed.wrap_runtime(_NoneRuntime()))
    outcome = await _drive_reader_incomplete(srv)
    assert outcome == "cancelled", f"the diagnostic failure replaced the initiating cancellation: {outcome!r}"
    assert len(attempts) == 1
    assert observed.sequence == ["close_all", "mcp_close", "reader_incomplete"], observed.sequence
    assert "diagnostic sink is broken" not in (mcp_trace.read_text(encoding="utf-8") if mcp_trace.exists() else "")


async def test_diagnostic_sink_failure_cannot_mask_an_ordinary_serving_exception(tmp_path, monkeypatch, mcp_trace):
    """The exact initiating exception INSTANCE survives a raising diagnostic."""

    class _InitiatingError(RuntimeError):
        pass

    initiating = _InitiatingError("serving exploded")

    async def exploding_notification(self, message):
        raise initiating

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_notification", exploding_notification)
    observed = _Observed(monkeypatch)
    spied = server.acp_debug_log
    attempts: list[dict] = []

    def failing_debug_log(**kwargs):
        if kwargs.get("location") == MCP_INCOMPLETE_LOCATION:
            attempts.append(kwargs)
            raise RuntimeError("diagnostic sink is broken")
        return spied(**kwargs)

    monkeypatch.setattr(server, "acp_debug_log", failing_debug_log)
    srv = _server(tmp_path, observed.wrap_runtime(_NoneRuntime()))
    reader = StdioNdjsonLineReader(io.BytesIO(b'{"jsonrpc":"2.0","method":"session/cancel","params":{}}\n'))
    task = asyncio.create_task(srv.serve_ndjson(reader, _CapturingWriter()))
    try:
        _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
        assert not pending, "serve_ndjson did not settle on the ordinary-error path"
        assert not task.cancelled(), "an ordinary exception must not surface as cancellation"
        assert task.exception() is initiating, f"the exact initiating instance must survive: {task.exception()!r}"
    finally:
        if not task.done():
            await _settle(task, what="ordinary-error serve task")
    assert len(attempts) == 1
    assert observed.sequence[:2] == ["close_all", "mcp_close"], observed.sequence


async def test_payload_construction_failure_is_contained(tmp_path, monkeypatch, mcp_trace):
    """A genuine outcome instance whose field access raises must not escape the teardown."""

    class _ExplodingOutcome(ClientMcpShutdownOutcome):
        # Constructed normally (the frozen dataclass initializer still runs); the failure is
        # injected only when the diagnostic READS a stage field during payload construction.
        def __getattribute__(self, name):
            if name == "sdk_closed":
                raise RuntimeError("payload construction boom")
            return super().__getattribute__(name)

    class _ExplodingRuntime:
        def close(self):
            return _ExplodingOutcome(
                sdk_closed=True,
                endpoint_closed=True,
                supervisor_closed=True,
                supervisor_state=MCPSupervisorState.STOPPING,
                complete=False,
            )

    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_ExplodingRuntime()))
    outcome = await _drive_reader_incomplete(srv)
    assert outcome == "cancelled", f"a payload-construction failure replaced the cancellation: {outcome!r}"
    # Seam 1: the reporter reaches the sink with a lazy payload; the field read fails INSIDE
    # the sink's boundary, so the attempt is observed, nothing is recorded on disk, and
    # teardown still continues to the reader decision.
    assert len(observed.mcp_attempts) == 1
    assert isinstance(observed.mcp_attempts[0].failure, RuntimeError)
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "reader_incomplete"], observed.sequence
    assert _mcp_records(mcp_trace) == []
    assert "payload construction boom" not in (mcp_trace.read_text(encoding="utf-8") if mcp_trace.exists() else "")


def test_exception_identity_check_rejects_a_replacement_instance():
    """Teeth for the identity assertion above: same class, different instance, must not satisfy `is`."""
    a = RuntimeError("serving exploded")
    b = RuntimeError("serving exploded")
    assert isinstance(b, type(a)) and b is not a


# --------------------------------------------------------------------------------------
# R1 (Codex review): classifying the outcome can itself fail. Reading `complete` on a
# genuine outcome instance is part of the diagnostic boundary: an ordinary failure there is
# contained, the result is treated as invalid (sentinel payload), and teardown continues
# through the owned writer and the reader decision. BaseException is NOT absorbed.
# --------------------------------------------------------------------------------------


class _CompletionReadFailure(RuntimeError):
    pass


def _outcome_failing_on(field_name: str, error: BaseException) -> type:
    """A genuine ClientMcpShutdownOutcome subclass whose named field raises on READ.

    Construction succeeds (the frozen dataclass initializer sets fields without reading
    them); the failure surfaces only when the server classifies or reports the outcome.
    """

    class _Failing(ClientMcpShutdownOutcome):
        def __getattribute__(self, name):
            if name == field_name:
                raise error
            return super().__getattribute__(name)

    return _Failing


class _FailingFieldRuntime:
    def __init__(self, field_name: str, error: BaseException) -> None:
        self._cls = _outcome_failing_on(field_name, error)

    def close(self):
        return self._cls(
            sdk_closed=True,
            endpoint_closed=True,
            supervisor_closed=True,
            supervisor_state=MCPSupervisorState.STOPPING,
            complete=False,
        )


async def test_completion_read_failure_is_contained_and_reported_under_cancellation(
    tmp_path, monkeypatch, mcp_trace
):
    """RED on the reviewed candidate: reading `complete` escaped and replaced the cancellation."""
    boom = _CompletionReadFailure("completion read boom")
    observed = _Observed(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_FailingFieldRuntime("complete", boom)))
    outcome = await _drive_reader_incomplete(srv, writer=_PhysicalWriter())
    assert outcome == "cancelled", f"a completion-read failure replaced the cancellation: {outcome!r}"
    # Classification failure is an INVALID result: one sentinel diagnostic, then teardown continues
    # through the owned writer and the reader decision.
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "writer", "reader_incomplete"], (
        observed.sequence
    )
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == SENTINEL_PAYLOAD
    records = _mcp_records(mcp_trace)
    assert len(records) == 1 and records[0]["data"] == SENTINEL_PAYLOAD
    assert "completion read boom" not in mcp_trace.read_text(encoding="utf-8")


async def test_completion_read_failure_preserves_an_ordinary_serving_exception_identity(
    tmp_path, monkeypatch, mcp_trace
):
    """RED on the reviewed candidate: the completion-read error replaced the initiating instance."""

    class _InitiatingError(RuntimeError):
        pass

    initiating = _InitiatingError("serving exploded")

    async def exploding_notification(self, message):
        raise initiating

    monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_notification", exploding_notification)
    boom = _CompletionReadFailure("completion read boom")
    observed = _Observed(monkeypatch)
    observed.observe_owned_writer(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_FailingFieldRuntime("complete", boom)))
    reader = StdioNdjsonLineReader(io.BytesIO(b'{"jsonrpc":"2.0","method":"session/cancel","params":{}}\n'))
    task = asyncio.create_task(srv.serve_ndjson(reader, _PhysicalWriter()))
    try:
        _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
        assert not pending, "serve_ndjson did not settle on the ordinary-error path"
        assert not task.cancelled(), "an ordinary exception must not surface as cancellation"
        assert task.exception() is initiating, f"the exact initiating instance must survive: {task.exception()!r}"
    finally:
        if not task.done():
            await _settle(task, what="ordinary-error serve task")
    # Teardown continued through the owned writer and reached the reader decision. Whether the
    # reader wrapper had already finished (one frame, then EOF) when the initiating exception
    # propagated is a schedule detail, so the reader outcome is not pinned here.
    assert observed.sequence[:4] == ["close_all", "mcp_close", "mcp_incomplete", "writer"], observed.sequence
    assert observed.sequence[4:] in ([], ["reader_incomplete"]), observed.sequence
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].payload == SENTINEL_PAYLOAD
    assert "completion read boom" not in mcp_trace.read_text(encoding="utf-8")


async def test_classification_containment_does_not_absorb_base_exception(tmp_path, monkeypatch, mcp_trace):
    """Control: a BaseException raised while classifying propagates by identity; nothing is reported."""

    class _Interrupt(BaseException):
        pass

    interrupt = _Interrupt("control-flow interrupt")
    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_FailingFieldRuntime("complete", interrupt)))
    task = asyncio.create_task(srv.serve_ndjson(StdioNdjsonLineReader(io.BytesIO(b"")), _CapturingWriter()))
    try:
        _done, pending = await asyncio.wait({task}, timeout=BOUND_SECONDS)
        assert not pending, "serve_ndjson did not settle"
        assert not task.cancelled()
        assert task.exception() is interrupt, f"BaseException must propagate by identity: {task.exception()!r}"
    finally:
        if not task.done():
            await _settle(task, what="base-exception control serve task")
    assert observed.sequence == ["close_all", "mcp_close"], observed.sequence
    assert observed.mcp_attempts == [], "a BaseException must not be converted into a diagnostic"


async def test_stage_field_read_failure_after_classification_is_still_contained(tmp_path, monkeypatch, mcp_trace):
    """Retained behaviour: a failure reading a STAGE field (after `complete` classified the outcome
    as non-clean) is contained. Seam 1 moved the stage reads into the sink's lazy supplier, so
    the attempt now reaches the sink and fails inside its boundary: observed, unrecorded, and
    teardown continues to the reader decision."""
    boom = _CompletionReadFailure("stage read boom")
    observed = _Observed(monkeypatch)
    srv = _server(tmp_path, observed.wrap_runtime(_FailingFieldRuntime("endpoint_closed", boom)))
    outcome = await _drive_reader_incomplete(srv)
    assert outcome == "cancelled", outcome
    assert len(observed.mcp_attempts) == 1
    assert observed.mcp_attempts[0].failure is boom
    assert _mcp_records(mcp_trace) == []
    assert "stage read boom" not in (mcp_trace.read_text(encoding="utf-8") if mcp_trace.exists() else "")
    assert observed.sequence == ["close_all", "mcp_close", "mcp_incomplete", "reader_incomplete"], observed.sequence
