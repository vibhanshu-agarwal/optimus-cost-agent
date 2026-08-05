# MCP Gateway Architecture Consolidated Document Redline — Draft

**Date:** 2026-08-05
**Status:** Redraft for fresh review; earlier sign-off withdrawn; no authoritative document regenerated
**Normative design:**
[`2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md`](../specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md)
**Required security reference:**
[`2026-08-05-mcp-gateway-security-best-practices-reference.md`](2026-08-05-mcp-gateway-security-best-practices-reference.md)

## 1. Source pins and proposed versions

| Document | Pinned source | Proposed publication |
|---|---|---|
| HLD | `Optimus-Cost-Agent-Architecture-v2.16.pdf` | v2.17 |
| LLD | `Optimus-Cost-Agent-LLD-v2.39.pdf` | v2.40 |
| Guardrails | `Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.1.pdf` | v1.2 |
| Test Strategy | `Optimus-Cost-Agent-Test-Strategy-v1.5.pdf` | v1.6 |
| Milestone charter | `2026-07-25-plan-11-v1-milestone-charter.md` | in-place charter amendment after review |

The prior PDFs have no complete editable authoring source. Publication will therefore use the
page-preserving splice method in `docs/sources/local-gateway-architecture-v3/`. The exact changed
page count is determined only after layout; the clusters below are requirement touchpoints, not a
claim that eleven PDF pages will change.

## 2. Settled global wording

Every document must use these rules consistently:

1. Replace "the Gateway holds exactly one upstream credential" with "the agent resolves zero
   upstream credentials; the Gateway may hold multiple profile-scoped upstream credentials."
2. Preserve the one agent-facing URL/shared-secret boundary. MCP adds no local agent credential.
3. State both stdio and Streamable HTTP transport support, limited to operator-preprovisioned
   static credentials.
4. Preserve the Plan 6.5 agent-side MCP trust registry and add an independent Gateway profile
   allowlist/binding check.
5. Bind approval to `(non-secret manifest hash, opaque profile revision)` and force reapproval on
   either change.
6. Use `profile_id.tool_name` agent-side and upstream tool names Gateway-side.
7. Permit only the enumerated tools-only protocol surface and fail closed at method, result-type,
   and content-behavior boundaries.
8. Keep existing settled usage rows unchanged; MCP uses its own attribution-aware usage row.
9. Require Docker containment for every stdio profile: immutable image digest, no host mounts,
   devices, or Docker socket, and safe `-e NAME` credential projection. Record daemon/image and
   permitted-network-policy residuals without pretending Docker is a universal security boundary.
