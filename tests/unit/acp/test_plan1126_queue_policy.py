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


def _sealed_replay():
    """Every family's sealed observations. The builders replay these; they measure nothing."""
    import json as _json

    from tools.plan1126_runtime_audit.replay import SealedObservations

    root = Path(__file__).resolve().parents[3]
    payload = _json.loads(
        (root / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(encoding="utf-8")
    )
    return SealedObservations.from_sealed(payload)


def _queue_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.queue_policy")
    except ModuleNotFoundError:
        pytest.fail("Task 9 queue-policy audit module does not exist")


def _current_source(paths: tuple[str, ...]) -> SourceTree:
    """The tree the installed package is actually running from.

    Dynamic probes import the installed modules, so a fresh measurement is evidence
    about THIS source; `_immutable_source` remains the binding for static discovery of
    historical baselines.
    """
    root = Path(__file__).resolve().parents[3]
    return SourceTree({path: (root / path).read_text(encoding="utf-8") for path in paths})


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


def _measurement_binding():
    """The identity these tests state their fresh measurements are taken against."""
    from tools.plan1126_runtime_audit.shutdown import H5_SOURCE_PATHS, installed_source
    from tools.plan1126_runtime_audit.source import capture_measurement_binding

    return capture_measurement_binding(
        installed_source(H5_SOURCE_PATHS), H5_SOURCE_PATHS, dependencies=("redis",)
    )


def _measured_h9():
    """The measured H9 tree, its specification and a captured ENVIRONMENT BINDING.

    A binding, not an execution context: contexts authorize probes and are issued only
    inside a measurement child. The controls using this helper are about the binding.
    """
    from tools.plan1126_runtime_audit.measurement import (
        MeasurementSpecification,
        capture_environment_binding,
    )
    from tools.plan1126_runtime_audit.source import SourceTree, source_fingerprint

    module = _queue_module()
    root = Path(__file__).resolve().parents[3]
    source = _current_source(module.H9_SOURCE_PATHS)
    bound = (
        "src/optimus/redis/async_bridge.py",
        "src/optimus/redis/runtime.py",
        "tools/plan1126_runtime_audit/measurement.py",
        "tools/plan1126_runtime_audit/queue_policy.py",
    )
    held = set(source.paths())
    identity = SourceTree({
        path: (source.read_text(path) if path in held else (root / path).read_text(encoding="utf-8"))
        for path in held | set(bound)
    })
    spec = MeasurementSpecification(
        paths=bound,
        import_roots=(str(root / "src"), str(root)),
        dependencies=("redis",),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    return source, spec, capture_environment_binding(
        measured=source, identity=identity, spec=spec, cache_prefix=None
    )


#: Controls that must run inside a real measurement child live here; the pytest process
#: cannot issue an authorizing context, which is the whole point of the correction.
_CHILD_CASES = (
    Path(__file__).resolve().parents[3]
    / "tests" / "unit" / "tools" / "plan1126_runtime_audit" / "measurement_child_cases.py"
)


def _child_case(case: str) -> dict:
    """Run one control inside a measurement child and return its single JSON result."""
    import json
    import subprocess
    import sys
    import tempfile

    from tools.plan1126_runtime_audit.measurement import fresh_child_environment

    root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="plan1126-control-cache-") as cache:
        completed = subprocess.run(
            [sys.executable, str(_CHILD_CASES), str(root), case],
            cwd=str(root), capture_output=True, text=True, timeout=1800,
            env=fresh_child_environment(cache),
        )
    assert completed.returncode == 0, f"{case}: {completed.stderr[-2000:]}"
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _measure_entry(entry: str, **options) -> tuple[dict, list[dict]]:
    """Drive the REAL public measurement path and return (inventory, observations)."""
    from tools.plan1126_runtime_audit.current_envelope import default_measurement_plan
    from tools.plan1126_runtime_audit.measurement import run_fresh_measurement

    root = Path(__file__).resolve().parents[3]
    plan = default_measurement_plan(repository_root=root, entries=(entry,), options=options)[0]
    _binding, result = run_fresh_measurement(
        source=plan.source, spec=plan.spec, entry=entry,
        options=plan.options, repository_root=root,
    )
    return result["inventory"], result["observations"]


def _sealed_admission_observations():
    module = _queue_module()
    payload = json.loads(
        (Path(__file__).resolve().parents[3] / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(
            encoding="utf-8"
        )
    )
    return module.replayed_admission_observations(payload)


def _sealed_health_observations():
    module = _queue_module()
    payload = json.loads(
        (Path(__file__).resolve().parents[3] / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(
            encoding="utf-8"
        )
    )
    return module.replayed_health_observations(payload)


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
    # Through the REAL public path. A dynamic health measurement imports the INSTALLED
    # runtime, so it is evidence about the current tree; the entry discovers its inventory
    # from the same tree the binding names, which is what keeps it from being filed
    # against a historical revision.
    _inventory, observations = _measure_entry("h9.connection_health")

    assert {row["scenario"] for row in observations} == {
        "HEALTHY", "OS_ERROR", "REDIS_TIMEOUT", "UNEXPECTED_ERROR"
    }
    assert {row["outcome"] for row in observations} == {
        "HEALTHY", "CONNECTION_FAILURE", "UNEXPECTED_PROPAGATED"
    }
    assert all(row["deadline_policy"] == "CONNECT_ONLY" for row in observations)
    assert all(row["pool_ownership"] == "RUNTIME_OWNED_CLIENT_THEN_POOL" for row in observations)
    assert all(row["complete"] for row in observations)


def test_health_deadline_scope_out_has_health_specific_reason_and_gate() -> None:
    module = _queue_module()
    record = module._record(
        _current_source(module.H9_SOURCE_PATHS),
        _MERGED,
        _OVERLAY,
        _sealed_health_observations(),
        _sealed_admission_observations(),
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
    artifact = module.build_h9_audit_artifact(replay=_sealed_replay(),
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


# --- Review round 1: R5 audit-binding controls -----------------------------------


def test_h9_refuses_an_inventory_discovered_from_a_different_source() -> None:
    """MUTATION: wrong inventory/source pairing.

    Verifying that the executing modules match the supplied source is not enough on its
    own: the inventory describing the contract can still come from somewhere else, and
    the measurement would then be recorded against a contract it was never taken from.
    """
    outcome = _child_case("h9_foreign_inventory")
    assert outcome["probe_calls"] == 0, "a probe ran against a contract discovered elsewhere"
    assert "not discovered from the source" in outcome["refusal"]


def test_h9_refuses_to_measure_a_source_it_is_not_executing() -> None:
    """MUTATION: H9 measured against a source binding it is not executing."""
    outcome = _child_case("h9_tampered_source")
    assert outcome["probe_calls"] == 0, "a probe ran against a source the binding does not name"
    assert "does not match the environment binding" in outcome["refusal"]


def test_health_deadline_citations_keep_the_evidence_line_and_are_checked_against_it() -> None:
    """The citation must name the line that SHOWS the defect, and still land in its symbol.

    Round 3 re-resolved these to their definition lines by symbol identity. That looked
    like a correction and was a regression: the finding is about `socket_connect_timeout=2`,
    the bare `await client.ping()` and the bare `Future.result()` -- specific lines *inside*
    those definitions -- so moving each citation to the enclosing `def` discarded exactly
    the evidence being cited, and stopped the sealed artifact reproducing. These citations
    are bound to the MERGED baseline, where the code they name has not moved.
    """
    module = _queue_module()
    merged = _immutable_source(_MERGED, module.H9_SOURCE_PATHS)
    record = module._record(  # noqa: SLF001
        merged, _MERGED, _OVERLAY, _sealed_health_observations(), _sealed_admission_observations()
    )
    finding = next(
        item
        for item in module._findings(record, source=merged)  # noqa: SLF001
        if item.finding_id == "H9-MISSING-HEALTH-DEADLINE-merged"
    )

    assert finding.symbols == (
        "src/optimus/redis/runtime.py:28:RedisRuntime.from_url",
        "src/optimus/redis/runtime.py:44:RedisRuntime._ping_async",
        "src/optimus/redis/async_bridge.py:47:sync_await",
    )
    for citation, token in zip(
        finding.symbols, ("socket_connect_timeout", "client.ping", ".result("), strict=True
    ):
        path, line, _ = citation.split(":", 2)
        source_line = merged.read_text(path).splitlines()[int(line) - 1]
        assert token in source_line, f"citation {citation} no longer shows {token}"


def test_a_citation_that_leaves_its_symbol_fails_rather_than_keeping_a_stale_line() -> None:
    """MUTATION: a citation kept while the code it named moved away from that line."""
    from tools.plan1126_runtime_audit.source import (
        SourceTree,
        SymbolCitationError,
        resolve_symbol_citation,
        verify_symbol_citation,
    )

    inside = SourceTree({"a.py": "def wanted():\n    return 1\n"})
    assert verify_symbol_citation(inside, "a.py:2:wanted") == "a.py:2:wanted"

    shifted = SourceTree({"a.py": "x = 0\n\n\ndef wanted():\n    return 1\n"})
    with pytest.raises(SymbolCitationError, match="outside that symbol"):
        verify_symbol_citation(shifted, "a.py:2:wanted")

    missing = SourceTree({"a.py": "def other():\n    return None\n"})
    with pytest.raises(SymbolCitationError, match="not defined"):
        verify_symbol_citation(missing, "a.py:1:wanted")
    with pytest.raises(SymbolCitationError, match="not defined"):
        resolve_symbol_citation(missing, "a.py", "wanted")

    ambiguous = SourceTree({"a.py": "def wanted():\n    return 1\n\n\ndef wanted():\n    return 2\n"})
    with pytest.raises(SymbolCitationError, match="defined 2 times"):
        verify_symbol_citation(ambiguous, "a.py:1:wanted")
    with pytest.raises(SymbolCitationError, match="defined 2 times"):
        resolve_symbol_citation(ambiguous, "a.py", "wanted")


def test_the_bridge_wait_is_still_discovered_after_ownership_moved_it() -> None:
    """Owner code must not drop out of the declared corpus when the path moves."""
    module = _queue_module()
    inventory = module.discover_queue_inventory(_current_source(module.H9_SOURCE_PATHS))
    kinds = {site.site_kind.value for site in inventory.sites}
    assert "BRIDGE_WAIT" in kinds, "the bridge wait vanished from discovery when it moved"
    waits = [site for site in inventory.sites if site.site_kind.value == "BRIDGE_WAIT"]
    assert any(site.path == "src/optimus/redis/async_bridge.py" for site in waits)


def _sealed_shutdown_observations():
    from tools.plan1126_runtime_audit.shutdown import replayed_shutdown_observations

    payload = json.loads(
        (Path(__file__).resolve().parents[3] / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(
            encoding="utf-8"
        )
    )
    return replayed_shutdown_observations(payload)
