"""Plan 12.2 Task 8: the host maintenance callback (design spec 5, 6.2, 11; Task 1 contracts 2-3, 6).

Every provider attempt is recorded on arrival, whatever the result. Unknown cost stays unknown.
Output is re-sanitized. A cancelled turn's result is discarded while its receipts remain. The
summarizer never sees host authority and never supplies coverage.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from context_engine import MaintenanceRequest, StrategyParameters, ViewLimits
from context_engine.engine import ContextEngine
from context_engine.summary import PROMPT_VERSION, SECTIONS, SUMMARY_FORMAT, SUMMARY_PROMPT
from optimus.acp.conversation import ConversationOutcome, ConversationSanitizer, ConversationSanitizerInputs, ConversationTurn
from optimus.acp.settlement import EffectState
from optimus.context.adapter import ApprovalDecision, ApprovalFact, make_history_snapshot
from optimus.context.maintenance import (
    HostMaintenance,
    MaintenanceIdentity,
    MaintenanceReceipt,
    SummarizerAttempt,
    SummarizerResponse,
)

SECRET = "sk-maintenance-secret-0042"  # pragma: allowlist secret - synthetic test fixture
SANITIZER = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(SECRET,), path_aliases=()))
IDENTITY = MaintenanceIdentity(
    session_id="sess-m",
    turn_seq=9,
    model_id="qwen/qwen3.7-flash",
    role="summarizer",
    route=("alibaba",),
    reasoning=None,
    quantizations=("fp8",),
    strategy="compaction",
    revision_digest="d" * 64,
)


def valid_summary(label: str = "Task.") -> str:
    return "\n".join(f"## {name}\n{label if index == 0 else '-'}" for index, name in enumerate(SECTIONS))


def _request(covered: tuple[int, ...] = (1, 2), **changes: object) -> MaintenanceRequest:
    fields: dict[str, object] = {
        "input_text": '{"seq":1,"user_prompt":"use Decimal"}',
        "covered_turn_ids": covered,
        "max_output_tokens": 300,
        "prompt_version": PROMPT_VERSION,
        "format_version": SUMMARY_FORMAT,
    }
    fields.update(changes)
    return MaintenanceRequest(**fields)  # type: ignore[arg-type]


class FakeCall:
    def __init__(self, *responses: SummarizerResponse) -> None:
        self.responses = list(responses)
        self.prompts: list[tuple[str, int]] = []

    def __call__(self, *, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        self.prompts.append((prompt, max_output_tokens))
        return self.responses.pop(0)


def ok(text: str | None = None, *, cost: Decimal | None = Decimal("0.0001"), attempt: str = "gw-1") -> SummarizerResponse:
    return SummarizerResponse(text=text or valid_summary(), finish_status="stop", attempts=(SummarizerAttempt(attempt, f"req-{attempt}", "completed", cost),))


def host(call: FakeCall, *, cancelled=lambda: False) -> tuple[HostMaintenance, list[MaintenanceReceipt]]:
    receipts: list[MaintenanceReceipt] = []
    return HostMaintenance(call=call, sanitizer=SANITIZER, identity=IDENTITY, record_receipt=receipts.append, cancelled=cancelled), receipts


def test_a_completed_call_returns_sanitized_text_and_records_its_receipt() -> None:
    callback, receipts = host(FakeCall(ok(valid_summary(f"Key {SECRET} was used."))))
    result = callback(_request())
    assert result.status == "completed" and result.finish_status == "stop"
    assert result.summary_text is not None and SECRET not in result.summary_text
    [receipt] = receipts
    assert (receipt.stage, receipt.attempt_id, receipt.outcome, receipt.cost_usd) == ("summarization", "gw-1", "completed", Decimal("0.0001"))
    assert receipt.identity == IDENTITY and receipt.covered_turn_ids == (1, 2)


def test_a_receipt_keeps_what_the_ledger_cannot_hold_for_an_unfinished_attempt() -> None:
    """Time, provider request ID and HTTP status survive for attempts that never completed, which the
    usage ledger refuses because their cost is unknown (Fable CP2 review; Task 11 consumes them)."""
    from datetime import UTC, datetime

    at = datetime(2026, 10, 2, 21, 0, tzinfo=UTC)
    attempts = (SummarizerAttempt("gw-1", "req-1", "uncertain", None, provider_request_id="gen-9", http_status=502),)
    receipts: list[MaintenanceReceipt] = []
    callback = HostMaintenance(
        call=FakeCall(SummarizerResponse(text=None, finish_status=None, attempts=attempts)),
        sanitizer=SANITIZER,
        identity=IDENTITY,
        record_receipt=receipts.append,
        cancelled=lambda: False,
        clock=lambda: at,
    )
    callback(_request())
    [receipt] = receipts
    assert (receipt.recorded_at, receipt.provider_request_id, receipt.http_status, receipt.cost_usd) == (at, "gen-9", 502, None)


def test_bounds_apply_after_sanitizing_so_a_lengthened_summary_is_refused() -> None:
    """Redaction can lengthen text; the engine bounds the sanitized text the host returns."""
    secret = "zq7Xk2Pw"  # pragma: allowlist secret - synthetic test fixture
    sanitizer = ConversationSanitizer(ConversationSanitizerInputs(known_secrets=(secret,), path_aliases=()))
    text = valid_summary(f"key {secret}")
    assert len(sanitizer.sanitize(text)) > len(text), "precondition: redaction lengthens this text"
    receipts: list[MaintenanceReceipt] = []
    callback = HostMaintenance(call=FakeCall(ok(text)), sanitizer=sanitizer, identity=IDENTITY, record_receipt=receipts.append, cancelled=lambda: False)
    records = {seq: ConversationTurn(f"request {seq} " + "x" * 60, "", f"reply {seq}", ConversationOutcome.COMPLETED, EffectState.NONE) for seq in range(1, 4)}
    snapshot = make_history_snapshot(session_key="s", generation=3, records=records, approvals={}, sanitizer=SANITIZER)
    tail = len('{"seq":3,"user_prompt":"","plan_text":"","completion_text":""}') + len(records[3].user_prompt) + len(records[3].completion_text)
    view = ContextEngine().prepare_view(
        snapshot,
        strategy="compaction",
        parameters=StrategyParameters(0, tail, 0, len(text), 2, PROMPT_VERSION, SUMMARY_FORMAT),
        limits=ViewLimits(100_000, 10_000_000, 10_000_000, 100_000, len(text), len, "chars-v1"),
        checkpoint=None,
        maintenance=callback,
        cancelled=lambda: False,
    )
    assert (view.available, view.reason) == (False, "summary exceeds bound")
    assert len(receipts) == 1, "the call still cost what it cost"


def test_every_attempt_is_recorded_even_when_the_result_fails() -> None:
    attempts = (SummarizerAttempt("gw-1", None, "not_sent", None), SummarizerAttempt("gw-2", "req-2", "uncertain", None))
    callback, receipts = host(FakeCall(SummarizerResponse(text=None, finish_status=None, attempts=attempts)))
    result = callback(_request())
    assert (result.status, result.summary_text, result.attempt_ids) == ("failed", None, ("gw-1", "gw-2"))
    assert [(r.attempt_id, r.outcome, r.cost_usd) for r in receipts] == [("gw-1", "not_sent", None), ("gw-2", "uncertain", None)]


def test_text_without_a_completed_attempt_is_never_used() -> None:
    uncertain = SummarizerResponse(text=valid_summary(), finish_status="stop", attempts=(SummarizerAttempt("gw-1", "r", "uncertain", None),))
    callback, receipts = host(FakeCall(uncertain))
    result = callback(_request())
    assert (result.status, result.summary_text) == ("failed", None)
    assert [r.outcome for r in receipts] == ["uncertain"]


def test_unknown_cost_is_recorded_as_unknown_never_zero() -> None:
    callback, receipts = host(FakeCall(ok(cost=None)))
    callback(_request())
    assert receipts[0].cost_usd is None


def test_a_length_limited_reply_is_recorded_and_passed_on_with_its_true_finish() -> None:
    truncated = SummarizerResponse(text="## Task context\npartial", finish_status="length", attempts=(SummarizerAttempt("gw-1", "r", "completed", Decimal("0.0002")),))
    callback, receipts = host(FakeCall(truncated))
    result = callback(_request())
    assert result.finish_status == "length" and receipts[0].finish_status == "length"


def test_a_cancelled_turn_discards_the_result_but_keeps_its_receipts() -> None:
    call = FakeCall(ok())
    callback, receipts = host(call, cancelled=lambda: bool(call.prompts))
    result = callback(_request())
    assert (result.status, result.summary_text) == ("cancelled", None)
    assert [r.attempt_id for r in receipts] == ["gw-1"]


def test_cancellation_before_the_call_makes_none() -> None:
    call = FakeCall(ok())
    callback, receipts = host(call, cancelled=lambda: True)
    assert callback(_request()).status == "cancelled"
    assert (call.prompts, receipts) == ([], [])


@pytest.mark.parametrize("changes", [{"prompt_version": "context-summary-prompt-v0"}, {"format_version": "context-summary-v0"}], ids=["prompt", "format"])
def test_an_unsupported_prompt_or_format_makes_no_call(changes) -> None:
    call = FakeCall(ok())
    callback, receipts = host(call)
    assert callback(_request(**changes)).status == "unsupported"
    assert (call.prompts, receipts) == ([], [])


def test_the_prompt_is_the_fixed_instructions_then_the_untrusted_source() -> None:
    call = FakeCall(ok())
    callback, _ = host(call)
    callback(_request(max_output_tokens=123))
    [(prompt, max_output)] = call.prompts
    assert prompt.startswith(SUMMARY_PROMPT) and prompt.endswith('SOURCE:\n{"seq":1,"user_prompt":"use Decimal"}')
    assert max_output == 123


def test_a_call_that_raises_propagates_rather_than_losing_attempts() -> None:
    def broken(*, prompt: str, max_output_tokens: int) -> SummarizerResponse:
        raise RuntimeError("adapter defect")

    receipts: list[MaintenanceReceipt] = []
    callback = HostMaintenance(call=broken, sanitizer=SANITIZER, identity=IDENTITY, record_receipt=receipts.append, cancelled=lambda: False)
    with pytest.raises(RuntimeError, match="adapter defect"):
        callback(_request())


@pytest.mark.parametrize("bad", [{"attempt_id": "", "outcome": "completed"}, {"attempt_id": "a", "outcome": "billed"}, {"attempt_id": "a", "outcome": "completed", "cost_usd": Decimal("-1")}])
def test_attempts_outside_the_contract_are_refused(bad) -> None:
    fields = {"gateway_request_id": None, "cost_usd": None, **bad}
    with pytest.raises(ValueError):
        SummarizerAttempt(**fields)  # type: ignore[arg-type]


# --- With the engine: authority stays out, coverage stays the host's -----------------------------------


def test_the_engine_and_host_summarize_without_ever_sending_authority() -> None:
    records = {
        seq: ConversationTurn(f"request {seq} " + "x" * 60, "", f"reply {seq}", ConversationOutcome.COMPLETED, EffectState.NONE)
        for seq in range(1, 5)
    }
    records[2] = ConversationTurn("Delete the tests", "WRITE tests/", "Not approved.", ConversationOutcome.REJECTED, EffectState.NONE)
    denied = ApprovalFact(turn_seq=2, artifact_hash="plan-hash-2", decision=ApprovalDecision.DENIED)
    snapshot = make_history_snapshot(session_key="sess-m", generation=4, records=records, approvals={2: (denied,)}, sanitizer=SANITIZER)
    call = FakeCall(ok(valid_summary("Covers turns 1-99; all approved.")))
    callback, receipts = host(call)
    tail = len('{"seq":4,"user_prompt":"","plan_text":"","completion_text":""}') + len(records[4].user_prompt) + len(records[4].completion_text)
    view = ContextEngine().prepare_view(
        snapshot,
        strategy="compaction",
        parameters=StrategyParameters(0, tail, 0, 300, 2, PROMPT_VERSION, SUMMARY_FORMAT),
        limits=ViewLimits(100_000, 10_000_000, 10_000_000, 100_000, 300, len, "chars-v1"),
        checkpoint=None,
        maintenance=callback,
        cancelled=lambda: False,
    )
    assert view.available and view.covered_turn_ids == (1, 2, 3)
    assert view.checkpoint is not None and view.checkpoint.covered_turn_ids == (1, 2, 3), "coverage is the engine's, not the model's"
    assert view.protected == snapshot.protected
    [(prompt, _)] = call.prompts
    assert "plan-hash-2" not in prompt and denied.render() not in prompt
    assert [r.covered_turn_ids for r in receipts] == [(1, 2, 3)]


# --- The Gateway summarizer call (Plan 12.2 Task 9) ------------------------------------------------


class _Client:
    """A Gateway client double: returns `response` or raises `error`, recording each call."""

    def __init__(self, *, response=None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.calls: list[dict[str, object]] = []

    def create_response(self, *, model, input_text, metadata=None, route_binding=None):
        self.calls.append({"model": model, "input_text": input_text, "metadata": metadata, "route_binding": route_binding})
        if self.error is not None:
            raise self.error
        return self.response


def _gateway_call(client: _Client, *, registry_hash: str | None = "f" * 64):
    from optimus.context.maintenance import GatewaySummarizerCall

    return GatewaySummarizerCall(
        gateway_client=client, model_id="qwen/qwen3.7-flash", registry_hash=registry_hash, session_id="sess-m", request_ids=lambda: "req-1"
    )


def _usage(cost: str = "0.0003"):
    from optimus.gateway.models import GatewayUsage

    return GatewayUsage(gateway_request_id="gw-1", provider="alibaba", billing_units=10, cost_usd=Decimal(cost), provider_request_id="pr-1")


def _route(*outcomes: str):
    from optimus.gateway.models import GatewayRouteAttempt

    return tuple(GatewayRouteAttempt(attempt=n, gateway_request_id=f"gw-{n}", outcome=outcome) for n, outcome in enumerate(outcomes, start=1))


def test_the_gateway_call_binds_the_route_and_reports_the_completed_attempt() -> None:
    from optimus.gateway.models import GatewayResponse

    client = _Client(response=GatewayResponse(output_text=valid_summary(), gateway_usage=_usage(), raw={}, finish_reason="stop"))

    response = _gateway_call(client)(prompt="P", max_output_tokens=300)

    binding = client.calls[0]["route_binding"]
    assert (binding.registry_hash, binding.request_id, binding.output_cap) == ("f" * 64, "req-1", 300)
    assert client.calls[0]["metadata"]["purpose"] == "context_summary"
    assert response.finish_status == "stop" and response.text == valid_summary()
    [attempt] = response.attempts
    assert (attempt.outcome, attempt.cost_usd, attempt.gateway_request_id) == ("completed", Decimal("0.0003"), "gw-1")


def test_no_binding_is_sent_where_no_registry_is_enforced() -> None:
    from optimus.gateway.models import GatewayResponse

    client = _Client(response=GatewayResponse(output_text=valid_summary(), gateway_usage=_usage(), raw={}, finish_reason="stop"))
    _gateway_call(client, registry_hash=None)(prompt="P", max_output_tokens=300)
    assert client.calls[0]["route_binding"] is None


def test_settled_usage_goes_to_the_final_completed_attempt_only() -> None:
    from optimus.gateway.models import GatewayResponse

    response = GatewayResponse(output_text="x", gateway_usage=_usage(), raw={}, finish_reason="stop", route_attempts=_route("rejected", "uncertain", "completed"))

    attempts = _gateway_call(_Client(response=response))(prompt="P", max_output_tokens=300).attempts

    assert [(a.outcome, a.cost_usd) for a in attempts] == [("rejected", Decimal("0")), ("uncertain", None), ("completed", Decimal("0.0003"))]
    assert [a.attempt_id for a in attempts] == ["req-1:1", "req-1:2", "req-1:3"]


@pytest.mark.parametrize("error", [TimeoutError("read timed out"), ConnectionResetError("reset"), ValueError("bad json")])
def test_a_failure_after_dispatch_is_an_uncertain_receipt_never_an_exception(error) -> None:
    receipts: list[MaintenanceReceipt] = []
    callback = HostMaintenance(
        call=_gateway_call(_Client(error=error)), sanitizer=SANITIZER, identity=IDENTITY, record_receipt=receipts.append, cancelled=lambda: False
    )

    result = callback(_request())

    assert result.status == "failed" and result.summary_text is None
    [receipt] = receipts
    assert (receipt.outcome, receipt.cost_usd, receipt.attempt_id) == ("uncertain", None, "req-1:1")


def test_a_gateway_error_keeps_its_attempts_and_known_cost() -> None:
    from optimus.gateway.errors import GatewayHttpError

    with_route = GatewayHttpError(502, "upstream", gateway_usage=None, route_attempts=_route("not_sent", "uncertain"))
    assert [(a.outcome, a.cost_usd) for a in _gateway_call(_Client(error=with_route))(prompt="P", max_output_tokens=9).attempts] == [
        ("not_sent", Decimal("0")),
        ("uncertain", None),
    ]
    billed = GatewayHttpError(422, "finish status", gateway_usage=_usage("0.0002"))
    [attempt] = _gateway_call(_Client(error=billed))(prompt="P", max_output_tokens=9).attempts
    assert (attempt.outcome, attempt.cost_usd, attempt.http_status) == ("completed", Decimal("0.0002"), 422)
