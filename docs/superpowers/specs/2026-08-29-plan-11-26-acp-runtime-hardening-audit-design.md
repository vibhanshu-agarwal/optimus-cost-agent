# Plan 11.26 ACP Runtime Hardening Audit and Contract Design

**Status:** Draft for operator and independent reviewer approval.

**Date:** 2026-08-29

**Backlog owner:** `P11-FEAT-ACP-RUNTIME-HARDENING`

**Plan boundary:** Plan 11.26 is an audit-and-contract plan. It may add audit tooling,
derived oracles, characterization tests, fixture-only client qualification, and evidence
schemas. It does not authorize production-runtime changes, live-system execution, evidence
promotion, release, push, or merge.

## Decision Summary

Plan 11.26 will audit the ACP runtime by crossing two views:

1. vertical runtime responsibility segments; and
2. horizontal cross-cutting policy contracts.

A cross-cutting concern is centralized when it has one normative definition, one enforcement
contract, one vocabulary, and one conformance surface. It does not need to live in one physical
file. The design explicitly rejects both a file-by-file-only review and a single global runtime
state machine.

The audit begins from evidence, not from invented canon. Existing merged vocabulary such as
delivery settlement and Plan 11.18 error-code ownership is inherited. Proposed connection,
session, cancellation, resource, error-selection, and telemetry models remain falsifiable
hypotheses until their symbols and behavior are classified against the applicable baseline.

Plan 11.26 may finish with `PASS_WITH_FINDINGS`. It cannot close
`P11-FEAT-ACP-RUNTIME-HARDENING`. Independently schedulable production remediations receive later
linear Plan 11 numbers only after this audit establishes that they are needed.

## Governing Authority

- `AGENTS.md` governs intake, evidence tiers, prerequisites, plan fidelity, live ACP drivers,
  review checkpoints, and versioning.
- `CONTRIBUTING.md` governs branch, worktree, review, and commit practice.
- `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` is the sole live
  registry of priority, status, owner, and next gate.
- Plan 11.18 and `tests/unit/acp/test_error_code_registry.py` are authoritative for ACP error-code
  ownership and its schema-derived and AST-derived oracles.
- The merged Plan 11.25 delivery-settlement vocabulary is authoritative unless this audit finds
  concrete contradictory evidence.
- `acpx` from `github.com/openclaw/acpx` remains the independently authored ACP integration and
  live-evidence driver required by `AGENTS.md`. The additional TypeScript or Java SDK client is a
  comparison driver required by the hardening backlog entry; it does not replace acpx.

## Goals

1. Classify every in-scope cross-cutting runtime behavior as canonical, bypassed, duplicated,
   contradictory, missing, intentionally exceptional, provisional, or not present.
2. Establish evidence-backed contracts for task supervision, cancellation, resource lifetime,
   semantic error selection, telemetry/correlation, persistence/leases, delivery, backpressure,
   and connection health.
3. Produce machine-readable inventories and derived oracles that make omissions visible.
4. Characterize concurrency, shutdown, queue, Redis, and client-interoperability behavior with
   numeric, reproducible predicates.
5. Name independently mergeable remediation candidates without pre-authoring production fixes.

## Non-Goals

- Changing production ACP, Redis, telemetry, Gateway, client-MCP, approval, or launch behavior.
- Closing Plan 11.7 or reconciling its branches inside Plan 11.26.
- Replacing Zed or acpx.
- Repeating Plan 11.18's completed raw error-code ownership audit.
- Claiming acpx load-time replay visibility, graceful Zed shutdown, immediate Zed reopen, release
  readiness, or Phase 1 working-agent sign-off.
- Running Zed, acpx, an additional client, live Redis, Gateway calls, paid calls, evidence
  promotion, release, push, or merge without fresh explicit authorization.

## Baseline Policy

The audit records three distinct baselines.

| Baseline | Initial identity | Authority |
|---|---|---|
| Merged | `main@5ea8f8f71548eb05a8562a10e98667e3d2061c4d` | Binding for merged-only and both-aligned findings available today. |
| Runtime overlay | The Plan 11.7 runtime line containing accepted runtime-code commit `fac32284888850bacde93815265cbabe3afd4663` | Provisional only. It is not an ancestor of `main` or the other observed Plan 11.7 heads. |
| Binding integration candidate | Not yet nominated by Plan 11.7 | Required before any overlay-dependent finding or evidence becomes binding. |

Every hypothesis, matrix row, evidence record, and finding carries one of:

- `merged`;
- `overlay`;
- `both-aligned`;
- `both-divergent`; or
- `binding`.

