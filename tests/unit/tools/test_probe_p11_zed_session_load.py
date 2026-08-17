"""Unit contracts for the version-agnostic P11 Zed session/load re-probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.probe_p11_zed_session_load import (
    ALLOWED_PROBE_SEMANTICS,
    CommandResult,
    Finding,
    IsolationEvidence,
    ProbeError,
    ProbePatchPlan,
    RelayExchange,
    build_acpx_command,
    build_cleanup_remediation,
    build_trust_command,
    capture_acpx_evidence,
    classify_indeterminate_context,
    classify_real_zed_result,
    evaluate_session_load_exchange,
    extract_acpx_archive_capability_payload,
    normal_workspace_source_digest,
    prepare_real_zed_probe,
    validate_isolation_evidence,
    validate_probe_patch_plan,
    verify_normal_operation_isolation,
)


def test_reachable_requires_advertised_capability_and_real_result() -> None:
    """Catches a false positive when a successful response lacks load capability."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {"resume": False}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {"sessionId": "saved-1"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.REACHABLE
    assert result.capability_payload == capability_payload
    assert result.load_exchange == load_exchange


def test_unreachable_preserves_method_not_found_payload() -> None:
    """Catches a classifier that loses the exact live rejection needed for review."""
    capability_payload = {"loadSession": False, "sessionCapabilities": {}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method not found"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.UNREACHABLE
    assert result.load_exchange["response"]["error"] == {"code": -32601, "message": "Method not found"}


def test_incomplete_exchange_is_indeterminate_even_when_advertised() -> None:
    """Catches a claim based solely on initialize when acpx did not invoke load."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.INDETERMINATE
    assert result.load_exchange is None


def test_unadvertised_agent_load_capability_is_internal_indeterminate_without_a_forced_call() -> None:
    """Catches turning the agent's own gate into a claim about Zed."""
    capability_payload = {"sessionCapabilities": {"resume": False}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.INDETERMINATE
    assert result.capability_payload == capability_payload
    assert result.load_exchange is None

    context = classify_indeterminate_context({"capability_payload": capability_payload})

    assert context == {"indeterminate_reason": "INTERNAL_CAPABILITY_UNAVAILABLE", "precondition": None}


def test_acpx_exported_session_capabilities_are_retained_as_live_evidence(tmp_path: Path) -> None:
    """Catches losing the initialized capabilities that acpx itself persisted."""
    archive = tmp_path / "session.json"
    archive.write_text(
        json.dumps(
            {
                "session": {
                    "state": {
                        "agent_capabilities": {"loadSession": False, "sessionCapabilities": {"resume": False}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert extract_acpx_archive_capability_payload(archive) == {
        "loadSession": False,
        "sessionCapabilities": {"resume": False},
    }


def test_raw_acpx_agent_command_uses_slash_normalized_windows_paths() -> None:
    """Catches acpx treating Windows backslashes in a raw agent command as escapes."""
    command = build_acpx_command(
        Path(r"C:\Tools\acpx.cmd"),
        workspace=Path(r"C:\probe workspace"),
        agent=Path(r"D:\agent path\optimus-agent.exe"),
    )

    assert command[-2] == "--agent"
    assert command[-1] == '"D:/agent path/optimus-agent.exe" --workspace-root "C:/probe workspace" --no-auto-start'


def test_temporary_workspace_approval_uses_the_trust_cli_and_has_a_matching_revoke() -> None:
    """Catches a live probe that could create approval state without its paired cleanup command."""
    workspace = Path(r"C:\probe workspace")

    approve = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "approve")
    revoke = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "revoke")

    assert approve[-3:] == ["approve", "--mode", "durable"]
    assert revoke[-1:] == ["revoke"]
    assert approve[:3] == [r"C:\Tools\optimus-trust.exe", "--workspace-root", r"C:\probe workspace"]
    assert approve[:3] == revoke[:3]


def test_acpx_evidence_keeps_protocol_records_but_redacts_secret_aliases_and_free_text() -> None:
    """Catches unsafe persistence of tool streams from the independently authored client."""
    result = CommandResult(
        command=["acpx", "sessions", "new"],
        returncode=1,
        stdout=(
            '{"jsonrpc":"2.0","result":{"agentCapabilities":'
            '{"loadSession":false,"apiKey":"json-secret","credential":"credential-secret"}}}'
        ),
        stderr="OPTIMUS_API_KEY=env-secret Bearer bearer-secret",
    )

    evidence = capture_acpx_evidence(result)

    serialized = json.dumps(evidence)
    assert "json-secret" not in serialized
    assert "credential-secret" not in serialized
    assert "env-secret" not in serialized
    assert "bearer-secret" not in serialized
    assert evidence["capability_payload"] == {
        "loadSession": False,
        "apiKey": "**********",
        "credential": "**********",
    }


def test_cleanup_remediation_is_workspace_scoped_and_contains_no_approval_identifier() -> None:
    """Catches a cleanup-failure path that cannot tell the operator exactly what to undo."""
    remediation = build_cleanup_remediation(
        Path(r"C:\Tools\optimus-trust.exe"), Path(r"C:\probe workspace")
    )

    assert str(remediation[0]).endswith("optimus-trust.exe")
    assert remediation[1:4] == ["--workspace-root", r"C:\probe workspace", "revoke"]
    assert all("approval" not in part.casefold() for part in remediation)


def test_redis_startup_failure_is_a_precondition_with_the_runbook_remediation() -> None:
    """Catches treating a missing Redis dependency as an observation about Zed."""
    context = classify_indeterminate_context(
        {
            "stderr": "optimus-agent: Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL."
        }
    )

    assert context["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert context["precondition"] == {
        "name": "redis",
        "remediation": {
            "runbook": "docs/runbooks/local-live-dependencies.md#5-bounded-session-bound-smoke-redis--gateway-optional-phoenix",
            "command": "optimus-agent --workspace-root <throwaway-workspace> --check-config --strict",
        },
    }


def test_missing_load_exchange_is_an_incomplete_observation_not_a_precondition() -> None:
    """Catches collapsing a clean ACP exchange gap into an infrastructure to-do."""
    context = classify_indeterminate_context({"stderr": "", "stdout_records": []})

    assert context == {"indeterminate_reason": "OBSERVATION_INCOMPLETE", "precondition": None}


REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_SPEC = REPO_ROOT / "src" / "optimus" / "acp" / "spec.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_normal_tree(root: Path) -> None:
    spec = root / "src" / "optimus" / "acp" / "spec.py"
    spec.parent.mkdir(parents=True)
    spec.write_text(REAL_SPEC.read_text(encoding="utf-8"), encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "probe@example.test")
    _git(root, "config", "user.name", "Probe")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")


def _isolation_evidence(**overrides: object) -> IsolationEvidence:
    payload = {
        "normal_agent_load_session_advertised": False,
        "isolated_probe_load_session_advertised": True,
        "normal_source_sha256_before": "a" * 64,
        "normal_source_sha256_after": "a" * 64,
        "isolated_source_root": r"C:\scratch\src",
        "isolated_build_root": r"C:\scratch\build",
        "hermetic_zed_root": r"C:\scratch\zed-home",
        "cleanup_dry_run_verified": True,
        "cleanup_verified": True,
    }
    payload.update(overrides)
    return IsolationEvidence(**payload)  # type: ignore[arg-type]


def _session_load_exchange(
    *,
    result: dict[str, object] | None = None,
    error: dict[str, object] | None = None,
    method: str = "session/load",
) -> RelayExchange:
    response: dict[str, object] = {"jsonrpc": "2.0", "id": 7}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = {} if result is None else result
    return RelayExchange(
        request={"jsonrpc": "2.0", "id": 7, "method": method, "params": {"sessionId": "saved-1"}},
        response=response,
    )


def test_prepare_probe_rejects_normal_workspace_and_extra_patch_surface(tmp_path: Path) -> None:
    normal_root = tmp_path / "normal"
    normal_root.mkdir()
    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(normal_root, normal_root=normal_root, scratch_parent=tmp_path)

    nested = normal_root / "nested"
    nested.mkdir()
    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(nested, normal_root=normal_root, scratch_parent=tmp_path)

    with pytest.raises(ProbeError, match="outside the normal workspace"):
        prepare_real_zed_probe(tmp_path, normal_root=normal_root, scratch_parent=tmp_path)

    plan = ProbePatchPlan(
        changed_paths=("src/optimus/acp/spec.py", "README.md"),
        capability_patch={"loadSession": True},
        load_response={},
    )
    with pytest.raises(ProbeError, match="unexpected patch surface"):
        validate_probe_patch_plan(plan)


def test_validate_probe_patch_plan_accepts_only_allowlisted_semantics() -> None:
    validate_probe_patch_plan(
        ProbePatchPlan(
            changed_paths=("src/optimus/acp/spec.py",),
            capability_patch={"loadSession": True},
            load_response={},
        )
    )
    assert ALLOWED_PROBE_SEMANTICS == {
        "initialize.agentCapabilities.loadSession": True,
        "request.session/load.response.result": {},
    }


def test_isolation_rejects_normal_capability_payload_containing_load_session() -> None:
    evidence = _isolation_evidence(normal_agent_load_session_advertised=True)
    with pytest.raises(ProbeError, match="normal capability payload"):
        validate_isolation_evidence(evidence)
    assert evidence.prelaunch_predicates_pass is False
    assert classify_real_zed_result(_session_load_exchange(), evidence) is Finding.INDETERMINATE


def test_isolation_rejects_missing_before_after_source_digest() -> None:
    evidence = _isolation_evidence(normal_source_sha256_before="", normal_source_sha256_after="")
    with pytest.raises(ProbeError, match="source digest"):
        validate_isolation_evidence(evidence)
    assert evidence.prelaunch_predicates_pass is False


def test_isolation_rejects_unremoved_scratch_roots() -> None:
    evidence = _isolation_evidence(cleanup_verified=False)
    with pytest.raises(ProbeError, match="unremoved scratch"):
        validate_isolation_evidence(evidence)
    assert evidence.all_four_predicates_pass is False
    assert classify_real_zed_result(_session_load_exchange(), evidence) is Finding.INDETERMINATE


def test_source_digest_changes_when_untracked_file_appears(tmp_path: Path) -> None:
    """Paired with the tracked-source digest so a stray untracked file cannot hide."""
    _init_normal_tree(tmp_path)
    before = normal_workspace_source_digest(tmp_path)
    (tmp_path / "stray-untracked.txt").write_text("leak", encoding="utf-8")
    after = normal_workspace_source_digest(tmp_path)
    assert before != after


def test_prepare_probe_excludes_gitignored_secret_like_files(tmp_path: Path) -> None:
    """Catches a blanket copytree that would leak .env/credentials into the isolated probe tree."""
    normal_root = tmp_path / "normal"
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    _init_normal_tree(normal_root)
    (normal_root / ".gitignore").write_text(".env\ncredentials.json\n", encoding="utf-8")
    _git(normal_root, "add", ".gitignore")
    _git(normal_root, "commit", "-m", "ignore secrets")
    (normal_root / ".env").write_text("OPTIMUS_API_KEY=live-secret\n", encoding="utf-8")
    (normal_root / "credentials.json").write_text('{"token": "live-secret"}\n', encoding="utf-8")
    isolated_root = scratch_parent / "probe-src"

    prepare_real_zed_probe(isolated_root, normal_root=normal_root, scratch_parent=scratch_parent)

    listed = {
        item.replace("\\", "/")
        for item in subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=normal_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split("\0")
        if item
    }
    copied = {path.relative_to(isolated_root).as_posix() for path in isolated_root.rglob("*") if path.is_file()}

    assert (isolated_root / ".env").exists() is False
    assert (isolated_root / "credentials.json").exists() is False
    assert (isolated_root / ".gitignore").exists() is True
    assert copied == listed
    assert ".env" not in listed
    assert "credentials.json" not in listed


def test_prepare_probe_patches_only_isolated_spec_and_records_isolation(tmp_path: Path) -> None:
    normal_root = tmp_path / "normal"
    scratch_parent = tmp_path / "scratch"
    scratch_parent.mkdir()
    _init_normal_tree(normal_root)
    isolated_root = scratch_parent / "probe-src"
    before = normal_workspace_source_digest(normal_root)

    preparation = prepare_real_zed_probe(
        isolated_root,
        normal_root=normal_root,
        scratch_parent=scratch_parent,
    )
    isolation = verify_normal_operation_isolation(preparation)

    isolated_spec = Path(preparation.isolated_source_root) / "src" / "optimus" / "acp" / "spec.py"
    normal_spec = normal_root / "src" / "optimus" / "acp" / "spec.py"
    isolated_text = isolated_spec.read_text(encoding="utf-8")
    normal_text = normal_spec.read_text(encoding="utf-8")

    assert isolated_root.resolve() == Path(preparation.isolated_source_root).resolve()
    assert isolated_root.is_relative_to(scratch_parent.resolve())
    assert '"loadSession": True' in isolated_text
    assert "session/load" in isolated_text
    assert '"loadSession": True' not in normal_text
    assert isolation.normal_agent_load_session_advertised is False
    assert isolation.isolated_probe_load_session_advertised is True
    assert isolation.normal_source_sha256_before == before
    assert isolation.normal_source_sha256_after == before
    assert isolation.cleanup_dry_run_verified is True
    assert isolation.prelaunch_predicates_pass is True
    assert isolation.cleanup_verified is False
    validate_isolation_evidence(isolation, require_cleanup=False)


def test_classify_real_zed_result_requires_session_load_request_for_reachable() -> None:
    isolation = _isolation_evidence()
    assert classify_real_zed_result(_session_load_exchange(result={}), isolation) is Finding.REACHABLE
    assert (
        classify_real_zed_result(
            _session_load_exchange(error={"code": -32601, "message": "Method not found"}),
            isolation,
        )
        is Finding.UNREACHABLE
    )
    assert classify_real_zed_result(None, isolation) is Finding.INDETERMINATE
    assert (
        classify_real_zed_result(_session_load_exchange(result={}, method="session/new"), isolation)
        is Finding.INDETERMINATE
    )
