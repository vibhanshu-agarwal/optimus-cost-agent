# Plan 11 Authoritative-Document Section Map

**Status:** Pre-11 feature-specification gate; section-level map only.

**Baseline:** `origin/main` at `5229036`.

**Purpose:** Establish a complete, version-pinned section map of the four authoritative Phase 1
documents before any Plan 11 feature specification freezes. This is a shallow map, not the
requirement-level inventory. The deep extraction is performed per feature ID at specification
time.

The map applies the existing deferred-work custody rule to requirements: every section has an
owner or is explicitly marked `UNOWNED` or `Cross-cutting`. A normative statement discovered
later in a mapped section is an extraction defect, not an invitation to silently widen a frozen
specification.

## Source set and digests

The version pin uses the filename and rendered cover page. SHA-256 is over the exact source bytes.

| Source document | Version pin | Pages | SHA-256 |
|---|---:|---:|---|
| `Optimus-Cost-Agent-Architecture-v2.15.pdf` (HLD) | v2.15 | 13 | `A386EEE8463A169A20A18B59BA923CFA80C0F6707DF7FEA3DB91B83FE3386C0B` |
| `Optimus-Cost-Agent-LLD-v2.38.pdf` | v2.38 | 40 | `0471DCAE8100F41340AD6F3FE30F19B7CA8042C2949A534973B2A8D9564944DB` |
| `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.0.pdf` | v1.0 | 16 | `4669940B34C8C0CAAB5501C193213C3087C45FAE0CBA3011E1DBF87EB74B4D0C` |
| `Optimus-Cost-Agent-Test-Strategy-v1.4.pdf` | v1.4 | 14 | `6F7EB2B48447F1CE3D882FC60E16DA8B41C1DD7C926C359F45185823492DA5DB` |

The PDF metadata title fields for the HLD, LLD, and Test Strategy lag their filename and rendered
cover versions by one revision. The digest, filename, and cover-page version together are the
stable pin for this map; a future refresh must recompute all three checks.

## Diagram and render-survey scope

The targeted render-defect survey covered the four HLD figures, Guardrails v1.0 Figure 1, and the
rendered-only/diagram-heavy LLD pages. The four HLD figures and Guardrails Figure 1 rendered
cleanly. The LLD v2.38 §0.B component-flow code block remains recorded as a source-document defect
because it is clipped at the page boundary around `/v1/tools/web/extract`. This survey does not
claim full diagram-fidelity certification for every Test Strategy figure or page; those require a
separate visual review if their diagrams become normative inputs to a feature specification.

## Ownership findings requiring follow-up

These are the rows that matter most. They are intentionally surfaced before the full bookkeeping
tables.

| Finding | Evidence | Current disposition |
|---|---|---|
| Two Gateway tool endpoints have no agent caller | LLD v2.38 §0.D lists `/v1/tools/package/lookup` and `/v1/tools/security/advisory`; repository callers cover only `/v1/tools/web/search` and `/v1/tools/web/extract`. | `UNOWNED`. The P11 Gateway specification must explicitly include, defer to a stable ID, or exclude each endpoint with a reason. |
| A second model endpoint shape is specified but not agent-facing | LLD v2.38 §0.D specifies `/v1/responses` with `input` and `/v1/chat/completions` with `messages`, plus a do-not-mix validator rule. The agent calls `/v1/responses`; `/chat/completions` is only the Gateway upstream adapter path. | `UNOWNED` until the Gateway feature specification records the support or exclusion decision. |
| The agent calls an endpoint absent from the API-shape list | `src/optimus/telemetry/observability.py:20` posts to `/v1/observability/traces`, while LLD v2.38 §0.D lists no observability endpoint. | `Cross-cutting` document gap. P11 Gateway must add the endpoint contract to its requirement inventory or record a reviewed source-document defect and disposition. |
| MCP brokering has responsibility but no endpoint shape | LLD v2.38 §0.C names MCP tool brokering among Gateway responsibilities; §0.D provides no corresponding endpoint. | `UNOWNED`. The missing boundary needs a stable requirement disposition before a Gateway spec freezes. |
| LangSmith seat/subscription cost is amortized | HLD v2.15 §11A and LLD v2.38 §0A describe allocated or amortized observability cost rather than per-call cost. | `P11-FEAT-GATEWAY`. Deep extraction must preserve this accounting model and identify its authoritative ledger contract. |
| The LLD component-flow diagram is clipped | Rendered LLD v2.38 page 2 (§0.B) cuts the code block off at the page boundary around `/v1/tools/web/extract`. | `UNOWNED` source-document defect; do not treat the truncated diagram as a complete requirement. |
| ACP registry publication has no source section | None of the four pinned documents contains a normative ACP registry registration/publication section. | `UNOWNED` under `P11-FEAT-REGISTRY` until its research gate supplies the missing authoritative source and requirements. |
| Multi-IDE ACP expectations are not normatively specified | HLD v2.15 §6 names an IntelliJ IDEA client; Test Strategy v1.4 §2 excludes IDE plugin UI testing to a separate frontend plan. Neither defines the conditional multi-IDE ACP gate. | `P11-FEAT-IDE` if opened by charter amendment; otherwise `UNOWNED`, not an implied v1.0 requirement. |

