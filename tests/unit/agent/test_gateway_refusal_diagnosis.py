"""Plan 12.2 r8 offline correction (Codex proposal f711bd72, operator-approved 2026-10-17): a reply the Gateway
refuses after it was charged is diagnosable, and a proven stopped experimental route never suggests a retry.

r8's B7.6: the Gateway settled a completed, charged answer, then refused the reply (422) and stopped the
experimental route for the rest of its life. The host kept the charge but logged no refusal code or outer status,
and Chat said "Please try again". Here: the real Gateway handler on the reviewed Haiku test snapshots, its HTTP
error through the host client's own parsing (`urlopen` raising `HTTPError`), and the real runner. Ordinary routes
keep their wording and recovery. Offline only: no service, no provider.
"""

from __future__ import annotations

import contextlib
import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

import optimus.gateway.client as gateway_client
import optimus_gateway.responses as gateway_responses
from optimus.acp.debug_trace import configure_debug_trace, log_provider_attempts, reset_debug_trace_context
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import CHAT_FAILURE_MESSAGES, CHAT_ROUTE_STOPPED_MESSAGES, AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.attempts import (
    GATEWAY_FAILURE_CODES,
    REPLY_REFUSAL_CODES,
    ROUTE_STOP_CODES,
    gateway_failure_facts,
    stops_experimental_route,
)
from optimus.gateway.client import GatewayClient, GatewayRequest, UrllibGatewayTransport
from optimus.gateway.errors import GatewayHttpError, GatewayResponseError
from optimus.gateway.models import GatewayRouteAttempt
from optimus.gateway.route_binding import RoutePolicy
from optimus.runtime.modes import ExecutionMode
from optimus.usage.turn_settlement import StageReceipt
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import ProviderMessageResult, UpstreamAttemptFailure
from optimus_model_policy import test_profiles as profiles
from optimus_model_policy.binding import ATTEMPT_REJECTED, ATTEMPT_UNCERTAIN, disclosure_key
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    SHARED_SECRET,
    RecordingUpstream,
    gateway_config,
    model_policy,
    verified_snapshot,
)

HAIKU = "anthropic/claude-haiku-5.5"
ORDINARY = "cn/alpha"
CANARY = "Authorization: Bearer " + "refusal-diagnosis-canary"  # synthetic; must never reach the log
LOCATION = "debug_trace.py:log_provider_attempts"
CHARGE = Decimal("0.0002")  # RecordingUpstream's reported cost


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gateway_responses, "_sleep", lambda _seconds: None)
    reset_debug_trace_context()
    yield
    reset_debug_trace_context()


class Replying(RecordingUpstream):
    """Completed replies with scripted router evidence (the experimental route's reply checks read it)."""

    def __init__(self, *, finish_reason: str | None = "stop", attempts=None, **evidence: Any) -> None:
        super().__init__(finish_reason=finish_reason, attempts=attempts)
        self.evidence = {"resolved_provider": "Anthropic", "router_attempt": 1, "router_pipeline": (), "input_tokens": 1, **evidence}

    def _result(self, model: str) -> ProviderMessageResult:
        return ProviderMessageResult(**{**super()._result(model).__dict__, **self.evidence})


class _Reply:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._data


