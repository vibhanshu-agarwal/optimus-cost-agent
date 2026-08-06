# Plan 11.8 Gateway MCP — Task 2 profile lifecycle evidence

**Status:** Task 2 focused verification completed on 2026-08-06.

## Scope

This evidence covers only the static Gateway-owned MCP profile registry, opaque revision
lifecycle, exact discovery/call binding admission, and non-secret HMAC-signed startup metadata.
No MCP discovery, transport adapter, invocation, usage, OAuth, catalog/autoload, ACP
`mcpServers`, or semantic-selection capability was added.

## Implemented and verified

- Profiles begin in `PENDING_REGISTRATION` and can become `ACTIVE` only through startup
  activation of the existing profile ID/revision with a valid manifest hash.
- Calls require `ACTIVE`, exact revision/hash binding, and a profile-scoped upstream allowlist.
- Refresh admission requires the existing manifest hash; stale profiles permit only an explicit
  matching-hash discovery refresh for recoverable drift handling, while stale calls, disabled,
  revision-mismatched, unknown, and non-allowlisted requests are denied.
- Drift transitions an active profile to `STALE`; configuration changes and re-enable mint opaque
  revisions and return to `PENDING_REGISTRATION`; disable is immediate without minting.
- Startup metadata is exact-field, duplicate-checked, JSON-only, and rejects OAuth, catalog,
  autoload, raw credential, bearer, password, and credential-fingerprint fields.
- The existing Gateway child manifest signs profile metadata alongside the existing provider/bind
  contract. It carries only a credential reference and never raw upstream/provider/shared-secret
  values. Tampering fails signature verification.
- The Gateway entrypoint constructs the registry only after manifest verification and fails closed
  on malformed or unbound startup profiles. `serve_gateway` accepts the injected registry without
  coupling it to Tavily or Plan 11.2 tool state. Parent bootstrap helpers forward metadata only.

## Verification

```text
uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/security/test_mcp_profile_manifest.py -q
22 passed

uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/security/test_mcp_profile_manifest.py tests/unit/security/test_launch_manifest.py tests/unit/acp/test_local_infra.py tests/unit/acp/test_launch_approval_cli.py -q
126 passed, 6 skipped

uv run --frozen pytest tests/unit/optimus_gateway/test_main_entrypoint.py tests/unit/optimus_gateway/test_server.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_import_boundary.py tests/unit/mcp/test_models.py -q
61 passed

uv run --frozen ruff check src/optimus_gateway/mcp_profiles.py src/optimus_security/launch_manifest.py src/optimus_gateway/__main__.py src/optimus_gateway/server.py src/optimus_gateway/models.py src/optimus_gateway/providers.py src/optimus/acp/local_infra.py src/optimus/acp/launch_approval_cli.py
All checks passed

git diff --check
clean
```

The reports in `reports/` remain uncommitted evidence artifacts. Existing `tmp/` content was not
modified.
