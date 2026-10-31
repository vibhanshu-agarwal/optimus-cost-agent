"""Plan 12.8 Task 1: the fsynced append-only outbox, on the real filesystem and a real killed writer process."""

from __future__ import annotations

import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from optimus_security import durable_outbox as ob

_LEDGER = "a" * 32


def _writer(tmp_path: Path, **kwargs) -> ob.StreamWriter:
    return ob.StreamWriter(tmp_path / "outbox", **kwargs)


def _fail_next_fsync(monkeypatch, count: int = 1) -> dict:
    real = ob.os.fsync
    state = {"left": count, "calls": 0}

    def fsync(fd):
        if state["left"] and stat.S_ISREG(ob.os.fstat(fd).st_mode):  # record writes, never POSIX directory syncs
            state["left"] -= 1
            state["calls"] += 1
            raise OSError(5, "simulated")
        return real(fd)

    monkeypatch.setattr(ob.os, "fsync", fsync)
    return state


def test_records_round_trip_in_order_with_a_digest_chain(tmp_path):
    writer = _writer(tmp_path)
    written = [writer.append({"kind": "k", "n": n}) for n in range(5)]
    writer.close()

    scan = ob.scan_stream(writer.directory)

    assert [r.sequence for r in scan.records] == [1, 2, 3, 4, 5]
    assert [r.payload["n"] for r in scan.records] == [0, 1, 2, 3, 4]
    assert scan.records[0].prev == ob.GENESIS
    assert all(later.prev == earlier.digest for earlier, later in zip(scan.records, scan.records[1:], strict=False))
    assert [r.digest for r in scan.records] == [r.digest for r in written]
    assert scan.damage == () and scan.unverified_tail is None


def test_nothing_touches_the_filesystem_until_the_first_record(tmp_path):
    ob.StreamWriter(tmp_path / "outbox")
    writer = ob.OutboxWriter(tmp_path / "outbox")

    assert not (tmp_path / "outbox").exists()
    assert writer.close()
    assert not (tmp_path / "outbox").exists()


def test_segments_roll_at_the_size_boundary_and_the_stream_spans_them(tmp_path):
    writer = _writer(tmp_path, segment_bytes=400)
    for n in range(10):
        writer.append({"kind": "k", "pad": "x" * 100, "n": n})
    writer.close()

    scan = ob.scan_stream(writer.directory)

    assert len(scan.segments) > 2
    assert [r.sequence for r in scan.records] == list(range(1, 11))
    assert all((writer.directory / s.name).stat().st_size <= 400 for s in scan.segments)


def test_a_record_over_the_limit_is_refused_without_consuming_a_sequence(tmp_path):
    writer = _writer(tmp_path)
    writer.append({"kind": "k"})
    with pytest.raises(ob.OutboxError) as refused:
        writer.append({"kind": "k", "pad": "x" * ob.MAX_RECORD_BYTES})
    writer.append({"kind": "k"})
    writer.close()

    assert refused.value.code == "TOO_LARGE"
    assert [r.sequence for r in ob.scan_stream(writer.directory).records] == [1, 2]


def test_a_frame_with_an_extra_field_does_not_verify(tmp_path):
    record = ob.frame("b" * 32, 1, ob.GENESIS, {"kind": "k"})
    body = record.line[65:-1].replace(b'"schema":1', b'"schema":1,"x":1')
    forged = ob.hashlib.sha256(body).hexdigest().encode() + b" " + body + b"\n"

    with pytest.raises(ValueError, match="malformed"):
        ob.parse_line(forged)


@pytest.mark.parametrize(("damage", "reason"), [("torn", "torn"), ("flip", "checksum")])
def test_a_damaged_tail_yields_its_verified_prefix(tmp_path, damage, reason):
    writer = _writer(tmp_path)
    for n in range(3):
        writer.append({"kind": "k", "n": n})
    writer.close()
    segment = writer.directory / "seg-000001.log"
    data = segment.read_bytes()
    segment.write_bytes(data[:-5] if damage == "torn" else data[:-10] + b"Z" + data[-9:])

    scan = ob.scan_stream(writer.directory)

    assert [r.sequence for r in scan.records] == [1, 2]
    assert [(d.segment, d.reason) for d in scan.damage] == [("seg-000001.log", reason)]


