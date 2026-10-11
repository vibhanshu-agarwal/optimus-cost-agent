"""Plan 12.2 Task 13 (Stage C), Codex completion review R1: a Stage C guard refusal that dispatched nothing is
a zero-cost rejection through host accounting.

The real Gateway handler refuses under a real guard; its HTTP error body reaches the host through the host
client's own parsing (`urlopen` raising `HTTPError`), and planning, Chat and summarization settle the error
it raises. A refusal before any attempt is one rejected attempt at exactly 0, complete. A refusal after a
proven unbilled first attempt keeps that real attempt's identity, count and zero cost. Anything short of the
proof (retryable or unstated, a malformed attempt list, reported usage) is not a free request.
"""

from __future__ import annotations

import dataclasses
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

import optimus.gateway.client as gateway_client
import optimus_gateway.responses as gateway_responses
from optimus.gateway.attempts import PREFLIGHT_REFUSAL_CODES, attempts_from_failure, is_preflight_refusal
from optimus.gateway.client import GatewayRequest, UrllibGatewayTransport
from optimus.gateway.errors import GatewayHttpError
from optimus.runtime.modes import ExecutionMode
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UpstreamAttemptFailure
from optimus_model_policy import stage_c
from optimus_model_policy.binding import ATTEMPT_NOT_SENT, ATTEMPT_REJECTED
from tests.unit.agent.test_attempt_classification import _run, _summarize
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    RecordingUpstream,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
INPUT = "plan the change"


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


@pytest.fixture
def envelope_guard(tmp_path: Path):
    clock = Clock()
    path = stage_c.stage_c_ledger_path(tmp_path / "runtime")
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=clock)
    guard = stage_c.StageCGuard.open(path, envelope, clock=clock)
    yield model_policy(verified_snapshot(tmp_path)), guard, clock
    guard.close()


def _post(policy, guard, upstream) -> tuple[int, dict[str, Any]]:
    config = dataclasses.replace(gateway_config(policy), stage_c_guard=guard)
    return handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": INPUT, "route_binding": binding(policy.snapshot, input_text=INPUT, request_id="host-req")},
        config=config,
        upstream_client=upstream,
    )


