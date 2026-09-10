"""Seam 2, checkpoint A: the per-runtime Redis loop owner contract.

Every test here owns its owner explicitly and closes it, including on the failure
path. Nothing in this module asserts on a process-wide thread-name search: an owner
is observed through its own loop and its own thread.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from concurrent.futures import CancelledError as FutureCancelledError

import pytest

from optimus.redis.async_bridge import (
    RedisLoopOwner,
    RedisLoopOwnerClosed,
    RedisLoopOwnerShutdownIncomplete,
    RedisLoopOwnerState,
)


@pytest.fixture
def owner():
    """An owned loop owner whose lifetime ends with the test, however it ends."""
    made = RedisLoopOwner(name="optimus-redis-owner-under-test")
    try:
        yield made
    finally:
        try:
            made.close(timeout=5.0)
        except RedisLoopOwnerShutdownIncomplete:
            pass


def test_operation_factory_is_entered_on_the_owner_loop_not_the_caller(owner):
    """The factory must be *called* on the owner loop, not merely awaited there."""
    caller_thread = threading.get_ident()
    seen: dict[str, object] = {}

    async def _operation():
        seen["thread"] = threading.get_ident()
        seen["loop"] = asyncio.get_running_loop()
        return "done"

    def _factory():
        seen["factory_thread"] = threading.get_ident()
        return _operation()

    assert owner.run_sync(_factory) == "done"
    assert seen["factory_thread"] != caller_thread
    assert seen["thread"] == owner.thread.ident
    assert seen["loop"] is not None


def test_states_progress_from_open_to_closed(owner):
    assert owner.state is RedisLoopOwnerState.OPEN
    owner.close(timeout=5.0)
    assert owner.state is RedisLoopOwnerState.CLOSED
    assert owner.is_terminated


def test_submission_after_admission_closes_is_refused(owner):
    """MUTATION: submission after admission closes."""
    owner.close(timeout=5.0)

    async def _operation():  # pragma: no cover - must never be entered
        raise AssertionError("the operation ran after admission closed")

    with pytest.raises(RedisLoopOwnerClosed):
        owner.run_sync(lambda: _operation())


def test_admission_is_refused_while_the_owner_loop_is_still_alive(owner):
    """MUTATION: submission after admission closes.

    Refusing work once the loop is already *dead* proves very little: the closed loop
    would reject the submission on its own. The load-bearing window is CLOSING, while
    the loop is still running and could still happily accept work in the middle of
    teardown. This test holds the owner open in exactly that state.
    """
    entered = threading.Event()
    release = threading.Event()

    async def _stubborn():
        entered.set()
        while not release.is_set():
            try:
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                pass

    submitter = threading.Thread(
        target=lambda: owner._submit(lambda: _stubborn()),  # noqa: SLF001 - direct submission
        name="seam2-stubborn-submitter",
    )
    submitter.start()
    submitter.join(5)
    assert entered.wait(5)

    try:
        with pytest.raises(RedisLoopOwnerShutdownIncomplete):
            owner.close(timeout=0.2)

        # The loop is STILL ALIVE, so any refusal below can only come from admission.
        assert owner.thread_is_alive
        assert not owner.loop_is_closed
        assert owner.state is RedisLoopOwnerState.CLOSING

        ran = threading.Event()

        async def _late():
            ran.set()

        with pytest.raises(RedisLoopOwnerClosed):
            owner.run_sync(lambda: _late())
        assert not ran.is_set(), "work was admitted while the owner was closing"
    finally:
        release.set()


def test_a_closed_owner_never_constructs_a_replacement_loop(owner):
    """MUTATION: replacement owner after timeout."""
    loop_before = owner._loop  # noqa: SLF001 - identity is the assertion
    thread_before = owner.thread
    owner.close(timeout=5.0)

    async def _operation():  # pragma: no cover - must never be entered
        raise AssertionError("a replacement loop accepted work")

    for _ in range(3):
        with pytest.raises(RedisLoopOwnerClosed):
            owner.run_sync(lambda: _operation())
    assert owner._loop is loop_before  # noqa: SLF001
    assert owner.thread is thread_before
    assert owner.is_terminated


def test_run_sync_from_inside_the_owner_thread_is_rejected(owner):
    """A blocking submission from the owner thread would deadlock it."""
    captured: dict[str, BaseException | None] = {"error": None}

    async def _operation():
        try:
            owner.run_sync(lambda: asyncio.sleep(0))
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            captured["error"] = exc
        return None

    owner.run_sync(_operation)
    assert isinstance(captured["error"], RuntimeError)
    assert "must not be called from inside the owner loop" in str(captured["error"])


def test_cancel_before_first_step_never_enters_the_operation(owner):
    """A pre-start cancellation must be honoured before the factory's awaitable runs."""
    entered = threading.Event()

    async def _never():  # pragma: no cover - must never be entered
        entered.set()
        return None

    async def _drive():
        task = asyncio.create_task(owner.run_async(lambda: _never()))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())
    assert not entered.is_set()


