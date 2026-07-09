## Summary

`optimus-agent` launches in Zed (Plan 9.7 operator PATH install verified) but **never returns a user-visible response** after `session/prompt` — loading spinner runs indefinitely with no plan, answer, or error.

**Priority:** P0 — blocks real-IDE sign-off and further manual use-case testing.

**Related plans:**
- Plan 9.6 — Known Open Defects → Zed HITL (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`)
- Plan 9.7 — manual DoD planning bar deferred pending this fix (`docs/superpowers/plans/2026-07-08-plan-9-7-local-dev-infra-autostart-and-setup.md`)
- Phase 1 Roadmap item 13 (`docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`)

**Out of scope (working per Plan 9.7 manual smoke):** PATH install, `--setup`, `--check-config --strict`, auto-start Redis/gateway, minimal Zed `agent_servers` launch.

---

## Environment

- OS: Windows 10
- IDE: Zed with custom ACP agent
- Install: `optimus-agent` from `%APPDATA%\Python\Python314\Scripts\optimus-agent.exe` (global PATH, not `.venv`)
- Tested on Plan 9.7 branch (merged via PR #32)
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
2. Start a **new** Optimus agent thread (do **not** resume — `sessionCapabilities: {}`, no `session/load`).
3. Send a read-only prompt, e.g. "What is this repository? Give me a 3-sentence summary based on the README. Do not change any files."
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

1. **HITL deadlock** — `AcpDuplexAdapter` keeps `session/prompt` pending until Zed responds to outbound `session/request_permission`; Zed may not render or auto-approve for custom `agent_servers`.
2. **ACP payload gap** — Plan 9.6/README claim `session/request_permission` includes ACP v1 `toolCall`. **`src/optimus/acp/spec.py` `_request_permission()` (lines 229–259) sends only `options` + `metadata` — no `toolCall`.** `toolCall` appears only in `session/update` `tool_call_update` notifications (lines 274–286). `tests/unit/acp/test_spec_protocol.py` does not assert `toolCall` on permission requests. Docs overstate fix state.
3. **Agent mode for all prompts** — `AcpSpecSession` defaults to `ExecutionMode.AGENT`; read-only questions still require approval. Consider Plan/Chat fast path.
4. **Unhandled prompt exceptions** — `serve_ndjson()` may not surface `process_request` failures to client; `session/prompt` can hang silently (reporter saw `PermissionError` on directory read in stderr during smoke).
5. **Session resume** — separate follow-up.

---

## Suggested fix scope (do not start without plan approval)

1. Implement and test ACP-conformant `toolCall` on `session/request_permission` per ACP v1; update `test_spec_protocol.py`.
2. Re-test in real Zed with/without `always_allow_external_agent_tools: true`; capture HITL artifact under `reports/`.
3. Ensure `session/prompt` always resolves (success, cancellation, or JSON-RPC error).
4. Consider read-only / Plan-mode path for Q&A without mutation approval.
5. Align Plan 9.6 defect text with actual code state.

---

## Evidence artifacts to produce when fixed

- ACP transcript: `initialize` → `session/new` → `session/prompt` → `session/update` → `session/request_permission` (or error)
- `reports/` HITL artifact
- Plan 9.6 checkbox: re-run Zed HITL flow
