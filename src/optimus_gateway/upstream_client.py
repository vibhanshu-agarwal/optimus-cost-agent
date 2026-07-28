from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

T = TypeVar("T")

_MAX_UPSTREAM_ATTEMPTS = 4
_MODEL_MAX_UPSTREAM_ATTEMPTS = 3
_TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_BACKOFF_SECONDS = (0.05, 0.1, 0.2)


@dataclass(frozen=True)
class RetryEvent:
    attempt: int
    classification: str
    latency_seconds: float
    disposition: Literal["retry", "terminal"]


@dataclass(frozen=True)
class ProviderMessageResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int | None
    billing_units: int
    cost_usd: Decimal
    provider: str
    resolved_provider: str | None
    requested_model: str
    resolved_model: str | None
    model_version: str | None
    cache_hit: bool
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_age_seconds: int | None = None


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
    on_attempt_failure: Callable[[int, str, float, Literal["retry", "terminal"]], None] | None = None,
    backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
) -> T:
    """Retry only transient upstream faults; reraise the final failure as RuntimeError."""
    sleeper = sleep or time.sleep
    attempt = 1
    while True:
        started_at = time.monotonic()
        try:
            return operation()
        except Exception as exc:
            retryable = is_retryable_upstream_fault(exc)
            disposition: Literal["retry", "terminal"] = (
                "retry" if retryable and attempt < max_attempts else "terminal"
            )
            if on_attempt_failure is not None:
                on_attempt_failure(
                    attempt,
                    "transient" if retryable else "permanent",
                    time.monotonic() - started_at,
                    disposition,
                )
            if disposition == "terminal":
                if retryable:
                    raise RuntimeError(str(exc)) from exc
                raise
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
        max_attempts: int = _MODEL_MAX_UPSTREAM_ATTEMPTS,
        sleep: Callable[[float], None] | None = None,
        on_retry: Callable[[RetryEvent], None] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least one")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
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
                "X-OpenRouter-Metadata": "enabled",
            },
            method="POST",
        )

        def call() -> ProviderMessageResult:
            body, headers = _urlopen_json(
                request,
                timeout_seconds=self._timeout_seconds,
                label="upstream",
            )
            return parse_openai_chat_completion(body, headers, requested_model=model)

        def report_failure(
            attempt: int,
            classification: str,
            latency_seconds: float,
            disposition: Literal["retry", "terminal"],
        ) -> None:
            if self._on_retry is not None:
                self._on_retry(
                    RetryEvent(
                        attempt=attempt,
                        classification=classification,
                        latency_seconds=latency_seconds,
                        disposition=disposition,
                    )
                )

        return call_with_upstream_retry(
            call,
            max_attempts=self._max_attempts,
            sleep=self._sleep,
            on_attempt_failure=report_failure,
        )


def _urlopen_json(
    request: Request, *, timeout_seconds: float, label: str
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError(f"{label} response was not an object")
            headers = {
                str(name).casefold(): str(value)
                for name, value in getattr(response, "headers", {}).items()
            }
            return decoded, headers
    except HTTPError as exc:
        message = f"{label} request failed ({exc.code})"
        if is_retryable_upstream_fault(exc):
            raise RetryableUpstreamError(message) from exc
        raise RuntimeError(message) from exc
    except URLError as exc:
        raise RetryableUpstreamError(f"{label} request failed") from exc
    except TimeoutError as exc:
        raise RetryableUpstreamError(f"{label} request timed out") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} response was invalid JSON") from exc


def parse_openai_chat_completion(
    body: dict[str, Any],
    headers: dict[str, str],
    *,
    requested_model: str,
) -> ProviderMessageResult:
    normalized_headers = {name.casefold(): value for name, value in headers.items()}
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
    input_tokens = _required_nonnegative_int(usage.get("prompt_tokens"), "input token count")
    output_tokens = _required_nonnegative_int(usage.get("completion_tokens"), "output token count")
    total_tokens_value = usage.get("total_tokens")
    total_tokens = (
        _required_nonnegative_int(total_tokens_value, "total token count")
        if total_tokens_value is not None
        else None
    )
    billing_units_value = total_tokens if total_tokens is not None else usage.get("billing_units")
    billing_units = _required_nonnegative_int(billing_units_value, "provider billing units")
    cost_usd = _provider_cost(usage.get("cost"))

    metadata = body.get("openrouter_metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise RuntimeError("upstream response has malformed router metadata")
    resolved_provider = _optional_string(metadata, "provider", "router metadata")
    metadata_model = _optional_string(metadata, "model", "router metadata")
    resolved_model = _optional_string(body, "model", "model") or metadata_model
    model_version = _optional_string(body, "model_version", "model version")

    prompt_details = usage.get("prompt_tokens_details")
    if prompt_details is not None and not isinstance(prompt_details, dict):
        raise RuntimeError("upstream response has invalid prompt token details")
    completion_details = usage.get("completion_tokens_details")
    if completion_details is not None and not isinstance(completion_details, dict):
        raise RuntimeError("upstream response has invalid completion token details")
    cached_tokens = _optional_nonnegative_int(prompt_details, "cached_tokens", "cached token count")
    reasoning_tokens = _optional_nonnegative_int(
        completion_details, "reasoning_tokens", "reasoning token count"
    )
    cache_status = normalized_headers.get("x-openrouter-cache-status", "").casefold()
    cache_age_seconds = _optional_header_nonnegative_int(
        normalized_headers, "x-openrouter-cache-age"
    )

    return ProviderMessageResult(
        message_id=message_id,
        output_text=output_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        billing_units=billing_units,
        cost_usd=cost_usd,
        provider="openrouter",
        resolved_provider=resolved_provider,
        requested_model=requested_model,
        resolved_model=resolved_model,
        model_version=model_version,
        cache_hit=cache_status == "hit",
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_age_seconds=cache_age_seconds,
    )


def _required_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"upstream response has invalid {field}")
    return value


def _optional_nonnegative_int(
    container: dict[str, Any] | None, field: str, description: str
) -> int | None:
    if container is None or field not in container:
        return None
    return _required_nonnegative_int(container[field], description)


def _provider_cost(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise RuntimeError("upstream response has invalid provider cost")
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError("upstream response has invalid provider cost") from exc
    if not cost.is_finite() or cost < 0:
        raise RuntimeError("upstream response has invalid provider cost")
    return cost


def _optional_string(
    container: dict[str, Any] | None, field: str, description: str
) -> str | None:
    if container is None or field not in container:
        return None
    value = container[field]
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"upstream response has malformed {description}")
    return value


def _optional_header_nonnegative_int(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"upstream response has invalid {name}") from exc
    if parsed < 0:
        raise RuntimeError(f"upstream response has invalid {name}")
    return parsed
