# Plan 9.98-FU-3 POSIX Runtime-Root Failure-Path Test Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the five Linux-failing runtime-root tests with the existing NO_APPROVAL and AUDIT_DIR_UNAVAILABLE contracts while preserving FU-1 workspace identity binding and FU-2 approval-time bootstrap behavior.

**Architecture:** Keep production code unchanged. Bucket A tests retain post-approval mutation before a full entrypoint and assert POSIX durable lookup failure; Bucket B tests obtain a real authorized capture first, inject a real filesystem mutation through a wrapper around the real authorize_capture(), and run the real audit composition against the mutated runtime root. WSL2 Ubuntu-24.04 provides interim POSIX evidence, and the clean Ubuntu GitHub Actions job remains the final gate.

**Tech Stack:** Python 3.14, pytest, pytest-cov, uv, WSL2 Ubuntu-24.04, GitHub Actions, Ruff.

## Global Constraints

- Baseline is origin/main at 41634cd2dcc8fae31315f9dfacdd1b95c679d82f.
- The approved design basis is docs/superpowers/specs/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests-design.md.
- This plan changes tests and test-only helpers only; no file under src/ may change.
- Preserve FU-1 lexical-path, canonical-path, device, inode, and st_ctime_ns workspace identity binding.
- Preserve NO_APPROVAL at durable-record lookup after a post-approval POSIX workspace mutation.
- Preserve AUDIT_DIR_UNAVAILABLE from the real audit consumer when an already-authorized capture sees a missing or unsafe runtime root.
- Do not bootstrap .optimus from launch, run, evidence, inspection, revocation, or verification paths.
- Do not mock append_authorized_audit(), append_launch_audit_event(), require_workspace_runtime_root(), authorize_launch(), or LaunchAuditError in Bucket B.
- Do not skip, deselect, xfail, or platform-xfail the Linux FU-3 tests. A platform branch may retain Windows' different st_ctime semantics, but the POSIX branch must execute on Linux.
- The exact _cmd_run() remediation string is: optimus-trust: no durable approval found for this workspace.
- The exact __main__.py remediation prefix is: optimus-agent: no launch approval found for this workspace. followed by the operator command.
- Preserve existing direct audit coverage in tests/unit/acp/test_launch_audit.py and existing post-audit WORKSPACE_IDENTITY_CHANGED coverage.
- Preserve pre-existing uv.lock modifications and .claude/ files; never stage them.
- Use WSL2 Ubuntu-24.04 for interim POSIX verification. The final acceptance artifact must be a clean Ubuntu clean-environment-recheck GitHub Actions run.
- Follow TDD ordering: run the relevant failing selector before the test correction, then run the corrected selector and inspect the exact result.
- Before any implementation commit, run git diff --check and uv run ruff check .; do not use --no-verify.

---

## Evidence and file map

### Baseline evidence

The exact five selectors were run inside WSL2 Ubuntu-24.04 before this plan. The observed result was 5 failed; the three capture-rooted failures raised LaunchGateError: NO_APPROVAL at src/optimus/acp/launch_gate.py:670. The WSL tool reported Linux uv 0.11.31.

### Files changed by the implementation

| File | Responsibility |
|---|---|
| tests/unit/acp/test_launch_approval_cli.py | Assert the non-bootstrapping _cmd_run() path returns POSIX NO_APPROVAL after a post-approval runtime-root removal and preserves the exact _cmd_run() message. |
| tests/unit/acp/test_main_wiring.py | Assert the full agent entrypoint returns POSIX NO_APPROVAL before audit/infra/server side effects and preserves the exact __main__.py remediation prefix. |
| tests/unit/tools/test_run_plan996_acpx_security_evidence.py | Move direct audit mutation after authorization and add a test-only wrapper that injects the real post-authorization filesystem mutation into the real capture_acpx() composition. |
| docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md | Gitignored reviewer handoff log; record current state and evidence, never stage it. |

### Frozen files

The implementation must not modify:

- src/optimus/acp/trusted_paths.py
- src/optimus/acp/launch_gate.py
- src/optimus/acp/launch_audit.py
- src/optimus/acp/operator_paths.py
- tools/run_plan996_acpx_security_evidence.py
- tests/unit/acp/test_launch_audit.py
- uv.lock
- .claude/

The frozen production files are not implementation targets because the approved design identifies no production defect.

