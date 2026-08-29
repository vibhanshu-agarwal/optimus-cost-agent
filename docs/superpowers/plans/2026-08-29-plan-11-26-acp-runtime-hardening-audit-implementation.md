# Plan 11.26 ACP Runtime Hardening Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft awaiting independent review and explicit execution authorization.

**Goal:** Produce a baseline-scoped, machine-checkable audit of ACP runtime cross-cutting contracts and evidence-backed remediation candidates without changing production runtime behavior.

**Architecture:** A non-production `tools.plan1126_runtime_audit` package supplies one shared artifact schema, baseline vocabulary, AST inventory framework, running-artifact provenance verifier, seed corpus, checkpoint protocol, and computed-cost model. Concern-specific tests and probes use that common approach to characterize delivery, task ownership, cancellation, resource lifetime, semantic error selection, telemetry, queues, and optional durable-session behavior; findings are recorded rather than repaired. Live rows use real named dependencies only after fresh authorization, while overlay-dependent claims remain Plan 11.7-owned scope-outs until a binding integration candidate exists.

**Tech Stack:** Python 3.14, uv 0.11.29, pytest/pytest-asyncio, Ruff, Python AST, JSON/NDJSON, Git blob reads, live TimeSeries-capable Redis when authorized, independently authored acpx 0.12.0, official `@agentclientprotocol/sdk` stable-v1 API with Node v26.5.0/npm 11.17.0, official Java ACP SDK fallback with Java 25.0.3 LTS/Maven 3.9.6, and real Zed 1.17.2 only under a separate live grant.

**Spec:** `docs/superpowers/specs/2026-08-29-plan-11-26-acp-runtime-hardening-audit-design.md`

## Global Constraints

- Plan 11.26 is audit-and-contract work only. Do not change any file under `src/`; production remediation receives a later linear Plan 11 number after separate review.
- Begin execution only after an independent reviewer approves this complete plan and the operator explicitly authorizes execution. Plan authoring approval is not execution approval.
- The merged audit baseline is `main@5ea8f8f71548eb05a8562a10e98667e3d2061c4d`; the provisional runtime overlay contains `fac32284888850bacde93815265cbabe3afd4663`; Plan 11.7 alone nominates the future binding integration candidate.
- Only `merged`, `both-aligned`, and later `binding` rows may produce binding findings. `overlay` and `both-divergent` rows remain provisional.
- Preserve Plan 11.18 authority: `src/optimus/acp/errors.py` remains the sole production owner of JSON-RPC, ACP, and Optimus error-code values, protected by `tests/unit/acp/test_error_code_registry.py`.
- Preserve the settled delivery vocabulary: `SendState`, `SendOutcome`, `Settlement`, `FinalDelivery`, `RpcResponseDelivery`, `ConversationCommit`, and `EffectState`.
- Preserve `ACP_TURN_SETTLEMENT` as the worked telemetry standard: exact content-free payload keys, enum-backed vocabulary, strict missing/extra-field rejection, redaction, and contained sink delivery.
- `acpx` remains the independently authored ACP integration/live driver required by `AGENTS.md`; the official TypeScript SDK, same-task Java fallback, or independently authored conformance-harness fallback is additional comparison evidence and never a substitute.
- Client behavior is never the oracle: record divergence rather than investigate it during this audit, name each finding's subject as Optimus, client/harness, observer/tooling, environment, or inconclusive, and retain mandatory acpx authority regardless of SDK agreement or disagreement.
- A project-authored ACP client or conformance harness cannot satisfy an ACP protocol integration or live-evidence row. The project-authored fixture agent in Task 3 exists only to qualify the independently authored comparison mechanism.
- Workspace `git_sha` is not installed running-artifact provenance. Every live row must independently bind executable/package bytes to the binding commit or be marked `INVALID`.
- Derive inventories and matrix multipliers mechanically. A hand-maintained complete-site list cannot satisfy an inventory gate.
- Audit reviewer-facing comments/docstrings with the same baseline-scoped inventory: require invariant, ownership, ordering, and intentional-exception rationale where behavior is non-obvious, but record missing/contradictory documentation as findings rather than editing production prose.
- Keep literal frozen regression seeds independent of commit-derived seeds. Never regenerate the frozen corpus solely because the binding commit changes.
- Derive the ownership lease from `SESSION_LOAD_LEASE_SECONDS` on the applicable tree and session retention from `DEFAULT_ACP_SESSION_TTL_SECONDS`; never substitute one for the other.
- Live Zed, acpx, SDK-client, Redis mutation, Gateway/model, paid-call, evidence-promotion, push, merge, and release actions each require fresh explicit authorization at their own gate.
- Checkpoint every repeated batch atomically. An interrupted batch resumes at the next unexecuted iteration; it never discards or cherry-picks completed results.
- A completed characterization run may end `PASS_WITH_FINDINGS`. Only malformed, provenance-invalid, or incomplete evidence makes the audit mechanism fail.
- Do not edit frozen plans, approval records, evidence seals, custody records, release reports, or historical reviews. Stale historical path text remains evidence.
- `docs/superpowers/reviews/plan-11-26-review-checkpoints.md` is reviewer-owned, gitignored handoff state. Read it on pickup and never stage it.
- Before every commit, run the task's narrow checks, `uv run --frozen ruff check .`, and `git diff --check`. Commit only with explicit operator authorization.

## File Map

| Path | Responsibility |
|---|---|
| `tools/plan1126_runtime_audit/__init__.py` | Stable exports for the non-production audit package. |
| `tools/plan1126_runtime_audit/model.py` | Closed baseline, classification, live-status, gate-status, finding, and artifact types plus strict JSON validation. |
| `tools/plan1126_runtime_audit/source.py` | Read-only source views for a worktree or immutable Git commit without checking out another branch. |
| `tools/plan1126_runtime_audit/inventory.py` | Shared AST/token inventory framework for runtime sites, duplicate logic, and invariant comments/docstrings. |
| `tools/plan1126_runtime_audit/provenance.py` | External build/install manifest and installed-artifact verification; rejects workspace-only provenance. |
| `tools/plan1126_runtime_audit/checkpoints.py` | Atomic iteration records, resume cursor, and duplicate/conflict rejection. |
| `tools/plan1126_runtime_audit/corpus.py` | Literal frozen-seed loading plus commit-derived seed calculation. |
| `tools/plan1126_runtime_audit/cost.py` | Discovered multipliers, exact run-count formulas, and measured p50/p95 wall-time estimates. |
| `tools/plan1126_runtime_audit/repeatability.py` | Stable outcome fingerprints and `STABLE`/`FLAKY`/`HARNESS_INVALID` classification across repeated runs. |
| `tools/plan1126_runtime_audit/clients.py` | Qualification and provenance checks for acpx, official TypeScript/Java clients, and an independently authored conformance-harness fallback; never implements ACP framing. |
| `tools/plan1126_runtime_audit/render.py` | Deterministic content-free Markdown rendering from the canonical JSON artifact. |
| `tools/run_plan1126_runtime_audit.py` | Thin CLI for static inventory, offline characterization, live gated rows, checkpoint resume, and final rendering. |
| `tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json` | Versioned closed schema used independently of Python dataclasses. |
| `tests/fixtures/plan1126_runtime_audit/frozen-regression-seeds.json` | Literal reviewed regression schedules, unchanged by binding-commit changes. |
| `tests/fixtures/plan1126_runtime_audit/fixture_agent.py` | Minimal non-production fixture agent used only to qualify the independently authored comparison mechanism in Task 3. |
| `tests/fixtures/plan1126_runtime_audit/typescript-client/` | Exact-lock official stable-v1 TypeScript SDK qualifier (`package.json`, `package-lock.json`, `tsconfig.json`, `src/client.ts`). |
| `tests/fixtures/plan1126_runtime_audit/java-client/` | Exact-version official Java SDK fallback qualifier (`pom.xml`, `src/main/java/.../QualificationClient.java`). |
| `tests/unit/tools/plan1126_runtime_audit/` | Unit tests for schema, source views, inventories, provenance, checkpoints, corpus, cost, repeatability, clients, and rendering. |
| `tests/unit/acp/test_plan1126_delivery_contract.py` | Delivery-site AST coverage and 1,000-seed settlement characterization. |
| `tests/unit/acp/test_plan1126_cancellation.py` | Derived cancellation-point schedule characterization. |
| `tests/unit/acp/test_plan1126_shutdown.py` | Five terminal causes, 100 repeats, idempotent-close counts, and control-derived growth allowlist. |
| `tests/unit/acp/test_plan1126_queue_policy.py` | Queue construction/admission cross-check and bounded 10,000-attempt probes. |
| `tests/unit/acp/test_plan1126_session_lease.py` | Binding-code lease/retention separation and derived boundary schedules. |
| `tests/unit/acp/test_plan1126_semantic_errors.py` | Exhaustive semantic-outcome-to-wire selection inventory while preserving Plan 11.18. |
| `tests/unit/telemetry/test_plan1126_runtime_contract.py` | Derived runtime event vocabulary, redaction, correlation, and sink-failure containment. |
| `tests/integration/acp/test_plan1126_runtime_live_redis.py` | Real TimeSeries-capable Redis owner/revision and health characterization. |
| `tests/e2e/acp/test_plan1126_clients_live.py` | Real process rows driven by acpx or the qualified comparison client/harness, plus validation of the manual Zed observation bundle; no project ACP client. |
| `reports/plan-11-26-baseline-intake.json` | Exact merged/overlay/binding refs, reconciliation state, and H1-H8 baseline scopes accepted at G0. |
| `reports/plan-11-26-prerequisite-intake.json` | Sanitized prerequisite decisions, authority state, and named scope-outs. |
| `reports/plan-11-26-acp-runtime-audit.json` | Canonical machine-readable audit artifact. |
| `reports/plan-11-26-acp-runtime-audit.md` | Deterministic reviewer-facing rendering of the JSON artifact. |
| `reports/plan-11-26-client-qualification.json` | Exact client package/commit, build, fixture-run, and fallback decision evidence. |
| `reports/plan-11-26-zed-manual-observations.json` | Five closed-vocabulary operator observations bound to Zed and installed Optimus artifact provenance. |
| `reports/plan-11-26-terminal-characterization.md` | Per-tier commands, costs, statuses, checkpoints, invalid reasons, and authorized live results. |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Sole live registry for Plan 11.26 status, owner, reviewed disposition, and later remediation gates. |
| `tests/unit/docs/test_open_work_pool_hygiene.py` | Locks Plan 11.26 live-registry and backlog custody language. |

