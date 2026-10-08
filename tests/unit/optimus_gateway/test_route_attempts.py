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
    PROVIDER_KEY,
    VERIFIED_POLICY,
    RecordingUpstream,
    Wire,
    binding,
    gateway_config,
    http_reply,
    model_policy,
    ok_completion_body,
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
            GatewayRequest(
                method="POST", url="http://127.0.0.1:8765/v1/responses", headers={}, payload={"model": "cn/alpha", "input": "hi"}
            )
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


# --- The real client: one attempt, classified by transmission phase -----------------------------------
#
# These drive the real urllib opener, including its URLError wrapping, and the real http.client connect
# and send. Only the operating-system layer underneath is replaced: `socket.create_connection` and
# `SSLContext.wrap_socket` (Codex CP1 corrections review: test the wrapped error, not a bare one).

_URL = "https://openrouter.ai/api/v1"


def _once(client: UrllibOpenAICompatibleClient, *, reasoning: str | None = None) -> Any:
    return client.create_message_once(model="cn/alpha", input_text="hi", max_tokens=8, provider_controls={"only": ["a/b"]}, reasoning=reasoning)


def _client() -> UrllibOpenAICompatibleClient:
    return UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=_URL, sleep=lambda _s: None)


_BEFORE_SENDING = {
    "dns": lambda: Wire(connect=socket.gaierror(11001, "getaddrinfo failed")),
    "refused": lambda: Wire(connect=ConnectionRefusedError(10061, "refused")),
    "connect-timeout": lambda: Wire(connect=TimeoutError("timed out")),
    "net-unreachable": lambda: Wire(connect=OSError(errno.ENETUNREACH, "network unreachable")),
    "tls-handshake": lambda: Wire(handshake=ssl.SSLError(1, "[SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] handshake failure")),
    "tls-certificate": lambda: Wire(handshake=ssl.SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] verify failed")),
}
_AFTER_CONNECTING = {
    "tls-while-sending": lambda: Wire(send=ssl.SSLError(1, "[SSL: BAD_RECORD_MAC] bad record mac")),
    "tls-eof-while-sending": lambda: Wire(send=ssl.SSLEOFError(8, "EOF occurred in violation of protocol")),
    "refused-while-sending": lambda: Wire(send=ConnectionRefusedError(10061, "refused")),
    "host-unreachable-while-sending": lambda: Wire(send=OSError(errno.EHOSTUNREACH, "host unreachable")),
    "reset-while-sending": lambda: Wire(send=ConnectionResetError(10054, "reset")),
    "timeout-while-sending": lambda: Wire(send=TimeoutError("timed out")),
    "read-timeout": lambda: Wire(reply=TimeoutError("read timed out")),
    "disconnected": lambda: Wire(reply=b""),
}


@pytest.mark.parametrize("name", sorted(_BEFORE_SENDING))
def test_a_failure_before_the_connection_is_established_is_not_sent(monkeypatch, name) -> None:
    """Resolving, connecting and the TLS handshake all precede the first request byte, so a failure in
    any of them certainly delivered nothing: never sent, and one recovery attempt is allowed."""
    wire = _BEFORE_SENDING[name]().install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.http_status, caught.value.recoverable) == ("not_sent", None, True)
    assert (wire.connects, wire.bytes_sent()) == (1, 0)


@pytest.mark.parametrize("name", sorted(_AFTER_CONNECTING))
def test_any_failure_once_connected_is_uncertain_whatever_its_type(monkeypatch, name) -> None:
    """Once connected, request bytes may have left; the exception's type cannot say otherwise (a
    refusal or an unreachable host raised while sending is no proof of anything). Uncertain, never
    re-sent, one connection only."""
    wire = _AFTER_CONNECTING[name]().install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.http_status, caught.value.recoverable) == ("uncertain", None, False)
    assert wire.connects == 1


@pytest.mark.parametrize(
    ("make_wire", "outcome"),
    [(lambda: Wire(connect=ConnectionRefusedError(10061, "refused")), "not_sent"), (lambda: Wire(send=ConnectionResetError(10054, "reset")), "uncertain")],
    ids=["refused", "reset-while-sending"],
)
def test_a_plain_http_base_url_is_classified_by_phase_too(monkeypatch, make_wire, outcome) -> None:
    wire = make_wire().install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url="http://127.0.0.1:9/api/v1", sleep=lambda _s: None)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(client)
    assert caught.value.outcome == outcome
    assert wire.connects == 1


