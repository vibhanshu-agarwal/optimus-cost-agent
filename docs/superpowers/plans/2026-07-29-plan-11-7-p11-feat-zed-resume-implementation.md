# Plan 11.7 `P11-FEAT-ZED-RESUME` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add conformant, durable ACP `session/load` support so Zed and `acpx` can reopen an
Optimus session after an agent-process restart, replay the client-visible conversation, and continue
with literal complete model history.

**Architecture:** Store one schema-versioned, canonical JSON session ledger per ACP session in a
dedicated `RedisAcpSessionStore` that reuses the process-wide `RedisRuntime`. The ledger is the one
source for replay and derived model history; a lease authorizes one owner while Redis `WATCH`/CAS
makes each revision and sliding-TTL update atomic. The ACP adapter advertises only top-level
`loadSession`, persists complete replay units before emission, and keeps context selection,
compression, summarization, pruning, and eviction exclusively in Plan 12.

**Tech Stack:** Python 3.12, Pydantic v2, `redis.asyncio`, JSON-RPC 2.0, ACP v1, pytest,
pytest-asyncio, pytest-cov/coverage.py, Ruff, Redis 8 with TimeSeries, Optimus Gateway, external
`acpx` 0.12.0, and Zed 1.12.1 stable build 330.

**Status:** Draft for operator approval. Implementation is not authorized.

## Global Constraints

- Drafting baseline is commit `012a0e0e2b0f56e99adf446628dba7a6c1d1fd49`.
- ACP v1 schema fixture is
  `tests/fixtures/acp/acp-v1-schema.json`, SHA-256
  `92C1DFCDA10DD47E99127500A3763DA2B471F9AC61E12B9BF0430C32CF953796`.
- The live Zed source pin is commit `2a37601c02a32b22e7700835c04b89ff75ffcd5d`
  (Zed 1.12.1 stable build 330). Task 0 must re-hash the installed binary/source artifacts rather
  than trusting this statement.
- Scope is ACP `session/load` only. `session/resume`, `session/list`, `session/delete`,
  `session/close`, and non-empty `additionalDirectories` are not implemented or advertised.
- Advertise `"loadSession": true` directly on `agentCapabilities`; keep
  `agentCapabilities.sessionCapabilities` empty. These are distinct ACP v1 capability surfaces.
- `LoadSessionRequest` requires `mcpServers`, `cwd`, and `sessionId`. Preserve today's
  client-nominated MCP posture; do not connect those servers and do not make Gateway-MCP a
  prerequisite.
- Redis is already a hard startup dependency through
  `run_preflight(..., require_timeseries=True)`. Do not add an in-memory fallback or advertise
  `loadSession` when the durable store is unavailable.
- Use a Redis String key named `optimus:acp:session:{session_id}`. The canonical JSON blob,
  revision, lease, operation IDs, and TTL are one transaction/CAS unit; do not create a parallel
  replay or history key.
- The maximum canonical UTF-8 record size is the schema-versioned constant `256 * 1024` bytes.
  It is not configurable. Reserve `4 * 1024` bytes for the bounded terminal-capacity record.
- Retention alone is configurable through `OPTIMUS_ACP_SESSION_RETENTION_DAYS`; default `30`,
  inclusive bounds `1..365`, captured in each new record, and refreshed as a sliding TTL after
  each successful validated load or committed state transition.
- Canonical JSON uses compact separators, sorted string keys, `ensure_ascii=False`, no floats,
  canonical decimal strings, and no Unicode normalization. Reject lone surrogates at the ACP input
  boundary.
- Persist client-visible replay events and typed user/agent turn history. Never persist planning
  observations, workspace reads, source bodies, internal planning context, secrets, or raw
  `mcpServers`; this is a security boundary.
- `committed` turns and `interrupted/client_cancelled` turns enter semantic model history.
  Cancellation projection contains the user content and every durable assistant unit the client
  saw, followed by trusted structural state carrying `incomplete — do not treat as final`.
  `pending`, `interrupted/process_lost`, refused, context-exhausted, and capacity-terminal turns
  remain replay/audit state but are excluded from later model projection.
- Every final agent response is measured and committed as a complete unit before emission. ACP
  agent-message streaming must not be introduced by this plan.
- Literal complete history is passed on every prompt for both uninterrupted and reloaded sessions.
  Do not select, summarize, compress, prune, evict, or promise a fixed number of turns.
- Keep `AgentRunRequest.max_cost_usd = Decimal("0.05")` for ACP prompts. Do not substitute
  `DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")`.
- All provider access remains through the Optimus Gateway. Preserve provider-reported
  `gateway_request_id`, provider, cache hit, billing units, cost, model/version, run ID, and session
  ID; do not estimate usage or cost.
- Lease ownership authorizes a writer; CAS provides atomicity. Never silently retry a CAS conflict.
- A live turn uses a 30-second lease renewed every 10 seconds, including while waiting for
  permission. Renewal reuses the same lease operation ID and is serialized with commits by an
  in-process async lock; a process death therefore becomes recoverable after at most 30 seconds.
- Every behavior task follows RED, focused failing command, minimum implementation, focused GREEN,
  then checkpoint. A checkbox changes to `- [x]` only after its literal verification command passes.
- Unit tests may use fakes. `requires_redis`, `requires_gateway`, and `e2e` evidence must use the
  real dependencies named by the marker. ACP protocol evidence must use independently authored
  `acpx`; Zed claims require real Zed.
- Maintain at least 80% aggregate Python production-code coverage and do not regress
  safety-critical coverage.
- The reviewing agent owns
  `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`. It is gitignored and must never be
  staged.
- Implementation commits, push, PR creation, merge, branch deletion, history rewrite, Redis data
  deletion, and external issue creation require separate operator authorization.

---

## Frozen Requirements and Design

### Wire contract

| Condition | ACP result |
|---|---|
| `initialize` with the durable store wired | top-level `agentCapabilities.loadSession: true`; `sessionCapabilities: {}` |
| Valid `session/load` | replay stored `session/update` notifications in sequence, refresh TTL atomically, return `{}` |
| Missing/malformed required load fields | `INVALID_PARAMS = -32602` |
| Non-empty `additionalDirectories` | `INVALID_PARAMS = -32602` with single-root explanation |
| Unknown or expired `sessionId` | ACP `RESOURCE_NOT_FOUND = -32002` |
| Stored canonical `cwd` differs from requested `cwd` | `INVALID_PARAMS = -32602` |
| Another unexpired owner lease exists | Optimus `SESSION_BUSY = -32900` |
| Malformed or unknown-schema record | fail closed; operator-readable storage error, no replay, no TTL refresh |
| Redis unavailable at startup | startup failure; no serving process and no capability advertisement |
| Redis fails during new/load/prompt | explicit error at the stage defined below; no in-memory downgrade |
| Client sends `session/cancel` | ACP stop reason `cancelled`; protocol error code `REQUEST_CANCELLED = -32800` where a JSON-RPC error is required |
| Client calls list/delete/resume/close | `METHOD_NOT_FOUND = -32601` |

`mcpServers` is required and must be an array on `session/load`, but Plan 11.7 preserves the shipped
disposition: Optimus does not dial client-nominated servers. `P11-FU-9` owns the cross-lifecycle
decision for both existing `session/new` and future lifecycle methods. The unrelated
`P11-FEAT-GATEWAY-MCP` lane owns internal Gateway tool brokering.

### Persisted record and canonical encoding

Schema version 1 has these logical fields:

```python
ACP_SESSION_SCHEMA_VERSION = 1
ACP_SESSION_MAX_BYTES = 256 * 1024
ACP_SESSION_TERMINAL_RESERVE_BYTES = 4 * 1024
ACP_SESSION_APPLIED_OPERATION_LIMIT = 64
ACP_SESSION_LEASE_SECONDS = 30
ACP_SESSION_LEASE_RENEW_INTERVAL_SECONDS = 10
DEFAULT_ACP_SESSION_RETENTION_DAYS = 30
MIN_ACP_SESSION_RETENTION_DAYS = 1
MAX_ACP_SESSION_RETENTION_DAYS = 365

class AcpTurnStatus(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    INTERRUPTED = "interrupted"
    SEALED = "sealed"

class AcpInterruptionReason(str, Enum):
    CLIENT_CANCELLED = "client_cancelled"
    PROCESS_LOST = "process_lost"
    MODEL_REFUSED = "model_refused"
    CONTEXT_WINDOW_EXCEEDED = "context_window_exceeded"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    STORAGE_UNAVAILABLE_AFTER_EFFECT = "storage_unavailable_after_effect"
```

