import pytest

from optimus.guardrails.mcp_trust import MCPServerManifest, MCPToolDescriptor, MCPTrustRegistry
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.guardrails.prompt_injection import ConfigTrustScanner
from optimus.mcp.runtime import MCPRuntimeBlocked, MCPRuntimeTrustContext
from optimus.runtime.modes import ExecutionMode


class ProbeMCPRunner:
    def __init__(self) -> None:
        self.called = False

    def __call__(self) -> str:
        self.called = True
        return "called"


def test_untrusted_mcp_call_never_reaches_runner(tmp_path):
    runner = ProbeMCPRunner()
    manifest = MCPServerManifest(
        server_id="packages",
        command=("uvx", "packages-mcp"),
        tools=(MCPToolDescriptor(name="search", description="Search metadata.", input_schema={"type": "object"}),),
    )
    guard = PreToolGuard.for_workspace(
        workspace_root=tmp_path,
        allowed_network_hosts=(),
        mcp_trust_registry=MCPTrustRegistry(scanner=ConfigTrustScanner()),
    )

    result = guard.check(
        PreToolRequest(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.MCP,
            action="packages.search",
            approval_granted=True,
            mcp_server_id="packages",
            mcp_tool_name="search",
            mcp_manifest=manifest,
        )
    )
    if result.allowed:
        runner()

    assert result.verdict is PreToolVerdict.HOLD
    assert result.rule_id == "mcp.server_not_registered"
    assert runner.called is False


def manifest() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="packages",
        command=("uvx", "packages-mcp"),
        tools=(MCPToolDescriptor(name="search", description="Search metadata.", input_schema={"type": "object"}),),
    )


def test_runtime_mcp_call_is_blocked_before_runner_side_effect(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="mcp.server_not_registered"):
        context.execute_tool(
            run_id="run-1",
            session_id=None,
            manifest=manifest(),
            tool_name="search",
            arguments={"query": "pytest"},
            execution_mode=ExecutionMode.AGENT,
            approval_granted=True,
            runner=runner,
        )

    assert called is False


def test_runtime_registered_mcp_call_reaches_runner_after_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = MCPServerManifest(
        server_id="packages",
        command=("uvx", "packages-mcp"),
        tools=(MCPToolDescriptor(name="search", description="Search metadata.", input_schema={"type": "object"}),),
    )
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )
    called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal called
        called = True
        return {"server_id": server_id, "tool_name": tool_name}

    result = context.execute_tool(
        run_id="run-1",
        session_id="session-1",
        manifest=current,
        tool_name="search",
        arguments={"query": "pytest"},
        execution_mode=ExecutionMode.AGENT,
        approval_granted=True,
        runner=runner,
    )

    assert called is True
    assert result["server_id"] == "packages"
    assert result["tool_name"] == "search"
