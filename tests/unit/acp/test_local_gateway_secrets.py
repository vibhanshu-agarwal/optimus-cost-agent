from __future__ import annotations

import pytest

from optimus.acp.local_gateway_secrets import (
    CredentialLayer,
    ProviderCredentialConfigurationError,
    ProviderSecrets,
    resolve_provider_credentials,
    resolve_shared_secret,
    run_setup_wizard,
)


class FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value


def test_resolve_shared_secret_prefers_env_over_dotenv_and_keyring(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=from-dotenv\n",
        encoding="utf-8",
    )
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    resolved = resolve_shared_secret(
        {"OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": "from-env"},
        config_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert resolved == "from-env"


def test_resolve_shared_secret_falls_back_dotenv_then_keyring(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    assert resolve_shared_secret({}, config_root=tmp_path, keyring_backend=fake_keyring) == "from-keyring"

    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=from-dotenv\n",
        encoding="utf-8",
    )
    assert resolve_shared_secret({}, config_root=tmp_path, keyring_backend=fake_keyring) == "from-dotenv"


def test_setup_wizard_stores_provider_key_and_generated_shared_secret(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    inputs = iter(["openrouter"])
    exit_code = run_setup_wizard(
        config_root=tmp_path,
        keyring_backend=fake_keyring,
        input_fn=lambda _prompt: next(inputs),
        getpass_fn=lambda _prompt: "sk-test-key",
        print_fn=lambda *_a, **_k: None,
    )

    assert exit_code == 0
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider") == "openrouter"
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider_api_key") == "sk-test-key"
    assert fake_keyring.get_password("optimus-cost-agent", "local_gateway_shared_secret")


def test_setup_wizard_declines_overwrite_without_confirmation(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "existing-key")
    inputs = iter(["openrouter", "n"])

    exit_code = run_setup_wizard(
        config_root=tmp_path,
        keyring_backend=fake_keyring,
        input_fn=lambda _prompt: next(inputs),
        getpass_fn=lambda _prompt: "sk-new-key",
        print_fn=lambda *_a, **_k: None,
    )

    assert exit_code == 1
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider_api_key") == "existing-key"


def test_resolve_provider_credentials_returns_none_when_nothing_configured(tmp_path) -> None:
    result = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=FakeKeyring())
    assert result.secrets is None
    assert result.provider_provenance.layer is CredentialLayer.DEFAULT


def test_resolve_provider_credentials_defaults_provider_to_openrouter_when_unset(tmp_path) -> None:
    resolved = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-implicit"},
        config_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert resolved.secrets == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-implicit")


def test_provider_secrets_includes_base_url_when_set(tmp_path) -> None:
    secrets_ = ProviderSecrets(
        provider="openai",
        model_provider_api_key="sk-test",
        base_url="https://custom.example.com/v1",
    )

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-test",
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL": "https://custom.example.com/v1",
    }


def test_resolve_provider_credentials_passes_through_base_url_from_dotenv(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openai\n"
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-test\n"
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL=https://custom.example.com/v1\n",
        encoding="utf-8",
    )

    resolved = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=FakeKeyring())

    assert resolved.secrets == ProviderSecrets(
        provider="openai",
        model_provider_api_key="sk-test",
        base_url="https://custom.example.com/v1",
    )


def test_provider_secrets_maps_anthropic_to_anthropic_api_key_only(tmp_path) -> None:
    secrets_ = ProviderSecrets(provider="anthropic", model_provider_api_key="sk-ant-test")

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {"ANTHROPIC_API_KEY": "sk-ant-test"}
    assert "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY" not in child_env


def test_provider_secrets_maps_openrouter_to_provider_api_key_var_only(tmp_path) -> None:
    secrets_ = ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-test")

    child_env = secrets_.as_gateway_child_env()

    assert child_env == {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-test"}
    assert "ANTHROPIC_API_KEY" not in child_env


def test_no_keyring_backend_available_fails_with_dotenv_pointer(tmp_path) -> None:
    class RaisingKeyring:
        def get_password(self, *_a: object, **_k: object) -> str:
            raise RuntimeError("no backend")

        def set_password(self, *_a: object, **_k: object) -> None:
            raise RuntimeError("no backend")

    messages: list[str] = []
    exit_code = run_setup_wizard(
        config_root=tmp_path,
        keyring_backend=RaisingKeyring(),
        input_fn=lambda _prompt: "openrouter",
        getpass_fn=lambda _prompt: "sk-test",
        print_fn=lambda msg="", **_k: messages.append(msg),
    )

    assert exit_code == 2
    assert any(".env.gateway" in msg for msg in messages)


def test_env_provider_and_mismatched_keyring_provider_fails_closed(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider", "openrouter")
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "sk-private-value")

    with pytest.raises(ProviderCredentialConfigurationError) as exc_info:
        resolve_provider_credentials(
            {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openai"},
            config_root=tmp_path,
            keyring_backend=fake_keyring,
        )

    message = str(exc_info.value)
    assert "openai" in message and "openrouter" in message
    assert "sk-private-value" not in message


def test_config_provider_and_matching_keyring_provider_pass_without_conflict(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openai\n",
        encoding="utf-8",
    )
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider", "openai")
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "sk-private-value")

    result = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=fake_keyring)

    assert result.secrets == ProviderSecrets(provider="openai", model_provider_api_key="sk-private-value")
    assert result.warnings == ()
    assert "sk-private-value" not in repr(result)


