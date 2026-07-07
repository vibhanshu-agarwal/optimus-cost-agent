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