Only `merged`, `both-aligned`, and later `binding` rows may produce binding findings. Overlay and
both-divergent rows may be classified and retained as provisional, but may not justify production
remediation until the binding integration candidate exists.

Plan 11.7 owns branch reconciliation and nomination of the binding integration candidate. Plan
11.26 explicitly scopes out all Definition-of-Done claims that depend on that unsatisfied
prerequisite. If Plan 11.7 does not satisfy it, Plan 11.26 may complete only its merged and
both-aligned audit surfaces and must report every binding/overlay-dependent row as scoped out with
`P11-FEAT-ZED-RESUME` as owner.

## Scope Model

### Full audit

The full audit covers the long-lived serving path and directly owned dependencies:

- composition and serving bootstrap;
- framing, stdio transport, request dispatch, and response delivery;
- ACP session, conversation, turn, lifecycle, and settlement behavior;
- session models/store when present on the applicable baseline;
- Redis runtime, agent state-store boundary, and telemetry Redis adapters;
- structured telemetry, debug tracing, redaction, and fanout;
- process- or session-owned client-MCP resources reached by the ACP server.

### Boundary audit

Entrypoint, preflight, local infrastructure, launch gate/policy, approvals, trusted paths,
credential resolution, and operator tooling are inspected only for:

- resource construction;
- ownership transfer;
- background work;
- timeout and cancellation propagation;
- failure propagation; and
- close/release behavior.

Their security, authorization, and operator-UX semantics are not re-adjudicated.

### Exclusions and custody

| Excluded work | Custody |
|---|---|
| Plan 11.7 branch reconciliation, Task 0 evidence, formal evidence, and closure | `P11-FEAT-ZED-RESUME` |
| Launch/trust and durable-approval policy correctness outside lifecycle interfaces | Existing Plan 9.96/11.15 authority; any new open obligation must enter the canonical backlog before Plan 11.26 closes. |
| Credential acquisition/rotation beyond ownership and redaction interfaces | `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` where applicable; otherwise assign a canonical backlog owner before deferral. |
| Gateway and agent reasoning/business semantics | Their existing canonical backlog feature owners; only ACP-facing lifecycle interfaces are in Plan 11.26. |
| Release, push, merge, evidence promotion, and working-agent sign-off | Existing release governance and the archived Plan 9.6 sign-off authority. |

## Runtime Segments

| Segment | Responsibility | Present anchors |
|---|---|---|
| Composition | Construct resources and declare ownership/shutdown order | ACP bootstrap and entrypoint |
| Transport | Stdio framing, reads/writes, EOF, and broken transport | `server.py`, `framing.py` |
| Protocol | ACP method dispatch, validation, and wire responses | `spec.py`, `dispatcher.py`, `errors.py`, `shapes.py` |
| Session | Identity, conversation, loading, persistence, lease, and recovery | `spec.py`, `conversation.py`, applicable session store/models |
| Turn execution | Task ownership, cancellation, and agent-run boundary | `spec.py`, `lifecycle.py`, agent interfaces |
| Delivery | Serialization, queueing, backpressure, send ownership, settlement | `outbound_writer.py`, `lifecycle.py`, `settlement.py` |
| Infrastructure | Redis client/pool lifetime, health, state and telemetry adapters | Redis runtime, agent state store, telemetry Redis adapters |
| Observability | Events, correlation, redaction, debug logging, export | telemetry package, `debug_trace.py` |

Zed, acpx, the additional SDK client, fixtures, unit harnesses, integration tests, and live Redis
form the verification plane. They are not production segments.

## Cross-Cutting Contract Candidates

Each candidate is one definition and one enforcement contract, not necessarily one module.

1. **Task supervision:** spawn, register, cancel, join, and account for owned work.
2. **Resource lifetime:** construct, transfer, close in dependency order, and close idempotently.
3. **Deadline/backpressure:** use one timeout vocabulary, numeric queue bounds, and explicit overload
   dispositions.
4. **Semantic error selection:** translate domain facts into wire errors at an ACP boundary while
   preserving Plan 11.18 code ownership.
5. **Correlation context:** propagate stable connection/session/turn/request/operation identity.
6. **Delivery settlement:** preserve authoritative send and effect outcomes.
7. **Telemetry:** construct one semantic event and fan it out through contained, redacting sinks.
8. **Persistence/lease:** acquire, renew, mutate, release, expire, and recover under one ownership
   contract when the binding baseline contains the durable session path.

Consumer modules may not invent competing state names, error meanings, timeout rules, correlation
fields, or cleanup semantics. The audit must first prove whether a candidate already exists,
partially exists, or is absent.

## Hypothesis Register

