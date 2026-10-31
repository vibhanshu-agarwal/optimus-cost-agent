"""The per-user Gateway diagnostic copy (Plan 12.8; memory design v4 section 7; ADR-032).

A best-effort, bounded copy of the Gateway's diagnostic lines under ``<accounting root>/gateway-diagnostics/``, beside
the existing stderr / workspace ``local-gateway.log``, which is unchanged. Only allowlisted structured events are
copied, sanitized again, each wrapped with a sequence and its UTC time. Every offered line takes a sequence, so a line
that was dropped, refused or failed leaves a gap; a restarted Gateway continues after the newest retained sequence.

Segments are append-only and never reopened: one rolls before it would exceed 64 MiB or when the UTC day changes.
Closed segments are retained for 30 days within a 256 MiB total, oldest removed first; the active segment is never
truncated, and when space cannot be made the line is refused and counted. Writes go through one bounded queue on one
owned thread, so a blocked disk never stalls a request; a full queue drops the line and counts it. Each accepted line
is flushed; this is not an fsynced accounting boundary. ``status()`` reports the retained date/sequence range and every
drop or failure; failures are also reported once each through ``report`` until the copy writes again. These limits
never touch ledger or outbox data, and an expired or unwritten line is unavailable reconciliation evidence.
"""

from __future__ import annotations

import contextlib
import json
import queue
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO

from optimus_security.failure_facts import final_sanitize

SEGMENT_BYTES = 64 * 1024 * 1024
RETAIN_DAYS = 30
CAP_BYTES = 256 * 1024 * 1024
QUEUE_LINES = 4096  # agent-selected
MAX_RECORD_BYTES = 64 * 1024  # agent-selected: a larger record is refused, never split
# The structured events the Gateway writes through `request_diagnostics.write_log_line`; anything else is not copied.
EVENTS = frozenset({"model_request", "model_attempt", "reply_undeliverable"})
_NAME = re.compile(r"gateway-diagnostics-(\d{8})-(\d{6})\.log")


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
        self._base: int | None = None  # the newest retained sequence when this process started; resolved by the thread
        self._last: tuple[str, int] | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        # Owned by the writer thread only.
        self._handle: BinaryIO | None = None
        self._active: Path | None = None
        self._day: str | None = None
        self._size = 0
        self._total = 0

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
        try:
            while (item := self._queue.get()) is not None:
                try:
                    self._append(*item)
                except OSError as exc:
                    self._close_handle()  # the next line opens a new segment
                    self._failed("write_failures", f"write:{type(exc).__name__}")
        finally:
            self._close_handle()

    def _append(self, offered: int, at: datetime, line: str) -> None:
        if self._base is None:
            self._base = self._newest_retained()
        seq = self._base + offered
        record = self._record(seq, at, line)
        if record is None:
            return
        day = at.strftime("%Y%m%d")
        if self._handle is None or day != self._day or self._size + len(record) > self._segment_bytes:
            self._roll(day, at)
        if self._total + len(record) > self._cap and not self._make_room(len(record), at):
            self._failed("refused_no_space", "no_space")
            return
        assert self._handle is not None
        self._handle.write(record)
        self._handle.flush()
        self._size += len(record)
        self._total += len(record)
        with self._lock:
            self._counts["written"] += 1
            self._last = (day, seq)
            self._reported.clear()  # a later failure is reported again

    def _record(self, seq: int, at: datetime, line: str) -> bytes | None:
        try:
            parsed: Any = json.loads(line)
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict) or parsed.get("event") not in EVENTS:
            self._failed("refused_malformed", "malformed")
            return None
        body = {"seq": seq, "at": at.isoformat(), "record": final_sanitize(parsed)}
        record = (json.dumps(body, ensure_ascii=True, separators=(",", ":"), sort_keys=True, default=str) + "\n").encode("ascii")
        if len(record) > MAX_RECORD_BYTES:
            self._failed("refused_oversized", "oversized")
            return None
        return record

    def _segments(self) -> list[tuple[str, int, Path]]:
        try:
            names = list(self._root.iterdir())
        except OSError:  # absent or unavailable: nothing is retained here
            return []
        found = [(m.group(1), int(m.group(2)), p) for p in names if (m := _NAME.fullmatch(p.name))]
        return sorted(found)

    def _newest_retained(self) -> int:
        """The newest retained sequence: the last whole record of the newest segment holding one; 0 when none."""
        for _, _, path in reversed(self._segments()):
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

    def _roll(self, day: str, at: datetime) -> None:
        self._close_handle()
        self._root.mkdir(parents=True, exist_ok=True)
        existing = [index for d, index, _ in self._segments() if d == day]
        path = self._root / f"gateway-diagnostics-{day}-{(max(existing) + 1 if existing else 1):06d}.log"
        self._handle = open(path, "xb")  # never reopen an existing segment
        self._active, self._day, self._size = path, day, 0
        self._make_room(0, at)  # expiry on every roll; this also recounts the retained total

    def _make_room(self, incoming: int, at: datetime) -> bool:
        """Remove expired closed segments, then the oldest closed ones until ``incoming`` fits the cap; never the
        active segment. A segment that cannot be removed stays counted."""
        cutoff = (at - self._retain).strftime("%Y%m%d")
        retained: list[tuple[str, Path, int]] = []
        for day, _, path in self._segments():
            try:
                retained.append((day, path, path.stat().st_size))
            except FileNotFoundError:
                continue
        total = sum(size for _, _, size in retained)
        for day, path, size in retained:
            if path == self._active or (day >= cutoff and total + incoming <= self._cap):
                continue
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                self._failed("deletion_failures", f"delete:{type(exc).__name__}")
                continue
            total -= size
        self._total = total
        return total + incoming <= self._cap

    def _close_handle(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except OSError as exc:
                self._failed("write_failures", f"close:{type(exc).__name__}")

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
        """Stop admitting, then wait up to ``timeout`` for the thread to write what was queued and close its segment.
        False when the writer is still blocked; it then finishes on its own."""
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
