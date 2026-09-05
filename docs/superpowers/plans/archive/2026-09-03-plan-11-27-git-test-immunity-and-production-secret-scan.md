# Plan 11.27 — Git Test Immunity and Production Secret Scan Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task, with Claude's independent review before each local commit. Checkboxes record executed verification, not intention.

**Goal:** Protect commit-time tests from inherited Git routing variables, then replace the CI directory-argument no-op with a required scan of tracked production text.

**Architecture:** Extract the reviewed session-level test protection without WP-27 helpers. Add a separate filename-driven manual pre-commit hook for CI; preserve the local commit hook. CI rejects an empty production text inventory before invoking the new hook. Only explicit non-credential annotations change production files.

**Tech Stack:** Python 3.14, pytest, pre-commit, detect-secrets 1.5.0, identify, PyYAML, Git, Windows and WSL Ubuntu 24.04; existing locked dependencies only.

**Spec:** Operator-approved `D:/Projects/Development/Python/optimus-agent-handoff/CODEX-BRIEF-2026-09-03-frozen-secret-scan-scope.md`, SHA-256 `f5d2b923b280999bb3ac68008b348e4933d59edd692d1b07efd8b5db3a3dad1b`.

**Authority:** Vibhanshu: "Approved per Claude comments" on 2026-09-03 IST. This grants execution, isolated Linux package downloads, and two local commits after their gates. It does not grant publication or runtime reinstall. The frozen scope and this executable transcription govern this lane; conflicts stop execution.

**Status:** STOPPED before Slice A implementation: the initial full suite hit the exact Gateway WinError 10053 test already owned by P11-FU-6. Execution started 2026-09-02 20:23:40 UTC; the stop condition was identified at approximately 20:36 UTC, before the 23:23:40 cap. This preserved scratch draft is not a live registered plan. No completion is claimed. The initial baseline command's inside-worktree basetemp also induced unrelated Git-parent discovery and long-path failures; the 192-pass normal-layout control is retained separately and does not erase the full-suite failure.

## Global Constraints

- Dedicated worktree `D:/Projects/Development/Python/optimus-cost-agent-wt-codex-ci-production`, branch `agent/codex/ci-production-secret-scan`, refreshed main base `5ea8f8f71548eb05a8562a10e98667e3d2061c4d`.
- Three hours total including setup, both reviews, rehearsals and two real local commits. Stop on an out-of-scope pre-existing defect, unresolved prerequisite, actual/unclassified secret, or cap breach. Repair defects introduced by this work only within the remaining scope and time.
- Slice A is exactly two files (+26/+112). Slice B is seven functional files plus this plan, the existing backlog and README; no status-only commit. Keep the plan and registry drafts out of Slice A's staged set; preserve them together when preparing its clean rehearsal/commit surface, and restore them together afterwards.
- Sanitize inherited `GIT_*` before any new fixture's first subprocess. Assert both Git directories resolve inside each disposable repository before any config/index/ref mutation. Rehearse from complete `git archive` exports, including reports; never copy a linked-worktree `.git` pointer.
- Record evidence below ignored `tmp/ci-production-execution/`. Put pytest temporary tests inside the independent export so child pytest cannot select a parent's configuration/conftest. Prove import provenance, not just PYTHONPATH presence.
- Claude is the independent reviewer and sole writer of shared CURRENT.md. Supply evidence paths/digests; do not invent review acceptance or write that ledger.
- Baseline SHA-256 remains `89eb6f47e9a1279ff6b9dad5f12e53a221914a16e0eabd873108bd7001397d71`; lockfile remains `f1caae185d41b02de2bf9a1cc4970e2517278c8a12b3a4728dd71fc2d826a097`.
- Shared Git config starts at SHA-256 `ae6059069cc62fde0eb237ecc9c6c0277974ff257b362c7ad596a5d35c651446`; audit config, index, HEAD, refs and identity at each real commit, accounting only for the intended commit/index changes.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | Exact two-file source at c69fd48646645a487b2a9521db8a92c22e536f3a, fresh main lane | yes | Codex | Verified port; runtime lane is not the implementation target. |
| tooling | Windows Python 3.14, locked dev environment, Git and pre-commit | yes | Operator machine-state | Existing tools and isolated environment. |
| tooling | WSL Ubuntu 24.04, Python 3.14.6, locked Linux dev environment | yes | Operator machine-state / Codex setup | Authorized isolated downloads; setup succeeded, no lock change. |
| code/state | Main's full default test and hook health | unknown | Codex | Genuinely hard until Task 0 establishes it; pre-existing failure stops the package before a real commit. |
| services | No Redis, Gateway, GUI or paid model call required by the default/focused gates | yes | Codex | Do not enable live markers or substitute fakes for a required live tier. |
| credentials/authority | Execution, Linux downloads, two local commits after gates | yes | Vibhanshu | Explicit approval above; no provider credential required. |
| human interaction | Claude's independent per-slice review | no | Claude | Merely unauthorized until the actual evidence review is accepted; no operator GUI step is needed. |
| cost | Package downloads, three-hour cap, no paid Gateway calls | yes | Vibhanshu | Stop rather than buy more time or skip a gate. |
| publication | Push, PR, merge, runtime reinstall | no | Vibhanshu | Merely unauthorized and explicitly excluded; not needed for local delivery. |

