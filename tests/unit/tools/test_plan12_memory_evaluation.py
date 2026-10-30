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


def _mem(key: str = "pref-indent", project_id: str = "proj-a", **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "project_id": project_id, "version": 1, "trust": "user-authored",
                            "status": "active", "off": False, "supersedes": None}
    if overrides.get("trust") == "absent":
        item |= {"version": None, "status": None}
    item.update(overrides)
    return item


def _ev(seq: int, kind: str, key: str | None = None, version: int | None = None, project_id: str = "proj-a") -> dict[str, Any]:
    return {"seq": seq, "type": kind, "memory_key": key, "project_id": project_id if key else None, "version": version}


def _route(attempt_id: str) -> dict[str, Any]:
    return {"attempt_id": attempt_id, "provider": "openrouter", "requested_model": "vendor/model-x", "resolved_provider": "vendor",
            "resolved_model": "vendor/model-x", "model_version": None, "cache_hit": False, "billing_units": 1200}


def _case(**overrides: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "schema": "plan12-memory-case/1",
        "case_id": "M01-a",
        "version": 1,
        "family": "M01",
        "split": "train",
        "kind": "lifecycle",
        "role": "control",
        "oracles": ["K1", "K6"],
        "inputs": [
            {"seq": 0, "actor": "user", "text": "From now on, use tabs for indentation.", "attempt": None},
            {"seq": 1, "actor": "user", "text": "How should I indent new files?", "attempt": None},
        ],
        "project_id": "proj-a",
        "snapshot": "snap-1",
        "cutoff": CUTOFF,
        "expected_action": "answer",
        "required_facts": ["fact-pref-tabs"],
        "required_evidence": [{"requirement_id": "R1", "any_of": ["ev-1", "ev-1b"]}],
        "prohibited_claims": ["claim-user-said-spaces"],
        "required_events": ["memory.committed", "memory.notice"],
        "prohibited_events": ["memory.trust_from_import"],
        "expected_memory": [_mem()],
        "expected_rank": [],
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
            _ev(0, "turn.user"),
            _ev(1, "memory.committed"),
            _ev(2, "memory.notice"),
        ],
        "evidence": [
            {"evidence_id": "ev-1", "project_id": "proj-a", "revision": "snap-1",
             "observed_at": "2026-09-30T12:00:00+00:00", "supports": ["R1"]},
        ],
        "served_memory": [{"memory_id": "mem-7", "version": 2, "project_id": "proj-a"}],
        "memory_state": [_mem(), _mem("mem-7", version=2)],
        "answer": {
            "action": "answer",
            "claims": ["fact-pref-tabs"],
            "supported_by": [{"memory_id": "mem-7", "version": 2}],
            "support_extracted": True,
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
    if "provenance" not in overrides:  # one route record per distinct receipt identity
        trace["provenance"] = [_route(i) for i in dict.fromkeys(a["attempt_id"] for a in trace["attempts"])]
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
    events = _trace()["events"] + [_ev(3, "memory.trust_from_import")]
    verdict = _grade(trace=_trace(events=events))
    assert verdict.layers["authority"].status == "FAIL"
    assert verdict.layers["answer"].status == "PASS"
    assert verdict.execution_status == "FAIL"


def test_required_events_must_occur_in_order() -> None:
    reordered = [_ev(0, "memory.notice"), _ev(1, "memory.committed")]
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
                 expected_cost={"known_usd": "0.002", "complete": True, "savings": None})
    trace = _trace(case_id="A01-a")
    assert _grade(case=case, trace=trace).layers["cost"].status == "PASS"
    case["expected_cost"] = {"known_usd": "0.003", "complete": True, "savings": None}
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


# --- Task 2 contract extensions -----------------------------------------------------


def test_expected_memory_state_is_graded_including_absence() -> None:
    assert _grade().layers["authority"].status == "PASS"
    demoted = [_mem(off=True), _mem("mem-7", version=2)]
    verdict = _grade(trace=_trace(memory_state=demoted))
    assert verdict.layers["authority"].status == "FAIL"
    assert "expected user-authored/active" in _reasons(verdict)
    absent = [_mem(trust="absent")]
    only_served = [_mem("mem-7", version=2)]
    assert _grade(case=_case(expected_memory=absent), trace=_trace(memory_state=only_served)).layers["authority"].status == "PASS"
    assert _grade(case=_case(expected_memory=absent)).layers["authority"].status == "FAIL"


