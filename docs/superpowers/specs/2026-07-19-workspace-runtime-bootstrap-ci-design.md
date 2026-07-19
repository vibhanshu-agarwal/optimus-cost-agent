# Corrective Design: Approval-Time Workspace Runtime Bootstrap

## Purpose

Correct the Linux-only self-invalidation discovered after Plan 9.98-FU-1 was
pushed to PR #60. The strengthened `WorkspaceIdentity` intentionally binds a
workspace directory's `st_ctime_ns` so a delete-and-recreate cannot evade a
device/inode comparison through inode reuse. On a fresh workspace, however,
the required pre-spawn launch audit creates the workspace's direct
`.optimus/` child after authorization captured that identity and before
revalidation runs. On POSIX, that child creation changes the parent
workspace's `st_ctime_ns`; the system therefore rejects its own audit write
as `WORKSPACE_IDENTITY_CHANGED`.

This specification builds on the committed Plan 9.98-FU-1 work in PR #60. It
does not weaken its lexical-path, resolved-target, device/inode, or
change-time identity binding, and does not amend frozen Plan 9.96 or Plan
9.98 documents. Its eventual roadmap/plan identifier is intentionally left
for the operator to assign.

## Goals

- Preserve Plan 9.98-FU-1's complete, fail-closed workspace identity
  revalidation, including delete-and-recreate detection on inode-reusing
  POSIX filesystems.
- Ensure that the workspace runtime directory exists before the identity used
  for an approval is captured, so ordinary audit, debug, and gateway writes
  beneath that directory do not create a new direct child of the workspace.
- Keep `optimus-agent` and the evidence capture tool free of filesystem writes
  before authorization. An unapproved launch must not create `.optimus/`.
- Make the bootstrap an explicit, narrowly bounded consequence of the
  operator's TTY-gated `optimus-trust approve` action for both durable and
  one-shot approvals.
- Fail closed if the bootstrap directory cannot be safely created or
  validated, and never write a durable or one-shot approval record after such
  a failure.
- Prove the complete fresh-workspace Linux lifecycle: approve, audit, and
  revalidate succeed; a separately introduced direct workspace child after
  approval still causes revalidation to fail.

## Non-goals

- Do not remove `st_ctime_ns` from `WorkspaceIdentity`, rebaseline identity
  after auditing, or otherwise create a post-authorization detection window.
- Do not move all runtime state to the external approval runtime root. That
  broader alternative would require a Plan 9.96 operator-path and audit-log
  architecture change.
- Do not alter approval-record cryptography, security-snapshot comparison,
  credential resolution, registry policy, manifests, or real ACPX evidence.
- Do not create runtime files, audit records, debug traces, gateway logs,
  network connections, child processes, or credentials during bootstrap.
- Do not make `inspect`, `revoke`, ordinary `optimus-agent` launch attempts,
  or evidence verification implicitly initialize a workspace.

## Recommended Architecture

### Approval-time bootstrap boundary

Add one approval-only bootstrap immediately after `_cmd_approve()` has
successfully completed `_require_tty()` and before `_resolve_candidate()` can
call `resolve_workspace_identity()`. Both durable and one-shot approval modes
pass through this exact point before their later mode-specific branch, so they
receive the same identity baseline.

The bootstrap must obtain its target through the existing authorized operator
path resolution, using the resolved workspace root and its computed
`runtime_root` (`resolved_workspace / ".optimus"`). It must not concatenate a
raw lexical workspace argument into a write path. It may read the environment
only through the approval flow's single captured launch-environment snapshot;
the implementation must not introduce a second live `os.environ` read merely
to initialize the directory.

The operation creates exactly the runtime directory when absent. Before
returning success it verifies that the resulting object is a directory and is
not a symlink or other redirected filesystem object. A creation error,
non-directory, symlink, or validation failure is fatal and produces a
value-safe error. The approval command then stops before candidate display,
approval-record construction, approval-record persistence, or one-shot spawn.

This is not an exception to the launch path's "no side effects before exact
authorization" rule: `optimus-agent` continues to resolve, authorize, audit,
and revalidate in its existing order, with no bootstrap capability. The write
is instead a deliberately limited part of an interactive, TTY-gated operator
approval ceremony. Its only result is an empty managed directory at the
already-resolved workspace target.

### Identity and launch lifecycle

The approval command creates/validates `.optimus/` first and only then captures
the `WorkspaceIdentity` included in the approval record. A later successful
launch appends `launch-audit.ndjson` inside that existing directory. Such a
write can update `.optimus/` metadata but does not create a new direct entry in
the workspace directory, so the workspace identity captured at approval still
matches at revalidation.

`append_launch_audit_event()` must no longer call `mkdir()` as a fallback. It
must require an already-initialized, safe runtime directory and fail closed
when that precondition is absent. This makes the no-launch-initializer rule a
property of the shared audit primitive, rather than a convention each caller
must remember to preserve. Local gateway and debug-trace writers may continue
to use that same already-initialized directory only after their existing
authorization/revalidation gates; they must not become alternative
pre-authorization bootstrap paths.

