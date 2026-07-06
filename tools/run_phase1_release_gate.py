from __future__ import annotations

from optimus.release.defaults import build_phase1_release_gates
from optimus.release.runner import ReleaseGateRunner


def main() -> int:
    report = ReleaseGateRunner(gates=build_phase1_release_gates()).run()
    print(report.to_json())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
