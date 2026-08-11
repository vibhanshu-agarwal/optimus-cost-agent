"""Live acceptance for durable signing-key custody (v2 Task 5).

R1 kill/restart and R3 live fail-closed require real Docker PostgreSQL + LedgerService
plus OS keyring *writes*. Deselected by default via ``requires_evidence_handoff_service``
and ``requires_os_keyring_write``.
"""

from __future__ import annotations

import secrets
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.requires_evidence_handoff_service,
    pytest.mark.requires_os_keyring_write,
]

EXPECTED_PROTOCOL = "2025-11-25"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _force_kill_service_process(pid: int) -> None:
    """Windows SIGKILL-equivalent; falls back to SIGKILL elsewhere."""
    if sys.platform == "win32":
        completed = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
    else:
        import os
        import signal

        os.kill(pid, signal.SIGKILL)


def test_r1_pre_crash_token_validates_after_taskkill_restart(tmp_path: Path) -> None:
    """R1 / R8.1: token issued before forced kill still validates after restart from keyring."""
    # Import first — RED must fail here until Task 2 lands the module.
    import keyring as os_keyring

    from evidence_handoff_runtime.auth import CredentialIssuer, CredentialValidator, Enrollment
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.service import LedgerService, ServiceConfig
    from evidence_handoff_runtime.signing_key_custody import (
        keyring_service_for_control_root,
        resolve_signing_key,
    )
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    pg_port = _free_port()
    svc_port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    password = f"svc-{secrets.token_hex(8)}"
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    service_name = keyring_service_for_control_root(control_root)

    # Mint while no instance exists yet (eligible first-run path).
    signing_key = resolve_signing_key(
        control_root=control_root,
        keyring_backend=os_keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    assert isinstance(signing_key, (bytes, bytearray))
    assert len(signing_key) == 32

    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(pg_port),
            "container_name": f"evidence-handoff-custody-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-custody-data-{suffix}",
        }
    )
    bootstrap = LifecycleBootstrapContext(
        service_secrets=("svc-secret-alpha",),
        identity_values=("operator@example.test",),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
        allowed_origins=(f"http://127.0.0.1:{svc_port}",),
        enrollment_principal_ids=("principal-reviewer",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=control_root,
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap, docker_executable="docker")
    service = None
    try:
        started = None
        for _attempt in range(3):
            started = manager.start()
            if started.running:
                break
            try:
                manager.stop()
            except Exception:
                pass
            try:
                manager.destroy_for_test_cleanup()
            except Exception:
                pass
        assert started is not None and started.running is True
        assert started.backend_id == "docker"
        instance_id = started.ledger_instance_id
        assert instance_id
        conninfo = (
            f"host=127.0.0.1 port={pg_port} user=handoff password={password} "
            "dbname=postgres connect_timeout=5"
        )
        apply_migrations(conninfo)
        store = PostgresLedgerStore(
            conninfo=conninfo,
            ledger_instance_id=instance_id,
            control_root=control_root,
        )
        store.ensure_instance_metadata()

        # Instance now exists — resolve must load the same durable key (no remint).
        signing_key = resolve_signing_key(
            control_root=control_root,
            keyring_backend=os_keyring,
            instance_record_present=True,
            store_instance_present=True,
        )

        enrollments = {
            (instance_id, "principal-reviewer"): Enrollment(
                principal_id="principal-reviewer",
                agent_id="reviewer-1",
                caller_role="reviewer",
                scopes=frozenset({"ledger.write", "ledger.read"}),
                instance_id=instance_id,
            ),
        }
        issuer = CredentialIssuer(
            signing_key=signing_key,
            issuer="evidence-handoff-runtime",
            audience="evidence-handoff",
            enrollments=enrollments,
            now=lambda: datetime.now(tz=UTC),
            default_ttl=timedelta(minutes=10),
        )
        pre_crash_token = issuer.issue(
            instance_id=instance_id,
            enrollment=enrollments[(instance_id, "principal-reviewer")],
        )

        service_config = ServiceConfig(
            bind_host="127.0.0.1",
            bind_port=svc_port,
            allowed_origins=(f"http://127.0.0.1:{svc_port}",),
            request_limits={"max_body_bytes": 65536},
            protocol_versions=(EXPECTED_PROTOCOL,),
        )
        service = LedgerService.start(
            service_config,
            store,
            bootstrap,
            auth={
                "signing_key": signing_key,
                "issuer": "evidence-handoff-runtime",
                "audience": "evidence-handoff",
                "enrollments": enrollments,
            },
        )
        service.wait_ready(timeout_seconds=30.0)
        pid = service.process.pid
        assert pid is not None
        _force_kill_service_process(pid)
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if service.process.poll() is not None:
                break
            time.sleep(0.1)
        assert service.process.poll() is not None
        service = None  # process already dead; skip graceful stop

        signing_key_after = resolve_signing_key(
            control_root=control_root,
            keyring_backend=os_keyring,
            instance_record_present=True,
            store_instance_present=True,
        )
        assert signing_key_after == signing_key

        service = LedgerService.start(
            service_config,
            store,
            bootstrap,
            auth={
                "signing_key": signing_key_after,
                "issuer": "evidence-handoff-runtime",
                "audience": "evidence-handoff",
                "enrollments": enrollments,
            },
        )
        service.wait_ready(timeout_seconds=30.0)

        validator = CredentialValidator(
            signing_key=signing_key_after,
            expected_issuer="evidence-handoff-runtime",
            expected_audience="evidence-handoff",
            enrollments=enrollments,
            now=lambda: datetime.now(tz=UTC),
            revoked_token_ids=frozenset(),
            consumed_jti=set(),
        )
        principal = validator.validate(
            f"Bearer {pre_crash_token}",
            {"ledger_instance_id": instance_id},
        )
        assert principal.principal_id == "principal-reviewer"
    finally:
        if service is not None:
            service.stop()
        try:
            os_keyring.delete_password(service_name, "signing_key")
        except Exception:
            pass
        manager.stop()
        try:
            manager.destroy_for_test_cleanup()
        except LifecycleError:
            pass


def test_r3_deleted_keyring_entry_with_instance_refuses_start_no_remint(tmp_path: Path) -> None:
    """R3 front door: instance exists + keyring entry deleted → fail-closed, no remint."""
    import keyring as os_keyring

    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleError, LifecycleManager
    from evidence_handoff_runtime.migrations import apply_migrations
    from evidence_handoff_runtime.signing_key_custody import (
        SigningKeyCustodyError,
        keyring_service_for_control_root,
        resolve_signing_key,
    )
    from evidence_handoff_runtime.store import PostgresLedgerStore
    from optimus_security.sanitization import PathAliasRule

    pg_port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    password = f"svc-{secrets.token_hex(8)}"
    capture = _abs(tmp_path, "capture")
    control_root = _abs(tmp_path, "control")
    service_name = keyring_service_for_control_root(control_root)

    seeded = resolve_signing_key(
        control_root=control_root,
        keyring_backend=os_keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    assert isinstance(seeded, bytes)

    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": str(pg_port),
            "container_name": f"evidence-handoff-custody-r3-{suffix}",
            "image": "postgres:16-alpine",
            "volume_name": f"evidence-handoff-custody-r3-data-{suffix}",
        }
    )
    bootstrap = LifecycleBootstrapContext(
        service_secrets=("svc-secret-alpha",),
        identity_values=("operator@example.test",),
        path_aliases=(PathAliasRule(source_root=str(capture), alias="<temp>"),),
        temporary_capture_root=capture,
        staging_root=_abs(tmp_path, "staging"),
        quarantine_root=_abs(tmp_path, "quarantine"),
        forbidden_persistence_roots=(_abs(tmp_path, "forbidden"),),
        allowed_origins=("http://127.0.0.1:9",),
        enrollment_principal_ids=("principal-reviewer",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=control_root,
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap, docker_executable="docker")
    try:
        started = None
        for _attempt in range(3):
            started = manager.start()
            if started.running:
                break
            try:
                manager.stop()
            except Exception:
                pass
            try:
                manager.destroy_for_test_cleanup()
            except Exception:
                pass
        assert started is not None and started.running is True
        assert started.backend_id == "docker"
        instance_id = started.ledger_instance_id
        assert instance_id
        conninfo = (
            f"host=127.0.0.1 port={pg_port} user=handoff password={password} "
            "dbname=postgres connect_timeout=5"
        )
        apply_migrations(conninfo)
        store = PostgresLedgerStore(
            conninfo=conninfo,
            ledger_instance_id=instance_id,
            control_root=control_root,
        )
        store.ensure_instance_metadata()

        os_keyring.delete_password(service_name, "signing_key")

        with pytest.raises(SigningKeyCustodyError) as raised:
            resolve_signing_key(
                control_root=control_root,
                keyring_backend=os_keyring,
                instance_record_present=True,
                store_instance_present=True,
            )
        assert raised.value.code in {"signing_key_missing", "signing_key_mint_forbidden"}
        assert os_keyring.get_password(service_name, "signing_key") in {None, ""}
    finally:
        try:
            os_keyring.delete_password(service_name, "signing_key")
        except Exception:
            pass
        manager.stop()
        try:
            manager.destroy_for_test_cleanup()
        except LifecycleError:
            pass