## Task 0: Freeze the reviewed plan and establish the reviewer checkpoint

**Files:**

- Create: docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md
- Create: docs/superpowers/reviews/2026-07-22-plan-9-98-fu-3-implementation-plan-approval.md
- Create: docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md (gitignored; never stage)

**Produces:** A digest-pinned implementation plan and a durable reviewer checkpoint before test mutation.

- [ ] **Step 1: Verify baseline and the intentionally dirty workspace.**

Run from the Codex worktree:

~~~powershell
git status --short --branch
git rev-parse HEAD
git diff --name-only -- src tools tests
git status --short --untracked-files=all
~~~

Expected:

- HEAD is 41634cd2dcc8fae31315f9dfacdd1b95c679d82f.
- The only pre-existing non-FU-3 state is uv.lock plus .claude/.
- The approved design spec and this plan are the only new FU-3 documents.
- No source or test file has changed before Task 1.

- [ ] **Step 2: Record reviewer and operator approval for the exact plan bytes.**

The reviewer must read this entire plan, verify the exact remediation strings, confirm that the composed-test wrapper calls the real authorization and audit functions, and record an approval statement in docs/superpowers/reviews/2026-07-22-plan-9-98-fu-3-implementation-plan-approval.md. The operator must approve the same bytes before any test edit.

- [ ] **Step 3: Compute and record the design and plan digests.**

Run inside WSL2 Ubuntu-24.04:

~~~bash
cd /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-codex
sha256sum docs/superpowers/specs/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests-design.md \
  docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md
~~~

Record both exact SHA-256 outputs, the baseline commit, reviewer statement, operator statement, and the scope limited to POSIX runtime-root failure-path test alignment in the approval record.

- [ ] **Step 4: Record the initial reviewer checkpoint.**

The checkpoint log must start with a Current State section stating that Task 0 is awaiting the digest-pinned approval, that uv.lock and .claude/ are preserved user state, and that no source/test implementation has begun. Record the WSL baseline command and its 5 failed result as the first evidence entry.

- [ ] **Step 5: Commit only the approved planning artifacts after explicit commit authorization.**

Run:

~~~bash
git diff --check
git add docs/superpowers/specs/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests-design.md \
  docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md \
  docs/superpowers/reviews/2026-07-22-plan-9-98-fu-3-implementation-plan-approval.md
git diff --cached --name-only
git commit -m "docs: approve Plan 9.98-FU-3 test alignment"
~~~

Expected staged paths are exactly the design spec, implementation plan, and approval record. Never stage uv.lock, .claude/, or the checkpoint log. After the commit, update the checkpoint log with the commit hash and leave plan checkboxes as ordinary progress tracking. The planning commit must contain the pristine plan text with every task checkbox still unchecked; do not tick a Task 0 or later checkbox before this commit. Subsequent progress ticks are allowed, but the final closure commit in Task 6 must be checkbox-only relative to this planning commit.

## Task 1: Align Bucket-A durable lookup assertions

**Files:**

- Modify: tests/unit/acp/test_launch_approval_cli.py:363-402
- Modify: tests/unit/acp/test_main_wiring.py:198-227

**Interfaces:**

- Consumes: Existing authorize_workspace_for_test(), _cmd_run(), acp_main.main(), and fake keyring fixtures.
- Produces: Platform-explicit assertions for the pre-authorization NO_APPROVAL path with exact per-entrypoint remediation text and no side effects.

- [ ] **Step 1: Run the Bucket-A RED selectors in WSL2.**

Run:

~~~bash
uv run pytest \
  tests/unit/acp/test_launch_approval_cli.py::TestApprovalTimeRuntimeBootstrap::test_run_does_not_bootstrap_a_missing_runtime_root \
  tests/unit/acp/test_main_wiring.py::test_legacy_approved_workspace_missing_root_fails_without_recreating_it \
  -q
~~~

Expected: both tests fail because the current assertions expect success or AUDIT_DIR_UNAVAILABLE, while the real POSIX path returns NO_APPROVAL before audit.

- [ ] **Step 2: Update the _cmd_run() test with its exact remediation string.**

Keep the current setup that authorizes the workspace, asserts the approval-time .optimus directory exists, removes it, patches bootstrap_workspace_runtime_root() to fail if called, and intercepts the target child command. Add capsys to the signature, add a child-start flag, and replace the unconditional success assertion with:

