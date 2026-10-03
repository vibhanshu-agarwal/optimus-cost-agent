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
* Rows are rendered by ``safe_view`` only, never by ``repr``: see its policy.
"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import functools
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence
from tools.concurrency_capture import (
    FrameLocation,
    ProcessSnapshot,
    ProcessWatch,
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


def _process_state(snapshot: Any) -> str:
    if snapshot.running:
        return "running"
    return "exited" if snapshot.returncode is None else f"exited({snapshot.returncode})"


def describe_process(process: Any) -> str:
    """A child process: pid and exit state only -- never its command line."""
    snapshot = snapshot_process(process)
    return f"process pid={snapshot.pid} state={_process_state(snapshot)}"


def assert_processes_exited(processes: Iterable[Any], what: str) -> None:
    running = [process for process in processes if snapshot_process(process).running]
    if running:
        raise AssertionError(
            f"{what}: {len(running)} process(es) running at detection\n"
            + "\n".join(describe_process(process) for process in running)
        )


def announce_pid_code(directory: Path | str, role: str) -> str:
    """Python statements a descendant runs first: publish its pid as ``<directory>/<role>.pid``."""
    target = str(Path(directory) / f"{role}.pid")
    return (
        f"import os as _o; _t = {target!r}; open(_t + '.tmp', 'w').write(str(_o.getpid())); "
        "_o.replace(_t + '.tmp', _t)"
    )


class DescendantRecorder:
    """Watches ``directory`` for the pid files the named descendants announce (``announce_pid_code``).

    Each descendant is pinned the moment its file appears (``ProcessWatch``), and the moment it
    is first seen gone is recorded. A test can then tell a descendant that was killed from one
    that only exited after the run under test waited for it -- which an elapsed-time check, or
    a liveness check made after that wait, cannot.
    """

    def __init__(self, directory: Path | str, roles: Iterable[str], *, poll_seconds: float = 0.01) -> None:
        self._directory = Path(directory)
        self._roles = tuple(roles)
        self._poll = poll_seconds
        self._lock = threading.Lock()
        self._watches: dict[str, ProcessWatch] = {}
        self._pids: dict[str, int] = {}
        self._exit_seen: dict[str, float] = {}
        self._final: dict[str, ProcessSnapshot] = {}
        self._closed = False
        self._error: BaseException | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="descendant-recorder", daemon=True)

    def __enter__(self) -> DescendantRecorder:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._closed = True
        self._stop.set()
        self._thread.join(5)
        if self._error is None:
            self._scan()
        with self._lock:
            for role, watch in self._watches.items():
                self._final[role] = watch.snapshot()
                watch.close()

    def _run(self) -> None:
        try:
            while not self._stop.wait(self._poll):
                self._scan()
        except Exception as exc:  # noqa: BLE001 - kept and reported by the verdict, never swallowed
            self._error = exc

    def _scan(self) -> None:
        now = time.monotonic()
        for role in self._roles:
            if role in self._pids:
                continue
            try:
                pid = int((self._directory / f"{role}.pid").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            with self._lock:
                self._pids[role] = pid
                try:
                    self._watches[role] = ProcessWatch(pid)
                except ProcessLookupError:
                    # The platform positively reported no such process: it exited by now at the latest.
                    # Any other failure (access denied) propagates and stops the recorder, which the
                    # verdict reports -- an unobservable process is never recorded as gone.
                    self._exit_seen[role] = now
        with self._lock:
            for role, watch in self._watches.items():
                if role not in self._exit_seen and not watch.snapshot().running:
                    self._exit_seen[role] = now

    def _wait(self, condition: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if condition():
                    return True
            time.sleep(self._poll)
        with self._lock:
            return condition()

    def wait_for(self, roles: Iterable[str], *, timeout: float) -> bool:
        """Wait until every role has announced itself."""
        wanted = list(roles)
        return self._wait(lambda: all(role in self._pids for role in wanted), timeout)

    def wait_for_exit(self, roles: Iterable[str], *, timeout: float) -> bool:
        """Wait until every role has been seen gone."""
        wanted = list(roles)
        return self._wait(lambda: all(role in self._exit_seen for role in wanted), timeout)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> BaseException | None:
        """Why the recorder stopped watching early, if it did."""
        return self._error

    def outcome(self, role: str) -> tuple[int | None, ProcessSnapshot | None, float | None]:
        """(pid, latest snapshot, monotonic time first seen gone) -- Nones where unknown."""
        with self._lock:
            snapshot = self._final.get(role)
            watch = self._watches.get(role)
            if snapshot is None and watch is not None:
                snapshot = watch.snapshot()
            return self._pids.get(role), snapshot, self._exit_seen.get(role)


def assert_descendants_killed(
    recorder: DescendantRecorder, roles: Iterable[str], *, deadline: float, what: str
) -> None:
    """Every role announced itself, and was gone by ``deadline`` (a ``time.monotonic()`` value).

    A kill takes effect asynchronously, so the verdict is taken at the deadline: this waits, at
    most until then, for announced descendants to be seen gone. Call it inside the recorder's
    ``with`` block, while it is still watching.
    """
    if recorder.closed:
        raise RuntimeError("assert_descendants_killed() needs an open recorder: call it inside its with block")
    if recorder.error is not None:
        raise AssertionError(f"{what}: the descendant recorder stopped watching: {recorder.error!r}") from recorder.error
    wanted = list(roles)
    announced = [role for role in wanted if recorder.outcome(role)[0] is not None]
    recorder.wait_for_exit(announced, timeout=max(0.0, deadline - time.monotonic()))
    lines: list[str] = []
    for role in wanted:
        pid, snapshot, gone_at = recorder.outcome(role)
        if pid is None:
            lines.append(f"{role} never announced a pid, so the run proves nothing about it")
        elif gone_at is None:
            state = _process_state(snapshot) if snapshot is not None else "unknown"
            lines.append(f"{role} pid={pid} state={state}")
        elif gone_at > deadline:
            lines.append(
                f"{role} pid={pid} exited {gone_at - deadline:.2f}s after the deadline (it was waited for, not killed)"
            )
    if lines:
        raise AssertionError(
            f"{what}: {len(lines)} of {len(wanted)} descendant(s) not killed by the deadline\n" + "\n".join(lines)
        )


# Keys whose values are never shown: command lines, environments, payloads, streams, locals.
_WITHHELD_KEY = re.compile(
    r"(?i)(?:^|[_\-.])(?:argv|args|cmd|cmdline|command|command_line|env|environ|environment|payload|body"
    r"|content|headers|stdin|stdout|stderr|locals)(?:$|[_\-.])"
)
_MAX_DEPTH = 4
_MAX_ITEMS = 12
_MAX_TEXT = 300


@functools.lru_cache(maxsize=1024)
def _is_secret_key(key: str) -> bool:
    """Whether the project's evidence policy treats ``key`` as naming a secret value."""
    return sanitize_for_persistence({key: "probe"}, policy=EVIDENCE_REDACTION_POLICY).value != {key: "probe"}


def _safe_text(text: str) -> str:
    redacted = sanitize_for_persistence(text, policy=EVIDENCE_REDACTION_POLICY).value
    text = redacted if isinstance(redacted, str) else "<redacted>"
    return text if len(text) <= _MAX_TEXT else f"{text[:_MAX_TEXT]}...(+{len(text) - _MAX_TEXT} chars)"


def _capped(items: list[Any]) -> tuple[list[Any], str]:
    extra = len(items) - _MAX_ITEMS
    return items[:_MAX_ITEMS], (f", ...+{extra} more" if extra > 0 else "")


def _safe_entry(key: Any, value: Any, depth: int) -> str:
    if isinstance(key, str):
        if _WITHHELD_KEY.search(key):
            return "'<withheld>'"
        if _is_secret_key(key):
            return "'<redacted>'"
    return safe_view(value, _depth=depth + 1)


def safe_view(value: Any, *, _depth: int = 0) -> str:
    """Render a diagnostic value under the credential-free policy (Codex review R4, P11-FU-33 batch).

    Scalars, enums and strings keep their identity; strings pass through the project's evidence
    redaction (``optimus_security.sanitization``: secret-named keys, bearer headers, known token
    prefixes, high-entropy tokens) and are truncated. Values under secret-named keys are
    ``<redacted>``; under command, environment, payload, stream or locals keys ``<withheld>``.
    Dataclasses show their fields under the same rules; any other object is ``<TypeName>`` and
    its ``repr`` is never called. Depth and item counts are capped. A string that looks like an
    ordinary identifier under an ordinary key cannot be told from one and is shown.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, str):
        return repr(_safe_text(value))
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{type(value).__name__} len={len(value)}>"
    if _depth >= _MAX_DEPTH:
        return f"<{type(value).__name__}>"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields, more = _capped([(field.name, getattr(value, field.name)) for field in dataclasses.fields(value)])
        return f"{type(value).__name__}(" + ", ".join(f"{k}={_safe_entry(k, v, _depth)}" for k, v in fields) + more + ")"
    if isinstance(value, Mapping):
        entries, more = _capped(list(value.items()))
        return "{" + ", ".join(f"{safe_view(k, _depth=_depth + 1)}: {_safe_entry(k, v, _depth)}" for k, v in entries) + more + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        items, more = _capped(sorted(value, key=repr) if isinstance(value, (set, frozenset)) else list(value))
        body = ", ".join(safe_view(item, _depth=_depth + 1) for item in items) + more
        if isinstance(value, tuple):
            return f"({body},)" if len(items) == 1 and not more else f"({body})"
        return f"[{body}]" if isinstance(value, list) else "{" + body + "}"
    return f"<{type(value).__name__}>"


def _render_row(row: Any, fields: Sequence[str] | None) -> str:
    """One row under the credential-free policy; with ``fields``, only those that the row has."""
    if fields is None:
        return safe_view(row)
    if isinstance(row, Mapping):
        chosen = {field: row[field] for field in fields if field in row}
    else:
        chosen = {field: getattr(row, field) for field in fields if hasattr(row, field)}
    return safe_view(chosen)


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
