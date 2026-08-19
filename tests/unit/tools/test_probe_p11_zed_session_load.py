"""Unit contracts for the version-agnostic P11 Zed session/load re-probe."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools.probe_p11_zed_session_load import (
    ALLOWED_PROBE_SEMANTICS,
    PLAN1119_RUN_ID,
    AcpxBaselineEvidence,
    CommandResult,
    Finding,
    IsolationEvidence,
    ProbeError,
    ProbePatchPlan,
    RelayExchange,
    ZedInvocation,
    build_acpx_command,
    build_cleanup_remediation,
    build_opaque_relay_command,
    build_real_zed_launch_argv,
    build_trust_command,
    capture_acpx_evidence,
    classify_indeterminate_context,
    classify_live_zed_observation,
    classify_real_zed_result,
    discover_hermetic_zed_invocation,
    evaluate_session_load_exchange,
    exchange_from_relay_extract,
    extract_acpx_archive_capability_payload,
    extract_session_load_from_messages,
    iter_acp_messages,
    main,
    materialize_sanitized_zed_evidence,
    normal_workspace_source_digest,
    prepare_real_zed_probe,
    reconstruct_sanitized_relay_bytes,
    record_probe_command_failure,
    seed_hermetic_zed_settings,
    throwaway_tree_digest,
    validate_acpx_baseline,
    validate_isolation_evidence,
    validate_probe_patch_plan,
    validate_zed_invocation,
    verify_normal_operation_isolation,
    write_isolated_agent_launcher,
    zed_target_already_running,
)
from tools.verify_plan1119_zed_reprobe_evidence import verify_manifest


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
    assert command[command.index("--ttl") + 1] == "60"


def test_raw_acpx_agent_command_prefixes_python_for_py_launcher(tmp_path: Path) -> None:
    """Windows acpx cannot spawn a .py agent directly; that fails as spawn EFTYPE."""
    launcher = tmp_path / "isolated_optimus_agent.py"
    launcher.write_text("raise SystemExit(0)\n", encoding="utf-8")
    command = build_acpx_command(
        Path(r"C:\Tools\acpx.cmd"),
        workspace=tmp_path / "workspace",
        agent=launcher,
    )
    agent_argv = command[-1]
    assert agent_argv.startswith('"') or "python" in agent_argv.casefold()
    assert "isolated_optimus_agent.py" in agent_argv
    assert "--workspace-root" in agent_argv
    assert not agent_argv.lstrip('"').startswith(str(launcher).replace("\\", "/"))

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


def test_throwaway_tree_digest_does_not_require_git(tmp_path: Path) -> None:
    """Isolated probe copies have no .git; identity recording must not call git ls-files there."""
    tree = tmp_path / "probe-source"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    digest = throwaway_tree_digest(tree)
    assert len(digest) == 64
    (tree / "src" / "a.py").write_text("print(2)\n", encoding="utf-8")
    assert throwaway_tree_digest(tree) != digest


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


HERMETIC_ROOT = Path(r"C:\scratch\zed-home")


def _valid_invocation() -> ZedInvocation:
    return ZedInvocation(
        argv=("C:\\Tools\\Zed.exe", "--isolated-user-data", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )


def test_real_zed_launch_rejects_ambient_profile_and_missing_discovery() -> None:
    invocation = ZedInvocation(argv=("Zed.exe",), user_data_root=None, discovered_from="")
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        validate_zed_invocation(invocation, hermetic_root=Path(r"C:\scratch\zed-home"))


def test_user_data_path_outside_hermetic_root_is_rejected() -> None:
    invocation = ZedInvocation(
        argv=("Zed.exe", "--isolated-user-data", r"C:\other\profile"),
        user_data_root=r"C:\other\profile",
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="hermetic root"):
        validate_zed_invocation(invocation, hermetic_root=HERMETIC_ROOT)


def test_ambient_profile_user_data_is_rejected() -> None:
    ambient = Path(r"C:\Users\me\AppData\Roaming")
    invocation = ZedInvocation(
        argv=("Zed.exe", "--isolated-user-data", str(ambient)),
        user_data_root=str(ambient),
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        validate_zed_invocation(
            invocation,
            hermetic_root=ambient,
            ambient_profile_roots=(ambient,),
        )


def test_hermetic_root_under_temp_is_not_treated_as_ambient_profile(tmp_path: Path) -> None:
    hermetic = tmp_path / "zed-home"
    hermetic.mkdir()
    invocation = ZedInvocation(
        argv=("Zed.exe", "--user-data-dir", str(hermetic)),
        user_data_root=str(hermetic),
        discovered_from="zed --help",
    )
    validate_zed_invocation(
        invocation,
        hermetic_root=hermetic,
        ambient_profile_roots=(tmp_path.parent, tmp_path.parent / "AppData" / "Roaming"),
    )


@pytest.mark.skipif(sys.platform != "win32", reason="default Zed data directory layout is Windows-specific")
def test_default_zed_data_directory_is_rejected_even_when_nested() -> None:
    zed_default = Path(r"C:\Users\me\AppData\Local\Zed")
    nested = zed_default / "probe-home"
    invocation = ZedInvocation(
        argv=("Zed.exe", "--user-data-dir", str(nested)),
        user_data_root=str(nested),
        discovered_from="zed --help",
    )
    with pytest.raises(ProbeError, match="ambient profile"):
        validate_zed_invocation(
            invocation,
            hermetic_root=nested,
            ambient_profile_roots=(zed_default,),
        )


def test_discovery_uses_help_text_flag_not_historical_default() -> None:
    invocation = discover_hermetic_zed_invocation(
        executable=Path(r"C:\Tools\Zed.exe"),
        version_output="Zed 1.99.0",
        help_output="  --isolated-user-data <path>  Bind editor user data to this directory\n",
        executable_sha256="a" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.discovered_from == "zed --help"
    assert "--isolated-user-data" in invocation.argv
    assert "--user-data-dir" not in invocation.argv
    assert invocation.user_data_root == str(HERMETIC_ROOT.resolve())
    assert invocation.environment_bind == ()
    validate_zed_invocation(invocation, hermetic_root=HERMETIC_ROOT)


def test_discovery_prefers_app_binary_from_version_path(tmp_path: Path) -> None:
    app = tmp_path / "Zed.exe"
    cli = tmp_path / "bin" / "Zed.exe"
    cli.parent.mkdir(parents=True)
    app.write_bytes(b"app")
    cli.write_bytes(b"cli")
    invocation = discover_hermetic_zed_invocation(
        executable=cli,
        version_output=f"Zed 1.15.0 deadbeef  – \\\\?\\{app}",
        help_output="  --user-data-dir <path>\n",
        executable_sha256="b" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.argv[0] == str(app)
    assert invocation.environment_bind == ()
    assert "--user-data-dir" in invocation.argv


def test_discovery_selects_sibling_app_when_version_omits_path(tmp_path: Path) -> None:
    """Force the ``_sibling_zed_app_binary`` tier: no path in version_output."""
    install = tmp_path / "Programs" / "Zed"
    app = install / "Zed.exe"
    cli = install / "bin" / "Zed.exe"
    cli.parent.mkdir(parents=True)
    app.write_bytes(b"app")
    cli.write_bytes(b"cli")
    invocation = discover_hermetic_zed_invocation(
        executable=cli,
        version_output="Zed 1.15.0 e17dc4f9d50db73a458b64dcce50ecd4878b98a3",
        help_output="  --user-data-dir <path>\n",
        executable_sha256="c" * 64,
        hermetic_root=HERMETIC_ROOT,
    )
    assert invocation.argv[0] == str(app.resolve())
    assert invocation.environment_bind == ()
    assert "--user-data-dir" in invocation.argv


def test_launch_argv_omits_cli_only_flags_absent_from_app_help() -> None:
    """App ``Zed.exe`` help omits ``--new``/``--wait``/``--foreground``; CLI help includes them.

    Shot 2 passed CLI-only flags to the app binary and exited 2 with no window.
    """
    invocation = ZedInvocation(
        argv=(r"C:\Programs\Zed\Zed.exe", "--user-data-dir", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )
    app_help = (
        "Usage: Zed.exe [OPTIONS] [PATHS_OR_URLS]...\n"
        "      --user-data-dir <DIR>\n"
        "  -h, --help\n"
    )
    workspace = Path(r"C:\scratch\zed-workspace")
    argv = build_real_zed_launch_argv(invocation, workspace=workspace, launch_help=app_help)
    assert argv == (
        r"C:\Programs\Zed\Zed.exe",
        "--user-data-dir",
        str(HERMETIC_ROOT),
        str(workspace),
    )
    assert "--new" not in argv
    assert "--wait" not in argv
    assert "--foreground" not in argv


def test_launch_argv_keeps_cli_flags_when_launch_help_lists_them() -> None:
    invocation = ZedInvocation(
        argv=(r"C:\Programs\Zed\bin\Zed.exe", "--user-data-dir", str(HERMETIC_ROOT)),
        user_data_root=str(HERMETIC_ROOT),
        discovered_from="zed --help",
    )
    cli_help = "  --foreground\n  -n, --new\n  -w, --wait\n  --user-data-dir <DIR>\n"
    workspace = Path(r"C:\scratch\zed-workspace")
    argv = build_real_zed_launch_argv(invocation, workspace=workspace, launch_help=cli_help)
    assert "--foreground" in argv
    assert "--new" in argv
    assert "--wait" in argv
    assert argv[-1] == str(workspace)


def test_launch_log_excerpt_runs_through_evidence_sanitizer(tmp_path: Path) -> None:
    from tools.probe_p11_zed_session_load import _launch_log_excerpt

    canary = "sk-" + ("a" * 16)
    log_path = tmp_path / "zed-launch.log"
    log_path.write_text(f"startup wire-dump {canary} trailing\n", encoding="utf-8", newline="\n")
    excerpt = _launch_log_excerpt(log_path)
    assert canary not in excerpt
    assert "wire-dump" in excerpt
    assert "trailing" in excerpt


def test_discovery_fails_closed_when_help_omits_user_data_binding() -> None:
    with pytest.raises(ProbeError, match="current-version hermetic invocation"):
        discover_hermetic_zed_invocation(
            executable=Path(r"C:\Tools\Zed.exe"),
            version_output="Zed 1.99.0",
            help_output="  --foreground\n  --version\n",
            executable_sha256="a" * 64,
            hermetic_root=HERMETIC_ROOT,
        )


def test_classification_consumes_sanitized_relay_extract_not_project_client() -> None:
    extract = {
        "source": "opaque-relay-post-run",
        "zed_to_agent_sha256": "a" * 64,
        "agent_to_zed_sha256": "b" * 64,
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    exchange = exchange_from_relay_extract(extract)
    assert exchange is not None
    assert exchange.request["method"] == "session/load"
    isolation = _isolation_evidence()
    assert classify_live_zed_observation(
        exchange,
        isolation,
        _valid_invocation(),
        already_running_zed=False,
        relay_failed=False,
        cleanup_roots_empty=True,
    ) is Finding.REACHABLE


def test_classification_rejects_project_authored_client_call() -> None:
    extract = {
        "source": "project-acp-client",
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load"},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    with pytest.raises(ProbeError, match="sanitized post-run relay extract"):
        exchange_from_relay_extract(extract)


def test_absent_descriptor_already_running_relay_failure_and_nonempty_cleanup_prevent_verdict() -> None:
    isolation = _isolation_evidence()
    exchange = _session_load_exchange()
    missing = ZedInvocation(argv=("Zed.exe",), user_data_root=None, discovered_from="")
    assert (
        classify_live_zed_observation(
            exchange, isolation, missing, already_running_zed=False, relay_failed=False, cleanup_roots_empty=True
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=True,
            relay_failed=False,
            cleanup_roots_empty=True,
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=False,
            relay_failed=True,
            cleanup_roots_empty=True,
        )
        is Finding.INDETERMINATE
    )
    assert (
        classify_live_zed_observation(
            exchange,
            isolation,
            _valid_invocation(),
            already_running_zed=False,
            relay_failed=False,
            cleanup_roots_empty=False,
        )
        is Finding.INDETERMINATE
    )
    assert zed_target_already_running(("notepad.exe", "Zed.exe")) is True
    assert zed_target_already_running(("notepad.exe",)) is False


def test_opaque_relay_command_uses_custody_relay_not_project_client() -> None:
    command = build_opaque_relay_command(
        capture_root=Path(r"C:\scratch\capture"),
        run_id="run-1",
        child_executable=Path(r"C:\scratch\optimus-agent.exe"),
        invocation=_valid_invocation(),
    )
    joined = " ".join(command)
    assert "plan117_custody_relay.py" in joined
    assert "--child-executable" in command
    assert "acpx" not in joined.casefold()


def test_opaque_relay_command_preserves_explicit_child_args_without_repeating_executable(
    tmp_path: Path,
) -> None:
    capture_root = tmp_path / "cap"
    capture_root.mkdir(parents=True)
    run_id = "run-1"
    launcher = tmp_path / "isolated_launcher.py"
    launcher.write_text("# launcher\n", encoding="utf-8")
    workspace = tmp_path / "zed-workspace"
    workspace.mkdir()

    explicit_child_args = [
        str(launcher),
        "--workspace-root",
        str(workspace),
        "--no-auto-start",
    ]
    command = build_opaque_relay_command(
        capture_root=capture_root,
        run_id=run_id,
        child_executable=Path(sys.executable),
        invocation=_valid_invocation(),
        child_args=explicit_child_args,
    )

    marker = command.index("--")
    after = command[marker + 1 :]
    assert after == explicit_child_args

    exe_marker = command.index("--child-executable")
    child_executable_at_cli = Path(command[exe_marker + 1])

    expected_exe = Path(sys.executable).resolve()
    assert child_executable_at_cli.resolve() == expected_exe

    # The relay contract resolves to [sys.executable, *child_args] exactly.
    resolved_child_argv = [str(child_executable_at_cli), *after]
    non_flag_items = [item for item in resolved_child_argv if not str(item).startswith("--")]
    non_flag_paths = [Path(item).resolve() for item in non_flag_items]
    assert non_flag_paths.count(expected_exe) == 1
    assert Path(resolved_child_argv[1]).resolve() == launcher.resolve()


def test_acpx_baseline_fails_closed_without_isolated_load_session() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"sessionCapabilities": {}},
        origin_a_launches=0,
    )
    with pytest.raises(ProbeError, match="loadSession"):
        validate_acpx_baseline(evidence)


def test_acpx_baseline_accepts_isolated_advertisement_without_zed_claim() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
    )
    validate_acpx_baseline(evidence)


def test_acpx_baseline_accepts_advertisement_without_live_set_mode_exchange() -> None:
    """Optimus has no session/set_mode; baseline must not require that CLI path."""
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
        session_load_exchange=None,
    )
    validate_acpx_baseline(evidence)


def test_acpx_baseline_rejects_non_empty_live_load_result() -> None:
    evidence = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable=r"C:\Tools\acpx.cmd",
        acpx_sha256="a" * 64,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
        session_load_exchange={
            "request": {"method": "session/load"},
            "response": {"result": {"sessionId": "x"}},
        },
    )
    with pytest.raises(ProbeError, match="session/load with"):
        validate_acpx_baseline(evidence)


def test_real_zed_cli_mode_does_not_launch(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe"
    assert main(["--mode", "real-zed", "--report-dir", str(report_dir), str(tmp_path)]) == 1


def test_preflight_failure_retains_sanitized_command_stderr() -> None:
    result: dict[str, object] = {}
    record_probe_command_failure(
        result,
        ProbeError(
            "acpx_new_session",
            "exit=1: captured command evidence",
            CommandResult(
                command=["acpx", "sessions", "new"],
                returncode=1,
                stdout="",
                stderr="agent exited: Redis is not reachable\nOPTIMUS_API_KEY=live-secret\n",
            ),
        ),
    )
    assert result["failure"]["stage"] == "acpx_new_session"
    evidence = result["acpx_failure"]
    assert evidence["exit_code"] == 1
    assert "Redis is not reachable" in str(evidence["stderr"])
    assert "live-secret" not in json.dumps(result)


def test_baseline_empty_load_failure_keeps_stdout_records() -> None:
    result: dict[str, object] = {}
    record_probe_command_failure(
        result,
        ProbeError(
            "acpx_baseline",
            "isolated probe must answer session/load with {}",
            CommandResult(
                command=["acpx", "set-mode", "x"],
                returncode=1,
                stdout=(
                    '{"jsonrpc":"2.0","id":null,"error":{"code":-32603,'
                    '"message":"Persistent ACP session missing","data":{"detailCode":"SESSION_RESUME_REQUIRED"}}}\n'
                ),
                stderr="",
            ),
        ),
    )
    assert result["acpx_failure"]["stdout_records"]
    assert "SESSION_RESUME_REQUIRED" in json.dumps(result["acpx_failure"])


def test_iter_acp_messages_parses_ndjson_and_pairs_session_load() -> None:
    request = {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "s1"}}
    response = {"jsonrpc": "2.0", "id": 7, "result": {}}
    zed_bytes = (json.dumps(request) + "\n").encode("utf-8")
    agent_bytes = (json.dumps(response) + "\n").encode("utf-8")
    exchange = extract_session_load_from_messages(iter_acp_messages(zed_bytes), iter_acp_messages(agent_bytes))
    assert exchange is not None
    assert exchange["request"]["method"] == "session/load"
    assert exchange["response"]["result"] == {}
    reconstructed = reconstruct_sanitized_relay_bytes(iter_acp_messages(zed_bytes))
    assert b"session/load" in reconstructed


def test_iter_acp_messages_parses_content_length_frames() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
    framed = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    messages = iter_acp_messages(framed)
    assert messages[0]["method"] == "initialize"


def test_seed_hermetic_settings_and_launcher_stay_under_scratch(tmp_path: Path) -> None:
    hermetic = tmp_path / "zed-home"
    user_data_dir = tmp_path / "user-data"
    launcher = write_isolated_agent_launcher(tmp_path / "probe-build", tmp_path / "probe-source")
    settings = seed_hermetic_zed_settings(
        user_data_dir,
        relay_command="python",
        relay_args=["relay.py", "--capture-root", str(tmp_path / "capture")],
    )
    assert launcher.is_relative_to(tmp_path)
    assert settings == (user_data_dir / "config" / "settings.json").resolve()
    assert settings.is_relative_to(user_data_dir)
    assert not (hermetic / "settings.json").exists()
    assert not (user_data_dir / "Zed" / "settings.json").exists()
    payload = json.loads(settings.read_text(encoding="utf-8"))
    assert payload["agent_servers"]["optimus"]["command"] == "python"
    assert "loadSession" not in settings.read_text(encoding="utf-8")
    assert "probe-source" in launcher.read_text(encoding="utf-8")


def test_seed_hermetic_settings_targets_custom_data_dir_config(tmp_path: Path) -> None:
    """Pinned Zed 1.15.0 reads <user-data-dir>/config/settings.json under --user-data-dir."""
    user_data_dir = tmp_path / "user-data"
    settings = seed_hermetic_zed_settings(
        user_data_dir,
        relay_command="python",
        relay_args=["relay.py"],
    )
    assert settings.name == "settings.json"
    assert settings.parent.name == "config"
    assert settings.parent.parent == user_data_dir.resolve()
    assert not (user_data_dir / "Zed" / "settings.json").exists()
    assert not (tmp_path / "AppData").exists()


COMMIT = "cfaffbebf184cd7e08f15749ce5aaff414991ec1"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
RAW_CAPTURE_CANARY = b"RAW_CAPTURE_CANARY=sk-live-not-for-disk"
RELAY_CHILD_STDERR_CANARY = "OPTIMUS_API_KEY=sk-child-stderr-canary-not-for-disk"
RELAY_CHILD_STDERR_RAW_SCRATCH_PATH = "C:/raw-scratch/relay-child-stderr.txt"
PLAN_1124_REPORT_NAME = "plan-11-24-zed-guided-session-load-probe"
PLAN_1124_V3_REPORT_NAME = "plan-11-24-zed-guided-session-load-probe-v3"
APPROVED_REAL_ZED_PREFIX = [
    "uv",
    "run",
    "--frozen",
    "python",
    "tools/probe_p11_zed_session_load.py",
]
PLAN1124_EXPECTED_CONSEQUENCES = {
    "REACHABLE": (
        "The tested current Zed issued `session/load`; a separately scoped `P11-FU-1` "
        "durable ACP session-store/handler design is justified, but this plan does not implement it."
    ),
    "UNREACHABLE": (
        "A captured Zed protocol/method error requires an operator disposition for the "
        "Zed-resume lane rather than presumed durable-store implementation."
    ),
    "INDETERMINATE": (
        "The named missing precondition/observation remains; no implementation or disposition "
        "follows automatically."
    ),
}


def reachable_result() -> dict[str, object]:
    """Complete sanitizer-safe REACHABLE fixture for verifier-valid materialization."""
    exchange = {
        "request": {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "session/load",
            "params": {"sessionId": "saved-1"},
        },
        "response": {"jsonrpc": "2.0", "id": 7, "result": {}},
    }
    return {
        "schema": "plan-11-19-zed-session-load-reprobe-v1",
        "recorded_at_utc": "2026-08-18T12:00:00+00:00",
        "commit": COMMIT,
        "finding": "REACHABLE",
        "indeterminate_reason": None,
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
            "cleanup_verified": True,
        },
        "capability_payload": {"loadSession": True, "sessionCapabilities": {}},
        "relay": {
            "source": "opaque-relay-post-run",
            "zed_to_agent_sha256": SHA_A,
            "agent_to_zed_sha256": SHA_B,
        },
        "captured_exchange": exchange,
        "origin_a_launches": 0,
        "zed_launches": 1,
        "_sanitized_relay_zed": b"should-not-be-serialized",
        "_secret_sidecar_key": "must-not-reach-disk",
    }


def _guided_report_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    monkeypatch.setattr("tools.probe_p11_zed_session_load.REPORTS_ROOT", reports_root)
    return reports_root / PLAN_1124_REPORT_NAME


def _paired_sanitized_relay_bytes() -> tuple[bytes, bytes]:
    request = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "session/load",
        "params": {"sessionId": "saved-1"},
    }
    response = {"jsonrpc": "2.0", "id": 7, "result": {}}
    return (
        reconstruct_sanitized_relay_bytes([request]),
        reconstruct_sanitized_relay_bytes([response]),
    )


def _scan_tree_for_canary(root: Path) -> list[str]:
    hits: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if RAW_CAPTURE_CANARY in payload or b"must-not-reach-disk" in payload:
            hits.append(path.as_posix())
    return hits


def test_nonempty_sanitized_relay_bundle_passes_existing_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()
    raw_zed = zed_to_agent + RAW_CAPTURE_CANARY
    raw_agent = agent_to_zed + RAW_CAPTURE_CANARY
    sanitized_zed = reconstruct_sanitized_relay_bytes(iter_acp_messages(raw_zed))
    sanitized_agent = reconstruct_sanitized_relay_bytes(iter_acp_messages(raw_agent))

    manifest = materialize_sanitized_zed_evidence(
        report_dir=report_dir,
        result=reachable_result(),
        zed_to_agent=sanitized_zed,
        agent_to_zed=sanitized_agent,
    )

    verify_manifest(manifest)
    published_zed = (report_dir / "relay" / "zed-to-agent.bin").read_bytes()
    published_agent = (report_dir / "relay" / "agent-to-zed.bin").read_bytes()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert published_zed
    assert published_agent
    assert published_zed == sanitized_zed
    assert published_agent == sanitized_agent
    assert payload["relay"]["zed_to_agent_sha256"] == hashlib.sha256(published_zed).hexdigest()
    assert payload["relay"]["agent_to_zed_sha256"] == hashlib.sha256(published_agent).hexdigest()
    report_text = (report_dir / "report.md").read_text(encoding="utf-8")
    assert "Plan 11.24" in report_text
    assert "REACHABLE" in report_text
    assert "Plan 11.19" in report_text
    assert PLAN1124_EXPECTED_CONSEQUENCES[Finding.REACHABLE.value] in report_text
    assert PLAN1124_EXPECTED_CONSEQUENCES[Finding.UNREACHABLE.value] not in report_text
    assert PLAN1124_EXPECTED_CONSEQUENCES[Finding.INDETERMINATE.value] not in report_text
    assert _scan_tree_for_canary(report_dir) == []
    assert RAW_CAPTURE_CANARY not in json.dumps(payload).encode("utf-8")


def test_materialize_rejects_existing_target_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    report_dir.mkdir()
    sentinel = report_dir / "preexisting.txt"
    sentinel.write_text("keep-me", encoding="utf-8")
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()

    with pytest.raises(ProbeError, match="existing"):
        materialize_sanitized_zed_evidence(
            report_dir=report_dir,
            result=reachable_result(),
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert sentinel.read_text(encoding="utf-8") == "keep-me"
    assert not (report_dir / "manifest.json").exists()
    assert not (report_dir / "relay").exists()


def test_materialize_rejects_target_outside_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _guided_report_dir(tmp_path, monkeypatch)
    outside = tmp_path / "not-reports" / PLAN_1124_REPORT_NAME
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()

    with pytest.raises(ProbeError, match="reports"):
        materialize_sanitized_zed_evidence(
            report_dir=outside,
            result=reachable_result(),
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert not outside.exists()


def test_materialize_cleanup_failed_result_leaves_no_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = _guided_report_dir(tmp_path, monkeypatch)
    zed_to_agent, agent_to_zed = _paired_sanitized_relay_bytes()
    result = reachable_result()
    isolation = dict(result["isolation"])  # type: ignore[arg-type]
    isolation["cleanup_verified"] = False
    result["isolation"] = isolation
    result["finding"] = "INDETERMINATE"
    result["indeterminate_reason"] = "CLEANUP_UNVERIFIED"

    with pytest.raises(ProbeError, match="cleanup"):
        materialize_sanitized_zed_evidence(
            report_dir=report_dir,
            result=result,
            zed_to_agent=zed_to_agent,
            agent_to_zed=agent_to_zed,
        )

    assert not report_dir.exists()


def test_real_zed_mode_requires_report_dir() -> None:
    from tools.probe_p11_zed_session_load import _parse_args

    with pytest.raises(SystemExit):
        _parse_args(["--mode", "real-zed", "C:/tmp/ws"])


def test_approved_real_zed_command_parser_requires_report_dir() -> None:
    from tools.probe_p11_zed_session_load import _parse_args

    for mode in ("preflight", "real-zed"):
        with pytest.raises(SystemExit):
            _parse_args(["--mode", mode, "C:/tmp/ws"])


def test_approved_real_zed_command_round_trips_through_same_parser() -> None:
    from tools.probe_p11_zed_session_load import _parse_args, build_approved_real_zed_command

    workspace = "C:/tmp/p11-24-zed-guided-probe-v3"
    report_dir = f"reports/{PLAN_1124_V3_REPORT_NAME}"
    parsed = _parse_args(
        [
            "--mode",
            "preflight",
            "--zed-launch-timeout-seconds",
            "900",
            "--report-dir",
            report_dir,
            workspace,
        ]
    )
    command = build_approved_real_zed_command(parsed)
    assert command[:5] == APPROVED_REAL_ZED_PREFIX
    remainder = command[5:]
    assert remainder.count("--mode") == 1
    assert remainder.count("--zed-launch-timeout-seconds") == 1
    assert remainder.count("--report-dir") == 1
    assert "--launch-approval-id" not in command
    assert all("p996_" not in part for part in command)
    round_tripped = _parse_args(remainder)
    assert round_tripped.mode == "real-zed"
    assert round_tripped.zed_launch_timeout_seconds == 900.0
    assert Path(round_tripped.report_dir) == Path(report_dir)
    assert Path(round_tripped.workspace) == Path(workspace)


@pytest.mark.parametrize(
    ("finding", "reason"),
    [
        ("REACHABLE", None),
        ("UNREACHABLE", None),
        ("INDETERMINATE", "OBSERVATION_INCOMPLETE"),
    ],
)
def test_plan1124_report_text_emits_exact_outcome_consequence(
    finding: str, reason: str | None
) -> None:
    from tools.probe_p11_zed_session_load import _plan1124_report_text

    expected = PLAN1124_EXPECTED_CONSEQUENCES[finding]
    text = _plan1124_report_text(
        {
            "finding": finding,
            "recorded_at_utc": "2026-08-19T00:00:00+00:00",
            "commit": COMMIT,
            "indeterminate_reason": reason,
        }
    )
    assert "## Outcome consequence" in text
    assert expected in text
    assert text.count("| Result | Consequence |") == 1
    for other_finding, other_text in PLAN1124_EXPECTED_CONSEQUENCES.items():
        if other_finding != finding:
            assert other_text not in text


def test_unknown_finding_outcome_consequence_fails_closed() -> None:
    from tools.probe_p11_zed_session_load import _plan1124_report_text

    with pytest.raises(ProbeError, match="outcome consequence"):
        _plan1124_report_text(
            {
                "finding": "NOT_A_VERDICT",
                "recorded_at_utc": "2026-08-19T00:00:00+00:00",
                "commit": COMMIT,
            }
        )


def test_agent_protocol_drive_delegates_all_protocol_traffic_to_acpx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)
    calls: list[list[str]] = []
    mode = {"value": "ok"}

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        calls.append(command)
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-1] == "new":
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            return CommandResult(command, 2, _agent_protocol_prompt_stdout(), "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            archive = command[-1]
            if not str(archive).endswith("session.json"):
                raise AssertionError(f"unexpected export archive path: {archive}")
            return CommandResult(command, 0, "", "")
        if len(command) >= 2 and command[-2:] == ["sessions", "import"]:
            archive = command[-1]
            if not str(archive).endswith("session.json"):
                raise AssertionError(f"unexpected import archive path: {archive}")
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            if mode["value"] == "ok":
                stdout = _agent_protocol_load_stdout()
            else:
                stdout = _agent_protocol_load_stdout(wrong_session=True)
            return CommandResult(command, 0, stdout, "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["zed_launches"] == 0
    assert result["origin_a_launches"] == 0
    assert result["no_gateway_path_established"] is True

    acpx = tmp_path / "acpx.cmd"
    expected_prefix = [
        str(acpx),
        "--format",
        "json",
        "--json-strict",
        "--no-terminal",
        "--auth-policy",
        "skip",
        "--deny-all",
        "--allowed-tools",
        "",
    ]
    assert any(call[: len(expected_prefix)] == expected_prefix for call in calls)
    assert any(call[-2:] == ["sessions", "new"] for call in calls)
    assert any(len(call) >= 2 and call[-2] == "exec" for call in calls)
    assert any(len(call) >= 4 and call[-4:-1] == ["sessions", "export", "--output"] for call in calls)
    assert any(len(call) >= 3 and call[-3:-1] == ["sessions", "import"] for call in calls)
    assert any(call[-1] == "status" for call in calls)

    serialized_calls = json.dumps(calls)
    assert '"session/new"' not in serialized_calls
    assert "jsonrpc" not in " ".join(" ".join(call) for call in calls)
    assert "Content-Length" not in " ".join(" ".join(call) for call in calls)
    driver_source = Path(probe.__file__).read_text(encoding="utf-8")
    driver_body = driver_source.split("def run_plan1124_agent_protocol_drive", 1)[1].split(
        "def _classify_resume_lifecycle", 1
    )[0]
    for forbidden in ("NdjsonSubprocessSession", "Content-Length"):
        assert forbidden not in driver_body

    sidecar = json.loads(Path(str(result["sidecar"])).read_text(encoding="utf-8"))
    assert sidecar["prompt_attempt"] == {"exit_code": 2, "prompt_failed": True}
    assert "stdout_records" not in json.dumps(sidecar)
    assert str(acpx) not in json.dumps(sidecar)
    report_text = (report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md").read_text(encoding="utf-8")
    assert "## Typed reconstruction record" in report_text
    parsed = probe.parse_establishing_report_v2(report_text.encode("utf-8"))
    assert parsed["establishing_disposition"] == probe.PLAN1124_ESTABLISHING_OK


def test_agent_protocol_drive_requires_erroring_prompt_and_matching_saved_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """baseline-green preservation: successful prompt or mismatched load must reject."""
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)
    scenario = {"value": "success-prompt"}

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-1] == "new":
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            if scenario["value"] == "success-prompt":
                stdout = _agent_protocol_prompt_stdout(include_error=False, result_ok=True)
            else:
                stdout = _agent_protocol_prompt_stdout()
            return CommandResult(command, 0 if scenario["value"] == "success-prompt" else 2, stdout, "")
        if command[-1] == "export":
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            if scenario["value"] == "mismatch":
                stdout = _agent_protocol_load_stdout(wrong_session=True)
            else:
                stdout = _agent_protocol_load_stdout()
            return CommandResult(command, 0, stdout, "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    first = probe.run_plan1124_agent_protocol_drive(parent)
    assert first["no_gateway_path_established"] is False
    assert first["indeterminate_reason"] == "PRECONDITION_UNMET"

    scenario["value"] = "mismatch"
    second = probe.run_plan1124_agent_protocol_drive(parent)
    assert second["no_gateway_path_established"] is False
    assert second["indeterminate_reason"] == "PRECONDITION_UNMET"


def _agent_protocol_drive_common_stubs(
    probe: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    report_root: Path,
    isolated_source: str | None = None,
) -> Path:
    parent = tmp_path / "parent"
    parent.mkdir()
    launcher = tmp_path / "isolated_optimus_agent.py"
    launcher.write_text("raise SystemExit(0)\n", encoding="utf-8")
    acpx = tmp_path / "acpx.cmd"
    acpx.write_text("@echo off\n", encoding="utf-8")
    trust = tmp_path / "optimus-trust.exe"
    trust.write_text("binary\n", encoding="utf-8")
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe, "verify_establishing_execution_surface", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_git_head", lambda _repo: COMMIT)
    files = [{"path": path, "blob_sha256": SHA_A} for path in probe.ESTABLISHING_EXECUTION_GIT_PATHS]
    canonical_obj = {"schema": probe.APPLICABILITY_MANIFEST_SCHEMA, "files": files}
    canonical_bytes = json.dumps(
        canonical_obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    stub_manifest = {
        "schema": probe.APPLICABILITY_MANIFEST_SCHEMA,
        "files": files,
        "manifest_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
    }
    monkeypatch.setattr(probe, "build_applicability_manifest", lambda *_a, **_k: stub_manifest)
    monkeypatch.setattr(
        probe,
        "resolve_acpx_identities",
        lambda _path, *, cwd, env: {
            "version": "0.0.test",
            "command_sha256": SHA_A,
            "cli_js_sha256": SHA_B,
        },
    )
    monkeypatch.setattr(
        probe,
        "_resolve_python_identity",
        lambda: {"python_version": "3.14.0", "python_executable_sha256": SHA_B},
    )
    monkeypatch.setattr(
        probe,
        "_resolve_trust_executable_identity",
        lambda _repo: {"trust_executable_sha256": SHA_C},
    )
    monkeypatch.setattr(
        probe,
        "_resolve_isolated_identity",
        lambda _repo, isolated_source_root=None: {
            "isolated_launcher_canonical_sha256": SHA_A,
            "isolated_launcher_raw_sha256": SHA_A,
            "isolated_patched_spec_sha256": SHA_B,
        },
    )
    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": isolated_source or str(tmp_path / "probe-source"),
                "isolated_build_root": str(tmp_path),
                "hermetic_zed_root": str(tmp_path / "zed-home"),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": isolated_source or str(tmp_path / "probe-source"),
                "isolated_build_root": str(tmp_path),
                "hermetic_zed_root": str(tmp_path / "zed-home"),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: launcher)
    monkeypatch.setattr(probe, "_resolve_acpx", lambda: acpx)
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: trust)
    monkeypatch.setattr(probe, "_file_sha256", lambda _p: SHA_A)
    monkeypatch.setattr(probe, "_isolated_environment", lambda _home: {"HOME": str(_home)})
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    return parent


def _agent_protocol_prompt_stdout(*, session_id: str = "session-a", include_request: bool = True, include_error: bool = True, error_code: int = -32000, result_ok: bool = False, result_and_error: bool = False, wrong_message: bool = False, wrong_session: bool = False, second_prompt: bool = False) -> str:
    import tools.probe_p11_zed_session_load as probe

    lines: list[str] = []
    sid = "session-b" if wrong_session else session_id
    text = "wrong message" if wrong_message else probe.PLAN1124_EXEC_MESSAGE
    if include_request:
        lines.append(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/prompt",
                    "params": {"sessionId": sid, "prompt": [{"type": "text", "text": text}]},
                }
            )
        )
        if second_prompt:
            lines.append(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "session/prompt",
                        "params": {"sessionId": sid, "prompt": [{"type": "text", "text": text}]},
                    }
                )
            )
    if result_and_error:
        lines.append(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}, "error": {"code": error_code}}))
    elif result_ok:
        lines.append(json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}))
    elif include_error:
        lines.append(json.dumps({"jsonrpc": "2.0", "id": 2, "error": {"code": error_code, "message": "forced"}}))
    return "\n".join(lines)


def _agent_protocol_new_stdout(*, session_id: str = "session-a", include_response: bool = True) -> str:
    lines = ['{"jsonrpc":"2.0","id":1,"method":"session/new"}']
    if include_response:
        lines.append(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"sessionId": session_id}}))
    return "\n".join(lines)


def _agent_protocol_load_stdout(*, session_id: str = "session-a", include_exchange: bool = True, wrong_session: bool = False, nonempty_result: bool = False, response_id_mismatch: bool = False) -> str:
    sid = "session-b" if wrong_session else session_id
    if not include_exchange:
        return ""
    response_id = 9 if response_id_mismatch else 3
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "session/load", "params": {"sessionId": sid}}),
        json.dumps({"jsonrpc": "2.0", "id": response_id, "result": {"unexpected": True} if nonempty_result else {}}),
    ]
    return "\n".join(lines)


def _assert_no_authorizing_establishing_report(report_root: Path) -> None:
    report_path = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    if not report_path.is_file():
        return
    import tools.probe_p11_zed_session_load as probe

    try:
        parsed = probe.parse_establishing_report_v2(report_path.read_bytes())
    except probe.ProbeError:
        return
    raise AssertionError(f"authorizing report must not be published: {parsed.get('establishing_disposition')}")


def test_agent_protocol_drive_requires_real_erroring_prompt_on_new_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED: nonzero acpx exit alone must not establish the premise."""
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            return CommandResult(command, 2, '{"jsonrpc":"2.0","id":2,"error":{"code":-32000}}', "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            return CommandResult(command, 0, _agent_protocol_load_stdout(), "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["zed_launches"] == 0
    assert result["origin_a_launches"] == 0
    assert result["no_gateway_path_established"] is False
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    _assert_no_authorizing_establishing_report(report_root)


def test_agent_protocol_drive_requires_same_session_new_prompt_and_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED: all three exchanges must share one session id."""
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            return CommandResult(command, 0, _agent_protocol_new_stdout(session_id="session-a"), "")
        if len(command) >= 2 and command[-2] == "exec":
            stdout = _agent_protocol_prompt_stdout(session_id="session-a", wrong_session=True)
            return CommandResult(command, 2, stdout, "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            return CommandResult(command, 0, _agent_protocol_load_stdout(session_id="session-a"), "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["zed_launches"] == 0
    assert result["no_gateway_path_established"] is False
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    _assert_no_authorizing_establishing_report(report_root)


def test_agent_protocol_report_v2_reconstructs_authority_sequence_traffic_custody_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path publishes typed v2 record reconstructable without the sidecar."""
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            stdout = _agent_protocol_prompt_stdout()
            return CommandResult(command, 2, stdout, "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            return CommandResult(command, 0, _agent_protocol_load_stdout(), "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["no_gateway_path_established"] is True
    report_path = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    assert report_path.is_file()
    parsed = probe.parse_establishing_report_v2(report_path.read_bytes())
    assert parsed["schema"] == probe.ESTABLISHING_REPORT_SCHEMA
    assert parsed["establishing_disposition"] == probe.PLAN1124_ESTABLISHING_OK
    probe.parse_aware_utc_timestamp(str(parsed["completed_at_utc"]))
    assert str(parsed["completed_at_utc"]).endswith("Z")
    assert parsed["counts"] == {"zed_launches": 0, "origin_a_launches": 0}
    assert parsed["traffic"] == {
        "gateway_attempted": False,
        "provider_attempted": False,
        "model_call_attempted": False,
    }
    assert parsed["custody"] == {
        "approval_created": True,
        "approval_revoked": True,
        "post_revoke_inspect_exit_code": 1,
    }
    assert parsed["cleanup"] == {"throwaway_root_removed": True}
    authority = parsed["authority"]
    assert authority["source_commit"] == COMMIT
    assert authority["source_commit_execution_surface_clean"] is True
    assert authority["python_version"] == "3.14.0"
    assert authority["python_executable_sha256"] == SHA_B
    assert authority["acpx_version"] == "0.0.test"
    assert authority["acpx_command_sha256"] == SHA_A
    assert authority["acpx_cli_js_sha256"] == SHA_B
    assert authority["trust_executable_sha256"] == SHA_C
    assert authority["isolated_launcher_canonical_sha256"] == SHA_A
    assert authority["isolated_launcher_raw_sha256"] == SHA_A
    assert authority["isolated_patched_spec_sha256"] == SHA_B
    assert authority["applicability"]["schema"] == probe.APPLICABILITY_MANIFEST_SCHEMA
    assert len(authority["applicability"]["files"]) == len(probe.ESTABLISHING_EXECUTION_GIT_PATHS)
    sequence = parsed["sequence"]
    assert sequence["session_new"]["session_id"] == "session-a"
    assert sequence["session_prompt"]["session_id"] == "session-a"
    assert sequence["session_load"]["session_id"] == "session-a"
    assert sequence["session_prompt"]["request_count"] == 1
    assert sequence["session_prompt"]["message_sha256"] == probe.PLAN1124_EXEC_MESSAGE_SHA256
    assert sequence["session_prompt"]["outcome"] == "error"
    assert sequence["session_prompt"]["response_id_matches"] is True
    assert sequence["session_load"]["response_id_matches"] is True
    assert sequence["session_load"]["result"] == {}
    sidecar = json.loads(Path(str(result["sidecar"])).read_text(encoding="utf-8"))
    assert "sequence" not in sidecar


@pytest.mark.parametrize(
    ("case_id", "mutator"),
    [
        pytest.param(
            "missing_session_new_response",
            lambda: {"new": _agent_protocol_new_stdout(include_response=False)},
            id="missing_session_new_response",
        ),
        pytest.param(
            "missing_prompt_request",
            lambda: {"prompt": _agent_protocol_prompt_stdout(include_request=False)},
            id="missing_prompt_request",
        ),
        pytest.param(
            "two_prompt_requests",
            lambda: {"prompt": _agent_protocol_prompt_stdout(second_prompt=True)},
            id="two_prompt_requests",
        ),
        pytest.param(
            "wrong_prompt_message",
            lambda: {"prompt": _agent_protocol_prompt_stdout(wrong_message=True)},
            id="wrong_prompt_message",
        ),
        pytest.param(
            "prompt_wrong_session",
            lambda: {"prompt": _agent_protocol_prompt_stdout(wrong_session=True)},
            id="prompt_wrong_session",
        ),
        pytest.param(
            "prompt_response_id_mismatch",
            lambda: {"prompt": '{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"session-a","prompt":[{"type":"text","text":"Persist this probe thread only; do not use tools or modify files."}]}}\n{"jsonrpc":"2.0","id":9,"error":{"code":-32000}}'},
            id="prompt_response_id_mismatch",
        ),
        pytest.param(
            "prompt_succeeds",
            lambda: {"prompt": _agent_protocol_prompt_stdout(include_error=False, result_ok=True)},
            id="prompt_succeeds",
        ),
        pytest.param(
            "prompt_result_and_error",
            lambda: {"prompt": _agent_protocol_prompt_stdout(result_and_error=True)},
            id="prompt_result_and_error",
        ),
        pytest.param(
            "missing_load_exchange",
            lambda: {"load": _agent_protocol_load_stdout(include_exchange=False)},
            id="missing_load_exchange",
        ),
        pytest.param(
            "load_wrong_session",
            lambda: {"load": _agent_protocol_load_stdout(wrong_session=True)},
            id="load_wrong_session",
        ),
        pytest.param(
            "load_nonempty_result",
            lambda: {"load": _agent_protocol_load_stdout(nonempty_result=True)},
            id="load_nonempty_result",
        ),
        pytest.param(
            "gateway_marker",
            lambda: {"prompt": _agent_protocol_prompt_stdout() + '\n{"method":"gateway_ping"}'},
            id="gateway_marker",
        ),
        pytest.param(
            "provider_marker",
            lambda: {"prompt": _agent_protocol_prompt_stdout() + '\n{"provider":"openrouter"}'},
            id="provider_marker",
        ),
    ],
)
def test_establishing_negative_sequence_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    mutator,
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)
    overrides = mutator()

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            stdout = overrides.get("new", _agent_protocol_new_stdout())
            return CommandResult(command, 0, stdout, "")
        if len(command) >= 2 and command[-2] == "exec":
            stdout = overrides.get("prompt", _agent_protocol_prompt_stdout())
            return CommandResult(command, 2, stdout, "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            stdout = overrides.get("load", _agent_protocol_load_stdout())
            return CommandResult(command, 0, stdout, "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["zed_launches"] == 0
    assert result["origin_a_launches"] == 0
    assert result["no_gateway_path_established"] is False
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    _assert_no_authorizing_establishing_report(report_root)


@pytest.mark.parametrize(
    ("case_id", "setup"),
    [
        pytest.param(
            "revoke_failure",
            lambda monkeypatch, probe: monkeypatch.setattr(
                probe,
                "_revoke_temporary_approval",
                lambda *_a, **_k: (_ for _ in ()).throw(probe.ProbeError("temporary_approval_revoke", "inspect exit=0")),
            ),
            id="approval_not_revoked",
        ),
        pytest.param(
            "cleanup_failure",
            lambda monkeypatch, probe: monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (False, ["leftover"])),
            id="cleanup_false",
        ),
    ],
)
def test_establishing_negative_custody_and_cleanup_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    setup,
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)
    setup(monkeypatch, probe)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            return CommandResult(command, 2, _agent_protocol_prompt_stdout(), "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            return CommandResult(command, 0, _agent_protocol_load_stdout(), "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)
    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["zed_launches"] == 0
    assert result["origin_a_launches"] == 0
    assert result["no_gateway_path_established"] is False
    _assert_no_authorizing_establishing_report(report_root)


def test_real_zed_resume_requires_established_agent_protocol_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    parent = tmp_path / "parent"
    parent.mkdir()
    report_dir = tmp_path / "reports" / "plan-11-24-zed-guided-session-load-probe-v5"
    report_root = tmp_path / "reports"
    report_root.mkdir()
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)

    result = probe.run_plan1124_two_lifecycle_real_zed(parent, timeout_s=900, report_dir=report_dir)
    assert result["zed_launches"] == 0
    assert result["finding"] == "INDETERMINATE"
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"

    establishing = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    establishing.write_text("Establishing-Disposition: PRECONDITION_UNMET\n", encoding="utf-8")
    blocked = probe.run_plan1124_two_lifecycle_real_zed(parent, timeout_s=900, report_dir=report_dir)
    assert blocked["zed_launches"] == 0
    assert blocked["indeterminate_reason"] == "PRECONDITION_UNMET"


