# Public Python API reference

This reference covers the bundled `optimus-cost-agent` distribution. Use the import
paths below for in-process code.
## Supported import paths

| Import from | Symbol |
| --- | --- |
| `context_engine` | `STRATEGIES` |
| `context_engine` | `SUMMARIZING_STRATEGIES` |
| `context_engine` | `ContractError` |
| `context_engine` | `HistoryRevision` |
| `context_engine` | `HistorySnapshot` |
| `context_engine` | `MaintenanceCallback` |
| `context_engine` | `MaintenanceRequest` |
| `context_engine` | `MaintenanceResult` |
| `context_engine` | `OrdinaryTurn` |
| `context_engine` | `PreparedView` |
| `context_engine` | `ProtectedTurnState` |
| `context_engine` | `ReuseResult` |
| `context_engine` | `StrategyParameters` |
| `context_engine` | `SummaryCheckpoint` |
| `context_engine` | `ViewLimits` |
| `context_engine` | `history_digest` |
| `context_engine` | `publish_checkpoint` |
| `context_engine` | `reuse_checkpoint` |
| `context_engine` | `turn_source_digest` |
| `context_engine.engine` | `ContextEngine` |
| `optimus_model_policy` | `EstimatorProfile` |
| `optimus_model_policy` | `ModelEntry` |
| `optimus_model_policy` | `Origin` |
| `optimus_model_policy` | `Policy` |
| `optimus_model_policy` | `RegistryError` |
| `optimus_model_policy` | `RegistrySnapshot` |
| `optimus_model_policy` | `Role` |
| `optimus_model_policy` | `Tier` |
| `optimus_model_policy` | `ValidationIssue` |
| `optimus_model_policy` | `load_registry` |
| `optimus_model_policy` | `validate_registry` |
| `optimus.telemetry` | `TelemetryEvent` |
| `optimus.telemetry` | `TelemetryEventKind` |

## Supported operations

- `ContextEngine.prepare_view`

## Context engine

Construct `ContextEngine()` to prepare a view of a sanitized, already-committed
history. The host supplies the snapshot, policy bounds, estimator, maintenance
callback and cancellation predicate.

| Name | Contract |
| --- | --- |
| `HistoryRevision` | Identifies committed history by session, generation, last committed turn and content digest. |
| `OrdinaryTurn` | Carries the sanitized prompt, plan and completion for one committed turn. |
| `ProtectedTurnState` | Carries that turn’s exact host authority, including outcome, effect state and approval facts. |
| `HistorySnapshot` | Holds immutable records. Ordinary and protected records must correspond in increasing turn order, and the revision must match the supplied history. |
| `StrategyParameters` | Supplies explicit token allocations, a maintenance call limit and prompt and format versions from the host’s policy. |
| `ViewLimits` | Supplies token and UTF-8 byte bounds, the host estimator and its identifier, and an optional remaining maintenance allowance. When set, the allowance can only tighten the parameter’s call limit. The estimator must be subadditive over concatenated text. |
| `MaintenanceCallback` | Synchronously accepts a `MaintenanceRequest` and returns a `MaintenanceResult`. The host owns provider access and accounting. |
| `MaintenanceRequest` | Carries sanitized input, the turn IDs to cover, the output limit and format and prompt versions. Exact protected authority is kept out of maintenance input. |
| `MaintenanceResult` | Carries summary text when present, correlation attempt IDs, status and finish status. A result arriving after cancellation is discarded. |
| `SummaryCheckpoint` | Carries an untrusted derived summary bound to a revision, strategy, parameters, format and covered ordinary source digests. |
| `ReuseResult` | Carries an accepted checkpoint adapted to the current revision, or no checkpoint and a refusal reason. |
| `PreparedView` | Carries disjoint head, tail, summarized and omitted turn groups. A view preserves the exact protected state. An unavailable result has a reason. |
| `ContractError` | Signals invalid contract input. An unavailable view is returned as a result for conditions such as insufficient capacity. |
| `STRATEGIES` | Lists the current strategies. Compaction summarizes earlier turns, hybrid can preserve an exact head before summarizing, and sliding window keeps a whole-turn suffix without maintenance. |
| `SUMMARIZING_STRATEGIES` | Lists the strategies that permit summary checkpoints. Current membership and ordering of either strategy collection may change. |

`prepare_view` takes a snapshot and explicit keyword arguments for the strategy,
parameters, limits, optional checkpoint, maintenance callback and cancellation
predicate. It returns a candidate `PreparedView` without storing it or changing the
snapshot. The host must check availability before using the candidate.

`history_digest` incorporates the ordinary and protected records in order.
`turn_source_digest` identifies the ordinary source of one turn. The same inputs
yield the same digest within one version. Treat returned digests as opaque values
for the current version’s contracts.

`reuse_checkpoint` validates session, revision, strategy, parameters, format,
coverage and source. `publish_checkpoint` decides whether a candidate still matches
the current revision and parameters and has escaped cancellation. The host writes
accepted state and settles any maintenance costs.

## Model policy

