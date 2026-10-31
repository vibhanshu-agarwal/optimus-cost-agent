"""Plan 12.8 Task 1: the fsynced append-only outbox, on the real filesystem and a real killed writer process."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from optimus_security import durable_outbox as ob


def _writer(tmp_path: Path, **kwargs) -> ob.StreamWriter:
    return ob.StreamWriter(tmp_path / "outbox", **kwargs)


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
    assert scan.damage == ()


def test_nothing_touches_the_filesystem_until_the_first_record(tmp_path):
    ob.StreamWriter(tmp_path / "outbox")
    writer = ob.OutboxWriter(tmp_path / "outbox")

    assert not (tmp_path / "outbox").exists()
    writer.close()
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
    real_fsync = ob.os.fsync
    calls = {"n": 0}

    def failing_fsync(fd):
        calls["n"] += 1
        raise OSError(5, "simulated")

    monkeypatch.setattr(ob.os, "fsync", failing_fsync)
    with pytest.raises(ob.OutboxError) as failed:
        writer.append({"kind": "k", "n": 2})  # its bytes land in the segment, but it is never confirmed
    monkeypatch.setattr(ob.os, "fsync", real_fsync)
    writer.append({"kind": "k", "n": 3})
    writer.close()

    scan = ob.scan_stream(writer.directory)

    assert failed.value.code == "WRITE_FAILED" and calls["n"] == 1
    assert b'"n":2' in (writer.directory / "seg-000001.log").read_bytes(), "the unconfirmed bytes are preserved"
    assert [(r.sequence, r.payload.get("kind"), r.payload.get("n")) for r in scan.records] == [
        (1, "k", 1),
        (3, ob.GAP_KIND, None),
        (4, "k", 3),
    ]
    assert scan.records[1].payload["unconfirmed_from"] == 2 and scan.records[1].payload["unconfirmed_to"] == 2
    assert scan.damage == ()


def test_a_missing_segment_ends_the_stream_at_the_discontinuity(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(8):
        writer.append({"kind": "k", "pad": "y" * 60, "n": n})
    writer.close()
    names = [segment.name for segment in ob.scan_stream(writer.directory).segments]
    (writer.directory / names[1]).unlink()

    scan = ob.scan_stream(writer.directory)

    first_segment_last = scan.segments[0].last_sequence
    assert scan.records[-1].sequence == first_segment_last
    assert scan.damage[-1].reason == "sequence"


def test_a_live_writer_holds_its_stream_and_a_closed_one_can_be_claimed(tmp_path):
    writer = _writer(tmp_path)
    writer.append({"kind": "k"})

    assert ob.claim(writer.directory) is None
    writer.close()
    handle = ob.claim(writer.directory)
    assert handle is not None
    ob.release(handle)


def test_the_last_verified_acknowledgement_wins_and_a_torn_one_is_ignored(tmp_path):
    writer = _writer(tmp_path)
    writer.append({"kind": "k"})
    writer.close()

    assert ob.read_ack(writer.directory) is None
    ob.write_ack(writer.directory, {"ledger_instance": "L", "sequence": 1, "digest": "a"})
    ob.write_ack(writer.directory, {"ledger_instance": "L", "sequence": 2, "digest": "b"})
    with open(writer.directory / "ack.log", "ab") as handle:
        handle.write(b"0" * 64 + b' {"torn":')

    assert ob.read_ack(writer.directory) == {"ledger_instance": "L", "sequence": 2, "digest": "b"}


def test_compaction_deletes_only_acknowledged_closed_segments(tmp_path):
    writer = _writer(tmp_path, segment_bytes=200)
    for n in range(8):
        writer.append({"kind": "k", "pad": "z" * 60, "n": n})
    scan = ob.scan_stream(writer.directory)
    active = scan.segments[-1].name
    acked = scan.segments[1].last_sequence
    ob.write_ack(writer.directory, {"ledger_instance": "L", "sequence": acked, "digest": "d"})

    deleted = ob.compact(writer.directory, scan, acked, active_segment=active)
    rescan = ob.scan_stream(writer.directory)

    assert deleted == [scan.segments[0].name, scan.segments[1].name]
    assert rescan.records[0].sequence == acked + 1 and rescan.damage == (), "a compacted stream still verifies"
    ob.write_ack(writer.directory, {"ledger_instance": "L", "sequence": 8, "digest": "d"})
    assert ob.compact(writer.directory, ob.scan_stream(writer.directory), 10**6, active_segment=active) == [
        s.name for s in scan.segments[2:-1]
    ], "an acknowledgement past the end never deletes the active segment"
    assert (writer.directory / active).exists()
    writer.close()


def test_compaction_keeps_a_damaged_segment(tmp_path):
    writer = _writer(tmp_path)
    for n in range(3):
        writer.append({"kind": "k", "n": n})
    writer.close()
    segment = writer.directory / "seg-000001.log"
    segment.write_bytes(segment.read_bytes()[:-3])

    assert ob.compact(writer.directory, ob.scan_stream(writer.directory), 3, active_segment=None) == []
    assert segment.exists()


def test_the_owned_writer_confirms_records_and_rejects_when_full_or_closed(tmp_path):
    writer = ob.OutboxWriter(tmp_path / "outbox", queue_records=1)
    assert writer.submit({"kind": "k"}).wait(5.0)

    gate = threading.Event()
    original = writer._writer.append

    def slow_append(payload, *, event_id=None):
        gate.wait(5.0)
        return original(payload, event_id=event_id)

    writer._writer.append = slow_append  # type: ignore[method-assign]
    in_flight = writer.submit({"kind": "k"})
    deadline_tickets = [writer.submit({"kind": "k"}) for _ in range(3)]
    rejected = [t for t in deadline_tickets if t.failure == "QUEUE_FULL"]

    assert not in_flight.wait(0.05), "a record that is not yet durable is not confirmed"
    assert rejected, "a full queue rejects immediately rather than blocking"
    gate.set()
    assert in_flight.wait(5.0)
    writer.close()
    assert writer.submit({"kind": "k"}).failure == "CLOSED"
    assert writer.stats().rejected_full == len(rejected)


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
    scan = ob.scan_stream(stream)

    assert killed.returncode == 7
    assert handle is not None, "the dead writer's lock is released with its process"
    ob.release(handle)
    assert [r.payload["n"] for r in scan.records] == [0, 1, 2]
    assert [d.reason for d in scan.damage] == ["torn"]