~~~python
child_started = False

def selective_subprocess_run(argv: list[str], **kwargs: object) -> object:
    nonlocal child_started
    if "-c" in argv and "pass" in argv:
        child_started = True
        return type("Result", (), {"returncode": 0})()
    return real_subprocess_run(argv, **kwargs)

monkeypatch.setattr(cli_module.subprocess, "run", selective_subprocess_run)

result = cli_module._cmd_run(
    workspace,
    target_argv=[sys.executable, "-c", "pass"],
    elevated_debug=False,
)
if sys.platform == "win32":
    assert result == 0
else:
    assert result == 2
    assert capsys.readouterr().err == (
        "optimus-trust: no durable approval found for this workspace.\n"
    )
    assert not child_started
assert not runtime_root.exists()
~~~

The Windows branch preserves the existing creation-time behavior while the Linux branch directly proves NO_APPROVAL, no bootstrap, and no child spawn. Do not assert the __main__.py message in this test; _cmd_run() emits the exact inline string above.

- [ ] **Step 3: Update the full agent entrypoint test with its distinct remediation prefix.**

Add import sys to the test module's standard-library imports. Keep the current setup and side-effect sentinels. Replace the single AUDIT_DIR_UNAVAILABLE assertion with:

~~~python
assert acp_main.main(["--workspace-root", str(workspace)]) == 2
stderr = capsys.readouterr().err
if sys.platform == "win32":
    assert "AUDIT_DIR_UNAVAILABLE" in stderr
else:
    assert stderr.startswith(
        "optimus-agent: no launch approval found for this workspace."
    )
    assert "optimus-trust --workspace-root" in stderr
assert not (workspace / ".optimus").exists()
redis.assert_not_called()
gateway.assert_not_called()
server.assert_not_called()
~~~

The POSIX assertion must use the __main__.py remediation prefix optimus-agent: no launch approval found for this workspace. and must not reuse _cmd_run()'s optimus-trust: no durable approval found for this workspace. string.

- [ ] **Step 4: Run the corrected Bucket-A selectors in WSL2.**

Run the same command from Step 1.

Expected: 2 passed, with the POSIX assertions proving NO_APPROVAL, no runtime-root recreation, and no Redis/Gateway/server calls.

- [ ] **Step 5: Run the corrected Bucket-A selectors on Windows.**

Run from PowerShell with the repository's configured Python runtime:

~~~powershell
uv run pytest tests/unit/acp/test_launch_approval_cli.py::TestApprovalTimeRuntimeBootstrap::test_run_does_not_bootstrap_a_missing_runtime_root tests/unit/acp/test_main_wiring.py::test_legacy_approved_workspace_missing_root_fails_without_recreating_it -q
~~~

Expected: 2 passed; Windows follows its existing st_ctime creation-time semantics without weakening the Linux assertions.

- [ ] **Step 6: Record the Bucket-A checkpoint and commit only its tests.**

Run:

~~~bash
git diff --check
git add tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_main_wiring.py
git diff --cached --name-only
git commit -m "test: align POSIX durable lookup failures"
~~~

Expected staged paths are exactly the two Bucket-A test files. Update the checkpoint log with the WSL and Windows results, commit hash, exact two remediation strings, and confirmation that no src/ file changed.

## Task 2: Align the direct regular-file audit test

**Files:**

- Modify: tests/unit/tools/test_run_plan996_acpx_security_evidence.py:280-306

**Interfaces:**

- Consumes: Real _write_durable_approval(), authorize_capture(), append_authorized_audit(), and LaunchAuditError.
- Produces: Direct-audit coverage that mutates the runtime root only after a real authorized capture exists.

- [ ] **Step 1: Run the regular-file RED selector in WSL2.**

Run:

~~~bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_stops_when_real_audit_runtime_root_is_a_regular_file -q
~~~

Expected: fail with LaunchGateError(NO_APPROVAL) from launch_gate.py:670 because the current test mutates .optimus before authorize_capture().

- [ ] **Step 2: Move the mutation after real authorization.**

Keep _write_durable_approval() unchanged. Replace the current pre-authorization removal/replacement block with this sequence:

~~~python
capture = authorize_capture(
    workspace=workspace,
    environment=environment,
    keyring_backend=keyring,
    approval_runtime_root=approval_runtime_root,
    launch_session_id="sess_audit_failure",
)

