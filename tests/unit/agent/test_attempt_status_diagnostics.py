"""Plan 12.2 r4 stop diagnosis (Codex disposition 2026-10-13, operator-approved): the host keeps every provider
attempt's status in the opt-in ACP debug log, content-free, for Chat, planning and summarization.

r4's A1 failed after two Gateway attempts whose statuses the host had parsed and then dropped. Each classified
attempt is now logged with its call correlation, stage, ordered key, fixed-vocabulary outcome, whether the
Gateway routed it, and an integer-or-null status: the upstream status only for a routed attempt, the outer
host-to-Gateway status otherwise (a Gateway 502 is never evidence of an upstream 502); an unknown status stays
null. Nothing else: no bodies, headers, error text, keys, provider error types or identifiers. With tracing
disabled no diagnostic work happens, and a diagnostic failure never changes a result, a receipt or a
cancellation. Fake Gateway responses only: no service, no provider.

Summaries (Codex review M1 and its expansion ruling, 2026-10-14): the Gateway summarizer only attaches its
diagnostic to the response; the host runs it once, after every attempt was offered to the receipt sinks. Every
summary claim here goes through that consumer - GatewaySummarizerCall -> HostMaintenance -> the attached turn's
receipt sink, with the session settlement wired as the ACP host wires it - so a cancelling diagnostic is shown to
keep every receipt, charge, unknown cost and integrity failure, with the accounting error it overtakes attached.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from context_engine import MaintenanceRequest
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT
from optimus.acp import debug_trace
from optimus.acp.conversation import ConversationOutcome, ConversationSanitizer, ConversationSanitizerInputs, ConversationTurn
from optimus.acp.debug_trace import configure_debug_trace, log_provider_attempts, reset_debug_trace_context
from optimus.acp.settlement import EffectState
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.context import maintenance
from optimus.context.assembly import AttachedTurn
from optimus.context.maintenance import GatewaySummarizerCall, HostMaintenance, MaintenanceIdentity, MaintenanceReceipt, SummarizerResponse
from optimus.gateway.attempts import AttemptIntegrityError
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.errors import DuplicateGatewayRequestError
from optimus.usage.turn_settlement import ReceiptConflictError, StageReceipt, TurnSettlement, UsageLedgerAdapter, receipt_from_maintenance
from tests.unit.acp.test_context_engine_admission import make_attachment

CANARY = "Authorization: Bearer " + "attempt-status-canary"  # synthetic; must never reach the log
LOCATION = "debug_trace.py:log_provider_attempts"


def _usage(gateway_request_id: str) -> GatewayUsage:
    return GatewayUsage(gateway_request_id=gateway_request_id, provider="p", billing_units=3, cost_usd=Decimal("0.0003"))


def _routed(number: int, outcome: str, status: int | None = None) -> GatewayRouteAttempt:
    return GatewayRouteAttempt(attempt=number, gateway_request_id=f"gw-{number}", outcome=outcome, http_status=status)


def _rejected_twice(first: int, second: int) -> GatewayHttpError:
    return GatewayHttpError(
        502, f"upstream attempt failed {CANARY}", gateway_code="UPSTREAM_ATTEMPT_REJECTED", retryable=False,
        route_attempts=(_routed(1, "rejected", first), _routed(2, "rejected", second)),
    )  # fmt: skip


def _recovered(text: str) -> GatewayResponse:
    """Realistic: one recoverable 429, then a charged completion."""
    return GatewayResponse(
        output_text=text, gateway_usage=_usage("gw-2"), raw={"echo": CANARY}, finish_reason="stop",
        route_attempts=(_routed(1, "rejected", 429), _routed(2, "completed")),
    )  # fmt: skip


def _attempt(key: str, outcome: str, routed: bool, upstream: int | None, gateway: int | None) -> dict:
    return {"attempt": key, "outcome": outcome, "routed": routed, "upstream_http_status": upstream, "gateway_http_status": gateway}


def _failure(code: str | None, status: int) -> dict:
    return {"gateway_failure": {"code": code, "http_status": status}}


REJECTED_502 = _failure("UPSTREAM_ATTEMPT_REJECTED", 502)
# Each scenario: what the fake Gateway does, the attempts the log must hold (same for every stage), and, for a
# request that failed with a Gateway HTTP error, its allowlisted refusal code and outer status (r8 correction).
SCENARIOS = {
    "429-then-403": (lambda text: _rejected_twice(429, 403), [_attempt("1", "rejected", True, 429, None), _attempt("2", "rejected", True, 403, None)], REJECTED_502),
    "429-then-429": (lambda text: _rejected_twice(429, 429), [_attempt("1", "rejected", True, 429, None), _attempt("2", "rejected", True, 429, None)], REJECTED_502),
    "429-then-success": (_recovered, [_attempt("1", "rejected", True, 429, None), _attempt("2", "completed", True, None, None)], {}),
    "transport-loss-no-status": (lambda text: ConnectionResetError(CANARY), [_attempt("1", "uncertain", False, None, None)], {}),
    "gateway-502-absent-route-metadata": (lambda text: GatewayHttpError(502, CANARY), [_attempt("1", "uncertain", False, None, 502)], _failure(None, 502)),
    "gateway-502-malformed-route-metadata": (
        lambda text: GatewayHttpError(502, CANARY, gateway_code="UPSTREAM_ATTEMPT_REJECTED", retryable=False, route_attempts=(), route_attempts_malformed=True),
        [_attempt("1", "uncertain", False, None, 502)],
        REJECTED_502,
    ),
}  # fmt: skip
STAGES = {ExecutionMode.CHAT: ("answer", "Hello."), ExecutionMode.AGENT: ("planning", "WRITE a.py\nx")}


class FakeGateway:
    def __init__(self, outcome) -> None:
        self.outcome = outcome
        self.calls = 0

    def create_response(self, **kwargs):
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture(autouse=True)
def _isolated_trace():
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


def _trace(tmp_path: Path, *, enabled: bool = True) -> Path:
    log = tmp_path / "trace" / "debug-acp.ndjson"
    configure_debug_trace(enabled=enabled, log_path=log)
    return log


def _records(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [record for record in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if record["location"] == LOCATION]


def _run(tmp_path: Path, mode: ExecutionMode, scenario: str, *, observer=log_provider_attempts):
    tmp_path.mkdir(parents=True, exist_ok=True)
    make = SCENARIOS[scenario][0]
    receipts: list[StageReceipt] = []
    gateway = FakeGateway(make(STAGES[mode][1]))
    request = AgentRunRequest(run_id="s:1", session_id="s", task=f"Change the greeting. {CANARY}", workspace_root=tmp_path, execution_mode=mode)
    result = AgentRunner(gateway_client=gateway, model="fake/model", provider_attempt_observer=observer).run(request, stage_receipts=receipts.append)
    return result, receipts


def _outcome(result) -> tuple:
    return (
        result.status, result.final_state, result.stop_reason, result.output_text, result.total_cost_usd,
        result.cost_complete, result.unknown_cost_attempt_count, result.mutation_count,
    )  # fmt: skip


def _receipt_facts(receipts: list[StageReceipt]) -> list[tuple]:
    return [(r.stage, r.attempt_id, r.outcome, r.reported_cost_usd, r.http_status) for r in receipts]


# --- The summary consumer -----------------------------------------------------------------------------------------

SUMMARY_IDENTITY = MaintenanceIdentity(
    session_id="s", turn_seq=1, model_id="fake/summarizer", role="summarizer", route=("p",), reasoning=None,
    quantizations=(None,), strategy="compaction", revision_digest="d" * 64,
)  # fmt: skip
SUMMARY_REQUEST = MaintenanceRequest(
    input_text=f"ordinary synthetic history {CANARY}", covered_turn_ids=(1,), max_output_tokens=9,
    prompt_version=PROMPT_VERSION, format_version=SUMMARY_FORMAT,
)  # fmt: skip
SUMMARY_TEXT = "\n".join(f"## {name}\n-" for name in SECTIONS)
SANITIZER = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(), path_aliases=()))
EARLIER = datetime(2026, 10, 14, tzinfo=UTC)


def _ledger_holding(gateway_request_id: str | None) -> UsageAccountingService:
    """The existing usage ledger; holding another run's record of `gateway_request_id`, it refuses that request."""
    service = UsageAccountingService()
    if gateway_request_id is not None:
        service.record_gateway_usage(
            GatewayUsage(gateway_request_id=gateway_request_id, provider="p", billing_units=3, cost_usd=Decimal("0.009")),
            run_id="other:1", session_id="other", request_id="other:1:planning:1:1", occurred_at=EARLIER,
            service="agent.model", native_unit="tokens",
        )  # fmt: skip
    return service


