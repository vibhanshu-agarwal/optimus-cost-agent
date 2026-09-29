# Plan 11.8: P11-FEAT-GATEWAY-MCP Design Specification

**Frozen design-body SHA-256:** `1eb6cb626e1ed74e83f9ce81b048cb68da8105a1468f8f12272620bf2325f911`

The digest above is the SHA-256 of the UTF-8 LF-normalized file body after removing this header
line and its trailing line ending. It is recomputed and replaced after drafting; the header is not
part of the hashed body.

**Status:** Draft for operator/reviewer approval. This document authorizes no implementation-plan
execution, source/test mutation, PDF regeneration, charter mutation, commit, push, or release claim.

**Stable feature:** `P11-FEAT-GATEWAY-MCP`.

**Plan number:** 11.8, assigned as the next unused Plan 11 single-decimal slot at pickup.

**Branch:** `agent/codex/plan-11-8-p11-feat-gateway-mcp`, based on `origin/main` at
`662e88666093bb93e51d35ed25f8dd7bc1159ce0` in the existing worktree.

**Scope posture:** This is the feature-slice design specification only. The implementation plan is
intentionally deferred until this written design receives operator/reviewer approval.

## 1. Frozen authoritative source set

The four amended PDFs are the normative source set for this feature. The Plan 11 charter is the
scope and custody authority. The PDF SHA-256 values below are over the committed PDF bytes; the
Git-blob IDs provide the committed-object identity. Section and page references use the printed
PDF page number, not a source-file line number.

| Source | Committed path | PDF SHA-256 | Git blob | Frozen sections/pages used here |
|---|---|---|---|---|
| HLD v2.17 | `docs/Optimus-Cost-Agent-Architecture-v2.17.pdf` | `A21BDB01BC737FA3D8EBFFBA8B8B7DF96C65101812E17F31C3C7324368D15024` | `f48c0ea56a842eebed16fc7a5e43decf01648a0f` | §5A p.3; §§6-7 pp.4-5; §11 p.10; §11.1 p.11; §§11A-12 p.12 |
| LLD v2.40 | `docs/Optimus-Cost-Agent-LLD-v2.40.pdf` | `0329AEF8B5392E05DDBB19AC3F76F3CE7F4FE3C4B728AEF6CBFC4DE84B324D03` | `0086e9bfd21ddf4229ef5d804614bfa9b16116ff` | §§0/0A pp.2-5; §0D p.3; §§9C-9C.4 pp.26-29; §9D p.30; §§9E-9E.1 pp.31-32; §§11-11A pp.36-38; §12B p.39 |
| Guardrails v1.2 | `docs/Optimus-Cost-Agent-Agent-Execution-Guardrails-and-Workflow-Strategy-v1.2.pdf` | `461A720FA28576523C87C2F2F89EE1FC52C99971E51ACC22EDC85E8C375A7070` | `cdd4168732d15397ebac4b11d80e7848dfb0d3ac` | §5 pp.8-9; §7.3 p.10; §8.3 p.11; §§9-10.2 pp.12-13; §11.2 p.14; §13 p.16 |
| Test Strategy v1.6 | `docs/Optimus-Cost-Agent-Test-Strategy-v1.6.pdf` | `B435E55687116BD7C4D7E78B48E50D8DA9ED0801575B7B5485F262D35C1B31A4` | `3a07c096ce54e654ad9796fa8d90fa5f14f8c71c` | §§1/3 pp.2-3; §6 p.5; §7 p.6; §8 pp.7-8; §§9-10 pp.9-10; §11 p.10; §12 p.11; §13 p.12; §14.10 p.14 |

The ratified scope authority is `docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md`
(Git blob `b10e1c884f06f24778969afbbe6e5cde2fb5a6a8`). The feature statement is in the
`P11-FEAT-GATEWAY-MCP - Gateway MCP tool-call brokering` section, especially charter lines
112-122, and the capability partition/revised map at lines 31-40 and 53-60. The charter keeps
`P11-FU-3` as the completed route/typed-contract publication gate and explicitly distinguishes
this feature from client-supplied ACP `mcpServers` and ACP session resume.

Supporting rationale is not a second authority. It is used only to explain why the frozen choices
are shaped as they are:

| Supporting document | Git blob | Use |
|---|---|---|
| `docs/superpowers/specs/2026-08-05-mcp-gateway-brokering-architecture-amendment-design.md` | `56fe89f9dcf37b47ffca4fb330f6ccd6f98fae6d` | Settled split-authority, static-profile, tools-only, transport, result, accounting, deferred-custody, and Context7 rulings. |
| `docs/superpowers/reports/2026-08-05-mcp-gateway-architecture-document-redline-draft.md` | `c2012bda1a46734784ec19a2eedfb9a98320a593` | Publication/redline rationale and exact amendment traceability. |
| `docs/superpowers/reports/2026-08-05-mcp-gateway-security-best-practices-reference.md` | `c4b0a6729b9cee2a9fd426786c62a72d45a56232` | Non-normative security rationale for preserving the local trust boundary, namespacing, least privilege, and untrusted-result treatment. |

