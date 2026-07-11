# Plan 9.75: Zed HITL — ACP conformance (plan entries + permission `toolCall`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before
> implementation.

**Goal:** Fix Zed `session/prompt` empty-thread / perceived-spinner after planning by sending
ACP v1-conformant `session/update` plan entries and `session/request_permission` payloads, completing
a real planning turn through approval.

**Status:** Complete (2026-07-10). Runtime evidence and post-fix Zed verification committed in
`reports/plan-9-75-zed-hitl-runtime-evidence.md` (merged via PR #36).

**Architecture:** Build wire shapes from ACP v1 `schema.json` in `src/optimus/acp/shapes.py`; wire
through `src/optimus/acp/spec.py`. Protocol tests pin exact serialized shapes in
`tests/unit/acp/test_shapes.py` and `tests/unit/acp/test_spec_protocol.py`. Phase 2 error surfacing
in `src/optimus/acp/server.py`.

**Runtime evidence (2026-07-10):** Zed 1.10 rejects non-conformant plan (`missing field entries`)
and permission (`missing field toolCall`) at deserialization with `-32602`. Error masking converted
both to invisible `stopReason: cancelled` (~5.6s). Post-fix verification confirms Cancel and
Approve/H7 gates. See evidence report for dual-source correlation.

## Verified defects (runtime + code review)

1. **Plan `session/update`:** Agent sent `update.content` (content blocks) instead of required
   `update.entries`. **`PlanEntry.content` is a plain string**, not content blocks.
2. **Permission request:** Agent omitted required nested `toolCall` (`ToolCallUpdate` under `toolCall`
   key) on `session/request_permission`.
3. **`tool_call_update` notifications:** Fields must be **flattened at `update` level** (`toolCallId`,
   `title`, `content`, …) — not nested under `toolCall`. Permission request uses the **opposite**
   nesting: `toolCall: { toolCallId, … }`.
4. **Approval handshake:** Runner integrity gate is `plan_hash` only; agent generates `approvalId`
   and reads `plan_hash` from retained `planning_result` (Zed need not echo `metadata`).
5. **Error masking (Phase 2):** `deliver_client_response` mapped client JSON-RPC errors to
   `{outcome: cancelled}`.

## Explicit scope boundaries

**In scope (Phase 1):**

1. `entries: [{content: <string>, priority, status}]` on plan `session/update`.
2. Nested `toolCall` on `session/request_permission`.
3. Flattened `tool_call_update` on execution `session/update`.
4. Agent-side approval handshake (no metadata echo dependency).
5. Unit tests pinning exact shapes from `tests/fixtures/acp/acp-v1-schema.json`.
6. Committed runtime evidence under `reports/`.

**In scope (Phase 2):**

1. Propagate outbound-request JSON-RPC errors (do not map to `cancelled`).
2. `process_request` exceptions → JSON-RPC error response on `session/prompt`.

**Out of scope:**

- Plan/Chat fast path without approval.
- Session resume.

## Task order (TDD)

- [x] **Task 0:** Commit runtime evidence (`reports/plan-9-75-zed-hitl-runtime-evidence.md`).
- [x] **Task 1:** Failing shape tests (`test_shapes.py`, `test_spec_protocol.py`).
- [x] **Task 2:** Implement `shapes.py` + `spec.py` conformance; green unit tests + ruff.
- [x] **Task 3:** Phase 2 `server.py` error propagation tests + implementation.
- [x] **Task 4:** Post-fix Zed verification with `--debug-trace`; confirm success table.
- [x] **Task 5:** Close Plan 9.6 / Plan 9.7 evidence rows when DoD met — **2026-07-11:** Plan 9.6
  claim table 8/8, Phase C evidence in `reports/plan-9-7-manual-e2e-evidence.md`, Phase E regression
  in `reports/plan-9-75-zed-hitl-runtime-evidence.md` § Post-#36 regression — 2026-07-11.

## Definition of Done

- No Zed `-32602` on plan or permission outbound messages.
- Agent logs: `has_entries: true`, `has_toolCall: true`.
- `permission_done` with `outcome: selected` → `stopReason: end_turn` (GAP1 proof).
- Zed shows plan or approval UI after `session/prompt`.
- `session/prompt` resolves with success, visible error, or explicit cancellation.

## Post-fix success table

| Signal | Expected |
|--------|----------|
| Zed `-32602` on plan/permission | None |
| Agent log plan emit | `has_entries: true` |
| Agent log permission emit | `has_toolCall: true` |
| `permission_done` | `outcome: selected` |
| `session/prompt` result | `stopReason: end_turn` |
| Zed UI | Plan or approval visible |

## Reference

- Runtime evidence: `reports/plan-9-75-zed-hitl-runtime-evidence.md`
- Defect notes: `reports/plan-9-75-zed-hitl-defect-notes.md`
- Schema fixture: `tests/fixtures/acp/acp-v1-schema.json`