runtime_root = workspace / ".optimus"
assert runtime_root.is_dir()
runtime_root.rmdir()
runtime_root.write_text("not a directory", encoding="utf-8")

with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
    append_authorized_audit(capture)

assert runtime_root.is_file()
assert runtime_root.read_text(encoding="utf-8") == "not a directory"
~~~

Do not call spawn_authorized_capture() in this direct-audit test; the assertion is that the real audit consumer rejects the unsafe final component before any later step.

- [ ] **Step 3: Run the corrected regular-file selector in WSL2.**

Run the same command from Step 1.

Expected: 1 passed; the exception comes from the real require_workspace_runtime_root()/lstat() path, and the regular file remains unchanged.

- [ ] **Step 4: Record the direct-audit checkpoint and commit the test correction.**

Run:

~~~bash
git diff --check
git add tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --cached --name-only
git commit -m "test: preserve real unsafe audit-root coverage"
~~~

Expected staged path: only tests/unit/tools/test_run_plan996_acpx_security_evidence.py. Update the checkpoint log with the RED NO_APPROVAL trace, GREEN AUDIT_DIR_UNAVAILABLE result, and confirmation that tests/unit/acp/test_launch_audit.py stayed unchanged.

## Task 3: Exercise the real composed capture_acpx() audit failure path

**Files:**

- Modify: tests/unit/tools/test_run_plan996_acpx_security_evidence.py:309-381

**Interfaces:**

- Consumes: Module-level capture_tool.authorize_capture, real capture_acpx(), real append_authorized_audit(), and the existing child-spawn sentinels.
- Produces: Two composed tests that prove the real sequence stops at AUDIT_DIR_UNAVAILABLE after authorization and before child spawn.

- [ ] **Step 1: Run the two composed RED selectors in WSL2.**

Run:

~~~bash
uv run pytest \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_blocks_child_when_composed_audit_fails \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_missing_approved_runtime_root_never_spawns_or_recreates_it \
  -q
~~~

Expected: both fail at authorize_launch() with LaunchGateError(NO_APPROVAL) before the audit layer.

- [ ] **Step 2: Add the test-only post-authorization mutation helper.**

Add Callable to the standard-library imports and add this helper near the existing evidence-test helpers:

~~~python
from collections.abc import Callable

def _patch_authorize_capture_after_real_authorization(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workspace: Path,
    mutate: Callable[[Path], None],
) -> None:
    real_authorize_capture = capture_tool.authorize_capture

    def authorize_then_mutate(**kwargs: object) -> capture_tool.CaptureLaunch:
        capture = real_authorize_capture(**kwargs)
        mutate(workspace / ".optimus")
        return capture

    monkeypatch.setattr(capture_tool, "authorize_capture", authorize_then_mutate)
~~~

The wrapper must call the real authorize_capture() first and must not replace or patch any audit function, gate function, or exception. capture_acpx() resolves its module-level authorize_capture name at call time, so this wrapper is the only injected seam.

- [ ] **Step 3: Rewrite the regular-file composed test to use the real wrapper.**

Keep the existing durable-approval authoring setup and child sentinel. Replace the pre-authorization mutation with:

~~~python
def replace_runtime_root_with_file(runtime_root: Path) -> None:
    runtime_root.rmdir()
    runtime_root.write_text("not a directory", encoding="utf-8")

_patch_authorize_capture_after_real_authorization(
    monkeypatch,
    workspace=workspace,
    mutate=replace_runtime_root_with_file,
)

with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
    capture_acpx(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_composed_audit_failure",
        command=[sys.executable, "-c", "raise SystemExit(0)"],
    )

assert (workspace / ".optimus").is_file()
~~~

The existing spawn_authorized_capture sentinel must remain. If the real audit path returns instead of raising, the sentinel fails the test; the audit layer itself is never mocked.

- [ ] **Step 4: Rewrite the missing-root composed test to use the real wrapper.**

Keep the existing child-spawn guard and replace the pre-authorization runtime_root.rmdir() with:

~~~python
def remove_runtime_root(runtime_root: Path) -> None:
    runtime_root.rmdir()

_patch_authorize_capture_after_real_authorization(
    monkeypatch,
    workspace=workspace,
    mutate=remove_runtime_root,
)

with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
    capture_acpx(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_missing_root",
        command=expected_command,
    )

