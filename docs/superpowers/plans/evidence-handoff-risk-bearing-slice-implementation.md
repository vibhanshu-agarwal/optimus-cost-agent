# EVIDENCE-HANDOFF-FEAT-A2A-LEDGER Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to execute this plan task by task. Steps use
> checkbox syntax for tracking.

**Goal:** Implement the risk-bearing vertical slice of EVIDENCE-HANDOFF-FEAT-A2A-LEDGER as a
default-off, local-first PostgreSQL-backed handoff ledger with authenticated MCP Streamable HTTP,
fail-closed redaction, chained integrity, reader-confirmed delivery, and real three-agent evidence.

**Architecture:** This artifact is one product-owned contract containing three ordered subplans,
not one undifferentiated implementation batch. Subplan A establishes lifecycle, migrations,
immutable entries, continuous verification, durable integrity state, and recovery against real
PostgreSQL. Subplan B adds the real Streamable HTTP service, authentication/session controls,
server-derived identity and authority, and the in-memory redaction ingress. Subplan C adds
recipient visibility, delivery/cursor mechanics, capability activation, delivery observability,
and real Claude Code/Codex/Cursor evidence. Each subplan produces independently reviewable
working software and its own real dependency evidence; later subplans consume earlier contracts
but are not the first proof of them.

**Tech Stack:** Python 3.14, the evidence_handoff portable package, a separate
evidence_handoff_runtime service/lifecycle package, PostgreSQL in wslc bound to 127.0.0.1,
the repository-pinned mcp Streamable HTTP implementation and official MCP client, a direct
PostgreSQL driver resolved by uv, optimus_security as the only redaction rule engine,
pytest/pytest-asyncio/pytest-cov, coverage.py, Ruff, detect-secrets, Windows process and ACL
primitives, and real Claude Code, Codex, and Cursor clients with distinct instance credentials.

**Frozen design baseline:** origin/main at 7a5a4af4cb67ccc7dbf14e93a3f2b6c8acb264c2, file
docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md, committed-blob SHA-256
b792b80f66acb79f8521df2eeb7944445dcbd34fcb2b959f2f8751d18b75eaff. The implementation worker
must verify the committed blob at pickup. A mismatch blocks pickup; the design is not edited from
this plan.

## Global Constraints

- The authoritative scope is exactly the design's Risk-bearing vertical slice heading. Do not
  implement Ledger protocol completion, Evidence bridge, or Operations and extraction.
- EVIDENCE-HANDOFF-FEAT-A2A-LEDGER is the only scheduling identity. Scheduling is assigned at
  pickup; do not reserve or invent a plan number, feature number, migration number, schema name,
  container name, service name, CLI name, or artifact name containing a scheduling number.
- Product package, module, configuration, schema, artifact, service, container, and CLI names are
  descriptive, brand-free, and number-free. Do not edit the Optimus local-infrastructure module.
- evidence_handoff must not import optimus, optimus_gateway, their subpackages, project tools, ACP
  launch types, or Gateway service types. It may consume optimus_security and must not fork its
  redaction engine. A static AST boundary test is mandatory.
- Keep PostgreSQL/MCP/process wiring in evidence_handoff_runtime (or an identically descriptive
  runtime package selected at pickup) so portable evidence_handoff remains free of database and
  service-framework imports. The runtime package is also forbidden from importing optimus,
  optimus_gateway, project tools, ACP launch types, and Gateway service types.
- The portable package exposes no approval/mutation callback, approval-shaped result, host mutation
  import, or adapter that turns authority, review-ruling, operator-relay, or acknowledgement into
  authorization. Ledger output is untrusted input.
- The feature toggle defaults to disabled. Disabled means no implicit PostgreSQL or MCP startup,
  no indefinite client retries, no projected ledger credential, and explicit operator relay as the
  active route. Integrity failure is never silently degraded to relay.
- The lifecycle manager alone may start, stop, initialize, migrate, health-check, quarantine,
  recover, or activate the service/store. Service handlers receive only a least-privileged
  application database credential; they never receive container rights or database-admin
  credentials.
- The first store backend is real PostgreSQL in wslc, bound and forwarded only on 127.0.0.1.
  Docker and native-Windows fallback paths are outside this slice. SQLite, Redis, remote/shared
  MCP, and implicit backend switching are not permitted.
- Use TDD for every production behavior: write the failing test, run it and record RED output,
  implement the minimum behavior, run the same test GREEN, then refactor while preserving the
  contract. A checkbox is complete only after its named command passes.
- Unit doubles may isolate pure deterministic functions, but a wiring boundary must exercise the
  real object on both sides. Do not create a fake MCP client, fake service process, fake redaction
  supplier, fake PostgreSQL protocol, or fake named agent as live evidence.
- Windows is the mandatory verification platform. WSL2 is CI-parity evidence only and cannot
  replace Windows evidence. Every task that first introduces a real dependency records its
  dependency identity and content-free result in the ignored review checkpoint.
- All rejection tests prove absence after an induced failure: no redaction on pre-policy rejection,
  no sequence allocation on rejection, no row after failed sanitization or transaction, no cursor
  movement on failed reads/confirmations, and no unredacted canary in PostgreSQL, logs, errors, or
  MCP responses.
- Runtime redaction inputs are populated from the immutable lifecycle/bootstrap context. An empty
  known-secret inventory when configured values exist is a readiness failure, never a successful
  redaction path. The current request credential is added only to an ephemeral per-request
  inventory.
- Six v1 entry kinds exist in the schema, but this slice activates and exposes only review-ruling;
  question, answer, evidence-notice, handoff, and acknowledgement remain inactive until the later
  protocol-completion chunk.
- Every append uses server-derived principal_id, agent_id, caller_role, and authority. Client-
  supplied server-owned fields, non-null attestation, empty/duplicate/unknown recipients, and
  unsupported schemas fail before redaction and sequence assignment.
