# P11-FEAT-GATEWAY Deep Requirement Inventory

**Status:** Read-only extraction report; not a Gateway specification and not implementation authority.

**Extraction basis:** The four repaired publication PDFs were re-hashed and re-extracted on this branch. Changed-page statements were checked against the v3 redline, the approved aggregator design note, and the measured OpenRouter spike. A carried-page statement is retained only where the repaired PDF contains the body text.

**Baseline reviewed:** `origin/main` at `4590dbf9e77a2bea11a9c28356fd59116568e50d`.

**Working branch:** `agent/codex/local-gateway-architecture-v3` at `85852b3d4640fec5b79647685f0c35c52dbbff15` (working tree contains the repaired publication and traceability artifacts).

## Source pin verification

| Source | SHA-256 | Pages | Result |
|---|---|---:|---|
| `docs/Optimus-Cost-Agent-Architecture-v2.16.pdf` | `6C2C98FE2327A6C466CAD3EB1800335EB59F0E1F65B2CB8E1E3401D7CFA05801` | 13 | Match |
| `docs/Optimus-Cost-Agent-LLD-v2.39.pdf` | `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE` | 40 | Match |
| `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | `27EF0657CCEC5568D3E3769C7320223D1BFE3CF6F4702564CBD0A8A391F11029` | 16 | Match |
| `docs/Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | `F3D744EC175B1E18E8B1E4E271997A0BB12666CC33CA7154A40BF5298588DA8D` | 14 | Match |

The hashes were checked with the bundled Python `pypdf` path and the text was independently spot-checked with WSL2 Poppler `pdftotext`. The repaired LLD §0.B route flow is extractable; it is not carried forward as the prior clipped-source exception.

The approved OpenRouter spike is the measured acceptance baseline for the search rows: one
`google/gemini-2.5-flash-lite` model, default engine, `max_tokens=16`, and a deterministic web
plugin. It measured 3 annotations on the minimal call, 3/3 allowed and 0/3 violating include-domain
results, 0/3 excluded-domain violations, 9/9 structurally complete citations, 7,068.7 ms mean
latency, `$0.0051584` mean provider-reported cost per search, and a 270,008-byte HTML fetch parsed to
60,077 characters in 589.5 ms. These are evidence values, not permanent performance thresholds.

## Disposition and evidence conventions

Every row has a disposition, owner, and named evidence target. `In scope` means the requirement is a current contract to be implemented or tested in its owning lane. `Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled)` records the settled cross-run budget-policy custody; it does not reopen the architecture question. `P11-FU-2` remains the package/advisory backlog. `P11-FU-3` remains open for the MCP source/transport gap; the inventory never infers an MCP Gateway route.

Evidence aliases:

- **E1 one-key release:** real Plan/Agent release evidence with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent process.
- **E2 route/schema:** unit, contract, and live-route evidence for both completion shapes and validated `GatewayUsage`.
- **E3 evidence wrappers:** harness-gated search, extract, package, and advisory evidence with provenance.
- **E4 ledger:** provider-reported usage/cost, USD reconciliation, and append-only ledger evidence.
- **E5 telemetry:** OTel/OTLP span and trace-ingress evidence, with Phoenix as the documented local default.
- **E6 retry:** bounded transient retry, permanent-failure, and retry-telemetry evidence.
- **E7 origin/secrets:** strict-loopback, secret-redaction, and agent/Gateway egress-scan evidence.
- **E8 policy revalidation:** real-Gateway policy, domain, provenance, call-cap, and usage fail-closed evidence.
- **E9 coverage/release:** `coverage.py`/`pytest-cov`, quality, and release-gate evidence.
- **E10 source repair:** repaired publication source plus fresh extraction/digest review.
- **E11 golden tasks:** real local Gateway golden-task and independent `acpx` protocol evidence.
- **E12 budget custody:** reviewed custody record for `P9.85-FU-3`; no implementation is authorized by this inventory.

## Requirement counts

| Tier | Section | Rows | Exhaustion result |
|---|---|---:|---|
| 1 | HLD §5A | 8 | Extracted from repaired page 3 |
| 1 | HLD §11 | 10 | Extracted from repaired page 10 |
| 1 | HLD §11A | 5 | Extracted from repaired page 12 |
| 1 | LLD §0 | 3 | Extracted from repaired page 2 |
| 1 | LLD §0.A | 3 | Extracted from repaired page 3 |
| 1 | LLD §0A | 8 | Extracted from repaired page 4 |
| 1 | LLD §0A named endpoint block | 5 | Extracted from repaired page 5 |
| 1 | LLD §6 | 11 | Extracted from repaired pages 20-21 |
| 1 | LLD §9C settings and origin trust | 5 | Extracted from repaired page 26 |
| 1 | LLD §9D | 7 | Extracted from repaired page 30 |
| 1 | Guardrails §9 | 9 | Extracted from repaired page 12 |
| 1 | Test Strategy §7 | 9 | Extracted from repaired pages 5-6 |
|  | **Tier 1 subtotal** | **83** | All Tier 1 sections exhausted |
| 2 | LLD §0.B | 2 | Repaired component flow extracted; no MCP endpoint inferred |
| 2 | LLD §0.C | 10 | Responsibilities extracted; MCP remains a source/transport gap |
| 2 | LLD §0.D | 7 | Documented routes extracted; package/advisory retained as independent backlog |
|  | **Tier 2 subtotal** | **19** | All Tier 2 sections exhausted |
| 3 | HLD §6 | 3 | Gateway intersection extracted from restored step 6 and co-located flow |
| 3 | HLD §10 | 8 | Restored system, phase, cost, and hallucination controls extracted |
| 3 | HLD §12 | 2 | OTel/OTLP and quality-gate intersection extracted |
| 3 | LLD §9 | 2 | Harness-first tool contract extracted |
| 3 | LLD §9E | 6 | Evidence and usage reconciliation extracted |
| 3 | LLD §10A | 7 | USD ledger and trace intersection extracted |
| 3 | LLD §11A | 5 | Coverage and live-dependency intersection extracted |
| 3 | LLD §12 | 2 | Model-touching guardrail boundary extracted |
| 3 | Guardrails §7 | 1 | USD evaluator budget boundary extracted |
| 3 | Guardrails §7.2 | 5 | Bounded-loop controls extracted |
| 3 | Test Strategy §8 | 6 | Usage and retention intersection extracted |
| 3 | Test Strategy §8A | 5 | OTel/OTLP and coverage intersection extracted |
| 3 | Test Strategy §9 | 5 | Retry and budget-failure intersection extracted |
| 3 | Test Strategy §10 | 3 | Schema-boundary intersection extracted |
| 3 | Test Strategy §13 | 8 | Release intersection extracted |
|  | **Tier 3 subtotal** | **68** | All requested intersections traced |
| 4 | HLD §5 | 2 | Provider-reported accounting constraints preserved |
| 4 | HLD §8 | 3 | Harness-first evidence constraints preserved |
| 4 | LLD §0.E | 1 | Strict one-key/loopback boundary preserved |
| 4 | LLD §9A | 2 | Package/advisory class constraints preserved |
| 4 | LLD §9B | 3 | Package/advisory routing and reason constraints preserved |
| 4 | LLD §9C | 4 | Typed wrapper/provenance constraints preserved |
| 4 | LLD §10 | 3 | Retention and run-metadata constraints preserved |
| 4 | LLD §12C | 3 | Bounded-loop state/evaluator constraints preserved |
|  | **Tier 4 subtotal** | **21** | All preserve-only constraints traced |
|  | **Total inventory rows** | **191** | No blank dispositions |

