"""Round-trip regression test for the parent/Gateway base_url resolution split.

Plan 9.96, Task 5 Batch 3 (review finding): ProviderSecrets.base_url resolved
to None when OPTIMUS_LOCAL_GATEWAY_BASE_URL was unset, but
GatewayServiceConfig.from_env() applies its own _DEFAULT_BASE_URLS[provider]
default independently. A manifest signed with base_url=None was rejected by
the REAL Gateway's verify_gateway_child_manifest() with
MANIFEST_BASE_URL_MISMATCH, because the Gateway's own from_env() resolved a
concrete URL that didn't match the signed None. This is the same "one value
computed independently in two places" disease as the Task 4 digest split and
the two incompatible HMAC domains.

This test exercises the REAL cross-package contract: ProviderSecrets'
resolved base_url (parent side) must equal GatewayServiceConfig.from_env()'s
resolved base_url (Gateway side) for every provider, given the SAME env
input. Both this test and its attack-sibling must keep passing after the
fix — the fix is "resolve identically," not "stop comparing."
"""

from __future__ import annotations

import pytest

from optimus.acp.local_gateway_secrets import resolve_provider_credentials
from optimus_gateway.models import GatewayServiceConfig
from optimus_security.launch_manifest import (
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)


class FakeKeyring:
    def get_password(self, service: str, key: str) -> str | None:
        return None


_HMAC_KEY = b"test-base-url-resolution-key-32!"


class TestParentAndGatewayResolveBaseUrlIdentically:
    """The concrete failing configuration from the review finding: provider
    set, OPTIMUS_LOCAL_GATEWAY_BASE_URL omitted (the documented/recommended
    common case in .env.gateway.example)."""

    @pytest.mark.parametrize("provider", ["openrouter", "openai"])
    def test_default_base_url_omitted_resolves_identically_on_both_sides(self, tmp_path, provider) -> None:
        environ = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider,
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-test-key",
        }

        # Parent side: resolve_provider_credentials -> ProviderSecrets.base_url.
        resolution = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
        assert resolution.secrets is not None
        parent_base_url = resolution.secrets.base_url

        # Gateway side: the real GatewayServiceConfig.from_env(), fed the
        # child env the parent WOULD construct (as_gateway_child_env()).
        child_env = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider,
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
            **resolution.secrets.as_gateway_child_env(),
        }
        gateway_config = GatewayServiceConfig.from_env(child_env, bind_host="127.0.0.1", bind_port=8765)

        assert parent_base_url == gateway_config.base_url, (
            f"parent resolved base_url={parent_base_url!r} but Gateway resolved "
            f"{gateway_config.base_url!r} for provider={provider!r} with no explicit "
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL -- these must be identical or the manifest "
            "signed by the parent can never verify against what the Gateway actually builds."
        )

    def test_anthropic_base_url_stays_none_on_both_sides(self, tmp_path) -> None:
        environ = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }
        resolution = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
        assert resolution.secrets is not None
        parent_base_url = resolution.secrets.base_url

        child_env = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
            **resolution.secrets.as_gateway_child_env(),
        }
        gateway_config = GatewayServiceConfig.from_env(child_env, bind_host="127.0.0.1", bind_port=8765)

        assert parent_base_url is None
        assert gateway_config.base_url is None

    @pytest.mark.parametrize("provider", ["openrouter", "openai"])
    def test_explicit_custom_base_url_still_passes_through_unchanged(self, tmp_path, provider) -> None:
        """The fix must not affect the explicit-override path — only the
        omitted-default case."""
        environ = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider,
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-test-key",
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://custom.example.com/v1",
        }
        resolution = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
        assert resolution.secrets is not None
        assert resolution.secrets.base_url == "https://custom.example.com/v1"

        child_env = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider,
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
            **resolution.secrets.as_gateway_child_env(),
        }
        gateway_config = GatewayServiceConfig.from_env(child_env, bind_host="127.0.0.1", bind_port=8765)
        assert gateway_config.base_url == "https://custom.example.com/v1"


