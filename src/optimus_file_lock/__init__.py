"""One cross-process file lock for every Optimus package (#532).

An OS lock on the first byte of a file that every process shares: `msvcrt.locking` on Windows, `fcntl.flock` elsewhere.
The OS releases it when its owner closes the file or dies, so a live owner is never taken over, and the file itself is
never replaced, unlinked or reclaimed by age. Every wait is an explicit deadline polled on every platform, never
`LK_LOCK` (which gives up after ten one-second retries on Windows) or a blocking `flock` (which never gives up on POSIX).
Only another holder's lock is contention; any other refusal is a fault, raised at once with its errno.

Standard library only, so every package may import it, `optimus_model_policy` included
(tests/unit/file_lock/test_file_lock.py checks this). Callers translate `LockBusy` and `LockFault` into their own error
codes around acquisition only, never around the work the lock protects. Both are `OSError`s, so a caller whose
`except OSError` already counts a failed step keeps counting a lock it could not take.
"""

from __future__ import annotations

import contextlib
import errno
import math
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Final, Literal

# What each platform's non-blocking lock raises when another holder has it, and nothing else: msvcrt.locking reports a
# held range as EACCES (EDEADLOCK when LK_LOCK gives up), flock(LOCK_NB) as EWOULDBLOCK. On POSIX, EACCES is a refusal
# such as a security policy denying the lock, so it is a fault there (#529 review 2).
CONTENTION_ERRNOS: Final = (frozenset({errno.EACCES, errno.EDEADLK}) if sys.platform == "win32"
                            else frozenset({errno.EAGAIN, errno.EWOULDBLOCK}))
DEFAULT_POLL_SECONDS: Final = 0.02


class LockBusy(OSError):
    """Another holder kept the lock past the deadline. Its errno is the last contention errno the OS gave."""


class LockFault(OSError):
    """The OS refused for a reason other than another holder. `stage` is "open" (creating the lock's folder or opening
    its file) or "lock" (the lock call itself); errno is the OS's own."""

    def __init__(self, number: int | None, message: str, *, stage: Literal["open", "lock"]) -> None:
        super().__init__(number, message)
        self.stage = stage


def _lock(handle: IO[bytes]) -> None:
    """One non-blocking attempt on the file's first byte. Imported at the call so a test can stand in for the OS call."""
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle: IO[bytes]) -> None:
    if sys.platform == "win32":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _seconds(name: str, value: float, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be a finite number of seconds {'above' if positive else 'at or above'} zero")
    return float(value)


class FileLock:
    """The lock on one file. `acquire` takes it or raises; `release` gives it back and always closes the file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._handle: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self, *, wait: float, poll: float = DEFAULT_POLL_SECONDS) -> None:
        """Take the lock within `wait` seconds (0: one attempt), retrying only contention every `poll` seconds. Raises
        `LockBusy` once the deadline passes and `LockFault` at once for anything else; the file is closed on every
        failure, an interruption included."""
        if self._handle is not None:
            raise RuntimeError(f"{self.path.name} is already held by this lock")
        deadline = time.monotonic() + _seconds("wait", wait, positive=False)
        interval = _seconds("poll", poll, positive=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "a+b")  # appending never truncates a lock file another process holds
        except OSError as exc:
            raise LockFault(exc.errno, f"the lock file {self.path.name} could not be opened", stage="open") from exc
        try:
            while True:
                try:
                    _lock(handle)
                    break
                except OSError as exc:
                    if exc.errno not in CONTENTION_ERRNOS:
                        raise LockFault(exc.errno, f"the lock file {self.path.name} could not be locked", stage="lock") from exc
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LockBusy(exc.errno, f"another process holds {self.path.name}") from exc
                    time.sleep(min(interval, remaining))
                    if time.monotonic() >= deadline:  # a sleep that overran never buys an attempt past the deadline
                        raise LockBusy(exc.errno, f"another process holds {self.path.name}") from exc
        except BaseException:
            handle.close()
            raise
        self._handle = handle

    def release(self) -> None:
        """Give the lock back and close the file; a second call does nothing. A failed unlock is not an error, because
        closing the file releases the lock anyway; a failed close is raised."""
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            with contextlib.suppress(OSError):
                _unlock(handle)
        finally:
            handle.close()


@contextlib.contextmanager
def held(path: Path, *, wait: float, poll: float = DEFAULT_POLL_SECONDS) -> Iterator[None]:
    """Hold the lock on `path` for the body. An error from the body passes through untouched."""
    lock = FileLock(path)
    lock.acquire(wait=wait, poll=poll)
    try:
        yield
    finally:
        lock.release()


__all__ = ["CONTENTION_ERRNOS", "DEFAULT_POLL_SECONDS", "FileLock", "LockBusy", "LockFault", "held"]
