"""Plan 12.2 Task 5: a reply cut off at the output limit never becomes a complete result.

A length-limited planning reply is refused before it is parsed, stored, offered for approval or
executed, even when its prefix is a syntactically valid WRITE plan; its usage receipt is kept. A
length-limited Chat answer is shown but marked incomplete and recorded as a non-success. These
checks are active now; they do not depend on the model registry (operator decision 2026-10-02).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.runtime.modes import ExecutionMode

WRITE_PLAN = "WRITE example.py\nnew content\nTEST pytest -q"
ANSWER = "calc.py defines add() and subtract(), and"


class _Gateway:
    def __init__(self, text: str, finish_reason: str | None) -> None:
        self.calls = 0
        self._text = text
        self._finish_reason = finish_reason

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, input_text, metadata
        self.calls += 1
        return GatewayResponse(
            response_id=f"resp-{self.calls}",
            output_text=self._text,
            gateway_usage=GatewayUsage(gateway_request_id=f"gw-{self.calls}", provider="test", billing_units=1, cost_usd=Decimal("0.001")),
            raw={"id": f"resp-{self.calls}"},
            finish_reason=self._finish_reason,
        )


def _runner(gateway: _Gateway) -> tuple[AgentRunner, InMemoryAgentStateStore]:
    store = InMemoryAgentStateStore()
    return AgentRunner(gateway_client=gateway, model="test-model", state_store=store), store


def _request(tmp_path: Path, mode: ExecutionMode) -> AgentRunRequest:
    return AgentRunRequest(run_id="run-1", session_id="sess-1", task="Change example.py", execution_mode=mode, workspace_root=tmp_path)


def test_length_limited_write_is_not_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    gateway = _Gateway(WRITE_PLAN, "length")
    runner, store = _runner(gateway)

    result = runner.run(_request(tmp_path, ExecutionMode.AGENT))

    # Like every other planning stop, a cut-off reply terminates the run (outcome: failed).
    assert result.status is AgentRunStatus.TERMINATED
    assert result.stop_reason == "PLANNING_OUTPUT_TRUNCATED"
    assert result.plan_hash is None, "no candidate plan is produced"
    assert result.mutation_count == 0
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "old\n"
    assert store.latest_plan_for_run(run_id="run-1") is None, "nothing is stored for approval"
    assert result.total_cost_usd == Decimal("0.001"), "the receipt for the cut-off call is kept"
    assert gateway.calls == 1, "a cut-off reply is not silently re-asked"
    assert "output limit" in result.output_text


def test_a_complete_write_plan_is_still_a_candidate(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    for finish_reason in ("stop", None):
        runner, _ = _runner(_Gateway(WRITE_PLAN, finish_reason))
        result = runner.run(_request(tmp_path, ExecutionMode.AGENT))
        assert result.status is AgentRunStatus.AWAITING_APPROVAL, finish_reason
        assert result.plan_hash


def test_a_length_limited_chat_answer_is_shown_but_marked_incomplete(tmp_path: Path) -> None:
    runner, _ = _runner(_Gateway(ANSWER, "length"))

    result = runner.run(_request(tmp_path, ExecutionMode.CHAT))

    assert result.status is AgentRunStatus.FAILED
    assert result.stop_reason == "CHAT_OUTPUT_TRUNCATED"
    assert result.output_text.startswith(ANSWER)
    assert "incomplete" in result.output_text
    assert result.total_cost_usd == Decimal("0.001")


async def test_acp_never_asks_permission_for_a_cut_off_plan(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    runner, _ = _runner(_Gateway(WRITE_PLAN, "length"))
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=runner, workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    created = (await adapter.handle_client_request(
        {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    )).response
    session_id = created["result"]["sessionId"]

    prompt = {
        "jsonrpc": "2.0",
        "id": "p1",
        "method": "session/prompt",
        "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change example.py"}]},
    }
    response = (await asyncio.wait_for(adapter.handle_client_request(prompt), timeout=10)).response

    assert response["result"] == {"stopReason": "end_turn"}
    assert outbound.requests == [], "no session/request_permission for a cut-off plan"
    texts = [
        n["params"]["update"]["content"]["text"]
        for n in outbound.notifications
        if n["params"]["update"]["sessionUpdate"] == "agent_message_chunk"
    ]
    assert any("output limit" in text for text in texts)
    record = adapter._sessions.get(session_id).conversation.records[1]  # noqa: SLF001
    assert record.outcome.value == "failed"
    assert record.effect_state.value == "none"


@pytest.mark.parametrize("finish_reason", ["content_filter", "error"])
def test_other_non_complete_finishes_are_left_to_the_verified_route_contract(tmp_path: Path, finish_reason: str) -> None:
    """Only the length limit is refused before registry activation; other statuses keep today's
    behaviour until a verified route contract is active (missing or unknown status fails then)."""
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    runner, _ = _runner(_Gateway(WRITE_PLAN, finish_reason))
    assert runner.run(_request(tmp_path, ExecutionMode.AGENT)).status is AgentRunStatus.AWAITING_APPROVAL
