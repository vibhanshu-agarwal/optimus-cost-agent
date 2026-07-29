# Plan 11.6 — Local live dependencies operator runbook

> **Authority:** [Plan 11.6](2026-07-29-plan-11-6-p11-5-fu-2-local-startup-consolidation.md).
> This is the **single** living operator sequence for Redis, local Gateway, and local Phoenix.
> Competing README/`docker run` launcher instructions are retired; presence tests reject them.

**Parent:** [Plan 11.5 deferred follow-up `P11.5-FU-2`](2026-07-23-consolidated-deferred-followups-backlog.md)

---

## What this runbook proves

| Path | Credential policy | Dependency lifetime |
|------|-------------------|---------------------|
| **Persistent Gateway terminal** | Keychain / `.env.gateway` via `optimus-trust` | Foreground `run-gateway --with-local-phoenix` owns Gateway + Phoenix for the session |
| **Consumer terminal** | Zero Optimus shell vars required | `optimus-agent --no-auto-start` or external `acpx` against the persistent Gateway |
| **Bounded auto-start smoke** | Zero Optimus shell vars; durable approval required | Session-bound Redis (+ optional Phoenix) + Gateway started by `optimus-agent --check-config --strict` and cleaned up on exit |

No local provider keys. No agent-shell OTLP/Phoenix variables. Gateway-only OTLP when Phoenix is opted in.

---

## 1. Checkout and PATH provenance

Use the checkout that owns the branch under test (primary clone or this worktree). Reinstall the PATH binary from that checkout so `where.exe optimus-agent` / `where.exe optimus-trust` resolve to it:

```powershell
uv tool install . --reinstall
uv tool update-shell
where.exe optimus-agent
where.exe optimus-trust
```

Open a **new** terminal after install. Reject `.venv\Scripts\…` and stale `~\.local\bin` shims.

---

## 2. Zero-Optimus-shell precondition

In every terminal used below, clear inherited Optimus names for the command scope:

```powershell
Get-ChildItem Env:OPTIMUS_* | Remove-Item
```

Confirm none remain:

```powershell
Get-ChildItem Env:OPTIMUS_*
```

**No repo-root `.env` is required** for the agent path once keychain credentials and durable approval exist. Do not export `OTEL_EXPORTER_OTLP_ENDPOINT` into the agent shell.

---

## 3. Keychain credentials

```powershell
optimus-trust setup-credentials
```

Store the OpenRouter provider key and local shared secret in the OS keychain (or keep them in the operator config-root `.env.gateway` / checkout `.env.gateway` as data for `run-gateway` — never `source`d into the interactive shell).

---

## 4. Durable workspace approval

```powershell
optimus-trust --workspace-root . approve --mode durable
```

Authoring requires an interactive TTY. Inspect without secrets:

```powershell
optimus-trust --workspace-root . inspect
```

---

## 5. Bounded session-bound smoke (Redis + Gateway, optional Phoenix)

From a zero-Optimus shell with approval present:

```powershell
optimus-agent --workspace-root . --check-config --strict
```

With local Phoenix for live evidence:

```powershell
optimus-agent --workspace-root . --check-config --strict --with-local-phoenix
```

Expected: exit 0; named containers `optimus-redis` (`redis:8`) and, when opted in, `optimus-phoenix` (`arizephoenix/phoenix:latest`); Gateway auth probe succeeds; no provider key or OTLP endpoint appears in agent output. This path **starts and stops** session-bound Gateway (and does not leave a persistent Gateway for consumers).

---

## 6. Persistent Gateway / Phoenix terminal + consumer terminal

**Terminal A — persistent ceremony (blocks until Ctrl-C):**

```powershell
optimus-trust --workspace-root . run-gateway --with-local-phoenix
```

This foreground process:

- parses checkout `.env.gateway` as untrusted key=value data (never `source`d);
- optionally ensures `optimus-phoenix` and injects `OTEL_EXPORTER_OTLP_ENDPOINT` into the **Gateway child only**;
- keeps the Gateway alive until you stop the terminal.

**Terminal B — consumer (zero Optimus shell vars):**

```powershell
optimus-agent --workspace-root . --no-auto-start
```

