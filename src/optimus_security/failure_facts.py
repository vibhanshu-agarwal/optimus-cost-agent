"""Bounded, content-free failure facts (Plan 12.2, operator directive 2026-10-20: every failure path persists its cause,
from precise logs, never hypotheses). One place for the Gateway and the host: an exception's class, its first cause's
class and errno, an allowlisted category, a slug of a module-authored reason, and a final redaction pass. None of
them ever records exception text, a body, a prompt, a reply or a credential."""

from __future__ import annotations

import re
from typing import Any

from optimus_security.sanitization import sanitize_for_persistence

UNRECOGNIZED = "unrecognized"
_CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}")
_SLUG_SOURCE = re.compile(r"[a-z0-9 _.()-]{1,120}")


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
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def bounded_failure(failure: object) -> dict[str, Any] | None:
    """A failure cause received from another component, re-bounded before it is persisted: an allowlisted kind,
    class names of the safe shape, an integer errno and a slug-shaped reason. Every other key is dropped."""
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
    if "reason" in failure:
        reason = failure["reason"]
        kept["reason"] = reason if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,120}", reason) else UNRECOGNIZED
    return kept


def bounded_id(value: object) -> str | None:
    """A request id of the plain id shape (``gw-…``, ``gen-…``), ``unrecognized`` otherwise, None for None."""
    if value is None:
        return None
    return value if isinstance(value, str) and _ID.fullmatch(value) else UNRECOGNIZED


def final_sanitize(record: dict[str, Any]) -> dict[str, Any]:
    """The last redaction pass over a selected diagnostic record before it is written. A failure keeps only the
    record's keys, never a raw value."""
    try:
        cleaned = sanitize_for_persistence(record).value
    except Exception:  # noqa: BLE001 - a diagnostic never fails the request it describes
        return {key: UNRECOGNIZED for key in record}
    return cleaned if isinstance(cleaned, dict) else {key: UNRECOGNIZED for key in record}
