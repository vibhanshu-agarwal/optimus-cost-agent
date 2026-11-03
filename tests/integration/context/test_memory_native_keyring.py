"""Plan 12.10 Task 2: setup and the Gateway's read on the real OS keyring, under an isolated test service name.

Selected with `-m requires_os_keyring_write`. Writes, reads and deletes only `optimus-p1210-test`, never a real Optimus entry.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import keyring
import pytest
from keyring.errors import PasswordDeleteError

from optimus.acp import memory_setup
from optimus_gateway import memory_index
from optimus_security import memory_index_config as mc
from optimus_security import memory_index_contract as mic

pytestmark = [pytest.mark.requires_os_keyring_write]

_SERVICE = "optimus-p1210-test"
_CREDENTIAL = "redis-password"


@pytest.fixture
def isolated_service(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setattr(memory_setup, "KEYRING_SERVICE", _SERVICE)
    monkeypatch.setattr(memory_index, "KEYRING_SERVICE", _SERVICE)
    yield _SERVICE
    try:
        keyring.delete_password(_SERVICE, _CREDENTIAL)
    except PasswordDeleteError:
        pass


def _download(*, repository: str, revision: str, target: Path) -> None:
    (target / "model.onnx").write_bytes(f"{repository}@{revision}".encode())


def _settings(tmp_path: Path) -> dict[str, Any]:
    probe = tmp_path / "probe"
    probe.mkdir()
    (probe / "model.onnx").write_bytes(b"test/repository@abc")
    return {"image": "redis@sha256:" + "a" * 64, "container": "test-redis", "volume": "test-data", "host": "127.0.0.1", "port": 9, "user": "optimus-index", "maxmemory_mb": 128,
            "artifact_megabytes": 1, "embedding": {"model": "test/model", "source": "test", "repository": "test/repository", "revision": "abc", "licence": "MIT", "dimensions": 8,
                                                   "max_input_tokens": 16, "artifact_directory": "model", "artifact_sha256": mc.artifact_digest(probe)}}


def test_the_real_keyring_holds_the_password_and_no_file_does(isolated_service: str, tmp_path: Path) -> None:
    assert keyring.get_password(isolated_service, _CREDENTIAL) is None
    path = memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: True, download=_download, defaults=_settings(tmp_path))
    password = keyring.get_password(isolated_service, _CREDENTIAL)
    assert password and len(password) >= 32
    for file in path.parent.rglob("*"):
        if file.is_file():
            assert password.encode() not in file.read_bytes(), file


def test_a_rerun_keeps_the_real_keyrings_password(isolated_service: str, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: True, download=_download, defaults=settings)
    before = keyring.get_password(isolated_service, _CREDENTIAL)
    memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: pytest.fail("no prompt"), download=_download, defaults=settings)
    assert keyring.get_password(isolated_service, _CREDENTIAL) == before


def test_the_gateway_reports_an_absent_real_credential_with_a_stable_code(isolated_service: str, tmp_path: Path) -> None:
    path = memory_setup.run_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: True, download=_download, defaults=_settings(tmp_path))
    _literal, config, _refusal = mc.read(path.parent)
    assert config is not None
    keyring.delete_password(isolated_service, _CREDENTIAL)
    service = memory_index.build_index_service(config, keyring_backend=keyring, hmac_key=b"k" * 32)
    body = b'{"op":"coverage","scope":"' + b"ab" * 32 + b'"}'
    assert service.handle(body, deadline=time.monotonic() + 1) == (503, mic.error_body("INDEX_CREDENTIAL_MISSING"))