Or drive the same agent with an independently authored external `acpx` client whose agent command includes `optimus-agent --no-auto-start`. Do not start a second Gateway from Terminal B.

---

## 7. Real evidence commands

With Terminal A still alive, from Terminal B (or a third shell) supply only the fixture variables each live tier already documents (`OPTIMUS_REDIS_URL`, one-key Gateway URL/API key, Phoenix query/OTLP values for direct Phoenix tests). Those are regression-fixture inputs, not proof that the agent needs shell variables for normal operation.

```powershell
uv run --frozen pytest tests/integration/agent/test_redis_live_agent.py -m requires_redis -q
uv run --frozen pytest tests/integration/telemetry/test_phoenix_live.py -m requires_phoenix -q
uv run --frozen pytest tests/integration/gateway/test_gateway_live.py -m requires_gateway -q
uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -m requires_live_gateway -q
```

External `acpx` cost-observability capture (separate consolidated-launcher exercise; opts into Phoenix itself):

```powershell
uv run --frozen python tools/run_plan115_acpx_cost_obs_evidence.py --workspace . --task "Return a one-sentence cost-observability smoke result." --report reports/plan-11-6-local-startup-acpx-evidence.md
```

Stop Terminal A with Ctrl-C only after Gateway / `acpx` / direct-client evidence is collected.

---

## 8. Named containers, health URLs, lifetime distinction

| Dependency | Name | Image | Health / reference |
|------------|------|-------|--------------------|
| Redis | `optimus-redis` | `redis:8` | `redis://127.0.0.1:6379/0` |
| Phoenix | `optimus-phoenix` | `arizephoenix/phoenix:latest` | UI `http://127.0.0.1:6006`, OTLP `http://127.0.0.1:6006/v1/traces`, `/healthz` |
| Gateway | local `optimus_gateway` child | n/a | `http://127.0.0.1:8765` (persistent via Terminal A; session-bound under strict check-config) |

**Persistent `run-gateway` lifetime** keeps Gateway (and Phoenix when opted in) until Ctrl-C.
**Session-bound agent auto-start** starts Redis (+ optional Phoenix) + Gateway for that process and cleans Gateway up on exit; it is not a substitute for Terminal A when live Gateway consumers need a long-lived peer.

---

## 9. Default-port conflict diagnosis

When the default Redis URL `redis://127.0.0.1:6379/0` is already reachable, Optimus probes Docker publish ownership:

```powershell
docker ps --filter publish=6379 --format "{{.Names}}`t{{.Image}}"
```

- Exact owner `optimus-redis` / `redis:8` → reuse.
- Different Docker name/image → typed `REDIS_PORT_CONFLICT` (fail closed; no Gateway start).
- Reachable with no Docker owner (native Redis / operator-managed) → log and continue.
- Docker missing/unreachable with a conflicting publish probe path → follow the typed error text.

**Optimus never stops or deletes the conflicting container.**

---

## 10. Non-destructive recovery

If you see `REDIS_PORT_CONFLICT` (or Phoenix port/image conflict):

1. Stop or reconfigure the unrelated project **yourself**, then retry; or
2. Explicitly configure a custom `OPTIMUS_REDIS_URL` (non-default port), re-run durable approval if the launch policy snapshot requires it, and retry.

Do not ask Optimus to kill foreign containers.

---

## 11. Restore shell-only test variables

After live pytest / evidence shells:

```powershell
Get-ChildItem Env:OPTIMUS_* | Remove-Item
Get-ChildItem Env:PHOENIX_* | Remove-Item -ErrorAction SilentlyContinue
Get-ChildItem Env:OTEL_* | Remove-Item -ErrorAction SilentlyContinue
```

Restore any renamed `.env` / operator `.env.gateway` backups only if you moved them aside for a zero-env proof.

---

## Quick reference

| Goal | Command |
|------|---------|
| Credentials | `optimus-trust setup-credentials` |
| Approve workspace | `optimus-trust --workspace-root . approve --mode durable` |
| Bounded smoke | `optimus-agent --workspace-root . --check-config --strict [--with-local-phoenix]` |
| Persistent Gateway+Phoenix | `optimus-trust --workspace-root . run-gateway --with-local-phoenix` |
| Consumer agent | `optimus-agent --workspace-root . --no-auto-start` |
