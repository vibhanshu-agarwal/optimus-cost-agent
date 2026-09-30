# Plan 12.1 — Task 0: picker finding and live-proof prerequisites

**Date:** 2026-09-29 (observations); 2026-09-30 (report, re-checks).
**Plan:** [Plan 12.1 implementation plan](../docs/superpowers/plans/2026-09-29-plan-12-1-plan-chat-advisory-answer-implementation.md), Task 0.
**Base:** `origin/main` `08ec2ee`. No product code is changed by this report.
**Raw artifacts:** screenshots, protocol probe transcript, Zed log excerpts and trace summaries are held outside the repository in the operator's handoff kit, folder `plan12-1-task0-20260929`. They are not copied here because they contain private paths.

## 1. Installed clients

| Item | Value |
|---|---|
| Zed | 1.21.0+stable.362.33c95853ed2b6956f339733c63a8220964ecbeb6 |
| `acpx` | 0.12.0 (independently authored ACP client) |
| Zed agent servers configured | optimus, github-copilot-cli, gemini, codex-acp, claude-acp, junie, cursor, auggie |
| Installed `optimus-agent` at observation time | uv tool built from the Plan 11.7 resume-runtime branch (`c69fd48`), which advertises `session/load`. It is not `main` and not the Plan 12.1 build. Task 4 must install the Plan 12.1 build first. |

## 2. Optimus `Loading...` finding

The Optimus thread that stayed at `Loading...` was a restored thread. Zed called `session/load`; during the load, Optimus sent `session/request_permission` for the Zed-configured MCP servers before Zed could answer it. `session/load` became slow at about 30 seconds and a second permission request followed.

- **Cause:** Zed live-check finding #6 (MCP permission requests sent before the client can handle them), on the resume path.
- **Not** evidence about how Zed renders modes or config options.
- **Owner:** outside Plan 12.1. `main` does not advertise `session/load`, and this plan keeps it absent.
- **Consequence for Task 4:** live proof uses a **new** Zed thread.

## 3. Picker observation (reference agent)

**Who and how:** Claude, through computer use at the operator's direction (operator, 2026-09-29: Claude may drive Zed itself), 2026-09-29 23:07–23:10 IST. New "Claude Agent" thread (Zed registry `claude-acp`, package `@agentclientprotocol/claude-agent-acp`). Nothing was sent; no model call was made.

**Observed controls under the composer:**

| Control | Values shown |
|---|---|
| Mode | Manual, Accept edits, Plan, Auto, Bypass permissions |
| Model | Default (recommended), and the listed models |
| Effort | Default, Low, Medium, High, Xhigh, Max |
| Fast mode | toggle |

The dropdowns show the prompt "Select an option...", which is Zed's config-option picker.

**Reference-agent response shape** (protocol probe: `initialize` and `session/new` only, no prompt):

- classic `modes`: `currentModeId` plus five `availableModes`;
- `configOptions`: `mode` (category `mode`, type `select`, mirrors `modes`), `model` (category `model`), `effort` (category `thought_level`) and `fast` (category `model_config`, select on/off).

**What this settles:**

- Zed shows **one** Mode picker while the agent sends both surfaces, so Zed renders the mode-category config option.
- Rendering of classic `modes` alone was **not** observed and remains unverified.
- The pinned schema `tests/fixtures/acp/acp-v1-schema.json` supports `configOptions` (select and boolean), `session/set_config_option` and `config_option_update`. Categories `mode`, `model` and `thought_level` are reserved; `_`-prefixed categories are free for custom use. A later context-strategy picker can therefore be a separate `_context_strategy` option.

**Accepted decision (design revision, merged in PR #211):** Plan 12.1 mirrors Agent/Chat through both surfaces: classic `modes` and one `mode`-category select config option. Both `session/set_mode` and `session/set_config_option` (configId `mode`) are accepted and kept in sync, and each real change emits `current_mode_update` and then `config_option_update`. The reference-agent observation is not Definition-of-Done evidence; Task 4 proves the implemented Optimus agent with `acpx` and Zed.

## 4. Live-proof prerequisites

| Prerequisite | Satisfied? | Owner | Evidence, or next action |
|---|---|---|---|
| Gateway reachable with Luna | yes (2026-09-29) | Operator (service state); Claude checks | `optimus-agent` auto-starts the local Gateway (OpenRouter provider). Luna runs succeeded in the 2026-09-29 Zed re-check. Claude re-checks when Task 4 starts. |
| Redis | yes (re-checked 2026-09-30) | Operator | `optimus-redis` container up (`redis:8`). |
| `acpx` usable | yes (re-checked 2026-09-30) | Claude | 0.12.0. |
| Zed usable | yes | Claude (computer use, at operator direction) | 1.21.0. New threads work; restored threads hit finding #6 (section 2). |
| Credentials | yes, not inspected | Operator | Only the Gateway holds the provider key. The agent receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` through its launch. No secret was read or recorded. |
| Paid-call authority | yes | Operator | Operator, 2026-09-29: Luna through the Gateway, at most $0.05 per prompt, at most six paid calls in total; record the call count and the Gateway-reported cost. Evidence collection only. |
| Cost recording | partial | Claude records; gap owned elsewhere | Gateway-reported `total_cost_usd` is available per run. `gateway_request_id` is `None` on the ACP path, so request IDs cannot be recorded. This is a known telemetry gap. The closest existing owner is `P11.26-CAND-2-TELEMETRY-CONTRACT`, which holds one schema and correlation authority for telemetry. No pool entry names this ACP-path gap specifically, and this report files none. It is not fixed here. |
| Trusted-workspace approval | no (not yet verified for the 12.1 build) | Claude | The existing durable approval was issued for the earlier install. Next action at Task 4: install the Plan 12.1 build, then re-check the approval before the first paid call. |
| Guarded-lane predicates | checked before each run and commit | Claude | Two predicates, checked before any local pytest run or commit with hooks: (1) no `run_main5_guarded_suite` process is active; (2) the newest `main5-*` guarded-run folder that contains `before.json` also contains `result.json`. The process check must exclude its own process tree, because a self-match gave a false count of 4 in the first attempt. |

## 5. Paid-call budget plan (at most six Gateway calls)

Chat makes **one** Gateway call per prompt. An Agent prompt can make up to three planning calls, so no Agent prompt is sent live.

| Use | Calls |
|---|---|
| `acpx`: one Chat question | 1 |
| Zed, new thread, Chat mode: one greeting and one read-only workspace question | 2 |
| Reserve: one retry each if a run fails for an environment reason | 3 |

The Agent default and the approval path are proven by unit tests and by the mode state that `acpx` and Zed observe, without an Agent prompt.

## 6. Plan wording to correct (for the plan author)

The plan says the picker observation was "operator-owned" and that typing into Zed and selecting its controls "remain operator-only". The observation in section 3 was made by Claude through computer use, at the operator's direction. Task 4 will also drive Zed through computer use unless the operator says otherwise. The plan text is left unchanged here; Task 5's doc-freshness pass should correct it.
