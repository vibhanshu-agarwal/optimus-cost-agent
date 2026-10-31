"""The Gateway's minimal capture stream (Plan 12.8; ADR-032): one intent before and one outcome after each physical
upstream model attempt. It exists only for what the host cannot see: a legacy route's internal retries, a reply lost on
the way back, or a host that died mid-call. It is evidence correlated by the host request header, never a receipt
store or a second debit: the host's settlement stays the only accounting.

Process-wide like the request diagnostics: the launch configures one writer (`configure`), the server opens and closes
each request's context (`begin` / `end`), the routes name the request or attempt ID they minted (`set_request`), and
the upstream client wraps each physical attempt (`physical_attempt`). Unconfigured, every call is a no-op. Capture
never refuses or delays an attempt beyond the outbox's short acknowledgement wait.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError

from optimus_security import usage_capture_contract as uc
from optimus_security.durable_outbox import ACK_WAIT_SECONDS, OutboxWriter

_STATE = threading.local()
_writer: OutboxWriter | None = None
_ack_wait = ACK_WAIT_SECONDS


def configure(writer: OutboxWriter | None, *, ack_wait: float = ACK_WAIT_SECONDS) -> None:
    global _writer, _ack_wait
    _writer, _ack_wait = writer, ack_wait


def begin(host_request_id: str | None) -> None:
    """Open this thread's request context with the host request it serves (None when the header was absent or malformed)."""
    _STATE.host_request_id = host_request_id if host_request_id and uc.CAPTURE_REQUEST_ID.fullmatch(host_request_id) else None
    _STATE.gateway_request_id = None
    _STATE.ordinals = {}


def end() -> None:
    _STATE.host_request_id = _STATE.gateway_request_id = None
    _STATE.ordinals = {}


def set_request(gateway_request_id: str) -> None:
    """The Gateway request (legacy) or attempt (enforced, decisions) ID the next physical attempts belong to."""
    _STATE.gateway_request_id = gateway_request_id


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _http_status(exc: BaseException) -> int | None:
    """The provider's HTTP status, raw or from the bounded failure fact the legacy client attaches; else None."""
    if isinstance(exc, HTTPError):
        return exc.code
    failure = getattr(exc, "failure", None)
    status = failure.get("status") if isinstance(failure, dict) and failure.get("kind") == "http" else None
    return status if type(status) is int else None


@contextmanager
def physical_attempt() -> Iterator[None]:
    """Record one physical upstream attempt around its I/O: completed, failed with its HTTP status, or uncertain."""
    writer = _writer
    gateway_request_id = getattr(_STATE, "gateway_request_id", None)
    if writer is None or gateway_request_id is None:
        yield
        return
    ordinals: dict[str, Any] = getattr(_STATE, "ordinals", None) or {}
    _STATE.ordinals = ordinals
    counter = ordinals.setdefault(gateway_request_id, itertools.count(1))
    number = next(counter)
    writer.submit(
        {"kind": uc.GATEWAY_ATTEMPT_INTENT, "at": _now(), "gateway_request_id": gateway_request_id,
         "host_request_id": getattr(_STATE, "host_request_id", None), "attempt": number, "route": None}
    ).wait(_ack_wait)
    outcome, status = "uncertain", None
    try:
        yield
        outcome = "completed"
    except BaseException as exc:
        status = _http_status(exc)
        outcome = "failed" if status is not None else "uncertain"
        raise
    finally:
        writer.submit(
            {"kind": uc.GATEWAY_ATTEMPT_OUTCOME, "at": _now(), "gateway_request_id": gateway_request_id, "attempt": number,
             "outcome": outcome, "http_status": status, "cost_usd": None, "billing_units": None}
        )
