# Plan 11.7 Standalone Zed Server-Side Custody Feasibility Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to execute this amendment task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. No checkbox may change until its stated verification command has
> run and passed.

**Goal:** Determine, without production changes, whether Zed 1.13.1 exposes a durable and
non-ambiguous signal that lets a fresh `session/new` after a full Zed restart be correlated with one
exact prior Zed-originated Optimus session rather than a genuinely new conversation in the same
workspace.

**Architecture:** Preserve the frozen Plan 11.7 and sealed Task 0 Steps 1-4 chain. Run a bounded
Windows feasibility probe in which Zed remains the only ACP client, an opaque byte relay captures
custody evidence, the production launch gate proves environment equivalence, Optimus's independent
debug trace corroborates the live transcript, and A/B restart observations plus a conditional
same-workspace fresh-thread control test every candidate correlation signal. Seal one fail-closed
disposition and return it for separate operator approval; do not implement server-side custody.

**Tech Stack:** Python 3.12, standard-library binary I/O and subprocesses, Pydantic v2, pytest,
pytest-cov/coverage.py, Ruff, Git, Windows PowerShell/CIM process observation, Redis 8 with
TimeSeries, Optimus Gateway, the merged evidence collector/redaction gate, Zed 1.13.1, and Zed
source commit `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`.

**Identity:** This is a standalone amendment to existing Plan 11.7. It allocates no new Plan 11.x
number, creates no new roadmap lane, remains owned by `P11-FEAT-ZED-RESUME`, and uses the existing
`docs/superpowers/reviews/plan-11-7-review-checkpoints.md` governance log.

**Status:** Draft for operator approval. Approval authorizes only this feasibility probe. It does
not authorize production implementation, a render observer, frozen Plan 11.7 Task 0 Steps 5-7, or
frozen Plan 11.7 Tasks 1-11.

## Global Constraints

- The frozen Plan 11.7 file is
  `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`.
  Never edit it or its checkboxes.
- The authoritative frozen-plan Git-blob SHA-256 is
  `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D`.
  Task 0 Step 1's sealed operator approval is bound to that exact digest.
- The approved design is
  `docs/superpowers/specs/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-design.md`,
  LF-byte SHA-256
  `8808E5212DCDB3B44198096D1A0AFE7E20A53E4A9B28438DA5AA23245D339F0E`.
- The triggering discovery disposition is `stop_amend_plan_session_load_unreachable` in
  `reports/plan-11-7-task0-artifacts/step4-discovery/discovery-finding.json`.
- The triggering sealed evidence report is
  `reports/plan-11-7-task0-artifacts/step4-discovery/evidence-report.json`, raw-byte SHA-256
  `1579A5B1A84F1AE46C0B09B317F61B93D919E5E03725FFA8BD0F9F6BD32565BF`.
- The amendment-file approval is a new identity + UTC + exact LF-byte SHA-256 triple. The reviewer
  records it in the existing Plan 11.7 checkpoint log before Task 0 execution. The worker never
  edits that reviewer-owned log.
- The worker reads the checkpoint Current State first and verifies every ruling against the tree,
  evidence files, Git objects, and hashes on disk. Recorded rulings are settled decisions.
- Probe execution is custody-bound to the existing Plan 11.7 worktree
  `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` on branch
  `agent/cursor/p11-feat-zed-resume`. That worktree holds the reviewer-owned checkpoint log and the
  untracked sealed Task 0 evidence. Before Task 0 starts, the approved amendment and design bytes
  must be present there through separately authorized Git integration. Never copy the checkpoint
  log or sealed trigger evidence into another worktree, and never create an empty replacement log.
  If that worktree or either custody input is unavailable, stop and return to the operator.
- Zed is the only ACP client during custody observations. Do not run `acpx` concurrently, create a
  project-authored ACP client, inject UI input, rewrite a session ID, return an old session from
  `session/new`, alter Zed profile session state, or correlate by timestamps/PIDs/workspace alone.
- Independent real-`acpx` restart/load/replay evidence remains mandatory for any future production
  implementation amendment. This relay is never ACP-conformance evidence.
- No file under `src/optimus`, `src/optimus_gateway`, or the pinned Zed source tree may change.
  Probe code is restricted to the exact `tools/` and `tests/unit/tools/` files listed below.
- Relay-mediated process ancestry is not production-representative. No ancestry-derived candidate
  may be eligible from a relay run; any topology-dependent candidate requires an additional direct,
  non-relayed full-restart control.
- The direct Zed launch and every relayed Optimus launch consume the same durable approval record
  and must match approval ID/mode, full `security_snapshot_digest`, workspace digest,
  registry/policy versions, setting-decision structure, propagation-name sets, and `AUTHORIZED`
  outcome. Do not reimplement the digest algorithm.
- The relay inherits Zed's environment and launches Optimus with `env=None` and `cwd=None`; it may
  not add, remove, rewrite, persist, or normalize an environment value. Relay-only configuration is
  supplied through its argv before `--` and is never forwarded to the Optimus child.
- The relay forwards opaque bytes only. ACP parsing occurs only on immutable copies after capture.
  Optimus's independently authored `.optimus/debug-acp.ndjson` must corroborate every relay record.
- The workspace contains a readable regular `README.md` inside the authorized root. Record its
  relative path, file identity, and raw-byte SHA-256 before launch. Never substitute another file.
- The exact prompt fixture is UTF-8 LF text:
  `Read README.md and answer with one sentence naming this project. Do not modify files.`
  It has no BOM, ends with exactly one LF, and has SHA-256
  `8EEA4738E72159A863FEA22A542F92D6A99E3681803BA21863F734C577480D82`.
- Zed `settings.json` mutation is an external-state action requiring separate operator approval at
  live-execution time. Preserve the exact pre-image and restore existence state and bytes on every
  success, failure, timeout, or crash. Restore failure outranks every feasibility result.
- Use the real installed Zed 1.13.1 binary and launcher and re-hash them at execution. Re-hash Zed
  source commit `00bd72e7838f4b875a913cd112b47a0ebe1ca62b` and every cited source blob. Do not
  inherit Task 0's old identity table by reference.
- Live prompt evidence uses real Redis TimeSeries and the real Optimus Gateway. Unit fakes cannot
  satisfy a live claim. Provider access remains Gateway-only; preserve provider-reported usage and
  cost without estimation.
- Correlation-capture retries and post-new prompt retries have independent caps of three. Every
  attempt has its own immutable manifest and an evidence-backed transient/permanent classification.
  A valid `session/new` capture is not repeated because its later prompt timed out.
