from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from optimus.acp.debug_trace import log_planning_replan_event, log_workspace_context_result
from optimus.acp.dispatcher import JsonRpcDispatcher
from optimus.acp.server import AcpStreamServer
from optimus.acp.spec import resolve_max_planning_turns
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
    """
    Builds and initializes an AgentRunner instance configured for use with a harness.

    This function sets up the necessary runtime environment by performing preflight
    checks, initializing required runtime components such as Redis, and resolving
    the provided workspace settings and model. It ensures that all dependencies
    and configurations are in place before returning the configured AgentRunner.

    :param environ: A mapping of environment variables as key-value pairs used for
        configuration and runtime behavior.
    :type environ: Mapping[str, str]
    :param workspace_root: The root directory path where the workspace resides. It
        is used for resolving workspace configurations and state.
    :type workspace_root: Path
    :param model: Optional argument to specify the model to be used by the AgentRunner.
        Defaults to None, which means the model will be resolved from the environment.
    :type model: str | None
    :return: A fully configured AgentRunner instance ready for execution.
    :rtype: AgentRunner
    :raises StartupConfigurationError: Raised when a preflight failure occurs, such
        as missing or misconfigured runtime dependencies.
    """
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
        planning_progress_observer=log_planning_replan_event,
    )


def build_configured_server(
    *,
    environ: Mapping[str, str],
    workspace_root: Path | None = None,
    model: str | None = None,
) -> AcpStreamServer:
    """
    Builds and configures an `AcpStreamServer` instance with the specified environment
    settings, workspace, and model. This function sets up the necessary components such as
    the agent runner, gateway client, and dispatcher required for the server.

    :param environ: A mapping of environment variables to be used for configuration.
    :type environ: Mapping[str, str]

    :param workspace_root: The root path of the workspace. If not provided, defaults
        to the current directory.
    :type workspace_root: Path | None

    :param model: The name of the model to be used in the configuration. If not
        specified, defaults to None.
    :type model: str | None

    :return: A fully configured instance of `AcpStreamServer`.
    :rtype: AcpStreamServer
    """
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
    # Plan 9.96, Task 5 Step 2: resolved once here from the (already
    # authorized/sanitized) agent environ passed into this function, rather
    # than read from os.environ per-request deep inside AcpDuplexAdapter.
    max_planning_turns = resolve_max_planning_turns(environ)
    return AcpStreamServer(dispatcher=dispatcher, max_planning_turns=max_planning_turns)
