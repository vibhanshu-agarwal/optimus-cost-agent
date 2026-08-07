# P11-FU-9 Client-Supplied ACP `mcpServers` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Use `superpowers:test-driven-development` for every production behavior change. Steps use checkbox (`- [ ]`) syntax for tracking. Do not mark a checkbox complete until its stated verification command has actually passed.

**Status:** Draft revision 2 for operator and independent-reviewer approval. This document authorizes no source,
test, dependency, lockfile, credential, live-configuration, commit, push, or PR mutation until the
operator approves this exact plan.

**Goal:** Honor client-supplied ACP `mcpServers` through a guarded agent-side MCP client, exposing
only static generic `mcp_list_tools` and `mcp_call` operations without importing Gateway MCP modules
or treating client configuration as durable authority.

**Architecture:** `session/new` creates a provisional in-memory session after basic input-shape
validation, removes it if configuration admission fails, then uses an async, 30-second-bounded ACP
`allow_once` round trip to grant a session lease or retain an unavailable client-MCP state. An
agent-owned SDK adapter, owned by one bounded background event-loop
supervisor, opens lazily and returns an identity-bound guarded catalog. The session-owned service is
passed only as a non-serializable runtime argument through the ACP adapter, runner, planning loop, and
toolbox; safe untrusted results return to a subsequent planning turn while audit records retain only a
summary. The legacy manifest registry remains unchanged; an explicit client-authorizer branch in
`PreToolGuard` enforces leases, conservative effects, and one-call ACP approval without a manifest.

**Tech Stack:** Python 3.14, the official MCP Python SDK constrained to `mcp>=2.0,<3` only after a
separate dependency approval, its reviewed `httpx2` transitive stack, stdlib `multiprocessing.connection`,
keyring, pytest, pytest-asyncio, Ruff, real Docker/stdio and public Context7 MCP fixtures, and the
independently authored `acpx` ACP client for ACP live evidence.

## Global Constraints

- The approved design contract is
  `docs/superpowers/specs/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md`, frozen
  design-body SHA-256 `66606036b37ddc59cf9f2f4c8a713156a1f839fb771679a16937a5263c9ca4a2`.
- Implementation starts in a newly created worktree and branch from the then-current `main`, never
  from paused `agent/codex/plan-11-8-p11-feat-gateway-mcp`. This documentation draft makes neither.
- P11-FU-9 owns `session/new` disposition and a reusable interface only. It must not implement,
  advertise, or otherwise alter ACP `session/load`; that remains `P11-FEAT-ZED-RESUME`.
- Preserve exact no-op behavior for absent or empty `mcpServers`. Parse stdio as the untagged ACP
  variant. HTTP and SSE capability flags remain false until their adapters and gates are actually
  implemented and verified.
- Do not import `optimus_gateway` MCP modules, use Gateway credentials, signed Gateway profiles,
  Gateway accounting, Docker-only containment, or the Gateway `2026-07-28` protocol floor.
- A submitted server entry never authorizes a child process or outbound connection. Only an ACP
  `allow_once` session lease or an HMAC-protected CLI-authored durable transport record may do so.
  ACP must never offer `allow_always`.
- Client-owned header/env values are transient runtime capabilities: never in a model prompt,
  descriptor, tool result, planner state, telemetry, error payload, `repr`, serialization, argv, or
  a durable record. Construct, do not inherit, the stdio child environment.
- Use `CLIENT_MCP_CONFIG`, `MCP_INITIALIZE_RESULT`, and `MCP_DESCRIPTOR` scanner subjects. Server
  instructions, `serverInfo`, descriptors, and results remain untrusted and cannot alter policy,
  identity, approval, ceilings, or later fetch behavior.
- The model sees exactly generic `mcp_list_tools(server)` and `mcp_call(server, tool, arguments)`.
  They are static *intermediate-turn* directives: each yields bounded safe untrusted evidence to the
  next model turn, never a descriptor-derived model tool. Do not expose prompts, resources, sampling,
  or other MCP methods.
- The initial durable ceiling is `non_mutating` (read and network-read). Write calls require a
  `side_effect_eligible` record and ordinary per-call `PreToolGuard`/ACP approval. Declared effects
  are inputs, never authority; use the more restrictive declared-plus-tokenized-name classifier.
- All connection, initialize, discovery, and call waits are bounded to 30 seconds. Stdio message or
  result size is at most 1 MiB; catalog discovery is complete-or-absent with 100 pages, 1,000 tools,
  16 KiB per descriptor, 1 MiB total descriptors, and 30 seconds total.
- Before any `pyproject.toml` dependency-constraint or `uv.lock` mutation, stop and obtain explicit
  operator approval for the exact SDK version and reviewed transitive graph, including `httpx2`.
  Unconditional test-marker registration and scratch-file ignore rules below do not depend on that
  gate. No test double is proof of an SDK injected-client or byte-budget composition claim.
- Do not touch paused Plan 11.8 Tasks 8-9, its plan file, `tmp/`, authoritative PDFs, or the charter.
  Keep the named deferred entries for descriptor pinning/allowlists, durable HTTP/SSE relaxation,
  authenticated-upstream evidence, and the Plan 11.8 Windows flake in the consolidated backlog.
- Every task begins RED, runs the named focused test before and after minimal implementation, and
  ends at a reviewer checkpoint. Commit, push, and checkbox completion each require separate
  authorization after the stated verification command passes.
- For a non-empty valid array, `session/new` awaits one 30-second-bounded transport-permission round
  trip. The request contains only opaque candidate id, safe name/transport/fingerprint metadata, and
  `allow_once`/`reject_once` options. Allow creates a lease; reject, timeout, or outbound failure still
  returns a usable session with that server unavailable and no connection opened. Invalid input removes
  the provisional in-memory session and returns invalid request. Absent/empty arrays do not request
  permission and retain the existing immediate response.