Each untrusted text value is stored as a typed pair such as
`{"text":"accepted Unicode scalar text","utf8_bytes":28}`. Trusted
`turn_status`, `interruption_reason`, role, revision, lease, and operation fields are sibling
structural fields, never text markers embedded inside user-controlled content. The decoder
recomputes each UTF-8 byte count, rejects lone surrogates and mismatches, rejects floats or
non-string keys recursively, rejects unknown schema versions, and never performs implicit
migration or salvage.

The record holds:

- session ID, canonical workspace root, schema version, created/updated timestamps;
- per-session retention days and current expiry;
- monotonic revision and bounded applied-operation IDs;
- current lease owner, opaque lease token, operation ID, and lease expiry;
- ordered replayable `session/update` events with sequence numbers;
- ordered typed turns with length-framed user and complete agent messages;
- sealed state and a bounded structural terminal reason when capacity is absolute.

Canonical bytes are:

```python
json.dumps(
    payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8", errors="strict")
```

Decimals are converted to finite, normalized decimal strings before encoding. No NFC/NFD
normalization is applied; exact accepted Unicode scalar values round-trip.

### State transitions, leases, and CAS

| Operation | Required transition |
|---|---|
| `session/new` | create revision 1 with captured retention and atomic expiry |
| prompt accepted | acquire lease, start 10-second heartbeat, append `pending` user turn before any model call |
| replayable update | measure complete update, CAS-append durably, then emit |
| successful turn | append complete agent response and mark `committed` before final emission |
| client cancel | retain already durable replay, mark turn `interrupted/client_cancelled`, project the user and durable assistant content plus trusted incomplete-state metadata, release lease |
| process dies mid-turn | on load, atomically convert an expired-lease `pending` turn to `interrupted/process_lost` |
| load with live foreign lease | return `SESSION_BUSY`; do not replay or refresh TTL |
| load after validation/recovery | refresh stored expiry and Redis TTL in the same CAS, then replay |
| capacity would overflow | do not append partial agent content; append bounded terminal structure, seal, release lease |
| context window exhausted | append replayable terminal message, mark interrupted, release lease, remain unsealed |

The transaction outcome classification is fixed:

1. the requested operation ID is already recorded: idempotent success returning the stored
   revision;
2. another unexpired owner holds the lease: `SessionBusy`;
3. the same owner observes an unexplained revision change: invariant failure surfaced as a defect.

No case silently retries. A Redis `WATCH` conflict is CAS evidence, not a normal retry signal.

### Failure ordering and irreversibility

1. Before planning: durable `pending` append must succeed before the model call. Failure means no
   model call and no client-visible agent update.
2. Before approval/mutation: all replayable planning output is durable before emission; no mutation
   runs until approval and the pre-mutation durable transition succeed.
3. After an irreversible mutation/tool outcome: if Redis cannot record the outcome, report that the
   effect may have occurred and cannot be rolled back. Never claim rollback or fabricate a durable
   success.

Capacity overflow is absolute and seals the session because the fixed record cannot admit another
complete unit. Context exhaustion remains unsealed because a different/larger-context model can
resume the same literal ledger; its terminal message names that option and `session/new`.

### Total stop-reason mapping

Create one typed `PlanningStopReason` enum and one exhaustive ACP mapping. The test oracle asserts
`set(mapping) == set(PlanningStopReason)` and that every mapped value is extracted from the pinned
schema's `StopReason` constants.

| Internal outcome | ACP `stopReason` |
|---|---|
| `PLANNING_CONTEXT_WINDOW_EXHAUSTED` | `max_tokens` |
| `PLANNING_TURN_LIMIT_EXHAUSTED` | `max_turn_requests` |
| `PLANNING_MODEL_REFUSED` | `refusal` |
| `PLANNING_BUDGET_EXHAUSTED` | `end_turn` |
| `PLANNING_GATEWAY_COST_UNKNOWN` | `end_turn` |
| `PLANNING_GATEWAY_FAILURE` | `end_turn` |
| `PLANNING_HALTED` | `end_turn` |
| `PLANNING_OBSERVATION_BUDGET_EXHAUSTED` | `end_turn` |
| `PLANNING_READ_BUDGET_EXHAUSTED` | `end_turn` |
| `PLANNING_READ_FILE_NOT_FOUND` | `end_turn` |
| `PLANNING_READ_GUARD_BLOCKED` | `end_turn` |
| `PLANNING_READ_INVALID_PATH` | `end_turn` |
| `PLANNING_READ_INVALID_RANGE` | `end_turn` |
| `PLANNING_READ_NOT_UTF8_ALIGNED` | `end_turn` |
| `PLANNING_READ_SOURCE_CHANGED` | `end_turn` |
| `PLANNING_REPEATED_READ_REQUEST` | `end_turn` |
| `PLANNING_UNPARSEABLE_RESPONSE` | `end_turn` |
| `PLANNING_WALL_CLOCK_EXHAUSTED` | `end_turn` |

Normal completion and plan-not-found/expired completion remain `end_turn`; an actual ACP
`session/cancel` remains `cancelled`. `PLANNING_HALTED` is not client cancellation. An unknown
internal outcome raises an invariant error and never falls through to a wire value.

This fixes a present defect: `_PLANNING_TERMINAL_STOP_REASONS` currently includes
`PLANNING_MODEL_REFUSED`, so genuine model refusal reports `end_turn`; only an unknown value reaches
the fallback `refusal`. Task 1 deliberately removes that inverted behavior.

### Error-code registry

- ACP/JSON-RPC: `RESOURCE_NOT_FOUND = -32002`, `REQUEST_CANCELLED = -32800`.
- Optimus application range: inclusive `-32999..-32900`, entirely below JSON-RPC's reserved
  `-32768..-32000` band and clear of ACP `-32800`.
- Plan 11.7 allocation: `SESSION_BUSY = -32900`, `MUTATION_FORBIDDEN = -32910`.
- Runtime exceptions remain semantic; only the ACP adapter maps them to wire codes.
- Plan 11.7 relocates the currently conflicting mutation code and deletes
  `src/optimus/runtime/mutation.py`'s duplicate numeric constant because `session/load` requires
  `-32002` for resource-not-found.
- `P11-FU-10` retains the general `DUPLICATE_REQUEST_ID` review, remaining raw-literal audit, and
  allowlist-to-zero work. It does not block this plan.

The schema oracle extracts ACP error constants from `$defs.ErrorCode.anyOf`. It asserts:

1. Optimus application codes are unique;
2. every Optimus application code is outside the full JSON-RPC reserved band;
3. Optimus application codes are disjoint from all pinned ACP constants;
4. every JSON-RPC/ACP-like numeric literal under `src/` is either a central registry definition or
   an exact path-and-symbol baseline allowlist owned by `P11-FU-10`.

Update `README.md`'s current mutation-boundary claim from `-32002` to `-32910`. Do not edit the
frozen historical plan
`docs/superpowers/plans/2026-07-01-mode-state-machine-mutation-guard.md`; its `-32002` occurrences
are expected retained evidence. Ignore untracked, gitignored `build/lib` copies.

### Plan 12 and practical-depth boundary

Plan 11.7 implements the baseline mechanism: literal complete history. It does not perform
intelligent selection or optimization. Before closure, `P11-FEAT-REGISTRY` must contain a named
excluded-capability row stating that long conversations can terminate at the first model context
or unchanged per-run cost limit and that selection/compression/summarization/pruning/eviction are
owned by Plan 12.

Live evidence records `turns_to_first_limit`, exact model/version, provider, cost, token fields, and
terminal reason. It is a model-specific observation, not a product promise and not generalized to
another model.

## Explicit Exceptions and Custody

| Excluded work | Named owner |
|---|---|
| Connect or otherwise honor client-nominated ACP `mcpServers` across session methods | `P11-FU-9` |
| Gateway-brokered internal MCP tool routing | `P11-FEAT-GATEWAY-MCP` |
| General duplicate-ID code review, remaining raw literals, allowlist to zero | `P11-FU-10` |
| `session/resume`, list, delete, close, and additional workspace roots | `P11-FEAT-REGISTRY` excluded-capability inventory |
| History selection, compression, summarization, pruning, eviction, context optimization | Plan 12, with Registry inventory row |
| Cumulative session/project cost policy | `P9.85-FU-3` |
| Ownership of FU-4A/FU-5 evidence re-pin | `P11-FU-4`; Plan 11.7 coordinates only |
| Agent-side workaround for a current Zed rendering defect | Requires a separately approved plan and named external/internal custody |
| Raising ACP prompt default from `$0.05` to live-run `$0.25` | Excluded; budget policy unchanged |

