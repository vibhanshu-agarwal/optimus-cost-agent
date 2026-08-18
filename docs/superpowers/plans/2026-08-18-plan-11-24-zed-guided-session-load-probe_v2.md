# Plan 11.24 v2 — Operator-Guided Zed `session/load` Probe Amendment

> **Status:** Live version of Plan 11.24. This file supersedes the execution authority in the frozen v1 plan only where stated below, authorizes only offline Task 5, and records Task 5 as not started. It authorizes no Zed launch.
>
> **Frozen predecessor:** `docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe.md`, git blob `421f9a9595dda1d55b9895b148839de8163e6556`. Leave it byte-identical.
>
> **Authoring baseline:** `origin/main` at `fb74c02cacbc89f096906f1e741480337380c571`.

## Purpose and amendment boundary

The single live launch authorized by Plan 11.24 v1 has been spent. It ended
`INDETERMINATE / RELAY_FAILURE`; it did not establish either `REACHABLE` or
`UNREACHABLE`. The failed shot also exposed a latent configuration-path defect in the
hermetic Zed harness. This amendment records that exhausted authority, corrects the
pinned-Zed configuration contract, and schedules one offline repair package before any
future live decision.

This amendment authorizes only the offline WP-10 code, test, and surface-audit changes
defined in Task 5. A corrected live re-shot remains a separate budget expansion owned
by the operator. Approval or merge of this amendment does not grant that expansion.

There is no committed pool, roadmap, README, or other index entry pointing to the v1
plan filename at this baseline. The supersession statement above is therefore the live
version pointer. Do not create a tracking row merely to point at this file, and do not
rename the existing `reports/plan-11-24-zed-guided-session-load-probe` evidence
directory contract.

## Settled evidence and causality

These are amendment inputs, not retroactive completion claims against the immutable v1
checkboxes:

- Plan 11.24 Tasks 1 and 2 landed on `main` through PR #174. Their offline harness and
  guided-timeout behavior remain accepted and unchanged.
- The authorized Task 3 preflight and Task 4 launch were attempted. The launch budget is
  exhausted even though no verifier-valid relay bundle was produced.
- The terminal classification is `INDETERMINATE / RELAY_FAILURE`. Absence of a capture
  does not prove protocol reachability or unreachability.
- Across the five spent shots spanning Plan 11.19 and Plan 11.24, shot 1 had the
  separate proximate cause that the Zed CLI wrapper produced no window. Shot 2 had the
  separate proximate cause that arguments reached the app binary in an invalid form
  (`returncode: 2`). Do not rewrite either failure as a settings-path failure.
- The settings-path defect was latent for all five shots and directly explains why shots
  3–5 could not load the seeded `agent_servers` entry. It is therefore a necessary repair
  before a corrected re-shot, but not the sole proximate cause of all five failures.
- The reviewer handoff record remains
  `docs/superpowers/reviews/plan-11-24-review-checkpoints.md`. It is gitignored by
  design and must not be staged.

## Corrected pinned-Zed contract

The probe pins Zed 1.15.0 at source commit
`e17dc4f9d50db73a458b64dcce50ecd4878b98a3`. At that commit:

1. `crates/zed/src/main.rs` parses the app binary's `--user-data-dir` argument and
   calls `paths::set_custom_data_dir(dir)`.
2. `crates/paths/src/paths.rs::config_dir()` resolves a custom data directory to
   `<custom-data-dir>/config`.
3. `crates/paths/src/paths.rs::settings_file()` appends `settings.json`.

Accordingly, a discovered invocation with
`invocation.user_data_root == hermetic_zed_root` reads settings from:

```text
Path(invocation.user_data_root) / "config" / "settings.json"
```

The v1-era `<run_root>/zed-appdata/Zed/settings.json` assumption is false for the pinned
binary. An `APPDATA` bind neither selects nor repairs the custom configuration path.

## Superseded v1 provisions

The following v1 provisions are superseded in full:

- The Task 4 instruction to execute the real-Zed command exactly once has been consumed.
  It is historical evidence, not reusable authority.
