from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.server import AcpStreamServer
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import RedisAgentStateStore, validate_redis_url
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.guardrails.pre_tool import PreToolGuard

_DEFAULT_MODEL = "glm-5.2"
_DEFAULT_REDIS_URL_HINT = "redis://localhost:6379/0"


@dataclass(frozen=True)
class StartupConfigurationError(Exception):
    exit_code: int
    user_message: str
    missing_names: tuple[str, ...] = ()


def build_configured_server(
    *,
    environ: Mapping[str, str],
    workspace_root: Path | None = None,
    model: str | None = None,
) -> AcpStreamServer:
    missing_gateway = _missing_env_names(environ, ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"))
    if missing_gateway:
        raise StartupConfigurationError(
            exit_code=2,
            user_message="Set OPTIMUS_GATEWAY_URL and OPTIMUS_API_KEY before launching the Optimus ACP agent.",
            missing_names=missing_gateway,
        )

    redis_url = environ.get("OPTIMUS_REDIS_URL", "").strip()
    if not redis_url:
        raise StartupConfigurationError(
            exit_code=2,
            user_message=f"Set OPTIMUS_REDIS_URL={_DEFAULT_REDIS_URL_HINT} before launching the Optimus ACP agent.",
            missing_names=("OPTIMUS_REDIS_URL",),
        )

    try:
        validate_redis_url(redis_url)
    except ValueError as exc:
        raise StartupConfigurationError(exit_code=2, user_message=str(exc)) from exc

    settings = OptimusGatewaySettings.from_env(environ)
    resolved_workspace = Path(workspace_root or ".").resolve()
    guard = PreToolGuard.for_workspace(workspace_root=resolved_workspace, allowed_network_hosts=())
    gateway_client = GatewayClient(settings=settings)
    state_store = RedisAgentStateStore.from_url(redis_url)
    try:
        state_store.ping()
    except ConnectionError as exc:
        raise StartupConfigurationError(
            exit_code=2,
            user_message=f"Redis is not reachable. Start Redis or set OPTIMUS_REDIS_URL={_DEFAULT_REDIS_URL_HINT}.",
        ) from exc

    agent_model = model or environ.get("OPTIMUS_AGENT_MODEL", _DEFAULT_MODEL)
    agent_runner = AgentRunner(
        gateway_client=gateway_client,
        model=agent_model,
        guard=guard,
        state_store=state_store,
    )
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway_client,
        agent_runner=agent_runner,
        pre_tool_guard=guard,
        workspace_root=resolved_workspace,
    )
    return AcpStreamServer(dispatcher=dispatcher)


def _missing_env_names(environ: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if not environ.get(name, "").strip())
