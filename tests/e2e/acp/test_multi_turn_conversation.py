"""Plan 11.25 Task 10 — hermetic multi-turn conversation contract scenarios.

Drives the real ``AcpStreamServer.serve_ndjson`` path with a deterministic
in-process runner (no live Gateway). Physical NDJSON writes go through the
dedicated writer when the transport exposes ``write_bytes``/``flush``.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.conversation import (
    CONVERSATION_MAX_BYTES,
    ConversationDisposition,
    ConversationOutcome,
    ConversationSanitizer,
    ConversationSanitizerInputs,
    ConversationState,
)
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.errors import INVALID_REQUEST, REQUEST_CANCELLED
from optimus.acp.server import AcpStreamServer
from optimus.acp.settlement import EffectState
from optimus.acp.shapes import build_usage_update
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.guardrails.pre_tool import PreToolGuard
from tests.integration.acp.test_server_stream import InteractiveLineReader


class PhysicalCapturingWriter:
    """NDJSON transport with dedicated-writer seams plus message wait helpers."""

    def __init__(self) -> None:
        self.raw_chunks: list[bytes] = []
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._response_events: dict[str | int, asyncio.Event] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def write_bytes(self, data: bytes) -> None:
        with self._lock:
            self.raw_chunks.append(data)
            for line in data.splitlines():
                if not line.strip():
                    continue
                message = json.loads(line.decode("utf-8"))
                self.messages.append(message)
                request_id = message.get("id")
                if request_id is not None and ("result" in message or "error" in message):
                    event = self._response_events.setdefault(request_id, asyncio.Event())
                    loop = self._loop
                    if loop is not None:
                        loop.call_soon_threadsafe(event.set)
                    else:
                        event.set()

    def flush(self) -> None:
        return None

    async def write_line(self, message: Mapping[str, Any]) -> None:
        # Fallback path when dedicated writer is absent.
        payload = (json.dumps(dict(message), separators=(",", ":")) + "\n").encode("utf-8")
        self.write_bytes(payload)

    async def wait_for_response(self, request_id: str | int, *, timeout: float = 5.0) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            for message in list(self.messages):
                if message.get("id") == request_id and ("result" in message or "error" in message):
                    return message
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"no response for id={request_id!r}")
            event = self._response_events.setdefault(request_id, asyncio.Event())
            event.clear()
            try:
                await asyncio.wait_for(event.wait(), timeout=remaining)
            except TimeoutError:
                continue


class DependentFollowUpRunner:
    """Turn 1 commits a fact; turn 2 answers only if that fact appears in task."""

    SECRET_FACT = "ALPHA-42-DEPENDENT"

    def __init__(self) -> None:
        self.tasks: list[str] = []
        self.run_ids: list[str] = []

    def run(self, request, **kwargs):
        del kwargs
        self.tasks.append(request.task)
        self.run_ids.append(request.run_id)
        if self.SECRET_FACT in request.task and "what was the code" in request.task.lower():
            text = f"The code is {self.SECRET_FACT}."
        elif "remember code" in request.task.lower():
            text = f"Stored code {self.SECRET_FACT}."
        else:
            text = "I do not know the code."
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text=text,
            plan_hash=None,
            total_cost_usd=Decimal("0.001"),
            cost_complete=True,
        )


class CompletingRunner:
    def __init__(self, *, text: str = "ok") -> None:
        self.tasks: list[str] = []
        self.run_ids: list[str] = []
        self.text = text

    def run(self, request, **kwargs):
        del kwargs
        self.tasks.append(request.task)
        self.run_ids.append(request.run_id)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text=self.text,
            plan_hash=None,
            total_cost_usd=Decimal("0.001"),
            cost_complete=True,
        )


class BlockingRunner:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def run(self, request, **kwargs):
        del kwargs
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self.started.set)
        else:
            self.started.set()
        self.release.wait(timeout=5)
        return AgentRunResult(
            run_id=request.run_id,
            session_id=request.session_id,
            execution_mode=request.execution_mode,
            status=AgentRunStatus.COMPLETED,
            final_state="COMPLETED",
            output_text="done",
            plan_hash=None,
        )


def _server_for_runner(tmp_path: Path, runner: Any) -> AcpStreamServer:
    workspace = tmp_path.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    dispatcher = JsonRpcDispatcher(
        gateway_client=object(),
        agent_runner=runner,
        pre_tool_guard=guard,
        workspace_root=workspace,
    )
    sanitizer = ConversationSanitizerInputs(
        known_secrets=("top-secret-canary", "hunter%402", "hunter@2"),
        path_aliases=(),
        known_pii=(),
    )
    return AcpStreamServer(
        dispatcher=dispatcher,
        conversation_sanitizer_inputs=sanitizer,
    )


def _prompt(session_id: str, text: str, *, request_id: int) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/prompt",
        "params": {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        },
    }


@pytest.mark.asyncio
async def test_dependent_follow_up_uses_turn1_history(tmp_path: Path) -> None:
    runner = DependentFollowUpRunner()
    server = _server_for_runner(tmp_path, runner)
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    loop = asyncio.get_running_loop()
    writer.bind_loop(loop)

    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
        )
        new_resp = await writer.wait_for_response(1)
        session_id = new_resp["result"]["sessionId"]

        await reader.send(_prompt(session_id, f"Remember code {runner.SECRET_FACT}", request_id=2))
        first = await writer.wait_for_response(2)
        assert "error" not in first
        assert first["result"]["stopReason"] == "end_turn"

        await reader.send(_prompt(session_id, "What was the code?", request_id=3))
        second = await writer.wait_for_response(3)
        assert "error" not in second
        assert second["result"]["stopReason"] == "end_turn"

        assert len(runner.tasks) == 2
        assert runner.SECRET_FACT in runner.tasks[0]
        # Turn 2 prompt alone lacks the fact; the envelope must supply it.
        assert "What was the code?" in runner.tasks[1]
        assert runner.SECRET_FACT in runner.tasks[1]
        assert runner.run_ids == [f"{session_id}:1", f"{session_id}:2"]
        # No refusal / warning agent_message_chunk about capacity.
        updates = [
            m
            for m in writer.messages
            if m.get("method") == "session/update"
            and isinstance(m.get("params"), dict)
            and isinstance(m["params"].get("update"), dict)
            and m["params"]["update"].get("sessionUpdate") == "agent_message_chunk"
        ]
        refusal_like = [u for u in updates if "refused" in json.dumps(u).lower() or "capacity" in json.dumps(u).lower()]
        assert refusal_like == []
    finally:
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)


@pytest.mark.asyncio
async def test_request_id_reuse_keeps_distinct_turn_seq(tmp_path: Path) -> None:
    runner = CompletingRunner()
    server = _server_for_runner(tmp_path, runner)
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    writer.bind_loop(asyncio.get_running_loop())
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
        )
        session_id = (await writer.wait_for_response(1))["result"]["sessionId"]
        for _ in range(2):
            await reader.send(_prompt(session_id, "hello", request_id=99))
            resp = await writer.wait_for_response(99)
            assert "result" in resp
            # Clear matching response so the second wait does not see the first.
            writer.messages = [m for m in writer.messages if not (m.get("id") == 99 and "result" in m)]
            writer._response_events.pop(99, None)
        assert runner.run_ids == [f"{session_id}:1", f"{session_id}:2"]
    finally:
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)


@pytest.mark.asyncio
async def test_unknown_session_is_jsonrpc_error_not_refusal(tmp_path: Path) -> None:
    server = _server_for_runner(tmp_path, CompletingRunner())
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    writer.bind_loop(asyncio.get_running_loop())
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send(_prompt("session-never-created", "hi", request_id=7))
        resp = await writer.wait_for_response(7)
        assert resp["error"]["code"] == INVALID_REQUEST
        assert resp["error"]["message"] == "unknown session"
    finally:
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)


@pytest.mark.asyncio
async def test_cap_closed_refusal_is_explanatory_success(tmp_path: Path) -> None:
    from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel

    runner = CompletingRunner()
    sessions = InMemoryAcpSpecSessionStore()
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(
        runner=runner,
        workspace_root=tmp_path,
        sessions=sessions,
        outbound=outbound,
    )
    new_response = (
        await adapter.handle_client_request(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
        )
    ).response
    session_id = new_response["result"]["sessionId"]
    session = sessions.get(session_id)
    assert session is not None and session.conversation is not None
    session.conversation._disposition = ConversationDisposition.CAP_CLOSED  # noqa: SLF001
    before = dict(session.conversation.records)
    refused = (
        await adapter.handle_client_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "more"}],
                },
            }
        )
    ).response
    assert "error" not in refused
    assert refused["result"]["stopReason"] == "refusal"
    assert session.conversation.records == before
    assert runner.run_ids == []
    assert any(
        n["params"]["update"]["sessionUpdate"] == "agent_message_chunk" for n in outbound.notifications
    )


@pytest.mark.asyncio
async def test_concurrent_same_session_prompt_rejected(tmp_path: Path) -> None:
    runner = BlockingRunner()
    server = _server_for_runner(tmp_path, runner)
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    loop = asyncio.get_running_loop()
    writer.bind_loop(loop)
    runner.bind_loop(loop)
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
        )
        session_id = (await writer.wait_for_response(1))["result"]["sessionId"]
        await reader.send(_prompt(session_id, "first", request_id=2))
        await asyncio.wait_for(runner.started.wait(), timeout=5)
        await reader.send(_prompt(session_id, "second", request_id=3))
        second = await writer.wait_for_response(3)
        assert second["error"]["code"] == REQUEST_CANCELLED
        assert second["error"]["message"] == "a turn is already in progress"
        runner.release.set()
        first = await writer.wait_for_response(2)
        assert "result" in first
    finally:
        runner.release.set()
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)


@pytest.mark.asyncio
async def test_sanitized_secret_absent_from_planner_task(tmp_path: Path) -> None:
    runner = CompletingRunner()
    server = _server_for_runner(tmp_path, runner)
    reader = InteractiveLineReader()
    writer = PhysicalCapturingWriter()
    writer.bind_loop(asyncio.get_running_loop())
    serve_task = asyncio.create_task(server.serve_ndjson(reader, writer))
    try:
        await reader.send(
            {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path)}}
        )
        session_id = (await writer.wait_for_response(1))["result"]["sessionId"]
        await reader.send(
            _prompt(session_id, "token top-secret-canary please remember", request_id=2)
        )
        await writer.wait_for_response(2)
        assert runner.tasks
        assert "top-secret-canary" not in runner.tasks[0]
    finally:
        reader.close()
        await asyncio.wait_for(serve_task, timeout=5)


def test_gauge_approximate_and_usage_update_shape() -> None:
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs((), (), ())))
    decision = state.prepare_commit(
        1,
        sanitized_user_prompt="u",
        sanitized_plan_text="",
        sanitized_completion_text="ok",
        outcome=ConversationOutcome.COMPLETED,
        effect_state=EffectState.NONE,
    )
    state.commit_after_final_flush(decision)
    gauge = state.usage_gauge()
    update = build_usage_update(session_id="s", used=gauge.used, size=gauge.size, cost=gauge.cost)
    assert update["update"]["sessionUpdate"] == "usage_update"
    assert isinstance(update["update"]["used"], int)
    assert isinstance(update["update"]["size"], int)
    assert update["update"]["size"] == CONVERSATION_MAX_BYTES // 4


def test_delivery_indeterminate_dominates_for_evidence_map(tmp_path: Path) -> None:
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs((), (), ())))
    state.latch_delivery_indeterminate()
    admission = state.prepare_admission("later")
    assert admission.admitted is False
    assert admission.refuse_reason == ConversationDisposition.DELIVERY_INDETERMINATE.value


def test_admission_cap_exact_boundary_still_refuses(tmp_path: Path) -> None:
    del tmp_path
    state = ConversationState(ConversationSanitizer(ConversationSanitizerInputs((), (), ())))
    chunk = "x" * 40_000
    for _ in range(30):
        admission = state.prepare_admission(chunk)
        if not admission.admitted:
            assert admission.refuse_reason == "cap"
            return
        assert admission.turn_seq is not None
        seq = state.allocate_turn_seq()
        decision = state.prepare_commit(
            seq,
            sanitized_user_prompt=chunk,
            sanitized_plan_text="",
            sanitized_completion_text="ok",
            outcome=ConversationOutcome.COMPLETED,
            effect_state=EffectState.NONE,
        )
        state.commit_after_final_flush(decision)
    raise AssertionError("could not reach conversation cap")
