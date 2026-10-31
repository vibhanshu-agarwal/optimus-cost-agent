"""The usage-capture contract, version 1 (Plan 12.8; ADR-032). Neutral: the ACP host and the Gateway write records of
these kinds, the host builds upload batches and the Gateway's `POST /v1/observability/usage-capture` validates them,
all through this one module.

Every record payload has a pinned schema per kind: exactly its keys, each of a stated type, strings and lists
bounded. Nothing else persists, so no prompt, reply, router payload, exception text or credential can ride along.

A batch carries one stream's framed outbox lines verbatim, so the Gateway re-verifies every digest and the chain itself
rather than trusting the host's reading. `after` names the prefix the sender believes committed and `ledger_instance`
the ledger it believes committed it (null before any acknowledgement). The acknowledgement names the ledger instance,
stream, sequence and digest the ledger committed; only a committed acknowledgement may authorize compaction.

Request: ``{"schema_version": 1, "writer": "host"|"gateway", "stream_id": <32 hex>, "ledger_instance": <32 hex>|null,
"after": {"sequence": int, "digest": <64 hex>}, "records": [<framed line>, ...]}``. Unknown keys are refused. Limits
are agent-selected; any one record fits in a batch (`durable_outbox.MAX_RECORD_BYTES`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from optimus_security.durable_outbox import GAP_KIND, GENESIS, STREAM_END_KIND, Record, parse_line

SCHEMA_VERSION = 1
MAX_RECORDS = 256
MAX_BODY_BYTES = 1024 * 1024
MAX_STRING = 512
MAX_LIST = 256  # identity lists beyond this continue in further `epoch.identities` parts
PATH = "/v1/observability/usage-capture"
# The host request a model call serves, sent by the host and read by the Gateway; never forwarded to a provider.
CAPTURE_REQUEST_HEADER = "X-Optimus-Capture-Request"
CAPTURE_REQUEST_ID = re.compile(r"[A-Za-z0-9:._-]{1,512}")

STREAM_START = "stream.start"
STREAM_END = STREAM_END_KIND
EPOCH_BEGIN = "epoch.begin"
EPOCH_TERMINAL = "epoch.terminal"
EPOCH_IDENTITIES = "epoch.identities"
EPOCH_CLOSE = "epoch.close"
INVOCATION_OPEN = "invocation.open"
INVOCATION_END = "invocation.end"
ATTEMPT_INTENT = "attempt.intent"
ATTEMPT_RECEIPT = "attempt.receipt"
INTEGRITY_FAILURE = "integrity.failure"
GATEWAY_ATTEMPT_INTENT = "gateway.attempt.intent"
GATEWAY_ATTEMPT_OUTCOME = "gateway.attempt.outcome"

STAGES = frozenset({"planning", "answer", "summarization", "classification", "operation"})
OUTCOMES = frozenset({"completed", "failed", "not_sent", "rejected", "uncertain", "unattributed"})

_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DECIMAL = re.compile(r"(0|[1-9][0-9]{0,30})(\.[0-9]{1,30})?")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(\+00:00|Z)")
_DIGEST = re.compile(r"hex:[0-9a-f]{64}")
PURPOSE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)+")

Check = Callable[[object], bool]


def _string(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= MAX_STRING


def _optional(check: Check) -> Check:
    return lambda value: value is None or check(value)


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def _matches(pattern: re.Pattern[str]) -> Check:
    return lambda value: isinstance(value, str) and pattern.fullmatch(value) is not None


def _one_of(choices: frozenset[str]) -> Check:
    return lambda value: isinstance(value, str) and value in choices


def _strings(value: object) -> bool:
    return isinstance(value, list) and len(value) <= MAX_LIST and all(_string(item) for item in value)


def _optional_strings(value: object) -> bool:
    return isinstance(value, list) and len(value) <= MAX_LIST and all(item is None or _string(item) for item in value)


def _boolean(value: object) -> bool:
    return type(value) is bool


_S, _S_, _N, _N_, _B = _string, _optional(_string), _count, _optional(_count), _boolean
_AT = _matches(_TIMESTAMP)
_ID = _matches(_HEX32)
_ID_ = _optional(_ID)
_USD = _matches(_DECIMAL)
_USD_ = _optional(_USD)

_USAGE_SCHEMA: dict[str, Check] = {
    "gateway_request_id": _S, "provider": _S, "provider_request_id": _S_, "billing_units": _N, "cost_usd": _USD,
    "service": _S_, "native_unit": _S_, "model": _S_, "model_version": _S_, "price_snapshot_id": _S_,
    "resolved_provider": _S_, "resolved_model": _S_, "input_tokens": _N_, "output_tokens": _N_, "total_tokens": _N_,
    "reasoning_tokens": _N_, "cached_tokens": _N_, "cache_age_seconds": _N_, "route_request_id": _S_, "attempt": _N_,
}
_USAGE_OPTIONAL: dict[str, Check] = {"cache_hit": _B}


def _epoch_ids(value: object) -> bool:
    return isinstance(value, list) and len(value) <= MAX_LIST and all(_ID(item) for item in value)


def _usage(value: object) -> bool:
    return value is None or _conforms(value, _USAGE_SCHEMA, _USAGE_OPTIONAL)


SCHEMAS: dict[str, dict[str, Check]] = {
    STREAM_START: {"kind": _S, "at": _AT},
    STREAM_END: {"kind": _S, "at": _AT, "open_epochs": _epoch_ids},
    GAP_KIND: {"kind": _S, "unconfirmed_from": _N, "unconfirmed_to": _N},
    EPOCH_BEGIN: {"kind": _S, "at": _AT, "epoch_id": _ID, "turn_id": _S, "session_id": _S_},
    EPOCH_TERMINAL: {"kind": _S, "at": _AT, "epoch_id": _ID, "turn_id": _S, "pending_invocations": _N},
    EPOCH_IDENTITIES: {
        "kind": _S, "at": _AT, "epoch_id": _ID, "part": _N, "parts": _N, "settled_attempt_ids": _strings,
        "unknown_attempt_ids": _strings,
    },
    EPOCH_CLOSE: {
        "kind": _S, "at": _AT, "epoch_id": _ID, "turn_id": _S, "identity_parts": _N, "settled_count": _N,
        "unknown_count": _N, "identities_digest": _matches(_DIGEST), "pending_invocations": _N, "integrity_failures": _N,
        "known_subtotal_usd": _USD, "intents": _N, "unconfirmed_intents": _N, "rejected_records": _N,
        "begin_confirmed": _B, "host_complete": _B,
    },
    INVOCATION_OPEN: {"kind": _S, "at": _AT, "epoch_id": _ID, "invocation_id": _ID},
    INVOCATION_END: {"kind": _S, "at": _AT, "epoch_id": _ID_, "invocation_id": _ID, "state": _one_of(frozenset({"ended", "abandoned"}))},
    ATTEMPT_INTENT: {
        "kind": _S, "at": _AT, "epoch_id": _ID, "host_request_id": _S, "stage": _one_of(STAGES),
        "purpose": _matches(PURPOSE), "requested_model": _S_,
    },
    ATTEMPT_RECEIPT: {
        "kind": _S, "at": _AT, "epoch_id": _ID, "late": _B, "session_id": _S_, "turn_id": _S, "stage": _one_of(STAGES),
        "purpose": _matches(PURPOSE), "attempt_id": _S, "gateway_request_id": _S_, "outcome": _one_of(OUTCOMES),
        "reported_cost_usd": _USD_, "recorded_at": _AT, "requested_model": _S_, "role": _S_, "route": _strings,
        "reasoning": _S_, "quantizations": _optional_strings, "resolved_model": _S_, "provider": _S_,
        "resolved_provider": _S_, "strategy": _S_, "revision_digest": _S_, "registry_hash": _S_, "input_tokens": _N_,
        "output_tokens": _N_, "cached_tokens": _N_, "provider_request_id": _S_, "http_status": _N_, "post_teardown": _B,
        "usage": _usage, "facts_digest": _matches(_DIGEST), "settled_digest": _matches(_DIGEST),
    },
    INTEGRITY_FAILURE: {
        "kind": _S, "at": _AT, "epoch_id": _ID_, "turn_id": _S, "late": _B,
        "reason": _one_of(frozenset({"receipt_conflict", "ledger_refused"})),
    },
    GATEWAY_ATTEMPT_INTENT: {"kind": _S, "at": _AT, "gateway_request_id": _S, "host_request_id": _S_, "attempt": _N, "route": _S_},
    GATEWAY_ATTEMPT_OUTCOME: {
        "kind": _S, "at": _AT, "gateway_request_id": _S, "attempt": _N, "outcome": _one_of(OUTCOMES), "http_status": _N_,
        "cost_usd": _USD_, "billing_units": _N_,
    },
}
_SHARED_KINDS = frozenset({STREAM_START, STREAM_END, GAP_KIND})
KINDS_BY_WRITER: Mapping[str, frozenset[str]] = {
    "host": _SHARED_KINDS
    | {EPOCH_BEGIN, EPOCH_TERMINAL, EPOCH_IDENTITIES, EPOCH_CLOSE, INVOCATION_OPEN, INVOCATION_END, ATTEMPT_INTENT,
       ATTEMPT_RECEIPT, INTEGRITY_FAILURE},
    "gateway": _SHARED_KINDS | {GATEWAY_ATTEMPT_INTENT, GATEWAY_ATTEMPT_OUTCOME},
}
_REQUEST_KEYS = frozenset({"schema_version", "writer", "stream_id", "ledger_instance", "after", "records"})
_ACK_KEYS = frozenset({"status", "ledger_instance", "stream_id", "sequence", "digest", "conflicts"})


def _conforms(value: object, schema: Mapping[str, Check], optional: Mapping[str, Check] | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    optional = optional or {}
    keys = set(value)
    if not set(schema) <= keys or keys - set(schema) - set(optional):
        return False
    return all(schema[key](value[key]) for key in schema) and all(optional[key](value[key]) for key in keys & set(optional))


class ContractError(ValueError):
    """``code``: too_large, malformed, unknown_field, schema, writer, stream, limit, record, kind, payload or order."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_payload(payload: object, *, writer: str) -> str:
    """The payload's kind if it is one ``writer`` may write and it matches that kind's schema exactly."""
    kind = payload.get("kind") if isinstance(payload, dict) else None
    if not isinstance(kind, str) or kind not in KINDS_BY_WRITER.get(writer, frozenset()):
        raise ContractError("kind")
    if not _conforms(payload, SCHEMAS[kind]):
        raise ContractError("payload")
    return kind


