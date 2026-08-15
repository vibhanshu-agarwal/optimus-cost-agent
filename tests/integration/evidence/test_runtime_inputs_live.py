"""Live resolver/OS-keyring evidence for portable redaction runtime inputs.

Uses the real OS credential-store backend for credential resolution. Does not
write, rotate, or delete credentials. Approval records use an in-memory fake
store so the test remains non-mutating against OS approval state.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

import keyring
import pytest

from optimus.acp.evidence_redaction_adapter import (
    EvidenceRedactionHostContext,
    assert_portable_runtime_inputs,
    build_redaction_runtime_inputs,
)
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_gate import authorize_launch, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import resolve_workspace_identity
from tests.unit.acp.conftest import FakeKeyring

pytestmark = pytest.mark.requires_os_keyring


def test_runtime_inputs_from_real_resolver_and_os_keyring(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Minimal inherited env; credentials may resolve from real OS keyring/config.
    env = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        "OPTIMUS_API_KEY": f"live-env-api-{uuid.uuid4().hex}",
        "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET": f"live-env-shared-{uuid.uuid4().hex}",
    }
    snapshot = LaunchEnvironmentSnapshot.capture(env)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
        platform_name=sys.platform,
    )
    paths.runtime_root.mkdir(parents=True, exist_ok=True)

    # Real OS credential backend for resolve_launch_candidate.
    assert keyring.get_keyring() is not None
    backend_name = type(keyring.get_keyring()).__module__
    assert "keyring" in backend_name or backend_name.startswith("keyring")

    approval_store = KeyringApprovalStore(
        keyring_backend=FakeKeyring(),
        runtime_root=paths.runtime_root,
    )
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=resolve_workspace_identity(workspace),
        operator_paths=paths,
        hmac_key=approval_store.hmac_key,
        credential_keyring_backend=keyring,
    )
    record = build_approval_record(
        mode="durable",
        workspace_identity=candidate.workspace_identity,
        security_literals=candidate.security_literals,
        secret_fingerprints=candidate.secret_fingerprints,
        monotonic_grants=candidate.monotonic_grants,
        model_observation=candidate.model_observation,
        hmac_key=approval_store.hmac_key,
    )
    approval_store.write_durable(record)
    launch = authorize_launch(
        candidate=candidate,
        store=approval_store,
        approval_id=None,
        launch_session_id=f"live-redaction-{uuid.uuid4().hex}",
    )

    profile = tmp_path / "profile"
    user_data = tmp_path / "user-data"
    capture = tmp_path / "capture"
    staging = tmp_path / "staging"
    quarantine = tmp_path / "quarantine"
    for path in (profile, user_data, capture, staging, quarantine):
        path.mkdir()

    context = EvidenceRedactionHostContext(
        authorized_launch=launch,
        operator_profile_root=profile.resolve(),
        user_data_roots=(user_data.resolve(),),
        temporary_capture_root=capture.resolve(),
        staging_root=staging.resolve(),
        quarantine_root=quarantine.resolve(),
        operator_identity_values=("live-operator", "live-host"),
        forbidden_persistence_roots=(workspace.resolve(),),
    )

    with caplog.at_level(logging.DEBUG):
        result = build_redaction_runtime_inputs(context)

    assert_portable_runtime_inputs(result)
    counts = dict(result.sensitive_values.source_class_counts)
    assert result.sensitive_values.secret_count >= 1
    assert any(key in counts for key in ("environment", "config_file", "keyring"))
    assert {rule.alias for rule in result.path_aliases} >= {
        "<workspace>",
        "<user-data>",
        "<temp>",
        "<staging>",
        "<quarantine>",
    }

    # Content-free assertions only — canary scan logs/exceptions for leaked values.
    env_secret = env["OPTIMUS_API_KEY"]
    shared = env["OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET"]
    rendered = repr(result.sensitive_values)
    assert env_secret not in rendered
    assert shared not in rendered
    assert env_secret not in caplog.text
    assert shared not in caplog.text
    assert "AuthorizedLaunch" not in type(result.sensitive_values).__name__
