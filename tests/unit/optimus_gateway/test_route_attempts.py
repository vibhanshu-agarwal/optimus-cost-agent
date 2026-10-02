"""Plan 12.2 Task 5: the enforced attempt contract (Task 1 contracts §4 and §6; Codex CP1 ruling, item 4).

Under enforcement one host model request makes at most two provider attempts of the identical
admitted payload. A recovery attempt follows only an attempt that certainly reached no model (never
sent, or rate-limited); an uncertain, possibly billed attempt is never re-sent, by the Gateway or by
the host. Every attempt has its own receipt identity and is reported in order. Today's routing keeps
its legacy retry loop unchanged.
"""

from __future__ import annotations

import errno
import io
import json
import socket
import ssl
from decimal import Decimal
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

import optimus_gateway.responses as gateway_responses
from optimus.gateway.client import _try_parse_error_correlation
from optimus.gateway.errors import GatewayHttpError
from optimus.gateway.models import parse_gateway_response
from optimus.retry.policy import FailureKind, classify_failure
from optimus_gateway.responses import handle_responses_request
from optimus_gateway.upstream_client import UpstreamAttemptFailure, UrllibOpenAICompatibleClient
from optimus_model_policy.binding import MAX_ROUTE_ATTEMPTS
from tests.unit.optimus_gateway.model_policy_support import (
    AUTH,
    VERIFIED_POLICY,
    RecordingUpstream,
    binding,
    gateway_config,
    model_policy,
    verified_snapshot,
)


@pytest.fixture
def snapshot(tmp_path: Path):
    return verified_snapshot(tmp_path)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(gateway_responses, "_sleep", slept.append)
    return slept


def _enforced(snapshot, upstream) -> tuple[int, dict[str, Any]]:
    return handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "hi", "route_binding": binding(snapshot, input_text="hi", request_id="host-req-7")},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
    )


NOT_SENT = UpstreamAttemptFailure("not_sent")
RATE_LIMITED = UpstreamAttemptFailure("rejected", http_status=429)


def test_bound_is_one_primary_plus_one_recovery() -> None:
    assert MAX_ROUTE_ATTEMPTS == 2


@pytest.mark.parametrize("first", [NOT_SENT, RATE_LIMITED], ids=["not-sent", "rate-limited"])
def test_one_recovery_follows_an_attempt_that_reached_no_model(snapshot, no_sleep, first) -> None:
    upstream = RecordingUpstream(attempts=[first, None])
    status, body = _enforced(snapshot, upstream)

    assert status == 200
    assert len(upstream.calls) == 2
    assert upstream.calls[0] == upstream.calls[1], "the recovery attempt sends the identical admitted payload"
    assert no_sleep == [gateway_responses._RECOVERY_DELAY_SECONDS]
    first_record, second_record = body["route_attempts"]
    assert (first_record["attempt"], first_record["outcome"]) == (1, first.outcome)
    assert (second_record["attempt"], second_record["outcome"]) == (2, "completed")
    assert first_record["gateway_request_id"] != second_record["gateway_request_id"], "each attempt has its own receipt"
    usage = body["gateway_usage"]
    assert usage["gateway_request_id"] == second_record["gateway_request_id"]
    assert (usage["route_request_id"], usage["attempt"]) == ("host-req-7", 2)
    assert second_record["provider_request_id"] == usage["provider_request_id"]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (UpstreamAttemptFailure("uncertain"), "UPSTREAM_ATTEMPT_UNCERTAIN"),
        (UpstreamAttemptFailure("uncertain", http_status=502), "UPSTREAM_ATTEMPT_UNCERTAIN"),
        (UpstreamAttemptFailure("rejected", http_status=400), "UPSTREAM_ATTEMPT_REJECTED"),
        (UpstreamAttemptFailure("rejected", http_status=402), "UPSTREAM_ATTEMPT_REJECTED"),
    ],
    ids=["timeout", "server-error", "bad-request", "payment"],
)
def test_an_uncertain_or_refused_attempt_is_never_re_sent(snapshot, no_sleep, failure, code) -> None:
    upstream = RecordingUpstream(attempts=[failure, None])
    status, body = _enforced(snapshot, upstream)

    assert (status, body["code"], body["retryable"]) == (502, code, False)
    assert len(upstream.calls) == 1, "no second attempt after an uncertain or refused one"
    assert no_sleep == []
    [record] = body["route_attempts"]
    assert (record["attempt"], record["outcome"], record["http_status"]) == (1, failure.outcome, failure.http_status)
    assert body["route_request_id"] == "host-req-7"
    assert "gateway_usage" not in body, "an uncertain attempt has no verified cost"


