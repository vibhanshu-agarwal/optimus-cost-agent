# Plan 9.98-FU-3: POSIX Runtime-Root Failure-Path Test Alignment

**Status:** Draft for reviewer review.

**Baseline:** `origin/main` at `41634cd2dcc8fae31315f9dfacdd1b95c679d82f`

**Goal:** Align the five Linux-failing runtime-root tests with the preserved workspace-identity and runtime-root lifecycle contracts, without weakening the security binding or changing production behavior.

## Problem statement

Plan 9.98-FU-2 merged with a known Linux CI defect. GitHub Actions run `29690328862` reported five failures in the clean Ubuntu environment:

1. `tests/unit/acp/test_launch_approval_cli.py::TestApprovalTimeRuntimeBootstrap::test_run_does_not_bootstrap_a_missing_runtime_root`
2. `tests/unit/acp/test_main_wiring.py::test_legacy_approved_workspace_missing_root_fails_without_recreating_it`
3. `tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_stops_when_real_audit_runtime_root_is_a_regular_file`
4. `tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_blocks_child_when_composed_audit_fails`
5. `tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_missing_approved_runtime_root_never_spawns_or_recreates_it`

The failure is a test-contract collision, not an identified production defect. `WorkspaceIdentity` binds the workspace directory's lexical path, resolved target, device, inode, and `st_ctime_ns` into its digest. On POSIX, removing or replacing the direct child `.optimus` changes the parent workspace directory's `st_ctime_ns`. A later full entrypoint therefore resolves a new workspace digest and correctly fails closed while reading the durable approval:

```text
resolve workspace identity
  -> resolve launch candidate
  -> read durable approval using the current workspace digest
  -> LaunchGateError(NO_APPROVAL)
```

The audit failure is a different contract. It is observable only after a launch has already been authorized and the audit consumer validates the current runtime-root path:

```text
authorized CaptureLaunch
  -> append_authorized_audit()
  -> append_launch_audit_event()
  -> require_workspace_runtime_root() / lstat()
  -> LaunchAuditError(AUDIT_DIR_UNAVAILABLE)
```

The POSIX baseline was independently reproduced on the host in WSL2 Ubuntu-24.04 with the exact five selectors. All five failed, and the three capture-rooted failures reached `launch_gate.py:670` with `LaunchGateError(NO_APPROVAL)`, confirming the ordering above. The WSL environment is now the interim POSIX verification path; the Ubuntu GitHub Actions job remains the final release gate.

## Invariants and scope

### Invariants to preserve

- Keep the complete FU-1 workspace identity binding: lexical path, canonical/resolved path, device, inode, and `st_ctime_ns`.
- Keep revalidation fail-closed with `WORKSPACE_IDENTITY_CHANGED` on any identity digest change.
- Keep approval-time `.optimus` bootstrap exclusively on the TTY-gated approval path.
- Keep launch, `optimus-trust run`, the evidence tool, inspection, revocation, and verification paths non-bootstrapping.
- Keep `append_launch_audit_event()` read-only with respect to the runtime root: an absent, non-directory, or symlinked root raises `AUDIT_DIR_UNAVAILABLE` and does not recreate or write through it.
- Keep the audit-before-revalidation-before-child-spawn ordering.
- Keep the child/infra no-side-effect assertions on every rejected path.

### Scope

This is a test-contract alignment change. Expected implementation files are limited to the five failing test locations, with shared test-only helpers permitted in the evidence test module. No file under `src/` is expected to change. Existing direct audit tests in `tests/unit/acp/test_launch_audit.py` remain in the suite and are not deleted, weakened, skipped, deselected, or platform-xfailed.

The unrelated working-tree changes in `uv.lock` and `.claude/settings.local.json` are pre-existing user state and are explicitly out of scope. They must remain untouched and unstaged.

## Design

### Bucket A: Full-entrypoint post-approval mutations prove `NO_APPROVAL`

The two full-entrypoint tests intentionally retain their current timing: they authorize the workspace, mutate the direct child `.optimus`, and then call the complete launch entrypoint. On POSIX, the expected result is `NO_APPROVAL` at durable-record lookup because the workspace identity has changed. The assertions must prove that no runtime root is recreated and no child, Redis, Gateway, or configured server side effect occurs.

The tests must express the platform contract explicitly. The POSIX branch is authoritative for the Linux failure and asserts exit code `2` plus the `no launch approval found` remediation. Windows retains its existing creation-time-compatible no-bootstrap assertion where removing the child does not change the parent `st_ctime`; this is a platform-semantic branch, not a skip or xfail of the Linux test.

The tests do not change production error handling to translate `NO_APPROVAL` into `AUDIT_DIR_UNAVAILABLE`. Those codes describe different points in the launch sequence and must remain distinct.

### Bucket B: Already-authorized capture mutations prove `AUDIT_DIR_UNAVAILABLE`

The three evidence-tool tests must reach the audit consumer with a real authorized object before mutating `.optimus`.

The regular-file test changes only the order: call the real `authorize_capture()` while `.optimus` is a valid directory, then remove the directory and create a regular file, then call the real `append_authorized_audit()` and assert `AUDIT_DIR_UNAVAILABLE`.

The two composed `capture_acpx()` tests use a test-only wrapper around the real `authorize_capture()` because `capture_acpx()` intentionally has one opaque composition boundary:

```python
real_authorize_capture = capture_tool.authorize_capture

def authorize_then_mutate(*args: object, **kwargs: object) -> CaptureLaunch:
    capture = real_authorize_capture(*args, **kwargs)
    mutate_runtime_root_after_authorization()
    return capture

monkeypatch.setattr(capture_tool, "authorize_capture", authorize_then_mutate)
```