## Owner vocabulary and extraction rule

- `P11-FEAT-GATEWAY`, `P11-FEAT-ZED-RESUME`, `P11-FEAT-REGISTRY`, and `P11-FEAT-IDE` are the
  permanent Plan 11 feature identities. Plan 11.x numbers are assigned only when a feature is
  picked up.
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
| `LLD v2.38 §0.D` | Exact statement from the source | `In scope`, `Deferred -> <stable ID>`, or `Excluded -> <reason>` | Stable owner | Named executable or release artifact |

No requirement-level rows are created in this section map.

## HLD v2.15 section map

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| HLD v2.15 §1 | Executive Summary | Phase 1 architecture thesis and deterministic harness boundary | Cross-cutting | Charter context for every feature; not a standalone implementation lane. |
| HLD v2.15 §2 | Harness Engineering & Context Optimization | Feedforward context shaping and feedback validation | Plan 12 | Existing Plans 4, 5, 6, 6.5, and 9 supply inputs; intelligent selection and optimization remain Plan 12 work. |
| HLD v2.15 §3 | Automated Architectural Fitness Functions | Scope, automation, invocation, return, and activation gates | Implemented by Plans 8 and 8.5 | Later feature inventories must still cite the gates they rely on. |
| HLD v2.15 §4 | Data Governance Plane & Local Storage Boundaries | Redis structural memory, TimeSeries telemetry, and retention | Implemented by Plan 7 | Storage and retention are evidence dependencies for Gateway and release work. |
| HLD v2.15 §5 | Request-Level Cost Attribution | Provider usage, pricing snapshots, and request-level cost records | Implemented by Plan 7 | P11 Gateway must trace the server-side normalized-cost contract that consumes this ledger. |
| HLD v2.15 §5A | Provider-Cost Normalization & Single-Key Wallet | Gateway-owned credentials, wallet mapping, budget authority, and normalized provider cost | P11-FEAT-GATEWAY | This is the primary Gateway requirements source and includes the amortized observability model in §11A. |
| HLD v2.15 §6 | Deterministic Data-Flow Architecture (Phase 1 MVP) | IDE/ACP ingress through context, Gateway, validation, storage, and FinOps output | Cross-cutting | Existing Plans 1-9 cover most runtime stages; P11 Gateway and conditional IDE work extend the external boundary. |
| HLD v2.15 §7 | Agent Operating Modes & Trust Framework | Plan/Chat, Agent mode, and generation-scope classification | Implemented by Plan 2 | Guardrail sections refine this boundary. |
| HLD v2.15 §8 | Tool Governance & Evidence Acquisition | Evidence-first policy, typed tools, and external-call authorization | Implemented by Plan 4 | P11 Gateway must preserve the Gateway-side policy boundary. |
| HLD v2.15 §9 | Adaptive Agent Execution Strategy & Rigor Policy | Rigor tiers, strategy selection, and bounded reflection | Implemented by Plan 9 | Plan 12 may optimize selection but does not replace this Phase 1 contract. |
| HLD v2.15 §10 | Architectural Control Flow | End-to-end control flow, the A-C architecture diagrams, and the D-E normative control tables | Cross-cutting | A-C are diagrams; D enumerates four cost-control points and E enumerates five hallucination-control layers. All are covered by this row and are not additional numbered sections. |
| HLD v2.15 §11 | Optimus AI Gateway - Phase 1 Mandatory | Mandatory Gateway boundary, routing, policy, and provider isolation | P11-FEAT-GATEWAY | Gateway route, failure, usage, cost, and observability requirements must be extracted here. |
| HLD v2.15 §11A | Trace Observability | Gateway-managed trace export and observability cost allocation | P11-FEAT-GATEWAY | Cross-reference with LLD §0A, §10A, and Test Strategy §8A. |
| HLD v2.15 §12 | Testing & Quality Gates | Release validation and quality-gate contract | Cross-cutting | HLD defers coverage authority to Test Strategy §8A. |
| HLD v2.15 §13 | Agent Execution Safety & Guardrails | Safety, approval, and bounded execution policy anchor | Cross-cutting | Detailed policy is in Guardrails v1.0; implementation custody is distributed across Plans 5, 6, 6.5, 8.5, and 9. |

