# Plan 11.7 Standalone Origin-A Fixture V2 and Attempt-Accounting Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to execute this amendment task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. No checkbox may change until its stated verification command has
> run and passed.

**Goal:** Correct the deterministic origin-A fixture defect without changing Optimus production
behavior, preserve and accurately classify `origin-a-1` and `origin-a-2`, and obtain one real
Gateway-backed origin-A observation through exactly one additional Zed launch, `origin-a-3`.

**Architecture:** Leave frozen Plan 11.7, its approved server-custody amendment, and every existing
attempt artifact byte-for-byte intact. Add append-only superseding classifications and a
stage-aware ledger so one physical run can consume correlation and prompt budgets independently.
Replace the evidentiary stimulus with a pinned root-relative `pyproject.toml` fixture. Before the
last launch, land and independently review the Windows relay partial-read fix and the string-aware
JSONC settings parser fix, pin the exact clean execution commit, and obtain a fresh settings-
mutation approval.

**Tech Stack:** Python 3.12, Pydantic v2, standard-library binary I/O and JSON/JSONC handling,
pytest, pytest-cov/coverage.py, Ruff, Git, Windows PowerShell/Event Log, Redis 8 with TimeSeries,
the real Optimus Gateway, the merged evidence collector/redaction gate, Zed 1.13.1, and Zed source
commit `00bd72e7838f4b875a913cd112b47a0ebe1ca62b`.

**Identity:** This is a second standalone execution amendment to Plan 11.7. It allocates no new
Plan 11.x number, creates no new roadmap lane, remains owned by `P11-FEAT-ZED-RESUME`, and remains
governed by `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`.

**Status:** Draft for independent reviewer and operator approval. Approval authorizes Tasks 0-6
below and, after the separate live settings gate, exactly one new Zed launch named `origin-a-3`.
It does not authorize a fourth correlation launch, production server-side custody, frozen Plan
11.7 Tasks 1-11, or any change under production source roots.

## Global Constraints

- Never edit the frozen Plan 11.7 file
  `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`.
  Its authoritative Git-blob SHA-256 is
  `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D`.
- Never edit the approved parent amendment
  `docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md`.
  Its approved LF-byte SHA-256 is
  `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6`.
- The approved parent design is
  `docs/superpowers/specs/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-design.md`,
  LF-byte SHA-256
  `8808E5212DCDB3B44198096D1A0AFE7E20A53E4A9B28438DA5AA23245D339F0E`.
- The design for this amendment is
  `docs/superpowers/specs/2026-08-02-plan-11-7-origin-a-fixture-v2-and-stage-accounting-design.md`,
  LF-byte SHA-256
  `9ADD264B06B67B7BF6C85A3A1439BFED29F10C08366848761EED9C3D8B624347`.
- The triggering Step 4 disposition remains `stop_amend_plan_session_load_unreachable`; its
  sealed evidence report has raw-byte SHA-256
  `1579A5B1A84F1AE46C0B09B317F61B93D919E5E03725FFA8BD0F9F6BD32565BF`.
- Execution is custody-bound to
  `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor` on branch
  `agent/cursor/p11-feat-zed-resume`. Read the reviewer log Current State before any mutation and
  verify it against the actual worktree and evidence. Never substitute a copied or empty log.
- This amendment requires its own approver identity + UTC + exact LF-byte SHA-256 triple in the
  existing reviewer log. The worker never edits the reviewer-owned log.
- No existing origin attempt file may be changed, moved, renamed, deleted, or regenerated.
  Corrections are new append-only superseding records whose parent hashes match the private raw
  artifacts.
- No lineage or budget resets. `origin-a-1` is correlation capture 1. `origin-a-2` is correlation
  capture 2 and post-new prompt 1. `origin-a-3` is correlation capture 3 and, only after successful
  correlation, post-new prompt 2.
- Exactly one new Zed launch is authorized: `origin-a-3`. A fourth correlation launch requires a
  later budget-expansion amendment and explicit operator approval.
- If `origin-a-3` correlation succeeds but its prompt suffers an evidence-backed transient failure
  while the same session remains alive, one prompt-only retry may consume prompt ordinal 3. It may
  not relaunch Zed or allocate another correlation stage.
- A Zed crash during `origin-a-3`, a permanent prompt failure, an invalid capture, an unavailable
  same live session, or settings restoration failure stops the probe. Do not consume a fourth
  correlation slot.
- The historical prompt remains immutable evidence only. The sole current fixture is UTF-8,
  no-BOM text with exactly one terminal LF:
  `Read ./pyproject.toml and answer with one sentence naming this project. Do not modify files.`
  Its raw-byte SHA-256 is
  `9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50`.
- The current target is the root-relative `pyproject.toml` in the custody-bound workspace. Its
  raw-byte and Git-blob SHA-256 is
  `AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697`.
  Re-hash and require the same value immediately before launch.
