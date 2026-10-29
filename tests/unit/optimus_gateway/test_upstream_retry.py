from __future__ import annotations

import inspect
import io
import socket
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

import optimus_gateway.upstream_client as upstream_module
from optimus.gateway.client import DEFAULT_GATEWAY_TIMEOUT_SECONDS
from optimus_gateway.models import GatewayToolContext
from optimus_gateway.tool_models import WebSearchGatewayRequest
from optimus_gateway.tool_provider_http import ToolProviderError, request_bytes, request_json
from optimus_gateway.tool_providers import OsvAdvisoryToolProvider, PackageRegistryToolProvider, TavilyWebToolProvider
from optimus_gateway.upstream_client import (
    AttemptDeadline,
    AttemptDeadlineExpired,
    RetryableUpstreamError,
    RetryEvent,
    UpstreamAttemptFailure,
    UpstreamBudgetExhausted,
    UrllibOpenAICompatibleClient,
    _AttemptHTTPConnection,
    _AttemptRequest,
    begin_request_budget,
    call_with_upstream_retry,
    end_request_budget,
    is_retryable_upstream_fault,
    watched_urlopen,
)
from optimus_model_policy import stage_c
from optimus_model_policy.binding import (
    GATEWAY_REQUEST_BUDGET_SECONDS,
    HOST_GATEWAY_TIMEOUT_SECONDS,
    MAX_ROUTE_ATTEMPTS,
    UPSTREAM_ATTEMPT_TIMEOUT_SECONDS,
)


def _http_error(code: int, body: bytes = b"upstream error") -> HTTPError:
    return HTTPError(
        url="https://openrouter.ai/api/v1/chat/completions",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(body),
    )


def _success_body() -> bytes:
    return (
        b'{"id":"chatcmpl-ok","choices":[{"message":{"role":"assistant","content":"ok"}}],'
        b'"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"cost":"0.00001"}}'
    )


