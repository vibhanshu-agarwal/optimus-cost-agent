"""The historical/current split, exercised through the paths a caller actually reaches.

Three behaviours are kept apart and tested apart: historical replay runs no probe, fresh
measurement runs in a verified child and retains what it measured, and a fresh
*historical* execution is refused rather than faked with the installed runtime.

Every counterexample that beat an earlier version of this machinery has a control here,
and each control asserts the thing that actually went wrong -- zero probe calls rather
than "an exception was raised", the executed marker rather than the file digest, a
reconstructed observation set rather than a digest compared with itself.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from tools.plan1126_runtime_audit import evidence_store, queue_policy, shutdown
from tools.plan1126_runtime_audit.current_envelope import (
    MeasurementPlan,
    build_successor_artifact,
    default_measurement_plan,
    measure_current,
    replay_sealed_artifact,
    verify_current_records,
)
from tools.plan1126_runtime_audit.evidence_store import (
    EvidenceCollisionError,
    RetainedEvidenceError,
    RetainedEvidenceReference,
    canonical_digest,
    derive_inventory_identifiers,
    verify_retained_evidence,
    write_evidence_sidecar,
)
from tools.plan1126_runtime_audit.measurement import (
    CACHE_PREFIX_VARIABLE,
    EnvironmentBinding,
    MeasurementSpecification,
    VerifiedExecution,
    capture_environment_binding,
    establish_verified_execution,
    fresh_child_environment,
    run_child_measurement,
    run_fresh_measurement,
    verify_dependency_integrity,
    verify_environment_binding,
)
from tools.plan1126_runtime_audit.model import (
    AUDIT_ARTIFACT_SCHEMA_V1,
    AUDIT_ARTIFACT_SCHEMA_V2,
    CURRENT_MEASUREMENT_SCHEMA_VERSION,
    AuditArtifact,
    CurrentMeasurementRecord,
)
from tools.plan1126_runtime_audit.source import ExecutingSourceMismatch, SourceTree, source_fingerprint

ROOT = Path(__file__).resolve().parents[4]
SEALED = ROOT / "reports" / "plan-11-26-acp-runtime-audit.json"
V1_SCHEMA = ROOT / "tests" / "fixtures" / "plan1126_runtime_audit" / "audit-artifact.schema.json"
V2_SCHEMA = ROOT / "tests" / "fixtures" / "plan1126_runtime_audit" / "audit-artifact-v2.schema.json"
CLI = ROOT / "tools" / "run_plan1126_runtime_audit.py"

_BRIDGE = "src/optimus/redis/async_bridge.py"
_RUNTIME = "src/optimus/redis/runtime.py"
_GATE = "tools/plan1126_runtime_audit/measurement.py"


def _tree(paths) -> SourceTree:
    return SourceTree({path: (ROOT / path).read_text(encoding="utf-8") for path in paths})


def _fabricated_binding() -> EnvironmentBinding:
    """Structurally valid, entirely invented. This is what once bought 65 probe calls."""
    return EnvironmentBinding(
        interpreter_executable="C:/not-the-running-interpreter/python.exe",
        interpreter_version="3.0 (fabricated)",
        prefix="C:/not-this-venv",
        source_fingerprint="a" * 64,
        module_origins=((("src/does/not/exist.py"), str(ROOT / "does" / "not" / "exist.py"), "b" * 64),),
        dependency_files=(),
    )


def _measure(entry: str, evidence_directory: Path, **options):
    plans = default_measurement_plan(repository_root=ROOT, entries=(entry,), options=options)
    return measure_current(
        plans=plans, repository_root=ROOT, evidence_directory=evidence_directory
    )


CHILD_CASES = ROOT / "tests" / "unit" / "tools" / "plan1126_runtime_audit" / "measurement_child_cases.py"


def _child_case(case: str) -> dict:
    """Run one authorization control inside a REAL measurement child.

    An authorizing context can only be issued inside one now, so a control about what a
    genuine context does and does not authorize has to run there. Running it here would
    only ever exercise the refusal to issue one, which is a different control.
    """
    with tempfile.TemporaryDirectory(prefix="plan1126-control-cache-") as cache:
        completed = subprocess.run(
            [sys.executable, str(CHILD_CASES), str(ROOT), case],
            cwd=str(ROOT), capture_output=True, text=True, timeout=1800,
            env=fresh_child_environment(cache),
        )
    assert completed.returncode == 0, f"{case}: {completed.stderr[-2000:]}"
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _seal_raw(directory: Path, record_id: str, payload: dict) -> RetainedEvidenceReference:
    """Put a payload on disk WITHOUT the writer's own consistency checks.

    The writer refuses an inventory whose identifiers disagree with it, so a control about
    what VERIFICATION does with such a payload has to place it by another route -- with
    every digest recomputed, or the digest checks fire first and the control proves nothing
    about derivation.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    location = f"{record_id}.{hashlib.sha256(encoded).hexdigest()[:32]}.evidence.json"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / location).write_bytes(encoded)
    return RetainedEvidenceReference(
        kind="sidecar",
        location=location,
        file_digest=hashlib.sha256(encoded).hexdigest(),
        inventory_digest=canonical_digest({
            "inventory": payload["inventory"],
            "inventory_identifiers": list(payload["inventory_identifiers"]),
        }),
        observation_digest=canonical_digest(payload["observations"]),
        observation_count=len(payload["observations"]),
    )


def _review_binding(*paths: str) -> dict:
    """A well-formed binding naming exactly ``paths`` as its executing modules.

    The bound-modules derivation reads the binding rather than the inventory, so a review
    fixture has to name the same modules on both sides -- as a real measurement does.
    """
    return {
        "interpreter_executable": "C:/python.exe",
        "interpreter_version": "3.14",
        "prefix": "C:/venv",
        "source_fingerprint": "a" * 64,
        "module_origins": [[path, str(ROOT / path), "b" * 64] for path in paths],
        "dependency_files": [],
    }


_REVIEW_BINDING = _review_binding("a.py")


# --- Historical replay ------------------------------------------------------------


