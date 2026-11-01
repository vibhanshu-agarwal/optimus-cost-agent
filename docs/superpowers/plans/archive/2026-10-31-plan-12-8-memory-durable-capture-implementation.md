# Plan 12.8: Memory durable capture (M0b)

> **For agentic workers:** Claude Opus implements using `superpowers:executing-plans`; Codex reviews read-only at the three checkpoints below. The operator approves the saved plan’s exact SHA-256 in Claude’s chat before Task 1 executes. Each live operation requires its own operator release.

**File:** `docs/superpowers/plans/2026-10-31-plan-12-8-memory-durable-capture-implementation.md`

## Goal

Deliver all of memory design v4 §7’s durable-capture infrastructure: an fsynced per-user outbox, immutable Postgres receipts, committed drain cursors, durable coverage epochs, append-only reconciliation evidence and the bounded per-user Gateway diagnostic copy. Extend existing accounting without calculating another debit. Prove K3 using real Postgres, interrupted writers, outages and replay.

**Base:** `c839dec55e659bf0a4676651571fa181481b80d3`, branch `agent/claude/plan12-8-memory-durable-capture`, in the supplied `optimus-cost-agent-wt-claude-p128m0b` worktree.

**Authority:** [memory design v4](../specs/2026-10-22-plan12-memory-design_v4.md), SHA-256 `708e0e7831f6d4c56b5f6442cd37c4e02eecffd2659db04f3e6a6b1c54506ff9`, especially §§2, 7, 8/K3, 8.1 and 9; accepted [ADR-031](../../decisions/ADR-031-project-memory-and-evidence.md). Read both during execution. The archived [Plan 12.6 v4](archive/2026-10-30-plan-12-6-memory-foundations-implementation_v4.md) and [Plan 12.7 v4](archive/2026-10-30-plan-12-7-memory-feasibility-implementation_v4.md) supply delivery precedents, not implementation authority.

Plan 12.7’s P4 evidence in `reports/plan12-memory-feasibility/{qualification,handoffs}.json` records Postgres 16.15, psycopg 3.3.4/libpq 18.3, transaction failures, restart, reconnect and surviving rows. It proves readiness only.

## Scope and Explicit Exceptions

Scope is a multi-file production, test, migration and documentation changeset. **No durable-capture requirement in §7 is excluded.** M0b starts coverage prospectively; earlier history remains qualified.

