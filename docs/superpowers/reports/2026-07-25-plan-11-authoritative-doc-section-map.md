# Plan 11 Authoritative-Document Section Map

**Status:** Plan 11.13 authoritative-publication map; Task 10 candidate and source-pin baselines retained for provenance.

**Baseline:** `agent/codex/local-gateway-architecture-v3` at `85852b3`.

**Purpose:** Maintain a complete, version-pinned section map of the four authoritative Phase 1
documents, their Task 10-approved MCP Gateway amendment candidates, and the Plan 11.13
successors. This is a shallow map, not the requirement-level inventory. The historical v3
source-pin and amendment rows below remain provenance; the Plan 11.13 overlay is authoritative
for current MCP conclusions.

The map applies the existing deferred-work custody rule to requirements: every section has an
owner or is explicitly marked `UNOWNED` or `Cross-cutting`. A normative statement discovered
later in a mapped section is an extraction defect, not an invitation to silently widen a frozen
specification. The candidate PDFs remain separate from the final Task 12 publication gate.

## Source set and digests

The version pin uses the filename and rendered cover page. SHA-256 is over the exact source bytes.

| Source document | Version pin | Pages | SHA-256 |
|---|---:|---:|---|
| `Optimus-Cost-Agent-Architecture-v2.16.pdf` (HLD) | v2.16 | 13 | `6C2C98FE2327A6C466CAD3EB1800335EB59F0E1F65B2CB8E1E3401D7CFA05801` |
| `Optimus-Cost-Agent-LLD-v2.39.pdf` | v2.39 | 40 | `82513729FD1A6E87FAD310DD90A18C996981B68024204E56CCA65377495585DE` |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | v1.1 | 16 | `27EF0657CCEC5568D3E3769C7320223D1BFE3CF6F4702564CBD0A8A391F11029` |
| `Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | v1.5 | 14 | `F3D744EC175B1E18E8B1E4E271997A0BB12666CC33CA7154A40BF5298588DA8D` |

The filename, rendered cover, running headers, and PDF metadata title agree for all four final
documents. The target version is asserted on every page; Guardrails page 16 is the sole explicit
exception permitting the superseded version in its historical change log. A future refresh must
recompute the page count, metadata, cover/header versions, and digest.

## Historical Task 10 amendment candidate set

| Candidate document | Version | Pages | SHA-256 | Replacement pages |
|---|---:|---:|---|---:|
| `Optimus-Cost-Agent-Architecture-v2.17.pdf` | v2.17 | 13 | `A21BDB01BC737FA3D8EBFFBA8B8B7DF96C65101812E17F31C3C7324368D15024` | 8 |
| `Optimus-Cost-Agent-LLD-v2.40.pdf` | v2.40 | 40 | `0329AEF8B5392E05DDBB19AC3F76F3CE7F4FE3C4B728AEF6CBFC4DE84B324D03` | 22 |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | v1.2 | 16 | `461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070` | 9 |
| `Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | v1.6 | 14 | `B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4` | 12 |

The four PDFs above are immutable Plan 11.13 inputs and provenance only. The successor PDFs below
are the current authoritative publication state.

## Plan 11.13 current authoritative set

