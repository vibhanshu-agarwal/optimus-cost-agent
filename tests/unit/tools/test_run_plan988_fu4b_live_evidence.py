"""Unit tests for Plan 9.88 FU-4B live evidence schema and attempt-1 fixture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_plan987_acpx_live_evidence import (  # noqa: E402
    REPLAN_POLICY_BYTES,
    REPLAN_TARGET_BYTES,
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
    PLAN988_SUMMARY_FIELDS,
    PREDICATE_ID,
    Plan988EvidenceSummary,
    Plan988LaneHeader,
    Plan988PreRegistration,
    fixture_file_sha256s,
    prepare_fu4b_fixture,
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
