"""No test reaches the host's credential store unless it is marked for it (#538).

Product code falls back to the real `keyring` module when no backend is injected, which is right in production. In a
test, that fallback read whatever the host resolved: GitHub CI's no-keyring backend, the operator's Windows Credential
Manager, or WSLg's Secret Service, which blocked a unit test on a prompt for over two hours. The root conftest installs
keyring's own `fail` backend for the whole session, in the controller and in every xdist worker, so every test sees
what CI sees and a call fails at once. Only a test marked `requires_os_keyring` or `requires_os_keyring_write`
re-resolves the host backend, for that test alone.

In-process only: a child process resolves its own backend (residual on #538). A run that selects its own backend for
the pytest process, as MAIN-5 does with `PYTHON_KEYRING_BACKEND=counting_keyring.CountingKeyring`, no longer sees
pytest-process calls in that backend's audit: they reach `fail`, so an empty audit there does not mean no calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

import keyring
import keyring.core
from keyring.backends import fail

REAL_KEYRING_MARKERS = ("requires_os_keyring", "requires_os_keyring_write")


class _Node(Protocol):
    def get_closest_marker(self, name: str) -> object | None: ...


def install_fail_keyring() -> None:
    keyring.set_keyring(fail.Keyring())


@contextmanager
def keyring_for_test(node: _Node) -> Iterator[None]:
    """The host backend for a marked test, keyring's `fail` backend otherwise; `fail` again afterwards, whatever
    happened. Setting `fail` before an unmarked test also undoes any backend an earlier test left installed."""
    try:
        if any(node.get_closest_marker(name) is not None for name in REAL_KEYRING_MARKERS):
            keyring.core.init_backend()
        else:
            install_fail_keyring()
        yield
    finally:
        install_fail_keyring()
