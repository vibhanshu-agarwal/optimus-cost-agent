"""Seam 2, checkpoint A: the RedisRuntime ownership and teardown contract.

Every runtime built here owns its resources explicitly and closes them, including on
the failure path.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

import pytest

from optimus.agent.state_store import RedisAgentStateStore
from optimus.redis.async_bridge import (
    RedisLoopOwner,
    RedisLoopOwnerClosed,
    RedisLoopOwnerShutdownIncomplete,
)
from optimus.redis.runtime import (
    RedisRuntime,
    RedisRuntimeShutdownIncomplete,
    RedisRuntimeState,
    StageOutcome,
)
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


class _CountingResource:
    """A fake client/pool that counts its own closes and records where they ran."""

    def __init__(self, *, error: BaseException | None = None, gate: threading.Event | None = None) -> None:
        self.count = 0
        self.threads: list[int] = []
        self.error = error
        self._gate = gate

    async def aclose(self) -> None:
        self.count += 1
        self.threads.append(threading.get_ident())
        if self._gate is not None:
            self._gate.set()
            await asyncio.sleep(0.05)
        if self.error is not None:
            raise self.error


@pytest.fixture
def owner():
    made = RedisLoopOwner(name="optimus-redis-owner-under-test")
    try:
        yield made
    finally:
        try:
            made.close(timeout=5.0)
        except RedisLoopOwnerShutdownIncomplete:
            pass


def _runtime(owner, *, client=None, pool=None) -> RedisRuntime:
    return RedisRuntime(pool=pool or _CountingResource(), client=client, owner=owner)


def test_redis_runtime_shares_pool_between_state_store_and_telemetry():
    """The original main contract, now with an explicitly closed runtime lifetime."""
    runtime = RedisRuntime.from_url("redis://127.0.0.1:6379/0")
    try:
        state_store = runtime.sync_state_store()
        adapter = runtime.telemetry_adapter()

        assert isinstance(state_store, RedisAgentStateStore)
        assert isinstance(adapter, RedisTelemetryAdapter)
        assert state_store.redis_client.connection_pool is runtime.pool
        assert adapter._client.connection_pool is runtime.pool
    finally:
        runtime.close(timeout=5.0)
    assert runtime.state is RedisRuntimeState.CLOSED


def test_from_url_builds_pool_and_client_on_the_owner_loop():
    runtime = RedisRuntime.from_url("redis://127.0.0.1:6379/0")
    try:
        assert runtime.owner.state.name == "OPEN"
        assert runtime.client.connection_pool is runtime.pool
    finally:
        record = runtime.close(timeout=5.0)
    assert record.owner_terminated
    assert runtime.owner.is_terminated


def test_resource_cleanup_runs_on_the_owner_loop_not_the_caller(owner):
    """MUTATION: cleanup on the caller's loop."""
    client = _CountingResource()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    caller = threading.get_ident()
    record = runtime.close(timeout=5.0)

    assert record.client is StageOutcome.RETURNED
    assert record.pool is StageOutcome.RETURNED
    assert client.threads == [owner.thread.ident]
    assert pool.threads == [owner.thread.ident]
    assert caller not in client.threads


def test_concurrent_close_performs_exactly_one_teardown(owner):
    """MUTATION: duplicate concurrent close.

    This is the tagged implementation's first counterexample: two threads both
    entered client close and both client and pool were closed twice.
    """
    gate = threading.Event()
    client = _CountingResource(gate=gate)
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    errors: list[BaseException] = []
    records: list[object] = []

    def _closer():
        try:
            records.append(runtime.close(timeout=5.0))
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=_closer, name=f"seam2-closer-{index}") for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    assert client.count == 1, f"client closed {client.count} times"
    assert pool.count == 1, f"pool closed {pool.count} times"
    # Both closers observed the SAME single teardown record.
    assert len(records) == 2
    assert records[0] is records[1]
    assert runtime.teardown_record is records[0]


def test_repeated_sequential_close_reuses_the_single_record(owner):
    client = _CountingResource()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    first = runtime.close(timeout=5.0)
    second = runtime.close(timeout=5.0)

    assert first is second
    assert client.count == 1
    assert pool.count == 1
    assert first.is_clean