def _settlement_holding(gateway_request_id: str | None) -> TurnSettlement:
    """The session settlement; having settled `gateway_request_id` differently, it refuses that request."""
    settlement = TurnSettlement()
    if gateway_request_id is not None:
        settlement.record_attempt(
            StageReceipt(
                session_id="s", turn_id="s:1", stage="summarization", attempt_id="earlier:1", gateway_request_id=gateway_request_id,
                outcome="completed", reported_cost_usd=Decimal("0.009"), recorded_at=EARLIER,
            )
        )
    return settlement


def _turn_sinks(settlement: TurnSettlement) -> dict:
    """The attached turn's settlement sinks, as acp/spec.py wires them."""
    return {
        "record_receipt": lambda receipt: settlement.record_attempt(receipt_from_maintenance(receipt)),
        "record_integrity_failure": lambda receipt: settlement.record_integrity_failure(receipt_from_maintenance(receipt).turn_id),
    }


class Summary:
    """One summarization through its production consumer: GatewaySummarizerCall -> HostMaintenance -> the attached
    turn's receipt sink, which offers each receipt to the attachment's usage ledger and to the session settlement,
    and tells the settlement of a ledger refusal."""

    def __init__(self, outcome, *, observer=log_provider_attempts, ledger_holds: str | None = None, settled: str | None = None) -> None:
        self.service = _ledger_holding(ledger_holds)
        self.settlement = _settlement_holding(settled)
        attachment = dataclasses.replace(make_attachment(), record_receipt=UsageLedgerAdapter(self.service).record_maintenance)
        self.turn = AttachedTurn.capture(
            attachment=attachment, session_key="s", records={}, approvals={}, generation=0, sanitizer=SANITIZER, strategy="compaction",
            mode=ExecutionMode.CHAT, checkpoint=None, current_prompt="now", turn_seq=1, cancelled=lambda: False, **_turn_sinks(self.settlement),
        )  # fmt: skip
        self.offered: list[MaintenanceReceipt] = []
        call = GatewaySummarizerCall(
            gateway_client=FakeGateway(outcome), model_id="fake/summarizer", session_id="s", request_ids=lambda: "req", attempt_observer=observer
        )
        self.host = HostMaintenance(call=call, sanitizer=SANITIZER, identity=SUMMARY_IDENTITY, record_receipt=self._offer, cancelled=lambda: False)

    def _offer(self, receipt: MaintenanceReceipt) -> None:
        self.offered.append(receipt)
        self.turn._receipt_sink(receipt)  # the attached turn's own sink, which production gives HostMaintenance

    def settle(self) -> tuple:
        """How the host settles: its status, or the accounting error it raises, by type, with its content-free notes."""
        try:
            return ("returned", self.host(SUMMARY_REQUEST).status, ())
        except Exception as error:  # noqa: BLE001 - the raised accounting error is the settled outcome
            return ("raised", type(error), tuple(getattr(error, "__notes__", ())))

    def accounting(self) -> tuple:
        """The session settlement's receipts and totals, and the usage ledger's entries."""
        receipts = [(r.attempt_id, r.gateway_request_id, r.outcome, r.reported_cost_usd, r.http_status) for r in self.settlement.receipts("s:1")]
        turn = self.settlement.settle_turn("s:1")
        totals = (turn.known_subtotal_usd, len(turn.unknown_attempt_ids), turn.integrity_failures, turn.complete)
        return receipts, totals, [(entry.gateway_request_id, entry.cost_usd) for entry in self.service.provider_ledger.entries]


