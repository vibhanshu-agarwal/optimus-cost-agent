import asyncio
import threading
from decimal import Decimal

import pytest

from optimus.acp.errors import METHOD_NOT_FOUND
from optimus.acp.shapes import build_plan_session_update
from optimus.acp.spec import (
    ACP_PROTOCOL_VERSION,
    AcpDuplexAdapter,
    InMemoryAcpSpecSessionStore,
    RecordingOutboundChannel,
    _max_planning_turns_from_env,
)
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall
from optimus.agent.planning_loop import PlanningProgressEvent
from optimus.runtime.modes import ExecutionMode


class FakeRunner:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request, *, planning_progress_observer=None):
        del planning_progress_observer
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


def test_max_planning_turns_from_env_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("OPTIMUS_MAX_PLANNING_TURNS", raising=False)
    assert _max_planning_turns_from_env() is None


def test_max_planning_turns_from_env_returns_none_when_blank(monkeypatch):
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "   ")
    assert _max_planning_turns_from_env() is None


def test_max_planning_turns_from_env_parses_valid_value(monkeypatch):
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "1")
    assert _max_planning_turns_from_env() == 1


@pytest.mark.parametrize("raw", ["0", "-1", "abc"])
def test_max_planning_turns_from_env_rejects_invalid_values(monkeypatch, raw):
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", raw)
    with pytest.raises(ValueError, match="OPTIMUS_MAX_PLANNING_TURNS"):
        _max_planning_turns_from_env()


class _RecordingCompletedRunner:
    """Returns COMPLETED immediately: no approval round-trip to drive."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request, *, planning_progress_observer=None):
        del planning_progress_observer
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


async def test_session_prompt_applies_max_planning_turns_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("OPTIMUS_MAX_PLANNING_TURNS", "1")
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

    await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )

    assert runner.requests[0].max_planning_turns == 1


async def test_session_prompt_uses_default_max_planning_turns_when_env_unset(tmp_path, monkeypatch):
    monkeypatch.delenv("OPTIMUS_MAX_PLANNING_TURNS", raising=False)
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

    await adapter.handle_client_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Add a docstring"}]},
        }
    )

    assert runner.requests[0].max_planning_turns == 3


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