| ID | Hypothesis | Baseline scope | Derived-from evidence | Audit question |
|---|---|---|---|---|
| H1 | Connection lifetime is implicitly owned by `AcpStreamServer.serve_ndjson()` | `both-divergent` | Reader task, request-task set, and baseline-specific `finally` blocks | Is there one complete, bounded, idempotent lifecycle or only local cleanup? |
| H2 | Durable session ownership is represented by typed store outcomes and adapter-held lease identity | `overlay` | Overlay-only create/load/acquire/mutate/release outcomes and `AcpDuplexAdapter.aclose()` | Do they form a coherent lifecycle with complete failure semantics? |
| H3 | Turn cancellation and effect gating are centralized in `TurnControl` | `both-aligned` | `CancelResult`, `request_session_cancel()`, `request_transport_teardown()`, and start leases | Does every child operation use the control, or are there bypasses? |
| H4 | Delivery settlement has established canonical vocabulary | `both-aligned` | `SendState`, `SendOutcome`, `Settlement`, `FinalDelivery`, `RpcResponseDelivery`, `ConversationCommit`, `EffectState` | Is the vocabulary consistently enforced from queue admission through conversation commit? |
| H5 | Shutdown ordering is complete and ownership-correct | `both-divergent` | Merged synchronous `adapter.close_all()` path versus overlay awaited lease release and Redis close | Which ordering is reachable and correct on the binding tree? |
| H6 | Raw ACP error-code ownership is canonical and mechanically enforced | `merged` | Plan 11.18, vendored schema oracle, AST oracle, empty legacy allowlist | Do all new audit tools preserve this settled authority? |
| H7 | Semantic failure selection is correct and exhaustive | `merged` | Inline named-constant selections in protocol boundary call sites | Are eight semantic categories mapped consistently for retry, certainty, wire output, and cleanup? |
| H8 | Runtime telemetry uses one correlation meaning and one event-construction approach | `merged` | `TelemetryEvent`, `ACP_TURN_SETTLEMENT`, debug trace, stderr, scalar/plural Gateway IDs | Are events joinable, redacted, and semantically consistent? |

Each completed hypothesis record contains exact symbol citations, supporting tests, contradicting
paths, untested transitions, baseline scope, reviewer ruling, and the resulting contract if one is
justified.

## Carried Unclassified Seeds

These are audit inputs, not pre-classified defects.

1. On the merged baseline, the serving `RedisRuntime` is constructed for the ACP server but has no
   observed serving-path close. Short-lived preflight paths do close their runtimes. Because the
   supported production shape is one stdio session per process and process exit reclaims resources,
   this is initially an ownership/orderly-shutdown question, not a claimed live leak.
2. On the merged baseline, `gateway_request_id` is used as a singular value while
   `gateway_request_ids` is used as a plural tuple in planning/debug paths. This may be a legitimate
   one-turn-to-many-Gateway-calls relationship or an inconsistent correlation contract.

## Classification Vocabulary

Every discovered item receives exactly one classification:

- `CANONICAL`;
- `CANONICAL_BYPASSED`;
- `DUPLICATED`;
- `CONTRADICTORY`;
- `MISSING`;
- `INTENTIONALLY_EXCEPTIONAL`;
- `PROVISIONAL_OVERLAY`;
- `NOT_PRESENT`;
- `SUPERSEDED`; or
- `UNCLASSIFIED`.

`INTENTIONALLY_EXCEPTIONAL`, `PROVISIONAL_OVERLAY`, `NOT_PRESENT`, and `SUPERSEDED` count as
classified. `UNCLASSIFIED` must be zero at the applicable audit gate. The broad catches in
`sanitize_protocol_error_message()` and `sanitize_protocol_error_data()` begin as
`INTENTIONALLY_EXCEPTIONAL` because their purpose is fail-closed sanitization; the audit may change
that ruling only with contrary evidence.

## Semantic Error Contract

Plan 11.18 already established `errors.py` as the sole production owner of JSON-RPC, ACP, and
Optimus error codes and mechanically prohibits raw production literals elsewhere. Plan 11.26 does
not reconstruct that registry.

The open audit problem is selection correctness and exhaustiveness. Expected domain outcomes use
typed results/enums. Exceptional failures carry semantic facts. ACP boundaries select a named code,
safe message/data, retry disposition, effect certainty, telemetry disposition, and cleanup
obligation.

The audit classifies at least these semantic categories:

| Category | Required distinctions |
|---|---|
| Protocol/input | Framing, invalid request/parameters, unknown method; deterministic and non-ambiguous |
| Cancellation/deadline | Client cancellation, teardown, timeout; preserve cause and interruption phase |
| Ownership/concurrency | Active owner, lost lease, revision conflict, duplicate request; distinguish retryable contention from lost ownership |
| Dependency availability | Redis/Gateway availability; distinguish definite failure from uncertain post-write outcome |
| Integrity | Missing, corrupt, unsupported durable state; fail closed without overwrite/recreation |
| Delivery | Client rejection, write failure, flush ambiguity; preserve authoritative settlement |
| Resource lifecycle | Close timeout, partial shutdown, unquiesced work; name owner and phase |
| Invariant/programming | Impossible transition or unclassified exception; internal wire error plus contained diagnostics |

`asyncio.CancelledError` may not be flattened into a generic internal failure. Unknown exceptions
fail closed to `INTERNAL_ERROR` without unsanitized wire details.

## Telemetry and Logging Contract

The merged telemetry envelope already defines schema/event/trace identity, run, session, request,
parent span, Gateway request, occurrence time, kind, and payload. The audit determines whether
connection, turn, operation, client, lifecycle phase, and running-artifact identity are additional
required fields. It may not assume them into canon before coverage is measured.

Correlation rules:

- one field has one meaning everywhere;
- missing identity is explicit rather than replaced with competing synthetic aliases;
- child operations inherit trace/session/turn context and receive distinct operation/event identity;
- wire error, lifecycle event, and settlement event from one failure are deterministically joinable;
- scalar and plural Gateway identifiers must have a documented cardinality relationship or be
  classified as a violation.

`ACP_TURN_SETTLEMENT` is the worked standard: exact content-free payload keys, enum-backed
vocabulary, validation against missing/extra fields, and contained sink delivery.

The audit derives a bounded runtime event vocabulary for connection, task, session/lease,
queue/backpressure, dependency health, close, semantic failure/wire mapping, and settlement.
Structured telemetry, debug trace, and stderr call sites are inventoried. The target common approach
constructs one redacted semantic event and fans it out to authorized sinks. Direct stderr is reserved
for bootstrap failure or last-resort telemetry failure. Sink failure may not alter runtime control
flow.

## Machine-Readable Audit Artifact

The canonical artifact contains at least:

```text
schema_version
merged_commit
overlay_commit
binding_commit
baseline_reconciliation_status
running_artifact_provenance
static_audit_status
runtime_characterization_status
live_redis_status
acpx_status
additional_client_status
zed_status
live_interoperability_status
unclassified_finding_count
finding_counts_by_classification
discovered_multipliers
computed_run_cost
gate_status
```

`live_interoperability_status` is one of `UNRUN`, `PARTIAL`, `INVALID`, or `COMPLETE`. A rendered
message such as `PARTIAL — LIVE INTEROPERABILITY MATRIX UNRUN` explains the field but never replaces
it. The applicable live gate fails unless the field is `COMPLETE`; rows whose subject is
`NOT_PRESENT` or scoped out by Plan 11.7 do not make `COMPLETE` unreachable.

### Running artifact provenance

Every live row records:

- binding commit;
- executable path and SHA-256;
- package name/version;
- build/install manifest digest;
- embedded source commit or equivalent immutable build provenance;
- launcher-command digest;
- client binary/package provenance; and
- environment fingerprint.

Workspace `git_sha` is not running-code provenance. A live row is invalid unless the installed
artifact's build provenance equals the binding commit. Plan 11.26 may implement external build and
verification manifests for audit evidence; it does not need to change production runtime behavior.

## Derived Oracles and Inventories

Independent static/runtime oracles derive, rather than hand-maintain, inventories of:

- task creation and cancellation points;
- queues, locks, producers, consumers, and declared bounds;
- resource constructors, ownership transfers, close/release paths, and close ordering;
- broad catches and cancellation handlers;
- protocol error selections and typed outcome-to-wire mappings;
- Redis clients/pools and session-store operations;
- telemetry, debug trace, stderr, redaction, and sink call sites; and
- delivery start/publication/settlement consumers.

Plan 11.18's schema-derived plus AST-derived precedent is the minimum bar. A green hand-maintained
list is insufficient.

## Characterization Matrix

The Plan 11.26 matrix characterizes the applicable baseline; it is not a production-runtime
acceptance gate. Characterization failures are findings. Acceptance against derived contracts and
numbers belongs to later remediation plans.

Every row records baseline scope and applicability. Timing uses a monotonic clock. Valid-run failure
thresholds are zero. An infrastructure-invalid run is neither pass nor fail; more than two invalid
attempts per scenario changes that scenario to `BLOCKED`.

