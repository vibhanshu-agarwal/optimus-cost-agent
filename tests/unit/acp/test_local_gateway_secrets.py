from __future__ import annotations

from optimus.acp.local_gateway_secrets import (
    ProviderSecrets,
    resolve_provider_secrets,
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
        project_root=tmp_path,
        keyring_backend=fake_keyring,
    )

    assert resolved == "from-env"


def test_resolve_shared_secret_falls_back_dotenv_then_keyring(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    fake_keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", "from-keyring")

    assert resolve_shared_secret({}, project_root=tmp_path, keyring_backend=fake_keyring) == "from-keyring"

    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=from-dotenv\n",
        encoding="utf-8",
    )
    assert resolve_shared_secret({}, project_root=tmp_path, keyring_backend=fake_keyring) == "from-dotenv"


def test_setup_wizard_stores_provider_key_and_generated_shared_secret(tmp_path) -> None:
    fake_keyring = FakeKeyring()
    inputs = iter(["openrouter"])
    exit_code = run_setup_wizard(
        project_root=tmp_path,
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
        project_root=tmp_path,
        keyring_backend=fake_keyring,
        input_fn=lambda _prompt: next(inputs),
        getpass_fn=lambda _prompt: "sk-new-key",
        print_fn=lambda *_a, **_k: None,
    )

    assert exit_code == 1
    assert fake_keyring.get_password("optimus-cost-agent", "model_provider_api_key") == "existing-key"


def test_resolve_provider_secrets_returns_none_when_nothing_configured(tmp_path) -> None:
    assert resolve_provider_secrets({}, project_root=tmp_path, keyring_backend=FakeKeyring()) is None


def test_resolve_provider_secrets_defaults_provider_to_openrouter_when_unset(tmp_path) -> None:
    resolved = resolve_provider_secrets(
        {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": "sk-or-implicit"},
        project_root=tmp_path,
        keyring_backend=FakeKeyring(),
    )

    assert resolved == ProviderSecrets(provider="openrouter", model_provider_api_key="sk-or-implicit")


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


def test_resolve_provider_secrets_passes_through_base_url_from_dotenv(tmp_path) -> None:
    (tmp_path / ".env.gateway").write_text(
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openai\n"
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-test\n"
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL=https://custom.example.com/v1\n",
        encoding="utf-8",
    )

    resolved = resolve_provider_secrets({}, project_root=tmp_path, keyring_backend=FakeKeyring())

    assert resolved == ProviderSecrets(
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
        project_root=tmp_path,
        keyring_backend=RaisingKeyring(),
        input_fn=lambda _prompt: "openrouter",
        getpass_fn=lambda _prompt: "sk-test",
        print_fn=lambda msg="", **_k: messages.append(msg),
    )

    assert exit_code == 2
    assert any(".env.gateway" in msg for msg in messages)