- The global `no budget expansion` boundary remains effective unless the operator makes
  a new, explicit decision. Nothing in Task 5 relaxes it.
- Any text that implies a second launch follows automatically from an `INDETERMINATE`
  result is void. A future launch requires fresh authority and a separately reviewed
  run package after Task 5 merges.
- Any harness assumption that Zed reads settings through `%APPDATA%/Zed` is replaced by
  the corrected pinned-Zed contract above.

All other v1 constraints remain in force, including hermeticity, sanitization, result
discipline, origin-A exclusion, and the prohibition on inferring a Zed result from normal
Optimus non-advertisement.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| plan/state | This `_v2` amendment is reviewed, approved, and merged before Cursor starts WP-10. | no | Codex + operator | merely unauthorized until the operator approves the authored bytes and the amendment merges. |
| code/state | The real-Zed caller seeds the exact `invocation.user_data_root` configuration path and no longer installs the inert APPDATA bind. | no | Cursor | genuinely absent but small and buildable now; Task 5 supplies it offline. |
| tooling/binaries | The repository's frozen `uv` environment can run pytest, Ruff, the Plan 9.96 surface verifier, and Git without dependency installation drift. | yes | implementing agent | n/a; stop if the frozen environment cannot execute the named gates. |
| services | Task 5 requires no Redis, ACP server, Zed process, daemon, port, or network service. | yes | implementing agent | n/a; any service requirement is scope drift. |
| credentials/authority | Task 5 requires no Optimus credentials, provider keys, paid-call authority, or live-launch authority. | yes | implementing agent | n/a; any credential or launch requirement is scope drift. |
| human interaction | Task 5 requires no GUI action, trusted-workspace click, Agent-panel action, or TTY ceremony. | yes | implementing agent | n/a; no live ceremony belongs in this repair. |
| cost | Task 5 is offline and makes no Gateway, provider, or other paid call. | yes | implementing agent | n/a; any paid call is forbidden. |
| future live authority | A corrected guided re-shot has a fresh operator-approved launch budget and run package. | no | operator | merely unauthorized and explicitly excluded from this amendment's Definition of Done. |

Task 5 may not start until the first row becomes `yes`. The final row is deliberately
unsatisfied because no Definition-of-Done claim below depends on a re-shot.

## File map

Task 5 is one atomic implementation package. No other production, report, pool, roadmap,
README, or plan file is in scope.

| Path | Required change |
|---|---|
| `tools/probe_p11_zed_session_load.py` | Seed `<user-data-dir>/config/settings.json`; remove the inert APPDATA bind and stale metadata while preserving the classified function name. |
| `tests/unit/tools/test_probe_p11_zed_session_load.py` | Add a call-boundary regression test and update the direct layout tests and stub fixture. |
| `docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json` | Update only the two affected `test_node` values and their now-false APPDATA rationales/sanitizer descriptions; preserve sink keys and classifications. |

## Task 5: Repair hermetic settings seeding offline

**Owner:** Cursor implements; Codex reviews.

**Scope classification:** Multi-file changeset, limited to the three files in the file
map. The source, tests, and surface-audit metadata form one indivisible commit.

**Interface contract:** `run_plan1119_real_zed()` must pass
`Path(invocation.user_data_root)` to the existing
`seed_hermetic_zed_settings` function. That function must create and write
`<user-data-dir>/config/settings.json` before `_launch_zed_once` observes the
invocation. `invocation.environment_bind` remains its discovered default `()`.

- [ ] **Step 1: Establish the implementation baseline and stop conditions.**
  - Start a fresh Cursor branch from the then-current `origin/main`; do not reuse the
    guided-capture branch.
  - Read this v2 plan, the reviewer checkpoint Current State, and the dispatched WP-10
    package before mutation; verify their settled facts against the tree.
  - Confirm the v1 blob still equals
    `421f9a9595dda1d55b9895b148839de8163e6556`.
  - Grep `tools/verify_plan1119_zed_reprobe_evidence.py` and its unit tests for
    `hermetic_settings`, `appdata_bind`, and the old settings path. Stop if the evidence
    verifier depends on the old key or layout; do not weaken it.