@pytest.mark.parametrize(
    "change",
    [
        {"inputs": [{"seq": 0, "actor": "user", "text": "x", "attempt": _attempt()}]},
        {"inputs": [{"seq": 0, "actor": "user", "text": None, "attempt": None}]},
        {"inputs": [{"seq": 1, "actor": "user", "text": "a", "attempt": None},
                    {"seq": 1, "actor": "user", "text": "b", "attempt": None}]},
        {"inputs": []},
        {"oracles": []},
        {"oracles": ["K7"]},
        {"expected_memory": [_mem("k", "p")] * 2},
        {"expected_memory": [_mem("k", "p", trust="absent", status="active")]},
        {"expected_memory": [_mem("k", "p", trust="absent", version=1, status=None)]},
        {"expected_memory": [_mem("k", "p", trust="off")]},
        {"expected_rank": ["k", "k"]},
        {"family": "a..b"},
        {"prohibited_claims": ["fact-pref-tabs"]},
        {"prohibited_events": ["memory.committed"]},
        {"expected_action": "abstain"},
        {"required_facts": [], "required_evidence": [], "prohibited_claims": [], "required_events": [],
         "prohibited_events": [], "expected_memory": []},
    ],
)
def test_case_extension_constraints(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        GoldenCase.model_validate(_case(**change))


def test_repository_path_ids_are_allowed() -> None:
    requirement = [{"requirement_id": "R1", "any_of": ["path:src/optimus/acp/spec.py", "symbol:src/optimus/acp/spec.py::Store.remove"]}]
    GoldenCase.model_validate(_case(required_evidence=requirement))


def test_trace_memory_state_must_be_unique() -> None:
    state = _trace()["memory_state"] * 2
    with pytest.raises(ValidationError):
        ObservedTrace.model_validate(_trace(memory_state=state))


def test_accounting_gold_includes_the_savings_figure() -> None:
    case = _case(kind="accounting", family="A01", case_id="A01-a",
                 expected_cost={"known_usd": "0.002", "complete": True, "savings": {
                     "label": "estimated", "basis": "same_tokens_repriced", "amount_usd": "-0.004",
                     "reference_price_snapshot_id": "price-2026-10-01"}})
    with_savings = _trace(case_id="A01-a", reported_cost=_cost_with(_savings(amount_usd="-0.004")))
    assert _grade(case=case, trace=with_savings).layers["cost"].status == "PASS"
    verdict = _grade(case=case, trace=_trace(case_id="A01-a"))
    assert verdict.layers["cost"].status == "FAIL"
    assert "gold expects ('estimated', 'same_tokens_repriced', Decimal('-0.004')" in _reasons(verdict)
    measured = _trace(case_id="A01-a", reported_cost=_cost_with(_savings(label="measured", basis="matched_run", amount_usd="-0.004")))
    assert _grade(case=case, trace=measured).layers["cost"].status == "FAIL"  # no matched run behind it


def _manifest(**overrides: Any) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema": "plan12-memory-splits/1",
        "version": 1,
        "families": {"train": ["M01", "L01"], "development": ["L02"], "held_out": ["M02"]},
        "expected_family_counts": {"lifecycle": 2, "localization": 2},
        "chronological_kinds": ["localization"],
    }
    manifest.update(overrides)
    return manifest


def _seed(tmp_path: Path, manifest: dict[str, Any], *, l02_cutoff: str = "2026-10-05T00:00:00+00:00") -> list[str]:
    cases = [
        _case(),
        _case(case_id="M02-a", family="M02", split="held_out"),
        _case(case_id="L01-a", family="L01", kind="localization", role="probe", cutoff="2026-10-02T00:00:00+00:00"),
        _case(case_id="L02-a", family="L02", kind="localization", role="probe", split="development", cutoff=l02_cutoff),
    ]
    _write_fixture(tmp_path / "cases.json", cases)
    (tmp_path / "splits.json").write_text(json.dumps(manifest), encoding="utf-8")
    return list(validate_cases(tmp_path).errors)


def test_split_manifest_accepts_a_matching_seed(tmp_path: Path) -> None:
    assert _seed(tmp_path, _manifest()) == []
    assert dict(validate_cases(tmp_path).family_counts) == {"lifecycle": 2, "localization": 2}