## Explicit Exceptions and Custody

| Excluded work | Named owner |
|---|---|
| Plan 11.7 branch reconciliation, Task 0 evidence, formal evidence, and closure | `P11-FEAT-ZED-RESUME` |
| Launch/trust and durable-approval policy correctness outside lifecycle interfaces | Existing Plan 9.96/11.15 authority; any newly observed obligation enters the canonical backlog before Plan 11.26 disposition. |
| Credential acquisition or rotation beyond ownership and redaction interfaces | `EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE` where applicable; otherwise a named canonical-backlog owner before deferral. |
| Gateway and agent reasoning/business semantics | Their existing canonical backlog feature owners; Plan 11.26 inspects only ACP-facing lifecycle interfaces. |
| Production fixes for findings | Later independently numbered Plan 11 remediation candidates after review. |
| Release, push, merge, evidence promotion, and working-agent sign-off | Existing release governance and archived Plan 9.6 sign-off authority. |

## Prerequisites

The table below carries the approved design table forward with the reviewer-mandated C3 correction: acpx `0.12.0` was established by review-time command output, not operator narration. Header, lowercase status vocabulary, ownership, dispositions, and every other row remain unchanged.

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
| tooling/binaries | acpx `0.12.0` launcher and version were established by review-time command output; the version must be re-recorded by the execution environment. | yes | operator | merely unauthorized — not applicable while satisfied |
| tooling/binaries | Zed `1.17.2` (`c8e44cfa7bda9b2e22c8d6934d78969352e7f61a`) is installed at `C:\Users\pc\AppData\Local\Programs\Zed\Zed.exe`. | yes | operator | merely unauthorized — not applicable while satisfied |
| platforms | Windows execution environment is present. | yes | operator | merely unauthorized — not applicable while satisfied |
| platforms | WSL2 environment and distro-native Redis/TimeSeries availability are established. | unknown | operator | genuinely hard — establish in early Task 1 before WSL-dependent evidence |
| services | Windows live Redis/TimeSeries availability, port ownership, and isolation are established. | unknown | operator | merely unauthorized — establish in early Task 1 before live-Redis evidence |
| credentials/authority | Optimus Gateway credentials and paid-call authority are available for any live prompt scenario. | unknown | operator | merely unauthorized — establish capability only in early Task 1; do not print or persist secrets |
| credentials/authority | Fresh authorization exists for Zed, acpx, additional client, Redis mutation, Gateway/model calls, and paid calls. | no | operator | merely unauthorized — live tasks remain dormant until granted |
| human interaction | Trusted Zed workspace and operator availability for five GUI runs are established. | unknown | operator | merely unauthorized — establish in early Task 1 before scheduling Zed evidence |
| cost/time | Paid-call budget and the authorized wall-clock lease-expiry window are accepted. | no | operator | merely unauthorized — derive duration from binding code and authorize before live scheduling |
| evidence/tooling | Installed running-artifact provenance can be proved independently of workspace `git_sha`. | no | Plan 11.26 Task 2 | genuinely absent — build the external manifest/verifier before any live row can be valid |

Every `unknown` prerequisite is resolved by Task 1 or Task 3 before a dependent task. Binding, overlay-dependent, lease, and live-resume evidence remains explicitly scoped out with Plan 11.7 as owner until it nominates the binding integration candidate. The prerequisite hygiene command in Task 0 must run against this plan artifact.

## Planned Predicate Map

| Predicate | Exact file | Exact command |
|---|---|---|
| `test_audit_artifact_requires_baseline_scope_and_classification` | `tests/unit/tools/plan1126_runtime_audit/test_artifact.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_artifact.py::test_audit_artifact_requires_baseline_scope_and_classification -q` |
| `test_audit_artifact_live_status_is_machine_checkable` | `tests/unit/tools/plan1126_runtime_audit/test_artifact.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_artifact.py::test_audit_artifact_live_status_is_machine_checkable -q` |
| `test_running_artifact_provenance_matches_binding_commit` | `tests/unit/tools/plan1126_runtime_audit/test_provenance.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_provenance.py::test_running_artifact_provenance_matches_binding_commit -q` |
| `test_derived_inventory_has_no_unclassified_sites` | `tests/unit/tools/plan1126_runtime_audit/test_inventory.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_inventory.py::test_derived_inventory_has_no_unclassified_sites -q` |
| `test_delivery_contract_ast_covers_all_send_sites` | `tests/unit/acp/test_plan1126_delivery_contract.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_ast_covers_all_send_sites -q` |
| `test_delivery_contract_model_1000_seed_schedule` | `tests/unit/acp/test_plan1126_delivery_contract.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule -q` |
| `test_turn_cancellation_races_256_seed_matrix` | `tests/unit/acp/test_plan1126_cancellation.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_turn_cancellation_races_256_seed_matrix -q` |
| `test_shutdown_causes_repeat_100_with_control_allowlist` | `tests/unit/acp/test_plan1126_shutdown.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist -q` |
| `test_close_is_idempotent_across_discovered_paths` | `tests/unit/acp/test_plan1126_shutdown.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_close_is_idempotent_across_discovered_paths -q` |
| `test_queue_policy_cross_checks_constructor_and_10000_admissions` | `tests/unit/acp/test_plan1126_queue_policy.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_queue_policy.py::test_queue_policy_cross_checks_constructor_and_10000_admissions -q` |
| `test_session_lease_boundary_uses_binding_runtime_constant` | `tests/unit/acp/test_plan1126_session_lease.py` | `uv run --frozen pytest tests/unit/acp/test_plan1126_session_lease.py::test_session_lease_boundary_uses_binding_runtime_constant -q` |
| `test_live_redis_owner_revision_races` | `tests/integration/acp/test_plan1126_runtime_live_redis.py` | `uv run --frozen pytest tests/integration/acp/test_plan1126_runtime_live_redis.py::test_live_redis_owner_revision_races -m requires_redis -v` |
| `test_runtime_event_schema_generated_10000_cases` | `tests/unit/telemetry/test_plan1126_runtime_contract.py` | `uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_event_schema_generated_10000_cases -q` |
| `test_runtime_redaction_generated_1000_cases` | `tests/unit/telemetry/test_plan1126_runtime_contract.py` | `uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_redaction_generated_1000_cases -q` |
| `test_runtime_correlation_chain_is_complete` | `tests/unit/telemetry/test_plan1126_runtime_contract.py` | `uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_correlation_chain_is_complete -q` |
| `test_telemetry_sink_failures_are_contained` | `tests/unit/telemetry/test_plan1126_runtime_contract.py` | `uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_telemetry_sink_failures_are_contained -q` |
| `test_regression_corpus_replays_frozen_literal_seeds` | `tests/unit/tools/plan1126_runtime_audit/test_corpus.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_corpus.py::test_regression_corpus_replays_frozen_literal_seeds -q` |
| `test_computed_cost_includes_cancellation_queue_sink_and_close_multipliers` | `tests/unit/tools/plan1126_runtime_audit/test_cost.py` | `uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_cost.py::test_computed_cost_includes_cancellation_queue_sink_and_close_multipliers -q` |
| `test_zed_manual_observation_bundle_is_complete` | `tests/e2e/acp/test_plan1126_clients_live.py` | `uv run --frozen pytest tests/e2e/acp/test_plan1126_clients_live.py::test_zed_manual_observation_bundle_is_complete -m "e2e and requires_zed" -v` |

