from __future__ import annotations

import getpass
import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import keyring

_KEYRING_SERVICE = "optimus-cost-agent"
_KEY_MODEL_PROVIDER = "model_provider"
_KEY_MODEL_PROVIDER_API_KEY = "model_provider_api_key"
_KEY_SHARED_SECRET = "local_gateway_shared_secret"

_SUPPORTED_PROVIDERS = ("openai", "openrouter", "anthropic")
_DEFAULT_PROVIDER = "openrouter"

_ENV_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class ProviderSecrets:
    provider: str  # "openai" | "openrouter" | "anthropic"
    model_provider_api_key: str
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
    project_root: Path,
    keyring_backend: Any = keyring,
) -> str | None:
    env_value = environ.get("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", "").strip()
    if env_value:
        return env_value
    dotenv_value = _parse_env_gateway_file(project_root / ".env.gateway").get(
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", ""
    ).strip()
    if dotenv_value:
        return dotenv_value
    return _safe_get_password(keyring_backend, _KEY_SHARED_SECRET)


def resolve_provider_secrets(
    environ: Mapping[str, str],
    *,
    project_root: Path,
    keyring_backend: Any = keyring,
) -> ProviderSecrets | None:
    dotenv_values = _parse_env_gateway_file(project_root / ".env.gateway")

    # Default to "openrouter" when unconfigured anywhere — matches GatewayServiceConfig.from_env()'s
    # own default (models.py:40). Only a missing/unresolvable *API key* is a hard failure below;
    # the provider name alone should never block resolution when the gateway itself wouldn't block.
    provider = (
        environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
        or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "").strip()
        or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER)
        or _DEFAULT_PROVIDER
    ).lower()
    if provider not in _SUPPORTED_PROVIDERS:
        return None

    if provider == "anthropic":
        api_key = (
            environ.get("ANTHROPIC_API_KEY", "").strip()
            or dotenv_values.get("ANTHROPIC_API_KEY", "").strip()
            or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
            or ""
        )
    else:
        api_key = (
            environ.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
            or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", "").strip()
            or _safe_get_password(keyring_backend, _KEY_MODEL_PROVIDER_API_KEY)
            or ""
        )
    if not api_key:
        return None

    # Not a secret — no keyring lookup, matching the design that keyring is reserved for secrets
    # only (see Task 1's keychain-schema note). Left as None if unset anywhere, letting
    # GatewayServiceConfig.from_env() apply its own per-provider default base URL.
    base_url = (
        environ.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        or dotenv_values.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        or None
    )
    return ProviderSecrets(provider=provider, model_provider_api_key=api_key, base_url=base_url)


def run_setup_wizard(
    *,
    project_root: Path,
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
    if (project_root / ".env.gateway").is_file():
        print_fn(
            "Note: .env.gateway also exists in this project; explicit env vars and that file "
            "take precedence over the keychain values just stored."
        )
    return 0