## Task 0 — establish a safe baseline

- [ ] Confirm refreshed main, clean lane, lock/baseline/shared-config digests and installed-product separation.
- [ ] Run `python -m ruff check .` and the full default `python -m pytest -q --basetemp=tmp/ci-production-execution/baseline-pytest` with inherited Git variables removed. A pre-existing failure is STOPPED, not a repair invitation.
- [ ] Verify both platform dependency environments without modifying dependency declarations or the installed uv tool.

## Task 1 / Slice A — exact central immunity extraction

**Files:** modify `tests/conftest.py`; create `tests/unit/tools/test_git_env_immunity.py`.

**Interfaces:** pytest's `pytest_sessionstart(session)` removes all inherited Git variables into `_INHERITED_GIT_ENV`; `pytest_sessionfinish(session, exitstatus)` restores and clears that mapping. No production interface changes.

- [ ] Extract the exact 112-line test from `git show c69fd48646645a487b2a9521db8a92c22e536f3a:tests/unit/tools/test_git_env_immunity.py`; verify SHA-256 `cd438ad0e78ce6b091fcfeb4eb1530802607be6cbbcbbb28741001aa555a0bee`.
- [ ] Before the hook extraction, run `python -m pytest tests/unit/tools/test_git_env_immunity.py -q --basetemp=tmp/ci-production-execution/a-red`. Require 1 failed / 4 passed, with the positive victim-state equality assertion failing; retain the no-protection negative control.
- [ ] Extract only the block starting `_INHERITED_GIT_ENV:` and ending before the first session fixture from the bound conftest. Keep all main imports and fixtures unchanged. Verify exactly 26 added lines and no removed lines; do not import `sync_await` or loop helpers.
- [ ] Repeat the five-case test using `a-green` basetemp, then repository Ruff and `git diff --check`. Verify imported conftest points to this lane and disposable victims stay inside evidence scratch.
- [ ] Export complete HEAD with `git archive`; initialize an independent Git directory, assert both directory identities and all exported file counts including reports, apply exactly the two-file candidate, and run a real commit with the unchanged hook configuration. Require all hooks to pass, expected candidate tree-ID equality, and unchanged source/shared state.
- [ ] Give Claude the source binding, red/green logs, provenance, exact diff, full rehearsal and audit. Wait for acceptance.
- [ ] Stage exactly both files and commit `test: isolate pytest from inherited git environment`. No bypass; compare resulting tree to rehearsal and audit shared state again. A commit is not publication.

## Task 2 / Slice B — required production-only CI gate

**Files:** `.pre-commit-config.yaml`, `.github/workflows/guardrails.yml`, `tests/unit/guardrails/test_ci_parity.py`, `src/evidence_handoff_runtime/migrations.py`, `src/optimus_gateway/observability.py`, `src/optimus/acp/launch_policy.py`, `src/optimus/acp/local_gateway_secrets.py`.

