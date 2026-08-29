# Plan 11.7 Retry Preflight Gate and Live Session Proof Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to execute this amendment task-by-task. Steps use checkbox
> (`- [ ]`) syntax for tracking. No checkbox may change until its stated verification command has
> run and passed.

**Goal:** Make the Plan 11.7 `origin-a-prompt-retry` command execute the real stage-ledger and
`assert_prompt_retry_preflight` gate, using a live proof from the exact Zed/relay/ACP session before
allowing one prompt-only retry.

**Architecture:** Preserve the frozen Plan 11.7 and both 2026-08-02 origin-A amendments. Add a
paired design-defined, private relay control path that returns a current `LiveSessionProof` from the
active Zed process, relay connection, and observed ACP session. Wire the retry CLI in the order
ledger -> fixture/target identity -> live proof -> pure preflight -> immutable prompt reservation
-> existing-session prompt. A proof failure stops before reservation and never relaunches Zed.

**Tech Stack:** Python 3.12, standard-library subprocess/process observation and Windows named-pipe
or AF_PIPE control, Pydantic v2 or the existing custody contract types, pytest, pytest-asyncio,
pytest-cov/coverage.py, Ruff, Git, Windows PowerShell/Event Log, Redis 8 with TimeSeries, the real
Optimus Gateway, the merged evidence collector/redaction gate, Zed 1.13.1, and the pinned Zed source
commit from the approved parent amendment.

