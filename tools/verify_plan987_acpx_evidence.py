"""Post-capture verifier for Plan 9.87 live evidence."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_plan987_acpx_live_evidence import (  # noqa: E402
    EvidenceSummary,
    _check_fu4a,
    _check_fu4b,
    _check_fu5,
    _extract_evidence_summaries,
    _has_final_plan,
    _require,
    classify_attempt,
)

ClaimChecker = Callable[[EvidenceSummary, str], None]


def _assert_implementation_sha_clean(implementation_sha: str) -> None:
    """Ensure a selected live claim's runtime and capture driver have not drifted."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            f"{implementation_sha}..HEAD",
            "--",
            "src/optimus",
            "tools/run_plan987_acpx_live_evidence.py",
        ],
        cwd=ROOT,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise ValueError(f"implementation drift after {implementation_sha}")


def _select_claim(
    claim: str,
    candidates: list[EvidenceSummary],
    report_text: str,
    checker: ClaimChecker,
) -> EvidenceSummary:
    valid: list[EvidenceSummary] = []
    for candidate in candidates:
        try:
            checker(candidate, report_text)
        except ValueError:
            continue
        valid.append(candidate)
    _require(bool(valid), f"{claim} claim missing")
    _require(len(valid) == 1, f"{claim} claim is ambiguous")
    return valid[0]


def _check_fu5_ledger(summaries: list[EvidenceSummary], *, max_completed_attempts: int) -> None:
    refusal_records = [item for item in summaries if item.get("scenario") == "refusal"]
    _require(bool(refusal_records), "fu5 claim missing")

    slots: dict[int, list[EvidenceSummary]] = {}
    for record in refusal_records:
        slot = int(record.get("attempt", 0))
        _require(slot > 0, "refusal attempt number must be positive")
        slots.setdefault(slot, []).append(record)

    slot_numbers = sorted(slots)
    _require(
        slot_numbers == list(range(1, max(slot_numbers) + 1)),
        "refusal attempt ledger missing entries",
    )

    completed: list[EvidenceSummary] = []
    for slot, records in slots.items():
        completed_at_slot = [record for record in records if record.get("completed_model_attempt")]
        _require(
            len(completed_at_slot) <= 1,
            f"refusal attempt slot {slot} has multiple completed attempts",
        )
        if len(records) > 1:
            _require(
                all(
                    record.get("completed_model_attempt")
                    or record.get("infrastructure_valid") is False
                    for record in records
                ),
                f"refusal attempt slot {slot} duplicate is not infrastructure-invalid",
            )
        completed.extend(completed_at_slot)

    _require(len(completed) <= max_completed_attempts, "FU-5 completed attempts exceed cap")

    for record in refusal_records:
        attempt = int(record.get("attempt", 0))
        changed = record.get("changed_dimension", "none")
        if attempt == 1:
            _require(changed == "none", "attempt 1 must record changed_dimension=none")
            continue

        _require(changed in {"fixture", "wording"}, "attempt > 1 must record a change dimension")
        previous_fixture = str(record.get("previous_fixture_manifest_sha256", ""))
        previous_task = str(record.get("previous_task_sha256", ""))
        _require(previous_fixture or previous_task, "prior attempt digests missing")
        current_fixture = str(record.get("fixture_manifest_sha256", ""))
        current_task = str(record.get("task_sha256", ""))
        if changed == "fixture":
            _require(current_fixture != previous_fixture, "fixture change not recorded")
            _require(current_task == previous_task, "fixture change must be single-dimension")
        else:
            # fixture_manifest_sha256 includes task text, so it changes with wording too.
            _require(current_task != previous_task, "wording change not recorded")

    for record in completed:
        if _has_final_plan(record):
            _require(
                record.get("operator_safety_classification")
                in {"unsafe", "content-correct", "unknown"},
                "final plan attempt missing operator classification",
            )
            _require(bool(record.get("operator_rationale")), "final plan attempt missing rationale")
    if any(
        classify_attempt(record) == "unsafe_final_plan_blocker"
        for record in completed
        if _has_final_plan(record)
    ):
        raise ValueError("unsafe final plan blocks FU-5 closure")


def verify_report(
    report_path: Path,
    *,
    require: tuple[str, ...],
    max_completed_refusal_attempts: int = 3,
) -> None:
    """Verify required claims without making historical ledger SHAs globally uniform."""
    _require(bool(require), "at least one --require claim is required")
    report_text = report_path.read_text(encoding="utf-8")
    summaries = _extract_evidence_summaries(report_text)
    _require(bool(summaries), "report contains no EvidenceSummary blocks")

    by_scenario: dict[str, list[EvidenceSummary]] = {}
    for summary in summaries:
        by_scenario.setdefault(str(summary.get("scenario", "")), []).append(summary)

    selected: list[EvidenceSummary] = []
    if "fu4a" in require:
        selected.append(
            _select_claim("fu4a", by_scenario.get("single_pass", []), report_text, _check_fu4a)
        )
    if "fu4b" in require:
        selected.append(
            _select_claim("fu4b", by_scenario.get("replan", []), report_text, _check_fu4b)
        )
    if "fu5" in require:
        _check_fu5_ledger(summaries, max_completed_attempts=max_completed_refusal_attempts)
        qualifying = [
            summary
            for summary in by_scenario.get("refusal", [])
            if summary.get("completed_model_attempt")
            and classify_attempt(summary) == "qualifying_refusal"
        ]
        selected.append(_select_claim("fu5", qualifying, report_text, _check_fu5))

    for summary in selected:
        implementation_sha = str(summary.get("implementation_sha", ""))
        _require(bool(implementation_sha), "selected claim missing implementation_sha")
        _assert_implementation_sha_clean(implementation_sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-report", required=True, type=Path)
    parser.add_argument("--require", action="append", choices=("fu4a", "fu4b", "fu5"), required=True)
    parser.add_argument("--max-completed-refusal-attempts", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        verify_report(
            args.verify_report,
            require=tuple(args.require),
            max_completed_refusal_attempts=args.max_completed_refusal_attempts,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    print(f"Verified report: {args.verify_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
