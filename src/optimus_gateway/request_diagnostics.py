"""Request-scoped, log-only diagnostics for the Gateway's two model routes (Plan 12.2 correction plan v4, C1, C2, C9).

The server handles each request on its own thread, retries included, so one thread-local context carries what the
request's log lines need and its response must never show: the legacy path's Gateway request id, a Stage C ledger
write failure, and a log-safe refusal text. ``do_POST`` opens it, ``_finish`` reads it into the log line, and it is
cleared once the reply is sent. Nothing here is merged into a response body.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
from typing import Any

from optimus_model_policy.experimental import EXPERIMENTAL_ROUTES
from optimus_security.failure_facts import UNRECOGNIZED, bounded, bounded_failure, final_sanitize, gateway_request_id

_STATE = threading.local()
_LOG_LOCK = threading.Lock()


def begin() -> None:
    """Open this thread's request context."""
    _STATE.facts = {}


def end() -> None:
    """Clear this thread's request context."""
    _STATE.facts = None


def note(**facts: Any) -> None:
    """Record log-only facts for the current request; a no-op outside one."""
    current = getattr(_STATE, "facts", None)
    if current is not None:
        current.update(facts)


def noted() -> dict[str, Any]:
    """The current request's log-only facts; empty outside a request."""
    return dict(getattr(_STATE, "facts", None) or {})


def write_log_line(line: str) -> None:
    """One locked write to the Gateway's log (its stderr, persisted as ``local-gateway.log``): concurrent lines never
    interleave, and a failed or closed stream never stops the request it describes."""
    with _LOG_LOCK, contextlib.suppress(OSError, ValueError):
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


_CLASSIFICATIONS = frozenset({"transient", "permanent"})
_DISPOSITIONS = frozenset({"retry", "terminal"})


def log_model_attempt(event: Any) -> None:
    """The production upstream client's retry observer: one ``model_attempt`` line per failed legacy attempt, with its
    origin cause and the request's Gateway id (C9). Contained: a diagnostic never changes a retry."""
    try:
        attempt = event.attempt
        record = {
            "event": "model_attempt",
            "gateway_request_id": gateway_request_id(noted().get("gateway_request_id")),
            "attempt": attempt if type(attempt) is int else None,
            "classification": bounded(event.classification, _CLASSIFICATIONS),
            "disposition": bounded(event.disposition, _DISPOSITIONS),
            "failure": bounded_failure(getattr(event, "failure", None)),
        }
        write_log_line(json.dumps(final_sanitize(record), separators=(",", ":"), sort_keys=True, default=str))
    except Exception:  # noqa: BLE001 - a diagnostic never fails the request it describes
        return


# --- Recognized upstream metadata for the log (C1): a value from trusted, code-shipped or registry data, else
# ``unrecognized``. The reply checks keep using the original values.

_ROUTE_PROVIDERS = frozenset(name for route in EXPERIMENTAL_ROUTES.values() for name in (route.provider_family, route.provider_name))
_ROUTE_MODELS = frozenset(route.model_id for route in EXPERIMENTAL_ROUTES.values())
RECOGNIZED_FINISH = frozenset({"stop", "length", "content_filter", "tool_calls", "error"})


def _registry(policy: Any) -> tuple[frozenset[str], frozenset[str]]:
    if policy is None:
        return frozenset(), frozenset()
    models = policy.snapshot.policy.models
    return frozenset(models), frozenset(provider for entry in models.values() for provider in entry.route.providers)


def recognized_provider(value: object, policy: Any = None) -> str | None:
    """A router provider recognized by the closed mapping: an experimental route's slug or display name (``anthropic``,
    ``Anthropic``) or a registry endpoint's provider slug."""
    try:
        return bounded(value, _ROUTE_PROVIDERS | _registry(policy)[1])
    except Exception:  # noqa: BLE001 - an unreadable registry recognizes nothing
        return None if value is None else UNRECOGNIZED


def recognized_model(value: object, policy: Any = None) -> str | None:
    """A model id from the trusted registry, or an experimental route's."""
    try:
        return bounded(value, _ROUTE_MODELS | _registry(policy)[0])
    except Exception:  # noqa: BLE001 - an unreadable registry recognizes nothing
        return None if value is None else UNRECOGNIZED
