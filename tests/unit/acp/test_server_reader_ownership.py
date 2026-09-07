"""Seam 4 B: who owns the physical stdin read when the server tears down.

These probes use the REAL `StdioNdjsonLineReader` over REAL OS pipes. An in-memory reader
fake cannot exhibit the defect at all -- the whole question is what happens to a blocking
`readline` already running inside `asyncio.to_thread`, and a fake never enters one.

Only the *stream handed to the real reader* is instrumented, so the genuine blocking read
still happens; the instrumentation merely acknowledges entry to and return from that read,
from inside the worker thread, at the read site. Receiving a protocol response would NOT
prove the worker re-entered a read -- that is a race, not evidence.

Cancelling the async wrapper returns promptly while the worker thread stays blocked in its
read. The interpreter may then wait on the default executor at interpreter shutdown; that is
an executor wait, not a guaranteed process-exit bound, and this module asserts no such bound.
The runtime actually used is recorded by the B2 case rather than assumed. Consequently a test
here may NEVER wait for a physical read to finish on its own: it must release the producer,
and every fixture releases it before waiting on anything.

Ported from sandbox tag `sandbox-seam4` (commit 0c718486), seam 4 B portion. Seam 4 A's
failure observer, delivered on main in 12cc5638, is unchanged and is exercised as a regression.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from optimus.acp import server
from optimus.acp.server import StdioNdjsonLineReader
from tests.integration.acp.test_server_stream import configured_test_agent_server

TEARDOWN_BOUND_SECONDS = 5.0
SETTLE_BOUND_SECONDS = 5.0
B2_BOUND_SECONDS = 60.0

# Diagnostic contract for the incomplete-reader record, implemented by the reader-ownership
# teardown in serve_ndjson; these constants pin the location and exact data shape it must emit.
READER_INCOMPLETE_LOCATION = "server.py:serve_ndjson:reader_incomplete"
READER_INCOMPLETE_DATA = {"reader_state": "incomplete"}


# Frame sequence delivered by the ordinary-exception fixtures, and the phase that proves the
# queued request actually reached the server queue. `returned >= FRAME_QUEUED` means all three
# frames were consumed; `entered >= FRAME_QUEUED + 1` means the reader loop advanced past the
# enqueue of frame three (it only re-enters `readline` after `message_queue.put` returns), so
# request 2 is pending server-side rather than merely written into the pipe; `outstanding == 1`
# pins that subsequent physical read as still blocked. A relative "one more read than when I
# started" check is NOT sufficient: it can be satisfied by the read that is about to consume
# frame three, before that frame is enqueued at all.
FRAME_INITIALIZE = 1
FRAME_NOTIFICATION = 2
FRAME_QUEUED = 3
SUBSEQUENT_READ = FRAME_QUEUED + 1


def _queued_frame_phase(stream) -> bool:
    return (
        stream.returned >= FRAME_QUEUED
        and stream.entered >= SUBSEQUENT_READ
        and stream.outstanding == 1
    )


class _SeamBOrdinaryError(RuntimeError):
    """A specific ordinary exception, so 'the initiating outcome survived' is checkable."""


def _records(path):
    if not path.exists() or path.is_dir():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _incomplete_records(path):
    return [r for r in _records(path) if r.get("location") == READER_INCOMPLETE_LOCATION]


@pytest.fixture
def reader_trace(tmp_path):
    """Trace enabled, always reset -- even if an assertion or cleanup below fails."""
    from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context

    path = tmp_path / "seam4b-trace.ndjson"
    configure_debug_trace(enabled=True, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


@pytest.fixture
def reader_trace_off(tmp_path):
    from optimus.acp.debug_trace import configure_debug_trace, reset_debug_trace_context

    path = tmp_path / "seam4b-trace-off.ndjson"
    configure_debug_trace(enabled=False, log_path=path)
    try:
        yield path
    finally:
        reset_debug_trace_context()


class _AcknowledgingStream:
    """Real pipe read end that acknowledges entry to, and return from, the blocking read.

    Counters are bumped on the event loop via `call_soon_threadsafe`, so the test observes
    them without a data race and without polling the worker thread.
    """

    def __init__(self, raw, loop) -> None:
        self._raw = raw
        self._loop = loop
        self.entered = 0
        self.returned = 0
        self._changed = asyncio.Event()

    def readline(self):  # executes on the executor worker thread
        self._loop.call_soon_threadsafe(self._bump, "entered")
        data = self._raw.readline()  # the genuine blocking read
        self._loop.call_soon_threadsafe(self._bump, "returned")
        return data

    def _bump(self, which: str) -> None:
        setattr(self, which, getattr(self, which) + 1)
        self._changed.set()

    @property
    def outstanding(self) -> int:
        return self.entered - self.returned

    async def wait_until(self, predicate, timeout=SETTLE_BOUND_SECONDS) -> bool:
        """Bounded wait on our own coroutine. Returns whether the predicate held."""

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


class _CapturingWriter:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def write_line(self, message):
        self.messages.append(dict(message))

    def response_ids(self):
        return [m.get("id") for m in self.messages if "result" in m or "error" in m]

    async def wait_for_response(self, request_id, timeout=SETTLE_BOUND_SECONDS):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            for message in self.messages:
                if message.get("id") == request_id and ("result" in message or "error" in message):
                    return message
            await asyncio.sleep(0.02)
        return None


class _Harness:
    """Real pipe + real reader + the real server, with forwarding cleanup spies."""

    def __init__(self, tmp_path, loop, monkeypatch) -> None:
        read_fd, write_fd = os.pipe()
        self._raw_read = os.fdopen(read_fd, "rb", buffering=0)
        self.producer = os.fdopen(write_fd, "wb", buffering=0)
        self._producer_open = True
        self.stream = _AcknowledgingStream(self._raw_read, loop)
        self.reader = StdioNdjsonLineReader(self.stream)
        self.writer = _CapturingWriter()
        self.server = configured_test_agent_server(tmp_path, output_text="done").server

        # Forwarding spies: the REAL cleanup still runs; we record order and count.
        self.sequence: list[str] = []
        real_close_all = server.AcpDuplexAdapter.close_all

        def spy_close_all(inner_self):
            self.sequence.append("close_all")
            return real_close_all(inner_self)

        monkeypatch.setattr(server.AcpDuplexAdapter, "close_all", spy_close_all)

        # Entry-level dispatch spy: records request IDs as they ENTER the real handler.
        # Responses measure settlement, not dispatch -- a request can enter the handler and have
        # its result discarded, which a response-only check cannot see.
        self.dispatch_entries: list = []
        real_handle_request = server.AcpDuplexAdapter.handle_client_request

        async def spy_handle_request(inner_self, message, *, ownership_slot=None):
            self.dispatch_entries.append(message.get("id"))
            return await real_handle_request(inner_self, message, ownership_slot=ownership_slot)

        monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_request", spy_handle_request)

        real_debug_log = server.acp_debug_log

        def spy_debug_log(**kwargs):
            if kwargs.get("location") == READER_INCOMPLETE_LOCATION:
                self.sequence.append("reader_incomplete")
            return real_debug_log(**kwargs)

        monkeypatch.setattr(server, "acp_debug_log", spy_debug_log)

    @property
    def close_all_count(self) -> int:
        return self.sequence.count("close_all")

    def send(self, *messages) -> None:
        """Write one or more NDJSON lines in a single write."""
        blob = b"".join((json.dumps(m) + "\n").encode("utf-8") for m in messages)
        self.producer.write(blob)
        self.producer.flush()

    def producer_is_open(self) -> bool:
        """Report producer ownership WITHOUT supplying input.

        Writing here (even a blank line) would release the very blocked read the caller is
        about to assert is still outstanding, and the acknowledgement counter could still show
        its old value because the loop callback had not run yet. Input is only ever released at
        the explicit test step intended to do so.
        """
        return self._producer_open and not self.producer.closed

    def release(self) -> None:
        """Release the producer so the blocked worker can return. Always safe to repeat."""
        if self._producer_open:
            try:
                self.producer.close()
            except OSError:
                pass
            self._producer_open = False

    async def settle_worker(self) -> bool:
        """Release input and wait for the worker to actually return from its read."""
        self.release()
        return await self.stream.wait_until(lambda: self.stream.outstanding == 0)

    async def aclose(self, serve_task, expected_exception=None) -> None:
        """Fail-closed cleanup: never leaves a blocked worker or an unsettled server task.

        Producer first, then the server, then the read handle -- closing the read end while a
        worker is inside `readline` on it is exactly what we must not do. The final wait's
        result is checked rather than discarded, and a finished task's exception is always
        retrieved so an unexpected terminal outcome cannot vanish as "never retrieved".
        """
        primary_failure = sys.exc_info()[0] is not None
        worker_returned = await self.settle_worker()

        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        if pending:
            serve_task.cancel()
            _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        settled = not pending

        terminal = None
        if settled and not serve_task.cancelled():
            terminal = serve_task.exception()  # always retrieved, even on the failure path

        if worker_returned and settled:
            try:
                self._raw_read.close()
            except OSError:
                pass

        if primary_failure:
            return  # a real failure is already propagating; do not mask it
        assert worker_returned, "cleanup left a worker thread blocked inside readline"
        assert settled, "cleanup returned with the serve task still pending; it resisted teardown"
        if expected_exception is not None:
            assert terminal is expected_exception, (
                f"the serve task settled with {terminal!r}, not the expected initiating exception"
            )
        elif terminal is not None:
            raise terminal


async def _start(harness):
    return asyncio.create_task(harness.server.serve_ndjson(harness.reader, harness.writer))


async def _blocked_read_established(harness) -> bool:
    """The precondition every B case needs: a physical read is entered and has not returned."""
    return await harness.stream.wait_until(
        lambda: harness.stream.entered >= 1 and harness.stream.outstanding == 1
    )


async def test_seam4_b1_cancellation_completes_teardown_while_the_producer_stays_open(
    tmp_path, monkeypatch, reader_trace
):
    """B1: cancelling the server must complete teardown while a physical read is still blocked.

    On unchanged main the teardown ends with an unconditional `await reader_task`, so with the
    producer open the coroutine never completes and this fails at the completion assertion --
    AFTER the blocked-read precondition is established, not at setup.
    """
    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    try:
        assert await _blocked_read_established(harness), (
            "precondition not established: no physical read was entered and left outstanding"
        )
        entered_at_cancel = harness.stream.entered

        serve_task.cancel()
        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, (
            "coroutine teardown did not complete while the producer was still open; the "
            "unconditional `await reader_task` parks cleanup on input that may never arrive"
        )

        assert serve_task.cancelled(), "the initiating cancellation must be preserved"
        assert harness.producer_is_open(), "the producer must still be open at this point"
        assert harness.stream.outstanding == 1, "the physical read must still be outstanding"

        assert harness.close_all_count == 1, (
            f"applicable cleanup must run exactly once, saw {harness.close_all_count}"
        )
        incomplete = _incomplete_records(reader_trace)
        assert len(incomplete) == 1, f"exactly one incomplete-reader record, saw {len(incomplete)}"
        assert incomplete[0]["data"] == READER_INCOMPLETE_DATA, incomplete[0]["data"]
        assert harness.sequence == ["close_all", "reader_incomplete"], (
            f"existing cleanup must precede the reader decision, saw {harness.sequence}"
        )

        # The asynchronous reader must have stopped consuming input: feeding a line now
        # releases the blocked worker but must not start another read or dispatch anything.
        responses_before = list(harness.writer.response_ids())
        harness.send({"jsonrpc": "2.0", "id": 99, "method": "initialize", "params": {}})
        assert await harness.stream.wait_until(lambda: harness.stream.outstanding == 0)
        await asyncio.sleep(0.2)
        assert harness.stream.entered == entered_at_cancel, (
            "the async reader kept consuming input after teardown; entered went "
            f"{entered_at_cancel} -> {harness.stream.entered}"
        )
        assert harness.writer.response_ids() == responses_before, (
            "a request delivered after teardown must not be dispatched"
        )
    finally:
        await harness.aclose(serve_task)


@pytest.mark.parametrize(
    "order",
    ["reader_ack_first", "handler_first"],
    ids=["reader-ack-arrives-first", "handler-starts-first"],
)
async def test_seam4_b_ordinary_exception_preserves_identity_and_drops_queued_work(
    tmp_path, monkeypatch, reader_trace, order
):
    """An ordinary exception initiating teardown must survive by IDENTITY, and queued work
    must never enter the request handler.

    The subsequent-read handshake is bound to a phase captured BEFORE the frames are delivered,
    so an acknowledgement that has already arrived is accepted rather than making the fixture
    demand another read that cannot occur while input is held open. Both scheduling orders are
    exercised explicitly: the reader's acknowledgement arriving first, and the handler starting
    first.
    """
    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    initiating = _SeamBOrdinaryError("ordinary teardown trigger")
    try:
        # 1. Establish that an ordinary request really dispatches, observed at handler ENTRY.
        harness.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert await harness.writer.wait_for_response(1) is not None, (
            "the initial request must dispatch before the baseline is taken"
        )
        assert harness.dispatch_entries == [1], harness.dispatch_entries
        entry_baseline = list(harness.dispatch_entries)

        # 2. The initiating exception may only propagate once the queued frame is genuinely
        #    pending in the server queue and the subsequent physical read is blocked.
        handler_entered = asyncio.Event()
        proceed = asyncio.Event()
        reached_phase = {}

        async def failing_notification(self, message):
            handler_entered.set()
            await proceed.wait()
            ok = await harness.stream.wait_until(lambda: _queued_frame_phase(harness.stream))
            assert ok, (
                "the queued frame never reached the server queue with a subsequent read "
                f"outstanding (entered={harness.stream.entered}, returned={harness.stream.returned})"
            )
            reached_phase["entered"] = harness.stream.entered
            reached_phase["returned"] = harness.stream.returned
            raise initiating

        monkeypatch.setattr(server.AcpDuplexAdapter, "handle_client_notification", failing_notification)

        notification = {"jsonrpc": "2.0", "method": "session/cancel", "params": {}}
        queued = {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path)}}

        if order == "reader_ack_first":
            # Both frames together; the complete phase is reached before the handler is released.
            harness.send(notification, queued)
            assert await harness.stream.wait_until(lambda: _queued_frame_phase(harness.stream)), (
                "the queued frame never reached the server queue before releasing the handler "
                f"(entered={harness.stream.entered}, returned={harness.stream.returned})"
            )
            proceed.set()
        else:
            # Handler first: it is already inside its body before the queued frame is delivered,
            # then it waits for the same complete phase.
            harness.send(notification)
            await asyncio.wait_for(handler_entered.wait(), timeout=SETTLE_BOUND_SECONDS)
            harness.send(queued)
            proceed.set()

        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, (
            "teardown driven by an ordinary exception did not complete while the producer was open"
        )

        # 3. Identity, not merely type: a replacement instance of the same class must not satisfy this.
        assert not serve_task.cancelled(), "an ordinary exception must not surface as cancellation"
        exc = serve_task.exception()
        assert exc is initiating, f"the exact initiating exception instance must survive: {exc!r}"

        assert harness.close_all_count == 1, harness.close_all_count
        incomplete = _incomplete_records(reader_trace)
        assert len(incomplete) == 1, f"exactly one incomplete-reader record, saw {len(incomplete)}"
        assert incomplete[0]["data"] == READER_INCOMPLETE_DATA

        # 4. Dispatch is measured at handler ENTRY; settlement is a separate, weaker check.
        assert harness.dispatch_entries == entry_baseline, (
            f"a request queued behind the failing notification entered the handler: "
            f"{harness.dispatch_entries}"
        )
        assert 2 not in harness.dispatch_entries, "the queued request id must never enter the handler"
        assert reached_phase.get("returned", 0) >= FRAME_QUEUED, (
            f"the initiating exception propagated before frame {FRAME_QUEUED} was consumed: {reached_phase}"
        )
        assert reached_phase.get("entered", 0) >= SUBSEQUENT_READ, (
            f"the subsequent read had not started when the exception propagated: {reached_phase}"
        )
        settled_ids = [i for i in harness.writer.response_ids() if i is not None]
        assert settled_ids == [1], f"only the established request may settle: {settled_ids}"
    finally:
        await harness.aclose(serve_task, expected_exception=initiating)


async def test_seam4_b_entry_spy_detects_a_queued_dispatch_that_writes_no_response(
    tmp_path, monkeypatch, reader_trace
):
    """Teeth for the no-dispatch guard: a queued request that ENTERS the handler and whose
    response is discarded must be visible.

    This injects the forbidden dispatch at the test boundary -- it is not a claim that
    production does it. A response-only assertion cannot see this; the entry spy must.
    """
    from optimus.acp.lifecycle import ResponseOwnershipSlot

    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    initiating = _SeamBOrdinaryError("ordinary teardown trigger")
    try:
        harness.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert await harness.writer.wait_for_response(1) is not None

        queued = {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path)}}

        async def notification_that_smuggles_a_dispatch(self, message):
            assert await harness.stream.wait_until(lambda: _queued_frame_phase(harness.stream)), (
                "the queued frame never reached the server queue with a subsequent read outstanding"
            )
            # The injected fault: the queued request enters the REAL handler, and its response
            # is deliberately not written.
            await self.handle_client_request(queued, ownership_slot=ResponseOwnershipSlot())
            raise initiating

        monkeypatch.setattr(
            server.AcpDuplexAdapter, "handle_client_notification", notification_that_smuggles_a_dispatch
        )
        harness.send({"jsonrpc": "2.0", "method": "session/cancel", "params": {}}, queued)

        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, "teardown must still complete"

        # The guard the contract test relies on: entry is observed even though nothing settled.
        assert 2 in harness.dispatch_entries, (
            "the entry spy failed to observe a forbidden handler entry; the no-dispatch "
            "assertion would be vacuous"
        )
        settled_ids = [i for i in harness.writer.response_ids() if i is not None]
        assert 2 not in settled_ids, (
            "this control requires the smuggled dispatch to write no response, so that a "
            "response-only check would wrongly pass"
        )
    finally:
        await harness.aclose(serve_task, expected_exception=initiating)


def test_seam4_b_exception_identity_check_rejects_a_replacement_instance():
    """Teeth for the identity assertion: same class, different instance, must not satisfy `is`."""
    initiating = _SeamBOrdinaryError("ordinary teardown trigger")
    replacement = _SeamBOrdinaryError("ordinary teardown trigger")
    assert isinstance(replacement, type(initiating)), "the control needs the same class"
    assert replacement is not initiating, (
        "a replacement instance must fail an identity check even though isinstance passes"
    )


async def test_seam4_b_cooperative_eof_still_completes_the_full_shutdown_path(
    tmp_path, monkeypatch, reader_trace
):
    """Control: deliberate EOF is a normal return with a completed reader and NO diagnostic."""
    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    try:
        assert await _blocked_read_established(harness), "precondition not established"

        harness.release()  # cooperative EOF
        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, "EOF must complete the shutdown path"
        assert not serve_task.cancelled(), "EOF must return normally, not by cancellation"
        assert serve_task.exception() is None, serve_task.exception()

        assert harness.stream.outstanding == 0, "the reader must have completed on the EOF path"
        assert harness.close_all_count == 1, harness.close_all_count
        assert _incomplete_records(reader_trace) == [], (
            "a cooperative EOF must not be reported as an incomplete reader"
        )
    finally:
        await harness.aclose(serve_task)


async def test_seam4_b_trace_disabled_writes_nothing_and_does_not_change_teardown(
    tmp_path, monkeypatch, reader_trace_off
):
    """Control: with trace off, teardown behaviour is identical and no trace file appears."""
    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    try:
        assert await _blocked_read_established(harness), "precondition not established"

        serve_task.cancel()
        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, "teardown must complete with trace disabled too"
        assert serve_task.cancelled(), "the initiating cancellation must be preserved"
        assert harness.close_all_count == 1, harness.close_all_count
        assert not reader_trace_off.exists(), "no trace file may be written while trace is disabled"
    finally:
        await harness.aclose(serve_task)


async def test_seam4_b_diagnostic_failure_cannot_mask_the_initiating_cancellation(
    tmp_path, monkeypatch, reader_trace
):
    """Control: an ordinary failure of the NEW diagnostic must not replace the outcome.

    The failure is injected only at the incomplete-reader boundary, after the read precondition
    is established, so this exercises the new reporting path rather than an earlier one.
    """
    loop = asyncio.get_running_loop()
    harness = _Harness(tmp_path, loop, monkeypatch)
    serve_task = await _start(harness)
    try:
        assert await _blocked_read_established(harness), "precondition not established"

        real_debug_log = server.acp_debug_log
        attempts = []

        def failing_debug_log(**kwargs):
            if kwargs.get("location") == READER_INCOMPLETE_LOCATION:
                attempts.append(kwargs.get("data"))
                raise RuntimeError("diagnostic sink is broken")
            return real_debug_log(**kwargs)

        monkeypatch.setattr(server, "acp_debug_log", failing_debug_log)

        serve_task.cancel()
        _done, pending = await asyncio.wait({serve_task}, timeout=TEARDOWN_BOUND_SECONDS)
        assert not pending, "a failing diagnostic must not stop teardown completing"
        assert serve_task.cancelled(), (
            "the diagnostic failure replaced the initiating cancellation as the outcome"
        )
        assert attempts, "the reporter must still have been invoked at the reader boundary"
        assert harness.close_all_count == 1, harness.close_all_count
    finally:
        await harness.aclose(serve_task)


# --------------------------------------------------------------------------------------
# B2: the process boundary. Coroutine teardown completing and the process exiting are
# distinct events, and this slice only establishes the first.
# --------------------------------------------------------------------------------------

_B2_CHILD_SCRIPT = '''
import asyncio, json, os, sys
from pathlib import Path

def _emit(marker):
    sys.stdout.write(marker + "\\n")
    sys.stdout.flush()

from optimus.acp import server as _server_module
from optimus.acp.server import StdioNdjsonLineReader
from tests.integration.acp.test_server_stream import configured_test_agent_server

_emit("MODULE=" + str(Path(_server_module.__file__).resolve()))
_emit("RUNTIME=" + sys.version.split()[0])


class _AckStream:
    def __init__(self, raw, loop):
        self._raw = raw
        self._loop = loop
        self.entered = 0

    def readline(self):
        self._loop.call_soon_threadsafe(self._bump)
        return self._raw.readline()

    def _bump(self):
        self.entered += 1


class _MemWriter:
    async def write_line(self, message):
        return None


async def main():
    loop = asyncio.get_running_loop()
    stream = _AckStream(sys.stdin.buffer, loop)
    reader = StdioNdjsonLineReader(stream)
    srv = configured_test_agent_server(Path(sys.argv[1]), output_text="done").server
    serve_task = asyncio.create_task(srv.serve_ndjson(reader, _MemWriter()))
    # Wait for the first real blocking read. An early serve failure must surface as its own
    # marker rather than masquerading as "never blocked" -- and never as the success marker.
    for _ in range(400):
        if stream.entered >= 1 or serve_task.done():
            break
        await asyncio.sleep(0.05)
    if serve_task.done():
        _emit("SERVE_DIED")
        exc = serve_task.exception()
        if exc is not None:
            sys.stderr.write("serve died: " + repr(exc) + "\\n")
            sys.stderr.flush()
        return
    if stream.entered < 1:
        _emit("NEVER_BLOCKED")
        return
    _emit("READ_BLOCKED")
    serve_task.cancel()
    try:
        await serve_task
    except asyncio.CancelledError:
        pass
    _emit("TEARDOWN_COMPLETE")

asyncio.run(main())
'''


def _b2_drain(stream, sink, lock):
    try:
        for line in stream:
            with lock:
                sink.append(line.strip())
    finally:
        stream.close()


def _b2_wait_marker(markers, lock, name, bound):
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        with lock:
            if any(entry == name for entry in markers):
                return True
        time.sleep(0.05)
    with lock:
        return any(entry == name for entry in markers)


def _b2_find_prefix(markers, lock, prefix, bound):
    deadline = time.monotonic() + bound
    while time.monotonic() < deadline:
        with lock:
            for entry in markers:
                if entry.startswith(prefix):
                    return entry
        time.sleep(0.05)
    return None


def test_seam4_b2_teardown_completes_in_a_child_while_the_parent_holds_stdin_open(tmp_path):
    """B2: at the process boundary, teardown completion is observable while input is held.

    The child's imported server module is verified to be THIS checkout, not an ambient install.
    The process is expected to stay alive while the parent holds stdin; it must then exit
    naturally with status 0 once input is released. Killing the child is failure cleanup only.
    """
    repo_root = Path(server.__file__).resolve().parents[3]
    workspace = tmp_path / "ws"
    workspace.mkdir()
    script = tmp_path / "b2_child.py"
    script.write_text(_B2_CHILD_SCRIPT, encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(repo_root / "src"), str(repo_root)])
    env.pop("PYTEST_ADDOPTS", None)

    proc = subprocess.Popen(
        [sys.executable, str(script), str(workspace)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
        cwd=str(repo_root),
    )
    markers: list[str] = []
    errors: list[str] = []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=_b2_drain, args=(proc.stdout, markers, lock), daemon=True),
        threading.Thread(target=_b2_drain, args=(proc.stderr, errors, lock), daemon=True),
    ]
    for thread in threads:
        thread.start()

    killed = False
    try:
        module_line = _b2_find_prefix(markers, lock, "MODULE=", B2_BOUND_SECONDS)
        assert module_line is not None, f"child never reported its module binding; stderr={errors}"
        child_module = Path(module_line.split("=", 1)[1])
        assert child_module == (repo_root / "src" / "optimus" / "acp" / "server.py").resolve(), (
            f"child imported {child_module}, not this candidate checkout's server module"
        )
        runtime_line = _b2_find_prefix(markers, lock, "RUNTIME=", B2_BOUND_SECONDS)
        assert runtime_line is not None, "child never reported its runtime"

        assert _b2_wait_marker(markers, lock, "READ_BLOCKED", B2_BOUND_SECONDS), (
            f"child never established a real blocked read; markers={markers} stderr={errors}"
        )
        with lock:
            assert "SERVE_DIED" not in markers and "NEVER_BLOCKED" not in markers, markers

        assert _b2_wait_marker(markers, lock, "TEARDOWN_COMPLETE", B2_BOUND_SECONDS), (
            "coroutine teardown never completed in the child while the parent held stdin open; "
            f"markers={markers} stderr={errors}"
        )
        # Teardown completing does NOT mean the process exited: the worker read is still held.
        assert proc.poll() is None, (
            "the child exited before input was released; this slice does not claim, and must "
            "not accidentally assert, a bounded process exit while a read is outstanding"
        )

        proc.stdin.close()  # release the read; the child may now exit naturally
        exit_code = proc.wait(timeout=B2_BOUND_SECONDS)
        assert exit_code == 0, f"child must exit naturally with 0, got {exit_code}; stderr={errors}"
    except BaseException:
        killed = True
        raise
    finally:
        try:
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            # Failure cleanup only -- never a passing path.
            proc.kill()
            proc.wait(timeout=B2_BOUND_SECONDS)
            assert killed, "the child had to be killed; that is never a passing result"
        for thread in threads:
            thread.join(timeout=SETTLE_BOUND_SECONDS)
