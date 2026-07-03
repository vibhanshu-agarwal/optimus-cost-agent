import pytest
from pydantic import ValidationError

from optimus.config.gateway import (
    BUILT_IN_TRUSTED_GATEWAY_ORIGINS,
    OptimusGatewaySettings,
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
