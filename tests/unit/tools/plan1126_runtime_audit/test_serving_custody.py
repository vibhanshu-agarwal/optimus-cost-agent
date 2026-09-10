"""Seam 2, checkpoint B: S1 serving custody is DERIVED from source and demonstrated wiring.

Round 2 (R2/R3) controls, each named for the reviewer's counterexample it inverts:

* a null handoff (`redis_runtime=None`) and an omitted product rollback, measured through
  the REAL public fresh-child path on a mutated COPY of the tree, must yield MISSING --
  they yielded CANONICAL in v1;
* the measurement's execution closure is checked against its binding: a binding that
  omits an executing product file or distribution is refused before any row is returned;
* the ruling is re-derived from retained rows at verification, and an edited ruling is
  refused.

The measurement itself runs through the REAL public path: a fresh child interpreter with a
context issued for this entry, discovery from the measured tree, retained evidence on disk.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from tools.plan1126_runtime_audit import serving_custody
from tools.plan1126_runtime_audit.current_envelope import (
    default_measurement_plan,
    entry_ruling,
    measure_current,
    verify_current_records,
)
from tools.plan1126_runtime_audit.evidence_store import (
    RetainedEvidenceError,
    derive_inventory_identifiers,
    write_evidence_sidecar,
)
from tools.plan1126_runtime_audit.measurement import (
    EnvironmentBinding,
    ExecutionClosureRecorder,
    run_fresh_measurement,
    verify_execution_closure,
)
from tools.plan1126_runtime_audit.model import AuditArtifact
from tools.plan1126_runtime_audit.registry import entry_requirements, entry_source_paths, measurement_entry_names
from tools.plan1126_runtime_audit.serving_custody import (
    S1_MEASUREMENT_ENTRY,
    S1_SOURCE_PATHS,
    CustodyObservation,
    CustodyOutcome,
    CustodyScenario,
    CustodySiteKind,
    derive_s1_classification,
    derive_s1_ruling,
    discover_serving_custody_inventory,
)
from tools.plan1126_runtime_audit.source import ExecutingSourceMismatch, SourceTree

ROOT = Path(__file__).resolve().parents[4]
SEALED = ROOT / "reports" / "plan-11-26-acp-runtime-audit.json"
BOOTSTRAP = "src/optimus/acp/bootstrap.py"


def _current_tree(paths=S1_SOURCE_PATHS) -> SourceTree:
    return SourceTree({path: (ROOT / path).read_text(encoding="utf-8") for path in paths})


def _measure_s1(repository_root: Path = ROOT) -> tuple[dict, list[dict]]:
    plan = default_measurement_plan(repository_root=repository_root, entries=(S1_MEASUREMENT_ENTRY,))[0]
    _binding, result = run_fresh_measurement(
        source=plan.source, spec=plan.spec, entry=S1_MEASUREMENT_ENTRY, options=plan.options,
        repository_root=repository_root,
    )
    return result["inventory"], result["observations"]


def _mutated_copy(tmp_path: Path, name: str, before: str, after: str) -> Path:
    """A separate tree (src + tools only) with ONE bootstrap mutation; the lane is untouched."""
    copy = tmp_path / name
    for directory in ("src", "tools"):
        shutil.copytree(ROOT / directory, copy / directory, ignore=shutil.ignore_patterns("__pycache__"))
    target = copy / BOOTSTRAP
    text = target.read_text(encoding="utf-8")
    assert text.count(before) == 1, before
    target.write_text(text.replace(before, after, 1), encoding="utf-8", newline="\n")
    return copy


# --- registry and identifiers ----------------------------------------------------------


def test_the_entry_is_allowlisted_and_binds_the_serving_graph_it_executes() -> None:
    assert S1_MEASUREMENT_ENTRY in measurement_entry_names()
    assert entry_source_paths(S1_MEASUREMENT_ENTRY) == S1_SOURCE_PATHS
    requirements = entry_requirements(S1_MEASUREMENT_ENTRY)
    for path in (
        "src/optimus/acp/bootstrap.py", "src/optimus/acp/server.py", "src/optimus/redis/runtime.py",
        "src/optimus/redis/async_bridge.py", "src/optimus/guardrails/pre_tool.py", "src/optimus/acp/debug_trace.py",
        "src/optimus/acp/lifecycle.py", "src/optimus/acp/request_ids.py",
        "tools/plan1126_runtime_audit/serving_custody.py", "tools/plan1126_runtime_audit/measurement.py",
    ):
        assert path in requirements.paths, path
    for distribution in ("redis", "keyring", "pydantic"):
        assert distribution in requirements.dependencies, distribution


def test_identifiers_come_from_the_scenario_enum_not_the_rows() -> None:
    inventory = discover_serving_custody_inventory(_current_tree()).to_dict()
    assert derive_inventory_identifiers(inventory) == tuple(sorted(s.value for s in CustodyScenario))
    assert len(CustodyScenario) == 7
    with pytest.raises(RetainedEvidenceError, match="sites or stage order"):
        derive_inventory_identifiers({"kind": "serving-custody"})


# --- static discovery on the real tree ----------------------------------------------


def test_the_current_tree_retains_the_handle_and_closes_redis_last() -> None:
    inventory = discover_serving_custody_inventory(_current_tree())
    kinds = {site.kind for site in inventory.sites}
    assert CustodySiteKind.RETAINED_HANDLE_CONSTRUCTION in kinds
    assert CustodySiteKind.RETAINED_HANDLE_FIELD in kinds
    assert CustodySiteKind.TEARDOWN_STAGE_CALL in kinds
    assert CustodySiteKind.NULL_HANDLE_CONSTRUCTION not in kinds
    assert inventory.retained_handle
    assert inventory.serving_shutdown_order == (
        "adapter", "client_mcp_runtime", "dedicated_writer", "reader_task", "redis_runtime",
    )
    assert inventory.redis_stage_last
    assert inventory.shared_loop_reaches == 0, [s for s in inventory.sites if s.kind is CustodySiteKind.SHARED_LOOP_REACH]
    assert inventory.submission_injections >= 2


def test_a_null_handoff_is_a_null_handle_not_a_retained_one() -> None:
    """R2 MUTATION (static half): keyword presence proved nothing; the VALUE is inspected."""
    texts = {path: (ROOT / path).read_text(encoding="utf-8") for path in S1_SOURCE_PATHS}
    texts[BOOTSTRAP] = texts[BOOTSTRAP].replace("redis_runtime=harness.redis_runtime,", "redis_runtime=None,")
    inventory = discover_serving_custody_inventory(SourceTree(texts))
    assert CustodySiteKind.NULL_HANDLE_CONSTRUCTION in {s.kind for s in inventory.sites}
    assert not inventory.retained_handle
    assert serving_custody._source_retention(inventory).outcome is CustodyOutcome.NOT_DEMONSTRATED


def test_dropping_the_retained_handle_from_source_makes_retention_false() -> None:
    texts = {path: (ROOT / path).read_text(encoding="utf-8") for path in S1_SOURCE_PATHS}
    mutated = texts[BOOTSTRAP].replace("redis_runtime=harness.redis_runtime,", "")
    assert mutated != texts[BOOTSTRAP]
    texts[BOOTSTRAP] = mutated
    inventory = discover_serving_custody_inventory(SourceTree(texts))
    assert not inventory.retained_handle
    rows = (serving_custody._source_retention(inventory),)
    assert rows[0].outcome is CustodyOutcome.NOT_DEMONSTRATED
    assert derive_s1_classification(rows) == "MISSING"


def test_a_serving_graph_that_reaches_the_shared_loop_is_a_retention_defect() -> None:
    texts = {path: (ROOT / path).read_text(encoding="utf-8") for path in S1_SOURCE_PATHS}
    texts["src/optimus/telemetry/redis_sink.py"] += "\n\ndef _leak(coro):\n    from optimus.redis.async_bridge import sync_await\n    return sync_await(coro)\n"
    inventory = discover_serving_custody_inventory(SourceTree(texts))
    assert inventory.shared_loop_reaches == 1
    assert serving_custody._source_retention(inventory).outcome is CustodyOutcome.NOT_DEMONSTRATED


# --- classification and ruling are derived -------------------------------------------


def _rows(**outcomes: str) -> tuple[CustodyObservation, ...]:
    return tuple(
        CustodyObservation(
            scenario=scenario,
            outcome=CustodyOutcome(outcomes.get(scenario.value, "DEMONSTRATED")),
            detail="control",
            evidence_digest="0" * 64,
        )
        for scenario in CustodyScenario
    )


def test_classification_is_canonical_only_when_every_scenario_is_demonstrated() -> None:
    """MUTATION: a hard-coded MISSING after B; MUTATION: a hard-coded CANONICAL before B."""
    assert derive_s1_classification(_rows()) == "CANONICAL"
    for scenario in CustodyScenario:
        assert derive_s1_classification(_rows(**{scenario.value: "NOT_DEMONSTRATED"})) == "MISSING", scenario
    assert derive_s1_classification(_rows()[:-1]) == "MISSING", "a missing scenario is not a demonstrated one"
    assert derive_s1_classification(tuple(row.to_dict() for row in _rows())) == "CANONICAL"


def test_the_ruling_names_the_classification_and_the_undemonstrated_scenarios() -> None:
    inventory = {"retained_handle": True, "redis_stage_last": True, "shared_loop_reaches": 0,
                 "serving_shutdown_order": ["adapter", "redis_runtime"]}
    canonical = derive_s1_ruling(_rows(), inventory)
    assert "CANONICAL" in canonical and "Not demonstrated: none" in canonical
    missing = derive_s1_ruling(_rows(startup_rollback="NOT_DEMONSTRATED"), inventory)
    assert "MISSING" in missing and "Not demonstrated: startup_rollback" in missing
    assert "not live Redis acceptance" in missing
    assert entry_ruling(S1_MEASUREMENT_ENTRY, inventory, [row.to_dict() for row in _rows()]) == canonical
    assert entry_ruling("identity.echo_bound_modules", inventory, []) != canonical


# --- the rollback probe observes the product, never its own cleanup (R2) ---------------


def test_the_rollback_probe_records_the_product_disposition_before_fallback_cleanup(tmp_path, monkeypatch) -> None:
    """R2 MUTATION: the product rollback replaced by a no-op; probe cleanup must not cover for it."""
    from optimus.acp import bootstrap

    monkeypatch.setattr(bootstrap, "_rollback_redis_runtime", lambda runtime, failure: None)
    row = serving_custody._probe_startup_rollback(tmp_path)
    assert row.outcome is CustodyOutcome.NOT_DEMONSTRATED
    assert "fallback_cleanup_needed=True" in row.detail
    assert "state=OPEN" in row.detail


def test_the_configured_handoff_probe_refuses_a_null_server_handle(tmp_path, monkeypatch) -> None:
    """R2 MUTATION: the configured composition hands the server no runtime."""
    from optimus.acp import bootstrap

    real = bootstrap.AcpStreamServer

    def _null_handoff(**kwargs):
        kwargs["redis_runtime"] = None
        return real(**kwargs)

    monkeypatch.setattr(bootstrap, "AcpStreamServer", _null_handoff)
    row = serving_custody._probe_configured_handoff(tmp_path)
    assert row.outcome is CustodyOutcome.NOT_DEMONSTRATED
    assert "server_holds_same_runtime=False" in row.detail


def test_the_custody_digest_is_content_only_and_writes_nothing(tmp_path, monkeypatch) -> None:
    """Plan 9.96: serving_custody._digest serializes scenario facts ONLY to hash them."""
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    facts = {"scenario": CustodyScenario.NORMAL_EOF_TEARDOWN, "path": tmp_path, "closed": True}
    digest = serving_custody._digest(facts)
    assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest)
    assert serving_custody._digest(dict(reversed(list(facts.items())))) == digest
    assert serving_custody._digest({**facts, "closed": False}) != digest
    assert set(tmp_path.iterdir()) == before, "the digest helper wrote something"


def _facts_of(row) -> dict[str, str]:
    return dict(item.split("=", 1) for item in row.detail.split(";"))


def test_the_cancellation_probe_retains_only_its_outcome_vocabulary(tmp_path) -> None:
    """Plan 9.96 (_drive:logger_export is an AST overmatch on task.exception()): the probe keeps a
    FIXED outcome vocabulary and an allowlisted error category, nothing else; on the measured tree
    the outcome is 'cancelled' and the category 'none'."""
    row = serving_custody._probe_cancellation(tmp_path)
    facts = _facts_of(row)
    assert facts["task_outcome"] in serving_custody.TASK_OUTCOME_VOCABULARY, row.detail
    assert facts["task_error_category"] in serving_custody.ERROR_CATEGORY_VOCABULARY, row.detail
    assert (facts["task_outcome"], facts["task_error_category"]) == ("cancelled", "none"), row.detail
    assert row.outcome is CustodyOutcome.DEMONSTRATED, row.detail


_SYNTHETIC_MARKER = "synthetic-sensitive-marker-" + "X" * 8192


def _serve_ndjson_that_fails_after_cleanup(exception_factory):
    """The reviewer's R15 shape: let the REAL cancellation cleanup run, then fail at that boundary."""
    from optimus.acp.server import AcpStreamServer

    original = AcpStreamServer.serve_ndjson

    async def _fail_after_normal_cleanup(self, *args, **kwargs):
        try:
            return await original(self, *args, **kwargs)
        except asyncio.CancelledError:
            raise exception_factory() from None

    return _fail_after_normal_cleanup