## Tier 1 - owned by P11-FEAT-GATEWAY-CORE, with partitioned Gateway requirements

### HLD v2.16 §5A - 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §5A, p.3 | `OPTIMUS_API_KEY` is the only agent-facing credential; it authenticates the agent to the loopback Gateway and is not an upstream key or tenant wallet. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §5A, p.3 | The Gateway process holds one developer-owned aggregator credential in local configuration or OS credential storage. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §5A, p.3 | OpenRouter is the default aggregator; Vercel AI Gateway is an allowed second OpenAI-compatible endpoint only when its Python integration is modest. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| HLD v2.16 §5A, p.3 | The developer funds the aggregator account directly; it supplies many models, routing, normalized usage/USD cost, and one developer-owned balance. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| HLD v2.16 §5A, p.3 | The local Gateway preserves the one-key, one-budget, one-ledger thesis by isolating the credential, enforcing policy/budget controls, and recording provider-reported usage. | In scope | P11-FEAT-GATEWAY-CORE | E1, E4 |
| HLD v2.16 §5A, p.3 | No Optimus-hosted account, prepaid balance, subscription, tenant, org, project wallet, OAuth/device flow, or public Optimus Gateway is part of Phase 1. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §5A, p.3 | Search shares the OpenRouter credential through a dedicated deterministic plugin request; package/OSV are free public APIs, and OTel export has no invented per-request charge. | In scope | P11-FEAT-GATEWAY-TOOLS / P11-FEAT-GATEWAY-COST-OBS | E3, E4, E5 |
| HLD v2.16 §5A, p.3 | One-key-for-search is conditional because the deterministic plugin is deprecated; withdrawal requires a verified-or-fail successor or a standalone backend with a second key/balance. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |

### HLD v2.16 §11 - 10 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §11, p.10 | The Gateway is a deterministic loopback process run alongside the local agent, not a hosted service, tenant control plane, subscription product, or central wallet. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §11, p.10 | It binds to strict loopback and authenticates the agent with a local shared secret. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §11, p.10 | The Gateway isolates the developer's aggregator credential in Gateway-owned local configuration or OS credential storage. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §11, p.10 | Approved model aliases route through the surviving OpenAI-compatible transport. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| HLD v2.16 §11, p.10 | Model/tool policy, domain rules, call caps, provenance, and the current run's USD budget are enforced at the Gateway. | In scope | P11-FEAT-GATEWAY-CORE / P11-FEAT-GATEWAY-TOOLS | E8 |
| HLD v2.16 §11, p.10 | Provider-reported usage and cost return in a validated `GatewayUsage` envelope. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |
| HLD v2.16 §11, p.10 | Deterministic search, bounded extract, package lookup, and OSV advisory are brokered independently. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| HLD v2.16 §11, p.10 | Structured trace ingress is accepted, mapped to OpenTelemetry, and exported through OTLP. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| HLD v2.16 §11, p.10 | Usage attribution persists run, session, request, Gateway-request, and provider-request identities. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| HLD v2.16 §11, p.10 | The agent has only the loopback URL and local shared secret; the Gateway has the aggregator key, shared secret, allowed domains, Redis URL, and optional OTLP endpoint, with no non-loopback override. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |

### HLD v2.16 §11A - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §11A, p.12 | Phase 1 uses OpenTelemetry spans and OTLP as the vendor-neutral trace contract across planning, Gateway calls, tools, validation, retries, and final response generation. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| HLD v2.16 §11A, p.12 | Authenticated structured trace ingress is validated and redacted by the Gateway, mapped to OTel spans/events, and exported through OTLP. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5, E7 |
| HLD v2.16 §11A, p.12 | Arize Phoenix is the documented local default; any OTLP-compatible backend may replace it without changing Optimus instrumentation. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| HLD v2.16 §11A, p.12 | Trace export is operational telemetry; no allocated or amortized observability `cost_usd` is added to the usage ledger. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| HLD v2.16 §11A, p.12 | Required attributes retain run/session/request and Gateway/provider IDs, execution mode, scope, model/provider, cache, USD cost, billing units, policy/tool, validation, retry, and failure attribution; secrets are redacted. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |

### LLD v2.39 §0 - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0, p.2 | The Gateway is a deterministic local loopback process separating the agent from upstream credentials, policy, budget authority, usage normalization, and controlled egress. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0, p.2 | The agent receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; the Gateway holds one developer-owned aggregator credential, with no hosted service, OAuth/device flow, tenant wallet, Vault, or public origin. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0, p.2 | OpenRouter is the default aggregator; Vercel is optional pending modest Python integration; direct single-provider adapters are removed. | In scope | P11-FEAT-GATEWAY-CORE | E2 |

### LLD v2.39 §0.A - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0.A, p.3 | The control plane is split between the agent's two-variable environment and the Gateway process configuration. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0.A, p.3 | The agent has `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; the Gateway has the OpenRouter provider/key and shared secret, with no upstream or OTel key in the agent. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0.A, p.3 | The boundary is strict loopback with domains, Redis, and optional OTLP configured on the Gateway; there is no hosted-origin, tenant-profile, or non-loopback override. | In scope | P11-FEAT-GATEWAY-CORE | E7 |

### LLD v2.39 §0A - 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0A, p.4 | The agent runtime allows only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0A, p.4 | Local Tavily, OpenAI, OpenRouter, GLM, LangSmith, and other provider keys are rejected; the approved aggregator credential stays in the Gateway process. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0A, p.4 | `OPTIMUS_API_KEY` is a local shared secret, not a wallet key; the developer funds the aggregator account directly. | In scope | P11-FEAT-GATEWAY-COST-OBS | E1, E4 |
| LLD v2.39 §0A, p.4 | Model completion accounting records aggregator/provider/model, tokens/cache, billing units, provider-reported `cost_usd`, and request IDs. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |
| LLD v2.39 §0A, p.4 | Deterministic search uses a separate minimal model call, structured citations, search-use accounting, and provider-reported `cost_usd`. | In scope | P11-FEAT-GATEWAY-TOOLS / P11-FEAT-GATEWAY-COST-OBS | E3, E4 |
| LLD v2.39 §0A, p.4 | Package/advisory requests record operational evidence and do not fabricate provider cost. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E4 |
| LLD v2.39 §0A, p.4 | Trace export records delivery state and trace IDs without an allocated or amortized request charge. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| LLD v2.39 §0A, p.4 | The separate USD rename removes legacy credit-named fields without changing existing USD semantics or adding cross-run policy. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E12 |

### LLD v2.39 §0A named endpoint block - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 named block, p.5 | The agent calls typed loopback Gateway endpoints and never calls OpenRouter, Vercel, registries, OSV, Phoenix, or another OTLP backend directly. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 named block, p.5 | Completion routes are `POST /v1/responses` and `POST /v1/chat/completions`. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 named block, p.5 | Search/extract routes are `POST /v1/tools/web/search` and `POST /v1/tools/web/extract`; search is a separate authorized minimal plugin request. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 named block, p.5 | Package/advisory routes are independent of paid-search configuration, and trace ingress is `POST /v1/observability/traces`. | In scope | P11-FEAT-GATEWAY-TOOLS / P11-FEAT-GATEWAY-COST-OBS | E3, E5 |
| LLD v2.39 named block, p.5 | The observability path is authenticated trace ingress -> Gateway validation/redaction -> OTel/OTLP -> Phoenix by default; the route list has no MCP endpoint. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |

### LLD v2.39 §6 - 11 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §6, p.20 | All model completions route from the agent to the strict-loopback Gateway using the local shared secret. | In scope | P11-FEAT-GATEWAY-CORE | E1, E2 |
| LLD v2.39 §6, p.20 | The Gateway resolves an Optimus model alias to an aggregator model identifier and calls OpenRouter by default or Vercel if retained. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §6, p.20 | The aggregator credential exists only in Gateway-owned local configuration or OS credential storage; there is no Vault, hosted account, or direct-provider adapter. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §6, p.20 | `/v1/responses` accepts the Responses `input` field and `/v1/chat/completions` accepts a `messages` array. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §6, p.20 | The validator rejects `messages` at `/v1/responses` and `input` at `/v1/chat/completions`; both converge on one authenticated completion service. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §6, p.20 | Both agent-facing shapes use the surviving `UrllibOpenAICompatibleClient` transport. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §6, p.20 | Transient network, timeout, rate-limit, and provider-availability failures may retry; permanent authentication, schema, policy, and malformed-usage failures do not. | In scope | P11-FEAT-GATEWAY-CORE | E6 |
| LLD v2.39 §6, p.20 | A transient call has at most three attempts, with attempt number, classification, latency, and disposition recorded for every retry. | In scope | P11-FEAT-GATEWAY-CORE | E5, E6 |
| LLD v2.39 §6, p.20 | Provider-reported `usage.cost` is authoritative; missing, null, negative, or malformed usage/cost fails closed before output is accepted. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |
| LLD v2.39 §6.1, p.21 | `UrllibOpenAICompatibleClient` stores the Gateway-owned key/base URL, posts the OpenAI-compatible payload, and parses message plus usage. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §6.1, p.21 | The parser validates output, provider request identity, billing units, token/cache detail, resolved model/version when present, USD cost, and returns the validated `GatewayUsage` contract. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |

### LLD v2.39 §9C settings and origin trust - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9C, p.26 | `OptimusGatewaySettings` defaults to `http://127.0.0.1:8765` and carries a secret `optimus_api_key`. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §9C, p.26 | Gateway URLs must use HTTP(S), contain no userinfo, and resolve to `127.0.0.1`, `localhost`, or `::1`. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| LLD v2.39 §9C, p.26 | The validator fails closed for non-HTTP(S), userinfo, and non-loopback hosts. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| LLD v2.39 §9C, p.26 | There is no production-mode flag, built-in hosted origin, extra-origin override, signed tenant profile, or non-loopback trust seam. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| LLD v2.39 §9C, p.26 | The final source must remain aligned with the separately reviewed strict-loopback implementation. | In scope | P11-FEAT-GATEWAY-CORE | E7 |