def _settled(summary: Summary) -> tuple:
    return summary.settle(), summary.accounting()


# --- What the log holds -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
@pytest.mark.parametrize("mode", sorted(STAGES, key=str), ids=lambda mode: STAGES[mode][0])
def test_each_chat_and_planning_attempt_is_logged_content_free(tmp_path, mode, scenario) -> None:
    log = _trace(tmp_path)
    result, receipts = _run(tmp_path, mode, scenario)

    [record] = _records(log)
    assert record["data"] == {
        "stage": STAGES[mode][0], "run_id": "s:1", "session_id": "s", "settled_turn": 1, "wire_attempt": 1, "attempts": SCENARIOS[scenario][1],
        **SCENARIOS[scenario][2],
    }  # fmt: skip
    assert CANARY not in log.read_text(encoding="utf-8")
    # The log names exactly the attempts the receipts recorded, in order, with the same statuses.
    assert [(a["outcome"], a["upstream_http_status"] if a["routed"] else a["gateway_http_status"]) for a in record["data"]["attempts"]] == [
        (r.outcome, r.http_status) for r in receipts
    ]


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_each_summarization_attempt_is_logged_content_free(tmp_path, scenario) -> None:
    log = _trace(tmp_path)
    summary = Summary(SCENARIOS[scenario][0](SUMMARY_TEXT))
    summary.settle()

    [record] = _records(log)
    assert record["data"] == {"stage": "summary", "session_id": "s", "request_id": "req", "attempts": SCENARIOS[scenario][1], **SCENARIOS[scenario][2]}
    assert CANARY not in log.read_text(encoding="utf-8")
    # The log names exactly the attempts the host offered as receipts, in order, with the same statuses.
    assert [(a["outcome"], a["upstream_http_status"] if a["routed"] else a["gateway_http_status"]) for a in record["data"]["attempts"]] == [
        (r.outcome, r.http_status) for r in summary.offered
    ]


