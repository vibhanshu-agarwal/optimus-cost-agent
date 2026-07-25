# Plan 11 v1.0 Milestone Charter

## Status and baseline

**Status:** Charter draft for review; no implementation sub-plan is authorized by this document.

**Baseline:** `origin/main` at `b5fdc655` (merged Plan 11 roadmap expansion). The living roadmap and
the [consolidated deferred follow-ups backlog](2026-07-23-consolidated-deferred-followups-backlog.md)
remain the custody records. This charter defines the v1.0 milestone and its sequencing; detailed
sub-plan specifications land in separate reviewed PRs.

## Milestone objective

Plan 11 is the v1.0 milestone for the local-first Optimus agent. It retains the existing Unified
Gateway Capabilities Broker scope and expands the completion target to a fully working,
feature-complete agent except for Plan 12's context-window optimization and intelligent-selection
work. v1.0 proves the ACP path with Zed, prepares the agent for ACP registry registration, and
closes the Plan 11 backlog before sign-off.

Registry registration is expected to satisfy the multi-IDE requirement without making a specific
second IDE an unconditional v1.0 gate. JetBrains Air and JetBrains AI Assistant are legitimate
future or conditional integration candidates, but neither is required for the initial v1.0 proof.
Any outward-facing registry publication requires explicit operator approval at execution time,
separate from approval of this charter or a sub-plan.

## Scope retained from the existing Plan 11 entry

The Gateway capability partition remains the first primary slice:

- `P11-FEAT-GATEWAY-CORE` (Plan 11.1) owns the one-key boundary, origin/secrets, model routing,
  both model wire shapes, retries, normalized response-envelope validation, and the
  `/v1/observability/traces` route;
- `P11-FEAT-GATEWAY-TOOLS` owns web search/extract adapters, provenance/domain revalidation, and
  the typed-tool envelope; package/advisory endpoints remain owned by `P11-FU-2` until pickup; and
- `P11-FEAT-GATEWAY-COST-OBS` owns provider-native usage normalization, ledger reconciliation,
  LangSmith trace export, and observability-field compatibility.

All three slices preserve the one-key local credential boundary, with vendor keys owned and resolved
gateway-side. `P9.85-FU-3` budget enforcement remains outside the Plan 11.1 scope pending the
operator decision recorded in the consolidated backlog.

The Gateway design must continue to respect the authoritative HLD/LLD/Guardrails boundary. The
parked `P9.85-FU-3` budget-enforcement question is not pulled into this charter's initial scope.

## Revised sub-plan map

| Feature ID | Scope | Intended order | v1.0 relationship |
|---|---|---|---|
| `P11-FEAT-GATEWAY-CORE` | Gateway core and `/v1/observability/traces` route | Plan 11.1 | First active feature slice; required. |
| `P11-FEAT-GATEWAY-TOOLS` | Gateway web/evidence tool capability partition | Assigned at pickup | Ratified feature identity; plan number is not reserved. |
| `P11-FEAT-GATEWAY-COST-OBS` | Gateway normalized cost and observability capability partition | Assigned at pickup | Ratified feature identity; plan number is not reserved. |
| `P11-FEAT-ZED-RESUME` | Zed integration fixes: `P9.8-FU-5` panic plus ACP session resume | 2nd | Required Zed proof slice; includes owned `P11-FU-1`. |
| `P11-FEAT-REGISTRY` | ACP registry requirements, registration, and v1.0 cut | 3rd | Required release slice; outward publication requires separate operator approval. |
| `P11-FEAT-IDE` | IDE-specific testing if registry registration does not surface or satisfy multi-IDE expectations | Conditional | Conditional; not an unconditional v1.0 gate. |

The feature IDs are permanent, greppable slice identities. They use the `P11-FEAT-*` prefix;
`FEAT` identifies milestone features and is distinct from `FU`, which identifies follow-ups. Slugs
carry no implied ordering. Each feature gets its own design/specification and review checkpoint
before implementation.

## Plan 11 feature-ID and plan-number allocation

Plan 11.x numbers are not reserved in advance. When a feature or backlog item is actually picked up
for scoping, it takes the next unused single-decimal slot at that moment. The number records
scheduling order only - never priority or scope identity. Two-decimal numbers such as `11.11` are
never valid. If new work must precede a planned slice, the new work takes the next number and the
planned slice takes a later number.

Feature IDs (`P11-FEAT-*`) and source IDs (`P9.8-FU-5`, `P11-FU-1`, and other stable backlog IDs)
are the durable identifiers; plan numbers are not. Promotion is recorded as `Promoted -> Plan 11.N`
with the date and plan-file link, matching the consolidated backlog's existing promotion rule.

## P11-FEAT-GATEWAY-CORE - Gateway Core and Observability Route

`P11-FEAT-GATEWAY-CORE` is Plan 11.1. Its scope is the Gateway core plus the
`/v1/observability/traces` route. Its design must resolve the one-key/origin boundary, the
`/v1/responses` and served `/v1/chat/completions` route contracts, upstream/provider adapter boundary,
gateway-side secret resolution, failure and retry behavior, normalized response-envelope validation,
and the Gateway-to-observability ingress contract. It must not move vendor keys into the agent runtime
or silently create a second local provider path.

The `P11-FEAT-GATEWAY-CORE` specification must identify the capability-level release evidence needed
for the model routes, observability ingress, one-key scans, provider failure behavior, response-envelope
fail-closed behavior, and the preserved ledger/trace interfaces. It must also identify any new follow-ups
in the consolidated backlog. Budget enforcement is not part of this scope; all such inventory rows
remain deferred to `P9.85-FU-3 (parked; operator decision pending)`.