- Keep Gateway usage and cost hard. A local refusal, zero-cost result, estimated usage, or missing
  provider fields cannot satisfy corrected origin A.
- Do not change the workspace-reference resolver or any file under `src/optimus`,
  `src/optimus_gateway`, or the pinned Zed source. Tooling changes are restricted to the files
  named in this amendment.
- The relay partial-read correction and JSONC parser correction must be committed, fully tested,
  and independently reviewer-approved before live settings mutation. Neither correction is
  evidence for or against fixture feasibility.
- Pin the exact execution commit and Git-blob digests for the runner, contract, relay, verifier,
  fixture, scenario, and logging-surface manifest before live approval. Do not execute from a dirty
  tree or transient uncommitted code.
- Zed remains the only ACP client. Do not run `acpx` concurrently, author a project ACP client,
  inject UI input, rewrite session IDs, return an old ID from `session/new`, alter Zed profile
  session state, or use timestamp/PID/workspace identity as a unique correlator.
- The relay is never ACP-conformance evidence. Independent real-`acpx` evidence remains mandatory
  for any future production implementation.
- The relay must be byte-opaque and environment-transparent. Its transcript must agree with
  Optimus's independently authored `.optimus/debug-acp.ndjson`. Relay process ancestry is not
  production-representative.
- Live prompt evidence requires real Redis TimeSeries and the real Gateway, using only
  `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` for runtime provider access.
- Before every production launch-gate check, fail closed if any `OPTIMUS_PLAN117_*` environment
  variable exists. Use PowerShell local variables for plan orchestration paths.
- The settings mutation is separately approved external state. Preserve the exact pre-image and
  restore prior existence and bytes on every exit. Restoration failure outranks every other result.
- Raw evidence remains under the approved private custody root. Promotion/redaction occurs only
  through subprocess invocation of `tools/evidence_gather.py redact`; add no plan-specific
  sanitizer and import nothing from `tools.evidence_gather_support`.
- At each task checkpoint run the narrow tests, Ruff, the checked-in logging-surface verifier, the
  complete unit suite, production-source cleanliness, and `git diff --check`.
- Commit, push, PR creation, merge, settings mutation, approval mutation, external issue creation,
  Redis deletion, and branch deletion retain their separate authorization requirements. Never use
  `--no-verify`.

---

## Effect on the approved parent amendment

Approval of this file temporarily supersedes only the parent amendment's origin-A fixture and Task
4 attempt/accounting sequence:

1. parent Tasks 0-3 and their existing evidence remain historical inputs and are not rerun to
   manufacture progress;
2. parent Task 4's original attempts remain immutable and are normalized only through the
   append-only records required here;
3. the parent Task 4 prompt is replaced prospectively by the exact v2 fixture only;
4. the parent crash stop remains true for origin-a-2, with one explicit corrected-stimulus
   exception authorizing only `origin-a-3`;
5. parent Task 5 remains blocked until this amendment's corrected origin-A evidence is sealed and
   independently accepted; and
6. if corrected origin A succeeds, the reviewer may return execution to parent Task 5 under the
   already-approved parent probe. If it stops, the result returns to the operator without an
   optimistic fallback.

The owner remains `P11-FEAT-ZED-RESUME`; no deferred work is left unnamed.

## File and responsibility map

| File | Responsibility |
|---|---|
| `tools/plan117_custody_contract.py` | Add immutable supersession schema, stage-aware attempt ledger, independent budget derivation, and fail-closed validation |
| `tools/plan117_custody_relay.py` | Land the Windows partial-read-safe full-duplex relay correction without byte mutation |
| `tools/run_plan117_custody_feasibility.py` | Use fixture v2, safe JSONC parsing, exact `origin-a-3` allocation, stage writes, prompt-only retry, and settings rollback |
| `tools/verify_plan117_custody_feasibility.py` | Offline verification of supersession chains, stage budgets, fixture/target identity, exact execution identity, live capture, and stop precedence |
| `tests/unit/tools/test_plan117_custody_contract.py` | Supersession, dual-stage, no-reset, cap, order, cycle/fork, and reason/evidence tests |
| `tests/unit/tools/test_plan117_custody_relay.py` | Windows partial-read, equality, ordering, EOF, failure, argv/env/cwd, and debug-corroboration tests |
| `tests/unit/tools/test_run_plan117_custody_feasibility.py` | Fixture v2, resolver preflight, JSONC safety, exact allocation, prompt-only retry, settings rollback, and launch guards |
| `tests/unit/tools/test_verify_plan117_custody_feasibility.py` | Positive amended fixture and tamper tests for every new evidence and precedence field |
| `tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt` | Exact approved v2 prompt; do not overwrite the historical v1 fixture |
| `tests/fixtures/evidence/scenarios/plan117-server-custody.toml` | Extend only as needed to promote safe supersession, stage, and corrected origin evidence |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Classify every added or changed persistence/export sink with resolving tests |
| `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/trigger-chain.json` | Parent/amendment/design approvals, original attempt hashes, fixture/target identities, and custody binding |
| `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/stage-ledger.json` | Canonical normalized correlation and prompt accounting across all origin-A runs |
| `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/` | Append-only safe origin-a-1 and origin-a-2 correction records |
| `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/` | Promoted safe artifacts for the sole new Zed launch |
| `reports/plan-11-7-server-custody-artifact-manifest.json` | Append new locators/hashes; retain all existing entries and identities |
| `reports/plan-11-7-server-custody-feasibility.json` | Normalized result after corrected origin A and later parent phases |
| `reports/plan-11-7-server-custody-feasibility.md` | Human-readable immutable history, correction, accounting, result, and limitations |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Current Plan 11.7 execution/amendment state |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Current active-slice and corrected-probe dependency |
| `docs/superpowers/plans/evidence-handoff-open-work-pool.md` | Inspect and update only if its Plan 11.7 dependency claim is stale |
| `README.md` | Inspect and update only if an existing current-state claim becomes stale |