### LLD v2.39 §9D - 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9D, p.30 | The Gateway independently revalidates every privileged input; agent-side checks are defense in depth and never authoritative. | In scope | P11-FEAT-GATEWAY-CORE | E8 |
| LLD v2.39 §9D, p.30 | Effective domains intersect the caller request with the local allowlist, and returned URLs outside it are rejected. | In scope | P11-FEAT-GATEWAY-TOOLS | E8 |
| LLD v2.39 §9D, p.30 | Extract requires an exact prior search result for the same `run_id`, with redirect and final-URL revalidation. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §9D, p.30 | The current-run USD cap is enforced against the Gateway ledger before billable dispatch. | In scope | P11-FEAT-GATEWAY-CORE | E4, E8 |
| LLD v2.39 §9D, p.30 | Call capacity is keyed by run and tool and does not share a paid-search configuration gate. | In scope | P11-FEAT-GATEWAY-TOOLS | E8 |
| LLD v2.39 §9D, p.30 | Tool class, policy signal, execution mode, and authenticated local subject are rechecked. | In scope | P11-FEAT-GATEWAY-TOOLS | E8 |
| LLD v2.39 §9D, p.30 | Missing, malformed, negative, or unparseable provider-reported cost is rejected before dispatch or ledger acceptance. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E8 |

### Guardrails v1.1 §9 - 9 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Guardrails v1.1 §9, p.12 | The governing rule is rules first, a small-model classifier only when needed, and human approval for high-risk uncertainty. | In scope | P11-FEAT-GATEWAY-CORE | E8, E11 |
| Guardrails v1.1 §9, p.12 | Permission rules, pre-tool guard, shell validation, and injection/MCP defense are deterministic and zero-LLM-cost controls. | In scope | P11-FEAT-GATEWAY-CORE | E8 |
| Guardrails v1.1 §9, p.12 | Pre-commit/CI uses Ruff, Bandit, AST-grep, and tests; its cost profile is compute, not tokens. | In scope | P11-FEAT-GATEWAY-CORE | E9 |
| Guardrails v1.1 §9, p.12 | Bounded loops use a cheap evaluator plus hard USD budgets for net cost reduction under caps. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E6, E11 |
| Guardrails v1.1 §9, p.12 | Workflow skills load on demand to save tokens and permit a smaller model. | In scope | P11-FEAT-GATEWAY-CORE | E11 |
| Guardrails v1.1 §9, p.12 | The borderline classifier is a cheap model via the Optimus Gateway with a strict budget, rare and off the hot path. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| Guardrails v1.1 §9, p.12 | The evaluator is routed through the same loopback Gateway, developer-owned aggregator account, USD ledger, and OTel/OTLP trace path as other calls. | In scope | P11-FEAT-GATEWAY-CORE / P11-FEAT-GATEWAY-COST-OBS | E2, E4, E5 |
| Guardrails v1.1 §9, p.12 | There is no second, ungoverned cost path introduced by guardrails. | In scope | P11-FEAT-GATEWAY-CORE / P11-FEAT-GATEWAY-COST-OBS | E2, E4, E5 |
| Guardrails v1.1 §9, p.12 | The evaluator fails closed when provider-reported usage/cost is missing or malformed. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |

### Test Strategy v1.5 §7 - 9 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §7, p.5 | Default `http://127.0.0.1:8765` passes; localhost and canonical IPv6 loopback pass; non-loopback DNS names and IP literals fail closed. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| Test Strategy v1.5 §7, p.5 | URI userinfo, ambiguous host parsing, and non-HTTP(S) schemes fail closed. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| Test Strategy v1.5 §7, p.5 | No field or environment variable authorizes non-loopback; hosted origins and signed tenant profiles are absent. | In scope | P11-FEAT-GATEWAY-CORE | E7 |
| Test Strategy v1.5 §7, p.5 | `optimus_api_key` is masked in repr, serialization, logs, telemetry, and state. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| Test Strategy v1.5 §7, p.5 | `/v1/responses` uses `input`; `/v1/chat/completions` uses `messages`; mixed shapes are rejected. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| Test Strategy v1.5 §7, p.6 | Direct policy-violation requests to the real loopback Gateway receive independent rejection. | In scope | P11-FEAT-GATEWAY-TOOLS | E8 |
| Test Strategy v1.5 §7, p.6 | Aggregator routing/fallback evidence records returned provider and model. | In scope | P11-FEAT-GATEWAY-CORE | E2, E6 |
| Test Strategy v1.5 §7, p.6 | Agent/ACP child egress is limited to loopback; Gateway egress is limited to configured aggregator, package/OSV, extract targets, Redis, and OTLP. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7, E11 |
| Test Strategy v1.5 §7, p.6 | Missing or malformed provider usage/cost fails closed; permanent failures do not retry and transient faults have a bounded retry budget. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E6 |

## Tier 2 - unowned rows resolved by this extraction

### LLD v2.39 §0.B - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0.B, rendered p.2 | The repaired component flow documents local agent ingress, loopback Gateway authentication, seven documented routes, policy/domain/call-cap controls, model/search/extract/package/advisory adapters, OTel/OTLP trace ingress, OpenRouter default, and Phoenix default. | In scope | P11-FEAT-GATEWAY-CORE / P11-FEAT-GATEWAY-TOOLS | E2, E3, E5, E10 |
| LLD v2.39 §0.B, rendered p.2 | The flow includes a budget/usage ledger with provider-reported USD cost; budget implementation remains architecture-unblocked but unscheduled under P9.85-FU-3. No MCP endpoint is shown or implied. | Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled) | P9.85-FU-3 | E10, E12 |

