# Plan 9.5 Working ACP Agent Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working local-first Optimus coding agent that a real ACP-capable IDE can spawn as an Agent Client Protocol stdio process, backed by the real Optimus Gateway, Redis-backed run state, persisted plan replay, guarded file/test execution, and protocol-level integration evidence.

**Architecture:** Keep `AgentRunner` as the task orchestrator, but make it production-runnable instead of only unit-test runnable. Add an ACP bootstrap layer that composes `OptimusGatewaySettings`, `GatewayClient`, `RedisAgentStateStore`, shared `PreToolGuard`, `AgentRunner`, `JsonRpcDispatcher`, and `AcpStreamServer`; add an Agent Client Protocol adapter using newline-delimited JSON-RPC with client-to-agent requests (`initialize`, `session/new`, `session/prompt`), client-to-agent `session/cancel` notification, and agent-to-client messages (`session/update`, `session/request_permission`) while retaining the existing `optimus.agent.run` Content-Length path as an internal compatibility surface. Add a stdio entrypoint for `python -m optimus.acp` and `optimus-agent`; persist plan records before approval and replay the stored plan on approval so a live Gateway is not called twice for different plan text.

**Tech Stack:** Python >=3.14, pydantic >=2.8, redis-py >=5, pytest, pytest-asyncio, pytest-cov, coverage.py, Ruff, existing `optimus.acp`, `optimus.agent`, `optimus.config`, `optimus.gateway`, `optimus.guardrails`, `optimus.runtime`, `optimus.tools`, `optimus.telemetry`, `optimus.golden`, and `optimus.release`.

## Global Constraints

- Build Phase 1 as a local-first Python ACP server with all provider access through the Optimus Gateway.
- Local runtime credentials are limited to `OPTIMUS_GATEWAY_URL` and `OPTIMUS_API_KEY`; no local Tavily, OpenAI, OpenRouter, GLM, LangSmith, Anthropic, Azure OpenAI, or provider keys.
- The running deliverable is a spawnable per-session stdio Agent Client Protocol process, not only importable Python classes.
- IDE-facing ACP conformance is in scope: newline-delimited JSON-RPC framing, client-to-agent requests `initialize`, `session/new`, and `session/prompt`; client-to-agent notification `session/cancel`; and agent-to-client `session/update` plus `session/request_permission`.
- The legacy Content-Length `optimus.agent.run` JSON-RPC method remains a lower-level compatibility/test path, not the IDE conformance path.
- Missing `OPTIMUS_GATEWAY_URL` or `OPTIMUS_API_KEY` must produce a clear operator action message naming the missing variables and must not crash with an opaque traceback.
- Production ACP bootstrap must require Redis-backed agent state. In-memory state is test-only.
- Redis configuration must not add a local secret. `OPTIMUS_REDIS_URL` may identify a local or pre-authenticated Redis endpoint, but URLs with username/password are rejected.
- Agent-mode approval must replay the exact stored plan text for the approved `run_id` and `plan_hash`; it must not call the Gateway to produce a new plan on the approval pass.
- Every side effect must pass through `AwaitingApproval`, `MutationGuard` / `assert_mutation_allowed()`, shared `PreToolGuard`, and `PermissionPolicy`.
- Agent tool execution must support guarded file read, guarded file write, and guarded test execution for `pytest` through the existing shell safety path.
- Gateway planning must use a versioned system prompt that mandates the directive grammar; unparseable plan text must return a typed `FAILED` result with a reason and must not silently succeed.
- The default production server path must never be `AcpStreamServer()` with an unconfigured `JsonRpcDispatcher()`.
- Redis connectivity must be checked at startup with `PING`; a down Redis instance must fail closed with an operator action message before serving IDE requests.
- Before sign-off, run Ruff, narrow tests, ACP integration tests, release-gate tests, and coverage. Aggregate production-code coverage must remain >=80%.

---

## Definition Of Done

> **Scope note (2026-07-07):** Plan 9.5 is the build plan. Live-dependency verification, real
> Gateway/Redis/E2E evidence, the committed transcripts, the Zed HITL artifact, LLD §10 Redis
> alignment, and the working-agent sign-off gate are owned by Plan 9.6
> (`docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md`).
> Items below that reference real-Gateway smoke evidence are satisfied via Plan 9.6; completing
> Plan 9.5 does not constitute working-agent sign-off.

> **Governance decision — plan-text persistence (Plan 9.6 Task L10, decided by owner 2026-07-08):**
> The Redis plan store (`agent:plan:{run_id}:{plan_hash}` HASH, `plan_text` field) persists raw
> plan text whose WRITE bodies contain file content. This is accepted as a **bounded exception**
> to Architecture §4's rule against unparsed source code in persistent stores, on these grounds:
> the plan store is short-TTL operational approval state (3600s `EXPIRE`, the control), keyed by
> `run_id`+`plan_hash`; it is not an index — nothing searches, embeds, or retrieves it by
> content; and replay correctness requires the exact text (a hash-only record cannot re-execute
> an approved plan after a process restart, which the Plan 9.6 L4/L6 restart-replay evidence
> depends on). This exception does NOT extend to long-lived or indexed structures: the Plan 10
> structural memory store (Architecture §6) remains bound by §4 — signatures, summaries, and
> relative paths only, never raw source code, even though it shares the same Redis instance.
> Same server, two governance zones: short-TTL operational keys may carry raw text; indexed
> structures may not.

Plan 9.5 is complete only when all of these are true:

- An ACP-capable IDE can launch `python -m optimus.acp --workspace-root <repo>` or `optimus-agent --workspace-root <repo>` as a stdio Agent Client Protocol server.
- The server passes protocol-level tests for newline-delimited JSON-RPC `initialize`, `session/new`, `session/prompt`, `session/cancel`, agent-to-client `session/update`, and agent-to-client `session/request_permission`.
- The launched server is wired to a real `GatewayClient`, real `AgentRunner`, Redis-backed plan/run state, configured workspace root, and one shared `PreToolGuard`.
- A framed ACP call to `optimus.agent.run` in Plan mode succeeds through `AcpStreamServer.handle_one()`.
- A framed two-call ACP Agent flow succeeds through `handle_one()`: first call returns `AWAITING_APPROVAL` and a `plan_hash`; second call carries `approval_id` plus `plan_hash`, replays the stored plan, mutates only after approval, and does not call the Gateway again.
- If Optimus credentials are missing, the spawnable entrypoint tells the operator exactly which variables to provide.
- If Redis state configuration is missing, unsafe, or unreachable, the spawnable entrypoint tells the operator exactly how to configure or start Redis.
- The README contains IDE launch instructions, required environment variables, sample ACP payloads, and the expected approval handshake.
- The real Gateway smoke run captures a checked-in redacted transcript proving the prompt, plan hash, approval replay, tool trajectory, and final state.
- Tests prove the behavior above without relying on hand-built object graphs alone.

## Explicit Exceptions

Anything not listed here is part of this completion plan.