The structural precedent is `docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md`
(Git blob `97ed2ecc4410ee37c7c0f7e287625588b6883b6e`).

### 1.1 Source-fidelity rules

- HLD, LLD, Guardrails, and Test Strategy are authoritative where this design makes a requirement
  claim. A conflict between them blocks implementation planning.
- The amendment and redline documents explain settled rulings but cannot widen the ratified charter
  scope or create new acceptance criteria by implication.
- MCP route names and typed components are taken from LLD v2.40 §0D p.3 and §0C p.3: `POST
  /v1/tools/mcp/discover`, `POST /v1/tools/mcp/call`, `MCPProfileRegistry`,
  `MCPDiscoveryBroker`, `MCPDiscoveryPaginator`, `MCPInvocationBroker`, and
  `MCPConnectionManager`.
- Implementation must re-verify all four PDF digests and the charter blob before its first source
  mutation. A digest mismatch is a stop-and-review condition.

## 2. Goal

Deliver a bounded, authenticated MCP tools broker behind the existing loopback Optimus Gateway.
The agent remains a one-key client with only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; the
Gateway owns static upstream credential references, operator-provisioned profile state, transport
connections, protocol handling, usage attribution, and controlled upstream egress.

The agent-side `MCPTrustRegistry`, `ConfigTrustScanner`, descriptor exposure guard, and
`PreToolGuard` remain active and authoritative for human approval, descriptor trust, namespaced
allowed tools, permission scope, and effect class. The Gateway independently enforces the
operator-owned profile, revision/binding pair, upstream allowlist, resource policy, and budget
admission before it contacts an upstream MCP server. Both gates are required.

V1 exposes only typed discovery and call operations over two transports: remote Streamable HTTP and
Docker-contained stdio. It accepts complete tools discovery and complete result content as
untrusted data, persists an MCP-specific usage record before releasing an accepted result, and
fails closed on safety, integrity, policy, accounting, or containment failures.

## 3. Current evidence and problem statement

The current Gateway already has a typed tool route boundary in
`src/optimus_gateway/server.py`, `tool_models.py`, `tool_policy.py`, `tool_state.py`, and
`tool_handlers.py`. The agent already has a generic authenticated Gateway client in
`src/optimus/gateway/client.py`, local MCP trust/runtime enforcement in
`src/optimus/mcp/runtime.py`, and the lower-level `MCPTrustRegistry` in
`src/optimus/guardrails/mcp_trust.py`. These are existing seams to extend, not systems to replace.

The missing capability is the Gateway-owned MCP route and broker contract. Without it, an approved
agent-side MCP descriptor has no typed path to a Gateway-held profile credential or a Gateway-side
transport. The missing path creates several risks if implemented as an ad hoc proxy:

- upstream credentials could be introduced into the agent process;
- a bearer caller could bypass the local approval record and widen beyond the operator allowlist;
- descriptor pagination could expose a partial manifest or accept a cursor-integrity failure;
- HTTP compatibility could silently fall back below the required 2026-07-28 floor;
- stdio could execute arbitrary host processes instead of a digest-pinned Docker child;
- result content, resource links, or server instructions could be treated as trusted instructions;
- an indeterminate side-effecting call could be silently redispatched; and
- unknown or failed accounting could release a result or reinterpret unavailable cost as zero.

The existing `P11-FEAT-GATEWAY-TOOLS` routes and shared Gateway usage contract remain separate.
MCP uses the additive `MCPUsageRecord` contract defined by LLD §9E p.13; it does not alter
`GatewayUsage`/`ProviderUsage` or the web/package/advisory route contracts.

## 4. Scope boundary

