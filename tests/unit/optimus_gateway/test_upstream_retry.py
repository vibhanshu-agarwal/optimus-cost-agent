from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from optimus_gateway.upstream_client import (
    RetryableUpstreamError,
    RetryEvent,
    UrllibOpenAICompatibleClient,
    call_with_upstream_retry,
    is_retryable_upstream_fault,
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
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
