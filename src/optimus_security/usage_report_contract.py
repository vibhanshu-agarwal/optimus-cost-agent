"""The usage-report contract, version 1 (Plan 12.9; ADR-034). Neutral: the ACP host builds requests and validates
responses, and the Gateway's `POST /v1/observability/usage-report` parses requests and builds responses, through this
one module. The host never reads Postgres (ADR-032): every ledger fact it shows arrives in a response shaped here.

Requests:
- ``{"schema_version": 1, "operation": "capabilities"}``: what this Gateway supports, with no database access. A host
  emits a capture kind added after Plan 12.8 (`FEATURE_REPORT_CONTEXT`) only to a Gateway that lists it, because an
  older Gateway refuses an unknown kind and that stops the stream's delivery.
- ``{"schema_version": 1, "operation": "report", "session_id": str, "turn_id": str|null, "reference_ids":
  [id]|null, "page_size": 1..100, "cursor": str|null, "expected_turns": int|null}``: one session (D2), optionally one
  turn. ``expected_turns`` is how many turns the host itself ran in the session, so a turn the ledger never received
  keeps the scope incomplete. A cursor continues exactly the request that produced it.

Money is decimal text; a null is unknown, never zero. Error bodies are ``{"schema_version": 1, "status": "error",
"code": <ERROR_CODES>}`` and never carry exception text, SQL, paths or credentials. Limits are agent-selected.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = 1
PATH = "/v1/observability/usage-report"
MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGE = 100
MAX_ATTEMPTS = 10_000  # per selected scope; above it the totals are unavailable rather than truncated
MAX_TURNS = 10_000
REFERENCE_GROUP = 3  # comparison columns per page: a transport bound, not a product rule
MAX_REFERENCE_IDS = 64
MAX_STRING = 512

FEATURE_REPORT = "usage-report-v1"
FEATURE_REPORT_CONTEXT = "capture.turn.report_context"

# Stable codes and their HTTP status.
ERROR_CODES: Mapping[str, int] = {
    "REQUEST_INVALID": 400,
    "UNAUTHORIZED": 401,
    "REPORT_CHANGED": 409,
    "REQUEST_TOO_LARGE": 413,
    "ACCOUNTING_NOT_CONFIGURED": 503,
    "LEDGER_UNAVAILABLE": 503,
    "REPORT_BUSY": 503,
    "REPORT_TIMEOUT": 504,
}

# Coverage reason codes: why a scope's totals are not definitive.
COVERAGE_REASONS = frozenset({
    "epoch_missing", "epoch_open", "epoch_incomplete", "turn_not_captured", "unknown_cost", "receipt_conflict",
    "late_receipt", "delivery_pending", "scope_too_large", "attribution_unavailable",
})
# Why an attempt could not be repriced for a reference.
UNPRICED_REASONS = frozenset({
    "tokens_unreported", "cached_split_unreported", "reasoning_split_unreported", "categories_inconsistent",
    "price_missing_input", "price_missing_cached_input", "price_missing_output",
})
# Why a comparison column is not complete, besides its unpriced attempts.
COLUMN_REASONS = frozenset({"source_date_missing", "unpriced_attempts", "actual_incomplete", "no_attempts"})

# Exact user-facing labels (plan v2, design 5). The renderer uses these and nothing looser.
LABELS: Mapping[str, str] = {
    "measured": "Measured known provider cost",
    "coverage_complete": "Coverage: complete for the stated scope",
    "coverage_incomplete": "Coverage: incomplete — {reasons}",
    "history": "History before durable capture: qualified; billing completeness unavailable",
    "b1": "Estimated B1 — same reported tokens at reference prices; not realized savings",
    "auto": "Auto comparison — configured reference models; not measured Auto-off results",
    "auto_question": "What would these same reported tokens cost at each reference's dated list prices? Not a "
                     "prediction of calls, context, retries, output or quality under another model or with Auto off.",
    "b2": "Estimated B2 — no-optimization counterfactual",
    "b2_unavailable": "Unavailable — no qualifying no-optimization workload evidence",
    "b3": "B3 — matched measured comparisons",
    "b3_unavailable": "No qualifying matched-run comparison available",
    "b4": "B4 — benchmark context only",
    "unavailable": "Unavailable: {what} — {reason}",
    "not_definitive": "Definitive net savings and percentage unavailable",
    "cache_writes": "Cache-write charges are not captured, so no reference column includes them.",
}

_ID32 = re.compile(r"[0-9a-f]{32}")
_DIGEST = re.compile(r"hex:[0-9a-f]{64}")
_DECIMAL = re.compile(r"(0|[1-9][0-9]{0,30})(\.[0-9]{1,30})?")
_SIGNED = re.compile(r"-?(0|[1-9][0-9]{0,30})(\.[0-9]{1,30})?")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(\+00:00|Z)")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_REFERENCE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_CURSOR = re.compile(r"[A-Za-z0-9_-]{1,2048}\.[0-9a-f]{64}")

Check = Callable[[object], bool]


class ContractError(ValueError):
    """``code`` names what was wrong; the Gateway answers every one of them as ``REQUEST_INVALID``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _string(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_STRING


def _optional(check: Check) -> Check:
    return lambda value: value is None or check(value)


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _boolean(value: object) -> bool:
    return type(value) is bool


def _matches(pattern: re.Pattern[str]) -> Check:
    return lambda value: isinstance(value, str) and pattern.fullmatch(value) is not None


def _one_of(choices: frozenset[str]) -> Check:
    return lambda value: isinstance(value, str) and value in choices


def _list_of(check: Check, limit: int) -> Check:
    return lambda value: isinstance(value, list) and len(value) <= limit and all(check(item) for item in value)


def _object(schema: Mapping[str, Check]) -> Check:
    return lambda value: _conforms(value, schema)


def _conforms(value: object, schema: Mapping[str, Check]) -> bool:
    return isinstance(value, dict) and set(value) == set(schema) and all(schema[key](value[key]) for key in schema)


_S, _S_, _N, _N_, _B = _string, _optional(_string), _count, _optional(_count), _boolean
_USD, _USD_, _SIGNED_ = _matches(_DECIMAL), _optional(_matches(_DECIMAL)), _optional(_matches(_SIGNED))
_SELECTION_ = _optional(_one_of(frozenset({"auto", "fixed"})))

# --- Requests --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportRequest:
    session_id: str
    turn_id: str | None
    reference_ids: tuple[str, ...] | None
    page_size: int
    cursor: str | None
    expected_turns: int | None


_CAPABILITIES_KEYS = frozenset({"schema_version", "operation"})
_REPORT_SCHEMA: dict[str, Check] = {
    "schema_version": lambda v: v == SCHEMA_VERSION, "operation": lambda v: v == "report", "session_id": _S,
    "turn_id": _S_, "reference_ids": _optional(_list_of(_matches(_REFERENCE_ID), MAX_REFERENCE_IDS)),
    "page_size": lambda v: type(v) is int and 1 <= v <= MAX_PAGE, "cursor": _optional(_matches(_CURSOR)),
    "expected_turns": _N_,
}


def build_request(request: ReportRequest | None) -> bytes:
    """The request body: a report for ``request``, or the capabilities request for None."""
    if request is None:
        document: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "operation": "capabilities"}
    else:
        document = {
            "schema_version": SCHEMA_VERSION, "operation": "report", "session_id": request.session_id,
            "turn_id": request.turn_id,
            "reference_ids": None if request.reference_ids is None else list(request.reference_ids),
            "page_size": request.page_size, "cursor": request.cursor, "expected_turns": request.expected_turns,
        }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def parse_request(body: bytes) -> ReportRequest | None:
    """A strictly validated request (None is the capabilities request), or `ContractError`."""
    if len(body) > MAX_REQUEST_BYTES:
        raise ContractError("too_large")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ContractError("malformed") from None
    if not isinstance(document, dict):
        raise ContractError("malformed")
    if document.get("operation") == "capabilities" and set(document) == _CAPABILITIES_KEYS:
        if document["schema_version"] != SCHEMA_VERSION:
            raise ContractError("schema")
        return None
    if not _conforms(document, _REPORT_SCHEMA):
        raise ContractError("schema")
    ids = document["reference_ids"]
    if ids is not None and len(ids) != len(set(ids)):
        raise ContractError("schema")
    return ReportRequest(document["session_id"], document["turn_id"], None if ids is None else tuple(ids),
                         document["page_size"], document["cursor"], document["expected_turns"])


