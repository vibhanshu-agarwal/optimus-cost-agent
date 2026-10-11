"""Plan 12.2 Task 2: a committed turn records the effect its lifecycle actually settled.

Suppressing an operation can change the settled effect: a completed WRITE followed by a TEST that
cancellation stopped is PARTIAL, not COMPLETE. Cancellation and a denied start do not recompute the
effect themselves, so ``_commit_turn`` reads it through ``refresh_effect_state()`` instead of a
hard-coded NONE. After transport teardown the frozen snapshot stays the authority.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from optimus.acp.errors import INTERNAL_ERROR, AcpOutboundError
from optimus.acp.lifecycle import DirectiveKind, TurnControl
from optimus.acp.settlement import EffectState
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage


def _control() -> TurnControl:
    return TurnControl(session_id="sess-1", turn_seq=1)


def _complete_write(control: TurnControl, operation_id: str = "w1") -> None:
    assert control.try_start(DirectiveKind.WRITE, operation_id).granted is True
    control.complete_directive(DirectiveKind.WRITE, operation_id, "succeeded")


def test_refresh_after_cancel_settles_partial_for_a_completed_write() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1"), (DirectiveKind.TEST, "t1")])
    _complete_write(control)
    assert control.effect_state is EffectState.COMPLETE

    control.request_session_cancel()

    assert control.directive_state(DirectiveKind.TEST, "t1") == "suppressed"
    assert control.refresh_effect_state() is EffectState.PARTIAL
    # The refreshed value is also what settlement telemetry reads afterwards.
    assert control.effect_state is EffectState.PARTIAL
    assert control.current_settlement_fields()["effect_state"] == "partial"


def test_refresh_after_a_denied_start_settles_partial() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    _complete_write(control)
    control.request_session_cancel()
    assert control.refresh_effect_state() is EffectState.COMPLETE

    assert control.try_start(DirectiveKind.TEST, "t-late").granted is False

    assert control.directive_state(DirectiveKind.TEST, "t-late") == "suppressed"
    assert control.refresh_effect_state() is EffectState.PARTIAL


def test_refresh_after_cancel_before_any_effect_settles_none() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1"), (DirectiveKind.TEST, "t1")])

    control.request_session_cancel()

    assert control.directive_state(DirectiveKind.WRITE, "w1") == "suppressed"
    assert control.directive_state(DirectiveKind.TEST, "t1") == "suppressed"
    assert control.refresh_effect_state() is EffectState.NONE


def test_refresh_keeps_the_frozen_teardown_effect_after_a_late_denied_start() -> None:
    control = _control()
    control.register_operations([(DirectiveKind.WRITE, "w1")])
    _complete_write(control)
    control.request_transport_teardown()
    snapshot = control.frozen_snapshot
    assert snapshot is not None
    assert snapshot.effect_state is EffectState.COMPLETE

    assert control.try_start(DirectiveKind.TEST, "t-late").granted is False

    assert control.refresh_effect_state() is EffectState.COMPLETE
    assert control.frozen_snapshot is snapshot


# --- ACP commit projection ------------------------------------------------------------------------


class _PlanGateway:
    def __init__(self, plan_text: str) -> None:
        self._plan_text = plan_text

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, input_text, metadata
        return GatewayResponse(
            response_id="resp-1",
            output_text=self._plan_text,
            gateway_usage=GatewayUsage(
                gateway_request_id="gw-1",
                provider="test",
                billing_units=1,
                cost_usd=Decimal("0.001"),
            ),
            raw={"id": "resp-1"},
        )


async def _rpc(adapter: AcpDuplexAdapter, request: dict[str, Any]) -> dict[str, Any]:
    envelope = await adapter.handle_client_request(request)
    return envelope.response


class _FailingToolCallChannel(RecordingOutboundChannel):
    """Fails the tool-call ``session/update`` once armed, as a client write failure would."""

    def __init__(self) -> None:
        super().__init__()
        self.armed = False

    async def notify(self, method: str, params: dict[str, Any], *, require_flushed: bool = False) -> None:
        update = params.get("update") if isinstance(params, dict) else None
        if self.armed and isinstance(update, dict) and update.get("sessionUpdate") == "tool_call":
            raise AcpOutboundError(code=INTERNAL_ERROR, message="outbound delivery failed")
        await super().notify(method, params, require_flushed=require_flushed)


class _ApprovedTurn:
    """A real AgentRunner behind the ACP adapter, with an approved single prompt."""

    def __init__(self, tmp_path: Path, plan_text: str, *, outbound: RecordingOutboundChannel | None = None) -> None:
        self.shell_calls: list[list[str]] = []
        self.settlements: list[Any] = []
        runner = AgentRunner(
            gateway_client=_PlanGateway(plan_text),
            model="test-model",
            state_store=InMemoryAgentStateStore(),
            shell_runner=lambda command: self.shell_calls.append(command) or CompletedProcess(command, 0, "ok", ""),
        )
        self.outbound = outbound or RecordingOutboundChannel()
        self.adapter = AcpDuplexAdapter(
            runner=runner,
            workspace_root=tmp_path,
            sessions=InMemoryAcpSpecSessionStore(),
            outbound=self.outbound,
            settlement_sink=self.settlements.append,
        )
        self._tmp_path = tmp_path
        self.session_id = ""

    async def open(self) -> None:
        created = await _rpc(
            self.adapter,
            {"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(self._tmp_path), "mcpServers": []}},
        )
        self.session_id = created["result"]["sessionId"]

    async def prompt_and_approve(self) -> dict[str, Any]:
        prompt = {
            "jsonrpc": "2.0",
            "id": "p1",
            "method": "session/prompt",
            "params": {"sessionId": self.session_id, "prompt": [{"type": "text", "text": "Change example.py"}]},
        }
        task = asyncio.create_task(_rpc(self.adapter, prompt))
        permission = await asyncio.wait_for(self.outbound.wait_for_request("session/request_permission"), timeout=5)
        if isinstance(self.outbound, _FailingToolCallChannel):
            self.outbound.armed = True
        self.outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
        return await asyncio.wait_for(task, timeout=5)

    def cancel_after_the_write_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Send the client's real session/cancel after the WRITE's terminal and before the TEST lease.

        In that window cancellation suppresses the TEST without recomputing the effect, so a commit
        that read the cached value would record COMPLETE. Runs on the runner's worker thread.
        """
        loop = asyncio.get_running_loop()
        original = AgentRunner._execute_test_directives
        session = self

        def cancel_then_run_tests(self: AgentRunner, plan_text: str, *, toolbox: Any, gate: Any) -> Any:
            cancel = {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session.session_id}}
            asyncio.run_coroutine_threadsafe(session.adapter.handle_client_notification(cancel), loop).result(timeout=5)
            return original(self, plan_text, toolbox=toolbox, gate=gate)

        monkeypatch.setattr(AgentRunner, "_execute_test_directives", cancel_then_run_tests)

    def records(self) -> list[Any]:
        conversation = self.adapter._sessions.get(self.session_id).conversation  # noqa: SLF001
        return [conversation.records[seq] for seq in sorted(conversation.records)]

    def settled_effects(self) -> list[str]:
        return [event.payload["effect_state"] for event in self.settlements]


