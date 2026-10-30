"""CLI-only stop coordination; observation expiry never releases a resource."""
from __future__ import annotations

import asyncio
import atexit
import math
import os
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from types import FrameType


class StopReason(StrEnum):
    EOF = "eof"
    SIGINT = "sigint"
    SIGTERM = "sigterm"
    ERROR = "error"


class StartupTermination(BaseException):
    """The first pre-loop SIGTERM interrupts synchronous startup."""


_STAGES = frozenset({"running", "serve", "request", "adapter", "worker", "mcp", "writer", "reader", "borrowed_stdio", "redis", "gateway", "startup", "done"})


def cleanup_failure(failures: list[tuple[str, BaseException]]) -> BaseException:
    primary = next((exc for _stage, exc in failures if not isinstance(exc, Exception)), failures[0][1])
    stages = [stage for stage, exc in failures if exc is not primary and stage in _STAGES]
    if stages:
        prefix = "optimus cleanup stages: "
        try:
            notes = getattr(primary, "__notes__", [])
            previous = next((i for i, note in enumerate(notes) if isinstance(note, str) and note.startswith(prefix)), None)
            count = len(stages)
            if previous is not None:
                old_stages, _, old_count = notes[previous][len(prefix):].partition("; count=")
                stages = [stage for stage in old_stages.split(",") if stage in _STAGES] + stages
                count += int(old_count) if old_count.isdecimal() else 0
            note = prefix + ",".join(dict.fromkeys(stages)) + f"; count={min(count, 99)}"
            if previous is None:
                primary.add_note(note)
            else:
                notes[previous] = note
        except BaseException:
            pass  # a diagnostic cannot replace the selected original failure
    return primary


def raise_preserving_failure(failure: BaseException) -> None:
    cause, context, suppress = failure.__cause__, failure.__context__, failure.__suppress_context__
    try:
        raise failure
    finally:
        failure.__cause__, failure.__context__, failure.__suppress_context__ = cause, context, suppress


@dataclass(frozen=True, slots=True)
class ShutdownObservation:
    complete: bool
    stage: str
    pending: int
    failure_stages: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.stage not in _STAGES or self.pending < 0 or len(self.failure_stages) > len(_STAGES):
            raise ValueError("invalid shutdown observation")
        if any(stage not in _STAGES for stage in self.failure_stages):
            raise ValueError("invalid shutdown failure stage")
        if self.complete and self.pending:
            raise ValueError("complete shutdown cannot retain pending ownership")