- `ClientMcpToolService` is a session-scoped, non-serializable runtime protocol defined in
  `client_catalog.py`; it is never placed in `AgentRunRequest`, plan storage, telemetry, or a Pydantic
  dump. `AgentRunner.run(..., client_mcp_service=..., mcp_permission_broker=...)` and its planning-loop
  and toolbox calls thread it as keyword-only runtime state. A safe `AgentMcpToolOutput` is distinct
  from the audit-only `AgentToolCall` and is never added to `AgentRunResult`.
- Client MCP authorization has a distinct `PreToolRequest.mcp_authority="client_session"` branch. It
  validates lease, identity-bound catalog, descriptor, effect ceiling, and actual arguments before the
  permission decision. Read/network-read under an active lease are allowed without plan approval;
  writes require an opaque one-call ACP approval token bound to session, server, tool, and canonical
  arguments. `mcp_authority="legacy_manifest"` retains the exact existing registry/manifest path.

---

## File responsibility map

| Path | Responsibility |
|---|---|
| `src/optimus/mcp/client_config.py` | ACP entry parsing, canonical identity, opaque secret runtime capabilities, safe audit views, scanner admission, and serialization refusal. |
| `src/optimus/mcp/client_trust.py` | Durable client-MCP HMAC record schema, effect ceilings, session leases, and identity-bound record lookup. |
| `src/optimus/mcp/local_ipc.py` | Production-local AF_PIPE/AF_UNIX read-only pending-candidate IPC extracted from the Plan 11.7 construction. |
| `src/optimus/mcp/client_supervisor.py` | Dedicated event-loop thread, lifecycle, bounded synchronous bridge, ownership, cancellation, and process-tree teardown seams. |
| `src/optimus/mcp/client_sdk.py` | SDK-only stdio/HTTP/SSE adapters, negotiated-version handling, injected hardened HTTP client, initialize/result containment, and bounded discovery/calls. |
| `src/optimus/mcp/client_catalog.py` | Client-only descriptor scan/normalization, conservative effects, complete catalog, and `PreToolGuard` authorizer. |
| `src/optimus/mcp/client_disposition.py` | Shared `ClientMcpDisposition` orchestration used by current `session/new` and future `session/load`. |
| `src/optimus/guardrails/prompt_injection.py` | New explicit scanner subjects only; preserve existing scanner behavior. |
| `src/optimus/guardrails/pre_tool.py`, `src/optimus/guardrails/permissions.py` | Client-versus-legacy MCP authority selection, actual-arguments non-serialization, effect-aware permission ordering, and legacy compatibility. |
| `src/optimus/acp/spec.py`, `src/optimus/acp/server.py`, `src/optimus/acp/bootstrap.py`, `src/optimus/acp/dispatcher.py` | Shared runtime construction, capability truthfulness, async `session/new` permission/disposition wiring, tracked request-task shutdown, and session teardown. |
| `src/optimus/acp/launch_approvals.py`, `src/optimus/acp/launch_approval_cli.py` | Separate MCP durable-record namespace/domains and `optimus-trust mcp review` manual/IPC ceremony. |
| `src/optimus/agent/models.py`, `src/optimus/agent/directives.py`, `src/optimus/agent/prompts.py`, `src/optimus/agent/planning_loop.py`, `src/optimus/agent/tools.py`, `src/optimus/agent/runner.py` | Static intermediate-turn spellings, safe result/audit separation, session-service propagation, and the two generic model-usable tools; no dynamic descriptor registration. |
| `tests/unit/mcp/test_client_*.py` | Unit coverage of normalization, trust, IPC, supervisor/SDK boundaries, catalog, disposition, and generic tools. |
| `tests/unit/acp/test_spec_protocol.py`, `tests/unit/acp/test_launch_approvals.py`, `tests/unit/acp/test_launch_approval_cli.py` | ACP and durable-ceremony behavior. |
| `tests/unit/guardrails/test_pre_tool_guard.py`, `tests/unit/guardrails/test_prompt_injection.py`, `tests/unit/agent/test_*.py` | Guard compatibility, scanner subjects, directive grammar, and agent-tool bridge. |
| `tests/integration/mcp/test_client_mcp_live.py`, `tests/e2e/test_client_mcp_acpx.py` | Real HTTP/stdio and independent ACP-client evidence, respectively; no project-authored client substitutes. |

## Task 1: Normalize ACP entries into secret-safe client identities

**Files:**

- Create: `src/optimus/mcp/client_config.py`
- Modify: `src/optimus/guardrails/prompt_injection.py`
- Modify: `src/optimus/mcp/__init__.py`
- Create: `tests/unit/mcp/test_client_config.py`
- Modify: `tests/unit/guardrails/test_prompt_injection.py`

**Interfaces:**

- Produces `ClientMcpConfigNormalizer.normalize(entries, *, workspace_root, controlled_path, hmac_key) -> tuple[ClientMcpRuntimeCapability, ...]`.
- `ClientMcpRuntimeCapability.safe_identity` exposes no raw credential value and supplies
  `safe_view()` only; dumping, pickling, reduction, and direct state access raise `TypeError`.
- Produces `ClientMcpSafeIdentity` keyed by `(transport, server_name, canonical_target, arguments,
  credential_name_fingerprints)` and rejects invalid/malformed inputs with a safe rule ID.

