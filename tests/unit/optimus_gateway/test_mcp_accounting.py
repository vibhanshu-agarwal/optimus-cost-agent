from __future__ import annotations

from decimal import Decimal

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
from optimus_gateway.mcp_usage import InMemoryMCPUsageWriter, MCPUsageRecord

_HASH = "a" * 64


def _request() -> MCPCallRequest:
    return MCPCallRequest(
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        profile_id="context7",
        profile_revision="rev-1",
        manifest_hash=_HASH,
        tool_name="context7.search",
        arguments={"query": "pytest"},
    )


def _profile(*, allow_unattributed_spend: bool, declared_free: bool = False) -> MCPProfile:
    return MCPProfile(
        profile_id="context7",
        revision="rev-1",
        state=MCPProfileState.PENDING_REGISTRATION,
        transport="http",
        credential_ref="gateway://mcp/context7",
        upstream_allowlist=("search",),
        manifest_hash=None,
        limits=MCPResourceLimits(),
        attribution_policy=MCPAttributionPolicy(
            allow_unattributed_spend=allow_unattributed_spend,
            declared_free=declared_free,
        ),
        transport_config=MCPHTTPProfile(endpoint="https://context7.example/mcp"),
    )


class _Transport:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls = 0

    def tools_call(self, **_kwargs: object) -> dict[str, object]:
        self.calls += 1
        return self.result

    def close(self) -> None:
        return None


def _registry(*, allow_unattributed_spend: bool, declared_free: bool = False) -> MCPProfileRegistry:
    registry = MCPProfileRegistry(
        (_profile(allow_unattributed_spend=allow_unattributed_spend, declared_free=declared_free),)
    )
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash=_HASH)
    return registry


def _standard_result() -> dict[str, object]:
    return {"content": [{"type": "text", "text": "untrusted"}], "isError": False}


def test_invocation_persists_a_usage_record_before_releasing_unavailable_result():
    transport = _Transport(_standard_result())
    writer = InMemoryMCPUsageWriter()

    response = MCPInvocationBroker().call(
        request=_request(),
        registry=_registry(allow_unattributed_spend=True),
        connection_manager=MCPConnectionManager(transport_factory=lambda _profile: transport),
        usage_writer=writer,
    )

    assert response.result_type == "complete"
    record = writer.record_for(response.usage.gateway_request_id)
    assert isinstance(record, MCPUsageRecord)
    assert record.attribution == "unavailable"
    assert record.billing_units is None
    assert record.cost_usd is None
    assert record.duration_ms >= 0
    assert record.request_bytes > 0
    assert record.response_bytes > 0


def test_strict_dollar_policy_denies_unavailable_attribution_after_dispatch():
    transport = _Transport(_standard_result())

    with pytest.raises(MCPInvocationError, match="unattributed"):
        MCPInvocationBroker().call(
            request=_request(),
            registry=_registry(allow_unattributed_spend=False),
            connection_manager=MCPConnectionManager(transport_factory=lambda _profile: transport),
            usage_writer=InMemoryMCPUsageWriter(),
        )

    assert transport.calls == 1


def test_explicit_zero_requires_the_revision_bound_free_policy():
    binding = MCPBindingSummary(profile_id="context7", profile_revision="rev-1", manifest_hash=_HASH)
    result = {
        "result_type": "complete",
        "content": [{"type": "text", "text": "untrusted"}],
        "disposition": "mcp.call.complete",
        "binding": binding.model_dump(mode="json"),
        "transport": "http",
        "protocol_version": "2026-07-28",
        "attribution": "explicit_zero",
        "usage": {
            "gateway_request_id": "gw-mcp-zero",
            "attribution": "explicit_zero",
            "billing_units": 0,
            "cost_usd": str(Decimal("0")),
        },
    }
    transport = _Transport(result)

    with pytest.raises(MCPInvocationError, match="free"):
        MCPInvocationBroker().call(
            request=_request(),
            registry=_registry(allow_unattributed_spend=False, declared_free=False),
            connection_manager=MCPConnectionManager(transport_factory=lambda _profile: transport),
            usage_writer=InMemoryMCPUsageWriter(),
        )

    response = MCPInvocationBroker().call(
        request=_request(),
        registry=_registry(allow_unattributed_spend=False, declared_free=True),
        connection_manager=MCPConnectionManager(transport_factory=lambda _profile: transport),
        usage_writer=InMemoryMCPUsageWriter(),
    )
    assert response.attribution == "explicit_zero"
