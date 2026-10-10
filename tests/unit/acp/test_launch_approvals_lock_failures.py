"""Deterministic coverage of the one-shot consume lock-failure paths.

`TestOneShotConcurrency.test_concurrent_consumers_only_one_succeeds` races real threads, so whether a
loser hits the nonblocking-lock failure, or the unlock in `finally` fails, depends on timing: a run can
pass without executing either path (Plan 12.2 Task 3 coverage gate, 2026-10-01). These tests inject
each `OSError` at the platform lock call and drive the public `KeyringApprovalStore.consume_one_shot`,
so both paths run, and are checked, on every run. No production code changes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO, Any

import pytest

from optimus.acp import launch_approvals
from optimus.acp.launch_approvals import ApprovalError, KeyringApprovalStore
from tests.unit.acp.test_launch_approvals import FakeKeyring, _sample_approval_record

_HMAC_KEY = bytes(range(32))
_NONCE = bytes([0xBB]) * 32


@pytest.fixture
def opened_files(monkeypatch: pytest.MonkeyPatch) -> list[IO[Any]]:
    """Every file the approvals module opens. Holding a reference means only an explicit close()
    closes it, so a dropped handle cannot pass for a closed one through garbage collection."""
    opened: list[IO[Any]] = []

    def _recording_open(*args: Any, **kwargs: Any) -> IO[Any]:
        handle = open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(launch_approvals, "open", _recording_open, raising=False)
    return opened


def _store(tmp_path: Path, keyring: FakeKeyring) -> KeyringApprovalStore:
    return KeyringApprovalStore(keyring_backend=keyring, runtime_root=tmp_path, hmac_key=_HMAC_KEY)


def _assert_only_closed_lock_files(opened: list[IO[Any]], tmp_path: Path, *, expected: int) -> None:
    assert len(opened) == expected
    for handle in opened:
        assert Path(handle.name).parent == tmp_path / "locks"
        assert Path(handle.name).suffix == ".lock"
        assert handle.closed, f"{handle.name} was left open"


def _platform_lock_call() -> tuple[Any, str]:
    if sys.platform == "win32":
        import msvcrt

        return msvcrt, "locking"
    import fcntl

    return fcntl, "flock"


def test_a_held_lock_refuses_with_lock_contention_and_keeps_the_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, opened_files: list[IO[Any]]
) -> None:
    keyring = FakeKeyring()
    record = _sample_approval_record(mode="one-shot", hmac_key=_HMAC_KEY)
    handle = _store(tmp_path, keyring).write_one_shot(record, _NONCE)
    module, name = _platform_lock_call()
    real_lock = getattr(module, name)
    acquire_mode = module.LK_NBLCK if sys.platform == "win32" else module.LOCK_EX | module.LOCK_NB
    acquisitions: list[int] = []

    def _held_elsewhere(fd: int, mode: int, *args: Any) -> Any:
        if mode == acquire_mode:
            acquisitions.append(fd)
            raise OSError("lock held by another consumer")
        return real_lock(fd, mode, *args)

    monkeypatch.setattr(module, name, _held_elsewhere)
    with pytest.raises(ApprovalError) as refused:
        _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)

    assert refused.value.code == "LOCK_CONTENTION"
    assert len(acquisitions) == 1
    _assert_only_closed_lock_files(opened_files, tmp_path, expected=1)

    # The refusal consumed nothing: once the lock is free, the same approval is consumed once.
    monkeypatch.setattr(module, name, real_lock)
    consumed = _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)
    assert consumed == record
    with pytest.raises(ApprovalError) as again:
        _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)
    assert again.value.code == "ONE_SHOT_NOT_FOUND"
    _assert_only_closed_lock_files(opened_files, tmp_path, expected=2)


@pytest.mark.skipif(sys.platform != "win32", reason="only the Windows path unlocks explicitly in finally")
def test_a_failed_unlock_keeps_the_consumed_result_and_still_closes_the_lock_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, opened_files: list[IO[Any]]
) -> None:
    import msvcrt

    keyring = FakeKeyring()
    record = _sample_approval_record(mode="one-shot", hmac_key=_HMAC_KEY)
    handle = _store(tmp_path, keyring).write_one_shot(record, _NONCE)
    real_lock = msvcrt.locking
    unlocks: list[int] = []

    def _unlock_reports_failure(fd: int, mode: int, nbytes: int) -> None:
        real_lock(fd, mode, nbytes)
        if mode == msvcrt.LK_UNLCK:
            unlocks.append(fd)
            raise OSError("unlock reported a failure")

    monkeypatch.setattr(msvcrt, "locking", _unlock_reports_failure)
    consumed = _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)

    assert consumed == record
    assert len(unlocks) == 1
    _assert_only_closed_lock_files(opened_files, tmp_path, expected=1)
    # Delete-before-use held despite the unlock failure: the approval cannot be consumed twice.
    monkeypatch.setattr(msvcrt, "locking", real_lock)
    with pytest.raises(ApprovalError) as again:
        _store(tmp_path, keyring).consume_one_shot(handle, record.security_snapshot_digest)
    assert again.value.code == "ONE_SHOT_NOT_FOUND"
    _assert_only_closed_lock_files(opened_files, tmp_path, expected=1)
