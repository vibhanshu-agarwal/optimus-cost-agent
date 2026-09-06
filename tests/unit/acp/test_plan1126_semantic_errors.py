from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import (
    AuditArtifact,
    ScopeOutReachability,
    assert_scope_out_register_ready_for_g4,
)
from tools.plan1126_runtime_audit.render import render_markdown
from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree
from tools.run_plan1126_runtime_audit import main

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - Historical commit-identity pin in _MERGED;
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - Historical commit-identity pin in _OVERLAY;
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")


def _semantic_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.semantic_errors")
    except ModuleNotFoundError:
        pytest.fail("Task 7 semantic-error audit module does not exist")


def _immutable_source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _cumulative_source(commit: str, semantic_paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(sorted(set(H3_SOURCE_PATHS) | set(H4_SOURCE_PATHS) | set(H5_SOURCE_PATHS) | set(semantic_paths)))
    return SourceTree({path: source.read_text(path) for path in paths})


@dataclass(frozen=True)
class _LexicalSemanticSite:
    path: str
    line: int
    site_kind: str


_NAMED_ERROR = re.compile(r"^(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*-\d+\s*$")
_JSON_RPC_ERROR = re.compile(r"\bJsonRpcError\s*\(")
_EXCEPT = re.compile(r"^\s*except\s+")
_ERROR_RESPONSE_DEFINITION = re.compile(r"^def\s+error_response\s*\(")


def _lexical_semantic_oracle(source: SourceTree) -> set[_LexicalSemanticSite]:
    """Line-regex oracle; it imports neither the AST scanner nor a site allowlist."""

    sites: set[_LexicalSemanticSite] = set()
    for path in source.paths():
        for line_number, line in enumerate(source.read_text(path).splitlines(), start=1):
            if path.endswith("errors.py") and _NAMED_ERROR.fullmatch(line):
                sites.add(_LexicalSemanticSite(path, line_number, "NAMED_ERROR_CONSTANT"))
            if _JSON_RPC_ERROR.search(line) and not line.lstrip().startswith(("class ", "#")):
                sites.add(_LexicalSemanticSite(path, line_number, "WIRE_ERROR_SELECTION"))
            if _EXCEPT.match(line):
                sites.add(_LexicalSemanticSite(path, line_number, "EXCEPTION_SELECTION"))
            if path.endswith("errors.py") and _ERROR_RESPONSE_DEFINITION.match(line):
                sites.add(_LexicalSemanticSite(path, line_number, "PUBLIC_OUTPUT_BUILDER"))
    return sites


def test_semantic_inventory_is_independent_complete_and_not_seeded() -> None:
    module = _semantic_module()
    source = _immutable_source(_MERGED, module.H7_SOURCE_PATHS)
    inventory = module.discover_semantic_inventory(source)

    actual = {
        _LexicalSemanticSite(site.path, site.line, site.site_kind)
        for site in inventory.sites
    }
    assert actual == _lexical_semantic_oracle(source)
    assert inventory.site_count == len(actual) > 0
    assert inventory.expected_site_count is None
    assert all(site.category in module.SemanticCategory for site in inventory.sites)
    assert all(site.classification.value != "UNCLASSIFIED" for site in inventory.sites)
    cancelled = [site for site in inventory.sites if "CancelledError" in site.exception_names]
    assert cancelled
    assert all(site.category.value == "CANCELLATION_DEADLINE" for site in cancelled)
    assert all(site.public_output == "NO_WIRE_OUTPUT" for site in cancelled)

    fixture = SourceTree({"src/optimus/acp/errors.py": '''
LOCAL_INPUT = -32600
def error_response(request_id, error):
    return error
def select():
    try:
        return JsonRpcError(code=LOCAL_INPUT, message="invalid")
    except LookupError:
        return None
'''})
    fixture_inventory = module.discover_semantic_inventory(fixture)
    assert fixture_inventory.site_count == 4
    assert {site.site_kind for site in fixture_inventory.sites} == {
        "NAMED_ERROR_CONSTANT", "PUBLIC_OUTPUT_BUILDER", "WIRE_ERROR_SELECTION", "EXCEPTION_SELECTION",
    }


def test_s3_sanitizer_broad_catches_are_exact_and_intentionally_exceptional() -> None:
    module = _semantic_module()
    inventory = module.discover_semantic_inventory(_immutable_source(_MERGED, module.H7_SOURCE_PATHS))
    s3 = [site for site in inventory.sites if site.seed_id == "S3"]
    assert {(site.symbol, site.exception_names) for site in s3} == {
        ("src.optimus.acp.errors.sanitize_protocol_error_message", ("Exception",)),
        ("src.optimus.acp.errors.sanitize_protocol_error_data", ("Exception",)),
    }
    assert all(site.classification.value == "INTENTIONALLY_EXCEPTIONAL" for site in s3)
    assert all(site.public_output == "FAIL_CLOSED_SANITIZED" for site in s3)


def test_eight_categories_execute_100_real_sanitizer_cases_each() -> None:
    module = _semantic_module()
    inventory = module.discover_semantic_inventory(_immutable_source(_MERGED, module.H7_SOURCE_PATHS))
    observations = module.semantic_selection_observations(inventory=inventory, cases_per_category=100)

    assert len(observations) == len(module.SemanticCategory) * 100
    assert {item.category for item in observations} == set(module.SemanticCategory)
    assert all(item.complete for item in observations)
    assert all(item.error_code_name in module.NAMED_ERROR_CODES for item in observations)
    assert all(item.leakage_result == "CLEAN" for item in observations)
    assert all(item.divergence_result == "MATCH" for item in observations)
    assert all(item.input_digest != item.output_digest for item in observations)
    by_category: dict[object, int] = {}
    for item in observations:
        by_category[item.category] = by_category.get(item.category, 0) + 1
    assert set(by_category.values()) == {100}


def test_h6_h7_artifact_recomputes_coverage_findings_and_scope_out_debt(tmp_path: Path) -> None:
    module = _semantic_module()
    artifact = module.build_h7_audit_artifact(
        merged=_cumulative_source(_MERGED, module.H7_SOURCE_PATHS),
        overlay=_cumulative_source(_OVERLAY, module.H7_SOURCE_PATHS),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4", "H5", "H6", "H7"}
    assert records["H6"]["schema_oracle_status"] == "PASS"
    assert records["H6"]["ast_oracle_status"] == "PASS"
    assert records["H6"]["legacy_allowlist_count"] == 0
    assert records["H6"]["reviewer_status"] == "PENDING_G2"

    h7 = records["H7"]
    assert h7["reviewer_status"] == "PENDING_G2"
    assert h7["inventory"]["expected_site_count"] is None
    assert h7["inventory"]["site_count"] == len(h7["inventory"]["sites"])
    assert h7["observations"]["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
    assert h7["observations"]["total_observation_count"] == 800
    assert h7["observations"]["complete_observation_count"] == 800

    for assessment in h7["observations"]["coverage_assessments"]:
        observed = sorted({row[assessment["field_name"]] for row in h7["observations"]["rows"]})
        missing = sorted(set(assessment["vocabulary_values"]) - set(observed))
        assert assessment["observed_values"] == observed
        assert assessment["missing_values"] == missing
        assert assessment["status"] == ("SCOPED_OUT" if missing else "FULLY_OBSERVED")
        if missing:
            assert assessment["reason"] and assessment["owner"] and assessment["next_gate"]

    h7_findings = [item for item in payload["findings"] if item["finding_id"].startswith("H7-")]
    assert h7_findings
    assert all(item["classification"] != "UNCLASSIFIED" for item in h7_findings)
    assert any("turn" in item["subject"].lower() and item["classification"] == "CONTRADICTORY" for item in h7_findings)

    register = payload["scope_out_register"]
    assert register
    assert all(entry["reachable_in_gate"] in {item.value for item in ScopeOutReachability} for entry in register)
    assert all("planned_scenarios_can_reach_missing" not in entry for entry in register)
    with pytest.raises(ValueError, match="NOT_YET_ASSESSED"):
        assert_scope_out_register_ready_for_g4(artifact.scope_out_register or ())
    discharged = tuple(replace(entry, reachable_in_gate=ScopeOutReachability.REACHABLE) for entry in artifact.scope_out_register or ())
    assert_scope_out_register_ready_for_g4(discharged)

    report = render_markdown(payload)
    assert "### `H6`" in report
    assert "### `H7`" in report
    assert "Semantic category coverage" in report
    assert "NOT_YET_ASSESSED" in report

    artifact_path = tmp_path / "task7-artifact.json"
    artifact_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 0

    changed = json.loads(artifact_path.read_text(encoding="utf-8"))
    changed_h7 = next(record for record in changed["evidence_records"] if record["hypothesis_id"] == "H7")
    canonical_site = next(site for site in changed_h7["inventory"]["sites"] if site["classification"] == "CANONICAL")
    canonical_site["classification"] = "MISSING"
    artifact_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 1
