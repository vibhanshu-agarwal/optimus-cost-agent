"""In-memory structured-entry redaction ingress for the handoff ledger.

Validates a primitive typed EntryDraft, sanitizes through the shared
optimus_security rule engine, deterministically serializes, runs a final
exact/pattern/entropy/path/encoded scan, and returns a closed SanitizedDraft
with content-free rule counts. Does not stage unredacted entries on disk.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence

from ..ledger.errors import LedgerValidationError
from ..ledger.models import (
    ArtifactRef,
    EntryDraft,
    EntryMessage,
    MessagePart,
    SanitizedDraft,
)
from .models import RedactionRuntimeInputs


@dataclass(frozen=True)
class IngressTextDraft:
    """Legacy Task 1 text-only draft. Rejected by StructuredIngress.sanitize."""

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
    """Legacy Task 1 sanitized text result. Not returned by Task 7 sanitize."""

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


def _merge_counts(*maps: Mapping[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for mapping in maps:
        for key, value in mapping.items():
            out[key] = out.get(key, 0) + int(value)
    return out


def _inventory_values(inputs: RequestRedactionInputs) -> tuple[tuple[str, ...], tuple[str, ...]]:
    inventory = inputs.runtime.sensitive_values
    secrets = tuple(inventory.secret_values_for_sanitizer())
    pii = tuple(inventory.pii_values_for_sanitizer())
    return secrets, pii


def _secret_encodings(secret: str) -> tuple[str, ...]:
    raw = secret.encode("utf-8")
    return (
        base64.b64encode(raw).decode("ascii"),
        base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="),
    )


def _contains_canary(haystack: str, *, secrets: tuple[str, ...], pii: tuple[str, ...]) -> bool:
    for secret in secrets:
        if secret and secret in haystack:
            return True
        for encoded in _secret_encodings(secret):
            if encoded and encoded in haystack:
                return True
    for value in pii:
        if value and value in haystack:
            return True
    return False


def _sanitize_text(
    text: str,
    *,
    secrets: tuple[str, ...],
    pii: tuple[str, ...],
    inputs: RequestRedactionInputs,
) -> tuple[str, dict[str, int]]:
    result = sanitize_for_persistence(
        text,
        known_secrets=secrets,
        known_pii=pii,
        path_aliases=inputs.runtime.path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    return str(result.value), dict(result.rule_counts)


def _sanitize_data(
    data: Mapping[str, Any],
    *,
    secrets: tuple[str, ...],
    pii: tuple[str, ...],
    inputs: RequestRedactionInputs,
) -> tuple[dict[str, Any], dict[str, int]]:
    result = sanitize_for_persistence(
        dict(data),
        known_secrets=secrets,
        known_pii=pii,
        path_aliases=inputs.runtime.path_aliases,
        policy=EVIDENCE_REDACTION_POLICY,
    )
    value = result.value
    if not isinstance(value, dict):
        raise LedgerValidationError("invalid_message_part_data")
    return value, dict(result.rule_counts)


class StructuredIngress:
    """Fail-closed in-memory sanitization boundary for ledger EntryDraft."""

    def sanitize(
        self,
        draft: EntryDraft,
        inputs: RequestRedactionInputs,
    ) -> SanitizedDraft | IngressRejection:
        if not isinstance(draft, EntryDraft):
            return IngressRejection(reason_code="invalid_entry_draft", rule_counts={})
        if not isinstance(inputs, RequestRedactionInputs):
            return IngressRejection(reason_code="invalid_request_inputs", rule_counts={})

        inventory = inputs.runtime.sensitive_values
        if inventory.secret_count == 0 and inventory.pii_count == 0:
            return IngressRejection(reason_code="empty_runtime_inventory", rule_counts={})

        secrets, pii = _inventory_values(inputs)
        counts: dict[str, int] = {}
        sanitized_parts: list[MessagePart] = []
        part_texts: list[str] = []

        for part in draft.message.parts:
            if part.kind == "text":
                text = part.text or ""
                part_texts.append(text)
                cleaned, part_counts = _sanitize_text(
                    text, secrets=secrets, pii=pii, inputs=inputs
                )
                counts = _merge_counts(counts, part_counts)
                sanitized_parts.append(MessagePart(kind="text", text=cleaned))
            else:
                data = dict(part.data or {})
                part_texts.append(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
                cleaned_data, part_counts = _sanitize_data(
                    data, secrets=secrets, pii=pii, inputs=inputs
                )
                counts = _merge_counts(counts, part_counts)
                sanitized_parts.append(MessagePart(kind="data", data=cleaned_data))

        sanitized_artifacts: list[ArtifactRef] = []
        for artifact in draft.artifacts:
            meta_blob = "|".join(
                item
                for item in (artifact.name, artifact.uri or "", artifact.media_type or "")
                if item
            )
            if _contains_canary(meta_blob, secrets=secrets, pii=pii):
                return IngressRejection(
                    reason_code="artifact_metadata_rejected",
                    rule_counts=counts,
                )
            name, name_counts = _sanitize_text(
                artifact.name, secrets=secrets, pii=pii, inputs=inputs
            )
            counts = _merge_counts(counts, name_counts)
            uri = artifact.uri
            if uri is not None:
                uri, uri_counts = _sanitize_text(uri, secrets=secrets, pii=pii, inputs=inputs)
                counts = _merge_counts(counts, uri_counts)
            media_type = artifact.media_type
            if media_type is not None:
                media_type, mt_counts = _sanitize_text(
                    media_type, secrets=secrets, pii=pii, inputs=inputs
                )
                counts = _merge_counts(counts, mt_counts)
            cleaned_meta = "|".join(
                item for item in (name, uri or "", media_type or "") if item
            )
            if _contains_canary(cleaned_meta, secrets=secrets, pii=pii):
                return IngressRejection(
                    reason_code="artifact_metadata_rejected",
                    rule_counts=counts,
                )
            sanitized_artifacts.append(
                ArtifactRef(
                    name=name,
                    content_sha256=artifact.content_sha256,
                    uri=uri,
                    media_type=media_type,
                )
            )

        sanitized = SanitizedDraft(
            kind=draft.kind,
            schema_id=draft.schema_id,
            context_id=draft.context_id,
            recipient_agent_ids=draft.recipient_agent_ids,
            message=EntryMessage(parts=tuple(sanitized_parts)),
            artifacts=tuple(sanitized_artifacts),
            task_id=draft.task_id,
            in_reply_to=draft.in_reply_to,
            rule_counts=counts,
        )
        serialized = json.dumps(
            sanitized.to_mapping(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        joined_original = "".join(part_texts)
        sanitized_texts: list[str] = []
        for part in sanitized_parts:
            if part.kind == "text":
                sanitized_texts.append(part.text or "")
            else:
                sanitized_texts.append(
                    json.dumps(
                        dict(part.data or {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                )
        joined_sanitized = "".join(sanitized_texts)

        # Split-across-parts: secret only appears when originals are concatenated.
        for secret in secrets:
            if not secret:
                continue
            if secret in joined_original and not any(secret in part for part in part_texts):
                return IngressRejection(reason_code="final_scan_hit", rule_counts=counts)
            # Encoded presentations of known secrets fail closed even if entropy-redacted.
            for encoded in _secret_encodings(secret):
                if encoded and any(encoded in part for part in part_texts):
                    return IngressRejection(reason_code="final_scan_hit", rule_counts=counts)
        if _contains_canary(serialized, secrets=secrets, pii=pii):
            return IngressRejection(reason_code="final_scan_hit", rule_counts=counts)
        if _contains_canary(joined_sanitized, secrets=secrets, pii=pii):
            return IngressRejection(reason_code="final_scan_hit", rule_counts=counts)

        # Pattern/entropy residual scan on the serialized form.
        # Any rewrite means a residual match (including entropy-only candidates in
        # unsanitized client fields such as context_id/task_id/in_reply_to). Fail
        # closed — do not return a pre-redaction SanitizedDraft.
        residual = sanitize_for_persistence(
            serialized,
            known_secrets=secrets,
            known_pii=pii,
            path_aliases=inputs.runtime.path_aliases,
            policy=EVIDENCE_REDACTION_POLICY,
        )
        counts = _merge_counts(counts, residual.rule_counts)
        residual_text = str(residual.value)
        if residual_text != serialized or _contains_canary(
            residual_text, secrets=secrets, pii=pii
        ):
            return IngressRejection(reason_code="final_scan_hit", rule_counts=counts)

        # Reparse closed mapping to prove deterministic round-trip.
        remapped = json.loads(serialized)
        rebuilt = SanitizedDraft(
            kind=sanitized.kind,
            schema_id=str(remapped["schema_id"]),
            context_id=str(remapped["context_id"]),
            recipient_agent_ids=tuple(str(item) for item in remapped["recipient_agent_ids"]),
            message=EntryMessage(
                parts=tuple(
                    MessagePart(
                        kind=str(part["kind"]),
                        text=part.get("text"),
                        data=part.get("data"),
                    )
                    for part in remapped["message"]["parts"]
                )
            ),
            artifacts=tuple(
                ArtifactRef(
                    name=str(item["name"]),
                    content_sha256=str(item["content_sha256"]),
                    uri=item.get("uri"),
                    media_type=item.get("media_type"),
                )
                for item in remapped.get("artifacts") or ()
            ),
            task_id=remapped.get("task_id"),
            in_reply_to=remapped.get("in_reply_to"),
            rule_counts=counts,
        )
        return rebuilt


__all__ = [
    "IngressRejection",
    "IngressSanitizedText",
    "IngressTextDraft",
    "RequestRedactionInputs",
    "StructuredIngress",
]
