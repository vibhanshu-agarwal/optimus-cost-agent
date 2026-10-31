"""Plan 12.8: the per-user Gateway diagnostic copy. Real files under a temporary root: size and UTC-day rollover at their
exact boundaries, 30-day and total-cap retention, restart continuity, refused lines leaving sequence gaps, unavailable
storage, a blocked writer, a failed deletion, two Gateway processes sharing the directory, and stderr and the copy
failing independently of each other."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus_gateway import diagnostic_segments as ds
from optimus_gateway import request_diagnostics, usage_capture
from optimus_gateway.diagnostic_segments import DiagnosticSegments
from optimus_gateway.responses import model_request_log_line

_DAY = datetime(2026, 10, 31, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def small_records(monkeypatch):
    monkeypatch.setattr(ds, "MAX_RECORD_BYTES", 160)  # lets a test use segments of a few records


class Clock:
    def __init__(self, at: datetime = _DAY) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at


def _line(n: int = 0, **extra: Any) -> str:
    return json.dumps({"event": "model_request", "n": n, **extra})


def _sink(root: Path, clock: Clock | None = None, **kwargs: Any) -> DiagnosticSegments:
    kwargs.setdefault("segment_bytes", 1000)
    kwargs.setdefault("cap_bytes", 10_000)
    return DiagnosticSegments(root, clock=clock or Clock(), **kwargs)


def _segments(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if ds._NAME.fullmatch(p.name))


def _records(root: Path) -> dict[str, list[dict[str, Any]]]:
    return {p.name: [json.loads(line) for line in p.read_bytes().splitlines()] for p in _segments(root)}


def _record_size(tmp_path: Path) -> int:
    probe = _sink(tmp_path / "probe")
    probe.write(_line())
    assert probe.close()
    return probe.status().retained_bytes


def test_nothing_is_created_before_the_first_line(tmp_path):
    sink = _sink(tmp_path / "copy")
    assert sink.close() and not (tmp_path / "copy").exists()


def test_a_segment_rolls_before_it_would_exceed_its_size_and_may_end_exactly_at_it(tmp_path):
    size = _record_size(tmp_path)
    root = tmp_path / "copy"
    sink = _sink(root, segment_bytes=3 * size)
    for n in range(7):
        sink.write(_line(n))
    assert sink.close()

    segments = _records(root)
    assert [len(records) for records in segments.values()] == [3, 3, 1]
    assert [p.stat().st_size for p in _segments(root)] == [3 * size, 3 * size, size]
    assert [r["seq"] for records in segments.values() for r in records] == list(range(1, 8))


def test_the_utc_day_change_rolls_the_segment(tmp_path):
    clock = Clock(datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=UTC))
    root = tmp_path / "copy"
    sink = _sink(root, clock)
    sink.write(_line(1))
    while sink.status().written < 1:
        time.sleep(0.005)
    clock.at += timedelta(microseconds=1)
    sink.write(_line(2))
    assert sink.close()

    segments = _records(root)
    assert list(segments) == ["gateway-diagnostics-20261031-000001.log", "gateway-diagnostics-20261101-000001.log"]
    assert segments["gateway-diagnostics-20261101-000001.log"][0]["at"] == "2026-11-01T00:00:00+00:00"


@pytest.mark.parametrize(("age_days", "kept"), [(30, True), (31, False)])
def test_closed_segments_are_retained_for_thirty_days(tmp_path, age_days, kept):
    root = tmp_path / "copy"
    clock = Clock(_DAY - timedelta(days=age_days))
    old = _sink(root, clock)
    old.write(_line(1))
    assert old.close()
    clock.at = _DAY
    new = _sink(root, clock)
    new.write(_line(2))
    assert new.close()

    names = list(_records(root))
    assert (f"gateway-diagnostics-{(_DAY - timedelta(days=age_days)):%Y%m%d}-000001.log" in names) is kept
    assert f"gateway-diagnostics-{_DAY:%Y%m%d}-000001.log" in names


def test_the_total_cap_removes_the_oldest_closed_segments_and_never_the_active_one(tmp_path):
    size = _record_size(tmp_path)  # every record below has this size: one-digit sequences and values
    root = tmp_path / "copy"
    sink = _sink(root, segment_bytes=2 * size, cap_bytes=3 * size)
    for n in range(5):
        sink.write(_line(n))
    assert sink.close()
    assert [r["seq"] for records in _records(root).values() for r in records] == [3, 4, 5], "exactly at the cap, all is kept"
    sink = _sink(root, segment_bytes=2 * size, cap_bytes=3 * size)
    sink.write(_line(5))
    assert sink.close()

    status = sink.status()
    # The sixth line (from a restarted Gateway, appended to the active segment) would make 4 records within a 3-record
    # cap: the oldest closed segment (3, 4) goes, never the active one, even though it leaves room to spare.
    assert status.retained_bytes == 2 * size and status.written == 1 and status.refused_no_space == 0
    assert [r["seq"] for records in _records(root).values() for r in records] == [5, 6], "oldest first"
    assert status.first == (f"{_DAY:%Y%m%d}", 5) and status.last == (f"{_DAY:%Y%m%d}", 6)


def test_a_restart_continues_the_sequence_in_a_new_segment_after_a_torn_tail(tmp_path):
    root = tmp_path / "copy"
    first = _sink(root)
    for n in range(3):
        first.write(_line(n))
    assert first.close()
    (segment,) = _segments(root)
    with open(segment, "ab") as handle:
        handle.write(b'{"seq":99,"at"')  # a crash mid-line

    second = _sink(root)
    second.write(_line(3))
    assert second.close()

    segments = _records_tolerant(root)
    assert segments[segment.name][:3] == [1, 2, 3], "a segment ending in a torn line is never appended to"
    assert segments["gateway-diagnostics-20261031-000002.log"] == [4]


def test_a_restart_appends_to_the_days_newest_whole_segment(tmp_path):
    root = tmp_path / "copy"
    for n in range(2):
        sink = _sink(root)
        sink.write(_line(n))
        assert sink.close()
    assert [[r["seq"] for r in records] for records in _records(root).values()] == [[1, 2]]


def _records_tolerant(root: Path) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in _segments(root):
        found[path.name] = []
        for line in path.read_bytes().splitlines():
            try:
                found[path.name].append(json.loads(line)["seq"])
            except ValueError:
                continue
    return found


def test_refused_lines_are_counted_leave_sequence_gaps_and_copied_lines_are_sanitized_again(tmp_path):
    root = tmp_path / "copy"
    sink = _sink(root)
    sink.write("not json")
    sink.write(json.dumps(["model_request"]))
    sink.write(json.dumps({"event": "provider_reply", "text": "unlisted"}))
    sink.write(_line(1, padding="x" * 500))
    sink.write(_line(2, refusal="Bearer gateway-diagnostics-canary"))  # synthetic credential
    assert sink.close()

    status = sink.status()
    assert (status.refused_malformed, status.refused_oversized, status.written) == (3, 1, 1)
    (records,) = _records(root).values()
    assert [r["seq"] for r in records] == [5]
    assert "gateway-diagnostics-canary" not in json.dumps(records)


def test_unavailable_storage_is_counted_reported_once_and_recovers(tmp_path):
    root = tmp_path / "copy"
    root.write_bytes(b"not a directory")
    reports: list[str] = []
    sink = _sink(root, report=reports.append)
    sink.write(_line(1))
    sink.write(_line(2))
    while sink.status().write_failures < 2:
        time.sleep(0.005)
    root.unlink()
    sink.write(_line(3))
    assert sink.close()

    status = sink.status()
    assert (status.write_failures, status.written) == (2, 1)
    assert len(reports) == 1 and "write failures" in reports[0]
    assert [r["seq"] for records in _records(root).values() for r in records] == [3]


def test_a_blocked_writer_never_blocks_the_caller_and_drops_are_counted(tmp_path, monkeypatch):
    release, entered = threading.Event(), threading.Event()
    real_open = open
    opened: list[Any] = []

    def blocking_open(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        release.wait(30)
        opened.append(real_open(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(ds, "open", blocking_open, raising=False)
    sink = _sink(tmp_path / "copy", queue_lines=2)
    started = time.monotonic()
    sink.write(_line(0))
    assert entered.wait(5), "the writer holds the first line, blocked"
    for n in range(1, 50):
        sink.write(_line(n))  # two queue, the rest are dropped: the queue is full when close() offers its stop item
    elapsed = time.monotonic() - started

    try:
        assert elapsed < 1.0
        assert sink.close(timeout=0.2) is False, "a blocked writer is reported, never waited on past the bound"
    finally:
        release.set()
    deadline = time.monotonic() + 10
    while (status := sink.status()).written + status.dropped_queue_full < 50 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert status.written + status.dropped_queue_full == 50, "every offered line is written or counted"
    assert (status.written, status.dropped_queue_full) == (3, 47), "one in the writer and two queued"
    # Codex Checkpoint C finding 4: the stop item never fit the full queue, yet the writer ends once it is drained.
    assert sink._thread is not None
    sink._thread.join(10)
    assert not sink._thread.is_alive(), "the writer ended after close although its stop item was refused"
    assert opened and all(handle.closed for handle in opened), "no segment or lock handle is left open"


def test_a_failed_deletion_is_counted_and_the_line_is_refused_rather_than_truncating(tmp_path, monkeypatch):
    size = _record_size(tmp_path)
    root = tmp_path / "copy"
    reports: list[str] = []
    real_unlink = Path.unlink

    def stuck_unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.parent == root and self.name.endswith("-000001.log"):  # only the oldest; the active one could go
            raise PermissionError("held open elsewhere")
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", stuck_unlink)
    sink = _sink(root, segment_bytes=2 * size, cap_bytes=3 * size, report=reports.append)
    for n in range(5):
        sink.write(_line(n))
    assert sink.close()

    status = sink.status()
    assert status.written == 3 and status.refused_no_space == 2 and status.deletion_failures >= 1
    assert status.retained_bytes == 3 * size, "the cap holds; nothing was truncated"
    assert any("deletion failures" in r for r in reports) and any("refused no space" in r for r in reports)


_GATEWAY_COPY = """
import json, sys
from datetime import UTC, datetime
from pathlib import Path
from optimus_gateway import diagnostic_segments as ds