- Every successful append is sanitized, deterministically serialized, chained, and committed with
  its counter update in one PostgreSQL transaction. sequence is the sole total-order authority.
  Timestamps never order, paginate, resolve conflicts, or advance cursors.
- Integrity failure is a distinguished non-retryable ledger_integrity_failed class with causes
  sequence_duplicate, sequence_gap, chain_break, counter_head_mismatch, rollback_divergence, and
  ledger_instance_mismatch. It durably latches outside the canonical ledger chain, survives
  restart, stops normal operations, and requires an explicit human recovery decision.
- Chain recovery never repairs or copies an untrusted tail. A replacement instance is linked to
  the last independently verified sequence and digest, starts after that anchor, and is explicitly
  activated only after recovery verification.
- Real integration evidence is distributed through the tasks that introduce each capability. A
  final gate may index earlier artifacts but may not be the first exercise of PostgreSQL, the
  service process, the official MCP client, redaction, or any named agent.
- Before each implementation commit, run the task's narrow tests, uv run --frozen ruff check .,
  and git diff --check; obtain operator approval for that task's commit. Do not merge. The
  implementation branch may be pushed and a PR opened only after this plan's own release gates.
- The reviewer-owned checkpoint is
  docs/superpowers/reviews/evidence-handoff-a2a-ledger-review-checkpoints.md; it is ignored,
  must be read on pickup, must record current state and each gate's evidence, and must never be
  staged.

## File and Boundary Map

The following paths are the planned ownership map. Private helpers may be split inside these
areas, but a responsibility may not cross the portable/runtime boundary without a reviewed plan
amendment.

| Area | Planned paths | Responsibility |
|---|---|---|
| Portable ledger contracts | src/evidence_handoff/ledger/ | Closed drafts, six-kind/schema identifiers, immutable envelope, canonical serialization, SHA-256 chain fields, result/error vocabulary, and delivery-token value objects. No PostgreSQL, MCP, subprocess, or host imports. |
| Portable ingress | src/evidence_handoff/redaction/ingress.py and existing redaction public models | Primitive typed structured-entry validation, in-memory sanitization through optimus_security, deterministic serialization, final scan, closed sanitized result, and content-free rule counts. No disk staging. |
| Runtime configuration/lifecycle | src/evidence_handoff_runtime/config.py, inputs.py, control_state.py, lifecycle.py, lifecycle_cli.py, process.py, backends.py | Default-off behavior, immutable bootstrap context, populated runtime-input supply, lifecycle lock, wslc process/store startup, readiness, stop/status, external integrity latch, quarantine, and explicit recovery activation. |
| Runtime persistence | src/evidence_handoff_runtime/store.py, migrations.py, migrations/evidence_handoff/ | Real PostgreSQL, immutable migration digests, instance/counter/entry/control/capability/cursor/token/audit tables, serialized append, verified scans, CAS confirmation, and recovery metadata. |
| Runtime service | src/evidence_handoff_runtime/service.py, transport.py, auth.py, sessions.py, policy.py, audit.py, service_cli.py | MCP Streamable HTTP, loopback/Origin/DNS-rebinding checks, audience-bound credentials, session replay controls, principal mapping, role policy, bounded requests, and MCP tool wiring. |
| Evidence tooling | tools/verify_evidence_handoff_live.py and tools/evidence_handoff_live_support/ | Evidence-only coordination and manifest verification. It may not emulate MCP, PostgreSQL, or an agent. |
| Tests | tests/unit/evidence_handoff/, tests/integration/evidence_handoff/, tests/e2e/evidence_handoff/, tests/fixtures/evidence_handoff/ | Pure contracts, AST/hygiene regressions, real Windows PostgreSQL/service process, official MCP client, and real named-agent evidence. |
| Metadata | pyproject.toml, uv.lock, .gitignore only if required | Direct PostgreSQL dependency, descriptive entry points/markers, lock data, and ignored local evidence roots. No Optimus package wiring. |

## Ordered Subplan A: Persistence, Lifecycle, Integrity, and Recovery

Subplan A is independently useful: it initializes an enabled/disabled local store, runs real
migrations, accepts direct store contract tests, detects induced corruption, and produces
content-free recovery status without any MCP client. Its real evidence is Windows wslc plus real
PostgreSQL, including restart and induced-failure recovery.

### Task 0: Pickup preflight and frozen contract verification

Files:
- Read AGENTS.md, CONTRIBUTING.md, the design, the product pool, and the ignored checkpoint when present.
- Modify tests/unit/docs/test_open_work_pool_hygiene.py only if the new plan path is not represented.

Interfaces:
- Consumes origin/main 7a5a4af4cb67ccc7dbf14e93a3f2b6c8acb264c2 and the committed design blob.
- Produces a pickup record containing the design commit/digest, official MCP/A2A artifact URLs and
  content digests actually consumed, clean-tree status, Windows dependency versions, and approval
  state. No production behavior changes are allowed.

- [ ] Step 1: Write the failing pickup-boundary/hygiene test.

Extend the document guard so the product-owned allowlist contains this plan path and the plan
contains the feature ID, three ordered subplan headings, frozen design path, explicit exclusion of
the other three delivery chunks, and no scheduling-plan token. Assert the portable boundary is
evidence_handoff and the runtime boundary is not an Optimus package.

- [ ] Step 2: Run RED and record it.

~~~
uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
~~~

Expected: FAIL only because the new plan path is not yet in the allowlist/assertions. An unrelated
failure blocks pickup.

- [ ] Step 3: Perform the read-only preflight.

~~~
git status -sb
git merge-base --is-ancestor 7a5a4af4cb67ccc7dbf14e93a3f2b6c8acb264c2 HEAD
git show -s --format="%H %s" origin/main
git show origin/main:docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md | Select-String "### Risk-bearing vertical slice"
uv --version
uv run --frozen python --version
~~~

