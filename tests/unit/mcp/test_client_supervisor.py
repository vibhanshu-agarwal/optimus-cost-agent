"""RED/GREEN contract for MCPAsyncSupervisor (P11-FU-9 Task 3)."""

from __future__ import annotations

import asyncio
import gc
import inspect
import os
import threading
import time
import warnings
from unittest import mock

import pytest

from optimus.mcp.client_supervisor import (
    MCPAsyncSupervisor,
    MCPSupervisorError,
    MCPSupervisorState,
    select_process_tree_teardown_seam,
)


@pytest.fixture
def supervisor() -> MCPAsyncSupervisor:
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    yield supervisor
    supervisor.close()


def test_start_puts_supervisor_in_running_state() -> None:
    supervisor = MCPAsyncSupervisor()
    assert supervisor.state is MCPSupervisorState.DEAD
    supervisor.start()
    try:
        assert supervisor.state is MCPSupervisorState.RUNNING
    finally:
        supervisor.close()
        assert supervisor.state is MCPSupervisorState.DEAD


def test_submit_runs_coroutine_on_supervisor_loop(supervisor: MCPAsyncSupervisor) -> None:
    async def _probe() -> int:
        await asyncio.sleep(0)
        return 41

    assert supervisor.submit(_probe(), timeout_seconds=2.0) == 41


def test_submit_times_out_and_cancels_slow_coroutine(supervisor: MCPAsyncSupervisor) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _slow() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(MCPSupervisorError) as exc_info:
        supervisor.submit(_slow(), timeout_seconds=0.2)
    assert exc_info.value.code == "SUBMIT_TIMEOUT"
    assert started.is_set()
    deadline = time.monotonic() + 2.0
    while not cancelled.is_set() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert cancelled.is_set()


def test_submit_after_close_returns_safe_dead_error() -> None:
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    supervisor.close()
    assert supervisor.state is MCPSupervisorState.DEAD

    async def _probe() -> str:
        return "nope"

    with pytest.raises(MCPSupervisorError) as exc_info:
        supervisor.submit(_probe(), timeout_seconds=1.0)
    assert exc_info.value.code == "SUPERVISOR_DEAD"


def test_close_cancels_in_flight_and_surfaces_shutdown_error() -> None:
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    entered = asyncio.Event()

    async def _hang() -> None:
        entered.set()
        await asyncio.Event().wait()

    def _run_hang() -> None:
        with pytest.raises(MCPSupervisorError) as exc_info:
            supervisor.submit(_hang(), timeout_seconds=5.0)
        assert exc_info.value.code in {"SUPERVISOR_SHUTDOWN", "SUBMIT_TIMEOUT", "SUPERVISOR_DEAD"}

    worker = threading.Thread(target=_run_hang)
    worker.start()
    deadline = time.monotonic() + 2.0
    while not entered.is_set() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert entered.is_set()
    supervisor.close()
    worker.join(timeout=3.0)
    assert not worker.is_alive()
    assert supervisor.state is MCPSupervisorState.DEAD


def test_process_tree_teardown_seam_selection_is_platform_specific() -> None:
    seam = select_process_tree_teardown_seam()
    if os.name == "nt":
        assert seam == "windows_job_object"
    else:
        assert seam == "posix_process_group"


