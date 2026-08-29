# Plan 11.7 `P11-FEAT-ZED-RESUME` Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement durable ACP `session/load` for current Zed, preserving complete sanitized
conversation history across Optimus process restarts and proving that a non-empty replay keeps
Zed's session binding across a clean shutdown.

**Architecture:** Keep `ConversationState` as the one canonical conversation model introduced by
Plan 11.25. Add a schema-versioned Redis ledger beneath it, hydrate that state on load, and make
the ledger the durable source for both model-history projection and ordered ACP replay. Preserve
`TurnControl`, `NoticeControl`, settlement, and `DedicatedOutboundWriter` as the existing lifecycle
and delivery authorities. `session/load` acquires one lease, hydrates one `AcpSpecSession`, emits
every stored `session/update` through the authoritative writer, and returns `{}` only after a
non-empty replay has flushed successfully.

**Tech Stack:** Python 3.14, ACP v1 vendored schema, asyncio, Redis 8 with TimeSeries, redis-py
async client, Pydantic, pytest/pytest-asyncio, Ruff, `acpx` 0.12.0, current Zed for Windows, SQLite
offline inspection, Git, and the repository evidence-handoff redaction gate.

**Spec:** The current execution authority is this v2 plan plus the ACP v1 schema in
`tests/fixtures/acp/acp-v1-schema.json`. Historical requirements remain evidentiary inputs in the
immutable 2026-07-29 plan and its three dated amendments. Current-state authority and the accepted
2026-08-22 disposition are recorded in
`D:\Projects\Development\Python\optimus-agent-handoff\CURRENT.md`.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---:|---|---|
| credentials/authority | Operator accepts the independent 2026-08-22 disposition and authorizes this forward-only v2 | yes | Operator | N/A; acceptance is recorded in the handoff log and the request that created this plan. |
| code/state | Exact implementation baseline is `origin/main == cd7014d`; frozen Plan 11.7 and all three amendments remain byte-identical | yes | Task 0 implementer and docs-hygiene tests | N/A; re-verify before any Task 0 edit. Any drift requires review, not silent rebasing. |
| code/state | Production durable `session/load`, Redis ledger, hydration, and replay do not yet exist | no | Tasks 1-8 implementer | genuinely absent but buildable now; this plan schedules the work after Task 0 acceptance. |
| code/state | The 2026-08-22 raw artifacts have passed the redaction gate and have a committed sanitized derivative | no | Task 0 evidence custodian | merely unauthorized evidence promotion; raw artifacts remain private and untracked. |
| code/state | Plan 11.25 architecture is reconciled with every v1 Plan 11.7 responsibility and independently accepted | no | Task 0 implementer and independent reviewer | genuinely absent but buildable now; Task 0 produces and reviews the required report before Tasks 1-11. |
| code/state | Current Zed's create-without-prompt/reopen path is classified for zero-entry-ledger reachability | no | Task 0 evidence custodian and independent reviewer | genuinely absent but buildable now; Lifecycle A′ must establish it before the zero-entry production policy or Tasks 1-11 are authorized. |
| services | Real Redis TimeSeries and Gateway are reachable for live tiers | unknown | Operator owns machine state; Tasks 9-10 implementer verifies | genuinely hard external dependency until Task 0/Task 9 preflight establishes exact availability. |
| tooling/binaries | Exact current Zed, independent `acpx`, `optimus-agent` trampoline, executing modules, and SQLite tooling are available and pinned | unknown | Operator owns installation state; Task 0 evidence custodian verifies | genuinely hard version-sensitive external state until Task 0 records exact identities. |
| credentials/authority | Bounded live Zed launch and redaction/promotion are approved for Task 0 and Task 10 | no | Operator | merely unauthorized operator action; plan approval does not itself approve each live launch or evidence promotion. |
| human interaction | Hermetic Zed GUI launch, thread creation, and clean shutdown ceremony can be performed | no | Operator performs or explicitly delegates; evidence custodian records | merely unauthorized operator action; the GUI ceremony cannot be replaced by a project-authored client. |
| cost | Paid Gateway/model calls required by Tasks 8-10 are approved | no | Operator | merely unauthorized paid call; unit and offline work incurs no required provider cost. |

## Authority and Forward-Only Supersession

Approval of this v2 is the forward-only authority event. It does not rewrite, retract, or
retroactively reinterpret historical bytes.

The controlling disposition is:

> The 2026-08-02 Task 0 Step 4 disposition remains immutable historical evidence for Zed 1.13.1 and is
> neither retracted nor re-executed. Current-version evidence dated 2026-08-22 establishes that Zed
> 1.16.1 issues `session/load` when Optimus advertises top-level `loadSession`. Approval of Plan 11.7
> v2 supersedes the three correlation-fallback amendments as current execution authority, retires
> `P11-FU-11` without claiming completion, and replaces their blocking sequence with the v2
> current-client evidence gate. Tasks 1-11 remain blocked until that gate and the Plan 11.25
> architectural reconciliation are independently accepted.

The authority effects are exact:

| Historical document or item | v2 disposition |
|---|---|
| `2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md` | Preserved unchanged as v1 approval history. This `_v2` file is the current implementation authority. |
| `2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md` | Preserved unchanged as historical evidence; superseded for current execution. |
| `2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md` | Preserved unchanged as historical evidence; superseded for current execution. |
| `2026-08-04-plan-11-7-retry-preflight-gate-amendment.md` | Preserved unchanged as historical evidence; superseded for current execution. |
| `P11-FU-11` | **Retired — superseded premise.** Never mark Closed and never claim its acceptance criteria completed. |
| `P11-FU-1` / `P11-FEAT-ZED-RESUME` | Remain open until this plan's implementation and evidence gates close. |

The stale editable-install explanation remains **most likely**, not demonstrated. The observed
Aug-1 snapshot was deleted before it could be sealed, so no report, backlog entry, or closure note
may upgrade W1 into a proved root cause. The 2026-08-15, 2026-08-17, and 2026-08-19 probes were
indeterminate; they were not negative Zed findings. The 2026-08-02 Zed 1.13.1 observation remains a
historical negative with the documented artifact-custody limitation.

## Frozen Replay Requirement

This requirement is copied verbatim from the accepted 2026-08-22 disposition and is not open to
implementation reinterpretation:

> For a stored non-empty session, `session/load` MUST emit every required replay `session/update`
> through the authoritative writer before returning successful `{}`. A successful zero-entry replay is
> forbidden unless an explicit empty-session policy proves that Zed retains a resumable binding. Zed
> evidence must verify the database binding remains non-null across clean shutdown and reopen.