def test_explicit_provider_without_keyring_key_warns_partial_state(tmp_path) -> None:
    result = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter"},
        config_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert result.secrets is None
    assert result.warnings


def test_env_provider_and_config_generic_key_warns_unprovable_split(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-private-value\n",
        encoding="utf-8",
    )
    result = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter"},
        config_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert result.secrets == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-private-value")
    assert any("layer" in warning.lower() or "unprovable" in warning.lower() for warning in result.warnings)
    assert "sk-private-value" not in repr(result)
    assert "sk-private-value" not in repr(result.warnings)


def test_config_anthropic_provider_uses_anthropic_key(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-private-value\n",
        encoding="utf-8",
    )
    result = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=FakeKeyring())

    assert result.secrets == ProviderSecrets(provider="anthropic", model_provider_api_key="sk-private-value")
    assert "sk-private-value" not in repr(result)


def test_explicit_anthropic_provider_with_only_generic_key_fails_with_anthropic_remediation(tmp_path) -> None:
    with pytest.raises(ProviderCredentialConfigurationError, match="ANTHROPIC_API_KEY") as exc_info:
        resolve_provider_credentials(
            {
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "anthropic",
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-private-value",
            },
            config_root=tmp_path,
            keyring_backend=FakeKeyring(),
        )
    assert "sk-private-value" not in str(exc_info.value)


def test_explicit_openai_provider_with_only_anthropic_key_fails_with_generic_remediation(tmp_path) -> None:
    with pytest.raises(
        ProviderCredentialConfigurationError,
        match="OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    ) as exc_info:
        resolve_provider_credentials(
            {
                "OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openai",
                "ANTHROPIC_API_KEY": "sk-private-value",
            },
            config_root=tmp_path,
            keyring_backend=FakeKeyring(),
        )
    assert "sk-private-value" not in str(exc_info.value)


def test_keyring_key_without_stored_provider_warns_and_resolves(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "sk-private-value")

    result = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openrouter"},
        config_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert result.secrets == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-private-value")
    assert result.api_key_provenance.layer is CredentialLayer.KEYRING
    assert result.warnings == (
        "optimus-agent: provider key came from keyring but keyring has no stored model_provider; "
        "run `optimus-agent --setup` to restore the provider/key pair.",
    )
    assert "sk-private-value" not in repr(result)


def test_stored_keyring_provider_without_key_does_not_trigger_pair_conflict(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider", "openrouter")

    result = resolve_provider_credentials(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "openai"},
        config_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert result.secrets is None
    assert result.api_key_provenance.layer is CredentialLayer.MISSING
    assert any("setup" in warning for warning in result.warnings)


def test_default_provider_with_only_ambient_anthropic_key_returns_setup_pointer(tmp_path) -> None:
    result = resolve_provider_credentials(
        {"ANTHROPIC_API_KEY": "sk-private-value"},
        config_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert result.secrets is None
    assert result.provider_provenance.layer is CredentialLayer.DEFAULT
    assert "sk-private-value" not in repr(result)
    assert not any("ANTHROPIC_API_KEY" in warning for warning in result.warnings)


def test_keyring_provider_resolves_keyring_pair(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider", "openrouter")
    fake_keyring.set_password("optimus-cost-agent", "model_provider_api_key", "sk-private-value")

    result = resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=fake_keyring)

    assert result.secrets == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-private-value")


@pytest.mark.parametrize(
    ("environ", "dotenv"),
    [
        ({"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "unsupported"}, {}),
        ({}, {"OPTIMUS_LOCAL_GATEWAY_PROVIDER": "unsupported"}),
    ],
)
def test_explicit_unsupported_provider_names_supported_set(tmp_path, environ, dotenv) -> None:
    if dotenv:
        (tmp_path / ".env.gateway").write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=unsupported\n",
            encoding="utf-8",
        )
    with pytest.raises(
        ProviderCredentialConfigurationError,
        match="anthropic, openai, openrouter",
    ) as exc_info:
        resolve_provider_credentials(environ, config_root=tmp_path, keyring_backend=FakeKeyring())
    assert "sk-private-value" not in str(exc_info.value)


def test_unsupported_keyring_provider_fails_closed_with_setup_remediation(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "model_provider", "unsupported")

    with pytest.raises(
        ProviderCredentialConfigurationError,
        match=r"anthropic, openai, openrouter.*optimus-agent --setup",
    ):
        resolve_provider_credentials({}, config_root=tmp_path, keyring_backend=fake_keyring)