- [x] **Step 1: Write RED parsing and identity tests.**

  Cover absent/empty arrays as an exact no-op; ASCII model-safe names; duplicate server names;
  case-insensitive duplicate headers; platform-aware duplicate env names; ignored `_meta`; untagged
  stdio; tagged HTTP/SSE; controlled bare-command resolution; real-path/normcase/PATHEXT identity;
  canonical URL normalization; URL userinfo/fragment rejection; query-name display with
  value fingerprints; and same-name identity drift.

- [x] **Step 2: Run the RED selector.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_config.py tests/unit/guardrails/test_prompt_injection.py -q
  ```

  Expected: import/behavior failures because no client normalizer or scanner subjects exist.

- [x] **Step 3: Implement the smallest normalizer and opaque capability.**

  Use ACP wire arrays as arrays, reject duplicate names before scanning, resolve bare commands only
  with the controlled resolver, and launch/fingerprint only canonical paths. Add
  `TrustScanSubject.CLIENT_MCP_CONFIG` and `TrustScanSubject.MCP_INITIALIZE_RESULT`; scan raw input
  inside the normalizer, retain only safe rule IDs, and construct a child environment from an
  explicit minimal baseline plus approved env values. The baseline is empty on POSIX and only the
  agent's `SystemRoot` on Windows; it never contains `PATH`, a home directory, provider/Gateway
  credentials, or telemetry state. Reject injection-capable env names and make raw-value holders
  non-serializable by construction.

- [x] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_config.py tests/unit/guardrails/test_prompt_injection.py -q
  uv run --frozen ruff check src/optimus/mcp/client_config.py src/optimus/guardrails/prompt_injection.py tests/unit/mcp/test_client_config.py tests/unit/guardrails/test_prompt_injection.py
  ```

- [x] **Step 5: Reviewer checkpoint.**

  Record the exact normalizer tests and scanner findings. Do not commit, modify `tmp/`, or mark a
  checkbox without separate authorization.

## Task 2: Add identity-only durable trust, session leases, and local candidate IPC

**Files:**

- Create: `src/optimus/mcp/client_trust.py`
- Create: `src/optimus/mcp/local_ipc.py`
- Modify: `src/optimus/acp/launch_approvals.py`
- Modify: `src/optimus/acp/launch_approval_cli.py`
- Create: `tests/unit/mcp/test_client_trust.py`
- Create: `tests/unit/mcp/test_local_ipc.py`
- Modify: `tests/unit/acp/test_launch_approvals.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`

**Interfaces:**

- Produces `ClientMcpDurableStore.read(workspace_digest, server_name, identity_fingerprint)` and
  `write(record)` using a client-only namespace, schema, HMAC domains, and
  `MCP_POLICY_COMPATIBILITY` separate from launch approvals.
- Produces `ClientMcpLeaseAuthority.acquire_allow_once(...)` and `lookup_durable(...)`; neither
  opens a transport.
- Produces `PendingClientMcpCandidateEndpoint.publish(candidate)`, `consume_snapshot(id)`, and
  `close()`; IPC accepts read-only snapshot retrieval only.

- [x] **Step 1: Write RED durable-record and IPC tests.**

  Assert domain/policy/key separation from launch approvals; HMAC tamper rejection; record keying by
  workspace/name/identity; changed identity requiring a new ceremony; default `non_mutating` and
  explicit `side_effect_eligible` ceilings; session-only `allow_once`; AF_PIPE/AF_UNIX local-only
  addresses; TCP rejection; derived IPC auth key; retrieval one-time consumption; concurrent matching
  candidate behavior; pending-only listener lifetime; and manual review fallback when IPC is absent.

- [x] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_trust.py tests/unit/mcp/test_local_ipc.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_approval_cli.py -q
  ```

  Expected: no client record schema, lease authority, local IPC helper, or CLI subcommand.

- [x] **Step 3: Implement isolated record and IPC seams.**

  Reuse `KeyringApprovalStore.hmac_key` only as a root; derive client-record signature,
  credential-fingerprint, and IPC-auth subkeys with distinct domain strings. Follow the Plan 11.7
  relay's `Listener`/`Client`, AF_PIPE/AF_UNIX, temp-directory socket path, and network-address
  rejection pattern, but place production code under `src/`. Expose safe candidate provenance and
  immutable rendered fingerprint only; the CLI writes exactly the rendered fingerprint and never
  approves over IPC.

- [x] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_trust.py tests/unit/mcp/test_local_ipc.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_launch_approval_cli.py -q
  uv run --frozen ruff check src/optimus/mcp/client_trust.py src/optimus/mcp/local_ipc.py src/optimus/acp/launch_approvals.py src/optimus/acp/launch_approval_cli.py tests/unit/mcp/test_client_trust.py tests/unit/mcp/test_local_ipc.py
  ```

- [x] **Step 5: Reviewer checkpoint.**

  Review that the CLI is the only durable-record writer, no raw configuration crosses IPC/keyring,
  and no caller can actuate a session through the local socket.

## Task 3: Obtain the dependency decision, then build the bounded SDK supervisor

**Files:**

- Modify: `pyproject.toml` dependency constraint (only after explicit operator approval)
- Modify: `uv.lock` (only after explicit operator approval)
- Create: `src/optimus/mcp/client_supervisor.py`
- Create: `src/optimus/mcp/client_sdk.py`
- Create: `tests/unit/mcp/test_client_supervisor.py`
- Create: `tests/unit/mcp/test_client_sdk.py`

**Interfaces:**

- Produces `MCPAsyncSupervisor.start()`, `submit(coro, *, timeout_seconds)`, and `close()` with
  `RUNNING`, `STOPPING`, and `DEAD` states.
