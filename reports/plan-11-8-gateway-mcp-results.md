# Plan 11.8 Gateway MCP — Task 6 invocation and route evidence

**Status:** Task 6 focused verification completed on 2026-08-06.

## Scope

This evidence covers only Gateway-side invocation admission, strict result-envelope validation,
complete-only release gating, typed handler behavior, and the two exact authenticated MCP routes.
It does not claim Task 7 additive usage-record semantics, Redis persistence, live Gateway/MCP
dependencies, OAuth, catalog/autoload, ACP `mcpServers`, or deferred MCP capabilities.

## Implemented and verified

- `MCPInvocationBroker` performs Gateway profile/revision/manifest/allowlist admission twice,
  derives the upstream tool name from the validated namespace, forwards only JSON arguments, and
  does not automatically retry a dispatched call.
- Standard upstream `tools/call` results are strictly validated and wrapped into the typed
  Gateway response envelope. Complete results are the only releasable result; `input_required`,
  malformed content, image/audio content, binding drift, transport drift, oversized responses,
  persistence failure, and budget denial are withheld with typed dispositions.
- Returned content remains model-validated untrusted data. No result body is fetched, executed,
  promoted to policy, or treated as a trusted manifest.
- `POST /v1/tools/mcp/discover` and `POST /v1/tools/mcp/call` are the only MCP paths exposed by
  the handler. Bearer authentication precedes typed parsing; existing CORE/TOOLS/observability
  and unknown-route behavior remains covered by the combined route suite.

## Verification

```text
uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_handlers.py -q
91 passed

uv run --frozen ruff check src/optimus_gateway/mcp_invocation.py src/optimus_gateway/mcp_handlers.py src/optimus_gateway/server.py tests/unit/optimus_gateway/test_mcp_invocation.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_result_policy.py
All checks passed

git diff --check
clean
```

The usage writer is an injected Task 7 seam; this Task 6 report makes no accounting-persistence
claim. Existing `tmp/` content was not modified. The report remains an uncommitted evidence
artifact.