class InProcessGateway:
    """The real Gateway handler behind the host client's real urllib transport: only `urlopen` is replaced, so a
    non-200 reply reaches the host as the `HTTPError` the client parses itself."""

    def __init__(self, policy, upstream, monkeypatch: pytest.MonkeyPatch) -> None:
        self.config, self.upstream, self.replies = gateway_config(policy), upstream, []
        monkeypatch.setattr(gateway_client, "urlopen", self._urlopen)

    def _urlopen(self, request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        status, body = handle_responses_request(authorization_header=AUTH, request_body=payload, config=self.config, upstream_client=self.upstream)
        self.replies.append((status, body))
        data = json.dumps(body, default=str).encode("utf-8")
        if status != 200:
            raise HTTPError(request.full_url, status, "refused", None, io.BytesIO(data))  # type: ignore[arg-type]
        return _Reply(data)


def _trace(tmp_path: Path) -> Path:
    log = tmp_path / "trace" / "debug-acp.ndjson"
    configure_debug_trace(enabled=True, log_path=log)
    return log


def _records(log: Path) -> list[dict]:
    if not log.exists():
        return []
    return [record["data"] for record in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if record["location"] == LOCATION]


def _haiku(profile: str):
    return model_policy(profiles.compose_test_profile_snapshot(profile)), HAIKU


def _ordinary(tmp_path: Path):
    return model_policy(verified_snapshot(tmp_path)), ORDINARY


def _chat(tmp_path: Path, policy, model: str, *, turn: int = 1):
    """One Chat turn through the real runner, bound to the same trusted snapshot as the Gateway."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    route = RoutePolicy(snapshot=policy.snapshot, disclosure_key=disclosure_key(SHARED_SECRET), model_id=model, role="easy" if model == HAIKU else "medium", output_cap=16384)
    binder = route.capture(session_id="s", turn_seq=turn, deliver_notice=lambda _text: True)
    receipts: list[StageReceipt] = []
    client = GatewayClient(settings=OptimusGatewaySettings(optimus_api_key=SHARED_SECRET), transport=UrllibGatewayTransport())
    request = AgentRunRequest(run_id=f"s:{turn}", session_id="s", task=f"Confirm the rule in one sentence. {CANARY}", workspace_root=tmp_path, execution_mode=ExecutionMode.CHAT)
    result = AgentRunner(gateway_client=client, model=model, provider_attempt_observer=log_provider_attempts).run(request, stage_receipts=receipts.append, route_binder=binder)
    return result, receipts


# The experimental route's reply refusals after a completed, charged attempt (each one stops the route), as the
# upstream evidence that triggers them. Finish statuses other than stop/length are refused on any route.
REPLY_REFUSALS = {
    "EMPIRICAL_ESTIMATE_EXCEEDED": {"input_tokens": 10**9},
    "EMPIRICAL_PROVIDER_MISMATCH": {"resolved_provider": "Google"},
    "EMPIRICAL_PROVIDER_MISSING": {"resolved_provider": None},
    "EMPIRICAL_ROUTER_FALLBACK": {"router_attempt": 2},
    "EMPIRICAL_ROUTER_METADATA_MISSING": {"router_attempt": None},
    "EMPIRICAL_ROUTER_PIPELINE": {"router_pipeline": ("context_compression",)},
    "EMPIRICAL_ROUTER_METADATA_MALFORMED": {"router_metadata_error": "ambiguous", "resolved_provider": None},
    "FINISH_STATUS_UNVERIFIED": {"finish_reason": None},
}


def _upstream(code: str) -> Replying:
    evidence = dict(REPLY_REFUSALS[code])
    return Replying(finish_reason=evidence.pop("finish_reason", "stop"), **evidence)


# --- r8 B7.6 reproduced: a charged reply refused on the experimental route ----------------------------------------


@pytest.mark.parametrize("profile", ["qualification", "attached"])
@pytest.mark.parametrize("code", sorted(REPLY_REFUSALS))
def test_a_refused_charged_reply_is_diagnosable_and_says_the_route_stopped(tmp_path, monkeypatch, profile, code) -> None:
    policy, model = _haiku(profile)
    gateway = InProcessGateway(policy, _upstream(code), monkeypatch)
    log = _trace(tmp_path)

    result, receipts = _chat(tmp_path, policy, model)

    [(status, body)] = gateway.replies
    assert (status, body["code"]) == (422, code)
    # Accounting and the result are unchanged: the charge is kept once, the turn failed and nothing is committed.
    assert (result.stop_reason, result.total_cost_usd, result.cost_complete, result.unknown_cost_attempt_count) == ("CHAT_GATEWAY_FAILURE", CHARGE, True, 0)
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("completed", CHARGE)]
    # The route is proven stopped, so Chat no longer suggests a retry.
    assert result.output_text == CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_FAILURE"]
    assert result.output_text != CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_FAILURE"] and "try again" not in result.output_text.lower()
    # The diagnostic names the Gateway's refusal and its outer status, apart from the routed attempt's own status.
    [record] = _records(log)
    assert record["attempts"] == [{"attempt": "1", "outcome": "completed", "routed": True, "upstream_http_status": None, "gateway_http_status": None}]
    assert record["gateway_failure"] == {"code": code, "http_status": 422}
    assert CANARY not in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("code", sorted(REPLY_REFUSALS))
def test_the_next_request_on_a_stopped_route_is_refused_free_and_says_so(tmp_path, monkeypatch, code) -> None:
    policy, model = _haiku("attached")
    gateway = InProcessGateway(policy, _upstream(code), monkeypatch)
    _chat(tmp_path / "first", policy, model)
    log = _trace(tmp_path)

    result, receipts = _chat(tmp_path / "second", policy, model, turn=2)

    assert [(status, body["code"]) for status, body in gateway.replies] == [(422, code), (503, "EMPIRICAL_ROUTE_STOPPED")]
    assert len(gateway.upstream.calls) == 1  # the stopped route reaches no provider
    assert (result.stop_reason, result.total_cost_usd, result.cost_complete) == ("CHAT_GATEWAY_REFUSED", Decimal("0"), True)
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    assert result.output_text == CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_REFUSED"] != CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_REFUSED"]
    _states_only_the_stop_and_this_free_refusal(result.output_text)
    [record] = _records(log)
    assert record["gateway_failure"] == {"code": "EMPIRICAL_ROUTE_STOPPED", "http_status": 503}


def _states_only_the_stop_and_this_free_refusal(text: str) -> None:
    """A later refusal proves only that the route is stopped and that this request reached no model at $0: the stop's
    cause is not known to it, so its text names none (Codex review P2, 2026-10-17)."""
    lowered = text.lower()
    for claim in ("reply", "check", "earlier", "failed", "uncertain", "cost could not"):
        assert claim not in lowered, claim
    for fact in ("stopped", "before it reached any model", "nothing was charged", "retrying will not help"):
        assert fact in lowered, fact


def test_a_route_stopped_by_an_uncertain_attempt_refuses_the_next_request_without_naming_a_cause(tmp_path, monkeypatch) -> None:
    """The Gateway also stops the experimental route after an uncertain attempt (no reply was refused): the later
    refusal must not claim that an earlier reply failed its checks."""
    policy, model = _haiku("qualification")
    gateway = InProcessGateway(policy, Replying(attempts=[UpstreamAttemptFailure(ATTEMPT_UNCERTAIN)]), monkeypatch)
    first, _ = _chat(tmp_path / "first", policy, model)
    log = _trace(tmp_path)

    result, receipts = _chat(tmp_path / "second", policy, model, turn=2)

    assert [(status, body["code"]) for status, body in gateway.replies] == [(502, "UPSTREAM_ATTEMPT_UNCERTAIN"), (503, "EMPIRICAL_ROUTE_STOPPED")]
    assert (first.stop_reason, first.cost_complete) == ("CHAT_GATEWAY_COST_UNKNOWN", False)
    assert len(gateway.upstream.calls) == 1  # the stopped route reaches no provider
    assert (result.stop_reason, result.total_cost_usd, result.cost_complete) == ("CHAT_GATEWAY_REFUSED", Decimal("0"), True)
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("rejected", Decimal("0"))]
    _states_only_the_stop_and_this_free_refusal(result.output_text)
    [record] = _records(log)
    assert record["gateway_failure"] == {"code": "EMPIRICAL_ROUTE_STOPPED", "http_status": 503}


def test_an_uncertain_attempt_on_the_experimental_route_keeps_its_unknown_cost_and_says_the_route_stopped(tmp_path, monkeypatch) -> None:
    policy, model = _haiku("qualification")
    gateway = InProcessGateway(policy, Replying(attempts=[UpstreamAttemptFailure(ATTEMPT_UNCERTAIN)]), monkeypatch)
    log = _trace(tmp_path)

    result, _ = _chat(tmp_path, policy, model)

    assert [(status, body["code"]) for status, body in gateway.replies] == [(502, "UPSTREAM_ATTEMPT_UNCERTAIN")]
    assert (result.stop_reason, result.cost_complete, result.unknown_cost_attempt_count) == ("CHAT_GATEWAY_COST_UNKNOWN", False, 1)
    assert result.output_text == CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_COST_UNKNOWN"] != CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_COST_UNKNOWN"]
    [record] = _records(log)
    assert record["gateway_failure"] == {"code": "UPSTREAM_ATTEMPT_UNCERTAIN", "http_status": 502}
    assert record["attempts"] == [{"attempt": "1", "outcome": "uncertain", "routed": True, "upstream_http_status": None, "gateway_http_status": None}]


def test_rejected_attempts_do_not_stop_the_experimental_route_or_change_its_wording(tmp_path, monkeypatch) -> None:
    """Twice rate-limited: proven unbilled, so the Gateway does not stop the route and the next request is admitted."""
    policy, model = _haiku("qualification")
    rejected = [UpstreamAttemptFailure(ATTEMPT_REJECTED, http_status=429), UpstreamAttemptFailure(ATTEMPT_REJECTED, http_status=429)]
    gateway = InProcessGateway(policy, Replying(attempts=rejected), monkeypatch)
    log = _trace(tmp_path)

    result, _ = _chat(tmp_path / "first", policy, model)
    later, _ = _chat(tmp_path / "second", policy, model, turn=2)

    assert [(status, body.get("code")) for status, body in gateway.replies] == [(502, "UPSTREAM_ATTEMPT_REJECTED"), (200, None)]
    assert result.stop_reason == "CHAT_GATEWAY_FAILURE" and result.output_text == CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_FAILURE"]
    assert later.status.value == "completed"
    assert _records(log)[0]["gateway_failure"] == {"code": "UPSTREAM_ATTEMPT_REJECTED", "http_status": 502}


def test_a_plan_mode_request_records_its_gateway_failure_too(tmp_path) -> None:
    """PLAN mode's single planning request reports through the same observer as Chat and the planning loop."""
    error = GatewayHttpError(
        502, CANARY, gateway_code="UPSTREAM_ATTEMPT_REJECTED", retryable=False,
        route_attempts=(GatewayRouteAttempt(attempt=1, gateway_request_id="gw-1", outcome="rejected", http_status=429),),
    )  # fmt: skip

    class Raising:
        def create_response(self, **_kwargs):
            raise error

    log = _trace(tmp_path)
    request = AgentRunRequest(run_id="s:1", session_id="s", task="Change the greeting.", workspace_root=tmp_path, execution_mode=ExecutionMode.PLAN)
    with contextlib.suppress(GatewayHttpError):  # the PLAN path lets the failure propagate, as it always has
        AgentRunner(gateway_client=Raising(), model="fake/model", provider_attempt_observer=log_provider_attempts).run(request)

    [record] = _records(log)
    assert (record["stage"], record["gateway_failure"]) == ("planning", {"code": "UPSTREAM_ATTEMPT_REJECTED", "http_status": 502})
    assert CANARY not in log.read_text(encoding="utf-8")


# --- Ordinary routes keep their wording and recovery --------------------------------------------------------------


def test_an_ordinary_route_refusal_is_diagnosable_but_keeps_its_retry_wording_and_recovers(tmp_path, monkeypatch) -> None:
    policy, model = _ordinary(tmp_path)
    upstream = Replying(finish_reason=None)
    gateway = InProcessGateway(policy, upstream, monkeypatch)
    log = _trace(tmp_path)

    result, receipts = _chat(tmp_path / "first", policy, model)
    upstream._finish_reason = "stop"
    later, _ = _chat(tmp_path / "second", policy, model, turn=2)

    assert [(status, body.get("code")) for status, body in gateway.replies] == [(422, "FINISH_STATUS_UNVERIFIED"), (200, None)]
    assert (result.stop_reason, result.total_cost_usd, result.output_text) == ("CHAT_GATEWAY_FAILURE", CHARGE, CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_FAILURE"])
    assert [(r.outcome, r.reported_cost_usd) for r in receipts] == [("completed", CHARGE)]
    assert later.status.value == "completed"  # the ordinary route was never stopped
    assert _records(log)[0]["gateway_failure"] == {"code": "FINISH_STATUS_UNVERIFIED", "http_status": 422}


def test_an_ordinary_route_uncertain_attempt_keeps_its_retry_wording(tmp_path, monkeypatch) -> None:
    policy, model = _ordinary(tmp_path)
    InProcessGateway(policy, Replying(attempts=[UpstreamAttemptFailure(ATTEMPT_UNCERTAIN)]), monkeypatch)
    result, _ = _chat(tmp_path, policy, model)
    assert (result.stop_reason, result.output_text) == ("CHAT_GATEWAY_COST_UNKNOWN", CHAT_FAILURE_MESSAGES["CHAT_GATEWAY_COST_UNKNOWN"])


# --- The classifier: bounded facts, never text ------------------------------------------------------------------


def test_the_route_binder_knows_its_route_from_the_trusted_snapshot_only(tmp_path) -> None:
    def experimental(snapshot, model, role) -> bool:
        policy = RoutePolicy(snapshot=snapshot, disclosure_key=b"k", model_id=model, role=role, output_cap=16384)
        return policy.capture(session_id="s", turn_seq=1, deliver_notice=lambda _text: True).experimental

    assert experimental(profiles.compose_test_profile_snapshot("qualification"), HAIKU, "easy") is True
    assert experimental(profiles.compose_test_profile_snapshot("attached"), HAIKU, "easy") is True
    assert experimental(verified_snapshot(tmp_path), ORDINARY, "medium") is False


@pytest.mark.parametrize(
    ("error", "facts"),
    [
        (GatewayHttpError(422, CANARY, gateway_code="EMPIRICAL_ROUTER_FALLBACK"), {"code": "EMPIRICAL_ROUTER_FALLBACK", "http_status": 422}),
        (GatewayHttpError(503, CANARY, gateway_code="EMPIRICAL_ROUTE_STOPPED"), {"code": "EMPIRICAL_ROUTE_STOPPED", "http_status": 503}),
        (GatewayHttpError(500, CANARY, gateway_code=CANARY), {"code": "UNRECOGNIZED", "http_status": 500}),
        (GatewayHttpError(502, CANARY), {"code": None, "http_status": 502}),
        (GatewayHttpError(0, CANARY), {"code": None, "http_status": None}),
        (GatewayHttpError(True, CANARY), {"code": None, "http_status": None}),  # type: ignore[arg-type]
        (GatewayHttpError(1000, CANARY), {"code": None, "http_status": None}),
        (GatewayResponseError(CANARY, audit_code="GATEWAY_USAGE_MISSING"), None),
        (ConnectionResetError(CANARY), None),
    ],
    ids=["known", "stopped", "unknown-code", "no-code", "no-http-status", "bool-status", "out-of-range", "response-error", "transport"],
)
def test_failure_facts_are_an_allowlisted_code_and_an_integer_status_only(error, facts) -> None:
    assert gateway_failure_facts(error) == facts
    assert CANARY not in json.dumps(gateway_failure_facts(error))


def test_only_a_proven_stop_selects_the_stopped_route_wording() -> None:
    def error(code: str | None) -> GatewayHttpError:
        return GatewayHttpError(422, CANARY, gateway_code=code)

    for code in sorted(ROUTE_STOP_CODES - {"EMPIRICAL_ROUTE_STOPPED"}):
        assert stops_experimental_route(error(code), experimental=True), code
        assert not stops_experimental_route(error(code), experimental=False), code
    # The Gateway refuses a stopped route by this code alone: it is its own proof.
    assert stops_experimental_route(error("EMPIRICAL_ROUTE_STOPPED"), experimental=False)
    for code in sorted(GATEWAY_FAILURE_CODES - ROUTE_STOP_CODES) + [None, CANARY]:
        assert not stops_experimental_route(error(code), experimental=True), code
    assert not stops_experimental_route(ConnectionResetError(CANARY), experimental=True)
    assert not stops_experimental_route(GatewayResponseError(CANARY), experimental=True)


def test_the_stop_codes_are_the_reply_refusals_the_uncertain_attempt_and_the_stopped_refusal() -> None:
    assert ROUTE_STOP_CODES == REPLY_REFUSAL_CODES | {"UPSTREAM_ATTEMPT_UNCERTAIN", "EMPIRICAL_ROUTE_STOPPED"}
    assert set(REPLY_REFUSALS) == REPLY_REFUSAL_CODES  # every reply refusal is reproduced above
    assert ROUTE_STOP_CODES <= GATEWAY_FAILURE_CODES


def test_the_stopped_route_wording_covers_exactly_the_three_stop_outcomes_and_never_suggests_a_retry() -> None:
    assert set(CHAT_ROUTE_STOPPED_MESSAGES) == {"CHAT_GATEWAY_FAILURE", "CHAT_GATEWAY_COST_UNKNOWN", "CHAT_GATEWAY_REFUSED"}
    for reason, text in CHAT_ROUTE_STOPPED_MESSAGES.items():
        assert text != CHAT_FAILURE_MESSAGES[reason] and "try again" not in text.lower(), reason
        assert "retrying will not help" in text.lower(), reason
    assert "charged" in CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_FAILURE"]
    assert "nothing was charged" in CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_REFUSED"]
    assert "cost" in CHAT_ROUTE_STOPPED_MESSAGES["CHAT_GATEWAY_COST_UNKNOWN"]


def test_the_host_request_reaches_the_gateway_through_the_real_transport(monkeypatch) -> None:
    """Guard for the harness itself: the request body the Gateway saw is the host's own wire payload."""
    seen: list[dict] = []

    def capture(request, timeout):
        seen.append(json.loads(request.data.decode("utf-8")))
        return _Reply(b"{}")

    monkeypatch.setattr(gateway_client, "urlopen", capture)
    UrllibGatewayTransport().post_json(GatewayRequest("POST", "http://127.0.0.1:8765/v1/responses", {}, {"model": "m"}))
    assert seen == [{"model": "m"}]