- Produces `ClientMcpSdkAdapter.open(runtime_capability) -> ClientMcpConnection`,
  `discover(connection)`, `call(connection, tool, arguments)`, and `close(connection)`.
- `ClientMcpConnection.negotiated_protocol_version` is populated only from successful
  `initialize.result.protocolVersion`.

- [x] **Step 1: Write RED supervisor and adapter contract tests without adding the dependency.**

  Use injected fake sessions/transports to prove bounded submission, dead/stopping-loop safe errors,
  cancellation, per-connection call serialization, per-session isolation, no retry/replay,
  process-wide connection-budget denial, remote reserved-address denial, redirect refusal, and no
  ambient proxy/credential inheritance, stdio 1 MiB framing overflow, remote streamed-byte overflow,
  per-operation 30-second deadlines, and safe DNS-rebinding residual disposition,
  downgrade-on-success (`2026-07-28` proposal and returned `2025-11-25`), malformed negotiated
  version rejection, initialize-result scanner denial, ignored prompts/resources capabilities, and
  complete process-tree teardown seam selection.

- [x] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_supervisor.py tests/unit/mcp/test_client_sdk.py -q
  ```

  Expected: no supervisor or SDK adapter imports.

- [x] **Step 3: Stop for the explicit dependency gate.**

  Present the resolved `mcp>=2.0,<3` version, exact `uv.lock` diff, and `httpx2` transitive review
  to the operator. Do not edit `pyproject.toml`, `uv.lock`, or install packages until approval is
  recorded. If declined, leave this task open and do not hand-roll a substitute client.

- [x] **Step 4: Implement the approved SDK seam and bounds.**

  After approval, constrain the dependency, freeze the exact lock, and prove the SDK accepts the
  injected `httpx2.AsyncClient` with `follow_redirects=False`, `trust_env=False`, explicit timeouts,
  and an Optimus-owned streamed byte budget. Record that fake adapter tests do not satisfy this
  composition claim; Task 8's real-SDK composition tier is required before the claim or its checkbox
  can close. Make the supervisor own all session context managers;
  give stdio incremental 1 MiB framing, a 30-second deadline, constructed env, and process-group/tree
  termination. Treat every initialize field as untrusted, take only returned protocol version, and
  ignore unsupported capabilities rather than rejecting a server that advertises them.

- [x] **Step 5: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_supervisor.py tests/unit/mcp/test_client_sdk.py -q
  uv run --frozen ruff check src/optimus/mcp/client_supervisor.py src/optimus/mcp/client_sdk.py tests/unit/mcp/test_client_supervisor.py tests/unit/mcp/test_client_sdk.py
  ```

- [x] **Step 6: Reviewer checkpoint.**

  Confirm no fake session/transport result is represented as proof of the SDK's hardened injected
  HTTP-client or streamed-byte composition; leave this task and the real-composition claim open until
  Task 8 records the actual SDK tier.

## Task 4: Guard complete client catalogs and authorize calls without a synthetic manifest

**Files:**

- Create: `src/optimus/mcp/client_catalog.py`
- Modify: `src/optimus/guardrails/mcp_trust.py`
- Modify: `src/optimus/guardrails/pre_tool.py`
- Modify: `src/optimus/guardrails/permissions.py`
- Create: `tests/unit/mcp/test_client_catalog.py`
- Modify: `tests/unit/guardrails/test_mcp_trust.py`
- Modify: `tests/unit/guardrails/test_pre_tool_guard.py`
- Modify: `tests/unit/guardrails/test_permissions.py`

**Interfaces:**

- Produces `ClientMcpDescriptorExposureAdapter.build(identity, raw_tools) -> ClientMcpCatalog`.
- Produces non-serializable `ClientMcpToolService` and `ClientMcpCallAuthorizer`. The service returns
  `(AgentMcpToolOutput, AgentToolCall)` only after guard authorization; the output is bounded safe
  untrusted model evidence and the call is audit-only.
- Produces `McpPermissionBroker.request_write(request) -> ClientMcpOneCallApproval | None`; its
  only concrete ACP implementation is supplied by Task 6. The opaque approval binds session, safe
  identity, descriptor name, canonical arguments digest, and one use.
- Extends `PreToolRequest` with `mcp_authority` (`legacy_manifest` or `client_session`),
  `mcp_arguments: Mapping[str, Any] | None`, and an opaque one-call approval token. None is
  serialized to audit subjects/events. `ClientMcpCallAuthorizer.authorize(request)` returns a
  client decision containing the effective effect and lease/catalog result.
- `PreToolGuard` dispatches the client branch before legacy manifest checks, then passes the effective
  effect to `PermissionPolicy`. A valid client read/network-read lease permits ALLOW; a write returns
  HOLD until its bound one-call token is supplied. The legacy registry/manifest branch and its order
  remain unchanged.

- [x] **Step 1: Write RED catalog and guard tests.**

  Cover descriptor count/page/byte/cursor/duplicate budget failures yielding no catalog; individual
  malformed or scanner-blocked soft drops; safe availability metadata for tools above a ceiling;
  identity mismatch; declared `readOnlyHint` failing to downgrade `delete`/`apply`; descriptor text
  and JSON schema not accidentally escalating a read tool; no global write scope; actual arguments
  passed to the guard but absent from audit; no-manifest client read/network-read ALLOW; client write
  HOLD then one-call-token ALLOW; token replay, cross-session use, tool/argument mismatch denial; and
  legacy registry/exposure behavior unchanged.

