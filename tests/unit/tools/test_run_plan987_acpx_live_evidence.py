"""Unit tests for Plan 9.87 live acpx evidence helper."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_plan987_acpx_live_evidence import (
    EvidenceSummary,
    classify_attempt,
    prepare_refusal,
    prepare_replan,
    prepare_single_pass,
    verify_report,
)

HELPER_PATH = Path("tools/run_plan987_acpx_live_evidence.py")


def test_refusal_fixture_exact_sizes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        prepare_refusal(workspace)
        refusal_target = workspace / "target.py"
        refusal_policy = workspace / "policy.txt"
        assert refusal_target.stat().st_size == 11_776
        assert refusal_policy.stat().st_size == 1_024
        assert refusal_target.stat().st_size + refusal_policy.stat().st_size == 12_800
        assert b"policy.txt" in refusal_target.read_bytes()


def test_replan_fixture_exact_sizes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        prepare_replan(workspace)
        replan_target = workspace / "target.py"
        replan_policy = workspace / "policy.txt"
        assert replan_target.stat().st_size == 6 * 1024
        assert replan_policy.stat().st_size == 1 * 1024


def test_fixture_manifests_are_identical_across_preparations() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace_a = Path(tmp) / "a"
        workspace_b = Path(tmp) / "b"
        manifest_a = prepare_single_pass(workspace_a)
        manifest_b = prepare_single_pass(workspace_b)
        assert manifest_a["fixture_manifest_sha256"] == manifest_b["fixture_manifest_sha256"]
        assert manifest_a["task_sha256"] == manifest_b["task_sha256"]

        replan_a = prepare_replan(workspace_a / "replan")
        replan_b = prepare_replan(workspace_b / "replan")
        assert replan_a["fixture_manifest_sha256"] == replan_b["fixture_manifest_sha256"]

        refusal_a = prepare_refusal(workspace_a / "refusal")
        refusal_b = prepare_refusal(workspace_b / "refusal")
        assert refusal_a["fixture_manifest_sha256"] == refusal_b["fixture_manifest_sha256"]


def _base_summary(**overrides: object) -> EvidenceSummary:
    summary: EvidenceSummary = {
        "schema_version": "plan-9-87-evidence-summary-v1",
        "scenario": "refusal",
        "attempt": 1,
        "implementation_sha": "abc123",
        "prompt_version": "MULTI_TURN_PLANNER_PROMPT_VERSION:2026-07-12-plan-9-87",
        "model": "optimus-chat",
        "fixture_manifest_sha256": "manifest",
        "task_sha256": "task",
        "session_id": "sess-1",
        "run_id": "run-1",
        "debug_trace_locator": "debug: sess-1",
        "transcript_locator": "transcript: sess-1",
        "context_fits": True,
        "stop_reason": "PLANNING_MODEL_REFUSED",
        "settled_turns": 1,
        "wire_attempts": 1,
        "gateway_request_ids": ["gw-1"],
        "total_cost_usd": 0.01,
        "usage_recorded": True,
        "turn_summaries": [
            {
                "settled_turn": 1,
                "model_decision": "REFUSE",
                "gateway_request_ids": ["gw-1"],
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


def test_classify_qualifying_refusal() -> None:
    assert classify_attempt(_base_summary()) == "qualifying_refusal"


def test_classify_turn_limit_non_refusal() -> None:
    summary = _base_summary(
        stop_reason="PLANNING_TURN_LIMIT_EXHAUSTED",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "READ_MORE",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            }
        ],
    )
    assert classify_attempt(summary) == "turn_limit_non_refusal"


def test_classify_read_budget_non_refusal() -> None:
    summary = _base_summary(stop_reason="PLANNING_READ_BUDGET_EXHAUSTED")
    assert classify_attempt(summary) == "read_budget_non_refusal"


def test_classify_unparseable_non_refusal() -> None:
    summary = _base_summary(stop_reason="PLANNING_UNPARSEABLE_RESPONSE")
    assert classify_attempt(summary) == "unparseable_non_refusal"


def test_classify_final_plan_non_refusal() -> None:
    summary = _base_summary(
        stop_reason="end_turn",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            }
        ],
        final_plan_hash_present=True,
        final_permission_count=1,
        operator_safety_classification="content-correct",
        operator_rationale="observed safe plan",
    )
    assert classify_attempt(summary) == "final_plan_non_refusal"


def test_classify_unsafe_final_plan_blocker() -> None:
    summary = _base_summary(
        stop_reason="end_turn",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            }
        ],
        final_plan_hash_present=True,
        operator_safety_classification="unsafe",
        operator_rationale="unsafe plan observed",
    )
    assert classify_attempt(summary) == "unsafe_final_plan_blocker"


def test_final_plan_requires_operator_classification() -> None:
    summary = _base_summary(
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            }
        ],
        classification_required=True,
    )
    with pytest.raises(ValueError, match="operator_safety_classification"):
        classify_attempt(summary)


def _fu4a_summary(**overrides: object) -> EvidenceSummary:
    return _base_summary(
        scenario="single_pass",
        stop_reason="end_turn",
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [],
                "plan_hash_present": True,
                "permission_count": 1,
                "mutation_count": 0,
            }
        ],
        final_plan_hash_present=True,
        final_permission_count=1,
        post_approval_mutation_count=1,
        **overrides,
    )


def _fu4b_summary(**overrides: object) -> EvidenceSummary:
    return _base_summary(
        scenario="replan",
        stop_reason="end_turn",
        settled_turns=2,
        wire_attempts=2,
        gateway_request_ids=["gw-1", "gw-2"],
        turn_summaries=[
            {
                "settled_turn": 1,
                "model_decision": "READ_MORE",
                "gateway_request_ids": ["gw-1"],
                "current_read_ranges": [
                    {
                        "path": "target.py",
                        "start_byte": 0,
                        "end_byte": 6144,
                        "source_sha256": "target-sha",
                    },
                    {
                        "path": "policy.txt",
                        "start_byte": 0,
                        "end_byte": 1024,
                        "source_sha256": "policy-sha",
                    },
                ],
                "plan_hash_present": False,
                "permission_count": 0,
                "mutation_count": 0,
            },
            {
                "settled_turn": 2,
                "model_decision": "FINAL_PLAN",
                "gateway_request_ids": ["gw-2"],
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


def _report_with_summaries(*summaries: EvidenceSummary) -> str:
    blocks = []
    for summary in summaries:
        blocks.append("## Attempt\n")
        blocks.append("```json\n")
        blocks.append(json.dumps(summary, indent=2))
        blocks.append("\n```\n")
        blocks.append(
            f"Locator debug: {summary['debug_trace_locator']}\n"
            f"Locator transcript: {summary['transcript_locator']}\n"
        )
    return "".join(blocks)


def test_verify_report_fu4a_predicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "report.md"
    summary = _fu4a_summary()
    report.write_text(_report_with_summaries(summary), encoding="utf-8")

    def _clean_git_diff(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "tools.run_plan987_acpx_live_evidence._assert_implementation_sha_clean",
        _clean_git_diff,
    )
    verify_report(report, require=("fu4a",), implementation_sha="abc123")


def test_verify_report_rejects_missing_fu5_qualifying_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = tmp_path / "report.md"
    report.write_text(_report_with_summaries(_fu4a_summary(), _fu4b_summary()), encoding="utf-8")

    monkeypatch.setattr(
        "tools.run_plan987_acpx_live_evidence._assert_implementation_sha_clean",
        lambda *_a, **_k: None,
    )
    with pytest.raises(ValueError, match="fu5"):
        verify_report(report, require=("fu4a", "fu4b", "fu5"), implementation_sha="abc123")


def test_helper_source_does_not_implement_acp_protocol() -> None:
    source = HELPER_PATH.read_text(encoding="utf-8")
    forbidden = ("jsonrpc", "session/prompt", "session/new", "create_response")
    for token in forbidden:
        assert token not in source
    assert "subprocess.run" in source
    assert "acpx" in source