The first 18 rows are the approved design predicates for the audit mechanism. The 19th supplemental row gates the Task 11 manual Zed observation bundle. A predicate passes when the scheduled behavior is exhaustively observed and truthfully classified; it does not force the current runtime to exhibit a desired future behavior.

---

### Task 0: Claim canonical custody and pin the review intake

**Files:**

- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md`
- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Create: `reports/plan-11-26-baseline-intake.json`
- Read only: `docs/superpowers/reviews/plan-11-26-review-checkpoints.md`

**Interfaces:**

- Consumes: explicit execution authorization; clean branch `agent/codex/plan-11-26-acp-runtime-hardening-audit`; approved spec commit `d4ac57887df3bcf078cdceebea68143120679cda`; checkpoint rulings C1-C3.
- Produces: canonical `Active` Plan 11.26 registry custody and a sanitized baseline record containing `merged_commit`, `overlay_commit`, `binding_commit`, `baseline_reconciliation_status`, and per-hypothesis scope.

- [x] **Step 1: Verify approval, checkpoint, branch, and immutable baseline facts.**

  Read the checkpoint Current State first. Then run:

  ```powershell
  git status --short --branch
  git rev-parse HEAD
  git rev-parse main
  git merge-base --is-ancestor 5ea8f8f71548eb05a8562a10e98667e3d2061c4d HEAD
  git merge-base --is-ancestor fac32284888850bacde93815265cbabe3afd4663 main
  git branch --contains fac32284888850bacde93815265cbabe3afd4663
  ```

  Expected: clean Plan 11.26 branch; `d4ac5788` is an ancestor of the current plan-line HEAD; merged base is an ancestor; `fac32284` is not on `main` and is present only on the recorded runtime-overlay line. Stop if Git facts, backlog, or checkpoint disagree.

- [x] **Step 2: Write the RED custody assertions.**

  Add `test_plan_11_26_runtime_audit_has_single_live_custody` to `tests/unit/docs/test_open_work_pool_hygiene.py`. It must require one live-registry row linking this plan, state `Active`, owner `P11-FEAT-ACP-RUNTIME-HARDENING`, and a next gate naming Task 0/G0. It must also require the feature row to name Plan 11.26, audit-only scope, and the prohibition on production fixes.

- [x] **Step 3: Prove the custody test is RED for the pre-execution `Blocked` state.**

  Run:

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py::test_plan_11_26_runtime_audit_has_single_live_custody -q
  ```

  Expected: FAIL because plan authoring registered the plan as `Blocked` pending review/execution authority, not because the plan is missing or duplicated.

- [x] **Step 4: Claim the lane and record the baseline intake.**

  Change the one registry row to `Active`; set its next gate to G0 baseline/review intake. Update the feature row to state that Plan 11.26 owns audit execution but not production remediation. Create `reports/plan-11-26-baseline-intake.json` with exact Git refs, `binding_commit: null`, reconciliation status `UNRESOLVED`, and H1-H8 baseline scopes copied from the approved spec.

- [x] **Step 5: Run the complete plan-hygiene gate.**

  ```powershell
  uv run --frozen pytest tests/unit/docs -q
  ```

  Expected: PASS, including this plan's prerequisites table and single live-registry custody.

- [x] **Step 6: Obtain G0 reviewer acceptance and commit only with authorization.**

  The reviewer verifies checkpoint alignment, all scope-outs, and the baseline JSON. Then run `uv run --frozen ruff check .` and `git diff --check`. With explicit commit approval only:

  ```powershell
  git add docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md tests/unit/docs/test_open_work_pool_hygiene.py reports/plan-11-26-baseline-intake.json
  git commit -m "docs(plan-11.26): claim runtime audit custody"
  ```

### Task 1: Resolve every machine, service, authority, and human unknown

**Files:**

- Modify: `.gitignore`
- Modify: `docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md`
- Create: `reports/plan-11-26-prerequisite-intake.json`
- Modify: `reports/plan-11-26-baseline-intake.json`

**Interfaces:**

- Consumes: Task 0 accepted baseline; operator answers for authority/cost/human availability.
- Produces: one sanitized row per prerequisite with `observed_status`, `method`, `owner`, `authorized`, `dependent_rows`, and `scope_out`; no secret value, service mutation, client launch, or paid call.

- [x] **Step 1: Record read-only platform and binary observations.**

  Run version/status commands only: `uv --version`, `node --version`, `npm --version`, `java --version`, `mvn --version`, `acpx --version`, `wsl --status`, and Zed file `VersionInfo`. Record stdout-derived versions and command exit codes; do not launch any ACP client or Zed.

- [x] **Step 2: Establish Redis/TimeSeries availability without mutation.**

  Identify Windows port ownership and WSL distro availability. If a service is already running, use only a health/capability read approved by the operator; otherwise record `UNAVAILABLE` or `UNAUTHORIZED`. Do not start a container, daemon, or Redis process and do not write a key.

- [x] **Step 3: Establish authority and credential capability without disclosure.**

  Record only booleans for `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` presence. Record separate operator decisions for Gateway/model calls, paid calls, Redis mutation, acpx, SDK/conformance-harness comparison, Zed, and the wall-clock lease window. Never serialize values, prefixes, lengths, hashes, or environment dumps.

- [x] **Step 4: Establish trusted-workspace and operator availability.**

  Record whether the named workspace is trusted and whether an operator can perform five Zed GUI runs. Do not open Zed or change settings.

- [x] **Step 5: Publish prerequisite decisions and scope-outs.**

  Each unresolved/negative row must list every dependent matrix row and its named owner. WSL-dependent evidence is Plan 11.26/operator-owned; binding/lease/resume evidence remains Plan 11.7-owned; unauthorized live rows remain dormant under the operator.

- [x] **Step 6: Validate sanitization and obtain reviewer acceptance.**

  Run a content scan for forbidden credential names followed by `=` and for values supplied through the current environment. The reviewer accepts each status or rejects the report. Commit only after `uv run --frozen ruff check .`, `git diff --check`, and explicit authorization.

### Task 2: Build the shared audit schema, inventories, provenance, checkpoints, corpus, and cost model

**Files:**

- Modify: `docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md`
- Create: `tools/plan1126_runtime_audit/{__init__,model,source,inventory,provenance,checkpoints,corpus,cost,repeatability,render}.py`
- Create: `tools/run_plan1126_runtime_audit.py`
- Create: `tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json`
- Create: `tests/fixtures/plan1126_runtime_audit/frozen-regression-seeds.json`
- Create: `tests/unit/tools/plan1126_runtime_audit/test_{artifact,source,inventory,provenance,checkpoints,corpus,cost,repeatability,render}.py`

**Interfaces:**

- Produces: `BaselineScope`, `Classification`, `LiveStatus`, `GateStatus`, `PrerequisiteStatus`, `InventoryKind`, `DiscoveredSite`, `Finding`, `AuditArtifact`, `SourceTree`, `GitCommitSource`, `discover_sites`, `verify_running_artifact`, `CheckpointStore`, `literal_seeds`, `derived_seed`, `compute_cost`, and `classify_repeatability`.
- Consumes: immutable Git blobs, Python source, the external JSON schema, literal corpus, and Task 0/1 reports. It does not import or modify runtime behavior.