def test_pool_is_closed_after_an_ordinary_client_failure(owner):
    """MUTATION: pool skipped after client failure."""
    client = _CountingResource(error=RuntimeError("client close failed"))
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    with pytest.raises(RuntimeError, match="client close failed"):
        runtime.close(timeout=5.0)

    record = runtime.teardown_record
    assert pool.count == 1, "pool cleanup was skipped after an ordinary client failure"
    assert record.client is StageOutcome.FAILED
    assert record.pool is StageOutcome.RETURNED
    assert isinstance(record.client_error, RuntimeError)
    assert not record.is_clean


def test_stages_distinguish_not_attempted_from_failed_and_returned(owner):
    """A runtime with no client records the client stage as not attempted."""
    pool = _CountingResource()
    runtime = _runtime(owner, client=None, pool=pool)

    record = runtime.close(timeout=5.0)

    assert record.client is StageOutcome.NOT_ATTEMPTED
    assert record.pool is StageOutcome.RETURNED
    assert record.is_clean


def test_admission_closes_atomically_before_resource_cleanup(owner):
    """New submissions stop at the very start of shutdown, not after cleanup begins."""
    client = _CountingResource()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    runtime.run_sync(lambda: asyncio.sleep(0))  # open for business first
    runtime.close(timeout=5.0)

    async def _late():  # pragma: no cover - must never be entered
        raise AssertionError("work was admitted after shutdown began")

    with pytest.raises(RedisLoopOwnerClosed):
        runtime.run_sync(lambda: _late())


def test_blocked_cleanup_reports_incomplete_and_retains_ownership(owner):
    """The budget spans cleanup, so a blocked close cannot outrun the deadline."""
    release = threading.Event()

    class _BlockedClient:
        def __init__(self) -> None:
            self.count = 0

        async def aclose(self) -> None:
            self.count += 1
            while not release.is_set():
                try:
                    await asyncio.sleep(0.005)
                except asyncio.CancelledError:
                    pass

    client = _BlockedClient()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)
    owner_before = runtime.owner

    with pytest.raises(RedisRuntimeShutdownIncomplete):
        runtime.close(timeout=0.3)

    assert runtime.state is RedisRuntimeState.CLOSING, "a timed-out close must not report CLOSED"
    assert runtime.owner is owner_before, "ownership must be retained, never replaced"
    assert not runtime.teardown_record.is_clean
    assert not runtime.teardown_record.owner_terminated
    release.set()


def test_startup_rollback_closes_the_pool_when_the_client_cannot_be_built(monkeypatch):
    """MUTATION: startup rollback leak."""
    import redis.asyncio as aioredis

    closed: list[str] = []

    class _Pool:
        async def aclose(self) -> None:
            closed.append("pool")

    monkeypatch.setattr(aioredis.ConnectionPool, "from_url", staticmethod(lambda *a, **k: _Pool()))
    monkeypatch.setattr(
        aioredis,
        "Redis",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("client construction failed")),
    )

    with pytest.raises(RuntimeError, match="client construction failed"):
        RedisRuntime.from_url("redis://127.0.0.1:6379/0")

    assert closed == ["pool"], "the pool leaked when client construction failed"


def test_startup_rollback_stops_the_owner_when_the_pool_cannot_be_built(monkeypatch):
    """No owner thread may survive a construction that never produced a pool."""
    import redis.asyncio as aioredis

    monkeypatch.setattr(
        aioredis.ConnectionPool,
        "from_url",
        staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("pool construction failed"))),
    )

    before = {thread.ident for thread in threading.enumerate()}
    with pytest.raises(RuntimeError, match="pool construction failed"):
        RedisRuntime.from_url("redis://127.0.0.1:6379/0")

    leaked = [
        thread
        for thread in threading.enumerate()
        if thread.ident not in before and thread.name.startswith("optimus-redis-owner")
    ]
    for thread in leaked:
        thread.join(5)
    assert not [thread for thread in leaked if thread.is_alive()], "the owner thread leaked"


