"""RED/GREEN unit tests for content-free evidence manifests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evidence_handoff.redaction.models import ArtifactKind, Disposition


def _manifest():
    from evidence_handoff.redaction import manifest as manifest_mod

    return manifest_mod


def test_schema_version_frozen() -> None:
    m = _manifest()
    assert m.MANIFEST_SCHEMA_VERSION == "evidence-redaction-manifest-v1"


def test_build_manifest_rejects_extra_fields() -> None:
    m = _manifest()
    with pytest.raises(m.ManifestError, match="manifest_extra_field"):
        m.build_manifest(
            {
                "schema_version": m.MANIFEST_SCHEMA_VERSION,
                "sanitizer_policy_version": "evidence-redaction-v1",
                "artifact_kind": ArtifactKind.TEXT.value,
                "disposition": Disposition.PROMOTED.value,
                "artifact_sha256": "a" * 64,
                "artifact_byte_size": 1,
                "artifact_locator": "<destination>/session_note/artifact",
                "rule_counts": {},
                "final_scan_passed": True,
                "reason_code": None,
                "created_at": datetime(2026, 7, 31, 12, 0, tzinfo=UTC).isoformat(),
                "raw_body": "secret",
            }
        )


def test_serialized_manifest_has_no_forbidden_content() -> None:
    m = _manifest()
    secret = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"  # pragma: allowlist secret
    abs_path = str(Path.cwd().resolve() / "hidden" / "secret.txt")
    payload = m.build_manifest(
        {
            "schema_version": m.MANIFEST_SCHEMA_VERSION,
            "sanitizer_policy_version": "evidence-redaction-v1",
            "artifact_kind": ArtifactKind.JSON.value,
            "disposition": Disposition.PROMOTED.value,
            "artifact_sha256": "b" * 64,
            "artifact_byte_size": 12,
            "artifact_locator": "<destination>/session_note/artifact",
            "rule_counts": {"exact_secret_replacement": 1},
            "final_scan_passed": True,
            "reason_code": None,
            "created_at": datetime(2026, 7, 31, 12, 0, tzinfo=UTC).isoformat(),
        }
    )
    serialized = m.serialize_manifest(payload)
    assert secret not in serialized
    assert abs_path not in serialized
    assert "raw_body" not in serialized
    assert "environment" not in serialized
    data = json.loads(serialized)
    assert set(data.keys()) <= m.ALLOWED_MANIFEST_FIELDS


def test_manifest_canary_scan_detects_secret_leak() -> None:
    m = _manifest()
    secret = "Q7mV2xN9pR4tY8kL3cD6wF1hJ5sB0zUa"  # pragma: allowlist secret
    poisoned = (
        '{"schema_version":"evidence-redaction-manifest-v1",'
        f'"artifact_locator":"{secret}"}}'
    )
    assert m.manifest_canary_scan(poisoned, known_secrets=(secret,), known_pii=()) is False


def test_manifest_canary_scan_passes_clean_manifest() -> None:
    m = _manifest()
    payload = m.build_manifest(
        {
            "schema_version": m.MANIFEST_SCHEMA_VERSION,
            "sanitizer_policy_version": "evidence-redaction-v1",
            "artifact_kind": ArtifactKind.TEXT.value,
            "disposition": Disposition.PROMOTED.value,
            "artifact_sha256": "c" * 64,
            "artifact_byte_size": 3,
            "artifact_locator": "<destination>/session_note/artifact",
            "rule_counts": {},
            "final_scan_passed": True,
            "reason_code": None,
            "created_at": datetime(2026, 7, 31, 12, 0, tzinfo=UTC).isoformat(),
        }
    )
    serialized = m.serialize_manifest(payload)
    assert m.manifest_canary_scan(serialized, known_secrets=("nope-secret-value-xxxx",), known_pii=()) is True


@pytest.mark.parametrize("policy_version", ["evidence-redaction-v1", "evidence-redaction-v2", "evidence-redaction-v3"])
def test_historical_and_current_policy_manifests_both_verify(policy_version: str) -> None:
    """#505 bumped the policy to v2, #584 to v3; manifests recorded under v1 or v2 must still validate, serialize and scan clean."""
    from optimus_security.sanitization import EVIDENCE_REDACTION_POLICY

    m = _manifest()
    assert EVIDENCE_REDACTION_POLICY.version == "evidence-redaction-v3"
    fields = {
        "schema_version": m.MANIFEST_SCHEMA_VERSION,
        "sanitizer_policy_version": policy_version,
        "artifact_kind": ArtifactKind.TEXT.value,
        "disposition": Disposition.PROMOTED.value,
        "artifact_locator": "<destination>/session_note/artifact",
        "rule_counts": {"whitespace_secret_assignment": 1},
        "final_scan_passed": True,
        "created_at": datetime(2026, 7, 31, 12, 0, tzinfo=UTC).isoformat(),
    }
    serialized = m.serialize_manifest(m.build_manifest(fields))
    assert json.loads(serialized)["sanitizer_policy_version"] == policy_version
    assert m.manifest_canary_scan(serialized, known_secrets=("nope-secret-value-xxxx",), known_pii=()) is True


def test_created_at_requires_timezone() -> None:
    m = _manifest()
    with pytest.raises(m.ManifestError, match="manifest_timestamp_not_timezone_aware"):
        m.build_manifest(
            {
                "schema_version": m.MANIFEST_SCHEMA_VERSION,
                "sanitizer_policy_version": "evidence-redaction-v1",
                "artifact_kind": ArtifactKind.TEXT.value,
                "disposition": Disposition.PROMOTED.value,
                "artifact_sha256": "d" * 64,
                "artifact_byte_size": 1,
                "artifact_locator": "<destination>/x/artifact",
                "rule_counts": {},
                "final_scan_passed": True,
                "reason_code": None,
                "created_at": "2026-07-31T12:00:00",
            }
        )
