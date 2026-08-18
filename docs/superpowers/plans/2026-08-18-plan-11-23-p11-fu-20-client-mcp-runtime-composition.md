# Plan 11.23 — P11-FU-20 Client-MCP Runtime Composition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task-by-task, and `superpowers:test-driven-development` for every production behavior change. Steps use checkbox syntax. Do not mark a checkbox complete until its stated verification command has passed.

**Goal:** Make a leased client-supplied MCP server usable through the existing static `mcp_list_tools` and `mcp_call` operations by composing the real SDK adapter, bounded discovery, catalog admission, concrete dispatch service, registry, and teardown at first use.

**Architecture:** `session/new` remains a transport-free lease-and-identity decision. The session-scoped service becomes the lazy entry point: on its first operation for a leased server it asks a runtime coordinator to look up the stored capability, open a connection through the production `ClientMcpSdkAdapter`, complete bounded discovery, pass the complete descriptor set to the existing admission seam, and register an adapter-backed `ClientMcpToolService`. The registered service retains the real connection and dispatches only after the existing `PreToolGuard` allows it; session close runs the registered connection close hook exactly once.

**Tech Stack:** Python 3.14, locked `mcp==2.0.0`, existing `optimus.acp`, `optimus.mcp.client_sdk`, `optimus.mcp.client_disposition`, `optimus.mcp.client_catalog`, `PreToolGuard`, pytest, pytest-asyncio, coverage.py, Ruff, and independently authored `acpx` for the final ACP tier.

**Spec:** `docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md`; custody and the one-call seam are in `docs/superpowers/plans/2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md`; the runtime-gap authority is `reports/p11-fu-20-client-mcp-runtime-gap-investigation.md`.

## Authority and baseline anchors

- `P11-FU-20` remains the sole live owner. This plan does not close it, create a successor, or amend frozen P11-FU-9 or Plan 11.20 bytes.
- At this plan's drafting commit, `build_client_mcp_runtime()` starts a supervisor but constructs no `ClientMcpSdkAdapter` (`src/optimus/acp/bootstrap.py`); `ClientMcpDisposition.materialize_tool_service()` is uncalled production code (`src/optimus/mcp/client_disposition.py`); and `ClientMcpToolService._dispatch()` raises `NotImplementedError` (`src/optimus/mcp/client_catalog.py`). The exact negative-existence searches and their results are retained in the WP-4 report, §4.
- `ClientMcpSdkAdapter.open(capability, session_id=...)`, `.discover(connection)`, and `.call(connection, tool, arguments)` are the existing supervisor-time-bounded SDK operations; `.close(connection)` is the current synchronous tracked-connection/process-tree teardown seam that this plan hardens for SDK contexts. Its five construction seams are `supervisor`, `session_factory`, `http_client_factory`, `stdio_transport_factory`, and `process_control` (`src/optimus/mcp/client_sdk.py:64-249`).
- The existing one-call broker is intentionally fail closed: `AcpDuplexAdapter._mcp_permission_broker_for()` resolves a token only through the registered `ClientMcpSessionService` and returns `None` when no matching service exists (`src/optimus/acp/spec.py:554-566`). `PreToolGuard.check()` remains the operation-entry authority in `ClientMcpToolService.call_tool()`.

## Prerequisites

| Category | Prerequisite | Satisfied today? | Owner | If unsatisfied: genuinely hard, or merely unauthorized? |
|---|---|---|---|---|
| code/state | A production discovery-to-composition path must exist end to end; it does not at drafting time. | no | implementing agent | genuinely hard until Tasks 1-4 ship; the unit path is buildable now. |
| services | A live Redis with TimeSeries must be reachable for a real ACP agent process. | unknown | operator | merely unauthorized for planning; Task 6 establishes availability before a live attempt. |
| tooling/binaries | Locked MCP SDK `mcp==2.0.0` and its real client transport/session objects must support the factories selected in Task 1. | yes | implementing agent | n/a; the lock and installed source are inspectable now. |
| tooling/binaries | Independently authored `acpx` must drive the final ACP proof. | yes | operator | merely unauthorized to run in this package; WP-4 recorded installed `acpx 0.12.0`. |
| tooling/binaries | An independently authored, controllable write-classified MCP server must be selected and validated. | no | operator, with Task 6 selection record | genuinely hard: the pinned Terraform fixture classifies as `read=9, network=0, write=0`, and a project fake cannot satisfy the independent-server rule. |
| credentials/authority | A reachable billing-enabled Optimus Gateway with operator-owned `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY` must authorize a real model turn. | no | operator | genuinely hard external authority; source changes cannot substitute for it. |
| human interaction | The selected write proof needs the identity-matching durable `side_effect_eligible` record through `optimus-trust mcp review` in a real TTY. | no | operator | merely unauthorized interactive ceremony; it is not required to record the transport lease. |
| cost | The final agent turn must be approved as a potentially paid Gateway model call. | no | operator | genuinely hard cost authority. |

