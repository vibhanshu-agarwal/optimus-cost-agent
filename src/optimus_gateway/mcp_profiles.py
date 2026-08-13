"""Gateway-owned static MCP profile definitions and lifecycle admission."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Mapping

from optimus_gateway.mcp_models import MCPCallRequest, MCPDiscoverRequest, parse_namespaced_tool_name

_PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_FIELDS = frozenset(
    {
        "oauth",
        "client_id",
        "client_secret",
        "access_token",
        "refresh_token",
        "authorization_url",
        "token_url",
        "scope",
        "catalog_url",
        "autoload",
        "install",
        "update",
        "credential",
        "password",
        "bearer",
        "credential_fingerprint",
        "secret_fingerprint",
    }
)


class MCPProfileDefinitionError(ValueError):
    """Raised when operator-owned profile metadata is malformed or out of scope."""


class MCPProfileState(StrEnum):
    PENDING_REGISTRATION = "PENDING_REGISTRATION"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class MCPResourceLimits:
    max_pages: int = 100
    max_tools: int = 1000
    max_descriptor_bytes: int = 1_048_576
    max_elapsed_seconds: float = 30.0
    max_call_duration_seconds: float = 30.0
    max_result_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if any(value <= 0 for value in (self.max_pages, self.max_tools, self.max_descriptor_bytes, self.max_result_bytes)):
            raise MCPProfileDefinitionError("resource limits must be positive")
        if self.max_elapsed_seconds <= 0 or self.max_call_duration_seconds <= 0:
            raise MCPProfileDefinitionError("resource time limits must be positive")


@dataclass(frozen=True)
class MCPAttributionPolicy:
    allow_unattributed_spend: bool = False
    declared_free: bool = False


@dataclass(frozen=True)
class MCPHTTPProfile:
    endpoint: str
    allow_insecure_loopback: bool = False
    auth_mode: Literal["bearer", "none"] = "bearer"

    def __post_init__(self) -> None:
        if not self.endpoint or self.endpoint != self.endpoint.strip():
            raise MCPProfileDefinitionError("HTTP endpoint must be non-empty")
        if not self.endpoint.startswith(("https://", "http://")):
            raise MCPProfileDefinitionError("HTTP endpoint must use http or https")
        if self.auth_mode not in ("bearer", "none"):
            raise MCPProfileDefinitionError("HTTP auth_mode must be 'bearer' or 'none'")


@dataclass(frozen=True)
class MCPStdioProfile:
    image: str
    command: str
    arguments: tuple[str, ...] = ()
    environment_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if "@sha256:" not in self.image:
            raise MCPProfileDefinitionError("stdio image must be digest pinned")
        if not self.command or self.command != self.command.strip():
            raise MCPProfileDefinitionError("stdio command must be non-empty")


@dataclass(frozen=True)
class MCPProfile:
    profile_id: str
    revision: str
    state: MCPProfileState
    transport: Literal["http", "stdio"]
    credential_ref: str | None
    upstream_allowlist: tuple[str, ...]
    manifest_hash: str | None
    limits: MCPResourceLimits
    attribution_policy: MCPAttributionPolicy
    transport_config: MCPHTTPProfile | MCPStdioProfile

    def __post_init__(self) -> None:
        if not _PROFILE_ID.fullmatch(self.profile_id):
            raise MCPProfileDefinitionError("invalid profile_id")
        if not self.revision or self.revision != self.revision.strip():
            raise MCPProfileDefinitionError("revision must be non-empty")
        object.__setattr__(self, "state", MCPProfileState(self.state))
        if not self.upstream_allowlist or len(set(self.upstream_allowlist)) != len(self.upstream_allowlist):
            raise MCPProfileDefinitionError("upstream_allowlist must be non-empty and unique")
        if any(not name or name != name.strip() for name in self.upstream_allowlist):
            raise MCPProfileDefinitionError("upstream_allowlist entries must be non-empty")
        if self.manifest_hash is not None and _HASH.fullmatch(self.manifest_hash) is None:
            raise MCPProfileDefinitionError("manifest_hash must be a lowercase SHA-256 hex digest")
        if self.transport == "http" and not isinstance(self.transport_config, MCPHTTPProfile):
            raise MCPProfileDefinitionError("HTTP profiles require MCPHTTPProfile")
        if self.transport == "stdio" and not isinstance(self.transport_config, MCPStdioProfile):
            raise MCPProfileDefinitionError("stdio profiles require MCPStdioProfile")
        if self.transport == "http" and self.transport_config.auth_mode == "none":
            if self.credential_ref is not None:
                raise MCPProfileDefinitionError("credential_ref must be None when HTTP auth_mode is none")
        else:
            if not isinstance(self.credential_ref, str) or not self.credential_ref or self.credential_ref != self.credential_ref.strip():
                raise MCPProfileDefinitionError("credential_ref must be non-empty")
            if _HASH.fullmatch(self.credential_ref):
                raise MCPProfileDefinitionError("credential_ref must not be a secret-derived fingerprint")


@dataclass(frozen=True)
class ProfileAdmission:
    accepted: bool
    profile: MCPProfile | None
    disposition: str
    reason: str = ""


class MCPProfileRegistry:
    """In-memory Gateway-owned registry populated only by operator/bootstrap input."""

    def __init__(self, profiles: tuple[MCPProfile, ...] | list[MCPProfile]) -> None:
        self._profiles: dict[str, MCPProfile] = {}
        self._stale_reasons: dict[tuple[str, str], str] = {}
        for profile in profiles:
            if profile.profile_id in self._profiles:
                raise MCPProfileDefinitionError("duplicate profile_id")
            if profile.state != MCPProfileState.PENDING_REGISTRATION:
                raise MCPProfileDefinitionError("static profiles must start pending")
            self._profiles[profile.profile_id] = profile

    @classmethod
    def from_startup_metadata(cls, metadata: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]]) -> MCPProfileRegistry:
        profiles = [profile_from_mapping(item) for item in metadata]
        registry = cls(profiles)
        for profile in profiles:
            if profile.manifest_hash is None:
                raise MCPProfileDefinitionError("startup profile requires manifest_hash")
            registry.activate_from_startup(
                profile_id=profile.profile_id,
                revision=profile.revision,
                manifest_hash=profile.manifest_hash,
            )
        return registry

    @property
    def profiles(self) -> tuple[MCPProfile, ...]:
        return tuple(self._profiles.values())

    def get(self, profile_id: str) -> MCPProfile:
        return self._profiles[profile_id]

    def for_discovery(self, request: MCPDiscoverRequest) -> ProfileAdmission:
        profile = self._profiles.get(request.profile_id)
        if profile is None:
            return self._denied("mcp.profile_not_found")
        if profile.revision != request.profile_revision:
            return self._denied("mcp.profile_revision_mismatch", profile)
        if profile.state == MCPProfileState.DISABLED:
            return self._denied("mcp.profile_disabled", profile)
        if profile.state == MCPProfileState.PENDING_REGISTRATION:
            if request.manifest_hash is not None:
                return self._denied("mcp.registration_binding_unexpected", profile)
            return self._accepted("mcp.profile_registration_allowed", profile)
        if profile.state == MCPProfileState.STALE:
            if request.manifest_hash != profile.manifest_hash:
                return self._denied("mcp.profile_manifest_mismatch", profile)
            return self._accepted("mcp.profile_stale_refresh_allowed", profile)
        if request.manifest_hash != profile.manifest_hash:
            return self._denied("mcp.profile_manifest_mismatch", profile)
        return self._accepted("mcp.profile_refresh_allowed", profile)

    def for_call(self, request: MCPCallRequest) -> ProfileAdmission:
        profile = self._profiles.get(request.profile_id)
        if profile is None:
            return self._denied("mcp.profile_not_found")
        if profile.revision != request.profile_revision:
            return self._denied("mcp.profile_revision_mismatch", profile)
        if profile.state != MCPProfileState.ACTIVE:
            return self._denied("mcp.profile_not_active", profile)
        if request.manifest_hash != profile.manifest_hash:
            return self._denied("mcp.profile_manifest_mismatch", profile)
        _, upstream_tool_name = parse_namespaced_tool_name(
            request.tool_name, expected_profile_id=profile.profile_id
        )
        if upstream_tool_name not in profile.upstream_allowlist:
            return self._denied("mcp.tool_not_allowlisted", profile)
        return self._accepted("mcp.profile_call_allowed", profile)

    def activate_from_startup(self, *, profile_id: str, revision: str, manifest_hash: str) -> MCPProfile:
        profile = self._profiles[profile_id]
        if profile.revision != revision:
            raise MCPProfileDefinitionError("startup revision does not match provisioned profile")
        if _HASH.fullmatch(manifest_hash) is None:
            raise MCPProfileDefinitionError("startup manifest_hash is invalid")
        if profile.state == MCPProfileState.ACTIVE and profile.manifest_hash == manifest_hash:
            return profile
        if profile.state != MCPProfileState.PENDING_REGISTRATION:
            raise MCPProfileDefinitionError("only a pending profile can be startup-activated")
        active = _copy_profile(profile, state=MCPProfileState.ACTIVE, manifest_hash=manifest_hash)
        self._profiles[profile_id] = active
        return active

    def mark_stale(self, *, profile_id: str, revision: str, reason: str) -> None:
        profile = self._profiles[profile_id]
        if profile.revision != revision:
            raise MCPProfileDefinitionError("stale revision does not match provisioned profile")
        if profile.state not in (MCPProfileState.ACTIVE, MCPProfileState.STALE):
            raise MCPProfileDefinitionError("only an active profile can become stale")
        self._profiles[profile_id] = _copy_profile(profile, state=MCPProfileState.STALE)
        self._stale_reasons[(profile_id, revision)] = reason

    def update_profile(self, *, profile_id: str, **changes: object) -> MCPProfile:
        profile = self._profiles[profile_id]
        allowed = {
            "transport",
            "credential_ref",
            "upstream_allowlist",
            "limits",
            "attribution_policy",
            "transport_config",
        }
        if not changes or set(changes) - allowed:
            raise MCPProfileDefinitionError("profile update contains unsupported fields")
        values = {
            "transport": profile.transport,
            "credential_ref": profile.credential_ref,
            "upstream_allowlist": profile.upstream_allowlist,
            "limits": profile.limits,
            "attribution_policy": profile.attribution_policy,
            "transport_config": profile.transport_config,
        }
        values.update(changes)
        replacement = MCPProfile(
            profile_id=profile.profile_id,
            revision=_mint_revision(),
            state=MCPProfileState.PENDING_REGISTRATION,
            manifest_hash=None,
            **values,
        )
        self._profiles[profile_id] = replacement
        return replacement

    def disable(self, *, profile_id: str) -> None:
        profile = self._profiles[profile_id]
        self._profiles[profile_id] = _copy_profile(
            profile, state=MCPProfileState.DISABLED, manifest_hash=None
        )

    def reenable(self, *, profile_id: str) -> MCPProfile:
        profile = self._profiles[profile_id]
        if profile.state != MCPProfileState.DISABLED:
            raise MCPProfileDefinitionError("only a disabled profile can be re-enabled")
        replacement = MCPProfile(
            profile_id=profile.profile_id,
            revision=_mint_revision(),
            state=MCPProfileState.PENDING_REGISTRATION,
            transport=profile.transport,
            credential_ref=profile.credential_ref,
            upstream_allowlist=profile.upstream_allowlist,
            manifest_hash=None,
            limits=profile.limits,
            attribution_policy=profile.attribution_policy,
            transport_config=profile.transport_config,
        )
        self._profiles[profile_id] = replacement
        return replacement

    @staticmethod
    def _accepted(disposition: str, profile: MCPProfile) -> ProfileAdmission:
        return ProfileAdmission(accepted=True, profile=profile, disposition=disposition)

    @staticmethod
    def _denied(disposition: str, profile: MCPProfile | None = None) -> ProfileAdmission:
        return ProfileAdmission(accepted=False, profile=profile, disposition=disposition)


def profile_from_mapping(values: Mapping[str, Any]) -> MCPProfile:
    """Parse only the non-secret, operator-owned startup profile shape."""
    try:
        _reject_forbidden_fields(values)
        allowed = {
            "profile_id",
            "revision",
            "state",
            "transport",
            "credential_ref",
            "upstream_allowlist",
            "manifest_hash",
            "limits",
            "attribution_policy",
            "transport_config",
        }
        unknown = set(values) - allowed
        if unknown:
            raise MCPProfileDefinitionError(f"unsupported profile fields: {sorted(unknown)}")
        transport = values["transport"]
        transport_config_values = values["transport_config"]
        if not isinstance(transport_config_values, Mapping):
            raise MCPProfileDefinitionError("transport_config must be an object")
        if transport == "http":
            transport_config: MCPHTTPProfile | MCPStdioProfile = MCPHTTPProfile(
                endpoint=str(transport_config_values["endpoint"]),
                allow_insecure_loopback=bool(transport_config_values.get("allow_insecure_loopback", False)),
                auth_mode=transport_config_values.get("auth_mode", "bearer"),
            )
        elif transport == "stdio":
            transport_config = MCPStdioProfile(
                image=str(transport_config_values["image"]),
                command=str(transport_config_values["command"]),
                arguments=tuple(transport_config_values.get("arguments", ())),
                environment_names=tuple(transport_config_values.get("environment_names", ())),
            )
        else:
            raise MCPProfileDefinitionError("unsupported MCP transport")
        limits_values = values.get("limits", {})
        attribution_values = values.get("attribution_policy", {})
        if not isinstance(limits_values, Mapping) or not isinstance(attribution_values, Mapping):
            raise MCPProfileDefinitionError("limits and attribution_policy must be objects")
        raw_credential = values.get("credential_ref")
        if isinstance(transport_config, MCPHTTPProfile) and transport_config.auth_mode == "none":
            if raw_credential is not None:
                raise MCPProfileDefinitionError("credential_ref must be None when HTTP auth_mode is none")
            credential_ref: str | None = None
        else:
            if raw_credential is None:
                raise MCPProfileDefinitionError("credential_ref must be non-empty")
            credential_ref = str(raw_credential)
        return MCPProfile(
            profile_id=str(values["profile_id"]),
            revision=str(values["revision"]),
            state=MCPProfileState(values.get("state", MCPProfileState.PENDING_REGISTRATION)),
            transport=transport,
            credential_ref=credential_ref,
            upstream_allowlist=tuple(values["upstream_allowlist"]),
            manifest_hash=values.get("manifest_hash"),
            limits=MCPResourceLimits(**limits_values),
            attribution_policy=MCPAttributionPolicy(**attribution_values),
            transport_config=transport_config,
        )
    except MCPProfileDefinitionError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise MCPProfileDefinitionError("invalid MCP profile definition") from exc


def _reject_forbidden_fields(values: Mapping[str, Any]) -> None:
    for key, value in values.items():
        if str(key).lower() in _FORBIDDEN_FIELDS:
            raise MCPProfileDefinitionError(f"forbidden profile field: {key}")
        if isinstance(value, Mapping):
            _reject_forbidden_fields(value)
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, Mapping):
                    _reject_forbidden_fields(item)


def _copy_profile(profile: MCPProfile, **changes: object) -> MCPProfile:
    values = {
        "profile_id": profile.profile_id,
        "revision": profile.revision,
        "state": profile.state,
        "transport": profile.transport,
        "credential_ref": profile.credential_ref,
        "upstream_allowlist": profile.upstream_allowlist,
        "manifest_hash": profile.manifest_hash,
        "limits": profile.limits,
        "attribution_policy": profile.attribution_policy,
        "transport_config": profile.transport_config,
    }
    values.update(changes)
    return MCPProfile(**values)


def _mint_revision() -> str:
    return f"rev-{secrets.token_urlsafe(18)}"


__all__ = [
    "MCPAttributionPolicy",
    "MCPHTTPProfile",
    "MCPProfile",
    "MCPProfileDefinitionError",
    "MCPProfileRegistry",
    "MCPProfileState",
    "MCPResourceLimits",
    "MCPStdioProfile",
    "ProfileAdmission",
    "profile_from_mapping",
]
