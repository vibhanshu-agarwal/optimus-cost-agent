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
from keyring.errors import NoKeyringError

from optimus_security.launch_manifest import resolve_effective_base_url

_KEYRING_SERVICE = "optimus-cost-agent"
_KEY_MODEL_PROVIDER = "model_provider"
_KEY_MODEL_PROVIDER_API_KEY = "model_provider_api_key"  # pragma: allowlist secret - keyring lookup name, not a retrieved credential
_KEY_SHARED_SECRET = "local_gateway_shared_secret"  # pragma: allowlist secret - keyring lookup name, not a retrieved credential

_SUPPORTED_PROVIDERS = ("openrouter",)
SUPPORTED_GATEWAY_PROVIDERS = frozenset(_SUPPORTED_PROVIDERS)
_DEFAULT_PROVIDER = "openrouter"

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class ProviderSecrets:
    provider: str
    model_provider_api_key: str = field(repr=False)
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.provider != _DEFAULT_PROVIDER:
            raise ValueError("ProviderSecrets supports the OpenRouter Gateway credential only.")

    def as_gateway_child_env(self) -> dict[str, str]:
        """Project the OpenRouter aggregator credential into the Gateway child only."""
        env = {"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": self.model_provider_api_key}
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


class CredentialStoreUnavailable(ProviderCredentialConfigurationError):
    """#654: the OS credential store raised on a read, so whether it holds the entry is unknown. Never read as absent."""


_ENV_NAME_FOR_KEY = {
    _KEY_MODEL_PROVIDER: "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
    _KEY_MODEL_PROVIDER_API_KEY: "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",  # pragma: allowlist secret - variable name, not a credential
    _KEY_SHARED_SECRET: "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",  # pragma: allowlist secret - variable name, not a credential
}


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
    """The stored value, or None when the store holds none; raises `CredentialStoreUnavailable` when it cannot answer.
    With no keyring backend at all (keyring's fail backend), nothing can be stored, so that is absent, not unknown."""
    failure: str | None = None
    try:
        value = keyring_backend.get_password(_KEYRING_SERVICE, key)
    except NoKeyringError:
        return None
    except Exception as exc:  # noqa: BLE001 - any backend failure means "unknown"; only its class is reported
        failure = type(exc).__name__
    if failure is not None:  # raised outside the handler, so the backend's exception is not even its __context__
        raise CredentialStoreUnavailable(
            f"optimus-agent: the OS keychain could not be read for {key} ({failure}); "
            f"set {_ENV_NAME_FOR_KEY.get(key, key)} in .env.gateway or the environment, or repair the keychain."
        )
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_env_config_keyring(
    environ: Mapping[str, str],
    *,
    dotenv_values: Mapping[str, str],
    env_name: str,
    keyring_name: str,
    keyring_backend: Any,
) -> tuple[str | None, CredentialProvenance]:
    environment_value = environ.get(env_name, "").strip()
    if environment_value:
        return environment_value, CredentialProvenance(CredentialLayer.ENVIRONMENT, env_name)
    config_value = dotenv_values.get(env_name, "").strip()
    if config_value:
        return config_value, CredentialProvenance(CredentialLayer.CONFIG_FILE, env_name)
    keyring_value = _safe_get_password(keyring_backend, keyring_name)
    if keyring_value:
        return keyring_value, CredentialProvenance(CredentialLayer.KEYRING, keyring_name)
    return None, CredentialProvenance(CredentialLayer.MISSING, env_name)


def resolve_shared_secret_with_provenance(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    dotenv_values: Mapping[str, str] | None = None,
) -> tuple[str | None, CredentialProvenance]:
    if dotenv_values is None:  # a launch passes the one reading it validated (#686)
        dotenv_values = _parse_env_gateway_file(config_root / ".env.gateway")
    return _resolve_env_config_keyring(
        environ,
        dotenv_values=dotenv_values,
        env_name="OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
        keyring_name=_KEY_SHARED_SECRET,
        keyring_backend=keyring_backend,
    )


def resolve_shared_secret(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    dotenv_values: Mapping[str, str] | None = None,
) -> str | None:
    value, _provenance = resolve_shared_secret_with_provenance(
        environ,
        config_root=config_root,
        keyring_backend=keyring_backend,
        dotenv_values=dotenv_values,
    )
    return value


_LAYER_WORDS = {
    CredentialLayer.ENVIRONMENT: "the environment",
    CredentialLayer.CONFIG_FILE: ".env.gateway",
    CredentialLayer.KEYRING: "the OS keychain",
}


