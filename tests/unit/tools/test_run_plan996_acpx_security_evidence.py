"""Real gate-walk tests for the Plan 9.96 controlled ACP capture tool."""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_plan996_acpx_security_evidence as capture_tool
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_audit import LaunchAuditError
from optimus.acp.launch_gate import LaunchGateError, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import resolve_authorized_operator_paths
from optimus.acp.trusted_paths import TrustedPathError, resolve_workspace_identity
from tools.run_plan996_acpx_security_evidence import (
    CaptureResult,
    _capture_to_disk,
    _compute_evidence_manifest_hmac,
    _joined_scan,
    _known_secrets,
    _stream_sanitized,
    _verify_evidence_manifest,
    _write_evidence_manifest,
    append_authorized_audit,
    authorize_capture,
    capture_acpx,
    main,
    spawn_authorized_capture,
)


class FakeKeyring:
    """In-memory keyring permitted only for deterministic tool unit tests."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._values.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._values[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._values.pop((service, key), None)


def _environment(config_root: Path) -> dict[str, str]:
    return {
        "OPTIMUS_API_KEY": "test-authorized-api-key",
        "OPTIMUS_CONFIG_ROOT": str(config_root),
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        "UNRELATED_SENTINEL": "must-not-reach-child",
        # System keys a real Windows process needs (mirrors local_infra._SYSTEM_ENV_KEYS).
        # Included so the positive control reflects an environment a real child can
        # actually execute in, not a bare 5-key env that nothing real could run in.
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "PATHEXT": os.environ.get("PATHEXT", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
    }


def _environment_without_env_credentials(config_root: Path) -> dict[str, str]:
    """Mirrors Task 9's real configuration: no OPTIMUS_API_KEY in the env,
    credentials sourced from the keyring (Windows Credential Manager in
    production). This is the configuration that exposed the _known_secrets
    leak — the env-sourced fixture above hides it by putting OPTIMUS_API_KEY
    in the env, exercising the path that already worked."""
    return {
        "OPTIMUS_CONFIG_ROOT": str(config_root),
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        "UNRELATED_SENTINEL": "must-not-reach-child",
    }


def _keyring_with_credentials(*, shared_secret: str, provider_api_key: str, provider: str = "openrouter") -> FakeKeyring:
    """Populate a FakeKeyring with the same key names the real Windows
    Credential Manager store uses (service `optimus-cost-agent`), so the
    credential resolution path is the real keyring-sourced one, not the
    env-sourced one."""
    keyring = FakeKeyring()
    keyring.set_password("optimus-cost-agent", "local_gateway_shared_secret", shared_secret)
    keyring.set_password("optimus-cost-agent", "model_provider", provider)
    keyring.set_password("optimus-cost-agent", "model_provider_api_key", provider_api_key)
    return keyring


def _patch_keyring(monkeypatch: pytest.MonkeyPatch, fake: FakeKeyring) -> None:
    """Patch the global `keyring` module so `import keyring as keyring_backend`
    inside authorize_capture picks up the FakeKeyring. This is needed for
    CLI-level tests (main()) that can't pass keyring_backend directly."""
    import keyring as real_keyring

    monkeypatch.setattr(real_keyring, "get_password", fake.get_password)
    monkeypatch.setattr(real_keyring, "set_password", fake.set_password)
    monkeypatch.setattr(real_keyring, "delete_password", fake.delete_password)


def _write_durable_approval(
    *,
    workspace: Path,
    environment: dict[str, str],
    keyring: FakeKeyring,
    approval_runtime_root: Path,
) -> None:
    snapshot = LaunchEnvironmentSnapshot.capture(environment)
    identity = resolve_workspace_identity(workspace)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=approval_runtime_root)
    candidate = resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=identity,
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring,
    )
    store.write_durable(
        build_approval_record(
            mode="durable",
            workspace_identity=identity,
            security_literals=candidate.security_literals,
            secret_fingerprints=candidate.secret_fingerprints,
            monotonic_grants=candidate.monotonic_grants,
            model_observation=candidate.model_observation,
            hmac_key=store.hmac_key,
        )
    )


def test_capture_rejects_absent_durable_approval_before_audit_or_spawn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()

    with pytest.raises(LaunchGateError, match="NO_APPROVAL"):
        authorize_capture(
            workspace=workspace,
            environment=_environment(config_root),
            keyring_backend=FakeKeyring(),
            approval_runtime_root=tmp_path / "approval-runtime",
            launch_session_id="sess_absent",
        )

    assert not (workspace / ".optimus" / "launch-audit.ndjson").exists()


def test_capture_rejects_mismatched_durable_approval_before_audit_or_spawn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    approved_environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=approved_environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    changed_environment = {**approved_environment, "OPTIMUS_API_KEY": "different-api-key"}

    with pytest.raises(LaunchGateError, match="SNAPSHOT_MISMATCH"):
        authorize_capture(
            workspace=workspace,
            environment=changed_environment,
            keyring_backend=keyring,
            approval_runtime_root=approval_runtime_root,
            launch_session_id="sess_mismatch",
        )

    assert not (workspace / ".optimus" / "launch-audit.ndjson").exists()


def test_capture_stops_when_real_audit_runtime_root_is_a_regular_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    (workspace / ".optimus").write_text("not a directory", encoding="utf-8")

    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_audit_failure",
    )

    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        append_authorized_audit(capture)