Anything not listed in this table is in scope.

## Acceptance Ledger

| Requirement | Tasks | Evidence |
|---|---:|---|
| Top-level capability and conformant load shapes | 0, 1, 4, 7A | Pinned-schema oracle, adapter tests, real `acpx`, real Zed |
| Durable identity/workspace/history across process restart | 2, 3, 5, 7A, 8, 9 | Canonical model tests, live Redis restart, Zed reopen |
| TTL, expiry, malformed storage, and version behavior | 2, 3, 4, 7A | Unit + real Redis integration |
| Replay and uninterrupted literal history from one ledger | 2, 5, 7A, 8, 9 | Projection tests, exact Gateway capture, replay transcripts |
| Lease/CAS concurrency and process-loss recovery | 3, 7A, 7B | Race tests with real Redis |
| Persist-before-emit, cancelled-view continuity, and irreversible-effect failure staging | 5, 7B | Ordering/projection/fault-injection tests and live Redis interruption evidence |
| Capacity never stores/emits a partial answer | 2, 7B | Boundary tests and complete-unit regression |
| Context exhaustion is typed, replayable, excluded, and unsealed | 6, 7B | Gateway boundary tests and adapter tests |
| Error-code conformance and current mutation collision removal | 1 | Schema-extracted oracle, AST scan, README/frozen-doc disposition |
| Total stop mapping and inverted-refusal fix | 1, 10 | Set-equality oracle and Zed 2x2 matrix |
| Client refusal stability | 0, 10 | Pre/post Zed artifacts or explicit named defect custody |
| Plan 12 boundary and model-specific practical depth | 5, 8, 11 | Registry row and real Gateway `turns_to_first_limit` |
| FU-4 coordination and mechanical closure | 11 | Reviewed disposition, manifests, ancestry, re-hash, zero unchecked boxes |

## Source Anchors and Baseline Evidence

- `src/optimus/acp/spec.py:194-240` handles new/prompt and advertises empty
  `sessionCapabilities`, but no top-level `loadSession`.
- `src/optimus/acp/spec.py:437-488` emits each plan/agent response as one complete notification and
  then emits discrete tool-call notifications.
- `src/optimus/acp/spec.py:523-587` contains the inverted refusal/default mapping fixed in Task 1.
- `src/optimus/acp/server.py:216-226` creates `InMemoryAcpSpecSessionStore` per NDJSON process.
- `src/optimus/acp/bootstrap.py:65-68` already requires real TimeSeries-capable Redis and creates
  the shared runtime.
- `src/optimus/redis/runtime.py` owns the existing `redis.asyncio` pool/client.
- `src/optimus/agent/state_store.py` stores expiring agent plans, not ACP sessions.
- `src/optimus/agent/models.py:44-57` pins ACP's current per-run model default at
  `Decimal("0.05")`.
- `src/optimus/agent/planning_loop.py:30-31` limits planning observations/reads to 4/12 KiB; neither
  belongs in the durable session ledger.
- `src/optimus/acp/errors.py` and `src/optimus/runtime/mutation.py` independently assign `-32002` to
  mutation refusal today.
- `tests/fixtures/acp/acp-v1-schema.json` defines top-level `loadSession`, required load fields,
  StopReason values, `-32002`, and `-32800`; its fixture README must be updated to name this oracle
  use.
- `tests/integration/acp/test_server_stream_live_redis.py` is the existing real-Redis ACP tier.
- `tools/run_plan987_acpx_live_evidence.py` and
  `tools/run_plan115_acpx_cost_obs_evidence.py` are existing external-`acpx` evidence patterns.
- `reports/plan-9-8-task-aware-context-evidence.md` and
  `reports/plan-9-75-zed-hitl-runtime-evidence.md` anchor `P9.8-FU-5`.
- Backlog/charter prose that attributes load support to `sessionCapabilities` is factually stale;
  living documents are corrected at closure. Frozen historical plans remain unchanged.

## File and Responsibility Map

| File | Responsibility |
|---|---|
| `src/optimus/acp/errors.py` | Sole ACP/JSON-RPC/Optimus wire-code registry and application-range constants. |
| `src/optimus/agent/stop_reasons.py` | New typed planning outcomes and exhaustive ACP stop-reason mapping. |
| `src/optimus/runtime/mutation.py`, `src/optimus/runtime/__init__.py` | Keep mutation refusal semantic; remove duplicated wire number/export. |
| `src/optimus/acp/session_models.py` | New schema-v1 ledger types, canonical encoding/decoding, capacity and history projection. |
| `src/optimus/acp/session_store.py` | New store protocol, semantic store failures, lease/CAS outcomes, and `RedisAcpSessionStore`. |
| `src/optimus/redis/runtime.py` | Construct the ACP store from the existing pooled client. |
| `src/optimus/acp/spec.py` | Validate new/load/prompt, orchestrate durable turns, advertise/load/replay, and map semantic errors. |
| `src/optimus/acp/shapes.py` | Build validated complete replayable update shapes and bounded terminal messages. |
| `src/optimus/acp/server.py` | Inject one durable store into ACP connections; stop constructing in-memory sessions. |
| `src/optimus/acp/bootstrap.py` | Build runner and ACP store from one `RedisRuntime`; resolve retention from authorized env. |
| `src/optimus/acp/launch_policy.py`, `src/optimus/acp/launch_gate.py` | Classify, validate, approve, and thread the retention variable. |
| `src/optimus/acp/subprocess_env.py` | Permit the registry-authorized retention variable in agent children. |
| `src/optimus/agent/conversation.py` | Shared immutable role/content/UTF-8-length type used by ledger projection and model input. |
| `src/optimus/agent/models.py`, `src/optimus/agent/prompts.py` | Carry and length-frame literal semantic history without changing the `$0.05` cap. |
| `src/optimus/agent/runner.py`, `src/optimus/agent/planning_loop.py` | Consume typed history/outcomes and keep internal reads/observations ephemeral. |
| `src/optimus/gateway/errors.py`, `src/optimus/gateway/client.py` | Normalize structured context-window failures without vendor-text matching. |
| `src/optimus_gateway/upstream_client.py`, `src/optimus_gateway/responses.py` | Preserve a typed provider failure category across the local Gateway boundary. |
| `tests/unit/acp/test_protocol_oracle.py` | Schema digest, error range/literal registry, capability, and stop-reason totality. |
| `tests/unit/acp/test_session_models.py` | Canonicalization, schema, capacity, projection, interruption, and lone-surrogate tests. |
| `tests/unit/acp/test_session_store.py` | Store contract, operation IDs, leases, CAS classification, TTL, and faults. |
| `tests/unit/acp/test_spec_protocol.py` | Adapter load/prompt/replay/cancel/error behavior and complete-unit emission. |
| `tests/unit/agent/test_session_history.py` | Literal history prompt construction and no-internal-context persistence. |
| `tests/unit/gateway/test_context_window_errors.py` | Structured client-side context normalization. |
| `tests/unit/optimus_gateway/test_context_window_errors.py` | Provider-to-Gateway structured normalization. |
| `tests/integration/acp/test_session_store_live_redis.py` | Real Redis CAS/lease/TTL/recovery/malformed behavior. |
| `tests/integration/acp/test_session_load_live_redis.py` | Real ACP process/store replay and failure semantics. |
| `tests/integration/agent/test_session_history_live_gateway.py` | Real Gateway literal-history and exact usage/cost evidence. |
| `tools/run_plan117_acpx_resume_evidence.py` | External-`acpx` restart/replay/depth capture. |
| `tools/verify_plan117_resume_evidence.py` | Task 0 creates the baseline verifier; later evidence tasks extend it with restart/Zed/closure invariants. |
| `tests/unit/tools/test_run_plan117_acpx_resume_evidence.py` | Evidence-driver commands, secret boundaries, and manifest tests. |
| `tests/unit/tools/test_verify_plan117_resume_evidence.py` | Offline verifier tamper/ancestry/invariant tests. |
| `reports/plan-11-7-*.md`, `reports/plan-11-7-*.json` | Durable baseline, Redis/`acpx`, Gateway-depth, Zed, and refusal evidence. |
| `README.md`, fixture README, backlog, charter, roadmap | Current capability/error docs, provenance, custody, and closure. |

### Task 0: Freeze approval, clients, and untouched-baseline evidence

**Files:**

