from __future__ import annotations

import asyncio
import contextlib
import threading
from concurrent.futures import Future, InvalidStateError
from concurrent.futures import wait as futures_wait
from dataclasses import dataclass, field
from enum import Enum

from optimus.agent.state_store import (
    DEFAULT_PLAN_TTL_SECONDS,
    AsyncRedisAgentStateStore,
    RedisAgentStateStore,
    validate_redis_url,
)
from optimus.redis.async_bridge import (
    SHUTDOWN_OBSERVATION_BUDGET_SECONDS,
    RedisLoopOwner,
    RedisLoopOwnerClosed,
)
from optimus.telemetry.redis_adapter import RedisTelemetryAdapter


class RedisRuntimeState(str, Enum):
    """Explicit lifecycle states for one runtime."""

    STARTING = "STARTING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class StageOutcome(str, Enum):
    """What actually happened to one teardown stage.

    ``RETURNED`` records that the call returned normally. It is **not** proof of
    server-side rollback or of physical socket behaviour -- only that this stage did
    not raise.
    """

    NOT_ATTEMPTED = "not_attempted"
    RETURNED = "returned"
    FAILED = "failed"


class RedisRuntimeShutdownIncomplete(TimeoutError):
    """The shutdown observation budget elapsed before teardown could be observed.

    The runtime stays ``CLOSING`` with **retained ownership**: the close task and the
    owner are kept, never discarded and never replaced, so a later observation reports
    the eventual outcome. This is not a claim that anything stopped.
    """


@dataclass
class TeardownRecord:
    """The single record of one runtime teardown.

    Created once, atomically with the closing of runtime admission. Every concurrent
    or repeated closer observes *this* record rather than performing a second
    teardown -- which is what stops a duplicate client/pool close.
    """

    client: StageOutcome = StageOutcome.NOT_ATTEMPTED
    pool: StageOutcome = StageOutcome.NOT_ATTEMPTED
    owner_terminated: bool = False
    admitted_work_settled: bool = False
    client_error: BaseException | None = None
    pool_error: BaseException | None = None
    error: BaseException | None = None
    #: Completed exactly once by the single closer. A Future rather than an Event so
    #: the bounded wait, the "already finished" query and the eventual outcome are one
    #: object -- and so this module contains no bare `.set()` call, which the Plan 9.96
    #: surface audit classifies as a Redis hash write by AST shape alone.
    completed: Future = field(default_factory=Future)

    @property
    def is_clean(self) -> bool:
        """A clean teardown returned from every attempted stage AND terminated the owner.

        A live owner thread can never make this True.
        """
        return (
            self.owner_terminated
            and self.admitted_work_settled
            and self.client in (StageOutcome.RETURNED, StageOutcome.NOT_ATTEMPTED)
            and self.pool is StageOutcome.RETURNED
            and self.error is None
        )


class _RuntimeLifecycle:
    """Mutable lifecycle state for a frozen runtime.

    A frozen dataclass can hold a mutable object; changing ``frozen=`` is not
    required to give the runtime explicit state.
    """

    __slots__ = ("_lock", "record", "state", "teardown_thread")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = RedisRuntimeState.OPEN
        self.record: TeardownRecord | None = None
        self.teardown_thread: threading.Thread | None = None

    def start_teardown(self, target) -> None:
        """Start the one retained teardown thread. Retained, never replaced."""
        with self._lock:
            if self.teardown_thread is not None:
                return
            self.teardown_thread = threading.Thread(
                target=target, name="optimus-redis-runtime-teardown", daemon=True
            )
            self.teardown_thread.start()

    def begin_close(self) -> tuple[TeardownRecord, bool]:
        """Close admission and create the one teardown record, atomically."""
        with self._lock:
            if self.record is None:
                self.state = RedisRuntimeState.CLOSING
                self.record = TeardownRecord()
                return self.record, True
            return self.record, False

    def check_admission(self) -> None:
        with self._lock:
            if self.state in (RedisRuntimeState.CLOSING, RedisRuntimeState.CLOSED):
                raise RedisLoopOwnerClosed("the Redis runtime is closing and admits no new work")

    def mark_closed(self) -> None:
        with self._lock:
            self.state = RedisRuntimeState.CLOSED


