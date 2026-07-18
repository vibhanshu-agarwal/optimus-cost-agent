# Plan 9.98 Implementation Plan Approval Record — V2 Amendment

**Status:** Approved and frozen on 2026-07-18; implementation remains blocked until this record and
the exact revised plan bytes are committed together in Task 0A.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V1 immutable baseline:** commit `424940ebc62155cfc2422da008efe89457d9ee37`, with the original
approval record and pristine SHA-256 `3C2C2F0D4521C251748886BB3810BEF1191F6CF75A759FDDA7C55FBA16F7AA0A`.

**Frozen V2 SHA-256:** `4D8F262343584F77583484752E0086C88C0855CB5B543EFACD9210602FD14BF2`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-18 after independently verifying the exact revised diff
  against `424940e`, the source-backed run-scoped comparison-record oracle, the frozen Plan 9.96
  Task 9 wording, checkbox counts, and every frozen path.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-18.

## Freeze Semantics

This v2 record approves the exact revised plan bytes whose digest appears above. It supplements —
and does not alter, replace, or invalidate — the v1 record and the immutable v1 baseline commit.

The approved revision changes the elevated-evidence discriminator from non-empty correlation-tag
presence to the run-scoped count of `launch_authorization_comparison` records: zero for ordinary and
exactly one for elevated. `correlation_tags` remains zero-or-more allowlisted/sanitized metadata and
may honestly be empty for a keyring/`.env.gateway`-resolved credential.

After the Task 0A amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v2 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before implementation may continue.

Approval authorizes execution only in the existing approved worktree and branch, only after the
revised plan and this record are committed together. It does not authorize changes to Plan 9.96's
frozen files or the Plan 9.96 follow-up files excluded by Plan 9.98.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 0A checkbox is ticked:

```text
4D8F262343584F77583484752E0086C88C0855CB5B543EFACD9210602FD14BF2
```