def _host_error(status: int, body: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> GatewayHttpError:
    """The host client's own parsing of the Gateway's HTTP error body."""

    def refuse(request, timeout):
        raise HTTPError(request.full_url, status, "refused", None, io.BytesIO(json.dumps(body, default=str).encode("utf-8")))

    monkeypatch.setattr(gateway_client, "urlopen", refuse)
    with pytest.raises(GatewayHttpError) as caught:
        UrllibGatewayTransport().post_json(GatewayRequest("POST", "http://127.0.0.1:8765/v1/responses", {}, {}))
    return caught.value


def _exhaust_budget(guard, clock) -> None:
    guard.settle_charged(guard.admit(attempt_id="gw-" + "0" * 32, request_id="earlier", reserve_usd=Decimal("0.495")), Decimal("0.495"))


def _exhaust_attempts(guard, clock) -> None:
    for n in range(stage_c.STAGE_C_MAX_ATTEMPTS):
        guard.settle_unbilled(guard.admit(attempt_id=f"gw-{n:032d}", request_id="earlier", reserve_usd=Decimal("0.001")), ATTEMPT_NOT_SENT)


def _exhaust_window(guard, clock) -> None:
    clock.now = guard.state.deadline - timedelta(seconds=30)  # an attempt could no longer time out inside it


def _leave_in_flight(guard, clock) -> None:
    guard.admit(attempt_id="gw-" + "1" * 32, request_id="other", reserve_usd=Decimal("0.001"))


def _halt(guard, clock) -> None:
    guard.settle_unknown(guard.admit(attempt_id="gw-" + "2" * 32, request_id="earlier", reserve_usd=Decimal("0.001")), "unknown")


def _fail_writes(guard, clock, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(handle, record, fsync):
        raise OSError("disk full")

    monkeypatch.setattr(stage_c, "_write_record", broken)


REFUSALS = {
    "STAGE_C_BUDGET_EXHAUSTED": _exhaust_budget,
    "STAGE_C_ATTEMPTS_EXHAUSTED": _exhaust_attempts,
    "STAGE_C_WINDOW_EXHAUSTED": _exhaust_window,
    "STAGE_C_ATTEMPT_IN_FLIGHT": _leave_in_flight,
    "STAGE_C_HALTED": _halt,
    "STAGE_C_LEDGER_WRITE_FAILED": _fail_writes,
}


def _refused(code: str, envelope_guard, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], GatewayHttpError]:
    policy, guard, clock = envelope_guard
    prepare = REFUSALS[code]
    if prepare is _fail_writes:
        prepare(guard, clock, monkeypatch)
    else:
        prepare(guard, clock)
    upstream = RecordingUpstream()
    status, body = _post(policy, guard, upstream)
    assert (status, body["code"], body["retryable"], body["route_attempts"]) == (503, code, False, [])
    assert upstream.calls == [] and "gateway_usage" not in body  # it reached no provider
    return body, _host_error(status, body, monkeypatch)


def test_every_guard_refusal_is_a_preflight_code() -> None:
    assert set(REFUSALS) | {"STAGE_C_RESERVE_INVALID"} <= PREFLIGHT_REFUSAL_CODES


@pytest.mark.parametrize("code", sorted(REFUSALS))
def test_a_guard_refusal_before_any_attempt_is_a_complete_zero_cost_rejection(code, envelope_guard, monkeypatch, tmp_path) -> None:
    _body, error = _refused(code, envelope_guard, monkeypatch)

    assert is_preflight_refusal(error)
    [attempt] = attempts_from_failure(error)
    assert (attempt.outcome, attempt.cost_usd, attempt.http_status) == ("rejected", Decimal("0"), 503)
    for mode, stage in ((ExecutionMode.AGENT, "planning"), (ExecutionMode.CHAT, "answer")):
        result, receipts, gateway = _run(tmp_path, mode, error)
        assert [(r.stage, r.outcome, r.reported_cost_usd) for r in receipts] == [(stage, "rejected", Decimal("0"))]
        assert (result.cost_complete, result.total_cost_usd, gateway.calls) == (True, Decimal("0"), 1)
    [summary] = _summarize(error).attempts
    assert (summary.outcome, summary.cost_usd) == ("rejected", Decimal("0"))


NEGATIVES = {
    "retryable-unstated": lambda body: {k: v for k, v in body.items() if k != "retryable"},
    "retryable-true": lambda body: {**body, "retryable": True},
    "malformed-attempt-list": lambda body: {**body, "route_attempts": [{"attempt": "one"}]},
    "reported-usage": lambda body: {
        **body,
        "gateway_usage": {"gateway_request_id": "gw-used", "provider": "p", "billing_units": 3, "cost_usd": "0.0003"},
    },
}
NEGATIVE_OUTCOMES = {
    "retryable-unstated": [("uncertain", None)],
    "retryable-true": [("uncertain", None)],
    "malformed-attempt-list": [("uncertain", None)],
    "reported-usage": [("completed", Decimal("0.0003"))],
}


@pytest.mark.parametrize("negative", sorted(NEGATIVES))
def test_a_stage_c_code_without_the_whole_proof_is_not_a_free_request(negative, envelope_guard, monkeypatch) -> None:
    body, _error = _refused("STAGE_C_BUDGET_EXHAUSTED", envelope_guard, monkeypatch)

    error = _host_error(503, NEGATIVES[negative](body), monkeypatch)

    assert not is_preflight_refusal(error)
    assert [(a.outcome, a.cost_usd) for a in attempts_from_failure(error)] == NEGATIVE_OUTCOMES[negative]


@pytest.mark.parametrize("first", [ATTEMPT_NOT_SENT, ATTEMPT_REJECTED])
def test_a_refused_resend_keeps_the_earlier_unbilled_attempt(first, envelope_guard, monkeypatch, tmp_path) -> None:
    policy, guard, clock = envelope_guard
    upstream = RecordingUpstream(attempts=[UpstreamAttemptFailure(first, http_status=429 if first == ATTEMPT_REJECTED else None), None])

    def expire(_seconds: float) -> None:
        clock.now = guard.state.deadline  # the recovery delay crosses the deadline

    monkeypatch.setattr(gateway_responses, "_sleep", expire)
    status, body = _post(policy, guard, upstream)
    assert (status, body["code"], len(upstream.calls), guard.state.attempts) == (503, "STAGE_C_WINDOW_EXHAUSTED", 1, 1)
    [sent] = body["route_attempts"]
    error = _host_error(status, body, monkeypatch)

    assert not is_preflight_refusal(error)  # an attempt was made: never "nothing happened"
    [attempt] = attempts_from_failure(error)
    assert (attempt.number, attempt.outcome, attempt.cost_usd, attempt.gateway_request_id, attempt.routed) == (1, first, Decimal("0"), sent["gateway_request_id"], True)
    result, receipts, _gateway = _run(tmp_path, ExecutionMode.CHAT, error)
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [(first, Decimal("0"))]
    assert (result.cost_complete, result.total_cost_usd) == (True, Decimal("0"))
