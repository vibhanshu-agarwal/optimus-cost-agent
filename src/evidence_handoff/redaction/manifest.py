"""Content-free evidence redaction manifests and pre-promotion canary scan."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY, sanitize_for_persistence

MANIFEST_SCHEMA_VERSION = "evidence-redaction-manifest-v1"

ALLOWED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "sanitizer_policy_version",
        "artifact_kind",
        "disposition",
        "artifact_sha256",
        "artifact_byte_size",
        "artifact_locator",
        "rule_counts",
        "final_scan_passed",
        "reason_code",
        "truncated_tail_dropped",
        "dropped_tail_bytes",
        "dump_kind",
        "approval_sha256",
        "approver_id",
        "approved_at",
        "created_at",
    }
)

REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "sanitizer_policy_version",
        "artifact_kind",
        "disposition",
        "artifact_locator",
        "rule_counts",
        "final_scan_passed",
        "created_at",
    }
)


class ManifestError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_manifest(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a content-free manifest mapping."""
    unknown = set(fields) - ALLOWED_MANIFEST_FIELDS
    if unknown:
        raise ManifestError("manifest_extra_field")
    missing = REQUIRED_MANIFEST_FIELDS - set(fields)
    if missing:
        raise ManifestError("manifest_missing_field")
    if fields.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("manifest_schema_mismatch")
    created_at = fields.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise ManifestError("manifest_timestamp_invalid")
    # Require timezone designator in ISO string.
    if created_at.endswith("Z"):
        parsed_ok = True
    else:
        try:
            parsed = datetime.fromisoformat(created_at)
            parsed_ok = parsed.tzinfo is not None
        except ValueError:
            parsed_ok = False
    if not parsed_ok:
        raise ManifestError("manifest_timestamp_not_timezone_aware")
    if not isinstance(fields.get("rule_counts"), Mapping):
        raise ManifestError("manifest_rule_counts_invalid")
    # Drop Nones for optional fields to keep serialization tight? Keep explicit nulls for required optionals.
    return {key: fields[key] for key in fields if key in ALLOWED_MANIFEST_FIELDS}


def serialize_manifest(manifest: Mapping[str, Any]) -> str:
    validated = build_manifest(manifest)
    return json.dumps(validated, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def manifest_canary_scan(
    serialized: str,
    *,
    known_secrets: Sequence[str],
    known_pii: Sequence[str],
) -> bool:
    """Return True when serialized manifest is free of inventory secrets/PII and bodies."""
    forbidden_keys = (
        "raw_body",
        "environment",
        "dump_contents",
        "source_path",
        "exception",
    )
    lower = serialized.lower()
    if any(key in lower for key in forbidden_keys):
        return False
    for secret in known_secrets:
        if secret and secret in serialized:
            return False
    for pii in known_pii:
        if pii and pii in serialized:
            return False
    result = sanitize_for_persistence(
        serialized,
        known_secrets=known_secrets,
        known_pii=known_pii,
        path_aliases=(),
        policy=EVIDENCE_REDACTION_POLICY,
    )
    for secret in known_secrets:
        if secret and secret in str(result.value):
            return False
    return True
