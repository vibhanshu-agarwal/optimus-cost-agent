# Plan 11 v1.0 Milestone Charter

## Status and baseline

**Status:** Ratified milestone charter. The revised sub-plan map below records Plan 11 execution
lanes; the [consolidated open-work pool](2026-07-23-consolidated-deferred-followups-backlog.md) owns
live item-level status.

**Baseline:** Ratified Plan 11 feature scope and sequencing. Detailed sub-plan specifications and
implementations land through separate reviewed PRs; this charter does not replace their evidence or
the pool's current-state custody.

## Milestone objective

Plan 11 is the v1.0 milestone for the local-first Optimus agent. It retains the existing Unified
Gateway Capabilities Broker scope and expands the completion target to a fully working,
feature-complete agent except for Plan 12's context-window optimization and intelligent-selection
work. v1.0 proves the ACP path with Zed, prepares the agent for ACP registry registration, and
closes the consolidated open-work pool before sign-off.

Registry registration is expected to satisfy the multi-IDE requirement without making a specific
second IDE an unconditional v1.0 gate. JetBrains Air and JetBrains AI Assistant are legitimate
future or conditional integration candidates, but neither is required for the initial v1.0 proof.
Any outward-facing registry publication requires explicit operator approval at execution time,
separate from approval of this charter or a sub-plan.

## Scope retained from the existing Plan 11 entry

The Gateway capability partition remains the first primary slice:

- `P11-FEAT-GATEWAY-CORE` (Plan 11.1) owns the zero-upstream-credential boundary, origin/secrets, model routing,
  both model wire shapes, retries, normalized response-envelope validation, and the
  `/v1/observability/traces` route;
- `P11-FEAT-GATEWAY-TOOLS` owns web search/extract adapters, provenance/domain revalidation, and
  the typed-tool envelope; the package/advisory capability is carried by `P11-FU-2` within this slice;
- `P11-FEAT-GATEWAY-MCP` owns MCP tool-call brokering through the Gateway, including transport,
  trust-registry integration with the existing `optimus/mcp/runtime.py` guardrail layer, and the
  typed request/response contract; and
- `P11-FEAT-GATEWAY-COST-OBS` owns provider-native usage persistence and reconciliation, the
  wire-aware USD field migration, authenticated structured agent-to-Gateway trace ingress, Gateway
  validation/redaction and OTel/OTLP export with Phoenix as the local default, Plan 7 telemetry
  compatibility, and observability-field compatibility. Trace export has
  no allocated or amortized per-request charge, and LangSmith is not part of the architecture.

All Gateway capability slices preserve zero upstream credentials in the agent process: the local
runtime holds only its Gateway endpoint and API key, while vendor and upstream credentials are owned
and resolved gateway-side. `P9.85-FU-3` budget enforcement remains outside the Plan 11.1 scope
pending the operator decision recorded in the consolidated backlog.

The Gateway design must continue to respect the authoritative HLD/LLD/Guardrails boundary. The
parked `P9.85-FU-3` budget-enforcement question is not pulled into this charter's initial scope.

## Revised sub-plan map