## LLD v2.38 section map

The LLD has rendered-only pages whose text layer is empty. The section sequence below was checked
against page renders, not only text extraction. The unnumbered endpoint block on page 5 is retained
as a separate row because it carries normative endpoint and LangSmith wiring content.

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| LLD v2.38 §0 | Optimus AI Gateway Architecture | Gateway-mandatory architecture, single credential, and component boundary | P11-FEAT-GATEWAY | Contains the source surface for the Gateway broker charter. |
| LLD v2.38 §0.A | Recommended Architecture | Local agent boundary and Gateway-resolved policy, routes, budgets, and secrets | P11-FEAT-GATEWAY | Local control-plane versus Gateway authority must be explicit in the deep inventory. |
| LLD v2.38 §0.B | Gateway Component Flow | IDE/agent request path through auth, routing, ledger, vault, and provider | UNOWNED | Rendered page 2 is clipped at the bottom around `/v1/tools/web/extract`; source repair or an authoritative replacement is required. |
| LLD v2.38 §0.C | Gateway Responsibilities | Authentication, model routing, tool brokering, billing, policy, and secret isolation | UNOWNED | MCP brokering is named here but has no corresponding endpoint shape in §0.D. |
| LLD v2.38 §0.D | Gateway-Facing API Shape | Responses and Chat Completions wire shapes plus four typed tool endpoints | UNOWNED | Package/security endpoints have no agent caller; the second model shape is not agent-facing; both need explicit dispositions. |
| LLD v2.38 §0.E | Developer-Facing vs. Server-Side Configuration Boundary | Local OPTIMUS configuration versus server-side provider secrets | Implemented by Plan 3 | P11 Gateway must preserve the one-key boundary. |
| LLD v2.38 §0A | Local vs. Gateway Configuration & Provider-Cost Mapping | Runtime keys, wallet mapping, provider-native units, and amortized LangSmith cost | P11-FEAT-GATEWAY | This is the primary source for the normalized cost and observability contract. |
| LLD v2.38 §0A (named block) | Gateway Tool & Observability Endpoints | Agent-facing Gateway adapters, model endpoints, typed tools, and `/v1/observability/traces` | P11-FEAT-GATEWAY | The block specifies `/v1/observability/traces`, but §0.D does not list it; record the source inconsistency. |
| LLD v2.38 §1 | ACP Protocol Framing & JSON-RPC Contract Specification | Content-Length framing, size limits, and JSON-RPC errors | Implemented by Plan 1 | Zed/session-resume work depends on this protocol boundary but does not replace its transport ownership. |
| LLD v2.38 §2 | Cross-Platform Stream Transport Layer | Stdio framing and async stream transport | Implemented by Plan 1 | Re-verify against the real ACP client at the relevant feature gate. |
| LLD v2.38 §3 | Queued Task Lifecycle, Backpressure Controls & Runtime Pooling | Task concurrency, pooling, cancellation, and duplicate IDs | Implemented by Plan 1 | Shared runtime dependency for every feature. |
| LLD v2.38 §4 | Behavioral Governance: Operating Modes, Strategies & Scope Classifier | Modes, generation scope, rigor, tool operation, and error contracts | Cross-cutting | Plan 2 owns the mode boundary; Plan 9 owns execution strategy; inventories must name the applicable slice. |
| LLD v2.38 §4A | Agent State Model and Execution Pathways | Lifecycle states, valid transitions, permission matrix, and execution pathway | Cross-cutting | Existing Plans 2 and 9.5 own the baseline; ACP client/session work must cite only the affected protocol behavior. |
| LLD v2.38 §5 | ADL Parser Continuity & Architectural Evolution | ADL parser strategy and structural validation | Implemented by Plan 8 | Fitness-gate consumers must trace their parser assumptions. |
| LLD v2.38 §6 | Resilient Provider Calling Layer & Tenacity Rules | Gateway model routing, distinct response shapes, retries, and normalized response | P11-FEAT-GATEWAY | The two model endpoint shapes and do-not-mix rule require an explicit Gateway disposition. |
| LLD v2.38 §7 | Composite Fitness Engine Scaffolding | Dependency, metric, test-architecture, and composite gates | Implemented by Plan 8 | P11 features consume these gates; they do not redefine them. |
| LLD v2.38 §8 | Patch Workspace Lifecycle Boundaries | Shadow workspace, mode enforcement, atomic apply, and rollback | Implemented by Plan 8 | Cross-reference HLD §7 and Guardrails §2-§6. |
| LLD v2.38 §9 | Tool Registry, Invocation Policy & Evidence Ledger | Typed tool registry, policy matrix, and evidence recording | Cross-cutting | Plan 4 owns evidence/tool policy; Plan 7 owns cost reconciliation. |
| LLD v2.38 §9A | Tool Class Enum & Registry Contract | Tool classes, reasons, registry entries, and call authorization | Implemented by Plan 4 | Plan 5 adds the pre-tool enforcement boundary. |
| LLD v2.38 §9B | Deterministic Invocation Policy Matrix | Signal-to-tool-class routing and evidence requirements | Implemented by Plan 4 | Cross-reference Guardrails §2-§4. |
| LLD v2.38 §9C | Typed Evidence Acquisition Wrappers | Gateway-backed search/extract wrappers and provenance bounds | Implemented by Plan 4 | The live agent caller surface is web search and web extract only. |
| LLD v2.38 §9D | Gateway Server-Side Policy Revalidation | Domain, provenance, budgets, call caps, tool policy, and fail-closed Gateway checks | P11-FEAT-GATEWAY | This is the authoritative Gateway enforcement surface; local checks are convenience/defense in depth. |
| LLD v2.38 §9E | Evidence Ledger Schema | Evidence/audit entries and gateway usage reconciliation | Cross-cutting | Plan 7 owns cost reconciliation; every P11 external-call requirement must cite the ledger join. |
| LLD v2.38 §10 | Usage Accounting Service & TimeSeries Policy Enforcement | Pricing fallback, RedisTimeSeries retention, and telemetry persistence | Implemented by Plan 7 | Gateway-side normalized cost must remain compatible with this persisted evidence. |
| LLD v2.38 §10A | Provider Usage Ledger Schema & Observability Export | ProviderUsage superset, normalized charges, and trace export | Cross-cutting | Plan 7 owns the current ledger; P11 Gateway owns the server-side normalization/amortization contract. |
| LLD v2.38 §11 | Sprint 1 Implementation Checklist | Subsystem checks and one-key release gate | Cross-cutting | Checklist ownership follows the underlying sections; it is not a substitute for feature inventories. |
| LLD v2.38 §11A | Test Coverage & Observability - Cross-Reference | Coverage threshold and evaluation/trace boundary | Cross-cutting | Test Strategy §8A is authoritative. |
| LLD v2.38 §12 | Guardrail & Workflow Component Contracts | Phase 1 guardrail and workflow component shapes | Cross-cutting | Detailed policy is in Guardrails v1.0; model-touching components must stay on the Gateway path. |
| LLD v2.38 §12A | Permission & Pre-Tool Enforcement | Permission decision, pre-tool guard, command validator, and audit event | Implemented by Plan 5 | Cross-reference Guardrails §2-§4. |
| LLD v2.38 §12B | Prompt-Injection & MCP Supply-Chain Trust | MCP trust registry and config poisoning defenses | Implemented by Plan 6.5 | Cross-reference Guardrails §5. |
| LLD v2.38 §12C | Bounded Agent Loops | Goal loop, budgets, persistent state, and Gateway-routed evaluator | Implemented by Plan 9 | Budget authority remains a Gateway-facing cross-cutting requirement. |
| LLD v2.38 §12D | Curated Workflow Skills | Skill registry, trust policy, and allowed-tool enforcement | Implemented by Plan 9 | Cross-reference Guardrails §8. |