def _write_agent_protocol_establishing_report(
    report_path: Path,
    *,
    disposition: str,
    recorded_at_utc: str,
    commit: str,
    acpx_version: str,
    acpx_sha256: str,
    isolated_launcher_sha256: str,
) -> None:
    report_path.write_text(
        "\n".join(
            [
                f"Establishing-Disposition: {disposition}",
                "No-Gateway-Path-Established: true",
                f"Recorded-At-UTC: {recorded_at_utc}",
                f"Commit: {commit}",
                f"Acpx-Version: {acpx_version}",
                f"Acpx-Executable-Sha256: {acpx_sha256}",
                f"Isolated-Launcher-Sha256: {isolated_launcher_sha256}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_require_established_agent_protocol_prerequisite_rejects_commit_mismatch(tmp_path: Path) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
        report_path = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
        recorded_at = probe.datetime.now(probe.UTC).isoformat()
        _write_agent_protocol_establishing_report(
            report_path,
            disposition=probe.PLAN1124_ESTABLISHING_OK,
            recorded_at_utc=recorded_at,
            commit="commit-old",
            acpx_version="0.0.test",
            acpx_sha256=SHA_B,
            isolated_launcher_sha256=SHA_A,
        )

        monkeypatch.setattr(probe, "_resolve_acpx", lambda: tmp_path / "acpx.cmd")
        monkeypatch.setattr(probe, "_acpx_version", lambda *_a, **_k: "0.0.test")
        monkeypatch.setattr(probe, "_file_sha256", lambda *_p: SHA_B)

        result = {"commit": COMMIT, "isolated_build": {"sha256": SHA_A}, "zed_launches": 0}
        ok = probe._require_established_agent_protocol_prerequisite(result)
        assert ok is False
        assert result["zed_launches"] == 0
        assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    finally:
        monkeypatch.undo()


def test_require_established_agent_protocol_prerequisite_rejects_acpx_sha_mismatch(tmp_path: Path) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
        report_path = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
        recorded_at = probe.datetime.now(probe.UTC).isoformat()
        _write_agent_protocol_establishing_report(
            report_path,
            disposition=probe.PLAN1124_ESTABLISHING_OK,
            recorded_at_utc=recorded_at,
            commit=COMMIT,
            acpx_version="0.0.test",
            acpx_sha256="c" * 64,
            isolated_launcher_sha256=SHA_A,
        )

        monkeypatch.setattr(probe, "_resolve_acpx", lambda: tmp_path / "acpx.cmd")
        monkeypatch.setattr(probe, "_acpx_version", lambda *_a, **_k: "0.0.test")
        monkeypatch.setattr(probe, "_file_sha256", lambda *_p: SHA_B)

        result = {"commit": COMMIT, "isolated_build": {"sha256": SHA_A}, "zed_launches": 0}
        ok = probe._require_established_agent_protocol_prerequisite(result)
        assert ok is False
        assert result["zed_launches"] == 0
        assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    finally:
        monkeypatch.undo()


def test_require_established_agent_protocol_prerequisite_rejects_launcher_sha_mismatch(tmp_path: Path) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
        report_path = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
        recorded_at = probe.datetime.now(probe.UTC).isoformat()
        _write_agent_protocol_establishing_report(
            report_path,
            disposition=probe.PLAN1124_ESTABLISHING_OK,
            recorded_at_utc=recorded_at,
            commit=COMMIT,
            acpx_version="0.0.test",
            acpx_sha256=SHA_B,
            isolated_launcher_sha256="d" * 64,
        )

        monkeypatch.setattr(probe, "_resolve_acpx", lambda: tmp_path / "acpx.cmd")
        monkeypatch.setattr(probe, "_acpx_version", lambda *_a, **_k: "0.0.test")
        monkeypatch.setattr(probe, "_file_sha256", lambda *_p: SHA_B)

        result = {"commit": COMMIT, "isolated_build": {"sha256": SHA_A}, "zed_launches": 0}
        ok = probe._require_established_agent_protocol_prerequisite(result)
        assert ok is False
        assert result["zed_launches"] == 0
        assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    finally:
        monkeypatch.undo()


def test_resume_classifier_requires_load_id_from_lifecycle_a_session_new() -> None:
    from tools.probe_p11_zed_session_load import _classify_resume_lifecycle

    finding, reason = _classify_resume_lifecycle(
        "session-a",
        {
            "request": {"method": "session/load", "params": {"sessionId": "session-b"}},
            "response": {"result": {}},
        },
    )
    assert finding.value == "INDETERMINATE"
    assert reason == "PRECONDITION_UNMET"

    finding_ok, reason_ok = _classify_resume_lifecycle(
        "session-a",
        {
            "request": {"method": "session/load", "params": {"sessionId": "session-a"}},
            "response": {"result": {}},
        },
    )
    assert finding_ok.value == "REACHABLE"
    assert reason_ok is None


def test_resume_classifier_rejects_response_with_result_and_error_as_indeterminate() -> None:
    from tools.probe_p11_zed_session_load import _classify_resume_lifecycle

    finding, reason = _classify_resume_lifecycle(
        "session-a",
        {
            "request": {"method": "session/load", "params": {"sessionId": "session-a"}},
            "response": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {},
                "error": {"code": -32601, "message": "Method not found"},
            },
        },
    )
    assert finding.value == "INDETERMINATE"
    assert reason == "OBSERVATION_INCOMPLETE"


PLAN1124_EXEC_MESSAGE = "Persist this probe thread only; do not use tools or modify files."


def _lifecycle_a_relay_bytes(
    *,
    include_prompt: bool = True,
    extra_prompt: bool = False,
    prompt_text: str = PLAN1124_EXEC_MESSAGE,
    prompt_session_id: str = "session-a",
    prompt_blocks: list[dict[str, str]] | None = None,
    include_prompt_response: bool = True,
    prompt_response_id: int = 2,
    prompt_error: bool = True,
    prompt_result_ok: bool = False,
) -> tuple[bytes, bytes]:
    zed_lines = ['{"jsonrpc":"2.0","id":1,"method":"session/new"}']
    if include_prompt:
        if prompt_blocks is not None:
            prompt_payload = prompt_blocks
        else:
            prompt_payload = [{"type": "text", "text": prompt_text}]
        zed_lines.append(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "session/prompt",
                    "params": {"sessionId": prompt_session_id, "prompt": prompt_payload},
                },
                separators=(",", ":"),
            )
        )
    if extra_prompt:
        zed_lines.append(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "session/prompt",
                    "params": {
                        "sessionId": prompt_session_id,
                        "prompt": [{"type": "text", "text": PLAN1124_EXEC_MESSAGE}],
                    },
                },
                separators=(",", ":"),
            )
        )
    agent_lines = ['{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-a"}}']
    if include_prompt and include_prompt_response:
        if prompt_error:
            agent_lines.append(
                json.dumps(
                    {"jsonrpc": "2.0", "id": prompt_response_id, "error": {"code": -32000, "message": "prompt rejected"}},
                    separators=(",", ":"),
                )
            )
        elif prompt_result_ok:
            agent_lines.append(json.dumps({"jsonrpc": "2.0", "id": prompt_response_id, "result": {"ok": True}}, separators=(",", ":")))
    return ("\n".join(zed_lines) + "\n").encode("utf-8"), ("\n".join(agent_lines) + "\n").encode("utf-8")


