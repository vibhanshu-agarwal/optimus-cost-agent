from decimal import Decimal

import pytest
from pydantic import ValidationError

from optimus.gateway.mcp_models import (
    MCPBindingSummary,
    MCPCallRequest,
    MCPCallResponse,
    MCPContent,
    MCPDiscoverRequest,
    MCPDiscoverResponse,
    MCPToolDescriptor,
    MCPUsageRecordSummary,
    canonical_manifest_bytes,
    compute_manifest_hash,
    namespace_tool_name,
    parse_namespaced_tool_name,
)


def descriptor(name: str) -> MCPToolDescriptor:
    return MCPToolDescriptor(
        name=name,
        description="Read untrusted documentation metadata.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        annotations={"readOnlyHint": True},
        side_effect_class="read",
    )


def discover_response(*, descriptors: tuple[MCPToolDescriptor, ...]) -> MCPDiscoverResponse:
    return MCPDiscoverResponse(
        profile_id="context7",
        profile_revision="rev-1",
        transport="http",
        protocol_version="2026-07-28",
        descriptors=descriptors,
        unmatched_allowlist=("missing", "also-missing"),
        manifest_hash="a" * 64,
        freshness="fresh",
        disposition="mcp.discover.complete",
    )


def test_discover_request_supports_registration_and_validated_refresh_binding():
    registration = MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1")
    refresh = MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1", manifest_hash="a" * 64)

    assert registration.manifest_hash is None
    assert refresh.manifest_hash == "a" * 64

    with pytest.raises(ValidationError):
        MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1", manifest_hash="")


def test_call_request_requires_profile_namespaced_tool_and_arguments_only():
    request = MCPCallRequest(
        run_id="run-1",
        session_id="session-1",
        request_id="request-1",
        profile_id="context7",
        profile_revision="rev-1",
        manifest_hash="a" * 64,
        tool_name="context7.search",
        arguments={"query": "pytest"},
    )

    assert request.tool_name == "context7.search"
    assert request.arguments == {"query": "pytest"}

    with pytest.raises(ValidationError):
        MCPCallRequest(
            run_id="run-1",
            session_id=None,
            request_id="request-1",
            profile_id="context7",
            profile_revision="rev-1",
            manifest_hash="a" * 64,
            tool_name="search",
            arguments={},
        )

    with pytest.raises(ValidationError):
        MCPCallRequest(
            run_id="run-1",
            session_id=None,
            request_id="request-1",
            profile_id="context7",
            profile_revision="rev-1",
            manifest_hash="a" * 64,
            tool_name="context7.search",
            arguments={},
            endpoint="https://secret.example",
        )


def test_call_request_rejects_non_json_argument_values():
    with pytest.raises(ValidationError, match="finite"):
        MCPCallRequest(
            run_id="run-1",
            session_id=None,
            request_id="request-1",
            profile_id="context7",
            profile_revision="rev-1",
            manifest_hash="a" * 64,
            tool_name="context7.search",
            arguments={"limit": float("inf")},
        )

    with pytest.raises(ValidationError, match="JSON"):
        MCPCallRequest(
            run_id="run-1",
            session_id=None,
            request_id="request-1",
            profile_id="context7",
            profile_revision="rev-1",
            manifest_hash="a" * 64,
            tool_name="context7.search",
            arguments={"bad": object()},
        )


def test_namespace_helpers_round_trip_and_reject_wrong_profile():
    namespaced = namespace_tool_name(profile_id="context7", tool_name="search")

    assert namespaced == "context7.search"
    assert parse_namespaced_tool_name(namespaced) == ("context7", "search")
    assert parse_namespaced_tool_name("context7.search.v2", expected_profile_id="context7") == (
        "context7",
        "search.v2",
    )

    with pytest.raises(ValueError, match="profile_id"):
        parse_namespaced_tool_name("other.search", expected_profile_id="context7")
    with pytest.raises(ValueError, match="namespaced"):
        parse_namespaced_tool_name("search")


def test_content_model_accepts_only_untrusted_tools_content_and_rejects_images_audio():
    assert MCPContent(type="text", text="untrusted server text").text == "untrusted server text"
    assert MCPContent(type="structured", data={"value": 1}).data == {"value": 1}
    assert MCPContent(type="resource_link", uri="https://docs.example/item", name="item").uri == "https://docs.example/item"
    assert MCPContent(
        type="embedded_resource",
        resource={"uri": "urn:doc:1", "mime_type": "text/plain", "text": "inert"},
    ).resource["uri"] == "urn:doc:1"

    with pytest.raises(ValidationError):
        MCPContent(type="image", data={"bytes": "not-released"})
    with pytest.raises(ValidationError):
        MCPContent(type="audio", data={"bytes": "not-released"})


@pytest.mark.parametrize(
    ("attribution", "billing_units", "cost_usd"),
    [
        ("settled", 4, Decimal("0.02")),
        ("explicit_zero", 0, Decimal("0")),
        ("unavailable", None, None),
    ],
)
def test_usage_summary_requires_state_consistent_monetary_values(attribution, billing_units, cost_usd):
    record = MCPUsageRecordSummary(
        gateway_request_id="gw-1",
        attribution=attribution,
        billing_units=billing_units,
        cost_usd=cost_usd,
    )

    assert record.attribution == attribution

    with pytest.raises(ValidationError):
        MCPUsageRecordSummary(
            gateway_request_id="gw-1",
            attribution="settled",
            billing_units=None,
            cost_usd=None,
        )
    with pytest.raises(ValidationError):
        MCPUsageRecordSummary(
            gateway_request_id="gw-1",
            attribution="unavailable",
            billing_units=0,
            cost_usd=Decimal("0"),
        )


def test_manifest_hash_is_stable_for_descriptor_order_and_excludes_response_disposition():
    first = discover_response(descriptors=(descriptor("context7.z"), descriptor("context7.a")))
    second = discover_response(descriptors=(descriptor("context7.a"), descriptor("context7.z")))
    second = second.model_copy(update={"disposition": "mcp.discover.complete; secret=redacted"})

    assert compute_manifest_hash(first) == compute_manifest_hash(second)
    assert canonical_manifest_bytes(first) == canonical_manifest_bytes(second)
    assert b"secret" not in canonical_manifest_bytes(second)


def test_discover_response_requires_namespaced_unique_descriptors():
    with pytest.raises(ValidationError, match="namespaced"):
        discover_response(descriptors=(descriptor("search"),))

    with pytest.raises(ValidationError, match="duplicate"):
        discover_response(descriptors=(descriptor("context7.search"), descriptor("context7.search")))


def test_call_response_requires_usage_attribution_to_match_summary():
    usage = MCPUsageRecordSummary(
        gateway_request_id="gw-1",
        attribution="unavailable",
        billing_units=None,
        cost_usd=None,
    )

    with pytest.raises(ValidationError, match="attribution"):
        MCPCallResponse(
            result_type="complete",
            content=(MCPContent(type="text", text="untrusted"),),
            disposition="mcp.call.complete",
            binding=MCPBindingSummary(
                profile_id="context7",
                profile_revision="rev-1",
                manifest_hash="a" * 64,
            ),
            transport="http",
            protocol_version="2026-07-28",
            attribution="settled",
            usage=usage,
        )