@pytest.mark.parametrize(
    ("factory", "category"),
    [
        (lambda: RuntimeError(_SYNTHETIC_MARKER), "runtime-error"),
        (lambda: OSError(_SYNTHETIC_MARKER), "os-error"),
        # An exception TYPE whose very name carries the marker: the category must come from
        # isinstance against the fixed list, never from the class name.
        (lambda: type("Leak" + _SYNTHETIC_MARKER, (Exception,), {})(_SYNTHETIC_MARKER), "other"),
    ],
)
def test_a_failing_serving_task_persists_a_content_free_failure_never_its_text(tmp_path, monkeypatch, factory, category) -> None:
    """R15 MUTATION: the probe used to retain `returned:<repr(exc)>` -- unrestricted exception text
    that `_observation` put in the detail and the real sidecar writer persisted verbatim (an
    8,226-character synthetic marker reached the sealed sidecar). Now: the failure stays visible
    (NOT_DEMONSTRATED, outcome 'returned', an allowlisted category) and the marker is absent from the
    observation AND from the bytes the real writer seals."""
    from optimus.acp.server import AcpStreamServer

    monkeypatch.setattr(AcpStreamServer, "serve_ndjson", _serve_ndjson_that_fails_after_cleanup(factory))
    row = serving_custody._probe_cancellation(tmp_path / "workspace")
    facts = _facts_of(row)
    assert row.outcome is CustodyOutcome.NOT_DEMONSTRATED, row.detail
    assert (facts["task_outcome"], facts["task_error_category"]) == ("returned", category), row.detail
    assert _SYNTHETIC_MARKER not in row.detail and "X" * 64 not in row.detail
    assert len(row.detail) < 512, len(row.detail)
    for value in facts.values():
        assert len(value) <= 64, value

    result = {
        "inventory": {"kind": "serving-custody", "sites": [], "serving_shutdown_order": []},
        "inventory_identifiers": sorted(s.value for s in CustodyScenario),
        "observations": [row.to_dict()],
    }
    reference = write_evidence_sidecar(
        directory=tmp_path / "evidence", record_id="r15-control", entry="s1.serving_custody",
        binding={}, result=result,
    )
    sealed = (tmp_path / "evidence" / reference.location).read_bytes()
    assert b"synthetic-sensitive-marker" not in sealed and b"X" * 64 not in sealed
    assert b'"outcome":"NOT_DEMONSTRATED"' in sealed and b"task_outcome=returned" in sealed
    assert f"task_error_category={category}".encode() in sealed


