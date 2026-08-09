"""Principal mapping and role policy for ledger appends.

Authority, caller_role, and agent_id are server-derived. Client supply is a
closed-schema rejection. Implementer review-ruling writes are refused before
ingress and sequence assignment. Recipients must be known enrolled agents.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from evidence_handoff.ledger.errors import LedgerStoreError, LedgerValidationError
from evidence_handoff.ledger.models import EntryDraft, EntryKind, ServerIdentity
from evidence_handoff.redaction.ingress import IngressRejection, StructuredIngress
from evidence_handoff_runtime.auth import AuthenticatedPrincipal, AuthError, CredentialValidator
from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

_CLOSED_SCHEMA_FIELDS = frozenset(
    {"authority", "caller_role", "agent_id", "principal_id", "attestation"}
)
_REVIEWER_ROLE = "reviewer"
_SAFE_READ_FIELDS = frozenset(
    {"entry_id", "sequence", "ledger_instance_id", "content_sha256"}
)


class PolicyError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"PolicyError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    identity: ServerIdentity
    code: str = "ok"

    @staticmethod
    def for_append(
        *,
        principal: AuthenticatedPrincipal,
        kind: str,
        client_fields: Mapping[str, Any],
    ) -> PolicyDecision:
        for field in _CLOSED_SCHEMA_FIELDS:
            if field not in client_fields:
                continue
            value = client_fields[field]
            if field == "attestation":
                if value is not None:
                    raise PolicyError("closed_schema_field_rejected")
                continue
            raise PolicyError("closed_schema_field_rejected")
        if kind != EntryKind.REVIEW_RULING.value:
            raise PolicyError("role_not_permitted")
        if principal.caller_role != _REVIEWER_ROLE:
            raise PolicyError("role_not_permitted")
        identity = ServerIdentity(
            principal_id=principal.principal_id,
            agent_id=principal.agent_id,
            caller_role=principal.caller_role,
            authority="review-ruling",
        )
        return PolicyDecision(allowed=True, identity=identity)


def validate_recipients(
    recipients: list[str] | tuple[str, ...],
    *,
    known_agent_ids: frozenset[str],
    retired_agent_ids: frozenset[str] = frozenset(),
) -> None:
    """Reject empty, duplicate, unknown, retired, wildcard, and alias recipients."""
    if not recipients:
        raise PolicyError("recipients_required")
    if len(recipients) != len(set(recipients)):
        raise PolicyError("duplicate_recipients")
    for agent_id in recipients:
        value = str(agent_id)
        if not value.strip():
            raise PolicyError("invalid_recipient")
        if value == "*":
            raise PolicyError("wildcard_recipient")
        if value.startswith("role:"):
            raise PolicyError("role_alias_recipient")
        if value.startswith("context:"):
            raise PolicyError("context_alias_recipient")
        if value in retired_agent_ids:
            raise PolicyError("retired_recipient")
        if value not in known_agent_ids:
            raise PolicyError("unknown_recipient")


def _validate_recipients(
    recipients: list[str] | tuple[str, ...],
    *,
    known_agent_ids: frozenset[str],
    retired_agent_ids: frozenset[str] = frozenset(),
) -> None:
    validate_recipients(
        recipients,
        known_agent_ids=known_agent_ids,
        retired_agent_ids=retired_agent_ids,
    )


def _entry_draft_from_client_fields(client_fields: Mapping[str, Any]) -> EntryDraft:
    """Build EntryDraft from structured message or legacy message_text.

    Legacy message_text is adapted into a single text part so the real
    StructuredIngress(EntryDraft) path always runs (including final scan).
    """
    values: dict[str, Any] = {
        "kind": str(client_fields.get("kind") or EntryKind.REVIEW_RULING.value),
        "schema_id": str(client_fields.get("schema_id") or "review-ruling.v1"),
        "context_id": str(client_fields["context_id"]),
        "recipient_agent_ids": list(client_fields.get("recipient_agent_ids") or ()),
        "task_id": client_fields.get("task_id"),
        "in_reply_to": client_fields.get("in_reply_to"),
        "artifacts": list(client_fields.get("artifacts") or ()),
        "attestation": client_fields.get("attestation"),
    }
    if "message" in client_fields and client_fields["message"] is not None:
        values["message"] = client_fields["message"]
    elif "message_text" in client_fields:
        values["message"] = {
            "parts": [{"kind": "text", "text": str(client_fields.get("message_text") or "")}]
        }
    else:
        raise PolicyError("message_required")
    try:
        return EntryDraft.from_mapping(values)
    except LedgerValidationError as exc:
        raise PolicyError(exc.code) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise PolicyError("invalid_entry_draft") from exc


def _authenticate(
    *,
    authorization_header: str,
    session_id: str,
    protocol_version: str,
    ledger_instance_id: str,
    validator: CredentialValidator,
    sessions: SessionRegistry,
    required_scope: str,
) -> AuthenticatedPrincipal:
    try:
        principal = validator.validate(
            header=authorization_header,
            request={
                "ledger_instance_id": ledger_instance_id,
                "required_scope": required_scope,
            },
        )
    except AuthError as exc:
        raise PolicyError(exc.code) from exc
    try:
        sessions.validate(session_id, principal, protocol_version=protocol_version)
    except SessionError as exc:
        raise PolicyError(exc.code) from exc
    return principal


def attempt_review_ruling_append(
    *,
    authorization_header: str,
    session_id: str,
    protocol_version: str,
    ledger_instance_id: str,
    client_fields: Mapping[str, Any],
    validator: CredentialValidator,
    sessions: SessionRegistry,
    ingress: StructuredIngress,
    store: Any,
    request_inputs: Any,
    known_agent_ids: frozenset[str],
    retired_agent_ids: frozenset[str] = frozenset(),
    audit: Any | None = None,
) -> Any:
    """Auth → session → policy → real StructuredIngress(EntryDraft) → store.append."""
    principal = _authenticate(
        authorization_header=authorization_header,
        session_id=session_id,
        protocol_version=protocol_version,
        ledger_instance_id=ledger_instance_id,
        validator=validator,
        sessions=sessions,
        required_scope="ledger.write",
    )
    decision = PolicyDecision.for_append(
        principal=principal,
        kind=str(client_fields.get("kind") or EntryKind.REVIEW_RULING.value),
        client_fields=client_fields,
    )
    recipients = list(client_fields.get("recipient_agent_ids") or ())
    _validate_recipients(
        recipients,
        known_agent_ids=known_agent_ids,
        retired_agent_ids=retired_agent_ids,
    )
    draft = _entry_draft_from_client_fields(client_fields)
    sanitized = ingress.sanitize(draft, request_inputs)
    if isinstance(sanitized, IngressRejection) or getattr(sanitized, "ok", True) is False:
        code = str(getattr(sanitized, "reason_code", "ingress_rejected"))
        if audit is not None:
            audit.record(
                {
                    "kind": "review-ruling",
                    "schema_id": str(client_fields.get("schema_id") or "review-ruling.v1"),
                    "digest": "",
                    "counts": dict(getattr(sanitized, "rule_counts", {}) or {}),
                    "principal_id": principal.principal_id,
                    "agent_id": principal.agent_id,
                    "sequence": 0,
                    "failure_code": code,
                }
            )
        raise PolicyError(code)

    idempotency_key = str(client_fields.get("idempotency_key") or "")
    try:
        result = store.append(sanitized, decision.identity, idempotency_key=idempotency_key)
    except LedgerStoreError:
        if audit is not None:
            audit.record(
                {
                    "kind": "review-ruling",
                    "schema_id": sanitized.schema_id,
                    "digest": "",
                    "counts": dict(sanitized.rule_counts),
                    "principal_id": principal.principal_id,
                    "agent_id": principal.agent_id,
                    "sequence": 0,
                    "failure_code": "induced_rollback",
                }
            )
        raise
    if audit is not None:
        audit.record(
            {
                "kind": "review-ruling",
                "schema_id": sanitized.schema_id,
                "digest": str(result.content_sha256),
                "counts": dict(sanitized.rule_counts),
                "principal_id": principal.principal_id,
                "agent_id": principal.agent_id,
                "sequence": int(result.sequence),
                "failure_code": None,
            }
        )
    return result


def attempt_review_ruling_read(
    *,
    authorization_header: str,
    session_id: str,
    protocol_version: str,
    ledger_instance_id: str,
    sequence: int,
    validator: CredentialValidator,
    sessions: SessionRegistry,
    store: Any,
) -> dict[str, Any]:
    """Auth → session → content-free entry summary (no message body)."""
    _authenticate(
        authorization_header=authorization_header,
        session_id=session_id,
        protocol_version=protocol_version,
        ledger_instance_id=ledger_instance_id,
        validator=validator,
        sessions=sessions,
        required_scope="ledger.read",
    )
    if hasattr(store, "get_entry_by_sequence"):
        raw = store.get_entry_by_sequence(int(sequence))
    elif hasattr(store, "read_entry"):
        raw = store.read_entry(int(sequence))
    else:
        raise PolicyError("entry_not_found")

    if raw is None:
        raise PolicyError("entry_not_found")
    if isinstance(raw, Mapping):
        source = dict(raw)
    else:
        source = {
            "entry_id": getattr(raw, "entry_id", None),
            "sequence": getattr(raw, "sequence", None),
            "ledger_instance_id": getattr(raw, "ledger_instance_id", None),
            "content_sha256": getattr(raw, "content_sha256", None),
        }
    result = {
        key: source[key]
        for key in ("entry_id", "sequence", "ledger_instance_id", "content_sha256")
        if key in source and source[key] is not None
    }
    if set(result) - _SAFE_READ_FIELDS:
        raise PolicyError("unsafe_read_fields")
    if len(result) != 4:
        raise PolicyError("entry_not_found")
    return {
        "entry_id": str(result["entry_id"]),
        "sequence": int(result["sequence"]),
        "ledger_instance_id": str(result["ledger_instance_id"]),
        "content_sha256": str(result["content_sha256"]),
    }


__all__ = [
    "PolicyDecision",
    "PolicyError",
    "attempt_review_ruling_append",
    "attempt_review_ruling_read",
    "validate_recipients",
]
