"""Dedicated background event-loop supervisor for client MCP SDK work."""

from __future__ import annotations

import asyncio
import concurrent.futures
import math
import os
import threading
from collections.abc import Coroutine
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class MCPSupervisorState(StrEnum):
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    DEAD = "DEAD"


class MCPSupervisorError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"MCPSupervisorError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


def select_process_tree_teardown_seam() -> str:
    return "windows_job_object" if os.name == "nt" else "posix_process_group"


class MCPAsyncSupervisor:
    """Own one background event loop for all client-MCP SDK sessions."""

    def __init__(self, *, close_join_timeout_seconds: float = 5.0) -> None:
        if not math.isfinite(close_join_timeout_seconds) or close_join_timeout_seconds <= 0:
            raise ValueError("close_join_timeout_seconds must be finite and > 0")
        self._close_join_timeout_seconds = close_join_timeout_seconds
        self._state = MCPSupervisorState.DEAD
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._inflight: set[concurrent.futures.Future[object]] = set()
        # Monotonic id for the currently-owned loop/thread. A close() that captured
        # an older generation must never finalize (clear/erase) a newer one.
        self._generation = 0

    @property
    def state(self) -> MCPSupervisorState:
        return self._state

    def start(self) -> None:
        with self._lock:
            if self._state is MCPSupervisorState.RUNNING:
                return
            if self._state is MCPSupervisorState.STOPPING:
                # Refuse throughout STOPPING -- including thread-dead-but-not-yet
                # finalized. Restart is admitted only once close() has published DEAD.
                raise MCPSupervisorError("SUPERVISOR_STOPPING")
            loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                try:
                    loop.run_forever()
                finally:
                    # Drain + close on the owning thread. Stopping first then
                    # cancel/gather avoids Windows ProactorEventLoop leaving
                    # tasks stuck in "cancelling" and leaking IOCP handles.
                    try:
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        if pending:
                            loop.run_until_complete(
                                asyncio.gather(*pending, return_exceptions=True)
                            )
                    finally:
                        loop.close()

            try:
                thread = threading.Thread(
                    target=_run, name="optimus-client-mcp-supervisor", daemon=True
                )
                thread.start()
            except BaseException:
                # Partial-start rollback: the loop was allocated but its owning
                # thread never ran, so no other party can close it. Close it here
                # and preserve DEAD + the original exception.
                loop.close()
                raise
            self._loop = loop
            self._thread = thread
            self._generation += 1
            self._state = MCPSupervisorState.RUNNING

    def submit(self, coro: Coroutine[object, object, T], *, timeout_seconds: float) -> T:
        with self._lock:
            if self._state is not MCPSupervisorState.RUNNING or self._loop is None:
                coro.close()
                raise MCPSupervisorError("SUPERVISOR_DEAD")
            loop = self._loop
            future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(coro, loop)
            self._inflight.add(future)  # type: ignore[arg-type]

        try:
            return future.result(timeout=timeout_seconds)
        except TimeoutError as exc:
            future.cancel()
            raise MCPSupervisorError("SUBMIT_TIMEOUT") from exc
        except concurrent.futures.CancelledError as exc:
            raise MCPSupervisorError("SUPERVISOR_SHUTDOWN") from exc
        except Exception as exc:
            if self._state in {MCPSupervisorState.STOPPING, MCPSupervisorState.DEAD}:
                raise MCPSupervisorError("SUPERVISOR_SHUTDOWN") from exc
            raise
        finally:
            with self._lock:
                self._inflight.discard(future)  # type: ignore[arg-type]

    def close(self) -> None:
        captured = self._begin_close()
        if captured is None:
            return
        generation, loop, thread, inflight, initiated = captured

        if initiated:
            # ONLY the closer that transitioned RUNNING -> STOPPING may signal the owner
            # to stop. A later close must wait/finalize instead: re-issuing loop.stop while
            # the owner is already inside its finally's run_until_complete(gather(...))
            # aborts that drain with RuntimeError and destroys the pending cleanup task,
            # after which _finalize would see a dead thread and publish a FALSE completion.
            for future in inflight:
                future.cancel()

            if loop is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass

        if thread is not None and thread.is_alive():
            thread.join(timeout=self._close_join_timeout_seconds)

        self._finalize(generation, thread)

    def _begin_close(
        self,
    ) -> tuple[
        int,
        asyncio.AbstractEventLoop | None,
        threading.Thread | None,
        list[concurrent.futures.Future[object]],
        bool,
    ] | None:
        with self._lock:
            if self._state is MCPSupervisorState.DEAD:
                return None
            # `initiated` marks the single closer that owns signalling the stop.
            initiated = self._state is MCPSupervisorState.RUNNING
            if initiated:
                self._state = MCPSupervisorState.STOPPING
            return (self._generation, self._loop, self._thread, list(self._inflight), initiated)

    def _finalize(self, generation: int, thread: threading.Thread | None) -> None:
        with self._lock:
            if self._generation != generation:
                # A newer generation was started after we captured ours; never
                # erase it -- that is the stale-closer hazard.
                return
            if self._state is MCPSupervisorState.DEAD:
                # Already finalized (e.g. by a concurrent closer of this generation).
                return
            if thread is not None and thread.is_alive():
                # Incomplete shutdown: the owning thread is still draining. Retain
                # ownership and stay STOPPING; a later close() re-joins and finalizes.
                return
            if thread is not None and self._loop is not None and not self._loop.is_closed():
                # The owning thread is gone but never closed its own loop, so its drain
                # did not complete. Retain ownership rather than publish a false
                # completion; the loop is only ever closed by its owner.
                return
            # The owning thread has terminated (or never existed) and closed its own
            # loop in its finally. Finalize this generation.
            self._loop = None
            self._thread = None
            self._inflight.clear()
            self._state = MCPSupervisorState.DEAD