def test_a_serving_task_that_never_settles_is_recorded_as_pending(tmp_path, monkeypatch) -> None:
    """The third outcome of the fixed vocabulary, exercised with a short settle budget."""
    from optimus.acp.server import AcpStreamServer

    original = AcpStreamServer.serve_ndjson

    async def _ignores_the_first_cancellation(self, *args, **kwargs):
        try:
            return await original(self, *args, **kwargs)
        except asyncio.CancelledError:
            await asyncio.sleep(2.0)  # a second cancellation (loop shutdown) interrupts this sleep

    monkeypatch.setattr(AcpStreamServer, "serve_ndjson", _ignores_the_first_cancellation)
    monkeypatch.setattr(serving_custody, "_CANCELLATION_SETTLE_SECONDS", 0.2)
    row = serving_custody._probe_cancellation(tmp_path)
    facts = _facts_of(row)
    assert (facts["task_outcome"], facts["task_error_category"]) == ("pending", "none"), row.detail
    assert row.outcome is CustodyOutcome.NOT_DEMONSTRATED


def test_error_category_is_derived_from_type_only() -> None:
    assert serving_custody.error_category(None) == "none"
    assert serving_custody.error_category(asyncio.CancelledError()) == "cancelled"
    assert serving_custody.error_category(TimeoutError("t")) == "timeout"
    assert serving_custody.error_category(FileNotFoundError("f")) == "os-error"
    assert serving_custody.error_category(ValueError("v")) == "value-error"
    assert serving_custody.error_category(RuntimeError("r")) == "runtime-error"
    named = type("Secret" + "Y" * 200, (Exception,), {})("Z" * 200)
    assert serving_custody.error_category(named) == "other"
    assert set(serving_custody.ERROR_CATEGORY_VOCABULARY) >= {"none", "other", "runtime-error"}