Expected: clean branch, ancestor check exit 0, origin/main at 7a5a4af4cb67ccc7dbf14e93a3f2b6c8acb264c2,
Python 3.14, and no source file changed. Record the committed design SHA-256; do not use a
working-tree digest as a substitute.

- [ ] Step 4: Stop for pickup approval.

Relay the preflight record and wait for approval before Task 1. This approval is not approval to
implement or commit later tasks.

### Task 1: Freeze default-off configuration and populated redaction runtime inputs

Files:
- Create src/evidence_handoff_runtime/config.py, inputs.py, control_state.py.
- Create tests/unit/evidence_handoff/test_runtime_inputs.py and test_default_off.py.
- Modify src/evidence_handoff/redaction/ingress.py and tests/unit/evidence/test_import_boundaries.py.
- Modify pyproject.toml only for descriptive runtime entry points/markers if required.

Interfaces:
- FeatureConfig.from_mapping(values: Mapping[str, str]) -> FeatureConfig, with enabled=False when
  absent; Availability.DISABLED, Availability.UNAVAILABLE, and Availability.INTEGRITY_FAILED; and
  LifecycleBootstrapContext containing resolved secrets, identity values, path aliases, roots,
  allowed origins, enrollment, and capabilities without serializing secrets.
- RuntimeInputSupplier(startup: LifecycleBootstrapContext) exposes startup_inputs() and
  request_inputs(credential: str), returning immutable snapshots; request_inputs retains no credential.
- StructuredIngress.sanitize(draft: EntryDraft, inputs: RequestRedactionInputs) -> SanitizedDraft,
  with deterministic bytes/digest/rule counts only, or a stable content-free rejection.

- [ ] Step 1: Write RED tests for disabled behavior and non-empty inventory readiness.

Cover absent toggle disables the feature; disabled lifecycle does not start a process or project a
credential; disabled status names operator relay rather than transport failure; enabled configuration
with an empty configured-secret/identity inventory fails readiness; populated exact secret, PII,
path-alias, temporary/staging/quarantine, and forbidden-root values reach the real
RedactionRuntimeInputs; the request credential is ephemeral; and no input value appears in repr,
audit, or exception text.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_runtime_inputs.py tests/unit/evidence_handoff/test_default_off.py -q
~~~

Expected RED: runtime package/ingress contract is absent or assertions fail. Preserve the output.

- [ ] Step 2: Implement the minimum immutable bootstrap/input path.

Use explicit resolved arguments from lifecycle. Do not reread env files, query a keyring, inspect
Optimus configuration, enumerate processes, or derive fingerprints from secret values. Reuse the
existing RedactionRuntimeInputs and optimus_security.sanitization types. Empty configured inventory
is a readiness failure.

- [ ] Step 3: Run unit, boundary, and canary checks.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_runtime_inputs.py tests/unit/evidence_handoff/test_default_off.py tests/unit/evidence/test_import_boundaries.py -q
uv run --frozen ruff check src/evidence_handoff src/evidence_handoff_runtime tests/unit/evidence_handoff tests/unit/evidence/test_import_boundaries.py
git diff --check
~~~

Expected: selected tests pass, AST has no forbidden/dynamic import, and diff check is clean.

- [ ] Step 4: Stop for review and approval.

Relay RED/GREEN output, input provenance, and absence scan. Commit only after approval:
feat: freeze evidence handoff runtime inputs.

### Task 2: Add lifecycle locking and real PostgreSQL-in-wslc startup

Files:
- Create src/evidence_handoff_runtime/lifecycle.py, backends.py, process.py, lifecycle_cli.py.
- Create tests/unit/evidence_handoff/test_lifecycle.py and
  tests/integration/evidence_handoff/test_wslc_lifecycle.py.
- Modify pyproject.toml, uv.lock, and .gitignore only for the direct PostgreSQL driver,
  descriptive entry points/markers, lock data, and explicitly named local evidence roots.

Interfaces:
- LifecycleManager(config: FeatureConfig, bootstrap: LifecycleBootstrapContext) exposes start(),
  stop(), status(), initialize(), migrate(), and health(), all idempotent and serialized by one
  restrictive lifecycle lock.
- StoreBackend has backend_id == wslc, bind_host == 127.0.0.1, explicit readiness/persistence
  checks, and no fallback in this slice. Admin credentials remain lifecycle-owned.
- Descriptive commands evidence-handoff-lifecycle and evidence-handoff-service may be added. Neither
  uses an Optimus name or implicit start.

- [ ] Step 1: Write RED lifecycle tests.

Test disabled start, concurrent serialization, enabled start, loopback-only argv, no 0.0.0.0,
no credential projection, stop/status, unavailable classification, and refusal to switch backend
while running. Exercise the real lifecycle object at the process boundary; a narrow spawn seam
may assert argv before the live test.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_lifecycle.py -q
~~~

Expected RED: lifecycle/backend/command is absent.

- [ ] Step 2: Implement lifecycle and the wslc adapter.

Use immutable bootstrap context, restrictive lock, atomic content-free status, fixed shell=False
argv, and loopback probes. Start PostgreSQL/service only after enabled, input, migration, principal,
and schema preflight succeeds. Report disabled, unavailable, or integrity_failed distinctly.

- [ ] Step 3: Run RED-to-GREEN and real Windows wslc evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_lifecycle.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_wslc_lifecycle.py -m requires_evidence_handoff_postgres -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: unit/live tests pass on Windows. Artifact identifies the real PostgreSQL version,
wslc distribution/process, 127.0.0.1 listener, readiness, restart persistence, instance identity,
and cleanup. A skipped or mocked PostgreSQL test is not evidence.

- [ ] Step 4: Stop for backend review and approval.

Relay live wslc artifact and lifecycle output. Commit only after approval:
feat: add loopback lifecycle management.

### Task 3: Add migrations, immutable envelope v1, review-ruling activation, and transactional ordering

