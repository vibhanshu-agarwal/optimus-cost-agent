"""RED/GREEN contract for MCPAsyncSupervisor (P11-FU-9 Task 3)."""

from __future__ import annotations

import asyncio
import gc
import inspect
import os
import threading
import time
import warnings

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