| Area | Baseline scope | Characterization predicate |
|---|---|---|
| Static ownership | Applicable baseline | Derived inventories cover every in-scope site; `UNCLASSIFIED == 0`. |
| Error-code canon | `merged`/`binding` | Existing Plan 11.18 schema and AST oracles remain green with an empty legacy allowlist. |
| Semantic error selection | `merged`/`binding` | Generated matrix covers every selection; 100 safe message/data cases per semantic category record leakage and divergence. |
| Delivery worked example | `both-aligned` | AST derives every send/settlement consumer; transition model executes 1,000 commit-derived seeds plus the frozen regression corpus. |
| Cancellation races | Applicable baseline | For each discovered cancellation point, execute 256 schedules at concurrency 2, 4, and 8 in the terminal tier. |
| Repeated lifecycle | Applicable baseline | Orderly EOF, cancellation, reader failure, writer failure, and malformed termination each run 100 times on Windows and 100 times on WSL2/Linux in the terminal tier. |
| Shutdown timing | Applicable baseline | Measure cooperative shutdown against 2 seconds, injected non-cooperative disposition against 5 seconds, total cleanup against 10 seconds, and individual close against 2 seconds; these are characterization thresholds, not pre-audit canon. |
| Idempotent close | Applicable baseline | For every discovered close path and each of five terminal causes, invoke close three times and measure underlying close/release count and repeat-call latency against 100 ms. |
| Queue/backpressure | Applicable baseline | Cross-check construction-site bound and runtime behavior; stop the consumer and attempt 10,000 admissions. Accepting 10,000 proves only that no effective bound was observed below 10,000 unless the constructor independently declares unbounded behavior. Waiting over 100 ms without an explicit outcome is `BLOCKING_WITHOUT_POLICY`. |
| Live Redis owner/revision | `binding` when durable path exists | 50 accelerated create/acquire/mutate/release cycles and 100 owner/revision races with 5-second operation timeouts. |
| Lease boundary | `overlay` until binding includes/supersedes it | Derive the lease duration from the binding runtime constant; test one tick before and at expiry plus 1,000 derived seeds around the boundary. Do not confuse it with session-retention TTL. |
| Real lease recovery | `binding` when durable path exists | One authorized wall-clock crash/recovery run: no recovery before the derived lease duration and recovery within a reviewed scheduler tolerance after expiry. |
| Resource growth | Applicable baseline | After 100 server cycles, compare with a control-derived allowlist of expected persistent executor/Redis threads; report unexpected task/thread/pool growth. |
| Telemetry schema | `merged`/`binding` | Generate 10,000 events and missing/extra/invalid-field cases across the derived runtime vocabulary. |
| Redaction | `merged`/`binding` | Run 1,000 nested payload cases; report prohibited values in every authorized sink and fallback diagnostic. |
| Correlation | `merged`/`binding` | Require 100% completeness for fields the reviewed schema marks required; classify scalar/plural Gateway cardinality. |
| Sink failure | Applicable baseline | For each discovered sink, inject 100 failures and compare runtime/wire outcome with the no-failure control. |
| Multi-client | `binding` | 50 rounds each at 2, 4, and 8 clients for one session, plus 50 distinct-session rounds. |
| acpx | `binding`; separately authorized | 25 valid supported-matrix runs using policy-required acpx. Known acpx replay-visibility limits remain non-probative. |
| Additional SDK client | `binding`; separately authorized | 25 valid runs using the qualified TypeScript primary or Java fallback, including raw replay ordering where supported. |
| Real Zed | `binding`; separately authorized | Five valid operator runs covering initialization, new, load/resume, continued prompt, and normal Zed close classified as abrupt termination. |

The session retention default, when present, is separately derived from
`DEFAULT_ACP_SESSION_TTL_SECONDS` and its authorized monotonic-limit configuration. No matrix row
uses the lease duration as a synonym for session retention.

## Seed, Regression, and Rerun Policy

Fresh randomized seed for iteration `n`:

```text
first_64_bits(SHA256(binding_commit + scenario_id + n))
```

Every seed and environment fingerprint is recorded. A failing seed is copied into a frozen literal
regression corpus that is independent of later binding commits. Each applicable run replays the
frozen corpus in addition to freshly derived seeds.

After a correction:

1. rerun the affected per-task family;
2. rerun its Plan 11.26 task-group tier at task-group close; and
3. run the full applicable characterization matrix once at Plan 11.26 terminal review.

The full matrix does not rerun after every intermediate correction.

## Evidence Tiers and Computed Cost

Within Plan 11.26, **task group** means one of the audit groups in the task sequence below. It does
not mean a later production-remediation plan. The terminal tier is Plan 11.26 characterization, not
production acceptance. Later remediation plans define their own evidence tiers against the reviewed
contracts.

