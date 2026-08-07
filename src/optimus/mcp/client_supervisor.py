"""Dedicated background event-loop supervisor for client MCP SDK work."""

from __future__ import annotations

import asyncio
import concurrent.futures
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

    def __init__(self) -> None:
        self._state = MCPSupervisorState.DEAD
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._inflight: set[concurrent.futures.Future[object]] = set()

    @property
    def state(self) -> MCPSupervisorState:
        return self._state

    def start(self) -> None:
        with self._lock:
            if self._state is MCPSupervisorState.RUNNING:
                return
            loop = asyncio.new_event_loop()

            def _run() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            thread = threading.Thread(target=_run, name="optimus-client-mcp-supervisor", daemon=True)
            thread.start()
            self._loop = loop
            self._thread = thread
            self._state = MCPSupervisorState.RUNNING

    def submit(self, coro: Coroutine[object, object, T], *, timeout_seconds: float) -> T:
        with self._lock:
            if self._state is not MCPSupervisorState.RUNNING or self._loop is None:
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
        with self._lock:
            if self._state is MCPSupervisorState.DEAD:
                return
            self._state = MCPSupervisorState.STOPPING
            loop = self._loop
            thread = self._thread
            inflight = list(self._inflight)
        for future in inflight:
            future.cancel()
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        with self._lock:
            self._loop = None
            self._thread = None
            self._inflight.clear()
            self._state = MCPSupervisorState.DEAD