### LLD v2.39 §0.C - 10 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0.C, p.3 | Authenticate the local agent with a shared secret on strict loopback. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0.C, p.3 | Resolve model aliases through an approved OpenAI-compatible aggregator. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §0.C, p.3 | Broker deterministic search, bounded extract, package lookup, and OSV advisory independently. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §0.C, p.3 | Enforce execution mode, tool policy, domain rules, call caps, provenance, and run budget. | In scope | P11-FEAT-GATEWAY-CORE / P11-FEAT-GATEWAY-TOOLS | E8 |
| LLD v2.39 §0.C, p.3 | Persist run/session/request/Gateway/provider request attribution. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| LLD v2.39 §0.C, p.3 | Isolate upstream credentials from the agent process. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| LLD v2.39 §0.C, p.3 | Accept structured trace ingress, map it to OTel, and export OTLP. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| LLD v2.39 §0.C, p.3 | Package and advisory capabilities remain independently dispatchable and do not depend on paid-search configuration. | In scope | P11-FEAT-GATEWAY-TOOLS | E3 |
| LLD v2.39 §0.C, p.3 | MCP remains a local trust-contract concern; no Gateway MCP endpoint is added or inferred, and P11-FU-3 remains open. | Excluded -> P11-FU-3 (MCP source/transport gap) | P11-FU-3 | E10 |
| LLD v2.39 §0.C, p.3 | OpenRouter is the default model/search route; Vercel remains an optional model route pending modest Python transport validation. | In scope | P11-FEAT-GATEWAY-CORE | E2 |

### LLD v2.39 §0.D - 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0.D, p.3 | The Gateway exposes OpenAI-compatible model endpoints and typed tool endpoints. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §0.D, p.3 | `POST /v1/responses` uses the top-level `input` field. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §0.D, p.3 | `POST /v1/chat/completions` uses the `messages` array. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §0.D, p.3 | Mixed `messages`/`input` shapes are rejected by the Gateway schema validator. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| LLD v2.39 §0.D, p.3 | `POST /v1/tools/web/search` and `POST /v1/tools/web/extract` are documented typed routes. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §0.D, p.3 | `POST /v1/tools/package/lookup` remains a separate public-registry capability owned by P11-FU-2. | Deferred -> P11-FU-2 | P11-FU-2 | E3, E10 |
| LLD v2.39 §0.D, p.3 | `POST /v1/tools/security/advisory` remains a separate public-OSV capability owned by P11-FU-2; the trace route is operational and no MCP route is added. | Deferred -> P11-FU-2 | P11-FU-2 | E3, E5, E10 |

## Tier 3 - cross-cutting intersections

These rows trace Gateway intersections without redefining ownership of Plans 4, 7, 8, or 9.

### HLD v2.16 §6 - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §6, p.4 | Restored step 6 delivers to the loopback Gateway and approved upstream aggregator, returning model output plus provider-reported usage and USD cost; aliases are policy inputs and no direct adapter is selected. | In scope | P11-FEAT-GATEWAY-CORE | E2, E4 |
| HLD v2.16 §6, p.4 | The orchestration loop returns to step 6 after a fitness failure and proceeds to patch execution only after the feedback gate passes. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E2, E11 |
| HLD v2.16 §6, p.4 | RedisTimeSeries/Redis HASH persistence and the FinOps display consume the resulting run/request usage attribution. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |

### HLD v2.16 §10 - 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §10.A, p.7 | The IDE, local agent, loopback Gateway, Redis, repository, and optional Phoenix collector share one developer environment while agent/Gateway credentials remain separate. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| HLD v2.16 §10.B, p.8 | Every request traverses feedforward constraints and feedback fitness gates before output reaches the working tree. | In scope | P11-FEAT-GATEWAY-TOOLS | E11 |
| HLD v2.16 §10.C, p.9 | Phase 1 Python local agent plus loopback Gateway is mandatory before later phases; the release gate requires only the two agent-facing variables in the agent process. | In scope | P11-FEAT-GATEWAY-CORE | E1 |
| HLD v2.16 §10.D, p.9 | Pre-prompt AST slicing, cache anchoring, and ADL constraints prevent unnecessary tokens. | In scope | P11-FEAT-GATEWAY-CORE / Plan 12 | E11 |
| HLD v2.16 §10.D, p.9 | The triage router sends a task to the cheapest sufficient model. | In scope | P11-FEAT-GATEWAY-CORE | E2, E11 |
| HLD v2.16 §10.D, p.9 | LOW/MEDIUM/HIGH rigor budgets cap tool calls and reflection passes. | In scope | Plan 9 / P11-FEAT-GATEWAY-CORE preserve-only | E11 |
| HLD v2.16 §10.D, p.9 | Gateway usage -> EvidenceLedger -> RedisTimeSeries prevents silent accumulation and enables per-run audit. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| HLD v2.16 §10.E, p.9 | ToolInvocationPolicy blocks casual web calls and requires reason codes as one layer of hallucination control. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |

### HLD v2.16 §12 - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §12, p.12 | Phase 1 requires at least 80% Python production-code coverage, with higher expectations for safety-critical modules; coverage is a release gate. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| HLD v2.16 §12, p.12 | DeepEval/Ragas/PyRIT and OTel/OTLP trace validation are separate quality, safety, and observability gates and do not count as coverage. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5, E9 |

### LLD v2.39 §9 - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9, carried body | Tool use is policy-driven first and model-requested second; the harness decides whether evidence is permitted, necessary, and cost-justified. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §9, carried body | The typed tool registry, deterministic invocation matrix, and Evidence Ledger record every external lookup alongside the Assumption Ledger. | In scope | P11-FEAT-GATEWAY-TOOLS / P11-FEAT-GATEWAY-COST-OBS | E3, E4 |

