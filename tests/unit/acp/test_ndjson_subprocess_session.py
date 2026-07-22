"""Unit tests for the launch-gate rejection detector in
ndjson_subprocess_session.py.

Plan 9.96, Task 5 Batch 3 review finding: _extract_gate_rejection_message's
docstring claims "All of __main__.py's own error prints use this exact
'optimus-agent: ' prefix" — that claim must be tested against EVERY rejection
family the docstring asserts it covers, not just the one family (NO_APPROVAL)
the original fix happened to be written against. A detector proven against
only a representative sample of its claimed input space is not proven at
all; the OperatorPathConfigurationError family was the specific gap found in
review (its print site at __main__.py's config-root resolution step omitted
the prefix its siblings all use).
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from optimus.acp.ndjson_subprocess_session import (
    LiveSessionError,
    NdjsonSubprocessSession,
    _extract_gate_rejection_message,
)


def test_stderr_is_sanitized_before_retention_without_breaking_gate_detection() -> None:
    canary = "ndjson-stderr-canary"
    stderr_line = f"optimus-agent: NO_APPROVAL: token={canary}\n"
    session = object.__new__(NdjsonSubprocessSession)
    session._process = SimpleNamespace(stderr=io.StringIO(stderr_line))
    session._stderr_lines = []

    session._read_stderr()

    retained = session.stderr_text()
    assert canary not in retained
    assert _extract_gate_rejection_message(retained) is not None


class TestGateRejectionDetectorCoversEveryPrefixedFamily:
    """Each of these stderr shapes is a REAL message __main__.py can print
    before the ACP protocol starts (i.e. before _authorize_or_exit/main()
    reaches the point of serving requests). If any of these regresses to
    omit the prefix, the corresponding rejection falls through to the
    misleading "timed out waiting for JSON-RPC response" wrapper."""

    def test_no_approval_rejection_is_detected(self) -> None:
        stderr_text = (
            "optimus-agent: no launch approval found for this workspace. Review the effective "
            "configuration and author one with:\n"
            "  optimus-trust --workspace-root /tmp/ws approve --mode durable\n"
        )
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "no launch approval found" in result
        assert "timed out" not in result

    def test_snapshot_mismatch_rejection_is_detected(self) -> None:
        stderr_text = (
            "optimus-agent: effective configuration changed since the last approval. Review the new "
            "configuration and re-approve with:\n"
            "  optimus-trust --workspace-root /tmp/ws approve --mode durable\n"
        )
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "effective configuration changed" in result

    def test_launch_gate_error_code_rejection_is_detected(self) -> None:
        stderr_text = "optimus-agent: UNCLASSIFIED_VARIABLE: OPTIMUS_SOME_UNKNOWN_NAME\n"
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "UNCLASSIFIED_VARIABLE" in result

    def test_trusted_path_error_rejection_is_detected(self) -> None:
        stderr_text = "optimus-agent: WORKSPACE_NOT_FOUND: workspace directory does not exist\n"
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "WORKSPACE_NOT_FOUND" in result

    def test_operator_path_configuration_error_rejection_is_detected(self) -> None:
        """The specific gap found in review: OperatorPathConfigurationError's
        print site must ALSO carry the prefix. This test exercises the exact
        message shape resolve_authorized_operator_paths() raises for a
        workspace-contained OPTIMUS_CONFIG_ROOT override -- proving the
        detector's claimed universal coverage against this family
        specifically, not just NO_APPROVAL."""
        stderr_text = (
            "optimus-agent: Refusing to load local gateway configuration from /workspace/config "
            "because it is inside workspace /workspace. Set OPTIMUS_CONFIG_ROOT to an absolute "
            "directory outside the workspace.\n"
        )
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "Refusing to load local gateway configuration" in result
        assert "timed out" not in result

    def test_audit_failure_rejection_is_detected(self) -> None:
        stderr_text = "optimus-agent: AUDIT_APPEND_FAILED: audit could not be recorded; startup stopped.\n"
        result = _extract_gate_rejection_message(stderr_text)
        assert result is not None
        assert "AUDIT_APPEND_FAILED" in result

    def test_unrelated_stderr_is_not_detected(self) -> None:
        """A message that never carries the prefix (e.g. a real ACP protocol
        crash unrelated to the launch gate) must NOT be misclassified as a
        gate rejection -- the detector should not be over-eager either."""
        stderr_text = "Traceback (most recent call last):\n  File ...\nValueError: something else broke\n"
        assert _extract_gate_rejection_message(stderr_text) is None

    def test_empty_stderr_is_not_detected(self) -> None:
        assert _extract_gate_rejection_message("") is None


class _BrokenPipeStdin:
    """A fake stdin that reproduces the real race: the child already closed
    its end of the pipe, so the write itself raises before any bytes land."""

    def write(self, _data: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise AssertionError("flush() must not run after write() already raised")


class TestSendAndCloseStdinSurviveAnAlreadyExitedChild:
    """Reproduces, deterministically, the race the real subprocess-backed
    test_run_operator_live_session_surfaces_no_approval_remediation only hits
    by timing luck: the launch-gate child exits (and closes stdin) before the
    parent's first send() completes. Real CI evidence
    (runs 29932232804 and 29932708043 on branch
    agent/claude/plan-9-99-backlog-broken-pipe) shows this raising a raw
    BrokenPipeError from send() at ndjson_subprocess_session.py:79, and then a
    SECOND BrokenPipeError from the unconditional operator_verify.py
    finally-block close_stdin() call at line 84 -- both call sites must
    convert the pipe closure into the same clean, value-free LiveSessionError
    read_next()/_fail_subprocess_exited() already produce for a read-time
    exit, not let a raw OSError escape."""

    def test_send_broken_pipe_surfaces_the_gate_rejection_cleanly(self) -> None:
        session = object.__new__(NdjsonSubprocessSession)
        session._process = SimpleNamespace(
            stdin=_BrokenPipeStdin(),
            poll=lambda: 2,
            wait=lambda timeout=None: 2,
        )
        session._transcript = SimpleNamespace(record_outbound=lambda _payload: None)
        session._stderr_reader = SimpleNamespace(join=lambda timeout=None: None)
        session._stderr_lines = [
            "optimus-agent: no launch approval found for this workspace. Review the effective "
            "configuration and author one with:\n",
            "  optimus-trust --workspace-root /tmp/ws approve --mode durable\n",
        ]

        with pytest.raises(LiveSessionError) as exc_info:
            session.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        assert "no launch approval found" in str(exc_info.value)
        assert "timed out" not in str(exc_info.value)

    def test_send_broken_pipe_without_a_gate_rejection_still_raises_cleanly(self) -> None:
        """No stderr at all (a bare crash, not a gate rejection) must still
        convert to a LiveSessionError -- never a raw BrokenPipeError."""
        session = object.__new__(NdjsonSubprocessSession)
        session._process = SimpleNamespace(
            stdin=_BrokenPipeStdin(),
            poll=lambda: 1,
            wait=lambda timeout=None: 1,
        )
        session._transcript = SimpleNamespace(record_outbound=lambda _payload: None)
        session._stderr_reader = SimpleNamespace(join=lambda timeout=None: None)
        session._stderr_lines = []

        with pytest.raises(LiveSessionError) as exc_info:
            session.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        assert "exited early" in str(exc_info.value)

    def test_close_stdin_swallows_an_already_broken_pipe(self) -> None:
        class _AlreadyClosedStdin:
            def close(self) -> None:
                raise BrokenPipeError(32, "Broken pipe")

        session = object.__new__(NdjsonSubprocessSession)
        session._process = SimpleNamespace(stdin=_AlreadyClosedStdin())

        session.close_stdin()  # must not raise

    def test_close_stdin_still_closes_a_healthy_pipe(self) -> None:
        closed = []

        class _HealthyStdin:
            def close(self) -> None:
                closed.append(True)

        session = object.__new__(NdjsonSubprocessSession)
        session._process = SimpleNamespace(stdin=_HealthyStdin())

        session.close_stdin()

        assert closed == [True]