def test_close_drains_pending_tasks_and_closes_event_loop() -> None:
    """Windows ProactorEventLoop must be closed after join or IOCP handles leak."""
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    loop = supervisor._loop
    assert loop is not None
    entered = threading.Event()

    async def _hang() -> None:
        entered.set()
        await asyncio.Event().wait()

    def _run_hang() -> None:
        with pytest.raises(MCPSupervisorError):
            supervisor.submit(_hang(), timeout_seconds=5.0)

    worker = threading.Thread(target=_run_hang)
    worker.start()
    assert entered.wait(timeout=2.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        supervisor.close()
        worker.join(timeout=3.0)
        assert not worker.is_alive()
        gc.collect()
    assert loop.is_closed()
    assert supervisor.state is MCPSupervisorState.DEAD
    pending = [w for w in caught if "pending" in str(w.message).lower()]
    unclosed = [w for w in caught if "unclosed event loop" in str(w.message)]
    assert not pending, pending
    assert not unclosed, unclosed


def test_submit_after_close_closes_rejected_coroutine() -> None:
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    supervisor.close()

    async def _probe() -> str:
        return "nope"

    coro = _probe()
    with pytest.raises(MCPSupervisorError) as exc_info:
        supervisor.submit(coro, timeout_seconds=1.0)
    assert exc_info.value.code == "SUPERVISOR_DEAD"
    assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED


# --- Seam 5: MCP supervisor lifecycle ownership (frozen matrix v3) ---


def _held_cancel_cleanup(started: threading.Event, cleanup_entered: threading.Event, release: threading.Event):
    """A coroutine whose cancellation cleanup blocks the owning loop thread until released."""

    async def op() -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cleanup_entered.set()
            release.wait(timeout=30)
            raise

    return op


def test_close_join_timeout_accepts_default_and_positive() -> None:
    MCPAsyncSupervisor()
    MCPAsyncSupervisor(close_join_timeout_seconds=5.0)


@pytest.mark.parametrize("bad", [0, -1.0, float("inf"), float("nan")])
def test_close_join_timeout_must_be_finite_positive(bad: float) -> None:
    with pytest.raises(ValueError):
        MCPAsyncSupervisor(close_join_timeout_seconds=bad)


def test_close_timeout_retains_ownership_then_reentrant_finalizes() -> None:
    # Row 1: R2 causal order -- the public submit timeout initiates cancellation,
    # cleanup is acknowledged BEFORE the bounded join, and held through the asserts.
    import optimus.mcp.client_supervisor as mod

    loop_closes: list[threading.Thread] = []
    real_new = asyncio.new_event_loop

    def tracking_new() -> asyncio.AbstractEventLoop:
        loop = real_new()
        real_close = loop.close

        def counting_close() -> None:
            loop_closes.append(threading.current_thread())
            real_close()

        loop.close = counting_close  # type: ignore[method-assign]
        return loop

    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.05)
    with mock.patch.object(mod.asyncio, "new_event_loop", tracking_new):
        sup.start()
    started = threading.Event()
    cleanup_entered = threading.Event()
    release = threading.Event()
    op = _held_cancel_cleanup(started, cleanup_entered, release)

    worker_outcome: list[object] = []

    def worker() -> None:
        try:
            sup.submit(op(), timeout_seconds=0.05)
            worker_outcome.append("UNEXPECTED-RETURN")
        except MCPSupervisorError as exc:
            worker_outcome.append(exc.code)
        except BaseException as exc:  # noqa: BLE001 - recorded, asserted below
            worker_outcome.append(exc)

    captured_loop = sup._loop  # noqa: SLF001
    captured_thread = sup._thread  # noqa: SLF001
    assert captured_thread is not None and captured_loop is not None
    w = threading.Thread(target=worker, name="row1-submit")
    w.start()
    try:
        try:
            assert started.wait(2)
            # public submit timeout cancels the op -> its cleanup holds the loop thread.
            assert cleanup_entered.wait(2)

            sup.close()  # bounded join elapses because the owner thread is held in cleanup
            assert sup.state is MCPSupervisorState.STOPPING
            assert sup._loop is captured_loop  # noqa: SLF001
            assert sup._thread is captured_thread  # noqa: SLF001
            with pytest.raises(MCPSupervisorError):
                sup.start()

            async def _n() -> None:
                return None

            with pytest.raises(MCPSupervisorError):
                sup.submit(_n(), timeout_seconds=1.0)
        finally:
            # Release + joins are protected: a failed assertion above must never
            # strand the held cleanup, the worker, or the owner thread.
            release.set()
            w.join(5)
            captured_thread.join(5)
        assert not w.is_alive()
        assert worker_outcome == ["SUBMIT_TIMEOUT"], worker_outcome
        assert not captured_thread.is_alive()

        sup.close()  # re-entrant finalize once the owner thread has terminated
        assert sup.state is MCPSupervisorState.DEAD
        assert sup._loop is None and sup._thread is None  # noqa: SLF001
        assert captured_loop.is_closed()
        # A started loop is closed exactly once, and by its OWNING thread -- never a caller.
        assert len(loop_closes) == 1, f"expected one physical loop.close, got {len(loop_closes)}"
        assert loop_closes[0] is captured_thread, "started loop must be closed by its owner"
    finally:
        release.set()
        sup.close()  # finalization protected even if an assertion above fails