def test_capture_acpx_blocks_child_when_composed_audit_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    (workspace / ".optimus").write_text("not a directory", encoding="utf-8")

    def child_must_not_start(*_args: object, **_kwargs: object) -> None:
        pytest.fail("child startup must not follow a failed audit append")

    monkeypatch.setattr(capture_tool, "spawn_authorized_capture", child_must_not_start)

    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        capture_acpx(
            workspace=workspace,
            environment=environment,
            keyring_backend=keyring,
            approval_runtime_root=approval_runtime_root,
            launch_session_id="sess_composed_audit_failure",
            command=[sys.executable, "-c", "raise SystemExit(0)"],
        )


def test_capture_revalidates_workspace_after_successful_audit_before_spawn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_workspace_changed",
    )
    audited = append_authorized_audit(capture)
    moved_workspace = tmp_path / "workspace-moved"
    workspace.rename(moved_workspace)
    workspace.mkdir()

    with pytest.raises(TrustedPathError, match="WORKSPACE_IDENTITY_CHANGED"):
        spawn_authorized_capture(audited, command=[sys.executable, "-c", "raise SystemExit(0)"])


def test_capture_spawns_child_with_only_exact_authorized_projection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_positive",
    )
    audited = append_authorized_audit(capture)

    process = spawn_authorized_capture(
        audited,
        command=[sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))"],
    )
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    child_environment = json.loads(stdout)
    assert "UNRELATED_SENTINEL" not in child_environment
    expected = {
        "OPTIMUS_AGENT_MODEL": "claude-haiku",
        "OPTIMUS_API_KEY": "test-authorized-api-key",
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_PRODUCTION_MODE": "false",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    }
    # System keys a real Windows process needs, merged from the gate's
    # sanctioned snapshot via the same allowlist as the committed Task 5
    # launcher (local_infra._SYSTEM_ENV_KEYS). UNRELATED_SENTINEL is NOT on
    # the allowlist, so the no-passthrough property survives.
    for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP"):
        value = os.environ.get(key, "")
        if value:
            expected[key] = value
    assert child_environment == expected


def test_known_secrets_folds_resolved_shared_secret_when_credentials_sourced_from_keyring(
    tmp_path: Path,
) -> None:
    """Regression guard for the round-14d leak path: when credentials come
    from the keyring (Task 9's real configuration — no .env, no
    OPTIMUS_API_KEY in the env), the resolved shared secret is projected into
    the child's OPTIMUS_API_KEY by apply_local_defaults but is NOT in
    candidate.inherited.values / secret_inventory. _known_secrets must fold
    it in or an acpx echo of OPTIMUS_API_KEY goes raw to disk — Task 8's
    purpose defeated in precisely the configuration Task 9 runs.

    The env-sourced fixture (_environment) hides this by putting
    OPTIMUS_API_KEY in the env, exercising the path that already worked.
    """
    shared_secret = "keyring-resolved-shared-secret"
    provider_api_key = "keyring-resolved-provider-api-key"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = _keyring_with_credentials(
        shared_secret=shared_secret, provider_api_key=provider_api_key
    )
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment_without_env_credentials(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_keyring_secrets",
    )

    known = _known_secrets(capture)

    # The shared secret is projected into the child's OPTIMUS_API_KEY by
    # apply_local_defaults; it must be in the sanitizer's known-secrets list
    # or an acpx echo of OPTIMUS_API_KEY goes raw to disk.
    assert shared_secret in known
    # The resolved provider API key is projected into the gateway child env;
    # it must likewise be folded in.
    assert provider_api_key in known
    # The child env must actually carry the projected shared secret under
    # OPTIMUS_API_KEY — otherwise the assertion above would be vacuous.
    assert capture.agent_environ["OPTIMUS_API_KEY"] == shared_secret


def _write_diagnostic_grant(
    *,
    keyring: FakeKeyring,
    store: KeyringApprovalStore,
    workspace_digest: str,
    approval_id: str,
    launch_session_id: str,
    grant_id: str = "diag_test_grant",
) -> None:
    """Write a valid, correctly-signed diagnostic grant into the keyring."""
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

    from optimus.acp.launch_approvals import DIAGNOSTIC_TTL_SECONDS, DiagnosticGrant, compute_grant_hmac

    unsigned = DiagnosticGrant(
        grant_id=grant_id,
        workspace_digest=workspace_digest,
        approval_id=approval_id,
        launch_session_id=launch_session_id,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=DIAGNOSTIC_TTL_SECONDS),
        record_hmac="",
    )
    grant = replace(unsigned, record_hmac=compute_grant_hmac(unsigned, hmac_key=store.hmac_key))
    store.write_diagnostic_grant(grant)


def test_elevated_capture_fails_closed_on_missing_diagnostic_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--mode elevated with --diagnostic-grant-id that doesn't exist in the
    keyring must FAIL CLOSED (exit 2, value-safe message), NOT silently
    downgrade to ordinary. The serving process (__main__.py) downgrades
    because ordinary is the safe serving mode; an evidence harness that
    claims elevated but captured ordinary is wrong-mode evidence.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "_capture_to_disk", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "elevated",
        "--diagnostic-grant-id",
        "diag_nonexistent",
        "--launch-session-id",
        "sess_elevated_missing",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "GRANT_NOT_FOUND" in captured.err