## Required interfaces

The contract must represent a physical run and each independently budgeted stage. Exact class names
may follow the parent module's established naming, but the serialized schema and behavior are
mandatory:

```python
class StageKind(StrEnum):
    CORRELATION_CAPTURE = "correlation_capture"
    POST_NEW_PROMPT = "post_new_prompt"


class StageStatus(StrEnum):
    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class EvidenceReference:
    relative_path: str
    sha256: str
    hash_method: str


@dataclass(frozen=True)
class StageAttemptRecord:
    record_id: str
    run_attempt_id: str
    stage: StageKind
    ordinal: int
    status: StageStatus
    failure_class: FailureClass
    reason_code: str | None
    evidence: tuple[EvidenceReference, ...]
    supersedes_record_id: str | None
    supersedes_sha256: str | None
    amendment_sha256: str
    created_by: str
    created_utc: str
```

Client/process facts that occur after a stage boundary use a separate immutable supplemental fact
record rather than falsifying either stage outcome. Its serialized fields are `record_id`,
`run_attempt_id`, `fact_kind`, `reason_code`, ordered `evidence`, `supersedes_record_id`,
`supersedes_sha256`, `amendment_sha256`, `created_by`, and `created_utc`. For origin-a-2,
`fact_kind` is `zed_client_crash`, the safe reason is `stop_probe_zed_client_crashed`, and the
evidence records `0xc0000409`, the bounded Windows event identity, its order after the prompt
refusal, and the absent relay-summary state. The fact neither changes correlation success nor
reclassifies the prompt failure.

The module exposes pure offline operations equivalent to:

```python
def normalize_stage_ledger(records: Sequence[StageAttemptRecord]) -> StageLedger: ...
def next_stage_ordinal(ledger: StageLedger, stage: StageKind) -> int: ...
def verify_supersession_chain(records: Sequence[StageAttemptRecord]) -> None: ...
```

Required behavior:

- a physical run may own at most one terminal record for each stage after supersession;
- stage ordinals are monotonic, unique within a stage, and cannot be reclaimed;
- supersession cites the exact predecessor ID and raw-byte SHA-256;
- cycles, forks, missing parents, mismatched hashes, duplicate terminal classifications, ordinal
  gaps, and amendment-digest mismatches fail closed;
- a successful correlation stage followed by a failed prompt stage consumes both ordinals;
- prompt-only retry requires a proven live session identity and allocates no correlation stage;
- `origin-a-3` is rejected unless it is correlation ordinal 3;
- any new physical run after `origin-a-3` is rejected under this amendment; and
- the allocator writes an immutable reservation before launch and a stage outcome after evidence is
  captured, without rewriting the reservation.

The runner adds or preserves these explicit CLI boundaries:

```text
origin-a --expected-run-attempt-id origin-a-3 --prompt-fixture <v2-path>
origin-a-prompt-retry --run-attempt-id origin-a-3 --prompt-fixture <v2-path>
```

The first command fails before settings mutation unless the ledger derives correlation ordinal 3,
the prompt fixture/target hashes match, and no `origin-a-3` reservation or launch already exists.
The second command fails unless correlation for `origin-a-3` succeeded, prompt ordinal 2 is an
evidence-backed transient failure, the exact Zed/ACP session remains live, and prompt ordinal 3 is
unused. It never launches Zed and never reapplies settings.

---

### Task 0: Freeze the amendment approval, custody inputs, and corrected stimulus

**Files:**

- Create: `tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt`
- Create: `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/trigger-chain.json`
- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Inspect: `docs/superpowers/plans/evidence-handoff-open-work-pool.md`
- Inspect: `README.md`
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Runs only in the custody-bound worktree.
- Reads the new identity + UTC + amendment-digest approval triple from the reviewer log.
- Freezes exact originals and current stimulus without launching Zed or mutating settings.