class _FakeResponse:
    def __init__(self, payload: bytes, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.parametrize("code", (429, 500, 502, 503, 504))
def test_transient_http_statuses_are_retryable(code: int):
    assert is_retryable_upstream_fault(_http_error(code)) is True


@pytest.mark.parametrize("code", (400, 401, 403, 404, 422))
def test_permanent_http_statuses_are_not_retryable(code: int):
    assert is_retryable_upstream_fault(_http_error(code)) is False


def test_network_and_timeout_url_errors_are_retryable():
    assert is_retryable_upstream_fault(URLError("connection refused")) is True
    assert is_retryable_upstream_fault(URLError(TimeoutError("timed out"))) is True
    assert is_retryable_upstream_fault(TimeoutError("timed out")) is True


def test_malformed_body_runtime_error_is_not_retryable():
    assert is_retryable_upstream_fault(RuntimeError("upstream response missing id")) is False


def test_upstream_retries_transient_503_then_succeeds(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []
    slept: list[float] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise _http_error(503, b"temporary")
        return _FakeResponse(_success_body())

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=slept.append,
        on_retry=events.append,
    )

    result = client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert result.output_text == "ok"
    assert attempts == [1, 2, 3]
    assert [(event.attempt, event.classification, event.disposition) for event in events] == [
        (1, "transient", "retry"),
        (2, "transient", "retry"),
    ]
    assert all(event.latency_seconds >= 0 for event in events)
    assert slept == [0.05, 0.1]


def test_upstream_does_not_retry_permanent_401(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        raise _http_error(401, b"unauthorized")

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    with pytest.raises(RuntimeError, match="401"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert [(event.classification, event.disposition) for event in events] == [("permanent", "terminal")]


def test_model_retry_ceiling_is_three_attempts(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        raise _http_error(429, b"rate limited")

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    with pytest.raises(RuntimeError, match="429"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1, 2, 3]
    assert [event.disposition for event in events] == ["retry", "retry", "terminal"]
    assert [event.attempt for event in events] == [1, 2, 3]
    assert all(event.classification == "transient" for event in events)
    assert all(event.latency_seconds >= 0 for event in events)


def test_upstream_does_not_retry_malformed_success_body(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        return _FakeResponse(b'{"id":"","choices":[]}')

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    with pytest.raises(RuntimeError, match="missing"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert [(event.classification, event.disposition) for event in events] == [("permanent", "terminal")]


def test_upstream_does_not_retry_malformed_json(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        return _FakeResponse(b"{not json")

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    with pytest.raises(RuntimeError, match="invalid JSON"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert [(event.classification, event.disposition) for event in events] == [("permanent", "terminal")]


def test_upstream_failure_does_not_expose_provider_response_context(monkeypatch):
    provider_context = "provider-secret-context"

    def fake_urlopen(request: object, timeout: float = 0):
        raise _http_error(401, provider_context.encode())

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
    )

    with pytest.raises(RuntimeError) as exc_info:
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert provider_context not in str(exc_info.value)


def test_upstream_retries_raw_timeout_error_then_succeeds(monkeypatch):
    """Exercise _urlopen_json's TimeoutError branch through the retry loop, not just the classifier."""
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 2:
            raise TimeoutError("timed out")
        return _FakeResponse(_success_body())

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    result = client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert result.output_text == "ok"
    assert attempts == [1, 2]
    assert [event.disposition for event in events] == ["retry"]


def test_upstream_retries_url_error_then_succeeds(monkeypatch):
    """Exercise _urlopen_json's URLError branch through the retry loop."""
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 2:
            raise URLError("connection refused")
        return _FakeResponse(_success_body())

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    result = client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert result.output_text == "ok"
    assert attempts == [1, 2]
    assert [event.disposition for event in events] == ["retry"]


def test_upstream_does_not_retry_malformed_accounting(monkeypatch):
    attempts: list[int] = []
    events: list[RetryEvent] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        return _FakeResponse(
            b'{"id":"chatcmpl-ok","choices":[{"message":{"role":"assistant","content":"ok"}}],'
            b'"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"cost":"NaN"}}'
        )

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=events.append,
    )

    with pytest.raises(RuntimeError, match="cost"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert [(event.classification, event.disposition) for event in events] == [("permanent", "terminal")]


def test_openrouter_request_enables_provider_metadata(monkeypatch):
    captured: list[object] = []

    def fake_urlopen(request: object, timeout: float = 0):
        captured.append(request)
        return _FakeResponse(_success_body())

    monkeypatch.setattr("optimus_gateway.upstream_client.watched_urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",  # pragma: allowlist secret
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
    )

    client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert captured[0].get_header("X-openrouter-metadata") == "enabled"


def test_tool_retry_helper_keeps_legacy_default_and_integer_callback():
    attempts: list[int] = []
    retries: list[int] = []

    def operation() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 4:
            raise RetryableUpstreamError("transient")
        return "ok"

    assert call_with_upstream_retry(operation, sleep=lambda _delay: None, on_retry=retries.append) == "ok"
    assert attempts == [1, 2, 3, 4]
    assert retries == [1, 2, 3]


# --- #397 live Z2: the host waits longer than the Gateway works on one request ---


def test_the_host_waits_longer_than_every_attempt_the_gateway_may_make_for_one_request():
    """A 30 s host wait against a 60 s attempt abandoned a reply the provider had already billed (#397 live Z2)."""
    assert GATEWAY_REQUEST_BUDGET_SECONDS >= MAX_ROUTE_ATTEMPTS * UPSTREAM_ATTEMPT_TIMEOUT_SECONDS
    assert HOST_GATEWAY_TIMEOUT_SECONDS > GATEWAY_REQUEST_BUDGET_SECONDS
    assert DEFAULT_GATEWAY_TIMEOUT_SECONDS == HOST_GATEWAY_TIMEOUT_SECONDS
    attempt_timeouts = [
        inspect.signature(UrllibOpenAICompatibleClient).parameters["timeout_seconds"].default,
        inspect.signature(call_with_upstream_retry).parameters["attempt_timeout_seconds"].default,
        inspect.signature(request_json).parameters["timeout_seconds"].default,
        inspect.signature(request_bytes).parameters["timeout_seconds"].default,
        *(
            inspect.signature(provider).parameters["timeout_seconds"].default
            for provider in (TavilyWebToolProvider, PackageRegistryToolProvider, OsvAdvisoryToolProvider)
        ),
        stage_c.ATTEMPT_TIMEOUT_SECONDS,
    ]
    assert attempt_timeouts == [UPSTREAM_ATTEMPT_TIMEOUT_SECONDS] * len(attempt_timeouts)


def _always_transient(calls: list[int]):
    def operation() -> str:
        calls.append(len(calls) + 1)
        raise RetryableUpstreamError("transient")

    return operation


def test_no_retry_starts_that_could_outlast_the_host_request():
    calls: list[int] = []
    dispositions: list[str] = []
    begin_request_budget()
    try:
        with pytest.raises(RuntimeError):
            call_with_upstream_retry(
                _always_transient(calls),
                sleep=lambda _delay: None,
                on_attempt_failure=lambda _n, _kind, _latency, disposition, _failure: dispositions.append(disposition),
                attempt_timeout_seconds=GATEWAY_REQUEST_BUDGET_SECONDS - 0.01,
            )
    finally:
        end_request_budget()
    assert (calls, dispositions) == ([1], ["terminal"])


def test_outside_a_host_request_only_the_attempt_bound_applies():
    calls: list[int] = []
    with pytest.raises(RuntimeError):
        call_with_upstream_retry(
            _always_transient(calls), sleep=lambda _delay: None, attempt_timeout_seconds=GATEWAY_REQUEST_BUDGET_SECONDS - 0.01
        )
    assert calls == [1, 2, 3, 4]


def test_no_attempt_starts_once_the_host_request_cannot_wait_for_it():
    calls: list[int] = []
    begin_request_budget()
    try:
        with pytest.raises(UpstreamBudgetExhausted):
            call_with_upstream_retry(_always_transient(calls), attempt_timeout_seconds=GATEWAY_REQUEST_BUDGET_SECONDS + 1)
    finally:
        end_request_budget()
    assert calls == []


@pytest.mark.parametrize("helper", [request_json, request_bytes])
def test_a_tool_request_starts_no_attempt_that_could_outlast_the_host_request(helper):
    opened: list[float] = []

    def urlopen_fn(_request, *, timeout):
        opened.append(timeout)
        raise AssertionError("no attempt may start")

    begin_request_budget()
    try:
        with pytest.raises(ToolProviderError):
            helper(
                Request("https://tools.invalid/probe"),
                label="probe",
                urlopen_fn=urlopen_fn,
                timeout_seconds=GATEWAY_REQUEST_BUDGET_SECONDS + 1,
            )
    finally:
        end_request_budget()
    assert opened == []


def test_a_retry_whose_backoff_outlasts_the_budget_ends_with_the_previous_failure(monkeypatch):
    """Checked at dispatch, after the backoff (Codex round 1): a long sleep leaves no room, so the earlier failure stands."""
    clock = [0.0]
    monkeypatch.setattr(upstream_module, "time", types.SimpleNamespace(monotonic=lambda: clock[0], sleep=time.sleep))
    calls: list[int] = []

    def oversleep(_delay: float) -> None:
        clock[0] += GATEWAY_REQUEST_BUDGET_SECONDS - UPSTREAM_ATTEMPT_TIMEOUT_SECONDS + 1

    begin_request_budget()
    try:
        with pytest.raises(RuntimeError, match="transient") as raised:
            call_with_upstream_retry(_always_transient(calls), sleep=oversleep)
    finally:
        end_request_budget()
    assert calls == [1]
    assert not isinstance(raised.value, UpstreamBudgetExhausted), "the attempt that ran is the outcome, not 'nothing sent'"


# --- an attempt ends at its deadline, whatever the provider keeps sending (Codex round 1, finding 1) ---

_DRIP_BODY = (
    b'{"id":"chatcmpl-drip","choices":[{"message":{"role":"assistant","content":"ok"}}],'
    b'"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"cost":"0.00001"}}'
)
_DRIP_ATTEMPT_SECONDS = 0.5  # each byte arrives well inside it, so only a whole-attempt deadline can end the read


_DRIP_ENDINGS: list[tuple[str, float]] = []
"""How each drip reply ended, and when: ``completed``, or ``dropped`` when the client's side closed under it."""


class _DripHandler(BaseHTTPRequestHandler):
    """Sends the status and headers at once, then one body byte every 20 ms: about 3 s in all."""

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(_DRIP_BODY)))
        self.end_headers()
        try:
            for byte in _DRIP_BODY:
                self.wfile.write(bytes([byte]))
                self.wfile.flush()
                time.sleep(0.02)
        except OSError:
            _DRIP_ENDINGS.append(("dropped", time.monotonic()))
            return  # the client ended the attempt
        _DRIP_ENDINGS.append(("completed", time.monotonic()))

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def drip_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DripHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _client(base_url: str, **kwargs) -> UrllibOpenAICompatibleClient:
    return UrllibOpenAICompatibleClient(api_key="drip-test", base_url=base_url, timeout_seconds=_DRIP_ATTEMPT_SECONDS, **kwargs)  # pragma: allowlist secret


def _ends_in_time(started: float) -> None:
    assert time.monotonic() - started < _DRIP_ATTEMPT_SECONDS + 1.0, "the attempt outlived its deadline"


def test_an_enforced_attempt_ends_at_its_deadline_while_bytes_keep_arriving(drip_url):
    started = time.monotonic()
    with pytest.raises(UpstreamAttemptFailure) as raised:
        _client(drip_url).create_message_once(model="m", input_text="x", max_tokens=1, provider_controls={}, reasoning=None)
    _ends_in_time(started)
    assert (raised.value.outcome, raised.value.failure) == ("uncertain", {"kind": "attempt_deadline"})


def test_a_decision_attempt_ends_at_its_deadline_while_bytes_keep_arriving(drip_url):
    started = time.monotonic()
    with pytest.raises(UpstreamAttemptFailure) as raised:
        _client(drip_url).create_decision_once(model="m", state={}, questions={}, provider_controls={})
    _ends_in_time(started)
    assert (raised.value.outcome, raised.value.failure) == ("uncertain", {"kind": "attempt_deadline"})


def test_a_legacy_attempt_ends_at_its_deadline_while_bytes_keep_arriving(drip_url):
    events: list[RetryEvent] = []
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="abandoned"):
        _client(drip_url, max_attempts=1, on_retry=events.append).create_message(model="m", input_text="x")
    _ends_in_time(started)
    assert [event.failure for event in events] == [{"kind": "attempt_deadline"}]


def test_a_tool_attempt_ends_at_its_deadline_while_bytes_keep_arriving(drip_url):
    started = time.monotonic()
    with pytest.raises(ToolProviderError):
        request_json(
            Request(drip_url + "/search", data=b"{}", method="POST"),
            label="probe",
            timeout_seconds=_DRIP_ATTEMPT_SECONDS,
            sleep=lambda _delay: None,
        )
    # Each of the bounded retries ends at its own deadline.
    assert time.monotonic() - started < 4 * _DRIP_ATTEMPT_SECONDS + 1.5


def test_a_connection_made_after_the_deadline_sends_nothing():
    """The abandoned attempt finishes its setup late: its connection is refused, so it stays not sent."""
    listener = socket.create_server(("127.0.0.1", 0))
    request = _AttemptRequest("http://127.0.0.1/")
    connection = _AttemptHTTPConnection("127.0.0.1", listener.getsockname()[1], attempt=request)
    deadline = AttemptDeadline(0.05)
    refused: list[BaseException] = []
    held: list[object] = []

    def slow_setup() -> None:
        time.sleep(0.3)  # as a slow name lookup would
        try:
            connection.connect()
        except TimeoutError as exc:
            refused.append(exc)
            held.append(connection.sock)

    started = time.monotonic()
    try:
        with pytest.raises(AttemptDeadlineExpired):
            deadline.run(slow_setup)
        assert time.monotonic() - started < 0.25
        time.sleep(0.5)  # the abandoned worker reaches its connect
    finally:
        connection.close()
        listener.close()
    assert (len(refused), request.connected, deadline.accepted) == (1, False, False)
    assert held == [None], "refused as soon as the TCP connection existed, before any tunnel or TLS work began"


def test_a_handshake_that_finishes_after_the_deadline_still_sends_nothing():
    """The TLS handshake runs after the raw socket was handed over, on a socket the deadline can no longer shut down: a
    handshake that completes late is refused when the connection is established, before any request byte leaves."""
    deadline = AttemptDeadline(0.05)
    raw, peer = socket.socketpair()
    refused: list[BaseException] = []

    def late_handshake() -> None:
        deadline.opened(raw)
        time.sleep(0.3)  # as a TLS handshake still running past the deadline would
        try:
            deadline.connected(raw)
        except TimeoutError as exc:
            refused.append(exc)

    try:
        with pytest.raises(AttemptDeadlineExpired):
            deadline.run(late_handshake)
        time.sleep(0.5)  # the abandoned worker finishes its handshake
    finally:
        raw.close()
        peer.close()
    assert (len(refused), deadline.accepted) == (1, False)


def test_a_slow_name_lookup_cannot_outlast_the_deadline(monkeypatch):
    """Codex round 2: resolution precedes any socket, so only waiting no longer than the deadline bounds it."""
    real = socket.getaddrinfo

    def slow_getaddrinfo(*args, **kwargs):
        time.sleep(3)
        return real(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", slow_getaddrinfo)
    started = time.monotonic()
    with pytest.raises(UpstreamAttemptFailure) as raised:
        _client("http://upstream.test").create_message_once(model="m", input_text="x", max_tokens=1, provider_controls={}, reasoning=None)
    _ends_in_time(started)
    assert (raised.value.outcome, raised.value.failure) == ("not_sent", {"kind": "attempt_deadline"})


_PROXY_ENDINGS: list[tuple[str, float]] = []


class _DripConnectProxy(BaseHTTPRequestHandler):
    """Answers CONNECT with a status line, then one header line every 20 ms (10 s in all), never ending the reply."""

    def do_CONNECT(self) -> None:
        try:
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n")
            for n in range(500):
                self.wfile.write(f"X-Drip-{n}: 1\r\n".encode("ascii"))
                self.wfile.flush()
                time.sleep(0.02)
        except OSError:
            _PROXY_ENDINGS.append(("dropped", time.monotonic()))
            return
        _PROXY_ENDINGS.append(("completed", time.monotonic()))

    def log_message(self, format: str, *args: object) -> None:
        return


def test_a_proxy_that_drips_its_connect_reply_cannot_outlast_the_deadline_or_keep_the_connection(monkeypatch):
    """Codex rounds 2-3: the tunnel runs inside ``connect()``. The deadline holds the socket from the moment the TCP
    connection exists, so abandoning the attempt also tears the tunnel down; no connection was accepted, so nothing was
    sent."""
    _PROXY_ENDINGS.clear()
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), _DripConnectProxy)
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{proxy.server_address[1]}")
    monkeypatch.setenv("NO_PROXY", "")
    try:
        started = time.monotonic()
        with pytest.raises(UpstreamAttemptFailure) as raised:
            _client("https://upstream.test").create_message_once(model="m", input_text="x", max_tokens=1, provider_controls={}, reasoning=None)
        _ends_in_time(started)
        wait_until = time.monotonic() + 5
        while not _PROXY_ENDINGS and time.monotonic() < wait_until:
            time.sleep(0.05)
    finally:
        proxy.shutdown()
        proxy.server_close()
    assert (raised.value.outcome, raised.value.failure) == ("not_sent", {"kind": "attempt_deadline"})
    [(ending, at)] = _PROXY_ENDINGS
    assert ending == "dropped" and at - started < _DRIP_ATTEMPT_SECONDS + 1.0, "the stalled tunnel was not torn down"


def test_stalled_attempts_hold_at_most_their_slots_and_later_ones_fail_at_once(monkeypatch):
    """Codex round 3: a name lookup cannot be interrupted, so an abandoned worker can outlive its deadline. The slots
    bound how many do; with all of them held, the next attempt starts nothing and fails at once, as not sent."""
    for earlier in [t for t in threading.enumerate() if t.name == "optimus-upstream-attempt"]:
        earlier.join(10)  # workers abandoned by earlier tests, so the count below is this test's own
    monkeypatch.setattr(upstream_module, "_ATTEMPT_SLOTS", threading.BoundedSemaphore(2))
    real = socket.getaddrinfo

    def stalled_getaddrinfo(*args, **kwargs):
        time.sleep(2)
        return real(*args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", stalled_getaddrinfo)

    def attempt() -> UpstreamAttemptFailure:
        with pytest.raises(UpstreamAttemptFailure) as raised:
            _client("http://upstream.test").create_message_once(model="m", input_text="x", max_tokens=1, provider_controls={}, reasoning=None)
        return raised.value

    stalled = [attempt(), attempt()]
    started = time.monotonic()
    refused = attempt()
    assert time.monotonic() - started < 0.2
    workers = [t for t in threading.enumerate() if t.name == "optimus-upstream-attempt"]
    assert len(workers) <= 2
    assert [(f.outcome, f.failure) for f in stalled] == [("not_sent", {"kind": "attempt_deadline"})] * 2
    assert (refused.outcome, refused.failure) == ("not_sent", {"kind": "attempt_capacity"})
    for worker in workers:
        worker.join(5)
    assert attempt().failure == {"kind": "attempt_deadline"}, "a slot is free again once its worker exits"


def test_the_production_tool_adapters_use_the_watched_opener():
    """Codex round 2: the adapters passed the standard ``urlopen`` explicitly, so the deadline never saw their sockets."""
    defaults = [inspect.signature(adapter).parameters["urlopen"].default for adapter in (TavilyWebToolProvider, PackageRegistryToolProvider, OsvAdvisoryToolProvider)]
    assert defaults == [watched_urlopen] * 3


def test_a_tool_adapter_ends_its_attempts_at_their_deadline_while_bytes_keep_arriving(drip_url):
    adapter = TavilyWebToolProvider(api_key="drip-test", base_url=drip_url, timeout_seconds=_DRIP_ATTEMPT_SECONDS, sleep=lambda _delay: None)  # pragma: allowlist secret
    request = WebSearchGatewayRequest(
        context=GatewayToolContext(run_id="run-drip", authenticated_subject="test"),
        query="q",
        allowed_domains=("python.org",),
        result_cap=1,
        search_depth="basic",
    )
    started = time.monotonic()
    with pytest.raises(ToolProviderError):
        adapter.search(request)
    assert time.monotonic() - started < 4 * _DRIP_ATTEMPT_SECONDS + 1.5


def test_an_abandoned_attempt_releases_its_connection_at_once(drip_url):
    """The waiting thread returns at the deadline either way; shutting the socket down also stops the abandoned worker,
    so the provider sees the connection end instead of streaming its whole reply into it."""
    _DRIP_ENDINGS.clear()
    started = time.monotonic()
    with pytest.raises(UpstreamAttemptFailure):
        _client(drip_url).create_message_once(model="m", input_text="x", max_tokens=1, provider_controls={}, reasoning=None)
    deadline = time.monotonic() + 5
    while not _DRIP_ENDINGS and time.monotonic() < deadline:
        time.sleep(0.05)
    [(ending, at)] = _DRIP_ENDINGS
    assert ending == "dropped" and at - started < _DRIP_ATTEMPT_SECONDS + 1.0