- [ ] **Step 2: Write the failing call-boundary regression first.**
  - In `_install_stubbed_real_zed`, replace the seed-discarding
    `lambda *_a, **_k: settings` seam with a spy that records the first positional
    argument and calls through to the real `seed_hermetic_zed_settings`.
  - Add `test_run_plan1119_real_zed_seeds_discovered_user_data_root` and assert all four
    boundary facts:
    1. the caller passes `Path(invocation.user_data_root)`;
    2. `<user-data-root>/config/settings.json` exists before `_launch_zed_once` runs;
    3. `<user-data-root>/Zed/settings.json` and every `zed-appdata` settings candidate are
       absent; and
    4. the launched `invocation.environment_bind == ()`.
  - Prove this exact test is RED against the pre-fix production path. Its diagnostic must
    show that the caller supplied `<run-root>/zed-appdata`, not the discovered user-data
    root. Record the command and failure in the PR description; do not mark this step
    complete from a synthetic failure.

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py::test_run_plan1119_real_zed_seeds_discovered_user_data_root -q
  ```

- [ ] **Step 3: Implement the minimum production correction.**
  - Keep the public/classified function name `seed_hermetic_zed_settings`. Change its
    parameter from the APPDATA-root concept to `user_data_dir`, rewrite the false
    docstring, create `Path(user_data_dir) / "config"`, and write `settings.json` there.
  - At the only real-Zed call site, remove
    `appdata_root = run_root / "zed-appdata"` and pass
    `Path(invocation.user_data_root)` directly. Do not derive a parallel root.
  - Delete `hermetic_appdata_environment_bind` and the reassignment that installs it.
    Do not replace it with another environment bind.
  - In `hermetic_settings`, replace `appdata_bind` with
    `config_dir: str(Path(invocation.user_data_root).resolve() / "config")`.
  - Do not launch Zed, acpx, Redis, an ACP server, or anything networked while developing
    or verifying this change.

- [ ] **Step 4: Repair direct tests and the classified-sink manifest without weakening either.**
  - Rename
    `test_seed_hermetic_settings_uses_windows_appdata_zed_layout` to
    `test_seed_hermetic_settings_targets_custom_data_dir_config`; rewrite its docstring
    and assertions for `config/settings.json`, including negative assertions for the old
    `Zed/` layout.
  - Keep `test_seed_hermetic_settings_and_launcher_stay_under_scratch`; remove its bind
    assertions and make it prove the corrected path remains inside scratch.
  - Update the two `seed_hermetic_zed_settings` audit entries to point at the renamed
    direct test. Rewrite only their stale `APPDATA bind` / `APPDATA/Zed` rationale and
    sanitizer text to describe the custom-data `config/` path.
  - Preserve the function name, both sink keys, all sink classifications, and the third
    launcher's existing `test_node`. A stale, missing, or reclassified sink is a defect,
    not a verifier problem to route around.

- [ ] **Step 5: Prove GREEN at the boundary and through all affected contracts.**

  Run these gates after the minimum fix:

  ```bash
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py::test_run_plan1119_real_zed_seeds_discovered_user_data_root -q
  uv run --frozen pytest tests/unit/tools/test_probe_p11_zed_session_load.py -q
  uv run --frozen pytest tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py -q
  uv run --frozen python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
  uv run --frozen pytest tests/unit/docs/test_open_work_pool_hygiene.py -q
  uv run --frozen python -m ruff check .
  ```

  The surface verifier must report zero unclassified sinks, zero stale manifest entries,
  and zero unresolved test nodes. The hygiene suite must remain green without adding a
  Plan 11.24 pool/index row.

- [ ] **Step 6: Review the atomic diff and publish only the offline repair.**
  - Confirm `git diff --check` is clean.
  - Confirm `git diff --name-only` lists exactly the three Task 5 files.
  - Confirm `git grep hermetic_appdata_environment_bind` returns no match.
  - Confirm the frozen v1 blob hash is unchanged and no report directory or reviewer
    checkpoint is staged.
  - Commit once as
    `fix(zed): seed hermetic settings to custom-data config dir`, push the Cursor branch,
    and open one draft PR under the standing WP-10 authorization. Do not merge.
  - Record the genuine RED and subsequent GREEN commands, the surface-verifier result,
    the CI status rollup, and the explicit fact that no live process/network/paid call ran.

## Stop conditions

Stop and return to the reviewer if any of these facts becomes true:

1. The evidence verifier requires `hermetic_settings.appdata_bind` or the old settings
   layout.
2. Passing the surface audit would require renaming a sink key, changing a classification,
   weakening the verifier, or leaving an unresolved test node.
3. The repair requires a real Zed/acpx/Redis/ACP launch, network access, credentials, or
   a paid call.
4. The diff must extend beyond the three Task 5 files or materially beyond path correction,
   bind removal, call-boundary coverage, direct-test repair, and audit metadata repair.

An ordinary test failure inside the authorized scope is not itself a stop condition;
diagnose it, keep the TDD evidence honest, and continue within the plan.

## Definition of Done and evidence map

| Claim | Required evidence |
|---|---|
| The actual caller passes the discovered Zed user-data root. | The call-boundary test is genuinely RED on the pre-fix production path and GREEN after the fix, with the captured argument asserted equal to `Path(invocation.user_data_root)`. |
| The pinned Zed binary can read the seeded `agent_servers` setting. | Direct and call-boundary tests prove the file exists at `<user-data-dir>/config/settings.json` before launch and prove the old `Zed/` and `zed-appdata` candidates are absent. |
| Hermeticity no longer relies on a false APPDATA contract. | Tests prove the corrected path stays under scratch, `environment_bind == ()`, and `git grep hermetic_appdata_environment_bind` is empty. |
| Plan 9.96 coverage remains resolved and truthful. | The surface verifier is green with the same sink keys/classifications, resolvable renamed test nodes, and corrected rationales. |
| No existing evidence schema was silently broken. | `tests/unit/tools/test_verify_plan1119_zed_reprobe_evidence.py` is green after the metadata change. |
| The repair stayed offline and atomic. | Exact three-file diff, one commit, clean Ruff/hygiene/CI, and PR record stating that no Zed/acpx/Redis/ACP/network/paid action ran. |

Task 5 completion does **not** establish `REACHABLE` or `UNREACHABLE`, does not produce
a corrected live bundle, and does not authorize a re-shot.

## Explicit exclusions and custody

| Excluded item | Custody |
|---|---|
| Corrected live guided re-shot and its launch budget | Operator decision after this amendment and WP-10 merge; requires fresh authority and a separately reviewed run package. |
| Retrospective edits to the frozen v1 plan | Permanently excluded by the forward-only amendment protocol; this v2 is the successor. |
| `CURRENT.md` approval/completion bookkeeping | Reviewer/operator-owned handoff state; outside this plan branch. |
| Pool, roadmap, or README status-pointer creation | No pointer exists at this baseline; documentation-freshness review should confirm the no-op rather than manufacture one. |
| Changes to Optimus production modules under `src/` | Not required for this harness-only defect and outside WP-10. |

## Plan self-review

- The amendment distinguishes the spent-shot result from the latent root cause and does
  not collapse shots 1–2 into the settings defect.
- The TDD boundary test exercises the argument at the real caller; it cannot stay green
  by discarding the seed argument in the fixture.
- The code, tests, and classified-sink metadata are one publishable state, not a droppable
  sequence that can leave false APPDATA claims behind.
- The prerequisites table covers code/state, services, tooling, authority, human action,
  and cost. The only evidence this plan claims is obtainable offline after the amendment
  merge; the separately unauthorized re-shot is excluded with an owner.
- No external status pointer is invented, the report-directory name is preserved, the v1
  bytes remain immutable, and `CURRENT.md` stays in the reviewer/operator lane.