- [ ] **Step 1: Verify custody, branch, clean parent documents, and approval.**

  Confirm the resolved repository root is the custody-bound worktree, branch is the assigned Plan
  11.7 branch, the checkpoint Current State names this amendment and its exact LF-byte digest, and
  the parent documents still match their pinned bytes. Stop on any mismatch; do not normalize line
  endings or reconstruct evidence.

  ```powershell
  $plan117ExecutionRoot = (Resolve-Path -LiteralPath "D:\Projects\Development\Python\optimus-cost-agent-wt-cursor").Path
  $plan117CurrentRoot = (Resolve-Path -LiteralPath (git rev-parse --show-toplevel)).Path
  if ($plan117ExecutionRoot -ne $plan117CurrentRoot) { throw "wrong Plan 11.7 custody worktree" }
  git branch --show-current
  git status --short
  Get-Content -LiteralPath "docs/superpowers/reviews/plan-11-7-review-checkpoints.md" -TotalCount 120
  uv run --frozen python -c "import hashlib,subprocess; print(hashlib.sha256(subprocess.check_output(['git','show','HEAD:docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md'])).hexdigest().upper())"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/specs/2026-08-02-plan-11-7-origin-a-fixture-v2-and-stage-accounting-design.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md"
  ```

  Expected: custody path and branch match; the known pre-existing Plan 11.7 execution changes are
  visible and preserved; all pinned digests and the new approval triple match exactly. A dirty tree
  is allowed at this intake step only because the parent probe already has reviewed work in
  progress; no live execution is allowed until Task 4 proves a clean commit.

- [ ] **Step 2: Hash and freeze every original attempt input before adding records.**

  Hash the private `origin-a-1` and `origin-a-2` manifests, observations, byte streams, indexes, and
  the missing/present summary state. Record raw size and hash method. Export the bounded Windows
  Application Event Log window needed to prove the distinct crash histories into private custody,
  hash it, and record only safe normalized event facts in promoted evidence.

  Expected original hashes are those listed in the approved design. Any mismatch or unexpected
  `relay-summary.json` stops before mutation and returns to the reviewer.

- [ ] **Step 3: Create and verify the v2 fixture without overwriting v1.**

  Create `plan117-server-custody-prompt-v2.txt` as UTF-8 without BOM, LF-only, exactly one terminal
  LF, and no other bytes. Re-hash the actual root `pyproject.toml`, require the pinned digest and a
  readable regular file within the authorized workspace, and exercise the existing resolver
  preflight to prove exact root-relative resolution within the file-size budget.

  ```powershell
  Get-FileHash -Algorithm SHA256 -LiteralPath "tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt"
  Get-FileHash -Algorithm SHA256 -LiteralPath "pyproject.toml"
  ```

  Expected: fixture is
  `9195EFEEE3A2180CFB85EDE409FF7785F159F64E36426DCDB369251560E28A50`; target is
  `AE28C0C3776F6B78DF23E86FC0E88B0088FEBB7241A04650C604D713E23EF697`; resolution is exact
  `pyproject.toml`; no Gateway, Zed, settings, or product-source action occurs.

- [ ] **Step 4: Write the amendment trigger manifest and current-state docs.**

  Record parent/design/amendment approvals, custody path/branch, original artifact locators and
  hashes, historical and v2 fixture identities, target identity, fixed budget table, and production
  source tree IDs. Append the manifest locator/hash to the existing artifact manifest; never
  rewrite an existing entry. Update roadmap/backlog state to "approved correction pending" only if
  the new approval exists. Audit the open-work pool and README for current-state claims.

- [ ] **Step 5: Verify Task 0.**

  ```powershell
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: all gates pass, originals are untouched, fixture v2 and trigger manifest match pinned
  bytes, and no live process or settings mutation occurred.

### Task 1: Implement stage-aware accounting and append-only supersession test-first

**Files:**

- Modify: `tools/plan117_custody_contract.py`
- Modify: `tools/run_plan117_custody_feasibility.py`
- Modify: `tools/verify_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_plan117_custody_contract.py`
- Modify: `tests/unit/tools/test_run_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`

**Interfaces:**

- Implements the Required interfaces above without touching production source.
- Separates physical-run reservation, correlation outcome, and prompt outcome.
- Treats original files as immutable parents of new records.

- [ ] **Step 1: Add failing contract tests for the settled accounting.**

  Tests must prove the fixed origin-a-1/origin-a-2 ledger, one physical run consuming both stages,
  no reclaimed ordinal, `origin-a-3` as final correlation ordinal, same-session prompt-only retry,
  no fourth launch, immutable reservations, and rejection of gaps, duplicates, forks, cycles,
  missing/mismatched parents, hash mismatch, unsupported reason codes, or wrong amendment digest.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py -q
  ```

  Expected before implementation: new tests fail for missing stage/supersession behavior. Record the
  RED output in the task checkpoint; an import failure alone is insufficient if it bypasses the
  behavior assertion.