def test_a_late_submission_refusal_is_recorded_from_a_fixed_vocabulary(tmp_path) -> None:
    row = serving_custody._probe_late_submission(tmp_path)
    facts = _facts_of(row)
    assert facts["refusal"] in serving_custody.REFUSAL_VOCABULARY, row.detail
    assert facts["refusal"] == "RedisLoopOwnerClosed", row.detail


def test_an_unexpected_late_submission_failure_is_recorded_content_free(tmp_path, monkeypatch) -> None:
    """R15: a refusal that is NOT the expected type must not carry its class name (or anything else)."""
    from optimus.agent.state_store import RedisAgentStateStore

    leak = type("Leak" + _SYNTHETIC_MARKER, (Exception,), {})

    def _refuse(self, operation):
        raise leak(_SYNTHETIC_MARKER)

    monkeypatch.setattr(RedisAgentStateStore, "submit", _refuse)
    row = serving_custody._probe_late_submission(tmp_path)
    facts = _facts_of(row)
    assert facts["refusal"] == "other-exception", row.detail
    assert _SYNTHETIC_MARKER not in row.detail and "X" * 64 not in row.detail
    assert row.outcome is CustodyOutcome.NOT_DEMONSTRATED


def test_a_failing_earlier_stage_still_demonstrates_custody_on_this_tree(tmp_path) -> None:
    row = serving_custody._probe_prior_stage_failure(tmp_path)
    assert row.outcome is CustodyOutcome.DEMONSTRATED, row.detail