def test_repeated_cancellation_does_not_destroy_owner_side_observation(owner):
    """MUTATION: cancellation that destroys observation.

    This is the tagged implementation's second counterexample. After the first
    cancellation the owner-side operation is unwinding; a *second* cancellation must
    not make the caller terminal while that unwind is still in flight.
    """
    entered = threading.Event()
    cleanup = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    async def _operation():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            while not release.is_set():
                try:
                    await asyncio.sleep(0.005)
                except asyncio.CancelledError:
                    pass
            finished.set()

    async def _drive():
        task = asyncio.create_task(owner.run_async(lambda: _operation()))

        async def _until(event):
            async with asyncio.timeout(5):
                while not event.is_set():
                    await asyncio.sleep(0.005)

        await _until(entered)
        task.cancel()
        await _until(cleanup)
        task.cancel()

        # The caller must STILL be observing: the owner-side operation has not
        # finished, so going terminal here would be the defect.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 0.5)
        assert not task.done(), "caller went terminal while owner-side work was unfinished"
        assert not finished.is_set()

        # Once the owner-side work really settles, the caller settles too.
        release.set()
        await _until(finished)
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())
    assert finished.is_set()


def test_close_settles_callers_blocked_on_unfinished_work(owner):
    """A closed loop must release its observers rather than stranding them."""
    entered = threading.Event()
    released: dict[str, BaseException | None] = {"error": None}

    async def _operation():
        entered.set()
        await asyncio.Event().wait()

    def _submit():
        try:
            owner.run_sync(lambda: _operation())
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            released["error"] = exc

    caller = threading.Thread(target=_submit, name="seam2-blocked-caller")
    caller.start()
    assert entered.wait(5)
    owner.close(timeout=5.0)
    caller.join(5)
    assert not caller.is_alive(), "the blocked caller was stranded by close()"
    # Either terminal state is honest: the work was cancelled, or the loop closed
    # under it. What must never happen is the caller waiting forever.
    assert isinstance(
        released["error"],
        (RedisLoopOwnerClosed, asyncio.CancelledError, FutureCancelledError),
    ), released["error"]


def test_incomplete_shutdown_is_reported_and_the_owner_is_retained(owner):
    """MUTATION: false clean outcome with a live thread."""
    entered = threading.Event()
    release = threading.Event()

    async def _stubborn():
        entered.set()
        while not release.is_set():
            try:
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                pass

    owner.run_sync(lambda: asyncio.sleep(0))  # prove the owner works first
    handle_thread = threading.Thread(
        target=lambda: owner._submit(lambda: _stubborn()),  # noqa: SLF001 - direct submission
        name="seam2-stubborn-submitter",
    )
    handle_thread.start()
    handle_thread.join(5)
    assert entered.wait(5)

    thread_before = owner.thread
    with pytest.raises(RedisLoopOwnerShutdownIncomplete):
        owner.close(timeout=0.2)
    # Retained, never replaced, and never reported terminated while alive.
    assert owner.thread is thread_before
    assert owner.thread_is_alive
    assert not owner.is_terminated
    assert owner.state is RedisLoopOwnerState.CLOSING

    release.set()
    for _ in range(200):
        if owner.is_terminated:
            break
        time.sleep(0.025)
    assert owner.is_terminated
    assert owner.state is RedisLoopOwnerState.CLOSED