- [x] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py tests/unit/guardrails/test_mcp_trust.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_permissions.py -q
  ```

- [x] **Step 3: Implement the client-only catalog adapter and authorizer seam.**

  Extract only reusable descriptor scanning/normalization primitives from `mcp_trust.py`; do not
  change manifest registration, allowlists, or `_PERMISSION_SCOPE_LIMITS`. Classify client effects as
  the restrictive maximum of normalized declared metadata and tokenized tool-name evidence. Require
  current transport lease, catalog identity, descriptor membership, and durable ceiling before
  dispatch; let ordinary `PreToolGuard`/ACP approval decide every write-classified call.

- [x] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_catalog.py tests/unit/guardrails/test_mcp_trust.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_permissions.py -q
  uv run --frozen ruff check src/optimus/mcp/client_catalog.py src/optimus/guardrails/mcp_trust.py src/optimus/guardrails/pre_tool.py src/optimus/guardrails/permissions.py tests/unit/mcp/test_client_catalog.py tests/unit/guardrails/test_pre_tool_guard.py tests/unit/guardrails/test_permissions.py
  ```

- [x] **Step 5: Reviewer checkpoint.**

  Confirm client transport approval conveys no trust in descriptors/results and legacy local-manifest
  trust remains independently tested.

## Task 5: Make the two generic MCP operations usable by the model

**Files:**

- Modify: `src/optimus/agent/models.py`
- Modify: `src/optimus/agent/directives.py`
- Modify: `src/optimus/agent/prompts.py`
- Modify: `src/optimus/agent/planning_loop.py`
- Modify: `src/optimus/agent/tools.py`
- Modify: `src/optimus/agent/runner.py`
- Create: `tests/unit/agent/test_mcp_tool_directives.py`
- Modify: `tests/unit/agent/test_tools.py`
- Modify: `tests/unit/agent/test_prompts.py`
- Modify: `tests/unit/agent/test_planning_loop_runner.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**

- Adds exact static directives `MCP_LIST <server>` and
  `MCP_CALL <server> <tool> <canonical-json-object>` to both directive grammars. They are valid
  only as a single intermediate tool request, not as a final mutation plan or inside a WRITE body.
- Adds `AgentToolbox.mcp_list_tools(server)` and
  `AgentToolbox.mcp_call(server, tool, arguments)`, each returning
  `tuple[AgentMcpToolOutput, AgentToolCall]`. `AgentMcpToolOutput` is a bounded, safe, untrusted
  in-memory observation; `AgentToolCall` retains only tool name, summary, and authorization outcome.
- `AgentRunner.run`, `_run_once`, and `PlanningLoopRunner.run` accept keyword-only
  `client_mcp_service` and `mcp_permission_broker` runtime arguments. They are never fields on
  `AgentRunRequest`, state-store records, telemetry events, or `AgentRunResult`.
- `PlanningTurnKind.MCP_TOOL` executes exactly one generic service call, returns its safe output in
  the next turn's bounded untrusted MCP-evidence envelope, and never registers descriptor-derived
  model tools. A write-classified call uses the ACP broker to obtain a bound one-call token before
  rechecking `PreToolGuard`; denial/timeout returns a safe unavailable observation without dispatch.

- [ ] **Step 1: Write RED directive and toolbox tests.**

  Assert malformed JSON, unknown server/tool, unsafe names, unavailable leases, and non-object
  arguments fail safely; a model can list then call a catalog tool through only the two generic
  operations and receives each safe output on the next planning turn; safe outputs omit
  credentials/config/process detail/instructions; audit records omit output and arguments; no
  descriptor name becomes a new directive or model tool; both directive grammars recognize MCP
  boundaries outside WRITE bodies; and client service, broker, and outputs never enter an
  `AgentRunRequest.model_dump()`, persisted plan, or `AgentRunResult`.

- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/agent/test_mcp_tool_directives.py tests/unit/agent/test_tools.py tests/unit/agent/test_prompts.py -q
  ```

- [ ] **Step 3: Implement the static directive bridge.**

  Add `AgentMcpToolOutput` without altering the audit-only `AgentToolCall` schema. Extend
  `parse_agent_plan`, `parse_planning_turn`, `_is_final_directive_line`, and both prompts with only
  `MCP_LIST` and `MCP_CALL`; require a canonical JSON object; and make an intermediate MCP turn
  execute one injected service call before adding the bounded output to the next prompt's explicitly
  untrusted MCP evidence envelope. Thread the runtime service/broker through runner, planning loop,
  and toolbox by keyword-only arguments. Do not expose server instructions, descriptors without the
  exposure adapter, raw results beyond bounded safe output, or arbitrary MCP RPC.

