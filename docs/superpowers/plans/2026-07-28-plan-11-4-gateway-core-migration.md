# Plan 11.4 Gateway Core Migration Implementation Plan

**Status:** Closed. Implemented and merged to `main` through PR #91 (`d80e112`).

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Complete the Phase 1 local-first Gateway migration so the agent has one strict-loopback trust boundary, the Gateway has one OpenRouter-compatible model transport, and settled model cost comes only from provider-reported accounting.

**Architecture:** The agent sends either /v1/responses (input) or /v1/chat/completions (messages) to the authenticated loopback Gateway. Both routes converge on one OpenRouter-compatible UrllibOpenAICompatibleClient; the Gateway parses provider/model/cache/accounting metadata and builds the existing GatewayUsage envelope without local price estimation. Direct Anthropic/OpenAI provider selection and hosted/tenant trust seams are removed while typed tool routes and COST-OBS persistence remain owned by their existing lanes.

**Tech Stack:** Python 3.14, stdlib urllib, Pydantic 2, pytest/pytest-asyncio/pytest-cov, coverage.py, Ruff, local ThreadingHTTPServer, HMAC-signed Gateway child manifests, and the independently authored acpx client for any ACP protocol evidence.

## Global Constraints

- Local runtime credentials are limited to OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY; provider credentials remain Gateway-child-only.
- OptimusGatewaySettings accepts only http:// or https:// URLs whose host is 127.0.0.1, localhost, or ::1; userinfo, malformed/ambiguous hosts, non-loopback hosts, and non-HTTP(S) schemes fail closed.
- The Gateway is developer-run on loopback and is not a hosted Optimus service, tenant control plane, OAuth/device-flow service, Vault, public Gateway, wallet, or subscription product.
- OpenRouter is the sole Phase 1 aggregator endpoint after the bounded Vercel check; Vercel remains backlogged under P11-FEAT-GATEWAY-CORE and no comparison matrix or second endpoint is added.
- Both agent-facing completion shapes use one OpenAI-compatible transport; the request shapes are never mixed.
- Provider-reported cost and billing units are authoritative. Missing, null, negative, non-finite, malformed, or type-invalid accounting is a permanent failure before model success or settled usage is emitted.
- Model completion retries are capped at three total attempts for transient network, timeout, rate-limit, and provider-availability faults. Authentication, schema, policy, unsupported-model, malformed-JSON, and malformed-accounting faults do not retry. Tool-provider retry semantics remain unchanged.
- GatewayUsage.provider is the aggregator identity (openrouter); an optional resolved_provider carries the actual selected provider only when the aggregator returns it. The parser never guesses a provider.
- The local MODEL_RATES/compute_cost_usd success path is removed. Any retained price snapshot is diagnostic metadata only and cannot populate settled cost_usd.
- The three inventory rows tagged P11-FEAT-GATEWAY-COST-OBS (LLD §6 row 9, LLD §6.1 row 11, Test Strategy §7 row 9) are split-custody rows: CORE implements request-path validation/fail-closed enforcement; COST-OBS owns settled-usage reconciliation, persistence, schema migration, and release evidence.
- P11-FEAT-GATEWAY-TOOLS, OTel/OTLP-to-Phoenix work, the separate USD field migration, budget governance, MCP, registry, Zed-resume, and Windows-flake work are not implemented in this plan.
- Use TDD for every production change: failing test, narrow failure run, minimum implementation, narrow green run, then the next task. Do not commit, push, delete branches, or rewrite history unless separately requested.
- Before sign-off, run the affected tests, the full approved suite, aggregate coverage at or above 80%, python -m ruff check ., and git diff --check. Real requires_gateway, requires_live_gateway, and ACP evidence must use their named dependencies rather than project-authored fakes.

Design source: docs/superpowers/specs/2026-07-28-plan-11-4-p11-feat-gateway-core-migration-design.md (operator-approved after reviewer-agent custody addendum). The 54-row inventory remains the acceptance baseline.

## File and responsibility map