def _lifecycle_b_relay_bytes(*, session_id: str = "session-a") -> tuple[bytes, bytes]:
    zed = json.dumps(
        {"jsonrpc": "2.0", "id": 9, "method": "session/load", "params": {"sessionId": session_id}},
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    agent = b'{"jsonrpc":"2.0","id":9,"result":{}}\n'
    return zed, agent


def _stub_two_lifecycle_harness(
    probe: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    relay_factory: object,
    materialize_spy: list[object] | None = None,
) -> tuple[Path, Path]:
    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])
    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _h: (
            tmp_path / "Zed.exe",
            ZedInvocation(argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)), user_data_root=str(zed_home), discovered_from="zed --help"),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: "--foreground")
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})
    monkeypatch.setattr(probe, "_launch_zed_once", lambda *_a, **_k: {"returncode": 0})
    monkeypatch.setattr(probe, "verify_relay_capture", lambda *_a, **_k: None)
    monkeypatch.setattr(probe.time, "monotonic", lambda: 100.0)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    if materialize_spy is not None:

        def _spy_materialize(**kwargs: object) -> Path:
            materialize_spy.append(kwargs)
            return tmp_path / "manifest.json"

        monkeypatch.setattr(probe, "materialize_sanitized_zed_evidence_v5", _spy_materialize)

    monkeypatch.setattr(probe, "build_opaque_relay_command", relay_factory)
    return parent, report_root