def test_finalize_requires_the_owner_to_have_closed_its_loop() -> None:
    """I1 residual: a dead owner whose loop was never closed means cleanup did not
    complete on the owning thread. Ownership must be retained, not published DEAD."""
    import optimus.mcp.client_supervisor as mod

    real_new = asyncio.new_event_loop

    def leaky_new() -> asyncio.AbstractEventLoop:
        loop = real_new()
        loop.close = lambda: None  # type: ignore[method-assign]  # owner cannot really close it
        return loop

    with mock.patch.object(mod.asyncio, "new_event_loop", leaky_new):
        sup = MCPAsyncSupervisor(close_join_timeout_seconds=1.0)
        sup.start()
    owner = sup._thread  # noqa: SLF001
    loop = sup._loop  # noqa: SLF001
    assert owner is not None and loop is not None
    try:
        sup.close()
        owner.join(5)
        assert not owner.is_alive()
        assert not loop.is_closed(), "precondition: the owner could not close its loop"
        # Owner gone, loop still open -> no false completion.
        assert sup.state is MCPSupervisorState.STOPPING
        assert sup._loop is loop  # noqa: SLF001
        assert sup._thread is owner  # noqa: SLF001
    finally:
        del loop.close  # restore the real close so the loop does not leak
        loop.close()


def test_repeated_close_during_owner_drain_does_not_abort_cleanup() -> None:
    """I1: a later close() must wait/finalize without re-stopping the owner's drain.

    Re-issuing loop.stop while the owner thread is inside its finally's
    run_until_complete(gather(...)) aborts the drain with RuntimeError, destroys the
    pending cleanup task, and lets _finalize publish DEAD -- a false completion.
    """
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.05)
    entered = threading.Event()
    leave_initial_hold = threading.Event()
    drain_ack = threading.Event()
    cleanup_finished = threading.Event()
    finish_release = threading.Event()
    gate: dict[str, asyncio.Event] = {}
    thread_errors: list[tuple[str, str]] = []
    old_hook = threading.excepthook
    threading.excepthook = lambda args: thread_errors.append(
        (args.exc_type.__name__, str(args.exc_value))
    )

    async def operation() -> None:
        gate["gate"] = asyncio.Event()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            entered.set()
            assert leave_initial_hold.wait(5)
            while not finish_release.is_set():
                try:
                    # Bounded: never an unbounded await, even on the hang path.
                    await asyncio.wait_for(gate["gate"].wait(), timeout=30)
                except asyncio.CancelledError:
                    # The owner's finally has entered its real cancellation drain.
                    drain_ack.set()
                except TimeoutError:
                    break
            cleanup_finished.set()
            raise

    def submitter() -> None:
        with pytest.raises(MCPSupervisorError):
            sup.submit(operation(), timeout_seconds=0.05)

    sup.start()
    loop = sup._loop  # noqa: SLF001
    owner = sup._thread  # noqa: SLF001
    assert loop is not None and owner is not None
    w = threading.Thread(target=submitter, name="i1-submit")
    w.start()
    try:
        assert entered.wait(5)
        sup.close()  # initiator: bounded join elapses while cleanup is held
        assert sup.state is MCPSupervisorState.STOPPING
        assert owner.is_alive()
        leave_initial_hold.set()
        assert drain_ack.wait(5)  # owner is now inside run_until_complete(gather(...))
        sup.close()  # later closer: must NOT stop the loop again
        assert sup.state is MCPSupervisorState.STOPPING, "later close published DEAD mid-drain"
        assert owner.is_alive()
        assert not loop.is_closed()
    finally:
        leave_initial_hold.set()
        finish_release.set()
        if not loop.is_closed() and gate.get("gate") is not None:
            loop.call_soon_threadsafe(gate["gate"].set)
        w.join(5)
        owner.join(5)
        sup.close()
        threading.excepthook = old_hook

    assert cleanup_finished.is_set(), "owner cleanup was destroyed instead of completing"
    assert thread_errors == [], f"owner thread raised: {thread_errors}"
    assert sup.state is MCPSupervisorState.DEAD


