"""Plan 12.9 Task 3: each admitted turn's explicit Auto/fixed selection (`turn.report_context`) in its own epoch before
classification, written only to a Gateway that lists the feature, and the host's report scope (its turn count and its
stream's frontier). Synthetic identities only; no model is named."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.auto_composition import ClassifierHalted, ClassifierOutcome
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.gateway.models import GatewayUsage
from optimus.usage.capture_delivery import CaptureDelivery
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus.usage.savings_report import ReportTransportError
from optimus.usage.turn_settlement import StageReceipt
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security import usage_report_contract as urc
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_auto_turn_routing import GEMINI, Classifier, _router
from tests.unit.acp.test_context_engine_admission import Runner, new_session, prompt

_AT = datetime(2026, 11, 1, tzinfo=UTC)


def _capture(tmp_path: Path, *, enabled: bool = True) -> DurableCapture:
    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=5.0, clock=lambda: _AT)
    if enabled:
        capture.enable_report_context()
    return capture


def _records(capture: DurableCapture) -> list[dict[str, Any]]:
    capture.stop()
    payloads = [dict(r.payload) for r in ob.scan_stream(capture.writer.directory).records]
    for payload in payloads:
        uc.validate_payload(payload, writer="host")  # every record is one the ledger accepts
    return payloads


# --- The capture ---------------------------------------------------------------------------------------------------


def test_without_the_negotiated_feature_no_context_is_written_and_the_turn_still_counts(tmp_path):
    capture = _capture(tmp_path, enabled=False)

    assert capture.report_context("s:1", "s", selection="auto", registry_hash=None, strategy=None) is False
    assert capture.report_scope("s") == (1, ())  # counted by the host, though nothing was written yet
    capture.stop()
    assert not capture.writer.directory.exists(), "nothing was written"


def test_the_context_opens_the_turns_epoch_and_its_invocations_join_that_epoch(tmp_path):
    capture = _capture(tmp_path)

    assert capture.report_context("s:1", "s", selection="fixed", registry_hash="hex:" + "2" * 64, strategy="sliding_window")
    capture.invocation_opened("s:1", "s")
    records = _records(capture)

    begin, context, opened = records[1], records[2], records[3]
    assert [r["kind"] for r in records[:4]] == [uc.STREAM_START, uc.EPOCH_BEGIN, uc.TURN_REPORT_CONTEXT, uc.INVOCATION_OPEN]
    assert begin["epoch_id"] == context["epoch_id"] == opened["epoch_id"] and begin["session_id"] == "s"
    assert (context["selection"], context["strategy"], context["turn_id"]) == ("fixed", "sliding_window", "s:1")


def test_a_context_after_the_turns_close_is_not_written_and_never_reopens_it(tmp_path):
    from optimus.usage.turn_settlement import TurnSettlement

    capture = _capture(tmp_path)
    settlement = TurnSettlement(capture=capture, session_id="s")
    invocation = settlement.open_invocation("s:1")
    invocation.start()
    invocation.end()
    settlement.finalize_turn("s:1")

    assert capture.report_context("s:1", "s", selection="auto", registry_hash=None, strategy=None) is False
    kinds = [r["kind"] for r in _records(capture)]
    assert uc.TURN_REPORT_CONTEXT not in kinds and kinds.count(uc.EPOCH_BEGIN) == 1


def test_the_report_scope_counts_each_sessions_turns_and_claims_every_record_not_yet_delivered(tmp_path):
    capture = _capture(tmp_path)
    for turn in ("a:1", "a:2"):
        capture.report_context(turn, "a", selection="auto", registry_hash=None, strategy=None)
    capture.invocation_opened("b:1", "b")

    turns, frontier = capture.report_scope("a")
    stats = capture.writer.stats()

    assert turns == 2 and capture.report_scope("b")[0] == 1 and capture.report_scope("c") == (0, frontier)
    [(stream, sequence)] = frontier
    assert stream == capture.writer.stream_id and sequence == stats.confirmed_sequence + stats.pending >= 1
    capture.stop()


# --- Negotiation -----------------------------------------------------------------------------------------------------


class _Capabilities:
    """The bounded report-route POST (`savings_report.gateway_post`) as the Gateway answers it."""

    def __init__(self, *answers: Any) -> None:
        self.answers, self.asked = list(answers), 0

    def __call__(self, body: bytes) -> tuple[int, Any]:
        self.asked += 1
        assert json.loads(body) == {"schema_version": 1, "operation": "capabilities"}
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.mark.parametrize(("answers", "enabled", "asked"), [
    ([(200, urc.capabilities_body())], True, 1),
    ([(404, {"error": "not found"})], False, 1),  # an older Gateway: never asked again, never sent a context
    ([(200, {"status": "ok"})], False, 1),  # an answer this contract does not know
    ([ReportTransportError("unreachable"), (503, urc.error_body("LEDGER_UNAVAILABLE")[1]), (200, urc.capabilities_body())], True, 3),
    ([ReportTransportError("timeout"), (200, urc.capabilities_body())], True, 2),  # a stalled answer, cut at its bound
    ([RuntimeError("unexpected"), (200, urc.capabilities_body())], True, 2),  # contained, asked again
])
def test_delivery_enables_contexts_only_for_a_gateway_that_lists_the_feature(tmp_path, answers, enabled, asked):
    capture = _capture(tmp_path, enabled=False)
    capabilities = _Capabilities(*answers)
    delivery = CaptureDelivery(capture, object(), capabilities=capabilities)  # type: ignore[arg-type]

    for _ in range(4):
        delivery.drain_once()

    assert capabilities.asked == asked and delivery.report_context is enabled
    assert capture.report_context("s:1", "s", selection="auto", registry_hash=None, strategy=None) is enabled
    capture.stop()


# --- Real spec turns ---------------------------------------------------------------------------------------------------


class _Paid:
    """Records a paid classification receipt in the turn's settlement, as the real H classifier does."""

    def __call__(self, contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
        usage = GatewayUsage(gateway_request_id="gw-c1", provider="p-1", billing_units=1, cost_usd=Decimal("0.0001"))
        call.record_receipt(StageReceipt(
            session_id=call.session_id, turn_id=call.run_id, stage="classification", attempt_id=f"{call.run_id}:classification:1:1",
            gateway_request_id="gw-c1", outcome="completed", reported_cost_usd=Decimal("0.0001"), recorded_at=_AT, gateway_usage=usage,
        ))
        return ClassifierOutcome(tier="easy", confidence_band="high", predicted_tier="easy", answered_by="classifier")


def _adapter(tmp_path: Path, capture: DurableCapture, classifier: Any | None):
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(Runner()), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(capture=capture),
        outbound=outbound, auto_router=None if classifier is None else _router(classifier),
    )
    return adapter, outbound


