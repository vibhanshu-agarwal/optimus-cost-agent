# Plan 9.98-FU-2 Approval-Time Runtime Bootstrap Implementation Plan

> For agentic workers: REQUIRED SUB-SKILLS: Use superpowers:executing-plans task-by-task and superpowers:test-driven-development for every behavior change. Steps use checkbox syntax for tracking.

**Status:** Draft. Only the Task 0 digest-pinned approval record authorizes implementation; later checkbox ticks do not.

**Goal:** Remove the Linux ctime self-invalidation introduced by Plan 9.98-FU-1 without weakening workspace replacement detection or allowing launch-side runtime-root creation.

**Architecture:** The TTY-gated optimus-trust approve command creates and validates the empty resolved-workspace .optimus directory before it captures the identity bound into an approval. Audit becomes a strict consumer of that directory: it never creates it, and a missing, non-directory, or symlink root fails closed. Direct test record-authoring helpers model the completed approval ceremony; unapproved launch tests keep proving no root is created.

**Tech Stack:** Python 3.12, pathlib, os/stat, pytest, pytest-cov, Ruff, GitHub Actions Ubuntu.

## Global Constraints

- Baseline: 287adf923cac5400a258551351cb908f7f39de4d on the existing agent/kiro/plan-9-96 branch and PR #60. Do not create a branch or worktree.
- Design basis: docs/superpowers/specs/2026-07-19-workspace-runtime-bootstrap-ci-design.md, SHA-256 32772A96312AEE5E3BCDBA5A9D055B131D72CAA76E2F1300AC5E44324CBC618A.
- Do not modify Plan 9.96, Plan 9.98, Plan 9.98-FU-1, existing FU-1 approval records, launch_gate.py, launch_policy.py, local_infra.py, local_gateway_secrets.py, uv.lock, .claude, or a reviewer checkpoint log.
- Preserve existing uncommitted FU-1 checkbox-only plan changes and uv.lock. Never stage either.
- Only optimus-trust approve, after _require_tty(), may bootstrap .optimus. optimus-agent, optimus-trust run, the evidence tool, inspect, revoke, and verification commands must never initialize it.
- Preserve the complete FU-1 workspace identity binding, including st_ctime_ns. Do not rebaseline after audit and do not remove the change-time token.
- Approval path environment data is captured once in LaunchEnvironmentSnapshot. Bootstrap and candidate resolution use that one snapshot, never a new live os.environ read.
- Bootstrap uses resolved OperatorPaths.runtime_root, rejects a symlink/non-directory, and creates no parent, file, approval record, network connection, or child process.
- append_launch_audit_event() must not call mkdir(). Missing/unsafe runtime roots are fatal and write nothing.
- No production code before its named RED test runs and fails for the intended reason. Fixtures contain synthetic values only.
- Before every commit, run git diff --check, uv run ruff check ., and a frozen-path diff. Never stage IDE directories, uv.lock, or checkpoint logs.
- Linux CI is the governing final gate because POSIX directory st_ctime_ns changes when a direct child is added. Windows-only success does not close this defect.

## File and Responsibility Map

| File | Responsibility |
|---|---|
| docs/superpowers/specs/2026-07-19-workspace-runtime-bootstrap-ci-design.md | Approved design basis; committed only in Task 0. |
| docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md | This immutable-after-approval plan. |
| docs/superpowers/reviews/2026-07-19-plan-9-98-fu-2-implementation-plan-approval.md | Task 0 two-signature approval record. |
| src/optimus/acp/operator_paths.py | Resolved-path-only bootstrap and read-only runtime-root validation. |
| src/optimus/acp/launch_approval_cli.py | One-snapshot, approval-only bootstrap before identity resolution. |
| src/optimus/acp/launch_audit.py | Fail-closed audit consumer; no directory creation. |
| tests/unit/acp/test_launch_audit.py | Missing/symlink runtime-root failures. |
| tests/unit/acp/test_launch_approval_cli.py | Durable/one-shot ordering, resolved-target, no-record, snapshot tests. |
| tests/unit/acp/conftest.py | Test-only completed-approval setup. |
| tests/unit/acp/test_main_wiring.py | Unapproved no-write and approved/legacy launch lifecycle tests. |
| tests/unit/tools/test_run_plan996_acpx_security_evidence.py | Evidence-tool parity and direct-record helper lifecycle. |
| tests/integration/acp/test_launch_trust_flow.py | Real assembled POSIX audit-to-revalidation proof. |

---

### Task 0: Freeze and Commit the Reviewed Plan

**Files:**