- No GUI approval screen is built in this plan. The ACP client presents the agent's `session/request_permission` request to the user and returns the selected permission response; the adapter maps that response to `AgentApproval(approval_id, plan_hash)` internally.
- No 24x7 daemon, Windows service, launchd service, or background scheduler is built. The required deliverable is a spawnable stdio process that remains alive for the IDE session.
- No local provider keys are supported. Provider credentials remain behind the Optimus Gateway.
- No password-bearing Redis URL is supported locally. If Redis needs authentication, that must be supplied by the operator's environment outside this local runtime contract.
- No arbitrary shell execution is supported. The working coding-agent path supports guarded `pytest` execution and read-only `git status`, `git diff`, `git log`, and `git show` through the existing allowlist.
- No full web-search, MCP, browser, multi-agent scheduling, or reflection tool expansion is included in this completion plan. The runnable coding-agent deliverable is file read, file write, pytest validation, cost accounting, approval replay, Redis state, and ACP stdio integration.
- No IDE-specific extension package is built. Conformance is proven at the Agent Client Protocol stdio boundary so ACP-capable IDEs or their standard ACP launcher can drive the server.

## Source Anchors

- `AGENTS.md`
- `CONTRIBUTING.md`
- [Agent Client Protocol Prompt Turn](https://agentclientprotocol.com/protocol/prompt-turn)
- [Agent Client Protocol Initialization](https://agentclientprotocol.com/protocol/v1/initialization)
- [Agent Client Protocol Session Setup](https://agentclientprotocol.com/protocol/v1/session-setup)
- [Agent Client Protocol Transport](https://agentclientprotocol.com/protocol/v1/transports)
- [Agent Client Protocol Schema](https://agentclientprotocol.com/protocol/schema)
- [agentclientprotocol/agent-client-protocol](https://github.com/agentclientprotocol/agent-client-protocol)
- `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`
- `docs/superpowers/plans/2026-07-07-agent-orchestration-end-to-end-coding-workflow.md`
- `src/optimus/acp/server.py`
- `src/optimus/acp/dispatcher.py`
- `src/optimus/agent/runner.py`
- `src/optimus/agent/tools.py`
- `src/optimus/telemetry/redis_adapter.py`
- `src/optimus/config/gateway.py`
- `tests/integration/acp/test_server_stream.py`

## Current Live Gaps

- `JsonRpcDispatcher` can dispatch `optimus.agent.run`, but `AcpStreamServer()` still creates a default dispatcher without `AgentRunner`.
- There is no `python -m optimus.acp` entrypoint and no `console_scripts` entry.
- `tests/integration/acp/test_server_stream.py` proves framed ping and framing errors only, not framed `optimus.agent.run`.
- There is no Agent Client Protocol duplex adapter for client-to-agent `initialize`/`session/new`/`session/prompt`, client notification `session/cancel`, or agent-to-client `session/update`/`session/request_permission`.
- `AgentRunner` computes `plan_hash` from a Gateway response and re-runs the Gateway call on the approval pass instead of replaying stored plan text.
- Redis exists only as telemetry adapter plumbing. There is no Redis-backed agent plan/run state store.
- `AgentToolbox` has file read/write only. It does not expose the test-runner tool expected of a working coding agent.
- There is no versioned planner prompt contract or typed failure path for unparseable model output.
- Credential errors come from `OptimusGatewaySettings.from_env()` as generic `ValueError`; the spawnable operator path has no clear action-oriented message.

## File Structure

- Create: `src/optimus/agent/state_store.py` - agent plan/run state models, in-memory test store, Redis production store, and Redis URL validation.
- Create: `src/optimus/agent/prompts.py` - versioned planner system prompt and directive grammar.
- Create: `src/optimus/agent/directives.py` - directive parser and typed parse failures for `READ`, `WRITE`, and `TEST`.
- Create: `src/optimus/acp/spec.py` - Agent Client Protocol newline-delimited JSON-RPC adapter.
- Create: `tests/unit/agent/test_state_store.py`
- Create: `tests/unit/agent/test_prompts.py`
- Create: `tests/unit/agent/test_directives.py`
- Create: `tests/unit/acp/test_spec_protocol.py`
- Modify: `src/optimus/agent/models.py` - add fields needed to identify stored plan replay and test execution summaries.
- Modify: `src/optimus/agent/runner.py` - inject `AgentStateStore`, persist plans, replay approved plans, add guarded test execution.
- Modify: `src/optimus/agent/tools.py` - add `run_tests(command: tuple[str, ...]) -> AgentToolCall`.
- Create: `src/optimus/acp/bootstrap.py` - production composition and startup configuration errors.
- Create: `tests/unit/acp/test_bootstrap.py`
- Modify: `src/optimus/acp/server.py` - add continuous stdio serving support and require explicit production composition.
- Create: `src/optimus/acp/__main__.py` - `python -m optimus.acp` entrypoint.
- Modify: `pyproject.toml` - add `redis>=5` runtime dependency and `optimus-agent` console script.
- Modify: `tests/integration/acp/test_server_stream.py` - add framed Plan-mode and two-call approved Agent-mode tests through `handle_one()`.
- Modify: `tests/unit/agent/test_runner.py`
- Modify: `tests/unit/agent/test_tools.py`
- Modify: `tests/integration/agent/test_golden_harness_real_runner.py`
- Modify: `tools/run_phase1_release_gate.py` - make `--agent-harness` use production bootstrap components or a production-equivalent fake in tests.
- Modify: `tests/integration/release/test_phase1_release_gate_cli.py`
- Modify: `README.md` - IDE launch, credential, Redis, approval handshake, and smoke-test documentation.
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md` - mark this completion plan as mandatory for Plan 9.5 done.

## Task 0: Agent Client Protocol Spec Adapter

**Files:**
- Create: `src/optimus/acp/spec.py`
- Create: `tests/unit/acp/test_spec_protocol.py`
- Modify: `src/optimus/acp/server.py`

**Interfaces:**
- Produces: `AcpProtocolVersion = 1`, `AcpSpecSessionStore`, `AcpPromptTurn`, `AcpDuplexAdapter`, `AcpOutboundChannel`, `AcpPermissionResponse`.
- Produces: newline-delimited JSON-RPC parsing/writing for IDE-facing Agent Client Protocol sessions.
- Produces: async prompt-turn lifecycle where `session/prompt` remains pending while the agent sends `session/update` notifications and an agent-initiated `session/request_permission` request.

- [x] **Step 1: Write failing protocol tests**

Create `tests/unit/acp/test_spec_protocol.py`:

```python
import asyncio
from decimal import Decimal

from optimus.acp.spec import ACP_PROTOCOL_VERSION, AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.runtime.modes import ExecutionMode


class FakeRunner:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        if request.execution_mode is ExecutionMode.AGENT and not request.approval.approved:
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text="WRITE example.py\ncontent",
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                plan_hash="hash-1",
            )
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text="done",
            tool_calls=(AgentToolCall(tool_name="write_file", summary="wrote example.py"),),
            total_cost_usd=Decimal("0.002"),
            mutation_count=1,
            provider_keys_resolvable=(),
            plan_hash="hash-1",
        )


async def test_initialize_returns_spec_capabilities(tmp_path):
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "zed", "version": "1.0.0"},
            },
        }
    )

    assert response["result"]["protocolVersion"] == ACP_PROTOCOL_VERSION
    assert response["result"]["agentCapabilities"]["promptCapabilities"] == {
        "image": False,
        "audio": False,
        "embeddedContext": False,
    }
    assert response["result"]["agentCapabilities"]["sessionCapabilities"] == {}
    assert response["result"]["authMethods"] == []