| Feature ID | Scope | Implemented plans / intended order | v1.0 relationship |
|---|---|---|---|
| `P11-FEAT-GATEWAY-CORE` | Gateway core and `/v1/observability/traces` route | Plan 11.1 / Plan 11.4 | Closed through PR #85 and PR #91. |
| `P11-FEAT-GATEWAY-TOOLS` | Gateway web/evidence tools and real provider adapters | Plan 11.2 / Plan 11.3 | Closed through PR #88. |
| `P11-FEAT-GATEWAY-COST-OBS` | Gateway normalized cost, observability, and local startup consolidation | Plan 11.5 / Plan 11.6 | Plan 11.5 closed through PR #95; Plan 11.6 merged through PR #97. |
| `P11-FEAT-GATEWAY-MCP` | Gateway MCP tools-only brokering through static profiles over remote HTTP and Docker-contained stdio, with trust-registry integration and typed request/response contract | Plan 11.8 / Plan 11.11 (historical); Plan 11.12 retirement; Plan 11.13 PDF reversal | Retired by Plan 11.12. Plan 11.13 must reverse the authoritative PDFs/source tree before `P11-FEAT-REGISTRY` or the v1.0 cut. |
| `P11-FEAT-ZED-RESUME` | Zed integration fixes, ACP session resume, and the configurable Gateway-timeout follow-up | Plan 11.7 / Plan 11.9 | Plan 11.7 is partially implemented and blocked; Plan 11.9 closed `P11.7-FU-1` through PR #123 and PR #124. |
| `P11-FEAT-REGISTRY` | ACP registry validation, registration, and v1.0 cut | Last primary Plan 11 slice (holding position) | Required release slice; Plan 11.13 must land first. Reassess 11.x-last versus a split outward-publication lane in 13.x after the consolidated open-work pool closes. |
| `P11-FEAT-IDE` | IDE-specific testing if registry registration does not surface or satisfy multi-IDE expectations | Conditional | Conditional; not an unconditional v1.0 gate. |

This map is the charter's current execution snapshot. The detailed feature sections below retain
ratification-time design requirements; where they describe pre-pickup authorization or numbering,
the map records the landed lane and the consolidated pool owns live work status.

The feature IDs are permanent, greppable slice identities. They use the `P11-FEAT-*` prefix;
`FEAT` identifies milestone features and is distinct from `FU`, which identifies follow-ups. Slugs
carry no implied ordering. Each feature gets its own design/specification and review checkpoint
before implementation.

## Plan 11 feature-ID and plan-number allocation

Plan numbers are scheduling labels only, never priority or scope identity. New independently
schedulable work takes the next linear plan number without a decimal-depth limit: `11.9` -> `11.10`
-> `11.11`. A revision keeps the same plan number and increments `_vN`. Interstitial allocations
such as the historical `9.8` -> `9.85` -> `9.975` sequence are forbidden going forward. Nested
`N.M.1` plan numbers are also forbidden.

Feature IDs (`P11-FEAT-*`) and source IDs (`P9.8-FU-5`, `P11-FU-1`, and other stable backlog IDs)
are the durable identifiers; plan numbers are not. Promotion is recorded as `Promoted -> Plan 11.N`
with the date and plan-file link, matching the consolidated backlog's existing promotion rule.

## P11-FEAT-GATEWAY-CORE - Gateway Core and Observability Route

`P11-FEAT-GATEWAY-CORE` is Plan 11.1. Its scope is the Gateway core plus the
`/v1/observability/traces` route. Its design must resolve the zero-upstream-credential/origin boundary, the
`/v1/responses` and served `/v1/chat/completions` route contracts, upstream/provider adapter boundary,
gateway-side secret resolution, failure and retry behavior, normalized response-envelope validation,
and the Gateway-to-observability ingress contract. It must not move vendor keys into the agent runtime
or silently create a second local provider path.

The `P11-FEAT-GATEWAY-CORE` specification must identify the capability-level release evidence needed
for the model routes, observability ingress, agent credential scans, provider failure behavior, response-envelope
fail-closed behavior, and the preserved ledger/trace interfaces. It must also identify any new follow-ups
in the consolidated backlog. Budget enforcement is not part of this scope; all such inventory rows
remain deferred to `P9.85-FU-3 (parked; operator decision pending)`.

## P11-FEAT-GATEWAY-TOOLS and P11-FEAT-GATEWAY-COST-OBS

`P11-FEAT-GATEWAY-TOOLS` is the ratified owner for web search/extract adapters, domain/provenance
revalidation, typed-tool envelopes, and the `P11-FU-2` package/advisory capability. It is picked up
as Plan 11.2 for the drafted design and implementation plan; implementation remains unauthorized
until the frozen artifacts receive their review approvals.

`P11-FEAT-GATEWAY-COST-OBS` is the ratified owner for provider-native usage persistence and
reconciliation, the wire-aware USD field migration,
authenticated structured agent-to-Gateway trace ingress, Gateway validation/redaction and
OTel/OTLP export with Phoenix as the local default, Plan 7 telemetry compatibility, and
observability-field compatibility. Trace export has
no allocated or amortized per-request charge, and LangSmith is not part of the architecture. Its
Plan 11.x number is assigned at pickup. Neither identity expands Plan 11.1's implementation scope.

