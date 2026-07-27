"""Shared, sanitized HTTP transport for Gateway tool providers."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from optimus_gateway.upstream_client import (
    RetryableUpstreamError,
    call_with_upstream_retry,
    is_retryable_upstream_fault,
)


class ToolProviderError(RuntimeError):
    """Sanitized provider failure safe to expose at the Gateway boundary."""


def request_json(
    request: Request,
    *,
    label: str,
    urlopen_fn: Callable[..., object] = urlopen,
    timeout_seconds: float = 60.0,
    sleep: Callable[[float], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Execute one JSON request with the Gateway's shared bounded retry seam."""

    def call() -> dict[str, Any]:
        try:
            with urlopen_fn(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if is_retryable_upstream_fault(exc):
                raise RetryableUpstreamError(f"{label} transient HTTP failure") from None
            raise RuntimeError(f"{label} HTTP failure") from None
        except (URLError, TimeoutError) as exc:
            if is_retryable_upstream_fault(exc):
                raise RetryableUpstreamError(f"{label} network failure") from None
            raise RuntimeError(f"{label} network failure") from None
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise RuntimeError(f"{label} response failure") from None
        if not isinstance(body, dict):
            raise RuntimeError(f"{label} response was not an object")
        return body

    try:
        return call_with_upstream_retry(call, sleep=sleep, on_retry=on_retry)
    except Exception:
        raise ToolProviderError(f"{label} failed") from None


def request_bytes(
    request: Request,
    *,
    label: str,
    urlopen_fn: Callable[..., object] = urlopen,
    timeout_seconds: float = 60.0,
    sleep: Callable[[float], None] | None = None,
    on_retry: Callable[[int], None] | None = None,
) -> bytes:
    """Execute a non-JSON request with the same retry and sanitization policy."""

    def call() -> bytes:
        try:
            with urlopen_fn(request, timeout=timeout_seconds) as response:
                return response.read()
        except HTTPError as exc:
            if is_retryable_upstream_fault(exc):
                raise RetryableUpstreamError(f"{label} transient HTTP failure") from None
            raise RuntimeError(f"{label} HTTP failure") from None
        except (URLError, TimeoutError) as exc:
            if is_retryable_upstream_fault(exc):
                raise RetryableUpstreamError(f"{label} network failure") from None
            raise RuntimeError(f"{label} network failure") from None
        except (OSError, UnicodeError):
            raise RuntimeError(f"{label} response failure") from None

    try:
        return call_with_upstream_retry(call, sleep=sleep, on_retry=on_retry)
    except Exception:
        raise ToolProviderError(f"{label} failed") from None