@pytest.mark.parametrize("status", ["429", True, 429.0], ids=["text", "bool", "float"])
def test_a_status_that_is_not_an_integer_is_logged_as_null_never_parsed(tmp_path, status) -> None:
    from optimus.gateway.attempts import ProviderAttempt

    log = _trace(tmp_path)
    attempt = ProviderAttempt(number=1, outcome="rejected", cost_usd=Decimal("0"), http_status=status, routed=True)
    log_provider_attempts(stage="answer", correlation=lambda: {}, attempts=(attempt,))
    [record] = _records(log)
    assert record["data"]["attempts"] == [_attempt("1", "rejected", True, None, None)]


def test_a_gateway_status_is_never_reported_as_an_upstream_status(tmp_path) -> None:
    log = _trace(tmp_path)
    _run(tmp_path, ExecutionMode.CHAT, "gateway-502-absent-route-metadata")
    [attempt] = _records(log)[0]["data"]["attempts"]
    assert (attempt["routed"], attempt["upstream_http_status"], attempt["gateway_http_status"]) == (False, None, 502)


# --- The Gateway summarizer only attaches its diagnostic -----------------------------------------------------------


def test_the_gateway_summarizer_attaches_its_diagnostic_without_running_it() -> None:
    calls: list[dict] = []

    def respond(observer) -> SummarizerResponse:
        call = GatewaySummarizerCall(
            gateway_client=FakeGateway(_recovered(SUMMARY_TEXT)), model_id="fake/summarizer", session_id="s", request_ids=lambda: "req",
            attempt_observer=observer,
        )  # fmt: skip
        return call(prompt="P", max_output_tokens=9)

    observed, plain = respond(lambda **kwargs: calls.append(kwargs)), respond(None)
    assert calls == []  # building the response runs nothing
    assert plain.diagnostic is None and SummarizerResponse(None, None, ()).diagnostic is None  # existing construction unchanged
    assert observed == plain and repr(observed) == repr(plain)  # never one of the response's facts

    assert observed.diagnostic is not None
    observed.diagnostic()
    [kwargs] = calls
    assert (kwargs["stage"], kwargs["correlation"](), [a.key for a in kwargs["attempts"]]) == ("summary", {"session_id": "s", "request_id": "req"}, ["1", "2"])


