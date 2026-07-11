from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optimus.acp.debug_trace import log_workspace_context_result
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.server import AcpStreamServer
from optimus.agent.defaults import resolve_agent_model
from optimus.agent.runner import AgentRunner
from optimus.config.gateway import OptimusGatewaySettings
from optimus.gateway.client import GatewayClient
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.redis.runtime import RedisRuntime
from optimus.telemetry.redis_sink import RedisTelemetryEventSink

_DEFAULT_REDIS_URL_HINT = "redis://localhost:6379/0"


@dataclass(frozen=True)
class StartupConfigurationError(Exception):
    exit_code: int
    user_message: str
    missing_names: tuple[str, ...] = ()


def _missing_env_names(environ: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if not environ.get(name, "").strip())


def build_agent_runner_for_harness(
    *,
    environ: Mapping[str, str],
    workspace_root: Path,
    model: str | None = None,
) -> AgentRunner:
    from optimus.acp.preflight import PreflightFailure, run_preflight

    try:
        redis_url = run_preflight(environ, workspace_root=workspace_root, require_timeseries=True)
    except PreflightFailure as exc:
        raise StartupConfigurationError(exit_code=exc.exit_code, user_message=exc.user_message) from exc
    redis_runtime = RedisRuntime.from_url(redis_url)
    settings = OptimusGatewaySettings.from_env(environ)
    resolved_workspace = workspace_root.resolve()
    guard = PreToolGuard.for_workspace(workspace_root=resolved_workspace, allowed_network_hosts=())
    gateway_client = GatewayClient(settings=settings)
    state_store = redis_runtime.sync_state_store()
    telemetry_sink = RedisTelemetryEventSink(redis_runtime.telemetry_adapter())

    agent_model = resolve_agent_model(environ, cli_model=model)
    return AgentRunner(
        gateway_client=gateway_client,
        model=agent_model,
        guard=guard,
        state_store=state_store,
        event_sink=telemetry_sink,
        workspace_context_observer=log_workspace_context_result,
    )


def build_configured_server(
    *,
    environ: Mapping[str, str],
    workspace_root: Path | None = None,
    model: str | None = None,
) -> AcpStreamServer:
    agent_runner = build_agent_runner_for_harness(
        environ=environ,
        workspace_root=Path(workspace_root or "."),
        model=model,
    )
    resolved_workspace = Path(workspace_root or ".").resolve()
    settings = OptimusGatewaySettings.from_env(environ)
    gateway_client = GatewayClient(settings=settings)
    guard = PreToolGuard.for_workspace(workspace_root=resolved_workspace, allowed_network_hosts=())
    dispatcher = JsonRpcDispatcher(
        gateway_client=gateway_client,
        agent_runner=agent_runner,
        pre_tool_guard=guard,
        workspace_root=resolved_workspace,
    )
    return AcpStreamServer(dispatcher=dispatcher)