def test_two_lifecycle_run_reuses_one_profile_and_separates_relay_captures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    # This test focuses on the two-lifecycle harness behavior; the Task-13 disposition
    # gate is already covered by the separate fail-closed prerequisite test above.
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])
    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _h: (
            tmp_path / "Zed.exe",
            ZedInvocation(argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)), user_data_root=str(zed_home), discovered_from="zed --help"),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: "--foreground")
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})
    launch_calls: list[dict[str, object]] = []
    monotonic_values = iter([100.0, 100.0, 100.0, 951.0, 951.0])

    def fake_launch(
        argv: object,
        *,
        env: object,
        cwd: object,
        log_path: object = None,
        timeout_s: float = 180.0,
    ) -> dict[str, object]:
        launch_calls.append({"argv": list(argv), "cwd": str(cwd), "timeout_s": timeout_s})
        return {"returncode": 0}

    monkeypatch.setattr(probe, "_launch_zed_once", fake_launch)
    monkeypatch.setattr(probe, "verify_relay_capture", lambda *_a, **_k: None)
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(monotonic_values, 901.0))
    monkeypatch.setattr(probe, "materialize_sanitized_zed_evidence_v5", lambda **_k: tmp_path / "manifest.json")

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    relay_calls: list[str] = []

    def fake_relay(**kwargs: object) -> list[str]:
        run_id = str(kwargs["run_id"])
        relay_calls.append(run_id)
        run_dir = run_root / "relay-capture" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if run_id == "plan1124-create":
            zed = (
                b'{"jsonrpc":"2.0","id":1,"method":"session/new"}\n'
                b'{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"session-a","prompt":[{"type":"text","text":"Persist this probe thread only; do not use tools or modify files."}]}}\n'
            )
            agent = (
                b'{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-a"}}\n'
                b'{"jsonrpc":"2.0","id":2,"error":{"code":-32000,"message":"prompt rejected"}}\n'
            )
        else:
            zed = b'{"jsonrpc":"2.0","id":2,"method":"session/load","params":{"sessionId":"session-a"}}\n'
            agent = b'{"jsonrpc":"2.0","id":2,"result":{}}\n'
        (run_dir / "zed-to-agent.bin").write_bytes(zed)
        (run_dir / "agent-to-zed.bin").write_bytes(agent)
        return ["python", "relay.py"]

    monkeypatch.setattr(probe, "build_opaque_relay_command", fake_relay)

    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert relay_calls == ["plan1124-create", "plan1124-resume"]
    assert result["zed_launches"] == 2
    assert result["finding"] == "REACHABLE"
    assert result["resume_lifecycle"]["shared_profile"] is True
    assert len(launch_calls) == 2
    assert launch_calls[0]["timeout_s"] == 900.0
    assert launch_calls[1]["timeout_s"] == 49.0
    assert Path(str(launch_calls[0]["cwd"])) == Path(str(launch_calls[1]["cwd"]))
    ledger = result["event_ledger"]
    kinds = [entry["kind"] for entry in ledger]
    assert kinds.index("lifecycle_launch_scheduled") < kinds.index("lifecycle_launch_started")
    assert "workspace_approved_durable" in kinds
    assert "no_intervening_cleanup_between_lifecycles" in kinds
    assert kinds.count("relay_capture_verified") == 2
    last_relay_verified = max(i for i, kind in enumerate(kinds) if kind == "relay_capture_verified")
    assert last_relay_verified < kinds.index("workspace_revoked")
    assert "final_cleanup_verified" in kinds
    assert kinds.count("workspace_revoked") == 1
    assert kinds.count("final_cleanup_verified") == 1
    assert kinds.index("workspace_revoked") < kinds.index("final_cleanup_verified")

    prompt_event = next(e for e in ledger if e["kind"] == "prompt_message_seam_observed")
    assert prompt_event["prompt_request_count"] == 1
    assert prompt_event["prompt_text_matches"] == 1
    assert "prompt_text_match_expected" not in prompt_event


@pytest.mark.parametrize(
    ("case_id", "factory_kwargs"),
    [
        pytest.param("zero_prompts", {"include_prompt": False}, id="zero_prompts"),
        pytest.param("two_prompts", {"extra_prompt": True}, id="two_prompts"),
    ],
)
def test_two_lifecycle_run_requires_exactly_one_fixed_lifecycle_a_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    factory_kwargs: dict[str, object],
) -> None:
    import tools.probe_p11_zed_session_load as probe

    def relay_factory(**kwargs: object) -> list[str]:
        run_id = str(kwargs["run_id"])
        run_dir = tmp_path / "run-root" / "relay-capture" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if run_id == "plan1124-create":
            zed, agent = _lifecycle_a_relay_bytes(**factory_kwargs)
        else:
            zed, agent = _lifecycle_b_relay_bytes()
        (run_dir / "zed-to-agent.bin").write_bytes(zed)
        (run_dir / "agent-to-zed.bin").write_bytes(agent)
        return ["python", "relay.py"]

    parent, report_root = _stub_two_lifecycle_harness(probe, tmp_path, monkeypatch, relay_factory=relay_factory)
    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert result["finding"] == "INDETERMINATE"
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert result["zed_launches"] == 1
    assert "evidence_manifest" not in result
    assert sum(1 for entry in result["event_ledger"] if entry.get("kind") == "workspace_revoked") == 1


@pytest.mark.parametrize(
    ("case_id", "factory_kwargs"),
    [
        pytest.param("wrong_text", {"prompt_text": "wrong message"}, id="wrong_text"),
        pytest.param("multi_block", {"prompt_blocks": [{"type": "text", "text": PLAN1124_EXEC_MESSAGE}, {"type": "text", "text": "extra"}]}, id="multi_block"),
        pytest.param("wrong_session", {"prompt_session_id": "session-b"}, id="wrong_session"),
        pytest.param("missing_response", {"include_prompt_response": False}, id="missing_response"),
        pytest.param("mismatched_response_id", {"prompt_response_id": 99}, id="mismatched_response_id"),
        pytest.param("successful_prompt", {"prompt_error": False, "prompt_result_ok": True}, id="successful_prompt"),
    ],
)
def test_two_lifecycle_run_rejects_prompt_with_extra_content_or_wrong_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: str,
    factory_kwargs: dict[str, object],
) -> None:
    import tools.probe_p11_zed_session_load as probe

    def relay_factory(**kwargs: object) -> list[str]:
        run_id = str(kwargs["run_id"])
        run_dir = tmp_path / "run-root" / "relay-capture" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if run_id == "plan1124-create":
            zed, agent = _lifecycle_a_relay_bytes(**factory_kwargs)
        else:
            zed, agent = _lifecycle_b_relay_bytes()
        (run_dir / "zed-to-agent.bin").write_bytes(zed)
        (run_dir / "agent-to-zed.bin").write_bytes(agent)
        return ["python", "relay.py"]

    parent, report_root = _stub_two_lifecycle_harness(probe, tmp_path, monkeypatch, relay_factory=relay_factory)
    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert result["finding"] == "INDETERMINATE"
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert result["zed_launches"] == 1
    assert "evidence_manifest" not in result
    assert sum(1 for entry in result["event_ledger"] if entry.get("kind") == "workspace_revoked") == 1


