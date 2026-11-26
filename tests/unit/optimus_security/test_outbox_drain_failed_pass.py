"""#652: a background drain pass that raises leaves a readable health record (that it failed, a bounded value-free cause,
and that the next good pass recovered), keeps every pending record, and keeps the retry cadence. Real outbox under a
temporary root, real background thread."""

from __future__ import annotations

import threading
from pathlib import Path

from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security.outbox_drain import OutboxDrain

_LEDGER = "1" * 32
_VALUE = "synthetic-" + "v" * 12  # stands in for a value an exception message might carry


def test_a_failed_background_pass_is_reported_then_recovers_without_dropping_a_record(tmp_path: Path) -> None:
    writer = ob.OutboxWriter(tmp_path / "outbox" / "host")
    assert writer.submit({"kind": "probe", "at": "2026-11-27T00:00:00+00:00"}).wait(5)
    calls: list[int] = []
    failed, delivered = threading.Event(), threading.Event()
    logs: list[str] = []
    seen: list[object] = []

    def send(stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[ob.Record]) -> uc.CaptureAck:
        calls.append(len(batch))
        if len(calls) == 1:
            raise RuntimeError(_VALUE)  # not a DrainStop: the whole pass raises
        last = batch[-1]
        return uc.CaptureAck(_LEDGER, stream_id, last.sequence, last.digest)

    def warn(line: str) -> None:
        logs.append(line)
        seen.append(drain.last_report)
        (failed if len(logs) == 1 else delivered).set()

    drain = OutboxDrain(writer, send, pass_seconds=60.0, warn=warn)
    drain.start()
    try:
        assert failed.wait(5)
        after_failure = seen[0]
        assert ob.read_ack(writer.directory) is None  # nothing acknowledged, nothing compacted
        assert [r.sequence for r in ob.scan_stream(writer.directory).records] == [1]
        drain.nudge()  # the retry is the ordinary next pass
        assert delivered.wait(5)
    finally:
        drain.stop()
        writer.close()

    assert after_failure.pass_failure == "pass_failed:RuntimeError"
    assert after_failure.failures == ["pass_failed:RuntimeError"]
    assert after_failure.backlog.last_failure == "pass_failed:RuntimeError"
    recovered = drain.last_report
    assert recovered.pass_failure is None and recovered.failures == [] and recovered.committed == 1
    ack = ob.read_ack(writer.directory)
    assert ack is not None and ack.sequence == 1
    assert calls == [1, 1]
    assert len(logs) == 2 and "pass failed" in logs[0] and "recovered" in logs[1]
    assert all(_VALUE not in line for line in logs)
    assert _VALUE not in repr(after_failure) and _VALUE not in repr(recovered)


def test_a_failing_pass_waits_the_ordinary_cadence_and_warns_once_per_streak(tmp_path: Path) -> None:
    writer = ob.OutboxWriter(tmp_path / "outbox" / "host")
    assert writer.submit({"kind": "probe"}).wait(5)
    third = threading.Event()
    calls: list[int] = []
    logs: list[str] = []

    def send(stream_id: str, ledger: str | None, after: tuple[int, str], batch: list[ob.Record]) -> uc.CaptureAck:
        calls.append(1)
        if len(calls) == 3:
            third.set()
        raise (OSError if len(calls) % 2 else PermissionError)(_VALUE)  # a cause that changes within one streak

    drain = OutboxDrain(writer, send, pass_seconds=0.05, warn=logs.append)
    drain.start()
    try:
        assert third.wait(5)
    finally:
        drain.stop()
        writer.close()

    assert len(calls) >= 3  # the loop kept running after each failed pass
    assert len(logs) == 1 and _VALUE not in logs[0]
    assert drain.last_report.pass_failure in {"pass_failed:OSError", "pass_failed:PermissionError"}
    assert ob.read_ack(writer.directory) is None
