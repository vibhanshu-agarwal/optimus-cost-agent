"""Shared concurrency diagnostics for tests: a failed check never loses its context.

Operator directive (2026-10-02): tests must make issues cheap to catch, above all where threads,
tasks or processes are involved. Every helper here raises with a report that names each offending
thread, task, process or row, what it was running, and where it currently is.

Capture has ONE owner, ``tools/concurrency_capture.py`` (shared with the H5 shutdown schedule);
this module only asserts and formats multi-line reports.

Rules every helper keeps:

* The verdict is taken at detection time. A diagnostic join afterwards only annotates the report
  ("still alive after a bounded join: yes/no"); it can never turn an observed leak into a pass.
* Reports carry names, ids, flags, qualified names and frame locations (``file:line in function``)
  only -- never local-variable values, source text, credentials or process command lines.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from tools.concurrency_capture import (
    FrameLocation,
    ThreadSnapshot,
    alive_after_bounded_join,
    snapshot_process,
    snapshot_task,
    snapshot_threads,
)

DIAGNOSTIC_JOIN_SECONDS = 0.2
_MAX_ROWS = 20


def _frame_lines(frames: tuple[FrameLocation, ...], empty: str) -> list[str]:
    """Outermost first, like a traceback."""
    if not frames:
        return [f"    at {empty}"]
    return [f"    at {frame.filename}:{frame.lineno} in {frame.function}" for frame in reversed(frames)]


def _thread_text(snapshot: ThreadSnapshot) -> str:
    header = (
        f"thread {snapshot.name!r} ident={snapshot.ident} native_id={snapshot.native_id} "
        f"daemon={snapshot.daemon} alive={snapshot.alive} target={snapshot.target}"
    )
    empty = "<never started>" if snapshot.ident is None else "<no live frame>"
    return "\n".join([header, *_frame_lines(snapshot.frames, empty)])


def describe_thread(thread: threading.Thread) -> str:
    """One thread: identity, flags, target and current stack."""
    return _thread_text(snapshot_threads([thread])[0])


def _report_threads(what: str, offenders: Sequence[threading.Thread], verdict: str) -> str:
    snapshots = snapshot_threads(offenders)  # the detection-time picture, one instant
    annotated = []
    for thread, snapshot in zip(offenders, snapshots, strict=True):
        still = "yes" if alive_after_bounded_join(thread, DIAGNOSTIC_JOIN_SECONDS) else "no"
        annotated.append(
            f"{_thread_text(snapshot)}\n    still alive after a {DIAGNOSTIC_JOIN_SECONDS}s diagnostic join: {still}"
        )
    return f"{what}: {len(offenders)} thread(s) {verdict} at detection\n" + "\n".join(annotated)


def assert_threads_stopped(threads: Iterable[threading.Thread], what: str) -> None:
    """Every given thread has already exited. Judged NOW; the report then annotates."""
    alive = [thread for thread in threads if thread.is_alive()]
    if alive:
        raise AssertionError(_report_threads(what, alive, "still alive"))


def assert_threads_alive(threads: Iterable[threading.Thread], what: str) -> None:
    """Every given thread is still running (a precondition); a dead one is described."""
    dead = [thread for thread in threads if not thread.is_alive()]
    if dead:
        raise AssertionError(
            f"{what}: {len(dead)} thread(s) not alive at detection\n"
            + "\n".join(_thread_text(snapshot) for snapshot in snapshot_threads(dead))
        )


def thread_baseline() -> frozenset[threading.Thread]:
    """Thread OBJECTS alive now. Compared by identity: an ident is recycled, a Thread is not."""
    return frozenset(threading.enumerate())


def new_threads(baseline: frozenset[threading.Thread]) -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread not in baseline and thread.is_alive()]


def assert_no_new_threads(baseline: frozenset[threading.Thread], what: str) -> None:
    """No thread outside ``baseline`` is alive now."""
    leaked = new_threads(baseline)
    if leaked:
        raise AssertionError(_report_threads(what, leaked, "outside the baseline still alive"))


def describe_task(task: asyncio.Future[Any]) -> str:
    """One asyncio task: name, coroutine, state and suspended stack."""
    snapshot = snapshot_task(task)
    header = f"task {snapshot.name!r} coro={snapshot.coroutine} state={snapshot.state}"
    return "\n".join([header, *_frame_lines(snapshot.frames, "<no frame>")])


def assert_tasks_done(tasks: Iterable[asyncio.Future[Any]], what: str) -> None:
    pending = [task for task in tasks if not task.done()]
    if pending:
        raise AssertionError(
            f"{what}: {len(pending)} task(s) pending at detection\n"
            + "\n".join(describe_task(task) for task in pending)
        )


def describe_process(process: Any) -> str:
    """A child process: pid and exit state only -- never its command line."""
    snapshot = snapshot_process(process)
    state = "running" if snapshot.running else f"exited({snapshot.returncode})"
    return f"process pid={snapshot.pid} state={state}"


def assert_processes_exited(processes: Iterable[Any], what: str) -> None:
    running = [process for process in processes if snapshot_process(process).running]
    if running:
        raise AssertionError(
            f"{what}: {len(running)} process(es) running at detection\n"
            + "\n".join(describe_process(process) for process in running)
        )


def _render_row(row: Any, fields: Sequence[str] | None) -> str:
    if fields is None:
        return repr(row)
    if isinstance(row, Mapping):
        return repr({field: row.get(field) for field in fields})
    return repr({field: getattr(row, field, None) for field in fields})


def assert_no_offending_rows(
    rows: Iterable[Any],
    is_offending: Callable[[Any], object],
    what: str,
    *,
    fields: Sequence[str] | None = None,
) -> None:
    """No row offends. On failure, print the offending rows (index, chosen fields) and the total."""
    materialized = list(rows)
    offending = [(index, row) for index, row in enumerate(materialized) if is_offending(row)]
    if offending:
        shown = offending[:_MAX_ROWS]
        raise AssertionError(
            f"{what}: {len(offending)} of {len(materialized)} row(s) offend; first {len(shown)}:\n"
            + "\n".join(f"  [{index}] {_render_row(row, fields)}" for index, row in shown)
        )


def assert_some_row(
    rows: Iterable[Any],
    predicate: Callable[[Any], object],
    what: str,
    *,
    fields: Sequence[str] | None = None,
) -> None:
    """At least one row satisfies ``predicate``. On failure, print the candidates that did not."""
    materialized = list(rows)
    if not any(predicate(row) for row in materialized):
        shown = materialized[:_MAX_ROWS]
        raise AssertionError(
            f"{what}: none of {len(materialized)} row(s) matched; first {len(shown)}:\n"
            + "\n".join(f"  [{index}] {_render_row(row, fields)}" for index, row in enumerate(shown))
        )