| Responsibility | Production surfaces | Test/evidence surfaces |
|---|---|---|
| Strict agent trust boundary | src/optimus/config/gateway.py, src/optimus/config/__init__.py, src/optimus/gateway/client.py | tests/unit/config/test_gateway_settings.py, tests/unit/gateway/test_client.py |
| Agent/child environment custody | src/optimus/acp/local_infra.py, src/optimus/acp/subprocess_env.py, src/optimus/acp/launch_policy.py, src/optimus/acp/local_gateway_secrets.py, src/optimus/acp/launch_gate.py, src/optimus/acp/launch_approval_cli.py | tests/unit/acp/test_local_infra.py, test_acp_subprocess_env.py, test_launch_policy.py, test_local_gateway_secrets.py, test_launch_gate.py, test_launch_approval_cli.py |
| Gateway child configuration | src/optimus_gateway/models.py, src/optimus_gateway/providers.py, src/optimus_gateway/model_mapping.py, src/optimus_security/launch_manifest.py | tests/unit/optimus_gateway/test_models.py, test_providers.py, test_main_entrypoint.py, tests/unit/security/test_launch_manifest.py, test_gateway_base_url_resolution.py |
| One upstream transport and retries | src/optimus_gateway/upstream_client.py, src/optimus_gateway/anthropic_client.py (retired) | tests/unit/optimus_gateway/test_upstream_client.py, test_upstream_retry.py |
| Provider accounting and route envelopes | src/optimus_gateway/responses.py, src/optimus_gateway/chat_completions.py, src/optimus/gateway/models.py, src/optimus_gateway/pricing.py (success path retired) | tests/unit/optimus_gateway/test_responses.py, test_server.py, test_pricing.py (replaced/removed), tests/unit/gateway/test_models.py, test_usage_fields.py |
| Live/release evidence | README.md, .env.example, .env.gateway.example, integration harnesses | tests/integration/optimus_gateway/test_gateway_live_smoke.py, gateway_env.py, tests/integration/gateway/test_gateway_live.py, test_failed_usage_transport_flow.py, release and egress suites |

The implementation plan does not authorize changes to src/optimus_gateway/tool_*, tool route policy, OTel exporters, Phoenix integration, or the COST-OBS persistence schema except for additive compatibility assertions required by the Gateway wire envelope.

---

### Task 1: Re-derive the blast radius and freeze the acceptance ledger

**Files:**
- Read-only: docs/superpowers/specs/2026-07-28-plan-11-4-p11-feat-gateway-core-migration-design.md
- Read-only: docs/superpowers/reports/2026-07-25-plan-11-p11-feat-gateway-deep-requirement-inventory.md
- Read-only: all production/test paths listed by the search commands below

**Interfaces:**
- Consumes: approved design spec, 54-row inventory, current origin/main baseline.
- Produces: a rerunnable blast-radius record in the implementation task notes/checkpoint log; no source or test mutation.

- [x] Step 1: Verify the branch and clean baseline

Run:

~~~powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
~~~

Expected: branch agent/codex/plan-11-4-gateway-core, both revisions 8b9486d950b9bf74dc5149ff7e2dc9c957b2593d, and no pre-existing source/test changes.

Executed on `agent/cursor/plan-11-4-gateway-core` with `HEAD`/`origin/main` both `7615c99e3beba311ea6dae7e87f871252c2bb7ab` after PR #90 merged the plan docs (see Task 1 report).

- [x] Step 2: Re-run the deprecated-surface search

Run:

~~~powershell
rg -n "gateway\.optimus\.ai|production_mode|OPTIMUS_PRODUCTION_MODE|OPTIMUS_EXTRA_GATEWAY_ORIGINS|signed_tenant_profile|ProviderKeyPolicy|UrllibAnthropicClient|parse_anthropic|ANTHROPIC_API_KEY|MODEL_RATES|compute_cost_usd|_MAX_UPSTREAM_ATTEMPTS" src tests README.md .env.example .env.gateway.example
~~~

Expected: output identifies only the current migration surfaces and their regression tests; no unrelated tool or observability path is added to the task ledger.

- [x] Step 3: Re-run a structural inventory with AST names

Run this read-only scan and record its output with the task notes:

~~~powershell
python -c "import ast; from pathlib import Path; roots=[Path('src/optimus/config'),Path('src/optimus/acp'),Path('src/optimus_gateway'),Path('src/optimus_security')]; needles=('gateway','provider','anthropic','pricing','retry','manifest','env'); [print(p, type(n).__name__, getattr(n,'name','')) for root in roots for p in root.rglob('*.py') for n in ast.walk(ast.parse(p.read_text(encoding='utf-8'))) if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef,ast.Import,ast.ImportFrom)) and any(k in ast.dump(n).lower() for k in needles)]"
~~~

Use the output to update any file list that differs from this plan; do not mutate production or test files during this baseline step.

- [x] Step 4: Map each changed surface to evidence aliases

Record the exact E1, E2, E4, E6, E7, and E9 artifact expected from each later task. Confirm the three split-custody COST-OBS rows remain attributed to both the CORE mechanism and COST-OBS settled evidence.

### Task 2: Replace the agent trust model with strict loopback settings

**Files:**
- Modify: src/optimus/config/gateway.py
- Modify: src/optimus/config/__init__.py
- Test: tests/unit/config/test_gateway_settings.py
- Test: tests/unit/gateway/test_client.py

