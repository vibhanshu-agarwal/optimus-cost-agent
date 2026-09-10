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
    def __init__(self, client: FakeAsyncRedisClient, *, close_error: BaseException | None = None) -> None:
        self.client = client
        self.closed = 0
        self.submissions = 0
        self.close_error = close_error

    def ping(self) -> None:
        if self.client.ping_error is not None:
            raise ConnectionError(str(self.client.ping_error))

    def run_sync(self, operation, *, timeout=None):
        import asyncio

        self.submissions += 1
        return asyncio.run(operation())

    def close(self, *, timeout=None):
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error
        return None


def _patch_runtime(monkeypatch, client: FakeAsyncRedisClient, **kwargs) -> FakeRedisRuntime:
    runtime = FakeRedisRuntime(client, **kwargs)
    monkeypatch.setattr("optimus.acp.preflight.RedisRuntime.from_url", lambda url: runtime)
    return runtime


def test_preflight_requires_gateway_credentials():
    with pytest.raises(PreflightFailure) as exc_info:
        run_preflight({"OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0"})

    assert exc_info.value.exit_code == 2
    assert "OPTIMUS_GATEWAY_URL" in exc_info.value.user_message


def test_preflight_requires_redis_url(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient())
    with pytest.raises(PreflightFailure, match="OPTIMUS_REDIS_URL"):
        run_preflight({"OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai", "OPTIMUS_API_KEY": "opt-test"})  # pragma: allowlist secret - synthetic test fixture, not a real credential


def test_preflight_rejects_password_redis_url():
    with pytest.raises(PreflightFailure, match="must not contain username or password"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
                "OPTIMUS_REDIS_URL": "redis://user:secret@127.0.0.1:6379/0",  # pragma: allowlist secret - synthetic test fixture, not a real credential
            }
        )


def test_preflight_reports_unreachable_redis(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient(ping_error=ConnectionError("down")))
    with pytest.raises(PreflightFailure, match="Redis is not reachable"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            }
        )


def test_preflight_requires_timeseries_when_requested(monkeypatch):
    _patch_runtime(monkeypatch, FakeAsyncRedisClient(timeseries=False))
    with pytest.raises(PreflightFailure, match="TimeSeries"):
        run_preflight(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
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
            "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
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
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
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
                "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
                "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
                "OPTIMUS_PRODUCTION_MODE": "false",
            },
            strict=True,
        )


# --- Seam 2, checkpoint B: owner-aware probe and close --------------------------------


_ENV = {
    "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
    "OPTIMUS_API_KEY": "opt-test",  # pragma: allowlist secret - synthetic test fixture, not a real credential
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}


def test_the_timeseries_probe_runs_through_the_runtime_owner_not_the_shared_loop(monkeypatch):
    """MUTATION: the probe runs a raw client operation on a second owner."""
    from optimus.redis import async_bridge

    client = FakeAsyncRedisClient()
    runtime = _patch_runtime(monkeypatch, client)

    assert run_preflight(_ENV, require_timeseries=True) == _ENV["OPTIMUS_REDIS_URL"]
    assert runtime.submissions == 1
    assert client.deleted == ["optimus:preflight:timeseries-probe"]
    assert runtime.closed == 1
    assert async_bridge._shared_tool_owner is None


def test_a_probe_runtime_that_cannot_shut_down_fails_preflight_on_the_success_path(monkeypatch):
    from optimus.redis.runtime import RedisRuntimeShutdownIncomplete

    runtime = _patch_runtime(
        monkeypatch, FakeAsyncRedisClient(), close_error=RedisRuntimeShutdownIncomplete("still closing")
    )
    with pytest.raises(PreflightFailure, match="did not shut down") as exc_info:
        run_preflight(_ENV)
    assert exc_info.value.exit_code == 2
    assert runtime.closed == 1


def test_a_close_failure_never_replaces_the_preflight_failure_it_follows(monkeypatch):
    runtime = _patch_runtime(
        monkeypatch,
        FakeAsyncRedisClient(timeseries=False),
        close_error=RuntimeError("close exploded"),
    )
    with pytest.raises(PreflightFailure, match="TimeSeries") as exc_info:
        run_preflight(_ENV, require_timeseries=True)
    assert runtime.closed == 1
    assert any("close exploded" in note for note in getattr(exc_info.value, "__notes__", []))


def test_collect_preflight_checks_closes_the_probe_runtime_on_every_path(monkeypatch):
    from optimus.acp.preflight import collect_preflight_checks

    runtime = _patch_runtime(monkeypatch, FakeAsyncRedisClient(ping_error=ConnectionError("down")))
    checks = collect_preflight_checks(_ENV, require_timeseries=True)
    assert [check.name for check in checks if not check.passed] == ["redis connectivity"]
    assert runtime.closed == 1


def test_collect_preflight_checks_reports_a_probe_runtime_that_cannot_shut_down(monkeypatch):
    from optimus.acp.preflight import collect_preflight_checks
    from optimus.redis.runtime import RedisRuntimeShutdownIncomplete

    _patch_runtime(monkeypatch, FakeAsyncRedisClient(), close_error=RedisRuntimeShutdownIncomplete("still closing"))
    checks = collect_preflight_checks(_ENV, require_timeseries=True)
    names = {check.name: check for check in checks}
    assert names["redis connectivity"].passed and names["redis timeseries"].passed
    assert not names["redis probe shutdown"].passed
    assert "did not shut down" in names["redis probe shutdown"].detail
