"""Unit tests for evidence handoff lifecycle locking and wslc backend argv contracts."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest


def _abs(tmp_path: Path, name: str) -> Path:
    path = (tmp_path / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bootstrap(tmp_path: Path, *, password: str = "admin-secret-canary"):
    from evidence_handoff_runtime.config import LifecycleBootstrapContext
    from optimus_security.sanitization import PathAliasRule

    capture = _abs(tmp_path, "capture")
    return LifecycleBootstrapContext(
        service_secrets=("svc-secret-alpha",),
        identity_values=("operator@example.test",),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=_abs(tmp_path, "control"),
        store_admin_user="handoff",
        store_admin_password=password,
    )


def _enabled_config(**overrides: object):
    from evidence_handoff_runtime.config import FeatureConfig

    values = {
        "enabled": "true",
        "backend_id": "wslc",
        "bind_host": "127.0.0.1",
        "postgres_port": "55432",
        "container_name": "evidence-handoff-postgres-test",
        "image": "postgres:16-alpine",
        "volume_name": "evidence-handoff-postgres-test-data",
    }
    values.update({key: str(value) for key, value in overrides.items()})
    return FeatureConfig.from_mapping(values)


class _RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._hold = threading.Event()
        self._entered = threading.Event()
        self.block_first = False

    def run(self, argv: list[str], **_kwargs: object) -> object:
        self.calls.append(tuple(argv))
        if self.block_first and len([c for c in self.calls if "run" in c or "start" in c]) == 1:
            if "run" in argv or ("start" in argv and "volume" not in argv):
                self._entered.set()
                self._hold.wait(timeout=2.0)
        returncode = 1 if "inspect" in argv else 0
        return type("Result", (), {"returncode": returncode, "stdout": "", "stderr": ""})()


def test_disabled_start_does_not_spawn_and_names_operator_relay(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import Availability, FeatureConfig
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    runner = _RecordingRunner()
    manager = LifecycleManager(
        FeatureConfig.from_mapping({}),
        _bootstrap(tmp_path),
        process_runner=runner,
    )
    status = manager.start()
    assert status.availability is Availability.DISABLED
    assert status.active_route == "operator_relay"
    assert status.may_start_infrastructure is False
    assert runner.calls == []


def test_wslc_run_argv_is_loopback_only_and_excludes_wildcard_bind(tmp_path: Path) -> None:
    from evidence_handoff_runtime.backends import WslcPostgresBackend

    backend = WslcPostgresBackend(
        config=_enabled_config(),
        bootstrap=_bootstrap(tmp_path),
        wslc_executable="wslc",
    )
    env_file = tmp_path / "store.env"
    backend.write_env_file(env_file)
    argv = backend.build_run_argv(env_file=env_file)
    assert argv[0] == "wslc"
    assert "run" in argv
    publish = next(arg for arg in argv if arg.startswith("127.0.0.1:") or "0.0.0.0" in arg)
    assert publish.startswith("127.0.0.1:")
    assert "0.0.0.0" not in " ".join(argv)
    assert "admin-secret-canary" not in " ".join(argv)
    assert "--env-file" in argv
    assert backend.backend_id == "wslc"
    assert backend.bind_host == "127.0.0.1"


def test_enabled_start_uses_spawn_seam_without_projecting_credentials(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    password = "admin-secret-canary"
    runner = _RecordingRunner()
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path, password=password),
        process_runner=runner,
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
    )
    status = manager.start()
    assert status.running is True
    assert status.availability is None
    assert runner.calls, "enabled start must invoke the process seam"
    joined = " ".join(" ".join(call) for call in runner.calls)
    assert password not in joined
    assert password not in repr(status)
    assert status.projected_credential is None


def test_concurrent_start_is_serialized_by_lifecycle_lock(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    runner = _RecordingRunner()
    runner.block_first = True
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=runner,
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
    )
    results: list[object] = []

    def _start() -> None:
        results.append(manager.start())

    first = threading.Thread(target=_start)
    second = threading.Thread(target=_start)
    first.start()
    assert runner._entered.wait(timeout=2.0)
    second.start()
    time.sleep(0.05)
    assert second.is_alive()
    runner._hold.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)
    assert not first.is_alive()
    assert not second.is_alive()
    assert len(results) == 2


def test_stop_and_status_are_idempotent_and_content_free(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import Availability
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    password = "admin-secret-canary"
    runner = _RecordingRunner()
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path, password=password),
        process_runner=runner,
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
    )
    started = manager.start()
    stopped = manager.stop()
    stopped_again = manager.stop()
    status = manager.status()
    assert started.running is True
    assert stopped.running is False
    assert stopped.availability is Availability.UNAVAILABLE
    assert stopped_again.summary_code == stopped.summary_code
    for item in (started, stopped, status, repr(manager)):
        assert password not in repr(item)


def test_stop_surfaces_nonzero_wslc_returncode(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import Availability
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    class _FailStopRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []
            self._created = False

        def run(self, argv: list[str], **_kwargs: object) -> object:
            self.calls.append(tuple(argv))
            if "inspect" in argv:
                returncode = 0 if self._created else 1
            elif "run" in argv:
                self._created = True
                returncode = 0
            elif "stop" in argv:
                returncode = 1
            else:
                returncode = 0
            return type("Result", (), {"returncode": returncode, "stdout": "", "stderr": ""})()

    runner = _FailStopRunner()
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=runner,
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
    )
    assert manager.start().running is True
    status = manager.stop()
    assert status.availability is Availability.UNAVAILABLE
    assert status.summary_code == "store_stop_failed"
    assert status.running is False
    assert any("stop" in call for call in runner.calls)


def test_destroy_for_test_cleanup_raises_on_nonzero_remove(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager

    class _FailRemoveRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def run(self, argv: list[str], **_kwargs: object) -> object:
            self.calls.append(tuple(argv))
            # inspect succeeds (resource present); remove fails (transient wslc error)
            if "remove" in argv:
                returncode = 1
            else:
                returncode = 0
            return type("Result", (), {"returncode": returncode, "stdout": "", "stderr": ""})()

    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=_FailRemoveRunner(),
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
        wslc_executable="wslc",
    )
    with pytest.raises(LifecycleError) as raised:
        manager.destroy_for_test_cleanup()
    assert raised.value.code == "store_destroy_failed"


def test_destroy_for_test_cleanup_skips_missing_resources(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    class _MissingResourcesRunner:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        def run(self, argv: list[str], **_kwargs: object) -> object:
            self.calls.append(tuple(argv))
            # inspect/volume inspect miss; remove must not be attempted
            return type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()

    runner = _MissingResourcesRunner()
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=runner,
        wslc_executable="wslc",
    )
    manager.destroy_for_test_cleanup()
    assert any("inspect" in call for call in runner.calls)
    assert not any("remove" in call for call in runner.calls)


def test_unavailable_when_wslc_missing(tmp_path: Path) -> None:
    from evidence_handoff_runtime.config import Availability
    from evidence_handoff_runtime.lifecycle import LifecycleManager

    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=_RecordingRunner(),
        wslc_executable=None,
    )
    status = manager.start()
    assert status.availability is Availability.UNAVAILABLE
    assert status.active_route == "operator_relay"


def test_refusal_to_switch_backend_while_running(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager

    runner = _RecordingRunner()
    manager = LifecycleManager(
        _enabled_config(),
        _bootstrap(tmp_path),
        process_runner=runner,
        probe_ready=lambda: True,
        probe_version=lambda: "PostgreSQL 16.0",
    )
    manager.start()
    with pytest.raises(LifecycleError) as raised:
        manager.switch_backend("docker")
    assert raised.value.code == "backend_switch_refused_while_running"


def test_store_backend_rejects_non_loopback_bind(tmp_path: Path) -> None:
    from evidence_handoff_runtime.backends import StoreBackendError, WslcPostgresBackend

    with pytest.raises(StoreBackendError) as raised:
        WslcPostgresBackend(
            config=_enabled_config(bind_host="0.0.0.0"),
            bootstrap=_bootstrap(tmp_path),
            wslc_executable="wslc",
        )
    assert raised.value.code == "non_loopback_bind_rejected"
