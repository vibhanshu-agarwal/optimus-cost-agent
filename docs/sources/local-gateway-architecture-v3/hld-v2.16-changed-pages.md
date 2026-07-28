---
title: "Optimus-Cost-Agent - Architecture v2.16"
lang: en
---

::: {.sheet .cover data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="1" data-total="13"}
<div class="eyebrow">Optimus-Cost-Agent</div>

# Enterprise Architectural Blueprint

<div class="subtitle">Adaptive Agent Reasoning Swarms and Evolutionary Governance Contracts</div>

<div class="version">Version 2.16</div>

<div class="credit">Architected by: Vibhanshu Agarwal</div>
:::
::: {.sheet data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="3" data-total="13"}
# 5A. Upstream Aggregator Cost Normalization and Single-Key Model

`OPTIMUS_API_KEY` is the only agent-facing credential. It is a local shared secret used to
authenticate the agent process to the loopback Optimus Gateway; it is not an upstream vendor key
or an Optimus tenant wallet. The Gateway process holds one developer-owned aggregator credential
in its own local configuration or OS credential storage. OpenRouter is the default aggregator.
Vercel AI Gateway is an allowed second OpenAI-compatible endpoint when its Python integration is
modest.

The developer funds the aggregator account directly. The aggregator supplies access to many
models, routes across upstream providers, reports normalized usage and USD cost, and debits one
developer-owned balance. The local Gateway preserves the one-key, one-budget, one-ledger thesis by
isolating that credential from the LLM-driven agent, enforcing policy and budget controls, and
recording provider-reported usage.

::: {.callout}
There is no Optimus-hosted account, prepaid balance, subscription, tenant, org, project wallet,
OAuth/device flow, or public Optimus Gateway.
:::

## Normalized cost path

| Stage | Credential and responsibility |
|---|---|
| Local agent | `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` only |
| Loopback Gateway | Shared-secret auth, policy, budget, attribution, aggregator credential isolation |
| Aggregator | Models, routing, provider-reported billing units and `cost_usd` |
| Local ledger | Run/session/request/Gateway/provider request attribution |

Web search currently shares the OpenRouter credential and balance through a dedicated,
deterministic plugin request. Package registry and OSV calls are free public APIs and are not
funding paths. OpenTelemetry trace export has no invented per-request charge.

The one-key property for search is explicitly conditional: OpenRouter has deprecated its
deterministic plugin, and no deterministic aggregator successor is presently documented. Plugin
withdrawal may require a verified-or-fail server-tool design or a standalone search provider with
a second key and balance.
:::

::: {.sheet .tight data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="4" data-total="13"}
# 6. Deterministic Data-Flow Architecture (Phase 1 MVP)

The updated system design integrates closed-loop Harness Engineering directly into the
orchestration sequence:

1. User Request Initiated (IntelliJ IDEA Client).
2. Ingress over ACP Protocol over StdIn JSON-RPC to the Optimus ACP Server Daemon (Asyncio
   Pipeline).
3. Read Topology & Structural Memory Maps from Local Redis State Store (HASH Schema Core Pull),
   which returns active code signatures and cached map assets.
4. Processing inside the Context Optimization Node [FEEDFORWARD CONTROLS] executing AST Slicing,
   Polyglot Fallbacks, ADL Constraint Prompt Injection, and Prompt Anchoring for Cache Tuning.
5. Emits minimal context prompt payload to the LangGraph Stateful Router (Claude Haiku 4.5 Triage
   Gate) for escalation route evaluation.
6. **Delivery to the loopback Optimus Gateway -> approved upstream aggregator (OpenRouter by
   default; Vercel AI Gateway if retained), returning the model output and provider-reported usage
   and USD cost. Model aliases remain policy inputs, but the agent never selects or contacts a
   direct provider adapter.**
7. Validation inside the Automated Fitness Function Engine [FEEDBACK SENSORS] conducting atomic
   structural checks via PyTestArch and static code metrics gate assertions (MI / Complexity
   Check). On FAIL: loops back to Step [6]; on PASS: approves code patch execution path.
8. Storage inside the Local Storage Engine Persistence Layer via Async TS.ADD Numeric Telemetry
   Tracking (RedisTimeSeries) and Async HSET Workspace Metrics Serialisation (Redis HASH
   Architecture Indexes).