def test_startup_rollback_preserves_the_original_error_over_a_cleanup_failure(monkeypatch):
    """The initialization error survives; the cleanup failure is separately observable."""
    import redis.asyncio as aioredis

    class _AngryPool:
        async def aclose(self) -> None:
            raise RuntimeError("pool cleanup failed")

    monkeypatch.setattr(aioredis.ConnectionPool, "from_url", staticmethod(lambda *a, **k: _AngryPool()))
    monkeypatch.setattr(
        aioredis,
        "Redis",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("original failure")),
    )

    with pytest.raises(RuntimeError, match="original failure") as excinfo:
        RedisRuntime.from_url("redis://127.0.0.1:6379/0")

    notes = getattr(excinfo.value, "__notes__", [])
    assert any("startup rollback also failed" in note for note in notes), notes
    assert any("pool cleanup failed" in note for note in notes), notes


# --- Review round 1: R1/R2 corrections ------------------------------------------


class _BlockingClient:
    """A client whose close blocks until released, absorbing cancellation."""

    def __init__(self, release: threading.Event) -> None:
        self.count = 0
        self._release = release

    async def aclose(self) -> None:
        self.count += 1
        while not self._release.is_set():
            try:
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                pass


def test_a_callers_timeout_never_publishes_the_record(owner):
    """R1: a caller giving up is an observation outcome, not a finished teardown."""
    release = threading.Event()
    runtime = _runtime(owner, client=_BlockingClient(release), pool=_CountingResource())
    try:
        with pytest.raises(RedisRuntimeShutdownIncomplete):
            runtime.close(timeout=0.1)
        record = runtime.teardown_record

        # A SECOND observer must also report incomplete rather than returning the
        # record as though the first observer's timeout had finished the teardown.
        with pytest.raises(RedisRuntimeShutdownIncomplete):
            runtime.close(timeout=0.1)

        assert not record.completed.done(), "the record was published before teardown finished"
        assert not record.owner_terminated
        assert runtime.state is RedisRuntimeState.CLOSING
        assert runtime.owner.thread_is_alive
    finally:
        release.set()


def test_the_retained_teardown_updates_the_record_at_real_termination(owner, monkeypatch):
    """R1: the record publishes at PHYSICAL owner termination, never before (rounds 3-4, R10/R12).

    Deterministic by TWO handshakes, not by scheduling. (1) The owner thread is parked at
    its loop-close boundary -- after the client and pool have closed, after shutdown was
    initiated. (2) The teardown thread must POSITIVELY signal that it entered the real
    termination-observation path (`owner.wait_terminated`, wrapped to signal entry and
    then perform the actual wait) while the owner is still parked. An implementation that
    omits the wait can never produce signal (2), however long its continuation is delayed
    after `initiate_shutdown()` -- so the mutant fails here on every schedule, not only
    when it happens to resume before the observer's budget expires. While the owner is
    held alive the record must be unresolved; once released, the SAME record must reach
    its real terminal outcome.
    """
    entered, release, wait_entered = threading.Event(), threading.Event(), threading.Event()
    original_close = owner._loop.close  # noqa: SLF001 - parks the owner at the loop-close boundary
    real_wait_terminated = owner.wait_terminated

    def _held_close():
        entered.set()
        assert release.wait(10), "the test never released the owner"
        original_close()

    def _observed_wait_terminated(timeout=None):
        wait_entered.set()  # positive handshake: the teardown entered termination observation
        return real_wait_terminated(timeout)

    monkeypatch.setattr(owner._loop, "close", _held_close)  # noqa: SLF001
    monkeypatch.setattr(owner, "wait_terminated", _observed_wait_terminated)
    client = _CountingResource()
    runtime = _runtime(owner, client=client, pool=_CountingResource())
    try:
        with pytest.raises(RedisRuntimeShutdownIncomplete):
            runtime.close(timeout=0.25)
        assert entered.wait(5), "the owner never reached its loop-close boundary"
        assert wait_entered.wait(5), "the teardown never entered the termination-observation path"
        # The owner is held alive PAST resource closure and shutdown initiation, and the
        # teardown is provably inside the real wait for it.
        record = runtime.teardown_record
        assert record is not None
        assert client.count == 1
        assert not record.completed.done(), "the record published while the owner was still alive"
        assert not record.owner_terminated
        assert runtime.state is RedisRuntimeState.CLOSING
        assert runtime.owner.thread_is_alive
    finally:
        release.set()

    later = runtime.close(timeout=10)
    assert later is record, "a later observer saw a different record"
    assert record.owner_terminated, "record stayed stale after the owner actually terminated"
    assert runtime.state is RedisRuntimeState.CLOSED
    assert record.is_clean
    assert client.count == 1, "the retained teardown re-closed the client"
    assert runtime.owner.is_terminated