The only `unknown` row is Redis availability. Task 6 begins by recording the operator preflight result before any task that claims live evidence; if it remains unavailable, the live tier is explicitly unrun rather than treated as a failure or a passing substitute. Tasks 1-5 do not depend on it.

## Global Constraints

- Cut the implementation checkout and branch from refreshed `origin/main`; prove `HEAD == origin/main` before the first write. Do not use this planning branch or another contributor's worktree for implementation.
- Preserve the local-first one-key model. Do not introduce, log, serialize, persist, or prompt with any provider, Gateway, MCP, or Phoenix credential.
- `ClientMcpDisposition.disposition_for_new_session()` must not invoke SDK `open`, `discover`, `call`, a resolving service method, or a factory that opens a transport. A fresh empty `mcpServers` list remains an exact no-op.
- Preserve capability identity, session isolation, bounds, complete-or-absent discovery, descriptor scanning, effect ceiling, and the no-retry/no-replay rule. On open, discover, scan, budget, or dispatch setup failure, expose only a safe unavailable result and leave no partial registry entry.
- Use real `ClientMcpSdkAdapter`, `ClientMcpSessionState`, `ClientMcpSessionService`, `ClientMcpToolService`, `ClientMcpCallAuthorizer`, and `PreToolGuard` objects at wiring boundaries. Controlled transport/session doubles may model remote behavior; they may not replace those project boundary classes with a different interface.
- No registered matching authorizer means no one-call approval (`None`), never a fabricated token. The ACP broker issues a bound token only after the ACP response; it never dispatches. `PreToolGuard` remains immediately before dispatch.
- Keep the model surface fixed at `mcp_list_tools(server)` and `mcp_call(server, tool, arguments)`. Third-party descriptors, initialization text, raw configuration, raw results, headers, environment values, and process detail remain untrusted and non-model-visible.
- Mark external tiers executed only when real dependencies ran. Unit fakes, code review, and a project-authored MCP server cannot discharge the `acpx` or independently authored write-server requirements.

## File Map

| Path | Responsibility |
|---|---|
| `src/optimus/acp/bootstrap.py` | Construct one adapter with real hardened factories and retain it in `ClientMcpRuntime` next to the started supervisor. |
| `src/optimus/mcp/client_sdk.py` | Own concrete SDK transport/session factory lifecycle and close both SDK context resources and the tracked connection safely. |
| `src/optimus/mcp/client_disposition.py` | Retain per-session capability/workspace state and coordinate lazy open → discover → admission → close-hook registration. |
| `src/optimus/mcp/client_catalog.py` | Add the real adapter-backed dispatch service and a narrowly scoped lazy resolver hook in the session registry. |
| `src/optimus/acp/spec.py` | Attach the session's lazy resolver only after successful transport-free disposition; retain the existing broker closure and close behavior. |
| `tests/unit/mcp/test_client_sdk.py` | Test real factory ownership and close semantics with controlled remote transport/session behavior. |
| `tests/unit/mcp/test_client_disposition.py` | Test lazy capability lookup, no partial registration, session/server isolation, and idempotent teardown. |
| `tests/unit/mcp/test_client_catalog.py` | Test real adapter-backed dispatch through the actual guard and safe-result boundary. |
| `tests/unit/acp/test_bootstrap.py` | Test bootstrap builds/retains the production adapter without opening a server. |
| `tests/unit/acp/test_spec_protocol.py` | Drive actual ACP session state, resolver, registry, broker, and guard to prove the zero-open and fail-closed contracts together. |
| `tests/e2e/test_client_mcp_acpx.py` and a new named live report | Hold the independently authored ACP one-call evidence only after Task 6 prerequisites are genuinely met. |

