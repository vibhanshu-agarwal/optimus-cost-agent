from __future__ import annotations

import io
from urllib.error import HTTPError, URLError

import pytest

from optimus_gateway.upstream_client import (
    UrllibOpenAICompatibleClient,
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
        b'"usage":{"prompt_tokens":1,"completion_tokens":1}}'
    )


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

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
    retries: list[int] = []
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
        on_retry=retries.append,
    )

    result = client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert result.output_text == "ok"
    assert attempts == [1, 2, 3]
    assert retries == [1, 2]
    assert slept == [0.05, 0.1]


def test_upstream_does_not_retry_permanent_401(monkeypatch):
    attempts: list[int] = []
    retries: list[int] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        raise _http_error(401, b"unauthorized")

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=retries.append,
    )

    with pytest.raises(RuntimeError, match="401"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert retries == []


def test_upstream_exhausts_four_attempts_and_reraises(monkeypatch):
    attempts: list[int] = []
    retries: list[int] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        raise _http_error(429, b"rate limited")

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=retries.append,
    )

    with pytest.raises(RuntimeError, match="429"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1, 2, 3, 4]
    assert retries == [1, 2, 3]


def test_upstream_does_not_retry_malformed_success_body(monkeypatch):
    attempts: list[int] = []
    retries: list[int] = []

    def fake_urlopen(request: object, timeout: float = 0):
        attempts.append(len(attempts) + 1)
        return _FakeResponse(b'{"id":"","choices":[]}')

    monkeypatch.setattr("optimus_gateway.upstream_client.urlopen", fake_urlopen)
    client = UrllibOpenAICompatibleClient(
        api_key="or-test",
        base_url="https://openrouter.ai/api/v1",
        sleep=lambda _delay: None,
        on_retry=retries.append,
    )

    with pytest.raises(RuntimeError, match="missing"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")

    assert attempts == [1]
    assert retries == []
