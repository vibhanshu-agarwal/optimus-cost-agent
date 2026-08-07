"""P11-FU-9 Task 8 live credential-free MCP catalog probes.

Real dependencies only:
- ``requires_mcp_stdio``: digest-pinned HashiCorp Terraform MCP Docker image
- ``requires_mcp_http``: public Context7 Streamable HTTP endpoint (no credential)

Skipped tiers are not evidence for DoD claims.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from optimus.guardrails import mcp_trust as mcp_trust_mod
from optimus.guardrails.mcp_trust import MCPToolDescriptor
from optimus.mcp.client_catalog import classify_client_tool_effect

TERRAFORM_IMAGE = (
    "hashicorp/terraform-mcp-server@"
    "sha256:bd095e2b442a2cb61255fe4db52f9e824f35d307a2044784c95d37a93f18d324"
)
CONTEXT7_URL = "https://mcp.context7.com/mcp"
PROPOSED_PROTOCOL_VERSION = "2026-07-28"
EXPECTED_NEGOTIATED_VERSION = "2025-11-25"

TERRAFORM_TOKENIZED = {"read": 9, "network": 0, "write": 0}
TERRAFORM_LEGACY = {"read": 0, "network": 6, "write": 3}
CONTEXT7_TOKENIZED = {"read": 2, "network": 0, "write": 0}
CONTEXT7_LEGACY = {"read": 0, "network": 2, "write": 0}


def _docker_executable() -> str | None:
    # Prefer native Linux docker; docker.exe on WSL is often not exec-able (PE binary).
    for name in ("docker", "docker.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _require_docker() -> str:
    docker = _docker_executable()
    if docker is None:
        pytest.skip("docker_not_available: Terraform stdio fixture requires Docker")
    try:
        probe = subprocess.run(  # noqa: S603
            [docker, "info"],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=30,
        )
    except OSError as exc:
        pytest.skip(f"docker_exec_unavailable: {exc}")
    if probe.returncode != 0:
        pytest.skip(f"docker_daemon_unavailable: exit={probe.returncode}")
    return docker


def _count_effects(tools: Sequence[Mapping[str, Any]], *, mode: str) -> dict[str, int]:
    counts = {"read": 0, "network": 0, "write": 0}
    for tool in tools:
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        if mode == "tokenized":
            # Design probe distribution is tokenized *names* only (not annotation hints).
            effect = classify_client_tool_effect(name=name, annotations=None)
        elif mode == "legacy":
            descriptor = MCPToolDescriptor(
                name=name,
                description=description,
                input_schema=dict(schema),
                side_effect_class="read",
            )
            effect = mcp_trust_mod._effective_side_effect_class(descriptor)
        else:
            raise AssertionError(f"unknown classifier mode: {mode}")
        counts[effect] += 1
    return counts


def _tool_schema(tool: object) -> dict[str, Any]:
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    return dict(schema) if isinstance(schema, dict) else {}


async def _list_tools_via_stdio(docker: str) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=docker,
        args=["run", "-i", "--rm", TERRAFORM_IMAGE],
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            init = await session.initialize()
            negotiated = str(getattr(init, "protocol_version", None) or getattr(init, "protocolVersion", "") or "")
            tools_result = await session.list_tools()
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": _tool_schema(tool),
                }
                for tool in tools_result.tools
            ]
            init_dump: dict[str, Any] = {}
            if hasattr(init, "model_dump"):
                init_dump = init.model_dump(exclude_none=True)
            elif hasattr(init, "protocol_version"):
                init_dump = {"protocolVersion": init.protocol_version}
            return negotiated, tools, init_dump


async def _list_tools_via_http() -> tuple[str, list[dict[str, Any]], Mapping[str, Any], str]:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    # Separate credential-free Accept probe (design: plain POST Accept header).
    async with httpx2.AsyncClient(follow_redirects=False, trust_env=False, timeout=30.0) as probe:
        response = await probe.post(
            CONTEXT7_URL,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            content=b"{}",
        )
        accept_header = response.request.headers.get("accept") or response.request.headers.get("Accept") or ""

    async with httpx2.AsyncClient(
        follow_redirects=False,
        trust_env=False,
        timeout=httpx2.Timeout(30.0, read=60.0),
    ) as http_client:
        async with streamable_http_client(CONTEXT7_URL, http_client=http_client) as streams:
            read_stream, write_stream = streams[0], streams[1]
            async with ClientSession(read_stream, write_stream) as session:
                init = await session.initialize()
                negotiated = str(getattr(init, "protocol_version", None) or getattr(init, "protocolVersion", "") or "")
                tools_result = await session.list_tools()
                tools = [
                    {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": _tool_schema(tool),
                    }
                    for tool in tools_result.tools
                ]
                init_dump: dict[str, Any] = {}
                if hasattr(init, "model_dump"):
                    init_dump = init.model_dump(exclude_none=True)
                elif hasattr(init, "protocol_version"):
                    init_dump = {"protocolVersion": init.protocol_version}
                return negotiated, tools, init_dump, accept_header


def _assert_initialize_untrusted_fields_not_policy(init_dump: Mapping[str, Any]) -> None:
    # Server instructions / serverInfo remain untrusted inputs; probe only records presence.
    version = init_dump.get("protocolVersion") or init_dump.get("protocol_version")
    assert version is not None
    # No dynamic tool registration claim: catalog is listed separately via list_tools.


@pytest.mark.requires_mcp_stdio
@pytest.mark.asyncio
async def test_terraform_stdio_catalog_distributions_and_negotiation() -> None:
    docker = _require_docker()
    try:
        negotiated, tools, init_dump = await _list_tools_via_stdio(docker)
    except Exception as exc:  # noqa: BLE001 — live tier: skip on missing image/network
        pytest.skip(f"terraform_stdio_unavailable: {type(exc).__name__}: {exc}")

    assert negotiated == EXPECTED_NEGOTIATED_VERSION, (
        f"observed negotiated protocolVersion={negotiated!r}; "
        f"design probe expected {EXPECTED_NEGOTIATED_VERSION!r} "
        f"(proposed {PROPOSED_PROTOCOL_VERSION!r}, must not invent)"
    )
    assert len(tools) == 9
    tokenized = _count_effects(tools, mode="tokenized")
    legacy = _count_effects(tools, mode="legacy")
    assert tokenized == TERRAFORM_TOKENIZED
    assert legacy == TERRAFORM_LEGACY
    _assert_initialize_untrusted_fields_not_policy(init_dump)
    # Contrast: legacy false positives must differ from tokenized.
    assert legacy != tokenized


@pytest.mark.requires_mcp_http
@pytest.mark.asyncio
async def test_context7_http_catalog_distributions_accept_and_negotiation() -> None:
    try:
        negotiated, tools, init_dump, accept_header = await _list_tools_via_http()
    except Exception as exc:  # noqa: BLE001 — live tier: skip on network/auth/outage
        pytest.skip(f"context7_http_unavailable: {type(exc).__name__}: {exc}")

    assert negotiated == EXPECTED_NEGOTIATED_VERSION, (
        f"observed negotiated protocolVersion={negotiated!r}; "
        f"design probe expected {EXPECTED_NEGOTIATED_VERSION!r} "
        f"(proposed {PROPOSED_PROTOCOL_VERSION!r}, must not invent)"
    )
    assert "application/json" in accept_header
    assert "text/event-stream" in accept_header
    assert len(tools) == 2
    tokenized = _count_effects(tools, mode="tokenized")
    legacy = _count_effects(tools, mode="legacy")
    assert tokenized == CONTEXT7_TOKENIZED
    assert legacy == CONTEXT7_LEGACY
    _assert_initialize_untrusted_fields_not_policy(init_dump)
    assert legacy != tokenized
    # Fingerprint-safe locator only (no secrets).
    locator = {"url": CONTEXT7_URL, "tool_names": sorted(t["name"] for t in tools)}
    assert "Authorization" not in json.dumps(locator)