def test_historical_replay_runs_zero_current_probes(monkeypatch) -> None:
    """Replay reads sealed evidence; it must not touch a current probe at all.

    This is what makes replay possible without the historical runtime: it re-states
    stored evidence rather than making a new execution claim.
    """

    def _forbidden(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("historical replay invoked a current probe")

    monkeypatch.setattr(shutdown, "shutdown_schedule_observations", _forbidden)
    monkeypatch.setattr(queue_policy, "connection_health_observations", _forbidden)

    artifact = replay_sealed_artifact(SEALED)

    assert artifact.schema_version == AUDIT_ARTIFACT_SCHEMA_V1
    assert artifact.evidence_records
    assert not artifact.current_measurement_records
    schema = json.loads(V1_SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(artifact.to_dict())) == []


# --- R5a: the claimed identity is enforced, not accepted --------------------------


def test_a_fabricated_binding_buys_zero_probe_calls(monkeypatch) -> None:
    """MUTATION: provenance downgraded to an argument the caller supplies.

    The reviewer's probe passed a well-shaped binding naming a wrong interpreter and a
    nonexistent module. H5 admitted 65 probe calls and returned 65 observations. The
    assertion that matters is not that an exception was raised -- it is that nothing ran.
    """
    h5_calls: list[object] = []
    h9_calls: list[object] = []
    monkeypatch.setattr(shutdown, "_probe_resource", lambda *a, **k: h5_calls.append(a))
    monkeypatch.setattr(queue_policy, "RedisRuntime", lambda *a, **k: h9_calls.append(a))

    source = _tree(shutdown.H5_SOURCE_PATHS)
    inventory = shutdown.discover_shutdown_inventory(source, overlay=source)
    fabricated = _fabricated_binding()

    for impostor in (fabricated, SimpleNamespace(binding=fabricated)):
        with pytest.raises(ExecutingSourceMismatch, match="verified execution context"):
            shutdown.shutdown_schedule_observations(
                inventory=inventory, repeats=1, source=source, execution=impostor
            )

    queue_source = _tree(queue_policy.H9_SOURCE_PATHS)
    queue_inventory = queue_policy.discover_queue_inventory(queue_source)
    for impostor in (fabricated, SimpleNamespace(binding=fabricated)):
        with pytest.raises(ExecutingSourceMismatch, match="verified execution context"):
            queue_policy.connection_health_observations(
                inventory=queue_inventory, source=queue_source, execution=impostor
            )

    assert h5_calls == [], "a fabricated binding reached the H5 probes"
    assert h9_calls == [], "a fabricated binding reached the H9 probes"


def test_a_verified_execution_cannot_be_constructed_directly() -> None:
    """The context is minted by the verification, so it cannot be manufactured."""
    spec = MeasurementSpecification(
        paths=(_GATE,), import_roots=(str(ROOT),), dependencies=(),
        source_fingerprint="a" * 64,
    )
    with pytest.raises(ExecutingSourceMismatch, match="cannot be constructed directly"):
        VerifiedExecution(_fabricated_binding(), spec, "h5.shutdown_schedule", "C:/cache")


def test_a_context_cannot_be_copied_into_a_different_shape() -> None:
    """MUTATION: `dataclasses.replace` re-badging a context for another entry.

    Not reflection and not a forged object: `replace` is a documented public API on every
    dataclass, so a shared mint sentinel would let a genuine H9 context become an "H5"
    context with nothing verified for H5. The token is single-use, so the copy has nothing
    to present.
    """
    from dataclasses import replace

    outcome = _child_case("replace_rebadges_the_context")
    assert outcome["replace_refused"] is True, outcome
    assert "cannot be constructed directly" in outcome["refusal"]
    del replace


def test_the_issuer_refuses_to_mint_outside_a_measurement_child(monkeypatch) -> None:
    """MUTATION: a GENUINE context, issued anywhere, authorizing anything.

    This is the counterexample that survived the previous round. No forged object, no
    private token, no reflection: the documented public issuer was asked for a context
    from a caller-chosen specification binding one unrelated module, and the H5 schedule
    accepted it for 65 probe calls. The issuer now demands the entry name, applies that
    entry's requirements itself, and requires the private empty bytecode cache that only
    a measurement child has -- so there is no route to an authorizing context from here.
    """
    calls: list[object] = []
    monkeypatch.setattr(shutdown, "_probe_resource", lambda *a, **k: calls.append(a))

    source = _tree(shutdown.H5_SOURCE_PATHS)
    under_scoped = MeasurementSpecification(
        paths=("tools/plan1126_runtime_audit/source.py",),
        import_roots=(str(ROOT),),
        dependencies=(),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    with pytest.raises(ExecutingSourceMismatch, match="private bytecode cache"):
        establish_verified_execution(
            entry=shutdown.H5_MEASUREMENT_ENTRY,
            measured=source,
            identity=_tree(("tools/plan1126_runtime_audit/source.py",)),
            spec=under_scoped,
        )
    assert calls == [], "a refused mint still reached the probes"


def test_an_under_scoped_specification_is_widened_by_the_issuer() -> None:
    """A caller cannot choose how little its context means.

    Inside a child the same under-scoped request succeeds -- but only because the issuer
    raised it to what H5 actually executes. The bound set is the assertion; a green run is
    not.
    """
    outcome = _child_case("underscoped_specification")
    assert outcome["refusal"] is None, outcome
    # Not just the modules H5 is ABOUT: everything `_probe_resource` imports and runs.
    # Binding only the subject leaves the rest of what executes unbound, which is the same
    # gap one level down.
    assert set(outcome["bound_modules"]) >= {
        _BRIDGE, _RUNTIME, _GATE, "tools/plan1126_runtime_audit/shutdown.py",
        "src/optimus/acp/local_infra.py", "src/optimus/acp/outbound_writer.py",
        "src/optimus/acp/spec.py", "src/optimus/mcp/client_disposition.py",
        "src/optimus/mcp/client_sdk.py", "src/optimus/mcp/client_supervisor.py",
        "src/optimus/mcp/local_ipc.py", "src/optimus/redis/__init__.py",
    }
    assert outcome["dependencies"] == ["redis"]
    # Every applicable close path under every terminal cause, once: derived from the tree
    # this child measured rather than pinned as a literal, so a new owner close path (Seam
    # 2, checkpoint B added three) raises the expectation with the inventory.
    applicable = sum(
        record.schedule_applicable
        for record in shutdown.discover_shutdown_inventory(_tree(shutdown.H5_CURRENT_SOURCE_PATHS)).resources
    )
    assert applicable >= 13
    assert outcome["probe_calls"] == applicable * len(shutdown._TERMINAL_CAUSES)


def test_a_context_issued_for_another_entry_authorizes_nothing() -> None:
    """MUTATION: one entry's verification standing in for another's."""
    outcome = _child_case("context_for_another_entry")
    assert outcome["issued_for"] == "h9.connection_health"
    assert outcome["probe_calls"] == 0, "an H9 context reached the H5 probes"
    assert "does not authorize" in outcome["refusal"]


def test_an_h5_context_does_not_authorize_h9_either() -> None:
    """The scope check exists on BOTH entries, not just the one the reviewer probed."""
    outcome = _child_case("h5_context_at_h9")
    assert outcome["issued_for"] == "h5.shutdown_schedule"
    assert outcome["probe_calls"] == 0, "an H5 context reached the H9 probes"
    assert "does not authorize" in outcome["refusal"]


def test_a_probe_internal_source_mismatch_is_raised_not_recorded() -> None:
    """MUTATION: a refusal downgraded into a `probe_error` observation.

    `_probe_resource` verifies each module it is about to execute, and the schedule's
    per-probe `except Exception` used to swallow that refusal into a row. The result was a
    schedule that looked measured while recording that the measurement had been refused --
    the exact downgrade the function's own docstring says never happens.
    """
    outcome = _child_case("probe_internal_mismatch")
    assert outcome["raised"] is True, "a source mismatch was recorded as an observation"
    assert outcome["probe_error_rows"] == 0
    assert "control marker" in outcome["refusal"]


def test_historical_replay_executes_no_h9_admission_probe() -> None:
    """MUTATION: `_record` calling itself replay-only while re-running 30,000 admissions.

    Rebuilding the historical H9 record re-executed the live admission probe on every
    `verify` of the accepted artifact. Replacing the probe with a hard failure is the only
    assertion that can tell a replay from a re-measurement.
    """
    from tools.plan1126_runtime_audit import queue_policy as module
    from tools.run_plan1126_runtime_audit import main

    original = module.queue_admission_observations

    def forbidden(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("historical replay executed a live admission probe")

    module.queue_admission_observations = forbidden
    try:
        assert main(["verify", "--artifact", str(SEALED)]) == 0
    finally:
        module.queue_admission_observations = original


def test_a_truncated_measured_tree_is_refused() -> None:
    """MUTATION: the entry's requirements bounding what is BOUND but not what is MEASURED.

    The entry re-discovers its contract from the supplied tree, so a truncated one yields a
    smaller contract that is internally consistent and quietly incomplete.
    """
    full = queue_policy.H9_SOURCE_PATHS
    truncated = _tree(full[:2])
    spec = MeasurementSpecification(
        paths=(_GATE,), import_roots=(str(ROOT / "src"), str(ROOT)),
        dependencies=(), source_fingerprint=source_fingerprint(truncated, truncated.paths()),
    )
    with pytest.raises(ExecutingSourceMismatch, match="omits paths"):
        run_fresh_measurement(
            source=truncated, spec=spec, entry="h9.connection_health",
            options={}, repository_root=ROOT,
        )


def test_a_context_whose_measurement_window_closed_authorizes_nothing() -> None:
    """MUTATION: a context outliving the measurement that issued it."""
    outcome = _child_case("closed_window")
    assert outcome["probe_calls"] == 0, "a closed context reached the probes"
    assert "window" in outcome["refusal"]


def test_a_missing_execution_context_fails_before_any_observation() -> None:
    """There is no unbound path: the argument is required, not defaulted."""
    source = _tree(shutdown.H5_SOURCE_PATHS)
    inventory = shutdown.discover_shutdown_inventory(source, overlay=source)
    with pytest.raises(TypeError):
        shutdown.shutdown_schedule_observations(inventory=inventory, repeats=1, source=source)

    queue_source = _tree(queue_policy.H9_SOURCE_PATHS)
    with pytest.raises(TypeError):
        queue_policy.connection_health_observations(
            inventory=queue_policy.discover_queue_inventory(queue_source), source=queue_source
        )


def test_an_entry_binds_its_own_runtime_even_when_the_caller_omits_it() -> None:
    """MUTATION: the caller chooses how little the evidence means.

    Codex ran the public H9 child with one harmless module bound and no Redis dependency
    at all, and it succeeded. The entry's requirements are a floor now.
    """
    source = _tree(queue_policy.H9_SOURCE_PATHS)
    minimal = MeasurementSpecification(
        paths=(_GATE,),
        import_roots=(str(ROOT / "src"), str(ROOT)),
        dependencies=(),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    binding, result = run_fresh_measurement(
        source=source, spec=minimal, entry="h9.connection_health",
        options={}, repository_root=ROOT,
    )

    bound = {path for path, _, _ in binding.module_origins}
    assert {_BRIDGE, _RUNTIME, _GATE, "tools/plan1126_runtime_audit/queue_policy.py"} <= bound
    assert [name for name, _ in binding.dependency_files] == ["redis"]
    assert result["observations"], "the entry produced no observations"


def test_the_fresh_child_executes_verified_source_not_stale_bytecode(tmp_path) -> None:
    """MUTATION: a fresh process assumed to imply fresh source.

    The reviewer compiled a module, replaced its text with an equal-length edit and
    restored the timestamp; the binding attested to the new file while the child executed
    the old bytecode. `-B` does not help: it prevents bytecode being written, not read.
    """
    root = tmp_path / "staleroot"
    root.mkdir()
    module_path = root / "plan1126_stale_probe.py"
    module_path.write_text('PLAN1126_STALE_MARKER = "old"\n', encoding="utf-8")
    py_compile.compile(str(module_path), doraise=True)
    stat = module_path.stat()
    module_path.write_text('PLAN1126_STALE_MARKER = "new"\n', encoding="utf-8")
    os.utime(module_path, (stat.st_atime, stat.st_mtime))

    # The trap is real: an ordinary fresh interpreter executes the OLD text.
    plain = subprocess.run(
        [sys.executable, "-c", "import plan1126_stale_probe as m; print(m.PLAN1126_STALE_MARKER)"],
        cwd=root, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", CACHE_PREFIX_VARIABLE: ""},
    )
    assert plain.stdout.strip() == "old", (
        "the stale-bytecode trap did not reproduce, so this control proves nothing"
    )

    source = SourceTree({"plan1126_stale_probe.py": module_path.read_text(encoding="utf-8")})
    spec = MeasurementSpecification(
        paths=("plan1126_stale_probe.py",),
        import_roots=(str(root),),
        dependencies=(),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    _binding, result = run_fresh_measurement(
        source=source, spec=spec, entry="identity.echo_bound_modules",
        options={}, repository_root=ROOT,
    )
    row = next(
        item for item in result["observations"]
        if item["observation_id"] == "plan1126_stale_probe.py"
    )
    assert row["constants"]["PLAN1126_STALE_MARKER"] == "new", (
        "the verified child executed cached bytecode compiled from source it did not bind"
    )
    assert row["cached_under_private_prefix"] is True, (
        "the module was loaded from a bytecode cache this measurement did not create"
    )


def test_the_child_refuses_to_measure_without_a_private_bytecode_cache(monkeypatch) -> None:
    """The defence fails closed: no private cache means no measurement."""
    monkeypatch.delenv(CACHE_PREFIX_VARIABLE, raising=False)
    with pytest.raises(ExecutingSourceMismatch, match="private bytecode cache"):
        run_child_measurement({
            "entry": "identity.echo_bound_modules",
            "spec": MeasurementSpecification(
                paths=(_GATE,), import_roots=(str(ROOT),), dependencies=(),
                source_fingerprint=source_fingerprint(SourceTree({}), ()),
            ).to_dict(),
            "source_files": {},
            "identity_files": {_GATE: (ROOT / _GATE).read_text(encoding="utf-8")},
            "options": {},
            "repository_root": str(ROOT),
        })


def test_an_unknown_measurement_entry_is_refused() -> None:
    """The child executes an allowlist, not an arbitrary importable name."""
    source = _tree(queue_policy.H9_SOURCE_PATHS)
    spec = MeasurementSpecification(
        paths=(_GATE,), import_roots=(str(ROOT),), dependencies=(),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    with pytest.raises(ValueError, match="not an allowlisted measurement entry"):
        run_fresh_measurement(
            source=source, spec=spec, entry="os.system", options={}, repository_root=ROOT
        )


# --- R5b: dependency integrity is validated, not described ------------------------


def _install_synthetic_distribution(directory: Path, *, body: str = "VALUE = 1\n") -> str:
    """A throwaway distribution with a real RECORD, so no installed package is touched."""
    module = directory / "plan1126_faux_module.py"
    module.write_text(body, encoding="utf-8")
    digest = base64.urlsafe_b64encode(hashlib.sha256(module.read_bytes()).digest()).decode().rstrip("=")
    info = directory / "plan1126_faux-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: plan1126-faux\nVersion: 1.0\n", encoding="utf-8"
    )
    (info / "RECORD").write_text(
        f"plan1126_faux_module.py,sha256={digest},{module.stat().st_size}\n"
        "plan1126_faux-1.0.dist-info/METADATA,,\n"
        "plan1126_faux-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    return "plan1126-faux"


@pytest.fixture()
def synthetic_distribution(tmp_path, monkeypatch):
    directory = tmp_path / "site"
    directory.mkdir()
    name = _install_synthetic_distribution(directory)
    monkeypatch.syspath_prepend(str(directory))
    importlib.invalidate_caches()
    yield name, directory / "plan1126_faux_module.py"
    sys.modules.pop("plan1126_faux_module", None)
    importlib.invalidate_caches()


def test_a_dependency_matching_its_record_binds_its_content(synthetic_distribution) -> None:
    name, _module = synthetic_distribution
    assert len(verify_dependency_integrity(name)) == 64


def test_a_dependency_modified_before_capture_is_refused(synthetic_distribution) -> None:
    """MUTATION: hashing damage instead of rejecting it.

    Capture-then-compare only detects change DURING a run. A file already edited before
    capture was previously folded into the digest as though it were intact.
    """
    name, module = synthetic_distribution
    module.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(ExecutingSourceMismatch, match="does not match its RECORD hash"):
        verify_dependency_integrity(name)


def test_a_dependency_missing_a_recorded_file_is_refused(synthetic_distribution) -> None:
    """MUTATION: an absent file encoded as a placeholder rather than refused."""
    name, module = synthetic_distribution
    module.unlink()
    with pytest.raises(ExecutingSourceMismatch, match="missing the installed file"):
        verify_dependency_integrity(name)


def test_a_dependency_edited_during_execution_is_refused(synthetic_distribution) -> None:
    """The binding is re-verified after the probes, not only captured before them."""
    name, module = synthetic_distribution
    source = SourceTree({"plan1126_faux_module.py": module.read_text(encoding="utf-8")})
    spec = MeasurementSpecification(
        paths=("plan1126_faux_module.py",),
        import_roots=(str(module.parent),),
        dependencies=(name,),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    binding = capture_environment_binding(
        measured=source, identity=source, spec=spec, cache_prefix=None
    )

    module.write_text("VALUE = 3\n", encoding="utf-8")
    with pytest.raises(ExecutingSourceMismatch):
        verify_environment_binding(binding, spec)


def test_a_dependency_the_specification_names_must_be_installed() -> None:
    """Identity that cannot be established is a refusal, never a downgrade."""
    source = _tree(queue_policy.H9_SOURCE_PATHS)
    spec = MeasurementSpecification(
        paths=(_GATE,),
        import_roots=(str(ROOT),),
        dependencies=("this-distribution-does-not-exist",),
        source_fingerprint=source_fingerprint(source, source.paths()),
    )
    with pytest.raises(ExecutingSourceMismatch, match="not installed"):
        capture_environment_binding(
            measured=source, identity=_tree((_GATE,)), spec=spec, cache_prefix=None
        )


# --- R5c: the evidence is retained, not hashed away -------------------------------


def test_fresh_measurement_retains_resolvable_evidence(tmp_path) -> None:
    """The whole public path: measure, seal, envelope, validate, resolve, round-trip."""
    records = _measure("h9.connection_health", tmp_path)
    assert len(records) == 1
    record = records[0]

    binding = record.measurement_binding
    assert Path(binding["interpreter_executable"]).is_absolute()
    assert [name for name, _ in [tuple(row) for row in binding["dependency_files"]]] == ["redis"]

    reference = RetainedEvidenceReference.from_dict(record.retained_evidence)
    assert reference.observation_count >= 4
    payload = verify_retained_evidence(
        record_id=record.record_id,
        measurement_binding=record.measurement_binding,
        observation_digest=record.observation_digest,
        reference=reference,
        base_directory=tmp_path,
    )
    assert payload["observations"], "the sidecar retained no observations"
    assert payload["inventory"]["kind"] == "queue-and-health-sites"

    sealed = replay_sealed_artifact(SEALED)
    artifact = build_successor_artifact(sealed, records)
    document = artifact.to_dict()
    assert document["schema_version"] == AUDIT_ARTIFACT_SCHEMA_V2
    schema = json.loads(V2_SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(document)) == []
    assert AuditArtifact.from_dict(document).to_dict() == document


def test_retained_evidence_round_trips_from_disk(tmp_path) -> None:
    """Reconstruction happens AFTER the measuring process exits, from bytes alone."""
    records = _measure("identity.echo_bound_modules", tmp_path)
    artifact_path = tmp_path / "successor.json"
    artifact = build_successor_artifact(replay_sealed_artifact(SEALED), records)
    artifact_path.write_text(json.dumps(artifact.to_dict()), encoding="utf-8")

    reloaded = AuditArtifact.from_dict(json.loads(artifact_path.read_text(encoding="utf-8")))
    resolved = verify_current_records(reloaded, tmp_path)
    assert len(resolved) == 1
    recomputed = canonical_digest(resolved[0]["observations"])
    assert recomputed == reloaded.current_measurement_records[0].observation_digest


def test_a_missing_sidecar_fails_verification(tmp_path) -> None:
    """MUTATION: a dangling evidence reference tolerated as a digest with no evidence."""
    records = _measure("identity.echo_bound_modules", tmp_path)
    artifact = build_successor_artifact(replay_sealed_artifact(SEALED), records)
    (tmp_path / records[0].retained_evidence["location"]).unlink()

    with pytest.raises(RetainedEvidenceError, match="is missing"):
        verify_current_records(artifact, tmp_path)


def test_a_tampered_observation_fails_verification(tmp_path) -> None:
    """MUTATION: sealed observations edited after the fact."""
    records = _measure("identity.echo_bound_modules", tmp_path)
    artifact = build_successor_artifact(replay_sealed_artifact(SEALED), records)
    sidecar = tmp_path / records[0].retained_evidence["location"]

    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["observations"][0]["digest"] = "f" * 64
    sidecar.write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    with pytest.raises(RetainedEvidenceError, match="file digest"):
        verify_current_records(artifact, tmp_path)

    # And with the file digest "repaired", the observation digest still refuses it: the
    # record binds the observations, not merely the bytes that happen to hold them.
    raw = sidecar.read_bytes()
    repaired = dict(records[0].retained_evidence, file_digest=hashlib.sha256(raw).hexdigest())
    with pytest.raises(RetainedEvidenceError, match="do not hash to the digest"):
        verify_retained_evidence(
            record_id=records[0].record_id,
            measurement_binding=records[0].measurement_binding,
            observation_digest=records[0].observation_digest,
            reference=RetainedEvidenceReference.from_dict(repaired),
            base_directory=tmp_path,
        )


def test_observations_from_another_inventory_are_refused(tmp_path) -> None:
    """MUTATION: rows discovered from one tree filed against another's inventory."""
    binding = _review_binding("a.py", "b.py")
    payload = {
        "schema_version": "plan-11-26-current-evidence-v1",
        "record_id": "CM-identity-echo_bound_modules",
        "entry": "identity.echo_bound_modules",
        "measurement_binding": dict(binding),
        "inventory": {"kind": "bound-modules", "paths": ["a.py", "b.py"]},
        "inventory_identifiers": ["a.py", "b.py"],
        "observations": [
            {"observation_id": "a.py", "value": 1},
            {"observation_id": "b.py", "value": 1},
            {"observation_id": "c.py", "value": 1},
        ],
    }
    reference = _seal_raw(tmp_path, "CM-identity-echo_bound_modules", payload)
    with pytest.raises(RetainedEvidenceError, match="absent from the inventory"):
        verify_retained_evidence(
            record_id="CM-identity-echo_bound_modules",
            measurement_binding=binding,
            observation_digest=reference.observation_digest,
            reference=reference,
            base_directory=tmp_path,
        )


def test_a_partial_observation_set_does_not_verify_as_complete(tmp_path) -> None:
    """MUTATION: a subset check calling one row of a full schedule complete.

    Membership alone says every row belongs; it never says every row is there. Coverage is
    the half that makes a retained set evidence about the whole contract.
    """
    binding = _review_binding("a.py", "b.py")
    payload = {
        "schema_version": "plan-11-26-current-evidence-v1",
        "record_id": "CM-identity-echo_bound_modules",
        "entry": "identity.echo_bound_modules",
        "measurement_binding": dict(binding),
        "inventory": {"kind": "bound-modules", "paths": ["a.py", "b.py"]},
        "inventory_identifiers": ["a.py", "b.py"],
        "observations": [{"observation_id": "a.py", "value": 1}],
    }
    reference = _seal_raw(tmp_path, "CM-identity-echo_bound_modules", payload)
    with pytest.raises(RetainedEvidenceError, match="do not cover every identifier"):
        verify_retained_evidence(
            record_id="CM-identity-echo_bound_modules", measurement_binding=binding,
            observation_digest=reference.observation_digest,
            reference=reference, base_directory=tmp_path,
        )


def test_a_sidecar_must_name_the_entry_it_is_filed_under(tmp_path) -> None:
    """MUTATION: the sealed entry written and never read back.

    The record id is derived from the entry, so a sidecar claiming another entry -- or one
    that does not exist -- is filed under a name nothing produced.
    """
    binding = _review_binding("a.py")
    def payload_for(entry: str) -> dict:
        return {
            "schema_version": "plan-11-26-current-evidence-v1",
            "record_id": "CM-identity-echo_bound_modules",
            "entry": entry,
            "measurement_binding": dict(binding),
            "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
            "inventory_identifiers": ["a.py"],
            "observations": [{"observation_id": "a.py", "value": 1}],
        }

    unknown = _seal_raw(tmp_path, "CM-identity-echo_bound_modules", payload_for("not.an.entry"))
    with pytest.raises(RetainedEvidenceError, match="not an allowlisted measurement entry"):
        verify_retained_evidence(
            record_id="CM-identity-echo_bound_modules", measurement_binding=binding,
            observation_digest=unknown.observation_digest,
            reference=unknown, base_directory=tmp_path,
        )

    mismatched = _seal_raw(tmp_path, "CM-identity-echo_bound_modules", payload_for("h9.connection_health"))
    with pytest.raises(RetainedEvidenceError, match="rather than"):
        verify_retained_evidence(
            record_id="CM-identity-echo_bound_modules", measurement_binding=binding,
            observation_digest=mismatched.observation_digest,
            reference=mismatched, base_directory=tmp_path,
        )


# --- D2: sealed evidence is immutable ---------------------------------------------------


def test_a_second_measurement_cannot_damage_the_first(tmp_path) -> None:
    """MUTATION: a deterministic filename plus an unconditional write.

    The reviewer needed no tampering for this: two runs into one evidence directory, and
    the second simply replaced the first run's sidecar, after which the first record no
    longer verified. Distinct results must land at distinct paths and BOTH must stay
    verifiable.
    """
    def seal(value: int):
        return write_evidence_sidecar(
            directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
            binding=_REVIEW_BINDING,
            result={
                "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
                "inventory_identifiers": ["a.py"],
                "observations": [{"observation_id": "a.py", "value": value}],
            },
        )

    def check(reference):
        return verify_retained_evidence(
            record_id="CM-identity-echo_bound_modules", measurement_binding=_REVIEW_BINDING,
            observation_digest=reference.observation_digest,
            reference=reference, base_directory=tmp_path,
        )

    first = seal(1)
    check(first)
    before = (tmp_path / first.location).read_bytes()

    second = seal(2)
    assert first.location != second.location, "a different result reused the same sealed path"
    assert (tmp_path / first.location).read_bytes() == before, "the first sidecar was rewritten"
    check(first)   # the earlier record is still verifiable ...
    check(second)  # ... and so is the later one


def _files_under(directory: Path) -> set[str]:
    # Non-recursive on purpose: these controls use a flat tmp_path, and a glob/rglob here would
    # itself be a filesystem walker needing a reviewed rationale.
    return {p.name for p in directory.iterdir() if p.is_file()}


def test_canonical_digest_is_content_only_and_writes_nothing(tmp_path, monkeypatch) -> None:
    """Plan 9.96: evidence_store.canonical_digest serializes ONLY to hash; nothing reaches disk."""
    monkeypatch.chdir(tmp_path)
    before = _files_under(tmp_path)
    value = {"b": [1, {"y": 2, "x": 1}], "a": "text"}
    digest = canonical_digest(value)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert canonical_digest({"a": "text", "b": [1, {"x": 1, "y": 2}]}) == digest, "key order changed the digest"
    assert canonical_digest({"a": "text", "b": [1, {"x": 1, "y": 3}]}) != digest, "content did not change the digest"
    assert _files_under(tmp_path) == before, "the digest helper wrote something"


def test_environment_binding_digest_is_content_only_and_writes_nothing(tmp_path, monkeypatch) -> None:
    """Plan 9.96: EnvironmentBinding.digest hashes the binding's own fields and persists nothing."""
    monkeypatch.chdir(tmp_path)
    before = _files_under(tmp_path)
    binding = _fabricated_binding()
    digest = binding.digest
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert EnvironmentBinding.from_dict(binding.to_dict()).digest == digest
    altered = EnvironmentBinding.from_dict({**binding.to_dict(), "source_fingerprint": "c" * 64})
    assert altered.digest != digest
    assert _files_under(tmp_path) == before, "the binding digest wrote something"


def test_build_evidence_payload_returns_the_exact_bytes_the_sidecar_persists_and_writes_nothing(tmp_path) -> None:
    """Plan 9.96: build_evidence_payload encodes the schema-limited payload and RETURNS it; those exact
    bytes -- and nothing else -- are what write_evidence_sidecar persists, content-addressed."""
    result = {
        "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
        "inventory_identifiers": ["a.py"],
        "observations": [{"observation_id": "a.py", "value": 1}],
    }
    payload, encoded, reference = evidence_store.build_evidence_payload(
        record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
        binding=_REVIEW_BINDING, result=result,
    )
    assert _files_under(tmp_path) == set(), "building the payload wrote to disk"
    assert set(payload) == {
        "schema_version", "record_id", "entry", "measurement_binding", "inventory", "inventory_identifiers", "observations",
    }, "the payload carries keys outside the fixed schema"
    assert payload["measurement_binding"] == dict(_REVIEW_BINDING)
    assert json.loads(encoded.decode("utf-8")) == payload
    assert reference.file_digest == hashlib.sha256(encoded).hexdigest()

    persisted = write_evidence_sidecar(
        directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
        binding=_REVIEW_BINDING, result=result,
    )
    assert persisted == reference
    assert _files_under(tmp_path) == {reference.location}, "the sidecar writer left more than the sealed file"
    assert (tmp_path / reference.location).read_bytes() == encoded, "persisted bytes differ from the returned bytes"


def test_an_identical_result_reseals_idempotently(tmp_path) -> None:
    """Re-sealing the same bytes is a no-op, not a collision: nothing changed."""
    result = {
        "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
        "inventory_identifiers": ["a.py"],
        "observations": [{"observation_id": "a.py", "value": 1}],
    }
    first = write_evidence_sidecar(
        directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
        binding=_REVIEW_BINDING, result=result,
    )
    again = write_evidence_sidecar(
        directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
        binding=_REVIEW_BINDING, result=result,
    )
    assert again.location == first.location and again.file_digest == first.file_digest
    assert len(list(tmp_path.glob("*.evidence.json"))) == 1


def test_an_occupied_evidence_path_is_refused_not_replaced(tmp_path) -> None:
    """MUTATION: a write that overwrites whatever is already there."""
    result = {
        "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
        "inventory_identifiers": ["a.py"],
        "observations": [{"observation_id": "a.py", "value": 1}],
    }
    reference = write_evidence_sidecar(
        directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
        binding=_REVIEW_BINDING, result=result,
    )
    occupied = tmp_path / reference.location
    occupied.write_bytes(b'{"someone else": "was here"}')

    with pytest.raises(EvidenceCollisionError, match="refusing to replace"):
        write_evidence_sidecar(
            directory=tmp_path, record_id="CM-identity-echo_bound_modules", entry="identity.echo_bound_modules",
            binding=_REVIEW_BINDING, result=result,
        )
    assert occupied.read_bytes() == b'{"someone else": "was here"}', "the occupied path was replaced"


def test_duplicate_entries_in_one_run_are_refused_before_any_measurement(tmp_path) -> None:
    """MUTATION: two plans for one entry, one record id, one sidecar path.

    Refused in the preflight, so nothing is measured and nothing is written -- rather than
    discovered halfway through, leaving a directory nobody can attribute.
    """
    plans = default_measurement_plan(
        repository_root=ROOT, entries=("identity.echo_bound_modules", "identity.echo_bound_modules")
    )
    with pytest.raises(RetainedEvidenceError, match="more than once"):
        measure_current(plans=plans, repository_root=ROOT, evidence_directory=tmp_path)
    assert list(tmp_path.glob("*.evidence.json")) == [], "a refused run still wrote evidence"


def test_a_later_stage_failure_leaves_earlier_evidence_verifiable(tmp_path) -> None:
    """MUTATION: a failed run damaging the evidence that already succeeded."""
    good = default_measurement_plan(
        repository_root=ROOT, entries=("identity.echo_bound_modules",)
    )[0]
    queue_source = _tree(queue_policy.H9_SOURCE_PATHS)
    doomed = MeasurementPlan(
        entry="h9.connection_health",
        source=queue_source,
        # A fingerprint the measured tree does not have: the child refuses after the first
        # plan has already sealed its evidence.
        spec=MeasurementSpecification(
            paths=(_GATE,), import_roots=(str(ROOT / "src"), str(ROOT)),
            dependencies=(), source_fingerprint="0" * 64,
        ),
        options={},
    )

    with pytest.raises(ExecutingSourceMismatch):
        measure_current(plans=(good, doomed), repository_root=ROOT, evidence_directory=tmp_path)

    sealed = list(tmp_path.glob("*.evidence.json"))
    assert len(sealed) == 1, sealed
    survivor = sealed[0].read_bytes()

    # Re-running the successful plan alone reseals to the SAME bytes and verifies, which is
    # what "the earlier evidence survived" has to mean to be worth asserting.
    records = measure_current(plans=(good,), repository_root=ROOT, evidence_directory=tmp_path)
    assert records[0].retained_evidence["location"] == sealed[0].name
    assert sealed[0].read_bytes() == survivor
    verify_retained_evidence(
        record_id=records[0].record_id,
        measurement_binding=records[0].measurement_binding,
        observation_digest=records[0].observation_digest,
        reference=RetainedEvidenceReference.from_dict(records[0].retained_evidence),
        base_directory=tmp_path,
    )


def test_the_cli_refuses_to_replace_an_existing_artifact(tmp_path) -> None:
    """MUTATION: an accepted artifact silently overwritten by the next run."""
    from tools.run_plan1126_runtime_audit import main

    artifact = tmp_path / "successor.json"
    artifact.write_text('{"schema_version": "someone-elses-artifact"}', encoding="utf-8")
    assert main([
        "current-measurement", "measure",
        "--sealed", str(SEALED), "--artifact", str(artifact),
        "--evidence-dir", str(tmp_path), "--entry", "identity.echo_bound_modules",
    ]) == 1
    assert artifact.read_text(encoding="utf-8") == '{"schema_version": "someone-elses-artifact"}'


# --- D3: identifiers are DERIVED from the retained inventory -----------------------------


def test_identifiers_are_derived_from_each_inventory_kind() -> None:
    """The derivation reads the inventory's primitive contents, not its own summary."""
    assert derive_inventory_identifiers(
        {"kind": "bound-modules", "paths": ["b.py", "a.py"]}, _review_binding("a.py", "b.py")
    ) == ("a.py", "b.py")
    with pytest.raises(RetainedEvidenceError, match="does not match the modules the binding names"):
        derive_inventory_identifiers(
            {"kind": "bound-modules", "paths": ["a.py"]}, _review_binding("a.py", "b.py")
        )

    shutdown_inventory = {
        "kind": "shutdown-close-paths",
        "resources": [
            {"close_path_id": "keep", "schedule_applicable": True},
            {"close_path_id": "skip", "schedule_applicable": False},
        ],
    }
    assert derive_inventory_identifiers(shutdown_inventory) == ("keep",)

    health_inventory = {
        "kind": "queue-and-health-sites",
        "sites": [
            {"path": _RUNTIME, "line": 41, "symbol": "RedisRuntime.ping", "site_kind": "HEALTH_PROBE"},
            {"path": "src/optimus/acp/server.py", "line": 9, "symbol": "x", "site_kind": "HEALTH_PROBE"},
            {"path": _RUNTIME, "line": 7, "symbol": "other", "site_kind": "QUEUE_CONSUMER"},
        ],
    }
    derived = derive_inventory_identifiers(health_inventory)
    assert derived == tuple(sorted(
        f"{_RUNTIME}:41:RedisRuntime.ping|{scenario.value}"
        for scenario in queue_policy.HealthScenario
    ))
    assert len(derived) == len(list(queue_policy.HealthScenario))


def test_the_h9_identifier_universe_comes_from_the_enum_not_the_observed_rows() -> None:
    """MUTATION: observations deciding which observations are admissible.

    Deriving the scenario set from the rows would make any set of rows self-consistent.
    The universe is the enum, so a row naming a scenario the enum does not have has
    nowhere to belong.
    """
    inventory = {
        "kind": "queue-and-health-sites",
        "sites": [{"path": _RUNTIME, "line": 41, "symbol": "RedisRuntime.ping",
                   "site_kind": "HEALTH_PROBE"}],
    }
    derived = set(derive_inventory_identifiers(inventory))
    assert f"{_RUNTIME}:41:RedisRuntime.ping|INVENTED_SCENARIO" not in derived
    assert all(item.endswith(tuple(s.value for s in queue_policy.HealthScenario)) for item in derived)


def test_an_unknown_or_malformed_inventory_is_refused() -> None:
    """An inventory with no derivation cannot validate anything, so it is refused."""
    with pytest.raises(RetainedEvidenceError, match="no derivation"):
        derive_inventory_identifiers({"kind": "something-new", "paths": ["a.py"]})
    with pytest.raises(RetainedEvidenceError, match="no derivation"):
        derive_inventory_identifiers({"paths": ["a.py"]})
    with pytest.raises(RetainedEvidenceError, match="missing or malformed"):
        derive_inventory_identifiers({"kind": "shutdown-close-paths"})
    with pytest.raises(RetainedEvidenceError, match="no applicable close path"):
        derive_inventory_identifiers({
            "kind": "shutdown-close-paths",
            "resources": [{"close_path_id": "skip", "schedule_applicable": False}],
        })
    with pytest.raises(RetainedEvidenceError, match="no health probe"):
        derive_inventory_identifiers({"kind": "queue-and-health-sites", "sites": []})
    with pytest.raises(RetainedEvidenceError, match="no usable path list"):
        derive_inventory_identifiers({"kind": "bound-modules", "paths": "a.py"}, _REVIEW_BINDING)


def test_an_inventory_that_disagrees_with_its_identifier_list_is_refused(tmp_path) -> None:
    """MUTATION: a declared identifier list treated as an authority over its own inventory.

    The reviewer's payload: an inventory listing only "a.py", a declared list of ["b.py"],
    and an observation for "b.py". It verified. It is now refused when sealed AND when
    verified -- and the verification refusal must come from the DERIVATION, not from a
    digest, so every digest is recomputed for the payload placed on disk.
    """
    inconsistent = {
        "inventory": {"kind": "bound-modules", "paths": ["a.py"]},
        "inventory_identifiers": ["b.py"],
        "observations": [{"observation_id": "b.py", "value": 1}],
    }
    with pytest.raises(RetainedEvidenceError, match="do not match the ones its own"):
        write_evidence_sidecar(
            directory=tmp_path, record_id="CM-inconsistent",
            entry="identity.echo_bound_modules", binding=_REVIEW_BINDING, result=inconsistent,
        )

    payload = {
        "schema_version": "plan-11-26-current-evidence-v1",
        "record_id": "CM-inconsistent",
        "entry": "identity.echo_bound_modules",
        "measurement_binding": dict(_REVIEW_BINDING),
        **inconsistent,
    }
    reference = _seal_raw(tmp_path, "CM-inconsistent", payload)
    with pytest.raises(RetainedEvidenceError) as excinfo:
        verify_retained_evidence(
            record_id="CM-inconsistent", measurement_binding=_REVIEW_BINDING,
            observation_digest=reference.observation_digest,
            reference=reference, base_directory=tmp_path,
        )
    assert "not an authority" in str(excinfo.value)
    assert "digest" not in str(excinfo.value), "the refusal came from a digest, not the derivation"


def test_a_retained_inventory_from_another_tree_is_refused(tmp_path) -> None:
    """MUTATION: an inventory whose own fingerprint names a revision the record never measured."""
    payload = {
        "schema_version": "plan-11-26-current-evidence-v1",
        "record_id": "CM-foreign-tree",
        "entry": "h5.shutdown_schedule",
        "measurement_binding": dict(_REVIEW_BINDING),
        "inventory": {
            "kind": "shutdown-close-paths",
            "source_fingerprint": "9" * 64,  # not the binding's "a" * 64
            "resources": [{"close_path_id": "keep", "schedule_applicable": True}],
        },
        "inventory_identifiers": ["keep"],
        "observations": [{"observation_id": "keep", "value": 1}],
    }
    reference = _seal_raw(tmp_path, "CM-foreign-tree", payload)
    with pytest.raises(RetainedEvidenceError, match="discovered from a different tree"):
        verify_retained_evidence(
            record_id="CM-foreign-tree", measurement_binding=_REVIEW_BINDING,
            observation_digest=reference.observation_digest,
            reference=reference, base_directory=tmp_path,
        )


def test_swapping_the_h5_and_h9_inventories_is_refused(tmp_path) -> None:
    """MUTATION: one hypothesis's rows validated against the other's inventory."""
    payload = {
        "schema_version": "plan-11-26-current-evidence-v1",
        "record_id": "CM-swapped",
        "entry": "h5.shutdown_schedule",
        "measurement_binding": dict(_REVIEW_BINDING),
        # H9's inventory kind, carrying H5's close-path observation.
        "inventory": {
            "kind": "queue-and-health-sites",
            "sites": [{"path": _RUNTIME, "line": 41, "symbol": "RedisRuntime.ping",
                       "site_kind": "HEALTH_PROBE"}],
        },
        "inventory_identifiers": ["src/optimus/redis/runtime.py:12:close"],
        "observations": [{"observation_id": "src/optimus/redis/runtime.py:12:close", "value": 1}],
    }
    reference = _seal_raw(tmp_path, "CM-swapped", payload)
    with pytest.raises(RetainedEvidenceError, match="not an authority"):
        verify_retained_evidence(
            record_id="CM-swapped", measurement_binding=_REVIEW_BINDING,
            observation_digest=reference.observation_digest,
            reference=reference, base_directory=tmp_path,
        )


def test_an_empty_measurement_retains_nothing_and_says_so(tmp_path) -> None:
    """A record whose evidence is empty is not a record; it is an unfalsifiable claim."""
    with pytest.raises(RetainedEvidenceError, match="no observations"):
        write_evidence_sidecar(
            directory=tmp_path, record_id="CM-empty", entry="identity.echo_bound_modules",
            binding={}, result={"inventory": {}, "inventory_identifiers": [], "observations": []},
        )


# --- R5d: the CLI and renderer support the successor ------------------------------


def test_the_cli_measures_verifies_renders_and_replays_in_fresh_processes(tmp_path) -> None:
    """The operation the ruling actually asked for, through the real command line.

    Python builders plus schema validation were never the claim under review: the CLI
    rejected its own successor with "'plan-11-26-runtime-audit-v1' was expected", and the
    renderer omitted the record entirely. Both are exercised here in fresh processes.
    """
    artifact = tmp_path / "successor.json"
    report = tmp_path / "successor.md"

    def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *arguments],
            cwd=ROOT, capture_output=True, text=True, timeout=1800,
        )

    measured = _cli(
        "current-measurement", "measure",
        "--sealed", str(SEALED), "--artifact", str(artifact),
        "--evidence-dir", str(tmp_path), "--entry", "identity.echo_bound_modules",
    )
    assert measured.returncode == 0, measured.stderr
    assert json.loads(measured.stdout)["status"] == "PASS"

    verified = _cli(
        "current-measurement", "verify", "--artifact", str(artifact), "--evidence-dir", str(tmp_path)
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert json.loads(verified.stdout)["reasons"] == ["CM-identity-echo_bound_modules"]

    rendered = _cli(
        "current-measurement", "render", "--artifact", str(artifact),
        "--evidence-dir", str(tmp_path), "--report", str(report),
    )
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr

    text = report.read_text(encoding="utf-8")
    record = AuditArtifact.from_dict(json.loads(artifact.read_text(encoding="utf-8")))
    current = record.current_measurement_records[0]
    assert "## Current measurements (NOT historical evidence)" in text
    assert current.record_id in text
    assert current.observation_digest in text
    assert current.retained_evidence["location"] in text
    assert current.retained_evidence["file_digest"] in text
    assert current.measurement_binding["source_fingerprint"] in text

    # Historical replay through the same CLI stays non-executing and still passes.
    replayed = _cli("verify", "--artifact", str(SEALED))
    assert replayed.returncode == 0, replayed.stdout + replayed.stderr


def test_the_cli_current_measurement_reports_invalid_input_without_raising(tmp_path) -> None:
    """The command reports INVALID rather than propagating; this is its raw-exception sink."""
    from tools.run_plan1126_runtime_audit import main

    assert main([
        "current-measurement", "verify",
        "--artifact", str(tmp_path / "there-is-no-such-artifact.json"),
        "--evidence-dir", str(tmp_path),
    ]) == 1


def test_the_renderer_distinguishes_current_records_from_historical_ones(tmp_path) -> None:
    """MUTATION: the report shows the successor's historical half and hides the new half.

    Rendering omitted the current record entirely, so a reader of the report could not
    tell a successor from the v1 artifact it was built on.
    """
    from tools.plan1126_runtime_audit.render import render_markdown

    sealed = replay_sealed_artifact(SEALED)
    assert "## Current measurements" not in render_markdown(sealed.to_dict())

    records = _measure("identity.echo_bound_modules", tmp_path)
    text = render_markdown(build_successor_artifact(sealed, records).to_dict())
    assert "## Current measurements (NOT historical evidence)" in text
    assert records[0].record_id in text
    assert records[0].observation_digest in text
    assert records[0].retained_evidence["location"] in text
    assert records[0].retained_evidence["file_digest"] in text
    assert records[0].measurement_binding["interpreter_executable"] in text


def test_the_cli_refuses_an_unknown_envelope(tmp_path) -> None:
    """Dispatch is closed: an envelope with no schema is named, not guessed at."""
    from tools.run_plan1126_runtime_audit import main

    payload = json.loads(SEALED.read_text(encoding="utf-8"))
    payload["schema_version"] = "plan-11-26-runtime-audit-v99"
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["verify", "--artifact", str(unknown)]) == 1


# --- Envelope and record invariants -----------------------------------------------


def test_the_successor_envelope_carries_historical_records_unchanged(tmp_path) -> None:
    """MUTATION: current identity leaking into a historical record."""
    records = _measure("identity.echo_bound_modules", tmp_path)
    sealed = replay_sealed_artifact(SEALED)
    successor = build_successor_artifact(sealed, records)

    before = [record.to_dict() for record in sealed.evidence_records]
    after = [record.to_dict() for record in successor.evidence_records]
    assert before == after, "a historical evidence record changed when fresh measurements were attached"

    current = successor.current_measurement_records[0].to_dict()
    assert "baseline_anchor_commit" not in current
    assert current["measurement_binding"]["source_fingerprint"] != sealed.merged_commit


def test_the_v1_envelope_rejects_fresh_measurements(tmp_path) -> None:
    """Old readers keep validating old artifacts; the successor is dispatched explicitly."""
    records = _measure("identity.echo_bound_modules", tmp_path)
    payload = build_successor_artifact(replay_sealed_artifact(SEALED), records).to_dict()

    v1 = json.loads(V1_SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(v1).iter_errors(payload)), "the v1 envelope accepted a fresh measurement"

    with pytest.raises(ValueError, match="successor envelope"):
        AuditArtifact.from_dict({**payload, "schema_version": AUDIT_ARTIFACT_SCHEMA_V1})


def test_frozen_fixtures_are_unchanged() -> None:
    """The v1 schema fixture stays byte-identical; the successor is a NEW file."""
    committed = subprocess.run(
        ["git", "show", "HEAD:tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json"],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout
    assert V1_SCHEMA.read_bytes().replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n")
    assert V2_SCHEMA.exists()


def _valid_binding() -> dict:
    return {
        "interpreter_executable": "C:/python.exe",
        "interpreter_version": "3.14",
        "prefix": "C:/venv",
        "source_fingerprint": "a" * 64,
        "module_origins": [["src/x.py", str(ROOT / "src" / "x.py"), "b" * 64]],
        "dependency_files": [["redis", "c" * 64]],
    }


def _valid_reference(digest: str = "d" * 64) -> dict:
    return {
        "kind": "sidecar",
        "location": "CM-review-only.evidence.json",
        "file_digest": "e" * 64,
        "inventory_digest": "f" * 64,
        "observation_digest": digest,
        "observation_count": 3,
    }


def test_a_current_record_rejects_a_malformed_binding_or_a_dangling_reference() -> None:
    """MUTATION: the persisted claim accepted without validating it.

    A record is the persisted claim about what was measured. An unvalidated claim is
    indistinguishable from a fabricated one, and a digest with no resolvable evidence
    behind it cannot be contradicted by anything.
    """

    def _build(binding=None, retained=None, digest="d" * 64):
        return CurrentMeasurementRecord(
            record_id="review-only", hypothesis_id="H5", subject="test",
            schema_version=CURRENT_MEASUREMENT_SCHEMA_VERSION,
            measurement_binding=binding if binding is not None else _valid_binding(),
            observation_digest=digest,
            retained_evidence=retained if retained is not None else _valid_reference(digest),
            ruling="test",
        )

    _build()  # the well-formed shape is accepted

    with pytest.raises(ValueError, match="binding is invalid"):
        _build(binding={
            "interpreter": "", "source_fingerprint": "invalid",
            "module_digests": [["path", "invalid"]], "dependency_digests": [],
        })
    for mutation in (
        {"interpreter_executable": ""},
        {"source_fingerprint": "not-a-digest"},
        {"module_origins": []},
        {"module_origins": [
            ["src/x.py", str(ROOT / "src" / "x.py"), "b" * 64],
            ["src/x.py", str(ROOT / "src" / "x.py"), "b" * 64],
        ]},
    ):
        with pytest.raises(ValueError, match="binding is invalid"):
            _build(binding={**_valid_binding(), **mutation})

    with pytest.raises(ValueError, match="retained evidence is invalid"):
        _build(retained={"kind": "sidecar"})
    with pytest.raises(ValueError, match="retained evidence is invalid"):
        _build(retained={**_valid_reference(), "location": "../escape.json"})
    with pytest.raises(ValueError, match="retained evidence is invalid"):
        _build(retained={**_valid_reference(), "observation_count": 0})
    with pytest.raises(ValueError, match="binds a different observation digest"):
        _build(retained={**_valid_reference(), "observation_digest": "9" * 64})


def test_the_evidence_store_module_is_importable_without_the_audit_package() -> None:
    """Retained evidence is data plumbing; it must not drag probes in behind it."""
    assert evidence_store.CURRENT_EVIDENCE_SCHEMA_VERSION == "plan-11-26-current-evidence-v1"


# --- Historical replay executes no current probe ------------------------------------


#: Every function in the audit package that executes product code to produce observations.
#: Each call site lives in the module that defines it, so patching the module attribute is
#: what a caller reaches; there is no `from x import y` alias to miss.
_PROBE_ENTRY_POINTS = (
    ("tools.plan1126_runtime_audit.cancellation", "cancellation_schedule_observations"),
    ("tools.plan1126_runtime_audit.delivery_characterization", "delivery_schedule_observations"),
    ("tools.plan1126_runtime_audit.semantic_errors", "semantic_selection_observations"),
    ("tools.plan1126_runtime_audit.telemetry", "runtime_event_schema_observations"),
    ("tools.plan1126_runtime_audit.telemetry", "runtime_redaction_observations"),
    ("tools.plan1126_runtime_audit.telemetry", "runtime_correlation_observations"),
    ("tools.plan1126_runtime_audit.telemetry", "telemetry_sink_failure_observations"),
    ("tools.plan1126_runtime_audit.queue_policy", "queue_admission_observations"),
    ("tools.plan1126_runtime_audit.queue_policy", "connection_health_observations"),
    ("tools.plan1126_runtime_audit.shutdown", "shutdown_schedule_observations"),
    ("tools.plan1126_runtime_audit.shutdown", "_probe_resource"),
)


def _disable_every_probe(monkeypatch, executed: list) -> None:
    """Make every observation entry point fail loudly, so replay cannot lean on one."""
    for module_path, name in _PROBE_ENTRY_POINTS:
        module = importlib.import_module(module_path)

        def refuse(*args, _label=f"{module_path}.{name}", **kwargs):
            executed.append(_label)
            raise AssertionError(f"a replay path executed {_label}")

        monkeypatch.setattr(module, name, refuse)


def test_historical_verification_and_rendering_execute_no_probe(monkeypatch, tmp_path) -> None:
    """MUTATION: a historical builder regenerating rows instead of replaying them.

    A reviewer disabled ONE function -- H4's delivery schedule -- called the CLI's verifier
    on the accepted artifact, and caught it executing. Disabling one at a time only ever
    finds the one you guessed; every entry point is disabled here at once, and the same
    commands must still succeed, because a replay that needs any of them is not a replay.
    """
    from tools.run_plan1126_runtime_audit import main

    executed: list = []
    _disable_every_probe(monkeypatch, executed)

    assert main(["verify", "--artifact", str(SEALED)]) == 0
    report = tmp_path / "historical.md"
    assert main(["render", "--artifact", str(SEALED), "--report", str(report)]) == 0
    assert report.stat().st_size > 0
    assert executed == [], executed


def test_the_cumulative_artifact_commands_execute_no_probe(monkeypatch, tmp_path) -> None:
    """The whole H3..H10 chain replays, not just the branch `verify` happens to take."""
    from tools.run_plan1126_runtime_audit import main

    executed: list = []
    _disable_every_probe(monkeypatch, executed)

    for command in ("semantic", "telemetry", "queue-policy", "session-lease"):
        artifact = tmp_path / f"{command}.json"
        assert main([
            command, "--artifact", str(artifact), "--report", str(tmp_path / f"{command}.md"),
        ]) == 0, command
        assert artifact.exists(), command
    assert executed == [], executed


def test_successor_verification_resolves_sidecars_without_remeasuring(monkeypatch, tmp_path) -> None:
    """The v2 envelope's historical half follows the same branch, and its current half resolves.

    The fresh measurement runs first with everything available; verification then runs with
    the probes AND the measurement machinery disabled, because "without remeasuring" is a
    claim about not re-running the measurement.
    """
    from tools.plan1126_runtime_audit import current_envelope, measurement
    from tools.run_plan1126_runtime_audit import main

    artifact = tmp_path / "successor.json"
    assert main([
        "current-measurement", "measure", "--sealed", str(SEALED),
        "--artifact", str(artifact), "--evidence-dir", str(tmp_path),
        "--entry", "identity.echo_bound_modules",
    ]) == 0

    executed: list = []
    _disable_every_probe(monkeypatch, executed)
    for module, name in (
        (current_envelope, "measure_current"),
        (measurement, "run_fresh_measurement"),
        (measurement, "establish_verified_execution"),
    ):
        def refuse_measure(*args, _label=f"{module.__name__}.{name}", **kwargs):
            executed.append(_label)
            raise AssertionError(f"verification re-measured via {_label}")

        monkeypatch.setattr(module, name, refuse_measure)

    assert main([
        "current-measurement", "verify", "--artifact", str(artifact), "--evidence-dir", str(tmp_path),
    ]) == 0
    assert main([
        "current-measurement", "render", "--artifact", str(artifact),
        "--evidence-dir", str(tmp_path), "--report", str(tmp_path / "successor.md"),
    ]) == 0
    assert executed == [], executed


def test_the_replay_carrier_reads_every_family_and_refuses_a_gap() -> None:
    """MUTATION: a family quietly measured because its sealed rows were never read.

    The counts are the assertion. "It did not raise" would pass just as well against a
    carrier that returned ten empty tuples.
    """
    from tools.plan1126_runtime_audit.replay import (
        FAMILY_NAMES,
        MissingSealedEvidence,
        SealedObservations,
    )

    sealed = json.loads(SEALED.read_text(encoding="utf-8"))
    bundle = SealedObservations.from_sealed(sealed)
    counts = bundle.counts()

    assert set(counts) == set(FAMILY_NAMES)
    assert counts == {
        "cancellation": 8320, "delivery": 1004, "shutdown": 6500, "semantic": 800,
        "schema": 10000, "redaction": 1000, "correlation": 19, "sink_failure": 500,
        "admission": 30000, "health": 4,
    }

    # TWO ways a family's evidence can be absent, and they take different branches. An
    # earlier version of this control only removed the whole RECORD, so the missing-ROWS
    # refusal was never reached and a mutation that deleted it survived: the assertion was
    # about the wrong absence.
    hypotheses = {
        "cancellation": "H3", "delivery": "H4", "shutdown": "H5", "semantic": "H7",
        "schema": "H8", "redaction": "H8", "correlation": "H8", "sink_failure": "H8",
        "admission": "H9", "health": "H9",
    }
    containers = {
        "cancellation": ("schedule_observations", "observations"),
        "delivery": ("schedule_observations", "observations"),
        "shutdown": ("schedule_observations", "observations"),
        "semantic": ("observations", "rows"),
        "schema": ("schema_observations", "rows"),
        "redaction": ("redaction_observations", "rows"),
        "correlation": ("correlation_observations", "rows"),
        "sink_failure": ("sink_failure_observations", "rows"),
        "admission": ("admission_observations", "rows"),
        "health": ("health_observations", "rows"),
    }

    for family in FAMILY_NAMES:
        hypothesis = hypotheses[family]

        without_record = json.loads(SEALED.read_text(encoding="utf-8"))
        without_record["evidence_records"] = [
            record for record in without_record["evidence_records"]
            if record["hypothesis_id"] != hypothesis
        ]
        with pytest.raises(MissingSealedEvidence, match=hypothesis):
            SealedObservations.from_sealed(without_record)

        field, key = containers[family]
        without_rows = json.loads(SEALED.read_text(encoding="utf-8"))
        for record in without_rows["evidence_records"]:
            if record["hypothesis_id"] == hypothesis:
                record[field][key] = []
        with pytest.raises(MissingSealedEvidence, match=re.escape(f"{field}.{key}")):
            SealedObservations.from_sealed(without_rows)