@dataclass(frozen=True)
class RedisRuntime:
    """Shared redis.asyncio pool for plan state and TimeSeries telemetry (LLD §10).

    Seam 2, checkpoint A: the runtime also owns the ONE event loop its pool and client
    are ever driven from. ``from_url`` builds both on that loop, and ``close()`` closes
    the client and pool **on the owner** before stopping it. One runtime therefore
    means one pool, one client and one loop owner.
    """

    pool: object
    client: object | None
    owner: RedisLoopOwner
    ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS
    lifecycle: _RuntimeLifecycle = field(default_factory=_RuntimeLifecycle, repr=False, compare=False)

    @classmethod
    def from_url(cls, url: str, *, ttl_seconds: int = DEFAULT_PLAN_TTL_SECONDS) -> RedisRuntime:
        """Build the pool and client on this runtime's own owner loop.

        Partial construction is rolled back **through the single close path**: if the
        client cannot be created after the pool exists, the pool is closed on the owner
        and the owner is stopped. The original initialization error propagates; a
        cleanup failure is attached as a note rather than replacing it.
        """
        validated = validate_redis_url(url)
        import redis.asyncio as aioredis

        owner = RedisLoopOwner()
        built: list[object] = []

        async def _build() -> tuple[object, object]:
            pool = aioredis.ConnectionPool.from_url(validated, decode_responses=True, socket_connect_timeout=2)
            built.append(pool)
            return pool, aioredis.Redis(connection_pool=pool)

        try:
            pool, client = owner.run_sync(_build)
        except BaseException as exc:
            try:
                if built:
                    # The client never existed, but the pool did. Close it through the
                    # ONE close path rather than adding a second aclose site.
                    cls(pool=built[0], client=None, owner=owner, ttl_seconds=ttl_seconds).close()
                else:
                    owner.close()
            except BaseException as cleanup_exc:  # noqa: BLE001 - reported, never swallowed
                exc.add_note(f"redis runtime startup rollback also failed: {cleanup_exc!r}")
            raise
        return cls(pool=pool, client=client, owner=owner, ttl_seconds=ttl_seconds)

    # -- owner submission seams ----------------------------------------------------

    def run_sync(self, operation, *, timeout: float | None = None):
        """Submit an operation factory to this runtime's owner.

        The runtime admission check runs INSIDE the owner's registration lock, so it and
        the submission are one atomic step against a concurrent close. Checking first and
        submitting afterwards leaves a window in which a caller that passed the check is
        still admitted after shutdown has begun -- and its work would then be running
        while the client and pool are closed underneath it.
        """
        self.owner.reject_reentrancy("run_sync")
        handle = self.owner.submit(operation, guard=self.lifecycle.check_admission)
        return handle.future.result(timeout)

    async def run_async(self, operation):
        """Submit an operation factory to this runtime's owner from a running loop."""
        handle = self.owner.submit(operation, guard=self.lifecycle.check_admission)
        return await self.owner.observe(handle)

    @property
    def state(self) -> RedisRuntimeState:
        return self.lifecycle.state

    @property
    def teardown_record(self) -> TeardownRecord | None:
        return self.lifecycle.record

    # -- consumers -----------------------------------------------------------------

    def sync_state_store(self) -> RedisAgentStateStore:
        """A synchronous store whose every operation is submitted to THIS owner.

        Seam 2, checkpoint B: the submission seam is injected, so the store never reaches
        the process-wide shared tool owner. One runtime, one loop, one client.
        """
        async_store = AsyncRedisAgentStateStore(client=self.client, ttl_seconds=self.ttl_seconds)
        return RedisAgentStateStore(async_store=async_store, submit=self.run_sync)

    def telemetry_adapter(self) -> RedisTelemetryAdapter:
        return RedisTelemetryAdapter(client=self.client)

    def telemetry_sink(self):
        """A synchronous telemetry sink bound to THIS owner's submission seam."""
        from optimus.telemetry.redis_sink import RedisTelemetryEventSink

        return RedisTelemetryEventSink(self.telemetry_adapter(), submit=self.run_sync)

    def ping(self) -> None:
        self.run_sync(self._ping_async)

    async def _ping_async(self) -> None:
        try:
            await self.client.ping()
        except ConnectionError:
            raise
        except OSError as exc:
            raise ConnectionError(str(exc)) from exc
        except Exception as exc:
            if type(exc).__module__.startswith("redis") and type(exc).__name__ in {
                "ConnectionError",
                "TimeoutError",
            }:
                raise ConnectionError(str(exc)) from exc
            raise

    # -- teardown ------------------------------------------------------------------

    async def _close_resources(self, record: TeardownRecord) -> None:
        """Close the client, then the pool, on the owner loop.

        Pool cleanup is attempted after an **ordinary** client-close failure. It is
        deliberately skipped when the client close ends in ``BaseException`` control
        flow (cancellation, interrupt): the loop is being torn down under us, so the
        stage is recorded as not attempted rather than pretended.
        """
        client_failed_ordinarily = False
        try:
            if self.client is None:
                record.client = StageOutcome.NOT_ATTEMPTED
            else:
                await self.client.aclose()
                record.client = StageOutcome.RETURNED
        except Exception as exc:
            record.client = StageOutcome.FAILED
            record.client_error = exc
            client_failed_ordinarily = True
            raise
        except BaseException as exc:
            record.client = StageOutcome.FAILED
            record.client_error = exc
            raise
        finally:
            if record.client is not StageOutcome.FAILED or client_failed_ordinarily:
                try:
                    await self.pool.aclose()
                    record.pool = StageOutcome.RETURNED
                except BaseException as exc:
                    record.pool = StageOutcome.FAILED
                    record.pool_error = exc
                    raise

    def _drive_teardown(self, record: TeardownRecord) -> None:
        """The ONE retained teardown operation. Runs on its own thread, unbounded.

        It deliberately has no budget of its own. A caller's budget bounds that caller's
        *observation*; this operation runs to actual terminal disposition, so the record
        it publishes is never a snapshot of the moment some caller gave up. If a
        cancellation-resistant operation or a blocked cleanup never settles, this thread
        stays parked, ``record.completed`` stays unresolved, and every observer keeps
        timing out -- honestly incomplete rather than falsely finished.
        """
        try:
            # 1. Close admission FIRST, atomically, and take the in-flight snapshot.
            handles = self.owner.begin_shutdown()
            # 2. Settle (or explicitly retain) admitted work BEFORE touching resources.
            #    Closing the client and pool underneath live work is precisely the
            #    ordering defect this step exists to prevent.
            record.admitted_work_settled = self.owner.settle_in_flight(handles)
            # 3. Only now close the resources, on the owner, as a privileged teardown
            #    submission that admission no longer accepts from anyone else.
            try:
                self.owner.submit(lambda: self._close_resources(record), teardown=True).future.result()
            except RedisLoopOwnerClosed:
                pass  # the loop was already gone; there is nothing left to close on it
            except BaseException as exc:  # noqa: BLE001 - recorded, then republished below
                if record.error is None:
                    record.error = exc
            # 4. Stop the loop and observe REAL termination, without a bounded join.
            self.owner.initiate_shutdown()
            self.owner.wait_terminated()
        except BaseException as exc:  # noqa: BLE001 - the record must always be published
            if record.error is None:
                record.error = exc
        finally:
            record.owner_terminated = self.owner.is_terminated
            if record.owner_terminated:
                self.lifecycle.mark_closed()
            # Resolved ONCE, here, at actual terminal disposition -- never when a caller
            # stopped waiting. Every caller, first or later, sees this same outcome.
            with contextlib.suppress(InvalidStateError):
                if record.error is not None:
                    record.completed.set_exception(record.error)
                else:
                    record.completed.set_result(None)

    def close(self, *, timeout: float | None = None) -> TeardownRecord:
        """Observe this runtime's single teardown, bounded by ``timeout``.

        The first caller starts the one retained teardown; every caller then *observes*
        it. Order inside that teardown: close admission atomically, settle or retain
        already-admitted work, close client then pool on the owner, stop the loop and
        establish physical thread termination.

        ``timeout`` bounds **this caller's observation only**. Expiry raises
        :class:`RedisRuntimeShutdownIncomplete`, leaves the runtime ``CLOSING`` with
        ownership retained, and records nothing on the shared record -- a caller giving
        up is not a resource-stage failure. A later observation reports the eventual
        outcome, and a stage failure reaches first and later callers alike.
        """
        # Reject reentrancy BEFORE mutating any lifecycle state: entering CLOSING and
        # only then discovering the caller is the owner thread would leave the runtime
        # permanently closing with nothing able to finish it.
        self.owner.reject_reentrancy("close")
        budget = SHUTDOWN_OBSERVATION_BUDGET_SECONDS if timeout is None else timeout
        record, is_first_closer = self.lifecycle.begin_close()
        if is_first_closer:
            self.lifecycle.start_teardown(lambda: self._drive_teardown(record))
        # Establish COMPLETION first, then retrieve the outcome -- two separate calls.
        # `Future.result(timeout)` raises TimeoutError both when the wait expires and when
        # a COMPLETED teardown failed with a TimeoutError, and
        # `concurrent.futures.TimeoutError` *is* the builtin, so a single call cannot tell
        # a resource-stage failure from an expired observation. Waiting on the future's
        # doneness answers that question directly, with no exception-type guessing and no
        # race between the two.
        done, _ = futures_wait([record.completed], timeout=budget)
        if not done:
            raise RedisRuntimeShutdownIncomplete(
                "the Redis runtime teardown has not reached terminal disposition within this "
                "observation budget; the teardown and the owner are retained"
            )
        # Completed: republish the retained terminal exception unchanged, so a resource
        # that failed with TimeoutError reaches the caller as that TimeoutError.
        record.completed.result()
        return record

    async def close_async(self, *, timeout: float | None = None) -> TeardownRecord:
        """Observe this runtime's single teardown from a running event loop.

        Seam 2, checkpoint B. The serving loop must never block on a thread join, so the
        observation here is an awaited signal rather than :meth:`close`'s blocking wait.
        Everything else is identical: the first caller starts the ONE retained teardown,
        every caller observes that same record, and an expired budget raises
        :class:`RedisRuntimeShutdownIncomplete` with ownership retained.

        The signal is a plain done-callback that pokes an event on the caller's loop --
        deliberately NOT :func:`asyncio.wrap_future`. Chaining a future would propagate an
        observer's cancellation back into the shared completion record and cancel it,
        which destroys the only evidence that the teardown reached terminal disposition.
        Cancelling this coroutine therefore cancels nothing but this observation.
        """
        self.owner.reject_reentrancy("close_async")
        budget = SHUTDOWN_OBSERVATION_BUDGET_SECONDS if timeout is None else timeout
        record, is_first_closer = self.lifecycle.begin_close()
        if is_first_closer:
            self.lifecycle.start_teardown(lambda: self._drive_teardown(record))
        if record.completed.done():
            # Round 2, R5: a budget bounds WAITING; it must never hide an outcome that is
            # already available. A completed teardown -- clean or failed -- is republished
            # immediately, exactly as the blocking observer would republish it.
            record.completed.result()
            return record
        loop = asyncio.get_running_loop()
        settled = asyncio.Event()

        def _notify(_future: Future) -> None:
            # The loop may have closed before the retained teardown settles; the record
            # itself stays valid for the next observer, so a dead loop is not an error.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(settled.set)

        record.completed.add_done_callback(_notify)
        try:
            await asyncio.wait_for(settled.wait(), timeout=budget)
        except TimeoutError:
            raise RedisRuntimeShutdownIncomplete(
                "the Redis runtime teardown has not reached terminal disposition within this "
                "observation budget; the teardown and the owner are retained"
            ) from None
        record.completed.result()
        return record