async def test_session_prompt_sends_permission_request_and_keeps_prompt_pending(tmp_path):
    runner = FakeRunner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    new_response = await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    )
    session_id = new_response["result"]["sessionId"]

    prompt_task = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "Add a docstring"}],
                },
            }
        )
    )
    await outbound.wait_for_request("session/request_permission")

    assert not prompt_task.done()
    assert outbound.notifications[0]["method"] == "session/update"
    assert outbound.notifications[0]["params"]["update"]["sessionUpdate"] == "plan"
    permission_request = outbound.requests[0]
    assert permission_request["method"] == "session/request_permission"
    assert permission_request["params"]["sessionId"] == session_id
    assert permission_request["params"]["options"][0]["optionId"] == "approve"
    assert permission_request["params"]["options"][0]["metadata"]["planHash"] == "hash-1"

    outbound.respond(permission_request["id"], {"outcome": {"outcome": "cancelled"}})
    response = await prompt_task
    assert response["result"]["stopReason"] == "cancelled"


async def test_permission_response_replays_approved_plan_before_prompt_response(tmp_path):
    runner = FakeRunner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    prompt_task = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "Add a docstring"}],
                },
            }
        )
    )
    permission_request = await outbound.wait_for_request("session/request_permission")
    outbound.respond(
        permission_request["id"],
        {
            "outcome": {"outcome": "selected", "optionId": "approve"},
            "metadata": {"approvalId": "approval-1", "planHash": "hash-1"},
        }
    )
    response = await prompt_task

    assert response["result"]["stopReason"] == "end_turn"
    assert runner.requests[-1].approval.approved is True
    assert runner.requests[-1].approval.approval_id == "approval-1"
    assert runner.requests[-1].approval.plan_hash == "hash-1"
    assert any(
        notification["params"]["update"]["sessionUpdate"] == "tool_call_update"
        for notification in outbound.notifications
    )


async def test_session_cancel_resolves_prompt_and_pending_permission(tmp_path):
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=FakeRunner(), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]
    prompt_task = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "Add a docstring"}],
                },
            }
        )
    )
    permission_request = await outbound.wait_for_request("session/request_permission")

    await adapter.handle_client_notification(
        {
            "jsonrpc": "2.0",
            "method": "session/cancel",
            "params": {"sessionId": session_id},
        }
    )
    outbound.respond(permission_request["id"], {"outcome": {"outcome": "cancelled"}})

    response = await prompt_task
    assert response["result"]["stopReason"] == "cancelled"


async def test_client_calling_session_update_or_request_permission_is_method_not_found(tmp_path):
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
    )

    update_response = await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": 1, "method": "session/update", "params": {"sessionId": "session-1"}}
    )
    permission_response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/request_permission",
            "params": {"sessionId": "session-1"},
        }
    )

    assert update_response["error"]["code"] == -32601
    assert permission_response["error"]["code"] == -32601
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_spec_protocol.py -v
```

Expected: FAIL because `optimus.acp.spec` does not exist.

- [x] **Step 3: Implement ACP spec adapter**

Create `src/optimus/acp/spec.py` with:

- `ACP_PROTOCOL_VERSION = 1`.
- `RecordingOutboundChannel` for tests and a production outbound channel used by the ndjson server to send agent-to-client messages.
- `InMemoryAcpSpecSessionStore` for session IDs, cwd, prompt task state, pending permission request IDs, pending plan hashes, last emitted updates, and cancellation flags.
- `AcpDuplexAdapter.handle_client_request()` for client-to-agent requests:
  - `initialize`: require `params.protocolVersion`, return the negotiated integer `protocolVersion`, `agentCapabilities` with `promptCapabilities`, `sessionCapabilities`, `agentInfo`, and `authMethods`.
  - `session/new`: require `cwd`, validate it resolves inside configured `workspace_root`, and return a generated `sessionId`.
  - `session/prompt`: require `prompt` as `ContentBlock[]`; extract text blocks into a task; keep the JSON-RPC request pending until the turn completes; emit `session/update` notifications; when approval is needed, send an outbound `session/request_permission` request and await the correlated client response before replaying the stored plan.
  - Unknown client calls to `session/update` or `session/request_permission`: return JSON-RPC method-not-found because those are agent-to-client messages in this flow.
- `AcpDuplexAdapter.handle_client_notification()` for `session/cancel`: mark the active prompt turn cancelled, resolve any pending permission future as cancelled, stop further mutation, emit any final cancellation update, and complete the original pending `session/prompt` with `{"stopReason": "cancelled"}`.
- Prompt completion mapping:
  - completed plan/chat or approved Agent execution -> `{"stopReason": "end_turn"}`
  - `UNPARSEABLE_PLAN`, denied permission, missing plan replay, or policy refusal -> `{"stopReason": "refusal"}`
  - cancellation -> `{"stopReason": "cancelled"}`
- `session/update` notifications for:
  - `plan` when the stored plan is returned for review
  - `agent_message_chunk` for final user-visible text
  - `tool_call` / `tool_call_update` for file writes and test runs
  - `usage_update` when cost fields are available
- Agent-initiated `session/request_permission` request payload must include a permission option whose metadata carries `planHash`; the client response metadata carries `approvalId` and `planHash` back to the adapter.
- Schema validation: add a test fixture that downloads or vendors the official ACP v1 schema from the `agent-client-protocol` release referenced by the schema docs, then validates the initialize response, `session/prompt` params, `session/update` notifications, `session/request_permission` request, and final prompt response. If live download is not allowed in CI, vendor the exact schema JSON under `tests/fixtures/acp/acp-v1-schema.json` with source URL and retrieval date in a comment-bearing adjacent README.

Modify `src/optimus/acp/server.py` to add newline-delimited JSON-RPC serving for the spec adapter without breaking existing Content-Length `handle_one()` tests:

- `handle_one()` remains Content-Length for compatibility.
- `serve_ndjson(reader, writer, adapter)` reads one UTF-8 JSON object per line and supports duplex JSON-RPC:
  - client requests create tasks and eventually receive responses with matching IDs
  - client notifications receive no response
  - client responses are routed to pending outbound agent requests by ID
  - outbound agent notifications and requests can be written while a client `session/prompt` request remains pending
  - EOF cancels pending turns and exits cleanly

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/acp/test_spec_protocol.py tests/integration/acp/test_server_stream.py -v
```

Expected: PASS.

## Task 1: Redis-Backed Agent State Store

**Files:**
- Create: `src/optimus/agent/state_store.py`
- Create: `tests/unit/agent/test_state_store.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `AgentPlanRecord`, `AgentRunRecord`, `AgentStateStore`, `InMemoryAgentStateStore`, `RedisAgentStateStore`, `validate_redis_url(url: str) -> str`.
- Consumes later: `AgentRunner(..., state_store: AgentStateStore)`.

- [x] **Step 1: Write failing tests**

Create `tests/unit/agent/test_state_store.py`:

```python
from decimal import Decimal

import pytest

from optimus.agent.state_store import AgentPlanRecord, InMemoryAgentStateStore, RedisAgentStateStore, validate_redis_url
from optimus.runtime.modes import ExecutionMode


def plan_record() -> AgentPlanRecord:
    return AgentPlanRecord(
        run_id="run-1",
        session_id="session-1",
        task="Add a docstring",
        execution_mode=ExecutionMode.AGENT,
        workspace_root="/repo",
        plan_hash="hash-1",
        plan_text="WRITE example.py\ncontent",
        gateway_request_id="gw-1",
        model="glm-5.2",
        provider="glm",
        cost_usd=Decimal("0.002"),
        created_at_ms=1000,
        expires_at_ms=3_601_000,
    )