**Interfaces:**
- Consumes: existing OptimusGatewaySettings.from_env, auth_headers, validate_trusted_gateway, and validate_no_local_provider_keys call sites.
- Produces: frozen OptimusGatewaySettings with gateway_url default http://127.0.0.1:8765, masked SecretStr API key, idempotent strict-loopback validation, and unconditional local-provider-key rejection.

- [x] Step 1: Write failing strict-loopback tests

Replace hosted-origin/production-mode tests with cases covering the actual contract:

~~~python
def test_default_gateway_url_is_loopback():
    settings = OptimusGatewaySettings(optimus_api_key="opt_test")
    assert settings.gateway_url == "http://127.0.0.1:8765"

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8765",
    "https://127.0.0.1:8765",
    "http://localhost:8765",
    "https://[::1]:8765",
])
def test_loopback_urls_are_accepted(url: str):
    OptimusGatewaySettings(gateway_url=url, optimus_api_key="opt_test").validate_trusted_gateway()

@pytest.mark.parametrize("url", [
    "https://gateway.optimus.ai",
    "https://tenant.example",
    "http://example.com",
    "file:///tmp/gateway",
    "http://user:pass@127.0.0.1:8765",
])
def test_non_loopback_or_ambiguous_urls_fail_closed(url: str):
    with pytest.raises(ValueError):
        OptimusGatewaySettings(gateway_url=url, optimus_api_key="opt_test")
~~~

Add tests proving production_mode, extra_trusted_origins, signed_tenant_profile_origins, and ProviderKeyPolicy.IGNORE are no longer accepted fields/exports, while repr, str, safe_model_dump, and auth_headers never expose the secret.

- [x] Step 2: Run the settings tests and verify failure

Run:

~~~powershell
python -m pytest tests/unit/config/test_gateway_settings.py tests/unit/gateway/test_client.py -q
~~~

Expected: the new loopback/default tests fail against hosted/production behavior before implementation.

- [x] Step 3: Implement the minimal settings contract

In gateway.py:

1. Remove BUILT_IN_TRUSTED_GATEWAY_ORIGINS, ProviderKeyPolicy, production_mode, extra_trusted_origins, and signed_tenant_profile_origins.
2. Give gateway_url the loopback default and keep optimus_api_key: SecretStr = Field(min_length=1).
3. Make from_env read OPTIMUS_GATEWAY_URL with the loopback default when omitted and require non-empty OPTIMUS_API_KEY.
4. Make construction-time validation call one safe URL parser that rejects userinfo, missing/ambiguous host, non-HTTP(S) scheme, and every host outside _LOOPBACK_HOSTS.
5. Keep validate_trusted_gateway() as an idempotent callable that invokes the same validator; it must not add a second trust seam.
6. Make validate_no_local_provider_keys() always raise ProviderKeyViolation for any non-empty name in LOCAL_PROVIDER_KEY_NAMES; there is no ignore branch.
7. Remove the retired exports from src/optimus/config/__init__.py while preserving LOCAL_PROVIDER_KEY_NAMES, ProviderKeyViolation, and OptimusGatewaySettings.

- [x] Step 4: Run the settings tests and verify green

Run:

~~~powershell
python -m pytest tests/unit/config/test_gateway_settings.py tests/unit/gateway/test_client.py -q
~~~

Expected: PASS, including secret masking and per-call client trust checks.

### Task 3: Close agent/child environment and credential seams

**Files:**
- Modify: src/optimus/acp/local_infra.py
- Modify: src/optimus/acp/subprocess_env.py
- Modify: src/optimus/acp/launch_policy.py
- Modify: src/optimus/acp/local_gateway_secrets.py
- Modify: src/optimus/acp/launch_gate.py
- Modify: src/optimus/acp/launch_approval_cli.py
- Modify: .env.example, .env.gateway.example, README.md
- Test: tests/unit/acp/test_local_infra.py
- Test: tests/unit/acp/test_acp_subprocess_env.py
- Test: tests/unit/acp/test_launch_policy.py
- Test: tests/unit/acp/test_local_gateway_secrets.py
- Test: tests/unit/acp/test_launch_gate.py
- Test: tests/unit/acp/test_launch_approval_cli.py
- Test: tests/unit/optimus_gateway/test_gateway_env.py

**Interfaces:**
- Consumes: ProviderCredentialResolution, ProviderSecrets.as_gateway_child_env, launch-variable registry, and the existing signed child-manifest construction.
- Produces: an agent environment containing only OPTIMUS_GATEWAY_URL/OPTIMUS_API_KEY for Gateway access, plus a Gateway child environment containing the OpenRouter aggregator key and tool-only variables.

- [x] Step 1: Write failing environment-projection tests

Add assertions that:

~~~python
def test_agent_projection_excludes_every_provider_and_gateway_child_secret():
    projected = strip_local_provider_keys({
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "agent-secret",
        "OPENROUTER_API_KEY": "or-secret",
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-secret",
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "child-secret",
        "OPTIMUS_PRODUCTION_MODE": "false",
        "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://example.com",
    })
    assert projected == {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "agent-secret",
    }
~~~

Add credential-resolution cases showing the default provider is openrouter, only OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY is projected to the child, Anthropic-native credentials are rejected, and any non-OpenRouter provider selection fails with a remediation message.

- [x] Step 2: Run the ACP credential tests and verify failure

Run:

~~~powershell
python -m pytest tests/unit/acp/test_local_infra.py tests/unit/acp/test_acp_subprocess_env.py tests/unit/acp/test_launch_policy.py tests/unit/acp/test_local_gateway_secrets.py tests/unit/optimus_gateway/test_gateway_env.py -q
~~~

Expected: old production-mode/Anthropic projection tests fail before implementation.

- [x] Step 3: Implement the two-environment projection

1. Remove OPTIMUS_PRODUCTION_MODE default injection and all OPTIMUS_EXTRA_GATEWAY_ORIGINS/tenant-origin propagation from local_infra.py, subprocess_env.py, and launch_policy.py.
2. Keep _AGENT_ENVIRON_EXCLUDED_KEYS broad enough to reject every LOCAL_PROVIDER_KEY_NAMES entry, OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY, and OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET.
3. Reduce ProviderSecrets resolution to OpenRouter: resolve OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY from environment/config/keyring, resolve the shared OpenRouter base URL through resolve_effective_base_url(provider="openrouter", ...), and never read ANTHROPIC_API_KEY.
4. Keep tool variables in the Gateway-child projection only; do not make Tavily/Redis configuration a prerequisite for model routes.
5. Update launch gate/approval CLI summaries to show the generic OpenRouter-owned Gateway credential without provider-specific branches or secret values.
6. Update .env.example, .env.gateway.example, and README examples to show only the local agent variables plus the Gateway-child OpenRouter key boundary.

- [x] Step 4: Run the ACP and redaction tests

Run:

~~~powershell
python -m pytest tests/unit/acp tests/unit/optimus_gateway/test_gateway_env.py tests/unit/release/test_credentials.py -q
~~~

Expected: PASS; no agent-facing test can resolve or display a provider key.

### Task 4: Make Gateway child configuration OpenRouter-only

**Files:**
- Modify: src/optimus_gateway/models.py
- Modify: src/optimus_gateway/providers.py
- Modify: src/optimus_gateway/model_mapping.py
- Modify: src/optimus_security/launch_manifest.py
- Modify: src/optimus_gateway/__main__.py
- Test: tests/unit/optimus_gateway/test_models.py
- Test: tests/unit/optimus_gateway/test_providers.py
- Test: tests/unit/optimus_gateway/test_main_entrypoint.py
- Test: tests/unit/security/test_launch_manifest.py
- Test: tests/unit/security/test_gateway_base_url_resolution.py

**Interfaces:**
- Consumes: explicit bind arguments, signed GatewayChildManifest, and resolve_effective_base_url.
- Produces: GatewayServiceConfig with fixed provider == "openrouter", OpenRouter default base URL https://openrouter.ai/api/v1, generic provider key, loopback bind, and optional tool configuration.

- [x] Step 1: Write failing OpenRouter-only configuration tests

Update/add tests for:

~~~python
def test_gateway_service_config_defaults_to_openrouter_and_default_url():
    config = GatewayServiceConfig.from_env(
        {
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "or-key",
        },
        bind_host="127.0.0.1",
        bind_port=8765,
    )
    assert config.provider == "openrouter"
    assert config.base_url == "https://openrouter.ai/api/v1"

def test_non_openrouter_provider_is_rejected():
    with pytest.raises(ValueError, match="openrouter"):
        GatewayServiceConfig.from_env(
            {
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
                "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared",
                "ANTHROPIC_API_KEY": "secret",
            },
            bind_host="127.0.0.1",
            bind_port=8765,
        )
~~~

Add a provider-builder assertion that build_upstream_client(config) returns UrllibOpenAICompatibleClient for the valid config and never constructs an Anthropic client.

- [x] Step 2: Run the Gateway configuration tests and verify failure

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway/test_models.py tests/unit/optimus_gateway/test_providers.py tests/unit/optimus_gateway/test_main_entrypoint.py tests/unit/security/test_launch_manifest.py tests/unit/security/test_gateway_base_url_resolution.py -q
~~~

Expected: old Anthropic/OpenAI provider-selection assertions fail before implementation.

- [x] Step 3: Implement the fixed provider and base URL contract