This plan provisionally chooses the fail-closed empty-session policy: a ledger with zero replay
entries is not loadable. It returns `INVALID_REQUEST` with sanitized, stable data and emits no
`session/update`; it does not return `{}`. That policy becomes execution authority only if Task 0
Lifecycle A′ proves that current Zed does not reach `session/load` after create-without-prompt and
clean reopen. If A′ preserves a non-null binding or Zed issues `session/load`, Task 0 stops with
`ZERO_ENTRY_REACHABLE_STOP`; the condition/error table and Tasks 4, 6, 7, 9, and 11 are not
authorized until a forward-only v2 revision defines and proves an explicit empty-session policy.
Task 0's separate prompted-thread arm deliberately uses an isolated empty-success stub only to
prove the current-client call and record Zed's resulting binding loss; production Tasks 1-11 must
never copy that stub behavior.

## Scope and Non-Scope

In scope:

- top-level `agentCapabilities.loadSession = true` after durable startup succeeds;
- durable `session/new`, sanitized replay entries, canonical conversation state, TTL, lease, and
  optimistic revision custody in the existing process-wide Redis runtime;
- exact `session/load` validation, MCP re-disposition, hydration, replay, and `{}` response order;
- restart, expiry, malformed record, live-owner, process-loss, cancellation, delivery ambiguity,
  context-capacity, and irreversible-effect fault behavior;
- independent `acpx` and real Zed evidence; and
- living backlog/roadmap status, including the `P11-FU-11` retirement.

Out of scope:

- ACP `session/resume`, `session/list`, `session/fork`, or `session/delete`;
- compression, summarization, pruning, eviction beyond the approved TTL, or increasing the
  Plan 11.25 conversation cap;
- a second conversation model, direct NDJSON writes, a second Redis pool, or a second lifecycle
  authority;
- reopening origin-A correlation budgets or completing the retired retry-preflight premise;
- provider-key custody, Gateway architecture changes, or MCP catalog/discover-and-connect; and
- claiming machine-power-loss durability beyond the repository's accepted Redis persistence
  configuration. Here, durable means survival across Optimus process restarts and Redis data
  retention under the configured service.

## Plan 11.25 Architectural Reconciliation

The v1 decomposition predates the code at baseline `cd7014d`. Executing it literally would create
a second conversation model and bypass the lifecycle machinery that now owns cancellation,
delivery, effect, cost, and settlement.

| v1 responsibility | Current v2 owner | Required reconciliation |
|---|---|---|
| Conversation records, capacity, cost, and planner history | `src/optimus/acp/conversation.py::ConversationState` | Add immutable snapshot/hydration operations; do not create `src/optimus/agent/conversation.py`. |
| Per-turn cancellation, execution gates, effect, and terminal classification | `src/optimus/acp/lifecycle.py::TurnControl` plus `src/optimus/acp/settlement.py` | Durable code consumes these authoritative facts; it never mirrors cancellation/effect state. |
| Non-turn load response and replay-send capability | `NoticeControl`, `ResponseHandle`, and `NdjsonOutboundChannel` | Replay sends and the final load response remain non-turn work with explicit writer completions. |
| Every physical ACP notification/request/response write | `src/optimus/acp/outbound_writer.py::DedicatedOutboundWriter` | No load or replay path calls a physical writer directly. |
| Session orchestration and in-process identity | `AcpDuplexAdapter`, `AcpSpecSession`, and `InMemoryAcpSpecSessionStore` | Add exact-ID load attachment and durable-store injection; do not add a parallel adapter. |
| Client-supplied MCP disposition | `src/optimus/mcp/client_disposition.py` | Add a load-specific seam over the same normalization, permission, lease, and cleanup owners. Never persist raw MCP credentials. |
| Redis construction and shutdown | `src/optimus/redis/runtime.py` and `src/optimus/acp/bootstrap.py` | The session store shares `RedisRuntime.client`; no per-session client or silent memory fallback. |
| Wire error allocations | `src/optimus/acp/errors.py` and Plan 11.18's oracles | Add only `SESSION_BUSY = -32900`; use existing ACP/JSON-RPC codes for all other mapped conditions. |
| Error-registry cleanup formerly in v1 | Completed Plan 11.18 / `P11-FU-10` | Do not redo it. Extend its central registry and AST/schema tests only where `SESSION_BUSY` requires. |

`reports/plan-11-7-v2-architecture-reconciliation.md` must freeze the exact baseline symbols and
the mapping above before Tasks 1-11. An independent reviewer must accept that report together with
the Task 0 client gate. A green test suite is not a substitute for that acceptance.

## Durable Contract

`AcpSessionLedger` is the schema-v1 Redis value. It contains one exact `session_id`, canonical
`cwd`, fixed `execution_mode`, monotonic `revision`, lease metadata, expiry metadata, a
`ConversationSnapshot`, and an ordered tuple of sanitized `ReplayEntry` values. It contains no raw
credential, environment value, permission answer, telemetry payload, or alternate conversation
history.

`ConversationSnapshot` is the serialized form of the existing `ConversationState`: ordered
five-field `ConversationTurn` records keyed by `turn_seq`, next sequence, disposition, warning
state, session cost, cost completeness, and applied-cost turn identities. Hydration must reproduce
the exact planner envelope, byte count, gauge, next sequence, disposition, and cost. The snapshot
type is persistence DTO only; it has no admission, cancellation, or settlement behavior.

Each `ReplayEntry` stores one exact already-sanitized `session/update` payload, its turn sequence,
within-turn ordinal, provenance (`replay_user_prompt` or `live_agent_update`), and canonical
SHA-256. Each admitted prompt contributes a replay-only ACP `user_message_chunk` derived from the
same sanitized user prompt stored in `ConversationState`; every client-visible live agent update
contributes the identical payload that was sent live. This is the complete replay stream, including
both sides of the conversation, rather than a transcript reconstructed from telemetry. The ledger
never stores or re-emits JSON-RPC request IDs.

The Redis key is `optimus:acp:session:{session_id}`. The configured session retention is resolved
once at startup. Creation, append/finalize, load-refresh, lease acquire/release, and process-loss
recovery use `WATCH`/CAS over one revision; a conflict is classified, not silently retried.

Subject to Task 0 Lifecycle A′ returning `ZERO_ENTRY_UNREACHABLE`, the production condition/error
map is:

| Condition | Result and side effects |
|---|---|
| Invalid request shape, cwd mismatch, unsupported additional root, or zero-entry ledger | `INVALID_REQUEST`; no replay, no TTL refresh, no in-memory attach. |
| Missing or expired session | ACP `RESOURCE_NOT_FOUND`; no replay. |
| Live foreign lease | Optimus `SESSION_BUSY = -32900`; no replay or TTL refresh. |
| Malformed/unsupported ledger schema or Redis failure | sanitized `INTERNAL_ERROR`; no in-memory downgrade and no capability success claim. |
| Successful non-empty load | recover/acquire lease, CAS-refresh revision and TTL, hydrate, emit every replay entry in order, then return `{}`. |
| Replay send not conclusively flushed | no `{}` success; abandon the in-process attach, preserve authoritative writer/settlement classification, and release or expire the lease according to the classified state. |

