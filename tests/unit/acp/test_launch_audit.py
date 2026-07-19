"""Tests for the append-only, value-safe launch authorization audit.

Plan 9.96, Task 5 Step 6: Every launch decision appends the complete
value-safe audit schema before child startup, and audit failure is fatal
(no raw fallback).
"""

from __future__ import annotations

import json
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from optimus.acp.launch_audit import (
    LaunchAuditError,
    LaunchAuditEvent,
    append_launch_audit_event,
)


def _sample_event(**overrides: object) -> LaunchAuditEvent:
    defaults: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc),
        "workspace_digest": "a" * 64,
        "launch_session_id": "sess_test123",
        "approval_id": "appr_abc123",
        "approval_mode": "durable",
        "registry_version": "P9.96-v1",
        "policy_version": "P9.96-v1",
        "setting_decisions": (
            {"name": "OPTIMUS_GATEWAY_URL", "tier": "security", "source_class": "inherited", "decision": "approved"},
        ),
        "monotonic_dispositions": (
            {"name": "OPTIMUS_LIVE_MAX_COST_USD", "disposition": "tightened"},
        ),
        "rejected_names": (),
        "child_propagation_decisions": {"agent_child": ("OPTIMUS_GATEWAY_URL",), "gateway_child": ()},
        "diagnostic_grant_state": "none",
        "sanitizer_rule_counts": {},
        "final_reason_code": "AUTHORIZED",
    }
    defaults.update(overrides)
    return LaunchAuditEvent(**defaults)  # type: ignore[arg-type]