1. Replace _SUPPORTED_PROVIDERS with the single openrouter provider and make GatewayServiceConfig.from_env reject any non-empty provider selector other than openrouter.
2. Always read OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY; do not branch to ANTHROPIC_API_KEY.
3. Resolve omitted OPTIMUS_LOCAL_GATEWAY_BASE_URL to https://openrouter.ai/api/v1 through the neutral resolver; keep explicit base URL support only for Gateway-child test/approved transport configuration and never expose it to the agent.
4. Make build_upstream_client return only UrllibOpenAICompatibleClient.
5. Keep the signed manifest’s provider field as the fixed value openrouter; preserve HMAC binding of base URL, provider key fingerprint, shared secret fingerprint, and code-derived loopback bind.
6. Remove direct OpenAI/Anthropic model mappings. Keep the OpenRouter alias claude-haiku -> anthropic/claude-haiku-4.5 and OpenRouter slash-qualified passthrough validation.

- [x] Step 4: Run configuration and manifest tests

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway/test_models.py tests/unit/optimus_gateway/test_providers.py tests/unit/optimus_gateway/test_main_entrypoint.py tests/unit/security/test_launch_manifest.py tests/unit/security/test_gateway_base_url_resolution.py -q
~~~

Expected: PASS with no provider-specific secret branch.

### Task 5: Replace the upstream client with provider metadata and bounded model retries

**Files:**
- Modify: src/optimus_gateway/upstream_client.py
- Modify: src/optimus_gateway/tool_provider_http.py only for a compatibility adapter if the callback type changes; preserve its retry count and classification behavior.
- Delete: src/optimus_gateway/anthropic_client.py after its direct adapter exports are removed.
- Test: tests/unit/optimus_gateway/test_upstream_client.py
- Test: tests/unit/optimus_gateway/test_upstream_retry.py
- Test: tests/unit/optimus_gateway/test_tool_providers.py when callback compatibility is exercised

**Interfaces:**
- Consumes: OpenRouter-compatible Chat Completions JSON and response headers.
- Produces: ProviderMessageResult with provider-reported accounting and attribution, and a model-path retry event stream.

Use these normalized types (field names are the cross-task contract):

~~~python
@dataclass(frozen=True)
class RetryEvent:
    attempt: int
    classification: str
    latency_seconds: float
    disposition: Literal["retry", "terminal"]

@dataclass(frozen=True)
class ProviderMessageResult:
    message_id: str
    output_text: str
    input_tokens: int
    output_tokens: int
    total_tokens: int | None
    billing_units: int
    cost_usd: Decimal
    provider: str
    resolved_provider: str | None
    requested_model: str
    resolved_model: str | None
    model_version: str | None
    cache_hit: bool
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    cache_age_seconds: int | None = None
~~~

- [x] Step 1: Write failing parser tests

Add a representative OpenRouter body and headers:

~~~python
body = {
    "id": "gen-1",
    "model": "anthropic/claude-haiku-4.5",
    "choices": [{"message": {"role": "assistant", "content": "hello"}}],
    "usage": {
        "prompt_tokens": 42,
        "completion_tokens": 18,
        "total_tokens": 60,
        "cost": "0.00042",
        "prompt_tokens_details": {"cached_tokens": 12},
    },
    "openrouter_metadata": {"provider": "Anthropic", "model": "claude-haiku-4.5"},
}
headers = {
    "X-OpenRouter-Cache-Status": "HIT",
    "X-OpenRouter-Cache-Age": "31",
}
~~~

Assert message text, generation ID, provider == openrouter, resolved provider/model, billing_units == 60, cost_usd == Decimal("0.00042"), cached tokens, and cache_hit is True.

Add parametrized failures for absent/null/negative/NaN/Infinity/boolean/string-invalid cost, missing usage, missing provider-reported total/billing units, invalid token types, missing ID/choices/message/content, and malformed router metadata. Unknown additive fields must not fail a valid response.

- [x] Step 2: Write failing retry tests

Change the existing four-attempt expectation to:

~~~python
def test_model_retry_ceiling_is_three_attempts(monkeypatch):
    # fake urlopen raises HTTP 429 every time
    with pytest.raises(RuntimeError, match="429"):
        client.create_message(model="anthropic/claude-haiku-4.5", input_text="hi")
    assert attempts == [1, 2, 3]
    assert [event.disposition for event in events] == ["retry", "retry", "terminal"]
~~~

Assert event attempt number, transient/permanent classification, measured non-negative latency, sanitized context, and no retry for 401, malformed JSON, malformed usage, or malformed cost. Add a tool-provider regression test proving its existing helper default and callback behavior remain unchanged.

- [x] Step 3: Implement response capture, typed parsing, and retry events

