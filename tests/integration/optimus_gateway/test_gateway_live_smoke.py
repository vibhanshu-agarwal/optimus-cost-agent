from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from decimal import Decimal

import pytest

from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient

pytestmark = pytest.mark.requires_live_gateway


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _gateway_provider_api_key(provider: str) -> str:
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            pytest.fail("ANTHROPIC_API_KEY is required when OPTIMUS_LOCAL_GATEWAY_PROVIDER=anthropic.")
        return api_key

    api_key = os.environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
    if not api_key:
        pytest.fail(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY is required for openai/openrouter live smoke tests."
        )
    return api_key


@pytest.fixture
def live_local_gateway_url():
    provider = os.environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
    if provider not in {"openai", "openrouter", "anthropic"}:
        pytest.fail(f"unsupported OPTIMUS_LOCAL_GATEWAY_PROVIDER for live smoke: {provider}")

    port = _pick_free_port()
    shared_secret = "live-gateway-smoke-secret"
    gateway_env = os.environ.copy()
    gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER"] = provider
    gateway_env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"] = shared_secret
    gateway_env["OPTIMUS_LOCAL_GATEWAY_BIND_HOST"] = "127.0.0.1"
    gateway_env["OPTIMUS_LOCAL_GATEWAY_PORT"] = str(port)
    gateway_env.pop("OPTIMUS_GATEWAY_URL", None)
    gateway_env.pop("OPTIMUS_API_KEY", None)

    if provider == "anthropic":
        gateway_env["ANTHROPIC_API_KEY"] = _gateway_provider_api_key(provider)
        gateway_env.pop("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", None)
    else:
        gateway_env["OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"] = _gateway_provider_api_key(provider)
        gateway_env.pop("ANTHROPIC_API_KEY", None)

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
