"""Offline verifier for Plan 11.7 server-side custody feasibility manifests."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    SCHEMA_APPROVAL_EQUIVALENCE,
    SCHEMA_SETTINGS_TRANSACTION,
    SCHEMA_VERIFIER_SUMMARY,
    CustodyContractError,
    VerificationResult,
    verify_manifest,
)
from tools.plan117_custody_relay import verify_relay_capture  # noqa: E402

__all__ = (
    "main",
    "verify_approval_equivalence",
    "verify_manifest",
    "verify_relay_capture",
    "verify_settings_transaction_proof",
    "verify_transcript_debug_agreement",
)


def _summary_payload(result: VerificationResult) -> dict[str, object]:
    return {
        "schema": SCHEMA_VERIFIER_SUMMARY,
        "disposition": result.disposition.value,
        "reason_codes": list(result.reason_codes),
        "verified_artifact_count": result.verified_artifact_count,
    }


def _failure_payload(exc: CustodyContractError) -> dict[str, str]:
    return {
        "field_path": exc.field_path,
        "reason_code": exc.reason_code,
    }


def verify_settings_transaction_proof(path: Path) -> dict[str, Any]:
    """Offline-check a promoted settings-transaction proof artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_SETTINGS_TRANSACTION:
        raise CustodyContractError("invalid_settings_transaction_schema", "schema")
    required = (
        "settings_path",
        "pre_image_existed",
        "pre_image_sha256",
        "mutated_sha256",
        "changed_key_paths",
        "restored",
    )
    for key in required:
        if key not in payload:
            raise CustodyContractError("settings_transaction_incomplete", key)
    if not payload.get("restored"):
        raise CustodyContractError("settings_not_restored", "restored")
    return payload


def verify_approval_equivalence(path: Path) -> dict[str, Any]:
    """Offline-check a direct/relay approval-equivalence artifact."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCHEMA_APPROVAL_EQUIVALENCE:
        raise CustodyContractError("invalid_approval_equivalence_schema", "schema")
    if payload.get("equivalent") is not True:
        raise CustodyContractError("invalid_probe_relay_environment_mismatch", "equivalent")
    if payload.get("final_reason_code") != "AUTHORIZED":
        raise CustodyContractError("invalid_probe_relay_environment_mismatch", "final_reason_code")
    if payload.get("record_hmac_verified") is not True:
        raise CustodyContractError("invalid_probe_relay_environment_mismatch", "record_hmac_verified")
    return payload


def verify_transcript_debug_agreement(
    projection: Mapping[str, Any],
    debug_suffix: Mapping[str, Any],
) -> None:
    """Fail closed when completed-copy projection disagrees with debug suffix."""
    for key in ("messages", "ordered_update_types", "server_session_id", "interval"):
        if projection.get(key) != debug_suffix.get(key):
            raise CustodyContractError("invalid_probe_transcript_debug_divergence", key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to plan117-custody-artifact-manifest-v1 JSON",
    )
    parser.add_argument(
        "--checkpoint",
        choices=("task4", "task5"),
        default=None,
        help="Allow a partial Task 4/5 manifest; omit for the complete final seal",
    )
    args = parser.parse_args(argv)

    try:
        result = verify_manifest(args.manifest, checkpoint=args.checkpoint)
    except CustodyContractError as exc:
        print(json.dumps(_failure_payload(exc), separators=(",", ":"), sort_keys=True), file=sys.stderr)
        return 1

    print(json.dumps(_summary_payload(result), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