| Explicit exception | Named owner and boundary |
|---|---|
| Broad telemetry consolidation across event kinds and sinks | [#303](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/303). This plan owns only the receipt/lifecycle envelope, correlation, containment and storage extension needed by §7; publish that contract for #303 to consume. |
| General evidence/provider-ledger consolidation | [#341](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/341). Preserve existing ledger responsibilities and fingerprints. |
| MAIN-5 delivery-state telemetry truth | [#271](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/271). Accounting coverage does not certify conversation delivery or replace its settlement semantics. |
| Loop-control episode accounting and retry-policy redesign | [#396](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/396). Record actual attempts without adding episode policy. |
| Known-cost handling of empty, length-truncated replies | [#423](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/423). Preserve currently reported unknowns; do not invent discarded usage. |
| General Gateway processing deadline | [#442](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/442). New capture/drain/diagnostic work must not introduce an unbounded wait; this does not certify existing Gateway processing end to end. |
| Savings/comparison presentation, repricing and paid campaigns | [#248](https://github.com/vibhanshu-agarwal/optimus-cost-agent/issues/248), including OC-4. Supply measured facts and coverage, without building its tables or running models. |

**Any issue that actually blocks this plan is repaired inside this plan**, under the operator’s 2026-10-30 rule. Record absorbed criteria and evidence in its existing issue under approved GitHub authority. Do not inherit Plan 12.7’s #447 exception or silently narrow this plan.

## Design choices

Mechanisms and numeric values selected below are **agent-selected**, except requirements explicitly attributed to the spec. The host-owned capture, Gateway-owned Postgres connection, three checkpoints and proposed issue assessment have substantive review acceptance; execution still requires approval of the saved plan’s exact hash.

### Accounting and credentials

The ACP host owns accounting, receipt acceptance and the local durable boundary. It uploads capture records through its existing Gateway URL and API key. **The Gateway process owns the Postgres connection and drain transaction.** Postgres is never on model dispatch or retrieval’s required path.

Record the credential boundary in **`ADR-032-durable-usage-capture-and-gateway-drain.md`**, currently the next free number; recheck allocation before filing. The disposition is that the two-credential restriction applies to the ACP/client runtime; a Gateway-owned Postgres credential, like a Gateway-owned provider credential, belongs exclusively to the Gateway service. The host must not read a Postgres password/credential-bearing DSN, resolve a database secret, inherit one into its runtime or persist one in its outbox. Preserve the operator’s acceptance and its shared source reference in the ADR.

Use nonsecret Gateway accounting configuration under the trusted per-user config root: endpoint, database, role, credential reference and connection limits. The Gateway alone resolves its password through a distinct Gateway-owned OS-keyring namespace. Bind the nonsecret configuration identity and secret reference into the authorized Gateway launch; preserve existing launch-manifest versions when accounting is absent. Changed endpoints/references require renewed authorization. No plaintext credential enters a workspace, command line, launch evidence or diagnostic.

The existing provider seam is `ProviderSecrets.as_gateway_child_env()` in `src/optimus/acp/local_gateway_secrets.py`, projected into `gateway_environ` by `launch_gate.py` and `local_infra.py`, then consumed by `GatewayServiceConfig.from_env()`. Reuse its child-environment separation and authorized-launch binding. **Do not reuse its parent-side secret resolution for Postgres:** that would let the host see the password. Pass only the accounting configuration/root/reference; resolve the database secret inside the Gateway after verifying its authorized configuration.

Rejected alternatives:

- Host DSN/password: adds the forbidden local client credential.
- Assuming passwordless local Postgres works on every platform: P4 did not establish OS-authenticated production connectivity.
- Sharing the evidence-handoff database/store: violates ownership and isolation.
- Moving receipt acceptance or debit calculation into the Gateway: violates host-owned accounting.

### Writers, identities and epochs

The host writes epoch begin, invocation lifecycle, pre-dispatch intent, accepted `StageReceipt`, integrity incidents, terminal state and close under `<config_root>/accounting/outbox/`.

**Existing attempt visibility:** `GatewayRouteAttempt` is defined in `src/optimus/gateway/models.py` and consumed by `_attempts`/`_routed` in `src/optimus/gateway/attempts.py`. A successfully decoded enforced-routing response or correlated HTTP failure already supplies its physical route attempts in order; reuse that list. Transport loss, malformed/unavailable correlation and host death cannot supply it. Legacy internal retries are not fully represented by the existing host envelope: without a route list, `_attempts` returns the reported settled usage or one uncertain attempt.

Keep a **minimal Gateway supplemental stream containing only physical-attempt intent and outcome records**. It preserves evidence the host cannot otherwise retain: lost responses, host death mid-call and hidden legacy retries. It is not another receipt store, epoch system or accounting service. Normal received route attempts continue through the existing host classifier and settlement. Gateway observations correlate with them rather than creating another charge.

Both writers use separate streams and the same framing semantics. Gateway modules remain independently importable with zero `optimus.*` imports, following the existing observability boundary; share only neutral low-level outbox mechanics, and test host/Gateway envelope agreement.

A stream has a random UUID allocated for its writer lifetime; restart creates a new stream. Each append has a strictly increasing sequence, event UUID, schema version, previous-record digest and payload digest. Epoch and invocation IDs are UUIDs allocated before work; retries/replay retain original event identities.

Propagate the invocation ID through validated Gateway capture metadata. Durable host attempt identity is the invocation ID plus `ProviderAttempt.key`; retain existing request/attempt identifiers as correlation aliases. The Gateway allocates physical attempt identity before upstream dispatch and records its ordinal within that invocation. Do not derive identity from timestamps, PIDs or a restarted counter.

An epoch begins durably before calls. Each invocation has a durable sequenced intent before dispatch. Physical retries receive their own Gateway intent before dispatch. Put capture admission **before** the existing final dispatch-budget check; do not insert blocking work between that check and dispatch.

Terminal state records expected and settled identities plus pending invocations. Close follows actual worker settlement, not merely transport teardown. A terminal record with pending workers is incomplete. Late records remain attributable to their original epoch. An unexpected arrival after close appends an incident/reconciliation record rather than rewriting the close.

Complete coverage requires verified begin, pre-dispatch intents, every expected attempt accounted, no unknown/conflict, no pending invocation and a verified close. Existing received route lists supply attempt identities; supplemental evidence covers otherwise missing observations. A host request alone cannot prove which internal retries ran. Missing Gateway evidence or unresolved usage keeps physical-attempt coverage incomplete.

### Outbox, failure and growth

Reuse the project registry’s cross-process locking, flush/fsync and atomic-publication pattern, while addressing its documented Windows rename limitation rather than claiming that pattern already proves power-loss durability.

Records are append-only, framed and checksummed. A successful local acknowledgement follows flush and fsync. Seal segments at an agent-selected **16 MiB** boundary. Never append behind a damaged tail: preserve its bytes, record the verified prefix and start a successor segment with an explicit gap. Missing tails, sequence discontinuities and unsupported versions cannot be skipped as if clean.

Use one owned writer with bounded admission and a bounded queue; no detached per-call workers. Agent-selected defaults are **250 ms acknowledgement wait** and **1,024 queued records**. A timeout, queue overflow, lock failure, disk-full condition or fsync failure lets model work continue with unconfirmed persistence and incomplete coverage. A write completed after dispatch cannot retroactively qualify as a confirmed pre-dispatch intent. Test the timeout race explicitly.

When persistence resumes, append the gap after the last verified watermark. If begin itself could not persist, recover an explicitly unverifiable span. Boot treats every missing close as incomplete. A later clean epoch never certifies an earlier gap.

Postgres absence leaves Optimus working and locally durable records accumulating. Expose pending bytes/events, oldest pending age, last local watermark, committed drain watermark, last drain failure and disk pressure. Warn at agent-selected **256 MiB pending bytes** or **24 hours oldest pending age**. These are visibility thresholds, not deletion limits. No hard retention cap deletes unacknowledged outbox data. Finite-disk exhaustion degrades capture truthfully and never becomes a model cost stop.

### Immutable receipts and replay

Reuse:

- `TurnSettlement`, `StageReceipt`, `ReceiptConflictError`, `receipt_from_maintenance` and `UsageLedgerAdapter` in `src/optimus/usage/turn_settlement.py`.
- `UsageAccountingService`, `ProviderUsageLedger` and `ProviderUsage`.
- `ProviderAttempt` and the common response/failure classifiers.
- `RedisTelemetryEventSink` → `RedisTelemetryAdapter.record_settled_usage`.

Preserve both existing replay contracts: `StageReceipt.facts()`/`settled_facts()` compare captured receipt facts; the provider ledger’s fingerprint compares Gateway request ID, provider, provider request ID, billing units and cost. They are not interchangeable. Preserve the Redis settled-usage claim semantics without treating Redis as the durable receipt authority.

`UsageLedgerAdapter` is summarization-only; planning/answer usage already reaches the accounting service. Do not wire another debit or emit their telemetry twice.

Persist accepted receipts by attempt identity with a unique constraint for every non-null Gateway request ID. An identical same-request replay with another host alias links to the original receipt. Contradictory duplicates append integrity evidence, retain the original and never become another charge. Compare facts before advancing a cursor.

Later reconciliation appends evidence linked to the original attempt/receipt and source observation. It never updates receipt fields or silently turns an unknown into a fabricated original receipt. A reconciled projection exposes its evidence and remaining uncertainty; it cannot erase a historical coverage gap.

Use an explicit field allowlist: identity/correlation, stage/purpose, outcome, requested/resolved route, reported usage/cost, model/version, price snapshot, timing bookkeeping and coverage references. Preserve unknown, unattributed and late attempts. Missing token/cache/reasoning facts remain null. `GatewayUsage.cache_hit` currently defaults to `False`; retain field-presence information at normalization so absent cache evidence is not newly persisted as an observed miss. No prompt, response body, raw router payload, exception text or credential is admitted.

Memory maintenance uses `stage=summarization`, `purpose=memory.*`. Existing context summarization retains its own purpose. Task class remains turn-level; duration is arrival bookkeeping, not a billing input.

### Postgres and delivery contract

Use Optimus-owned migrations under `migrations/optimus_usage/`, with a distinct schema and migration table. Reuse the transaction, row-lock, parameterized-SQL and immutable migration-digest patterns from `evidence_handoff_runtime.store.PostgresLedgerStore` and `migrations.apply_migrations`; **do not instantiate their store or use their schema/database**.

| Relation | Contract |
|---|---|
| Capture events | Immutable event payload; primary key `(stream_id, sequence)`, unique event ID, recorded payload/chain digest. |
| Attempt receipts and aliases | Immutable original facts; attempt identity primary key; unique non-null Gateway request ID; replay aliases reference the canonical receipt. |
| Coverage | Durable lifecycle events and rebuildable epoch projection containing expected/settled identities, pending invocations and gap/conflict reasons. |
| Reconciliation evidence | Append-only links to original receipt/attempt and independently observed evidence. |
| Drain cursors | Ledger-instance ID, principal/stream, segment/offset, sequence and digest of the committed contiguous prefix. |
| Migration history | Ordered, digest-pinned migrations; changed applied bytes refuse advancement. |

Receipt/event immutability is enforced in the database, not solely by Python convention. Cursor/projection maintenance is permitted; receipt replacement is not.

Follow the existing host upload pattern:

- `GatewayObservabilityExporter` in `src/optimus/telemetry/observability.py` uses `GatewayClient.post_observability_json()`.
- `/v1/observability/traces` is dispatched by `src/optimus_gateway/server.py`.
- `handle_observability_traces_request`, `validate_trace_batch` and the Gateway-local envelope/result types in `src/optimus_gateway/observability.py` provide authentication, code-defined validation and explicit delivery-state precedents.
- `tests/unit/optimus_gateway/test_server.py` covers bearer rejection, malformed input, empty batches, transport dispatch and delivery-state propagation.

Add sibling **`POST /v1/observability/usage-capture`** so the existing host transport/authentication seam can be reused unchanged. Define capture request/response types and validators in code, with matching host/Gateway contract tests. No OpenAPI file, `contracts/` directory or Postman setup/publication is required.

The trace precedent does **not** already provide capture’s stricter guarantees: `validate_trace_batch` tolerates unknown keys, and the recognized-route body reader has no equivalent capture size/deadline bound. Add capture-specific strict validation and bounded framing/read/write handling without changing the existing trace contract.

Agent-selected request limits are **256 events and 1 MiB encoded body**. Reject unknown fields. Large terminal identity sets use ordered continuation records referenced by the close, without silently omitting identities.

A request identifies stream, ledger instance, previous cursor and contiguous records. The server derives authorization scope from its configured principal, not a caller-supplied user ID. Reject ownership changes, holes, contradictory replay, malformed facts and unauthorized access before acknowledging data. Capture metadata remains local to Optimus and is not forwarded to providers.

One Postgres transaction checks/inserts events, accepts immutable receipts or records replay/conflict disposition, updates coverage and advances the contiguous cursor. The code-defined response reports delivery state and acknowledges **only committed bytes**, identifying ledger instance, stream, sequence and digest. Database unavailability returns a retryable failure without acknowledgement. Unlike trace-export acceptance, an HTTP success alone is not sufficient to authorize compaction.

Record-and-dispose a conflicting observation durably so it remains visible without poisoning the stream forever; the contradictory receipt is never inserted as a charge.

The host persists the returned acknowledgement before compacting fully acknowledged **closed** segments. A crash before acknowledgement or after commit replays the same bytes. A crash after acknowledgement but before deletion merely repeats safe cleanup. A replacement database or forged/stale acknowledgement cannot authorize deletion.

Drain on owned startup/settlement/recovery opportunities with bounded background work and at most three transient attempts per trigger. Never perform Postgres work inside settlement’s lock or make provider execution wait for drain.

### Per-user Gateway diagnostic copy

The Gateway process owns one additional sink under `<config_root>/accounting/gateway-diagnostics/`. Extend `request_diagnostics.write_log_line` fan-out; preserve stderr/current workspace `local-gateway.log` behavior and paths. `stage_c_ledger_path` remains the release-specific Stage C guard ledger, not this feature’s outbox or a general receipt ledger. No Q27 path or rotation change is authorized.

The new copy contains allowlisted, sanitized structured facts with sequence and UTC time. Roll **before exceeding 64 MiB** or when the UTC day changes. Retain **30 days subject to 256 MiB total**, deleting oldest closed segments only. If space cannot be made safely, refuse that copy’s write and expose failure; never truncate the active segment or exceed the cap silently.

Flush each accepted line; orderly close flushes/closes the owned sink. The copy is best effort, not an fsynced accounting boundary. Bound its queue and isolate blocked writes from model work. Expose retained date/sequence ranges, dropped/unwritten records and delivery/retention failures, including stderr failure independently. Expired or unwritten records are unavailable reconciliation evidence. Diagnostic retention never deletes ledger or outbox rows.

### Production roots and test isolation

Production composition resolves the authorized per-user root through the existing operator-path/trusted-root flow, then explicitly injects it into capture, delivery and diagnostic components. Constructors and imports do not resolve a default root or create files.

**Every test uses a temporary config/accounting root**, including production-composition tests, live K3 tests and child processes. Tests exercising root resolution supply temporary OS-root adapters/environment values; children receive explicit temporary roots. No test falls back to the operator’s real root.

Reuse `tests/conftest.py`’s pre-collection run-context installation and `tools/testing/run_context_guard.py`’s Windows real-folder refusal, write audit and per-test synthetic-root redirection. Add focused controls for the new accounting sinks and child launches; extend test-only protection where needed for alternate platforms and subprocesses rather than weakening the existing guard.

Prove that default-suite composition cannot create anything under the real `<config_root>/accounting/`, even when persistence errors are caught by production code. A forbidden attempt must be observable to the test gate. Do not claim that the existing Windows pytest-process guard automatically protects Linux or child processes; qualify and test those boundaries explicitly.

## Prerequisites

| Requirement | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|
| Exact saved-plan hash approval | no | Operator | merely unauthorized: required before Task 1; substantive review acceptance does not release execution. |
| Dedicated supplied worktree/branch at the stated base | yes | Claude | Supplied checkout is on the stated branch/HEAD; Task 0 rechecks drift and overlap. |
| Governing spec, ADR-031, foundations and P4 handoff | yes | Claude | Repository inputs exist; P4 qualifies readiness, not K3. |
| Durable production capture, epochs, ledger and upload route | no | Claude | genuinely absent: buildable now in Tasks 1–3. |
| Frozen worktree-local environment | yes | Claude | Claude ran `uv sync --frozen --extra dev` in this worktree on 2026-10-31, exit 0. Record its identities in Task 0; coverage-writer exclusivity is checked per run. |
| CPython 3.14, uv, Git/Bash and psycopg dependency | yes | Operator owns machine state | Supplied machine facts and repository dependency declarations establish availability; record installed identities in Task 0. No `psql` is required. |
| Docker daemon | no | Operator | merely unauthorized: observed stopped on 2026-10-31; operator starts Docker Desktop before live work. |
| Cached Postgres image and isolated run resources | unknown | Operator releases; Claude establishes | genuinely hard: Task 0 inventories image availability and resource isolation before live execution; any download/container requires release. |
| Gateway-only configuration/secret resolution through authorized launch | unknown | Claude; operator owns credentials/authority | genuinely absent: Task 0 maps existing seams; Tasks 1–3 add and qualify the narrow path. No real secret operation is implied by plan approval. |
| Native OS-keyring availability for the K3 credential path | unknown | Operator owns machine state; Claude establishes | genuinely hard: Task 0 inventories backend availability; the released live run must prove the native set/read/delete path without a fake backend. |
| Real alternate-OS focused filesystem/locking checks | unknown | Operator owns environment; Claude establishes | genuinely hard: Task 0 checks WSL/Linux availability before platform-dependent work; use a separate frozen environment. |
| Docker/container/download and real secret-store operations | no | Operator | merely unauthorized: each operation needs its own bounded release, including restart/destruction and run-specific keyring creation/read/deletion. |
| Issue filing, label changes, push, PR, CI publication and merge | no | Operator | merely unauthorized: obtain explicit GitHub/publication authority. |

Every unknown is established in Task 0 before dependent execution. A missing required K3 release leaves acceptance UNRUN and the plan open; readiness evidence or administrative handoff cannot replace it.

## Planned files and inventories

Names below are proposed new files.

| Responsibility | Files |
|---|---|
| Host capture format, lifecycle and delivery | Create `src/optimus/usage/{capture_events,durable_capture,capture_delivery}.py`; extend `turn_settlement.py`, `accounting.py`, `models.py` and `ledger.py` only where required. Keep Postgres imports out of host startup. |
| Shared outbox mechanics | Create `src/optimus_security/durable_outbox.py` for framing, locking, fsync, segment recovery and acknowledgements only; no host accounting types or debit logic. Both processes reuse it without Gateway imports of `optimus.*`. |
| Host callers and wire presence/correlation | `src/optimus/agent/runner.py`, `src/optimus/acp/{spec,auto_hybrid}.py`, `src/optimus/context/maintenance.py`, `src/optimus/gateway/{client,models,attempts}.py`; relevant composition/teardown sites discovered in Task 0. Reuse `post_observability_json()`. |
| Gateway supplemental attempt capture, ingestion and storage | Create `src/optimus_gateway/{usage_capture,usage_store}.py`; modify `server.py`, `responses.py`, `decisions.py`, `chat_completions.py`, `upstream_client.py`, `providers.py`, `models.py` and `__main__.py` only where required. `usage_capture.py` owns Gateway-local strict request/result types and validators, following `observability.py`. |
| Authorized roots/configuration and Gateway secret resolution | Reuse `src/optimus/acp/operator_paths.py`; narrow changes to `launch_gate.py`, `launch_policy.py`, `launch_approval_cli.py`, `local_infra.py` and `src/optimus_security/launch_manifest.py` where required. Add Gateway-only accounting configuration/secret resolution in `usage_store.py`; do not put Postgres secret resolution in the ACP host. |
| Migrations | Create `migrations/optimus_usage/001_durable_capture.sql`. Migration application belongs to `usage_store.py`; immutable successors are new SQL files. |
| New diagnostic sink | Create `src/optimus_gateway/diagnostic_segments.py`; extend `request_diagnostics.py` and Gateway lifecycle composition. |
| Focused tests | Create `tests/unit/usage/test_{outbox,durable_capture,capture_delivery}.py`, `tests/unit/optimus_gateway/test_{usage_capture,usage_store,diagnostic_segments}.py`, and `tests/integration/usage/test_durable_capture_postgres.py`; extend existing settlement, accounting, receipt-ownership, late-receipt, classifier, maintenance, Gateway parsing/retry/server and launch tests. |
| Test-root protection | `tests/conftest.py`, `tools/testing/run_context_guard.py` only as needed, and `tests/unit/tools/test_run_context.py`; temporary-root fixtures and accounting-specific guard/child controls. Preserve root conftest and default guard activation. |
| Live provisioning helper | Create `tests/support/plan12_capture_provisioner.py`: isolated native-secret/container setup, returning nonsecret resource references only. No import-time operations. |
| Live admission/default selection | `pyproject.toml` addopts/markers and `tools/testing/run_context.py` `EXCLUDED_BY_DEFAULT`, changed together; `tests/unit/tools/test_run_context.py` and `tests/profiles.toml`. |
| Establishing-import inventory | `tools/probe_p11_zed_session_load.py` and `tests/unit/tools/test_probe_p11_zed_session_load.py`, **only** for modules entering the establishing-import closure; inspect fresh-process imports. |
| Logging-surface inventory | `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`: register every new file/serialization sink with sanitizer, rationale and test; appended JSON uses `ensure_ascii=True`. |
| Walker/index inventories | `tests/unit/guardrails/test_tracked_file_scanners.py`; use `tools.tracked_repository_files` for repository truth. Every new `ls-files` use gets an `_INDEX_LISTINGS` reason in `tests/unit/tools/test_tracked_repository_files.py`. |
| Child/platform inventories | `tests/unit/tools/run_context_child_sites.json`, `_REVIEWED_CHEAP_LAUNCHERS` in `tests/unit/tools/test_test_profiles.py`, and `tests/profiles.toml` `[parallel]` serial list, following actual launch classification. Every test reading `sys.platform` receives the `platform` tag. |
| Decision, filing and current-state documentation | New ADR and `docs/decisions/README.md`; this plan, `docs/README.md`, ADR-022 issue-only live-plan registry pointer, and affected mutable README/roadmap claims. |
| Evidence and continuity | `reports/plan12-memory-durable-capture/{manifest,requirements,qualification}.json`, per-run records and sanitized report; Claude maintains gitignored, unstaged `docs/superpowers/reviews/plan-12-8-review-checkpoints.md`. |

## Tasks

Use failing focused tests first, minimum implementation, then focused regressions and authorized local commits. Checkbox completion requires the stated verification to have run and passed. No per-task reviewer gate is added.

### Task 0 — Establish source, authority and attainable evidence

- [ ] Recheck branch, HEAD, status, worktree registry, current main drift and overlap. Record frozen-environment identities, launch composition, all callers and every unknown prerequisite above.
- [ ] Confirm HLD/LLD/Test Strategy alignment and record any conflict before dependent work. Recheck ADR allocation and preserve the accepted credential-boundary decision.
- [ ] Read current adjacent-issue criteria and #447’s latest evidence. Establish whether any is a blocker; absorb necessary repair into the owning task here rather than inheriting a predecessor exception or refreshing pins blindly.
- [ ] Prepare the issue **“Plan 12.8 — Memory durable capture (M0b)”**, labels, ADR provenance and registry pointer. Claude files/updates only with operator OK; substitute its assigned issue number in filing references without creating another work register.
- [ ] Inventory disposable Postgres image/resources, native keyring and alternate-OS environment without starting services or reading secrets. Obtain separate releases for each live operation.

**Verification:** read-only source/prerequisite matrix, exact hashes and approved boundaries. No unknown may silently become “yes.”

### Task 1 — Contract, decision and fsynced outbox

**Files:** capture format/outbox, SQL and code-defined request/result schema drafts, ADR, focused outbox tests and applicable inventories.

- [ ] Pin immutable event/receipt fields, replay fingerprints, null/presence semantics, epoch transitions, framing and acknowledgement contract. Record operator words/date/shared source reference separately from agent-selected mechanisms in the ADR.
- [ ] Implement locked append, fsync acknowledgement, segment sealing, verified-prefix recovery, persistent gap records and ledger-bound acknowledgement storage. Use write-through publication where Windows metadata durability requires it; do not import the registry’s documented limitation as an unqualified guarantee.
- [ ] Test real temporary-filesystem operations, concurrent processes, partial frame/header/payload, checksum mismatch, missing segment, failed fsync, disk-full/permission failures, queue overflow, slow writer and timeout races. A killed writer never yields an inferred clean close.
- [ ] Prove acknowledgement-before-deletion ordering, no deletion of unacknowledged/active segments and safe replay after interrupted compaction. Add negative/revert checks for fsync and cursor ordering.
- [ ] Require injected roots, no import/constructor writes and temporary roots throughout tests. Add the default-suite guard control proving no capture sink can create files under the operator’s real accounting root; cover swallowed persistence errors and child-process roots.

**Verify:**

```powershell
uv run --no-sync pytest --no-cov tests/unit/usage/test_outbox.py tests/unit/usage/test_durable_capture.py tests/unit/tools/test_run_context.py -q
```

Run corresponding focused real-filesystem/locking cases on available WSL/Linux in its own environment. These prove their recorded platform behavior, not hardware power-loss survival.

### Checkpoint A — Capture contract and local durability

Codex reviews the ADR, credential boundary, code-defined upload contract, framing/recovery, bounded admission, epoch state model, real-root protection and adversarial controls. Focused evidence suffices. Resolve blockers before dependent integration.

### Task 2 — Extend actual settlement and dispatch paths

**Files:** settlement/accounting models and host/Gateway callers in the files table.

- [ ] Attach durable capture to accepted settlement without replacing in-memory settlement or performing another debit. Preserve `ReceiptConflictError`, provider-ledger conflicts, Redis fingerprint behavior and summarization-only adapter ownership.
- [ ] Wire begin/intent/invocation/terminal/close into ordinary planning, answer, classification and maintenance paths, including failed extraction, preflight refusal, cancellation, worker abandonment and post-teardown arrivals. Engine absence does not disable capture or change ordinary Optimus behavior.
- [ ] Reuse existing received `GatewayRouteAttempt` lists and `_attempts`/`_routed` classification. Keep the Gateway supplemental writer to intent/outcome evidence for lost responses, host death and otherwise hidden physical attempts. Preserve retry decisions, limits, budget checks and unknown-cost classification; do not add a parallel settlement engine.
- [ ] Preserve nullable usage/presence fields and price snapshot; propagate memory purpose without changing ordinary context-summary purpose. Test identical replay, differing arrival bookkeeping, same-request aliases, contradictory facts, unattributed usage and linked late reconciliation.
- [ ] Test persistence unavailable from begin onward and mid-turn: work proceeds, known subtotal survives, coverage stays unknown/incomplete and the next clean epoch does not repair the gap. Sweep dispatch/settlement classes for missing hooks.
- [ ] Verify that supplemental observations and host receipts of the same physical attempt join by identity without double counting; missing route correlation cannot produce complete coverage.

**Verify:**

```powershell
uv run --no-sync pytest --no-cov tests/unit/usage tests/unit/acp/test_ordinary_receipt_accounting.py tests/unit/acp/test_late_receipts.py tests/unit/acp/test_auto_hybrid.py tests/unit/agent/test_receipt_ownership.py tests/unit/agent/test_context_maintenance.py tests/unit/optimus_gateway/test_upstream_retry.py -q
```

Run affected Gateway response/decision/parsing tests and targeted revert checks showing missing intent or accepted-receipt append breaks the owning regression.

### Task 3 — Gateway-owned Postgres drain and committed cursors

**Files:** Gateway ingestion/store, migration, delivery client, authorized configuration and tests.

- [ ] Implement code-defined capture request/result validation, following the trace-ingress authorization/handler/test pattern. Add capture-specific strict fields, body/event limits and bounded framing/read/write handling. Preserve the existing trace route and its delivery semantics.
- [ ] Implement Gateway-only database-secret resolution. Prove wrong/missing authentication, oversized/slow/malformed requests, stream ownership changes and ambient host DSNs cannot cause writes or acquire acknowledgement.
- [ ] Apply isolated, digest-verified migrations and database-enforced immutability. Implement atomic replay/conflict disposition plus cursor advancement, receipt aliases and rebuildable coverage.
- [ ] Wire bounded host upload and Gateway self-drain for supplemental observations. Database outage, missing configuration, migration refusal or unsupported older Gateway leaves outboxes intact and model work available. No recursive capture of capture-upload traffic.
- [ ] Register **`requires_plan12_capture_postgres`** in markers, default exclusion and profiles in lockstep. Tests exercising the native secret path also carry existing **`requires_os_keyring_write`**. Admission controls run before any connection, secret access or child launch.
- [ ] Use one disposable `postgres:16-alpine` instance per live run, with run-labelled container, distinct database/role/volume and inspected loopback mapping. Bind resource identity and ledger instance in the run configuration; never adopt Plan 12.7 or evidence-handoff resources. Missing configuration gives a prerequisite skip before side effects; an explicit protected/invalid target is rejected.
- [ ] Validate the API with the production HTTP client/handler and real Postgres, feeding synthetic accounting envelopes through production settlement. No provider call, fake database or fake Gateway stands in for the named boundary.

**Live-tier password path:**

1. A separately released **provisioner process**, not the ACP host/client process, generates the disposable database password in RAM.
2. It writes the password through the native OS-keyring backend to a unique service such as `optimus.gateway.accounting.k3.<run-id>` and a run-specific account reference. It supplies that same password to Docker through the provisioner’s private child environment, with no password literal in argv, retained environment dumps or raw inspection output.
3. It returns only nonsecret container/volume/port/database/role and keyring-reference metadata. The fixture/client receives no password.
4. The Gateway subprocess receives the temporary trusted config root and approved nonsecret accounting configuration/reference. It calls the **same production Gateway accounting resolver** used by normal composition, which reads the native keyring entry inside that process and constructs its connection information there.
5. The ACP host/client uses only its Gateway URL/key. Test provider credentials are synthetic, and no model route is invoked. Verify that Postgres credentials are absent from host environment, launch arguments, capture data, logs and returned fixture records.

The provisioner’s native keyring write, Gateway read and cleanup deletion are **real secret-store operations requiring their own bounded operator releases**, as do container creation/restart/destruction. Use only the run-specific namespace; never read, overwrite or delete an operator credential. An unavailable native backend or missing release leaves this proof UNRUN; a fake keyring or direct test DSN injection does not qualify it.

**Verify:**

```powershell
uv run --no-sync pytest --no-cov tests/unit/usage/test_capture_delivery.py tests/unit/optimus_gateway/test_usage_capture.py tests/unit/optimus_gateway/test_usage_store.py tests/unit/optimus_gateway/test_server.py tests/unit/tools/test_run_context.py -q
uv run --no-sync pytest --no-cov -m "requires_plan12_capture_postgres and requires_os_keyring_write" tests/integration/usage/test_durable_capture_postgres.py -q
```

The second command requires its separately released run configuration and native-secret operations. Never clear addopts or borrow shared Redis fixtures. Inspect emitted passive/active mode and evidence validity separately.

### Checkpoint B — Integrated accounting and replay

Codex reviews Tasks 2–3, actual caller coverage, minimal supplemental stream, credential isolation, native-secret path, real transaction/replay evidence, migration/immutability controls and default-selection protection. Re-estimate remaining work. No full suite is scheduled here.

### Task 4 — Diagnostic copy and complete K3 proof

**Files:** diagnostic sink/lifecycle, focused tests, live tests and evidence.

- [ ] Implement exact sink ownership, ordered concurrent writes, flush/close, day/size rollover, 30-day/256-MiB retention and failure visibility. Test threshold boundaries, UTC transitions, restart, malformed/oversized records, unavailable storage, blocked writers, deletion failure and independent stderr failure. Verify old workspace/Q27 paths and Stage C behavior remain unchanged.
- [ ] Complete real-Postgres K3 cases: unavailable before dispatch; outage during drain; rollback/constraint/statement failure; concurrent drains; lost commit response; restart of the same container/volume; replay after process death; and durable readback using a new connection.
- [ ] Kill the real outbox writer at framing/flush boundaries and restart through production recovery. Test death before commit, after commit/before local acknowledgement, and after acknowledgement/before compaction. Assert immutable row identities, exact row counts/costs, committed cursor and retained gap/epoch state.
- [ ] Demonstrate pending growth/warnings during outage and catch-up after recovery without deleting pending facts or changing model outcomes. A later complete epoch must coexist with the earlier incomplete one.
- [ ] Run class sweeps and focused revert checks for each money/durability claim. Repair genuine blockers here, retain failed attempts and complete applicable repository inventories.
- [ ] Confirm every test sink and child uses temporary roots and the default-suite real-root control remains effective after production composition is wired.

**Verify:**

```powershell
uv run --no-sync pytest --no-cov tests/unit/optimus_gateway/test_diagnostic_segments.py tests/unit/optimus_gateway/test_correction_diagnostics.py tests/unit/optimus_gateway/test_failure_diagnostics.py tests/unit/usage -q
uv run --no-sync pytest --no-cov -m "requires_plan12_capture_postgres and requires_os_keyring_write" tests/integration/usage/test_durable_capture_postgres.py -q
```

Real filesystem/process/Postgres evidence is required. Synthetic receipt values establish capture semantics, not provider billing correctness.

### Task 5 — Final verification, filing and closure

- [ ] Finish focused fixes, inventories and current-state documentation audit before freezing the final code head. Audit README, roadmap, docs/decision indexes, transitional registry and linked issues, including summary claims not touched by the implementer.
- [ ] Run exactly one Windows full suite with coverage from PowerShell on that final code head, validate coverage and run Ruff using the commands below. Retain the real-root protection result.
- [ ] Obtain Checkpoint C’s consolidated Codex review; resolve findings with focused checks and disclose the exact tested-source/fix delta.
- [ ] Under separate operator authority, publish the PR with the plan, ADR, code-defined upload schema/tests, evidence, docs index and ADR-022 issue-only registry pointer. Use `Refs #<assigned Plan 12.8 issue>`.
- [ ] Inspect Linux PR CI at its actual SHA and repeat the documentation audit before merge. Investigate platform-shaped failures with focused real alternate-OS reproduction, not review alone.
- [ ] After authorized merge and acceptance of required evidence/CI, deliberately close the Plan 12.8 issue and remove its `status:` label. Archive the terminal plan byte-for-byte, repair mutable references and update `docs/README.md` in the authorized closure change. Do not rewrite frozen ADRs/evidence or infer cleanup authority.

## Verification and checkpoints

Claude owns the operator chat and checkpoint log. Codex reviews through:

```bash
codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"' -s read-only
```

Specify model/effort on every invocation, including resumes; report model failure without substitution. Under approved GitHub writes, Claude posts reviews verbatim to the owning issue with the required reviewer/model/effort/session heading.

**Checkpoint C — Final K3 and release review:** review Tasks 4–5, Windows final evidence, complete requirement-to-evidence mapping, diagnostics, real-root protection, inventories and remaining limitations. Linux PR CI is the subsequent publication gate. Codex’s acceptance counts as the operator’s **review verdict**, not permission for live operations, GitHub writes, push, PR or merge. Fable is optional at Claude’s judgment for genuinely complex points; no mandatory Fable-first or per-task reviews apply.

Authorized local commits skip only `optimus-pytest-coverage`; every other applicable hook runs.

Before the final freeze, run applicable inventory and filing checks:

```powershell
uv run --no-sync pytest --no-cov tests/unit/tools/test_verify_plan996_logging_surfaces.py tests/unit/guardrails/test_tracked_file_scanners.py tests/unit/tools/test_tracked_repository_files.py tests/unit/tools/test_run_context_child_sites.py tests/unit/tools/test_test_profiles.py tests/unit/tools/test_probe_p11_zed_session_load.py -q
uv run --no-sync pytest --no-cov tests/unit/docs/test_docs_index.py tests/unit/docs/test_plan_directory_hygiene.py tests/unit/docs/test_open_work_pool_hygiene.py -q
```

Run the final Windows full suite and validation once:

```powershell
uv run --no-sync python tools/check_product_coverage.py --run-full-suite --groups tools/product-coverage-groups.json --report-json tmp/coverage/product-coverage-report.json --coverage-json tmp/coverage/coverage.json
uv run --no-sync python -m tools.testing.coverage_products validate --coverage-json tmp/coverage/coverage.json --gate-report tmp/coverage/product-coverage-report.json
uv run --no-sync ruff check .
```

Require canonical product floors, at least **80% aggregate Python production coverage** and no safety-critical regression. Linux PR CI is the second full run; dedicated Postgres/native-secret proof remains separately required even when default CI excludes it.

A code change after the Windows run invalidates attribution to the final code head. Preserve that run, disclose the delta and obtain operator disposition before another full run or acceptance of changed bytes. Never rerun silently, relabel older evidence or hide baseline failures.

## Definition of Done and named evidence

All paths below are required outputs under `reports/plan12-memory-durable-capture/`, not existing results.

| Claim | Named evidence and required real boundary |
|---|---|
| Local durable append and truthful crash recovery | `outbox-recovery.json`: real filesystem/fsync and killed writer processes, verified prefixes, failure/timeout races and platform qualifications. |
| Existing settlement extended without another debit | `settlement-extension.json`: caller/class sweep, existing route-list reuse, supplemental-evidence joins, replay/conflict matrix, exact subtotals and targeted revert checks through production settlement. |
| Credential rule preserved | `credential-boundary.json`: accepted ADR reference, authorized configuration/launch tests, provisioner-to-native-keyring-to-Gateway path, host credential-denial controls and real capture HTTP using only Gateway URL/key on the client. |
| Immutable receipts, atomic cursors and safe compaction | `postgres-k3.json`: real isolated Postgres identities, migrations, independent readback, concurrent replay, rollback, lost acknowledgement and commit/deletion crash windows. |
| Coverage remains honest across outage/restart | `coverage-epochs.json`: durable begin/intents/terminal/close, pending/unknown cases, missing route evidence, failed begin, interrupted tail and a later clean epoch leaving the earlier gap intact. |
| Exact diagnostic ownership/retention | `diagnostic-retention.json`: production sink on real temporary files, exact size/date/cap boundaries, retained ranges, flush/lifecycle and failure observations; unchanged existing-path controls. |
| Tests cannot create operator accounting data | `test-root-isolation.json`: temporary-root composition/child checks and default-suite protection proving no creations under the real accounting root, with explicit platform/guard qualifications. |
| Regression, coverage and delivery gates | `qualification.json`: focused/revert/class-sweep results, inventory checks, Windows final coverage/Ruff, Linux CI SHA/results and all three checkpoint verdicts. |

K3 cannot pass with a mocked Postgres, fake secret backend, P4 readiness result, default-suite skip or accepted handoff. No claim of live-provider billing completeness, hardware power-loss survival or a generally “working Phase 1 agent” follows from this plan.

## Evidence discipline

Record absolute checkout, branch, source HEAD/tree or provisional dirty-diff digest, exact command, run ID, platform/interpreter/environment, configuration/dependency/migration identities, stdout/stderr, exit status and HEAD/status before and after each reviewed run. Preserve root conftest, selection, mode/reason, guard/native validity and record completeness.

Use each worktree’s own frozen environment. **Verify coverage-writer exclusivity before every coverage-producing run**; it is a per-run admission check, not a planning prerequisite. Keep Windows and WSL/Linux environments and evidence separate.

Every test uses temporary roots. Default runs perform no native secret-store operation. Live runs use only their released run-specific secret namespace and temporary config root; subprocess protection is established explicitly, not inferred from the pytest parent’s guard.

Each live container/run requires explicit configuration binding its released image/container/database/role/port/volume, credential reference and lifecycle operations. Never touch protected `optimus-redis`, another lane’s database or shared evidence-handoff resources. Filter inspected Docker metadata before retention; do not capture secret-bearing environment arrays.

Preserve failures, skips with node IDs/reasons, UNKNOWN, UNRUN and invalid/incomplete records. Passing tests and valid acceptance evidence are separate requirements. Archive/hash required records before temporary retention can prune them.

Serialize JSON with `ensure_ascii=True`; render digests as **`hex:<digest>`**. Publish sanitized repository-visible manifests and summaries, never credentials, raw content or private-workstation dependencies. The manifest records the full approved plan/spec hashes and each artifact digest.

## Issue assessment and closure

Propose `priority:high`, `handler:claude`, **`difficulty:high`**, **`estimate:8d`**; Claude/Codex agreement is recorded, and operator approval precedes label writes.

- **Difficulty:** crash-consistent cross-process capture, existing replay semantics, authorized Gateway configuration and commit-bound compaction must agree under failure.
- **Estimate:** eight working days covers the production extension, real-boundary failure matrix and three coarse reviews using existing drivers/patterns; approval waits are excluded. Re-estimate at checkpoints, especially if a blocking issue is absorbed.

Closure requires all task verification, three accepted checkpoints, valid K3/native-secret evidence, final Windows coverage/Ruff, Linux PR CI and the documentation audit. Issue closure, `status:` removal, plan archival and resource cleanup retain their separate operator authority.

Paid model calls and Q27 changes remain outside this plan. Prolonged outages can exhaust disk; capture must expose that loss of coverage while model work continues.