**Identity:** This is a standalone execution amendment owned by `P11-FEAT-ZED-RESUME`. It allocates
no new Plan 11.x number and is tracked first as
[`P11-FU-11`](../2026-07-23-consolidated-deferred-followups-backlog.md#p11-fu-11-plan-117-retry-preflight-and-live-session-proof).
Its paired design is
[`2026-08-04-plan-11-7-retry-preflight-gate-design.md`](../../specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md).

**Status:** Draft for independent reviewer and operator approval. Approval authorizes the bounded
tooling and evidence work below. It does not authorize changes under `src/optimus` or
`src/optimus_gateway`, a fourth correlation launch, production server-side custody, or edits to
frozen/approved parent documents.

## Global Constraints

- The consolidated pool entry `P11-FU-11` is the source of truth for this newly discovered gap.
  This amendment may describe the work but must not become a second open-work pool.
- The paired design spec is required because no existing runner or relay path constructs
  `live_session_proof` from real Zed/relay process state. Do not collapse the acquisition design
  into an unexplained CLI call.
- Never edit the frozen Plan 11.7 file
  `docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md`. Its known
  Git-blob SHA-256 is
  `F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D`; re-compute it at Task 0.
  This branch is based on `origin/main` at `c17af17`, and its frozen-plan blob matches that approved
  digest; Task 0 must still recompute it before execution.
- Never edit either approved 2026-08-02 parent amendment or design. The expected parent digests at
  the time of the prior approval are:
  `79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6` for the parent amendment,
  `8808E5212DCDB3B44198096D1A0AFE7E20A53E4A9B28438DA5AA23245D339F0E` for the server-side custody
  design, `9ADD264B06B67B7BF6C85A3A1439BFED29F10C08366848761EED9C3D8B624347` for the fixture-v2
  design, and `5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D` for the fixture-v2
  amendment. Re-compute every value from on-disk bytes; stop on absence or mismatch.
- Preserve every original attempt, reservation, stage record, transcript, relay index, byte stream,
  settings pre-image, reviewer record, and sealed artifact. Corrections are append-only records.
- Preserve the existing accounting: `origin-a-3` is correlation ordinal 3; a successful correlation
  may use prompt ordinal 2 and, only after an evidence-backed transient failure plus live proof,
  prompt ordinal 3. No fourth correlation launch is allowed.
- The existing `assert_prompt_retry_preflight` function remains pure, but its signature is
  deliberately superseded by the contract in the “Existing gate contract and supersession” section
  below. It must not inspect processes, open the relay, mutate settings, or synthesize missing proof
  fields.
- The retry CLI must use a live query to the active relay. A persisted JSON snapshot, PID-only
  match, workspace match, timestamp proximity, or caller-supplied `acp_session_id` is not proof.
- The ACP relay remains byte-opaque. Control-plane traffic is private custody tooling and is not
  ACP-conformance evidence or a replacement for relay/index/debug corroboration.
- The control path is same-run, local-only, run-bound, and restricted to the current operator. It
  may not expose a network listener, forward credentials, or mutate the ACP byte stream.
- A successful retry reuses the exact existing Zed process, relay connection, and ACP session. It
  must not launch Zed, issue `session/new`, mutate settings, or allocate correlation ordinal 4.
- Live evidence requires the real Zed/relay process, real Redis TimeSeries, and real Optimus Gateway.
  Runtime provider access remains limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.
- Tool output, process state, relay messages, and web/extract text are untrusted inputs. Validate
  identity and schema before using them as custody facts; never execute or `eval` them.
- Raw evidence, control descriptors, credentials, private environment, settings bytes, and raw
  transcripts remain under approved private custody. Promoted evidence contains safe normalized
  facts, hashes, reason codes, and relative locators only.
- Run narrow tests, the complete unit suite, Ruff, the checked-in logging-surface verifier,
  production-source cleanliness, and `git diff --check` at every required checkpoint.
- Approval, settings mutation, commit, push, PR creation, merge, external issue creation, Redis
  deletion, and branch deletion retain separate authorization. Never use `--no-verify`.

---

## Effect on the approved parent amendments

This amendment changes only the missing implementation/evidence path for the already-authorized
same-session prompt-only retry:

1. the frozen Plan 11.7 plan and both 2026-08-02 amendments remain historical, immutable inputs;
2. the fixture-v2 stage accounting and `origin-a-3` correlation budget remain unchanged;
3. the retry branch is no longer allowed to print success from fixture validation alone;
4. a retry is eligible only after a live relay proof binds the exact Zed PID/process identity,
   relay `connection_id`, and observed ACP `acp_session_id` to `origin-a-3`;
5. proof acquisition or identity failure stops before prompt reservation and never authorizes a new
   launch; and
6. the parent probe remains blocked until the amendment's code, offline verifier, and real-process
   evidence are independently accepted.

The owner remains `P11-FEAT-ZED-RESUME`; no follow-up is left unnamed.

## Current implementation gap to close

The source inspection that raised `P11-FU-11` identified these exact behaviors in the execution
runner:

- `assert_prompt_retry_preflight` at the reported line 1457 is complete and never called;
- the `origin-a-prompt-retry` CLI branch at reported lines 1639-1659 validates the fixture hash and
  prints a hardcoded JSON blob; and
- no function anywhere constructs `live_session_proof` from real Zed/relay process state.

Task 0 must revalidate the exact file and line locations against the execution commit before an
implementer edits anything. The line numbers are navigation evidence, not a substitute for source
identity or a permission to modify a different branch.

## File and responsibility map

| File | Responsibility |
|---|---|
| `tools/plan117_custody_contract.py` | New canonical `LiveSessionProof` and `RetryPreflightResult` types, proof hashing, retry eligibility helpers, and stable reason codes; it does not own the runner's public gate |
| `tools/plan117_custody_relay.py` | Same-run private control endpoint, live process/connection observation, proof response, and existing-session prompt forwarding; ACP bytes remain opaque |
| `tools/run_plan117_custody_feasibility.py` | Load/recompute the ledger, acquire proof, call preflight, reserve prompt ordinal 3, dispatch existing-session prompt, and emit structured outcomes |
| `tools/verify_plan117_custody_feasibility.py` | Offline verification of proof fields, hashes, descriptor binding, ledger state, no-relaunch/no-settings invariants, and stop precedence |
| `tests/unit/tools/test_plan117_custody_contract.py` | Proof schema, canonical digest, ledger binding, mismatch, stale, PID-reuse, and pure-gate tests |
| `tests/unit/tools/test_plan117_custody_relay.py` | Control-channel identity, liveness, pipe failure, ordering, EOF, ACL/capability, and no-byte-mutation tests |
| `tests/unit/tools/test_run_plan117_custody_feasibility.py` | CLI order, hardcoded-output removal, reservation ordering, existing-session retry, and no-launch/settings tests |
| `tests/unit/tools/test_verify_plan117_custody_feasibility.py` | Positive proof and tamper/precedence cases for every promoted field |
| `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/live-session-proof.json` | Append-only safe proof record with process, connection, session, liveness, evidence, and digest fields |
| `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/relay-control-descriptor.json` | Private locator/digest record for the active run-bound relay control endpoint; never promoted with secrets |
| `reports/plan-11-7-server-custody-artifact-manifest.json` | Append proof and retry evidence locators/hashes without rewriting existing entries |
| `reports/plan-11-7-server-custody-feasibility.json` | Normalized result after offline verification and review |
| `reports/plan-11-7-server-custody-feasibility.md` | Human-readable retry proof, outcome, limitations, and no-relaunch disposition |
| `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` | Pool custody; update only its current-state link/status when the reviewed result changes it |
| `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` | Current Plan 11.7 amendment dependency, only if its current-state claim becomes stale |
| `README.md` | Freshness audit; update only if a current-state claim is made false |

## Existing gate contract and deliberate supersession

On `origin/main` at `c17af17`, `tools/run_plan117_custody_feasibility.py:1457` exposes this current
runner API and keeps it in the module's `__all__` export at line 1696:

```python
def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    live_session_proof: Mapping[str, Any] | None,
) -> None:
```

This amendment deliberately supersedes that signature while preserving the function's module and
export identity. The function remains in `tools/run_plan117_custody_feasibility.py`, remains pure
and exception-based for invalid input, and remains listed in that module's `__all__`. Task 1 adds
`LiveSessionProof` and the new `RetryPreflightResult` type to
`tools/plan117_custody_contract.py`; the runner imports those types but does not relocate the public
gate. The replacement contract is:

```python
def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    target_sha256: str,
    live_session_proof: LiveSessionProof | None,
) -> RetryPreflightResult:
```

`target_sha256` is computed by the existing exact target-resolution preflight before this call; the
gate compares it to the approved target identity and never resolves a path itself. Successful
validation returns the new immutable result; failed validation continues to raise the existing
`CustodyRunnerError` reason codes. Existing unit fixtures that pass a plain mapping must be replaced
with typed proof fixtures, and the `None` rejection test remains mandatory.

## Required interfaces

The public gate remains in `tools/run_plan117_custody_feasibility.py`; the contract module owns the
new proof/result types and validation helpers. The serialized behavior below is mandatory:

```python
@dataclass(frozen=True)
class LiveSessionProof:
    run_attempt_id: str
    zed_pid: int
    zed_process_start_time_utc: str
    connection_id: str
    acp_session_id: str
    zed_alive: bool
    relay_alive: bool
    acp_session_observed: bool
    captured_utc: str
    evidence: tuple[EvidenceReference, ...]
    proof_sha256: str


@dataclass(frozen=True)
class RetryPreflightResult:
    run_attempt_id: str
    prompt_ordinal: int
    prompt_fixture_sha256: str
    target_sha256: str
    live_session_proof_sha256: str
    settings_mutated: bool
    zed_launched: bool


def acquire_live_session_proof(
    *,
    run_attempt_id: str,
    descriptor_path: Path,
    expected_descriptor_sha256: str,
) -> LiveSessionProof:
    """Query the active relay control path; never reconstruct proof from the descriptor."""


def assert_prompt_retry_preflight(
    *,
    run_attempt_id: str,
    ledger: StageLedger,
    prompt_fixture: Path,
    target_sha256: str,
    live_session_proof: LiveSessionProof | None,
) -> RetryPreflightResult:
    """Pure fail-closed eligibility check for the one same-session prompt retry."""
```

The implementation must bind `zed_pid` to a process-start identity, bind `connection_id` to the
relay's active connection, and bind `acp_session_id` to the actual `session/new` response observed
on that connection. The proof query must fail closed if any field is missing or cannot be verified.

## Retry protocol

The runner must implement this exact order for `origin-a-prompt-retry`:

```text
load immutable stage ledger
derive next prompt ordinal and verify origin-a-3 prompt ordinal 2 transient failure
verify approved fixture and target identities
load private relay descriptor as a locator only
query live relay for LiveSessionProof
call assert_prompt_retry_preflight(ledger, proof, identities)
atomically reserve prompt ordinal 3
send existing ACP session/prompt over the active relay connection
append prompt outcome and proof references
```

The command must never launch Zed, mutate settings, call `session/new`, allocate correlation
ordinal 4, or print a success result that was not derived from the gate and live relay response.
If the relay proof is unavailable or mismatched, the command exits before reservation and emits
`blocked_probe_same_session_prompt_retry_unavailable` or the more specific invalid-proof reason.

## Task 0: Freeze authority, source identity, and approval inputs

**Files:**

- Inspect and do not edit: frozen Plan 11.7, both 2026-08-02 parent amendments/designs, and the
  existing reviewer checkpoint log.
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` only if
  the pool entry link/status is stale after reviewer approval.
- Create: the amendment/design approval record through the existing reviewer process.

**Interfaces:**

- Produces the exact parent digests, execution branch/worktree identity, and approved amendment and
  design digests consumed by every later task.
- Does not launch Zed, open the control endpoint, mutate settings, or change production source.

- [ ] **Step 1: Verify the pool-first entry and branch state.**

  Read `P11-FU-11`, verify the amendment and design paths resolve from that entry, confirm the
  current branch is `agent/codex/plan-11-7-retry-preflight-brief` for drafting or the separately
  approved execution branch for live evidence, and confirm no unrelated work is overwritten. The
  drafting branch may carry the documents, but it may not be used for live Plan 11.7 execution.

  ```powershell
  git status --short --branch
  git branch --show-current
  Get-Content -LiteralPath "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md" | Select-Object -Skip 550 -First 90
  ```

- [ ] **Step 2: Recompute parent and new-document hashes from bytes.**

  Hash the frozen plan, both existing 2026-08-02 amendments/designs, this amendment, and its paired
  design from the exact execution tree. Record identity + UTC + exact LF-byte SHA-256 in the
  reviewer-owned checkpoint process. Stop if a parent file is absent or differs; never reconstruct
  it from chat text.

  ```powershell
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md"
  Get-FileHash -Algorithm SHA256 -LiteralPath "docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md"
  git status --short
  ```

- [ ] **Step 3: Revalidate the reported source locations.**

  Locate the actual `assert_prompt_retry_preflight` definition, the `origin-a-prompt-retry` CLI
  branch, and every existing `live_session_proof` reference on the exact execution commit. Record
  the file path, current line range, and clean-source digest. If the source differs from the intake
  description, stop and amend this plan before implementation.

## Task 1: Add the proof contract and pure preflight tests

**Files:**

- Modify: `tools/plan117_custody_contract.py`
- Modify: `tests/unit/tools/test_plan117_custody_contract.py`
- Modify: `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` for any new
  persistence/export surface

**Interfaces:**

- Consumes the existing append-only stage ledger and launch/session identity records.
- Produces canonical `LiveSessionProof`, stable invalid/blocked reasons, and a pure preflight result.

- [ ] **Step 1: Write failing contract tests.**

  Cover a positive proof, missing fields, wrong `run_attempt_id`, wrong PID/process-start identity,
  closed process, stale/closed relay connection, unobserved session, mismatched
  `acp_session_id`, changed fixture/target, missing correlation success, non-transient prompt
  failure, prior retry, prompt ordinal gap, and a request that would allocate correlation ordinal 4.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py -q
  ```

  Expected before implementation: the new proof/retry assertions fail for the intended missing
  fields or call path; an import-only failure is insufficient.

- [ ] **Step 2: Implement canonical proof validation and pure gate wiring.**

  Canonicalize only safe normalized fields, compute the digest over canonical bytes, require
  evidence references for live facts, and preserve the existing stage-ledger precedence. The pure
  function must not query Windows, read the control endpoint, or accept caller-provided proof facts
  without validation.

- [ ] **Step 3: Run focused and project gates.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_contract.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen python -m ruff check .
  git diff --check
  ```

## Task 2: Add live relay proof acquisition without changing ACP bytes

**Files:**

- Modify: `tools/plan117_custody_relay.py`
- Modify: `tests/unit/tools/test_plan117_custody_relay.py`
- Create private: the run-bound relay control descriptor and runtime state under the approved
  private custody root

**Interfaces:**

- Consumes the relay-owned Zed process handle, active ACP connection, and observed `session/new`
  response.
- Produces `get_live_session_proof` and `send_existing_session_prompt` over a local run-bound
  control endpoint. Control traffic is separate from the opaque ACP byte stream.

- [ ] **Step 1: Write failing relay-control tests.**

  Prove a live response includes exact PID/process-start identity, connection ID, session ID, and
  current liveness; prove failure on PID reuse, process exit, connection EOF, wrong run ID, stale
  descriptor, unauthorized caller, malformed request, and duplicate/second retry. Prove ACP bytes,
  ordering, environment, argv, and cwd remain unchanged.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q
  ```

- [ ] **Step 2: Implement the private control endpoint.**

  Bind the endpoint to the current operator and one run attempt, use an exclusive descriptor, keep
  the descriptor as a locator rather than proof, and return facts read from the live process and
  connection. Reject network endpoints and never forward the control request into ACP. The relay
  must keep ownership of the existing connection until the retry outcome is sealed.

- [ ] **Step 3: Implement existing-session prompt forwarding.**

  Accept only a preflight-approved run, connection ID, and observed ACP session ID. Forward exactly
  one `session/prompt`; never issue `session/new`, launch Zed, or mutate settings. Close the control
  endpoint after terminal outcome and preserve all raw evidence under private custody.

- [ ] **Step 4: Run relay and source-safety gates.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen python -m ruff check .
  git diff --check
  ```

## Task 3: Wire the retry CLI to ledger, proof, preflight, reservation, and prompt

**Files:**

- Modify: `tools/run_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_run_plan117_custody_feasibility.py`

**Interfaces:**

- Consumes the stage ledger, fixture/target identity, relay descriptor, live proof, and pure
  preflight result from Tasks 1-2.
- Produces structured retry outcomes derived from actual gate results; removes the hardcoded JSON
  success path.

- [ ] **Step 1: Write failing CLI-order tests.**

  Assert that the branch loads/recomputes the ledger, verifies fixture and target identity, queries
  the relay, calls `assert_prompt_retry_preflight`, reserves ordinal 3 only after success, and then
  sends the existing session prompt. Assert that every failure before reservation performs no ACP
  request, no Zed launch, no settings mutation, and no correlation allocation.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py -q
  ```

  Expected before implementation: the tests observe the current hardcoded output or missing calls.

- [ ] **Step 2: Replace the hardcoded branch with the real sequence.**

  The retry branch must load the immutable ledger, derive prompt ordinal 3, call the proof
  acquisition function, pass the proof to the pure gate, reserve atomically, forward one existing
  `session/prompt`, append the outcome, and emit safe structured JSON. The branch must not accept a
  proof object, ACP session ID, or eligibility result from CLI input.

- [ ] **Step 3: Add reservation and race tests.**

  Prove a second concurrent retry sees the existing immutable reservation and stops, a stale proof
  cannot reserve, a process that exits after proof but before prompt is classified without relaunch,
  and a prompt failure after reservation cannot reclaim ordinal 3.

- [ ] **Step 4: Run focused integration gates.**

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_run_plan117_custody_feasibility.py tests/unit/tools/test_plan117_custody_contract.py tests/unit/tools/test_plan117_custody_relay.py -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

## Task 4: Extend offline verification and append-only evidence

**Files:**

- Modify: `tools/verify_plan117_custody_feasibility.py`
- Modify: `tests/unit/tools/test_verify_plan117_custody_feasibility.py`
- Modify append-only: `reports/plan-11-7-server-custody-artifact-manifest.json`
- Create append-only: `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/live-session-proof.json`
- Keep private: `reports/plan-11-7-server-custody-artifacts/attempts/origin-a-3/relay-control-descriptor.json`

**Interfaces:**

- Consumes proof, launch, relay, transcript, debug, ledger, and prompt outcome records.
- Produces a verifier result that can distinguish unavailable proof, identity mismatch, control
  failure, second prompt failure, and accepted same-session retry.

- [ ] **Step 1: Write failing verifier/tamper tests.**

  Reject every changed proof field, changed evidence hash, descriptor mismatch, stale endpoint,
  PID reuse, wrong session ID, wrong connection ID, missing debug corroboration, prompt ordinal 4,
  a second reservation, a relaunch, settings mutation, and a hardcoded success result.

  ```powershell
  uv run --frozen pytest tests/unit/tools/test_verify_plan117_custody_feasibility.py -q
  ```

- [ ] **Step 2: Implement offline proof verification.**

  Recompute canonical proof and descriptor digests, verify the immutable parent chain, bind proof
  fields to launch/relay/session evidence, enforce precedence, and reject any live claim supported
  only by a persisted snapshot. The verifier must remain offline-only.

- [ ] **Step 3: Seal only safe append-only records.**

  Add proof locators and hashes to the manifest without rewriting existing entries. Keep raw control
  messages, private descriptors, environment, credentials, and settings bytes out of promoted
  output.

- [ ] **Step 4: Run the offline evidence gates.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-3
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit/tools -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

## Task 5: Capture the real same-session retry evidence

**Files:**

- Create private and promoted evidence only under the approved Plan 11.7 custody roots.
- Append: `reports/plan-11-7-server-custody-artifact-manifest.json`.
- Update normalized reports only after offline verification accepts the chain.
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`.

**Interfaces:**

- Consumes the reviewed committed execution identity, existing origin-A evidence, real Zed 1.13.1,
  real relay, real Redis TimeSeries, and real Gateway.
- Produces one independently verifiable same-session prompt retry or a sealed fail-closed stop.

- [ ] **Step 1: Prove the clean execution identity and external approvals.**

  Pin the exact runner, relay, contract, verifier, tests, fixture, scenario, and logging manifest
  Git-blob digests. Confirm no `src/optimus` or `src/optimus_gateway` change, no exported
  `OPTIMUS_PLAN117_*` variable, exact settings pre-image, approved launch command, and fresh
  settings-mutation approval. Do not proceed from a dirty or unreviewed tree.

- [ ] **Step 2: Run the already-authorized `origin-a-3` correlation flow once.**

  Preserve the parent command and fixture-v2 identity. The correlation stage must succeed before a
  prompt retry can be considered. A Zed crash, invalid relay/debug evidence, settings restoration
  failure, permanent failure, or missing Gateway fields stops without another launch.

- [ ] **Step 3: Invoke the prompt-only retry branch.**

  ```powershell
  uv run --frozen python tools/run_plan117_custody_feasibility.py origin-a-prompt-retry --run-attempt-id origin-a-3 --prompt-fixture tests/fixtures/evidence/plan117-server-custody-prompt-v2.txt --workspace-root $plan117Workspace --capture-root $plan117PrivateRoot --debug-log $plan117DebugLog
  ```

  Before accepting success, verify the proof was returned by the live relay, the Zed PID/process
  identity is unchanged, the relay connection ID is unchanged, the ACP session ID matches the real
  prior `session/new`, and the command issued no launch, settings mutation, or new correlation.

- [ ] **Step 4: Verify the live attempt offline and promote through the public collector.**

  Require hard Gateway request/provider/model/usage/cost fields, exact response/session/debug
  binding, relay byte agreement, prompt ordinal 3 accounting, and no second retry. Promote only
  through the existing `tools/evidence_gather.py prepare` / `redact` subprocess path.

## Task 6: Final gates, documentation freshness, and reviewer return

**Files:**

- Inspect/update when stale: the consolidated backlog, Phase 1 roadmap, evidence-handoff open-work
  pool, `README.md`, and the parent feasibility report.
- Reviewer updates separately: `docs/superpowers/reviews/plan-11-7-review-checkpoints.md`.

**Interfaces:**

- Consumes the sealed append-only evidence and exact execution identity.
- Produces an independently reviewed disposition; it does not close the frozen Plan 11.7 plan or
  claim production server-side custody.

- [ ] **Step 1: Run all release gates.**

  ```powershell
  uv run --frozen python tools/verify_plan117_custody_feasibility.py --manifest reports/plan-11-7-server-custody-artifact-manifest.json --checkpoint origin-a-3
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json --project-root .
  uv run --frozen pytest tests/unit -q
  uv run --frozen pytest tests/integration -q
  uv run --frozen python -m ruff check .
  git diff --check
  git status --short
  ```

- [ ] **Step 2: Audit every current-state document.**

  Check the consolidated deferred-followups backlog, roadmap, evidence-handoff pool, parent report,
  README, and both new design/plan documents for stale claims. Keep frozen/historical documents
  unchanged; update only current-state documents whose claims changed and record the exact evidence
  anchor.

- [ ] **Step 3: Obtain independent reviewer and operator disposition.**

  Reviewer verifies the pool-first custody, parent hashes, pure-gate call, live relay proof, exact
  process/connection/session identity, no relaunch, no settings mutation, prompt-only accounting,
  Gateway fields, redaction, and all final gates. The reviewer records acceptance, stop, or blocked
  retry in the existing checkpoint process. No agent edits that reviewer-owned record.

- [ ] **Step 4: Preserve the terminal result.**

  If the retry succeeds, return the sealed same-session evidence to the approved parent sequence.
  If proof is unavailable or the retry stops, preserve that result as terminal and do not consume a
  fourth correlation launch. Any later budget expansion requires a new pool entry and separately
  approved amendment.

## Stop taxonomy and precedence

The verifier preserves all parent stop codes and adds these retry-specific safe codes:

| Code | Meaning |
|---|---|
| `invalid_probe_retry_ledger_unavailable` | The stage ledger is absent, malformed, forked, or inconsistent with immutable records |
| `invalid_probe_retry_proof_unavailable` | The live relay cannot answer the proof request or the endpoint is stale |
| `invalid_probe_retry_process_identity_mismatch` | PID, process-start identity, or Zed liveness differs from the launch |
| `invalid_probe_retry_connection_identity_mismatch` | The relay connection is absent, closed, or not the reserved connection |
| `invalid_probe_retry_acp_session_identity_mismatch` | The ACP session ID was not observed from the exact prior `session/new` response |
| `blocked_probe_same_session_prompt_retry_unavailable` | A transient prompt failure exists but exact live same-session proof is unavailable |
| `invalid_probe_retry_control_channel_failure` | The private relay control path failed before prompt transmission |
| `invalid_probe_retry_second_prompt_failure` | The single allowed prompt-only retry failed; no further retry is allowed |

Precedence remains:

1. trigger/amendment/parent/execution/fixture/target identity invalid;
2. settings restoration failure;
3. relay/control/process/transcript/debug/custody invalid;
4. Zed client crash;
5. stage ledger, reservation, or retry-budget invalid;
6. permanent prompt/dependency failure or unavailable same-session proof;
7. evidence-backed transient prompt failure eligible for the one retry; and
8. successful real-Gateway prompt evidence.

No lower result is reachable while a higher predicate is true. Proof acquisition failure is never
an invitation to relaunch Zed.

## Definition of done

This amendment is ready to return to the Plan 11.7 reviewer only when every claim maps to named
evidence:

- the pool entry predates and links this amendment;
- the paired design and amendment have exact approval digests;
- the retry CLI calls the actual ledger loader and `assert_prompt_retry_preflight`;
- live proof is returned by the active relay and binds PID/process identity, connection ID, and ACP
  session ID to `origin-a-3`;
- stale/mismatched/missing proof fails before reservation or prompt transmission;
- the accepted path uses exactly one existing-session prompt and no new launch, settings mutation,
  `session/new`, or correlation ordinal;
- offline verifier, unit/integration tests, Ruff, logging audit, redaction, and docs freshness pass;
- real Zed/relay/Gateway/Redis evidence proves the result; and
- reviewer and operator dispositions are recorded through their existing separate gates.

Approval of this amendment never authorizes production server-side custody or changes to frozen
Plan 11.7.