1. Make _urlopen_json return a decoded body plus a case-insensitive response-header mapping; never discard headers.
2. Add X-OpenRouter-Metadata: enabled to the OpenRouter request and retain cache status/age headers for parsing.
3. Parse usage.cost as a finite non-negative Decimal; reject booleans, null, strings that do not parse, negative values, and non-finite values.
4. Require the provider-reported billing total (usage.total_tokens or the documented provider billing-unit field) and never derive it by summing local counters.
5. Parse prompt/completion/reasoning/cached token details when present, body model/version, router metadata, and case-insensitive cache status. Preserve provider == openrouter when actual provider metadata is absent.
6. Add an explicit max_attempts=3 argument on the model client. Keep the helper’s existing default for tool HTTP calls. Emit RetryEvent for every failed attempt and retain the legacy integer callback only where tool callers still require it.
7. Retire the direct adapter in this task: remove UrllibAnthropicClient, parse_anthropic_message, and _extract_anthropic_output_text from upstream_client.py; delete the anthropic_client.py compatibility re-export; and replace test_parse_anthropic_message_maps_usage_fields with a direct-adapter-absence assertion. This keeps Task 5’s own upstream test checkpoint green after ProviderMessageResult gains required accounting fields.

- [x] Step 4: Run upstream and tool regression tests

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway/test_upstream_client.py tests/unit/optimus_gateway/test_upstream_retry.py tests/unit/optimus_gateway/test_tool_providers.py -q
~~~

Expected: PASS; model calls stop at three total attempts, tool calls retain their prior retry behavior, and no provider accounting fallback exists.

### Task 6: Build GatewayUsage from provider-reported accounting and preserve route shapes

**Files:**
- Modify: src/optimus_gateway/responses.py
- Modify: src/optimus_gateway/chat_completions.py only when normalized result fields require an envelope update
- Modify: src/optimus/gateway/models.py
- Modify: src/optimus_gateway/pricing.py (remove settled-cost path; retain no fallback)
- Modify: src/optimus/acp/dispatcher.py only for additive serialization of new optional usage fields
- Test: tests/unit/optimus_gateway/test_responses.py
- Test: tests/unit/optimus_gateway/test_server.py
- Test: tests/unit/gateway/test_models.py
- Test: tests/unit/gateway/test_usage_fields.py
- Test: tests/unit/optimus_gateway/test_pricing.py (replace local-pricing assertions with retirement assertions)
- Test: tests/integration/gateway/test_one_key_mocked_run.py

**Interfaces:**
- Consumes: ProviderMessageResult from Task 5 and the existing run_model_completion callback shape.
- Produces: gateway_usage with provider-reported cost_usd, billing_units, cache state, provider/model attribution, and optional token detail; both routes return their existing response shape.

- [x] Step 1: Write failing response/accounting tests

Use a fake result with explicit provider accounting:

~~~python
FakeProviderResult(
    message_id="gen-1",
    output_text="ok",
    input_tokens=42,
    output_tokens=18,
    total_tokens=60,
    billing_units=60,
    cost_usd=Decimal("0.00042"),
    provider="openrouter",
    resolved_provider="Anthropic",
    requested_model="claude-haiku",
    resolved_model="anthropic/claude-haiku-4.5",
    model_version=None,
    cache_hit=True,
)
~~~

Assert GatewayUsage.provider == openrouter, resolved_provider == Anthropic, provider request ID, requested alias, resolved model/version, billing_units == 60, cost_usd == Decimal("0.00042"), and cache state. Assert that /v1/responses rejects messages, /v1/chat/completions rejects input, mixed shapes do not invoke the upstream client, and both routes use the same normalized result path.

Add parametrized run_model_completion failures for each malformed cost/billing case. Assert status is a sanitized upstream failure, output is not emitted, and the fake client is called once because malformed accounting is permanent.

- [x] Step 2: Run response/accounting tests and verify failure

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway/test_responses.py tests/unit/optimus_gateway/test_server.py tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py tests/integration/gateway/test_one_key_mocked_run.py -q
~~~

Expected: old locally computed cost/cache assertions fail before implementation.

- [x] Step 3: Implement the provider-reported usage envelope

1. Remove lookup_model_rate, compute_cost_usd, and local token-sum billing from run_model_completion.
2. Build gateway_usage from ProviderMessageResult; keep model as the agent alias, use the returned resolved model/version when available, and set provider to the aggregator identity.
3. Extend GatewayUsage only additively with resolved_provider, resolved_model, input_tokens, output_tokens, total_tokens, reasoning_tokens, cached_tokens, and cache_age_seconds optional fields. Preserve existing optional compatibility fields (service, native_unit, optimus_credits_debited, price_snapshot_id) without fabricating settled cost.
4. Make assert_gateway_usage_contract reject non-finite Decimal values (NaN, Infinity, -Infinity) as well as null, negative, invalid, or boolean billing units.
5. Keep GatewayClient and ACP dispatcher parsing/serialization additive; existing tool envelopes and error-body usage parsing must continue to use the same strict parser.
6. Reduce pricing.py to no settled-cost calculation. If a diagnostic snapshot helper remains, its output must be marked diagnostic, omitted from settled cost_usd, and never be used as a fallback.