def test_two_lifecycle_failure_cannot_materialize_v5_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    materialize_calls: list[object] = []

    def relay_factory(**kwargs: object) -> list[str]:
        run_id = str(kwargs["run_id"])
        run_dir = tmp_path / "run-root" / "relay-capture" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if run_id == "plan1124-create":
            zed, agent = _lifecycle_a_relay_bytes(include_prompt=False)
        else:
            zed, agent = _lifecycle_b_relay_bytes()
        (run_dir / "zed-to-agent.bin").write_bytes(zed)
        (run_dir / "agent-to-zed.bin").write_bytes(agent)
        return ["python", "relay.py"]

    parent, report_root = _stub_two_lifecycle_harness(
        probe,
        tmp_path,
        monkeypatch,
        relay_factory=relay_factory,
        materialize_spy=materialize_calls,
    )
    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert result["finding"] == "INDETERMINATE"
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert materialize_calls == []
    assert "evidence_manifest" not in result
    assert not (report_root / "plan-11-24-zed-guided-session-load-probe-v5" / "manifest.json").exists()


def test_two_lifecycle_sidecar_canary_aliases_event_ledger_paths_and_redacts_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Canary: event_ledger must not persist raw absolute paths or credential strings."""
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])

    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _root: (
            tmp_path / "Zed.exe",
            ZedInvocation(
                argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)),
                user_data_root=str(zed_home),
                discovered_from="zed --help",
            ),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: "--foreground")
    # Inject a credential-like string into argv; it must be redacted in persisted sidecar.
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe", "OPTIMUS_API_KEY=SECRET"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})

    launch_calls: list[dict[str, object]] = []
    monotonic_values = iter([100.0, 100.0, 100.0, 951.0, 951.0])

    def fake_launch(
        argv: object,
        *,
        env: object,
        cwd: object,
        log_path: object = None,
        timeout_s: float = 180.0,
    ) -> dict[str, object]:
        launch_calls.append({"argv": list(argv), "cwd": str(cwd), "timeout_s": timeout_s})
        return {"returncode": 0}

    monkeypatch.setattr(probe, "_launch_zed_once", fake_launch)
    monkeypatch.setattr(probe, "verify_relay_capture", lambda *_a, **_k: None)
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(monotonic_values, 901.0))
    # IMPORTANT: do NOT monkeypatch materialize_sanitized_zed_evidence_v5; we want the canary to exercise it.

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    def fake_relay(**kwargs: object) -> list[str]:
        run_id = str(kwargs["run_id"])
        run_dir = run_root / "relay-capture" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if run_id == "plan1124-create":
            zed = (
                b'{"jsonrpc":"2.0","id":1,"method":"session/new"}\n'
                b'{"jsonrpc":"2.0","id":2,"method":"session/prompt","params":{"sessionId":"session-a","prompt":[{"type":"text","text":"Persist this probe thread only; do not use tools or modify files."}]}}\n'
            )
            agent = (
                b'{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-a"}}\n'
                b'{"jsonrpc":"2.0","id":2,"error":{"code":-32000,"message":"prompt rejected"}}\n'
            )
        else:
            zed = b'{"jsonrpc":"2.0","id":2,"method":"session/load","params":{"sessionId":"session-a"}}\n'
            agent = b'{"jsonrpc":"2.0","id":2,"result":{}}\n'
        (run_dir / "zed-to-agent.bin").write_bytes(zed)
        (run_dir / "agent-to-zed.bin").write_bytes(agent)
        return ["python", "relay.py"]

    monkeypatch.setattr(probe, "build_opaque_relay_command", fake_relay)

    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert result["zed_launches"] == 2

    sidecar_path = parent / "plan1124-real-zed-resume-result.json"
    sidecar_text = sidecar_path.read_text(encoding="utf-8")
    assert str(zed_home) not in sidecar_text
    assert "OPTIMUS_API_KEY=SECRET" not in sidecar_text


def test_agent_protocol_drive_revoke_failure_removes_positive_marker_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    stale_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    stale_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    parent = _agent_protocol_drive_common_stubs(probe, tmp_path, monkeypatch, report_root=report_root)
    monkeypatch.setattr(
        probe,
        "_revoke_temporary_approval",
        lambda *_a, **_k: (_ for _ in ()).throw(probe.ProbeError("temporary_approval_revoke", "inspect exit=0")),
    )

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        if command[-2:] == ["sessions", "new"]:
            return CommandResult(command, 0, _agent_protocol_new_stdout(), "")
        if len(command) >= 2 and command[-2] == "exec":
            return CommandResult(command, 2, _agent_protocol_prompt_stdout(), "")
        if len(command) >= 4 and command[-4:-1] == ["sessions", "export", "--output"]:
            return CommandResult(command, 0, "", "")
        if command[-2:] == ["sessions", "import"]:
            return CommandResult(command, 0, "", "")
        if command[-1] == "status":
            return CommandResult(command, 0, _agent_protocol_load_stdout(), "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_plan1124_agent_protocol_drive(parent)
    assert result["no_gateway_path_established"] is False
    assert result["indeterminate_reason"] == "CLEANUP_UNVERIFIED"
    assert not stale_report.exists()


def test_two_lifecycle_launch_crash_still_records_spent_shot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])
    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _h: (
            tmp_path / "Zed.exe",
            ZedInvocation(argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)), user_data_root=str(zed_home), discovered_from="zed --help"),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: "--foreground")
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})
    monkeypatch.setattr(probe.time, "monotonic", lambda: 100.0)
    launch_attempts = {"count": 0}

    def crashing_launch(*_a: object, **_k: object) -> dict[str, object]:
        launch_attempts["count"] += 1
        raise probe.ProbeError("zed_launch", "simulated crash")

    monkeypatch.setattr(probe, "_launch_zed_once", crashing_launch)
    monkeypatch.setattr(probe, "build_opaque_relay_command", lambda **_k: ["python", "relay.py"])
    monkeypatch.setattr(probe, "seed_hermetic_zed_settings", lambda *_a, **_k: tmp_path / "settings.json")

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert launch_attempts["count"] == 1
    assert result["zed_launches"] == 1


def test_two_lifecycle_prelaunch_failure_does_not_advance_launch_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])

    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _root: (
            tmp_path / "Zed.exe",
            ZedInvocation(
                argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)),
                user_data_root=str(zed_home),
                discovered_from="zed --help",
            ),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))

    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: (_ for _ in ()).throw(probe.ProbeError("zed_discovery", "simulated help failure")))
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})
    monkeypatch.setattr(probe.time, "monotonic", lambda: 100.0)

    launch_attempts = {"count": 0}

    def crashing_launch(*_a: object, **_k: object) -> dict[str, object]:
        launch_attempts["count"] += 1
        raise probe.ProbeError("zed_launch", "should not be called")

    monkeypatch.setattr(probe, "_launch_zed_once", crashing_launch)
    monkeypatch.setattr(probe, "build_opaque_relay_command", lambda **_k: ["python", "relay.py"])
    monkeypatch.setattr(probe, "seed_hermetic_zed_settings", lambda *_a, **_k: None)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert launch_attempts["count"] == 0
    assert result["zed_launches"] == 0
    assert result["indeterminate_reason"] == "HERMETIC_INVOCATION_UNAVAILABLE"


def test_two_lifecycle_deadline_expiry_does_not_advance_launch_accounting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe

    report_root = tmp_path / "reports"
    report_root.mkdir()
    agent_report = report_root / "plan-11-24-agent-protocol-persistence-establishing-drive.md"
    agent_report.write_text(
        "Establishing-Disposition: NO_GATEWAY_PATH_ESTABLISHED\nNo-Gateway-Path-Established: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "REPORTS_ROOT", report_root)
    monkeypatch.setattr(probe, "_require_established_agent_protocol_prerequisite", lambda _r: True)

    parent = tmp_path / "parent"
    parent.mkdir()
    run_root = tmp_path / "run-root"
    run_root.mkdir()
    (run_root / "probe-source").mkdir(parents=True, exist_ok=True)
    (run_root / "probe-source" / "marker.py").write_text("# isolated copy\n", encoding="utf-8")
    (run_root / "probe-build").mkdir(parents=True, exist_ok=True)
    (tmp_path / "launcher.py").write_text("# launcher\n", encoding="utf-8")
    workspace = run_root / "zed-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    zed_home = run_root / "zed-home"
    zed_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(probe, "_validate_parent_workspace", lambda *_a, **_k: parent)
    monkeypatch.setattr(probe.tempfile, "mkdtemp", lambda **_k: str(run_root))
    monkeypatch.setattr(probe, "zed_target_already_running", lambda *_a, **_k: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])

    monkeypatch.setattr(
        probe,
        "prepare_real_zed_probe",
        lambda *_a, **_k: type(
            "Prep",
            (),
            {
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "normal_root": str(tmp_path / "repo"),
                "normal_commit": COMMIT,
                "normal_source_sha256_before": SHA_A,
                "cleanup_dry_run_verified": True,
            },
        )(),
    )
    monkeypatch.setattr(
        probe,
        "verify_normal_operation_isolation",
        lambda _prep: type(
            "Iso",
            (),
            {
                "normal_agent_load_session_advertised": False,
                "isolated_probe_load_session_advertised": True,
                "normal_source_sha256_before": SHA_A,
                "normal_source_sha256_after": SHA_A,
                "isolated_source_root": str(run_root / "probe-source"),
                "isolated_build_root": str(run_root / "probe-build"),
                "hermetic_zed_root": str(zed_home),
                "cleanup_dry_run_verified": True,
                "cleanup_verified": True,
                "prelaunch_predicates_pass": True,
            },
        )(),
    )
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(
        probe,
        "_discover_live_zed_invocation",
        lambda _root: (
            tmp_path / "Zed.exe",
            ZedInvocation(
                argv=("C:/Tools/Zed.exe", "--user-data-dir", str(zed_home)),
                user_data_root=str(zed_home),
                discovered_from="zed --help",
            ),
            SHA_A,
        ),
    )
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: tmp_path / "launcher.py")
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _repo: tmp_path / "optimus-trust.exe")
    monkeypatch.setattr(probe, "_run_interactive_required", lambda *_a, **_k: CommandResult([], 0, "", ""))
    monkeypatch.setattr(probe, "_revoke_temporary_approval", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", lambda **_k: (True, []))
    monkeypatch.setattr(probe, "_observe_zed_help", lambda *_a, **_k: "--foreground")
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", lambda *_a, **_k: ["C:/Tools/Zed.exe"])
    monkeypatch.setattr(probe, "_zed_env_for_invocation", lambda *_a, **_k: {})

    # deadline = 100 + 900 = 1000; remaining recompute returns 1000 - 1100 <= 0
    monotonic_values = iter([100.0, 100.0, 1100.0])
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(monotonic_values, 901.0))

    launch_attempts = {"count": 0}

    def crashing_launch(*_a: object, **_k: object) -> dict[str, object]:
        launch_attempts["count"] += 1
        raise probe.ProbeError("zed_launch", "should not be called")

    monkeypatch.setattr(probe, "_launch_zed_once", crashing_launch)
    monkeypatch.setattr(probe, "build_opaque_relay_command", lambda **_k: ["python", "relay.py"])
    monkeypatch.setattr(probe, "seed_hermetic_zed_settings", lambda *_a, **_k: None)

    def fake_run(command: list[str], *, cwd: Path, env: dict[str, str]) -> CommandResult:
        del cwd, env
        if command[-1] == "inspect":
            return CommandResult(command, 1, "", "")
        return CommandResult(command, 0, "", "")

    monkeypatch.setattr(probe, "_run", fake_run)

    result = probe.run_plan1124_two_lifecycle_real_zed(
        parent,
        timeout_s=900,
        report_dir=report_root / "plan-11-24-zed-guided-session-load-probe-v5",
    )
    assert launch_attempts["count"] == 0
    assert result["zed_launches"] == 0
    assert result["indeterminate_reason"] == "OBSERVATION_INCOMPLETE"


def test_resume_classifier_rejects_non_session_load_error_as_unreachable(
) -> None:
    from tools.probe_p11_zed_session_load import Finding, _classify_resume_lifecycle

    finding, reason = _classify_resume_lifecycle(
        "session-a",
        {
            "request": {"method": "session/prompt", "params": {"sessionId": "session-a"}},
            "response": {"error": {"code": -32601, "message": "Method not found"}},
        },
    )
    assert finding == Finding.INDETERMINATE
    assert reason == "OBSERVATION_INCOMPLETE"

def test_cli_default_timeout_is_unattended_180() -> None:
    from tools.probe_p11_zed_session_load import _parse_args

    args = _parse_args(
        [
            "--mode",
            "real-zed",
            "--report-dir",
            "reports/plan-11-24-zed-guided-session-load-probe",
            "C:/tmp/ws",
        ]
    )
    assert args.zed_launch_timeout_seconds == 180.0


def test_cli_guided_timeout_parses_900() -> None:
    from tools.probe_p11_zed_session_load import _parse_args

    args = _parse_args(
        [
            "--mode",
            "real-zed",
            "--zed-launch-timeout-seconds",
            "900",
            "--report-dir",
            "reports/plan-11-24-zed-guided-session-load-probe",
            "C:/tmp/ws",
        ]
    )
    assert args.zed_launch_timeout_seconds == 900.0


def test_invalid_timeouts_fail_before_popen(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    from tools.probe_p11_zed_session_load import _parse_args, validate_zed_launch_timeout_seconds

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Popen must not run")

    monkeypatch.setattr(subprocess, "Popen", boom)
    for raw in ("0", "-1", "nan", "inf", "901"):
        with pytest.raises(SystemExit):
            _parse_args(
                [
                    "--mode",
                    "real-zed",
                    "--zed-launch-timeout-seconds",
                    raw,
                    "--report-dir",
                    "reports/plan-11-24-zed-guided-session-load-probe",
                    "C:/tmp/ws",
                ]
            )
    for value in (0.0, -1.0, float("nan"), float("inf"), 901.0):
        with pytest.raises(ValueError):
            validate_zed_launch_timeout_seconds(value)


def _event_kinds(events: list[dict[str, object]]) -> list[str]:
    return [str(event["kind"]) for event in events]


def _events_of(events: list[dict[str, object]], kind: str) -> list[dict[str, object]]:
    return [event for event in events if event["kind"] == kind]


def _workspace_from_command(command: list[str]) -> Path:
    return Path(command[command.index("--workspace-root") + 1]).resolve()


def _install_stubbed_real_zed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    write_capture: bool = False,
    inspect_returncode: int = 1,
    approve_error: str | None = None,
    launch_returncode: int = 0,
    launch_error: str | None = None,
    revoke_error: str | None = None,
    revoke_interrupt: BaseException | None = None,
) -> tuple[Path, Path, Path, dict[str, object]]:
    """Patch the live-Zed path so tests never start a GUI. Optionally plant relay capture files."""
    import tools.probe_p11_zed_session_load as probe
    from tools.probe_p11_zed_session_load import DEFAULT_PROBE_PATCH_PLAN, ProbePreparation

    parent = tmp_path / "throwaway"
    parent.mkdir()
    scratch = tmp_path / "scratch"
    isolated = scratch / "probe-source"
    build = scratch / "probe-build"
    hermetic = scratch / "zed-home"
    for path in (isolated, build, hermetic):
        path.mkdir(parents=True)
    launcher = build / "isolated_optimus_agent.py"
    launcher.write_text("# launcher\n", encoding="utf-8")
    zed_exe = tmp_path / "Zed.exe"
    zed_exe.write_bytes(b"fake")
    trust_cli = tmp_path / "optimus-trust.exe"
    prep = ProbePreparation(
        isolated_source_root=str(isolated),
        isolated_build_root=str(build),
        hermetic_zed_root=str(hermetic),
        normal_root=str(tmp_path / "normal"),
        normal_commit=COMMIT,
        normal_source_sha256_before=SHA_C,
        patch_plan=DEFAULT_PROBE_PATCH_PLAN,
        cleanup_dry_run_verified=True,
    )
    isolation = IsolationEvidence(
        normal_agent_load_session_advertised=False,
        isolated_probe_load_session_advertised=True,
        normal_source_sha256_before=SHA_C,
        normal_source_sha256_after=SHA_C,
        isolated_source_root=str(isolated),
        isolated_build_root=str(build),
        hermetic_zed_root=str(hermetic),
        cleanup_dry_run_verified=True,
        cleanup_verified=False,
    )
    invocation = ZedInvocation(
        argv=(str(zed_exe), "--user-data-dir", str(hermetic)),
        user_data_root=str(hermetic),
        discovered_from="zed --help",
        version="Zed 1.15.0",
        executable_sha256=SHA_A,
        environment_bind=(),
    )
    acpx = AcpxBaselineEvidence(
        acpx_version="0.12.0",
        acpx_executable="C:/Tools/acpx.cmd",
        acpx_sha256=SHA_B,
        capability_payload={"loadSession": True, "sessionCapabilities": {}},
        origin_a_launches=0,
        session_load_exchange=None,
    )
    events: list[dict[str, object]] = []
    approval = {"live": False}
    observed: dict[str, object] = {
        "events": events,
        "approval": approval,
        "trust_cli": trust_cli,
    }

    def spy_seed_hermetic_zed_settings(
        user_data_dir: Path,
        *,
        relay_command: str,
        relay_args: list[str] | tuple[str, ...],
    ) -> Path:
        observed["seed_first_arg"] = user_data_dir
        events.append({"kind": "settings_prepared"})
        return seed_hermetic_zed_settings(
            user_data_dir,
            relay_command=relay_command,
            relay_args=relay_args,
        )

    real_build_opaque_relay_command = probe.build_opaque_relay_command

    def spy_build_opaque_relay_command(**kwargs: object) -> list[str]:
        child_args = [str(item) for item in list(kwargs.get("child_args") or ())]
        observed["child_executable"] = str(kwargs.get("child_executable") or "")
        observed["child_args"] = child_args
        events.append({"kind": "relay_prepared", "child_args": child_args})
        return real_build_opaque_relay_command(**kwargs)

    def capture_launch_argv(inv: ZedInvocation, **_kwargs: object) -> tuple[str, ...]:
        observed["launched_environment_bind"] = inv.environment_bind
        events.append({"kind": "launch_argv_prepared"})
        return (str(zed_exe), str(parent))

    def fake_acpx(**kwargs: object) -> AcpxBaselineEvidence:
        run_root = Path(str(kwargs["run_root"]))
        workspace = run_root / "zed-workspace"
        events.append(
            {
                "kind": "acpx",
                "zed_workspace_exists": workspace.is_dir(),
                "approval_live": bool(approval["live"]),
                "zed_workspace": str(workspace.resolve()) if workspace.exists() else None,
            }
        )
        return acpx

    def fake_run(command: object, *, cwd: object, env: object) -> CommandResult:
        argv = [str(item) for item in list(command)]
        if "inspect" in argv:
            events.append({"kind": "inspect", "command": argv, "cwd": str(cwd)})
            return CommandResult(command=argv, returncode=inspect_returncode, stdout="", stderr="")
        return CommandResult(command=argv, returncode=0, stdout="", stderr="")

    def fake_interactive(command: object, *, cwd: object, stage: str) -> CommandResult:
        argv = [str(item) for item in list(command)]
        events.append({"kind": "approve", "command": argv, "cwd": str(cwd), "stage": stage})
        if approve_error is not None:
            raise ProbeError(stage, approve_error)
        approval["live"] = True
        return CommandResult(command=argv, returncode=0, stdout="", stderr="")

    def fake_revoke(trust_cli_path: Path, workspace: Path, *, cwd: Path) -> None:
        command = build_trust_command(trust_cli_path, workspace, "revoke")
        events.append(
            {
                "kind": "revoke",
                "command": command,
                "workspace": str(Path(workspace).resolve()),
                "approval_live_before": bool(approval["live"]),
            }
        )
        if revoke_interrupt is not None:
            raise revoke_interrupt
        if revoke_error is not None:
            raise ProbeError("zed_workspace_revoke", revoke_error)
        approval["live"] = False

    def fake_launch(
        argv: object,
        *,
        env: object,
        cwd: object,
        log_path: object = None,
        timeout_s: float = 180.0,
    ) -> dict[str, object]:
        observed["timeout_s"] = timeout_s
        observed["config_settings_before_launch"] = (hermetic / "config" / "settings.json").is_file()
        observed["old_layout_settings_before_launch"] = (hermetic / "Zed" / "settings.json").exists()
        roots = sorted(parent.glob("p1119-real-zed-*"))
        observed["zed_appdata_before_launch"] = bool(roots) and (roots[-1] / "zed-appdata").exists()
        live = bool(approval["live"])
        events.append({"kind": "launch_start", "cwd": str(cwd), "approval_live": live, "argv": list(argv)})
        if launch_error is not None:
            raise ProbeError("zed_launch", launch_error)
        events.append({"kind": "child_spawn", "n": 1, "approval_live": live})
        events.append({"kind": "child_spawn", "n": 2, "approval_live": live})
        if write_capture:
            cap = roots[-1] / "relay-capture" / PLAN1119_RUN_ID
            cap.mkdir(parents=True, exist_ok=True)
            zed_bytes, agent_bytes = _paired_sanitized_relay_bytes()
            (cap / "zed-to-agent.bin").write_bytes(zed_bytes)
            (cap / "agent-to-zed.bin").write_bytes(agent_bytes)
            # Plant private relay-child stderr scratch diagnostics.
            # The probe must extract a bounded sanitized excerpt and never persist the raw file.
            prefix = (
                f"child-stderr-prefix {RELAY_CHILD_STDERR_CANARY} scratch_path={RELAY_CHILD_STDERR_RAW_SCRATCH_PATH}\n\n\t"
            )
            # Ensure the prefix/canary and scratch path fall outside the tail-cropped excerpt.
            filler = "X  \n\t" * 5000
            raw = prefix + filler
            (cap / "relay-child-stderr.txt").write_bytes(raw.encode("utf-8"))
        events.append({"kind": "launch_return", "approval_live": bool(approval["live"])})
        return {"pid": 1, "returncode": launch_returncode, "log_path": str(log_path) if log_path else None}

    def spy_cleanup(**kwargs: object) -> tuple[bool, list[str]]:
        run_root = kwargs.get("run_root")
        observed["cleanup_run_root"] = run_root
        events.append({"kind": "cleanup", "run_root": None if run_root is None else str(run_root)})
        if (revoke_error is not None or revoke_interrupt is not None) and run_root is not None:
            path = Path(str(run_root))
            if path.exists():
                shutil.rmtree(path)
        return (True, [])

    monkeypatch.setattr(probe, "zed_target_already_running", lambda _names: False)
    monkeypatch.setattr(probe, "_list_process_names", lambda: [])
    monkeypatch.setattr(probe, "prepare_real_zed_probe", lambda *_a, **_k: prep)
    monkeypatch.setattr(probe, "verify_normal_operation_isolation", lambda _prep: isolation)
    monkeypatch.setattr(probe, "validate_isolation_evidence", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "_discover_live_zed_invocation", lambda _root: (zed_exe, invocation, SHA_A))
    monkeypatch.setattr(probe, "write_isolated_agent_launcher", lambda *_a, **_k: launcher)
    monkeypatch.setattr(probe, "_run_acpx_against_isolated_agent", fake_acpx)
    monkeypatch.setattr(probe, "_resolve_trust_cli", lambda _root: trust_cli)
    monkeypatch.setattr(probe, "_run", fake_run)
    monkeypatch.setattr(probe, "_run_interactive_required", fake_interactive)
    monkeypatch.setattr(probe, "_revoke_temporary_approval", fake_revoke)
    monkeypatch.setattr(probe, "build_opaque_relay_command", spy_build_opaque_relay_command)
    monkeypatch.setattr(probe, "seed_hermetic_zed_settings", spy_seed_hermetic_zed_settings)
    monkeypatch.setattr(probe, "_observe_zed_help", lambda _exe: "--user-data-dir")
    monkeypatch.setattr(probe, "build_real_zed_launch_argv", capture_launch_argv)
    monkeypatch.setattr(probe, "_launch_zed_once", fake_launch)
    monkeypatch.setattr(probe, "normal_workspace_source_digest", lambda _root: SHA_C)
    monkeypatch.setattr(probe, "_cleanup_plan1119_roots", spy_cleanup)
    reports_root = tmp_path / "reports"
    reports_root.mkdir()
    monkeypatch.setattr(probe, "REPORTS_ROOT", reports_root)
    return parent, reports_root / PLAN_1124_REPORT_NAME, hermetic, observed


def test_run_plan1119_real_zed_seeds_discovered_user_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caller must seed <user-data-dir>/config/settings.json before launch, not zed-appdata."""
    import tools.probe_p11_zed_session_load as probe
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, hermetic, observed = _install_stubbed_real_zed(tmp_path, monkeypatch)
    stub_launch = probe._launch_zed_once

    def fake_launch_with_boundary_asserts(*args: object, **kwargs: object) -> dict[str, object]:
        assert observed["seed_first_arg"] == Path(hermetic)
        assert (hermetic / "config" / "settings.json").is_file()
        assert not (hermetic / "Zed" / "settings.json").exists()
        roots = sorted(parent.glob("p1119-real-zed-*"))
        assert roots
        assert not (roots[-1] / "zed-appdata").exists()
        assert observed["launched_environment_bind"] == ()
        return stub_launch(*args, **kwargs)

    monkeypatch.setattr(probe, "_launch_zed_once", fake_launch_with_boundary_asserts)
    run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)