@pytest.mark.parametrize("base_url", ["ftp://127.0.0.1/api/v1", "file:///api/v1"])
def test_another_scheme_fails_before_anything_is_sent(monkeypatch, base_url) -> None:
    """The attempt opener has only HTTP and HTTPS handlers, so no other scheme can open a connection
    whose phase goes unrecorded; it fails as an unknown URL type, certainly unsent."""
    wire = Wire().install(monkeypatch)
    client = UrllibOpenAICompatibleClient(api_key=PROVIDER_KEY, base_url=base_url, sleep=lambda _s: None)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(client)
    assert caught.value.outcome == "not_sent"
    assert "unknown url type" in str(caught.value.__cause__)
    assert wire.connects == 0


_PROXY = {"https": "http://proxy.example:3128"}


def test_a_refused_proxy_tunnel_is_not_sent(monkeypatch) -> None:
    """Through an HTTPS proxy, connecting includes the CONNECT tunnel. A refused tunnel happens before
    the request's first byte: only the CONNECT line went out, and the attempt is certainly unsent."""
    wire = Wire(replies=[http_reply(403)], proxies=_PROXY).install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.recoverable) == ("not_sent", True)
    assert wire.requests_sent() == [b"CONNECT openrouter.ai:443 HTTP/1.1"]


def test_a_failure_after_the_proxy_tunnel_opens_is_uncertain(monkeypatch) -> None:
    """The tunnel opens (its CONNECT is the first send), then sending the request itself fails: the
    attempt had connected, so it is uncertain."""
    wire = Wire(replies=[http_reply(200)], send=ssl.SSLError(1, "[SSL: BAD_RECORD_MAC] bad record mac"), send_ok_calls=1, proxies=_PROXY)
    wire.install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.recoverable) == ("uncertain", False)
    assert wire.requests_sent() == [b"CONNECT openrouter.ai:443 HTTP/1.1"]
    assert wire.connects == 1


def test_an_untracked_request_is_refused_rather_than_presumed_unsent() -> None:
    """Fail closed: a request without a phase record could only ever be classified "not sent"."""
    from urllib.request import Request

    from optimus_gateway.upstream_client import _AttemptHTTPHandler, _AttemptHTTPSHandler

    for handler, url in ((_AttemptHTTPSHandler(), _URL), (_AttemptHTTPHandler(), "http://127.0.0.1:9/")):
        with pytest.raises(TypeError, match="_AttemptRequest"):
            (handler.https_open if url.startswith("https") else handler.http_open)(Request(url))  # type: ignore[union-attr]


def test_a_tls_failure_while_sending_is_uncertain_though_urllib_wraps_it_like_a_handshake_failure(monkeypatch) -> None:
    """The CP1 defect (Codex corrections review). urllib wraps an SSLError raised while sending in the
    same URLError as one raised during the handshake, so the type cannot place it; the phase does."""
    seen = []
    for wire in (Wire(send=ssl.SSLError(1, "[SSL: BAD_RECORD_MAC] bad record mac")), Wire(handshake=ssl.SSLError(1, "handshake failure"))):
        wire.install(monkeypatch)
        with pytest.raises(UpstreamAttemptFailure) as caught:
            _once(_client())
        cause = caught.value.__cause__
        assert type(cause) is URLError and type(cause.reason) is ssl.SSLError, "the wrapped form, exactly as urllib raises it"
        seen.append((caught.value.outcome, caught.value.recoverable))
    assert seen == [("uncertain", False), ("not_sent", True)]


@pytest.mark.parametrize(
    ("status", "outcome", "recoverable"),
    [(429, "rejected", True), (400, "rejected", False), (408, "uncertain", False), (500, "uncertain", False), (503, "uncertain", False)],
)
def test_an_http_error_is_classified_by_its_status(monkeypatch, status, outcome, recoverable) -> None:
    wire = Wire(reply=http_reply(status)).install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.http_status, caught.value.recoverable) == (outcome, status, recoverable)
    assert wire.connects == 1


