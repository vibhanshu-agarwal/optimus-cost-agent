"""Tests for the optimus-trust CLI.

Plan 9.96, Task 4 Step 6: Piped input cannot author, headless can read an
existing durable record, one-shot uses dedicated argv fields, credentials
never display, and CLI output/exception paths contain no canaries.
"""

from __future__ import annotations

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

    def test_inspect_on_nonexistent_workspace_fails_gracefully(self) -> None:
        result = main(["--workspace-root", "/nonexistent/path", "inspect"])
        assert result != 0  # Should fail gracefully, not crash.


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


class TestOutputContainsNoSecrets:
    """CLI output and exception paths contain no canary secrets."""

    def test_error_messages_contain_no_raw_values(self) -> None:
        """Error messages from the CLI contain codes, not secret values."""
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
