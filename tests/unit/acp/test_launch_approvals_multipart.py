"""#433: approval records that exceed one Windows credential blob are stored as bounded parts.

Windows caps a credential blob at 2,560 bytes and the keyring backend writes UTF-16-LE, so a record over 1,280
characters crashed `CredWrite` with winerror 1783. `WindowsLimitKeyring` enforces that rule on every platform, so these
unit tests are also the off-Windows regression check. The real Windows round trip is in
`tests/integration/acp/test_launch_approvals_windows_keyring.py`.
"""

from __future__ import annotations

import base64
import errno
import json
import secrets
import sys
import threading
import zlib
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from optimus.acp import launch_approvals
from optimus.acp.launch_approvals import (
    MAX_APPROVAL_RECORD_BYTES,
    MAX_KEYRING_VALUE_UTF16_BYTES,
    ONE_SHOT_TTL_SECONDS,
    ApprovalError,
    ApprovalRecord,
    KeyringApprovalStore,
    build_approval_record,
    compute_record_hmac,
    serialize_approval_record,
)
from optimus.acp.trusted_paths import WorkspaceIdentity, absent_git_context
from tests.unit.acp.test_launch_approvals import FakeKeyring

_SERVICE = "optimus-cost-agent-approvals"
_HMAC_KEY = b"p433-multipart-hmac-key-32-byte"
_URL_VALUE = "http://127.0.0.1:8790/api/v1"
_FINGERPRINT = "fp_" + "9" * 61


class _CredWriteError(Exception):
    """Shaped like pywin32-ctypes' error for CredWrite 1783."""

    def __init__(self) -> None:
        super().__init__(1783, "CredWrite", "The stub received bad data")
        self.winerror = 1783
        self.funcname = "CredWrite"


class _Crash(BaseException):
    """A process death: no `except Exception` handler runs."""


class WindowsLimitKeyring(FakeKeyring):
    """FakeKeyring with the Windows credential-blob limit and an optional fault hook run before each call."""

    def __init__(self) -> None:
        super().__init__()
        self.hook: Callable[[str, str], None] | None = None

    def _run_hook(self, op: str, key: str) -> None:
        if self.hook is not None:
            self.hook(op, key)

    def get_password(self, service: str, key: str) -> str | None:
        self._run_hook("get", key)
        return super().get_password(service, key)

    def set_password(self, service: str, key: str, value: str) -> None:
        self._run_hook("set", key)
        if len(value.encode("utf-16-le")) > MAX_KEYRING_VALUE_UTF16_BYTES:
            raise _CredWriteError()
        super().set_password(service, key, value)

    def delete_password(self, service: str, key: str) -> None:
        self._run_hook("delete", key)
        super().delete_password(service, key)

    def keys(self) -> set[str]:
        return {key for (_service, key) in self._store}


def _identity(digest: str = "a" * 64) -> WorkspaceIdentity:
    return WorkspaceIdentity(
        format_version=3,
        lexical_path="/tmp/p433-workspace",
        canonical_path="/tmp/p433-workspace",
        device=4,
        inode=33,
        git_context=absent_git_context(),
        digest=digest,
    )


def _record(
    chars: int | None = None,
    *,
    mode: str = "durable",
    digest: str = "a" * 64,
    created_at: datetime | None = None,
) -> ApprovalRecord:
    """A record whose canonical JSON is exactly `chars` characters, padded with incompressible URL-safe text."""
    record = build_approval_record(
        mode=mode,
        workspace_identity=_identity(digest),
        security_literals={"OPTIMUS_LOCAL_GATEWAY_BASE_URL": _URL_VALUE, "OPTIMUS_AGENT_MODEL": "auto"},
        secret_fingerprints={"OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY": _FINGERPRINT},
        monotonic_grants={"OPTIMUS_MAX_PLANNING_TURNS": "5"},
        model_observation=None,
        hmac_key=_HMAC_KEY,
        override_created_at=created_at,
    )
    if chars is not None:
        pad = chars - len(serialize_approval_record(record)) + len("null") - len('""')
        record = replace(record, model_observation=secrets.token_urlsafe(pad)[:pad])
        record = replace(record, record_hmac=compute_record_hmac(record, hmac_key=_HMAC_KEY))
        assert len(serialize_approval_record(record)) == chars
    return record


def _store(tmp_path: Path, keyring: FakeKeyring) -> KeyringApprovalStore:
    return KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)


def _part_keys(keyring: WindowsLimitKeyring, publication_key: str) -> set[str]:
    return {key for key in keyring.keys() if key.startswith(publication_key + "#")}


def _manifest(keyring: WindowsLimitKeyring, publication_key: str) -> dict:
    data = json.loads(keyring.get_password(_SERVICE, publication_key) or "null")
    assert isinstance(data, dict) and "approval_parts" in data
    return data


def _assert_safe_diagnostic(error: ApprovalError, record: ApprovalRecord) -> None:
    text = str(error)
    for leaked in (_URL_VALUE, _FINGERPRINT, record.record_hmac, record.approval_id, "{", _HMAC_KEY.decode()):
        assert leaked not in text, f"diagnostic leaks {leaked!r}: {text}"


@pytest.fixture(autouse=True)
def _short_lock_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launch_approvals, "_LOCK_WAIT_SECONDS", 0.05)


# --- Size boundaries ---------------------------------------------------------------------------------------------


