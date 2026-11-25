"""Offline ACP Gateway error contracts through the owning capture and runner paths."""

from __future__ import annotations

import asyncio
import io
import json
from decimal import Decimal
from urllib.error import HTTPError, URLError

import pytest

from optimus.acp import server as server_module
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.server import AcpStreamServer
from optimus.acp.spec import AcpDuplexAdapter
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway import client as gateway_client
from optimus.gateway.attempts import AttemptIntegrityError
from optimus.gateway.errors import GatewayFailureFacts, GatewayFailureReason, GatewayHttpError, PreflightProof
from optimus.usage.accounting import UsageAccountingService
from optimus.usage.turn_settlement import TurnSettlement
from optimus_model_policy import binding
from optimus_security import usage_capture_contract as capture_contract
from tests.integration.acp.test_server_stream import InteractiveLineReader, MemoryLineWriter, configured_test_agent_server, roundtrip
from tests.unit.usage.test_capture_wiring import _capture, _records

_REFUSAL = b'{"code":"CAPACITY_REFUSED","retryable":false,"route_attempts":[]}'
_USAGE = {"gateway_request_id": "gw-used", "provider": "fixture", "billing_units": 3, "cost_usd": "0.0003"}
_ERROR = {"code": -32603, "message": "gateway request failed"}


def _failed_body(*, matched: bool) -> bytes:
    return json.dumps(
        {
            "message": "gateway-private-canary",
            "gateway_usage": _USAGE,
            "route_attempts": [{"attempt": 1, "outcome": "completed", "gateway_request_id": "gw-used" if matched else "other"}],
        }
    ).encode()


def _mixed_body() -> bytes:
    return json.dumps(
        {
            "gateway_usage": _USAGE,
            "route_attempts": [
                {"attempt": 1, "outcome": "uncertain", "gateway_request_id": "gw-unknown"},
                {"attempt": 2, "outcome": "completed", "gateway_request_id": "gw-used"},
            ],
        }
    ).encode()


def _recording_refusal_body() -> bytes:
    body = json.loads(_failed_body(matched=True))
    body["route_attempts"].append({"attempt": 2, "outcome": "rejected", "gateway_request_id": "gw-not-accepted"})
    return json.dumps(body).encode()


def _invalid_receipt_body() -> bytes:
    body = json.loads(_failed_body(matched=True))
    body["gateway_usage"]["provider_request_id"] = "usage-id"
    body["route_attempts"][0]["provider_request_id"] = "different-attempt-id"
    return json.dumps(body).encode()


def _client(capture=None, *, scheme="http"):
    settings = OptimusGatewaySettings(
        gateway_url=f"{scheme}://127.0.0.1:8765", optimus_api_key="opt_fixture_gateway_only"  # pragma: allowlist secret
    )
    return gateway_client.GatewayClient(settings=settings, capture=capture.hook if capture is not None else None)