def test_a_stage_failure_reaches_first_and_later_callers_alike(owner):
    """R1: every observer of one teardown sees the same eventual result."""
    client = _CountingResource(error=RuntimeError("client close failed"))
    runtime = _runtime(owner, client=client, pool=_CountingResource())

    with pytest.raises(RuntimeError, match="client close failed"):
        runtime.close(timeout=10)
    with pytest.raises(RuntimeError, match="client close failed"):
        runtime.close(timeout=10)

    record = runtime.teardown_record
    assert record.client is StageOutcome.FAILED
    assert record.pool is StageOutcome.RETURNED
    assert client.count == 1


def test_admitted_work_settles_before_any_resource_is_closed(owner):
    """R2: resources must never close underneath work that is still running."""
    entered, done = threading.Event(), threading.Event()
    observations: list[bool] = []

    async def _operation():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            done.set()

    class _Observer:
        async def aclose(self) -> None:
            observations.append(done.is_set())

    runtime = RedisRuntime(pool=_Observer(), client=_Observer(), owner=owner)
    handle = owner.submit(_operation)
    assert entered.wait(5)

    record = runtime.close(timeout=10)

    assert observations == [True, True], f"resources closed under live work: {observations}"
    assert record.admitted_work_settled
    with contextlib.suppress(BaseException):
        handle.future.result(1)