- [ ] **Step 2: Implement the minimum pure contract and ledger.**

  Add immutable types, canonical serialization, record hashing, chain validation, normalized stage
  derivation, and independent next-ordinal computation. Preserve the parent contract's disposition
  precedence. Do not infer outcomes from directory names when a terminal stage record exists.

- [ ] **Step 3: Add failing runner and verifier tests.**

  Cover reservation-before-launch, exact expected run ID, refusal to reuse `origin-a-3`, prompt-only
  retry without settings/launch, required live-session proof, original-hash verification, absence
  of writes to original directories, and fail-closed verifier behavior for every new field.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_verify_plan117_custody_feasibility.py -q
  ```

  Expected before implementation: new behavior tests fail for the intended missing contract.

- [ ] **Step 4: Implement runner/verifier integration and atomic append-only writes.**

  Use exclusive creation or the project's existing atomic no-overwrite primitive for reservations,
  stage outcomes, and supersessions. The verifier remains offline-only and performs no keyring read
  or write, launch, settings access, Redis mutation, or Gateway request.

- [ ] **Step 5: Update logging-surface custody and verify Task 1.**

  Classify every new path-writing or projection surface with its policy, safe output, resolving test
  node, and rationale.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_verify_plan117_custody_feasibility.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: all stage, supersession, tamper, logging, full-unit, and Ruff gates pass; no original
  evidence or production source changed.

### Task 2: Land the relay and JSONC safety corrections under separate review

**Files:**

- Modify: `tools/plan117_custody_relay.py`
- Modify: `tools/run_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_plan117_custody_relay.py`
- Modify: `tests/unit/tools/test_run_plan117_custody_feasibility.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json`

**Interfaces:**

- Resolves two tooling safety defects before live execution.
- Produces reviewable code/tests only; it does not run Zed or mutate settings.
- Keeps the safety conclusions separate from the fixture feasibility conclusion.

- [ ] **Step 1: Preserve and reconcile the existing relay working-tree correction.**

  Inspect the current uncommitted relay and tests before editing. Do not discard or overwrite
  another worker's changes. Bind the partial-read correction to the reviewer checkpoint ruling and
  demonstrate that its regression test fails against the pre-fix relay behavior, using an isolated
  non-custody test copy if necessary rather than reverting the shared worktree.

  Tests must prove partial reads, full byte equality, direction/order/index agreement, EOF and child
  exit handling, exception propagation, unchanged child argv/environment/cwd, no buffering-induced
  deadlock, and independent debug-corroboration compatibility.

- [ ] **Step 2: Add failing JSONC corruption tests before changing the parser.**

  Required cases include commented-file fallback with `",}"` and `", ]"` inside strings, escaped
  quotes and backslashes, line/block comment markers inside strings, real trailing commas outside
  strings, comment-free strict JSON bypass, malformed JSONC failure, exact round-trip semantic
  values, and exact settings pre-image restoration after mutation-window failure.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py -q
  ```

  Expected before the parser correction: at least the realistic commented settings regression
  fails by showing silent string-value corruption.

- [ ] **Step 3: Implement the minimum string-aware JSONC correction.**

  Make trailing-comma removal track string/escape state and remove commas only when outside a string
  and followed by a structural `}` or `]` after permitted whitespace/comments. Preserve strict JSON
  fast-path behavior and fail closed on malformed input. Do not introduce a general parser
  dependency or change unrelated settings semantics.

- [ ] **Step 4: Verify platform-shaped safety and all project gates.**

  Run the relay and settings tests on the real Windows host. If any behavior is plausibly
  OS-shaped beyond Windows, also use the project-approved WSL2 alternate-OS procedure before review.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_run_plan117_custody_feasibility.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: all tests and audits pass; hostile JSONC string values remain exact; relay bytes remain
  exact; no settings or Zed process was touched.

- [ ] **Step 5: Obtain an independent tooling review checkpoint.**

  Present the pre-fix failures, diff, platform results, source-cleanliness proof, and exact affected
  files. The reviewer records separate conclusions for relay safety and JSONC safety. Do not proceed
  if either is merely "present" rather than proven and approved.

### Task 3: Append the origin-a-1 and origin-a-2 superseding classifications

**Files:**

