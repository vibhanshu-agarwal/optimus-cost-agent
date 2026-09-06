from __future__ import annotations

import importlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit.cancellation import H3_SOURCE_PATHS
from tools.plan1126_runtime_audit.delivery_characterization import H4_SOURCE_PATHS
from tools.plan1126_runtime_audit.model import AuditArtifact
from tools.plan1126_runtime_audit.semantic_errors import H7_SOURCE_PATHS
from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS
from tools.plan1126_runtime_audit.source import GitCommitSource, SourceTree
from tools.plan1126_runtime_audit.telemetry import H8_SOURCE_PATHS
from tools.run_plan1126_runtime_audit import main

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - Historical commit-identity pin in _MERGED;
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - Historical commit-identity pin in _OVERLAY;
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")


def _queue_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.queue_policy")
    except ModuleNotFoundError:
        pytest.fail("Task 9 queue-policy audit module does not exist")


def _immutable_source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _cumulative_source(commit: str, queue_paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    paths = tuple(sorted(
        set(H3_SOURCE_PATHS)
        | set(H4_SOURCE_PATHS)
        | set(H5_SOURCE_PATHS)
        | set(H7_SOURCE_PATHS)
        | set(H8_SOURCE_PATHS)
        | set(queue_paths)
    ))
    return SourceTree({path: source.read_text(path) for path in paths})


@dataclass(frozen=True)
class _LexicalSite:
    path: str
    line: int
    site_kind: str


_QUEUE_CONSTRUCTOR = re.compile(
    r"\b(?P<receiver>(?:self\.)?[A-Za-z_]\w*)(?:\s*:[^=]+)?\s*=\s*"
    r"(?:queue|asyncio)\.Queue(?:\[[^]]+\])?\s*\("
)
_QUEUE_OPERATION = re.compile(r"\b(?P<receiver>(?:self\.)?[A-Za-z_]\w*)\.(?P<method>put|get)\s*\(")
_HEALTH_PATTERNS = (
    ("POOL_CONSTRUCTOR", re.compile(r"\bConnectionPool\.from_url\s*\(")),
    ("CLIENT_CONSTRUCTOR", re.compile(r"\baioredis\.Redis\s*\(")),
    ("HEALTH_PROBE", re.compile(r"\bself\.client\.ping\s*\(")),
    ("CLIENT_CLOSE", re.compile(r"\bself\.client\.aclose\s*\(")),
    ("POOL_CLOSE", re.compile(r"\bself\.pool\.aclose\s*\(")),
    ("BRIDGE_WAIT", re.compile(r"\brun_coroutine_threadsafe\([^\n]+\)\.result\s*\(")),
)


def _lexical_inventory_oracle(source: SourceTree) -> set[_LexicalSite]:
    """Raw-line oracle: no AST scanner import, queue list, or expected count."""

    sites: set[_LexicalSite] = set()
    for path in source.paths():
        numbered_lines = tuple(enumerate(source.read_text(path).splitlines(), start=1))
        queue_receivers = {
            match.group("receiver")
            for _, line in numbered_lines
            if (match := _QUEUE_CONSTRUCTOR.search(line)) is not None
        }
        for line_number, line in numbered_lines:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _QUEUE_CONSTRUCTOR.search(line):
                sites.add(_LexicalSite(path, line_number, "QUEUE_CONSTRUCTOR"))
            operation = _QUEUE_OPERATION.search(line)
            if operation is not None and operation.group("receiver") in queue_receivers:
                kind = "QUEUE_ADMISSION" if operation.group("method") == "put" else "QUEUE_CONSUMER"
                sites.add(_LexicalSite(path, line_number, kind))
            for site_kind, pattern in _HEALTH_PATTERNS:
                if pattern.search(line):
                    sites.add(_LexicalSite(path, line_number, site_kind))
    return sites


def test_queue_inventory_is_independent_complete_and_not_seeded() -> None:
    module = _queue_module()
    source = _immutable_source(_MERGED, module.H9_SOURCE_PATHS)
    inventory = module.discover_queue_inventory(source)

    actual = {_LexicalSite(site.path, site.line, site.site_kind.value) for site in inventory.sites}
    assert actual == _lexical_inventory_oracle(source)
    assert inventory.expected_queue_count is None
    assert inventory.queue_count == len(inventory.queues) > 0
    assert inventory.queue_count == len({queue.queue_id for queue in inventory.queues})
    assert all(queue.constructor_declares_unbounded for queue in inventory.queues)
    assert all(queue.declared_bound == 0 for queue in inventory.queues)
    assert all(site.classification.value != "UNCLASSIFIED" for site in inventory.sites)


def test_queue_inventory_derives_receiver_names_instead_of_using_an_allowlist() -> None:
    module = _queue_module()
    source = SourceTree({
        "src/example.py": (
            "import queue\n\n"
            "def exercise() -> None:\n"
            "    renamed_work: queue.Queue[int] = queue.Queue(maxsize=3)\n"
            "    renamed_work.put(1)\n"
            "    renamed_work.get()\n"
        ),
    })

    inventory = module.discover_queue_inventory(source)

    assert inventory.queue_count == 1
    assert inventory.queues[0].queue_ref == "renamed_work"
    assert inventory.queues[0].constructor_policy.value == "DECLARED_BOUNDED"
    assert inventory.queues[0].producer_lines == (5,)
    assert inventory.queues[0].consumer_lines == (6,)


def test_queue_policy_classifier_separates_probe_evidence_and_explicit_policy() -> None:
    module = _queue_module()

    assert module.classify_admission_behavior(
        constructor_policy=module.ConstructorPolicy.UNKNOWN,
        accepted_count=10_000,
        attempted_count=10_000,
        elapsed_ms=1.0,
        explicit_timeout_seconds=None,
        observed_outcome=module.AdmissionOutcome.ACCEPTED,
    ) is module.QueueInference.NO_OBSERVED_BOUND_BELOW_10000
    assert module.classify_admission_behavior(
        constructor_policy=module.ConstructorPolicy.DECLARED_UNBOUNDED,
        accepted_count=10_000,
        attempted_count=10_000,
        elapsed_ms=1.0,
        explicit_timeout_seconds=None,
        observed_outcome=module.AdmissionOutcome.ACCEPTED,
    ) is module.QueueInference.DECLARED_UNBOUNDED
    assert module.classify_admission_behavior(
        constructor_policy=module.ConstructorPolicy.DECLARED_BOUNDED,
        accepted_count=1,
        attempted_count=2,
        elapsed_ms=101.0,
        explicit_timeout_seconds=0.2,
        observed_outcome=module.AdmissionOutcome.BLOCKED,
    ) is module.QueueInference.BLOCKING_WITH_POLICY
    assert module.classify_admission_behavior(
        constructor_policy=module.ConstructorPolicy.DECLARED_BOUNDED,
        accepted_count=1,
        attempted_count=2,
        elapsed_ms=101.0,
        explicit_timeout_seconds=None,
        observed_outcome=module.AdmissionOutcome.BLOCKED,
    ) is module.QueueInference.BLOCKING_WITHOUT_POLICY


def test_queue_policy_cross_checks_constructor_and_10000_admissions() -> None:
    module = _queue_module()
    inventory = module.discover_queue_inventory(
        _immutable_source(_MERGED, module.H9_SOURCE_PATHS)
    )
    observations = module.queue_admission_observations(
        inventory=inventory,
        admission_count=10_000,
    )

    assert len(observations) == inventory.queue_count * 10_000
    assert Counter(row.queue_id for row in observations) == {
        queue.queue_id: 10_000 for queue in inventory.queues
    }
    assert {row.observed_outcome.value for row in observations} == {"ACCEPTED"}
    assert {row.inference.value for row in observations} == {"DECLARED_UNBOUNDED"}
    assert all(row.constructor_policy.value == "DECLARED_UNBOUNDED" for row in observations)
    assert all(row.complete for row in observations)
    assert {row.elapsed_class.value for row in observations} == {"WITHIN_100MS"}
    assert {row.elapsed_threshold_ms for row in observations} == {100.0}


def test_connection_health_probe_and_pool_ownership_are_classified() -> None:
    module = _queue_module()
    inventory = module.discover_queue_inventory(
        _immutable_source(_MERGED, module.H9_SOURCE_PATHS)
    )
    observations = module.connection_health_observations(inventory=inventory)

    assert {row.scenario.value for row in observations} == {
        "HEALTHY", "OS_ERROR", "REDIS_TIMEOUT", "UNEXPECTED_ERROR"
    }
    assert {row.outcome.value for row in observations} == {
        "HEALTHY", "CONNECTION_FAILURE", "UNEXPECTED_PROPAGATED"
    }
    assert all(row.deadline_policy.value == "CONNECT_ONLY" for row in observations)
    assert all(row.pool_ownership.value == "RUNTIME_OWNED_CLIENT_THEN_POOL" for row in observations)
    assert all(row.complete for row in observations)


def test_health_deadline_scope_out_has_health_specific_reason_and_gate() -> None:
    module = _queue_module()
    record = module._record(
        _immutable_source(_MERGED, module.H9_SOURCE_PATHS),
        _MERGED,
        _OVERLAY,
    )
    assessment = next(
        item for item in record.health_observations.coverage_assessments
        if item.field_name == "deadline_policy"
    )

    assert "Redis health" in (assessment.reason or "")
    assert assessment.next_gate == "G4 health-deadline reachability assessment"
    ownership = next(
        item for item in record.health_observations.coverage_assessments
        if item.field_name == "pool_ownership"
    )
    assert ownership.status.value == "SCOPED_OUT"
    assert ownership.missing_values
    assert "ownership" in (ownership.reason or "").lower()
    assert ownership.next_gate == "G4 pool-ownership reachability assessment"


def test_h9_artifact_recomputes_cost_coverage_and_findings(tmp_path: Path) -> None:
    module = _queue_module()
    artifact = module.build_h9_audit_artifact(
        merged=_cumulative_source(_MERGED, module.H9_SOURCE_PATHS),
        overlay=_cumulative_source(_OVERLAY, module.H9_SOURCE_PATHS),
        merged_commit=_MERGED,
        overlay_commit=_OVERLAY,
    )
    payload = artifact.to_dict()
    assert AuditArtifact.from_dict(payload).to_dict() == payload
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(payload)) == []

    records = {record["hypothesis_id"]: record for record in payload["evidence_records"]}
    assert set(records) == {"H3", "H4", "H5", "H6", "H7", "H8", "H9"}
    h9 = records["H9"]
    assert h9["reviewer_status"] == "PENDING_G2"
    assert h9["inventory"]["expected_queue_count"] is None
    assert h9["inventory"]["queue_count"] == payload["discovered_multipliers"]["queues"]
    assert payload["computed_run_cost"]["queue_admissions"] == h9["inventory"]["queue_count"] * 10_000
    assert h9["admission_observations"]["total_observation_count"] == h9["inventory"]["queue_count"] * 10_000

    for summary_name in ("admission_observations", "health_observations"):
        summary = h9[summary_name]
        assert summary["observation_closure_status"] == "FULLY_STRUCTURALLY_CLOSED"
        for assessment in summary["coverage_assessments"]:
            observed = sorted({row[assessment["field_name"]] for row in summary["rows"]})
            missing = sorted(set(assessment["vocabulary_values"]) - set(observed))
            assert assessment["observed_values"] == observed
            assert assessment["missing_values"] == missing
            assert assessment["status"] == ("SCOPED_OUT" if missing else "FULLY_OBSERVED")
            if missing:
                assert assessment["reason"] and assessment["owner"] and assessment["next_gate"]

    h9_findings = [item for item in payload["findings"] if item["finding_id"].startswith("H9-")]
    assert {item["finding_id"] for item in h9_findings} == {
        "H9-MISSING-QUEUE-BACKPRESSURE-merged",
        "H9-MISSING-HEALTH-DEADLINE-merged",
    }
    assert all(item["classification"] == "MISSING" for item in h9_findings)

    artifact_path = tmp_path / "task9-artifact.json"
    artifact_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 0

    changed = json.loads(artifact_path.read_text(encoding="utf-8"))
    changed_h9 = next(record for record in changed["evidence_records"] if record["hypothesis_id"] == "H9")
    changed_h9["inventory"]["expected_queue_count"] = 1
    artifact_path.write_text(json.dumps(changed, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    assert main(["verify", "--artifact", str(artifact_path)]) == 1
