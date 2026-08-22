from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from optimus.telemetry.fanout import TelemetryFanout
from optimus.telemetry.jsonl import JsonlTelemetryWriter
from optimus.telemetry.observability import GatewayObservabilityExporter
from optimus.telemetry.redis_sink import RedisTelemetryEventSink


@dataclass(frozen=True)
class StartupConfigurationError(Exception):
    exit_code: int
    user_message: str
    missing_names: tuple[str, ...] = ()


def _missing_env_names(environ: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if not environ.get(name, "").strip())


def _build_gateway_client(*, settings, timeout_seconds):
    if timeout_seconds is None:
        return GatewayClient(settings=settings)
    return GatewayClient(settings=settings, timeout_seconds=timeout_seconds)


def build_agent_runner_for_harness(
    *,
    environ: Mapping[str, str],
    workspace_root: Path,
    model: str | None = None,
    gateway_timeout_seconds: float | None = None,
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
    gateway_client = _build_gateway_client(settings=settings, timeout_seconds=gateway_timeout_seconds)
    state_store = redis_runtime.sync_state_store()
    # Plan 11.5, Task 5: one fanout writes every telemetry event to the local
    # append-only JSONL log and the existing Redis sink unconditionally, and
    # batches redacted events to the Gateway trace-ingress exporter. No
    # Phoenix/OTLP endpoint or LangSmith credential is read or forwarded here --
    # `GatewayObservabilityExporter` only ever talks to the one-key Gateway.
    # Plan 11.25 Task 9: the same fanout is the non-debug ACP_TURN_SETTLEMENT sink
    # (threaded via AgentRunner.event_sink → AcpDuplexAdapter.settlement_sink).
    telemetry_sink = TelemetryFanout(
        jsonl_writer=JsonlTelemetryWriter.for_workspace(resolved_workspace),
        redis_sink=RedisTelemetryEventSink(redis_runtime.telemetry_adapter()),
        gateway_exporter=GatewayObservabilityExporter(settings=settings),
    )

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
    gateway_timeout_seconds: float | None = None,
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
        gateway_timeout_seconds=gateway_timeout_seconds,
    )
    resolved_workspace = Path(workspace_root or ".").resolve()
    settings = OptimusGatewaySettings.from_env(environ)
    gateway_client = _build_gateway_client(settings=settings, timeout_seconds=gateway_timeout_seconds)
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
    client_mcp_runtime = build_client_mcp_runtime(workspace_root=resolved_workspace)
    from optimus.acp.conversation import build_conversation_sanitizer_inputs

    conversation_sanitizer_inputs = build_conversation_sanitizer_inputs(
        environ,
        workspace_root=resolved_workspace,
    )
    return AcpStreamServer(
        dispatcher=dispatcher,
        max_planning_turns=max_planning_turns,
        client_mcp_runtime=client_mcp_runtime,
        conversation_sanitizer_inputs=conversation_sanitizer_inputs,
    )


def build_client_mcp_runtime(*, workspace_root: Path) -> Any:
    """Build one process-lifetime client-MCP runtime (supervisor + disposition seam).

    HTTP/SSE capability flags stay false until adapters and verification exist.
    Runtime capabilities are never inserted into Pydantic dumps or dispatcher payloads.
    """
    import os
    import secrets
    import sys

    import httpx2
    import keyring

    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.acp.trusted_paths import resolve_trusted_operator_roots, resolve_workspace_identity
    from optimus.mcp.client_config import ClientMcpConfigNormalizer
    from optimus.mcp.client_disposition import ClientMcpDisposition, ClientMcpRuntime
    from optimus.mcp.client_sdk import (
        ClientMcpSdkAdapter,
        build_sdk_session_context_factory,
        build_sdk_transport_context_factory,
    )
    from optimus.mcp.client_supervisor import MCPAsyncSupervisor
    from optimus.mcp.client_trust import ClientMcpDurableStore, ClientMcpLeaseAuthority, derive_ipc_auth_key
    from optimus.mcp.local_ipc import PendingClientMcpCandidateEndpoint

    class _ProcessControl:
        def terminate_tree(self, *, seam: str) -> None:
            del seam

    def _hardened_http_client() -> Any:
        return httpx2.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            timeout=httpx2.Timeout(30.0, read=60.0),
        )

    roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    approval_store = KeyringApprovalStore(
        keyring_backend=keyring,
        runtime_root=roots.approval_runtime_root,
        hmac_key=secrets.token_bytes(32) if os.environ.get("OPTIMUS_CLIENT_MCP_EPHEMERAL_HMAC") else None,
    )
    hmac_key = approval_store.hmac_key
    workspace_identity = resolve_workspace_identity(workspace_root)
    durable = ClientMcpDurableStore(keyring_backend=approval_store._keyring, hmac_key=hmac_key)
    supervisor = MCPAsyncSupervisor()
    supervisor.start()
    sdk_adapter = ClientMcpSdkAdapter(
        supervisor=supervisor,
        session_factory=lambda _capability: None,
        http_client_factory=_hardened_http_client,
        stdio_transport_factory=lambda _capability: None,
        process_control=_ProcessControl(),
        transport_context_factory=build_sdk_transport_context_factory(
            http_client_factory=_hardened_http_client,
        ),
        session_context_factory=build_sdk_session_context_factory(),
    )
    candidate_endpoint = PendingClientMcpCandidateEndpoint(authkey=derive_ipc_auth_key(hmac_key))
    disposition = ClientMcpDisposition(
        normalizer=ClientMcpConfigNormalizer(),
        lease_authority=ClientMcpLeaseAuthority(store=durable),
        hmac_key=hmac_key,
        controlled_path=os.environ.get("PATH", ""),
        workspace_digest=workspace_identity.digest,
        candidate_endpoint=candidate_endpoint,
    )
    return ClientMcpRuntime(
        disposition=disposition,
        supervisor=supervisor,
        sdk_adapter=sdk_adapter,
        mcp_http_enabled=False,
        mcp_sse_enabled=False,
        candidate_endpoint=candidate_endpoint,
    )
