import pytest
from pydantic import ValidationError

import optimus.config as config
from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES, OptimusGatewaySettings, ProviderKeyViolation


def test_default_gateway_url_is_loopback():
    settings = OptimusGatewaySettings(optimus_api_key="opt_test")

    assert settings.gateway_url == "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8765",
        "https://127.0.0.1:8765",
        "http://localhost:8765",
        "https://[::1]:8765",
    ],
)
def test_loopback_urls_are_accepted(url: str):
    settings = OptimusGatewaySettings(gateway_url=url, optimus_api_key="opt_test")

    assert settings.validate_trusted_gateway() is None
    assert settings.validate_trusted_gateway() is None


@pytest.mark.parametrize(
    "url",
    [
        "https://gateway.optimus.ai",
        "https://tenant.example",
        "http://example.com",
        "file:///tmp/gateway",
        "http://user:pass@127.0.0.1:8765",
        "http://127.0.0.1:99999",
        "http://[::1",
    ],
)
def test_non_loopback_or_ambiguous_urls_fail_closed(url: str):
    with pytest.raises(ValueError):
        OptimusGatewaySettings(gateway_url=url, optimus_api_key="opt_test")


@pytest.mark.parametrize(
    "field",
    [
        "production_mode",
        "extra_trusted_origins",
        "signed_tenant_profile_origins",
        "provider_key_policy",
    ],
)
def test_retired_settings_fields_are_rejected(field: str):
    with pytest.raises(ValidationError):
        OptimusGatewaySettings(optimus_api_key="opt_test", **{field: "ignored"})


def test_retired_exports_are_absent():
    for name in ("BUILT_IN_TRUSTED_GATEWAY_ORIGINS", "ProviderKeyPolicy"):
        assert not hasattr(config, name)


def test_secret_is_masked_in_repr_str_and_model_dump():
    settings = OptimusGatewaySettings(optimus_api_key="opt_live_secret")

    assert "opt_live_secret" not in repr(settings)
    assert "**********" in repr(settings)
    assert "opt_live_secret" not in str(settings)
    assert "**********" in str(settings)
    dumped = settings.safe_model_dump()
    assert dumped["optimus_api_key"] == "**********"
    assert "opt_live_secret" not in str(dumped)
    assert settings.auth_headers() == {"Authorization": "Bearer opt_live_secret"}


def test_from_env_defaults_to_loopback_and_requires_nonempty_api_key():
    settings = OptimusGatewaySettings.from_env({"OPTIMUS_API_KEY": "opt_test"})

    assert settings.gateway_url == "http://127.0.0.1:8765"
    with pytest.raises(ValueError, match="OPTIMUS_API_KEY is required"):
        OptimusGatewaySettings.from_env({})


def test_provider_keys_are_always_rejected():
    settings = OptimusGatewaySettings(optimus_api_key="opt_test")

    with pytest.raises(ProviderKeyViolation) as exc_info:
        settings.validate_no_local_provider_keys({"OPENAI_API_KEY": "sk-local"})

    assert exc_info.value.keys == ["OPENAI_API_KEY"]
    assert LOCAL_PROVIDER_KEY_NAMES
