import pytest
from pydantic import ValidationError

from optimus.config.gateway import (
    BUILT_IN_TRUSTED_GATEWAY_ORIGINS,
    OptimusGatewaySettings,
    ProviderKeyPolicy,
    ProviderKeyViolation,
)


def test_builtin_gateway_origin_is_trusted():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    assert settings.validate_trusted_gateway() is None


def test_auth_headers_use_optimus_key_only():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    assert settings.auth_headers() == {"Authorization": "Bearer opt_live_abc"}


def test_secret_is_masked_in_repr_str_and_model_dump():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_secret",
    )

    assert "opt_live_secret" not in repr(settings)
    assert "**********" in repr(settings)
    assert "opt_live_secret" not in str(settings)
    assert "**********" in str(settings)
    dumped = settings.safe_model_dump()
    assert dumped["optimus_api_key"] == "**********"
    assert "opt_live_secret" not in str(dumped)


def test_empty_api_key_is_rejected():
    with pytest.raises(ValidationError):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="",
        )


def test_builtin_origin_constant_is_exact_phase_1_origin():
    assert BUILT_IN_TRUSTED_GATEWAY_ORIGINS == frozenset({"https://gateway.optimus.ai"})


def test_rogue_gateway_origin_is_rejected():
    settings = OptimusGatewaySettings(
        gateway_url="https://rogue.attacker.com",
        optimus_api_key="opt_live_abc",
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        settings.validate_trusted_gateway()


def test_non_production_extra_origin_is_accepted():
    settings = OptimusGatewaySettings(
        gateway_url="https://internal.corp.com/path",
        optimus_api_key="opt_live_abc",
        production_mode=False,
        extra_trusted_origins=("https://internal.corp.com",),
    )

    assert settings.validate_trusted_gateway() is None


def test_production_extra_origins_are_rejected():
    with pytest.raises(ValueError, match="extra_trusted_origins must not be set in production_mode"):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="opt_live_abc",
            production_mode=True,
            extra_trusted_origins=("https://internal.corp.com",),
        )


def test_production_env_ignores_extra_gateway_origins():
    settings = OptimusGatewaySettings.from_env(
        {
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPTIMUS_PRODUCTION_MODE": "true",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://internal.corp.com",
        }
    )

    assert settings.production_mode is True
    assert settings.extra_trusted_origins == ()


def test_non_production_env_loads_extra_gateway_origins():
    settings = OptimusGatewaySettings.from_env(
        {
            "OPTIMUS_GATEWAY_URL": "https://internal.corp.com",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPTIMUS_PRODUCTION_MODE": "false",
            "OPTIMUS_EXTRA_GATEWAY_ORIGINS": "https://internal.corp.com",
        }
    )

    assert settings.production_mode is False
    assert settings.extra_trusted_origins == ("https://internal.corp.com",)
    assert settings.validate_trusted_gateway() is None


def test_already_verified_signed_tenant_profile_origin_is_accepted_in_production():
    settings = OptimusGatewaySettings(
        gateway_url="https://tenant-gateway.example.com",
        optimus_api_key="opt_live_abc",
        production_mode=True,
        signed_tenant_profile_origins=("https://tenant-gateway.example.com",),
    )

    assert settings.validate_trusted_gateway() is None


def test_from_env_rejects_provider_keys_in_production():
    with pytest.raises(ProviderKeyViolation) as exc_info:
        OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPTIMUS_PRODUCTION_MODE": "true",
                "OPENAI_API_KEY": "sk-local",
            }
        )

    assert exc_info.value.keys == ["OPENAI_API_KEY"]


def test_from_env_validates_trusted_gateway_before_returning_settings():
    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        OptimusGatewaySettings.from_env(
            {
                "OPTIMUS_GATEWAY_URL": "https://rogue.attacker.com",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPTIMUS_PRODUCTION_MODE": "true",
            }
        )


def test_provider_keys_are_rejected_by_default():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
    )

    with pytest.raises(ProviderKeyViolation) as exc_info:
        settings.validate_no_local_provider_keys(
            {
                "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
                "OPTIMUS_API_KEY": "opt_live_abc",
                "OPENAI_API_KEY": "sk-local",
                "TAVILY_API_KEY": "tvly-local",
                "LANGSMITH_API_KEY": "lsv2-local",
            }
        )

    assert exc_info.value.keys == ["LANGSMITH_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"]


def test_provider_keys_can_be_ignored_without_loading_in_non_production():
    settings = OptimusGatewaySettings(
        gateway_url="https://gateway.optimus.ai",
        optimus_api_key="opt_live_abc",
        production_mode=False,
        provider_key_policy=ProviderKeyPolicy.IGNORE,
    )

    ignored = settings.validate_no_local_provider_keys(
        {
            "OPTIMUS_GATEWAY_URL": "https://gateway.optimus.ai",
            "OPTIMUS_API_KEY": "opt_live_abc",
            "OPENROUTER_API_KEY": "or-local",
            "GLM_API_KEY": "glm-local",
        }
    )

    assert ignored == ("GLM_API_KEY", "OPENROUTER_API_KEY")
    assert "or-local" not in repr(ignored)
    assert "glm-local" not in repr(ignored)


def test_ignore_policy_cannot_be_used_in_production():
    with pytest.raises(ValueError, match="provider_key_policy=ignore is valid only outside production_mode"):
        OptimusGatewaySettings(
            gateway_url="https://gateway.optimus.ai",
            optimus_api_key="opt_live_abc",
            production_mode=True,
            provider_key_policy=ProviderKeyPolicy.IGNORE,
        )


def test_non_production_loopback_http_origin_is_trusted():
    settings = OptimusGatewaySettings(
        gateway_url="http://127.0.0.1:8765",
        optimus_api_key="opt_live_abc",
        production_mode=False,
    )

    assert settings.validate_trusted_gateway() is None


def test_production_rejects_loopback_http_origin():
    settings = OptimusGatewaySettings(
        gateway_url="http://127.0.0.1:8765",
        optimus_api_key="opt_live_abc",
        production_mode=True,
    )

    with pytest.raises(ValueError):
        settings.validate_trusted_gateway()


def test_non_production_rejects_non_loopback_http_origin():
    settings = OptimusGatewaySettings(
        gateway_url="http://example.com",
        optimus_api_key="opt_live_abc",
        production_mode=False,
    )

    with pytest.raises(ValueError, match="gateway origin not in trusted set"):
        settings.validate_trusted_gateway()
