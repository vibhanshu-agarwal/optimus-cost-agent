"""Store backend contracts. This slice supports only PostgreSQL-in-wslc on loopback."""

from __future__ import annotations

from pathlib import Path

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


class WslcPostgresBackend:
    """wslc-managed PostgreSQL published only on 127.0.0.1."""

    def __init__(
        self,
        *,
        config: FeatureConfig,
        bootstrap: LifecycleBootstrapContext,
        wslc_executable: str,
    ) -> None:
        if config.backend_id != "wslc":
            raise StoreBackendError("unsupported_backend")
        if config.bind_host != "127.0.0.1":
            raise StoreBackendError("non_loopback_bind_rejected")
        if not wslc_executable:
            raise StoreBackendError("wslc_executable_missing")
        self._config = config
        self._bootstrap = bootstrap
        self._wslc = wslc_executable

    @property
    def backend_id(self) -> str:
        return "wslc"

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
            self._wslc,
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
        return require_argv([self._wslc, "start", self.container_name])

    def build_stop_argv(self) -> list[str]:
        return require_argv([self._wslc, "stop", self.container_name])

    def build_inspect_argv(self) -> list[str]:
        return require_argv([self._wslc, "inspect", self.container_name])

    def build_volume_create_argv(self) -> list[str]:
        return require_argv([self._wslc, "volume", "create", self.volume_name])

    def build_remove_container_argv(self) -> list[str]:
        return require_argv([self._wslc, "remove", "--force", self.container_name])

    def build_remove_volume_argv(self) -> list[str]:
        return require_argv([self._wslc, "volume", "remove", self.volume_name])

    def build_version_argv(self) -> list[str]:
        return require_argv([self._wslc, "version"])

    def build_pull_argv(self) -> list[str]:
        return require_argv([self._wslc, "pull", self.image])


__all__ = [
    "StoreBackendError",
    "WslcPostgresBackend",
]