### LLD v2.39 §9E - 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9E, carried body | Every external lookup is recorded with source, policy signal, and reason code so architectural claims can be traced to evidence. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E4 |
| LLD v2.39 §9E, carried body | Gateway request ID, provider, cache, billing units, and `cost_usd` come directly from the validated Gateway response. | In scope | P11-FEAT-GATEWAY-COST-OBS | E3, E4 |
| LLD v2.39 §9E, carried body | The ledger exposes backward-compatible credits, provider-native billing units, and primary `total_cost_usd()` reconciliation. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| LLD v2.39 §9E, carried body | Local evidence is first; external evidence is policy-triggered; mutation follows mode and fitness gates. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8, E11 |
| LLD v2.39 §9E, carried body | `ToolRegistry.authorize_and_record_call` atomically enforces mode, policy signal, and per-run call ceiling. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §9E, carried body | Evidence and cost ledgers remain separate and join on `gateway_request_id`; their totals reconcile. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |

### LLD v2.39 §10A - 7 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §10A, carried body | `GatewayUsage` remains the wire-level envelope returned on every billable call. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |
| LLD v2.39 §10A, carried body | `ProviderUsage` is the canonical persisted superset carrying GatewayUsage fields plus normalization fields. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| LLD v2.39 §10A, carried body | Usage accounting stores provider-native units and normalized USD semantics for every request. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| LLD v2.39 §10A, carried body | Evidence audit joins the cost ledger on `gateway_request_id` without duplicating normalized cost fields. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| LLD v2.39 §10A, carried body | Cross-run budget authority remains P9.85-FU-3; local current-run budget evidence is retained without inventing a second policy. | Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled) | P9.85-FU-3 | E12 |
| LLD v2.39 §10A, carried body | The USD rename carries the normalized USD figure into run telemetry and RedisTimeSeries without legacy credit-named fields. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| LLD v2.39 §10A, carried body | Trace records retain run/request/mode/scope/model/provider/cache/USD/billing/policy/tool/validation/failure fields through authenticated OTel/OTLP ingress. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |

### LLD v2.39 §11A - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §11A, carried body | Test Strategy §8A is authoritative for coverage, measurement taxonomy, and trace observability. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| LLD v2.39 §11A, carried body | Coverage uses `coverage.py` and `pytest-cov`; the Phase 1 gate is at least 80% aggregate with no safety-critical regression. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| LLD v2.39 §11A, carried body | DeepEval/Ragas and PyRIT remain separate quality/security suites, not coverage metrics. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| LLD v2.39 §11A, carried body | Critical quality/security failures can block release through separate gates. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| LLD v2.39 §11A, carried body | Authoritative thresholds, CI commands, evals, red-team tests, OTel assertions, and release gates live in Test Strategy. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5, E9 |

### LLD v2.39 §12 - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §12, p.39 | Borderline classifiers and loop completion evaluators route through the loopback Gateway and normalized USD ledger. | In scope | P11-FEAT-GATEWAY-CORE | E2, E4 |
| LLD v2.39 §12, p.39 | Guardrails add no second cost path; cross-run budget authority remains P9.85-FU-3. | Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled) | P9.85-FU-3 | E12 |

### Guardrails v1.1 §7 - 1 row

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Guardrails v1.1 §7, p.11 | `max_budget_usd` is enforced by the same local Gateway USD budget policy as every other call and reconciled from provider-reported cost. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E4, E6 |

### Guardrails v1.1 §7.2 - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Guardrails v1.1 §7.2, p.10 | Persistent state lives in files, git history, task manifests, traces, and the evidence ledger, not an ever-growing chat context. | In scope | P11-FEAT-GATEWAY-COST-OBS / Plan 9 | E4, E5 |
| Guardrails v1.1 §7.2, p.10 | Every loop has hard `max_iterations`, USD-budget, wall-clock, and explicit-completion bounds. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E11 |
| Guardrails v1.1 §7.2, p.10 | Each iteration writes evidence, verifies a clean git diff, and leaves the pre-tool guard active. | In scope | P11-FEAT-GATEWAY-TOOLS / Plan 9 | E3, E11 |
| Guardrails v1.1 §7.2, p.10 | Human approval is required for escalation and repeated identical failures stop the loop. | In scope | P11-FEAT-GATEWAY-TOOLS / Plan 9 | E8, E11 |
| Guardrails v1.1 §7.2, p.10 | The completion evaluator is a cheap model through the strict-loopback Gateway and fails closed on missing/malformed usage or cost. | In scope | P11-FEAT-GATEWAY-COST-OBS | E2, E4 |

### Test Strategy v1.5 §8 - 6 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §8, carried body | `total_cost_usd()` sums ledger cost and returns zero on an empty ledger; billing-unit totals reconcile provider-native units. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| Test Strategy v1.5 §8, carried body | GatewayUsage identity, cache, billing, and USD fields propagate to append-only ledger entries. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |
| Test Strategy v1.5 §8, carried body | Pricing fallback/staleness emits an audit signal and does not replace provider-reported usage authority. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4, E5 |
| Test Strategy v1.5 §8, carried body | RedisTimeSeries creation, retention, idempotent alteration, and tagged TS.ADD are verified. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| Test Strategy v1.5 §8, carried body | Run metadata hash records execution mode, generation scope, rigor level, assumption count, and a 30-day TTL. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| Test Strategy v1.5 §8, carried body | EvidenceLedger USD and billing-unit totals reconcile to GatewayUsage values within the stated delta. | In scope | P11-FEAT-GATEWAY-COST-OBS | E4 |

### Test Strategy v1.5 §8A - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §8A, p.8 | Test Strategy is authoritative for the Phase 1 coverage target, measurement taxonomy, and trace observability. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| Test Strategy v1.5 §8A, p.8 | Production Python coverage is at least 80% in CI via `coverage.py` and `pytest-cov`; safety-critical modules must not regress. | In scope | P11-FEAT-GATEWAY-COST-OBS | E9 |
| Test Strategy v1.5 §8A, p.8 | Required trace fields include run/request/mode/scope/model/provider/cache/USD/billing/policy/tool/validation/failure attribution. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| Test Strategy v1.5 §8A, p.8 | Phoenix is the documented default for a real OTel/OTLP evidence tier; backend APIs are not the instrumentation contract. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| Test Strategy v1.5 §8A, p.8 | Coverage, quality, adversarial, and trace suites are tracked separately; no LangSmith dependency or amortized per-request charge exists. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5, E9 |