## File and Responsibility Map

| Path | Responsibility |
|---|---|
| `src/optimus/acp/session_models.py` | Persistence-only schema-v1 ledger, replay-entry canonicalization, decoding, and semantic validation. |
| `src/optimus/acp/session_store.py` | Store protocol, semantic outcomes, lease/revision operations, and `RedisAcpSessionStore`. |
| `src/optimus/acp/conversation.py` | Existing canonical model plus exact snapshot/hydration; no competing model. |
| `src/optimus/acp/shapes.py` | Schema-derived replay builders, including the missing ACP `user_message_chunk` shape. |
| `src/optimus/acp/spec.py` | Durable new/prompt/load orchestration and exact replay-before-response behavior. |
| `src/optimus/acp/server.py` | Inject shared session store; preserve response ownership and the dedicated writer. |
| `src/optimus/acp/bootstrap.py` | Resolve retention once and construct runner/session store from one `RedisRuntime`. |
| `src/optimus/redis/runtime.py` | Expose one session-store factory sharing the existing async client. |
| `src/optimus/acp/errors.py` | Add central `SESSION_BUSY = -32900`; no other raw production code literal. |
| `src/optimus/mcp/client_disposition.py` | Load-specific re-disposition using request-supplied `mcpServers` and existing safety owners. |
| `tools/probe_p11_zed_session_load.py` | Extend the existing current-Zed probe with v2 load-only/provenance/database evidence. |
| `tools/verify_plan117_v2_current_client_evidence.py` | Offline, fail-closed verifier for Task 0 and Task 10 manifests. |
| `tests/unit/acp/test_session_models.py` | Canonical schema, hydration, privacy, replay, capacity, and malformed-input tests. |
| `tests/unit/acp/test_shapes.py` | Exact user/agent replay notification shapes derived from the vendored schema. |
| `tests/unit/acp/test_session_store.py` | Lease, CAS, TTL, conflict, cleanup, and failure-stage tests. |
| `tests/unit/acp/test_spec_protocol.py` | New/load/prompt ordering, writer, MCP, replay, errors, settlement, and history tests. |
| `tests/unit/acp/test_error_code_registry.py` | Central-code set and schema/AST oracles including `SESSION_BUSY`. |
| `tests/unit/mcp/test_client_disposition.py` | Load re-disposition, reapproval, mismatch, failure cleanup, and secret non-persistence. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Deterministic v2 probe custody tests. |
| `tests/unit/tools/test_verify_plan117_v2_current_client_evidence.py` | Verifier tamper, omission, redaction, ordering, provenance, and DB-binding tests. |
| `tests/integration/acp/test_session_store_live_redis.py` | Real Redis lease/CAS/TTL/recovery behavior. |
| `tests/integration/acp/test_session_load_live_redis.py` | Two-process new/prompt/load/replay/follow-up behavior. |
| `tests/e2e/acp/test_session_load_restart.py` | Real `optimus-agent` process plus independent `acpx` restart proof. |
| `reports/plan-11-7-v2-current-client-gate/` | Committed sanitized Task 0 manifest/report/relay extracts and offline-verifier result. |
| `reports/plan-11-7-v2-architecture-reconciliation.md` | Accepted current-source ownership map. |
| `reports/plan-11-7-v2-acpx-restart/` | Committed sanitized Task 9 evidence. |
| `reports/plan-11-7-v2-zed-resume/` | Committed sanitized Task 10 evidence. |
| Living pool, roadmap, README, and docs hygiene tests | Supersession, retirement, user contract, closure, and freshness. |

Forbidden creation: `src/optimus/agent/conversation.py`, any second outbound writer, any second
Redis pool, or a second session/cancellation/effect state machine.

## Task Dependency Order

```text
Task 0 current-client gate + architecture acceptance
  -> Task 1 durable schema/hydration
  -> Task 2 Redis lease/CAS store
  -> Task 3 runtime/capability wiring
  -> Task 4 durable new + MCP load disposition
  -> Task 5 turn/update persistence under Plan 11.25 ownership
  -> Task 6 session/load + authoritative replay
  -> Task 7 fault/concurrency/recovery matrix
  -> Task 8 capacity/depth/refusal contract
  -> Task 9 real Redis + independent acpx restart
  -> Task 10 real Zed binding-retention proof
  -> Task 11 living docs and closure
```

## Tasks

### Task 0: Replace the historical blocker with a current-client gate and accepted architecture map

**Files:**

- Create: `reports/plan-11-7-v2-current-client-gate/manifest.json`
- Create: `reports/plan-11-7-v2-current-client-gate/report.md`
- Create: sanitized relay/database-derived artifacts under the same report directory
- Create: `reports/plan-11-7-v2-architecture-reconciliation.md`
- Create: `tools/verify_plan117_v2_current_client_evidence.py`
- Create: `tests/unit/tools/test_verify_plan117_v2_current_client_evidence.py`
- Modify: `tools/probe_p11_zed_session_load.py`
- Modify: `tests/unit/tools/test_probe_p11_zed_session_load.py`
- Modify: the living consolidated backlog, roadmap, and docs-hygiene test
- Do not modify or re-run: the v1 plan or any of its three amendments

**Interfaces:** Produces one committed, sanitized, offline-verifiable current-client finding,
including a determinate zero-entry-reachability classification, and one independently accepted
source-ownership map. It makes no production capability change.

- [ ] **Step 1: Record the v2 authority in living status.** Write RED docs-hygiene assertions that
  require all three amendments to be described as historical and superseded for current execution,
  require the 2026-08-02 disposition to remain historical Zed 1.13.1 evidence, and require
  `P11-FU-11` to read exactly **Retired — superseded premise**, never Closed. Update the living pool
  and roadmap, then run the focused docs test. Do not edit digest-pinned history.

- [ ] **Step 2: Inventory the untracked 2026-08-22 evidence without promoting claims.** Record each
  raw path and SHA-256 in a private `tmp/plan-11-7-v2-current-client-gate/` custody manifest. Record
  the pre-freeze brief digest `EA96538DD2B6B1E8FA96613BF38B58DEAE5CD60D016A457AD5C4E87CE86321A2`
  and the post-addendum digest
  `18DA4100072358318E2FBC89415B4B29CBA8537FF4307D624B862D5A8EF686A7`. State that W1 remains
  under-evidenced and that earlier Aug-15/Aug-17/Aug-19 probes were indeterminate. Never stage raw
  relay bytes, Zed databases, profiles, settings, credentials, or logs.