Files:
- Create src/evidence_handoff/ledger/__init__.py, models.py, canonical.py, errors.py.
- Create src/evidence_handoff_runtime/store.py and migrations.py.
- Create descriptive migrations under migrations/evidence_handoff/.
- Create tests/unit/evidence_handoff/test_ledger_models.py, test_canonical_hashing.py,
  test_migration_manifest.py, and tests/integration/evidence_handoff/test_postgres_store.py.
- Modify tests/unit/evidence/test_import_boundaries.py.

Interfaces:
- EntryKind contains all six design values; SchemaId, EntryDraft, ImmutableEntryEnvelope, SanitizedDraft,
  AppendResult, VerifiedRange, and IntegrityWitness are frozen/slotted portable values. Only
  review-ruling is active in the first-slice writer capability.
- canonical_json(value: Mapping[str, object]) -> bytes uses deterministic UTF-8 JSON with sorted keys
  and fixed separators. content_sha256 covers sequence, instance, predecessor, recipients, message,
  artifacts, identity mapping, schema, and all fields except content_sha256.
- PostgresLedgerStore.append(sanitized, identity, idempotency_key) -> AppendResult,
  read_verified_global_range(start, watermark) -> VerifiedRange, verify_full() -> IntegrityWitness,
  and current_status() -> StoreStatus.
- Tables include immutable instance metadata, singleton counter, entries with sequence UNIQUE NOT
  NULL CHECK sequence > 0, recipient arrays, schema/kind, server identity, nullable-only attestation,
  content/audit/control/capability/cursor/token data. Migrations never rewrite canonical bodies.

- [ ] Step 1: Write RED model, canonical, migration, and real-PostgreSQL tests.

Cover closed schemas and bounded Message/Part data; absent server-owned draft fields; all six kinds;
non-null attestation; explicit duplicate-free recipients; malformed SHA-256; deterministic
serialization; digest sensitivity to sequence/instance/predecessor; migration digest immutability;
real constraints; first-entry null predecessor; ordinary counter/head; same-key idempotency;
conflicting retry; concurrent appends; rollback of row and counter; and zero committed gaps.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_ledger_models.py tests/unit/evidence_handoff/test_canonical_hashing.py tests/unit/evidence_handoff/test_migration_manifest.py tests/integration/evidence_handoff/test_postgres_store.py -q
~~~

Expected RED: contracts/migrations/store are absent. The live test must fail for missing real
PostgreSQL rather than pass through an in-memory substitute.

- [ ] Step 2: Implement portable contracts and real store.

Validate primitive input before database calls. One transaction locks the counter, verifies instance
and head, assigns last_committed + 1, computes the chained digest, inserts, advances counter/head,
and commits. Database locking, not an in-process mutex, preserves correctness. Keep future kinds
physical but inactive; do not add their operational writers.

- [ ] Step 3: Run real PostgreSQL ordering evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_ledger_models.py tests/unit/evidence_handoff/test_canonical_hashing.py tests/unit/evidence_handoff/test_migration_manifest.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_postgres_store.py -m requires_evidence_handoff_postgres -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real migrations, one instance identity, contiguous sequences, equal counter/head digest,
rollback/idempotency/concurrency results, and no fake/SQLite evidence.

- [ ] Step 4: Stop for persistence review and approval.

Relay schema/migration digests and transaction evidence. Commit only after approval:
feat: add immutable evidence handoff ledger storage.

### Task 4: Add continuous integrity state, full audits, and linked chain-break recovery

Files:
- Modify src/evidence_handoff_runtime/store.py, control_state.py, lifecycle.py.
- Create src/evidence_handoff_runtime/integrity.py and recovery.py.
- Create tests/unit/evidence_handoff/test_integrity.py, test_recovery.py, and
  tests/integration/evidence_handoff/test_integrity_recovery.py.

Interfaces:
- IntegrityCause, IntegrityIncident, IntegrityStatus, and IntegrityLatch contain only incident ID,
  cause, instance ID, safe boundary, time, and disposition. IntegrityMonitor.verify_readiness(),
  verify_full(), and verify_unfiltered_range(reader_cursor, watermark, anchor) return content-free
  results or latch ledger_integrity_failed.
- RecoveryManager.quarantine(instance_id), find_last_verified_anchor(instance_id), and
  activate_linked_replacement(incident, anchor) are explicit. clear_false_positive is allowed only
  after repeated full verification plus all available external witnesses; genuine corruption cannot
  clear in place.

- [ ] Step 1: Write RED induced-failure tests.

Use real PostgreSQL rows/control state to induce and detect duplicate sequence, missing global
sequence, broken predecessor/content digest, counter/head mismatch, instance mismatch, witness
ahead of restored head, and rollback witness conflict. After each failure assert stable cause,
non-retryable class, durable latch, stopped normal operations, no automatic relay, and content-free
status. Restart the real process and assert persistence.

Recovery must quarantine the predecessor read-only, select only the last verified anchor, preserve
tail rows without copying/calling them repaired, reject automatic clearing, create a linked
replacement with the anchor sequence/digest, verify the link, and require explicit activation.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_integrity.py tests/unit/evidence_handoff/test_recovery.py tests/integration/evidence_handoff/test_integrity_recovery.py -q
~~~

Expected RED: induced corruption cannot yet be classified, latched, or recovered.

- [ ] Step 2: Implement verification, latch, quarantine, and recovery.

Readiness verifies genesis/recovery anchor through the complete head. Normal global scans verify
unfiltered positions before recipient filtering. Persist the external latch with restrictive
permissions and atomic replacement; fail closed if it cannot persist; mirror control metadata where
possible. Preserve predecessor permanent status after replacement activation.