## P11-FEAT-GATEWAY-MCP - Gateway MCP tool-call brokering

Living status: retired by Plan 11.12. Plan 11.8 and Plan 11.11 are historical precursor work.
Plan 11.13 must reverse HLD v2.17, LLD v2.40, Guardrails v1.2, Test Strategy v1.6, and the
amendment source tree before `P11-FEAT-REGISTRY` or the v1.0 cut. The ratification-time design
requirements below are retained as historical charter text.

`P11-FEAT-GATEWAY-MCP` is the ratified owner for a bounded v1 MCP tool-call broker through the
Gateway. Its v1 scope is tools-only method/result/content handling through operator-provisioned,
static credential profiles, over the separately specified remote HTTP and Docker-contained stdio
transports. It includes integration with the existing local trust and pre-tool guardrail layer in
`src/optimus/mcp/runtime.py` and the typed Gateway request/response contract. The agent process
keeps zero upstream credentials; the Gateway owns the upstream credentials and runtime connection
state.

`P11-FU-3` records the route/typed-contract design gate. That gate may be marked satisfied only
after this charter amendment and all four amended HLD, LLD, Guardrails, and Test Strategy PDFs are
approved and published. Until then, no MCP implementation plan, route, payload, or response envelope
may be promoted from this charter or its source fragments. At pickup, independently schedulable work
takes the next linear plan number under the charter rule used for TOOLS, COST-OBS, and ZED-RESUME.

Context7 is a named remote-compatibility acceptance dependency of this feature, not a sixth
follow-up. Before Context7 support may be claimed, a Gateway-originated, authenticated
discovery/version/tools probe of the configured endpoint must prove the `2026-07-28` protocol floor
against the real service; a fake or a different HTTP server cannot discharge that dependency.

Gateway-brokered MCP remains distinct from `P11-FU-9` client-supplied ACP `mcpServers`, which would
ask the agent to connect to client-nominated servers, and from `P11-FEAT-ZED-RESUME` ACP session
custody. MCP catalog/discover-and-connect remains deferred under `P11-FU-14`; it is not ACP
publication identity or registry work owned by `P11-FEAT-REGISTRY`.

## P11-FEAT-ZED-RESUME - Zed integration fixes and session resume

`P11-FEAT-ZED-RESUME` owns two ACP-facing items:

- `P9.8-FU-5`, the Zed refusal-rendering panic and its agent-payload versus externally owned client
  disposition; and
- `P11-FU-1`, the session-resume capability gap described below.

The Zed v1.0 proof must preserve ACP conformance and the existing fail-closed refusal behavior. An
agent-side workaround for the client panic requires its own reviewed design decision and must not
weaken refusal semantics.

### Session-resume design contract

The current implementation advertises an empty `sessionCapabilities` object and dispatches no
`session/load`; a resume request therefore returns `METHOD_NOT_FOUND`, and the client correctly
starts a new session. The `P11-FEAT-ZED-RESUME` specification must cover, as one design problem:

1. implementing the ACP `session/load` request path;
2. advertising the ACP `loadSession` capability only when its persistence and replay semantics are
   actually supported;
3. defining what session identity, workspace binding, conversation history, prompt state, and
   relevant run metadata persist across process/client boundaries;
4. selecting and documenting the durable storage mechanism, TTL/expiry, deletion behavior,
   migration/versioning, failure mode, and operator data-retention policy; and
5. restoring the session in the ACP-required shape, including replaying the prior conversation or
   otherwise meeting the protocol's load semantics, without silently substituting `session/new`.

`InMemoryAcpSpecSessionStore` is process-local and cannot establish cross-process resume. The
existing `RedisAgentStateStore` persists expiring `AgentPlanRecord` values, not ACP conversation or
session state, so it is not an implementation-ready answer. The `P11-FEAT-ZED-RESUME` design must compare and select
an explicit session-state storage strategy, including security and workspace isolation, rather than
assuming that the plan store is sufficient. If durable state is unavailable or corrupt, behavior
must be fail-closed and operator-visible; it must not advertise resume and then lose history.

