# Plan 9.75 — Zed HITL Runtime Evidence (Issue #33)

**Date:** 2026-07-10
**Client:** Zed 1.10.0+stable.318.111c4082fd38215c31fa87803ece7695f898a94e
**Agent build:** `a53c2ee` (`optimus-cost-agent-wt-cursor`, instrumented `debug/issue-33-trace`)
**Log:** `.optimus/debug-acp.ndjson` (copy committed with this report)

## Summary

Zed `session/prompt` does **not** hang indefinitely server-side. The agent completes in ~5.6s with
`stopReason: cancelled` after Zed rejects two non-conformant outbound messages at deserialization
(`-32602`). `deliver_client_response` masks those errors as `{outcome: cancelled}`, producing an
empty thread with no plan, approval UI, or error — perceived as a spinner.

## Dual-source correlation

| Step | Zed ACP log | Agent log (line) | Match |
|------|-------------|------------------|-------|
| Build provenance | stderr: `ACP debug trace: ...debug-acp.ndjson` | L1 `PROVENANCE` `git_sha=a53c2ee` | ✓ |
| Planning completes | — | L8 `status=awaiting_approval` | ✓ |
| Plan sent (non-conformant) | `content: [{type,text}]`, no `entries` | L9 `has_entries=false` | ✓ |
| Permission sent (non-conformant) | no `toolCall` in params | L11–12 `has_toolCall=false` | ✓ |
| Zed rejects plan | `-32602` `missing field entries` | L13 `H2-REPLY` | ✓ |
| Zed rejects permission | `-32602` `missing field toolCall` (id 10000) | L15 `H2-REPLY` | ✓ |
| Agent masks errors → cancelled | — | L14, L16 `mapped_to_cancelled=true` | ✓ |
| `session/prompt` ends | `stopReason: cancelled` | L18 | ✓ |

## Root cause (confirmed)

1. **GAP2 — plan `session/update`:** Agent sent `update.content` (content blocks) instead of
   `update.entries` (`PlanEntry.content` is a **plain string**, not blocks).
2. **H2 — permission request:** Agent omitted required nested `toolCall` on
   `session/request_permission` (`ToolCallUpdate` under `toolCall` key).
3. **H1 — error masking:** `NdjsonOutboundChannel.deliver_client_response` maps client JSON-RPC
   errors to `{outcome: {outcome: cancelled}}`, hiding protocol failures.

## Hypothesis disposition

| ID | Hypothesis | Result |
|----|------------|--------|
| H1 | Error masking → invisible cancelled | **CONFIRMED** (L14, L16) |
| H2 | Missing `toolCall` on permission | **CONFIRMED** (L11–12, L15) |
| H2-REPLY | Zed rejects at deserialization, not silent drop | **CONFIRMED** (L13, L15) |
| GAP2 | Plan missing `entries` | **CONFIRMED** (L9, L13) |
| GAP1 | Metadata echo required for approval | **NOT REACHED** (cancelled before approval) |
| H3 | Agent-side planning deadlock | **REJECTED** (L8 planning_done in ~5.5s) |
| H4 | Swallowed exception, no response | **NOT OBSERVED** this run |

## Agent log excerpts

**Plan emission (defect):**
```json
{"location":"spec.py:_emit_result_updates:plan","data":{"update_keys":["content","sessionUpdate"],"has_entries":false}}
```

**Zed rejection (plan notification error, no request id):**
```json
{"error":{"code":-32602,"message":"Invalid params","data":{"error":"missing field `entries`"}}}
```

**Zed rejection (permission request id 10000):**
```json
{"error":{"code":-32602,"message":"Invalid params","data":{"error":"missing field `toolCall`"}}}
```

## Fix contract (approved)

**Phase 1 — conformance**

- Plan update: `entries: [{content: <string>, priority, status}]` per ACP v1 schema.
- Permission request: nested `toolCall: {toolCallId, ...}` (`ToolCallUpdate`).
- `tool_call_update` notifications: **flattened** `toolCallId` + fields at `update` level (not nested `toolCall`).
- Approval handshake: agent-side `approvalId` + `plan_hash` from retained `planning_result` (runner gates on `plan_hash` only).

**Phase 2 — error surfacing**

- Stop mapping outbound-request JSON-RPC errors to `cancelled`; propagate visible failure.
- `process_request` exceptions → JSON-RPC error response (not silent drop).

## Post-fix success criteria

| Signal | Expected |
|--------|----------|
| Zed `-32602` on plan/permission | **None** |
| Agent log | `has_entries: true`, `has_toolCall: true` |
| `permission_done` | `outcome: selected` → `stopReason: end_turn` |
| Zed UI | Plan or approval UI visible |

## Caveat

This run resolved in ~5.6s with `stopReason: cancelled`, not an indefinite spinner. The original
report may have been H4 (swallowed exception) or Zed UI idling on cancelled+empty content. Phase 2
addresses the latter class; Phase 1 addresses protocol non-conformance.

