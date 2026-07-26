from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

T = TypeVar("T")

_MAX_UPSTREAM_ATTEMPTS = 4
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_BACKOFF_SECONDS = (0.05, 0.1, 0.2)


@dataclass(frozen=True)
class ProviderMessageResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int


class UpstreamClient(Protocol):
    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        """Call an upstream LLM API and return normalized text + usage."""


class RetryableUpstreamError(Exception):
    """Transient gateway→provider fault eligible for local retry before RuntimeError."""


def is_retryable_upstream_fault(exc: BaseException) -> bool:
    """Classify gateway→provider faults while HTTP/network shape is still visible."""
    if isinstance(exc, RetryableUpstreamError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, HTTPError):
        return exc.code in _TRANSIENT_HTTP_STATUS_CODES
    if isinstance(exc, URLError):
        return True
    return False


def call_with_upstream_retry(
    operation: Callable[[], T],
    *,
    max_attempts: int = _MAX_UPSTREAM_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
    backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
) -> T:
    """Retry only transient upstream faults; reraise the final failure as RuntimeError."""
    sleeper = sleep or time.sleep
    attempt = 1
    while True:
        try:
            return operation()
        except RetryableUpstreamError as exc:
            if attempt >= max_attempts:
                raise RuntimeError(str(exc)) from exc
            if on_retry is not None:
                on_retry(attempt)
            delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
            sleeper(delay)
            attempt += 1


class UrllibOpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._on_retry = on_retry

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
        }
        request = Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
            },
            method="POST",
        )
        body = call_with_upstream_retry(
            lambda: _urlopen_json(request, timeout_seconds=self._timeout_seconds, label="upstream"),
            sleep=self._sleep,
            on_retry=self._on_retry,
        )
        return parse_openai_chat_completion(body)


class UrllibAnthropicClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[int], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep
        self._on_retry = on_retry

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": input_text}],
        }
        request = Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )
        body = call_with_upstream_retry(
            lambda: _urlopen_json(request, timeout_seconds=self._timeout_seconds, label="anthropic"),
            sleep=self._sleep,
            on_retry=self._on_retry,
        )
        return parse_anthropic_message(body)


def _urlopen_json(request: Request, *, timeout_seconds: float, label: str) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"{label} request failed ({exc.code}): {detail}"
        if is_retryable_upstream_fault(exc):
            raise RetryableUpstreamError(message) from exc
        raise RuntimeError(message) from exc
    except URLError as exc:
        message = f"{label} request failed: {exc.reason}"
        if is_retryable_upstream_fault(exc):
            raise RetryableUpstreamError(message) from exc
        raise RuntimeError(message) from exc
    except TimeoutError as exc:
        message = f"{label} request failed: timed out"
        raise RetryableUpstreamError(message) from exc


def parse_openai_chat_completion(body: dict[str, Any]) -> ProviderMessageResult:
    message_id = body.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise RuntimeError("upstream response missing id")

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("upstream response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("upstream response missing choices[0]")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("upstream response missing message")
    output_text = message.get("content")
    if not isinstance(output_text, str):
        raise RuntimeError("upstream response missing message content")

    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("upstream response missing usage")
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise RuntimeError("upstream response usage missing token counts")

    return ProviderMessageResult(
        message_id=message_id,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def parse_anthropic_message(body: dict[str, Any]) -> ProviderMessageResult:
    message_id = body.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise RuntimeError("anthropic response missing id")

    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("anthropic response missing usage")
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
        raise RuntimeError("anthropic response usage missing token counts")

    output_text = _extract_anthropic_output_text(body.get("content"))
    return ProviderMessageResult(
        message_id=message_id,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _extract_anthropic_output_text(content: object) -> str:
    if not isinstance(content, list):
        raise RuntimeError("anthropic response missing content")
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if not chunks:
        raise RuntimeError("anthropic response missing text content")
    return "".join(chunks)