def test_is_terminated_is_owner_identity_not_a_process_wide_name(owner):
    """Negative control: a live owner and an unrelated same-named thread.

    A name-based oracle would answer this wrongly in both directions.
    """
    decoy_release = threading.Event()
    decoy = threading.Thread(
        target=decoy_release.wait,
        name=owner.thread.name,  # deliberately the SAME name
        daemon=True,
    )
    decoy.start()
    try:
        assert owner.thread_is_alive
        assert not owner.is_terminated

        owner.close(timeout=5.0)

        # This owner really terminated, even though a thread of the same name is
        # still alive; and the decoy is not mistaken for the owner.
        assert owner.is_terminated
        assert owner.loop_is_closed
        assert not owner.thread_is_alive
        assert decoy.is_alive()
        assert any(thread.name == owner.thread.name for thread in threading.enumerate())
    finally:
        decoy_release.set()
        decoy.join(5)


def test_close_is_idempotent_and_repeats_no_cancellation(owner):
    owner.close(timeout=5.0)
    owner.close(timeout=5.0)
    assert owner.is_terminated
    assert owner.state is RedisLoopOwnerState.CLOSED


# --- Review round 1: R3/R4 corrections ------------------------------------------


def test_drain_retains_pending_work_instead_of_discarding_it(owner):
    """R4: a fixed drain deadline must not destroy pending tasks and call them settled."""
    entered, release, finished = (threading.Event() for _ in range(3))

    async def _stubborn():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            while not release.is_set():
                try:
                    await asyncio.sleep(0.005)
                except asyncio.CancelledError:
                    pass
            finished.set()

    handle = owner.submit(_stubborn)
    assert entered.wait(5)

    with pytest.raises(RedisLoopOwnerShutdownIncomplete):
        owner.close(timeout=0.2)
    assert not owner.is_terminated, "termination was claimed while the loop was alive"
    assert not finished.is_set(), "work was reported finished before it unwound"

    release.set()
    for _ in range(400):
        if owner.is_terminated:
            break
        time.sleep(0.025)
    assert finished.is_set(), "pending work was discarded rather than unwound"
    assert owner.is_terminated
    with contextlib.suppress(BaseException):
        handle.future.result(1)


def test_shared_tool_owner_is_retained_never_replaced_while_live():
    """R3: a live shared owner must not be dropped and replaced by a new one."""
    from optimus.redis import async_bridge

    entered, release = threading.Event(), threading.Event()
    original_budget = async_bridge.SHUTDOWN_OBSERVATION_BUDGET_SECONDS
    async_bridge.SHUTDOWN_OBSERVATION_BUDGET_SECONDS = 0.05
    old = async_bridge._acquire_shared_tool_owner()  # noqa: SLF001

    def _block():
        entered.set()
        release.wait(20)

    old._loop.call_soon_threadsafe(_block)  # noqa: SLF001
    assert entered.wait(5)
    try:
        with pytest.raises(RedisLoopOwnerShutdownIncomplete):
            async_bridge.shutdown_background_loop()

        # The slot still holds the SAME live owner, and acquisition is refused rather
        # than silently handing out a replacement loop.
        assert async_bridge._shared_tool_owner is old  # noqa: SLF001
        assert old.thread_is_alive
        with pytest.raises(RedisLoopOwnerClosed):
            async_bridge._acquire_shared_tool_owner()  # noqa: SLF001
    finally:
        release.set()
        old.close(timeout=10)
        async_bridge.shutdown_background_loop()
        async_bridge.SHUTDOWN_OBSERVATION_BUDGET_SECONDS = original_budget

    # Only after verified termination may the slot be reused -- and the new owner is a
    # genuinely different lifetime, never a revival of the old one.
    assert old.is_terminated
    assert async_bridge._shared_tool_owner is None  # noqa: SLF001
    fresh = async_bridge._acquire_shared_tool_owner()  # noqa: SLF001
    try:
        assert fresh is not old
    finally:
        async_bridge.shutdown_background_loop()