def test_in_memory_store_replays_exact_plan_text():
    store = InMemoryAgentStateStore()
    record = plan_record()

    store.save_plan(record)

    loaded = store.load_plan(run_id="run-1", plan_hash="hash-1")
    assert loaded == record
    assert loaded.plan_text == "WRITE example.py\ncontent"


def test_in_memory_store_rejects_missing_plan_hash():
    store = InMemoryAgentStateStore()

    with pytest.raises(KeyError, match="stored plan not found"):
        store.load_plan(run_id="run-1", plan_hash="missing")


def test_validate_redis_url_rejects_passwords():
    with pytest.raises(ValueError, match="must not contain username or password"):
        validate_redis_url("redis://user:secret@localhost:6379/0")


def test_redis_store_writes_hash_and_ttl():
    fake = FakeRedis()
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)

    store.save_plan(plan_record())

    assert fake.hsets[0][0] == "agent:plan:run-1:hash-1"
    assert fake.hsets[0][1]["plan_text"] == "WRITE example.py\ncontent"
    assert fake.expires == [("agent:plan:run-1:hash-1", 3600)]


def test_redis_store_ping_fails_closed_when_redis_is_down():
    fake = FakeRedis(ping_error=ConnectionError("redis unavailable"))
    store = RedisAgentStateStore(client=fake, ttl_seconds=3600)

    with pytest.raises(ConnectionError, match="redis unavailable"):
        store.ping()


def test_in_memory_store_treats_expired_plan_as_missing():
    store = InMemoryAgentStateStore(clock_ms=lambda: 3_700_000)
    store.save_plan(plan_record())

    with pytest.raises(KeyError, match="stored plan not found"):
        store.load_plan(run_id="run-1", plan_hash="hash-1")
```

Include the `FakeRedis` helper in the same test file with `hset`, `hgetall`, `expire`, and `ping` methods.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_state_store.py -v
```

Expected: FAIL because `optimus.agent.state_store` does not exist.

- [x] **Step 3: Implement state store**

Create `src/optimus/agent/state_store.py` with frozen pydantic records, a protocol, an in-memory implementation for tests, and a Redis implementation that stores plans at `agent:plan:{run_id}:{plan_hash}` with TTL.

Required behavior:

- Serialize `Decimal` as strings.
- Store `execution_mode` as its wire value.
- `load_plan()` raises `KeyError("stored plan not found")` when no record exists.
- `validate_redis_url()` accepts `redis://localhost:6379/0` and `rediss://cache.example.com:6380/0`, rejects any URL containing username or password, and rejects non-Redis schemes.
- `RedisAgentStateStore.from_url(url: str, ttl_seconds: int = 3600)` imports `redis.Redis` inside the method so unit tests do not require a real Redis server.
- `RedisAgentStateStore.ping()` calls `client.ping()` and lets bootstrap translate connectivity failures into `StartupConfigurationError`.
- `InMemoryAgentStateStore` accepts an optional `clock_ms` callable and treats expired records as missing so TTL behavior is testable without sleeping.

Modify `pyproject.toml`:

```toml
dependencies = [
  "confusable-homoglyphs>=3.3",
  "pydantic>=2.8",
  "redis>=5",
]
```

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/agent/test_state_store.py tests/unit/telemetry/test_redis_adapter.py -v
```

Expected: PASS.

## Task 2: Persist And Replay Approved Plans

**Files:**
- Modify: `src/optimus/agent/runner.py`
- Modify: `src/optimus/agent/models.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**
- Consumes: `AgentStateStore`.
- Produces: `AgentRunner(..., state_store: AgentStateStore)`.
- Produces behavior: first Agent call stores plan; approved call loads stored plan by `run_id` and `plan_hash`, executes that text, and does not call `GatewayClient.create_response()`.

- [x] **Step 1: Write failing replay tests**

Add to `tests/unit/agent/test_runner.py`:

```python
def test_approved_agent_run_replays_stored_plan_without_second_gateway_call(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n")
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)

    plan_result = runner.run(
        AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    )
    gateway.output_text = "WRITE example.py\nBROKEN SECOND PLAN\n"
    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert len(gateway.calls) == 1
    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in target.read_text(encoding="utf-8")
    assert "BROKEN SECOND PLAN" not in target.read_text(encoding="utf-8")
```

Also add a hash-mismatch test for the case where a stored pending plan exists for the run but the approval supplies a different `plan_hash`:

```python
def test_approved_agent_run_with_wrong_hash_returns_awaiting_approval_without_mutation(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    gateway = FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n")
    store = InMemoryAgentStateStore()
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=store)
    runner.run(AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="wrong-hash"),
        )
    )

    assert result.status is AgentRunStatus.AWAITING_APPROVAL
    assert result.mutation_count == 0
    assert "Return one" not in target.read_text(encoding="utf-8")
```

Add a cross-process replay shape test:

```python
def test_approved_agent_run_replays_plan_from_fresh_runner_with_shared_store(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    shared_store = InMemoryAgentStateStore()
    runner_a_gateway = FakeGatewayClient("WRITE example.py\ndef f():\n    \"\"\"Return one.\"\"\"\n    return 1\n")
    runner_a = AgentRunner(gateway_client=runner_a_gateway, model="glm-5.2", state_store=shared_store)
    plan_result = runner_a.run(
        AgentRunRequest(run_id="run-1", task="Add a docstring", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path)
    )
    runner_b_gateway = FakeGatewayClient("WRITE example.py\nBROKEN SECOND PLAN\n")
    runner_b = AgentRunner(gateway_client=runner_b_gateway, model="glm-5.2", state_store=shared_store)

    result = runner_b.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert runner_b_gateway.calls == []
    assert result.status is AgentRunStatus.COMPLETED
    assert "Return one" in target.read_text(encoding="utf-8")
```

Add an expired/unknown record message assertion:

```python
def test_approved_agent_run_reports_expired_or_unknown_plan_without_replanning(tmp_path):
    gateway = FakeGatewayClient("WRITE example.py\nBROKEN SECOND PLAN\n")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore())

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Add a docstring",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash="expired-plan"),
        )
    )

    assert gateway.calls == []
    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "PLAN_NOT_FOUND_OR_EXPIRED"
    assert "plan approval expired or was not found" in result.output_text.lower()
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_runner.py::test_approved_agent_run_replays_stored_plan_without_second_gateway_call -v
```

Expected: FAIL because `AgentRunner` has no state store and calls the Gateway again.

- [x] **Step 3: Implement replay**

Update `AgentRunner.__init__`:

```python
def __init__(..., state_store: AgentStateStore | None = None, clock_ms: Callable[[], int] | None = None) -> None:
    self._state_store = state_store or InMemoryAgentStateStore()
    self._clock_ms = clock_ms or _epoch_ms
```

Update `_run_once()`:

