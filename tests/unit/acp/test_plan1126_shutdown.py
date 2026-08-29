from __future__ import annotations

import copy
import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import AuditArtifact
from tools.plan1126_runtime_audit.render import render_markdown
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")
_CAUSES = {
    "orderly_eof",
    "request_cancellation",
    "transport_failure",
    "server_cancellation",
    "partial_startup_failure",
}


def _shutdown_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.shutdown")
    except ModuleNotFoundError:
        pytest.fail("Task 6 shutdown audit module does not exist")


def _immutable_source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _cumulative_source(commit: str, shutdown_paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS) | set(shutdown_paths)))
    return SourceTree({path: source.read_text(path) for path in paths})


@dataclass(frozen=True)
class _LexicalCloseSite:
    path: str
    line: int
    site_kind: str
    reference: str


_CLOSE_DEFINITION = re.compile(
    r"^\s*(?:async\s+)?def\s+(?P<name>close|aclose|close_all|close_and_join|stop|shutdown_background_loop)\s*\("
)
_CLOSE_CALL = re.compile(
    r"\b(?P<reference>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\."
    r"(?:close|aclose|close_all|close_and_join|stop|terminate|kill|cancel|release|join))\s*\("
)
_INLINE_CONSTRUCTOR_CLOSE = re.compile(
    r"\b(?P<owner>[A-Z][A-Za-z0-9_]*)\([^\n]*\)\."
    r"(?P<leaf>close|aclose|close_all|close_and_join|stop)\s*\("
)


def _lexical_close_oracle(source: SourceTree) -> set[_LexicalCloseSite]:
    """Line-regex oracle: independent of the scanner's AST/receiver graph."""

    sites: set[_LexicalCloseSite] = set()
    for path in source.paths():
        for line_number, line in enumerate(source.read_text(path).splitlines(), start=1):
            definition = _CLOSE_DEFINITION.search(line)
            if definition:
                sites.add(_LexicalCloseSite(path, line_number, "CLOSE_DEFINITION", definition.group("name")))
                continue
            if line.lstrip().startswith(("#", "class ")):
                continue
            inline = _INLINE_CONSTRUCTOR_CLOSE.search(line)
            if inline:
                sites.add(
                    _LexicalCloseSite(
                        path,
                        line_number,
                        "CLOSE_INVOCATION",
                        f"{inline.group('owner')}.{inline.group('leaf')}",
                    )
                )
            for match in _CLOSE_CALL.finditer(line):
                reference = match.group("reference")
                if reference.endswith(".join") and not re.search(
                    r"(?:thread|reader|writer|worker|parts|future)s?\.join\s*\(", line, re.IGNORECASE
                ):
                    continue
                sites.add(_LexicalCloseSite(path, line_number, "CLOSE_INVOCATION", reference))
    return sites


def test_shutdown_inventory_is_independent_complete_and_receiver_safe() -> None:
    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    merged = _immutable_source(_MERGED, paths)
    overlay = _immutable_source(_OVERLAY, paths)
    inventory = module.discover_shutdown_inventory(merged, overlay=overlay)

    for baseline, source in (("merged", merged), ("overlay", overlay)):
        actual = {
            _LexicalCloseSite(site.path, site.line, site.site_kind, site.reference)
            for site in inventory.close_sites
            if site.source_baseline == baseline
        }
        assert actual == _lexical_close_oracle(source)

    assert inventory.close_path_count == len({site.conceptual_id for site in inventory.close_definitions})
    assert inventory.close_path_count > 0
    assert all(
        record.constructor and record.owner_transfer and record.normal_close
        and record.cancellation_close and record.partial_failure_close and record.repeated_close
        for record in inventory.resources
    )
    assert all(record.dependency_rank >= 0 for record in inventory.resources)
    assert all(site.reference not in {"str.join", "bytes.join"} for site in inventory.close_sites)

    fixture = SourceTree({"fixture.py": '''
class RealOwner:
    def close(self):
        return None

def run(owner, metrics, values):
    owner.close()
    metrics.close()
    return ",".join(values)
'''})
    fixture_inventory = module.discover_shutdown_inventory(fixture)
    references = {site.reference for site in fixture_inventory.close_sites}
    assert "close" in references
    assert "owner.close" in references
    assert "metrics.close" not in references
    assert not any("join" in reference for reference in references)


def test_shutdown_causes_repeat_100_with_control_allowlist() -> None:
    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    inventory = module.discover_shutdown_inventory(
        _immutable_source(_MERGED, paths), overlay=_immutable_source(_OVERLAY, paths)
    )
    observations = module.shutdown_schedule_observations(inventory=inventory, repeats=100)
    applicable = {record.close_path_id for record in inventory.resources if record.schedule_applicable}

    assert len(observations) == len(applicable) * len(_CAUSES) * 100
    assert {item.terminal_cause for item in observations} == _CAUSES
    assert {item.close_path_id for item in observations} == applicable
    assert all(item.complete for item in observations)
    assert all(item.close_invocation_count == 3 for item in observations)
    assert all(item.control_thread_names for item in observations)
    assert all(not item.unexpected_persistent_threads for item in observations)
    assert all(not item.unexpected_persistent_tasks for item in observations)
    assert all("probe_error" not in item.cause_effect for item in observations)
    assert all(item.repeat_latency_class in {"WITHIN_100MS", "ABOVE_100MS"} for item in observations)

    by_family: dict[tuple[str, str], int] = {}
    for item in observations:
        key = (item.close_path_id, item.terminal_cause)
        by_family[key] = by_family.get(key, 0) + 1
    assert set(by_family) == {(path, cause) for path in applicable for cause in _CAUSES}
    assert set(by_family.values()) == {100}