- A Zed panic/crash is `stop_probe_zed_client_crashed` by default and stops immediately. A retry
  requires evidence proving the particular failure transient; prior Case 2 makes crashes an expected
  live possibility, not an unnamed exception.
- Raw evidence is promoted only through subprocess invocation of the merged public entry point
  `tools/evidence_gather.py redact`. Do not implement plan-specific sanitization and do not import
  `tools.evidence_gather_support`.
- Raw content, raw environment-sensitive artifacts, private approval records, and raw transcript
  bytes remain under an operator-approved private custody root. Normalized output contains hashes,
  identities, safe structure, usage/cost, and reason codes only.
- Transient retries are capped at three unless a later operator-approved amendment changes the
  bound. Permanent failures stop immediately.
- The reviewer independently checks on-disk evidence, reducer precedence, settings restoration,
  production-source cleanliness, and living-document freshness before accepting the verdict.
- Implementation commits, push, PR creation, merge, external issue creation, approval mutation,
  settings mutation, Redis deletion, and branch deletion each require their existing separate
  authorization. Do not use `--no-verify`.

---

## Amendment effect on frozen Plan 11.7

Approval of this file discharges Task 0 Step 4's instruction to “stop and amend the plan before
implementation” only by authorizing the bounded probe below. The frozen plan remains the historical
implementation contract and retains its sealed digest. This amendment temporarily supersedes its
sequencing sentence as follows:

1. frozen Task 0 Steps 1-4 remain sealed inputs and are not rerun or rechecked as progress boxes;
2. frozen Task 0 Steps 5-7 and Tasks 1-11 remain blocked while this amendment is Draft, approved but
   unexecuted, executing, awaiting independent review, or awaiting operator verdict;
3. `feasible_server_side_custody_candidate` does not unblock them; it triggers a separate design and
   operator go/no-go for a future production amendment;
4. `infeasible_for_production_target` leaves them blocked without an optimistic fallback; and
5. a crash, dependency block, or invalid probe leaves feasibility undecided and returns to the
   operator without widening scope.

The owning entry remains `P11-FEAT-ZED-RESUME`. No work is deferred to an unnamed lane.

## File and responsibility map

| File | Responsibility |
|---|---|
| `tools/plan117_custody_contract.py` | Canonical schemas, enums, hash helpers, correlation eligibility, attempt budgets, and fail-closed reducer shared by runner and verifier |
| `tools/plan117_custody_relay.py` | Opaque full-duplex byte relay; private raw stream/index capture; exact child argv/environment/cwd inheritance |
| `tools/run_plan117_custody_feasibility.py` | Phase-scoped orchestration, preconditions, settings transaction, process/launch capture, immutable attempt manifests, completed-transcript projection, and operator instructions |
| `tools/verify_plan117_custody_feasibility.py` | Offline-only manifest, hash, ancestry, environment-equivalence, transcript/debug, A/B/C, retry, restoration, redaction, and disposition verification |
| `tests/unit/tools/test_plan117_custody_contract.py` | Exhaustive reducer precedence, eligibility, attempt-budget, schema, and canonical-hash tests |
| `tests/unit/tools/test_plan117_custody_relay.py` | Opaque byte equality, ordering, EOF, backpressure, child argv/env/cwd, mutation, and failure tests |
| `tests/unit/tools/test_run_plan117_custody_feasibility.py` | Settings rollback, prompt/correlation budget separation, process observation, direct/relay approval comparison, completed-copy parsing, and no-client-injection tests |
| `tests/unit/tools/test_verify_plan117_custody_feasibility.py` | Positive fixture plus one tamper test for every evidence-contract field and stop-precedence edge |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Checked-in classification of every persistence/export sink discovered in the new `tools/` modules; update at the task that introduces each surface |
| `tests/fixtures/evidence/plan117-server-custody-prompt.txt` | Exact LF prompt fixture named in Global Constraints |
| `tests/fixtures/evidence/scenarios/plan117-server-custody.toml` | Collector/redaction scenario that permits a complete custody observation without requiring successful model completion |
| `reports/plan-11-7-server-custody-feasibility.md` | Human-readable facts, attempts, signal inventory, disposition, limitations, and operator-return status |
| `reports/plan-11-7-server-custody-feasibility.json` | Canonical normalized result consumed by the verifier |
| `reports/plan-11-7-server-custody-artifact-manifest.json` | Relative artifact locators, SHA-256 values, hash methods, run/attempt roles, and redaction/restoration references |
| `reports/plan-11-7-server-custody-artifacts/` | Promoted trigger, target, process, launch, transcript projection, debug suffix, signal inventory, reducer, attempt, restoration, and redaction artifacts |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Current Plan 11.7 gate before execution and sealed disposition after review |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Current active-slice status and amendment/verdict dependency |
| `docs/superpowers/plans/evidence-handoff-open-work-pool.md` | Exact render-observation dependency on approved same-session custody |
| `README.md` | Freshness audit; update only if an existing current-state claim is made false by the amendment or verdict |

## Core interfaces

`tools/plan117_custody_contract.py` produces these exact public types:

```python
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class ProbeDisposition(StrEnum):
    INVALID_TRIGGER_CHAIN = "invalid_probe_trigger_chain_mismatch"
    INVALID_TARGET_IDENTITY = "invalid_probe_target_identity_mismatch"
    INVALID_RELAY_ENVIRONMENT = "invalid_probe_relay_environment_mismatch"
    INVALID_SETTINGS_RESTORE = "invalid_probe_settings_not_restored"
    INVALID_NON_ZED_TRAFFIC = "invalid_probe_non_zed_client_or_injected_traffic"
    INVALID_PROCESS_CUSTODY = "invalid_probe_process_custody_ambiguous"
    INVALID_TRANSCRIPT_DEBUG = "invalid_probe_transcript_debug_divergence"
    INVALID_CORRELATION_INVENTORY = "invalid_probe_correlation_inventory_incomplete"
    INVALID_REDACTION_SEAL = "invalid_probe_redaction_or_seal_failure"
    ZED_CLIENT_CRASHED = "stop_probe_zed_client_crashed"
    POST_NEW_PROMPT_UNAVAILABLE = "blocked_probe_post_new_prompt_unavailable"
    DEPENDENCY_UNAVAILABLE = "blocked_probe_dependency_unavailable"
    INFEASIBLE = "infeasible_for_production_target"
    FEASIBLE_CANDIDATE = "feasible_server_side_custody_candidate"


class AttemptKind(StrEnum):
    CORRELATION_CAPTURE = "correlation_capture"
    POST_NEW_PROMPT = "post_new_prompt"


class FailureClass(StrEnum):
    NONE = "none"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class AttemptRecord:
    attempt_id: str
    phase: str
    kind: AttemptKind
    ordinal: int
    failure_class: FailureClass
    reason_code: str | None
    manifest_sha256: str


@dataclass(frozen=True)
class CorrelationSignal:
    field_path: str
    origin: str
    available_before_new_decision: bool
    a_sha256: str | None
    b_sha256: str | None
    c_sha256: str | None
    restart_stable: bool
    fresh_thread_distinct: bool
    thread_specific: bool
    trust_compatible: bool
    protocol_honest: bool
    safely_persistable: bool
    independently_falsifiable: bool
    ancestry_derived: bool
    eligible: bool
    reason_code: str


@dataclass(frozen=True)
class VerificationResult:
    disposition: ProbeDisposition
    reason_codes: Sequence[str]
    verified_artifact_count: int


```

