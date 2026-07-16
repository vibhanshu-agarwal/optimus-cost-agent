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

from optimus.acp.ndjson_subprocess_session import _extract_gate_rejection_message


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