assert not runtime_root.exists()
~~~

The real capture_acpx() call must perform authorization first, then the wrapper mutation, then the real audit append. The missing root must remain absent and the child command must never reach Popen.

- [ ] **Step 5: Run the two corrected composed selectors in WSL2.**

Run the same command from Step 1.

Expected: 2 passed; both failures are LaunchAuditError(AUDIT_DIR_UNAVAILABLE), and neither child sentinel is reached.

- [ ] **Step 6: Run the entire evidence-tool unit module in WSL2.**

Run:

~~~bash
uv run pytest tests/unit/tools/test_run_plan996_acpx_security_evidence.py -q
~~~

Expected: the module passes with no FU-3-specific skip, xfail, or deselection. Existing WORKSPACE_IDENTITY_CHANGED post-audit coverage remains green.

- [ ] **Step 7: Record the composed-path checkpoint and commit the test correction.**

Run:

~~~bash
git diff --check
git add tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --cached --name-only
git commit -m "test: exercise composed audit-root rejection"
~~~

Expected staged path: only the evidence-tool test module. Update the checkpoint log with the wrapper code-review ruling, both GREEN selector results, the full module result, and the commit hash.

## Task 4: Run affected-suite fitness gates and prove frozen scope

**Files:**

- No source changes.
- Update docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md only; never stage it.

**Interfaces:**

- Consumes: Tasks 1-3 test corrections.
- Produces: A clean affected suite, Ruff result, and frozen-scope evidence.

- [ ] **Step 1: Run the affected unit and direct-audit selectors in WSL2.**

Run:

~~~bash
uv run pytest \
  tests/unit/acp/test_launch_approval_cli.py \
  tests/unit/acp/test_main_wiring.py \
  tests/unit/acp/test_launch_audit.py \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py \
  -q
~~~

Expected: zero failures; direct missing, symlink, regular-file, pre-authorization, composed-audit, and post-audit revalidation cases all remain represented.

- [ ] **Step 2: Run Ruff in WSL2.**

Run:

~~~bash
uv run ruff check .
~~~

Expected: exit code 0 with no diagnostics.

- [ ] **Step 3: Prove no production or tool file changed.**

Run:

~~~bash
git diff --name-only -- src tools
git diff --check
~~~

Expected: the first command prints nothing, and the second exits 0. If any source or tool file is modified, stop and return to scope review; do not stage it.

- [ ] **Step 4: Verify staged scope before each test commit.**

Run:

~~~bash
git status --short
git diff --cached --name-only
~~~

Expected: only the intended test files are staged for their task commit. uv.lock, .claude/, and the checkpoint log are never staged.

- [ ] **Step 5: Record the fitness-gate checkpoint.**

Record the exact WSL commands, exit statuses, affected-suite result, Ruff result, frozen-source proof, and current commit sequence in docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md.

## Task 5: Run the full CI-equivalent WSL gate

**Files:**

- No source or test changes.
- Update docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md only; never stage it.

**Interfaces:**

- Consumes: The complete test-only implementation from Tasks 1-3.
- Produces: Interim full-suite POSIX evidence before final CI.

- [ ] **Step 1: Run the full clean-environment-recheck equivalent in WSL.**

Run from WSL2 Ubuntu-24.04:

~~~bash
uv sync --all-extras
node --version
uv build --wheel --out-dir dist/plan99
uv run python tools/verify_plan99_noneditable_install.py \
  --wheel-dir dist/plan99 \
  --scratch-root /tmp/optimus-plan99-package
uv run pre-commit run trailing-whitespace --all-files
uv run pre-commit run check-yaml --all-files
uv run pre-commit run check-toml --all-files
uv run pre-commit run check-added-large-files --all-files
uv run ruff check .
uv run bandit -q -r src -c pyproject.toml
uv run pre-commit run optimus-ast-grep --all-files
uv run python -m optimus.guardrails.prompt_injection
uv run detect-secrets-hook --baseline .secrets.baseline src
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
~~~

The `node --version` check is a local precondition for the repository's Node-backed hooks; the workflow installs Node 22 before running this block, so WSL must provide the equivalent Node 22 toolchain. Expected: every command passes, the noneditable wheel check succeeds, the full default suite passes, aggregate coverage is at least 80%, and the five FU-3 tests execute rather than being skipped or xfailed. Live-dependency deselection from the repository's existing pytest configuration is allowed only for its named live markers and is unrelated to FU-3.

