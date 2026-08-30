from __future__ import annotations

import importlib
import json
import re
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import AuditArtifact
from tools.plan1126_runtime_audit.queue_policy import H9_SOURCE_PATHS
from tools.plan1126_runtime_audit.semantic_errors import H7_SOURCE_PATHS
from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree
from tools.plan1126_runtime_audit.telemetry import H8_SOURCE_PATHS
from tools.run_plan1126_runtime_audit import main

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"
_INTAKE_PATH = Path("reports/plan-11-26-baseline-intake.json")
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")
_EXPECTED_HEADS = (
    "128af65c851bd9f6eeffe54b01484a7a5650163f",
    "6208177b55237132c4087652de87c78f21159fb2",
    "79cd37cf37b2740f7580b2ed3859c0401a47f6a4",
    "9467df26603a88a4adce1057dea7725f925441f6",
    "c26928673cf03759c509c982e1e7a355ee6e9f46",
    "f6bd17069b906c74e7d6ba28ecd319354b5123b6",
    "f8e7e06c9c59f3adf50527f757f2c58b9b83795f",
    "fc80403060f578986c287686c27d935a8043dc5a",
)
_EXPECTED_DEFERRED = {
    "derive_session_lease_and_retention_constants": 0,
    "lease_boundary_1000_seed_schedule": 1_000,
    "create_acquire_mutate_release_cycles": 50,
    "owner_revision_races": 100,
    "wall_clock_recovery": 1,
}


def _session_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.session_lease")
    except ModuleNotFoundError:
        pytest.fail("Task 10 session-lease gate module does not exist")


def _intake() -> dict[str, object]:
    return json.loads(_INTAKE_PATH.read_text(encoding="utf-8"))


def _source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _cumulative_source(commit: str, h10_paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(sorted(
        set(H3_SOURCE_PATHS)
        | set(H4_SOURCE_PATHS)
        | set(H5_SOURCE_PATHS)
        | set(H7_SOURCE_PATHS)
        | set(H8_SOURCE_PATHS)
        | set(H9_SOURCE_PATHS)
        | set(h10_paths)
    ))
    return SourceTree({path: source.read_text(path) for path in paths})


def _lexical_symbol_oracle(source: SourceTree) -> set[tuple[str, int, str]]:
    pattern = re.compile(r"^\s*(SESSION_LOAD_LEASE_SECONDS|DEFAULT_ACP_SESSION_TTL_SECONDS)\s*=")
    return {
        (path, line_number, match.group(1))
        for path in source.paths()
        for line_number, line in enumerate(source.read_text(path).splitlines(), start=1)
        if (match := pattern.search(line)) is not None
    }


def test_binding_presence_gate_derives_provisional_overlay_and_stops() -> None:
    module = _session_module()
    merged = _source(_MERGED, module.H10_SOURCE_PATHS)
    overlay = _source(_OVERLAY, module.H10_SOURCE_PATHS)

    decision = module.evaluate_binding_presence_gate(
        intake=_intake(), merged=merged, overlay=overlay,
    )

    assert decision.outcome.value == "PROVISIONAL_OVERLAY"
    assert decision.binding_commit is None
    assert decision.owner == "P11-FEAT-ZED-RESUME"
    assert decision.stop_before_runtime is True
    assert decision.observed_plan_11_7_heads == _EXPECTED_HEADS
    assert {
        (item.path, item.line, item.symbol) for item in decision.overlay_symbols
    } == _lexical_symbol_oracle(overlay) == {
        ("src/optimus/acp/launch_policy.py", 89, "DEFAULT_ACP_SESSION_TTL_SECONDS"),
        ("src/optimus/acp/spec.py", 84, "SESSION_LOAD_LEASE_SECONDS"),
    }
    assert _lexical_symbol_oracle(merged) == set()
    assert decision.executed_predicate_count == 0
    assert decision.runtime_predicates_executed is False
    assert decision.live_redis_predicates_executed is False


def test_binding_presence_gate_can_report_not_present_without_seeded_overlay_expectation() -> None:
    module = _session_module()
    empty = SourceTree({"src/example.py": "VALUE = 1\n"})

    decision = module.evaluate_binding_presence_gate(
        intake=_intake(), merged=empty, overlay=empty,
    )

    assert decision.outcome.value == "NOT_PRESENT"
    assert decision.overlay_symbols == ()
    assert decision.stop_before_runtime is True


def test_binding_scope_out_names_every_deferred_obligation_and_next_gate() -> None:
    module = _session_module()
    record = module.session_lease_gate_record(
        intake=_intake(),
        merged=_source(_MERGED, module.H10_SOURCE_PATHS),
        overlay=_source(_OVERLAY, module.H10_SOURCE_PATHS),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )

    assert {item.obligation_id: item.planned_execution_count for item in record.deferred_obligations} == _EXPECTED_DEFERRED
    assert all(item.executed_count == 0 for item in record.deferred_obligations)
    assert all(item.owner == "P11-FEAT-ZED-RESUME" for item in record.deferred_obligations)
    assert all(item.next_gate == "Plan 11.7 binding integration candidate nomination" for item in record.deferred_obligations)
    assert all("binding" in item.reachable_after.lower() for item in record.deferred_obligations)
    payload = record.to_dict()
    assert "lease_seconds" not in json.dumps(payload)
    assert "retention_seconds" not in json.dumps(payload)


def test_binding_gate_rejects_intake_with_mismatched_baseline_identity() -> None:
    module = _session_module()
    intake = deepcopy(_intake())
    intake["merged_baseline"]["commit"] = "0" * 40

    with pytest.raises(ValueError, match="intake baseline identities"):
        module.session_lease_gate_record(
            intake=intake,
            merged=_source(_MERGED, module.H10_SOURCE_PATHS),
            overlay=_source(_OVERLAY, module.H10_SOURCE_PATHS),
            merged_commit=_MERGED,
            overlay_commit=_OVERLAY,
        )


def test_h10_artifact_is_scoped_out_without_runtime_or_live_evidence(tmp_path: Path) -> None:
    module = _session_module()
    artifact = module.build_h10_audit_artifact(
        merged=_cumulative_source(_MERGED, module.H10_SOURCE_PATHS),
        overlay=_cumulative_source(_OVERLAY, module.H10_SOURCE_PATHS),
        intake=_intake(),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()

    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []
    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10"}
    h10 = records["H10"]
    assert h10["gate_outcome"] == "PROVISIONAL_OVERLAY"
    assert h10["reviewer_status"] == "PENDING_G2"
    assert h10["executed_predicate_count"] == 0
    assert h10["runtime_predicates_executed"] is False
    assert h10["live_redis_predicates_executed"] is False
    assert payload["binding_commit"] is None
    assert payload["running_artifact_provenance"] is None
    assert payload["live_redis_status"] == "UNRUN"
    findings = [item for item in payload["findings"] if item["finding_id"].startswith("H10-")]
    assert len(findings) == 1
    assert findings[0]["classification"] == "PROVISIONAL_OVERLAY"
    assert findings[0]["baseline_scope"] == "overlay"
    assert findings[0]["owner"] == "P11-FEAT-ZED-RESUME"

    artifact_path = tmp_path / "task10-artifact.json"
    artifact_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 0

    changed = json.loads(artifact_path.read_text(encoding="utf-8"))
    changed_h10 = next(record for record in changed["evidence_records"] if record["hypothesis_id"] == "H10")
    changed_h10["executed_predicate_count"] = 1
    artifact_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 1
