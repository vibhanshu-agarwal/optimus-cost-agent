"""Append-only, value-safe launch authorization audit.

Plan 9.96, Task 5 Step 6: Before any child/network startup, append one
LaunchAuditEvent under the workspace-local runtime root with timestamp,
workspace digest, launch/session/approval metadata, registry/policy
versions, setting names/tiers/source classes, display-safe non-secret
decisions, monotonic dispositions, unknown/internal rejection names,
child-propagation decisions, diagnostic-grant state, sanitizer rule counts,
and final value-free reason code. Audit path, permission, serialization,
sanitization, or append failure stops startup; there is no raw fallback.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from optimus.acp.operator_paths import WorkspaceRuntimeRootError, require_workspace_runtime_root
from optimus_security.sanitization import sanitize_for_persistence

_AUDIT_FILENAME = "launch-audit.ndjson"


class LaunchAuditError(ValueError):
    """Raised when the audit append fails. Startup must stop; no raw fallback."""

    def __init__(self, *, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class LaunchAuditEvent:
    """One value-safe record of a launch authorization decision."""

    timestamp: datetime
    workspace_digest: str
    launch_session_id: str
    approval_id: str | None
    approval_mode: str | None
    registry_version: str
    policy_version: str
    setting_decisions: tuple[dict[str, str], ...]
    monotonic_dispositions: tuple[dict[str, str], ...]
    rejected_names: tuple[str, ...]
    child_propagation_decisions: dict[str, tuple[str, ...]]
    diagnostic_grant_state: str
    sanitizer_rule_counts: dict[str, int] = field(default_factory=dict)
    final_reason_code: str = "AUTHORIZED"


def _audit_path(runtime_root: Path) -> Path:
    return runtime_root / _AUDIT_FILENAME


def append_launch_audit_event(event: LaunchAuditEvent, *, runtime_root: Path) -> None:
    """Append one audit event under the workspace-local runtime root.

    Opens with append semantics and restrictive current-user permissions.
    Sanitizes the payload through the shared sanitizer before writing (a
    defense-in-depth last line, matching debug_trace.acp_debug_log's
    unconditional-redaction pattern) even though every field here is
    value-free by construction. Any path, permission, serialization, or
    append failure raises LaunchAuditError — callers MUST treat this as
    fatal and stop startup; there is no raw fallback write.
    """
    try:
        require_workspace_runtime_root(runtime_root)
    except WorkspaceRuntimeRootError as exc:
        raise LaunchAuditError(code="AUDIT_DIR_UNAVAILABLE", detail="runtime root is unavailable") from exc

    path = _audit_path(runtime_root)

    try:
        payload = _serialize_event(event)
    except (TypeError, ValueError) as exc:
        raise LaunchAuditError(code="AUDIT_SERIALIZATION_FAILED") from exc

    # Sanitize only the fields that carry free-text risk (names supplied by
    # the launch-classification loop) as a last line of defense — matching
    # debug_trace.acp_debug_log's pattern of unconditionally redacting
    # free-form content. Structured metadata fields (rule-count dict KEYS
    # like "exact_secret_replacement" are rule identifiers, not secrets) are
    # left untouched so the blanket dict-key heuristic doesn't misfire on
    # this module's own vocabulary and corrupt otherwise value-free counts.
    payload["rejected_names"] = sanitize_for_persistence(
        payload["rejected_names"], known_secrets=()
    ).value
    payload["setting_decisions"] = sanitize_for_persistence(
        payload["setting_decisions"], known_secrets=()
    ).value
    # Sanitize rule-count VALUES (not keys — rule identifiers like
    # "exact_secret_replacement" are the plan's own vocabulary, not
    # secrets). Any non-int value routes through the sanitizer's
    # unsupported-object type-metadata path instead of json.dumps failing
    # the whole audit event over one malformed count.
    payload["sanitizer_rule_counts"] = {
        key: value if isinstance(value, int) else sanitize_for_persistence(value, known_secrets=()).value
        for key, value in payload["sanitizer_rule_counts"].items()
    }

    try:
        line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    except Exception as exc:
        # json.dumps has no `default=` fallback here deliberately: `default=str`
        # would call str()/repr() on an unsupported object, and a hostile or
        # buggy __repr__ can raise an arbitrary exception (proven empirically —
        # a __repr__ that raises RuntimeError propagates straight through
        # json's C encoder). Catching Exception broadly (not just TypeError/
        # ValueError) ensures ANY such failure fails closed as
        # AUDIT_SERIALIZATION_FAILED rather than crashing the caller with an
        # unrelated exception type or silently falling back to a raw write.
        raise LaunchAuditError(code="AUDIT_SERIALIZATION_FAILED") from exc

    try:
        _append_with_restrictive_permissions(path, line + "\n")
    except OSError as exc:
        raise LaunchAuditError(code="AUDIT_APPEND_FAILED", detail="cannot write audit event") from exc


def _serialize_event(event: LaunchAuditEvent) -> dict[str, Any]:
    return {
        "timestamp": event.timestamp.isoformat(),
        "workspace_digest": event.workspace_digest,
        "launch_session_id": event.launch_session_id,
        "approval_id": event.approval_id,
        "approval_mode": event.approval_mode,
        "registry_version": event.registry_version,
        "policy_version": event.policy_version,
        "setting_decisions": list(event.setting_decisions),
        "monotonic_dispositions": list(event.monotonic_dispositions),
        "rejected_names": list(event.rejected_names),
        "child_propagation_decisions": {k: list(v) for k, v in event.child_propagation_decisions.items()},
        "diagnostic_grant_state": event.diagnostic_grant_state,
        "sanitizer_rule_counts": dict(event.sanitizer_rule_counts),
        "final_reason_code": event.final_reason_code,
    }


def _append_with_restrictive_permissions(path: Path, text: str) -> None:
    """Open with append semantics and restrictive current-user permissions.

    On POSIX, creates the file (if new) with mode 0600 via os.open's `mode`
    argument combined with O_CREAT — os.open respects `mode` only at creation
    time, so an existing world-readable file is not silently tightened here;
    that is a pre-existing-file condition operators should not hit under
    normal use since this file lives under the trusted runtime root.
    On Windows, os.open's mode argument has no ACL effect; the trusted
    runtime root's own directory permissions (LocalAppData, current-user
    owned by OS default) are the actual boundary there.
    """
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    file_mode = stat.S_IRUSR | stat.S_IWUSR  # 0600
    fd = os.open(path, flags, file_mode)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