def test_a_redirect_is_not_followed(monkeypatch) -> None:
    """Following it would send the request again, elsewhere; the attempt ends, uncertain."""
    wire = Wire(reply=http_reply(302, extra_headers="Location: https://elsewhere.example/v1/chat/completions\r\n")).install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client())
    assert (caught.value.outcome, caught.value.http_status, caught.value.recoverable) == ("uncertain", 302, False)
    assert wire.connects == 1


@pytest.mark.parametrize(
    "payload", [b"not json", b"[1, 2]", json.dumps({"id": "gen-1", "choices": []}).encode()], ids=["invalid", "array", "no-usage"]
)
def test_an_unreadable_reply_is_an_uncertain_attempt(monkeypatch, payload) -> None:
    Wire(reply=http_reply(200, payload)).install(monkeypatch)
    with pytest.raises(UpstreamAttemptFailure) as caught:
        _once(_client(), reasoning="high")
    assert caught.value.outcome == "uncertain"


def test_the_real_client_sends_the_reasoning_level_and_returns_the_reply(monkeypatch) -> None:
    """The serialized request as it leaves http.client, not the Request object handed to urllib."""
    for reasoning, expected in (("xhigh", {"effort": "xhigh"}), (None, None)):
        wire = Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
        result = _once(_client(), reasoning=reasoning)
        assert result.cost_usd == Decimal("0.00001")
        body = wire.request_body()
        assert body.get("reasoning") == expected
        assert (body["max_tokens"], body["provider"]) == (8, {"only": ["a/b"]})
        if expected is None:
            assert "reasoning" not in body, "no reasoning field when the route has no reasoning levels"


def test_a_wrapped_send_phase_tls_failure_is_one_uncertain_attempt_end_to_end(snapshot, monkeypatch) -> None:
    """Codex CP1 corrections review, required negative evidence. Through the real client and urllib,
    the Gateway reports exactly one uncertain attempt with retryable false, and the host's retry
    controller sends nothing further: one Gateway call, one upstream connection."""
    from optimus.gateway.client import GatewayRequest, UrllibGatewayTransport
    from optimus.retry.policy import RetryController

    wire = Wire(send=ssl.SSLError(1, "[SSL: BAD_RECORD_MAC] bad record mac")).install(monkeypatch)
    upstream = _client()
    gateway_calls: list[object] = []

    def gateway(request: Any, timeout: float = 0) -> Any:
        gateway_calls.append(request)
        status, body = _enforced(snapshot, upstream)
        raise HTTPError(request.full_url, status, "gateway error", None, io.BytesIO(json.dumps(body, default=str).encode()))  # type: ignore[arg-type]

    monkeypatch.setattr("optimus.gateway.client.urlopen", gateway)
    transport = UrllibGatewayTransport()
    errors: list[GatewayHttpError] = []

    def operation() -> Any:
        try:
            return transport.post_json(
                GatewayRequest(method="POST", url="http://127.0.0.1:8765/v1/responses", headers={}, payload={"model": "cn/alpha", "input": "hi"})
            )
        except GatewayHttpError as error:
            errors.append(error)
            raise

    result = RetryController(sleep_ms=lambda _ms: None).run(operation)
    assert (result.value, result.attempts, result.retry_count) == (None, 1, 0)
    [error] = errors
    assert (error.status_code, error.gateway_code, error.retryable) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN", False)
    assert [(a.attempt, a.outcome) for a in error.route_attempts] == [(1, "uncertain")]
    assert (len(gateway_calls), wire.connects) == (1, 1), "nothing re-sent, by the Gateway or the host"


