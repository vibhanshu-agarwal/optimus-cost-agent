"""Tamper-resistant contracts for the Plan 11.19 offline Zed reprobe verifier."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tools.verify_plan1119_zed_reprobe_evidence import main

COMMIT = "cfaffbebf184cd7e08f15749ce5aaff414991ec1"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
PLAN1124_EXEC_MESSAGE = "Persist this probe thread only; do not use tools or modify files."


def _write_valid_lifecycle_a_relay(relay_a: Path) -> None:
    zed = (
        b'{"jsonrpc":"2.0","id":1,"method":"session/new"}\n'
        b'{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"session-a","prompt":[{"type":"text","text":"'
        + PLAN1124_EXEC_MESSAGE.encode("utf-8")
        + b'"}]}}\n'
    )
    agent = (
        b'{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-a"}}\n'
        b'{"jsonrpc":"2.0","id":2,"error":{"code":-32000,"message":"prompt rejected"}}\n'
    )
    (relay_a / "zed-to-agent.bin").write_bytes(zed)
    (relay_a / "agent-to-zed.bin").write_bytes(agent)


def _write_minimal_lifecycle_b_relay(relay_b: Path) -> None:
    (relay_b / "zed-to-agent.bin").write_bytes(
        b'{"jsonrpc":"2.0","id":9,"method":"session/load","params":{"sessionId":"session-a"}}\n'
    )
    (relay_b / "agent-to-zed.bin").write_bytes(b'{"jsonrpc":"2.0","id":9,"result":{}}\n')


def _v5_resume_lifecycle(*, session_id: str = "session-a", load_response: dict[str, Any] | None = None) -> dict[str, Any]:
    if load_response is None:
        load_response = {"jsonrpc": "2.0", "id": 9, "result": {}}
    return {
        "shared_profile": True,
        "shared_user_data_root": "scratch/zed-home",
        "shared_workspace": "scratch/zed-workspace",
        "lifecycle_a": {
            "label": "plan1124-create",
            "session_new_id": session_id,
        },
        "lifecycle_b": {
            "label": "plan1124-resume",
            "session_load_exchange": {
                "request": {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "session/load",
                    "params": {"sessionId": session_id},
                },
                "response": load_response,
            },
        },
    }


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


def test_optional_relay_child_stderr_excerpt_is_backward_compatible_and_bounded(
    tmp_path: Path, capsys: object
) -> None:
    # No optional field remains accepted byte-for-byte.
    path = write_manifest(tmp_path / "no-field", valid_manifest(finding="REACHABLE"))
    assert main(["--manifest", str(path)]) == 0

    for excerpt in ("", "a" * 4000):
        manifest = valid_manifest(finding="REACHABLE")
        manifest["relay_child_stderr_excerpt"] = excerpt
        path = write_manifest(tmp_path / f"ok-{len(excerpt)}", manifest)
        assert main(["--manifest", str(path)]) == 0

    manifest = valid_manifest(finding="REACHABLE")
    manifest["relay_child_stderr_excerpt"] = 123
    path = write_manifest(tmp_path / "bad-type", manifest)
    assert main(["--manifest", str(path)]) == 1

    manifest = valid_manifest(finding="REACHABLE")
    manifest["relay_child_stderr_excerpt"] = "a" * 4001
    path = write_manifest(tmp_path / "bad-len", manifest)
    assert main(["--manifest", str(path)]) == 1

    secret_like = "OPTIMUS_API_KEY=live-secret"
    manifest = valid_manifest(finding="REACHABLE")
    manifest["relay_child_stderr_excerpt"] = secret_like
    path = write_manifest(tmp_path / "bad-secret-like", manifest)
    assert main(["--manifest", str(path)]) == 1
    captured = capsys.readouterr()
    assert secret_like not in captured.err


def test_v5_manifest_requires_two_lifecycle_correlation_but_legacy_manifests_still_pass(tmp_path: Path) -> None:
    legacy = write_manifest(tmp_path / "legacy", valid_manifest(finding="REACHABLE"))
    assert main(["--manifest", str(legacy)]) == 0

    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe-v5"
    report_dir.mkdir(parents=True)
    relay_a = report_dir / "relay" / "lifecycle-a"
    relay_b = report_dir / "relay" / "lifecycle-b"
    relay_a.mkdir(parents=True)
    relay_b.mkdir(parents=True)
    _write_valid_lifecycle_a_relay(relay_a)
    _write_minimal_lifecycle_b_relay(relay_b)
    zed_a = relay_a / "zed-to-agent.bin"
    agent_a = relay_a / "agent-to-zed.bin"
    zed_b = relay_b / "zed-to-agent.bin"
    agent_b = relay_b / "agent-to-zed.bin"
    report = report_dir / "report.md"
    report.write_text("Finding: REACHABLE.\n", encoding="utf-8")

    payload = valid_manifest(finding="REACHABLE")
    payload["zed_launches"] = 2
    payload["relay"] = {"source": "opaque-relay-post-run"}
    resume = _v5_resume_lifecycle()
    resume["lifecycle_a"]["zed_to_agent_sha256"] = _sha256_file(zed_a)
    resume["lifecycle_a"]["agent_to_zed_sha256"] = _sha256_file(agent_a)
    resume["lifecycle_b"]["zed_to_agent_sha256"] = _sha256_file(zed_b)
    resume["lifecycle_b"]["agent_to_zed_sha256"] = _sha256_file(agent_b)
    payload["resume_lifecycle"] = resume
    payload["files"] = {
        "report.md": _sha256_file(report),
        "relay/lifecycle-a/zed-to-agent.bin": _sha256_file(zed_a),
        "relay/lifecycle-a/agent-to-zed.bin": _sha256_file(agent_a),
        "relay/lifecycle-b/zed-to-agent.bin": _sha256_file(zed_b),
        "relay/lifecycle-b/agent-to-zed.bin": _sha256_file(agent_b),
    }
    manifest_path = report_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 0

    def break_match(doc: dict[str, Any]) -> None:
        doc["resume_lifecycle"]["lifecycle_b"]["session_load_exchange"]["request"]["params"]["sessionId"] = "session-b"

    _rewrite(manifest_path, break_match)
    assert main(["--manifest", str(manifest_path)]) == 1


def test_v5_manifest_rejects_wrong_lifecycle_labels(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe-v5"
    report_dir.mkdir(parents=True)
    relay_a = report_dir / "relay" / "lifecycle-a"
    relay_b = report_dir / "relay" / "lifecycle-b"
    relay_a.mkdir(parents=True)
    relay_b.mkdir(parents=True)
    for path, payload in (
        (relay_a / "zed-to-agent.bin", b"a-zed"),
        (relay_a / "agent-to-zed.bin", b"a-agent"),
        (relay_b / "zed-to-agent.bin", b"b-zed"),
        (relay_b / "agent-to-zed.bin", b"b-agent"),
    ):
        path.write_bytes(payload)
    report = report_dir / "report.md"
    report.write_text("Finding: REACHABLE.\n", encoding="utf-8")
    payload = valid_manifest(finding="REACHABLE")
    payload["zed_launches"] = 2
    payload["relay"] = {"source": "opaque-relay-post-run"}
    payload["resume_lifecycle"] = {
        "shared_profile": True,
        "lifecycle_a": {
            "label": "wrong-a",
            "session_new_id": "session-a",
            "zed_to_agent_sha256": _sha256_file(relay_a / "zed-to-agent.bin"),
            "agent_to_zed_sha256": _sha256_file(relay_a / "agent-to-zed.bin"),
        },
        "lifecycle_b": {
            "label": "plan1124-resume",
            "session_load_exchange": {
                "request": {"method": "session/load", "params": {"sessionId": "session-a"}},
                "response": {"result": {}},
            },
            "zed_to_agent_sha256": _sha256_file(relay_b / "zed-to-agent.bin"),
            "agent_to_zed_sha256": _sha256_file(relay_b / "agent-to-zed.bin"),
        },
    }
    payload["files"] = {
        "report.md": _sha256_file(report),
        "relay/lifecycle-a/zed-to-agent.bin": _sha256_file(relay_a / "zed-to-agent.bin"),
        "relay/lifecycle-a/agent-to-zed.bin": _sha256_file(relay_a / "agent-to-zed.bin"),
        "relay/lifecycle-b/zed-to-agent.bin": _sha256_file(relay_b / "zed-to-agent.bin"),
        "relay/lifecycle-b/agent-to-zed.bin": _sha256_file(relay_b / "agent-to-zed.bin"),
    }
    manifest_path = report_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 1


def _build_valid_v5_manifest(tmp_path: Path) -> Path:
    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe-v5"
    relay_a = report_dir / "relay" / "lifecycle-a"
    relay_b = report_dir / "relay" / "lifecycle-b"
    relay_a.mkdir(parents=True)
    relay_b.mkdir(parents=True)
    _write_valid_lifecycle_a_relay(relay_a)
    _write_minimal_lifecycle_b_relay(relay_b)

    za = relay_a / "zed-to-agent.bin"
    aa = relay_a / "agent-to-zed.bin"
    zb = relay_b / "zed-to-agent.bin"
    ab = relay_b / "agent-to-zed.bin"

    rep = report_dir / "report.md"
    rep.write_text("Finding: REACHABLE.\n", encoding="utf-8")

    payload = valid_manifest(finding="REACHABLE")
    payload["zed_launches"] = 2
    payload["relay"] = {"source": "opaque-relay-post-run"}
    resume = _v5_resume_lifecycle()
    resume["lifecycle_a"]["zed_to_agent_sha256"] = _sha256_file(za)
    resume["lifecycle_a"]["agent_to_zed_sha256"] = _sha256_file(aa)
    resume["lifecycle_b"]["zed_to_agent_sha256"] = _sha256_file(zb)
    resume["lifecycle_b"]["agent_to_zed_sha256"] = _sha256_file(ab)
    payload["resume_lifecycle"] = resume
    payload["files"] = {
        "report.md": _sha256_file(rep),
        "relay/lifecycle-a/zed-to-agent.bin": _sha256_file(za),
        "relay/lifecycle-a/agent-to-zed.bin": _sha256_file(aa),
        "relay/lifecycle-b/zed-to-agent.bin": _sha256_file(zb),
        "relay/lifecycle-b/agent-to-zed.bin": _sha256_file(ab),
    }

    manifest_path = report_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def _write_v5_manifest(
    tmp_path: Path,
    payload: dict[str, Any],
    *,
    write_valid_lifecycle_a: bool = True,
    write_valid_lifecycle_b: bool = True,
) -> Path:
    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe-v5"
    relay_a = report_dir / "relay" / "lifecycle-a"
    relay_b = report_dir / "relay" / "lifecycle-b"
    relay_a.mkdir(parents=True)
    relay_b.mkdir(parents=True)
    if write_valid_lifecycle_a:
        _write_valid_lifecycle_a_relay(relay_a)
    else:
        (relay_a / "zed-to-agent.bin").write_bytes(b"a-zed")
        (relay_a / "agent-to-zed.bin").write_bytes(b"a-agent")
    if write_valid_lifecycle_b:
        _write_minimal_lifecycle_b_relay(relay_b)
    else:
        (relay_b / "zed-to-agent.bin").write_bytes(b"b-zed")
        (relay_b / "agent-to-zed.bin").write_bytes(b"b-agent")
    report = report_dir / "report.md"
    finding = str(payload.get("finding", "REACHABLE"))
    reason = payload.get("indeterminate_reason")
    if finding == "INDETERMINATE" and isinstance(reason, str):
        report.write_text(f"Finding: INDETERMINATE / {reason}.\n", encoding="utf-8")
    else:
        report.write_text(f"Finding: {finding}.\n", encoding="utf-8")
    payload.setdefault("files", {})
    payload["files"]["report.md"] = _sha256_file(report)
    for rel in (
        "relay/lifecycle-a/zed-to-agent.bin",
        "relay/lifecycle-a/agent-to-zed.bin",
        "relay/lifecycle-b/zed-to-agent.bin",
        "relay/lifecycle-b/agent-to-zed.bin",
    ):
        payload["files"][rel] = _sha256_file(report_dir / rel)
    resume = payload.get("resume_lifecycle")
    if isinstance(resume, Mapping):
        lifecycle_a = resume.get("lifecycle_a")
        lifecycle_b = resume.get("lifecycle_b")
        if isinstance(lifecycle_a, Mapping):
            lifecycle_a["zed_to_agent_sha256"] = payload["files"]["relay/lifecycle-a/zed-to-agent.bin"]
            lifecycle_a["agent_to_zed_sha256"] = payload["files"]["relay/lifecycle-a/agent-to-zed.bin"]
        if isinstance(lifecycle_b, Mapping):
            lifecycle_b["zed_to_agent_sha256"] = payload["files"]["relay/lifecycle-b/zed-to-agent.bin"]
            lifecycle_b["agent_to_zed_sha256"] = payload["files"]["relay/lifecycle-b/agent-to-zed.bin"]
    manifest_path = report_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def test_v5_rejects_extra_declared_files(tmp_path: Path) -> None:
    manifest_path = _build_valid_v5_manifest(tmp_path)
    assert main(["--manifest", str(manifest_path)]) == 0

    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["files"]["missing-extra.bin"] = "0" * 64
    manifest_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 1


def test_v5_rejects_lifecycle_b_error_certifying_reachable(tmp_path: Path) -> None:
    manifest_path = _build_valid_v5_manifest(tmp_path)
    assert main(["--manifest", str(manifest_path)]) == 0

    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["resume_lifecycle"]["lifecycle_b"]["session_load_exchange"]["response"] = {
        "jsonrpc": "2.0",
        "id": 9,
        "error": {"code": -32601, "message": "method not found"},
    }
    manifest_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 1


def test_v5_indeterminate_without_b_response_fails(tmp_path: Path) -> None:
    payload = valid_manifest(finding="INDETERMINATE")
    payload["zed_launches"] = 2
    payload["relay"] = {"source": "opaque-relay-post-run"}
    resume = _v5_resume_lifecycle(load_response={})
    payload["resume_lifecycle"] = resume
    manifest_path = _write_v5_manifest(tmp_path, payload)
    assert main(["--manifest", str(manifest_path)]) == 1


@pytest.mark.parametrize(
    ("case_id", "mutator", "expected_field"),
    [
        pytest.param(
            "one_launch",
            lambda doc: doc.__setitem__("zed_launches", 1),
            "zed_launches",
            id="v5_negative_one_launch",
        ),
        pytest.param(
            "three_launches",
            lambda doc: doc.__setitem__("zed_launches", 3),
            "zed_launches",
            id="v5_negative_three_launches",
        ),
        pytest.param(
            "shared_profile_false",
            lambda doc: doc["resume_lifecycle"].__setitem__("shared_profile", False),
            "resume_lifecycle.shared_profile",
            id="v5_negative_shared_profile_false",
        ),
        pytest.param(
            "missing_shared_workspace",
            lambda doc: doc["resume_lifecycle"].pop("shared_workspace", None),
            "resume_lifecycle.shared_workspace",
            id="v5_negative_missing_shared_workspace",
        ),
        pytest.param(
            "missing_lifecycle_a_session_id",
            lambda doc: doc["resume_lifecycle"]["lifecycle_a"].pop("session_new_id", None),
            "resume_lifecycle.lifecycle_a.session_new_id",
            id="v5_negative_missing_lifecycle_a_session_id",
        ),
        pytest.param(
            "wrong_lifecycle_b_load_id",
            lambda doc: doc["resume_lifecycle"]["lifecycle_b"]["session_load_exchange"]["request"]["params"].__setitem__(
                "sessionId",
                "session-b",
            ),
            "resume_lifecycle.lifecycle_b.session_load_exchange.request.params.sessionId",
            id="v5_negative_wrong_lifecycle_b_load_id",
        ),
        pytest.param(
            "result_plus_error",
            lambda doc: doc["resume_lifecycle"]["lifecycle_b"]["session_load_exchange"]["response"].update(
                {"result": {}, "error": {"code": -32601, "message": "bad"}}
            ),
            "resume_lifecycle.lifecycle_b.session_load_exchange.response",
            id="v5_negative_result_plus_error",
        ),
        pytest.param(
            "missing_lifecycle_file",
            lambda doc: doc["files"].pop("relay/lifecycle-b/agent-to-zed.bin", None),
            "files",
            id="v5_negative_missing_lifecycle_file",
        ),
        pytest.param(
            "digest_mismatch",
            lambda doc: doc["resume_lifecycle"]["lifecycle_a"].__setitem__("zed_to_agent_sha256", "0" * 64),
            "resume_lifecycle.lifecycle_a.zed_to_agent_sha256",
            id="v5_negative_digest_mismatch",
        ),
        pytest.param(
            "unverified_raw_capture",
            lambda doc: None,
            "relay/lifecycle-a/zed-to-agent.bin",
            id="v5_negative_unverified_raw_capture",
        ),
        pytest.param(
            "failed_message_seam",
            lambda doc: None,
            "resume_lifecycle.lifecycle_a.message_seam",
            id="v5_negative_failed_message_seam",
        ),
    ],
)
def test_v5_negative_matrix_rejects_invalid_resume_manifests(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case_id: str,
    mutator: object,
    expected_field: str,
) -> None:
    payload = valid_manifest(finding="REACHABLE")
    payload["zed_launches"] = 2
    payload["relay"] = {"source": "opaque-relay-post-run"}
    payload["resume_lifecycle"] = _v5_resume_lifecycle()
    write_valid_a = True
    write_valid_b = case_id != "missing_lifecycle_file"
    manifest_path = _write_v5_manifest(
        tmp_path,
        payload,
        write_valid_lifecycle_a=write_valid_a,
        write_valid_lifecycle_b=write_valid_b,
    )
    assert main(["--manifest", str(manifest_path)]) == 0

    if case_id == "unverified_raw_capture":
        relay_path = manifest_path.parent / "relay" / "lifecycle-a" / "zed-to-agent.bin"
        relay_path.write_bytes(b"tampered-bytes\n")
    elif case_id == "failed_message_seam":
        relay_a = manifest_path.parent / "relay" / "lifecycle-a"
        zed = (
            b'{"jsonrpc":"2.0","id":1,"method":"session/new"}\n'
            b'{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"session-a","prompt":[{"type":"text","text":"wrong"}]}}\n'
        )
        agent = (
            b'{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-a"}}\n'
            b'{"jsonrpc":"2.0","id":2,"error":{"code":-32000,"message":"prompt rejected"}}\n'
        )
        (relay_a / "zed-to-agent.bin").write_bytes(zed)
        (relay_a / "agent-to-zed.bin").write_bytes(agent)
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc["files"]["relay/lifecycle-a/zed-to-agent.bin"] = _sha256_file(relay_a / "zed-to-agent.bin")
        doc["files"]["relay/lifecycle-a/agent-to-zed.bin"] = _sha256_file(relay_a / "agent-to-zed.bin")
        doc["resume_lifecycle"]["lifecycle_a"]["zed_to_agent_sha256"] = doc["files"]["relay/lifecycle-a/zed-to-agent.bin"]
        doc["resume_lifecycle"]["lifecycle_a"]["agent_to_zed_sha256"] = doc["files"]["relay/lifecycle-a/agent-to-zed.bin"]
        manifest_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    else:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutator(doc)
        manifest_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    assert main(["--manifest", str(manifest_path)]) == 1
    captured = capsys.readouterr()
    assert expected_field in captured.err


def test_v5_negative_extra_file_baseline_green_preservation(tmp_path: Path) -> None:
    """baseline-green preservation: extra declared files remain rejected."""
    manifest_path = _build_valid_v5_manifest(tmp_path)
    assert main(["--manifest", str(manifest_path)]) == 0
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["files"]["missing-extra.bin"] = "0" * 64
    manifest_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    assert main(["--manifest", str(manifest_path)]) == 1
