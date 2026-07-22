"""Canonical launch-variable policy registry and immutable environment snapshot.

Plan 9.96, Task 1: Every concrete source-referenced OPTIMUS_* name, the
OPTIMUS_LOCAL_GATEWAY_ prefix, and every provider-key name has one tier, parser,
display rule, approval rule, and propagation rule. A new unclassified name fails
tests and launch.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from urllib.parse import urlparse

from optimus.config.gateway import LOCAL_PROVIDER_KEY_NAMES
from optimus_security.sanitization import mask_uri_userinfo

# --- Enumerations ---


class LaunchVariableTier(StrEnum):
    """Classification tier for launch environment variables."""

    SECRET = "secret"
    SECURITY = "security"
    MONOTONIC_LIMIT = "monotonic_limit"
    OPERATIONAL = "operational"
    INTERNAL_ONLY = "internal_only"


class PropagationTarget(StrEnum):
    """Where a classified variable may be propagated after authorization."""

    PARENT_ONLY = "parent_only"
    AGENT_CHILD = "agent_child"
    GATEWAY_CHILD = "gateway_child"
    REVIEWED_INTERNAL = "reviewed_internal"
    NEVER = "never"


# --- Policy dataclass ---


@dataclass(frozen=True)
class LaunchVariablePolicy:
    """One classification entry for a named launch variable."""

    name: str
    tier: LaunchVariableTier
    propagation: frozenset[PropagationTarget]
    parser: Callable[[str], object]
    display: Callable[[str], str]
    approval: str
    uri_userinfo: bool


# --- Error type ---


@dataclass(frozen=True)
class LaunchPolicyError(ValueError):
    """Raised when a variable cannot be classified or validated."""

    code: str
    variable_name: str | None = None

    def __str__(self) -> str:
        if self.variable_name:
            return f"{self.code}: {self.variable_name}"
        return self.code


# --- Defaults ---

DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")
DEFAULT_MAX_PLANNING_TURNS = 3

# --- Prefix constant ---

LOCAL_GATEWAY_PREFIX = "OPTIMUS_LOCAL_GATEWAY_"


# --- Parsers ---


def _parse_secret(value: str) -> str:
    """Secret values are opaque strings; presence is sufficient."""
    if not value.strip():
        raise ValueError("Secret value must not be empty")
    return value.strip()


def _parse_url(value: str) -> str:
    """Parse and validate a URL value.

    Error messages must not include the raw value — URI user information
    is a secret subfield per the Fixed Launch-Variable Policy Table.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("URL must not be empty")
    parsed = urlparse(stripped)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid URL: missing scheme or host")
    return stripped


def _parse_redis_url(value: str) -> str:
    """Parse Redis URL — may contain user information (secret subfield).

    Error messages must not include the raw value.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Redis URL must not be empty")
    parsed = urlparse(stripped)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("Invalid Redis URL: missing scheme or host")
    return stripped


def _parse_bool_like(value: str) -> bool:
    """Parse boolean-like value (true/false/1/0/yes/no)."""
    stripped = value.strip().lower()
    if stripped in {"1", "true", "yes", "on"}:
        return True
    if stripped in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def _parse_origins(value: str) -> tuple[str, ...]:
    """Parse comma-separated origin URLs."""
    if not value.strip():
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _parse_provider(value: str) -> str:
    """Parse provider name."""
    stripped = value.strip().lower()
    if not stripped:
        raise ValueError("Provider must not be empty")
    return stripped


def _parse_base_url(value: str) -> str:
    """Parse base URL for provider."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("Base URL must not be empty")
    return stripped


def _parse_config_root(value: str) -> str:
    """Parse config root path."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("Config root must not be empty")
    return stripped


def _parse_monotonic_cost(value: str) -> Decimal:
    """Parse and validate a monetary cost ceiling.

    Must be a positive finite Decimal. Zero and negative values are rejected.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Cost value must not be empty")
    try:
        result = Decimal(stripped)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid cost value: {stripped!r}") from exc
    if not result.is_finite():
        raise ValueError(f"Cost must be finite, got: {stripped!r}")
    if result <= 0:
        raise ValueError(f"Cost must be positive, got: {stripped!r}")
    return result