def test_start_refused_across_entire_stopping_window() -> None:
    # Row 2b: start() refuses throughout STOPPING, including thread-dead-but-not-finalized.
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.05)
    sup.start()
    started = threading.Event()
    cleanup_entered = threading.Event()
    release = threading.Event()
    op = _held_cancel_cleanup(started, cleanup_entered, release)

    worker_outcome: list[object] = []

    def worker() -> None:
        try:
            sup.submit(op(), timeout_seconds=0.05)
            worker_outcome.append("UNEXPECTED-RETURN")
        except MCPSupervisorError as exc:
            worker_outcome.append(exc.code)
        except BaseException as exc:  # noqa: BLE001 - recorded, asserted below
            worker_outcome.append(exc)

    captured_thread = sup._thread  # noqa: SLF001
    assert captured_thread is not None
    w = threading.Thread(target=worker, name="row2b-submit")
    w.start()
    try:
        try:
            assert started.wait(2)
            assert cleanup_entered.wait(2)
            sup.close()  # retain: thread alive
            assert sup.state is MCPSupervisorState.STOPPING
            with pytest.raises(MCPSupervisorError):  # thread-alive STOPPING window
                sup.start()
        finally:
            # Release + joins protected: a failed assertion must not strand cleanup.
            release.set()
            w.join(5)
            captured_thread.join(5)
        assert not w.is_alive()
        assert worker_outcome == ["SUBMIT_TIMEOUT"], worker_outcome
        assert not captured_thread.is_alive()

        # thread-dead-but-not-finalized STOPPING window: start still refused.
        assert sup.state is MCPSupervisorState.STOPPING
        with pytest.raises(MCPSupervisorError):
            sup.start()

        sup.close()  # finalize -> DEAD
        assert sup.state is MCPSupervisorState.DEAD
        sup.start()  # admitted only after finalization
        assert sup.state is MCPSupervisorState.RUNNING
    finally:
        release.set()
        sup.close()  # finalization protected even if an assertion above fails


def test_two_closer_chronology_preserves_new_generation() -> None:
    # Row 2: a stale closer (captured generation G) must not clear a newer generation G+1.
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.05)
    sup.start()

    real_finalize = sup._finalize  # noqa: SLF001
    both_at_finalize = threading.Barrier(2)
    idx_lock = threading.Lock()
    idx = {"n": 0}
    a_finalized = threading.Event()
    b_may_proceed = threading.Event()

    def sequenced_finalize(gen: int, thread: object) -> None:
        both_at_finalize.wait(timeout=10)
        with idx_lock:
            idx["n"] += 1
            mine = idx["n"]
        if mine == 1:
            real_finalize(gen, thread)  # closer A finalizes generation G -> DEAD
            a_finalized.set()
        else:
            assert b_may_proceed.wait(10)
            real_finalize(gen, thread)  # closer B is stale (generation G); must no-op

    sup._finalize = sequenced_finalize  # type: ignore[method-assign]  # noqa: SLF001

    closers = [threading.Thread(target=sup.close, name=f"closer-{i}") for i in range(2)]
    for c in closers:
        c.start()

    ran: list[int] = []

    async def sentinel() -> str:
        ran.append(1)
        return "ok"

    try:
        assert a_finalized.wait(10)
        assert sup.state is MCPSupervisorState.DEAD
        sup._finalize = real_finalize  # type: ignore[method-assign]  # noqa: SLF001
        sup.start()  # generation G+1
        gen2_thread = sup._thread  # noqa: SLF001
        assert sup.state is MCPSupervisorState.RUNNING and gen2_thread is not None

        # G+1 must be a real working owner: a sentinel actually executes on it, once.
        assert sup.submit(sentinel(), timeout_seconds=5) == "ok"
        assert len(ran) == 1

        b_may_proceed.set()
        for c in closers:
            c.join(10)

        # The stale closer B must not have touched generation G+1 ...
        assert sup.state is MCPSupervisorState.RUNNING
        assert sup._thread is gen2_thread  # noqa: SLF001
        assert gen2_thread.is_alive()
        # ... and G+1 is still functional after the stale finalization attempt.
        assert sup.submit(sentinel(), timeout_seconds=5) == "ok"
        assert len(ran) == 2
    finally:
        b_may_proceed.set()
        for c in closers:
            c.join(10)
        sup.close()
    assert sup.state is MCPSupervisorState.DEAD