def test_the_bound_is_never_exceeded(snapshot) -> None:
    upstream = RecordingUpstream(attempts=[NOT_SENT, NOT_SENT, None, None])
    status, body = _enforced(snapshot, upstream)

    assert (status, body["code"], body["retryable"]) == (502, "UPSTREAM_ATTEMPT_NOT_SENT", False)
    assert len(upstream.calls) == MAX_ROUTE_ATTEMPTS
    assert [record["outcome"] for record in body["route_attempts"]] == ["not_sent", "not_sent"]


@pytest.mark.parametrize(
    ("second", "code"),
    [(UpstreamAttemptFailure("uncertain"), "UPSTREAM_ATTEMPT_UNCERTAIN"), (RATE_LIMITED, "UPSTREAM_ATTEMPT_REJECTED")],
    ids=["429-then-uncertain", "429-then-429"],
)
def test_a_failed_recovery_attempt_ends_the_request(snapshot, second, code) -> None:
    upstream = RecordingUpstream(attempts=[RATE_LIMITED, second, None])
    status, body = _enforced(snapshot, upstream)
    assert (status, body["code"], body["retryable"]) == (502, code, False)
    assert len(upstream.calls) == 2
    assert [(r["attempt"], r["outcome"]) for r in body["route_attempts"]] == [(1, "rejected"), (2, second.outcome)]
    assert "gateway_usage" not in body


def test_a_finish_refusal_reports_its_completed_attempt(snapshot) -> None:
    upstream = RecordingUpstream(finish_reason="content_filter")
    status, body = _enforced(snapshot, upstream)
    assert (status, body["code"], body["retryable"]) == (422, "FINISH_STATUS_UNVERIFIED", False)
    [record] = body["route_attempts"]
    assert record["outcome"] == "completed"
    assert body["gateway_usage"]["gateway_request_id"] == record["gateway_request_id"]


def test_admission_refusals_report_zero_attempts(snapshot) -> None:
    upstream = RecordingUpstream()
    forged = dict(binding(snapshot), registry_hash="f" * 64)
    status, body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "hi", "route_binding": forged},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
    )
    assert (status, body["route_attempts"], body["retryable"]) == (400, [], False)
    assert upstream.calls == []


def test_todays_routing_keeps_its_legacy_path(snapshot) -> None:
    upstream = RecordingUpstream()
    status, body = handle_responses_request(
        authorization_header=AUTH, request_body={"model": "claude-haiku", "input": "hi"}, config=gateway_config(), upstream_client=upstream
    )
    assert status == 200
    assert upstream.calls == [{"legacy": True, "model": "anthropic/claude-haiku-4.5", "input_text": "hi"}]
    assert "route_attempts" not in body


# --- Exact endpoint expression (Codex CP1 ruling, item 1) -------------------------------------------


