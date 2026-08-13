from __future__ import annotations

from dataclasses import dataclass

import pytest

from optimus_gateway.mcp_models import MCPDiscoverRequest


def _profile():
    from optimus_gateway.mcp_profiles import (
        MCPAttributionPolicy,
        MCPHTTPProfile,
        MCPProfile,
        MCPResourceLimits,
    )

    return MCPProfile(
        profile_id="context7",
        revision="rev-1",
        state="PENDING_REGISTRATION",
        transport="http",
        credential_ref="gateway://mcp/context7",
        upstream_allowlist=("fetch", "search", "missing"),
        manifest_hash=None,
        limits=MCPResourceLimits(max_pages=4, max_tools=5, max_descriptor_bytes=4096),
        attribution_policy=MCPAttributionPolicy(),
        transport_config=MCPHTTPProfile(endpoint="https://context7.example/mcp"),
    )


def _tool(name: str, *, annotations: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "name": name,
        "description": f"Untrusted {name} description",
        "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}},
        "annotations": annotations or {},
    }


@dataclass
class FakeTransport:
    pages: dict[str | None, dict[str, object]]
    server_info: dict[str, object]

    def __post_init__(self) -> None:
        self.discover_calls: list[tuple[str, dict[str, object]]] = []
        self.list_calls: list[str | None] = []

    def server_discover(self, *, protocol_version: str, client_meta: dict[str, object]) -> dict[str, object]:
        self.discover_calls.append((protocol_version, client_meta))
        return self.server_info

    def tools_list(self, *, cursor: str | None, protocol_version: str, client_meta: dict[str, object]) -> dict[str, object]:
        self.list_calls.append(cursor)
        return self.pages[cursor]


class FakeConnectionManager:
    def __init__(self, transport: FakeTransport) -> None:
        self.transport = transport
        self.opened: list[str] = []

    def open_for(self, profile):
        self.opened.append(profile.profile_id)
        return self.transport


def _classes():
    from optimus_gateway.mcp_discovery import (
        MCPDiscoveryBroker,
        MCPDiscoveryError,
        MCPDiscoveryPaginator,
    )

    return MCPDiscoveryBroker, MCPDiscoveryError, MCPDiscoveryPaginator


def test_paginator_requires_exact_protocol_floor_tools_capability_and_exhausts_pages():
    _, _, paginator_cls = _classes()
    transport = FakeTransport(
        pages={
            None: {"tools": [_tool("fetch"), _tool("ignored")], "nextCursor": "cursor-1"},
            "cursor-1": {"tools": [_tool("search")], "nextCursor": None},
        },
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )

    result = paginator_cls().collect_tools(transport=transport, profile=_profile())

    assert [descriptor.name for descriptor in result.descriptors] == ["fetch", "search"]
    assert result.unmatched_allowlist == ("missing",)
    assert result.protocol_version == "2026-07-28"
    assert transport.discover_calls[0][0] == "2026-07-28"
    assert transport.list_calls == [None, "cursor-1"]


@pytest.mark.parametrize(
    "server_info",
    [
        {"protocolVersion": "2026-06-18", "capabilities": {"tools": {}}},
        {"protocolVersion": "2026-07-28", "capabilities": {}},
    ],
)
def test_paginator_rejects_unsupported_protocol_or_missing_tools_capability(server_info):
    _, error_cls, paginator_cls = _classes()
    transport = FakeTransport(pages={}, server_info=server_info)

    with pytest.raises(error_cls) as exc_info:
        paginator_cls().collect_tools(transport=transport, profile=_profile())

    assert exc_info.value.disposition in {
        "mcp.protocol_version_unsupported",
        "mcp.tools_capability_missing",
    }


