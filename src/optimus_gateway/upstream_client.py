from __future__ import annotations

import errno
import json
import socket
import ssl
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from typing import Any, Literal, Protocol, TypeVar
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus_model_policy.binding import ATTEMPT_NOT_SENT, ATTEMPT_REJECTED, ATTEMPT_UNCERTAIN

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
    finish_reason: str | None = None
    """The provider's own finish status, lower-cased (``stop``, ``length``, ...); ``None`` when the
    provider reported none. Never synthesized (Plan 12.2 Task 5)."""


class UpstreamClient(Protocol):
    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        """Call an upstream LLM API and return normalized text + usage (today's routing)."""

    def create_message_once(
        self,
        *,
        model: str,
        input_text: str,
        max_tokens: int,
        provider_controls: Mapping[str, Any],
        reasoning: str | None,
    ) -> ProviderMessageResult:
        """One provider attempt under an enforced model policy; raises UpstreamAttemptFailure."""


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

    def _request(self, payload: Mapping[str, Any]) -> Request:
        return Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "content-type": "application/json",
                "X-OpenRouter-Metadata": "enabled",
            },
            method="POST",
        )

    def create_message(self, *, model: str, input_text: str) -> ProviderMessageResult:
        """Today's routing: one request with the legacy transient-fault retry loop."""
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
        }
        request = self._request(payload)

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

    def create_message_once(
        self,
        *,
        model: str,
        input_text: str,
        max_tokens: int,
        provider_controls: Mapping[str, Any],
        reasoning: str | None,
    ) -> ProviderMessageResult:
        """Exactly one provider attempt under an enforced model policy (Plan 12.2 Task 5).

        No retry happens here: the Gateway decides, per the attempt contract, whether a failed attempt
        may be followed by one recovery attempt. A failure raises :class:`UpstreamAttemptFailure` saying
        whether the request certainly never reached a model or may have run and been billed.

        Wire mapping v1: the output cap is OpenRouter's ``max_tokens``, the approved endpoints are its
        ``provider`` routing object, and the approved reasoning level is ``reasoning.effort``.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
            "max_tokens": max_tokens,
            "provider": json.loads(json.dumps(dict(provider_controls))),
        }
        if reasoning is not None:
            payload["reasoning"] = {"effort": reasoning}
        request = self._request(payload)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
                headers = {str(name).casefold(): str(value) for name, value in getattr(response, "headers", {}).items()}
        except HTTPError as exc:
            # A 4xx (other than a request timeout) is the provider refusing the request before any
            # model ran; a 408 or 5xx may follow a model run that was billed.
            refused = 400 <= exc.code < 500 and exc.code != 408
            raise UpstreamAttemptFailure(ATTEMPT_REJECTED if refused else ATTEMPT_UNCERTAIN, http_status=exc.code) from exc
        except URLError as exc:
            # urllib raises URLError only while connecting and sending. A refused connection, an
            # unresolved or unreachable host, or a failed TLS handshake delivers no request, so no
            # model ran. A timeout cannot be told apart from one after the request went out, so it
            # stays uncertain (Fable CP1 correction review, m4).
            raise UpstreamAttemptFailure(ATTEMPT_NOT_SENT if _never_sent(exc.reason) else ATTEMPT_UNCERTAIN) from exc
        except (OSError, HTTPException) as exc:
            # A timeout, reset or truncated body after sending: the model may have run.
            raise UpstreamAttemptFailure(ATTEMPT_UNCERTAIN) from exc
        try:
            decoded = json.loads(raw.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError("upstream response was not an object")
            return parse_openai_chat_completion(decoded, headers, requested_model=model)
        except (UnicodeError, ValueError, RuntimeError) as exc:
            # A reply arrived but its usage cannot be verified: it may have been billed.
            raise UpstreamAttemptFailure(ATTEMPT_UNCERTAIN) from exc


_UNREACHABLE_ERRNOS = frozenset({errno.ENETUNREACH, errno.EHOSTUNREACH})


def _never_sent(reason: object) -> bool:
    if isinstance(reason, (ConnectionRefusedError, socket.gaierror, ssl.SSLError)):
        return True
    return isinstance(reason, OSError) and not isinstance(reason, TimeoutError) and reason.errno in _UNREACHABLE_ERRNOS


class UpstreamAttemptFailure(Exception):
    """One enforced provider attempt that did not complete, and what is known about it."""

    def __init__(self, outcome: str, *, http_status: int | None = None) -> None:
        self.outcome = outcome
        self.http_status = http_status
        super().__init__(f"upstream attempt {outcome}" + (f" ({http_status})" if http_status is not None else ""))

    @property
    def recoverable(self) -> bool:
        """True only when the attempt certainly reached no model: never sent, or rate-limited (429)."""
        return self.outcome == ATTEMPT_NOT_SENT or (self.outcome == ATTEMPT_REJECTED and self.http_status == 429)


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
    # A missing or malformed finish status reads as None ("not reported"): it is never trusted as
    # complete, and the billed call keeps its usage either way (Plan 12.2 Task 5).
    raw_finish = first.get("finish_reason")
    finish_reason = raw_finish.strip().casefold() if isinstance(raw_finish, str) and raw_finish.strip() else None

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
        finish_reason=finish_reason,
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