### Test Strategy v1.5 §9 - 5 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §9, p.9 | Transient Gateway errors retry up to three attempts; rate limits use exponential backoff with jitter. | In scope | P11-FEAT-GATEWAY-CORE | E6 |
| Test Strategy v1.5 §9, p.9 | Permanent Gateway and policy errors abort immediately with a failure report/escalation signal. | In scope | P11-FEAT-GATEWAY-CORE | E6, E8 |
| Test Strategy v1.5 §9, p.9 | Budget exhaustion aborts the run, records USD at abort, flushes partial telemetry, and produces no partial file writes. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E4, E11 |
| Test Strategy v1.5 §9, p.9 | Exceeded retry budget returns `ESCALATE_TO_USER` with prior failures. | In scope | P11-FEAT-GATEWAY-CORE | E6 |
| Test Strategy v1.5 §9, p.9 | 503 retry and fitness-failure scenarios prove no mutation before success and targeted replanning on later attempts. | In scope | P11-FEAT-GATEWAY-CORE / Plan 9 | E6, E11 |

### Test Strategy v1.5 §10 - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §10, p.9 | Empty evidence query and zero extract limit fail validation before any Gateway call. | In scope | P11-FEAT-GATEWAY-TOOLS | E3 |
| Test Strategy v1.5 §10, p.9 | Empty API key, negative billing units, and negative USD cost fail validation. | In scope | P11-FEAT-GATEWAY-CORE | E2, E7 |
| Test Strategy v1.5 §10, p.9 | ACP framing and Pydantic v2 validators reject malformed boundary inputs before processing. | In scope | P11-FEAT-GATEWAY-CORE | E2, E3 |

### Test Strategy v1.5 §13 - 8 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| Test Strategy v1.5 §13, p.12 | Strict-loopback topology and WSL2 same-namespace evidence pass the transport release gate. | In scope | P11-FEAT-GATEWAY-CORE | E1, E7 |
| Test Strategy v1.5 §13, p.12 | Both completion shapes validate and mixed shapes fail. | In scope | P11-FEAT-GATEWAY-CORE | E2 |
| Test Strategy v1.5 §13, p.12 | Direct server-side policy revalidation is exercised against the real loopback Gateway. | In scope | P11-FEAT-GATEWAY-TOOLS | E8 |
| Test Strategy v1.5 §13, p.12 | Secrets never appear in plaintext in logs, telemetry, repr, serialization, state, responses, child environments, or errors. | In scope | P11-FEAT-GATEWAY-CORE | E1, E5, E7 |
| Test Strategy v1.5 §13, p.12 | Search input is captured verbatim and ledger USD/billing totals reconcile to GatewayUsage. | In scope | P11-FEAT-GATEWAY-COST-OBS | E3, E4 |
| Test Strategy v1.5 §13, p.12 | Coverage is at least 80% and safety-critical modules do not regress; OTel/OTLP trace fields and redaction are asserted separately. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5, E9 |
| Test Strategy v1.5 §13, p.12 | RedisTimeSeries schema operations are idempotent and run metadata records execution mode, rigor, and assumption count. | In scope | P11-FEAT-GATEWAY-COST-OBS | E5 |
| Test Strategy v1.5 §13, p.12 | Release runs complete in Plan and Agent modes with only the two agent-facing variables; no upstream key is resolvable in the agent process. | In scope | P11-FEAT-GATEWAY-CORE | E1 |

## Tier 4 - preserve-only constraints

### HLD v2.16 §5 - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §5, carried body | Provider usage response is the primary request-level cost record; attribution does not estimate tokens post hoc. | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY-COST-OBS preserve | E4 |
| HLD v2.16 §5, carried body | Gateway usage fields are parsed directly from the response envelope and retained in the normalized ledger. | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY-COST-OBS preserve | E4 |

### HLD v2.16 §8 - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| HLD v2.16 §8, carried body | Tool use is policy-driven first and model-requested second; the harness alone decides whether a tool is allowed, necessary, and cost-justified. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E8 |
| HLD v2.16 §8, carried body | Web evidence is wrapped behind Optimus-owned typed tools so domains, timeouts, retries, caps, and telemetry are uniform. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E8 |
| HLD v2.16 §8, carried body | Local evidence is first; external evidence is policy-triggered; mutation follows mode and fitness gates. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E8, E11 |

### LLD v2.39 §0.E - 1 row

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §0.E, p.3 | The strict boundary gives the agent only the loopback URL and API secret; Gateway-side configuration holds the aggregator key, domains, Redis, and optional OTLP endpoint, with no hosted origin or non-loopback mode. | In scope | Implemented by Plan 3 / P11-FEAT-GATEWAY-CORE preserve | E1, E7 |

### LLD v2.39 §9A - 2 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9A, carried body | `PACKAGE_AND_ADVISORY_METADATA` remains the shared read-only tool class. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E10 |
| LLD v2.39 §9A, carried body | `PACKAGE_VERSION` and `SECURITY_ADVISORY` remain the package/CVE reason classes. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E10 |

### LLD v2.39 §9B - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9B, carried body | Package and advisory lookup covers public PyPI/npm/Maven registries and OSV advisories; both are read-only and policy-triggered. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3, E10 |
| LLD v2.39 §9B, carried body | Query is a non-empty search string; the reason is metadata and is never sent as the query. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3 |
| LLD v2.39 §9B, carried body | Lookup depth remains capped to bound the operation; package and OSV routes are independent of search configuration. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E3 |

