from __future__ import annotations

import getpass
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import keyring

from optimus_security.launch_manifest import resolve_effective_base_url

_KEYRING_SERVICE = "optimus-cost-agent"
_KEY_MODEL_PROVIDER = "model_provider"
_KEY_MODEL_PROVIDER_API_KEY = "model_provider_api_key"
_KEY_SHARED_SECRET = "local_gateway_shared_secret"

_SUPPORTED_PROVIDERS = ("anthropic", "openai", "openrouter")
SUPPORTED_GATEWAY_PROVIDERS = frozenset(_SUPPORTED_PROVIDERS)
_DEFAULT_PROVIDER = "openrouter"

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class ProviderSecrets:
    provider: str  # "openai" | "openrouter" | "anthropic"
    model_provider_api_key: str = field(repr=False)
    base_url: str | None = None

    def as_gateway_child_env(self) -> dict[str, str]:
        """Map to the exact var names GatewayServiceConfig.from_env() reads for this provider
        (src/optimus_gateway/models.py:45): ANTHROPIC_API_KEY for anthropic, else
        OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY. Only ever sets the one name the resolved
        provider needs. Also passes through OPTIMUS_LOCAL_GATEWAY_BASE_URL when set (models.py:44)
        — harmless to include for anthropic too, since GatewayServiceConfig.from_env() always
        forces base_url to None for that provider regardless of what's in its env."""
        env = (
            {"ANTHROPIC_API_KEY": self.model_provider_api_key}
            if self.provider == "anthropic"
            else {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": self.model_provider_api_key}
        )
        if self.base_url:
            env["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] = self.base_url
        return env


class CredentialLayer(str, Enum):
    ENVIRONMENT = "environment"
    CONFIG_FILE = "config_file"
    KEYRING = "keyring"
    DEFAULT = "default"
    MISSING = "missing"


@dataclass(frozen=True)
class CredentialProvenance:
    layer: CredentialLayer
    field_name: str


@dataclass(frozen=True)
class ProviderCredentialResolution:
    secrets: ProviderSecrets | None
    provider_provenance: CredentialProvenance
    api_key_provenance: CredentialProvenance
    base_url_provenance: CredentialProvenance
    warnings: tuple[str, ...] = ()


class ProviderCredentialConfigurationError(ValueError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def _parse_env_gateway_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _safe_get_password(keyring_backend: Any, key: str) -> str | None:
    try:
        value = keyring_backend.get_password(_KEYRING_SERVICE, key)
    except Exception:
        return None
    if value is None:
        return None
    value = value.strip()
    return value or None


def resolve_shared_secret(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
) -> str | None:
    env_value = environ.get("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "").strip()
    if env_value:
        return env_value
    dotenv_value = _parse_env_gateway_file(config_root / ".env.gateway").get(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", ""
    ).strip()
    if dotenv_value:
        return dotenv_value
    return _safe_get_password(keyring_backend, _KEY_SHARED_SECRET)


def _provider_error(provider: str, *, keyring: bool = False) -> ProviderCredentialConfigurationError:
    suffix = " Run `optimus-agent --setup` to choose a supported provider." if keyring else ""
    return ProviderCredentialConfigurationError(
        f"optimus-agent: unsupported provider {provider!r}; supported providers: "
        f"{', '.join(_SUPPORTED_PROVIDERS)}.{suffix}"
    )


def resolve_provider_credentials(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
) -> ProviderCredentialResolution:
    dotenv_values = _parse_env_gateway_file(config_root / ".env.gateway")
    provider_raw = environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
    provider_provenance = CredentialProvenance(
        CredentialLayer.ENVIRONMENT,
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
    )
    if not provider_raw:
        provider_raw = dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
        provider_provenance = CredentialProvenance(
            CredentialLayer.CONFIG_FILE,
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
        )
    if not provider_raw:
        provider_raw = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER)
        provider_provenance = CredentialProvenance(
            CredentialLayer.KEYRING,
            _KEY_MODEL_PROVIDER,
        )
    if provider_raw is None:
        provider = _DEFAULT_PROVIDER
        provider_provenance = CredentialProvenance(
            CredentialLayer.DEFAULT,
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
        )
    else:
        provider = provider_raw.casefold()
    if provider not in _SUPPORTED_PROVIDERS:
        raise _provider_error(
            provider,
            keyring=provider_provenance.layer is CredentialLayer.KEYRING,
        )
    stored_keyring_provider = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER)
    expected_key_name = (
        "ANTHROPIC_API_KEY"
        if provider == "anthropic"
        else "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"
    )
    alternate_key_name = (
        "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"
        if provider == "anthropic"
        else "ANTHROPIC_API_KEY"
    )
    api_key = environ.get(expected_key_name, "").strip()
    api_key_provenance = CredentialProvenance(CredentialLayer.ENVIRONMENT, expected_key_name)
    if not api_key:
        api_key = dotenv_values.get(expected_key_name, "").strip()
        api_key_provenance = CredentialProvenance(CredentialLayer.CONFIG_FILE, expected_key_name)
    if not api_key:
        keyring_api_key = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
        if keyring_api_key:
            api_key = keyring_api_key
            api_key_provenance = CredentialProvenance(
                CredentialLayer.KEYRING,
                _KEY_MODEL_PROVIDER_API_KEY,
            )
    warnings: list[str] = []
    if (
        api_key_provenance.layer is CredentialLayer.KEYRING
        and stored_keyring_provider
        and stored_keyring_provider.casefold() != provider.casefold()
    ):
        raise ProviderCredentialConfigurationError(
            "optimus-agent: local gateway provider resolves to "
            f"{provider!r} from {provider_provenance.layer.value}, but the keyring API key is paired "
            f"with provider {stored_keyring_provider!r}; run `optimus-agent --setup` or remove the "
            "higher-precedence provider override."
        )
    if provider_provenance.layer in {
        CredentialLayer.ENVIRONMENT,
        CredentialLayer.CONFIG_FILE,
        CredentialLayer.KEYRING,
    } and not api_key:
        alternate_value = environ.get(alternate_key_name, "").strip() or dotenv_values.get(
            alternate_key_name,
            "",
        ).strip()
        if alternate_value:
            raise ProviderCredentialConfigurationError(
                f"optimus-agent: provider {provider!r} requires {expected_key_name}; "
                f"found {alternate_key_name} instead. Configure {expected_key_name} or run "
                "`optimus-agent --setup`."
            )
    if not api_key:
        api_key_provenance = CredentialProvenance(CredentialLayer.MISSING, expected_key_name)
        if provider_provenance.layer is CredentialLayer.DEFAULT:
            return ProviderCredentialResolution(
                secrets=None,
                provider_provenance=provider_provenance,
                api_key_provenance=api_key_provenance,
                base_url_provenance=CredentialProvenance(
                    CredentialLayer.DEFAULT,
                    "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
                ),
                warnings=(),
            )
        warnings.append(
            f"optimus-agent: provider {provider!r} is configured but no {expected_key_name} "
            "was found; run `optimus-agent --setup`."
        )
    elif (
        provider_provenance.layer in {CredentialLayer.ENVIRONMENT, CredentialLayer.CONFIG_FILE}
        and api_key_provenance.layer in {CredentialLayer.ENVIRONMENT, CredentialLayer.CONFIG_FILE}
        and provider_provenance.layer is not api_key_provenance.layer
    ):
        warnings.append(
            "optimus-agent: provider and API key came from different configuration layers; "
            "the provider/key pairing cannot be proven."
        )
    if (
        api_key_provenance.layer is CredentialLayer.KEYRING
        and stored_keyring_provider is None
    ):
        warnings.append(
            "optimus-agent: provider key came from keyring but keyring has no stored model_provider; "
            "run `optimus-agent --setup` to restore the provider/key pair."
        )
    base_url = environ.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
    base_url_provenance = CredentialProvenance(
        CredentialLayer.ENVIRONMENT,
        "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
    )
    if not base_url:
        base_url = dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        base_url_provenance = CredentialProvenance(
            CredentialLayer.CONFIG_FILE,
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
        )
    if not base_url:
        base_url_provenance = CredentialProvenance(
            CredentialLayer.DEFAULT,
            "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
        )
    # Resolve the EFFECTIVE base_url through the single shared resolver
    # (optimus_security.launch_manifest.resolve_effective_base_url) rather
    # than leaving it None when unset. GatewayServiceConfig.from_env() on
    # the Gateway side applies its own default independently when no
    # explicit base_url is present in its child env — if this side left it
    # None, the manifest signed here would never match what the Gateway
    # actually constructs (review finding: MANIFEST_BASE_URL_MISMATCH on
    # every legitimate default-base_url launch).
    resolved_base_url = resolve_effective_base_url(provider=provider, base_url=base_url or None)
    resolved_secrets = (
        ProviderSecrets(
            provider=provider,
            model_provider_api_key=api_key,
            base_url=resolved_base_url,
        )
        if api_key
        else None
    )
    return ProviderCredentialResolution(
        secrets=resolved_secrets,
        provider_provenance=provider_provenance,
        api_key_provenance=api_key_provenance,
        base_url_provenance=base_url_provenance,
        warnings=tuple(warnings),
    )


def run_setup_wizard(
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[..., None] = print,
) -> int:
    provider = (input_fn(f"Provider [{_DEFAULT_PROVIDER}]: ").strip() or _DEFAULT_PROVIDER).lower()
    if provider not in _SUPPORTED_PROVIDERS:
        print_fn(f"Unsupported provider: {provider!r}. Choose one of {_SUPPORTED_PROVIDERS}.")
        return 1

    existing_api_key = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
    if existing_api_key:
        answer = input_fn("A provider key is already stored. Overwrite? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print_fn("Setup cancelled; existing credentials unchanged.")
            return 1

    api_key = getpass_fn(f"{provider} API key: ").strip()
    if not api_key:
        print_fn("No API key entered; aborting setup.")
        return 1

    shared_secret = secrets.token_urlsafe(32)

    try:
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_MODEL_PROVIDER, provider)
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_MODEL_PROVIDER_API_KEY, api_key)
        keyring_backend.set_password(_KEYRING_SERVICE, _KEY_SHARED_SECRET, shared_secret)
    except Exception as exc:
        print_fn(
            f"Could not store credentials in the OS keychain ({exc}). "
            "Use .env.gateway instead (see .env.gateway.example)."
        )
        return 2

    print_fn(
        "Stored local gateway credentials in the OS keychain. "
        "You can now run `optimus-agent` with no environment variables required."
    )
    if (config_root / ".env.gateway").is_file():
        print_fn(
            "Note: operator config file .env.gateway also exists; explicit environment values and "
            "that file take precedence over the keychain values just stored."
        )
    return 0
