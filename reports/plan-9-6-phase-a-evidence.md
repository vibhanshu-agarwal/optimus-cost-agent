# Plan 9.6 Phase A evidence

**Date:** 2026-07-10
**Checkout:** `optimus-cost-agent-wt-cursor` @ `main` (`0ca83f8`, post-PR #38)
**Operator:** Cursor agent shell (Windows)

## First live blocker — disposition

**Original symptom:** `OPTIMUS_API_KEY was rejected by the gateway.` on `--check-config --strict`
(operator interactive session, earlier in investigation).

**Mechanism:** Code-confirmed cross-layer shared-secret mismatch (shell env outranks keyring for
agent; gateway resolves env → `.env.gateway` → keyring).

**Probable root cause (unconfirmed):** Stale session `OPTIMUS_API_KEY` from the pre-PR #38 Phase A2
instruction (`$env:OPTIMUS_API_KEY = "<your key>"`). The failing session's environment was never
captured, so this cannot be proven — only consistent with the mechanism.

**Re-run outcome:** All four credential layers verified clean; keyring backfill authenticated
successfully against loopback gateway on `:8765`.

## Layer checks (re-run)

| Layer | Result |
|-------|--------|
| User-scope `OPTIMUS_API_KEY` | empty |
| User-scope `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET` | empty |
| Session env (both vars) | not set |
| `.env` / `.env.gateway` in workspace | absent |
| Keyring backfill | yes (`resolved_api_key_len` 43) |

## Per-step results

| Step | Command | Result |
|------|---------|--------|
| A1 | `docker ps --filter name=optimus-redis` | `optimus-redis Up 22 hours` |
| A2 | key-leak grep | no `OPTIMUS_*` or provider keys in session |
| A3 | default Redis URL | `redis://127.0.0.1:6379/0` (default) |
| A4 non-strict | `python -m optimus.acp --workspace-root . --check-config` | exit **0** |
| A4 strict | `python -m optimus.acp --workspace-root . --check-config --strict` | exit **0** |
| A5 | Redis PING | `PING True` |

**Gateway note (preflight only):** Port `8765` was already listening from a prior session; sufficient
for strict preflight. Phase B/D require a fresh gateway restart from current `main` (see Phase B
evidence).

## Preflight table (strict)

```
Check                Status  Detail
-------------------------------------
gateway credentials  PASS    present
redis url            PASS    redis://127.0.0.1:6379/0
redis connectivity   PASS    PING ok
redis timeseries     PASS    TS.ADD ok
gateway auth         PASS    auth probe accepted
workspace writable   PASS    D:\Projects\Development\Python\optimus-cost-agent-wt-cursor
```

## Safe snapshot (after `apply_local_defaults`)

```
resolved_gateway_host  127.0.0.1
resolved_gateway_port  8765
resolved_api_key_set   True
resolved_api_key_len   43
keyring_backfill       True
```
