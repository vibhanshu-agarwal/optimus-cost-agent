"""Default-off feature configuration and immutable lifecycle bootstrap context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optimus_security.sanitization import PathAliasRule

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})


class Availability(StrEnum):
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    INTEGRITY_FAILED = "integrity_failed"


class LifecycleBootstrapError(Exception):
    """Value-free bootstrap/readiness failure. Message is the stable code only."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"LifecycleBootstrapError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class FeatureConfig:
    enabled: bool

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> FeatureConfig:
        raw = values.get("enabled")
        if raw is None:
            return cls(enabled=False)
        normalized = raw.strip().lower()
        if normalized in _TRUTHY:
            return cls(enabled=True)
        if normalized in _FALSY:
            return cls(enabled=False)
        return cls(enabled=False)


@dataclass(frozen=True)
class LifecycleBootstrapContext:
    """Immutable resolved startup values. Secrets never appear in repr/str."""

    service_secrets: tuple[str, ...]
    identity_values: tuple[str, ...]
    path_aliases: tuple[PathAliasRule, ...]
    temporary_capture_root: Path
    staging_root: Path
    quarantine_root: Path
    forbidden_persistence_roots: tuple[Path, ...]
    allowed_origins: tuple[str, ...]
    enrollment_principal_ids: tuple[str, ...]
    capabilities: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            "LifecycleBootstrapContext("
            f"service_secret_count={len(self.service_secrets)}, "
            f"identity_value_count={len(self.identity_values)}, "
            f"path_alias_count={len(self.path_aliases)}, "
            f"temporary_capture_root={self.temporary_capture_root!s}, "
            f"staging_root={self.staging_root!s}, "
            f"quarantine_root={self.quarantine_root!s}, "
            f"forbidden_persistence_root_count={len(self.forbidden_persistence_roots)}, "
            f"allowed_origin_count={len(self.allowed_origins)}, "
            f"enrollment_principal_count={len(self.enrollment_principal_ids)}, "
            f"capability_count={len(self.capabilities)})"
        )

    def __str__(self) -> str:
        return self.__repr__()


__all__ = [
    "Availability",
    "FeatureConfig",
    "LifecycleBootstrapContext",
    "LifecycleBootstrapError",
]
