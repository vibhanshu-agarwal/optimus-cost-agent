---
title: "Optimus-Cost-Agent - Test Strategy v1.5"
lang: en
---

::: {.sheet .cover data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="1" data-total="14"}
<div class="eyebrow">Optimus-Cost-Agent</div>

# Test Strategy

<div class="subtitle">Validation Plan - Phase 1, Sprint 1 - Gateway-Centric Local Runtime</div>

<div class="version">Version 1.5</div>

<div class="credit">Architected by: Vibhanshu Agarwal</div>
:::
::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="2" data-total="14"}
# 1. Test objectives

The strategy proves that a developer can complete full Plan and Agent runs with only
`OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent process. No upstream credential is
resolvable by the agent. Separately, the loopback Gateway receives exactly its approved aggregator
credential and never exposes it.

# 2. Scope and non-scope

In scope:

- strict loopback URL and bind enforcement, including WSL2 same-network-namespace topology;
- OpenRouter default and bounded Vercel option through the OpenAI-compatible transport;
- deterministic search live compatibility and plugin deprecation gate;
- include/exclude domain enforcement and returned-URL revalidation;
- independent package/OSV routes without search configuration;
- bounded extract provenance, redirect, SSRF, media, size, and time controls;
- provider-reported usage/cost authority and full request attribution;
- OTel/OTLP export to a real Phoenix tier;
- separate agent and Gateway credential/egress scans.

Out of scope:

- hosted staging Gateway, OAuth/device flow, tenants, org/project wallets, Vault;
- direct provider adapters;
- cross-run spend policy (`P9.85-FU-3`);
- MCP Gateway endpoint or contract;
- engine/model comparison matrices.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="3" data-total="14"}
# 3. Test pyramid and evidence tiers

| Tier | Dependency | Fakes permitted | Claim supported |
|---|---|---:|---|
| Unit | In-process functions | Yes | Local logic and contracts |
| Contract | Recorded request/response shape | Yes | Parser and schema behavior |
| `requires_redis` | Real TimeSeries-capable Redis | No | Persistence and retention |
| `requires_gateway` | Real loopback Gateway + approved credential | No | Gateway/provider behavior |
| ACP protocol | Independent `acpx` client | No | Real client compatibility |
| E2E | Spawned ACP process + named dependencies | No | Golden workflow |
| Release | Full process/credential/egress evidence | No | Phase 1 sign-off |

There is no hosted staging Gateway. Provider fakes remain confined to unit and contract tests and
cannot justify a live claim.

## Verification ownership

Every design claim maps to an executable unit, integration, E2E, eval, or release-gate check.
Coverage remains at least 80% aggregate Python production code, and safety-critical modules do not
regress.
:::

::: {.sheet .tight data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="5" data-total="14"}
# 6. Tool Invocation Tests

- Search is authorized only by existing policy signals and the harness gate.
- The Gateway forwards the effective include/exclude policy and rejects off-policy citation URLs.
- At `max_tokens=16`, the live deterministic plugin returns typed URL annotations or fails.
- URL, title, and non-empty content are required; annotation offsets are ignored.
- Extract requires exact prior Gateway-recorded provenance and passes redirect/SSRF/media/size/time
  bounds.
- Package and OSV routes remain callable without a Tavily/search credential.
- Search, extract, package, and advisory usage envelopes reconcile independently.

# 7. OptimusGatewaySettings Unit Tests

- Default `http://127.0.0.1:8765` passes.
- `localhost` and canonical IPv6 loopback pass.
- Non-loopback DNS names and IP literals fail closed.
- URI userinfo, ambiguous host parsing, and non-HTTP(S) schemes fail closed.
- No field or environment variable authorizes non-loopback.
- `production_mode`, extra origins, hosted origins, and signed tenant profiles are absent.
- `optimus_api_key` is masked in repr, serialization, logs, telemetry, and state.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="6" data-total="14"}
# 7.1 Integration, E2E, and egress gates

- Direct policy-violation tests target the real loopback Gateway.
- Aggregator routing/fallback evidence records the returned provider and model.
- The agent and ACP child may egress only to the loopback Gateway.
- The Gateway may egress only to the configured aggregator, approved package/OSV hosts, approved
  extract targets, Redis, and configured OTLP endpoint.
- Agent and Gateway environments are scanned separately.
- The agent has no upstream key; the Gateway has the approved aggregator key by design.
- After replacement acceptance, the Gateway has no direct-provider, Tavily, or LangSmith key.
- Crafted tool output cannot cause direct agent egress.
- WSL2 evidence proves both processes share one network namespace.

## Failure behavior

