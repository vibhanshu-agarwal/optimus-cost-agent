# Plan 11.2 (P11-FEAT-GATEWAY-TOOLS) — Task 4 Local-Process Evidence

- **Date:** 2026-07-27
- **Branch:** `agent/cursor/plan-11-2-gateway-tools`
- **Commit (worktree HEAD, uncommitted Task 4 changes on top):** `91b0f25d8d87010523965172538d394d32472a5f`
- **Command:**
  ```
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_tools_live.py -m requires_live_gateway -q
  ```
- **Result:** `7 passed in 3.84s`

## What this evidence proves

`tests/integration/optimus_gateway/test_gateway_tools_live.py` starts the
real, production `serve_gateway()` `ThreadingHTTPServer` bound to a real
loopback socket on an OS-assigned ephemeral port, running in a background
daemon thread. This is the same server construction path production code
uses (`optimus_gateway.server.serve_gateway`) — the test only substitutes the
injectable `GatewayToolDependencies` seam (deterministic
web/package/advisory provider doubles, an in-memory `GatewayToolStateStore`,
and a real `GatewayToolPolicy`) plus a deterministic `UpstreamClient` double
for the CORE model route. No HTTP-layer fake is used anywhere: every request
in the test module is a genuine `HTTPConnection`/`urllib.request` round trip
over the real socket, through the real `OptimusGatewayHandler.do_POST`
routing, real JSON parsing, real bearer-auth check, and the real
`handle_tool_request` dispatch.

## Routes exercised (all four, over real HTTP)

| Route | Test | Status | Notes |
|---|---|---|---|
| `/v1/tools/web/search` | `test_web_search_route_served_over_real_http_with_bearer_auth` | 401 (wrong bearer) then 200 | Verifies auth precedes dispatch; success envelope has `tool_class=web_search`, `policy_signal=CURRENT_OR_LATEST_FACT`, non-empty `provenance.search_id`, `gateway_usage.gateway_request_id` prefixed `gw-tool-`, `gateway_usage.provider=tavily` |
| `/v1/tools/web/search` → `/v1/tools/web/extract` | `test_search_then_extract_provenance_sequence_over_real_http` | 200, 200 | End-to-end provenance sequence: extract only succeeds because the URL was previously returned by search on the same `run_id`; `gateway_usage.cache_hit=true` on the deterministic extract double confirms provider-reported usage flows through unmodified |
| `/v1/tools/web/extract` (no prior search) | `test_web_extract_rejects_url_without_prior_search_over_real_http` | 403 | `rule_id=URL_NOT_IN_SEARCH_PROVENANCE`, non-empty `gateway_request_id`, no raw state-store detail leaked |
| `/v1/tools/package/lookup` | `test_package_lookup_route_served_over_real_http` | 200 | `tool_class=package_and_advisory_metadata`, `policy_signal=DEPENDENCY_VERSION_CHECK`, provider usage `provider=package-registry` |
| `/v1/tools/security/advisory` | `test_security_advisory_route_served_over_real_http` | 200 | `tool_class=package_and_advisory_metadata`, `policy_signal=SECURITY_OR_CVE_CHECK`, provider usage `provider=osv` |
| `/v1/responses` (CORE, unaffected) | `test_core_routes_remain_unaffected_alongside_tool_dependencies` | 200 | Confirms injecting `tool_dependencies` does not disturb the pre-existing CORE model route |
| `/v1/unknown` | `test_unknown_route_still_returns_not_found` | 404 | Confirms unknown-path 404 behavior is preserved alongside the new tool dispatch branch |

## Sanitized summary of exercised gateway_request_ids

Each 200/403/429/503 response carries a fresh, uniquely-generated
`gateway_request_id` (`gw-tool-<uuid4 hex>` for tool routes, `gw-<uuid4 hex>`
for the CORE route), confirmed via string assertions in the test bodies. No
raw provider payload, credential, or internal exception text is present in
any response body — provider doubles return only synthetic, non-secret
strings (`"Get Python"`, `"Download the latest Python release."`, a synthetic
advisory id), and the 403/404/401 paths assert on `rule_id`/`error` fields
only, never on state-store or policy internals.

## Distinction from Task 6

This is Task 4's **local-process** artifact: a real HTTP server object with
injected deterministic providers, run in-process in the test's own Python
interpreter. It is not the Task 6 real-staging-Gateway evidence tier
(`requires_gateway`), which will use a genuinely separate Gateway process,
real credentials, and real upstream providers.