async def test_approved_write_and_test_turn_commits_complete_effect(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    turn = _ApprovedTurn(tmp_path, "WRITE example.py\nnew\nTEST pytest -q")
    await turn.open()

    response = await turn.prompt_and_approve()

    assert response["result"]["stopReason"] == "end_turn", response
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new"
    assert turn.shell_calls == [["pytest", "-q"]]
    records = turn.records()
    assert [record.outcome.value for record in records] == ["completed"]
    assert records[0].effect_state is EffectState.COMPLETE
    assert turn.settled_effects() == ["complete"]


async def test_approved_read_only_turn_commits_no_effect(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    turn = _ApprovedTurn(tmp_path, "READ example.py")
    await turn.open()

    response = await turn.prompt_and_approve()

    assert response["result"]["stopReason"] == "end_turn", response
    records = turn.records()
    assert [record.outcome.value for record in records] == ["completed"]
    assert records[0].effect_state is EffectState.NONE


async def test_session_cancel_between_approved_write_and_test_commits_partial_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    turn = _ApprovedTurn(tmp_path, "WRITE example.py\nnew\nTEST pytest -q")
    await turn.open()
    turn.cancel_after_the_write_terminal(monkeypatch)

    response = await turn.prompt_and_approve()

    assert response["result"]["stopReason"] == "cancelled", response
    assert (tmp_path / "example.py").read_text(encoding="utf-8") == "new"
    assert turn.shell_calls == []
    records = turn.records()
    assert [record.outcome.value for record in records] == ["cancelled"]
    assert records[0].effect_state is EffectState.PARTIAL
    assert turn.settled_effects() == ["partial"]


async def test_a_cancelled_turn_that_ends_without_a_commit_still_settles_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "example.py").write_text("old\n", encoding="utf-8")
    turn = _ApprovedTurn(tmp_path, "WRITE example.py\nnew\nTEST pytest -q", outbound=_FailingToolCallChannel())
    await turn.open()
    turn.cancel_after_the_write_terminal(monkeypatch)

    response = await turn.prompt_and_approve()

    # The tool-call update fails after the cancellation, so the turn errors before any commit.
    assert "error" in response, response
    assert turn.records() == []
    assert turn.settled_effects() == ["partial"]