- [x] **Step 1: Write RED closed-vocabulary and artifact-schema tests.**

  Define the required public shapes in tests before implementation:

  ```python
  class BaselineScope(StrEnum):
      MERGED = "merged"
      OVERLAY = "overlay"
      BOTH_ALIGNED = "both-aligned"
      BOTH_DIVERGENT = "both-divergent"
      BINDING = "binding"

  class LiveStatus(StrEnum):
      UNRUN = "UNRUN"
      PARTIAL = "PARTIAL"
      INVALID = "INVALID"
      COMPLETE = "COMPLETE"
  ```

  Require all ten approved classifications, exact top-level artifact fields, per-record baseline scope, no unknown keys, `UNCLASSIFIED == 0` at G1, and machine-checkable live status. Run the first two exact predicate commands from the predicate map and expect missing-module failures.

- [x] **Step 2: Implement the model and independent JSON-schema agreement.**

  `model.py` owns Python types and deterministic `to_dict`; the fixture schema independently constrains the same fields/enums. Tests must reject rendered prose in place of status, a workspace-only `git_sha`, a binding finding on overlay scope, missing owner/evidence, and count mismatches.

- [x] **Step 3: Write RED source-view and inventory tests.**

  Require `GitCommitSource(commit).read_text(path)` to use immutable blob reads and reject dirty-worktree substitution. Require `discover_sites` to emit sorted unique sites for task creation/cancellation, queues, resource construction/transfer/close, broad catches, semantic wire selections, Redis clients/pools, telemetry/debug/stderr/redaction/sinks, and delivery start/publication/settlement.

- [x] **Step 4: Implement the shared AST inventory framework.**

  Each concern is a small `InventoryRule` using the same `DiscoveredSite(path, symbol, line, kind, baseline_scope, evidence_digest)` record. Use `tokenize` as well as AST to associate invariant comments/docstrings with ownership, ordering, intentional-exception, and state-transition sites. The framework must retain discovered-but-unclassified sites, compare merged/overlay symbol sets, and never treat a copied expected-site list as discovery.

- [x] **Step 5: Write RED provenance, checkpoint, corpus, and cost tests.**

  Require executable SHA-256, package/version, build-manifest digest, embedded commit/equivalent immutable provenance, launcher digest, client provenance, and environment fingerprint. Require atomic checkpoint resume/conflict rejection. Require literal seeds to survive binding-commit changes while fresh seeds equal `first_64_bits(SHA256(binding_commit + scenario_id + n))`. Require:

  ```text
  cancellation_concurrency_levels = (2, 4, 8)
  cancellation_schedules = N_cancellation_points * len(cancellation_concurrency_levels) * seed_count
  cancellation_control_schedules = N_cancellation_points * seed_count
  queue_admissions = N_queues * admission_probe_count
  sink_failure_runs = N_sinks * sink_failure_count
  idempotent_close_invocations = N_close_paths * 3 * 5
  ```

- [x] **Step 6: Implement provenance, checkpoints, corpus, cost, and repeatability without runtime mutation.**

  `verify_running_artifact` returns a typed valid/invalid result with reasons; it never infers provenance from the checkout. `CheckpointStore` writes a temporary sibling, fsyncs, and atomically replaces the target. `compute_cost` includes measured per-scenario p50/p95 and every discovered multiplier. Level `1` is the cancellation control family and is counted only by `cancellation_control_schedules`; levels `2`, `4`, and `8` are the race family counted by `cancellation_schedules`. At the 256-seed group tier this yields 768 race schedules plus 256 control schedules, exactly 1,024 per discovered cancellation point. `classify_repeatability` fingerprints normalized outcomes across repeated identical schedules and reports `FLAKY` for inconsistent runtime outcomes and `HARNESS_INVALID` for inconsistent harness/provenance inputs.

- [x] **Step 7: Implement deterministic rendering and the thin CLI.**

  JSON is canonical; Markdown is regenerated and content-free. CLI subcommands are `inventory`, `offline`, `live-redis`, `acpx`, `sdk`, `zed record`, `render`, and `verify`. `zed record` never launches Zed: it verifies current Zed/Optimus file identities, prompts the operator for one closed-vocabulary scenario outcome and attestation, and appends an atomic content-free record. Live subcommands require an explicit authority-record path and provenance manifest; missing authority returns `UNRUN`, bad provenance returns `INVALID`, and neither starts a dependency. The authority report is itself accepted only when its canonical digest appears in the closed, code-owned reviewed allowlist. A future live grant therefore requires both a separately reviewed successor report and a reviewed audit-tool change admitting that digest; caller input cannot extend or replace the allowlist.

- [x] **Step 8: Run G1 foundation verification and seek review.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit -q
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Expected: all foundation tests and Plan 11.18 oracles pass. Reviewer verifies `UNCLASSIFIED == 0` only for the foundation's own fixture corpus; production inventory classification occurs in Tasks 4-10.

### Task 3: Qualify the additional independent comparison mechanism, SDK first

**Files:**

- Modify: `docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md`
- Create: `tools/plan1126_runtime_audit/clients.py`
- Create: `tests/unit/tools/plan1126_runtime_audit/test_clients.py`
- Create: `tests/fixtures/plan1126_runtime_audit/fixture_agent.py`
- Create: `tests/fixtures/plan1126_runtime_audit/typescript-client/{package.json,package-lock.json,tsconfig.json,src/client.ts}`
- Create only if primary qualification fails: `tests/fixtures/plan1126_runtime_audit/java-client/{pom.xml,src/main/java/plan1126/QualificationClient.java}`
- Create: `reports/plan-11-26-client-qualification.json`

**Interfaces:**

- Consumes: official stable-v1 TypeScript `client({name}).connectWith(stream, workflow)` API; official Java `com.agentclientprotocol:acp-core:0.14.0` `AcpClient`/`StdioAcpClientTransport` fallback; Task 1 authority record.
- Produces: `ClientQualification` with package/harness name, exact version or immutable commit, registry/repository identity, lock/source digest, build command, fixture command, observed method sequence, result, and fallback reason.

- [x] **Step 1: Write RED qualification/provenance tests.**

  Tests reject version ranges, absent lockfiles, experimental-v2 imports, a project ACP client import, shell-string execution, missing package-repository identity, missing `initialize -> session/new -> session/prompt` observation, or claiming that the SDK replaces acpx.

- [x] **Step 2: Resolve and review the exact TypeScript package identity.**

  With package-registry access authorized, run:

  ```powershell
  npm view @agentclientprotocol/sdk version dist.tarball dist.integrity repository.url --json
  ```

  Record the returned exact stable release and integrity, then set that exact version without `^` or `~`. The reviewer compares repository identity to `https://github.com/agentclientprotocol/typescript-sdk` before installation.

- [x] **Step 3: Build the fixture-only official TypeScript client.**

  `src/client.ts` imports only `@agentclientprotocol/sdk` plus Node standard libraries, spawns `fixture_agent.py`, records ordered method/result categories without prompt bodies, and exits nonzero unless initialize/new/prompt/close complete. Generate and commit the exact lock with scripts disabled during install.

- [x] **Step 4: Compile and execute the primary qualifier.**

  ```powershell
  npm ci --ignore-scripts --prefix tests/fixtures/plan1126_runtime_audit/typescript-client
  npm run build --prefix tests/fixtures/plan1126_runtime_audit/typescript-client
  npm run qualify --prefix tests/fixtures/plan1126_runtime_audit/typescript-client
  ```

  Expected: stable-v1 client API drives the fixture and produces the reviewed ordered summary. This is fixture qualification, not Optimus protocol evidence.

- [x] **Step 5: Exercise ordered fallbacks in the same task only after the preceding candidate fails.**

  Record the primary failure first. Pin `com.agentclientprotocol:acp-core:0.14.0`, use `StdioAcpClientTransport` and `AcpClient.sync`, and run:

  ```powershell
  mvn -B -ntp -f tests/fixtures/plan1126_runtime_audit/java-client/pom.xml verify
  ```

  Do not create or run the Java fallback merely to accumulate evidence after a passing primary. If Java also fails, a reviewer may approve an independently authored ACP conformance harness in this same task only after its external repository, immutable release/commit, ACP-v1 coverage, license, install/build digest, and exact non-project-authored invocation are recorded in the qualification report. Run that recorded invocation against `fixture_agent.py`; reject a project-authored harness or a harness that cannot expose ordered initialize/new/prompt results. If no harness qualifies, retain `BLOCKED` with the failed candidates and next selection gate.

