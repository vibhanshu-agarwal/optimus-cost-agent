# Plan 9.8 - Task-Aware Workspace Context Evidence

**Date:** 2026-07-11
**OS:** Windows 11 Pro (10.0.26200)
**Branch:** `agent/cursor/plan-9-8-task-aware-workspace-context`
**Commit (implementation HEAD):** `6643cf8a3d963b281275278e0699328e60478541`
**Zed:** 1.10.2+stable.322 (`adc60ccf12e199b8828bad3abb2591e147034734`)
**Model (operator / acpx live):** `claude-haiku`
**Executable:** `C:\Users\pc\.local\bin\optimus-agent.exe` (uv editable PATH install)
**Source checkout:** `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor`
**PROVENANCE (operator):** `git_sha=6643cf8`, `optimus_acp_file=...\wt-cursor\src\optimus\acp\debug_trace.py`, keychain credentials (no `OPTIMUS_*` / provider keys in shell)

**Plan:** [`docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md`](../docs/superpowers/plans/2026-07-10-plan-9-8-task-aware-workspace-context.md)

---

## Summary

Plan 9.8's deterministic contract and live exact-path mutation gate are proven. Ambiguous
references fail closed before Gateway with a corrective message. Exact-path works end-to-end in
**Zed 1.10.2**. Ambiguous refusal is correct on the wire and was briefly visible in Zed before a
**Zed client panic** (tracked as `P9.8-FU-5`). Independent client **acpx 0.12.0** is the primary
automated ACP evidence tier; a hand-rolled subprocess harness is superseded (`P9.8-FU-6`).

This does **not** claim mutation tasks generally succeed, multi-turn replanning, or Plan 11
intelligent selection.

---

## Evidence tiers (policy)

| Tier | Tool | Role in this report |
|------|------|---------------------|
| Unit / runner | `pytest` + `FakeGatewayClient` | Business-logic contract (allowed) |
| Automated ACP (primary) | **`acpx@latest`** (third-party) | Pre-GUI protocol conformance |
| Operator GUI (required) | **Zed 1.10.2** | Steps 6-7 user-client gate |
| Superseded | `tools/run_plan98_live_evidence.py` | Early ACP probe only - **not** co-equal evidence; retire via `P9.8-FU-6` |

Project-authored ACP harnesses that share assumptions with `optimus-agent` are not treated as
independent conformance proof (they can pass scenarios that still crash real Zed).

---

## Deterministic gates (Steps 1-4)

Independently reviewed and approved before live work.

### Step 1 - Narrow suite

```text
uv sync --all-extras
uv run pytest tests/unit/agent/test_workspace_context.py tests/unit/agent/test_runner.py \
  tests/unit/acp/test_main_debug_trace.py tests/unit/acp/test_bootstrap.py \
  tests/unit/acp/test_spec_protocol.py -v
```

**Result:** **65 passed**, exit 0.

### Step 2 - Default suite, coverage, Ruff

| Gate | Command | Result |
|------|---------|--------|
| Default suite | `uv run pytest -q` | **682 passed**, **20 deselected**, exit 0 |
| Coverage | `uv run pytest --cov=src/optimus --cov-report=term-missing --cov-fail-under=80 -q` | **84.86%** (>=80%) |
| Ruff | `python -m ruff check .` | clean |
| HEAD | `git rev-parse HEAD` | `6643cf8a3d963b281275278e0699328e60478541` |

Live tiers deselected by default (stated, not implied as run).

### Step 3 - Exact-path inclusion under filler pressure

Named packing regression (`-vv`); probe confirmed (no source pasted):

| Field | Value |
|-------|--------|
| Task reference | exact relative path to small target |
| Cap | `max_total_bytes == used_bytes == 600` (test fixture budget) |
| Target | header + complete sentinel present |
| Filler | header present; content truncated (full filler body not included) |
| `omitted_paths` | empty (truncation-in-place path) |
| `blocking_stop_reason` | `None` |

### Step 4 - Ambiguous basename, zero Gateway cost

Runner + ACP protocol tests by node ID. Stronger probe: `FakeGatewayClient` that raises if
`create_response` is called.

| Field | Value |
|-------|--------|
| Candidates | sorted in `output_text` |
| `gateway.calls` | `[]` |
| `total_cost_usd` | `0` |
| `mutation_count` | `0` |
| ACP `stopReason` | `refusal` |
| Internal | `AMBIGUOUS_WORKSPACE_REFERENCE` |
| Message | not `"Turn completed."` |

