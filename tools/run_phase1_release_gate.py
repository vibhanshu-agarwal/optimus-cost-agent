from __future__ import annotations

import argparse
from pathlib import Path

from optimus.golden.json_harness import JsonGoldenTaskHarness
from optimus.release.defaults import build_phase1_release_gates
from optimus.release.runner import ReleaseGateRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 1 Optimus release gate.")
    parser.add_argument("--golden-results", type=Path, help="Path to actual GoldenTaskResult JSON captured from a real Optimus-only run.")
    parser.add_argument("--python-executable", default="python", help="Python executable used for command gates.")
    parser.add_argument("--credential-scan-root", type=Path, default=Path("."), help="Root used for default release credential artifact scans.")
    parser.add_argument("--command-timeout-seconds", type=float, default=600.0, help="Timeout for each subprocess-backed release gate.")
    parser.add_argument("--skip-command-gates-for-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    golden_harness = JsonGoldenTaskHarness.from_path(args.golden_results) if args.golden_results is not None else None
    gates = build_phase1_release_gates(
        python_executable=args.python_executable,
        golden_harness=golden_harness,
        include_command_gates=not args.skip_command_gates_for_test,
        credential_scan_root=args.credential_scan_root,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    report = ReleaseGateRunner(gates=gates).run()
    print(report.to_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