- [ ] Step 3: Run real induced-failure/restart evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_integrity.py tests/unit/evidence_handoff/test_recovery.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_integrity_recovery.py -m requires_evidence_handoff_postgres -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real corruption, restart, quarantine, witness conflict, and linked replacement artifacts
exist. Untrusted tail content is never emitted as final/repaired/copied content and no relay/retry
clears the incident.

- [ ] Step 4: Stop for integrity/recovery review and approval.

Relay every induced-failure class and recovery lineage. Commit only after approval:
feat: add latched integrity recovery.

## Ordered Subplan B: Streamable HTTP Service, Identity, Security, and Redaction

Subplan B is independently useful: it starts the real service against Subplan A's real store,
drives it with the official MCP client, and proves pre-redaction rejection and authentication/session
properties. It adds no future protocol kind or evidence collection tool.

### Task 5: Add loopback Streamable HTTP transport and protocol service

Files:
- Create src/evidence_handoff_runtime/service.py, transport.py, service_cli.py.
- Create tests/unit/evidence_handoff/test_transport.py and
  tests/integration/evidence_handoff/test_service_process.py.
- Modify pyproject.toml for direct service entry point/markers if required.

Interfaces:
- ServiceConfig(bind_host, bind_port, allowed_origins, request_limits, protocol_versions) validates
  loopback-only settings.
- LedgerService.start(config, store, bootstrap) -> RunningService; RunningService exposes endpoint,
  wait_ready(), and stop(). The live implementation is a real process under the lifecycle manager.
- MCP exposes only capabilities/status, review-ruling append/read, delivery read/confirm/status,
  and integrity/recovery status. It never exposes collection, process launch, window capture,
  approval, or mutation.

- [ ] Step 1: Write RED transport and real-process tests.

Cover loopback bind, host/DNS-rebinding rejection, exact Origin allowlist, absent Origin only for
native authenticated clients, unsupported protocol, request limits before parsing, no legacy HTTP+SSE
fallback, and tool-surface exclusion. The integration test uses official
mcp.client.streamable_http.streamable_http_client and mcp.ClientSession directly; no project client
or fake transport.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_transport.py tests/integration/evidence_handoff/test_service_process.py -q
~~~

Expected RED: service/transport or real process fixture is absent.

- [ ] Step 2: Implement real Streamable HTTP and MCP tool wiring.

Use the repository-pinned MCP implementation, exact origins, loopback host, bounded request/response
work, and content-free errors. Authorization/session checks run before MCP parsing. Client tokens
never reach PostgreSQL.

- [ ] Step 3: Run real service-process evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_transport.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_service_process.py -m requires_evidence_handoff_service -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real service subprocess reaches ready against real wslc PostgreSQL; official MCP client
initializes, negotiates the pinned protocol, discovers only allowed tools, and exercises transport
negatives. Skips or project-authored client evidence is not a pass.

- [ ] Step 4: Stop for protocol review and approval.

Relay service process identity, MCP client/library identity, negotiated version, tool surface, and
request-boundary artifact. Commit only after approval:
feat: serve the ledger over streamable http.

### Task 6: Add audience-bound credentials, session binding, principal mapping, and role policy

Files:
- Create src/evidence_handoff_runtime/auth.py, sessions.py, policy.py.
- Create tests/unit/evidence_handoff/test_auth.py, test_sessions.py, test_policy.py, and
  tests/integration/evidence_handoff/test_authenticated_service.py.
- Modify src/evidence_handoff_runtime/service.py and store.py.

Interfaces:
- CredentialClaims(principal_id, agent_id, caller_role, issuer, audience, scope, expires_at,
  token_id), CredentialIssuer.issue(instance_id, enrollment) -> str, and
  CredentialValidator.validate(header, request) -> AuthenticatedPrincipal. Validate issuer, audience,
  expiry, scope, token status, signature, and instance binding; token values never enter logs/rows.
- SessionRegistry.create(principal, protocol_version) -> SessionBinding, validate(session_id,
  principal), and expire(session_id). IDs are random and never credentials.
- PolicyDecision derives agent_id, caller_role, and authority. Reviewer principals alone append
  review-ruling; implementers reject before redaction/sequence. Client authority/caller_role/agent_id
  and non-null attestation are closed-schema rejections.

- [ ] Step 1: Write RED auth/session/role tests.

Cover malformed/expired/wrong-audience/wrong-issuer/wrong-scope/revoked/replayed tokens,
session-as-credential rejection, session expiry, protocol binding, principal mismatch, invalid
Origin before parsing, reviewer success, implementer rejection, client field rejection, and unchanged
counter/head after every rejection. Assert the real ingress boundary is not invoked for pre-policy
rejection.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_auth.py tests/unit/evidence_handoff/test_sessions.py tests/unit/evidence_handoff/test_policy.py tests/integration/evidence_handoff/test_authenticated_service.py -q
~~~

Expected RED: validator/session/policy behavior or negative assertions are absent.

- [ ] Step 2: Implement credentials, sessions, and policy.

Use a signed audience-bound short-lived credential with constant-time signature comparison and
server-side enrollment/revocation. Store only token IDs/hashes and content-free claims. Create
sessions only after authentication and check every request. Derive authority; never accept or
overwrite client authority.

- [ ] Step 3: Run real authenticated service evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_auth.py tests/unit/evidence_handoff/test_sessions.py tests/unit/evidence_handoff/test_policy.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_authenticated_service.py -m requires_evidence_handoff_service -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real tokens/sessions/service requests show reviewer success and implementer/field
rejection with no sequence change. Artifact contains no token or entry body.

- [ ] Step 4: Stop for security review and approval.

Relay the negative-property matrix and content-free authentication audit. Commit only after approval:
feat: enforce ledger identity and role policy.

### Task 7: Add in-memory structured redaction ingress and review-ruling append/read

Files:
- Modify src/evidence_handoff/redaction/ingress.py, redaction/__init__.py,
  src/evidence_handoff_runtime/service.py, policy.py, store.py, audit.py.
