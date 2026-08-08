"""In-memory structured-entry redaction ingress for the handoff ledger.

Validates a primitive typed draft, sanitizes through the shared optimus_security
rule engine, deterministically serializes, and returns a closed result with
content-free rule counts. Does not stage unredacted entries on disk.

Naming (Task 1 vs Task 3 reconciliation):
- This module keeps narrow text-only ingress stubs as IngressTextDraft /
  IngressSanitizedText.
- The canonical EntryDraft / SanitizedDraft contracts live in
  evidence_handoff.ledger.models (Task 3). Task 7 will point StructuredIngress at
  those ledger types for full Message/Part sanitization.
- Temporary aliases were intentionally not kept: importing EntryDraft from
  ingress would collide with ledger.models.EntryDraft. Call sites use the
  Ingress* names explicitly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence

from .models import RedactionRuntimeInputs


@dataclass(frozen=True)
class IngressTextDraft:
    """Narrow Task 1 text-only ingress draft. Not the ledger EntryDraft."""

    kind: str
    message_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("invalid_entry_kind")
        if not isinstance(self.message_text, str):
            raise ValueError("invalid_message_text")


@dataclass(frozen=True)
class RequestRedactionInputs:
    runtime: RedactionRuntimeInputs

    def __repr__(self) -> str:
        return (
            "RequestRedactionInputs("
            f"secret_count={self.runtime.sensitive_values.secret_count}, "
            f"pii_count={self.runtime.sensitive_values.pii_count})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True)
class IngressSanitizedText:
    """Narrow Task 1 sanitized text result. Not the ledger SanitizedDraft."""

    kind: str
    message_text: str
    content_sha256: str
    rule_counts: Mapping[str, int]

    @property
    def ok(self) -> bool:
        return True

    @property
    def reason_code(self) -> str | None:
        return None

    def __repr__(self) -> str:
        return (
            "IngressSanitizedText("
            f"kind={self.kind!r}, "
            f"content_sha256={self.content_sha256!r}, "
            f"rule_counts={dict(self.rule_counts)!r})"
        )


@dataclass(frozen=True)
class IngressRejection:
    reason_code: str
    rule_counts: Mapping[str, int]

    @property
    def ok(self) -> bool:
        return False

    @property
    def message_text(self) -> str:
        return ""

    @property
    def content_sha256(self) -> str:
        return ""

    def __repr__(self) -> str:
        return (
            "IngressRejection("
            f"reason_code={self.reason_code!r}, "
            f"rule_counts={dict(self.rule_counts)!r})"
        )

    def __str__(self) -> str:
        return self.reason_code


class StructuredIngress:
    """Fail-closed in-memory sanitization boundary for narrow text drafts."""

    def sanitize(
        self,
        draft: IngressTextDraft,
        inputs: RequestRedactionInputs,
    ) -> IngressSanitizedText | IngressRejection:
        if not isinstance(draft, IngressTextDraft):
            return IngressRejection(reason_code="invalid_entry_draft", rule_counts={})
        if not isinstance(inputs, RequestRedactionInputs):
            return IngressRejection(reason_code="invalid_request_inputs", rule_counts={})

        inventory = inputs.runtime.sensitive_values
        if inventory.secret_count == 0 and inventory.pii_count == 0:
            return IngressRejection(reason_code="empty_runtime_inventory", rule_counts={})

        known_secrets = inventory.secret_values_for_sanitizer()
        known_pii = inventory.pii_values_for_sanitizer()
        sanitized = sanitize_for_persistence(
            draft.message_text,
            known_secrets=known_secrets,
            known_pii=known_pii,
            path_aliases=inputs.runtime.path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        message_text = str(sanitized.value)
        payload = json.dumps(
            {"kind": draft.kind, "message_text": message_text},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return IngressSanitizedText(
            kind=draft.kind,
            message_text=message_text,
            content_sha256=digest,
            rule_counts=dict(sanitized.rule_counts),
        )


__all__ = [
    "IngressRejection",
    "IngressSanitizedText",
    "IngressTextDraft",
    "RequestRedactionInputs",
    "StructuredIngress",
]