@dataclass(frozen=True)
class CaptureBatch:
    writer: str
    stream_id: str
    ledger_instance: str | None
    after_sequence: int
    after_digest: str
    records: tuple[Record, ...]


@dataclass(frozen=True)
class CaptureAck:
    """What the ledger committed: every record of the stream up to and including ``sequence`` / ``digest``."""

    ledger_instance: str
    stream_id: str
    sequence: int
    digest: str
    conflicts: int = 0


def build_batch(writer: str, stream_id: str, ledger_instance: str | None, after_sequence: int, after_digest: str,
                records: Sequence[Record]) -> bytes:
    document = {
        "schema_version": SCHEMA_VERSION,
        "writer": writer,
        "stream_id": stream_id,
        "ledger_instance": ledger_instance,
        "after": {"sequence": after_sequence, "digest": after_digest},
        "records": [record.line.decode("ascii") for record in records],
    }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def parse_batch(body: bytes) -> CaptureBatch:
    """A strictly validated batch: its own shape and limits, every line's digest, writer-appropriate kinds, each
    payload's schema and the stream it claims. Ordering against the committed prefix is the ledger's check
    (`durable_outbox.follows`)."""
    if len(body) > MAX_BODY_BYTES:
        raise ContractError("too_large")
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ContractError("malformed") from None
    if not isinstance(document, dict):
        raise ContractError("malformed")
    if set(document) != _REQUEST_KEYS:
        raise ContractError("unknown_field" if set(document) - _REQUEST_KEYS else "malformed")
    if document["schema_version"] != SCHEMA_VERSION:
        raise ContractError("schema")
    writer, stream_id, ledger, after, lines = (document[k] for k in ("writer", "stream_id", "ledger_instance", "after", "records"))
    if not isinstance(writer, str) or writer not in KINDS_BY_WRITER:
        raise ContractError("writer")
    if not _ID(stream_id) or not _ID_(ledger):
        raise ContractError("stream")
    if not (isinstance(after, dict) and set(after) == {"sequence", "digest"}):
        raise ContractError("malformed")
    sequence, digest = after["sequence"], after["digest"]
    if not _count(sequence) or not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
        raise ContractError("malformed")
    if (sequence == 0) != (digest == GENESIS):
        raise ContractError("malformed")
    if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_RECORDS:
        raise ContractError("limit")
    records = []
    for line in lines:
        if not isinstance(line, str):
            raise ContractError("record")
        try:
            record = parse_line(line.encode("ascii"))
        except (ValueError, UnicodeEncodeError):
            raise ContractError("record") from None
        if record.stream_id != stream_id:
            raise ContractError("stream")
        validate_payload(record.payload, writer=writer)
        records.append(record)
    if any(later.sequence <= earlier.sequence for earlier, later in zip(records, records[1:], strict=False)):
        raise ContractError("order")
    return CaptureBatch(writer, stream_id, ledger, sequence, digest, tuple(records))


def build_ack(ack: CaptureAck) -> dict[str, Any]:
    return {"status": "committed", "ledger_instance": ack.ledger_instance, "stream_id": ack.stream_id,
            "sequence": ack.sequence, "digest": ack.digest, "conflicts": ack.conflicts}


def parse_ack(document: object, *, stream_id: str) -> CaptureAck:
    """A committed acknowledgement for ``stream_id``, or `ContractError`. Anything else authorizes no compaction."""
    if not isinstance(document, dict) or set(document) != _ACK_KEYS or document.get("status") != "committed":
        raise ContractError("malformed")
    ledger, stream, sequence, digest, conflicts = (document[k] for k in ("ledger_instance", "stream_id", "sequence", "digest", "conflicts"))
    if stream != stream_id or not _ID(ledger):
        raise ContractError("stream")
    if not (_count(sequence) and sequence >= 1 and isinstance(digest, str) and _HEX64.fullmatch(digest) and _count(conflicts)):
        raise ContractError("malformed")
    return CaptureAck(ledger, stream, sequence, digest, conflicts)