def test_a_record_that_fits_one_blob_stays_a_single_inline_entry(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(1280)
    _store(tmp_path, keyring).write_durable(record)

    assert keyring.get_password(_SERVICE, f"durable:{record.workspace_digest}") == serialize_approval_record(record)
    assert _part_keys(keyring, f"durable:{record.workspace_digest}") == set()
    assert _store(tmp_path, keyring).read_durable(record.workspace_digest) == record


@pytest.mark.parametrize("chars", [1281, 1500, MAX_APPROVAL_RECORD_BYTES])
def test_a_record_over_one_blob_is_stored_as_two_bounded_parts_and_reads_back(tmp_path: Path, chars: int) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(chars)
    _store(tmp_path, keyring).write_durable(record)

    key = f"durable:{record.workspace_digest}"
    manifest = _manifest(keyring, key)
    parts = _part_keys(keyring, key)
    assert len(parts) == 2 and all(manifest["generation"] in part for part in parts)
    for stored_key in {key, *parts}:
        assert len(keyring.get_password(_SERVICE, stored_key).encode("utf-16-le")) <= MAX_KEYRING_VALUE_UTF16_BYTES
    assert _store(tmp_path, keyring).read_durable(record.workspace_digest) == record


def test_compression_would_not_have_fit_the_policy_sized_record(tmp_path: Path) -> None:
    serialized = serialize_approval_record(_record(MAX_APPROVAL_RECORD_BYTES)).encode("utf-8")
    compressed = base64.b64encode(zlib.compress(serialized, 9)).decode("ascii")
    assert len(compressed.encode("utf-16-le")) > MAX_KEYRING_VALUE_UTF16_BYTES


def test_a_record_over_the_policy_limit_is_refused_by_setting_name_without_values(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(MAX_APPROVAL_RECORD_BYTES + 1)

    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(record)

    assert refused.value.code == "RECORD_TOO_LARGE"
    assert "OPTIMUS_LOCAL_GATEWAY_BASE_URL" in refused.value.detail and "OPTIMUS_MAX_PLANNING_TURNS" in refused.value.detail
    _assert_safe_diagnostic(refused.value, record)
    assert keyring.keys() == set()


# --- Fail closed on missing, mixed, oversized or corrupt parts ---------------------------------------------------


def _written(tmp_path: Path, chars: int = 1600) -> tuple[WindowsLimitKeyring, ApprovalRecord, str]:
    keyring = WindowsLimitKeyring()
    record = _record(chars)
    _store(tmp_path, keyring).write_durable(record)
    return keyring, record, f"durable:{record.workspace_digest}"


def _read_code(tmp_path: Path, keyring: WindowsLimitKeyring, record: ApprovalRecord) -> str:
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable(record.workspace_digest)
    _assert_safe_diagnostic(refused.value, record)
    return refused.value.code


def test_a_missing_part_fails_closed(tmp_path: Path) -> None:
    keyring, record, key = _written(tmp_path)
    keyring.delete_password(_SERVICE, sorted(_part_keys(keyring, key))[1])
    assert _read_code(tmp_path, keyring, record) == "RECORD_CORRUPT"


def test_a_tampered_part_of_the_same_length_fails_closed(tmp_path: Path) -> None:
    keyring, record, key = _written(tmp_path)
    part = sorted(_part_keys(keyring, key))[1]
    value = keyring.get_password(_SERVICE, part)
    keyring.set_password(_SERVICE, part, value[:-2] + ("ab" if value[-2:] != "ab" else "cd"))
    assert _read_code(tmp_path, keyring, record) == "INTEGRITY_FAILURE"


def test_a_part_from_another_generation_fails_closed(tmp_path: Path) -> None:
    keyring, first, key = _written(tmp_path)
    old_part_1 = keyring.get_password(_SERVICE, sorted(_part_keys(keyring, key))[1])
    second = _record(1600)
    _store(tmp_path, keyring).write_durable(second)
    new_part_1 = sorted(_part_keys(keyring, key))[1]
    keyring.set_password(_SERVICE, new_part_1, old_part_1)
    assert _read_code(tmp_path, keyring, second) == "INTEGRITY_FAILURE"


def test_a_part_whose_length_differs_from_the_manifest_fails_closed(tmp_path: Path) -> None:
    keyring, record, key = _written(tmp_path)
    part = sorted(_part_keys(keyring, key))[0]
    keyring.set_password(_SERVICE, part, keyring.get_password(_SERVICE, part) + "x")
    assert _read_code(tmp_path, keyring, record) == "RECORD_CORRUPT"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda m: m.update(manifest_hmac="0" * 64), id="hmac"),
        pytest.param(lambda m: m.update(workspace_digest="b" * 64), id="workspace-digest"),
        pytest.param(lambda m: m.update(legacy_source_digest="c" * 64), id="legacy-source"),
    ],
)
def test_a_manifest_that_fails_its_hmac_fails_closed(tmp_path: Path, mutate: Callable[[dict], None]) -> None:
    keyring, record, key = _written(tmp_path)
    manifest = _manifest(keyring, key)
    mutate(manifest)
    keyring.set_password(_SERVICE, key, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    assert _read_code(tmp_path, keyring, record) == "INTEGRITY_FAILURE"


def test_a_manifest_moved_to_another_publication_key_fails_closed(tmp_path: Path) -> None:
    keyring, record, key = _written(tmp_path)
    other = "b" * 64
    keyring.set_password(_SERVICE, f"durable:{other}", keyring.get_password(_SERVICE, key))
    for part in _part_keys(keyring, key):
        keyring.set_password(_SERVICE, part.replace(key, f"durable:{other}"), keyring.get_password(_SERVICE, part))
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable(other)
    assert refused.value.code == "INTEGRITY_FAILURE"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda m: m.update(extra="x"), id="extra-field"),
        pytest.param(lambda m: m.update(approval_parts=2), id="unknown-version"),
        pytest.param(lambda m: m.update(part_lengths=[1, 1, 1]), id="three-parts"),
        pytest.param(lambda m: m.update(part_lengths=[]), id="no-parts"),
        pytest.param(lambda m: m.update(generation="../x"), id="bad-generation"),
        pytest.param(lambda m: m.pop("payload_sha256"), id="missing-field"),
    ],
)
def test_a_malformed_manifest_fails_closed(tmp_path: Path, mutate: Callable[[dict], None]) -> None:
    keyring, record, key = _written(tmp_path)
    manifest = _manifest(keyring, key)
    mutate(manifest)
    keyring.set_password(_SERVICE, key, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    assert _read_code(tmp_path, keyring, record) == "RECORD_CORRUPT"


def _signed_manifest(
    key: str, parts: list[str], *, workspace_digest: str = "a" * 64, legacy_source_digest: str | None = None
) -> str:
    """A correctly signed manifest over arbitrary parts, as only a holder of the store key could write."""
    import hashlib

    body = {
        "approval_parts": 1,
        "generation": "f" * 32,
        "legacy_source_digest": legacy_source_digest,
        "part_lengths": [len(part) for part in parts],
        "payload_sha256": hashlib.sha256("".join(parts).encode("utf-8")).hexdigest(),
        "workspace_digest": workspace_digest,
    }
    body["manifest_hmac"] = launch_approvals._manifest_hmac(body, publication_key=key, hmac_key=_HMAC_KEY)
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param(["x" * (MAX_KEYRING_VALUE_UTF16_BYTES // 2 + 1), "y"], id="part-over-one-blob"),
        pytest.param(["x" * 1000, "y" * (MAX_APPROVAL_RECORD_BYTES - 999)], id="payload-over-policy"),
    ],
)
def test_signed_but_oversized_parts_fail_closed(tmp_path: Path, parts: list[str]) -> None:
    keyring = FakeKeyring()  # no blob limit, so the oversized part can exist
    key = "durable:" + "a" * 64
    keyring.set_password(_SERVICE, key, _signed_manifest(key, parts))
    for index, part in enumerate(parts):
        keyring.set_password(_SERVICE, f"{key}#{'f' * 32}:{index}", part)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable("a" * 64)
    assert refused.value.code == "RECORD_CORRUPT"


def test_existing_single_entry_records_still_read(tmp_path: Path) -> None:
    keyring = FakeKeyring()
    record = _record()
    keyring.set_password(_SERVICE, f"durable:{record.workspace_digest}", serialize_approval_record(record))
    assert _store(tmp_path, keyring).read_durable(record.workspace_digest) == record


# --- Interrupted replacement keeps the previous approval ---------------------------------------------------------


def _fail_on(keyring: WindowsLimitKeyring, op: str, key_matches: Callable[[str], bool], *, error: BaseException) -> None:
    def hook(called_op: str, key: str) -> None:
        if called_op == op and key_matches(key):
            raise error

    keyring.hook = hook


@pytest.mark.parametrize(
    "failing_key",
    [
        pytest.param(lambda key: key.endswith(":0") and "#" in key, id="part-0"),
        pytest.param(lambda key: key.endswith(":1") and "#" in key, id="part-1"),
        pytest.param(lambda key: "#" not in key, id="manifest"),
    ],
)
def test_a_failed_replacement_keeps_the_previous_approval_and_leaves_no_new_parts(
    tmp_path: Path, failing_key: Callable[[str], bool]
) -> None:
    keyring, previous, key = _written(tmp_path)
    previous_parts = _part_keys(keyring, key)
    _fail_on(keyring, "set", failing_key, error=_CredWriteError())

    replacement = _record(1700)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(replacement)

    assert refused.value.code == "APPROVAL_STORE_WRITE_FAILED"
    assert "CredWrite" in refused.value.detail and "1783" in refused.value.detail
    _assert_safe_diagnostic(refused.value, replacement)
    keyring.hook = None
    assert _part_keys(keyring, key) == previous_parts
    assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == previous


def test_a_publication_that_reads_back_differently_is_rolled_back(tmp_path: Path) -> None:
    class _CorruptsOnePublication(WindowsLimitKeyring):
        armed = False

        def set_password(self, service: str, key: str, value: str) -> None:
            if self.armed and "#" not in key:
                self.armed = False  # the rollback write is stored faithfully
                value = value[:-1] + ',"x":0}'
            super().set_password(service, key, value)

    keyring = _CorruptsOnePublication()
    previous = _record(1600)
    _store(tmp_path, keyring).write_durable(previous)
    key = f"durable:{previous.workspace_digest}"
    previous_parts = _part_keys(keyring, key)
    keyring.armed = True

    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(_record(1700))

    assert refused.value.code == "APPROVAL_STORE_WRITE_FAILED"
    assert _part_keys(keyring, key) == previous_parts
    assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == previous


def test_a_crash_before_publication_leaves_the_previous_approval_active(tmp_path: Path) -> None:
    keyring, previous, key = _written(tmp_path)
    _fail_on(keyring, "set", lambda k: k == key, error=_Crash())

    with pytest.raises(_Crash):
        _store(tmp_path, keyring).write_durable(_record(1700))

    keyring.hook = None
    assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == previous


def test_a_store_then_fail_first_write_leaves_no_approval(tmp_path: Path) -> None:
    class _StoreThenFail(WindowsLimitKeyring):
        def set_password(self, service: str, key: str, value: str) -> None:
            super().set_password(service, key, value)
            if "#" not in key:
                raise _CredWriteError()

    keyring = _StoreThenFail()
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(_record(1600))
    assert refused.value.code == "APPROVAL_STORE_WRITE_FAILED"
    assert keyring.keys() == set()


def test_a_successful_replacement_removes_the_previous_generation(tmp_path: Path) -> None:
    keyring, _previous, key = _written(tmp_path)
    replacement = _record(1700)
    _store(tmp_path, keyring).write_durable(replacement)
    assert all(_manifest(keyring, key)["generation"] in part for part in _part_keys(keyring, key))
    assert len(_part_keys(keyring, key)) == 2
    small = _record()
    _store(tmp_path, keyring).write_durable(small)
    assert _part_keys(keyring, key) == set()
    assert _store(tmp_path, keyring).read_durable(small.workspace_digest) == small


# --- Coordinated locking -------------------------------------------------------------------------------------------


def _during_part_read(keyring: WindowsLimitKeyring, action: Callable[[], None]) -> list[str]:
    """Run `action` once, while the first operation is reading part 1; report the ApprovalError codes it raised."""
    codes: list[str] = []

    def hook(op: str, key: str) -> None:
        if op == "get" and key.endswith(":1") and "#" in key and not codes:
            keyring.hook = None
            try:
                action()
                codes.append("ran")
            except ApprovalError as exc:
                codes.append(exc.code)

    keyring.hook = hook
    return codes


@pytest.mark.parametrize("other", ["revoke", "replace", "read", "other-workspace", "one-shot-write", "grant-write", "rotate-key"])
def test_a_durable_read_excludes_every_other_approvals_service_operation(tmp_path: Path, other: str) -> None:
    keyring, record, _key = _written(tmp_path)
    other_store = _store(tmp_path, keyring)
    grant = launch_approvals.DiagnosticGrant(
        grant_id="grant_p433",
        workspace_digest=record.workspace_digest,
        approval_id=record.approval_id,
        launch_session_id="sess_p433",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
        record_hmac="0" * 64,
    )
    action = {
        "revoke": lambda: other_store.revoke_workspace(record.workspace_digest),
        "replace": lambda: other_store.write_durable(_record(1700)),
        "read": lambda: other_store.read_durable(record.workspace_digest),
        "other-workspace": lambda: other_store.write_durable(_record(digest="b" * 64)),
        "one-shot-write": lambda: other_store.write_one_shot(_record(mode="one-shot"), b"\x0a" * 32),
        "grant-write": lambda: other_store.write_diagnostic_grant(grant),
        "rotate-key": other_store.rotate_hmac_key,
    }[other]
    codes = _during_part_read(keyring, action)

    assert _store(tmp_path, keyring).read_durable(record.workspace_digest) == record
    assert codes == ["LOCK_CONTENTION"]
    assert _store(tmp_path, keyring).read_durable(record.workspace_digest) == record


@pytest.mark.parametrize("other", ["revoke", "read"])
def test_a_one_shot_consume_excludes_revocation_and_readers(tmp_path: Path, other: str) -> None:
    keyring = WindowsLimitKeyring()
    durable = _record(1600)
    one_shot = _record(1600, mode="one-shot")
    store = _store(tmp_path, keyring)
    store.write_durable(durable)
    handle = store.write_one_shot(one_shot, b"\x07" * 32)
    other_store = _store(tmp_path, keyring)
    action = {
        "revoke": lambda: other_store.revoke_workspace(durable.workspace_digest),
        "read": lambda: other_store.read_durable(durable.workspace_digest),
    }[other]

    codes: list[str] = []

    def hook(op: str, key: str) -> None:
        if op == "get" and key.startswith("oneshot:") and key.endswith(":1") and not codes:
            keyring.hook = None
            try:
                action()
                codes.append("ran")
            except ApprovalError as exc:
                codes.append(exc.code)

    keyring.hook = hook
    assert store.consume_one_shot(handle, one_shot.security_snapshot_digest) == one_shot
    assert codes == ["LOCK_CONTENTION"]


def test_concurrent_consumers_of_a_multipart_one_shot_have_exactly_one_winner(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(1700, mode="one-shot")
    handle = _store(tmp_path, keyring).write_one_shot(record, b"\x09" * 32)
    results: list[str] = []
    guard = threading.Lock()

    def consume() -> None:
        try:
            _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)
            outcome = "success"
        except ApprovalError as exc:
            outcome = exc.code
        with guard:
            results.append(outcome)

    threads = [threading.Thread(target=consume) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count("success") == 1
    assert set(results) <= {"success", "ONE_SHOT_NOT_FOUND", "LOCK_CONTENTION"}
    assert keyring.keys() == set()


# --- Lifecycle: one-shot, migration, revocation -------------------------------------------------------------------


def test_a_multipart_one_shot_is_consumed_once_and_removed_completely(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(1800, mode="one-shot")
    store = _store(tmp_path, keyring)
    handle = store.write_one_shot(record, b"\x05" * 32)
    assert len(_part_keys(keyring, f"oneshot:{handle}")) == 2

    assert store.consume_one_shot(handle, record.security_snapshot_digest) == record
    assert keyring.keys() == set()
    with pytest.raises(ApprovalError) as again:
        store.consume_one_shot(handle, record.security_snapshot_digest)
    assert again.value.code == "ONE_SHOT_NOT_FOUND"


def test_an_expired_multipart_one_shot_is_removed_completely(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(1700, mode="one-shot", created_at=datetime.now(timezone.utc) - timedelta(seconds=ONE_SHOT_TTL_SECONDS + 5))
    store = _store(tmp_path, keyring)
    handle = store.write_one_shot(record, b"\x06" * 32)

    with pytest.raises(ApprovalError) as expired:
        store.consume_one_shot(handle, record.security_snapshot_digest)
    assert expired.value.code == "APPROVAL_EXPIRED"
    assert keyring.keys() == set()


def test_a_one_shot_whose_record_names_another_workspace_than_its_manifest_is_refused(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    record = _record(1700, mode="one-shot")
    key = "oneshot:p996_forged"
    payload = serialize_approval_record(record)
    parts = [payload[:850], payload[850:]]
    manifest = json.loads(_signed_manifest(key, parts, workspace_digest="b" * 64))
    keyring.set_password(_SERVICE, key, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    for index, part in enumerate(parts):
        keyring.set_password(_SERVICE, f"{key}#{'f' * 32}:{index}", part)

    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).consume_one_shot("p996_forged", record.security_snapshot_digest)
    assert refused.value.code == "INTEGRITY_FAILURE"
    assert keyring.get_password(_SERVICE, key) is not None


def _legacy_record(chars: int, *, legacy_digest: str = "c" * 64) -> ApprovalRecord:
    """A schema-1 durable record bound to a v2 (legacy) workspace digest."""
    base = replace(_record(chars), schema_version=1, identity_format_version=2, workspace_digest=legacy_digest)
    return replace(base, record_hmac=compute_record_hmac(base, hmac_key=_HMAC_KEY))


def _promote(store: KeyringApprovalStore, legacy: ApprovalRecord, current: WorkspaceIdentity):
    return store.lookup_durable(
        current_identity=current,
        legacy_workspace_digest=legacy.workspace_digest,
        expected_legacy_snapshot_digest=legacy.security_snapshot_digest,
        current_security_snapshot_digest="f" * 64,
    )


def _migrated(tmp_path: Path) -> tuple[WindowsLimitKeyring, ApprovalRecord, WorkspaceIdentity]:
    keyring = WindowsLimitKeyring()
    legacy = _legacy_record(1200)
    serialized_legacy = serialize_approval_record(legacy)
    assert len(serialized_legacy) <= 1280
    keyring.set_password(_SERVICE, f"durable:{legacy.workspace_digest}", serialized_legacy)
    current = _identity("d" * 64)
    lookup = _promote(_store(tmp_path, keyring), legacy, current)
    assert lookup.state == "migrated" and lookup.record is not None
    return keyring, legacy, current


def test_migration_of_a_large_legacy_record_publishes_a_multipart_v3_with_its_legacy_source(tmp_path: Path) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    manifest = _manifest(keyring, f"durable:{current.digest}")
    assert manifest["legacy_source_digest"] == legacy.workspace_digest

    again = _promote(_store(tmp_path, keyring), legacy, current)
    assert again.state == "migrated" and again.record.approval_id == legacy.approval_id


@pytest.mark.parametrize("damage_part", [False, True])
def test_revoking_a_migrated_multipart_record_removes_it_and_its_legacy_source_for_good(tmp_path: Path, damage_part: bool) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    key = f"durable:{current.digest}"
    if damage_part:
        keyring.delete_password(_SERVICE, sorted(_part_keys(keyring, key))[0])

    _store(tmp_path, keyring).revoke_workspace(current.digest)

    assert keyring.keys() == set()
    assert _promote(_store(tmp_path, keyring), legacy, current).state == "legacy_reapproval_required"


def test_a_crash_during_revocation_never_lets_the_legacy_source_revive(tmp_path: Path) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    key = f"durable:{current.digest}"
    _fail_on(keyring, "delete", lambda k: k == key, error=_Crash())

    with pytest.raises(_Crash):
        _store(tmp_path, keyring).revoke_workspace(current.digest)

    keyring.hook = None
    assert keyring.get_password(_SERVICE, f"durable:{legacy.workspace_digest}") is None
    still_active = _promote(_store(tmp_path, keyring), legacy, current)
    assert still_active.state == "migrated"  # the v3 record, not a re-promotion
    _store(tmp_path, keyring).revoke_workspace(current.digest)
    assert keyring.keys() == set()


def test_revoking_an_absent_approval_succeeds_on_a_backend_that_refuses_missing_deletes(tmp_path: Path) -> None:
    from keyring.errors import PasswordDeleteError

    class _StrictDelete(WindowsLimitKeyring):
        def delete_password(self, service: str, key: str) -> None:
            if super().get_password(service, key) is None:
                raise PasswordDeleteError(service)
            super().delete_password(service, key)

    _store(tmp_path, _StrictDelete()).revoke_workspace("a" * 64)


# --- Typed backend failures ----------------------------------------------------------------------------------------


class _OddBackendError(Exception):
    def __init__(self) -> None:
        super().__init__("message quoting a stored value")
        self.funcname = "message quoting a stored value"
        self.winerror = "1783 plus a stored value"


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        pytest.param(RuntimeError("message quoting a stored value"), "keyring backend RuntimeError", id="plain"),
        pytest.param(_CredWriteError(), "keyring backend _CredWriteError (CredWrite, winerror 1783)", id="win32"),
        pytest.param(_OddBackendError(), "keyring backend _OddBackendError", id="unlisted-attributes"),
    ],
)
def test_a_backend_failure_is_typed_and_its_traceback_carries_no_backend_message(
    tmp_path: Path, error: Exception, detail: str
) -> None:
    import traceback

    keyring, record, _key = _written(tmp_path)
    _fail_on(keyring, "get", lambda _k: True, error=error)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable(record.workspace_digest)

    assert (refused.value.code, refused.value.detail) == ("APPROVAL_STORE_READ_FAILED", detail)
    assert refused.value.__cause__ is None and refused.value.__suppress_context__
    assert "stored value" not in "".join(traceback.format_exception(refused.value))
    _assert_safe_diagnostic(refused.value, record)


def test_a_backend_failure_reading_the_hmac_key_is_typed(tmp_path: Path) -> None:
    keyring = WindowsLimitKeyring()
    _fail_on(keyring, "get", lambda _k: True, error=RuntimeError("message quoting a stored value"))
    with pytest.raises(ApprovalError) as refused:
        KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path)
    assert refused.value.code == "APPROVAL_STORE_READ_FAILED"


# --- #433 r2: the Windows shared-slot resurrection --------------------------------------------------------------


class WinVaultModelKeyring(WindowsLimitKeyring):
    """WinVaultKeyring's shared service slot: set_password captures the slot's occupant, re-saves it under its
    compound name, then writes the new entry into the slot. `after_capture` runs once, between capture and re-save."""

    def __init__(self) -> None:
        super().__init__()
        self.slot: tuple[str, str] | None = None
        self.compound: dict[str, str] = {}
        self.after_capture: Callable[[], None] | None = None

    def get_password(self, service: str, key: str) -> str | None:
        self._run_hook("get", key)
        if self.slot is not None and self.slot[0] == key:
            return self.slot[1]
        return self.compound.get(key)

    def set_password(self, service: str, key: str, value: str) -> None:
        self._run_hook("set", key)
        if len(value.encode("utf-16-le")) > MAX_KEYRING_VALUE_UTF16_BYTES:
            raise _CredWriteError()
        captured = self.slot
        if self.after_capture is not None:
            hook, self.after_capture = self.after_capture, None
            hook()
        if captured is not None:
            self.compound[captured[0]] = captured[1]
        self.slot = (key, value)

    def delete_password(self, service: str, key: str) -> None:
        from keyring.errors import PasswordDeleteError

        self._run_hook("delete", key)
        deleted = False
        if self.slot is not None and self.slot[0] == key:
            self.slot, deleted = None, True
        if self.compound.pop(key, None) is not None:
            deleted = True
        if not deleted:
            raise PasswordDeleteError(service)

    def keys(self) -> set[str]:
        return ({self.slot[0]} if self.slot else set()) | set(self.compound)


def test_the_slot_model_reproduces_the_backend_resurrection_without_the_store() -> None:
    keyring = WinVaultModelKeyring()
    keyring.set_password(_SERVICE, "oneshot:a", "approval A")

    def delete_a() -> None:
        keyring.delete_password(_SERVICE, "oneshot:a")
        assert keyring.get_password(_SERVICE, "oneshot:a") is None

    keyring.after_capture = delete_a
    keyring.set_password(_SERVICE, "unrelated", "B")

    assert keyring.get_password(_SERVICE, "oneshot:a") == "approval A"  # deleted, confirmed, and back


@pytest.mark.parametrize("deleter", ["consume", "revoke"])
def test_a_store_write_excludes_deletes_so_no_approval_is_resurrected(tmp_path: Path, deleter: str) -> None:
    keyring = WinVaultModelKeyring()
    store = _store(tmp_path, keyring)
    one_shot = _record(mode="one-shot")
    handle = store.write_one_shot(one_shot, b"\x0b" * 32)
    durable = _record(digest="b" * 64)
    if deleter == "revoke":
        store.write_durable(durable)
    victim = f"oneshot:{handle}" if deleter == "consume" else f"durable:{durable.workspace_digest}"
    assert keyring.slot is not None and keyring.slot[0] == victim

    other = _store(tmp_path, keyring)
    delete = {
        "consume": lambda: other.consume_one_shot(handle, one_shot.security_snapshot_digest),
        "revoke": lambda: other.revoke_workspace(durable.workspace_digest),
    }[deleter]
    codes: list[str] = []

    def attempt() -> None:
        try:
            delete()
            codes.append("ran")
        except ApprovalError as exc:
            codes.append(exc.code)

    keyring.after_capture = attempt
    store.write_durable(_record(digest="c" * 64))

    assert codes == ["LOCK_CONTENTION"]
    delete()
    assert keyring.get_password(_SERVICE, victim) is None
    store.write_durable(_record(digest="d" * 64))  # a later writer finds nothing of the victim to re-save
    assert keyring.get_password(_SERVICE, victim) is None


# --- #433 r2: rollback outcomes -----------------------------------------------------------------------------------


class _PublicationFaults(WindowsLimitKeyring):
    """Once armed, each write of a publication key (not a part) takes the next behaviour from `sets`."""

    def __init__(self, sets: list[str], *, deletes_work: bool = True, part_deletes_work: bool = True) -> None:
        super().__init__()
        self.armed = False
        self.sets = sets
        self.deletes_work = deletes_work
        self.part_deletes_work = part_deletes_work

    def set_password(self, service: str, key: str, value: str) -> None:
        if self.armed and "#" not in key and self.sets:
            behaviour = self.sets.pop(0)
            if behaviour == "store-then-fail":
                super().set_password(service, key, value)
            raise _CredWriteError()
        super().set_password(service, key, value)

    def delete_password(self, service: str, key: str) -> None:
        works = self.part_deletes_work if "#" in key else self.deletes_work
        if self.armed and not works:
            return  # reports success, deletes nothing
        super().delete_password(service, key)


@pytest.mark.parametrize("part_deletes_work", [True, False], ids=["cleanup-ok", "cleanup-fails"])
@pytest.mark.parametrize("new_chars", [None, 1700], ids=["new-inline", "new-parts"])
@pytest.mark.parametrize(
    ("sets", "deletes_work", "code", "outcome"),
    [
        pytest.param(["store-then-fail", "store-then-fail"], True, "APPROVAL_STORE_WRITE_FAILED", "unchanged", id="restored"),
        pytest.param(["store-then-fail", "fail"], True, "APPROVAL_STORE_WRITE_FAILED", "removed", id="removed"),
        pytest.param(["store-then-fail", "fail"], False, "APPROVAL_STORE_STATE_UNKNOWN", "unknown", id="unknown"),
    ],
)
def test_a_failed_publication_reports_a_confirmed_rollback_outcome(
    tmp_path: Path,
    sets: list[str],
    deletes_work: bool,
    code: str,
    outcome: str,
    new_chars: int | None,
    part_deletes_work: bool,
) -> None:
    keyring = _PublicationFaults(list(sets), deletes_work=deletes_work, part_deletes_work=part_deletes_work)
    previous = _record(1600)
    _store(tmp_path, keyring).write_durable(previous)
    key = f"durable:{previous.workspace_digest}"
    previous_parts = _part_keys(keyring, key)
    replacement = _record(new_chars)
    keyring.armed = True

    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(replacement)

    assert refused.value.code == code  # a cleanup failure never replaces or masks the outcome
    _assert_safe_diagnostic(refused.value, previous)
    keyring.armed = False
    if outcome == "unchanged":
        assert refused.value.detail.endswith("; previous approval unchanged")
        assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == previous
        assert previous_parts <= _part_keys(keyring, key)
    elif outcome == "removed":
        assert refused.value.detail.endswith("; the previous approval could not be restored and was removed; approve again")
        assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) is None
        if part_deletes_work:
            assert keyring.keys() == set()
    else:
        assert "could not be restored or removed, so it may hold the new approval, the previous one, or none" in refused.value.detail
        if new_chars is None or not part_deletes_work:
            # Nothing invalidated it: an inline value has no parts, and failed cleanup left the new parts.
            assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == replacement
        else:
            assert _read_code(tmp_path, keyring, previous) == "RECORD_CORRUPT"


def test_a_failure_before_publication_never_touches_the_previous_approval_even_when_reads_then_fail(tmp_path: Path) -> None:
    """Fable checkpoint finding 1: a confirming read is not needed for a publication key that was never written."""
    keyring, previous, _key = _written(tmp_path)
    backend_down = {"now": False}

    def hook(op: str, key: str) -> None:
        if op == "set" and "#" in key and key.endswith(":0"):
            backend_down["now"] = True
            raise _CredWriteError()
        if op == "get" and backend_down["now"]:
            raise RuntimeError("backend unavailable")

    keyring.hook = hook
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).write_durable(_record(1700))

    assert refused.value.code == "APPROVAL_STORE_WRITE_FAILED"
    assert refused.value.detail.endswith("; previous approval unchanged")
    keyring.hook = None
    assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == previous


@pytest.mark.parametrize(
    ("raised", "code", "attempts"),
    [
        pytest.param(errno.EACCES if sys.platform == "win32" else errno.EWOULDBLOCK, "LOCK_CONTENTION", "many", id="contention"),
        pytest.param(errno.EBADF, "LOCK_FAILED", "one", id="other-error"),
    ],
)
def test_only_lock_contention_is_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: int, code: str, attempts: str) -> None:
    keyring, record, _key = _written(tmp_path)
    if sys.platform == "win32":
        import msvcrt

        module, name, acquire = msvcrt, "locking", msvcrt.LK_NBLCK
    else:
        import fcntl

        module, name, acquire = fcntl, "flock", fcntl.LOCK_EX | fcntl.LOCK_NB
    real = getattr(module, name)
    calls: list[int] = []

    def failing(fd: int, mode: int, *args: object) -> object:
        if mode == acquire:
            calls.append(fd)
            raise OSError(raised, "simulated lock failure")
        return real(fd, mode, *args)

    monkeypatch.setattr(module, name, failing)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable(record.workspace_digest)

    assert refused.value.code == code
    assert (len(calls) > 1) if attempts == "many" else (len(calls) == 1)
    assert "simulated" not in str(refused.value)


