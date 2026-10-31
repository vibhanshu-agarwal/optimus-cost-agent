"""Plan 12.8 Task 1: the usage-capture upload contract and the ledger's ordering check."""

from __future__ import annotations

import json

import pytest

from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc


def _stream(tmp_path, kinds=("stream.start", "epoch.begin", "attempt.intent")) -> list[ob.Record]:
    writer = ob.StreamWriter(tmp_path / "outbox")
    records = [writer.append({"kind": kind}) for kind in kinds]
    writer.close()
    return records


def test_a_batch_round_trips_and_reverifies_every_line(tmp_path):
    records = _stream(tmp_path)
    body = uc.build_batch("host", records[0].stream_id, 0, ob.GENESIS, records)

    batch = uc.parse_batch(body)

    assert batch.writer == "host" and batch.after_sequence == 0
    assert [r.digest for r in batch.records] == [r.digest for r in records]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: d.update(extra=1), "unknown_field"),
        (lambda d: d.update(schema_version=2), "schema"),
        (lambda d: d.update(writer="admin"), "writer"),
        (lambda d: d.update(stream_id="../x"), "stream"),
        (lambda d: d.update(records=[]), "limit"),
        (lambda d: d["after"].update(sequence=-1), "malformed"),
        (lambda d: d.update(records=[d["records"][0].replace('"stream.start"', '"stream.stArt"')]), "record"),
        (lambda d: d.update(records=list(reversed(d["records"]))), "order"),
    ],
)
def test_a_malformed_batch_is_refused_before_any_ledger_work(tmp_path, mutate, code):
    records = _stream(tmp_path)
    document = json.loads(uc.build_batch("host", records[0].stream_id, 0, ob.GENESIS, records))
    mutate(document)

    with pytest.raises(uc.ContractError) as refused:
        uc.parse_batch(json.dumps(document).encode())

    assert refused.value.code == code


def test_a_writer_may_send_only_its_own_kinds(tmp_path):
    records = _stream(tmp_path, kinds=("attempt.receipt",))

    with pytest.raises(uc.ContractError) as refused:
        uc.parse_batch(uc.build_batch("gateway", records[0].stream_id, 0, ob.GENESIS, records))

    assert refused.value.code == "kind"


def test_a_line_from_another_stream_and_an_oversized_body_are_refused(tmp_path):
    records = _stream(tmp_path)
    other = "f" * 32
    with pytest.raises(uc.ContractError) as wrong:
        uc.parse_batch(uc.build_batch("host", other, 0, ob.GENESIS, records))
    with pytest.raises(uc.ContractError) as big:
        uc.parse_batch(b" " * (uc.MAX_BODY_BYTES + 1))

    assert wrong.value.code == "stream" and big.value.code == "too_large"


def test_only_a_committed_ack_for_the_same_stream_parses(tmp_path):
    ack = uc.CaptureAck("a" * 32, "b" * 32, 3, "c" * 64)
    document = uc.build_ack(ack)

    assert uc.parse_ack(document, stream_id="b" * 32) == ack
    for bad in ({**document, "status": "accepted"}, {**document, "stream_id": "d" * 32}, {**document, "sequence": 0}, {**document, "x": 1}):
        with pytest.raises(uc.ContractError):
            uc.parse_ack(bad, stream_id="b" * 32)


def test_the_ledger_ordering_check_accepts_only_the_next_record_or_an_explaining_gap(tmp_path):
    first, second, third = _stream(tmp_path)

    assert ob.follows(first, 0, ob.GENESIS) == ""
    assert ob.follows(second, 1, first.digest) == ""
    assert ob.follows(third, 1, first.digest) == "sequence"
    assert ob.follows(second, 1, "0" * 63 + "1") == "chain"
    gap = ob.frame(first.stream_id, 4, second.digest, {"kind": ob.GAP_KIND, "unconfirmed_from": 3, "unconfirmed_to": 3})
    retracting = ob.frame(first.stream_id, 4, first.digest, {"kind": ob.GAP_KIND, "unconfirmed_from": 2, "unconfirmed_to": 3})
    assert ob.follows(gap, 2, second.digest) == ""
    assert ob.follows(retracting, 2, second.digest) == "sequence", "a gap never retracts a committed record"
