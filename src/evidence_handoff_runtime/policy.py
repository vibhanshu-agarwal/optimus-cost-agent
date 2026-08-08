"""Principal mapping and role policy for ledger appends.

Authority, caller_role, and agent_id are server-derived. Client supply is a
closed-schema rejection. Implementer review-ruling writes are refused before
ingress and sequence assignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from evidence_handoff.ledger.models import (
    EntryKind,
    EntryMessage,
    MessagePart,
    SanitizedDraft,
    SchemaId,
    ServerIdentity,
)
from evidence_handoff.redaction.ingress import IngressTextDraft, StructuredIngress
from evidence_handoff_runtime.auth import AuthenticatedPrincipal, AuthError, CredentialValidator
from evidence_handoff_runtime.sessions import SessionError, SessionRegistry

_CLOSED_SCHEMA_FIELDS = frozenset(
    {"authority", "caller_role", "agent_id", "principal_id", "attestation"}
)
_REVIEWER_ROLE = "reviewer"


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


def _adapt_ingress_to_sanitized_draft(
    *,
    ingress_result: Any,
    client_fields: Mapping[str, Any],
) -> SanitizedDraft:
    if not getattr(ingress_result, "ok", False):
        raise PolicyError(str(getattr(ingress_result, "reason_code", "ingress_rejected")))
    recipients = tuple(str(item) for item in client_fields.get("recipient_agent_ids") or ())
    return SanitizedDraft(
        kind=EntryKind.REVIEW_RULING,
        schema_id=str(client_fields.get("schema_id") or SchemaId.REVIEW_RULING.value),
        context_id=str(client_fields["context_id"]),
        recipient_agent_ids=recipients,
        message=EntryMessage(
            parts=(MessagePart(kind="text", text=str(ingress_result.message_text)),)
        ),
        artifacts=(),
        task_id=client_fields.get("task_id"),
        in_reply_to=client_fields.get("in_reply_to"),
        rule_counts=dict(ingress_result.rule_counts),
    )


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
) -> Any:
    """Auth → session → policy → real StructuredIngress → store.append."""
    try:
        principal = validator.validate(
            authorization_header,
            {
                "ledger_instance_id": ledger_instance_id,
                "required_scope": "ledger.write",
            },
        )
    except AuthError as exc:
        raise PolicyError(exc.code) from exc
    try:
        sessions.validate(session_id, principal, protocol_version=protocol_version)
    except SessionError as exc:
        raise PolicyError(exc.code) from exc

    decision = PolicyDecision.for_append(
        principal=principal,
        kind=str(client_fields.get("kind") or EntryKind.REVIEW_RULING.value),
        client_fields=client_fields,
    )
    draft = IngressTextDraft(
        kind=EntryKind.REVIEW_RULING.value,
        message_text=str(client_fields.get("message_text") or ""),
    )
    sanitized_text = ingress.sanitize(draft, request_inputs)
    sanitized = _adapt_ingress_to_sanitized_draft(
        ingress_result=sanitized_text,
        client_fields=client_fields,
    )
    idempotency_key = str(client_fields.get("idempotency_key") or "")
    return store.append(sanitized, decision.identity, idempotency_key=idempotency_key)


__all__ = [
    "PolicyDecision",
    "PolicyError",
    "attempt_review_ruling_append",
]