- If `request.execution_mode is ExecutionMode.AGENT` and `request.approval.approved` is true, load `AgentPlanRecord` before any Gateway call.
- If no stored record exists, the record expired, or the stored task/workspace/mode do not match the request, return `AgentRunStatus.FAILED`, `stop_reason="PLAN_NOT_FOUND_OR_EXPIRED"`, and output text telling the operator to re-run planning and approve the new plan. Do not re-plan automatically and do not mutate.
- If a pending plan exists for the run but the supplied approval hash does not match, return `AgentRunStatus.AWAITING_APPROVAL` with the stored plan hash and no mutation.
- Execute read/write/test directives from `record.plan_text`.
- Preserve the original `plan_hash`, `gateway_request_id`, and cost in `AgentRunResult`.
- On the non-approved planning pass, call Gateway once, compute `plan_hash`, and save `AgentPlanRecord` before returning `AWAITING_APPROVAL`.

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/agent/test_runner.py tests/unit/agent/test_state_store.py -v
```

Expected: PASS.

## Task 2A: Planner Prompt Contract And Directive Failures

**Files:**
- Create: `src/optimus/agent/prompts.py`
- Create: `src/optimus/agent/directives.py`
- Create: `tests/unit/agent/test_prompts.py`
- Create: `tests/unit/agent/test_directives.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**
- Produces: `AGENT_PLANNER_PROMPT_VERSION`, `build_agent_planner_input(task: str) -> str`.
- Produces: `parse_agent_plan(plan_text: str) -> AgentPlanDirectives`.
- Produces: typed parse failure `AgentDirectiveParseError`.

- [x] **Step 1: Write failing prompt and parser tests**

Create `tests/unit/agent/test_prompts.py`:

```python
from optimus.agent.prompts import AGENT_PLANNER_PROMPT_VERSION, build_agent_planner_input


def test_planner_prompt_mandates_directive_grammar():
    prompt = build_agent_planner_input("Add a docstring")

    assert AGENT_PLANNER_PROMPT_VERSION in prompt
    assert "READ <relative-path>" in prompt
    assert "WRITE <relative-path>" in prompt
    assert "TEST pytest <relative-test-path-or-args>" in prompt
    assert "Do not emit prose before the directives" in prompt
```

Create `tests/unit/agent/test_directives.py`:

```python
import pytest

from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan


def test_parse_agent_plan_accepts_read_write_and_test_directives():
    directives = parse_agent_plan("READ src/example.py\nWRITE src/example.py\ncontent\nTEST pytest tests/unit -q")

    assert directives.read_paths == ("src/example.py",)
    assert directives.write.path == "src/example.py"
    assert directives.tests == (("pytest", "tests/unit", "-q"),)


def test_parse_agent_plan_rejects_unparseable_text():
    with pytest.raises(AgentDirectiveParseError, match="no valid agent directives"):
        parse_agent_plan("Here is what I would do in prose.")


def test_parse_agent_plan_rejects_unsafe_test_directive():
    with pytest.raises(AgentDirectiveParseError, match="unsafe TEST directive"):
        parse_agent_plan("TEST python -c print(1)")
```

Add to `tests/unit/agent/test_runner.py`:

```python
def test_runner_sends_versioned_directive_prompt_to_gateway(tmp_path):
    gateway = FakeGatewayClient("READ example.py")
    runner = AgentRunner(gateway_client=gateway, model="glm-5.2")

    runner.run(AgentRunRequest(run_id="run-1", task="Explain", execution_mode=ExecutionMode.PLAN, workspace_root=tmp_path))

    assert "AGENT_PLANNER_PROMPT_VERSION" in gateway.calls[0]["input_text"]
    assert "READ <relative-path>" in gateway.calls[0]["input_text"]


def test_unparseable_agent_plan_fails_typed_without_silent_success(tmp_path):
    runner = AgentRunner(gateway_client=FakeGatewayClient("Here is prose, not directives."), model="glm-5.2")

    result = runner.run(AgentRunRequest(run_id="run-1", task="Do work", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "UNPARSEABLE_PLAN"
    assert result.mutation_count == 0
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_directives.py tests/unit/agent/test_runner.py -v
```

Expected: FAIL because prompt construction, directive parsing, and unparseable-plan failure semantics do not exist.

- [x] **Step 3: Implement prompt and parser**

Create `src/optimus/agent/prompts.py`:

- `AGENT_PLANNER_PROMPT_VERSION = "AGENT_PLANNER_PROMPT_VERSION:2026-07-07"`
- `build_agent_planner_input(task: str) -> str` returns a prompt containing the task and the exact directive grammar:
  - `READ <relative-path>`
  - `WRITE <relative-path>`
  - file content immediately after the `WRITE` line
  - `TEST pytest <relative-test-path-or-args>`
  - no prose before directives

Create `src/optimus/agent/directives.py`:

- Parse directives into a frozen dataclass or pydantic model.
- Reject absolute paths, `..`, empty paths, shell metacharacters, and non-`pytest` test commands.
- Reject unparseable text with `AgentDirectiveParseError("no valid agent directives")`.
- Reject unsafe test directives with `AgentDirectiveParseError("unsafe TEST directive: ...")`.

Update `AgentRunner` to:

- Send `build_agent_planner_input(request.task)` to the Gateway instead of raw task text.
- Store the raw user task separately in metadata.
- Parse plan text before returning success or awaiting approval.
- Return `AgentRunStatus.FAILED`, `stop_reason="UNPARSEABLE_PLAN"`, and no mutation when parsing fails.

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/agent/test_prompts.py tests/unit/agent/test_directives.py tests/unit/agent/test_runner.py -v
```

Expected: PASS.

## Task 3: Guarded Test Runner Tool

**Files:**
- Modify: `src/optimus/agent/tools.py`
- Modify: `src/optimus/agent/runner.py`
- Modify: `tests/unit/agent/test_tools.py`
- Modify: `tests/unit/agent/test_runner.py`

**Interfaces:**
- Produces: `AgentToolbox.run_tests(command: tuple[str, ...]) -> AgentToolCall`.
- Produces: directive parser support for `TEST pytest tests/path -q`.

- [x] **Step 1: Write failing tests**

Add to `tests/unit/agent/test_tools.py`:

```python
def test_toolbox_runs_pytest_through_guard(tmp_path):
    calls = []
    toolbox = AgentToolbox.for_workspace(
        workspace_root=tmp_path,
        context=approved_context(),
        run_id="run-1",
        shell_runner=lambda command: calls.append(command) or CompletedProcess(command, 0, "1 passed", ""),
    )

    call = toolbox.run_tests(("pytest", "tests/unit/agent", "-q"))

    assert calls == [["pytest", "tests/unit/agent", "-q"]]
    assert call.tool_name == "test_runner"
    assert call.authorization_outcome == "ALLOW"
```

Add to `tests/unit/agent/test_runner.py`:

```python
def test_agent_runner_executes_test_directive_after_approval(tmp_path):
    gateway = FakeGatewayClient("TEST pytest tests/unit/agent -q")
    store = InMemoryAgentStateStore()
    shell_calls = []
    runner = AgentRunner(
        gateway_client=gateway,
        model="glm-5.2",
        state_store=store,
        shell_runner=lambda command: shell_calls.append(command) or CompletedProcess(command, 0, "ok", ""),
    )
    plan_result = runner.run(AgentRunRequest(run_id="run-1", task="Run tests", execution_mode=ExecutionMode.AGENT, workspace_root=tmp_path))

    result = runner.run(
        AgentRunRequest(
            run_id="run-1",
            task="Run tests",
            execution_mode=ExecutionMode.AGENT,
            workspace_root=tmp_path,
            approval=AgentApproval(approved=True, approval_id="approval-1", plan_hash=plan_result.plan_hash),
        )
    )

    assert shell_calls == [["pytest", "tests/unit/agent", "-q"]]
    assert tuple(call.tool_name for call in result.tool_calls) == ("test_runner",)