| In scope for P11-FEAT-GATEWAY-MCP | Explicitly out of scope and named custody |
|---|---|
| `POST /v1/tools/mcp/discover` and `POST /v1/tools/mcp/call`, with typed request/result/disposition contracts. | Prompts, resources, elicitation, completion, subscriptions, tasks/progress, roots, sampling, external MCP logging, and long-lived interaction: `P11-FU-13`. |
| Tools-only method/result/content handling; `server/discover`, `tools/list`, and `tools/call` only. | Resumable discovery cursor checkpoints and background pagination: `P11-FU-13`. |
| Operator-provisioned static credential profiles only, in Gateway-owned custody. | OAuth 2.1 acquisition, dynamic registration, refresh, token storage, step-up scopes, and lifecycle: `P11-FU-12`. |
| Remote Streamable HTTP with the 2026-07-28 protocol floor and Docker-contained stdio with discovery-first modern/legacy negotiation. | HTTP legacy initialization fallback, standalone GET/SSE, subscriptions, and protocol-session resume. Stdio negotiation is the only legacy path. |
| Separate agent `MCPTrustRegistry` and Gateway `MCPProfileRegistry` with split authority and a required two-gate call. | Redesigning `src/optimus/mcp/runtime.py`, weakening local MCP trust, or replacing `PreToolGuard`/`ConfigTrustScanner`. |
| Complete bounded discovery, namespace-safe descriptors, static upstream allowlists, and typed untrusted results. | Catalog lookup, runtime discover-and-connect, automated install/update, profile autoload, or registry trust inheritance: `P11-FU-14`. |
| Deterministic operator-selected descriptor subset/count/UTF-8-byte admission accounting. | Semantic per-turn tool selection, context minimization, and code-mode execution: `P11-FU-15`. |
| Additive `MCPUsageRecord`, attribution states, budget admission, persistence-before-release, and indeterminate-call handling. | Changing existing model/tool `GatewayUsage`, credit/USD migration, cross-run wallet policy, or a second accounting path. |
| Named Context7 remote compatibility acceptance dependency. | Claiming Context7 support without a Gateway-originated authenticated probe of the configured real endpoint proving 2026-07-28 discovery/version/tools support. A fake or substitute server is insufficient. |
| Gateway-brokered MCP from operator profiles. | Client-supplied ACP `mcpServers` (`P11-FU-9`), ACP session resume (`P11-FEAT-ZED-RESUME`), and ACP registry publication (`P11-FEAT-REGISTRY`). |

No catalog, OAuth, semantic selection, arbitrary-method proxy, model sampling, server-initiated
prompt flow, or transport-resume behavior may be inferred from a successful tools call.

## 5. Design decisions

### 5.1 Typed Gateway routes and contract ownership

The agent-facing routes are exactly:

- `POST /v1/tools/mcp/discover`
- `POST /v1/tools/mcp/call`

They authenticate with the existing Gateway bearer check. They are not a generic method proxy and
must not accept an arbitrary MCP method name. Inside the Gateway, the only permitted upstream
method set is the tools-only set described in §5.3.

The shared wire contracts live on the agent side beside the existing Gateway tool models, while
the independently deployable `optimus_gateway` package owns a self-contained wire-equivalent copy;
the Gateway package must retain its zero-`optimus.*` import boundary. Both copies serialize the
same field names, enum values, canonical ordering, and typed dispositions.

`MCPDiscoverRequest` has:

- `profile_id` and `profile_revision` for registration;
- `manifest_hash` additionally required for refresh of an active profile; and
- no credential, secret-derived identifier, raw endpoint, command, or client-provided upstream
  profile definition.

`MCPDiscoverResponse` contains the profile/revision identity, selected transport/protocol metadata,
the complete ordered namespaced descriptor set, unmatched operator allowlist entries, canonical
manifest hash, freshness/cache metadata, and a typed disposition. Descriptor descriptions and
schemas are passed verbatim as untrusted data after Gateway allowlist/filter validation; transport
and secret configuration are never returned.

`MCPCallRequest` contains `run_id`, `session_id`, and `request_id`, `profile_id`,
`profile_revision`, `manifest_hash`, a namespaced `tool_name` in the form
`profile_id.tool_name`, and JSON arguments. The Gateway derives the internal
`(profile_id, upstream_tool_name)` pair from the approved binding; an agent caller cannot supply a
second upstream name to widen that join. Arguments are the only agent-originated payload allowed
to cross to an upstream server.

`MCPCallResponse` contains `result_type`, validated content blocks, disposition, profile/revision
binding, transport/protocol, request and byte/duration attribution, and an `MCPUsageRecord`-backed
accounting summary. Only `resultType: complete` is releasable. `input_required` is a typed,
call-scoped denial. Resource links and embedded resources remain inert; image/audio blocks are
discarded with a typed note and are not decoded or persisted. No result field is trusted policy or
executable content.

### 5.2 Split authority and profile lifecycle

The agent and Gateway deliberately own different decisions:

| Decision | Agent authority | Gateway authority |
|---|---|---|
| Human approval and permission scope | `MCPTrustRegistry`, `ConfigTrustScanner`, `PreToolGuard`, approved effect class | Never reimplemented; Gateway requires the agent-supplied binding but does not trust a client assertion to widen its own policy. |
| Descriptor trust and planner exposure | Exact descriptor scan, namespaced approved subset, manifest hash | Filters to operator allowlist, validates definitions/header annotations, canonicalizes the returned set, and provides no partial manifest. |
| Profile/credential/transport state | Holds no upstream secret and no profile credential | `MCPProfileRegistry` owns `PENDING_REGISTRATION`, `ACTIVE`, `STALE`, and `DISABLED`, opaque revision, binding, static credential reference, transport, limits, and lifecycle state. |
| Final call admission | Local pre-tool decision | Bearer, active state, exact revision/hash, freshness, upstream allowlist, resource, budget, and immediate binding recheck. |