def test_a_route_written_with_base_slugs_never_reaches_upstream(tmp_path: Path) -> None:
    """Approved pairs alpha-cloud/fp8 and alpha-backup/bf16 written as base slugs would let OpenRouter
    pick alpha-cloud's bf16 or alpha-backup's fp8 variant; such a route is not eligible."""
    text = VERIFIED_POLICY.replace("provider: alpha-cloud/fp8,", "provider: alpha-cloud,").replace(
        "provider: alpha-backup/bf16,", "provider: alpha-backup,"
    )
    snapshot = verified_snapshot(tmp_path, text)
    upstream = RecordingUpstream()
    status, body = handle_responses_request(
        authorization_header=AUTH,
        request_body={"model": "cn/alpha", "input": "hi", "route_binding": binding(snapshot, input_text="hi")},
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
    )
    assert (status, body["code"]) == (400, "MODEL_NOT_ELIGIBLE")
    assert upstream.calls == []


def test_the_wire_names_only_the_exact_approved_endpoints(snapshot) -> None:
    upstream = RecordingUpstream()
    assert _enforced(snapshot, upstream)[0] == 200
    only = list(upstream.calls[0]["provider_controls"]["only"])
    approved = [endpoint.provider for endpoint in snapshot.policy.models["cn/alpha"].route.endpoints]
    assert only == approved == ["alpha-cloud/fp8", "alpha-backup/bf16"]
    assert all("/" in slug for slug in only), "no base slug that would widen to other variants"


# --- Host side: parsing and no re-send ----------------------------------------------------------------


def test_the_host_parses_each_attempt(snapshot) -> None:
    status, body = _enforced(snapshot, RecordingUpstream(attempts=[NOT_SENT, None]))
    response = parse_gateway_response(json.loads(json.dumps(body, default=str)))
    assert [(a.attempt, a.outcome) for a in response.route_attempts] == [(1, "not_sent"), (2, "completed")]
    assert (response.gateway_usage.route_request_id, response.gateway_usage.attempt) == ("host-req-7", 2)


def test_the_host_never_re_sends_an_enforced_failure(snapshot) -> None:
    status, body = _enforced(snapshot, RecordingUpstream(attempts=[UpstreamAttemptFailure("uncertain")]))
    detail = json.dumps(body)
    code, retryable, attempts = _try_parse_error_correlation(detail)
    error = GatewayHttpError(status, detail, gateway_code=code, retryable=retryable, route_attempts=attempts)
    classification = classify_failure(error)
    assert (classification.kind, classification.retryable) == (FailureKind.PERMANENT, False)
    assert [a.outcome for a in error.route_attempts] == ["uncertain"]


def test_the_host_transport_carries_the_enforced_error_fields(snapshot, monkeypatch) -> None:
    """Through a real HTTPError on the host's urllib transport, not a hand-built error (Fable m2)."""
    from optimus.gateway.client import GatewayRequest, UrllibGatewayTransport

    status, body = _enforced(snapshot, RecordingUpstream(finish_reason="error"))
    raw = json.dumps(body, default=str).encode()

    def fake_urlopen(request, timeout: float = 0):
        raise HTTPError("http://127.0.0.1:8765/v1/responses", status, "refused", None, io.BytesIO(raw))  # type: ignore[arg-type]

    monkeypatch.setattr("optimus.gateway.client.urlopen", fake_urlopen)
    with pytest.raises(GatewayHttpError) as caught:
        UrllibGatewayTransport().post_json(
            GatewayRequest(method="POST", url="http://127.0.0.1:8765/v1/responses", headers={}, payload={"model": "cn/alpha", "input": "hi"})
        )
    error = caught.value
    assert (error.status_code, error.gateway_code, error.retryable) == (422, "FINISH_STATUS_UNVERIFIED", False)
    assert [a.outcome for a in error.route_attempts] == ["completed"]
    assert error.gateway_usage is not None and error.gateway_usage.attempt == 1
    assert classify_failure(error).retryable is False


def test_todays_gateway_errors_keep_status_based_retries() -> None:
    error = GatewayHttpError(502, "upstream request failed")
    assert classify_failure(error).retryable is True
    assert _try_parse_error_correlation('{"error": "x"}') == (None, None, ())


