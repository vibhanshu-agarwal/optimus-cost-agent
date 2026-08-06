from decimal import Decimal

from optimus.gateway import mcp_models as agent_models
from optimus_gateway import mcp_models as gateway_models


def test_gateway_and_agent_contracts_emit_identical_canonical_json():
    payload = {
        "profile_id": "context7",
        "profile_revision": "rev-1",
        "manifest_hash": "a" * 64,
        "tool_name": "context7.search",
        "run_id": "run-1",
        "session_id": "session-1",
        "request_id": "request-1",
        "arguments": {"query": "pytest", "limit": 3},
    }

    agent_request = agent_models.MCPCallRequest.model_validate(payload)
    gateway_request = gateway_models.MCPCallRequest.model_validate(payload)

    assert agent_request.model_dump(mode="json") == gateway_request.model_dump(mode="json")


def test_gateway_and_agent_response_contracts_parse_same_usage_states():
    payload = {
        "gateway_request_id": "gw-1",
        "attribution": "settled",
        "billing_units": 4,
        "cost_usd": "0.02",
    }

    agent_usage = agent_models.MCPUsageRecordSummary.model_validate(payload)
    gateway_usage = gateway_models.MCPUsageRecordSummary.model_validate(payload)

    assert agent_usage.model_dump(mode="json") == gateway_usage.model_dump(mode="json")
    assert agent_usage.cost_usd == Decimal("0.02")