## Tasks

### Task 0: Lock the behavior baseline and implementation custody

**Files:**

- Modify: `tests/unit/mcp/test_client_disposition.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Create: `reports/plan-11-23-p11-fu-20-runtime-baseline.md`

**Interfaces:** Consumes the existing transport-free disposition and fail-closed broker. Produces focused RED tests and a committed baseline identifying the production call-site searches, without changing the pool or any frozen artifact.

- [ ] **Step 1: Write RED tests for the absent runtime path.** Add tests that construct real `ClientMcpSessionState` and `ClientMcpSessionService`, lease a server through `disposition_for_new_session()`, then call the static generic list route. Assert the desired post-implementation result—an admitted catalog and exactly one adapter `open` followed by one `discover`—which must fail on the baseline because it returns `unavailable:unknown_server`; separately assert the already-passing `session/new` boundary leaves controlled adapter open and discover counters at zero.
- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: the new admitted-catalog/one-open/one-discover assertion fails on the current baseline, while the zero-open assertion passes.

- [ ] **Step 3: Record the baseline.** Write the committed-base SHA, the six WP-4 negative-existence searches, the existing zero-open and fail-closed test names, and the statement that P11-FU-20 remains open pending both implementation and real evidence. Do not change the pool row.
- [ ] **Step 4: Commit the behavior contract.** Run the selectors plus `git diff --check`; commit only the tests and report with `test: define client MCP lazy runtime contract`.

### Task 1: Build the production SDK adapter with owned real factory lifecycles

**Files:**

- Modify: `src/optimus/mcp/client_sdk.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/mcp/client_disposition.py`
- Modify: `tests/unit/mcp/test_client_sdk.py`
- Modify: `tests/unit/acp/test_bootstrap.py`

**Interfaces:** `ClientMcpRuntime` gains a non-serializable `sdk_adapter: ClientMcpSdkAdapter`; production construction supplies concrete `mcp.client` transport/session factories, while the existing adapter remains injectable for unit tests. A `ClientMcpConnection` retains every entered SDK transport/session context necessary to close the same connection exactly once.

- [ ] **Step 1: Write RED factory and lifecycle tests.** Cover construction of the real adapter through `build_client_mcp_runtime()` without opening any capability; then use controlled remote streams around the real `ClientMcpSdkAdapter` to assert one open retains its entered resources, close invokes their exits once, duplicate close is harmless, and a failed initialize cleans every entered resource and removes the connection slot.
- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/acp/test_bootstrap.py -q
  ```

  Expected: FAIL because bootstrap has no adapter and `ClientMcpConnection` cannot yet own the SDK contexts.

- [ ] **Step 3: Implement concrete, hardened factories.** Build stdio parameters only from `ClientMcpRuntimeCapability`'s canonical safe identity and constructed child environment. Enter the locked SDK's stdio/HTTP/SSE transport and `ClientSession` contexts inside the supervisor-owned coroutine, create a session from their real streams, and retain the matching context exits on the connection. Construct HTTP clients with redirects and ambient environment disabled and explicit timeouts; do not claim HTTP/SSE support beyond the existing capability flags unless their present policy and tests admit it. Make `close()` exit the retained session/transport resources before process-tree teardown, never close an unrelated reused connection.

  ```python
  class ClientMcpConnection:
      session_id: str
      identity_key: tuple[str, str, str]
      session: ClientSession
      close_resources: Callable[[], Awaitable[None]]
      closed: bool = False
  ```