---

## Step 5 - Operator PATH install

```powershell
uv tool install --editable . --reinstall
where.exe optimus-agent
optimus-agent --workspace-root . --check-config --strict --debug-trace
```

| Requirement | Evidence |
|-------------|---------|
| Fresh PATH binary | `C:\Users\pc\.local\bin\optimus-agent.exe` first |
| No shell `OPTIMUS_*` | empty |
| Config | exit 0, `Optimus ACP agent configuration OK.` |
| PROVENANCE | `git_sha=6643cf8`, editable wt-cursor `optimus_acp_file`, uv-tools `sys_executable` |
| Secrets | keychain path only; none copied into this report |

---

## Automated ACP (acpx) - primary pre-GUI tier

Client: `acpx` **0.12.0** via `npx acpx@latest`, `--format json`, agent =
`optimus-agent --workspace-root . --debug-trace --model claude-haiku`.

### Exact-path (after fixture reset)

**Artifact:** `reports/plan98-acpx-exact-path-retry-output.jsonl`
**run_id:** `session-ab09a18c0f6540478de7ab01446817a8:2`

| Check | Result |
|-------|--------|
| `stopReason` | `end_turn` |
| Permission | `session/request_permission` id 10000, nested `toolCall`, `--approve-all` -> `approve` |
| Tools | `file_reader`, `write_file` |
| `P9.8-CONTEXT` | prioritized exact path, `used_bytes=16384`, `omitted_count=330`, `blocking_stop_reason=null` |
| Debug | `mutation_count=1`, `status=completed` |
| `-32602` | none |

(First attempt refused with `"Turn completed."` because the fixture already had a docstring from a
prior run - stale-fixture -> `UNPARSEABLE_PLAN`, not a protocol failure.)

### Ambiguous

**Artifact:** `reports/plan98-acpx-ambiguous-output.jsonl`
**Workspace:** `reports/.plan98-ambiguous-live`
**run_id:** `session-2b98bc0604f3443493a92be2e09b11eb:2`

| Check | Result |
|-------|--------|
| `stopReason` | `refusal` |
| Message | candidates `a/example.py`, `b/example.py` (not `"Turn completed."`) |
| Permission / tools | none |
| `P9.8-CONTEXT` | `AMBIGUOUS_WORKSPACE_REFERENCE`, `used_bytes=0` |
| Fixtures | unchanged |

---

## Zed live gates (Steps 6-7)

### Step 6 - Exact-path large-workspace (Zed)

**Task:** `Add a docstring to reports/.plan98-e2e-workspace/example.py.`
**run_id:** `session-51d2f79bfe8343c8b701eed123265ae4:f71b5c64-c3c1-494e-8dd1-47ab0c658924`
**Log:** `.optimus/debug-acp.ndjson`

| Claim | Evidence |
|-------|----------|
| `P9.8-CONTEXT` | resolved exact path, `used_bytes=16384`, `omitted_count=330`, `blocking_stop_reason=null` |
| Plan / permission | `GAP2 has_entries=true`, `H2 has_toolCall=true`, approve selected |
| Execution | `mutation_count=1`, `tool_names=[file_reader, write_file]` |
| Completion | `Completed:\n- wrote reports/.plan98-e2e-workspace/example.py` |
| `stop_reason` | **`end_turn`** on `server.py:process_request:exit` for request `f71b5c64-...` (directly logged) |
| `-32602` | zero in full 234-line log at review time |
| Fixture | docstring present; SHA256 `C13060FE2441328D8BA62B41C204302C137E535E95B3A6F7FEA5EC69F588FF13` |
| Operator UI | Approve -> file_reader -> write_file -> Completed Plan (7 steps) |

### Step 7 - Ambiguous refusal (Zed) + crash disposition

**Task:** `Add a docstring to example.py.`
**Workspace:** `reports/.plan98-ambiguous-live`
**run_id:** `session-32800dacfab94513a2003738696c46b8:6b18df4b-f7bd-407e-ba0a-69394b56a551`
**Log:** `reports/.plan98-ambiguous-live/.optimus/debug-acp.ndjson`

| Claim | Evidence |
|-------|----------|
| `P9.8-CONTEXT` | `AMBIGUOUS_WORKSPACE_REFERENCE`, candidates `[a/example.py, b/example.py]`, `used_bytes=0` |
| Tools / permission | structurally never emitted for this `run_id` |
| Message (server) | corrective ambiguous text (`H7` preview) |
| `stop_reason` | **`refusal`** on `process_request:exit` for `6b18df4b-...` (directly logged) |
| Fixtures | `def a(): return 1` / `def b(): return 2` unchanged |
| Operator UI | corrective text **flashed**, then Zed crashed |

