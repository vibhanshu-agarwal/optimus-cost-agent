# Plan 11.8 Gateway MCP — Task 4 transport evidence

**Status:** Task 4 focused verification completed on 2026-08-06.

## Scope

This evidence covers only the bounded HTTP and Docker-contained stdio transport adapters and
the profile/revision-scoped connection manager. It does not claim Gateway routes, invocation,
usage persistence, OAuth, catalog/autoload, or live remote/stdio dependency evidence.

## Implemented and verified

- Streamable HTTP uses POST-only JSON-RPC requests with pinned endpoint origin/path, explicit
  HTTPS or provisioned loopback policy, no redirects, bearer credential projection, and per-request
  protocol/client/tools metadata.
- HTTP responses are bounded, JSON-object validated, and forbidden MCP capabilities are rejected;
  an active elapsed-time deadline is checked before and after each response chunk.
- Stdio launches only a digest-pinned image with fixed command/arguments, no mount/device/socket
  flags, `--env NAME` projection, and an environment containing only selected profile values.
- Stdio uses bounded response/duration reads, modern discovery with tools-only legacy initialization
  fallback, and an injected process-control seam for deterministic process-tree cleanup and
  platform-specific controls.
- Connection reuse is keyed by profile ID and revision. Revision changes close the old transport;
  close operations never activate or mutate profile lifecycle state.

## Verification

```text
uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py -q
15 passed

uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_tool_handlers.py -q
85 passed

uv run --frozen ruff check src/optimus_gateway/mcp_transports.py src/optimus_gateway/mcp_connections.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py
All checks passed
```

Real Windows Job Object and Linux/WSL2 platform evidence remains a release-tier requirement and is
not claimed by these unit tests. The report remains an uncommitted evidence artifact. Existing
`tmp/` content was not modified.