# --- #433 r2: replacement transitions ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"), [(None, 1700), (1600, None), (1600, 1700)], ids=["inline-to-parts", "parts-to-inline", "parts-to-parts"]
)
@pytest.mark.parametrize("succeeds", [True, False], ids=["ok", "failed"])
def test_replacement_between_inline_and_multipart_storage(
    tmp_path: Path, before: int | None, after: int | None, succeeds: bool
) -> None:
    keyring = WindowsLimitKeyring()
    previous, replacement = _record(before), _record(after)
    assert len(serialize_approval_record(_record())) <= MAX_KEYRING_VALUE_UTF16_BYTES // 2
    _store(tmp_path, keyring).write_durable(previous)
    key = f"durable:{previous.workspace_digest}"
    previous_parts = _part_keys(keyring, key)
    if not succeeds:
        _fail_on(keyring, "set", lambda k: k == key, error=_CredWriteError())
        with pytest.raises(ApprovalError):
            _store(tmp_path, keyring).write_durable(replacement)
        keyring.hook = None
    else:
        _store(tmp_path, keyring).write_durable(replacement)

    expected = replacement if succeeds else previous
    assert _store(tmp_path, keyring).read_durable(previous.workspace_digest) == expected
    parts = _part_keys(keyring, key)
    if not succeeds:
        assert parts == previous_parts
    elif after is None:
        assert parts == set()
    else:
        assert len(parts) == 2 and all(_manifest(keyring, key)["generation"] in part for part in parts)