# --- Disabled tracing ---------------------------------------------------------------------------------------------


def test_disabled_tracing_does_no_diagnostic_work(tmp_path) -> None:
    _trace(tmp_path, enabled=False)

    class Untouchable:
        def __iter__(self):
            raise AssertionError("attempts were read with tracing disabled")

    def correlation():
        raise AssertionError("the correlation was built with tracing disabled")

    log_provider_attempts(stage="answer", correlation=correlation, attempts=Untouchable())
    _run(tmp_path, ExecutionMode.CHAT, "429-then-403")
    Summary(_rejected_twice(429, 403)).settle()
    assert not (tmp_path / "trace").exists()


# --- A diagnostic failure never changes the run -------------------------------------------------------------------


def _fail(kind: str, monkeypatch: pytest.MonkeyPatch, log: Path) -> None:
    if kind == "supplier":
        monkeypatch.setattr(debug_trace, "_attempt_fields", lambda attempt: (_ for _ in ()).throw(RuntimeError(CANARY)))
    elif kind == "redaction":
        monkeypatch.setattr(debug_trace, "redact_for_telemetry", lambda value: (_ for _ in ()).throw(RuntimeError(CANARY)))
    else:
        log.mkdir(parents=True)  # the log path is a directory: the write fails


@pytest.mark.parametrize("kind", ["supplier", "redaction", "write"])
@pytest.mark.parametrize("mode", sorted(STAGES, key=str), ids=lambda mode: STAGES[mode][0])
def test_a_diagnostic_failure_keeps_the_result_costs_and_receipts(tmp_path, monkeypatch, mode, kind) -> None:
    baseline_result, baseline_receipts = _run(tmp_path / "off", mode, "429-then-403", observer=None)
    log = _trace(tmp_path)
    _fail(kind, monkeypatch, log)
    result, receipts = _run(tmp_path, mode, "429-then-403")

    assert _outcome(result) == _outcome(baseline_result)
    assert _receipt_facts(receipts) == _receipt_facts(baseline_receipts)
    assert not log.is_file() or not _records(log)


@pytest.mark.parametrize("kind", ["supplier", "redaction", "write"])
def test_a_diagnostic_failure_keeps_the_summary_outcome_and_accounting(tmp_path, monkeypatch, kind) -> None:
    baseline = _settled(Summary(_recovered(SUMMARY_TEXT), observer=None))
    log = _trace(tmp_path)
    _fail(kind, monkeypatch, log)
    assert _settled(Summary(_recovered(SUMMARY_TEXT))) == baseline
    assert not log.is_file() or not _records(log)


def test_an_observer_that_raises_never_changes_the_run(tmp_path) -> None:
    def broken(**_kwargs):
        raise RuntimeError(CANARY)

    baseline_result, baseline_receipts = _run(tmp_path / "off", ExecutionMode.CHAT, "429-then-403", observer=None)
    result, receipts = _run(tmp_path, ExecutionMode.CHAT, "429-then-403", observer=broken)
    assert (_outcome(result), _receipt_facts(receipts)) == (_outcome(baseline_result), _receipt_facts(baseline_receipts))
    assert _settled(Summary(_rejected_twice(429, 403), observer=broken)) == _settled(Summary(_rejected_twice(429, 403), observer=None))


def _cancel(**_kwargs):
    raise asyncio.CancelledError


