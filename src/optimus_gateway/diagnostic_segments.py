"""The per-user Gateway diagnostic copy (Plan 12.8; memory design v4 section 7; ADR-032).

A best-effort, bounded copy of the Gateway's diagnostic lines under ``<accounting root>/gateway-diagnostics/``, beside
the existing stderr / workspace ``local-gateway.log``, which is unchanged. Only allowlisted structured events are
copied, sanitized again, each wrapped with a sequence and its UTC time. Every offered line takes a sequence, so a line
that was dropped, refused or failed leaves a gap; a restarted Gateway continues after the newest retained sequence.

The directory is per user, so every Gateway of that user shares it (Codex Checkpoint C, finding 1): each line is
appended under the directory's lock file, which serializes the Gateways' sequence, rollover, retention and capacity
decisions on what is on disk then, and no segment is held open between lines. A line goes to its UTC day's newest
segment (or to a newer day's, never an older one) unless it would exceed 64 MiB there or that segment ends in a torn
line; otherwise a new segment starts.
Closed segments are retained for 30 days within a 256 MiB total, oldest removed first; the segment being appended to
is never removed or truncated, and when space cannot be made the line is refused and counted.
Writes go through one bounded queue on one owned thread, so a blocked disk or a held lock never stalls a request; a full
queue drops the line and counts it. Each accepted line is flushed; this is not an fsynced accounting boundary.
``status()`` reports the retained date/sequence range and every drop or failure; failures are also reported once each
through ``report`` until the copy writes again. These limits never touch ledger or outbox data, and an expired or
unwritten line is unavailable reconciliation evidence.
"""

from __future__ import annotations

import contextlib
import json
import queue
import re
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from optimus_security.failure_facts import final_sanitize

SEGMENT_BYTES = 64 * 1024 * 1024
RETAIN_DAYS = 30
CAP_BYTES = 256 * 1024 * 1024
QUEUE_LINES = 4096  # agent-selected
MAX_RECORD_BYTES = 64 * 1024  # agent-selected: a larger record is refused, never split
# The structured events the Gateway writes through `request_diagnostics.write_log_line`; anything else is not copied.
EVENTS = frozenset({"model_request", "model_attempt", "reply_undeliverable"})
_NAME = re.compile(r"gateway-diagnostics-(\d{8})-(\d{6})\.log")
LOCK_NAME = "gateway-diagnostics.lock"


@dataclass(frozen=True)
class DiagnosticStatus:
    first: tuple[str, int] | None  # (UTC date, sequence) of the oldest retained record
    last: tuple[str, int] | None  # of the newest record this process wrote
    segments: int
    retained_bytes: int
    written: int
    dropped_queue_full: int
    refused_malformed: int
    refused_oversized: int
    refused_no_space: int
    write_failures: int
    deletion_failures: int
    last_failure: str | None


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@contextlib.contextmanager
def _directory_lock(path: Path) -> Iterator[None]:
    """Exclusive across processes for the duration of one line. On Windows the lock is retried for about 10 s before
    it raises, which the writer counts as a write failure."""
    with open(path, "a+b") as handle:
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                with contextlib.suppress(OSError):
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield  # closing the handle releases it


