# Plan 8.5 Release-Gate Hardening and Golden-Harness Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close PR #21 review gaps so shadow promotion matches gate-evaluated state, the one-key scanner covers the real local credential surface, the Phase 1 release CLI can reach a truthful PASS/FAIL, release commands cannot hang indefinitely, shadow copy cost is bounded, and fitness-gate telemetry reports reconcilable cost.

**Architecture:** Keep Plan 8.5 inside the Plan 8 release-gate and mutation-validation boundary. Extend `optimus.gates.shadow_workspace`, `optimus.release.credentials`, `optimus.release.defaults`, `optimus.release.runner`, `optimus.retry.gated_run`, and `tools/run_phase1_release_gate.py` without re-opening Plan 7 usage accounting or Plan 9 loop/skill work. This plan closes gaps against existing Test Strategy sections 9, 12, and 13; it does not add new release requirements.

**Tech Stack:** Python >=3.14, pydantic >=2.8, pytest, pytest-asyncio, coverage.py, pytest-cov, stdlib `dataclasses`, stdlib `decimal`, stdlib `pathlib`, stdlib `subprocess`, existing `optimus.gates`, `optimus.golden`, `optimus.release`, `optimus.retry`, and `optimus.telemetry` modules. No new runtime dependency is required unless the implementor chooses a maintained ignore-pattern helper; prefer stdlib first.

---

## Source Anchors

- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, Plan 8.5: gap-closing slice after Plan 8, before Plan 9.
- `docs/superpowers/plans/2026-07-05-retry-fitness-gates-golden-tasks-release-gate.md`: Plan 8 implementation, Deferred Follow-Ups P8-FU-1 through P8-FU-3, and PR self-disclosed unchecked test-plan items (golden-harness CLI, staging Gateway E2E).
- GitHub PR #21 code review (2026-07-06): shadow deletion divergence, one-key scan surface, CLI fail-closed harness, command timeout, shadow copy cost, telemetry cost placeholder, optional `retry`↔`gates` import cycle.
- `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf`, sections 9, 12, and 13: transient vs permanent failure handling, golden task expected mode/tools/cost/final state, ordered Phase 1 release gates, and one-key go/no-go.
- `AGENTS.md`: local runtime credentials limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; failed fitness gates must not leave partial writes; mutation paths pass through `MutationGuard` / `assert_mutation_allowed()`.

## Review Finding Traceability

| ID | Finding | Plan 8.5 owner |
|----|---------|----------------|
| P8-FU-1 / Critical #1 | Shadow promotion does not delete files removed in shadow tree | Task 1 |
| Review #2 | One-key gate scans only three hardcoded config paths | Task 2 |
| Plan 8 PR test-plan | CLI always fails without manual harness injection | Task 3 |
| Review #4 | `CommandGate` has no subprocess timeout | Task 4 |
| P8-FU-2 / Review #5 | Full `copytree` per retry with narrow ignore list | Task 5 |
| Review #6 | `GatedRetryRunner._emit_fitness_gate` hardcodes `cost_usd=0` | Task 6 |
| P8-FU-3 | `fail_after_promoted_paths` test hook on production `ShadowWorkspaceMutationRunner` API | Task 8 |
| Review #7 (optional) | Deferred `CompositeGateError` import in `classify_failure` | Task 9 (optional) |

## Scope

### In Scope

- Deletion detection and promotion in shadow workspace with rollback of deleted files on partial promotion failure.
- Default one-key scan surface alignment (extend paths or document/test explicit boundary).
- Default CLI golden-harness wiring or documented flag/config path; explicit Sprint 1 sign-off decision for staging Gateway E2E vs manual step.
- Bounded timeout for release-gate subprocess commands with failed-gate reporting on expiry.
- Configurable/broader shadow copy ignore patterns and/or shadow reuse across gated-retry attempts within one run.
- Non-placeholder `cost_usd` on fitness-gate telemetry emitted from gated retry orchestration.
- Removal of `fail_after_promoted_paths` from production promotion/mutation-runner APIs with equivalent rollback test coverage via a test-only seam.
- Tests and docs updates proving the above.

### Out of Scope

- Staging Gateway E2E implementation unless Task 3 explicitly chooses it as the Sprint 1 default (otherwise document as manual).
- LLM-judged golden evaluation (remains Gateway-routed extension).
- Plan 9 `GoalLoopController`, `SkillRegistry`, and bounded loop controllers.
- Plan 10 context-window optimization gates and calibration placeholders.
- Rewriting Plan 7 usage accounting or observability export behavior.