def test_a_chat_cancellation_propagates_after_every_receipt_is_kept(tmp_path) -> None:
    _, baseline_receipts = _run(tmp_path / "off", ExecutionMode.CHAT, "429-then-403", observer=None)
    receipts: list[StageReceipt] = []
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Change the greeting.", workspace_root=tmp_path, execution_mode=ExecutionMode.CHAT)
    runner = AgentRunner(gateway_client=FakeGateway(_rejected_twice(429, 403)), model="fake/model", provider_attempt_observer=_cancel)
    with pytest.raises(asyncio.CancelledError):
        runner.run(request, stage_receipts=receipts.append)
    assert _receipt_facts(receipts) == _receipt_facts(baseline_receipts)  # the runner observes after every receipt is kept


# --- Summary receipts are offered before the diagnostic runs (Codex review M1, 2026-10-14) ------------------------


def _uncertain_after_a_429() -> GatewayHttpError:
    """Realistic: one recoverable 429, then an uncertain attempt; the Gateway stops and reports it."""
    return GatewayHttpError(
        502, CANARY, gateway_code="UPSTREAM_ATTEMPT_UNCERTAIN", retryable=False,
        route_attempts=(_routed(1, "rejected", 429), _routed(2, "uncertain")),
    )  # fmt: skip


def _unattributable_after_a_429() -> GatewayResponse:
    """The settled usage names no completed attempt: an accounting integrity error that still carries a known charge."""
    return GatewayResponse(
        output_text=SUMMARY_TEXT, gateway_usage=_usage("gw-9"), raw={}, finish_reason="stop",
        route_attempts=(_routed(1, "rejected", 429), _routed(2, "completed")),
    )  # fmt: skip


def _stress_mixture() -> GatewayResponse:
    """An adversarial host-parser and accounting stress fixture, NOT a possible live sequence and no eligibility
    proof: the enforced Gateway makes at most two attempts and never resends after an uncertain one. It puts a
    not-sent, a rejected, an uncertain and a charged attempt in one report."""
    return GatewayResponse(
        output_text=SUMMARY_TEXT, gateway_usage=_usage("gw-4"), raw={}, finish_reason="stop",
        route_attempts=(_routed(1, "not_sent"), _routed(2, "rejected", 429), _routed(3, "uncertain"), _routed(4, "completed")),
    )  # fmt: skip


CHARGE = Decimal("0.0003")
# Each case: the Gateway's report, which sink already holds a request (and so refuses it), how the host settles
# without a diagnostic, and the session settlement's totals: known subtotal, unknown attempts, integrity failures,
# complete.
CASES = {
    "429-then-charged-completion": (lambda: _recovered(SUMMARY_TEXT), {}, ("returned", "completed", ()), (CHARGE, 0, 0, True)),
    "429-then-uncertain-failure": (_uncertain_after_a_429, {}, ("returned", "failed", ()), (Decimal("0"), 1, 0, False)),
    "unattributable-integrity-error": (_unattributable_after_a_429, {}, ("raised", AttemptIntegrityError, ()), (CHARGE, 1, 1, False)),
    "settlement-refuses-the-charge": (
        lambda: _recovered(SUMMARY_TEXT), {"settled": "gw-2"}, ("raised", ReceiptConflictError, ()), (Decimal("0.009"), 0, 1, False),
    ),
    "ledger-refusal-beside-integrity-error": (
        _unattributable_after_a_429, {"ledger_holds": "gw-9"},
        ("raised", DuplicateGatewayRequestError, ("accounting also failed: AttemptIntegrityError",)), (CHARGE, 1, 2, False),
    ),
    "stress-four-attempt-mixture": (_stress_mixture, {}, ("returned", "completed", ()), (CHARGE, 1, 0, False)),
}  # fmt: skip