def test_elevated_capture_fails_closed_on_wrong_session_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--mode elevated with a grant bound to a DIFFERENT launch session ID
    must FAIL CLOSED (exit 2), not silently downgrade."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    # Write a grant bound to a DIFFERENT session ID
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.acp.trusted_paths import resolve_workspace_identity

    identity = resolve_workspace_identity(workspace)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=approval_runtime_root)
    _write_diagnostic_grant(
        keyring=keyring,
        store=store,
        workspace_digest=identity.digest,
        approval_id="appr_test",
        launch_session_id="sess_wrong",
        grant_id="diag_wrong_session",
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "_capture_to_disk", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "elevated",
        "--diagnostic-grant-id",
        "diag_wrong_session",
        "--launch-session-id",
        "sess_correct",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "GRANT_SESSION_MISMATCH" in captured.err


def test_elevated_capture_consumes_valid_grant_and_records_granted_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--mode elevated with a valid grant: the grant is consumed (single-use,
    deleted from keyring), the audit event records diagnostic_grant_state:
    'granted', and the capture proceeds. This proves the elevated path works
    end-to-end with a real grant, not just that failures fail closed."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    # Write a valid grant bound to the CORRECT session ID
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.acp.trusted_paths import resolve_workspace_identity

    identity = resolve_workspace_identity(workspace)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=approval_runtime_root)
    grant_id = "diag_valid_grant"
    session_id = "sess_elevated_valid"
    _write_diagnostic_grant(
        keyring=keyring,
        store=store,
        workspace_digest=identity.digest,
        approval_id="appr_test",
        launch_session_id=session_id,
        grant_id=grant_id,
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(
        capture_tool,
        "_capture_to_disk",
        lambda *a, **k: CaptureResult(exit_code=0, rule_counts={}),
    )
    monkeypatch.setattr(capture_tool, "_joined_scan", lambda *a, **k: {"hit": False, "rules_fired": [], "scanned_artifacts": []})
    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", lambda *a, **k: None)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "elevated",
        "--diagnostic-grant-id",
        grant_id,
        "--launch-session-id",
        session_id,
    ]
    exit_code = main(arguments)

    assert exit_code == 0
    # The grant must have been consumed (single-use, deleted from keyring)
    assert keyring.get_password("optimus-cost-agent-approvals", f"grant:{grant_id}") is None
    # The audit event must record diagnostic_grant_state: granted
    audit_path = workspace / ".optimus" / "launch-audit.ndjson"
    assert audit_path.is_file()
    audit_text = audit_path.read_text(encoding="utf-8")
    assert '"diagnostic_grant_state":"granted"' in audit_text or '"diagnostic_grant_state": "granted"' in audit_text


def test_elevated_mode_without_diagnostic_grant_id_is_rejected_before_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--mode elevated with NO --diagnostic-grant-id must exit 2 before
    authorization — the capture must not proceed ungated. This is the
    omitted-path case the reviewer flagged: every grant-failure test supplied
    a grant id, but the flag-simply-absent path was never tested. An evidence
    artifact that claims elevated but captured with no grant ever existing is
    wrong-mode evidence.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    environment = _environment(config_root)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "authorize_capture", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "elevated",
        "--launch-session-id",
        "sess_elevated_no_grant",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--mode elevated requires --diagnostic-grant-id" in captured.err


