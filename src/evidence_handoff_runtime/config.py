"""Default-off feature configuration and immutable lifecycle bootstrap context."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from optimus_security.sanitization import PathAliasRule

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off", ""})

_DEFAULT_BACKEND = "wslc"
_DEFAULT_BIND_HOST = "127.0.0.1"
_DEFAULT_POSTGRES_PORT = 55432
_DEFAULT_CONTAINER_NAME = "evidence-handoff-postgres"
_DEFAULT_IMAGE = "postgres:16-alpine"
_DEFAULT_VOLUME_NAME = "evidence-handoff-postgres-data"


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


def _parse_bool(raw: str | None) -> bool:
    if raw is None:
        return False
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return False


@dataclass(frozen=True)
class FeatureConfig:
    enabled: bool
    backend_id: str = _DEFAULT_BACKEND
    bind_host: str = _DEFAULT_BIND_HOST
    postgres_port: int = _DEFAULT_POSTGRES_PORT
    container_name: str = _DEFAULT_CONTAINER_NAME
    image: str = _DEFAULT_IMAGE
    volume_name: str = _DEFAULT_VOLUME_NAME

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> FeatureConfig:
        port_raw = values.get("postgres_port")
        port = _DEFAULT_POSTGRES_PORT
        if port_raw is not None and port_raw.strip():
            port = int(port_raw)
        return cls(
            enabled=_parse_bool(values.get("enabled")),
            backend_id=(values.get("backend_id") or _DEFAULT_BACKEND).strip() or _DEFAULT_BACKEND,
            bind_host=(values.get("bind_host") or _DEFAULT_BIND_HOST).strip() or _DEFAULT_BIND_HOST,
            postgres_port=port,
            container_name=(values.get("container_name") or _DEFAULT_CONTAINER_NAME).strip()
            or _DEFAULT_CONTAINER_NAME,
            image=(values.get("image") or _DEFAULT_IMAGE).strip() or _DEFAULT_IMAGE,
            volume_name=(values.get("volume_name") or _DEFAULT_VOLUME_NAME).strip() or _DEFAULT_VOLUME_NAME,
        )


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
    lock_path: Path | None = None
    control_root: Path | None = None
    store_admin_user: str = "postgres"
    store_admin_password: str = ""

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
            f"capability_count={len(self.capabilities)}, "
            f"lock_path_set={self.lock_path is not None}, "
            f"control_root_set={self.control_root is not None}, "
            f"store_admin_user={self.store_admin_user!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


__all__ = [
    "Availability",
    "FeatureConfig",
    "LifecycleBootstrapContext",
    "LifecycleBootstrapError",
]