- Create tests/unit/evidence/test_structured_ingress.py, tests/unit/evidence_handoff/test_review_ruling.py,
  and tests/integration/evidence_handoff/test_redaction_service.py.

Interfaces:
- StructuredIngress.sanitize accepts only a primitive typed EntryDraft, validates bounded message
  parts/structured values and artifact metadata, sanitizes through the populated shared rule engine,
  serializes deterministically, performs final exact/pattern/entropy/path scans, and reparses into
  SanitizedDraft. It returns content-free counts or a stable failure.
- PostgresLedgerStore.append is called only after policy and ingress success. Redaction/final-scan/
  serialization/input/transaction failure leaves entries and counter unchanged.
- review-ruling is append/read only; response contains immutable entry ID, sequence, instance ID,
  and content digest, never secrets or raw exception text.

- [ ] Step 1: Write RED redaction and no-row/no-sequence tests.

Use populated exact-secret, PII, path-alias, split/encoded-secret, entropy, and request-credential
canaries. Cover deterministic output, sanitized response, final-scan rejection, malformed input,
empty inventory, induced rollback, and row/counter scan after each failure. Assert failed writes
leave no unredacted row, raw body, error/MCP canary, or sequence. Add reviewer success, implementer
rejection, client authority rejection, unknown recipient rejection, and non-null attestation rejection
against real service/store objects.

~~~
uv run --frozen pytest tests/unit/evidence/test_structured_ingress.py tests/unit/evidence_handoff/test_review_ruling.py tests/integration/evidence_handoff/test_redaction_service.py -q
~~~

Expected RED: structured ingress/review-ruling wiring is absent or permits persistence after failure.

- [ ] Step 2: Implement fail-closed ingress and append/read.

Do not stage the draft or unredacted entry on disk. Keep only sanitized typed result and content-free
counts in memory. Use real RuntimeInputSupplier, StructuredIngress, PostgresLedgerStore, and service
policy at the integration boundary. Audit only kind, schema, digest, counts, identity IDs, sequence,
and stable failure code.

- [ ] Step 3: Run real redaction canary/failure evidence.

~~~
uv run --frozen pytest tests/unit/evidence/test_structured_ingress.py tests/unit/evidence_handoff/test_review_ruling.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_redaction_service.py -m requires_evidence_handoff_service -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real PostgreSQL contains only sanitized data; presented/configured canaries are absent
from rows, logs, errors, and MCP responses after successful/failed writes. Rejections leave counter
and head unchanged.

- [ ] Step 4: Stop for redaction/policy review and approval.

Relay raw-canary scan, no-row/no-sequence matrix, reviewer/implementer evidence, and audit summary.
Commit only after approval:
feat: add fail-closed review ruling ingress.

## Ordered Subplan C: Recipient Delivery, Capabilities, Observability, and Three-Agent Evidence

Subplan C is independently useful: it proves reader-confirmed at-least-once delivery and factual
per-agent state, then drives the same real service from distinct Claude Code, Codex, and Cursor
configurations. It adds no wakeup, evidence collection, or future entry-kind writers.

### Task 8: Add frozen recipient visibility, verified global reads, delivery tokens, and cursors

Files:
- Modify src/evidence_handoff_runtime/store.py, service.py, and src/evidence_handoff/ledger/models.py.
- Create src/evidence_handoff_runtime/delivery.py.
- Create tests/unit/evidence_handoff/test_delivery.py and
  tests/integration/evidence_handoff/test_delivery_service.py.

Interfaces:
- DeliveryToken binds principal, instance, previous cursor/witness, watermark, resulting witness,
  visible entry IDs, and page digest; it is short-lived, single-use, and cannot cross boundaries.
- read_entries(principal, cursor, supported_schemas) -> DeliveryPage and
  confirm_delivery(token) -> CursorStatus. Scan/verify the unfiltered range before recipient
  filtering; confirmation uses CAS and advances past non-visible positions only after validation.
- Recipient validation rejects empty, duplicate, unknown, retired, wildcard, role-alias, and
  context-alias recipients before redaction/sequence. Visibility is exactly stable agent membership;
  no sender copy, broadcast, expansion, or retroactive change.

- [ ] Step 1: Write RED cursor/delivery/visibility tests.

Cover explicit recipients, no broadcast, immutable membership, visible gaps, no-visible watermarks,
unread count, lost-confirmation redelivery, invalid/expired/replayed/mismatched token, concurrent CAS
conflict, unsupported visible schema with unchanged cursor, global gap/chain/instance/witness failure
with no page/token/cursor, and rollback witness ahead of current head. Assert hidden commitments,
existence, and counts are never disclosed.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_delivery.py tests/integration/evidence_handoff/test_delivery_service.py -q
~~~

Expected RED: token/cursor/visibility semantics are absent.

- [ ] Step 2: Implement verified read and confirmation.

Use one snapshot watermark, verify every global position and chain boundary from the confirmed
cursor anchor before applying the recipient predicate, and return no page/token on failure. Persist
cursor sequence/time/witness atomically after valid confirmation. Never infer delivery from HTTP.

- [ ] Step 3: Run real delivery evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_delivery.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_delivery_service.py -m requires_evidence_handoff_service -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real service/PostgreSQL show at-least-once redelivery, one successful CAS confirmation,
unchanged cursor on failures, correct unread count, safe hidden-position advance, and no disclosure.

- [ ] Step 4: Stop for delivery review and approval.

Relay token fields, cursor/witness transitions, visibility matrix, and induced-failure artifacts.
Commit only after approval:
feat: add reader-confirmed ledger delivery.

### Task 9: Add reader capabilities, coordinated schema activation, and delivery observability

Files:
- Modify src/evidence_handoff_runtime/store.py, lifecycle.py, service.py, and audit.py.
- Create src/evidence_handoff_runtime/capabilities.py and observability.py.
- Create tests/unit/evidence_handoff/test_capabilities.py and
  tests/integration/evidence_handoff/test_capability_activation.py.

