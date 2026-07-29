# Plan 11.6 — Local startup live evidence

**Plan:** `docs/superpowers/plans/2026-07-29-plan-11-6-p11-5-fu-2-local-startup-consolidation.md`
**Operator runbook:** `docs/runbooks/local-live-dependencies.md`
**Branch:** `agent/cursor/plan-11-6-local-startup-consolidation`
**Worktree:** `D:\Projects\Development\Python\optimus-cost-agent-wt-cursor`
**Evidence captured:** 2026-07-29 (UTC afternoon; Windows host + WSL2 Ubuntu 24.04)

## Digests and commits

| Item | Value |
|------|-------|
| Approved plan SHA-256 (freeze / implementation authorization) | `74CBE070C2CAA90C0D1D562F5DFE8CBA8C8F2839CD2CF1E9369E9A3D613B85C1` |
| Approval record SHA-256 | `F3456EAB59D7C292411668AEAF5DB0B1F9D49040F1A26340B52C2AD732D55153` |
| Plan file SHA-256 at evidence time (checkboxes progressed; Step 5 path note + `wt-cursor` command; Step 8 handoff; runbook relocated to `docs/runbooks/`) | `0210863356D5AE911F2B426EC67A444B146C2014BA969104D0438E7E436EAA43` |
| Implementation baseline | `origin/main` @ `9d95e6c` |
| HEAD at evidence start (Task 5 landed) | `ef3dbd819dbef30232d48a11cc10d8d16acf644f` |

**Implementation commits on branch (ahead of `origin/main`):**

1. `d123779` — `fix(acp): honor zero-env child startup contract`
2. `01f7849` — `fix(acp): reject ambiguous default Redis ownership`
3. `24158ce` — `feat(acp): auto-start local Phoenix for live evidence`
4. `1618591` — `refactor(acp): retire misleading local Gateway wrappers`
5. `ef3dbd8` — `docs: establish one local dependency startup runbook`
6. *(Task 6 evidence/backlog commit held for review)*

Durable approval used for live smoke: `appr_04598d8984f6104b07626c41` (operator-confirmed).

## Command taxonomy

| Class | What it proves | Commands / artifacts |
|-------|----------------|----------------------|
| **Non-live regression** | Unit/integration without claiming live deps | Step 1 selector → `184 passed, 6 skipped` |
| **Consolidated launcher (session-bound)** | Zero-Optimus shell; auto-start Redis+Phoenix+Gateway; cleanup | `uv run --frozen optimus-agent --workspace-root . --check-config --strict --with-local-phoenix` |
| **Conflict fail-closed** | Wrong Docker owner on 6379 | Isolated `plan116-conflict-redis` (`redis:7-alpine`) fixture |
| **Persistent Gateway ceremony** | Foreground `run-gateway --with-local-phoenix` | Terminal A (new console) PID 51728; Gateway child PIDs later stopped |
| **Direct-client live tiers** | Fixture env against Terminal A / ephemeral smoke GW | `requires_redis`, `requires_phoenix`, `requires_gateway`, `requires_live_gateway` |
| **External acpx (Windows)** | Independent `acpx` 0.12.0; PATH-only / zero OPTIMUS shell | `tools/run_plan115_acpx_cost_obs_evidence.py` + `--no-auto-start` capture |
| **WSL2 POSIX** | Focused projection + documented residual | Ubuntu 24.04; `wt-cursor` path; isolated `.venv-wsl` |

PATH note: host `optimus-agent` shims were stale (July). Live Windows evidence used
`uv run --frozen optimus-agent` / `optimus-trust` from this checkout (current `--with-local-phoenix`).

---

## Step 1 — Affected non-live tests

```text
uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py ... test_verify_live_agent_cli.py -q
→ 184 passed, 6 skipped
```

No Docker/keyring/Gateway/Phoenix/`acpx` fake presented as live evidence.

---