- Create: `reports/plan-11-7-task0-client-discovery-and-refusal-baseline.md`
- Create: `reports/plan-11-7-task0-artifact-manifest.json`
- Create: `tools/verify_plan117_resume_evidence.py`
- Create: `tests/unit/tools/test_verify_plan117_resume_evidence.py`
- Create/update (reviewer-owned, gitignored):
  `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Produces immutable `baseline_commit`, schema/Zed/`acpx` identities, Zed discovery trace, the
  pre-Task-1 halves of Task 10's refusal matrix, and an offline hash/identity verifier that later
  tasks extend.
- Blocks every implementation checkbox until the operator approves this plan's SHA-256.

- [ ] **Step 1: Verify the clean ancestry baseline and exact plan digest.**

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  git merge-base --is-ancestor 012a0e0e2b0f56e99adf446628dba7a6c1d1fd49 HEAD
  git diff --exit-code 012a0e0e2b0f56e99adf446628dba7a6c1d1fd49 -- src tests
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "tests/fixtures/acp/acp-v1-schema.json"
  ```

  Expected: commit `012a0e0e2b0f56e99adf446628dba7a6c1d1fd49` is an ancestor of `HEAD`;
  `git diff --exit-code 012a0e0e2b0f56e99adf446628dba7a6c1d1fd49 -- src tests` is clean before
  baseline capture; and the schema hash equals the Global Constraints value. A plan-only approval
  commit after the baseline is permitted. Record the operator's approval identity, UTC time, exact
  plan hash, baseline commit, and current plan-only commit in both report and reviewer checkpoint
  before proceeding.

- [ ] **Step 2: Prove the real dependency and client identities.**

  ```powershell
  uv run --frozen python -m optimus.acp --check-config --strict
  acpx --version
  $plan117ZedSource = $env:OPTIMUS_PLAN117_ZED_SOURCE
  if ([string]::IsNullOrWhiteSpace($plan117ZedSource)) { throw "OPTIMUS_PLAN117_ZED_SOURCE is required" }
  git -C $plan117ZedSource rev-parse HEAD
  ```

  Replace the quoted Zed source argument at execution with the absolute source path recorded in the
  manifest; the command must resolve to `2a37601c02a32b22e7700835c04b89ff75ffcd5d`.
  Record Redis image/container ID and TimeSeries module output, Gateway URL host with credentials
  redacted, `acpx` 0.12.0 executable hash, Zed executable hash/version, source commit, and source
  files proving top-level `loadSession` discovery and the load request path. Hash and identify the
  on-disk Zed agent-registry source already found during design review, and attach that provenance
  to `P11-FEAT-REGISTRY`'s research gate without expanding Plan 11.7 into registry submission.
  If a real dependency or either Zed source is unavailable, stop Task 0.

- [ ] **Step 3: Capture refusal matrix cases 1 and 2 on untouched production code.**

  On the same untouched live stack, capture:

  1. a genuine `PLANNING_MODEL_REFUSED`, verifying legacy wire `end_turn` and Zed rendering;
  2. a best-effort reproduction of the historical ambiguous/unknown path that currently falls
     through to wire `refusal`.

  Preserve raw NDJSON, sanitized Zed logs, screenshots, model/version, and exact construction. A
  precise non-reproduction is a valid result for case 2; do not fabricate a new baseline harness or
  rebuild baseline later.

- [ ] **Step 4: Capture Zed discovery after the refusal baseline is sealed.**

  Preserve the clean-source hash from Step 1, then apply an explicitly recorded temporary
  capability/load probe that changes only top-level `loadSession` advertisement and returns an
  empty successful `session/load`. Launch that baseline agent with the same real Redis/Gateway and
  Zed, create a session, close the agent process, reopen the same Zed thread, and capture whether
  Zed reads top-level `loadSession`, issues `session/load`, requires `session/list`, or instead
  creates a new session. Record the `sidebar_threads.session_id` row with unrelated content
  redacted. Reverse only the recorded probe patch and re-run the Step 1 source-tree diff before
  proceeding. The probe establishes client reachability; it is not implementation or conformance
  evidence. If Zed does not issue `session/load`, requires list support, or the source tree does not
  return exactly to baseline, stop and amend the plan before implementation.

- [ ] **Step 5: Write and run RED baseline-verifier tests.**

  Create tests that require the exact baseline/schema/`acpx`/Zed identities, artifact SHA-256
  values, discovery outcome, case-1 result, and case-2 artifact-or-non-reproduction disposition.
  The verifier must reject a changed byte, missing identity, mismatched baseline, or a narrative
  timestamp used instead of a commit.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

  Expected: failure because the verifier entrypoint does not exist.

- [ ] **Step 6: Implement and run the Task 0 offline verifier.**

  Implement `--task0 reports/plan-11-7-task0-artifact-manifest.json` using only local files and Git
  ancestry. It reads the supplied JSON manifest, recomputes every SHA-256, checks the pinned
  constants, and exits nonzero with a safe field-level diagnostic on the first invariant failure.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

  Expected: baseline verifier unit tests pass.

- [ ] **Step 7: Verify and checkpoint Task 0 artifacts.**

  ```powershell
  uv run --frozen python tools/verify_plan117_resume_evidence.py --task0 reports/plan-11-7-task0-artifact-manifest.json
  git diff --check
  ```

  Expected: manifest hashes resolve, baseline/schema/client identities match, case 1 exists, and
  case 2 records either an artifact or an exact non-reproduction. Commit Task 0 reports only after
  separate authorization, with subject `test(acp): pin Plan 11.7 baseline evidence`.

### Task 1: Pin the protocol oracle, total stop mapping, and error registry

**Files:**

- Create: `src/optimus/agent/stop_reasons.py`
- Create: `tests/unit/acp/test_protocol_oracle.py`
- Modify: `src/optimus/acp/errors.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/agent/models.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/runtime/mutation.py`
- Modify: `src/optimus/runtime/__init__.py`
- Modify: `tests/unit/acp/test_errors.py`
- Modify: `tests/unit/acp/test_dispatcher.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/fixtures/acp/README.md`
- Modify: `README.md`

**Interfaces:**

- Produces `PlanningStopReason`, `ACP_STOP_REASON_BY_PLANNING_REASON`,
  `acp_stop_reason(result)`, `RESOURCE_NOT_FOUND`, `REQUEST_CANCELLED`, `SESSION_BUSY`,
  `MUTATION_FORBIDDEN`, and `OPTIMUS_APPLICATION_ERROR_CODES`.
- Preserves `MutationForbidden` as a semantic runtime exception with no numeric field.
- Leaves only the exact `P11-FU-10` path-and-symbol baseline allowlist.

- [ ] **Step 1: Write RED schema/error/stop totality tests.**

  The test must load and hash the fixture, derive
  `schema["$defs"]["ErrorCode"]["anyOf"]` integer `const` values and
  `schema["$defs"]["StopReason"]["anyOf"]` string `const` values, then assert:

  ```python
  assert set(ACP_STOP_REASON_BY_PLANNING_REASON) == set(PlanningStopReason)
  assert set(ACP_STOP_REASON_BY_PLANNING_REASON.values()) <= schema_stop_reasons
  assert set(OPTIMUS_APPLICATION_ERROR_CODES).isdisjoint(schema_error_codes)
  assert all(not (-32768 <= code <= -32000) for code in OPTIMUS_APPLICATION_ERROR_CODES)
  assert len(OPTIMUS_APPLICATION_ERROR_CODES) == len(set(OPTIMUS_APPLICATION_ERROR_CODES))
  assert RESOURCE_NOT_FOUND == -32002
  assert REQUEST_CANCELLED == -32800
  assert SESSION_BUSY == -32900
  assert MUTATION_FORBIDDEN == -32910
  ```

  Parse Python AST under `src/` and fail for a JSON-RPC-like integer literal not defined in
  `optimus.acp.errors`, except the reviewed baseline symbols still assigned to `P11-FU-10`.
  Add a test that frozen mutation-plan matches remain expected and `README.md` names `-32910`.

- [ ] **Step 2: Write RED refusal and unknown-outcome tests.**

  Add explicit tests for all 18 table rows, a genuine model refusal returning `refusal`, client
  cancellation returning `cancelled`, human halt returning `end_turn`, and an unknown string raising
  `InternalStopReasonMappingError` rather than returning `refusal`.

- [ ] **Step 3: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_protocol_oracle.py tests/unit/acp/test_errors.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: failures expose missing oracle/types, `-32002` collision/duplication, genuine refusal
  reporting `end_turn`, and the unknown fallback reporting `refusal`.

