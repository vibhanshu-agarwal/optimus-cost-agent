# Plan 11.8 Gateway MCP — Task 5 split-authority evidence

**Status:** Task 5 focused verification completed on 2026-08-06.

## Scope

This evidence covers only the agent-side typed Gateway client calls and the local MCP trust-gate
runner seam. It does not claim Gateway MCP route handlers, invocation admission, result validation,
usage persistence, live Gateway evidence, or later transport/result tasks.

## Implemented and verified

- `GatewayClient.discover_mcp` and `call_mcp` use only the exact typed routes
  `/v1/tools/mcp/discover` and `/v1/tools/mcp/call`, with the existing bearer and JSON headers.
- Typed request models form the complete outbound payload boundary; no upstream credential,
  endpoint, command, policy, approval, prompt, conversation, or secret-derived identifier is added.
- Typed response parsing fails closed with sanitized MCP response errors. Generic MCP proxying is
  rejected, and authorization is redacted in request representations.
- The runtime preserves the local registry/scanner/exposure/permission/`PreToolGuard` sequence and
  invokes the typed runner only after local approval. Calls bind profile ID, profile revision,
  Gateway-issued canonical manifest hash, namespaced tool name, and JSON arguments; response binding
  drift is held. The local trust manifest hash remains a separate tamper/reapproval authority.
- The existing trust registry records the approved profile revision and denies revision drift before
  the Gateway runner is called. Typed calls require a prior typed discovery binding and the test uses
  distinct local and Gateway hashes to prove the source is not conflated. No second permission
  registry was introduced.

## Verification

```text
uv run --frozen pytest tests/unit/gateway/test_client.py tests/unit/mcp/test_runtime.py tests/unit/mcp/test_gateway_runner.py tests/unit/mcp/test_gateway_payload_boundary.py tests/unit/guardrails/test_mcp_trust.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_prompt_injection.py -q
68 passed

rg -n "OPTIMUS_LOCAL_GATEWAY_MCP|MCP.*(TOKEN|SECRET|PASSWORD|API_KEY)|upstream.*credential|credential.*identifier" src/optimus tests/unit/mcp tests/unit/gateway
NO_MATCHES

uv run --frozen ruff check src/optimus/gateway/client.py src/optimus/mcp/runtime.py src/optimus/guardrails/mcp_trust.py tests/unit/mcp
All checks passed

git diff --check
clean
```

The report remains an uncommitted evidence artifact. Existing `tmp/` content was not modified.