class TestManifestRoundTripThroughRealGatewayFromEnv:
    """The end-to-end proof: a manifest signed by the parent for a
    default-base_url launch must verify against the REAL Gateway's
    from_env()-resolved config -- and an attacker-injected base_url must
    still be rejected. Both directions must hold simultaneously; a fix that
    breaks either one is wrong."""

    @pytest.mark.parametrize("provider", ["openrouter", "openai"])
    def test_legitimate_default_base_url_launch_is_accepted(self, tmp_path, provider) -> None:
        environ = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": provider,
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-legit-key",
        }
        resolution = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
        secrets_ = resolution.secrets
        assert secrets_ is not None

        manifest = build_gateway_child_manifest(
            workspace_digest="a" * 64,
            security_snapshot_digest="b" * 64,
            provider=secrets_.provider,
            base_url=secrets_.base_url,
            bind_host="127.0.0.1",
            bind_port=8765,
            provider_api_key=secrets_.model_provider_api_key,
            shared_secret="shared-secret-value",
            hmac_key=_HMAC_KEY,
            policy_version="P9.96-v1",
        )
        serialized = serialize_gateway_child_manifest(manifest)

        # The REAL Gateway side: build child_env the way the parent would,
        # then resolve the REAL GatewayServiceConfig.from_env() from it, then
        # verify the manifest against that config's ACTUAL fields -- not
        # against secrets_ again (that would just re-prove the parent's own
        # internal consistency, not the cross-package contract).
        child_env = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": secrets_.provider,
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
            **secrets_.as_gateway_child_env(),
        }
        gateway_config = GatewayServiceConfig.from_env(child_env, bind_host="127.0.0.1", bind_port=8765)

        # Must NOT raise MANIFEST_BASE_URL_MISMATCH.
        verified = verify_gateway_child_manifest(
            serialized,
            hmac_key=_HMAC_KEY,
            provider=gateway_config.provider,
            base_url=gateway_config.base_url,
            provider_api_key=gateway_config.provider_api_key,
            shared_secret=gateway_config.shared_secret,
            bind_host=gateway_config.bind_host,
            bind_port=gateway_config.bind_port,
        )
        assert verified.workspace_digest == "a" * 64

    def test_injected_base_url_is_still_rejected_after_the_fix(self, tmp_path) -> None:
        """The attack-sibling: an attacker who mutates
        OPTIMUS_LOCAL_GATEWAY_BASE_URL in the child env AFTER the parent
        signed the manifest must still be rejected -- proving the fix
        (resolving the default identically) did not become "accept any
        base_url on either side"."""
        environ = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-legit-key",
        }
        resolution = resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
        secrets_ = resolution.secrets
        assert secrets_ is not None

        manifest = build_gateway_child_manifest(
            workspace_digest="a" * 64,
            security_snapshot_digest="b" * 64,
            provider=secrets_.provider,
            base_url=secrets_.base_url,
            bind_host="127.0.0.1",
            bind_port=8765,
            provider_api_key=secrets_.model_provider_api_key,
            shared_secret="shared-secret-value",
            hmac_key=_HMAC_KEY,
            policy_version="P9.96-v1",
        )
        serialized = serialize_gateway_child_manifest(manifest)

        # Attacker injects a redirect AFTER signing -- into the raw env, not
        # through as_gateway_child_env().
        attacker_child_env = {
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER": secrets_.provider,
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "shared-secret-value",
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": secrets_.model_provider_api_key,
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://evil.attacker.example/v1",
        }
        attacker_gateway_config = GatewayServiceConfig.from_env(
            attacker_child_env, bind_host="127.0.0.1", bind_port=8765
        )
        assert attacker_gateway_config.base_url == "https://evil.attacker.example/v1"

        with pytest.raises(LaunchManifestError) as exc_info:
            verify_gateway_child_manifest(
                serialized,
                hmac_key=_HMAC_KEY,
                provider=attacker_gateway_config.provider,
                base_url=attacker_gateway_config.base_url,
                provider_api_key=attacker_gateway_config.provider_api_key,
                shared_secret=attacker_gateway_config.shared_secret,
                bind_host=attacker_gateway_config.bind_host,
                bind_port=attacker_gateway_config.bind_port,
            )
        assert exc_info.value.code == "MANIFEST_BASE_URL_MISMATCH"
