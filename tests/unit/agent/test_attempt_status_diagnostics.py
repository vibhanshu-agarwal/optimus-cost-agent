"""Plan 12.2 r4 stop diagnosis (Codex disposition 2026-10-13, operator-approved): the host keeps every provider
attempt's status in the opt-in ACP debug log, content-free, for Chat, planning and summarization.

r4's A1 failed after two Gateway attempts whose statuses the host had parsed and then dropped. Each classified
attempt is now logged with its call correlation, stage, ordered key, fixed-vocabulary outcome, whether the
Gateway routed it, and an integer-or-null status: the upstream status only for a routed attempt, the outer
host-to-Gateway status otherwise (a Gateway 502 is never evidence of an upstream 502); an unknown status stays
null. Nothing else: no bodies, headers, error text, keys, provider error types or identifiers. With tracing
disabled no diagnostic work happens, and a diagnostic failure never changes a result, a receipt or a
cancellation. Fake Gateway responses only: no service, no provider.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp import debug_trace
from optimus.acp.debug_trace import configure_debug_trace, log_provider_attempts, reset_debug_trace_context
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.context.maintenance import GatewaySummarizerCall
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import GatewayResponse, GatewayRouteAttempt, GatewayUsage
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt

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
    return GatewayResponse(
        output_text=text, gateway_usage=_usage("gw-2"), raw={"echo": CANARY}, finish_reason="stop",
        route_attempts=(_routed(1, "rejected", 429), _routed(2, "completed")),
    )  # fmt: skip


def _attempt(key: str, outcome: str, routed: bool, upstream: int | None, gateway: int | None) -> dict:
    return {"attempt": key, "outcome": outcome, "routed": routed, "upstream_http_status": upstream, "gateway_http_status": gateway}


# Each scenario: what the fake Gateway does, and the attempts the log must hold (same for every stage).
SCENARIOS = {
    "429-then-403": (lambda text: _rejected_twice(429, 403), [_attempt("1", "rejected", True, 429, None), _attempt("2", "rejected", True, 403, None)]),
    "429-then-429": (lambda text: _rejected_twice(429, 429), [_attempt("1", "rejected", True, 429, None), _attempt("2", "rejected", True, 429, None)]),
    "429-then-success": (_recovered, [_attempt("1", "rejected", True, 429, None), _attempt("2", "completed", True, None, None)]),
    "transport-loss-no-status": (lambda text: ConnectionResetError(CANARY), [_attempt("1", "uncertain", False, None, None)]),
    "gateway-502-absent-route-metadata": (lambda text: GatewayHttpError(502, CANARY), [_attempt("1", "uncertain", False, None, 502)]),
    "gateway-502-malformed-route-metadata": (
        lambda text: GatewayHttpError(502, CANARY, gateway_code="UPSTREAM_ATTEMPT_REJECTED", retryable=False, route_attempts=(), route_attempts_malformed=True),
        [_attempt("1", "uncertain", False, None, 502)],
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
    make, _ = SCENARIOS[scenario]
    receipts: list[StageReceipt] = []
    gateway = FakeGateway(make(STAGES[mode][1]))
    request = AgentRunRequest(run_id="s:1", session_id="s", task=f"Change the greeting. {CANARY}", workspace_root=tmp_path, execution_mode=mode)
    result = AgentRunner(gateway_client=gateway, model="fake/model", provider_attempt_observer=observer).run(request, stage_receipts=receipts.append)
    return result, receipts


def _summarize(scenario: str, *, observer=log_provider_attempts):
    make, _ = SCENARIOS[scenario]
    call = GatewaySummarizerCall(
        gateway_client=FakeGateway(make("Summary.")), model_id="fake/summarizer", session_id="s", request_ids=lambda: "req", attempt_observer=observer
    )
    return call(prompt=f"Summarize. {CANARY}", max_output_tokens=9)


def _outcome(result) -> tuple:
    return (
        result.status, result.final_state, result.stop_reason, result.output_text, result.total_cost_usd,
        result.cost_complete, result.unknown_cost_attempt_count, result.mutation_count,
    )  # fmt: skip


def _receipt_facts(receipts: list[StageReceipt]) -> list[tuple]:
    return [(r.stage, r.attempt_id, r.outcome, r.reported_cost_usd, r.http_status) for r in receipts]


# --- What the log holds -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
@pytest.mark.parametrize("mode", sorted(STAGES, key=str), ids=lambda mode: STAGES[mode][0])
def test_each_chat_and_planning_attempt_is_logged_content_free(tmp_path, mode, scenario) -> None:
    log = _trace(tmp_path)
    result, receipts = _run(tmp_path, mode, scenario)

    [record] = _records(log)
    assert record["data"] == {
        "stage": STAGES[mode][0], "run_id": "s:1", "session_id": "s", "settled_turn": 1, "wire_attempt": 1, "attempts": SCENARIOS[scenario][1],
    }  # fmt: skip
    assert CANARY not in log.read_text(encoding="utf-8")
    # The log names exactly the attempts the receipts recorded, in order, with the same statuses.
    assert [(a["outcome"], a["upstream_http_status"] if a["routed"] else a["gateway_http_status"]) for a in record["data"]["attempts"]] == [
        (r.outcome, r.http_status) for r in receipts
    ]


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_each_summarization_attempt_is_logged_content_free(tmp_path, scenario) -> None:
    log = _trace(tmp_path)
    response = _summarize(scenario)

    [record] = _records(log)
    assert record["data"] == {"stage": "summary", "session_id": "s", "request_id": "req", "attempts": SCENARIOS[scenario][1]}
    assert CANARY not in log.read_text(encoding="utf-8")
    assert [a.outcome for a in response.attempts] == [a["outcome"] for a in record["data"]["attempts"]]


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
    _summarize("429-then-403")
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
def test_a_diagnostic_failure_keeps_the_summary_response(tmp_path, monkeypatch, kind) -> None:
    baseline = _summarize("429-then-success", observer=None)
    log = _trace(tmp_path)
    _fail(kind, monkeypatch, log)
    response = _summarize("429-then-success")
    assert response == baseline


def test_an_observer_that_raises_never_changes_the_run(tmp_path) -> None:
    def broken(**_kwargs):
        raise RuntimeError(CANARY)

    baseline_result, baseline_receipts = _run(tmp_path / "off", ExecutionMode.CHAT, "429-then-403", observer=None)
    result, receipts = _run(tmp_path, ExecutionMode.CHAT, "429-then-403", observer=broken)
    assert (_outcome(result), _receipt_facts(receipts)) == (_outcome(baseline_result), _receipt_facts(baseline_receipts))
    assert _summarize("429-then-403", observer=broken) == _summarize("429-then-403", observer=None)


def test_a_cancellation_still_propagates_and_every_receipt_is_kept_first(tmp_path) -> None:
    def cancelled(**_kwargs):
        raise asyncio.CancelledError

    _, baseline_receipts = _run(tmp_path / "off", ExecutionMode.CHAT, "429-then-403", observer=None)
    receipts: list[StageReceipt] = []
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Change the greeting.", workspace_root=tmp_path, execution_mode=ExecutionMode.CHAT)
    runner = AgentRunner(gateway_client=FakeGateway(_rejected_twice(429, 403)), model="fake/model", provider_attempt_observer=cancelled)
    with pytest.raises(asyncio.CancelledError):
        runner.run(request, stage_receipts=receipts.append)
    assert _receipt_facts(receipts) == _receipt_facts(baseline_receipts)  # diagnostics run after every record is kept
    with pytest.raises(asyncio.CancelledError):
        _summarize("429-then-403", observer=cancelled)
