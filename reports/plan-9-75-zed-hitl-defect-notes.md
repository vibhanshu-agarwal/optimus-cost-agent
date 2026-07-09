# Plan 9.75 defect notes — Zed `session/prompt` hang

Reference material for
`docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md`.
Use **Plan 9.75** in cross-plan references — not PR or issue numbers.

## Summary

`optimus-agent` launches in Zed (Plan 9.7 operator PATH install verified) but **never returns a
user-visible response** after `session/prompt` — loading spinner runs indefinitely with no plan,
answer, or error.

**Priority:** P0 — blocks real-IDE sign-off and further manual use-case testing.

**Related plans:**

- [Plan 9.75](../docs/superpowers/plans/2026-07-09-plan-9-75-zed-hitl-acp-toolcall-permission.md)
  — implementation plan (primary tracking)
- Plan 9.6 — Known Open Defects → Zed HITL
  (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`)
- Plan 9.7 — manual DoD planning bar deferred pending Plan 9.75
  (`docs/superpowers/plans/2026-07-08-plan-9-7-local-dev-infra-autostart-and-setup.md`)
- Phase 1 Roadmap item 13 (`docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`)

**Out of scope (working per Plan 9.7 manual smoke):** PATH install, `--setup`,
`--check-config --strict`, auto-start Redis/gateway, minimal Zed `agent_servers` launch.

---

## Environment

- OS: Windows 10
- IDE: Zed with custom ACP agent
- Install: `optimus-agent` from `%APPDATA%\Python\Python314\Scripts\optimus-agent.exe` (global
  PATH, not `.venv`)
- Tested after Plan 9.7 merge to `main` (2026-07-09)
- Zed `agent_servers`:

```json
{
  "agent_servers": {
    "optimus": {
      "type": "custom",
      "command": "optimus-agent",
      "args": ["--workspace-root", "."]
    }
  }
}
```

- Pre-flight: `optimus-agent --workspace-root . --check-config --strict` → exit 0

---

## Repro

1. Open Zed on repo root (same folder as `--workspace-root "."`).
2. Start a **new** Optimus agent thread (do **not** resume — `sessionCapabilities: {}`, no
   `session/load`).
3. Send a read-only prompt, e.g. "What is this repository? Give me a 3-sentence summary based on
   the README. Do not change any files."
4. **Actual:** loading indicator indefinitely; no plan, answer, error, or approval UI.

## Expected

- `session/update` (plan) during planning
- ACP-conformant `session/request_permission` with Zed approval UI (or auto-approve)
- `session/prompt` completes with `stopReason` and user-visible content

---

## What works vs broken

| Works | Broken |
|-------|--------|
| Global PATH `optimus-agent` | No user-visible response after `session/prompt` |
| `--setup` keychain | Session resume (unsupported by design) |
| `--check-config --strict` | Zed approval UI / HITL wiring |
| Auto-start Redis + gateway | Read-only prompts still require Agent-mode plan+approval |

---

## Likely root causes (priority order)

1. **HITL deadlock** — `AcpDuplexAdapter` keeps `session/prompt` pending until Zed responds to
   outbound `session/request_permission`; Zed may not render or auto-approve for custom
   `agent_servers`.
2. **ACP payload gap** — `_request_permission()` (`spec.py` lines 229–259) sends only `options`
   + `metadata` — **no `toolCall`.** `toolCall` appears only in `session/update`
   `tool_call_update` notifications (lines 274–286). No test asserts `toolCall` on permission
   requests. **Hypothesis:** #2 likely causes #1.
3. **Agent mode for all prompts** — read-only questions still require approval; separate UX scope
   (not Plan 9.75).
4. **Unhandled prompt exceptions** — `serve_ndjson()` may not surface failures to client.
5. **Session resume** — separate follow-up.

---

## Evidence artifacts to produce when fixed

- ACP transcript: `initialize` → `session/new` → `session/prompt` → `session/update` →
  `session/request_permission` (or error)
- `reports/` HITL artifact
- `reports/plan-9-7-manual-e2e-evidence.md` planning section filled; Plan 9.7 DoD box checked
- Plan 9.6 HITL claim-table row closed