- [x] Step 4: Run route and accounting tests

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway/test_responses.py tests/unit/optimus_gateway/test_server.py tests/unit/gateway/test_models.py tests/unit/gateway/test_usage_fields.py tests/integration/gateway/test_one_key_mocked_run.py -q
~~~

Expected: PASS with provider cost preserved exactly and malformed accounting failing closed before success.

### Task 7: Retire direct adapters and update compatibility fixtures

**Files:**
- Read-only verification: src/optimus_gateway/anthropic_client.py (deleted in Task 5)
- Modify: src/optimus_gateway/upstream_client.py (direct adapter retired in Task 5; verify no direct branch remains)
- Modify: src/optimus_gateway/providers.py (completed in Task 4; verify no direct branch remains)
- Modify: src/optimus_gateway/model_mapping.py (completed in Task 4; verify no direct aliases remain)
- Modify: src/optimus/config/__init__.py (completed in Task 2; verify no retired exports remain)
- Modify: tests and fixtures that import/select UrllibAnthropicClient, Anthropic provider, or direct OpenAI provider
- Test: tests/unit/optimus_gateway/test_upstream_client.py
- Test: tests/unit/optimus_gateway/test_upstream_retry.py
- Test: tests/unit/optimus_gateway/test_models.py
- Test: tests/unit/optimus_gateway/test_providers.py
- Test: tests/unit/optimus_gateway/test_main_entrypoint.py
- Test: tests/unit/acp/test_local_gateway_secrets.py

**Interfaces:**
- Consumes: fixed OpenRouter provider contract from Tasks 3–6.
- Produces: no import, branch, alias, credential resolver, manifest fixture, or test fixture that can select a direct Anthropic/OpenAI model path.

- [x] Step 1: Write the retirement guard test

Add a source-level regression test that imports the production provider module and asserts UrllibOpenAICompatibleClient is the only upstream class constructed. Add a repository search assertion in the task notes for zero production references to UrllibAnthropicClient, parse_anthropic_message, and direct provider aliases after cleanup.

- [x] Step 2: Remove remaining stale fixtures and imports

Replace remaining Anthropic/OpenAI config helpers in ACP, manifest, and Gateway entrypoint tests with one _openrouter_config() helper, update fake results to include provider-reported cost fields, and verify no test imports the deleted direct adapter module. Keep direct tool-provider tests untouched.

- [x] Step 3: Run the retirement and full Gateway unit slice

Run:

~~~powershell
python -m pytest tests/unit/optimus_gateway tests/unit/acp/test_local_gateway_secrets.py tests/unit/config/test_gateway_settings.py -q
~~~

Expected: PASS, with rg -n "UrllibAnthropicClient|parse_anthropic_message|provider.*anthropic|provider.*openai" src/optimus_gateway src/optimus/acp src/optimus_security returning no direct model-path references.

### Task 8: Verify real local-process, Gateway, credential, and egress evidence

