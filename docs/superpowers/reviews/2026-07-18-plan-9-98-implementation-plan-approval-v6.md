# Plan 9.98 Implementation Plan Approval Record — V6 Amendment

**Status:** Approved and frozen on 2026-07-18; implementation remains blocked until this record and
the exact revised plan bytes are committed together in Task 2D.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V5 immutable baseline:** commit `5f7dcb379e1a76a0950eccd0f3ba5c99cddf4c64`, with the v5
approval record and SHA-256 `E38F4985E3D213547123A62EC663881F9E5B15704C460397E17F6F94179CC8E2`.

**Frozen V6 SHA-256:** `D6D3E563655D8BDDB1FA852995DD9465DB8169273E82916C7AE4158C0AEF605B`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-18 after independently verifying the exact revised diff
  against `5f7dcb3`, the exact 38/49/87 checkbox count, all frozen paths and Plan 9.96 core files,
  every v1/v2/v3/v4/v5 approval record, the six Task 3A RED-before-GREEN environment-boundary tests,
  additive audit semantics preserving the exact five-name `agent_child` claim, the mandatory real
  session regression gate, nine-commit/closure accounting, and the separately owned Plan 9.99 URI
  canonicalization deferral.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-18 after the reviewer-agent's exact-byte approval.

## Freeze Semantics

This v6 record approves the exact revised plan bytes whose digest appears above. It supplements —
and does not alter, replace, or invalidate — the v1/v2/v3/v4/v5 records or their immutable baseline
commits.

The approved revision corrects Plan 9.98's two-tier launch boundary without changing Plan 9.96's
core digest/default semantics. The evidence helper retains its post-default effective agent mapping
as the source of the outer audit's exact five-name `agent_child` claim and the run-bound Redis URL,
but introduces a distinct system-only ACPX client environment sourced from the sanctioned one-time
snapshot. The outer audit adds an `acpx_client` classified-setting-name role without removing or
reinterpreting `agent_child`. Driven sessions fail closed before audit or spawn when any classified
launch setting is inherited, so the inner `optimus-agent` resolves its own defaults/keyring secret
from the same clean pre-default shape the operator approved. Six RED-before-GREEN tests and a real
controlled session must prove the former `SNAPSHOT_MISMATCH` is gone.

The distinct URI-userinfo digest/display conformance finding is not implemented or waived by this
amendment. Its named owner is Plan 9.99, which requires separate reviewed security-contract and
implementation work before Plan 9.96 may close.

After the Task 2D amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v6 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before implementation may continue.

Approval authorizes execution only in the existing approved worktree and branch, only after the
revised plan and this record are committed together. It does not authorize changes to Plan 9.96's
frozen files, Plan 9.96 core digest/default files, or the Plan 9.96 follow-up files excluded by Plan
9.98.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is genuinely on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 2D checkbox is ticked:

```text
D6D3E563655D8BDDB1FA852995DD9465DB8169273E82916C7AE4158C0AEF605B
```
