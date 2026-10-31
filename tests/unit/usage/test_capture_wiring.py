"""Plan 12.8 Task 2: durable capture wired into the existing settlement and the Gateway client, on a real outbox under a
temporary root. Every record read back is validated against its kind's contract schema."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.spec import InMemoryAcpSpecSessionStore
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import CAPTURE_REQUEST_HEADER, CaptureIntent, GatewayClient, GatewayRequest, capturing
from optimus.gateway.models import GatewayUsage
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.operation_capture import captured_operation
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc

_AT = datetime(2026, 10, 31, tzinfo=UTC)
_REPLY = {
    "id": "resp-1",
    "output_text": "ok",
    "gateway_usage": {"gateway_request_id": "gw-1", "provider": "glm", "cache_hit": False, "billing_units": 7, "cost_usd": "0.0007"},
}


class _Transport:
    def __init__(self, events: list[str], reply: dict | None = None, error: Exception | None = None) -> None:
        self.events, self.reply, self.error = events, reply or _REPLY, error
        self.requests: list[GatewayRequest] = []

    def post_json(self, request: GatewayRequest) -> dict:
        self.events.append("send")
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.reply


def _settings() -> OptimusGatewaySettings:
    return OptimusGatewaySettings(gateway_url="http://127.0.0.1:8765", optimus_api_key="opt_live_abc")  # pragma: allowlist secret


def _capture(tmp_path: Path) -> DurableCapture:
    return DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=5.0, clock=lambda: _AT)


def _records(capture: DurableCapture) -> list[dict]:
    capture.stop()
    payloads = [dict(r.payload) for r in ob.scan_stream(capture.writer.directory).records]
    for payload in payloads:
        uc.validate_payload(payload, writer="host")
    return payloads


def _receipt(attempt: str = "s:1:planning:1:1", *, cost: str = "0.25", gw: str = "gw-a") -> StageReceipt:
    usage = GatewayUsage(gateway_request_id=gw, provider="openrouter", billing_units=3, cost_usd=Decimal(cost))
    return StageReceipt(
        session_id="s", turn_id="s:1", stage="planning", attempt_id=attempt, gateway_request_id=gw, outcome="completed",
        reported_cost_usd=Decimal(cost), recorded_at=_AT, gateway_usage=usage,
    )


def test_the_client_records_the_intent_before_it_sends_and_carries_the_host_request(tmp_path):
    events: list[str] = []
    transport = _Transport(events)

    def hook(intent: CaptureIntent) -> bool:
        events.append(f"intent:{intent.host_request_id}")
        return True

    client = GatewayClient(settings=_settings(), transport=transport, capture=hook)
    with capturing(CaptureIntent("s:1", "s:1:planning:1:1", "planning")):
        client.create_response(model="m", input_text="hi")
    client.create_response(model="m", input_text="outside")

    assert events == ["intent:s:1:planning:1:1", "send", "send"]
    assert transport.requests[0].headers[CAPTURE_REQUEST_HEADER] == "s:1:planning:1:1"
    assert CAPTURE_REQUEST_HEADER not in transport.requests[1].headers


def test_a_failing_hook_or_malformed_identity_never_stops_the_send(tmp_path):
    events: list[str] = []
    transport = _Transport(events)

    def broken(intent: CaptureIntent) -> bool:
        raise OSError("disk gone")

    client = GatewayClient(settings=_settings(), transport=transport, capture=broken)
    with capturing(CaptureIntent("s:1", "s:1:planning:1:1", "planning")):
        assert client.create_response(model="m", input_text="hi").output_text == "ok"
    with capturing(CaptureIntent("s:1", "bad id\nX-Injected: 1", "planning")):
        client.create_response(model="m", input_text="hi")

    assert events == ["send", "send"]
    assert CAPTURE_REQUEST_HEADER not in transport.requests[1].headers, "a malformed identity is never sent as a header"


def test_settlement_appends_invocations_new_receipts_integrity_and_the_close(tmp_path):
    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    receipt = _receipt()
    settlement.record_attempt(receipt)
    settlement.record_attempt(receipt)  # an identical replay adds nothing
    with pytest.raises(ReceiptConflictError):
        settlement.record_attempt(_receipt(cost="0.30"))
    settlement.record_integrity_failure("s:1")  # the existing ledger refused a charge
    settlement.finalize_turn("s:1")  # a worker still runs: terminal snapshot only
    invocation.end()  # the last worker settles: the close follows

    records = _records(capture)
    kinds = [r["kind"] for r in records]

    assert kinds == [
        uc.STREAM_START, uc.EPOCH_BEGIN, uc.INVOCATION_OPEN, uc.ATTEMPT_RECEIPT, uc.INTEGRITY_FAILURE, uc.INTEGRITY_FAILURE,
        uc.EPOCH_TERMINAL, uc.INVOCATION_END, uc.EPOCH_IDENTITIES, uc.EPOCH_CLOSE, uc.STREAM_END,
    ]
    assert [r["reason"] for r in records if r["kind"] == uc.INTEGRITY_FAILURE] == ["receipt_conflict", "ledger_refused"]
    assert records[1]["session_id"] == "s"
    close = records[-2]
    assert close["integrity_failures"] == 2 and close["host_complete"] is False and close["known_subtotal_usd"] == "0.25"


def test_a_clean_turn_closes_complete_and_the_known_subtotal_is_settlements_own(tmp_path):
    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    events: list[str] = []
    client = GatewayClient(settings=_settings(), transport=_Transport(events), capture=capture.hook)
    with capturing(CaptureIntent("s:1", "s:1:planning:1:1", "planning")):
        client.create_response(model="m", input_text="hi")
    settlement.record_attempt(_receipt())
    invocation.end()
    settlement.finalize_turn("s:1")

    records = _records(capture)
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert close["host_complete"] is True and close["intents"] == 1
    assert close["known_subtotal_usd"] == str(settlement.settle_turn("s:1").known_subtotal_usd)


def test_settlement_without_capture_is_unchanged_and_writes_nothing(tmp_path):
    settlement = TurnSettlement()
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    settlement.record_attempt(_receipt())
    invocation.end()
    settlement.finalize_turn("s:1")

    assert settlement.settle_turn("s:1").complete
    assert not (tmp_path / "config").exists()


def test_persistence_failing_from_the_start_never_stops_settlement_or_model_work(tmp_path):
    blocker = tmp_path / "config"
    blocker.write_bytes(b"not a directory")  # the accounting root cannot be created
    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(blocker)), ack_wait=1.0, clock=lambda: _AT)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    events: list[str] = []
    client = GatewayClient(settings=_settings(), transport=_Transport(events), capture=capture.hook)
    with capturing(CaptureIntent("s:1", "s:1:planning:1:1", "planning")):
        reply = client.create_response(model="m", input_text="hi")
    settlement.record_attempt(_receipt())
    invocation.end()
    settlement.finalize_turn("s:1")
    capture.stop()

    assert reply.output_text == "ok" and events == ["send"]
    summary = settlement.settle_turn("s:1")
    assert summary.known_subtotal_usd == Decimal("0.25") and summary.complete, "the in-memory settlement is untouched"
    assert capture.writer.stats().write_failures >= 1


def test_a_receipt_after_the_close_is_appended_late_and_a_later_epoch_cannot_repair_it(tmp_path):
    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    invocation.end()
    settlement.finalize_turn("s:1")
    deadline = time.monotonic() + 5.0
    while capture.writer.stats().pending and time.monotonic() < deadline:
        time.sleep(0.01)
    settlement.record_attempt(_receipt())  # e.g. a worker left behind by transport teardown
    second = settlement.open_invocation("s:2")
    second.start()
    second.end()
    settlement.finalize_turn("s:2")

    records = _records(capture)
    late = next(r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT)
    closes = [r for r in records if r["kind"] == uc.EPOCH_CLOSE]
    assert late["late"] is True and late["epoch_id"] == closes[0]["epoch_id"]
    assert len(closes) == 2 and closes[0]["epoch_id"] != closes[1]["epoch_id"]


def test_an_operation_call_gets_its_own_complete_epoch(tmp_path):
    capture = _capture(tmp_path)
    events: list[str] = []
    client = GatewayClient(settings=_settings(), transport=_Transport(events), capture=capture.hook)

    reply = captured_operation(capture, kind="gateway_passthrough", requested_model="m",
                               call=lambda: client.create_response(model="m", input_text="hi"))

    records = _records(capture)
    kinds = [r["kind"] for r in records]
    assert reply.output_text == "ok"
    assert kinds == [
        uc.STREAM_START, uc.EPOCH_BEGIN, uc.INVOCATION_OPEN, uc.ATTEMPT_INTENT, uc.ATTEMPT_RECEIPT, uc.INVOCATION_END,
        uc.EPOCH_IDENTITIES, uc.EPOCH_CLOSE, uc.STREAM_END,
    ]
    intent, receipt, close = records[3], records[4], records[-2]
    assert intent["purpose"] == "operation.gateway_passthrough" and intent["stage"] == "operation"
    assert receipt["attempt_id"] == intent["host_request_id"] and receipt["reported_cost_usd"] == "0.0007"
    assert close["host_complete"] is True and close["turn_id"].startswith("op:gateway_passthrough:")


def test_a_failed_operation_call_propagates_and_its_epoch_stays_incomplete(tmp_path):
    capture = _capture(tmp_path)
    client = GatewayClient(settings=_settings(), transport=_Transport([], error=ConnectionResetError("lost")), capture=capture.hook)

    with pytest.raises(Exception):  # noqa: B017 - the call's own failure passes through unchanged
        captured_operation(capture, kind="preflight_probe", call=lambda: client.create_response(model="m", input_text="hi"))

    records = _records(capture)
    receipt = next(r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT)
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert receipt["outcome"] == "uncertain" and receipt["reported_cost_usd"] is None
    assert close["host_complete"] is False and close["unknown_count"] == 1


def test_without_capture_an_operation_is_just_the_call():
    assert captured_operation(None, kind="preflight_probe", call=lambda: "reply") == "reply"  # type: ignore[arg-type,return-value]


def test_each_session_of_a_capturing_store_settles_into_the_one_capture(tmp_path):
    capture = _capture(tmp_path)
    store = InMemoryAcpSpecSessionStore(capture=capture)
    first, second = store.create(cwd=tmp_path), store.create(cwd=tmp_path)
    first.cost_settlement.open_invocation(f"{first.session_id}:1").start()
    second.cost_settlement.open_invocation(f"{second.session_id}:1").start()

    begins = [r for r in _records(capture) if r["kind"] == uc.EPOCH_BEGIN]
    assert sorted(r["session_id"] for r in begins) == sorted([first.session_id, second.session_id])
    assert InMemoryAcpSpecSessionStore().create(cwd=tmp_path).cost_settlement._capture is None


async def test_a_real_spec_turn_begins_receipts_and_closes_its_epoch(tmp_path):
    from optimus.acp.spec import AcpDuplexAdapter, RecordingOutboundChannel
    from tests.support.contract_doubles import checked_agent_runner
    from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt

    class ReceiptingRunner(Runner):
        def run(self, request, **kwargs):
            kwargs["stage_receipts"](_receipt(f"{request.run_id}:planning:1:1", gw=f"gw-{request.run_id}").__class__(
                session_id=request.session_id, turn_id=request.run_id, stage="planning", attempt_id=f"{request.run_id}:planning:1:1",
                gateway_request_id=f"gw-{request.run_id}", outcome="completed", reported_cost_usd=Decimal("0.002"), recorded_at=_AT,
                gateway_usage=GatewayUsage(gateway_request_id=f"gw-{request.run_id}", provider="openrouter", billing_units=1, cost_usd=Decimal("0.002")),
            ))
            return super().run(request, **kwargs)

    capture = _capture(tmp_path)
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(ReceiptingRunner()),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(capture=capture),
        outbound=outbound,
    )
    session_id = await new_session(adapter, tmp_path)
    await prompt(adapter, outbound, session_id, "Plan it", "p1", approve=True)  # the approved run replays the receipt: no new charge

    records = _records(capture)
    kinds = [r["kind"] for r in records]
    assert kinds[:3] == [uc.STREAM_START, uc.EPOCH_BEGIN, uc.INVOCATION_OPEN]
    assert kinds.count(uc.EPOCH_CLOSE) == 1 and kinds.index(uc.ATTEMPT_RECEIPT) < kinds.index(uc.EPOCH_CLOSE)
    close = next(r for r in records if r["kind"] == uc.EPOCH_CLOSE)
    assert close["turn_id"] == f"{session_id}:1" and close["settled_count"] == 1 and close["known_subtotal_usd"] == "0.002"
