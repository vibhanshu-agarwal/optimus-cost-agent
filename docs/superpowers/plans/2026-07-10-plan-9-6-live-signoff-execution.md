# Plan 9.6 Live Sign-Off — Execution Checklist

> **For operators:** This is the Phase 1 working-agent gate. Checkboxes may be set to `[x]` only
> after the stated verification command actually ran and passed on the operator machine. Prose
> claims count for nothing (AGENTS.md checkbox protocol).

**Parent plan:** [Plan 9.6](2026-07-07-plan-9-6-live-verification-and-lld-alignment.md)  
**Branch:** `agent/cursor/plan-9-6-live-signoff`  
**Base:** `main` @ post-PR #35 (`7304644`)

## Claim → Evidence status (8 rows)

| # | DoD claim | Evidence artifact | Status |
|---|-----------|-------------------|--------|
| 1 | Redis-backed plan state | `test_redis_live_agent.py` green | `[ ]` |
| 2 | Bootstrap fails closed | `test_bootstrap_live_redis.py` green | `[ ]` |
| 3 | LLD §10 telemetry on real Redis | `test_redis_telemetry_live.py` green | `[ ]` |
| 4 | ACP server persist/replay | `test_server_stream_live_redis.py` green | `[ ]` |
| 5 | Real model honors directive prompt | `test_gateway_live.py` green | `[ ]` |
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
agent runs. No local provider keys.

- [ ] **A1. Docker Desktop running** — Redis auto-start depends on it.
  ```powershell
  docker ps --filter name=optimus-redis
  ```

- [ ] **A2. Gateway credentials set** (new terminal; redact secrets in evidence paste):
  ```powershell
  $env:OPTIMUS_GATEWAY_URL = "<your gateway url>"
  $env:OPTIMUS_API_KEY = "<your key>"
  # Confirm no other OPTIMUS_* or provider keys leak:
  Get-ChildItem Env: | Where-Object { $_.Name -match 'OPTIMUS|OPENAI|ANTHROPIC|OPENROUTER' }
  ```

- [ ] **A3. Redis URL** (if not auto-defaulted):
  ```powershell
  $env:OPTIMUS_REDIS_URL = "redis://127.0.0.1:6379/0"
  ```

- [ ] **A4. Preflight passes** (from repo checkout):
  ```powershell
  cd <repo-checkout>
  python -m optimus.acp --workspace-root . --check-config --strict
  ```
  Record exit code and stderr (no secrets).

- [ ] **A5. Live Redis reachable** (TimeSeries-capable):
  ```powershell
  python -c "import redis; r=redis.from_url('redis://127.0.0.1:6379/0'); print('PING', r.ping())"
  ```

**Phase A pass criteria:** A4 exit 0, A5 prints `PING True`. Report pass/fail + command output.

## Phase B — Live-tier pytest (`requires_redis`, then `requires_gateway`)

Run from repo checkout with Phase A env active. Capture full stdout/stderr per tier.

- [ ] **B1. `requires_redis`** (rows 1–4):
  ```powershell
  pytest tests/integration/agent/test_redis_live_agent.py `
    tests/integration/acp/test_bootstrap_live_redis.py `
    tests/integration/telemetry/test_redis_telemetry_live.py `
    tests/integration/acp/test_server_stream_live_redis.py `
    -m requires_redis -v
  ```

- [ ] **B2. `requires_gateway`** (row 5):
  ```powershell
  pytest tests/integration/gateway/test_gateway_live.py -m requires_gateway -v
  ```

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
