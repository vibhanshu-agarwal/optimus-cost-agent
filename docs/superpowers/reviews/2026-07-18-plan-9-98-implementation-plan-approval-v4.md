# Plan 9.98 Implementation Plan Approval Record — V4 Amendment

**Status:** Approved and frozen on 2026-07-18; implementation remains blocked until this record and
the exact revised plan bytes are committed together in Task 2B.

**Implementation plan:** `docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md`

**V3 immutable baseline:** commit `4e009380c54b56ec8f93bd8f9e06ae61de193864`, with the v3
approval record and SHA-256 `23E4C248D5A447E30B8CB753DF2BE5CBD44BC68D6DB660BF226CD80E19CCCCA0`.

**Frozen V4 SHA-256:** `8ECFD4734BC5BC6EC152BDE1C63ADB563B32DC6A2CE16967A64BB5421937A96C`

## Approvals

- **Reviewer-agent:** Approved on 2026-07-18 after independently verifying the exact revised diff
  against `4e00938`, the single-collector Redis design, parser-before-collector ordering, sanctioned
  Redis URL path, stale-reference sweep, checkbox/commit accounting, and every frozen path.
- **Operator:** Vibhanshu (`vibhanshu-agarwal`) explicitly approved these exact revised plan bytes on
  2026-07-18.

## Freeze Semantics

This v4 record approves the exact revised plan bytes whose digest appears above. It supplements —
and does not alter, replace, or invalidate — the v1/v2/v3 records or their immutable baseline
commits.

The approved revision corrects Plan 9.98's cost-evidence assumption after a real ACP session showed
that ACP stdout has no cost/usage surface while the same run's real, run-ID-keyed Redis
`AgentPlanRecord.cost_usd` is populated. It generalizes the already-designed outside-transcript
collector: after the parser derives `run_id` from session ID plus prompt request ID, the collector
reads the sanctioned Redis source once, reduces it to content-free `total_cost_usd`, and writes the
result through the existing sanitizer, digest, and joined-scan pipeline. It must obtain
`OPTIMUS_REDIS_URL` only from authorized `CaptureLaunch.agent_environ`, never a new ambient
environment read. This does not amend or reinterpret frozen Plan 9.96.

After the Task 2B amendment commit lands, subsequent checkbox ticks in the working tree do not
invalidate this v4 snapshot. Any further substantive plan text change requires fresh reviewer-agent
and operator approval plus a new digest-pinned amendment record before implementation may continue.

Approval authorizes execution only in the existing approved worktree and branch, only after the
revised plan and this record are committed together. It does not authorize changes to Plan 9.96's
frozen files or the Plan 9.96 follow-up files excluded by Plan 9.98.

## Mechanical Verification

Run from the repository root in a terminal where `uv` is on `PATH`:

```powershell
uv run python -c "from pathlib import Path; import hashlib; p=Path('docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md'); print(hashlib.sha256(p.read_bytes()).hexdigest().upper())"
```

Expected exact output, before any Task 2B checkbox is ticked:

```text
8ECFD4734BC5BC6EC152BDE1C63ADB563B32DC6A2CE16967A64BB5421937A96C
```
