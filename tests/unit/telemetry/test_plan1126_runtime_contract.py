from __future__ import annotations

import importlib
import io
import json
import re
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import AuditArtifact
from tools.plan1126_runtime_audit.render import render_markdown
from tools.plan1126_runtime_audit.semantic_errors import H7_SOURCE_PATHS
from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree
from tools.run_plan1126_runtime_audit import main

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - Historical commit-identity pin in _MERGED;
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - Historical commit-identity pin in _OVERLAY;
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")


def _telemetry_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.telemetry")
    except ModuleNotFoundError:
        pytest.fail("Task 8 telemetry audit module does not exist")


def _immutable_source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _cumulative_source(commit: str, telemetry_paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(
        sorted(
            set(H3_SOURCE_PATHS)
            | set(H4_SOURCE_PATHS)
            | set(H5_SOURCE_PATHS)
            | set(H7_SOURCE_PATHS)
            | set(telemetry_paths)
        )
    )
    return SourceTree({path: source.read_text(path) for path in paths})


@dataclass(frozen=True)
class _LexicalSite:
    path: str
    line: int
    site_kind: str


_EVENT_KIND = re.compile(r'^\s{4}[A-Z][A-Z0-9_]*\s*=\s*"[a-z0-9_]+"\s*$')
_EVENT_EMISSION = re.compile(r"\bTelemetryEvent\.[a-z_]+\s*\(")
_DEBUG_TRACE = re.compile(r"\bacp_debug_log\s*\(")
_REDACTION = re.compile(r"\bredact_for_telemetry\s*\(")
_STDERR = re.compile(r"\bfile\s*=\s*sys\.stderr\b")
_SINK_DEFINITION = re.compile(
    r"^(?:class\s+(?:JsonlTelemetryWriter|RedisTelemetryEventSink|GatewayObservabilityExporter)\b"
    r"|def\s+acp_debug_log\s*\()"
)


def _lexical_inventory_oracle(source: SourceTree) -> set[_LexicalSite]:
    """Line oracle: no AST scanner import, expected site list, or expected count."""

    sites: set[_LexicalSite] = set()
    in_event_kind = False
    for path in source.paths():
        raw = source.read_text(path)
        lines = raw.splitlines()
        ignored_rows: set[int] = set()
        tokens = list(tokenize.generate_tokens(io.StringIO(raw).readline))
        significant = [
            token for token in tokens
            if token.type not in {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING}
        ]
        for index, token in enumerate(significant):
            if token.type != tokenize.STRING:
                continue
            previous = significant[index - 1] if index else None
            if previous is None or previous.type in {tokenize.INDENT, tokenize.NEWLINE, tokenize.DEDENT}:
                ignored_rows.update(range(token.start[0], token.end[0] + 1))
        for line_number, line in enumerate(lines, start=1):
            if line_number in ignored_rows:
                continue
            stripped = line.strip()
            if path.endswith("telemetry/events.py") and stripped == "class TelemetryEventKind(StrEnum):":
                in_event_kind = True
                continue
            if in_event_kind and path.endswith("telemetry/events.py"):
                if stripped.startswith("class "):
                    in_event_kind = False
                elif _EVENT_KIND.fullmatch(line):
                    sites.add(_LexicalSite(path, line_number, "EVENT_KIND"))
            if _EVENT_EMISSION.search(line) and not stripped.startswith(("#", "def ")):
                sites.add(_LexicalSite(path, line_number, "EVENT_EMISSION"))
            if _DEBUG_TRACE.search(line) and not stripped.startswith(("#", "def ")):
                sites.add(_LexicalSite(path, line_number, "DEBUG_TRACE"))
            if _REDACTION.search(line) and not stripped.startswith(("#", "def ")):
                sites.add(_LexicalSite(path, line_number, "REDACTION"))
            if _STDERR.search(line):
                sites.add(_LexicalSite(path, line_number, "STDERR"))
            if _SINK_DEFINITION.match(stripped):
                sites.add(_LexicalSite(path, line_number, "SINK"))
    return sites


def test_telemetry_inventory_is_independent_complete_and_not_seeded() -> None:
    module = _telemetry_module()
    source = _immutable_source(_MERGED, module.H8_SOURCE_PATHS)
    inventory = module.discover_telemetry_inventory(source)

    actual = {_LexicalSite(site.path, site.line, site.site_kind) for site in inventory.sites}
    assert actual == _lexical_inventory_oracle(source)
    assert inventory.expected_site_count is None
    assert inventory.site_count == len(actual) > 0
    assert inventory.sink_count == len({site.sink_id for site in inventory.sites if site.sink_id}) > 0
    assert inventory.event_kind_count == len(inventory.event_schemas) > 0
    assert all(site.classification.value != "UNCLASSIFIED" for site in inventory.sites)


def test_runtime_event_schema_generated_10000_cases() -> None:
    module = _telemetry_module()
    inventory = module.discover_telemetry_inventory(
        _immutable_source(_MERGED, module.H8_SOURCE_PATHS)
    )
    observations = module.runtime_event_schema_observations(inventory=inventory, case_count=10_000)

    assert len(observations) == 10_000
    assert {row.event_kind for row in observations} == set(inventory.event_schemas)
    assert {row.case_kind.value for row in observations} == {
        "VALID", "MISSING_REQUIRED", "EXTRA_FIELD", "INVALID_FIELD"
    }
    assert {row.conformance.value for row in observations} == {"MATCH", "DIVERGED"}
    assert all(row.complete for row in observations)
    for row in observations:
        expected = "ACCEPTED" if row.case_kind.value == "VALID" else "REJECTED"
        assert row.expected_outcome.value == expected
        assert row.conformance.value == (
            "MATCH" if row.actual_outcome is row.expected_outcome else "DIVERGED"
        )


def test_runtime_redaction_generated_1000_cases(tmp_path: Path) -> None:
    module = _telemetry_module()
    inventory = module.discover_telemetry_inventory(
        _immutable_source(_MERGED, module.H8_SOURCE_PATHS)
    )
    observations = module.runtime_redaction_observations(
        inventory=inventory,
        case_count=1_000,
        workspace=tmp_path,
    )

    assert len(observations) == 1_000
    assert {row.content_class.value for row in observations} == {
        "CREDENTIAL", "PROMPT", "RESPONSE", "PATH", "REQUEST_BODY"
    }
    assert {row.overall_result.value for row in observations} == {"CLEAN", "LEAKED"}
    assert all(row.complete for row in observations)
    for row in observations:
        assert set(row.sink_results) == set(inventory.sink_ids)
        expected = "CLEAN" if set(row.sink_results.values()) == {"CLEAN"} else "LEAKED"
        assert row.overall_result.value == expected


def test_runtime_correlation_chain_is_complete() -> None:
    module = _telemetry_module()
    inventory = module.discover_telemetry_inventory(
        _immutable_source(_MERGED, module.H8_SOURCE_PATHS)
    )
    observations = module.runtime_correlation_observations(inventory=inventory)

    assert observations
    assert {row.result.value for row in observations} == {"COMPLETE", "INCOMPLETE"}
    assert "request_id" in inventory.required_correlation_fields
    assert "run_id" in inventory.required_correlation_fields
    for row in observations:
        missing = tuple(sorted(set(inventory.required_correlation_fields) - set(row.present_fields)))
        assert row.missing_fields == missing
        assert row.result.value == ("COMPLETE" if not missing else "INCOMPLETE")

    by_channel = {row.channel: row for row in observations if row.event_kind is None}
    for channel, site_kind in (
        ("debug_trace", module.TelemetrySiteKind.DEBUG_TRACE),
        ("stderr", module.TelemetrySiteKind.STDERR),
    ):
        site_fields = [
            set(site.correlation_fields)
            for site in inventory.sites
            if site.site_kind is site_kind
        ]
        assert site_fields
        fields_present_at_every_site = set.intersection(*site_fields)
        expected = tuple(sorted(fields_present_at_every_site & set(inventory.required_correlation_fields)))
        assert by_channel[channel].present_fields == expected


def test_telemetry_sink_failures_are_contained(tmp_path: Path) -> None:
    module = _telemetry_module()
    inventory = module.discover_telemetry_inventory(
        _immutable_source(_MERGED, module.H8_SOURCE_PATHS)
    )
    observations = module.telemetry_sink_failure_observations(
        inventory=inventory,
        repeats=100,
        workspace=tmp_path,
    )

    assert len(observations) == inventory.sink_count * 100
    assert Counter(row.sink_id for row in observations) == {
        sink_id: 100 for sink_id in inventory.sink_ids
    }
    assert {row.failure_result.value for row in observations} == {"CONTAINED", "PROPAGATED"}
    assert all(row.complete for row in observations)
    assert all(row.control_digest for row in observations)
    assert all(row.failure_digest for row in observations)


def test_h8_artifact_recomputes_s2_cost_coverage_and_findings(tmp_path: Path) -> None:
    module = _telemetry_module()
    artifact = module.build_h8_audit_artifact(
        merged=_cumulative_source(_MERGED, module.H8_SOURCE_PATHS),
        overlay=_cumulative_source(_OVERLAY, module.H8_SOURCE_PATHS),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
        workspace=tmp_path,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4", "H5", "H6", "H7", "H8"}
    h8 = records["H8"]
    assert h8["reviewer_status"] == "PENDING_G2"
    assert h8["inventory"]["expected_site_count"] is None
    assert h8["inventory"]["sink_count"] == payload["discovered_multipliers"]["sinks"]
    assert payload["computed_run_cost"]["sink_failure_runs"] == h8["inventory"]["sink_count"] * 100
    assert h8["schema_observations"]["total_observation_count"] == 10_000
    assert h8["redaction_observations"]["total_observation_count"] == 1_000
    assert h8["sink_failure_observations"]["total_observation_count"] == h8["inventory"]["sink_count"] * 100
    assert h8["s2_ruling"]["classification"] == "CANONICAL"
    assert h8["s2_ruling"]["scalar_field"] == "gateway_request_id"
    assert h8["s2_ruling"]["plural_field"] == "gateway_request_ids"
    assert h8["s2_ruling"]["symbol_citations"]

    for summary_name in (
        "schema_observations", "redaction_observations", "correlation_observations",
        "sink_failure_observations",
    ):
        summary = h8[summary_name]
        assert summary["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
        for assessment in summary["coverage_assessments"]:
            observed = sorted({row[assessment["field_name"]] for row in summary["rows"]})
            missing = sorted(set(assessment["vocabulary_values"]) - set(observed))
            assert assessment["observed_values"] == observed
            assert assessment["missing_values"] == missing
            assert assessment["status"] == ("SCOPED_OUT" if missing else "FULLY_OBSERVED")
            if missing:
                assert assessment["reason"] and assessment["owner"] and assessment["next_gate"]

    h8_findings = [item for item in payload["findings"] if item["finding_id"].startswith("H8-")]
    assert h8_findings
    assert all(item["classification"] != "UNCLASSIFIED" for item in h8_findings)

    report = render_markdown(payload)
    assert "### `H8`" in report
    assert "gateway_request_id" in report
    assert "gateway_request_ids" in report

    artifact_path = tmp_path / "task8-artifact.json"
    artifact_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 0

    changed = json.loads(artifact_path.read_text(encoding="utf-8"))
    changed_h8 = next(record for record in changed["evidence_records"] if record["hypothesis_id"] == "H8")
    changed_h8["inventory"]["expected_site_count"] = 1
    artifact_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 1