def test_a_failed_fsync_retracts_the_record_through_a_gap_in_a_successor_segment(tmp_path, monkeypatch):
    writer = _writer(tmp_path)
    writer.append({"kind": "k", "n": 1})
    state = _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError) as failed:
        writer.append({"kind": "k", "n": 2})  # its bytes land in the segment, but it is never confirmed
    writer.append({"kind": "k", "n": 3})
    writer.close()

    scan = ob.scan_stream(writer.directory)

    assert failed.value.code == "WRITE_FAILED" and state["calls"] == 1
    assert b'"n":2' in (writer.directory / "seg-000001.log").read_bytes(), "the unconfirmed bytes are preserved"
    assert [(r.sequence, r.payload.get("kind"), r.payload.get("n")) for r in scan.records] == [
        (1, "k", 1),
        (3, ob.GAP_KIND, None),
        (4, "k", 3),
    ]
    assert scan.records[1].payload["unconfirmed_from"] == 2 and scan.records[1].payload["unconfirmed_to"] == 2
    assert scan.damage == ()


def test_an_orphans_last_record_is_withheld_unless_it_is_the_orderly_end(tmp_path, monkeypatch):
    dead = _writer(tmp_path)
    dead.append({"kind": "k", "n": 1})
    _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError):
        dead.append({"kind": "epoch.close"})  # lands, fsync fails, and the process "dies" before any gap
    dead._lock_handle.close()  # type: ignore[union-attr]
    orderly = _writer(tmp_path)
    orderly.append({"kind": "k"})
    orderly.append({"kind": ob.STREAM_END_KIND})
    orderly.close()

    dead_scan = ob.scan_stream(dead.directory, orphan=True)
    orderly_scan = ob.scan_stream(orderly.directory, orphan=True)

    assert [r.payload["kind"] for r in dead_scan.records] == ["k"]
    assert dead_scan.unverified_tail is not None and dead_scan.unverified_tail.payload["kind"] == "epoch.close"
    assert [r.payload["kind"] for r in orderly_scan.records] == ["k", ob.STREAM_END_KIND]
    assert orderly_scan.unverified_tail is None


def test_an_orphans_withheld_gap_still_retracts_what_it_names(tmp_path, monkeypatch):
    dead = _writer(tmp_path)
    dead.append({"kind": "k", "n": 1})
    _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError):
        dead.append({"kind": "k", "n": 2})
    _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError):
        dead.append({"kind": "k", "n": 3})  # the gap retracting 2 lands, but its own fsync fails; then death
    dead._lock_handle.close()  # type: ignore[union-attr]

    scan = ob.scan_stream(dead.directory, orphan=True)

    assert [r.payload.get("n") for r in scan.records] == [1]
    assert scan.unverified_tail is not None and scan.unverified_tail.payload["kind"] == ob.GAP_KIND


def test_an_orphan_whose_gap_segment_never_opened_still_withholds_the_unconfirmed_record(tmp_path, monkeypatch):
    dead = _writer(tmp_path)
    dead.append({"kind": "k", "n": 1})
    _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError):
        dead.append({"kind": "k", "n": 2})

    def no_directory_sync(directory):
        raise OSError(5, "simulated")

    monkeypatch.setattr(ob, "_fsync_directory", no_directory_sync)
    with pytest.raises(ob.OutboxError):
        dead.append({"kind": "k", "n": 3})  # the gap's successor segment cannot be made durable; then death
    dead._lock_handle.close()  # type: ignore[union-attr]

    scan = ob.scan_stream(dead.directory, orphan=True)

    assert [r.payload.get("n") for r in scan.records] == [1]
    assert scan.unverified_tail is not None and scan.unverified_tail.payload.get("n") == 2