- Create:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/origin-a-1-correlation.json`
- Create:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/origin-a-2-correlation.json`
- Create:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/origin-a-2-prompt.json`
- Create:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/supersessions/origin-a-2-client.json`
- Create: `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/stage-ledger.json`
- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Modify: `reports/plan-11-7-server-custody-feasibility.md`
- Modify: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`

**Interfaces:**

- Consumes only frozen private originals and Tasks 0-2 tooling.
- Creates normalized promoted records without raw transcript content or overwritten history.
- Launches no process and mutates no settings.

- [ ] **Step 1: Write origin-a-1's tooling-failure supersession.**

  Cite all five pinned origin-a-1 hashes. Classify correlation ordinal 1 as failed with
  `invalid_probe_relay_capture_tooling_failure`; record the full-duplex relay deadlock, forced
  termination, empty capture, and absence of a matching Zed crash event. State explicitly that no
  prompt stage started and the attempt is not product infeasibility evidence.

- [ ] **Step 2: Write origin-a-2's three fact records.**

  Cite all pinned origin-a-2 hashes and the absent summary. Record correlation ordinal 2 as
  succeeded with valid `initialize`/`session/new`, index, byte consistency, and independent debug
  agreement. Record prompt ordinal 1 as a permanent stimulus failure before Gateway with
  `AMBIGUOUS_WORKSPACE_REFERENCE`. Record the later real Zed crash `0xc0000409` and missing relay
  summary without changing either stage fact.

- [ ] **Step 3: Materialize and independently recompute the stage ledger.**

  The promoted ledger must derive, not assert, that the next correlation ordinal is 3 and the next
  prompt ordinal is 2. It must reject any supplied budget count that disagrees with record-derived
  values. It must bind every supersession to this amendment digest.

- [ ] **Step 4: Add tamper tests and verify the amended checkpoint.**

  Include tests that reject a falsely restored correlation slot, missing crash fact, changed
  original hash, replaced original file, prompt-only origin-a-1 record, missing origin-a-2
  correlation success, and a ledger that allocates `origin-a-4`.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_verify_plan117_custody_feasibility.py -q
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-fixture-v2-classifications
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: classifications, immutable parents, stage ledger, full unit suite, logging inventory,
  and Ruff pass; no live result or feasibility disposition is inferred from the corrected records.

### Task 4: Freeze a clean execution commit and obtain the two live gates

**Files:**

- Create private: exact execution-identity and settings-approval records
- Create promoted:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/execution-preflight.json`
- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Converts Tasks 0-3 into one exact reviewed commit before any live action.
- Obtains a fresh settings approval only after the execution bytes are fixed.
- Does not itself launch Zed.

- [ ] **Step 1: Run final code and evidence review before commit.**

  Reviewer verifies the full diff, RED/GREEN evidence, original-attempt hashes, ledger, fixture,
  target, JSONC/relay fixes, logging surfaces, redaction boundary, and production-source
  cleanliness. Resolve every actionable finding and rerun its affected gates.

- [ ] **Step 2: Commit the exact probe correction only with separate authorization.**

  Stage only the named tooling, tests, fixture, safe promoted amendment records/manifests, and
  current-state docs. Never stage the gitignored reviewer log, private custody files, raw
  transcripts, raw environment/process data, credentials, settings backup, or unrelated changes.

  Suggested subject: `test(acp): amend Plan 11.7 origin fixture accounting`.

- [ ] **Step 3: Prove the committed execution identity and clean tree.**

  Record the exact commit and Git-blob SHA-256 for every execution tool, test, fixture, scenario,
  and logging manifest. Re-hash installed Zed and pinned source. Capture production source tree IDs
  and prove they match Task 0. Fail if the execution files are dirty or if any untracked executable
  dependency is in the launch path.

  ```powershell
  git status --short
  git rev-parse HEAD
  git ls-files --error-unmatch tools/plan117_custody_contract.py tools/plan117_custody_relay.py tools/run_plan117_custody_feasibility.py tools/verify_plan117_custody_feasibility.py tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-fixture-v2-preflight
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: worktree is clean; all execution files are tracked at one commit; all verification
  gates pass; production source and target identities match; the reviewer records approval of this
  exact execution identity.

- [ ] **Step 4: Obtain fresh operator approval for one settings mutation.**

  Present the settings path, existence, exact pre-image hash, exact changed JSON-key paths, protected
  backup path, exact execution commit and tool/fixture digests, exact `origin-a-3` command, and exact
  restoration command. The private record contains approver identity and UTC. This approval permits
  one settings transaction and one Zed launch only. Prior approval is not reused.

- [ ] **Step 5: Run the non-mutating final preflight immediately before live execution.**

  Require real Redis TimeSeries and Gateway readiness, durable launch approval, Zed identities,
  target and fixture digests, no conflicting Zed/relay/Optimus processes, available private custody
  root, and absence of `OPTIMUS_PLAN117_*` environment names before `--check-config`.

  Expected: preflight is fully green. Any mismatch expires the live approval inputs and returns to
  the operator; do not repair it during the mutation window.

### Task 5: Execute exactly one corrected origin-A launch

**Files:**

- Create private: immutable `origin-a-3` reservation, raw relay streams/index, debug suffix,
  process/launch records, settings transaction, stage outcomes, Gateway evidence, and optional
  same-session prompt-only retry
- Create promoted: `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/`
- Modify append-only:
  `reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/stage-ledger.json`
- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`