`load_registry` reads the caller’s defaults file and any overrides in argument
order. It skips `None` entries, combines mapping keys and replaces non-mapping
values such as lists. File reads can raise `OSError`. Invalid YAML and schema
validation failures raise `RegistryError`. Structural findings are reported
separately by `validate_registry` as a deterministically ordered
`tuple[ValidationIssue, ...]`. An empty tuple means that validation reported no
structural findings.

| Name | Documented reads |
| --- | --- |
| `RegistrySnapshot` | `policy`, the effective policy identity in `effective_hash`, and file-name and byte-digest provenance in `input_hashes`. |
| `Policy` | `policy_version`, `models` by model ID, `roles` by role and `estimators` by name on the returned snapshot. |
| `ModelEntry` | `origin` and `tier` describe recorded model classifications. |
| `EstimatorProfile` | `method`, `tokens_per_byte`, `per_message_tokens`, `fixed_tokens` and `verified` describe the recorded estimate profile. |
| `Origin`, `Tier`, `Role` | Classifiers for origin, cost tier and assignment role. Their member collections may evolve. |
| `RegistryError` | `code` distinguishes `YAML_REJECTED` from `SCHEMA_INVALID`. `detail` is diagnostic text. |
| `ValidationIssue` | `code` and `detail` describe a finding, with `model_id` and `role` when applicable. |

Read these records through the returned snapshot. The boundary covers these reads
and the two functions. Nested constructors, YAML layout and schema, cost claims,
model eligibility, route authorization and live admission have separate owners.

## Telemetry envelope

Construct `TelemetryEvent` with a `TelemetryEventKind`, `run_id`, `session_id`,
`request_id`, `occurred_at` and `payload`. The event validates its envelope and can
validate payloads for particular kinds. Per-kind payload shapes are outside this
reference.

`schema_version` identifies the event schema and `event_id` defaults to a generated
identity. `trace_id` defaults to `run_id` when not supplied.
`parent_span_id` and `gateway_request_id` are optional correlation fields.
`session_id` may be `None`. The model configuration is frozen at the top level.
Nested payload values can be mutable. Treat them as in-memory data.

`TelemetryEventKind` distinguishes the event’s purpose, such as model calls, tool
calls, gateway usage, guardrail audit, errors and logical turn settlement. The full
set and order of enum members may evolve. Construction in this example stays local
and uses synthetic data.

## Exclusions

- Import paths and symbols outside the table, including deeper aliases and wildcard imports.
- Context-engine memory, continuity, indexing, retrieval, storage and rendering, including prompt helpers.
- The other 14 model-policy facade exports, live routing and admission.
- The other ten telemetry facade exports, event factories, serialized wire formats,
  sinks, fanout, exporters and sensitive-data handling.
- Other Optimus runtime, transport, gateway, security and Evidence Handoff APIs, as
  well as CLI behavior, protocols, configuration tooling, tests and historical artifacts.

## Examples

### Context view

```python
from context_engine import (
    HistoryRevision,
    HistorySnapshot,
    MaintenanceRequest,
    MaintenanceResult,
    OrdinaryTurn,
    ProtectedTurnState,
    StrategyParameters,
    ViewLimits,
    history_digest,
)
from context_engine.engine import ContextEngine

turns = (OrdinaryTurn(1, "Question", "Plan", "Answer"),)
protected = (ProtectedTurnState(1, "completed", "none", ("example approval",)),)
revision = HistoryRevision("example-session", 1, 1, history_digest(turns, protected))
snapshot = HistorySnapshot(revision, turns, protected)
parameters = StrategyParameters(
    anchor_input_tokens=0,
    compaction_tail_input_tokens=256,
    hybrid_tail_input_tokens=256,
    summary_output_tokens=64,
    max_maintenance_calls=0,
    prompt_version="example",
    format_version="context-summary-v1",
)
limits = ViewLimits(
    history_input_tokens=1024,
    source_max_bytes=4096,
    transient_max_bytes=1024,
    maintenance_input_tokens=1024,
    maintenance_output_tokens=64,
    summary_max_bytes=128,
    estimate_history=lambda text: len(text.encode("utf-8")),
    estimator_id="example-bytes",
)


def offline_maintenance(request: MaintenanceRequest) -> MaintenanceResult:
    raise AssertionError("a sliding-window view needs no maintenance")


view = ContextEngine().prepare_view(
    snapshot,
    strategy="sliding_window",
    parameters=parameters,
    limits=limits,
    checkpoint=None,
    maintenance=offline_maintenance,
    cancelled=lambda: False,
)
```

The example uses synthetic policy bounds and keeps the committed turn and its
protected state in the resulting view.

### Registry inspection

```python
from pathlib import Path

from optimus_model_policy import load_registry, validate_registry

snapshot = load_registry(Path("registry.yaml"))
issues = validate_registry(snapshot)
```

Supply your own readable registry file. The snapshot records the effective policy
and file provenance. Validation only inspects the snapshot.

### Telemetry envelope

```python
from datetime import UTC, datetime

from optimus.telemetry import TelemetryEvent, TelemetryEventKind

event = TelemetryEvent(
    kind=TelemetryEventKind.ERROR,
    run_id="example-run",
    session_id=None,
    request_id="example-request",
    occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    payload={"note": "synthetic example"},
)
```

The event stays in memory and `event.trace_id` is `"example-run"`.