### Dependency Notes

- Plan 8 (#21) must be merged or accepted before Plan 8.5 implementation starts.
- Plan 8.5 should branch from latest `main` after Plan 8 merge, using `CONTRIBUTING.md` worktree conventions.
- Task 6 may require a small cost carrier on gated attempt results if actual candidate cost is not yet available from the harness path; do not estimate tokens or cost post-hoc when gateway usage is available.

## File Structure

- Modify: `src/optimus/gates/shadow_workspace.py` - deletion propagation, ignore patterns, optional shadow reuse seam.
- Modify: `src/optimus/gates/mutation_flow.py` - pass ignore/reuse options; remove `fail_after_promoted_paths` from production surface; keep promotion rollback guarantees.
- Modify: `src/optimus/release/credentials.py` - shared default config path list or scan-boundary helper (if extending surface).
- Modify: `src/optimus/release/defaults.py` - one-key scan wiring, command timeouts, golden harness default/CLI hook.
- Modify: `src/optimus/release/runner.py` - `CommandGate` timeout support.
- Modify: `src/optimus/retry/gated_run.py` - fitness-gate telemetry cost, optional shadow reuse across attempts.
- Modify: `tools/run_phase1_release_gate.py` - harness wiring and/or CLI flag.
- Modify: `README.md` - scan boundary, harness flag, timeout, and staging E2E decision.
- Modify: `tests/unit/gates/test_mutation_flow.py` - deletion promote + rollback tests; migrate rollback tests off production `fail_after_promoted_paths`.
- Modify: `tests/integration/gates/test_composite_gate_failure_flow.py` - deletion divergence regression (if needed).
- Modify: `tests/unit/release/test_credentials.py` - extended default scan surface or boundary tests.
- Modify: `tests/unit/release/test_defaults.py` - scan paths, timeout, harness CLI smoke.
- Modify: `tests/unit/release/test_runner.py` - command timeout tests.
- Modify: `tests/unit/retry/test_gated_run.py` - shadow reuse and telemetry cost tests.
- Create (optional): `tests/integration/release/test_phase1_release_gate_cli.py` - default CLI PASS/FAIL smoke with deterministic harness.
- Optional: `src/optimus/gates/exceptions.py` or `src/optimus/retry/exceptions.py` - shared `CompositeGateError` home (Task 9).

## Human Agile Sizing

Roughly 1-2 weeks of human development effort:

- Days 1-2: shadow deletion propagation and rollback tests.
- Day 3: one-key scan surface decision + tests.
- Days 4-5: golden harness CLI wiring and sign-off decision doc.
- Day 6: command timeout.
- Days 7-8: shadow ignore/reuse hardening and promotion test-hook removal.
- Day 9: fitness-gate telemetry cost.
- Day 10: focused verification, README, optional import refactor.

## Commit Policy for Execution

Each task includes a commit step because the Superpowers workflow favors small reviewable checkpoints. In this repository, commit steps are approval-gated: do not run `git commit`, push, delete branches, or rewrite history unless the user explicitly approves that action.

---

## Task 1: Shadow-Workspace Deletion Propagation

**Traceability:** P8-FU-1, PR #21 Critical Issue #1

**Files:**
- Modify: `src/optimus/gates/shadow_workspace.py`
- Modify: `src/optimus/gates/mutation_flow.py` (if promotion plan shape changes)
- Test: `tests/unit/gates/test_mutation_flow.py`
- Test: `tests/integration/gates/test_composite_gate_failure_flow.py` (optional regression)

- [ ] **Step 1: Write failing deletion promotion tests** — candidate deletes a tracked file; assert real workspace file removed after gates pass; assert deletion restored when a later promotion step fails.
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement deletion detection in `changed_paths()` and deletion promotion in `promote_shadow_changes()` with rollback of removed files**
- [ ] **Step 4: Run gate tests**
- [ ] **Step 5: Commit**

**Acceptance criteria:**
- Promotion plan includes deletions (workspace path present, shadow path absent).
- Rollback restores deleted files on mid-promotion failure.
- Composite gates evaluate the same post-promotion shape the user would see after successful promotion.

---

## Task 2: One-Key Scanner Default Wiring

**Traceability:** PR #21 Review #2

**Files:**
- Modify: `src/optimus/release/defaults.py`
- Modify: `src/optimus/release/credentials.py` (if centralizing default paths)
- Test: `tests/unit/release/test_credentials.py`
- Test: `tests/unit/release/test_defaults.py`
- Modify: `README.md` (if documenting an explicit scan boundary instead of extending paths)

- [ ] **Step 1: Write failing test** — provider key resolvable from an in-scope artifact the release runner reads (e.g. JSON report output path, coverage artifact, or other runner-produced file) OR test that documents the explicit excluded set with a failing case for any newly included path.
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement chosen approach** — extend `_one_key_credential_gate()` default `config_paths` to the reviewed surface **or** add `RELEASE_GATE_CREDENTIAL_SCAN_PATHS` / documented constant with tests locking the boundary.
- [ ] **Step 4: Run credential and defaults tests**
- [ ] **Step 5: Commit**

**Decision record required in PR:** list every path class scanned by default (env, dotenv, pyproject, report outputs, process snapshots, etc.) or justify each exclusion.

---

## Task 3: Golden-Harness Wiring for Default CLI

**Traceability:** Plan 8 PR unchecked test-plan items (harness CLI, staging E2E)

**Files:**
- Modify: `tools/run_phase1_release_gate.py`
- Modify: `src/optimus/release/defaults.py`
- Create (if needed): `src/optimus/golden/local_harness.py` or equivalent deterministic harness
- Test: `tests/unit/release/test_defaults.py`
- Create: `tests/integration/release/test_phase1_release_gate_cli.py` (recommended)
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI integration test** — with Optimus-only env and deterministic harness, `python tools/run_phase1_release_gate.py` exits 0 and golden-task-suite passes; without harness, still exits 1 with `golden task harness not configured`.
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement** — default local deterministic harness for `phase1_golden_tasks.json` **or** `--golden-harness` / config path; document whether staging Gateway E2E is required for Sprint 1 sign-off or a manual checklist item. **Record the path not chosen as an explicit deferred decision** in the task output (README + PR), not only the chosen path.
- [ ] **Step 4: Run CLI and golden tests**
- [ ] **Step 5: Commit**

**Note:** If staging Gateway E2E is not implemented in this task, README and PR must state that explicitly; do not mark Sprint 1 sign-off complete on staging evidence alone. If default local harness is not wired into the CLI, document that deferral explicitly with the flag/config path that operators must use instead.

---

## Task 4: Release-Gate Command Timeout

**Traceability:** PR #21 Review #4

**Files:**
- Modify: `src/optimus/release/runner.py`
- Modify: `src/optimus/release/defaults.py` (pass timeout to command gates)
- Test: `tests/unit/release/test_runner.py`

- [ ] **Step 1: Write failing timeout test** — injected executor or short timeout proves hung command returns `passed=False` with timeout summary, runner continues to next gate.
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Add bounded `subprocess` timeout to `CommandGate` / `_run_command` with safe summary (no secret leakage)**
- [ ] **Step 4: Run release runner tests**
- [ ] **Step 5: Commit**

---

## Task 5: Shadow-Workspace Copy Cost Hardening

**Traceability:** P8-FU-2, PR #21 Review #5

**Files:**
- Modify: `src/optimus/gates/shadow_workspace.py`
- Modify: `src/optimus/retry/gated_run.py` (reuse shadow per retry loop if chosen)
- Test: `tests/unit/gates/test_mutation_flow.py`
- Test: `tests/unit/retry/test_gated_run.py`

- [ ] **Step 1: Write failing tests** — large ignored directory (e.g. `.venv` fixture) does not get copied; gated retry reuses one shadow workspace across attempts (if reuse approach chosen).
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Implement configurable ignore patterns with safe defaults (`.git`, `__pycache__`, `.pytest_cache`, `.venv`, `node_modules`, common build outputs) and/or shadow reuse across attempts**
- [ ] **Step 4: Run gate and gated-retry tests**
- [ ] **Step 5: Commit**

---

## Task 6: Fitness-Gate Telemetry Cost Accuracy

**Traceability:** PR #21 Review #6, Plan 7 reconciliation dependency

**Files:**
- Modify: `src/optimus/retry/gated_run.py`
- Test: `tests/unit/retry/test_gated_run.py`
- Test: `tests/unit/telemetry/test_events.py` (if event payload assertions need extension)

- [ ] **Step 1: Write failing test** — gated retry with non-zero candidate cost emits `fitness_gate` telemetry with matching `cost_usd` (not `0`).
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Thread actual candidate/run cost into `_emit_fitness_gate`** from gateway-normalized fields or an explicit `Decimal` on the gated attempt result; never post-hoc estimate when provider usage is available.
- [ ] **Step 4: Run retry and telemetry tests**
- [ ] **Step 5: Commit**

---

## Task 8: Remove Promotion Failure Test Hook From Production API

**Traceability:** P8-FU-3

**Files:**
- Modify: `src/optimus/gates/mutation_flow.py`
- Modify: `src/optimus/gates/shadow_workspace.py` (if hook lives on promotion path)
- Test: `tests/unit/gates/test_mutation_flow.py`

- [ ] **Step 1: Write failing test** — production `ShadowWorkspaceMutationRunner` signature must not accept `fail_after_promoted_paths`; rollback-on-partial-promotion-failure behavior is still provable through a test-only seam.
- [ ] **Step 2: Run tests to verify they fail**
- [ ] **Step 3: Remove `fail_after_promoted_paths` from production APIs** — migrate existing rollback test to injected file copier, promotion strategy, or private test helper.
- [ ] **Step 4: Run gate and mutation-flow tests**
- [ ] **Step 5: Commit**

**Acceptance criteria:**
- Runtime promotion and mutation-runner public APIs no longer expose `fail_after_promoted_paths`.
- Rollback coverage for mid-promotion failure remains equivalent or stronger.
- No production runtime path can trigger artificial promotion failure through public parameters.

---

## Task 9 (Optional): Shared Composite Gate Exception Module

**Traceability:** PR #21 Review #7

**Files:**
- Create: shared exceptions module (location TBD by implementor)
- Modify: `src/optimus/retry/policy.py`
- Modify: `src/optimus/gates/fitness.py`
- Test: existing retry and gate tests (must remain green)

- [ ] **Step 1: Move `CompositeGateError` to shared low-level module without import cycle**
- [ ] **Step 2: Run full retry/gate test suite**
- [ ] **Step 3: Commit** (only if user approves optional scope)

---

## Task 10: Focused Verification and Sign-Off

**Files:**
- Verify: `src/optimus/gates/shadow_workspace.py`
- Verify: `src/optimus/release`
- Verify: `src/optimus/retry/gated_run.py`
- Verify: `tools/run_phase1_release_gate.py`

- [ ] **Step 1: Run focused Plan 8 + 8.5 tests**

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release -v
```

- [ ] **Step 2: Run telemetry regression**

```bash
pytest tests/unit/telemetry tests/integration/telemetry -v
```

- [ ] **Step 3: Run Plan 8 module coverage gate (≥ 80%)**

```bash
pytest tests/unit/retry tests/unit/gates tests/unit/golden tests/unit/release tests/integration/retry tests/integration/gates tests/integration/release --cov=optimus.retry --cov=optimus.gates --cov=optimus.golden --cov=optimus.release --cov=optimus.telemetry --cov-branch --cov-report=term-missing --cov-fail-under=80
```

- [ ] **Step 4: Run default release CLI** — Optimus-only env; assert real PASS with wired harness and documented staging E2E status.

```bash
python tools/run_phase1_release_gate.py
```

- [ ] **Step 5: Check diff hygiene** — `git status --short`, `git diff --check`

- [ ] **Step 6: Commit** (approval-gated)

---

## Self-Review

- Closes P8-FU-1, P8-FU-2, and P8-FU-3 without expanding Plan 9/10 scope.
- One-key and golden-harness items convert implicit gaps into tested or explicitly documented boundaries; rejected fork choices are recorded as deferred decisions.
- Command timeout prevents indefinite release-gate hangs.
- Telemetry cost field supports Plan 7 reconciliation semantics.
- TDD: each task starts with a failing test tied to a review finding ID.

## Execution Handoff

Plan 8.5 should start after Plan 8 (PR #21) is merged to `main`. Branch from latest `main` using `CONTRIBUTING.md` conventions (e.g. `agent/<id>/plan-8-5-release-gate-hardening`).

**Execution options:** subagent-driven (recommended) or inline with `superpowers:executing-plans`.