def test_admission_and_submission_are_atomic_against_close(owner):
    """R2: passing the runtime check must not permit admission after close begins."""
    ran = threading.Event()
    outcome: list[str] = []

    async def _late():
        ran.set()

    runtime = _runtime(owner, client=_CountingResource(), pool=_CountingResource())
    start = threading.Barrier(2)

    def _submitter():
        start.wait(5)
        try:
            runtime.run_sync(lambda: _late())
            outcome.append("admitted")
        except RedisLoopOwnerClosed:
            outcome.append("refused")

    def _closer():
        start.wait(5)
        runtime.close(timeout=10)

    threads = [threading.Thread(target=_submitter), threading.Thread(target=_closer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)

    assert not any(thread.is_alive() for thread in threads)
    assert runtime.state is RedisRuntimeState.CLOSED
    # Either the submission genuinely won the race, or it was refused. What must never
    # happen is being admitted after the close transition and running afterwards.
    if outcome == ["refused"]:
        assert not ran.is_set()


def test_close_rejects_reentrancy_before_mutating_lifecycle_state(owner):
    """R2: entering CLOSING and only then refusing would strand the runtime."""
    runtime = _runtime(owner, client=_CountingResource(), pool=_CountingResource())
    captured: dict[str, BaseException | None] = {"error": None}

    async def _from_owner_thread():
        try:
            runtime.close(timeout=1)
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            captured["error"] = exc

    owner.run_sync(_from_owner_thread)

    assert isinstance(captured["error"], RuntimeError)
    assert "must not be called from inside the owner loop" in str(captured["error"])
    assert runtime.state is RedisRuntimeState.OPEN, "lifecycle state was mutated before the guard ran"
    assert runtime.teardown_record is None


# --- Review round 2: R6 -----------------------------------------------------------


class _TimingOutResource:
    """A resource whose close fails with the builtin TimeoutError."""

    def __init__(self, stage: str, failing_stage: str, calls: list[str]) -> None:
        self.stage = stage
        self.failing_stage = failing_stage
        self.calls = calls
        self.error = TimeoutError(f"{failing_stage} resource timeout")

    async def aclose(self) -> None:
        self.calls.append(self.stage)
        if self.stage == self.failing_stage:
            raise self.error


@pytest.mark.parametrize("failing_stage", ["client", "pool"])
def test_a_resource_timeout_is_not_reported_as_an_incomplete_shutdown(owner, failing_stage):
    """MUTATION: a completed teardown that failed with TimeoutError reported as incomplete.

    `Future.result(timeout)` raises TimeoutError both when the wait expires and when a
    COMPLETED future holds a TimeoutError -- and `concurrent.futures.TimeoutError` IS the
    builtin. Waiting and retrieving must therefore be separate steps, or a resource
    failure is silently reclassified as "we stopped watching".
    """
    calls: list[str] = []
    client = _TimingOutResource("client", failing_stage, calls)
    pool = _TimingOutResource("pool", failing_stage, calls)
    failure = client.error if failing_stage == "client" else pool.error
    runtime = RedisRuntime(pool=pool, client=client, owner=owner)

    observed: list[BaseException] = []
    for _ in range(2):  # first AND repeated observer
        try:
            runtime.close(timeout=5)
        except BaseException as exc:  # noqa: BLE001 - the identity is the assertion
            observed.append(exc)

    assert len(observed) == 2
    for exc in observed:
        assert not isinstance(exc, RedisRuntimeShutdownIncomplete), (
            "a completed teardown failure was reported as an expired observation"
        )
        assert exc is failure, "the caller did not receive the original resource error"

    record = runtime.teardown_record
    assert record.completed.done()
    assert record.error is failure
    assert runtime.state is RedisRuntimeState.CLOSED
    assert runtime.owner.is_terminated
    assert calls == ["client", "pool"], "both stages must still be attempted in order"


def test_concurrent_observers_both_receive_the_original_resource_timeout(owner):
    """Every observer of one teardown sees the same terminal exception, not a timeout."""
    calls: list[str] = []
    client = _TimingOutResource("client", "client", calls)
    pool = _TimingOutResource("pool", "client", calls)
    runtime = RedisRuntime(pool=pool, client=client, owner=owner)

    seen: list[BaseException] = []

    def _observer():
        try:
            runtime.close(timeout=10)
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            seen.append(exc)

    threads = [threading.Thread(target=_observer) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)

    assert not any(thread.is_alive() for thread in threads)
    assert len(seen) == 2
    assert all(exc is client.error for exc in seen)
    assert not any(isinstance(exc, RedisRuntimeShutdownIncomplete) for exc in seen)


def test_a_genuinely_expired_observation_still_reports_incomplete_then_succeeds(owner):
    """The distinction must cut both ways: a real expiry is still reported as one."""
    release = threading.Event()
    runtime = _runtime(owner, client=_BlockingClient(release), pool=_CountingResource())

    with pytest.raises(RedisRuntimeShutdownIncomplete):
        runtime.close(timeout=0.1)
    assert not runtime.teardown_record.completed.done()

    release.set()
    record = runtime.close(timeout=10)
    assert record.is_clean
    assert runtime.state is RedisRuntimeState.CLOSED


# --- Seam 2, checkpoint B: async observation of the single teardown ----------------


class _BlockedUntilReleased:
    """A client whose close parks until released, without ever raising."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.count = 0

    async def aclose(self) -> None:
        self.count += 1
        while not self.release.is_set():
            try:
                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                pass


async def test_close_async_observes_the_same_single_teardown_without_blocking_the_loop(owner):
    """MUTATION: cleanup observed by blocking the caller's event loop.

    The serving loop must stay responsive while a teardown runs; a ticking task proves
    the loop kept scheduling during the observation.
    """
    client = _CountingResource()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)
    ticks = 0

    async def _tick() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    ticker = asyncio.create_task(_tick())
    try:
        record = await runtime.close_async(timeout=5.0)
    finally:
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ticker
    assert record is runtime.teardown_record
    assert record.is_clean
    assert client.count == 1 and pool.count == 1
    assert client.threads == [owner.thread.ident]
    assert ticks > 0
    assert runtime.state is RedisRuntimeState.CLOSED


async def test_close_async_reports_incomplete_and_retains_ownership(owner):
    """MUTATION: false clean outcome with a live thread, on the async path."""
    client = _BlockedUntilReleased()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    with pytest.raises(RedisRuntimeShutdownIncomplete):
        await runtime.close_async(timeout=0.2)
    assert runtime.state is RedisRuntimeState.CLOSING
    assert runtime.owner.thread_is_alive
    record = runtime.teardown_record
    assert record is not None and not record.completed.done()
    assert pool.count == 0, "the pool must not be closed under a client close that has not returned"

    client.release.set()
    later = await runtime.close_async(timeout=5.0)
    assert later is record
    assert later.is_clean
    assert client.count == 1 and pool.count == 1


async def test_cancelling_the_async_observer_never_cancels_the_teardown(owner):
    """MUTATION: cancellation that destroys observation.

    An observer that gives up must not turn the shared completion record into a
    cancelled future; the retained teardown still publishes its real outcome.
    """
    client = _BlockedUntilReleased()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    observer = asyncio.create_task(runtime.close_async(timeout=5.0))
    await asyncio.sleep(0.05)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    record = runtime.teardown_record
    assert record is not None
    assert not record.completed.cancelled(), "the shared completion record was cancelled by an observer"

    client.release.set()
    final = await runtime.close_async(timeout=5.0)
    assert final is record and final.is_clean
    assert client.count == 1 and pool.count == 1


async def test_close_async_and_sync_close_share_the_record(owner):
    client = _CountingResource()
    pool = _CountingResource()
    runtime = _runtime(owner, client=client, pool=pool)

    record = await runtime.close_async(timeout=5.0)
    later = await asyncio.to_thread(runtime.close, timeout=5.0)
    assert later is record
    assert client.count == 1 and pool.count == 1


async def test_close_async_rejects_reentrancy_from_the_owner_loop(owner):
    runtime = _runtime(owner, client=_CountingResource(), pool=_CountingResource())

    async def _from_owner():
        await runtime.close_async(timeout=1.0)

    with pytest.raises(RuntimeError, match="must not be called from inside the owner loop"):
        runtime.run_sync(_from_owner)
    assert runtime.state is RedisRuntimeState.OPEN
    runtime.close(timeout=5.0)


def test_reentrancy_is_judged_by_thread_identity_not_a_recycled_ident(owner, monkeypatch):
    """MUTATION: reentrancy by ident. A terminated owner's ident is recycled by the OS; a later
    caller that happens to hold it is not the owner loop and must not be refused."""
    from optimus.redis import async_bridge

    runtime = _runtime(owner, client=_CountingResource(), pool=_CountingResource())
    record = runtime.close(timeout=5.0)
    assert record.is_clean and owner.is_terminated
    dead_ident = owner.thread.ident
    monkeypatch.setattr(async_bridge.threading, "get_ident", lambda: dead_ident)

    assert runtime.close(timeout=5.0) is record  # a later observer holding the recycled ident


# --- R5: an already completed teardown is retrieved before any waiting budget applies ---


async def test_close_async_returns_a_completed_clean_record_at_zero_budget(owner):
    """R5 MUTATION: a zero budget hides an outcome that is already available."""
    runtime = _runtime(owner, client=_CountingResource(), pool=_CountingResource())
    record = await asyncio.to_thread(runtime.close, timeout=5.0)
    assert record.is_clean

    later = await runtime.close_async(timeout=0)
    assert later is record


async def test_close_async_republishes_a_completed_failure_at_zero_budget(owner):
    client = _CountingResource(error=TimeoutError("resource timed out"))
    runtime = _runtime(owner, client=client, pool=_CountingResource())
    with pytest.raises(TimeoutError, match="resource timed out"):
        await asyncio.to_thread(runtime.close, timeout=5.0)
    assert runtime.teardown_record.completed.done()

    with pytest.raises(TimeoutError, match="resource timed out"):
        await runtime.close_async(timeout=0)


async def test_close_async_still_reports_genuinely_pending_work_at_zero_budget(owner):
    client = _BlockedUntilReleased()
    runtime = _runtime(owner, client=client, pool=_CountingResource())
    try:
        with pytest.raises(RedisRuntimeShutdownIncomplete):
            await runtime.close_async(timeout=0)
        assert runtime.state is RedisRuntimeState.CLOSING
    finally:
        client.release.set()
        final = await runtime.close_async(timeout=5.0)
    assert final.is_clean
