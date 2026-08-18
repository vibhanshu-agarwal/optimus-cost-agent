import asyncio
import json
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.errors import METHOD_NOT_FOUND
from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.shapes import build_plan_session_update
from optimus.acp.spec import (
    _PLANNING_TERMINAL_STOP_REASONS,
    ACP_PROTOCOL_VERSION,
    AcpDuplexAdapter,
    InMemoryAcpSpecSessionStore,
    RecordingOutboundChannel,
    resolve_max_planning_turns,
)
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolRequest
from optimus.mcp.client_catalog import ClientMcpSessionService, ClientMcpToolService, arguments_digest
from optimus.mcp.client_config import ClientMcpConfigNormalizer, ClientMcpSafeIdentity
from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpSessionState
from optimus.mcp.client_trust import (
    ClientMcpDurableStore,
    ClientMcpLeaseAuthority,
    compute_identity_fingerprint,
    write_client_mcp_durable_from_fingerprint,
)
from optimus.runtime.modes import ExecutionMode, GenerationScope

_HMAC_KEY = b"p11-fu-9-disposition-test-hmac-key!!"


class _FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


class _SafeDispatchService(ClientMcpToolService):
    def _dispatch(self, tool_name: str, arguments: dict[str, Any]) -> str:
        del arguments
        return f"ok:{tool_name}"


def _http_identity(*, name: str = "tools") -> ClientMcpSafeIdentity:
    return ClientMcpSafeIdentity(
        transport="http",
        server_name=name,
        canonical_target="https://mcp.example.com/v1",
        arguments=(),
        credential_name_fingerprints=(),
    )


def _write_thing_pages() -> list[dict[str, object]]:
    return [
        {
            "tools": [
                {
                    "name": "write_thing",
                    "description": "Write a thing.",
                    "inputSchema": {"type": "object"},
                    "annotations": {"destructiveHint": True},
                }
            ]
        }
    ]


async def _lease_and_materialize_write_thing(session, tmp_path: Path) -> ClientMcpToolService:
    """Allow-once lease then register a real write service on the adapter session."""
    keyring = _FakeKeyring()
    launch = KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)
    store = ClientMcpDurableStore(keyring_backend=keyring, hmac_key=launch.hmac_key)
    identity = _http_identity()
    fingerprint = compute_identity_fingerprint(identity, hmac_key=_HMAC_KEY)
    write_client_mcp_durable_from_fingerprint(
        store=store,
        workspace_digest="d" * 64,
        identity=identity,
        rendered_fingerprint=fingerprint,
        effect_ceiling="side_effect_eligible",
    )
    disp = ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=store),
        hmac_key=_HMAC_KEY,
        controlled_path=str(tmp_path / "bin"),
        workspace_digest="d" * 64,
    )

    async def _allow(_params: dict[str, Any]) -> str:
        return "allow"

    state = await disp.disposition_for_new_session(
        session.session_id,
        tmp_path,
        [{"type": "http", "name": "tools", "url": "https://mcp.example.com/v1", "headers": []}],
        _allow,
    )
    session.client_mcp_state = state
    service = disp.materialize_tool_service(
        session.client_mcp_state,
        identity=identity,
        raw_tools=_write_thing_pages(),
        workspace_root=tmp_path,
        service_cls=_SafeDispatchService,
    )
    assert service is not None
    return service


class FakeRunner:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request, *, planning_progress_observer=None, client_mcp_service=None, mcp_permission_broker=None):
        del planning_progress_observer, client_mcp_service, mcp_permission_broker
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


def test_resolve_max_planning_turns_returns_none_when_unset():
    assert resolve_max_planning_turns({}) is None


def test_resolve_max_planning_turns_returns_none_when_blank():
    assert resolve_max_planning_turns({"OPTIMUS_MAX_PLANNING_TURNS": "   "}) is None


def test_gateway_failure_is_a_terminal_planning_stop() -> None:
    assert "PLANNING_GATEWAY_FAILURE" in _PLANNING_TERMINAL_STOP_REASONS


def test_resolve_max_planning_turns_parses_valid_value():
    assert resolve_max_planning_turns({"OPTIMUS_MAX_PLANNING_TURNS": "1"}) == 1


@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_resolve_max_planning_turns_rejects_invalid_values(raw):
    with pytest.raises(ValueError, match="OPTIMUS_MAX_PLANNING_TURNS"):
        resolve_max_planning_turns({"OPTIMUS_MAX_PLANNING_TURNS": raw})


