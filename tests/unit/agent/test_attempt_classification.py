"""Codex CP3 ruling R3: one source-pinned classifier for every host call path (Task 1 contracts 6).

A proven Gateway preflight refusal - a known refusal code, not retryable, no route attempts, no usage -
is a rejection that cost exactly 0, through planning, Chat and summarization alike. Anything short of
that proof stays what it was: an unknown code, a retryable or ambiguous refusal, a failure after an
actual route attempt, FINISH_STATUS_UNVERIFIED and any failure with reported usage. An empty attempt
list alone proves nothing, and nothing is retried to resolve an uncertain cost.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.context.maintenance import GatewaySummarizerCall
from optimus.gateway.attempts import PREFLIGHT_REFUSAL_CODES, attempts_from_failure, is_preflight_refusal
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayRouteAttempt, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt

SRC = Path(__file__).resolve().parents[3] / "src"


def _usage(cost: str = "0.0003") -> GatewayUsage:
    return GatewayUsage(gateway_request_id="gw-used", provider="p", billing_units=3, cost_usd=Decimal(cost))


def _refusal(code: str) -> GatewayHttpError:
    return GatewayHttpError(400, "refused", gateway_code=code, retryable=False, route_attempts=())


# Each negative control and what every stage must settle it as: (outcome, cost) per attempt.
NEGATIVE_CONTROLS = {
    "unknown-code": (GatewayHttpError(400, "x", gateway_code="SOMETHING_NEW", retryable=False), [("uncertain", None)]),
    "retryable-refusal": (GatewayHttpError(400, "x", gateway_code="CAPACITY_REFUSED", retryable=True), [("uncertain", None)]),
    "ambiguous-refusal": (GatewayHttpError(400, "x", gateway_code="CAPACITY_REFUSED", retryable=None), [("uncertain", None)]),
    "no-code-no-usage": (GatewayHttpError(502, "x"), [("uncertain", None)]),
    "actual-route-attempt": (
        GatewayHttpError(
            502, "x", gateway_code="CAPACITY_REFUSED", retryable=False,
            route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="gw-1", outcome="uncertain"),),
        ),
        [("uncertain", None)],
    ),
    "finish-status-unverified": (
        GatewayHttpError(
            422, "x", gateway_code="FINISH_STATUS_UNVERIFIED", retryable=False, gateway_usage=_usage(),
            route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="gw-used", outcome="completed"),),
        ),
        [("completed", Decimal("0.0003"))],
    ),
    "failure-with-usage": (GatewayHttpError(502, "x", gateway_usage=_usage()), [("completed", Decimal("0.0003"))]),
    "response-error-without-usage": (GatewayResponseError("malformed"), [("uncertain", None)]),
    "transport-loss": (ConnectionResetError("reset"), [("uncertain", None)]),
}  # fmt: skip


class RaisingGateway:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def create_response(self, **kwargs):
        self.calls += 1
        raise self.error


def _run(tmp_path: Path, mode: ExecutionMode, error: BaseException):
    receipts: list[StageReceipt] = []
    gateway = RaisingGateway(error)
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Change the greeting.", workspace_root=tmp_path, execution_mode=mode)
    result = AgentRunner(gateway_client=gateway, model="fake/model").run(request, stage_receipts=receipts.append)
    return result, receipts, gateway


def _summarize(error: BaseException):
    call = GatewaySummarizerCall(gateway_client=RaisingGateway(error), model_id="fake/summarizer", session_id="s", request_ids=lambda: "req")
    return call(prompt="P", max_output_tokens=9)


# --- The classifier --------------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(PREFLIGHT_REFUSAL_CODES))
def test_every_preflight_code_is_a_zero_cost_rejection(code) -> None:
    error = _refusal(code)

    assert is_preflight_refusal(error)
    [attempt] = attempts_from_failure(error)
    assert (attempt.outcome, attempt.cost_usd, attempt.http_status) == ("rejected", Decimal("0"), 400)


@pytest.mark.parametrize("control", sorted(NEGATIVE_CONTROLS))
def test_nothing_short_of_proof_is_a_preflight_refusal(control) -> None:
    error, expected = NEGATIVE_CONTROLS[control]

    assert not is_preflight_refusal(error)
    assert [(a.outcome, a.cost_usd) for a in attempts_from_failure(error)] == expected


def test_the_preflight_codes_are_exactly_the_gateways_refusals_before_any_attempt() -> None:
    from optimus.context import maintenance

    sources = [
        SRC / "optimus_gateway" / "model_policy.py",
        SRC / "optimus_gateway" / "responses.py",
        SRC / "optimus_gateway" / "chat_completions.py",
        SRC / "optimus_model_policy" / "capacity.py",
        SRC / "optimus_model_policy" / "binding.py",
    ]
    pattern = re.compile(r'(?:ModelPolicyRefusal|_refuse|BindingError)\(\s*"([A-Z_]+)"|reason or "([A-Z_]+)"')
    codes = {match for path in sources for pair in pattern.findall(path.read_text(encoding="utf-8")) for match in pair if match}
    # Raised after a completed, billed attempt (with its usage), or only at launch: never a preflight refusal.
    assert PREFLIGHT_REFUSAL_CODES == codes - {"FINISH_STATUS_UNVERIFIED", "FIXTURE_POLICY"}
    assert maintenance.PREFLIGHT_REFUSAL_CODES is PREFLIGHT_REFUSAL_CODES  # one classifier, not a copy


def test_no_host_call_path_keeps_its_own_refusal_classifier() -> None:
    """Every stage imports the one classifier; none re-declares the code set or the predicate."""
    paths = [SRC / "optimus" / "agent" / "runner.py", SRC / "optimus" / "agent" / "planning_loop.py", SRC / "optimus" / "context" / "maintenance.py"]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "from optimus.gateway.attempts import" in text, path.name
        assert '"CAPACITY_REFUSED"' not in text and "gateway_code in" not in text, path.name


# --- Through planning, Chat and summarization -------------------------------------------------------


@pytest.mark.parametrize("code", sorted(PREFLIGHT_REFUSAL_CODES))
def test_a_preflight_refusal_through_planning_is_complete_at_zero(tmp_path, code) -> None:
    result, receipts, gateway = _run(tmp_path, ExecutionMode.AGENT, _refusal(code))

    assert [(r.stage, r.outcome, r.reported_cost_usd) for r in receipts] == [("planning", "rejected", Decimal("0"))]
    assert (result.stop_reason, result.cost_complete, result.total_cost_usd) == ("PLANNING_GATEWAY_REFUSED", True, Decimal("0"))
    assert gateway.calls == 1  # not retried


@pytest.mark.parametrize("code", sorted(PREFLIGHT_REFUSAL_CODES))
def test_a_preflight_refusal_through_chat_is_complete_at_zero(tmp_path, code) -> None:
    result, receipts, gateway = _run(tmp_path, ExecutionMode.CHAT, _refusal(code))

    assert [(r.stage, r.outcome, r.reported_cost_usd) for r in receipts] == [("answer", "rejected", Decimal("0"))]
    assert (result.stop_reason, result.cost_complete, result.total_cost_usd) == ("CHAT_GATEWAY_REFUSED", True, Decimal("0"))
    assert gateway.calls == 1


@pytest.mark.parametrize("code", sorted(PREFLIGHT_REFUSAL_CODES))
def test_a_preflight_refusal_through_summarization_is_complete_at_zero(code) -> None:
    [attempt] = _summarize(_refusal(code)).attempts

    assert (attempt.outcome, attempt.cost_usd) == ("rejected", Decimal("0"))


@pytest.mark.parametrize("mode", [ExecutionMode.AGENT, ExecutionMode.CHAT], ids=["planning", "chat"])
@pytest.mark.parametrize("control", sorted(NEGATIVE_CONTROLS))
def test_every_stage_settles_a_negative_control_the_same_way(tmp_path, mode, control) -> None:
    error, expected = NEGATIVE_CONTROLS[control]

    result, receipts, gateway = _run(tmp_path, mode, error)

    # A legacy failure with reported usage may be re-sent by the existing status-based retry; each
    # host attempt is then its own receipt, settled the same way.
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == expected * gateway.calls
    assert [(a.outcome, a.cost_usd) for a in _summarize(error).attempts] == expected
    unknown = any(cost is None for _, cost in expected)
    assert result.cost_complete is not unknown
    assert result.stop_reason not in {"PLANNING_GATEWAY_REFUSED", "CHAT_GATEWAY_REFUSED"}
    if unknown:
        # An uncertain cost is never resolved by sending again.
        assert gateway.calls == 1


# --- Attempt and receipt invariants ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"number": 0, "outcome": "completed", "cost_usd": Decimal("0.1")},
        {"number": 1, "outcome": "billed", "cost_usd": Decimal("0.1")},
        {"number": 1, "outcome": "not_sent", "cost_usd": Decimal("0.1")},
        {"number": 1, "outcome": "rejected", "cost_usd": None},
        {"number": 1, "outcome": "uncertain", "cost_usd": Decimal("0")},
        {"number": 1, "outcome": "uncertain", "cost_usd": None, "gateway_usage": _usage()},
        {"number": 1, "outcome": "completed", "cost_usd": Decimal("0.9"), "gateway_usage": _usage()},
    ],
    ids=["number", "outcome", "unsent-cost", "refused-unknown", "uncertain-zero", "uncertain-usage", "usage-cost-mismatch"],
)
def test_a_provider_attempt_refuses_an_impossible_combination(fields) -> None:
    from optimus.gateway.attempts import ProviderAttempt

    with pytest.raises(ValueError):
        ProviderAttempt(**fields)


@pytest.mark.parametrize(
    "changes",
    [{"outcome": "uncertain", "reported_cost_usd": None}, {"reported_cost_usd": Decimal("0.9")}, {"gateway_request_id": "gw-other"}],
    ids=["not-completed", "cost-mismatch", "request-mismatch"],
)
def test_a_receipt_carries_usage_only_for_the_attempt_it_settled(changes) -> None:
    from datetime import UTC, datetime

    fields = dict(
        session_id="s", turn_id="s:1", stage="planning", attempt_id="a", gateway_request_id="gw-used", outcome="completed",
        reported_cost_usd=Decimal("0.0003"), recorded_at=datetime(2026, 10, 3, tzinfo=UTC), gateway_usage=_usage(),
    )  # fmt: skip

    with pytest.raises(ValueError):
        StageReceipt(**{**fields, **changes})