# --- #433 r2: manifest metadata must agree with the record --------------------------------------------------------


@pytest.mark.parametrize(
    "manifest_overrides",
    [
        pytest.param({"workspace_digest": "b" * 64}, id="workspace"),
        pytest.param({"legacy_source_digest": "c" * 64}, id="legacy-source"),
    ],
)
def test_signed_manifest_metadata_that_disagrees_with_its_record_fails_closed(tmp_path: Path, manifest_overrides: dict) -> None:
    keyring = FakeKeyring()
    record = _record(1700)
    key = f"durable:{record.workspace_digest}"
    payload = serialize_approval_record(record)
    parts = [payload[:850], payload[850:]]
    keyring.set_password(_SERVICE, key, _signed_manifest(key, parts, **manifest_overrides))
    for index, part in enumerate(parts):
        keyring.set_password(_SERVICE, f"{key}#{'f' * 32}:{index}", part)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).read_durable(record.workspace_digest)
    assert refused.value.code == "INTEGRITY_FAILURE"


# --- #433 r2: revocation completeness ------------------------------------------------------------------------------


def test_replacing_a_migrated_record_removes_its_legacy_source_so_a_later_revocation_is_complete(tmp_path: Path) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    _store(tmp_path, keyring).write_durable(_record(digest=current.digest))
    assert keyring.get_password(_SERVICE, f"durable:{legacy.workspace_digest}") is None

    _store(tmp_path, keyring).revoke_workspace(current.digest)

    assert _promote(_store(tmp_path, keyring), legacy, current).state == "legacy_reapproval_required"


