from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any, Mapping

from optimus_security.launch_manifest import resolve_effective_base_url

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SUPPORTED_PROVIDERS = frozenset({"openai", "openrouter", "anthropic"})


@dataclass(frozen=True)
class GatewayServiceConfig:
    bind_host: str
    bind_port: int
    shared_secret: str
    provider: str
    provider_api_key: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        if self.bind_host.lower() not in _LOOPBACK_HOSTS:
            raise ValueError(f"bind host must be loopback, got {self.bind_host!r}")
        if not self.shared_secret.strip():
            raise ValueError("shared_secret is required")
        if self.provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {self.provider}")
        if not self.provider_api_key.strip():
            raise ValueError("provider_api_key is required")
        if self.provider != "anthropic" and not (self.base_url or "").strip():
            raise ValueError(f"base_url is required for provider {self.provider!r}")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        bind_host: str,
        bind_port: int,
    ) -> GatewayServiceConfig:
        """Build config from credential/provider env plus EXPLICIT bind values.

        Plan 9.96, Task 5 Step 4: bind_host/bind_port are never read from
        OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT — the standalone entrypoint no
        longer trusts those inherited names at all. The authorized parent
        (or the operator via an explicit --bind-host/--port CLI argument)
        supplies bind_host/bind_port directly; this closes the standalone
        bind seam. Provider/credential fields still come from `environ`
        because that mapping is the authorized parent's explicit child
        environment construction, not ambient inherited state.
        """
        env = os.environ if environ is None else environ
        provider = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", "openrouter").strip().lower()
        if provider not in _SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider: {provider}")

        base_url = env.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        if provider == "anthropic":
            provider_api_key = _required_env(env, "ANTHROPIC_API_KEY")
        else:
            provider_api_key = _required_env(env, "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")
        # Single shared resolver (optimus_security.launch_manifest) — the
        # parent side (ProviderSecrets / resolve_provider_credentials) calls
        # this exact function too, so an omitted OPTIMUS_LOCAL_GATEWAY_BASE_URL
        # resolves to the SAME concrete value on both sides.
        resolved_base_url = resolve_effective_base_url(provider=provider, base_url=base_url or None)

        return cls(
            bind_host=bind_host,
            bind_port=bind_port,
            shared_secret=_required_env(env, "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"),
            provider=provider,
            provider_api_key=provider_api_key,
            base_url=resolved_base_url,
        )


class ModelRequestValidationError(ValueError):
    """Strict known-field validation failure for model route envelopes."""


def authorize_bearer(*, authorization_header: str | None, shared_secret: str) -> bool:
    if authorization_header is None:
        return False
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        return False
    token = authorization_header[len(prefix) :].strip()
    return secrets.compare_digest(token, shared_secret)


def validate_responses_envelope(
    request_body: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any] | None]:
    model, metadata = _validate_common_model_fields(request_body)
    if "messages" in request_body:
        raise ModelRequestValidationError("messages is not allowed on /v1/responses")
    input_text = request_body.get("input")
    if not isinstance(input_text, str) or not input_text.strip():
        raise ModelRequestValidationError("input is required")
    return model, input_text, metadata


def validate_chat_completions_envelope(
    request_body: Mapping[str, Any],
) -> tuple[str, list[Any], dict[str, Any] | None]:
    model, metadata = _validate_common_model_fields(request_body)
    if "input" in request_body:
        raise ModelRequestValidationError("input is not allowed on /v1/chat/completions")
    messages = request_body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ModelRequestValidationError("messages is required")
    return model, messages, metadata


def flatten_messages_to_input_text(messages: list[Any]) -> str:
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, str) and part.strip():
                    parts.append(part.strip())
                elif isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
    flattened = "\n".join(parts).strip()
    if not flattened:
        raise ModelRequestValidationError("messages must contain text content")
    return flattened


def _validate_common_model_fields(
    request_body: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    model = request_body.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ModelRequestValidationError("model is required")
    metadata = request_body.get("metadata")
    if metadata is None:
        return model.strip(), None
    if not isinstance(metadata, dict):
        raise ModelRequestValidationError("metadata must be a JSON object")
    return model.strip(), metadata


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value
