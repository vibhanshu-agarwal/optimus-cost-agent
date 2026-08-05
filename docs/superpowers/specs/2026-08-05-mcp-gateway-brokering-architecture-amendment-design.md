# MCP Gateway Brokering Architecture Amendment Design

**Date:** 2026-08-05
**Status:** Redraft for reviewer review; prior sign-off withdrawn
**Feature owner:** `P11-FEAT-GATEWAY-MCP`
**Decision source:** affirmative `P11-FU-3` operator ruling and redraft rulings 8-16
**Required security reference:**
[`2026-08-05-mcp-gateway-security-best-practices-reference.md`](../reports/2026-08-05-mcp-gateway-security-best-practices-reference.md)

**OWASP numbering check:** the LLM01/02/03/05/06/07/10 names used below were reverified on
2026-08-05 against OWASP's official
[2025 Top 10 risk list](https://genai.owasp.org/llm-top-10/?cat=253); the older-list caveat in the
research compilation is not used as an authority for numbering.

**Protocol support and frozen wire snapshot:** the official
[Go SDK v1.7.0 release](https://github.com/modelcontextprotocol/go-sdk/releases/tag/v1.7.0)
is the primary citation for `2026-07-28` support and identifies the stateless lifecycle, discovery,
and roots/sampling/logging deprecations. Its immutable
[MCP repository commit `f817239`](https://github.com/modelcontextprotocol/modelcontextprotocol/tree/f817239f4d6b1efff2c4dfc2f7af85c985d73076)
freezes the wire-content snapshot used by that SDK release. At this commit, the `2026-07-28`
artifact resides under `schema/draft/`, not a released `schema/2026-07-28/` directory; the commit
is therefore a content snapshot, not a claim of final per-version specification publication.
Mutable live `/specification/draft/` pages and the release-candidate announcement are not the
version-pinned authority for this amendment. The
[MCP Registry overview](https://modelcontextprotocol.io/registry/about) remains a living reference
for its catalog role. These sources establish protocol facts; the normative v1 choices and
ownership remain those stated in this amendment.

## 1. Purpose

Phase 1 will broker approved MCP tools through the strict-loopback Optimus Gateway. This reverses
the current documentation exclusion without weakening the shipped Plan 6.5 agent-side MCP trust
registry.

The invariant is not "one upstream credential." It is:

> The agent process receives only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` and can resolve zero
> upstream credentials. The Gateway may hold multiple operator-provisioned, profile-scoped MCP
> credentials, but no credential or secret-derived identifier crosses into the agent process.

This document is an architecture amendment, not an implementation plan. No route, profile, ledger,
or sandbox claim is complete until the Test Strategy evidence named here passes.

### 1.1 Exclusion provenance finding

**REFERENCE — owner `Cross-cutting`; non-normative.** The local-Gateway v3 correction did not merely
carry the MCP exclusion on an untouched page. Its consolidated redline made "MCP is outside this
correction" settled global rule 14 and newly authored no-MCP captions, route text, and test-scope
text while also replacing the hosted service with a loopback process. This weakens the hypothesis
that the exclusion survived wholly unexamined. The artifacts record no rationale for reaffirming
it, however, so they neither confirm nor disprove that a hosted-SaaS premise influenced the choice.
Guardrails v1.1 page 16 also retains only the v1.0 change-log entry, leaving that document's v1.1
provenance incomplete.

**NORMATIVE — owner `P11-FEAT-GATEWAY-MCP` publication.** The amendment must describe the causal
hypothesis as unconfirmed, must repair the Guardrails v1.1-to-v1.2 document-control/change-log chain,
and must not claim that the prior exclusion was simply accidental. The missing reverse-direction
research-to-documentation freshness gate is deferred to `P11-FU-16`.

## 2. V1 scope

V1 targets MCP protocol version `2026-07-28` and supports both operator-preprovisioned transport
forms:

- local stdio servers in a mandatory Docker container with a digest-pinned image, fixed command and
  arguments, projected static credential, upstream-tool allowlist, and isolation policy; and
- remote Streamable HTTP servers with a pinned endpoint and static bearer/API-key headers.

Profiles are never discovered or loaded from repository configuration. Dynamic OAuth 2.1
acquisition and lifecycle management are excluded from v1 implementation; v1 has no CIMD/DCR,
browser authorization, refresh-token storage, token refresh, or dynamic client registration. The
future architecture position and refresh-versus-rotation discriminator are nevertheless fixed in
this amendment so that later OAuth work cannot weaken reapproval silently.

The MCP protocol surface is tools-only. For remote Streamable HTTP profiles that carry a credential
across the network, the Gateway's internal client may send only `server/discover`, `tools/list`, and
`tools/call` at `2026-07-28`; required protocol version, client identity, and client capabilities
ride in per-request `_meta`, and v1 performs no legacy `initialize` fallback. For a mandatory-
containerized stdio profile, the Gateway first probes with `server/discover` at its preferred modern
version. A modern reply selects a mutually supported version; a legacy/error-or-timeout reply may
use the legacy `initialize`/`initialized` handshake and then the same tools-only list/call surface.
The selected era/version is canonical manifest data and a change to it requires reapproval. Client
metadata advertises no roots, sampling, elicitation, logging, or extension capability, and v1 opens
no subscription stream.

Only `resultType: "complete"` is accepted. `input_required` is denied with a typed, call-scoped
error and is never promoted into a model-visible question or profile-state transition. Tool-result resource links and embedded resources
are inert data and are never automatically fetched. Prompts, resource operations, sampling,
elicitation, completion, subscriptions, roots, external MCP logging, and model-generated code
execution are closed in v1 and have the explicit future-open conditions and custody recorded below.
External MCP logging is distinct from Optimus's existing append-only audit logging and telemetry;
v1 neither sends `logging/setLevel` nor accepts an MCP logging channel that can change Optimus
logging policy or volume.

The `2026-07-28` floor is deliberately breaking only for remote Streamable HTTP profiles that carry
credentials over the network. Such a remote credential-bearing server that does not successfully
answer `server/discover` with support for `2026-07-28` and the tools capability receives the typed,
profile-capability disposition `mcp.protocol_version_unsupported`; it remains provisioned for a
later compatible probe but cannot activate its HTTP tools. The Gateway does not downgrade that
remote profile to `initialize`. This intentionally narrows the official Go SDK v1.7.0 negotiation
behavior, which may negotiate to `2025-11-25` or earlier. Containerized stdio instead follows the
probe/negotiation path above, because the protocol's authorization rules are HTTP-scoped and stdio
credentials are projected into the contained child environment rather than negotiated over HTTP.

**Named `P11-FEAT-GATEWAY-MCP` dependency — Context7 remote compatibility:** Context7 is the
motivating remote Streamable HTTP case. Its
[public client configuration](https://context7.com/docs/resources/all-clients) identifies a
Streamable HTTP endpoint, but does not pin the deployed server's protocol version. Before this feature claims
Context7 reachability or uses Context7 as remote live evidence, a Gateway-originated, authenticated
probe of the configured endpoint must establish the `2026-07-28` discovery/version/tools contract.
Until that evidence exists, Context7 support is indeterminate rather than assumed; a failed or
unsupported probe leaves its HTTP capability unavailable and never enables legacy fallback. This is an
existing feature dependency, not a new discovery/autoconnect capability or a deferred roadmap item.

### 2.1 Position ledger for the expanded review scope

This is position-level capture, not subsystem design. Each row names the architectural position,
the v1 control that enforces it, the implementation excluded from v1, and the custody owner.

| Area | Architectural position | V1 enforcement and owner | Out of v1 and custody |
|---|---|---|---|
| OWASP reference and control voice | Generalized findings land now in HLD/LLD only as statements explicitly labelled `REFERENCE — Cross-cutting`; normative MCP controls remain separately labelled and extend the Plan 6.5 cage | Only the separately marked `NORMATIVE — P11-FEAT-GATEWAY-MCP` controls in §10.1 create v1 obligations | A reverse research-to-documentation freshness gate is not designed here and is owned by `P11-FU-16` |
| Protocol floor and Context7 reachability | `2026-07-28` is the HTTP credential-transport floor, not a best-effort preference; containerized stdio uses discovery-first protocol negotiation | Remote Gateway discovery requires the exact version and tools capability, returns call-scoped `mcp.protocol_version_unsupported` when absent, and records Context7 as a named real-server compatibility dependency of `P11-FEAT-GATEWAY-MCP` | HTTP legacy fallback is excluded; Context7 cannot be represented as supported until its configured deployment passes the named live probe |
| OAuth 2.1 | Future HTTP OAuth uses per-profile Gateway custody; automatic refresh is not operator rotation when the authorization binding is unchanged | V1 profile validation rejects OAuth fields and treats 401/403 as typed authorization failure; owner `P11-FEAT-GATEWAY-MCP` | Acquisition, registration, secure token storage, refresh, and step-up are owned by `P11-FU-12` |
| Elicitation | The method/result-type/content triple remains closed in v1; it may open only through the attributed, schema-validated, rate-limited operator interaction in §6.1 | No elicitation capability is advertised; every `input_required` result is a typed, call-scoped denial, never a planner question or profile-state change; owner `P11-FEAT-GATEWAY-MCP` | Form/URL UI, accept/decline/cancel, and bounded multi-round-trip execution are owned by `P11-FU-13` |
| MCP registry | Registry data is catalog metadata that an operator may consult before manual provisioning; it is never runtime trust or authority | No registry route, agent/model lookup, autoload, install, connect, or activation exists; owner `P11-FEAT-GATEWAY-MCP` provisioning gate | Discover-and-connect, automated installation/update, and registry trust scoring are owned by `P11-FU-14`, not ACP `P11-FEAT-REGISTRY` |
| Connection lifecycle | Provisioning controls whether a profile may exist; transport open/close controls resources for an already-active profile | Stateless per-request HTTP and bounded stdio child lifetime are enforced by the Gateway transport adapters; owner `P11-FEAT-GATEWAY-MCP` | Pooling, long-lived subscriptions, task streams, and cross-request transport state are owned by `P11-FU-13` |
| Tool-search and context cost | Approved descriptors are a recurring model-input cost and pass a pre-model context-admission budget; provider-reported input usage remains the billing authority | Only an operator-selected subset of approved, namespaced descriptors may be admitted; descriptor count/bytes and admitted identities are recorded by `P11-FEAT-GATEWAY-MCP` | Semantic tool search, automatic per-turn selection, and code mode are owned by `P11-FU-15` |
| Error handling and retry | Extend the existing failure taxonomy and `RetryPolicy`; do not create an MCP-only retry engine | Safety failures close; transient discovery/refresh failures retry through the existing path and capability absence yields a narrow disposition, subject to the no-automatic-`tools/call` rule; owner `P11-FEAT-GATEWAY-MCP` | Task-style or resumable long-running operations are owned by `P11-FU-13` |
| Pagination and responsiveness | Registration/refresh consumes every `tools/list` page or yields no approvable manifest; hostile cursor integrity is distinct from recoverable capacity | Cursor-loop detection closes; profile page/tool/byte/time limits are provisionable, transient discovery retries use the existing policy, and effective cache age/cancellation/teardown are implemented by `P11-FEAT-GATEWAY-MCP` | Resumable cursor checkpoints, unbounded browsing, background pagination, progress UI, and subscription-driven refresh are owned by `P11-FU-13` |

### 2.2 Sampling position

Sampling is not a capability-table footnote. It lets an MCP server initiate inference with
server-supplied prompt content on Optimus's model budget, so it combines MCP-scoped OWASP
LLM01:2025 Prompt Injection and LLM10:2025 Unbounded Consumption and reverses the normal cost
direction.

- **Architectural position:** sampling is deprecated in MCP `2026-07-28`; v1 does not advertise or
  fulfill it. If a later amendment opens it, server content may reach a model only in a dedicated,
  server-attributed sampling request after the operator reviews the exact prompt. No Optimus system
  prompt, conversation history, approval record, other-server context, or server-nominated tool is
  inherited.
- **Control that would open it:** one human decision is required before reserving budget and
  forwarding the reviewed request to the model, and a second human decision is required before
  returning the model response to the server. The generated call must create normal provider usage
  plus a linked `MCPUsageRecord` attributed to the initiating profile/tool; unavailable cost cannot
  be treated as zero.
- **V1 enforcement:** sampling capability metadata is absent and sampling inside
  `InputRequiredResult` is rejected at the method, result-type, and content boundaries.
- **Out of v1 and custody:** sampling UI, prompt editing, double approval, model/tool selection,
  linked accounting, and bounded multi-round-trip state are owned by `P11-FU-13`.

## 3. Split authority model

### 3.1 Agent authority

The existing agent-side cage remains authoritative for:

- human approval;
- sanitized descriptor and manifest trust;
- namespaced `allowed_tools`;
- `permission_scope` and independently derived effect class;
- descriptor exposure to the planner; and
- the final pre-tool decision.

The approval record binds `(non-secret manifest hash, Gateway profile revision)`. Either value
changing produces the existing `mcp.manifest_hash_changed` hold and requires reapproval.

### 3.2 Gateway authority

The Gateway independently enforces an operator-provisioned record containing:

- unique operator-assigned `profile_id`;
- transport configuration;
- Gateway-only secret reference;
- upstream-name allowlist;
- current opaque revision;
- approved non-secret manifest hash after activation;
- attribution policy, resource limits, and isolation policy; and
- lifecycle state.

Every data-plane request still requires the shared bearer secret. MCP invocation additionally
requires an active profile, exact binding-pair match, and membership in the Gateway's own upstream
allowlist. A caller that bypasses the agent cage cannot widen beyond that allowlist.

The Gateway does not duplicate `permission_scope` or effect-class evaluation. A direct caller that
possesses the shared secret and the non-secret binding values can bypass those agent-only checks,
but cannot exceed the provisioned Gateway allowlist or invoke after detected binding/manifest drift.
A recoverable failed refresh instead marks the last bound record stale and leaves that narrow
residual explicit. This is accepted only for v1's strict-loopback, single-operator machine and must
remain explicit in HLD, LLD, and Guardrails.

This design does not resist a compromised Gateway. The Gateway necessarily holds credentials and
the upstream execution path. Split authority limits agent-side credential misuse, direct-route
privilege widening, and silent record drift; it does not make Gateway compromise harmless.

### 3.3 Write authority and revisions

Profile administration is absent from the bearer-authenticated data plane. Profiles are created
and changed only through the operator provisioning and HMAC-authenticated startup-manifest flow.

Any change to the Gateway-owned profile surface mints a new random revision, including a change to:

- static secret reference or static credential;
- transport, endpoint, executable, arguments, or working directory;
- upstream allowlist;
- isolation or resource-limit policy;
- attribution mode; or
- permission to use unattributed spend.

The revision is random or derived with a Gateway-held keyed construction; it is never a plain or
salted hash of a credential. Disabling a profile is immediate and does not mint a revision.
Re-enabling always mints a revision and requires reapproval.

The one exception is the initial approved-manifest-hash synchronization. It completes approval for
the already-reviewed revision and therefore does not mint another revision.

The architecture-level OAuth exception is intentionally narrower. Once `P11-FU-12` is implemented,
an automatic access-token or rotating-refresh-token replacement performed inside the same approved
grant is **refresh**, not profile rotation, only while all of these remain equal: protected-resource
URI, authorization-server issuer, client registration, resource-owner subject, granted scope set,
credential-store reference, transport target, and profile policy. Refresh never changes the
revision. A change to any member of that authorization binding, a step-up scope grant, re-consent,
client re-registration, operator-supplied token replacement, or credential-mode change is
**rotation** and must mint a revision. Returned audience/issuer/scope drift fails closed rather than
being accepted as refresh. V1 implements neither path; it accepts static credentials only.

## 4. Provisioning and activation

The official or a curated downstream MCP registry may be used only as a catalog in the operator
provisioning experience. Registry metadata is untrusted discovery input: it may prefill a proposed
package coordinate or remote URL, but it cannot create, install, enable, connect, update, or approve
a profile. The operator must pin the concrete executable/package version or HTTPS origin, secret
reference, allowlist, isolation policy, and limits through the same provisioning flow below.
Neither the agent/model nor the Gateway data plane queries a registry in v1. This catalog is
distinct from ACP publication work under `P11-FEAT-REGISTRY`; future MCP discover-and-connect is
owned by `P11-FU-14`.

The profile state machine is:

```text
ABSENT --> PENDING_REGISTRATION --approval + restart--> ACTIVE
              ^                                           |   |
              | re-registration                           |   +--disable--> DISABLED
              +---------------- STALE <-------drift--------+                    |
              ^                                                                |
              +----------------re-enable + new revision-------------------------+
```

`STALE` re-enters `PENDING_REGISTRATION` through registration discovery and replacement approval.
Re-enabling a disabled profile also creates a new revision and returns to
`PENDING_REGISTRATION`; neither path can jump directly to `ACTIVE`.

1. The operator creates a `PENDING_REGISTRATION` profile. A short-lived HMAC-signed
   `GatewayChildManifest` carries that profile into a Gateway launch.
2. Registration discovery carries `profile_id` and `profile_revision` only. It cannot carry a
   manifest hash because discovery supplies the descriptors from which the manifest is built.
3. The Gateway validates `server/discover` for protocol `2026-07-28`, exhausts bounded
   `tools/list` pagination, filters tools to the upstream allowlist, validates definitions, and
   returns the sanitized set plus unmatched allowlist entries.
4. The agent scans the descriptors, constructs the versioned canonical manifest, derives effect
   classes, and obtains human approval.
5. Approval is persisted in the durable agent approval store. The next HMAC-signed Gateway launch
   carries the same revision as `ACTIVE` with the approved manifest hash. V1 therefore accepts
   restart-to-activate and introduces no live activation endpoint.
6. Refresh and invocation carry the full binding pair. Drift puts the profile into a fail-closed
   reapproval state; activation of the replacement hash again requires restart.

The Gateway startup manifest is a bootstrap boundary, not a runtime control channel. A new profile
therefore requires a pending launch and an activation restart. This is acceptable for static,
operator-preprovisioned v1 profiles.

## 5. Discovery contract

The agent-facing Gateway surface is typed rather than an arbitrary MCP-method proxy:

- `POST /v1/tools/mcp/discover`
- `POST /v1/tools/mcp/call`

`discover` has two modes:

- **registration:** `profile_id` plus `profile_revision`; allowed only for a pending or stale
  profile; and
- **refresh:** `profile_id`, `profile_revision`, and `manifest_hash`; allowed for an active profile.

The agent-facing route name is not the MCP `server/discover` method. Inside the Gateway, a remote
HTTP profile requires `server/discover` support for `2026-07-28` and the tools capability before
`tools/list`; absence produces the narrow `mcp.protocol_version_unsupported` disposition and never
falls back to initialization. A mandatory-containerized stdio profile first probes with
`server/discover`, selects a mutually supported modern version when possible, and otherwise may use
the legacy initialization handshake before `tools/list`. Server identity, instructions,
capabilities, cache metadata, descriptors, cursors, and tool annotations are all untrusted input;
self-reported server identity is never used for security or namespacing.

The Gateway allowlist uses upstream tool names. The agent manifest and planner use
`profile_id.tool_name`. The `profile_id` scopes the deterministic join. Discovery reports any
provisioned allowlist entry that matched no upstream tool so a typo is operator-visible.

Before descriptors cross the boundary, the Gateway:

1. excludes every tool outside the upstream allowlist;
2. rejects malformed definitions;
3. for Streamable HTTP, excludes definitions with invalid `x-mcp-header` values;
4. never enables `Mcp-Param-*` argument mirroring in v1; and
5. adds the profile-ID namespace without using `serverInfo.name` for disambiguation.

`tools/list` pagination is atomic from the approval system's perspective. The Gateway follows
`nextCursor` until absent, while enforcing provisioned page-count, total-tool, descriptor-byte, and
elapsed-time bounds. A repeated or malformed cursor and a malformed/incomplete page are integrity
failures: they reject the discovery and no prefix can become an approvable manifest. A transient
transport failure retries through the existing capped policy; an exhausted capacity bound produces
a narrow `mcp.discovery_budget_exceeded` disposition and no manifest. Bounds are raised through
operator provisioning when a complete discovery needs them. V1 retries a complete scan rather than
persisting a cursor checkpoint; resumable cursor checkpoints belong to `P11-FU-13`. Allowlist
filtering and definition validation occur on every page before any descriptor crosses to the agent.

"Sanitized" means transport and secret configuration is excluded while upstream descriptor text
is passed verbatim. The Gateway does not rewrite descriptions. The agent's existing scanner must
inspect the exact upstream text.

"Canonical" means a single schema-versioned field set, deterministic ordering, UTF-8 encoding,
and canonical JSON serialization shared by both processes. The canonicalization version is part of
the profile schema; changing it changes the manifest hash and requires reapproval.

Discovery is attempted at every agent-session start and before an invocation when the last
successful discovery is older than the effective freshness interval. That interval is the lesser
of `mcp.discovery_max_age_seconds` (default 300) and a valid upstream `ttlMs`; absent or invalid
`ttlMs` cannot extend the local maximum. Cache entries are always partitioned by profile revision
and credential binding even when a server declares a broader `cacheScope`. A successful refresh
whose canonical hash differs is detected drift and moves the profile to the fail-closed reapproval
path. A transient or capacity-limited refresh failure leaves the last approved, still-bound
manifest callable with `freshness: stale_marked` recorded on the call and audit trail; it does not
disable the profile merely because the check could not complete. The per-call binding comparison
detects profile changes immediately, while upstream descriptor drift is detectable only at a
successful refresh because v1 opens no `subscriptions/listen` stream.

## 6. Invocation and result flow

A call request carries run/session/request context, `profile_id`, `profile_revision`,
`manifest_hash`, upstream tool name, and arguments. The agent translates the approved namespaced
name to `(profile_id, upstream tool name)`.

Before dispatch:

1. the agent applies permission, approval, manifest, scope, effect, and allowed-tool checks;
2. the Gateway authenticates the bearer secret;
3. the Gateway checks active state, revision, approved hash, last-known freshness state, upstream
   allowlist, resource policy, and budget policy; and
4. the Gateway rechecks the binding immediately before transport execution.

Tool arguments are the only agent-originated payload sent to an MCP server. No system prompt,
conversation history, policy text, approval record, or other instruction content is transmitted.
Arguments pass the existing redaction boundary before dispatch.

Only `text` and `structuredContent` result data is promoted as normal tool output.
`structuredContent` is validated agent-side against `outputSchema` when present. `resource_link`
and embedded-resource blocks remain inert untrusted data. Image and audio blocks are discarded
with an explicit typed note and are never decoded or persisted.

All accepted result content remains untrusted input. It cannot modify policy, approve tools,
trigger a resource fetch, execute code, or become trusted manifest content.

### 6.1 Condition for opening elicitation after v1

The current method/result-type/content denial remains intact. A later `P11-FU-13` amendment may
open it only as one coordinated control:

1. **Method:** the client advertises the exact elicitation mode only after a server-attributed,
   rate-limited operator UI exists. V1 advertises none.
2. **Result type:** `input_required` becomes a durable hold tied to the initiating profile, tool,
   request, binding pair, round count, and deadline; it never becomes a planner-authored question
   and never triggers an automatic retry.
3. **Content:** the operator sees the requesting profile/server, purpose, exact form schema or URL
   origin, and explicit accept/decline/cancel choices. Form mode cannot request secrets; URL mode
   requires an approved HTTPS origin. Accepted form content is schema-validated and redacted before
   return. Opaque `requestState` is treated as untrusted and may only be echoed inside the bounded,
   integrity-protected continuation.

Until all three open together, any elicitation request embedded inside a tool result is denied
call-scoped and the original call is not redispatched; the profile and its approved binding remain
active.

## 7. Transport profiles, connection lifecycle, and honest isolation

Provisioning and connection lifecycle are separate axes. Profile state decides whether a transport
may be opened. A runtime socket or child process for an already-active revision cannot create,
activate, re-enable, or change that profile and is not evidence of approval.

MCP `2026-07-28` has no protocol initialization session or client ping; external MCP logging is
also deprecated and closed. Streamable HTTP is
request-scoped and carries version/client/capability metadata on every request. A stdio child is
opened lazily by the Gateway only after profile admission and is closed on disable, stale/revision
change, idle or duration limit, policy breach, transport corruption, or Gateway shutdown. Reusing a
bounded stdio child does not create resumable MCP session custody; application state must travel as
explicit tool arguments/handles.

### 7.1 Stdio

The stdio executable is arbitrary operator-approved code. V1 does not launch it on the Gateway
host: every stdio profile runs through Docker from an immutable image digest, never an image tag.
This is the containment condition for permitting discovery-first modern/legacy negotiation on
stdio; it is not an HTTP authorization downgrade. V1 separates controls into three tiers.

**Enforced v1 controls:**

- Docker-only launch from `repository@sha256:<digest>`; a tag-only or mutable image reference is
  rejected at provisioning;
- no host bind mount, device passthrough, or Docker-socket mount;
- a newly constructed Docker-client environment containing only the selected profile credential;
- safe credential projection with `docker run --env NAME`, never `--env NAME=value`, so the value
  is neither command-line data nor logged command text;
- no model-provider key, Gateway bearer secret, other MCP credential, or telemetry credential;
- default 30-second call duration and 1 MiB response limit;
- bounded read loops; and
- deterministic process-tree termination.

**Platform work requiring platform evidence:**

- subprocess-count confinement using a Windows Job Object and an appropriate Linux/WSL2 process
  limit. The claim is unavailable until real Windows and Linux/WSL2 evidence passes.

**Accepted v1 residual:**

- Docker daemon trust, image supply-chain trust, and any egress permitted by the provisioned
  container-network policy remain material residuals. The Docker boundary prevents a stdio process
  from inheriting the Gateway host identity or host filesystem through v1 mounts; it does not make
  MCP roots a security boundary or claim protection from a compromised daemon/image.

Relaxing a limit or enforced container policy changes the isolation policy, mints a revision, and requires
reapproval.

The target protocol has no general server-to-client request channel. An `InputRequiredResult` is
handled only by the v1 fail-closed rules above. Unknown notifications or protocol messages are
logged and ignored or terminate the affected transport according to the existing failure taxonomy;
they are never treated as instructions.

### 7.2 Streamable HTTP

The profile pins scheme, origin, path policy, static header mapping, TLS policy, duration, and
response-size limits. HTTPS is required except for an explicitly provisioned loopback endpoint.
Redirects are disabled, so credentials cannot cross origins. V1 never opens a standalone HTTP
GET/SSE channel or subscription. Each POST carries the `2026-07-28` protocol header and required
method/name mirrors and may return SSE for that request only, bounded by the same 30-second and
1 MiB defaults.

Dynamic OAuth acquisition, refresh, token storage, and client registration are excluded from v1.
`P11-FU-12` must implement the refresh-versus-rotation discriminator in §3.3, audience/issuer/scope
validation, least-privilege scope selection, and Gateway-only token custody before an OAuth profile
can be admitted.

## 8. MCP accounting and budgets

Existing `GatewayUsage`, `ProviderUsage`, and their non-null `billing_units`/`cost_usd` validation
remain unchanged. MCP uses an additive `MCPUsageRecord` and MCP-specific wire envelope so an
unknown cost never relaxes or contaminates the shipped settled-usage contract.

Tool definitions are also recurring model-input cost. Before each model request, a context-admission
gate may expose only an operator-selected subset of already-approved, namespaced descriptors and
must enforce configured descriptor-count and UTF-8-byte ceilings. It records the admitted identities,
count, and bytes beside the model request; provider-reported input usage remains the billing source,
and Optimus must not estimate per-descriptor tokens post hoc. V1 does not claim semantic tool search
or automatic per-turn selection. Those optimizations, and any code-execution mode, belong to
`P11-FU-15`.

Each MCP row has one attribution state:

- `settled`: a versioned profile adapter parsed authoritative upstream billing units and cost;
- `explicit_zero`: the operator provisioned the profile as free of per-call external charge; this
  is a revision-bound declaration and does not depend on a server volunteering cost metadata; or
- `unavailable`: no authoritative monetary data exists, so billing units and cost remain absent.

An unavailable cost never contributes zero to displays or totals. The ledger displays known spend
and an unattributed-call count separately. Strict-dollar-budget runs admit an operator-declared-free
`explicit_zero` profile, but deny an `unavailable` profile before execution unless the revision-bound
profile policy explicitly permits unattributed spend. The typed denial is
`mcp.budget.unattributed_spend_denied`. An upstream claim of free usage cannot by itself select
`explicit_zero`.

Every attempt records Gateway/run/session/request IDs, profile ID and revision, namespaced and
upstream tool names, transport, provider request ID when present, request/response bytes, duration,
disposition, attribution state, and authoritative monetary fields when available. Existing
redaction applies to parameters, results, errors, and identifiers.

The contract change requires a consumer sweep across persistence, current-run budget enforcement,
display, reconciliation, telemetry, Redis schemas, evidence ledgers, golden tasks, and Test
Strategy §8A. Consumers of existing usage rows must remain byte-compatible.

If accounting persistence fails after upstream execution, the result is withheld and the run is
held until the same `gateway_request_id` can be persisted. Recovery retries persistence only; it
must not redispatch the upstream tool call.

## 9. Errors, indeterminate outcomes, and retries

Typed MCP errors extend the existing failure taxonomy and `RetryPolicy`; they do not create a
parallel retry engine. They distinguish authentication, inactive profile, stale binding, allowlist denial,
invalid descriptor, deferred-capability request, result-schema failure, unsupported content,
resource-limit breach, budget denial, accounting failure, transport failure, and upstream failure.
Safety failures stay closed; missing optional capability, older stdio protocol, brief transport
unavailability, and absent optional cost metadata produce a call- or feature-scoped disposition,
retry, or negotiated path rather than disabling an otherwise valid profile.
Profile hash or revision mismatch maps to `mcp.manifest_hash_changed`.

`tools/call` is never automatically retried in v1 because MCP provides no general idempotency
guarantee. Timeout or connection loss after dispatch is an `indeterminate` outcome.

The guard against model-level redispatch is effect-aware:

- a read-only-classed tool may be invoked again after an indeterminate outcome; and
- a side-effecting-classed `(profile_id, tool)` is held by `PreToolGuard` until the operator
  acknowledges the indeterminate prior attempt.

The indeterminate-hold record is durable in the approval store and survives agent-session and
agent-process restart. Acknowledgment authorizes a new attempt; it does not assert that the earlier
attempt failed.

Only `server/discover` and `tools/list` within registration/refresh discovery may retry transient
failures. They use the existing exponential-backoff/jitter policy with a maximum of three attempts
and restart a complete scan; v1 does not retain cursor checkpoints. Permanent validation,
authorization, pagination-integrity, and policy failures never retry. User-visible errors carry a
safe typed disposition, whether retry is allowed, and the operator action required; they never
include credentials, raw authorization challenges, or unredacted server text.

## 10. Threat model and residuals

V1 protects against accidental or buggy agent behavior, repository-supplied MCP autoload, prompt
injection in descriptors/results, cross-profile credential projection, direct-route widening past
the provisioned allowlist, stale approvals after profile changes, and silent unknown-cost reporting.

### 10.1 OWASP architectural reference and MCP control mapping

Guardrails v1.1 already cites the OWASP LLM Top 10, and Plan 6.5 already implements the local
descriptor/configuration cage. The two voices below are deliberately separate.

| Voice and owner | OWASP 2025 risk | Architectural reference observation |
|---|---|---|
| `REFERENCE — Cross-cutting` | LLM01 Prompt Injection | Untrusted instructions can enter through tools, retrieved content, configuration, user input, and other context-bearing integrations; the trust boundary is broader than MCP |
| `REFERENCE — Cross-cutting` | LLM02 Sensitive Information Disclosure | Credential custody, prompt/context minimization, logging redaction, and downstream data sharing are related disclosure surfaces across the product |
| `REFERENCE — Cross-cutting` | LLM03 Supply Chain | Models, packages, plugins, skills, MCP servers, manifests, and registries are supply-chain inputs whose provenance and update paths affect trust |
| `REFERENCE — Cross-cutting` | LLM05 Improper Output Handling | Model and tool output becomes dangerous when downstream consumers execute, dereference, render, or promote it without validation |
| `REFERENCE — Cross-cutting` | LLM06 Excessive Agency | Functionality, permission, autonomy, and spending authority are separate dimensions that benefit from least privilege and explicit approval |
| `REFERENCE — Cross-cutting` | LLM07 System Prompt Leakage | Any integration that forwards hidden instructions or history to another process or service creates a disclosure path |
| `REFERENCE — Cross-cutting` | LLM10 Unbounded Consumption | Model context, retries, tool calls, result sizes, long-lived work, and third-party-initiated inference can all consume bounded resources |

These reference rows are architectural guidance, not requirements, acceptance criteria, or claims
that controls are implemented. They use no normative keyword and requirements extraction must not
assign them to `P11-FEAT-GATEWAY-MCP`.

| Voice and owner | MCP-specific normative control | Existing seam extended |
|---|---|---|
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Gateway allowlist filtering precedes descriptor crossing; the agent scans exact descriptor text; every result remains untrusted | `ConfigTrustScanner`, `MCPTrustRegistry`, Test Strategy §14.4 |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Per-profile credentials remain Gateway-only; arguments are the only agent-originated upstream payload; logs/results/errors are redacted | secret-free agent and existing redaction boundary |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Profiles are operator-preprovisioned and pin package/endpoint; catalog metadata is an untrusted proposal only | no-autoload and manifest-hash reapproval |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Structured output is schema-validated; resource content is inert; no output auto-fetches, executes code, or changes policy | pre-tool/result validation boundaries |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Split allowlists, binding freshness, resource admission, and budget admission compose with agent approval/scope/effect checks | human approval, `allowed_tools`, `permission_scope`, effect class |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | No system prompt, history, policy, or approval data crosses to an MCP server | existing prompt redaction boundary |
| `NORMATIVE — P11-FEAT-GATEWAY-MCP` | Pagination, descriptor context, duration, bytes, unknown cost, and MCP usage are bounded and attributed | current-run budget and settled usage contracts |

V1 explicitly does not claim protection from:

- a compromised Gateway process;
- a compromised Docker daemon or a malicious digest-pinned image;
- a local process that has both the shared bearer secret and the public binding values bypassing
  agent-only scope/effect checks while remaining subject to Gateway profile state, freshness,
  binding, allowlist, resource, and budget checks; or
- upstream drift inside the configured discovery-freshness window or while a refresh is
  stale-marked after a recoverable refresh failure.

These residuals are acceptable only for the current strict-loopback, single-operator Phase 1
deployment. Multi-user, off-box, or hosted deployment requires a new threat model.

## 11. Alternatives considered

### Gateway-centralized trust — rejected

Moving approval and effect/scope authority to the Gateway replaces the shipped Plan 6.5 cage and
makes the data-plane process the sole decision and execution authority.

### Signed per-call approval capabilities — rejected for v1

Short-lived signed capabilities could prove that the agent gate approved a call, but would add
signing-key lifecycle, replay handling, and new trust vocabulary for a loopback single-operator
deployment. This is a decision record, not a speculative follow-up. A future multi-user or off-box
design may reconsider it under a concrete threat model.

### Runtime activation endpoint — rejected for v1

A one-shot signed activation request is viable but adds a new live authenticated surface and replay
analysis. Restart-to-activate reuses the existing startup boundary.

## 12. Required evidence

| Claim | Required evidence |
|---|---|
| Agent holds no upstream MCP credential | Process-specific environment, keyring/config, log, and egress scans with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the agent |
| Direct bearer caller cannot widen tools | Real Gateway tests calling MCP routes directly and proving Gateway allowlist denial |
| Profile changes force reapproval | Tests for credential, endpoint, command, allowlist, isolation, limit, and attribution-policy changes; all must map to `mcp.manifest_hash_changed` |
| Rotation property survives migration | Successor to `test_launch_env_change_forces_reapproval_without_logging_secret_values` proving Gateway-side credential rotation breaks the bound pair without exposing secret-derived data |
| Bootstrap is satisfiable | Pending registration discovery without a hash, operator approval, restart-to-activate, then full-pair refresh/call |
| Descriptor drift is bounded | Session-start refresh and 300-second expiry; detected drift enters reapproval, while a recoverable refresh failure serves only the prior bound manifest with `freshness: stale_marked` recorded |
| Tool namespace is collision-safe | Two profiles exposing the same upstream name remain distinct; `serverInfo.name` is ignored for disambiguation |
| Deferred protocol features fail closed | `input_required`, roots, sampling, elicitation, external logging, subscriptions, invalid methods, and auto-dereference attempts are denied without changing Optimus audit logging or profile state |
| HTTP header mirroring is absent | Invalid `x-mcp-header` definitions are excluded and no valid annotation produces `Mcp-Param-*` |
| Stdio credential isolation is real | Docker image is digest-pinned, no host mounts/devices/socket are admitted, and `docker run --env NAME` projects only the profile credential without placing its value in command text |
| Resource controls are symmetric | Stdio and HTTP duration/byte limits, POST-SSE bounds, process termination, and platform-specific process-limit evidence |
| Unknown spend is never zero | MCP-specific rows, strict-budget denial for `unavailable`, revision-bound operator-declared-free `explicit_zero`, unattributed display/reconciliation, and unchanged legacy usage consumers |
| Indeterminate mutation is not silently repeated | Side-effecting model re-invocation holds for acknowledgment; read-only re-invocation remains allowed |
| Accounting failure cannot escape budget control | Result withholding and persistence-only recovery using the same Gateway request ID |
| Protocol interoperability is real | Independently authored MCP stdio and Streamable HTTP servers drive live evidence; fakes remain unit-tier only |
| Protocol generation is correct | Remote HTTP requests use `2026-07-28` per-request `_meta`, `server/discover`, `tools/list`, and `tools/call` with no initialization fallback; containerized stdio proves discovery-first negotiated/legacy behavior without non-tools capabilities |
| Context7 compatibility dependency is honest | A live, Gateway-originated authenticated probe of the configured Context7 endpoint proves `2026-07-28` plus tools support before any claim of Context7 reachability; unsupported/indeterminate evidence leaves only its HTTP capability unavailable with `mcp.protocol_version_unsupported` |
| Pagination is complete or absent | Multi-page `tools/list` fixtures prove full ordered accumulation; repeated/malformed cursors reject discovery without a prefix, while transient failures retry and capacity exhaustion returns a narrow no-manifest disposition |
| Registry cannot become autoload | Catalog metadata can only prefill a pending operator proposal; agent/model/data-plane registry lookup, install, connect, update, activation, and trust inheritance are denied |
| Provisioning and connections stay separate | Opening/reusing/closing a transport cannot change profile state; disable/stale/revision change terminates the affected stdio child and blocks later HTTP requests |
| Elicitation remains triply closed | No capability advertisement; call-scoped method and `input_required` denials; no schema/URL/request-state content reaches planner or continuation logic, and the profile remains active |
| Sampling cannot spend or inject | Sampling input requests produce no model call, budget reservation, provider usage, MCP usage, server response, or inherited context in v1 |
| Descriptor context is cost-bounded | Only the operator-selected approved subset reaches a model request; count/byte ceilings and admitted identities are recorded while provider input usage remains authoritative |
| MCP errors extend existing retry | Typed MCP failures flow through the existing failure taxonomy/`RetryPolicy`; only `server/discover` and `tools/list` transient failures retry, capped at three attempts |
| OWASP voice and ownership are non-ambiguous | Every generalized row is labelled `REFERENCE — Cross-cutting` and produces no acceptance criterion; every normative MCP row is labelled `NORMATIVE — P11-FEAT-GATEWAY-MCP` and maps to a named test |
| Exclusion provenance is honest | The local-Gateway v3 explicit reaffirmation and incomplete Guardrails v1.1 change log are cited; the hosted-premise causal hypothesis remains labelled unconfirmed |

Windows Job Object evidence and Linux/WSL2 process-limit evidence are both required before claiming
subprocess-count confinement. The normal Phase 1 release gate remains owned by the Plan 9.6 live
verification plan.

## 13. Deferred custody and non-conflation

Five named follow-ups are required; they are custody identities, not speculative implementation
plan numbers:

1. **`P11-FU-12` — MCP OAuth 2.1 lifecycle:** acquisition, client registration, secure token
   storage, refresh, audience/issuer/resource validation, step-up scopes, and the §3.3
   refresh-versus-rotation discriminator.
2. **`P11-FU-13` — Deferred MCP capabilities and long-lived interaction:** prompts, resources,
   elicitation, sampling, external logging, completion, subscriptions, roots, tasks/progress,
   advanced connection state, resumable discovery cursor checkpoints, and model-generated code execution. Sampling must retain its
   separate §2.2 threat and accounting gate; it is not satisfied by generic capability enablement.
3. **`P11-FU-14` — MCP registry discover-and-connect:** runtime catalog query, installation,
   update, trust scoring, profile creation, and connection automation. This identity is unrelated
   to ACP publication owner `P11-FEAT-REGISTRY`.
4. **`P11-FU-15` — MCP tool-search and context minimization:** semantic search, automatic per-turn
   descriptor selection, prompt-cache optimization beyond deterministic ordering, and any future
   sandboxed code mode.
5. **`P11-FU-16` — Reverse research-to-documentation freshness gate:** detect research or
   implementation learning that authoritative docs never capture, without converting explicitly
   labelled architectural reference into phantom normative requirements.

Roots, sampling, and external MCP logging are excluded in part because MCP `2026-07-28` deprecates
them; roots also are not an access-control boundary, while sampling initiates model spend and prompt
flow in the reverse direction. External MCP logging is not an input to, substitute for, or control
over Optimus audit logging. OAuth is excluded from v1 implementation because acquisition and refresh require the
new discriminator and token threat model. Elicitation and the other capabilities are excluded
because the shipped trust vocabulary and UX are tools-only. Registry autoconnect is excluded
because catalog metadata is neither code trust nor operator approval. Semantic tool search is
excluded because no selection seam exists today. Generalized OWASP research lands now as
non-normative `Cross-cutting` reference; only the reverse-direction freshness mechanism remains
deferred because it is a process feature, not part of MCP brokering.

Gateway-brokered MCP is not ACP client-supplied `mcpServers` (`P11-FU-9`) and is not ACP
session-resume/session-load (`P11-FEAT-ZED-RESUME`). This amendment implements or closes neither.

## 14. Documentation and publication scope

After operator approval, a separate plan will redline and publish:

- HLD v2.16 -> v2.17;
- LLD v2.39 -> v2.40;
- Guardrails v1.1 -> v1.2;
- Test Strategy v1.5 -> v1.6; and
- the Plan 11 milestone charter.

The publication follows `docs/sources/local-gateway-architecture-v3/`: editable changed-page
Markdown and SVG, a pinned splice manifest, carried-page preservation, rebuilt PDFs, changed-page
manifests, visual inspection, machine validation, completeness audit, and SHA-256 recording.

The publication plan must also update the authoritative section map, consolidated open-work pool,
roadmap, and README wherever their current-state claims become stale. Those freshness edits are
reviewer-enforced derivative work, not silent expansion of an implementation lane.

## 15. Approval record

The earlier reviewer sign-off was withdrawn when rulings 8-15 expanded and reopened the scope. This
redraft preserves the prior split-authority, rotation, tools-only, isolation, and accounting rulings
while adding the position-level scope above. It must receive a fresh reviewer sign-off before the
operator can approve publication execution. Approval of this document will authorize the detailed
documentation/publication plan, not MCP runtime implementation, commit, push, or merge.