def test_a_failed_replacement_of_a_migrated_record_keeps_the_migrated_record_working(tmp_path: Path) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    key = f"durable:{current.digest}"
    _fail_on(keyring, "set", lambda k: k == key, error=_CredWriteError())
    with pytest.raises(ApprovalError):
        _store(tmp_path, keyring).write_durable(_record(1700, digest=current.digest))
    keyring.hook = None

    kept = _promote(_store(tmp_path, keyring), legacy, current)
    assert kept.state == "migrated" and kept.record is not None and kept.record.approval_id == legacy.approval_id


@pytest.mark.parametrize("damage", ["inline-value", "manifest-hmac"])
def test_revoking_an_unauthenticated_entry_refuses_and_deletes_nothing(tmp_path: Path, damage: str) -> None:
    keyring, legacy, current = _migrated(tmp_path)
    key = f"durable:{current.digest}"
    if damage == "manifest-hmac":
        manifest = _manifest(keyring, key)
        manifest["manifest_hmac"] = "0" * 64
        keyring.set_password(_SERVICE, key, json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    else:
        keyring.set_password(_SERVICE, key, '{"not":"a record"}')
    before = dict(keyring._store)

    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).revoke_workspace(current.digest)

    assert refused.value.code == "REVOCATION_INCOMPLETE"
    assert keyring._store == before
    with pytest.raises(ApprovalError):
        _promote(_store(tmp_path, keyring), legacy, current)  # still fails closed; never falls back to legacy

    assert "legacy approval it may have been migrated from can remain" in refused.value.detail

    # Approving again replaces the entry, and revoking that removes it, but it does NOT complete revocation:
    # residual R1, owned by #433. The unknown legacy source survives and lookup promotes it again.
    _store(tmp_path, keyring).write_durable(_record(digest=current.digest))
    _store(tmp_path, keyring).revoke_workspace(current.digest)
    assert keyring.get_password(_SERVICE, key) is None
    if damage == "manifest-hmac":  # overwriting with a non-record (the other case) orphaned the parts, as a crash would
        assert _part_keys(keyring, key) == set()
    assert _promote(_store(tmp_path, keyring), legacy, current).state == "migrated"


def test_a_delete_that_does_not_delete_is_deletion_failed(tmp_path: Path) -> None:
    class _NeverDeletes(WindowsLimitKeyring):
        def delete_password(self, service: str, key: str) -> None:
            raise RuntimeError("backend refused")

    keyring = _NeverDeletes()
    record = _record(1700, mode="one-shot")
    handle = _store(tmp_path, keyring).write_one_shot(record, b"\x08" * 32)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)
    assert refused.value.code == "DELETION_FAILED"
    _assert_safe_diagnostic(refused.value, record)