The module also exposes `sha256_file(path: Path) -> str` and
`verify_manifest(path: Path) -> VerificationResult`. Their complete behavior is defined by Task 1;
the implementation must contain executable bodies and no stub return.

The reducer evaluates the `ProbeDisposition` members in declaration order. A lower item is reachable
only when every higher predicate is false. `FEASIBLE_CANDIDATE` additionally requires at least one
eligible signal, a valid B continuation observation, a valid same-workspace C control, successful
message binding, and direct revalidation for any ancestry-dependent candidate. `INFEASIBLE` requires
all validity gates and a complete inventory but no eligible signal. Workspace-only evidence is
infeasible, not invalid.

The verifier derives the two digest relationships rather than trusting manifest booleans:

```text
restart_stable = a_sha256 is not None and a_sha256 == b_sha256
fresh_thread_distinct = c_sha256 is None or c_sha256 != b_sha256
```

It rejects supplied `restart_stable`, `fresh_thread_distinct`, or `eligible` values that disagree
with recomputation. A missing C digest cannot support `FEASIBLE_CANDIDATE` even though the
field-level `fresh_thread_distinct` expression is true, because the reducer separately requires a
valid completed C control for every candidate that survives Task 5 Step 3.

---

### Task 0: Freeze amendment approval, trigger chain, and target preconditions

**Files:**

- Create: `reports/plan-11-7-server-custody-artifacts/trigger-chain.json`
- Create: `reports/plan-11-7-server-custody-artifacts/target-identities.json`
- Create: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Create: `tests/fixtures/evidence/plan117-server-custody-prompt.txt`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Inspect: `docs/superpowers/plans/evidence-handoff-open-work-pool.md`
- Inspect: `README.md`
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Consumes the operator's amendment approval identity + UTC + exact amendment digest from the
  reviewer checkpoint Current State.
- Runs only in the custody-bound `optimus-cost-agent-wt-cursor` worktree after the approved design
  and amendment bytes have been integrated there without relocating its gitignored/untracked
  checkpoint and trigger inputs.
- Produces immutable trigger and target manifests used by every later task.
- Makes no external settings change and launches no Zed process.

- [ ] **Step 1: Verify the branch, checkpoint ruling, and amendment approval triple.**

  Run from the custody-bound Plan 11.7 execution worktree. Do not copy inputs into the current
  directory to make these checks pass:

  ```powershell
  $plan117ExecutionRoot = (Resolve-Path -LiteralPath "D:\Projects\Development\Python\optimus-cost-agent-wt-cursor").Path
  $plan117CurrentRoot = (Resolve-Path -LiteralPath (git rev-parse --show-toplevel)).Path
  if ($plan117CurrentRoot -ne $plan117ExecutionRoot) { throw "wrong Plan 11.7 execution worktree" }
  $plan117Branch = (git branch --show-current).Trim()
  if ($plan117Branch -ne "agent/cursor/p11-feat-zed-resume") { throw "wrong Plan 11.7 execution branch" }
  $plan117CustodyInputs = @(
    "docs/superpowers/reviews/plan-11-7-review-checkpoints.md",
    "reports/plan-11-7-task0-artifacts/step4-discovery/discovery-finding.json",
    "reports/plan-11-7-task0-artifacts/step4-discovery/evidence-report.json"
  )
  foreach ($plan117CustodyInput in $plan117CustodyInputs) {
    if (-not (Test-Path -LiteralPath $plan117CustodyInput -PathType Leaf)) {
      throw "missing existing Plan 11.7 custody input: $plan117CustodyInput"
    }
  }
  git status --short --branch
  git rev-parse HEAD
  git merge-base --is-ancestor d5894e3b29d3d64a8fd2c6810fe2d01058b5bac5 HEAD
  $plan117AncestorExit = $LASTEXITCODE
  $plan117AncestorExit
  if ($plan117AncestorExit -ne 0) { throw "required baseline is not an ancestor" }
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  Get-Content -Raw -LiteralPath "docs/superpowers/reviews/plan-11-7-review-checkpoints.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md"
  ```

  Expected: the resolved root and branch match the custody-bound worktree, all three pre-existing
  custody inputs exist, and `$plan117AncestorExit` prints `0`, proving
  `d5894e3b29d3d64a8fd2c6810fe2d01058b5bac5` is an ancestor; production source diff is empty;
  Current State contains the same approver, UTC, and full amendment SHA-256 printed by
  `Get-FileHash`. If line endings changed after approval, stop; do not normalize and continue.

- [ ] **Step 2: Verify the immutable trigger chain by the specified byte methods.**

  ```powershell
  uv run --frozen python -c "import hashlib,subprocess; p='docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md'; print(hashlib.sha256(subprocess.check_output(['git','show','d5894e3:'+p])).hexdigest().upper())"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/specs/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-design.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "reports/plan-11-7-task0-artifacts/step4-discovery/evidence-report.json"
  (Get-Content -Raw -LiteralPath "reports/plan-11-7-task0-artifacts/step4-discovery/discovery-finding.json" | ConvertFrom-Json).disposition
  ```

  Expected: exact frozen-plan, design, and Step 4 hashes from Global Constraints and exact
  disposition `stop_amend_plan_session_load_unreachable`.

- [ ] **Step 3: Write the prompt fixture and canonical trigger-chain manifest.**

  Write the exact no-BOM prompt bytes and one terminal LF to the fixture and verify the pinned
  SHA-256. Create `trigger-chain.json` with schema `plan117-custody-trigger-v1`, full relative locators,
  digests, hash methods (`git_blob_sha256` or `raw_file_sha256`), discovery disposition, amendment
  approval triple, checkpoint-log locator, baseline commits, and production-source-clean result.
  Initialize the artifact manifest with schema `plan117-custody-artifact-manifest-v1`,
  `checkpoint: task0`, and the trigger, design, frozen-plan, Step 4, and prompt-fixture locators and
  hashes. Store no chat transcript and no secret values.