def test_ordinary_mode_with_diagnostic_grant_id_is_rejected_before_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--mode ordinary WITH --diagnostic-grant-id must exit 2 before
    authorization — must not burn a single-use grant on an ordinary capture.
    The grant must NOT be consumed (still present in the keyring afterward).
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    # Write a grant so we can verify it is NOT consumed
    from optimus.acp.launch_approvals import KeyringApprovalStore
    from optimus.acp.trusted_paths import resolve_workspace_identity

    identity = resolve_workspace_identity(workspace)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=approval_runtime_root)
    grant_id = "diag_ordinary_must_not_burn"
    _write_diagnostic_grant(
        keyring=keyring,
        store=store,
        workspace_digest=identity.digest,
        approval_id="appr_test",
        launch_session_id="sess_ordinary",
        grant_id=grant_id,
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "authorize_capture", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "ordinary",
        "--diagnostic-grant-id",
        grant_id,
        "--launch-session-id",
        "sess_ordinary",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--mode ordinary must not be combined with --diagnostic-grant-id" in captured.err
    # The grant must NOT have been consumed (still present in keyring)
    assert keyring.get_password("optimus-cost-agent-approvals", f"grant:{grant_id}") is not None


def test_elevated_capture_fails_closed_on_expired_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """--mode elevated with an expired grant must FAIL CLOSED (exit 2), not
    silently downgrade to ordinary. The ruling names expiry explicitly; unit
    tests cover consume_diagnostic_grant's expiry check, but the CLI
    conversion path (ApprovalError → LaunchGateError → exit 2) deserves its
    own test.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    # Write an already-expired grant
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

    from optimus.acp.launch_approvals import (
        DiagnosticGrant,
        KeyringApprovalStore,
        compute_grant_hmac,
    )
    from optimus.acp.trusted_paths import resolve_workspace_identity

    identity = resolve_workspace_identity(workspace)
    store = KeyringApprovalStore(keyring_backend=keyring, runtime_root=approval_runtime_root)
    grant_id = "diag_expired"
    session_id = "sess_expired"
    unsigned = DiagnosticGrant(
        grant_id=grant_id,
        workspace_digest=identity.digest,
        approval_id="appr_test",
        launch_session_id=session_id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        record_hmac="",
    )
    expired_grant = replace(unsigned, record_hmac=compute_grant_hmac(unsigned, hmac_key=store.hmac_key))
    store.write_diagnostic_grant(expired_grant)
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "_capture_to_disk", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "elevated",
        "--diagnostic-grant-id",
        grant_id,
        "--launch-session-id",
        session_id,
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "GRANT_EXPIRED" in captured.err


def test_capture_creates_output_directory_before_starting_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "new-output"

    class CompletedProcess:
        stdout = io.StringIO("")
        stderr = io.StringIO("")

        def wait(self, timeout: float | None = None) -> int:
            return 0

    def start_after_output_directory_exists(*_args: object, **_kwargs: object) -> CompletedProcess:
        assert output_dir.is_dir()
        return CompletedProcess()

    class AuditedSentinel:
        capture = object()

    monkeypatch.setattr(capture_tool, "spawn_authorized_capture", start_after_output_directory_exists)
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())

    result = _capture_to_disk(AuditedSentinel(), command=["acpx"], output_dir=output_dir)
    assert result.exit_code == 0


class FixedSizeReadSource(io.StringIO):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> str:
        self.read_sizes.append(size)
        return super().read(size)


def test_stream_sanitized_uses_fixed_size_reads(tmp_path: Path) -> None:
    source = FixedSizeReadSource("safe transcript")
    destination = tmp_path / "transcript.txt"

    _stream_sanitized(source, destination, known_secrets=())

    assert destination.read_text(encoding="utf-8") == "safe transcript"
    assert len(source.read_sizes) >= 2
    assert set(source.read_sizes) == {8192}


def test_stream_sanitized_redacts_known_secret_before_persisting_to_disk(
    tmp_path: Path,
) -> None:
    """Canary for the _stream_sanitized file_open + text_write sinks: a known
    secret present in the child's stdout must not reach the persisted
    transcript file. This is the load-bearing sanitization property — without
    it, an acpx echo of OPTIMUS_API_KEY goes raw to disk. The fixed-size-read
    test above uses known_secrets=() and safe content, so it does not prove
    the sanitizer is load-bearing here."""
    canary = "canary-secret-must-not-persist"
    source = io.StringIO(f"line before\n{canary}\nline after")
    destination = tmp_path / "transcript.stdout"

    _stream_sanitized(source, destination, known_secrets=(canary,))

    persisted = destination.read_text(encoding="utf-8")
    assert canary not in persisted
    assert "line before" in persisted
    assert "line after" in persisted


class ControlledChunkSource(io.StringIO):
    """A source that yields text in caller-controlled chunk sizes, so a canary
    can be split at an exact boundary inside the secret."""

    def __init__(self, text: str, chunk_sizes: list[int]) -> None:
        super().__init__(text)
        self._chunk_sizes = list(chunk_sizes)
        self._index = 0

    def read(self, size: int = -1) -> str:
        if self._index < len(self._chunk_sizes):
            size = self._chunk_sizes[self._index]
            self._index += 1
        return super().read(size)


_CROSS_CHUNK_CANARY = "canary-split-across-chunk-boundary"


@pytest.mark.parametrize(
    ("split_after"),
    range(1, len(_CROSS_CHUNK_CANARY)),
)
def test_stream_sanitized_redacts_canary_split_across_chunk_boundary(
    tmp_path: Path, split_after: int
) -> None:
    """Exhaustive cross-chunk canary-split matrix: a known secret split across
    a chunk boundary at EVERY position (1..len(canary)-1) must not reach the
    persisted file. The StreamingTextSanitizer unit tests (test_sanitization.py)
    prove the sanitizer itself handles cross-chunk splits; this test proves the
    _stream_sanitized capture path (which reads in fixed-size chunks and feeds
    to the sanitizer) doesn't let a split canary through to disk.

    Exhaustive range (not hand-picked positions) because the classic
    streaming-sanitizer failure mode is the tail region (almost-whole secret
    in chunk 1), which a hand-picked list can silently miss. The range bound
    is derived from len(_CROSS_CHUNK_CANARY) so a canary change can't silently
    shrink coverage.

    Plan 9.96 Task 8 Step 1: 'Split one canary across every adjacent
    line/chunk pair and assert no prefix or suffix reaches disk.'
    """
    canary = _CROSS_CHUNK_CANARY
    prefix = "data-before "
    suffix = " data-after"
    full_text = f"{prefix}{canary}{suffix}"
    # Split the text so the chunk boundary falls at `split_after` chars into
    # the canary (i.e., inside the secret).
    canary_start = len(prefix)
    boundary = canary_start + split_after
    chunk_sizes = [boundary, len(full_text) - boundary]
    source = ControlledChunkSource(full_text, chunk_sizes)
    destination = tmp_path / "transcript.stdout"

    _stream_sanitized(source, destination, known_secrets=(canary,))

    persisted = destination.read_text(encoding="utf-8")
    assert canary not in persisted
    assert prefix.strip() in persisted
    assert suffix.strip() in persisted


def test_stream_sanitized_fail_closed_on_sanitizer_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed: if the sanitizer raises, no raw secret reaches disk. The
    file may contain partial sanitized output, but never the raw secret.
    Plan 9.96 Task 8 Step 1: 'fail-closed sanitizer-failure tests.'"""
    canary = "raw-secret-must-not-reach-disk"
    source = io.StringIO(f"safe-prefix {canary} safe-suffix")
    destination = tmp_path / "transcript.stdout"

    original_feed = capture_tool.StreamingTextSanitizer.feed

    def failing_feed(self: object, chunk: str) -> str:
        if canary in chunk:
            raise RuntimeError("simulated sanitizer failure")
        return original_feed(self, chunk)  # type: ignore[arg-type]

    monkeypatch.setattr(capture_tool.StreamingTextSanitizer, "feed", failing_feed)

    with pytest.raises(RuntimeError, match="simulated sanitizer failure"):
        _stream_sanitized(source, destination, known_secrets=(canary,))

    if destination.exists():
        persisted = destination.read_text(encoding="utf-8")
        assert canary not in persisted


def test_main_generates_launch_session_id_when_absent(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--launch-session-id`` is optional (plan Task 8 CLI spec puts it in the
    optional bracket); when absent, main() generates one via
    ``sess_{secrets.token_hex(12)}``, mirroring the committed _cmd_run
    precedent (launch_approval_cli.py:395)."""
    captured_session_ids: list[str] = []

    def spy_authorize(**kwargs: object) -> object:
        captured_session_ids.append(str(kwargs.get("launch_session_id", "")))
        return object()  # type: ignore[return-value]

    monkeypatch.setattr(capture_tool, "authorize_capture", spy_authorize)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool, "append_authorized_audit", lambda _capture: object())
    monkeypatch.setattr(
        capture_tool,
        "_capture_to_disk",
        lambda *a, **k: CaptureResult(exit_code=0, rule_counts={}),
    )
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(capture_tool, "_joined_scan", lambda *a, **k: {"hit": False, "rules_fired": [], "scanned_artifacts": []})
    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", lambda *a, **k: None)

    arguments = [
        "capture",
        "--workspace",
        "workspace",
        "--output-dir",
        "output",
        "--mode",
        "ordinary",
    ]
    assert main(arguments) == 0
    assert len(captured_session_ids) == 1
    assert captured_session_ids[0].startswith("sess_")
    # token_hex(12) = 24 hex chars + "sess_" prefix = 29 chars total
    assert len(captured_session_ids[0]) == 29


def test_spawn_authorized_capture_merges_system_env_keys(tmp_path: Path) -> None:
    """The child env must include the system keys a real Windows process needs
    (PATH, SYSTEMROOT, etc.), merged from the gate's sanctioned snapshot,
    not a bare OPTIMUS_* set that nothing real could execute in. Follows the
    committed Task 5 launcher precedent (local_infra._SYSTEM_ENV_KEYS)."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_system_keys",
    )
    audited = append_authorized_audit(capture)

    process = spawn_authorized_capture(
        audited,
        command=[sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))"],
    )
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    child_environment = json.loads(stdout)
    # System keys from the allowlist must be present (sourced from the snapshot)
    assert "PATH" in child_environment
    assert "SYSTEMROOT" in child_environment
    assert "UNRELATED_SENTINEL" not in child_environment