**Interfaces:**

- Consumes the exact Task 4 execution identity and live approval.
- Launches Zed once and only once.
- Sends no prompt itself; the operator enters the printed exact fixture in the disclosed Zed UI.

- [ ] **Step 1: Reserve `origin-a-3` before settings mutation.**

  Atomically create the immutable physical-run reservation and correlation-stage reservation.
  Recompute the ledger and require correlation ordinal 3 and prompt ordinal 2. Fail if any
  `origin-a-3` artifact/reservation exists or the remaining budget differs. Reservation failure
  must leave settings untouched.

- [ ] **Step 2: Run the approved origin-a-3 command once.**

  Assign approved paths to local PowerShell variables without exporting them, then run:

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py origin-a --expected-run-attempt-id origin-a-3 --prompt-fixture tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --zed-executable $plan117ZedExecutable --zed-source $plan117ZedSource --settings-path $plan117ZedSettings --debug-log $plan117DebugLog
  ```

  The operator opens exactly one new Optimus thread in Zed and enters only the printed prompt after
  its displayed digest matches the approved fixture. The runner performs no UI input. Do not rerun
  this command for any outcome.

- [ ] **Step 3: Restore settings and classify correlation before considering the prompt.**

  Restore exact prior existence and bytes in `finally` handling for success, failure, timeout,
  forced termination, and crash. Verify restoration independently. Then finalize correlation
  ordinal 3 using relay/index/debug/process evidence. Settings restoration failure outranks all;
  invalid correlation or Zed crash stops with no retry.

- [ ] **Step 4: Require a real Gateway-backed prompt result.**

  On successful correlation, finalize prompt ordinal 2. A success requires exact v2 prompt/target
  binding, Gateway request identity, provider/model identity, provider-reported token usage and
  cost, response binding, terminal ACP response, and relay/debug byte agreement. A local refusal or
  zero/missing/estimated usage is not success.

- [ ] **Step 5: Allow at most one same-session prompt-only retry when proven eligible.**

  Only an evidence-backed transient prompt failure with the exact Zed process, connection, and ACP
  session still alive may allocate prompt ordinal 3. Recompute the ledger and run:

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py origin-a-prompt-retry --run-attempt-id origin-a-3 --prompt-fixture tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --debug-log $plan117DebugLog
  ```

  This command must not launch Zed, mutate settings, allocate correlation ordinal 4, or change the
  session. If liveness/identity is not exact, stop. Permanent failure, Zed crash, or second prompt
  failure stops.

- [ ] **Step 6: Verify the live attempt offline before promotion.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-3
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git status --short
  git diff --check
  ```

  Expected for success: one and only one new Zed launch, successful correlation ordinal 3, prompt
  ordinal 2 or allowed same-session ordinal 3, hard Gateway fields, exact restoration, independent
  debug corroboration, and no production-source change. Any stop is preserved as a valid sealed
  ending, not retried through a new launch.

### Task 6: Redact, seal, audit current state, and return to review

**Files:**

- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Modify: `reports/plan-11-7-server-custody-feasibility.md`
- Modify when a normalized result is now valid: `reports/plan-11-7-server-custody-feasibility.json`
- Create/modify through public collector only: `reports/plan-11-7-server-custody-artifacts/`
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- Inspect/update if stale: `docs/superpowers/plans/evidence-handoff-open-work-pool.md`
- Inspect/update if stale: `README.md`
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`

**Interfaces:**

- Promotes only normalized safe evidence through the merged public collector.
- Preserves raw evidence and settings material in private custody.
- Returns corrected origin A to the independent reviewer before parent Task 5.

- [ ] **Step 1: Prepare and redact through the public entry point only.**

  Use the parent amendment's approved scenario and operator-bound paths. Invoke
  `tools/evidence_gather.py prepare` and `tools/evidence_gather.py redact` as subprocess commands.
  Do not import support modules or add a plan-specific sanitizer. Quarantine on any redaction,
  completeness, hash, or policy failure.

- [ ] **Step 2: Seal the append-only chain and normalized report.**

  Include the amendment/design approvals, exact execution identity, v1 history, v2 fixture/target,
  all supersessions, stage ledger, one-launch proof, prompt-only retry status, settings restoration,
  relay/debug agreement, Gateway usage/cost, stop/success classification, limitations, artifact
  locators, raw/promoted hash methods, and redaction report digest. Never copy secrets, raw prompts
  beyond the approved fixture, raw environment, or private settings bytes into promoted output.

- [ ] **Step 3: Run the final offline and project gates.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-fixture-v2-final
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: verifier accepts the immutable chain and exact budgets; logging inventory, full unit
  suite, Ruff, whitespace, redaction, restoration, and production-source gates pass.

