"""Live Windows evidence: PostgreSQL started via the real wslc CLI on loopback only."""

from __future__ import annotations

import json
import secrets
import socket
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_evidence_handoff_postgres

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO_ROOT / ".evidence-handoff" / "lifecycle"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _abs(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tcp_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def test_wslc_postgres_lifecycle_loopback_restart_persistence(tmp_path: Path) -> None:
    import shutil

    import psycopg

    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleManager
    from optimus_security.sanitization import PathAliasRule

    wslc = shutil.which("wslc")
    assert wslc is not None, "wslc CLI binary must be on PATH"

    port = _free_port()
    suffix = uuid.uuid4().hex[:8]
    container_name = f"evidence-handoff-pg-{suffix}"
    volume_name = f"evidence-handoff-pg-data-{suffix}"
    password = f"live-{secrets.token_hex(8)}"
    marker_value = f"persist-{uuid.uuid4().hex}"

    capture = _abs(tmp_path, "capture")
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "wslc",
            "bind_host": "127.0.0.1",
            "postgres_port": str(port),
            "container_name": container_name,
            "image": "postgres:16-alpine",
            "volume_name": volume_name,
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
        allowed_origins=("http://127.0.0.1:8765",),
        enrollment_principal_ids=("reviewer-1",),
        capabilities=("review-ruling",),
        lock_path=tmp_path / "lifecycle.lock",
        control_root=_abs(tmp_path, "control"),
        store_admin_user="handoff",
        store_admin_password=password,
    )
    manager = LifecycleManager(config, bootstrap)

    artifact: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "wslc_executable": wslc,
        "container_name": container_name,
        "volume_name": volume_name,
        "bind_host": "127.0.0.1",
        "port": port,
    }

    try:
        started = manager.start()
        assert started.running is True
        assert started.availability is None
        assert _tcp_ready("127.0.0.1", port)

        health = manager.health()
        assert health.ready is True
        assert health.postgres_version
        assert "PostgreSQL" in health.postgres_version
        artifact["postgres_version"] = health.postgres_version
        artifact["ledger_instance_id"] = health.ledger_instance_id
        artifact["wslc_version"] = manager.wslc_version()

        conninfo = (
            f"host=127.0.0.1 port={port} user=handoff password={password} dbname=postgres "
            "connect_timeout=5"
        )
        with psycopg.connect(conninfo) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_probe (id int PRIMARY KEY, marker text NOT NULL)"
            )
            conn.execute("DELETE FROM lifecycle_probe")
            conn.execute("INSERT INTO lifecycle_probe(id, marker) VALUES (1, %s)", (marker_value,))
            conn.commit()

        manager.stop()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and _tcp_ready("127.0.0.1", port):
            time.sleep(0.2)
        assert not _tcp_ready("127.0.0.1", port)

        restarted = manager.start()
        assert restarted.running is True
        assert restarted.availability is None
        assert _tcp_ready("127.0.0.1", port)
        with psycopg.connect(conninfo) as conn:
            row = conn.execute("SELECT marker FROM lifecycle_probe WHERE id = 1").fetchone()
            assert row is not None
            assert row[0] == marker_value
        artifact["restart_persistence"] = True
        artifact["loopback_ready"] = True
        artifact["result"] = "pass"
    finally:
        try:
            manager.stop()
        except Exception:
            pass
        try:
            manager.destroy_for_test_cleanup()
        except Exception:
            pass

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    artifact_path = ARTIFACT_ROOT / f"wslc-lifecycle-{suffix}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert artifact_path.is_file()
    raw = artifact_path.read_text(encoding="utf-8")
    assert password not in raw