## Guardrails and Workflow Strategy v1.0 section map

The cross-reference register is recorded as a named row because it assigns authority among the four
documents. Subsections are retained individually so a later requirement inventory can cite the exact
policy surface rather than only the parent section.

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| Guardrails v1.0 §0 | Purpose & Document Scope | Canonical guardrail/workflow policy boundary | Cross-cutting | References HLD §7-§9, LLD §4A/§10A, and Test Strategy §8A/§14. |
| Guardrails v1.0 §0 (register) | Cross-Reference Register | Authority and relationship of HLD, LLD, Test Strategy, and this document | Cross-cutting | The register is part of §0 on page 2. |
| Guardrails v1.0 §1 | Control-Plane Overview | Layered permission, pre-tool, sandbox, audit, and CI control flow | Cross-cutting | Shared by Plans 5, 6, 6.5, 8.5, and 9. |
| Guardrails v1.0 §2 | Permission Model | Allow/deny policy, mode overlay, and human approval | Implemented by Plan 5 |  |
| Guardrails v1.0 §2.1 | Project-Level Allow Rules | Project-scoped allow policy | Implemented by Plan 5 |  |
| Guardrails v1.0 §2.2 | User-Level Deny Rules | User deny precedence and immutable safety floor | Implemented by Plan 5 |  |
| Guardrails v1.0 §2.3 | Mode Mapping | Plan/Chat versus Agent mode mapping | Implemented by Plan 5 | Cross-reference LLD §4 and §12A. |
| Guardrails v1.0 §2.4 | Human Approval | HOLD and explicit approval path | Implemented by Plan 5 |  |
| Guardrails v1.0 §2.5 | Decision Order | Deterministic deny, allow, impact, and classifier order | Implemented by Plan 5 |  |
| Guardrails v1.0 §3 | Pre-Tool Guard / Hook Layer | Pre-execution deterministic validation | Implemented by Plan 5 |  |
| Guardrails v1.0 §3.1 | Deterministic First | Deterministic checks before classifiers | Implemented by Plan 5 |  |
| Guardrails v1.0 §3.2 | Hook Surface | Tool classes and pre-tool integration point | Implemented by Plan 5 |  |
| Guardrails v1.0 §4 | Shell Command Sanitization | Shell safety and fail-closed command validation | Implemented by Plan 5 |  |
| Guardrails v1.0 §4.1 | Required Checks | Destructive, pipe-to-shell, credential, transport, and egress checks | Implemented by Plan 5 |  |
| Guardrails v1.0 §4.2 | The Homoglyph Problem | Unicode confusable detection | Implemented by Plan 5 |  |
| Guardrails v1.0 §4.3 | Implementation Posture | Tirith or equivalent validator boundary | Implemented by Plan 5 |  |
| Guardrails v1.0 §5 | Prompt-Injection & MCP Supply-Chain Defense | Config/repository poisoning and MCP trust boundary | Implemented by Plan 6.5 |  |
| Guardrails v1.0 §5.1 | Config & Repo Poisoning | Ingest scanning for untrusted configuration | Implemented by Plan 6.5 |  |
| Guardrails v1.0 §5.2 | MCP Servers Are Arbitrary Code | No implicit trust or auto-load | Implemented by Plan 6.5 |  |
| Guardrails v1.0 §5.3 | Explicit Threat Scenarios | Threat fixtures and expected denials | Implemented by Plan 6.5 |  |
| Guardrails v1.0 §6 | Pre-commit & CI Gates | Local/CI parity and clean-environment verification | Cross-cutting | Plans 6, 6.5, and 8.5 contribute distinct gates. |
| Guardrails v1.0 §6.1 | Local Pre-commit - Four-Layer Config | Local hook stack | Implemented by Plan 6.5 |  |
| Guardrails v1.0 §6.2 | CI - Clean-Environment Re-Check | CI revalidation and hygiene parity | Implemented by Plan 8.5 |  |
| Guardrails v1.0 §7 | Bounded Agent Loops / Goal-Driven Execution | Loop termination and bounded work | Implemented by Plan 9 | Gateway budget authority remains cross-cutting. |
| Guardrails v1.0 §7.1 | Phase 1 Stance | Phase 1 loop posture and constraints | Implemented by Plan 9 |  |
| Guardrails v1.0 §7.2 | Required Controls | Iteration, budget, wall-clock, and repeated-failure controls | Implemented by Plan 9 | The source assigns budget enforcement to the Gateway; trace this in P11 Gateway extraction. |
| Guardrails v1.0 §8 | Curated Workflow Skills | On-demand procedural knowledge and trust discipline | Implemented by Plan 9 |  |
| Guardrails v1.0 §8.1 | Skill Rules | Skill matching, manifest, and allowed-tool rules | Implemented by Plan 9 |  |
| Guardrails v1.0 §8.2 | Trust & Invocation | Skill trust and invocation policy | Implemented by Plan 9 |  |
| Guardrails v1.0 §9 | Cost Model Alignment | Guardrail/loop cost behavior and Gateway ledger alignment | P11-FEAT-GATEWAY | Deep extraction must include the source's amortized observability rule. |
| Guardrails v1.0 §10 | Implementation Contracts (LLD Anchor) | Component-contract relationship to LLD | Cross-cutting |  |
| Guardrails v1.0 §10.1 | Component Inventory | Guardrail/workflow component list | Cross-cutting |  |
| Guardrails v1.0 §10.2 | Representative Contract Shapes | Pydantic/API contract examples | Cross-cutting |  |
| Guardrails v1.0 §11 | Test Coverage Mapping (Test Strategy Anchor) | Test-category relationship to Test Strategy | Cross-cutting | Test Strategy §14 is the detailed companion. |
| Guardrails v1.0 §11.1 | Guardrail & Workflow Traceability | Traceability rows for safety and workflow controls | Cross-cutting |  |
| Guardrails v1.0 §11.2 | Required Test Cases | Required executable categories | Cross-cutting |  |
| Guardrails v1.0 §12 | References | Source references and authority links | Cross-cutting |  |
| Guardrails v1.0 §13 | Document Control & Cross-Reference Register | Version bumps, anchors, and document-control history | Cross-cutting | This map's digest pin is an additional staleness check, not a replacement for §13. |