| Current document | Version | Pages | SHA-256 | Replacement pages | Reversal package |
|---|---:|---:|---|---:|---|
| `Optimus-Cost-Agent-Architecture-v2.18.pdf` | v2.18 | 13 | `0F8725765FECC9A93045FD26630457DFE7112508DF164A3EC5BCC55DBC976807` | 8 | sibling package |
| `Optimus-Cost-Agent-LLD-v2.41.pdf` | v2.41 | 40 | `69400FD474EB30711FCC9A061243D6A4D2E35D39D7794D4AA69F5FF51B98109B` | 22 | sibling package |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.3.pdf` | v1.3 | 16 | `94F8F829D60FB9945237227B16E82CB523659E4D67C8488909035FE9BDB27957` | 9 | sibling package |
| `Optimus-Cost-Agent-Test-Strategy-v1.7.pdf` | v1.7 | 14 | `31A60C6A198C60CC1203FF5C4A8E6E0300A820EC18CC702E25F246EDC51DC0B0` | 12 | sibling package |

Exact source maps, immutable-input proof, rendered-page inspection, and the bidirectional audit
are recorded in [Plan 11.13 evidence](2026-08-15-plan-11-13-authoritative-document-reversal-evidence.md).

## Historical Task 10 diagram and render-survey scope

The historical Task 10-approved v2.40 component-flow candidate is complete and legible; it shows the agent
pre-tool/context-admission gate and Gateway discovery, transport, allowlist, freshness, resource,
pagination, and budget gates without an agent-to-MCP edge or agent-held upstream credential. The
Task 10-approved v2.17 system-context candidate keeps the catalog as operator-side reference only
and shows Gateway-owned remote HTTP and Docker-contained stdio edges. All three amended SVGs pass
text-bound and connector-intersection checks, and the final assembled HLD/LLD PDFs were rerendered
after the diagram corrections.

## Plan 11.13 ownership overlay

Gateway-brokered MCP claims are retired; the historical Task 10 amendment material below is
provenance, not current authority. ACP `mcpServers` remains client supplied, and local
`MCPTrustRegistry`, `validate_tool_call`, `PreToolGuard.check`, and untrusted-output handling
remain agent/client controls. The Test Strategy markers require independently authored client-MCP
servers. Registry publication identity remains separate from both the retired Gateway feature and
client MCP.

## Ownership findings requiring follow-up

These are the rows that matter most. They are intentionally surfaced before the full bookkeeping
tables.

| Finding | Evidence | Current disposition |
|---|---|---|
| Package lookup and security advisory routes | LLD v2.39 §0.D and the named endpoint block specify `/v1/tools/package/lookup` and `/v1/tools/security/advisory`. | Implemented by `P11-FEAT-GATEWAY-TOOLS` in Plan 11.2 / PR #88. The remaining migration work is to keep these routes available independently of search configuration. |
| Two agent-facing model shapes share one upstream transport | LLD v2.39 §§0.D, 6, and 6.1 specify `/v1/responses` with `input` and `/v1/chat/completions` with `messages`, reject mixed shapes, and normalize both onto the OpenAI-compatible aggregator transport. | Route and shape support is implemented by `P11-FEAT-GATEWAY-CORE`; retiring direct-provider adapters and adopting the approved aggregator are follow-up work in the same feature identity. |
| Authenticated structured trace ingress | LLD v2.39 §0.D and the named endpoint block both specify `/v1/observability/traces`. | Route serving is implemented by `P11-FEAT-GATEWAY-CORE`; real OTel/OTLP export to Phoenix remains owned by `P11-FEAT-GATEWAY-COST-OBS`. |
| Gateway-MCP historical contract and current boundary | The v2.17/v2.40 amendment candidates are historical inputs. Plan 11.13 current PDFs retire their Gateway-brokered claims while preserving client-supplied ACP `mcpServers` and local validation/guarding. | `P11-FEAT-GATEWAY-MCP` is retired; Plan 11.13 evidence records the current PDFs and audit. `P11-FU-3` remains historical closure evidence. |
| Search backend migration must preserve deterministic evidence | LLD v2.39 §§9C.1-9C.4 and Test Strategy v1.5 §7A require a minimal deterministic search call, verified annotations/domain enforcement, bounded extract, and route-specific dependency construction. | `P11-FEAT-GATEWAY-TOOLS`. OpenRouter is the default; Tavily remains only a rollback seam until replacement acceptance and rollback review pass. |
| Observability is vendor-neutral and has no amortized charge | HLD v2.16 §11A, LLD v2.39 §§10A and 11A, Guardrails v1.1 §9, and Test Strategy v1.5 §8A specify OTel/OTLP with Phoenix as the documented default. | `P11-FEAT-GATEWAY-COST-OBS`. No backend dependency or allocated/amortized observability cost belongs in the ledger. |
| The LLD component-flow source defect is repaired | Rendered LLD v2.39 page 2 (§0.B) contains the complete tool and trace ingress flow and passes text-bound and connector-intersection checks. | Closed by the v2.39 publication. This does not close the separate MCP decision in `P11-FU-3`. |
| ACP registry publication has no source section | None of the four pinned documents contains a normative ACP registry registration/publication section. | `UNOWNED` under `P11-FEAT-REGISTRY` until its research gate supplies the missing authoritative source and requirements. |
| Multi-IDE UI expectations are not normatively specified | HLD v2.16 §6 defines IDE/ACP ingress, while Test Strategy v1.5 requires independent `acpx` protocol evidence but does not define IDE plugin UI proof. | `P11-FEAT-IDE` if opened by charter amendment; otherwise `UNOWNED`, not an implied v1.0 requirement. |

## Owner vocabulary and extraction rule

- `P11-FEAT-GATEWAY-CORE`, `P11-FEAT-GATEWAY-TOOLS`,
  `P11-FEAT-GATEWAY-COST-OBS`, historical/retired `P11-FEAT-GATEWAY-MCP`, `P11-FEAT-ZED-RESUME`,
  `P11-FEAT-REGISTRY`, and `P11-FEAT-IDE` are the permanent Plan 11 feature identities. Plan 11.x
  numbers are assigned only when a feature is picked up; frozen Plan 11.1 and 11.2 are not edited.
- `P11-FU-3` owns the open MCP source-contract decision. `P9.85-FU-3` owns future cumulative
  session/project spend policy; the local current-run Gateway budget authority no longer blocks
  that item architecturally, but it remains undesigned and unscheduled.
- `Plan 12` is the post-v1.0 context-window and intelligent-selection lane.
- `Implemented by Plan N` records an existing roadmap lane that already owns the section's Phase 1
  implementation surface. It does not waive the requirement from the v1.0 evidence gate.
- `Cross-cutting` means the section is shared by multiple existing or future lanes and must be
  traced in each affected feature inventory.
- `UNOWNED` means no stable owner is currently recorded. It is a finding, not permission to ignore
  the section.

Each eventual requirement-level inventory row must use the shape:

| Citation | Normative statement | Disposition | Owning feature/source ID | Evidence target |
|---|---|---|---|---|
| `LLD v2.39 §0.D` | Exact statement from the source | `In scope`, `Deferred -> <stable ID>`, or `Excluded -> <reason>` | Stable owner | Named executable or release artifact |

No requirement-level rows are created in this section map.

## HLD v2.16 section map

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| HLD v2.16 §1 | Executive Summary | Phase 1 architecture thesis and deterministic harness boundary | Cross-cutting | Carried body; charter context for every feature, not a standalone implementation lane. |
| HLD v2.16 §2 | Harness Engineering & Context Optimization | Feedforward context shaping and feedback validation | Plan 12 | Carried body with the declared inline v2.16 self-reference correction; intelligent selection and optimization remain Plan 12 work. |
| HLD v2.16 §3 | Automated Architectural Fitness Functions | Scope, automation, invocation, return, and activation gates | Implemented by Plans 8 and 8.5 | Later feature inventories must still cite the gates they rely on. |
| HLD v2.16 §4 | Data Governance Plane & Local Storage Boundaries | Redis structural memory, TimeSeries telemetry, and retention | Implemented by Plan 7 | Storage and retention are evidence dependencies for Gateway and release work. |
| HLD v2.16 §5 | Request-Level Cost Attribution | Provider usage, pricing snapshots, and request-level cost records | Implemented by Plan 7 | The v3 Gateway must persist provider-reported usage and USD cost compatibly with this ledger. |
| Historical source pin — HLD v2.16 §5A | Upstream Aggregator Cost Normalization and Single-Key Model | One agent-facing shared secret, one Gateway-owned aggregator credential, provider-reported usage/cost, and current-run budget authority | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-COST-OBS` | Historical v2.16 source wording retained for provenance only; superseded for current MCP publication state by the HLD v2.17 amendment overlay above. |
| HLD v2.16 §6 | Deterministic Data-Flow Architecture (Phase 1 MVP) | IDE/ACP ingress through strict-loopback Gateway, harness-gated evidence, validation, storage, and FinOps output | Cross-cutting | Search is a separate minimal model call; attaching `:online` to the main generation call is rejected. |
| HLD v2.16 §7 | Agent Operating Modes & Trust Framework | Plan/Chat, Agent mode, and generation-scope classification | Implemented by Plan 2 | Guardrail sections refine this boundary. |
| HLD v2.16 §8 | Tool Governance & Evidence Acquisition | Evidence-first policy, typed tools, and external-call authorization | Implemented by Plan 4 | Gateway-side policy revalidation remains defense in depth. |
| HLD v2.16 §9 | Adaptive Agent Execution Strategy & Rigor Policy | Rigor tiers, strategy selection, and bounded reflection | Implemented by Plan 9 | Plan 12 may optimize selection but does not replace this Phase 1 contract. |
| HLD v2.16 §10 | Architectural Control Flow | System context, governance loop, Phase 1 release gate, and normative control tables | Cross-cutting | §10.A routes model/tools/traces through the local Gateway; §10.C separates agent and Gateway credential/egress evidence. |
| HLD v2.16 §10.A | System Context Diagram | Developer-machine/network-namespace boundary, local agent/Gateway processes, controlled external edges, and Phoenix/OTLP | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-COST-OBS` | Local Gateway and agent share a namespace; no MCP endpoint is shown or implied. |
| HLD v2.16 §10.B | Governance Loop Diagram | Feedforward constraints, triage routing, feedback sensors, and mutation gate | Cross-cutting: Plans 2, 4, 8, and 8.5 | Carried governance diagram; no new Gateway or provider contract is inferred from the figure. |
| HLD v2.16 §10.C | Phase Evolution Diagram | Phase 1 local agent plus Gateway release gate, followed by bounded future phases | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / Plan 12 | The release gate requires only agent-facing Gateway URL/shared secret and no upstream key in the agent process. |
| HLD v2.16 §10.D | Where Cost Control Happens | Pre-prompt, router, runtime rigor budget, and post-call attribution controls | Cross-cutting: Plans 2, 7, 9, and `P11-FEAT-GATEWAY-COST-OBS` | Restored normative control table; provider-reported usage and EvidenceLedger attribution remain authoritative. |
| HLD v2.16 §10.E | Where Hallucination Control Happens | Context, evidence, tool policy, fitness, and reflection control layers | Cross-cutting: Plans 4, 8, and 9 | Restored normative control table; evidence-first and fitness gates remain required together. |
| HLD v2.16 §11 | Optimus Gateway - Phase 1 Local Process Boundary | Strict-loopback shared-secret boundary, aggregator routing, typed tools, accounting, and policy | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | Direct-provider adapters are migration work; package/OSV routes must remain independent of search configuration. |
| HLD v2.16 §11.1 | Gateway request / response sequence | Agent-to-loopback-Gateway-to-aggregator sequence with provider-reported usage and correlated trace/accounting records | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-COST-OBS` | Preserve run, session, Gateway request, and provider request attribution without tenant/org/project identity. |
| HLD v2.16 §11A | OpenTelemetry Trace Observability | OTel-native instrumentation, authenticated trace ingress, OTLP export, and Phoenix live evidence | `P11-FEAT-GATEWAY-COST-OBS` | Phoenix is the documented default, not an API dependency; there is no separate trace billing path or observability allocation. |
| HLD v2.16 §12 | Testing and quality gates | Coverage, live dependency, strict-loopback, deterministic search, accounting, and trace evidence | Cross-cutting | Test Strategy v1.5 is authoritative; fake-based tests cannot justify named live claims. |
| HLD v2.16 §13 | Agent Execution Safety & Guardrails | Safety, approval, and bounded execution policy anchor | Cross-cutting | Detailed policy is in Guardrails v1.1; implementation custody is distributed across Plans 5, 6, 6.5, 8.5, and 9. |