Profiles are operator-provisioned and activated through the existing startup/provisioning custody;
there is no bearer-authenticated live profile administration route. A profile enters
`PENDING_REGISTRATION`, runs bounded discovery, receives explicit agent/operator approval, and
becomes `ACTIVE` only through the approved restart/activation flow. Any endpoint, command,
credential reference, allowlist, isolation, resource, attribution, or policy change mints a new
revision and forces reapproval. Disable is immediate; re-enable mints a revision. The only
no-new-revision exception is initial approved-manifest-hash synchronization for an already
provisioned revision.

Discovery cache keys include profile revision and credential binding, regardless of upstream cache
scope. A successful refresh with a different canonical hash is drift and enters reapproval. A
recoverable refresh failure may serve the still-bound prior manifest with `freshness: stale_marked`;
it cannot create a new manifest or silently activate a changed profile.

### 5.3 Tools-only discovery and pagination

For every profile, discovery runs `server/discover` before `tools/list`. It follows `nextCursor` to
completion under provisioned page-count, tool-count, descriptor-byte, and elapsed-time bounds.
Allowlist filtering and descriptor validation run on every page. Repeated or malformed cursors,
malformed pages, incomplete pages, or invalid descriptors reject discovery atomically: no prefix
can become an approvable manifest. Transient discovery failures use the existing capped retry
policy; capacity exhaustion returns `mcp.discovery_budget_exceeded` and no manifest. V1 restarts a
complete scan and persists no cursor checkpoint.

The Gateway adds the `profile_id.tool_name` namespace and never uses self-reported `serverInfo.name`
for identity or authorization. It excludes tools outside the Gateway upstream allowlist, rejects
invalid definitions, rejects invalid `x-mcp-header` values, and never enables `Mcp-Param-*`
argument mirroring. It reports unmatched configured allowlist entries for operator visibility.

Remote Streamable HTTP must prove the 2026-07-28 version and tools capability at
`server/discover`; it has no initialization fallback. Docker-contained stdio first probes the
modern discovery path, negotiates a supported modern version, and may use the legacy
tools-only initialization path only when the contained child cannot use the modern path. No path
advertises roots, sampling, elicitation, logging, subscriptions, or extensions.

Context7 is the named remote acceptance dependency. Its configured endpoint is not considered
reachable or supported until a real authenticated probe originates from the Gateway and proves the
exact 2026-07-28 discovery/version/tools contract. Unsupported or indeterminate evidence yields
`mcp.protocol_version_unsupported` for that HTTP capability and never activates fallback.

### 5.4 Invocation, result trust, and local guardrail integration

The request path is ordered as follows:

1. The agent loads the already approved namespaced descriptor and runs the existing
   `MCPTrustRegistry`, `ConfigTrustScanner`, descriptor exposure guard, permission/scope/effect
   checks, and `PreToolGuard`.
2. The agent sends only typed binding metadata and arguments to the Gateway using the existing
   one-key `GatewayClient` transport.
3. The Gateway authenticates the bearer and resolves profile state, exact revision/hash, freshness,
   allowlist, resource limits, and budget before opening a transport.
4. `MCPInvocationBroker` rechecks the binding immediately before dispatch and delegates connection
   lifetime to `MCPConnectionManager` and the selected transport adapter.
5. The Gateway validates the complete result, records the MCP usage row, and releases the result
   only after accounting succeeds.

No system prompt, conversation history, policy text, approval record, Gateway bearer, upstream
credential, or other instruction content crosses the Gateway. Returned descriptors, annotations,
text, structured content, resource links, and server identity remain untrusted input. They cannot
approve tools, alter policy, trigger a fetch, execute code, or become trusted manifest content.

`src/optimus/mcp/runtime.py` remains the local orchestration boundary. Its runner seam changes only
to call the typed Gateway route after the existing local guard passes. The implementation must not
replace the local runner with a Gateway-only trust decision, bypass `PreToolGuard`, or introduce a
second permission registry.

### 5.5 Transport and connection lifecycle

Provisioning state and runtime connection lifetime are separate axes. Opening, reusing, or closing
a socket/child cannot create, activate, re-enable, or mutate a profile. Remote HTTP is request-scoped
and carries protocol version, client identity, and capability metadata in per-request `_meta`; v1
opens no standalone GET/SSE stream, subscription, or protocol session. A stdio child is opened only
after admission and is closed on disable, stale/revision change, idle/duration limit, policy breach,
transport corruption, or Gateway shutdown. Bounded reuse is not MCP session resume.

The stdio adapter is required to:

- launch only a digest-pinned Docker image;
- reject tags, host mounts, devices, Docker-socket mounts, and unsafe credential projection;
- construct a child environment containing only the selected profile credential;
- use `docker run --env NAME`, never `--env NAME=value`, for secret projection;
- exclude the Gateway bearer, model key, other MCP credentials, and telemetry credentials;
- enforce the specified duration/response-byte/read-loop limits; and
- deterministically terminate the child process tree.

