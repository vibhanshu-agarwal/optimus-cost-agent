from __future__ import annotations

import asyncio
import itertools
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from optimus.acp.errors import INVALID_REQUEST, METHOD_NOT_FOUND, JsonRpcError, error_response, success_response
from optimus.agent.models import AgentApproval, AgentRunRequest, AgentRunResult, AgentRunStatus
from optimus.runtime.modes import ExecutionMode

ACP_PROTOCOL_VERSION = 1


class AcpOutboundChannel(Protocol):
    async def notify(self, method: str, params: dict[str, Any]) -> None:
        ...

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        ...

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        ...


@dataclass
class AcpSpecSession:
    session_id: str
    cwd: Path
    execution_mode: ExecutionMode = ExecutionMode.AGENT


@dataclass
class AcpPromptTurn:
    session_id: str
    request_id: str | int | None
    run_id: str
    cancelled: bool = False
    pending_permission_request_id: str | int | None = None


class InMemoryAcpSpecSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AcpSpecSession] = {}

    def create(self, *, cwd: Path) -> AcpSpecSession:
        session = AcpSpecSession(session_id=f"session-{uuid.uuid4().hex}", cwd=cwd.resolve())
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AcpSpecSession | None:
        return self._sessions.get(session_id)


class RecordingOutboundChannel:
    def __init__(self) -> None:
        self.notifications: list[dict[str, Any]] = []
        self.requests: list[dict[str, Any]] = []
        self._request_ids = itertools.count(1)
        self._request_event = asyncio.Event()
        self._futures: dict[str | int, asyncio.Future[dict[str, Any]]] = {}

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        self.notifications.append({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = f"agent-{next(self._request_ids)}"
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._futures[request_id] = future
        self.requests.append({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        self._request_event.set()
        return await future

    async def wait_for_request(self, method: str) -> dict[str, Any]:
        while True:
            for request in self.requests:
                if request["method"] == method:
                    return request
            self._request_event.clear()
            await self._request_event.wait()

    def respond(self, request_id: str | int, result: dict[str, Any]) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(result)

    def cancel_request(self, request_id: str | int, result: dict[str, Any]) -> None:
        self.respond(request_id, result)


class AcpDuplexAdapter:
    def __init__(
        self,
        *,
        runner: Any,
        workspace_root: str | Path,
        sessions: InMemoryAcpSpecSessionStore,
        outbound: AcpOutboundChannel,
    ) -> None:
        self._runner = runner
        self._workspace_root = Path(workspace_root).resolve()
        self._sessions = sessions
        self._outbound = outbound
        self._active_turns: dict[str, AcpPromptTurn] = {}

    async def handle_client_request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0" or "method" not in request:
            return error_response(request_id, JsonRpcError(code=INVALID_REQUEST, message="invalid request"))

        method = request["method"]
        if method == "initialize":
            return self._handle_initialize(request)
        if method == "session/new":
            return self._handle_session_new(request)
        if method == "session/prompt":
            return await self._handle_session_prompt(request)
        if method in {"session/update", "session/request_permission"}:
            return error_response(request_id, JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"))
        return error_response(request_id, JsonRpcError(code=METHOD_NOT_FOUND, message=f"method not found: {method}"))

    async def handle_client_notification(self, notification: dict[str, Any]) -> None:
        if notification.get("method") != "session/cancel":
            return
        params = notification.get("params")
        if not isinstance(params, dict):
            return
        session_id = params.get("sessionId")
        if not isinstance(session_id, str):
            return
        turn = self._active_turns.get(session_id)
        if turn is None:
            return
        turn.cancelled = True
        if turn.pending_permission_request_id is not None:
            self._outbound.cancel_request(turn.pending_permission_request_id, {"outcome": {"outcome": "cancelled"}})

    def _handle_initialize(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), int):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        return success_response(
            request_id=request.get("id"),
            result={
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "agentCapabilities": {
                    "promptCapabilities": {
                        "image": False,
                        "audio": False,
                        "embeddedContext": False,
                    },
                    "sessionCapabilities": {},
                },
                "agentInfo": {"name": "optimus", "version": "0.1.0"},
                "authMethods": [],
            },
        )

    def _handle_session_new(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict) or not isinstance(params.get("cwd"), str):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        cwd = Path(params["cwd"]).resolve()
        if not cwd.is_relative_to(self._workspace_root):
            return error_response(
                request.get("id"),
                JsonRpcError(code=INVALID_REQUEST, message="session cwd outside configured workspace"),
            )
        session = self._sessions.create(cwd=cwd)
        return success_response(request_id=request.get("id"), result={"sessionId": session.session_id})

    async def _handle_session_prompt(self, request: dict[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        if not isinstance(params, dict):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        session_id = params.get("sessionId")
        prompt = params.get("prompt")
        if not isinstance(session_id, str) or not isinstance(prompt, list):
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="invalid request"))
        session = self._sessions.get(session_id)
        if session is None:
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="unknown session"))
        task = _text_from_content_blocks(prompt)
        if not task:
            return error_response(request.get("id"), JsonRpcError(code=INVALID_REQUEST, message="empty prompt"))

        run_id = f"{session_id}:{request.get('id')}"
        turn = AcpPromptTurn(session_id=session_id, request_id=request.get("id"), run_id=run_id)
        self._active_turns[session_id] = turn
        try:
            planning_request = AgentRunRequest(
                run_id=run_id,
                session_id=session_id,
                task=task,
                execution_mode=session.execution_mode,
                workspace_root=session.cwd,
            )
            planning_result = await asyncio.to_thread(self._runner.run, planning_request)
            await self._emit_result_updates(session_id=session_id, result=planning_result, planning=True)
            if turn.cancelled:
                return success_response(request_id=request.get("id"), result={"stopReason": "cancelled"})
            if planning_result.status is not AgentRunStatus.AWAITING_APPROVAL:
                return success_response(request_id=request.get("id"), result={"stopReason": _stop_reason(planning_result)})

            permission_result = await self._request_permission(turn=turn, result=planning_result)
            if turn.cancelled or permission_result.get("outcome", {}).get("outcome") != "selected":
                return success_response(request_id=request.get("id"), result={"stopReason": "cancelled"})

            metadata = permission_result.get("metadata")
            if not isinstance(metadata, dict):
                return success_response(request_id=request.get("id"), result={"stopReason": "refusal"})
            approved_request = planning_request.model_copy(
                update={
                    "approval": AgentApproval(
                        approved=True,
                        approval_id=str(metadata.get("approvalId") or ""),
                        plan_hash=str(metadata.get("planHash") or ""),
                    )
                }
            )
            approved_result = await asyncio.to_thread(self._runner.run, approved_request)
            await self._emit_result_updates(session_id=session_id, result=approved_result, planning=False)
            return success_response(request_id=request.get("id"), result={"stopReason": _stop_reason(approved_result)})
        finally:
            self._active_turns.pop(session_id, None)

    async def _request_permission(self, *, turn: AcpPromptTurn, result: AgentRunResult) -> dict[str, Any]:
        params = {
            "sessionId": turn.session_id,
            "options": [
                {
                    "optionId": "approve",
                    "name": "Approve",
                    "kind": "allow_once",
                    "metadata": {"planHash": result.plan_hash},
                },
                {
                    "optionId": "cancel",
                    "name": "Cancel",
                    "kind": "reject_once",
                    "metadata": {"planHash": result.plan_hash},
                },
            ],
            "metadata": {
                "runId": result.run_id,
                "planHash": result.plan_hash,
                "planText": result.output_text,
            },
        }
        request_task = asyncio.create_task(self._outbound.request("session/request_permission", params))
        await asyncio.sleep(0)
        if self._active_turns.get(turn.session_id) is turn:
            if hasattr(self._outbound, "requests") and self._outbound.requests:
                turn.pending_permission_request_id = self._outbound.requests[-1]["id"]
            elif getattr(self._outbound, "last_outbound_request_id", None) is not None:
                turn.pending_permission_request_id = self._outbound.last_outbound_request_id
        return await request_task

    async def _emit_result_updates(self, *, session_id: str, result: AgentRunResult, planning: bool) -> None:
        if planning:
            await self._outbound.notify(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "plan",
                        "content": [{"type": "text", "text": result.output_text}],
                    },
                },
            )
            return
        for tool_call in result.tool_calls:
            await self._outbound.notify(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCall": {
                            "title": tool_call.tool_name,
                            "content": [{"type": "text", "text": tool_call.summary}],
                        },
                    },
                },
            )


def _text_from_content_blocks(blocks: list[Any]) -> str:
    texts: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
            texts.append(block["text"])
    return "\n".join(texts).strip()


def _stop_reason(result: AgentRunResult) -> str:
    if result.status is AgentRunStatus.COMPLETED:
        return "end_turn"
    if result.status is AgentRunStatus.TERMINATED and result.stop_reason == "cancelled":
        return "cancelled"
    return "refusal"
