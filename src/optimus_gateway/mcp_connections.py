"""Connection lifetime management separated from MCP profile lifecycle."""

from __future__ import annotations

from collections.abc import Callable

from optimus_gateway.mcp_profiles import MCPProfile
from optimus_gateway.mcp_transports import (
    DockerStdioMCPTransport,
    MCPTransport,
    StreamableHTTPMCPTransport,
)


class MCPConnectionManager:
    def __init__(
        self,
        *,
        transport_factory: Callable[[MCPProfile], MCPTransport] | None = None,
        opener=None,
        credential_resolver=None,
        process_factory=None,
        process_control=None,
        clock=None,
    ) -> None:
        self._transport_factory = transport_factory
        self._opener = opener
        self._credential_resolver = credential_resolver
        self._process_factory = process_factory
        self._process_control = process_control
        self._clock = clock
        self._connections: dict[str, tuple[str, MCPTransport]] = {}

    def open_for(self, profile: MCPProfile) -> MCPTransport:
        current = self._connections.get(profile.profile_id)
        if current is not None and current[0] == profile.revision:
            return current[1]
        if current is not None:
            current[1].close()
        transport = self._make_transport(profile)
        self._connections[profile.profile_id] = (profile.revision, transport)
        return transport

    def close_profile(self, *, profile_id: str, revision: str) -> None:
        current = self._connections.get(profile_id)
        if current is None or current[0] != revision:
            return
        current[1].close()
        del self._connections[profile_id]

    def close_all(self) -> None:
        connections = tuple(self._connections.values())
        self._connections.clear()
        for _revision, transport in connections:
            transport.close()

    def _make_transport(self, profile: MCPProfile) -> MCPTransport:
        if self._transport_factory is not None:
            return self._transport_factory(profile)
        common = {"credential_resolver": self._credential_resolver}
        if self._clock is not None:
            common["clock"] = self._clock
        if profile.transport == "http":
            return StreamableHTTPMCPTransport(profile, opener=self._opener, **common)
        return DockerStdioMCPTransport(
            profile,
            process_factory=self._process_factory or None,
            process_control=self._process_control,
            **common,
        )


__all__ = ["MCPConnectionManager"]