@pytest.mark.parametrize(
    ("manifest", "reason"),
    [
        (_manifest(families={"train": ["M01", "L01"], "development": ["L02"], "held_out": []}), "family M02 is not in the split manifest"),
        (_manifest(families={"train": ["M01", "L01", "M02"], "development": ["L02"], "held_out": []}), "manifest says train"),
        (_manifest(families={"train": ["M01", "L01"], "development": ["L02"], "held_out": ["M02", "M03"]}), "manifest family M03 has no cases"),
        (_manifest(expected_family_counts={"lifecycle": 24, "localization": 2}), "manifest expects 24"),
    ],
)
def test_split_manifest_mismatches_are_reported(tmp_path: Path, manifest: dict[str, Any], reason: str) -> None:
    assert reason in " | ".join(_seed(tmp_path, manifest))


def test_chronological_split_rejects_a_later_train_cutoff(tmp_path: Path) -> None:
    errors = _seed(tmp_path, _manifest(), l02_cutoff="2026-10-01T00:00:00+00:00")
    assert "localization: a train cutoff is not before every development cutoff" in errors


def test_lifecycle_family_without_a_control_is_reported(tmp_path: Path) -> None:
    _write_fixture(tmp_path / "cases.json", [_case(role="probe")])
    assert "lifecycle family M01 has no control case" in validate_cases(tmp_path).errors


SEED = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "plan12_memory"
TASK0_MANIFEST = Path(__file__).resolve().parents[3] / "reports" / "plan12-memory-evaluation" / "manifest.json"


def test_seed_set_validates_with_its_cardinalities() -> None:
    report = validate_cases(SEED)
    assert report.errors == ()
    assert dict(report.family_counts) == {"accounting": 8, "lifecycle": 24, "localization": 12}
    assert main(["--validate-only", str(SEED)]) == 0


def test_seed_split_matches_the_task0_manifest() -> None:
    task0 = json.loads(TASK0_MANIFEST.read_text(encoding="utf-8"))["split"]
    expected = {split: {family for group in groups for family in task0["lifecycle_groups"][next(
        name for name in task0["lifecycle_groups"] if name.split()[0] == group)]}
        for split, groups in task0["lifecycle_assignment"].items()}
    seed = json.loads((SEED / "splits.json").read_text(encoding="utf-8"))["families"]
    assert {split: {f for f in families if f.startswith("M")} for split, families in seed.items()} == expected
    assert not {f for f in seed["held_out"] if f.startswith("A")}  # accounting is never held out


def test_every_seed_event_is_in_the_reviewed_vocabulary() -> None:
    review = json.loads((TASK0_MANIFEST.parent / "case-review.json").read_text(encoding="utf-8"))
    events = {
        event.partition(":")[0]  # a keyed event ID is type:key
        for name in ("lifecycle", "localization", "accounting")
        for case in json.loads((SEED / f"{name}.json").read_text(encoding="utf-8"))["cases"]
        for event in case["required_events"] + case["prohibited_events"]
    }
    vocabulary = {name for name in review["event_vocabulary"] if not name.endswith("_pin")}  # pins are scan pragmas
    assert events <= vocabulary, sorted(events - vocabulary)