- [ ] **Step 2: Record interim evidence.**

Record the WSL distro/version, Linux uv version, exact command, pass count, coverage percentage, and the five FU-3 test node IDs in the checkpoint log. This record is interim evidence and does not replace GitHub Actions.

- [ ] **Step 3: Confirm the worktree before final push authorization.**

Run:

~~~bash
git status --short --branch
git log --oneline --decorate -5
~~~

Expected: only the intentionally preserved uv.lock/.claude state and the task's intended commits are present; no untracked generated artifacts are in the implementation scope.

## Task 6: Complete the official clean Ubuntu CI gate

**Files:**

- No source or test changes.
- Update docs/superpowers/reviews/plan-9-98-fu-3-review-checkpoints.md only; never stage it.

**Interfaces:**

- Consumes: Tasks 1-5 and their WSL evidence.
- Produces: The required final GitHub Actions evidence artifact.

- [ ] **Step 1: Obtain explicit operator authorization to push.**

Do not infer push or pull-request permission from the plan or from prior PR #60 authorization. The operator must authorize both this FU-3 branch push and opening a PR targeting `main`, after the WSL full CI-equivalent gate is green. A branch push alone is not a workflow trigger for this repository.

- [ ] **Step 2: Update the branch from the latest origin/main without rewriting history.**

Run:

~~~bash
git fetch origin
git merge --ff-only origin/main
~~~

Expected: either a fast-forward to the current origin/main or an explicit stop if the branch has diverged. Do not force-push or rebase shared history without separate authorization.

- [ ] **Step 3: Run the pre-push gates again.**

Run:

~~~bash
git diff --check
uv sync --all-extras
node --version
uv build --wheel --out-dir dist/plan99
uv run python tools/verify_plan99_noneditable_install.py \
  --wheel-dir dist/plan99 \
  --scratch-root /tmp/optimus-plan99-package
uv run pre-commit run trailing-whitespace --all-files
uv run pre-commit run check-yaml --all-files
uv run pre-commit run check-toml --all-files
uv run pre-commit run check-added-large-files --all-files
uv run ruff check .
uv run bandit -q -r src -c pyproject.toml
uv run pre-commit run optimus-ast-grep --all-files
uv run python -m optimus.guardrails.prompt_injection
uv run detect-secrets-hook --baseline .secrets.baseline src
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
~~~

Expected: all commands pass before push, including the noneditable-package check, all four hygiene hooks, Ruff, Bandit, AST-grep, prompt-injection scan, secret scan, and pytest with coverage. The final local WSL run must be recorded separately from the earlier interim run. Preserve the disclosed `uv.lock` and `.claude/` state; do not stage generated or unrelated changes.

- [ ] **Step 4: Push the named branch after authorization.**

Run:

~~~bash
git push --set-upstream origin agent/codex/plan-9-98-fu-3-posix-runtime-root-tests
~~~

Expected: the push succeeds without `--force`. It does not, by itself, trigger `.github/workflows/guardrails.yml`: this workflow runs for `pull_request` events or pushes to `main` only.

- [ ] **Step 5: Open and verify the PR that triggers the workflow.**

After the operator authorizes the PR, create a draft PR targeting `main` if one does not already exist:

~~~bash
gh pr create \
  --base main \
  --head agent/codex/plan-9-98-fu-3-posix-runtime-root-tests \
  --draft \
  --title "test: align POSIX runtime-root failure paths" \
  --body "Align the five Linux runtime-root failure-path tests with the existing NO_APPROVAL and AUDIT_DIR_UNAVAILABLE contracts. Preserve FU-1 workspace identity binding; use WSL2 interim verification and clean Ubuntu CI final evidence."
~~~

If a PR for this exact branch already exists, reuse it rather than opening a duplicate. Verify that it targets `main`, has the named branch as its head, and is visible to the repository checks:

~~~bash
gh pr view --json number,url,baseRefName,headRefName,isDraft
~~~

Expected: the PR is open with `baseRefName` equal to `main` and `headRefName` equal to `agent/codex/plan-9-98-fu-3-posix-runtime-root-tests`. Opening or updating this PR is the event that causes `.github/workflows/guardrails.yml` to run.

- [ ] **Step 6: Verify the actual clean-environment-recheck job.**