The wrapper calls the real authorization implementation with the real keyring fixture and real workspace identity, performs a real filesystem mutation only after authorization returns, and returns the real `CaptureLaunch`. The test then calls the real `capture_acpx()` function. Its real `append_authorized_audit()` and `append_launch_audit_event()` execute against the mutated path; no audit function, `require_workspace_runtime_root()`, `authorize_launch()`, or `LaunchAuditError` is mocked. A spawn sentinel remains installed so any child-start attempt fails the test.

The regular-file variant uses `rmdir()` followed by `write_text()` to model an unsafe final component. The missing-root variant uses `rmdir()` only. Both assert:

- `LaunchAuditError` has code `AUDIT_DIR_UNAVAILABLE`;
- the real audit append did not create or write a replacement directory/file;
- the child-spawn sentinel was not reached.

This seam tests the exact production sequence rather than synthesizing the audit exception. It also deliberately leaves the workspace identity changed after the injected mutation; audit must fail first because the runtime root is unsafe, while the existing post-audit revalidation tests continue to cover `WORKSPACE_IDENTITY_CHANGED` after a successful audit.

## Files and responsibilities

| File | Responsibility in FU-3 |
|---|---|
| `tests/unit/acp/test_launch_approval_cli.py` | Assert POSIX `NO_APPROVAL` for the non-bootstrapping durable-record path while preserving the no-bootstrap invariant. |
| `tests/unit/acp/test_main_wiring.py` | Assert the full agent entrypoint stops at `NO_APPROVAL` on POSIX, before audit/infra/server side effects, and never recreates `.optimus`. |
| `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` | Separate authorization-time mutation from direct audit-time mutation; exercise the real composed `capture_acpx()` sequence through the wrapper seam. |
| `tests/unit/acp/test_launch_audit.py` | Existing direct missing/unsafe runtime-root coverage remains intact. |
| `src/optimus/acp/trusted_paths.py` | No change; FU-1 identity binding is frozen. |
| `src/optimus/acp/launch_gate.py` | No change; durable lookup must continue to return `NO_APPROVAL`. |
| `src/optimus/acp/launch_audit.py` | No change; direct unsafe-root validation must continue to return `AUDIT_DIR_UNAVAILABLE`. |

## Verification strategy

### Baseline evidence already obtained

Run inside WSL2 Ubuntu-24.04 from the Codex worktree:

```text
uv 0.11.31 (x86_64-unknown-linux-gnu)
uv run pytest <the exact five selectors> -q
```

Expected and observed baseline: `5 failed`, with all three capture-rooted failures raising `LaunchGateError: NO_APPROVAL` at `src/optimus/acp/launch_gate.py:670`.

### Interim POSIX loop after test changes

After the test-only changes, run the exact five selectors in WSL2 Ubuntu-24.04 before any final CI or completion claim:

```bash
uv run pytest \
  tests/unit/acp/test_launch_approval_cli.py::TestApprovalTimeRuntimeBootstrap::test_run_does_not_bootstrap_a_missing_runtime_root \
  tests/unit/acp/test_main_wiring.py::test_legacy_approved_workspace_missing_root_fails_without_recreating_it \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_stops_when_real_audit_runtime_root_is_a_regular_file \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_blocks_child_when_composed_audit_fails \
  tests/unit/tools/test_run_plan996_acpx_security_evidence.py::test_capture_acpx_missing_approved_runtime_root_never_spawns_or_recreates_it \
  -q
```

Expected: all five pass, with no skip, xfail, or deselection attributable to FU-3. This WSL run is the fast feedback loop for POSIX `st_ctime_ns` behavior.

Then run the affected module selectors and `uv run ruff check .` in WSL before the full suite. Any failure must be diagnosed from its actual trace; no production change may be introduced merely to make the tests reach a different error code.

### Final official gate

The final acceptance gate remains the clean Ubuntu GitHub Actions job `clean-environment-recheck` in `.github/workflows/guardrails.yml`:

```bash
uv run ruff check .
uv run pytest --cov=optimus --cov-branch --cov-report=term-missing -v
```

The final run must be unskipped with respect to all five FU-3 tests, pass the full suite and coverage threshold, and provide a recorded GitHub Actions run ID and URL. The WSL run is interim evidence; it does not replace this final CI artifact.

## Risks and rejected alternatives

- Removing `st_ctime_ns` or rebaselining the identity after the audit would reopen the FU-1 TOCTOU risk and is rejected.
- Translating `NO_APPROVAL` into `AUDIT_DIR_UNAVAILABLE` would collapse two distinct fail-closed boundaries and is rejected.
- Mocking `append_authorized_audit()` or forcing a synthetic `LaunchAuditError` would not prove the real runtime-root validation and is rejected.
- Preserving parent ctime with platform-specific timestamp manipulation is not reliable on POSIX and would make the test depend on filesystem behavior it is meant to verify; it is rejected.
- Deferring all POSIX verification to GitHub Actions is unnecessary now that WSL2 Ubuntu-24.04 is available, though GitHub Actions remains mandatory for final sign-off.

## Acceptance boundary

FU-3 is ready for implementation planning only after this spec is approved. The implementation plan must name the five tests above, retain the wrapper-based real composition seam, define the POSIX/Windows assertion split without skipping Linux coverage, preserve all frozen source contracts, and require the WSL interim run plus the final clean Ubuntu GitHub Actions run.
