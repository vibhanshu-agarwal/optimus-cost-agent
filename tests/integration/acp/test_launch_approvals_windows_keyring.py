"""#433: approval records round-trip through the real Windows Credential Manager.

Runs only on Windows with `-m requires_os_keyring_write`. Every entry lives under a random, isolated test service name
(never `optimus-cost-agent-approvals`), the store gets an explicit HMAC key so the real HMAC entry is never read or
written, and every created entry is deleted and confirmed absent. Assertions print lengths and codes only.
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from optimus.acp.launch_approvals import (
    MAX_APPROVAL_RECORD_BYTES,
    MAX_KEYRING_VALUE_UTF16_BYTES,
    ApprovalError,
    KeyringApprovalStore,
    serialize_approval_record,
)
from tests.unit.acp.test_launch_approvals_multipart import _HMAC_KEY, _record

pytestmark = [
    pytest.mark.requires_os_keyring_write,
    pytest.mark.skipif(sys.platform != "win32", reason="the Windows Credential Manager is the backend under test"),
]


@pytest.fixture
def windows_store(tmp_path: Path) -> Iterator[tuple[KeyringApprovalStore, object, list[str]]]:
    from keyring.backends.Windows import WinVaultKeyring

    service = f"optimus-p433-test-{secrets.token_hex(8)}"
    assert service != KeyringApprovalStore._service_name
    backend = WinVaultKeyring()
    touched: list[str] = []

    class _Recording:
        def get_password(self, svc: str, key: str) -> str | None:
            assert svc == service
            return backend.get_password(svc, key)

        def set_password(self, svc: str, key: str, value: str) -> None:
            assert svc == service
            touched.append(key)
            backend.set_password(svc, key, value)

        def delete_password(self, svc: str, key: str) -> None:
            assert svc == service
            backend.delete_password(svc, key)

    class _IsolatedStore(KeyringApprovalStore):
        _service_name = service

    store = _IsolatedStore(keyring_backend=_Recording(), runtime_root=tmp_path, hmac_key=_HMAC_KEY)
    try:
        yield store, backend, touched
    finally:
        for key in set(touched):
            try:
                backend.delete_password(service, key)
            except Exception:  # noqa: BLE001, S110 - already absent; confirmed below
                pass
        assert all(backend.get_password(service, key) is None for key in set(touched)), "test entries left behind"


def test_the_real_backend_refuses_one_character_over_the_blob_limit(windows_store) -> None:
    store, backend, touched = windows_store
    service = store._service_name
    limit_chars = MAX_KEYRING_VALUE_UTF16_BYTES // 2
    touched.extend(["probe-at-limit", "probe-over-limit"])

    backend.set_password(service, "probe-at-limit", "x" * limit_chars)
    with pytest.raises(Exception) as refused:
        backend.set_password(service, "probe-over-limit", "x" * (limit_chars + 1))

    assert (getattr(refused.value, "funcname", None), getattr(refused.value, "winerror", None)) == ("CredWrite", 1783)


@pytest.mark.parametrize("chars", [1280, 1281, MAX_APPROVAL_RECORD_BYTES])
def test_a_durable_record_round_trips_replaces_and_revokes(windows_store, chars: int) -> None:
    store, backend, touched = windows_store
    record = _record(chars)
    store.write_durable(record)
    assert store.read_durable(record.workspace_digest) == record
    assert len([key for key in set(touched) if "#" in key]) == (0 if chars <= 1280 else 2)

    replacement = _record(MAX_APPROVAL_RECORD_BYTES)
    store.write_durable(replacement)
    assert store.read_durable(replacement.workspace_digest) == replacement

    store.revoke_workspace(record.workspace_digest)
    assert store.read_durable(record.workspace_digest) is None
    assert all(backend.get_password(store._service_name, key) is None for key in set(touched))


def test_a_policy_sized_one_shot_is_consumed_once(windows_store) -> None:
    store, backend, touched = windows_store
    record = _record(MAX_APPROVAL_RECORD_BYTES, mode="one-shot")
    assert len(serialize_approval_record(record).encode("utf-16-le")) > MAX_KEYRING_VALUE_UTF16_BYTES
    handle = store.write_one_shot(record, secrets.token_bytes(32))

    assert store.consume_one_shot(handle, record.security_snapshot_digest) == record
    with pytest.raises(ApprovalError) as again:
        store.consume_one_shot(handle, record.security_snapshot_digest)
    assert again.value.code == "ONE_SHOT_NOT_FOUND"
    assert all(backend.get_password(store._service_name, key) is None for key in set(touched))
