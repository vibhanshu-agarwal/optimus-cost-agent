# P11-FEAT-GATEWAY-MCP 2026-07-28 HTTP Compatibility Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Gateway MCP HTTP path conform to the frozen 2026-07-28 Streamable HTTP contract and support explicitly provisioned unauthenticated HTTP profiles, so the real Context7 fixture can pass through the Gateway without weakening the one-key agent boundary.

**Architecture:** Preserve the frozen static-profile, tools-only, dual-transport Gateway design. Add an explicit `auth_mode` to HTTP profile configuration, normalize the profile credential reference as optional only for `auth_mode="none"`, emit the namespaced 2026-07-28 request metadata and headers, and normalize both the existing singular discovery version shape and the real `supportedVersions` shape into the existing internal `protocol_version` field. Validate the change with unit tests and one Gateway-originated Context7 discovery probe; leave the broader Playwright/Redis, ACP, WSL2, and release evidence lane with Plan 11.8.

**Tech Stack:** Python 3.14, dataclass profile models, `urllib.request` Streamable HTTP transport, `pytest`, `pytest-asyncio`, `coverage.py`, `pytest-cov`, Ruff, the existing `GatewayClient` and `serve_gateway` path, and the real public Context7 MCP endpoint.

**Status:** Draft for Claude review and operator approval. This document authorizes planning only; it does not authorize implementation, commit, push, or PR creation.

## Global Constraints

- Plan 11.8 remains frozen. Do not edit `docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md` or `docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md` from this lane.
- Plan 11.11 is a narrow compatibility remediation. It does not replace or absorb Plan 11.8 Task 8 Steps 2-4 or Task 9 Steps 2-4. Those tasks remain owned by the original frozen Plan 11.8 and resume separately after this remediation lands and is reviewed.
- The selected concrete transports are fixed: Context7 is the HTTP fixture; Playwright MCP and official Redis MCP are stdio fixtures for the later Plan 11.8 live lane. Do not add Playwright HTTP or Redis HTTP acceptance to this plan.
- The remote MCP protocol floor is exactly `2026-07-28`. HTTP has no initialize fallback, no session behavior, no redirect behavior, and no direct upstream route.
- `MCPHTTPProfile.auth_mode` is explicit and auditable: `"bearer"` is the default; `"none"` is the only way to permit an unauthenticated upstream HTTP leg. An empty or missing credential value must never silently infer `"none"`.
- Authenticated HTTP remains the default and continues to require a non-empty Gateway-owned `credential_ref` and a resolved bearer credential. Stdio continues to require its existing Gateway-owned credential reference and safe environment projection.
- The no-auth option changes only the Gateway-to-upstream HTTP leg. The agent still receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no provider, Context7, Playwright, Redis, or other upstream credential may enter the agent environment.
- Context7 discovery must be performed through the Gateway route using `GatewayClient` and the configured real endpoint. A direct curl probe, a fake MCP server, or a project-authored upstream MCP client is not release evidence.
- Preserve the current tools-only capability policy, profile revision/manifest binding, allowlist, bounded response, result validation, accounting-before-release, and no-automatic-redispatch behavior.
- Use TDD: write the failing test, run it to establish the failure, implement the smallest change, rerun the focused test, then run the affected regression suite.
- No commit, push, branch deletion, history rewrite, or PR is authorized by this draft. The implementation agent must stop after verification and hand off the diff and evidence to Claude and the operator.

## Verified Scope and Ownership Boundary

The upstream mapping was independently verified before this plan was drafted:

| Dependency | Verified upstream behavior | Plan 11.11 treatment |
|---|---|---|
| Context7 | Public Streamable HTTP endpoint at `https://mcp.context7.com/mcp`; the live preflight returned `supportedVersions: ["2026-07-28"]`, tools capability, and complete `tools/list` without an Authorization header | Remediate the Gateway HTTP/profile/discovery compatibility path and run one Gateway-originated discovery evidence probe |
| Playwright MCP | Official default and Docker usage are stdio; its HTTP implementation also exposes session/GET and legacy SSE behavior | No change; remains a later Plan 11.8 stdio fixture |
| Redis MCP | Official `mcp-redis` supports stdio and documents Streamable HTTP as future work | No change; remains a later Plan 11.8 stdio fixture |