| Tier | Plan 11.26 execution |
|---|---|
| Per task | Relevant derived oracles, frozen corpus, 32 commit-derived seeds per affected scenario, and 10 repeated local runs. Target under five minutes where feasible; measured overruns update computed cost rather than waive evidence. |
| Per task group | All group tests, frozen corpus, 256 seeds per affected scenario, and 25 repeated runs per applicable platform. |
| Terminal characterization | Full applicable offline matrix and only those live rows separately authorized. Executes once after every task group passes. |

Static inventory emits:

- `N_cancellation_points`;
- `N_queues`;
- `N_sinks`; and
- `N_close_paths`.

The artifact computes at least:

```text
cancellation_schedules = N_cancellation_points * concurrency_levels * seed_count
queue_admissions = N_queues * admission_probe_count
sink_failure_runs = N_sinks * sink_failure_count
idempotent_close_invocations = N_close_paths * 3 * 5
```

Measured per-task p50/p95 durations and discovered multipliers produce the estimated terminal wall
time. The plan does not promise a fixed total before these values exist.

Iteration evidence is checkpointed so an interrupted batch resumes from the next unexecuted
iteration while preserving completed records. WSL2 runs use distro-native Redis rather than a host
port-forward. High-volume Windows and WSL2 pytest output is written directly to files rather than
piped through another process.

## Additional Independent Client

The primary additional client candidate is the official stable-v1 TypeScript SDK,
`@agentclientprotocol/sdk`, using its real client API and connection transport. It is independently
authored relative to Optimus but does not displace acpx.

- Primary source: <https://github.com/agentclientprotocol/typescript-sdk>
- Present toolchain: Node `v26.5.0`, npm `11.17.0`.

The same-task fallback is the official Java SDK stdio `AcpClient`.

- Primary source: <https://github.com/agentclientprotocol/java-sdk>
- Present toolchain: Java `25.0.3 LTS`, Maven `3.9.6`.

The present toolchain versions in this section and the prerequisites table were established from
recorded command output on this host during review. The sole exception is acpx `0.12.0`: its launcher
was observed, but its version is operator-confirmed and must be independently re-recorded by the
execution environment.

The primary and fallback package versions/commits are not yet pinned or executed. Early Task 3 must
pin, resolve, compile, and execute the TypeScript candidate against a non-production fixture. If it
does not qualify, Task 3 exercises the Java fallback before any dependent client-matrix work begins.
No project-authored JSON-RPC client may substitute for acpx or the qualified additional SDK client.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Merged audit baseline is `main@5ea8f8f71548eb05a8562a10e98667e3d2061c4d`. | yes | reviewing architect | merely unauthorized — not applicable while satisfied |
| code/state | Plan 11.7 nominates a binding integration candidate and reconciles or formally supersedes competing runtime deltas. | no | Plan 11.7 / `P11-FEAT-ZED-RESUME` | genuinely hard — external prerequisite; binding-baseline evidence is scoped out of Plan 11.26 until satisfied |
| tooling/binaries | Plan 11.26 branch/worktree is isolated from latest main and Plan 11.26 is unclaimed. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | uv `0.11.29` is present. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | Node `v26.5.0` and npm `11.17.0` are present for the TypeScript candidate. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | Java `25.0.3 LTS` and Maven `3.9.6` are present for the Java fallback. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | TypeScript SDK package version/commit is pinned, installed, compiled, and fixture-executed. | unknown | operator | merely unauthorized — establish in early Task 3 before dependent client work |
| tooling/binaries | Java SDK fallback version/commit is pinned and fixture-executed if the primary fails qualification. | unknown | operator | merely unauthorized — establish in early Task 3 before declaring the client gate blocked |
| tooling/binaries | acpx `0.12.0` launcher is present; version is operator-confirmed and must be re-recorded by the execution environment. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | Zed `1.17.2` (`c8e44cfa7bda9b2e22c8d6934d78969352e7f61a`) is installed at `C:\Users\pc\AppData\Local\Programs\Zed\Zed.exe`. | yes | operator | merely unauthorized — not applicable while satisfied |
| platforms | Windows execution environment is present. | yes | operator | merely unauthorized — not applicable while satisfied |
| platforms | WSL2 environment and distro-native Redis/TimeSeries availability are established. | unknown | operator | genuinely hard — establish in early Task 1 before WSL-dependent evidence |
| services | Windows live Redis/TimeSeries availability, port ownership, and isolation are established. | unknown | operator | merely unauthorized — establish in early Task 1 before live-Redis evidence |
| credentials/authority | Optimus Gateway credentials and paid-call authority are available for any live prompt scenario. | unknown | operator | merely unauthorized — establish capability only in early Task 1; do not print or persist secrets |
| credentials/authority | Fresh authorization exists for Zed, acpx, additional client, Redis mutation, Gateway/model calls, and paid calls. | no | operator | merely unauthorized — live tasks remain dormant until granted |
| human interaction | Trusted Zed workspace and operator availability for five GUI runs are established. | unknown | operator | merely unauthorized — establish in early Task 1 before scheduling Zed evidence |
| cost/time | Paid-call budget and the authorized wall-clock lease-expiry window are accepted. | no | operator | merely unauthorized — derive duration from binding code and authorize before live scheduling |
| evidence/tooling | Installed running-artifact provenance can be proved independently of workspace `git_sha`. | no | Plan 11.26 Task 2 | genuinely absent — build the external manifest/verifier before any live row can be valid |