10. Do not imply resistance to Gateway compromise.
11. Target MCP `2026-07-28` using the official [Go SDK v1.7.0
    release](https://github.com/modelcontextprotocol/go-sdk/releases/tag/v1.7.0) as the support
    citation and the immutable [wire-content snapshot at commit
    `f817239`](https://github.com/modelcontextprotocol/modelcontextprotocol/tree/f817239f4d6b1efff2c4dfc2f7af85c985d73076).
    At that commit the `2026-07-28` material is under `schema/draft/`, not a released
    per-version schema directory; do not present the snapshot as final publication. Remote HTTP
    credential profiles use per-request `_meta`, `server/discover`, `tools/list`, and `tools/call`
    at `2026-07-28`, with no initialization fallback, client ping, protocol session, or standalone
    GET stream. Containerized stdio probes first and may negotiate a modern version or use the
    legacy initialization handshake. Missing remote discovery/version/tools support yields the
    narrow `mcp.protocol_version_unsupported` disposition, never HTTP downgrade.
12. Exhaust bounded `tools/list` pagination or produce no manifest; an incomplete prefix is never
    approvable. Cursor-integrity failures close, while transient transport failures retry and
    capacity exhaustion is a narrow retry/provisioning outcome.
13. Treat MCP registries as operator-facing catalog metadata only. No registry trust, autoload,
    install, connect, update, activation, agent/model lookup, or Gateway data-plane query exists in
    v1. Keep this distinct from ACP `P11-FEAT-REGISTRY`.
14. Keep provisioning state separate from runtime connection open/close. A socket or stdio child
    for an active profile cannot activate or mutate that profile.
15. State the OAuth architecture while keeping its implementation deferred: automatic token
    refresh within an unchanged authorization binding is not rotation; grant/issuer/resource/
    subject/scope/client/store/policy change is rotation and forces reapproval.
16. Preserve the method/result-type/content denial for elicitation and sampling in v1, and state the
    exact future-open conditions instead of deleting the denial. Close deprecated external MCP
    logging too: no `logging/setLevel` or logging channel changes Optimus's own audit logging.
17. Record Context7 as the named remote-compatibility dependency of `P11-FEAT-GATEWAY-MCP`: its
    configured endpoint must pass an authenticated Gateway `server/discover` probe for
    `2026-07-28` plus tools before the documents claim Context7 reachability or use it as live
    evidence. The current public transport documentation is not version-support evidence.
18. Extend existing `RetryPolicy`, LLD §12B, Guardrails §5, and Test Strategy §14.4; do not create
    parallel retry or trust layers. Generalized OWASP findings land in HLD/LLD as individually
    labelled `REFERENCE — Cross-cutting` guidance; only separately labelled MCP controls are
    normative with `P11-FEAT-GATEWAY-MCP` ownership.
19. Treat admitted MCP descriptors as recurring model-input cost. V1 enforces an operator-selected
    approved subset plus count/byte ceilings; semantic tool search remains deferred.
20. Record the exclusion provenance honestly: local-Gateway v3 explicitly reaffirmed the no-MCP
    rule while moving to loopback, so the hosted-premise causal theory is unconfirmed, not fact.
    Repair the Guardrails change log, whose v1.1 PDF still ends at the v1.0 entry.

## 3. HLD v2.16 -> v2.17

### HLD-MCP-1 — §5A single-key invariant

Replace the one-aggregator-credential claim with:

> `OPTIMUS_API_KEY` remains the only agent-facing credential. It authenticates the agent to the
> strict-loopback Gateway and is not an upstream vendor key. The Gateway may hold one model
> aggregator credential plus multiple operator-provisioned, profile-scoped MCP credentials. The
> architectural invariant is zero upstream credentials in the agent process, not exactly one
> upstream credential in the Gateway process.

Add an MCP cost qualification:

> Model and existing typed-tool usage retains the mandatory settled `GatewayUsage` contract. MCP
> calls use separate attribution-aware records so provider-reported spend, operator-asserted zero
> marginal cost, and unavailable cost are never conflated.

Add the HLD-level context-cost position:

> Approved MCP descriptors are recurring model-input cost. A pre-model admission gate exposes only
> the operator-selected approved subset, enforces descriptor-count and UTF-8-byte ceilings, and
> records admitted identities/count/bytes. Provider-reported model input usage remains the billing
> authority; Optimus does not estimate per-descriptor tokens. Semantic tool search, automatic
> per-turn selection, and code mode are deferred to `P11-FU-15`.

Sampling must have a separate cost callout: it is closed in v1 because it lets a server initiate
model spend with server-supplied prompt content. A future opening requires pre-model budget
reservation, linked provider usage and `MCPUsageRecord`, and human review before both model dispatch
and response return.

### HLD-MCP-2 — §6 deterministic data flow

Add a guarded MCP branch after the pre-tool decision and before result consumption:

> For an approved namespaced MCP tool, the agent validates the Plan 6.5 trust record and sends the
> profile ID, upstream tool name, arguments, non-secret manifest hash, and profile revision to the
> Gateway. The Gateway independently validates the active profile, exact binding pair, upstream
> allowlist, resource limits, and budget policy before contacting the configured stdio or
> Streamable HTTP server. Returned content remains untrusted.

Registration and refresh must show `server/discover` followed by complete bounded `tools/list`
pagination. A cursor loop, malformed cursor, or malformed page rejects discovery as a whole; a
partial tool prefix cannot reach approval or the planner. Transient transport failures retry through
the existing policy, while a provisioned page/tool/byte/time bound produces no manifest and a narrow
capacity disposition; v1 restarts a complete scan rather than storing cursor checkpoints.

### HLD-MCP-3 — §10.A system context diagram and caption

Add two Gateway-owned external edges:

- Gateway -> operator-approved remote MCP servers over pinned Streamable HTTP; and
- Gateway -> operator-approved local stdio MCP child processes.

The diagram must show MCP credential/profile storage inside the Gateway process boundary and must
not draw an agent-to-MCP edge. It may show an operator consulting a curated MCP catalog before
provisioning, but no agent/model/Gateway data-plane edge to a registry and no discover-and-connect
arrow is permitted. Replace the current "No MCP endpoint is shown or implied" caption
with:

> Figure 10.A — Local-first system context. MCP servers are reachable only through the
> strict-loopback Gateway after both agent and Gateway trust checks; no upstream MCP credential
> enters the agent process.

### HLD-MCP-4 — §10.C Phase 1 release gate

Replace "the Gateway receives only its approved aggregator key" with:

> The agent runs with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no model, search, MCP, OTel,
> or other upstream credential is resolvable in the agent process. The Gateway receives only the
> approved credentials and profile records required by its enabled capabilities, with MCP secrets
> isolated per profile.

### HLD-MCP-5 — §11 responsibilities and process configuration

Add Gateway responsibilities for typed MCP discovery/call routes, `2026-07-28` per-request protocol
metadata, bounded `tools/list` pagination, per-profile credential projection, independent upstream
allowlists, binding-pair enforcement, tools-only protocol filtering, result/resource limits,
MCP usage attribution, connection teardown, and restart-to-activate provisioning.

State that the protocol floor is deliberately breaking for remote HTTP credential profiles: a remote
profile whose server cannot establish `2026-07-28` discovery and tools support receives the narrow
`mcp.protocol_version_unsupported` disposition and never falls back to `initialize`. A Docker-
contained stdio profile probes first and may negotiate a compatible modern or legacy tools-only
protocol. Name Context7 as the remote-compatibility dependency. Its public Streamable HTTP
configuration establishes the motivating transport case, not protocol-version support. Before
publication or implementation claims Context7 reachability, require an authenticated Gateway-
originated probe of the configured Context7 endpoint that proves the required discovery/version/
tools contract.

State explicitly that the remote no-fallback choice deliberately narrows the official Go SDK v1.7.0
default, which may negotiate down to `2025-11-25` or earlier. This is an HTTP credential-transport
rule; stdio's arbitrary-code risk is controlled by mandatory Docker containment, not an HTTP auth
handshake.

Add the split-authority residual:

> The agent remains authoritative for human approval, descriptor trust, permission scope, and
> effect class. The Gateway is authoritative for profile state, credential custody, upstream-name
> allowlists, binding freshness, transport execution, resource limits, and budget admission. A
> direct shared-secret caller can bypass agent-only scope/effect checks but cannot exceed the
> operator-provisioned Gateway allowlist. A recoverable refresh failure marks the last bound
> manifest stale rather than denying it; detected drift remains a denial. This is accepted only for
> Phase 1's strict-loopback, single-operator deployment.

The configuration table must show multiple Gateway-only MCP secret references and must not expose
their values or secret-derived digests agent-side. It must separate profile/provisioning fields from
runtime connection limits, and include protocol version, discovery page/tool/descriptor-byte/time
bounds, effective freshness policy, and descriptor-context count/byte ceilings.

Add an architecture-position block covering:

- registry catalog metadata is untrusted operator input and cannot install/connect/activate;
- OAuth is static-credential-only in v1, while the future binding discriminator distinguishes
  automatic same-grant refresh from reapproval-triggering rotation;
- `input_required` remains closed at method/result/content boundaries until the attributed UI and
  bounded continuation conditions exist; and
- normative MCP controls extend Plan 6.5 only.

Add a separate HLD architectural-reference panel with generalized observations for OWASP 2025
LLM01, LLM02, LLM03, LLM05, LLM06, LLM07, and LLM10 across tools, retrieval, configuration,
packages/skills/plugins, model and tool output, permissions/autonomy/spend, hidden context, retries,
long-lived work, and resource use. Every row must carry the literal voice/owner label
`REFERENCE — Cross-cutting` and avoid normative keywords. Follow it with a separate block labelled
`NORMATIVE — P11-FEAT-GATEWAY-MCP` for the MCP controls this amendment implements. The reference
panel is guidance, not an acceptance-criteria source.

### HLD-MCP-6 — §11.1 sequence and §12 quality gates

The sequence diagram must show:

1. agent pre-tool approval;
2. Gateway bearer and profile/binding/allowlist/budget checks;
3. profile-scoped transport execution;
4. untrusted result validation;
5. MCP-specific usage persistence; and
6. result release only after required accounting succeeds.

The flow must show that opening or closing an HTTP request/stdio child happens only after active-
profile admission and never changes provisioning state. HTTP has no protocol session; stdio child
reuse is bounded Gateway process custody, not MCP session resume.

The quality gates must add real stdio and HTTP interoperability, direct-route allowlist denial,
rotation/profile-change reapproval, credential-isolation scans, platform process-limit evidence,
strict-budget behavior, indeterminate-side-effect acknowledgment, and no deferred-protocol
capability leakage.

Add quality gates for the remote HTTP `2026-07-28` method set and absence of HTTP legacy
handshake/session/ping, Docker-contained stdio discovery-first negotiation, multi-page discovery
with cursor-integrity versus transient/capacity outcomes, catalog-only registry behavior,
connection/profile-axis separation, descriptor-context ceilings, existing-`RetryPolicy`
integration, OWASP voice/ownership classification, normative MCP-control traceability, call-scoped
elicitation triple denial, sampling causing no model call or spend in v1, Context7's named
real-server compatibility probe, and external MCP logging denial that leaves Optimus audit logging
unchanged.

## 4. LLD v2.39 -> v2.40

### LLD-MCP-1 — §§0.B-0.C component flow and responsibilities

Replace the explicit no-MCP branch with a typed MCP broker component containing:

- `MCPProfileRegistry` with pending/active/stale/disabled states;
- `MCPDiscoveryBroker`;
- bounded `MCPDiscoveryPaginator`;
- `MCPInvocationBroker`;
- `MCPConnectionManager` whose transport lifetime cannot mutate profiles;
- stdio and Streamable HTTP transport adapters;
- MCP result validator; and
- MCP usage writer; and
- agent-side MCP descriptor-context admission extending the existing trusted-descriptor exposure
  seam.

The diagram must keep the existing agent-side `MCPTrustRegistry` separate. It must show both checks
before execution and must not depict the Gateway as reimplementing permission-scope/effect logic.

### LLD-MCP-2 — §0.D and named endpoint block

Add exactly two agent-facing routes; do not expose an arbitrary MCP-method proxy.

```text
POST /v1/tools/mcp/discover
POST /v1/tools/mcp/call
```

Registration discovery requires `profile_id` and `profile_revision`. Refresh requires those fields
plus `manifest_hash`. Call requires run/session/request context, profile ID/revision, manifest hash,
upstream tool name, and arguments.

All routes require the existing bearer check. Call additionally requires active state, binding
match, last-known discovery freshness state, upstream allowlist membership, resource-policy
admission, and budget admission. Detected drift denies; a recoverable failed refresh uses the prior
approved binding with `freshness: stale_marked` recorded rather than disabling the profile.

Tool arguments are the only agent-originated payload forwarded to an MCP server. System prompts,
conversation history, policy text, and approval records are never forwarded; arguments pass the
existing redaction boundary before dispatch.

For remote HTTP credential profiles, the Gateway client targets `2026-07-28` and may emit only
`server/discover`, `tools/list`, and `tools/call`. Required protocol/client/capability metadata is
sent in `_meta` on every request; HTTP performs no initialization fallback, client ping, protocol-
session handling, or standalone GET/SSE. Unsupported remote discovery, exact-version support, or
tools capability maps to `mcp.protocol_version_unsupported`. Docker-contained stdio probes with
`server/discover`, negotiates a modern version when supported, and otherwise may initialize a legacy
tools-only session. No path advertises roots, sampling, elicitation, logging, or extension capability
or opens a subscription.

`tools/list` follows `nextCursor` to completion under provisioned page/tool/descriptor-byte/time
bounds. Repeated/malformed cursors and malformed/incomplete pages reject discovery atomically.
Transient failures retry; capacity exhaustion returns no manifest and a narrow disposition; v1 has
no cursor checkpoint. Effective freshness is `min(local_max_age, valid ttlMs)` and cache entries
remain partitioned by profile revision/credential binding regardless of upstream `cacheScope`.

### LLD-MCP-3 — §0.E and §0A profile and configuration contract

Define a versioned profile union:

```text
MCPProfile = StdioMCPProfile | StreamableHTTPMCPProfile
```

Common fields include `profile_id`, opaque revision, upstream allowlist, approved manifest hash,
state, discovery-freshness timestamp, attribution policy, duration/byte limits, and isolation
policy. Add pinned protocol version, discovery page/tool/descriptor-byte/time bounds, descriptor-
context count/byte ceilings, and connection idle/teardown limits. Stdio adds a Docker image digest,
command/arguments, container network policy, and `-e NAME` credential projection; tags, host mounts,
devices, and Docker socket projection are invalid. HTTP adds pinned scheme/origin/path, static
header mapping, and TLS policy.

Any Gateway-owned profile-field change mints a revision except initial approved-hash activation.
Disable does not mint; re-enable does. Activation is restart-based through the existing
HMAC-authenticated startup manifest; there is no runtime provisioning endpoint.

Document the future OAuth binding even though v1 rejects OAuth fields. Automatic token refresh
does not mint a revision only while protected resource, issuer, client registration, subject,
scope set, credential-store reference, transport target, and profile policy remain equal. Any
change to that tuple, step-up authorization, re-consent, client re-registration, operator token
replacement, or credential-mode change mints a revision and forces reapproval. Audience/issuer/
scope drift fails closed.

### LLD-MCP-4 — §§9, 9E-10A accounting and policy

Keep `GatewayUsage` and `ProviderUsage` unchanged. Add `MCPUsageRecord` with:

- mandatory request/profile/tool/transport/disposition/resource fields;
- `attribution_state` in `settled | explicit_zero | unavailable`;
- monetary fields mandatory for `settled`, exactly zero for `explicit_zero`, and absent for
  `unavailable`; and
- separate known-cost totals and unattributed-call counts.

Strict-dollar-budget execution admits only revision-bound operator-declared-free `explicit_zero` or
settled attribution; it denies `unavailable` before dispatch unless the revision-bound profile
explicitly permits unattributed spend. An upstream self-report cannot select `explicit_zero`. The
error is `mcp.budget.unattributed_spend_denied`.

Accounting persistence failure withholds the result and holds the run. Recovery retries only the
idempotent ledger write under the same `gateway_request_id`, never the upstream call.

Document the future sampling linkage rule adjacent to the schema, but do not add sampling-only
fields to the v1 schema: a future server-initiated model call would require normal provider usage
plus an `MCPUsageRecord` linked to the initiating profile/tool and two human decisions. V1 sampling
denial proves no sampling row, field population, or budget reservation is created.

### LLD-MCP-5 — §§12, 12B, and 12D trust integration

Extend `MCPServerManifest` with a remote/profile-aware variant rather than pretending the current
stdio-shaped command/env manifest already represents HTTP. Agent approval stores the namespaced
allowed tools and binding pair. No secret digest crosses from Gateway to agent.

Rotation and every other Gateway profile change must preserve the existing
`mcp.manifest_hash_changed` denial class. The current env-change test may be replaced only by a
successor proving that a Gateway-side credential revision breaks the bound pair without logging or
transporting secret-derived values.

After an indeterminate outcome, `PreToolGuard` permits read-only re-invocation but holds a
side-effecting `(profile_id, tool)` until operator acknowledgment. The hold record is durable in
the approval store and survives agent-session and agent-process restart.

Extend, do not duplicate, the existing Plan 6.5 and OWASP seams. Add an LLD reference table whose
every row is labelled `REFERENCE — Cross-cutting`, covering LLM01/02/03/05/06/07/10 and the
architectural component classes implicated across the product. The table is explanatory only and
must use no normative keyword or acceptance criterion. Add a physically separate table whose every
row is labelled `NORMATIVE — P11-FEAT-GATEWAY-MCP`, mapping descriptor/result distrust,
credential/payload isolation, preprovisioned supply-chain pins, output validation, split agency,
prompt non-forwarding, and pagination/context/resource/budget bounds to the existing Plan 6.5 seam
and named MCP implementation evidence.

Add the future-open elicitation contract without enabling it: method capability advertisement,
durable `input_required` hold, attributed operator UI, schema/URL-origin validation, explicit
accept/decline/cancel, rate/round/deadline bounds, redaction, and opaque untrusted `requestState`
must land as one amendment. The v1 path rejects all three boundaries and never redispatches.

### LLD-MCP-6 — §6.1 failure handling and runtime lifecycle

Extend the current failure taxonomy and `RetryPolicy`. Only transient `server/discover` and
`tools/list` failures may use the existing capped exponential-backoff/jitter path and restart a
complete scan. `tools/call`, authorization drift, pagination-integrity failures, policy denials,
and schema failures do not retry automatically. Older stdio protocol, absent optional metadata, and
recoverable refresh failure remain feature/call-scoped rather than profile-disable outcomes. Typed
safe errors state retryability and required operator action without raw authorization challenges or
unredacted server text.

Define runtime transport teardown separately from profile state. HTTP requests are stateless;
stdio children may be reused only within a bounded active-revision lease and terminate on disable,
stale/revision change, idle/duration/resource breach, corruption, or Gateway shutdown. No transport
open/close transition can activate or rewrite a profile.

## 5. Guardrails v1.1 -> v1.2

### GR-MCP-1 — §§1-3 control plane and authority

Add the split-authority sequence and direct-route residual. State that the shared bearer authenticates
the caller but does not establish MCP approval. Gateway allowlist enforcement is mandatory on every
MCP call even when the agent cage was bypassed.

### GR-MCP-2 — §5 MCP supply-chain defense

Preserve no-autoload, descriptor scanning, allowed-tools enforcement, permission scope, derived
effects, and manifest-change reapproval. Add:

- profile-ID namespacing;
- Gateway-side allowlist filtering before descriptors cross;
- verbatim descriptor text and versioned canonicalization;
- `2026-07-28` per-request metadata and exact method allowlist;
- complete bounded pagination with transient retry/capacity distinction and effective
  `min(local_max_age, ttlMs)` freshness, where failed refresh marks the last bound manifest stale
  rather than denying it until drift is detected;
- complete-only results;
- inert resource content;
- invalid `x-mcp-header` exclusion and no `Mcp-Param-*` emission;
- typed, call-scoped denial of deferred features; and
- effect-aware acknowledgment after indeterminate side-effecting calls.

Add catalog-only registry handling, separation of provisioning from connection lifetime, descriptor-
context count/byte admission, and the future-open conditions for elicitation and sampling. Preserve
the triple v1 denial. The normative controls are owned by `P11-FEAT-GATEWAY-MCP`; generalized OWASP
reference material belongs in HLD/LLD and must not be restated here as an unimplemented control.

### GR-MCP-3 — §§5.2, 9, and 11 residuals/accounting/tests

State three stdio tiers explicitly:

- enforced: Docker digest image, no host mounts/devices/socket, safe `-e NAME` credential
  projection, timeout/output limits, bounded reads, and termination;
- platform-gated: process-count confinement with real Windows and Linux/WSL2 evidence; and
- residual: Docker daemon/image trust and any provisioned network egress remain explicit; roots are
  not containment.

Add the MCP-specific accounting states and never-zero-for-unknown rule. Neither roots nor the
deferred model-generated code-execution pattern may be described as a sandbox boundary.

### GR-MCP-4 — §13 document control and change log

Repair the incomplete chain on page 16. Preserve the v1.0 initial-issue entry, add the missing v1.1
local-Gateway correction entry with its actual changed-page scope, and add v1.2 for this amendment.
Record that local-Gateway v3 explicitly reaffirmed the no-MCP disposition as global rule 14, while
its causal rationale was not captured. The hosted-SaaS-premise hypothesis must remain labelled
unconfirmed.

## 6. Test Strategy v1.5 -> v1.6

### TS-MCP-1 — §§1-3 scope and evidence tiers

Move Gateway-brokered tools-only MCP into scope for both stdio and Streamable HTTP. Keep dynamic
OAuth, non-tool capabilities, ACP client-supplied `mcpServers`, and ACP session resume out of scope
with named custody and distinct rationales.

Fakes are unit-tier only. Live claims require the real Gateway plus independently authored MCP
servers over both transports. Platform confinement claims require real Windows and Linux/WSL2
evidence.

### TS-MCP-2 — §§6-7 integration and security boundary

Add tests for registration bootstrap, restart activation, direct-route allowlist enforcement,
unmatched allowlist reporting, two-name-space collisions, canonical hash equality, discovery age,
profile revisioning, secret rotation, descriptor filtering/scanning, HTTP redirect denial, no
credential crossing, `x-mcp-header`, POST-SSE bounds, and Docker stdio isolation. Add protocol-
generation tests for remote HTTP per-request `_meta`, `server/discover`, absence of HTTP
initialize/session/ping, containerized stdio discovery-first negotiated/legacy behavior, complete
bounded `tools/list` pagination, cursor-loop/malformed-page denial, transient retry/capacity
disposition, `ttlMs` capping, profile-partitioned caching, and the typed remote unsupported-version
disposition with no HTTP fallback.

### TS-MCP-3 — §§8-10 accounting, retry, and schema

Add a Test Strategy §8A consumer sweep proving legacy usage rows remain unchanged while MCP rows
handle all three attribution states. Test strict-budget pre-execution denial, display/reconciliation
of unattributed calls, result withholding on accounting failure, and persistence-only recovery.

Test that `tools/call` never retries automatically; only transient `server/discover`/`tools/list`
failures use the existing `RetryPolicy` exponential backoff with jitter and at most three attempts
from a complete scan; indeterminate side-effecting re-invocation holds for operator acknowledgment
before and after agent restart. Authorization drift, pagination integrity, policy, and schema
failures are permanent. Verify failed refresh serves only the prior bound manifest with a stale
marker, while detected drift denies/requires reapproval.

### TS-MCP-4 — §§11-14 guardrails and release gate

Add fail-closed, call-scoped fixtures for `input_required`, roots, sampling, elicitation, external logging,
subscriptions, unsolicited server requests, automatic resource dereference, image/audio promotion,
invalid result schema, oversize output, timeout, stale binding, and invalid profile state. Prove
that external MCP logging cannot alter Optimus audit logging.

Add tests proving: catalog metadata can only prefill a pending operator proposal and never causes
lookup/install/connect/activation; transport open/close cannot mutate a profile; descriptor-context
count/byte ceilings and selected identities are enforced/recorded; sampling creates no model call,
budget reservation, provider/MCP usage, or response; and elicitation exposes no schema, URL, or
request state to the planner. Reference-only HLD/LLD OWASP rows create no Test Strategy acceptance
criteria; only the separately labelled normative MCP rows map to tests.

Context7 is a named remote compatibility dependency. Before any Context7 reachability claim, a live
Gateway-originated authenticated probe of its configured endpoint must prove `2026-07-28` and tools
support. A fake or different HTTP server cannot discharge this dependency; unsupported or
indeterminate evidence leaves only the HTTP capability unavailable with
`mcp.protocol_version_unsupported`.

Extend §14.4/§14.5 rather than replacing them. The named successor to
`test_launch_env_change_forces_reapproval_without_logging_secret_values` must prove Gateway-side
credential rotation causes the same agent-side denial while no secret or secret-derived digest is
logged or returned.

## 7. Plan 11 milestone charter amendment

The charter edit must:

1. change the shared invariant from "all three slices preserve one upstream credential" to "all
   slices preserve zero upstream credentials in the agent process";
2. mark the `P11-FU-3` route/typed-contract design gate satisfied only after this amendment and the
   four PDFs are approved/published;
3. define `P11-FEAT-GATEWAY-MCP` v1 as the tools-only, static-profile, dual-transport design in this
   redline; and
4. add the five owned follow-ups below without assigning speculative implementation plan numbers.

The charter must continue to distinguish Gateway-brokered MCP from `P11-FU-9` client-supplied ACP
`mcpServers` and `P11-FEAT-ZED-RESUME` session custody.

## 8. Deferred custody and rationale

| Deferred item | Rationale | Required owner |
|---|---|---|
| MCP OAuth 2.1 lifecycle | Acquisition, token custody, and step-up are absent; automatic same-binding refresh must remain distinct from grant/issuer/resource/subject/scope/client/store/policy rotation | `P11-FU-12` |
| Deferred MCP capabilities and long-lived interaction | Prompts/resources/elicitation/completion/subscriptions/tasks and resumable discovery cursor checkpoints need new trust and UX vocabulary; roots, sampling, and external logging are deprecated; roots is not access control; sampling reverses prompt/cost direction; external logging cannot alter Optimus audit logging | `P11-FU-13`, with sampling's separate double-approval/accounting gate preserved |
| MCP registry discover-and-connect | Catalog metadata is not code trust or operator approval; automated install/update/connect would invalidate the preprovisioned-only safety answer | `P11-FU-14`, explicitly distinct from ACP `P11-FEAT-REGISTRY` |
| MCP tool-search and context minimization | V1 bounds and records an operator-selected descriptor subset but has no semantic per-turn selection seam or code-mode sandbox | `P11-FU-15` |
| Reverse research-to-documentation freshness gate | Existing traceability catches normative doc requirements missing from specs, not research/implementation learning absent from authoritative docs; reference voice must not become a phantom requirement | `P11-FU-16` |

The rejected signed per-call capability design is a decision record, not deferred work. It should
not create a backlog item absent a real multi-user or off-box threat model.

## 9. Publication package after approval

Create `docs/sources/mcp-gateway-architecture-amendment/` containing:

- README with pinned sources and splice policy;
- changed-page Markdown for all four PDFs;
- revised HLD and LLD SVGs;
- print CSS;
- build manifest with source/output digests and replacement-page mapping;
- build and validation scripts adapted from `local-gateway-architecture-v3`;
- changed-pages manifests and a dropped-entry completeness audit; and
- final verification record with visual inspection, extraction anchors, page geometry, version
  checks, carried-page preservation, diagram validation, and SHA-256 values.

Before closing the publication and again before merge, audit the authoritative section map,
consolidated open-work pool, Phase 1 roadmap, README, and every other current-state claim affected
by the reversal.

## 10. Full-draft acceptance checklist

- [ ] The operator approves the split-authority and direct-route residual wording.
- [ ] The operator approves restart-to-activate and the sole no-revision activation write.
- [ ] The operator approves the tools-only method/result/content boundary.
- [ ] The operator approves honest stdio isolation tiers and platform gates.
- [ ] The operator approves the separate MCP accounting row and consumer sweep.
- [ ] Every current no-MCP statement is removed or replaced without weakening local trust.
- [ ] Both name spaces, revision rules, rotation behavior, and discovery freshness are explicit.
- [ ] OAuth refresh and rotation have a future-safe discriminator while OAuth implementation stays deferred.
- [ ] Remote HTTP credential-profile `2026-07-28` stateless methods, per-request metadata, pagination, cache age, and no-legacy-fallback posture are explicit; Docker-contained stdio negotiation is separately explicit.
- [ ] The breaking remote HTTP credential-profile floor, typed unsupported-version disposition, immutable source pin, and Context7 named compatibility dependency are explicit; no Context7 reachability is asserted without its real-server probe.
- [ ] Catalog-only MCP registry use cannot install/connect/activate and cannot be confused with ACP `P11-FEAT-REGISTRY`.
- [ ] Provisioning state and runtime connection lifetime remain separate axes.
- [ ] Sampling has its own prompt, double-approval, and linked-cost position; v1 proves no model call or spend.
- [ ] Deprecated external MCP logging is closed and cannot alter Optimus audit logging.
- [ ] Elicitation remains closed at method/result/content levels with one coordinated future-open condition.
- [ ] Descriptor context is an HLD cost concern with subset/count/byte admission; semantic tool search remains deferred.
- [ ] MCP failures extend existing `RetryPolicy`; pagination and responsiveness failures have typed dispositions.
- [ ] Every generalized OWASP statement is labelled `REFERENCE — Cross-cutting`; every normative MCP control is separately labelled and owned by `P11-FEAT-GATEWAY-MCP`.
- [ ] Exclusion provenance is described as unconfirmed, Guardrails document control is repaired, and `P11-FU-16` owns the reverse-direction process gap.
- [ ] Every exclusion has named custody and its own rationale.
- [ ] Gateway-MCP remains distinct from ACP `mcpServers` and ACP session resume.
- [ ] PDF generation, charter mutation, implementation, commit, and push remain separately gated.
