from optimus.guardrails.mcp_trust import MCPServerManifest, MCPToolDescriptor, MCPTrustRegistry
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.guardrails.prompt_injection import ConfigTrustScanner
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