Malformed or missing provider usage/cost fails closed. Permanent authentication, policy, schema,
and validation failures do not retry. Transient faults have a bounded retry budget and record every
attempt.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="8" data-total="14"}
# 8A. Observability Test Strategy

| Tool | Category | Purpose | Counts toward coverage |
|---|---|---|---:|
| `coverage.py` / `pytest-cov` | Code coverage | Production-code execution | Yes |
| DeepEval / Ragas | LLM quality | Correctness and groundedness | No |
| PyRIT | Adversarial | Injection and tool-control safety | No |
| OpenTelemetry / OTLP | Trace observability | Vendor-neutral span contract and export | No |

Run a real Phoenix evidence tier and assert:

- required span attributes and request correlation;
- parent/child relationships;
- secret redaction;
- batching and retry outcome;
- validation and policy disposition;
- final failure/success disposition.

Phoenix is the documented default, not an API dependency. No LangSmith dependency, endpoint,
credential, or amortized per-request charge exists.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="9" data-total="14"}
# 7A. Deterministic Search Compatibility Gate

The gate uses one cheap Flash/Haiku-class model and the default engine request shape.

<div class="metric-grid">
<div class="metric"><b>16</b>maximum output tokens</div>
<div class="metric"><b>3</b>minimal-call annotations</div>
<div class="metric"><b>9/9</b>complete citations</div>
</div>

<div class="metric-grid">
<div class="metric"><b>0</b>include-domain violations</div>
<div class="metric"><b>0</b>exclude-domain violations</div>
<div class="metric"><b>7,068.7 ms</b>mean latency</div>
</div>

Provider-reported mean cost was `$0.0051584/search`. Direct extract measured 270,008 bytes to
60,077 text characters in 589.5 ms.

These values are evidence, not permanent performance thresholds. Every run reports fresh values
and fails on absent search execution, annotations, domain enforcement, or usage/cost.

A server-tool successor requires a separate live test proving `max_uses: 1`, exactly one search,
search-use accounting, valid annotations, domain enforcement, and fail-closed behavior when
execution evidence is absent.
:::

::: {.sheet .tight data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="10" data-total="14"}
# 11. Security and Trust Boundary Tests

- Secret scans include the aggregator key and every retired direct-provider, Tavily, and LangSmith
  key name.
- Strict-loopback validation replaces production-mode permutations.
- URL parsing rejects userinfo, non-HTTP(S), non-loopback hosts, ambiguous IP forms, and DNS
  rebinding seams.
- Extract revalidates every redirect and final address and blocks private/link-local/loopback
  resolution.
- Tool output is untrusted and cannot become policy or executable content.
- Provider-reported cost must be Decimal-parseable, non-negative, and attributable.
- Logs and traces preserve field names while redacting secrets.

## Golden task evidence

Golden tasks run against the real local Gateway. Named live claims use real dependencies. ACP
protocol evidence uses `acpx`, not a project-authored client.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="11" data-total="14"}
# 12. Golden Task Regression Suite

Every golden task records:

- expected mode and final state;
- expected tool class and authorization outcome;
- cost band and provider-reported usage;
- mutation behavior;
- Gateway and provider request identity;
- trace identity and final disposition.

The suite covers Plan-only refusal, approved Agent mutation, deterministic search, bounded extract,
free package/advisory routes, retry exhaustion, malformed usage/cost, and credential leakage
attempts.

OTel/OTLP-to-Phoenix evidence replaces LangSmith assertions. A trace failure cannot silently count
as success; delivery state and final disposition must be explicit.

## Process-scope assertion

The agent has no upstream credential. The Gateway has exactly the approved aggregator credential
and never exposes it through logs, telemetry, state, responses, child environments, or error text.
:::

::: {.sheet .compact data-doc="Optimus-Cost-Agent - Test Strategy v1.5" data-page="12" data-total="14"}
# 13. Phase 1 Release Gates

## Transport and protocol

- Shadow workspace, mutation guard, and independent ACP-client evidence pass.
- Strict-loopback topology and WSL2 namespace evidence pass.
- Both agent-facing completion shapes validate; mixed shapes fail.

## Runtime and credentials

- Full Plan and Agent runs use only the two agent-facing variables.
- Agent and child processes have no direct external egress.
- Gateway has one approved aggregator credential and no retired keys after acceptance.

## Evidence and cost

- Search plugin compatibility/deprecation gate passes.
- Package and OSV routes work without search configuration.
- Extract provenance and SSRF gates pass.
- Provider-reported usage/cost reconciles across response, ledger, and TimeSeries.

## Observability

- Real OTLP spans reach Phoenix with required fields and redaction.
- No LangSmith dependency or amortized charge exists.

Release sign-off remains governed by the authoritative Plan 9.6 live-verification gate.
:::
