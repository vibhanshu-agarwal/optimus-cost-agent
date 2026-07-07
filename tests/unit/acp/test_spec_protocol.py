import asyncio
from decimal import Decimal

from optimus.acp.errors import METHOD_NOT_FOUND
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
        },
    )
    response = await prompt_task

    assert response["result"]["stopReason"] == "end_turn"
    assert runner.requests[-1].approval.approved is True
    assert runner.requests[-1].approval.approval_id == "approval-1"
    assert runner.requests[-1].approval.plan_hash == "hash-1"
    assert any(notification["params"]["update"]["sessionUpdate"] == "tool_call_update" for notification in outbound.notifications)


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
