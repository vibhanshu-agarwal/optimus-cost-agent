# P11-FU-9: Client-Supplied ACP `mcpServers` Design Specification

**Frozen design-body SHA-256:** `66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2`

The digest is the SHA-256 of the UTF-8 LF-normalized body after removing the header line above and
its trailing line ending. The header is replaced only after this draft passes its self-review.

**Status:** Draft for independent reviewer and operator approval. This document authorizes no source
or test mutation, dependency or lockfile update, implementation-plan execution, commit, push,
release claim, authoritative-PDF change, charter change, or work on paused Plan 11.8 Tasks 8-9.

**Custody:** `P11-FU-9`, Client-Supplied ACP `mcpServers` Disposition. No Plan 11.x number or
implementation branch is assigned by this design. A later implementation must branch from current
`main`, not the paused Gateway-MCP feature branch.

## 1. Authority, problem, and boundary

The [consolidated follow-up pool](../plans/2026-07-23-consolidated-deferred-followups-backlog.md#p11-fu-9-client-supplied-acp-mcpservers-disposition)
owns this work. The Plan 11 charter explicitly separates client-nominated ACP servers from
Gateway-brokered MCP and assigns ACP `session/load` implementation to `P11-FEAT-ZED-RESUME`.
The vendored ACP v1 schema is the protocol source for the input shape. The current `session/new`
handler creates a session but ignores `mcpServers`.

This design changes that disposition: Optimus will honor client-supplied servers through an
agent-owned MCP client while retaining local approval, descriptor, and per-call guardrails. It does
not import `optimus_gateway` MCP modules or reuse Gateway profile, signed-manifest, Docker,
accounting, or protocol-floor machinery. Client-nominated credentials belong to the IDE user and
their chosen server; they are not Optimus-provisioned upstream credentials and cannot be sent to the
Gateway. They remain transient and structurally unavailable to the model.

`ClientMcpDisposition` is a standalone shared seam. `session/new` calls it now. A future
`session/load` implementation must call the same seam, but this work does not add, advertise, or
otherwise implement `session/load`.

| In scope | Explicitly excluded with custody |
|---|---|
| Client-supplied stdio, Streamable HTTP, and SSE server disposition, transport trust, guarded discovery, and static generic tool invocation. | `session/load`, durable ACP session state, retention, replay, and capability negotiation: `P11-FEAT-ZED-RESUME`. |
| Session-scoped ACP approval and durable CLI-only transport approval. | Gateway static profiles, signed startup manifests, Gateway credentials, MCP accounting, and paused Plan 11.8 live evidence. |
| Agent-owned SDK adapter and synchronous bridge. | OAuth lifecycle: `P11-FU-12`; dynamic model-tool registration, descriptor pinning, and tool allowlists: named backlog entry below. |
| Safe telemetry distinguishing `client_supplied_acp` from Gateway MCP. | Catalog/autoload/install/update, arbitrary MCP methods, resources/prompts/sampling, and semantic selection. |

## 2. ACP normalization and four representations

Absent or empty `mcpServers` is an exact no-op, preserving current live payload and test behavior.
The normalizer rejects duplicate server names, duplicate environment names, and duplicate HTTP
header names before scanning or transport work. Header comparison is case-insensitive. Environment
comparison follows the child platform's case rules. `_meta` is untrusted extension data: it is ignored
and never enters identity, telemetry, persistence, or a model-visible surface.

The ACP union is parsed deliberately: `type: "http"` and `type: "sse"` select those transports;
the untagged variant with no `type` is stdio. Stdio `command` is accepted as either an absolute path
or a bare executable token because the schema documents but does not enforce an absolute path.
The implementation advertises `mcpCapabilities.http: true` and `mcpCapabilities.sse: true` only
after those adapters, their trust gates, and their verification requirements exist; it must never
advertise either transport and then discard or fail the supplied entries.

Every accepted entry immediately separates into:

1. an opaque, slot-backed in-memory runtime capability holding raw header/env values;
2. a safe identity holding transport, safe server name, canonical executable or URL, non-secret
   arguments, credential-name metadata, and keyed value fingerprints;
3. a safe audit view holding provenance, scanner rule IDs, credential-presence flags, and
   disposition; and
4. an HMAC-protected durable MCP record containing only the safe identity, a transport-policy
   version, and an effect-scope ceiling.

Runtime capabilities are not dataclasses or model objects, expose no dump API, and reject pickle and
state reduction. Only an explicit `safe_view()` can cross into telemetry, evidence, or error paths.
Redacted `repr`/`str` is defense in depth, not the serialization control. References to raw values
are dropped when their connection closes; Python secure memory wiping is not claimed.

Server names exposed to the model are constrained to ASCII `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. The
same canonical name is the round-trip `server` argument. Invalid names are rejected rather than
escaped into model context.

### 2.1 Canonical identity

For stdio, a controlled copy of the agent PATH and explicit Windows `PATHEXT` rules are used solely
to resolve a bare command. The child never inherits that PATH. The result must be an existing
executable, is canonicalized with strict `Path.resolve()`, and applies `os.path.normcase` on Windows.
Thus `docker` and `docker.exe` resolve to one real executable identity. The canonical executable,
not the submitted token, is launched and fingerprinted. Resolution repeats on each disposition;
a new resolved path is untrusted-new. Replacement of bytes at the same canonical path remains an
explicit residual: this design deliberately does not digest-pin client-selected executables.

For HTTP/SSE, normalization permits only absolute `http` or `https` URLs. It lowercases scheme and
host, converts IDNs to lower-case ASCII A-labels, canonicalizes IP literals, removes default ports,
rejects userinfo and fragments, maps an empty path to `/`, and otherwise preserves trailing slashes.
It uppercases percent-triplet hex and decodes only unreserved characters. Reserved characters,
query order, and repeated query names remain significant. Query names are rendered; each value is
HMAC-bound to its name and positional index and is never rendered or stored in plaintext. DNS
rebinding remains an accepted residual; redirects are disabled and the initial normalized origin is
the approved identity, not a claim that hostname pinning fixes future DNS answers.

Env/header names are rendered and canonicalized. Values use a domain-separated HMAC fingerprint
bound to kind, canonical name, and positional index. Names with child-process injection semantics
(`LD_PRELOAD`, `DYLD_INSERT_LIBRARIES`, `NODE_OPTIONS`, `PYTHONSTARTUP`, `PYTHONPATH`, and `PATH`)
are hard rejected independently of credential handling.

`ConfigTrustScanner` receives a new explicit `CLIENT_MCP_CONFIG` subject. Raw scan input and
findings never escape the normalizer; only rule identifiers and a safe disposition do. ACP cannot
tell Optimus whether an entry originated in global user settings or a repository-local IDE file.
`client_supplied_acp` is therefore the finest provenance available, making the out-of-band durable
ceremony, not provenance inference, the durable malicious-repository defense.

## 3. Durable transport trust and the review ceremony

Transport establishment is independently authorized: an array entry alone never starts a child
process or outbound connection. `allow_once` grants a session-only lease. The agent never offers an
IDE-side `allow_always`; the existing ACP permission mechanism is used only with `allow_once` and
rejection options. Its safe text identifies `optimus-trust mcp review` as the route to durable trust.

Durable records use the existing approval-store/keyring trusted roots and HMAC root, but a distinct
MCP schema, key namespace, signature domain, credential-fingerprint domain, and
`MCP_POLICY_COMPATIBILITY` constant. The key is the tuple
`(workspace_digest, server_name, safe_identity_fingerprint)`. Same name with a changed identity is
untrusted-new. The record contains the canonical transport identity, credential fingerprints,
policy version, and an operator-selected client effect ceiling. The default `non_mutating` ceiling
permits read and network-read calls; `side_effect_eligible` permits a write-classified call only
after its ordinary per-call guard and ACP approval. This client vocabulary deliberately does not add
a global write-permitting entry to `_PERMISSION_SCOPE_LIMITS`. The record contains neither raw
configuration nor a discovered allowlist or descriptor fingerprint.

This is intentionally identity-only durable trust. Discovery occurs only after transport trust, so a
descriptor-surface fingerprint and named allowlist cannot be created without a circular first
connection. The existing `MCPTrustRegistry` and `MCPDescriptorExposureGuard` are manifest- and
allowlist-bound and remain unchanged for operator/local manifests; a client catalog must not
synthesize an `MCPServerManifest` merely to enter that path. Instead,
`ClientMcpDescriptorExposureAdapter` shares the extracted descriptor scan/normalization primitives
with the legacy guard but owns an in-memory, identity-bound client catalog. It soft-drops only a
malformed or scanner-blocked descriptor, recording a safe reason; scope/effect incompatibility never
raises during registration or hides an otherwise safe catalog. `PreToolGuard` remains the required
call-time authority. A later named backlog item owns descriptor pinning and allowlist selection.

The CLI review flow uses a small extracted production-local IPC helper patterned after the Plan 11.7
relay: `multiprocessing.connection.Listener`/`Client` with authentication, AF_PIPE on Windows,
AF_UNIX in the system temporary directory on POSIX, and hard rejection of TCP/network endpoint
addresses. Its auth key is derived from the approval-store HMAC root under an IPC-only domain. The
agent exposes read-only pending snapshots only while at least one candidate is pending; it has no
approve operation. ACP owns stdin/stdout NDJSON framing, so the agent has no independent TTY for
this ceremony.

The endpoint lists safe candidate snapshots with opaque IDs, workspace/session/received-at
provenance, scanner findings, and the immutable rendered fingerprint. Retrieval consumes one
snapshot. The CLI writes a record bound to exactly that fingerprint; the agent notices the record
only on a later lookup. One record satisfies other pending candidates only when the workspace, name,
and complete safe identity all match. Manual `optimus-trust mcp review` entry remains available when
IPC is unavailable. A session never waits for this ceremony: it can use a session lease or leave the
server unavailable.

## 4. Connection supervisor and bounded transports

The official MCP Python SDK v2 is isolated behind agent-owned adapters. It must be constrained as
`mcp>=2.0,<3`; the exact lockfile mutation and transitive review, including `httpx2`, require separate
operator approval when implementation reaches that gate. Client protocol negotiation is deliberately
broad; no Gateway `2026-07-28` protocol floor transfers. A successful `initialize` is not evidence
that its proposed version was accepted: the adapter must take the session version only from the
required `result.protocolVersion`, reject a missing, malformed, or unsupported negotiated result, and
use that returned value for subsequent session behavior. It must never infer the proposed version from
the absence of an initialization error.

One `MCPAsyncSupervisor` background event-loop thread owns SDK sessions and transports. Synchronous
agent tools submit with `run_coroutine_threadsafe`; no per-call `asyncio.run()` can tear down a
long-lived stdio session. It has `RUNNING`, `STOPPING`, and `DEAD` states. Every submission checks
liveness and has a bounded wait; a dead/stopping loop returns a safe error, never an indefinite
block. Shutdown cancels in-flight tasks, closes transports, and resolves pending work with a shutdown
error before the loop exits.

Connections are lazy, single-flight, and deliberately isolated by `(session_id, safe_identity)`.
No session shares transport state or credentials with another. A process-wide connection budget
rejects excess opens rather than weakening isolation. An async lock serializes calls per connection;
SDK request-ID multiplexing is not assumed. Initialize, descriptor discovery, and each call have a
30-second default deadline. No automatic call retry or post-dispatch replay is allowed.

Stdio starts only the canonical resolved executable with validated args, validated session workspace
cwd, and a constructed child environment. It receives supplied approved values plus only an
individually documented minimal platform baseline; it never inherits Optimus, Gateway, provider, or
telemetry variables. MCP framing uses bounded incremental reads with a 1 MiB maximum message/result.
Timeout, EOF mid-frame, malformed framing, or excess bytes closes the connection. Teardown first
attempts orderly close then terminates the complete spawned process tree: a Windows Job Object/tree
seam and a POSIX process-group/session seam. Resources created inside a client command, such as a
Docker container not removed by its own arguments, are outside Optimus control and remain a stated
residual.

HTTP/SSE use an injected `httpx2.AsyncClient` with `follow_redirects=False`, `trust_env=False`,
explicit connect/read/write/pool limits, and an Optimus-owned streaming-byte wrapper. The remote
policy rejects malformed/reserved targets before connect and records address-class findings for the
ceremony; it never forwards ambient proxy or credential state. Connection and discovery failures
produce safe errors and no partial cached catalog.

The complete initialize result is untrusted `MCP_INITIALIZE_RESULT` input, distinct from a later
`MCP_DESCRIPTOR`. The adapter scans bounded textual fields, including `instructions` and
`serverInfo` description, website URL, and icons, before retaining any safe initialization state. A
scanner-blocked initialize result closes the connection with a safe error. Even when admitted, none of
that server-supplied text is model-visible in this first release and none may become policy input,
modify an effect ceiling, approve a tool, or alter the trusted transport identity. A tools-only client
requires only a usable tools capability; it ignores, rather than rejects, unrelated advertised
capabilities such as prompts or resources, never invokes their methods, and never exposes them to the
model.

Descriptor discovery is complete-or-absent: at most 100 pages, 1,000 tools, 16 KiB per descriptor,
1 MiB aggregate descriptor bytes, and 30 seconds total. Cursor loops, malformed pages, duplicate
tool names, or any budget exhaustion yield no catalog. Every descriptor is untrusted
`MCP_DESCRIPTOR` input. The client adapter scans and validates descriptors individually before model
visibility, retaining a complete catalog of all individually admissible descriptors and safe
per-tool availability metadata rather than applying a manifest allowlist at discovery time.

## 5. Static model tools and call policy

The model receives only two fixed agent tools:

```text
mcp_list_tools(server)
mcp_call(server, tool, arguments)
```

A safe session inventory may list only validated server names and availability. `mcp_list_tools`
performs the lazy connection/discovery path and returns the complete individually guarded catalog or
a safe unavailable error, never a partial catalog. A descriptor above the current client effect
ceiling remains visible with fixed safe metadata stating that durable ceiling elevation is required;
it is not silently removed. The result cannot return headers, environment values, query values, raw
configuration, or process details. Third-party descriptors are not registered as first-class model
tools; dynamic descriptor promotion is deferred.

`mcp_call` validates that `arguments` is a JSON object and passes the actual arguments, server, and
guarded descriptor to `PreToolGuard`. `PreToolRequest` gains an MCP arguments field and an injected
MCP call-authorizer seam; the existing manifest registry is its legacy implementation and
`ClientMcpCallAuthorizer` is the client implementation. Neither `_sanitize_subject` nor the audit
event may serialize the arguments. The client authorizer rechecks the session/durable transport
lease, identity-bound discovered descriptor, and selected client ceiling before dispatch.

For client catalogs, effect classification is not the legacy full-description/full-schema substring
heuristic. It combines normalized declared effect metadata with tokenized tool-name evidence and
takes the more restrictive result; declarations are inputs, never authority, and cannot downgrade a
write token such as `delete` or `apply`. Description text and JSON-schema text do not participate in
automatic effect escalation, so incidental words such as `created_at`, `runtime`, `fetch`, or `url`
cannot make a read tool disappear. The `non_mutating` ceiling blocks write-classified calls while
allowing read and network-read calls. A `side_effect_eligible` ceiling still routes every
write-classified call, with its actual arguments, through ordinary `PreToolGuard`/ACP approval. The
transport ceremony never weakens that per-call control.

Two credential-free live catalogs demonstrate why this split is required. On 2026-08-06, the pinned
Terraform image `hashicorp/terraform-mcp-server@sha256:bd095e2b442a2cb61255fe4db52f9e824f35d307a2044784c95d37a93f18d324`
returned nine tools: the legacy full-text classifier produced `read=0, network=6, write=3`, while
tokenized names produced `read=9, network=0, write=0`. Public Context7 returned two tools under
protocol `2025-11-25`: legacy full text produced `read=0, network=2, write=0`, while tokenized names
produced `read=2, network=0, write=0`. Both probes proposed `2026-07-28` and returned successful
initialize results negotiated to `2025-11-25`: Terraform over stdio, and Context7 over an HTTP 200
plain POST with `Accept: application/json, text/event-stream`. Neither server accepted the proposed
revision. The client adapter must therefore negotiate broadly, read the negotiated revision from the
initialize result, and must not import a Gateway protocol floor.

MCP results are untrusted tool output. Transport trust does not make result bodies policy input:
no result may alter policy, widen an effect ceiling, approve a tool, become a trusted descriptor, or
trigger a fetch. Result size limits, safe error handling, and the no-replay rule apply equally to
read-only and effectful calls; an outcome after dispatch that cannot be known is explicitly
indeterminate, not silently retried. Telemetry records only safe identity, source
`client_supplied_acp`, transport, bounded outcome, and credential-presence/fingerprint metadata.
It never conflates this path with `gateway_brokered_mcp` or logs raw credentials/configuration.

## 6. Required verification and implementation gates

An implementation plan may be drafted only after this document is approved. It must begin with RED
tests and include, at minimum:

- schema-pinned parsing for absent/empty arrays, untagged stdio, HTTP/SSE capability advertisement,
  duplicate arrays, ignored `_meta`, controlled command resolution, and canonical identity drift;
- raw-value non-serialization, no model visibility, constructed-child-environment, injection-name,
  query/header/env fingerprint, and redaction tests;
- durable-record domain/key/policy separation, one-time IPC snapshot, manual fallback, concurrent
  candidate, tamper, and same-name/different-identity tests;
- supervisor death, timeout, cancellation, per-connection serialization, process-tree teardown,
  stdio overflow, remote redirect, proxy, byte-limit, and DNS-residual disposition tests;
- successful-initialize downgrade tests proving that a proposed `2026-07-28` session uses returned
  `2025-11-25`, plus safe rejection of absent, malformed, or unsupported negotiated versions;
- initialize-result scanning and containment tests for `instructions` and `serverInfo` text, including
  scanner-blocked safe denial, no model/policy exposure, and tolerance-without-use of advertised
  prompts/resources or other non-tools capabilities;
- complete-or-absent pagination/discovery, client-adapter soft-drop behavior, legacy-registry
  non-regression, client-ceiling classification from declared-plus-tokenized-name evidence,
  actual-arguments/non-serialization `PreToolGuard` tests, and never-auto-replay tests;
- repeatable credential-free real-catalog probes for the pinned Terraform image and public Context7
  endpoint proving the legacy classifier's false positives, the tokenized classifier's observed
  distribution, and broad protocol negotiation; and
- real independently authored ACP-client evidence for empty arrays and every advertised transport.

The dependency gate must inspect the exact SDK and transitive lockfile graph before mutation. A real
authenticated client-owned upstream test is separately required before claiming authenticated-server
support. It must use an operator-approved non-secret test credential and prove values remain absent
from model context, logs, evidence, argv, and durable records.

## 7. Deferred-work custody

The consolidated pool receives named, unnumbered-at-pickup entries with this draft for:

1. durable client-MCP descriptor-surface pinning and named tool allowlists;
2. a possible lighter durable HTTP/SSE trust path, evaluated separately from the equal-ceremony
   baseline; and
3. real authenticated client-owned upstream evidence beyond the initial safe test fixture.

The existing Plan 11.8 Windows `WinError 10053` test flake also receives a separate unnumbered
custody entry. These deferrals do not authorize any code path and may not silently disappear during
implementation planning.

## 8. Acceptance criteria for design approval

This design is ready for independent review only if the reviewer confirms that it:

1. honors non-empty client MCP configuration without importing or depending on `optimus_gateway`;
2. preserves an exact no-op for omitted/empty arrays and a shared future-lifecycle disposition seam
   without implementing `session/load`;
3. separates opaque runtime secrets, safe identity/audit views, and durable records with no raw-value
   serialization or model visibility;
4. establishes transport trust through session-only ACP approval or CLI-only durable ceremony,
   never an IDE durable approval;
5. pins canonical executable/URL identity and states binary-swap and DNS-rebinding residuals honestly;
6. bounds stdio and remote transports, discovery, supervisor liveness, cancellation, and process
   teardown at least as strictly as the stated defaults;
7. exposes only fixed generic tools and routes real arguments plus conservative effective effects
   through existing guardrails; and
8. names every deferred capability and real-dependency evidence requirement in the consolidated pool.

Approval authorizes only a separate implementation-plan draft. It does not authorize package/lockfile
mutation, live credentials, client configuration, source/test changes, a commit, or a PR.
