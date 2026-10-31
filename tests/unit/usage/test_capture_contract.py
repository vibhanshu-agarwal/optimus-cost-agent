"""Plan 12.8 Task 1: the usage-capture contract (per-kind schemas, batches, acknowledgements) and the ordering check."""

from __future__ import annotations

import json

import pytest

from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

_AT = "2026-10-31T00:00:00+00:00"
_EPOCH = "e" * 32
_LEDGER = "a" * 32


def _payloads() -> list[dict]:
    return [
        {"kind": uc.STREAM_START, "at": _AT},
        {"kind": uc.EPOCH_BEGIN, "at": _AT, "epoch_id": _EPOCH, "turn_id": "s:1", "session_id": "s"},
        {"kind": uc.ATTEMPT_INTENT, "at": _AT, "epoch_id": _EPOCH, "host_request_id": "s:1:planning:1:1", "stage": "planning",
         "purpose": "agent.plan", "requested_model": None},
    ]


def _stream(tmp_path, payloads=None) -> list[ob.Record]:
    writer = ob.StreamWriter(tmp_path / "outbox")
    records = [writer.append(payload) for payload in (payloads or _payloads())]
    writer.close()
    return records


def _batch(records, *, writer="host", ledger=None) -> bytes:
    return uc.build_batch(writer, records[0].stream_id, ledger, 0, ob.GENESIS, records)


def test_a_batch_round_trips_and_reverifies_every_line(tmp_path):
    records = _stream(tmp_path)

    batch = uc.parse_batch(_batch(records, ledger=_LEDGER))

    assert batch.writer == "host" and batch.after_sequence == 0 and batch.ledger_instance == _LEDGER
    assert [r.digest for r in batch.records] == [r.digest for r in records]


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: d.update(extra=1), "unknown_field"),
        (lambda d: d.pop("ledger_instance"), "malformed"),
        (lambda d: d.update(schema_version=2), "schema"),
        (lambda d: d.update(writer="admin"), "writer"),
        (lambda d: d.update(writer=[]), "writer"),
        (lambda d: d.update(stream_id="../x"), "stream"),
        (lambda d: d.update(ledger_instance="not-hex"), "stream"),
        (lambda d: d.update(records=[]), "limit"),
        (lambda d: d.update(records={}), "limit"),
        (lambda d: d["after"].update(sequence=-1), "malformed"),
        (lambda d: d["after"].update(sequence=3), "malformed"),
        (lambda d: d.update(after=[]), "malformed"),
        (lambda d: d.update(records=[d["records"][0].replace('"stream.start"', '"stream.stArt"')]), "record"),
        (lambda d: d.update(records=[1]), "record"),
        (lambda d: d.update(records=list(reversed(d["records"]))), "order"),
    ],
)
def test_a_malformed_batch_is_refused_before_any_ledger_work(tmp_path, mutate, code):
    records = _stream(tmp_path)
    document = json.loads(_batch(records))
    mutate(document)

    with pytest.raises(uc.ContractError) as refused:
        uc.parse_batch(json.dumps(document).encode())

    assert refused.value.code == code


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": uc.ATTEMPT_RECEIPT, "prompt": "leaked prompt text"},
        {**_payloads()[1], "prompt": "leaked prompt text"},
        {**_payloads()[1], "session_id": 7},
        {k: v for k, v in _payloads()[1].items() if k != "turn_id"},
        {**_payloads()[2], "stage": "exfiltrate"},
        {**_payloads()[2], "purpose": "Not A Purpose"},
        {**_payloads()[1], "turn_id": "x" * (uc.MAX_STRING + 1)},
    ],
)
def test_a_record_outside_its_kinds_schema_is_refused(tmp_path, payload):
    records = _stream(tmp_path, [payload])

    with pytest.raises(uc.ContractError) as refused:
        uc.parse_batch(_batch(records))

    assert refused.value.code == "payload"


def test_a_writer_may_send_only_its_own_kinds(tmp_path):
    records = _stream(tmp_path, [_payloads()[1]])

    with pytest.raises(uc.ContractError) as refused:
        uc.parse_batch(_batch(records, writer="gateway"))

    assert refused.value.code == "kind"


def test_a_line_from_another_stream_and_an_oversized_body_are_refused(tmp_path):
    records = _stream(tmp_path)
    with pytest.raises(uc.ContractError) as wrong:
        uc.parse_batch(uc.build_batch("host", "f" * 32, None, 0, ob.GENESIS, records))
    with pytest.raises(uc.ContractError) as big:
        uc.parse_batch(b" " * (uc.MAX_BODY_BYTES + 1))

    assert wrong.value.code == "stream" and big.value.code == "too_large"


def test_a_maximal_record_fits_in_a_batch():
    assert ob.MAX_RECORD_BYTES * 2 < uc.MAX_BODY_BYTES, "any one record is always drainable"


def test_only_a_committed_ack_for_the_same_stream_parses():
    ack = uc.CaptureAck("a" * 32, "b" * 32, 3, "c" * 64)
    document = uc.build_ack(ack)

    assert uc.parse_ack(document, stream_id="b" * 32) == ack
    for bad in ({**document, "status": "accepted"}, {**document, "stream_id": "d" * 32}, {**document, "sequence": 0}, {**document, "x": 1}, []):
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


def _receipt_payload(cost: str = "0.25", usage_cost: str | None = None) -> dict:
    from datetime import UTC, datetime
    from decimal import Decimal

    from optimus.gateway.models import GatewayUsage
    from optimus.usage.capture_events import receipt_payload
    from optimus.usage.turn_settlement import StageReceipt

    usage = GatewayUsage(gateway_request_id="gw-1", provider="openrouter", billing_units=3, cost_usd=Decimal(cost))
    receipt = StageReceipt(session_id="s", turn_id="s:1", stage="planning", attempt_id="s:1:planning:1:1", gateway_request_id="gw-1",
                           outcome="completed", reported_cost_usd=Decimal(cost), recorded_at=datetime(2026, 10, 31, tzinfo=UTC), gateway_usage=usage)
    payload = receipt_payload(receipt, epoch_id=_EPOCH, late=False)
    payload["at"] = _AT
    if usage_cost is not None:
        payload["usage"]["cost_usd"] = usage_cost
    return payload


def test_the_ledger_recomputes_receipt_fingerprints_and_enforces_receipt_rules(tmp_path):
    good = _receipt_payload()
    tampered = {**good, "reported_cost_usd": "9.99", "usage": {**good["usage"], "cost_usd": "9.99"}}  # old fingerprints kept
    contradicting = _receipt_payload(usage_cost="0.30")  # usage disagrees with the receipt's cost
    uncertain_with_cost = {**good, "outcome": "uncertain", "usage": None}

    assert uc.validate_payload(good, writer="host") == uc.ATTEMPT_RECEIPT
    for bad in (tampered, contradicting, uncertain_with_cost):
        with pytest.raises(uc.ContractError) as refused:
            uc.validate_payload(bad, writer="host")
        assert refused.value.code == "receipt"
    assert uc.receipt_fingerprints(_receipt_payload("0.25")) == uc.receipt_fingerprints(_receipt_payload("0.250"))