- [ ] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/agent/test_mcp_tool_directives.py tests/unit/agent/test_tools.py tests/unit/agent/test_prompts.py tests/unit/agent/test_planning_loop_runner.py tests/unit/agent/test_runner.py -q
  uv run --frozen ruff check src/optimus/agent/models.py src/optimus/agent/directives.py src/optimus/agent/prompts.py src/optimus/agent/planning_loop.py src/optimus/agent/tools.py src/optimus/agent/runner.py tests/unit/agent/test_mcp_tool_directives.py
  ```

- [ ] **Step 5: Reviewer checkpoint.**

  Confirm MCP output is an untrusted next-turn observation rather than an audit summary or persisted
  plan/result field, and that the two generic operations are the only model-visible MCP surface.

## Task 6: Wire the shared disposition seam into ACP session/new truthfully

**Files:**

- Create: `src/optimus/mcp/client_disposition.py`
- Modify: `src/optimus/acp/spec.py`
- Modify: `src/optimus/acp/server.py`
- Modify: `src/optimus/acp/shapes.py`
- Modify: `src/optimus/acp/bootstrap.py`
- Modify: `src/optimus/acp/dispatcher.py`
- Modify: `tests/unit/acp/test_spec_protocol.py`
- Modify: `tests/unit/acp/test_stdio_ndjson.py`
- Modify: `tests/unit/acp/test_bootstrap.py`
- Create: `tests/unit/mcp/test_client_disposition.py`

**Interfaces:**

- Produces `await ClientMcpDisposition.disposition_for_new_session(session_id, cwd, entries,
  request_permission) -> ClientMcpSessionState`. It never opens transport. For a valid non-empty
  array, `request_permission` receives an opaque candidate id and safe view, awaits at most 30
  seconds, and returns allow/reject/timeout/outbound-failure; only allow creates a session lease.
- Produces `AcpMcpPermissionBroker`, which translates an otherwise-HOLD write decision into one
  30-second-bounded `session/request_permission` request with safe server/tool/effect/fingerprint
  metadata and only `allow_once`/`reject_once`. It returns a `ClientMcpOneCallApproval` only for an
  explicit allow result; reject, timeout, cancellation, or outbound error returns `None`.
- `AcpSpecSession` gains opaque `client_mcp_state`. `InMemoryAcpSpecSessionStore.close_all()` closes
  every state exactly once. `AcpDuplexAdapter.close_all()` first cancels outstanding ACP permission
  work, then closes session states; `AcpStreamServer` cancels and gathers tracked request tasks before
  calling it and closing the shared supervisor.
- `build_configured_server` builds one process-lifetime client-MCP runtime (store roots, supervisor,
  state registry, authorizer, and capability set) and passes its factory to `AcpStreamServer`/
  `AcpDuplexAdapter`; dispatcher/runner receive the same guard authorizer. No runtime capability is
  inserted into a Pydantic request or dispatcher payload.
- ACP initialize advertises `mcpCapabilities.http`/`sse` only after the corresponding adapter is
  implemented; no `loadSession` capability is added.

- [ ] **Step 1: Write RED ACP disposition tests.**

  Cover absent/empty exact no-op; malformed/duplicate config before any transport action; valid entry
  producing a pending safe approval disposition without opening transport; `session/new` awaiting
  `session/request_permission` with only opaque candidate/safe identity fields and `allow_once`/
  `reject_once` options; 30-second timeout and outbound failure returning a session with unavailable
  tools; `allow_once` creating a session lease only; durable record lookup; rejection leaving tools
  unavailable; safe permission text naming `optimus-trust mcp review`; invalid input removing its
  provisional session; process EOF, handler exception, and pending-request cancellation closing only
  owned session connections; and no `session/load` request/capability behavior change.

- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_bootstrap.py tests/unit/mcp/test_client_disposition.py -q
  ```

- [ ] **Step 3: Implement `ClientMcpDisposition` and session wiring.**

  Make `_handle_session_new` async and await it from `handle_client_request`. Create a provisional
  in-memory session after input-shape validation; normalize before any transport, remove it on
  normalization failure, and otherwise call the shared seam with an async broker that uses a new
  `build_client_mcp_permission_params()` shape. The payload contains only session id, opaque candidate
  id, safe server name/transport/fingerprint, and `allow_once`/`reject_once`; it never offers
  `allow_always`. On reject, timeout, or outbound error keep the session and mark the server
  unavailable. Thread the session service and per-call broker into runner calls without serializing
  them. Track every `process_request` task in `AcpStreamServer`; on EOF or exception cancel/gather
  them, call adapter/store `close_all()`, then close the supervisor. Keep future `session/load` as a
  documented consumer of this interface only.

- [ ] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_bootstrap.py tests/unit/mcp/test_client_disposition.py -q
  uv run --frozen ruff check src/optimus/mcp/client_disposition.py src/optimus/acp/spec.py src/optimus/acp/server.py src/optimus/acp/shapes.py src/optimus/acp/bootstrap.py src/optimus/acp/dispatcher.py tests/unit/acp/test_spec_protocol.py tests/unit/acp/test_stdio_ndjson.py tests/unit/acp/test_bootstrap.py tests/unit/mcp/test_client_disposition.py
  ```

- [ ] **Step 5: Reviewer checkpoint.**

  Verify the live ACP surface advertises only implemented transports and never starts a connection
  merely because a client supplied an entry.

## Task 7: Complete the CLI ceremony and safe observability boundary

**Files:**

- Modify: `src/optimus/acp/launch_approval_cli.py`
- Modify: `src/optimus/acp/launch_approvals.py`
- Modify: `src/optimus/acp/evidence_redaction_adapter.py`
- Modify: `tests/unit/acp/test_launch_approval_cli.py`
- Modify: `tests/unit/acp/test_launch_approvals.py`
- Modify: `tests/unit/acp/test_evidence_redaction_adapter.py`

**Interfaces:**

- Adds `optimus-trust mcp review` with IPC import and manual-entry modes, TTY-only authoring, safe
  provenance rendering, named credential fields, keyed fingerprints, and an explicit ceiling choice.
- Produces redacted client-MCP audit fields: provenance `client_supplied_acp`, transport,
  disposition/outcome, credential-presence/name/fingerprint metadata, never a raw value.

- [ ] **Step 1: Write RED ceremony and redaction tests.**

  Cover no TTY, unreadable/missing/expired candidate, rendering session/workspace/received-at and
  query/header/env names without values, immutable fingerprint round trip, manual fallback,
  selected ceiling persistence, record lookup after separate CLI exit, redaction under `repr`, error,
  structured safe-view and evidence paths, and no `gateway_brokered_mcp` telemetry label.

- [ ] **Step 2: Run the RED selectors.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_evidence_redaction_adapter.py -q
  ```

