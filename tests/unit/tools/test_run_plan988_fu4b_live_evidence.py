"""Unit tests for Plan 9.88 FU-4B live evidence schema and attempt-1 fixture."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import run_plan988_fu4b_live_evidence as plan988  # noqa: E402
from tools.run_plan987_acpx_live_evidence import (  # noqa: E402
    REPLAN_POLICY_BYTES,
    REPLAN_TARGET_BYTES,
    _sha256_text,
)
from tools.run_plan988_fu4b_live_evidence import (  # noqa: E402
    BASELINE_FIXTURE_FILE_SHA256S,
    BASELINE_FIXTURE_MANIFEST_SHA256,
    BASELINE_IMPLEMENTATION_SHA,
    BASELINE_PROMPT_VERSION,
    BASELINE_TASK_SHA256,
    EVIDENCE_LANE,
    LANE_PROMPT_VERSION,
    PLAN988_LANE_HEADER_FIELDS,
    PLAN988_PRE_REGISTRATION_FIELDS,
    PLAN988_REPLAN_TASK,
    PLAN988_REPLAN_TASK_ATTEMPT2,
    PLAN988_SUMMARY_FIELDS,
    PREDICATE_ID,
    Plan988EvidenceSummary,
    Plan988LaneHeader,
    Plan988PreRegistration,
    classify_fu4b_final,
    fixture_file_sha256s,
    prepare_fu4b_fixture,
    select_fu4b_task,
    validate_next_attempt,
)


def test_plan988_constants_pin_approved_baseline() -> None:
    assert EVIDENCE_LANE == "P9.88-FU4B"
    assert PREDICATE_ID == "P9.88-FU4B-QUALIFY-v1"
    assert BASELINE_IMPLEMENTATION_SHA == "d71b29390c7bafe57612bcc0ea3a0fcf5c06d7e9"
    assert BASELINE_FIXTURE_MANIFEST_SHA256 == (
        "a642d014fe0317d3bb8d76fd03ce596721a5d223129da7150ee8c5b4cad082bd"
    )
    assert BASELINE_TASK_SHA256 == (
        "72ac1a176db8bbe91f8533aa1b701b36f319eeecb5860dcb03d8bfb363175252"
    )
    assert BASELINE_FIXTURE_FILE_SHA256S == {
        "target.py": "96fb9c16da5fb69693ec7607d495f905f4162f40de2049a8891a3dee1643a4b8",
        "policy.txt": "dcfe98c1394d297d51cc0d82b88ecb0c1cfccf71182cd7354c5bfef992a39908",
    }
    assert BASELINE_PROMPT_VERSION.endswith("-fu4c")
    assert LANE_PROMPT_VERSION.endswith("-fu5a")


def test_attempt_one_fixture_changes_only_cross_lane_wording(tmp_path: Path) -> None:
    manifest = prepare_fu4b_fixture(tmp_path)
    assert manifest["task"] == PLAN988_REPLAN_TASK
    assert "policy.txt" in PLAN988_REPLAN_TASK
    assert manifest["task_sha256"] != BASELINE_TASK_SHA256
    assert (tmp_path / "target.py").stat().st_size == REPLAN_TARGET_BYTES
    assert (tmp_path / "policy.txt").stat().st_size == REPLAN_POLICY_BYTES
    assert fixture_file_sha256s(tmp_path) == BASELINE_FIXTURE_FILE_SHA256S
    assert manifest["fixture_file_sha256s"] == BASELINE_FIXTURE_FILE_SHA256S


def test_attempt_two_wording_selects_new_task_preserving_fixture_bytes(tmp_path: Path) -> None:
    assert select_fu4b_task(attempt=1, changed_dimension="none") == PLAN988_REPLAN_TASK
    assert (
        select_fu4b_task(attempt=2, changed_dimension="wording") == PLAN988_REPLAN_TASK_ATTEMPT2
    )
    assert PLAN988_REPLAN_TASK_ATTEMPT2 != PLAN988_REPLAN_TASK
    assert "1024" in PLAN988_REPLAN_TASK_ATTEMPT2
    assert "4096" in PLAN988_REPLAN_TASK_ATTEMPT2

    attempt1 = prepare_fu4b_fixture(tmp_path / "a1")
    attempt2 = prepare_fu4b_fixture(
        tmp_path / "a2",
        task=select_fu4b_task(attempt=2, changed_dimension="wording"),
    )
    assert attempt2["task"] == PLAN988_REPLAN_TASK_ATTEMPT2
    assert attempt2["task_sha256"] != attempt1["task_sha256"]
    assert attempt2["task_sha256"] == _sha256_text(PLAN988_REPLAN_TASK_ATTEMPT2)
    assert attempt2["fixture_file_sha256s"] == attempt1["fixture_file_sha256s"]
    assert attempt2["fixture_file_sha256s"] == BASELINE_FIXTURE_FILE_SHA256S
    assert attempt2["fixture_manifest_sha256"] != attempt1["fixture_manifest_sha256"]


def test_plan988_schema_field_sets_are_pinned() -> None:
    assert PLAN988_LANE_HEADER_FIELDS == {
        "schema_version",
        "record_type",
        "evidence_lane",
        "predicate_id",
        "max_completed_attempts",
        "baseline_prompt_version",
        "lane_prompt_version",
        "inherited_prompt_delta",
        "baseline_implementation_sha",
        "baseline_model",
        "baseline_fixture_manifest_sha256",
        "baseline_task_sha256",
        "implementation_sha",
        "branch",
        "watched_paths",
    }
    assert PLAN988_PRE_REGISTRATION_FIELDS == {
        "schema_version",
        "record_type",
        "evidence_lane",
        "predicate_id",
        "attempt",
        "implementation_sha",
        "prompt_version",
        "model",
        "previous_model",
        "changed_dimension",
        "baseline_remediation_dimension",
        "rationale",
        "fixture_manifest_sha256",
        "previous_fixture_manifest_sha256",
        "fixture_file_sha256s",
        "previous_fixture_file_sha256s",
        "task_sha256",
        "previous_task_sha256",
        "strict_preflight_passed",
        "gateway_restart_required",
        "gateway_restart_recorded",
        "raw_debug_path",
        "raw_transcript_path",
        "max_planning_turns",
        "max_cost_usd",
        "wall_clock_minutes",
        "lane_header_sha256",
    }
    assert PLAN988_SUMMARY_FIELDS == {
        "schema_version",
        "record_type",
        "evidence_lane",
        "predicate_id",
        "attempt",
        "implementation_sha",
        "prompt_version",
        "model",
        "previous_model",
        "fixture_manifest_sha256",
        "previous_fixture_manifest_sha256",
        "fixture_file_sha256s",
        "previous_fixture_file_sha256s",
        "task_sha256",
        "previous_task_sha256",
        "baseline_remediation_dimension",
        "session_id",
        "run_id",
        "debug_trace_locator",
        "transcript_locator",
        "raw_debug_path",
        "raw_transcript_path",
        "context_fits",
        "stop_reason",
        "settled_turns",
        "wire_attempts",
        "gateway_request_ids",
        "total_cost_usd",
        "usage_recorded",
        "turn_summaries",
        "intermediate_plan_hash_count",
        "final_plan_hash_present",
        "intermediate_permission_count",
        "final_permission_count",
        "intermediate_mutation_count",
        "pre_approval_mutation_count",
        "post_approval_mutation_count",
        "terminal_reason",
        "output_sanitized",
        "infrastructure_valid",
        "completed_model_attempt",
        "changed_dimension",
        "operator_safety_classification",
        "operator_rationale",
        "operator_rationale_sha256",
        "classification_required",
        "operator_issued",
        "operator_identity",
        "operator_decision_timestamp",
        "lane_header_sha256",
        "pre_registration_sha256",
        "strict_preflight_passed",
        "gateway_restart_required",
        "gateway_restart_recorded",
    }
    assert set(Plan988LaneHeader.__annotations__) == PLAN988_LANE_HEADER_FIELDS
    assert set(Plan988PreRegistration.__annotations__) == PLAN988_PRE_REGISTRATION_FIELDS
    assert set(Plan988EvidenceSummary.__annotations__) == PLAN988_SUMMARY_FIELDS


def _registration(**overrides: Any) -> Plan988PreRegistration:
    base: Plan988PreRegistration = {
        "schema_version": plan988.PLAN988_SCHEMA_VERSION,
        "record_type": "plan988_pre_registration",
        "evidence_lane": EVIDENCE_LANE,
        "predicate_id": PREDICATE_ID,
        "attempt": 1,
        "implementation_sha": "a" * 40,
        "prompt_version": LANE_PROMPT_VERSION,
        "model": "z-ai/glm-5.2",
        "previous_model": "",
        "changed_dimension": "none",
        "baseline_remediation_dimension": "wording",
        "rationale": "attempt-1 cross-lane wording remediation",
        "fixture_manifest_sha256": "manifest-1",
        "previous_fixture_manifest_sha256": BASELINE_FIXTURE_MANIFEST_SHA256,
        "fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "previous_fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "task_sha256": "task-1",
        "previous_task_sha256": BASELINE_TASK_SHA256,
        "strict_preflight_passed": True,
        "gateway_restart_required": False,
        "gateway_restart_recorded": False,
        "raw_debug_path": "reports/.plan988-fu4b-workspace/.optimus/debug-acp.ndjson",
        "raw_transcript_path": "reports/.plan988-fu4b-workspace/attempt-1-transcript.jsonl",
        "max_planning_turns": 8,
        "max_cost_usd": 1.0,
        "wall_clock_minutes": 30,
        "lane_header_sha256": "lane-header-1",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _completed_summary(**overrides: Any) -> Plan988EvidenceSummary:
    base: Plan988EvidenceSummary = {
        "schema_version": plan988.PLAN988_SCHEMA_VERSION,
        "record_type": "plan988_evidence_summary",
        "evidence_lane": EVIDENCE_LANE,
        "predicate_id": PREDICATE_ID,
        "attempt": 1,
        "implementation_sha": "a" * 40,
        "prompt_version": LANE_PROMPT_VERSION,
        "model": "z-ai/glm-5.2",
        "previous_model": "",
        "fixture_manifest_sha256": "manifest-1",
        "previous_fixture_manifest_sha256": BASELINE_FIXTURE_MANIFEST_SHA256,
        "fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "previous_fixture_file_sha256s": dict(BASELINE_FIXTURE_FILE_SHA256S),
        "task_sha256": "task-1",
        "previous_task_sha256": BASELINE_TASK_SHA256,
        "baseline_remediation_dimension": "wording",
        "session_id": "session-1",
        "run_id": "run-1",
        "debug_trace_locator": "debug: attempt-1",
        "transcript_locator": "transcript: attempt-1",
        "raw_debug_path": "reports/.plan988-fu4b-workspace/.optimus/debug-acp.ndjson",
        "raw_transcript_path": "reports/.plan988-fu4b-workspace/attempt-1-transcript.jsonl",
        "context_fits": True,
        "stop_reason": "COMPLETE",
        "settled_turns": 1,
        "wire_attempts": 1,
        "gateway_request_ids": ["gw-1"],
        "total_cost_usd": 0.01,
        "usage_recorded": True,
        "turn_summaries": [],
        "intermediate_plan_hash_count": 0,
        "final_plan_hash_present": False,
        "intermediate_permission_count": 0,
        "final_permission_count": 0,
        "intermediate_mutation_count": 0,
        "pre_approval_mutation_count": 0,
        "post_approval_mutation_count": 0,
        "terminal_reason": "COMPLETE",
        "output_sanitized": True,
        "infrastructure_valid": True,
        "completed_model_attempt": True,
        "changed_dimension": "none",
        "operator_safety_classification": "unknown",
        "operator_rationale": "non-qualifying",
        "operator_rationale_sha256": "rationale-1",
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
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_attempt_two_rejects_two_changed_dimensions() -> None:
    prior = _completed_summary(attempt=1)
    registration = _registration(
        attempt=2,
        changed_dimension="wording",
        task_sha256="task-2",
        fixture_file_sha256s={"target.py": "changed", "policy.txt": "policy-1"},
    )
    with pytest.raises(ValueError, match="wording change must preserve fixture bytes"):
        validate_next_attempt([prior], registration)


def test_model_change_requires_prior_model_and_stable_task_fixture_digests() -> None:
    prior = _completed_summary(attempt=1, model="z-ai/glm-5.2")
    registration = _registration(
        attempt=2,
        changed_dimension="model",
        model="model-2",
        previous_model="",
    )
    with pytest.raises(ValueError, match="model change requires previous_model"):
        validate_next_attempt([prior], registration)


def test_infrastructure_invalid_run_does_not_consume_slot() -> None:
    invalid = _completed_summary(
        attempt=1,
        infrastructure_valid=False,
        completed_model_attempt=False,
    )
    validate_next_attempt([invalid], _registration(attempt=1, changed_dimension="none"))


@pytest.mark.parametrize(
    ("classification", "expected"),
    [
        ("unknown", "unknown_non_qualifying"),
        ("unsafe", "unsafe_terminal"),
        ("content-correct", "qualifying_candidate"),
    ],
)
def test_final_classification_is_explicit(classification: str, expected: str) -> None:
    summary = _completed_summary(
        classification_required=True,
        operator_safety_classification=classification,  # type: ignore[arg-type]
        operator_issued=True,
        operator_identity="user",
        operator_decision_timestamp="2026-07-13T12:00:00+05:30",
    )
    assert classify_fu4b_final(summary) == expected


def test_attempt_after_terminal_record_is_rejected() -> None:
    terminal = _completed_summary(
        attempt=1,
        classification_required=True,
        operator_safety_classification="unsafe",
    )
    with pytest.raises(ValueError, match="FU-4B lane already terminated"):
        validate_next_attempt(
            [terminal],
            _registration(attempt=2, changed_dimension="wording"),
        )


def test_helper_source_does_not_implement_acp_protocol() -> None:
    source = Path(plan988.__file__).read_text(encoding="utf-8")
    assert "session/new" not in source
    assert "session/prompt" not in source
    assert "jsonrpc" not in source.lower()
    assert "subprocess.run" in source


def test_run_loads_persisted_pre_registration_not_rebuilt_args(tmp_path: Path) -> None:
    """Task 6 separates --pre-register and --run with different argv; run must bind the report record."""
    report = tmp_path / "report.md"
    persisted = _registration(
        attempt=1,
        baseline_remediation_dimension="wording",
        strict_preflight_passed=True,
        model="z-ai/glm-5.2",
        rationale="attempt-1 cross-lane wording remediation",
    )
    digest = plan988.pre_register_attempt(report, persisted)
    loaded = plan988.load_pre_registration(report, attempt=1)
    assert loaded == persisted
    assert plan988.registration_sha256(loaded) == digest
    # Divergent Step-3-style args must not be used when a persisted record exists.
    assert loaded["baseline_remediation_dimension"] == "wording"
    assert loaded["strict_preflight_passed"] is True
    assert loaded["baseline_remediation_dimension"] != ""
    assert loaded["strict_preflight_passed"] is not False