### LLD v2.39 §9C - 4 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §9C, carried body | The local agent authenticates only to the loopback Gateway; provider mechanics remain behind typed Gateway routes. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-TOOLS preserve | E1, E3, E7 |
| LLD v2.39 §9C, carried body | Extract follows a prior approved search result in the same run and never fetches an arbitrary URL. | In scope | P11-FEAT-GATEWAY-TOOLS | E3, E8 |
| LLD v2.39 §9C, carried body | Extract requests have bounded URL count, character count, and duplicate checks. | In scope | P11-FEAT-GATEWAY-TOOLS | E3 |
| LLD v2.39 §9C, carried body | Search/extract responses carry Gateway/provider request identity, cache, billing, and provider-reported USD fields. | In scope | Implemented by Plan 4 / P11-FEAT-GATEWAY-COST-OBS preserve | E3, E4 |

### LLD v2.39 §10 - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §10, carried body | TimeSeries keys retain an explicit 30-day corporate storage window. | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY-COST-OBS preserve | E5 |
| LLD v2.39 §10, carried body | Pricing fallback signals and cost/token series remain auditable without replacing provider-reported cost. | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY-COST-OBS preserve | E4, E5 |
| LLD v2.39 §10, carried body | Run metadata stores execution mode, scope, rigor, approval identity, assumption count, and a 30-day TTL. | In scope | Implemented by Plan 7 / P11-FEAT-GATEWAY-COST-OBS preserve | E5 |

### LLD v2.39 §12C - 3 rows

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| LLD v2.39 §12C, carried body | Persistent state lives in files, git history, manifests, traces, and the evidence ledger, not in unbounded chat context. | In scope | Implemented by Plan 9 / P11-FEAT-GATEWAY-COST-OBS preserve | E4, E5 |
| LLD v2.39 §12C, carried body | The pre-tool guard is never bypassed inside a loop, and the completion evaluator is a cheap Gateway-routed model. | In scope | Implemented by Plan 9 / P11-FEAT-GATEWAY-CORE preserve | E2, E8 |
| LLD v2.39 §12C, carried body | Loop budget fields use the current USD naming; cross-run budget authority is architecture-unblocked but implementation-unscheduled under P9.85-FU-3. | Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled) | Implemented by Plan 9 / P9.85-FU-3 | E12 |

## Named findings and decisions

1. **Aggregator thesis retained and retargeted.** OpenRouter is the default upstream for models and deterministic search while the plugin remains accepted; Vercel is a bounded second model endpoint pending a modest Python transport check and moves to backlog if that check is more than modest. Search is a separate minimal model call and never attaches to the main generation call.
2. **Search replacement is conditional.** The spike measured annotations, domain enforcement, citation structure, provider-reported cost, and direct fetch/extract. The deterministic plugin is deprecated, so release needs a live compatibility gate. Tavily remains rollback-only until replacement acceptance and rollback review pass; it is not the primary architecture.
3. **Tool capabilities are independent.** The current `build_tool_dependencies()` behavior returns `None` when `TAVILY_API_KEY` is absent, which hides all four routes. That hard gate must be removed regardless of the selected backend: search, extract, package, and OSV receive independent capability construction, and package/OSV remain usable without a search credential.
4. **Strict loopback is the trust boundary.** The agent has only the two agent-facing variables. The Gateway owns the aggregator credential, policy, budget, upstream egress, and OTel/OTLP ingress/export. There is no hosted-origin, tenant, OAuth, or non-loopback contract.
5. **MCP disposition is unchanged.** The local MCP trust contract may remain in the guardrail/LLD contract, but no Gateway MCP endpoint is shown or implied. `P11-FU-3` remains open and `P11-FEAT-GATEWAY-MCP` remains blocked.
6. **Observability is OTel-native.** Phoenix is the documented local default; LangSmith is absent from the architecture/dependency set, and no allocated or amortized per-request observability charge is invented.
7. **Budget custody is explicit.** Current-run USD checks and provider-reported cost are current requirements; the cross-run budget-policy implementation remains architecture-unblocked and unscheduled under `P9.85-FU-3`.
8. **Package/advisory custody is explicit.** `P11-FU-2` owns the independent PyPI/npm/Maven and OSV routes; this inventory does not fold them into the core model lane.
9. **Determinism is a design constraint.** OpenRouter's web plugin searches and injects annotations deterministically; Vercel's documented `exaSearch` path is a model-elected tool call. The latter cannot satisfy the harness-gated evidence-first contract without a separate verified-or-fail release gate.
10. **Extraction is bounded and untrusted.** The spike proves plain HTTPS fetch plus HTML-to-text feasibility, but production still needs redirect-by-redirect authorization, SSRF-safe resolution, streaming/size limits, media/encoding checks, and adversarial-HTML tests.
11. **Pricing is not optimized here.** The spike records provider-reported cost and documents engine options, but volume is too low to justify a comparison matrix or engine-price optimization.

## Verification record

- Four repaired PDF digests and page counts match the authoritative section map.
- Text extraction was checked through bundled `pypdf` and an independent WSL2 Poppler path; restored sections and the repaired LLD §0.B flow are present.
- Tier 1 = 83 rows, Tier 2 = 19 rows, Tier 3 = 68 rows, Tier 4 = 21 rows; total = 191 rows.
- Every inventory row has a non-empty disposition, owner, and evidence target.
- Every explicitly cross-run budget-policy row uses `Deferred -> P9.85-FU-3 (architecture-unblocked; implementation unscheduled)`; current-run USD caps and loop budgets remain `In scope`. No row uses the superseded parked/operator-pending wording.
- Package/advisory routes remain independently owned by `P11-FU-2`; the MCP gap remains `P11-FU-3` with no inferred endpoint.
- Stale-reference sweep is clean for affirmative hosted-service, tenant-wallet, OAuth/device, and retired observability contracts; any remaining terms are explicit negative statements in the current source.