- [ ] **Step 4: Reacquire exact Zed, Optimus, dependency, registry, and README identities.**

  In the live PowerShell process, assign `$plan117ZedSource` and `$plan117ZedExecutable` as local
  variables from the exact operator-approved paths before running this block. Do not use or set an
  environment variable for either value.

  ```powershell
  $plan117ZedSource = (Resolve-Path -LiteralPath $plan117ZedSource).Path
  $plan117ZedExecutable = (Resolve-Path -LiteralPath $plan117ZedExecutable).Path
  acpx --version
  git -C $plan117ZedSource rev-parse HEAD
  Get-FileHash -Algorithm SHA256 -LiteralPath $plan117ZedExecutable
  Get-Item -LiteralPath $plan117ZedExecutable | Select-Object FullName,@{Name='FileVersion';Expression={$_.VersionInfo.FileVersion}},@{Name='ProductVersion';Expression={$_.VersionInfo.ProductVersion}}
  $plan117UnexpectedEnv = Get-ChildItem Env: | Where-Object Name -Like 'OPTIMUS_PLAN117_*'
  $plan117UnexpectedEnv
  if ($plan117UnexpectedEnv) { throw "OPTIMUS_PLAN117_* must not enter the launch environment" }
  uv run --frozen python -m optimus.acp --check-config --strict --no-auto-start
  Get-Item -LiteralPath "README.md" | Select-Object FullName,Length,Attributes
  Get-FileHash -Algorithm SHA256 -LiteralPath "README.md"
  ```

  `$plan117ZedSource` and `$plan117ZedExecutable` are local PowerShell variables, never environment
  variables. The `OPTIMUS_PLAN117_*` query must print no rows before `--check-config`;
  otherwise stop and clean the inherited environment before retrying. Record Zed launcher,
  registry, source-blob, Optimus executable,
  package/Git, Redis TimeSeries, Gateway host-only, workspace, and README identities in
  `target-identities.json`. Source-blob digests use `git show` with the exact source paths listed in
  Phase 1 of the approved design and every additional source path recorded in the manifest.

  Expected: Zed 1.13.1/product commit and source commit match; README is a readable regular file
  inside the workspace; real dependency checks pass; no credential value is recorded.

- [ ] **Step 5: Refresh the current Plan 11.7 status without claiming probe completion.**

  Update the backlog and roadmap rows to state: Task 0 Steps 1-4 sealed; `session/load` unreachable;
  frozen Plan 11.7 implementation blocked; this standalone amendment approved and probe authorized
  but not yet completed. Inspect the evidence-handoff pool and README and record checked/no-change
  when their current claims remain true. Do not mark the server-side route feasible.

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  git diff --check
  ```

  Expected: document hygiene passes and no current-state document claims Plan 11.7 implementation is
  merely in generic drafting/review.

- [ ] **Step 6: Checkpoint Task 0.**

  ```powershell
  uv run --frozen pytest tests/unit -q
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  Get-FileHash -Algorithm SHA256 -LiteralPath "reports/plan-11-7-server-custody-artifacts/trigger-chain.json"
  Get-FileHash -Algorithm SHA256 -LiteralPath "reports/plan-11-7-server-custody-artifacts/target-identities.json"
  Get-FileHash -Algorithm SHA256 -LiteralPath "tests/fixtures/evidence/plan117-server-custody-prompt.txt"
  ```

  Expected: production source remains unchanged and both manifests are immutable inputs for Task 1.
  Commit only with separate authorization, subject `docs(acp): pin Plan 11.7 custody probe inputs`.

### Task 1: Implement the canonical contract and offline reducer

**Files:**

- Create: `tools/plan117_custody_contract.py`
- Create: `tools/verify_plan117_custody_feasibility.py`
- Create: `tests/unit/tools/test_plan117_custody_contract.py`
- Create: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`

**Interfaces:**

- Produces the exact public enums/dataclasses/signatures under Core interfaces.
- `verify_manifest(path)` performs local file/Git/hash verification only: no network, Redis,
  Gateway, keyring read or write, settings write, process launch, or ambient credential read. Every
  approval fact it checks comes from manifest-recorded, hashed evidence.
- Later tasks append fixture manifests; this task establishes the stable schema and precedence.

- [ ] **Step 1: Write RED schema, hash, eligibility, budget, and precedence tests.**

  Tests must require:

  - strict schema/version and unknown-field rejection;
  - lowercase 64-hex SHA-256 in JSON and case-insensitive comparison to pinned constants;
  - path containment under the supplied report/custody roots;
  - exact 14-value disposition enum and declaration-order precedence;
  - workspace/cwd/recency/PID/title/prompt fields ineligible;
  - ancestry candidates ineligible until direct restart revalidation passes;
  - verifier-derived `restart_stable` and `fresh_thread_distinct` values from the exact digest
    expressions under Core interfaces;
  - independent tamper cases in which each supplied relationship boolean disagrees with its
    recomputed value and is rejected;
  - A/B stability plus C distinction and a separately valid completed C control for feasible
    candidates;
  - complete inventory plus no candidate for infeasible;
  - independent three-attempt budgets and permanent-failure immediate stop;
  - crash precedence over prompt/dependency/infeasible/feasible;
  - settings-restore precedence over crash; and
  - valid `session/new` preservation across later prompt failures.

  Use a table-driven reducer test whose expected order is exactly the Stop taxonomy list in Global
  Constraints; do not duplicate a shorter list in a helper.

- [ ] **Step 2: Run RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_verify_plan117_custody_feasibility.py -q
  ```

  Expected: collection fails because the two tool modules do not exist.

- [ ] **Step 3: Implement strict models, canonical hashing, eligibility, and reducer.**

  Use Pydantic models with `ConfigDict(extra="forbid", frozen=True)`. Hash regular files through
  streaming 1 MiB reads, reject symlinks where a regular evidence file is required, and resolve all
  manifest-relative paths against the manifest directory before containment checks. The reducer
  takes booleans derived by verification, not narrative reason strings, and selects the first true
  disposition predicate in enum order.

  `CorrelationSignal.eligible` must equal the conjunction of all eight design eligibility rules and
  `not ancestry_derived`, unless a separate direct-revalidation artifact names that exact field path
  and passes. Derive `restart_stable` and `fresh_thread_distinct` with the exact expressions under
  Core interfaces. Reject a manifest that supplies either relationship boolean or an `eligible`
  value inconsistent with recomputation.

- [ ] **Step 4: Implement offline manifest verification.**

  The CLI is:

  ```text
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json
  ```

  It verifies trigger/target pins, every referenced digest and method, attempt budgets, A/B/C roles,
  process and interval structure, approval equality, transcript/debug equality, signal eligibility,
  settings restoration, redaction report, document-audit record, and reducer result. It prints one
  canonical JSON summary containing only schema, disposition, safe reason codes, and artifact count.
  On first failure it exits nonzero with a field path and safe reason code, never a raw value.
  Partial manifests require an explicit `--checkpoint task4` or `--checkpoint task5`; omitting the
  option requires the complete final seal and rejects a partial manifest.

- [ ] **Step 5: Run GREEN and coverage.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_verify_plan117_custody_feasibility.py --cov=tools.plan117_custody_contract --cov=tools.verify_plan117_custody_feasibility --cov-report=term-missing -q
  ```

  Expected: all tests pass and both new tool modules have at least 90% line coverage; every reducer
  branch and manifest rejection path is exercised.

