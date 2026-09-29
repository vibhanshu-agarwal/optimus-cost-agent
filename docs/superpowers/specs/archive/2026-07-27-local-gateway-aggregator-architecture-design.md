# Local Gateway Aggregator Architecture Design Note

**Status:** Approved 2026-07-27; document redline authorized, implementation still requires separate plans
**Date:** 2026-07-27
**Authority:** `docs/superpowers/reports/2026-07-27-local-gateway-architecture-correction-brief.md`, with v3 outranking v2 and v1
**Applies to:** Phase 1 local Optimus Gateway model access, evidence acquisition, accounting, and observability

## 1. Decision summary

The local Optimus Gateway remains the only network boundary visible to the agent. The Gateway uses
one upstream aggregator account to provide model access, normalized upstream billing, and
deterministic web search. OpenRouter is the default upstream. Vercel AI Gateway is an allowed
secondary upstream only if a later Python integration spike shows modest effort; otherwise it is
backlogged.

The architectural thesis is therefore retained and retargeted:

> one agent key, one Gateway policy boundary, one aggregator balance, one normalized ledger, and
> many models behind the curtain.

This is not a hosted-service requirement. Phase 1 may run the Gateway locally on strict loopback.
The agent still receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; the aggregator credential
exists only in the Gateway process.

The one-aggregator-key property for both models and search is a Phase 1 capability, not a permanent
guarantee. OpenRouter has deprecated the only deterministic aggregator-level search mechanism, and
neither its documented successor nor Vercel's search contract guarantees that a search occurs.
Withdrawal of the plugin may therefore require either a verified-or-fail successor or a return to a
standalone search provider with a second key and balance.

Web search is a distinct, minimal model call made by a Gateway-owned provider adapter. It is never
attached to the main generation call. The deterministic OpenRouter web plugin is selected because it
performs exactly one search for a request, before the model answers; the newer OpenRouter server tool
is not selected because the model may elect whether and how often to search. That distinction is
required by the existing harness gate, `ToolInvocationPolicy`, per-tool call cap, and
`EvidenceLedger`.

Observability becomes OpenTelemetry-native. The agent submits structured trace data through the
Gateway boundary; the Gateway exports OTLP spans. Arize Phoenix is the documented local default.
LangSmith and the amortized-observability-cost model are removed.

## 2. Verified current-state findings

The following are source findings, not assumptions:

1. `src/optimus_gateway/providers.py` currently chooses a direct Anthropic client when
   `config.provider == "anthropic"`. The implementation is in
   `src/optimus_gateway/upstream_client.py`; `src/optimus_gateway/anthropic_client.py` is a
   compatibility re-export. Removing the direct provider path therefore requires removing both the
   branch and the implementation/re-export surface.
2. `UrllibOpenAICompatibleClient` sends only `model` and `messages`, and returns only assistant text,
   request ID, and token counts. It does not accept search options or retain annotations, raw usage
   cost, resolved provider, or cache detail.
3. Model completion cost is currently calculated from the local static table in
   `src/optimus_gateway/pricing.py`. This conflicts with the settled rule that provider-reported
   usage and cost are authoritative when available.
4. `build_tool_dependencies()` returns `None` unless Tavily credentials, Redis, and an allowed-domain
   policy are all configured. `src/optimus_gateway/server.py` then returns 404 for all four tool
   routes. Tavily absence therefore disables the independent PyPI/npm/Maven and OSV providers.
5. `GatewayToolDependencies` requires one non-optional web provider and the server exposes tools as
   one bundle. Capability availability is not route-specific.
6. Search results are already re-authorized by `GatewayToolPolicy` after the provider returns them.
   Extract already requires prior Gateway-recorded search provenance. These controls survive.
7. `src/optimus_gateway/observability.py` currently validates and acknowledges trace events but has
   no exporter. `src/optimus/telemetry/observability.py` sends project-specific JSON events, not
   OTLP. No LangSmith, LangChain, OpenTelemetry, or Phoenix dependency exists in `pyproject.toml`.

## 3. Selected architecture

### 3.1 Runtime boundary

```text
Agent process
  |
  | OPTIMUS_API_KEY; loopback OPTIMUS_GATEWAY_URL
  v
Local Optimus Gateway
  |-- model completion adapter --------------------\
  |-- deterministic evidence-search adapter --------+--> OpenRouter account/balance
  |-- direct HTTPS extract adapter                  |
  |-- package registry + OSV adapters               |
  |-- usage normalization + policy + telemetry -----/
  |
  `-- OTLP exporter --> Phoenix by default
