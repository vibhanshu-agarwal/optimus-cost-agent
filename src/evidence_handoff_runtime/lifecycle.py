"""Product-owned lifecycle manager for the evidence handoff store."""

from __future__ import annotations

import json
import shutil
import socket
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from evidence_handoff_runtime.backends import (
    StoreBackend,
    StoreBackendError,
    build_store_backend,
    registered_backend_ids,
)
from evidence_handoff_runtime.config import (
    Availability,
    FeatureConfig,
    LifecycleBootstrapContext,
    LifecycleBootstrapError,
)
from evidence_handoff_runtime.inputs import RuntimeInputSupplier
from evidence_handoff_runtime.process import ProcessRunner, SubprocessRunner

_READY_TIMEOUT_SECONDS = 90.0
_POLL_INTERVAL_SECONDS = 0.25


class LifecycleError(Exception):
    """Value-free lifecycle failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def __repr__(self) -> str:
        return f"LifecycleError(code={self.code!r})"

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class LifecycleStatus:
    availability: Availability | None
    running: bool
    active_route: str
    summary_code: str
    may_start_infrastructure: bool
    projected_credential: str | None
    ledger_instance_id: str | None = None
    backend_id: str | None = None
    integrity_incident: object | None = None

    def __repr__(self) -> str:
        return (
            "LifecycleStatus("
            f"availability={self.availability!r}, "
            f"running={self.running!r}, "
            f"active_route={self.active_route!r}, "
            f"summary_code={self.summary_code!r}, "
            f"may_start_infrastructure={self.may_start_infrastructure!r}, "
            f"projected_credential={self.projected_credential!r}, "
            f"ledger_instance_id={self.ledger_instance_id!r}, "
            f"backend_id={self.backend_id!r}, "
            f"integrity_incident={self.integrity_incident!r})"
        )


@dataclass(frozen=True)
class HealthReport:
    ready: bool
    postgres_version: str | None
    ledger_instance_id: str | None

    def __repr__(self) -> str:
        return (
            "HealthReport("
            f"ready={self.ready!r}, "
            f"postgres_version={self.postgres_version!r}, "
            f"ledger_instance_id={self.ledger_instance_id!r})"
        )


class LifecycleManager:
    """Idempotent, lock-serialized lifecycle operations for the Docker PostgreSQL store."""

    def __init__(
        self,
        config: FeatureConfig,
        bootstrap: LifecycleBootstrapContext,
        *,
        process_runner: ProcessRunner | None = None,
        docker_executable: str | None | object = ...,
        probe_ready: Callable[[], bool] | None = None,
        probe_version: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._bootstrap = bootstrap
        self._runner: ProcessRunner = process_runner or SubprocessRunner()
        if docker_executable is ...:
            if config.backend_id in registered_backend_ids():
                self._executable = shutil.which("docker")
            else:
                self._executable = None
        else:
            self._executable = docker_executable  # type: ignore[assignment]
        self._probe_ready = probe_ready
        self._probe_version = probe_version
        self._thread_lock = threading.RLock()
        self._running = False
        self._ledger_instance_id: str | None = self._load_instance_id()

    def __repr__(self) -> str:
        return (
            "LifecycleManager("
            f"enabled={self._config.enabled!r}, "
            f"backend_id={self._config.backend_id!r}, "
            f"running={self._running!r}, "
            f"ledger_instance_id={self._ledger_instance_id!r})"
        )

    def status(self) -> LifecycleStatus:
        with self._lifecycle_lock():
            integrity = self._load_integrity_incident()
            if integrity is not None:
                return self._integrity_failed_status(integrity)
            if not self._config.enabled:
                return self._disabled_status()
            if self._running and self._is_ready():
                return self._ready_status()
            if self._config.backend_id not in registered_backend_ids():
                return self._unavailable_status("unsupported_backend")
            if not self._executable:
                return self._unavailable_status("docker_unavailable")
            return self._unavailable_status("store_not_running")

    def start(self) -> LifecycleStatus:
        with self._lifecycle_lock():
            integrity = self._load_integrity_incident()
            if integrity is not None:
                return self._integrity_failed_status(integrity)
            if not self._config.enabled:
                return self._disabled_status()
            try:
                RuntimeInputSupplier(config=self._config, startup=self._bootstrap).startup_inputs()
            except LifecycleBootstrapError as exc:
                return self._unavailable_status(exc.code)
            # Unknown backend must fail closed before any process spawn.
            if self._config.backend_id not in registered_backend_ids():
                return self._unavailable_status("unsupported_backend")
            if not self._executable:
                return self._unavailable_status("docker_unavailable")
            try:
                backend = self._backend()
            except StoreBackendError as exc:
                return self._unavailable_status(exc.code)

            if self._running and self._is_ready():
                return self._ready_status()

            try:
                self._ensure_volume(backend)
                self._runner.run(backend.build_pull_argv())
                if self._container_exists(backend):
                    self._runner.run(backend.build_start_argv())
                else:
                    env_file = self._env_file_path()
                    backend.write_env_file(env_file)
                    try:
                        result = self._runner.run(backend.build_run_argv(env_file=env_file))
                        if getattr(result, "returncode", 1) != 0:
                            return self._unavailable_status("store_start_failed")
                    finally:
                        env_file.unlink(missing_ok=True)
                if not self._wait_until_ready():
                    return self._unavailable_status("store_not_ready")
                self._initialize_unlocked()
                self._migrate_unlocked()
                self._running = True
                return self._ready_status()
            except LifecycleError as exc:
                return self._unavailable_status(exc.code)
            except OSError:
                return self._unavailable_status("store_start_failed")

    def stop(self) -> LifecycleStatus:
        with self._lifecycle_lock():
            integrity = self._load_integrity_incident()
            if not self._config.enabled and not self._running:
                if integrity is not None:
                    return self._integrity_failed_status(integrity)
                return self._disabled_status()
            if self._config.backend_id not in registered_backend_ids():
                self._running = False
                if integrity is not None:
                    return self._integrity_failed_status(integrity)
                return self._unavailable_status("unsupported_backend")
            if not self._executable:
                self._running = False
                if integrity is not None:
                    return self._integrity_failed_status(integrity)
                return self._unavailable_status("docker_unavailable")
            try:
                backend = self._backend()
                if self._container_exists(backend):
                    result = self._runner.run(backend.build_stop_argv())
                    if getattr(result, "returncode", 1) != 0:
                        self._running = False
                        if integrity is not None:
                            return self._integrity_failed_status(integrity)
                        return self._unavailable_status("store_stop_failed")
            except StoreBackendError as exc:
                self._running = False
                if integrity is not None:
                    return self._integrity_failed_status(integrity)
                return self._unavailable_status(exc.code)
            self._running = False
            if integrity is not None:
                return self._integrity_failed_status(integrity)
            return self._unavailable_status("store_stopped")

    def initialize(self) -> LifecycleStatus:
        with self._lifecycle_lock():
            if not self._config.enabled:
                return self._disabled_status()
            self._initialize_unlocked()
            return self._ready_status() if self._running else self._unavailable_status("initialized")

    def migrate(self) -> LifecycleStatus:
        """Task 2 preflight: prove PostgreSQL accepts connections. Schema migrations are Task 3."""
        with self._lifecycle_lock():
            if not self._config.enabled:
                return self._disabled_status()
            self._migrate_unlocked()
            return self._ready_status() if self._running else self._unavailable_status("migrate_preflight_ok")

    def preflight_schema_activation(self, coordinator: object, schema_id: str) -> object:
        """Task 9: delegate writer-activation preflight to CapabilityCoordinator (facts only)."""
        preflight = getattr(coordinator, "preflight_activation", None)
        if not callable(preflight):
            raise LifecycleError("capability_coordinator_required")
        return preflight(schema_id)

    def _initialize_unlocked(self) -> None:
        if self._ledger_instance_id is None:
            self._ledger_instance_id = str(uuid.uuid4())
            self._persist_instance_id(self._ledger_instance_id)

    def _migrate_unlocked(self) -> None:
        version = self._postgres_version()
        if not version:
            raise LifecycleError("migration_preflight_failed")

    def health(self) -> HealthReport:
        with self._lifecycle_lock():
            ready = self._is_ready()
            version = self._postgres_version() if ready else None
            return HealthReport(
                ready=ready,
                postgres_version=version,
                ledger_instance_id=self._ledger_instance_id,
            )

    def switch_backend(self, backend_id: str) -> None:
        with self._lifecycle_lock():
            if self._running:
                raise LifecycleError("backend_switch_refused_while_running")
            if backend_id != self._config.backend_id:
                raise LifecycleError("backend_switch_not_supported_in_slice")

    def docker_version(self) -> str:
        if not self._executable:
            return ""
        backend = self._backend()
        result = self._runner.run(backend.build_version_argv())
        stdout = getattr(result, "stdout", "") or ""
        return stdout.strip() or "docker"

    def resolve_installation_signing_key(
        self,
        *,
        keyring_backend: object,
        store: object,
    ) -> bytes:
        """Lifecycle-owned mint/load of the installation signing key (design line 265)."""
        from evidence_handoff_runtime.signing_key_custody import (
            SigningKeyCustodyError,
            resolve_signing_key,
        )

        if store is None:
            raise LifecycleError("signing_key_instance_fact_unavailable")
        try:
            store_instance_present = bool(store.instance_row_present())
        except Exception as exc:  # noqa: BLE001 — any probe failure is fail-closed
            raise LifecycleError("signing_key_instance_fact_unavailable") from exc

        control_root = self._control_root()
        instance_record_present = self._load_instance_id() is not None
        try:
            return resolve_signing_key(
                control_root=control_root,
                keyring_backend=keyring_backend,
                instance_record_present=instance_record_present,
                store_instance_present=store_instance_present,
            )
        except SigningKeyCustodyError as exc:
            raise LifecycleError(exc.code) from exc

    def destroy_for_test_cleanup(self) -> None:
        """Test-only cleanup of container and volume. Not part of operator stop."""
        with self._lifecycle_lock():
            if self._config.backend_id not in registered_backend_ids():
                return
            if not self._executable:
                return
            try:
                backend = self._backend()
            except StoreBackendError:
                return
            # Only remove resources that exist: bare `remove` / `volume remove` of a
            # missing name returns nonzero, and raising early would skip the volume when
            # start failed after `volume create` but before a container.
            if self._container_exists(backend):
                remove_container = self._runner.run(backend.build_remove_container_argv())
                if getattr(remove_container, "returncode", 1) != 0:
                    raise LifecycleError("store_destroy_failed")
            if self._volume_exists(backend):
                remove_volume = self._runner.run(backend.build_remove_volume_argv())
                if getattr(remove_volume, "returncode", 1) != 0:
                    raise LifecycleError("store_destroy_failed")
            self._running = False

    def _backend(self) -> StoreBackend:
        if not self._executable:
            raise StoreBackendError("docker_executable_missing")
        return build_store_backend(
            config=self._config,
            bootstrap=self._bootstrap,
            executable=str(self._executable),
        )

    def _ensure_volume(self, backend: StoreBackend) -> None:
        self._runner.run(backend.build_volume_create_argv())

    def _container_exists(self, backend: StoreBackend) -> bool:
        result = self._runner.run(backend.build_inspect_argv())
        return getattr(result, "returncode", 1) == 0

    def _volume_exists(self, backend: StoreBackend) -> bool:
        result = self._runner.run(backend.build_volume_inspect_argv())
        return getattr(result, "returncode", 1) == 0

    def _wait_until_ready(self) -> bool:
        deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if self._is_ready():
                return True
            time.sleep(_POLL_INTERVAL_SECONDS)
        return False

    def _is_ready(self) -> bool:
        if self._probe_ready is not None:
            return bool(self._probe_ready())
        if not self._tcp_ready(self._config.bind_host, self._config.postgres_port):
            return False
        # TCP accept can precede PostgreSQL auth readiness; require a real probe.
        return self._postgres_version() is not None

    def _postgres_version(self) -> str | None:
        if self._probe_version is not None:
            return self._probe_version()
        try:
            import psycopg
        except ImportError:
            return None
        conninfo = (
            f"host={self._config.bind_host} port={self._config.postgres_port} "
            f"user={self._bootstrap.store_admin_user} "
            f"password={self._bootstrap.store_admin_password} "
            "dbname=postgres connect_timeout=3"
        )
        try:
            with psycopg.connect(conninfo) as conn:
                row = conn.execute("SHOW server_version").fetchone()
                if row is None:
                    return None
                return f"PostgreSQL {row[0]}"
        except Exception:
            return None

    def _tcp_ready(self, host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            return False

    def _control_root(self) -> Path:
        root = self._bootstrap.control_root
        if root is None:
            raise LifecycleError("control_root_missing")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _env_file_path(self) -> Path:
        return self._control_root() / "store.env"

    def _instance_path(self) -> Path:
        return self._control_root() / "ledger_instance.json"

    def _load_instance_id(self) -> str | None:
        if self._bootstrap.control_root is None:
            return None
        path = self._bootstrap.control_root / "ledger_instance.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        value = payload.get("ledger_instance_id")
        return value if isinstance(value, str) and value else None

    def _persist_instance_id(self, instance_id: str) -> None:
        path = self._instance_path()
        path.write_text(
            json.dumps({"ledger_instance_id": instance_id}, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _lifecycle_lock(self):
        return _LifecycleLock(self._thread_lock, self._bootstrap.lock_path)

    def _load_integrity_incident(self):
        if self._bootstrap.control_root is None:
            return None
        from evidence_handoff_runtime.integrity import IntegrityLatch, IntegrityLatchError

        try:
            return IntegrityLatch(control_root=self._bootstrap.control_root).load()
        except IntegrityLatchError as exc:
            raise LifecycleError(exc.code) from exc

    def _integrity_failed_status(self, incident) -> LifecycleStatus:
        return LifecycleStatus(
            availability=Availability.UNAVAILABLE,
            running=False,
            active_route="integrity_hold",
            summary_code="ledger_integrity_failed",
            may_start_infrastructure=False,
            projected_credential=None,
            ledger_instance_id=self._ledger_instance_id,
            backend_id=self._config.backend_id,
            integrity_incident=incident,
        )

    def _disabled_status(self) -> LifecycleStatus:
        return LifecycleStatus(
            availability=Availability.DISABLED,
            running=False,
            active_route="operator_relay",
            summary_code="feature_disabled_operator_relay",
            may_start_infrastructure=False,
            projected_credential=None,
            ledger_instance_id=self._ledger_instance_id,
            backend_id=self._config.backend_id,
        )

    def _unavailable_status(self, code: str) -> LifecycleStatus:
        return LifecycleStatus(
            availability=Availability.UNAVAILABLE,
            running=False,
            active_route="operator_relay",
            summary_code=code,
            may_start_infrastructure=False,
            projected_credential=None,
            ledger_instance_id=self._ledger_instance_id,
            backend_id=self._config.backend_id,
        )

    def _ready_status(self) -> LifecycleStatus:
        return LifecycleStatus(
            availability=None,
            running=True,
            active_route="ledger",
            summary_code="store_ready",
            may_start_infrastructure=False,
            projected_credential=None,
            ledger_instance_id=self._ledger_instance_id,
            backend_id=self._config.backend_id,
        )


class _LifecycleLock:
    """Thread lock plus optional exclusive lock file for cross-process serialization."""

    def __init__(self, thread_lock: threading.RLock, lock_path: Path | None) -> None:
        self._thread_lock = thread_lock
        self._lock_path = lock_path
        self._fh = None

    def __enter__(self) -> _LifecycleLock:
        self._thread_lock.acquire()
        if self._lock_path is not None:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self._lock_path, "a+b")
            self._lock_file(self._fh)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._fh is not None:
            try:
                self._unlock_file(self._fh)
            finally:
                self._fh.close()
                self._fh = None
        self._thread_lock.release()

    @staticmethod
    def _lock_file(handle: object) -> None:
        import sys

        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock_file(handle: object) -> None:
        import sys

        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


__all__ = [
    "HealthReport",
    "LifecycleError",
    "LifecycleManager",
    "LifecycleStatus",
]