class _RecordingCompletedRunner:
    """Returns COMPLETED immediately: no approval round-trip to drive."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request, *, planning_progress_observer=None, client_mcp_service=None, mcp_permission_broker=None):
        del planning_progress_observer, client_mcp_service, mcp_permission_broker
        self.requests.append(request)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="CHAT_ONLY",
            output_text="done",
            tool_calls=(),
            total_cost_usd=Decimal("0"),
            mutation_count=0,
            provider_keys_resolvable=(),
        )


async def test_session_prompt_applies_max_planning_turns_override(tmp_path):
    runner = _RecordingCompletedRunner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
        max_planning_turns=resolve_max_planning_turns({"OPTIMUS_MAX_PLANNING_TURNS": "1"}),
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )

    assert runner.requests[0].max_planning_turns == 1


async def test_session_prompt_uses_default_max_planning_turns_when_unset(tmp_path):
    runner = _RecordingCompletedRunner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
        max_planning_turns=resolve_max_planning_turns({}),
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )

    assert runner.requests[0].max_planning_turns == 3


async def test_session_prompt_never_lets_optimus_live_max_cost_usd_override_agent_run_request(tmp_path):
    """Plan 9.96, Task 5 Step 5 (bounded-model exception, condition 1):
    'The effective cost ceiling remains the approved or monotonic-safe Tier
    3 value' -- OPTIMUS_LIVE_MAX_COST_USD must never override
    AgentRunRequest.max_cost_usd (Global Constraint 12: 'The live-cost
    variable remains an evidence ceiling; this plan does not replace
    AgentRunRequest.max_cost_usd's existing runtime budget').

    Unlike OPTIMUS_MAX_PLANNING_TURNS, AcpDuplexAdapter has NO
    max_cost_usd/live_max_cost_usd constructor parameter at all -- there is
    no threading path for OPTIMUS_LIVE_MAX_COST_USD to reach
    AgentRunRequest through this adapter, by construction. This test locks
    that absence in as a regression guard: every AgentRunRequest actually
    constructed by _handle_session_prompt keeps max_cost_usd at its
    Pydantic default (Decimal("0.05")) regardless of what
    OPTIMUS_LIVE_MAX_COST_USD is set to in the process environment --
    proving the negative Step 5 explicitly asks for, not just asserting it
    by inspection."""
    import os

    runner = _RecordingCompletedRunner()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    # Set an aggressive OPTIMUS_LIVE_MAX_COST_USD in the real process
    # environment -- if any code path threaded it into AgentRunRequest, it
    # would show up here. os.environ is used deliberately (not passed to
    # the adapter) to prove there is no ambient-read path either.
    previous = os.environ.get("OPTIMUS_LIVE_MAX_COST_USD")
    os.environ["OPTIMUS_LIVE_MAX_COST_USD"] = "999.00"
    try:
        await adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
            }
        )
    finally:
        if previous is None:
            os.environ.pop("OPTIMUS_LIVE_MAX_COST_USD", None)
        else:
            os.environ["OPTIMUS_LIVE_MAX_COST_USD"] = previous

    assert runner.requests[0].max_cost_usd == Decimal("0.05")


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
    # P11-FU-9: do not advertise unimplemented HTTP/SSE or session/load.
    mcp_caps = response["result"]["agentCapabilities"].get("mcpCapabilities")
    if mcp_caps is not None:
        assert mcp_caps.get("http") is not True
        assert mcp_caps.get("sse") is not True
    assert "loadSession" not in response["result"]["agentCapabilities"].get("sessionCapabilities", {})


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
    assert outbound.notifications[0]["params"] == build_plan_session_update(
        session_id=session_id,
        plan_text="WRITE example.py\ncontent",
    )
    permission_request = outbound.requests[0]
    assert permission_request["method"] == "session/request_permission"
    assert permission_request["params"]["sessionId"] == session_id
    assert permission_request["params"]["options"][0]["optionId"] == "approve"
    assert permission_request["params"]["options"][0]["metadata"]["planHash"] == "hash-1"
    assert "toolCall" in permission_request["params"]
    assert permission_request["params"]["toolCall"]["toolCallId"]
    assert permission_request["params"]["toolCall"]["title"]
    assert "toolCallId" not in permission_request["params"]

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
        },
    )
    response = await prompt_task

    assert response["result"]["stopReason"] == "end_turn"
    assert runner.requests[-1].approval.approved is True
    assert runner.requests[-1].approval.approval_id.startswith("approval-")
    assert runner.requests[-1].approval.plan_hash == "hash-1"
    tool_calls = [
        notification["params"]["update"]
        for notification in outbound.notifications
        if notification["params"]["update"]["sessionUpdate"] == "tool_call"
    ]
    assert tool_calls
    assert "toolCallId" in tool_calls[0]
    assert "toolCall" not in tool_calls[0]
    assert all(
        notification["params"]["update"]["sessionUpdate"] != "tool_call_update"
        for notification in outbound.notifications
    )
    message_chunks = [
        notification["params"]["update"]
        for notification in outbound.notifications
        if notification["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert message_chunks
    assert message_chunks[0]["content"]["type"] == "text"
    completed_plans = [
        notification["params"]["update"]
        for notification in outbound.notifications
        if notification["params"]["update"]["sessionUpdate"] == "plan"
        and notification["params"]["update"]["entries"][0]["status"] == "completed"
    ]
    assert completed_plans


async def test_permission_cancel_option_does_not_execute_plan(tmp_path):
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
            "outcome": {"outcome": "selected", "optionId": "cancel"},
        },
    )
    response = await prompt_task

    assert response["result"]["stopReason"] == "cancelled"
    assert len(runner.requests) == 1
    assert runner.requests[0].approval.approved is False


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

    assert update_response["error"]["code"] == METHOD_NOT_FOUND
    assert permission_response["error"]["code"] == METHOD_NOT_FOUND


async def test_workspace_context_failure_surfaces_corrective_refusal_message(tmp_path):
    failure_text = (
        "Workspace reference 'example.py' is ambiguous. "
        "Candidates: a/example.py, b/example.py. Retry with one exact workspace-relative path."
    )

    class AmbiguousFailureRunner:
        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                status=AgentRunStatus.FAILED,
                final_state="FAILED",
                output_text=failure_text,
                tool_calls=(),
                total_cost_usd=Decimal("0"),
                mutation_count=0,
                provider_keys_resolvable=(),
                stop_reason="AMBIGUOUS_WORKSPACE_REFERENCE",
            )

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AmbiguousFailureRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Add a docstring to example.py"}],
            },
        }
    )

    assert response["result"]["stopReason"] == "refusal"
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == failure_text
    assert messages[-1] != "Turn completed."


async def test_unparseable_plan_completion_does_not_echo_raw_model_output(tmp_path):
    raw_sentinel = "UNIQUE_RAW_MODEL_SENTINEL_XYZ"
    corrective_text = (
        "Planning stopped after repeated responses that did not match the required directive grammar."
    )

    class UnparseablePlanRunner:
        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                status=AgentRunStatus.TERMINATED,
                final_state="TERMINATED",
                output_text=corrective_text,
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                stop_reason="PLANNING_UNPARSEABLE_RESPONSE",
                plan_hash=None,
            )

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=UnparseablePlanRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Do work"}],
            },
        }
    )

    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert response["result"]["stopReason"] == "end_turn"
    assert outbound.requests == []
    assert messages[-1] == corrective_text
    assert raw_sentinel not in messages[-1]


async def test_multi_turn_planning_emits_progress_before_final_permission(tmp_path):
    class MultiTurnRunner:
        def __init__(self) -> None:
            self.requests = []

        def run(self, request, *, planning_progress_observer=None):
            self.requests.append(request)
            if request.approval.approved:
                return AgentRunResult(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    execution_mode=request.execution_mode,
                    status=AgentRunStatus.COMPLETED,
                    final_state="COMPLETED",
                    output_text="done",
                    tool_calls=(AgentToolCall(tool_name="write_file", summary="wrote large.py"),),
                    total_cost_usd=Decimal("0.004"),
                    mutation_count=1,
                    provider_keys_resolvable=(),
                    plan_hash="hash-final",
                )
            if planning_progress_observer is not None:
                planning_progress_observer(
                    PlanningProgressEvent(
                        run_id=request.run_id,
                        session_id=request.session_id,
                        settled_turn=1,
                        max_planning_turns=3,
                        read_request_count=2,
                        read_identities=("large.py#bytes=0:5", "large.py#bytes=5:10"),
                        source_sha256s=("a" * 64, "b" * 64),
                        read_byte_counts=(5, 5),
                        total_cost_usd=Decimal("0.002"),
                        remaining_budget_usd=Decimal("0.048"),
                        gateway_request_ids=("gw-1",),
                    )
                )
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text="READ large.py\nWRITE large.py\nupdated\n",
                tool_calls=(),
                total_cost_usd=Decimal("0.004"),
                mutation_count=0,
                provider_keys_resolvable=(),
                plan_hash="hash-final",
            )

    runner = MultiTurnRunner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
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
                    "prompt": [{"type": "text", "text": "Edit large.py"}],
                },
            }
        )
    )
    permission_request = await outbound.wait_for_request("session/request_permission")
    outbound.respond(
        permission_request["id"],
        {"outcome": {"outcome": "selected", "optionId": "approve"}},
    )
    response = await prompt_task

    progress_chunks = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        and "Planning turn" in item["params"]["update"]["content"]["text"]
    ]
    assert progress_chunks == ["Planning turn 1 of 3: reading 2 guarded ranges."]
    assert len([item for item in outbound.requests if item["method"] == "session/request_permission"]) == 1
    assert permission_request["params"]["options"][0]["metadata"]["planHash"] == "hash-final"
    assert response["result"]["stopReason"] == "end_turn"


async def test_planning_failure_emits_end_turn_without_permission(tmp_path):
    corrective_text = "Planning stopped because the run budget was exhausted."

    class PlanningFailureRunner:
        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                status=AgentRunStatus.TERMINATED,
                final_state="TERMINATED",
                output_text=corrective_text,
                tool_calls=(),
                total_cost_usd=Decimal("0.05"),
                mutation_count=0,
                provider_keys_resolvable=(),
                stop_reason="PLANNING_BUDGET_EXHAUSTED",
                plan_hash=None,
            )

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=PlanningFailureRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Edit large.py"}],
            },
        }
    )

    assert response["result"]["stopReason"] == "end_turn"
    assert outbound.requests == []
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == corrective_text
    outbound_blob = str(outbound.requests) + str(outbound.notifications)
    assert "planHash" not in outbound_blob


async def test_planning_model_refused_emits_sanitized_text_without_permission(tmp_path):
    refusal = "Inspect <workspace>; token **********"

    class RefusalRunner:
        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                status=AgentRunStatus.FAILED,
                final_state="FAILED",
                output_text=refusal,
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                stop_reason="PLANNING_MODEL_REFUSED",
                plan_hash=None,
            )

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=RefusalRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Edit large.py"}],
            },
        }
    )

    assert response["result"]["stopReason"] == "end_turn"
    assert outbound.requests == []
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == refusal
    outbound_blob = str(outbound.requests) + str(outbound.notifications)
    assert "planHash" not in outbound_blob


async def test_superseded_approval_hash_does_not_execute_plan(tmp_path):
    class SupersededHashRunner:
        def __init__(self) -> None:
            self.requests = []

        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            self.requests.append(request)
            if request.approval.approved:
                return AgentRunResult(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    execution_mode=request.execution_mode,
                    status=AgentRunStatus.FAILED,
                    final_state="FAILED",
                    output_text="Plan approval expired or was not found. Re-run planning and approve the new plan.",
                    tool_calls=(),
                    total_cost_usd=Decimal("0"),
                    mutation_count=0,
                    provider_keys_resolvable=(),
                    stop_reason="PLAN_NOT_FOUND_OR_EXPIRED",
                )
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text="WRITE example.py\ncontent\n",
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                plan_hash="hash-final",
            )

    runner = SupersededHashRunner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
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
            "metadata": {"planHash": "superseded-hash"},
        },
    )
    response = await prompt_task

    assert response["result"]["stopReason"] == "end_turn"
    assert len(runner.requests) == 2
    assert runner.requests[-1].approval.plan_hash == "hash-final"
    assert runner.requests[-1].approval.approved is True
    write_calls = [
        item
        for item in outbound.notifications
        if item["params"]["update"].get("sessionUpdate") == "tool_call"
        and item["params"]["update"].get("kind") == "edit"
    ]
    assert write_calls == []


async def test_concurrent_sessions_route_planning_progress_to_own_session_only(tmp_path):
    class ConcurrentRaceRunner:
        def __init__(self) -> None:
            self._entered = 0
            self._lock = threading.Lock()
            self._both_entered = threading.Event()

        def run(self, request, *, planning_progress_observer=None):
            if request.approval.approved:
                return AgentRunResult(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    execution_mode=request.execution_mode,
                    status=AgentRunStatus.COMPLETED,
                    final_state="COMPLETED",
                    output_text="done",
                    tool_calls=(),
                    total_cost_usd=Decimal("0.002"),
                    mutation_count=0,
                    provider_keys_resolvable=(),
                    plan_hash=f"hash-{request.session_id}",
                )
            with self._lock:
                self._entered += 1
                if self._entered == 2:
                    self._both_entered.set()
            assert self._both_entered.wait(timeout=2), "both sessions must overlap inside runner.run"
            if planning_progress_observer is not None:
                planning_progress_observer(
                    PlanningProgressEvent(
                        run_id=request.run_id,
                        session_id=request.session_id,
                        settled_turn=1,
                        max_planning_turns=3,
                        read_request_count=1,
                        read_identities=(f"{request.session_id}#bytes=0:5",),
                        source_sha256s=("a" * 64,),
                        read_byte_counts=(5,),
                        total_cost_usd=Decimal("0.002"),
                        remaining_budget_usd=Decimal("0.048"),
                        gateway_request_ids=(request.run_id,),
                    )
                )
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=ExecutionMode.AGENT,
                status=AgentRunStatus.AWAITING_APPROVAL,
                final_state="AWAITING_APPROVAL",
                output_text=f"WRITE {request.session_id}.py\ncontent\n",
                tool_calls=(),
                total_cost_usd=Decimal("0.002"),
                mutation_count=0,
                provider_keys_resolvable=(),
                plan_hash=f"hash-{request.session_id}",
            )

    runner = ConcurrentRaceRunner()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_a = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]
    session_b = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    prompt_a = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {"sessionId": session_a, "prompt": [{"type": "text", "text": "Edit large-a.py"}]},
            }
        )
    )
    prompt_b = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "session/prompt",
                "params": {"sessionId": session_b, "prompt": [{"type": "text", "text": "Edit large-b.py"}]},
            }
        )
    )

    while len([item for item in outbound.requests if item["method"] == "session/request_permission"]) < 2:
        await asyncio.sleep(0)

    for permission_request in [item for item in outbound.requests if item["method"] == "session/request_permission"]:
        outbound.respond(permission_request["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})

    await asyncio.gather(prompt_a, prompt_b)

    progress_for_a = [
        item["params"]["sessionId"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        and "Planning turn" in item["params"]["update"]["content"]["text"]
        and item["params"]["sessionId"] == session_a
    ]
    progress_for_b = [
        item["params"]["sessionId"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
        and "Planning turn" in item["params"]["update"]["content"]["text"]
        and item["params"]["sessionId"] == session_b
    ]
    assert progress_for_a == [session_a]
    assert progress_for_b == [session_b]


async def test_planning_observation_overflow_emits_end_turn_not_internal_error(tmp_path):
    from optimus.agent.planning_loop import PlanningReadRequest, max_planning_observation_text_bytes
    from optimus.agent.runner import AgentRunner
    from tests.integration.agent.test_multi_turn_planning_flow import ScriptingGateway, _write_oversized_required_file

    _write_oversized_required_file(tmp_path)
    scripts: list[tuple[str, Decimal, str]] = []
    for index in range(6):
        start = index * 5
        end = start + 5
        read_request = (PlanningReadRequest(path="large.py", start_byte=start, end_byte=end),)
        observation = "o" * max_planning_observation_text_bytes(read_request)
        scripts.append(
            (
                f"OBSERVE: {observation}\nREAD: large.py#bytes={start}:{end}\n",
                Decimal("0.001"),
                f"gw-{index + 1}",
            )
        )
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=AgentRunner(gateway_client=ScriptingGateway(scripts), model="glm-5.2"),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Edit large.py"}],
            },
        }
    )

    assert "error" not in response
    assert response["result"]["stopReason"] == "end_turn"
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == "Planning stopped because carried observation evidence exceeds the allowed budget."
    assert outbound.requests == []


# --- Plan 9.95 Task 3 Step 3: unknown-cost ACP terminal contract ---


def test_cost_unknown_is_a_terminal_planning_stop() -> None:
    assert "PLANNING_GATEWAY_COST_UNKNOWN" in _PLANNING_TERMINAL_STOP_REASONS


async def test_unknown_cost_emits_end_turn_without_permission_request(tmp_path):
    """PLANNING_GATEWAY_COST_UNKNOWN returns end_turn with corrective text and no permission."""
    corrective_text = (
        "Planning stopped because a gateway attempt cost could not be verified; "
        "no further retry was dispatched."
    )

    class UnknownCostRunner:
        def run(self, request, *, planning_progress_observer=None):
            del planning_progress_observer
            return AgentRunResult(
                run_id=request.run_id,
                session_id=request.session_id,
                execution_mode=request.execution_mode,
                status=AgentRunStatus.TERMINATED,
                final_state="TERMINATED",
                output_text=corrective_text,
                tool_calls=(),
                total_cost_usd=Decimal("0"),
                cost_complete=False,
                unknown_cost_attempt_count=1,
                mutation_count=0,
                provider_keys_resolvable=(),
                stop_reason="PLANNING_GATEWAY_COST_UNKNOWN",
                plan_hash=None,
            )

    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=UnknownCostRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session_id = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
        )
    )["result"]["sessionId"]

    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "Do work"}],
            },
        }
    )

    assert response["result"]["stopReason"] == "end_turn"
    # No permission request issued.
    assert outbound.requests == []
    # Corrective text is the final message.
    messages = [
        item["params"]["update"]["content"]["text"]
        for item in outbound.notifications
        if item["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert messages[-1] == corrective_text


# --- P11-FU-9 Task 6: client mcpServers disposition on session/new ---


def _client_mcp_runtime_for_tests(tmp_path):
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.mcp.client_config import ClientMcpConfigNormalizer
    from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor
    from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority

    class _FakeKeyring:
        def __init__(self) -> None:
            self._store = {}

        def get_password(self, service, key):
            return self._store.get((service, key))

        def set_password(self, service, key, value):
            self._store[(service, key)] = value

        def delete_password(self, service, key):
            self._store.pop((service, key), None)

    hmac_key = b"p11-fu-9-acp-spec-test-hmac-key-32"
    keyring = _FakeKeyring()
    KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=hmac_key)
    durable = ClientMcpDurableStore(keyring_backend=keyring, hmac_key=hmac_key)
    # Disposition never opens transport; supervisor is process-lifetime in production
    # but unit tests can omit a live loop to avoid teardown hangs.
    supervisor = MCPAsyncSupervisor()
    disposition = ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=durable),
        hmac_key=hmac_key,
        controlled_path=str(tmp_path / "bin"),
        workspace_digest="a" * 64,
        permission_timeout_seconds=30.0,
    )
    return ClientMcpRuntime(disposition=disposition, supervisor=supervisor)


async def test_session_new_absent_or_empty_mcp_servers_is_exact_noop(tmp_path):
    outbound = RecordingOutboundChannel()
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=_client_mcp_runtime_for_tests(tmp_path),
    )
    for params in (
        {"cwd": str(tmp_path)},
        {"cwd": str(tmp_path), "mcpServers": []},
    ):
        response = await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": params}
        )
        assert "result" in response
        assert outbound.requests == []
        session = sessions.get(response["result"]["sessionId"])
        assert session is not None
        assert session.client_mcp_state is not None
        assert session.client_mcp_state.server_names() == ()


async def test_session_new_malformed_mcp_servers_removes_provisional_session(tmp_path):
    outbound = RecordingOutboundChannel()
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=_client_mcp_runtime_for_tests(tmp_path),
    )
    response = await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session/new",
            "params": {
                "cwd": str(tmp_path),
                "mcpServers": [
                    {"type": "http", "name": "tools", "url": "https://mcp.example.com/v1"},
                    {"type": "http", "name": "tools", "url": "https://mcp.example.com/v2"},
                ],
            },
        }
    )
    assert "error" in response
    assert response["error"]["code"] == -32600
    assert sessions._sessions == {}
    assert outbound.requests == []


async def test_session_new_awaits_transport_permission_with_opaque_safe_fields(tmp_path):
    outbound = RecordingOutboundChannel()
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=_client_mcp_runtime_for_tests(tmp_path),
    )

    async def _drive():
        task = asyncio.create_task(
            adapter.handle_client_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "session/new",
                    "params": {
                        "cwd": str(tmp_path),
                        "mcpServers": [
                            {
                                "type": "http",
                                "name": "tools",
                                "url": "https://mcp.example.com/v1",
                                "headers": [{"name": "Authorization", "value": "SECRET-TOKEN"}],
                            }
                        ],
                    },
                }
            )
        )
        request = await outbound.wait_for_request("session/request_permission")
        params = request["params"]
        blob = str(params)
        assert "SECRET-TOKEN" not in blob
        assert "Authorization" not in blob or "fingerprint" in blob.lower() or "credential" in blob.lower()
        assert params["sessionId"]
        assert params["candidateId"]
        assert {opt["kind"] for opt in params["options"]} == {"allow_once", "reject_once"}
        assert "optimus-trust mcp review" in blob
        outbound.respond(
            request["id"],
            {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )
        return await task

    response = await _drive()
    assert "result" in response
    session = sessions.get(response["result"]["sessionId"])
    assert session is not None
    assert session.client_mcp_state.is_leased("tools")


async def test_session_new_timeout_and_reject_keep_usable_session_unavailable(tmp_path):
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.mcp.client_config import ClientMcpConfigNormalizer
    from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor
    from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority

    class _FakeKeyring:
        def __init__(self) -> None:
            self._store = {}

        def get_password(self, service, key):
            return self._store.get((service, key))

        def set_password(self, service, key, value):
            self._store[(service, key)] = value

        def delete_password(self, service, key):
            self._store.pop((service, key), None)

    hmac_key = b"p11-fu-9-acp-timeout-hmac-key-32b"
    keyring = _FakeKeyring()
    KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=hmac_key)
    durable = ClientMcpDurableStore(keyring_backend=keyring, hmac_key=hmac_key)
    supervisor = MCPAsyncSupervisor()
    runtime = ClientMcpRuntime(
        disposition=ClientMcpDisposition(
            normalizer=ClientMcpConfigNormalizer(),
            lease_authority=ClientMcpLeaseAuthority(store=durable),
            hmac_key=hmac_key,
            controlled_path=str(tmp_path / "bin"),
            workspace_digest="b" * 64,
            permission_timeout_seconds=0.05,
        ),
        supervisor=supervisor,
    )
    outbound = RecordingOutboundChannel()
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=runtime,
    )

    async def _drive_timeout():
        task = asyncio.create_task(
            adapter.handle_client_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "session/new",
                    "params": {
                        "cwd": str(tmp_path),
                        "mcpServers": [
                            {"type": "http", "name": "tools", "url": "https://mcp.example.com/v1"}
                        ],
                    },
                }
            )
        )
        await outbound.wait_for_request("session/request_permission")
        # Never respond — disposition timeout path.
        return await task

    response = await _drive_timeout()
    assert "result" in response
    session = sessions.get(response["result"]["sessionId"])
    assert session is not None
    assert session.client_mcp_state.is_unavailable("tools")

    outbound2 = RecordingOutboundChannel()
    sessions2 = InMemoryAcpSpecSessionStore()
    runtime2 = _client_mcp_runtime_for_tests(tmp_path)
    adapter2 = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions2,
        outbound=outbound2,
        client_mcp_runtime=runtime2,
    )

    async def _drive_reject():
        task = asyncio.create_task(
            adapter2.handle_client_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/new",
                    "params": {
                        "cwd": str(tmp_path),
                        "mcpServers": [
                            {"type": "http", "name": "tools", "url": "https://mcp.example.com/v1"}
                        ],
                    },
                }
            )
        )
        request = await outbound2.wait_for_request("session/request_permission")
        outbound2.respond(
            request["id"],
            {"outcome": {"outcome": "selected", "optionId": "reject_once"}},
        )
        return await task

    reject_response = await _drive_reject()
    assert "result" in reject_response
    session2 = sessions2.get(reject_response["result"]["sessionId"])
    assert session2.client_mcp_state.is_unavailable("tools")


async def test_session_load_still_method_not_found(tmp_path):
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=RecordingOutboundChannel(),
    )
    response = await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": 9, "method": "session/load", "params": {"sessionId": "x"}}
    )
    assert response["error"]["code"] == METHOD_NOT_FOUND


async def test_close_all_closes_session_states_exactly_once(tmp_path):
    sessions = InMemoryAcpSpecSessionStore()
    outbound = RecordingOutboundChannel()
    runtime = _client_mcp_runtime_for_tests(tmp_path)
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=runtime,
    )
    response = await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    )
    session = sessions.get(response["result"]["sessionId"])
    closes = {"n": 0}
    session.client_mcp_state.register_close_hook(lambda: closes.__setitem__("n", closes["n"] + 1))
    adapter.close_all()
    adapter.close_all()
    assert closes["n"] == 1


async def test_session_prompt_threads_client_mcp_service_without_serializing(tmp_path):
    class CapturingRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__()
            self.kwargs = []

        def run(self, request, *, planning_progress_observer=None, client_mcp_service=None, mcp_permission_broker=None):
            self.kwargs.append(
                {
                    "client_mcp_service": client_mcp_service,
                    "mcp_permission_broker": mcp_permission_broker,
                    "dump": request.model_dump(),
                }
            )
            return super().run(request, planning_progress_observer=planning_progress_observer)

    runner = CapturingRunner()
    outbound = RecordingOutboundChannel()
    sessions = InMemoryAcpSpecSessionStore()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
        client_mcp_runtime=_client_mcp_runtime_for_tests(tmp_path),
    )

    async def _drive():
        task = asyncio.create_task(
            adapter.handle_client_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "session/new",
                    "params": {
                        "cwd": str(tmp_path),
                        "mcpServers": [
                            {"type": "http", "name": "tools", "url": "https://mcp.example.com/v1"}
                        ],
                    },
                }
            )
        )
        request = await outbound.wait_for_request("session/request_permission")
        outbound.respond(
            request["id"],
            {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )
        return await task

    new_response = await _drive()
    session_id = new_response["result"]["sessionId"]
    before = len(outbound.requests)

    prompt_task = asyncio.create_task(
        adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
            }
        )
    )
    while len(outbound.requests) <= before:
        await asyncio.sleep(0.01)
    permission = outbound.requests[-1]
    assert permission["method"] == "session/request_permission"
    # Plan approval permission (second request after transport).
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    await prompt_task

    assert runner.kwargs
    first = runner.kwargs[0]
    assert first["client_mcp_service"] is not None
    assert "client_mcp_service" not in first["dump"]
    assert "mcp_permission_broker" not in first["dump"]


@pytest.mark.asyncio
async def test_spec_mcp_broker_issue_fails_closed_until_catalog_authorizer_attached(tmp_path) -> None:
    """Real AcpDuplexAdapter._issue must not fabricate tokens that fail downstream.

    Until a per-server ClientMcpCallAuthorizer is registered on the session tool service
    (tracked as P11-FU-20), allow-path issuance returns None (fail closed) rather than a
    token that later surfaces as mcp.client.one_call_unknown.
    """
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=FakeRunner(),
        workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(),
        outbound=outbound,
    )
    session = adapter._sessions.create(cwd=tmp_path)
    session.client_mcp_state = ClientMcpSessionState(session_id=session.session_id)
    assert isinstance(session.client_mcp_state.tool_service, ClientMcpSessionService)
    broker = adapter._mcp_permission_broker_for(session)
    assert broker is not None

    request = PreToolRequest(
        run_id="run-1",
        session_id=session.session_id,
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.MCP,
        action="tools.write_thing",
        generation_scope=GenerationScope.INLINE_SNIPPET,
        approval_granted=False,
        mcp_authority="client_session",
        mcp_server_id="tools",
        mcp_tool_name="write_thing",
        mcp_arguments={"x": 1},
    )
    assert broker._issue_approval(request) is None

    service = await _lease_and_materialize_write_thing(session, tmp_path)
    broker = adapter._mcp_permission_broker_for(session)
    assert broker is not None
    lease = session.client_mcp_state.lease_for("tools")
    assert lease is not None

    mismatched = PreToolRequest(
        run_id="run-1",
        session_id=session.session_id,
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.MCP,
        action="other.write_thing",
        generation_scope=GenerationScope.INLINE_SNIPPET,
        approval_granted=False,
        mcp_authority="client_session",
        mcp_server_id="other",
        mcp_tool_name="write_thing",
        mcp_arguments={"x": 1},
    )
    assert broker._issue_approval(mismatched) is None

    issued = broker._issue_approval(request)
    assert issued is not None
    assert issued.session_id == session.session_id
    assert issued.identity_fingerprint == lease.identity_fingerprint
    assert issued.tool_name == "write_thing"
    assert issued.arguments_digest == arguments_digest({"x": 1})
    assert issued.token

    write_task = asyncio.create_task(asyncio.to_thread(broker.request_write, request))
    permission = await outbound.wait_for_request("session/request_permission")
    outbound.respond(
        permission["id"],
        {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
    )
    allowed = await write_task
    assert allowed is not None
    assert allowed.token
    assert allowed.tool_name == "write_thing"
    assert allowed.arguments_digest == arguments_digest({"x": 1})

    output, call = service.call_tool(
        "write_thing",
        {"x": 1},
        one_call_approval=allowed.token,
    )
    assert call.authorization_outcome == "ALLOW"
    assert output.text == "ok:write_thing"
    assert "x" not in output.text
    guard = object.__getattribute__(service, "_guard")
    audit = guard.audit_events()[-1]
    assert audit.verdict == "ALLOW"
    assert audit.rule_id == "mcp.client.write_one_call_allowed"
    dumped = json.dumps(audit.__dict__, default=str)
    assert '{"x": 1}' not in dumped
    assert "x" not in audit.sanitized_subject

    _replay_out, replay = service.call_tool(
        "write_thing",
        {"x": 1},
        one_call_approval=allowed.token,
    )
    assert replay.authorization_outcome != "ALLOW"