The Docker daemon, image supply chain, and provisioned container egress remain explicit residuals.
Windows Job Object and Linux/WSL2 process-limit claims require real platform evidence before release
sign-off; a green test fake or remote CI result does not discharge them.

The HTTP adapter pins scheme/origin/path, static header mapping, TLS policy, duration, and response
limits. HTTPS is required except for an explicitly provisioned loopback endpoint. Redirects are
disabled so credentials cannot cross origins. OAuth fields are rejected in v1 and are owned by
`P11-FU-12`.

### 5.6 Accounting, budgets, errors, and retries

MCP uses an additive `MCPUsageRecord` with `gateway_request_id`, run/session/request IDs,
profile/revision, namespaced/upstream tool names, transport, disposition, duration, request/response
bytes, attribution state, provider request ID when present, and authoritative monetary fields when
available. The attribution state is exactly one of:

- `settled`: the profile adapter returned authoritative billing units and cost;
- `explicit_zero`: the operator declared this revision free of per-call external charge; or
- `unavailable`: no authoritative monetary data exists.

`unavailable` is never displayed or reconciled as zero. Strict-dollar budget policy denies it unless
the revision-bound profile explicitly permits unattributed spend. An accounting persistence failure
withholds the result and retries persistence only with the same `gateway_request_id`; it never
redispatches the upstream call.

MCP errors extend the existing failure taxonomy and `RetryPolicy`. Safety, authorization,
descriptor, schema, content, budget, and integrity failures do not retry. Only transient
`server/discover` and `tools/list` failures retry, at most three attempts with existing
backoff/jitter. `tools/call` is never automatically retried. A timeout or connection loss after
dispatch is `indeterminate`: read-only tools may be explicitly re-invoked, while a side-effecting
`(profile_id, tool)` is durably held by `PreToolGuard` until operator acknowledgement.

User-visible errors are sanitized typed dispositions and never contain credentials, raw challenges,
secret-derived identifiers, or unredacted server text.

## 6. Verification design

The evidence tier named by a requirement must use the real dependency named by that tier. Fakes are
allowed only in unit tests. A project-authored MCP client/server cannot replace the independent
protocol or live dependency required by the Test Strategy.

### 6.1 Unit evidence

Unit tests must cover:

- strict typed request/response validation, canonicalization, namespace construction, and malformed
  or incomplete result rejection;
- registration versus refresh field requirements and profile state/revision transitions;
- allowlist filtering, invalid descriptor/header rejection, unmatched allowlist reporting, and
  repeated/malformed cursor detection;
- split authority: local trust/permission remains required while Gateway profile/binding/allowlist
  checks independently deny direct widening;
- HTTP method/version/header behavior and no legacy fallback; stdio modern/legacy negotiation
  selection;
- Docker launch policy, secret projection, no-mount/device/socket rules, byte/time bounds, and
  deterministic termination seams;
- content/result handling for `complete`, `input_required`, resource links, embedded resources,
  image/audio, invalid schemas, and untrusted text;
- `MCPUsageRecord` attribution states, unavailable-cost budget denial, explicit-zero revision binding,
  idempotent persistence-before-release, and no redispatch after accounting failure;
- retry classification, three-attempt discovery/list cap, no automatic call retry, and durable
  side-effect indeterminate hold;
- absence of upstream credentials and secret-derived identifiers from agent payloads, child env,
  logs, traces, state, responses, and error messages; and
- preservation of existing web/package/advisory Gateway route and local MCP runtime tests.

### 6.2 Integration evidence

Integration tests must run a real local Gateway process and exercise both typed routes through the
existing agent Gateway client and local trust/guardrail path. They must prove:

- pending registration -> complete discovery -> explicit approval -> restart activation -> refresh
  -> call;
- multi-page discovery complete-or-absent behavior, cursor-integrity denial, freshness and stale
  marking, profile/revision drift, and profile/connection-axis separation;
- direct Gateway bearer requests cannot exceed the operator allowlist or bypass the binding pair;
- result validation and accounting occur before release; persistence failure withholds the result;
- remote HTTP requests use exact 2026-07-28 per-request metadata and tools-only methods; and
- Docker-contained stdio uses an independently authored server with digest-pinned/no-mount
  containment, safe credential projection, negotiated/legacy discovery-first behavior, bounded
  reads, and deterministic teardown.

The named live tiers are:

| Tier | Real dependency and evidence |
|---|---|
| `requires_redis` | Real TimeSeries-capable Redis for MCP usage persistence, idempotency, retention, and consumer reconciliation. |
| `requires_gateway` | Real loopback Gateway and approved Optimus credentials for direct-route policy, binding, accounting, and credential-isolation evidence. |
| `requires_mcp_http` | Real Gateway plus an independently authored remote Streamable HTTP MCP server. |
| `requires_mcp_stdio` | Real Gateway plus an independently authored Docker-contained stdio MCP server. |
| ACP protocol | Independent `acpx` client; never a project-authored ACP client or MCP harness. |
| Platform containment | Real Windows and Linux/WSL2 process-limit evidence before claiming the enforced process-count control. |
| Context7 compatibility | The actual configured Context7 endpoint, probed by the Gateway with authenticated discovery/version/tools requests; no substitute server. |

### 6.3 Release gates

The frozen design is complete only when the later implementation plan names evidence artifacts for
each claim and the following gates pass:

- Plan-mode and Agent-mode runs resolve only `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` in the
  agent process; no provider or MCP upstream credential is locally resolvable.
- All affected unit/integration suites, the default suite, aggregate production coverage at or
  above 80%, Ruff, and `git diff --check` pass.
- Real Gateway, Redis, independent MCP HTTP/stdio servers, and independent ACP evidence pass their
  named tiers; fake-based tests are not release evidence.
- Remote HTTP 2026-07-28 method-set evidence, Docker stdio containment/negotiation evidence,
  complete pagination, typed failures, accounting-before-release, and indeterminate-call custody
  all pass.
- Context7 is either proven by the named real Gateway-originated probe or remains explicitly
  unclaimed/unsupported; a configuration snippet cannot satisfy the gate.
- Every deferred boundary has a named owner: `P11-FU-12`, `P11-FU-13`, `P11-FU-14`,
  `P11-FU-15`, or the existing ACP/Zed/registry feature as applicable.
- The working-agent sign-off remains governed by
  `docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`.

## 7. Four-authoritative-document requirement traceability