class TestAuditAppend:
    """Basic append-only behavior."""

    def test_append_creates_file(self, tmp_path: Path) -> None:
        event = _sample_event()
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        assert audit_file.exists()

    def test_append_writes_valid_json_line(self, tmp_path: Path) -> None:
        event = _sample_event()
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        line = audit_file.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["workspace_digest"] == "a" * 64
        assert parsed["approval_id"] == "appr_abc123"
        assert parsed["final_reason_code"] == "AUTHORIZED"

    def test_multiple_appends_produce_multiple_lines(self, tmp_path: Path) -> None:
        append_launch_audit_event(_sample_event(launch_session_id="sess_1"), runtime_root=tmp_path)
        append_launch_audit_event(_sample_event(launch_session_id="sess_2"), runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["launch_session_id"] == "sess_1"
        assert json.loads(lines[1])["launch_session_id"] == "sess_2"

    def test_missing_runtime_root_fails_without_creating_it(self, tmp_path: Path) -> None:
        runtime_root = tmp_path / "missing-runtime-root"

        with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
            append_launch_audit_event(_sample_event(), runtime_root=runtime_root)

        assert not runtime_root.exists()

    def test_symlink_runtime_root_fails_without_writing_target(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        target.mkdir()
        runtime_root = tmp_path / ".optimus"
        try:
            runtime_root.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlink creation unavailable")

        with pytest.raises(LaunchAuditError, match="AUDIT_DIR_UNAVAILABLE"):
            append_launch_audit_event(_sample_event(), runtime_root=runtime_root)

        assert not (target / "launch-audit.ndjson").exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only: file mode check")
    def test_created_file_has_restrictive_permissions(self, tmp_path: Path) -> None:
        event = _sample_event()
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        mode = audit_file.stat().st_mode
        assert not (mode & stat.S_IRWXG), "group must have no access"
        assert not (mode & stat.S_IRWXO), "other must have no access"
        assert mode & stat.S_IRUSR
        assert mode & stat.S_IWUSR


class TestAuditContentFields:
    """The audit event carries every field required by the plan's schema."""

    def test_rejection_event_records_names_only(self, tmp_path: Path) -> None:
        """Rejection audit contains only stable names/codes, never values."""
        event = _sample_event(
            approval_id=None,
            approval_mode=None,
            rejected_names=("OPTIMUS_UNKNOWN_SETTING",),
            final_reason_code="UNCLASSIFIED_VARIABLE",
        )
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        parsed = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert parsed["rejected_names"] == ["OPTIMUS_UNKNOWN_SETTING"]
        assert parsed["final_reason_code"] == "UNCLASSIFIED_VARIABLE"
        assert parsed["approval_id"] is None

    def test_child_propagation_decisions_recorded(self, tmp_path: Path) -> None:
        event = _sample_event(
            child_propagation_decisions={
                "agent_child": ("OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"),
                "gateway_child": ("OPTIMUS_LOCAL_GATEWAY_PROVIDER",),
            },
        )
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        parsed = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert parsed["child_propagation_decisions"]["agent_child"] == ["OPTIMUS_GATEWAY_URL", "OPTIMUS_API_KEY"]
        assert parsed["child_propagation_decisions"]["gateway_child"] == ["OPTIMUS_LOCAL_GATEWAY_PROVIDER"]

    def test_sanitizer_rule_counts_recorded(self, tmp_path: Path) -> None:
        event = _sample_event(sanitizer_rule_counts={"exact_secret_replacement": 2})
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        parsed = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert parsed["sanitizer_rule_counts"] == {"exact_secret_replacement": 2}

    def test_diagnostic_grant_state_recorded(self, tmp_path: Path) -> None:
        event = _sample_event(diagnostic_grant_state="consumed:diag_abc123")
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        parsed = json.loads(audit_file.read_text(encoding="utf-8").strip())
        assert parsed["diagnostic_grant_state"] == "consumed:diag_abc123"


class TestAuditValueSafety:
    """No canary secret ever appears in the persisted audit line, even if a
    caller accidentally passes one through a supposedly value-free field."""

    def test_canary_in_rejected_name_is_sanitized(self, tmp_path: Path) -> None:
        """Even if a caller mistakenly puts a secret-shaped string into a name
        field, the shared sanitizer (applied as a last line of defense)
        catches common secret patterns."""
        event = _sample_event(
            rejected_names=("OPTIMUS_API_KEY=sk-CANARY-CCC-SHOULD-NOT-APPEAR",),
        )
        append_launch_audit_event(event, runtime_root=tmp_path)
        audit_file = tmp_path / "launch-audit.ndjson"
        raw_text = audit_file.read_text(encoding="utf-8")
        assert "sk-CANARY-CCC-SHOULD-NOT-APPEAR" not in raw_text


class TestAuditFailureIsFatal:
    """Audit failure must be fatal — no raw fallback."""

    def test_unwritable_runtime_root_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the append itself fails (e.g. os.open raises), the error
        propagates as LaunchAuditError rather than silently degrading."""
        import optimus.acp.launch_audit as audit_module

        def _boom(*args: object, **kwargs: object) -> None:
            raise OSError("simulated disk failure")

        monkeypatch.setattr(audit_module, "_append_with_restrictive_permissions", _boom)

        with pytest.raises(LaunchAuditError) as exc_info:
            append_launch_audit_event(_sample_event(), runtime_root=tmp_path)
        assert exc_info.value.code == "AUDIT_APPEND_FAILED"

    def test_unserializable_payload_raises(self, tmp_path: Path) -> None:
        """A field that can't be JSON-serialized fails closed rather than
        falling back to a raw/partial write."""

        class Unserializable:
            def __repr__(self) -> str:
                raise RuntimeError("should never be called")

        event = _sample_event(sanitizer_rule_counts={"bad": Unserializable()})  # type: ignore[dict-item]
        # This should either sanitize the unsupported object safely or raise
        # LaunchAuditError — it must NOT crash with an unhandled exception
        # or silently write a raw fallback.
        try:
            append_launch_audit_event(event, runtime_root=tmp_path)
        except LaunchAuditError:
            pass  # Acceptable: fails closed.
        else:
            # If it succeeded, the sanitizer must have produced safe type
            # metadata rather than calling repr() on the object.
            audit_file = tmp_path / "launch-audit.ndjson"
            raw_text = audit_file.read_text(encoding="utf-8")
            assert "should never be called" not in raw_text