- [ ] **Step 4: Implement the central types and mappings.**

  Define all 18 enum values exactly as the Total stop-reason table. Define the mapping as a literal
  dictionary keyed by every enum member. Replace string producers with enum members, remove
  `_PLANNING_TERMINAL_STOP_REASONS`, and make unknown input an invariant error.

  In `errors.py`, keep standard/ACP definitions central and define:

  ```python
  RESOURCE_NOT_FOUND = -32002
  REQUEST_CANCELLED = -32800
  SESSION_BUSY = -32900
  MUTATION_FORBIDDEN = -32910
  OPTIMUS_APPLICATION_ERROR_CODES = frozenset({SESSION_BUSY, MUTATION_FORBIDDEN})
  ```

  Remove `MUTATION_FORBIDDEN_CODE` from runtime code/exports. Map `MutationForbidden` only in the
  ACP dispatcher. Update current README prose, leave the frozen plan unchanged, and document
  expected historical grep results.

- [ ] **Step 5: Run focused GREEN and documentation disposition.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_protocol_oracle.py tests/unit/acp/test_errors.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_spec_protocol.py -q
  rg -n -- "-32002|-32910" README.md src docs/superpowers/plans/2026-07-01-mode-state-machine-mutation-guard.md
  ```

  Expected: tests pass; live code/README use `-32910` for mutation; `-32002` remains resource-not-found
  plus expected frozen-plan history and any exact `P11-FU-10` allowlist entries.

- [ ] **Step 6: Checkpoint Task 1.**

  Run `uv run --frozen ruff check` on Task 1 paths and `git diff --check`. Record the before/after
  refusal behavior and allowlist. Commit only with separate authorization, subject
  `fix(acp): centralize protocol outcomes and error codes`.

### Task 2: Define the canonical session ledger and capacity boundary

**Files:**

- Create: `src/optimus/acp/session_models.py`
- Create: `src/optimus/agent/conversation.py`
- Create: `tests/unit/acp/test_session_models.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `tests/unit/acp/test_shapes.py`

**Interfaces:**

- Produces immutable `ConversationMessage`, `ConversationTurn`, `AcpSessionRecord`,
  `AcpTurnRecord`, `AcpReplayEvent`, `FramedText`,
  `encode_session_record(record) -> bytes`, `decode_session_record(payload) -> AcpSessionRecord`,
  `project_model_history(record) -> tuple[ConversationTurn, ...]`, and typed capacity/schema
  failures.
- Task 3 persists only the encoded blob. Tasks 5/7 consume projection and replay events.

- [ ] **Step 1: Write RED canonicalization and schema tests.**

  Cover deterministic key ordering, exact UTF-8 byte length, non-ASCII round-trip without
  normalization, decimal strings, rejection of floats/non-string keys/lone surrogates, framed-text
  byte mismatch, unknown schema, malformed JSON, non-monotonic sequence/revision, and exact
  round-trip equality.

  ```python
  first = encode_session_record(record)
  second = encode_session_record(record)
  assert first == second
  assert len(first) <= ACP_SESSION_MAX_BYTES
  assert decode_session_record(first) == record
  ```

- [ ] **Step 2: Write RED projection/interruption/security tests.**

  Assert committed user/agent turns project in order. Assert `interrupted/client_cancelled`
  projects the user content, every durable assistant unit already visible to the client, and trusted
  `incomplete — do not treat as final` state; cover cancellation before and after the first
  assistant unit. Pending, process-lost, refused, context-exhausted, and capacity-terminal turns do
  not project. Assert replay still contains already durable client-visible updates for interrupted
  turns. Insert terminal-marker-looking user text and prove trusted status is read from structural
  fields outside the length-framed content, not inferred from text.

- [ ] **Step 3: Write RED byte-boundary and complete-unit tests.**

  Construct records at `ACP_SESSION_MAX_BYTES - ACP_SESSION_TERMINAL_RESERVE_BYTES`, one byte over,
  multibyte boundaries, and a full agent response that cannot fit. Assert no prefix/truncation is
  returned and the bounded sealed terminal record fits within 256 KiB.

- [ ] **Step 4: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_session_models.py tests/unit/acp/test_shapes.py -q
  ```

  Expected: missing model/codec/capacity failures.

- [ ] **Step 5: Implement immutable models and strict codec.**

  Use Pydantic frozen models/enums and a recursive pre-encode validator. `FramedText.from_text`
  performs strict UTF-8 encoding and stores byte length. Ordinary appends must leave the exact 4 KiB
  terminal reserve; `seal_for_capacity` replaces no content, adds only bounded trusted fields, and
  returns a record under the absolute cap.

- [ ] **Step 6: Run focused GREEN and checkpoint.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_session_models.py tests/unit/acp/test_shapes.py -q
  uv run --frozen ruff check src/optimus/acp/session_models.py src/optimus/acp/shapes.py src/optimus/agent/conversation.py tests/unit/acp/test_session_models.py tests/unit/acp/test_shapes.py
  ```

  Expected: all canonicalization, projection, injection, and byte-boundary cases pass. Record the
  largest ordinary/terminal fixture byte counts. Commit only with separate authorization, subject
  `feat(acp): define canonical durable session ledger`.

### Task 3: Implement Redis lease/CAS storage on the shared runtime

**Files:**

- Create: `src/optimus/acp/session_store.py`
- Create: `tests/unit/acp/test_session_store.py`
- Create: `tests/integration/acp/test_session_store_live_redis.py`
- Modify: `src/optimus/redis/runtime.py`
- Modify: `tests/unit/redis/test_runtime.py`

**Interfaces:**

- Produces async `AcpSessionStore` methods
  `create`, `load`, `acquire`, `commit`, `release`, and `refresh_after_load`.
- `RedisRuntime.acp_session_store()` returns a `RedisAcpSessionStore` sharing `runtime.client`.
- Produces semantic `SessionNotFound`, `SessionBusy`, `SessionMalformed`,
  `SessionRevisionConflict`, `SessionStorageUnavailable`, and `SessionSealed`.

  ```python
  async def create(self, record: AcpSessionRecord) -> AcpSessionRecord: ...
  async def load(self, session_id: str) -> AcpSessionRecord: ...
  async def acquire(
      self, session_id: str, owner_id: str, operation_id: str
  ) -> AcpSessionRecord: ...
  async def commit(
      self,
      session_id: str,
      lease_token: str,
      expected_revision: int,
      operation_id: str,
      next_record: AcpSessionRecord,
  ) -> AcpSessionRecord: ...
  async def release(
      self,
      session_id: str,
      lease_token: str,
      expected_revision: int,
      operation_id: str,
      next_record: AcpSessionRecord,
  ) -> AcpSessionRecord: ...
  async def refresh_after_load(
      self, session_id: str, canonical_cwd: str, operation_id: str
  ) -> AcpSessionRecord: ...
  ```

- [ ] **Step 1: Write RED store-contract tests.**

  Pin key template `optimus:acp:session:{session_id}`, create-only semantics, atomic value+TTL, default/captured
  retention, read without mutation, successful-load refresh, failed-load no refresh, sealed-load
  refresh, and unknown/expired/malformed classifications.

- [ ] **Step 2: Write RED lease/CAS classification tests.**

  Cover owner/token/operation validation, live foreign owner -> busy, expired pending lease ->
  `interrupted/process_lost`, duplicate operation ID -> idempotent stored success, explained next
  revision -> success, bounded 64-operation retention, 10-second same-operation lease renewal, and
  unexplained same-owner revision -> surfaced invariant failure. Assert `WATCH` conflicts are never
  retried.

- [ ] **Step 3: Run unit RED.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_session_store.py tests/unit/redis/test_runtime.py -q
  ```

  Expected: missing store/runtime factory and transaction semantics.

- [ ] **Step 4: Implement one-key transactions.**

  Reuse the existing async client/pool. For each write: `WATCH` the one key, decode and validate the
  exact revision/lease/operation, create the next immutable record, encode/capacity-check, then
  `MULTI` + `SET key payload EX (record.retention_days * 86_400)` + `EXEC`. Lease renewal uses the same operation
  ID, updates the caller's current revision, and cannot run concurrently with a commit inside one
  process. Do not create a Redis client per operation, use blocking Redis commands, or scan the
  keyspace.

- [ ] **Step 5: Run unit GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_session_store.py tests/unit/redis/test_runtime.py -q
  ```

  Expected: contract/classification tests pass and injected CAS conflict is observed once.

- [ ] **Step 6: Add and run real-Redis integration.**

  Mark the new file `requires_redis`. Use unique session IDs, short test-only TTLs, two store
  instances sharing the real runtime, and cleanup only those exact keys in fixture teardown.

  ```powershell
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_store_live_redis.py -q
  ```

  Expected: real expiry, lease contention, process-loss conversion, operation idempotency, TTL
  refresh, and CAS conflict pass on TimeSeries-capable Redis.

