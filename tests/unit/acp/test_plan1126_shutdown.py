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
from tools.plan1126_runtime_audit.source import (
    ExecutingSourceMismatch,
    GitCommitSource,
    SourceTree,
)

_MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - Historical commit-identity pin in _MERGED;
_OVERLAY = "fac32284888850bacde93815265cbabe3afd4663"  # pragma: allowlist secret - Historical commit-identity pin in _OVERLAY;
_SCHEMA_PATH = Path("tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json")
_CAUSES = {
    "orderly_eof",
    "request_cancellation",
    "transport_failure",
    "server_cancellation",
    "partial_startup_failure",
}


def _sealed_replay():
    """Every family's sealed observations. The builders replay these; they measure nothing."""
    import json as _json

    from tools.plan1126_runtime_audit.replay import SealedObservations

    root = Path(__file__).resolve().parents[3]
    payload = _json.loads(
        (root / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(encoding="utf-8")
    )
    return SealedObservations.from_sealed(payload)


def _shutdown_module():
    try:
        return importlib.import_module("tools.plan1126_runtime_audit.shutdown")
    except ModuleNotFoundError:
        pytest.fail("Task 6 shutdown audit module does not exist")


def _immutable_source(commit: str, paths: tuple[str, ...]) -> SourceTree:
    source = GitCommitSource(commit)
    return SourceTree({path: source.read_text(path) for path in paths})


def _current_source(paths: tuple[str, ...]) -> SourceTree:
    """The tree the installed package is actually running from.

    Dynamic probes import the installed modules, so a fresh measurement is evidence
    about THIS source. Binding the schedule to it is what stops a current measurement
    being filed under a historical revision; `_immutable_source` remains the binding
    for the static discovery those historical findings rest on.
    """
    root = Path(__file__).resolve().parents[3]
    return SourceTree({path: (root / path).read_text(encoding="utf-8") for path in paths})


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
    r"^\s*(?:async\s+)?def\s+(?P<name>close|aclose|close_all|close_and_join|close_async|stop|shutdown_background_loop)\s*\("
)
_CLOSE_CALL = re.compile(
    r"\b(?P<reference>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\."
    r"(?:close|aclose|close_all|close_and_join|close_async|stop|terminate|kill|cancel|release|join))\s*\("
)
_INLINE_CONSTRUCTOR_CLOSE = re.compile(
    r"\b(?P<owner>[A-Z][A-Za-z0-9_]*)\([^\n]*\)\."
    r"(?P<leaf>close|aclose|close_all|close_and_join|close_async|stop)\s*\("
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


def _identity_tree(source, bound):
    """Bound text for every module whose execution is claimed, measured tree or on disk.

    The audit's own probe implementations are executing code too, so they are bound
    alongside the product modules; they simply do not live in the measured tree.
    """
    from tools.plan1126_runtime_audit.source import SourceTree

    root = Path(__file__).resolve().parents[3]
    held = set(source.paths())
    return SourceTree({
        path: (source.read_text(path) if path in held else (root / path).read_text(encoding="utf-8"))
        for path in held | set(bound)
    })


def _measured(paths=None, *, bound=None):
    """The measured tree, its specification and a captured ENVIRONMENT BINDING.

    A binding, deliberately -- not an execution context. A context authorizes probes and
    can only be issued inside a measurement child; the controls below that use this helper
    are about the binding itself (interpreter identity, dependency content, import roots),
    which authorizes nothing and needs no child.
    """
    from tools.plan1126_runtime_audit.measurement import (
        MeasurementSpecification,
        capture_environment_binding,
    )
    from tools.plan1126_runtime_audit.source import source_fingerprint

    module = _shutdown_module()
    root = Path(__file__).resolve().parents[3]
    source = _current_source(paths or module.H5_SOURCE_PATHS)
    bound = bound or (
        "src/optimus/redis/async_bridge.py",
        "src/optimus/redis/runtime.py",
        "tools/plan1126_runtime_audit/measurement.py",
        "tools/plan1126_runtime_audit/shutdown.py",
    )
    spec = MeasurementSpecification(
        paths=bound,
        import_roots=(str(root / "src"), str(root)),
        dependencies=("redis",),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    return source, spec, capture_environment_binding(
        measured=source, identity=_identity_tree(source, bound), spec=spec, cache_prefix=None
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


def _sealed_payload():
    """The sealed accepted artifact -- the only legitimate source for replay."""
    return json.loads(
        (Path(__file__).resolve().parents[3] / "reports" / "plan-11-26-acp-runtime-audit.json").read_text(
            encoding="utf-8"
        )
    )


def _sealed_observations():
    module = _shutdown_module()
    return module.replayed_shutdown_observations(_sealed_payload())


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
    # Through the REAL public path: a fresh child issues a context scoped to this entry,
    # and the entry discovers its inventory from the same tree the binding names. There is
    # no in-process route to these observations any more, which is the correction.
    inventory, observations = _measure_entry("h5.shutdown_schedule", repeats=100)
    applicable = {
        record["close_path_id"] for record in inventory["resources"] if record["schedule_applicable"]
    }

    assert len(observations) == len(applicable) * len(_CAUSES) * 100
    assert {item["terminal_cause"] for item in observations} == _CAUSES
    assert {item["close_path_id"] for item in observations} == applicable
    assert all(item["complete"] for item in observations)
    assert all(item["close_invocation_count"] == 3 for item in observations)
    assert all(item["control_thread_names"] for item in observations)
    assert all(not item["unexpected_persistent_threads"] for item in observations)
    assert all(not item["unexpected_persistent_tasks"] for item in observations)
    assert all("probe_error" not in item["cause_effect"] for item in observations)
    assert all(item["repeat_latency_class"] in {"WITHIN_100MS", "ABOVE_100MS"} for item in observations)

    by_family: dict[tuple[str, str], int] = {}
    for item in observations:
        key = (item["close_path_id"], item["terminal_cause"])
        by_family[key] = by_family.get(key, 0) + 1
    assert set(by_family) == {(path, cause) for path in applicable for cause in _CAUSES}
    assert set(by_family.values()) == {100}


def test_close_is_idempotent_across_discovered_paths() -> None:
    inventory, observations = _measure_entry("h5.shutdown_schedule", repeats=1)
    applicable = {
        record["close_path_id"] for record in inventory["resources"] if record["schedule_applicable"]
    }
    assert {(item["close_path_id"], item["terminal_cause"]) for item in observations} == {
        (path, cause) for path in applicable for cause in _CAUSES
    }
    for item in observations:
        assert item["close_invocation_count"] == 3
        assert item["underlying_close_count"] <= 1 or item["close_outcome"] in {"DOUBLE_CLOSE_OBSERVED", "ERROR"}
        assert item["close_outcome"] in {"CLOSED_ONCE", "IDEMPOTENT_NOOP", "DOUBLE_CLOSE_OBSERVED", "ERROR"}


def test_h5_artifact_derives_s1_cost_coverage_and_scope_out_register(tmp_path: Path) -> None:
    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    artifact = module.build_h5_audit_artifact(replay=_sealed_replay(),
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
    assert all(entry["reachable_in_gate"] == "NOT_YET_ASSESSED" for entry in register)
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
    changed["scope_out_register"][0]["reachable_in_gate"] = "yes"
    with pytest.raises(ValueError):
        AuditArtifact.from_dict(changed)


def test_dynamic_probe_refuses_a_source_binding_it_is_not_executing() -> None:
    """MUTATION: wrong runtime/source binding.

    The probes read immutable trees but import the installed package. On main those
    two happened to agree byte-for-byte, so the combination was only accidentally
    sound; any change to the Redis runtime breaks that coincidence. A mismatch must
    fail explicitly -- never skip, never downgrade to a success.
    """
    module = _shutdown_module()
    # Run in a measurement child with a genuine, correctly scoped H5 context, because the
    # question is whether a REAL context still refuses a source it is not executing.
    # Deliberately built from the CURRENT tree: this control is about the executing-source
    # gate alone, and binding it to `_OVERLAY` would make it UNRUN in any clone where that
    # unreachable commit is absent -- which is exactly the situation this lane is in.
    outcome = _child_case("h5_tampered_source")
    assert outcome["probe_calls"] == 0, "a probe ran against a source the binding does not name"
    assert "does not match the environment binding" in outcome["refusal"]

    measured, _spec, _binding = _measured(module.H5_SOURCE_PATHS)
    inventory = module.discover_shutdown_inventory(measured, overlay=measured)
    with pytest.raises(TypeError):
        module.shutdown_schedule_observations(inventory=inventory, repeats=1, source=measured)


def test_bridge_probe_oracle_is_owner_identity_not_a_thread_name() -> None:
    """MUTATION: a live owner hidden by the old name oracle.

    The previous oracle answered "did the bridge stop?" by asking whether ANY thread in
    the process still carried a hard-coded name. A decoy thread with that name makes it
    answer wrongly while the real owner has genuinely terminated.
    """
    import threading

    module = _shutdown_module()
    paths = module.H5_SOURCE_PATHS
    inventory = module.discover_shutdown_inventory(
        _current_source(paths), overlay=_current_source(paths)
    )
    record = next(
        item for item in inventory.resources
        if item.resource_type == "async_bridge" and item.schedule_applicable
    )

    release = threading.Event()
    decoy = threading.Thread(target=release.wait, name="optimus-redis-async", daemon=True)
    decoy.start()
    try:
        count, cause_effect = module._probe_resource(  # noqa: SLF001 - the oracle is the subject
            record, "orderly_eof", source=_current_source(paths)
        )
        assert decoy.is_alive()
        assert count == 1, "the probe failed to observe its own owner's termination"
        assert cause_effect.endswith("bridge_loop_stopped")
    finally:
        release.set()
        decoy.join(5)


def test_a_historical_inventory_with_a_current_measurement_is_refused() -> None:
    """MUTATION: wrong inventory/source pairing at the schedule."""
    outcome = _child_case("h5_historical_inventory")
    assert outcome["probe_calls"] == 0, "a probe ran against a contract discovered elsewhere"
    assert "discovered from a different tree" in outcome["refusal"]
    assert "sealed observations" in outcome["refusal"]


def test_an_environment_binding_detects_a_modified_same_version_dependency() -> None:
    """A version string cannot see an edited dependency; installed-file content can."""
    from dataclasses import replace

    from tools.plan1126_runtime_audit.measurement import verify_environment_binding

    _source, spec, binding = _measured()
    assert binding.dependency_files, "the binding must pin dependency file contents"
    tampered = replace(
        binding,
        dependency_files=tuple((name, "0" * 64) for name, _ in binding.dependency_files),
    )
    with pytest.raises(ExecutingSourceMismatch, match="installed files changed"):
        verify_environment_binding(tampered, spec)


def test_an_environment_binding_detects_a_substituted_interpreter() -> None:
    """The interpreter fields are verified, not merely recorded."""
    from dataclasses import replace

    from tools.plan1126_runtime_audit.measurement import verify_environment_binding

    _source, spec, binding = _measured()
    with pytest.raises(ExecutingSourceMismatch, match="different interpreter"):
        verify_environment_binding(replace(binding, interpreter_executable="C:/not/the/one.exe"), spec)
    with pytest.raises(ExecutingSourceMismatch, match="different interpreter version"):
        verify_environment_binding(replace(binding, interpreter_version="not the running version"), spec)


def test_an_environment_binding_refuses_a_module_outside_the_declared_import_root() -> None:
    """Controlled import roots are enforced, not assumed."""
    from tools.plan1126_runtime_audit.measurement import (
        MeasurementSpecification,
        capture_environment_binding,
    )
    from tools.plan1126_runtime_audit.source import source_fingerprint

    source = _current_source(_shutdown_module().H5_SOURCE_PATHS)
    bound = ("src/optimus/redis/runtime.py",)
    spec = MeasurementSpecification(
        paths=bound,
        import_roots=(str(Path(__file__).resolve().parents[3] / "does-not-contain-it"),),
        dependencies=(),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    with pytest.raises(ExecutingSourceMismatch, match="outside every declared import root"):
        capture_environment_binding(
            measured=source, identity=_identity_tree(source, bound), spec=spec, cache_prefix=None
        )


def test_measurement_binding_digest_is_deterministic_and_content_only() -> None:
    """The digest canonicalizes the binding solely to hash it; nothing is retained."""
    _source, _spec, binding = _measured()

    assert binding.digest == binding.digest
    assert len(binding.digest) == 64 and all(ch in "0123456789abcdef" for ch in binding.digest)

    payload = binding.to_dict()
    assert set(payload) == {
        "interpreter_executable", "interpreter_version", "prefix",
        "source_fingerprint", "module_origins", "dependency_files",
    }
    for path, origin, digest in payload["module_origins"]:
        # Product modules and the audit's own probe implementations alike: the probe code
        # that executes is executing code, so the evidence names it too.
        assert path.startswith(("src/", "tools/"))
        assert Path(origin).is_absolute() and len(digest) == 64
    for name, digest in payload["dependency_files"]:
        assert name and len(digest) == 64