- Create: docs/superpowers/reviews/2026-07-19-plan-9-98-fu-2-implementation-plan-approval.md
- Add: the approved design spec and this plan

**Produces:** A pristine, two-signature, digest-pinned plan before any production or test mutation.

**Pristine-byte safeguard:** Do not tick any Task 0 checkbox until the Task 0 commit lands. That commit must contain all five Task 0 checkboxes as unchecked; otherwise the approval digest attests to the wrong bytes. Tick them only afterward as checkbox-only working-tree progress.

- [ ] **Step 1: Verify baseline, design digest, and protected state.**

Run:

~~~bash
git status --short
git rev-parse HEAD
uv run python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('docs/superpowers/specs/2026-07-19-workspace-runtime-bootstrap-ci-design.md').read_bytes()).hexdigest().upper())"
git diff --name-only 287adf923cac5400a258551351cb908f7f39de4d -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md src/optimus/acp/launch_gate.py src/optimus/acp/launch_policy.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py
git diff 287adf923cac5400a258551351cb908f7f39de4d -- docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
~~~

Expected: baseline matches; design digest matches the Global Constraint; the strictly frozen-path command is silent; the FU-1 pipeline prints nothing because its only permitted drift is unchecked-to-checked checkbox lines; uv.lock and .claude are preserved.

- [ ] **Step 2: Obtain and record reviewer and operator approval for exact bytes.**

Create the approval record after both approvals with: plan path; baseline commit; design spec digest; literal Step 3 plan digest; reviewer identity and exact statement; operator identity and exact statement; and scope restricted to approval-time resolved .optimus bootstrap plus fail-closed audit consumption.

- [ ] **Step 3: Compute the pristine plan digest with literal uv run.**

~~~bash
uv run python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md').read_bytes()).hexdigest().upper())"
~~~

Expected: copy the exact uppercase output to the approval record.

- [ ] **Step 4: Commit only planning artifacts.**

~~~bash
git diff --check
git add docs/superpowers/specs/2026-07-19-workspace-runtime-bootstrap-ci-design.md docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md docs/superpowers/reviews/2026-07-19-plan-9-98-fu-2-implementation-plan-approval.md
git commit -m "docs: approve Plan 9.98-FU-2 runtime bootstrap"
~~~

Expected: exactly these three files are committed.

- [ ] **Step 5: Verify committed pristine bytes, then tick Task 0.**

~~~bash
git show --format= --name-only HEAD
git show HEAD:docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md > /tmp/plan-9-98-fu-2.md
git diff --no-index -- docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md /tmp/plan-9-98-fu-2.md
~~~

Expected: only three planning files; final comparison prints nothing.

### Task 1: Establish the Safe Runtime-Root Primitive

**Files:**

- Modify: tests/unit/acp/test_launch_audit.py
- Modify: tests/unit/acp/test_launch_approval_cli.py
- Modify: src/optimus/acp/operator_paths.py
- Modify: src/optimus/acp/launch_audit.py

**Interfaces:**

- WorkspaceRuntimeRootError(code: str, detail: str = "")
- bootstrap_workspace_runtime_root(paths: OperatorPaths) -> Path
- require_workspace_runtime_root(runtime_root: Path) -> Path
- append_launch_audit_event() retains its signature and raises LaunchAuditError with code AUDIT_DIR_UNAVAILABLE for an invalid root.

- [ ] **Step 1: Write RED tests for audit and bootstrap behavior.**

Replace the existing test_creates_runtime_root_if_missing with:

~~~python
def test_missing_runtime_root_fails_without_creating_it(self, tmp_path: Path) -> None:
    runtime_root = tmp_path / "missing-runtime-root"
    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        append_launch_audit_event(_sample_event(), runtime_root=runtime_root)
    assert not runtime_root.exists()
~~~

Add a symlink test that skips only if symlink creation is unavailable:

~~~python
def test_symlink_runtime_root_fails_without_writing_target(self, tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    runtime_root = tmp_path / ".optimus"
    try:
        runtime_root.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        append_launch_audit_event(_sample_event(), runtime_root=runtime_root)
    assert not (target / "launch-audit.ndjson").exists()
~~~

In CLI tests, build real OperatorPaths from a workspace symlink and assert bootstrap creates the resolved target .optimus, rejects a regular file there, and never writes through a final symlink.

- [ ] **Step 2: Run the focused RED selector.**

~~~bash
uv run pytest tests/unit/acp/test_launch_audit.py tests/unit/acp/test_launch_approval_cli.py -q
~~~

Expected: genuine failures because audit calls mkdir() and the new helper interface does not exist.

- [ ] **Step 3: Implement resolved-root validation and bootstrap.**

In operator_paths.py, import stat, add the exception, and implement:

~~~python
class WorkspaceRuntimeRootError(ValueError):
    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)

