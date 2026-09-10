"""One explicit owner for every Redis event-loop operation (Seam 2, checkpoint A).

Before this seam the module exposed only :func:`sync_await`, which lazily created a
*process-global* background loop shared by every runtime in the process. That global
had three consequences this module removes:

* unrelated runtimes shared one lifetime, so one teardown could affect another;
* :func:`shutdown_background_loop` joined for five seconds and then dropped its
  references **regardless of thread liveness**, reporting a timed-out join as a
  completed shutdown, and never closed the loop;
* nothing owned the loop, so there was no place to put admission, lifecycle state
  or a teardown record.

:class:`RedisLoopOwner` replaces the implicit global with an explicit, per-runtime
owner. Both submission styles -- :meth:`RedisLoopOwner.run_sync` for synchronous
callers and :meth:`RedisLoopOwner.run_async` for callers that already have a running
loop -- take an *operation factory*: a zero-argument callable returning an awaitable.
That is load-bearing. A caller who hands over an already-created task or future has
already bound it to the caller's loop; taking a factory lets the owner create AND
enter the coroutine on its own loop, so no Redis operation ever touches the caller's
loop.

:func:`sync_await` survives for separate doctor/tool/test PROCESSES
(``optimus.acp.operator_verify``, the live integration tests, and the synchronous
consumers that checkpoint B will inject with a runtime owner). It now runs on a
shared *owner* rather than a bare global loop, so even the legacy path gets
admission, real thread termination and a truthful shutdown outcome.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Awaitable, Callable, Coroutine
from concurrent.futures import Future as ConcurrentFuture
from concurrent.futures import InvalidStateError
from concurrent.futures import wait as futures_wait
from enum import Enum
from typing import TypeVar

T = TypeVar("T")

_START_TIMEOUT_SECONDS = 10.0
#: Default per-call shutdown *observation* budget. It spans resource cleanup and
#: thread termination together -- not only the join -- so a blocked cleanup cannot
#: consume unbounded time before the clock even starts. It is emphatically NOT a
#: promise that a blocked Python thread can be killed.
SHUTDOWN_OBSERVATION_BUDGET_SECONDS = 10.0
#: How often the drain re-checks for pending tasks. It is a POLL interval, not a
#: deadline: the drain never stops the loop while a task is still pending.
_DRAIN_POLL_SECONDS = 0.05


class RedisLoopOwnerState(str, Enum):
    """Explicit lifecycle states for one loop owner."""

    STARTING = "STARTING"
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class RedisLoopOwnerClosed(RuntimeError):
    """Raised when an operation is submitted to an owner whose admission is closed.

    This means admission is closed, not that shutdown has necessarily finished. The
    runtime may already have closed its resources; accepting work on a replacement
    loop would violate both resource lifetime and loop affinity.
    """


class RedisLoopOwnerStartupIncomplete(TimeoutError):
    """The owner loop did not reach readiness within the startup budget.

    Carries the partially started owner on :attr:`owner` so the caller has retained
    custody to observe rather than an unreferenced thread. Raised from ``__init__``,
    where no object can be returned to hold it.
    """

    def __init__(self, message: str, *, owner: "RedisLoopOwner") -> None:
        super().__init__(message)
        self.owner = owner


class RedisLoopOwnerShutdownIncomplete(TimeoutError):
    """The shutdown observation budget elapsed while the owner was still working.

    New submissions remain refused and **the same owner is retained** -- a later
    observation reports its eventual outcome. Already-submitted work may still be
    running; this is not evidence that it stopped, nor that its effects rolled back.
    """


class _OwnerOperation:
    """One submitted operation, tracked from the caller's thread.

    Built on the standard :func:`asyncio.run_coroutine_threadsafe` lifecycle. The
    :class:`concurrent.futures.Future` it returns is completed for EVERY terminal
    state of the owner-side task -- including a task cancelled before its first step
    -- so it doubles as the "owner-side work has settled" signal that a cancelling
    caller must keep observing.

    Two things that lifecycle cannot do by itself:

    * It does not expose the :class:`asyncio.Task`, so there is no way to cancel the
      owner-side work *without* also cancelling the caller-visible future -- and
      cancelling that future destroys the very signal we need. :meth:`request_cancel`
      cancels the task instead, leaving the future as the observation channel.
    * A cancel requested before the task's first step has no task to act on. The flag
      is therefore read INSIDE the coroutine, on the owner loop, as its first act, so
      a pre-start cancellation is honoured before ``operation()`` is ever called and
      nothing reaches Redis.
    """

    __slots__ = ("_cancel_requested", "_lock", "_loop", "_task", "future")

    def __init__(self, loop: asyncio.AbstractEventLoop, operation: Callable[[], Awaitable[T]]) -> None:
        self._loop = loop
        self._lock = threading.Lock()
        self._task: asyncio.Task | None = None
        self._cancel_requested = False
        self.future: ConcurrentFuture = asyncio.run_coroutine_threadsafe(self._drive(operation), loop)

    async def _drive(self, operation: Callable[[], Awaitable[T]]) -> T:
        # Runs ON the owner loop. Publishing the task handle from here, rather than
        # from the submitting thread, closes the pre-start window: a cancel requested
        # before this first step is seen right here, before `operation()` is called.
        with self._lock:
            if self._cancel_requested:
                raise asyncio.CancelledError
            self._task = asyncio.current_task()
        return await operation()

    def request_cancel(self) -> None:
        """Ask the owner loop to cancel this operation, from any thread."""
        with self._lock:
            self._cancel_requested = True
            task = self._task
        if task is None:
            return
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(task.cancel)

    def abandon(self) -> None:
        """Fail this operation because the owner loop stopped under it.

        A closed loop will never complete the task, so nothing would ever settle
        ``future`` and the caller would wait forever. Called only after the loop has
        actually closed, so the task provably never runs again -- even if a close
        caller already exhausted its budget.
        """
        _settle_exception(
            self.future,
            RedisLoopOwnerClosed("the Redis loop owner closed while this operation was in flight"),
        )


def _settle_exception(future: ConcurrentFuture, exception: BaseException) -> None:
    with contextlib.suppress(InvalidStateError):
        future.set_exception(exception)


class RedisLoopOwner:
    """Owns one event loop, on one dedicated thread, for one Redis runtime.

    Everything that touches the owned ``redis.asyncio`` pool/client -- creating them,
    every store/telemetry operation, and finally closing them -- is submitted here, so
    the pool is only ever driven from a single loop.
    """

    def __init__(self, *, name: str = "optimus-redis-owner") -> None:
        self._state = RedisLoopOwnerState.STARTING
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._state_lock = threading.Lock()
        self._live: set[_OwnerOperation] = set()
        self._shutdown_begun = False
        # Distinct from `_shutdown_begun`: closing admission and scheduling the drain
        # are separate steps, because `begin_shutdown()` closes admission WITHOUT
        # stopping the loop so a retained teardown can still run cleanup on it.
        self._drain_scheduled = False
        # Round 4, R11: the ONE retained finalization of a dead thread's open loop.
        # Claimed atomically under `_state_lock` by the first observer that finds the
        # thread dead with the loop open; every observer -- concurrent, repeated, the
        # claimer itself -- waits on this same future within its own remaining budget.
        self._finalization: ConcurrentFuture[None] | None = None
        self._thread = threading.Thread(target=self._run_forever, name=name, daemon=True)
        self._thread.start()
        if not self._ready.wait(_START_TIMEOUT_SECONDS):  # pragma: no cover - startup wedge
            # Ask it to stop, then observe. Either it terminated -- in which case the
            # thread is provably gone -- or it did not, and the caller is handed the
            # retained owner rather than an unreferenced live thread.
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._loop.stop)
            # `join` raises if the thread never started at all, which is itself a
            # startup failure -- observe it rather than replacing the real diagnosis.
            with contextlib.suppress(RuntimeError):
                self._thread.join(timeout=_START_TIMEOUT_SECONDS)
            raise RedisLoopOwnerStartupIncomplete(
                "the Redis loop owner did not start; ownership is retained for observation",
                owner=self,
            )
        with self._state_lock:
            if self._state is RedisLoopOwnerState.STARTING:
                self._state = RedisLoopOwnerState.OPEN

    # -- observation --------------------------------------------------------------

    @property
    def state(self) -> RedisLoopOwnerState:
        with self._state_lock:
            return self._state

    @property
    def thread(self) -> threading.Thread:
        """The owner's own thread. Identity, not a process-wide name search."""
        return self._thread

    @property
    def thread_is_alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def loop_is_closed(self) -> bool:
        return self._loop.is_closed()

    @property
    def is_terminated(self) -> bool:
        """True only when THIS owner's loop is closed and THIS owner's thread is dead.

        Deliberately not a process-wide thread-name query: another owner, or an
        unrelated thread that happens to share a name, must never be able to make this
        answer True or False.
        """
        return self._loop.is_closed() and not self._thread.is_alive()

    def _run_forever(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        try:
            self._loop.run_forever()
        finally:
            asyncio.set_event_loop(None)
            self._loop.close()
            # A close caller may already have exhausted its budget. Settle stragglers
            # at actual loop termination, not only when somebody calls close again.
            with self._state_lock:
                in_flight = tuple(self._live)
                self._state = RedisLoopOwnerState.CLOSED
            for handle in in_flight:
                handle.abandon()

    # -- submission ---------------------------------------------------------------

    def submit(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        guard: Callable[[], None] | None = None,
        teardown: bool = False,
    ) -> _OwnerOperation:
        """Admit ``operation`` and return its handle.

        ``guard`` runs INSIDE the same lock that decides admission and performs the
        registration, so a runtime-level admission check and this owner-level one are a
        single atomic step against a concurrent close. Two separate checks would leave a
        window in which a caller that passed the first can still be admitted after
        shutdown began.

        ``teardown`` marks the runtime's own cleanup submission, which is the one thing
        that must still reach a loop whose admission has just been closed. It is never a
        general bypass: a CLOSED owner refuses it too.
        """
        return self._submit(operation, guard=guard, teardown=teardown)

    def run_sync(self, operation: Callable[[], Awaitable[T]], *, timeout: float | None = None) -> T:
        """Run ``operation`` on the owner loop and block until it completes."""
        self._reject_reentrancy("run_sync")
        return self._submit(operation).future.result(timeout)

    def begin_shutdown(self) -> tuple[_OwnerOperation, ...]:
        """Close admission and snapshot in-flight work, atomically.

        Separated from :meth:`close` so a runtime can close admission FIRST, settle the
        work that was already admitted, and only then close resources underneath it.
        """
        with self._state_lock:
            self._shutdown_begun = True
            if self._state in (RedisLoopOwnerState.STARTING, RedisLoopOwnerState.OPEN):
                self._state = RedisLoopOwnerState.CLOSING
            return tuple(self._live)

    def settle_in_flight(
        self,
        handles: tuple[_OwnerOperation, ...],
        *,
        timeout: float | None = None,
    ) -> bool:
        """Cancel and then OBSERVE the given operations. True when all have settled.

        Returning False means work is still running and is explicitly retained -- never
        that it was discarded. Callers must not close resources under it.
        """
        for handle in handles:
            handle.request_cancel()
        futures = [handle.future for handle in handles]
        if not futures:
            return True
        _, not_done = futures_wait(futures, timeout=timeout)
        return not not_done

    async def run_async(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run ``operation`` on the owner loop, awaited from the caller's loop.

        On caller cancellation the owner-side operation is cancelled and then
        *observed*: this coroutine does not re-raise until the owner-side task has
        reached a terminal state, so a cancelled public store method can never leave a
        Redis operation running unwatched behind it.

        **Repeated cancellation must not destroy that observation.** The shield keeps
        the caller's cancellation off ``waiter`` -- the object that reports the
        owner-side terminal state -- but a single shielded await is not enough: a
        second cancellation lands on the await itself, and simply re-raising there
        would make the caller terminal while owner-side work was still unfinished.
        The observation therefore *loops*, absorbing further cancellations, until the
        owner-side future is genuinely done. The bound on that wait is the owner's own
        shutdown path: :meth:`close` cancels in-flight work and, once the loop has
        actually closed, abandons stragglers -- which settles ``waiter`` and releases
        the observer.
        """
        return await self.observe(self._submit(operation))

    async def observe(self, handle: _OwnerOperation) -> T:
        """Await an already-admitted operation, preserving observation on cancellation.

        Split from :meth:`run_async` so a caller that had to admit under an external
        guard observes through exactly the same path.
        """
        waiter = asyncio.wrap_future(handle.future)
        try:
            return await asyncio.shield(waiter)
        except asyncio.CancelledError:
            handle.request_cancel()
            while not waiter.done():
                try:
                    await asyncio.shield(waiter)
                except asyncio.CancelledError:
                    # A further cancellation arrived while we were observing. Keep
                    # observing: the completion signal is the only evidence that the
                    # owner-side operation stopped.
                    continue
                except BaseException:
                    # The owner-side operation reached a terminal state by failing.
                    break
                else:
                    break
            raise

    # -- shutdown -----------------------------------------------------------------

    def initiate_shutdown(self) -> None:
        """Close admission and schedule the drain, WITHOUT joining.

        Split out of :meth:`close` so a retained teardown can start shutdown and then
        observe termination without any bounded join of its own.
        """
        with self._state_lock:
            self._shutdown_begun = True
            schedule_drain = not self._drain_scheduled
            self._drain_scheduled = True
            if self._state in (RedisLoopOwnerState.STARTING, RedisLoopOwnerState.OPEN):
                self._state = RedisLoopOwnerState.CLOSING
        if schedule_drain:
            with contextlib.suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._drain_then_stop)

    def reject_reentrancy(self, method: str) -> None:
        """Public reentrancy guard, so callers can refuse BEFORE mutating their state."""
        self._reject_reentrancy(method)

    def close(self, *, timeout: float | None = None) -> None:
        """Close admission, cancel in-flight work, stop the loop and join the thread.

        The budget spans the whole operation. A timed-out join raises
        :class:`RedisLoopOwnerShutdownIncomplete` and **retains this owner**; repeated
        calls observe the same shutdown and never construct a replacement loop. Having
        been asked to close is never reported as having closed.
        """
        self._reject_reentrancy("close")
        budget = SHUTDOWN_OBSERVATION_BUDGET_SECONDS if timeout is None else timeout
        deadline = time.monotonic() + budget
        # Cancellation is requested ONCE, on the owner loop, by the drain. Cancelling
        # here as well would deliver a second cancellation into a cleanup that is already
        # unwinding, which can interrupt the very `finally` the contract promises runs.
        self.initiate_shutdown()
        # The lifecycle lock is NOT held across this join.
        self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        # Round 3, R9 / round 4, R11 / round 5, R13: the public close and `wait_terminated`
        # observe the SAME retained finalization of a dead thread's open loop, each within
        # its own remaining budget, and the RETAINED OUTCOME governs the decision: a
        # finalization that is still pending is incomplete even if the loop is already
        # physically closed (the finalizer may still be settling handles or publishing);
        # a finalization that FAILED -- including a failure to launch it -- is re-raised to
        # every observer; only a successfully completed one, with the physical predicate
        # true as well, is reported as success.
        finalized = self._observe_finalization(deadline=deadline)
        if not finalized or not self.is_terminated:
            raise RedisLoopOwnerShutdownIncomplete(
                "the Redis loop owner shutdown is incomplete; the owner is retained for later observation"
            )

    def wait_terminated(self, timeout: float | None = None) -> bool:
        """Observe physical termination without asking for another shutdown.

        ``timeout`` bounds the whole observation (join AND any pending finalization);
        ``None`` observes without bound. Shares :meth:`_observe_finalization` with the
        public :meth:`close`, so the two observation entries can never disagree about what
        terminal disposition means, and a retained finalization failure reaches this
        observer exactly as it reaches ``close``.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        self._thread.join(timeout=timeout)
        finalized = self._observe_finalization(deadline=deadline)
        return finalized and self.is_terminated

    def _observe_finalization(self, *, deadline: float | None) -> bool:
        """Claim (at most once) and observe the finalization of a dead thread's open loop.

        The condition that starts a finalization is exactly "thread dead AND loop open"
        -- NOT "the loop never ran": this owner cannot know from outside whether the body
        ran, and does not need to. The loop is only ever driven by ``self._thread``; once
        that thread has provably died nothing can be running, stopping or closing the
        loop, so closing it from outside is safe and is the ONLY way it can still be
        closed. In the normal path ``_run_forever``'s own ``finally`` has already closed
        it and there is nothing to claim.

        Round 4, R11. Thread death proves the owner thread is not driving the loop; it
        does NOT prove that another observer is not already closing it. So the
        finalization is claimed ATOMICALLY under ``_state_lock`` -- one future, created by
        exactly one observer -- and runs ONCE, on its own thread, so that every observer
        (the claimer included) waits on that same future within what remains of its own
        budget rather than blocking inside native loop cleanup. CLOSED is published only
        after the cleanup actually completed; a cleanup failure is retained on the future
        and republished to every observer, first or later.

        Round 5, R13. Returns the finalization DISPOSITION rather than leaving callers to
        infer it from the physical loop flag: ``True`` when there is nothing to finalize or
        the retained finalization completed successfully, ``False`` while it is still
        pending at the deadline (or the thread is still alive), and it raises the retained
        failure when the finalization -- or the attempt to launch it -- failed. A launch
        failure (thread construction or start) is published into the SAME retained future
        before it propagates, so the first, a concurrent and every later observer see the
        real failure instead of an operation that is pending forever; the claim is kept,
        nothing is marked CLOSED, and no replacement finalizer is launched.
        """
        if self._thread.is_alive():
            return False
        with self._state_lock:
            finalization = self._finalization
            claimed = False
            if finalization is None:
                if self._loop.is_closed():
                    return True  # closed on the owner thread by `_run_forever`: nothing to finalize
                finalization = self._finalization = ConcurrentFuture()
                claimed = True
        if claimed:
            try:
                threading.Thread(
                    target=self._run_finalization,
                    args=(finalization,),
                    name=f"{self._thread.name}-finalizer",
                    daemon=True,
                ).start()
            except BaseException as exc:  # noqa: BLE001 - published as the retained outcome, then propagated
                with contextlib.suppress(InvalidStateError):
                    finalization.set_exception(exc)
                raise
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        done, _ = futures_wait([finalization], timeout=remaining)
        if not done:
            return False
        finalization.result()  # republish a retained finalization failure unchanged
        return True

    def _run_finalization(self, finalization: ConcurrentFuture[None]) -> None:
        """The ONE native cleanup of a dead thread's loop; publishes its outcome once.

        A thread that died leaving its loop open (a startup wedge that later unwound, or a
        body that never reached ``run_forever``) would otherwise leave an orphaned loop
        that surfaces as an unclosed-loop warning wherever garbage collection happens to
        run (Seam 2, checkpoint B round 2, found by an ordering-dependent supervisor
        test). Admitted-but-unentered handles are abandoned exactly as ``_run_forever``
        abandons them, so no waiter is left parked on a loop that will never run.
        """
        try:
            self._loop.close()
            with self._state_lock:
                in_flight = tuple(self._live)
                self._state = RedisLoopOwnerState.CLOSED
            for handle in in_flight:
                handle.abandon()
        except BaseException as exc:  # noqa: BLE001 - retained and republished to every observer
            finalization.set_exception(exc)
        else:
            finalization.set_result(None)

    def _drain_then_stop(self) -> None:
        """Cancel everything once, then UNWIND to completion. Runs ON the owner loop.

        The loop is stopped only when no task remains pending. A fixed drain deadline
        that stopped the loop anyway would destroy still-pending tasks and then settle
        their futures -- discarding work and labelling it finished, which is exactly what
        the contract forbids. If a cancellation-resistant task never unwinds, this owner
        stays alive and :attr:`is_terminated` stays False: the lifecycle is honestly
        incomplete, and the *caller's* budget is what bounds observation.
        """
        for task in asyncio.all_tasks(self._loop):
            if not task.done():
                task.cancel()
        self._loop.create_task(self._drain_until_settled())

    async def _drain_until_settled(self) -> None:
        while True:
            pending = [
                task
                for task in asyncio.all_tasks(self._loop)
                if not task.done() and task is not asyncio.current_task()
            ]
            if not pending:
                break
            await asyncio.wait(pending, timeout=_DRAIN_POLL_SECONDS)
        self._loop.stop()

    # -- internals ----------------------------------------------------------------

    def _reject_reentrancy(self, method: str) -> None:
        # Identity of the THREAD OBJECT, not its ident. An ident is recycled once a thread
        # exits: on Linux a worker started after this owner terminated received the dead
        # owner's ident and a legitimate blocking close from it was refused as reentrancy
        # (Seam 2, checkpoint B, found in the Linux lane).
        if threading.current_thread() is self._thread:
            raise RuntimeError(f"{method}() blocks its calling thread and must not be called from inside the owner loop")

    def _submit(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        guard: Callable[[], None] | None = None,
        teardown: bool = False,
    ) -> _OwnerOperation:
        # Constructed under the lock so that "admission is still open", the submission
        # and the registry insert are one atomic step against a concurrent `close()`.
        # Otherwise an operation could slip in after close snapshotted the in-flight
        # set and would then never be cancelled or abandoned.
        with self._state_lock:
            if guard is not None:
                # Evaluated under THIS lock so a runtime-level admission decision and
                # this registration cannot be separated by a concurrent close.
                guard()
            closed = self._shutdown_begun or self._state in (
                RedisLoopOwnerState.CLOSING,
                RedisLoopOwnerState.CLOSED,
            )
            if closed and not teardown:
                raise RedisLoopOwnerClosed("the Redis loop owner is closed and never starts a replacement loop")
            if self._state is RedisLoopOwnerState.CLOSED:
                raise RedisLoopOwnerClosed("the Redis loop owner is closed and never starts a replacement loop")
            try:
                handle = _OwnerOperation(self._loop, operation)
            except RuntimeError as exc:  # pragma: no cover - the loop closed underneath us
                raise RedisLoopOwnerClosed(
                    "the Redis loop owner is closed and never starts a replacement loop"
                ) from exc
            self._live.add(handle)
        # Registered OUTSIDE the lock: an already-completed future runs its done
        # callback inline on this thread, and `_forget` takes the same non-reentrant
        # lock.
        handle.future.add_done_callback(self._forget)
        return handle

    def _forget(self, future: ConcurrentFuture) -> None:
        with self._state_lock:
            self._live = {handle for handle in self._live if handle.future is not future}


# --- Shared tool/test loop: separate PROCESSES only --------------------------------

_shared_tool_owner: RedisLoopOwner | None = None
_shared_tool_owner_lock = threading.Lock()


def _acquire_shared_tool_owner() -> RedisLoopOwner:
    """Return the shared tool owner, creating one only when the slot is genuinely free.

    A non-OPEN owner is **retained**, not replaced. Constructing a replacement while the
    old loop is still alive abandons live ownership and can end up driving the old
    clients from a new loop -- the very failure this seam exists to remove. A fresh tool
    lifetime is allowed only once the previous owner has verifiably terminated, and it
    never revives the old owner's resources.
    """
    global _shared_tool_owner
    with _shared_tool_owner_lock:
        current = _shared_tool_owner
        if current is not None:
            if current.state is RedisLoopOwnerState.OPEN:
                return current
            if not current.is_terminated:
                raise RedisLoopOwnerClosed(
                    "the shared Redis tool owner is closing and has not terminated; "
                    "it is retained and no replacement loop is started"
                )
        _shared_tool_owner = RedisLoopOwner(name="optimus-redis-shared-tool-loop")
        return _shared_tool_owner


def shutdown_background_loop(*, timeout: float | None = None) -> None:
    """Stop the shared tool/test owner (test session teardown, tool exit).

    Unlike the loop it replaces, this closes the loop, establishes real thread
    termination and propagates :class:`RedisLoopOwnerShutdownIncomplete` rather than
    dropping its references after a timed-out join and reporting success.

    It closes the **shared tool owner only**. It is not a teardown for a per-runtime
    owner: a :class:`~optimus.redis.runtime.RedisRuntime` closes its own owner through
    its own single teardown path.
    """
    global _shared_tool_owner
    with _shared_tool_owner_lock:
        owner = _shared_tool_owner
    if owner is None:
        return
    try:
        owner.close(timeout=timeout)
    finally:
        with _shared_tool_owner_lock:
            # Identity-protected, and only AFTER verified termination. Clearing the slot
            # first would drop live ownership on a timed-out close, and an identity check
            # stops a late closer from erasing a newer owner that has since replaced it.
            if _shared_tool_owner is owner and owner.is_terminated:
                _shared_tool_owner = None


def sync_await(coro: Coroutine[object, object, T]) -> T:
    """Run a Redis coroutine on the shared tool owner.

    Retained for separate processes -- ``optimus.acp.operator_verify``, the live
    integration tests -- and for the synchronous consumers that checkpoint B will
    inject with their runtime's own owner. Serving code that reaches this function
    after that wiring would reintroduce a second loop owner.
    """
    return _acquire_shared_tool_owner().run_sync(lambda: coro)
