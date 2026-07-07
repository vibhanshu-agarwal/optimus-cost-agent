from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optimus.agent.state_store import RedisAgentStateStore, validate_redis_url

DEFAULT_REDIS_URL_HINT = "redis://127.0.0.1:6379/0"
_REDIS_TS_PROBE_KEY = "optimus:preflight:timeseries-probe"


@dataclass(frozen=True)
class PreflightFailure(Exception):
    exit_code: int
    user_message: str

    def __str__(self) -> str:
        return self.user_message


def run_preflight(
    environ: Mapping[str, str] | None = None,
    *,
    workspace_root: Path | None = None,
    strict: bool = False,
    require_timeseries: bool = False,
) -> str:
    """Validate operator environment. Returns the validated Redis URL on success."""
    env = os.environ if environ is None else environ
    _require_gateway_credentials(env)
    redis_url = _require_redis_url(env)
    store = RedisAgentStateStore.from_url(redis_url)
    _require_redis_ping(store)
    if require_timeseries:
        _require_redis_timeseries(store)
    if strict:
        _require_gateway_auth(env)
    if workspace_root is not None:
        _require_workspace_root(workspace_root)
    return redis_url


def _require_gateway_credentials(environ: Mapping[str, str]) -> None:
    missing = tuple(name for name in ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY") if not environ.get(name, "").strip())
    if missing:
        raise PreflightFailure(
            exit_code=2,
            user_message="Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.",
        )


def _require_redis_url(environ: Mapping[str, str]) -> str:
    redis_url = environ.get("OPTIMUS_REDIS_URL", "").strip()
    if not redis_url:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                f"Set OPTIMUS_REDIS_URL={DEFAULT_REDIS_URL_HINT} "
                "(start one with: docker run --rm -d -p 6379:6379 redis:8)."
            ),
        )
    try:
        return validate_redis_url(redis_url)
    except ValueError as exc:
        raise PreflightFailure(exit_code=2, user_message=str(exc)) from exc


def _require_redis_ping(store: RedisAgentStateStore) -> None:
    try:
        store.ping()
    except ConnectionError as exc:
        raise PreflightFailure(
            exit_code=2,
            user_message=f"Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL. ({exc})",
        ) from exc


def _require_redis_timeseries(store: RedisAgentStateStore) -> None:
    client = store._client
    try:
        client.execute_command("TS.ADD", _REDIS_TS_PROBE_KEY, "*", 1)
        client.delete(_REDIS_TS_PROBE_KEY)
    except Exception as exc:
        raise PreflightFailure(
            exit_code=2,
            user_message=(
                "Redis lacks TimeSeries support. Use redis:8 or redis/redis-stack-server "
                f"(LLD section 10 requires TS.* commands). ({exc})"
            ),
        ) from exc


def _require_gateway_auth(environ: Mapping[str, str]) -> None:
    from optimus.config.gateway import OptimusGatewaySettings
    from optimus.gateway.client import GatewayClient

    settings = OptimusGatewaySettings.from_env(environ)
    client = GatewayClient(settings=settings)
    try:
        client.create_response(model="glm-5.2", input_text="preflight", metadata={"purpose": "preflight_auth_probe"})
    except Exception as exc:
        message = str(exc)
        if "401" in message or "403" in message:
            raise PreflightFailure(exit_code=2, user_message="OPTIMUS_API_KEY was rejected by the gateway.") from exc
        gateway_url = environ.get("OPTIMUS_GATEWAY_URL", "")
        raise PreflightFailure(
            exit_code=2,
            user_message=f"Gateway is not reachable at {gateway_url}. ({exc})",
        ) from exc


def _require_workspace_root(workspace_root: Path) -> None:
    resolved = workspace_root.resolve()
    if not resolved.is_dir():
        raise PreflightFailure(exit_code=2, user_message=f"Workspace root is not a directory: {resolved}")
    if not os.access(resolved, os.W_OK):
        raise PreflightFailure(exit_code=2, user_message=f"Workspace root is not writable: {resolved}")
