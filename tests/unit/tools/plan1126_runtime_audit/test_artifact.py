"""Contract tests for the Plan 11.26 canonical audit artifact."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.model import (
    AuditArtifact,
    BaselineScope,
    Classification,
    EvidenceReference,
    Finding,
    GateStatus,
    LiveStatus,
    PrerequisiteStatus,
)

_SCHEMA_PATH = Path(__file__).parents[3] / "fixtures" / "plan1126_runtime_audit" / "audit-artifact.schema.json"
_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"


def _finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "finding_id": "F-FOUNDATION-001",
        "subject": "fixture discovery site",
        "classification": Classification.CANONICAL,
        "baseline_scope": BaselineScope.MERGED,
        "symbols": ("fixture.py:fixture_symbol",),
        "evidence": (
            EvidenceReference(
                evidence_id="E-FOUNDATION-001",
                baseline_scope=BaselineScope.MERGED,
                digest="a" * 64,
            ),
        ),
        "owner": "Plan 11.26",
        "ruling": "Fixture-only site is classified for the G1 foundation gate.",
    }
    values.update(overrides)
    return Finding(**values)


def _artifact(**overrides: object) -> AuditArtifact:
    values: dict[str, object] = {
        "schema_version": "plan-11-26-runtime-audit-v1",
        "merged_commit": _MERGED,
        "overlay_commit": _OVERLAY,
        "binding_commit": None,
        "baseline_reconciliation_status": "UNRESOLVED",
        "running_artifact_provenance": None,
        "static_audit_status": LiveStatus.UNRUN,
        "runtime_characterization_status": LiveStatus.UNRUN,
        "live_redis_status": LiveStatus.UNRUN,
        "acpx_status": LiveStatus.UNRUN,
        "additional_client_status": LiveStatus.UNRUN,
        "zed_status": LiveStatus.UNRUN,
        "live_interoperability_status": LiveStatus.UNRUN,
        "findings": (_finding(),),
        "discovered_multipliers": {"cancellation_points": 0, "queues": 0, "sinks": 0, "close_paths": 0},
        "computed_run_cost": {
            "cancellation_concurrency_levels": [2, 4, 8],
            "cancellation_schedules": 0,
            "cancellation_control_schedules": 0,
            "queue_admissions": 0,
            "sink_failure_runs": 0,
            "idempotent_close_invocations": 0,
            "scenario_p50_ms": {},
            "scenario_p95_ms": {},
        },
        "gate_status": GateStatus.PASS,
    }
    values.update(overrides)
    return AuditArtifact(**values)


def _provenance() -> dict[str, object]:
    return {
        "binding_commit": _MERGED,
        "executable_path": "C:/installed/optimus-agent.exe",
        "executable_sha256": "1" * 64,
        "package_name": "optimus-cost-agent",
        "package_version": "0.1.0",
        "package_metadata_sha256": "2" * 64,
        "build_manifest_sha256": "3" * 64,
        "embedded_commit": _MERGED,
        "embedded_commit_sha256": "4" * 64,
        "launcher_sha256": "5" * 64,
        "client_provenance": {
            "name": "zed", "version": "1.17.2", "path": "C:/installed/Zed.exe",
            "sha256": "6" * 64, "metadata_sha256": "7" * 64,
        },
        "environment_fingerprint": "8" * 64,
    }


def test_audit_artifact_requires_baseline_scope_and_classification() -> None:
    payload = _artifact().to_dict()
    assert payload["findings"][0]["baseline_scope"] == "merged"
    assert payload["findings"][0]["classification"] == "CANONICAL"
    assert payload["unclassified_finding_count"] == 0
    assert payload["finding_counts_by_classification"]["CANONICAL"] == 1


def test_audit_artifact_live_status_is_machine_checkable() -> None:
    payload = _artifact().to_dict()
    assert payload["live_interoperability_status"] == "UNRUN"
    with pytest.raises(ValueError, match="live_interoperability_status"):
        _artifact(live_interoperability_status="PARTIAL — LIVE INTEROPERABILITY MATRIX UNRUN")


def test_closed_vocabularies_are_exact() -> None:
    assert [item.value for item in BaselineScope] == ["merged", "overlay", "both-aligned", "both-divergent", "binding"]
    assert [item.value for item in Classification] == [
        "CANONICAL", "CANONICAL_BYPASSED", "DUPLICATED", "CONTRADICTORY", "MISSING",
        "INTENTIONALLY_EXCEPTIONAL", "PROVISIONAL_OVERLAY", "NOT_PRESENT", "SUPERSEDED", "UNCLASSIFIED",
    ]
    assert [item.value for item in LiveStatus] == ["UNRUN", "PARTIAL", "INVALID", "COMPLETE"]
    assert [item.value for item in GateStatus] == ["PASS", "PASS_WITH_FINDINGS", "INCOMPLETE"]
    assert [item.value for item in PrerequisiteStatus] == [
        "SATISFIED", "SATISFIED_AT_PICKUP", "UNRESOLVED", "DEFERRED_TASK_3", "UNAVAILABLE",
        "UNAUTHORIZED", "UNAVAILABLE_AND_UNAUTHORIZED", "NOT_YET_IMPLEMENTED",
    ]


def test_python_model_and_independent_json_schema_agree() -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    payload = _artifact().to_dict()
    assert list(validator.iter_errors(payload)) == []
    assert set(payload) == set(schema["required"])
    assert schema["additionalProperties"] is False


def test_artifact_rejects_unknown_fields_missing_evidence_and_count_mismatch() -> None:
    with pytest.raises(TypeError):
        _artifact(unexpected=True)
    with pytest.raises(ValueError, match="owner"):
        _artifact(findings=(_finding(owner=""),))
    with pytest.raises(ValueError, match="evidence"):
        _artifact(findings=(_finding(evidence=()),))
    with pytest.raises(ValueError, match="finding_counts_by_classification"):
        AuditArtifact.from_dict({
            **_artifact().to_dict(),
            "finding_counts_by_classification": {**_artifact().to_dict()["finding_counts_by_classification"], "CANONICAL": 2},
        })
    with pytest.raises(ValueError, match="discovered_multipliers"):
        _artifact(discovered_multipliers={"cancellation_points": 0})
    with pytest.raises(ValueError, match="computed_run_cost"):
        _artifact(computed_run_cost={**_artifact().computed_run_cost, "unexpected": 0})


def test_artifact_rejects_workspace_only_provenance_and_overlay_binding_finding() -> None:
    with pytest.raises(ValueError, match="running_artifact_provenance"):
        _artifact(running_artifact_provenance={"git_sha": _MERGED})
    with pytest.raises(ValueError, match="binding finding"):
        _artifact(binding_commit=_MERGED, findings=(_finding(baseline_scope=BaselineScope.OVERLAY),))
    with pytest.raises(ValueError, match="binding_commit"):
        _artifact(findings=(_finding(baseline_scope=BaselineScope.BINDING),))


def test_g1_pass_rejects_unclassified_foundation_findings() -> None:
    with pytest.raises(ValueError, match="UNCLASSIFIED"):
        _artifact(findings=(_finding(classification=Classification.UNCLASSIFIED),))
    incomplete = _artifact(
        findings=(_finding(classification=Classification.UNCLASSIFIED),),
        gate_status=GateStatus.INCOMPLETE,
        static_audit_status=LiveStatus.UNRUN,
    )
    assert incomplete.unclassified_finding_count == 1


def test_binding_finding_requires_binding_scoped_evidence_lineage() -> None:
    with pytest.raises(ValueError, match="binding evidence"):
        _artifact(
            binding_commit=_MERGED,
            findings=(
                _finding(
                    baseline_scope=BaselineScope.BINDING,
                    evidence=(
                        EvidenceReference(
                            evidence_id="E-OVERLAY-001",
                            baseline_scope=BaselineScope.OVERLAY,
                            digest="b" * 64,
                        ),
                    ),
                ),
            ),
        )
    payload = _artifact().to_dict()
    payload["binding_commit"] = _MERGED
    payload["findings"][0]["baseline_scope"] = "binding"
    payload["findings"][0]["evidence"][0]["baseline_scope"] = "overlay"
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_python_model_rejects_every_schema_constrained_negative_shape() -> None:
    valid = _artifact().to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    mutations = []
    for path, value in (
        (("schema_version",), "wrong"),
        (("merged_commit",), "ABC"),
        (("overlay_commit",), None),
        (("binding_commit",), "bad"),
        (("discovered_multipliers", "queues"), -1),
        (("discovered_multipliers", "sinks"), True),
        (("computed_run_cost", "cancellation_concurrency_levels"), [1, 2, 4, 8]),
        (("computed_run_cost", "queue_admissions"), -1),
        (("computed_run_cost", "scenario_p50_ms"), {"delivery": -0.1}),
        (("computed_run_cost", "scenario_p95_ms"), {"delivery": True}),
        (("finding_counts_by_classification", "CANONICAL"), True),
        (("unclassified_finding_count",), False),
    ):
        payload = deepcopy(valid)
        target = payload
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        mutations.append(payload)
    for payload in mutations:
        assert list(Draft202012Validator(schema).iter_errors(payload))
        with pytest.raises(ValueError):
            AuditArtifact.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("findings", 0, "finding_id"), True),
        (("findings", 0, "subject"), 17),
        (("findings", 0, "owner"), ["Plan 11.26"]),
        (("findings", 0, "ruling"), False),
        (("findings", 0, "symbols", 0), 9),
        (("findings", 0, "evidence", 0, "evidence_id"), 4),
        (("findings", 0, "evidence", 0, "digest"), ["a" * 64]),
        (("baseline_reconciliation_status",), 1),
    ],
)
def test_python_and_schema_reject_non_string_values_for_every_artifact_string(
    path: tuple[str | int, ...], value: object,
) -> None:
    payload = deepcopy(_artifact().to_dict())
    target: object = payload
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("running_artifact_provenance", "executable_path"), True),
        (("running_artifact_provenance", "package_name"), 1),
        (("running_artifact_provenance", "package_version"), []),
        (("running_artifact_provenance", "client_provenance", "name"), False),
        (("running_artifact_provenance", "client_provenance", "version"), 17),
        (("running_artifact_provenance", "client_provenance", "path"), ["Zed.exe"]),
    ],
)
def test_python_and_schema_reject_non_string_provenance_identity_fields(
    path: tuple[str, ...], value: object,
) -> None:
    payload = deepcopy(_artifact(binding_commit=_MERGED, running_artifact_provenance=_provenance()).to_dict())
    target: object = payload
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "findings_tuple",
        "symbols_string",
        "symbols_tuple",
        "evidence_tuple",
        "concurrency_tuple",
        "finding_record_list",
        "evidence_record_list",
        "multipliers_key_list",
        "cost_key_list",
        "provenance_key_list",
    ],
)
def test_python_and_schema_reject_wrong_array_and_object_container_types(mutation: str) -> None:
    payload = deepcopy(_artifact().to_dict())
    finding = payload["findings"][0]
    if mutation == "findings_tuple":
        payload["findings"] = tuple(payload["findings"])
    elif mutation == "symbols_string":
        finding["symbols"] = "not-an-array"
    elif mutation == "symbols_tuple":
        finding["symbols"] = tuple(finding["symbols"])
    elif mutation == "evidence_tuple":
        finding["evidence"] = tuple(finding["evidence"])
    elif mutation == "concurrency_tuple":
        payload["computed_run_cost"]["cancellation_concurrency_levels"] = (2, 4, 8)
    elif mutation == "finding_record_list":
        finding_payload = finding
        payload["findings"][0] = list(finding_payload)
    elif mutation == "evidence_record_list":
        evidence_payload = finding["evidence"][0]
        finding["evidence"][0] = list(evidence_payload)
    elif mutation == "multipliers_key_list":
        payload["discovered_multipliers"] = list(payload["discovered_multipliers"])
    elif mutation == "cost_key_list":
        payload["computed_run_cost"] = list(payload["computed_run_cost"])
    elif mutation == "provenance_key_list":
        payload["binding_commit"] = _MERGED
        payload["running_artifact_provenance"] = list(_provenance())
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(payload)


def test_to_dict_canonicalizes_finding_and_mapping_order() -> None:
    first = _finding(finding_id="F-002")
    second = _finding(finding_id="F-001")
    a = _artifact(
        findings=(first, second),
        discovered_multipliers={"sinks": 0, "queues": 0, "close_paths": 0, "cancellation_points": 0},
    )
    b = _artifact(findings=(second, first))
    assert json.dumps(a.to_dict(), separators=(",", ":")) == json.dumps(b.to_dict(), separators=(",", ":"))


def test_model_and_schema_validate_closed_derived_provenance_record() -> None:
    artifact = _artifact(binding_commit=_MERGED, running_artifact_provenance=_provenance())
    payload = artifact.to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    for mutation in (
        {**_provenance(), "package_name": ""},
        {**_provenance(), "environment_fingerprint": "bad"},
        {**_provenance(), "unexpected": "asserted"},
        {**_provenance(), "client_provenance": {**_provenance()["client_provenance"], "metadata_sha256": "bad"}},
    ):
        with pytest.raises(ValueError):
            _artifact(binding_commit=_MERGED, running_artifact_provenance=mutation)


@pytest.mark.parametrize(
    "field",
    [
        "live_redis_status",
        "acpx_status",
        "additional_client_status",
        "zed_status",
        "live_interoperability_status",
    ],
)
@pytest.mark.parametrize("status", [LiveStatus.PARTIAL, LiveStatus.COMPLETE])
def test_live_partial_or_complete_requires_binding_and_provenance_in_model_and_schema(
    field: str, status: LiveStatus,
) -> None:
    with pytest.raises(ValueError, match="live evidence"):
        _artifact(**{field: status})
    payload = _artifact().to_dict()
    payload[field] = status.value
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload))
    with pytest.raises(ValueError, match="live evidence"):
        AuditArtifact.from_dict(payload)


@pytest.mark.parametrize("status", [LiveStatus.PARTIAL, LiveStatus.COMPLETE])
def test_live_evidence_invariant_accepts_complete_binding_and_provenance(status: LiveStatus) -> None:
    artifact = _artifact(
        binding_commit=_MERGED,
        running_artifact_provenance=_provenance(),
        live_interoperability_status=status,
    )
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(artifact.to_dict())) == []


@pytest.mark.parametrize("status", [LiveStatus.UNRUN, LiveStatus.INVALID])
def test_live_evidence_invariant_keeps_null_evidence_controls_representable(status: LiveStatus) -> None:
    artifact = _artifact(
        live_redis_status=status,
        acpx_status=status,
        additional_client_status=status,
        zed_status=status,
        live_interoperability_status=status,
        static_audit_status=LiveStatus.UNRUN,
        runtime_characterization_status=LiveStatus.UNRUN,
    )
    payload = artifact.to_dict()
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    assert AuditArtifact.from_dict(payload).binding_commit is None