def test_a_missing_segment_ends_the_stream_at_the_discontinuity(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(8):
        writer.append({"kind": "k", "pad": "y" * 60, "n": n})
    writer.close()
    names = [segment.name for segment in ob.scan_stream(writer.directory).segments]
    (writer.directory / names[1]).unlink()

    scan = ob.scan_stream(writer.directory)

    assert scan.records[-1].sequence == scan.segments[0].last_sequence
    assert scan.damage[-1].reason == "sequence"


def test_an_invalid_gap_leaves_the_verified_prefix_intact(tmp_path):
    writer = _writer(tmp_path)
    good = [writer.append({"kind": "k", "n": n}) for n in range(3)]
    writer.close()
    forged = ob.frame(writer.stream_id, 4, "1" * 64, {"kind": ob.GAP_KIND, "unconfirmed_from": 2, "unconfirmed_to": 3})
    (writer.directory / "seg-000002.log").write_bytes(forged.line)

    scan = ob.scan_stream(writer.directory)

    assert [r.digest for r in scan.records] == [r.digest for r in good]
    assert scan.damage[-1].reason == "chain"


def test_a_live_writer_holds_its_stream_and_a_closed_one_can_be_claimed(tmp_path):
    writer = _writer(tmp_path)
    writer.append({"kind": "k"})

    assert ob.claim(writer.directory) is None
    writer.close()
    handle = ob.claim(writer.directory)
    assert handle is not None
    ob.release(handle)


def test_open_is_retryable_after_a_failed_directory_sync(tmp_path, monkeypatch):
    writer = _writer(tmp_path)
    real = ob._fsync_directory
    calls = {"n": 0}

    def flaky(directory):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError(5, "simulated")
        return real(directory)

    monkeypatch.setattr(ob, "_fsync_directory", flaky)
    with pytest.raises(ob.OutboxError):
        writer.append({"kind": "k", "n": 1})  # the directory now exists, unsynced and unlocked
    writer.append({"kind": "k", "n": 2})
    writer.close()

    assert [r.payload["n"] for r in ob.scan_stream(writer.directory).records] == [2]


def test_acknowledgements_bind_to_a_held_record_and_only_advance(tmp_path):
    writer = _writer(tmp_path)
    first, second = writer.append({"kind": "k"}), writer.append({"kind": "k"})
    writer.close()
    scan = ob.scan_stream(writer.directory)

    assert ob.read_ack(writer.directory) is None
    assert ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=2, digest=second.digest)
    assert not ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=1, digest=first.digest)
    for bad in ({"sequence": 3, "digest": second.digest}, {"sequence": 2, "digest": first.digest}):
        with pytest.raises(ob.OutboxError) as refused:
            ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, **bad)
        assert refused.value.code == "INVALID"
    with open(writer.directory / "ack.log", "ab") as handle:
        handle.write(b"0" * 64 + b' {"torn":')

    assert ob.read_ack(writer.directory) == ob.Ack(_LEDGER, writer.stream_id, 2, second.digest)


def test_compaction_needs_a_stored_acknowledgement_from_the_expected_ledger(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(8):
        writer.append({"kind": "k", "pad": "z" * 60, "n": n})
    scan = ob.scan_stream(writer.directory)
    active = scan.segments[-1].name
    boundary = next(r for r in scan.records if r.sequence == scan.segments[1].last_sequence)

    assert ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=active) == [], "no acknowledgement"
    ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=boundary.sequence, digest=boundary.digest)
    assert ob.compact(writer.directory, scan, ledger_instance="c" * 32, active_segment=active) == [], "another ledger"

    deleted = ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=active)
    rescan = ob.scan_stream(writer.directory)

    assert deleted == [scan.segments[0].name, scan.segments[1].name]
    assert rescan.records[0].sequence == boundary.sequence + 1 and rescan.damage == (), "a compacted stream still verifies"
    last = rescan.records[-1]
    ob.write_ack(writer.directory, rescan, ledger_instance=_LEDGER, sequence=last.sequence, digest=last.digest)
    remaining = ob.compact(writer.directory, ob.scan_stream(writer.directory), ledger_instance=_LEDGER, active_segment=active)
    assert remaining == [s.name for s in scan.segments[2:-1]] and (writer.directory / active).exists()
    writer.close()