## Step 2 — Zero-env strict smoke (Windows)

Precondition: cleared `OPTIMUS_*` / `OTEL_*` for the command scope.
`optimus-trust --workspace-root . inspect` → Approval ID `appr_04598d8984f6104b07626c41`.

```text
uv run --frozen optimus-agent --workspace-root . --check-config --strict --with-local-phoenix
→ EXIT=0
→ created optimus-phoenix (arizephoenix/phoenix:latest)
→ started local gateway; "Optimus ACP agent configuration OK."
→ BOUNDARY_CLEAN (no sk-/OPENROUTER/OTEL_EXPORTER_OTLP_ENDPOINT/6006/v1/traces in agent output)
```

---

## Step 3 — Dependency identities and collision

### Named containers (after Step 2)

```text
optimus-redis     redis:8                         127.0.0.1:6379->6379/tcp
optimus-phoenix   arizephoenix/phoenix:latest     127.0.0.1:6006->6006/tcp
Phoenix /healthz → 200
```

### Image IDs / digests

| Name | Config.Image | Image ID |
|------|--------------|----------|
| `/optimus-redis` | `redis:8` | `sha256:2838d5524559494f6f1cd66e97e76b200d64a633a8614200620755ed395daf32` |
| `/optimus-phoenix` | `arizephoenix/phoenix:latest` | `sha256:3092f5543a3ddd35db7390cf971027c33be6be1f171274d57f3c8658c2193d67` |

Repo digests matched the same sha256 values via `docker image inspect`.

### Live wrong-owner fixture (owned containers only)

1. `docker stop optimus-redis`
2. `docker run -d --name plan116-conflict-redis -p 127.0.0.1:6379:6379 redis:7-alpine`
3. Zero-env `optimus-agent --workspace-root . --check-config --strict` → **EXIT=2**
4. stderr named `plan116-conflict-redis`, stated Optimus will not stop/delete the conflicting container; no “starting local gateway” side effect
5. Fixture removed; `docker start optimus-redis` restored (`redis:8` on 6379)

Typed code `REDIS_PORT_CONFLICT` is asserted in unit tests; live path prints `user_message` only (same exception).

---

## Step 4 — Persistent Gateway + live tiers + acpx

### Terminal A

Started in a real new console (no pipe) so TTY checks pass:

```text
uv run --frozen optimus-trust --workspace-root . run-gateway --with-local-phoenix
TerminalA powershell PID=51728 (alive during live tiers)
Gateway answered on :8765 (HTTP 501 on `/` = listening handler)
```

Shutdown after evidence:

```text
shutdown_attempt_utc=2026-07-29T13:19:41.1740675Z
stopped TerminalA powershell 51728; stopped optimus_gateway PIDs 58568, 57636
gateway down OK
shutdown_done_utc=2026-07-29T13:19:46.0182652Z
```

### Direct-client live pytest (Terminal B fixture env; secrets not recorded)

| Selector | Result |
|----------|--------|
| `tests/integration/agent/test_redis_live_agent.py -m requires_redis` | **7 passed** |
| `tests/integration/telemetry/test_phoenix_live.py -m requires_phoenix` | **1 passed** |
| `tests/integration/gateway/test_gateway_live.py -m requires_gateway` | first pass 1 flaky LLM failure (`PLANNING_UNPARSEABLE_RESPONSE`); retry of failed case + full module re-run → **4 passed** |
| `tests/integration/optimus_gateway/test_gateway_live_smoke.py -m requires_live_gateway` | **6 passed** (own ephemeral Gateway process; real OpenRouter) |

No skips in the selected live tiers above.

### External acpx (Windows)

Independent client: `C:\Users\pc\AppData\Roaming\npm\acpx` **0.12.0**.