def test_real_zed_relay_child_argv_contains_interpreter_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(tmp_path, monkeypatch)
    run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)

    child_executable = str(observed["child_executable"])
    child_args = list(observed["child_args"])  # type: ignore[arg-type]
    resolved_child_argv = [child_executable, *child_args]

    expected_exe = Path(sys.executable).resolve()
    non_flag_items = [item for item in resolved_child_argv if not str(item).startswith("--")]
    non_flag_paths = [Path(item).resolve() for item in non_flag_items]
    assert non_flag_paths.count(expected_exe) == 1

    assert Path(resolved_child_argv[0]).resolve() == expected_exe
    expected_launcher = (tmp_path / "scratch" / "probe-build" / "isolated_optimus_agent.py").resolve()
    assert Path(resolved_child_argv[1]).resolve() == expected_launcher

    workspace_root = Path(resolved_child_argv[resolved_child_argv.index("--workspace-root") + 1]).resolve()
    assert workspace_root.name == "zed-workspace"
    assert "--no-auto-start" in resolved_child_argv


def test_guided_timeout_is_threaded_to_launch_without_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(tmp_path, monkeypatch)
    run_plan1119_real_zed(parent, launch_timeout_seconds=900.0, report_dir=report_dir)
    assert observed["timeout_s"] == 900.0


def test_materialization_failure_records_sanitized_reason_without_changing_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tools.probe_p11_zed_session_load as probe
    from tools.probe_p11_zed_session_load import _safe_payload, run_plan1119_real_zed

    parent, report_dir, hermetic, _observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, write_capture=True
    )
    leaky_path = str((hermetic / "settings.json").resolve())
    secret = "OPTIMUS_API_KEY=sk-live-not-for-disk"
    thrown: list[OSError] = []

    def boom(**_kwargs: object) -> Path:
        exc = OSError(13, f"Permission denied {secret}", leaky_path)
        thrown.append(exc)
        raise exc

    monkeypatch.setattr(probe, "materialize_sanitized_zed_evidence", boom)
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    assert len(thrown) == 1
    recorded = result["evidence_materialization_error"]
    assert recorded["type"] == type(thrown[0]).__name__
    assert recorded["stage"] == "evidence_bundle"
    assert recorded["message"] == _safe_payload(str(thrown[0]))
    payload = json.dumps(result, default=str)
    assert "sk-live-not-for-disk" not in payload
    assert "evidence_manifest" not in result
    assert not report_dir.exists()
    assert result["finding"] == Finding.INDETERMINATE.value
    assert result["indeterminate_reason"] == "OBSERVATION_INCOMPLETE"
    sidecar_text = Path(str(result["sidecar"])).read_text(encoding="utf-8")
    assert "evidence_materialization_error" in sidecar_text
    assert "sk-live-not-for-disk" not in sidecar_text


def test_real_zed_path_publishes_nonempty_sanitized_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, _observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, write_capture=True
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    assert "evidence_materialization_error" not in result
    manifest = Path(str(result["evidence_manifest"]))
    verify_manifest(manifest)
    assert (report_dir / "relay" / "zed-to-agent.bin").read_bytes()
    assert (report_dir / "relay" / "agent-to-zed.bin").read_bytes()


def test_real_zed_sidecar_and_bundle_include_bounded_sanitized_child_stderr_excerpt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, _observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, write_capture=True
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)

    excerpt = result.get("relay_child_stderr_excerpt")
    assert isinstance(excerpt, str)
    assert len(excerpt) <= 4000
    assert RELAY_CHILD_STDERR_CANARY not in excerpt
    assert RELAY_CHILD_STDERR_RAW_SCRATCH_PATH not in excerpt

    sidecar = Path(str(result["sidecar"])).read_text(encoding="utf-8")
    sidecar_payload = json.loads(sidecar)
    assert sidecar_payload["relay_child_stderr_excerpt"] == excerpt

    manifest_path = Path(str(result["evidence_manifest"]))
    verify_manifest(manifest_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["relay_child_stderr_excerpt"] == excerpt

    # Raw diagnostic must not be persisted into the reconstructed bundle.
    assert not (report_dir / "relay-child-stderr.txt").exists()
    assert not (report_dir / "relay" / "relay-child-stderr.txt").exists()

    expected_files = {
        report_dir / "manifest.json",
        report_dir / "report.md",
        report_dir / "relay" / "zed-to-agent.bin",
        report_dir / "relay" / "agent-to-zed.bin",
    }
    actual_files = {p for p in report_dir.rglob("*") if p.is_file()}
    assert actual_files == expected_files


def test_relay_child_stderr_excerpt_sanitizes_before_truncating_to_prevent_secret_fragment_leak(
    tmp_path: Path,
) -> None:
    """Tail-first truncation can cut a secret prefix so regex-based redaction misses it."""
    from tools.probe_p11_zed_session_load import _relay_child_stderr_excerpt

    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)

    limit = 4000
    secret_full = "OPTIMUS_API_KEY=sk-live-not-for-disk"
    leaked_fragment = "live-not-for-disk"
    secret_prefix = "OPTIMUS_API_KEY=sk-"
    offset_in_secret = len(secret_prefix)
    filler_after_len = limit + offset_in_secret - len(secret_full)
    assert filler_after_len >= 0

    # Make the excerpt boundary start inside the secret value (after `sk-`), so
    # tail-first truncation would drop the redaction-matching key/prefix.
    raw = "A" + secret_full + ("B" * filler_after_len)
    (run_dir / "relay-child-stderr.txt").write_text(raw, encoding="utf-8")

    excerpt = _relay_child_stderr_excerpt(run_dir, limit=limit)
    assert len(excerpt) <= limit
    assert leaked_fragment not in excerpt