def test_a_compacted_stream_keeps_a_gap_that_retracts_a_compacted_record(tmp_path, monkeypatch):
    writer = _writer(tmp_path)
    confirmed = writer.append({"kind": "k", "n": 1})
    _fail_next_fsync(monkeypatch)
    with pytest.raises(ob.OutboxError):
        writer.append({"kind": "k", "n": 2})
    writer.append({"kind": "k", "n": 3})  # opens seg-000002 with the gap retracting 2
    writer.close()
    scan = ob.scan_stream(writer.directory)
    ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=1, digest=confirmed.digest)

    deleted = ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=None)
    rescan = ob.scan_stream(writer.directory)

    assert deleted == ["seg-000001.log"]
    assert [(r.payload.get("kind"), r.payload.get("n")) for r in rescan.records] == [(ob.GAP_KIND, None), ("k", 3)]
    assert rescan.damage == ()


def test_an_anchor_that_contradicts_the_stream_yields_nothing(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(6):
        writer.append({"kind": "k", "pad": "q" * 60, "n": n})
    writer.close()
    scan = ob.scan_stream(writer.directory)
    target = scan.records[2]
    ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=target.sequence, digest=target.digest)
    ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=None)
    forged = ob.frame(writer.stream_id, 1, ob.GENESIS, {"ledger_instance": _LEDGER, "stream_id": writer.stream_id, "sequence": 9, "digest": "2" * 64})
    with open(writer.directory / "ack.log", "ab") as handle:
        handle.write(forged.line)

    rescan = ob.scan_stream(writer.directory)

    assert rescan.records == ()


def test_compaction_keeps_a_damaged_segment_and_an_orphans_tail(tmp_path):
    writer = _writer(tmp_path)
    records = [writer.append({"kind": "k", "n": n}) for n in range(3)]
    writer.close()
    scan = ob.scan_stream(writer.directory, orphan=True)
    ob.write_ack(writer.directory, scan, ledger_instance=_LEDGER, sequence=2, digest=records[1].digest)

    assert ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=None) == []
    segment = writer.directory / "seg-000001.log"
    segment.write_bytes(segment.read_bytes()[:-3])
    assert ob.compact(writer.directory, ob.scan_stream(writer.directory), ledger_instance=_LEDGER, active_segment=None) == []
    assert segment.exists()


def test_the_owned_writer_confirms_records_and_rejects_when_full_or_closed(tmp_path):
    writer = ob.OutboxWriter(tmp_path / "outbox", queue_records=1)
    assert writer.submit({"kind": "k"}).wait(5.0)

    gate, entered = threading.Event(), threading.Event()
    original = writer._writer.append

    def slow_append(payload, *, event_id=None):
        entered.set()
        gate.wait(5.0)
        return original(payload, event_id=event_id)

    writer._writer.append = slow_append  # type: ignore[method-assign]
    in_flight = writer.submit({"kind": "k"})
    assert entered.wait(5.0)
    queued = writer.submit({"kind": "k"})
    rejected = writer.submit({"kind": "k"})

    assert not in_flight.wait(0.05), "a record that is not yet durable is not confirmed"
    assert rejected.failure == "QUEUE_FULL", "a full queue rejects immediately rather than blocking"
    gate.set()
    assert in_flight.wait(5.0) and queued.wait(5.0)
    assert writer.close()
    assert writer.submit({"kind": "k"}).failure == "CLOSED"
    assert writer.stats().rejected_full == 1


def test_a_timed_out_close_still_writes_what_was_admitted_and_releases_the_stream(tmp_path):
    writer = ob.OutboxWriter(tmp_path / "outbox", queue_records=2)
    assert writer.submit({"kind": "k"}).wait(5.0)
    gate, entered = threading.Event(), threading.Event()
    original = writer._writer.append

    def slow_append(payload, *, event_id=None):
        entered.set()
        gate.wait(5.0)
        return original(payload, event_id=event_id)

    writer._writer.append = slow_append  # type: ignore[method-assign]
    blocked = writer.submit({"kind": "k"})
    assert entered.wait(5.0)
    admitted = [writer.submit({"kind": "k"}), writer.submit({"kind": "k"})]

    assert writer.close(timeout=0.05) is False, "close stopped waiting; the thread still owns the stream"
    assert writer.submit({"kind": "k"}).failure == "CLOSED", "nothing is admitted after close begins"
    gate.set()
    assert blocked.wait(5.0) and all(ticket.wait(5.0) for ticket in admitted)
    writer._thread.join(5.0)  # type: ignore[union-attr]
    handle = ob.claim(writer.directory)
    assert handle is not None, "the thread released the stream on its own"
    ob.release(handle)
    assert len(ob.scan_stream(writer.directory).records) == 4