- [ ] **Step 4: Retain the adapter in the process runtime.** Construct it once after starting `MCPAsyncSupervisor`, pass it into `ClientMcpRuntime`, and keep runtime `close()` ordering as session connections first (via their per-session hooks), then candidate endpoint and supervisor. Do not open, discover, or manufacture a session from bootstrap.
- [ ] **Step 5: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/acp/test_bootstrap.py -q
  uv run --frozen ruff check src/optimus/mcp/client_sdk.py src/optimus/mcp/client_disposition.py src/optimus/acp/bootstrap.py tests/unit/mcp/test_client_sdk.py tests/unit/acp/test_bootstrap.py
  ```

- [ ] **Step 6: Commit.** Commit the adapter construction and lifecycle slice with `feat: build client MCP SDK runtime adapter`.

### Task 2: Create the concrete guarded SDK dispatch service

**Files:**

- Modify: `src/optimus/mcp/client_catalog.py`
- Modify: `tests/unit/mcp/test_client_catalog.py`
- Modify: `tests/unit/mcp/test_client_disposition.py`

**Interfaces:** Add a non-serializable `AdapterBackedClientMcpToolService(ClientMcpToolService)` before any registrar uses it. Its keyword-only constructor accepts `guard`, `catalog`, `authorizer`, `adapter: ClientMcpSdkAdapter`, and `connection: ClientMcpConnection`; `_dispatch(tool_name, arguments)` calls `adapter.call(connection, tool_name, arguments)` and returns only the established bounded safe string representation. It does not authorize, issue a token, or retry.

- [ ] **Step 1: Write RED dispatch tests.** Construct the real guard, catalog, authorizer, adapter-backed service, and connection. Assert a read dispatches once only after `PreToolGuard.check()` allows it; a write first gets the actual ACP broker's bound token and consumes it at the guard; absent/mismatched/replayed token, tool, arguments, server, or session never invokes `adapter.call`; adapter errors produce safe unavailable output with no retry; and arguments/raw results do not enter audit summaries or serializable state.
- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_disposition.py -q
  ```

  Expected: FAIL because no concrete production dispatch service exists.

- [ ] **Step 3: Implement the adapter-backed service.** Give the subclass explicit slots for the real adapter and connection, preserve the base class's non-serialization restrictions, use the existing safe result envelope, and leave `ClientMcpToolService.call_tool()` as the only code that invokes `PreToolGuard` before `_dispatch`.
- [ ] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_disposition.py tests/unit/guardrails/test_pre_tool_guard.py -q
  uv run --frozen ruff check src/optimus/mcp/client_catalog.py tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_disposition.py
  ```

- [ ] **Step 5: Commit.** Commit with `feat: dispatch client MCP calls through SDK adapter`.

### Task 3: Add lazy session composition without weakening the `session/new` boundary

**Files:**

- Modify: `src/optimus/mcp/client_disposition.py`
- Modify: `src/optimus/mcp/client_catalog.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `tests/unit/mcp/test_client_disposition.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`

**Interfaces:** Add a non-serializable resolver contract on `ClientMcpSessionService`, for example `ensure_server(server: str) -> ClientMcpToolService | None`. Replace `materialize_tool_service(..., service_cls=...)` with an explicit `service_factory(*, guard, catalog, authorizer) -> ClientMcpToolService` seam; the coordinator closes over its real adapter and opened connection when constructing `AdapterBackedClientMcpToolService`. `list_tools`, `requires_write_approval`, and `call_tool` must resolve first, so direct generic calls cannot bypass discovery.

- [ ] **Step 1: Write RED lazy-path tests.** Use an actual `ClientMcpSdkAdapter` object with controlled remote factory behavior, actual `ClientMcpSessionState`, actual registry, and a leased capability. Assert all of the following: `session/new` calls neither `open` nor `discover`; first list invokes `open` then bounded `discover` exactly once and registers an `AdapterBackedClientMcpToolService` with that same adapter/connection; a second list reuses it; a rejected lease, SDK error, malformed/over-budget catalog, identity mismatch, or factory exception closes the just-opened connection and registers nothing; separate sessions and server names never share a connection or service.
- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: FAIL because the registry does not yet own a resolver and no production caller reaches materialization.

- [ ] **Step 3: Implement the coordinator, factory seam, and resolver.** Retain the normalized capability and safe workspace root in opaque session state. The factory closure must be the only construction point for the adapter-backed service and must pass the exact opened connection; it must not store raw configuration or the closure on a serializable object. Attach the resolver only after `disposition_for_new_session()` succeeds; for a named leased capability it must execute this exact sequence:

  ```text
  capability lookup → adapter.open(session_id) → adapter.discover(connection)
  → ClientMcpDescriptorExposureAdapter build/scan/budget admission
  → ClientMcpCallAuthorizer + PreToolGuard → concrete service → registry.register
  → state.register_close_hook(lambda: adapter.close(connection))
  ```

  On any failure, close the just-opened connection, retain no partial catalog/authorizer/service, and return the existing safe unavailable shape. A resolver must never create a lease, change an effect ceiling, issue a one-call token, retry, or make raw configuration/results serializable.

