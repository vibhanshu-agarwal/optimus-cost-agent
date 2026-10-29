"""Plan 12.4 Checkpoint B (Codex round 68): Auto through the real launch composition, offline.

``build_configured_server`` with the approved Auto composition builds the real harness, server, adapter and
``AgentRunner``, with H installed by ``auto_router``. Only external dependencies are replaced: Redis and the client-MCP
runtime by fakes, the telemetry fanout by a recorder, and the Gateway's network by an in-process transport that hands
every request to the real Gateway handlers (``/v1/responses`` and ``/v1/decisions``) under the same composition, with a
scripted provider behind them. The test drives the server over NDJSON, as an editor does. No network or paid call.

Two Chat notes turns of 24 KiB each, then an Agent turn whose history exceeds the tail and is compacted (the ordinary
compaction schedule, ``test_ordinary_compaction_flow.py``). H's rules are unsure of all three prompts, so Jev decides:
easy, complex, easy. Each turn is sent to its own tier's model; the Agent turn plans on Luna, not the launch's
default planner (Gemini), so a runner that fell back to its launch model would be refused; and that turn's
classification, summarization and planning receipts settle in the same turn.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

from context_engine.summary import WRAPPER_OPEN
from optimus.acp import bootstrap as bootstrap_module
from optimus.acp import server as acp_server
from optimus.acp.auto_composition import AutoComposition
from optimus.acp.bootstrap import build_configured_server
from optimus.acp.spec import AcpDuplexAdapter
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.client import GatewayClient, GatewayRequest
from optimus.telemetry.events import TelemetryEventKind
from optimus.telemetry.fanout import TelemetryFanout
from optimus_gateway.decisions import handle_decision_request
from optimus_gateway.upstream_client import DecisionResult, ProviderMessageResult
from optimus_model_policy.binding import auto_snapshot
from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter
from tests.unit.acp.test_bootstrap import _fake_client_runtime
from tests.unit.acp.test_context_engine_admission import SUMMARY
from tests.unit.acp.test_ordinary_compaction_flow import FACT, synthetic_notes
from tests.unit.agent.test_route_binding import InProcessGateway
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET

LUNA, HAIKU, GEMINI, JEV = "openai/gpt-6-luna", "anthropic/claude-haiku-5.5", "google/gemini-3.8-flash", "typesafe/jev-1.14"
PLAN = "WRITE a.py\nCODE_NAME = 'TANGERINE-47'\n"


class Provider:
    """The scripted provider behind the real Gateway handlers: Jev answers the scripted tiers; Haiku, the summarizer,
    answers summaries; every other call is the turn's own, answered in order."""

    def __init__(self, tiers: list[str], answers: list[str]) -> None:
        self.tiers, self.answers = list(tiers), list(answers)
        self.messages: list[str] = []
        self.decisions = 0

    def create_message_once(self, *, model, input_text, max_tokens, provider_controls, reasoning) -> ProviderMessageResult:
        self.messages.append(model)
        text = SUMMARY if model == HAIKU else self.answers.pop(0)
        return ProviderMessageResult(
            message_id=f"gen-{len(self.messages)}", output_text=text, input_tokens=10, output_tokens=5, total_tokens=15,
            billing_units=15, cost_usd=Decimal("0.0002"), provider="openrouter", resolved_provider="Anthropic" if model == HAIKU else "Other",
            requested_model=model, resolved_model=model, model_version=None, cache_hit=False, finish_reason="stop",
            router_attempt=1, router_pipeline=(),
        )  # fmt: skip

    def create_decision_once(self, *, model, state, questions, provider_controls) -> DecisionResult:
        self.decisions += 1
        answer = {"type": "choice", "choice": self.tiers.pop(0), "confidence": 0.99}
        return DecisionResult(
            decision_id=f"gen-dec-{self.decisions}", resolved_model=model + "-20261014", resolved_provider="TypeSafe",
            answers={"tier": answer}, input_tokens=10, output_tokens=0, cost_usd=Decimal("0.0000004"),
        )  # fmt: skip


class AutoGateway(InProcessGateway):
    """The real Gateway handlers in process, routed by path."""

    def post_json(self, request: GatewayRequest) -> dict[str, Any]:
        if urlsplit(request.url).path != "/v1/decisions":
            return super().post_json(request)
        self.payloads.append(request.payload)
        status, body = handle_decision_request(
            authorization_header=request.headers.get("Authorization"), request_body=request.payload, config=self.config, upstream_client=self.upstream
        )
        assert status == 200, body
        return body


