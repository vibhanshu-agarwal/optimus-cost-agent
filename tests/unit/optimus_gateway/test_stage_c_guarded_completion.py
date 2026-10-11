"""Plan 12.2 Task 13 (Stage C): the enforced completion path under the shared test envelope's guard.

With a Stage C guard configured, every physical upstream attempt, a safe resend included, is admitted by
the guard and its full reservation (the final admitted input estimate and the bound output cap at the
registry's prices) is durable before dispatch. The provider's reported charge is settled once, before any
reply check can fail the call; a proven unbilled attempt releases its dollars but keeps its count; an
uncertain attempt or an unknown charge stops every later dispatch. A refusal reaches no provider. Without a
guard the path is unchanged. Fake upstream attempts and temporary ledgers only.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import optimus_gateway.responses as gateway_responses
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure
from optimus_model_policy import stage_c
from optimus_model_policy.binding import ATTEMPT_NOT_SENT, ATTEMPT_REJECTED, ATTEMPT_UNCERTAIN
from optimus_model_policy.stage_c import StageCGuard
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    CAP,
    RecordingUpstream,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)
INPUT = "plan the change"


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def guarded(tmp_path: Path):
    """A verified policy, an initialized ledger and an open guard (closed afterwards)."""
    clock = Clock()
    path = stage_c.stage_c_ledger_path(tmp_path / "runtime")
    envelope = stage_c.compose_stage_c_envelope(ledger=path)
    stage_c.initialize_stage_c_ledger(path, envelope, clock=clock)
    guard = StageCGuard.open(path, envelope, clock=clock)
    policy = model_policy(verified_snapshot(tmp_path))
    yield policy, guard, path, clock
    guard.close()


def _post(policy, guard, upstream, *, request_id: str = "host-req-1") -> tuple[int, dict[str, Any]]:
    config = dataclasses.replace(gateway_config(policy), stage_c_guard=guard)
    return handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": INPUT, "route_binding": binding(policy.snapshot, input_text=INPUT, request_id=request_id)},
        config=config,
        upstream_client=upstream,
    )


def _records(path: Path, kind: str | None = None) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return [r for r in records if kind is None or r["kind"] == kind]


def _expected_reserve(policy) -> Decimal:
    entry = policy.snapshot.policy.models["cn/alpha"]
    estimate = -(-len(INPUT.encode("utf-8")) // 2) + 8 + 64  # ceil(0.5 * bytes) + one message + fixed framing
    return stage_c.reservation_usd(
        input_tokens=estimate, output_tokens=CAP, input_usd_per_million=entry.prices.input_usd_per_million, output_usd_per_million=entry.prices.output_usd_per_million
    )


class Observing(RecordingUpstream):
    """Records the ledger as it stood when each attempt reached the provider."""

    def __init__(self, path: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = path
        self.seen: list[list[str]] = []

    def create_message_once(self, **kwargs: Any) -> ProviderMessageResult:
        self.seen.append([r["kind"] for r in _records(self.path)])
        return super().create_message_once(**kwargs)


class Costing(RecordingUpstream):
    def __init__(self, cost: Decimal | None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cost = cost

    def _result(self, model: str) -> ProviderMessageResult:
        return dataclasses.replace(super()._result(model), cost_usd=self.cost)


def test_the_full_reservation_is_durable_before_the_attempt_and_the_charge_is_settled(guarded) -> None:
    policy, guard, path, _ = guarded
    upstream = Observing(path)

    status, body = _post(policy, guard, upstream)

    assert status == 200 and len(upstream.calls) == 1
    assert upstream.seen == [["init", "window", "reserve"]]
    [reserve] = _records(path, "reserve")
    assert Decimal(reserve["reserve_usd"]) == _expected_reserve(policy)
    assert reserve["request_id"] == "host-req-1" and reserve["attempt_id"] == body["gateway_usage"]["gateway_request_id"]
    [settle] = _records(path, "settle")
    assert (settle["result"], settle["cost_usd"]) == ("charged", "0.0002")
    assert (guard.state.attempts, guard.state.charged_usd, guard.state.outstanding_usd) == (1, Decimal("0.0002"), Decimal("0"))


@pytest.mark.parametrize("first", [UpstreamAttemptFailure(ATTEMPT_NOT_SENT), UpstreamAttemptFailure(ATTEMPT_REJECTED, http_status=429)], ids=["not-sent", "rate-limited"])
def test_a_safe_resend_is_admitted_again_and_its_unbilled_attempt_still_counts(guarded, first) -> None:
    policy, guard, path, _ = guarded
    upstream = Observing(path, attempts=[first, None])

    status, _body = _post(policy, guard, upstream)

    assert status == 200 and len(upstream.calls) == 2
    assert [r["result"] for r in _records(path, "settle")] == ["unbilled", "charged"]
    assert upstream.seen[1][-2:] == ["settle", "reserve"]  # the resend was admitted after the first settled
    assert (guard.state.attempts, guard.state.charged_usd) == (2, Decimal("0.0002"))


def test_an_uncertain_attempt_stops_every_later_dispatch(guarded) -> None:
    policy, guard, path, _ = guarded
    upstream = RecordingUpstream(attempts=[UpstreamAttemptFailure(ATTEMPT_UNCERTAIN, http_status=502)])

    status, _body = _post(policy, guard, upstream)
    assert status == 502 and len(upstream.calls) == 1
    assert [r["result"] for r in _records(path, "settle")] == ["unknown"]

    status, body = _post(policy, guard, upstream, request_id="host-req-2")
    assert (status, body["code"], body["retryable"]) == (503, "STAGE_C_HALTED", False)
    assert len(upstream.calls) == 1  # no provider was reached


def test_a_reply_without_a_known_charge_stops_dispatch(guarded) -> None:
    policy, guard, path, _ = guarded
    status, body = _post(policy, guard, Costing(None))
    assert (status, body["code"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN")
    assert [r["result"] for r in _records(path, "settle")] == ["unknown"]
    assert guard.state.halted is not None


def test_a_reply_that_fails_its_finish_check_keeps_its_settled_charge(guarded) -> None:
    policy, guard, path, _ = guarded
    status, body = _post(policy, guard, Costing(Decimal("0.0007"), finish_reason="content_filter"))
    assert (status, body["code"]) == (422, "FINISH_STATUS_UNVERIFIED")
    assert [(r["result"], r["cost_usd"]) for r in _records(path, "settle")] == [("charged", "0.0007")]
    assert guard.state.charged_usd == Decimal("0.0007")


def test_an_exhausted_envelope_refuses_before_any_provider_call(guarded) -> None:
    policy, guard, _path, _ = guarded
    guard.settle_charged(guard.admit(attempt_id="gw-" + "0" * 32, request_id="earlier", reserve_usd=Decimal("0.495")), Decimal("0.495"))  # the next reservation (about $0.0066) no longer fits
    upstream = RecordingUpstream()

    status, body = _post(policy, guard, upstream)

    assert (status, body["code"], body["retryable"], body["route_attempts"]) == (503, "STAGE_C_BUDGET_EXHAUSTED", False, [])
    assert upstream.calls == []


def test_a_resend_the_envelope_cannot_admit_is_refused_with_the_earlier_attempt_kept(guarded, monkeypatch: pytest.MonkeyPatch) -> None:
    policy, guard, path, clock = guarded
    upstream = Observing(path, attempts=[UpstreamAttemptFailure(ATTEMPT_NOT_SENT), None])

    def expire(_seconds: float) -> None:
        clock.now = T0 + timedelta(hours=1)  # the recovery delay crosses the deadline

    monkeypatch.setattr(gateway_responses, "_sleep", expire)
    status, body = _post(policy, guard, upstream)

    assert (status, body["code"]) == (503, "STAGE_C_WINDOW_EXHAUSTED")
    assert [a["outcome"] for a in body["route_attempts"]] == ["not_sent"]
    assert len(upstream.calls) == 1 and guard.state.attempts == 1


def test_without_a_guard_the_enforced_path_is_unchanged(tmp_path: Path) -> None:
    policy = model_policy(verified_snapshot(tmp_path))
    upstream = RecordingUpstream()
    status, _body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": INPUT, "route_binding": binding(policy.snapshot, input_text=INPUT)},
        config=gateway_config(policy),
        upstream_client=upstream,
    )
    assert status == 200 and len(upstream.calls) == 1
    assert gateway_config(policy).stage_c_guard is None
