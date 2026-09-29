# Plan 9.98-FU-1: Workspace Identity and Linux CI Corrective Design

## Purpose

Correct the Linux CI failures on PR #60 without weakening the Plan 9.96 launch-trust boundary. The primary defect is that workspace revalidation currently remembers only the resolved target path. A symlink used at authorization can later be retargeted without changing that stored target path, so the revalidation check misses the change. A delete-and-recreate can also evade a device/inode-only comparison if the filesystem reuses the inode.

This is a follow-up plan on PR #60. It does not amend or edit the frozen Plan 9.96 or Plan 9.98 documents.

## Goals

- Bind a workspace identity to the original absolute lexical input path and the resolved target identity.
- Detect a post-authorization symlink retarget, workspace relocation, and delete/recreate replacement before spawn.
- Preserve the current fail-closed `WORKSPACE_IDENTITY_CHANGED` contract.
- Make the default Linux CI suite independent of a host keyring, POSIX file-creation defaults, and Python locale coercion.
- Keep all real Redis, Gateway, and ACPX tests deselected by the established default marker expression; this correction adds no CI service dependency.

## Non-goals

- Do not add Redis, Gateway credentials, ACPX, or a keyring backend to CI.
- Do not change Plan 9.96/9.98 approval semantics, registry policy, credential resolution, manifests, or evidence artifacts beyond the workspace-identity correction required for safe launch.
- Do not retain OS directory handles or introduce platform-specific open-handle lifetime management.
- Do not alter the existing real-evidence artifacts or rerun paid/live evidence as part of this corrective plan.

## Recommended Architecture

`WorkspaceIdentity` will store a lexical absolute workspace path in addition to its existing resolved canonical path, filesystem device/inode, Git metadata, and digest. Identity resolution will capture the lexical path before symlink resolution, resolve that same path to obtain the target, and record the target directory's `st_ctime_ns` as a filesystem change token.

The identity digest will bind the lexical path, canonical target path, device, inode, change-time token, and existing Git fields. Revalidation will reconstruct a fresh identity from `identity.lexical_path`, rather than statting `identity.canonical_path` directly, and compare the complete digest. Thus a retargeted symlink changes the resolved target; a replacement at the same path changes the inode or change-time token; and either case fails before spawn with `WORKSPACE_IDENTITY_CHANGED`.

The extra identity fields are deliberately not persisted as separate approval-record fields. Existing record serialization stores the workspace digest only. `launch_approvals._deserialize_approval_record()` must nevertheless construct the expanded `WorkspaceIdentity` with explicit inert placeholder values for the lexical path and change-time token, because it reconstructs an identity object around the stored digest. The strengthened digest makes old durable records unreachable for a new candidate and therefore requires re-approval, which is the safe behavior.

## Error and CLI Behavior

`TrustedPathError` will become a regular exception class, following `ApprovalError`, because Python's exception machinery assigns traceback metadata during propagation. It will retain the same `code`, `detail`, and string rendering.

`optimus-trust inspect` will resolve workspace identity before constructing the approval store. A nonexistent workspace therefore returns the intended trusted-path error without accessing an unavailable system keyring. This plan does not add a fallback keyring backend.

## Test Isolation and Portability

- Tests that create `.env.gateway` for real POSIX permission validation will explicitly set owner-only mode (`0o600`).
- The test that only proves permission-validator invocation will replace the validator with a recorder/no-op; it will not invoke the real permission check after recording the call.
- Evidence-tool `main()` tests will patch the module's imported `keyring` object with their existing in-memory `FakeKeyring` whenever they drive the manifest-writing path. Production continues to use the OS keyring.
- The ACPX client-environment test will inspect the `env` argument passed to `subprocess.Popen`, not the child Python process's reconstructed `os.environ`; Linux can add `LC_CTYPE` after startup even when it was not supplied to `Popen`.
- The case-normalization test will be explicitly Windows-only. It describes Windows filesystem semantics and must not attempt a case-variant path lookup on Linux.

## Files Expected to Change

| File | Responsibility |
|---|---|
| `src/optimus/acp/trusted_paths.py` | Strengthened lexical/resolved workspace identity and non-frozen trusted-path exception. |
| `src/optimus/acp/launch_approvals.py` | Supply inert lexical-path/change-time placeholders while deserializing the digest-only durable approval record. |
| `src/optimus/acp/launch_approval_cli.py` | Resolve inspect workspace identity before opening the keyring-backed store. |
| `tests/unit/acp/test_trusted_paths.py` | Linux-safe symlink, replacement, unchanged, and Windows-only case tests. |
| `tests/integration/acp/test_launch_trust_flow.py` | Real authorization-to-revalidation replacement regression. |
| `tests/unit/acp/test_main_wiring.py` | Fail-closed relocation-before-side-effect regression. |
| `tests/unit/acp/test_launch_approval_cli.py` | Headless inspect and permission-invocation isolation. |
| `tests/unit/acp/test_launch_gate.py` | Private `.env.gateway` fixtures for credential TOCTOU/digest tests. |
| `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` | Fake-keyring `main()` isolation and direct spawned-environment assertion. |

## Acceptance Criteria

1. The exact GitHub Actions default pytest command completes with zero failures on Linux and continues to deselect live-dependency markers.
2. A workspace symlink repointed after authorization fails revalidation with `WORKSPACE_IDENTITY_CHANGED`.
3. A workspace deleted and recreated after authorization fails revalidation, including on inode-reusing filesystems.
4. Revalidation of an unchanged ordinary workspace succeeds.
5. A nonexistent `optimus-trust inspect` workspace fails cleanly without initializing a real keyring backend.
6. Unit tests do not depend on an installed keyring backend or Redis service.
7. The ACPX client process receives exactly the allowed bootstrap environment passed to `Popen`, with no classified `OPTIMUS_*` setting.
8. Existing digest-only durable approval records deserialize without a `TypeError`; their inert placeholder fields are never used for revalidation.
9. Focused tests, the full default suite with coverage, and full-repository Ruff pass; no frozen plan, approval record, `uv.lock`, or `.claude/` file is staged.

## Risks and Mitigations

Adding the change-time token makes workspace replacement detection robust against inode reuse, but a directory metadata change can invalidate a durable approval. This is an intentional fail-closed consequence for a security-bound workspace identity and is disclosed to operators as a re-approval requirement. `st_ctime_ns` represents inode metadata-change time on POSIX and creation time on Windows; in both cases a directory replacement yields a distinct value for the identity comparison.

The corrective plan must use RED-first tests for every production change and must keep the PR's existing real-dependency evidence intact. The final PR gate is GitHub Actions on Linux, not a Windows-only local test run.
