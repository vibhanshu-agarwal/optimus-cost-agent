"""Plan 12.11 Task 1: store setup and the Gateway's read on the real OS keyring, under the released isolated test service name.

Selected with `-m requires_os_keyring_write`. Writes, reads and deletes only `optimus-p1211-test`, never a real Optimus entry.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import keyring
import pytest
from keyring.errors import PasswordDeleteError

from optimus.acp import memory_setup
from optimus_gateway import memory_store
from optimus_security import memory_store_config as sc
from optimus_security import memory_store_contract as msc

pytestmark = [pytest.mark.requires_os_keyring_write]

_SERVICE = "optimus-p1211-test"
_SETTINGS = {"image": "redis@sha256:" + "a" * 64, "container": "test-memory-store", "volume": "test-memory-data", "host": "127.0.0.1", "port": 9,
             "user": "optimus-memory", "maxmemory_mb": 128, "admission_ceiling_mb": 96}


@pytest.fixture
def credential(monkeypatch: pytest.MonkeyPatch) -> str:
    """Setup names a fresh entry each time (#526); pin this test's own one so the isolated service's entry is known and removed."""
    name = memory_setup._new_credential_name()
    monkeypatch.setattr(memory_setup, "_new_credential_name", lambda: name)
    return name


@pytest.fixture
def isolated_service(monkeypatch: pytest.MonkeyPatch, credential: str) -> Iterator[str]:
    monkeypatch.setattr(memory_setup, "STORE_KEYRING_SERVICE", _SERVICE)
    monkeypatch.setattr(memory_store, "KEYRING_SERVICE", _SERVICE)
    yield _SERVICE
    try:
        keyring.delete_password(_SERVICE, credential)
    except PasswordDeleteError:
        pass
    assert keyring.get_password(_SERVICE, credential) is None, "the isolated entry must not outlive the test"


def _setup(tmp_path: Path) -> Path:
    return memory_setup.run_store_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: True, defaults=_SETTINGS)


def test_the_real_keyring_holds_the_password_and_no_file_does(isolated_service: str, credential: str, tmp_path: Path) -> None:
    assert keyring.get_password(isolated_service, credential) is None
    path = _setup(tmp_path)
    password = keyring.get_password(isolated_service, credential)
    assert password and len(password) >= 32
    for file in path.parent.rglob("*"):
        if file.is_file():
            assert password.encode() not in file.read_bytes(), file


def test_a_rerun_keeps_the_real_keyrings_password(isolated_service: str, credential: str, tmp_path: Path) -> None:
    _setup(tmp_path)
    before = keyring.get_password(isolated_service, credential)
    memory_setup.run_store_setup(tmp_path, keyring_backend=keyring, confirm=lambda _d: pytest.fail("no prompt"), defaults=_SETTINGS)
    assert keyring.get_password(isolated_service, credential) == before


def test_a_deleted_real_credential_is_gone_and_the_gateway_says_so(isolated_service: str, credential: str, tmp_path: Path) -> None:
    _literal, config, _refusal = sc.read(_setup(tmp_path).parent)
    assert config is not None
    keyring.delete_password(isolated_service, credential)
    assert keyring.get_password(isolated_service, credential) is None  # the native backend reports the deletion
    service = memory_store.build_memory_store_service(config, keyring_backend=keyring, hmac_key=b"k" * 32)
    assert service.handle(b'{"op":"capabilities"}', deadline=time.monotonic() + 1) == (503, msc.error_body("MEMORY_STORE_CREDENTIAL_MISSING"))