For old or partially initialized approvals, launch code must remain read-only
before authorization. If an authorized launch finds that the required runtime
directory is absent, redirected, or unsafe, it fails closed with remediation
to re-run `optimus-trust approve`; it must not recreate the directory in the
launch path. This deliberate migration behavior ensures that legacy approval
records cannot bypass the new lifecycle by causing a first-write bootstrap
during launch.

`optimus-trust inspect` remains digest-only and read-only. An approved but
never-launched workspace has an empty `.optimus/` directory and can still be
inspected normally; no audit record need exist for inspection to work.

### Rejected alternatives

Rebaselining identity after audit would leave a window between the original
capture and replacement baseline in which a workspace retarget or replacement
could escape detection. Removing the change-time token would restore the
inode-reuse gap that Plan 9.98-FU-1 was specifically approved to close.

Moving only `launch-audit.ndjson` outside the workspace is also rejected: the
same first-child ctime collision would recur when debug tracing or local
gateway logging first creates `.optimus/`. Moving all runtime state externally
could be valid future architecture, but is wider than this corrective change.

## Required Proofs

- A genuine failing Linux/POSIX regression test starts from a fresh workspace,
  completes the official approval path, performs the required audit append,
  and proves revalidation succeeds without suppressing the change-time check.
- A second failing test adds an unrelated direct child to the approved
  workspace after authorization and proves `WORKSPACE_IDENTITY_CHANGED` still
  stops the launch before spawn.
- A failing test proves an unapproved `optimus-agent` launch never creates
  `.optimus/`.
- Bootstrap-failure tests cover at least directory creation failure and an
  unsafe pre-existing `.optimus` object; neither may write an approval record
  or launch a one-shot target.
- A test proves the bootstrap uses the resolved operator-path runtime root,
  rather than a lexical path that could be redirected through a symlink.
- Existing `inspect` behavior is covered for an approved, not-yet-launched
  workspace, confirming that an empty bootstrap directory is not treated as a
  missing audit artifact.

## Files Expected to Change

| File | Responsibility |
|---|---|
| `src/optimus/acp/launch_approval_cli.py` | Capture the approval snapshot once, resolve the trusted runtime path, perform the approval-only safe bootstrap, then resolve the candidate from that same prepared context. |
| `src/optimus/acp/operator_paths.py` and/or a narrowly scoped runtime-path helper | Provide one reusable, resolved-path-safe validation/bootstrap primitive without creating a launch-path initializer. |
| `src/optimus/acp/launch_audit.py` | Require an existing safe runtime directory; remove its launch-side `mkdir()` fallback and retain fatal value-safe audit errors. |
| `src/optimus/acp/__main__.py` | Add a read-only, fail-closed check for legacy/missing/unsafe runtime roots before audit append; do not bootstrap. |
| `tools/run_plan996_acpx_security_evidence.py` | Apply the same read-only launch-side runtime-root check before audit/capture, if it shares the affected audit lifecycle. |
| `tests/unit/acp/test_launch_audit.py` | Verify that audit append rejects an absent or unsafe runtime root rather than initializing it. |
| `tests/unit/acp/test_launch_approval_cli.py` | RED/GREEN coverage for durable and one-shot bootstrap ordering, failure, and no-record behavior. |
| `tests/unit/acp/test_trusted_paths.py` or a focused new unit module | Safe resolved-root and symlink/non-directory validation coverage. |
| `tests/unit/acp/test_main_wiring.py` | Unapproved no-write and approved fresh-workspace audit-to-revalidation lifecycle coverage. |
| `tests/unit/tools/test_run_plan996_acpx_security_evidence.py` | Evidence-tool parity for the read-only launch-side behavior. |

## Risks and Mitigations

The bootstrap deliberately changes `approve` from a pure record-authoring
operation to one that can create a single empty workspace directory. It is
bounded by the operator's TTY gate, applies identically to durable and
one-shot approvals, happens before any approval record exists, creates no
file, approval record, network connection, child process, or effect outside
that resolved workspace directory, and fails closed on error. Tests must prove
those boundaries; they are not informal assurances.

An existing durable approval created before this lifecycle may not have an
initialized runtime directory. Requiring explicit re-approval rather than
repairing it during launch is intentionally conservative and preserves the
launch-side no-write boundary.

`st_ctime_ns` is inode metadata-change time on POSIX and creation time on
Windows. The self-invalidation mechanism is therefore principally a POSIX
fresh-workspace issue, but the bootstrap is harmless and deterministic on
both platforms. The Linux CI workflow remains the governing proof for this
regression.

The directory check must be robust against symlink and object-type surprises.
If a race-free primitive cannot be expressed with the existing trusted-path
facilities, implementation must stop for a reviewed plan amendment rather
than quietly following a redirected runtime path.
