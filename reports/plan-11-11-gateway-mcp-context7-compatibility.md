# Plan 11.11 Context7 Gateway MCP compatibility evidence

**Status:** Success. Context7 proved the exact `2026-07-28` floor, tools capability, complete allowlisted list, namespace/allowlist behavior, and no-auth Gateway-to-upstream path.

This artifact is Plan 11.11 compatibility evidence only. It does **not** claim Plan 11.8 Task 8 or Task 9 completion, ACP/WSL2/Docker/Redis/Playwright live closure, authenticated-server coverage, OAuth, or release-gate sign-off.

## Identity

| Field | Value |
|---|---|
| Repository commit | `5bdba34` (`5bdba346bfbb124aea70cb30461fec9c82b799ce`) |
| Gateway process | in-process `serve_gateway` from this worktree (same commit) |
| Working tree | uncommitted Plan 11.11 Tasks 1–4 (profile `auth_mode`, HTTP wire, `supportedVersions` normalization, this probe) |
| Branch | `agent/cursor/plan-11-11-mcp-http-compat` |

## Endpoint (sanitized)

- Hostname: `mcp.context7.com`
- Path: `/mcp`
- Query string: none (not recorded; none was configured)
- Secrets: none. `OPTIMUS_MCP_CONTEXT7_BEARER` was unset. No Authorization header was sent on the Gateway-to-upstream leg.

## Test command and markers

```powershell
uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py -m "requires_gateway and requires_mcp_context7" -q
```

Process environment for this run (not baked into `_required_env`): `OPTIMUS_MCP_CONTEXT7_URL` set to the verified public endpoint. Gateway shared-secret/provider material came from the existing `.env.gateway` seam and was injected only into `GatewayServiceConfig`. The agent client received only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`.

Real dependency markers: `requires_gateway` and `requires_mcp_context7`. The test fails (does not skip) when `OPTIMUS_MCP_CONTEXT7_URL` or Gateway material is absent. `requires_mcp_context7` is registered and default-deselected in `pyproject.toml`.

## Result counts

```text
.                                                                        [100%]
1 passed in 4.69s
```

Selected: 1. Passed: 1. Failed: 0. Skipped: 0. Deselected: 0.

## Selected protocol and sanitized disposition

- Selected protocol: `2026-07-28` (asserted; the passing probe requires exact equality).
- Sanitized disposition: asserted as one of `mcp.discover.complete` or `mcp.discover.unchanged`. This probe used `PENDING_REGISTRATION` with `manifest_hash=None` and invoked discover once, which is the Gateway `mcp.discover.complete` path. Quiet pytest output does not print the field; no upstream payload body was captured.
- Allowlist: `resolve-library-id`, `query-docs`. `unmatched_allowlist` was empty.
- Namespaced descriptors: exactly `context7.resolve-library-id` and `context7.query-docs`.
- Tools capability: accepted (discover completed; the Gateway path rejects a missing tools capability before returning descriptors).

Tool schemas, descriptions, and any other response content were redacted and were not required to prove the contract.

## No-auth and one-key assertions

- HTTP profile: `auth_mode="none"`, `credential_ref=None`.
- Credential resolver was required to raise if called; `resolver_calls == []`, so it was not called.
- Therefore no upstream Authorization header was constructed (`StreamableHTTPMCPTransport` adds `Authorization` only after a resolved bearer credential).
- `OPTIMUS_MCP_CONTEXT7_BEARER` was absent from the agent/test environment.
- `LOCAL_PROVIDER_KEY_NAMES` were absent from the agent/test environment (same one-key assertion as the existing Gateway live harness). Gateway shared-secret/provider keys stayed in Gateway config and were not copied into the agent env mapping.

## Explicit non-claims

- Plan 11.8 Task 8 Steps 2–4 remain incomplete and owned by Plan 11.8.
- Plan 11.8 Task 9 Steps 2–4 remain incomplete and owned by Plan 11.8.
- This probe did not exercise `tools/call`, stdio, Playwright, Redis, OAuth, ACP, WSL2, or the Plan 11.8 live harness file.