def require_workspace_runtime_root(runtime_root: Path) -> Path:
    try:
        metadata = runtime_root.lstat()
    except OSError as exc:
        raise WorkspaceRuntimeRootError(code="RUNTIME_ROOT_UNAVAILABLE") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WorkspaceRuntimeRootError(code="RUNTIME_ROOT_UNSAFE")
    return runtime_root

def bootstrap_workspace_runtime_root(paths: OperatorPaths) -> Path:
    runtime_root = paths.runtime_root
    if runtime_root.parent != paths.workspace_root:
        raise WorkspaceRuntimeRootError(code="RUNTIME_ROOT_UNSAFE")
    try:
        runtime_root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise WorkspaceRuntimeRootError(code="RUNTIME_ROOT_UNAVAILABLE") from exc
    return require_workspace_runtime_root(runtime_root)
~~~

Do not use parents=True; the resolved workspace exists. lstat() is required so a final .optimus symlink is rejected rather than followed.
Before accepting this implementation, the reviewer must assess the mkdir-to-lstat final-component race against the project's trusted-path threat model. If this sequence cannot be accepted without a race-free primitive available on every supported platform, stop implementation and request a reviewed plan amendment; do not silently substitute a weaker check.

In launch_audit.py, remove runtime_root.mkdir(...); validate through require_workspace_runtime_root() before serialization and translate its exception to LaunchAuditError(code="AUDIT_DIR_UNAVAILABLE", detail="runtime root is unavailable"). Do not reveal paths.

- [ ] **Step 4: Run GREEN tests and lint.**

~~~bash
uv run pytest tests/unit/acp/test_launch_audit.py tests/unit/acp/test_launch_approval_cli.py -q
uv run ruff check src/optimus/acp/operator_paths.py src/optimus/acp/launch_audit.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_launch_approval_cli.py
~~~

Expected: normal append works with an existing directory; missing/symlink roots create and write nothing.

- [ ] **Step 5: Reviewer checkpoint and commit.**

Reviewer verifies the lstat final-component rule, no audit mkdir, and stable error mapping. Then:

~~~bash
git diff --check
git add src/optimus/acp/operator_paths.py src/optimus/acp/launch_audit.py tests/unit/acp/test_launch_audit.py tests/unit/acp/test_launch_approval_cli.py
git commit -m "fix: require initialized workspace runtime root"
~~~

### Task 2: Bootstrap Both Approval Modes From One Snapshot

**Files:**

- Modify: src/optimus/acp/launch_approval_cli.py
- Modify: tests/unit/acp/test_launch_approval_cli.py

**Interfaces:**

- _prepare_approval_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]
- _prepare_candidate_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]
- _resolve_candidate(..., snapshot: LaunchEnvironmentSnapshot, operator_paths: OperatorPaths) -> LaunchCandidate
- _cmd_approve() runs TTY check, candidate context, bootstrap, approval store, then candidate resolution for durable and one-shot modes alike.
- _cmd_run() runs the same candidate-context resolution without bootstrap, preserving the headless durable-approval route.

- [ ] **Step 1: Write approval-ceremony RED tests.**

Add a durable test that wraps resolve_workspace_identity and proves a real non-symlink .optimus exists at capture time. Use synthetic environment values, a FakeKeyring, and patched _require_tty; assert the durable record is created only afterward.

Add an equivalent one-shot-without-target test:

~~~python
assert cli_module._cmd_approve(workspace, mode="one-shot", target_argv=[]) == 0
assert (workspace.resolve() / ".optimus").is_dir()
assert identity_observations == [workspace.resolve() / ".optimus"]
~~~

Add a failure test that makes bootstrap_workspace_runtime_root raise WorkspaceRuntimeRootError(code="RUNTIME_ROOT_UNAVAILABLE"); call main(... approve --mode durable) with TTY mocks and assert exit 2. Make _resolve_store, build_approval_record, and subprocess.run fail the test if called; assert neither durable nor one-shot data was written.

Add a snapshot canary: mutate live OPTIMUS_CONFIG_ROOT immediately after LaunchEnvironmentSnapshot.capture; bootstrap and candidate must use the original snapshot value.

Add a plain _cmd_run regression: arrange a matching durable record, remove workspace/.optimus, patch subprocess.run to return success, and assert _cmd_run does not call bootstrap_workspace_runtime_root or recreate the directory. This is intentionally the non-interactive durable-record path; it proves the signature refactor cannot turn it into a second initializer.

- [ ] **Step 2: Run approval RED tests.**