**Files:**
- Modify: tests/integration/optimus_gateway/gateway_env.py to remove provider matrix/Anthropic key resolution and build only an OpenRouter child manifest.
- Modify: tests/integration/optimus_gateway/test_gateway_live_smoke.py to exercise both completion shapes and capture provider/accounting fields.
- Modify: tests/integration/gateway/test_gateway_live.py only where provider-reported cost assertions need the fixed OpenRouter contract.
- Modify: tests/integration/gateway/test_failed_usage_transport_flow.py to cover malformed provider accounting and no retry.
- Modify: tests/integration/gateway/test_one_key_mocked_run.py to use loopback agent settings and preserve the one-key boundary.
- Read-only evidence: tests/integration/release/*, tests/e2e/acp/*, egress scanners, and independent acpx client.

**Interfaces:**
- Consumes: signed OpenRouter child manifest, only Gateway-child provider credential, and Tasks 2–7 contracts.
- Produces: named E1, E2, E4, E6, E7, and E9 artifacts with real dependencies at the tiers that require them.

- [x] Step 1: Add deterministic local-process tests first

Use a loopback ThreadingHTTPServer only for unit/integration transport behavior. Return a valid OpenRouter-shaped body with explicit usage.cost, usage.total_tokens, and cache headers; return malformed cost in a second handler. Assert valid output includes settled cost and malformed cost stops after one request with no ledger entry or successful output.

- [x] Step 2: Run the local-process evidence

Run:

~~~powershell
python -m pytest tests/integration/gateway/test_failed_usage_transport_flow.py tests/integration/gateway/test_one_key_mocked_run.py -q
~~~

Expected: PASS with deterministic request counts and no fake provider key in the agent environment.

- [x] Step 3: Update and run the real Gateway smoke harness

The requires_live_gateway harness must resolve only OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY, build a manifest with provider="openrouter", and remove all Anthropic/OpenAI matrix branches. Run the real child process with the independently authored acpx client for ACP protocol evidence where required. Exercise /v1/responses and /v1/chat/completions, record returned provider/model/cache/cost fields, and enforce the configured live cost cap.

Run:

~~~powershell
python -m pytest tests/integration/optimus_gateway/test_gateway_live_smoke.py -m requires_live_gateway -q
python -m pytest tests/integration/gateway/test_gateway_live.py -m requires_gateway -q
~~~

Expected: real OpenRouter responses provide finite provider-reported cost and billing units; no direct provider egress occurs.

- [x] Step 4: Run the credential and egress evidence

Run the release credential/launch suites and the repository’s approved egress scan. Confirm the agent process resolves only OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY; the Gateway child alone resolves the OpenRouter credential; no direct OpenAI/Anthropic/Tavily/LangSmith egress is added by CORE.

### Task 9: Repository-wide verification and handoff

**Files:**
- Read-only: all changed files and the approved design/plan/checkpoint documents.
- Evidence outputs: test reports, coverage report, Ruff output, git diff --check, and live artifacts named in the task notes.

**Interfaces:**
- Consumes: green task-level tests and real-tier artifacts from Tasks 2–8.
- Produces: release-gate verification record; no commit or push.

- [x] Step 1: Run the affected unit suites together

Run:

~~~powershell
python -m pytest tests/unit/config tests/unit/gateway tests/unit/optimus_gateway tests/unit/security tests/unit/acp tests/unit/release -q
~~~

Expected: PASS with no skipped test silently standing in for a required real dependency.

- [x] Step 2: Run integration suites allowed by the local environment

Run:

~~~powershell
python -m pytest tests/integration/gateway tests/integration/optimus_gateway tests/integration/telemetry tests/integration/release -q
~~~

Run requires_redis, requires_gateway, requires_live_gateway, and e2e selections separately only when their real dependencies and credentials are available; report each unrun tier explicitly.

- [x] Step 3: Run coverage and static gates

Run:

~~~powershell
python -m pytest --cov=src --cov-report=term-missing --cov-report=xml -q
python -m ruff check .
git diff --check
~~~

Expected: aggregate production coverage is at least 80%, Ruff is clean, and git diff --check reports no whitespace errors.

- [x] Step 4: Re-run the retirement and custody searches

Run:

~~~powershell
rg -n "UrllibAnthropicClient|parse_anthropic_message|OPTIMUS_PRODUCTION_MODE|OPTIMUS_EXTRA_GATEWAY_ORIGINS|ProviderKeyPolicy|MODEL_RATES|compute_cost_usd|gateway\.optimus\.ai" src/optimus src/optimus_gateway src/optimus_security README.md .env.example .env.gateway.example
rg -n "usage\.cost|billing_units|resolved_provider|X-OpenRouter-Metadata|X-OpenRouter-Cache-Status" src/optimus_gateway tests
~~~

Expected: no retired trust/direct-adapter/local-pricing production surface remains; provider accounting and metadata are covered by code/tests.

- [x] Step 5: Update the reviewer checkpoint log and hand off

Record the exact test commands, dependency tiers run, coverage percentage, Ruff result, egress artifact paths, and any unrun release gates in docs/superpowers/reviews/plan-11-4-review-checkpoints.md. Do not mark a plan checkbox complete without the command named by that checkbox passing. Do not commit or push without a separate request.

## Definition of Done

- All 54 inventory rows have an explicit task and ownership disposition, including the three split-custody COST-OBS rows.
- Agent settings and environment expose only the loopback Gateway URL/key contract; no hosted, tenant, production-mode, extra-origin, signed-profile, or provider-key bypass remains.
- The Gateway child defaults to and routes through OpenRouter using one OpenAI-compatible transport; direct Anthropic/OpenAI adapters and aliases are retired.
- Responses and Chat Completions retain their distinct wire shapes while sharing normalized provider/model/cache/accounting handling.
- Settled cost_usd and billing units come from provider response fields; malformed accounting fails closed and never retries.
- Model retries are capped at three total attempts with structured attempt/classification/latency/disposition evidence, while tool retry behavior is unchanged.
- E1/E2/E4/E6/E7/E9 artifacts are produced with real named dependencies where required; ACP protocol evidence uses independent acpx if invoked.
- Affected tests, full approved suite, coverage at least 80%, Ruff, and git diff --check pass.
- No source-document redline, Vercel endpoint, TOOLS redesign, COST-OBS persistence migration, MCP endpoint, commit, or push is included in this plan execution.