The `P11-FEAT-ZED-RESUME` evidence plan must include protocol-level tests for capability negotiation, successful
load, unknown/expired sessions, workspace mismatch, malformed state, storage unavailability, and
history replay. ACP live evidence must use an independently authored ACP client, with Zed evidence
for the v1.0 gate.

## P11-FEAT-REGISTRY - ACP registry registration and v1.0 cut

The ACP registry is a public, stabilized process with a maintained
[registry repository](https://github.com/agentclientprotocol/registry),
[submission guide](https://github.com/agentclientprotocol/registry/blob/main/CONTRIBUTING.md), and
[published schema and format](https://github.com/agentclientprotocol/registry/blob/main/FORMAT.md).
`P11-FEAT-REGISTRY` therefore begins with a source-revalidation and scope gate against the live
process, not research for an unknown authoritative source. At pickup, pin the exact upstream
revision and verify the applicable validator and CI behavior by execution before freezing scope;
published prose is a requirements input, not proof of enforcement. The research record must identify
package metadata, naming/identity, protocol and version declarations, validation, discoverability,
release artifacts, ownership, and rollback or withdrawal expectations that actually apply.

The current Optimus side of a likely authentication collision is verified: `pyproject.toml` and
`src/optimus/acp/spec.py` both declare version `0.1.0`, while the ACP `initialize` response declares
`authMethods: []`. The registry's current
[authentication guidance](https://github.com/agentclientprotocol/registry/blob/main/AUTHENTICATION.md)
and submission guide describe admission as requiring at least one Agent Auth or Terminal Auth
method. That registry-side behavior remains an external claim to reproduce through the live
registry validator/auth check at pickup, not a settled implementation requirement in this charter.
The eventual design must resolve any confirmed collision without weakening the one-key Gateway
boundary or inventing unsupported authentication behavior.

`P11-FEAT-REGISTRY` also owns the v1.0 release inventory: a named list of every capability excluded
from the cut, with its rationale, custody, and next-phase or conditional destination. That inventory
is the authoritative answer to the DoD's "feature-complete except Plan 12" boundary and must be
reviewed before sign-off.

The v1.0 cut must update both known version locations together:

- `pyproject.toml`'s package version (`version = "0.1.0"` today); and
- `src/optimus/acp/spec.py`'s hardcoded `agentInfo.version` (`"0.1.0"` today).

The `P11-FEAT-REGISTRY` sub-plan must establish one release-version contract so these values cannot drift again, and
must add a check that fails when the package and ACP-reported versions disagree. Actual outward
registry registration/publication is an operator-controlled action and requires explicit approval
at the time the researched procedure is executed.

The release-version contract and excluded-capability inventory are part of the v1.0 cut and remain
inside Plan 11. Outward registration/publication is separable discoverability work. Once the
consolidated open-work pool closes, the operator and reviewer must record a placement decision:
retain outward publication in this last primary Plan 11 slice, or split only that publication action
into a 13.x train while keeping the v1.0 contract and inventory in Plan 11. Moving the whole slice to
13.x would require a separate v1.0 boundary amendment; this charter does not make that move.

## P11-FEAT-IDE - Conditional IDE-specific testing

`P11-FEAT-IDE` is opened only if the `P11-FEAT-REGISTRY` research or registration process surfaces an unmet
multi-IDE requirement. It may cover JetBrains Air, JetBrains AI Assistant inside IntelliJ-family
products, or another operator-named client. It is not a standing v1.0 dependency: Zed is the v1.0
IDE proof, and registry registration is expected to satisfy the broader distribution expectation.

If `P11-FEAT-IDE` is opened, its scope and completion gate must be written as an explicit amendment rather
than inferred from the existence of a second IDE candidate.

## Backlog and completion gates

The [consolidated open-work pool](2026-07-23-consolidated-deferred-followups-backlog.md) is the
single source of truth for the carried `P9.8-FU-5` and `P9.87-FU-1` items, `P11-FU-4` evidence-
freshness work, and follow-ups discovered during Plan 11 feature work. `P11-FU-1` is owned by
`P11-FEAT-ZED-RESUME`, not parked. `P11-FU-2` is owned by
`P11-FEAT-GATEWAY-TOOLS` as an unimplemented package/advisory capability. `P11-FU-3` owns the
conditional route/typed-contract publication gate for `P11-FEAT-GATEWAY-MCP`; it closes only after
this charter amendment and all four amended PDFs are approved and published. The five distinct MCP
deferred-work entries are `P11-FU-12` OAuth lifecycle, `P11-FU-13` deferred capabilities and
long-lived interaction, `P11-FU-14` registry discover-and-connect, `P11-FU-15` tool-search/context
minimization, and `P11-FU-16` reverse research-to-documentation freshness. The
`P11-FEAT-ZED-RESUME` Zed live-evidence work should coordinate with the re-pin, but the freshness
item still needs explicit fresh-evidence closure or a reviewed disposition. The budget-enforcement
item `P9.85-FU-3` remains parked and undecided outside Plan 11.1's initial scope; revisit it only if
Gateway work organically reaches budget or cost policy.

Primary `P11-FEAT-GATEWAY-CORE` and `P11-FEAT-ZED-RESUME` work is sequenced first.
`P11-FEAT-REGISTRY` is the last primary Plan 11 slice as a holding position. Its final placement is
reassessed after the consolidated open-work pool closes under the split rule above. Before v1.0
sign-off, every item in that pool must be closed with evidence or an explicit reviewed disposition;
v1.0 does not ship with an open consolidated open-work pool. Conditional `P11-FEAT-IDE` is handled
according to its explicit amendment and does not become a v1.0 gate merely because an IDE candidate
exists.

The v1.0 Definition of Done is therefore:

- Gateway capability work is complete with zero upstream credentials in the agent process, with Plan 11.1 closing the
  CORE plus observability-route gate and the ratified TOOLS/COST-OBS slices accounted for separately;
- the agent is feature-complete against the Phase 1 charter except for Plan 12's context/intelligence
  work, with every excluded capability named rather than implied;
- Zed ACP evidence proves the supported v1.0 interaction, including the `P11-FEAT-ZED-RESUME` session-resume and
  refusal-rendering dispositions;
- registry requirements are researched, the two version declarations are aligned, and the
  registration/release artifact and `P11-FEAT-REGISTRY` excluded-capability inventory are ready for explicit
  operator-approved execution; and
- the consolidated open-work pool is closed or has a reviewed, recorded disposition before the
  v1.0 cut.

## Explicit exclusions and unresolved inputs

- Plan 12's context-window optimization and intelligent selection remain post-v1.0 v1.x work.
- `P9.85-FU-3` remains outside the initial Plan 11 scope pending the Gateway budget authority
  decision.
- MCP Gateway brokering remains outside the CORE and TOOLS scopes. `P11-FEAT-GATEWAY-MCP` is
  retired by Plan 11.12. Plan 11.13 must reverse the authoritative PDFs/source tree before
  `P11-FEAT-REGISTRY` or the v1.0 cut; neither catalog automation nor client-supplied ACP
  `mcpServers` is part of that retired Gateway feature.
- The **Windows Subprocess Handle-Duplication Flake, WinError 6/50** remains explicitly excluded
  from the initial Plan 11 feature scope and v1.0 gate. The `P11-FU-5` entry in the consolidated open-work
  pool owns its future Windows investigation state; the no-reproduction result, lack of a
  deterministic fix, and lack of a v1.0 capability/ACP-evidence dependency are the rationale. The
  separately identified durable-approval identity concern remains in that entry until a separate
  reviewed custody decision is made.
- JetBrains Air and JetBrains AI Assistant are conditional/post-v1.0 candidates, not unconditional
  v1.0 gates.
- ACP registry requirements have a public authoritative source, but their exact live enforcement
  remains a pickup-time validation input; this charter does not authorize external publication.
