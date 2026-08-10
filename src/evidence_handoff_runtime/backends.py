"""Store backend contracts. This slice supports only PostgreSQL-in-Docker on loopback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
from evidence_handoff_runtime.process import require_argv


class StoreBackendError(Exception):
    """Value-free store-backend failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"StoreBackendError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


class StoreBackend(Protocol):
    """Loopback store backend selected by stopped-lifecycle ``backend_id``."""

    @property
    def backend_id(self) -> str: ...

    @property
    def bind_host(self) -> str: ...

    @property
    def port(self) -> int: ...

    @property
    def container_name(self) -> str: ...

    @property
    def volume_name(self) -> str: ...

    @property
    def image(self) -> str: ...

    def write_env_file(self, path: Path) -> Path: ...

    def build_run_argv(self, *, env_file: Path) -> list[str]: ...

    def build_start_argv(self) -> list[str]: ...

    def build_stop_argv(self) -> list[str]: ...

    def build_inspect_argv(self) -> list[str]: ...

    def build_volume_inspect_argv(self) -> list[str]: ...

    def build_volume_create_argv(self) -> list[str]: ...

    def build_remove_container_argv(self) -> list[str]: ...

    def build_remove_volume_argv(self) -> list[str]: ...

    def build_pull_argv(self) -> list[str]: ...

    def build_version_argv(self) -> list[str]: ...


class DockerPostgresBackend:
    """Docker Desktop-managed PostgreSQL published only on 127.0.0.1."""

    def __init__(
        self,
        *,
        config: FeatureConfig,
        bootstrap: LifecycleBootstrapContext,
        docker_executable: str,
    ) -> None:
        if config.backend_id != "docker":
            raise StoreBackendError("unsupported_backend")
        if config.bind_host != "127.0.0.1":
            raise StoreBackendError("non_loopback_bind_rejected")
        if not docker_executable:
            raise StoreBackendError("docker_executable_missing")
        self._config = config
        self._bootstrap = bootstrap
        self._docker = docker_executable

    @property
    def backend_id(self) -> str:
        return "docker"

    @property
    def bind_host(self) -> str:
        return self._config.bind_host

    @property
    def port(self) -> int:
        return self._config.postgres_port

    @property
    def container_name(self) -> str:
        return self._config.container_name

    @property
    def volume_name(self) -> str:
        return self._config.volume_name

    @property
    def image(self) -> str:
        return self._config.image

    def build_run_argv(self, *, env_file: Path) -> list[str]:
        publish = f"{self.bind_host}:{self.port}:5432"
        argv = [
            self._docker,
            "run",
            "--detach",
            "--name",
            self.container_name,
            "--publish",
            publish,
            "--volume",
            f"{self.volume_name}:/var/lib/postgresql/data",
            "--env-file",
            str(env_file),
            self.image,
        ]
        return require_argv(argv)

    def write_env_file(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Password stays in the env file, never in argv/status/repr.
        path.write_text(
            (
                f"POSTGRES_USER={self._bootstrap.store_admin_user}\n"
                f"POSTGRES_PASSWORD={self._bootstrap.store_admin_password}\n"
            ),
            encoding="utf-8",
        )
        return path

    def build_start_argv(self) -> list[str]:
        return require_argv([self._docker, "start", self.container_name])

    def build_stop_argv(self) -> list[str]:
        return require_argv([self._docker, "stop", self.container_name])

    def build_inspect_argv(self) -> list[str]:
        return require_argv([self._docker, "inspect", self.container_name])

    def build_volume_inspect_argv(self) -> list[str]:
        return require_argv([self._docker, "volume", "inspect", self.volume_name])

    def build_volume_create_argv(self) -> list[str]:
        return require_argv([self._docker, "volume", "create", self.volume_name])

    def build_remove_container_argv(self) -> list[str]:
        return require_argv([self._docker, "remove", "--force", self.container_name])

    def build_remove_volume_argv(self) -> list[str]:
        return require_argv([self._docker, "volume", "remove", self.volume_name])

    def build_version_argv(self) -> list[str]:
        return require_argv([self._docker, "version"])

    def build_pull_argv(self) -> list[str]:
        return require_argv([self._docker, "pull", self.image])


def _build_docker_backend(
    *,
    config: FeatureConfig,
    bootstrap: LifecycleBootstrapContext,
    executable: str,
) -> DockerPostgresBackend:
    return DockerPostgresBackend(
        config=config,
        bootstrap=bootstrap,
        docker_executable=executable,
    )


_BACKEND_FACTORIES: dict[
    str,
    Callable[..., StoreBackend],
] = {"docker": _build_docker_backend}


def registered_backend_ids() -> frozenset[str]:
    return frozenset(_BACKEND_FACTORIES)


def build_store_backend(
    *,
    config: FeatureConfig,
    bootstrap: LifecycleBootstrapContext,
    executable: str,
) -> StoreBackend:
    factory = _BACKEND_FACTORIES.get(config.backend_id)
    if factory is None:
        raise StoreBackendError("unsupported_backend")
    return factory(config=config, bootstrap=bootstrap, executable=executable)


__all__ = [
    "DockerPostgresBackend",
    "StoreBackend",
    "StoreBackendError",
    "build_store_backend",
    "registered_backend_ids",
]