def test_startup_timeout_hands_back_retained_custody(monkeypatch):
    """R4: a blocked startup must expose the owner, not strand an unreferenced thread."""
    from optimus.redis import async_bridge

    release = threading.Event()
    monkeypatch.setattr(async_bridge, "_START_TIMEOUT_SECONDS", 0.1)

    def _wedged_run_forever(self):
        # A real, live thread that never reaches readiness -- the actual shape of a
        # startup wedge, not an unstarted thread.
        release.wait(30)

    monkeypatch.setattr(async_bridge.RedisLoopOwner, "_run_forever", _wedged_run_forever)

    with pytest.raises(async_bridge.RedisLoopOwnerStartupIncomplete) as excinfo:
        async_bridge.RedisLoopOwner(name="optimus-redis-owner-startup-wedge")

    retained = excinfo.value.owner
    try:
        assert isinstance(retained, async_bridge.RedisLoopOwner)
        assert retained.state is not RedisLoopOwnerState.OPEN
        # Retained custody is the point: the caller is handed a live owner it can
        # observe, rather than an unreferenced thread nobody holds.
        assert retained.thread_is_alive
        assert not retained.is_terminated
    finally:
        release.set()
        # Observe termination through the owner: once the wedged thread has died the owner
        # closes the loop it never ran, so a retained-then-released wedge leaves no
        # orphaned loop behind (round 2: an ordering-dependent unclosed-loop warning).
        terminated = retained.wait_terminated(10)
    assert not retained.thread_is_alive
    assert terminated and retained.is_terminated and retained.loop_is_closed


def test_a_failing_admission_guard_prevents_registration_entirely(owner):
    """R2: the guard decides admission INSIDE the registration lock.

    If the guard were consulted outside that lock -- or not at all -- a caller could be
    registered and its operation entered despite the guard's refusal, which is the race
    the atomic step exists to close.
    """
    ran = threading.Event()

    class _Refused(RuntimeError):
        pass

    def _guard():
        raise _Refused("refused by the runtime")

    async def _operation():  # pragma: no cover - must never be entered
        ran.set()

    live_before = len(owner._live)  # noqa: SLF001
    with pytest.raises(_Refused):
        owner.submit(lambda: _operation(), guard=_guard)

    assert not ran.is_set(), "the operation ran despite a refusing guard"
    assert len(owner._live) == live_before, "a refused submission was still registered"  # noqa: SLF001
    assert owner.state is RedisLoopOwnerState.OPEN