Inspect the GitHub Actions run and record its URL and run ID. Confirm all of the following from the actual job output:

- clean-environment-recheck ran on ubuntu-latest.
- The workflow completed its noneditable-package wheel build and installation check.
- The four all-files hygiene hooks passed: trailing-whitespace, check-yaml, check-toml, and check-added-large-files.
- uv run ruff check . passed.
- Bandit passed for `src`.
- The all-files `optimus-ast-grep` hook passed.
- The prompt-injection configuration scan passed.
- The detect-secrets scan passed against `src`.
- The full uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v command passed.
- All five FU-3 tests executed and passed; none was skipped, deselected as a FU-3 workaround, or platform-xfailed.
- Coverage met the repository's 80% threshold.

- [ ] **Step 7: Record final evidence and closure ruling.**

Update the checkpoint log with the final CI URL/run ID, exact test and coverage summary, frozen-scope proof, and reviewer ruling that the roadmap acceptance boundary is satisfied. Do not claim FU-3 complete before this artifact exists.

- [ ] **Step 8: Close the plan with a checkbox-only commit.**

Every prior task and Definition-of-Done row must already be genuinely complete. As the irreducible self-reference of a final closure action, mark this Step 8 checkbox complete immediately before the sweep below; then mechanically prove that no unchecked task remains and that the plan changed since the Task 0 planning commit only by checkbox transitions. Run from WSL2 Ubuntu-24.04:

~~~bash
PLAN_PATH="docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md"
PLAN_BASELINE_COMMIT="$(git log --follow --format=%H --reverse -- "$PLAN_PATH" | head -n1)"
if rg -n '^- \[ \]' "$PLAN_PATH"; then
  echo "unchecked plan steps remain" >&2
  exit 1
fi
uv run python - "$PLAN_BASELINE_COMMIT" "$PLAN_PATH" <<'PY'
from pathlib import Path
import re
import subprocess
import sys

baseline_commit, plan_path = sys.argv[1:]
baseline = subprocess.check_output(
    ["git", "show", f"{baseline_commit}:{plan_path}"], text=True
).splitlines()
current = Path(plan_path).read_text(encoding="utf-8").splitlines()
normalize = lambda line: re.sub(r"^- \[[ x]\]", "- [ ]", line)
if [normalize(line) for line in baseline] != [normalize(line) for line in current]:
    raise SystemExit("plan diff contains substantive changes after Task 0")
PY
git add "$PLAN_PATH"
git diff --cached --check
test "$(git diff --cached --name-only)" = "$PLAN_PATH"
git commit -m "docs: close Plan 9.98-FU-3 (checkbox-only)"
~~~

Expected: the unchecked-box sweep produces no output, the normalization check succeeds, the staged path is exactly the plan file, and the closure commit contains only checkbox transitions. The checkpoint log must record the closure commit hash; it remains gitignored and unstaged. This closure commit is required before the plan can be declared complete.

## Definition of Done and evidence mapping

| Claim | Required evidence |
|---|---|
| POSIX pre-authorization mutation is NO_APPROVAL | WSL Bucket-A selector output; exact _cmd_run() and __main__.py remediation assertions; no side-effect mock calls. |
| Direct unsafe authorized runtime root is AUDIT_DIR_UNAVAILABLE | WSL regular-file selector and both composed selector outputs; real audit path; root remains missing/file and child sentinel is not reached. |
| FU-1 identity security binding is preserved | git diff --name-only -- src is empty; frozen source files unchanged from origin/main. |
| No launch-side bootstrap was added | Same frozen-source proof plus existing no-bootstrap assertions passing. |
| Interim POSIX suite is green | WSL2 Ubuntu-24.04 affected-suite and full-coverage command outputs recorded in the checkpoint log. |
| Final Phase 1 gate is green | GitHub Actions clean-environment-recheck URL/run ID with the noneditable-package check, four hygiene hooks, Ruff, Bandit, AST-grep, prompt-injection scan, secret scan, full pytest, coverage, and all five FU-3 tests passing. |
| Plan is mechanically closed | Zero unchecked boxes, a checkbox-only diff from the Task 0 planning commit, and the dedicated `docs: close Plan 9.98-FU-3 (checkbox-only)` commit recorded in the checkpoint log. |

The implementation plan is complete only when every row has its named evidence artifact. A Windows-green run alone cannot close this plan.
