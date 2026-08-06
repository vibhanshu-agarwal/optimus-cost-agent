# Plan 11.8 Gateway MCP — Task 3 discovery evidence

**Status:** Task 3 focused verification completed on 2026-08-06.

## Scope

This evidence covers only complete, bounded tools discovery and deterministic pagination over an
injected transport seam. It does not claim a remote HTTP adapter, Docker stdio adapter, Gateway
route, invocation, usage persistence, or live dependency evidence; those remain later tasks.

## Implemented and verified

- `server/discover` must return a dated protocol at or above `2026-07-28` and advertise tools.
  No legacy HTTP initialize fallback is present.
- `tools/list` pages are exhausted in order under page, tool, descriptor-byte, and elapsed-time
  limits. A malformed page, repeated/non-advancing cursor, malformed cursor, or budget exhaustion
  raises without returning a partial manifest.
- Only the profile’s operator allowlist is returned; unmatched configured names are reported.
  Tool definitions and `x-mcp-header` annotations are validated, and `Mcp-Param-*` requirements
  are rejected.
- Discovery retries only transient server/list faults and caps attempts at three.
- The broker emits `profile_id.tool_name` names, computes the canonical manifest hash, reports
  `fresh`/`unchanged`/`stale` freshness, marks drift stale, and marks an active profile stale after
  a recoverable refresh failure.
- Registration and refresh remain bound to the existing profile/revision request contract.

## Verification

```text
uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/mcp/test_mcp_discovery_binding.py -q
11 passed

uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/security/test_mcp_profile_manifest.py tests/unit/security/test_launch_manifest.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_launch_approval_cli.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/mcp/test_mcp_discovery_binding.py -q
137 passed, 6 skipped

uv run --frozen pytest tests/unit/optimus_gateway/test_main_entrypoint.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py tests/unit/mcp/test_models.py -q
61 passed

uv run --frozen ruff check src/optimus_gateway/mcp_profiles.py src/optimus_gateway/mcp_discovery.py src/optimus_gateway/__main__.py src/optimus_gateway/server.py src/optimus_gateway/models.py src/optimus_gateway/providers.py src/optimus_security/launch_manifest.py src/optimus/acp/local_infra.py src/optimus/acp/launch_approval_cli.py tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/mcp/test_mcp_discovery_binding.py tests/unit/security/test_mcp_profile_manifest.py tests/unit/optimus_gateway/test_server.py
All checks passed

git diff --check
clean
```

The report remains an uncommitted evidence artifact. Existing `tmp/` content was not modified.
