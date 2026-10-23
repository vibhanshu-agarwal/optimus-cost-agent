"""Bounded, content-free failure facts (Plan 12.2, operator directive 2026-10-20: every failure path persists its cause,
from precise logs, never hypotheses). One place for the Gateway and the host: an exception's class, its first cause's
class and errno, an allowlisted category, a slug of a module-authored reason, field-specific id projections and a
final redaction pass. None of them ever records exception text, a body, a prompt, a reply or a credential."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from optimus_security.sanitization import (
    _RECOGNIZED_PREFIXES,
    COMPATIBILITY_SANITIZATION_POLICY,
    sanitize_for_persistence,
)

UNRECOGNIZED = "unrecognized"
_CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_SLUG_SOURCE = re.compile(r"[a-z0-9 _.()\[\]:-]{1,120}")

# The last pass over a diagnostic record: the compatibility rules plus credential-prefix detection, so a bare key
# (``sk-or-v1-...``) is redacted too. Entropy detection stays off: it would erase the real request ids kept below.
DIAGNOSTICS_SANITIZATION_POLICY = replace(COMPATIBILITY_SANITIZATION_POLICY, version="diagnostics-v1", enable_prefix_detection=True)


def _class_name(value: object) -> str:
    name = type(value).__name__
    return name if _CLASS_NAME.fullmatch(name) else UNRECOGNIZED


def exception_fact(exc: BaseException) -> dict[str, Any]:
    """The exception's class, its first cause's class (``URLError.reason``, else ``__cause__``), and the first errno
    found on either. Never their text."""
    fact: dict[str, Any] = {"class": _class_name(exc)}
    reason = getattr(exc, "reason", None)
    cause = reason if isinstance(reason, BaseException) else exc.__cause__
    if cause is not None:
        fact["cause"] = _class_name(cause)
    number = next((getattr(item, "errno", None) for item in (exc, cause) if isinstance(getattr(item, "errno", None), int)), None)
    fact["errno"] = number
    return fact


def bounded(value: object, allowed: frozenset[str]) -> str | None:
    """``value`` when it is one of the allowlisted strings, ``unrecognized`` for anything else, None for None."""
    if value is None:
        return None
    return value if isinstance(value, str) and value in allowed else UNRECOGNIZED


def slug(reason: object) -> str:
    """A module-authored reason as a snake_case slug; anything outside the plain lower-case shape is ``unrecognized``."""
    if not isinstance(reason, str) or not _SLUG_SOURCE.fullmatch(reason):
        return UNRECOGNIZED
    return re.sub(r"[^a-z0-9]+", "_", reason).strip("_") or UNRECOGNIZED


FAILURE_KINDS = frozenset(
    {"http", "transport", "invalid_utf8", "invalid_json", "schema", "usage_contract", "gateway_invalid_json", "gateway_non_object_json"}
)


def bounded_failure(failure: object) -> dict[str, Any] | None:
    """A failure cause received from another component, re-bounded before it is persisted: an allowlisted kind,
    class names of the safe shape, an integer errno, an HTTP status and a slug-shaped reason. Every other key is
    dropped."""
    if not isinstance(failure, dict):
        return None
    kept: dict[str, Any] = {"kind": bounded(failure.get("kind"), FAILURE_KINDS)}
    for key in ("class", "cause"):
        if key in failure:
            value = failure[key]
            kept[key] = value if isinstance(value, str) and _CLASS_NAME.fullmatch(value) else UNRECOGNIZED
    if "errno" in failure:
        number = failure["errno"]
        kept["errno"] = number if isinstance(number, int) and not isinstance(number, bool) else None
    if "status" in failure:
        status = failure["status"]
        kept["status"] = status if type(status) is int and 100 <= status <= 599 else None
    if "reason" in failure:
        reason = failure["reason"]
        kept["reason"] = reason if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,120}", reason) else UNRECOGNIZED
    return kept


# --- An OpenRouter `guardrail` router stage's closed facts (#400, agreed handling D, Codex round 39) ---------------
# Only literals OpenRouter's router-metadata and guardrails guides enumerate are recognized (retained 2026-10-23 in
# the #400 evidence). The guides name `decision` but list no value. None of these facts proves a stage left the
# request or reply unchanged, so the empirical route still refuses every guardrail stage.

MISSING, INVALID = "missing", "invalid"
GUARDRAIL_ACTIONS = frozenset({"blocked"})
GUARDRAIL_DECISIONS: frozenset[str] = frozenset()
GUARDRAIL_SCOPES = frozenset({"api-key"})
_GUARDRAIL_STATES = frozenset({UNRECOGNIZED, MISSING, INVALID})
_GUARDRAIL_BOOLEANS = ("flagged", "detected")
_GUARDRAIL_LITERALS = {"decision": GUARDRAIL_DECISIONS, "action": GUARDRAIL_ACTIONS, "guardrail_scope": GUARDRAIL_SCOPES}


def _guardrail_boolean(container: object, key: str) -> bool | str:
    if not isinstance(container, dict):
        return INVALID
    if key not in container:
        return MISSING
    value = container[key]
    return value if isinstance(value, bool) else INVALID


def _guardrail_literal(container: object, key: str, allowed: frozenset[str]) -> str:
    if not isinstance(container, dict):
        return INVALID
    if key not in container:
        return MISSING
    value = container[key]
    if not isinstance(value, str):
        return INVALID
    return value if value in allowed else UNRECOGNIZED


def guardrail_stage_facts(stage: dict[str, Any]) -> dict[str, Any]:
    """One guardrail stage's closed, content-free facts: `flagged` and `detected` as a Boolean or `missing`/`invalid`
    (never coerced); `decision` and `action` apart, each a documented literal or `unrecognized`/`missing`/`invalid`;
    whether both are present and differ; and `guardrail_scope`, diagnostic only. Never its name, id, summary,
    patterns, entity labels or any other data."""
    data = stage.get("data", {})
    # Presence is the key, never its value: an explicit null verdict is present (Codex round 40, finding 4).
    both = isinstance(data, dict) and "decision" in data and "action" in data
    return {
        **{key: _guardrail_boolean(data, key) for key in _GUARDRAIL_BOOLEANS},
        "decision": _guardrail_literal(data, "decision", GUARDRAIL_DECISIONS),
        "action": _guardrail_literal(data, "action", GUARDRAIL_ACTIONS),
        "verdict_conflict": both and data["decision"] != data["action"],
        "guardrail_scope": _guardrail_literal(stage, "guardrail_scope", GUARDRAIL_SCOPES),
    }


def bounded_guardrail_list(received: object) -> list[dict[str, Any] | str] | str:
    """A received ``router_guardrails`` value, re-bounded: each entry's facts, or ``invalid`` for an entry that is no
    object, or ``invalid`` for a container that is no list (Codex round 40, finding 1). Never raises, so a diagnostic
    can never invalidate the attempt it describes."""
    if not isinstance(received, (list, tuple)):
        return INVALID
    return [bounded_guardrail_facts(facts) or INVALID for facts in received]


def bounded_guardrail_facts(facts: object) -> dict[str, Any] | None:
    """Guardrail facts received from another component, re-bounded before they are persisted; every other key is
    dropped."""
    if not isinstance(facts, dict):
        return None
    kept: dict[str, Any] = {}
    for key in _GUARDRAIL_BOOLEANS:
        value = facts.get(key, MISSING)
        kept[key] = value if isinstance(value, bool) or value in (MISSING, INVALID) else INVALID
    for key, allowed in _GUARDRAIL_LITERALS.items():
        value = facts.get(key, MISSING)
        if not isinstance(value, str):
            kept[key] = INVALID
        else:
            kept[key] = value if value in allowed or value in _GUARDRAIL_STATES else UNRECOGNIZED
    conflict = facts.get("verdict_conflict")
    kept["verdict_conflict"] = conflict if isinstance(conflict, bool) else INVALID
    return {key: kept[key] for key in ("flagged", "detected", "decision", "action", "verdict_conflict", "guardrail_scope")}


# --- Field-specific id projections (correction plan v4, C1): a value of the field's generated shape, else
# ``unrecognized``; None for None. A shape check alone would keep a bare credential, so each field has its own.

_GATEWAY_REQUEST_ID = re.compile(r"gw-[0-9a-f]{32}")
_PROVIDER_REQUEST_ID = re.compile(r"gen-[A-Za-z0-9_-]{1,96}")
_HOST_SESSION_ID = re.compile(r"session-[0-9a-f]{32}")
# `{session_id}:{turn_seq}` (a turn's run id), optionally `:{stage}:{ordinal}:{uuid hex}` (a route or summary request).
_HOST_ROUTE_ID = re.compile(r"session-[0-9a-f]{32}:[0-9]{1,9}(?::[a-z_]{1,32}:[0-9]{1,9}:[0-9a-f]{32})?")
_RPC_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _shaped(value: object, shape: re.Pattern[str]) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) and shape.fullmatch(value) else UNRECOGNIZED


def gateway_request_id(value: object) -> str | None:
    """The Gateway's own attempt or request id, ``gw-`` and 32 lower-case hex digits."""
    return _shaped(value, _GATEWAY_REQUEST_ID)


