# P11-FU-20 client-MCP runtime gap investigation

**Status:** Investigation only. No production source, tests, frozen plans, or pool rows were changed.

**Working commit:** `2fc53836efe90ed8c082a5c7385b7faf8e465b5c` (`origin/main` at branch creation)

## Executive finding

The gap is **(c) an absent subsystem**. The repository has tested components for
transport supervision, SDK operations, descriptor admission, session registration, and one-call
issuance; it does not have a production runtime which composes them. In particular, no production
path constructs `ClientMcpSdkAdapter`, opens a client capability, discovers its tools, creates a
concrete dispatching service, or invokes `materialize_tool_service`.

This is not an `acpx` availability problem. The only skipped `acpx` node is P11-FU-9's empty-array
ACP capture, not a P11-FU-20 one-call test; its own code skips when capture is incomplete
([`tests/e2e/test_client_mcp_acpx.py:45-75`](../tests/e2e/test_client_mcp_acpx.py)).

## 1. Actual production path and where it stops

1. `build_configured_server()` creates `ClientMcpRuntime`; its factory creates and starts an
   `MCPAsyncSupervisor` ([`src/optimus/acp/bootstrap.py:159-206`](../src/optimus/acp/bootstrap.py)).
   The runtime's declared state is a disposition, supervisor, capability flags, and candidate
   endpoint ([`src/optimus/mcp/client_disposition.py:99-116`](../src/optimus/mcp/client_disposition.py)).
   Section 4's production-construction search records zero `ClientMcpSdkAdapter` constructors.
2. ACP `session/new` creates a provisional session and calls
   `disposition_for_new_session()` ([`src/optimus/acp/spec.py:294-344`](../src/optimus/acp/spec.py)).
   That method normalizes entries, performs the ACP permission exchange, and records a lease or
   unavailable entry ([`src/optimus/mcp/client_disposition.py:136-207`](../src/optimus/mcp/client_disposition.py)).
   It deliberately does not open a transport.
3. On `session/prompt`, the ACP adapter passes the session's `ClientMcpSessionService` and permission
   broker into the runner ([`src/optimus/acp/spec.py:530-566`](../src/optimus/acp/spec.py)). The
   generic `mcp_list_tools` / `mcp_call` toolbox calls that service; with no registered service it
   returns `client MCP service unavailable` ([`src/optimus/agent/tools.py:115-169`](../src/optimus/agent/tools.py)).
4. The only registration operation is inside
   `ClientMcpDisposition.materialize_tool_service()`: it builds a catalog and registers the service
   ([`src/optimus/mcp/client_disposition.py:209-254`](../src/optimus/mcp/client_disposition.py)).
   No production caller reaches that method. Thus the state passed to the runner is a usable
   registry object, but an empty one.

The chain therefore stops **after lease recording and before lazy transport-open/discovery**. The
later ACP one-call broker is correctly fail-closed: it delegates only to a registered service
([`src/optimus/acp/spec.py:554-566`](../src/optimus/acp/spec.py)); it cannot create the missing
catalog or service.

## 2. Deliberate exclusions versus simply absent work

The frozen P11-FU-9 design and implementation plan put guarded discovery and the two static generic
operations in scope, not out of scope. The design's in-scope table says
"guarded discovery" and static generic invocation
([`docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md:20-32`](../docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md));
its connection section specifies complete-or-absent descriptor discovery
([`...design.md:196-211`](../docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md)).
The implementation plan likewise describes the intended lazy, identity-bound catalog path in its
architecture ([`docs/superpowers/plans/archive/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md:10-18`](../docs/superpowers/plans/archive/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md))
and gives Task 5 the model-facing generic operations
([`...implementation.md:365-434`](../docs/superpowers/plans/archive/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md)).

The documents do deliberately exclude, with named custody: `session/load` (`P11-FEAT-ZED-RESUME`),
descriptor pinning/allowlists (`P11-FU-23`), durable HTTP/SSE-trust relaxation (`P11-FU-24`), and
authenticated upstream evidence (`P11-FU-25`)
([`...implementation.md:655-706`](../docs/superpowers/plans/archive/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md);
[`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:1134-1174`](../docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)).
The living pool instead leaves P11-FU-20 itself promoted and explicitly states its residual as
"production composition not yet wired"
([`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:170`](../docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)).

There is a narrower, deliberate deferral: the P11-FU-20 pool entry says neither P11-FU-9 Task 7 nor
Task 8 covered attaching a real per-server catalog/authorizer to the session tool service
([`docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md:1436-1485`](../docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md)).
That explains the one-call registration seam. It does **not** turn the unimplemented runtime into a
P11-FU-9 explicit exception with separate custody; the current live owner remains P11-FU-20. Task 8 did exercise
direct SDK/catalog probes in tests—for example it directly uses the official SDK's `initialize()`
and `list_tools()` ([`tests/integration/mcp/test_client_mcp_live.py:93-195`](../tests/integration/mcp/test_client_mcp_live.py))—but does not drive the production server path.