def test_a_killed_writer_leaves_a_claimable_stream_with_its_verified_prefix(tmp_path):
    root = tmp_path / "outbox"
    script = (
        "import os, sys; from pathlib import Path\n"
        "from optimus_security import durable_outbox as ob\n"
        "w = ob.StreamWriter(Path(sys.argv[1]))\n"
        "for n in range(3): w.append({'kind': 'k', 'n': n})\n"
        "w._segment.write(b'0123456789abcdef partial'); w._segment.flush()\n"
        "os._exit(7)  # dies holding the lock, mid-record, without closing\n"
    )
    killed = subprocess.run([sys.executable, "-c", script, str(root)], timeout=120)
    (stream,) = list(ob.stream_dirs(root))

    handle = ob.claim(stream)
    scan = ob.scan_stream(stream, orphan=True)

    assert killed.returncode == 7
    assert handle is not None, "the dead writer's lock is released with its process"
    ob.release(handle)
    assert [r.payload["n"] for r in scan.records] == [0, 1]
    assert scan.unverified_tail is not None and scan.unverified_tail.payload["n"] == 2
    assert [d.reason for d in scan.damage] == ["torn"]


def test_another_streams_scan_authorizes_no_acknowledgement_or_deletion(tmp_path):
    a, b = _writer(tmp_path, segment_bytes=200), _writer(tmp_path, segment_bytes=200)
    for writer in (a, b):
        for n in range(6):
            writer.append({"kind": "k", "pad": "w" * 60, "n": n})
        writer.close()
    scan_b = ob.scan_stream(b.directory)
    record_b = scan_b.records[3]
    before = {p.name: p.read_bytes() for p in a.directory.iterdir()}

    with pytest.raises(ob.OutboxError) as refused:
        ob.write_ack(a.directory, scan_b, ledger_instance=_LEDGER, sequence=record_b.sequence, digest=record_b.digest)
    forged = {"ledger_instance": _LEDGER, "stream_id": a.stream_id, "sequence": record_b.sequence, "digest": record_b.digest}
    (a.directory / "ack.log").write_bytes(ob.frame(a.stream_id, 1, ob.GENESIS, forged).line)  # labelled A, naming B's record

    assert refused.value.code == "INVALID"
    assert ob.read_ack(a.directory) is not None
    assert ob.compact(a.directory, scan_b, ledger_instance=_LEDGER, active_segment=None) == [], "B's scan authorizes nothing in A"
    assert ob.compact(a.directory, ob.scan_stream(a.directory), ledger_instance=_LEDGER, active_segment=None) == [], (
        "A's own scan holds no record with that digest"
    )
    assert {p.name: p.read_bytes() for p in a.directory.iterdir() if p.name != "ack.log"} == {
        k: v for k, v in before.items() if k != "ack.log"
    }


def test_an_acknowledged_last_record_of_an_orphan_is_kept_and_compaction_proceeds(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(5):
        writer.append({"kind": "k", "pad": "v" * 60, "n": n})
    close = writer.append({"kind": "epoch.close"})
    writer._abandon_segment()  # dies before stream.end: the process's handles go with it
    writer._lock_handle.close()  # type: ignore[union-attr]
    live = ob.scan_stream(writer.directory)
    ob.write_ack(writer.directory, live, ledger_instance=_LEDGER, sequence=close.sequence, digest=close.digest)

    scan = ob.scan_stream(writer.directory, orphan=True)
    deleted = ob.compact(writer.directory, scan, ledger_instance=_LEDGER, active_segment=None)

    assert scan.unverified_tail is None and scan.records[-1].digest == close.digest
    assert deleted == [s.name for s in scan.segments], "every segment is acknowledged and closed"