```

The Gateway listener remains restricted to `127.0.0.1`, `localhost`, or `::1`; standalone launch
must not derive its bind address from ambient inherited environment. This design does not weaken the
existing launch approval, credential projection, bearer authorization, or forbidden-egress gates.

### 3.2 Upstream model adapters

`UrllibOpenAICompatibleClient` is the single Phase 1 model-completion transport. It covers
OpenRouter and, if retained after its later integration check, Vercel AI Gateway. The direct
Anthropic branch, `UrllibAnthropicClient`, compatibility re-export, native Anthropic credential
path, configuration enum value, examples, and tests are retired together.

The surviving client must parse provider-returned accounting fields instead of making the local
price table authoritative. The normalized Gateway envelope continues to contain at least:

- `gateway_request_id`
- actual provider and provider request ID
- resolved model/version where returned
- cache status/details
- provider-reported billing units and token detail
- provider-reported `cost_usd`

If an upstream response lacks mandatory accounting, the Gateway fails closed. A local price snapshot
may be retained only as explicitly labelled diagnostic metadata; it must not overwrite or fabricate
the settled provider cost.

### 3.3 Deterministic evidence search

The Gateway receives the existing typed `/v1/tools/web/search` request only after the agent-side
harness authorizes the tool call. It then:

1. re-derives and authorizes the policy signal and effective domain intersection;
2. consumes the existing per-run/per-tool call-cap token;
3. sends a dedicated, minimal Chat Completions request using one cheap Flash/Haiku-class model,
   low `max_tokens`, and OpenRouter's deterministic `web` plugin;
4. supplies the effective allowlist as `include_domains` and configured denials as
   `exclude_domains`, using the default search engine;
5. parses only standardized `url_citation` annotations into `WebSearchResult` values;
6. independently rejects every returned URL outside the effective allowlist;
7. records approved URLs for extract provenance; and
8. returns provider-reported usage/cost for the `EvidenceLedger`.

Assistant prose is not evidence and is not promoted into search results. Missing/malformed
annotations, a returned off-policy URL, or missing usage/cost fails the search call closed.

The plugin is currently documented by OpenRouter as deprecated in favor of its server tool. The
deprecated plugin remains the selected Phase 1 mechanism because it always searches once, whereas
the server tool lets the model decide whether and how often to search. The server tool's
`max_results`, `max_uses`, `max_total_results`, and top-level `max_tool_calls` are documented as
upper bounds; none is a documented minimum. OpenRouter documents generic `tool_choice` controls for
function tools and forced use for some other server-tool scenarios, but it does not document a
web-search-specific required/minimum contract. That possibility must be proved live before it can be
treated as deterministic.

This is an explicit compatibility risk. Removal or behavioral change of the deterministic plugin
blocks release. The designated successor evaluation is **verified-or-fail search**:

1. the Gateway decides to search and sends a dedicated search-only request;
2. it exposes only `openrouter:web_search`, with `max_uses: 1` and a one-call server-tool budget;
3. it requires a provider-reported search-use count and non-empty, valid URL annotations; and
4. it fails the typed tool call closed if the model does not search or the evidence is malformed.

Verified-or-fail preserves the harness gate because the Gateway—not the model—decides whether a
search is authorized. It verifies execution rather than guaranteeing it by construction. It is not
the current implementation and is not accepted until a separate live spike proves one search, zero
unrequested extra searches, annotation/domain behavior, and accounting across the chosen model
route.

### 3.3.1 Latency tradeoff

The approved spike measured 21,206.1 ms across three search calls: 7,068.7 ms mean per call. At three
to five sequential searches per run, that measured mean projects to 21.2-35.3 seconds of added
wall-clock time. The delay is structural to the minimal-model-call pattern because each search pays
aggregator routing, model queue, search injection, and inference latency.

The review baseline places typical Tavily search latency at approximately 1-2 seconds; that
comparison was not measured in this spike and must not be presented as project-generated evidence.
The OpenRouter latency is accepted for Phase 1 because deterministic harness integration and a
single balance currently outweigh interactive speed. Production telemetry must record per-search
latency, and a future implementation plan should consider safe concurrency for independent searches
without weakening per-tool call caps, deterministic ledger order, or policy revalidation.

Official references:

- OpenRouter deterministic plugin, annotations, filters, engine behavior, and pricing:
  <https://openrouter.ai/docs/guides/features/plugins/web-search>
- OpenRouter server-tool behavior and plugin deprecation:
  <https://openrouter.ai/docs/guides/features/server-tools/web-search>
- OpenRouter provider-reported usage accounting:
  <https://openrouter.ai/docs/cookbook/administration/usage-accounting>

### 3.4 Direct extract

`/v1/tools/web/extract` no longer calls Tavily after the search spike is accepted. It performs a
bounded Gateway-side HTTPS fetch followed by HTML-to-text conversion. "Plain HTTP fetch" means a
normal HTTP client rather than a search/extract vendor; it does not relax the existing HTTPS-only
URL policy.

The adapter must retain these controls:

- the URL must be an exact prior approved search result for the same run;
- every redirect target is revalidated before follow;
- non-HTTPS, userinfo, disallowed host/port, private/link-local/loopback address, and DNS rebinding
  cases fail closed;
- response bytes, redirects, time, and decoded characters are bounded;
- executable content is never evaluated;
- unsupported media types are rejected;
- the returned URL must remain the requested, authorized provenance URL; and
- the result records fetch request ID, byte/character counts, cache state, and zero external
  provider cost without pretending a vendor reported billing.

The spike may use a small standalone parser to establish feasibility. Production choice of a parser
and its security limits belongs in the implementation plan.

### 3.5 Independent tool capabilities

Tool configuration changes from an all-or-nothing bundle to route-specific capabilities sharing
policy and state:

- web search requires the aggregator search adapter, domain policy, and Redis-backed call/provenance
  state;
- web extract requires the direct fetch adapter, domain policy, and Redis-backed provenance state;
- package lookup requires its registry adapter, policy, and Redis-backed call state;
- security advisory lookup requires its OSV adapter, policy, and Redis-backed call state.

The server dispatches every known tool path independently. A known but unconfigured capability
returns an explicit unavailable response; it does not make unrelated routes disappear. In
particular, PyPI/npm/Maven and OSV remain usable without Tavily.

Tavily remains in the tree behind its existing adapter until the OpenRouter replacement acceptance
tests and rollback review pass. It is then deleted under the operator ruling rather than retained as
a permanently supported backend. The rollback review must explicitly record that this is a
deliberate deletion despite a plausible future need: no deterministic aggregator successor is
currently documented, so withdrawal of the deprecated plugin could require restoring Tavily—or
introducing direct Exa/Parallel search—with a second key and balance. The version-control history and
this design note are the rollback trail; production does not carry two active search backends merely
for speculation.

### 3.6 Observability

The canonical data model is OpenTelemetry spans and the canonical wire format is OTLP. Existing
domain events may be mapped to span attributes/events, but downstream-vendor JSON must not become the
internal contract. Sensitive prompts, responses, tool parameters, and errors follow the existing
redaction policy before export.

The local default is Phoenix because it accepts OTLP and supplies a local collector/UI. Optimus
depends on the OTel SDK/exporter contract, not Phoenix APIs. A remote OTLP-compatible backend,
including Langfuse at team scale, can replace Phoenix without changing agent instrumentation.

The Gateway must expose one deliberate topology in the implementation plan: either authenticated
project JSON ingress translated to OTLP in the Gateway, or authenticated OTLP/HTTP ingress proxied
by the Gateway. The current `/v1/observability/traces` JSON contract makes the first the lower-drift
migration, provided the translation is lossless for required trace fields. The implementation plan
must not introduce a second direct agent-to-Phoenix egress path.

Observability has infrastructure cost but no invented per-request `cost_usd`. LangSmith references,
credentials, export behavior, and allocated/amortized observability charges are deleted.

Official references:

- OpenTelemetry Python OTLP exporters:
  <https://opentelemetry.io/docs/languages/python/exporters/>
- OTLP exporter configuration and retry contract:
  <https://opentelemetry.io/docs/specs/otel/protocol/exporter/>
- Phoenix OTLP collector model:
  <https://arize.com/docs/phoenix/tracing/concepts-tracing/how-does-tracing-work>

### 3.7 Vercel AI Gateway disposition

Vercel AI Gateway remains an allowed second OpenAI-compatible model endpoint, not a Phase 1 search
dependency. Its public Gateway documentation confirms OpenAI-compatible Chat Completions and a
single key across models. The currently located search-tool examples are TypeScript AI SDK
integrations where the model elects to invoke a tool, which does not satisfy the deterministic
search contract.

After the OpenRouter path is settled, a time-boxed Python transport check may retain Vercel if it
requires only base URL, credential, model-name, and response-accounting mapping changes. Any SDK
dependency, model-elected search integration, or non-modest response translation moves it to the
named backlog. There is no provider comparison matrix in this work.

Reference: <https://vercel.com/docs/ai-gateway>

## 4. Alternatives considered

### A. OpenRouter deterministic web plugin — selected

It preserves one aggregator balance, searches exactly once per authorized request, returns
standardized annotations, and supports domain filters. The deprecation risk is explicit and must be
covered by a live release gate.

### B. OpenRouter server web-search tool — rejected for Phase 1

It is the recommended successor to the plugin and can cap total results, but the model controls
whether and how often it searches. That makes the harness's one-authorized-call accounting and
evidence-first contract nondeterministic. It is nevertheless the designated first contingency under
the verified-or-fail contract in section 3.3: dedicated request, `max_uses: 1`, one-call budget,
mandatory annotations and usage evidence, and fail-closed behavior when no search occurs.

### C. Attach `:online` or search to main generation — rejected

It combines evidence acquisition with generation, bypasses the dedicated harness decision, obscures
per-search cost/call caps, and makes annotations incidental to a larger completion.

### D. Keep Tavily as the primary web provider — rejected after replacement acceptance

It retains a second vendor credential and balance and leaves the original one-key thesis unresolved.
It remains only as a rollback seam until the replacement is proven.

### E. Extend the generic completion client with arbitrary plugin options — rejected

It would leak provider-specific search semantics into the common model path and make it easier to
attach search to ordinary generation. A dedicated provider adapter may share low-level authenticated
HTTP transport, but owns its request and annotation parser.

## 5. Verification and evidence gates

No architecture claim below is complete without its named evidence:

| Claim | Required evidence |
|---|---|
| Minimal generation still returns usable annotations | Live OpenRouter response with chosen model, exact `max_tokens`, annotation count, completion-token count, latency, and provider-reported cost |
| Domain filters are policy-capable | Repeated live include/exclude probes; every annotation URL recorded; zero off-policy URLs required |
| Citation quality is adequate | Operator-readable sample showing URL, title, non-empty content/snippet, relevance rubric, and measured pass count |
| Direct extract is viable | Live HTTPS fetch of an approved result with status, redirects, bytes, parse time, output characters, and content-quality rubric |
| Free tools survive without Tavily | Unit/server-route tests with no Tavily key proving package and OSV routes are exposed and callable |
| Search remains harness-gated | Unit/integration tests proving signal, allowlist, call cap, returned-URL revalidation, provenance, and ledger recording |
| Billing remains authoritative | Contract tests using upstream `usage.cost`; missing/malformed cost fails closed; no local estimate replaces it |
| Plugin remains deterministic | Live release probe produces exactly one deterministic search result set per authorized call or release blocks; if blocked, verified-or-fail successor spike is the first contingency |
| Observability is vendor-neutral | OTLP integration evidence against real Phoenix plus a backend-agnostic exporter contract test |
| One-key boundary holds | Release egress/credential scan with only agent-facing `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` |

The OpenRouter spike is restricted to the first four rows. It uses one cheap Flash/Haiku-class
model, the default engine, and four questions only: annotation survival, domain enforcement,
citation adequacy, and direct extract viability. Search-engine pricing options are recorded from
official documentation but not optimized or compared at Phase 1 volume.

## 6. Migration order

1. Complete and record the narrow OpenRouter spike without deleting Tavily.
2. Obtain operator approval of this design note.
3. Produce the HLD/LLD/Test Strategy v1.5/Guardrails redline from v3 and measured spike evidence.
4. Create separate implementation plans for:
   - upstream aggregator and provider-accounting changes;
   - deterministic search and direct extract;
   - route-specific tool dependency wiring;
   - OTel/Phoenix observability;
   - strict-loopback completion;
   - USD field rename.
5. Implement with TDD in the approved lanes.
6. Remove Tavily only after replacement acceptance tests and rollback review pass; record the
   deliberate deletion and the second-key fallback risk.
7. Generate PDFs only after source-document approval and only with operator approval for any Pandoc
   or WeasyPrint installation.

## 7. Explicit non-goals and custody

- No MCP endpoint, diagram implication, or implementation is introduced.
- `P11-FU-3` remains open.
- `P11-FEAT-GATEWAY-MCP` remains blocked.
- No PDF or source-document redline is started by this note.
- No USD/credit field rename is folded into provider/search work.
- No hosted Optimus service is required.
- No Vercel/OpenRouter model or search-engine comparison matrix is produced.
- One-key-for-search is not promised beyond the lifetime of an accepted aggregator search contract.
- No provider-adapter, Tavily, observability, or test code is changed before design approval and a
  separately approved implementation plan.

## 8. Approval record

The operator approved this design note and the measured spike on 2026-07-27. The approval authorizes
the HLD/LLD/Test Strategy/Guardrails redline. It does not approve implementation or PDF generation.
