"""#538: tests reach keyring's `fail` backend, never the host's, unless marked `requires_os_keyring(_write)`.

Every backend here is synthetic; no test re-resolves the host backend (`keyring.core.init_backend` is replaced).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import keyring
import keyring.core
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import fail

from optimus.acp.local_gateway_secrets import CredentialLayer, resolve_shared_secret_with_provenance
from tests.support.keyring_isolation import REAL_KEYRING_MARKERS, keyring_for_test

_SEEDED = "seeded-host-secret"  # pragma: allowlist secret - synthetic value, never a real credential


class _SeededBackend(KeyringBackend):
    """Stands in for a host store that holds a Gateway secret."""

    priority = 1  # type: ignore[assignment]

    def get_password(self, service: str, username: str) -> str | None:
        return _SEEDED

    def set_password(self, service: str, username: str, password: str) -> None:
        raise AssertionError("a test wrote to the host stand-in")

    def delete_password(self, service: str, username: str) -> None:
        raise AssertionError("a test deleted from the host stand-in")


def _node(*markers: str) -> SimpleNamespace:
    return SimpleNamespace(get_closest_marker=lambda name: object() if name in markers else None)


@pytest.fixture
def host_resolves_seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-resolution installs the seeded stand-in instead of the host's backend."""
    monkeypatch.setattr(keyring.core, "init_backend", lambda limit=None: keyring.set_keyring(_SeededBackend()))


def _product_read(tmp_path: Path) -> str | None:
    """The production fallback: no backend injected, so the process-wide `keyring` backend answers."""
    value, provenance = resolve_shared_secret_with_provenance({}, config_root=tmp_path)
    assert (value is None) == (provenance.layer is CredentialLayer.MISSING)
    return value


def test_an_unmarked_test_sees_keyrings_fail_backend_and_the_product_fallback_finds_nothing(tmp_path: Path) -> None:
    assert isinstance(keyring.get_keyring(), fail.Keyring)
    assert _product_read(tmp_path) is None


def test_an_unmarked_test_never_inherits_a_backend_left_installed_before_it(tmp_path: Path) -> None:
    keyring.set_keyring(_SeededBackend())  # what an earlier test, or the host, left in place
    with keyring_for_test(_node()):
        assert isinstance(keyring.get_keyring(), fail.Keyring)
        assert _product_read(tmp_path) is None
    assert isinstance(keyring.get_keyring(), fail.Keyring)


@pytest.mark.parametrize("marker", REAL_KEYRING_MARKERS)
@pytest.mark.usefixtures("host_resolves_seeded")
def test_a_marked_test_gets_the_resolved_backend_and_the_next_unmarked_test_gets_fail(marker: str, tmp_path: Path) -> None:
    with keyring_for_test(_node(marker)):
        assert isinstance(keyring.get_keyring(), _SeededBackend)
        assert _product_read(tmp_path) == _SEEDED
    assert isinstance(keyring.get_keyring(), fail.Keyring)
    with keyring_for_test(_node()):
        assert isinstance(keyring.get_keyring(), fail.Keyring)


@pytest.mark.usefixtures("host_resolves_seeded")
def test_fail_is_restored_after_a_marked_test_fails() -> None:
    with pytest.raises(RuntimeError, match="the test failed"), keyring_for_test(_node(REAL_KEYRING_MARKERS[0])):
        assert isinstance(keyring.get_keyring(), _SeededBackend)
        raise RuntimeError("the test failed")
    assert isinstance(keyring.get_keyring(), fail.Keyring)


def test_fail_is_restored_when_re_resolution_itself_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(limit=None) -> None:  # noqa: ANN001 - keyring's own signature
        keyring.set_keyring(_SeededBackend())
        raise RuntimeError("resolution failed")

    monkeypatch.setattr(keyring.core, "init_backend", broken)
    with pytest.raises(RuntimeError, match="resolution failed"), keyring_for_test(_node(REAL_KEYRING_MARKERS[1])):
        pytest.fail("the test body ran without a backend")
    assert isinstance(keyring.get_keyring(), fail.Keyring)


class TestAMarkerOnTheEnclosingClass:
    @pytest.mark.usefixtures("host_resolves_seeded")
    def test_counts_as_marking_the_test(self, request: pytest.FixtureRequest) -> None:
        request.node.parent.add_marker(pytest.mark.requires_os_keyring)  # this class holds only this test
        with keyring_for_test(request.node):
            assert isinstance(keyring.get_keyring(), _SeededBackend)
        assert isinstance(keyring.get_keyring(), fail.Keyring)
