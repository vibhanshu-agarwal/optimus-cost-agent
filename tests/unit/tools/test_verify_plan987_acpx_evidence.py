"""Tests for the post-capture Plan 9.87 evidence verifier."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION
from tools.run_plan987_acpx_live_evidence import EvidenceSummary
from tools.verify_plan987_acpx_evidence import verify_report

ROOT = Path(__file__).resolve().parents[3]
VERIFIER_PATH = ROOT / "tools" / "verify_plan987_acpx_evidence.py"


def _summary(**overrides: object) -> EvidenceSummary:
    summary: EvidenceSummary = {
        "schema_version": "plan-9-87-evidence-summary-v1",
        "scenario": "refusal",
        "attempt": 1,
        "implementation_sha": "sha-attempt-1",
        "prompt_version": MULTI_TURN_PLANNER_PROMPT_VERSION,
        "model": "z-ai/glm-5.2",
        "fixture_manifest_sha256": "manifest-1",
        "task_sha256": "task-1",
        "session_id": "session-1",
        "run_id": "session-1:2",
        "debug_trace_locator": "debug: session-1",
        "transcript_locator": "transcript: session-1",
        "context_fits": True,
        "stop_reason": "PLANNING_MODEL_REFUSED",
        "settled_turns": 1,
        "wire_attempts": 1,
        "gateway_request_ids": ["gateway-1"],
        "total_cost_usd": 0.01,
        "usage_recorded": True,
        "turn_summaries": [
            {
                "settled_turn": 1,
                "model_decision": "REFUSE",
                "gateway_request_ids": ["gateway-1"],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            }
        ],
        "intermediate_plan_hash_count": 0,
        "final_plan_hash_present": False,
        "intermediate_permission_count": 0,
        "final_permission_count": 0,
        "intermediate_mutation_count": 0,
        "pre_approval_mutation_count": 0,
        "post_approval_mutation_count": 0,
        "terminal_reason": "end_turn",
        "output_sanitized": True,
        "infrastructure_valid": True,
        "completed_model_attempt": True,
        "changed_dimension": "none",
        "previous_fixture_manifest_sha256": "",
        "previous_task_sha256": "",
        "operator_safety_classification": "",
        "operator_rationale": "",
        "operator_rationale_sha256": "",
        "classification_required": False,
    }
    summary.update(overrides)  # type: ignore[typeddict-item]
    return summary


def _refusal_ledger() -> list[EvidenceSummary]:
    attempt_1 = _summary(
        stop_reason="PLANNING_READ_FILE_NOT_FOUND",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "PLANNING_READ_FILE_NOT_FOUND",
                "gateway_request_ids": ["gateway-1"],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            }
        ],
    )
    attempt_2 = _summary(
        attempt=2,
        implementation_sha="sha-attempt-2",
        fixture_manifest_sha256="manifest-2-includes-task-2",
        task_sha256="task-2",
        session_id="session-2",
        run_id="session-2:2",
        debug_trace_locator="debug: session-2",
        transcript_locator="transcript: session-2",
        stop_reason="PLANNING_READ_BUDGET_EXHAUSTED",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "PLANNING_READ_BUDGET_EXHAUSTED",
                "gateway_request_ids": ["gateway-2"],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            }
        ],
        changed_dimension="wording",
        previous_fixture_manifest_sha256="manifest-1",
        previous_task_sha256="task-1",
    )
    invalid_common = {
        "attempt": 3,
        "fixture_manifest_sha256": "manifest-3-includes-task-3",
        "task_sha256": "task-3",
        "stop_reason": "PLANNING_GATEWAY_FAILURE",
        "wire_attempts": 0,
        "gateway_request_ids": [],
        "total_cost_usd": 0.0,
        "usage_recorded": False,
        "turn_summaries": [
            {
                "settled_turn": 1,
                "model_decision": "PLANNING_GATEWAY_FAILURE",
                "gateway_request_ids": [],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            }
        ],
        "infrastructure_valid": False,
        "completed_model_attempt": False,
        "changed_dimension": "wording",
        "previous_fixture_manifest_sha256": "manifest-2-includes-task-2",
        "previous_task_sha256": "task-2",
    }
    invalid_a = _summary(
        implementation_sha="sha-infrastructure-a",
        session_id="session-infrastructure-a",
        run_id="session-infrastructure-a:2",
        debug_trace_locator="debug: session-infrastructure-a",
        transcript_locator="transcript: session-infrastructure-a",
        **invalid_common,
    )
    invalid_b = _summary(
        implementation_sha="sha-infrastructure-b",
        session_id="session-infrastructure-b",
        run_id="session-infrastructure-b:2",
        debug_trace_locator="debug: session-infrastructure-b",
        transcript_locator="transcript: session-infrastructure-b",
        **invalid_common,
    )
    qualifying = _summary(
        attempt=3,
        implementation_sha="sha-qualifying",
        fixture_manifest_sha256="manifest-3-includes-task-3",
        task_sha256="task-3",
        session_id="session-qualifying",
        run_id="session-qualifying:2",
        debug_trace_locator="debug: session-qualifying",
        transcript_locator="transcript: session-qualifying",
        changed_dimension="wording",
        previous_fixture_manifest_sha256="manifest-2-includes-task-2",
        previous_task_sha256="task-2",
    )
    return [attempt_1, attempt_2, invalid_a, invalid_b, qualifying]


def _fu4a_summary(**overrides: object) -> EvidenceSummary:
    values: dict[str, object] = {
        "scenario": "single_pass",
        "implementation_sha": "sha-fu4a",
        "stop_reason": "end_turn",
        "turn_summaries": [
            {
                "settled_turn": 1,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gateway-fu4a"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            }
        ],
        "final_plan_hash_present": True,
        "final_permission_count": 1,
        "post_approval_mutation_count": 1,
    }
    values.update(overrides)
    return _summary(**values)


def _fu4b_summary(**overrides: object) -> EvidenceSummary:
    return _summary(
        scenario="replan",
        implementation_sha="sha-fu4b",
        stop_reason="end_turn",
        settled_turns=2,
        wire_attempts=2,
        gateway_request_ids=["gateway-fu4b-1", "gateway-fu4b-2"],
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "READ_MORE",
                "gateway_request_ids": ["gateway-fu4b-1"],
                "current_read_ranges": [
                    {"path": "target.py", "start_byte": 0, "end_byte": 6144, "source_sha256": "target"},
                    {"path": "policy.txt", "start_byte": 0, "end_byte": 1024, "source_sha256": "policy"},
                ],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            },
            {
                "settled_turn": 2,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gateway-fu4b-2"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            },
        ],
        final_plan_hash_present=True,
        final_permission_count=1,
        post_approval_mutation_count=1,
        **overrides,
    )


def _report_with(*summaries: EvidenceSummary) -> str:
    blocks: list[str] = []
    for summary in summaries:
        blocks.extend(
            [
                "## Evidence\n",
                f"Locator debug: {summary['debug_trace_locator']}\n",
                f"Locator transcript: {summary['transcript_locator']}\n",
                "```json\n",
                json.dumps(summary),
                "\n```\n",
            ]
        )
    return "".join(blocks)


def test_fu5_ledger_allows_duplicate_infrastructure_slot_and_checks_qualifying_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(_report_with(*_refusal_ledger()), encoding="utf-8")
    checked: list[str] = []
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_implementation_sha_clean",
        checked.append,
    )

    verify_report(report, require=("fu5",))

    assert checked == ["sha-qualifying"]


def test_fu5_rejects_drift_in_qualifying_summary_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(_report_with(*_refusal_ledger()), encoding="utf-8")

    def _drifted(implementation_sha: str) -> None:
        assert implementation_sha == "sha-qualifying"
        raise ValueError("implementation drift after sha-qualifying")

    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_implementation_sha_clean",
        _drifted,
    )

    with pytest.raises(ValueError, match="implementation drift"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_two_completed_attempts_at_the_same_slot(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    records = _refusal_ledger()
    records.append(
        _summary(
            attempt=3,
            implementation_sha="sha-second-completed-slot-3",
            fixture_manifest_sha256="manifest-3-includes-task-3",
            task_sha256="task-3",
            session_id="session-second-completed-slot-3",
            run_id="session-second-completed-slot-3:2",
            debug_trace_locator="debug: session-second-completed-slot-3",
            transcript_locator="transcript: session-second-completed-slot-3",
            changed_dimension="wording",
            previous_fixture_manifest_sha256="manifest-2-includes-task-2",
            previous_task_sha256="task-2",
        )
    )
    report.write_text(_report_with(*records), encoding="utf-8")

    with pytest.raises(ValueError, match="slot 3 has multiple completed attempts"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_more_than_three_completed_attempts(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    records = _refusal_ledger()
    records.append(
        _summary(
            attempt=4,
            implementation_sha="sha-attempt-4",
            fixture_manifest_sha256="manifest-4-includes-task-4",
            task_sha256="task-4",
            session_id="session-4",
            run_id="session-4:2",
            debug_trace_locator="debug: session-4",
            transcript_locator="transcript: session-4",
            stop_reason="PLANNING_READ_BUDGET_EXHAUSTED",
            turn_summaries=[
                {
                    "settled_turn": 1,
                    "model_decision": "PLANNING_READ_BUDGET_EXHAUSTED",
                    "gateway_request_ids": ["gateway-4"],
                    "current_read_ranges": [],
                    "plan_hash_present": False,
                    "permission_count": 0,
                    "mutation_count": 0,
                }
            ],
            changed_dimension="wording",
            previous_fixture_manifest_sha256="manifest-3-includes-task-3",
            previous_task_sha256="task-3",
        )
    )
    report.write_text(_report_with(*records), encoding="utf-8")

    with pytest.raises(ValueError, match="FU-5 completed attempts exceed cap"):
        verify_report(report, require=("fu5",))


def test_each_requested_claim_checks_only_its_selected_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        _report_with(_fu4a_summary(), _fu4b_summary(), *_refusal_ledger()), encoding="utf-8"
    )
    checked: list[str] = []
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_implementation_sha_clean",
        checked.append,
    )

    verify_report(report, require=("fu4a", "fu4b", "fu5"))

    assert checked == ["sha-fu4a", "sha-fu4b", "sha-qualifying"]


def test_ambiguous_claim_summaries_are_rejected_instead_of_selecting_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        _report_with(_fu4a_summary(), _fu4a_summary(implementation_sha="sha-fu4a-new")),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_implementation_sha_clean",
        lambda _sha: None,
    )

    with pytest.raises(ValueError, match="fu4a claim is ambiguous"):
        verify_report(report, require=("fu4a",))


def test_post_capture_verifier_is_directly_executable() -> None:
    result = subprocess.run(
        [sys.executable, str(VERIFIER_PATH), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "--verify-report" in result.stdout
