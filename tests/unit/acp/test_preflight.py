from __future__ import annotations

import pytest

from optimus.acp.preflight import PreflightFailure, run_preflight


class FakeAsyncRedisClient:
    def __init__(self, *, ping_error: Exception | None = None, timeseries: bool = True) -> None:
        self.ping_error = ping_error
        self.timeseries = timeseries
        self.deleted: list[str] = []

    async def ping(self):
        if self.ping_error is not None:
            raise self.ping_error
        return True

    async def execute_command(self, command: str, *args):
        if command == "TS.ADD" and not self.timeseries:
            raise RuntimeError("unknown command TS.ADD")
        return 1

    async def delete(self, key: str):
        self.deleted.append(key)
        return 1

    async def aclose(self):
        return None


class FakeRedisRuntime:
    def __init__(self, client: FakeAsyncRedisClient) -> None:
        self.client = client
        self.closed = False

    def ping(self) -> None:
        if self.client.ping_error is not None:
            raise ConnectionError(str(self.client.ping_error))

    def close(self) -> None:
        self.closed = True


def _patch_runtime(monkeypatch, client: FakeAsyncRedisClient) -> None:
    monkeypatch.setattr(
        "optimus.acp.preflight.RedisRuntime.from_url",
        lambda url: FakeRedisRuntime(client),
    )


def test_preflight_requires_gateway_credentials():
    with pytest.raises(PreflightFailure) as exc_info:
        run_preflight({"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"})

    assert exc_info.value.exit_code == 2
    assert "OPTIMUS_GATEWAY_URL" in exc_info.value.user_message


def test_preflight_requires_redis_url(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    with pytest.raises(PreflightFailure, match="OPTIMUS_REDIS_URL"):
        run_preflight({"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_API_KEY": "opt-test"})


def test_preflight_rejects_password_redis_url():
    with pytest.raises(PreflightFailure, match="must not contain username or password"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://user:secret@127.0.0.1:6379/0",
            }
        )


def test_preflight_reports_unreachable_redis(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient(ping_error=ConnectionError("down")))
    with pytest.raises(PreflightFailure, match="Redis is not reachable"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            }
        )


def test_preflight_requires_timeseries_when_requested(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient(timeseries=False))
    with pytest.raises(PreflightFailure, match="TimeSeries"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            },
            require_timeseries=True,
        )


def test_preflight_strict_gateway_probe_uses_configured_agent_model(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    captured: dict[str, str] = {}

    class FakeGatewayClient:
        def __init__(self, *, settings):
            self.settings = settings

        def create_response(self, *, model: str, input_text: str, metadata=None):
            captured["model"] = model
            return object()

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", FakeGatewayClient)

    run_preflight(
        {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "opt-test",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_PRODUCTION_MODE": "false",
            "OPTIMUS_AGENT_MODEL": "claude-haiku",
        },
        strict=True,
    )

    assert captured["model"] == "claude-haiku"


def test_preflight_strict_gateway_probe_reports_rejected_request_for_http_4xx(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    from optimus.gateway.errors import GatewayHttpError

    class FakeGatewayClient:
        def __init__(self, *, settings):
            self.settings = settings

        def create_response(self, *, model: str, input_text: str, metadata=None):
            raise GatewayHttpError(400, "unsupported gateway model: glm-5.2")

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", FakeGatewayClient)

    with pytest.raises(PreflightFailure, match="rejected the auth probe request") as exc_info:
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
                "OPTIMUS_PRODUCTION_MODE": "false",
                "OPTIMUS_AGENT_MODEL": "glm-5.2",
            },
            strict=True,
        )

    assert "Gateway is not reachable" not in exc_info.value.user_message


def test_preflight_strict_gateway_probe_reports_unreachable_for_network_failure(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    from optimus.gateway.errors import GatewayHttpError

    class FakeGatewayClient:
        def __init__(self, *, settings):
            self.settings = settings

        def create_response(self, *, model: str, input_text: str, metadata=None):
            raise GatewayHttpError(0, "Connection refused")

    monkeypatch.setattr("optimus.gateway.client.GatewayClient", FakeGatewayClient)

    with pytest.raises(PreflightFailure, match="Gateway is not reachable"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
                "OPTIMUS_API_KEY": "opt-test",
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
                "OPTIMUS_PRODUCTION_MODE": "false",
            },
            strict=True,
        )