- [ ] **Step 3: Write RED verifier and probe-contract tests.** The manifest schema must require:
  exact Zed executable path/hash, CLI and app version/source revision; exact executed
  `optimus-agent` trampoline path/hash/contents digest; every executing in-repo module's resolved
  path and SHA-256; source-root HEAD; tracked diff plus untracked-source digest; hermetic profile and
  database paths expressed through approved aliases; pre-launch and post-clean-shutdown binding
  state; initialize capability payload; replay notification count; every `session/load` request ID;
  distinct request-ID count; session/new count; normal-source before/after digest; cleanup result;
  redaction-gate result; and file hashes. Add a separate Lifecycle A′ record with its own fresh
  profile/workspace identity, first-launch initialize/session-new/load counts, closed-database
  binding, reopen initialize/session-new/load counts and request IDs, post-reopen closed-database
  binding, and classification `ZERO_ENTRY_UNREACHABLE` or `ZERO_ENTRY_REACHABLE_STOP`. Omission,
  cross-arm profile reuse, duplicate load IDs, `resume: true`, source drift, ambient profile use,
  live-database inspection, raw secret/path leakage, or unverified cleanup must fail closed.

- [ ] **Step 4: Extend the bounded probe without touching normal source.** Build an isolated source
  copy from exact `cd7014d`. Apply only the temporary load-only patch: top-level
  `loadSession = true`, `sessionCapabilities = {}`, a `session/load` route, and an empty `{}` stub.
  The patch must not advertise `sessionCapabilities.resume`. Create and record the exact isolated
  `optimus-agent` trampoline used by Zed. Capture its import origins and file hashes at process
  start, not from the ambient workspace. Prove the operator's daily trampoline still resolves to
  `D:\Projects\Development\Python\optimus-cost-agent-wt-integration` on branch
  `integration/optimus-live` and exact source HEAD `cd7014d` before the run.

- [ ] **Step 5: Run Lifecycle A′ for create-without-prompt reachability.** Use a fresh hermetic Zed
  profile and workspace that are never reused by the prompted A/B arm. First launch: initialize,
  create/open one agent thread, send no prompt or permission response, record whether
  `session/new` or `session/load` occurs, then cleanly stop Zed and the agent. Inspect only a copy of
  the closed SQLite database and record whether the exact thread row has a non-null `session_id`.
  Reopen the same A′ profile/workspace against the same load-only stub, record every
  `session/new`/`session/load` request and distinct ID, answer a received load with the probe's `{}`
  stub, cleanly stop, and inspect a second closed-database copy. Classify
  `ZERO_ENTRY_UNREACHABLE` only when the pre-reopen binding is null and reopen issues no
  `session/load`; record separately whether `session/new` created a server-side empty ledger. A
  non-null pre-reopen binding **or** any reopen `session/load` is
  `ZERO_ENTRY_REACHABLE_STOP`, regardless of the post-response binding result. Latch that terminal
  stop and obtain a forward-only v2 policy revision before Tasks 1-11; continue Steps 6-10 only to
  finish the already-authorized prompted arm, cleanup, redaction, and evidence sealing. Do not let
  an implementer or reviewer choose or waive the carve-out.

- [ ] **Step 6: Run the prompted-thread current-client positive arm under explicit live approval.**
  Use a second fresh hermetic Zed user-data root and workspace. Lifecycle A creates one prompted Zed
  thread/session binding and ends with a clean Zed shutdown. Lifecycle B launches the same prompted
  profile against the load-only stub. Require exactly one distinct `session/load` request ID for
  Lifecycle A's `sessionId`, zero `session/new` requests in Lifecycle B, zero replay
  `session/update` entries, and an empty `{}` response. This is a reachability probe, not
  usable-resume evidence. Do **not** rerun historical Task 0 Step 4 and do not allocate an origin-A
  correlation.

- [ ] **Step 7: Prove the prompted empty-replay binding consequence offline.** Only after each Zed lifecycle
  exits cleanly, copy the hermetic SQLite database to private staging and inspect the copy. Bind the
  exact database path/hash and thread row identity. Require the binding before Lifecycle B to equal
  Lifecycle A's `sessionId`; record the binding after Lifecycle B's clean shutdown. The expected
  current observation is `session_id = NULL`, which proves the production empty-success stub is
  forbidden. Never query or copy an open/live Zed database.

- [ ] **Step 8: Restore and prove source/profile custody.** Remove only the verified throwaway
  source/build/profile targets created by the probe. Recompute normal HEAD, tracked diff,
  untracked-source digest, executing import origins, and trampoline identity. They must match the
  pre-run values exactly. If cleanup or source restoration is not proved, classify the run
  indeterminate and do not promote it.

- [ ] **Step 9: Pass the redaction gate and commit only sanitized derivatives.** Run the repository
  `tools/evidence_gather.py redact` flow with private capture, staging, quarantine, and sanitized
  roots under `tmp/plan-11-7-v2-current-client-gate/`. Copy only eligible sanitized output to
  `reports/plan-11-7-v2-current-client-gate/`. The committed report must distinguish measured fact,
  inference, and unknown; it must not claim the stale-install mechanism was demonstrated. Include
  both A′ and prompted A/B even when A′ produces `ZERO_ENTRY_REACHABLE_STOP`; a stop is evidence,
  not permission to omit the arm.

- [ ] **Step 10: Run the offline verifier and focused gates.** Run:

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan117_v2_current_client_evidence.py -q
  uv run --frozen python tools/verify_plan117_v2_current_client_evidence.py --manifest reports/plan-11-7-v2-current-client-gate/manifest.json
  uv run --frozen ruff check tools/probe_p11_zed_session_load.py tools/verify_plan117_v2_current_client_evidence.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan117_v2_current_client_evidence.py
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  ```

- [ ] **Step 11: Freeze and independently accept the architecture report.** Record exact baseline
  paths/symbols for `ConversationState`, `TurnControl`, `NoticeControl`, settlement,
  `DedicatedOutboundWriter`, `AcpDuplexAdapter`, `AcpSpecSession`, `RedisRuntime`, and
  `ClientMcpDisposition`. Include a negative-existence search for a second conversation model,
  writer, and Redis pool. A reviewer other than the implementer must accept both this report and
  the Task 0 evidence manifest. Acceptance requires Lifecycle A′ classification
  `ZERO_ENTRY_UNREACHABLE`; `ZERO_ENTRY_REACHABLE_STOP` cannot be waived by review. **Stop here
  until both acceptances exist. Tasks 1-11 are blocked.**

### Task 1: Define the durable ledger as a projection of `ConversationState`

**Files:**

- Create: `src/optimus/acp/session_models.py`
- Create: `tests/unit/acp/test_session_models.py`
- Modify: `src/optimus/acp/conversation.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `tests/unit/acp/test_conversation.py`
- Modify: `tests/unit/acp/test_shapes.py`

