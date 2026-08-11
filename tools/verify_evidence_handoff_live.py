"""Evidence-only verifier for real Claude Code / Codex / Cursor ledger runs.

Does not launch agents, emulate MCP, create credentials, or synthesize results.
Operator supplies absolute evidence roots and native-client manifests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.evidence_handoff_live_support import (  # noqa: E402
    VerificationError,
    inspect_evidence_root,
    verify_evidence_root,
)


def verify_evidence(
    *,
    evidence_root: Path | None,
    service_endpoint: str | None,
    expected_agent_ids: Sequence[str],
) -> dict[str, Any]:
    return verify_evidence_root(
        evidence_root=evidence_root,
        service_endpoint=service_endpoint,
        expected_agent_ids=tuple(expected_agent_ids),
    )


def inspect_evidence(*, evidence_root: Path | None) -> dict[str, Any]:
    return inspect_evidence_root(evidence_root=evidence_root)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_evidence_handoff_live",
        description="Verify or inspect operator-supplied three-agent live evidence (no agent launch).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify_p = sub.add_parser("verify", help="Verify a content-free live evidence root")
    verify_p.add_argument(
        "--evidence-root",
        required=True,
        type=Path,
        help="Absolute path to the operator evidence root (required; no default)",
    )
    verify_p.add_argument(
        "--service-endpoint",
        required=True,
        help="Service MCP endpoint URL (required; no default)",
    )
    verify_p.add_argument(
        "--expected-agent-id",
        action="append",
        dest="expected_agent_ids",
        required=True,
        help="Expected distinct agent_id (repeat three times)",
    )

    inspect_p = sub.add_parser("inspect", help="Inspect evidence root and scan raw canaries")
    inspect_p.add_argument(
        "--evidence-root",
        required=True,
        type=Path,
        help="Absolute path to the operator evidence root (required; no default)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "verify":
            result = verify_evidence(
                evidence_root=args.evidence_root,
                service_endpoint=args.service_endpoint,
                expected_agent_ids=tuple(args.expected_agent_ids),
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("passed") else 2
        if args.command == "inspect":
            result = inspect_evidence(evidence_root=args.evidence_root)
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result.get("canary", {}).get("clean", False) else 3
    except VerificationError as exc:
        print(json.dumps({"error": exc.code, "detail": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
