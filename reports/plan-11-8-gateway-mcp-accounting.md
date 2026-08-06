# Plan 11.8 Gateway MCP — Task 7 accounting-core evidence

**Status:** Task 7 closed on 2026-08-06 by operator ruling: the accounting core and fail-closed
never-redispatch behavior are delivered and verified. The durable effect-aware indeterminate-call
custody/re-invocation capability is explicitly deferred to the named backlog entry
[`Durable effect-aware MCP indeterminate-call custody`](../docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md#durable-effect-aware-mcp-indeterminate-call-custody).

## Implemented and verified

- Added immutable Gateway-owned `MCPUsageRecord` validation for `settled`, `explicit_zero`, and
  `unavailable` attribution, including non-negative byte/duration measurements and preservation of
  unavailable monetary fields as absent rather than zero.
- Added idempotent in-memory and direct Redis writers keyed by `gateway_request_id`. Identical
  replays are accepted; divergent same-ID records are rejected; Redis failures surface as typed
  unavailable/persistence errors without an in-memory fallback.
- Wired invocation release through `MCPUsageRecord` persistence. The record is built only after
  strict result validation and before the response is returned. Strict-dollar policy denies
  unavailable attribution unless the bound profile permits unattributed spend; explicit zero
  requires the revision-bound declared-free policy.
- Existing Gateway usage contracts and Plan 11.2 Redis tool-state keys remain unchanged.

## Verification

```text
uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_usage.py tests/unit/optimus_gateway/test_mcp_accounting.py tests/unit/optimus_gateway/test_tool_state.py tests/unit/gateway/test_usage_fields.py -q
37 passed

uv run --frozen ruff check src/optimus_gateway/mcp_usage.py src/optimus_gateway/mcp_invocation.py tests/unit/optimus_gateway/test_mcp_usage.py tests/unit/optimus_gateway/test_mcp_accounting.py
All checks passed

uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py tests/unit/optimus_gateway/test_mcp_usage.py tests/unit/optimus_gateway/test_mcp_accounting.py tests/unit/mcp/test_gateway_runner.py tests/unit/mcp/test_runtime.py -q
86 passed

uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_handlers.py -q
91 passed

git diff --check
clean
```

## Deferred boundary and closure decision

The frozen design describes effect-aware durable custody for post-dispatch indeterminate calls:
read-only tools may be explicitly re-invoked, while side-effecting calls must remain held until
operator acknowledgment across agent restart. The current repository has no durable indeterminate
hold/acknowledgment API in `PreToolGuard` or its approval store. Per the Task 7 closure decision,
that custody/re-invocation half is not claimed as delivered and is owned by the backlog entry linked
above; the delivered safety half remains fail-closed with no automatic redispatch and explicit
indeterminate errors. No live Redis or live dependency evidence is claimed; `tmp/` was not modified.
