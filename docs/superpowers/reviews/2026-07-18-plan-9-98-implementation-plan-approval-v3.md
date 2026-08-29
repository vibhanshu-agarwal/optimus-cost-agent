# Plan 9.98 Implementation Plan Approval Record — V3 Amendment

**Status:** Approved and frozen on 2026-07-18; implementation remains blocked until this record and
the exact revised plan bytes are committed together in Task 2A.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V2 immutable baseline:** commit `1749747b46aff42d9c487ba62bc1bf38dcf29155`, with the v2 approval
record and SHA-256 `4D8F262343584F77583484752E0086C88C0855CB5B543EFACD9210602FD14BF2`.

**Frozen V3 SHA-256:** `23E4C248D5A447E30B8CB753DF2BE5CBD44BC68D6DB660BF226CD80E19CCCCA0`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-18 after independently verifying the exact revised diff
  against `1749747`, Task 3/4's RED-before-GREEN sequencing and named interfaces, the stale-reference
  sweep, checkbox counts, and every frozen path.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-18.

## Freeze Semantics

This v3 record approves the exact revised plan bytes whose digest appears above. It supplements —
and does not alter, replace, or invalidate — the v1/v2 records or their immutable baseline commits.

The approved revision corrects deferred-test sequencing in the incomplete Task 3 and Task 4 work:
Task 2A requires the construction/CLI and parser/manifest RED tests to fail before their respective
production behavior is introduced. It also pins `_build_agent_invocation(...)` as the Task 3
interface, preserving the pre-existing final-state and elevated-evidence rulings.

After the Task 2A amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v3 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before implementation may continue.

Approval authorizes execution only in the existing approved worktree and branch, only after the
revised plan and this record are committed together. It does not authorize changes to Plan 9.96's
frozen files or the Plan 9.96 follow-up files excluded by Plan 9.98.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 2A checkbox is ticked:

```text
23E4C248D5A447E30B8CB753DF2BE5CBD44BC68D6DB660BF226CD80E19CCCCA0
```