## 3. `MCPAsyncSupervisor` production wiring

`MCPAsyncSupervisor` is partially wired: bootstrap constructs and starts one process-lifetime
instance ([`src/optimus/acp/bootstrap.py:188-189`](../src/optimus/acp/bootstrap.py)) and
`ClientMcpRuntime.close()` closes it ([`src/optimus/mcp/client_disposition.py:99-116`](../src/optimus/mcp/client_disposition.py)).
It is not wired to useful client-MCP work. `ClientMcpSdkAdapter` is the only production caller of
`_supervisor.submit()` ([`src/optimus/mcp/client_sdk.py:64-116`](../src/optimus/mcp/client_sdk.py)),
but no production code constructs that adapter. Consequently the started loop owns no production
MCP open, discovery, or call operation.

## 4. Classification and evidence

**Classification: (c) absent subsystem.**

This is not (a): no existing production flow has `raw_tools` to hand to
`materialize_tool_service`. It is not (b): one joining function would still need to instantiate the
SDK adapter with production factories, retain/close the connection, discover tools, carry the
capability/identity across the boundary, construct a real dispatching subclass, and only then admit
and register a service. The required transport-open, discovery, and dispatch lifecycle are all
absent from production.

The existing pieces are intentionally insufficient on their own:

- `ClientMcpSdkAdapter` exposes `open`, `discover`, and `call`
  ([`src/optimus/mcp/client_sdk.py:64-249`](../src/optimus/mcp/client_sdk.py)).
- `ClientMcpToolService._dispatch()` raises `NotImplementedError`; a concrete service is required
  for a real call ([`src/optimus/mcp/client_catalog.py:498-526`](../src/optimus/mcp/client_catalog.py)).
- `materialize_tool_service()` accepts caller-provided `identity`, `raw_tools`, and an optional
  service class rather than discovering or dispatching itself
  ([`src/optimus/mcp/client_disposition.py:209-254`](../src/optimus/mcp/client_disposition.py)).

### Negative-existence search record

All searches below ran at the working commit and were scoped to `src/**/*.py`.

| Claim | Exact search | Result |
|---|---|---|
| No production SDK-adapter construction | `rg -n --glob '*.py' 'ClientMcpSdkAdapter\\(' src` | 0 matches |
| No concrete production `ClientMcpToolService` | `rg -n --glob '*.py' 'class .+\\(ClientMcpToolService\\)' src` | 0 matches |
| No production caller of materialization | `rg -n --glob '*.py' 'materialize_tool_service\\(' src`, excluding the definition at `client_disposition.py:209` | 0 callers |
| Catalog construction is only inside materialization | `rg -n --glob '*.py' 'ClientMcpDescriptorExposureAdapter\\(\\)\\.build' src` | 1 match: `client_disposition.py:234` |
| Session-service registration is only inside materialization | `rg -n --glob '*.py' 'state\\.tool_service\\.register\\(' src` | 1 match: `client_disposition.py:254` |
| The live one-call test is unwritten | `rg -n -i 'session/new|session/request_permission|mcp_call|allow_once|issue_one_call_approval' tests/e2e tests/integration/mcp` | 0 matches. The two present files are catalog/negotiation and empty-array capture, as cited above; neither can drive the required ACP sequence. |
| `ClientMcpSdkAdapter` is the only production submit caller | `rg -n --glob '*.py' '_supervisor\\.submit|supervisor\\.submit' src` | 1 match: `src/optimus/mcp/client_sdk.py:92` |

## 5. What a live one-call proof would require

After the missing runtime exists, a real proof would need:

1. The production ACP agent with a live Redis instance supporting TimeSeries: startup calls
   `run_preflight(..., require_timeseries=True)`
   ([`src/optimus/acp/bootstrap.py:70-76`](../src/optimus/acp/bootstrap.py)). **Merely
   unauthorized for this package:** the repository identifies the required service, but WP-4 forbids
   starting or probing it. Its current machine availability is therefore unanswerable here, not a
   demonstrated blocker.
