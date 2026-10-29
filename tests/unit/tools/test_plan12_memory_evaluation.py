"""Plan 12.5 Task 1: case/trace contracts and the offline grader.

Every negative control sits next to a valid control that exercises the same path, so a
failure here proves the grader discriminates rather than rejecting everything.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from tools.plan12_memory.contracts import GoldenCase, ObservedTrace
from tools.plan12_memory.evaluate import grade_trace, main, validate_cases

CUTOFF = "2026-10-01T00:00:00+00:00"


def _case(**overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "schema": "plan12-memory-case/1",
        "case_id": "M01-a",
        "version": 1,
        "family": "M01",
        "split": "train",
        "kind": "lifecycle",
        "input_ref": "synthetic:m01/turns-1",
        "project_id": "proj-a",
        "snapshot": "snap-1",
        "cutoff": CUTOFF,
        "expected_action": "answer",
        "required_facts": ["fact-pref-tabs"],
        "required_evidence": [{"requirement_id": "R1", "any_of": ["ev-1", "ev-1b"]}],
        "prohibited_claims": ["claim-user-said-spaces"],
        "required_events": ["memory.committed", "memory.notice"],
        "prohibited_events": ["memory.trust_from_import"],
        "expected_cost": None,
        "verification": "deterministic trace comparison",
        "provenance": {"drafted_by": "claude", "verified_by": None, "source": "plan 12.5 Task 2 M01"},
    }
    case.update(overrides)
    return case


def _trace(**overrides: Any) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "schema": "plan12-memory-trace/1",
        "case_id": "M01-a",
        "case_version": 1,
        "source_id": "synthetic-control",
        "config_id": "cfg-a",
        "events": [
            {"seq": 0, "type": "turn.user"},
            {"seq": 1, "type": "memory.committed"},
            {"seq": 2, "type": "memory.notice"},
        ],
        "evidence": [
            {"evidence_id": "ev-1", "project_id": "proj-a", "revision": "snap-1",
             "observed_at": "2026-09-30T12:00:00+00:00", "supports": ["R1"]},
        ],
        "served_memory": [{"memory_id": "mem-7", "version": 2, "project_id": "proj-a"}],
        "answer": {
            "action": "answer",
            "claims": ["fact-pref-tabs"],
            "supported_by": [{"memory_id": "mem-7", "version": 2}],
            "citations": [{"memory_id": "mem-7", "version": 2}],
            "judge_status": "ok",
        },
        "attempts": [_attempt()],
        "reported_cost": {"known_usd": "0.002", "complete": True, "savings": None},
        "coverage_complete": True,
        "missing_coverage": [],
        "timing_ms": 840,
    }
    trace.update(overrides)
    return trace


def _attempt(**overrides: Any) -> dict[str, Any]:
    attempt: dict[str, Any] = {
        "attempt_id": "att-1",
        "gateway_request_id": "gw-1",
        "state": "settled",
        "input_tokens": 1000,
        "output_tokens": 200,
        "cache_tokens": 0,
        "reasoning_tokens": 0,
        "price_snapshot_id": "price-2026-10-01",
        "cost_usd": "0.002",
    }
    attempt.update(overrides)
    return attempt


def _grade(case: dict[str, Any] | None = None, trace: dict[str, Any] | None = None):
    return grade_trace(GoldenCase.model_validate(case or _case()), ObservedTrace.model_validate(trace or _trace()))


def _reasons(verdict) -> str:
    return " | ".join(verdict.reasons)


# --- Valid control -----------------------------------------------------------------


def test_valid_case_and_trace_pass_every_layer() -> None:
    verdict = _grade()
    assert verdict.execution_status == "PASS", verdict.reasons
    assert {layer: v.status for layer, v in verdict.layers.items()} == {
        "authority": "PASS", "retrieval": "PASS", "answer": "PASS", "cost": "PASS",
    }
    assert verdict.measurements.known_cost_usd == Decimal("0.002")
    assert verdict.measurements.timing_ms == 840
    assert verdict.measurements.retrieval_recall == Decimal(1)
    assert "ev-1" in verdict.evidence_ids


def test_absent_trace_is_unrun_not_pass() -> None:
    verdict = grade_trace(GoldenCase.model_validate(_case()), None)
    assert verdict.execution_status == "UNRUN"
    assert verdict.layers == {}


def test_honestly_incomplete_trace_is_inconclusive_not_pass() -> None:
    honest_cost = {"known_usd": "0.002", "complete": None, "savings": None}
    verdict = _grade(trace=_trace(missing_coverage=["events.tail"], coverage_complete=None, reported_cost=honest_cost))
    assert {v.status for v in verdict.layers.values()} == {"INCONCLUSIVE"}
    assert verdict.execution_status == "INCONCLUSIVE"
    assert "events.tail" in _reasons(verdict)


# --- Contract rejection (fail closed, no optimistic defaults) ----------------------


@pytest.mark.parametrize("bad_id", ["", " M01", "M01 a", "../x", "a" * 201])
def test_malformed_ids_are_rejected(bad_id: str) -> None:
    GoldenCase.model_validate(_case())  # positive path
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(case_id=bad_id))


@pytest.mark.parametrize("field", ["case_id", "project_id", "cutoff", "provenance", "expected_cost"])
def test_missing_case_fields_are_rejected(field: str) -> None:
    case = _case()
    del case[field]
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(case)


@pytest.mark.parametrize("field", ["coverage_complete", "missing_coverage", "source_id", "attempts", "reported_cost"])
def test_missing_trace_authority_and_coverage_fields_are_rejected(field: str) -> None:
    ObservedTrace.model_validate(_trace())
    trace = _trace()
    del trace[field]
    with pytest.raises(ValidationError):
        ObservedTrace.model_validate(trace)


def test_unsupported_schema_and_naive_cutoff_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(schema="plan12-memory-case/2"))
    with pytest.raises(ValidationError):
        ObservedTrace.model_validate(_trace(schema="plan12-memory-trace/0"))
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(cutoff="2026-10-01T00:00:00"))


def test_trace_for_another_case_or_version_is_rejected() -> None:
    case = GoldenCase.model_validate(_case())
    with pytest.raises(ValueError, match="case_id"):
        grade_trace(case, ObservedTrace.model_validate(_trace(case_id="M02-a")))
    with pytest.raises(ValueError, match="version"):
        grade_trace(case, ObservedTrace.model_validate(_trace(case_version=2)))


# --- Authority / lifecycle (hard failures) -----------------------------------------


def test_prohibited_event_fails_authority_even_with_a_perfect_answer() -> None:
    events = _trace()["events"] + [{"seq": 3, "type": "memory.trust_from_import"}]
    verdict = _grade(trace=_trace(events=events))
    assert verdict.layers["authority"].status == "FAIL"
    assert verdict.layers["answer"].status == "PASS"
    assert verdict.execution_status == "FAIL"


def test_required_events_must_occur_in_order() -> None:
    reordered = [{"seq": 0, "type": "memory.notice"}, {"seq": 1, "type": "memory.committed"}]
    assert _grade(trace=_trace(events=reordered)).layers["authority"].status == "FAIL"


def test_cross_project_served_memory_is_a_deterministic_failure() -> None:
    served = _trace()["served_memory"] + [{"memory_id": "mem-9", "version": 1, "project_id": "proj-b"}]
    verdict = _grade(trace=_trace(served_memory=served))
    assert verdict.layers["authority"].status == "FAIL"
    assert "proj-b" in _reasons(verdict)


# --- Retrieval ----------------------------------------------------------------------


def test_equivalent_listed_alternative_satisfies_requirement() -> None:
    evidence = [dict(_trace()["evidence"][0], evidence_id="ev-1b")]
    assert _grade(trace=_trace(evidence=evidence)).layers["retrieval"].status == "PASS"


def test_unlisted_equivalent_evidence_is_inconclusive_not_fail() -> None:
    evidence = [dict(_trace()["evidence"][0], evidence_id="ev-other")]
    verdict = _grade(trace=_trace(evidence=evidence))
    assert verdict.layers["retrieval"].status == "INCONCLUSIVE"
    assert "ev-other" in _reasons(verdict)


def test_missing_required_evidence_fails() -> None:
    assert _grade(trace=_trace(evidence=[])).layers["retrieval"].status == "FAIL"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"observed_at": "2026-10-02T00:00:00+00:00"}, "after the cutoff"),
        ({"project_id": "proj-b"}, "out of scope"),
        ({"revision": "snap-0"}, "stale"),
    ],
)
def test_future_wrong_scope_and_stale_evidence_fail(change: dict[str, str], reason: str) -> None:
    evidence = [dict(_trace()["evidence"][0], **change)]
    verdict = _grade(trace=_trace(evidence=evidence))
    assert verdict.layers["retrieval"].status == "FAIL"
    assert reason in _reasons(verdict)


# --- Answer and citations -----------------------------------------------------------


def test_prohibited_claim_fails_and_missing_fact_fails() -> None:
    answer = dict(_trace()["answer"], claims=["fact-pref-tabs", "claim-user-said-spaces"])
    assert _grade(trace=_trace(answer=answer)).layers["answer"].status == "FAIL"
    answer = dict(_trace()["answer"], claims=[])
    assert _grade(trace=_trace(answer=answer)).layers["answer"].status == "FAIL"


def test_wrong_action_fails_and_correct_abstention_passes() -> None:
    abstain = dict(_trace()["answer"], action="abstain", claims=[], supported_by=[], citations=[])
    assert _grade(trace=_trace(answer=abstain)).layers["answer"].status == "FAIL"
    case = _case(expected_action="abstain", required_facts=[], required_evidence=[])
    verdict = _grade(case=case, trace=_trace(answer=abstain, evidence=[]))
    assert verdict.layers["answer"].status == "PASS"
    assert verdict.layers["retrieval"].status == "PASS"


@pytest.mark.parametrize(
    ("citations", "reason"),
    [
        ([], "not cited"),
        ([{"memory_id": "mem-7", "version": 2}, {"memory_id": "mem-404", "version": 1}], "fabricated"),
        ([{"memory_id": "mem-7", "version": 1}], "fabricated"),
    ],
)
def test_missing_fabricated_and_mismatched_citations_fail(citations: list[dict[str, Any]], reason: str) -> None:
    answer = dict(_trace()["answer"], citations=citations)
    verdict = _grade(trace=_trace(answer=answer))
    assert verdict.layers["answer"].status == "FAIL"
    assert reason in _reasons(verdict)


def test_served_but_unused_memory_need_not_be_cited() -> None:
    served = _trace()["served_memory"] + [{"memory_id": "mem-8", "version": 1, "project_id": "proj-a"}]
    assert _grade(trace=_trace(served_memory=served)).layers["answer"].status == "PASS"


def test_judge_error_is_inconclusive_but_structural_failures_still_fail() -> None:
    answer = dict(_trace()["answer"], judge_status="error")
    assert _grade(trace=_trace(answer=answer)).layers["answer"].status == "INCONCLUSIVE"
    answer = dict(answer, citations=[])
    assert _grade(trace=_trace(answer=answer)).layers["answer"].status == "FAIL"


# --- Cost and accounting ------------------------------------------------------------


def test_replayed_receipt_is_counted_once() -> None:
    verdict = _grade(trace=_trace(attempts=[_attempt(), _attempt()]))
    assert verdict.layers["cost"].status == "PASS"
    assert verdict.measurements.known_cost_usd == Decimal("0.002")


def test_contradictory_duplicate_is_never_a_new_charge() -> None:
    attempts = [_attempt(), _attempt(cost_usd="0.009")]
    verdict = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0", "complete": None, "savings": None}))
    assert verdict.measurements.known_cost_usd == Decimal(0)
    assert verdict.measurements.cost_complete is False
    assert "conflict" in _reasons(verdict)
    assert verdict.layers["cost"].status == "PASS"  # honest report of the unknown
    verdict = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0.011", "complete": True, "savings": None}))
    assert verdict.layers["cost"].status == "FAIL"


def test_shared_gateway_request_id_across_attempts_is_a_conflict() -> None:
    attempts = [_attempt(), _attempt(attempt_id="att-2")]
    verdict = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0", "complete": None, "savings": None}))
    assert verdict.measurements.cost_complete is False
    assert "gw-1" in _reasons(verdict)


@pytest.mark.parametrize(
    ("attempt", "reason"),
    [
        (_attempt(attempt_id="att-2", gateway_request_id="gw-2", state="intent_only", cost_usd=None), "missing tail"),
        (_attempt(attempt_id="att-2", gateway_request_id=None), "unattributed"),
        (_attempt(attempt_id="att-2", gateway_request_id="gw-2", price_snapshot_id=None, cost_usd=None), "dated price"),
    ],
    ids=["missing-tail", "unattributed", "missing-price"],
)
def test_incomplete_accounting_stays_unknown(attempt: dict[str, Any], reason: str) -> None:
    attempts = [_attempt(), attempt]
    honest = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0.002", "complete": None, "savings": None}))
    assert honest.layers["cost"].status == "PASS"
    assert reason in _reasons(honest)
    assert honest.measurements.known_cost_usd == Decimal("0.002")
    assert honest.measurements.cost_complete is False
    overclaim = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0.002", "complete": True, "savings": None}))
    assert overclaim.layers["cost"].status == "FAIL"


def test_late_receipt_counts_but_breaks_completeness() -> None:
    attempts = [_attempt(), _attempt(attempt_id="att-2", gateway_request_id="gw-2", state="late")]
    verdict = _grade(trace=_trace(attempts=attempts, reported_cost={"known_usd": "0.004", "complete": False, "savings": None}))
    assert verdict.layers["cost"].status == "PASS"
    assert verdict.measurements.known_cost_usd == Decimal("0.004")
    assert verdict.measurements.cost_complete is False


def _savings(**overrides: Any) -> dict[str, Any]:
    savings: dict[str, Any] = {
        "label": "estimated",
        "basis": "same_tokens_repriced",
        "amount_usd": "0.010",
        "reference_price_snapshot_id": "price-2026-10-01",
        "counterfactual_tokens_inferred": False,
    }
    savings.update(overrides)
    return savings


def _cost_with(savings: dict[str, Any]) -> dict[str, Any]:
    return {"known_usd": "0.002", "complete": True, "savings": savings}


def test_negative_estimated_savings_stay_visible() -> None:
    verdict = _grade(trace=_trace(reported_cost=_cost_with(_savings(amount_usd="-0.004"))))
    assert verdict.layers["cost"].status == "PASS"
    assert verdict.measurements.savings_usd == Decimal("-0.004")


@pytest.mark.parametrize(
    ("savings", "reason"),
    [
        (_savings(label="measured"), "estimated"),
        (_savings(label="estimated", basis="matched_run"), "measured"),
        (_savings(reference_price_snapshot_id=None), "dated price"),
        (_savings(counterfactual_tokens_inferred=True), "counterfactual"),
    ],
)
def test_savings_label_price_and_counterfactual_rules(savings: dict[str, Any], reason: str) -> None:
    verdict = _grade(trace=_trace(reported_cost=_cost_with(savings)))
    assert verdict.layers["cost"].status == "FAIL"
    assert reason in _reasons(verdict)


def test_repricing_with_a_null_token_category_is_unavailable() -> None:
    attempts = [_attempt(reasoning_tokens=None)]
    assert _grade(trace=_trace(attempts=attempts)).layers["cost"].status == "PASS"  # null is allowed
    verdict = _grade(trace=_trace(attempts=attempts, reported_cost=_cost_with(_savings())))
    assert verdict.layers["cost"].status == "FAIL"
    assert "token category" in _reasons(verdict)


def test_accounting_gold_is_compared_with_the_report() -> None:
    case = _case(kind="accounting", family="A01", case_id="A01-a",
                 expected_cost={"known_usd": "0.002", "complete": True})
    trace = _trace(case_id="A01-a")
    assert _grade(case=case, trace=trace).layers["cost"].status == "PASS"
    case["expected_cost"] = {"known_usd": "0.003", "complete": True}
    assert _grade(case=case, trace=trace).layers["cost"].status == "FAIL"


# --- Fixture validation -------------------------------------------------------------


def _write_fixture(path: Path, cases: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps({"schema": "plan12-memory-fixtures/1", "cases": cases}), encoding="utf-8")
    return path


def test_validate_cases_counts_valid_fixtures(tmp_path: Path) -> None:
    other = _case(case_id="M02-a", family="M02", split="held_out")
    _write_fixture(tmp_path / "lifecycle.json", [_case(), other])
    report = validate_cases(tmp_path)
    assert report.errors == ()
    assert report.case_count == 2
    assert dict(report.split_counts) == {"held_out": 1, "train": 1}


def test_validate_cases_reports_every_defect(tmp_path: Path) -> None:
    split_family = _case(case_id="M01-b", split="held_out")
    duplicate = copy.deepcopy(_case())
    broken = _case(case_id="")
    _write_fixture(tmp_path / "lifecycle.json", [_case(), split_family, duplicate, broken])
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "wrong.json").write_text(json.dumps({"schema": "x", "cases": []}), encoding="utf-8")
    errors = " | ".join(validate_cases(tmp_path).errors)
    assert "duplicate case M01-a v1" in errors
    assert "family M01 spans splits" in errors
    assert "lifecycle.json case 4" in errors
    assert "bad.json" in errors
    assert "wrong.json" in errors


def test_validate_only_cli_exit_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_fixture(tmp_path / "ok.json", [_case()])
    assert main(["--validate-only", str(tmp_path)]) == 0
    assert "1 cases" in capsys.readouterr().out
    _write_fixture(tmp_path / "ok.json", [_case(case_id="")])
    assert main(["--validate-only", str(tmp_path)]) == 1
