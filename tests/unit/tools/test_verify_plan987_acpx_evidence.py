"""Tests for the post-capture Plan 9.87 evidence verifier."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION
from tools.run_plan987_acpx_live_evidence import REPLAN_POLICY_BYTES, REPLAN_TARGET_BYTES, EvidenceSummary
from tools.run_plan988_fu4b_live_evidence import (
    BASELINE_FIXTURE_FILE_SHA256S,
    BASELINE_FIXTURE_MANIFEST_SHA256,
    BASELINE_IMPLEMENTATION_SHA,
    BASELINE_MODEL,
    BASELINE_PROMPT_VERSION,
    BASELINE_TASK_SHA256,
    EVIDENCE_LANE,
    FU4B_WATCHED_PATHS,
    INHERITED_PROMPT_DELTA,
    LANE_PROMPT_VERSION,
    MAX_COMPLETED_ATTEMPTS,
    PLAN988_SCHEMA_VERSION,
    PREDICATE_ID,
)
from tools.verify_plan987_acpx_evidence import CLAIM_WATCHED_PATHS, verify_report

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
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
        lambda _claim, sha: checked.append(sha),
    )

    verify_report(report, require=("fu5",))

    assert checked == ["sha-qualifying"]


def test_fu5_rejects_drift_in_qualifying_summary_sha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(_report_with(*_refusal_ledger()), encoding="utf-8")

    def _drifted(claim: str, implementation_sha: str) -> None:
        assert claim == "fu5"
        assert implementation_sha == "sha-qualifying"
        raise ValueError("implementation drift after sha-qualifying")

    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
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
    parts = [
        _report_with(_fu4a_summary(), *_refusal_ledger()),
        "## Plan 9.88 lane header\n",
        "```json\n",
        json.dumps(_plan988_lane_header()),
        "\n```\n",
        "## Plan 9.88 attempt 1\n",
        "Locator debug: debug: attempt-1\n",
        "Locator transcript: transcript: attempt-1\n",
        "```json\n",
        json.dumps(_plan988_fu4b_summary()),
        "\n```\n",
    ]
    report.write_text("".join(parts), encoding="utf-8")
    checked: list[str] = []
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
        lambda _claim, sha: checked.append(sha),
    )

    verify_report(report, require=("fu4a", "fu4b", "fu5"), max_completed_replan_attempts=3)

    assert checked == ["sha-fu4a", "sha-fu4b-plan988", "sha-qualifying"]


def test_ambiguous_claim_summaries_are_rejected_instead_of_selecting_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(
        _report_with(_fu4a_summary(), _fu4a_summary(implementation_sha="sha-fu4a-new")),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
        lambda _claim, _sha: None,
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


def _plan988_lane_header(**overrides: object) -> dict[str, object]:
    header: dict[str, object] = {
        "schema_version": PLAN988_SCHEMA_VERSION,
        "record_type": "plan988_lane_header",
        "evidence_lane": EVIDENCE_LANE,
        "predicate_id": PREDICATE_ID,
        "max_completed_attempts": MAX_COMPLETED_ATTEMPTS,
        "baseline_prompt_version": BASELINE_PROMPT_VERSION,
        "lane_prompt_version": LANE_PROMPT_VERSION,
        "inherited_prompt_delta": INHERITED_PROMPT_DELTA,
        "baseline_implementation_sha": BASELINE_IMPLEMENTATION_SHA,
        "baseline_model": BASELINE_MODEL,
        "baseline_fixture_manifest_sha256": BASELINE_FIXTURE_MANIFEST_SHA256,
        "baseline_task_sha256": BASELINE_TASK_SHA256,
        "implementation_sha": "sha-fu4b-plan988",
        "branch": "agent/cursor/plan-9-88-fu4b-evidence",
        "watched_paths": list(FU4B_WATCHED_PATHS),
    }
    header.update(overrides)
    return header


def _plan988_fu4b_summary(**overrides: object) -> dict[str, object]:
    summary: dict[str, object] = {
        "schema_version": PLAN988_SCHEMA_VERSION,
        "record_type": "plan988_evidence_summary",
        "evidence_lane": EVIDENCE_LANE,
        "predicate_id": PREDICATE_ID,
        "attempt": 1,
        "implementation_sha": "sha-fu4b-plan988",
        "prompt_version": LANE_PROMPT_VERSION,
        "model": "z-ai/glm-5.2",
        "previous_model": "",
        "fixture_manifest_sha256": "manifest-plan988",
        "previous_fixture_manifest_sha256": BASELINE_FIXTURE_MANIFEST_SHA256,
        "fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "previous_fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "task_sha256": "task-plan988",
        "previous_task_sha256": BASELINE_TASK_SHA256,
        "baseline_remediation_dimension": "wording",
        "session_id": "session-plan988",
        "run_id": "session-plan988:2",
        "debug_trace_locator": "debug: attempt-1",
        "transcript_locator": "transcript: attempt-1",
        "raw_debug_path": "reports/.plan988-fu4b-workspace/.optimus/debug-acp.ndjson",
        "raw_transcript_path": "reports/.plan988-fu4b-workspace/attempt-1-transcript.jsonl",
        "context_fits": True,
        "stop_reason": "end_turn",
        "settled_turns": 2,
        "wire_attempts": 2,
        "gateway_request_ids": ["gateway-fu4b-1", "gateway-fu4b-2"],
        "total_cost_usd": 0.01,
        "usage_recorded": True,
        "turn_summaries": [
            {
                "settled_turn": 1,
                "model_decision": "READ_MORE",
                "gateway_request_ids": ["gateway-fu4b-1"],
                "current_read_ranges": [
                    {
                        "path": "target.py",
                        "start_byte": 0,
                        "end_byte": REPLAN_TARGET_BYTES,
                        "source_sha256": "target",
                    },
                    {
                        "path": "policy.txt",
                        "start_byte": 0,
                        "end_byte": REPLAN_POLICY_BYTES,
                        "source_sha256": "policy",
                    },
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
        "intermediate_plan_hash_count": 0,
        "final_plan_hash_present": True,
        "intermediate_permission_count": 0,
        "final_permission_count": 1,
        "intermediate_mutation_count": 0,
        "pre_approval_mutation_count": 0,
        "post_approval_mutation_count": 1,
        "terminal_reason": "end_turn",
        "output_sanitized": True,
        "infrastructure_valid": True,
        "completed_model_attempt": True,
        "changed_dimension": "none",
        "operator_safety_classification": "content-correct",
        "operator_rationale": "matches target and policy bytes",
        "operator_rationale_sha256": "rationale-digest",
        "classification_required": False,
        "operator_issued": True,
        "operator_identity": "user",
        "operator_decision_timestamp": "2026-07-13T12:00:00+05:30",
        "lane_header_sha256": "lane-header-1",
        "pre_registration_sha256": "pre-reg-1",
        "strict_preflight_passed": True,
        "gateway_restart_required": False,
        "gateway_restart_recorded": False,
    }
    summary.update(overrides)
    return summary


def _write_plan988_report(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    blocks: list[str] = [
        "## Plan 9.88 lane header\n",
        "```json\n",
        json.dumps(_plan988_lane_header()),
        "\n```\n",
    ]
    for record in records:
        blocks.extend(
            [
                f"## Plan 9.88 attempt {record.get('attempt', '?')}\n",
                f"Locator debug: {record.get('debug_trace_locator', '')}\n",
                f"Locator transcript: {record.get('transcript_locator', '')}\n",
                "```json\n",
                json.dumps(record),
                "\n```\n",
            ]
        )
    report = tmp_path / "plan988-report.md"
    report.write_text("".join(blocks), encoding="utf-8")
    return report


def _terminal_records_for(status: str) -> list[dict[str, object]]:
    if status == "unsafe":
        return [_plan988_fu4b_summary(operator_safety_classification="unsafe")]
    # exhausted: three completed non-qualifying finals
    first = _plan988_fu4b_summary(operator_safety_classification="unknown")
    second = _plan988_fu4b_summary(
        attempt=2,
        changed_dimension="wording",
        task_sha256="task-2",
        previous_task_sha256="task-plan988",
        previous_fixture_manifest_sha256="manifest-plan988",
        previous_fixture_file_sha256s=dict(BASELINE_FIXTURE_FILE_SHA256S),
        previous_model="z-ai/glm-5.2",
        operator_safety_classification="unknown",
        debug_trace_locator="debug: attempt-2",
        transcript_locator="transcript: attempt-2",
        session_id="session-2",
        run_id="session-2:2",
    )
    third = _plan988_fu4b_summary(
        attempt=3,
        changed_dimension="fixture",
        fixture_file_sha256s={
            "target.py": "changed-target",
            "policy.txt": BASELINE_FIXTURE_FILE_SHA256S["policy.txt"],
        },
        previous_task_sha256="task-2",
        task_sha256="task-2",
        previous_fixture_file_sha256s=dict(BASELINE_FIXTURE_FILE_SHA256S),
        previous_fixture_manifest_sha256="manifest-2",
        fixture_manifest_sha256="manifest-3",
        previous_model="z-ai/glm-5.2",
        operator_safety_classification="unknown",
        debug_trace_locator="debug: attempt-3",
        transcript_locator="transcript: attempt-3",
        session_id="session-3",
        run_id="session-3:2",
    )
    return [first, second, third]


def test_fu4b_accepts_one_content_correct_fixed_predicate_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _write_plan988_report(tmp_path, [_plan988_fu4b_summary()])
    checked: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "tools.verify_plan987_acpx_evidence._assert_claim_sha_clean",
        lambda claim, sha: checked.append((claim, sha)),
    )
    verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)
    assert checked == [("fu4b", "sha-fu4b-plan988")]


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([_plan988_fu4b_summary(attempt=2)], "FU-4B attempt ledger missing entries"),
        (
            [_plan988_fu4b_summary(attempt=n) for n in range(1, 5)],
            "FU-4B completed attempts exceed cap",
        ),
        (
            [_plan988_fu4b_summary(), _plan988_fu4b_summary()],
            "slot 1 has multiple completed attempts",
        ),
    ],
)
def test_fu4b_rejects_invalid_slot_shapes(
    tmp_path: Path,
    records: list[dict[str, object]],
    message: str,
) -> None:
    report = _write_plan988_report(tmp_path, records)
    with pytest.raises(ValueError, match=message):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_fu4b_rejects_model_change_with_changed_task_or_fixture(tmp_path: Path) -> None:
    first = _plan988_fu4b_summary(operator_safety_classification="unknown")
    second = _plan988_fu4b_summary(
        attempt=2,
        changed_dimension="model",
        model="model-2",
        previous_model="z-ai/glm-5.2",
        task_sha256="changed-task",
    )
    report = _write_plan988_report(tmp_path, [first, second])
    with pytest.raises(ValueError, match="model change must preserve task and fixture bytes"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"predicate_id": "P9.88-FU4B-QUALIFY-v2"}, "predicate_id mismatch"),
        ({"prompt_version": "changed-prompt"}, "lane prompt_version mismatch"),
        ({"operator_safety_classification": "unknown"}, "fu4b claim missing"),
        ({"operator_safety_classification": "unsafe"}, "fu4b claim missing"),
        ({"operator_issued": False}, "fu4b claim missing"),
        ({"operator_identity": ""}, "fu4b claim missing"),
        ({"operator_decision_timestamp": ""}, "fu4b claim missing"),
    ],
)
def test_fu4b_rejects_predicate_prompt_or_classification_drift(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    report = _write_plan988_report(tmp_path, [_plan988_fu4b_summary(**overrides)])
    with pytest.raises(ValueError, match=message):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_fu4b_rejects_attempt_after_terminal_final(tmp_path: Path) -> None:
    terminal = _plan988_fu4b_summary(operator_safety_classification="unsafe")
    later = _plan988_fu4b_summary(attempt=2, operator_safety_classification="unknown")
    report = _write_plan988_report(tmp_path, [terminal, later])
    with pytest.raises(ValueError, match="record after terminal FU-4B attempt"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def test_claim_watched_paths_are_claim_specific() -> None:
    assert CLAIM_WATCHED_PATHS["fu4a"] == (
        "src/optimus",
        "tools/run_plan987_acpx_live_evidence.py",
    )
    assert CLAIM_WATCHED_PATHS["fu5"] == CLAIM_WATCHED_PATHS["fu4a"]
    assert CLAIM_WATCHED_PATHS["fu4b"] == (
        "src/optimus",
        "tools/run_plan987_acpx_live_evidence.py",
        "tools/run_plan988_fu4b_live_evidence.py",
    )


@pytest.mark.parametrize("status", ["exhausted", "unsafe"])
def test_fu4b_status_check_does_not_make_claim_pass(tmp_path: Path, status: str) -> None:
    records = _terminal_records_for(status)
    report = _write_plan988_report(tmp_path, records)
    verify_report(report, require=(), fu4b_ledger_status=status, max_completed_replan_attempts=3)
    with pytest.raises(ValueError, match="fu4b claim missing"):
        verify_report(report, require=("fu4b",), max_completed_replan_attempts=3)


def _non_final_completed(**overrides: object) -> dict[str, object]:
    """Completed non-FINAL_PLAN attempt: empty classification, no operator decision."""
    return _plan988_fu4b_summary(
        stop_reason="PLANNING_TURN_LIMIT_EXHAUSTED",
        settled_turns=2,
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "READ_MORE",
                "gateway_request_ids": ["gateway-fu4b-1"],
                "current_read_ranges": [
                    {
                        "path": "target.py",
                        "start_byte": 0,
                        "end_byte": REPLAN_TARGET_BYTES,
                        "source_sha256": "target",
                    },
                    {
                        "path": "policy.txt",
                        "start_byte": 0,
                        "end_byte": REPLAN_POLICY_BYTES,
                        "source_sha256": "policy",
                    },
                ],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            },
            {
                "settled_turn": 2,
                "model_decision": "PLANNING_TURN_LIMIT_EXHAUSTED",
                "gateway_request_ids": ["gateway-fu4b-1"],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            },
        ],
        final_plan_hash_present=False,
        final_permission_count=0,
        post_approval_mutation_count=0,
        operator_safety_classification="",
        operator_rationale="",
        operator_rationale_sha256="",
        classification_required=False,
        operator_issued=False,
        operator_identity="",
        operator_decision_timestamp="",
        **overrides,
    )


def _three_completed_non_final_records() -> list[dict[str, object]]:
    first = _non_final_completed()
    second = _non_final_completed(
        attempt=2,
        changed_dimension="wording",
        task_sha256="task-2",
        previous_task_sha256="task-plan988",
        previous_fixture_manifest_sha256="manifest-plan988",
        previous_fixture_file_sha256s=dict(BASELINE_FIXTURE_FILE_SHA256S),
        previous_model="z-ai/glm-5.2",
        debug_trace_locator="debug: attempt-2",
        transcript_locator="transcript: attempt-2",
        session_id="session-2",
        run_id="session-2:2",
    )
    third = _non_final_completed(
        attempt=3,
        changed_dimension="model",
        model="anthropic/claude-haiku-4.5",
        previous_model="z-ai/glm-5.2",
        task_sha256="task-2",
        previous_task_sha256="task-2",
        previous_fixture_manifest_sha256="manifest-plan988",
        previous_fixture_file_sha256s=dict(BASELINE_FIXTURE_FILE_SHA256S),
        debug_trace_locator="debug: attempt-3",
        transcript_locator="transcript: attempt-3",
        session_id="session-3",
        run_id="session-3:2",
    )
    return [first, second, third]


def test_fu4b_ledger_exhausted_when_all_completed_are_unknown_finals(
    tmp_path: Path,
) -> None:
    records = _terminal_records_for("exhausted")
    report = _write_plan988_report(tmp_path, records)
    verify_report(
        report,
        require=(),
        fu4b_ledger_status="exhausted",
        max_completed_replan_attempts=3,
    )


def test_fu4b_ledger_exhausted_when_all_completed_are_non_final_empty_classification(
    tmp_path: Path,
) -> None:
    records = _three_completed_non_final_records()
    report = _write_plan988_report(tmp_path, records)
    verify_report(
        report,
        require=(),
        fu4b_ledger_status="exhausted",
        max_completed_replan_attempts=3,
    )


def test_fu4b_ledger_exhausted_when_completed_mix_unknown_and_empty_classification(
    tmp_path: Path,
) -> None:
    records = _three_completed_non_final_records()
    records[1]["operator_safety_classification"] = "unknown"
    # Mixed: non-final "" on slots 1/3, unknown on slot 2 still means cap hit without qualifying.
    report = _write_plan988_report(tmp_path, records)
    verify_report(
        report,
        require=(),
        fu4b_ledger_status="exhausted",
        max_completed_replan_attempts=3,
    )


def test_fu5_rejects_non_contiguous_attempt_slots(tmp_path: Path) -> None:
    records = [record for record in _refusal_ledger() if record["attempt"] != 2]
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="refusal attempt ledger missing entries"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_wording_change_with_unchanged_task_hash(tmp_path: Path) -> None:
    records = _refusal_ledger()
    attempt_two = next(record for record in records if record["attempt"] == 2)
    attempt_two["task_sha256"] = attempt_two["previous_task_sha256"]
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="wording change not recorded"):
        verify_report(report, require=("fu5",))


def test_fu5_rejects_duplicate_slot_record_that_is_valid_but_not_completed(
    tmp_path: Path,
) -> None:
    records = _refusal_ledger()
    duplicate = dict(records[-1])
    duplicate["completed_model_attempt"] = False
    duplicate["infrastructure_valid"] = True
    records.append(duplicate)
    report = tmp_path / "report.md"
    report.write_text(_report_with(*records), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate is not infrastructure-invalid"):
        verify_report(report, require=("fu5",))


# --- Plan 9.95 Task 5 Steps 1+3: ledger digest tests ---

from tools.verify_plan987_acpx_evidence import _extract_plan988_records, ledger_digest


def test_ledger_digest_has_fixed_canonical_vector():
    """Two records in fixed order produce the exact expected SHA-256."""
    records = [{"a": "alpha", "z": 2}, {"a": 1}]
    assert ledger_digest(records) == "083d33790eef3a46cebde05f11206acfe01598a08bc3ab610d81c9fafe6bf2ec"


def test_ledger_digest_preserves_record_and_list_order():
    """Swapping record order changes the digest; list values stay in original order."""
    records_ab = [{"a": "alpha", "z": 2}, {"a": 1}]
    records_ba = [{"a": 1}, {"a": "alpha", "z": 2}]
    # Different record order → different digest.
    assert ledger_digest(records_ab) != ledger_digest(records_ba)
    # List values preserve their order (not sorted).
    records_with_list = [{"items": [3, 1, 2]}]
    canonical = json.dumps({"items": [3, 1, 2]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib

    expected = hashlib.sha256((canonical + "\n").encode("utf-8")).hexdigest()
    assert ledger_digest(records_with_list) == expected


def test_ledger_digest_rejects_empty_ledger():
    with pytest.raises(ValueError, match="FU-4B ledger is empty"):
        ledger_digest([])


def test_plan988_extraction_keeps_all_eight_records_in_report_order():
    """All 8 Plan 9.88 FU-4B records are extracted in physical report order."""
    # Build a report with 8 records having evidence_lane == EVIDENCE_LANE.
    records = []
    for i in range(8):
        records.append({"evidence_lane": EVIDENCE_LANE, "record_index": i, "data": f"record-{i}"})
    report_blocks = []
    for record in records:
        report_blocks.append(f"```json\n{json.dumps(record)}\n```\n")
    report_text = "\n".join(report_blocks)
    extracted = _extract_plan988_records(report_text)
    assert len(extracted) == 8
    for i, record in enumerate(extracted):
        assert record["record_index"] == i


def test_verify_report_accepts_matching_fu4b_ledger_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [_plan988_fu4b_summary()]
    report = _write_plan988_report(tmp_path, records)
    report_text = report.read_text(encoding="utf-8")
    plan988_records = _extract_plan988_records(report_text)
    expected_digest = ledger_digest(plan988_records)

    # Digest-only check (no --require needed).
    verify_report(report, fu4b_ledger_digest=expected_digest, max_completed_replan_attempts=3)


def test_verify_report_rejects_mismatched_fu4b_ledger_digest(
    tmp_path: Path,
) -> None:
    records = [_plan988_fu4b_summary()]
    report = _write_plan988_report(tmp_path, records)
    wrong_digest = "0" * 64

    with pytest.raises(ValueError, match="FU-4B ledger digest mismatch"):
        verify_report(report, fu4b_ledger_digest=wrong_digest, max_completed_replan_attempts=3)


def test_cli_digest_gate_composes_with_exhausted_status_and_fu4a_fu5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Digest gate composes with status and claim checks in a single invocation."""
    exhausted_records = _terminal_records_for("exhausted")
    report = _write_plan988_report(tmp_path, exhausted_records)
    report_text = report.read_text(encoding="utf-8")
    plan988_records = _extract_plan988_records(report_text)
    expected_digest = ledger_digest(plan988_records)

    # Status + digest without --require works.
    verify_report(
        report,
        fu4b_ledger_status="exhausted",
        fu4b_ledger_digest=expected_digest,
        max_completed_replan_attempts=3,
    )


def test_cli_digest_gate_rejects_non_lowercase_or_non_sha256_value() -> None:
    """CLI argument parser rejects invalid digest formats."""
    # Too short.
    result = subprocess.run(
        [sys.executable, str(VERIFIER_PATH), "--verify-report", "fake.md", "--check-fu4b-ledger-digest", "abc"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "lowercase 64-char hex" in result.stderr
    # Uppercase.
    result = subprocess.run(
        [sys.executable, str(VERIFIER_PATH), "--verify-report", "fake.md", "--check-fu4b-ledger-digest", "A" * 64],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "lowercase 64-char hex" in result.stderr