## LLD v2.39 section map

The final LLD retains image-backed carried pages, so its section sequence is checked against both
page renders and extracted text. The unnumbered endpoint block on page 5 remains a separate row
because it carries normative model, tool, and trace-ingress routes.

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| LLD v2.39 §0 | Optimus AI Gateway Architecture | Local-first mandatory Gateway, one agent-facing shared secret, aggregator transport, typed tools, accounting, and traces | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | Direct single-provider adapters are removed by follow-up migration; Vercel remains bounded by the modest-effort Python check. |
| LLD v2.39 §0.A | Recommended architecture | Agent and Gateway in one loopback/network namespace with process-scoped credentials and policy | `P11-FEAT-GATEWAY-CORE` | No hosted service, tenant wallet, or tenant-level profile remains. |
| LLD v2.39 §0.B | Gateway Component Flow | Complete agent path through documented ingress, auth/policy, model and tool routing, accounting, and trace ingress | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | The prior clip is resolved. The diagram shows no MCP branch or endpoint; `P11-FU-3` remains open separately. |
| LLD v2.39 §0.C | Gateway responsibilities | Shared-secret auth, aggregator routing, independent typed tools, provider usage/cost, trace ingress, and secret isolation | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | MCP is explicitly outside this correction and is not a Gateway responsibility in the current source. |
| LLD v2.39 §0.D | Gateway-facing API shape | Two model shapes, four typed tool routes, and authenticated structured trace ingress | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | Core route/shape support and Plan 11.2 package/advisory routes are implemented; remaining work is architecture migration and live evidence. |
| LLD v2.39 §0.E | Process-scoped configuration boundary | Agent-only Gateway URL/shared secret versus Gateway-only aggregator/search-migration/OTLP configuration | `P11-FEAT-GATEWAY-CORE` | Strict loopback replaces production-mode and trusted-host bypasses; credential scans remain process-specific. |
| LLD v2.39 §0A | Local vs. Gateway Configuration and Provider-Cost Mapping | Runtime credential scopes, OpenAI-compatible aggregator choice, provider-reported billing units/cost, and current-run budget | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-COST-OBS` | OpenRouter is default; Vercel is optional only if Python integration is modest. No wallet/credit or observability-allocation model remains. |
| LLD v2.39 §0A (named block) | Gateway Tool and Observability Endpoints | Agent-facing model routes, four typed tools, and `/v1/observability/traces` | Cross-cutting: `P11-FEAT-GATEWAY-CORE` / `P11-FEAT-GATEWAY-TOOLS` / `P11-FEAT-GATEWAY-COST-OBS` | Package/advisory routes are implemented by Plan 11.2; search configuration must not gate their availability. |
| LLD v2.39 §1 | ACP Protocol Framing & JSON-RPC Contract Specification | Content-Length framing, size limits, and JSON-RPC errors | Implemented by Plan 1 | Carried body; Zed/session-resume work depends on this boundary but does not replace transport ownership. |
| LLD v2.39 §2 | Cross-Platform Stream Transport Layer | Stdio framing and async stream transport | Implemented by Plan 1 | Carried body; re-verify with independent `acpx` evidence at the relevant gate. |
| LLD v2.39 §3 | Queued Task Lifecycle, Backpressure Controls & Runtime Pooling | Task concurrency, pooling, cancellation, and duplicate IDs | Implemented by Plan 1 | Carried body; shared runtime dependency for every feature. |
| LLD v2.39 §4 | Behavioral Governance: Operating Modes, Strategies & Scope Classifier | Modes, generation scope, rigor, tool operation, and error contracts | Cross-cutting | Plan 2 owns the mode boundary; Plan 9 owns execution strategy. |
| LLD v2.39 §4A | Agent State Model and Execution Pathways | Lifecycle states, valid transitions, permission matrix, and execution pathway | Cross-cutting | Existing Plans 2 and 9.5 own the baseline. |
| LLD v2.39 §5 | ADL Parser Continuity & Architectural Evolution | ADL parser strategy and structural validation | Implemented by Plan 8 | Fitness-gate consumers must trace their parser assumptions. |
| LLD v2.39 §6 | Resilient Aggregator Calling Layer and Tenacity Rules | Both agent-facing shapes, OpenAI-compatible upstream transport, normalized envelopes, and bounded retries | `P11-FEAT-GATEWAY-CORE` | OpenRouter is default; direct-provider retirement and bounded Vercel evaluation remain under CORE. |
| LLD v2.39 §6.1 | OpenAI-compatible upstream pattern | `input`/`messages` validation onto `UrllibOpenAICompatibleClient`, provider-reported usage/cost, and failure classification | `P11-FEAT-GATEWAY-CORE` | `anthropic_client.py` and the Anthropic-native branch are retirement targets; permanent failures do not retry. |
| LLD v2.39 §7 | Composite Fitness Engine Scaffolding | Dependency, metric, test-architecture, and composite gates | Implemented by Plan 8 | Carried body; Plan 11 features consume these gates. |
| LLD v2.39 §8 | Patch Workspace Lifecycle Boundaries | Shadow workspace, mode enforcement, atomic apply, and rollback | Implemented by Plan 8 | Carried body; cross-reference HLD §7 and Guardrails §§2-6. |
| LLD v2.39 §9 | Tool Registry, Invocation Policy & Evidence Ledger | Typed tool registry, policy matrix, and evidence recording | Cross-cutting | Plan 4 owns evidence/tool policy; Plan 7 owns cost reconciliation. |
| LLD v2.39 §9A | Tool Class Enum & Registry Contract | Tool classes, reasons, registry entries, and call authorization | Implemented by Plan 4 | Plan 5 adds the pre-tool enforcement boundary. |
| LLD v2.39 §9B | Deterministic Invocation Policy Matrix | Signal-to-tool-class routing and evidence requirements | Implemented by Plan 4 | The harness gate remains authoritative for deciding when search occurs. |
| LLD v2.39 §9C | Typed Evidence Acquisition Wrappers | Strict-loopback typed search/extract wrappers, untrusted output handling, provenance, and independent package/advisory routes | Cross-cutting: Implemented by Plan 4 / `P11-FEAT-GATEWAY-TOOLS` migration | The Gateway backend changes; the harness gate and EvidenceLedger remain. |
| LLD v2.39 §9C.1 | Deterministic search contract | One minimal model call per search with deterministic plugin execution, annotations, domain enforcement, URL revalidation, and usage/cost | `P11-FEAT-GATEWAY-TOOLS` | Attaching `:online` to main generation is rejected. OpenRouter's deterministic plugin fits the evidence-first gate; Vercel `exaSearch` is model-elected and therefore not the approved search path. |
| LLD v2.39 §9C.2 | Plugin deprecation and successor gate | Verified-or-fail requirements for any future server-tool successor | `P11-FEAT-GATEWAY-TOOLS` | Prove `max_uses: 1`, exactly one search, accounting, annotations, domain enforcement, and fail-closed behavior. |
| LLD v2.39 §9C.3 | Bounded direct extract | Plain HTTP fetch plus HTML-to-text with exact provenance, redirect/SSRF/media/size/time controls | `P11-FEAT-GATEWAY-TOOLS` | Extract is not a second search or an arbitrary fetch path. |
| LLD v2.39 §9C.4 | Independent tool dependency construction | Capability-specific route availability for search, extract, package, and advisory routes | `P11-FEAT-GATEWAY-TOOLS` | Tavily currently hard-gates all four routes; restructure regardless of which search backend wins. |
| LLD v2.39 §9D | Gateway Server-Side Policy Revalidation | Domain, provenance, current-run USD budget, call caps, tool policy, and fail-closed checks | `P11-FEAT-GATEWAY-TOOLS` / `P9.85-FU-3` for future cross-run policy | Local checks remain convenience/defense in depth. This section adds no cumulative cross-run policy. |
| LLD v2.39 §9E | Evidence Ledger Schema | Evidence/audit entries and Decimal-safe Gateway usage reconciliation by run/session/request identity | Cross-cutting: Implemented by Plan 7 / `P11-FEAT-GATEWAY-COST-OBS` | Search/extract annotations, provider identity, and final policy disposition remain joinable. |
| LLD v2.39 §9E.1 | Protocol-visible USD rename custody | Separate wire-aware migration from credit-named fields to USD fields | `P11-FEAT-GATEWAY-COST-OBS` | The rename must update schemas, persistence, fixtures, and consumers atomically; it adds no new budget policy. |
| LLD v2.39 §10 | Usage Accounting Service and TimeSeries Policy | Provider-reported cost authority, full attribution, malformed-usage failure, and TimeSeries compatibility | Cross-cutting: Implemented by Plan 7 / `P11-FEAT-GATEWAY-COST-OBS` | Do not estimate cost post hoc when provider usage/cost is present. |
| LLD v2.39 §10.1 | RedisTimeSeries persistence | Existing 30-day retention, idempotent series setup, run/session/request labels, and reconciliation | Cross-cutting: Implemented by Plan 7 / `P11-FEAT-GATEWAY-COST-OBS` | Persist `cost_usd` and billing units with request/provider/model attribution. |
| LLD v2.39 §10A | Provider Usage Ledger and Observability Export | ProviderUsage/GatewayUsage reconciliation and OTel/OTLP span export | `P11-FEAT-GATEWAY-COST-OBS` | Phoenix is the live default; trace delivery has no allocated or amortized per-request charge. |
| LLD v2.39 §11 | Sprint 1 Implementation Checklist | Trust boundary, aggregator transport, independent tools, migration acceptance, and release evidence | Cross-cutting | Checklist ownership follows the stable feature identities and does not reopen frozen plans. |
| LLD v2.39 §11.1 | Accounting, telemetry, and release evidence | Decimal-safe accounting, OTLP-to-Phoenix evidence, retired-key scans, and real dependency tiers | Cross-cutting | The deterministic search plugin is release-blocking while it remains the Phase 1 path. |
| LLD v2.39 §11A | Test Coverage and Observability Cross-Reference | Coverage threshold plus Redis, Gateway, ACP, trace, and release evidence tiers | Cross-cutting | Test Strategy v1.5 is authoritative; OTel assertions do not count toward code coverage. |
| LLD v2.39 §12 | Guardrail and Workflow Component Contracts | Shared loopback Gateway, current-run USD budget, provider-reported cost, OTel path, and guardrail/workflow contracts | Cross-cutting | The complete parent and child contracts are preserved; MCP remains a local trust-boundary topic only, not a Gateway endpoint. |
| LLD v2.39 §12A | Permission & Pre-Tool Enforcement | `PermissionPolicy`, `PermissionDecision`, `PreToolGuard`, `CommandSafetyValidator`, and `ToolInvocationAuditEvent` contracts | Implemented by Plan 5 | Restored co-located contract body; pre-tool enforcement remains the authoritative action gate. |
| LLD v2.39 §12B | Prompt-Injection & MCP Supply-Chain Trust | `MCPTrustRegistry` and `ConfigTrustScanner` for local trust and poisoning controls | Implemented by Plan 6.5 | Preserved local MCP trust contract; it does not authorize or imply a Gateway MCP route. |
| LLD v2.39 §12C | Bounded Agent Loops | `GoalLoopController`, `IterationState`, `CompletionEvaluator`, `ProgressLedger`, `LoopBudgetPolicy`, and `LoopStopReason` | Implemented by Plan 9 / `P11-FEAT-GATEWAY-COST-OBS` preserve | Current-run USD budget and cheap Gateway-routed evaluator remain bounded-loop controls; future cross-run policy stays with `P9.85-FU-3`. |
| LLD v2.39 §12D | Curated Workflow Skills | `SkillRegistry`, `SkillManifest`, `SkillTrustPolicy`, and `SkillInvocationPolicy` contracts | Implemented by Plan 9 / `P11-FEAT-GATEWAY-COST-OBS` preserve | Restored contract body; skill trust does not widen permissions or add a hosted, direct-provider, LangSmith, or Gateway MCP path. |

## Guardrails and Workflow Strategy v1.1 section map

The cross-reference register is recorded as a named row because it assigns authority among the four
documents. The repaired pages preserve §7.1, §7.2, §8.1, and §8.2 as individually traceable
subsections; the completion-evaluator wording remains co-located prose rather than a new heading.

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| Guardrails v1.1 §0 | Purpose & Document Scope | Canonical guardrail/workflow policy boundary | Cross-cutting | References HLD §§7-9, LLD §4A/§10A, and Test Strategy §8A/§14. |
| Guardrails v1.1 §0 (register) | Cross-Reference Register | Authority and relationship of HLD, LLD, Test Strategy, and this document | Cross-cutting | The register is part of §0 on page 2. |
| Guardrails v1.1 §1 | Control-Plane Overview | Layered permission, pre-tool, sandbox, audit, and CI control flow | Cross-cutting | Shared by Plans 5, 6, 6.5, 8.5, and 9. |
| Guardrails v1.1 §2 | Permission Model | Allow/deny policy, mode overlay, and human approval | Implemented by Plan 5 |  |
| Guardrails v1.1 §2.1 | Project-Level Allow Rules | Project-scoped allow policy | Implemented by Plan 5 |  |
| Guardrails v1.1 §2.2 | User-Level Deny Rules | User deny precedence and immutable safety floor | Implemented by Plan 5 |  |
| Guardrails v1.1 §2.3 | Mode Mapping | Plan/Chat versus Agent mode mapping | Implemented by Plan 5 | Cross-reference LLD §4 and the current §12 guardrail anchor. |
| Guardrails v1.1 §2.4 | Human Approval | HOLD and explicit approval path | Implemented by Plan 5 |  |
| Guardrails v1.1 §2.5 | Decision Order | Deterministic deny, allow, impact, and classifier order | Implemented by Plan 5 |  |
| Guardrails v1.1 §3 | Pre-Tool Guard / Hook Layer | Pre-execution deterministic validation | Implemented by Plan 5 |  |
| Guardrails v1.1 §3.1 | Deterministic First | Deterministic checks before classifiers | Implemented by Plan 5 |  |
| Guardrails v1.1 §3.2 | Hook Surface | Tool classes and pre-tool integration point | Implemented by Plan 5 |  |
| Guardrails v1.1 §4 | Shell Command Sanitization | Shell safety and fail-closed command validation | Implemented by Plan 5 |  |
| Guardrails v1.1 §4.1 | Required Checks | Destructive, pipe-to-shell, credential, transport, and egress checks | Implemented by Plan 5 |  |
| Guardrails v1.1 §4.2 | The Homoglyph Problem | Unicode confusable detection | Implemented by Plan 5 |  |
| Guardrails v1.1 §4.3 | Implementation Posture | Tirith or equivalent validator boundary | Implemented by Plan 5 |  |
| Guardrails v1.1 §5 | Prompt-Injection & MCP Supply-Chain Defense | Config/repository poisoning and local MCP trust boundary | Implemented by Plan 6.5 | This does not authorize a Gateway MCP endpoint. |
| Guardrails v1.1 §5.1 | Config & Repo Poisoning | Ingest scanning for untrusted configuration | Implemented by Plan 6.5 |  |
| Guardrails v1.1 §5.2 | MCP Servers Are Arbitrary Code | No implicit trust or auto-load | Implemented by Plan 6.5 |  |
| Guardrails v1.1 §5.3 | Explicit Threat Scenarios | Threat fixtures and expected denials | Implemented by Plan 6.5 |  |
| Guardrails v1.1 §6 | Pre-commit & CI Gates | Local/CI parity and clean-environment verification | Cross-cutting | Plans 6, 6.5, and 8.5 contribute distinct gates. |
| Guardrails v1.1 §6.1 | Local Pre-commit - Four-Layer Config | Local hook stack | Implemented by Plan 6.5 |  |
| Guardrails v1.1 §6.2 | CI - Clean-Environment Re-Check | CI revalidation and hygiene parity | Implemented by Plan 8.5 |  |
| Guardrails v1.1 §7 | Bounded Agent Loops and Goal-Driven Execution | Loop termination and bounded work | Implemented by Plan 9 / Gateway budget cross-cutting | Current-run budget authority is the local Gateway; future cross-run policy remains `P9.85-FU-3`. |
| Guardrails v1.1 §7.1 | Phase 1 Stance | Phase 1 loop posture and constraints | Implemented by Plan 9 | Carried body. |
| Guardrails v1.1 §7.2 | Required Controls | Iteration, USD budget, wall-clock, completion, evidence, clean-diff, pre-tool, approval, and repeated-failure controls | Implemented by Plan 9 / `P11-FEAT-GATEWAY-COST-OBS` preserve | The `max_budget_credits` → `max_budget_usd` rename is the only row change; it adds no cross-run limit. |
| Guardrails v1.1 §8 | Curated Workflow Skills | Reviewed, versioned, narrow procedural artifacts that cannot widen permissions | Implemented by Plan 9 | The repaired source preserves the parent section and both child contracts below. |
| Guardrails v1.1 §8.1 | Skill Rules | Curated, reviewed, versioned skill artifacts with focused procedures and required metadata | Implemented by Plan 9 | Restored co-located subsection; generated skills remain draft-only until reviewed. |
| Guardrails v1.1 §8.2 | Trust & Invocation | Allowed-tools enforcement, deny-rule precedence, manifest matching, and draft/untrusted blocking | Implemented by Plan 9 | Restored co-located subsection; skill invocation cannot widen the agent tool surface. |
| Guardrails v1.1 §9 | Cost Model Alignment | Shared loopback Gateway, developer aggregator account, current-run USD budget, provider cost ledger, and OTel path | `P11-FEAT-GATEWAY-COST-OBS` | Guardrails introduce no second credential, direct adapter, cost path, or observability backend dependency. |
| Guardrails v1.1 §10 | Implementation contracts | LLD authority for guardrails, loops, skills, and local Gateway accounting/telemetry | Cross-cutting | Regenerated parent section; carried subsections below remain authoritative where not contradicted. |
| Guardrails v1.1 §10.1 | Component Inventory | Guardrail/workflow component list | Cross-cutting | Carried body. |
| Guardrails v1.1 §10.2 | Representative Contract Shapes | Pydantic/API contract examples | Cross-cutting | Carried body; credit-named fields are subject to the separate USD migration. |
| Guardrails v1.1 §11 | Test Coverage Mapping (Test Strategy Anchor) | Test-category relationship to Test Strategy | Cross-cutting | Test Strategy v1.5 §14 is the detailed companion. |
| Guardrails v1.1 §11.1 | Guardrail & Workflow Traceability | Traceability rows for safety and workflow controls | Cross-cutting |  |
| Guardrails v1.1 §11.2 | Required Test Cases | Required executable categories | Cross-cutting |  |
| Guardrails v1.1 §12 | References | Source references and authority links | Cross-cutting |  |
| Guardrails v1.1 §13 | Document Control & Cross-Reference Register | Version bumps, anchors, and document-control history | Cross-cutting | Guardrails page 16 may legitimately mention v1.0 as historical change-log evidence. |

## Test Strategy v1.5 section map

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| Test Strategy v1.5 §1 | Test objectives | Full Plan/Agent proof with only the agent-facing Gateway URL/shared secret and separately scoped Gateway aggregator credential | Cross-cutting | Applies to every Plan 11 feature inventory and credential/egress gate. |
| Test Strategy v1.5 §2 | Scope and non-scope | Strict loopback, aggregator transport, deterministic search/extract, independent tools, accounting, Phoenix, and explicit exclusions | Cross-cutting | Hosted service, direct adapters, cross-run policy, MCP Gateway contract, and comparison matrices are out of scope. |
| Test Strategy v1.5 §3 | Test pyramid and evidence tiers | Unit, contract, real Redis/Gateway/ACP/E2E/release tiers with explicit fake limits | Cross-cutting | Named dependency claims require the real dependency; ACP evidence uses independent `acpx`. |
| Test Strategy v1.5 §4 | Requirements-to-Test Traceability Matrix | LLD claim-to-test mapping | Cross-cutting | Carried body; feature inventories must extend it. |
| Test Strategy v1.5 §5 | Mode and State Transition Tests | MutationGuard, state machine, and mode boundary tests | Implemented by Plan 2 | Carried body. |
| Test Strategy v1.5 §6 | Tool Invocation Tests | Harness-gated deterministic search, annotation/domain checks, bounded extract, and independent package/OSV routes | Implemented by Plan 4 / `P11-FEAT-GATEWAY-TOOLS` migration | Package and OSV must work without a search credential; usage envelopes reconcile separately. |
| Test Strategy v1.5 §7 | OptimusGatewaySettings Unit Tests | Strict-loopback URL validation with no hosted, production-mode, extra-origin, or tenant-profile bypass | `P11-FEAT-GATEWAY-CORE` | The target source removes `production_mode`; current compatibility configuration is retired only with the separately reviewed strict-loopback code change. |
| Test Strategy v1.5 §7.1 | Integration, E2E, and egress gates | Real loopback policy tests, aggregator evidence, process-specific egress/credential scans, WSL2 topology, and failure behavior | Cross-cutting: Gateway feature slices | Retired direct-provider, Tavily, and LangSmith keys are absent after migration acceptance. |
| Test Strategy v1.5 §7A | Deterministic Search Compatibility Gate | Live minimal-call annotations, domain enforcement, citation quality, provider cost/latency, direct extract, and successor criteria | `P11-FEAT-GATEWAY-TOOLS` | Baseline evidence is measured, not a permanent performance threshold; every run reports fresh values. |
| Test Strategy v1.5 §8 | Cost Accounting Tests | Usage, ledger, and reconciliation tests | Cross-cutting | Carried body, governed by current provider-reported USD authority in LLD §§9E-10A. |
| Test Strategy v1.5 §8A | Observability Test Strategy | Coverage separation plus real OTel/OTLP-to-Phoenix span evidence | `P11-FEAT-GATEWAY-COST-OBS` / coverage cross-cutting | Phoenix is the documented default, not an API dependency; no separate credential or amortized charge exists. |
| Test Strategy v1.5 §9 | Error, Retry, and Failure Injection Tests | Transient/permanent retry behavior, bounded attempts, escalation, and failure-side-effect checks | Cross-cutting: Gateway feature slices | Restored co-located retry/failure contract; `RetryPolicy` remains the named test seam. |
| Test Strategy v1.5 §10 | Schema Validation Tests | ACP framing, JSON-RPC, and Pydantic boundary validation for malformed inputs and usage/settings models | Cross-cutting: Gateway feature slices | Restored co-located schema contract; validation rejects malformed inputs before a Gateway call. |
| Test Strategy v1.5 §11 | Security and Trust Boundary Tests | Strict-loopback parsing, credential scans, extract SSRF controls, untrusted output, cost validation, and redaction | Cross-cutting | Golden task evidence uses the real local Gateway and independent `acpx` at protocol tier. |
| Test Strategy v1.5 §12 | Golden Task Regression Suite | Real-Gateway tasks with mode, tool, cost, mutation, request identity, trace identity, and final disposition | Implemented by Plan 8.5 / Gateway feature evidence | OTel/OTLP-to-Phoenix replaces backend-specific trace assertions. |
| Test Strategy v1.5 §13 | Phase 1 Release Gates | Transport, protocol, credentials, egress, search, independent tools, extract, accounting, and Phoenix go/no-go evidence | Cross-cutting | Release sign-off remains governed by the authoritative Plan 9.6 live-verification gate. |
| Test Strategy v1.5 §14 | Guardrail & Workflow Test Cases | Executable companion cases for Guardrails v1.1 | Cross-cutting | Carried body; subsections below remain separately traceable. |
| Test Strategy v1.5 §14.1 | Permission policy tests - deny precedence over allow; mode short-circuit; impact-class HOLD; classifier cannot overturn a deny | Permission decision behavior | Implemented by Plan 5 |  |
| Test Strategy v1.5 §14.2 | Shell validator tests - destructive, pipe-to-shell, environment/credential access, ANSI, insecure-transport, and egress patterns all BLOCK before any subprocess is spawned | Shell safety behavior | Implemented by Plan 5 |  |
| Test Strategy v1.5 §14.3 | Unicode / homoglyph tests - Cyrillic-vs-Latin confusables in hostnames and paths | Confusable detection | Implemented by Plan 5 |  |
| Test Strategy v1.5 §14.4 | Prompt-injection fixture tests - poisoned agent config and poisoned MCP tool metadata | Config/MCP poisoning | Implemented by Plan 6.5 | Local MCP trust evidence does not imply a Gateway endpoint. |
| Test Strategy v1.5 §14.5 | MCP autoload denial tests - a server bundled in a cloned repo does not auto-load; manifest-hash change forces re-approval; allowed_tools are enforced | MCP trust | Implemented by Plan 6.5 |  |
| Test Strategy v1.5 §14.6 | Pre-commit / CI parity tests - same rule set fails identically locally and in a clean CI checkout | CI parity | Implemented by Plan 8.5 |  |
| Test Strategy v1.5 §14.7 | Bypass tests - `--no-verify`, force-push to main, unsafe `.env` reads, and unsafe network commands are blocked | Process bypass safety | Cross-cutting | Applies to every implementation branch and release gate. |
| Test Strategy v1.5 §14.8 | Loop control tests - loop stops on completion, max_iterations, budget exhaustion, and repeated failure | Bounded loops | Implemented by Plan 9 | Current-run Gateway budget is settled; future cross-run policy remains `P9.85-FU-3`. |
| Test Strategy v1.5 §14.9 | Skill loading & trust tests - matched-only load, draft blocking, allowed-tools enforcement, and deny-rule precedence | Skill trust | Implemented by Plan 9 |  |
| Test Strategy v1.5 §14.10 | Additions to the §4 Requirements-to-Test Traceability Matrix | Guardrail-to-test traceability additions | Cross-cutting | The rows extend §4 and do not replace per-feature evidence inventories. |

## Completeness and handoff

| Source | Page count | Map entries | Completeness check |
|---|---:|---:|---|
| HLD v2.16 | 13 | 21 | All current numbered sections, including §10.A-§10.E, §11.1, and the restored §6/§7 content, are accounted for. |
| LLD v2.39 | 40 | 40 | Carried image-backed pages were preserved; current regenerated subsections, the unnumbered endpoint block, and restored §12A-§12D contracts are included. |
| Guardrails v1.1 | 16 | 38 | Current numbered sections, carried subsections, the §0 register, and restored §7.1/§7.2/§8.1/§8.2 controls are accounted for. |
| Test Strategy v1.5 | 14 | 27 | Current numbered sections, §7.1, §7A, §8A, restored §9-10, and carried §14.1-§14.10 are accounted for. |

The map intentionally does not edit the Plan 11 charter, roadmap, frozen plans, specifications, or
approval records. The next gate is the delta-aware deep inventory refresh across the stable Gateway
feature identities, using these exact pins and preserving the explicit `P11-FU-3` and
`P9.85-FU-3` dispositions.