# --- the execution closure is enforced (R3) --------------------------------------------


def _binding_with(paths: tuple[str, ...], dependencies: tuple[str, ...]) -> EnvironmentBinding:
    return EnvironmentBinding(
        interpreter_executable="C:/python.exe", interpreter_version="3.14", prefix="C:/venv",
        source_fingerprint="a" * 64,
        module_origins=tuple((path, str(ROOT / path), "b" * 64) for path in paths),
        dependency_files=tuple((name, "c" * 64) for name in dependencies),
    )


def test_a_binding_that_omits_an_executing_product_file_is_refused() -> None:
    """R3 MUTATION: a declared floor lower than what actually ran."""
    recorder = ExecutionClosureRecorder(ROOT)
    recorder.product_files.update({"src/optimus/guardrails/pre_tool.py", "src/optimus/acp/server.py"})
    with pytest.raises(ExecutingSourceMismatch, match="pre_tool.py"):
        verify_execution_closure(recorder, _binding_with(("src/optimus/acp/server.py",), ("redis",)))
    verify_execution_closure(
        recorder, _binding_with(("src/optimus/acp/server.py", "src/optimus/guardrails/pre_tool.py"), ("redis",))
    )


def test_a_binding_that_omits_an_executing_distribution_is_refused() -> None:
    recorder = ExecutionClosureRecorder(ROOT)
    recorder.site_top_levels.add("keyring")
    bound = ("src/optimus/acp/server.py",)
    with pytest.raises(ExecutingSourceMismatch, match="keyring"):
        verify_execution_closure(recorder, _binding_with(bound, ("redis",)))
    verify_execution_closure(recorder, _binding_with(bound, ("redis", "keyring")))