- [ ] **Step 7: Checkpoint Task 3.**

  Record Redis server/module identity, key names, TTL observations, and conflict classification.
  Run Ruff/diff check. Commit only with separate authorization, subject
  `feat(acp): add Redis session lease and CAS store`.

### Task 4: Wire retention, durable startup, and capability advertisement

**Files:**

- Modify: `src/optimus/acp/launch_policy.py`
- Modify: `src/optimus/acp/launch_gate.py`
- Modify: `src/optimus/acp/subprocess_env.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `tests/unit/acp/test_launch_policy.py`
- Modify: `tests/unit/acp/test_launch_gate.py`
- Modify: `tests/unit/acp/test_acp_subprocess_env.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Modify: `tests/unit/acp/test_main_wiring.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:**

- Produces `resolve_acp_session_retention_days(environ) -> int` with default/bounds.
- `AcpStreamServer` receives the durable store and never constructs an in-memory store.
- `build_configured_server` creates runner/state store/session store from one `RedisRuntime`.

- [ ] **Step 1: Write RED configuration/trust tests.**

  Pin missing/blank -> 30, `1`/`365` accepted, `0`/`366`/non-integer rejected without echoing raw
  values, authorized child projection, launch digest participation, monotonic policy classification,
  and no ambient environment reads below bootstrap.

- [ ] **Step 2: Write RED runtime/capability tests.**

  Assert one `RedisRuntime` supplies both existing plan state and the new session store, server
  startup fails when Redis preflight fails, no in-memory fallback exists, initialize advertises
  top-level `loadSession: true`, and session capability list/delete/resume remain absent.

- [ ] **Step 3: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: retention registry/wiring and capability failures.

- [ ] **Step 4: Implement authorized configuration and shared construction.**

  Add `OPTIMUS_ACP_SESSION_RETENTION_DAYS` to the launch registry as non-secret agent-child
  configuration. Resolve it once after authorization. Refactor bootstrap with one private
  configured-runtime builder returning runner plus the shared `RedisRuntime`; keep
  `build_agent_runner_for_harness`'s public return type unchanged. Inject the durable store into
  `AcpStreamServer` and `AcpDuplexAdapter`.

- [ ] **Step 5: Run focused GREEN and strict startup.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_policy.py tests/unit/acp/test_launch_gate.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_main_wiring.py tests/unit/acp/test_spec_protocol.py -q
  uv run --frozen python -m optimus.acp --check-config --strict
  ```

  Expected: tests pass and strict startup reaches real Redis/Gateway with no new prerequisite.

- [ ] **Step 6: Checkpoint Task 4.**

  Record the authorized environment names and prove the `$0.05` request default is unchanged.
  Commit only with separate authorization, subject
  `feat(acp): wire durable load capability and retention`.

### Task 5: Project literal complete history into every model call

**Files:**

- Create: `tests/unit/agent/test_session_history.py`
- Create: `tests/integration/agent/test_session_history_live_gateway.py`
- Modify: `src/optimus/agent/models.py`
- Modify: `src/optimus/agent/prompts.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `tests/unit/agent/test_planning_loop.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:**

- Consumes Task 2's immutable `ConversationTurn` containing length-framed
  `ConversationMessage(role, content, utf8_bytes)` values plus trusted turn status, and produces
  `AgentRunRequest.history`.
- ACP derives history only through `project_model_history(record)`.
- Prompt builders length-frame every history item and current task; all planning turns receive the
  same complete prior committed history plus current turn.

- [ ] **Step 1: Write RED history projection and prompt tests.**

  Cover uninterrupted second prompt, process-reloaded second prompt, a prompt following client
  cancellation, multiple planning calls, exact role/order/text/UTF-8 counts, delimiter-like user
  content, and the status-specific projection rules. The post-cancel prompt must contain what the
  client saw plus trusted `interrupted/client_cancelled` and
  `incomplete — do not treat as final` metadata outside untrusted frames. Assert planning
  observations, guarded-read contents, tool summaries, and internal progress never enter the
  persisted record or model-history field.

- [ ] **Step 2: Write RED cost/telemetry invariants.**

  Assert ACP-created `AgentRunRequest` leaves `max_cost_usd` at `Decimal("0.05")`. For every model
  call in a multi-turn fixture, assert the existing exact Gateway usage/cost metadata and
  session/run correlation remain present.

- [ ] **Step 3: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/agent/test_session_history.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: history field/builder/projection failures; current single-task prompt behavior remains
  the baseline.

- [ ] **Step 4: Implement literal length-framed history.**

  Add the frozen history tuple with an empty default for non-ACP callers. Build a deterministic
  history section where trusted role/byte-count/status headers are outside the exact untrusted
  content. For a cancelled turn, serialize `status=interrupted`,
  `reason=client_cancelled`, and `instruction=incomplete — do not treat as final` after all durable
  assistant units; never synthesize missing assistant content. Feed that section to every
  planning/replanning call; do not copy workspace reads or observations into it. ACP reads it only
  from the current durable record after the pending turn is committed.

- [ ] **Step 5: Run unit GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/agent/test_session_history.py tests/unit/agent/test_runner.py tests/unit/agent/test_planning_loop.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: uninterrupted/reloaded inputs are byte-identical for identical ledgers and `$0.05`
  remains unchanged.

- [ ] **Step 6: Run real-Gateway history evidence.**

  Mark the integration file `requires_gateway`. Send two bounded prompts, capture redacted request
  metadata at the Gateway boundary, and assert the second contains the exact first user/agent
  history plus current user turn. Assert provider usage/cost fields, model/version, run ID, and
  session ID are complete.

  ```powershell
  uv run --frozen pytest -m requires_gateway tests/integration/agent/test_session_history_live_gateway.py -q
  ```

- [ ] **Step 7: Checkpoint Task 5.**

  Record model/version and redacted history hashes, not source bodies. Commit only with separate
  authorization, subject `feat(agent): carry literal ACP session history`.

### Task 6: Normalize context-window exhaustion and preserve replay

**Files:**

- Modify: `src/optimus_gateway/upstream_client.py`
- Modify: `src/optimus_gateway/responses.py`
- Modify: `src/optimus/gateway/errors.py`
- Modify: `src/optimus/gateway/client.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/acp/spec.py`
- Create: `tests/unit/optimus_gateway/test_context_window_errors.py`
- Create: `tests/unit/gateway/test_context_window_errors.py`
- Modify: `tests/unit/agent/test_planning_loop.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:**

- Produces structured `GatewayFailureKind.CONTEXT_WINDOW_EXCEEDED` across local Gateway/client
  layers and `PlanningStopReason.CONTEXT_WINDOW_EXHAUSTED`.
- Never classifies by matching vendor message text.
- ACP maps the outcome to `max_tokens`, durable interrupted replay, semantic-history exclusion, and
  an unsealed session.

- [ ] **Step 1: Write RED provider/Gateway normalization tests.**

  Supply structured upstream bodies with provider error `type`/`code` indicating context length and
  unrelated messages containing similar words. Assert only structured fields produce
  `CONTEXT_WINDOW_EXCEEDED`; redact provider bodies and preserve valid gateway usage when present.

- [ ] **Step 2: Write RED agent/ACP behavior tests.**

  Assert typed planning outcome, `stopReason: max_tokens`, one durable complete terminal message,
  `interrupted/context_window_exceeded`, no failed-turn semantic projection, lease release, no
  sealed flag, and a later prompt allowed for a changed/larger-context model.

- [ ] **Step 3: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_context_window_errors.py tests/unit/gateway/test_context_window_errors.py tests/unit/agent/test_planning_loop.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: missing typed failure path and current generic `PLANNING_GATEWAY_FAILURE`.

- [ ] **Step 4: Implement structured normalization.**

  Normalize only provider-structured error fields at the local Gateway boundary, return a safe
  typed code, parse it into a typed client exception, and translate it once in planning. Keep
  unknown failures at `PLANNING_GATEWAY_FAILURE -> end_turn`. The ACP terminal message states that
  a larger-context model or `session/new` can recover.

- [ ] **Step 5: Run focused GREEN and checkpoint.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_context_window_errors.py tests/unit/gateway/test_context_window_errors.py tests/unit/agent/test_planning_loop.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Run Ruff/diff check and record structured fields used for classification. Commit only with
  separate authorization, subject `fix(acp): normalize context-window exhaustion`.

### Task 7A: Implement `session/load`, replay, TTL refresh, and protocol errors

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Create: `tests/integration/acp/test_session_load_live_redis.py`
- Modify: `tests/integration/acp/test_server_stream_live_redis.py`

**Interfaces:**

- Consumes Task 3 store semantics and Task 2 ordered replay.
- Produces `_handle_session_load`, maps semantic store failures to the frozen wire table, and binds
  a loaded session into the current adapter.

- [ ] **Step 1: Write RED request/capability tests.**

  Cover required `mcpServers` array, absolute canonical `cwd`, `sessionId`, omitted/empty
  `additionalDirectories`, rejection of non-empty additional roots, unknown/expired, workspace
  mismatch, malformed/unknown schema, unavailable store, busy owner, and list/delete/resume
  method-not-found.

- [ ] **Step 2: Write RED replay/refresh tests.**

  Assert successful load performs expired-lease recovery, CAS-refreshes record/Redis TTL, then emits
  every stored `session/update` once in sequence and returns `{}`. Failed validation/busy/malformed
  load emits nothing and does not refresh. Sealed valid load replays and refreshes.

- [ ] **Step 3: Run unit RED.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: no load handler/capability/store mappings.

- [ ] **Step 4: Implement minimal load orchestration.**

  Validate all request fields before store access. Compare canonical paths exactly after
  `Path.resolve`, while still requiring the configured single root. Do not store/dial
  `mcpServers`. Refresh atomically before replay so a successful response cannot describe a
  session that expired during load.

- [ ] **Step 5: Run unit GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_protocol_oracle.py -q
  ```