def test_main_returns_exit_2_with_clean_message_on_unapproved_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The most common operator error (forgot to approve) must produce a clean
    message and exit 2, NOT an uncaught traceback with exit 1. The traceback
    also printed the full workspace path and internal call chain — a minor
    path-leak on the expected rejection path. This test asserts exit 2, a
    value-safe remediation message, and no traceback on stderr.

    Found by the partial smoke (reviewer-run 2026-07-17): the real tool
    against a fresh unapproved workspace produced an uncaught
    LaunchGateError(NO_APPROVAL) traceback with EXITCODE=1.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    environment = _environment(config_root)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "_capture_to_disk", pytest.fail)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "ordinary",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "no launch approval" in captured.err.lower()
    assert "optimus-trust" in captured.err
    assert "approve --mode durable" in captured.err


def test_main_returns_exit_2_on_workspace_relocation_between_audit_and_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The TOCTOU vector — workspace relocated between authorize and spawn —
    must produce a clean message and exit 2, NOT an uncaught traceback with
    exit 1. ``revalidate_workspace_identity`` fires at spawn time inside
    ``_capture_to_disk``; if ``main()``'s try/except doesn't cover that call,
    ``TrustedPathError(WORKSPACE_IDENTITY_CHANGED)`` propagates uncaught.

    Same defect class as the NO_APPROVAL gap (FIX 5), on the
    security-critical TOCTOU path. The existing function-level test
    (``test_capture_revalidates_workspace_after_successful_audit_before_spawn``)
    proves the function raises; this test proves ``main()`` handles it.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)

    original_spawn = capture_tool.spawn_authorized_capture

    def spawn_after_relocating(audited: object, **kwargs: object) -> object:
        # Relocate the workspace between audit and spawn — the real TOCTOU
        # vector. revalidate_workspace_identity will see the changed path.
        moved = tmp_path / "workspace-moved"
        workspace.rename(moved)
        workspace.mkdir()
        return original_spawn(audited, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(capture_tool, "spawn_authorized_capture", spawn_after_relocating)

    arguments = [
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(tmp_path / "output"),
        "--mode",
        "ordinary",
    ]
    exit_code = main(arguments)
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Traceback" not in captured.err
    assert "WORKSPACE_IDENTITY_CHANGED" in captured.err or "workspace" in captured.err.lower()


# --- Step 3: joined promotion scan + HMAC manifest + verify ---


def _write_clean_artifacts(output_dir: Path, *, stdout_text: str = "safe output", stderr_text: str = "") -> None:
    """Write sanitized transcript artifacts for manifest/verify tests."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "transcript.stdout").write_text(stdout_text, encoding="utf-8")
    (output_dir / "transcript.stderr").write_text(stderr_text, encoding="utf-8")


def _store_hmac_key(keyring: FakeKeyring, hmac_key: bytes) -> None:
    """Store an HMAC key in the FakeKeyring using the same base64url encoding
    the real KeyringApprovalStore uses."""
    import base64
    keyring.set_password(
        "optimus-cost-agent-approvals",
        "hmac_integrity_key",
        base64.urlsafe_b64encode(hmac_key).decode("ascii"),
    )


def test_evidence_manifest_hmac_is_deterministic_and_domain_separated() -> None:
    """The evidence manifest HMAC must be deterministic (same fields + key →
    same HMAC) and domain-separated (different from approval-record or grant
    HMACs — a different domain prefix means cross-type collisions are
    impossible)."""
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    fields = {
        "sanitizer_version": "p996-streaming-sanitizer-v1",
        "rule_counts": {"exact_secret_replacement": 1},
        "artifact_sha256": {"transcript.stdout": "abc123"},
        "joined_scan": {"hit": False, "rules_fired": [], "scanned_artifacts": ["transcript.stdout"]},
    }
    h1 = _compute_evidence_manifest_hmac(fields, hmac_key)
    h2 = _compute_evidence_manifest_hmac(fields, hmac_key)
    assert h1 == h2  # deterministic
    # Domain separation: a different domain (e.g. approval-record) would
    # produce a different HMAC for the same fields + key.
    import hashlib
    import hmac as hmac_mod
    other_domain = b"p996-record-hmac-v1"
    canonical = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    other_hmac = hmac_mod.new(hmac_key, other_domain + b"\x00" + canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    assert h1 != other_hmac  # domain-separated


def test_evidence_manifest_contains_no_secret_material(tmp_path: Path) -> None:
    """The written manifest must contain no secret material — only sanitizer
    version, rule counts, artifact SHA-256, joined-scan result, timestamp, and
    HMAC."""
    _write_clean_artifacts(tmp_path, stdout_text="safe output")
    canary = "secret-that-must-not-appear-in-manifest"
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"

    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={"exact_secret_replacement": 1},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": ["transcript.stdout"]},
        hmac_key=hmac_key,
    )
    manifest_text = manifest_path.read_text(encoding="utf-8")
    assert canary not in manifest_text
    manifest = json.loads(manifest_text)
    assert "sanitizer_version" in manifest
    assert "rule_counts" in manifest
    assert "artifact_sha256" in manifest
    assert "joined_scan" in manifest
    assert "hmac" in manifest
    assert "created_at" in manifest


def test_joined_scan_detects_secret_that_survived_sanitization(tmp_path: Path) -> None:
    """If a known secret value appears verbatim in the sanitized output, the
    joined scan must detect it (hit=True). This is the sanitizer-failure
    detection path — a hit means the sanitizer failed and the artifact must be
    quarantined."""
    canary = "leaked-secret-in-sanitized-output"
    _write_clean_artifacts(tmp_path, stdout_text=f"prefix {canary} suffix")

    result = _joined_scan(tmp_path, known_secrets=(canary,))

    assert result["hit"] is True
    assert len(result["rules_fired"]) > 0
    assert any("exact_secret_leak" in r for r in result["rules_fired"])


def test_joined_scan_passes_on_clean_output(tmp_path: Path) -> None:
    """Clean sanitized output (no secrets, no patterns) must produce hit=False."""
    _write_clean_artifacts(tmp_path, stdout_text="safe output with no secrets")

    result = _joined_scan(tmp_path, known_secrets=("secret-not-present",))

    assert result["hit"] is False
    assert result["rules_fired"] == []


def test_verify_accepts_valid_manifest_and_artifacts(tmp_path: Path) -> None:
    """End-to-end: write clean artifacts + manifest, then verify passes."""
    _write_clean_artifacts(tmp_path, stdout_text="acpx 0.12.0")
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    scan_result = _joined_scan(tmp_path, known_secrets=())
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result=scan_result,
        hmac_key=hmac_key,
    )

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)

    exit_code = _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring)
    assert exit_code == 0


def test_verify_rejects_tampered_manifest_hmac(tmp_path: Path) -> None:
    """Adversarial: a manifest whose HMAC was recomputed with a different key
    (or tampered) must be rejected with EVIDENCE_HMAC_MISMATCH and the
    artifacts quarantined."""
    _write_clean_artifacts(tmp_path, stdout_text="safe output")
    writer_key = b"writer-hmac-key-32-bytes-long!!"
    verifier_key = b"verifier-hmac-key-32-bytes!!"
    scan_result = _joined_scan(tmp_path, known_secrets=())
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result=scan_result,
        hmac_key=writer_key,
    )

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, verifier_key)

    exit_code = _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring)
    assert exit_code == 1
    # Artifacts must be quarantined
    assert (tmp_path / "quarantine").is_dir()
    assert (tmp_path / "quarantine" / "transcript.stdout").is_file()


def test_verify_rejects_tampered_artifact_with_recomputed_digest(tmp_path: Path) -> None:
    """Adversarial: an artifact tampered post-manifest (content changed, so
    SHA-256 no longer matches) must be rejected with EVIDENCE_DIGEST_MISMATCH
    and quarantined — even if the manifest HMAC is valid."""
    _write_clean_artifacts(tmp_path, stdout_text="original output")
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    scan_result = _joined_scan(tmp_path, known_secrets=())
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result=scan_result,
        hmac_key=hmac_key,
    )
    # Tamper with the artifact AFTER the manifest was written
    (tmp_path / "transcript.stdout").write_text("tampered content", encoding="utf-8")

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)

    exit_code = _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring)
    assert exit_code == 1
    assert (tmp_path / "quarantine").is_dir()


def test_verify_rejects_canary_planted_post_sanitization(tmp_path: Path) -> None:
    """Adversarial: a canary planted in the artifact AFTER sanitization (so
    the manifest HMAC is valid, the digest matches the tampered content, but
    the pattern scan catches a bearer token or secret assignment that should
    have been redacted) must be rejected with EVIDENCE_PATTERN_HIT and
    quarantined."""
    # Write an artifact with a bearer token pattern that should have been
    # redacted by the sanitizer — simulating a post-sanitization plant.
    _write_clean_artifacts(tmp_path, stdout_text="Authorization: Bearer sk-leaked-token")
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    # Build a manifest that claims the scan passed (the scan at capture time
    # would have caught this, but we're testing the verify-time re-check)
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": ["transcript.stdout"]},
        hmac_key=hmac_key,
    )

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)

    exit_code = _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring)
    assert exit_code == 1
    assert (tmp_path / "quarantine").is_dir()


def test_verify_rejects_tampered_manifest_field(tmp_path: Path) -> None:
    """R1: a manifest field (not the hmac) tampered AFTER signing must be
    rejected with EVIDENCE_HMAC_MISMATCH + quarantine. The HMAC covers the
    ENTIRE parsed manifest minus the `hmac` field (sorted compact canonical
    JSON), so any field modification breaks it. This pins the whole-dict
    canonicalization against a future subset-signing refactor.
    """
    _write_clean_artifacts(tmp_path, stdout_text="safe output")
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    scan_result = _joined_scan(tmp_path, known_secrets=())
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result=scan_result,
        hmac_key=hmac_key,
    )
    # Tamper with a non-digest field AFTER the manifest was written
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["created_at"] = "2099-01-01T00:00:00+00:00"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)

    exit_code = _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring)
    assert exit_code == 1
    assert (tmp_path / "quarantine").is_dir()


def test_joined_scan_catches_unicode_escaped_secret_in_json(tmp_path: Path) -> None:
    """R2: a secret unicode-escaped inside a JSON string (e.g.
    ``\u0068unter2`` for ``hunter2``) evades the raw-text scan but must be
    caught by the decoded-JSON scan layer. This is the plan-conformance gap
    the reviewer found: the frozen plan requires scanning **decoded**
    transcript records, not just raw text.

    Sensitivity proof: the raw-text scan alone would miss this — the escaped
    form does not contain the literal secret string.
    """
    canary = "hunter2"
    # Construct a JSON line where the secret is unicode-escaped in the JSON
    # encoding: \u0068 = 'h'. The raw JSON text contains "\u0068unter2", not
    # "hunter2" — but json.loads decodes it to "hunter2".
    json_line = '{"token": "\\u0068unter2"}'
    _write_clean_artifacts(tmp_path, stdout_text=json_line)

    # The raw text does NOT contain the literal canary
    raw_content = (tmp_path / "transcript.stdout").read_text(encoding="utf-8")
    assert canary not in raw_content

    # But the decoded JSON string DOES — the joined scan must catch it
    result = _joined_scan(tmp_path, known_secrets=(canary,))
    assert result["hit"] is True
    assert any("decoded_secret_leak" in r for r in result["rules_fired"])


def test_joined_scan_catches_secret_split_across_real_agent_message_chunk_records(
    tmp_path: Path,
) -> None:
    """R2c: a secret split across two REAL agent_message_chunk records (built
    by the repo's own producer ``build_agent_message_chunk_notification``) must
    be caught by the joined-decoded-strings scan layer. Text lives at
    ``update.content.text`` in the real shape — NOT ``params.text``.

    This test uses the real producer, not a hand-built dict, because the
    reviewer proved that R2b's protocol-specific extractor passed its own
    hand-built test while failing on the real shape.
    """
    from optimus.acp.shapes import build_agent_message_chunk_notification

    canary = "split-across-records-canary"
    half = len(canary) // 2
    record_1 = json.dumps(
        build_agent_message_chunk_notification(session_id="s1", text=canary[:half])
    )
    record_2 = json.dumps(
        build_agent_message_chunk_notification(session_id="s1", text=canary[half:])
    )
    _write_clean_artifacts(tmp_path, stdout_text=f"{record_1}\n{record_2}\n")

    # The raw text does NOT contain the literal canary
    raw_content = (tmp_path / "transcript.stdout").read_text(encoding="utf-8")
    assert canary not in raw_content

    # The joined scan must catch it via the joined-decoded-strings layer
    result = _joined_scan(tmp_path, known_secrets=(canary,))
    assert result["hit"] is True
    assert any("joined_decoded_secret_leak" in r for r in result["rules_fired"])


def test_joined_scan_catches_secret_split_across_generic_json_records(tmp_path: Path) -> None:
    """R2c: path-agnostic coverage — a secret split across two generic JSON
    records using ``params.delta`` (the reviewer's original probe shape, not
    the real ACP shape) must also be caught. Proves the per-path join is
    shape-agnostic, not fitted to one protocol.
    """
    canary = "split-across-records-canary"
    half = len(canary) // 2
    record_1 = json.dumps({"method": "session/update", "params": {"delta": canary[:half]}})
    record_2 = json.dumps({"method": "session/update", "params": {"delta": canary[half:]}})
    _write_clean_artifacts(tmp_path, stdout_text=f"{record_1}\n{record_2}\n")

    # The raw text does NOT contain the literal canary
    raw_content = (tmp_path / "transcript.stdout").read_text(encoding="utf-8")
    assert canary not in raw_content

    # The joined scan must catch it via the joined-decoded-strings layer
    result = _joined_scan(tmp_path, known_secrets=(canary,))
    assert result["hit"] is True
    assert any("joined_decoded_secret_leak" in r for r in result["rules_fired"])


def test_joined_scan_catches_secret_intact_in_single_json_record(tmp_path: Path) -> None:
    """Control for R2c: the same canary intact in a single JSON record must
    also be caught (by the per-string decoded layer). This proves the joined
    layer isn't the ONLY thing catching secrets — it's the safety net for the
    cross-record-boundary case the per-string layer misses.
    """
    from optimus.acp.shapes import build_agent_message_chunk_notification

    canary = "split-across-records-canary"
    record = json.dumps(
        build_agent_message_chunk_notification(session_id="s1", text=canary)
    )
    _write_clean_artifacts(tmp_path, stdout_text=f"{record}\n")

    result = _joined_scan(tmp_path, known_secrets=(canary,))
    assert result["hit"] is True
    assert any("decoded_secret_leak" in r for r in result["rules_fired"])


# --- Step 4: legacy 9.87/9.88 locator rejection ---


def test_verify_rejects_plan987_locator_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4: the verify path must reject a Plan 9.87 raw-transcript locator
    as Plan 9.96 evidence, by name, and name the controlled capture command."""
    legacy_manifest = tmp_path / "plan-9-87-evidence-manifest.json"
    legacy_manifest.write_text("{}", encoding="utf-8")

    exit_code = main([
        "verify",
        "--manifest",
        str(legacy_manifest),
        "--artifact-dir",
        str(tmp_path),
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "plan-9-87" in captured.err.lower() or "plan987" in captured.err.lower()
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_verify_rejects_plan988_locator_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4: the verify path must reject a Plan 9.88 raw-transcript locator."""
    legacy_manifest = tmp_path / "plan-9-88-fu4b-evidence.json"
    legacy_manifest.write_text("{}", encoding="utf-8")

    exit_code = main([
        "verify",
        "--manifest",
        str(legacy_manifest),
        "--artifact-dir",
        str(tmp_path),
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "plan-9-88" in captured.err.lower() or "plan988" in captured.err.lower()
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_verify_rejects_run_plan987_helper_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4: reject a path containing the frozen helper's name
    (run_plan987_acpx_live_evidence)."""
    legacy_dir = tmp_path / "run_plan987_acpx_live_evidence_output"
    legacy_dir.mkdir()
    legacy_manifest = legacy_dir / "manifest.json"
    legacy_manifest.write_text("{}", encoding="utf-8")

    exit_code = main([
        "verify",
        "--manifest",
        str(legacy_manifest),
        "--artifact-dir",
        str(legacy_dir),
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "run_plan987" in captured.err
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_verify_rejects_run_plan988_helper_output_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4: reject a path containing the frozen helper's name
    (run_plan988_fu4b_live_evidence)."""
    legacy_dir = tmp_path / "run_plan988_fu4b_live_evidence_output"
    legacy_dir.mkdir()
    legacy_manifest = legacy_dir / "manifest.json"
    legacy_manifest.write_text("{}", encoding="utf-8")

    exit_code = main([
        "verify",
        "--manifest",
        str(legacy_manifest),
        "--artifact-dir",
        str(legacy_dir),
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "run_plan988" in captured.err
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_capture_rejects_plan987_artifact_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Step 4: the capture path must also reject a legacy locator in
    --output-dir."""
    legacy_output = tmp_path / "plan-9-87-output"
    legacy_output.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    environment = _environment(config_root)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "authorize_capture", pytest.fail)

    exit_code = main([
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(legacy_output),
        "--mode",
        "ordinary",
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "plan-9-87" in captured.err.lower() or "plan987" in captured.err.lower()
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_verify_rejects_raw_transcript_locator_from_frozen_helper(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S4b: the verify path must reject the actual raw-transcript filename the
    frozen helpers write — ``attempt-{N}-transcript.jsonl`` — constructed
    exactly as the helpers do (run_plan987:1231, run_plan988:971).

    This is the literal 'raw transcript locator' the frozen plan Step 4 names.
    The four substring patterns miss it because the filename contains none
    of them.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Construct the path EXACTLY as the frozen helpers do
    raw_transcript = workspace / "attempt-1-transcript.jsonl"
    raw_transcript.write_text("{}", encoding="utf-8")

    exit_code = main([
        "verify",
        "--manifest",
        str(raw_transcript),
        "--artifact-dir",
        str(workspace),
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "attempt" in captured.err.lower() and "transcript" in captured.err.lower()
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_capture_rejects_raw_transcript_locator_in_output_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """S4b: the capture path must also reject a legacy raw-transcript locator
    in --output-dir."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # A directory containing the frozen helper's raw transcript
    legacy_output = tmp_path / "legacy-evidence"
    legacy_output.mkdir()
    (legacy_output / "attempt-3-transcript.jsonl").write_text("{}", encoding="utf-8")
    config_root = tmp_path / "config"
    config_root.mkdir()
    environment = _environment(config_root)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool, "authorize_capture", pytest.fail)

    exit_code = main([
        "capture",
        "--workspace",
        str(workspace),
        "--output-dir",
        str(legacy_output / "attempt-3-transcript.jsonl"),
        "--mode",
        "ordinary",
    ])

    assert exit_code == 2
    captured = capsys.readouterr()
    assert "attempt" in captured.err.lower() and "transcript" in captured.err.lower()
    assert "run_plan996_acpx_security_evidence" in captured.err


def test_996_artifact_names_are_not_rejected_as_legacy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S4b negative control: the 9.96 tool's own artifact names
    (transcript.stdout, transcript.stderr, sanitizer-manifest.json) must NOT
    be rejected as legacy locators. Guards against an over-broad pattern
    breaking the tool's own output."""
    from tools.run_plan996_acpx_security_evidence import _is_legacy_locator

    assert _is_legacy_locator(Path("output/transcript.stdout")) is None
    assert _is_legacy_locator(Path("output/transcript.stderr")) is None
    assert _is_legacy_locator(Path("output/sanitizer-manifest.json")) is None
