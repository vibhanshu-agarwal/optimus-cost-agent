"""Canonical immutable ledger entry contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .canonical import canonical_json
from .errors import LedgerValidationError

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_PART_CHARS = 64 * 1024
_MAX_PART_BYTES = 64 * 1024
_CLIENT_DRAFT_FIELDS = frozenset(
    {
        "kind",
        "schema_id",
        "context_id",
        "recipient_agent_ids",
        "message",
        "task_id",
        "in_reply_to",
        "artifacts",
        "attestation",
    }
)
_SERVER_OWNED_FIELDS = frozenset(
    {
        "sequence",
        "ledger_instance_id",
        "entry_id",
        "principal_id",
        "agent_id",
        "caller_role",
        "authority",
        "created_at",
        "prev_content_sha256",
        "content_sha256",
        "idempotency_key",
    }
)


class EntryKind(StrEnum):
    QUESTION = "question"
    ANSWER = "answer"
    EVIDENCE_NOTICE = "evidence-notice"
    REVIEW_RULING = "review-ruling"
    HANDOFF = "handoff"
    ACKNOWLEDGEMENT = "acknowledgement"


class SchemaId(StrEnum):
    QUESTION = "question.v1"
    ANSWER = "answer.v1"
    EVIDENCE_NOTICE = "evidence-notice.v1"
    REVIEW_RULING = "review-ruling.v1"
    HANDOFF = "handoff.v1"
    ACKNOWLEDGEMENT = "acknowledgement.v1"


SCHEMA_ID_BY_KIND: dict[EntryKind, str] = {
    EntryKind.QUESTION: SchemaId.QUESTION.value,
    EntryKind.ANSWER: SchemaId.ANSWER.value,
    EntryKind.EVIDENCE_NOTICE: SchemaId.EVIDENCE_NOTICE.value,
    EntryKind.REVIEW_RULING: SchemaId.REVIEW_RULING.value,
    EntryKind.HANDOFF: SchemaId.HANDOFF.value,
    EntryKind.ACKNOWLEDGEMENT: SchemaId.ACKNOWLEDGEMENT.value,
}

ACTIVE_WRITER_KINDS = frozenset({EntryKind.REVIEW_RULING})


@dataclass(frozen=True, slots=True)
class MessagePart:
    kind: str
    text: str | None = None
    data: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"text", "data"}:
            raise LedgerValidationError("invalid_message_part_kind")
        if self.kind == "text":
            if not isinstance(self.text, str):
                raise LedgerValidationError("invalid_message_part_text")
            if len(self.text) > _MAX_PART_CHARS:
                raise LedgerValidationError("message_part_too_large")
            if self.data is not None:
                raise LedgerValidationError("invalid_message_part_data")
        else:
            if self.data is None or not isinstance(self.data, Mapping):
                raise LedgerValidationError("invalid_message_part_data")
            if self.text is not None:
                raise LedgerValidationError("invalid_message_part_text")
            encoded = canonical_json(dict(self.data))
            if len(encoded) > _MAX_PART_BYTES:
                raise LedgerValidationError("message_part_too_large")

    def to_mapping(self) -> dict[str, Any]:
        if self.kind == "text":
            return {"kind": "text", "text": self.text}
        return {"kind": "data", "data": dict(self.data or {})}


@dataclass(frozen=True, slots=True)
class EntryMessage:
    parts: tuple[MessagePart, ...]

    def __post_init__(self) -> None:
        if not self.parts:
            raise LedgerValidationError("message_parts_required")

    def to_mapping(self) -> dict[str, Any]:
        return {"parts": [part.to_mapping() for part in self.parts]}


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    name: str
    content_sha256: str
    uri: str | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise LedgerValidationError("invalid_artifact_name")
        if not _SHA256_RE.fullmatch(self.content_sha256):
            raise LedgerValidationError("malformed_sha256")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "content_sha256": self.content_sha256,
            "uri": self.uri,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class EntryDraft:
    """Client-authorable draft. Server-owned fields are rejected, not overwritten."""

    kind: EntryKind
    schema_id: str
    context_id: str
    recipient_agent_ids: tuple[str, ...]
    message: EntryMessage
    task_id: str | None = None
    in_reply_to: str | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    attestation: None = None

    def __post_init__(self) -> None:
        if self.kind not in ACTIVE_WRITER_KINDS:
            raise LedgerValidationError("writer_kind_inactive")
        if self.schema_id != SCHEMA_ID_BY_KIND[self.kind]:
            raise LedgerValidationError("schema_kind_mismatch")
        if not self.context_id.strip():
            raise LedgerValidationError("context_id_required")
        if not self.recipient_agent_ids:
            raise LedgerValidationError("recipients_required")
        if len(self.recipient_agent_ids) != len(set(self.recipient_agent_ids)):
            raise LedgerValidationError("duplicate_recipients")
        if any(not agent_id.strip() for agent_id in self.recipient_agent_ids):
            raise LedgerValidationError("invalid_recipient")
        if self.attestation is not None:
            raise LedgerValidationError("attestation_must_be_null")

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> EntryDraft:
        unexpected = sorted(set(values) & _SERVER_OWNED_FIELDS)
        if unexpected:
            raise LedgerValidationError("unexpected_server_owned_field")
        unknown = sorted(set(values) - _CLIENT_DRAFT_FIELDS)
        if unknown:
            raise LedgerValidationError("unknown_field")
        kind = EntryKind(str(values["kind"]))
        message_raw = values.get("message") or {}
        parts_raw = message_raw.get("parts") or ()
        parts = tuple(
            MessagePart(
                kind=str(part["kind"]),
                text=part.get("text"),
                data=part.get("data"),
            )
            for part in parts_raw
        )
        artifacts_raw = values.get("artifacts") or ()
        artifacts = tuple(
            ArtifactRef(
                name=str(item["name"]),
                content_sha256=str(item["content_sha256"]),
                uri=item.get("uri"),
                media_type=item.get("media_type"),
            )
            for item in artifacts_raw
        )
        recipients = tuple(str(item) for item in values.get("recipient_agent_ids") or ())
        return cls(
            kind=kind,
            schema_id=str(values["schema_id"]),
            context_id=str(values["context_id"]),
            recipient_agent_ids=recipients,
            message=EntryMessage(parts=parts),
            task_id=values.get("task_id"),
            in_reply_to=values.get("in_reply_to"),
            artifacts=artifacts,
            attestation=values.get("attestation"),
        )


@dataclass(frozen=True, slots=True)
class SanitizedDraft:
    """Sanitized client payload ready for transactional append."""

    kind: EntryKind
    schema_id: str
    context_id: str
    recipient_agent_ids: tuple[str, ...]
    message: EntryMessage
    artifacts: tuple[ArtifactRef, ...]
    task_id: str | None
    in_reply_to: str | None
    rule_counts: Mapping[str, int]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "schema_id": self.schema_id,
            "context_id": self.context_id,
            "recipient_agent_ids": list(self.recipient_agent_ids),
            "message": self.message.to_mapping(),
            "artifacts": [item.to_mapping() for item in self.artifacts],
            "task_id": self.task_id,
            "in_reply_to": self.in_reply_to,
            "rule_counts": dict(self.rule_counts),
        }

    def request_fingerprint(self) -> dict[str, Any]:
        """Sanitized request identity used for idempotency comparison."""
        return {
            "kind": self.kind.value,
            "schema_id": self.schema_id,
            "context_id": self.context_id,
            "recipient_agent_ids": list(self.recipient_agent_ids),
            "message": self.message.to_mapping(),
            "artifacts": [item.to_mapping() for item in self.artifacts],
            "task_id": self.task_id,
            "in_reply_to": self.in_reply_to,
        }


@dataclass(frozen=True, slots=True)
class ServerIdentity:
    principal_id: str
    agent_id: str
    caller_role: str
    authority: str


@dataclass(frozen=True, slots=True)
class ImmutableEntryEnvelope:
    sequence: int
    ledger_instance_id: str
    entry_id: str
    schema_id: str
    kind: EntryKind
    context_id: str
    task_id: str | None
    in_reply_to: str | None
    recipient_agent_ids: tuple[str, ...]
    message: EntryMessage
    artifacts: tuple[ArtifactRef, ...]
    principal_id: str
    agent_id: str
    caller_role: str
    authority: str
    attestation: None
    created_at: str
    idempotency_key: str
    prev_content_sha256: str | None
    content_sha256: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "ledger_instance_id": self.ledger_instance_id,
            "entry_id": self.entry_id,
            "schema_id": self.schema_id,
            "kind": self.kind.value,
            "context_id": self.context_id,
            "task_id": self.task_id,
            "in_reply_to": self.in_reply_to,
            "recipient_agent_ids": list(self.recipient_agent_ids),
            "message": self.message.to_mapping(),
            "artifacts": [item.to_mapping() for item in self.artifacts],
            "principal_id": self.principal_id,
            "agent_id": self.agent_id,
            "caller_role": self.caller_role,
            "authority": self.authority,
            "attestation": self.attestation,
            "created_at": self.created_at,
            "idempotency_key": self.idempotency_key,
            "prev_content_sha256": self.prev_content_sha256,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True, slots=True)
class AppendResult:
    entry_id: str
    sequence: int
    ledger_instance_id: str
    content_sha256: str
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedRange:
    entries: tuple[ImmutableEntryEnvelope, ...]
    start: int
    watermark: int


@dataclass(frozen=True, slots=True)
class IntegrityWitness:
    ledger_instance_id: str
    last_committed: int
    last_content_sha256: str | None
    verified: bool


@dataclass(frozen=True, slots=True)
class StoreStatus:
    ledger_instance_id: str
    last_committed: int
    last_content_sha256: str | None


__all__ = [
    "ACTIVE_WRITER_KINDS",
    "AppendResult",
    "ArtifactRef",
    "EntryDraft",
    "EntryKind",
    "EntryMessage",
    "ImmutableEntryEnvelope",
    "IntegrityWitness",
    "MessagePart",
    "SCHEMA_ID_BY_KIND",
    "SanitizedDraft",
    "SchemaId",
    "ServerIdentity",
    "StoreStatus",
    "VerifiedRange",
]
