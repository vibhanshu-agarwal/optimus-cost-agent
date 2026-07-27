# Plan 11.2: P11-FEAT-GATEWAY-TOOLS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Serve typed Gateway web, package, and advisory tools with independent domain/provenance/policy revalidation while preserving the one-key client boundary and existing evidence ledger seam.

**Architecture:** Extend the existing `GatewayClient.post_tool_json` transport with one shared typed-tool contract. The local agent keeps deterministic validation, `ToolRegistry`, `PreToolGuard`, and ledger recording; the Gateway adds its own authenticated context, policy, domain, provenance, and call-cap checks before invoking server-side provider adapters. MCP is not implemented: `P11-FEAT-GATEWAY-MCP` is blocked on `P11-FU-3`.

**Tech Stack:** Python 3.11+, Pydantic v2, stdlib HTTP transport, `pytest`, `pytest-asyncio`, `pytest-cov`, Ruff, the existing Gateway server, and the existing Redis-backed integration conventions.

**Baseline:** `origin/main` at `bd216388c0da995e04df254ec198a00e4aab23d4`, after the merged Plan 11.1
CORE implementation and the `P11-FU-6` flake backlog entry. TOOLS extends the current
`src/optimus_gateway/server.py` dispatch and builds on the existing `chat_completions.py`,
`observability.py`, `models.py` envelope/auth validators, `upstream_client.py` retry helpers, and
`src/optimus/gateway/models.py` usage parser. It must not recreate or silently alter those CORE
contracts.

## Global Constraints

- The local agent resolves only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; provider credentials remain Gateway-side.
- Web search/extract, package lookup, and security advisory are read-only, policy-triggered tools; tool output and metadata are untrusted data.
- The Gateway independently revalidates tool class, signal, model, execution mode, domain, provenance, and call caps; it does not trust local `ToolRegistry` or `approved_urls` as authoritative.
- `P11-FU-2` is in scope; `P11-FEAT-GATEWAY-MCP` and `P11-FU-3` are out of scope and must remain absent from source/test changes.
- Budget/wallet/spend-cap enforcement remains `Deferred → P9.85-FU-3 (parked; operator decision pending)`; this plan may parse usage but may not compare or debit budgets.
- `cost_usd` and `billing_units` are parsed from the Gateway response envelope; no post-hoc token or cost estimation is introduced.
- Extract accepts one to ten unique HTTPS URLs, with `max_chars_per_source` default 4,000 and maximum 20,000; advanced search is capped at five results.
- Live §9D evidence uses a real staging Gateway and real policy state under `requires_gateway`; fakes are limited to unit tests and local-process tests explicitly named as deterministic local tiers.
- The `optimus_gateway` package remains independently deployable: its tool state module uses the
  direct top-level `redis>=5` client and has no `optimus.*` imports or agent-side Redis-store reuse.
- No source or test implementation begins until the frozen spec, implementation plan, and digest-pinned approval record are reviewed and approved.

---

## Freeze inputs and requirement custody

The design specification is
`docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md`.

The four authoritative source digests are:

| Source | SHA-256 |
|---|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.15.pdf` | `A386EEE8463A169A20A18B59BA923CFA80C0F6707DF7FEA3DB91B83FE3386C0B` |
| `docs/Optimus-Cost-Agent-LLD-v2.38.pdf` | `0471DCAE8100F41340AD6F3FE30F19B7CA8042C2949A534973B2A8D9564944DB` |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf` | `4669940B34C8C0CAAB5501C193213C3087C45FAE0CBA3011E1DBF87EB74B4D0C` |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf` | `6F7EB2B48447F1CE3D882FC60E16DA8B41C1DD7C926C359F45185823492DA5DB` |

The extracted inventory is
`docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md`.
Its committed-blob SHA-256 is
`7DD4FA40916B2306C55492B36D37FC0178798CC20552B6E73CF13CBF5B69FDC5`.

Every task below maps to the spec's four-authoritative-document traceability table and to one or
more evidence aliases from the inventory: E1 one-key release, E3 evidence wrappers, E4 ledger, E7
origin/secrets, E8 server policy revalidation, E9 coverage/release, and E10 source custody.

## File responsibility map

| File | Responsibility |
|---|---|
| `src/optimus/gateway/tool_models.py` | Shared typed request/result/provenance/envelope/package/advisory contracts. |
| `src/optimus/tools/policy.py` | Package/advisory tool class and dedicated signal/reason routing. |
| `src/optimus/evidence/models.py` | ACP-facing web/package/advisory request and response models, including single-URL extract compatibility. |
| `src/optimus/evidence/gateway_io.py` | Shared envelope builders/parsers for web and package/advisory calls. |
| `src/optimus/evidence/acquisition.py` | Local web policy, pre-tool, provenance, Gateway transport, and ledger orchestration. |
| `src/optimus/evidence/package_advisory.py` | Package lookup and security advisory orchestration and ledger joins. |
| `src/optimus/acp/dispatcher.py` | ACP method routing for package lookup and security advisory. |
| `src/optimus_gateway/tool_models.py` | Gateway-side contract validation adapters. |
| `src/optimus_gateway/tool_policy.py` | Authenticated context and independent Gateway policy/domain decisions. |
| `src/optimus_gateway/tool_state.py` | Gateway-owned search provenance and atomic call-cap state. |
| `src/optimus_gateway/tool_providers.py` | Server-side web/package/advisory provider protocols and adapters. |
| `src/optimus_gateway/tool_handlers.py` | Authenticated route handlers, validation, provider dispatch, and sanitized errors. |
| `src/optimus_gateway/server.py` | Extend the post-CORE dispatch with `/v1/tools/*`; preserve `/v1/responses`, `/v1/chat/completions`, `/v1/observability/traces`, and unknown-route behavior. |
| `src/optimus_gateway/chat_completions.py` | Existing Plan 11.1 handler to preserve and test as a regression seam; no TOOLS reimplementation. |
| `src/optimus_gateway/observability.py` | Existing Plan 11.1 trace-ingress handler to preserve and test as a regression seam; no TOOLS changes. |
| `src/optimus_gateway/models.py` | Reuse existing bearer authorization and model-route envelope validators; no duplicate CORE validators. |
| `src/optimus_gateway/upstream_client.py` | Reuse existing bounded retry/normalized provider-result seam for tool adapters; no parallel retry policy. |
| `src/optimus/gateway/models.py` | Reuse existing strict `GatewayUsage` model/parser for typed-tool usage/cost fields. |
| `tests/unit/gateway/test_tool_models.py` | Shared contract and envelope validation tests. |
| `tests/unit/tools/test_tool_policy.py` | Local tool-class/signal routing tests. |
| `tests/unit/evidence/test_gateway_io.py` | Client envelope building/parsing and usage/provenance tests. |
| `tests/unit/evidence/test_package_advisory.py` | Package/advisory service and ledger tests. |
| `tests/unit/optimus_gateway/test_tool_policy.py` | Gateway context, domain, policy, and error decision tests. |
| `tests/unit/optimus_gateway/test_tool_state.py` | Provenance and call-cap state tests. |
| `tests/unit/optimus_gateway/test_tool_handlers.py` | Route handler and provider-boundary tests. |
| `tests/unit/optimus_gateway/test_server.py` | Extend the existing three-route CORE dispatch regression coverage with the four tool paths. |
| `tests/unit/optimus_gateway/test_models.py` | Existing CORE envelope-validator regression coverage; retain while adding tool contracts. |
| `tests/unit/optimus_gateway/test_upstream_retry.py` | Existing CORE retry regression coverage; retain for shared tool-provider retry semantics. |
| `tests/integration/evidence/test_mocked_evidence_flow.py` | Local client flow and one-key request capture. |
| `tests/integration/optimus_gateway/test_gateway_tools_live.py` | Task 4 local-process route artifact plus Task 6 staging-only `requires_gateway` evidence. |
| `tests/integration/optimus_gateway/test_gateway_live_smoke.py` | Existing local-process CORE route smoke coverage; rerun as a TOOLS regression gate. |
| `tests/integration/optimus_gateway/test_gateway_tool_state_live.py` | `requires_redis` evidence for the direct Gateway Redis client, atomic call caps, and provenance TTL. |
| `docs/superpowers/reviews/plan-11-review-checkpoints.md` | Gitignored reviewer/implementation handoff log; never stage. |

---

### Task 0: Verify the frozen source and plan inputs before implementation

**Files:** Read-only verification of the four PDFs, requirement inventory, design spec, implementation plan, approval record, and current branch.

**Produces:** A freeze-input artifact proving that the worker is on the approved baseline and that
the exact design/plan/inventory bytes match the pending or approved digest record.

- [x] **Step 1: Confirm branch and worktree state.**

  Run from Git Bash at the repository root:

  ```bash
  git status --short --branch
  git rev-parse HEAD
  git rev-parse origin/main
  git diff --name-only -- src tests
  ```

  Expected: `git rev-parse HEAD` and `git rev-parse origin/main` both equal
  `bd216388c0da995e04df254ec198a00e4aab23d4`, and no source or
  test path is dirty before implementation.

- [x] **Step 2: Verify all four authoritative PDF digests.**

  ```bash
  sha256sum docs/Optimus-Cost-Agent-Architecture-v2.15.pdf
  sha256sum docs/Optimus-Cost-Agent-LLD-v2.38.pdf
  sha256sum docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf
  sha256sum docs/Optimus-Cost-Agent-Test-Strategy-v1.4.pdf
  ```

  Expected: the four values equal the source pin table above. A mismatch stops the task and
  requires a new requirement extraction; it is not a reason to silently update the spec.

- [x] **Step 3: Verify the inventory and frozen artifact bytes.**

  ```bash
  sha256sum docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md
  sha256sum docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md
  sha256sum docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md
  git show HEAD:docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md | sha256sum
  git show HEAD:docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md | sha256sum
  git show HEAD:docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md | sha256sum
  ```

  Expected: working-tree and committed-blob hashes match the approval record exactly and all
  pinned artifacts contain zero CR bytes. If any byte changes, invalidate the old record and create
  a versioned replacement before continuing.

- [x] **Step 4: Read the approval record and reviewer checkpoint Current State.**

  Do not begin source or test mutation until the approval record says reviewer-agent and operator
  approval exist for the exact bytes, and the checkpoint log confirms no conflicting ruling.

---

### Task 1: Establish shared typed-tool contracts and correct local policy routing

**Files:**

- Create: `src/optimus/gateway/tool_models.py`
- Modify: `src/optimus/tools/policy.py`
- Modify: `src/optimus/evidence/models.py`
- Create: `tests/unit/gateway/test_tool_models.py`
- Modify: `tests/unit/tools/test_tool_policy.py`
- Modify: `tests/unit/evidence/test_models.py`

**Interfaces:**

- `GatewayToolContext`: frozen model with `run_id: str`, `session_id: str | None`,
  `execution_mode: str`, `org_id: str | None`, `project_id: str | None`, and `model: str | None`.
- `GatewayToolProvenance`: frozen model with `search_id: str | None`,
  `source_urls: tuple[HttpUrl, ...]`, and `trust: Literal["untrusted"]`.
- `GatewayToolEnvelope[T]`: frozen generic model with `tool_class: ToolClass`,
  `policy_signal: ToolPolicySignal`, `run_id: str`, `result: T`, `provenance: GatewayToolProvenance`,
  and `gateway_usage: GatewayUsage`.
- `PackageLookupRequest`, `SecurityAdvisoryRequest`, `PackageLookupResult`, and
  `SecurityAdvisoryResult` use the exact fields in the design spec; package/advisory text and
  citations are marked untrusted.
- `ToolClass.PACKAGE_AND_ADVISORY_METADATA` is the only class accepted for package/advisory
  signals. `DEPENDENCY_VERSION_CHECK + PACKAGE_VERSION` and
  `SECURITY_OR_CVE_CHECK + SECURITY_ADVISORY` are removed from generic web triggers and placed in a
  dedicated package/advisory trigger set.

- [x] **Step 1: Write failing contract tests.**

  Add tests that reject empty queries and identifiers, unsupported ecosystems, duplicate extract
  URLs, non-HTTPS URLs, mixed `url`/`urls` forms, result caps outside 1–10, extraction limits
  outside 1–20,000, and malformed/null `gateway_usage`. Add tests that accept the exact web,
  package, and advisory success envelopes and preserve `Decimal` cost values.

- [x] **Step 2: Run the focused tests and confirm RED.**

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_tool_models.py tests/unit/tools/test_tool_policy.py tests/unit/evidence/test_models.py -q
  ```

  Expected: the new contract tests fail because the shared models and package/advisory class do not
  yet exist; existing tests may fail only where the intentional package-signal ownership changes
  their expected class.

- [x] **Step 3: Implement the minimum shared contracts and policy taxonomy.**

  Add frozen Pydantic v2 models with bounded fields and explicit HTTPS validation. Keep existing
  `GatewayUsage` parsing as the single usage parser. Update `ToolInvocationPolicy.authorize` so
  web and package/advisory classes have separate branches and reason-code requirements. Do not add
  MCP to the taxonomy or change `optimus/mcp/runtime.py`.

- [x] **Step 4: Run the focused tests and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/gateway/test_tool_models.py tests/unit/tools/test_tool_policy.py tests/unit/evidence/test_models.py -q
  ```

  Expected: all contract and policy tests pass, including explicit proof that dependency/CVE
  signals no longer authorize `WEB_SEARCH`.

---

### Task 2: Make the client web/package/advisory adapters consume the common envelope

**Files:**

- Modify: `src/optimus/evidence/gateway_io.py`
- Modify: `src/optimus/evidence/models.py`
- Modify: `src/optimus/evidence/acquisition.py`
- Create: `src/optimus/evidence/package_advisory.py`
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/evidence/test_gateway_io.py`
- Modify: `tests/unit/evidence/test_acquisition.py`
- Create: `tests/unit/evidence/test_package_advisory.py`
- Modify: `tests/integration/evidence/test_mocked_evidence_flow.py`

**Interfaces:**

- `build_web_search_payload(request: EvidenceRequest, context: GatewayToolContext) -> dict[str, Any]`.
- `build_web_extract_payload(request: EvidenceExtractRequest, context: GatewayToolContext) -> dict[str, Any]`.
- `parse_web_search_envelope(body: Mapping[str, Any]) -> GatewayToolEnvelope[WebSearchResultSet]`.
- `parse_web_extract_envelope(body: Mapping[str, Any]) -> GatewayToolEnvelope[WebExtractResultSet]`.
- `PackageAdvisoryService.package_lookup(request: PackageLookupRequest, *, execution_mode: ExecutionMode) -> tuple[PackageLookupResult, EvidenceLedger]`.
- `PackageAdvisoryService.security_advisory(request: SecurityAdvisoryRequest, *, execution_mode: ExecutionMode) -> tuple[SecurityAdvisoryResult, EvidenceLedger]`.
- ACP methods `optimus.evidence.package_lookup` and `optimus.evidence.security_advisory` return
  typed result payloads using the same error mapping as existing evidence methods.

- [x] **Step 1: Write failing adapter tests.**

  Prove that web builders preserve query verbatim, send reason only as metadata, map a legacy
  single `url` to `urls: [url]`, and reject duplicate or mixed forms. Prove that parsers unwrap
  `result`/`provenance`, require valid `gateway_usage`, preserve untrusted content, and retain
  `gateway_request_id`, billing units, cache status, and cost. Add package/advisory service tests
  for policy class, signal, Gateway path, typed result, and ledger join.

- [x] **Step 2: Run the client-focused tests and confirm RED.**

  ```powershell
  uv run --frozen pytest tests/unit/evidence/test_gateway_io.py tests/unit/evidence/test_acquisition.py tests/unit/evidence/test_package_advisory.py tests/integration/evidence/test_mocked_evidence_flow.py -q
  ```

  Expected: new envelope and package/advisory cases fail before adapter changes exist.

- [x] **Step 3: Implement the adapter/service changes.**

  Keep local `EvidenceDomainPolicy`, `ToolRegistry`, `PreToolGuard`, and `EvidenceLedger` in the
  call path. Replace direct top-level result parsing with shared-envelope parsing and preserve the
  existing ACP single-URL compatibility mapping. Ensure package/advisory failures record usage only
  when the Gateway supplied a valid usage envelope, exactly as web failures do.

- [x] **Step 4: Wire the two ACP methods without weakening dispatcher validation.**

  Add focused service construction to `JsonRpcDispatcher`; malformed params return `INVALID_REQUEST`,
  missing service returns `METHOD_NOT_FOUND`, and tool/policy/Gateway errors use the existing
  sanitized error path. Do not add an ACP MCP method.

- [x] **Step 5: Run the client-focused tests and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/evidence/test_gateway_io.py tests/unit/evidence/test_acquisition.py tests/unit/evidence/test_package_advisory.py tests/unit/acp/test_dispatcher.py tests/integration/evidence/test_mocked_evidence_flow.py -q
  ```

  Expected: existing web flow remains green, the package/security paths are dedicated, and no
  provider key appears in captured request payloads or exceptions.

---

### Task 3: Add Gateway-owned policy, provenance, and call-cap state

**Files:**

- Create: `src/optimus_gateway/tool_policy.py`
- Create: `src/optimus_gateway/tool_state.py`
- Modify: `src/optimus_gateway/models.py`
- Create: `tests/unit/optimus_gateway/test_tool_policy.py`
- Create: `tests/unit/optimus_gateway/test_tool_state.py`
- Create: `tests/integration/optimus_gateway/test_gateway_tool_state_live.py`

**Interfaces:**

- `GatewayToolPolicy.resolve_context(*, request_body: Mapping[str, Any], authenticated_subject: str) -> GatewayToolContext`.
- `GatewayToolPolicy.authorize(*, context: GatewayToolContext, tool_class: ToolClass, policy_signal: ToolPolicySignal, requested_domains: tuple[str, ...], resolved_urls: tuple[str, ...]) -> GatewayToolDecision`.
- `GatewayToolStateStore.record_search(*, run_id: str, source_urls: tuple[str, ...]) -> str`.
- `GatewayToolStateStore.search_result_urls(*, run_id: str) -> frozenset[str]`.
- `GatewayToolStateStore.increment_call(*, run_id: str, tool_class: ToolClass, max_calls: int) -> int`.
- `InMemoryGatewayToolStateStore` is unit-only. `RedisGatewayToolStateStore` is the named live
  implementation and must fail closed when Redis is unavailable.
- `RedisGatewayToolStateStore` uses the existing top-level `redis>=5` dependency through its own
  direct Redis client. It must not import `optimus.*`, reuse `optimus.redis.*`, or call the agent-side
  `RedisAgentStateStore`/wrapper; the `optimus_gateway` package remains independently deployable.

- [x] **Step 1: Write failing policy/state tests.**

  Test missing `run_id`, malformed metadata, unsupported execution mode, missing required identity,
  empty effective domain intersection, HTTP/non-HTTPS URL rejection, subdomain matching, search
  URL recording, same-run lookup, cross-run rejection, atomic cap rejection, and state-store
  unavailability.

- [x] **Step 2: Run policy/state tests and confirm RED.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_tool_policy.py tests/unit/optimus_gateway/test_tool_state.py -q
  ```

  Expected: the new Gateway-owned policy and state interfaces are absent and the tests fail.
  Confirmed: `ImportError: cannot import name 'GatewayToolContext' from 'optimus_gateway.models'`
  (2 errors during collection). See `.superpowers/sdd/task-3-report.md`.

- [x] **Step 3: Implement independent Gateway checks.**

  Normalize requested and resolved HTTPS hosts using the existing domain semantics, intersect them
  with the authenticated Gateway policy, and never accept local `approved_urls` as the authoritative
  source. Key provenance by `run_id` and call caps by `run_id + tool_class`; keep provider result
  bodies out of the state store. Return structured decisions with stable rule IDs for audit/error
  mapping.

- [x] **Step 4: Implement the Redis-backed state boundary.**

  Import the top-level `redis` package directly inside the Gateway state module and keep the client
  behind the narrow `GatewayToolStateStore` protocol. Use atomic Redis operations for the call
  counter and a bounded TTL record for search-result URL provenance. Do not import `optimus.*`, reuse
  `optimus.redis.*`, or call the agent-side `RedisAgentStateStore`/wrapper. The live path must not
  silently fall back to `InMemoryGatewayToolStateStore` when the configured state store is
  unavailable. Unit tests may use the in-memory store only as a dependency double.

- [x] **Step 5a (unit half): Run policy/state tests and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_tool_policy.py tests/unit/optimus_gateway/test_tool_state.py -q
  ```

  Confirmed: `38 passed in 0.21s`.

- [x] **Step 5b (live half): Run the real-Redis artifact and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_tool_state_live.py -m requires_redis -q
  ```

  Confirmed after Docker Desktop + local `redis:7-alpine` on `OPTIMUS_REDIS_URL=redis://127.0.0.1:6379/0`:
  `8 passed in 0.81s` (atomic call-cap, same-run provenance, cross-run isolation, TTL, fail-closed).

---

### Task 4: Add server-side provider adapters, typed handlers, and route dispatch

**Files:**

- Create: `src/optimus_gateway/tool_providers.py`
- Create: `src/optimus_gateway/tool_models.py`
- Create: `src/optimus_gateway/tool_handlers.py`
- Modify: `src/optimus_gateway/providers.py`
- Modify: `src/optimus_gateway/server.py`
- Create: `tests/unit/optimus_gateway/test_tool_handlers.py`
- Modify: `tests/unit/optimus_gateway/test_server.py`
- Create: `tests/integration/optimus_gateway/test_gateway_tools_live.py` (local-process route artifact)
- Create: `reports/plan-11-2-gateway-tools-local-process-evidence.md`

**Interfaces:**

- `WebToolProvider.search(request: WebSearchGatewayRequest) -> WebSearchProviderResult`.
- `WebToolProvider.extract(request: WebExtractGatewayRequest) -> WebExtractProviderResult`.
- `PackageToolProvider.lookup(request: PackageLookupGatewayRequest) -> PackageProviderResult`.
- `AdvisoryToolProvider.lookup(request: SecurityAdvisoryGatewayRequest) -> AdvisoryProviderResult`.
- `GatewayToolDependencies` groups the four provider protocols, `GatewayToolPolicy`, and
  `GatewayToolStateStore` for injection into `serve_gateway`.
- `handle_tool_request(*, authorization_header: str | None, path: str, request_body: Mapping[str, Any], config: GatewayServiceConfig, dependencies: GatewayToolDependencies) -> tuple[int, dict[str, Any]]`.

- [x] **Step 1: Write failing handler tests.**

  Test all four paths with an injected deterministic provider bundle. Verify bearer auth happens
  before provider invocation; malformed typed bodies return 400; blocked domains and wrong class or
  signal return 403; missing extract provenance returns 403; cap overflow returns 429; state outage
  returns 503; successful responses contain only the common typed envelope and valid usage.

- [x] **Step 2: Run handler/server tests and confirm RED.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_tool_handlers.py tests/unit/optimus_gateway/test_server.py -q
  ```

  Expected: the four tool routes still return 404 because route dispatch and handlers do not exist.
  Confirmed via `git stash` of the new/changed Task 4 files: `ModuleNotFoundError: No module named
  'optimus_gateway.tool_handlers'` (collection errors) before restoring the implementation.

- [x] **Step 3: Implement provider protocols and server-side adapter boundaries.**

  Keep credentials inside the Gateway provider bundle. Translate the typed web/package/advisory
  requests to provider calls without passing raw request metadata as provider instructions. Sanitize
  provider errors and normalize provider results into the shared result models; never return raw
  provider JSON, keys, or unbounded URLs.

- [x] **Step 4: Implement handlers in the prescribed order.**

  Authenticate, validate, resolve context, apply policy/domain/provenance/call-cap checks, invoke
  the provider, record search provenance where applicable, and build the common envelope. Assign a
  `gateway_request_id` to accepted or policy-rejected requests and preserve the existing 404
  behavior for unknown paths.

- [x] **Step 5: Add explicit server dispatch.**

  Extend the current post-CORE `OptimusGatewayHandler.do_POST` dispatch for exactly:

  ```text
  /v1/tools/web/search
  /v1/tools/web/extract
  /v1/tools/package/lookup
  /v1/tools/security/advisory
  ```

  Keep `/v1/responses`, `/v1/chat/completions`, `/v1/observability/traces`, invalid-JSON handling,
  non-object-body handling, and unknown-route behavior unchanged. Reuse the existing CORE auth and
  envelope-validation/retry/usage seams; do not modify `chat_completions.py`, `observability.py`, or
  `upstream_client.py` as a substitute for tool-specific contracts. Thread
  `GatewayToolDependencies` from `serve_gateway` without making the local agent aware of provider
  configuration.

- [x] **Step 6: Run handler/server tests and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/unit/optimus_gateway/test_tool_handlers.py tests/unit/optimus_gateway/test_server.py -q
  ```

  Confirmed: `62 passed`. All four tool routes are served over HTTP with deterministic unit
  providers, while the three existing CORE routes and unknown-route behavior remain green.

- [x] **Step 7: Produce the Task 4 local-process artifact before closing the task.**

  Extend `tests/integration/optimus_gateway/test_gateway_tools_live.py` using the existing
  subprocess/fixture conventions. Start the real Gateway server process and inject only a
  deterministic server-side tool-provider bundle through the `GatewayToolDependencies` seam; do not
  substitute an HTTP fake. Exercise all four tool paths over real HTTP, including bearer auth,
  typed success envelopes, and the search-then-extract provenance sequence. Preserve the existing
  CORE route smoke assertions in `test_gateway_live_smoke.py` as a regression gate.

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_tools_live.py -m requires_live_gateway -q
  ```

  Write `reports/plan-11-2-gateway-tools-local-process-evidence.md` with the exact test command,
  date, implementation SHA, process configuration class, route status codes, request IDs, and
  sanitized response summaries. Expected: this local-process HTTP artifact records the four route
  responses before Task 4 is marked complete. It is local deterministic evidence, not the real
  staging policy evidence reserved for Task 6.

  Confirmed: `7 passed in 3.84s`; see
  `reports/plan-11-2-gateway-tools-local-process-evidence.md`.

---

### Task 5: Reconcile local integration flow and ledger/provenance behavior

**Files:**

- Modify: `tests/integration/evidence/test_mocked_evidence_flow.py`
- Create: `tests/integration/evidence/test_package_advisory_flow.py`
- Modify: `tests/integration/usage/test_evidence_provider_reconciliation.py`
- Modify: `tests/unit/evidence/test_ledger.py`
- Modify: `tests/unit/gateway/test_client.py`

- [x] **Step 1: Write failing integration assertions.**

  Extend the existing search-then-extract flow to assert the common envelope, Gateway-issued search
  provenance, untrusted content, one-key Authorization header, and ledger joins by
  `gateway_request_id`. Add package and advisory flows that prove their paths and tool class are
  dedicated and that usage/cost is recorded once per Gateway response.

- [x] **Step 2: Run the integration subset and confirm RED.**

  ```powershell
  uv run --frozen pytest tests/integration/evidence/test_mocked_evidence_flow.py tests/integration/evidence/test_package_advisory_flow.py tests/integration/usage/test_evidence_provider_reconciliation.py tests/unit/evidence/test_ledger.py tests/unit/gateway/test_client.py -q
  ```

  Confirmed RED via `tests/integration/evidence/test_package_advisory_flow.py` not existing
  (collection error) before this task; Tasks 1–4 had already implemented the common envelope,
  Gateway-issued provenance, and ledger semantics, so the extended assertions on the pre-existing
  files exercised already-correct behavior rather than surfacing a second defect. See
  `.superpowers/sdd/task-5-report.md`.

- [x] **Step 3: Reconcile the integration fixtures and ledger assertions.**

  Keep the transport fake limited to the client/integration tier. Assert no direct provider URL is
  requested by the local agent, no secret appears in `GatewayRequest.__repr__`, the search URL is
  recorded before extract, and malformed or usage-less responses never create a false ledger entry.

- [x] **Step 4: Run the integration subset and confirm GREEN.**

  ```powershell
  uv run --frozen pytest tests/integration/evidence/test_mocked_evidence_flow.py tests/integration/evidence/test_package_advisory_flow.py tests/integration/usage/test_evidence_provider_reconciliation.py tests/unit/evidence/test_ledger.py tests/unit/gateway/test_client.py -q
  ```

  Confirmed: `33 passed`. Full `tests/unit`: `1654 passed, 19 skipped`. Ruff clean on touched
  files. No `src/` files changed (test-only reconciliation).

---

### Task 6: Produce real staging §9D evidence

**Files:**

- Modify: `tests/integration/optimus_gateway/test_gateway_tools_live.py` (staging tests only)
- Create: `reports/plan-11-2-gateway-tools-staging-evidence.md`
- Modify: `docs/superpowers/reviews/plan-11-review-checkpoints.md` (gitignored; never stage)

- [ ] **Step 1: Add real staging Gateway policy evidence.**

  Mark the staging tests `requires_gateway`. Use only real `OPTIMUS_GATEWAY_URL` and
  `OPTIMUS_API_KEY` credentials, send direct HTTP requests that bypass local `ToolRegistry`, and
  record sanitized results for:

  - a blocked domain search;
  - an extract URL not present in a preceding Gateway search for the same `run_id`;
  - a package lookup sent with a web tool class or wrong signal;
  - a security advisory sent with a web tool class or wrong signal; and
  - a call-cap overage on a real `run_id + tool_class` counter.

  The tests must assert the Gateway status, structured error reason, and `gateway_request_id`.
  They must not use a fake server or claim §9D evidence from the local unit provider.

- [ ] **Step 2: Add real success-path evidence for both package families.**

  Use the staging Gateway's configured package-registry and advisory providers to record one
  successful package lookup and one successful security advisory lookup. Assert the dedicated paths,
  `PACKAGE_AND_ADVISORY_METADATA` class, correct signal/reason, typed result, HTTPS citations,
  `gateway_usage`, and one-key credential boundary. Sanitize provider response bodies before writing
  the evidence report.

- [ ] **Step 3: Write the named evidence report and checkpoint entry.**

  `reports/plan-11-2-gateway-tools-staging-evidence.md` must contain the exact test command, date,
  implementation SHA, Gateway environment class, status codes, request IDs, and sanitized response
  summaries. Update the gitignored checkpoint log with the same artifact path; do not stage the log.

- [ ] **Step 4: Run the staging tier.**

  ```powershell
  uv run --frozen pytest tests/integration/optimus_gateway/test_gateway_tools_live.py -m requires_gateway -q
  ```

  Expected: real-staging evidence is recorded separately from Task 4's local-process artifact. If
  credentials or Gateway policy state are unavailable, mark the staging tier not run; do not replace
  it with a fake and do not close the §9D claim.

---

### Task 7: Run the release, security, coverage, and scope gates

**Files:** The affected source/tests, report, approval record, and checkpoint log; no MCP or budget files.

- [ ] **Step 1: Run the affected unit and integration suites.**

  ```powershell
  uv run --frozen pytest tests/unit/tools tests/unit/evidence tests/unit/gateway tests/unit/optimus_gateway tests/unit/acp/test_dispatcher.py tests/integration/evidence tests/integration/usage/test_evidence_provider_reconciliation.py tests/integration/optimus_gateway/test_gateway_tools_live.py tests/integration/optimus_gateway/test_gateway_tool_state_live.py -q
  ```

- [ ] **Step 2: Run the repository default suite and aggregate coverage.**

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen pytest --cov=optimus --cov=optimus_gateway --cov=optimus_security --cov-report=term-missing --cov-fail-under=80 -q
  ```

  Expected: aggregate Python production-code coverage is at least 80%; safety-critical policy and
  trust modules do not regress.

- [ ] **Step 3: Run Ruff and diff hygiene.**

  ```powershell
  uv run --frozen ruff check .
  git diff --check
  git status --short --branch
  ```

  Expected: Ruff and diff checks pass, with no source/test path from MCP or budget enforcement in
  the implementation diff.

- [ ] **Step 4: Run the one-key release scan.**

  Use the repository's existing release-gate command and prove that only
  `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` are resolvable in the local agent process. Provider
  credentials may appear only in the Gateway deployment boundary used by the named live tier.

- [ ] **Step 5: Reconcile every traceability row.**

  For every in-scope row in the spec, record its unit, local-process, staging, ledger, or release
  artifact. Record `P11-FU-3`/MCP and `P9.85-FU-3`/budget as explicit exclusions, not missing tests.

- [ ] **Step 6: Freeze the final bytes.**

  Recompute the design spec, implementation plan, and inventory committed-blob SHA-256 values.
  If any approved byte changed, invalidate the current approval record and create a new versioned
  record before implementation sign-off. Do not amend a frozen approval record in place.

---

## Evidence-to-claim table

| Claim | Required evidence |
|---|---|
| Four typed tool routes are served | Local-process HTTP artifact plus focused handler/server tests. |
| Gateway-owned Redis state is isolated and fail-closed | Unit state tests, `requires_redis` artifact using a real Redis client, and the no-`optimus.*` import boundary. |
| Web search domains are independently revalidated | Real `requires_gateway` blocked-domain artifact, not only local policy tests. |
| Extract requires same-run Gateway provenance | Real `requires_gateway` unapproved-URL rejection plus local search-then-extract flow. |
| Package and advisory signals use the dedicated tool class | Policy unit tests, ACP integration flow, and real success/error artifacts for both routes. |
| Typed envelopes preserve usage/provenance and fail closed | Contract/parser tests, malformed-usage tests, and sanitized live response summaries. |
| One-key and provider isolation hold | Request-capture tests, local release scan, and staging credential-boundary evidence. |
| Call caps are Gateway-owned | State tests plus real staging cap-overage rejection keyed by `run_id + tool_class`. |
| Budget remains deferred | Explicit `P9.85-FU-3` disposition and absence of spend-cap implementation/tests. |
| MCP remains gated | Charter/backlog cross-link, no MCP source/test diff, and `P11-FU-3` source-repair custody. |
| Release fitness holds | Full suite, coverage >=80%, Ruff, diff hygiene, and named evidence report. |

## Definition of Done

- [ ] The four typed Gateway tool routes are implemented with shared request/result/provenance/
  usage envelopes and sanitized errors.
- [ ] Task 4's real local-process HTTP artifact proves the four route responses before staging policy
  evidence is attempted.
- [ ] Web search/extract use HTTPS/domain bounds, Gateway-owned search provenance, and bounded
  extraction limits; local pre-tool and registry checks remain active.
- [ ] `P11-FU-2` is closed by dedicated package/advisory routing, with signals no longer passing
  through generic `WEB_SEARCH` policy.
- [ ] Gateway-side tool, model, execution-mode, domain, provenance, and call-cap checks are
  independently proven with real staging Gateway evidence.
- [ ] `RedisGatewayToolStateStore` uses the direct top-level Redis client, not an agent-side wrapper,
  and real-Redis evidence proves atomic call caps and provenance TTL behavior.
- [ ] Provider keys remain Gateway-side; local agent requests use only the two Optimus credentials.
- [ ] Usage/cost is parsed from Gateway envelopes and joined to the evidence ledger by
  `gateway_request_id`; no budget enforcement or cost estimation is added.
- [ ] `P11-FEAT-GATEWAY-MCP` and `P11-FU-3` remain outside the implementation diff and explicitly
  linked in the charter/backlog.
- [ ] The full affected suite, default suite, coverage >=80%, Ruff, diff hygiene, and one-key
  release scan pass, with each checkbox backed by its stated artifact.