- [ ] **Step 3: Implement the TTY-only review flow and safe audit fields.**

  Add the `mcp review` subcommand without weakening current launch commands. Resolve the same trusted
  roots, receive a read-only candidate snapshot or manual input, display only safe identity/provenance
  data, require explicit confirmation, write only the client durable record, and redact all client
  runtime capability structures before any evidence/telemetry emission.

- [ ] **Step 4: Run focused GREEN and static fitness.**

  ```powershell
  uv run --frozen pytest tests/unit/acp/test_launch_approval_cli.py tests/unit/acp/test_launch_approvals.py tests/unit/acp/test_evidence_redaction_adapter.py -q
  uv run --frozen ruff check src/optimus/acp/launch_approval_cli.py src/optimus/acp/launch_approvals.py src/optimus/acp/evidence_redaction_adapter.py tests/unit/acp/test_launch_approval_cli.py
  ```

- [ ] **Step 5: Reviewer checkpoint.**

  Confirm the CLI is the only durable client-MCP record writer, IPC remains read-only, and safe
  observability cannot collapse client credentials/configuration or tool output into Gateway telemetry.

## Task 8: Prove live protocol, transport, and ACP behavior with real dependencies

**Files:**

- Create: `tests/integration/mcp/test_client_mcp_live.py`
- Create: `tests/integration/mcp/test_client_sdk_real.py`
- Create: `tests/e2e/test_client_mcp_acpx.py`
- Create: `tools/run_p11_fu_9_acpx_evidence.py`
- Create: `tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py`
- Create: `reports/p11-fu-9-client-mcp-live-evidence.md`
- Create: `reports/p11-fu-9-client-mcp-live-evidence.json`
- Modify: `pyproject.toml` (unconditional `requires_mcp_stdio` and `requires_mcp_http` marker and
  default-deselection registration; any SDK dependency constraint remains separately gated)
- Modify: `.gitignore` (unconditional local ACP/MCP scratch-file rules)

**Interfaces:**

- Uses a real independently authored pinned Terraform stdio fixture and the real public Context7 HTTP
  endpoint for credential-free evidence. Uses real `acpx`, not a project-authored ACP client, for the
  ACP protocol layer.
- Produces sanitized evidence of negotiation, permission/lease behavior, generic tool invocation,
  process teardown, transport/capability truthfulness, exact no-op empty arrays, real-SDK hardened
  HTTP-client/byte-budget composition, and no-secret environment boundary.

- [ ] **Step 1: Write RED live-evidence verifier tests.**

  Require recorded dependency identities, exact negotiated version from `initialize.result.protocolVersion`,
  no error-assumption logic, Context7 plain POST `Accept: application/json, text/event-stream`,
  Terraform/Context7 initialize untrusted-field disposition, no dynamic tool registration, safe
  candidate/record fingerprints, redaction, and external ACP-client identity. Require the Terraform
  and Context7 probes to assert both observed legacy full-text false-positive distributions and the
  new tokenized-name distributions (`Terraform read=9/network=0/write=0`; `Context7
  read=2/network=0/write=0`). Require a real SDK test with no fake session/transport that proves the
  injected `httpx2.AsyncClient` flags and streamed byte wrapper take effect. Require acpx evidence
  for omitted/empty arrays and each actually advertised stdio/HTTP/SSE transport.

- [ ] **Step 2: Run the RED verifier selectors.**

  ```powershell
  uv run --frozen pytest tests/integration/mcp/test_client_mcp_live.py tests/integration/mcp/test_client_sdk_real.py tests/e2e/test_client_mcp_acpx.py tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py -q
  ```

  Expected: tests skip or fail until real-dependency configuration and evidence driver exist; skipped
  tests are not evidence.

- [ ] **Step 3: Implement only the evidence harness and run named real tiers.**

  First, unconditionally register `requires_mcp_stdio` and `requires_mcp_http` in `markers` and add
  `not requires_mcp_stdio` and `not requires_mcp_http` to the default `addopts` `-m` deselection
  expression. A clean P11-FU-9 branch from `main` does not have those markers; this registration is
  independent of SDK approval and keeps Task 9's bare `pytest -q` gate from running live Docker or
  network tiers. Then use `requires_mcp_stdio`, `requires_mcp_http`, `requires_acpx`, and `e2e`
  marker discipline. Run Terraform with its pinned digest, Context7 without a credential, and the
  actual official SDK path over the injected hardened HTTP client; no fake SDK/session/transport can
  satisfy the client-composition claim. The evidence helper must assert `git check-ignore -q` for
  `.acpxrc.json`, `mcpServers.json`, and `tmp/` before producing any scratch. It writes an ignored
  scratch `.acpxrc.json` with a structured Windows-safe `agents.optimus-fu9.argv` entry for the real
  agent and an ignored `mcpServers.json` containing the fixture array, then invokes:

  ```powershell
  acpx --mcp-config <scratch>/mcpServers.json --format json --approve-all --cwd <scratch> optimus-fu9 exec <task>
  ```

  The helper must invoke `acpx --version`, use `shell=False`, bounded timeout, and no project-authored
  ACP framing/client. Its verifier must parse only the real acpx JSONL fields needed for the evidence:
  client version/path digest, ACP negotiated version, advertised transport capabilities, session id,
  `allow_once` transport and write-call permission dispositions, generic tool-call titles, terminal
  stop reason, and no-op empty-array result. Raw transcript/config/debug stay in ignored scratch; the
  Markdown/JSON reports contain only hashes, versions, safe names, and content-free locators. On
  Windows run process-tree proof; on WSL2 run the equivalent POSIX group teardown proof in a separately
  authorized WSL worktree.