def test_real_zed_approves_actual_workspace_only_for_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Option A: create zed-workspace early, approve that exact identity only for launch."""
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, write_capture=True
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    events = list(observed["events"])  # type: ignore[arg-type]
    kinds = _event_kinds(events)

    acpx_events = _events_of(events, "acpx")
    assert len(acpx_events) == 1
    assert acpx_events[0]["zed_workspace_exists"] is True
    assert acpx_events[0]["approval_live"] is False

    inspect_events = _events_of(events, "inspect")
    approve_events = _events_of(events, "approve")
    revoke_events = _events_of(events, "revoke")
    launch_starts = _events_of(events, "launch_start")
    spawns = _events_of(events, "child_spawn")
    assert len(inspect_events) == 1
    assert len(approve_events) == 1
    assert len(revoke_events) == 1
    assert len(launch_starts) == 1
    assert kinds.index("acpx") < kinds.index("inspect")
    assert kinds.index("settings_prepared") < kinds.index("approve")
    assert kinds.index("relay_prepared") < kinds.index("approve")
    assert kinds.index("launch_argv_prepared") < kinds.index("approve")
    assert kinds.index("approve") < kinds.index("launch_start")
    assert kinds.index("launch_return") < kinds.index("revoke")
    assert kinds[kinds.index("approve") + 1] == "launch_start"

    approve_command = list(approve_events[0]["command"])  # type: ignore[arg-type]
    child_args = list(observed["child_args"])  # type: ignore[arg-type]
    approved_workspace = _workspace_from_command(approve_command)
    child_workspace = _workspace_from_command(child_args)
    launch_cwd = Path(str(launch_starts[0]["cwd"])).resolve()
    revoked_workspace = Path(str(revoke_events[0]["workspace"])).resolve()
    assert approved_workspace == child_workspace == launch_cwd == revoked_workspace
    assert approved_workspace.name == "zed-workspace"
    assert approve_command[-3:] == ["approve", "--mode", "durable"]
    assert approve_events[0]["stage"] == "zed_workspace_approval"
    assert "--launch-approval-id" not in approve_command
    assert "--launch-approval-id" not in child_args
    assert all("p996_" not in part for part in approve_command)
    assert launch_starts[0]["approval_live"] is True
    assert len(spawns) == 2
    assert all(spawn["approval_live"] is True for spawn in spawns)
    assert _events_of(events, "launch_return")[0]["approval_live"] is True
    serialized = json.dumps(result, default=str)
    assert "--launch-approval-id" not in serialized
    assert "p996_" not in serialized
    lifecycle = result["zed_workspace_approval"]
    assert lifecycle["mode"] == "durable"
    assert lifecycle["created"] is True
    assert lifecycle["child_workspace_match"] is True
    assert lifecycle["revoked"] is True
    assert "approval_id" not in lifecycle


@pytest.mark.parametrize("failure", ["inspect", "approve"])
def test_real_zed_approval_failure_prevents_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    kwargs: dict[str, object] = {}
    if failure == "inspect":
        kwargs["inspect_returncode"] = 0
    else:
        kwargs["approve_error"] = "exit=1"
    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, **kwargs
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    events = list(observed["events"])  # type: ignore[arg-type]
    assert _events_of(events, "launch_start") == []
    assert _events_of(events, "revoke") == []
    assert result["zed_launches"] == 0
    assert result["finding"] == Finding.INDETERMINATE.value
    assert result["indeterminate_reason"] == "LIVE_LAUNCH_UNAUTHORIZED"
    assert "evidence_manifest" not in result
    assert not report_dir.exists()


@pytest.mark.parametrize("failure", ["exception", "nonzero"])
def test_real_zed_launch_failure_still_revokes_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    kwargs: dict[str, object] = (
        {"launch_error": "Zed crashed"} if failure == "exception" else {"launch_returncode": 2}
    )
    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, **kwargs
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    events = list(observed["events"])  # type: ignore[arg-type]
    assert len(_events_of(events, "launch_start")) == 1
    revoke_events = _events_of(events, "revoke")
    assert len(revoke_events) == 1
    assert _event_kinds(events).index("launch_start") < _event_kinds(events).index("revoke")
    assert result["finding"] == Finding.INDETERMINATE.value
    assert result["indeterminate_reason"] != "CLEANUP_UNVERIFIED"
    assert result["zed_workspace_approval"]["revoked"] is True


def test_real_zed_revoke_failure_retains_workspace_and_blocks_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(
        tmp_path, monkeypatch, write_capture=True, revoke_error="inspect exit=0"
    )
    result = run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    events = list(observed["events"])  # type: ignore[arg-type]
    assert len(_events_of(events, "launch_start")) == 1
    assert len(_events_of(events, "revoke")) == 1
    roots = sorted(parent.glob("p1119-real-zed-*"))
    assert len(roots) == 1
    run_root = roots[0]
    workspace = run_root / "zed-workspace"
    assert run_root.is_dir()
    assert workspace.is_dir()
    assert observed.get("cleanup_run_root") is None
    assert result["isolation"]["cleanup_verified"] is False
    assert result["finding"] == Finding.INDETERMINATE.value
    assert result["indeterminate_reason"] == "CLEANUP_UNVERIFIED"
    assert "evidence_manifest" not in result
    assert not report_dir.exists()
    remediation = result["cleanup_remediation"]
    assert remediation[-1] == "revoke"
    assert _workspace_from_command([str(part) for part in remediation]) == workspace.resolve()
    assert all("approval" not in str(part).casefold() for part in remediation)
    assert all("p996_" not in str(part) for part in remediation)
    assert "--launch-approval-id" not in json.dumps(result, default=str)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit, RuntimeError])
def test_real_zed_revoke_interrupt_retains_workspace_and_records_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interrupt: type[BaseException]
) -> None:
    """Unexpected revoke failures must retain zed-workspace and record remediation before re-raising."""
    import tools.probe_p11_zed_session_load as probe
    from tools.probe_p11_zed_session_load import run_plan1119_real_zed

    recorded: list[dict[str, object]] = []
    real_record = probe._record_zed_workspace_revoke_failure

    def spy_record(*args: object, **kwargs: object) -> None:
        recorded.append({"args": args, "kwargs": kwargs})
        real_record(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(probe, "_record_zed_workspace_revoke_failure", spy_record)
    parent, report_dir, _hermetic, observed = _install_stubbed_real_zed(
        tmp_path,
        monkeypatch,
        write_capture=True,
        revoke_interrupt=interrupt(),
    )
    with pytest.raises(interrupt):
        run_plan1119_real_zed(parent, launch_timeout_seconds=180.0, report_dir=report_dir)
    events = list(observed["events"])  # type: ignore[arg-type]
    assert len(_events_of(events, "launch_start")) == 1
    assert len(_events_of(events, "revoke")) == 1
    roots = sorted(parent.glob("p1119-real-zed-*"))
    assert len(roots) == 1
    run_root = roots[0]
    workspace = run_root / "zed-workspace"
    assert run_root.is_dir()
    assert workspace.is_dir()
    assert observed.get("cleanup_run_root") is None
    assert len(recorded) == 1
    record_call = recorded[0]
    result_arg = record_call["args"][0]
    record_kwargs = record_call["kwargs"]
    assert record_kwargs["stage"] == "zed_workspace_revoke"
    assert "interrupted during revoke" in str(record_kwargs["message"])
    remediation = result_arg["cleanup_remediation"]  # type: ignore[index]
    assert remediation[-1] == "revoke"
    assert _workspace_from_command([str(part) for part in remediation]) == workspace.resolve()
    assert bool(observed["approval"]["live"]) is True  # type: ignore[index]

# --- Task 15: Git-blob authority and freshness gate ---

def _establishing_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_establishing_repo(repo: Path, *, content: str = "alpha\n", path: str = "tracked.txt") -> str:
    repo.mkdir(parents=True, exist_ok=True)
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    _establishing_git(repo, "init")
    _establishing_git(repo, "config", "user.email", "probe@example.test")
    _establishing_git(repo, "config", "user.name", "Probe")
    _establishing_git(repo, "add", "-A")
    _establishing_git(repo, "commit", "-m", "init")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def _build_v2_establishing_report_text(record: dict[str, object]) -> str:
    return "\n".join(
        [
            "# Plan 11.24 agent protocol persistence establishing drive",
            "",
            "## Typed reconstruction record",
            "",
            "```json",
            json.dumps(record, sort_keys=True),
            "```",
            "",
        ]
    )


def _minimal_v2_record(
    *,
    source_commit: str,
    manifest: dict[str, object],
    completed_at_utc: str,
    python_version: str = "3.14.0",
    python_executable_sha256: str = SHA_B,
    acpx_version: str = "0.0.test",
    acpx_command_sha256: str = SHA_C,
    acpx_cli_js_sha256: str = SHA_B,
    trust_executable_sha256: str = SHA_B,
    isolated_launcher_canonical_sha256: str = SHA_A,
    isolated_launcher_raw_sha256: str = SHA_A,
    isolated_patched_spec_sha256: str = SHA_B,
) -> dict[str, object]:
    return {
        "schema": "plan-11-24-agent-protocol-establishing-v2",
        "establishing_disposition": "NO_GATEWAY_PATH_ESTABLISHED",
        "completed_at_utc": completed_at_utc,
        "authority": {
            "source_commit": source_commit,
            "source_commit_execution_surface_clean": True,
            "applicability": manifest,
            "python_version": python_version,
            "python_executable_sha256": python_executable_sha256,
            "acpx_version": acpx_version,
            "acpx_command_sha256": acpx_command_sha256,
            "acpx_cli_js_sha256": acpx_cli_js_sha256,
            "trust_executable_sha256": trust_executable_sha256,
            "isolated_launcher_canonical_sha256": isolated_launcher_canonical_sha256,
            "isolated_launcher_raw_sha256": isolated_launcher_raw_sha256,
            "isolated_patched_spec_sha256": isolated_patched_spec_sha256,
        },
        "counts": {"zed_launches": 0, "origin_a_launches": 0},
        "sequence": {
            "session_new": {"request_id": 1, "session_id": "sess-1"},
            "session_prompt": {
                "request_id": 2,
                "session_id": "sess-1",
                "request_count": 1,
                "message_sha256": SHA_C,
                "outcome": "error",
                "response_id_matches": True,
                "error_code": -32000,
            },
            "session_load": {"request_id": 3, "session_id": "sess-1", "response_id_matches": True, "result": {}},
        },
        "traffic": {
            "gateway_attempted": False,
            "provider_attempted": False,
            "model_call_attempted": False,
        },
        "custody": {
            "approval_created": True,
            "approval_revoked": True,
            "post_revoke_inspect_exit_code": 1,
        },
        "cleanup": {"throwaway_root_removed": True},
    }


def test_establishing_applicability_hashes_git_blobs_not_worktree_bytes(tmp_path: Path) -> None:
    """genuine RED baseline: blob digest must ignore worktree normalization."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    commit = _init_establishing_repo(repo, content="line\n", path="sample.txt")
    blob_digest = probe.hash_git_blob_bytes(probe.git_cat_file_blob(repo, commit, "sample.txt"))
    (repo / "sample.txt").write_text("line\r\n", encoding="utf-8")
    worktree_digest = probe.hash_git_blob_bytes((repo / "sample.txt").read_bytes())
    manifest = probe.build_applicability_manifest(repo, commit, ("sample.txt",))
    assert manifest["files"][0]["blob_sha256"] == blob_digest
    assert blob_digest != worktree_digest


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(
            lambda repo: (
                (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8"),
                _establishing_git(repo, "add", "tracked.txt"),
            ),
            id="staged",
        ),
        pytest.param(lambda repo: (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8"), id="unstaged"),
        pytest.param(
            lambda repo: (
                _establishing_git(repo, "rm", "tracked.txt"),
                (repo / "tracked.txt").write_text("resurrected\n", encoding="utf-8"),
            ),
            id="deleted",
        ),
        pytest.param(
            lambda repo: (
                _establishing_git(repo, "mv", "tracked.txt", "renamed.txt"),
                (repo / "renamed.txt").write_text("renamed-body\n", encoding="utf-8"),
            ),
            id="renamed",
        ),
        pytest.param(
            lambda repo: (
                _establishing_git(repo, "rm", "tracked.txt"),
                _establishing_git(repo, "add", "-A"),
            ),
            id="type-changed",
        ),
    ],
)
def test_establishing_applicability_rejects_dirty_execution_surface(tmp_path: Path, mutator) -> None:
    """genuine RED baseline: dirty execution paths fail closed."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    _init_establishing_repo(repo)
    mutator(repo)
    assert probe.execution_surface_clean(repo, ("tracked.txt",)) is False


def test_establishing_import_closure_equals_explicit_module_path_subset() -> None:
    """baseline-green preservation: live AST closure matches the explicit 128-file subset."""
    import tools.probe_p11_zed_session_load as probe

    closure = probe.compute_establishing_import_closure(REPO_ROOT)
    expected = frozenset(path for path in probe.ESTABLISHING_EXECUTION_GIT_PATHS if path.endswith(".py"))
    assert closure == expected
    assert len(closure) == 128


def test_establishing_import_closure_traverses_package_init_reexports(tmp_path: Path) -> None:
    """genuine RED baseline: package __init__ re-exports must expand closure."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    (repo / "tools" / "pkg").mkdir(parents=True)
    (repo / "tools" / "pkg" / "__init__.py").write_text("from tools.pkg.leaf import value\n", encoding="utf-8")
    (repo / "tools" / "pkg" / "leaf.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "tools" / "entry.py").write_text("from tools.pkg import value\n", encoding="utf-8")
    _establishing_git(repo, "init")
    _establishing_git(repo, "config", "user.email", "probe@example.test")
    _establishing_git(repo, "config", "user.name", "Probe")
    _establishing_git(repo, "add", "-A")
    _establishing_git(repo, "commit", "-m", "init")
    allowed = frozenset(
        {
            "tools/pkg/__init__.py",
            "tools/pkg/leaf.py",
            "tools/entry.py",
        }
    )
    closure = probe.compute_establishing_import_closure(
        repo,
        root_modules=("tools.entry",),
        allowed_py_paths=allowed,
    )
    assert "tools/pkg/__init__.py" in closure
    assert "tools/pkg/leaf.py" in closure


def _commit_establishing_repo(repo: Path) -> None:
    _establishing_git(repo, "add", "-A")
    _establishing_git(repo, "commit", "-m", "init")


@pytest.mark.parametrize(
    ("layout", "root_modules", "allowed_paths", "expect_reject"),
    [
        pytest.param(
            {
                "tools/entry.py": "from tools.secret import token\n",
                "tools/secret.py": "token = 'x'\n",
            },
            ("tools.entry",),
            frozenset({"tools/entry.py"}),
            True,
            id="tools_top_level_unlisted_sibling",
        ),
        pytest.param(
            {
                "src/optimus/__init__.py": "",
                "src/optimus/acp/__init__.py": "",
                "src/optimus/acp/entry.py": "from optimus.acp.sneaky import token\n",
                "src/optimus/acp/sneaky.py": "token = 'x'\n",
            },
            ("optimus.acp.entry",),
            frozenset(
                {
                    "src/optimus/__init__.py",
                    "src/optimus/acp/__init__.py",
                    "src/optimus/acp/entry.py",
                }
            ),
            True,
            id="package_from_import_unlisted_sibling",
        ),
        pytest.param(
            {
                "src/optimus/__init__.py": "",
                "src/optimus/acp/__init__.py": "",
                "src/optimus/acp/entry.py": "import optimus.acp.sneaky\n",
                "src/optimus/acp/sneaky.py": "token = 'x'\n",
            },
            ("optimus.acp.entry",),
            frozenset(
                {
                    "src/optimus/__init__.py",
                    "src/optimus/acp/__init__.py",
                    "src/optimus/acp/entry.py",
                }
            ),
            True,
            id="package_plain_import_unlisted_sibling",
        ),
        pytest.param(
            {
                "src/optimus/__init__.py": "",
                "src/optimus/acp/__init__.py": "from .sneaky import token\n",
                "src/optimus/acp/entry.py": "value = 1\n",
                "src/optimus/acp/sneaky.py": "token = 'x'\n",
            },
            ("optimus.acp.entry",),
            frozenset(
                {
                    "src/optimus/__init__.py",
                    "src/optimus/acp/__init__.py",
                    "src/optimus/acp/entry.py",
                }
            ),
            True,
            id="package_relative_import_unlisted_sibling",
        ),
        pytest.param(
            {
                "src/optimus/__init__.py": "",
                "src/optimus/acp/__init__.py": "",
                "src/optimus/acp/spec.py": "class SomeClass:\n    pass\n",
                "src/optimus/acp/entry.py": "from optimus.acp.spec import SomeClass\n",
            },
            ("optimus.acp.entry",),
            frozenset(
                {
                    "src/optimus/__init__.py",
                    "src/optimus/acp/__init__.py",
                    "src/optimus/acp/spec.py",
                    "src/optimus/acp/entry.py",
                }
            ),
            False,
            id="package_symbol_import_from_listed_module",
        ),
    ],
)
def test_establishing_import_closure_rejects_unlisted_new_project_module(
    tmp_path: Path,
    layout: dict[str, str],
    root_modules: tuple[str, ...],
    allowed_paths: frozenset[str],
    expect_reject: bool,
) -> None:
    """Unlisted in-repo modules must fail closed; symbol imports from listed modules still resolve."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    repo.mkdir()
    for relative, content in layout.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _establishing_git(repo, "init")
    _establishing_git(repo, "config", "user.email", "probe@example.test")
    _establishing_git(repo, "config", "user.name", "Probe")
    _commit_establishing_repo(repo)
    if expect_reject:
        with pytest.raises(probe.ProbeError, match="unlisted module path"):
            probe.compute_establishing_import_closure(
                repo, root_modules=root_modules, allowed_py_paths=allowed_paths
            )
    else:
        closure = probe.compute_establishing_import_closure(
            repo, root_modules=root_modules, allowed_py_paths=allowed_paths
        )
        assert "src/optimus/acp/spec.py" in closure


def test_establishing_authority_allows_report_only_descendant_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED baseline: descendant report-only commit remains authorized when manifest matches."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    source_commit = _init_establishing_repo(repo)
    manifest = probe.build_applicability_manifest(repo, source_commit, ("tracked.txt",))
    completed_at = probe.serialize_aware_utc_timestamp(probe.datetime.now(probe.UTC))
    isolated_root = str(tmp_path / "isolated-source")
    canonical = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(probe.ISOLATED_SOURCE_ROOT))
    raw = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(isolated_root))
    record = _minimal_v2_record(
        source_commit=source_commit,
        manifest=manifest,
        completed_at_utc=completed_at,
        isolated_launcher_canonical_sha256=canonical,
        isolated_launcher_raw_sha256=raw,
    )
    report_text = _build_v2_establishing_report_text(record)
    report_path = repo / "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8", newline="\n")
    _establishing_git(repo, "add", "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md")
    _establishing_git(repo, "commit", "-m", "report only")
    head_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    monkeypatch.setattr(probe, "read_committed_establishing_report_blob", lambda _r: report_text.encode("utf-8"))
    monkeypatch.setattr(probe, "parse_establishing_report_v2", lambda _blob: record)
    monkeypatch.setattr(probe, "is_ancestor", lambda _r, ancestor, head: ancestor == source_commit and head == head_commit)
    monkeypatch.setattr(probe, "verify_establishing_execution_surface", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "build_applicability_manifest", lambda _r, _c, paths=("tracked.txt",): manifest)
    monkeypatch.setattr(
        probe,
        "_resolve_python_identity",
        lambda: {"python_version": "3.14.0", "python_executable_sha256": SHA_B},
    )
    monkeypatch.setattr(probe, "_resolve_trust_executable_identity", lambda _r: {"trust_executable_sha256": SHA_B})
    monkeypatch.setattr(
        probe,
        "resolve_acpx_identities",
        lambda *_a, **_k: {"version": "0.0.test", "command_sha256": SHA_C, "cli_js_sha256": SHA_B},
    )
    monkeypatch.setattr(probe, "_resolve_acpx", lambda: tmp_path / "acpx.cmd")
    monkeypatch.setattr(
        probe,
        "_resolve_isolated_identity",
        lambda _r, source_root: {
            "isolated_launcher_canonical_sha256": canonical,
            "isolated_patched_spec_sha256": SHA_B,
            "isolated_launcher_raw_sha256": raw,
        },
    )
    result = {
        "commit": head_commit,
        "isolated_launcher_source_root": isolated_root,
        "isolated_build": {"sha256": raw},
        "zed_launches": 0,
    }
    assert probe._require_established_agent_protocol_prerequisite(result) is True
    assert result["zed_launches"] == 0


def test_establishing_authority_rejects_untracked_authorizing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED baseline: untracked worktree report is not authorizing."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    _init_establishing_repo(repo)
    report_path = repo / "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("untracked\n", encoding="utf-8")
    monkeypatch.setattr(
        probe,
        "read_committed_establishing_report_blob",
        lambda _r: (_ for _ in ()).throw(probe.ProbeError("establishing_report", "report path is not clean")),
    )
    result = {"commit": "a" * 40, "zed_launches": 0}
    assert probe._require_established_agent_protocol_prerequisite(result) is False
    assert result["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert result["zed_launches"] == 0


def test_establishing_authority_rejects_dirty_tracked_authorizing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED baseline: dirty tracked report rejects before launch."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    _init_establishing_repo(repo, path="reports/plan-11-24-agent-protocol-persistence-establishing-drive.md")
    (repo / "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md").write_text("dirty\n", encoding="utf-8")
    monkeypatch.setattr(
        probe,
        "read_committed_establishing_report_blob",
        lambda _r: (_ for _ in ()).throw(probe.ProbeError("establishing_report", "report path is not clean")),
    )
    result = {"commit": "a" * 40, "zed_launches": 0}
    assert probe._require_established_agent_protocol_prerequisite(result) is False
    assert result["zed_launches"] == 0


def test_establishing_authority_reads_committed_report_blob_not_worktree_bytes(tmp_path: Path) -> None:
    """genuine RED baseline: parser reads HEAD blob bytes only."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    report_rel = "reports/plan-11-24-agent-protocol-persistence-establishing-drive.md"
    _init_establishing_repo(repo, content="committed\n", path=report_rel)
    _establishing_git(repo, "config", "core.autocrlf", "true")
    report_path = repo / report_rel
    blob = probe.git_cat_file_blob(repo, "HEAD", report_rel)
    worktree_bytes = report_path.read_bytes()
    committed = probe.read_committed_establishing_report_blob(repo)
    assert committed == blob
    if worktree_bytes != blob:
        assert committed != worktree_bytes


def test_establishing_authority_rejects_nonancestor_or_surface_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """genuine RED baseline: non-ancestor source or manifest drift rejects."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    source_commit = _init_establishing_repo(repo)
    manifest = probe.build_applicability_manifest(repo, source_commit, ("tracked.txt",))
    completed_at = probe.serialize_aware_utc_timestamp(probe.datetime.now(probe.UTC))
    record = _minimal_v2_record(source_commit="b" * 40, manifest=manifest, completed_at_utc=completed_at)
    monkeypatch.setattr(probe, "read_committed_establishing_report_blob", lambda _r: _build_v2_establishing_report_text(record).encode("utf-8"))
    monkeypatch.setattr(probe, "parse_establishing_report_v2", lambda _blob: record)
    monkeypatch.setattr(probe, "is_ancestor", lambda *_a, **_k: False)
    result = {"commit": source_commit, "zed_launches": 0}
    assert probe._require_established_agent_protocol_prerequisite(result) is False
    assert result["zed_launches"] == 0

    drift_manifest = dict(manifest)
    drift_manifest["manifest_sha256"] = "d" * 64
    record_drift = _minimal_v2_record(source_commit=source_commit, manifest=drift_manifest, completed_at_utc=completed_at)
    monkeypatch.setattr(probe, "read_committed_establishing_report_blob", lambda _r: _build_v2_establishing_report_text(record_drift).encode("utf-8"))
    monkeypatch.setattr(probe, "parse_establishing_report_v2", lambda _blob: record_drift)
    monkeypatch.setattr(probe, "is_ancestor", lambda *_a, **_k: True)
    monkeypatch.setattr(probe, "verify_establishing_execution_surface", lambda *_a, **_k: None)
    monkeypatch.setattr(probe, "build_applicability_manifest", lambda *_a, **_k: manifest)
    result = {"commit": source_commit, "zed_launches": 0}
    assert probe._require_established_agent_protocol_prerequisite(result) is False


def test_canonical_launcher_identity_ignores_only_run_root(tmp_path: Path) -> None:
    """genuine RED baseline: canonical launcher digest is stable across run roots."""
    import tools.probe_p11_zed_session_load as probe

    first = tmp_path / "source-a"
    second = tmp_path / "source-b"
    canonical = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(probe.ISOLATED_SOURCE_ROOT))
    raw_a = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(first))
    raw_b = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(second))
    assert raw_a != raw_b
    assert raw_a != canonical
    assert raw_b != canonical


def test_raw_launcher_sha_is_audit_only_not_cross_run_authority(tmp_path: Path) -> None:
    """baseline-green preservation: raw launcher digests differ while canonical stays fixed."""
    import tools.probe_p11_zed_session_load as probe

    roots = [tmp_path / "run-a", tmp_path / "run-b"]
    canonical = probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(probe.ISOLATED_SOURCE_ROOT))
    raw_digests = [probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(root)) for root in roots]
    assert raw_digests[0] != raw_digests[1]
    assert all(
        probe.hash_git_blob_bytes(probe.render_isolated_launcher_bytes(probe.ISOLATED_SOURCE_ROOT)) == canonical
        for _ in roots
    )


def test_isolated_probe_patch_writes_exact_git_blob_bytes_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """genuine RED baseline: patched spec uses write_bytes from git blob, not CRLF text IO."""
    import tools.probe_p11_zed_session_load as probe

    repo = tmp_path / "repo"
    spec_rel = "src/optimus/acp/spec.py"
    spec_path = repo / spec_rel
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(REAL_SPEC.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    _establishing_git(repo, "init")
    _establishing_git(repo, "config", "user.email", "probe@example.test")
    _establishing_git(repo, "config", "user.name", "Probe")
    _establishing_git(repo, "config", "core.autocrlf", "true")
    _establishing_git(repo, "add", "-A")
    _establishing_git(repo, "commit", "-m", "spec")
    blob = probe.git_cat_file_blob(repo, "HEAD", spec_rel)
    expected = probe.compute_isolated_patched_spec_bytes(blob)
    isolated_spec = tmp_path / "isolated" / spec_rel
    monkeypatch.setattr(probe, "git_cat_file_blob", lambda _r, _c, path: blob if path == spec_rel else b"")
    probe._apply_isolated_probe_patch(isolated_spec, repo_root=repo)
    assert isolated_spec.read_bytes() == expected
    assert b"\r\n" not in isolated_spec.read_bytes()


def test_acpx_identity_binds_cli_js_not_generic_npm_shim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """genuine RED baseline: authority binds acpx version + cli.js SHA, not shim alone."""
    import tools.probe_p11_zed_session_load as probe

    acpx_cmd = tmp_path / "acpx.cmd"
    acpx_cmd.write_text("@echo off\n", encoding="utf-8")
    cli_js = tmp_path / "node_modules" / "acpx" / "dist" / "cli.js"
    cli_js.parent.mkdir(parents=True)
    cli_js.write_bytes(b"console.log('cli-v1')\n")
    monkeypatch.setattr(probe, "_acpx_version", lambda *_a, **_k: "1.0.0")
    identity = probe.resolve_acpx_identities(acpx_cmd, cwd=tmp_path, env={})
    cli_js.write_bytes(b"console.log('cli-v2')\n")
    changed = probe.resolve_acpx_identities(acpx_cmd, cwd=tmp_path, env={})
    assert identity["command_sha256"] == changed["command_sha256"]
    assert identity["cli_js_sha256"] != changed["cli_js_sha256"]


def test_establishing_report_freshness_uses_completion_time_and_dedicated_bound() -> None:
    """genuine RED baseline: freshness uses dedicated 86400-second bound."""
    import tools.probe_p11_zed_session_load as probe

    now = probe.datetime(2026, 1, 2, tzinfo=probe.UTC)
    completed = probe.serialize_aware_utc_timestamp(now - probe.timedelta(seconds=probe.ESTABLISHING_REPORT_MAX_AGE_SECONDS))
    probe.validate_establishing_report_freshness(completed, now)
    stale = probe.serialize_aware_utc_timestamp(now - probe.timedelta(seconds=probe.ESTABLISHING_REPORT_MAX_AGE_SECONDS + 1))
    with pytest.raises(ValueError, match="stale"):
        probe.validate_establishing_report_freshness(stale, now)
    assert probe.ESTABLISHING_REPORT_MAX_AGE_SECONDS != probe.MAX_ZED_LAUNCH_TIMEOUT_SECONDS


def test_establishing_report_freshness_accepts_z_and_plus_zero_and_serializes_z() -> None:
    """genuine RED baseline: Z and +00:00 accepted; persisted serialization uses Z."""
    import tools.probe_p11_zed_session_load as probe

    dt = probe.datetime(2026, 1, 1, 12, 0, tzinfo=probe.UTC)
    z_value = "2026-01-01T12:00:00+00:00"
    parsed = probe.parse_aware_utc_timestamp(z_value)
    assert probe.serialize_aware_utc_timestamp(parsed) == "2026-01-01T12:00:00Z"
    probe.validate_establishing_report_freshness("2026-01-01T12:00:00Z", dt)


@pytest.mark.parametrize(
    "timestamp,matcher",
    [
        ("2026-01-01T12:00:00", "timestamp must end"),
        ("2026-01-01T12:00:00-05:00", "timestamp must end"),
        ("2026-01-01T12:00:00-00:00", "unsupported UTC offset"),
        ("2030-01-01T00:00:00Z", "future"),
    ],
)
def test_establishing_report_freshness_rejects_stale_future_naive_minus_zero_and_non_utc(
    timestamp: str, matcher: str
) -> None:
    """genuine RED baseline: malformed/future timestamps reject."""
    import tools.probe_p11_zed_session_load as probe

    now = probe.datetime(2026, 1, 1, tzinfo=probe.UTC)
    with pytest.raises(ValueError, match=matcher):
        if matcher == "future":
            probe.validate_establishing_report_freshness(timestamp, now)
        else:
            probe.parse_aware_utc_timestamp(timestamp)