class DiagnosticSegments:
    def __init__(self, root: Path, *, segment_bytes: int = SEGMENT_BYTES, retain_days: int = RETAIN_DAYS,
                 cap_bytes: int = CAP_BYTES, queue_lines: int = QUEUE_LINES, clock: Callable[[], datetime] = _utc_now,
                 report: Callable[[str], None] | None = None) -> None:
        if not MAX_RECORD_BYTES < segment_bytes < cap_bytes:
            raise ValueError("a record must fit a segment and a segment must be smaller than the total cap")
        self._root = root
        self._segment_bytes = segment_bytes
        self._retain = timedelta(days=retain_days)
        self._cap = cap_bytes
        self._clock = clock
        self._report = report
        self._queue: queue.Queue[tuple[int, datetime, str] | None] = queue.Queue(maxsize=queue_lines)
        self._lock = threading.Lock()  # admission, counters and shutdown
        self._counts = dict.fromkeys(("written", "dropped_queue_full", "refused_malformed", "refused_oversized",
                                      "refused_no_space", "write_failures", "deletion_failures"), 0)
        self._last_failure: str | None = None
        self._reported: set[str] = set()
        self._offered = 0
        self._written_offered = 0  # the offer number of this process's last written line; owned by the writer thread
        self._last: tuple[str, int] | None = None
        self._thread: threading.Thread | None = None
        self._closed = False

    def write(self, line: str) -> None:
        """Offer one diagnostic line; never blocks and never raises."""
        with self._lock:
            if self._closed:
                return
            self._offered += 1
            if self._thread is None:
                thread = threading.Thread(target=self._run, name="gateway-diagnostic-copy", daemon=True)
                try:
                    thread.start()
                except RuntimeError:
                    self._failed_locked("write_failures", "thread_unavailable")
                    return
                self._thread = thread
            try:
                self._queue.put_nowait((self._offered, self._clock(), line))
            except queue.Full:
                self._failed_locked("dropped_queue_full", "queue_full")

    def _run(self) -> None:
        while (item := self._queue.get()) is not None:
            try:
                self._append(*item)
            except OSError as exc:
                self._failed("write_failures", f"write:{type(exc).__name__}")
            if self._closed and self._queue.empty():
                return  # closed while the queue was full, so no stop item may come: the drained queue ends the thread

    def _append(self, offered: int, at: datetime, line: str) -> None:
        try:
            parsed: Any = json.loads(line)
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict) or parsed.get("event") not in EVENTS:
            self._failed("refused_malformed", "malformed")
            return
        sanitized = final_sanitize(parsed)
        self._root.mkdir(parents=True, exist_ok=True)
        with _directory_lock(self._root / LOCK_NAME):
            segments = self._segments()
            # Never into a segment older than the newest (Codex Checkpoint C pass 2): a line queued before midnight but
            # written after another Gateway started the new day goes into that day's segment with its own time, so the
            # newest segment always holds the highest sequence.
            day = at.strftime("%Y%m%d")
            if segments and segments[-1][0] > day:
                day = segments[-1][0]
            # After the newest retained line, whichever Gateway wrote it, leaving a gap for each of this process's
            # lines offered since its last written one.
            seq = self._newest_retained(segments) + offered - self._written_offered
            body = {"seq": seq, "at": at.isoformat(), "record": sanitized}
            record = (json.dumps(body, ensure_ascii=True, separators=(",", ":"), sort_keys=True, default=str) + "\n").encode("ascii")
            if len(record) > MAX_RECORD_BYTES:
                self._failed("refused_oversized", "oversized")
                return
            target, new = self._target(segments, day, len(record))
            if not self._make_room(segments, target, len(record), at):
                self._failed("refused_no_space", "no_space")
                return
            with open(target, "xb" if new else "ab") as handle:
                handle.write(record)
                handle.flush()
        self._written_offered = offered
        with self._lock:
            self._counts["written"] += 1
            self._last = (day, seq)
            self._reported.clear()  # a later failure is reported again

    def _segments(self) -> list[tuple[str, int, Path]]:
        try:
            names = list(self._root.iterdir())
        except OSError:  # absent or unavailable: nothing is retained here
            return []
        found = [(m.group(1), int(m.group(2)), p) for p in names if (m := _NAME.fullmatch(p.name))]
        return sorted(found)

    def _newest_retained(self, segments: list[tuple[str, int, Path]]) -> int:
        """The newest retained sequence: the last whole record of the newest segment holding one; 0 when none."""
        for _, _, path in reversed(segments):
            try:
                with open(path, "rb") as handle:
                    size = handle.seek(0, 2)
                    handle.seek(max(0, size - MAX_RECORD_BYTES - 1))
                    tail = handle.read().split(b"\n")
            except OSError:
                continue
            for raw in reversed(tail[:-1] if len(tail) > 1 else []):  # the piece after the final newline is torn or empty
                try:
                    return int(json.loads(raw)["seq"])
                except (ValueError, KeyError, TypeError):
                    continue
        return 0

    def _target(self, segments: list[tuple[str, int, Path]], day: str, incoming: int) -> tuple[Path, bool]:
        """The segment this line goes to, and whether it is new: the day's newest unless the line would make it exceed
        its size or it ends in a torn line, which is never appended to."""
        today = [(index, path) for d, index, path in segments if d == day]
        if not today:
            return self._root / f"gateway-diagnostics-{day}-000001.log", True
        index, path = today[-1]
        with open(path, "rb") as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - 1))
            whole = size == 0 or handle.read(1) == b"\n"
        if whole and size + incoming <= self._segment_bytes:
            return path, False
        return self._root / f"gateway-diagnostics-{day}-{index + 1:06d}.log", True

    def _make_room(self, segments: list[tuple[str, int, Path]], target: Path, incoming: int, at: datetime) -> bool:
        """Remove expired closed segments, then the oldest closed ones until ``incoming`` fits the cap; never the
        segment the line goes to. A segment that cannot be removed stays counted."""
        cutoff = (at - self._retain).strftime("%Y%m%d")
        retained: list[tuple[str, Path, int]] = []
        for day, _, path in segments:
            try:
                retained.append((day, path, path.stat().st_size))
            except FileNotFoundError:
                continue
        total = sum(size for _, _, size in retained)
        for day, path, size in retained:
            if path == target or (day >= cutoff and total + incoming <= self._cap):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                self._failed("deletion_failures", f"delete:{type(exc).__name__}")
                continue
            total -= size
        return total + incoming <= self._cap

    def _failed(self, counter: str, code: str) -> None:
        with self._lock:
            self._failed_locked(counter, code)

    def _failed_locked(self, counter: str, code: str) -> None:
        self._counts[counter] += 1
        self._last_failure = code
        if self._report is not None and code not in self._reported:
            self._reported.add(code)
            with contextlib.suppress(Exception):  # reporting a diagnostic failure never fails anything else
                self._report(f"optimus-local-gateway: diagnostic copy {counter.replace('_', ' ')} ({code}).")

    def status(self) -> DiagnosticStatus:
        segments = self._segments()
        first = None
        sizes = 0
        for day, _, path in segments:
            try:
                sizes += path.stat().st_size
                if first is None:
                    with open(path, "rb") as handle:
                        first = (day, int(json.loads(handle.readline())["seq"]))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        with self._lock:
            return DiagnosticStatus(first, self._last, len(segments), sizes, **self._counts, last_failure=self._last_failure)

    def close(self, timeout: float = 5.0) -> bool:
        """Stop admitting, then wait up to ``timeout`` for the thread to write what was queued. False when the writer
        is still blocked; it then writes what is queued and ends on its own."""
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is None:
            return True
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            return False
        thread.join(timeout)
        return not thread.is_alive()