def _turn_records(records: list[dict[str, Any]], turn: str) -> list[dict[str, Any]]:
    epochs = {r["epoch_id"] for r in records if r.get("turn_id") == turn and "epoch_id" in r}
    return [r for r in records if r.get("epoch_id") in epochs]


async def _one_turn(tmp_path: Path, classifier: Any | None, *, stop: str | None = None) -> tuple[str, list[dict[str, Any]], dict]:
    capture = _capture(tmp_path)
    adapter, outbound = _adapter(tmp_path, capture, classifier)
    if stop is not None:
        adapter._auto_router.stops.add(stop)  # noqa: SLF001
    session_id = await new_session(adapter, tmp_path, mode="chat")
    response = await prompt(adapter, outbound, session_id, "Hello?", "q1")
    return f"{session_id}:1", _records(capture), response


@pytest.mark.parametrize(("classifier", "stop", "selection"), [
    (None, None, "fixed"),  # an ordinary turn
    (Classifier(["easy"]), None, "auto"),  # routed
    (_Paid(), None, "auto"),  # routed after a paid classification
    (Classifier(["complex"]), GEMINI, "auto"),  # refused: no routable model
    (Classifier([ClassifierHalted()]), None, "auto"),  # cancelled by a refused lease
])
async def test_every_admitted_turn_records_its_selection_once_before_classification_and_closes(tmp_path, classifier, stop, selection):
    turn, records, _ = await _one_turn(tmp_path, classifier, stop=stop)
    own = _turn_records(records, turn)
    kinds = [r["kind"] for r in own]

    contexts = [r for r in own if r["kind"] == uc.TURN_REPORT_CONTEXT]
    assert [c["selection"] for c in contexts] == [selection] and contexts[0]["session_id"] == turn.rsplit(":", 1)[0]
    if selection == "auto":  # the Auto router's trusted snapshot, the launch's provenance
        assert contexts[0]["registry_hash"] == _router(Classifier([])).snapshot.effective_hash
    assert kinds[0] == uc.EPOCH_BEGIN and kinds[1] == uc.TURN_REPORT_CONTEXT, "before any invocation or classification"
    assert kinds.count(uc.EPOCH_CLOSE) == 1, "the turn's epoch still closes"
    assert all(r["turn_id"] == turn for r in own if r["kind"] == uc.ATTEMPT_RECEIPT)
    if isinstance(classifier, _Paid):  # the classification receipt is in the context's epoch, after the context
        assert kinds.index(uc.TURN_REPORT_CONTEXT) < kinds.index(uc.ATTEMPT_RECEIPT)