- [x] **Step 6: Publish the client qualification and preserve acpx authority.**

  Record one of `TYPESCRIPT_QUALIFIED`, `JAVA_FALLBACK_QUALIFIED`, `CONFORMANCE_HARNESS_QUALIFIED`, or `BLOCKED`, with exact command output digests and no transcript bodies. Re-record `acpx --version` as command-derived evidence and state that acpx remains mandatory.

- [x] **Step 7: Run G3 checks and obtain reviewer acceptance.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit/test_clients.py -q
  uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit -q
  uv run --frozen ruff check .
  git diff --check
  ```

  Dependent SDK matrix rows remain blocked until the reviewer accepts the report.

### Task 4: Establish delivery settlement as the worked audit example

**Files:**

- Create: `tests/unit/acp/test_plan1126_delivery_contract.py`
- Create: `tools/plan1126_runtime_audit/delivery.py`
- Create: `tools/plan1126_runtime_audit/delivery_characterization.py`
- Modify: `tools/plan1126_runtime_audit/{__init__,inventory,model,render}.py`
- Modify: `tools/run_plan1126_runtime_audit.py`
- Modify: `tests/unit/tools/plan1126_runtime_audit/{test_artifact,test_render}.py`
- Modify: `tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Generate: `reports/plan-11-26-acp-runtime-audit.md`
- Modify: `docs/superpowers/plans/2026-08-29-plan-11-26-acp-runtime-hardening-audit-implementation.md`
- Read only: `src/optimus/acp/{outbound_writer,lifecycle,settlement,conversation,spec,server}.py`

**Interfaces:**

- Consumes: Task 2 inventories/corpus/checkpoints and the settled delivery vocabulary.
- Produces: H4 record with every delivery start/publication/settlement consumer, symbol citation, baseline scope, contradiction search, 1,000-seed observations, reviewer ruling, and the evidence-record template used by Tasks 5-10.

- [x] **Step 1: Write the RED delivery-site coverage predicate.**

  Derive every send/write/enqueue, publication, flush, final-response, conversation-commit, and effect-settlement site from AST/call references. Assert that each discovered site has exactly one `DiscoveredSite` record and a delivery phase; do not seed expected file/line lists into the scanner.

- [x] **Step 2: Run the exact AST predicate and verify RED.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_ast_covers_all_send_sites -q
  ```

  Expected: FAIL because H4 classifications and the delivery-specific inventory rule do not exist.

- [x] **Step 3: Classify delivery sites against both available baselines.**

  Preserve the seven settled types exactly. Classify each site as canonical, bypassed, duplicated, contradictory, intentionally exceptional, provisional, not present, superseded, or unclassified. A new vocabulary is a finding, not an automatic replacement.

- [x] **Step 4: Write and run the 1,000-seed schedule predicate.**

  Generate schedules for queue admission, publication, write success/failure, flush ambiguity, cancellation, final-response delivery, conversation commit, and effect certainty. Replay literal frozen seeds first, then exactly 1,000 commit-derived seeds anchored to the immutable merged baseline. Record the overlay identity and `both-aligned` scope separately; never label the merged anchor as binding. The test passes when every schedule yields a complete classified record, including observed contradictions.

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_delivery_contract.py::test_delivery_contract_model_1000_seed_schedule -q
  ```

- [x] **Step 5: Publish H4 and render the report.**

  Update the canonical JSON and run:

  ```powershell
  uv run --frozen python tools/run_plan1126_runtime_audit.py render --artifact reports/plan-11-26-acp-runtime-audit.json --report reports/plan-11-26-acp-runtime-audit.md
  uv run --frozen python tools/run_plan1126_runtime_audit.py verify --artifact reports/plan-11-26-acp-runtime-audit.json
  ```

- [x] **Step 6: Obtain G2 worked-example acceptance.**

  The reviewer confirms symbol citations, contradiction search, test commands, baseline scope, and ruling. Tasks 5-10 may use the record structure only after acceptance.

### Task 5: Audit task supervision and cancellation

**Files:**

- Create: `tests/unit/acp/test_plan1126_cancellation.py`
- Create: `tools/plan1126_runtime_audit/cancellation.py`
- Modify: `tools/plan1126_runtime_audit/{__init__,model,render}.py`
- Modify: `tools/run_plan1126_runtime_audit.py`
- Modify: `tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.md`
- Read only: `src/optimus/acp/{server,spec,lifecycle,outbound_writer}.py`

**Interfaces:**

- Consumes: derived `TASK_CREATE` and `CANCELLATION_POINT` sites plus H3/Task 4 record format.
- Produces: `N_cancellation_points`, owned/escaped-child classifications, and per-point schedules across pre-start, running, delivery, settlement, and teardown phases.

- [x] **Step 1: Derive task and cancellation ownership.**

  Inventory `asyncio.create_task`, task groups, callbacks, thread/future submissions, timeout contexts, cancellation catches, joins, and task-set mutations. Each created unit records creator, owner, registration point, cancellation source, join/settlement point, and escape path.

- [x] **Step 2: Write the 256-seed race predicate.**

  For each discovered cancellation point, run level `1` as a separate control and concurrency levels `2`, `4`, and `8` as the race family. Replay the frozen corpus plus 256 derived schedules in each family. Require one terminal observation for request task, child work, delivery, conversation, and effect state. Preserve `asyncio.CancelledError` as cancellation rather than a generic internal failure. Record 768 concurrent plus 256 control schedules per point at this tier.

- [x] **Step 3: Run the exact predicate.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py::test_turn_cancellation_races_256_seed_matrix -q
  ```

  Expected: PASS only when every discovered point is scheduled and classified; runtime races may produce findings.

- [x] **Step 4: Publish H3 and supervision findings.**

  State whether `TurnControl` is canonical, bypassed, or incomplete on each baseline. Do not prescribe a new supervisor implementation. Add every newly failing schedule to the literal corpus without removing the commit-derived seed record.

- [x] **Step 5: Run the task-group tier and checkpoint it.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_cancellation.py tests/unit/acp/test_lifecycle.py tests/unit/acp/test_stdio_ndjson.py -q
  ```

  Record 25 repeated group runs per authorized platform through the CLI checkpoint store; measured duration updates computed cost.

### Task 6: Audit resource ownership, shutdown, and idempotent close

**Files:**

- Create: `tests/unit/acp/test_plan1126_shutdown.py`
- Create: `tools/plan1126_runtime_audit/shutdown.py`
- Modify: `tools/plan1126_runtime_audit/{__init__,model,render}.py`
- Modify: `tools/run_plan1126_runtime_audit.py`
- Modify: `tests/fixtures/plan1126_runtime_audit/audit-artifact.schema.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.md`
- Read only: `src/optimus/acp/{__main__,bootstrap,server,spec,preflight,outbound_writer,launch_approvals,launch_gate,launch_policy,launch_audit,trusted_paths,local_infra,local_gateway_secrets,operator_paths,operator_verify}.py`
- Read only: `src/optimus/redis/{runtime,async_bridge}.py`
- Read only: `src/optimus/telemetry/{redis_adapter,redis_sink}.py`
- Read only: `src/optimus/mcp/{runtime,client_disposition,client_sdk,client_supervisor,local_ipc}.py`

**Interfaces:**

- Consumes: resource constructor/transfer/close inventories and carried seed S1.
- Produces: `N_close_paths`, construction-to-owner graph, dependency close ordering, five-cause repeat matrix, idempotence counts, and a ruling on merged serving `RedisRuntime` custody.

- [x] **Step 1: Derive the resource ownership graph.**

  Cover Redis clients/pools, outbound writer, adapter/session resources, client-MCP resources, executor/thread ownership, and partial-construction paths. Boundary-audit launch, trust, approval, local-infrastructure, credential-resolution, and operator modules only for construction, transfer, background work, timeout/cancellation, failure propagation, and close/release. A resource is classified only when constructor, owner transfer, normal close, cancellation close, partial-failure close, and repeated-close behavior are accounted for or explicitly absent.

- [x] **Step 2: Write the five-cause/100-repeat predicate.**

  Causes are orderly EOF, request cancellation, transport failure, server cancellation, and partial startup failure. For each applicable cause, run 100 schedules. Build the persistent thread/task allowlist from a no-server control and report only growth beyond that control.