- [ ] **Step 4: Preserve ACP semantics.** `AcpDuplexAdapter` must pass the resolver-bearing session service into the runner only after normal disposition. Preserve `session/new` rollback behavior on malformed input and `close_all()`'s idempotent state close. The broker closure remains a lookup over the same registry and still returns `None` before successful materialization.
- [ ] **Step 5: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_spec_protocol.py -q
  uv run --frozen ruff check src/optimus/mcp/client_disposition.py src/optimus/mcp/client_catalog.py src/optimus/acp/spec.py tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_spec_protocol.py
  ```

- [ ] **Step 6: Commit.** Commit with `feat: compose client MCP services lazily`.

### Task 4: Prove end-to-end hermetic wiring and teardown with real project objects

**Files:**

- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Modify: `tests/unit/mcp/test_client_disposition.py`
- Modify: `tests/unit/mcp/test_client_sdk.py`

**Interfaces:** Consumes the concrete runtime, resolver, adapter-backed service, registry, broker, and guard. Produces real-object composition evidence; remote endpoints remain controlled unit doubles only.

- [ ] **Step 1: Write the final RED composition test.** Drive the actual `AcpDuplexAdapter` through non-empty `session/new`, then a generic list and an eligible write call. Assert the service is absent and broker returns `None` immediately after `session/new`; list triggers one open/discover/register sequence; the ACP allow produces an identity- and arguments-bound token; `PreToolGuard` consumes it before exactly one adapter call; `close_all()` closes the connection exactly once; and an empty `mcpServers` array retains zero adapter counters.
- [ ] **Step 2: Run the RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py -q
  ```

  Expected: any remaining disconnected wiring fails before an implementation claim is made.