#### Zed panic (P9.8-FU-5) - verified on disk

| Artifact | Path |
|----------|------|
| Panic JSON | `%LOCALAPPDATA%\Zed\logs\1376d75f-30d5-4337-a14a-c46f05718501.json` |
| Minidump | same basename `.dmp` (**226198** bytes) |

Panic payload (excerpt, no secrets):

```json
{
  "init": {
    "zed_version": "1.10.2",
    "commit_sha": "adc60ccf12e199b8828bad3abb2591e147034734",
    "binary": "zed"
  },
  "panic": {
    "message": "range end index 3 out of range for slice of length 2"
  }
}
```

Zed.log: same panic at **18:10:49** and **18:13:13** (reproduced). Minidump upload event id
`a944891d-0860-4fb5-bfb9-8e44862d0a0a`. Panic is inside the Zed binary (Rust slice OOB), after the
agent had already completed the refusal turn. Not `-32602` / non-conformant ACP shapes. Exact-path
on the same Zed build did not panic. acpx completes the identical refusal protocol without crash.

**Disposition:** Deferred as **`P9.8-FU-5`**. Step 7 agent contract is live-verified (message
observed + correlated logs). Durable on-screen refusal in Zed is **not** claimed; durable UI proof
is via acpx. Fixing the Zed panic is out of Plan 9.8 agent scope.

---

## Redacted debug excerpts (no source / secrets)

Exact-path `P9.8-CONTEXT`:

```json
{
  "hypothesisId": "P9.8-CONTEXT",
  "runId": "session-51d2f79bfe8343c8b701eed123265ae4:f71b5c64-c3c1-494e-8dd1-47ab0c658924",
  "data": {
    "max_total_bytes": 16384,
    "used_bytes": 16384,
    "prioritized_paths": ["reports/.plan98-e2e-workspace/example.py"],
    "omitted_count": 330,
    "blocking_stop_reason": null
  }
}
```

Ambiguous `P9.8-CONTEXT`:

```json
{
  "hypothesisId": "P9.8-CONTEXT",
  "runId": "session-32800dacfab94513a2003738696c46b8:6b18df4b-f7bd-407e-ba0a-69394b56a551",
  "data": {
    "used_bytes": 0,
    "prioritized_paths": [],
    "references": [{
      "reference": "example.py",
      "status": "ambiguous",
      "candidates": ["a/example.py", "b/example.py"]
    }],
    "blocking_stop_reason": "AMBIGUOUS_WORKSPACE_REFERENCE"
  }
}
```

---

## Commands and exit codes (live)

| Command | Exit |
|---------|------|
| `optimus-agent --check-config --strict --debug-trace` | 0 |
| `npx acpx@latest ... exec` exact-path (retry) | 0 |
| `npx acpx@latest ... exec` ambiguous | 0 |
| Zed exact-path session | completed (`end_turn`) |
| Zed ambiguous session | agent `refusal`; client panic after flash |

Superseded harness outputs (not primary evidence):
`reports/plan98-exact-path-live-output.json`, `reports/plan98-ambiguous-live-output.json`.

---

## Limitations and explicit non-claims

1. Does **not** prove mutation tasks generally; only the exact-path docstring fixture under filler
   pressure.
2. Does **not** provide multi-turn replan or Plan 11 selection.
3. Ambiguous refusal is **not** durable in Zed 1.10.2 UI (`P9.8-FU-5`); operator saw a flash then
   crash.
4. `tools/run_plan98_live_evidence.py` is **not** independent conformance evidence (`P9.8-FU-6`).
5. Unit `FakeGatewayClient` doubles remain valid for isolated business-logic tests; the
   "no project-authored ACP client as live proof" policy applies to ACP integration/live tooling.
6. Plan 9.6 small-workspace mutation remains baseline evidence, not a new 9.8 claim.
7. No secrets, provider keys, or workspace file bodies are included in this report.

---

## Cross-references

- Historical READ-only / HITL context: [`plan-9-75-zed-hitl-runtime-evidence.md`](plan-9-75-zed-hitl-runtime-evidence.md) (append-only cross-ref; historical result unchanged).
- Roadmap status: [`docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`](../docs/superpowers/plans/2026-07-01-phase-1-roadmap.md) -> Plan 9.8.
