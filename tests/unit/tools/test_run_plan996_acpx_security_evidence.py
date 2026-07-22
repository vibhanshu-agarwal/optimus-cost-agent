"""Real gate-walk tests for the Plan 9.96 controlled ACP capture tool."""

from __future__ import annotations

import ast
import inspect
import io
import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools.run_plan996_acpx_security_evidence as capture_tool
from optimus.acp.launch_approvals import KeyringApprovalStore, build_approval_record
from optimus.acp.launch_audit import LaunchAuditError
from optimus.acp.launch_gate import LaunchGateError, resolve_launch_candidate
from optimus.acp.launch_policy import LaunchEnvironmentSnapshot
from optimus.acp.operator_paths import bootstrap_workspace_runtime_root, resolve_authorized_operator_paths
from optimus.acp.trusted_paths import TrustedPathError, resolve_workspace_identity
from tools.run_plan996_acpx_security_evidence import (
    SESSION_TASK,
    CaptureResult,
    _build_capture_command,
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


def _system_environment() -> dict[str, str]:
    """Return only non-empty bootstrap keys from the sanctioned snapshot allowlist."""
    return {
        name: value
        for name in capture_tool._SYSTEM_ENV_KEYS
        if (value := os.environ.get(name, ""))
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
    monkeypatch.setattr(capture_tool, "keyring", fake)


def _write_durable_approval(
    *,
    workspace: Path,
    environment: dict[str, str],
    keyring: FakeKeyring,
    approval_runtime_root: Path,
) -> None:
    snapshot = LaunchEnvironmentSnapshot.capture(environment)
    paths = resolve_authorized_operator_paths(workspace_root=workspace, snapshot_values=snapshot.values)
    bootstrap_workspace_runtime_root(paths)
    identity = resolve_workspace_identity(workspace)
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


def _resolve_candidate_for_test(
    *,
    workspace: Path,
    environment: dict[str, str],
    keyring: FakeKeyring,
    approval_runtime_root: Path,
) -> object:
    snapshot = LaunchEnvironmentSnapshot.capture(environment)
    identity = resolve_workspace_identity(workspace)
    paths = resolve_authorized_operator_paths(
        workspace_root=workspace,
        snapshot_values=snapshot.values,
    )
    store = KeyringApprovalStore(
        keyring_backend=keyring,
        runtime_root=approval_runtime_root,
    )
    return resolve_launch_candidate(
        snapshot=snapshot,
        workspace_identity=identity,
        operator_paths=paths,
        hmac_key=store.hmac_key,
        credential_keyring_backend=keyring,
    )


def _patch_authorize_capture_after_real_authorization(
    monkeypatch: pytest.MonkeyPatch,
    *,
    workspace: Path,
    mutate: Callable[[Path], None],
) -> None:
    real_authorize_capture = capture_tool.authorize_capture

    def authorize_then_mutate(**kwargs: object) -> capture_tool.CaptureLaunch:
        capture = real_authorize_capture(**kwargs)
        mutate(workspace / ".optimus")
        return capture

    monkeypatch.setattr(capture_tool, "authorize_capture", authorize_then_mutate)


def test_nested_agent_snapshot_uses_clean_predefault_environment(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    keyring = _keyring_with_credentials(
        shared_secret="nested-snapshot-shared-secret",
        provider_api_key="nested-snapshot-provider-key",
    )
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _system_environment()
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
        launch_session_id="sess_clean_nested_snapshot",
    )

    acpx_client_environ = getattr(capture, "acpx_client_environ", None)
    assert acpx_client_environ is not None, "missing ACPX client environment role"
    clean_nested = _resolve_candidate_for_test(
        workspace=workspace,
        environment=dict(acpx_client_environ),
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    postdefault_nested = _resolve_candidate_for_test(
        workspace=workspace,
        environment={**acpx_client_environ, **capture.agent_environ},
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )

    outer_digest = capture.authorized.candidate.security_snapshot_digest
    assert postdefault_nested.security_snapshot_digest != outer_digest
    assert clean_nested.security_snapshot_digest == outer_digest


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
    capture = authorize_capture(
        workspace=workspace,
        environment=environment,
        keyring_backend=keyring,
        approval_runtime_root=approval_runtime_root,
        launch_session_id="sess_audit_failure",
    )

    runtime_root = workspace / ".optimus"
    assert runtime_root.is_dir()
    runtime_root.rmdir()
    runtime_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        append_authorized_audit(capture)

    assert runtime_root.is_file()
    assert runtime_root.read_text(encoding="utf-8") == "not a directory"


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

    def replace_runtime_root_with_file(runtime_root: Path) -> None:
        runtime_root.rmdir()
        runtime_root.write_text("not a directory", encoding="utf-8")

    _patch_authorize_capture_after_real_authorization(
        monkeypatch,
        workspace=workspace,
        mutate=replace_runtime_root_with_file,
    )

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

    assert (workspace / ".optimus").is_file()


def test_capture_acpx_missing_approved_runtime_root_never_spawns_or_recreates_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    runtime_root = workspace / ".optimus"

    def remove_runtime_root(runtime_root: Path) -> None:
        runtime_root.rmdir()

    _patch_authorize_capture_after_real_authorization(
        monkeypatch,
        workspace=workspace,
        mutate=remove_runtime_root,
    )

    real_popen = capture_tool.subprocess.Popen
    expected_command = [sys.executable, "-c", "raise SystemExit(0)"]

    def fail_only_capture_spawn(command: list[str], *args: object, **kwargs: object) -> object:
        if command == expected_command:
            pytest.fail("missing runtime root must block child spawn")
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(capture_tool.subprocess, "Popen", fail_only_capture_spawn)

    with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
        capture_acpx(
            workspace=workspace,
            environment=environment,
            keyring_backend=keyring,
            approval_runtime_root=approval_runtime_root,
            launch_session_id="sess_missing_root",
            command=expected_command,
        )

    assert not runtime_root.exists()


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


def test_spawn_uses_acpx_client_environment_not_effective_agent_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        launch_session_id="sess_acpx_client_boundary",
    )
    audited = append_authorized_audit(capture)

    observed_env: dict[str, str] = {}
    real_popen = subprocess.Popen

    def spy_popen(command: list[str], *args: object, **kwargs: object) -> subprocess.Popen[str]:
        if "env" in kwargs:
            observed_env.update(kwargs["env"])
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(capture_tool.subprocess, "Popen", spy_popen)

    process = spawn_authorized_capture(
        audited,
        command=[sys.executable, "-c", "raise SystemExit(0)"],
    )
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    assert stdout == ""
    assert observed_env == _system_environment()
    assert not any(name.startswith("OPTIMUS_") for name in observed_env)


def test_capture_tool_does_not_import_or_instantiate_project_acp_client() -> None:
    """The evidence tool delegates ACP driving to acpx and only parses its output."""
    tree = ast.parse(Path(capture_tool.__file__).read_text(encoding="utf-8"))
    forbidden_symbol = "NdjsonSubprocessSession"
    forbidden_module = "ndjson_subprocess_session"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert forbidden_module not in alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert forbidden_module not in module
            for alias in node.names:
                assert alias.name != forbidden_symbol
                assert forbidden_module not in alias.name
        elif isinstance(node, ast.Call):
            function = node.func
            assert not (
                isinstance(function, ast.Name) and function.id == forbidden_symbol
            )
            assert not (
                isinstance(function, ast.Attribute) and function.attr == forbidden_symbol
            )


def test_spawn_authorized_capture_uses_devnull_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real spawn path cannot write ACP requests to the supplied child."""
    captured: dict[str, object] = {}
    real_popen = subprocess.Popen

    def spy_popen(
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.Popen[str]:
        captured.update(kwargs)
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(capture_tool.subprocess, "Popen", spy_popen)
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
        launch_session_id="sess_stdin_devnull",
    )
    audited = append_authorized_audit(capture)

    process = spawn_authorized_capture(
        audited,
        command=[sys.executable, "-c", "pass"],
    )
    process.communicate(timeout=10)

    assert process.returncode == 0
    assert captured["stdin"] is subprocess.DEVNULL


def test_build_capture_command_places_supplied_acpx_path_first() -> None:
    command = _build_capture_command(
        acpx="/fake/bin/acpx",
        workspace=Path("C:/tmp/fake-workspace"),
        agent_invocation=(
            "optimus-agent --workspace-root C:/tmp/fake-workspace "
            "--launch-session-id sess_x --debug-trace"
        ),
        drive_session=True,
    )

    assert command[0] == "/fake/bin/acpx"
    assert command[-2:] == ["exec", SESSION_TASK]


def test_main_default_path_never_resolves_optimus_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_keyring(monkeypatch, FakeKeyring())
    queried_names: list[str] = []

    def which_spy(name: str) -> str | None:
        queried_names.append(name)
        return "acpx" if name == "acpx" else None

    monkeypatch.setattr(capture_tool.shutil, "which", which_spy)
    monkeypatch.setattr(capture_tool, "authorize_capture", lambda **_kwargs: object())
    monkeypatch.setattr(capture_tool, "append_authorized_audit", lambda _capture: object())
    monkeypatch.setattr(
        capture_tool,
        "_capture_to_disk",
        lambda *_args, **_kwargs: CaptureResult(exit_code=0, rule_counts={}),
    )
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(
        capture_tool,
        "_joined_scan",
        lambda *_args, **_kwargs: {
            "hit": False,
            "rules_fired": [],
            "scanned_artifacts": [],
        },
    )
    monkeypatch.setattr(
        capture_tool,
        "_write_evidence_manifest",
        lambda *_args, **_kwargs: None,
    )

    exit_code = main(
        [
            "capture",
            "--workspace",
            "workspace",
            "--output-dir",
            "output",
            "--mode",
            "ordinary",
        ]
    )

    assert exit_code == 0
    assert "acpx" in queried_names
    assert "optimus-agent" not in queried_names


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


def test_stream_sanitized_preserves_crlf_without_doubling_carriage_returns(
    tmp_path: Path,
) -> None:
    source_text = '{"record":1}\r\n{"record":2}\r\n'
    destination = tmp_path / "snapshot.ndjson"

    _stream_sanitized(io.StringIO(source_text), destination, known_secrets=())

    assert destination.read_bytes() == source_text.encode("utf-8")
    assert [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()] == [
        {"record": 1},
        {"record": 2},
    ]


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
    _patch_keyring(monkeypatch, FakeKeyring())

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


def test_capability_gap_default_capture_remains_version_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default ``acpx --version`` path never masquerades as a real session."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=tmp_path / "approval-runtime",
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(
        capture_tool.shutil,
        "which",
        lambda name: sys.executable if name == "acpx" else None,
    )

    output_dir = tmp_path / "output"
    assert main(
        [
            "capture",
            "--workspace",
            str(workspace),
            "--output-dir",
            str(output_dir),
            "--mode",
            "ordinary",
        ]
    ) == 0

    manifest = json.loads((output_dir / "sanitizer-manifest.json").read_text(encoding="utf-8"))
    assert "stop_reason" not in manifest
    assert "tool_names" not in manifest
    assert "tool_call_count" not in manifest
    assert not (output_dir / "external-session-evidence.json").exists()


def _observed_session_transcript() -> str:
    """Content-free synthetic JSON-RPC shape observed in Task 1 Step 5."""
    records = (
        {"jsonrpc": "2.0", "id": 1, "result": {"sessionId": "session_unit"}},
        {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": {}},
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"update": {"sessionUpdate": "tool_call", "title": "file_reader"}},
        },
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {"update": {"sessionUpdate": "tool_call", "title": "write_file"}},
        },
        {"jsonrpc": "2.0", "id": 2, "result": {"stopReason": "end_turn"}},
    )
    return "\n".join(json.dumps(record) for record in records)


def test_parse_session_result_extracts_the_observed_run_identity_and_tool_evidence() -> None:
    """Task 4 RED: only actual ACP JSON-RPC fields become session evidence."""
    parser = getattr(capture_tool, "_parse_session_result", None)
    assert parser is not None, "missing capability: Task 4 session-result parser"

    result = parser(_observed_session_transcript())

    assert result.session_id == "session_unit"
    assert result.prompt_request_id == 2
    assert result.run_id == "session_unit:2"
    assert result.stop_reason == "end_turn"
    assert result.tool_names == ("file_reader", "write_file")
    assert result.tool_call_count == 2
    assert not hasattr(result, "total_cost_usd"), "ACP transcript must not invent a cost field"


def test_external_session_evidence_snapshot_collector_reads_the_run_bound_redis_plan_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 4 RED: Redis cost is one sanitized, run-bound external snapshot."""
    collector = getattr(capture_tool, "_collect_external_session_evidence", None)
    assert collector is not None, "missing capability: unified external-session collector"

    class FakeStateStore:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def latest_plan_for_run(self, *, run_id: str) -> SimpleNamespace:
            self.calls.append(run_id)
            return SimpleNamespace(
                run_id=run_id,
                cost_usd=Decimal("0.003538"),
                plan_text="never persist this task text",
                gateway_request_id="never persist this gateway identifier",
                provider="never persist this provider",
            )

    store = FakeStateStore()
    urls: list[str] = []

    class FakeRedisAgentStateStore:
        @classmethod
        def from_url(cls, url: str) -> FakeStateStore:
            urls.append(url)
            return store

    monkeypatch.setattr(capture_tool, "RedisAgentStateStore", FakeRedisAgentStateStore, raising=False)
    monkeypatch.setattr(capture_tool.os, "environ", {"OPTIMUS_REDIS_URL": "redis://ambient-must-not-be-read"})

    evidence = collector(
        capture=SimpleNamespace(agent_environ={"OPTIMUS_REDIS_URL": "redis://authorized/0"}),
        session_result=SimpleNamespace(run_id="session_unit:2"),
        output_dir=tmp_path,
        known_secrets=("never persist",),
    )

    assert urls == ["redis://authorized/0"]
    assert store.calls == ["session_unit:2"]
    assert str(evidence.total_cost_usd) == "0.003538"
    snapshot_text = (tmp_path / "external-session-evidence.json").read_text(encoding="utf-8")
    assert json.loads(snapshot_text) == {"run_id": "session_unit:2", "total_cost_usd": "0.003538"}
    assert "plan_text" not in snapshot_text
    assert "gateway_request_id" not in snapshot_text
    assert "provider" not in snapshot_text


@pytest.mark.parametrize(
    "record",
    (
        None,
        SimpleNamespace(run_id="different:2", cost_usd=Decimal("0.003538")),
        SimpleNamespace(run_id="session_unit:2", cost_usd=Decimal("0")),
    ),
)
def test_external_session_evidence_snapshot_collector_fails_closed_on_absent_mismatched_or_nonpositive_cost(
    record: SimpleNamespace | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No manifest-promotable external evidence exists without a valid run-bound cost."""
    collector = getattr(capture_tool, "_collect_external_session_evidence", None)
    assert collector is not None, "missing capability: unified external-session collector"

    class FakeStateStore:
        def latest_plan_for_run(self, *, run_id: str) -> SimpleNamespace | None:
            assert run_id == "session_unit:2"
            return record

    class FakeRedisAgentStateStore:
        @classmethod
        def from_url(cls, _url: str) -> FakeStateStore:
            return FakeStateStore()

    monkeypatch.setattr(capture_tool, "RedisAgentStateStore", FakeRedisAgentStateStore, raising=False)

    with pytest.raises(ValueError):
        collector(
            capture=SimpleNamespace(agent_environ={"OPTIMUS_REDIS_URL": "redis://authorized/0"}),
            session_result=SimpleNamespace(run_id="session_unit:2"),
            output_dir=tmp_path,
            known_secrets=(),
        )

    assert not (tmp_path / "external-session-evidence.json").exists()


def test_drive_session_collects_external_evidence_before_promotion_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A driven session snapshots only post-offset logs before scan and promotion."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_root = workspace / ".optimus"
    runtime_root.mkdir()
    audit_path = runtime_root / "launch-audit.ndjson"
    debug_path = runtime_root / "debug-acp.ndjson"
    audit_path.write_text(json.dumps({"launch_session_id": "old"}) + "\n", encoding="utf-8")
    debug_path.write_text(json.dumps({"sessionId": "old"}) + "\n", encoding="utf-8")
    expected_audit_offset = audit_path.stat().st_size
    expected_debug_offset = debug_path.stat().st_size
    output_dir = tmp_path / "output"
    capture = SimpleNamespace(
        agent_environ={"OPTIMUS_REDIS_URL": "redis://authorized/0"},
        authorized=SimpleNamespace(
            launch_session_id="sess_current",
            candidate=SimpleNamespace(operator_paths=SimpleNamespace(runtime_root=runtime_root)),
        ),
    )
    session_result = SimpleNamespace(run_id="session_unit:2")
    external_evidence = SimpleNamespace(run_id="session_unit:2", total_cost_usd=Decimal("0.003538"))
    log_evidence = SimpleNamespace(
        child_key_names=("OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"),
        elevated_comparison_record_present=False,
    )
    events: list[str] = []

    monkeypatch.setattr(capture_tool.shutil, "which", lambda name: name)
    monkeypatch.setattr(capture_tool, "authorize_capture", lambda **_kwargs: capture)

    def append_audit(_capture: object) -> SimpleNamespace:
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "launch_session_id": "sess_current",
                        "child_propagation_decisions": {
                            "agent_child": ["OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"],
                            "acpx_client": [],
                        },
                    }
                )
                + "\n"
            )
        events.append("audit")
        return SimpleNamespace(capture=capture)

    monkeypatch.setattr(capture_tool, "append_authorized_audit", append_audit)

    def capture_to_disk(
        _audited: object, *, command: list[str], output_dir: Path, drive_session: bool
    ) -> CaptureResult:
        assert drive_session is True
        assert command[-2:] == ["exec", capture_tool.SESSION_TASK]
        with audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"launch_session_id": "sess_current"}) + "\n")
        with debug_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"sessionId": "debug_current", "location": "other"}) + "\n")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "transcript.stdout").write_text(_observed_session_transcript(), encoding="utf-8")
        events.append("capture")
        return CaptureResult(exit_code=0, rule_counts={})

    def parse_session(transcript: str) -> SimpleNamespace:
        assert transcript == _observed_session_transcript()
        events.append("parse")
        return session_result

    def collect_external(
        *, capture: object, session_result: object, output_dir: Path, known_secrets: tuple[str, ...]
    ) -> SimpleNamespace:
        assert capture is not None
        assert session_result is not None
        assert known_secrets == ()
        events.append("collect")
        (output_dir / "external-session-evidence.json").write_text(
            '{"run_id":"session_unit:2","total_cost_usd":"0.003538"}', encoding="utf-8"
        )
        return external_evidence

    def snapshot_logs(
        *,
        workspace: Path,
        output_dir: Path,
        audit_offset: int,
        debug_offset: int,
        launch_session_id: str,
        session_mode: str,
        known_secrets: tuple[str, ...],
    ) -> SimpleNamespace:
        assert workspace == tmp_path / "workspace"
        assert audit_offset == expected_audit_offset
        assert debug_offset == expected_debug_offset
        assert launch_session_id == "sess_current"
        assert session_mode == "ordinary"
        assert known_secrets == ()
        assert events == ["audit", "capture", "parse", "collect"]
        (output_dir / "audit-snapshot.ndjson").write_text(
            audit_path.read_bytes()[audit_offset:].decode("utf-8"), encoding="utf-8"
        )
        (output_dir / "debug-snapshot.ndjson").write_text(
            debug_path.read_bytes()[debug_offset:].decode("utf-8"), encoding="utf-8"
        )
        events.append("snapshot")
        return log_evidence

    def joined_scan(artifact_dir: Path, known_secrets: tuple[str, ...]) -> dict[str, object]:
        assert events == ["audit", "capture", "parse", "collect", "snapshot"]
        assert known_secrets == ()
        assert (artifact_dir / "external-session-evidence.json").is_file()
        assert (artifact_dir / "audit-snapshot.ndjson").is_file()
        assert (artifact_dir / "debug-snapshot.ndjson").is_file()
        events.append("scan")
        return {"hit": False, "rules_fired": [], "scanned_artifacts": []}

    def write_manifest(
        _output_dir: Path,
        *,
        session_mode: str,
        session_result: object,
        external_evidence: object,
        log_evidence: object,
        evidence_run_nonce: str,
        **_kwargs: object,
    ) -> None:
        assert session_mode == "ordinary"
        assert session_result is not None
        assert external_evidence is not None
        assert log_evidence is not None
        assert evidence_run_nonce == "run_0123456789abcdef01234567"
        events.append("manifest")

    monkeypatch.setattr(capture_tool, "_capture_to_disk", capture_to_disk)
    monkeypatch.setattr(capture_tool, "_parse_session_result", parse_session)
    monkeypatch.setattr(capture_tool, "_collect_external_session_evidence", collect_external)
    monkeypatch.setattr(capture_tool, "_snapshot_run_scoped_launch_logs", snapshot_logs, raising=False)
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(capture_tool, "_joined_scan", joined_scan)
    monkeypatch.setattr(
        capture_tool,
        "resolve_trusted_operator_roots",
        lambda **_kwargs: SimpleNamespace(approval_runtime_root=tmp_path / "approval-runtime"),
    )
    monkeypatch.setattr(
        capture_tool,
        "KeyringApprovalStore",
        lambda **_kwargs: SimpleNamespace(hmac_key=b"test-hmac-key-32-bytes-long!!!!"),
    )
    monkeypatch.setattr(
        capture_tool,
        "_write_evidence_manifest",
        write_manifest,
    )

    assert main([
        "capture",
        "--workspace", str(workspace),
        "--output-dir", str(output_dir),
        "--mode", "ordinary",
        "--drive-session",
        "--evidence-run-nonce", "run_0123456789abcdef01234567",
    ]) == 0
    assert events == ["audit", "capture", "parse", "collect", "snapshot", "scan", "manifest"]


def test_drive_session_quarantines_when_external_evidence_collection_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid run-bound Redis record cannot promote a driven-session manifest."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output_dir = tmp_path / "output"
    events: list[str] = []
    capture = SimpleNamespace(
        agent_environ={"OPTIMUS_REDIS_URL": "redis://authorized/0"},
        authorized=SimpleNamespace(launch_session_id="sess_failure"),
    )

    monkeypatch.setattr(capture_tool.shutil, "which", lambda name: name)
    monkeypatch.setattr(capture_tool, "authorize_capture", lambda **_kwargs: capture)
    monkeypatch.setattr(
        capture_tool,
        "append_authorized_audit",
        lambda _capture: SimpleNamespace(capture=capture),
    )
    monkeypatch.setattr(
        capture_tool,
        "_capture_to_disk",
        lambda *_args, output_dir, **_kwargs: (
            output_dir.mkdir(parents=True, exist_ok=True),
            (output_dir / "transcript.stdout").write_text(_observed_session_transcript(), encoding="utf-8"),
            CaptureResult(exit_code=0, rule_counts={}),
        )[-1],
    )
    monkeypatch.setattr(capture_tool, "_parse_session_result", lambda _text: SimpleNamespace(run_id="session_unit:2"))

    def reject_collection(**_kwargs: object) -> None:
        events.append("collect")
        raise ValueError("external session evidence cost must be positive")

    monkeypatch.setattr(capture_tool, "_collect_external_session_evidence", reject_collection)
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(capture_tool, "_joined_scan", lambda *_args: {"hit": False, "rules_fired": [], "scanned_artifacts": []})
    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(capture_tool, "_quarantine_artifacts", lambda _path: events.append("quarantine"))

    assert main([
        "capture",
        "--workspace", str(workspace),
        "--output-dir", str(output_dir),
        "--mode", "ordinary",
        "--drive-session",
        "--evidence-run-nonce", "run_0123456789abcdef01234567",
    ]) == 1
    assert events == ["collect", "quarantine"]


def _assert_manifest_extension_interface() -> None:
    required = {
        "session_mode",
        "session_result",
        "external_evidence",
        "log_evidence",
        "evidence_run_nonce",
    }
    missing = sorted(required - set(inspect.signature(_write_evidence_manifest).parameters))
    assert not missing, f"missing capability: manifest evidence inputs {missing}"


def _write_session_evidence_artifacts(output_dir: Path) -> None:
    _write_clean_artifacts(output_dir, stdout_text="safe output")
    (output_dir / "external-session-evidence.json").write_text(
        json.dumps({"run_id": "session_unit:2", "total_cost_usd": "0.003538"}),
        encoding="utf-8",
    )
    (output_dir / "audit-snapshot.ndjson").write_text(
        json.dumps({"launch_session_id": "sess_current"}) + "\n",
        encoding="utf-8",
    )
    (output_dir / "debug-snapshot.ndjson").write_text("", encoding="utf-8")


def _manifest_evidence_inputs(
    *, tool_names: tuple[str, ...], elevated_comparison_record_present: bool
) -> tuple[object, object, object]:
    session_type = getattr(capture_tool, "SessionResultEvidence", None)
    external_type = getattr(capture_tool, "ExternalSessionEvidence", None)
    assert session_type is not None, "missing capability: typed session-result evidence"
    assert external_type is not None, "missing capability: typed external-session evidence"
    session = session_type(
        session_id="session_unit",
        prompt_request_id=2,
        run_id="session_unit:2",
        stop_reason="end_turn",
        tool_names=tool_names,
        tool_call_count=len(tool_names),
    )
    external = external_type(run_id="session_unit:2", total_cost_usd=Decimal("0.003538"))
    log_evidence = SimpleNamespace(
        child_key_names=("OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"),
        elevated_comparison_record_present=elevated_comparison_record_present,
    )
    return session, external, log_evidence


def test_manifest_hmac_and_verify_cover_all_run_bound_session_evidence(tmp_path: Path) -> None:
    """Task 4 RED: all content-free session fields and snapshots are signed."""
    _assert_manifest_extension_interface()
    _write_session_evidence_artifacts(tmp_path)
    session, external, log_evidence = _manifest_evidence_inputs(
        tool_names=("file_reader", "write_file"),
        elevated_comparison_record_present=False,
    )
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"

    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": []},
        hmac_key=hmac_key,
        session_mode="ordinary",
        session_result=session,
        external_evidence=external,
        log_evidence=log_evidence,
        evidence_run_nonce="run_0123456789abcdef01234567",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["session_mode"] == "ordinary"
    assert manifest["stop_reason"] == "end_turn"
    assert manifest["tool_names"] == ["file_reader", "write_file"]
    assert manifest["tool_call_count"] == 2
    assert manifest["total_cost_usd"] == "0.003538"
    assert manifest["final_agent_state"] == "COMPLETED"
    assert manifest["child_key_names"] == ["OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"]
    assert manifest["elevated_comparison_record_present"] is False
    assert manifest["evidence_run_nonce"] == "run_0123456789abcdef01234567"
    assert "external-session-evidence.json" in manifest["artifact_sha256"]
    assert "audit-snapshot.ndjson" in manifest["artifact_sha256"]
    assert "debug-snapshot.ndjson" in manifest["artifact_sha256"]

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)
    assert _verify_evidence_manifest(manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring) == 0


def test_manifest_omits_final_agent_state_without_the_bounded_completion_proof(
    tmp_path: Path,
) -> None:
    """``end_turn`` alone must never be generalized into agent completion."""
    _assert_manifest_extension_interface()
    _write_session_evidence_artifacts(tmp_path)
    session, external, log_evidence = _manifest_evidence_inputs(
        tool_names=("file_reader",),
        elevated_comparison_record_present=False,
    )

    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": []},
        hmac_key=b"test-hmac-key-32-bytes-long!!!!",
        session_mode="ordinary",
        session_result=session,
        external_evidence=external,
        log_evidence=log_evidence,
        evidence_run_nonce="run_0123456789abcdef01234567",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stop_reason"] == "end_turn"
    assert manifest["tool_call_count"] == 1
    assert "final_agent_state" not in manifest


def test_manifest_records_elevated_comparison_presence(tmp_path: Path) -> None:
    """Exactly one run-scoped elevated comparison becomes a signed boolean."""
    _assert_manifest_extension_interface()
    _write_session_evidence_artifacts(tmp_path)
    session, external, log_evidence = _manifest_evidence_inputs(
        tool_names=("file_reader", "write_file"),
        elevated_comparison_record_present=True,
    )

    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": []},
        hmac_key=b"test-hmac-key-32-bytes-long!!!!",
        session_mode="elevated",
        session_result=session,
        external_evidence=external,
        log_evidence=log_evidence,
        evidence_run_nonce="run_0123456789abcdef01234567",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["session_mode"] == "elevated"
    assert manifest["elevated_comparison_record_present"] is True


def test_verify_rejects_tampered_evidence_run_nonce(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The new nonce field is covered by the existing whole-manifest HMAC."""
    _assert_manifest_extension_interface()
    _write_session_evidence_artifacts(tmp_path)
    session, external, log_evidence = _manifest_evidence_inputs(
        tool_names=("file_reader", "write_file"),
        elevated_comparison_record_present=False,
    )
    hmac_key = b"test-hmac-key-32-bytes-long!!!!"
    manifest_path = _write_evidence_manifest(
        tmp_path,
        rule_counts={},
        joined_scan_result={"hit": False, "rules_fired": [], "scanned_artifacts": []},
        hmac_key=hmac_key,
        session_mode="ordinary",
        session_result=session,
        external_evidence=external,
        log_evidence=log_evidence,
        evidence_run_nonce="run_0123456789abcdef01234567",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence_run_nonce"] = "run_89abcdef0123456789abcdef"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    fake_keyring = FakeKeyring()
    _store_hmac_key(fake_keyring, hmac_key)
    assert _verify_evidence_manifest(
        manifest_path, artifact_dir=tmp_path, keyring_backend=fake_keyring
    ) == 1
    assert "EVIDENCE_HMAC_MISMATCH" in capsys.readouterr().err
    assert (tmp_path / "quarantine" / "sanitizer-manifest.json").is_file()


def _valid_run_audit_records(
    launch_session_id: str = "sess_current",
) -> list[dict[str, object]]:
    return [
        {
            "launch_session_id": launch_session_id,
            "child_propagation_decisions": {
                "agent_child": ["OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"],
                "acpx_client": [],
            },
        },
        {"launch_session_id": launch_session_id},
    ]


def _comparison_record(tags: list[object], *, session_id: str = "debug_current") -> dict[str, object]:
    return {
        "sessionId": session_id,
        "location": "launch_authorization_comparison",
        "data": {"correlation_tags": tags},
    }


def _write_run_logs(
    runtime_root: Path,
    *,
    audit_records: list[dict[str, object]],
    debug_records: list[dict[str, object]],
) -> None:
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "launch-audit.ndjson").write_text(
        "".join(json.dumps(record) + "\n" for record in audit_records), encoding="utf-8"
    )
    (runtime_root / "debug-acp.ndjson").write_text(
        "".join(json.dumps(record) + "\n" for record in debug_records), encoding="utf-8"
    )


def test_run_scoped_log_snapshot_uses_offsets_and_accepts_elevated_empty_tags(tmp_path: Path) -> None:
    """Task 4 RED: only this run's suffix becomes immutable audit/debug evidence."""
    snapshotter = getattr(capture_tool, "_snapshot_run_scoped_launch_logs", None)
    assert snapshotter is not None, "missing capability: run-scoped audit/debug snapshotter"

    runtime_root = tmp_path / ".optimus"
    runtime_root.mkdir()
    audit_path = runtime_root / "launch-audit.ndjson"
    debug_path = runtime_root / "debug-acp.ndjson"
    audit_path.write_text(json.dumps({"launch_session_id": "old"}) + "\n", encoding="utf-8")
    debug_path.write_text(json.dumps({"sessionId": "old"}) + "\n", encoding="utf-8")
    audit_offset = audit_path.stat().st_size
    debug_offset = debug_path.stat().st_size
    audit_path.write_text(
        audit_path.read_text(encoding="utf-8")
        + "".join(json.dumps(record) + "\n" for record in _valid_run_audit_records()),
        encoding="utf-8",
    )
    debug_path.write_text(
        debug_path.read_text(encoding="utf-8")
        + json.dumps(_comparison_record([]))
        + "\n",
        encoding="utf-8",
    )

    evidence = snapshotter(
        workspace=tmp_path,
        output_dir=tmp_path / "output",
        audit_offset=audit_offset,
        debug_offset=debug_offset,
        launch_session_id="sess_current",
        session_mode="elevated",
        known_secrets=(),
    )

    assert evidence.child_key_names == ("OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL")
    assert evidence.elevated_comparison_record_present is True
    assert "old" not in (tmp_path / "output" / "audit-snapshot.ndjson").read_text(encoding="utf-8")
    assert "old" not in (tmp_path / "output" / "debug-snapshot.ndjson").read_text(encoding="utf-8")


def test_run_scoped_log_snapshot_accepts_ordinary_zero_comparison_records(tmp_path: Path) -> None:
    """Ordinary mode is proven by zero comparison records in this run's suffix."""
    snapshotter = getattr(capture_tool, "_snapshot_run_scoped_launch_logs", None)
    assert snapshotter is not None, "missing capability: run-scoped audit/debug snapshotter"
    runtime_root = tmp_path / ".optimus"
    _write_run_logs(
        runtime_root,
        audit_records=_valid_run_audit_records(),
        debug_records=[{"sessionId": "debug_current", "location": "other"}],
    )

    evidence = snapshotter(
        workspace=tmp_path,
        output_dir=tmp_path / "output",
        audit_offset=0,
        debug_offset=0,
        launch_session_id="sess_current",
        session_mode="ordinary",
        known_secrets=(),
    )

    assert evidence.elevated_comparison_record_present is False
    assert (tmp_path / "output" / "debug-snapshot.ndjson").is_file()


def test_run_scoped_log_snapshot_accepts_elevated_allowlisted_nonempty_tags(
    tmp_path: Path,
) -> None:
    """A real-shaped, allowlisted name plus a 128-bit hex tag is valid evidence."""
    snapshotter = getattr(capture_tool, "_snapshot_run_scoped_launch_logs", None)
    assert snapshotter is not None, "missing capability: run-scoped audit/debug snapshotter"
    runtime_root = tmp_path / ".optimus"
    allowed_tag = {
        "field_name": "OPTIMUS_API_KEY",
        "tag": "0123456789abcdef0123456789abcdef",
    }
    _write_run_logs(
        runtime_root,
        audit_records=_valid_run_audit_records(),
        debug_records=[_comparison_record([allowed_tag])],
    )

    evidence = snapshotter(
        workspace=tmp_path,
        output_dir=tmp_path / "output",
        audit_offset=0,
        debug_offset=0,
        launch_session_id="sess_current",
        session_mode="elevated",
        known_secrets=(),
    )

    assert evidence.elevated_comparison_record_present is True
    snapshot = (tmp_path / "output" / "debug-snapshot.ndjson").read_text(encoding="utf-8")
    assert allowed_tag["tag"] in snapshot


@pytest.mark.parametrize(
    "audit_records,debug_records,session_mode",
    (
        (_valid_run_audit_records("foreign"), [], "ordinary"),
        (_valid_run_audit_records(), [{"sessionId": "one"}, {"sessionId": "two"}], "ordinary"),
        (_valid_run_audit_records(), [_comparison_record([], session_id="one")], "ordinary"),
        (_valid_run_audit_records(), [_comparison_record([42], session_id="one")], "elevated"),
        (
            _valid_run_audit_records(),
            [
                _comparison_record(
                    [
                        {
                            "field_name": "UNRELATED_SENTINEL",
                            "tag": "0123456789abcdef0123456789abcdef",
                        }
                    ]
                )
            ],
            "elevated",
        ),
        (
            _valid_run_audit_records(),
            [_comparison_record([{"field_name": "OPTIMUS_API_KEY", "tag": "not-hex"}])],
            "elevated",
        ),
        (
            [
                {
                    "launch_session_id": "sess_current",
                    "child_propagation_decisions": {
                        "agent_child": ["OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"],
                        "acpx_client": ["OPTIMUS_API_KEY"],
                    },
                },
                {"launch_session_id": "sess_current"},
            ],
            [],
            "ordinary",
        ),
        (
            [
                {
                    "launch_session_id": "sess_current",
                    "child_propagation_decisions": {
                        "agent_child": ["OPTIMUS_API_KEY", "OPTIMUS_REDIS_URL"],
                    },
                },
                {"launch_session_id": "sess_current"},
            ],
            [],
            "ordinary",
        ),
    ),
)
def test_run_scoped_log_snapshot_fails_closed_on_foreign_or_malformed_suffix(
    audit_records: list[dict[str, object]],
    debug_records: list[dict[str, object]],
    session_mode: str,
    tmp_path: Path,
) -> None:
    """Foreign writers, wrong mode, and malformed tags cannot become evidence."""
    snapshotter = getattr(capture_tool, "_snapshot_run_scoped_launch_logs", None)
    assert snapshotter is not None, "missing capability: run-scoped audit/debug snapshotter"

    runtime_root = tmp_path / ".optimus"
    _write_run_logs(
        runtime_root,
        audit_records=audit_records,
        debug_records=debug_records,
    )

    with pytest.raises(ValueError):
        snapshotter(
            workspace=tmp_path,
            output_dir=tmp_path / "output",
            audit_offset=0,
            debug_offset=0,
            launch_session_id="sess_current",
            session_mode=session_mode,
            known_secrets=(),
        )

    assert not (tmp_path / "output" / "audit-snapshot.ndjson").exists()
    assert not (tmp_path / "output" / "debug-snapshot.ndjson").exists()


def test_nonzero_capture_result_blocks_manifest_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed child may not produce an apparently verified manifest."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=tmp_path / "approval-runtime",
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    real_which = capture_tool.shutil.which

    def which(name: str) -> str | None:
        if name in {"acpx", "optimus-agent"}:
            return sys.executable
        return real_which(name)

    monkeypatch.setattr(capture_tool.shutil, "which", which)
    monkeypatch.setattr(capture_tool, "_capture_to_disk", lambda *_args, **_kwargs: CaptureResult(17, {}))

    def manifest_must_not_be_written(*_args: object, **_kwargs: object) -> None:
        pytest.fail("nonzero capture result must block manifest promotion")

    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", manifest_must_not_be_written)

    assert main([
        "capture",
        "--workspace", str(workspace),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "ordinary",
    ]) == 17


@pytest.mark.skipif(sys.platform != "win32", reason="Task 3's exercised tree-kill path is Windows taskkill")
def test_capture_timeout_terminates_parent_and_descendant_in_an_isolated_probe(tmp_path: Path) -> None:
    """Task 3 Step 4 RED: bounded capture must not orphan an acpx-style tree."""
    pids_path = tmp_path / "sleeping-pids.json"
    probe_path = tmp_path / "capture-probe.py"
    target_path = tmp_path / "sleeping-parent.py"
    repo_root = Path(__file__).resolve().parents[3]
    target_path.write_text(
        textwrap.dedent(
            f"""
            import json
            import os
            import subprocess
            import sys
            import time
            from pathlib import Path

            descendant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            Path({str(pids_path)!r}).write_text(
                json.dumps({{"parent": os.getpid(), "descendant": descendant.pid}}), encoding="utf-8"
            )
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    probe_path.write_text(
        textwrap.dedent(
            f"""
            import json
            import subprocess
            import sys
            from pathlib import Path

            import tools.run_plan996_acpx_security_evidence as tool

            pids_path = Path({str(pids_path)!r})
            target = subprocess.Popen([sys.executable, {str(target_path)!r}], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            class Audited:
                capture = object()

            tool.spawn_authorized_capture = lambda *_args, **_kwargs: target
            tool._known_secrets = lambda _capture: ()
            result = tool._capture_to_disk(Audited(), command=['acpx'], output_dir=Path({str(tmp_path / 'artifacts')!r}), drive_session=True, wait_timeout_seconds=1.0)
            raise SystemExit(0 if result.exit_code != 0 else 1)
            """
        ),
        encoding="utf-8",
    )
    probe = subprocess.Popen(
        [sys.executable, str(probe_path)],
        cwd=repo_root,
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    pids: dict[str, int] = {}
    try:
        try:
                assert probe.wait(timeout=4.5) == 0
        except subprocess.TimeoutExpired:
            pytest.fail("capture timeout never reached because reader joins blocked first")
        assert pids_path.is_file(), "the sleeping parent must record its descendant PID"
        pids = json.loads(pids_path.read_text(encoding="utf-8"))
    finally:
        for pid in (probe.pid, *pids.values()):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)

    for pid in pids.values():
        with pytest.raises(OSError):
            os.kill(pid, 0)


def test_agent_invocation_session_fixture_constants_are_pinned() -> None:
    """Task 3's fixed session task stays concrete and single-file scoped."""
    assert capture_tool._SESSION_FIXTURE_FILENAME == "plan998_fixture.py"
    assert capture_tool._SESSION_FIXTURE_PRISTINE_CONTENT == "def status():\n    return 'pending'\n"
    assert capture_tool.SESSION_TASK == (
        "Add a module docstring to `plan998_fixture.py` describing its function. "
        "Modify only `plan998_fixture.py`; do not create any other files or tests."
    )


def test_build_agent_invocation_contains_only_pinned_inner_agent_arguments(tmp_path: Path) -> None:
    """The outer acpx permission flag must never leak into ``--agent``."""
    invocation = capture_tool._build_agent_invocation(
        optimus_agent="optimus-agent",
        workspace=tmp_path / "workspace",
        launch_session_id="sess_pinned",
        diagnostic_grant_id="grant_pinned",
    )

    assert invocation == (
        f"optimus-agent --workspace-root {(tmp_path / 'workspace').as_posix()} "
        "--launch-session-id sess_pinned --debug-trace "
        "--diagnostic-grant-id grant_pinned"
    )
    assert "--approve-all" not in invocation


def test_build_agent_invocation_serializes_windows_paths_for_acpx_raw_command_parser() -> None:
    """Raw ``--agent`` text must not leave backslashes for ACPX to consume."""
    invocation = capture_tool._build_agent_invocation(
        optimus_agent=r"D:\Projects\Optimus\.venv\Scripts\optimus-agent.EXE",
        workspace=PureWindowsPath(r"C:\tmp\approved-workspace"),
        launch_session_id="sess_pinned",
        diagnostic_grant_id=None,
    )

    assert invocation == (
        "D:/Projects/Optimus/.venv/Scripts/optimus-agent.EXE "
        "--workspace-root C:/tmp/approved-workspace "
        "--launch-session-id sess_pinned --debug-trace"
    )


def test_build_capture_command_keeps_default_or_builds_outer_approved_exec_argv(tmp_path: Path) -> None:
    """Default capture is unchanged; a driven session gets the outer approval flag."""
    assert capture_tool._build_capture_command(
        acpx="acpx",
        workspace=tmp_path / "workspace",
        agent_invocation=None,
        drive_session=False,
    ) == ["acpx", "--version"]

    assert capture_tool._build_capture_command(
        acpx="acpx",
        workspace=tmp_path / "workspace",
        agent_invocation="optimus-agent --workspace-root workspace",
        drive_session=True,
    ) == [
        "acpx",
        "--format",
        "json",
        "--approve-all",
        "--cwd",
        str(tmp_path / "workspace"),
        "--agent",
        "optimus-agent --workspace-root workspace",
        "exec",
        capture_tool.SESSION_TASK,
    ]


def test_default_version_spawn_uses_system_only_client_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unchanged smoke command receives only sanctioned system bootstrap keys."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    keyring = FakeKeyring()
    environment = _environment(config_root)
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=tmp_path / "approval-runtime",
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.os, "environ", environment)

    def which(name: str) -> str | None:
        if name == "optimus-agent":
            pytest.fail("default capture must not resolve optimus-agent")
        return sys.executable if name == "acpx" else None

    monkeypatch.setattr(capture_tool.shutil, "which", which)

    real_popen = subprocess.Popen
    popen_calls: list[tuple[list[str], dict[str, object]]] = []

    def spy_popen(command: list[str], *args: object, **kwargs: object) -> subprocess.Popen[str]:
        popen_calls.append((list(command), dict(kwargs)))
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(capture_tool.subprocess, "Popen", spy_popen)

    assert main([
        "capture",
        "--workspace", str(workspace),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "ordinary",
    ]) == 0
    assert len(popen_calls) == 1
    command, kwargs = popen_calls[0]
    assert command == [sys.executable, "--version"]
    assert set(kwargs["env"]) == set(_system_environment())
    assert kwargs["env"] == _system_environment()
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert "creationflags" not in kwargs
    assert "start_new_session" not in kwargs
    assert capture_tool._CAPTURE_WAIT_TIMEOUT_SECONDS == 30.0


def test_agent_invocation_drive_session_fails_closed_when_optimus_agent_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The driven mode needs a resolvable inner-agent executable."""
    monkeypatch.setattr(
        capture_tool.shutil,
        "which",
        lambda name: "acpx" if name == "acpx" else None,
    )

    assert main([
        "capture",
        "--workspace", str(tmp_path / "workspace"),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "ordinary",
        "--drive-session",
    ]) == 2
    assert "optimus-agent is required" in capsys.readouterr().err


@pytest.mark.parametrize(
    "nonce",
    ("", "bad nonce", "run_" + "a" * 257, "sk-secret-shaped-nonce"),
)
def test_evidence_run_nonce_is_rejected_before_authorize(
    nonce: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed nonces cannot reach the launch gate or consume a grant."""
    monkeypatch.setattr(capture_tool, "authorize_capture", pytest.fail)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: "acpx")

    assert main([
        "capture",
        "--workspace", str(tmp_path / "workspace"),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "ordinary",
        "--evidence-run-nonce", nonce,
    ]) == 2
    assert "evidence-run-nonce" in capsys.readouterr().err


def test_agent_invocation_elevated_drive_session_passes_grant_only_to_inner_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The outer gate stays ordinary; the inner invocation receives the grant."""
    calls: list[dict[str, object]] = []
    _patch_keyring(monkeypatch, FakeKeyring())

    def spy_authorize(**kwargs: object) -> object:
        calls.append(dict(kwargs))
        return SimpleNamespace(
            authorized=SimpleNamespace(launch_session_id=kwargs["launch_session_id"])
        )

    def fake_capture(*_args: object, output_dir: Path, **_kwargs: object) -> CaptureResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "transcript.stdout").write_text("{}\n", encoding="utf-8")
        return CaptureResult(0, {})

    monkeypatch.setattr(capture_tool, "authorize_capture", spy_authorize)
    monkeypatch.setattr(capture_tool, "append_authorized_audit", lambda _capture: object())
    monkeypatch.setattr(capture_tool, "_capture_to_disk", fake_capture)
    monkeypatch.setattr(capture_tool, "_parse_session_result", lambda _transcript: object())
    monkeypatch.setattr(capture_tool, "_collect_external_session_evidence", lambda **_kwargs: object())
    monkeypatch.setattr(
        capture_tool,
        "_snapshot_run_scoped_launch_logs",
        lambda **_kwargs: SimpleNamespace(
            child_key_names=(),
            elevated_comparison_record_present=True,
            rule_counts={},
        ),
    )
    monkeypatch.setattr(capture_tool, "_known_secrets", lambda _capture: ())
    monkeypatch.setattr(capture_tool, "_joined_scan", lambda *_a, **_k: {"hit": False, "rules_fired": [], "scanned_artifacts": []})
    monkeypatch.setattr(capture_tool, "_write_evidence_manifest", lambda *_a, **_k: None)
    monkeypatch.setattr(
        capture_tool.shutil,
        "which",
        lambda name: name if name in {"acpx", "optimus-agent"} else None,
    )

    assert main([
        "capture",
        "--workspace", str(tmp_path / "workspace"),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "elevated",
        "--diagnostic-grant-id", "grant_inner_only",
        "--drive-session",
        "--evidence-run-nonce", "run_0123456789abcdef01234567",
    ]) == 0
    assert calls == [{
        "workspace": tmp_path / "workspace",
        "environment": capture_tool.os.environ,
        "launch_approval_id": None,
        "launch_session_id": calls[0]["launch_session_id"],
        "diagnostic_grant_id": None,
        "drive_session": True,
    }]


def test_capture_launch_builds_system_only_acpx_client_environment(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    keyring = _keyring_with_credentials(
        shared_secret="client-role-shared-secret",
        provider_api_key="client-role-provider-key",
    )
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _system_environment()
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
        launch_session_id="sess_client_role",
    )
    expected_agent_names = {
        "OPTIMUS_AGENT_MODEL",
        "OPTIMUS_API_KEY",
        "OPTIMUS_GATEWAY_URL",
        "OPTIMUS_PRODUCTION_MODE",
        "OPTIMUS_REDIS_URL",
    }
    assert set(capture.agent_environ) == expected_agent_names
    acpx_client_environ = getattr(capture, "acpx_client_environ", None)
    assert acpx_client_environ is not None, "missing ACPX client environment role"
    assert dict(acpx_client_environ) == _system_environment()
    assert not any(name.startswith("OPTIMUS_") for name in acpx_client_environ)
    assert "OPTIMUS_API_KEY" not in acpx_client_environ


def test_launch_audit_adds_acpx_client_role_without_changing_agent_child_manifest(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    keyring = _keyring_with_credentials(
        shared_secret="audit-role-shared-secret",
        provider_api_key="audit-role-provider-key",
    )
    approval_runtime_root = tmp_path / "approval-runtime"
    environment = _system_environment()
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
        launch_session_id="sess_audit_client_role",
    )

    append_authorized_audit(capture)

    audit_path = workspace / ".optimus" / "launch-audit.ndjson"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 1
    decisions = records[0]["child_propagation_decisions"]
    assert decisions["agent_child"] == [
        "OPTIMUS_AGENT_MODEL",
        "OPTIMUS_API_KEY",
        "OPTIMUS_GATEWAY_URL",
        "OPTIMUS_PRODUCTION_MODE",
        "OPTIMUS_REDIS_URL",
    ]
    assert decisions["gateway_child"] == sorted(capture.authorized.candidate.gateway_environ)
    assert decisions.get("acpx_client") == []


@pytest.mark.parametrize(
    "setting_name,setting_kind",
    (
        ("OPTIMUS_API_KEY", "secret"),
        ("OPTIMUS_CONFIG_ROOT", "parent_only_security"),
        ("OPENAI_API_KEY", "provider_secret"),
    ),
)
def test_drive_session_rejects_inherited_classified_launch_settings_before_audit_or_spawn(
    setting_name: str,
    setting_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = tmp_path / "config"
    config_root.mkdir()
    dirty_value = (
        str(config_root)
        if setting_name == "OPTIMUS_CONFIG_ROOT"
        else f"sentinel-{setting_kind}-value"
    )
    environment = {**_system_environment(), setting_name: dirty_value}
    keyring = _keyring_with_credentials(
        shared_secret="dirty-boundary-shared-secret",
        provider_api_key="dirty-boundary-provider-key",
    )
    approval_runtime_root = tmp_path / "approval-runtime"
    _write_durable_approval(
        workspace=workspace,
        environment=environment,
        keyring=keyring,
        approval_runtime_root=approval_runtime_root,
    )
    _patch_keyring(monkeypatch, keyring)
    monkeypatch.setattr(capture_tool.os, "environ", environment)
    monkeypatch.setattr(capture_tool.shutil, "which", lambda _name: sys.executable)

    real_authorize = authorize_capture

    def authorize_with_test_store(**kwargs: object) -> object:
        assert kwargs.get("drive_session") is True, "main did not forward driven-session authorization mode"
        return real_authorize(
            workspace=kwargs["workspace"],
            environment=environment,
            keyring_backend=keyring,
            approval_runtime_root=approval_runtime_root,
            launch_approval_id=kwargs.get("launch_approval_id"),
            launch_session_id=kwargs["launch_session_id"],
            diagnostic_grant_id=kwargs.get("diagnostic_grant_id"),
            drive_session=True,
        )

    monkeypatch.setattr(capture_tool, "authorize_capture", authorize_with_test_store)
    monkeypatch.setattr(
        capture_tool,
        "append_authorized_audit",
        lambda _capture: pytest.fail("dirty ACPX client environment reached audit"),
    )
    real_popen = subprocess.Popen
    observed_commands: list[object] = []

    def spy_popen(command: object, *args: object, **kwargs: object) -> subprocess.Popen[str]:
        observed_commands.append(command)
        if isinstance(command, (list, tuple)) and "--agent" in command:
            pytest.fail("dirty ACPX client environment reached spawn")
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(capture_tool.subprocess, "Popen", spy_popen)

    exit_code = main([
        "capture",
        "--workspace", str(workspace),
        "--output-dir", str(tmp_path / "output"),
        "--mode", "ordinary",
        "--drive-session",
        "--evidence-run-nonce", "run_0123456789abcdef01234567",
    ])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ACPX_CLIENT_ENV_NOT_CLEAN" in captured.err
    assert dirty_value not in captured.err

    with pytest.raises(LaunchGateError, match="ACPX_CLIENT_ENV_NOT_CLEAN"):
        capture_acpx(
            workspace=workspace,
            environment=environment,
            keyring_backend=keyring,
            approval_runtime_root=approval_runtime_root,
            launch_session_id="sess_dirty_complete_walk",
            command=[sys.executable, "--version"],
            drive_session=True,
        )
    assert not any(
        isinstance(command, (list, tuple)) and "--agent" in command
        for command in observed_commands
    )


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
    _patch_keyring(monkeypatch, FakeKeyring())
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
    _patch_keyring(monkeypatch, keyring)
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