9. Real-Time FinOps Console Panel display for IDE Cost Dashboard Live Update Screen.

# 7. Agent Operating Modes & Trust Framework

To guarantee user trust and operational predictability, the control plane implements strict
execution state isolation:

- **Plan/Chat Mode:** Advisory-only mode. The agent may inspect context, discuss requirements,
  propose plans, and produce diffs or snippets for review, but it must not mutate the repository,
  filesystem, external services, or user/project state. Internal cost, audit, and performance
  telemetry is append-only and explicitly allowed.
- **Agent Mode:** Execution mode. The agent is write-authorised and empowered to actively modify
  code, run tools, create files, update tests, and apply patches within approved workspace
  boundaries. Modifications apply to the working tree only after clearing all composite fitness
  engine gates.
- **Code Generation Scope Classification:** Delineates advisory inline fragments from
  implementation deliverables based on clear architectural criteria:
  - `INLINE_SNIPPET`: Explanatory text fragments under 15 lines that touch zero core packages and
    create/delete no files.
  - `PATCH_PROPOSAL`: A bounded diff or file mutation proposal for review.
  - `IMPLEMENTATION_DELIVERABLE`: A multi-file change that requires Agent Mode and all release
    gates.
:::

::: {.sheet data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="7" data-total="13"}
# 10.A System Context Diagram

The IDE, local agent, loopback Gateway, Redis, repository, and optional Phoenix collector are
inside one developer environment. The agent and Gateway are separate processes with separate
environments. The agent authenticates with a local shared secret and cannot read the Gateway's
aggregator credential.

![System context: local Gateway and its controlled external edges](assets/hld-system-context.svg){.diagram}

The Gateway alone may contact the approved upstream aggregator, package registries, OSV, and the
configured OTLP collector. An agent in WSL2 cannot reach a Windows-host Gateway through loopback;
Phase 1 requires both processes in the same network namespace.

<div class="source-note">Figure 10.A - Local-first system context. No MCP endpoint is shown or implied.</div>
:::

::: {.sheet .tight data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="9" data-total="13"}
# 10.C Phase Evolution Diagram

Optimus is designed as a three-phase architecture. Phase 1 is mandatory before any later phase.

**PHASE 1 -> Python Local Agent + Optimus Gateway**
Current - Mandatory before Phase 2

**Release Gate:** the agent runs with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no upstream
key is resolvable in the agent process. The separate loopback Gateway receives only its approved
aggregator key and optional infrastructure configuration.

**PHASE 2 -> Rust Core Rewrite**
Trigger: Python performance ceiling or team scaling

**PHASE 3 -> Agentic Mesh Topology**
Trigger: Multi-repo / multi-team deployment

See: Optimus-Architecture-Roadmap.pdf

# 10.D Where Cost Control Happens

Cost control is not a single checkpoint - it is enforced at four distinct points in the request
lifecycle, each with a different mechanism.

| Control Point | Mechanism | What It Prevents |
|---|---|---|
| 1. Pre-prompt (Feedforward) | AST slicing + cache anchoring + ADL constraints | Unnecessary tokens sent to expensive models. |
| 2. Router (Triage Gate) | Haiku classifies task -> routes to cheapest sufficient model | Over-routing simple tasks to Pro/Opus tier. |
| 3. Rigor Budget (Runtime) | LOW/MEDIUM/HIGH tier caps tool calls + reflection passes | Token-doubling on ceremonial planning loops. |
| 4. Post-call (Attribution) | Gateway usage object -> EvidenceLedger -> RedisTimeSeries | Silent cost accumulation; enables per-run audit. |

# 10.E Where Hallucination Control Happens

Hallucination is controlled through a defence-in-depth stack. No single gate is sufficient; all five
layers must be active simultaneously.

| Layer | Mechanism | What It Catches |
|---|---|---|
| 1. Context Constraint | ADL rules injected pre-prompt; AST slices only relevant code | Irrelevant context that confuses the model. |
| 2. Evidence Gate | Assumption Ledger: every architectural claim must be inspected or logged | Unverified claims promoted to implementation decisions. |
| 3. Tool Policy | ToolInvocationPolicy blocks casual web calls; reason codes required | Model hallucinating external facts without evidence. |
| 4. Fitness Functions | PyTestArch and static metrics gates | Structurally invalid or low-quality changes. |
| 5. Reflection Circuit | Bounded reflection with prior-failure summaries | Repeated failure without targeted replanning. |
:::

