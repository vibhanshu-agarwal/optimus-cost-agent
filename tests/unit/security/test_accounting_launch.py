"""Plan 12.8 (ADR-032): the accounting configuration through approval, the signed Gateway manifest and Gateway startup.

The launch gate binds the configuration's exact bytes as a security literal (any change needs re-approval; no file, no
literal, existing approvals unchanged). The parent signs the accounting literal (root plus approved configuration) into
the Gateway manifest, which then has its version plus 3; manifests without it keep their versions and bytes. The
Gateway composes the same literal itself and refuses to start unless the manifest binds exactly it; it opens the
ledger only with an approved configuration and the credential from its own keyring namespace. No real service.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

from optimus_gateway import __main__ as gateway_main
from optimus_gateway import usage_capture
from optimus_security import accounting_config as ac
from optimus_security.launch_manifest import (
    MANIFEST_ACCOUNTING_VERSION_OFFSET,
    MANIFEST_REGISTRY_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    LaunchManifestError,
    build_gateway_child_manifest,
    serialize_gateway_child_manifest,
    verify_gateway_child_manifest,
)
from tests.unit.optimus_gateway.test_main_model_registry import _API_KEY, _KEY, _SECRET, _Server

_INPUTS = {
    "provider": "openrouter",
    "base_url": "https://openrouter.ai/api/v1",
    "provider_api_key": _API_KEY,
    "shared_secret": _SECRET,
    "bind_host": "127.0.0.1",
    "bind_port": 8765,
}
_CONFIG = {"schema_version": 1, "host": "127.0.0.1", "port": 55432, "database": "optimus_usage", "user": "optimus",
           "credential_name": "optimus@127.0.0.1:55432/optimus_usage", "connect_timeout_seconds": 5}


def _write_config(root: Path, document: dict | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ac.CONFIG_NAME).write_bytes(json.dumps(document or _CONFIG).encode("utf-8"))


def _serialized(*, model_registry: str | None = None, accounting: str | None = None) -> str:
    manifest = build_gateway_child_manifest(workspace_digest="a" * 64, security_snapshot_digest="b" * 64, hmac_key=_KEY,
                                            policy_version="P9.99-v1", model_registry=model_registry, accounting=accounting, **_INPUTS)
    return serialize_gateway_child_manifest(manifest)


# Manifest -------------------------------------------------------------------------------------------------------------

def test_an_accounting_manifest_is_its_version_plus_three_and_signs_the_literal():
    literal = ac.accounting_literal(Path("/x/accounting"), None)
    plain, registry = json.loads(_serialized(accounting=literal)), json.loads(_serialized(model_registry="r" * 10, accounting=literal))

    assert plain["schema_version"] == MANIFEST_SCHEMA_VERSION + MANIFEST_ACCOUNTING_VERSION_OFFSET == 4
    assert registry["schema_version"] == MANIFEST_REGISTRY_SCHEMA_VERSION + MANIFEST_ACCOUNTING_VERSION_OFFSET == 5
    assert verify_gateway_child_manifest(_serialized(accounting=literal), hmac_key=_KEY, accounting=literal, **_INPUTS).accounting == literal


def test_a_manifest_without_accounting_keeps_its_version_and_field_set():
    data = json.loads(_serialized())

    assert data["schema_version"] == MANIFEST_SCHEMA_VERSION and "accounting" not in data


@pytest.mark.parametrize(("signed", "composed"), [("A", "B"), ("A", None), (None, "B")])
def test_the_gateway_refuses_any_accounting_literal_but_the_one_it_composed(signed, composed):
    with pytest.raises(LaunchManifestError) as refused:
        verify_gateway_child_manifest(_serialized(accounting=signed), hmac_key=_KEY, accounting=composed, **_INPUTS)

    assert refused.value.code == "MANIFEST_ACCOUNTING_MISMATCH"


def test_a_tampered_accounting_literal_breaks_the_signature():
    data = json.loads(_serialized(accounting="A"))
    data["accounting"] = "B"

    with pytest.raises(LaunchManifestError) as refused:
        verify_gateway_child_manifest(json.dumps(data), hmac_key=_KEY, accounting="B", **_INPUTS)

    assert refused.value.code == "MANIFEST_INVALID_SIGNATURE"


# Configuration --------------------------------------------------------------------------------------------------------

def test_the_configuration_is_the_documented_non_secret_shape(tmp_path):
    _write_config(tmp_path)

    config = ac.load(tmp_path)

    assert config == ac.AccountingConfig("127.0.0.1", 55432, "optimus_usage", "optimus", "optimus@127.0.0.1:55432/optimus_usage", 5)
    assert ac.load(tmp_path / "absent") is None and ac.config_literal(tmp_path / "absent") is None


@pytest.mark.parametrize(("change", "code"), [
    ({"password": "hunter2"}, "schema"),  # pragma: allowlist secret - the refused shape under test
    ({"port": 0}, "endpoint"),
    ({"user": "bad user"}, "names"),
    ({"connect_timeout_seconds": 600}, "timeout"),
])
def test_anything_but_that_shape_is_refused_so_no_password_is_ever_read(tmp_path, change, code):
    _write_config(tmp_path, {**_CONFIG, **change})

    with pytest.raises(ac.AccountingConfigError) as refused:
        ac.load(tmp_path)

    assert refused.value.code == code


def test_the_literal_follows_the_exact_bytes_and_an_oversized_file_is_refused(tmp_path):
    _write_config(tmp_path)
    first = ac.config_literal(tmp_path)
    _write_config(tmp_path, {**_CONFIG, "port": 55433})

    assert first != ac.config_literal(tmp_path) and first.startswith("accounting-config:sha256:")
    (tmp_path / ac.CONFIG_NAME).write_bytes(b" " * (16 * 1024 + 1))
    with pytest.raises(ac.AccountingConfigError):
        ac.config_literal(tmp_path)


# Launch gate ----------------------------------------------------------------------------------------------------------

@pytest.mark.usefixtures("isolated_windows_known_folders")
def test_the_launch_gate_binds_the_configuration_and_a_change_needs_reapproval(tmp_path, tmp_path_factory):
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.acp.launch_gate import resolve_launch_candidate
    from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
    from optimus.acp.operator_paths import resolve_authorized_operator_paths
    from optimus.acp.trusted_paths import resolve_workspace_security_state
    from tests.unit.acp.conftest import FakeKeyring
    from tests.unit.acp.test_test_composition import _ENV

    # The operator's supported override keeps the config root temporary on every platform (outside the workspace).
    snapshot = LaunchEnvironmentSnapshot.capture({**_ENV, "OPTIMUS_CONFIG_ROOT": str(tmp_path_factory.mktemp("config-root"))})
    paths = resolve_authorized_operator_paths(workspace_root=tmp_path, snapshot_values=snapshot.values, platform_name=sys.platform)
    store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / ".optimus-runtime")

    def candidate():
        return resolve_launch_candidate(snapshot=snapshot, workspace_state=resolve_workspace_security_state(tmp_path), operator_paths=paths,
                                        hmac_key=store.hmac_key, test_profile=None, stage_c=False)

    without = candidate()
    _write_config(ac.accounting_root(paths.config_root))
    bound = candidate()
    _write_config(ac.accounting_root(paths.config_root), {**_CONFIG, "port": 55433})
    changed = candidate()

    assert ac.SECURITY_LITERAL_NAME not in without.security_literals
    assert bound.security_literals[ac.SECURITY_LITERAL_NAME].startswith("accounting-config:sha256:")
    assert changed.security_literals[ac.SECURITY_LITERAL_NAME] == ac.config_literal(ac.accounting_root(paths.config_root))
    assert bound.security_snapshot_digest != without.security_snapshot_digest
    assert changed.security_snapshot_digest != bound.security_snapshot_digest
    [row] = [row for row in bound.display_rows if row.name == ac.SECURITY_LITERAL_NAME]
    assert row.decision == "requires exact approval"


# Gateway startup ------------------------------------------------------------------------------------------------------

class _Keyring:
    def __init__(self, password: str | None = None) -> None:
        self.password = password

    def get_password(self, service: str, key: str) -> str | None:
        if key == "hmac_integrity_key":
            return base64.urlsafe_b64encode(_KEY).decode("ascii")
        if service == ac.KEYRING_SERVICE and key == _CONFIG["credential_name"]:
            return self.password
        return None


@pytest.fixture
def started(monkeypatch):
    for name in ("OPTIMUS_LOCAL_GATEWAY_BIND_HOST", "OPTIMUS_LOCAL_GATEWAY_PORT", "OPTIMUS_LOCAL_GATEWAY_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET", _SECRET)
    monkeypatch.setenv("OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY", _API_KEY)
    monkeypatch.setattr(gateway_main, "trusted_snapshot", lambda: None)  # registry enforcement off: accounting alone is bound
    configs: list = []
    monkeypatch.setattr(gateway_main, "serve_gateway", lambda *, config: configs.append(config) or _Server())
    yield configs
    usage_capture.configure(None)


def _run(root: Path, manifest: str) -> int:
    return gateway_main.main(["--bind-host", "127.0.0.1", "--port", "8765", "--manifest", manifest, "--accounting-root", str(root)])


def test_a_gateway_with_its_bound_root_and_no_configuration_captures_locally(started, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())
    root = tmp_path / "accounting"

    assert _run(root, _serialized(accounting=ac.accounting_literal(root, None))) == 0
    assert started[0].usage_store is None


def test_a_gateway_refuses_a_root_the_manifest_does_not_bind(started, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring())

    assert _run(tmp_path / "accounting", _serialized()) == 2
    assert "MANIFEST_ACCOUNTING_MISMATCH" in capsys.readouterr().err and started == []


def test_a_configuration_swapped_after_approval_refuses_to_start(started, monkeypatch, tmp_path):
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring("pw"))
    root = tmp_path / "accounting"
    _write_config(root)
    approved = ac.accounting_literal(root, ac.config_literal(root))
    _write_config(root, {**_CONFIG, "host": "10.0.0.9"})

    assert _run(root, _serialized(accounting=approved)) == 2 and started == []


@pytest.mark.parametrize("password", [None, "k3-password"])  # pragma: allowlist secret - synthetic
def test_the_ledger_opens_only_with_the_credential_from_the_gateway_keyring_namespace(started, monkeypatch, tmp_path, password):
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring(password))
    root = tmp_path / "accounting"
    _write_config(root)

    assert _run(root, _serialized(accounting=ac.accounting_literal(root, ac.config_literal(root)))) == 0
    store = started[0].usage_store
    assert (store is None) is (password is None)
    if store is not None:
        assert "k3-password" in store._conninfo and store.ledger_instance is None, "no connection is made at startup"


# Parent launch --------------------------------------------------------------------------------------------------------

def test_the_parent_signs_the_root_and_the_approved_configuration_only_when_they_match(tmp_path, monkeypatch):
    from tests.unit.acp.test_local_infra_model_registry import _spawned_args

    config_root = tmp_path / "config"
    root = ac.accounting_root(config_root)
    _write_config(root)
    approved = ac.config_literal(root)

    args = _spawned_args(tmp_path, monkeypatch, config_root=config_root, usage_accounting=True, approved_accounting_config=approved)
    manifest = json.loads(args[args.index("--manifest") + 1])
    stale = _spawned_args(tmp_path, monkeypatch, config_root=config_root, usage_accounting=True, approved_accounting_config="accounting-config:sha256:" + "0" * 64)
    absent = _spawned_args(tmp_path, monkeypatch, config_root=config_root)

    assert args[args.index("--accounting-root") + 1] == str(root)
    assert manifest["accounting"] == ac.accounting_literal(root, approved) and manifest["schema_version"] == 4
    assert "--accounting-root" not in stale and "accounting" not in json.loads(stale[stale.index("--manifest") + 1])
    assert "--accounting-root" not in absent, "a launch that does not ask for accounting keeps its manifest"


def test_a_configuration_swapped_during_verification_is_never_used(started, monkeypatch, tmp_path):
    """Checkpoint B finding 2: the Gateway hashes and parses one captured buffer; a replacement written after that read
    (here, while the manifest is being verified) never selects the endpoint or credential reference."""
    monkeypatch.setattr(gateway_main, "_keyring_module", _Keyring("pw"))
    root = tmp_path / "accounting"
    _write_config(root)
    manifest = _serialized(accounting=ac.accounting_literal(root, ac.config_literal(root)))
    real_verify = gateway_main.verify_gateway_child_manifest

    def verify_then_swap(*args, **kwargs):
        verified = real_verify(*args, **kwargs)
        _write_config(root, {**_CONFIG, "host": "attacker.example", "credential_name": "other-entry"})
        return verified

    monkeypatch.setattr(gateway_main, "verify_gateway_child_manifest", verify_then_swap)

    assert _run(root, manifest) == 0
    assert "host=127.0.0.1" in started[0].usage_store._conninfo and "attacker" not in started[0].usage_store._conninfo
