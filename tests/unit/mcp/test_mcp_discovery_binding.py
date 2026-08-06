from __future__ import annotations

from optimus.gateway.mcp_models import MCPDiscoverRequest


def test_discovery_request_contains_only_profile_binding_for_registration_or_refresh():
    registration = MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1")
    refresh = MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1", manifest_hash="a" * 64)

    assert registration.model_dump(mode="json") == {
        "profile_id": "context7",
        "profile_revision": "rev-1",
        "manifest_hash": None,
    }
    assert refresh.model_dump(mode="json")["manifest_hash"] == "a" * 64
    assert "endpoint" not in registration.model_dump()
    assert "credential" not in refresh.model_dump()
