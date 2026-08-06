from __future__ import annotations

from optimus_gateway.mcp_connections import MCPConnectionManager
from optimus_gateway.mcp_profiles import (
    MCPAttributionPolicy,
    MCPHTTPProfile,
    MCPProfile,
    MCPProfileState,
    MCPResourceLimits,
)


def _profile(revision: str = "rev-1") -> MCPProfile:
    return MCPProfile(
        profile_id="context7",
        revision=revision,
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="http",
        credential_ref="context7-token",
        upstream_allowlist=("fetch",),
        manifest_hash=None,
        limits=MCPResourceLimits(),
        attribution_policy=MCPAttributionPolicy(),
        transport_config=MCPHTTPProfile("https://mcp.example/tools"),
    )


class _Transport:
    def __init__(self, label: str) -> None:
        self.label = label
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


def test_connection_manager_reuses_by_profile_revision_and_closes_old_revision_without_activation() -> None:
    created: list[tuple[MCPProfile, _Transport]] = []

    def factory(profile: MCPProfile) -> _Transport:
        transport = _Transport(profile.revision)
        created.append((profile, transport))
        return transport

    manager = MCPConnectionManager(transport_factory=factory)
    first = manager.open_for(_profile())
    assert manager.open_for(_profile()) is first
    second = manager.open_for(_profile("rev-2"))

    assert second is not first
    assert first.closed == 1
    assert [profile.state for profile, _transport in created] == [MCPProfileState.PENDING_REGISTRATION] * 2

    manager.close_profile(profile_id="context7", revision="rev-2")
    assert second.closed == 1
    manager.close_profile(profile_id="context7", revision="rev-2")
    assert second.closed == 1


def test_connection_manager_close_all_closes_each_transport_once() -> None:
    transports: list[_Transport] = []
    manager = MCPConnectionManager(
        transport_factory=lambda profile: transports.append(_Transport(profile.revision)) or transports[-1]
    )
    manager.open_for(_profile("rev-1"))
    manager.open_for(_profile("rev-2"))
    manager.close_all()
    assert [transport.closed for transport in transports] == [1, 1]