1. **Consolidated-launcher tool** (opts into Phoenix):
   `tools/run_plan115_acpx_cost_obs_evidence.py` →
   [`reports/plan-11-6-local-startup-acpx-evidence.md`](plan-11-6-local-startup-acpx-evidence.md)
   - Zero `OPTIMUS_*` in operator shell before run
   - `agent_environment_names` = system PATH keys only (no Optimus names)
   - `exit_code: 0`, `capture_complete: true`, ACP initialize/session/prompt succeeded
   - Planning stopped with gateway cost-verification message; `cost_evidence_fields: []` recorded honestly

2. **Persistent-Gateway consumer**: `acpx … --agent "…/optimus-agent … --no-auto-start" exec …`
   - EXIT=0; ACP session completed; BOUNDARY_SCAN_OK
   - Same planning cost-verification stop observed against Terminal A

Gateway-only OTLP ownership remains: agent shell had no `OTEL_*`; Phoenix UI/health remained up for `requires_phoenix`.

---

## Step 5 — WSL2 (`wt-cursor`, not plan typo `wt-codex`)

```text
Distro: Ubuntu 24.04.1 LTS
Path: /mnt/d/Projects/Development/Python/optimus-cost-agent-wt-cursor
acpx: /mnt/c/Users/pc/AppData/Roaming/npm/acpx 0.12.0
```

Used isolated `UV_PROJECT_ENVIRONMENT=$PWD/.venv-wsl` after an earlier mistaken `.venv` clobber was restored on Windows (`uv sync --frozen --extra dev`; `.venv-wsl/` gitignored).

**Focused PATH-only projection:**

```text
env -i PATH=… uv run --frozen pytest tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_local_infra.py -q
→ 50 passed
```

**PATH-only external acpx** ([`reports/plan-11-6-local-startup-acpx-wsl-evidence.md`](plan-11-6-local-startup-acpx-wsl-evidence.md)):

```text
exit_code: 1
capture_complete: false
agent_environment_names: ["PATH"]
keyring backend: keyring.backends.fail.Keyring
error: NoKeyringError — No recommended backend was available (Linux SecretStorage/D-Bus)
```

**POSIX residual risk (explicit):** Linux zero-env keychain authentication is **unverified** on this host because the fail keyring backend cannot load HMAC/approval material. Windows success does **not** discharge that gap. Focused subprocess-env / local_infra unit projection on WSL **did** pass.

---

## Step 6 — Fitness and retirement gates

| Gate | Result |
|------|--------|
| `uv run --frozen pytest -q` | **1957 passed, 20 skipped, 56 deselected** |
| coverage `--cov-fail-under=80` | **87.51%** TOTAL (pass) |
| `uv run --frozen ruff check .` | All checks passed |
| `rg run_local_gateway\|docker run.*(redis\|arizephoenix)` on README/env/src/tests/tools | **Only** presence-test assertions in `test_plan116_local_startup_docs.py` |
| `rg run-gateway` on README / `.env.example` / `.env.gateway.example` | **No hits** (ceremony lives in runbook + CLI/tests) |
| `git diff --check` | Clean (CRLF normalization warnings only) |

---

## Secret / endpoint boundary proof

- Step 2 agent output: no provider key material; no OTLP endpoint string
- Windows acpx reports: agent env names exclude `OPTIMUS_*` / `OTEL_*`
- `.env.example` remains free of Phoenix/OTLP names (Plan 11.5 + 11.6 presence tests)
- Phoenix OTLP is Gateway-child-only when `--with-local-phoenix` is used

---

## Changed-file scope (Plan 11.6 implementation set)

Tasks 1–5 commits above. Task 6 adds evidence reports + backlog closure + `.gitignore` (`.venv-wsl/`) + plan checkbox progress. No Phase 1 “working” claim outside Plan 9.6 authority. No push/PR/merge performed by the implementing agent.

## Backlog

`P11.5-FU-2` closed against this evidence pack and implementation commits `d123779`…`ef3dbd8` (+ Task 6 commit when authorized).
