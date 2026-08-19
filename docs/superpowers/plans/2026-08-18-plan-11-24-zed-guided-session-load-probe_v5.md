# Plan 11.24 v5 — Two-Lifecycle Zed Resume-Observation Amendment

> **Status:** Proposed forward-only successor. `_v4`'s corrected offline contract is PR #180 head
> `d868b55` at authoring and has not yet merged. `_v5` must not merge ahead of that correction. Once
> `_v4` lands and this file subsequently lands, `_v5` is the sole live Plan 11.24 contract: it
> authorizes only the offline implementation tasks below and defines, but does not grant, the later
> two-lifecycle Zed observation. It authorizes no Zed launch, GUI action, TTY ceremony, keyring
> mutation, Gateway/provider call, or paid turn.
>
> **Frozen predecessors:**
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md`, git blob
> `421f9a9595dda1d55b9895b148839de8163e6556`;
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v2.md`, git blob
> `85cea53cbec6ca9faf1cee85f5c81e15999321b8`;
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v3.md`, git blob
> `220000b208059030488c920fef3f15e9f8834e89`; and
> `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v4.md`, corrected
> PR #180 blob `260ad5dc692e03601d48c6f1713238de4fa5c164`. Leave all four byte-identical.
>
> **Live-version pointer:** After the required sequential merges, this `_v5` file supersedes `_v4`
> for all Plan 11.24 authority. `_v4` remains the live offline relay-child argv/diagnostic package;
> its Tasks 9–11 and historical evidence are not redesigned or reopened here. At the time a `_v5` PR
> is opened after the required rebase, record the actual main commit that contains the corrected
> `_v4` blob above; until then, do not state that `_v4` has landed.
>
> **Authoring baseline:** `origin/main` at
> `728a29d0312b0298c3352f5af8a92dda9da954c4` (PR #179 merged). Rebase this plan branch onto the
> then-current `origin/main` only after that mainline contains corrected `_v4`; record that exact
> successor commit in the implementation PR.

## Purpose and settled run-shape ruling

The v1–v4 live ceremony could never answer its intended question. Zed 1.15.1 source at
`b962c0ab00b3d368503d8cd4000a6de2895b535c` shows that `session/load` resumes a known persisted
thread; a fresh `--user-data-dir` has no `ThreadMetadata.session_id`, so its first **Start** takes the
`session/new` path. The v4 offline bisection proves only the preceding handshake: the fixed relay
returns a 345-byte `initialize` response. It does not prove that a fresh Zed thread will send
`session/load`.

This amendment replaces the invalid single-launch observation shape with two bounded lifecycles on
one shared hermetic profile:

1. **Lifecycle A — create and persist.** Zed launches with a newly created hermetic
   `--user-data-dir`; the operator trusts only the generated workspace, starts Optimus once, and
   sends exactly one fixed message. The resulting `session/new` id is expected to become the thread
   metadata id on the optimistic user-message push. Zed then closes.
2. **Lifecycle B — resume and observe.** Zed launches once more with the *same* hermetic profile and
   the same approved workspace. The operator opens the persisted thread from history; they do not
   create a new thread or click **Start** again. That restored-thread action is the only path that
   supplies `resume_thread_id` to Zed's ACP client and can issue `session/load`.

The one remaining inference is deliberately not assumed: whether Lifecycle A's single send still
persists a resumable row when `session/prompt` fails under `--no-auto-start`, before any model turn.
Tasks 12–13 establish it with the real independently authored `acpx` client and an isolated agent
before a Zed grant can be considered. A project-authored JSON-RPC client or raw-framing harness is
forbidden for that protocol evidence.

The new falsifiable prediction is:

> In Lifecycle B, the captured `session/load.params.sessionId` equals the `sessionId` returned by
> Lifecycle A's captured `session/new` response. A result `{}` is `REACHABLE`; a captured
> `session/load` protocol/method error for that same id is `UNREACHABLE`; every other state is
> `INDETERMINATE` with a named reason.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| plan/state | Corrected `_v4` blob `260ad5dc692e03601d48c6f1713238de4fa5c164` has merged to `main` before any `_v5` implementation branch is cut. | no | operator | merely unauthorized; PR #180 must be reviewed and merged first. |
| code/state | `_v4` Tasks 9–10 and their CI have merged before the v5 harness is changed or a new live report target exists. | no | Cursor + operator | genuinely absent; the independent offline repair is its own prerequisite. |
| evidence/state | The v3 four-file bundle and root-cause report remain byte-exact and verifier-valid; revocation remains confirmed and former run/scratch roots remain absent. | yes | Codex + reviewer | n/a; `_v5` cites, never recreates or edits, this evidence. |
| tooling/binaries | The independently authored `acpx` binary can drive `session/new` → one `session/prompt` attempt → saved-session reload against the isolated launcher, and its version/SHA are recordable. | unknown | implementing agent + operator | merely unauthorized to run the one-approval agent-only drive; Task 13 establishes this before a Zed ceremony. |
| services | The Task 13 drive has no running/started Gateway or provider path and invokes the isolated agent with `--no-auto-start`; its prompt attempt must fail cleanly before a model call. | unknown | operator | merely unauthorized to inspect and enforce the machine boundary; Task 13 establishes it. |
| credentials/authority | Task 13 has one workspace-specific durable-approval ceremony for its throwaway agent workspace, then revokes and verifies it; no credential/keyring mutation or Zed authority is granted. | no | operator | merely unauthorized; exactly one operator `y` is required for that no-Zed drive. |
| human interaction | The operator can perform the Task 13 `y` approval and later the two Zed lifecycle GUI actions, including opening a history thread rather than a new thread. | no | operator | merely unauthorized; the live actions remain behind a later separate grant. |
| cost | The no-Gateway Task 13 path is confirmed. If it is not, a single bounded paid turn has a separately recorded provider/model, numeric maximum cost, and operator grant before Lifecycle A. | unknown | operator | merely unauthorized until Task 13 resolves the no-Gateway path and, only if needed, the operator grants the exact cost. |
| live authority | Exactly two Zed launches, one shared profile, one fixed message, no third launch, and no retry have a separate reviewer-checked operator grant after Tasks 12–14 and Task 13 evidence are green. | no | operator | merely unauthorized; this plan defines no implicit launch budget. |

Task 13 is the required early establishing task for the three `unknown` prerequisites. A failed,
ambiguous, Gateway-touching, or non-`acpx` drive is a terminal `PRECONDITION_UNMET`, not permission to
substitute a project protocol client or spend a Zed shot.

## Global constraints

- Start every implementation branch from current `origin/main` after corrected `_v4` is present;
  read this plan and the reviewer checkpoint Current State before mutation. Never reuse a capture,
  amendment, or spent-live-run branch.
- Preserve v4's relay contract: `child_executable` appears once; child stderr remains private raw
  scratch with only the optional bounded sanitized string `relay_child_stderr_excerpt` eligible for
  evidence. Do not change `SCHEMA_SUMMARY`, the evidence schema, `REQUIRED_FIELDS`, historical
  verifier acceptance, ACP byte opacity, or either existing report bundle.
- Use `acpx` as the real client for Task 13 and all ACP-protocol live evidence. The probe may compose
  and invoke `acpx` CLI commands and parse its sanitized output, but it must not construct JSON-RPC,
  frame `Content-Length`, use `NdjsonSubprocessSession`, or directly send `initialize`,
  `session/new`, `session/prompt`, or `session/load` itself.
- The Task 13 client command uses the isolated launcher, `--no-auto-start`, an isolated acpx home,
  `--auth-policy skip`, `--deny-all`, no allowed tools, a fixed content-free message, and an
  environment that omits Gateway/provider credentials. It starts no Redis, Gateway, Zed, or provider
  process. An unexpected model/Gateway attempt is a stop, even if a later response is received.
- The live run has one generated `zed-workspace`, one durable Option-A approval held through both
  lifecycles then revoked/verified, one hermetic `--user-data-dir`, two distinct relay run ids, and
  one monotonic **900-second total** deadline. Do not clean the shared profile, settings, workspace,
  or relay capture between Lifecycle A and Lifecycle B; final cleanup follows Lifecycle B only.
- Lifecycle A permits exactly one user message and no retry. Lifecycle B opens the existing history
  row; it must not start another new Optimus thread. No third Zed launch, relaunch, agent switch, or
  second message is permitted.
- Raw relay directories, raw child stderr, ambient paths, credentials, unsanitized command output,
  and GUI logs never enter a committed report. Verify each raw relay capture in the throwaway run root
  before reconstructing sanitized per-lifecycle evidence; remove all scratch only after revocation
  and final cleanup verification.
- The v5 manifest adds a **conditional** `resume_lifecycle` record only for the v5 report shape. It
  contains the two lifecycle labels, sanitized response/request identifiers needed for equality,
  shared-profile assertion, and per-lifecycle digests. Older manifests remain valid without that
  record. The existing optional `relay_child_stderr_excerpt` remains a string of at most 4000
  characters; a two-lifecycle run joins only already-sanitized, one-line lifecycle excerpts within
  that same bound.
- Do not change normal Optimus `loadSession` advertisement or durable session behavior. The isolated
  scratch patch remains limited to temporary `loadSession: true` plus `{}` for `session/load`.

## File map

| Path | Required change |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Add the acpx-driven no-Gateway establishing mode; add the two-lifecycle shared-profile orchestrator, two relay capture labels, session-new/session-load correlation, 900-second total deadline, v5 materialization, and exact result consequences. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Genuine RED→GREEN tests for the acpx-only driver, no embedded project protocol client, prompt-error persistence result, same profile/two launches/one message lifecycle wiring, capture separation, correlation, cleanup, and no paid fallback without a recorded authority seam. |
| `tools/verify_plan1119_zed_reprobe_evidence.py` | Keep legacy validation unchanged; validate the optional v5 `resume_lifecycle` shape, exactly two launches, per-lifecycle files/digests, and equality between Lifecycle A `session/new` and Lifecycle B `session/load`. |
| `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py` | Preserve legacy-manifest acceptance; add v5 positive and mismatch/rejection cases for launch count, profile identity, missing create id, wrong load id, missing response, and unsanitized/oversized diagnostic data. |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Update only the probe materialization/agent-drive entries whose actual persistence surface changes; each new exact key must use the named final unit test and explain that only schema-limited sanitized data reaches the report. |
| `reports/plan-11-24-agent-protocol-persistence-establishing-drive.md` | Task 13's committed, sanitized, no-Zed `acpx` evidence record; it is an agent-protocol prerequisite, never a Zed finding. |
| `reports/plan-11-24-zed-guided-session-load-probe-v5/` | Future-only fresh evidence bundle with separate sanitized Lifecycle A/B relay files; never create it in a unit test or before the two-launch grant. |
| `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v5.md` | Check Task 12–14 boxes only after their own stated gates pass. |

## Task 12: Add an `acpx`-driven no-Gateway persistence establishing mode

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Offline harness/code change. Unit tests stub every process, trust, clock,
and filesystem boundary; no real `acpx`, agent, approval, Zed, Redis, Gateway, or network action is
part of this task.

**Interfaces:** Add `run_plan1124_agent_protocol_drive(parent_workspace: Path) -> dict[str, Any>` and
the parser mode `agent-protocol`. It composes the existing `build_acpx_command()` with an isolated
launcher and fixed prompt text, runs `acpx … exec <fixed-message>`, exports/imports the saved acpx
session, then runs `acpx … status` to cause the independently authored client to reload it. Its
sanitized result has `zed_launches: 0`, `origin_a_launches: 0`, `prompt_attempt`,
`session_new_response`, `session_load_exchange`, `no_gateway_path_established`, and a named
indeterminate reason when the sequence cannot be established.

- [ ] **Step 1: Establish the corrected baseline.** Read corrected `_v4`, the root-cause report, and
  this plan. Confirm the v4 code/test package is merged before starting. Read
  `build_acpx_command()`, `_run_acpx_against_isolated_agent()`, and the source-level real-client
  guards in `tests/unit/tools/test_run_plan987_acpx_live_evidence.py`; retain `acpx` rather than
  copying `operator_verify.py` or an NDJSON harness.

- [ ] **Step 2: Write genuine RED unit tests.** Add tests named
  `test_agent_protocol_drive_delegates_all_protocol_traffic_to_acpx` and
  `test_agent_protocol_drive_requires_erroring_prompt_and_matching_saved_load`. Stub `_run`,
  `_run_interactive_required`, `_revoke_temporary_approval`, and the isolated preparation seams.
  Assert the composed command has the existing `acpx --format json --json-strict --no-terminal
  --auth-policy skip --deny-all --allowed-tools ""` prefix and uses `exec`, export/import, and
  `status`; assert no `jsonrpc`, `Content-Length`, `NdjsonSubprocessSession`, or handwritten ACP
  request appears in the new driver source. Feed sanitized acpx records in which `session/new`
  returns `session-a`, the prompt errors, and the reload returns `{}` for `session-a`; require the
  result to establish the no-Gateway path. Feed a successful prompt, missing session id, different
  reload id, or Gateway-attempt marker and require `PRECONDITION_UNMET`.

- [ ] **Step 3: Run RED.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "agent_protocol_drive" -q
  ```

  Expected: FAIL because the mode/driver and its correlation guard do not exist. A test that sends
  project-authored ACP messages is invalid RED evidence.

- [ ] **Step 4: Implement the minimum acpx-only driver.** Reuse the isolated source/launcher,
  `build_acpx_command()`, `_isolated_environment()`, and workspace-specific durable approval/revoke
  helpers. Give `acpx exec` the exact fixed message `Persist this probe thread only; do not use tools
  or modify files.` Require a non-successful `session/prompt` attempt under `--no-auto-start`, then
  export/import and `status` through `acpx`. Parse only the client-produced, sanitized records;
  persist typed booleans, ids, digests, and fixed reason codes—never raw stdout/stderr. Revoke and
  verify the sole agent-workspace approval before cleanup; a revoke failure retains the exact
  workspace and blocks report materialization.

- [ ] **Step 5: Prove GREEN without a real process.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -k "agent_protocol_drive or raw_acpx_agent_command" -q
  uv run --frozen python -m ruff check tools/probe_p11_zed_session_load.py tests/unit/tools/test_probe_p11_zed_session_load.py
  ```

  Expected: all protocol traffic is demonstrably delegated to acpx; no Zed launch, service start,
  trust prompt, keyring mutation, or network request occurs in tests.

## Task 13: Establish the no-Gateway persistence premise with real `acpx`

**Owner:** Operator executes after a separate no-Zed approval; Cursor records; Codex reviews.

**Scope classification:** Real ACP-protocol evidence with a real independently authored client. It is
not a Zed run and spends no Zed launch budget. It requires the one `y` approval identified in the
prerequisites table and is the required early task before the live ceremony.

- [ ] **Step 1: Record the narrow no-Zed grant and recheck the boundary.** The reviewer checkpoint
  must name the current commit, exact `acpx --version`/SHA, isolated launcher SHA, one durable
  agent-workspace approval, `zed_launches: 0`, origin-A exclusion, and the statement that no Redis,
  Gateway, provider, or Zed process will be started. Confirm the v5 report directory is absent and
  no v5 live grant exists.

- [ ] **Step 2: Execute only the establishing drive.** In an interactive terminal, create the
  throwaway parent and run the generated mode once; approve only its generated agent workspace when
  asked, then allow its mandatory revoke/inspect cleanup to finish.

  ```powershell
  $probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-agent-protocol-persistence'
  New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
  uv run --frozen python tools/probe_p11_zed_session_load.py --mode agent-protocol $probeParent
  ```

  Require `zed_launches: 0`, `origin_a_launches: 0`, a captured `session/new` id, an erroring
  `session/prompt` attempt, a matching `session/load` `{}` response, no-Gateway evidence, durable
  approval revocation confirmed by `inspect` exit 1, and throwaway-root removal. Do not start Zed,
  Redis, or a Gateway; do not repeat the command.

- [ ] **Step 3: Record the only permissible conclusion.** Create
  `reports/plan-11-24-agent-protocol-persistence-establishing-drive.md` from the sanitized sidecar.
  It records client/launcher provenance, the sequence/result, zero Zed launches, no-Gateway fact,
  revocation/cleanup result, and one of these exact dispositions:

  | Establishing result | Consequence |
  |---|---|
  | matching `session/new` → errored prompt → `session/load {}` with no Gateway | The no-Gateway Lifecycle A message path is established; proceed to Task 14 and later seek the separate two-launch grant. |
  | prompt succeeds, touches Gateway/provider, lacks a matching saved load, or cleanup/revocation fails | `PRECONDITION_UNMET`; do not launch Zed. A single paid-turn fallback requires a new reviewer-checked operator grant naming one message, model/provider, and a numeric cost ceiling. |

  The report must state that this is not a finding about Zed and must not quote raw command output,
  session content, credentials, paths, or approval identifiers.

- [ ] **Step 4: Verify and commit the prerequisite record.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Commit only the authorized harness/tests/audit/plan checkbox and sanitized prerequisite report.
  Do not create the v5 Zed bundle, change the pool/roadmap/README, or imply a Zed outcome.

## Task 14: Implement the shared-profile two-lifecycle harness and v5 classifier

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Offline multi-file harness/verifier patch. All tests stub GUI launches,
approval, clock, client commands, and filesystem roots. This task creates no real profile, report
bundle, Zed process, prompt, provider call, or keyring mutation.

**Interfaces:** Add `run_plan1124_two_lifecycle_real_zed(parent_workspace: Path, *, timeout_s: float,
report_dir: Path) -> dict[str, Any>` behind parser mode `real-zed-resume`. It uses
`PLAN1124_LIFECYCLE_A_RUN_ID = "plan1124-create"` and
`PLAN1124_LIFECYCLE_B_RUN_ID = "plan1124-resume"`, one `run_root/zed-home`, one
`run_root/zed-appdata`, and one `run_root/zed-workspace`. Its `resume_lifecycle` record has
`shared_profile: true`, both per-lifecycle relay digest pairs, the Lifecycle A `session/new` id, and
the Lifecycle B `session/load` exchange. It returns `zed_launches: 2` only after both lifecycle
launch calls are attempted; it materializes a fresh v5 bundle only after final cleanup succeeds.

- [ ] **Step 1: Write genuine RED lifecycle and verifier tests.** Add
  `test_two_lifecycle_run_reuses_one_profile_and_separates_relay_captures`,
  `test_resume_classifier_requires_load_id_from_lifecycle_a_session_new`, and
  `test_v5_manifest_requires_two_lifecycle_correlation_but_legacy_manifests_still_pass`. Stub
  `_launch_zed_once` and assert: the same resolved user-data root and workspace reach both launches;
  the first relay uses `plan1124-create`, the second `plan1124-resume`; no cleanup occurs between
  them; the single monotonic deadline is decremented rather than reset; and final cleanup/revocation
  occurs once after Lifecycle B. Build synthetic sanitized captures where `session/new` returns
  `session-a` and B loads `session-a`; require `REACHABLE` only for `{}` and `UNREACHABLE` only for an
  error on that same id. Reject one/three launches, a changed profile, a missing A id, a different B
  id, a missing B response, or an unverified raw capture.

- [ ] **Step 2: Run RED.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -k "two_lifecycle or resume_classifier or v5_manifest" -q
  ```

  Expected: FAIL because the existing single lifecycle overwrites a relay run id, removes its
  hermetic root in `finally`, and the verifier has no v5 correlation rule.

- [ ] **Step 3: Implement only the audited run shape.** Use distinct capture directories, verify
  each raw relay directory with `verify_relay_capture()`, then reconstruct and materialize only
  sanitized `relay/lifecycle-a/{zed-to-agent,agent-to-zed}.bin` and
  `relay/lifecycle-b/{zed-to-agent,agent-to-zed}.bin`. Hold the Option-A approval and all three
  shared roots across A/B, then revoke/inspect and clean only after B. Add the parser-derived
  `--mode real-zed-resume`, `--zed-launch-timeout-seconds`, and `--report-dir` contract; require a
  fresh `reports/plan-11-24-zed-guided-session-load-probe-v5/` directory and a total timeout in
  `[60, 900]`. The report consequence is fixed schema-limited prose and never interpolates raw ACP.

  Extend the verifier only when `resume_lifecycle` is present: require exactly two launches, both
  lifecycle file pairs/digests, `shared_profile is true`, a Lifecycle A `session/new` id, and a
  Lifecycle B `session/load` request for the same id. Preserve the old branch unchanged for all
  historical manifests and preserve v4's optional string stderr excerpt contract.

- [ ] **Step 4: Classify every new persistence surface truthfully.** Update the Plan 9.96 manifest
  for the exact new functions emitted by the surface verifier: the acpx-drive sidecar/report writer,
  v5 lifecycle materializer, and any new verifier export. Each rationale must state the schema-only
  fields and sanitizer, and each `test_node` must resolve to the named Task 12/14 test. Do not silence
  or blanket-exclude a newly discovered sink.

- [ ] **Step 5: Prove GREEN and publish the offline implementation only.**

  ```bash
  uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe/manifest.json
  uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v3/manifest.json
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen python -m ruff check .
  git diff --check
  ```

  Expected: both historical manifests still verify byte-for-byte; unit fixtures prove the v5
  two-lifecycle contract; no `reports/plan-11-24-zed-guided-session-load-probe-v5/` exists yet; and
  no live/interactive/keyring/network/provider action ran. Commit and open a draft PR; do not merge
  or run the future gates without the separate grant.

## Future gates — definition only, not authorization

### Future Gate 1: Recheck v5 implementation and the establishing evidence

After Tasks 12–14 merge, a reviewer confirms the corrected `_v4` commit is in main, the Task 13
record exists with its exact disposition, both historical bundles still verify, and the implementation
commit/CI are clean. If Task 13 is `PRECONDITION_UNMET`, stop here unless the operator records the
one-message provider/model/numeric-cost fallback authority; it never becomes implicit.

### Future Gate 2: Record the one shared-profile/two-launch grant

The reviewer checkpoint records the exact implementation commit, parser-derived command digest,
total 900-second limit, one fixed Lifecycle A message, shared profile identity, two distinct relay
run ids, and permission for exactly two Zed launches under one Option-A approval lifecycle. The grant
forbids a third launch, a retry, a second message, origin-A, an ambient profile, and any pool/roadmap
closure. If a paid fallback is required, the same entry records its one provider/model turn and
numeric maximum cost; otherwise no Gateway/provider call is allowed.

### Future Gate 3: Fresh no-launch boundary check

```powershell
$probeParent = Join-Path $env:LOCALAPPDATA 'Optimus\p11-24-zed-resume-v5'
$reportDir = 'reports/plan-11-24-zed-guided-session-load-probe-v5'
New-Item -ItemType Directory -Force -Path $probeParent | Out-Null
if (Test-Path -LiteralPath $reportDir) { throw "Fresh v5 report directory already exists" }
git status --short --branch
git rev-parse HEAD
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
```

Require the granted commit, no in-scope Zed process, no existing target report directory, and no
source/credential drift. Any failure leaves both launch slots unspent.

### Future Gate 4: Lifecycle A — create and persist exactly once

Run the parser-derived canonical command once; do not retype flags or start a second process.

```powershell
uv run --frozen python tools/probe_p11_zed_session_load.py --mode real-zed-resume --zed-launch-timeout-seconds 900 --report-dir $reportDir $probeParent
```

When Lifecycle A's hermetic Zed window appears, trust only its generated workspace if prompted,
select Optimus, click **Start** once, and send exactly the Gate 2 fixed message once. Close the Zed
window. The harness retains the shared profile, workspace approval, settings, and raw Lifecycle A
relay capture; it must not publish evidence or clean these roots yet.

### Future Gate 5: Lifecycle B — resume the persisted thread exactly once

The same running command launches Zed a second time with the same `--user-data-dir` and workspace.
Open the Lifecycle A thread from history. Do not click **Start**, create **New optimus Thread**, send
a message, switch agents, restart manually, or rerun the command. Close the second window after the
bounded observation. The harness then verifies both raw captures, revokes/inspects the workspace
approval, cleans the roots, and materializes the sanitized v5 bundle only if all final predicates
pass.

### Future Gate 6: Verify the new bundle and state only the evidence consequence

```powershell
uv run --frozen python tools/verify_plan1119_zed_reprobe_evidence.py --manifest reports/plan-11-24-zed-guided-session-load-probe-v5/manifest.json
uv run --frozen pytest tests/unit/tools/test_plan117_custody_relay.py tests/unit/tools/test_probe_p11_zed_session_load.py tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py tests/unit/docs/test_open_work_pool_hygiene.py -q
uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
uv run --frozen python -m ruff check .
git diff --check
```

`REACHABLE` requires the B request id equality plus `{}` response and only justifies a separately
scoped durable-session design. `UNREACHABLE` requires the matching captured error and an operator
disposition. `INDETERMINATE` names the failed precondition or incomplete observation and grants no
additional shot. None closes `P11-FEAT-ZED-RESUME`, modifies frozen evidence, or creates automatic
follow-up authority.

## Stop conditions

Stop and return to the reviewer if any of these occurs:

1. Corrected `_v4` is not merged, or any implementation would modify v1–v4, their reports, or their
   bundles instead of creating forward-only v5 artifacts.
2. The establishing drive needs a project-authored ACP client, raw framing, a fake as the protocol
   evidence tier, Zed, Redis/Gateway startup, a provider call, more than one approval, or a second
   attempt.
3. The Task 13 prompt does not error cleanly before a model call, or it cannot prove the matching
   no-Gateway saved-session reload. Do not infer persistence or take a Zed shot.
4. A paid fallback lacks an operator-recorded one-message model/provider and numeric cost ceiling.
5. The two-lifecycle harness changes profile/workspace/approval identity, cleans any shared root
   between launches, needs a third launch/retry/second message, or cannot make the B history action
   distinguishable from a new thread.
6. The relay captures cannot be separately verified raw before sanitization, child stderr enters ACP
   bytes/report files, or the optional v4 diagnostic contract must be broken.
7. V5 validation would change the existing evidence schema/required fields, reject either historical
   bundle, accept a mismatched A/B session id, or weaken sanitizer/digest/report-directory checks.
8. A new Plan 9.96 persistence surface cannot receive a truthful exact classification and resolvable
   test node, or the offline diff exceeds the stated file map.

## Definition of Done and evidence map

| Claim | Required evidence |
|---|---|
| The remaining no-Gateway persistence inference is established rather than assumed. | Real `acpx` Task 13 record proves `session/new` id, erroring prompt, matching saved-session `session/load {}`, zero Zed launches, no Gateway/provider path, approval revocation, and cleanup; any other result is terminal `PRECONDITION_UNMET`. |
| The live harness creates a genuine resume opportunity. | Unit event ledger proves one profile/workspace/approval through exactly two launches, separate raw capture ids, no intervening cleanup, one total 900-second deadline, one message seam, and final-only cleanup. |
| The live result is causally classified. | V5 verifier requires the exact A `session/new` id to equal B `session/load.params.sessionId`, `{}` for REACHABLE, an error for UNREACHABLE, and a named reason otherwise. |
| Custody and diagnostics remain safe. | Each lifecycle raw relay capture verifies before reconstruction; only sanitized per-lifecycle bytes and the bounded optional stderr string can enter the v5 bundle; relay summary v1 and old bundles remain valid. |
| ACP evidence is independently driven. | Source-level guard and Task 13 provenance show acpx alone drives protocol traffic; no project JSON-RPC/framing client appears in the drive. |
| The plan remains forward-only and does not spend live authority implicitly. | Frozen v1–v4 blob checks, v5-only file diff, hygiene/Plan 9.96/Ruff passes, reviewer checkpoint grants, and the absence of a v5 report before Future Gates 1–5. |

## Explicit exclusions and custody

| Excluded item | Custody |
|---|---|
| Normal `loadSession` advertisement, durable store, session identity/history, and handler implementation | `P11-FU-1` / `P11-FEAT-ZED-RESUME`; a v5 `REACHABLE` result is evidence only, not implementation authority. |
| Any Zed launch, GUI action, two-launch grant, or paid turn | Future Gates 1–6; operator owns machine state, interaction, and cost authority. |
| A project-authored ACP client, fake protocol driver, raw framing, or prompt injection automation | Forbidden by the ACP evidence-tier rule; `acpx` is mandatory. |
| Changes to Option A, `--launch-approval-id`, or shared acpx/Zed workspace | Frozen v3/Plan 9.96 ruling; unavailable without a separate architecture amendment. |
| Origin-A fixture/correlation, refusal-rendering, same-session retry policy, pool/roadmap/README, and checkpoint edits | Existing `P11-FEAT-ZED-RESUME`, `P9.8-FU-5`, `P11-FU-11`, and reviewer/operator custody. |

## Plan self-review

- The source-backed reason v1–v4 cannot observe `session/load` is explicit: a fresh profile produces
  `session/new`; a persisted metadata row requires the Lifecycle A send and a restart.
- The only inference beyond source is an early, real-acpx, no-Zed establishing task. Its failure stops
  rather than silently spending a Zed shot or manufacturing a client.
- The live run is bounded to one shared profile, two launches, one message, no retry, and one total
  900-second deadline; Lifecycle B opens history rather than a new thread.
- The classifier requires the cross-lifecycle session-id equality that the observation actually asks
  about, while preserving old evidence acceptance and v4's additive diagnostic contract.
- `_v4` remains intact as the offline relay/argv/evidence amendment. `_v5` cannot claim it has landed
  until the required sequential merge records the real main commit.