~~~bash
uv run pytest tests/unit/acp/test_launch_approval_cli.py -q
~~~

Expected: failures show identity occurs before bootstrap, missing preparation interfaces, or bootstrap failure reaches a record path. No real OS keyring failure is acceptable.

- [ ] **Step 3: Implement the single-snapshot preparation boundary.**

Implement the non-bootstrapping common preparation function:

~~~python
def _prepare_candidate_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]:
    snapshot = LaunchEnvironmentSnapshot.capture(os.environ)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace_root,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    return snapshot, paths
~~~

Implement the approval-only wrapper:

~~~python
def _prepare_approval_context(workspace_root: Path) -> tuple[LaunchEnvironmentSnapshot, OperatorPaths]:
    snapshot, paths = _prepare_candidate_context(workspace_root)
    bootstrap_workspace_runtime_root(paths)
    return snapshot, paths
~~~

Refactor _resolve_candidate to receive snapshot and paths, resolve identity only there, and call resolve_launch_candidate with those exact objects. At _cmd_approve start, after _require_tty and separator stripping, call _prepare_approval_context before _resolve_store; then pass prepared objects into _resolve_candidate. In _cmd_run, call _prepare_candidate_context before _resolve_store and pass its result to _resolve_candidate; it must not call _prepare_approval_context or bootstrap_workspace_runtime_root. Add WorkspaceRuntimeRootError handling in main() that prints only optimus-trust: code and returns 2. Update every direct unit-test call to construct one snapshot and paths explicitly.

- [ ] **Step 4: Run GREEN tests and static parse.**

~~~bash
uv run pytest tests/unit/acp/test_launch_approval_cli.py -q
uv run python -c "import ast, pathlib; ast.parse(pathlib.Path('src/optimus/acp/launch_approval_cli.py').read_text(encoding='utf-8')); print('parsed')"
uv run ruff check src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
~~~

Expected: all pass, parsed prints, and no second live environment read exists.

- [ ] **Step 5: Reviewer checkpoint and commit.**

Reviewer verifies post-TTY-only bootstrap, the same snapshot feeds path and candidate resolution, durable/one-shot share it, and _cmd_run has an explicitly non-bootstrapping context path. Then:

~~~bash
git diff --check
git add src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
git commit -m "fix: bootstrap runtime root during approval"
~~~

### Task 3: Prove Launch and Evidence Flows Consume, Never Initialize

**Files:**

- Modify: tests/unit/acp/conftest.py
- Modify: tests/unit/acp/test_main_wiring.py
- Modify: tests/unit/tools/test_run_plan996_acpx_security_evidence.py
- Modify: tests/integration/acp/test_launch_trust_flow.py

**Interfaces:** Direct test record-authoring helpers invoke bootstrap_workspace_runtime_root(paths) before resolve_workspace_identity(). Neither __main__.py nor the evidence tool gains a bootstrap call; both consume through the Task 1 audit gate.

- [ ] **Step 1: Write composed RED tests.**

Extend test_unapproved_workspace_fails_closed_before_any_side_effect:

~~~python
assert not (tmp_path / ".optimus").exists()
~~~

Add an approved fresh-workspace main-path test using the real approval preparation boundary plus fake keyring/TTY dependencies. Drive acp_main.main with no-auto-start; assert exit 0, exactly one audit line, and no WORKSPACE_IDENTITY_CHANGED output.

Add a legacy-root test: author an approval, remove .optimus, launch, and assert exit 2, AUDIT_DIR_UNAVAILABLE, no recreated root, and no Redis/Gateway/server calls.

For the evidence tool, add a matching missing-root composed test: after authoring, remove .optimus; capture_acpx() must raise LaunchAuditError, never call subprocess.Popen, and never recreate the root.

Add this POSIX-only integration proof without mocking audit or revalidation:

~~~python
bootstrap_workspace_runtime_root(authoring_paths)
identity = resolve_workspace_identity(workspace_root)
# build the record, resolve a separate launch candidate, authorize, append audit
append_launch_audit_event(event, runtime_root=launch_candidate.operator_paths.runtime_root)
revalidate_workspace_identity(launch_candidate.workspace_identity)  # succeeds
(workspace_root / "unrelated-post-approval-entry").write_text("synthetic", encoding="utf-8")
with pytest.raises(TrustedPathError, match="WORKSPACE_IDENTITY_CHANGED"):
    revalidate_workspace_identity(launch_candidate.workspace_identity)
~~~

- [ ] **Step 2: Run composed RED selector.**

~~~bash
uv run pytest tests/unit/acp/test_main_wiring.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/integration/acp/test_launch_trust_flow.py -q
~~~

