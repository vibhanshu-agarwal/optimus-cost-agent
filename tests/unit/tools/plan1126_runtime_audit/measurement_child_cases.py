"""Controls that must run INSIDE a real measurement child, invoked as a subprocess.

An authorizing execution context can only be issued inside a measurement child now -- fresh
interpreter, private and empty bytecode cache -- so every control about what such a context
does and does not authorize has to run there too. Running them in the pytest process would
only ever exercise the refusal to issue one at all, which is a different control.

Not named ``test_*`` on purpose: pytest must not collect it. The tests spawn it with
``measurement.fresh_child_environment`` and read one JSON object from stdout:

    <python> measurement_child_cases.py <checkout> <case>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CHECKOUT = Path(sys.argv[1]).resolve()
CASE = sys.argv[2]
sys.path[:0] = [str(CHECKOUT), str(CHECKOUT / "src")]

from tools.plan1126_runtime_audit import queue_policy, shutdown  # noqa: E402
from tools.plan1126_runtime_audit.measurement import (  # noqa: E402
    MeasurementSpecification,
    establish_verified_execution,
)
from tools.plan1126_runtime_audit.registry import entry_source_paths  # noqa: E402
from tools.plan1126_runtime_audit.source import (  # noqa: E402
    ExecutingSourceMismatch,
    GitCommitSource,
    SourceTree,
    source_fingerprint,
)

H5 = shutdown.H5_MEASUREMENT_ENTRY
H9 = queue_policy.H9_MEASUREMENT_ENTRY
MERGED = "5ea8f8f71548eb05a8562a10e98667e3d2061c4d"  # pragma: allowlist secret - historical baseline pin

def tree(paths) -> SourceTree:
    return SourceTree({path: (CHECKOUT / path).read_text(encoding="utf-8") for path in paths})


def identity_for(entry: str, measured: SourceTree, extra=()) -> SourceTree:
    """Bound text for every module the ENTRY requires, read from its own requirements.

    Derived rather than listed: the issuer widens the caller's specification to the entry's
    requirements, and a hand-maintained list silently stops covering them the moment an
    entry starts executing something new.
    """
    from tools.plan1126_runtime_audit.registry import entry_requirements

    held = {path: measured.read_text(path) for path in measured.paths()}
    for path in (*entry_requirements(entry).paths, *extra):
        held.setdefault(path, (CHECKOUT / path).read_text(encoding="utf-8"))
    return SourceTree(held)


def issue(entry: str, measured: SourceTree, *, paths=("tools/plan1126_runtime_audit/measurement.py",)):
    return establish_verified_execution(
        entry=entry,
        measured=measured,
        identity=identity_for(entry, measured, paths),
        spec=MeasurementSpecification(
            paths=paths,
            import_roots=(str(CHECKOUT / "src"), str(CHECKOUT)),
            dependencies=(),
            source_fingerprint=source_fingerprint(measured, measured.paths()),
        ),
    )


def counting_h5(execution, measured, inventory=None):
    inventory = inventory if inventory is not None else shutdown.discover_shutdown_inventory(
        measured, overlay=measured
    )
    calls: list[int] = []
    original = shutdown._probe_resource  # noqa: SLF001

    def controlled(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("control marker: a probe ran that should not have")

    shutdown._probe_resource = controlled  # noqa: SLF001
    try:
        shutdown.shutdown_schedule_observations(
            inventory=inventory, repeats=1, source=measured, execution=execution
        )
        return len(calls), None
    except ExecutingSourceMismatch as exc:
        return len(calls), str(exc)
    finally:
        shutdown._probe_resource = original  # noqa: SLF001


def counting_h9(execution, source, inventory=None):
    inventory = inventory if inventory is not None else queue_policy.discover_queue_inventory(source)
    calls: list[int] = []
    original = queue_policy.RedisRuntime

    def controlled(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("control marker: a probe ran that should not have")

    queue_policy.RedisRuntime = controlled
    try:
        queue_policy.connection_health_observations(
            inventory=inventory, source=source, execution=execution
        )
        return len(calls), None
    except ExecutingSourceMismatch as exc:
        return len(calls), str(exc)
    finally:
        queue_policy.RedisRuntime = original


def emit(payload) -> None:
    print(json.dumps(payload))


if CASE == "underscoped_specification":
    # The reviewer's under-scoped request, with the entry named. The issuer raises the floor
    # rather than honouring it, so the context that comes back is scoped to what H5 executes.
    measured = tree(entry_source_paths(H5))
    execution = issue(H5, measured, paths=("tools/plan1126_runtime_audit/source.py",))
    calls, refusal = counting_h5(execution, measured)
    emit({
        "requested_paths": ["tools/plan1126_runtime_audit/source.py"],
        "bound_modules": sorted(path for path, _, _ in execution.binding.module_origins),
        "dependencies": [name for name, _ in execution.binding.dependency_files],
        "probe_calls": calls,
        "refusal": refusal,
    })

elif CASE == "context_for_another_entry":
    h9_measured = tree(entry_source_paths(H9))
    execution = issue(H9, h9_measured)
    calls, refusal = counting_h5(execution, tree(entry_source_paths(H5)))
    emit({"issued_for": execution.entry, "offered_to": H5, "probe_calls": calls, "refusal": refusal})

elif CASE == "h5_context_at_h9":
    # The mirror of context_for_another_entry: H9 must refuse an H5 context too, or the
    # scope check would only exist on one of the two entries that share a runtime.
    h5_measured = tree(entry_source_paths(H5))
    execution = issue(H5, h5_measured)
    calls, refusal = counting_h9(execution, tree(entry_source_paths(H9)))
    emit({"issued_for": execution.entry, "offered_to": H9, "probe_calls": calls, "refusal": refusal})

elif CASE == "replace_rebadges_the_context":
    from dataclasses import replace

    measured = tree(entry_source_paths(H9))
    execution = issue(H9, measured)
    try:
        replace(execution, entry=H5)
        emit({"replace_refused": False, "refusal": None})
    except ExecutingSourceMismatch as exc:
        emit({"replace_refused": True, "refusal": str(exc)})

elif CASE == "probe_internal_mismatch":
    # A mismatch raised INSIDE _probe_resource used to be caught by the schedule's
    # per-probe `except Exception` and filed as a `probe_error` row -- a measurement that
    # looks taken while recording that it was refused.
    measured = tree(entry_source_paths(H5))
    execution = issue(H5, measured)

    def refusing(*args, **kwargs):
        raise ExecutingSourceMismatch("control marker: executing module is not the bound source")

    shutdown.verify_executing_module = refusing
    try:
        rows = shutdown.shutdown_schedule_observations(
            inventory=shutdown.discover_shutdown_inventory(measured, overlay=measured),
            repeats=1, source=measured, execution=execution,
        )
        emit({"raised": False, "probe_error_rows": sum(
            1 for row in rows if "probe_error" in row.cause_effect
        )})
    except ExecutingSourceMismatch as exc:
        emit({"raised": True, "refusal": str(exc), "probe_error_rows": 0})

elif CASE == "closed_window":
    measured = tree(entry_source_paths(H5))
    execution = issue(H5, measured)
    execution.close()
    calls, refusal = counting_h5(execution, measured)
    emit({"probe_calls": calls, "refusal": refusal})

elif CASE == "h5_historical_inventory":
    measured = tree(entry_source_paths(H5))
    execution = issue(H5, measured)
    historical_source = GitCommitSource(MERGED, repository=CHECKOUT)
    historical = shutdown.discover_shutdown_inventory(
        SourceTree({p: historical_source.read_text(p) for p in shutdown.H5_SOURCE_PATHS})
    )
    calls, refusal = counting_h5(execution, measured, inventory=historical)
    emit({"probe_calls": calls, "refusal": refusal})

elif CASE == "h5_tampered_source":
    measured = tree(entry_source_paths(H5))
    execution = issue(H5, measured)
    inventory = shutdown.discover_shutdown_inventory(measured, overlay=measured)
    tampered = SourceTree({p: measured.read_text(p) for p in measured.paths()})
    tampered._files["src/optimus/redis/runtime.py"] += "# not the executing source"  # noqa: SLF001
    calls, refusal = counting_h5(execution, tampered, inventory=inventory)
    emit({"probe_calls": calls, "refusal": refusal})

elif CASE == "h9_foreign_inventory":
    measured = tree(entry_source_paths(H9))
    execution = issue(H9, measured)
    historical_source = GitCommitSource(MERGED, repository=CHECKOUT)
    foreign = queue_policy.discover_queue_inventory(
        SourceTree({p: historical_source.read_text(p) for p in queue_policy.H9_SOURCE_PATHS})
    )
    calls, refusal = counting_h9(execution, measured, inventory=foreign)
    emit({"probe_calls": calls, "refusal": refusal})

elif CASE == "h9_tampered_source":
    measured = tree(entry_source_paths(H9))
    execution = issue(H9, measured)
    inventory = queue_policy.discover_queue_inventory(measured)
    tampered = SourceTree({p: measured.read_text(p) for p in measured.paths()})
    tampered._files["src/optimus/redis/runtime.py"] += "# not the executing source"  # noqa: SLF001
    calls, refusal = counting_h9(execution, tampered, inventory=inventory)
    emit({"probe_calls": calls, "refusal": refusal})

elif CASE in {"s1_lowered_floor_module", "s1_lowered_floor_distribution", "h5_lowered_floor_module"}:
    # Round 2, R3: a registry floor lowered below what the entry EXECUTES. The issuer binds
    # the lowered floor faithfully, so the binding is genuine; the execution-closure recorder
    # then refuses the measurement because something that ran is outside that binding.
    from tools.plan1126_runtime_audit import registry, serving_custody

    S1 = serving_custody.S1_MEASUREMENT_ENTRY
    if CASE == "s1_lowered_floor_module":
        entry, dropped = S1, "src/optimus/guardrails/pre_tool.py"
        registry._REQUIRED_PATHS[S1] = tuple(p for p in registry._REQUIRED_PATHS[S1] if p != dropped)  # noqa: SLF001
    elif CASE == "s1_lowered_floor_distribution":
        entry, dropped = S1, "pydantic"
        registry._REQUIRED_DISTRIBUTIONS[S1] = tuple(d for d in registry._REQUIRED_DISTRIBUTIONS[S1] if d != dropped)  # noqa: SLF001
    else:
        entry, dropped = H5, "src/optimus/acp/harness_runtime.py"
        registry._REQUIRED_PATHS[H5] = tuple(p for p in registry._REQUIRED_PATHS[H5] if p != dropped)  # noqa: SLF001
    measured = tree(entry_source_paths(entry))
    execution = issue(entry, measured)
    bound = sorted(path for path, _, _ in execution.binding.module_origins)
    rows_returned = 0
    refusal = None
    try:
        if entry == S1:
            inventory = serving_custody.discover_serving_custody_inventory(measured)
            rows = serving_custody.serving_custody_observations(inventory=inventory, source=measured, execution=execution)
        else:
            inventory = shutdown.discover_shutdown_inventory(measured, overlay=measured)
            rows = shutdown.shutdown_schedule_observations(inventory=inventory, repeats=1, source=measured, execution=execution)
        rows_returned = len(rows)
    except ExecutingSourceMismatch as exc:
        refusal = str(exc)
    emit({"entry": entry, "dropped": dropped, "dropped_is_bound": dropped in bound,
          "dropped_distribution_bound": dropped in [n for n, _ in execution.binding.dependency_files],
          "rows_returned": rows_returned, "refusal": refusal})

else:  # pragma: no cover - the tests only ask for known cases
    raise SystemExit(f"unknown case {CASE!r}")