def error_body(code: str) -> tuple[int, dict[str, Any]]:
    return ERROR_CODES[code], {"schema_version": SCHEMA_VERSION, "status": "error", "code": code}


def capabilities_body() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "status": "ok", "features": [FEATURE_REPORT, FEATURE_REPORT_CONTEXT],
            "max_page": MAX_PAGE, "reference_group": REFERENCE_GROUP}


# --- Cursors ---------------------------------------------------------------------------------------
# Opaque to the host. The Gateway seals the request it continues (principal, scope, reference selection, revision,
# reference offset and last detail key) under a key only it holds; any change answers REPORT_CHANGED.


def seal_cursor(key: bytes, fields: Mapping[str, Any]) -> str:
    body = base64.urlsafe_b64encode(json.dumps(dict(fields), sort_keys=True, separators=(",", ":"),
                                               ensure_ascii=True).encode("ascii")).rstrip(b"=").decode("ascii")
    return body + "." + hmac.new(key, body.encode("ascii"), hashlib.sha256).hexdigest()


def open_cursor(key: bytes, cursor: str) -> dict[str, Any]:
    """The sealed fields, or `ContractError("cursor")` for anything not sealed under ``key``."""
    if not _CURSOR.fullmatch(cursor):
        raise ContractError("cursor")
    body, mac = cursor.split(".")
    if not hmac.compare_digest(hmac.new(key, body.encode("ascii"), hashlib.sha256).hexdigest(), mac):
        raise ContractError("cursor")
    try:
        fields = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, binascii.Error):
        raise ContractError("cursor") from None
    if not isinstance(fields, dict):
        raise ContractError("cursor")
    return fields


