"""Tamper-resistant contracts for the Plan 11.19 offline Zed reprobe verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.verify_plan1119_zed_reprobe_evidence import REQUIRED_FIELDS, SCHEMA, main

COMMIT = "cfaffbebf184cd7e08f15749ce5aaff414991ec1"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def valid_manifest(*, finding: str) -> dict[str, Any]:
    exchange: dict[str, Any] | None
    reason: str | None
    if finding == "REACHABLE":
        exchange = {
            "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
            "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
        }
        reason = None
    elif finding == "UNREACHABLE":
        exchange = {
            "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
            "response": {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method not found"}},
        }
        reason = None
    else:
        exchange = None
        reason = "OBSERVATION_INCOMPLETE"
    return {
        "schema": "plan-11-19-zed-session-load-reprobe-v1",
        "recorded_at_utc": "2026-08-17T12:00:00+00:00",
        "commit": COMMIT,
        "finding": finding,
        "indeterminate_reason": reason,
        "zed": {
            "version": "Zed 1.15.0",
            "executable": "C:/Tools/Zed.exe",
            "executable_sha256": SHA_A,
        },
        "acpx": {
            "version": "0.12.0",
            "executable": "C:/Tools/acpx.cmd",
            "executable_sha256": SHA_B,
        },
        "normal_source": {
            "commit": COMMIT,
            "sha256_before": SHA_C,
            "sha256_after": SHA_C,
        },
        "isolated_source": {"sha256": SHA_A},
        "isolated_build": {"sha256": SHA_B},
        "invocation": {
            "discovered_from": "zed --help",
            "argv": ["C:/Tools/Zed.exe", "--isolated-user-data", "scratch/zed-home"],
            "user_data_root": "scratch/zed-home",
            "help_sha256": SHA_A,
        },
        "isolation": {
            "normal_agent_load_session_advertised": False,
            "isolated_probe_load_session_advertised": True,
            "cleanup_dry_run_verified": True,
            "cleanup_verified": finding != "INDETERMINATE",
        },
        "capability_payload": {"loadSession": True, "sessionCapabilities": {}},
        "relay": {
            "source": "opaque-relay-post-run",
            "zed_to_agent_sha256": SHA_A,
            "agent_to_zed_sha256": SHA_B,
        },
        "captured_exchange": exchange,
        "origin_a_launches": 0,
        "zed_launches": 0 if finding == "INDETERMINATE" else 1,
        "files": {},
    }


def default_report(manifest: dict[str, Any]) -> str:
    finding = manifest["finding"]
    reason = manifest.get("indeterminate_reason")
    if finding == "INDETERMINATE":
        return (
            f"Finding: INDETERMINATE / {reason}. "
            "No captured session/load exchange. This is not a finding about Zed.\n"
        )
    return f"Finding: {finding}. Captured sanitized session/load exchange is recorded in the manifest.\n"


def write_manifest(
    tmp_path: Path,
    manifest: dict[str, Any],
    *,
    report_text: str | None = None,
    zed_bytes: bytes = b"zed-bytes",
    agent_bytes: bytes = b"agent-bytes",
) -> Path:
    report_dir = tmp_path / "reports" / "plan-11-19-zed-session-load-reprobe"
    report_dir.mkdir(parents=True)
    relay_dir = report_dir / "relay"
    relay_dir.mkdir()
    report_body = report_text if report_text is not None else default_report(manifest)
    report_path = report_dir / "report.md"
    zed_path = relay_dir / "zed-to-agent.bin"
    agent_path = relay_dir / "agent-to-zed.bin"
    report_path.write_text(report_body, encoding="utf-8", newline="\n")
    zed_path.write_bytes(zed_bytes)
    agent_path.write_bytes(agent_bytes)
    payload = json.loads(json.dumps(manifest))
    payload["relay"]["zed_to_agent_sha256"] = _sha256_file(zed_path)
    payload["relay"]["agent_to_zed_sha256"] = _sha256_file(agent_path)
    payload["files"] = {
        "report.md": _sha256_file(report_path),
        "relay/zed-to-agent.bin": _sha256_file(zed_path),
        "relay/agent-to-zed.bin": _sha256_file(agent_path),
    }
    path = report_dir / "manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    return path


def _rewrite(path: Path, mutator: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutator(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_valid_reachable_unreachable_and_indeterminate_pass(tmp_path: Path) -> None:
    for finding in ("REACHABLE", "UNREACHABLE", "INDETERMINATE"):
        path = write_manifest(tmp_path / finding, valid_manifest(finding=finding))
        assert main(["--manifest", str(path)]) == 0


def test_reachable_requires_captured_zed_request_and_empty_response(tmp_path: Path) -> None:
    manifest = valid_manifest(finding="REACHABLE")
    manifest["captured_exchange"] = None
    path = write_manifest(tmp_path, manifest)

    assert main(["--manifest", str(path)]) == 1


def test_missing_required_field_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def drop_commit(payload: dict[str, Any]) -> None:
        del payload["commit"]

    _rewrite(path, drop_commit)
    assert main(["--manifest", str(path)]) == 1


def test_normal_source_digest_drift_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def drift(payload: dict[str, Any]) -> None:
        payload["normal_source"]["sha256_after"] = "d" * 64

    _rewrite(path, drift)
    assert main(["--manifest", str(path)]) == 1


def test_normal_agent_advertisement_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def advertise(payload: dict[str, Any]) -> None:
        payload["isolation"]["normal_agent_load_session_advertised"] = True

    _rewrite(path, advertise)
    assert main(["--manifest", str(path)]) == 1


def test_isolated_probe_not_advertising_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def hide(payload: dict[str, Any]) -> None:
        payload["isolation"]["isolated_probe_load_session_advertised"] = False

    _rewrite(path, hide)
    assert main(["--manifest", str(path)]) == 1


def test_root_cleanup_false_fails_for_qualifying_finding(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def dirty(payload: dict[str, Any]) -> None:
        payload["isolation"]["cleanup_verified"] = False

    _rewrite(path, dirty)
    assert main(["--manifest", str(path)]) == 1


def test_raw_credential_like_value_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def leak(payload: dict[str, Any]) -> None:
        payload["notes"] = "OPTIMUS_API_KEY=live-secret"

    _rewrite(path, leak)
    assert main(["--manifest", str(path)]) == 1


def test_optional_relay_child_stderr_excerpt_is_backward_compatible_and_bounded(
    tmp_path: Path, capsys: Any
) -> None:
    assert SCHEMA == "plan-11-19-zed-session-load-reprobe-v1"
    assert "relay_child_stderr_excerpt" not in REQUIRED_FIELDS

    legacy = valid_manifest(finding="REACHABLE")
    assert "relay_child_stderr_excerpt" not in legacy
    legacy_path = write_manifest(tmp_path / "legacy", legacy)
    assert main(["--manifest", str(legacy_path)]) == 0

    for label, value in (("empty", ""), ("limit", "x" * 4000)):
        manifest = valid_manifest(finding="REACHABLE")
        manifest["relay_child_stderr_excerpt"] = value
        path = write_manifest(tmp_path / label, manifest)
        assert main(["--manifest", str(path)]) == 0

    for label, value, diagnostic in (
        ("wrong-type", 7, "relay_child_stderr_excerpt: must be a string"),
        ("too-long", "x" * 4001, "relay_child_stderr_excerpt: must be at most 4000 characters"),
    ):
        manifest = valid_manifest(finding="REACHABLE")
        manifest["relay_child_stderr_excerpt"] = value
        path = write_manifest(tmp_path / label, manifest)
        assert main(["--manifest", str(path)]) == 1
        assert capsys.readouterr().err.strip() == diagnostic

    canary = "sk-" + ("a" * 24)
    unsafe = valid_manifest(finding="REACHABLE")
    unsafe["relay_child_stderr_excerpt"] = f"child failed with {canary}"
    unsafe_path = write_manifest(tmp_path / "unsafe", unsafe)
    assert main(["--manifest", str(unsafe_path)]) == 1
    diagnostic = capsys.readouterr().err
    assert "manifest.relay_child_stderr_excerpt: raw credential-like value" in diagnostic
    assert canary not in diagnostic


def test_relay_digest_mismatch_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def mismatch(payload: dict[str, Any]) -> None:
        payload["relay"]["zed_to_agent_sha256"] = "0" * 64

    _rewrite(path, mismatch)
    assert main(["--manifest", str(path)]) == 1


def test_unreachable_without_captured_error_fails(tmp_path: Path) -> None:
    manifest = valid_manifest(finding="UNREACHABLE")
    manifest["captured_exchange"] = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    path = write_manifest(tmp_path, manifest)
    assert main(["--manifest", str(path)]) == 1


def test_indeterminate_without_named_reason_fails(tmp_path: Path) -> None:
    manifest = valid_manifest(finding="INDETERMINATE")
    manifest["indeterminate_reason"] = None
    path = write_manifest(tmp_path, manifest)
    assert main(["--manifest", str(path)]) == 1


def test_path_outside_report_directory_fails(tmp_path: Path) -> None:
    path = write_manifest(tmp_path, valid_manifest(finding="REACHABLE"))

    def escape(payload: dict[str, Any]) -> None:
        payload["files"]["../../secrets.json"] = SHA_A

    _rewrite(path, escape)
    assert main(["--manifest", str(path)]) == 1


def test_report_must_not_describe_normal_non_advertisement_as_zed_finding(tmp_path: Path) -> None:
    manifest = valid_manifest(finding="INDETERMINATE")
    manifest["indeterminate_reason"] = "INTERNAL_CAPABILITY_UNAVAILABLE"
    path = write_manifest(
        tmp_path,
        manifest,
        report_text="Zed does not support session/load after restart.\n",
    )
    assert main(["--manifest", str(path)]) == 1
