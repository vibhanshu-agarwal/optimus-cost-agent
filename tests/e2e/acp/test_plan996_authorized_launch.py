"""Real Plan 9.96 launch evidence driven by the independent ``acpx`` client.

Run these nodes only in the non-interleaving order pinned by Plan 9.98 Task 5.
The elevated node verifies operator-produced artifacts; it never authors or
consumes a diagnostic grant itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import keyring
import pytest

from optimus.acp.launch_approvals import KeyringApprovalStore
from optimus.acp.launch_policy import (
    DEFAULT_LIVE_MAX_COST_USD,
    LAUNCH_VARIABLE_POLICIES,
    LaunchVariableTier,
)
from optimus.acp.trusted_paths import (
    resolve_trusted_operator_roots,
    resolve_workspace_identity,
)
from tools.run_plan996_acpx_security_evidence import (
    _SESSION_FIXTURE_FILENAME,
    _SESSION_FIXTURE_PRISTINE_CONTENT,
)

pytestmark = pytest.mark.e2e

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CAPTURE_TOOL = _PROJECT_ROOT / "tools" / "run_plan996_acpx_security_evidence.py"
_EVIDENCE_WORKSPACE = Path("C:/tmp/optimus-plan998-evidence")
_ARTIFACT_ROOT = Path("C:/tmp/optimus-plan998-artifacts")
_ORDINARY_ARTIFACTS = _ARTIFACT_ROOT / "ordinary"
_ELEVATED_ARTIFACTS = _ARTIFACT_ROOT / "elevated"
_NONCE_MARKER = _EVIDENCE_WORKSPACE / ".evidence-run-nonce"
_MANIFEST_FILENAME = "sanitizer-manifest.json"
_EXPECTED_AGENT_CHILD_KEYS = {
    "OPTIMUS_AGENT_MODEL",
    "OPTIMUS_API_KEY",
    "OPTIMUS_GATEWAY_URL",
    "OPTIMUS_PRODUCTION_MODE",
    "OPTIMUS_REDIS_URL",
}
_REQUIRED_SESSION_ARTIFACTS = {
    "transcript.stdout",
    "transcript.stderr",
    "external-session-evidence.json",
    "audit-snapshot.ndjson",
    "debug-snapshot.ndjson",
}
_ALLOWED_CORRELATION_TAG_FIELDS = {
    name
    for name, policy in LAUNCH_VARIABLE_POLICIES.items()
    if policy.tier is LaunchVariableTier.SECRET
}
_NONCE_RE = re.compile(r"^run_[0-9a-f]{24}$")
_TAG_RE = re.compile(r"^[0-9a-f]{32}$")
_CAPTURE_TIMEOUT_SECONDS = 900
_REJECTION_TIMEOUT_SECONDS = 60
_VERIFY_TIMEOUT_SECONDS = 60


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean_capture_environment() -> dict[str, str]:
    """Keep process transport settings while excluding classified launch input."""
    return {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("OPTIMUS_")
    }


def _run_capture(
    *, workspace: Path, output_dir: Path, mode: str, nonce: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_CAPTURE_TOOL),
            "capture",
            "--workspace",
            str(workspace),
            "--output-dir",
            str(output_dir),
            "--mode",
            mode,
            "--evidence-run-nonce",
            nonce,
            "--drive-session",
        ],
        cwd=_PROJECT_ROOT,
        env=_clean_capture_environment(),
        capture_output=True,
        text=True,
        timeout=_CAPTURE_TIMEOUT_SECONDS,
        check=False,
    )


def _verify_artifacts(output_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(_CAPTURE_TOOL),
            "verify",
            "--manifest",
            str(output_dir / _MANIFEST_FILENAME),
            "--artifact-dir",
            str(output_dir),
        ],
        cwd=_PROJECT_ROOT,
        env=_clean_capture_environment(),
        capture_output=True,
        text=True,
        timeout=_VERIFY_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, (
        f"evidence verification failed with exit code {result.returncode}"
    )
    assert "evidence manifest verified" in result.stderr


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"expected a JSON object in {path.name}"
    return value


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        assert isinstance(value, dict), f"expected JSON objects in {path.name}"
        records.append(value)
    return records


def _transcript_run_id(transcript_path: Path) -> str:
    session_ids: set[str] = set()
    prompt_request_ids: set[int] = set()
    for record in _load_ndjson(transcript_path):
        result = record.get("result")
        if isinstance(result, dict) and isinstance(result.get("sessionId"), str):
            session_ids.add(result["sessionId"])
        if record.get("method") == "session/prompt" and isinstance(record.get("id"), int):
            prompt_request_ids.add(record["id"])
    assert len(session_ids) == 1, "transcript must identify exactly one ACP session"
    assert len(prompt_request_ids) == 1, "transcript must identify exactly one prompt request"
    return f"{next(iter(session_ids))}:{next(iter(prompt_request_ids))}"


def _live_cost_cap() -> Decimal:
    raw = os.environ.get("OPTIMUS_LIVE_MAX_COST_USD", "").strip()
    if not raw:
        return DEFAULT_LIVE_MAX_COST_USD
    try:
        cap = Decimal(raw)
    except InvalidOperation as exc:
        raise AssertionError("OPTIMUS_LIVE_MAX_COST_USD must be a decimal") from exc
    assert cap.is_finite() and cap > 0
    return cap


def _assert_common_session_evidence(
    *, output_dir: Path, expected_mode: str, expected_nonce: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _verify_artifacts(output_dir)

    manifest_path = output_dir / _MANIFEST_FILENAME
    manifest = _load_json(manifest_path)
    external = _load_json(output_dir / "external-session-evidence.json")
    audit_records = _load_ndjson(output_dir / "audit-snapshot.ndjson")
    debug_records = _load_ndjson(output_dir / "debug-snapshot.ndjson")

    assert manifest["evidence_run_nonce"] == expected_nonce
    assert manifest["session_mode"] == expected_mode
    assert manifest["stop_reason"] == "end_turn"
    assert manifest["final_agent_state"] == "COMPLETED"

    tool_names = manifest["tool_names"]
    assert isinstance(tool_names, list) and tool_names
    assert all(isinstance(name, str) and name for name in tool_names)
    assert "write_file" in tool_names
    assert manifest["tool_call_count"] == len(tool_names)
    assert manifest["tool_call_count"] > 0

    try:
        cost = Decimal(external["total_cost_usd"])
    except (InvalidOperation, KeyError, TypeError) as exc:
        raise AssertionError("external session cost must be a decimal string") from exc
    assert cost.is_finite() and Decimal("0") < cost <= _live_cost_cap()
    assert manifest["total_cost_usd"] == external["total_cost_usd"]
    assert external["run_id"] == _transcript_run_id(output_dir / "transcript.stdout")

    artifact_sha256 = manifest["artifact_sha256"]
    assert isinstance(artifact_sha256, dict)
    assert _REQUIRED_SESSION_ARTIFACTS <= set(artifact_sha256)
    for name in _REQUIRED_SESSION_ARTIFACTS:
        assert artifact_sha256[name] == _sha256(output_dir / name)
    joined_scan = manifest["joined_scan"]
    assert isinstance(joined_scan, dict)
    assert joined_scan["hit"] is False
    assert joined_scan["rules_fired"] == []
    assert _REQUIRED_SESSION_ARTIFACTS <= set(joined_scan["scanned_artifacts"])

    assert len(audit_records) == 2
    outer_decisions = audit_records[0]["child_propagation_decisions"]
    assert set(outer_decisions["agent_child"]) == _EXPECTED_AGENT_CHILD_KEYS
    assert outer_decisions["acpx_client"] == []
    assert set(manifest["child_key_names"]) == _EXPECTED_AGENT_CHILD_KEYS
    return manifest, debug_records


def test_unapproved_capture_leaves_fixture_unmutated(tmp_path: Path) -> None:
    workspace = tmp_path / "unapproved-workspace"
    workspace.mkdir()
    fixture = workspace / _SESSION_FIXTURE_FILENAME
    fixture.write_text(_SESSION_FIXTURE_PRISTINE_CONTENT, encoding="utf-8")
    digest_before = _sha256(fixture)

    roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    identity = resolve_workspace_identity(workspace)
    store = KeyringApprovalStore(
        keyring_backend=keyring,
        runtime_root=roots.approval_runtime_root,
    )
    assert store.read_durable(identity.digest) is None

    nonce = f"run_{secrets.token_hex(12)}"
    result = subprocess.run(
        [
            sys.executable,
            str(_CAPTURE_TOOL),
            "capture",
            "--workspace",
            str(workspace),
            "--output-dir",
            str(tmp_path / "unapproved-artifacts"),
            "--mode",
            "ordinary",
            "--evidence-run-nonce",
            nonce,
            "--drive-session",
        ],
        cwd=_PROJECT_ROOT,
        env=_clean_capture_environment(),
        capture_output=True,
        text=True,
        timeout=_REJECTION_TIMEOUT_SECONDS,
        check=False,
    )

    assert result.returncode == 2
    assert "no launch approval" in result.stderr.lower()
    assert "approve --mode durable" in result.stderr
    assert "Traceback" not in result.stderr
    assert _sha256(fixture) == digest_before


def test_ordinary_session_evidence() -> None:
    assert _EVIDENCE_WORKSPACE.is_dir(), (
        "create C:/tmp/optimus-plan998-evidence and author its durable approval first"
    )
    roots = resolve_trusted_operator_roots(platform_name=sys.platform)
    identity = resolve_workspace_identity(_EVIDENCE_WORKSPACE)
    store = KeyringApprovalStore(
        keyring_backend=keyring,
        runtime_root=roots.approval_runtime_root,
    )
    assert store.read_durable(identity.digest) is not None, (
        "run: uv run optimus-trust --workspace-root "
        "C:/tmp/optimus-plan998-evidence approve --mode durable"
    )

    fixture = _EVIDENCE_WORKSPACE / _SESSION_FIXTURE_FILENAME
    fixture.write_text(_SESSION_FIXTURE_PRISTINE_CONTENT, encoding="utf-8")
    nonce = f"run_{secrets.token_hex(12)}"
    result = _run_capture(
        workspace=_EVIDENCE_WORKSPACE,
        output_dir=_ORDINARY_ARTIFACTS,
        mode="ordinary",
        nonce=nonce,
    )
    assert result.returncode == 0, (
        f"ordinary capture failed with exit code {result.returncode}"
    )

    manifest, debug_records = _assert_common_session_evidence(
        output_dir=_ORDINARY_ARTIFACTS,
        expected_mode="ordinary",
        expected_nonce=nonce,
    )
    comparison_records = [
        record
        for record in debug_records
        if record.get("location") == "launch_authorization_comparison"
    ]
    assert manifest["elevated_comparison_record_present"] is False
    assert comparison_records == []


def test_elevated_session_evidence_verification() -> None:
    nonce = _NONCE_MARKER.read_text(encoding="utf-8").strip()
    assert _NONCE_RE.fullmatch(nonce), "elevated nonce marker is absent or malformed"

    manifest, debug_records = _assert_common_session_evidence(
        output_dir=_ELEVATED_ARTIFACTS,
        expected_mode="elevated",
        expected_nonce=nonce,
    )
    comparison_records = [
        record
        for record in debug_records
        if record.get("location") == "launch_authorization_comparison"
    ]
    assert manifest["elevated_comparison_record_present"] is True
    assert len(comparison_records) == 1

    tags = comparison_records[0]["data"]["correlation_tags"]
    assert isinstance(tags, list)
    for tag in tags:
        assert isinstance(tag, dict)
        assert set(tag) == {"field_name", "tag"}
        assert tag["field_name"] in _ALLOWED_CORRELATION_TAG_FIELDS
        assert _TAG_RE.fullmatch(tag["tag"])