- [ ] **Step 4: Perform the documentation freshness audit.**

  Review every document claiming current Plan 11.7 state, including the backlog, roadmap, open-work
  pool, parent feasibility report, and README. Record corrected origin A as awaiting independent
  review, stopped, or accepted. Do not mark the parent feasibility probe complete and do not unblock
  frozen Plan 11.7 implementation work.

- [ ] **Step 5: Obtain independent reviewer acceptance and operator return.**

  The reviewer verifies on-disk hashes, immutable originals, supersession chain, stage accounting,
  execution commit, one-launch proof, no fourth allocation, Gateway fields, settings restoration,
  redaction, and docs freshness. The reviewer records the ruling in the existing checkpoint log.

  - If corrected origin A is accepted, execution may return to parent amendment Task 5 only after
    the reviewer records that transition.
  - If the run stopped or is invalid, feasibility remains undecided and returns to the operator.
  - No result authorizes production server-side custody or changes frozen Plan 11.7.

- [ ] **Step 6: Commit or publish only with separate authorization.**

  Stage only named tracked safe artifacts and documentation. Never stage the checkpoint log,
  private custody files, settings pre-images, raw transcripts/environment, credentials, or unrelated
  work. Run Ruff and all final gates again immediately before any authorized commit or push.

---

## Stop taxonomy and precedence

The verifier preserves all parent stop codes and adds these amendment-specific safe codes:

| Code | Meaning |
|---|---|
| `invalid_probe_origin_attempt_original_mismatch` | An immutable original locator, size, presence state, or raw hash differs |
| `invalid_probe_attempt_supersession_chain` | Supersession has a missing/mismatched parent, cycle, fork, duplicate terminal record, or wrong amendment digest |
| `invalid_probe_stage_accounting` | Stage ordinal, status, physical-run binding, or derived budget disagrees |
| `invalid_probe_retry_budget_exhausted` | A command would allocate correlation ordinal 4 or prompt ordinal above 3 |
| `invalid_probe_fixture_identity_mismatch` | V2 fixture bytes/hash or target bytes/hash/resolution differ |
| `invalid_probe_relay_capture_tooling_failure` | Relay failed to capture faithfully; this classifies origin-a-1 and is not product infeasibility |
| `invalid_probe_execution_identity_mismatch` | Live tools/fixture/scenario are dirty, untracked, or differ from reviewed commit digests |
| `invalid_probe_jsonc_settings_safety` | Parser safety gate or semantic preservation proof fails before settings mutation |
| `blocked_probe_same_session_prompt_retry_unavailable` | Prompt was transient but the exact live session cannot be proven; no relaunch is allowed |
| `blocked_probe_gateway_usage_cost_unavailable` | A terminal response lacks required real provider-reported usage/cost evidence |

Precedence is:

1. trigger/amendment/original/execution/target/fixture identity invalid;
2. settings not exactly restored;
3. non-Zed traffic, launch-approval/environment, process, relay/debug/transcript, redaction, or
   custody invalid;
4. Zed client crash;
5. supersession, stage accounting, or retry-budget invalid;
6. permanent prompt/dependency failure or unavailable same-session retry;
7. evidence-backed transient prompt failure eligible for the one same-session retry; and
8. successful corrected origin A with hard Gateway evidence.

No lower outcome is emitted while a higher predicate is true. `origin-a-1`'s corrected tooling code
does not retroactively make it a valid correlation capture. `origin-a-2`'s successful correlation
does not erase its prompt failure or later crash. The one corrected-stimulus exception is exhausted
when `origin-a-3` is launched, whatever its result.

## Definition of Done

This amendment is complete only when all of the following are independently verified:

- the new approval triple matches this file's exact LF bytes;
- parent/frozen files and all original attempt artifacts retain their pinned identities;
- fixture v2 and root `pyproject.toml` match their exact hashes and resolve unambiguously within
  budget;
- origin-a-1 and origin-a-2 are classified through append-only evidence-bound records;
- the normalized ledger derives correlation ordinals 1-3 and prompt ordinals without reset;
- relay and JSONC safety fixes are test-first, committed, and separately reviewer-approved;
- the execution tree is clean and every live dependency is pinned to one reviewed commit;
- fresh settings approval is bound to those exact bytes;
- no more than one new Zed launch occurred and no correlation ordinal 4 exists;
- any prompt-only retry reused the exact live `origin-a-3` session and did not mutate settings;
- a successful prompt contains real provider-reported Gateway usage/cost and full custody binding;
- settings restoration, redaction, logging-surface, full unit, Ruff, production-source, and
  documentation freshness gates pass; and
- the independent reviewer records whether parent Task 5 may resume or the result returns to the
  operator.

Completion of this amendment never constitutes approval to build server-side custody.
