from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from optimus_security.launch_manifest import resolve_effective_base_url

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_GATEWAY_PROVIDER = "openrouter"
_GATEWAY_TOOL_ENV_PREFIX = "OPTIMUS_GATEWAY_"


@dataclass(frozen=True)
class GatewayServiceConfig:
    bind_host: str
    bind_port: int
    shared_secret: str
    provider: str
    provider_api_key: str
    base_url: str | None = None
    tavily_api_key: str | None = None
    tavily_base_url: str | None = None
    tool_allowed_domains: tuple[str, ...] = ()
    tool_redis_url: str | None = None
    osv_base_url: str | None = None
    osv_api_key: str | None = None
    pypi_base_url: str | None = None
    npm_base_url: str | None = None
    maven_base_url: str | None = None
    tool_max_calls_per_tool: int = 5
    otlp_endpoint: str | None = None

    def __post_init__(self) -> None:
        if self.bind_host.lower() not in _LOOPBACK_HOSTS:
            raise ValueError(f"bind host must be loopback, got {self.bind_host!r}")
        if not self.shared_secret.strip():
            raise ValueError("shared_secret is required")
        if self.provider != _GATEWAY_PROVIDER:
            raise ValueError(f"provider must be {_GATEWAY_PROVIDER!r}, got {self.provider!r}")
        if not self.provider_api_key.strip():
            raise ValueError("provider_api_key is required")
        if not (self.base_url or "").strip():
            raise ValueError(f"base_url is required for provider {self.provider!r}")
        if self.tool_max_calls_per_tool <= 0:
            raise ValueError("tool_max_calls_per_tool must be positive")

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        bind_host: str,
        bind_port: int,
    ) -> GatewayServiceConfig:
        """Build config from Gateway and tool env plus EXPLICIT bind values.

        Plan 9.96, Task 5 Step 4: bind_host/bind_port are never read from
        OPTIMUS_LOCAL_GATEWAY_BIND_HOST/PORT — the standalone entrypoint no
        longer trusts those inherited names at all. The authorized parent
        (or the operator via an explicit --bind-host/--port CLI argument)
        supplies bind_host/bind_port directly; this closes the standalone
        bind seam. Provider/credential fields still come from `environ`
        because that mapping is the authorized parent's explicit child
        environment construction, not ambient inherited state.

        Gateway-only tool variables include ``TAVILY_API_KEY`` and the
        ``OPTIMUS_GATEWAY_*`` tool configuration variables.
        """
        env = os.environ if environ is None else environ
        provider = env.get("OPTIMUS_LOCAL_GATEWAY_PROVIDER", _GATEWAY_PROVIDER).strip().lower()
        if provider != _GATEWAY_PROVIDER:
            raise ValueError(f"provider must be {_GATEWAY_PROVIDER!r}, got {provider!r}")

        base_url = env.get("OPTIMUS_LOCAL_GATEWAY_BASE_URL", "").strip()
        provider_api_key = _required_env(env, "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY")
        # Single shared resolver (optimus_security.launch_manifest) — the
        # parent side (ProviderSecrets / resolve_provider_credentials) calls
        # this exact function too, so an omitted OPTIMUS_LOCAL_GATEWAY_BASE_URL
        # resolves to the SAME concrete value on both sides.
        resolved_base_url = resolve_effective_base_url(provider=provider, base_url=base_url or None)
        allowed_domains = tuple(
            domain.strip()
            for domain in env.get(_GATEWAY_TOOL_ENV_PREFIX + "TOOL_ALLOWED_DOMAINS", "").split(",")
            if domain.strip()
        )
        max_calls_name = _GATEWAY_TOOL_ENV_PREFIX + "TOOL_MAX_CALLS_PER_TOOL"
        max_calls_raw = env.get(max_calls_name, "5").strip()
        try:
            max_calls = int(max_calls_raw)
        except ValueError as exc:
            raise ValueError(f"{max_calls_name} must be an integer") from exc

        return cls(
            bind_host=bind_host,
            bind_port=bind_port,
            shared_secret=_required_env(env, "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"),
            provider=provider,
            provider_api_key=provider_api_key,
            base_url=resolved_base_url,
            tavily_api_key=_optional_env(env, "TAVILY_API_KEY"),
            tavily_base_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "TAVILY_BASE_URL"),
            tool_allowed_domains=allowed_domains,
            tool_redis_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "TOOL_REDIS_URL"),
            osv_base_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "OSV_BASE_URL"),
            osv_api_key=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "OSV_API_KEY"),
            pypi_base_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "PYPI_BASE_URL"),
            npm_base_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "NPM_BASE_URL"),
            maven_base_url=_optional_env(env, _GATEWAY_TOOL_ENV_PREFIX + "MAVEN_BASE_URL"),
            tool_max_calls_per_tool=max_calls,
            # Plan 11.5, Task 4: standard (non-`OPTIMUS_LOCAL_GATEWAY_`-prefixed) OTel
            # env var, read only on the Gateway-child side. The agent-side
            # `OptimusGatewaySettings` never reads or forwards this variable — the
            # agent receives no OTLP/Phoenix endpoint or credential.
            otlp_endpoint=_optional_env(env, "OTEL_EXPORTER_OTLP_ENDPOINT"),
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


def _optional_env(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


# --- Plan 11.2 (P11-FEAT-GATEWAY-TOOLS): Gateway-owned tool taxonomy --------
#
# These are Gateway-local equivalents of the shared wire values defined in the
# agent-side ``optimus.gateway.tool_models`` / ``optimus.tools.policy``
# modules. ``optimus_gateway`` must remain independently deployable with zero
# ``optimus.*`` imports, so the enum members are duplicated here rather than
# imported; the string values are kept identical so requests/responses stay
# wire-compatible with the agent-side contracts.


class ToolClass(StrEnum):
    WEB_SEARCH = "web_search"
    WEB_EXTRACT = "web_extract"
    PACKAGE_AND_ADVISORY_METADATA = "package_and_advisory_metadata"


class ToolPolicySignal(StrEnum):
    USER_REQUESTED_EXTERNAL_FACT = "USER_REQUESTED_EXTERNAL_FACT"
    CURRENT_OR_LATEST_FACT = "CURRENT_OR_LATEST_FACT"
    API_OR_FRAMEWORK_FACT_NOT_IN_REPO = "API_OR_FRAMEWORK_FACT_NOT_IN_REPO"
    DEPENDENCY_VERSION_CHECK = "DEPENDENCY_VERSION_CHECK"
    SECURITY_OR_CVE_CHECK = "SECURITY_OR_CVE_CHECK"
    APPROVED_SEARCH_RESULT_PROVENANCE = "APPROVED_SEARCH_RESULT_PROVENANCE"


@dataclass(frozen=True)
class GatewayToolContext:
    """Authenticated, server-resolved request context for a Gateway tool call.

    This is the Gateway's own resolved context, built from ``authenticated_subject``
    (the bearer-authenticated caller) plus the caller-supplied transport metadata.
    The transport metadata is never treated as an authorization decision by itself.
    """

    run_id: str
    authenticated_subject: str
    session_id: str | None = None
    execution_mode: str = ""
    org_id: str | None = None
    project_id: str | None = None
    model: str | None = None
