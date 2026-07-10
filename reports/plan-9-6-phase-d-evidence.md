# Plan 9.6 Phase D evidence

**Date:** 2026-07-10
**Checkout:** `optimus-cost-agent-wt-cursor` @ `8c0a80097ce11ff1ebe87ee7efe70dc3e0928253` (main)
**Depends on:** [Phase A evidence](plan-9-6-phase-a-evidence.md), [Phase B evidence](plan-9-6-phase-b-evidence.md)

## Gateway provenance (before D1/D2)

Killed prior listener on `127.0.0.1:8765` (pid **36952**) and restarted from current checkout:

```
optimus-agent: starting local gateway (pid 68476); logging to reports/local-gateway.log
gateway_pid 68476
```

Gateway pid at D2 completion: **68476** (unchanged across D1/D2 re-runs).

## Fixture drift pattern (review finding)

Three instances of test/operator fixtures shaped to pre-#36 protocol masking production drift:

1. GAP1 — approve metadata echo in client responses
2. B1 — `params.metadata.runId` in integration tests
3. **D2** — `test_verify_live_agent_cli.py` fabricated `sessionUpdate: tool_call_update` while the
   live agent emits `tool_call` only; 6/6 CLI tests green did not prove trajectory extraction worked

## D1 — `e2e` spawned agent (claim row 6)

**First run (ship-blocker):** `KeyError: 'metadata'` at `operator_verify.py:443` —
`run_operator_live_session` still read `permission_request["params"]["metadata"]["runId"]`
(pre-#36 shape). Same drift class as B1 integration-test fix; production operator path missed in #36.

**Fix:** Align `operator_verify.py` with post-#36 ACP wire shapes:

| Area | Before | After |
|------|--------|-------|
| Permission `runId` | `params.metadata.runId` | `params._meta.runId` |
| Plan text for verify | `params.metadata.planText` | `latest_plan_text_from_transcript()` (`entries`) |
| Approve response | metadata echo (`approvalId`, `planHash`) | GAP1: `optionId: approve` only |
| Plan transcript parse | `update.content[]` blocks | `update.entries[].content` (+ legacy fallback) |
| Plan hash from transcript | `params.metadata.planHash` | `params.options[0].metadata.planHash` |

**Second run:** **1 passed**, exit **0** (6.40s).

```
tests/e2e/acp/test_spawned_agent_live.py::test_spawned_acp_agent_live_docstring_turn PASSED
```

**D1 trajectory note:** `test_spawned_agent_live.py` does not call `tool_trajectory_from_transcript` or
assert tool names — it validates file mutation, docstring content, cost cap, and `end_turn`. No
fixture drift there.

## Transcript diff (D1 positive conformance evidence)

Baseline (committed in PR): `reports/plan-9-6-e2e-acp-transcript.pre-d1-run.json` (pre-#36 shapes on
`main`). Regenerated artifact: `reports/plan-9-6-e2e-acp-transcript.json`.

| Shape | Pre-#36 baseline | Post-D1 (conformant) |
|-------|------------------|----------------------|
| Plan update | `update.content[]` text blocks | `update.entries[]` with `content`/`priority`/`status` |
| Permission request | `params.metadata` (`planHash`, `planText`, `runId`) | `params._meta` (`planHash`, `runId`) + nested `params.toolCall` |
| Approve response (outbound) | `result.metadata` echo (`approvalId`, `planHash`) | `result.outcome` only (GAP1) |
| Tool call event | `sessionUpdate: tool_call_update` + nested `toolCall` | `sessionUpdate: tool_call` + flattened `title`/`toolCallId` |
| Streaming | absent | `sessionUpdate: agent_message_chunk` present |

Parsed live-agent transcript update types after D2: `{plan: 2, tool_call: 3, agent_message_chunk: 1}`
— zero `tool_call_update` events.

## D2 — `verify_live_agent.py` (claim row 7)

**Workspace:** default scratch dir `reports/.verify-live-agent-workspace` (not repo checkout).

### Ship-blocker 1 — scratch workspace bootstrap order

**First run:** preflight `workspace writable FAIL` — directory did not exist yet;
`ensure_verify_workspace()` ran after preflight in `main()`.

**Fix:** Call `ensure_verify_workspace(workspace)` before `collect_preflight_checks()`.

### Ship-blocker 2 — tool trajectory filter (review catch)

**Second run:** exit **0** but stdout showed `tool_trajectory: (none)` despite three `tool_call`
events in `reports/plan-9-6-live-agent-transcript.json`. Root cause: `tool_trajectory_from_transcript`
filtered on `sessionUpdate == "tool_call_update"` only; post-#36 adapter emits `tool_call`. The
`update.title` extraction fix was inside a branch that never matched live output. Exit 0 was a false
green — nothing asserts non-empty trajectory.

**Fix:**

- Filter: `sessionUpdate in {"tool_call", "tool_call_update"}`; keep title fallback chain.
- Tests: `test_tool_trajectory_from_transcript_accepts_post_36_tool_call_shape` + CLI success test
  fixture uses `tool_call` messages and asserts `tool_trajectory: file_reader, write_file, legacy_reader`.

**Third run (authoritative for row 7):** exit **0**.

```
Check                Status  Detail
gateway credentials  PASS    present
redis url            PASS    redis://127.0.0.1:6379/0
redis connectivity   PASS    PING ok
redis timeseries     PASS    TS.ADD ok
gateway auth         PASS    auth probe accepted
workspace writable   PASS    .../reports/.verify-live-agent-workspace

model: claude-haiku
prompt_version: AGENT_PLANNER_PROMPT_VERSION:2026-07-12
plan_hash: 3e26854b69fa20c05d4c33643f1cac78d7e5e145e459a1caccee85125a99866d
approval_id: (none)
tool_trajectory: file_reader, file_reader, write_file
files_changed: example.py
total_cost_usd: 0.000973
stop_reason: end_turn
PASS: Optimus live agent verification completed.
```

Transcript: `reports/plan-9-6-live-agent-transcript.json` (regenerated).

## Code changes

- `src/optimus/acp/operator_verify.py` — post-#36 shape alignment, scratch workspace bootstrap order,
  `tool_call` trajectory filter
- `tests/integration/release/test_verify_live_agent_cli.py` — post-#36 trajectory fixtures + assertions

## Verification commands (re-run)

```powershell
# D1
python -c "
import os, subprocess, sys
from pathlib import Path
from optimus.acp.__main__ import _project_root
from optimus.acp.local_infra import apply_local_defaults, strip_local_provider_keys
root = Path('.').resolve()
env = dict(os.environ)
env.update(strip_local_provider_keys(apply_local_defaults(env, project_root=_project_root())))
raise SystemExit(subprocess.run([sys.executable, '-m', 'pytest', 'tests/e2e/acp/test_spawned_agent_live.py', '-m', 'e2e', '-v'], env=env, cwd=root).returncode)
"

# D2 (default scratch workspace — do not pass --workspace-root)
python tools/verify_live_agent.py

# CLI unit coverage (trajectory shape)
pytest tests/integration/release/test_verify_live_agent_cli.py -q
```