def test_paginator_rejects_cursor_loops_and_never_returns_a_partial_manifest():
    _, error_cls, paginator_cls = _classes()
    transport = FakeTransport(
        pages={None: {"tools": [_tool("fetch")], "nextCursor": "loop"}, "loop": {"tools": [], "nextCursor": "loop"}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )

    with pytest.raises(error_cls, match="cursor"):
        paginator_cls().collect_tools(transport=transport, profile=_profile())


def test_paginator_rejects_malformed_cursor_and_page_budget_exhaustion():
    _, error_cls, paginator_cls = _classes()
    malformed = FakeTransport(
        pages={None: {"tools": [_tool("fetch")], "nextCursor": 7}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    with pytest.raises(error_cls, match="cursor"):
        paginator_cls().collect_tools(transport=malformed, profile=_profile())

    budget = FakeTransport(
        pages={None: {"tools": [_tool("fetch")], "nextCursor": "more"}, "more": {"tools": [], "nextCursor": None}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    with pytest.raises(error_cls, match="limit"):
        paginator_cls(max_pages=1).collect_tools(transport=budget, profile=_profile())


def test_paginator_rejects_invalid_definitions_and_mcp_param_headers():
    _, error_cls, paginator_cls = _classes()
    transport = FakeTransport(
        pages={
            None: {
                "tools": [
                    {"name": "fetch", "inputSchema": []},
                ],
                "nextCursor": None,
            }
        },
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    with pytest.raises(error_cls, match="definition"):
        paginator_cls().collect_tools(transport=transport, profile=_profile())

    transport.pages[None] = {
        "tools": [_tool("fetch", annotations={"x-mcp-header": {"Mcp-Param-Query": "query"}})],
        "nextCursor": None,
    }
    with pytest.raises(error_cls, match="header"):
        paginator_cls().collect_tools(transport=transport, profile=_profile())


def test_paginator_retries_only_transient_discovery_failures_three_times():
    _, error_cls, paginator_cls = _classes()

    class FlakyTransport(FakeTransport):
        def server_discover(self, *, protocol_version: str, client_meta: dict[str, object]) -> dict[str, object]:
            self.discover_calls.append((protocol_version, client_meta))
            raise TimeoutError("temporary")

    transport = FlakyTransport(pages={}, server_info={})
    with pytest.raises(error_cls, match="transient"):
        paginator_cls().collect_tools(transport=transport, profile=_profile())
    assert len(transport.discover_calls) == 3


def test_broker_returns_namespaced_complete_manifest_and_refresh_freshness():
    broker_cls, _, paginator_cls = _classes()
    transport = FakeTransport(
        pages={None: {"tools": [_tool("fetch"), _tool("ignored")], "nextCursor": None}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    manager = FakeConnectionManager(transport)

    from optimus_gateway.mcp_profiles import MCPProfileRegistry

    registry = MCPProfileRegistry((_profile(),))
    broker = broker_cls(paginator=paginator_cls())
    response = broker.discover(
        request=MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1"),
        registry=registry,
        connection_manager=manager,
    )

    assert [descriptor.name for descriptor in response.descriptors] == ["context7.fetch"]
    assert response.freshness == "fresh"
    assert response.manifest_hash == "a" * 64 or len(response.manifest_hash) == 64
    assert manager.opened == ["context7"]

    active = registry.activate_from_startup(
        profile_id="context7", revision="rev-1", manifest_hash=response.manifest_hash
    )
    unchanged = broker.discover(
        request=MCPDiscoverRequest(
            profile_id="context7", profile_revision=active.revision, manifest_hash=active.manifest_hash
        ),
        registry=registry,
        connection_manager=manager,
    )
    assert unchanged.freshness == "unchanged"


def test_broker_marks_active_profile_stale_when_refresh_manifest_drifts():
    broker_cls, _, paginator_cls = _classes()
    transport = FakeTransport(
        pages={None: {"tools": [_tool("fetch")], "nextCursor": None}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    manager = FakeConnectionManager(transport)
    from optimus_gateway.mcp_profiles import MCPProfileRegistry

    registry = MCPProfileRegistry((_profile(),))
    broker = broker_cls(paginator=paginator_cls())
    initial = broker.discover(
        request=MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1"),
        registry=registry,
        connection_manager=manager,
    )
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash=initial.manifest_hash)
    transport.pages[None] = {"tools": [_tool("search")], "nextCursor": None}
    drift = broker.discover(
        request=MCPDiscoverRequest(
            profile_id="context7", profile_revision="rev-1", manifest_hash=initial.manifest_hash
        ),
        registry=registry,
        connection_manager=manager,
    )

    assert drift.freshness == "stale"
    assert drift.disposition == "mcp.discover.drift"
    assert registry.get("context7").state.value == "STALE"


def test_broker_marks_active_profile_stale_after_recoverable_refresh_failure():
    broker_cls, error_cls, paginator_cls = _classes()
    transport = FakeTransport(
        pages={None: {"tools": [_tool("fetch")], "nextCursor": None}},
        server_info={"protocolVersion": "2026-07-28", "capabilities": {"tools": {}}},
    )
    manager = FakeConnectionManager(transport)
    from optimus_gateway.mcp_profiles import MCPProfileRegistry

    registry = MCPProfileRegistry((_profile(),))
    broker = broker_cls(paginator=paginator_cls())
    initial = broker.discover(
        request=MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1"),
        registry=registry,
        connection_manager=manager,
    )
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash=initial.manifest_hash)

    class FailingTransport(FakeTransport):
        def tools_list(self, *, cursor: str | None, protocol_version: str, client_meta: dict[str, object]):
            raise TimeoutError("temporary refresh failure")

    manager.transport = FailingTransport(pages={}, server_info=transport.server_info)
    with pytest.raises(error_cls, match="transient"):
        broker.discover(
            request=MCPDiscoverRequest(
                profile_id="context7", profile_revision="rev-1", manifest_hash=initial.manifest_hash
            ),
            registry=registry,
            connection_manager=manager,
        )
    assert registry.get("context7").state.value == "STALE"


def test_server_discover_accepts_supported_versions_at_the_protocol_floor():
    from optimus_gateway.mcp_discovery import MCPDiscoveryPaginator

    assert MCPDiscoveryPaginator._validate_server_discover(
        {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}}
    ) == "2026-07-28"


@pytest.mark.parametrize(
    "server_info",
    [
        {"supportedVersions": "2026-07-28", "capabilities": {"tools": {}}},
        {"supportedVersions": ["2025-11-25"], "capabilities": {"tools": {}}},
        {
            "protocolVersion": "2026-07-28",
            "supportedVersions": ["2025-11-25"],
            "capabilities": {"tools": {}},
        },
    ],
)
def test_server_discover_rejects_invalid_or_conflicting_version_shapes(server_info):
    from optimus_gateway.mcp_discovery import MCPDiscoveryError, MCPDiscoveryPaginator

    with pytest.raises(MCPDiscoveryError, match="mcp.protocol_version_unsupported"):
        MCPDiscoveryPaginator._validate_server_discover(server_info)
