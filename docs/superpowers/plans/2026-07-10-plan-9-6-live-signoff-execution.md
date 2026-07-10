# Plan 9.6 Live Sign-Off — Execution Checklist

> **For operators:** This is the Phase 1 working-agent gate. Checkboxes may be set to `[x]` only
> after the stated verification command actually ran and passed on the operator machine. Prose
> claims count for nothing (AGENTS.md checkbox protocol).

**Parent plan:** [Plan 9.6](2026-07-07-plan-9-6-live-verification-and-lld-alignment.md)
**Evidence:** [Phase A](reports/plan-9-6-phase-a-evidence.md)

## Claim → Evidence status (8 rows)

| # | DoD claim | Evidence artifact | Status |
|---|-----------|-------------------|--------|
| 1 | Redis-backed plan state | `test_redis_live_agent.py` green | `[x]` |
| 2 | Bootstrap fails closed | `test_bootstrap_live_redis.py` green | `[x]` |
| 3 | LLD §10 telemetry on real Redis | `test_redis_telemetry_live.py` green | `[x]` |
| 4 | ACP server persist/replay | `test_server_stream_live_redis.py` green | `[x]` |
| 5 | Real model honors directive prompt | `test_gateway_live.py` green | `[x]` |
| 6 | IDE-spawnable agent E2E | `test_spawned_agent_live.py` + `reports/plan-9-6-e2e-acp-transcript.json` | `[ ]` |
| 7 | Operator verify alone | `tools/verify_live_agent.py` exit 0 + transcript | `[ ]` |
| 8 | Real IDE (Zed HITL) | `reports/plan-9-75-zed-hitl-runtime-evidence.md` | `[x]` (PR #36) |

Default `pytest` excludes live tiers (`requires_redis`, `requires_gateway`, `e2e`). Every live
row requires an **explicit** marker run — passing unit tests alone does not satisfy any row.

## Phase 0 — Doc integrity (no infra)

- [x] **Revert premature Plan 9.7 manual DoD checkbox** — PR #35 (`8ed90ab`) falsely marked the
  operator PATH walkthrough complete while `reports/plan-9-7-manual-e2e-evidence.md` remains blank.
  Restored `[ ]` and accurate remaining-gate note on this branch.

## Phase A — Infra prep (operator machine)

**Credentials policy:** Only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the environment for
agent runs during live-tier pytest (Phases B/D). Phase C (keychain-only walkthrough) requires zero
`OPTIMUS_*` in the shell — see Phase C. No local provider keys at any tier.

### First live blocker (2026-07-10): cross-layer shared-secret mismatch

**Symptom:** `OPTIMUS_API_KEY was rejected by the gateway.` on `--check-config --strict` after Redis
checks pass (401/403 on preflight auth probe).

**Mechanism (code-confirmed):** Agent `OPTIMUS_API_KEY` is filled from shell env when non-empty
(`local_infra.py` — env outranks keyring). Auto-started local gateway auth uses
`resolve_shared_secret` (env → `.env.gateway` → keyring). A stale value in **any** layer can make
the agent authenticate with secret A while the gateway expects secret B. Stale values can live in
shell session env, Windows User-scoped persistent env, or `.env.gateway`. This is the parked
**cross-layer provider/key mismatch** gap from Plan 9.7 review (deferred to Plan 10+ broker work);
Phase A surfaced it in production.

**Disposition (2026-07-10):** Resolved on re-run. Most likely stale session env from the pre-#38 A2
instruction (unconfirmed — failing session not captured); all four layers verified clean on re-run,
keyring backfill authenticated successfully. Evidence:
`reports/plan-9-6-phase-a-evidence.md`.

**Resolution order before A4:** clean all four layers, then let keyring supply the secret (local
loopback path). **Run the env-cleanup steps in every terminal** you will use (preflight terminal
*and* gateway terminal) — file renames are workspace-wide; env vars are per-session.

- [x] **A0. Clear stale credential layers** — evidence:
  [reports/plan-9-6-phase-a-evidence.md](reports/plan-9-6-phase-a-evidence.md). Commands:
  ```powershell
  # Layer 1 — Windows User-scoped persistent env
  [Environment]::GetEnvironmentVariable('OPTIMUS_API_KEY','User')
  [Environment]::GetEnvironmentVariable('OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET','User')
  [Environment]::SetEnvironmentVariable('OPTIMUS_API_KEY',$null,'User')
  [Environment]::SetEnvironmentVariable('OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET',$null,'User')
  # Layer 2 — session env (each terminal)
  Remove-Item Env:OPTIMUS_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET -ErrorAction SilentlyContinue
  # Layer 3 — workspace dotenv
  Rename-Item .env .env.bak -ErrorAction SilentlyContinue
  Rename-Item .env.gateway .env.gateway.bak -ErrorAction SilentlyContinue
  ```

- [x] **A0b. Local gateway for preflight** — port `8765` was already listening (prior session);
  sufficient for strict preflight only. **Before B2 and Phase D:** kill and restart gateway from
  current `main` checkout (provenance — see Phase B).

If A4 still fails with all layers clean (no User-scope vars, empty session env in both terminals,
no `.env`/`.env.gateway`, keyring-only), treat as a possible **auth-path defect** (preflight probe
vs real planning) — capture the preflight table and safe env snapshot below and escalate.

- [x] **A1. Docker Desktop running** — `optimus-redis Up 22 hours` (evidence file).
  ```powershell
  docker ps --filter name=optimus-redis
  ```

- [x] **A2. Gateway URL** — loopback default; no provider keys in session (evidence file).
  ```powershell
  Get-ChildItem Env: | Where-Object { $_.Name -match 'OPTIMUS|OPENAI|ANTHROPIC|OPENROUTER|GLM|TAVILY|ZHIPUAI|LANGSMITH|LANGCHAIN' }
  ```

- [x] **A3. Redis URL** — default `redis://127.0.0.1:6379/0` (evidence file).

- [x] **A4. Preflight passes** — non-strict and strict exit 0 (evidence file).
  ```powershell
  python -m optimus.acp --workspace-root . --check-config --strict
  ```
  On auth failure, capture preflight table + resolved safe snapshot:
  ```powershell
  python -c "
from pathlib import Path
import os
from optimus.acp.__main__ import _project_root
from optimus.acp.local_infra import apply_local_defaults, strip_local_provider_keys
from optimus.acp.preflight import collect_preflight_checks, format_preflight_table
from urllib.parse import urlparse
env = apply_local_defaults(os.environ, project_root=_project_root())
agent = strip_local_provider_keys(env)
print(format_preflight_table(collect_preflight_checks(agent, workspace_root=Path('.'), strict=True, require_timeseries=True)))
p = urlparse(env.get('OPTIMUS_GATEWAY_URL',''))
k = env.get('OPTIMUS_API_KEY','')
print('resolved_gateway_host', p.hostname)
print('resolved_gateway_port', p.port)
print('resolved_api_key_set', bool(k.strip()))
print('resolved_api_key_len', len(k.strip()))
print('keyring_backfill', not bool(os.environ.get('OPTIMUS_API_KEY','').strip()) and bool(k.strip()))
"
  ```

- [x] **A5. Live Redis reachable** — `PING True` (evidence file).

## Phase B — Live-tier pytest (`requires_redis`, then `requires_gateway`)

Run from repo checkout with Phase A env active. Capture full stdout/stderr per tier.

**Gateway provenance (before B2 and Phase D):** Kill any process on `127.0.0.1:8765` and restart
from the current checkout so live-tier evidence is not against an unknown older build:
```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
python -c "
import os
from pathlib import Path
from optimus.acp.local_infra import apply_local_defaults, ensure_local_gateway
root = Path('.').resolve()
env = apply_local_defaults(os.environ, project_root=root)
proc = ensure_local_gateway(environ=env, project_root=root, log=print)
print('gateway_pid', proc.process.pid if proc else None)
"
```

- [x] **B1. `requires_redis`** — 15/15 passed; evidence
  [reports/plan-9-6-phase-b-evidence.md](reports/plan-9-6-phase-b-evidence.md). Required one
  integration-test fix for post-#36 permission `run_id` shape.

- [x] **B2. `requires_gateway`** — 3/3 passed after gateway restart (pid 36952); same evidence
  file.

**Phase B pass criteria:** All selected tests green. Any failure is a ship-blocker until root-caused.

## Phase D — Automated E2E + operator verify (before manual walkthrough)

Cheaper failure discovery than burning a manual walkthrough on a broken stack.

- [ ] **D1. `e2e` spawned agent** (row 6):
  ```powershell
  pytest tests/e2e/acp/test_spawned_agent_live.py -m e2e -v
  ```
  Confirm/update committed `reports/plan-9-6-e2e-acp-transcript.json` if the test regenerates it.

- [ ] **D2. `verify_live_agent.py`** (row 7):
  ```powershell
  python tools/verify_live_agent.py --workspace-root <scratch-dir>
  ```
  Confirm/update `reports/plan-9-6-live-agent-transcript.json` (or path documented by tool).

**Phase D pass criteria:** Exit 0 on D2; D1 green with committed transcript artifacts current for `main`.

## Phase C — Manual operator walkthrough (Plan 9.7 template)

Only after Phase D passes (or failures are understood and fixed). Fill every section of
`reports/plan-9-7-manual-e2e-evidence.md` — replace every `(paste)` placeholder with real output.

- [ ] **C1. Preconditions** — clean shell, no venv, no `OPTIMUS_*` in env, `.env` renamed away.
- [ ] **C2. PATH install** — `uv tool install --editable .` + `where.exe optimus-agent` output pasted.
- [ ] **C3. Keychain setup** — `optimus-agent --setup` (stderr pasted, secrets redacted).
- [ ] **C4. Config check** — `optimus-agent --workspace-root . --check-config`.
- [ ] **C5. Serve + planning call** — real `claude-haiku` turn through auto-started stack; gateway log tail pasted.
- [ ] **C6. Sign-off checkboxes** in the evidence file all checked with date/signature.

**Phase C pass criteria:** `reports/plan-9-7-manual-e2e-evidence.md` fully filled; Plan 9.7 DoD
checkbox may then be set `[x]` in a follow-up commit citing this file.

## Phase E — Zed re-confirm on current `main`

Row 8 is already closed by Plan 9.75, but confirm no regression on post-merge `main`.

- [ ] **E1. Fresh Zed session** — one planning turn with `--debug-trace` optional; confirm plan +
  approval UI + `end_turn` or explicit cancel.
- [ ] **E2. Record** — append a short "post-#36/#35 regression" note to
  `reports/plan-9-75-zed-hitl-runtime-evidence.md` or a new dated section if behavior differs.

## Phase F — Sign-off commit

- [ ] **F1.** All claim-table rows `[x]` with artifact paths cited in Plan 9.6.
- [ ] **F2.** Plan 9.7 manual DoD checkbox `[x]` only after Phase C evidence file is filled.
- [ ] **F3.** Plan 9.75 Task 5 `[x]` only after F1 + F2.
- [ ] **F4.** `python -m ruff check .` clean; default `pytest -q` green.
- [ ] **F5.** PR opened; reviewer verifies artifacts on disk, not agent prose.

## Notes

- **debug_trace:** Keep env-gated instrumentation; Plan 9.8 DoD requires `debug-acp.ndjson`
  correlation. Optional rename pass for `hypothesis_id` / `run_id` labels — not blocking.
- **Existing transcripts:** `reports/plan-9-6-e2e-acp-transcript.json` and
  `reports/plan-9-6-live-agent-transcript.json` exist on `main` but must be re-validated against
  current code in Phases B/D before counting as evidence.
- **Backlog (after Phase A green, not a detour now):** Preflight auth failure should report which
  layer supplied `OPTIMUS_API_KEY` vs gateway shared secret (env / `.env.gateway` / keyring) and
  whether lengths differ — diagnostic only, no secret bytes. Small standalone item; does not require
  full Plan 10 gateway-broker scope. Strongest argument for pulling the parked Plan 9.7
  cross-layer mismatch warning forward.
