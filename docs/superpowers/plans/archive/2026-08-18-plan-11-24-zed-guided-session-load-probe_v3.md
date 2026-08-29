# Plan 11.24 v3 — Zed Workspace Approval and Guided-Probe Amendment

> **Status:** Live version of Plan 11.24. This file supersedes v2's execution authority only where
> stated below, authorizes only offline Tasks 6–8, and records those tasks as not started. It does
> not authorize a Zed launch, a preflight that starts external processes, or any paid/network call.
>
> **Frozen predecessors:**
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md`, git blob
> `421f9a9595dda1d55b9895b148839de8163e6556`; and
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md`, git blob
> `85cea53cbec6ca9faf1cee85f5c81e15999321b8`. Leave both byte-identical.
>
> **Live-version pointer:** This `_v3` file is the sole live Plan 11.24 contract. No committed pool,
> roadmap, README, or other index points at a predecessor filename, so this header is the required
> forward-only pointer; do not manufacture another tracking row.
>
> **Authoring baseline:** `origin/main` at
> `aa84341b8d30c2fea861e28b89df80e5f8c5b781` (PR #177 merged).

## Purpose and amendment boundary

Plan 11.24 v1's single guided launch and the later operator-granted WP-11 re-shot are both spent.
The re-shot proved the v2 settings-seeding correction—Optimus appeared in Zed's Agent panel and the
settings file was present under the discovered user-data root—but ended
`INDETERMINATE / OBSERVATION_INCOMPLETE`. Zed sent `initialize`; the agent returned zero bytes, so
the run never reached the open question of whether Zed 1.15.1 sends `session/load`.

The merged root-cause report establishes why:
`reports/plan-11-24-agent-launch-approval-root-cause.md`. The acpx baseline approves
`<run-root>/acpx-workspace`, uses it, and revokes that approval before returning. The real-Zed path
then creates `<run-root>/zed-workspace` and tells Zed's agent child to use that different workspace.
Durable approval lookup is workspace-specific, so the child deterministically fails `NO_APPROVAL`,
writes remediation only to stderr, returns 2, and emits no ACP stdout. The opaque relay, settings
seeding, guided timeout, isolation, and cleanup are exonerated.

This amendment implements the operator's settled **Option A** ruling: create `zed-workspace` before
the acpx stage, perform the existing durable approval ceremony for that exact workspace immediately
before the Zed launch, keep the approval live through the launch, and revoke it in `finally`. It also
bundles two small offline harness defects found while preserving the evidence:

1. `approved_real_zed_command` omits `--zed-launch-timeout-seconds` and `--report-dir` and is a stale
   handwritten list instead of a serialization of the parsed command contract.
2. `_plan1124_report_text()` omits the v1-required result-to-consequence row.

Tasks 6–8 are one offline implementation package. Their approval or merge supplies no authority to
start Zed, Redis, acpx, an ACP server, or an approval ceremony. The corrected run package is defined
later in this file so it can be reviewed now, but it remains dormant until a future package and an
explicit one-shot launch-budget grant are recorded by the operator.

## Settled evidence and design ruling

These facts are inputs, not work for the implementing agent to redesign:

- Plan 11.24 v2 Task 5 merged through PR #176 at Optimus commit `a8d8755`. Its caller now passes
  `Path(invocation.user_data_root)`, settings exist at `<user-data-dir>/config/settings.json` before
  launch, the old `Zed/` and `zed-appdata` candidates are absent, and `environment_bind == ()`.
- The WP-11 re-shot's verifier-valid evidence and the root-cause report merged through PR #177. The
  historical bundle at `reports/plan-11-24-zed-guided-session-load-probe/` is digest-pinned and must
  not be edited or reused as the target of another run.
- `WorkspaceIdentity` binds the lexical/canonical path, device, inode, and Git context; it explicitly
  does not bind timestamps or snapshots (`src/optimus/acp/trusted_paths.py:121-129,879-889`). An
  empty `zed-workspace` can therefore be created and approved before Zed writes into it without
  invalidating that approval.
- `--launch-approval-id` reaches `authorize_launch()`
  (`src/optimus/acp/__main__.py:115-120,244-250`), but `p996_` records are consumed atomically on the
  first use (`src/optimus/acp/launch_gate.py:706-730` and
  `src/optimus/acp/launch_approvals.py:750-783`). The argument is an internal slot whose stated only
  intended caller is the `optimus-trust` spawn path. It is not a probe-to-Zed contract.
- Durable lookup is read-only and therefore remains usable by another launch of the same candidate
  (`src/optimus/acp/launch_approvals.py:598-622`). The existing
  `tests/unit/acp/test_launch_gate.py::TestEndToEndAuthorization::test_full_authorize_launch_durable_succeeds`
  proves the full durable authorization path. This is the required behavior if Zed restarts the
  agent or spawns it more than once.

The rejected alternatives remain rejected:

| Option | Ruling | Reason |
|---|---|---|
| B — seed `--launch-approval-id` into the relay child command | rejected | It repurposes an unratified internal production-security contract. A `p996_` id is delete-before-use, so a second Zed spawn receives `NO_APPROVAL` and dies with the same silent-agent failure shape during a spent observation window. It would also require `src/` security-surface work. |
| C — make acpx and Zed share one workspace and defer the existing revocation | rejected | It keeps one durable approval live across both probe stages—the longest security window—and conflates the independent acpx control with Zed's project/evidence workspace. |

Do not reopen A/B/C during implementation. New evidence that contradicts a pinned contract is a stop
condition and returns to the reviewer; an implementation preference is not such evidence.

## Superseded and preserved provisions

The following v1/v2 provisions are superseded:

- v1's and v2's live commands are historical and may never be re-run as authority.
- v2's statement that only Task 5 is authorized is replaced by this amendment's authorization of
  offline Tasks 6–8. Task 5 remains accepted merged history even though v2's frozen checkbox is not
  retroactively changed.
- Any future preflight/run command must carry the parsed 900-second timeout and a fresh v3 report
  directory. The existing report directory is evidence, not an overwrite target.
- The generated report must state the exact consequence for its classified result; a finding-only
  report is no longer conformant.

All other v1/v2 constraints remain in force: hermeticity, sanitized reconstructed evidence only,
unchanged normal Optimus capability behavior, no origin-A launch, no prompt or Gateway call, one
Zed launch per separately granted shot, no retry, and no inference from an absent observation.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| plan/state | This `_v3` amendment is reviewed and merged before Cursor starts Tasks 6–8. | no | Codex + operator | merely unauthorized until the authored bytes are approved and merged. |
| code/state | The real-Zed path creates and durably approves the exact `zed-workspace` used by the child, keeps it approved through launch, and revokes it before deleting the workspace. | no | Cursor | genuinely absent but small and buildable offline; Task 6 supplies it. |
| code/state | The approved-command metadata round-trips through the parser with both run flags, the report emits the exact outcome consequence, and the surface-audit rationale remains truthful. | no | Cursor | genuinely absent but small and buildable offline; Task 7 supplies it. |
| tooling/binaries | The frozen `uv` environment can run pytest, Ruff, the Plan 9.96 surface verifier, and Git without dependency drift. | yes | implementing agent | n/a; stop if the named offline gates cannot execute. |
| services | Tasks 6–8 require no Redis, daemon, port, ACP server, Zed, acpx, or network service. | yes | implementing agent | n/a; any service dependency is scope drift. |
| credentials/authority | Tasks 6–8 require no Optimus credentials, provider key, OS-keyring mutation, trust approval, live-process authority, or launch budget. | yes | implementing agent | n/a; tests must stub every external/interactive boundary. |
| human interaction | Tasks 6–8 require no TTY, `y` confirmation, GUI trust action, Agent-panel action, or manual click. | yes | implementing agent | n/a; an interactive request is a stop condition. |
| cost | Tasks 6–8 make no Gateway/provider call and incur no paid cost. | yes | implementing agent | n/a; any paid call is forbidden. |
| future code/state | Tasks 6–8 and their CI have merged before the corrected run package is dispatched. | no | Cursor + operator | genuinely absent until this offline package is complete; no live Definition-of-Done claim depends on it. |
| future services/tooling | Fresh Redis, acpx, Zed, invocation, and cleanup readiness for the next observation are established by the corrected non-launch preflight. | unknown | future run-package operator | merely unauthorized to inspect or start in this amendment; Future Gate 1 establishes each fact before any launch grant. |
| future human interaction | The operator can complete the acpx and `zed-workspace` durable-approval ceremonies in an interactive terminal, trust the hermetic Zed project, and start Optimus once. | no | operator | merely unauthorized; Future Gates 1 and 4 name the exact ceremonies and GUI actions. |
| future cost/authority | A separately reviewed package grants exactly one real-Zed launch after a successful fresh preflight. | no | operator | merely unauthorized; this amendment deliberately cannot satisfy or imply that grant. |

The only `unknown` is future machine/tool readiness. Future Gate 1 resolves it before the dependent
launch and has `zed_launches: 0`. Tasks 6–8 have no unsatisfied prerequisite after `_v3` merges.

## Global constraints for Tasks 6–8

- Start the implementation branch from the then-current `origin/main`; read this live plan and the
  reviewer checkpoint Current State before mutation. Never reuse a capture or amendment branch.
- Scope is the probe, its unit tests, the one stale surface-audit rationale, and this plan's
  checkboxes. Do not modify `src/`, a verifier, a report/evidence artifact, v1, v2, the root-cause
  report, `CURRENT.md`, the pool, roadmap, or README.
- Reuse `build_trust_command()`, `_run_interactive_required()`,
  `_revoke_temporary_approval()`, and `build_cleanup_remediation()`. Tests replace those seams;
  neither RED nor GREEN may touch the real keyring or request real consent.
- Create `zed-workspace` before the acpx baseline so the exact identity exists early, but do not
  approve it until every deterministic launch preparation has passed and `_launch_zed_once()` is
  next. This minimizes the durable-approval window.
- Once the Zed-workspace approval succeeds, revocation is mandatory on success, launch failure,
  timeout, classifier failure, and evidence failure. A revocation failure prevents run-root deletion
  and evidence publication so the still-existing exact workspace can be used for remediation.
- Never put `--launch-approval-id` into child args, settings, metadata, fixtures, or the run command.
- Preserve the acpx approval lifecycle. The new ceremony is additional and workspace-specific; it
  does not extend or reuse the acpx approval.
- Keep the historical `PLAN_1124_REPORT_NAME` and bundle unchanged. Define a distinct future target,
  `reports/plan-11-24-zed-guided-session-load-probe-v3/`; never rename or overwrite the old target.
- The generated report consequence text is schema-limited constant prose. It must not interpolate
  raw ACP, command output, exception text, credentials, ambient paths, or approval identifiers.
- Preserve all Plan 9.96 sink keys and classifications. Only the text-write rationale made stale by
  the consequence row may change, unless the verifier identifies a genuinely new sink; that is a
  stop condition rather than permission to reclassify silently.

## File map

| Path | Required change |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Option A workspace/approval lifecycle; parser-derived approved run command; fresh v3 report target; exact report consequence mapping. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Genuine RED lifecycle/order/failure tests; command parser round-trip; all-result report-consequence tests; no real GUI, process, keyring, TTY, or network. |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Rewrite only the stale Plan 11.24 report text-write rationale/sanitizer wording while preserving its key, classification, evidence tier, and resolvable test node. |
| `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md` | Mark Task 6–8 checkboxes only after each stated verification command passes; make no prose redesign during implementation. |

## Task 6: Implement Option A at the real-Zed call boundary

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Multi-file offline patch. The behavior change is confined to the probe and
its unit tests; no production security module changes.

**Interface contract:** `run_plan1119_real_zed()` creates `<run-root>/zed-workspace` before invoking
`_run_acpx_against_isolated_agent()`. After acpx returns (and has revoked its own approval), the probe
finishes relay/settings/argv preparation, resolves `optimus-trust`, confirms no existing durable
record for `zed-workspace`, and runs
`optimus-trust --workspace-root <zed-workspace> approve --mode durable` through the existing
interactive seam. `_launch_zed_once()` runs while that approval is live. The exact workspace is
revoked in `finally` before cleanup removes it.

- [x] **Step 1: Establish the frozen and causal baseline.**
  - Read this plan, the checkpoint Current State, and
    `reports/plan-11-24-agent-launch-approval-root-cause.md`.
  - Confirm `HEAD` was cut from current `origin/main`; confirm the v1/v2 blobs are exactly
    `421f9a9595dda1d55b9895b148839de8163e6556` and
    `85cea53cbec6ca9faf1cee85f5c81e15999321b8`.
  - Confirm the current ordering is acpx call → create `zed-workspace` → launch, and confirm
    `_run_acpx_against_isolated_agent()` revokes its distinct workspace before returning.

- [x] **Step 2: Write genuine RED lifecycle tests before production edits.** Extend
  `_install_stubbed_real_zed()` with an event ledger and fully stubbed trust seams. Add tests that
  prove all of these boundaries:
  1. `zed-workspace` exists before the fake acpx function runs, but its approval is not yet live;
  2. the acpx function returns before the Zed-workspace `inspect`/`approve` sequence;
  3. the approve command names the same resolved workspace used in relay child
     `--workspace-root`, uses `--mode durable`, and contains no approval id;
  4. approval happens after settings/relay/Zed argv preparation and immediately before the launch;
  5. the approval remains live for the full fake launch, including two recorded simulated
     child-spawn observations, and is revoked exactly once only after launch returns;
  6. an approval/inspect failure yields `zed_launches: 0` and never calls the launch seam;
  7. a launch exception or nonzero exit still revokes exactly once; and
  8. a revoke failure retains the exact run root/workspace for remediation, sets
     `INDETERMINATE / CLEANUP_UNVERIFIED`, publishes no evidence bundle, and never reports cleanup
     success.

  Use explicit tests such as
  `test_real_zed_approves_actual_workspace_only_for_launch`,
  `test_real_zed_approval_failure_prevents_launch`,
  `test_real_zed_launch_failure_still_revokes_workspace`, and
  `test_real_zed_revoke_failure_retains_workspace_and_blocks_publish`. Names may vary only if the
  same four contracts remain directly selectable.

- [x] **Step 3: Run the RED selectors and retain their production-path diagnostics.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "actual_workspace_only_for_launch or approval_failure_prevents_launch or launch_failure_still_revokes_workspace or revoke_failure_retains_workspace" -q
  ```

  Expected: failures show the current probe creates the workspace after acpx and never calls the
  Zed-workspace approval/revocation seams. A synthetic assertion failure or an unstubbed TTY error
  is not valid RED evidence.

- [x] **Step 4: Implement the minimum lifecycle correction.**
  - Move only `workspace = run_root / "zed-workspace"` and `workspace.mkdir(...)` before the acpx
    call. Keep acpx on `acpx-workspace`; do not share roots.
  - Complete deterministic preparation before approval: relay child args, corrected settings,
    launch argv, identity metadata, and all prelaunch validations.
  - Resolve the existing trust CLI, require `inspect` exit 1 for the fresh workspace, then call the
    existing durable approve command through `_run_interactive_required()` with a distinct
    Zed-workspace stage name. Do not synthesize `y` in production or tests.
  - Track only schema-limited lifecycle facts needed for evidence: durable mode, approval created,
    exact child-workspace match, and revocation state. Persist no approval id.
  - Put `_launch_zed_once()` and all postlaunch extraction/classification inside a nested
    `try/finally` whose `finally` revokes the exact `zed-workspace` if approval was created.
  - If revocation fails, record the sanitized failure and workspace-scoped cleanup command, retain
    the run root so its path/device/inode identity still exists, force cleanup false, and prevent
    bundle materialization. Do not let later directory cleanup erase the only remediable identity.
  - Map Zed-workspace inspect/approve failures to `LIVE_LAUNCH_UNAUTHORIZED` and keep
    `zed_launches == 0`; map a revoke failure to `CLEANUP_UNVERIFIED`. Preserve the original
    launch/classifier failure when revocation succeeds; cleanup failure takes precedence only when
    revocation itself fails.

- [x] **Step 5: Prove GREEN at the lifecycle boundary and against the durable contract.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "actual_workspace_only_for_launch or approval_failure_prevents_launch or launch_failure_still_revokes_workspace or revoke_failure_retains_workspace" -q
  uv run --frozen pytest tests/unit/acp/test_launch_gate.py::TestEndToEndAuthorization::test_full_authorize_launch_durable_succeeds -q
  uv run --frozen python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

  Expected: ordering/failure tests and the existing end-to-end durable authorization test pass. No
  test opens a TTY, touches the OS keyring, or starts Zed/acpx/Redis/ACP.

## Task 7: Repair the approved command, report consequence, and audit truthfulness

**Owner:** Cursor implements; Codex reviews.

**Command interface:** Extract the parser construction into `_build_parser()` while retaining
`_parse_args()` as the validation wrapper. Add
`build_approved_real_zed_command(parsed: argparse.Namespace) -> list[str]`. It accepts only a
namespace returned by `_parse_args()` for preflight, changes the serialized mode to `real-zed`, and
serializes the parser-provided workspace, validated timeout, and report directory. The preflight CLI
requires `--report-dir`; `main()` passes the parsed namespace to the helper and passes the resulting
command into
`run_plan1119_preflight(..., approved_real_zed_command: Sequence[str] | None = None)` for metadata.
The preflight CLI path must pass a non-`None` command; the internal acpx-only caller may omit it and
must then omit—not invent—approved-command metadata. Do not maintain a second hardcoded set of
timeout/report values inside `run_plan1119_preflight()`.

**Report interface:** Add a fixed `PLAN1124_OUTCOME_CONSEQUENCES` mapping for exactly
`REACHABLE`, `UNREACHABLE`, and `INDETERMINATE`. `_plan1124_report_text()` emits an
`## Outcome consequence` section with a one-row Markdown table containing the classified result and
its exact v1 consequence. Unknown findings fail closed rather than borrowing another consequence.

- [x] **Step 1: Write RED parser-round-trip tests.** Define the fresh target constant as
  `plan-11-24-zed-guided-session-load-probe-v3`. Parse this preflight argument list:

  ```text
  --mode preflight
  --zed-launch-timeout-seconds 900
  --report-dir reports/plan-11-24-zed-guided-session-load-probe-v3
  <probe-parent>
  ```

  Pass the returned namespace to `build_approved_real_zed_command()`, assert the metadata contains
  each required flag exactly once and no `--launch-approval-id`, then strip the fixed
  `uv run --frozen python tools/probe_p11_zed_session_load.py` prefix and parse the remainder again
  with `_parse_args()`. The round-tripped namespace must have `mode == "real-zed"`, timeout
  `900.0`, the fresh v3 report path, and the same workspace. Add a parser test proving preflight and
  real-zed both reject a missing report directory before any external seam runs.

- [x] **Step 2: Write RED report tests for all three outcomes.** Parameterize
  `_plan1124_report_text()` over the exact v1 consequence table:

  | Result | Required consequence |
  |---|---|
  | `REACHABLE` | The tested current Zed issued `session/load`; a separately scoped `P11-FU-1` durable ACP session-store/handler design is justified, but this plan does not implement it. |
  | `UNREACHABLE` | A captured Zed protocol/method error requires an operator disposition for the Zed-resume lane rather than presumed durable-store implementation. |
  | `INDETERMINATE` | The named missing precondition/observation remains; no implementation or disposition follows automatically. |

  Assert the report has exactly one matching result row and none of the other two consequences.
  Enhance `test_nonempty_sanitized_relay_bundle_passes_existing_verifier` to assert that the
  materialized report includes the matching consequence row, while retaining its canary scan and
  real-verifier pass.

- [x] **Step 3: Run the RED selectors.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "approved_real_zed_command or outcome_consequence or nonempty_sanitized_relay_bundle" -q
  ```

  Expected: the command test exposes both missing flags/the literal metadata, and report tests expose
  the missing consequence section. No external process starts.

- [x] **Step 4: Implement the minimum parser-derived command and report mapping.**
  - Keep one parser definition. The metadata helper serializes parsed/validated values; it does not
    independently choose 180/900 or an evidence directory.
  - Require `--report-dir` in `preflight` and `real-zed`, but not the unrelated acpx-only modes.
  - Preserve the fixed executable prefix and make the v3 preflight command the source of the future
    real-Zed command stored in `approved_real_zed_command`.
  - Keep `PLAN_1124_REPORT_NAME` for historical tests/evidence and add a distinct v3 name; do not
    rename the committed directory.
  - Emit the exact consequence prose above as constant text. Preserve the existing reason and
    “not a finding about Zed” safeguard for applicable `INDETERMINATE` results.
  - Update only
    `tools.probe_p11_zed_session_load:materialize_sanitized_zed_evidence:text_file_write` in the
    Plan 9.96 manifest: replace “finding/reason/commit only” with truthful schema-limited wording
    that includes the fixed outcome consequence. Preserve its key, `safe-by-construction` policy,
    evidence tier, and resolvable nonempty-bundle test node.

- [x] **Step 5: Prove GREEN through the parser, report, verifier, and surface audit.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "approved_real_zed_command or outcome_consequence or nonempty_sanitized_relay_bundle" -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

  Expected: the command round-trips, all three consequences are exact, materialized evidence still
  passes the unchanged verifier, and the surface verifier reports zero unclassified sinks, zero
  stale entries, and zero unresolved test nodes.

## Task 8: Verify and publish one atomic offline repair package

**Owner:** Cursor publishes; Codex performs one substantive review round; operator alone merges.

- [x] **Step 1: Run the complete affected test and policy gates.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen pytest tests/unit/acp/test_launch_gate.py::TestEndToEndAuthorization::test_full_authorize_launch_durable_succeeds -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

- [x] **Step 2: Prove scope, immutability, and non-execution.**
  - `git diff --name-only` lists exactly the probe, its unit test, the surface-audit manifest, and
    this v3 plan's checkbox updates.
  - `git diff --exit-code -- src/optimus src/optimus_gateway` is clean.
  - v1 and v2 still resolve to blobs `421f9a9595dda1d55b9895b148839de8163e6556` and
    `85cea53cbec6ca9faf1cee85f5c81e15999321b8`.
  - The historical Plan 11.24 bundle and root-cause report are byte-identical to `origin/main`; no
    v3 evidence directory exists.
  - The diff contains no `--launch-approval-id` addition and no synthesized confirmation input.
  - Record explicitly that no Zed/acpx/Redis/ACP process, TTY ceremony, keyring mutation, network
    request, provider call, or paid call ran.

- [ ] **Step 3: Commit and open one draft implementation PR.** Stage only the four authorized files,
  commit once as `fix(zed): approve hermetic workspace for guided launch`, push the Cursor branch,
  and open a draft PR. Do not merge. The PR description must carry the genuine RED failure, GREEN
  commands, full gate rollup, exact file list, frozen blob checks, and explicit no-live-action fact.

## Corrected future run package — definition only, not authorization

Nothing in this section may be executed under `_v3` alone. After Tasks 6–8 and CI merge, a future
work package must name its own operator, current commit, current Zed/acpx identities, stop
conditions, and exactly one Zed-launch budget. The operator records the actual grant only after
Future Gate 1 is green. That later package may use the following reviewed run definition without
redesign.

### Future Gate 1: Fresh non-launch readiness and canonical command

This gate starts real prerequisite processes and performs the existing acpx durable-approval
ceremony, so it requires its own future dispatch even though `zed_launches` remains zero.

```powershell
$probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-zed-guided-probe-v3'
$reportDir = 'reports/plan-11-24-zed-guided-session-load-probe-v3'
New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
if (Test-Path -LiteralPath $reportDir) { throw "Fresh v3 report directory already exists" }
uv run --frozen python tools/probe_p11_zed_session_load.py --mode preflight --zed-launch-timeout-seconds 900 --report-dir $reportDir $probeParent
Get-Content -Raw (Join-Path $probeParent 'plan1119-preflight-result.json')
```

Expected before any launch grant: `preflight_ok: true`, `zed_launches: 0`,
`origin_a_launches: 0`, fresh Zed/acpx identities, Redis/acpx baseline success, normal
`loadSession: false`, isolated `loadSession: true`, verified cleanup, and an
`approved_real_zed_command` that round-trips to the same workspace, timeout 900, and fresh v3 report
directory. Any failed predicate ends the package `INDETERMINATE / PRECONDITION_UNMET`; do not repair,
retry, or launch ad hoc.

### Future Gate 2: Record the separate one-shot launch grant

After a reviewer verifies Gate 1, the operator may grant exactly one execution of the canonical
`approved_real_zed_command`, with one hermetic Zed window, no origin-A launch, no prompt, no Gateway
call, and no retry. Without a timestamped grant in the reviewer checkpoint, stop here. A successful
preflight never implies the grant.

### Future Gate 3: Recheck the boundary without launching

```powershell
git status --short --branch
git rev-parse HEAD
uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
if (Test-Path -LiteralPath $reportDir) { throw "Fresh v3 report directory already exists" }
```

Expected: the approved commit is checked out, deterministic gates pass, no target Zed is already
running, and the v3 report directory is absent. Otherwise the grant remains unspent and the run
stops.

### Future Gate 4: Execute the canonical command once and perform the guided actions

Load the sidecar and execute its parser-derived command rather than retyping flags:

```powershell
$preflight = Get-Content -Raw (Join-Path $probeParent 'plan1119-preflight-result.json') | ConvertFrom-Json
$approved = @($preflight.approved_real_zed_command)
if ($approved.Count -lt 2) { throw "Approved command metadata is missing" }
$approvedExecutable = $approved[0]
$approvedArgs = @($approved[1..($approved.Count - 1)])
& $approvedExecutable @approvedArgs
```

The real-Zed command runs the existing acpx ceremony and then the **additional** `zed-workspace`
ceremony. The operator therefore expects one extra `y` confirmation before Zed launches. Then:

1. Trust only the generated hermetic workspace if Zed presents the Unrecognized Project / Restricted
   Mode action.
2. Open the Agent panel, select **Optimus**, and invoke **Start** exactly once.
3. Wait within the 900-second window, then close the hermetic Zed window once. Do not click Start a
   second time, restart Zed manually, switch agents, or re-run the command.

The falsifiable prediction is: Zed's captured `initialize` receives an agent reply; only then can the
capture establish whether `session/load` follows. Multiple Zed child spawns during the one approved
window remain authorized by the same durable lookup, but they do not authorize a second operator
execution.

If Zed-workspace revocation fails, the probe must retain the exact throwaway workspace and emit its
workspace-scoped remediation. Run that remediation before deleting scratch; no evidence bundle may
be staged while approval cleanup is unverified.

### Future Gate 5: Verify the fresh bundle and state only its consequence

```powershell
uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen python -m ruff check .
git diff --check
```

The generated report must contain exactly the applicable consequence from Task 7. `REACHABLE`
justifies separately scoped durable-session work; `UNREACHABLE` requires an operator disposition;
`INDETERMINATE` leaves the named precondition/observation open. None automatically edits the pool,
closes `P11-FEAT-ZED-RESUME`, or grants another shot.

## Stop conditions

Stop and return to the reviewer if any of these becomes true:

1. Option A requires a change under `src/`, a new approval mode, a one-shot approval id, or shared
   acpx/Zed workspace state.
2. Tests cannot fully stub the keyring/TTY/process boundaries or a required RED/GREEN proof starts a
   real external process.
3. Correct revocation failure handling cannot retain the exact workspace while blocking directory
   cleanup and evidence publication.
4. The command cannot round-trip through the same parser, or a fresh report target cannot be used
   without changing the historical bundle/verifier contract.
5. The report repair requires raw dynamic text, weakening the sanitizer/verifier, changing a Plan
   9.96 sink key/classification, or leaving an unresolved test node.
6. The offline diff extends beyond the four files in the file map or modifies a frozen/evidence/status
   artifact.
7. Any task needs Zed, Redis, acpx, ACP, a TTY ceremony, OS-keyring mutation, network access,
   credentials, or paid-call authority.

An ordinary test failure inside the authorized offline scope is not a stop condition. Diagnose it,
preserve genuine TDD evidence, and continue within the settled design.

## Definition of Done and evidence map

| Claim | Required evidence |
|---|---|
| The Zed child uses the exact workspace that was approved. | RED→GREEN call-boundary test records one resolved `zed-workspace` across creation, durable approve command, relay child `--workspace-root`, launch cwd, and revoke command. |
| The approval exists for every Zed spawn in the window and is not broadened. | Event-ledger test records two child-spawn observations while approval is live, no `--launch-approval-id`, and an exact workspace-scoped durable command; source inspection and the existing end-to-end launch-gate test pin the read-only durable path. |
| Failures cannot silently launch unapproved or leave approval cleanup reported as green. | Approval failure proves `zed_launches: 0`; launch failure proves `finally` revocation; revoke failure proves retained remediable workspace, cleanup false, and no bundle. |
| The future command is executable and not stale prose. | Parser namespace → command → same-parser round-trip proves real-zed mode, 900 seconds, fresh v3 report directory, same workspace, both flags exactly once, and no internal approval id. |
| Every generated report states the required result consequence. | Parameterized exact-text tests for all three findings, nonempty materialization assertion, and unchanged real evidence verifier pass. |
| Plan 9.96 coverage remains truthful. | Surface verifier is green with the existing sink key/classification/evidence tier/test node and corrected schema-limited rationale. |
| The package stayed offline, atomic, and forward-only. | Exact four-file diff, clean tests/Ruff/hygiene/CI, v1/v2 blob checks, historical report/root-cause bytes unchanged, no v3 bundle, and explicit no-live-action PR record. |

Tasks 6–8 completion does not establish `REACHABLE` or `UNREACHABLE`, does not produce new live
evidence, and does not authorize Future Gates 1–5.

## Explicit exclusions and custody

| Excluded item | Custody |
|---|---|
| Any corrected preflight, TTY ceremony, GUI action, Zed launch, or launch-budget grant | Future separately dispatched run package; operator owns machine state and is sole budget authority. |
| Option B / public or probe use of `--launch-approval-id` | Plan 9.96 production security contract; rejected here and unavailable without a separately approved architecture change. |
| Option C / shared acpx and Zed workspace | Rejected Plan 11.24 design; no scheduled implementation. |
| Edits to v1, v2, the committed Plan 11.24 evidence bundle, or the root-cause report | Frozen historical artifacts; cite only. The new run has a distinct `-v3` directory. |
| Changes to `src/optimus`, normal `loadSession` advertisement, durable ACP store/handler, or session history | `P11-FU-1` / `P11-FEAT-ZED-RESUME`; only a future `REACHABLE` result can justify separately scoped design. |
| Origin-A fixture/correlation, Zed refusal-rendering panic, or same-session retry policy | Existing Plan 11.7 / `P9.8-FU-5` / `P11-FU-11` custody; untouched by this probe repair. |
| Pool, roadmap, README, or manufactured plan-index changes | Reviewer documentation-freshness audit; no current Plan 11.24 pointer exists to advance. |
| `CURRENT.md` and reviewer checkpoint updates | Reviewer/operator handoff lane; never stage them in the implementation commit. |

## Plan self-review

- The Status line is written for the post-merge state: v3 is live, Tasks 6–8 are not started, and no
  live authority exists. Both predecessor blob identities are pinned and the header is the only
  required live-version pointer.
- The remedy follows the settled Option A lifecycle and explains why the empty-workspace approval is
  stable. It neither repurposes the one-shot internal slot nor extends the acpx approval.
- Approval lifetime is minimized: workspace creation is early, approval is late, and revocation
  precedes deletion. Revocation failure preserves the exact identity needed to remediate rather than
  falsely claiming cleanup after deleting it.
- The command fix cannot drift silently because the future preflight's parsed namespace is serialized
  and round-tripped by the same parser. A new `-v3` report target prevents collision with immutable
  evidence.
- The report fix includes all three exact v1 consequences and carries the otherwise-easy-to-miss
  Plan 9.96 rationale repair in the same atomic package.
- The prerequisites distinguish offline implementation from future machine state, TTY/GUI actions,
  and launch budget. The one unknown has an explicit prelaunch establishing gate.
- The future run is concrete enough to execute after a separate grant, but every heading and gate
  preserves that `_v3` itself authorizes no process start or launch.
