from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.gateway.models import build_chat_completions_payload, parse_gateway_usage
from optimus.telemetry.events import TelemetryEvent
from optimus.telemetry.observability import GatewayObservabilityExporter
from tests.integration.optimus_gateway.gateway_env import (
    build_signed_child_manifest,
    merge_gateway_subprocess_env,
    strip_rejected_child_bind_env,
)

pytestmark = pytest.mark.requires_live_gateway


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_local_gateway_url():
    port = _pick_free_port()
    bind_host = "127.0.0.1"
    shared_secret = "live-gateway-smoke-secret"
    gateway_env = merge_gateway_subprocess_env(port=port, shared_secret=shared_secret)
    provider = gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"]

    # Plan 9.96 gates `python -m optimus_gateway` behind --bind-host/--manifest.
    # Build the real signed manifest from the same env the child receives, then
    # strip the inherited bind names the child rejects (bind is passed via CLI).
    manifest_arg = build_signed_child_manifest(gateway_env=gateway_env, port=port, bind_host=bind_host)
    strip_rejected_child_bind_env(gateway_env)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "optimus_gateway",
            "--bind-host",
            bind_host,
            "--port",
            str(port),
            "--manifest",
            manifest_arg,
        ],
        env=gateway_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    gateway_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            pytest.fail(f"local gateway exited early.\nstdout:\n{stdout}\nstderr:\n{stderr}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.connect(("127.0.0.1", port))
                break
            except OSError:
                time.sleep(0.2)
    else:
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(f"local gateway did not become ready.\nstdout:\n{stdout}\nstderr:\n{stderr}")

    try:
        yield gateway_url, shared_secret, provider
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_live_local_gateway_smoke_returns_real_usage(live_local_gateway_url):
    gateway_url, shared_secret, provider = live_local_gateway_url
    client = GatewayClient(
        settings=OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": gateway_url,
                "OPTIMUS_API_KEY": shared_secret,
                "OPTIMUS_PRODUCTION_MODE": "false",
            }
        )
    )

    response = client.create_response(
        model="claude-haiku",
        input_text="Reply with the single word: ok",
        metadata={"purpose": "local_gateway_smoke"},
    )

    assert response.response_id
    assert response.output_text.strip()
    assert response.gateway_usage.provider == provider
    assert response.gateway_usage.cost_usd > Decimal("0")
    assert response.gateway_usage.billing_units > 0


def test_live_local_gateway_chat_completions_returns_real_usage(live_local_gateway_url):
    gateway_url, shared_secret, provider = live_local_gateway_url
    payload = build_chat_completions_payload(
        model="claude-haiku",
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
    )
    request = urllib.request.Request(
        f"{gateway_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {shared_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        pytest.fail(f"chat completions live smoke failed ({exc.code}): {detail}")

    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert str(body["choices"][0]["message"]["content"]).strip()
    usage = parse_gateway_usage(body["gateway_usage"])
    assert usage.provider == provider
    assert usage.cost_usd > Decimal("0")
    assert usage.billing_units > 0
    assert usage.gateway_request_id


def test_live_local_gateway_observability_traces_accepts_real_exporter_batch(live_local_gateway_url):
    gateway_url, shared_secret, _provider = live_local_gateway_url
    exporter = GatewayObservabilityExporter(
        settings=OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": gateway_url,
                "OPTIMUS_API_KEY": shared_secret,
                "OPTIMUS_PRODUCTION_MODE": "false",
            }
        )
    )
    event = TelemetryEvent.model_call(
        run_id="run-live-obs-1",
        session_id="session-live-obs-1",
        request_id="req-live-obs-1",
        occurred_at=datetime(2026, 7, 26, tzinfo=UTC),
        model="claude-haiku",
        model_version="2026-07-01",
        provider="openrouter",
        cache_hit=False,
        billing_units=10,
        cost_usd=Decimal("0.001"),
        latency_ms=20,
        prompt="live observability smoke",
        response="ok",
        input_tokens=3,
        output_tokens=2,
    )

    response = exporter.export((event,))

    assert response["status"] == "accepted"
    assert response["gateway_request_id"]
    assert "gateway_usage" not in response
    assert "billing_units" not in response
    assert "cost_usd" not in response


def test_live_local_gateway_observability_traces_fails_closed_on_malformed_batch(live_local_gateway_url):
    gateway_url, shared_secret, _provider = live_local_gateway_url
    request = urllib.request.Request(
        f"{gateway_url}/v1/observability/traces",
        data=json.dumps({"events": ["not-an-object"]}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {shared_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=30)

    assert excinfo.value.code == 400
    body = json.loads(excinfo.value.read().decode("utf-8"))
    assert "event" in body["error"]
    assert "status" not in body
