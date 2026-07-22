# Plan 9.6 Phase C — Operator PATH walkthrough runbook

> **Human-gated.** Cursor cannot run this for you. Schedule one uninterrupted sitting (~30–45 min).
> **Output artifact:** every `(paste)` in
> [`reports/plan-9-7-manual-e2e-evidence.md`](../../../reports/plan-9-7-manual-e2e-evidence.md)
> replaced with real command output (secrets redacted).

**Parent:** [Execution checklist](2026-07-10-plan-9-6-live-signoff-execution.md) · [Plan 9.6](2026-07-07-plan-9-6-live-verification-and-lld-alignment.md)

**Status:** Completed. Evidence captured in
[`reports/plan-9-7-manual-e2e-evidence.md`](../../../reports/plan-9-7-manual-e2e-evidence.md) —
every `(paste)` placeholder replaced with real command output. This runbook predates this project's
per-step checkbox-tracking convention, so its own checklist items below were never intended to be
individually ticked; the evidence report is the completion record.

**Prerequisite:** Phase D merged on `main` (PR #40, commit `8aa9776` or later). Rows 6–7 closed.

---

## What Phase C proves (vs Phases B/D)

| Tier | Credential policy | Install path |
|------|-------------------|--------------|
| **B / D** (pytest live) | `OPTIMUS_GATEWAY_URL` + `OPTIMUS_API_KEY` allowed in shell (keyring backfill OK) | Repo checkout + `python -m pytest` / `tools/verify_live_agent.py` |
| **C** (this runbook) | **Zero `OPTIMUS_*` in shell** — keychain-only | Global PATH binary via `uv tool install . --reinstall` (non-editable, per Plan 9.9) |

Phase C is stricter than Phase A0/B/D. Do **not** copy Phase B's two-var env wrapper here. The agent
must resolve gateway URL and API key from keyring + defaults after `optimus-agent --setup`, with no
shell shortcuts.

---

## Before you start — checkout and PATH provenance

Use the **primary clone** (`optimus-cost-agent`), which owns `main`. Agent worktrees
(`optimus-cost-agent-wt-*`) cannot `git checkout main` when the primary clone already has it
checked out — Git will refuse with a worktree conflict.

### 1. Update primary clone to post-#40 `main`

```powershell
cd D:\Projects\Development\Python\optimus-cost-agent   # primary clone, owns main
git pull origin main                                   # e.g. 0ca83f8 → 8aa9776+
git rev-parse HEAD                                     # expect 8aa9776 or later (PR #40 merge)
```

Phase C tests the **operator install path** from the canonical `main` checkout, not a feature
worktree that happens to be on the right commit.

### 2. Reinstall PATH binary from this checkout

```powershell
uv tool install . --reinstall
uv tool update-shell
```

Plan 9.9 established the non-editable install as the operator contract: this builds a wheel from
the checkout and installs it into an isolated `uv`-managed environment rather than linking back to
`src/`.

**Open a brand-new terminal** (and restart IDE if integrated terminals were open during install —
JetBrains/Cursor cache PATH from launch).

### 3. Verify PATH — no stale shim

```powershell
where.exe optimus-agent
```

**Expected:**

- `uv` tool bin dir **or** `Roaming\Python\Python*\Scripts\optimus-agent.exe`
- Resolves to the checkout you just built

**Reject (documented failure modes on this machine):**

- `.venv\Scripts\optimus-agent.exe` — venv path, not operator PATH
- `C:\Users\<you>\.local\bin\optimus-agent.exe` — stale shim missing `keyring` (README Troubleshooting)
- A path pointing at an old feature branch worktree

If a broken `.local\bin` shim exists, rename it before continuing:

```powershell
Rename-Item "$env:USERPROFILE\.local\bin\optimus-agent.exe" "optimus-agent.exe.bak" -ErrorAction SilentlyContinue
```

Paste `where.exe` output into the evidence template **before** IDE launch.

---

## C0 — Credential cleanup (Phase-C-specific)

Phase A0's four-layer cleanup still applies, but the **success criterion differs**:

| Layer | Phase A0 / B action | Phase C requirement |
|-------|---------------------|---------------------|
| 1 — Windows User-scope env | Clear `OPTIMUS_API_KEY`, `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` | Must remain empty |
| 2 — Session env | `Remove-Item Env:OPTIMUS_*` in **this** terminal | **All** `OPTIMUS_*` absent — not just API key |
| 3 — Workspace `.env` | Rename `.env` to `.bak` (see commands below) | Absent during C4/C5; **restore after C6** |
| 4 — Operator config root `.env.gateway` | Inspect the resolved config root (`%APPDATA%\optimus-cost-agent\.env.gateway` by default, or your `OPTIMUS_CONFIG_ROOT` override); migrate/rename it aside if present | Absent during C4/C5; **restore after C6** — under Plan 9.9, `optimus-agent` resolves `.env.gateway` from this operator-owned root only and never reads a checkout-root `.env.gateway` |
| 5 — Keyring | Keyring supplies secret when shell env empty | **This is the intended path** — run `--setup` if unsure |

**Phase C precondition check** (run in the clean terminal you will use for C2–C5):

```powershell
# Must be empty
$env:VIRTUAL_ENV
Get-ChildItem Env: | Where-Object { $_.Name -match '^OPTIMUS_' }
# Rename the workspace .env away for the walkthrough (restore after C6 — see below)
Rename-Item .env .env.bak -ErrorAction SilentlyContinue
Test-Path .env

# Inspect the resolved operator config root — optimus-agent reads .env.gateway from HERE only,
# never from the checkout, so only this file (if present) can defeat the keychain-only proof
$configRoot = if ($env:OPTIMUS_CONFIG_ROOT) { $env:OPTIMUS_CONFIG_ROOT } else { Join-Path $env:APPDATA 'optimus-cost-agent' }
$configEnvGateway = Join-Path $configRoot '.env.gateway'
Test-Path $configEnvGateway
# If it exists, migrate it aside for a clean keychain-only proof (restore after C6):
Rename-Item $configEnvGateway "$configEnvGateway.bak" -ErrorAction SilentlyContinue
```

**Pass:** `$env:VIRTUAL_ENV` empty; zero `OPTIMUS_*` session vars; workspace `.env` not present;
the resolved operator config root's `.env.gateway` absent or explicitly migrated aside.

**Fail:** Any `OPTIMUS_*` in session or User scope — stop and clean before continuing. Shell env
outranks keyring (`local_gateway_secrets.py`); a leftover `OPTIMUS_API_KEY` or a stray operator
config root `.env.gateway` breaks the keychain-only proof.

---

## C1 — Preconditions (evidence template § Preconditions)

- [ ] New terminal, no venv
- [ ] Zero `OPTIMUS_*` in session (verified above)
- [ ] Checkout `.env` renamed away; operator config-root `.env.gateway` migrated aside (or absent)
- [ ] Docker Desktop running: `docker ps --filter name=optimus-redis`
- [ ] Stale `.local\bin` shim handled if present

Check the precondition boxes in the evidence file.

---

## C2 — PATH install (evidence template § 1)

Already done in **Before you start** if you followed provenance steps. Paste:

```powershell
where.exe optimus-agent
```

into the template. Record checkout SHA alongside it (provenance).

---

## C3 — Keychain setup (evidence template § 2)

```powershell
optimus-agent --setup
```

Paste stderr (redact secrets). This seeds keyring entries the agent will use with **no** shell vars.

---

## C4 — Config check (evidence template § 3)

Use a workspace directory for the walkthrough (repo root is fine **after** dotenv rename):

```powershell
optimus-agent --workspace-root . --check-config
```

Paste exit code and stderr. Non-zero here is a ship-blocker — capture full output and stop.

Optional strict probe (not required by template, useful if auth fails):

```powershell
optimus-agent --workspace-root . --check-config --strict
```

---

## C5 — Serve + planning call (evidence template § 4)

**Goal:** One real planning turn on `claude-haiku` through the auto-started loopback stack.

```powershell
optimus-agent --workspace-root .
```

In Zed (or another ACP client), configure agent command as `"optimus-agent"` only — no venv wrapper,
no extra env injection. Trigger a simple planning task (e.g. docstring on `example.py`).

**Evidence to capture:**

- Session behaved correctly (plan → approval → tool execution or cancel)
- Tail of `.optimus/local-gateway.log` (redact secrets)

```powershell
Get-Content .optimus/local-gateway.log -Tail 40
```

**Singleton ownership note (Plan 9.9):** this log only exists if *this* workspace started the
loopback gateway. If a gateway was already reachable on the configured port (for example a prior
`optimus-agent` session still running), this workspace reuses that process and does **not** create
its own `.optimus/local-gateway.log` — tail the log under the workspace that originally started
it, or stop that process first if you need a fresh log for this walkthrough.

Confirm the model call shows `claude-haiku` (not a stale model override from env).

---

## C6 — Sign-off (evidence template § 5)

Check all five boxes in the template. Fill **Recorded by** and **Date**.

**Phase C pass criteria:** `reports/plan-9-7-manual-e2e-evidence.md` has no remaining `(paste)`
placeholders; all checkboxes `[x]`.

### C6b — Restore workspace dotenv (after evidence is saved)

The clean-state claim in the evidence file applies **through C6 only**. Restore local dev config
so the next session in this checkout does not hit missing-config surprises:

```powershell
Rename-Item .env.bak .env -ErrorAction SilentlyContinue
$configRoot = if ($env:OPTIMUS_CONFIG_ROOT) { $env:OPTIMUS_CONFIG_ROOT } else { Join-Path $env:APPDATA 'optimus-cost-agent' }
$configEnvGateway = Join-Path $configRoot '.env.gateway'
if (Test-Path "$configEnvGateway.bak") {
    Rename-Item "$configEnvGateway.bak" $configEnvGateway -ErrorAction SilentlyContinue
}
```

Note the restore date in the evidence file (e.g. under **Recorded by**) so reviewers know when the
keychain-only window ended.

---

## After Phase C

| Next | What |
|------|------|
| **Phase E** | One fresh Zed session on current `main`; append regression note to Plan 9.75 evidence |
| **Phase F** | Sign-off commit: claim table 8/8, Plan 9.7 DoD `[x]`, Plan 9.75 Task 5 `[x]`, ruff + pytest |
| **Plan 9.8** | Natural next implementation lane (context-floor fix, already drafted) |

---

## Failure triage (ship-blocker)

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `OPTIMUS_API_KEY was rejected by the gateway` | Stale shell or User-scope key | Re-run C0; verify zero `OPTIMUS_*` before `optimus-agent --setup` |
| `ModuleNotFoundError: keyring` | Stale `.local\bin` shim | `where.exe optimus-agent`; reinstall with `uv tool install . --reinstall` |
| Wrong checkout / old behavior | PATH points at old worktree | Reinstall from post-#40 `main`; re-verify `where.exe` |
| Config check fails, keyring empty | Skipped `--setup` | Run `optimus-agent --setup` (C3) |
| `Refusing to load local gateway configuration from ... because it is inside workspace ...` | `OPTIMUS_CONFIG_ROOT` points at or under the workspace | Follow the error's own remediation exactly: move `.env.gateway` to the displayed safe operator config directory, or set `OPTIMUS_CONFIG_ROOT` to an absolute directory outside the workspace |
| `optimus-agent: local gateway provider resolves to ... but the keyring API key is paired with provider ...` | Provider/key mismatch across configuration layers | Run `optimus-agent --setup` to re-pair provider and key, or remove the higher-precedence override named in the message |
| Doubt whether the installed binary is really non-editable / outside the repo | Want to re-verify the packaging contract itself | Run Task 4's package verifier: `python tools/verify_plan99_noneditable_install.py --wheel-dir <dist-dir> --scratch-root <scratch-dir>` |
| Gateway not starting | Docker not running | `docker ps --filter name=optimus-redis` |

Capture command output in the evidence file or a scratch note — prose claims do not satisfy the gate.