def test_the_recorder_sees_work_on_threads_started_while_armed() -> None:
    import threading

    from optimus.redis.async_bridge import RedisLoopOwner

    recorder = ExecutionClosureRecorder(ROOT)
    with recorder:
        owner = RedisLoopOwner(name="s1-recorder-control")
        try:
            owner.run_sync(lambda: __import__("asyncio").sleep(0))
        finally:
            owner.close(timeout=5.0)
        threading.Thread(target=lambda: None).start()
    assert "src/optimus/redis/async_bridge.py" in recorder.product_files


# --- the real measurement, through the public path -----------------------------------


def test_the_measured_revision_demonstrates_every_scenario() -> None:
    """The load-bearing GREEN: on this tree, S1 is CANONICAL because the wiring is demonstrated."""
    inventory, observations = _measure_s1()
    by_scenario = {row["scenario"]: row for row in observations}
    assert set(by_scenario) == {s.value for s in CustodyScenario}
    for scenario, row in by_scenario.items():
        assert row["outcome"] == "DEMONSTRATED", (scenario, row["detail"])
    assert inventory["retained_handle"] and inventory["redis_stage_last"]
    assert inventory["shared_loop_reaches"] == 0
    assert derive_s1_classification(tuple(observations)) == "CANONICAL"
    assert "server_holds_same_runtime=True" in by_scenario["configured_handoff_teardown"]["detail"]
    assert "fallback_cleanup_needed=False" in by_scenario["startup_rollback"]["detail"]


def test_a_null_handoff_measures_missing_through_the_public_path(tmp_path) -> None:
    """R2 COUNTEREXAMPLE INVERTED: the reviewer's null-handoff mutation now measures MISSING."""
    copy = _mutated_copy(tmp_path, "null-handoff", "redis_runtime=harness.redis_runtime,", "redis_runtime=None,")
    _inventory, observations = _measure_s1(copy)
    by_scenario = {row["scenario"]: row for row in observations}
    assert by_scenario["source_retention"]["outcome"] == "NOT_DEMONSTRATED"
    assert by_scenario["configured_handoff_teardown"]["outcome"] == "NOT_DEMONSTRATED"
    assert derive_s1_classification(tuple(observations)) == "MISSING"


