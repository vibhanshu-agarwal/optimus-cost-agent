from __future__ import annotations

import socket
import subprocess
import sys
import time
from decimal import Decimal

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from tests.integration.optimus_gateway.gateway_env import merge_gateway_subprocess_env

pytestmark = pytest.mark.requires_live_gateway


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def live_local_gateway_url():
    port = _pick_free_port()
    shared_secret = "live-gateway-smoke-secret"
    gateway_env = merge_gateway_subprocess_env(port=port, shared_secret=shared_secret)
    provider = gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"]

    process = subprocess.Popen(
        [sys.executable, "-m", "optimus_gateway", "--port", str(port)],
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
