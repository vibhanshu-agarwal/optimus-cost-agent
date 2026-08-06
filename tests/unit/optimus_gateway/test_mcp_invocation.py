from __future__ import annotations

import pytest

from optimus_gateway.mcp_connections import MCPConnectionManager
from optimus_gateway.mcp_invocation import MCPInvocationBroker, MCPInvocationError
from optimus_gateway.mcp_models import MCPBindingSummary, MCPCallRequest
from optimus_gateway.mcp_profiles import (
    MCPAttributionPolicy,
    MCPHTTPProfile,
    MCPProfile,
    MCPProfileRegistry,
    MCPProfileState,
    MCPResourceLimits,
)

_HASH = "a" * 64


def _profile(*, state: MCPProfileState = MCPProfileState.ACTIVE, max_result_bytes: int = 4096) -> MCPProfile:
    return MCPProfile(
        profile_id="context7",
        revision="rev-1",
        state=state,
        transport="http",
        credential_ref="gateway://mcp/context7",
        upstream_allowlist=("search",),
        manifest_hash=_HASH,
        limits=MCPResourceLimits(max_result_bytes=max_result_bytes),
        attribution_policy=MCPAttributionPolicy(allow_unattributed_spend=True, declared_free=True),
        transport_config=MCPHTTPProfile(endpoint="https://context7.example/mcp"),
    )


def _request(**overrides: object) -> MCPCallRequest:
    values: dict[str, object] = {
        "run_id": "run-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "profile_id": "context7",
        "profile_revision": "rev-1",
        "manifest_hash": _HASH,
        "tool_name": "context7.search",
        "arguments": {"query": "pytest"},
    }
    values.update(overrides)
    return MCPCallRequest(**values)


def _raw_result(*, tool_hash: str = _HASH, content: list[dict[str, object]] | None = None) -> dict[str, object]:
    binding = MCPBindingSummary(
        profile_id="context7", profile_revision="rev-1", manifest_hash=tool_hash
    )
    return {
        "result_type": "complete",
        "content": content or [{"type": "text", "text": "untrusted"}],
        "disposition": "mcp.call.complete",
        "binding": binding.model_dump(mode="json"),
        "transport": "http",
        "protocol_version": "2026-07-28",
        "attribution": "explicit_zero",
        "usage": {
            "gateway_request_id": "gw-mcp-1",
            "attribution": "explicit_zero",
            "billing_units": 0,
            "cost_usd": "0",
        },
    }


class _Transport:
    def __init__(self, result: dict[str, object] | None = None) -> None:
        self.result = result or _raw_result()
        self.calls: list[tuple[str, dict[str, object]]] = []

    def tools_call(self, *, upstream_tool_name: str, arguments: dict[str, object], protocol_version: str):
        self.calls.append((upstream_tool_name, arguments))
        assert protocol_version == "2026-07-28"
        return self.result

    def close(self) -> None:
        return None


class _UsageWriter:
    def __init__(self) -> None:
        self.records: list[object] = []

    def persist(self, record: object) -> None:
        self.records.append(record)


def _admitted() -> tuple[MCPProfileRegistry, MCPConnectionManager, _Transport, _UsageWriter]:
    transport = _Transport()
    registry = MCPProfileRegistry((_profile(state=MCPProfileState.PENDING_REGISTRATION),))
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash=_HASH)
    manager = MCPConnectionManager(transport_factory=lambda _profile: transport)
    writer = _UsageWriter()
    return registry, manager, transport, writer


def test_call_rechecks_gateway_binding_and_forwards_only_derived_name_and_arguments():
    registry, manager, transport, writer = _admitted()

    response = MCPInvocationBroker().call(
        request=_request(), registry=registry, connection_manager=manager, usage_writer=writer
    )

    assert response.result_type == "complete"
    assert transport.calls == [("search", {"query": "pytest"})]
    assert len(writer.records) == 1


def test_standard_upstream_tools_call_result_is_wrapped_before_release():
    registry, manager, _transport, writer = _admitted()
    standard_result = _Transport({"content": [{"type": "text", "text": "untrusted"}], "isError": False})
    manager = MCPConnectionManager(transport_factory=lambda _profile: standard_result)

    response = MCPInvocationBroker().call(
        request=_request(), registry=registry, connection_manager=manager, usage_writer=writer
    )

    assert response.result_type == "complete"
    assert response.binding.manifest_hash == _HASH
    assert response.attribution == "unavailable"


@pytest.mark.parametrize(
    "request_overrides",
    (
        {"profile_revision": "rev-old"},
        {"manifest_hash": "b" * 64},
        {"tool_name": "context7.delete"},
    ),
)
def test_call_denies_binding_or_allowlist_widening_before_transport(request_overrides: dict[str, object]):
    registry, manager, transport, writer = _admitted()
    request = _request(**request_overrides)

    with pytest.raises(MCPInvocationError):
        MCPInvocationBroker().call(
            request=request, registry=registry, connection_manager=manager, usage_writer=writer
        )

    assert transport.calls == []
    assert writer.records == []


@pytest.mark.parametrize("state", (MCPProfileState.STALE, MCPProfileState.DISABLED))
def test_call_denies_stale_and_disabled_profiles(state: MCPProfileState):
    profile = _profile(state=MCPProfileState.PENDING_REGISTRATION)
    registry = MCPProfileRegistry((profile,))
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash=_HASH)
    if state == MCPProfileState.STALE:
        registry.mark_stale(profile_id="context7", revision="rev-1", reason="drift")
    else:
        registry.disable(profile_id="context7")
    transport = _Transport()
    manager = MCPConnectionManager(transport_factory=lambda _profile: transport)

    with pytest.raises(MCPInvocationError):
        MCPInvocationBroker().call(
            request=_request(),
            registry=registry,
            connection_manager=manager,
            usage_writer=_UsageWriter(),
        )
    assert transport.calls == []


def test_persistence_failure_withholds_result_without_redispatch():
    registry, manager, transport, _writer = _admitted()

    class _FailingWriter:
        def persist(self, _record: object) -> None:
            raise RuntimeError("redis credential and secret must not escape")

    with pytest.raises(MCPInvocationError, match="persistence"):
        MCPInvocationBroker().call(
            request=_request(), registry=registry, connection_manager=manager, usage_writer=_FailingWriter()
        )
    assert len(transport.calls) == 1


def test_budget_admission_denies_before_transport():
    registry, manager, transport, _writer = _admitted()

    class _BudgetDeniedWriter:
        def admit(self, **_kwargs: object) -> None:
            raise MCPInvocationError("mcp.call_budget_denied", status=429)

        def persist(self, _record: object) -> None:
            raise AssertionError("budget denial must happen before persistence")

    with pytest.raises(MCPInvocationError, match="budget"):
        MCPInvocationBroker().call(
            request=_request(),
            registry=registry,
            connection_manager=manager,
            usage_writer=_BudgetDeniedWriter(),
        )
    assert transport.calls == []


def test_call_failure_is_not_retried():
    registry, _manager, _transport, writer = _admitted()

    class _FailingTransport(_Transport):
        def tools_call(self, **_kwargs: object):
            self.calls.append(("search", {}))
            raise TimeoutError("upstream timeout")

    failing = _FailingTransport()
    manager = MCPConnectionManager(transport_factory=lambda _profile: failing)

    with pytest.raises(MCPInvocationError):
        MCPInvocationBroker().call(
            request=_request(), registry=registry, connection_manager=manager, usage_writer=writer
        )
    assert len(failing.calls) == 1