| Authority | Exact requirement anchor | Design response | Required evidence |
|---|---|---|---|
| HLD v2.17 §5A p.3 | Agent has only Gateway URL/shared secret; Gateway may hold profile-scoped MCP credentials; MCP usage is separate from model/tool usage. | One-key agent boundary, Gateway-owned static profile credentials, additive `MCPUsageRecord`; no secret or secret-derived identifier crosses. | Credential scans; live Gateway/stdio/HTTP evidence; accounting consumer sweep. |
| HLD v2.17 §§6-7 pp.4-5 | Approved MCP call is a separate guarded branch; agent sends profile/binding/manifest/arguments; Gateway validates profile/allowlist/resource/connection. | Existing local trust guard remains active; typed Gateway broker performs independent binding and transport admission. | Unit split-authority tests; real direct-route denial and approved call. |
| HLD v2.17 §11 p.10 | Gateway owns MCP routes, credentials, profile state, allowlists, resource limits, transport execution, and usage. | `MCPProfileRegistry`, discovery/invocation brokers, connection manager, transport adapters, and usage writer are Gateway-owned. | Local Gateway process and live dependency artifacts. |
| HLD v2.17 §§11.1-12 pp.11-12 | Arguments-only forwarding, untrusted results, no session resume, and transport/trust/accounting/credential tests. | Typed call path, inert content, no HTTP session/stdio resume semantics, and named live gates. | Protocol, trust, containment, and accounting evidence. |
| LLD v2.40 §§0/0A pp.2-5 | Tools-only static profiles, two transports, zero upstream credentials, route names, typed components, and Gateway-owned profile/usage boundaries. | Frozen contract and file map follow the named routes/components; no OAuth/autoload/arbitrary proxy. | Contract tests, import boundary, one-key release scan. |
| LLD v2.40 §0D p.3 | The MCP routes are typed Gateway endpoints, not an arbitrary MCP-method proxy; named broker components own the Gateway side. | The contract and file map follow the exact route/component inventory. | Contract and import-boundary tests. |
| LLD v2.40 §§9C-9C.4 pp.26-29 | Existing typed Gateway tool/client seam and independent provider boundaries. | MCP extends the current route/client boundaries and preserves existing tool route regressions; no MCP reuse of web provider contracts. | Existing tool suite plus MCP-specific contract suite. |
| LLD v2.40 §9D p.30 | Gateway independently revalidates privileged inputs; MCP checks active profile, revision/hash, freshness, allowlist, resource, and budget. | Split-authority ordering and direct-bearer denial are normative. | `requires_gateway` direct-route evidence. |
| LLD v2.40 §§9E-9E.1 pp.31-32 | Separate `MCPUsageRecord`, complete-only release, inert resources, attribution states, persistence-before-release, and no unknown-cost-as-zero. | §5.6 defines the additive accounting contract and recovery behavior; existing usage rows stay unchanged. | Redis, ledger, budget, and golden-task evidence. |
| LLD v2.40 §§11-11A pp.36-38 | Implementation checklist, coverage, real dependencies, independent ACP, Context7 probe, and no credential leakage. | §6 names exact tiers and release gates; implementation plan must produce named artifacts. | Coverage/Ruff, live tiers, acpx, Context7, credential scans. |
| LLD v2.40 §12B p.39 | `MCPTrustRegistry`, `ConfigTrustScanner`, descriptor trust, manifest reapproval, and durable indeterminate holds. | `src/optimus/mcp/runtime.py` remains the local guardrail seam; Gateway integration cannot weaken it. | Existing guardrail tests plus Gateway integration and restart/hold evidence. |
| Guardrails v1.2 §5 pp.8-9 | MCP/config trust and prompt-injection controls are deterministic; no cloned-repository autoload; descriptor trust is explicit. | Preserve scanner/registry/approval behavior and treat all live descriptors/results as untrusted. | Guardrail unit/integration fixtures and no-autoload tests. |
| Guardrails v1.2 §8.3 p.11 | MCP capability table is tools-only; remote HTTP is request-scoped; stdio is Docker-contained discovery-first negotiation. | §4 and §§5.3-5.5 close all deferred methods and transport behavior explicitly. | `requires_mcp_http`, `requires_mcp_stdio`, platform evidence. |
| Guardrails v1.2 §7.3 p.10 | Indeterminate holds, static profile/connection separation, and no silent redispatch. | No automatic call retry; bounded connection lifecycle; deferred capabilities remain closed. | Failure injection, restart hold, transport protocol, audit-log invariance. |
| Guardrails v1.2 §§9-10.2 pp.12-13 | Separate MCP accounting states, Gateway usage path, component contracts, and no second credential/cost path. | Additive MCP usage row with Gateway-only credential custody; no mutation of settled usage contract. | Accounting consumer sweep and process-scope scans. |
| Guardrails v1.2 §11.2 p.14 | Required MCP tests cover protocol, trust, isolation, accounting, errors, and platform behavior. | Verification design maps each control to unit, integration, live, or release evidence. | Named evidence artifacts and platform gates. |
| Guardrails v1.2 §13 p.16 | Document-control and cross-reference obligations. | Implementation plan must include freshness audit; this design does not mutate authoritative PDFs or charter. | Reviewer audit before plan closure and before merge. |
| Test Strategy v1.6 §§1/3 pp.2-3 | Real dependency tiers, zero upstream credentials, Gateway-owned profile credentials, and independent ACP client. | Tier table in §6.2; fakes restricted to unit tests. | Real Gateway/Redis/MCP/acpx evidence. |
| Test Strategy v1.6 §6 p.5 | Discovery/call protocol tests, exact HTTP method set, no fallback, and stdio negotiation. | §5.3 and §5.5 freeze the method/transport behavior. | `requires_mcp_http` and `requires_mcp_stdio`. |
| Test Strategy v1.6 §§7-8 pp.6-8 | Egress, cache/lifecycle, credential isolation, MCP accounting, unknown-cost handling, and consumer sweep. | Profile/revision cache partitioning, bounded lifecycle, additive accounting, and no-zero rule. | Redis, egress, credential, ledger, golden-task evidence. |
| Test Strategy v1.6 §§9-10 pp.9-10 | Retry/failure taxonomy and schema/result validation. | Existing `RetryPolicy`, no call retry, typed complete-only results, and typed dispositions. | Unit and failure-injection suites. |
| Test Strategy v1.6 §§11-13 pp.10-12 | Security/trust tests, golden tasks, and Phase 1 release gates with real Gateway and independently authored servers. | Release gates require mode/tool/authorization/transport/cost/usage/credential assertions. | E2E golden and release artifacts. |
| Test Strategy v1.6 §14.10 p.14 | Traceability matrix includes exact remote/stdio, descriptor/payload, Context7, and profile-axis claims. | Every in-scope control is mapped to a named evidence family; no fake substitutes. | Final traceability artifact and review checkpoint. |

## 8. File responsibility map

The paths below are design responsibilities for the later implementation plan, not authorization to
create or edit them now. Existing Plan 11.2 files are extended only where the boundary is shared.