class ProcessLifecycle:
    def __init__(self, *, report: Callable[[ShutdownObservation], None] | None = None) -> None:
        self._lock = threading.RLock()
        self._reason: StopReason | None = None
        self._state = "RUNNING"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[ShutdownObservation] | None = None
        self._stop = asyncio.Event()
        self._cancel_posted = False
        self._cancel_delivered = False
        self._reported = False
        self._result_seen = False
        self._failure: BaseException | None = None
        self._report = report
        self.signal_count = 0
        self._observation = ShutdownObservation(False, "running", 0, ())
        self._cleanup_started: float | None = None
        self.gateway_attempted = False

    @property
    def reason(self) -> StopReason | None:
        return self._reason

    @property
    def state(self) -> str:
        return self._state

    @property
    def observation(self) -> ShutdownObservation:
        return self._observation

    @property
    def bound(self) -> bool:
        return self._loop is not None

    def bind(self, loop: asyncio.AbstractEventLoop, task: asyncio.Task[ShutdownObservation]) -> None:
        with self._lock:
            if self._task is not None:
                if self._task is task and self._loop is loop:
                    return
                raise RuntimeError("process cleanup already bound")
            self._loop, self._task = loop, task
            if self._reason is not None:
                self._post_stop()
        task.add_done_callback(lambda _task: self.begin_cleanup())

    def request_stop(self, reason: StopReason) -> None:
        with self._lock:
            if reason in (StopReason.SIGINT, StopReason.SIGTERM):
                self.signal_count = min(self.signal_count + 1, 2**31 - 1)
            if self._reason is None:
                self._reason = reason
                self._state = "STOP_REQUESTED"
                self._cleanup_started = monotonic()
                self._post_stop()

    def _post_stop(self) -> None:
        if self._loop is None or self._cancel_posted:
            return
        self._cancel_posted = True
        try:
            self._loop.call_soon_threadsafe(self._apply_stop)
        except RuntimeError:
            pass  # loop loss retains the record; atexit never creates a replacement

    def _apply_stop(self) -> None:
        self._stop.set()
        task = self._task
        if self._reason is not StopReason.EOF and self._state != "DRAINING" and not self._cancel_delivered and task is not None and not task.done():
            self._cancel_delivered = True
            task.cancel()

    def begin_cleanup(self) -> None:
        if self._cleanup_started is None:
            self._cleanup_started = monotonic()
        if self._reason is None:
            self._reason = StopReason.EOF
        if self._state != "COMPLETE":
            self._state = "DRAINING"
        self._stop.set()

    def record(self, observation: ShutdownObservation) -> None:
        self._observation = observation
        if observation.complete and self._task is not None and self._task.done():
            self._state = "COMPLETE"

    def remaining(self, timeout: float = 10.0) -> float:
        return timeout if self._cleanup_started is None else max(0.0, timeout - (monotonic() - self._cleanup_started))

    async def wait_for_stop(self) -> None:
        await self._stop.wait()

    def _consume_result(self) -> None:
        if self._result_seen or self._task is None or not self._task.done():
            return
        self._result_seen = True
        try:
            result = self._task.result()
            if not isinstance(result, ShutdownObservation):
                raise RuntimeError("missing process cleanup observation")
            self._observation = result
        except BaseException as exc:
            self._failure = exc
            previous = self._observation
            self._observation = ShutdownObservation(
                previous.complete, previous.stage, previous.pending,
                tuple(dict.fromkeys((*previous.failure_stages, "serve"))),
            )
        if self._observation.complete:
            self._state = "COMPLETE"

    def report_incomplete(self) -> None:
        observation = self._observation
        if self._reported or observation.complete or not observation.pending:
            return
        self._reported = True
        if self._report is not None:
            with suppress(Exception):
                self._report(observation)

    def observe_at_exit(self) -> None:
        # Finalization may only inspect retained state; even stderr may be blocked.
        self._consume_result()

    # The budget starts with cleanup; expiry reports and returns an incomplete observation instead of raising.
    async def observe(self, timeout: float = 10.0) -> ShutdownObservation:  # noqa: ASYNC109
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("shutdown observation timeout must be positive and finite")
        if self._task is None:
            raise RuntimeError("process cleanup not bound")
        await asyncio.wait({self._task}, timeout=self.remaining(timeout))
        self._consume_result()
        if self._failure is not None:
            raise_preserving_failure(self._failure)
        if not self._task.done() and self._observation.complete:
            self._observation = ShutdownObservation(False, "serve", 1, self._observation.failure_stages)
        if not self._task.done() and not self._observation.pending:
            self._observation = ShutdownObservation(False, "serve", 1, self._observation.failure_stages)
        if not self._observation.complete:
            self.report_incomplete()
        return self._observation

    @property
    def exit_code(self) -> int | None:
        self._consume_result()
        if not self._observation.complete:
            if self._observation.failure_stages:
                return 74
            return 75 if self._observation.stage == "borrowed_stdio" and self.reason in (StopReason.SIGINT, StopReason.SIGTERM) else None
        if self._observation.failure_stages:
            return 74
        return {StopReason.SIGINT: 130, StopReason.SIGTERM: 143}.get(self._reason or StopReason.EOF, 0)


@contextmanager
def signal_handlers(lifecycle: ProcessLifecycle) -> Iterator[None]:
    previous = {}

    def on_signal(number: int, _frame: FrameType | None) -> None:
        first = lifecycle.reason is None
        reason = StopReason.SIGINT if number == signal.SIGINT else StopReason.SIGTERM
        lifecycle.request_stop(reason)
        if first and not lifecycle.bound:
            if reason is StopReason.SIGINT:
                raise KeyboardInterrupt
            raise StartupTermination

    final_observation = lifecycle.observe_at_exit
    try:
        for number in (signal.SIGINT, *((signal.SIGTERM,) if os.name != "nt" else ())):
            previous[number] = signal.getsignal(number)
            signal.signal(number, on_signal)
        atexit.register(final_observation)
        yield
    finally:
        atexit.unregister(final_observation)
        for number, handler in previous.items():
            signal.signal(number, handler)