Every `unknown` prerequisite is resolved by Task 1 or Task 3 before a dependent task. No Plan 11.26
Definition-of-Done claim depends on an unsatisfied Plan 11.7 prerequisite: binding, overlay-dependent,
lease, and live-resume evidence remains explicitly scoped out with Plan 11.7 as owner until that
prerequisite is satisfied.

Review-time documentation verification reported `65 passed` for `tests/unit/docs/`. That result
establishes that the documentation suite was green; it does not establish that this prerequisites
table was mechanically validated because the prerequisite-hygiene checker scans
`docs/superpowers/plans`, not `docs/superpowers/specs`. The future implementation plan must carry
this entire prerequisites table forward verbatim, including its header, lowercase status values, and
disposition wording, and must run the checker against that plan artifact.

## Task Sequence

### Task 0 — Baseline and review-intake gate

- Read and verify `docs/superpowers/reviews/plan-11-26-review-checkpoints.md` when present.
- After a conflict check, claim Plan 11.26 in the canonical backlog by recording its owner, active
  status, and next gate before audit execution begins.
- Record exact merged, overlay, and observed Plan 11.7 refs.
- Record which hypothesis/matrix rows are binding, provisional, divergent, absent, or scoped out.
- Stop if chat summary, checkpoint log, backlog, and Git facts disagree.

### Task 1 — Resolve machine/service/authority unknowns

- Establish WSL2 and distro-native Redis/TimeSeries availability.
- Establish Windows Redis/TimeSeries availability, port ownership, and isolation.
- Establish Gateway credential capability without revealing or persisting credentials.
- Establish trusted Zed workspace and operator availability.
- Update the audit artifact; do not run live scenarios.
- Scope out each still-unsatisfied dependent evidence row with its named owner.

### Task 2 — Audit schema, derived oracles, checkpoints, and provenance

- Define the machine-readable artifact and classification schema.
- Build independent AST/runtime inventory oracles.
- Build atomic iteration checkpoints and computed-cost output.
- Build external running-artifact build/install manifest verification.
- Add tests that fail when required fields, baseline scope, provenance, or classification are absent.

### Task 3 — Qualify the additional independent client

- Pin and resolve the TypeScript SDK.
- Compile and run its real client API against a non-production fixture.
- If it fails qualification, pin and execute the Java SDK fallback in the same task.
- Record client package/build provenance and supported matrix.
- Preserve acpx as the mandatory integration/live driver.

### Task 4 — Complete the delivery worked example

- Derive every delivery start/publication/settlement consumer.
- Complete H4 with symbol citations, contradiction search, tests, baseline scope, and reviewer ruling.
- Establish the evidence-record standard every later audit group must match.

### Task 5 — Audit task supervision and cancellation

- Inventory task creation, callback ownership, child work, cancellation, timeout, and escape paths.
- Emit `N_cancellation_points` and the derived scenario family.
- Characterize both-aligned behavior without prescribing a new supervisor implementation.

### Task 6 — Audit resource ownership and shutdown

- Inventory construction, transfer, dependency ordering, close/release, and partial teardown.
- Emit `N_close_paths`.
- Rule on the merged serving-Redis seed.
- Compare baseline-specific shutdown blocks without promoting overlay behavior to merged canon.

### Task 7 — Audit semantic error selection

- Preserve and run Plan 11.18's settled oracles.
- Derive every semantic outcome/exception-to-wire selection.
- Classify the eight categories for retry, certainty, public output, telemetry, and cleanup.
- Treat canonical sanitizer broad catches as intentionally exceptional unless contradicted.

### Task 8 — Audit telemetry, logging, and correlation

- Derive event, trace, stderr, redaction, and sink call sites.
- Emit `N_sinks`.
- Rule on scalar/plural Gateway request identity.
- Compare each proposed runtime event with the `ACP_TURN_SETTLEMENT` worked standard.

### Task 9 — Audit queues, backpressure, and connection health