def _provider_error(layer: CredentialLayer) -> ProviderCredentialConfigurationError:
    # #669: never echo the value; an API key pasted into the provider variable would reach stderr and the IDE's log.
    suffix = " Run `optimus-agent --setup` to choose a supported provider." if layer is CredentialLayer.KEYRING else ""
    return ProviderCredentialConfigurationError(
        f"optimus-agent: OPTIMUS_LOCAL_GATEWAY_PROVIDER from {_LAYER_WORDS.get(layer, 'configuration')} is not a "
        f"supported provider; set it to openrouter (the local Gateway supports OpenRouter only).{suffix}"
    )


def resolve_provider_credentials(
    environ: Mapping[str, str],
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    dotenv_values: Mapping[str, str] | None = None,
) -> ProviderCredentialResolution:
    if dotenv_values is None:  # a launch passes the one reading it validated (#686)
        dotenv_values = _parse_env_gateway_file(config_root / ".env.gateway")
    provider_raw, provider_provenance = _resolve_env_config_keyring(
        environ,
        dotenv_values=dotenv_values,
        env_name="OPTIMUS_LOCAL_GATEWAY_PROVIDER",
        keyring_name=_KEY_MODEL_PROVIDER,
        keyring_backend=keyring_backend,
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
        raise _provider_error(provider_provenance.layer)
    expected_key_name = "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY"
    api_key, api_key_provenance = _resolve_env_config_keyring(
        environ,
        dotenv_values=dotenv_values,
        env_name=expected_key_name,
        keyring_name=_KEY_MODEL_PROVIDER_API_KEY,
        keyring_backend=keyring_backend,
    )
    warnings: list[str] = []
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


def _store_entries(keyring_backend: Any, entries: tuple[tuple[str, str], ...]) -> str | None:
    """Write each entry, then read each back. None when all are stored; otherwise a value-free account (lookup names and
    exception classes only) of where it stopped. Nothing is rolled back: deleting through a store that just failed can
    fail too and cannot restore what an overwrite replaced; every entry is openrouter-paired, so none mismatches."""
    names = [key for key, _ in entries]
    for index, (key, value) in enumerate(entries):
        try:
            keyring_backend.set_password(_KEYRING_SERVICE, key, value)
        except Exception as exc:  # noqa: BLE001 - reported by class only; its text may carry the value
            return (f"OS keychain entries written, not verified: {', '.join(names[:index]) or 'none'}; unconfirmed: {key} "
                    f"({type(exc).__name__}; it may or may not be stored); not written: {', '.join(names[index + 1:]) or 'none'}.")
    for index, (key, value) in enumerate(entries):
        try:
            stored = keyring_backend.get_password(_KEYRING_SERVICE, key) == value
            why = "did not read back"
        except Exception as exc:  # noqa: BLE001 - reported by class only
            stored, why = False, type(exc).__name__
        if not stored:  # e.g. keyring's null backend accepts writes and keeps nothing
            return (f"OS keychain entries written and confirmed: {', '.join(names[:index]) or 'none'}; "
                    f"unconfirmed: {key} ({why}); not checked: {', '.join(names[index + 1:]) or 'none'}.")
    return None


def run_setup_wizard(
    *,
    config_root: Path,
    keyring_backend: Any = keyring,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    print_fn: Callable[..., None] = print,
) -> int:
    provider = _DEFAULT_PROVIDER

    try:
        existing_api_key = _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
    except CredentialStoreUnavailable as exc:
        print_fn(f"{exc.user_message} Nothing was changed. Use .env.gateway instead (see .env.gateway.example).")
        return 2
    if existing_api_key:
        answer = input_fn("A provider key is already stored. Overwrite? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print_fn("Setup cancelled; existing credentials unchanged.")
            return 1

    api_key = getpass_fn("OpenRouter API key: ").strip()
    if not api_key:
        print_fn("No API key entered; aborting setup.")
        return 1

    shared_secret = secrets.token_urlsafe(32)

    entries = ((_KEY_MODEL_PROVIDER, provider), (_KEY_MODEL_PROVIDER_API_KEY, api_key), (_KEY_SHARED_SECRET, shared_secret))
    incomplete = _store_entries(keyring_backend, entries)
    if incomplete is not None:
        print_fn(f"Setup is incomplete. {incomplete} Run setup again, or use .env.gateway instead (see .env.gateway.example).")
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