Interfaces:
- ReaderCapability(agent_id, principal_id, supported_schemas, reported_at, retired) and
  CapabilityCoordinator.preflight_activation(schema_id) -> ActivationBlockers,
  activate_writer(schema_id) -> ActivationStatus, and retire_principal(principal_id) ->
  AdministrativeAuditResult.
- DeliveryView reports asserted agent ID/status, cursor/last-confirmed time, visible unread count,
  last authenticated request, last acknowledgement fact if present, capability freshness/block, and
  global integrity incident/cause/boundary plus warning delivery fact. It never guesses liveness.
- Unknown visible schema returns whole-query unsupported_entry_schema with no token/cursor. Activation
  refuses stale/missing non-retired readers; retirement is explicit administrative state.

- [ ] Step 1: Write RED capability/view tests.

Cover reader-first activation, stale blockers, explicit retirement, per-query unsupported schema,
projection rebuildability, factual delivery view, warning delivered versus not-yet-requested, and
absence of online/dead/healthy claims.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_capabilities.py tests/integration/evidence_handoff/test_capability_activation.py -q
~~~

Expected RED: capability/view behavior is absent.

- [ ] Step 2: Implement capability/activation and facts.

Record asserted capabilities against principals, use lifecycle preflight, and expose facts only.
Keep projections rebuildable and non-authoritative for canonical entry content.

- [ ] Step 3: Run real activation/view evidence.

~~~
uv run --frozen pytest tests/unit/evidence_handoff/test_capabilities.py -q
uv run --frozen pytest tests/integration/evidence_handoff/test_capability_activation.py -m requires_evidence_handoff_service -q
uv run --frozen ruff check .
git diff --check
~~~

Expected: real service/store refuses activation with stale readers, accepts after all active readers
report support, returns whole-query schema failures, and emits content-free factual rows.

- [ ] Step 4: Stop for capability/observability review and approval.

Relay blocker/retirement transitions and delivery-view output. Commit only after approval:
feat: coordinate reader capabilities and delivery facts.

### Task 10: Prove real Claude Code, Codex, and Cursor configurations and next-interaction warnings

Files:
- Create tools/verify_evidence_handoff_live.py and tools/evidence_handoff_live_support/.
- Create tests/unit/tools/test_verify_evidence_handoff_live.py,
  tests/e2e/evidence_handoff/test_three_agent_live.py, and
  tests/fixtures/evidence_handoff/three_agent_scenario.json.
- Modify .gitignore only for explicitly named local credentials/config/evidence roots.

Interfaces:
- The live verifier accepts explicit absolute service/evidence roots and expected agent IDs; it does
  not launch an agent through a project-authored fake, emulate MCP, or create credentials. It verifies
  a content-free manifest containing real client names/versions, distinct principal/agent IDs,
  service/store identities, request/entry/delivery digests, and safe outcomes.
- Real MCP configurations use distinct instance-bound credentials and the service endpoint; the
  operator runs native Claude Code, Codex, and Cursor clients. Claude and Cursor may be reviewers;
  Codex is implementer so rejection is observable.
- The scenario proves reviewer append succeeds, explicit recipient delivery reaches other agents,
  implementer review-ruling append is rejected with unchanged sequence/counter, client authority is
  rejected, each client confirms a real page, and after an induced latch each agent's next
  authenticated interaction emits ledger_integrity_failed without automatic relay.

- [ ] Step 1: Write RED verifier/live-contract tests.

Reject missing/implicit roots, duplicate credentials, non-distinct agents, missing manifest fields,
fabricated dependency identities, tokens in manifests, and evidence lacking real client/process/store
identity. A skipped agent or mocked service cannot be marked passed.

~~~
uv run --frozen pytest tests/unit/tools/test_verify_evidence_handoff_live.py tests/e2e/evidence_handoff/test_three_agent_live.py -q
~~~

Expected RED: verifier/scenario is absent. The e2e test remains a real-dependency test and cannot
be made green by a project-authored agent harness.

- [ ] Step 2: Implement evidence-only manifest verification and native-client configuration.

Use explicit CLI arguments, shell=False when process inspection is unavoidable, safe digest/identity
fields only, and raw-canary scanning across PostgreSQL, service logs, audit output, temporary/
quarantine roots, errors, and MCP responses. Native agent settings are supplied by the operator; the
verifier records, but does not synthesize, results.

- [ ] Step 3: Run real three-agent Windows evidence.

The operator provisions three distinct credentials and configures the real clients. Then run the
service/lifecycle process and verifier with explicit roots:

~~~
uv run --frozen pytest tests/e2e/evidence_handoff/test_three_agent_live.py -m requires_real_agents -q
uv run --frozen python tools/verify_evidence_handoff_live.py verify --evidence-root C:\evidence-handoff-live\run --service-endpoint http://127.0.0.1:PORT/mcp
~~~

The operator replaces the approved explicit root and port at pickup; the verifier must reject missing
values rather than choose defaults. Expected: real Claude Code, Codex, and Cursor identities,
distinct server-mapped principals, shared append/read/delivery, implementer rejection with no
sequence allocation, and one warning from each agent on its next post-latch interaction. A skipped
agent, fake client, simulated warning, or project-authored ACP/MCP driver is not a pass.

- [ ] Step 4: Run raw-canary and manifest audit.

~~~
uv run --frozen python tools/verify_evidence_handoff_live.py inspect --evidence-root C:\evidence-handoff-live\run
uv run --frozen ruff check .
git diff --check
~~~

Expected: manifests/digests are content-free, zero canaries occur in PostgreSQL, logs, audit,
temporary/quarantine roots, errors, or MCP responses, and no credential value is reported.

- [ ] Step 5: Stop for named-agent evidence review and approval.