## Test Strategy v1.4 section map

| Citation | Title | Surface | Owner | Note |
|---|---|---|---|---|
| Test Strategy v1.4 §1 | Test Objectives | Executable proof, one-key release gate, and regression baseline | Cross-cutting | Applies to every Plan 11 feature inventory. |
| Test Strategy v1.4 §2 | Scope and Non-Scope | Phase 1 test boundary and explicit exclusions | Cross-cutting | IDE plugin UI testing is explicitly separate; this does not define multi-IDE ACP proof. |
| Test Strategy v1.4 §3 | Test Pyramid | Unit, integration, and E2E tiers | Cross-cutting | Evidence-tier rule remains binding. |
| Test Strategy v1.4 §4 | Requirements-to-Test Traceability Matrix | LLD claim-to-test mapping | Cross-cutting | This is the closest existing requirement inventory; feature inventories must extend it. |
| Test Strategy v1.4 §5 | Mode and State Transition Tests | MutationGuard, state machine, and mode boundary tests | Implemented by Plan 2 |  |
| Test Strategy v1.4 §6 | Tool Invocation Tests | Tool policy and evidence request tests | Implemented by Plan 4 |  |
| Test Strategy v1.4 §7 | Gateway and Authentication Tests | One-key Gateway auth, routing, and provider-key isolation | P11-FEAT-GATEWAY | Existing tests cover the current path; the feature inventory must capture the authoritative Gateway surface. |
| Test Strategy v1.4 §8 | Cost Accounting Tests | Usage, ledger, and reconciliation tests | Cross-cutting | Plan 7 baseline plus P11 Gateway normalization/amortization. |
| Test Strategy v1.4 §8A | Test Coverage Target, Measurement & Trace | 80% aggregate threshold and safety-critical trend | Cross-cutting | HLD/LLD defer authority here; every feature gate needs named evidence. |
| Test Strategy v1.4 §9 | Error, Retry, and Failure Injection Tests | Transient/permanent classification and retry behavior | Implemented by Plan 8 | Gateway failure behavior must be included in the P11 Gateway inventory. |
| Test Strategy v1.4 §10 | Schema Validation Tests | Pydantic and wire-shape rejection tests | Cross-cutting | The `/v1/responses` versus `/v1/chat/completions` distinction needs a disposition. |
| Test Strategy v1.4 §11 | Security and Trust Boundary Tests | Path, secret, URL, tool-output, and trust-boundary validation | Cross-cutting | Plans 5 and 6.5 own current implementations. |
| Test Strategy v1.4 §12 | Golden Task Regression Suite | Real-gateway golden tasks and expected cost/mode/tool state | Implemented by Plan 8.5 | P11 v1.0 evidence must not substitute a fake for a named dependency tier. |
| Test Strategy v1.4 §13 | Phase 1 Release Gates | One-key release and go/no-go criteria | Cross-cutting | P11 registry/release work must map its v1.0 cut to these gates. |
| Test Strategy v1.4 §14 | Guardrail & Workflow Test Cases | Executable companion cases for Guardrails v1.0 | Cross-cutting | Subsections below are kept separately traceable. |
| Test Strategy v1.4 §14.1 | Permission policy tests - deny precedence over allow; mode short-circuit; impact-class HOLD; classifier cannot overturn a deny | Permission decision behavior | Implemented by Plan 5 |  |
| Test Strategy v1.4 §14.2 | Shell validator tests - destructive, pipe-to-shell, environment/credential access, ANSI, insecure-transport, and egress patterns all BLOCK before any subprocess is spawned | Shell safety behavior | Implemented by Plan 5 |  |
| Test Strategy v1.4 §14.3 | Unicode / homoglyph tests - Cyrillic-vs-Latin confusables in hostnames and paths | Confusable detection | Implemented by Plan 5 |  |
| Test Strategy v1.4 §14.4 | Prompt-injection fixture tests - poisoned agent config and poisoned MCP tool metadata | Config/MCP poisoning | Implemented by Plan 6.5 |  |
| Test Strategy v1.4 §14.5 | MCP autoload denial tests - a server bundled in a cloned repo does not auto-load; manifest-hash change forces re-approval; allowed_tools are enforced | MCP trust | Implemented by Plan 6.5 |  |
| Test Strategy v1.4 §14.6 | Pre-commit / CI parity tests - same rule set fails identically locally and in a clean CI checkout | CI parity | Implemented by Plan 8.5 |  |
| Test Strategy v1.4 §14.7 | Bypass tests - `--no-verify`, force-push to main, unsafe `.env` reads, and unsafe network commands are blocked | Process bypass safety | Cross-cutting | Applies to every implementation branch and release gate. |
| Test Strategy v1.4 §14.8 | Loop control tests - loop stops on completion, max_iterations, budget exhaustion, and repeated failure | Bounded loops | Implemented by Plan 9 | Gateway budget authority remains a P11 extraction dependency. |
| Test Strategy v1.4 §14.9 | Skill loading & trust tests - matched-only load, draft blocking, allowed-tools enforcement, and deny-rule precedence | Skill trust | Implemented by Plan 9 |  |
| Test Strategy v1.4 §14.10 | Additions to the §4 Requirements-to-Test Traceability Matrix | Guardrail-to-test traceability additions | Cross-cutting | The rows extend §4 and do not replace per-feature evidence inventories. |

## Completeness and handoff

| Source | Page count | Map entries | Completeness check |
|---|---:|---:|---|
| HLD v2.15 | 13 | 15 | All numbered sections and §10's A-E diagrams are accounted for. |
| LLD v2.38 | 40 | 32 | Render-only pages were visually scanned; continuation pages are folded into their containing section. The unnumbered endpoint block is included. |
| Guardrails v1.0 | 16 | 38 | All numbered sections, numbered subsections, and the §0 cross-reference register are accounted for. |
| Test Strategy v1.4 | 14 | 25 | All numbered sections, §8A, and §14.1-§14.10 are accounted for. |

The map intentionally does not edit the Plan 11 charter, roadmap, frozen plans, specifications, or
approval records. The next gate is a deep requirements inventory for `P11-FEAT-GATEWAY`, using this
map's pinned digests and resolving every `UNOWNED` row before the Gateway specification freezes.