def test_thread_construct_failure_rolls_back_loop() -> None:
    import optimus.mcp.client_supervisor as mod

    created: list[asyncio.AbstractEventLoop] = []
    closed_by: list[threading.Thread] = []
    real_new = asyncio.new_event_loop

    def tracking_new() -> asyncio.AbstractEventLoop:
        loop = real_new()
        real_close = loop.close

        def recording_close() -> None:
            closed_by.append(threading.current_thread())
            real_close()

        loop.close = recording_close  # type: ignore[method-assign]
        created.append(loop)
        return loop

    class BoomConstruct:
        def __init__(self, *a: object, **k: object) -> None:
            raise RuntimeError("construct boom")

    sup = MCPAsyncSupervisor()
    with (
        mock.patch.object(mod.asyncio, "new_event_loop", tracking_new),
        mock.patch.object(mod.threading, "Thread", BoomConstruct),
    ):
        with pytest.raises(RuntimeError, match="construct boom"):
            sup.start()

    assert sup.state is MCPSupervisorState.DEAD
    assert sup._loop is None and sup._thread is None  # noqa: SLF001
    assert created and created[-1].is_closed()
    # Close-thread ownership: a loop whose thread never started is closed by the STARTUP
    # CALLER (this thread) -- never by a supervisor thread, which does not exist here.
    assert closed_by == [threading.current_thread()], closed_by
    # Recovery + ownership: the next start owns a fresh generation that really runs work.
    generation_before = sup._generation  # noqa: SLF001
    sup.start()
    try:
        assert sup.state is MCPSupervisorState.RUNNING
        assert sup._generation == generation_before + 1  # noqa: SLF001
        assert sup._loop is not None and sup._thread is not None  # noqa: SLF001

        async def _sentinel() -> str:
            return "ok"

        assert sup.submit(_sentinel(), timeout_seconds=5) == "ok"
    finally:
        sup.close()
    assert sup.state is MCPSupervisorState.DEAD


def test_thread_start_failure_rolls_back_loop() -> None:
    import optimus.mcp.client_supervisor as mod

    created: list[asyncio.AbstractEventLoop] = []
    closed_by: list[threading.Thread] = []
    real_new = asyncio.new_event_loop

    def tracking_new() -> asyncio.AbstractEventLoop:
        loop = real_new()
        real_close = loop.close

        def recording_close() -> None:
            closed_by.append(threading.current_thread())
            real_close()

        loop.close = recording_close  # type: ignore[method-assign]
        created.append(loop)
        return loop

    class BoomStart(threading.Thread):
        def start(self) -> None:
            raise RuntimeError("start boom")

    sup = MCPAsyncSupervisor()
    with (
        mock.patch.object(mod.asyncio, "new_event_loop", tracking_new),
        mock.patch.object(mod.threading, "Thread", BoomStart),
    ):
        with pytest.raises(RuntimeError, match="start boom"):
            sup.start()

    assert sup.state is MCPSupervisorState.DEAD
    assert sup._loop is None and sup._thread is None  # noqa: SLF001
    assert created and created[-1].is_closed()
    # Close-thread ownership: a loop whose thread never started is closed by the STARTUP
    # CALLER (this thread) -- never by a supervisor thread, which does not exist here.
    assert closed_by == [threading.current_thread()], closed_by
    # Recovery + ownership: the next start owns a fresh generation that really runs work.
    generation_before = sup._generation  # noqa: SLF001
    sup.start()
    try:
        assert sup.state is MCPSupervisorState.RUNNING
        assert sup._generation == generation_before + 1  # noqa: SLF001
        assert sup._loop is not None and sup._thread is not None  # noqa: SLF001

        async def _sentinel() -> str:
            return "ok"

        assert sup.submit(_sentinel(), timeout_seconds=5) == "ok"
    finally:
        sup.close()
    assert sup.state is MCPSupervisorState.DEAD


# --------------------------------------------------------------------------------------
# R2 (Codex review): phase-specific ownership tests for the interval AFTER the owner has
# closed its loop and BEFORE its thread terminates. In that window the owner-closed-loop
# check no longer retains ownership, so only the live-owner check (S1) protects a draining
# owner, and only the generation check (S3) protects a live newer owner from a stale
# closer. Real threads and real loops throughout; the loop's real close() runs first and
# its return is acknowledged before the owner is held.
# --------------------------------------------------------------------------------------


def _hold_owner_after_real_loop_close(sup: MCPAsyncSupervisor):
    """Start `sup`, then arrange for its owner to close its loop for real, acknowledge that,
    and hold before terminating. Returns (owner, loop, reached, release, failures)."""
    sup.start()
    owner, loop = sup._thread, sup._loop  # noqa: SLF001
    assert owner is not None and loop is not None
    reached = threading.Event()
    release = threading.Event()
    failures: list[str] = []
    real_close = loop.close

    def close_then_hold() -> None:
        real_close()  # the genuine loop close, on the owning thread
        reached.set()
        if not release.wait(10):
            failures.append("owner release timed out")

    loop.close = close_then_hold  # type: ignore[method-assign]
    return owner, loop, reached, release, failures