- [x] **Step 3: Write the discovered-path idempotence predicate.**

  For every close path, invoke close three times under each cause, measure underlying close/release count, and classify repeat latency above 100 ms. Do not hide double-close or timeout outcomes by weakening the assertion; record them as findings while requiring complete evidence.

- [x] **Step 4: Run both exact predicates.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_shutdown_causes_repeat_100_with_control_allowlist -q
  uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py::test_close_is_idempotent_across_discovered_paths -q
  ```

- [x] **Step 5: Rule on S1 without preclassifying a leak.**

  Compare merged serving construction at `bootstrap.py`, preflight close paths, process-lifetime shape, and overlay shutdown changes. Decide ownership/orderly-shutdown status and baseline scope; process exit reclamation is evidence, not proof of orderly close.

- [x] **Step 6: Run and checkpoint the resource group.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_shutdown.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_preflight.py tests/unit/redis/test_runtime.py tests/unit/telemetry/test_redis_adapter.py tests/unit/telemetry/test_redis_sink.py -q
  ```

### Task 7: Audit semantic error selection while preserving Plan 11.18 authority

**Files:**

- Create: `tests/unit/acp/test_plan1126_semantic_errors.py`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Read only: `src/optimus/acp/{errors,dispatcher,spec,server,lifecycle,request_ids}.py`
- Read only: `tests/unit/acp/test_error_code_registry.py`

**Interfaces:**

- Consumes: Plan 11.18 schema/AST oracles and semantic outcome/exception-to-wire selection sites.
- Produces: exhaustive selection rows for protocol/input, cancellation/deadline, ownership/concurrency, dependency availability, integrity, delivery, resource lifecycle, and invariant/programming categories.

- [ ] **Step 1: Prove Plan 11.18 remains green before extending the audit.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_errors.py -q
  ```

  Any failure is a stop condition outside Plan 11.26; do not repair production authority here.

- [ ] **Step 2: Derive every semantic selection site.**

  Inventory named error constants, `JsonRpcError` construction, exception/result catches, retry decisions, safe message/data selection, effect certainty, telemetry disposition, and cleanup obligation. Raw code ownership is not reopened.

- [ ] **Step 3: Write exhaustive selection characterization.**

  Require every discovered selection to name one of the eight categories, retryability, certainty, public output, telemetry, cleanup, and baseline scope. Require `asyncio.CancelledError` to remain distinct. Seed S3's two sanitizer broad catches as `INTENTIONALLY_EXCEPTIONAL` unless contrary evidence is cited.

- [ ] **Step 4: Run the semantic group.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_semantic_errors.py tests/unit/acp/test_error_code_registry.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_errors.py -q
  ```

- [ ] **Step 5: Publish the H6/H7 rulings.**

  H6 must remain accepted canon if the two existing mechanical oracles pass. H7 records selection gaps and intentional exceptions; no code-number or runtime mapping change occurs in this plan.

### Task 8: Audit telemetry, logging, redaction, correlation, and sink containment

**Files:**

- Create: `tests/unit/telemetry/test_plan1126_runtime_contract.py`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Read only: `src/optimus/telemetry/{events,fanout,redaction,serialization,jsonl,observability,redis_adapter,redis_sink}.py`
- Read only: `src/optimus/acp/{bootstrap,debug_trace,spec,server,settlement}.py`
- Read only: `src/optimus/agent/planning_loop.py`

**Interfaces:**

- Consumes: derived event/trace/stderr/redaction/sink sites, `ACP_TURN_SETTLEMENT`, and carried seed S2.
- Produces: `N_sinks`, reviewed runtime-event vocabulary, required correlation fields, redaction observations, sink containment results, and scalar/plural Gateway-ID ruling.

- [ ] **Step 1: Derive event and sink inventories.**

  Discover event construction, direct stderr/debug trace, fanout, serialization, redaction, Redis/JSONL/export sinks, and fallback diagnostics. Each call site records semantic event, correlation fields, content class, redaction path, and sink-failure behavior.

- [ ] **Step 2: Write the 10,000-case event-schema predicate.**

  Generate valid and missing/extra/invalid-field cases across the derived vocabulary. Compare every proposed runtime event to `ACP_TURN_SETTLEMENT`; do not assume connection/turn/operation/client fields are required until the inventory and reviewer establish them.

- [ ] **Step 3: Write the 1,000-case redaction predicate.**

  Generate nested mappings/sequences/exceptions containing credential, prompt, response, path, and request-body canaries. Require prohibited values to be absent from every authorized sink and fallback diagnostic while preserving safe field names/reasons.

- [ ] **Step 4: Write correlation and sink-failure predicates.**

  Correlation requires 100% presence only for fields the reviewed schema marks required and deterministic joins among wire error, lifecycle event, and settlement. For each discovered sink, inject 100 failures and compare runtime/wire outcome with the no-failure control.

- [ ] **Step 5: Run all four exact predicates.**

  ```powershell
  uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_event_schema_generated_10000_cases -q
  uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_redaction_generated_1000_cases -q
  uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_runtime_correlation_chain_is_complete -q
  uv run --frozen pytest tests/unit/telemetry/test_plan1126_runtime_contract.py::test_telemetry_sink_failures_are_contained -q
  ```

- [ ] **Step 6: Rule on S2 and publish H8.**

  Decide whether scalar `gateway_request_id` and plural `gateway_request_ids` encode a documented one-to-many relationship or contradictory correlation. Publish symbol citations and baseline scope; do not rename fields in this plan.

### Task 9: Audit queues, backpressure, and connection health

**Files:**

- Create: `tests/unit/acp/test_plan1126_queue_policy.py`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Read only: `src/optimus/acp/{outbound_writer,server,spec,ndjson_subprocess_session}.py`
- Read only: `src/optimus/redis/{runtime,async_bridge}.py`

**Interfaces:**

- Consumes: derived queue/producer/consumer/constructor-bound and health-probe inventories.
- Produces: `N_queues`, declared/effective bounds, overload disposition, blocking observations, and connection-health/pool ownership classifications.

- [ ] **Step 1: Derive every queue and connection-health site.**

  Record constructor bound, producer, consumer, admission API, stop behavior, overflow result, timeout, connection health probe, pool constructor, and pool close path. Missing policy remains a classified finding.

- [ ] **Step 2: Write the 10,000-admission predicate.**

  Stop the consumer and attempt 10,000 admissions per discovered queue. Cross-check behavior with the construction-site bound. Label acceptance of all attempts only as `NO_OBSERVED_BOUND_BELOW_10000` unless the constructor independently declares unbounded behavior. Waiting beyond 100 ms without an explicit outcome is `BLOCKING_WITHOUT_POLICY`.

- [ ] **Step 3: Run the exact predicate.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_queue_policy.py::test_queue_policy_cross_checks_constructor_and_10000_admissions -q
  ```

- [ ] **Step 4: Publish queue/backpressure/health findings and checkpoint the group.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_queue_policy.py tests/unit/acp/test_outbound_writer.py tests/unit/acp/test_ndjson_subprocess_session.py tests/unit/redis/test_runtime.py -q
  ```

  Record every queue and health site; `UNCLASSIFIED` must be zero for this group.

### Task 10: Audit durable session, lease, retention, and live Redis only when applicable

**Files:**

- Create: `tests/unit/acp/test_plan1126_session_lease.py`
- Create: `tests/integration/acp/test_plan1126_runtime_live_redis.py`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Read only: binding-candidate session/store/model files nominated by Plan 11.7

**Interfaces:**

- Consumes: Task 0 reconciliation status, binding code when available, Task 1 Redis authority, Task 2 provenance, and checkpoint/corpus support.
- Produces: either `NOT_PRESENT`/`PROVISIONAL_OVERLAY` with Plan 11.7 scope-out, or binding lease/retention constants plus boundary and real-Redis owner/revision characterization.

- [ ] **Step 1: Apply the binding-presence gate.**

  If Plan 11.7 has not nominated a binding integration candidate containing or superseding the durable path, emit `PROVISIONAL_OVERLAY` or `NOT_PRESENT`, name `P11-FEAT-ZED-RESUME`, and stop this task before runtime/live predicates. Never copy the overlay into the audit branch.