## P11-FEAT-GATEWAY-TOOLS and P11-FEAT-GATEWAY-COST-OBS

`P11-FEAT-GATEWAY-TOOLS` is the ratified owner for web search/extract adapters, domain/provenance
revalidation, typed-tool envelopes, and the unscheduled `P11-FU-2` package/advisory capability. Its
Plan 11.x number is assigned at pickup.

`P11-FEAT-GATEWAY-COST-OBS` is the ratified owner for provider-native usage normalization, ledger
reconciliation, LangSmith export, amortized observability cost, and Plan 7 telemetry compatibility.
Its Plan 11.x number is assigned at pickup. Neither identity expands Plan 11.1's implementation scope.

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

`P11-FEAT-REGISTRY` begins with a research gate. ACP registry publication and registration requirements are not
yet known and must be researched against the current registry process before the implementation
scope is frozen. The research record must identify package metadata, naming/identity, protocol and
version declarations, validation, discoverability, release artifacts, ownership, and rollback or
withdrawal expectations that actually apply. `P11-FEAT-REGISTRY` also owns the v1.0 release inventory: a named
list of every capability excluded from the cut, with its rationale, custody, and next-phase or
conditional destination. That inventory is the authoritative answer to the DoD's
"feature-complete except Plan 12" boundary and must be reviewed before sign-off.

The v1.0 cut must update both known version locations together:

- `pyproject.toml`'s package version (`version = "0.1.0"` today); and
- `src/optimus/acp/spec.py`'s hardcoded `agentInfo.version` (`"0.1.0"` today).

The `P11-FEAT-REGISTRY` sub-plan must establish one release-version contract so these values cannot drift again, and
must add a check that fails when the package and ACP-reported versions disagree. Actual outward
registry registration/publication is an operator-controlled action and requires explicit approval
at the time the researched procedure is executed.

## P11-FEAT-IDE - Conditional IDE-specific testing

`P11-FEAT-IDE` is opened only if the `P11-FEAT-REGISTRY` research or registration process surfaces an unmet
multi-IDE requirement. It may cover JetBrains Air, JetBrains AI Assistant inside IntelliJ-family
products, or another operator-named client. It is not a standing v1.0 dependency: Zed is the v1.0
IDE proof, and registry registration is expected to satisfy the broader distribution expectation.

If `P11-FEAT-IDE` is opened, its scope and completion gate must be written as an explicit amendment rather
than inferred from the existence of a second IDE candidate.

## Backlog and completion gates

The Plan 11 backlog is one pool. It contains the carried `P9.8-FU-5` and `P9.87-FU-1` items, the
roadmap's **Re-pin FU-4A/FU-5 Live Evidence** freshness item, and follow-ups discovered during Plan
11 feature work. `P11-FU-1` is owned by `P11-FEAT-ZED-RESUME`, not parked. `P11-FU-2` is owned by
`P11-FEAT-GATEWAY-TOOLS` as an unimplemented, unscheduled package/advisory capability, and `P11-FU-3`
is owned by `LLD source repair` for the clipped §0.B and missing MCP endpoint contract. The
`P11-FEAT-ZED-RESUME` Zed live-evidence work should
coordinate with the re-pin, but the freshness item still needs explicit fresh-evidence closure or
a reviewed disposition. The budget-enforcement item `P9.85-FU-3` remains parked and undecided
outside Plan 11.1's initial scope; revisit it only if Gateway work organically reaches budget or cost
policy.

Primary `P11-FEAT-GATEWAY-CORE`, `P11-FEAT-ZED-RESUME`, and `P11-FEAT-REGISTRY` work is sequenced first. Before v1.0 sign-off, every item in the Plan 11 backlog
must be closed with evidence or an explicit reviewed disposition; v1.0 does not ship with an open
Plan 11 backlog. Conditional `P11-FEAT-IDE` is handled according to its explicit amendment and does not
become a v1.0 gate merely because an IDE candidate exists.

The v1.0 Definition of Done is therefore:

- Gateway capability work is complete within the one-key architecture, with Plan 11.1 closing the
  CORE plus observability-route gate and the ratified TOOLS/COST-OBS slices accounted for separately;
- the agent is feature-complete against the Phase 1 charter except for Plan 12's context/intelligence
  work, with every excluded capability named rather than implied;
- Zed ACP evidence proves the supported v1.0 interaction, including the `P11-FEAT-ZED-RESUME` session-resume and
  refusal-rendering dispositions;
- registry requirements are researched, the two version declarations are aligned, and the
  registration/release artifact and `P11-FEAT-REGISTRY` excluded-capability inventory are ready for explicit
  operator-approved execution; and
- the consolidated Plan 11 backlog is closed or has a reviewed, recorded disposition before the
  v1.0 cut.

## Explicit exclusions and unresolved inputs

- Plan 12's context-window optimization and intelligent selection remain post-v1.0 v1.x work.
- `P9.85-FU-3` remains outside the initial Plan 11 scope pending the Gateway budget authority
  decision.
- The **Windows Subprocess Handle-Duplication Flake, WinError 6/50** remains explicitly excluded
  from the initial Plan 11 backlog and v1.0 gate. Its existing roadmap entry remains the owner for
  future Windows investigation; the no-reproduction result, lack of a deterministic fix, and lack
  of a v1.0 capability/ACP-evidence dependency are the rationale. The same existing roadmap entry
  owns the separately identified durable-approval identity concern until a separate plan is
  designated; any scheduling requires its own reviewed custody decision.
- JetBrains Air and JetBrains AI Assistant are conditional/post-v1.0 candidates, not unconditional
  v1.0 gates.
- ACP registry requirements remain an open research input; this charter does not assume them or
  authorize external publication.
