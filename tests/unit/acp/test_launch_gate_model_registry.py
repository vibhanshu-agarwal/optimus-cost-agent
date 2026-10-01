"""Plan 12.2 Task 5: a launch approval binds the trusted model registry's effective hash.

The binding is one HMAC-covered security literal (schema version plus hash), so the approval record
schema and frozen predecessor bytes are unchanged. While enforcement is inactive no literal exists and
existing approvals stay valid; on activation the literal changes the snapshot digest, so an approval
made before activation no longer authorizes and the operator must re-approve the exact registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_gate import LaunchGateError, authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_security_state
from optimus_model_policy import binding as binding_module
from optimus_model_policy.binding import APPROVAL_LITERAL_NAME, approval_literal, compose_trusted_snapshot, packaged_defaults
from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

_ENV = {
    "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
    "OPTIMUS_API_KEY": "test-key",  # pragma: allowlist secret - synthetic test fixture
    "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
}


def _candidate(workspace: Path, keyring: FakeKeyring):
    snapshot = LaunchEnvironmentSnapshot.capture(_ENV)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values, platform_name=sys.platform)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=workspace / ".optimus-runtime")
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_state=resolve_workspace_security_state(workspace),
        operator_paths=paths,
        hmac_key=store.hmac_key,
    )
    return candidate, store


def test_inactive_launch_binds_no_registry(tmp_path: Path) -> None:
    candidate, _ = _candidate(tmp_path, FakeKeyring())
    assert APPROVAL_LITERAL_NAME not in candidate.security_literals
    assert all(row.name != APPROVAL_LITERAL_NAME for row in candidate.display_rows)


def test_activation_binds_the_registry_and_shows_it_for_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keyring = FakeKeyring()
    inactive, _ = _candidate(tmp_path, keyring)
    monkeypatch.setattr(binding_module, "ENFORCEMENT_ACTIVE", True)
    active, _ = _candidate(tmp_path, keyring)

    literal = approval_literal(compose_trusted_snapshot(packaged_defaults()))
    assert active.security_literals[APPROVAL_LITERAL_NAME] == literal
    [row] = [row for row in active.display_rows if row.name == APPROVAL_LITERAL_NAME]
    assert (row.display_value, row.decision) == (literal, "requires exact approval")
    assert active.security_snapshot_digest != inactive.security_snapshot_digest


def test_an_approval_from_before_activation_requires_reapproval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keyring = FakeKeyring()
    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)
    candidate, store = _candidate(tmp_path, keyring)
    assert authorize_launch(candidate=candidate, store=store, launch_session_id="s1").approval_mode == "durable"

    monkeypatch.setattr(binding_module, "ENFORCEMENT_ACTIVE", True)
    active, store = _candidate(tmp_path, keyring)
    with pytest.raises(LaunchGateError) as caught:
        authorize_launch(candidate=active, store=store, launch_session_id="s2")
    assert caught.value.code == "SNAPSHOT_MISMATCH"

    authorize_workspace_for_test(env=_ENV, workspace_root=tmp_path, fake_keyring=keyring)  # re-approval
    active, store = _candidate(tmp_path, keyring)
    assert authorize_launch(candidate=active, store=store, launch_session_id="s3").approval_mode == "durable"


def test_an_untrustworthy_registry_blocks_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("schema_version: 1\nschema_version: 1\n", encoding="utf-8")
    monkeypatch.setattr(binding_module, "ENFORCEMENT_ACTIVE", True)
    monkeypatch.setattr(binding_module, "packaged_defaults", lambda: bad)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(LaunchGateError) as caught:
        _candidate(workspace, FakeKeyring())
    assert (caught.value.code, caught.value.detail) == ("MODEL_REGISTRY_INVALID", "YAML_REJECTED")
