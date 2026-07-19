# Plan 9.98-FU-1 Workspace Identity and Linux CI Corrective Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILLS: Use superpowers:executing-plans to execute this plan task-by-task and superpowers:test-driven-development for every behavior change. Steps use checkbox syntax for tracking.

**Status:** Draft for reviewer-agent and operator review. Approval is determined only by the digest-pinned approval record committed in Task 0, not by this status line or later checkbox ticks.

**Goal:** Repair the workspace-identity TOCTOU defect found by Linux CI and remove host keyring, POSIX-umask, and child-locale assumptions from the default test suite.

**Architecture:** WorkspaceIdentity will bind the absolute lexical workspace path as supplied by the operator and its resolved target. Its digest will include device, inode, and st_ctime_ns; revalidation will reconstruct identity from the lexical path and fail closed on any digest change. Test-only changes will assert the intended boundary directly instead of depending on CI services or host behavior.

**Tech Stack:** Python, pathlib, dataclasses, pytest, pytest-cov, Ruff, GitHub Actions Ubuntu.

## Global Constraints

- Baseline is PR #60 head 9f2ddd7697e99cc977cc7b5897155127734af12a; work remains on the existing agent/kiro/plan-9-96 branch and PR.
- Do not edit the frozen Plan 9.96 or Plan 9.98 files, existing Plan 9.98 approval records, launch_gate.py, launch_policy.py, local_infra.py, local_gateway_secrets.py, uv.lock, .claude/, or any reviewer checkpoint log.
- Do not add Redis, Gateway credentials, ACPX, or a keyring backend to CI. The default marker expression continues to deselect live-dependency tests.
- No production code before its named RED test has run and failed for the intended reason.
- Never log or assert raw credential values; fixtures use synthetic values only.
- Never stage .claude/, .idea/, .kiro/, .zed/, .air/, uv.lock, or docs/superpowers/reviews/*-review-checkpoints.md.
- The stronger workspace digest intentionally invalidates old durable approvals. Reapproval is required; do not add a migration or compatibility bypass.
- Before every commit, run git diff --check and prove frozen paths unchanged from the baseline.

## File and Responsibility Map

| File | Responsibility |
|---|---|
| docs/superpowers/specs/2026-07-19-plan-9-98-fu-1-workspace-identity-ci-design.md | Approved design basis; committed only in Task 0. |
| docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md | This digest-pinned implementation plan. |
| docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval.md | Task 0 approval record; not a checkpoint log. |
| docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval-v2.md | Amendment approval record for the revised Task 1/2 identity behavior. |
| src/optimus/acp/trusted_paths.py | Lexical/resolved workspace identity and propagatable TrustedPathError. |
| src/optimus/acp/launch_approvals.py | Digest-only durable-record placeholders for expanded identities. |
| src/optimus/acp/launch_approval_cli.py | Inspect validates workspace before opening a keyring-backed store. |
| tests/unit/acp/test_trusted_paths.py | Identity, exception, symlink, and Windows-only tests. |
| tests/unit/acp/test_launch_approvals.py | Durable-record deserialization regression. |
| tests/integration/acp/test_launch_trust_flow.py | Authorization-to-revalidation replacement regression. |
| tests/unit/acp/test_main_wiring.py | Relocation has no post-authorization side effect. |
| tests/unit/acp/test_launch_approval_cli.py | Headless inspect and permission invocation. |
| tests/unit/acp/test_launch_gate.py | Owner-only .env.gateway fixtures. |
| tests/unit/tools/test_run_plan996_acpx_security_evidence.py | Fake keyring and direct Popen environment assertions. |

---

### Task 0: Freeze and Commit the Reviewed Corrective Plan

**Files:**
- Create: docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval.md
- Add: the approved design spec and this plan

**Produces:** A committed, digest-pinned, reviewer- and operator-approved plan before any test or production mutation.

**Pristine-byte safeguard:** Do not tick the checkboxes for Task 0 Steps 1-4 until after the Step 5 planning commit lands. Ticking any of them earlier changes this plan file before Step 4 hashes it, so the approval record would no longer attest to the pristine bytes the reviewer and operator approved. Step 5 must commit this plan with all five Task 0 checkboxes still `- [ ]`. Once that pristine planning commit has landed, all five Task 0 checkboxes may be ticked as ordinary working-tree progress tracking; those later checkbox-only changes do not invalidate the approval, but any later substantive plan-text change requires fresh review, operator approval, and a new digest.

- [x] **Step 1: Verify baseline and pristine scope.**

Run:

~~~
git status --short
git rev-parse HEAD
git diff --name-only 9f2ddd7697e99cc977cc7b5897155127734af12a -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md src/optimus/acp/launch_gate.py src/optimus/acp/launch_policy.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py
~~~

Expected: HEAD is the stated baseline, only the new design/plan documents plus pre-existing uv.lock and .claude/ appear, and the frozen-path command prints nothing.

- [x] **Step 2: Obtain reviewer approval for the exact plan bytes.**

The reviewer reads the whole plan, verifies RED-before-GREEN ordering and scope, and records their identity and exact approval statement in the Task 0 approval record.

- [x] **Step 3: Obtain operator approval for the same exact bytes.**

Record operator identity and exact approval statement in the same approval record. Do not begin Task 1 until both approvals exist.

- [x] **Step 4: Compute the pristine digest using literal uv run python.**

Run in a terminal where uv is genuinely on PATH:

~~~
uv run python -c "import hashlib, pathlib; print(hashlib.sha256(pathlib.Path('docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md').read_bytes()).hexdigest().upper())"
~~~

Create the approval record:

~~~
# Plan 9.98-FU-1 Implementation Plan Approval

- Plan: docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md
- Baseline commit: 9f2ddd7697e99cc977cc7b5897155127734af12a
- Plan SHA-256: exact uppercase command output
- Reviewer approval: reviewer identity and exact approval statement
- Operator approval: operator identity and exact approval statement
- Scope: workspace identity TOCTOU repair and default-Linux-CI isolation only
~~~

- [x] **Step 5: Commit only the reviewed planning artifacts.**

Run:

~~~
git diff --check
git add docs/superpowers/specs/2026-07-19-plan-9-98-fu-1-workspace-identity-ci-design.md docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval.md
git commit -m "docs: approve Plan 9.98-FU-1 corrective work"
~~~

Expected: exactly these three docs in one commit. Do not stage uv.lock, .claude/, or a checkpoint log.

### Task 0A: Freeze the v2 Identity-Test Amendment

**Files:**
- Create: docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval-v2.md
- Modify: this plan only

**Produces:** A reviewer- and operator-approved amended plan before replacing the Task 1 RED test or continuing Task 2.

**Pristine-byte safeguard:** Do not tick any Task 0A checkbox until its amendment commit lands. The amendment commit must contain this plan exactly as freshly reviewed and hashed, including the completed Task 0 checkbox history, the reset Task 1 checkboxes below, and all Task 0A checkboxes still unchecked.

- [ ] **Step 1: Obtain reviewer and operator approval for exact amended bytes.**

The reviewer must verify that only the completed Task 0 checkbox history, Task 0A, Task 1, Task 2, File Map, and Definition of Done change. The operator approval must follow the reviewer approval. Both statements go in the v2 record.

- [ ] **Step 2: Compute and record the amended plan digest.**

Run the same literal command from Task 0 Step 4. Record its uppercase output, the reviewer statement, operator statement, baseline planning commit d250003, and scope limited to the POSIX mutation test, Windows lexical normalization, and related wording in the v2 record.

- [ ] **Step 3: Commit the amended plan and v2 record only.**

Run git diff --check, stage this plan plus the v2 record only, and commit with message docs: amend Plan 9.98-FU-1 identity tests. Do not stage source or test files. After the commit, tick Task 0A checkboxes as ordinary checkbox-only progress.

### Task 1: Establish the Workspace-Identity RED Suite

**Files:**
- Modify: tests/unit/acp/test_trusted_paths.py:185-310
- Modify: tests/unit/acp/test_launch_approvals.py:76-90
- Modify: tests/integration/acp/test_launch_trust_flow.py:270-305
- Modify: tests/unit/acp/test_main_wiring.py relocation test

**Produces:** Failing tests for missing lexical path, change-time binding, propagatable exception behavior, and durable-record placeholders.

**Amendment reset:** The uncommitted Task 2 production draft and its Task-2-only fixture adaptations were written before the corrected RED tests existed. Before this amended Task 1 begins, discard those draft-only changes with `apply_patch` back to the `d250003` content. Retain or revise only the Task 1 test additions below. This is not a revert of committed work; it enforces the plan's TDD constraint that the corrected tests fail against the committed baseline behavior.

- [ ] **Step 1: Add lexical-path and platform-specific change-time RED tests.**

In test_trusted_paths.py, import os (alongside the existing sys import) and add:

~~~python
def test_identity_binds_lexical_path_and_target_change_time(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "workspace-link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires elevated privileges")

    identity = resolve_workspace_identity(link)

    expected_lexical = os.path.normcase(str(link.absolute())) if sys.platform == "win32" else str(link.absolute())
    assert identity.lexical_path == expected_lexical
    assert identity.canonical_path == str(target.resolve())
    assert identity.change_time_ns == target.stat().st_ctime_ns


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: directory ctime changes on entry creation")
def test_revalidation_fails_after_workspace_directory_metadata_change(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    identity = resolve_workspace_identity(workspace)
    (workspace / "added-after-authorization").write_text("synthetic", encoding="utf-8")

    with pytest.raises(TrustedPathError, match="WORKSPACE_IDENTITY_CHANGED"):
        revalidate_workspace_identity(identity)
~~~

Keep the existing post-authorization symlink-repoint and delete/recreate tests; both must continue to require WORKSPACE_IDENTITY_CHANGED.

- [ ] **Step 2: Add durable-record and exception RED tests.**

Add a durable store round trip in test_launch_approvals.py that asserts:

~~~python
assert loaded is not None
assert loaded.workspace_identity.digest == record.workspace_identity.digest
assert loaded.workspace_identity.lexical_path == ""
assert loaded.workspace_identity.change_time_ns == 0
~~~

Add this to test_trusted_paths.py:

~~~python
def test_trusted_path_error_propagates_as_its_own_type() -> None:
    with pytest.raises(TrustedPathError) as exc_info:
        raise TrustedPathError(code="WORKSPACE_NOT_FOUND", detail="synthetic")

    assert exc_info.value.code == "WORKSPACE_NOT_FOUND"
~~~

Mark TestWindowsCaseNormalization.test_case_variants_produce_same_identity with pytest.mark.skipif(sys.platform != "win32", reason="Windows-only: case-insensitive filesystem identity"), then assert both id_upper.lexical_path == id_lower.lexical_path and id_upper.digest == id_lower.digest.

- [ ] **Step 3: Run the identity RED selector.**

Run:

~~~
uv run pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/integration/acp/test_launch_trust_flow.py::test_full_launch_trust_flow_relocated_workspace_fails_revalidation tests/unit/acp/test_main_wiring.py::test_workspace_relocated_after_authorization_fails_closed_before_side_effect -q
~~~

Expected before Task 2: genuine missing-field failures, the POSIX metadata-mutation DID NOT RAISE failure, or the current FrozenInstanceError. Do not proceed on collection errors or vacuous passes.

### Task 2: Implement Fail-Closed Lexical Workspace Revalidation

**Files:**
- Modify: src/optimus/acp/trusted_paths.py:22-341
- Modify: src/optimus/acp/launch_approvals.py:371-380
- Modify: all Task 1 test files plus tests/unit/acp/test_launch_gate.py:27-40,226-235

**Interfaces:**
- WorkspaceIdentity gains lexical_path: str and change_time_ns: int.
- resolve_workspace_identity(workspace_root: Path) -> WorkspaceIdentity remains public.
- revalidate_workspace_identity(identity: WorkspaceIdentity) -> None still raises TrustedPathError(code="WORKSPACE_IDENTITY_CHANGED") on a mismatch.

- [ ] **Step 1: Replace the frozen trusted-path exception and expand identity.**

Use the established ApprovalError pattern:

~~~python
class TrustedPathError(ValueError):
    """Raised when trusted path resolution or workspace identity fails."""

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}" if self.detail else self.code
~~~

Declare WorkspaceIdentity fields in this order:

~~~python
lexical_path: str
canonical_path: str
device: int
inode: int
change_time_ns: int
repository_root: str | None
git_common_dir: str | None
digest: str
~~~

- [ ] **Step 2: Bind lexical path and change time into the digest.**

Import os and sys in trusted_paths.py. At the start of resolve_workspace_identity, preserve symlinks while normalizing Windows caller casing:

~~~python
lexical_path = str(workspace_root.absolute())
if sys.platform == "win32":
    lexical_path = os.path.normcase(lexical_path)
resolved = Path(lexical_path).resolve()
~~~

After stat = resolved.stat(), include lexical_path and stat.st_ctime_ns in the NUL-delimited _compute_identity_digest input and returned WorkspaceIdentity. Preserve existing canonical-path, device, inode, and Git inputs; do not read environment variables or create directories.

- [ ] **Step 3: Revalidate from the lexical path.**

Replace direct Path(identity.canonical_path) restatting with:

~~~python
try:
    current = resolve_workspace_identity(Path(identity.lexical_path))
except TrustedPathError as exc:
    raise TrustedPathError(
        code="WORKSPACE_IDENTITY_CHANGED",
        detail="workspace directory no longer resolves to the authorized identity",
    ) from exc

if current.digest != identity.digest:
    raise TrustedPathError(
        code="WORKSPACE_IDENTITY_CHANGED",
        detail="workspace identity digest mismatch",
    )
~~~

The serialized record placeholder must never reach this function; callers revalidate only the fresh identity from the current LaunchCandidate.

- [ ] **Step 4: Preserve digest-only durable record reads.**

In _deserialize_approval_record, construct:

~~~python
workspace_identity = WorkspaceIdentity(
    lexical_path="",
    canonical_path="",
    device=0,
    inode=0,
    change_time_ns=0,
    repository_root=None,
    git_common_dir=None,
    digest=data["workspace_digest"],
)
~~~

Update every direct WorkspaceIdentity fixture in test_launch_approvals.py and test_launch_gate.py with synthetic lexical path and change-time values. Do not add dataclass defaults.

- [ ] **Step 5: Run the identity suite GREEN and commit.**

Run:

~~~
uv run pytest tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/integration/acp/test_launch_trust_flow.py::test_full_launch_trust_flow_relocated_workspace_fails_revalidation tests/unit/acp/test_main_wiring.py::test_workspace_relocated_after_authorization_fails_closed_before_side_effect -q
uv run ruff check src/optimus/acp/trusted_paths.py src/optimus/acp/launch_approvals.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py
git diff --check
git add src/optimus/acp/trusted_paths.py src/optimus/acp/launch_approvals.py tests/unit/acp/test_trusted_paths.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_gate.py tests/integration/acp/test_launch_trust_flow.py tests/unit/acp/test_main_wiring.py
git commit -m "fix: harden workspace identity revalidation"
~~~

Expected: the POSIX metadata-mutation test is skipped on Windows, the Windows case-normalization test is skipped on POSIX, all other selected tests pass, and Ruff/diff checks are clean.

### Task 3: Make optimus-trust inspect Headless-Safe

**Files:**
- Modify: tests/unit/acp/test_launch_approval_cli.py:47-54,627-645
- Modify: src/optimus/acp/launch_approval_cli.py:321-333

**Produces:** A nonexistent inspect workspace fails before any real keyring access.

- [ ] **Step 1: Write the CLI ordering RED test.**

Give test_inspect_on_nonexistent_workspace_fails_gracefully a monkeypatch parameter. Patch optimus.acp.launch_approval_cli._resolve_store to call pytest.fail("keyring store must not be opened for a missing workspace"); invoke main with nonexistent workspace and inspect; assert a nonzero result and WORKSPACE_NOT_FOUND in stderr. Update test_error_messages_contain_no_raw_values with the same no-store assertion while retaining the no-secret check.

- [ ] **Step 2: Run the CLI RED selector.**

Run:

~~~
uv run pytest tests/unit/acp/test_launch_approval_cli.py::TestCliParsing::test_inspect_on_nonexistent_workspace_fails_gracefully tests/unit/acp/test_launch_approval_cli.py::TestOutputContainsNoSecrets::test_error_messages_contain_no_raw_values -q
~~~

Expected before implementation: patched store failure proves the old ordering opens a keyring-backed store first.

- [ ] **Step 3: Resolve identity before opening the store.**

Make _cmd_inspect begin:

~~~python
def _cmd_inspect(workspace_root: Path) -> int:
    """Display approval metadata (no secrets, no handles)."""
    workspace_identity = resolve_workspace_identity(workspace_root)
    store, _ = _resolve_store(workspace_root)
~~~

Leave store.read_durable(workspace_identity.digest) and behavior for existing workspaces unchanged. Do not add a fallback keyring.

- [ ] **Step 4: Run the CLI suite GREEN and commit.**

Run:

~~~
uv run pytest tests/unit/acp/test_launch_approval_cli.py -q
uv run ruff check src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
git diff --check
git add src/optimus/acp/launch_approval_cli.py tests/unit/acp/test_launch_approval_cli.py
git commit -m "fix: validate inspect workspace before keyring access"
~~~

### Task 4: Remove Host-Dependent Unit-Test Assumptions

**Files:**
- Modify: tests/unit/acp/test_launch_approval_cli.py
- Modify: tests/unit/acp/test_launch_gate.py:836-1040
- Modify: tests/unit/tools/test_run_plan996_acpx_security_evidence.py:100-130,340-405,494-550,1146-1195,2255-2325,2495-2585

**Produces:** Unit tests that preserve security coverage without Redis, a system keyring backend, POSIX umask assumptions, or Python locale coercion.

- [ ] **Step 1: Make permission invocation a recorder/no-op.**

In test_env_gateway_permission_check_is_actually_invoked, replace the wrapper that calls the original validator with:

~~~python
def recording_validate(path: Path, **_kwargs: object) -> None:
    calls.append(path)
~~~

Retain the assertion that exactly the .env.gateway path was passed. In both TestSingleReadCredentialResolution tests that write a real .env.gateway, add env_gateway.chmod(0o600) immediately after write_text when sys.platform != "win32".

- [ ] **Step 2: Use fake keyring at every main test boundary.**

Extend _patch_keyring:

~~~python
monkeypatch.setattr(real_keyring, "get_password", fake.get_password)
monkeypatch.setattr(real_keyring, "set_password", fake.set_password)
monkeypatch.setattr(real_keyring, "delete_password", fake.delete_password)
monkeypatch.setattr(capture_tool, "keyring", fake)
~~~

Call _patch_keyring(monkeypatch, FakeKeyring()) in test_main_default_path_never_resolves_optimus_agent, test_main_generates_launch_session_id_when_absent, test_agent_invocation_elevated_drive_session_passes_grant_only_to_inner_agent, test_main_returns_exit_2_with_clean_message_on_unapproved_workspace, and test_main_returns_exit_2_on_workspace_relocation_between_audit_and_spawn.

- [ ] **Step 3: Assert the actual Popen environment.**

In test_spawn_uses_acpx_client_environment_not_effective_agent_environment, spy on capture_tool.subprocess.Popen, save kwargs["env"], and run a child that exits zero. Replace child JSON environment inspection with:

~~~python
assert observed_env == _system_environment()
assert not any(name.startswith("OPTIMUS_") for name in observed_env)
~~~

This tests the supplied mapping and is not affected by Python adding LC_CTYPE inside a Linux child.

- [ ] **Step 4: Run portability tests GREEN and commit.**

Run:

~~~
uv run pytest tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_gate.py::TestSingleReadCredentialResolution tests/unit/tools/test_run_plan996_acpx_security_evidence.py -q
uv run ruff check tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_gate.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git diff --check
git add tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_gate.py tests/unit/tools/test_run_plan996_acpx_security_evidence.py
git commit -m "test: make launch trust checks portable in CI"
~~~

Expected: all selected tests pass without Redis or a real keyring; fixtures remain synthetic.

### Task 5: Verify the PR Gate and Publish Follow-Up Commits

**Files:** No source changes; verify committed Task 0-4 scope only.

**Produces:** Evidence that the required GitHub Actions job passes on Linux and the PR contains no forbidden noise.

- [ ] **Step 1: Run the required pytest job locally.**

Run:

~~~
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
~~~

Expected: zero failures, aggregate coverage at least 80%, and live-dependency tests remain deselected by the default marker expression.

- [ ] **Step 2: Run repository integrity checks.**

Run:

~~~
uv run ruff check .
uv run python tools/verify_plan996_logging_surfaces.py
git diff --check 9f2ddd7697e99cc977cc7b5897155127734af12a
git diff --name-only 9f2ddd7697e99cc977cc7b5897155127734af12a -- docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md src/optimus/acp/launch_gate.py src/optimus/acp/launch_policy.py src/optimus/acp/local_infra.py src/optimus/acp/local_gateway_secrets.py
git status --short
~~~

Expected: Ruff and logging-surface audit pass; diff check clean; frozen-path command silent; no staged or tracked uv.lock, .claude/, or checkpoint log.

- [ ] **Step 3: Obtain reviewer sign-off.**

The reviewer verifies the PR diff contains only Tasks 0-4 files, the Linux identity tests are genuine, and the default configuration still deselects real Redis/Gateway/ACPX tiers rather than substituting fakes.

- [ ] **Step 4: Push only after explicit operator authorization and verify GitHub Actions.**

After explicit operator push authorization, push the existing PR branch and wait for clean-environment-recheck. Record its run URL and zero-failure result in the PR discussion or reviewer-owned checkpoint log; never stage the checkpoint log.

### Definition of Done

- [ ] The Plan 9.98-FU-1 record pins the exact plan digest and both approvals before source mutation.
- [ ] Revalidation detects symlink retargeting and same-path workspace replacement before any spawn-side effect.
- [ ] On POSIX, creating an entry in the workspace directory after authorization invalidates the change-time-bound identity; on Windows, case variants of one lexical workspace path produce one identity digest.
- [ ] Digest-only durable records deserialize with inert expanded-identity placeholders; placeholders never reach revalidation.
- [ ] optimus-trust inspect fails a nonexistent workspace before touching the keyring.
- [ ] Host-keyring, POSIX-permission, Windows-case, and LC_CTYPE CI failures are eliminated without adding CI services.
- [ ] Required pytest, full Ruff, logging-surface audit, frozen-path, and GitHub Actions checks pass.
- [ ] uv.lock, .claude/, and reviewer checkpoint logs remain unstaged.