---

## Post-fix verification (2026-07-10, Zed 1.10)

**Prompt:** "Add a docstring to example.py" (two turns in same session)
**Build:** `fix/issue-33-acp-conformance` working tree via `uv tool install --editable`
**Log:** `.optimus/debug-acp.ndjson` (session `session-1e3658b5db7d4321bfd96445f1342847`)

### Turn 1 — Cancel gate (explicit rejection)

| Signal | Expected | Observed |
|--------|----------|----------|
| Zed permission response | `optionId: cancel` | L12–13 `{"outcome":"selected","optionId":"cancel"}` |
| `permission_done` | cancel outcome | L14 |
| `stopReason` | `cancelled` | L15 |
| Post-approval execution | None | No `approved_done`, no `tool_call`, no H7 |
| File writes | None | `mutation_count` not reached |

Zed UI: approval bar dismissed with Cancel (red X); no execution.

### Turn 2 — Approve + H7 gate

| Signal | Expected | Observed |
|--------|----------|----------|
| Plan emit | `has_entries: true` | L19–20 |
| Permission emit | `has_toolCall: true` | L22–23 |
| Zed `-32602` | None | No error lines |
| `permission_done` | `optionId: approve` | L25–26 |
| Approved execution | `file_reader` only | L27 `mutation_count: 0`, `tool_names: ["file_reader"]` |
| `tool_call` init | H5 | L28–29 |
| H7 completion | plan completed + message | L30–32 `message_preview: "Executed:\n- read reports/.plan97-e2e-workspace/example.py"` |
| `stopReason` | `end_turn` | L33 |

Zed UI: `file_reader` output → "Executed: read reports/.plan97-e2e-workspace/example.py" →
"Completed Plan — 1 step" with green checkmark on READ entry.

### Post-fix hypothesis disposition

| ID | Result | Evidence |
|----|--------|----------|
| GAP2 (plan entries) | **FIXED** | L19 `has_entries: true` |
| H2 (toolCall) | **FIXED** | L22 `has_toolCall: true` |
| H1 (error masking) | **FIXED** | L24 `mapped_to_cancelled: false` |
| GAP1 (metadata echo) | **FIXED** | L26 approve without metadata; L27 approved execution proceeds |
| `optionId` guard | **FIXED** | L12–15 cancel → cancelled, no execution |
| H5 (tool_call init) | **FIXED** | L28–29 |
| H7 (completion UX) | **FIXED** | L30–32; Zed shows message + completed plan |

### Known limitation (out of scope #33)

Gateway returned READ-only plan (`READ reports/.plan97-e2e-workspace/example.py`) for a docstring
mutation task — no `WRITE` directive, so no file was modified despite successful HITL flow.
Planner/gateway prompt quality; track separately.

### Fast-follow (non-blocking)

`_emit_completion_message` on `FAILED`/`TERMINATED` early-return may emit `"Turn completed."`
alongside `stopReason: refusal` — log as follow-up issue, not a merge blocker.

---

## Post-#36 regression — 2026-07-11 (main @ 7376e23)

2026-07-11: plan + approval + completed turn; READ-only plan to fixture paths; no protocol hang.

**Provenance (debug trace, not prose alone):** `optimus-cost-agent-wt-cursor\.optimus\debug-acp.ndjson`
— PROVENANCE lines on 2026-07-11 show `git_sha: 7376e23`, `optimus_acp_file` under the **primary
clone** (`D:\Projects\Development\Python\optimus-cost-agent\src\...`) from the uv editable PATH
install, while `cwd` / `--workspace-root .` resolved to the **wt-cursor worktree**
(`D:\Projects\Development\Python\optimus-cost-agent-wt-cursor`). Agent **code** = primary clone
`main` @ `7376e23`; Zed **workspace** = wt-cursor.

Zed agent config: `optimus-agent` with `--workspace-root .`, `--debug-trace`. Latest session:
2-step Completed Plan (READ `reports/.plan97-e2e-workspace/example.py`, READ
`reports/.verify-live-agent-workspace/example.py`); `stop_reason: end_turn`; no `-32602`
deserialization errors. Fixture paths exist in wt-cursor but not primary clone — consistent with
Plan 9.8 workspace-context attribution. HITL protocol from PR #36 remains intact.

---

## Cross-reference — Plan 9.8 (2026-07-11)

Task-aware workspace context live evidence is recorded in
[`plan-9-8-task-aware-context-evidence.md`](plan-9-8-task-aware-context-evidence.md). That report
preserves this document's historical READ-only / HITL findings unchanged. Plan 9.8 exact-path Zed
mutation under filler pressure succeeded on Zed 1.10.2 with conformant `entries` / nested
`toolCall` and no `-32602`. Ambiguous refusal completed correctly on the agent wire (and briefly
in Zed UI) before a Zed client panic tracked as `P9.8-FU-5` — a separate client-stability issue,
not a regression of the Plan 9.75 protocol fixes.