- [ ] **Step 4: Run live verification and final local fitness.**

  ```powershell
  uv run --frozen pytest -m requires_mcp_stdio tests/integration/mcp/test_client_mcp_live.py -q
  uv run --frozen pytest -m requires_mcp_http tests/integration/mcp/test_client_mcp_live.py -q
  uv run --frozen pytest -m requires_mcp_http tests/integration/mcp/test_client_sdk_real.py -q
  uv run --frozen pytest -m requires_acpx tests/e2e/test_client_mcp_acpx.py -q
  uv run --frozen pytest tests/unit/tools/test_run_p11_fu_9_acpx_evidence.py -q
  uv run --frozen pytest tests/unit/mcp tests/unit/acp tests/unit/guardrails tests/unit/agent -q
  uv run --frozen ruff check .
  git diff --check
  ```

- [ ] **Step 5: Platform and review checkpoint.**

  Reproduce subprocess/path/socket behavior in the separate WSL2 worktree before accepting Windows
  results as cross-platform proof. Record test commands, identities, negotiated versions, sanitized
  dispositions, and skipped/not-run tiers. Do not claim authenticated upstream support.

## Task 9: Audit documentation, deferred custody, and plan closure gates

**Files:**

- Modify: `README.md` only if the live implementation changes a current-state claim
- Modify: `docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md` only for
  evidence-backed status updates; preserve its named deferred entries
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` only if its current-state claim is stale
- Modify: this plan's status and checkboxes only after each stated verification passes
- Create: `reports/p11-fu-9-client-mcp-closure-evidence.md`
- Create: `tests/unit/mcp/test_client_mcp_closure.py`

**Interfaces:**

- Produces a claim-to-evidence map that distinguishes client-supplied ACP MCP from Gateway-brokered
  MCP and lists every deferred capability with an owning backlog entry.

- [ ] **Step 1: Write RED documentation/closure tests.**

  Require the closure evidence to name the approved design digest, real dependency artifacts,
  scanner/credential boundaries, current transport capability status, generic-tool-only model surface,
  session/new allow-once/timeout behavior, session shutdown ordering, real-SDK injected-client and
  byte-budget evidence, Terraform/Context7 legacy-versus-tokenized classifier distributions, acpx
  empty-array and per-advertised-transport evidence, `session/load` exclusion ownership, and the
  three P11-FU-9 deferrals plus the Plan 11.8 flake.

- [ ] **Step 2: Run the RED closure selector.**

  ```powershell
  uv run --frozen pytest tests/unit/mcp/test_client_mcp_closure.py -q
  ```

- [ ] **Step 3: Perform the documentation freshness audit and create closure evidence.**

  Audit every current-state claim in README, roadmap, and consolidated backlog. Update only factual
  prose made stale by this implementation; never rewrite frozen historical plan bodies. Keep durable
  descriptor pinning/tool allowlists, HTTP/SSE trust relaxation, authenticated-upstream evidence, and
  `session/load` visibly owned by their named backlog/charter entries.

- [ ] **Step 4: Run full final gates.**

  ```powershell
  uv run --frozen pytest -q
  uv run --frozen coverage run -m pytest
  uv run --frozen coverage report --fail-under=80
  uv run --frozen ruff check .
  git diff --check
  git status --short --branch
  ```

- [ ] **Step 5: Apply progress and integration gates only with authorization.**

  Mark a task checkbox only after its exact command passed and attach the named evidence. Before any
  commit, push, or PR, rerun Ruff and `git diff --check`, verify no reviewer checkpoint, secret,
  raw evidence, `tmp/`, paused Plan 11.8 work, or unrelated change is staged, and obtain explicit
  authorization.

- [ ] **Step 6: Reviewer closure checkpoint.**

  Independently verify the documentation freshness audit, every named evidence artifact, live-tier
  execution status, deferred-work ownership, clean staging boundary, and the exact commands recorded
  above before recommending the plan for closure.

## Plan self-review

**Spec coverage:** Tasks 1-2 cover normalization, secret residency, trust, records, and ceremony;
Tasks 3-4 cover SDK lifecycle, negotiated versions, bounds, initialize/descriptor trust, explicit
client-versus-legacy authorization, and one-call approval; Tasks 5-6 carry static generic operations
and their safe untrusted results through the real per-session ACP/agent path, including async
`session/new`, capability construction, and deterministic teardown; Tasks 7-9 cover ceremony UX,
real SDK/transport/acpx tiers, documentation, custody, and closure.
Gateway-only functionality, OAuth, descriptor pinning/allowlists, HTTP/SSE relaxation, authenticated
upstreams, and Plan 11.8 live evidence remain excluded with named custody.

**Placeholder scan:** The prohibited placeholder-marker scan is clean; every deferred capability has
named ownership. The dependency gate is deliberately a stop condition, not an implicit implementation
choice.

**Type consistency:** `ClientMcpDisposition` owns `ClientMcpSessionState`; that state exposes a
non-serializable `ClientMcpToolService` passed only as a runtime keyword argument through
`AcpDuplexAdapter`, `AgentRunner`, `PlanningLoopRunner`, and `AgentToolbox`. The service returns
`AgentMcpToolOutput` separately from its audit-only `AgentToolCall`. `ClientMcpCallAuthorizer` owns
only `mcp_authority="client_session"`; `MCPTrustRegistry` owns only `legacy_manifest`. No task
requires an `MCPServerManifest` for client entries.

## Implementation handoff

After independent approval, create an implementation worktree/branch from then-current `main` and
execute one task at a time with TDD and reviewer checkpoints. The first implementation action is
Task 1's RED test; Task 3 cannot mutate dependencies until the explicit operator gate is approved.