root, start, lines, segment_bytes, cap_bytes = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
ds.MAX_RECORD_BYTES = 160
sink = ds.DiagnosticSegments(root, segment_bytes=segment_bytes, cap_bytes=cap_bytes, queue_lines=lines + 1,
                             clock=lambda: datetime(2026, 10, 31, 12, tzinfo=UTC))
while not start.exists():
    pass
for n in range(lines):
    sink.write(json.dumps({"event": "model_request", "n": n}))
assert sink.close(60)
status = sink.status()
print(json.dumps({"written": status.written, "refused": status.refused_no_space, "failures": status.write_failures}))
"""


@pytest.mark.parametrize("capped", [False, True])
def test_two_gateway_processes_share_one_sequence_rollover_and_cap(tmp_path, capped):
    """Codex Checkpoint C finding 1: two Gateways of the same user write the same directory at once. Every line lands
    whole, in one strictly increasing sequence; no segment exceeds its size; under a tight cap the total never exceeds
    it and nothing is refused, because each Gateway sees the other's segments when it makes room."""
    size = _record_size(tmp_path) + 2  # two-digit offers and up to three-digit sequences
    root, start, lines = tmp_path / "copy", tmp_path / "start", 60
    segment_bytes, cap_bytes = 4 * size, (12 * size if capped else 1000 * size)
    children = [subprocess.Popen([sys.executable, "-c", _GATEWAY_COPY, str(root), str(start), str(lines), str(segment_bytes), str(cap_bytes)],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    start.write_bytes(b"")
    reports = []
    for child in children:
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0, err
        reports.append(json.loads(out))

    assert all(report == {"written": lines, "refused": 0, "failures": 0} for report in reports)
    sequences = [r["seq"] for records in _records(root).values() for r in records]
    assert sequences == sorted(set(sequences)), "one strictly increasing sequence across both Gateways"
    assert all(p.stat().st_size <= segment_bytes for p in _segments(root))
    retained = sum(p.stat().st_size for p in _segments(root))
    if capped:
        assert retained <= cap_bytes and sequences[-1] == 2 * lines
    else:
        assert sequences == list(range(1, 2 * lines + 1)), "nothing lost or duplicated"


class _BrokenStream:
    def write(self, _text: str) -> int:
        raise OSError("stderr closed")

    def flush(self) -> None:
        raise OSError("stderr closed")


def test_stderr_and_the_copy_fail_independently(tmp_path, monkeypatch, capsys):
    root = tmp_path / "copy"
    sink = _sink(root)
    request_diagnostics.configure_copy(sink)
    try:
        before = request_diagnostics.stderr_failures()
        with monkeypatch.context() as patched:
            patched.setattr(sys, "stderr", _BrokenStream())
            request_diagnostics.write_log_line(_line(1))
        assert request_diagnostics.stderr_failures() == before + 1

        broken = tmp_path / "blocked"
        broken.write_bytes(b"")
        request_diagnostics.configure_copy(_sink(broken))  # its storage is unavailable
        request_diagnostics.write_log_line(_line(2))
    finally:
        request_diagnostics.configure_copy(None)
    assert sink.close()

    assert capsys.readouterr().err == _line(2) + "\n", "stderr is written exactly as before"
    assert [r["record"]["n"] for records in _records(root).values() for r in records] == [1]


def test_the_gateway_producers_are_copied(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "MAX_RECORD_BYTES", 64 * 1024)
    root = tmp_path / "copy"
    sink = _sink(root, segment_bytes=100_000, cap_bytes=1_000_000)
    request_diagnostics.configure_copy(sink)
    try:
        request_diagnostics.write_log_line(model_request_log_line("/v1/responses", 200, {"status": "completed"}))
        request_diagnostics.log_model_attempt(SimpleNamespace(attempt=1, classification="transient", disposition="retry", failure=None))
        request_diagnostics.write_log_line(json.dumps({"event": "reply_undeliverable", "path": "/v1/responses", "status": 200}))
    finally:
        request_diagnostics.configure_copy(None)
    assert sink.close()

    status = sink.status()
    assert status.written == 3 and status.refused_malformed == 0


def test_gateway_accounting_owns_the_copy_under_its_root_and_closes_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ds, "MAX_RECORD_BYTES", 64 * 1024)
    root = tmp_path / "accounting"
    accounting = usage_capture.start_accounting(root, None, keyring_backend=None, log=lambda _line: None)
    try:
        request_diagnostics.write_log_line(_line(1))
    finally:
        accounting.stop()

    assert request_diagnostics._copy is None
    (records,) = _records(root / "gateway-diagnostics").values()
    assert [r["record"] for r in records] == [json.loads(_line(1))]
    final = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert final["event"] == "diagnostic_copy_status" and final["closed"] is True and final["written"] == 1
    assert "stderr_failures" in final


def test_the_gateway_copy_aimed_at_the_real_config_root_is_refused_and_creates_nothing(monkeypatch):
    """The accounting-root control with the Gateway composition wired: in the guarded pytest process, the diagnostic
    copy and the Gateway outbox under the real per-user root are refused, the log line still reaches stderr and the
    refusal is counted and reported."""
    from tools.testing import run_context_guard

    if run_context_guard.mode() != "pytest_process_guard":
        pytest.skip("the pytest-process guard is not installed in this run")
    monkeypatch.setattr(ds, "MAX_RECORD_BYTES", 64 * 1024)
    config_root = next((Path(root) for root in run_context_guard.protected_roots() if root.endswith("\\roaming\\optimus-cost-agent")), None)
    if config_root is None:
        pytest.skip("this platform's guard protects no Windows per-user config root")
    accounting = config_root / "accounting"
    existed = (accounting / "gateway-diagnostics").exists()
    before = run_context_guard.denials()
    reports: list[str] = []
    started = usage_capture.start_accounting(accounting, None, keyring_backend=None, log=reports.append)
    try:
        request_diagnostics.write_log_line(_line(1))
        assert started.diagnostics is not None
        assert started.diagnostics.close()
        status = started.diagnostics.status()
    finally:
        started.stop()

    assert status.written == 0 and status.write_failures == 1
    assert run_context_guard.denials() > before, "the guard refused the write"
    assert (accounting / "gateway-diagnostics").exists() == existed
    assert any("write failures" in r for r in reports)