def test_malformed_attempt_lists_are_rejected_by_the_host(snapshot) -> None:
    status, body = _enforced(snapshot, RecordingUpstream())
    body = json.loads(json.dumps(body, default=str))
    for bad in ([{"attempt": 2, "gateway_request_id": "gw-1", "outcome": "completed"}], [{"attempt": 1, "outcome": "done"}], "nope"):
        with pytest.raises(Exception, match="route_attempts"):
            parse_gateway_response(dict(body, route_attempts=bad))


# --- The real client: one attempt, classified ---------------------------------------------------------


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.headers: dict[str, str] = {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _ok_body() -> bytes:
    return json.dumps(
        {
            "id": "gen-1",
            "model": "cn/alpha",
            "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "cost": "0.00001"},
        }
    ).encode()


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://openrouter.ai/api/v1/chat/completions", code, "error", None, io.BytesIO(b"{}"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raised", "outcome", "status", "recoverable"),
    [
        (URLError(ConnectionRefusedError(10061, "refused")), "not_sent", None, True),
        (URLError(socket.gaierror(11001, "getaddrinfo failed")), "not_sent", None, True),
        (URLError(ssl.SSLError(1, "handshake failure")), "not_sent", None, True),
        (URLError(OSError(errno.ENETUNREACH, "network unreachable")), "not_sent", None, True),
        (URLError(OSError(errno.EHOSTUNREACH, "host unreachable")), "not_sent", None, True),
        (ssl.SSLError(1, "bad record mac after send"), "uncertain", None, False),
        (URLError(TimeoutError("timed out")), "uncertain", None, False),
        (URLError(ConnectionResetError(10054, "reset")), "uncertain", None, False),
        (TimeoutError("read timed out"), "uncertain", None, False),
        (RemoteDisconnected("closed"), "uncertain", None, False),
        (_http_error(429), "rejected", 429, True),
        (_http_error(400), "rejected", 400, False),
        (_http_error(408), "uncertain", 408, False),
        (_http_error(500), "uncertain", 500, False),
        (_http_error(503), "uncertain", 503, False),
    ],
    ids=[
        "refused", "dns", "tls-handshake", "net-unreachable", "host-unreachable", "tls-after-send", "connect-timeout",
        "reset-on-send", "read-timeout", "disconnected", "429", "400", "408", "500", "503",
    ],
)
def test_the_real_client_classifies_each_failure_and_never_retries_itself(monkeypatch, raised, outcome, status, recoverable) -> None:
    calls: list[object] = []

    def fake_urlopen(request, timeout: float = 0):
        calls.append(request)
        raise raised

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1", sleep=lambda _s: None)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=8, provider_controls={"only": ["a/b"]}, reasoning=None)
    assert (caught.value.outcome, caught.value.http_status, caught.value.recoverable) == (outcome, status, recoverable)
    assert len(calls) == 1, "one call per attempt; the Gateway owns the bound"


@pytest.mark.parametrize("payload", [b"not json", b"[1, 2]", json.dumps({"id": "gen-1", "choices": []}).encode()], ids=["invalid", "array", "no-usage"])
def test_an_unreadable_reply_is_an_uncertain_attempt(monkeypatch, payload) -> None:
    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", lambda request, timeout=0: _Response(payload))
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1")
    with pytest.raises(UpstreamAttemptFailure) as caught:
        client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=8, provider_controls={}, reasoning="high")
    assert caught.value.outcome == "uncertain"


def test_the_real_client_sends_the_reasoning_level_and_returns_the_reply(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout: float = 0):
        sent.append(json.loads(request.data.decode("utf-8")))
        return _Response(_ok_body())

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(api_key="or-test", base_url="https://openrouter.ai/api/v1")
    for reasoning, expected in (("xhigh", {"effort": "xhigh"}), (None, None)):
        result = client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=8, provider_controls={"only": ["a/b"]}, reasoning=reasoning)
        assert result.cost_usd == Decimal("0.00001")
        assert sent[-1].get("reasoning") == expected
    assert "reasoning" not in sent[-1], "no reasoning field when the route has no reasoning levels"