- [ ] **Step 2: Derive lease and retention constants independently when binding exists.**

  Resolve the ownership lease from the binding tree's `SESSION_LOAD_LEASE_SECONDS` and retention from `DEFAULT_ACP_SESSION_TTL_SECONDS` plus its monotonic configuration limit. Reject absent, aliased, or workspace-substituted values.

- [ ] **Step 3: Write and run the boundary predicate.**

  Test one scheduler tick before expiry, exact expiry, and 1,000 derived seeds around the boundary. Assert the expected owner transition uses the lease constant and that retention is never used as the ownership boundary.

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_plan1126_session_lease.py::test_session_lease_boundary_uses_binding_runtime_constant -q
  ```

- [ ] **Step 4: Gate the real Redis predicate on dependency and provenance.**

  Require a real TimeSeries-capable Redis, isolated key prefix/database, explicit Redis-mutation authority, installed-artifact provenance matching the binding commit, and five-second operation timeouts. Missing requirements yield `UNRUN` or `INVALID`, never a fake-based pass.

- [ ] **Step 5: Run owner/revision characterization only under fresh authorization.**

  Execute 50 accelerated create/acquire/mutate/release cycles and 100 owner/revision races:

  ```powershell
  uv run --frozen pytest tests/integration/acp/test_plan1126_runtime_live_redis.py::test_live_redis_owner_revision_races -m requires_redis -v
  ```

- [ ] **Step 6: Run the one wall-clock recovery row only under its separate grant.**

  Prove no recovery before the derived lease duration and recovery within the reviewed scheduler tolerance after expiry. Record elapsed monotonic time and constant provenance. Never shorten the production lease or use retention TTL to make the run convenient.

### Task 11: Execute tiered characterization and separately gated real-client rows

**Files:**

- Create: `tests/e2e/acp/test_plan1126_clients_live.py`
- Create: `reports/plan-11-26-zed-manual-observations.json`
- Create: `reports/plan-11-26-terminal-characterization.md`
- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Modify only after a fresh live grant: `reports/plan-11-26-prerequisite-intake.json`
- Modify only after a fresh live grant: `tools/run_plan1126_runtime_audit.py`
- Modify only after a fresh live grant: `tests/unit/tools/plan1126_runtime_audit/test_render.py`

**Interfaces:**

- Consumes: accepted Tasks 2-10 groups, client qualification, authority record, running-artifact provenance, computed cost, and checkpoints.
- Produces: per-task, per-group, and terminal statuses; authorized acpx/comparison/Zed observations; invalid/unrun reasons; terminal `PASS`, `PASS_WITH_FINDINGS`, or `INCOMPLETE` disposition.

- [ ] **Step 1: Run every per-task narrow command and literal regression corpus.**

  Each task runs its named predicate(s), affected existing tests, frozen corpus, 32 fresh seeds per affected scenario, and 10 repeats. Failed behavior becomes a finding only if the evidence record remains complete and schema-valid.

- [ ] **Step 2: Run every per-task-group tier.**

  Use 256 seeds per affected scenario and 25 repeats per applicable authorized platform. Feed normalized outcomes into `classify_repeatability`; inconsistent runtime outcomes are `FLAKY` findings, while changing harness/provenance inputs invalidate the batch. WSL2 uses distro-native Redis from a native ext4 clone; do not use a host-forwarded Windows Redis as Linux evidence.

- [ ] **Step 3: Recompute terminal cost and obtain cost/authority approval.**

  Update discovered `N_cancellation_points`, `N_queues`, `N_sinks`, and `N_close_paths`; include measured p50/p95. Present the exact offline and live run counts before starting the terminal batch.

  Before any live row can be approved, the reviewer must accept a successor authority report and the same separately authorized pre-live gate commit must update the closed `_ACCEPTED_AUTHORITY_DIGESTS` allowlist plus its tests with that report's canonical digest. Until both artifacts are reviewed and committed together, every newly granted live command must fail `INVALID`; caller input cannot admit the new digest.

- [ ] **Step 4: Run the full offline terminal characterization once.**

  ```powershell
  uv run --frozen python tools/run_plan1126_runtime_audit.py offline --artifact reports/plan-11-26-acp-runtime-audit.json --checkpoint reports/.plan-11-26-offline-checkpoint.json
  ```

  The checkpoint file is working evidence until the batch completes; the final content-free summary enters the terminal report.

- [ ] **Step 5: Run real acpx and qualified SDK rows only under fresh client/Gateway authority.**

  The E2E tests must invoke the independently authored binaries/packages and the installed Optimus artifact, never a project ACP client:

  ```powershell
  uv run --frozen pytest tests/e2e/acp/test_plan1126_clients_live.py -m "e2e and requires_acpx and requires_redis and requires_gateway" -v
  ```

  Run 25 valid supported-matrix acpx rounds and 25 valid rounds with the qualified SDK or conformance harness. Then run the multi-client matrix: 50 same-session rounds at each concurrency level `2`, `4`, and `8`, plus 50 distinct-session rounds. Apply the Global Constraints client-attribution rule to every acpx/SDK divergence; neither client is authoritative. Skipped, deselected, wrong-artifact, fake-dependency, or missing-provenance rows are `UNRUN`/`INVALID`, never passing evidence.

- [ ] **Step 6: Run five real Zed GUI rows only under a separate Zed grant.**

  These are operator-manual rows; pytest does not launch or control Zed. Immediately before each row, `zed record` verifies the Zed executable path/version/SHA-256, installed Optimus executable/package SHA-256 and build-manifest binding commit, trusted workspace identity, authority-report digest, and environment fingerprint. The operator performs the named GUI action, then the recorder accepts only a closed outcome enum, monotonic timestamps, safe correlation IDs, and an attestation that no prompt/response body or secret was retained. Run exactly:

  ```powershell
  uv run --frozen python tools/run_plan1126_runtime_audit.py zed record --scenario initialize --artifact reports/plan-11-26-acp-runtime-audit.json --authority-report reports/plan-11-26-prerequisite-intake.json --observations reports/plan-11-26-zed-manual-observations.json
  uv run --frozen python tools/run_plan1126_runtime_audit.py zed record --scenario session-new --artifact reports/plan-11-26-acp-runtime-audit.json --authority-report reports/plan-11-26-prerequisite-intake.json --observations reports/plan-11-26-zed-manual-observations.json
  uv run --frozen python tools/run_plan1126_runtime_audit.py zed record --scenario session-load-resume --artifact reports/plan-11-26-acp-runtime-audit.json --authority-report reports/plan-11-26-prerequisite-intake.json --observations reports/plan-11-26-zed-manual-observations.json
  uv run --frozen python tools/run_plan1126_runtime_audit.py zed record --scenario continued-prompt --artifact reports/plan-11-26-acp-runtime-audit.json --authority-report reports/plan-11-26-prerequisite-intake.json --observations reports/plan-11-26-zed-manual-observations.json
  uv run --frozen python tools/run_plan1126_runtime_audit.py zed record --scenario normal-close --artifact reports/plan-11-26-acp-runtime-audit.json --authority-report reports/plan-11-26-prerequisite-intake.json --observations reports/plan-11-26-zed-manual-observations.json
  uv run --frozen pytest tests/e2e/acp/test_plan1126_clients_live.py::test_zed_manual_observation_bundle_is_complete -m "e2e and requires_zed" -v
  ```

  `session-load-resume` records a Plan 11.7-owned `NOT_APPLICABLE` scope-out without launching Zed when no binding durable path exists. Classify current normal close as abrupt termination if observed. Any provenance drift, duplicate/missing scenario, unordered timestamp, unregistered outcome, or secret/content field makes the bundle `INVALID`. Preserve the known acpx replay-visibility limitation and never claim graceful shutdown or immediate reopen.

- [ ] **Step 7: Verify all 19 predicates (18 approved plus the supplemental Zed-bundle gate) and render terminal evidence.**

  Run each exact command in the predicate map, then:

  ```powershell
  uv run --frozen python tools/run_plan1126_runtime_audit.py verify --artifact reports/plan-11-26-acp-runtime-audit.json
  uv run --frozen python tools/run_plan1126_runtime_audit.py render --artifact reports/plan-11-26-acp-runtime-audit.json --report reports/plan-11-26-acp-runtime-audit.md
  uv run --frozen ruff check .
  git diff --check
  ```

- [ ] **Step 8: Obtain G4/G5 reviewer acceptance.**

  The reviewer checks checkpoint continuity, computed cost, installed-artifact provenance, real dependency identity, valid/unrun distinctions, and all scope-outs. Do not promote evidence or claim production acceptance.

### Task 12: Synthesize contracts, findings, and canonical remediation custody

**Files:**

- Modify: `reports/plan-11-26-acp-runtime-audit.json`
- Modify: `reports/plan-11-26-acp-runtime-audit.md`
- Modify: `reports/plan-11-26-terminal-characterization.md`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `tests/unit/docs/test_open_work_pool_hygiene.py`
- Reviewer-owned only: `docs/superpowers/reviews/plan-11-26-review-checkpoints.md`

**Interfaces:**

- Consumes: G0-G5 accepted artifacts and reviewer rulings.
- Produces: accepted cross-cutting canon, bypasses, contradictions, missing contracts, intentional exceptions, provisional/scope-out rows, rejected hypotheses, and named backlog custody for each independently schedulable remediation candidate.

- [ ] **Step 1: Freeze the reviewed finding set.**

  Every binding finding names classification, baseline, exact symbols, evidence IDs, impact, owner, and next gate. Every provisional/scope-out row names Plan 11.7 or another canonical owner. No finding contains proposed production code.

- [ ] **Step 2: Group only independently schedulable remediation candidates.**

  Separate candidates by contract and merge boundary. Assign no plan number until the backlog conflict check at actual pickup. Do not combine unrelated findings merely because this audit observed them together.

- [ ] **Step 3: Write RED canonical-disposition tests.**

  Extend `test_open_work_pool_hygiene.py` to require Plan 11.26's reviewed disposition, report links, open `P11-FEAT-ACP-RUNTIME-HARDENING` status, and one named owner/next gate per accepted candidate. Require no second open-work pool and no amendment file.

- [ ] **Step 4: Update the canonical backlog only after reviewer rulings.**

  Change Plan 11.26 registry state to the reviewer-approved terminal state and archive gate, link the canonical JSON/Markdown/terminal reports, and add candidate custody beneath the existing feature entry. Keep `P11-FEAT-ACP-RUNTIME-HARDENING` open until all later remediations separately complete.

- [ ] **Step 5: Run documentation freshness and full fitness review.**

  The reviewing agent audits backlog, roadmap, README, and every document whose current-state claims may have changed. Then run:

  ```powershell
  uv run --frozen pytest tests/unit/docs -q
  uv run --frozen pytest tests/unit/tools/plan1126_runtime_audit tests/unit/acp/test_plan1126_delivery_contract.py tests/unit/acp/test_plan1126_cancellation.py tests/unit/acp/test_plan1126_shutdown.py tests/unit/acp/test_plan1126_queue_policy.py tests/unit/acp/test_plan1126_session_lease.py tests/unit/acp/test_plan1126_semantic_errors.py tests/unit/telemetry/test_plan1126_runtime_contract.py -q
  uv run --frozen pytest tests/unit/acp/test_error_code_registry.py -q
  uv run --frozen ruff check .
  git diff --check
  ```

- [ ] **Step 6: Obtain G6 disposition and separate commit authorization.**

  The reviewer accepts or rejects each finding, scope-out, and candidate. A closing commit, push, PR, merge, archive move, evidence promotion, release action, or production-remediation plan each requires its own applicable authorization; none is implied by G6.

## Review Gates

| Gate | Required acceptance |
|---|---|
| G0 — Intake | Execution authority, canonical custody, exact baseline scope, Plan 11.7 scope-outs, and checkpoint agreement. |
| G1 — Inventory | Shared schema/provenance/checkpoint/corpus/cost mechanisms pass; every applicable discovered site is classified. |
| G2 — Contract review | H4 worked example and every later hypothesis record meet the same symbol/evidence/ruling standard. |
| G3 — Client qualification | Official TypeScript primary, same-task Java fallback, or reviewed independently authored conformance-harness fallback is fixture-qualified; acpx remains mandatory. |
| G4 — Per-group evidence | Each group completes its named predicates/repeats or records a valid owned scope-out. |
| G5 — Terminal characterization | Applicable authorized matrix completes with computed cost, checkpoints, and installed-artifact provenance. |
| G6 — Disposition | Reviewer accepts findings, scope-outs, current-state docs, and each canonical remediation candidate. |

## Definition of Done and Evidence Map

| Claim | Required evidence |
|---|---|
| Every applicable cross-cutting site is baseline-scoped and classified. | G1 inventory artifact, `test_derived_inventory_has_no_unclassified_sites`, and per-group inventories with `UNCLASSIFIED == 0`. |
| Hypotheses are evidence-backed rather than invented canon. | H1-H8 records with exact symbols, contradicting paths, tests, baseline scope, and reviewer ruling; H4 is the accepted worked example. |
| Plan 11.18 and delivery authority remain protected. | Green `tests/unit/acp/test_error_code_registry.py`, delivery predicates, and unchanged production files. |
| Unknown prerequisites are resolved early or dependent evidence is truthfully scoped out. | Task 1 prerequisite report plus Task 3 qualification report and named owners. |
| The audit uses an additional independent client or conformance harness without displacing acpx. | G3 report, exact package/source/build provenance, fixture result, and G5 real-comparison rows only when separately authorized. |
| Evidence cannot confuse workspace state with running code. | `test_running_artifact_provenance_matches_binding_commit` and per-live-row external manifests. |
| Randomized evidence is reproducible without losing prior failures. | Literal corpus predicate, commit-derived seed records, atomic checkpoints, and rerun logs. |
| Repeated-run instability and duplicated/non-obvious logic are audited consistently. | Repeatability fingerprints, duplicate-site inventory, and invariant comment/docstring coverage recorded per baseline. |
| Matrix cost is computed rather than guessed. | Cost predicate, discovered multipliers, p50/p95 measurements, and terminal cost approval. |
| Live claims use real named dependencies. | `requires_redis`, `requires_acpx`, `requires_gateway`, the qualified independent comparison mechanism, and Zed evidence with `UNRUN`/`INVALID` fail-closed states. |
| Findings have durable custody without premature fixes. | G6 reports and canonical backlog owner/next-gate rows; no `src/` diff and no production-remediation code. |
| Plan 11.26 does not overclaim closure. | Backlog keeps `P11-FEAT-ACP-RUNTIME-HARDENING` open and preserves Plan 11.7/live/release limitations. |

Plan 11.26 may complete as `PASS_WITH_FINDINGS`. It does not claim Plan 11.7 closure, formal evidence, release, push, merge, Phase 1 working-agent status, graceful Zed shutdown, acpx replay visibility, immediate session reopen, or acceptance of current runtime behavior as the desired production contract.

## Plan Self-Review

- **Spec coverage:** Tasks 0-12 map one-for-one to the approved sequence. The file map covers shared schema/inventory/provenance/checkpoint/corpus/cost infrastructure, all vertical runtime segments, all horizontal contracts, independent comparison qualification, tiered evidence, and canonical disposition.
- **Cross-cutting centralization:** Common vocabularies and mechanics live in one audit package; concern-specific rules/tests plug into it without creating competing artifact, baseline, classification, seed, provenance, or checkpoint approaches.
- **Code-quality coverage:** Shared AST/token inventory covers duplicate logic and reviewer-facing invariant comments/docstrings; repeated tiers classify flaky outcomes with one common fingerprinting model.
- **Predicate coverage:** The Planned Predicate Map lists all 18 approved names exactly once plus the supplemental Zed-bundle gate, each with one concrete file and one exact command.
- **Prerequisite coverage:** All `unknown` rows resolve in Task 1 or Task 3 before dependents. Binding/lease/resume evidence is Plan 11.7-owned; unauthorized live rows remain operator-owned and dormant.
- **Production boundary:** No task modifies `src/`. Characterization can pass with findings, and remediation is deferred to later independently numbered plans.
- **Custody:** The canonical backlog is the only live registry. Task 0 claims execution; Task 12 records disposition and candidate next gates while keeping the feature open.
- **C3:** The implementation-plan table correctly records acpx `0.12.0` as command-derived and retains execution-time re-recording.
- **Type consistency:** The shared types and function names in Tasks 2-12 match the File Map and Interfaces blocks; later tasks consume only names produced earlier.
- **No-placeholder review:** Every task names concrete files, interfaces, commands, counts, status semantics, stop conditions, and owners. Conditional Java/live/binding branches have explicit same-task behavior and evidence outcomes.