def provider_request_id(value: object) -> str | None:
    """OpenRouter's generation id, ``gen-…`` (the only configured provider)."""
    return _shaped(value, _PROVIDER_REQUEST_ID)


def host_session_id(value: object) -> str | None:
    """A host session id, ``session-`` and 32 lower-case hex digits."""
    return _shaped(value, _HOST_SESSION_ID)


def host_route_id(value: object) -> str | None:
    """A host run id (``session-…:<turn>``) or a route or summary request id (``…:<stage>:<n>:<uuid hex>``)."""
    return _shaped(value, _HOST_ROUTE_ID)


def host_run_of(value: object) -> str | None:
    """The run id that prefixes a recognized host route or summary request id, else None."""
    projected = host_route_id(value)
    if projected is None or projected == UNRECOGNIZED:
        return None
    return ":".join(projected.split(":")[:2])


def rpc_request_id(value: object) -> int | str | None:
    """A client JSON-RPC id: an integer (never a bool), or a short plain token that does not start like a credential."""
    if value is None:
        return None
    if type(value) is int:
        return value
    if isinstance(value, str) and _RPC_ID.fullmatch(value) and not value.startswith(_RECOGNIZED_PREFIXES):
        return value
    return UNRECOGNIZED


def final_sanitize(record: dict[str, Any]) -> dict[str, Any]:
    """The last redaction pass over a selected diagnostic record before it is written. A failure keeps only the
    record's keys, never a raw value."""
    try:
        cleaned = sanitize_for_persistence(record, policy=DIAGNOSTICS_SANITIZATION_POLICY).value
    except Exception:  # noqa: BLE001 - a diagnostic never fails the request it describes
        return {key: UNRECOGNIZED for key in record}
    return cleaned if isinstance(cleaned, dict) else {key: UNRECOGNIZED for key in record}
