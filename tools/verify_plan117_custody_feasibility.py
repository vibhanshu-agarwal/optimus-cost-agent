"""Offline verifier for Plan 11.7 server-side custody feasibility manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.plan117_custody_contract import (  # noqa: E402
    SCHEMA_VERIFIER_SUMMARY,
    CustodyContractError,
    VerificationResult,
    verify_manifest,
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
