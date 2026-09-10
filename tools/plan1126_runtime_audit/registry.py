"""The allowlist of measurement entries a fresh child interpreter may execute.

An explicit registry rather than an importable dotted path: the child receives its entry
name over stdin, and a name is executable only if it appears here.

Each entry also declares **what it must bind**, and that declaration is a floor the
caller cannot lower. A public child once ran the Redis health measurement with a single
harmless reviewer-created module bound and no Redis dependency at all -- the caller chose
the module set, so the caller chose how little the evidence meant. An entry now names its
product runtime, its bridge, the probe implementation that actually executes, and the
installed dependency closure; :func:`~.measurement.run_child_measurement` unions those in
before any identity is established.

Each entry returns its **complete** inventory and its **complete** observation rows, each
row carrying the inventory identifier it derives from. Discovery happens against the same
measured source the entry is bound to, so historical and current identifiers stay in
separate inventories and can never be silently interchanged.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from .measurement import VerifiedExecution, distribution_closure
from .source import SourceTree

#: Bound by every entry that executes the Redis runtime: the code under measurement.
_REDIS_RUNTIME_PATHS = (
    "src/optimus/redis/async_bridge.py",
    "src/optimus/redis/runtime.py",
)
#: Bound by every entry: the gate that establishes identity is itself executing code.
_GATE_PATHS = ("tools/plan1126_runtime_audit/measurement.py",)

#: Everything `shutdown._probe_resource` imports and executes, beyond the Redis pair.
#: An entry that binds only the modules it is *about* leaves the rest of what it runs
#: unbound, which is the same gap one level down.
_H5_PROBE_EXECUTES = (
    "src/optimus/acp/harness_runtime.py",
    "src/optimus/acp/local_infra.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/spec.py",
    "src/optimus/agent/state_store.py",
    "src/optimus/mcp/client_catalog.py",
    "src/optimus/mcp/client_disposition.py",
    "src/optimus/mcp/client_sdk.py",
    "src/optimus/mcp/client_supervisor.py",
    "src/optimus/mcp/local_ipc.py",
    "src/optimus/redis/__init__.py",
    "tools/plan1126_runtime_audit/source.py",
)


@dataclass(frozen=True)
class EntryRequirements:
    """The minimum identity an entry binds, whatever the caller asked for."""

    paths: tuple[str, ...]
    dependencies: tuple[str, ...]


def _h5_shutdown_schedule(
    *, source: SourceTree, execution: VerifiedExecution, options: Mapping[str, Any]
) -> dict[str, Any]:
    from .shutdown import discover_shutdown_inventory, shutdown_schedule_observations

    repeats = int(options.get("repeats", 1))
    inventory = discover_shutdown_inventory(source, overlay=source)
    observations = shutdown_schedule_observations(
        inventory=inventory, repeats=repeats, source=source, execution=execution
    )
    identifiers = sorted({record.close_path_id for record in inventory.resources if record.schedule_applicable})
    return {
        "inventory": {
            "kind": "shutdown-close-paths",
            "source_fingerprint": inventory.source_fingerprint,
            "close_path_count": inventory.close_path_count,
            "close_sites": [asdict(site) for site in inventory.close_sites],
            "resources": [record.to_dict() for record in inventory.resources],
        },
        "inventory_identifiers": identifiers,
        "observations": [
            {**asdict(item), "observation_id": item.close_path_id} for item in observations
        ],
    }


def _h9_connection_health(
    *, source: SourceTree, execution: VerifiedExecution, options: Mapping[str, Any]
) -> dict[str, Any]:
    from .queue_policy import (
        HealthScenario,
        connection_health_observations,
        discover_queue_inventory,
        health_probe_surface,
    )

    del options
    inventory = discover_queue_inventory(source)
    # The identifier names the health-probe surface the measurement actually drives, as
    # DISCOVERED in the measured source. An inventory from another tree names other lines,
    # so its rows cannot be passed off as these.
    surface = health_probe_surface(inventory)
    observations = connection_health_observations(
        inventory=inventory, source=source, execution=execution
    )
    # The scenario universe is the ENUM, not the scenarios that happened to be observed.
    # Deriving it from the rows would let the observations decide which observations are
    # admissible, which is the circularity the retained-evidence contract exists to break.
    scenarios = sorted(scenario.value for scenario in HealthScenario)
    return {
        "inventory": {
            "kind": "queue-and-health-sites",
            "queue_count": inventory.queue_count,
            "health_probe_surface": surface,
            "site_kinds": sorted({str(site.site_kind) for site in inventory.sites}),
            **inventory.to_dict(),
        },
        "inventory_identifiers": [f"{surface}|{scenario}" for scenario in scenarios],
        "observations": [
            {**item.to_dict(), "observation_id": f"{surface}|{item.scenario.value}"}
            for item in observations
        ],
    }


def _identity_echo_bound_modules(
    *, source: SourceTree, execution: VerifiedExecution, options: Mapping[str, Any]
) -> dict[str, Any]:
    """Report what the verified child actually loaded, module by module.

    A self-check rather than a product measurement: it exists so the execution-identity
    machinery can be exercised over the real public path -- including against planted
    stale bytecode -- without pointing a Redis probe at a fixture.
    """
    import importlib
    from pathlib import Path

    del source, options
    private_cache = Path(execution.cache_prefix).resolve()
    rows: list[dict[str, Any]] = []
    for path, origin, digest in execution.binding.module_origins:
        module = importlib.import_module(path.removesuffix(".py").replace("/", ".").removeprefix("src."))
        cached = getattr(module, "__cached__", None)
        rows.append({
            "observation_id": path,
            "origin": origin,
            "digest": digest,
            # The RELATIONSHIP, not the path. The private cache is a fresh temporary
            # directory on every run, so retaining its absolute path would make identical
            # measurements produce different evidence -- and the path is not the claim
            # anyway. The claim is that nothing was loaded from a cache we did not create.
            "cached_under_private_prefix": (
                cached is not None and Path(cached).resolve().is_relative_to(private_cache)
            ),
            # Module-level string constants the caller can use to prove WHICH text ran,
            # as opposed to which text is on disk.
            "constants": {
                name: value
                for name, value in sorted(vars(module).items())
                if name.startswith("PLAN1126_") and isinstance(value, str)
            },
        })
    identifiers = sorted(row["observation_id"] for row in rows)
    return {
        "inventory": {"kind": "bound-modules", "paths": identifiers},
        "inventory_identifiers": identifiers,
        "observations": rows,
    }


def _s1_serving_custody(
    *, source: SourceTree, execution: VerifiedExecution, options: Mapping[str, Any]
) -> dict[str, Any]:
    """Seam 2, checkpoint B: S1 serving custody, derived from source AND demonstrated wiring."""
    from .serving_custody import (
        CustodyScenario,
        discover_serving_custody_inventory,
        serving_custody_observations,
    )

    del options
    inventory = discover_serving_custody_inventory(source)
    observations = serving_custody_observations(inventory=inventory, source=source, execution=execution)
    # The identifier universe is the ENUM, not the rows that happened to be observed.
    return {
        "inventory": inventory.to_dict(),
        "inventory_identifiers": sorted(scenario.value for scenario in CustodyScenario),
        "observations": [item.to_dict() for item in observations],
    }


#: Everything the S1 scenarios EXECUTE (round 2, R3): the real bootstrap composition, the
#: real server teardown, the consumers they wire, the guardrails and MCP wiring the
#: composition constructs, and the launch/policy modules it reads. Derived from a
#: recorded execution trace of every scenario on both platforms -- not from the minimum
#: that makes a test pass -- and enforced at measurement time by the execution-closure
#: recorder in `serving_custody_observations`, which refuses evidence when anything
#: executed lies outside the binding. The list is therefore a floor that cannot be
#: lowered silently: a new executing module fails the closure check until it is added.
_S1_PROBE_EXECUTES = (
    "src/optimus/acp/bootstrap.py",
    "src/optimus/acp/conversation.py",
    "src/optimus/acp/debug_trace.py",
    "src/optimus/acp/dispatcher.py",
    "src/optimus/acp/failure_notes.py",
    "src/optimus/acp/framing.py",
    "src/optimus/acp/harness_runtime.py",
    "src/optimus/acp/launch_policy.py",
    "src/optimus/acp/lifecycle.py",
    "src/optimus/acp/local_gateway_secrets.py",
    "src/optimus/acp/local_infra.py",
    "src/optimus/acp/operator_verify.py",
    "src/optimus/acp/outbound_writer.py",
    "src/optimus/acp/preflight.py",
    "src/optimus/acp/request_ids.py",
    "src/optimus/acp/server.py",
    "src/optimus/acp/shapes.py",
    "src/optimus/acp/spec.py",
    "src/optimus/acp/subprocess_env.py",
    "src/optimus/agent/defaults.py",
    "src/optimus/agent/runner.py",
    "src/optimus/agent/state_store.py",
    "src/optimus/config/gateway.py",
    "src/optimus/gateway/client.py",
    "src/optimus/guardrails/audit.py",
    "src/optimus/guardrails/command_safety.py",
    "src/optimus/guardrails/network_safety.py",
    "src/optimus/guardrails/path_safety.py",
    "src/optimus/guardrails/permissions.py",
    "src/optimus/guardrails/pre_tool.py",
    "src/optimus/mcp/__init__.py",
    "src/optimus/mcp/client_catalog.py",
    "src/optimus/mcp/client_config.py",
    "src/optimus/mcp/client_disposition.py",
    "src/optimus/mcp/client_sdk.py",
    "src/optimus/mcp/client_supervisor.py",
    "src/optimus/mcp/client_trust.py",
    "src/optimus/mcp/local_ipc.py",
    "src/optimus/mcp/runtime.py",
    "src/optimus/telemetry/events.py",
    "src/optimus/telemetry/fanout.py",
    "src/optimus/telemetry/jsonl.py",
    "src/optimus/telemetry/observability.py",
    "src/optimus/telemetry/redis_adapter.py",
    "src/optimus/telemetry/redis_sink.py",
    "src/optimus_security/launch_manifest.py",
)


_ENTRIES: dict[str, Callable[..., dict[str, Any]]] = {
    "h5.shutdown_schedule": _h5_shutdown_schedule,
    "h9.connection_health": _h9_connection_health,
    "identity.echo_bound_modules": _identity_echo_bound_modules,
    "s1.serving_custody": _s1_serving_custody,
}

_REQUIRED_PATHS: dict[str, tuple[str, ...]] = {
    "h5.shutdown_schedule": (
        *_GATE_PATHS, *_REDIS_RUNTIME_PATHS, *_H5_PROBE_EXECUTES,
        "tools/plan1126_runtime_audit/shutdown.py",
    ),
    "h9.connection_health": (*_GATE_PATHS, *_REDIS_RUNTIME_PATHS, "tools/plan1126_runtime_audit/queue_policy.py"),
    "identity.echo_bound_modules": _GATE_PATHS,
    "s1.serving_custody": (
        *_GATE_PATHS, *_REDIS_RUNTIME_PATHS, *_S1_PROBE_EXECUTES,
        "tools/plan1126_runtime_audit/serving_custody.py",
    ),
}

_REQUIRED_DISTRIBUTIONS: dict[str, tuple[str, ...]] = {
    "h5.shutdown_schedule": ("redis",),
    "h9.connection_health": ("redis",),
    "identity.echo_bound_modules": (),
    # R3: the installed distributions the S1 scenarios execute (recorded on every thread):
    # pydantic for the composed records, keyring -- with its jaraco/more-itertools closure --
    # reached by the configured composition's launch-policy and conversation wiring, and
    # redis for the runtime pair. The closure recorder refuses the measurement if anything
    # outside this closure runs.
    "s1.serving_custody": ("redis", "keyring", "pydantic"),
}


def entry_source_paths(name: str) -> tuple[str, ...]:
    """The paths whose text an entry MEASURES, as opposed to the modules it binds.

    Per entry, because H5 and H9 discover their inventories from different path sets. The
    identity self-check measures no product tree at all: it reports what the verified
    child loaded, and inventing a tree for it would only invite reading its result as a
    product measurement.
    """
    if name == "h5.shutdown_schedule":
        from .shutdown import H5_CURRENT_SOURCE_PATHS

        return H5_CURRENT_SOURCE_PATHS
    if name == "h9.connection_health":
        from .queue_policy import H9_SOURCE_PATHS

        return H9_SOURCE_PATHS
    if name == "identity.echo_bound_modules":
        return ()
    if name == "s1.serving_custody":
        from .serving_custody import S1_SOURCE_PATHS

        return S1_SOURCE_PATHS
    raise ValueError(f"{name!r} is not an allowlisted measurement entry")


def entry_requirements(name: str) -> EntryRequirements:
    """The minimum module and dependency closure ``name`` binds, regardless of the caller."""
    if name not in _ENTRIES:
        raise ValueError(f"{name!r} is not an allowlisted measurement entry")
    dependencies: set[str] = set()
    for distribution in _REQUIRED_DISTRIBUTIONS[name]:
        dependencies.update(distribution_closure(distribution))
    return EntryRequirements(
        paths=tuple(sorted(_REQUIRED_PATHS[name])),
        dependencies=tuple(sorted(dependencies)),
    )


def resolve_measurement_entry(name: str):
    """Resolve an allowlisted entry, refusing anything else."""
    try:
        return _ENTRIES[name]
    except KeyError as exc:
        raise ValueError(f"{name!r} is not an allowlisted measurement entry") from exc


def measurement_entry_names() -> tuple[str, ...]:
    return tuple(sorted(_ENTRIES))
