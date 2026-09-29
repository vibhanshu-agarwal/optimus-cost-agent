# Plan 9.98 Implementation Plan Approval Record — V5 Amendment

**Status:** Approved and frozen on 2026-07-18; implementation remains blocked until this record and
the exact revised plan bytes are committed together in Task 2C.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V4 immutable baseline:** commit `3e04c29fe09b4ec038fa851e24ac187ea9071ba2`, with the v4
approval record and SHA-256 `8ECFD4734BC5BC6EC152BDE1C63ADB563B32DC6A2CE16967A64BB5421937A96C`.

**Frozen V5 SHA-256:** `E38F4985E3D213547123A62EC663881F9E5B15704C460397E17F6F94179CC8E2`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-18 after independently verifying the exact revised diff
  against `3e04c29`, all six affected `final_agent_state` locations plus the downstream E2E wording,
  the fixed-fixture-only three-predicate boundary, stale-reference and checkbox accounting, and every
  frozen path and v1/v2/v3/v4 approval record.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-18.

## Freeze Semantics

This v5 record approves the exact revised plan bytes whose digest appears above. It supplements —
and does not alter, replace, or invalidate — the v1/v2/v3/v4 records or their immutable baseline
commits.

The approved revision resolves an internal Plan 9.98 wording conflict after Task 1 established that
there is no distinct persisted/transcribed final-state signal for this fixture. It permits the
manifest to set `final_agent_state` to `"COMPLETED"` only when all three independently observable,
already-captured facts hold on this plan's fixed normal ACP path: `stop_reason == "end_turn"`,
`tool_call_count > 0`, and `"write_file" in tool_names`. When that conjunction does not hold, the
field is omitted rather than fabricated. This is not a general `end_turn` rule, does not apply to a
request with `completion_condition` or a different fixture, and does not amend or reinterpret frozen
Plan 9.96.

After the Task 2C amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v5 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before implementation may continue.

Approval authorizes execution only in the existing approved worktree and branch, only after the
revised plan and this record are committed together. It does not authorize changes to Plan 9.96's
frozen files or the Plan 9.96 follow-up files excluded by Plan 9.98.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 2C checkbox is ticked:

```text
E38F4985E3D213547123A62EC663881F9E5B15704C460397E17F6F94179CC8E2
```