- [ ] **Step 6: Checkpoint Task 1.**

  ```powershell
  uv run --frozen python -m ruff check tools/plan117_custody_contract.py tools/verify_plan117_custody_feasibility.py tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_verify_plan117_custody_feasibility.py
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --check
  ```

  Expected: Ruff, the checked-in logging-surface inventory, the full unit suite, and whitespace
  checks pass. Every discovered surface in the two new tool modules has an exact manifest
  classification and resolving unit test node. Commit only with separate authorization, subject
  `test(acp): define Plan 11.7 custody probe contract`.

### Task 2: Implement and prove the opaque relay

**Files:**

- Create: `tools/plan117_custody_relay.py`
- Create: `tests/unit/tools/test_plan117_custody_relay.py`
- Modify: `tools/verify_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`

**Interfaces:**

- CLI: `plan117_custody_relay.py --capture-root ABS --run-id ID --child-executable ABS --` followed
  by the exact original Optimus argument vector captured from the approved registry/settings input.
- Produces private `zed-to-agent.bin`, `agent-to-zed.bin`, and
  `relay-index.ndjson` plus a terminal `relay-summary.json`.
- Launches `[child_executable, *child_args]` with `env=None`, `cwd=None`, binary pipes for stdin/stdout,
  and inherited stderr; returns the child's exit code.
- Never imports ACP models, JSON-RPC handlers, redaction internals, or ambient Optimus configuration.

- [ ] **Step 1: Write RED relay tests.**

  Cover empty streams, all byte values, multi-megabyte chunks, partial lines, concurrent duplex
  chunks, ordering, EOF in either direction, child-first exit, parent-first EOF, backpressure,
  recorder failure, broken pipe, and Ctrl-C termination. Assert:

  - concatenated captured bytes equal input bytes for each direction;
  - forwarded bytes equal captured bytes;
  - the globally increasing index sequence and per-direction offsets are gap-free;
  - each chunk digest matches raw private bytes;
  - stdout contains child stdout only;
  - `Popen` receives `env=None`, `cwd=None`, exact child argv, inherited stderr, and no shell;
  - no relay-only argument reaches the child; and
  - failure never switches to an uncaptured or unverified fallback path.

- [ ] **Step 2: Run RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q
  ```

  Expected: failure because the relay entrypoint does not exist.

- [ ] **Step 3: Implement minimal opaque forwarding and private capture.**

  Use one reader thread per direction and one locked recorder. Each index record has schema,
  run_id, global sequence, direction, monotonic offset from a captured origin, directional byte
  offset, size, and SHA-256. Raw chunks append to direction-specific binary files before their index
  record is fsynced. A recorder error closes the child pipes, terminates only the owned child, emits
  a safe stderr reason code, and exits nonzero. Do not decode bytes in the live path.

- [ ] **Step 4: Extend verifier mutation tests for the relay.**

  Mutate raw bytes, chunk sizes, offsets, sequences, directions, digests, run ID, child argv digest,
  relay digest, and terminal exit record. The verifier must reject each mutation independently and
  reject a capture lacking either directional EOF/terminal disposition.

- [ ] **Step 5: Run GREEN, coverage, and Ruff.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_verify_plan117_custody_feasibility.py --cov=tools.plan117_custody_relay --cov-report=term-missing -q
  uv run --frozen python -m ruff check tools/plan117_custody_relay.py tests/unit/tools/test_plan117_custody_relay.py tools/verify_plan117_custody_feasibility.py tests/unit/tools/test_verify_plan117_custody_feasibility.py
  ```

  Expected: all tests pass; relay line coverage is at least 90%; Ruff is clean.

- [ ] **Step 6: Checkpoint Task 2.**

  Classify every newly discovered relay/verifier persistence or export surface in the checked-in
  logging-surface audit with an exact rationale, sanitizer/policy, resolving unit test node, and
  evidence tier. Then run:

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --check
  ```

  Expected: the audit verifier and full unit suite pass. Record test output and relay file SHA-256
  in a Task 2 checkpoint artifact. Commit only with separate authorization, subject
  `test(acp): add opaque Plan 11.7 custody relay`.

### Task 3: Implement phase orchestration, settings rollback, and independent corroboration

**Files:**

- Create: `tools/run_plan117_custody_feasibility.py`
- Create: `tests/unit/tools/test_run_plan117_custody_feasibility.py`
- Create: `tests/fixtures/evidence/scenarios/plan117-server-custody.toml`
- Modify: `tools/plan117_custody_contract.py`
- Modify: `tools/verify_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_plan117_custody_contract.py`
- Modify: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`

**Interfaces:**

- Phase CLI values: `direct-control`, `relay-control`, `origin-a`, `restart-b`,
  `fresh-control-c`, `direct-ancestry-control`, `restore-settings`, and `finalize`.
- All paths (`--workspace-root`, `--capture-root`, `--zed-executable`, `--zed-source`,
  `--settings-path`, `--debug-log`) are explicit and resolve absolutely before side effects.
- `finalize` additionally requires `--evidence-capture-root` and `--result`; it reads completed
  private attempts, writes the public collector bundle through `evidence_handoff.collector`, and
  never mutates a live capture.
- The runner never sends ACP bytes, keyboard/mouse/UI input, a model prompt, or a client request.
  It prints the exact operator action for content-bearing phases and only observes files/processes.