def test_an_omitted_rollback_measures_missing_through_the_public_path(tmp_path) -> None:
    """R2 COUNTEREXAMPLE INVERTED: the reviewer's no-op rollback mutation now measures MISSING."""
    copy = _mutated_copy(
        tmp_path, "rollback-noop",
        "    try:\n        redis_runtime.close()\n    except Exception as exc:",
        "    try:\n        pass  # reviewer fault: omit product rollback\n    except Exception as exc:",
    )
    _inventory, observations = _measure_s1(copy)
    by_scenario = {row["scenario"]: row for row in observations}
    assert by_scenario["startup_rollback"]["outcome"] == "NOT_DEMONSTRATED"
    assert "fallback_cleanup_needed=True" in by_scenario["startup_rollback"]["detail"]
    assert derive_s1_classification(tuple(observations)) == "MISSING"


def test_a_sealed_s1_record_verifies_and_an_edited_ruling_is_refused(tmp_path) -> None:
    """MUTATION: the ruling is edited over unchanged retained rows."""
    records = measure_current(
        plans=default_measurement_plan(repository_root=ROOT, entries=(S1_MEASUREMENT_ENTRY,)),
        repository_root=ROOT, evidence_directory=tmp_path,
    )
    [record] = records
    assert record.record_id == "CM-s1-serving_custody" and record.hypothesis_id == "S1"
    assert "CANONICAL" in record.ruling
    sealed = AuditArtifact.from_dict(json.loads(SEALED.read_text(encoding="utf-8")))
    from tools.plan1126_runtime_audit.current_envelope import build_successor_artifact

    successor = build_successor_artifact(sealed, records)
    [payload] = verify_current_records(successor, tmp_path)
    assert payload["entry"] == S1_MEASUREMENT_ENTRY
    assert len(payload["observations"]) == len(CustodyScenario)

    from dataclasses import replace

    edited = replace(successor, current_measurement_records=(
        replace(record, ruling=record.ruling.replace("CANONICAL", "MISSING")),
    ))
    with pytest.raises(RetainedEvidenceError, match="ruling does not match"):
        verify_current_records(edited, tmp_path)


# --- a lowered floor is refused BEFORE any evidence is produced (R3 negative controls) ---


CHILD_CASES = ROOT / "tests" / "unit" / "tools" / "plan1126_runtime_audit" / "measurement_child_cases.py"


def _child_case(case: str) -> dict:
    import subprocess
    import sys
    import tempfile

    from tools.plan1126_runtime_audit.measurement import fresh_child_environment

    with tempfile.TemporaryDirectory(prefix="plan1126-s1-control-") as cache:
        completed = subprocess.run(
            [sys.executable, str(CHILD_CASES), str(ROOT), case], cwd=str(ROOT),
            capture_output=True, text=True, timeout=1800, env=fresh_child_environment(cache),
        )
    assert completed.returncode == 0, f"{case}: {completed.stderr[-2000:]}"
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_a_floor_lowered_below_an_executing_module_is_refused_before_evidence() -> None:
    """R3 MUTATION: the declared S1 floor omits a product file the scenarios execute."""
    outcome = _child_case("s1_lowered_floor_module")
    assert outcome["dropped_is_bound"] is False
    assert outcome["rows_returned"] == 0
    assert outcome["refusal"] and "pre_tool.py" in outcome["refusal"]


def test_a_floor_lowered_below_an_executing_distribution_is_refused_before_evidence() -> None:
    outcome = _child_case("s1_lowered_floor_distribution")
    assert outcome["dropped_distribution_bound"] is False
    assert outcome["rows_returned"] == 0
    assert outcome["refusal"] and "pydantic" in outcome["refusal"]


def test_the_h5_probe_branches_are_closure_checked_too() -> None:
    """R3: the same check applies to H5's new B probe branches (the leaf bundle module)."""
    outcome = _child_case("h5_lowered_floor_module")
    assert outcome["dropped_is_bound"] is False
    assert outcome["rows_returned"] == 0
    assert outcome["refusal"] and "harness_runtime.py" in outcome["refusal"]
