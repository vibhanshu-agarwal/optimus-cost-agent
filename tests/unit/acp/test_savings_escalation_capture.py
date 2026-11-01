"""Plan 12.9 Checkpoint B finding 9: an escalated Auto turn's accounting, captured through the real launch composition.

The launch is `test_auto_escalation_end_to_end`'s (the real harness, server, adapter, AgentRunner and H over a scripted
provider; offline, no paid call) with durable capture on. The escalated turn must leave one Auto context in one epoch,
every request's receipt exactly once (the classifier's, the first model's and the escalation model's), and a report
over those captured receipts must count all of them in the Auto scope and price all of them in each B1 column."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from optimus.acp import bootstrap as bootstrap_module
from optimus.acp import server as acp_server
from optimus.acp.auto_composition import AutoComposition
from optimus.acp.bootstrap import build_configured_server
from optimus.acp.shapes import LOOP_CONTINUE_OPTION_ID
from optimus.acp.spec import AcpDuplexAdapter
from optimus.gateway.client import GatewayClient
from optimus.telemetry.fanout import TelemetryFanout
from optimus.usage.durable_capture import DurableCapture, host_outbox_root
from optimus_gateway import usage_report as report
from optimus_gateway.usage_store import ReportFacts
from optimus_model_policy.binding import auto_snapshot
from optimus_model_policy.savings_references import ReferenceSet
from optimus_security import durable_outbox as ob
from optimus_security import usage_capture_contract as uc
from optimus_security import usage_report_contract as urc
from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter
from tests.unit.acp.test_auto_escalation_end_to_end import PLAN, READ_A, _next_permission
from tests.unit.acp.test_auto_launch_end_to_end import GEMINI, LUNA, AutoGateway, FakeRedisRuntime, Provider
from tests.unit.acp.test_bootstrap import _fake_client_runtime
from tests.unit.optimus_gateway.model_policy_support import SHARED_SECRET
from tests.unit.optimus_gateway.test_usage_report import _reference


@pytest.fixture
def captured_launch(monkeypatch, tmp_path):
    snapshot = auto_snapshot()
    assert snapshot is not None
    provider = Provider(tiers=["easy"], answers=[READ_A] * 4 + [PLAN])
    gateway = AutoGateway(snapshot, provider)
    adapters: list[AcpDuplexAdapter] = []
    capture = DurableCapture(ob.OutboxWriter(host_outbox_root(tmp_path / "config")), ack_wait=5.0)
    capture.enable_report_context()  # the Gateway listed the feature
    monkeypatch.setattr("optimus.acp.preflight.run_preflight", lambda environ, **kwargs: "redis://localhost:6379/0")
    monkeypatch.setattr("optimus.acp.bootstrap.RedisRuntime.from_url", lambda url: FakeRedisRuntime())
    monkeypatch.setattr("optimus.acp.bootstrap.build_client_mcp_runtime", lambda **kwargs: _fake_client_runtime())
    monkeypatch.setattr(bootstrap_module, "_build_gateway_client", lambda *, settings, timeout_seconds, durable_capture=None: GatewayClient(
        settings=settings, transport=gateway, **({} if durable_capture is None else {"capture": durable_capture.hook})))
    monkeypatch.setattr(TelemetryFanout, "__call__", lambda self, event: None)
    monkeypatch.setattr(acp_server, "AcpDuplexAdapter", lambda **kwargs: adapters.append(AcpDuplexAdapter(**kwargs)) or adapters[-1])
    environ = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765", "OPTIMUS_API_KEY": SHARED_SECRET, "OPTIMUS_REDIS_URL": "redis://localhost:6379/0"}
    (tmp_path / "a.py").write_text("0123456789abcdef", encoding="utf-8")
    server = build_configured_server(environ=environ, workspace_root=tmp_path, auto_composition=AutoComposition(snapshot),
                                     durable_capture=capture)
    return server, provider, capture, snapshot


async def _escalate(server, tmp_path) -> str:
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def call(request_id: str, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=10)

    try:
        await call("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session_id = (await call("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []}))["result"]["sessionId"]
        prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "What is the release code name? Record it in b.py."}]}
        await reader.send({"jsonrpc": "2.0", "id": "t1", "method": "session/prompt", "params": prompt})
        seen: set[Any] = set()
        checkin = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": checkin["id"], "result": {"outcome": {"outcome": "selected", "optionId": LOOP_CONTINUE_OPTION_ID}}})
        approval = await asyncio.wait_for(_next_permission(writer, seen), timeout=10)
        await reader.send({"jsonrpc": "2.0", "id": approval["id"], "result": {"outcome": {"outcome": "selected", "optionId": "approve"}}})
        assert (await asyncio.wait_for(writer.wait_for_response("t1"), timeout=10))["result"]["stopReason"] == "end_turn"
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=10)
    return session_id


async def test_an_escalated_turn_is_one_auto_context_and_every_model_s_receipt_counts_once(captured_launch, tmp_path):
    server, provider, capture, snapshot = captured_launch
    session_id = await _escalate(server, tmp_path)
    turn = f"{session_id}:1"
    capture.stop()
    records = [dict(r.payload) for r in ob.scan_stream(capture.writer.directory).records]
    for payload in records:
        uc.validate_payload(payload, writer="host")

    begins = [r for r in records if r["kind"] == uc.EPOCH_BEGIN and r["turn_id"] == turn]
    contexts = [r for r in records if r["kind"] == uc.TURN_REPORT_CONTEXT and r["turn_id"] == turn]
    receipts = [r for r in records if r["kind"] == uc.ATTEMPT_RECEIPT and r["turn_id"] == turn]
    assert len(begins) == 1 and [(c["selection"], c["registry_hash"]) for c in contexts] == [("auto", snapshot.effective_hash)]
    assert all(r["epoch_id"] == begins[0]["epoch_id"] for r in contexts + receipts), "one epoch for the whole escalated turn"
    assert provider.messages == [LUNA] * 4 + [GEMINI], "the turn escalated once"
    planning = [r for r in receipts if r["stage"] == "planning"]
    assert [r["requested_model"] for r in planning] == [LUNA] * 4 + [GEMINI]
    assert len({r["attempt_id"] for r in receipts}) == len(receipts), "each request's receipt once"

    # The report over exactly these captured receipts: all of them in the Auto scope, fully loaded, and each B1 column
    # reprices all of them (one subtraction against the same total).
    facts = ReportFacts("a" * 32, datetime(2026, 11, 2, tzinfo=UTC), tuple((r, False, False) for r in receipts),
                        {turn: ("complete",)}, {turn: ("auto",)}, uncommitted_streams=0)
    request = urc.ReportRequest(session_id, None, None, 100, None, 1, ((capture.writer.stream_id, 1),))
    # A flat schedule (cached priced as uncached) prices every request even though this provider reports no cached
    # split; a split schedule leaves them unpriced and says so (the disclosed classification/cached-split limit).
    flat, split = _reference("ref-flat", input="1", output="4", cached="1"), _reference("ref-split", input="1", output="4", cached="0.1")
    body = urc.validate_report(report.report_body(facts, request, ReferenceSet(version=1, references=(flat, split)),
                                                  key=b"k" * 32, principal="p"))
    total = sum(Decimal(r["reported_cost_usd"]) for r in receipts)
    assert {r["stage"] for r in receipts} == {"classification", "planning"}, "the classifier's overhead is in the turn"
    assert body["auto"]["attempts"] == len(receipts) == 6 and Decimal(body["auto"]["known_usd"]) == total
    flat_column, split_column = body["comparisons"]["columns"]
    # Every request repriced: five planning calls at 10 in / 5 out and the classification at 10 in, at 1 and 4 per M.
    baseline = sum(Decimal(r["input_tokens"]) * 1 + Decimal(r["output_tokens"]) * 4 for r in receipts) / Decimal(1_000_000)
    assert flat_column["complete"] and flat_column["priced_attempts"] == 6 and Decimal(flat_column["baseline_known_usd"]) == baseline
    assert Decimal(flat_column["savings_usd"]) == baseline - total, "one subtraction against the fully loaded total"
    assert not split_column["complete"] and split_column["unpriced"] == [
        {"reason": "cached_split_unreported", "attempts": 6, "tokens": sum(r["input_tokens"] + r["output_tokens"] for r in receipts)}]