- Derive every queue, producer, consumer, declared bound, and health probe.
- Emit `N_queues`.
- Run bounded probes that distinguish declared unbounded behavior, no observed bound below the probe
  limit, and blocking without policy.

### Task 10 — Audit persistence and lease behavior when applicable

- Run only if the binding baseline contains or supersedes the durable session path.
- Derive lease and retention values from binding code.
- Keep ownership lease, record TTL, and session retention semantics distinct.
- Otherwise emit `NOT_PRESENT` or `PROVISIONAL_OVERLAY` and scope the evidence out to Plan 11.7.

### Task 11 — Run tiered characterization evidence

- Run per-task and per-task-group offline tiers.
- Compute terminal cost from discovered multipliers.
- Run only separately authorized live rows with installed-artifact provenance.
- Checkpoint each iteration and preserve invalid-run reasons without cherry-picking.

### Task 12 — Synthesize contracts and remediation candidates

- Publish accepted canon, bypasses, contradictions, missing contracts, intentional exceptions,
  provisional rows, scoped-out rows, and rejected hypotheses.
- Map each binding finding to evidence and a named backlog owner.
- Recommend independently numbered production-remediation plans only where evidence justifies them.
- Update the canonical backlog with Plan 11.26's reviewed disposition, owner, and next gates for each
  accepted remediation candidate.
- Keep `P11-FEAT-ACP-RUNTIME-HARDENING` open.

## Planned Named Test Predicates

The implementation plan must map these predicates to exact files and commands:

- `test_audit_artifact_requires_baseline_scope_and_classification`
- `test_audit_artifact_live_status_is_machine_checkable`
- `test_running_artifact_provenance_matches_binding_commit`
- `test_derived_inventory_has_no_unclassified_sites`
- `test_delivery_contract_ast_covers_all_send_sites`
- `test_delivery_contract_model_1000_seed_schedule`
- `test_turn_cancellation_races_256_seed_matrix`
- `test_shutdown_causes_repeat_100_with_control_allowlist`
- `test_close_is_idempotent_across_discovered_paths`
- `test_queue_policy_cross_checks_constructor_and_10000_admissions`
- `test_session_lease_boundary_uses_binding_runtime_constant`
- `test_live_redis_owner_revision_races`
- `test_runtime_event_schema_generated_10000_cases`
- `test_runtime_redaction_generated_1000_cases`
- `test_runtime_correlation_chain_is_complete`
- `test_telemetry_sink_failures_are_contained`
- `test_regression_corpus_replays_frozen_literal_seeds`
- `test_computed_cost_includes_cancellation_queue_sink_and_close_multipliers`

## Review Gates

- **G0 — Intake:** prerequisites, baseline scope, scope-outs, and review checkpoint accepted.
- **G1 — Inventory:** derived inventories complete; `UNCLASSIFIED == 0` for applicable rows.
- **G2 — Contract review:** each hypothesis independently reviewed; H4 is the worked standard.
- **G3 — Client qualification:** TypeScript primary or same-task Java fallback qualified; acpx remains
  mandatory.
- **G4 — Per-group evidence:** per-task and per-task-group characterization passes as an evidence
  mechanism; runtime failures are classified findings rather than hidden.
- **G5 — Terminal characterization:** applicable authorized matrix completes with checkpoints,
  computed cost, and running-artifact provenance.
- **G6 — Disposition:** reviewer accepts findings, scope-outs, and each proposed independently
  numbered remediation candidate.

## Definition of Done

Plan 11.26 is complete only when:

1. every applicable discovered site is classified and baseline-scoped;
2. every hypothesis has a reviewer disposition or an explicit Plan 11.7-owned scope-out;
3. Plan 11.18 error-code authority and delivery-settlement canon remain mechanically protected;
4. every `unknown` prerequisite was resolved early or its dependent evidence was scoped out with a
   named owner;
5. the TypeScript primary or Java fallback was qualified before dependent client work;
6. acpx remains the required ACP integration/live driver;
7. the machine-readable artifact, computed cost, frozen corpus, checkpoints, and provenance rules
   are executable and reviewed;
8. every live claim uses real named dependencies and the exact installed artifact provenance;
9. each binding finding maps to named evidence and canonical backlog custody;
10. proposed production remediations are independently schedulable and receive later linear Plan 11
    numbers only after separate review; and
11. the backlog still records `P11-FEAT-ACP-RUNTIME-HARDENING` as open unless all later remediation
    obligations are separately completed.

Plan 11.26 does not claim Plan 11.7 closure, formal evidence, release, push, merge, Phase 1
working-agent status, graceful Zed shutdown, acpx replay visibility, or immediate session reopen.