- [ ] **Step 6: Run real-Redis integration.**

  Spawn two real ACP server instances sequentially against the same Redis. Create/prompt on the
  first, load on the second, assert replay order/history, then exercise unknown, forced expiry,
  mismatch, malformed exact test key, live lease, and process-loss recovery.

  ```powershell
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_load_live_redis.py tests/integration/acp/test_server_stream_live_redis.py -q
  ```

- [ ] **Step 7: Checkpoint Task 7A.**

  Record Redis identity, TTL before/after, replay event hashes, and error codes. Commit only with
  separate authorization, subject `feat(acp): load and replay durable sessions`.

### Task 7B: Enforce persistence ordering, cancellation, and sealing

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/integration/acp/test_session_load_live_redis.py`
- Modify: `tests/integration/acp/test_server_stream_live_redis.py`

**Interfaces:**

- Consumes durable load/store/history.
- Produces one ordered turn transaction across new/prompt/planning/approval/execution/cancel and the
  complete-unit emission invariant.

- [ ] **Step 1: Write RED event-order tests.**

  Use ordered spies to assert `pending append < model call`, `durable replay append < outbound
  notify`, `pre-mutation durable transition < approval effect`, and `complete agent measurement <
  append < emission`. Fail the test if multiple `agent_message_chunk` notifications partition one
  final response.

- [ ] **Step 2: Write RED fault-stage tests.**

  Inject storage loss before planning, after planning/before approval, before mutation, and after an
  irreversible effect. Assert the first three prevent later effects and partial commits; the last
  reports possible completed effect/no rollback and structural interruption.

- [ ] **Step 3: Write RED cancel/process/capacity tests.**

  Cover partial durable replay then client cancel, permission cancellation, process death with
  expired lease, live-lease busy, multibyte capacity edge, oversized complete response, bounded
  terminal seal, sealed prompt refusal, and successful sealed load replay. Assert cancellation
  commits `interrupted/client_cancelled`, projects the user and every already durable assistant unit
  plus trusted `incomplete — do not treat as final` state, and does not represent the partial answer
  as complete.

- [ ] **Step 4: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_session_models.py tests/unit/acp/test_session_store.py -q
  ```

- [ ] **Step 5: Implement staged durable orchestration.**

  Centralize a helper that encodes/measures and commits one replayable update before calling
  `outbound.notify`. Start the 10-second lease heartbeat after acquisition, serialize heartbeat and
  commits, keep it active while awaiting permission, and cancel/await it on every terminal path.
  Do not expose a streaming helper for final agent responses. On absolute overflow, commit the
  reserved structural marker and seal without storing/emitting a prefix. On client cancellation,
  retain replay and project the user plus all durable client-visible assistant units with trusted
  structural incomplete-state metadata. On context exhaustion or refusal, retain replay but exclude
  the turn from semantic projection.

- [ ] **Step 6: Run unit and live-Redis GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_session_models.py tests/unit/acp/test_session_store.py -q
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_load_live_redis.py tests/integration/acp/test_server_stream_live_redis.py -q
  ```

  Expected: all ordering/fault/cancel/capacity cases pass with no partial final agent update.

- [ ] **Step 7: Checkpoint Task 7B.**

  Record ordered traces and exact irreversible-effect wording. Commit only with separate
  authorization, subject `feat(acp): make replay durability precede emission`.

### Task 8: Prove restart, replay, and practical depth with real `acpx`

**Files:**

- Create: `tools/run_plan117_acpx_resume_evidence.py`
- Create: `tests/unit/tools/test_run_plan117_acpx_resume_evidence.py`
- Modify: `tools/verify_plan117_resume_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan117_resume_evidence.py`
- Create: `reports/plan-11-7-acpx-resume-evidence.md`
- Create: `reports/plan-11-7-acpx-resume-evidence.json`
- Create: `reports/plan-11-7-acpx-artifact-manifest.json`

**Interfaces:**

- Uses external `acpx` 0.12.0, real agent processes, real Redis, and real Gateway.
- Produces machine-verifiable restart/replay/depth evidence without invoking ordinary
  `sessions list`.

- [ ] **Step 1: Write RED driver/verifier tests.**

  Pin exact `acpx` version validation, `sessions ensure --resume-session $plan117SessionId`, two distinct
  agent PIDs, no project-authored ACP client, no `sessions list`, sanitized environment, artifact
  hashes, replay sequence equality, and verifier rejection of tampering/missing usage/cost fields.

- [ ] **Step 2: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_acpx_resume_evidence.py tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

- [ ] **Step 3: Implement bounded external-client evidence capture.**

  The tool must initialize/new/prompt through `acpx`, record the session ID, terminate only its
  owned agent process, start a second process, load via
  `sessions ensure --resume-session $plan117SessionId`, verify replay, and continue with a second prompt.
  Capture exact NDJSON and Redis TTL/revision metadata without logging credentials or source bodies.

- [ ] **Step 4: Add the model-specific depth run.**

  Continue deterministic low-risk prompts in the same session until the first of unchanged `$0.05`
  cost, model context, planning limit, or 256 KiB capacity terminates. Record
  `turns_to_first_limit`, limit kind, exact model/version, provider, provider-reported token/cost
  fields, cache hit, and session/run IDs. Do not label the observation a general turn limit.

- [ ] **Step 5: Run unit GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_acpx_resume_evidence.py tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

- [ ] **Step 6: Capture and verify live evidence.**

  ```powershell
  uv run --frozen python tools/run_plan117_acpx_resume_evidence.py --acpx-version 0.12.0
  uv run --frozen python tools/verify_plan117_resume_evidence.py --acpx reports/plan-11-7-acpx-artifact-manifest.json
  ```

  Expected: real restart/load/replay/continue succeeds; depth terminates with one named first limit;
  all artifact hashes and usage/cost fields verify.

- [ ] **Step 7: Checkpoint Task 8.**

  Record dependency identities and hashes. Commit only with separate authorization, subject
  `test(acp): prove durable resume with external acpx`.

### Task 9: Prove real Zed reopen and continued history

**Files:**

- Create: `reports/plan-11-7-zed-resume-evidence.md`
- Create: `reports/plan-11-7-zed-resume-artifact-manifest.json`
- Modify: `tools/verify_plan117_resume_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan117_resume_evidence.py`

**Interfaces:**

- Consumes Task 0's pinned Zed identity/discovery path.
- Produces real-IDE evidence that Zed reuses the stored session ID, calls load after process restart,
  renders replay, and continues the same literal model history.

- [ ] **Step 1: Extend RED verifier tests for Zed artifacts.**

  Require Zed executable/source hashes, pinned commit, two agent PIDs, one session ID, initialize
  capability, load request, ordered replay updates, continued prompt, SQLite session-ID evidence,
  sanitized logs/screenshots, and artifact hashes.

- [ ] **Step 2: Run RED verifier.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

- [ ] **Step 3: Capture the real reopen.**

  With real Redis/Gateway and the pinned Zed build: create and prompt; close only the agent process;
  reopen the existing Zed thread; capture top-level capability discovery, `session/load`, replay,
  and a follow-up prompt whose Gateway input contains exact prior committed history. Record that
  Zed does not require `session/list`.

- [ ] **Step 4: Verify artifacts and render semantics.**

  ```powershell
  uv run --frozen python tools/verify_plan117_resume_evidence.py --zed reports/plan-11-7-zed-resume-artifact-manifest.json
  ```

  Expected: one session survives two processes, replay order matches Redis, follow-up history hash
  matches the ledger, and Zed remains stable.

- [ ] **Step 5: Checkpoint Task 9.**

  Record exact Zed/version/source/binary identities and screenshots. Commit only with separate
  authorization, subject `test(acp): prove Zed session reopen`.

### Task 10: Close `P9.8-FU-5` with the pre/post refusal matrix

**Files:**

- Create: `reports/plan-11-7-zed-refusal-matrix.md`
- Create: `reports/plan-11-7-zed-refusal-artifact-manifest.json`
- Modify: `tools/verify_plan117_resume_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan117_resume_evidence.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:**