def test_close_is_idempotent_across_discovered_paths() -> None:
    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    inventory = module.discover_shutdown_inventory(
        _immutable_source(_MERGED, paths), overlay=_immutable_source(_OVERLAY, paths)
    )
    observations = module.shutdown_schedule_observations(inventory=inventory, repeats=1)
    applicable = {record.close_path_id for record in inventory.resources if record.schedule_applicable}
    assert {(item.close_path_id, item.terminal_cause) for item in observations} == {
        (path, cause) for path in applicable for cause in _CAUSES
    }
    for item in observations:
        assert item.close_invocation_count == 3
        assert item.underlying_close_count <= 1 or item.close_outcome in {"DOUBLE_CLOSE_OBSERVED", "ERROR"}
        assert item.close_outcome in {"CLOSED_ONCE", "IDEMPOTENT_NOOP", "DOUBLE_CLOSE_OBSERVED", "ERROR"}


def test_h5_artifact_derives_s1_cost_coverage_and_scope_out_register(tmp_path: Path) -> None:
    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    artifact = module.build_h5_audit_artifact(
        merged=_cumulative_source(_MERGED, paths),
        overlay=_cumulative_source(_OVERLAY, paths),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4", "H5"}
    record = records["H5"]
    assert record["baseline_scope"] == "both-divergent"
    assert record["reviewer_status"] == "PENDING_G2"
    assert record["close_path_count"] == payload["discovered_multipliers"]["close_paths"]
    assert payload["computed_run_cost"]["idempotent_close_invocations"] == record["close_path_count"] * 3 * 5
    assert record["s1_redis_runtime_ruling"]["merged"] == "MISSING"
    assert record["s1_redis_runtime_ruling"]["overlay"] == "PROVISIONAL_OVERLAY"
    assert record["shutdown_order"]["merged"][-1] != "redis_runtime"
    assert record["shutdown_order"]["overlay"][-1] == "redis_runtime"
    applicable_ids = {
        item["close_path_id"] for item in record["resource_ownership"] if item["schedule_applicable"]
    }
    scoped_ids = {
        item["close_path_id"] for item in record["resource_ownership"] if not item["schedule_applicable"]
    }
    assert {item["close_path_id"] for item in record["close_path_scope_outs"]} == scoped_ids
    assert all(item["owner"] == "P11-FEAT-ZED-RESUME" for item in record["close_path_scope_outs"])
    assert all("PENDING" not in item["repeated_close"] for item in record["resource_ownership"])

    summary = record["schedule_observations"]
    assert summary["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
    assert summary["vocabulary_coverage_status"] == "PARTIAL_WITH_SCOPE_OUTS"
    assert summary["total_observation_count"] == summary["complete_observation_count"]
    assert {item["close_path_id"] for item in summary["observations"]} == applicable_ids
    for assessment in summary["coverage_assessments"]:
        observed = {
            value
            for observation in summary["observations"]
            for value in (observation[assessment["field_name"]] if isinstance(observation[assessment["field_name"]], list) else [observation[assessment["field_name"]]])
        }
        vocabulary = set(assessment["vocabulary_values"])
        assert assessment["observed_values"] == sorted(observed)
        assert assessment["missing_values"] == sorted(vocabulary - observed)
        assert assessment["status"] == ("SCOPED_OUT" if vocabulary - observed else "FULLY_OBSERVED")

    register = payload["scope_out_register"]
    expected_scope_outs = sum(
        assessment["status"] == "SCOPED_OUT"
        for evidence_record in records.values()
        for assessment in evidence_record["schedule_observations"]["coverage_assessments"]
    )
    assert len(register) == expected_scope_outs
    assert all(entry["field_name"] and entry["owning_gate"] for entry in register)
    assert all(entry["missing_values"] for entry in register)
    assert all(entry["owner"] for entry in register)
    assert all(entry["planned_scenarios_can_reach_missing"] in {True, False, None} for entry in register)
    assert all(entry["reachability_reason"] for entry in register)

    report = render_markdown(payload)
    assert "### `H5`" in report
    assert "Derived close paths" in report
    assert "S1 serving RedisRuntime" in report
    assert "## Running scope-out register" in report

    artifact_path = tmp_path / "task6-artifact.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    cli = importlib.import_module("tools.run_plan1126_runtime_audit")
    assert cli._verify_artifact(str(artifact_path)).to_dict() == payload

    changed = copy.deepcopy(payload)
    changed["computed_run_cost"]["idempotent_close_invocations"] -= 1
    with pytest.raises(ValueError, match="close cost"):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    changed["scope_out_register"].pop()
    with pytest.raises(ValueError, match="scope-out register"):
        AuditArtifact.from_dict(changed)

    changed = copy.deepcopy(payload)
    changed["scope_out_register"][0]["planned_scenarios_can_reach_missing"] = "yes"
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(changed)
