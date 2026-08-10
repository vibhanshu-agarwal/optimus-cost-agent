"""RED→GREEN tests for durable signing-key custody.

Lifecycle owns mint/load via OS keyring. Service consumes resolved bytes only.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest


class _FakeKeyring:
    """In-memory keyring. Never touches the real OS credential store."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}
        self.set_calls: list[tuple[str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.set_calls.append((service, key))
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self.delete_calls.append((service, key))
        self._store.pop((service, key), None)


def test_signing_key_custody_module_exports_resolve_and_error() -> None:
    from evidence_handoff_runtime import signing_key_custody as custody

    assert hasattr(custody, "SigningKeyCustodyError")
    assert hasattr(custody, "resolve_signing_key")
    assert hasattr(custody, "load_signing_key")
    assert callable(custody.resolve_signing_key)
    assert callable(custody.load_signing_key)


def test_mint_allowed_only_when_no_instance_file_and_no_store_row(tmp_path: Path) -> None:
    from evidence_handoff_runtime.signing_key_custody import resolve_signing_key

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()

    minted = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    assert isinstance(minted, bytes)
    assert len(minted) == 32
    assert len(keyring.set_calls) == 1

    # Second resolve with no instance still present loads the same key (no remint).
    loaded = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    assert loaded == minted
    assert len(keyring.set_calls) == 1


@pytest.mark.parametrize(
    ("instance_record_present", "store_instance_present"),
    [
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_missing_key_with_existing_instance_fails_closed_no_remint(
    tmp_path: Path,
    instance_record_present: bool,
    store_instance_present: bool,
) -> None:
    """R3 / R8.3: deleting the keyring entry must not reopen mint once an instance exists."""
    from evidence_handoff_runtime.signing_key_custody import (
        SigningKeyCustodyError,
        resolve_signing_key,
    )

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()

    with pytest.raises(SigningKeyCustodyError) as raised:
        resolve_signing_key(
            control_root=control_root,
            keyring_backend=keyring,
            instance_record_present=instance_record_present,
            store_instance_present=store_instance_present,
        )
    assert raised.value.code in {
        "signing_key_missing",
        "signing_key_mint_forbidden",
    }
    assert str(raised.value) == raised.value.code
    assert repr(raised.value) == f"SigningKeyCustodyError(code={raised.value.code!r})"
    assert keyring.set_calls == []


def test_corrupt_durable_key_fails_closed_typed_code(tmp_path: Path) -> None:
    from evidence_handoff_runtime.signing_key_custody import (
        SigningKeyCustodyError,
        keyring_service_for_control_root,
        load_signing_key,
        resolve_signing_key,
    )

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()
    service = keyring_service_for_control_root(control_root)
    keyring.set_password(service, "signing_key", "%%%not-valid-b64%%%")

    with pytest.raises(SigningKeyCustodyError) as raised:
        load_signing_key(control_root=control_root, keyring_backend=keyring)
    assert raised.value.code == "signing_key_corrupt"
    assert keyring.set_calls == [(service, "signing_key")]  # only the seed write above

    with pytest.raises(SigningKeyCustodyError) as raised_resolve:
        resolve_signing_key(
            control_root=control_root,
            keyring_backend=keyring,
            instance_record_present=True,
            store_instance_present=True,
        )
    assert raised_resolve.value.code == "signing_key_corrupt"


def test_unreadable_durable_key_fails_closed_typed_code(tmp_path: Path) -> None:
    from evidence_handoff_runtime.signing_key_custody import (
        SigningKeyCustodyError,
        load_signing_key,
    )

    class _BrokenKeyring:
        def get_password(self, service: str, key: str) -> str | None:
            raise OSError("keyring backend unavailable")

        def set_password(self, service: str, key: str, value: str) -> None:
            raise AssertionError("must not mint on unreadable backend")

    control_root = tmp_path / "control"
    control_root.mkdir()
    with pytest.raises(SigningKeyCustodyError) as raised:
        load_signing_key(control_root=control_root, keyring_backend=_BrokenKeyring())
    assert raised.value.code == "signing_key_unreadable"


def test_set_password_failure_uses_unwritable_code(tmp_path: Path) -> None:
    from evidence_handoff_runtime.signing_key_custody import (
        SigningKeyCustodyError,
        resolve_signing_key,
    )

    class _WriteFailKeyring:
        def get_password(self, service: str, key: str) -> str | None:
            return None

        def set_password(self, service: str, key: str, value: str) -> None:
            raise OSError("credential store write denied")

    control_root = tmp_path / "control"
    control_root.mkdir()
    with pytest.raises(SigningKeyCustodyError) as raised:
        resolve_signing_key(
            control_root=control_root,
            keyring_backend=_WriteFailKeyring(),
            instance_record_present=False,
            store_instance_present=False,
        )
    assert raised.value.code == "signing_key_unwritable"


def test_r4_durable_key_lives_in_keyring_not_chmod_file(tmp_path: Path) -> None:
    from evidence_handoff_runtime.signing_key_custody import resolve_signing_key

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()
    key = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    assert isinstance(key, bytes)
    # No durable key material under the control root (R4: not chmod-0600 file custody).
    for path in control_root.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            assert base64.b64encode(key).decode("ascii") not in text
            assert base64.urlsafe_b64encode(key).decode("ascii").rstrip("=") not in text
    assert keyring.set_calls, "key must be stored via keyring backend"


def test_runtime_input_supplier_and_service_do_not_query_keyring() -> None:
    """Design line 265 / R6: lifecycle may query keyring; service and supplier must not."""
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    targets = (
        repo / "src" / "evidence_handoff_runtime" / "inputs.py",
        repo / "src" / "evidence_handoff_runtime" / "service.py",
    )
    forbidden_attrs = frozenset({"get_password", "set_password", "delete_password"})
    violations: list[str] = []
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "keyring" or alias.name.startswith("keyring."):
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "keyring" or node.module.startswith("keyring.")):
                    violations.append(f"{path.name}: from {node.module} import …")
            elif isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                violations.append(f"{path.name}: attribute {node.attr}")
            elif isinstance(node, ast.Name) and node.id in forbidden_attrs:
                violations.append(f"{path.name}: name {node.id}")
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in forbidden_attrs:
                    violations.append(f"{path.name}: call {func.id}")
                if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
                    violations.append(f"{path.name}: call {func.attr}")
    assert violations == []


def test_r10_linked_replacement_does_not_remint_signing_key(tmp_path: Path) -> None:
    """R10: recovery creates a new instance under the same installation key — no remint."""
    from evidence_handoff_runtime.integrity import IntegrityCause, IntegrityIncident, IntegrityLatch
    from evidence_handoff_runtime.recovery import RecoveryAnchor, RecoveryManager
    from evidence_handoff_runtime.signing_key_custody import resolve_signing_key

    control_root = tmp_path / "control"
    control_root.mkdir()
    keyring = _FakeKeyring()
    original = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=False,
        store_instance_present=False,
    )
    sets_after_mint = list(keyring.set_calls)

    incident = IntegrityIncident(
        incident_id="inc-custody-r10",
        cause=IntegrityCause.CHAIN_BREAK,
        ledger_instance_id="inst-pred",
        safe_boundary_sequence=3,
        detected_at="2026-08-10T12:00:00+00:00",
        disposition="latched",
    )
    IntegrityLatch(control_root=control_root).persist(incident)
    anchor = RecoveryAnchor(
        ledger_instance_id="inst-pred",
        sequence=3,
        content_sha256="c" * 64,
        verified=True,
    )

    class _Store:
        def create_linked_replacement(self, *, incident, anchor):  # noqa: ANN001
            return {
                "ledger_instance_id": "inst-replacement",
                "predecessor_instance_id": "inst-pred",
                "recovery_anchor_sequence": anchor.sequence,
                "recovery_anchor_digest": anchor.content_sha256,
                "incident_id": incident.incident_id,
            }

    manager = RecoveryManager(control_root=control_root, store=_Store())
    manager.quarantine("inst-pred", incident=incident)
    replacement = manager.activate_linked_replacement(incident, anchor)
    assert replacement.ledger_instance_id == "inst-replacement"

    # After recovery, instance exists — resolve must load the same key, never remint.
    reloaded = resolve_signing_key(
        control_root=control_root,
        keyring_backend=keyring,
        instance_record_present=True,
        store_instance_present=True,
    )
    assert reloaded == original
    assert keyring.set_calls == sets_after_mint


def _abs(tmp_path: Path, name: str) -> Path:
    path = (tmp_path / name).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _lifecycle_manager_for_custody(tmp_path: Path):
    from evidence_handoff_runtime.config import FeatureConfig, LifecycleBootstrapContext
    from evidence_handoff_runtime.lifecycle import LifecycleManager
    from optimus_security.sanitization import PathAliasRule

    capture = _abs(tmp_path, "capture")
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
        store_admin_password="admin-secret-canary",
    )
    config = FeatureConfig.from_mapping(
        {
            "enabled": "true",
            "backend_id": "docker",
            "bind_host": "127.0.0.1",
            "postgres_port": "55432",
            "container_name": "evidence-handoff-custody-unit",
            "image": "postgres:16-alpine",
            "volume_name": "evidence-handoff-custody-unit-data",
        }
    )
    return LifecycleManager(config, bootstrap, docker_executable="docker")


def test_lifecycle_resolve_omitted_store_fails_closed_no_mint(tmp_path: Path) -> None:
    """Wiring regression: omitting store must not degrade store_instance_present to False."""
    from evidence_handoff_runtime.lifecycle import LifecycleError

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    with pytest.raises((LifecycleError, TypeError)) as raised:
        manager.resolve_installation_signing_key(keyring_backend=keyring)  # type: ignore[call-arg]
    if isinstance(raised.value, LifecycleError):
        assert raised.value.code == "signing_key_instance_fact_unavailable"
    assert keyring.set_calls == []


def test_lifecycle_resolve_none_store_fails_closed_no_mint(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    with pytest.raises(LifecycleError) as raised:
        manager.resolve_installation_signing_key(keyring_backend=keyring, store=None)
    assert raised.value.code == "signing_key_instance_fact_unavailable"
    assert keyring.set_calls == []


def test_lifecycle_resolve_store_without_instance_row_method_fails_closed_no_mint(
    tmp_path: Path,
) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError

    class _StoreMissingFact:
        pass

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    with pytest.raises(LifecycleError) as raised:
        manager.resolve_installation_signing_key(
            keyring_backend=keyring,
            store=_StoreMissingFact(),
        )
    assert raised.value.code == "signing_key_instance_fact_unavailable"
    assert keyring.set_calls == []


def test_lifecycle_resolve_store_reporting_row_forbids_mint_when_key_missing(
    tmp_path: Path,
) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError

    class _StoreWithRow:
        def instance_row_present(self) -> bool:
            return True

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    with pytest.raises(LifecycleError) as raised:
        manager.resolve_installation_signing_key(
            keyring_backend=keyring,
            store=_StoreWithRow(),
        )
    assert raised.value.code == "signing_key_mint_forbidden"
    assert keyring.set_calls == []


def test_lifecycle_resolve_store_query_error_fails_closed_no_mint(tmp_path: Path) -> None:
    from evidence_handoff_runtime.lifecycle import LifecycleError

    class _StoreRaises:
        def instance_row_present(self) -> bool:
            raise OSError("postgres unreachable")

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    with pytest.raises(LifecycleError) as raised:
        manager.resolve_installation_signing_key(
            keyring_backend=keyring,
            store=_StoreRaises(),
        )
    assert raised.value.code == "signing_key_instance_fact_unavailable"
    assert keyring.set_calls == []


def test_lifecycle_resolve_both_facts_absent_mints_once(tmp_path: Path) -> None:
    class _EmptyStore:
        def instance_row_present(self) -> bool:
            return False

    manager = _lifecycle_manager_for_custody(tmp_path)
    keyring = _FakeKeyring()
    minted = manager.resolve_installation_signing_key(
        keyring_backend=keyring,
        store=_EmptyStore(),
    )
    assert isinstance(minted, bytes)
    assert len(minted) == 32
    assert len(keyring.set_calls) == 1
    loaded = manager.resolve_installation_signing_key(
        keyring_backend=keyring,
        store=_EmptyStore(),
    )
    assert loaded == minted
    assert len(keyring.set_calls) == 1