- Consumes Task 0 cases 1/2 and Task 1 mapping.
- Produces cases 3/4, ancestry-backed proof of ordering, and either stable Zed evidence or a named
  externally owned defect disposition.

- [ ] **Step 1: Write RED matrix/verifier tests.**

  Require four rows:

  | Mapping | Internal input | Required wire/result |
  |---|---|---|
  | baseline | genuine model refusal | legacy `end_turn` |
  | baseline | unknown/ambiguous attempt | legacy `refusal` or exact non-reproduction |
  | implementation | genuine model refusal | conformant `refusal` |
  | implementation | unknown internal reason | invariant failure; no spurious `refusal` |

  Require each live row's Zed render/panic result and hashes. Verify the baseline commit is an
  ancestor of the implementation commit; reject timestamps or prose as ordering proof.

- [ ] **Step 2: Run RED verifier tests.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_resume_evidence.py tests/unit/acp/test_spec_protocol.py -q
  ```

- [ ] **Step 3: Capture cases 3 and 4 after Task 1.**

  Use the same real Zed build/dependency class as Task 0. Produce a real genuine model refusal and
  verify `stopReason: refusal` plus stable rendering. Prove unknown internal reasons fail the unit
  invariant and cannot be serialized as refusal. Do not recreate or overwrite Task 0 baseline
  artifacts.

- [ ] **Step 4: Verify ancestry and re-hash both halves.**

  ```powershell
  $plan117Manifest = Get-Content -Raw -LiteralPath "reports/plan-11-7-zed-refusal-artifact-manifest.json" | ConvertFrom-Json
  git merge-base --is-ancestor $plan117Manifest.baseline_commit $plan117Manifest.implementation_commit
  uv run --frozen python tools/verify_plan117_resume_evidence.py --refusal reports/plan-11-7-zed-refusal-artifact-manifest.json
  ```

  Expected: ancestry exits 0 and every baseline/implementation artifact re-hashes.

- [ ] **Step 5: Dispose `P9.8-FU-5`.**

  If current Zed renders conformant refusal stably, close the backlog item with the matrix. If it
  still panics, stop Plan 11.7 closure until an external Zed issue or a separately named internal
  follow-up/plan owns the defect; do not weaken ACP conformance or add an unreviewed workaround.

- [ ] **Step 6: Checkpoint Task 10.**

  Record both commit IDs, ancestry output, hashes, and disposition. Commit only with separate
  authorization, subject `test(acp): close Zed refusal stability matrix`.

### Task 11: Coordinate custody, refresh docs, and close mechanically

**Files:**

- Modify: `README.md`
- Modify: `tests/fixtures/acp/README.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `tools/verify_plan117_resume_evidence.py`
- Modify: `tests/unit/tools/test_verify_plan117_resume_evidence.py`
- Create: `reports/plan-11-7-closure-evidence.md`
- Create: `reports/plan-11-7-closure-artifact-manifest.json`
- Modify: this plan's checkboxes and Status line only after each named command passes

**Interfaces:**

- Closes owned `P11-FU-1` and `P9.8-FU-5`.
- Coordinates, but does not take ownership of, `P11-FU-4`.
- Preserves custody for `P11-FU-9`, narrowed `P11-FU-10`, and Plan 12.
- Produces final claim-to-evidence, artifact hashes, ancestry, coverage, Ruff, and mechanical
  checkbox/status gates.

- [ ] **Step 1: Write RED documentation/custody tests.**

  Extend the verifier to require:

  - correct top-level `loadSession` wording in living backlog/charter/README;
  - `P11-FU-1` and `P9.8-FU-5` evidence-backed dispositions;
  - `P11-FU-9` and narrowed `P11-FU-10` still open with named custody;
  - `P11-FU-4` coordinated evidence/disposition without ownership transfer;
  - `P11-FEAT-REGISTRY` named excluded-capability row for literal-history limits/Plan 12;
  - unchanged `$0.05` ACP default and no turn-count promise;
  - expected frozen-plan `-32002` matches;
  - zero unchecked plan boxes and a current Status line at closure.

- [ ] **Step 2: Run RED closure verifier.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  ```

  Expected: documentation/custody/closure requirements fail before updates.

- [ ] **Step 3: Update living documentation and custody.**

  Document `session/load` versus `session/resume`, top-level capability, Redis retention/capacity,
  recovery/error behavior, unsupported methods, MCP posture, literal-history/Plan 12 boundary, and
  real client evidence. Correct living factual prose; do not edit frozen historical plan bodies.
  Coordinate fresh FU-4A/FU-5 artifact re-pin with `P11-FU-4` or record its review-approved
  independent disposition.

- [ ] **Step 4: Run focused and live suites.**

  ```powershell
  uv run --frozen pytest tests/unit/acp tests/unit/agent tests/unit/gateway tests/unit/optimus_gateway tests/unit/redis tests/unit/tools/test_run_plan117_acpx_resume_evidence.py tests/unit/tools/test_verify_plan117_resume_evidence.py -q
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_store_live_redis.py tests/integration/acp/test_session_load_live_redis.py tests/integration/acp/test_server_stream_live_redis.py -q
  uv run --frozen pytest -m requires_gateway tests/integration/agent/test_session_history_live_gateway.py -q
  ```

  Expected: all pass with real dependencies for marked tiers.

- [ ] **Step 5: Run default suite, coverage, and static fitness.**

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  ```

  Expected: default suite passes, aggregate production coverage is at least 80%, Ruff and diff
  checks are clean.

- [ ] **Step 6: Re-run all live client evidence and final verifier.**

  ```powershell
  uv run --frozen python tools/verify_plan117_resume_evidence.py --all reports/plan-11-7-closure-artifact-manifest.json
  ```

  Expected: Task 0, `acpx`, Zed resume, refusal matrix, Redis/Gateway, and closure artifacts all
  re-hash; manifests name real dependency identities.

- [ ] **Step 7: Prove ancestry and artifact integrity mechanically.**

  ```powershell
  $plan117Closure = Get-Content -Raw -LiteralPath "reports/plan-11-7-closure-artifact-manifest.json" | ConvertFrom-Json
  git merge-base --is-ancestor $plan117Closure.baseline_commit $plan117Closure.implementation_commit
  Get-FileHash -Algorithm SHA256 -LiteralPath "tests/fixtures/acp/acp-v1-schema.json"
  ```

  Expected: ancestry exits 0 and schema hash remains
  `92C1DFCDA10DD47E99127500A3763DA2B471F9AC61E12B9BF0430C32CF953796`. Re-hash every artifact
  listed in the closure manifest; timestamps/narrative order are not evidence.

- [ ] **Step 8: Apply the checkbox and Status closure gate.**

  Only after Steps 1-7 pass, mark their boxes and every previously verified box. Set Status to an
  evidence-backed implemented/verified state. Then run in Git Bash:

  ```bash
  grep -c '^- \[ \]' docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md
  grep -n '^\*\*Status:\*\*' docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md
  ```

  Expected before the closing commit: first command prints `0`; second prints the current
  implemented/verified Status.

- [ ] **Step 9: Final status/staging audit; commit only with separate approval.**

  ```powershell
  git status --short --branch
  git diff --cached --check
  ```

  Verify no reviewer checkpoint, credential, raw secret, unrelated worktree change, or frozen-plan
  rewrite is staged. If authorized, make the closing commit. Before merge, rerun the two Git Bash
  closure commands and require the same `0`/current-Status results.

## Implementation Handoff

This draft becomes the implementation contract only after operator approval records its exact
SHA-256 in Task 0. Implementation then starts at Task 0 on the pinned baseline; no worker may skip
the pre-change Zed evidence, silently change a frozen decision, or mark a checkbox from narrative
claims.