**Interfaces:** new manual hook ID `optimus-secret-scan-ci-production`; name `optimus-check: secret-scan CI production-only tracked text`; entry `python -X utf8 -m detect_secrets.pre_commit_hook --baseline .secrets.baseline`; language `system`, types `[text]`, files `^src/`, stages `[manual]`, filename passing enabled. Keep the existing local hook untouched.

- [ ] Add production-named real subprocess tests first in the existing parity test file. Read the actual YAML workflow and run its configured scan command in disposable Git repositories; do not replace the command with a test-owned approximation. Stage the baseline before evaluation and assert byte identity after every invocation.
- [ ] Primary test sequence: clean fixture exits 0; nested split-built AWS canary exits 1 with `AWS Access Key` and its exact path/line; restoring that file exits 0. Outside-src canary remains present and excluded. Mutating the command to the old directory-only form must fail the test because it returns 0 and misses the canary. A no-op control must pass.
- [ ] Cover tracked text across all production packages and nested UTF-8 paths. Compare the actual pre-commit selection to the independent tracked-text inventory. Reject empty inventories including binary-only and outside-src-only fixtures. Reject conditional skipping, continue-on-error, filename suppression or weakened filters/detectors.
- [ ] Run the new focused tests against the old configuration and retain the expected failures. Then add only the new hook and required workflow step. Keep the empty-inventory preflight inline in the workflow; select `git ls-files -z -- src/` paths that identify tags as text, and exit nonzero with `No tracked production text files under src/` if none remain. Follow it with `uv run pre-commit run optimus-secret-scan-ci-production --all-files --hook-stage manual`.
- [ ] Add reasoned `pragma: allowlist secret` annotations only at the approved main-based occurrences: migrations lines 19/23/27 (recomputed SQL integrity hashes); observability 43/46/47/48 (redaction labels); launch_policy 28/227 (enum label/docstring placeholder); local_gateway_secrets 18/19 (keyring names). No baseline, executable runtime behavior or detector changes.
- [ ] Iterate the production scan to exit 0; compare every finding to the reviewed classification before annotation. Stop on an unclassified value. If a direct phantom-drift regression is used, assert scanner exit 3 AND `The baseline file was updated.`, never just wrapper/nonzero status.
- [ ] Run guardrail, migration-manifest, observability, launch-policy and local-gateway-secret focused tests; run repository Ruff and diff checks. Obtain real Windows and Linux canary/restored/empty evidence with baseline invariance and both Git-directory assertions.
- [ ] Update README to name the production-only CI boundary; retain broader migration custody in the existing backlog. Do not claim the local hook or repository-wide coverage was repaired.
- [ ] Rehearse the actual Slice B staged file set plus these bounded documentation changes in a complete independent archive; require the unchanged full commit hooks, tree-ID equality and shared-state audit.
- [ ] Give Claude the seven-file functional diff, documentation, real regression controls, both platform results, full rehearsal and audit; wait for acceptance.
- [ ] Commit `fix: enforce production-only CI secret scanning` locally after all gates. Audit exact tree, shared configuration and unchanged baseline/lock. Stop without push, merge or reinstall.

## Explicit Exceptions

| Excluded obligation | Owning backlog entry / authority |
|---|---|
| Broad baseline migration, frozen-artifact classification/path custody, PR #194 collision (12 of 12 stale identities) | Existing `P11-FEAT-ACP-RUNTIME-HARDENING`; PR #194's hardening lane. This interim never closes it. |
| WP-27 helper-level Git isolation, runtime changes, source installation and live session gates | Existing `P11-FEAT-ZED-RESUME`; accepted WP-27 runtime lane. |
| Changing `.secrets.baseline`, detectors/filters, dependencies or local-hook scope | Existing `P11-FEAT-ACP-RUNTIME-HARDENING`; separately reviewed grant required. |
| Publication of these commits or the 37-commit runtime branch, PRs, branch protection, merge | Operator-owned publication decision under the existing hardening/Zed Resume custody. |

## Evidence and closure

Evidence lives at `tmp/ci-production-execution/`: command logs, platform/version bindings, red/green and mutation controls, candidate/rehearsal tree identities, exact staged paths and before/after shared-state hashes. Each completion checkbox requires its command to have passed. STOPPED reports name the precise dependency and untouched state, retain evidence, and leave the product as installed. Local delivery does not close publication or the broader hardening program.