def _dead_before_loop_owner(monkeypatch, name: str):
    from optimus.redis import async_bridge

    monkeypatch.setattr(async_bridge, "_START_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(async_bridge.RedisLoopOwner, "_run_forever", lambda self: None)
    with pytest.raises(async_bridge.RedisLoopOwnerStartupIncomplete) as excinfo:
        async_bridge.RedisLoopOwner(name=name)
    return excinfo.value.owner


def _hold_native_loop_close(monkeypatch, owner):
    """Park the ONE native cleanup of a dead owner's loop; count its entries."""
    entered, release = threading.Event(), threading.Event()
    entries: list[int] = []
    original_close = owner._loop.close  # noqa: SLF001

    def _held_close():
        entries.append(1)
        entered.set()
        assert release.wait(10), "the test never released native cleanup"
        original_close()

    monkeypatch.setattr(owner._loop, "close", _held_close)  # noqa: SLF001
    return entered, release, entries


def _observer(owner, kind: str):
    outcome: dict[str, object] = {}

    def _run():
        try:
            outcome["value"] = owner.close(timeout=5) if kind == "close" else owner.wait_terminated(5)
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            outcome["error"] = exc

    thread = threading.Thread(target=_run, name=f"observer-{kind}")
    return thread, outcome


@pytest.mark.parametrize("kinds", [("close", "close"), ("close", "wait"), ("wait", "wait")])
def test_concurrent_observers_share_one_finalization_of_a_dead_thread(monkeypatch, kinds):
    """R11 MUTATION: two observers entered native loop cleanup at once (AttributeError on
    the second; two cleanup entries). Now: one claim, one native cleanup, one outcome."""
    retained = _dead_before_loop_owner(monkeypatch, f"optimus-redis-owner-concurrent-{'-'.join(kinds)}")
    entered, release, entries = _hold_native_loop_close(monkeypatch, retained)
    first, first_outcome = _observer(retained, kinds[0])
    second, second_outcome = _observer(retained, kinds[1])
    try:
        first.start()
        assert entered.wait(5), "the first observer never claimed finalization"
        second.start()
        second.join(0.3)
        assert second.is_alive(), "the second observer returned while finalization was still pending"
        assert retained.state is not RedisLoopOwnerState.CLOSED, "CLOSED published before cleanup completed"
        assert not retained.loop_is_closed
    finally:
        release.set()
        first.join(10)
        second.join(10)
    assert not first.is_alive() and not second.is_alive()
    assert entries == [1], "native loop cleanup ran more than once"
    for kind, outcome in ((kinds[0], first_outcome), (kinds[1], second_outcome)):
        assert "error" not in outcome, f"{kind} observer failed: {outcome.get('error')!r}"
        assert outcome["value"] == (None if kind == "close" else True)
    assert retained.is_terminated and retained.loop_is_closed
    assert retained.state is RedisLoopOwnerState.CLOSED


def test_every_observer_respects_its_own_budget_while_finalization_is_pending(monkeypatch):
    """R11 MUTATION: the first observer blocked inside native cleanup past a 10 ms budget.
    Now the claimer waits on the retained finalization for what remains of ITS budget,
    reports incomplete, and a later observer sees the finalization's real outcome."""
    retained = _dead_before_loop_owner(monkeypatch, "optimus-redis-owner-budget")
    entered, release, entries = _hold_native_loop_close(monkeypatch, retained)
    outcome: dict[str, object] = {}

    def _bounded():
        started = time.monotonic()
        try:
            retained.close(timeout=0.05)
            outcome["result"] = "returned"
        except RedisLoopOwnerShutdownIncomplete:
            outcome["result"] = "incomplete"
        finally:
            outcome["elapsed"] = time.monotonic() - started

    observer = threading.Thread(target=_bounded)
    try:
        observer.start()
        assert entered.wait(5)
        observer.join(2.0)
        assert not observer.is_alive(), "the bounded observer stayed blocked inside pending finalization"
        assert outcome["result"] == "incomplete"
        assert retained.state is not RedisLoopOwnerState.CLOSED
        assert not retained.loop_is_closed and not retained.is_terminated
        # A second bounded observer while still pending: also incomplete, still ONE cleanup.
        assert retained.wait_terminated(0.05) is False
        assert entries == [1]
    finally:
        release.set()
    assert retained.wait_terminated(5) is True
    retained.close(timeout=1)
    assert retained.is_terminated and retained.state is RedisLoopOwnerState.CLOSED
    assert entries == [1]


def test_a_finalization_failure_is_retained_and_observed_consistently(monkeypatch):
    """A real cleanup failure reaches the first AND later observers, through both entries."""
    retained = _dead_before_loop_owner(monkeypatch, "optimus-redis-owner-finalization-failure")
    original_close = retained._loop.close  # noqa: SLF001
    failures: list[int] = []

    def _failing_close():
        failures.append(1)
        raise OSError("native loop cleanup failed")

    monkeypatch.setattr(retained._loop, "close", _failing_close)  # noqa: SLF001
    try:
        with pytest.raises(OSError, match="native loop cleanup failed"):
            retained.close(timeout=2)
        with pytest.raises(OSError, match="native loop cleanup failed"):
            retained.wait_terminated(2)
        with pytest.raises(OSError, match="native loop cleanup failed"):
            retained.close(timeout=2)
        assert failures == [1], "cleanup was retried instead of retained"
        assert retained.state is not RedisLoopOwnerState.CLOSED
        assert not retained.is_terminated
    finally:
        # The retained failure is honest; do not leave the real loop open behind the test.
        original_close()


@pytest.mark.parametrize("eventual", ["success", "failure"])
def test_success_is_not_reported_until_the_retained_finalization_completes(monkeypatch, eventual):
    """R13 MUTATION: with the loop already PHYSICALLY closed but the finalizer not yet
    published, `close` returned and `wait_terminated` said True while another observer
    later saw the finalization fail. The retained outcome governs, on both sides of the
    physical flag, for the first, a concurrent and a later observer."""
    retained = _dead_before_loop_owner(monkeypatch, f"optimus-redis-owner-outcome-{eventual}")
    native_close = retained._loop.close  # noqa: SLF001
    closed, release = threading.Event(), threading.Event()
    terminal_error = OSError("finalizer failed after the physical loop close")

    def _close_then_park():
        native_close()  # the loop is now PHYSICALLY closed ...
        closed.set()
        assert release.wait(10)  # ... but the finalization has not published its outcome
        if eventual == "failure":
            raise terminal_error

    monkeypatch.setattr(retained._loop, "close", _close_then_park)  # noqa: SLF001
    concurrent, concurrent_outcome = _observer(retained, "wait")
    try:
        with pytest.raises(RedisLoopOwnerShutdownIncomplete):
            retained.close(timeout=0.05)
        assert closed.wait(5)
        assert retained.is_terminated, "the physical predicate is unchanged"
        assert retained.wait_terminated(0.01) is False, "bounded wait reported success while pending"
        with pytest.raises(RedisLoopOwnerShutdownIncomplete):
            retained.close(timeout=0.01)
        assert not retained._finalization.done()  # noqa: SLF001
        assert retained.state is not RedisLoopOwnerState.CLOSED
        concurrent.start()
        concurrent.join(0.2)
        assert concurrent.is_alive(), "a concurrent observer returned while the outcome was pending"
    finally:
        release.set()
        concurrent.join(10)
    if eventual == "success":
        retained.close(timeout=3)
        assert retained.wait_terminated(1) is True
        assert retained.state is RedisLoopOwnerState.CLOSED
        assert concurrent_outcome.get("value") is True and "error" not in concurrent_outcome
    else:
        with pytest.raises(OSError) as first:
            retained.close(timeout=3)
        with pytest.raises(OSError) as second:
            retained.wait_terminated(1)
        assert first.value is terminal_error and second.value is terminal_error
        assert concurrent_outcome.get("error") is terminal_error
        assert retained.state is not RedisLoopOwnerState.CLOSED


def test_a_finalizer_launch_failure_is_published_to_every_observer(monkeypatch):
    """R13 MUTATION: a failed `Thread.start` left the claimed future pending forever --
    later observers could only time out. The launch failure is now the retained outcome."""
    retained = _dead_before_loop_owner(monkeypatch, "optimus-redis-owner-launch-failure")
    native_close = retained._loop.close  # noqa: SLF001
    launch_error = RuntimeError("finalizer thread could not start")
    starts: list[int] = []

    def _failing_start(self):
        starts.append(1)
        raise launch_error

    monkeypatch.setattr(threading.Thread, "start", _failing_start)
    try:
        with pytest.raises(RuntimeError) as first:
            retained.close(timeout=0.05)
        assert first.value is launch_error
        with pytest.raises(RuntimeError) as later:
            retained.close(timeout=0.01)
        assert later.value is launch_error, "a later observer did not see the retained launch failure"
        with pytest.raises(RuntimeError) as waited:
            retained.wait_terminated(0.01)
        assert waited.value is launch_error
        assert retained._finalization is not None and retained._finalization.done()  # noqa: SLF001
        assert starts == [1], "a replacement finalizer was launched"
        assert retained.state is not RedisLoopOwnerState.CLOSED
        assert not retained.loop_is_closed, "custody was not retained honestly"
    finally:
        monkeypatch.undo()
        native_close()


def test_public_close_finalizes_a_dead_thread_that_left_its_loop_open(monkeypatch):
    """R9 MUTATION: `close` returned ordinary success with the loop open and state CLOSING."""
    retained = _dead_before_loop_owner(monkeypatch, "optimus-redis-owner-dead-public-close")
    assert not retained.thread_is_alive and not retained.loop_is_closed
    retained.close(timeout=1)
    assert retained.loop_is_closed
    assert retained.state is RedisLoopOwnerState.CLOSED
    assert retained.is_terminated


def test_public_close_can_be_repeated_after_finalizing_a_dead_thread(monkeypatch):
    """Repeat observation through the public entry stays consistent and never re-opens anything."""
    retained = _dead_before_loop_owner(monkeypatch, "optimus-redis-owner-dead-repeat-close")
    retained.close(timeout=1)
    retained.close(timeout=1)
    assert retained.wait_terminated(1)
    assert retained.is_terminated and retained.state is RedisLoopOwnerState.CLOSED


def test_public_close_of_a_still_alive_startup_wedge_reports_incomplete_and_does_not_force_the_loop(monkeypatch):
    """A LIVE wedged thread must not be finalized from outside: incomplete, loop untouched."""
    from optimus.redis import async_bridge

    release = threading.Event()
    monkeypatch.setattr(async_bridge, "_START_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(async_bridge.RedisLoopOwner, "_run_forever", lambda self: release.wait(30))
    with pytest.raises(async_bridge.RedisLoopOwnerStartupIncomplete) as excinfo:
        async_bridge.RedisLoopOwner(name="optimus-redis-owner-live-wedge-public-close")
    retained = excinfo.value.owner
    try:
        with pytest.raises(async_bridge.RedisLoopOwnerShutdownIncomplete):
            retained.close(timeout=0.2)
        assert retained.thread_is_alive
        assert not retained.loop_is_closed, "a running thread's loop was force-closed from outside"
        assert retained._finalization is None, "finalization was claimed for a LIVE thread"  # noqa: SLF001
        assert not retained.is_terminated
    finally:
        release.set()
        assert retained.wait_terminated(10)
    assert retained.is_terminated and retained.loop_is_closed


def test_a_thread_that_died_before_running_the_loop_leaves_no_orphaned_loop(monkeypatch):
    """MUTATION: an orphaned loop after a startup wedge unwinds (unclosed-loop leak)."""
    from optimus.redis import async_bridge

    monkeypatch.setattr(async_bridge, "_START_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(async_bridge.RedisLoopOwner, "_run_forever", lambda self: None)
    with pytest.raises(async_bridge.RedisLoopOwnerStartupIncomplete) as excinfo:
        async_bridge.RedisLoopOwner(name="optimus-redis-owner-dead-before-loop")
    retained = excinfo.value.owner
    assert retained.wait_terminated(5)
    assert retained.is_terminated and retained.loop_is_closed