**Interfaces:** Produces immutable `ConversationSnapshot`, `ReplayEntry`, `AcpSessionLedger`,
canonical encode/decode functions, and `ConversationState.snapshot()` /
`ConversationState.from_snapshot(...)`.

- [ ] **Step 1: Write RED canonical-schema tests.** Pin schema version 1, exact fields, deterministic
  UTF-8 JSON, fixed `execution_mode`, sorted turn sequence, replay `(turn_seq, ordinal)` order,
  canonical SHA-256, provenance enum, lone-surrogate rejection, unknown-field rejection,
  malformed-enum rejection, and maximum-size behavior. Assert no raw secret, permission answer,
  environment mapping, or telemetry object can enter the DTOs.

- [ ] **Step 2: Write RED round-trip tests against the real current model.** Build
  `ConversationState` with completed, rejected, failed, and cancelled turns; warning and cap state;
  complete/incomplete cost; and effect states. Snapshot and hydrate it. Assert exact planner
  envelope, records, used bytes, next sequence, disposition, warning state, gauge, session cost,
  cost-completeness, and cost idempotence.

- [ ] **Step 3: Write RED schema-derived replay-shape tests.** Add the ACP
  `user_message_chunk` builder required to replay each stored sanitized user prompt. Validate it and
  existing agent/tool update builders against the vendored `SessionUpdate` union. Assert the user
  entry precedes that turn's agent entries and is marked `replay_user_prompt`; it is stored for
  load replay but is not echoed during the live `session/prompt` request.

- [ ] **Step 4: Run RED.** Run
  `uv run --frozen pytest tests/unit/acp/test_session_models.py tests/unit/acp/test_conversation.py tests/unit/acp/test_shapes.py -q`.
  Expected failure is the absent persistence DTO and snapshot/hydration API.

- [ ] **Step 5: Implement persistence-only values and model hydration.** Keep admission, cap,
  history rendering, and cost behavior in `ConversationState`. DTO constructors validate only.
  Hydration uses the existing `ConversationSanitizer` and rejects a snapshot whose recomputed
  envelope digest/byte count does not match. Do not import Redis, asyncio, lifecycle, or writer
  code into either model module.

- [ ] **Step 6: Run GREEN and static gates.** Run the Task 1 selector, Ruff on the six files, and
  `git diff --check`. Commit only after all pass.

### Task 2: Add the Redis lease, revision, TTL, and CAS store on the shared runtime

**Files:**

- Create: `src/optimus/acp/session_store.py`
- Create: `tests/unit/acp/test_session_store.py`
- Create: `tests/integration/acp/test_session_store_live_redis.py`
- Modify: `src/optimus/redis/runtime.py`
- Modify: `tests/unit/redis/test_runtime.py`

**Interfaces:** Produces `AcpSessionStore`, typed create/load/append/finalize/release outcomes, and
`RedisAcpSessionStore`; `RedisRuntime.acp_session_store(...)` shares `runtime.client`.

- [ ] **Step 1: Write RED contract tests.** Cover create-if-absent, exact key, TTL, load without
  refresh, load-and-acquire with refresh, same-owner idempotence, foreign live lease, expired lease
  recovery, revision conflict, append/finalize, release, missing, expired, malformed, unsupported
  schema, and Redis failure before/after an acknowledged mutation. Assert no implicit retry and no
  in-memory fallback.

- [ ] **Step 2: Write RED shared-runtime tests.** Prove plan state, telemetry, and ACP sessions use
  one `RedisRuntime.client` and pool. Assert session-store creation does not open a connection or
  read ambient environment.

- [ ] **Step 3: Run RED.** Run
  `uv run --frozen pytest tests/unit/acp/test_session_store.py tests/unit/redis/test_runtime.py -q`.

- [ ] **Step 4: Implement the async store and narrow synchronous construction seam.** Use Redis
  transactions with `WATCH`/CAS. Each operation receives an explicit operation ID and expected
  revision. Clock and owner identity are injected for deterministic tests. Never use `SCAN`, a
  blocking Redis call on the event loop, or a retry loop.

- [ ] **Step 5: Run unit GREEN.** Run the Task 2 unit selector, Ruff, and `git diff --check`.

- [ ] **Step 6: Run real-Redis integration.** With approved TimeSeries-capable Redis, run
  `uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_store_live_redis.py -q`.
  Record server/module identity, key, observed TTL/revision, conflict, and lease recovery in the
  Task 9 evidence workspace; no raw Redis URL may enter a report.

### Task 3: Wire durable startup and advertise only implemented load

**Files:**

- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/redis/runtime.py`
- Modify: relevant bootstrap/server/spec unit tests

**Interfaces:** One configured server receives one shared `AcpSessionStore`. Initialize advertises
top-level `loadSession: true` only when durable startup succeeded; `sessionCapabilities` remains
empty.

- [ ] **Step 1: Write RED configuration tests.** Pin one authorized session-retention setting with
  bounded integer validation and a stable default. Assert the configured builder creates one
  `RedisRuntime`, passes its state store and ACP session store to the server, and closes the shared
  runtime once. Missing/unhealthy Redis remains a startup failure.

- [ ] **Step 2: Write RED capability tests.** Assert healthy durable configuration advertises
  `agentCapabilities.loadSession is True` and `sessionCapabilities == {}`. A test-only adapter
  without a durable store omits `loadSession`. No branch advertises `resume`, `list`, `fork`, or
  `delete`.

- [ ] **Step 3: Run RED.** Run focused bootstrap, server, runtime, and spec tests. Expected failures
  are absent store injection and absent capability.

- [ ] **Step 4: Implement constructor injection and lifetime ownership.** Keep the adapter usable in
  pure unit tests via an explicit no-store configuration that does not advertise load. Production
  `build_configured_server` always supplies the real store after Redis preflight. Preserve the
  one-writer process lifetime and close order.

- [ ] **Step 5: Run GREEN.** Run focused tests, Ruff on changed files, and `git diff --check`.

### Task 4: Make `session/new` durable and add load-specific MCP re-disposition

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/mcp/client_disposition.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/mcp/test_client_disposition.py`

**Interfaces:** `session/new` persists a schema-v1 empty ledger before success.
`ClientMcpDisposition.disposition_for_load(...)` validates request-supplied `mcpServers` under the
same normalization, permission, durable-lease, resolver, and cleanup owners as new-session setup.

