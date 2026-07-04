import pytest

from optimus.guardrails.mcp_trust import MCPServerManifest, MCPToolDescriptor
from optimus.mcp.runtime import MCPRuntimeBlocked, MCPRuntimeTrustContext


def manifest() -> MCPServerManifest:
    return MCPServerManifest(
        server_id="packages",
        command=("uvx", "packages-mcp"),
        launch_args=("--stdio",),
        tools=(
            MCPToolDescriptor(
                name="search",
                description="Search approved package metadata.",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                side_effect_class="read",
            ),
            MCPToolDescriptor(
                name="details",
                description="Read package details.",
                input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
                side_effect_class="read",
            ),
        ),
    )


def test_runtime_context_bootstraps_registry_and_exposes_approved_descriptors(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()

    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )

    descriptors = context.expose_descriptors(server_id="packages", manifest=current)

    assert [descriptor.name for descriptor in descriptors] == ["search"]


def test_runtime_rejects_workspace_bundled_manifest_registration(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    bundled_manifest_path = tmp_path / ".cursor" / "mcp.json"
    bundled_manifest_path.parent.mkdir()
    bundled_manifest_path.write_text('{"mcpServers": {"packages": {"command": "uvx"}}}', encoding="utf-8")

    with pytest.raises(MCPRuntimeBlocked, match="mcp.autoload.cloned_repo_denied"):
        context.register_explicit_manifest(
            manifest(),
            manifest_path=bundled_manifest_path,
            allowed_tools=("search",),
            permission_scope="read_only_metadata",
            approved_by="maintainer",
        )


def test_runtime_rejects_missing_manifest_input(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    with pytest.raises(MCPRuntimeBlocked, match="injection.unscannable_path"):
        context.register_explicit_manifest(
            manifest(),
            manifest_path=tmp_path.parent / "missing" / "packages.mcp.json",
            allowed_tools=("search",),
            permission_scope="read_only_metadata",
            approved_by="maintainer",
        )


def test_runtime_registered_mcp_call_requires_per_call_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )
    runner_called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal runner_called
        runner_called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="classifier.not_configured"):
        context.execute_tool(
            run_id="run-1",
            session_id="session-1",
            manifest=current,
            tool_name="search",
            arguments={"query": "pytest"},
            approval_granted=False,
            runner=runner,
        )

    assert runner_called is False


def test_runtime_registered_mcp_call_runs_after_explicit_per_call_approval(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=workspace, allowed_network_hosts=())
    current = manifest()
    context.register_explicit_manifest(
        current,
        manifest_path=tmp_path / "approved" / "packages.mcp.json",
        allowed_tools=("search",),
        permission_scope="read_only_metadata",
        approved_by="maintainer",
        manifest_text='{"mcpServers": {"packages": {"command": "uvx"}}}',
    )

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"server_id": server_id, "tool_name": tool_name, "arguments": arguments}

    result = context.execute_tool(
        run_id="run-1",
        session_id="session-1",
        manifest=current,
        tool_name="search",
        arguments={"query": "pytest"},
        approval_granted=True,
        runner=runner,
    )

    assert result["server_id"] == "packages"
    assert result["tool_name"] == "search"


def test_runtime_blocks_unregistered_mcp_call_before_runner(tmp_path):
    context = MCPRuntimeTrustContext.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())
    runner_called = False

    def runner(server_id: str, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        nonlocal runner_called
        runner_called = True
        return {"ok": True}

    with pytest.raises(MCPRuntimeBlocked, match="mcp.server_not_registered"):
        context.execute_tool(
            run_id="run-1",
            session_id="session-1",
            manifest=manifest(),
            tool_name="search",
            arguments={"query": "pytest"},
            approval_granted=True,
            runner=runner,
        )

    assert runner_called is False