def test_localization_gold_needs_a_symbol_wherever_one_changed() -> None:
    cases = json.loads((SEED / "localization.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        for requirement in case["required_evidence"]:
            ids = requirement["any_of"]
            assert all(i.startswith("symbol:") for i in ids) or (len(ids) == 1 and ids[0].startswith("path:")), case["case_id"]


# --- Checkpoint 1 corrections (Fable F-03, F-04) ------------------------------------


def test_support_beyond_the_predeclared_k_does_not_count() -> None:
    filler = [{"evidence_id": f"ev-x{n}", "project_id": "proj-a", "revision": "snap-1",
               "observed_at": "2026-09-30T12:00:00+00:00", "supports": []} for n in range(5)]
    late = {"evidence_id": "ev-1", "project_id": "proj-a", "revision": "snap-1",
            "observed_at": "2026-09-30T12:00:00+00:00", "supports": ["R1"]}

    verdict = _grade(trace=_trace(evidence=[*filler, late]))

    assert verdict.layers["retrieval"].status == "FAIL"
    assert "requirement R1 has no supporting evidence in the first 5" in _reasons(verdict)
    assert verdict.measurements is not None and verdict.measurements.retrieval_precision == 0


def test_served_memory_without_extraction_is_undecided_not_pass() -> None:
    unextracted = {**_trace()["answer"], "supported_by": [], "citations": [], "support_extracted": False}
    extracted_none = {**unextracted, "support_extracted": True}

    verdict = _grade(trace=_trace(answer=unextracted))
    made_prohibited = _grade(trace=_trace(answer={**unextracted, "claims": ["fact-pref-tabs", "claim-user-said-spaces"]}))

    assert verdict.layers["answer"].status == "INCONCLUSIVE"
    assert "no extractor attributed the answer's support" in _reasons(verdict)
    assert made_prohibited.layers["answer"].status == "FAIL"  # the claim checks still run
    assert _grade(trace=_trace(answer=extracted_none)).layers["answer"].status == "PASS"  # extracted: nothing used memory


# --- Checkpoint 1 round 2 (Codex C-01 to C-06, C-12, C-13) ---------------------------


def _localization_case(**overrides: Any) -> dict[str, Any]:
    return _case(case_id="L01-a", family="L01", kind="localization", role="probe", oracles=["K2"], required_facts=[],
                 prohibited_claims=[], required_events=[], prohibited_events=[], expected_memory=[],
                 required_evidence=[{"requirement_id": "R1", "any_of": ["symbol:a.py::f"]}], **overrides)


def _localization_trace(evidence_ids: list[str], claims: list[str]) -> dict[str, Any]:
    evidence = [{"evidence_id": i, "project_id": "proj-a", "revision": "snap-1", "observed_at": "2026-09-30T12:00:00+00:00",
                 "supports": ["R1"]} for i in evidence_ids]
    answer = {"action": "answer", "claims": claims, "supported_by": [], "support_extracted": True, "citations": [], "judge_status": "ok"}
    return _trace(case_id="L01-a", evidence=evidence, served_memory=[], memory_state=[], answer=answer)


@pytest.mark.parametrize(
    ("evidence_ids", "claims", "status", "reason"),
    [
        (["symbol:a.py::f"], ["locus:symbol:a.py::f"], "PASS", ""),
        (["symbol:a.py::f"], [], "FAIL", "names no locus for requirement R1"),
        (["symbol:a.py::g"], ["locus:symbol:a.py::f"], "FAIL", "not supported by the retrieved evidence"),
        (["symbol:a.py::g"], ["locus:symbol:a.py::g"], "INCONCLUSIVE", "unlisted evidence"),
    ],
    ids=["supported-locus", "no-locus", "unretrieved-locus", "unlisted-locus"],
)
def test_localization_answer_needs_a_retrieved_locus(evidence_ids: list[str], claims: list[str], status: str, reason: str) -> None:
    verdict = _grade(_localization_case(), _localization_trace(evidence_ids, claims))

    assert verdict.layers["answer"].status == status
    assert reason in _reasons(verdict)


@pytest.mark.parametrize(
    ("state", "served_version"),
    [(_mem("mem-7", version=2, off=True), 2), (_mem("mem-7", version=2, status="withdrawn"), 2),
     (_mem("mem-7", version=2, status="superseded"), 2), (_mem("mem-7", version=2), 3)],
    ids=["off", "withdrawn", "superseded", "no-state-at-version"],
)
def test_serving_an_ineligible_item_fails_even_if_unused(state: dict[str, Any], served_version: int) -> None:
    served = [{"memory_id": "mem-7", "version": served_version, "project_id": "proj-a"}]
    answer = {**_trace()["answer"], "supported_by": [], "citations": []}

    verdict = _grade(trace=_trace(memory_state=[_mem(), state], served_memory=served, answer=answer))

    assert verdict.layers["authority"].status == "FAIL"
    assert "served memory mem-7" in _reasons(verdict)


def test_notice_needs_an_earlier_commit_of_the_same_version_in_the_same_project() -> None:
    case = _case(required_events=["memory.committed", "memory.notice.remembered"])
    good = [_ev(0, "memory.committed", "pref-indent", 1), _ev(1, "memory.notice.remembered", "pref-indent", 1)]
    other_project = [_ev(0, "memory.committed", "pref-indent", 1, project_id="proj-b"), good[1]]
    wrong_version = [_ev(0, "memory.committed", "pref-indent", 2), _ev(1, "memory.notice.remembered", "pref-indent", 2)]

    assert _grade(case, _trace(events=good)).layers["authority"].status == "PASS"
    for events, reason in ((other_project, "no earlier durable commit"), (wrong_version, "no notice names pref-indent v1")):
        verdict = _grade(case, _trace(events=events))
        assert verdict.layers["authority"].status == "FAIL"
        assert reason in _reasons(verdict)


def test_case_receipts_must_reach_the_trace_unaltered() -> None:
    inputs = [{"seq": 0, "actor": "gateway", "text": None, "attempt": _attempt()},
              {"seq": 1, "actor": "user", "text": "What did this cost?", "attempt": None}]
    case = _case(inputs=inputs)
    nothing = {"known_usd": "0", "complete": None, "savings": None}

    assert _grade(case, _trace()).layers["cost"].status == "PASS"
    missing = _grade(case, _trace(attempts=[], coverage_complete=None, reported_cost=nothing))
    altered = _grade(case, _trace(attempts=[_attempt(cost_usd="0.003")], reported_cost={**nothing, "known_usd": "0.003"}))
    assert "receipt att-1 from the case inputs is missing" in _reasons(missing)
    assert "receipt att-1 from the case inputs is altered" in _reasons(altered)
    assert {missing.layers["cost"].status, altered.layers["cost"].status} == {"FAIL"}


def test_expected_rank_is_checked_against_the_served_order() -> None:
    case = _case(expected_rank=["mem-7", "mem-8"])
    state = [_mem(), _mem("mem-7", version=2), _mem("mem-8")]
    first = {"memory_id": "mem-7", "version": 2, "project_id": "proj-a"}
    second = {"memory_id": "mem-8", "version": 1, "project_id": "proj-a"}

    assert _grade(case, _trace(memory_state=state, served_memory=[first, second])).layers["retrieval"].status == "PASS"
    reversed_order = _grade(case, _trace(memory_state=state, served_memory=[second, first]))
    unserved = _grade(case, _trace(memory_state=state, served_memory=[first]))
    assert "breaks the required rank" in _reasons(reversed_order)
    assert "were not served" in _reasons(unserved)


def test_keyed_event_ids_match_only_that_item() -> None:
    case = _case(required_events=["memory.committed:pref-indent"], prohibited_events=["memory.served:api-freeze"])
    other_item = [_ev(0, "memory.committed", "pref-indent", 1), _ev(1, "memory.served", "pref-ruff", 1)]
    named_item = [_ev(0, "memory.committed", "pref-indent", 1), _ev(1, "memory.served", "api-freeze", 1)]
    wrong_commit = [_ev(0, "memory.committed", "pref-ruff", 1)]

    assert _grade(case, _trace(events=other_item)).layers["authority"].status == "PASS"
    assert "prohibited event memory.served:api-freeze" in _reasons(_grade(case, _trace(events=named_item)))
    assert "required events" in _reasons(_grade(case, _trace(events=wrong_commit)))


def test_old_root_destruction_needs_its_prerequisites_and_happens_once() -> None:
    case = _case(required_events=["rotation.old_root_destroyed"])
    ready = [_ev(0, "generation.usable_verified"), _ev(1, "rotation.acknowledged")]
    once = [*ready, _ev(2, "rotation.old_root_destroyed", version=2)]
    early = [_ev(0, "rotation.old_root_destroyed", version=2), _ev(1, "generation.usable_verified"), _ev(2, "rotation.acknowledged")]
    twice = [*once, _ev(3, "rotation.old_root_destroyed", version=2)]

    assert _grade(case, _trace(events=once)).layers["authority"].status == "PASS"
    assert "before verification and acknowledgement" in _reasons(_grade(case, _trace(events=early)))
    assert "generation 2 was destroyed 2 times" in _reasons(_grade(case, _trace(events=twice)))


@pytest.mark.parametrize("routes", [[], ["att-1", "att-1"], ["att-1", "att-9"]], ids=["missing", "duplicate", "extra"])
def test_trace_needs_exactly_one_route_record_per_receipt(routes: list[str]) -> None:
    with pytest.raises(ValidationError, match="provenance"):
        ObservedTrace.model_validate(_trace(provenance=[_route(i) for i in routes]))


def test_superseded_history_is_part_of_the_expected_state() -> None:
    history = [_mem(status="superseded"), _mem(version=2, supersedes=1)]
    case = _case(expected_memory=history)
    served = [{"memory_id": "pref-indent", "version": 2, "project_id": "proj-a"}]
    answer = {**_trace()["answer"], "supported_by": [{"memory_id": "pref-indent", "version": 2}],
              "citations": [{"memory_id": "pref-indent", "version": 2}]}

    kept = _grade(case, _trace(memory_state=history, served_memory=served, answer=answer))
    overwritten = _grade(case, _trace(memory_state=history[1:], served_memory=served, answer=answer))
    unlinked = _grade(case, _trace(memory_state=[history[0], _mem(version=2)], served_memory=served, answer=answer))
    assert kept.layers["authority"].status == "PASS", kept.reasons
    assert "memory pref-indent v1 in proj-a is absent" in _reasons(overwritten)
    assert "expected user-authored/active/supersedes v1" in _reasons(unlinked)