@pytest.mark.parametrize(
    ("body", "transport_result", "reason", "certainty", "receipts"),
    [
        (_REFUSAL, "direct", "GATEWAY_PREFLIGHT_REFUSED", "no_effect", [("rejected", "0")]),
        (_failed_body(matched=True), "direct", "GATEWAY_ACCOUNTED_FAILURE", "unknown", [("completed", "0.0003")]),
        (_mixed_body(), "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("uncertain", None), ("completed", "0.0003")]),
        (_invalid_receipt_body(), "direct", "GATEWAY_ATTEMPT_INTEGRITY", "unknown", []),
        (_recording_refusal_body(), "recording-refused", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("completed", "0.0003")]),
        (_failed_body(matched=False), "direct", "GATEWAY_ATTEMPT_INTEGRITY", "unknown", [("unattributed", "0.0003"), ("uncertain", None)]),
        (_REFUSAL, "custom", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL, "redirected", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL, "wrong-url", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL, "proxy", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL, "tunnel", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL.replace(b"false", b"true"), "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("uncertain", None)]),
        (_REFUSAL.replace(b"CAPACITY_REFUSED", b"UNKNOWN_REFUSAL"), "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("uncertain", None)]),
        (_REFUSAL, "no-reply", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("uncertain", None)]),
        (_failed_body(matched=True), "no-capture", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", []),
        (_REFUSAL, "no-capture", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", []),
        (_REFUSAL[:-1] + b',"gateway_usage":null}', "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL[:-1] + b',"message":"\xff"}', "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL[:-3] + b'null}', "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("uncertain", None)]),
        (b'{"route_attempts":[{}],' + _REFUSAL[1:], "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
        (_REFUSAL[:-1] + b',"value":NaN}', "direct", "GATEWAY_OUTCOME_UNCERTAIN", "unknown", [("rejected", "0")]),
    ],
    ids=[
        "refused", "accounted", "mixed-uncertain", "invalid-receipt", "recording-refused", "integrity", "custom", "redirect-chain", "wrong-url",
        "proxy", "tunnel", "retryable", "unknown-code", "no-reply", "no-capture", "refusal-without-capture",
        "usage", "utf8", "attempts", "duplicate", "nan",
    ],
)
async def test_offline_framed_gateway_fixture(tmp_path, monkeypatch, body, transport_result, reason, certainty, receipts):
    monkeypatch.setattr(binding, "ENFORCEMENT_ACTIVE", False)
    capture = None if transport_result == "no-capture" else _capture(tmp_path)
    scheme = "https" if transport_result == "tunnel" else "http"
    client = _client(capture, scheme=scheme)
    calls = []

    def open_stub(request, *, timeout):
        calls.append(request.full_url)
        if transport_result == "redirected":
            request.redirect_dict = {request.full_url: 1}
        if transport_result == "proxy":
            request.set_proxy("127.0.0.1:8767", "http")
        if transport_result == "tunnel":
            request.set_proxy("127.0.0.1:8767", "http")
            assert not request.has_proxy()
        if transport_result == "no-reply":
            raise URLError("gateway-private-canary")
        url = "http://127.0.0.1:8766/v1/responses" if transport_result == "wrong-url" else request.full_url
        raise HTTPError(url, 422, "gateway-private-canary", {}, io.BytesIO(body))

    def custom_transport(request):
        calls.append(request.url)
        raise GatewayHttpError(422, "gateway-private-canary", gateway_code="CAPACITY_REFUSED", retryable=False)

    if transport_result == "custom":
        monkeypatch.setattr(client, "_transport", type("CustomTransport", (), {"post_json": staticmethod(custom_transport)})())
    else:
        monkeypatch.setattr(gateway_client, "urlopen", open_stub)
    if transport_result == "recording-refused":
        record_attempt = TurnSettlement.record_attempt

        def reject_one_receipt(self, receipt):
            if receipt.gateway_request_id == "gw-not-accepted":
                raise ValueError("fixture recording failure")
            record_attempt(self, receipt)

        monkeypatch.setattr(TurnSettlement, "record_attempt", reject_one_receipt)
    dispatcher = JsonRpcDispatcher(gateway_client=client, durable_capture=capture)
    server = AcpStreamServer(dispatcher=dispatcher)

    try:
        response = await roundtrip(
            server, {"jsonrpc": "2.0", "id": "gw", "method": "optimus.gateway.responses", "params": {"model": "m", "input": "hi"}}
        )
    finally:
        records = _records(capture) if capture is not None else []

    assert calls == [f"{scheme}://127.0.0.1:8765/v1/responses"]
    observed = [(r["outcome"], r["reported_cost_usd"]) for r in records if r["kind"] == capture_contract.ATTEMPT_RECEIPT]
    assert observed == receipts
    if reason == "GATEWAY_ATTEMPT_INTEGRITY" or transport_result == "recording-refused":
        assert any(r["kind"] == capture_contract.INTEGRITY_FAILURE for r in records)
    assert response == {"jsonrpc": "2.0", "id": "gw", "error": {**_ERROR, "data": {"reason": reason, "effect_certainty": certainty}}}


@pytest.mark.parametrize(
    ("mode", "case", "reason"),
    [
        ("chat", "conflict", "GATEWAY_ATTEMPT_INTEGRITY"),
        ("agent", "conflict", "GATEWAY_ATTEMPT_INTEGRITY"),
        ("chat", "storage-first", "GATEWAY_ATTEMPT_INTEGRITY"),
        ("agent", "storage-first", "GATEWAY_ATTEMPT_INTEGRITY"),
        ("chat", "storage-only", None),
        ("agent", "storage-only", None),
        ("chat", "replacement", None),
        ("agent", "replacement", None),
        ("chat", "injected", "GATEWAY_OUTCOME_UNCERTAIN"),
        ("agent", "injected", "GATEWAY_OUTCOME_UNCERTAIN"),
        ("chat", "duplicate-publication", "GATEWAY_OUTCOME_UNCERTAIN"),
        ("chat", "refusal-stop", None),
        ("agent", "refusal-stop", None),
    ],
)
async def test_ndjson_gateway_failure_custody(tmp_path, monkeypatch, mode, case, reason):
    client = _client()
    accounting = UsageAccountingService()
    runner = AgentRunner(gateway_client=client, model="fixture/model", usage_accounting=accounting)
    calls = []

    def open_stub(request, *, timeout):
        calls.append(request.full_url)
        body = _REFUSAL if case == "refusal-stop" else _failed_body(matched=case == "storage-only")
        raise HTTPError(request.full_url, 422, "gateway-private-canary", {}, io.BytesIO(body))

    def storage_failure(*args, **kwargs):
        raise OSError("fixture storage failure")

    def inject_unwitnessed_integrity(request, **kwargs):
        raise AttemptIntegrityError("unwitnessed-attribution", attempts=())

    def inject_conflicting_facts(request, *, gateway_failure_facts, **kwargs):
        failure = GatewayHttpError(422, "gateway-private-canary")
        gateway_failure_facts.publish(failure, GatewayFailureReason.ATTEMPT_INTEGRITY)
        gateway_failure_facts.publish(failure, GatewayFailureReason.ACCOUNTED_FAILURE)
        raise failure

    async def replace_failure(self, turn):
        raise GatewayHttpError(502, "fixture exit failure")

    monkeypatch.setattr(gateway_client, "urlopen", open_stub)
    if case.startswith("storage-"):
        monkeypatch.setattr(accounting, "record_gateway_usage", storage_failure)
    if case == "replacement":
        monkeypatch.setattr(AcpDuplexAdapter, "_emit_exit_cost_alerts", replace_failure)
    if case == "injected":
        monkeypatch.setattr(runner, "run", inject_unwitnessed_integrity)
    if case == "duplicate-publication":
        monkeypatch.setattr(runner, "run", inject_conflicting_facts)

    capture = _capture(tmp_path)
    server = AcpStreamServer(
        dispatcher=JsonRpcDispatcher(agent_runner=runner, workspace_root=tmp_path), durable_capture=capture, interactive_recovery=False
    )
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(server.serve_ndjson(reader, writer))

    async def rpc(request_id, method, params):
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=5)

    try:
        await rpc("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        created = await rpc("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []})
        session_id = created["result"]["sessionId"]
        mode_set = await rpc("mode", "session/set_mode", {"sessionId": session_id, "modeId": mode})
        assert "result" in mode_set
        response = await rpc("prompt", "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": "Explain the greeting."}]})
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=5)
        records = _records(capture)

    assert response["id"] == "prompt"
    assert len(calls) == (0 if case in {"injected", "duplicate-publication"} else 1)
    if case in {"conflict", "storage-first", "storage-only", "replacement"}:
        paid = [Decimal(r["reported_cost_usd"]) for r in records if r["kind"] == capture_contract.ATTEMPT_RECEIPT and r["reported_cost_usd"]]
        assert paid == [Decimal("0.0003")]
    if reason is not None:
        assert response["error"] == {**_ERROR, "data": {"reason": reason, "effect_certainty": "unknown"}}
    elif case == "refusal-stop":
        assert response["result"]["stopReason"] == "end_turn"
        expected_stop = "CHAT_GATEWAY_REFUSED" if mode == "chat" else "PLANNING_GATEWAY_REFUSED"
        assert response["result"]["_meta"]["runStopReason"] == expected_stop
        assert "error" not in response
    else:
        assert response["error"] == {"code": -32603, "message": "fixture exit failure" if case == "replacement" else "fixture storage failure"}


