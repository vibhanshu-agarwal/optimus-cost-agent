"""Integration tests for failed-attempt usage through the real urllib transport.

These tests use a local ThreadingHTTPServer on loopback to exercise the real
GatewayClient + UrllibGatewayTransport against deterministic HTTP 503 responses.
They are NOT marked requires_gateway and do NOT claim real-provider behavior.
"""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.runtime.modes import ExecutionMode
from optimus.usage.accounting import UsageAccountingService


def _start_local_server(handler_class: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, int]:
    """Start a local HTTP server on a random port and return (server, port)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


FINAL_PLAN_TEXT = "READ target.py\nWRITE target.py\nupdated content\n"


class ReportedFailureThenSuccessHandler(BaseHTTPRequestHandler):
    """First request: 503 with valid gateway_usage. Second request: 200 with final plan."""

    request_count = 0

    def do_POST(self) -> None:
        ReportedFailureThenSuccessHandler.request_count += 1
        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)  # consume body

        if ReportedFailureThenSuccessHandler.request_count == 1:
            body = json.dumps(
                {
                    "error": "temporary overload",
                    "gateway_usage": {
                        "gateway_request_id": "gw-local-failed-1",
                        "provider": "local-test",
                        "cache_hit": False,
                        "billing_units": 5,
                        "cost_usd": "0.001",
                        "service": "responses",
                        "native_unit": "tokens",
                        "optimus_credits_debited": "0.1",
                        "price_snapshot_id": "prices-local",
                    },
                }
            ).encode("utf-8")
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = json.dumps(
                {
                    "id": "resp-local-success",
                    "output_text": FINAL_PLAN_TEXT,
                    "gateway_usage": {
                        "gateway_request_id": "gw-local-success-2",
                        "provider": "local-test",
                        "cache_hit": False,
                        "billing_units": 10,
                        "cost_usd": "0.002",
                        "service": "responses",
                        "native_unit": "tokens",
                        "optimus_credits_debited": "0.2",
                        "price_snapshot_id": "prices-local",
                    },
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass  # suppress console logging during tests


class UnknownCostHandler(BaseHTTPRequestHandler):
    """Always returns 503 with no gateway_usage field."""

    request_count = 0

    def do_POST(self) -> None:
        UnknownCostHandler.request_count += 1
        content_length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_length)

        body = json.dumps({"error": "temporary outage"}).encode("utf-8")
        self.send_response(503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args) -> None:  # noqa: A002
        pass


def test_reported_failure_then_success_charges_both_attempts(tmp_path: Path) -> None:
    """Real urllib transport: 503 with usage + 200 with usage -> both charged."""
    ReportedFailureThenSuccessHandler.request_count = 0
    server, port = _start_local_server(ReportedFailureThenSuccessHandler)
    try:
        (tmp_path / "target.py").write_text("original\n", encoding="utf-8")
        settings = OptimusGatewaySettings(
            gateway_url=f"http://127.0.0.1:{port}",
            optimus_api_key="test-key-local",
            production_mode=False,
        )
        client = GatewayClient(settings=settings, timeout_seconds=5.0)
        accounting = UsageAccountingService()
        runner = AgentRunner(
            gateway_client=client,
            model="local-test-model",
            usage_accounting=accounting,
        )

        result = runner.run(
            AgentRunRequest(
                run_id="run-transport-reported",
                session_id="session-transport",
                task="Update target.py",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=tmp_path,
                max_planning_turns=1,
            )
        )

        # Exactly 2 HTTP requests hit the server.
        assert ReportedFailureThenSuccessHandler.request_count == 2
        # Result: awaiting approval with aggregated cost.
        assert result.status is AgentRunStatus.AWAITING_APPROVAL
        assert result.total_cost_usd == Decimal("0.003")
        assert result.cost_complete is True
        assert result.unknown_cost_attempt_count == 0
        # Both attempts persisted as ProviderUsage rows.
        assert len(accounting.provider_ledger.entries) == 2
        assert [e.request_id for e in accounting.provider_ledger.entries] == [
            "run-transport-reported:planning:1:1",
            "run-transport-reported:planning:1:2",
        ]
        assert accounting.provider_ledger.gateway_request_ids(run_id="run-transport-reported") == {
            "gw-local-failed-1",
            "gw-local-success-2",
        }
    finally:
        server.shutdown()
        server.server_close()


def test_unknown_cost_stops_after_one_request(tmp_path: Path) -> None:
    """Real urllib transport: 503 without usage -> immediate stop, no retry."""
    UnknownCostHandler.request_count = 0
    server, port = _start_local_server(UnknownCostHandler)
    try:
        (tmp_path / "target.py").write_text("original\n", encoding="utf-8")
        settings = OptimusGatewaySettings(
            gateway_url=f"http://127.0.0.1:{port}",
            optimus_api_key="test-key-local",
            production_mode=False,
        )
        client = GatewayClient(settings=settings, timeout_seconds=5.0)
        accounting = UsageAccountingService()
        runner = AgentRunner(
            gateway_client=client,
            model="local-test-model",
            usage_accounting=accounting,
        )

        result = runner.run(
            AgentRunRequest(
                run_id="run-transport-unknown",
                session_id="session-transport",
                task="Update target.py",
                execution_mode=ExecutionMode.AGENT,
                workspace_root=tmp_path,
                max_planning_turns=1,
            )
        )

        # Exactly 1 HTTP request — no retry dispatched.
        assert UnknownCostHandler.request_count == 1
        assert result.status is AgentRunStatus.TERMINATED
        assert result.stop_reason == "PLANNING_GATEWAY_COST_UNKNOWN"
        assert result.total_cost_usd == Decimal("0")
        assert result.cost_complete is False
        assert result.unknown_cost_attempt_count == 1
        assert result.plan_hash is None
        assert result.mutation_count == 0
        # Zero persisted usage rows.
        assert accounting.provider_ledger.entries == ()
    finally:
        server.shutdown()
        server.server_close()