- [ ] **Step 3: Make only the minimum compatibility corrections discovered by the real-object test.** Do not replace a real boundary object with a hand-fed permission broker, registry, adapter, guard, or service fake. Preserve all existing P11-FU-9 generic-tool, session-isolation, and no-serialization tests.
- [ ] **Step 4: Run the full hermetic safety set.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_sdk.py tests/unit/mcp/test_client_catalog.py tests/unit/mcp/test_client_disposition.py tests/unit/acp/test_bootstrap.py tests/unit/acp/test_spec_protocol.py tests/unit/agent/test_tools.py tests/unit/agent/test_planning_loop_runner.py tests/unit/guardrails/test_pre_tool_guard.py -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  ```

- [ ] **Step 5: Commit.** Commit the verified wiring corrections with `test: prove client MCP runtime composition`.

### Task 5: Perform the mandatory implementation review and custody decision

**Files:**

- Create: `reports/plan-11-23-p11-fu-20-runtime-release.md`
- Audit only: `README.md`, `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md`

**Interfaces:** Consumes hermetic evidence and external-tier disposition. Produces a truthful review package while retaining P11-FU-20 ownership and status until Task 6 evidence is complete.

- [ ] **Step 1: Run the documented absence and source-anchor searches at the implementation commit.** Verify there is now a production adapter constructor, a production materialization caller, a concrete service, and a registry registration path. Record commands and exact results; classify any remaining zero-match claim as absence evidence rather than inference.
- [ ] **Step 2: Audit current-state documents.** Search for `P11-FU-20`, `ClientMcpToolService`, `one-call`, and `client MCP`. Classify every hit as current, frozen historical provenance, or evidence; do not modify a frozen artifact or pool status merely to make an aggregator look closed.
- [ ] **Step 3: Record the truthful interim disposition.** State that source and hermetic real-object tests are complete only if their commands passed. Keep P11-FU-20 open because final live evidence is separately gated by Task 6.
- [ ] **Step 4: Commit the review report.** Run `git diff --check` and commit the report only with `docs: record client MCP runtime composition evidence`.

### Task 6: Establish and run the external one-call evidence gate

**Files:**

- Modify before the authority-gated run on a separate evidence branch: `tests/e2e/test_client_mcp_acpx.py`
- Modify before the authority-gated run on that branch: `pyproject.toml`
- Create: a dated `reports/` live-evidence report after the run, whether passing or explicitly unrun

**Interfaces:** Uses the shipped production runtime and independently authored dependencies. It is not a substitute for Tasks 1-5, and a project-authored fake is prohibited.

- [ ] **Step 1: Establish prerequisite state before the run.** The operator records the real Redis/TimeSeries preflight result, selected independently authored write-capable server identity and classifier output, approved Gateway route/credentials, and paid-call approval. If any is unavailable, record the named prerequisite as unrun and stop this task without changing P11-FU-20 status.
- [ ] **Step 2: Perform the TTY ceremony.** The operator creates or confirms an identity-matching `side_effect_eligible` durable record with `optimus-trust mcp review`; retain only a token-presence/record-effect confirmation, never credentials, raw config, or the record secret.
- [ ] **Step 3: Add and run a properly tiered independently authored ACP test.** Add `test_client_mcp_one_call_write_via_acpx` marked `e2e`, `requires_acpx`, `requires_redis`, `requires_gateway`, and a new `requires_client_mcp_write_fixture` marker defined in `pyproject.toml`. Its fixture configuration must name the operator-selected independently authored server and assert a safe catalog list, one write-classified dispatch after ACP approval, and replay/mismatch refusal without logging arguments, tokens, raw configuration, or transcript bodies. Run exactly:

  ```powershell
  uv run --frozen pytest tests/e2e/test_client_mcp_acpx.py::test_client_mcp_one_call_write_via_acpx -m "e2e and requires_acpx and requires_redis and requires_gateway and requires_client_mcp_write_fixture" -v
  ```

  Record skipped or deselected as unrun, never as passing evidence. Do not use a project-authored ACP harness or MCP server.
- [ ] **Step 4: Decide custody only from named evidence.** Close P11-FU-20 only if the live report, selected fixture, paid Gateway result, and hermetic evidence all pass; otherwise retain it open with the exact missing owner and prerequisite. This step requires a forward plan/package authorizing the pool update; this plan itself does not authorize a closure edit.

## Definition of Done and Evidence Map

| Claim | Required evidence |
|---|---|
| `session/new` remains zero-open | Task 0/3/4 controlled adapter counters through the real ACP session path. |
| Production can lazily list a leased server | Task 3/4 real project-object resolver, adapter, catalog, and registry tests. |
| Production can safely dispatch a catalog tool | Task 2/4 real service, connection, and `PreToolGuard` tests. |
| ACP cannot fabricate approval without a registered authorizer | Existing and Task 3/4 actual adapter broker tests returning `None` before registration. |
| Write token remains identity-, tool-, arguments-, and one-call-bound | Task 2/4 authorizer and real guard-consumption assertions. |
| Connection lifecycle is bounded and torn down | Task 1/3/4 factory ownership, failed-open cleanup, and idempotent session-close evidence. |
| ACP protocol claim uses independent dependencies | Task 6 real `acpx`, external write-capable MCP server, Gateway, Redis, and TTY evidence, or an explicit unrun disposition. |
| P11-FU-20 closure is truthful | Task 5 report plus Task 6 passing evidence and a separately authorized custody update. |

## Plan Self-Review

- **Scope coverage:** Tasks 1-4 cover every WP-4 change area: production adapter construction/hardened factories, per-session lifecycle, open/discover/admission, concrete dispatch, registry, and teardown. Task 6 separately owns the external proof rather than blocking the buildable work.
- **Boundary review:** The resolver is reached only from generic operations after `session/new`; it cannot open a transport during disposition. The ACP broker remains a registry lookup and the guard remains immediately before `_dispatch`.
- **Real-object review:** The composition tests use actual adapter, state, registry, catalog, authorizer, service, broker, and guard instances. Test doubles represent only remote transport/session behavior at the SDK edge.
- **Prerequisite review:** Both genuinely hard dependencies are explicit: paid Gateway authority and an independent write-capable server. The Terraform fixture's tokenized zero-write result is recorded, Redis is the only `unknown` and has an early prerequisite task, while TTY/Docker-style execution steps are correctly merely unauthorized.
- **Custody review:** P11-FU-20 stays open and no successor is created. Frozen P11-FU-9 and Plan 11.20 artifacts are read-only authorities.
- **Placeholder/type scan:** All named interfaces and files were verified at the drafting commit; task steps name concrete tests, commands, error behavior, and commit boundaries. No task uses an unnamed owner or a generic final-evidence substitute.