References to verify again at execution time: [MCP 2026-07-28 Streamable HTTP](https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx), [Playwright MCP](https://github.com/microsoft/playwright-mcp), [Redis MCP](https://raw.githubusercontent.com/redis/mcp-redis/main/README.md), and [Context7 MCP](https://github.com/upstash/context7/blob/master/packages/mcp/README.md).

The gap is in the already-landed Gateway implementation, not in a new upstream transport requirement:

- `src/optimus_gateway/mcp_transports.py` currently emits legacy unnamespaced `_meta` keys, sends only `Accept: application/json`, and always resolves and attaches a bearer credential for HTTP.
- `src/optimus_gateway/mcp_profiles.py` currently requires a non-empty `credential_ref` for every profile and has no explicit HTTP authentication mode.
- `src/optimus_gateway/mcp_discovery.py` currently accepts only a singular `protocolVersion` field, while the verified Context7 response uses `supportedVersions`.

## File Map

Files that the implementation may modify or create:

- Modify: `src/optimus_gateway/mcp_profiles.py` — explicit HTTP authentication mode, optional credential reference only for explicit no-auth HTTP, startup mapping, copy/update behavior, and safe serialization.
- Modify: `src/optimus_gateway/mcp_transports.py` — 2026-07-28 metadata/header construction and conditional HTTP credential resolution.
- Modify: `src/optimus_gateway/mcp_discovery.py` — normalize singular and plural version response shapes into the existing selected protocol version.
- Modify: `tests/unit/optimus_gateway/test_mcp_profiles.py` — profile auth-mode and serialization contract tests.
- Modify: `tests/unit/optimus_gateway/test_mcp_transports.py` — request metadata, header, bearer-default, and no-auth wire tests.
- Modify: `tests/unit/optimus_gateway/test_mcp_discovery.py` — `supportedVersions` normalization and fail-closed malformed-shape tests.
- Modify: `pyproject.toml` — register and default-deselect the focused `requires_mcp_context7` real-dependency marker if the marker is not already present.
- Create: `tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py` — one real Gateway-originated Context7 discovery probe; this is compatibility evidence only, not Plan 11.8 release closure.
- Create: `reports/plan-11-11-gateway-mcp-context7-compatibility.md` — sanitized live evidence report produced only after the real probe passes or records the required fail-closed disposition.

Do not modify the frozen Plan 11.8 plan/design, the Plan 11.8 generic HTTP/stdio harness, the ACP evidence tool, WSL worktree, or the Redis accounting test in this plan.

---

### Task 1: Add an explicit, auditable HTTP authentication mode

**Files:**

- Modify: `src/optimus_gateway/mcp_profiles.py:72-128, 230-380`
- Test: `tests/unit/optimus_gateway/test_mcp_profiles.py`
- Test: `tests/unit/optimus_gateway/test_mcp_handlers.py` if profile startup serialization assertions require coverage there

**Interfaces:**

- `MCPHTTPProfile` gains `auth_mode: Literal["bearer", "none"] = "bearer"`.
- `MCPProfile.credential_ref` becomes `str | None` at the dataclass boundary.
- Validation rules are explicit:
  - HTTP + `auth_mode="bearer"`: `credential_ref` must be a non-empty, non-fingerprint string.
  - HTTP + `auth_mode="none"`: `credential_ref` must be `None`; an empty string is invalid, and a non-empty reference is invalid because it would falsely imply a credential is bound.
  - stdio: `credential_ref` remains a required non-empty, non-fingerprint string and continues to drive environment projection.
- `profile_from_mapping()` must require the explicit `transport_config.auth_mode="none"` before accepting a missing/null HTTP `credential_ref`; a missing auth mode keeps the default `"bearer"` and therefore rejects a missing credential.
- Startup metadata, `_copy_profile()`, `update_profile()`, `reenable()`, and any safe profile serialization must preserve `auth_mode` and the nullable credential reference without serializing a secret.

- [x] **Step 1: Write the failing profile tests.** Reuse the existing `_profile_kwargs()` fixture factory in `tests/unit/optimus_gateway/test_mcp_profiles.py` and add these exact behavioral assertions. Import `MCPProfileDefinitionError` and `profile_from_mapping` inside the tests, matching the existing test-file import pattern:

```python
def test_http_bearer_is_the_default_and_requires_a_credential_ref():
    with pytest.raises(MCPProfileDefinitionError, match="credential_ref"):
        profile_from_mapping(_profile_kwargs(credential_ref=None))


def test_http_none_requires_explicit_mode_and_has_no_credential_ref():
    profile = profile_from_mapping(
        _profile_kwargs(
            credential_ref=None,
            transport_config={"endpoint": "https://mcp.context7.com/mcp", "auth_mode": "none"},
        )
    )
    assert profile.transport_config.auth_mode == "none"
    assert profile.credential_ref is None


def test_empty_credential_does_not_infer_http_none():
    with pytest.raises(MCPProfileDefinitionError):
        profile_from_mapping(
            _profile_kwargs(
                credential_ref="",
                transport_config={"endpoint": "https://mcp.context7.com/mcp", "auth_mode": "none"},
            )
        )
```

The test file must retain its existing authenticated profile and stdio fixtures; the new tests add only the explicit `None`/`auth_mode` cases.

- [x] **Step 2: Run the focused tests to verify they fail for the current model.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py -k "auth_mode or credential" -q
  ```

  Expected: FAIL because `MCPHTTPProfile` has no `auth_mode`, `MCPProfile` rejects `None`, and the mapping path always stringifies `credential_ref`.

- [x] **Step 3: Implement the smallest profile-model change.** Add the explicit auth mode and cross-field validation. Keep the existing fingerprint rejection, profile allowlist, revision, manifest, and forbidden-field checks. Update every profile copy/update/startup path so changing `transport_config.auth_mode` mints a new revision and so a no-auth HTTP profile cannot accidentally inherit a previous bearer reference.

  The implementation must preserve this invariant:

  ```python
  if profile.transport == "http" and profile.transport_config.auth_mode == "none":
      assert profile.credential_ref is None
  else:
      assert isinstance(profile.credential_ref, str) and profile.credential_ref.strip()
  ```

- [x] **Step 4: Run the profile and serialization regression tests.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_handlers.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_profiles.py tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_handlers.py
  ```

  Expected: all existing bearer/stdio/profile-lifecycle tests remain green; no credential value appears in safe serialized output.

### Task 2: Emit the exact 2026-07-28 HTTP request contract

**Files:**

- Modify: `src/optimus_gateway/mcp_transports.py:74-186`
- Test: `tests/unit/optimus_gateway/test_mcp_transports.py`

**Interfaces:**

- `_meta(protocol_version, client_meta)` returns only the namespaced 2026-07-28 keys:

  ```python
  {
      "io.modelcontextprotocol/protocolVersion": protocol_version,
      "io.modelcontextprotocol/clientInfo": {"name": name, "version": version},
      "io.modelcontextprotocol/clientCapabilities": {"tools": {}},
  }
  ```

- `_request()` accepts an optional `mcp_name` so `tools/call` can emit the method name without reconstructing it from untrusted header input. The JSON-RPC body remains the source of truth for method, tool name, and arguments.
- Every HTTP request sends `Accept: application/json, text/event-stream`, `Content-Type: application/json`, and `MCP-Protocol-Version: 2026-07-28`.
- Every request sends `Mcp-Method` matching the exact allowed method. `tools/call` additionally sends `Mcp-Name` matching the validated upstream tool name. No `Mcp-Param-*` mirroring is added.
- The transport remains request-scoped: no `MCP-Session-Id`, GET stream, redirect following, or HTTP initialize fallback.
- `auth_mode="bearer"` still requires a credential resolver and emits `Authorization: Bearer <resolved value>`.
- `auth_mode="none"` never calls the credential resolver and never emits an `Authorization` header. Supplying a resolver is harmless but it must not be invoked.
- Extend the existing test helper `_http_profile()` with keyword arguments `credential_ref: str | None = "context7-token"` and `auth_mode: Literal["bearer", "none"] = "bearer"` so both auth branches use the same profile construction path.

- [x] **Step 1: Write failing wire-contract tests.** Extend the existing HTTP transport tests with these assertions:

```python
def test_http_transport_emits_namespaced_2026_metadata_and_method_headers():
    opener = _HTTPOpener(
        _HTTPResponse(
            {"result": {"capabilities": {"tools": {}}}},
            url="https://mcp.example/tools",
        )
    )
    transport = StreamableHTTPMCPTransport(
        _http_profile(), opener=opener, credential_resolver=lambda _ref: "secret"
    )

    transport.tools_call(
        upstream_tool_name="resolve-library-id",
        arguments={"libraryName": "pytest"},
        protocol_version="2026-07-28",
    )

    request, _timeout = opener.requests[0]
    payload = json.loads(request.data)
    assert request.headers["Accept"] == "application/json, text/event-stream"
    assert request.headers["Mcp-method"] == "tools/call"
    assert request.headers["Mcp-name"] == "resolve-library-id"
    assert payload["params"]["_meta"] == {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "client", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {"tools": {}},
    }


def test_http_none_does_not_resolve_or_send_a_bearer_credential():
    opener = _HTTPOpener(
        _HTTPResponse(
            {"result": {"capabilities": {"tools": {}}}},
            url="https://mcp.example/tools",
        )
    )
    resolver_calls: list[str | None] = []
    transport = StreamableHTTPMCPTransport(
        _http_profile(auth_mode="none", credential_ref=None),
        opener=opener,
        credential_resolver=lambda ref: resolver_calls.append(ref) or "must-not-be-used",
    )

    transport.server_discover(protocol_version="2026-07-28", client_meta={"name": "client", "version": "1"})

    request, _timeout = opener.requests[0]
    assert resolver_calls == []
    assert "Authorization" not in request.headers
```

- [x] **Step 2: Run the focused transport tests to verify the current failure.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py -q
  ```

  Expected: FAIL on legacy metadata, the single-value Accept header, missing MCP method/name headers, and unconditional bearer resolution.

- [x] **Step 3: Implement the wire and credential branching changes.** Keep the existing origin pinning, bounded reads, timeout, redirect denial, JSON validation, error classification, and transport close behavior. Add no compatibility fallback for legacy HTTP initialization. Pass the validated `tools/call` name explicitly into `_request()` and keep all header values derived from fixed method/tool validation.

- [x] **Step 4: Run transport and connection regressions.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_connections.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_transports.py tests/unit/optimus_gateway/test_mcp_transports.py
  ```

  Expected: bearer-default tests, origin/redirect tests, response-limit tests, Docker stdio tests, and deterministic teardown tests remain green.

### Task 3: Normalize `supportedVersions` without weakening the protocol floor

**Files:**

- Modify: `src/optimus_gateway/mcp_discovery.py:65-155`
- Test: `tests/unit/optimus_gateway/test_mcp_discovery.py`

**Interfaces:**

- `_validate_server_discover(server_info)` continues to return the selected internal protocol string consumed by `CompleteToolSet.protocol_version` and the typed route responses.
- Accepted response shapes are:
  - Existing shape: `{"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}}`.
  - Real Streamable HTTP shape: `{"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}}`.
- For `supportedVersions`, select `MCP_PROTOCOL_FLOOR` only when it is present as a valid version. Do not guess a future version or silently downgrade below the floor.
- If both fields are present, require the singular field to equal the selected supported version; conflicting fields fail closed with `mcp.protocol_version_unsupported`.
- A missing, malformed, duplicate, unsupported, or below-floor version list fails closed with `mcp.protocol_version_unsupported`. Capability validation remains unchanged: `tools` is required and forbidden capabilities remain denied.

- [x] **Step 1: Write failing discovery tests.** Add tests covering plural success, malformed plural failure, below-floor failure, and conflicting dual-field failure:

```python
def test_server_discover_accepts_supported_versions_at_the_protocol_floor():
    assert MCPDiscoveryPaginator._validate_server_discover(
        {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}}
    ) == "2026-07-28"


@pytest.mark.parametrize(
    "server_info",
    [
        {"supportedVersions": "2026-07-28", "capabilities": {"tools": {}}},
        {"supportedVersions": ["2025-11-25"], "capabilities": {"tools": {}}},
        {
            "protocolVersion": "2026-07-28",
            "supportedVersions": ["2025-11-25"],
            "capabilities": {"tools": {}},
        },
    ],
)
def test_server_discover_rejects_invalid_or_conflicting_version_shapes(server_info):
    with pytest.raises(MCPDiscoveryError, match="mcp.protocol_version_unsupported"):
        MCPDiscoveryPaginator._validate_server_discover(server_info)
```

- [x] **Step 2: Run the focused discovery tests to verify the plural response currently fails.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_discovery.py -q
  ```

  Expected: the new `supportedVersions` test fails with the current singular-field-only validator.

- [x] **Step 3: Implement deterministic version normalization.** Keep the existing retry cap, page/cursor validation, capability rejection, allowlist, manifest, and freshness semantics. The normalization must not turn an unsupported Context7 response into a successful result; it succeeds only when the exact floor is proven.

- [x] **Step 4: Run discovery, model, and handler regressions.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/optimus_gateway/test_mcp_models.py tests/unit/optimus_gateway/test_mcp_handlers.py -q
  uv run --frozen ruff check src/optimus_gateway/mcp_discovery.py tests/unit/optimus_gateway/test_mcp_discovery.py
  ```

### Task 4: Prove the corrected path with a real Gateway-originated Context7 probe

**Files:**

- Modify: `pyproject.toml` only if `requires_mcp_context7` is not already registered and default-deselected
- Create: `tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py`
- Create: `reports/plan-11-11-gateway-mcp-context7-compatibility.md`

**Interfaces and evidence:**

- The test must use the existing `GatewayClient` and Gateway MCP route/handler path. It may start the real `serve_gateway` process through the established integration fixture pattern, but it must not implement an upstream MCP server or use a project-authored upstream MCP client.
- Configure only `OPTIMUS_MCP_CONTEXT7_URL` for the upstream endpoint, the existing Gateway shared-secret/provider configuration required by the real Gateway test path, and the agent-side `OPTIMUS_GATEWAY_URL`/`OPTIMUS_API_KEY` pair. There is deliberately no `OPTIMUS_MCP_CONTEXT7_BEARER`.
- Construct a static HTTP profile with `MCPHTTPProfile(endpoint=..., auth_mode="none")`, `credential_ref=None`, and an allowlist containing only the Context7 discovery target needed by the test. A credential resolver that fails the test if called is required so an accidental credential lookup cannot pass silently.
- Invoke only `POST /v1/tools/mcp/discover` through `GatewayClient`. Assert the selected protocol is `2026-07-28`, the tools capability is accepted, the returned descriptors are complete, the Context7 names are namespaced, the allowlist is satisfied, and the disposition is complete/unchanged as appropriate.
- The report must include the Gateway and repository commit, endpoint hostname/path without secrets, test command, real dependency marker, result counts, selected protocol, sanitized disposition, and explicit assertions that no Authorization header or upstream credential was used. Do not claim the full Plan 11.8 Task 9 result from this focused probe.

- [x] **Step 1: Add the marker and write the RED live-test skeleton.** Follow the existing `requires_gateway`/real-dependency marker convention. The test must fail clearly when `OPTIMUS_MCP_CONTEXT7_URL` or the real Gateway material is absent; a skipped or deselected test is not evidence.

  ```python
  @pytest.mark.requires_gateway
  @pytest.mark.requires_mcp_context7
  def test_context7_discovery_is_gateway_originated_and_unauthenticated():
      endpoint = _required_env("OPTIMUS_MCP_CONTEXT7_URL")
      profile = _context7_none_profile(endpoint)
      resolver_calls: list[str | None] = []

      def resolver(ref: str | None):
          resolver_calls.append(ref)
          raise AssertionError("unauthenticated Context7 profile requested a credential")

      with _running_gateway(profile=profile, credential_resolver=resolver) as gateway:
          response = gateway.client.discover_mcp(_discover_request(profile))

      assert response.protocol_version == "2026-07-28"
      assert response.descriptors
      assert response.unmatched_allowlist == ()
      assert response.disposition in {"mcp.discover.complete", "mcp.discover.unchanged"}
      assert resolver_calls == []
  ```

  Define the helpers in the new test file with these exact responsibilities:

  - `_required_env(name: str) -> str` reads and strips the named environment variable and calls `pytest.fail(f"{name} is required for this real dependency tier")` when empty.
  - `_context7_none_profile(endpoint: str) -> MCPProfile` returns profile id `context7`, revision `rev-11-11-context7-1`, state `PENDING_REGISTRATION`, transport `http`, `credential_ref=None`, allowlist `("resolve-library-id", "query-docs")`, `MCPHTTPProfile(endpoint=endpoint, auth_mode="none")`, and `MCPResourceLimits(max_pages=10, max_tools=20, max_descriptor_bytes=65536, max_elapsed_seconds=30.0, max_call_duration_seconds=30.0, max_result_bytes=65536)`.
  - `_discover_request(profile: MCPProfile) -> MCPDiscoverRequest` returns a request containing the profile id and revision with no manifest hash.
  - `_running_gateway(*, profile: MCPProfile, credential_resolver: Callable[[str | None], str | dict[str, str]]) -> Iterator[GatewayClient]` constructs `MCPProfileRegistry`, `MCPConnectionManager`, `MCPDiscoveryBroker`, `MCPInvocationBroker`, `InMemoryMCPUsageWriter`, `GatewayMCPDependencies`, and `GatewayServiceConfig` using the existing `serve_gateway`/background-thread pattern in `tests/integration/optimus_gateway/test_gateway_mcp_live.py`; it yields a `GatewayClient`, then closes connections and the server in `finally`.

  The helper must use the existing Gateway setup seam; do not add a second MCP protocol client or an upstream fake server.

- [x] **Step 2: Run the live test before implementation to establish the compatibility failure.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py -m "requires_gateway and requires_mcp_context7" -q
  ```

  Expected before Tasks 1-3: profile construction or Gateway discovery fails because the current profile cannot represent explicit no-auth, the current HTTP wire shape is incompatible, or the singular discovery validator rejects Context7’s plural version response.

- [x] **Step 3: Implement the real probe after Tasks 1-3 pass.** Use the configured real endpoint and Gateway path. Do not replace the endpoint with a local fixture, direct curl, fake transport, or project-authored MCP client. Preserve the agent one-key assertion and redact all endpoint query material and response content not required to prove the contract.

- [x] **Step 4: Run the real Context7 evidence command and write the sanitized report.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py -m "requires_gateway and requires_mcp_context7" -q
  ```

  The report must state one of the following, based on the actual result:

  - Success: Context7 proved the exact floor, tools capability, complete list, namespace/allowlist behavior, and no-auth Gateway-to-upstream path.
  - Fail-closed: the endpoint did not prove the floor or tools contract, with disposition `mcp.protocol_version_unsupported` or the precise validated error; no Context7 support claim is permitted.

### Task 5: Run the remediation fitness gate and hand off without closing Plan 11.8

**Files:**

- No new source files.
- Read: `docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md` and the frozen design to confirm no edits occurred.
- Read: `reports/plan-11-11-gateway-mcp-context7-compatibility.md`.

- [x] **Step 1: Run the complete affected unit suite and coverage.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/unit/optimus_gateway/test_mcp_connections.py tests/unit/optimus_gateway/test_mcp_handlers.py tests/unit/optimus_gateway/test_mcp_models.py -q
  uv run --frozen pytest --cov=optimus_gateway.mcp_profiles --cov=optimus_gateway.mcp_transports --cov=optimus_gateway.mcp_discovery --cov-branch --cov-report=term-missing tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_discovery.py -q
  ```

  Expected: all affected tests pass and the changed production paths do not fall below the project’s 80% aggregate coverage gate when the full release gate is later run by Plan 11.8.

- [x] **Step 2: Run the repository lint and diff hygiene checks.**

  ```powershell
  uv run --frozen ruff check src/optimus_gateway/mcp_profiles.py src/optimus_gateway/mcp_transports.py src/optimus_gateway/mcp_discovery.py tests/unit/optimus_gateway/test_mcp_profiles.py tests/unit/optimus_gateway/test_mcp_transports.py tests/unit/optimus_gateway/test_mcp_discovery.py tests/integration/optimus_gateway/test_gateway_mcp_context7_live.py
  git diff --check
  git status --short --branch
  ```

- [x] **Step 3: Perform the scope and credential audit.** Confirm with `rg` that:

  ```powershell
  rg -n "auth_mode|credential_ref|Authorization|MCP-Protocol-Version|Mcp-Method|Mcp-Name|supportedVersions|protocolVersion" src/optimus_gateway tests/unit/optimus_gateway tests/integration/optimus_gateway
  rg -n "OPENAI_API_KEY|OPENROUTER_API_KEY|TAVILY_API_KEY|CONTEXT7_API_KEY|OPTIMUS_MCP_CONTEXT7_BEARER" reports tests tools .env.example .env.gateway.example
  ```

  The audit must show that authenticated bearer behavior remains the default, no-auth is explicit, no upstream credential is present in agent configuration, and no Plan 11.8 Task 8/9 evidence claim was copied into the new report.

- [x] **Step 4: Hand off for review.** Stop with the working tree uncommitted. Give Claude and the operator the changed-file list, focused test output, live Context7 report, coverage output, Ruff output, and explicit confirmation that:

  - Plan 11.8 Task 8 Steps 2-4 remain incomplete and owned by Plan 11.8.
  - Plan 11.8 Task 9 Steps 2-4 remain incomplete and owned by Plan 11.8.
  - Plan 11.11 has not authorized ACP, WSL2, Docker containment, Redis accounting, Playwright/Redis live fixtures, authenticated servers, OAuth, or release closure.
  - No commit, push, or PR was created.

## Acceptance Criteria

Plan 11.11 is complete only when every applicable condition below is backed by a real artifact or passing command:

- A bearer HTTP profile without a credential reference is rejected.
- An HTTP profile with `auth_mode="none"` and `credential_ref=None` is accepted; an empty string or non-empty credential reference does not silently produce no-auth behavior.
- Authenticated HTTP remains the default and still sends the resolved bearer credential.
- Explicit no-auth HTTP never calls the credential resolver and never sends an Authorization header.
- HTTP requests emit the exact namespaced 2026-07-28 metadata, dual media-type Accept header, protocol-version header, method header, and validated tool-name header required by the selected method.
- The HTTP path remains request-scoped and refuses redirects, sessions, legacy initialization fallback, forbidden capabilities, oversized responses, and invalid result shapes exactly as before.
- Discovery accepts the verified `supportedVersions: ["2026-07-28"]` shape and retains fail-closed handling for malformed, conflicting, below-floor, or missing version evidence.
- The real Gateway-originated Context7 probe proves the floor, tools capability, complete list, namespace/allowlist result, and explicit no-auth mode, or records the required unsupported disposition without claiming support.
- The agent environment still contains only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no upstream credential is introduced.
- Playwright/Redis stdio behavior and all existing authenticated HTTP/stdio tests remain green.
- The remediation report is sanitized and does not claim completion of any remaining Plan 11.8 Task 8 or Task 9 step.

## Explicit Exclusions and Deferred Custody

| Excluded item | Owning scope | Boundary |
|---|---|---|
| Plan 11.8 Task 8 Steps 2-4 | Frozen Plan 11.8 | Complete local Gateway flow, generic real HTTP/stdio fixtures, Redis accounting, split-authority, and transport reports remain there |
| Plan 11.8 Task 9 Step 2 | Frozen Plan 11.8 | External `acpx` ACP evidence remains there |
| Plan 11.8 Task 9 Step 3 | Frozen Plan 11.8 | WSL2/Linux Docker containment remains there |
| Plan 11.8 Task 9 Step 4 | Frozen Plan 11.8 | Full coverage, release, documentation freshness, and final credential gates remain there |
| Playwright HTTP | Future `P11-FEAT-GATEWAY-MCP` work | The verified official HTTP behavior is not a clean fit for the frozen request-scoped HTTP contract |
| Redis Streamable HTTP | Future `P11-FEAT-GATEWAY-MCP` work | Official `mcp-redis` documents stdio; HTTP is future work |
| Authenticated MCP servers and OAuth | `P11-FU-12` / future MCP follow-up | No OAuth lifecycle, token, or authenticated-server fixture is added |
| Deferred MCP capabilities and long-lived interaction | `P11-FU-13` | No resources, prompts, subscriptions, sampling, elicitation, roots, or logging support is added |
| MCP registry/discover-and-connect | `P11-FU-14` | Profiles remain static and operator-provisioned |
| Tool search/context minimization | `P11-FU-15` | No search or context-management behavior is added |
| Publication-plan historical reconciliation | `P11-FU-27` | Remains separately open and unrelated to this implementation lane |

The frozen design and Plan 11.8 remain the source of truth for the deferred items. Plan 11.11 may not close the feature lane or mark any excluded item complete.