async def test_without_capture_a_turn_is_unchanged(tmp_path):
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Runner()), workspace_root=tmp_path,
                               sessions=InMemoryAcpSpecSessionStore(), outbound=outbound, auto_router=_router(Classifier(["easy"])))
    session_id = await new_session(adapter, tmp_path, mode="chat")

    response = await prompt(adapter, outbound, session_id, "Hello?", "q1")

    assert response["result"]["stopReason"] == "end_turn"


async def test_a_turn_torn_down_during_classification_keeps_its_context_and_late_receipt(tmp_path):
    class TearsDown:
        def __call__(self, contract: Any, stops: Any, call: Any) -> ClassifierOutcome:
            call.operation_control.request_transport_teardown()
            call.record_receipt(StageReceipt(
                session_id=call.session_id, turn_id=call.run_id, stage="classification",
                attempt_id=f"{call.run_id}:classification:1:1", gateway_request_id=None, outcome="uncertain",
                reported_cost_usd=None, recorded_at=_AT,
            ))
            return ClassifierOutcome(tier="easy", confidence_band="high", predicted_tier="easy", answered_by="classifier")

    turn, records, _ = await _one_turn(tmp_path, TearsDown())
    own = _turn_records(records, turn)

    assert [r["selection"] for r in own if r["kind"] == uc.TURN_REPORT_CONTEXT] == ["auto"]
    assert any(r["kind"] == uc.ATTEMPT_RECEIPT and r["outcome"] == "uncertain" for r in own), "the abandoned turn's cost stays visible"


def test_records_still_being_written_put_the_frontier_beyond_anything_the_ledger_can_have_committed():
    from types import SimpleNamespace

    writer = SimpleNamespace(stream_id="f" * 32, stats=lambda: ob.WriterStats(confirmed_sequence=5, pending=2))
    capture = DurableCapture(writer, ack_wait=0.0, clock=lambda: _AT)  # type: ignore[arg-type]

    assert capture.report_scope("s") == (0, (("f" * 32, 7),))



class _AckingClient:
    """A Gateway capture route that commits every batch it is sent."""

    def __init__(self) -> None:
        self.batches = 0

    def post_observability_json(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert path == uc.PATH
        self.batches += 1
        last = ob.parse_line(payload["records"][-1].encode("ascii"))
        return {"status": "committed", "ledger_instance": "a" * 32, "stream_id": payload["stream_id"],
                "sequence": last.sequence, "digest": last.digest, "conflicts": 0}


def test_a_stalled_capabilities_endpoint_never_holds_up_ordinary_receipt_delivery(tmp_path):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.usage.savings_report import gateway_post

    class Stalls(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"{")
            self.wfile.flush()
            time.sleep(5)  # the capabilities answer never completes in time

    server = ThreadingHTTPServer(("127.0.0.1", 0), Stalls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    settings = OptimusGatewaySettings(gateway_url=f"http://127.0.0.1:{server.server_address[1]}", optimus_api_key="opt_live_k")  # pragma: allowlist secret
    capture = _capture(tmp_path, enabled=False)
    capture.invocation_opened("s:1", "s")
    for _ in range(100):
        if capture.writer.stats().confirmed_sequence >= 3 and not capture.writer.stats().pending:
            break
        time.sleep(0.01)
    client = _AckingClient()
    delivery = CaptureDelivery(capture, client, capabilities=gateway_post(settings, timeout=0.5))  # type: ignore[arg-type]
    try:
        started = time.monotonic()
        report = delivery.drain_once()
        elapsed = time.monotonic() - started
    finally:
        server.shutdown()
        server.server_close()
        capture.stop()

    assert report.failures == [] and report.committed >= 3 and client.batches >= 1, "the capture pass still ran"
    assert delivery.report_context is None and elapsed < 2, "asked again next pass; this one was bounded"