Expected: genuine lifecycle failures only. Existing direct-record helpers initially fail missing-root audit because they do not yet model approval; Step 3 corrects that setup.

- [ ] **Step 3: Update test-only authoring helpers, not launch code.**

In authorize_workspace_for_test, _write_durable_approval, and the integration authoring side, resolve OperatorPaths, call bootstrap_workspace_runtime_root(paths), then capture identity and build the record. Do not bootstrap in the later launch-resolution side.

Do not add a bootstrap call to src/optimus/acp/__main__.py or tools/run_plan996_acpx_security_evidence.py; the Task 1 audit primitive makes the launch-side no-write contract structural.

- [ ] **Step 4: Run composed GREEN selector.**

~~~bash
uv run pytest tests/unit/acp/test_main_wiring.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/integration/acp/test_launch_trust_flow.py -q
uv run ruff check tests/unit/acp/conftest.py tests/unit/acp/test_main_wiring.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/integration/acp/test_launch_trust_flow.py
~~~

Expected: approved fresh workspaces audit/revalidate; later direct mutation still fails; unapproved and legacy paths create no root.

- [ ] **Step 5: Reviewer checkpoint and commit.**

Reviewer verifies fixtures model only a completed approval, not a launch bypass; audit occurs before revalidation in the POSIX proof; and production launch files contain no bootstrap call. Then:

~~~bash
git diff --check
git add tests/unit/acp/conftest.py tests/unit/acp/test_main_wiring.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py tests/integration/acp/test_launch_trust_flow.py
git commit -m "test: cover approved runtime root lifecycle"
~~~

### Task 4: Full Verification and Linux CI Gate

**Files:**

- Modify: this plan only, checkbox tracking after each stated gate passes

- [ ] **Step 1: Run local default gates.**

~~~bash
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
uv run ruff check .
uv run python tools/verify_plan996_logging_surfaces.py --manifest docs/superpowers/reviews/2026-07-15-plan-9-96-logging-surface-audit.json
git diff --check
~~~

Expected: no failures; coverage at least 80%; Ruff and logging verifier pass; default live markers remain deselected.

- [ ] **Step 2: Verify exact scope and frozen paths.**

~~~bash
git diff --name-only 287adf923cac5400a258551351cb908f7f39de4d
git diff --quiet 287adf923cac5400a258551351cb908f7f39de4d -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md src/optimus/acp/launch_gate.py src/optimus/acp/launch_policy.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py
git diff 287adf923cac5400a258551351cb908f7f39de4d -- docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md | grep '^[+-]' | grep -v '^[+-]\{3\}' | grep -vE '^\+- \[x\]' | grep -vE '^-- \[ \]'
git status --short
~~~

Expected: strictly frozen-path command is silent; the FU-1 checkbox-only pipeline is silent; only listed work plus protected existing noise is present.

- [ ] **Step 3: Pause for reviewer sign-off.**

Reviewer independently confirms: unchanged FU-1 identity semantics; audit cannot create roots; only post-TTY approval initializes; durable/one-shot share one snapshot; unapproved and legacy paths do not initialize; and the POSIX lifecycle proves both success and subsequent mutation failure.

- [ ] **Step 4: Pause for operator push authorization.**

Do not infer push permission from FU-1. Obtain explicit operator authorization for these reviewed commits.

- [ ] **Step 5: Push and inspect the governing Linux CI job.**

~~~bash
git push origin agent/kiro/plan-9-96
gh pr checks 60 --watch
~~~

Expected: GitHub Actions default Linux job succeeds. Inspect logs to confirm the prior WORKSPACE_IDENTITY_CHANGED self-invalidation failures are absent rather than hidden by deselection/retry.

## Definition of Done

- Both approval modes create only an empty resolved-workspace .optimus directory after TTY validation and before identity capture.
- Path bootstrap and candidate resolution use one environment snapshot; no ambient reread is added.
- Audit never creates a root and rejects missing, non-directory, and symlink roots without writing through redirects.
- On Linux, a fresh approved workspace audits then revalidates successfully; a later direct workspace mutation still fails WORKSPACE_IDENTITY_CHANGED before spawn.
- Unapproved, missing-root legacy, optimus-trust run, inspect, revoke, and evidence verification paths never initialize .optimus.
- Test-only direct record authors explicitly model completed approval bootstrap, without masking the unapproved-launch proof.
- Default pytest with coverage, full Ruff, logging-surface verification, frozen-path verification, and GitHub Actions Linux pass.
- Commits exclude frozen plans, existing approval records, uv.lock, .claude, and reviewer checkpoint logs.