@pytest.mark.parametrize("case", sorted(CASES))
def test_a_summary_cancellation_propagates_only_after_every_receipt_is_settled(monkeypatch, case) -> None:
    report, holds, settles, totals = CASES[case]
    baseline = Summary(report(), observer=None, **holds)
    assert baseline.settle() == settles
    assert baseline.accounting()[1] == totals

    selected: list[BaseException] = []
    select = maintenance.first_error
    monkeypatch.setattr(maintenance, "first_error", lambda errors: selected.append(select(errors)) or selected[-1])
    summary = Summary(report(), observer=_cancel, **holds)
    with pytest.raises(asyncio.CancelledError) as cancelled:
        summary.host(SUMMARY_REQUEST)

    # Every receipt, known charge, unknown cost and integrity failure is settled before the cancellation escapes.
    assert summary.accounting() == baseline.accounting()
    assert len(summary.offered) == len(baseline.offered)
    if settles[0] == "raised":
        # The accounting error it overtook stays attached: the very object the host selected, with its notes.
        [error] = selected
        assert cancelled.value.__context__ is error
        assert (type(error), tuple(getattr(error, "__notes__", ()))) == settles[1:]
    else:
        assert selected == [] and cancelled.value.__context__ is None


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_summary_diagnostic_runs_once_after_every_receipt_is_offered(tmp_path, case) -> None:
    report, holds, settles, _ = CASES[case]
    log = _trace(tmp_path)
    seen: list[int] = []

    def observer(**kwargs):
        seen.append(len(summary.offered))
        log_provider_attempts(**kwargs)

    summary = Summary(report(), observer=observer, **holds)
    baseline = Summary(report(), observer=None, **holds)
    assert summary.settle() == baseline.settle() == settles
    assert summary.accounting() == baseline.accounting()
    assert seen == [len(baseline.offered)]
    [record] = _records(log)
    assert [a["outcome"] for a in record["data"]["attempts"]] == [r.outcome for r in baseline.offered]


@pytest.mark.parametrize("case", sorted(CASES))
def test_an_ordinary_summary_diagnostic_failure_changes_no_outcome_or_accounting(case) -> None:
    def broken(**_kwargs):
        raise RuntimeError(CANARY)

    report, holds, settles, _ = CASES[case]
    summary, baseline = Summary(report(), observer=broken, **holds), Summary(report(), observer=None, **holds)
    assert summary.settle() == baseline.settle() == settles
    assert summary.accounting() == baseline.accounting()


def test_an_attached_turn_keeps_its_summary_charge_and_refusal_when_the_diagnostic_cancels() -> None:
    """The whole attached turn: its ledger refuses the summary's charge, its session settlement keeps the charge and
    is told of the refusal, and a cancelling diagnostic propagates with that refusal attached."""

    def prepare(observer):
        settlement, service = TurnSettlement(), _ledger_holding("gw-2")
        call = GatewaySummarizerCall(
            gateway_client=FakeGateway(_recovered(SUMMARY_TEXT)), model_id="m", session_id="s", request_ids=lambda: "r", attempt_observer=observer
        )
        attachment = dataclasses.replace(
            make_attachment(tail=10), summarizer=lambda identity, deliver: call, record_receipt=UsageLedgerAdapter(service).record_maintenance
        )
        records = {seq: ConversationTurn(f"q{seq} " + "w " * 200, "", "a " * 200, ConversationOutcome.COMPLETED, EffectState.NONE) for seq in (1, 2, 3)}
        turn = AttachedTurn.capture(
            attachment=attachment, session_key="s", records=records, approvals={}, generation=3, sanitizer=SANITIZER, strategy="compaction",
            mode=ExecutionMode.CHAT, checkpoint=None, current_prompt="now", turn_seq=4, cancelled=lambda: False, **_turn_sinks(settlement),
        )  # fmt: skip
        return turn, settlement

    turn, settlement = prepare(None)
    with pytest.raises(DuplicateGatewayRequestError):
        turn.prepare()
    summary = settlement.settle_turn("s:4")
    baseline = (summary.known_subtotal_usd, summary.complete, summary.integrity_failures, summary.receipt_ids)
    assert baseline[:3] == (CHARGE, False, 1)

    turn, settlement = prepare(_cancel)
    with pytest.raises(asyncio.CancelledError) as cancelled:
        turn.prepare()
    summary = settlement.settle_turn("s:4")
    assert (summary.known_subtotal_usd, summary.complete, summary.integrity_failures, summary.receipt_ids) == baseline
    assert isinstance(cancelled.value.__context__, DuplicateGatewayRequestError)
    assert cancelled.value.__context__ is turn._sink_error  # the refusal the turn holds, not a stand-in