```

Add parser-level rejection coverage in `tests/unit/agent/test_directives.py`:

```python
@pytest.mark.parametrize(
    "plan_text",
    (
        "TEST python -m pytest tests/unit",
        "TEST pytest ../outside -q",
        "TEST pytest tests/unit; rm -rf .",
        "TEST pytest C:/repo/tests",
        "TEST pytest tests/unit && pytest tests/integration",
    ),
)
def test_test_directive_rejects_non_pytest_or_unsafe_tokens(plan_text):
    with pytest.raises(AgentDirectiveParseError, match="unsafe TEST directive"):
        parse_agent_plan(plan_text)
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/agent/test_tools.py tests/unit/agent/test_runner.py -v
```

Expected: FAIL because `run_tests` and `TEST` directives do not exist.

- [x] **Step 3: Implement guarded test runner**

Update `AgentToolbox.for_workspace()` to accept `shell_runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None`.

Implement `run_tests()` by calling `optimus.tools.mutation_tools.shell_exec(command, context=self._context, runner=self._shell_runner, guard=self._guard)` and returning an `AgentToolCall` with:

- `tool_name="test_runner"`
- `summary="ran pytest tests/unit/agent -q exit=0"` for successful runs
- `authorization_outcome="ALLOW"`

Update `AgentRunner` to parse `TEST` directives only on approved Agent execution. Plan/Chat mode must not execute tests.

The `TEST` parser must enforce all of the following before `shell_exec()` is reached:

- First token must be exactly `pytest`.
- Path-like tokens must be relative workspace paths.
- No token may contain `..`.
- No token may contain shell metacharacters such as `;`, `&&`, `|`, backticks, `$(`, or redirection.
- Execution cwd is pinned to `request.workspace_root`.
- Rejected test directives produce `AgentRunStatus.FAILED`, `stop_reason="UNSAFE_TEST_DIRECTIVE"`, and no shell execution.

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/agent/test_tools.py tests/unit/agent/test_runner.py tests/unit/guardrails/test_command_safety.py -v
```

Expected: PASS.

## Task 4: Production ACP Bootstrap And Credential Messages

**Files:**
- Create: `src/optimus/acp/bootstrap.py`
- Create: `tests/unit/acp/test_bootstrap.py`
- Modify: `src/optimus/acp/server.py`

**Interfaces:**
- Produces: `build_configured_server(environ: Mapping[str, str], workspace_root: Path | None = None, model: str | None = None) -> AcpStreamServer`.
- Produces: `StartupConfigurationError` with `exit_code: int`, `user_message: str`, and `missing_names: tuple[str, ...]`.

- [x] **Step 1: Write failing bootstrap tests**

Create `tests/unit/acp/test_bootstrap.py`:

```python
from pathlib import Path

import pytest

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server


def test_bootstrap_reports_missing_optimus_credentials(tmp_path):
    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ={"OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}, workspace_root=tmp_path)

    assert exc_info.value.exit_code == 2
    assert exc_info.value.missing_names == ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY")
    assert "Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY" in exc_info.value.user_message


def test_bootstrap_reports_missing_redis_url(tmp_path):
    env = {"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_API_KEY": "opt-test"}

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(environ=env, workspace_root=tmp_path)

    assert exc_info.value.missing_names == ("OPTIMUS_REDIS_URL",)
    assert "Set OPTIMUS_REDIS_URL=redis://localhost:6379/0" in exc_info.value.user_message


def test_bootstrap_builds_agent_configured_server(tmp_path, monkeypatch):
    class FakeStore:
        def ping(self):
            return None

    fake_store = FakeStore()
    monkeypatch.setattr("optimus.acp.bootstrap.RedisAgentStateStore.from_url", lambda url, ttl_seconds=3600: fake_store)
    server = build_configured_server(
        environ={
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
        },
        workspace_root=tmp_path,
        model="glm-5.2",
    )

    assert server is not None


def test_bootstrap_reports_unreachable_redis(tmp_path, monkeypatch):
    class DownRedisStore:
        def ping(self):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr("optimus.acp.bootstrap.RedisAgentStateStore.from_url", lambda url, ttl_seconds=3600: DownRedisStore())

    with pytest.raises(StartupConfigurationError) as exc_info:
        build_configured_server(
            environ={
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://localhost:6379/0",
            },
            workspace_root=tmp_path,
        )

    assert exc_info.value.exit_code == 2
    assert "Redis is not reachable" in exc_info.value.user_message
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_bootstrap.py -v
```

Expected: FAIL because `optimus.acp.bootstrap` does not exist.

- [x] **Step 3: Implement bootstrap**

`build_configured_server()` must:

- Validate missing Optimus credentials before constructing `OptimusGatewaySettings`.
- Validate missing or unsafe `OPTIMUS_REDIS_URL`.
- Call `state_store.ping()` during startup and translate connection failures into `StartupConfigurationError(exit_code=2, user_message="Redis is not reachable. Start Redis or set OPTIMUS_REDIS_URL=redis://localhost:6379/0.")`.
- Build one `PreToolGuard.for_workspace(workspace_root=resolved_workspace, allowed_network_hosts=())`.
- Build `GatewayClient(settings=settings)`.
- Build `RedisAgentStateStore.from_url(redis_url)`.
- Build `AgentRunner(gateway_client=gateway_client, model=model or env.get("OPTIMUS_AGENT_MODEL", "glm-5.2"), guard=guard, state_store=state_store)`.
- Build `JsonRpcDispatcher(gateway_client=gateway_client, agent_runner=agent_runner, pre_tool_guard=guard, workspace_root=resolved_workspace)`.
- Return `AcpStreamServer(dispatcher=dispatcher)`.

`StartupConfigurationError.user_message` must be safe for stderr and must never include secret values.

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/acp/test_bootstrap.py tests/unit/config/test_gateway_settings.py -v
```

Expected: PASS.

## Task 5: Spawnable Stdio ACP Entrypoint

**Files:**
- Modify: `src/optimus/acp/server.py`
- Create: `src/optimus/acp/__main__.py`
- Modify: `pyproject.toml`
- Create: `tests/unit/acp/test_entrypoint.py`

**Interfaces:**
- Produces: `async def serve(reader: AsyncByteReader, writer: AsyncByteWriter) -> None` on `AcpStreamServer`.
- Produces: `python -m optimus.acp`.
- Produces: `optimus-agent` console script.

- [x] **Step 1: Write failing tests**

Create `tests/unit/acp/test_entrypoint.py`:

```python
import runpy
from pathlib import Path


def test_pyproject_declares_optimus_agent_console_script():
    text = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in text
    assert 'optimus-agent = "optimus.acp.__main__:main"' in text


def test_module_entrypoint_exists():
    module_globals = runpy.run_module("optimus.acp.__main__", run_name="optimus.acp.__main__")

    assert "main" in module_globals
```

Add a server loop test to `tests/integration/acp/test_server_stream.py` that feeds two framed ping messages and asserts two framed responses are written before EOF.

Add an EOF/error-loop regression:

```python
async def test_serve_exits_cleanly_on_eof_after_framing_error():
    reader = MemoryReader([b"Content-Length: 1\r\n\r\n{", b""])
    writer = MemoryWriter()
    server = AcpStreamServer()

    await server.serve(reader, writer)

    responses = decode_all_framed_responses(bytes(writer.data))
    assert len(responses) == 1
    assert responses[0]["error"]["message"] == "invalid JSON body"
```

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/acp/test_entrypoint.py tests/integration/acp/test_server_stream.py -v
```

Expected: FAIL because no module entrypoint, no script, and no continuous serve loop exist.

- [x] **Step 3: Implement entrypoint**

In `src/optimus/acp/server.py`:

- Keep `handle_one()` for tests and single-message callers.
- Add `serve()` that repeatedly calls `handle_one()` until `read_message()` reaches EOF through the existing framing path.
- Distinguish clean EOF from `FramingError`: EOF exits the loop without writing an error response; malformed input writes one error response and then exits if the next read is EOF. Garbage input must not create an infinite error-response loop.
- Add stdio reader/writer wrappers that use `asyncio.to_thread()` around `sys.stdin.buffer.read`, `sys.stdout.buffer.write`, and `sys.stdout.buffer.flush`.

Create `src/optimus/acp/__main__.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from optimus.acp.bootstrap import StartupConfigurationError, build_configured_server
from optimus.acp.server import StdioByteReader, StdioByteWriter


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="optimus-agent")
    parser.add_argument("--workspace-root", default=".", help="Workspace root exposed to the ACP agent.")
    parser.add_argument("--model", default=None, help="Gateway model for agent planning.")
    parser.add_argument("--check-config", action="store_true", help="Validate configuration and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        server = build_configured_server(environ=os.environ, workspace_root=Path(args.workspace_root), model=args.model)
    except StartupConfigurationError as exc:
        print(exc.user_message, file=sys.stderr)
        return exc.exit_code
    if args.check_config:
        print("Optimus ACP agent configuration OK.", file=sys.stderr)
        return 0
    asyncio.run(server.serve(StdioByteReader(sys.stdin.buffer), StdioByteWriter(sys.stdout.buffer)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Modify `pyproject.toml`:

```toml
[project.scripts]
optimus-agent = "optimus.acp.__main__:main"
```

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/unit/acp/test_entrypoint.py tests/unit/acp/test_bootstrap.py tests/integration/acp/test_server_stream.py -v
```

Expected: PASS.

## Task 6: Framed `optimus.agent.run` ACP Integration

**Files:**
- Modify: `tests/integration/acp/test_server_stream.py`
- Modify: `src/optimus/acp/dispatcher.py` only if the tests reveal missing response fields.
- Modify: `src/optimus/acp/spec.py` only if the tests reveal missing spec response fields.

**Interfaces:**
- Produces framed Plan-mode and approved Agent-mode integration evidence through `AcpStreamServer.handle_one()`.
- Produces newline-delimited Agent Client Protocol integration evidence through `AcpStreamServer.serve_ndjson()`.

- [x] **Step 1: Write failing framed integration tests**

Add to `tests/integration/acp/test_server_stream.py`:

```python
async def test_stream_handler_runs_agent_plan_mode_through_framed_acp(tmp_path):
    target = tmp_path / "example.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    server = configured_test_agent_server(tmp_path, output_text="READ example.py\nExplain it.")
    request = {
        "jsonrpc": "2.0",
        "id": "agent-plan",
        "method": "optimus.agent.run",
        "params": {
            "run_id": "run-1",
            "task": "Explain example.py",
            "execution_mode": "plan",
            "workspace_root": str(tmp_path),
        },
    }

    response = await roundtrip(server, request)

    assert response["result"]["status"] == "completed"
    assert response["result"]["tool_calls"][0]["tool_name"] == "file_reader"
```

Add a second test that uses one configured server instance and two framed `optimus.agent.run` calls:

- First call returns `awaiting_approval` plus `plan_hash`.
- Second call includes `approval: {"approved": true, "approval_id": "approval-1", "plan_hash": first_hash}`.
- The target file changes.
- The fake gateway call count remains `1`.

Add Agent Client Protocol ndjson integration tests:

```python
async def test_ndjson_spec_session_prompt_and_permission_flow(tmp_path):
    server = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    reader = InteractiveLineReader()
    writer = MemoryLineWriter()
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "zed", "version": "1.0.0"},
            },
        }
    )
    initialize_response = await writer.wait_for_response(1)
    assert initialize_response["result"]["protocolVersion"] == 1
    assert "agentCapabilities" in initialize_response["result"]

    await reader.send({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    session_response = await writer.wait_for_response(2)
    session_id = session_response["result"]["sessionId"]

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )
    permission_request = await writer.wait_for_request("session/request_permission")
    assert permission_request["params"]["sessionId"] == session_id
    plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]

    await reader.send(
        {
            "jsonrpc": "2.0",
            "id": permission_request["id"],
            "result": {
                "outcome": {"outcome": "selected", "optionId": "approve"},
                "metadata": {"approvalId": "approval-1", "planHash": plan_hash},
            },
        }
    )
    prompt_response = await writer.wait_for_response(3)

    assert prompt_response["result"]["stopReason"] == "end_turn"
    assert any(
        message["method"] == "session/update"
        and message["params"]["update"]["sessionUpdate"] in {"plan", "tool_call", "tool_call_update"}
        for message in writer.messages
    )
    assert server.fake_gateway_call_count == 1
    reader.close()
    await serve_task
```

The `InteractiveLineReader` helper must support appending client messages after the server has already emitted an agent-to-client request. This is required because a real ACP prompt turn is duplex: the server writes `session/request_permission` while the original `session/prompt` request remains pending, then routes the client's JSON-RPC response by outbound request ID.

- [x] **Step 2: Run tests to verify they fail before implementation**

Run:

```bash
pytest tests/integration/acp/test_server_stream.py -v
```

Expected before Tasks 2-5: FAIL because the production-like server is not wired and approval replay is missing.

- [x] **Step 3: Implement helper and fix response shape**

Use a `configured_test_agent_server()` helper in the test file that constructs the same object graph as production bootstrap but with fake gateway and `InMemoryAgentStateStore`. Do not bypass `AcpStreamServer.handle_one()` for the Content-Length path or `AcpStreamServer.serve_ndjson()` for the Agent Client Protocol path.

If `result.model_dump(mode="json")` does not serialize nested `Decimal` fields as strings consistently, fix that in `JsonRpcDispatcher` and add an assertion for `total_cost_usd`.

- [x] **Step 4: Run tests**

Run:

```bash
pytest tests/integration/acp/test_server_stream.py tests/unit/acp/test_dispatcher.py tests/unit/acp/test_spec_protocol.py -v
```

Expected: PASS.

## Task 7: README And Operator Launch Contract

**Files:**
- Modify: `README.md`
- Modify: `tests/integration/release/test_phase1_release_gate_cli.py`

**Interfaces:**
- Produces operator documentation that a reviewer can follow without chat context.

- [x] **Step 1: Add README assertions**

Add or update a text-presence test:

```python
def test_readme_documents_spawnable_acp_agent_contract():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "python -m optimus.acp --workspace-root" in text
    assert "optimus-agent --workspace-root" in text
    assert "OPTIMUS_REDIS_URL=redis://localhost:6379/0" in text
    assert "initialize" in text
    assert "session/new" in text
    assert "session/prompt" in text
    assert "session/request_permission" in text
    assert "agent_servers" in text
    assert "session/cancel" in text
    assert "approval_id" in text
    assert "plan_hash" in text
    assert "plan approval expires after 3600 seconds" in text
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/integration/release/test_phase1_release_gate_cli.py::test_readme_documents_spawnable_acp_agent_contract -v
```

Expected: FAIL until README is updated.

- [x] **Step 3: Update README**

Add a `Run The ACP Agent From An IDE` section containing:

- Required env:

```bash
export OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai
export OPTIMUS_API_KEY=...
export OPTIMUS_REDIS_URL=redis://localhost:6379/0
```

- Config check:

```bash
python -m optimus.acp --workspace-root . --check-config
```

- Launch command:

```bash
python -m optimus.acp --workspace-root .
```

- Console script equivalent:

```bash
optimus-agent --workspace-root .
```

- Zed settings example for the live demo:

```json
{
  "agent_servers": {
    "optimus": {
      "command": "optimus-agent",
      "args": ["--workspace-root", "."],
      "env": {
        "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
        "OPTIMUS_API_KEY": "set-in-your-local-environment",
        "OPTIMUS_REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

- Missing credentials behavior:

```text
Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.
```

- Approval handshake:
  - The IDE starts with `initialize`, creates a session with `session/new`, and sends work with `session/prompt`.
  - `session/prompt` remains pending while the agent emits `session/update` notifications.
  - When approval is needed, the agent sends `session/request_permission` to the IDE with plan text and `planHash`.
  - The IDE presents the returned plan text to the user and replies to the agent's outbound request with approval metadata containing `approvalId` and the same `planHash`.
  - The runtime replays the stored plan from Redis and does not call the Gateway again for a new plan.
  - Plan approval expires after 3600 seconds. If approval arrives after expiry, the runtime returns `PLAN_NOT_FOUND_OR_EXPIRED`; the IDE must ask the user to re-run planning and approve the new plan.
  - If the user cancels the turn, the IDE sends `session/cancel`; the runtime responds to the pending `session/prompt` with `stopReason="cancelled"`.

- [x] **Step 4: Run test**

Run:

```bash
pytest tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: PASS.

## Task 8: Release-Gate Wiring And Final Verification

**Files:**
- Modify: `tools/run_phase1_release_gate.py`
- Modify: `tests/integration/release/test_phase1_release_gate_cli.py`
- Modify: `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`

**Interfaces:**
- Produces: release-gate command path that can run Plan 9.5's real agent harness with production-equivalent bootstrap components.

- [x] **Step 1: Write failing release CLI assertions**

Add assertions that `tools/run_phase1_release_gate.py` includes:

- `OPTIMUS_REDIS_URL`
- `RedisAgentStateStore`
- `.ping()`
- `build_configured_server` or the same bootstrap composition pieces
- `PLAN_9_5_REAL_AGENT_TASK_IDS`
- `reports/plan-9-5-working-agent-smoke-transcript.json`

Add one behavioral release CLI test that monkeypatches Redis and Gateway fakes, runs the CLI with `--agent-harness`, and asserts the fake Redis store's `ping()` was called before golden task execution.

- [x] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/integration/release/test_phase1_release_gate_cli.py -v
```

Expected: FAIL until release CLI uses Redis-backed agent state for the real agent harness.

- [x] **Step 3: Wire release CLI**

When `--agent-harness` is used:

- Load `OptimusGatewaySettings.from_env()`.
- Require safe `OPTIMUS_REDIS_URL`.
- Build `RedisAgentStateStore.from_url(redis_url)`.
- Call `redis_store.ping()` and translate failures into the same operator-friendly Redis startup message used by ACP bootstrap.
- Build `AgentRunner(..., state_store=redis_store)`.
- Use `AgentGoldenTaskHarness` with that runner.
- Fail closed with the same operator-friendly missing variable messages as ACP bootstrap.
- Capture a redacted smoke transcript at `reports/plan-9-5-working-agent-smoke-transcript.json` when the real Gateway smoke run is executed. The transcript must include request IDs, run IDs, session IDs, model name, prompt version, plan hash, approval ID, tool names, final state, and cost fields; it must not include `OPTIMUS_API_KEY` or any provider key value.

- [x] **Step 4: Update roadmap**

In `docs/superpowers/plans/2026-07-01-phase-1-roadmap.md`, update Plan 9.5 status to say this completion plan is mandatory before Plan 9.5 is done:

```markdown
**Completion plan:** `docs/superpowers/plans/2026-07-07-plan-9-5-working-acp-agent-completion.md`

**Status:** Plan 9.5 is not complete until the completion plan delivers Agent Client Protocol conformance, a spawnable ACP stdio process, Redis-backed plan replay, framed compatibility tests for `optimus.agent.run`, Zed live-demo docs, and operator launch docs.
```

- [x] **Step 5: Run final verification**

Run:

```bash
python -m ruff check .
pytest tests/unit/agent tests/unit/acp tests/integration/acp tests/integration/agent tests/integration/release -v
pytest --cov=optimus --cov-branch --cov-report=term-missing
git diff --check
```

Expected:

- Ruff PASS.
- All listed tests PASS.
- Coverage remains >=80%.
- `git diff --check` PASS.

- [ ] **Step 6: Running deliverable smoke checks** *(transferred to Plan 9.6 Tasks L6/L7 — do not check here)*

With only these local credentials/config values present:

```bash
OPTIMUS_GATEWAY_URL=https://gateway.optimus.ai
OPTIMUS_API_KEY=<optimus key>
OPTIMUS_REDIS_URL=redis://localhost:6379/0
```

Run:

```bash
python -m optimus.acp --workspace-root . --check-config
python tools/run_phase1_release_gate.py --agent-harness --task-id explain-small-function --task-id docstring-single-function --task-id plan-then-approve-agent --task-id budget-exhausted
```

Expected:

- Config check exits 0 and writes `Optimus ACP agent configuration OK.` to stderr.
- Release gate reaches a real PASS/FAIL based on agent execution, not synthetic result JSON.
- `reports/plan-9-5-working-agent-smoke-transcript.json` is produced, redacted, and committed with the implementation PR as evidence.
- If Redis is down, the command fails closed with an operator action message.
- If Optimus credentials are missing, the command fails closed with an operator action message.

## Self-Review

- Working ACP agent: covered by Tasks 4, 5, 6, 7, and 8.
- ACP spec conformance: covered by Task 0 and ndjson integration in Task 6.
- Duplex prompt-turn lifecycle: covered by Task 0 and Task 6; client-to-agent versus agent-to-client direction is checked against the official ACP docs.
- Missing API keys ask: covered by Task 4 and README behavior in Task 7.
- Redis wiring and liveness: covered by Task 1, bootstrap in Task 4, and release CLI in Task 8.
- Running deliverable: covered by `python -m optimus.acp`, `optimus-agent`, `--check-config`, framed stream tests, and release smoke checks.
- Approval replay: covered by Task 2, cross-runner replay, and two-call framed test in Task 6.
- Planner directive robustness: covered by Task 2A and smoke transcript evidence in Task 8.
- Guarded coding tools: covered by file read/write from existing Plan 9.5 plus pytest runner and TEST validation in Task 3.
- Explicit exceptions: listed in the `Explicit Exceptions` section. No other Plan 9.5 working-agent behavior is excluded.
- Placeholder scan: this plan intentionally contains no placeholder tasks or unresolved follow-up section.