Relay manifest, commands, client/process versions, service/store identities, digest table, negative
matrix, and raw-canary result. Commit only after approval:
test: prove cross-agent ledger delivery.

## Repository Release Gates and Handoff

### Task 11: Run complete gates, freshness audit, and prepare the draft implementation handoff

Files:
- Read all changed source/test/config/migration/tool files and the current-state documents.
- Read the product pool, frozen design, README.md, phase-1 roadmap, and every document whose claims
  change.
- Modify only plan checkboxes, ignored checkpoint, and pool status after named gates/approval.

Interfaces:
- Produces a claim-to-evidence bundle, not runtime behavior. Every completion claim names a real
  artifact, dependency identity, command, result, digest, and reviewer ruling.

- [ ] Step 1: Run Windows test and quality gates.

~~~
uv run --frozen pytest tests/unit/evidence tests/unit/evidence_handoff tests/unit/docs/test_open_work_pool_hygiene.py tests/unit/tools/test_verify_evidence_handoff_live.py -q
uv run --frozen pytest tests/integration/evidence_handoff -q
uv run --frozen pytest --cov=src/optimus --cov=src/optimus_gateway --cov=src/optimus_security --cov=src/evidence_handoff --cov=src/evidence_handoff_runtime --cov-report=term-missing --cov-report=xml --cov-fail-under=80
uv run --frozen ruff check .
uv run --frozen detect-secrets-hook --baseline .secrets.baseline src tools
uv lock --check
git diff --check
~~~

Expected: selected tests pass, production coverage is at least 80%, Ruff/secrets/lock/whitespace
checks are clean. Named live markers are not satisfied by skipped defaults; cite earlier artifacts.

- [ ] Step 2: Run WSL2 parity without replacing Windows evidence.

~~~
uv sync --frozen --extra dev
uv run --frozen pytest tests/unit/evidence_handoff tests/integration/evidence_handoff -q
~~~

Expected: portable, migration, and PostgreSQL protocol behavior passes in WSL2. Windows remains
mandatory for wslc, loopback, lifecycle, path, ACL, and named-agent claims.

- [ ] Step 3: Run static boundary and package checks.

~~~
uv run --frozen pytest tests/unit/evidence/test_import_boundaries.py tests/unit/evidence/test_naming_boundaries.py tests/unit/docs/test_open_work_pool_hygiene.py -q
uv build
git status --short
~~~

Expected: AST rejects all forbidden Optimus/tools/ACP/Gateway roots and dynamic imports, names contain
no feature/scheduling coupling, wheel contains the portable/runtime packages, and only approved files
changed.

- [ ] Step 4: Audit documentation freshness and custody.

Confirm that the pool links this plan, allowlist and hygiene test agree exactly, current-state rows
do not claim unmerged work is closed, the design remains frozen, README/roadmap claims are current,
and no deferred follow-up is unowned. Do not mark the feature closed merely because this plan is
green; retain any real evidence blocker in the pool with an owning roadmap entry.

- [ ] Step 5: Produce the final review bundle and stop before merge.

Update the ignored checkpoint with exact commits, design digest, every command/result, coverage,
Ruff/secret/lock/package/boundary results, Windows and WSL identities, real PostgreSQL/service/MCP
client/Claude Code/Codex/Cursor identities, canary scan, integrity/recovery artifacts, and reviewer
rulings. After operator approval, push the implementation branch and open a PR against main. The
operator, not the implementing agent, merges it.

## Definition of Done

- [ ] Disabled configuration produces no implicit service/store startup, credential projection, or
  indefinite retry, and reports operator relay as the active route.
- [ ] Real Windows wslc PostgreSQL lifecycle is loopback-only, idempotent, persisted across restart,
  migrated by descriptive immutable migrations, and operated only by the lifecycle manager.
- [ ] Immutable envelope v1, six physical entry kinds, activated review-ruling, server-owned fields,
  nullable-only attestation, deterministic digest, transactional counter, and unique positive
  sequence constraints are proven against real PostgreSQL.
- [ ] Readiness, append, and unfiltered global-range verification detect every specified integrity
  cause; latching is restart-durable, non-retryable, content-free, and never silently relays.
- [ ] Induced chain break, counter/head disagreement, rollback witness conflict, and instance
  mismatch produce real quarantine/recovery evidence; untrusted tails are never repaired/copied.
- [ ] Real Streamable HTTP evidence proves exact Origin/DNS-rebinding/authentication/session/replay
  controls with the official independent MCP client.
- [ ] Real principal mapping proves reviewer success, implementer rejection, client authority
  rejection, no redaction on pre-policy rejection, no unredacted row after failures, and no sequence
  allocation on rejection.
- [ ] Populated runtime redaction inputs and in-memory structured ingress use the shared rule engine;
  canaries are absent from PostgreSQL, logs, errors, responses, temporary roots, and manifests.
- [ ] Explicit immutable recipient visibility, safe non-visible watermarks, verified global reads,
  delivery tokens, reader confirmation, unread counts, CAS conflicts, and factual delivery views
  are proven against real service/store objects.
- [ ] Reader-first capability activation and per-query unsupported-schema failure are proven; no
  partial page or cursor movement occurs.
- [ ] Real Claude Code, Codex, and Cursor configurations use distinct credentials and prove shared
  append/read/delivery, implementer rejection, and next-interaction integrity warnings.
- [ ] Aggregate production coverage is at least 80%; unit/integration/live gates, Ruff, secrets,
  lock, package, static boundary, diff, Windows, and WSL checks are green, with skipped named
  dependencies reported as blockers rather than passes.
- [ ] Product pool, plan allowlist, design, README, roadmap, and current-state documents are fresh;
  the draft PR targets main; no merge has occurred.

## Review Handoff

Claude reviews this plan against the committed design digest and product pool before implementation
pickup. The operator approves each task independently. A task approval authorizes only that task's
implementation/commit request; it does not authorize the next task, remote push, PR creation, or
merge.