def test_close_retains_a_live_owner_after_its_loop_has_closed() -> None:
    """S1 alone must be killed: with the loop already closed, only the live-owner check
    stands between a draining owner and a false DEAD."""
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.1)
    owner, loop, reached, release, failures = _hold_owner_after_real_loop_close(sup)
    try:
        sup.close()  # bounded join elapses: the owner is held after closing its loop
        assert reached.wait(2), "the owner never reached the post-loop-close phase"
        assert owner.is_alive() and loop.is_closed(), "precondition: live owner, closed loop"
        assert sup.state is MCPSupervisorState.STOPPING, "a live owner was published DEAD"
        assert sup._thread is owner, "the live owner's thread reference was erased"  # noqa: SLF001
        assert sup._loop is loop, "the live owner's loop reference was erased"  # noqa: SLF001
        with pytest.raises(MCPSupervisorError):
            sup.start()
    finally:
        release.set()
        owner.join(5)
        sup.close()
    assert not owner.is_alive() and failures == [], failures
    assert sup.state is MCPSupervisorState.DEAD
    assert sup._thread is None and sup._loop is None  # noqa: SLF001


def test_stale_closer_cannot_erase_a_new_owner_after_its_loop_has_closed() -> None:
    """S3 alone must be killed: a stale closer resuming while the NEW owner is alive with its
    loop already closed sees a dead captured thread and a closed current loop; only the
    generation check keeps it from erasing the live new owner."""
    sup = MCPAsyncSupervisor(close_join_timeout_seconds=0.1)
    sup.start()
    old_owner = sup._thread  # noqa: SLF001
    old_generation = sup._generation  # noqa: SLF001
    assert old_owner is not None
    stale_reached = threading.Event()
    stale_release = threading.Event()
    stale_errors: list[str] = []
    real_finalize = sup._finalize  # noqa: SLF001

    def pause_stale(generation: int, thread: object) -> None:
        if threading.current_thread().name == "seam5-stale-closer":
            stale_reached.set()
            if not stale_release.wait(10):
                stale_errors.append("stale release timed out")
        return real_finalize(generation, thread)

    sup._finalize = pause_stale  # type: ignore[method-assign]  # noqa: SLF001

    def stale_close() -> None:
        try:
            sup.close()
        except BaseException as exc:  # noqa: BLE001 - collected and asserted
            stale_errors.append(repr(exc))

    stale = threading.Thread(target=stale_close, name="seam5-stale-closer")
    stale.start()
    new_owner = new_loop = release = None
    failures: list[str] = []
    try:
        assert stale_reached.wait(2), "the stale closer never reached finalization"
        old_owner.join(2)
        assert not old_owner.is_alive(), "precondition: the old owner must have terminated"
        sup.close()  # a second real closer finalizes the old generation
        assert sup.state is MCPSupervisorState.DEAD

        new_owner, new_loop, reached, release, failures = _hold_owner_after_real_loop_close(sup)
        assert sup._generation == old_generation + 1  # noqa: SLF001
        sup.close()
        assert reached.wait(2), "the new owner never reached the post-loop-close phase"
        assert new_owner.is_alive() and new_loop.is_closed()
        assert sup.state is MCPSupervisorState.STOPPING
        assert sup._thread is new_owner and sup._loop is new_loop  # noqa: SLF001

        stale_release.set()  # the stale closer (old generation) now finalizes
        stale.join(2)
        assert not stale.is_alive() and stale_errors == [], stale_errors
        assert sup.state is MCPSupervisorState.STOPPING, "a stale closer erased a live new owner"
        assert sup._thread is new_owner, "the new owner's thread reference was erased"  # noqa: SLF001
        assert sup._loop is new_loop, "the new owner's loop reference was erased"  # noqa: SLF001
    finally:
        stale_release.set()
        if release is not None:
            release.set()
        stale.join(2)
        if new_owner is not None:
            new_owner.join(5)
        sup.close()
    assert not stale.is_alive() and stale_errors == [], stale_errors
    if new_owner is not None:
        assert not new_owner.is_alive() and failures == [], failures
    assert sup.state is MCPSupervisorState.DEAD