- [ ] **Step 1: Write RED orchestration tests.**

  Require tests for:

  - path containment and rejection of symlinks/unapproved settings/custody paths;
  - settings pre-image capture, changed-key allowlist, atomic replace, exact restore on success and
    every exception path, and absent-file restoration;
  - refusal to mutate settings without an approval record containing exact path, pre-image digest,
    operator identity, and UTC;
  - phase-order state machine and immutable/non-overwriting attempt directories;
  - separate correlation and prompt ordinals/caps;
  - permanent vs transient classification evidence fields;
  - PowerShell/CIM process records limited to requested PIDs with PID, ParentProcessId,
    CreationDate, ExecutablePath, and safe CommandLine digest;
  - complete process-tree exit before `restart-b`;
  - same durable approval equality across direct/relay launches;
  - completed-copy transcript parsing only after relay termination;
  - exact relay/debug method, ID, order, terminal, and interval agreement;
  - no `acpx`, no project-authored client, no `tools.evidence_gather_support` import, and no UI
    automation/input API; and
  - README precondition and exact prompt-fixture hash.

  Validate the new scenario through the repository's public scenario loader. It requires
  `observation_window_complete`, uses the registered `zed_acp_client`,
  `hermetic_user_data_fixture`, `acp_stream_collector`, `completion_detector`, and
  `crash_detector` adapters, and does not require `completion_observed`; a valid correlation
  infeasibility result may occur before successful model completion.

- [ ] **Step 2: Run RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py -q
  ```

  Expected: failure because the runner entrypoint does not exist.

- [ ] **Step 3: Implement the settings transaction and attempt state machine.**

  `settings.json` changes only the selected external-agent command/args from the exact original
  Optimus command to the relay command. Preserve every unrelated byte semantically by restoring the
  complete pre-image, not by attempting a reverse JSON patch. Store pre-image bytes only in private
  custody; promoted proof contains existence state, pre/mutated/final hashes, and changed JSON-key
  paths. Register restoration in `try/finally` and expose `restore-settings` as an idempotent recovery
  command that first verifies the target path and currently expected mutated digest.

  The phase state file is canonical JSON with `schema=plan117-custody-state-v1`, completed phase list,
  active settings transaction, A/B/C run IDs, per-kind next ordinal, immutable attempt locators, and
  current safe stop code. Atomic replacement is required; an existing attempt directory is fatal.

- [ ] **Step 4: Implement process, launch, transcript, and debug observation.**

  Invoke Windows PowerShell with argument-list subprocess calls and `Get-CimInstance Win32_Process`
  filtered to explicitly resolved PIDs. Normalize only allowlisted process fields; hash command-line
  text rather than promoting it. Capture Zed executable identity separately. Never inspect process
  environments.

  Read the durable approval through existing approval-store code in a read-only path and record only
  approval ID/mode, full security snapshot digest, workspace digest, policy compatibility, and
  record HMAC verification outcome. Compare those fields to append-only launch-audit suffixes for
  direct and relayed runs. Do not write or re-author an approval.

  After relay termination, parse copied directional bytes into NDJSON messages, reject invalid UTF-8
  or framing, and project method, request ID, response/error presence, server-assigned session ID,
  ordered update type, terminal stop/error, content SHA-256, and byte-record references. Compare that
  projection against the immutable Optimus debug suffix; disagreement is
  `invalid_probe_transcript_debug_divergence`.

- [ ] **Step 5: Implement operator instructions and phase-specific safety checks.**

  `origin-a` prints the exact prompt and fixture SHA; `restart-b` prints only the instruction to use
  the prior-thread affordance Zed actually exposes and requires the operator to label whether the UI
  offered prior thread or only “New Optimus Thread”; `fresh-control-c` prints the explicit new-thread
  control instruction. No phase calls `SendInput`, UIA input APIs, clipboard APIs, URI handlers, or
  an ACP client. The runner records operator assertions as asserted observations, not machine proof.

- [ ] **Step 6: Run GREEN, coverage, and static policy scans.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_verify_plan117_custody_feasibility.py --cov=tools.run_plan117_custody_feasibility --cov-report=term-missing -q
  rg -n "SendInput|pyautogui|uiautomation|acpx|evidence_gather_support|session/load" tools/run_plan117_custody_feasibility.py tools/plan117_custody_relay.py
  uv run --frozen python -m ruff check tools/plan117_custody_contract.py tools/plan117_custody_relay.py tools/run_plan117_custody_feasibility.py tools/verify_plan117_custody_feasibility.py tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_verify_plan117_custody_feasibility.py
  ```

  Expected: all tests pass; runner coverage is at least 90%; the `rg` scan reports only explicit
  forbidden-token guards/tests or no matches, never an import/invocation; Ruff is clean.

- [ ] **Step 7: Checkpoint Task 3.**

  Classify every newly discovered runner/contract/verifier persistence or export surface in the
  checked-in logging-surface audit before running this checkpoint.

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  git diff --check
  ```

  Expected: the audit verifier and full unit suite pass and production source remains unchanged.
  Commit only with separate authorization, subject
  `test(acp): orchestrate bounded Zed custody probe`.

### Task 4: Prove direct/relay launch equivalence and capture origin session A

**Files:**

- Create: `reports/plan-11-7-server-custody-artifacts/approval-equivalence.json`
- Create: `reports/plan-11-7-server-custody-artifacts/settings-transaction.json`
- Create: `reports/plan-11-7-server-custody-artifacts/attempts/direct-control-1/`
- Create: `reports/plan-11-7-server-custody-artifacts/attempts/relay-control-1/`
- Create: `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-1/`
- Modify: `reports/plan-11-7-server-custody-artifact-manifest.json`

**Interfaces:**

- Consumes Task 0 identities and Tasks 1-3 tooling.
- Produces environment equivalence and one real Zed-originated origin session with exact message
  custody, or a higher-precedence sealed stop.
- Performs an external settings mutation only after exact operator approval is recorded.

- [ ] **Step 1: Obtain and record external settings-mutation approval.**

  Present the resolved settings path, pre-image existence/hash, exact changed JSON-key paths, relay
  command, protected backup path, and restoration command. Record operator identity and UTC in the
  private run manifest. Without that explicit approval, stop before writing settings.

  In the live PowerShell process, assign the local variables used by the commands below from the
  exact paths in the approved private run manifest: `$plan117Workspace`, `$plan117PrivateRoot`,
  `$plan117ZedExecutable`, `$plan117ZedSource`, `$plan117ZedSettings`, `$plan117DebugLog`, and
  `$plan117UserData`. These are PowerShell variables, not environment variables, and must not be
  exported to Zed, the relay, or Optimus. Before Task 6 also assign `$plan117PromotableRoot`,
  `$plan117StagingRoot`, `$plan117QuarantineRoot`, `$plan117SanitizedRoot`, and `$plan117Result` from
  the private phase state created by the runner.

- [ ] **Step 2: Run direct-control and relay-control phases.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py direct-control --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  uv run --frozen python tools/run_plan117_custody_feasibility.py relay-control --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  Expected: same durable approval ID/mode/full snapshot digest, workspace digest, policy/registry
  versions, setting decisions, propagation names, and `AUTHORIZED`; relay bytes agree with Optimus
  debug for the control; settings restore proof passes after each phase.

- [ ] **Step 3: Run origin A and perform the disclosed operator prompt.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py origin-a --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  The operator opens exactly one new Optimus thread and enters the printed prompt whose hash matches
  the fixture. The runner sends no input. If `initialize` + `session/new` is valid but the prompt
  later times out, retain the valid correlation attempt and use only the separate prompt retry budget
  in the same session.

  Expected: one Zed-originated connection, one server-assigned A session ID, prompt/update/terminal
  response, Gateway usage/cost fields, process chain, relay/debug agreement, and settings restore.

- [ ] **Step 4: Classify every failure before any retry.**

  For each attempt record phase, kind, ordinal, safe reason code, evidence locator, and
  transient/permanent class. Gateway/model timeouts after new-session capture are prompt attempts;
  missing/corrupt relay/debug capture is a correlation-capture failure; a valid Zed omission of
  `session/new` is a behavioral feasibility fact; Zed crash uses the crash stop. Never spend one
  budget on another class.

- [ ] **Step 5: Verify Task 4 artifacts offline.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint task4
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  ```

  Expected: Task 4 partial manifest verifies, settings are restored, production source is clean, and
  no feasibility disposition is emitted before B.

