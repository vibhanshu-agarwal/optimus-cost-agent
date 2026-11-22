"""#532: the one cross-process file lock's contract, on the real OS lock. Every caller's own mapping is tested with that
caller; this file proves what they all rely on."""

from __future__ import annotations

import ast
import errno
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Any

import pytest

import optimus_file_lock as fl
from tools.tracked_repository_files import tracked_repository_files

_ROOT = Path(__file__).resolve().parents[3]
# A refusal that is never another holder, on every platform; EACCES is one too on POSIX (it is contention on Windows).
FAULTS = [errno.ENOLCK] + ([] if sys.platform == "win32" else [errno.EACCES])


def _old_style_attempt(path: Path) -> IO[bytes]:
    """What the six hand-rolled copies did before #532: their own handle, one non-blocking call on byte 0."""
    handle = open(path, "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def _refuse_with(monkeypatch: pytest.MonkeyPatch, number: int) -> list[int]:
    """Make the platform's own lock call fail with `number`, as the OS would. Returns the attempts it saw."""
    attempts: list[int] = []

    def refuse(*_args: Any) -> None:
        attempts.append(number)
        raise OSError(number, os.strerror(number))

    if sys.platform == "win32":
        import msvcrt

        monkeypatch.setattr(msvcrt, "locking", refuse)
    else:
        import fcntl

        monkeypatch.setattr(fcntl, "flock", refuse)
    return attempts


def test_the_package_imports_only_the_standard_library() -> None:
    sources = [path for path in tracked_repository_files(_ROOT, pathspecs=("src/optimus_file_lock",)) if path.suffix == ".py"]
    assert sources, "the package must have tracked sources"
    imported: set[str] = set()
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
    assert sorted(imported - set(sys.stdlib_module_names) - {"__future__"}) == []


def test_another_holder_is_busy_until_it_lets_go(tmp_path: Path) -> None:
    path = tmp_path / "locks" / "x.lock"  # its folder does not exist yet
    first, second = fl.FileLock(path), fl.FileLock(path)
    first.acquire(wait=0)
    assert path.stat().st_size == 0  # an empty file is locked past its end, as Windows allows
    with pytest.raises(fl.LockBusy) as busy:
        second.acquire(wait=0)
    assert busy.value.errno in fl.CONTENTION_ERRNOS and not second.held
    started = time.monotonic()
    with pytest.raises(fl.LockBusy):
        second.acquire(wait=0.3, poll=0.05)
    assert 0.3 <= time.monotonic() - started < 5.0
    first.release()
    second.acquire(wait=0)
    assert second.held
    second.release()


def test_a_waiter_takes_the_lock_as_soon_as_its_holder_releases(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    holder = fl.FileLock(path)
    holder.acquire(wait=0)
    threading.Timer(0.2, holder.release).start()
    waiter = fl.FileLock(path)
    started = time.monotonic()
    waiter.acquire(wait=10, poll=0.02)
    assert time.monotonic() - started < 5.0
    waiter.release()


def test_the_old_hand_rolled_locks_and_this_one_exclude_each_other(tmp_path: Path) -> None:
    """A process still running the code from before #532 and one running this take the same byte, so neither gets in."""
    path = tmp_path / "x.lock"
    old = _old_style_attempt(path)
    try:
        with pytest.raises(fl.LockBusy):
            fl.FileLock(path).acquire(wait=0)
    finally:
        old.close()
    with fl.held(path, wait=0):
        with pytest.raises(OSError) as refused:
            _old_style_attempt(path).close()
        assert refused.value.errno in fl.CONTENTION_ERRNOS


_HOLDER = """
import sys
from pathlib import Path

import optimus_file_lock as fl

lock = fl.FileLock(Path(sys.argv[1]))
lock.acquire(wait=0)
print("held", flush=True)
if sys.stdin.readline().strip() == "release":
    lock.release()
"""


def _child_holding(path: Path) -> subprocess.Popen[str]:
    child = subprocess.Popen([sys.executable, "-c", _HOLDER, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    ready: list[str] = []
    reader = threading.Thread(target=lambda: ready.append(child.stdout.readline()), daemon=True)  # type: ignore[union-attr]
    reader.start()
    reader.join(30)  # bounded: a child that never takes the lock fails the test instead of hanging it
    if ready != ["held\n"]:
        child.kill()
        child.communicate()
        pytest.fail(f"the child did not take the lock: {ready}")
    return child


@pytest.mark.parametrize("ending", ["release", "death"])
def test_another_process_holds_it_until_it_releases_or_dies(tmp_path: Path, ending: str) -> None:
    path = tmp_path / "x.lock"
    child = _child_holding(path)
    try:
        with pytest.raises(fl.LockBusy):
            fl.FileLock(path).acquire(wait=0.2)
        if ending == "release":
            assert child.stdin is not None
            child.stdin.write("release\n")
            child.stdin.flush()
            assert child.wait(timeout=30) == 0
        else:
            child.kill()  # the OS releases a dead owner's lock; the file stays where it is
            child.wait(timeout=30)
        with fl.held(path, wait=5):
            assert path.exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate()


@pytest.mark.parametrize("number", FAULTS)
def test_a_lock_fault_is_raised_at_once_with_its_errno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, number: int) -> None:
    attempts = _refuse_with(monkeypatch, number)
    started = time.monotonic()
    with pytest.raises(fl.LockFault) as fault:
        fl.FileLock(tmp_path / "x.lock").acquire(wait=30)
    assert (fault.value.errno, fault.value.stage, attempts) == (number, "lock", [number])
    assert time.monotonic() - started < 5.0 and isinstance(fault.value.__cause__, OSError)


def test_a_file_that_cannot_be_opened_is_a_fault_even_with_a_contention_errno(tmp_path: Path) -> None:
    """Contention is read only from the lock call: a directory where the file should be is a fault on every platform,
    though Windows reports it as EACCES."""
    (tmp_path / "x.lock").mkdir()
    with pytest.raises(fl.LockFault) as fault:
        fl.FileLock(tmp_path / "x.lock").acquire(wait=30)
    assert fault.value.stage == "open" and fault.value.errno is not None
    (tmp_path / "file").write_text("", encoding="utf-8")
    with pytest.raises(fl.LockFault) as no_folder:
        fl.FileLock(tmp_path / "file" / "x.lock").acquire(wait=0)  # its folder cannot be made
    assert no_folder.value.stage == "open"


def test_every_failed_acquisition_closes_its_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    opened: list[IO[bytes]] = []

    def recording_open(*args: Any, **kwargs: Any) -> IO[bytes]:
        handle = open(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(fl, "open", recording_open, raising=False)
    path = tmp_path / "x.lock"
    with fl.held(path, wait=0):
        with pytest.raises(fl.LockBusy):
            fl.FileLock(path).acquire(wait=0)

    def interrupted(_handle: IO[bytes]) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(fl, "_lock", interrupted)
    with pytest.raises(KeyboardInterrupt):
        fl.FileLock(path).acquire(wait=0)
    assert len(opened) == 3 and all(handle.closed for handle in opened)


def test_a_failed_unlock_still_closes_and_frees_the_lock(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    lock = fl.FileLock(path)
    lock.acquire(wait=0)

    def failing(_handle: IO[bytes]) -> None:
        raise OSError(errno.EIO, "unlock failed")

    monkeypatch.setattr(fl, "_unlock", failing)
    lock.release()
    lock.release()  # a second release does nothing
    assert not lock.held
    monkeypatch.undo()
    with fl.held(path, wait=0):
        pass


def test_a_failed_close_is_raised_and_the_lock_is_no_longer_held(tmp_path: Path) -> None:
    class Unclosable:
        def seek(self, _offset: int) -> None:
            pass

        def fileno(self) -> int:
            raise OSError(errno.EBADF, "gone")

        def close(self) -> None:
            raise OSError(errno.EIO, "close failed")

    lock = fl.FileLock(tmp_path / "x.lock")
    lock._handle = Unclosable()  # type: ignore[assignment]
    with pytest.raises(OSError) as failed:
        lock.release()
    assert failed.value.errno == errno.EIO and not lock.held


def test_an_error_in_the_body_passes_through_and_the_lock_is_released(tmp_path: Path) -> None:
    path = tmp_path / "x.lock"
    with pytest.raises(KeyError), fl.held(path, wait=0):
        raise KeyError("the protected work failed")
    with fl.held(path, wait=0):
        pass


def test_a_held_lock_cannot_be_acquired_again(tmp_path: Path) -> None:
    lock = fl.FileLock(tmp_path / "x.lock")
    lock.acquire(wait=0)
    try:
        with pytest.raises(RuntimeError, match="already held"):
            lock.acquire(wait=0)
    finally:
        lock.release()


@pytest.mark.parametrize(("wait", "poll"), [(-1, 0.02), (float("nan"), 0.02), (float("inf"), 0.02), (True, 0.02), ("1", 0.02),
                                            (1, 0), (1, -0.1), (1, float("inf"))])
def test_a_wait_or_poll_that_is_not_a_finite_duration_is_refused(tmp_path: Path, wait: Any, poll: Any) -> None:
    with pytest.raises(ValueError):
        fl.FileLock(tmp_path / "x.lock").acquire(wait=wait, poll=poll)
    assert not (tmp_path / "x.lock").exists()  # refused before anything is opened