# --- Responses -------------------------------------------------------------------------------------

_TOTALS: dict[str, Check] = {
    "known_usd": _USD, "attempts": _N, "unknown_attempts": _N, "conflicts": _N, "late": _N, "turns": _N,
    "definitive": _B, "reasons": _list_of(_one_of(COVERAGE_REASONS), len(COVERAGE_REASONS)),
}
_UNPRICED: dict[str, Check] = {"reason": _one_of(UNPRICED_REASONS), "attempts": _N, "tokens": _N_}
_COLUMN: dict[str, Check] = {
    "reference_id": _matches(_REFERENCE_ID), "display": _S, "snapshot_id": _matches(_DIGEST), "source": _S,
    "price_as_of": _optional(_matches(_DATE)), "baseline_known_usd": _USD, "priced_attempts": _N,
    "unpriced": _list_of(_object(_UNPRICED), len(UNPRICED_REASONS)), "complete": _B,
    "reasons": _list_of(_one_of(COLUMN_REASONS), len(COLUMN_REASONS)), "savings_usd": _SIGNED_,
    "savings_percent": _SIGNED_,
}
_ROW: dict[str, Check] = {
    "turn_id": _S, "attempt_id": _S, "stage": _S, "purpose": _S, "outcome": _S, "cost_usd": _USD_, "selection": _SELECTION_,
    "requested_model": _S_, "resolved_model": _S_, "provider": _S_, "input_tokens": _N_, "output_tokens": _N_,
    "cached_tokens": _N_, "reasoning_tokens": _N_, "late": _B, "conflict": _B,
}
_BENCHMARK: dict[str, Check] = {"text": _S, "limitations": _S, "source": _S, "as_of": _optional(_matches(_DATE))}
_REPORT_RESPONSE: dict[str, Check] = {
    "schema_version": lambda v: v == SCHEMA_VERSION, "status": lambda v: v == "ok",
    "ledger_instance": _matches(_ID32), "as_of": _matches(_TIMESTAMP), "revision": _matches(_DIGEST),
    "scope": _object({"session_id": _S, "turn_id": _S_}),
    "session": _object(_TOTALS), "auto": _object(_TOTALS),
    "attribution": _object({"auto_turns": _N, "fixed_turns": _N, "unattributed_turns": _N}),
    "comparisons": _object({"offset": _N, "total": _N, "columns": _list_of(_object(_COLUMN), REFERENCE_GROUP)}),
    "detail": _list_of(_object(_ROW), MAX_PAGE), "next_cursor": _optional(_matches(_CURSOR)),
    "b2": _object({"state": lambda v: v == "unavailable"}), "b3": _object({"state": lambda v: v == "unavailable"}),
    "benchmark": _optional(_object(_BENCHMARK)),
}


def validate_report(document: object) -> dict[str, Any]:
    """The host's check of a report response: exactly this shape, or `ContractError("response")`."""
    if not _conforms(document, _REPORT_RESPONSE):
        raise ContractError("response")
    return document  # type: ignore[return-value]


def validate_capabilities(document: object) -> frozenset[str]:
    """The features a capabilities response lists, or `ContractError("response")`."""
    schema: dict[str, Check] = {
        "schema_version": lambda v: v == SCHEMA_VERSION, "status": lambda v: v == "ok",
        "features": _list_of(_S, 32), "max_page": _N, "reference_group": _N,
    }
    if not _conforms(document, schema):
        raise ContractError("response")
    return frozenset(document["features"])  # type: ignore[index]