def _parse_monotonic_turns(value: str) -> int:
    """Parse and validate a planning-turn limit.

    Must be a positive integer >= 1.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Turn limit must not be empty")
    # Reject floats explicitly.
    if "." in stripped:
        raise ValueError(f"Turn limit must be an integer, got: {stripped!r}")
    try:
        result = int(stripped)
    except ValueError as exc:
        raise ValueError(f"Invalid turn limit: {stripped!r}") from exc
    if result < 1:
        raise ValueError(f"Turn limit must be >= 1, got: {result}")
    return result


_MODEL_USERINFO_RE = re.compile(r"^[^/\s@]+:[^/\s@]+@")


def _model_value_has_userinfo(value: str) -> bool:
    """Detect a userinfo/credential-shaped segment in a model value.

    Two independent checks, because neither alone covers both shapes:

    1. `_MODEL_USERINFO_RE` catches the SCHEMELESS leading form
       ("user:pass@host", no "scheme://" prefix) — this is the shape
       urlparse() cannot detect at all (with no scheme, urlparse treats the
       whole string as an opaque path and never populates
       .username/.password), and it's exactly the shape the existing
       optimus_security.sanitization._URL_USERINFO_RE would miss too (that
       regex requires a scheme-colon-slash-slash prefix).
    2. `urlparse(value).username/.password` catches the SCHEMED form
       ("scheme://user:pass@host") — the regex above deliberately excludes
       "/" from both sides of the ":", so it does not match past a "://".
    """
    if _MODEL_USERINFO_RE.match(value):
        return True
    parsed = urlparse(value)
    return bool(parsed.scheme) and (parsed.username is not None or parsed.password is not None)


def _parse_model(value: str) -> str:
    """Parse model name — operational, ceremony-free under bounded conditions.

    Frozen contract, Tier 4 condition 4: "The model value is logged only as
    non-secret configuration and cannot contain URI user information or
    credentials." Rejects a userinfo-shaped segment BEFORE the value is ever
    displayed (_display_literal echoes it verbatim) or stored in
    model_observation/the approval record/the audit event.
    """
    stripped = value.strip()
    if not stripped:
        raise ValueError("Model name must not be empty")
    if _model_value_has_userinfo(stripped):
        raise ValueError("Model name must not contain URI user information or credentials")
    return stripped


def _parse_internal_only(value: str) -> str:
    """Internal-only values are never consumed from the inherited environment."""
    return value.strip()


# --- Display functions ---


def _display_redacted(_value: str) -> str:
    """Secret values are never displayed."""
    return "**********"


def _display_literal(value: str) -> str:
    """Non-secret values display literally."""
    return value.strip()


def _display_uri_masked(value: str) -> str:
    """URI values mask user information but show structure."""
    return mask_uri_userinfo(value)


def _display_internal(_value: str) -> str:
    """Internal-only values should not reach display; show placeholder."""
    return "[internal-only]"


# --- The canonical five-tier policy table ---
# Exactly matches the Fixed Launch-Variable Policy Table in Plan 9.96.

_POLICIES: dict[str, LaunchVariablePolicy] = {}


def _register(
    name: str,
    *,
    tier: LaunchVariableTier,
    propagation: frozenset[PropagationTarget],
    parser: Callable[[str], object],
    display: Callable[[str], str],
    approval: str,
    uri_userinfo: bool,
) -> None:
    _POLICIES[name] = LaunchVariablePolicy(
        name=name,
        tier=tier,
        propagation=propagation,
        parser=parser,
        display=display,
        approval=approval,
        uri_userinfo=uri_userinfo,
    )


# --- Tier: Secret (provider keys) ---
# "only the selected provider credential reaches the Gateway child"
for _provider_key in sorted(LOCAL_PROVIDER_KEY_NAMES):
    _register(
        _provider_key,
        tier=LaunchVariableTier.SECRET,
        propagation=frozenset({PropagationTarget.GATEWAY_CHILD}),
        parser=_parse_secret,
        display=_display_redacted,
        approval="exact_hmac",
        uri_userinfo=False,
    )

# --- Tier: Secret (OPTIMUS_API_KEY) ---
# "agent child as the one-key contract"
_register(
    "OPTIMUS_API_KEY",
    tier=LaunchVariableTier.SECRET,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_secret,
    display=_display_redacted,
    approval="exact_hmac",
    uri_userinfo=False,
)

# --- Tier: Secret (Gateway-internal credentials) ---
# "Gateway child only; shared secret is projected to agent as OPTIMUS_API_KEY"
_register(
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY",
    tier=LaunchVariableTier.SECRET,
    propagation=frozenset({PropagationTarget.GATEWAY_CHILD}),
    parser=_parse_secret,
    display=_display_redacted,
    approval="exact_hmac",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET",
    tier=LaunchVariableTier.SECRET,
    propagation=frozenset({PropagationTarget.GATEWAY_CHILD}),
    parser=_parse_secret,
    display=_display_redacted,
    approval="exact_hmac",
    uri_userinfo=False,
)

# --- Tier: Security ---
# "exact approval; URI user information is a secret subfield"
_register(
    "OPTIMUS_GATEWAY_URL",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_url,
    display=_display_uri_masked,
    approval="exact_hmac_uri",
    uri_userinfo=True,
)
_register(
    "OPTIMUS_REDIS_URL",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_redis_url,
    display=_display_uri_masked,
    approval="exact_hmac_uri",
    uri_userinfo=True,
)
_register(
    "OPTIMUS_CONFIG_ROOT",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.PARENT_ONLY}),
    parser=_parse_config_root,
    display=_display_literal,
    approval="exact_literal",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_PRODUCTION_MODE",
    tier=LaunchVariableTier.SECURITY,
    # Plan 9.96, Task 5 review: GATEWAY_CHILD was removed from this
    # propagation set. optimus_gateway/models.py's GatewayServiceConfig.from_env()
    # has no code path that reads OPTIMUS_PRODUCTION_MODE at all, and Task 5
    # Step 3's Gateway-child projection list ("provider, one provider key,
    # base URL when applicable, shared secret, and code-derived loopback
    # bind values") does not include it either — only the agent-child list
    # mentions "production/origin settings when applicable." Propagating a
    # value with zero consumers on the Gateway side violates least privilege
    # and was a registry error, not an intentional dual-propagation design.
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_bool_like,
    display=_display_literal,
    approval="exact_literal",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_EXTRA_GATEWAY_ORIGINS",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_origins,
    display=_display_literal,
    approval="exact_literal",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_LOCAL_GATEWAY_PROVIDER",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.GATEWAY_CHILD}),
    parser=_parse_provider,
    display=_display_literal,
    approval="exact_literal",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_LOCAL_GATEWAY_BASE_URL",
    tier=LaunchVariableTier.SECURITY,
    propagation=frozenset({PropagationTarget.GATEWAY_CHILD}),
    parser=_parse_base_url,
    display=_display_uri_masked,
    approval="exact_hmac_uri",
    uri_userinfo=True,
)

# --- Tier: Monotonic Limit ---
# "tightening/equal allowed; loosening requires exact approval"
_register(
    "OPTIMUS_LIVE_MAX_COST_USD",
    tier=LaunchVariableTier.MONOTONIC_LIMIT,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_monotonic_cost,
    display=_display_literal,
    approval="monotonic_tighten_or_exact",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_MAX_PLANNING_TURNS",
    tier=LaunchVariableTier.MONOTONIC_LIMIT,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_monotonic_turns,
    display=_display_literal,
    approval="monotonic_tighten_or_exact",
    uri_userinfo=False,
)

# --- Tier: Operational ---
# "allowed only under the bounded-model predicate"
_register(
    "OPTIMUS_AGENT_MODEL",
    tier=LaunchVariableTier.OPERATIONAL,
    propagation=frozenset({PropagationTarget.AGENT_CHILD}),
    parser=_parse_model,
    display=_display_literal,
    approval="bounded_model_predicate",
    uri_userinfo=False,
)

# --- Tier: Internal-only ---
# "reject when inherited; code-derived arguments or in-memory context only after authorization"
_register(
    "OPTIMUS_LOCAL_GATEWAY_BIND_HOST",
    tier=LaunchVariableTier.INTERNAL_ONLY,
    propagation=frozenset({PropagationTarget.NEVER}),
    parser=_parse_internal_only,
    display=_display_internal,
    approval="reject_inherited",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_LOCAL_GATEWAY_PORT",
    tier=LaunchVariableTier.INTERNAL_ONLY,
    propagation=frozenset({PropagationTarget.NEVER}),
    parser=_parse_internal_only,
    display=_display_internal,
    approval="reject_inherited",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_ACP_DEBUG_TRACE",
    tier=LaunchVariableTier.INTERNAL_ONLY,
    propagation=frozenset({PropagationTarget.NEVER}),
    parser=_parse_internal_only,
    display=_display_internal,
    approval="reject_inherited",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_ACP_DEBUG_LOG",
    tier=LaunchVariableTier.INTERNAL_ONLY,
    propagation=frozenset({PropagationTarget.NEVER}),
    parser=_parse_internal_only,
    display=_display_internal,
    approval="reject_inherited",
    uri_userinfo=False,
)
_register(
    "OPTIMUS_ACP_PROVENANCE_ROOT",
    tier=LaunchVariableTier.INTERNAL_ONLY,
    propagation=frozenset({PropagationTarget.NEVER}),
    parser=_parse_internal_only,
    display=_display_internal,
    approval="reject_inherited",
    uri_userinfo=False,
)

# --- Exported immutable registry ---

LAUNCH_VARIABLE_POLICIES: Mapping[str, LaunchVariablePolicy] = MappingProxyType(_POLICIES)


# --- Classification function ---


def classify_variable(name: str) -> LaunchVariablePolicy:
    """Look up the policy for a variable name.

    Raises LaunchPolicyError with code 'LAUNCH_VARIABLE_UNCLASSIFIED' if the name
    is unknown. For the OPTIMUS_LOCAL_GATEWAY_ prefix, any non-enumerated member
    also fails closed.
    """
    if name in LAUNCH_VARIABLE_POLICIES:
        return LAUNCH_VARIABLE_POLICIES[name]

    # Prefix rule: any non-enumerated OPTIMUS_LOCAL_GATEWAY_* name fails closed.
    if name.startswith(LOCAL_GATEWAY_PREFIX):
        raise LaunchPolicyError(
            code="LAUNCH_VARIABLE_UNCLASSIFIED",
            variable_name=name,
        )

    # Any other OPTIMUS_* name not in the registry fails closed.
    if name.startswith("OPTIMUS_"):
        raise LaunchPolicyError(
            code="LAUNCH_VARIABLE_UNCLASSIFIED",
            variable_name=name,
        )

    # Non-OPTIMUS names are not classified by this registry.
    raise LaunchPolicyError(
        code="LAUNCH_VARIABLE_NOT_OPTIMUS",
        variable_name=name,
    )


# --- Immutable environment snapshot ---


@dataclass(frozen=True)
class LaunchEnvironmentSnapshot:
    """Immutable capture of the inherited environment at process startup.

    Captured once before any Optimus config/path helper reads it.
    Gated code receives this snapshot and performs no later os.environ reads.
    """

    values: Mapping[str, str]

    @classmethod
    def capture(cls, environ: Mapping[str, str]) -> LaunchEnvironmentSnapshot:
        """Capture an immutable copy of the environment.

        The returned snapshot's values are a read-only MappingProxy over a
        private dict copy — modifications to the source environ after capture
        have no effect, and the snapshot itself cannot be mutated.
        """
        frozen_copy = MappingProxyType(dict(environ))
        return cls(values=frozen_copy)