- [ ] **Step 6: Checkpoint Task 4.**

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --check
  ```

  Expected: the audit verifier and full unit suite pass. Preserve exact hashes and independent
  reviewer pickup instructions. Commit promoted Task 4 artifacts only with separate authorization,
  subject `test(acp): capture Plan 11.7 custody origin`.

### Task 5: Test cross-restart correlation with B and conditional fresh control C

**Files:**

- Create: `reports/plan-11-7-server-custody-artifacts/attempts/restart-b-1/`
- Create when required: `reports/plan-11-7-server-custody-artifacts/attempts/fresh-control-c-1/`
- Create when required: `reports/plan-11-7-server-custody-artifacts/attempts/direct-ancestry-control-1/`
- Create: `reports/plan-11-7-server-custody-artifacts/correlation-signal-inventory.json`
- Create: `reports/plan-11-7-server-custody-artifacts/reducer-result.json`
- Modify: `reports/plan-11-7-server-custody-artifact-manifest.json`

**Interfaces:**

- Consumes immutable A, exact target and approval identities, and restored settings proof.
- Produces complete A/B/C field-level signal inventory and one provisional reducer disposition.
- Cannot emit feasible without B, required C, message binding, and any required direct ancestry
  revalidation.

- [ ] **Step 1: Prove complete A process-tree shutdown.**

  Close the entire hermetic Zed tree. Use Task 3 process observation to require every A Zed, relay,
  and Optimus PID/start identity exited. A still-live process invalidates the restart boundary; do
  not relaunch over it.

- [ ] **Step 2: Run restart B without profile or UI injection.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py restart-b --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  The operator uses the prior-thread affordance Zed actually exposes. Record whether a prior thread
  exists or only “New Optimus Thread” is available. Capture all B `initialize` and `session/new`
  fields and launch-context values available to Optimus before the B new-session decision. A new
  thread is labeled fresh, never continuation by intent alone.

- [ ] **Step 3: Build and reduce the complete correlation inventory.**

  For every observed field write origin, availability point, A/B digest, scope/cardinality,
  restart stability, thread specificity, trust compatibility, protocol honesty, safe persistence,
  independent falsifiability, ancestry flag, eligibility, and exact reason code. Explicitly list
  workspace/cwd/project, MCP collection, client/agent identity, model, title, PID/process proximity,
  wall-clock proximity, recency, B server ID, and prompt as ineligible when that is what evidence
  shows. If no candidate survives, emit provisional infeasible reason
  `workspace_only_or_no_restart_discriminator` and skip C.

- [ ] **Step 4: Run same-workspace fresh control C for every surviving candidate.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py fresh-control-c --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  The operator explicitly creates a new thread. The candidate must remain stable A-to-B and differ
  or be absent for C. Shared, recency-selected, post-decision, or user-controlled candidates are
  infeasible. C is mandatory for feasible and forbidden as narrative substitution when no B
  continuation observation exists.

- [ ] **Step 5: Run a direct ancestry control if any candidate depends on topology.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py direct-ancestry-control --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  Expected: only required for an ancestry-dependent candidate. It must repeat the full restart
  without the relay and corroborate through Optimus debug plus OS snapshots. Process proximity alone
  remains ineligible even if repeated.

- [ ] **Step 6: Run the provisional offline reducer.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint task5
  ```

  Expected: one exact provisional disposition according to precedence; no feasible result without
  every positive invariant; prompt blocks/crashes/invalid evidence are not relabeled infeasible.

