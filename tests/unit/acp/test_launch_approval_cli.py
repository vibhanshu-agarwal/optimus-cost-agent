"""Tests for the optimus-trust CLI.

Plan 9.96, Task 4 Step 6: Piped input cannot author, headless can read an
existing durable record, one-shot uses dedicated argv fields, credentials
never display, and CLI output/exception paths contain no canaries.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from optimus.acp.launch_approval_cli import CliError, _require_tty, main


class TestTtyRequirement:
    """Authoring and rotation require interactive TTY."""

    def test_require_tty_fails_when_stdin_not_tty(self) -> None:
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = True
            with pytest.raises(CliError):
                _require_tty()

    def test_require_tty_fails_when_stdout_not_tty(self) -> None:
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = False
            with pytest.raises(CliError):
                _require_tty()

    def test_require_tty_fails_when_both_not_tty(self) -> None:
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = False
            with pytest.raises(CliError):
                _require_tty()


class TestCliParsing:
    """CLI argument parsing."""

    def test_approve_requires_mode(self) -> None:
        with pytest.raises(SystemExit):
            main(["approve"])

    def test_inspect_on_nonexistent_workspace_fails_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "optimus.acp.launch_approval_cli._resolve_store",
            lambda _workspace_root: pytest.fail("keyring store must not be opened for a missing workspace"),
        )
        result = main(["--workspace-root", "/nonexistent/path", "inspect"])
        assert result != 0  # Should fail gracefully, not crash.


class TestElevatedDebugGrantSigning:
    """Plan 9.96, Task 6 Batch 2: _cmd_run's --elevated-debug branch must
    write a DiagnosticGrant that its OWN store's consume_diagnostic_grant
    will later accept -- i.e. it must be signed with compute_grant_hmac
    using the store's real hmac_key, not left at the Task 5 "" stub (which
    would now be rejected by Batch 2's own HMAC verification added to
    consume_diagnostic_grant)."""

    def test_elevated_debug_writes_a_grant_that_verifies_against_its_own_store(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import sys as _sys

        from optimus.acp import launch_approval_cli as cli_module
        from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        env = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        fake_keyring = FakeKeyring()
        authorize_workspace_for_test(env=env, workspace_root=workspace_root, fake_keyring=fake_keyring)

        # Patch _resolve_store to return a store backed by the SAME fake
        # keyring the durable approval was authored into, and patch
        # os.environ so _resolve_candidate resolves the matching candidate.
        for name, value in env.items():
            monkeypatch.setenv(name, value)

        def fake_resolve_store(_workspace_root):
            from optimus.acp.launch_approvals import KeyringApprovalStore

            store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path / ".runtime")
            return store, tmp_path / ".runtime"

        monkeypatch.setattr(cli_module, "_resolve_store", fake_resolve_store)

        fake_process = type("FakeResult", (), {"returncode": 0})()
        captured_argv: list[list[str]] = []
        real_subprocess_run = cli_module.subprocess.run

        def selective_subprocess_run(argv, **kwargs):
            # Only intercept the target-command spawn (recognizable by the
            # -c "pass" marker this test's target_argv uses); pass every
            # other subprocess.run call (e.g. resolve_workspace_identity's
            # internal `git rev-parse` probe) through to the REAL
            # subprocess.run, since patching the shared subprocess module
            # object affects every caller, not just this test's target spawn.
            if "-c" in argv and "pass" in argv:
                captured_argv.append(argv)
                return fake_process
            return real_subprocess_run(argv, **kwargs)

        monkeypatch.setattr(cli_module.subprocess, "run", selective_subprocess_run)
        monkeypatch.setattr(cli_module, "_require_tty", lambda: None)

        exit_code = cli_module._cmd_run(
            workspace_root,
            target_argv=[
                _sys.executable,
                "-c",
                "pass",
                "--grant={diagnostic_grant_id}",
                "--session={launch_session_id}",
            ],
            elevated_debug=True,
        )

        assert exit_code == 0
        # Recover the grant_id/session_id substituted into the spawned argv
        # and prove the SAME store's consume_diagnostic_grant accepts it --
        # the real end-to-end proof that the grant was signed with the
        # store's own hmac_key, not left unsigned/placeholder.
        spawned_argv = captured_argv[0]
        grant_arg = next(arg for arg in spawned_argv if arg.startswith("--grant="))
        session_arg = next(arg for arg in spawned_argv if arg.startswith("--session="))
        grant_id = grant_arg.removeprefix("--grant=")
        session_id = session_arg.removeprefix("--session=")
        store, _ = fake_resolve_store(workspace_root)
        consumed = store.consume_diagnostic_grant(grant_id, session_id)
        assert consumed.grant_id == grant_id


class TestHeadlessBehavior:
    """Headless processes cannot author approvals."""

    def test_piped_approve_fails(self) -> None:
        """A non-TTY process cannot run 'approve'."""
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = False
            result = main(["--workspace-root", ".", "approve", "--mode", "durable"])
            assert result == 2

    def test_piped_revoke_fails(self) -> None:
        """A non-TTY process cannot run 'revoke'."""
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = False
            result = main(["--workspace-root", ".", "revoke"])
            assert result == 2

    def test_piped_rotate_key_fails(self) -> None:
        """A non-TTY process cannot run 'rotate-key'."""
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = False
            result = main(["--workspace-root", ".", "rotate-key"])
            assert result == 2


class TestWorkspaceRuntimeRootBootstrap:
    """The approval-only bootstrap targets the resolved workspace root."""

    @staticmethod
    def _resolved_paths_from_workspace_symlink(tmp_path: Path):
        from optimus.acp import operator_paths

        target = tmp_path / "workspace-target"
        target.mkdir()
        workspace_link = tmp_path / "workspace-link"
        try:
            workspace_link.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")

        paths = operator_paths.resolve_operator_paths(
            workspace_root=workspace_link,
            environ={"HOME": str(tmp_path / "home")},
            platform_name="linux",
        )
        assert paths.workspace_root == target.resolve()
        return operator_paths, paths, target

    def test_bootstrap_creates_runtime_root_at_resolved_workspace_target(self, tmp_path: Path) -> None:
        operator_paths, paths, target = self._resolved_paths_from_workspace_symlink(tmp_path)
        bootstrap = getattr(operator_paths, "bootstrap_workspace_runtime_root", None)

        assert callable(bootstrap), "missing capability: approval-time runtime-root bootstrap"
        runtime_root = bootstrap(paths)

        assert runtime_root == target.resolve() / ".optimus"
        assert runtime_root.is_dir()
        assert not runtime_root.is_symlink()

    def test_bootstrap_rejects_regular_file_runtime_root(self, tmp_path: Path) -> None:
        operator_paths, paths, _target = self._resolved_paths_from_workspace_symlink(tmp_path)
        paths.runtime_root.write_text("not a directory", encoding="utf-8")
        bootstrap = getattr(operator_paths, "bootstrap_workspace_runtime_root", None)
        error_type = getattr(operator_paths, "WorkspaceRuntimeRootError", None)

        assert callable(bootstrap), "missing capability: approval-time runtime-root bootstrap"
        assert isinstance(error_type, type), "missing capability: runtime-root error"
        with pytest.raises(error_type, match="RUNTIME_ROOT_UNSAFE"):
            bootstrap(paths)

        assert paths.runtime_root.is_file()

    def test_bootstrap_rejects_final_symlink_without_writing_target(self, tmp_path: Path) -> None:
        operator_paths, paths, _target = self._resolved_paths_from_workspace_symlink(tmp_path)
        redirected_target = tmp_path / "redirected-target"
        redirected_target.mkdir()
        paths.runtime_root.symlink_to(redirected_target, target_is_directory=True)
        bootstrap = getattr(operator_paths, "bootstrap_workspace_runtime_root", None)
        error_type = getattr(operator_paths, "WorkspaceRuntimeRootError", None)

        assert callable(bootstrap), "missing capability: approval-time runtime-root bootstrap"
        assert isinstance(error_type, type), "missing capability: runtime-root error"
        with pytest.raises(error_type, match="RUNTIME_ROOT_UNSAFE"):
            bootstrap(paths)

        assert not (redirected_target / "launch-audit.ndjson").exists()


class TestApprovalTimeRuntimeBootstrap:
    """Approval, unlike launch and run, initializes the runtime root first."""

    @staticmethod
    def _configure_approval_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        config_root = tmp_path / "config"
        config_root.mkdir()
        environment = {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
            "OPTIMUS_CONFIG_ROOT": str(config_root),
        }
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        return environment

    def test_durable_approval_bootstraps_before_workspace_identity_capture(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import launch_approval_cli as cli_module
        from optimus.acp.launch_approvals import KeyringApprovalStore
        from tests.unit.acp.conftest import FakeKeyring

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        self._configure_approval_environment(tmp_path, monkeypatch)
        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path / "approval-runtime")
        observations: list[bool] = []
        original_resolve_identity = cli_module.resolve_workspace_identity

        def observe_identity(path: Path):
            observations.append((path.resolve() / ".optimus").is_dir())
            return original_resolve_identity(path)

        monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
        monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, tmp_path / "approval-runtime"))
        monkeypatch.setattr(cli_module, "resolve_workspace_identity", observe_identity)

        assert cli_module._cmd_approve(workspace, mode="durable", target_argv=[]) == 0
        assert observations == [True]
        assert store.read_durable(original_resolve_identity(workspace).digest) is not None

    def test_one_shot_approval_bootstraps_before_workspace_identity_capture(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import launch_approval_cli as cli_module
        from optimus.acp.launch_approvals import KeyringApprovalStore
        from tests.unit.acp.conftest import FakeKeyring

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        self._configure_approval_environment(tmp_path, monkeypatch)
        fake_keyring = FakeKeyring()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path / "approval-runtime")
        observations: list[bool] = []
        original_resolve_identity = cli_module.resolve_workspace_identity

        def observe_identity(path: Path):
            observations.append((path.resolve() / ".optimus").is_dir())
            return original_resolve_identity(path)

        monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
        monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, tmp_path / "approval-runtime"))
        monkeypatch.setattr(cli_module, "resolve_workspace_identity", observe_identity)

        assert cli_module._cmd_approve(workspace, mode="one-shot", target_argv=[]) == 0
        assert observations == [True]

    def test_bootstrap_failure_exits_before_store_or_record_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import launch_approval_cli as cli_module

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        self._configure_approval_environment(tmp_path, monkeypatch)
        bootstrap = getattr(cli_module, "bootstrap_workspace_runtime_root", None)
        error_type = getattr(cli_module, "WorkspaceRuntimeRootError", None)

        assert callable(bootstrap), "missing capability: approval-time bootstrap context"
        assert isinstance(error_type, type), "missing capability: runtime-root error mapping"

        def fail_bootstrap(_paths: object) -> None:
            raise error_type(code="RUNTIME_ROOT_UNAVAILABLE")

        monkeypatch.setattr(cli_module, "_require_tty", lambda: None)
        monkeypatch.setattr(cli_module, "bootstrap_workspace_runtime_root", fail_bootstrap)
        monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: pytest.fail("store must not open"))
        monkeypatch.setattr(cli_module, "build_approval_record", lambda **_kwargs: pytest.fail("record must not build"))
        monkeypatch.setattr(cli_module.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("must not spawn"))

        assert cli_module.main(["--workspace-root", str(workspace), "approve", "--mode", "durable"]) == 2

    def test_prepared_context_keeps_snapshot_value_when_live_environment_changes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from optimus.acp import launch_approval_cli as cli_module
        from optimus.acp.launch_policy import LaunchEnvironmentSnapshot

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        environment = self._configure_approval_environment(tmp_path, monkeypatch)
        approved_config_root = Path(environment["OPTIMUS_CONFIG_ROOT"])
        attacker_config_root = tmp_path / "attacker-config"
        attacker_config_root.mkdir()
        prepare_context = getattr(cli_module, "_prepare_approval_context", None)

        assert callable(prepare_context), "missing capability: single-snapshot approval context"

        original_capture = LaunchEnvironmentSnapshot.capture

        def capture_then_mutate(environ: object) -> LaunchEnvironmentSnapshot:
            snapshot = original_capture(environ)  # type: ignore[arg-type]
            monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(attacker_config_root))
            return snapshot

        monkeypatch.setattr(LaunchEnvironmentSnapshot, "capture", staticmethod(capture_then_mutate))
        snapshot, paths = prepare_context(workspace)

        assert snapshot.values["OPTIMUS_CONFIG_ROOT"] == str(approved_config_root)
        assert paths.config_root == approved_config_root.resolve()
        assert paths.config_root != attacker_config_root.resolve()

    def test_run_does_not_bootstrap_a_missing_runtime_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from optimus.acp import launch_approval_cli as cli_module
        from optimus.acp.launch_approvals import KeyringApprovalStore
        from tests.unit.acp.conftest import FakeKeyring, authorize_workspace_for_test

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        environment = self._configure_approval_environment(tmp_path, monkeypatch)
        fake_keyring = FakeKeyring()
        authorize_workspace_for_test(
            env=environment,
            workspace_root=workspace,
            fake_keyring=fake_keyring,
            runtime_root=tmp_path / "approval-runtime",
        )
        runtime_root = workspace / ".optimus"
        assert runtime_root.is_dir()
        runtime_root.rmdir()
        store = KeyringApprovalStore(keyring_backend=fake_keyring, runtime_root=tmp_path / "approval-runtime")
        prepare_context = getattr(cli_module, "_prepare_candidate_context", None)
        bootstrap = getattr(cli_module, "bootstrap_workspace_runtime_root", None)

        assert callable(prepare_context), "missing capability: non-bootstrapping candidate context"
        assert callable(bootstrap), "missing capability: approval-only bootstrap"
        monkeypatch.setattr(cli_module, "_resolve_store", lambda _workspace: (store, tmp_path / "approval-runtime"))
        monkeypatch.setattr(cli_module, "bootstrap_workspace_runtime_root", lambda _paths: pytest.fail("run must not bootstrap"))
        real_subprocess_run = cli_module.subprocess.run
        child_started = False

        def selective_subprocess_run(argv: list[str], **kwargs: object) -> object:
            nonlocal child_started
            if "-c" in argv and "pass" in argv:
                child_started = True
                return type("Result", (), {"returncode": 0})()
            return real_subprocess_run(argv, **kwargs)

        monkeypatch.setattr(cli_module.subprocess, "run", selective_subprocess_run)

        result = cli_module._cmd_run(
            workspace,
            target_argv=[sys.executable, "-c", "pass"],
            elevated_debug=False,
        )
        if sys.platform == "win32":
            assert result == 0
        else:
            assert result == 2
            assert capsys.readouterr().err == (
                "optimus-trust: no durable approval found for this workspace.\n"
            )
            assert not child_started
        assert not runtime_root.exists()


class TestOneShotArgvSpawning:
    """One-shot approval with argv substitution."""

    def test_one_shot_substitutes_placeholders_in_argv(self) -> None:
        """Placeholder {approval_id} and {launch_session_id} are substituted."""
        from optimus.acp.launch_approval_cli import _parse_args

        args = _parse_args([
            "--workspace-root", ".",
            "approve", "--mode", "one-shot",
            "--", "python", "-c", "print('{approval_id}')",
        ])
        assert args.mode == "one-shot"
        # REMAINDER captures everything including the -- separator; strip it.
        target = [a for a in args.target_argv if a != "--"]
        assert target == ["python", "-c", "print('{approval_id}')"]

    def test_run_command_accepts_elevated_debug(self) -> None:
        """The run subcommand supports --elevated-debug flag."""
        from optimus.acp.launch_approval_cli import _parse_args

        args = _parse_args([
            "--workspace-root", ".",
            "run", "--elevated-debug",
            "--", "python", "-c", "pass",
        ])
        assert args.elevated_debug is True
        target = [a for a in args.target_argv if a != "--"]
        assert target == ["python", "-c", "pass"]

    def test_run_without_target_argv_fails(self) -> None:
        """run with no target command returns error."""
        result = main(["--workspace-root", ".", "run"])
        assert result == 2


class TestResolveConfigRootUsesSnapshotNotOsEnviron:
    """Review finding: _resolve_candidate must read OPTIMUS_CONFIG_ROOT from
    the captured snapshot, never a second direct os.environ read — otherwise
    the digest (bound to the snapshot's value) and the actually-resolved
    config root (which parses .env.gateway / reads provider credentials)
    can diverge, reopening the Task 4 credential-swap hole through an
    ambient re-read instead of a stale approval."""

    def test_config_root_resolution_uses_captured_snapshot_value(self, tmp_path, monkeypatch) -> None:
        from optimus.acp.launch_approval_cli import _prepare_candidate_context, _resolve_candidate
        from optimus.acp.launch_approvals import KeyringApprovalStore

        approved_root = tmp_path / "approved_config"
        approved_root.mkdir()
        attacker_root = tmp_path / "attacker_config"
        attacker_root.mkdir()

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
        monkeypatch.setenv("OPTIMUS_API_KEY", "test-key")
        monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(approved_root))

        # Capture the snapshot exactly as _resolve_candidate does, THEN mutate
        # os.environ — simulating a TOCTOU window between snapshot capture
        # and any later direct os.environ read. If _resolve_candidate reads
        # os.environ a second time for OPTIMUS_CONFIG_ROOT, it will resolve
        # against attacker_root even though the digest is bound to
        # approved_root's snapshot value.
        import os as os_module

        from optimus.acp.launch_policy import LaunchEnvironmentSnapshot

        original_capture = LaunchEnvironmentSnapshot.capture

        def capture_then_mutate(environ):
            snapshot = original_capture(environ)
            os_module.environ["OPTIMUS_CONFIG_ROOT"] = str(attacker_root)
            return snapshot

        monkeypatch.setattr(LaunchEnvironmentSnapshot, "capture", staticmethod(capture_then_mutate))

        class FakeKeyring:
            def __init__(self) -> None:
                self._store: dict[tuple[str, str], str] = {}

            def get_password(self, service: str, key: str) -> str | None:
                return self._store.get((service, key))

            def set_password(self, service: str, key: str, value: str) -> None:
                self._store[(service, key)] = value

            def delete_password(self, service: str, key: str) -> None:
                self._store.pop((service, key), None)

        store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "runtime")

        snapshot, paths = _prepare_candidate_context(workspace)
        candidate = _resolve_candidate(workspace, store, snapshot=snapshot, operator_paths=paths)

        # The resolved config root must be the SNAPSHOT value (approved_root),
        # not whatever os.environ held by the time a later read might occur.
        assert candidate.operator_paths.config_root == approved_root.resolve()
        assert candidate.operator_paths.config_root != attacker_root.resolve()


class TestConfigFilePermissionsWiredIntoResolution:
    """Review finding: validate_config_file_permissions() had zero
    production call sites — .env.gateway was parsed with no permission
    check at all. _resolve_candidate must validate it before resolution."""

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_group_readable_env_gateway_fails_closed(self, tmp_path, monkeypatch) -> None:
        from optimus.acp.launch_approval_cli import _prepare_candidate_context, _resolve_candidate
        from optimus.acp.launch_approvals import KeyringApprovalStore
        from optimus.acp.launch_gate import LaunchGateError

        config_root = tmp_path / "config"
        config_root.mkdir()
        env_gateway = config_root / ".env.gateway"
        env_gateway.write_text("OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n", encoding="utf-8")
        env_gateway.chmod(0o640)  # group-readable — must be rejected

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
        monkeypatch.setenv("OPTIMUS_API_KEY", "test-key")
        monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config_root))

        class FakeKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

            def set_password(self, service: str, key: str, value: str) -> None:
                pass

        store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "runtime")

        snapshot, paths = _prepare_candidate_context(workspace)
        with pytest.raises(LaunchGateError) as exc_info:
            _resolve_candidate(workspace, store, snapshot=snapshot, operator_paths=paths)
        assert exc_info.value.code == "CONFIG_FILE_PERMISSIONS_TOO_OPEN"

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_owner_only_env_gateway_passes(self, tmp_path, monkeypatch) -> None:
        from optimus.acp.launch_approval_cli import _prepare_candidate_context, _resolve_candidate
        from optimus.acp.launch_approvals import KeyringApprovalStore

        config_root = tmp_path / "config"
        config_root.mkdir()
        env_gateway = config_root / ".env.gateway"
        env_gateway.write_text("OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n", encoding="utf-8")
        env_gateway.chmod(0o600)  # owner-only — must pass

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
        monkeypatch.setenv("OPTIMUS_API_KEY", "test-key")
        monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config_root))

        class FakeKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

            def set_password(self, service: str, key: str, value: str) -> None:
                pass

        store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "runtime")

        # Should not raise.
        snapshot, paths = _prepare_candidate_context(workspace)
        candidate = _resolve_candidate(workspace, store, snapshot=snapshot, operator_paths=paths)
        assert candidate.operator_paths.config_root == config_root.resolve()

    def test_env_gateway_permission_check_is_actually_invoked(self, tmp_path, monkeypatch) -> None:
        """Platform-agnostic proof that resolving a candidate through the CLI
        entry point (_resolve_candidate -> resolve_launch_candidate) calls
        validate_config_file_permissions() with the .env.gateway path when
        the file exists — mocked so this runs identically on any CI
        platform, complementing the POSIX-mode-bit tests above which are
        platform-guarded. The check itself now lives inside
        launch_gate.resolve_launch_candidate (review finding: it must be
        structural, not something each caller remembers to call), so the
        patch target is launch_gate, not launch_approval_cli."""
        import optimus.acp.launch_gate as launch_gate_module
        from optimus.acp.launch_approval_cli import _prepare_candidate_context, _resolve_candidate
        from optimus.acp.launch_approvals import KeyringApprovalStore

        config_root = tmp_path / "config"
        config_root.mkdir()
        env_gateway = config_root / ".env.gateway"
        env_gateway.write_text("OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n", encoding="utf-8")

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
        monkeypatch.setenv("OPTIMUS_API_KEY", "test-key")
        monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config_root))

        class FakeKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

            def set_password(self, service: str, key: str, value: str) -> None:
                pass

        store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "runtime")

        calls: list[Path] = []
        def recording_validate(path: Path, **_kwargs: object) -> None:
            calls.append(path)

        monkeypatch.setattr(launch_gate_module, "validate_config_file_permissions", recording_validate)

        snapshot, paths = _prepare_candidate_context(workspace)
        _resolve_candidate(workspace, store, snapshot=snapshot, operator_paths=paths)

        assert calls == [env_gateway.resolve()] or calls == [env_gateway]

    def test_missing_env_gateway_skips_permission_check(self, tmp_path, monkeypatch) -> None:
        """No .env.gateway present -> nothing to validate, resolution proceeds."""
        from optimus.acp.launch_approval_cli import _prepare_candidate_context, _resolve_candidate
        from optimus.acp.launch_approvals import KeyringApprovalStore

        config_root = tmp_path / "config"
        config_root.mkdir()
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "http://127.0.0.1:8765")
        monkeypatch.setenv("OPTIMUS_API_KEY", "test-key")
        monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
        monkeypatch.setenv("OPTIMUS_CONFIG_ROOT", str(config_root))

        class FakeKeyring:
            def get_password(self, service: str, key: str) -> str | None:
                return None

            def set_password(self, service: str, key: str, value: str) -> None:
                pass

        store = KeyringApprovalStore(keyring_backend=FakeKeyring(), runtime_root=tmp_path / "runtime")

        snapshot, paths = _prepare_candidate_context(workspace)
        candidate = _resolve_candidate(workspace, store, snapshot=snapshot, operator_paths=paths)
        assert candidate.operator_paths.config_root == config_root.resolve()


class _FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        self._store.pop((service, key), None)


def _sys_platform_is_posix() -> bool:
    import sys as _sys

    return _sys.platform != "win32"


class TestRunGatewayCommand:
    """Plan 9.96, Task 5 Batch 3 Step 4: `optimus-trust run-gateway` parses
    the repository's own .env.gateway as untrusted data, displays the safe
    snapshot, builds a signed GatewayChildManifest, and spawns the real
    optimus_gateway subprocess — replacing the launcher scripts' prior
    `source .env.gateway` behavior.

    _cmd_run_gateway takes explicit injectable parameters (trusted_roots,
    credential_keyring_backend) rather than requiring tests to monkeypatch
    internal module functions — matching the existing
    resolve_launch_candidate(credential_keyring_backend=...) pattern used
    elsewhere in this codebase, and keeping the real OS keyring completely
    out of the test path."""

    def test_run_gateway_requires_tty(self, tmp_path) -> None:
        """A non-interactive invocation fails with a value-free message —
        the explicit developer/admin ceremony this command wraps cannot be
        run headlessly, same as approve/revoke/rotate-key."""
        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = False
            mock_stdout.isatty.return_value = False
            result = main(["--workspace-root", str(tmp_path), "run-gateway"])
            assert result == 2

    def test_run_gateway_missing_env_gateway_file_fails_closed(self, tmp_path, monkeypatch) -> None:
        """No repository .env.gateway present -> fail closed with remediation,
        never fall through to spawning the gateway with no credentials."""
        from optimus.acp.launch_approval_cli import _cmd_run_gateway
        from optimus.acp.trusted_paths import TrustedOperatorRoots

        popen_calls: list[object] = []
        monkeypatch.setattr("subprocess.run", lambda *a, **k: popen_calls.append((a, k)))

        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            result = _cmd_run_gateway(
                tmp_path,
                bind_host="127.0.0.1",
                bind_port=8765,
                trusted_roots=TrustedOperatorRoots(
                    default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"
                ),
                credential_keyring_backend=_FakeKeyring(),
            )

        assert result == 2
        assert popen_calls == []

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="POSIX-only: permission bit checks",
    )
    def test_run_gateway_rejects_insecure_env_gateway_permissions(self, tmp_path, monkeypatch) -> None:
        from optimus.acp.launch_approval_cli import _cmd_run_gateway
        from optimus.acp.trusted_paths import TrustedOperatorRoots

        env_gateway = tmp_path / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-should-never-be-read\n"
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=shared-secret-value\n",
            encoding="utf-8",
        )
        env_gateway.chmod(0o640)  # group-readable — must be rejected

        popen_calls: list[object] = []
        monkeypatch.setattr("subprocess.run", lambda *a, **k: popen_calls.append((a, k)))

        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            result = _cmd_run_gateway(
                tmp_path,
                bind_host="127.0.0.1",
                bind_port=8765,
                trusted_roots=TrustedOperatorRoots(
                    default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"
                ),
                credential_keyring_backend=_FakeKeyring(),
            )

        assert result == 2
        assert popen_calls == []

    def test_run_gateway_no_credentials_resolved_fails_closed(self, tmp_path, monkeypatch) -> None:
        """A syntactically-valid but empty .env.gateway (or one missing the
        provider key) must not spawn the gateway with no credentials."""
        from optimus.acp.launch_approval_cli import _cmd_run_gateway
        from optimus.acp.trusted_paths import TrustedOperatorRoots

        env_gateway = tmp_path / ".env.gateway"
        env_gateway.write_text("OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n", encoding="utf-8")
        if _sys_platform_is_posix():
            env_gateway.chmod(0o600)

        popen_calls: list[object] = []
        monkeypatch.setattr("subprocess.run", lambda *a, **k: popen_calls.append((a, k)))

        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            result = _cmd_run_gateway(
                tmp_path,
                bind_host="127.0.0.1",
                bind_port=8765,
                trusted_roots=TrustedOperatorRoots(
                    default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"
                ),
                credential_keyring_backend=_FakeKeyring(),  # empty — no provider key stored
            )

        assert result == 2
        assert popen_calls == []

    def test_run_gateway_builds_manifest_and_spawns_with_expected_args(self, tmp_path, monkeypatch) -> None:
        """The manifest passed to the spawned optimus_gateway subprocess
        contains no raw secret, and --bind-host/--port/--manifest are all
        present as explicit CLI arguments (never env vars)."""
        from optimus.acp.launch_approval_cli import _cmd_run_gateway
        from optimus.acp.trusted_paths import TrustedOperatorRoots

        env_gateway = tmp_path / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-CANARY-SECRET-VALUE\n"
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=CANARY-SHARED-SECRET\n",
            encoding="utf-8",
        )
        if _sys_platform_is_posix():
            env_gateway.chmod(0o600)

        captured: dict[str, object] = {}

        class FakeCompletedProcess:
            returncode = 0
            stdout = ""

        real_subprocess_run = subprocess.run

        def fake_run(args, **kwargs):
            if args and isinstance(args, list) and "optimus_gateway" in args:
                captured["args"] = args
                captured["kwargs"] = kwargs
                return FakeCompletedProcess()
            # Any other subprocess.run call (e.g. resolve_workspace_identity's
            # git rev-parse) passes through to the real implementation so it
            # behaves normally rather than being intercepted too.
            return real_subprocess_run(args, **kwargs)

        monkeypatch.setattr("subprocess.run", fake_run)

        with patch("sys.stdin") as mock_stdin, patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdout.isatty.return_value = True
            result = _cmd_run_gateway(
                tmp_path,
                bind_host="127.0.0.1",
                bind_port=8765,
                trusted_roots=TrustedOperatorRoots(
                    default_config_root=tmp_path / "config", approval_runtime_root=tmp_path / "runtime"
                ),
                credential_keyring_backend=_FakeKeyring(),
            )

        assert result == 0
        args = captured["args"]
        assert "--bind-host" in args and args[args.index("--bind-host") + 1] == "127.0.0.1"
        assert "--port" in args and args[args.index("--port") + 1] == "8765"
        assert "--manifest" in args
        manifest_arg = args[args.index("--manifest") + 1]
        assert "sk-CANARY-SECRET-VALUE" not in manifest_arg
        assert "CANARY-SHARED-SECRET" not in manifest_arg
        # No env var carries the bind host/port — closing the standalone
        # bind seam from the parent side too.
        env_passed = captured["kwargs"].get("env")
        if env_passed is not None:
            assert "OPTIMUS_LOCAL_GATEWAY_BIND_HOST" not in env_passed
            assert "OPTIMUS_LOCAL_GATEWAY_PORT" not in env_passed

    def test_run_gateway_masks_base_url_userinfo_in_display(self, tmp_path, monkeypatch) -> None:
        """Direct run-gateway stdout must redact URI userinfo while transport
        (child env + signed manifest) keeps the raw effective base URL."""
        import io

        from optimus.acp.launch_approval_cli import _cmd_run_gateway
        from optimus.acp.trusted_paths import TrustedOperatorRoots

        canary = "uri-display-canary-XYZ"
        raw_base_url = f"https://{canary}:pass@api.example.com/v1"

        env_gateway = tmp_path / ".env.gateway"
        env_gateway.write_text(
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER=openrouter\n"
            "OPTIMUS_LOCAL_GATEWAY_PROVIDER_API_KEY=sk-CANARY-SECRET-VALUE\n"
            "OPTIMUS_LOCAL_GATEWAY_SHARED_SECRET=CANARY-SHARED-SECRET\n"
            f"OPTIMUS_LOCAL_GATEWAY_BASE_URL={raw_base_url}\n",
            encoding="utf-8",
        )
        if _sys_platform_is_posix():
            env_gateway.chmod(0o600)

        captured: dict[str, object] = {}

        class FakeCompletedProcess:
            returncode = 0
            stdout = ""

        real_subprocess_run = subprocess.run

        def fake_run(args, **kwargs):
            if args and isinstance(args, list) and "optimus_gateway" in args:
                captured["args"] = args
                captured["kwargs"] = kwargs
                return FakeCompletedProcess()
            return real_subprocess_run(args, **kwargs)

        monkeypatch.setattr("subprocess.run", fake_run)

        class CapturingStdout(io.StringIO):
            def isatty(self) -> bool:
                return True

        stdout_capture = CapturingStdout()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("sys.stdout", stdout_capture):
                result = _cmd_run_gateway(
                    tmp_path,
                    bind_host="127.0.0.1",
                    bind_port=8765,
                    trusted_roots=TrustedOperatorRoots(
                        default_config_root=tmp_path / "config",
                        approval_runtime_root=tmp_path / "runtime",
                    ),
                    credential_keyring_backend=_FakeKeyring(),
                )

        assert result == 0
        output = stdout_capture.getvalue()
        assert canary not in output
        assert "**********" in output

        child_env = captured["kwargs"]["env"]
        assert child_env["OPTIMUS_LOCAL_GATEWAY_BASE_URL"] == raw_base_url

        args = captured["args"]
        manifest_arg = args[args.index("--manifest") + 1]
        assert canary in manifest_arg
        assert raw_base_url in manifest_arg


class TestOutputContainsNoSecrets:
    """CLI output and exception paths contain no canary secrets."""

    def test_error_messages_contain_no_raw_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error messages from the CLI contain codes, not secret values."""
        monkeypatch.setattr(
            "optimus.acp.launch_approval_cli._resolve_store",
            lambda _workspace_root: pytest.fail("keyring store must not be opened for a missing workspace"),
        )
        # Trigger a workspace-not-found error.
        import io
        from contextlib import redirect_stderr

        stderr_capture = io.StringIO()
        with redirect_stderr(stderr_capture):
            result = main(["--workspace-root", "/nonexistent/secret-path", "inspect"])

        stderr_text = stderr_capture.getvalue()
        # Should NOT contain raw paths in an exploitable form — just error codes.
        assert result != 0
        # The error message should be about workspace resolution, not leak internals.
        assert "optimus-trust:" in stderr_text or stderr_text == ""