- [ ] **Step 1: Write RED durable-new tests.** Assert cwd/shape validation occurs before Redis
  mutation; store creation occurs before the success response; duplicate session ID and store
  failure remove/close provisional in-memory and MCP state; the stored ledger has zero replay
  entries and, only under Task 0's accepted `ZERO_ENTRY_UNREACHABLE` finding, is deliberately not
  loadable. If Task 0 instead recorded `ZERO_ENTRY_REACHABLE_STOP`, this task is unauthorized.

- [ ] **Step 2: Write RED MCP load tests.** Cover empty and non-empty `mcpServers`, normalization,
  permission allow/reject/timeout/outbound failure, identity fingerprint, resolver attachment,
  cwd mismatch, and cleanup. Assert raw MCP command/env/credential data never enters the session
  ledger, telemetry, error, or evidence.

- [ ] **Step 3: Run RED.** Run the focused spec and client-disposition selectors.

- [ ] **Step 4: Implement durable creation and the dedicated load seam.** Load receives the ACP
  request's required `cwd`, `sessionId`, and `mcpServers`. It does not reuse a stale in-process MCP
  object and does not infer configuration from the ledger. Use the existing permission and
  `ClientMcpLeaseAuthority` path; on any failure close every provisional capability/state once.

- [ ] **Step 5: Run GREEN.** Run focused tests, Ruff, and `git diff --check`.

### Task 5: Persist turn history and replay payloads under Plan 11.25 ownership

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/conversation.py` only for approved snapshot helpers
- Modify: `src/optimus/acp/lifecycle.py` only if an immutable existing-authority read is missing
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_lifecycle.py` only for that read seam

**Interfaces:** Every durable turn uses the existing `ConversationState`, `TurnControl`, settlement
vocabulary, outbound channel, and writer. No persistence operation becomes a new cancellation,
effect, cost, or delivery authority.

- [ ] **Step 1: Write RED ordering tests.** For each admitted prompt, stage its sanitized
  replay-only `user_message_chunk` first. For planning, permission, tool, completion, refusal,
  cancellation, and warning updates, assert the exact sanitized live-agent replay payload is staged
  under the expected revision before that same payload is submitted to the outbound channel. Assert
  final ledger snapshot and in-memory `ConversationState` advance only through the existing
  `prepare_commit` / `commit_after_final_flush` boundary. A replay-only user entry is never echoed
  during the live prompt lifecycle.

- [ ] **Step 2: Write RED settlement-integration tests.** Assert effect and cost facts are read from
  `TurnControl`/settlement and applied exactly once. Cover cancelled before provider, cancelled
  after plan, rejected permission, approved mutation, partial persistence, final notification
  conclusive failure, ambiguous flush, and transport teardown. A durable helper may classify a
  store outcome but may not revise authoritative settlement.

- [ ] **Step 3: Write RED replay-equivalence tests.** For each completed turn, compare canonical
  hashes of live `session/update` params with the `live_agent_update` replay entries and compare the
  stored sanitized user prompt with its `replay_user_prompt` entry. Assert order is stable across
  multiple turns and complete planner history is derived from the hydrated `ConversationState`,
  not from replay text parsing.

- [ ] **Step 4: Run RED.** Run focused spec, conversation, lifecycle, and session-store tests.

- [ ] **Step 5: Implement one durable turn coordinator inside the adapter boundary.** It holds the
  current store revision and operation IDs but owns no lifecycle state. Sanitize once, use that
  value for durable staging and live send, await the writer-backed outbound completion, then
  finalize the durable ledger and current conversation. Map pre-effect versus post-effect Redis
  failure according to the existing settlement/effect facts; never retry an ambiguous operation.

- [ ] **Step 6: Run GREEN.** Run the focused selector, Ruff, and `git diff --check`.

### Task 6: Implement non-empty `session/load` replay through the authoritative writer

**Files:**

- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/errors.py`
- Modify: `src/optimus/acp/server.py` only if an existing non-turn completion seam is insufficient
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_error_code_registry.py`
- Modify: `tests/unit/acp/test_stdio_ndjson.py`

**Interfaces:** Adds `SESSION_BUSY = -32900`, exact-ID session attachment, and a load handler that
returns `{}` only after every non-empty replay notification has been writer-flushed.

- [ ] **Step 1: Confirm the Task 0 zero-entry authority, then write RED request/error tests.** Require
  the accepted Task 0 manifest to classify Lifecycle A′ as `ZERO_ENTRY_UNREACHABLE`; otherwise stop
  without writing the production load mapping. Derive required load fields from the vendored ACP
  schema. Cover invalid shape, cwd outside workspace, stored/request cwd mismatch, missing, expired,
  malformed, unsupported schema, Redis failure, zero replay, live foreign lease, same-process
  duplicate attach, MCP failure, and unsupported additional directories. Pin the condition/error
  table in this plan.

- [ ] **Step 2: Write RED registry tests.** Add `SESSION_BUSY` only in `errors.py`, include it in
  `OPTIMUS_APPLICATION_ERROR_CODES`, prove `-32900` is outside the JSON-RPC reserved band and absent
  from the vendored ACP allocations, and keep the AST legacy-literal allowlist empty.

- [ ] **Step 3: Write RED replay/response-order tests against the real server.** Use at least two
  turns and multiple update kinds. Require lease/revision/TTL refresh before replay; exact
  hydration; one notification per stored entry; each turn's sanitized `user_message_chunk` before
  its agent/tool updates; strict global order; every writer future conclusively `FLUSHED`; and the
  `session/load` response bytes after the final replay bytes. Assert a zero-entry ledger emits
  nothing and returns `INVALID_REQUEST`, never `{}`.

- [ ] **Step 4: Run RED.** Run the focused spec, stdio, error-registry, model, and store tests.

- [ ] **Step 5: Implement validate -> acquire -> hydrate -> MCP -> attach -> replay -> respond.**
  Acquire/refresh under CAS before in-memory attachment. Attach the exact stored session ID, not a
  generated replacement. Replay by awaiting `AcpOutboundChannel.notify("session/update", params)`
  for each entry; this path must terminate in `DedicatedOutboundWriter`. Return the non-turn
  success envelope with `{}` only after the last flush. On any failure, emit no later entry, do not
  return success, remove the provisional in-process session, close MCP state, and release/classify
  the lease exactly once.

- [ ] **Step 6: Run GREEN and structural searches.** Run focused tests and Ruff. Search for direct
  `write_bytes`, `write_line`, and new writer construction outside existing server/writer owners;
  search for `sessionCapabilities.resume`; search for a second conversation model. Expected: no
  new bypass or duplicate owner. Run `git diff --check`.

### Task 7: Close concurrency, crash recovery, and failure-stage behavior

**Files:**

- Modify: `tests/unit/acp/test_session_store.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_lifecycle.py` only where existing owner behavior needs coverage
- Modify production files only where a RED contract exposes a missing approved seam