2. An Optimus Gateway endpoint plus `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; the settings
   constructor reads those values ([`src/optimus/config/gateway.py:49-55`](../src/optimus/config/gateway.py)).
   A real agent turn must ask the model to list/call the selected tool, so this entails a real,
   potentially paid model call. **Genuinely hard external dependency:** this requires operator-owned
   credentials, a reachable billing-enabled Gateway route, and approval for a paid invocation; no
   source change can substitute for it.
3. Independently authored `acpx` as the ACP driver, not a project harness. **Merely unauthorized
   for this package:** WP-4 forbids a live run, and the installed-client fact is already established;
   it is not the root cause.
4. An independently authored, controllable **write-classified** client-MCP server. The existing
   Terraform fixture is unsuitable because its observed tokenized distribution has zero write tools
   ([`tests/integration/mcp/test_client_mcp_live.py:22-31`](../tests/integration/mcp/test_client_mcp_live.py)).
   **Genuinely hard evidence dependency:** a new project-authored fake cannot satisfy the
   independently-authored-server rule. Selecting and validating a suitable external fixture is
   required. Starting Docker or network access for an already-selected fixture is merely
   unauthorized under WP-4, not evidence that Docker itself is difficult.
5. ACP responses for the initial transport `allow_once` and the later one-call write permission.
   A fresh allow-once lease has a `non_mutating` ceiling
   ([`src/optimus/mcp/client_trust.py:215-229`](../src/optimus/mcp/client_trust.py)), so a
   write-classified call also needs an identity-matching durable
   `side_effect_eligible` record. The record-authoring CLI is TTY-gated
   ([`src/optimus/acp/launch_approval_cli.py:82-85`](../src/optimus/acp/launch_approval_cli.py)).
   Therefore **yes: an `optimus-trust mcp review` TTY ceremony is required for this particular
   write proof**; it is not needed merely to establish the session transport lease. The ceremony is
   **merely unauthorized** in WP-4 (operator-owned interactive action), not technically absent.

The verifier should retain only safe server/tool names, client/version identity, token
presence/one-use booleans, safe ACP dispositions, and the terminal status—never the token,
configuration, arguments, or transcript body.

## 6. What finishing the runtime would take, and whether it can be done now

**The production runtime can be implemented in one focused code-and-test package now.** It is not a
one-line call site, but it is a bounded subsystem built from existing project modules and the already
locked MCP SDK. It should not be deferred merely because `acpx` or Phoenix-like local state is
unrun.

The implementation package would make these connected changes:

| Area | Likely change shape |
|---|---|
| `src/optimus/acp/bootstrap.py` | Build one production `ClientMcpSdkAdapter` with real hardened SDK/session/transport/process-tree factories, then retain it in `ClientMcpRuntime` alongside the already-started supervisor. The adapter constructor exposes all five required seams ([`src/optimus/mcp/client_sdk.py:64-86`](../src/optimus/mcp/client_sdk.py)). |
| `src/optimus/mcp/client_disposition.py` | Add the lazy runtime coordinator: retrieve a leased runtime capability, open it with the session ID, run complete bounded discovery, pass its tools into the existing catalog-admission method, and register a close hook. Preserve the existing zero-open `session/new` boundary. |
| `src/optimus/mcp/client_catalog.py` (or a new tightly scoped runtime module) | Provide the concrete adapter-backed `ClientMcpToolService` dispatch implementation: its `_dispatch` calls the connection-bound SDK adapter and returns only the existing safe output. The base class currently raises until a subclass supplies it ([`src/optimus/mcp/client_catalog.py:498-526`](../src/optimus/mcp/client_catalog.py)). |
| `src/optimus/mcp/client_sdk.py` | Supply or expose the production SDK factories and close semantics that the current injected unit seam deliberately leaves to callers; retain its existing open/discover/call bounds ([`src/optimus/mcp/client_sdk.py:98-249`](../src/optimus/mcp/client_sdk.py)). |
| Unit/integration/E2E tests | Add unit tests for the coordinator's lazy open/discover/register/teardown path and real-object guard consumption; add an independently authored `acpx` one-call test plus an external write-capable MCP fixture. The existing live tests contain no relevant ACP structural anchors (search recorded in §4). |

The source implementation and its hermetic unit tests **can be written today**; no new provider,
SDK-version, or production secret is required for that work. The only parts that genuinely await
external authority are the paid Gateway model invocation and selection/use of an independently
authored write-capable server for the final live proof. Redis/Docker/process start and the durable
TTY record are operator-authorized machine-state steps, not root-cause blockers. WP-4 prohibits all
of those live actions, so this report does not claim they are presently available.

## 7. Recommendation to the operator

**Recommendation: keep P11-FU-20 open and schedule the single focused runtime-composition package
now.** Root cause: the absent production subsystem in §4 has no adapter construction, capability
open/discovery driver, concrete dispatch service, or materialization caller. Size: the bounded
five-area change in §6, followed by the separately authorized real proof dependencies in §5. The
frozen Plan 11.20 closure rule says to retain the item
when the required real tier lacks passing evidence
([`docs/superpowers/plans/archive/2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md:246-249`](../docs/superpowers/plans/archive/2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md)).
The current P11-FU-20 pool row is the owner of the production-composition residual. Before a live
attempt, its next forward-only scope should own the whole production lazy path: capability lookup;
SDK-adapter construction with hardened real factories; per-session connection lifecycle; `open` →
complete bounded `discover` → scan/budget admission → concrete dispatch-service creation → registry
registration; teardown; and the independently authored ACP live one-call proof described above.

This preserves the Plan 11.20 result without overstating it: its registry, authorizer, ACP broker,
and `PreToolGuard` seam are correctly fail-closed and unit-tested, but the runtime needed to reach
them is absent. If the operator instead wants to close P11-FU-20 as a seam-only deliverable, that
requires an explicit forward custody amendment which transfers these named runtime duties to a new
item; it cannot treat an unrun live tier as passing evidence or modify a frozen artifact.