def test_one_client_reuses_its_opener_and_every_attempt_starts_unconnected(monkeypatch) -> None:
    """The Gateway keeps one client, so every attempt after the first reuses its opener. The phase
    belongs to each attempt: one that connected never makes the next look connected, or the reverse."""
    client = _client()
    Wire(reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    assert _once(client).cost_usd == Decimal("0.00001")
    opener = client._attempt_opener  # noqa: SLF001

    outcomes = []
    for wire in (Wire(connect=ConnectionRefusedError(10061, "refused")), Wire(send=ssl.SSLError(1, "bad record mac")), Wire(connect=socket.gaierror(11001, "getaddrinfo failed"))):
        wire.install(monkeypatch)
        with pytest.raises(UpstreamAttemptFailure) as caught:
            _once(client)
        outcomes.append(caught.value.outcome)
    assert outcomes == ["not_sent", "uncertain", "not_sent"]
    assert client._attempt_opener is opener, "one opener, reused"  # noqa: SLF001


@pytest.mark.parametrize(
    ("second", "status", "code", "outcomes"),
    [
        (None, 200, None, ["not_sent", "completed"]),
        (ssl.SSLError(1, "[SSL: BAD_RECORD_MAC] bad record mac"), 502, "UPSTREAM_ATTEMPT_UNCERTAIN", ["not_sent", "uncertain"]),
    ],
    ids=["recovered", "recovery-uncertain"],
)
def test_the_gateway_recovers_once_through_the_real_client_after_a_refused_connection(snapshot, monkeypatch, no_sleep, second, status, code, outcomes) -> None:
    """The attempt contract's one recovery, through the real client rather than a recording fake: the
    refused first connection certainly sent nothing, so the identical payload is sent once more."""
    wire = Wire(connect=ConnectionRefusedError(10061, "refused"), connect_failures=1, send=second, reply=http_reply(200, ok_completion_body())).install(monkeypatch)
    response_status, body = _enforced(snapshot, _client())
    assert response_status == status
    attempts = body["route_attempts"]
    assert [(a["attempt"], a["outcome"]) for a in attempts] == list(enumerate(outcomes, start=1))
    assert len({a["gateway_request_id"] for a in attempts}) == 2, "each attempt has its own receipt identity"
    assert body.get("code") == code
    assert wire.connects == 2 and no_sleep == [gateway_responses._RECOVERY_DELAY_SECONDS]  # noqa: SLF001
    if status == 200:
        assert body["gateway_usage"]["attempt"] == 2


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("not json", (None, None, ())),
        ("[1, 2]", (None, None, ())),
        ('{"code": 7, "retryable": "no"}', (None, None, ())),
        (
            '{"code": "UPSTREAM_ATTEMPT_UNCERTAIN", "retryable": false, "route_attempts": [{"attempt": 3}]}',
            ("UPSTREAM_ATTEMPT_UNCERTAIN", False, ()),
        ),
    ],
    ids=["invalid-json", "not-an-object", "wrong-types", "malformed-attempts-keep-retryable"],
)
def test_error_correlation_parsing_never_raises_and_keeps_the_retry_flag(detail, expected) -> None:
    assert _try_parse_error_correlation(detail) == expected


def test_an_enforced_completion_without_a_binding_is_refused(snapshot) -> None:
    """Defence in depth: the handlers parse the binding first, but the enforced path refuses on its own."""
    upstream = RecordingUpstream()
    status, body = gateway_responses.run_model_completion(
        model="cn/alpha",
        input_text="hi",
        config=gateway_config(model_policy(snapshot)),
        upstream_client=upstream,
        build_success=lambda **_: {},
        route_binding=None,
    )
    assert (status, body["code"], body["route_attempts"], body["retryable"]) == (400, "BINDING_REQUIRED", [], False)
    assert upstream.calls == []


def test_a_reply_whose_usage_fails_the_contract_is_an_uncertain_attempt(snapshot) -> None:
    """Usage the Gateway cannot vouch for is never emitted as a success: the attempt is recorded as
    uncertain (it may have been billed) and nothing is re-sent."""
    from dataclasses import replace as replace_result

    class _BadUsage(RecordingUpstream):
        def _result(self, model: str):
            return replace_result(super()._result(model), billing_units=-1)

    upstream = _BadUsage()
    status, body = _enforced(snapshot, upstream)
    assert (status, body["code"], body["retryable"]) == (502, "UPSTREAM_ATTEMPT_UNCERTAIN", False)
    assert [r["outcome"] for r in body["route_attempts"]] == ["uncertain"]
    assert "gateway_usage" not in body
    assert len(upstream.calls) == 1
