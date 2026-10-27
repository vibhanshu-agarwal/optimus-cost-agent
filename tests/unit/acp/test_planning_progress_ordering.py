"""Ordering is FIFO admission; physical completion remains separately owned."""
from __future__ import annotations

import asyncio
import threading
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp import spec
from optimus.acp.lifecycle import TurnControl
from optimus.acp.spec import AcpDuplexAdapter, AcpPromptTurn, AcpSpecSession, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.agent.planning_loop import PlanningProgressEvent
from tests.support.contract_doubles import checked_agent_runner


def progress_lane(send):
    lane_type = getattr(spec, "ProgressLane", None)
    assert lane_type is not None, "planning progress needs a bounded admission/completion owner"
    return lane_type(send)


async def loop_turn() -> None:
    tick = asyncio.Event()
    asyncio.get_running_loop().call_soon(tick.set)
    await tick.wait()


@pytest.mark.asyncio
async def test_progress_fifo_admission_precedes_every_dependent_branch():
    entered = asyncio.Event()
    admit = asyncio.Event()
    physical = asyncio.Event()
    frames = []

    async def send(event, admitted):
        entered.set()
        await admit.wait()
        frames.append(event)
        admitted.set()
        await physical.wait()

    lane = progress_lane(send)
    lane.offer("progress")
    await entered.wait()
    barrier = asyncio.create_task(lane.settle())
    try:
        await loop_turn()
        assert not barrier.done()
        assert frames == []
        admit.set()
        await asyncio.wait_for(barrier, 2)
        frames.extend(["plan", "permission", "response"])
        assert frames == ["progress", "plan", "permission", "response"]
        assert not physical.is_set(), "admission must not require physical flush"
    finally:
        admit.set()
        physical.set()
        await lane.drain()


@pytest.mark.asyncio
async def test_progress_lane_coalesces_only_unsubmitted_events():
    entered = asyncio.Event()
    physical = asyncio.Event()
    frames = []

    async def send(event, admitted):
        frames.append(event)
        admitted.set()
        entered.set()
        await physical.wait()

    lane = progress_lane(send)
    lane.offer(1)
    await entered.wait()
    for event in range(2, 1001):
        lane.offer(event)
    try:
        await asyncio.wait_for(lane.settle(), 2)
        assert frames == [1, 1000], "already admitted progress cannot be rewritten or overtaken"
        lane.offer(1001)
        await loop_turn()
        assert frames == [1, 1000], "late callbacks cannot create new send tasks"
    finally:
        physical.set()
        await lane.drain()


@pytest.mark.asyncio
async def test_cancelled_progress_keeps_owner_completion():
    admitted = asyncio.Event()
    physical = asyncio.Event()
    completed = []

    async def send(event, admission):
        admission.set()
        admitted.set()
        await physical.wait()
        completed.append(event)

    lane = progress_lane(send)
    lane.offer(1)
    await admitted.wait()
    lane.cancel()
    drain = asyncio.create_task(lane.drain())
    try:
        await loop_turn()
        assert not drain.done()
        lane.offer(2)
        physical.set()
        await asyncio.wait_for(drain, 2)
        assert completed == [1]
    finally:
        physical.set()
        await drain


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("writer closed"), OSError("physical failure")])
async def test_eof_and_writer_failure_unblock_planner_without_late_send(failure):
    calls = []

    async def send(event, admitted):
        calls.append(event)
        raise failure

    lane = progress_lane(send)
    lane.offer(1)
    await asyncio.wait_for(lane.settle(), 2)
    lane.cancel()
    lane.offer(2)
    await lane.drain()
    assert calls == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_owned", [False, True])
async def test_started_worker_stays_owned_until_physical_return(tmp_path: Path, cancel_owned):
    sessions = InMemoryAcpSpecSessionStore()
    session = AcpSpecSession(session_id="session", cwd=tmp_path)
    sessions._sessions[session.session_id] = session
    turn = AcpPromptTurn(session_id="session", turn_seq=1, turn_control=TurnControl(session_id="session", turn_seq=1))
    adapter = AcpDuplexAdapter(runner=object(), workspace_root=tmp_path, sessions=sessions, outbound=RecordingOutboundChannel())
    entered = threading.Event()
    release = threading.Event()
    returned = threading.Event()

    def worker():
        entered.set()
        try:
            assert release.wait(5), "fixture must release its own worker"
        finally:
            returned.set()

    call = asyncio.create_task(adapter._in_worker(session, turn, worker))
    close = None
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        if cancel_owned:
            [owned] = adapter._worker_tasks
            owned.cancel()
            await loop_turn()
            assert not owned.done(), "cancellation of a supervisor task is not physical completion"
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        close = asyncio.create_task(adapter.aclose())
        await loop_turn()
        assert not close.done(), "cancelling the await does not release the physical worker"
        assert not returned.is_set()
        release.set()
        await asyncio.wait_for(close, 2)
        assert returned.is_set()
    finally:
        release.set()
        if close is not None:
            await close
        if not call.done():
            await call


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", ["chat", "completion", "permission", "failure"])
async def test_real_prompt_branch_waits_for_progress_admission(tmp_path, branch):
    entered, release = asyncio.Event(), asyncio.Event()
    frames = []

    class Outbound(RecordingOutboundChannel):
        async def notify(self, method, params, *, require_flushed=False):
            progress = spec.progress_submission.get() is not None
            if progress:
                entered.set()
                await release.wait()
            frames.append("progress" if progress else "update")
            await super().notify(method, params, require_flushed=require_flushed)

        async def request(self, method, params):
            frames.append("permission")
            return {"outcome": {"outcome": "cancelled"}}

    class Runner:
        def run(self, request, *, planning_progress_observer=None, **kwargs):
            assert planning_progress_observer is not None
            planning_progress_observer(PlanningProgressEvent(run_id=request.run_id, session_id=request.session_id,
                settled_turn=1, max_planning_turns=1))
            if branch == "failure":
                raise RuntimeError("owned planner failure")
            return AgentRunResult(run_id=request.run_id, session_id=request.session_id, execution_mode=request.execution_mode,
                status=AgentRunStatus.AWAITING_APPROVAL if branch == "permission" else AgentRunStatus.COMPLETED,
                final_state="AWAITING_APPROVAL" if branch == "permission" else "COMPLETED", output_text="answer",
                tool_calls=(), total_cost_usd=Decimal("0"), mutation_count=0, provider_keys_resolvable=(),
                plan_hash="fixture-plan" if branch == "permission" else None)

    adapter = AcpDuplexAdapter(runner=checked_agent_runner(Runner()), workspace_root=tmp_path,
        sessions=InMemoryAcpSpecSessionStore(), outbound=Outbound())
    response = await adapter.handle_client_request({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    session = response.response["result"]["sessionId"]
    if branch == "chat":
        await adapter.handle_client_request({"jsonrpc": "2.0", "id": 2, "method": "session/set_mode", "params": {"sessionId": session, "modeId": "chat"}})
    frames.clear()
    call = asyncio.create_task(adapter.handle_client_request({"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
        "params": {"sessionId": session, "prompt": [{"type": "text", "text": "Explain"}]}}))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await loop_turn()
        assert frames == [] and not call.done()
        release.set()
        if branch == "failure":
            with pytest.raises(RuntimeError, match="owned planner failure"):
                await asyncio.wait_for(call, 2)
        else:
            await asyncio.wait_for(call, 2)
        assert frames[0] == "progress"
        if branch == "permission":
            assert "permission" in frames[1:]
    finally:
        release.set()
        await asyncio.gather(call, return_exceptions=True)
        await adapter.aclose()