| File/surface | Responsibility in Plan 11.8 |
|---|---|
| `src/optimus/gateway/mcp_models.py` | Agent-side typed discovery/call requests, descriptor/result/disposition models, canonical serialization, and MCP usage envelope parsing. |
| `src/optimus/gateway/client.py` | Reuse authenticated JSON transport; add narrow typed MCP discovery/call methods without adding provider credentials or arbitrary route proxying. |
| `src/optimus/mcp/runtime.py` | Preserve local trust/guardrail sequence; add the typed Gateway runner seam after local approval and before execution. |
| `src/optimus/guardrails/mcp_trust.py` | Preserve `MCPTrustRegistry`/descriptor scanner semantics; only add binding/namespace adapters if required to represent Gateway profile revision without weakening trust. |
| `src/optimus_gateway/mcp_models.py` | Independently deployable Gateway-side contract duplicate; must not import `optimus.*`. |
| `src/optimus_gateway/mcp_profiles.py` | `MCPProfileRegistry`, static profile schema, lifecycle/revision/binding validation, startup/provisioning activation, and credential-reference custody. |
| `src/optimus_gateway/mcp_discovery.py` | `MCPDiscoveryBroker` and `MCPDiscoveryPaginator`, complete pagination, cursor-integrity checks, allowlist filtering, descriptor validation, namespace, canonical manifest, freshness, and typed discovery dispositions. |
| `src/optimus_gateway/mcp_invocation.py` | `MCPInvocationBroker`, two-gate admission, binding recheck, arguments-only forwarding, resource/budget checks, result validation, and indeterminate-call dispositions. |
| `src/optimus_gateway/mcp_connections.py` | `MCPConnectionManager`; separate profile state from HTTP request/stdio child lifecycle, bounded reuse/teardown, and no profile mutation by transport. |
| `src/optimus_gateway/mcp_transports.py` | Remote Streamable HTTP 2026-07-28 adapter and Docker-contained stdio discovery-first adapter, including safe credential projection and limits. |
| `src/optimus_gateway/mcp_usage.py` | MCP usage record construction, attribution states, persistence-before-release, idempotency, and existing ledger/Redis integration without changing `GatewayUsage`. |
| `src/optimus_gateway/mcp_handlers.py` | Authenticated typed route handlers for `/v1/tools/mcp/discover` and `/v1/tools/mcp/call`, sanitized errors, and status/disposition mapping. |
| `src/optimus_gateway/server.py` | Extend route dispatch with exactly the two MCP routes while preserving all current CORE/TOOLS/observability and unknown-route behavior. |
| `src/optimus_gateway/providers.py` and existing `tool_*` modules | Preserve existing web/package/advisory provider contracts; add MCP dependency wiring without making MCP availability depend on Tavily or another existing tool key. |
| `tests/unit/mcp/` | Agent contract, trust integration, namespace, error, result, and runner unit tests. |
| `tests/unit/optimus_gateway/test_mcp_*.py` | Gateway profiles, discovery/pagination, transports, connections, invocation, usage, handlers, and import-boundary tests. |
| `tests/integration/optimus_gateway/test_gateway_mcp_live.py` | Real local Gateway route, policy, accounting, and independent transport evidence; separate markers for `requires_gateway`, `requires_mcp_http`, and `requires_mcp_stdio`. |
| `tests/integration/optimus_gateway/test_gateway_mcp_redis_live.py` | Real Redis persistence/retention/idempotency and unavailable-cost consumer evidence. |
| `tests/e2e/` and independent `acpx` driver assets | Golden tasks and ACP compatibility evidence; no project-authored ACP client or fake server may discharge live protocol claims. |
| `reports/plan-11-8-gateway-mcp-*.md` | Sanitized live evidence artifacts with dependency identity, request/response summaries, digests, and disposition; no secrets or raw untrusted bodies. |
| `docs/superpowers/reviews/plan-11-8-review-checkpoints.md` | Gitignored reviewer handoff log; maintain current state and rulings; never stage. |

## 9. Definition of Done for the frozen design

- The branch is based on `origin/main` at the recorded baseline, and the four authoritative PDF
  bytes, charter, and supporting rationale identities are recorded.
- The design names the exact MCP Gateway routes and all six LLD broker components without creating
  an arbitrary-method proxy.
- The v1 boundary is explicit: tools-only, two transports, static profiles, zero upstream agent
  credentials, no OAuth, no catalog/autoload, no semantic selection, and named deferred custody.
- The existing local MCP trust/guardrail system is preserved as a required agent-side gate and is
  not conflated with the Gateway profile registry or with P11-FU-9/P11-FEAT-ZED-RESUME.
- Split authority, profile revision/binding, discovery completeness, namespace, result trust,
  transport containment, lifecycle separation, retry, indeterminate outcome, and accounting-before-
  release behavior are deterministic and implementation-testable.
- Context7 is recorded as a real remote-compatibility acceptance dependency, with no reachability
  claim absent the required Gateway-originated authenticated probe.
- All four authoritative documents have exact section/page requirement traceability and each
  in-scope requirement maps to a named evidence tier or release gate.
- The file responsibility map identifies current seams and new responsibilities without mutating
  source code, tests, authoritative PDFs, charter text, or deferred-work custody.
- No placeholders, silent scope expansion, fake live evidence, or unsupported current-state claims
  remain after self-review.
- The design body is SHA-256 frozen in the header after this draft is self-reviewed.

Implementation planning is intentionally blocked until an operator/reviewer approves this written
specification. Once approved, the next stage is a separate Plan 11.8 implementation-plan document;
that plan must re-verify this spec digest and the four authoritative PDF digests before defining
tasks, tests, and mutation gates.
