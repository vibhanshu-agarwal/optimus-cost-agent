# Plan 11 v1.0 Milestone Charter

## Status and baseline

**Status:** Charter draft for review; no implementation sub-plan is authorized by this document.

**Baseline:** `origin/main` at `9d366c0` (merged Plan 11 roadmap expansion). The living roadmap and
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

The Gateway Capabilities Broker remains the first primary slice:

- broker web search, web extract, and observability export through the Gateway;
- preserve the one-key local credential boundary, with vendor keys owned and resolved gateway-side;
- add the Gateway routes and upstream adapters needed by the existing agent-side seams; and
- normalize usage, cost, and observability fields for non-model calls consistently with model calls.

The Gateway design must continue to respect the authoritative HLD/LLD/Guardrails boundary. The
parked `P9.85-FU-3` budget-enforcement question is not pulled into this charter's initial scope.

## Revised sub-plan map

| Slice | Scope | v1.0 relationship |
|---|---|---|
| `11.1` | Gateway Capabilities Broker | First primary feature slice; required. |
| `11.2` | Zed integration fixes: `P9.8-FU-5` panic plus ACP session resume | Required Zed proof slice; includes owned `P11-FU-1`. |
| `11.3` | ACP registry requirements, registration, and v1.0 cut | Required release slice; outward publication requires separate operator approval. |
| `11.4` | IDE-specific testing if registry registration does not surface or satisfy multi-IDE expectations | Conditional; not an unconditional v1.0 gate. |

The numbering is a sequencing map, not permission to implement multiple slices in one PR. Each
slice gets its own design/specification and review checkpoint before implementation.

## 11.1 - Gateway Capabilities Broker

11.1 carries forward the existing Gateway broker scope unchanged from the roadmap. Its design must
resolve the route contract, upstream/provider adapter boundary, gateway-side secret resolution,
failure and retry behavior, normalized usage/cost accounting, and observability export. It must not
move vendor keys into the agent runtime or silently create a second local provider path.

The 11.1 specification must identify the capability-level release evidence needed for web search,
web extract, observability export, one-key scans, provider failure behavior, and cost/usage
attribution. The specification must also identify any new follow-ups in the consolidated backlog.

## 11.2 - Zed integration fixes and session resume

11.2 owns two ACP-facing items:

- `P9.8-FU-5`, the Zed refusal-rendering panic and its agent-payload versus externally owned client
  disposition; and
- `P11-FU-1`, the session-resume capability gap described below.

The Zed v1.0 proof must preserve ACP conformance and the existing fail-closed refusal behavior. An
agent-side workaround for the client panic requires its own reviewed design decision and must not
weaken refusal semantics.

### Session-resume design contract

The current implementation advertises an empty `sessionCapabilities` object and dispatches no
`session/load`; a resume request therefore returns `METHOD_NOT_FOUND`, and the client correctly
starts a new session. The 11.2 specification must cover, as one design problem:

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
session state, so it is not an implementation-ready answer. The 11.2 design must compare and select
an explicit session-state storage strategy, including security and workspace isolation, rather than
assuming that the plan store is sufficient. If durable state is unavailable or corrupt, behavior
must be fail-closed and operator-visible; it must not advertise resume and then lose history.

The 11.2 evidence plan must include protocol-level tests for capability negotiation, successful
load, unknown/expired sessions, workspace mismatch, malformed state, storage unavailability, and
history replay. ACP live evidence must use an independently authored ACP client, with Zed evidence
for the v1.0 gate.

## 11.3 - ACP registry registration and v1.0 cut

11.3 begins with a research gate. ACP registry publication and registration requirements are not
yet known and must be researched against the current registry process before the implementation
scope is frozen. The research record must identify package metadata, naming/identity, protocol and
version declarations, validation, discoverability, release artifacts, ownership, and rollback or
withdrawal expectations that actually apply.

The v1.0 cut must update both known version locations together:

- `pyproject.toml`'s package version (`version = "0.1.0"` today); and
- `src/optimus/acp/spec.py`'s hardcoded `agentInfo.version` (`"0.1.0"` today).

The sub-plan must establish one release-version contract so these values cannot drift again, and
must add a check that fails when the package and ACP-reported versions disagree. Actual outward
registry registration/publication is an operator-controlled action and requires explicit approval
at the time the researched procedure is executed.

## 11.4 - Conditional IDE-specific testing

11.4 is opened only if the 11.3 registry research or registration process surfaces an unmet
multi-IDE requirement. It may cover JetBrains Air, JetBrains AI Assistant inside IntelliJ-family
products, or another operator-named client. It is not a standing v1.0 dependency: Zed is the v1.0
IDE proof, and registry registration is expected to satisfy the broader distribution expectation.

If 11.4 is opened, its scope and completion gate must be written as an explicit amendment rather
than inferred from the existence of a second IDE candidate.

## Backlog and completion gates

The Plan 11 backlog is one pool. It contains the carried `P9.8-FU-5` and `P9.87-FU-1` items and
follow-ups discovered during Plan 11 feature work. `P11-FU-1` is owned by 11.2, not parked. The
budget-enforcement item `P9.85-FU-3` remains parked and undecided outside Plan 11's initial scope;
revisit it only if Gateway work organically reaches budget or cost policy.

Primary 11.1-11.3 work is sequenced first. Before v1.0 sign-off, every item in the Plan 11 backlog
must be closed with evidence or an explicit reviewed disposition; v1.0 does not ship with an open
Plan 11 backlog. Conditional 11.4 is handled according to its explicit amendment and does not
become a v1.0 gate merely because an IDE candidate exists.

The v1.0 Definition of Done is therefore:

- Gateway broker functionality is complete within the one-key architecture;
- the agent is feature-complete against the Phase 1 charter except for Plan 12's context/intelligence
  work, with every excluded capability named rather than implied;
- Zed ACP evidence proves the supported v1.0 interaction, including the 11.2 session-resume and
  refusal-rendering dispositions;
- registry requirements are researched, the two version declarations are aligned, and the
  registration/release artifact is ready for explicit operator-approved execution; and
- the consolidated Plan 11 backlog is closed or has a reviewed, recorded disposition before the
  v1.0 cut.

## Explicit exclusions and unresolved inputs

- Plan 12's context-window optimization and intelligent selection remain post-v1.0 v1.x work.
- `P9.85-FU-3` remains outside the initial Plan 11 scope pending the Gateway budget authority
  decision.
- JetBrains Air and JetBrains AI Assistant are conditional/post-v1.0 candidates, not unconditional
  v1.0 gates.
- ACP registry requirements remain an open research input; this charter does not assume them or
  authorize external publication.