::: {.sheet data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="10" data-total="13"}
# 11. Optimus Gateway - Phase 1 Local Process Boundary

The Optimus Gateway is a deterministic loopback process run by the developer alongside the local
agent. It is not a hosted Optimus service, tenant control plane, subscription product, or central
wallet.

## Gateway responsibilities

- Bind to strict loopback and authenticate the agent with a local shared secret.
- Isolate the developer's aggregator credential in Gateway-owned local configuration or OS
  credential storage.
- Route approved model aliases through the surviving OpenAI-compatible transport.
- Enforce model/tool policy, domain rules, call caps, provenance, and the current run's USD budget.
- Return provider-reported usage and cost in a validated GatewayUsage envelope.
- Broker deterministic search, bounded extract, package lookup, and OSV advisory independently.
- Accept structured trace ingress, map it to OpenTelemetry, and export OTLP.
- Persist usage attribution across run, session, request, Gateway request, and provider request IDs.

## Process-scoped configuration

| Agent process environment | Gateway process local configuration |
|---|---|
| `OPTIMUS_GATEWAY_URL=http://127.0.0.1:8765` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter` |
| `OPTIMUS_API_KEY=<local shared secret>` | `OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=<developer key>` |
| No provider, search, or OTel credentials | `OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=<same secret>` |
| Loopback URL only | allowed domains, Redis URL, optional OTLP endpoint |
| No hosted-origin override | no tenant profile, Vault, or non-loopback mode |

Run the agent and Gateway in the same network namespace. A Windows-host Gateway is not loopback
from an agent running inside WSL2.
:::

::: {.sheet data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="11" data-total="13"}
# 11.1 Gateway request / response sequence

![Request sequence from agent to loopback Gateway, aggregator, ledger, and Phoenix](assets/hld-gateway-sequence.svg){.diagram}

The agent sends one authenticated request to the loopback Gateway. The Gateway applies policy and
budget controls, calls the configured aggregator with its Gateway-owned credential, parses
provider-reported usage and cost, and returns the normalized GatewayUsage envelope. The
aggregator credential never enters the agent process or response.

Search follows a separate authorized request and annotation path. Package and OSV routes do not
depend on search availability. Trace delivery is an independent Gateway-to-OTLP operation and
does not create a fabricated per-request observability charge.
:::

::: {.sheet data-doc="Optimus-Cost-Agent - Architecture v2.16" data-page="12" data-total="13"}
# 11A. OpenTelemetry Trace Observability

Phase 1 uses OpenTelemetry spans and OTLP as the vendor-neutral trace contract across planning,
Gateway calls, tool invocation, validation, retries, and final response generation. The local
agent sends authenticated structured trace ingress to the Gateway; the Gateway validates and
redacts fields, maps them to OTel spans/events, and exports OTLP. Arize Phoenix is the documented
local default. Any OTLP-compatible backend may replace it without changing Optimus
instrumentation; Langfuse may be considered for team-scale deployments.

Trace export records operational telemetry, not an invented billable provider request. No
allocated or amortized observability `cost_usd` is added to the usage ledger. Infrastructure cost
is an operator concern outside per-request accounting.

Required attributes retain run, session, request, Gateway/provider request, execution mode,
generation scope, model/provider, cache, `cost_usd`, billing units, policy/tool, validation, retry,
and failure attribution. Secrets are redacted before export.

## 12. Testing and quality gates

| Concern | Tooling | Role in gates |
|---|---|---|
| Code coverage | `coverage.py`, `pytest-cov` | Release gate: at least 80%, safety-critical modules do not regress |
| Agent quality eval | DeepEval, Ragas | Task quality, correctness, groundedness |
| Adversarial/red-team | PyRIT | Prompt injection, tool-control, and trust-boundary validation |
| Trace observability | OpenTelemetry + OTLP; Phoenix default | Debugging and regression analysis, not a coverage metric |

OTel/OTLP trace validation is tracked separately from production-code coverage. LangSmith is not
part of the architecture or dependency set.
:::