class FakeRedisRuntime:
    def ping(self):
        return None

    def sync_state_store(self):
        return InMemoryAgentStateStore()

    def telemetry_adapter(self):
        return object()

    def run_sync(self, operation, *, timeout=None):
        return asyncio.run(operation())

    def close(self, *, timeout=None):
        return "record"

    async def close_async(self, *, timeout=None):
        class Clean:
            is_clean = True

        return Clean()


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    snapshot = auto_snapshot()
    assert snapshot is not None
    provider = Provider(tiers=["easy", "complex", "easy"], answers=["Noted.", "Noted.", PLAN])
    gateway = AutoGateway(snapshot, provider)
    events: list[Any] = []
    adapters: list[AcpDuplexAdapter] = []
    monkeypatch.setattr("optimus.acp.preflight.run_preflight", lambda environ, **kwargs: "redis://localhost:6379/0")
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRedisRuntime())
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: _fake_client_runtime())
    monkeypatch.setattr(bootstrap_module, "_build_gateway_client", lambda *, settings, timeout_seconds: GatewayClient(settings=settings, transport=gateway))
    monkeypatch.setattr(TelemetryFanout, "__call__", lambda self, event: events.append(event))
    monkeypatch.setattr(acp_server, "AcpDuplexAdapter", lambda **kwargs: adapters.append(AcpDuplexAdapter(**kwargs)) or adapters[-1])
    environ = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": SHARED_SECRET, "OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}
    server = build_configured_server(environ=environ, workspace_root=tmp_path, auto_composition=AutoComposition(snapshot))
    return server, provider, gateway, events, adapters


async def test_auto_turns_route_plan_compact_and_settle_through_the_real_launch_composition(launch, tmp_path: Path) -> None:
    server, provider, gateway, events, adapters = launch
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def call(request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=10)

    def prompt(session_id: str, text: str) -> dict[str, Any]:
        return {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]}

    try:
        await call("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session_id = (await call("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []}))["result"]["sessionId"]
        assert "result" in await call("chat", "session/set_mode", {"sessionId": session_id, "modeId": "chat"})
        assert (await call("t1", "session/prompt", prompt(session_id, synthetic_notes(1))))["result"]["stopReason"] == "end_turn"
        assert (await call("t2", "session/prompt", prompt(session_id, synthetic_notes(2))))["result"]["stopReason"] == "end_turn"
        assert "result" in await call("agent", "session/set_mode", {"sessionId": session_id, "modeId": "agent"})

        await reader.send({"jsonrpc": "2.0", "id": "t3", "method": "session/prompt", "params": prompt(session_id, "What is the release code name? Record it in a.py.")})
        permission = await asyncio.wait_for(writer.wait_for_request("session/request_permission"), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": permission["id"], "result": {"outcome": {"outcome": "selected", "optionId": "approve"}}})
        assert (await asyncio.wait_for(writer.wait_for_response("t3"), timeout=10))["result"]["stopReason"] == "end_turn"

        [adapter] = adapters
        settlement = adapter._sessions.get(session_id).cost_settlement  # noqa: SLF001
        stages = {turn: {(r.stage, r.outcome) for r in settlement.receipts(f"{session_id}:{turn}")} for turn in (1, 2, 3)}
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=10)

    # Each turn went to its own tier's model; Jev decided each; the Agent turn planned on its model.
    assert provider.messages[:2] == [LUNA, GEMINI] and provider.messages[-1] == LUNA and provider.decisions == 3
    sent = [payload["model"] for payload in gateway.payloads]
    assert sent.count(JEV) == 3 and sent[-1] == LUNA
    routed = [event.payload for event in events if event.kind is TelemetryEventKind.AUTO_ROUTING]
    assert [(r["disposition"], r["tier"], r["model_id"], r["answered_by"], r["classifier_attempt"]) for r in routed] == [
        ("routed", "easy", LUNA, "classifier", "completed"),
        ("routed", "complex", GEMINI, "classifier", "completed"),
        ("routed", "easy", LUNA, "classifier", "completed"),
    ]
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "CODE_NAME = 'TANGERINE-47'\n"

    # Compaction ran on the third turn only, through the summarizer, and its summary reached the planning request.
    assert provider.messages[2:-1] and set(provider.messages[2:-1]) == {HAIKU}
    [planning] = [payload for payload in gateway.payloads if payload["model"] == LUNA and WRAPPER_OPEN in payload["input"]]
    assert FACT not in planning["input"], "the summarized turn's own text is no longer sent"

    # Every attempt of the compacted turn settled in that turn.
    assert stages[1] == {("classification", "completed"), ("answer", "completed")}
    assert stages[2] == {("classification", "completed"), ("answer", "completed")}
    assert stages[3] == {("classification", "completed"), ("summarization", "completed"), ("planning", "completed")}
