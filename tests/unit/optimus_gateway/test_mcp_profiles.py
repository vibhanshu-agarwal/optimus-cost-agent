from __future__ import annotations

import pytest

from optimus_gateway.mcp_models import MCPCallRequest, MCPDiscoverRequest


def _profile_kwargs(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "profile_id": "context7",
        "revision": "rev-1",
        "state": "PENDING_REGISTRATION",
        "transport": "http",
        "credential_ref": "gateway://mcp/context7",
        "upstream_allowlist": ("search", "fetch"),
        "manifest_hash": None,
        "limits": {"max_pages": 10, "max_tools": 50, "max_descriptor_bytes": 65536},
        "attribution_policy": {"allow_unattributed_spend": False},
        "transport_config": {"endpoint": "https://context7.example/mcp"},
    }
    values.update(overrides)
    return values


def _new_registry():
    from optimus_gateway.mcp_profiles import (
        MCPAttributionPolicy,
        MCPHTTPProfile,
        MCPProfile,
        MCPProfileRegistry,
        MCPResourceLimits,
    )

    profile = MCPProfile(
        profile_id="context7",
        revision="rev-1",
        state="PENDING_REGISTRATION",
        transport="http",
        credential_ref="gateway://mcp/context7",
        upstream_allowlist=("search", "fetch"),
        manifest_hash=None,
        limits=MCPResourceLimits(max_pages=10, max_tools=50, max_descriptor_bytes=65536),
        attribution_policy=MCPAttributionPolicy(allow_unattributed_spend=False),
        transport_config=MCPHTTPProfile(endpoint="https://context7.example/mcp"),
    )
    return MCPProfileRegistry((profile,)), profile


def test_profile_lifecycle_requires_startup_activation_and_exact_binding():
    registry, profile = _new_registry()
    manifest_hash = "a" * 64

    registration = registry.for_discovery(
        MCPDiscoverRequest(profile_id="context7", profile_revision=profile.revision)
    )
    assert registration.accepted is True
    assert registration.profile.state.value == "PENDING_REGISTRATION"

    active = registry.activate_from_startup(
        profile_id="context7", revision=profile.revision, manifest_hash=manifest_hash
    )
    assert active.state.value == "ACTIVE"
    assert active.manifest_hash == manifest_hash

    assert registry.for_call(
        MCPCallRequest(
            run_id="run-1",
            request_id="request-1",
            profile_id="context7",
            profile_revision=profile.revision,
            manifest_hash=manifest_hash,
            tool_name="context7.search",
            arguments={"query": "pytest"},
        )
    ).accepted is True

    assert registry.for_call(
        MCPCallRequest(
            run_id="run-1",
            request_id="request-2",
            profile_id="context7",
            profile_revision=profile.revision,
            manifest_hash="b" * 64,
            tool_name="context7.search",
            arguments={},
        )
    ).accepted is False

    assert registry.for_call(
        MCPCallRequest(
            run_id="run-1",
            request_id="request-3",
            profile_id="context7",
            profile_revision=profile.revision,
            manifest_hash=manifest_hash,
            tool_name="context7.delete",
            arguments={},
        )
    ).accepted is False


def test_profile_drift_marks_stale_and_replacement_mints_revision():
    registry, profile = _new_registry()
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash="a" * 64)

    registry.mark_stale(profile_id="context7", revision="rev-1", reason="manifest drift")
    assert registry.get("context7").state.value == "STALE"
    stale_refresh = registry.for_discovery(
        MCPDiscoverRequest(profile_id="context7", profile_revision="rev-1", manifest_hash="a" * 64)
    )
    assert stale_refresh.accepted is True
    assert stale_refresh.disposition == "mcp.profile_stale_refresh_allowed"
    assert registry.for_call(
        MCPCallRequest(
            run_id="run-1",
            request_id="request-1",
            profile_id="context7",
            profile_revision="rev-1",
            manifest_hash="a" * 64,
            tool_name="context7.search",
            arguments={},
        )
    ).accepted is False

    replacement = registry.update_profile(
        profile_id="context7", upstream_allowlist=("search",), credential_ref="gateway://mcp/context7-v2"
    )
    assert replacement.revision != profile.revision
    assert replacement.state.value == "PENDING_REGISTRATION"
    assert replacement.manifest_hash is None
    assert replacement.upstream_allowlist == ("search",)