@pytest.mark.parametrize(
    ("path", "proof"),
    [("/v1/decisions", PreflightProof.DIRECT_REFUSAL), ("/v1/tools/web/search", None)],
)
def test_gateway_preflight_proof_is_limited_to_model_calls(monkeypatch, path, proof):
    def open_stub(request, *, timeout):
        raise HTTPError(request.full_url, 422, "refused", {}, io.BytesIO(_REFUSAL))

    monkeypatch.setattr(gateway_client, "urlopen", open_stub)
    request = gateway_client.GatewayRequest(
        method="POST", url=f"http://127.0.0.1:8765{path}", headers={}, payload={}, timeout_seconds=1
    )
    with pytest.raises(GatewayHttpError) as failure:
        gateway_client.UrllibGatewayTransport().post_json(request)
    assert failure.value.preflight_proof is proof


def test_discarded_gateway_facts_cannot_be_used_by_a_detached_worker():
    facts = GatewayFailureFacts()
    failure = AttemptIntegrityError("unwitnessed-attribution", attempts=())
    facts.discard()
    facts.publish(failure, GatewayFailureReason.ATTEMPT_INTEGRITY)
    facts.supply_uncertainty(failure)
    assert facts.consume(failure) is None


@pytest.mark.parametrize("boundary", ["approved-execution", "torn-down"])
async def test_ndjson_gateway_recovery_does_not_reuse_planning_custody(tmp_path, monkeypatch, boundary):
    configured = configured_test_agent_server(tmp_path, output_text="WRITE example.py\ncontent")
    failure = GatewayHttpError(502, "fixture worker failure")
    runner_run = AgentRunner.run
    recovery_observed = asyncio.Event()
    observed = server_module._request_failure_payload

    def observe_recovery(*args, **kwargs):
        recovery_observed.set()
        return observed(*args, **kwargs)

    def run(self, request, *, operation_control=None, gateway_failure_facts=None, **kwargs):
        if boundary == "torn-down":
            assert gateway_failure_facts is not None
            operation_control.request_transport_teardown()
            gateway_failure_facts.publish(failure, GatewayFailureReason.ATTEMPT_INTEGRITY)
            raise failure
        if request.approval.approved:
            assert gateway_failure_facts is None
            raise failure
        return runner_run(
            self, request, operation_control=operation_control, gateway_failure_facts=gateway_failure_facts, **kwargs
        )

    monkeypatch.setattr(AgentRunner, "run", run)
    monkeypatch.setattr(server_module, "_request_failure_payload", observe_recovery)
    reader, writer = InteractiveLineReader(), MemoryLineWriter()
    serving = asyncio.create_task(configured.server.serve_ndjson(reader, writer))

    async def rpc(request_id, method, params):
        await reader.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return await asyncio.wait_for(writer.wait_for_response(request_id), timeout=5)

    try:
        await rpc("init", "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
        session = await rpc("new", "session/new", {"cwd": str(tmp_path), "mcpServers": []})
        session_id = session["result"]["sessionId"]
        await reader.send(
            {"jsonrpc": "2.0", "id": "prompt", "method": "session/prompt",
             "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change the greeting."}]}}
        )
        if boundary == "approved-execution":
            permission = await asyncio.wait_for(writer.wait_for_request("session/request_permission"), timeout=5)
            plan_hash = permission["params"]["options"][0]["metadata"]["planHash"]
            await reader.send(
                {
                    "jsonrpc": "2.0", "id": permission["id"],
                    "result": {
                        "outcome": {"outcome": "selected", "optionId": "approve"},
                        "metadata": {"approvalId": "approval-1", "planHash": plan_hash},
                    },
                }
            )
            response = await asyncio.wait_for(writer.wait_for_response("prompt"), timeout=5)
            assert response["error"] == {"code": -32603, "message": "fixture worker failure"}
            assert configured.fake_gateway_call_count == 1
        else:
            await asyncio.wait_for(recovery_observed.wait(), timeout=5)
            assert all(message.get("id") != "prompt" for message in writer.messages)
            assert configured.fake_gateway_call_count == 0
    finally:
        reader.close()
        await asyncio.wait_for(serving, timeout=5)
    if boundary == "torn-down":
        assert all(message.get("id") != "prompt" for message in writer.messages)
