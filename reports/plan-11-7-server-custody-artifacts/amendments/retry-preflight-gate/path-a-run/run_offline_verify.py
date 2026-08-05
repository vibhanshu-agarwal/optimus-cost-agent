"""Path A: offline-verify the real fail-closed CLI result."""

from __future__ import annotations

import json
from pathlib import Path

from tools.verify_plan117_custody_feasibility import (
    RETRY_OUTCOME_CONTROL_FAILURE,
    RETRY_OUTCOME_UNAVAILABLE_PROOF,
    verify_retry_preflight_offline,
)

ROOT = Path(__file__).resolve().parents[4]
# parents: path-a-run -> retry-preflight-gate -> amendments -> artifacts -> reports -> ROOT
# Wait - if script lives in path-a-run under reports/... this is wrong.
# Place next to cli-result and compute ROOT from known repo marker.


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "tools" / "verify_plan117_custody_feasibility.py").is_file():
            return candidate
    raise SystemExit("repo root not found")


def main() -> int:
    root = _repo_root()
    base = (
        root
        / "reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/path-a-run"
    )
    cli = json.loads((base / "cli-result.json").read_text(encoding="utf-8"))
    launch = json.loads((base / "launch-session-identity.json").read_text(encoding="utf-8"))
    descriptor = json.loads(
        (base / "relay-control-descriptor.json").read_text(encoding="utf-8")
    )
    ledger = json.loads(
        (
            root
            / "reports/plan-11-7-server-custody-artifacts/amendments/"
            "origin-a-fixture-v2/stage-ledger.json"
        ).read_text(encoding="utf-8")
    )

    claim = {
        "schema": "plan117-retry-preflight-path-a-claim-v1",
        "path": "A",
        "supported_by_live_attestation": False,
        "hardcoded": False,
        "settings_mutated": bool(cli.get("settings_mutated")),
        "zed_launched": bool(cli.get("zed_launched")),
        "cli_reason_code": cli.get("reason_code"),
        "cli_field_path": cli.get("field_path"),
        "reservation_exists": bool(cli.get("reservation_exists")),
        "origin_a4_attempt_exists": bool(cli.get("origin_a4_attempt_exists")),
    }

    # No live proof was returned; offline verifier must classify fail-closed.
    summary = verify_retry_preflight_offline(
        proof=None,
        launch_identity=launch,
        control_descriptor=descriptor,
        stage_ledger=ledger,
        prompt_outcome=None,
        claim=claim,
        promote_safe_only=True,
    )

    allowed = {RETRY_OUTCOME_UNAVAILABLE_PROOF, RETRY_OUTCOME_CONTROL_FAILURE}
    if summary.get("outcome") not in allowed:
        raise SystemExit(f"unexpected offline outcome: {summary}")
    if claim["settings_mutated"] or claim["zed_launched"]:
        raise SystemExit("settings/zed flags must be false for Path A")
    if claim["reservation_exists"] or claim["origin_a4_attempt_exists"]:
        raise SystemExit("Path A must not reserve ordinal 3 or allocate origin-a-4")

    out = {
        "schema": "plan117-retry-preflight-path-a-offline-verify-v1",
        "cli_reason_code": cli.get("reason_code"),
        "cli_field_path": cli.get("field_path"),
        "offline_summary": summary,
        "offline_outcome_allowed": sorted(allowed),
        "settings_mutated": False,
        "zed_launched": False,
    }
    out_path = base / "offline-verify-result.json"
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    print("WROTE", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