- [ ] **Step 7: Checkpoint Task 5.**

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  git diff --check
  ```

  Expected: the audit verifier and full unit suite pass. Verify settings restoration and
  production-source cleanliness again. Preserve A/B/C and any direct-control artifact hashes.
  Commit promoted Task 5 artifacts only with separate authorization, subject
  `test(acp): probe Zed restart custody signals`.

### Task 6: Redact, seal, refresh current-state docs, and return to the operator

**Files:**

- Create: `reports/plan-11-7-server-custody-feasibility.md`
- Create: `reports/plan-11-7-server-custody-feasibility.json`
- Create: `reports/plan-11-7-server-custody-artifacts/evidence-report.json`
- Create: `reports/plan-11-7-server-custody-artifacts/document-freshness-audit.json`
- Modify: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Modify: `docs/superpowers/plans/evidence-handoff-open-work-pool.md`
- Inspect and conditionally modify: `README.md`
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Consumes immutable raw/private runs and provisional reducer result.
- Produces one promoted, offline-verifiable seal and a current-state documentation set.
- Stops for independent review and operator verdict; performs no production implementation.

- [ ] **Step 1: Build separate full-private and promotable artifact sets.**

  Full private custody retains raw directional bytes, settings pre-image, raw transcripts, raw debug
  suffixes, process source records, and approval-store corroboration. The promotable set contains
  only normalized structural JSON/NDJSON, safe debug output accepted by the merged gate, digests,
  identities, usage/cost, attempt classifications, and reason codes. Do not copy raw environment
  values, secrets, MCP configuration, prompt/response text, settings bytes, or raw command lines into
  the promotable set.

  Prepare the promotable run through the public entry point, then let the runner's `finalize` phase
  project completed immutable captures through public `evidence_handoff.collector` models and
  `write_raw_bundle`. The runner must not import the `tools.evidence_gather_support` package.

  ```powershell
  uv run --frozen python tools/evidence_gather.py prepare --scenario tests/fixtures/evidence/scenarios/plan117-server-custody.toml --capture-root $plan117PromotableRoot --bind model=operator-supplied
  uv run --frozen python tools/run_plan117_custody_feasibility.py finalize --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --evidence-capture-root $plan117PromotableRoot --result $plan117Result
  ```

  The private phase state supplies the immutable run IDs and artifact locators. `$plan117Result` is
  an evidence-classification result accepted by the merged gate: `indeterminate` for feasible,
  infeasible, dependency, prompt-block, or invalid custody outcomes, and `client_crashed` only when
  correlated Zed panic/process evidence supports `stop_probe_zed_client_crashed`. The probe-specific
  disposition remains in the normalized Plan 11.7 result and reason codes; it does not invent a new
  collector outcome.

- [ ] **Step 2: Invoke only the merged public redaction entry point.**

  ```powershell
  uv run --frozen python tools/evidence_gather.py redact --scenario tests/fixtures/evidence/scenarios/plan117-server-custody.toml --workspace-root $plan117Workspace --user-data-root $plan117UserData --capture-root $plan117PromotableRoot --result $plan117Result --staging-root $plan117StagingRoot --quarantine-root $plan117QuarantineRoot --sanitized-root $plan117SanitizedRoot --report reports/plan-11-7-server-custody-artifacts/evidence-report.json --bind model=operator-supplied
  ```

  Expected: every report-eligible artifact is promoted or the reducer selects
  `invalid_probe_redaction_or_seal_failure`. A quarantined private artifact is never silently omitted
  from the full-private manifest or presented as promoted.

- [ ] **Step 3: Finalize normalized result and human report.**

  `plan-11-7-server-custody-feasibility.json` contains schema, exact disposition, safe reason codes,
  eligible-field paths or complete ineligible inventory summary, A/B/C roles, attempt counts by
  budget, crash/dependency fields, settings-restoration result, artifact-manifest digest,
  evidence-report digest, and `implementation_authorized: false`.

  The Markdown report distinguishes facts from operator assertions and explicitly denies claims of
  resume, `session/load`, rendering, visual presentation, ACP conformance, or build authorization.

- [ ] **Step 4: Run final offline verification and mutation-negative suite.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json
  uv run --frozen pytest tests/unit -q
  ```

  Expected: manifest and every artifact hash verify; all unit/mutation-negative tests pass; printed
  disposition equals the sealed report.

- [ ] **Step 5: Refresh and audit all current-state documentation.**

  Update backlog, roadmap, and evidence-handoff pool with the exact sealed status and operator-return
  gate. Inspect README and either update an affected current-state claim or record checked/no-change.
  Write `document-freshness-audit.json` with each inspected path, claim searched, affected boolean,
  action, and post-change SHA-256. Do not close Plan 11.7 or render-observation custody on a feasible
  candidate; both still require separate approval/implementation.

  ```powershell
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  rg -n "P11-FEAT-ZED-RESUME|Plan 11.7|Zed.*custody|render.*custody" docs/superpowers/plans README.md
  ```

  Expected: living documents agree with the sealed disposition and no stale generic drafting status
  remains.

- [ ] **Step 6: Run repository fitness gates appropriate to probe tooling.**

  ```powershell
  uv run --frozen python -m ruff check .
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_verify_plan117_custody_feasibility.py tests/unit/docs/test_open_work_pool_hygiene.py --cov=tools.plan117_custody_contract --cov=tools.plan117_custody_relay --cov=tools.run_plan117_custody_feasibility --cov=tools.verify_plan117_custody_feasibility --cov-report=term-missing -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  git diff --exit-code 2cf2f42aa7d1072f09d0678a3c75eb43516c8808 -- src/optimus src/optimus_gateway
  git diff --check
  git status --short --branch
  ```

  Expected: Ruff clean; focused coverage tests and the complete unit suite pass; each new probe
  module has at least 90% line coverage; the checked-in logging-surface manifest exactly covers the
  current inventory; production source is unchanged; whitespace and status are reviewable.
  Non-unit integration, live, and E2E tiers run only where their named real dependencies and the
  applicable live steps above require them.

- [ ] **Step 7: Obtain independent review and stop for operator verdict.**

  The reviewer reads the existing checkpoint Current State, recomputes every trigger/target/report
  hash, inspects raw/private custody as authorized, verifies launch equality, process boundaries,
  relay/debug agreement, signal inventory, attempt classification, settings restoration, reducer
  precedence, production-source cleanliness, and document freshness, then records a timestamped
  ruling in the existing checkpoint log.

  The working agent stops. For `feasible_server_side_custody_candidate`, request separate operator
  authorization to draft the production implementation amendment. For infeasible, leave Plan 11.7
  blocked without fallback. For crash/block/invalid, report the earliest stop and request direction.
  Do not begin frozen Task 0 Step 5 or Task 1.

- [ ] **Step 8: Commit only after separate closing authorization.**

  Re-run Step 6 immediately before any commit. If authorized, stage only this amendment's tool,
  test, fixture, promoted report, manifest, and current-state documentation files; never stage the
  gitignored reviewer checkpoint or private custody files. Suggested subject:
  `test(acp): seal Plan 11.7 custody feasibility`.

---

## Definition of Done

This amendment is complete only when every applicable checkbox above is checked by its literal
passing command and all of the following are true:

1. the frozen Plan 11.7 digest and sealed Steps 1-4 evidence remain unchanged;
2. exact amendment approval and settings-mutation approvals are recorded under existing governance;
3. Zed/Optimus identities are recomputed on the exact live target;
4. direct and relayed launches prove equal production security snapshots through the same durable
   approval record;
5. the relay proves opaque bytes in tests and agrees with Optimus debug in each live run;
6. session A, full Zed restart, restart session B, and every required C/direct control are immutable
   and independently verifiable;
7. the complete correlation inventory applies every eligibility rule and fails closed on workspace,
   recency, prompt, PID, title, or ancestry-only evidence;
8. correlation-capture and prompt retry budgets remain separate and every failure classification is
   evidenced;
9. Zed settings are restored exactly and production source is unchanged;
10. the merged redaction path alone produces the promoted seal;
11. the reducer emits exactly one disposition with correct precedence;
12. backlog, roadmap, evidence pool, README audit, and checkpoint state are current; and
13. the worker has stopped for a separate operator verdict with
    `implementation_authorized: false`.

No green fake-based test, narrative claim, or successful single-connection capture can substitute
for the real A/B restart evidence and required same-workspace fresh control.