**Interfaces:** Proves the total state-transition matrix; adds no new feature surface.

- [ ] **Step 1: Write deterministic race tests.** Use barriers, injected clock, and controlled
  futures for two loads, load versus prompt, load versus clean release, expired-owner recovery,
  process loss after acquire, CAS conflict at append/finalize, cancel during durable staging,
  teardown during replay, and response cancellation after all replay flushes.

- [ ] **Step 2: Write failure-stage tests.** Cover Redis failure before mutation, acknowledged
  mutation then response loss, irreversible tool effect before persistence, conclusive writer
  failure, ambiguous writer failure, and cleanup failure. Assert no silent retry, duplicate replay,
  second response, in-memory downgrade, effect erasure, or cost double-application.

- [ ] **Step 3: Run RED, implement the smallest missing seams, then GREEN.** Production changes may
  expose typed outcomes or injected clocks only; they may not add another lock/state machine.
  Re-run focused tests, Ruff, and `git diff --check`.

- [ ] **Step 4: Run repeated concurrency fitness.** Run the race selector at least 25 times on
  Windows. Record the exact command and pass count in the Task 9 report. A timing-based sleep is not
  acceptance evidence.

### Task 8: Prove complete-history depth, capacity, and the refusal matrix

**Files:**

- Modify: `tests/unit/acp/test_session_models.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Create or modify: a focused hermetic ACP depth/refusal test under `tests/e2e/acp/`
- Update production only if RED reveals a v2-owned gap

**Interfaces:** Preserves Plan 11.25's 524,288-byte canonical conversation cap and closes the
resume-dependent portion of `P9.8-FU-5` without changing model/provider policy.

- [ ] **Step 1: Write RED capacity tests across restart.** Hydrate just below warning, at warning,
  at cap, and over cap. Assert exact bytes, warning idempotence, cap-closed disposition, cost gauge,
  and refusal behavior match the same-process path. No load operation resets or expands the cap.

- [ ] **Step 2: Write RED complete-history depth tests.** Create enough turns to exceed the old
  single-turn context assumption while remaining below the canonical cap. Restart/load and assert
  the next model request contains the exact complete inert-marked history once, in order, with no
  summary, truncation, or replay-derived reconstruction.

- [ ] **Step 3: Write the pre/post refusal matrix.** Cover genuine model refusal before restart and
  after load, plus context-window exhaustion. Assert replay remains available and the session
  stays coherent. Reuse Plan 11.18's central error registry and current Gateway normalization; do
  not reopen or duplicate its completed error-code work.

- [ ] **Step 4: Run RED, implement only identified v2 gaps, then GREEN.** Run unit/e2e selectors,
  Ruff, and `git diff --check`. Record which `P9.8-FU-5` criteria are now satisfied; do not close
  unrelated criteria by implication.

### Task 9: Prove restart and replay with real Redis, Gateway, processes, and independent `acpx`

**Files:**

- Create: `tests/integration/acp/test_session_load_live_redis.py`
- Create: `tests/e2e/acp/test_session_load_restart.py`
- Create: `reports/plan-11-7-v2-acpx-restart/manifest.json`
- Create: `reports/plan-11-7-v2-acpx-restart/report.md`
- Extend: the v2 offline verifier and its tests for this evidence kind

**Interfaces:** Proves one session across two real Optimus processes without depending on project
test doubles or Zed.

- [ ] **Step 1: Write the process harness test-first.** Use independent `acpx` 0.12.0, exact
  `optimus-agent` trampoline provenance, real TimeSeries-capable Redis, real Gateway, and a
  hermetic workspace. Project code may prepare/verify evidence but must not replace the ACP client.

- [ ] **Step 2: Execute Lifecycle A.** Initialize; create session; complete at least two prompts
  including one approved effect-free path and one refusal/cancellation path; record exact live
  update hashes, durable revision/TTL, planner-history digest, and clean process shutdown.

- [ ] **Step 3: Execute Lifecycle B.** Start a new Optimus process, initialize with top-level load
  only, send `session/load` for the exact ID/cwd/MCP set, require all replay update hashes in order
  before `{}`, then send a follow-up prompt and prove its planner-history digest contains all prior
  turns once.

- [ ] **Step 4: Exercise real failure cases.** Against the same Redis class prove missing, expired,
  live foreign lease, recovered expired lease, zero-entry rejection, and one controlled CAS
  conflict. Never mutate or inspect unrelated Redis keys.

- [ ] **Step 5: Redact, verify, and commit sanitized evidence.** Use the repository redaction gate,
  run the offline verifier, then run:

  ```powershell
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_store_live_redis.py tests/integration/acp/test_session_load_live_redis.py -q
  uv run --frozen pytest tests/e2e/acp/test_session_load_restart.py -q
  uv run --frozen python tools/verify_plan117_v2_current_client_evidence.py --manifest reports/plan-11-7-v2-acpx-restart/manifest.json
  git diff --check
  ```

### Task 10: Prove real Zed retains a resumable binding after non-empty replay

**Files:**

- Modify: `tools/probe_p11_zed_session_load.py`
- Modify: corresponding probe/verifier tests
- Create: `reports/plan-11-7-v2-zed-resume/manifest.json`
- Create: `reports/plan-11-7-v2-zed-resume/report.md`
- Create: sanitized relay/database-derived files under that directory

**Interfaces:** Converts Task 0's current-client reachability into real feature acceptance. The
same manifest family binds exact client, entrypoint, modules, source, profile, database, protocol,
writer ordering, Redis, and cleanup provenance.

- [ ] **Step 1: Write RED final-evidence rules.** In addition to every Task 0 provenance field,
  require production source with no temporary capability patch; non-empty replay; exact replay
  count/order/hashes; `{}` strictly after replay; one distinct `session/load` request ID; zero
  Lifecycle-B `session/new`; Redis revision/TTL; clean process/Zed shutdown; DB binding before and
  after; and a successful follow-up prompt whose model-history digest includes pre-restart turns.

- [ ] **Step 2: Execute Lifecycle A under explicit live approval.** Use current Zed and a new
  hermetic profile/workspace. Capture exact Zed executable/version/source revision, exact production
  `optimus-agent` trampoline, executing module paths/hashes, source HEAD/diff/untracked digest,
  Redis/Gateway identity class, and profile/DB paths. Create and prompt until at least one durable
  replay entry exists. Cleanly stop Zed and the agent. Inspect only a closed database copy and
  require the thread binding equals the created session ID.

- [ ] **Step 3: Execute Lifecycle B with the same hermetic profile.** Launch current Zed against a
  fresh production Optimus process. Require initialize advertises top-level `loadSession` and no
  `resume`; exactly one distinct `session/load`; no `session/new`; every stored replay
  `session/update` emitted through the writer before `{}`; and a follow-up prompt using complete
  hydrated history.

- [ ] **Step 4: Prove binding retention after clean shutdown.** Cleanly stop Lifecycle B. Copy and
  inspect the closed database. The exact thread row must still contain the same non-null session ID.
  A null/different binding, zero replay, response-before-replay, source drift, or unproved cleanup
  fails the feature gate.

- [ ] **Step 5: Restore, redact, verify, and independently review.** Recompute normal source and
  entrypoint provenance; delete only verified throwaway targets; pass all raw artifacts through the
  redaction gate; commit only sanitized derivatives; run the offline verifier and focused probe
  tests. An independent reviewer must compare Task 0's empty-replay/null-binding observation with
  Task 10's non-empty-replay/retained-binding observation and accept the causal boundary as scoped.

### Task 11: Run release gates, update living custody, and close truthfully

**Files:**

- Modify: `README.md` for current user-visible `session/load` behavior and configuration
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Create: `reports/plan-11-7-v2-release-review.md`
- Do not modify: the v1 plan or any of its three amendments

**Interfaces:** Produces final test/evidence references and living status without rewriting history
or conflating retirement with completion.

- [ ] **Step 1: Run structural conformance searches.** Prove one `ConversationState`, one
  `TurnControl` per turn, one process `NoticeControl`, one `DedicatedOutboundWriter`, one shared
  Redis client/pool, one central error-code registry, no direct replay write, no advertised resume,
  no raw replay/credential telemetry, and no zero-entry `{}` success.

- [ ] **Step 2: Run the full verification matrix.** At minimum run:

  ```powershell
  uv run --frozen pytest tests/unit/acp tests/unit/mcp tests/unit/redis tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan117_v2_current_client_evidence.py -q
  uv run --frozen pytest -m requires_redis tests/integration/acp/test_session_store_live_redis.py tests/integration/acp/test_session_load_live_redis.py -q
  uv run --frozen pytest tests/e2e/acp/test_session_load_restart.py -q
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen ruff check .
  uv run --frozen pytest --cov=src/optimus --cov=src/optimus_security --cov-report=term-missing --cov-fail-under=80
  git diff --check
  ```

- [ ] **Step 3: Re-run every offline evidence verifier from committed bytes.** Verify Task 0,
  Task 9, and Task 10 manifests in a fresh checkout with no private raw directory available. Each
  must fail on a tampered copy and pass on the committed manifest.

- [ ] **Step 4: Perform the document-freshness audit.** Update README, living backlog, and roadmap
  with exact implementation commit/PR/evidence only after those identities exist. Preserve
  `P11-FU-11` as **Retired — superseded premise**, never Closed. Close `P11-FU-1` and
  `P11-FEAT-ZED-RESUME` only if all implementation, acpx, Zed, binding-retention, redaction,
  verifier, and independent-review gates pass. Otherwise record the narrow blocker and leave them
  open.

- [ ] **Step 5: Write and independently review the release report.** Include baseline, final HEAD,
  changed-file ownership map, unit/integration/e2e counts, coverage, Ruff, docs hygiene, diff check,
  evidence manifest hashes, W1 limitation, Task 0 versus Task 10 binding comparison, known risks,
  and every still-open follow-up. The reviewer must reject any statement that Zed "always could"
  load sessions or that the stale install was proved.

## Definition of Done

- This `_v2` plan is the sole current Plan 11.7 execution authority; all historical files remain
  byte-identical.
- `P11-FU-11` is **Retired — superseded premise**, not Closed.
- Task 0 committed evidence proves current Zed issues exactly one `session/load` when only
  top-level `loadSession` is advertised, with exact entrypoint/module/source/profile/DB provenance
  and source restoration.
- Task 0 Lifecycle A′ proves whether create-without-prompt can reach a zero-entry `session/load`;
  this plan reaches Tasks 1-11 only on accepted `ZERO_ENTRY_UNREACHABLE` evidence.
- The untracked 2026-08-22 evidence has an explicit private-custody/redaction disposition and a
  committed sanitized derivative; raw evidence remains untracked.
- `ConversationState`, `TurnControl`, `NoticeControl`, settlement, and `DedicatedOutboundWriter`
  remain the unique architecture owners.
- Redis stores one canonical schema-v1 ledger and shares the process runtime; no silent fallback
  exists.
- `session/load` validates, leases, hydrates, re-disposes MCP, replays every non-empty update in
  order through the authoritative writer, then returns `{}`.
- A successful zero-entry replay is impossible in production.
- Independent `acpx` proves two-process restart, replay, and continued complete history.
- Real Zed proves the same non-null session binding before and after clean shutdown following a
  non-empty replay, then successfully continues the conversation.
- Unit, integration, e2e, coverage, Ruff, docs hygiene, offline verifier, redaction, and diff gates
  pass from committed bytes.
- Living documentation states only what the evidence proves and retains W1 as under-evidenced.

## Implementation Handoff

Start in a dedicated implementation worktree at exact `origin/main == cd7014d`. Re-verify the
operator approval, branch/HEAD, clean status, frozen-history no-diff, and the standing exact-
entrypoint invariant before editing. The operator's daily `optimus-agent` is an editable install
pointing at `D:\Projects\Development\Python\optimus-cost-agent-wt-integration` on
`integration/optimus-live`; that fact is not self-proving and must be re-measured for every live
run.

Complete Task 0 and obtain both independent acceptances before starting Task 1. If Task 0 is
indeterminate, Zed no longer issues load under load-only advertisement, architecture ownership has
drifted, or a frozen file differs, stop and request a new forward-only plan revision. Do not fall
back to the superseded amendments, rerun historical Step 4, or create a new correlation budget.

## Plan Self-Review

- Required `## Prerequisites` table is present with current satisfaction, owner, and hard-versus-
  unauthorized classification.
- Every user-required Task 0 provenance field is explicit and verifier-enforced.
- Replay wording is verbatim and production provisionally chooses an exact fail-closed zero-entry
  policy, activated only by accepted `ZERO_ENTRY_UNREACHABLE` evidence.
- Lifecycle A′ tests the zero-entry policy's reachability premise in a separate fresh profile and
  has an exact non-waivable stop outcome if Zed issues `session/load`.
- The v1 amendments remain historical; `P11-FU-11` retirement does not claim completion.
- Tasks 1-11 are explicitly blocked on both Task 0 acceptances.
- Plan 11.25 owners are named and duplicate conversation/writer/lifecycle/Redis owners are forbidden.
- The evidence-promotion gap has a named Task 0 owner and cannot be satisfied by committing raw
  artifacts.
- Error-registry work already completed by Plan 11.18 is not duplicated.
- TDD order, exact files, interfaces, verification commands, live approvals, and stop conditions
  are present without implementation placeholders.