def test_disable_is_immediate_and_reenable_mints_pending_revision():
    registry, _ = _new_registry()
    registry.activate_from_startup(profile_id="context7", revision="rev-1", manifest_hash="a" * 64)

    registry.disable(profile_id="context7")
    disabled = registry.get("context7")
    assert disabled.state.value == "DISABLED"
    assert disabled.revision == "rev-1"

    reenabled = registry.reenable(profile_id="context7")
    assert reenabled.state.value == "PENDING_REGISTRATION"
    assert reenabled.revision != "rev-1"
    assert reenabled.manifest_hash is None


@pytest.mark.parametrize(
    "field",
    ["oauth", "client_id", "access_token", "refresh_token", "catalog_url", "autoload"],
)
def test_profile_definition_rejects_deferred_or_oauth_fields(field: str):
    from optimus_gateway.mcp_profiles import MCPProfileDefinitionError, profile_from_mapping

    values = _profile_kwargs(**{field: "forbidden"})
    with pytest.raises(MCPProfileDefinitionError):
        profile_from_mapping(values)


def test_profile_definition_keeps_allowlist_and_credential_reference_gateway_owned():
    from optimus_gateway.mcp_profiles import MCPProfileDefinitionError, profile_from_mapping

    profile = profile_from_mapping(_profile_kwargs())
    assert profile.upstream_allowlist == ("search", "fetch")
    assert profile.credential_ref == "gateway://mcp/context7"
    assert not hasattr(profile, "credential")

    with pytest.raises(MCPProfileDefinitionError):
        profile_from_mapping(_profile_kwargs(credential_ref="a" * 64))


def test_unknown_profile_and_direct_activation_cannot_create_a_profile():
    registry, _ = _new_registry()

    assert registry.for_discovery(
        MCPDiscoverRequest(profile_id="other", profile_revision="rev-1")
    ).accepted is False
    with pytest.raises(KeyError):
        registry.activate_from_startup(profile_id="other", revision="rev-1", manifest_hash="a" * 64)
    assert not hasattr(registry, "register_from_bearer")


def test_startup_metadata_requires_an_existing_manifest_binding():
    from optimus_gateway.mcp_profiles import MCPProfileDefinitionError, MCPProfileRegistry

    with pytest.raises(MCPProfileDefinitionError, match="manifest_hash"):
        MCPProfileRegistry.from_startup_metadata([_profile_kwargs()])


def test_http_bearer_is_the_default_and_requires_a_credential_ref():
    from optimus_gateway.mcp_profiles import MCPProfileDefinitionError, profile_from_mapping

    with pytest.raises(MCPProfileDefinitionError, match="credential_ref"):
        profile_from_mapping(_profile_kwargs(credential_ref=None))


def test_http_none_requires_explicit_mode_and_has_no_credential_ref():
    from optimus_gateway.mcp_profiles import profile_from_mapping

    profile = profile_from_mapping(
        _profile_kwargs(
            credential_ref=None,
            transport_config={"endpoint": "https://mcp.context7.com/mcp", "auth_mode": "none"},
        )
    )
    assert profile.transport_config.auth_mode == "none"
    assert profile.credential_ref is None


def test_empty_credential_does_not_infer_http_none():
    from optimus_gateway.mcp_profiles import MCPProfileDefinitionError, profile_from_mapping

    with pytest.raises(MCPProfileDefinitionError):
        profile_from_mapping(
            _profile_kwargs(
                credential_ref="",
                transport_config={"endpoint": "https://mcp.context7.com/mcp", "auth_mode": "none"},
            )
        )
