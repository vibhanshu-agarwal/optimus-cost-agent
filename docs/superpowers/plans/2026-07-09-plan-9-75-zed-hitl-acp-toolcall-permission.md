# Plan 9.75: Zed HITL — ACP `toolCall` on `session/request_permission`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before
> implementation. Do not start without reviewer approval of this plan.

**Goal:** Unblock real-IDE sign-off by fixing the Zed `session/prompt` hang after planning: send
ACP v1-conformant `toolCall` on `session/request_permission`, verify Zed renders approval UI (or
auto-approve path works), and complete a real planning turn through the operator PATH install
from Plan 9.7.

**Status:** Drafted 2026-07-09 (P0). Not yet implemented. Supersedes ad-hoc issue tracking for
this defect — use **Plan 9.75** in roadmap and cross-plan references, not PR or issue numbers.

**Architecture:** Minimal change in `src/optimus/acp/spec.py` `_request_permission()` plus
protocol tests in `tests/unit/acp/test_spec_protocol.py`. Reuse `toolCall` field construction
patterns from the existing `session/update` `tool_call_update` path. No gateway or local-infra
changes (Plan 9.7 scope).

**Relationship to other plans:**

- **Plan 9.6** — Known Open Defects section records symptom and root-cause analysis; Plan 9.75
  closes the open HITL claim-table row when a real Zed artifact is committed under `reports/`.
- **Plan 9.7** — Operator infra path verified; manual DoD planning bar stays unchecked until
  Plan 9.75 completes and evidence is recorded in `reports/plan-9-7-manual-e2e-evidence.md`.
- **Plan 9.8** — Unified Gateway Capabilities Broker; **out of scope** for Plan 9.75.

## Verified facts (code review 2026-07-09)

- `_request_permission()` (`spec.py` lines 229–259) sends only `options` + `metadata` — **no
  `toolCall`** on `session/request_permission`.
- `toolCall` appears only on `session/update` `tool_call_update` notifications.
- No test asserts `toolCall` on permission requests.
- Plan 9.6 previously overstated that `toolCall` was fixed; correction recorded in Plan 9.6
  Known Open Defects.

## Working hypothesis

Missing `toolCall` on `session/request_permission` likely **causes** the HITL deadlock: Zed cannot
render approval UI → adapter blocks awaiting a response that never comes.

## Explicit scope boundaries

**In scope:**

1. Failing test asserting `toolCall` shape on outbound `session/request_permission`.
2. Payload fix in `_request_permission()`.
3. Real Zed re-test with Plan 9.7 operator PATH config; commit HITL artifact under `reports/`.
4. Fill `reports/plan-9-7-manual-e2e-evidence.md` planning-run section; check Plan 9.7 DoD box.

**Out of scope (separate plan/UX decision):**

- Read-only / Plan-mode fast path for Q&A without mutation approval (root-cause #3 in defect
  notes).
- Session resume support.
- Cross-layer provider/key mismatch warning (parked for Plan 9.8 or later).

## Suggested task order (TDD)

- [ ] **Task 1:** Add failing `test_spec_protocol.py` assertion for `toolCall` on
  `session/request_permission`.
- [ ] **Task 2:** Implement `toolCall` in `_request_permission()`; green unit tests + ruff.
- [ ] **Task 3:** Manual Zed verification (operator PATH, same config as Plan 9.7 partial sign-off);
  record transcript and stdout in `reports/plan-9-7-manual-e2e-evidence.md`.
- [ ] **Task 4:** Close Plan 9.6 defect status when DoD met (README architecture narrative and
  known-defect pointers for Plans 9.6–9.75 landed in the doc-consistency pass; approval-handshake
  text documents current vs Plan 9.75 target state).

## Definition of Done

- Zed shows plan text or approval UI after `session/prompt` (no infinite loading).
- `session/prompt` always resolves (success, cancellation, or JSON-RPC error).
- Committed `reports/` HITL artifact + filled Plan 9.7 evidence template.
- Plan 9.7 manual DoD planning checkbox checked with evidence citation.

## Reference notes

Detailed repro, environment, and root-cause analysis:
`reports/plan-9-75-zed-hitl-defect-notes.md`.
