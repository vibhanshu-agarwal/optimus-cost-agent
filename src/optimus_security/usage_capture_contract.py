"""The usage-capture upload contract, version 1 (Plan 12.8; ADR-032). Neutral: the ACP host builds batches and the
Gateway's `POST /v1/observability/usage-capture` validates them, through this one module.

A batch carries one stream's framed outbox lines verbatim, so the Gateway re-verifies every digest and the chain
itself rather than trusting the host's reading. `after` names the prefix the sender believes is committed. The
acknowledgement names the ledger instance, stream, sequence and digest the ledger committed, and only a committed
acknowledgement may authorize the sender's compaction.

Request: ``{"schema_version": 1, "writer": "host"|"gateway", "stream_id": <32 hex>, "after": {"sequence": int,
"digest": <64 hex>}, "records": [<framed line>, ...]}``. Unknown keys are refused. Limits are agent-selected.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from optimus_security.durable_outbox import GAP_KIND, GENESIS, Record, parse_line

SCHEMA_VERSION = 1
MAX_RECORDS = 256
MAX_BODY_BYTES = 1024 * 1024
PATH = "/v1/observability/usage-capture"

STREAM_START = "stream.start"
STREAM_END = "stream.end"
EPOCH_BEGIN = "epoch.begin"
EPOCH_CLOSE = "epoch.close"
INVOCATION_OPEN = "invocation.open"
INVOCATION_END = "invocation.end"
ATTEMPT_INTENT = "attempt.intent"
ATTEMPT_RECEIPT = "attempt.receipt"
INTEGRITY_FAILURE = "integrity.failure"
GATEWAY_ATTEMPT_INTENT = "gateway.attempt.intent"
GATEWAY_ATTEMPT_OUTCOME = "gateway.attempt.outcome"
_SHARED_KINDS = frozenset({STREAM_START, STREAM_END, GAP_KIND})
KINDS_BY_WRITER: Mapping[str, frozenset[str]] = {
    "host": _SHARED_KINDS
    | {EPOCH_BEGIN, EPOCH_CLOSE, INVOCATION_OPEN, INVOCATION_END, ATTEMPT_INTENT, ATTEMPT_RECEIPT, INTEGRITY_FAILURE},
    "gateway": _SHARED_KINDS | {GATEWAY_ATTEMPT_INTENT, GATEWAY_ATTEMPT_OUTCOME},
}
_HEX32 = re.compile(r"[0-9a-f]{32}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_REQUEST_KEYS = frozenset({"schema_version", "writer", "stream_id", "after", "records"})
_ACK_KEYS = frozenset({"status", "ledger_instance", "stream_id", "sequence", "digest", "conflicts"})


class ContractError(ValueError):
    """``code``: too_large, malformed, unknown_field, schema, writer, stream, limit, record, kind or order."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CaptureBatch:
    writer: str
    stream_id: str
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


def build_batch(writer: str, stream_id: str, after_sequence: int, after_digest: str, records: Sequence[Record]) -> bytes:
    document = {
        "schema_version": SCHEMA_VERSION,
        "writer": writer,
        "stream_id": stream_id,
        "after": {"sequence": after_sequence, "digest": after_digest},
        "records": [record.line.decode("ascii") for record in records],
    }
    return json.dumps(document, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def parse_batch(body: bytes) -> CaptureBatch:
    """A strictly validated batch: its own shape and limits, every line's digest, writer-appropriate kinds and the
    stream it claims. Ordering against the committed prefix is the ledger's check (`durable_outbox.follows`)."""
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
    writer, stream_id, after, lines = document["writer"], document["stream_id"], document["after"], document["records"]
    if writer not in KINDS_BY_WRITER:
        raise ContractError("writer")
    if not isinstance(stream_id, str) or not _HEX32.fullmatch(stream_id):
        raise ContractError("stream")
    if not (isinstance(after, dict) and set(after) == {"sequence", "digest"}):
        raise ContractError("malformed")
    sequence, digest = after["sequence"], after["digest"]
    if type(sequence) is not int or sequence < 0 or not isinstance(digest, str) or not (_HEX64.fullmatch(digest) or digest == GENESIS):
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
        if record.payload.get("kind") not in KINDS_BY_WRITER[writer]:
            raise ContractError("kind")
        records.append(record)
    if any(later.sequence <= earlier.sequence for earlier, later in zip(records, records[1:], strict=False)):
        raise ContractError("order")
    return CaptureBatch(writer, stream_id, sequence, digest, tuple(records))


def build_ack(ack: CaptureAck) -> dict[str, Any]:
    return {"status": "committed", "ledger_instance": ack.ledger_instance, "stream_id": ack.stream_id,
            "sequence": ack.sequence, "digest": ack.digest, "conflicts": ack.conflicts}


def parse_ack(document: object, *, stream_id: str) -> CaptureAck:
    """A committed acknowledgement for ``stream_id``, or `ContractError`. Anything else authorizes no compaction."""
    if not isinstance(document, dict) or set(document) != _ACK_KEYS or document.get("status") != "committed":
        raise ContractError("malformed")
    ledger, stream, sequence, digest, conflicts = (document[k] for k in ("ledger_instance", "stream_id", "sequence", "digest", "conflicts"))
    if stream != stream_id or not isinstance(ledger, str) or not _HEX32.fullmatch(ledger):
        raise ContractError("stream")
    if type(sequence) is not int or sequence < 1 or not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        raise ContractError("malformed")
    if type(conflicts) is not int or conflicts < 0:
        raise ContractError("malformed")
    return CaptureAck(ledger, stream, sequence, digest, conflicts)
