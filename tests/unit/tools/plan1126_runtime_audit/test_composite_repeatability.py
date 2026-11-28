"""Tests for evidence-bound, per-observation repeatability attribution."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit.repeatability import RepeatabilityStatus, classify_repeatability

HASH = "a" * 64
HARNESS_NODE = "tests/unit/test_example.py::test_harness"
IDENTITY = {
    "measurement_generation": "fixture",
    "artifact_digest": HASH,
    "provenance_fingerprint": HASH,
    "harness_fingerprint_before": HASH,
    "harness_fingerprint_after": HASH,
    "original_command_sha256": HASH,
    "command": "<interpreter> -m pytest",
    "platform": "synthetic",
    "python": "3.14",
}
REPORTS = Path(__file__).resolve().parents[4] / "reports" / "repeatability-attribution"


def _encode(document: object) -> bytes:
    return json.dumps(document).encode("utf-8")


def _row(index: int, status: str, *, cohort: str = "narrow", claim: str = "product") -> dict:
    is_timeout = status == "TIMEOUT"
    claim_fields = {
        "product": ("PRODUCT" if status == "FAIL" else "NONE", "PRODUCT_ASSERTION", "assertions"),
        "harness": ("HARNESS", "DECLARED_HARNESS_NODE_MATCH", "harness"),
        "unknown": ("UNRESOLVED", "UNATTRIBUTED_OUTCOME", None),
        "none": ("NONE", "NONE", None),
    }
    subject, kind, ref = claim_fields[claim]
    return {
        **IDENTITY,
        "observation_id": f"{cohort}-{index}",
        "cohort": cohort,
        "repeat_index": index,
        "checkpoint_revision": index,
        "duration_ms": 12.5,
        "outcome": {
            "status": status,
            "returncode": None if is_timeout else int(status != "PASS"),
            "counts": {},
            "timeout_subject": "HARNESS" if claim == "harness" else ("UNRESOLVED" if is_timeout else None),
            "last_test_nodeid": HARNESS_NODE if claim == "harness" else None,
            "stdout_sha256": HASH if is_timeout else None,
            "stderr_sha256": HASH if is_timeout else None,
            "timeout_output_truncated": False if is_timeout else None,
        },
        "provenance_refs": ["checkpoint"],
        "omitted_fields": [],
        "limitations": [],
        "attribution": {"subject": subject, "evidence_kind": kind, "evidence_ref": ref, "rationale": "synthetic case"},
        "product_evidence": [
            {"assertion_id": "shutdown", "comparison_key": "shutdown-v1", "result": status, "evidence_ref": "assertions"}
        ] if claim == "product" else [],
    }


def documents(rows: list[dict], expected: list[dict] | None = None) -> tuple[bytes, bytes]:
    declared = rows if expected is None else expected
    cohorts: dict[str, dict] = {}
    for row in declared:
        name = row["cohort"]
        cohort = cohorts.setdefault(name, {
            "cohort": name,
            "expected_count": 0,
            "expected_observations": {},
            "identity": {key: row[key] for key in IDENTITY},
            "assertions": {"shutdown": "shutdown-v1"},
        })
        cohort["expected_count"] += 1
        cohort["expected_observations"][row["observation_id"]] = {
            "repeat_index": row["repeat_index"],
            "checkpoint_revision": row["checkpoint_revision"],
        }
    payload = _encode({"schema": "optimus-repeatability-input-v1", "observations": rows})
    manifest = _encode({
        "schema": "optimus-repeatability-manifest-v1",
        "input_sha256": hashlib.sha256(payload).hexdigest(),
        "checkpoint_sha256": HASH,
        "selection": "fixture",
        "transformation": "synthetic",
        "witness": "synthetic",
        "cohorts": list(cohorts.values()),
        "harness_node_allowlist": [HARNESS_NODE],
        "evidence_refs": {
            "harness": {"kind": "DECLARED_HARNESS_NODE_MATCH", "path": "fixtures/harness.md", "sha256": HASH},
            "assertions": {"kind": "PRODUCT_ASSERTION", "path": "fixtures/assertions.md", "sha256": HASH},
            "checkpoint": {"kind": "PROVENANCE", "path": "fixtures/checkpoint.json", "sha256": HASH},
        },
        "residual_dispositions": [],
    })
    return payload, manifest


def _api():
    return importlib.import_module("tools.plan1126_runtime_audit.composite_repeatability")


def _classify(rows: list[dict], expected: list[dict] | None = None):
    parsed = _api().parse_input(*documents(rows, expected))
    return _api().classify_composite(parsed.observations, parsed.specs)


def test_mixed_product_flake_and_harness_timeout_are_both_visible() -> None:
    outcome = _classify([_row(1, "PASS"), _row(2, "FAIL"), _row(3, "TIMEOUT", claim="harness")])
    assert outcome.input_validity == "VALID"
    assert outcome.product_variability_observed
    assert outcome.harness_instability_observed
    assert outcome.product_repeatability == "FLAKY"
    assert [(row.observed_outcome, row.subject) for row in outcome.rows] == [
        ("PASS", "NONE"), ("FAIL", "PRODUCT"), ("TIMEOUT", "HARNESS")
    ]


def test_unresolved_timeout_does_not_become_product_failure_or_stability() -> None:
    result = _classify([_row(1, "PASS"), _row(2, "TIMEOUT", claim="unknown")])
    assert result.input_validity == "VALID"
    assert result.rows[1].subject == "UNRESOLVED"
    assert result.product_repeatability == "INDETERMINATE"
    assert not result.product_variability_observed
    assert not result.harness_instability_observed


def test_metadata_variation_does_not_create_product_flake() -> None:
    first = _row(1, "FAIL")
    second = _row(2, "FAIL")
    second["duration_ms"] = 202.0
    second["outcome"]["stdout_sha256"] = "4" * 64
    second["outcome"]["counts"] = {"failed": 20}
    outcome = _classify([first, second])
    assert outcome.input_validity == "VALID"
    assert not outcome.product_variability_observed
    assert outcome.product_repeatability == "STABLE_OBSERVED"


@pytest.mark.parametrize("damage", ["missing", "extra", "duplicate", "index", "generation", "provenance", "harness", "command"])
def test_invalid_cohort_retains_rows_and_diagnostics(damage: str) -> None:
    declared = [_row(1, "PASS"), _row(2, "FAIL"), _row(3, "TIMEOUT", claim="harness")]
    rows = [json.loads(json.dumps(row)) for row in declared]
    if damage == "missing":
        rows.pop()
    elif damage == "extra":
        rows.append(_row(4, "FAIL"))
    elif damage == "duplicate":
        rows.append(rows[2])
    else:
        field, value = {
            "index": ("repeat_index", 8),
            "generation": ("measurement_generation", "other"),
            "provenance": ("provenance_fingerprint", "b" * 64),
            "harness": ("harness_fingerprint_after", "c" * 64),
            "command": ("command", "setup"),
        }[damage]
        rows[2][field] = value
    result = _classify(rows, declared)
    assert result.input_validity == "INVALID"
    assert result.product_variability_observed
    assert result.product_repeatability == "INDETERMINATE"
    assert result.harness_instability_observed is (damage == "extra")
    assert len(result.rows) == len(rows)
    assert result.diagnostics


@pytest.mark.parametrize("document", [
    b'{"schema": "a", "schema": "b"}',
    b'{"duration": NaN}',
    b'{"duration": 1e900}',
    b'{"x":"\xff"}',
])
def test_strict_input_rejects_duplicate_keys_bad_types_and_nonfinite_numbers(document: bytes) -> None:
    _, manifest = documents([_row(1, "PASS")])
    with pytest.raises(_api().InputParseError):
        _api().parse_input(document, manifest)


@pytest.mark.parametrize(("field", "value"), [
    ("checkpoint_revision", True),
    ("repeat_index", 0),
    ("duration_ms", -1),
    ("artifact_digest", "not-a-digest"),
    ("outcome", {"status": "PASS", "returncode": 1, "counts": {"passed": -1}}),
])
def test_invalid_fields_withhold_acceptance(field: str, value: object) -> None:
    expected = _row(1, "PASS")
    result = _classify([{**expected, field: value}], [expected])
    assert result.input_validity == "INVALID"
    assert result.rows[0].observation.raw[field] == value


def test_unbound_harness_and_product_claims_do_not_create_facts() -> None:
    failure = _row(2, "FAIL")
    failure["product_evidence"][0]["evidence_ref"] = "not-in-manifest"
    harness = _row(3, "TIMEOUT", claim="harness")
    harness["outcome"]["last_test_nodeid"] = "test_unlisted"
    result = _classify([_row(1, "PASS"), failure, harness])
    assert result.input_validity == "INVALID"
    assert not result.harness_instability_observed
    assert not result.product_variability_observed
    assert [row.subject for row in result.rows[1:]] == ["UNRESOLVED", "UNRESOLVED"]


def test_distinct_cohort_harnesses_are_valid_and_legacy_api_is_unchanged() -> None:
    first = _row(1, "PASS")
    second = _row(1, "FAIL", cohort="group")
    second["harness_fingerprint_before"] = second["harness_fingerprint_after"] = "b" * 64
    result = _classify([first, second])
    assert result.input_validity == "VALID"
    assert not result.product_variability_observed
    assert result.product_repeatability == "INDETERMINATE"
    legacy = classify_repeatability(
        outcomes=("PASS", "FAIL"), harness_fingerprints=("h", "h"),
        provenance_fingerprints=("p", "p"), harness_behavior_unstable=(False, True),
    )
    assert legacy.status is RepeatabilityStatus.HARNESS_UNSTABLE


@pytest.mark.parametrize("outcome", [
    {"status": "NOT_A_STATUS", "returncode": 1, "counts": {}},
    {"status": "FAIL", "returncode": 1, "counts": {"failed": 0}},
])
def test_invalid_outcome_enum_or_contradictory_failure_count_withholds_acceptance(outcome: dict) -> None:
    row = _row(1, "FAIL")
    row["outcome"] = outcome
    result = _classify([row])
    assert result.input_validity == "INVALID"
    assert result.rows[0].observation.raw["outcome"] == outcome


def test_sealed_shutdown_selection_preserves_all_35_rows_and_10_4_split() -> None:
    parsed = _api().parse_input(
        (REPORTS / "historical-input.json").read_bytes(),
        (REPORTS / "historical-manifest.json").read_bytes(),
    )
    assert not parsed.diagnostics
    result = _api().classify_composite(parsed.observations, parsed.specs)
    assert result.input_validity == "VALID"
    assert result.product_repeatability == "INDETERMINATE"
    assert result.harness_instability_observed
    assert not result.product_variability_observed
    for name, scenario, size, passed, harness, unknown in [
        ("narrow", "task6_shutdown", 10, 6, 2, {3, 6}),
        ("group", "task6_shutdown_group", 25, 15, 8, {18, 24}),
    ]:
        rows = [row for row in result.rows if row.observation.raw["cohort"] == name]
        assert {row.observation.raw["observation_id"] for row in rows} == {
            f"task11-{name}-{scenario}-c18-latest-complete-v1-repeat-{i:02}" for i in range(1, size + 1)
        }
        assert sum(row.observed_outcome == "PASS" for row in rows) == passed
        assert sum(row.subject == "HARNESS" for row in rows) == harness
        assert {row.observation.raw["repeat_index"] for row in rows if row.subject == "UNRESOLVED"} == unknown
